"""Anthropic API extraction backend with native PDF input + prompt caching.

Bypasses OpenCode CLI entirely. No tool-call loops, no file-fallback hacks,
no JSON repair. Uses native PDF input (preserves table structure for
markschemes) and tool-use to enforce the JSON schema.

Model is configurable via EXTRACT_MODEL_ANTHROPIC; defaults to claude-haiku-4-5
(~$1/M input — cheapest tier with vision + 64K output, plenty for PDF
extraction). Override to claude-sonnet-4-6 or claude-opus-4-7 if a paper's
markscheme is too complex for Haiku.

Prompt caching: system prompt and stable user_text (spec topic codes for QP
extraction) are cached so the 27-paper batch reuses ~13KB of context per call
at ~10% of base price.
"""
from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any

import anthropic
from dotenv import load_dotenv

load_dotenv()

_client = anthropic.Anthropic(max_retries=2, timeout=600.0)
MODEL = os.getenv("EXTRACT_MODEL_ANTHROPIC", "claude-haiku-4-5")
_MAX_TOKENS = 32000


def _pdf_to_base64(path: Path) -> str:
    return base64.standard_b64encode(Path(path).resolve().read_bytes()).decode("ascii")


def call_json(
    *,
    system: str,
    user_text: str,
    files: list[Path],
    schema: dict,
    max_tokens: int = _MAX_TOKENS,
) -> Any:
    """Extract structured JSON from PDFs via Claude tool-use."""
    tool = {
        "name": "extraction_result",
        "description": "Return the extracted data in the required format.",
        "input_schema": schema,
    }

    user_content: list[dict] = [
        {
            "type": "text",
            "text": user_text,
            "cache_control": {"type": "ephemeral"},
        },
    ]
    for f in files:
        user_content.append({
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": _pdf_to_base64(f),
            },
        })

    system_blocks = [{
        "type": "text",
        "text": system,
        "cache_control": {"type": "ephemeral"},
    }]

    with _client.messages.stream(
        model=MODEL,
        max_tokens=max_tokens,
        system=system_blocks,
        tools=[tool],
        tool_choice={"type": "tool", "name": "extraction_result"},
        messages=[{"role": "user", "content": user_content}],
    ) as stream:
        response = stream.get_final_message()

    if response.stop_reason == "max_tokens":
        raise RuntimeError(
            f"Hit max_tokens={max_tokens} on {[f.name for f in files]} — "
            "increase max_tokens or split input"
        )

    for block in response.content:
        if block.type == "tool_use" and block.name == "extraction_result":
            return block.input

    raise ValueError(
        f"No tool_use block in response: stop_reason={response.stop_reason}"
    )


def call_text(
    *,
    system: str,
    user_text: str,
    files: list[Path] | None = None,
    max_tokens: int = 8000,
) -> str:
    """Free-text output (used for spec extraction)."""
    user_content: list[dict] = [{"type": "text", "text": user_text}]
    for f in (files or []):
        user_content.append({
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": _pdf_to_base64(f),
            },
        })

    response = _client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_content}],
    )

    for block in response.content:
        if block.type == "text":
            return block.text
    return ""
