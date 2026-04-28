"""Anthropic client wrapper.

- Files API caching: upload PDFs once, persist file_id in db.
- Prompt caching on stable context (specs, markschemes).
- Structured JSON via output_config.format.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import anthropic
from dotenv import load_dotenv

from .config import MODEL
from .db import connect

load_dotenv()
_client = anthropic.Anthropic(max_retries=2, timeout=600.0)


def _call_with_rate_limit_retry(fn, *args, **kwargs):
    """Call fn(*args, **kwargs), retrying on 429 rate limit errors."""
    for attempt in range(6):
        try:
            return fn(*args, **kwargs)
        except anthropic.RateLimitError as e:
            if attempt == 5:
                raise
            wait = 60 * (attempt + 1)
            print(f"  Rate limited; waiting {wait}s before retry {attempt + 1}/5...")
            time.sleep(wait)

FILES_BETA = "files-api-2025-04-14"


def upload_pdf(path: Path) -> str:
    """Upload a PDF (or return cached file_id). Returns the file_id."""
    import time
    path = Path(path).resolve()
    key = str(path)
    with connect() as conn:
        row = conn.execute("SELECT file_id FROM files_cache WHERE path = ?", (key,)).fetchone()
        if row:
            return row["file_id"]

        last_err = None
        for attempt in range(1, 6):
            try:
                with open(path, "rb") as f:
                    uploaded = _client.beta.files.upload(
                        file=(path.name, f, "application/pdf"),
                        betas=[FILES_BETA],
                    )
                break
            except (anthropic.APIConnectionError, anthropic.APIStatusError) as e:
                last_err = e
                wait = 2 ** attempt
                print(f"  upload attempt {attempt} failed ({type(e).__name__}); retrying in {wait}s...")
                time.sleep(wait)
        else:
            raise RuntimeError(f"upload failed after 5 attempts: {last_err}")

        conn.execute(
            "INSERT OR REPLACE INTO files_cache(path, file_id) VALUES(?, ?)",
            (key, uploaded.id),
        )
        conn.commit()
        return uploaded.id


def call_json(
    *,
    system: str,
    user_blocks: list[dict],
    schema: dict,
    cache_system: bool = True,
    model: str = MODEL,
    max_tokens: int = 16000,
) -> Any:
    """Call Claude with structured JSON output. Returns parsed dict/list."""
    system_param: list[dict] = [{"type": "text", "text": system}]
    if cache_system:
        system_param[0]["cache_control"] = {"type": "ephemeral"}

    response = _call_with_rate_limit_retry(
        _client.beta.messages.create,
        model=model,
        max_tokens=max_tokens,
        system=system_param,
        messages=[{"role": "user", "content": user_blocks}],
        output_config={"format": {"type": "json_schema", "schema": schema}},
        betas=[FILES_BETA],
    )

    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)


def stream_text(
    *,
    system: str,
    user_blocks: list[dict],
    cache_system: bool = True,
    model: str = MODEL,
    max_tokens: int = 2000,
):
    """Yield text deltas as they arrive. Final yield is the full text string.

    Generator protocol: each `yield` is either a str delta or, on completion,
    a dict {'__final__': str} containing the full assembled text.
    """
    system_param: list[dict] = [{"type": "text", "text": system}]
    if cache_system:
        system_param[0]["cache_control"] = {"type": "ephemeral"}

    with _client.beta.messages.stream(
        model=model,
        max_tokens=max_tokens,
        system=system_param,
        messages=[{"role": "user", "content": user_blocks}],
        betas=[FILES_BETA],
    ) as stream:
        for delta in stream.text_stream:
            yield delta
        final = stream.get_final_message()
    full = next(b.text for b in final.content if b.type == "text")
    yield {"__final__": full}


def call_text(
    *,
    system: str,
    user_blocks: list[dict],
    cache_system: bool = True,
    model: str = MODEL,
    max_tokens: int = 4000,
) -> str:
    system_param: list[dict] = [{"type": "text", "text": system}]
    if cache_system:
        system_param[0]["cache_control"] = {"type": "ephemeral"}

    response = _call_with_rate_limit_retry(
        _client.beta.messages.create,
        model=model,
        max_tokens=max_tokens,
        system=system_param,
        messages=[{"role": "user", "content": user_blocks}],
        betas=[FILES_BETA],
    )
    return next(b.text for b in response.content if b.type == "text")


def doc_block(file_id: str, *, cache: bool = False) -> dict:
    block: dict = {"type": "document", "source": {"type": "file", "file_id": file_id}}
    if cache:
        block["cache_control"] = {"type": "ephemeral"}
    return block


def text_block(text: str, *, cache: bool = False) -> dict:
    block: dict = {"type": "text", "text": text}
    if cache:
        block["cache_control"] = {"type": "ephemeral"}
    return block
