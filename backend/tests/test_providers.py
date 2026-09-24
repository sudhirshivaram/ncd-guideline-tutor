import unittest
from types import SimpleNamespace as N
from unittest.mock import AsyncMock, MagicMock, patch
from app.rag.generate import stream_llm
from app.eval.provider_demo import cost


async def events(*items):
    for item in items:
        yield item


class ProvidersTests(unittest.IsolatedAsyncioTestCase):
    messages=[{'role':'system','content':'rules'},{'role':'user','content':'first'},{'role':'assistant','content':'reply'},{'role':'user','content':'next'}]

    async def test_openai_stream_and_usage(self):
        import openai
        client=AsyncMock()
        client.__aenter__.return_value=client
        stream=MagicMock()
        stream.__aenter__=AsyncMock(return_value=stream)
        stream.__aexit__=AsyncMock()
        stream.__aiter__.side_effect=lambda: events(N(choices=[N(delta=N(content='answer'))],usage=None),N(choices=[],usage=N(prompt_tokens=100,completion_tokens=20)))
        client.chat.completions.create=AsyncMock(return_value=stream)
        usage={}
        with patch.object(openai,'AsyncOpenAI',return_value=client):
            answer=''.join([x async for x in stream_llm('openai','test','gpt-4o-mini',self.messages,.2,usage,400)])
        self.assertEqual(answer,'answer');self.assertEqual(usage,{'input_tokens':100,'output_tokens':20})
        self.assertTrue(client.chat.completions.create.call_args.kwargs['stream_options']['include_usage'])
        self.assertEqual(client.chat.completions.create.call_args.kwargs['max_completion_tokens'],400)
        client.__aexit__.assert_awaited()

    async def test_anthropic_system_history_and_usage(self):
        import anthropic
        client=AsyncMock();client.__aenter__.return_value=client
        stream=MagicMock();stream.text_stream=events('answer')
        stream.get_final_message=AsyncMock(return_value=N(usage=N(input_tokens=100,output_tokens=20)))
        manager=MagicMock();manager.__aenter__=AsyncMock(return_value=stream);manager.__aexit__=AsyncMock()
        client.messages.stream=MagicMock(return_value=manager)
        usage={}
        with patch.object(anthropic,'AsyncAnthropic',return_value=client):
            self.assertEqual(''.join([x async for x in stream_llm('anthropic','test','claude-haiku-4-5',self.messages,.2,usage,400)]),'answer')
        kwargs=client.messages.stream.call_args.kwargs
        self.assertEqual(kwargs['system'],'rules');self.assertEqual(kwargs['messages'],self.messages[1:])
        self.assertEqual(kwargs['max_tokens'],400);self.assertEqual(usage['output_tokens'],20)
        self.assertEqual(kwargs['extra_body'], {'temperature': .2})
        client.__aexit__.assert_awaited()

    async def test_gemini_isolated_keys_history_and_thinking_usage(self):
        from google import genai
        from google.genai import types
        client=AsyncMock();client.__aenter__.return_value=client
        def stream(**kwargs):
            return events(types.GenerateContentResponse(candidates=[types.Candidate(content=types.Content(parts=[types.Part(text='answer')]))],usage_metadata=types.GenerateContentResponseUsageMetadata(prompt_token_count=100,candidates_token_count=20,thoughts_token_count=30,total_token_count=150)))
        client.models.generate_content_stream=AsyncMock(side_effect=stream)
        with patch.object(genai,'Client',return_value=N(aio=client)) as factory:
            for key in ['key-one','key-two']:
                usage={}
                answer=''.join([x async for x in stream_llm('gemini',key,'gemini-3.5-flash-lite',self.messages,.2,usage,400)])
                self.assertEqual(answer,'answer');self.assertEqual(usage['output_tokens'],50)
            self.assertEqual([c.kwargs['api_key'] for c in factory.call_args_list],['key-one','key-two'])
        kwargs=client.models.generate_content_stream.call_args.kwargs
        self.assertEqual([c.role for c in kwargs['contents']],['user','model','user'])
        self.assertEqual(kwargs['config'].max_output_tokens,400)
        client.__aexit__.assert_awaited()

    async def test_missing_key_and_output_limits(self):
        for key,limit in [('',400),('test',0),('test',1201)]:
            with self.assertRaises(ValueError):
                _=[x async for x in stream_llm('openai',key,'gpt-4o-mini',[],.2,max_output_tokens=limit)]

    def test_cost_and_unknown_usage(self):
        self.assertIsNone(cost('openai',{}))
        self.assertEqual(cost('anthropic',{'input_tokens':1000,'output_tokens':400}),.003)
        self.assertAlmostEqual(cost('openai',{'input_tokens':1000,'output_tokens':400}),.00039)


class SdkContractTests(unittest.TestCase):
    def test_installed_sdk_signatures(self):
        import inspect
        from openai.resources.chat.completions import AsyncCompletions
        from anthropic.resources.messages import AsyncMessages
        from google.genai.models import AsyncModels
        for method, names in [
            (AsyncCompletions.create, ['model','messages','temperature','stream','stream_options','max_completion_tokens']),
            (AsyncMessages.stream, ['model','system','messages','max_tokens','extra_body']),
            (AsyncModels.generate_content_stream, ['model','contents','config']),
        ]:
            with self.subTest(method=method.__qualname__):
                self.assertTrue(set(names) <= inspect.signature(method).parameters.keys())
