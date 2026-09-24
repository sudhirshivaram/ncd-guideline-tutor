"""LLM generation adapters for OpenAI, Google Gemini, and Anthropic Claude."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from app.core.schemas import ChatMessage, ProviderName


SYSTEM_PROMPT = """You are NCD Guideline Tutor, a clinical decision-support assistant for primary health care workers.

You answer ONLY from the retrieved World Health Organization (WHO) NCD guideline excerpts provided below.
You are NOT a substitute for clinical judgment and must not diagnose, prescribe for, or treat a specific named patient.

Rules:
- Ground every clinical fact in the sources. Cite them inline as [1], [2], matching the source list.
- If the retrieved sources do not contain the answer, say so clearly. Do not invent thresholds, doses, or protocols.
- Prefer precise numbers, eligibility criteria, and protocol steps when they appear in the sources.
- Preserve recommendation strength and qualifiers exactly: do not turn "suggests" into "recommends", "should" into "must", or "may" into a requirement. Keep conditional recommendations and their conditions explicit.
- Use plain Unicode mathematical symbols (≥, ≤, ±) in prose, not LaTeX commands or dollar-delimited math. For example, write "≥20/10 mmHg above target".
- Keep answers structured and concise.
- End with a one-line reminder that this is WHO guideline information, not individualized medical advice.
"""


def format_context(contexts: list[dict[str, Any]]) -> str:
    blocks = []
    for i, chunk in enumerate(contexts, start=1):
        header = (
            f"[{i}] {chunk['short_title']} ({chunk['year']}) | "
            f"p.{chunk['page']} | {chunk.get('section', '')} | {chunk.get('ncd_types', '')}"
        )
        blocks.append(f"{header}\n{chunk['text']}")
    return "\n\n".join(blocks)


def build_messages(
    question: str,
    contexts: list[dict[str, Any]],
    history: list[ChatMessage],
) -> list[dict[str, str]]:
    context_block = format_context(contexts) if contexts else "No guideline excerpts were retrieved."
    user_content = (
        f"Retrieved WHO sources:\n\n{context_block}\n\n"
        f"Question: {question}\n\n"
        "Answer using only the retrieved sources and cite them as [n]."
    )
    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for item in history[-8:]:
        messages.append({"role": item.role, "content": item.content})
    messages.append({"role": "user", "content": user_content})
    return messages


async def stream_llm(
    provider: ProviderName,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    usage: dict[str, int] | None = None,
    max_output_tokens: int = 1200,
) -> AsyncIterator[str]:
    if usage is not None:
        usage.clear()
    if not 1 <= max_output_tokens <= 1200:
        raise ValueError("Output limit must be between 1 and 1200 tokens.")
    if not api_key.strip():
        raise ValueError("An API key is required. Add it in Settings; keys are never stored on the server.")
    if provider == "openai":
        async for token in _stream_openai(api_key, model, messages, temperature, usage, max_output_tokens):
            yield token
    elif provider == "gemini":
        async for token in _stream_gemini(api_key, model, messages, temperature, usage, max_output_tokens):
            yield token
    elif provider == "anthropic":
        async for token in _stream_anthropic(api_key, model, messages, temperature, usage, max_output_tokens):
            yield token
    else:
        raise ValueError(f"Unsupported provider: {provider}")


async def _stream_openai(
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    usage: dict[str, int] | None = None,
    max_output_tokens: int = 1200,
) -> AsyncIterator[str]:
    from openai import AsyncOpenAI

    async with AsyncOpenAI(api_key=api_key, timeout=60.0, max_retries=0) as client:
        stream = await client.chat.completions.create(
            model=model, messages=messages, temperature=temperature,
            stream=True, stream_options={"include_usage": True},
            max_completion_tokens=max_output_tokens,
        )
        async with stream:
            async for event in stream:
                if usage is not None and event.usage is not None:
                    usage.update(input_tokens=event.usage.prompt_tokens, output_tokens=event.usage.completion_tokens)
                delta = event.choices[0].delta.content if event.choices else None
                if delta:
                    yield delta


async def _stream_anthropic(
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    usage: dict[str, int] | None = None,
    max_output_tokens: int = 1200,
) -> AsyncIterator[str]:
    from anthropic import AsyncAnthropic

    system = ""
    converted: list[dict[str, Any]] = []
    for message in messages:
        if message["role"] == "system":
            system = message["content"]
            continue
        converted.append({"role": message["role"], "content": message["content"]})

    async with AsyncAnthropic(api_key=api_key, timeout=60.0, max_retries=0) as client:
        async with client.messages.stream(
            model=model, system=system, messages=converted,
            max_tokens=max_output_tokens, extra_body={"temperature": temperature},
        ) as stream:
            async for text in stream.text_stream:
                if text:
                    yield text
            final = await stream.get_final_message()
            if usage is not None:
                usage.update(input_tokens=final.usage.input_tokens, output_tokens=final.usage.output_tokens)


async def _stream_gemini(
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    usage: dict[str, int] | None = None,
    max_output_tokens: int = 1200,
) -> AsyncIterator[str]:
    from google import genai
    from google.genai import types

    system = "\n".join(m["content"] for m in messages if m["role"] == "system")
    contents = [types.Content(
        role="model" if m["role"] == "assistant" else "user",
        parts=[types.Part.from_text(text=m["content"])],
    ) for m in messages if m["role"] != "system"]
    async with genai.Client(api_key=api_key, http_options=types.HttpOptions(
        timeout=60000, retry_options=types.HttpRetryOptions(attempts=1),
    )).aio as client:
        stream = await client.models.generate_content_stream(
            model=model, contents=contents,
            config=types.GenerateContentConfig(system_instruction=system or None,
                temperature=temperature, max_output_tokens=max_output_tokens),
        )
        async for chunk in stream:
            if usage is not None and chunk.usage_metadata is not None:
                meta = chunk.usage_metadata
                if meta.prompt_token_count is not None and meta.total_token_count is not None:
                    # Includes thinking tokens, which are billed as output.
                    usage.update(input_tokens=meta.prompt_token_count,
                                 output_tokens=max(0, meta.total_token_count - meta.prompt_token_count))
            if chunk.text:
                yield chunk.text
