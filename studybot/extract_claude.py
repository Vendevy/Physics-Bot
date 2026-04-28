"""Claude Haiku extraction backend (via Anthropic SDK).

Uses claude-haiku-4-5 with tool use to enforce exact JSON schema output.
Haiku's output cap is 8,192 tokens, so long documents are chunked: the text
is split at a clean question boundary near the midpoint and the model runs
twice, then the two result arrays are merged.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

import anthropic
from dotenv import load_dotenv

load_dotenv()

_client = anthropic.Anthropic(max_retries=2, timeout=120.0)
MODEL = "claude-haiku-4-5-20251001"
# Haiku hard cap is 8,192 — stay well under to avoid truncated tool calls.
_MAX_TOKENS = 7000
# Split text into chunks when it exceeds this many characters.
_CHUNK_THRESHOLD = 8_000


def _pdf_to_text(path: Path) -> str:
    path = Path(path).resolve()
    result = subprocess.run(
        ["pdftotext", str(path), "-"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pdftotext failed for {path}: {result.stderr}")
    return result.stdout


def _split_at_question_boundary(text: str) -> tuple[str, str]:
    """Split near the midpoint at the start of a top-level question line."""
    mid = len(text) // 2
    # Look for a line that starts a new top-level question: a number (possibly
    # preceded by whitespace) at the start of a line, e.g. "\n21 " or "\n21\n"
    pattern = re.compile(r"\n\s*(\d{1,2})\s*[\n(]")
    best = None
    for m in pattern.finditer(text):
        if m.start() >= mid // 2:  # don't split too early
            best = m
            if m.start() >= mid:
                break
    if best:
        split = best.start() + 1  # keep the \n at the end of chunk 1
        return text[:split], text[split:]
    return text[:mid], text[mid:]


def _call_once(system: str, user_text: str, schema: dict) -> Any:
    tool = {
        "name": "extraction_result",
        "description": "Return the extracted data in the required format.",
        "input_schema": schema,
    }
    response = _client.messages.create(
        model=MODEL,
        max_tokens=_MAX_TOKENS,
        temperature=0,
        system=system,
        tools=[tool],
        tool_choice={"type": "tool", "name": "extraction_result"},
        messages=[{"role": "user", "content": user_text}],
    )
    if response.stop_reason == "max_tokens":
        raise RuntimeError("Hit max_tokens — chunk this input further")
    for block in response.content:
        if block.type == "tool_use" and block.name == "extraction_result":
            return block.input
    raise ValueError(f"No tool_use block in response: {response.content}")


def _merge_results(a: Any, b: Any) -> Any:
    """Merge two dicts that each contain a single list value."""
    if not isinstance(a, dict) or not isinstance(b, dict):
        return a
    merged = {}
    for key in a:
        va, vb = a.get(key, []), b.get(key, [])
        if isinstance(va, list) and isinstance(vb, list):
            # Deduplicate by first field of each item
            seen = {list(item.values())[0] for item in va if item}
            merged[key] = va + [item for item in vb if list(item.values())[0] not in seen]
        else:
            merged[key] = va
    return merged


def call_json(
    *,
    system: str,
    user_text: str,
    files: list[Path],
    schema: dict,
    max_tokens: int = _MAX_TOKENS,
) -> Any:
    """Call Claude Haiku with structured JSON output, chunking long documents."""
    file_texts = []
    for f in files:
        text = _pdf_to_text(f)
        if len(text) > 120_000:
            text = text[:120_000] + "\n\n[...truncated...]"
        file_texts.append((f.name, text))

    combined = "\n\n".join(f"--- {name} ---\n{text}" for name, text in file_texts)

    if len(combined) <= _CHUNK_THRESHOLD:
        return _call_once(system, user_text + "\n\n" + combined, schema)

    # Split at a clean question boundary and run two passes
    chunk_a, chunk_b = _split_at_question_boundary(combined)
    result_a = _call_once(system, user_text + "\n\n" + chunk_a, schema)
    result_b = _call_once(system, user_text + "\n\n" + chunk_b, schema)
    return _merge_results(result_a, result_b)


def call_text(
    *,
    system: str,
    user_text: str,
    files: list[Path] | None = None,
    max_tokens: int = 8000,
) -> str:
    """Call Claude Haiku with free-text output."""
    file_texts = []
    for f in (files or []):
        text = _pdf_to_text(f)
        if len(text) > 120_000:
            text = text[:120_000] + "\n\n[...truncated...]"
        file_texts.append(f"--- {f.name} ---\n{text}")

    full_user = user_text + "\n\n" + "\n\n".join(file_texts)

    response = _client.messages.create(
        model=MODEL,
        max_tokens=min(max_tokens, _MAX_TOKENS),
        system=system,
        messages=[{"role": "user", "content": full_user}],
    )

    return response.content[0].text or ""
