"""Claude CLI wrapper for question generation.

Uses the local `claude` CLI (-p/--print mode) so question generation can run
through the Claude Code CLI rather than the Anthropic SDK directly.
"""
from __future__ import annotations

import json
import json_repair
import os
import subprocess
from typing import Any

CLAUDE_BIN = os.path.expanduser("~/.local/bin/claude")


_JSON_SYSTEM_PREFIX = (
    "CRITICAL OUTPUT FORMAT: Your response must be a single raw JSON object. "
    "Do NOT include any text, explanation, markdown, or code fences before or after it. "
    "Output ONLY the JSON object — nothing else.\n\n"
)


def _run_claude(
    system: str,
    user_text: str,
    model: str,
    json_mode: bool = False,
) -> str:
    """Run claude CLI in print mode and return the response text."""
    effective_system = (_JSON_SYSTEM_PREFIX + system) if json_mode else system
    output_fmt = "json" if json_mode else "text"
    cmd = [
        CLAUDE_BIN,
        "-p",
        "--output-format", output_fmt,
        "--model", model,
        "--system-prompt", effective_system,
        "--tools", "",
        "--no-session-persistence",
    ]

    # Strip ANTHROPIC_API_KEY so the CLI authenticates via OAuth (subscription)
    # rather than the API key. Without this it inherits the key from load_dotenv()
    # and bills API credits instead of the subscription.
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)

    print(f"  [DEBUG] claude-cli: model={model} json_mode={json_mode} prompt_len={len(user_text)}")
    result = subprocess.run(
        cmd,
        input=user_text,
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
    )
    print(f"  [DEBUG] claude-cli: exit={result.returncode} stdout_len={len(result.stdout)} stderr_len={len(result.stderr)}")
    if result.stderr:
        print(f"  [DEBUG] claude-cli stderr: {result.stderr[:300]}")

    if result.returncode != 0:
        raise RuntimeError(
            f"claude CLI failed (exit {result.returncode}): {result.stderr[:500]}"
        )

    if not json_mode:
        return result.stdout

    try:
        envelope = json.loads(result.stdout)
        if envelope.get("is_error"):
            raise RuntimeError(f"claude CLI error: {envelope.get('result', result.stdout[:300])}")
        return envelope.get("result", "") or result.stdout
    except json.JSONDecodeError:
        return result.stdout


def call_json(
    *,
    system: str,
    user_text: str,
    schema: dict,
    model: str,
    max_tokens: int = 16000,
) -> Any:
    """Call Claude CLI with structured JSON output."""
    schema_json = json.dumps(schema, indent=2)
    augmented_user = (
        user_text
        + "\n\nYou must respond with valid JSON matching this schema exactly:\n"
        + schema_json
        + "\n\nCRITICAL: Return ONLY the raw JSON object. "
        "Do NOT use markdown code blocks. "
        "Do NOT add explanations before or after the JSON."
    )

    text = _run_claude(system, augmented_user, model, json_mode=True)

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        raw = text[start : end + 1]
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            repaired = json_repair.repair_json(raw, return_objects=True)
            if repaired:
                return repaired

    raise ValueError(f"No valid JSON in Claude CLI response: {text[:500]}")


def call_text(
    *,
    system: str,
    user_text: str,
    model: str,
) -> str:
    """Call Claude CLI with free-text output."""
    return _run_claude(system, user_text, model, json_mode=False)
