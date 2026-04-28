"""OpenCode CLI wrapper for extraction.

Uses the local `opencode` CLI tool via stdin (avoids argument length limits).
PDFs are converted to text via pdftotext before sending.
"""
from __future__ import annotations

import json
import json_repair
import os
import subprocess
from pathlib import Path
from typing import Any

OPENCODE_BIN = os.path.expanduser("~/.opencode/bin/opencode")
DEFAULT_MODEL = os.getenv("EXTRACT_MODEL", "opencode-go/minimax-m2.5")


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


def _run_cli(
    model: str,
    prompt: str,
    files: list[Path],
) -> str:
    """Run opencode CLI via stdin and return the final text response."""
    # Convert PDFs to text and build the full prompt
    file_texts = []
    for f in files:
        text = _pdf_to_text(f)
        if len(text) > 120_000:
            text = text[:120_000] + "\n\n[...truncated...]"
        file_texts.append(f"--- {f.name} ---\n{text}")

    full_prompt = prompt + "\n\n" + "\n\n".join(file_texts)

    cmd = [
        OPENCODE_BIN,
        "run",
        "--model", model,
        "--format", "json",
        "--dangerously-skip-permissions",
    ]

    result = subprocess.run(
        cmd,
        input=full_prompt,
        capture_output=True,
        text=True,
        timeout=300,
    )

    # Parse JSON events
    text_parts = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
            if event.get("type") == "text":
                text = event.get("part", {}).get("text", "")
                if text:
                    text_parts.append(text)
        except json.JSONDecodeError:
            continue

    return "".join(text_parts)


def call_json(
    *,
    system: str,
    user_text: str,
    files: list[Path],
    schema: dict,
    model: str = DEFAULT_MODEL,
) -> Any:
    """Call OpenCode CLI with structured JSON output."""
    schema_json = json.dumps(schema, indent=2)
    prompt = (
        f"{system}\n\n"
        f"{user_text}\n\n"
        f"You must respond with valid JSON matching this schema exactly:\n"
        f"{schema_json}\n\n"
        f"CRITICAL: Return ONLY the raw JSON object inline. "
        f"Do NOT save to files. Do NOT use markdown code blocks. "
        f"Do NOT add explanations before or after the JSON."
    )

    text = _run_cli(model, prompt, files)

    # Try 1: direct JSON parse from response text
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        raw = text[start:end+1]
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Try 2: repair common JSON syntax errors
            repaired = json_repair.repair_json(raw, return_objects=True)
            if repaired:
                return repaired

    # Try 3: model may have written JSON to a file instead of returning it
    fallback_paths = [Path("markscheme.json"), Path("questions.json")]
    for fp in fallback_paths:
        if fp.exists():
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    raw = f.read()
                data = json.loads(raw)
                fp.unlink()  # clean up so it isn't reused accidentally
                return data
            except (json.JSONDecodeError, OSError):
                # Try repair on file content too
                try:
                    repaired = json_repair.repair_json(raw, return_objects=True)
                    if repaired:
                        fp.unlink()
                        return repaired
                except Exception:
                    continue

    raise ValueError(f"No valid JSON found in response: {text[:500]}")


def call_text(
    *,
    system: str,
    user_text: str,
    files: list[Path] | None = None,
    model: str = DEFAULT_MODEL,
) -> str:
    """Call OpenCode CLI with free-text output."""
    prompt = f"{system}\n\n{user_text}"
    return _run_cli(model, prompt, files or [])
