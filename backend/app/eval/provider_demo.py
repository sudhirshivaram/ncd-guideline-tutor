"""Three-question provider smoke test; offline projection by default, --live opts in."""
import argparse
import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from app.core.schemas import ChatSettings
from app.rag.generate import build_messages, stream_llm
from app.rag.pipeline import retrieve_contexts
from app.eval.metrics import citation_metrics

# Standard text rates, USD per million tokens. No cache discounts or free tiers assumed.
RATES = {
    'openai': {'model': 'gpt-4o-mini', 'input': .15, 'output': .60, 'env': 'OPENAI_API_KEY', 'source': 'https://developers.openai.com/api/docs/models/gpt-4o-mini'},
    'gemini': {'model': 'gemini-3.5-flash-lite', 'input': .30, 'output': 2.50, 'env': 'GOOGLE_API_KEY', 'source': 'https://ai.google.dev/gemini-api/docs/pricing'},
    'anthropic': {'model': 'claude-haiku-4-5', 'input': 1.0, 'output': 5.0, 'env': 'ANTHROPIC_API_KEY', 'source': 'https://platform.claude.com/docs/en/about-claude/pricing'},
}
QUESTIONS = [
    'When should pharmacological treatment for adult hypertension start?',
    'What is the HEARTS-D first-line treatment for type 2 diabetes?',
    'How do I connect this assistant to an EHR using FHIR based on these WHO documents?',
]


def cost(provider, usage):
    if 'input_tokens' not in usage or 'output_tokens' not in usage:
        return None
    rates = RATES[provider]
    return round((usage['input_tokens'] * rates['input'] + usage['output_tokens'] * rates['output']) / 1_000_000, 8)


async def run(live=False, providers=None):
    from app.rag.pipeline import to_citations
    rows=[]
    for question in QUESTIONS:
        contexts=retrieve_contexts(question, ChatSettings(top_k=5))
        messages=build_messages(question, contexts, [])
        # Rough offline projection, explicitly not measured provider token usage.
        approximate_input=sum(len(m['content']) for m in messages)//4 + 100
        for provider in providers or RATES:
            rates=RATES[provider]
            row={'provider': provider, 'model': rates['model'], 'question': question,
                 'estimated_input_tokens': approximate_input, 'max_output_tokens': 400,
                 'projected_usd': cost(provider, {'input_tokens': approximate_input, 'output_tokens': 400}),
                 'api_usage': None, 'usage_based_usd': None, 'status': 'offline_only'}
            key=os.environ.get(rates['env'])
            if live and not key:
                row['status']='missing_key'
            elif live:
                usage={}
                try:
                    answer=''.join([text async for text in stream_llm(provider, key, rates['model'], messages, .2, usage, 400)])
                    row.update(status='passed' if answer.strip() and usage else 'incomplete_response',
                               api_usage=usage or None, usage_based_usd=cost(provider, usage),
                               answer=answer,
                               citations=citation_metrics(answer, [c.model_dump() for c in to_citations(contexts)], []))
                except Exception as exc:
                    # Do not save provider error bodies that may contain credentials.
                    row.update(status='failed', error_type=type(exc).__name__)
            rows.append(row)
    complete=live and all(r['status']=='passed' for r in rows)
    return {'created_at':datetime.now(timezone.utc).isoformat(), 'pricing_checked':'2026-09-24',
            'rates':RATES, 'live':live, 'all_live_checks_passed':complete,
            'projected_total_usd':round(sum(r['projected_usd'] for r in rows),6),
            'usage_based_total_usd':round(sum(r['usage_based_usd'] for r in rows),6) if complete else None,
            'note':'Offline projection uses characters/4 + 100 input tokens and 400 output tokens per independent question. Live costs use API token usage at standard list rates, not invoice amounts. Cache discounts, free tiers, taxes and failed/interrupted requests are not accounted for. No automatic retries. A passed check confirms nonempty streaming output and usage, not answer quality.',
            'cases':rows}


async def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true')
    parser.add_argument('--provider',choices=list(RATES))
    parser.add_argument('--output',type=Path,default=Path('evals/provider_demo.json'))
    args=parser.parse_args()
    report=await run(args.live, [args.provider] if args.provider else None)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('cases','rates')},indent=2))
    if args.live and not report['all_live_checks_passed']:
        raise SystemExit(1)


if __name__=='__main__':
    asyncio.run(main())
