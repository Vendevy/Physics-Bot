"""Generic OpenAI-compatible client for extraction.

Uses pdftotext to convert PDFs to text, then sends text to any OpenAI-compatible API.
This works with OpenCode GO, Together, Fireworks, or any provider.

Why this approach:
- pdftotext is already installed and produces clean text
- Any model that accepts text works (no PDF upload needed)
- Much cheaper than Claude's Files API
- Structured JSON via response_format

Environment variables:
  EXTRACT_API_KEY      — API key for the provider
  EXTRACT_BASE_URL     — Base URL (default: OpenCode GO or OpenAI)
  EXTRACT_MODEL        — Model name (default: minimax-m2.5)
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

EXTRACT_API_KEY = os.getenv("EXTRACT_API_KEY", "")
EXTRACT_BASE_URL = os.getenv("EXTRACT_BASE_URL", "")
EXTRACT_MODEL = os.getenv("EXTRACT_MODEL", "minimax-m2.5")

if EXTRACT_API_KEY:
    _client = OpenAI(api_key=EXTRACT_API_KEY, base_url=EXTRACT_BASE_URL or None)
else:
    _client = None


def _pdf_to_text(path: Path) -> str:
    """Convert a PDF to plain text using pdftotext."""
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


def _build_messages(
    system: str,
    user_text: str,
    files: list[Path],
) -> list[dict]:
    """Build OpenAI messages with PDF text inlined."""
    file_texts = []
    for f in files:
        text = _pdf_to_text(f)
        # Truncate extremely long texts to avoid hitting context limits
        # Most models handle 128k-200k context; we'll be well under that
        if len(text) > 150_000:
            text = text[:150_000] + "\n\n[...truncated...]"
        file_texts.append(f"--- {f.name} ---\n{text}")

    full_user = user_text + "\n\n" + "\n\n".join(file_texts)
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": full_user},
    ]


def call_json(
    *,
    system: str,
    user_text: str,
    files: list[Path],
    schema: dict,
    max_tokens: int = 16000,
) -> Any:
    """Call an OpenAI-compatible API with structured JSON output."""
    if _client is None:
        raise RuntimeError(
            "EXTRACT_API_KEY not set. Add it to your .env file:\n"
            "  EXTRACT_API_KEY=your_key_here\n"
            "  EXTRACT_BASE_URL=https://api.opencode.gg/v1  # or your provider\n"
            "  EXTRACT_MODEL=minimax-m2.5  # or your chosen model"
        )

    messages = _build_messages(system, user_text, files)

    # Convert our schema to OpenAI's json_schema format
    openai_schema = {
        "name": "extraction_result",
        "schema": schema,
        "strict": True,
    }

    for attempt in range(1, 4):
        try:
            response = _client.chat.completions.create(
                model=EXTRACT_MODEL,
                messages=messages,
                response_format={"type": "json_schema", "json_schema": openai_schema},
                max_tokens=max_tokens,
                temperature=0.0,  # Deterministic for extraction
            )
            text = response.choices[0].message.content
            if not text:
                raise ValueError("Empty response")
            return json.loads(text)
        except Exception as e:
            if attempt == 3:
                raise RuntimeError(f"Extraction failed after 3 attempts: {e}")
            import time
            wait = 2 ** attempt
            print(f"    Generation attempt {attempt} failed ({e}); retrying in {wait}s...")
            time.sleep(wait)


def call_text(
    *,
    system: str,
    user_text: str,
    files: list[Path] | None = None,
    max_tokens: int = 8000,
) -> str:
    """Call an OpenAI-compatible API with free-text output."""
    if _client is None:
        raise RuntimeError("EXTRACT_API_KEY not set. See call_json docs.")

    messages = _build_messages(system, user_text, files or [])

    for attempt in range(1, 4):
        try:
            response = _client.chat.completions.create(
                model=EXTRACT_MODEL,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.0,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            if attempt == 3:
                raise RuntimeError(f"Extraction failed after 3 attempts: {e}")
            import time
            wait = 2 ** attempt
            print(f"    Generation attempt {attempt} failed ({e}); retrying in {wait}s...")
            time.sleep(wait)
