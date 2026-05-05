"""OpenAI-compatible client wrapper for question generation and grading.

Supports two backends:
- DEEPSEEK: official DeepSeek API (https://api.deepseek.com/v1)
- OpenCode GO: fallback for other models (uses EXTRACT_API_KEY + EXTRACT_BASE_URL)

Mirrors the llm.py interface: call_json, call_text, stream_text.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any

from openai import OpenAI

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

OPENCODE_API_KEY = os.environ.get("EXTRACT_API_KEY", "")
OPENCODE_BASE_URL = os.environ.get("EXTRACT_BASE_URL", "https://api.opencode.gg/v1")


def _get_client(model: str) -> OpenAI:
    """Route to the right OpenAI-compatible client."""
    if DEEPSEEK_API_KEY and "deepseek" in model.lower() and "opencode" not in model.lower():
        return OpenAI(base_url=DEEPSEEK_BASE_URL, api_key=DEEPSEEK_API_KEY, max_retries=2, timeout=600.0)
    return OpenAI(base_url=OPENCODE_BASE_URL, api_key=OPENCODE_API_KEY, max_retries=2, timeout=600.0)


def _call_with_rate_limit_retry(fn, *args, **kwargs):
    for attempt in range(6):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            if "429" in str(e) or "rate" in str(e).lower():
                if attempt == 5:
                    raise
                wait = 60 * (attempt + 1)
                print(f"  Rate limited; waiting {wait}s before retry {attempt + 1}/5...")
                time.sleep(wait)
            else:
                raise


def call_json_openai(
    *,
    system: str,
    user_text: str,
    schema: dict,
    model: str,
    max_tokens: int = 16000,
) -> Any:
    is_deepseek = "deepseek" in model.lower()
    extra_msg = ""
    if is_deepseek:
        extra_msg = "\n\nYou must respond with a single JSON object matching this schema exactly:\n" + json.dumps(schema)
    response = _call_with_rate_limit_retry(
        _get_client(model).chat.completions.create,
        model=model,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_text + extra_msg},
        ],
        response_format={"type": "json_object"} if is_deepseek else {
            "type": "json_schema",
            "json_schema": {"name": "response", "schema": schema, "strict": True},
        },
    )
    text = response.choices[0].message.content
    return json.loads(text)


def call_text_openai(
    *,
    system: str,
    user_text: str,
    model: str,
    max_tokens: int = 4000,
) -> str:
    response = _call_with_rate_limit_retry(
        _get_client(model).chat.completions.create,
        model=model,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_text},
        ],
    )
    return response.choices[0].message.content or ""


def stream_text_openai(
    *,
    system: str,
    user_text: str,
    model: str,
    max_tokens: int = 2000,
):
    stream = _call_with_rate_limit_retry(
        _get_client(model).chat.completions.create,
        model=model,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_text},
        ],
        stream=True,
    )
    full = ""
    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            full += delta
            yield delta
    yield {"__final__": full}
