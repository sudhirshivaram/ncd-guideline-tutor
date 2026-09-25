import json
import tempfile
import unittest
from unittest.mock import patch
from app.eval.semantic import CachedCalls, dollars, parse_judgment, aggregate

class SemanticTests(unittest.IsolatedAsyncioTestCase):
    def test_missing_usage_stops(self):
        with self.assertRaises(ValueError): dollars({})
    def test_invalid_judge_score(self):
        with self.assertRaises(ValueError): parse_judgment('{"context_relevance": 8}',False)
    def test_null_is_not_success(self):
        self.assertIsNone(aggregate([])['all']['citation_support']['mean_0_to_2'])
    async def test_budget_prevents_call(self):
        with tempfile.TemporaryDirectory() as folder:
            calls=CachedCalls(folder,True,.000001)
            with patch('app.eval.semantic.stream_llm') as stream:
                with self.assertRaises(RuntimeError): await calls.call([{'content':'text'}],700,'test')
                stream.assert_not_called()
    async def test_cache_reuse(self):
        async def stream(*args):
            args[5].update(input_tokens=100,output_tokens=20)
            yield 'cached answer'
        with tempfile.TemporaryDirectory() as folder:
            calls=CachedCalls(folder,True)
            with patch('app.eval.semantic.stream_llm',stream):
                first=await calls.call([{'content':'text'}],700,'test')
            with patch('app.eval.semantic.stream_llm') as second:
                self.assertEqual(first,await calls.call([{'content':'text'}],700,'test'))
                second.assert_not_called()
            self.assertEqual(calls.new_calls,1)
    async def test_missing_usage_is_not_retried(self):
        async def stream(*args): yield 'answer without usage'
        with tempfile.TemporaryDirectory() as folder:
            calls=CachedCalls(folder,True)
            with patch('app.eval.semantic.stream_llm',stream):
                with self.assertRaises(RuntimeError):await calls.call([{'content':'text'}],700,'test')
            with patch('app.eval.semantic.stream_llm') as again:
                with self.assertRaises(RuntimeError):await calls.call([{'content':'text'}],700,'test')
                again.assert_not_called()

    def test_missing_nullable_metric_is_rejected(self):
        value = dict(context_relevance=2, answer_quality=2, groundedness=2,
                     refusal_correctness=None, rationale='Supported')
        with self.assertRaises(ValueError):
            parse_judgment(json.dumps(value), False)

    def test_refusal_requires_score(self):
        value = dict(context_relevance=0, answer_quality=2, groundedness=2,
                     citation_support=None, refusal_correctness=None, rationale='Refusal')
        with self.assertRaises(ValueError):
            parse_judgment(json.dumps(value), True)
        value['refusal_correctness'] = 2
        self.assertIsNone(parse_judgment(json.dumps(value), True)['citation_support'])

    async def test_resumed_budget_counts_prior_calls(self):
        async def stream(*args):
            args[5].update(input_tokens=100, output_tokens=20)
            yield 'answer'
        with tempfile.TemporaryDirectory() as folder:
            with patch('app.eval.semantic.stream_llm', stream):
                await CachedCalls(folder, True).call([{'content':'first'}], 700, 'test')
            resumed = CachedCalls(folder, True, budget=.00008)
            with patch('app.eval.semantic.stream_llm') as again:
                with self.assertRaises(RuntimeError):
                    await resumed.call([{'content':'different'}], 700, 'test')
                again.assert_not_called()
