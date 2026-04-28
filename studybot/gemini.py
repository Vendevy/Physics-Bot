"""Gemini client wrapper for extraction tasks (spec + past papers).

Why Gemini for extraction:
- Native PDF support (reads PDFs directly, no conversion)
- 1M token context (fits full QP + MS + spec)
- ~100x cheaper than Claude for the same task
- No rate limit headaches

Model: gemini-2.0-flash (falls back to gemini-1.5-flash)
Uses the modern google-genai SDK (not the deprecated generativeai package).
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

if not GEMINI_API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY not set. Get a free key at https://aistudio.google.com/app/apikey "
        "and add it to your .env file."
    )

_client = genai.Client(api_key=GEMINI_API_KEY)


def _clean_schema_for_gemini(schema: dict) -> dict:
    """Recursively remove unsupported JSON Schema keys for Gemini's response_schema."""
    if isinstance(schema, dict):
        cleaned = {}
        for k, v in schema.items():
            if k == "additionalProperties":
                continue
            cleaned[k] = _clean_schema_for_gemini(v)
        return cleaned
    elif isinstance(schema, list):
        return [_clean_schema_for_gemini(item) for item in schema]
    else:
        return schema


def _upload_pdf(path: Path) -> types.File:
    """Upload a PDF to Gemini's file API. Returns the File object."""
    path = Path(path).resolve()
    print(f"    Uploading to Gemini: {path.name}")
    for attempt in range(1, 4):
        try:
            file = _client.files.upload(file=str(path))
            # Wait for file to be processed
            while file.state.value == "PROCESSING":
                time.sleep(1)
                file = _client.files.get(name=file.name)
            if file.state.value != "ACTIVE":
                raise RuntimeError(f"File processing failed: {file.state.value}")
            return file
        except Exception as e:
            if attempt == 3:
                raise RuntimeError(f"Gemini upload failed after 3 attempts: {e}")
            wait = 2 ** attempt
            print(f"    Upload attempt {attempt} failed ({e}); retrying in {wait}s...")
            time.sleep(wait)


def call_json(
    *,
    system: str,
    user_text: str,
    files: list[Path],
    schema: dict,
    max_tokens: int = 32000,
) -> Any:
    """Call Gemini with structured JSON output. Uploads files, sends prompt, returns parsed JSON."""
    uploaded_files = [_upload_pdf(p) for p in files]

    parts = [user_text]
    parts.extend(uploaded_files)

    config = types.GenerateContentConfig(
        system_instruction=system,
        max_output_tokens=max_tokens,
        response_mime_type="application/json",
        response_schema=_clean_schema_for_gemini(schema),
    )

    for attempt in range(1, 4):
        try:
            response = _client.models.generate_content(
                model=GEMINI_MODEL,
                contents=parts,
                config=config,
            )
            text = response.text
            if not text:
                raise ValueError("Empty response from Gemini")
            return json.loads(text)
        except Exception as e:
            if attempt == 3:
                raise RuntimeError(f"Gemini generation failed after 3 attempts: {e}")
            wait = 2 ** attempt
            print(f"    Generation attempt {attempt} failed ({e}); retrying in {wait}s...")
            time.sleep(wait)


def call_text(
    *,
    system: str,
    user_text: str,
    files: list[Path] | None = None,
    max_tokens: int = 16000,
) -> str:
    """Call Gemini with free-text output."""
    uploaded_files = [_upload_pdf(p) for p in (files or [])]
    parts = [user_text]
    parts.extend(uploaded_files)

    config = types.GenerateContentConfig(
        system_instruction=system,
        max_output_tokens=max_tokens,
    )

    for attempt in range(1, 4):
        try:
            response = _client.models.generate_content(
                model=GEMINI_MODEL,
                contents=parts,
                config=config,
            )
            return response.text or ""
        except Exception as e:
            if attempt == 3:
                raise RuntimeError(f"Gemini generation failed after 3 attempts: {e}")
            wait = 2 ** attempt
            print(f"    Generation attempt {attempt} failed ({e}); retrying in {wait}s...")
            time.sleep(wait)
