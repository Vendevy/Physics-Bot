# StudyBot Extraction System — Technical Brief for Claude Opus

## Project Overview

**StudyBot** is an A-Level Physics (OCR H556) study system that extracts questions and markschemes from past papers, tags them to topics, and uses SM-2 spaced repetition for daily study sessions.

**Current status:** Spec extracted (491 topics). Building question bank from 27 past papers. Only ~4 papers successfully processed.

**Working directory:** `/home/nadab/Desktop/Phys/Physics Bot`

## Architecture

```
studybot/extract_questions.py  → Two-pass extraction (QP → questions, MS → markschemes)
studybot/extract_cli.py        → OpenCode CLI backend (current working backend)
studybot/gemini.py            → Gemini backend (quota exhausted)
studybot/extract_claude.py     → Claude Haiku backend (token limits, unused)
studybot/__main__.py           → CLI entry point with build-questions command
```

## Current Backend Configuration (.env)

```ini
EXTRACT_BACKEND=cli
EXTRACT_MODEL=opencode-go/minimax-m2.5
```

**MiniMax M2.5 via OpenCode CLI is the ONLY working backend.**

## Failure Modes Encountered

### Failure Mode 1: Model Writes JSON to File Instead of Returning Inline
**Trigger:** Large markscheme extractions (80+ entries, ~15KB JSON)
**Symptom:** Model returns plain text summary like:
```
Extracted 83 markscheme entries:
- Section A: Questions 1-15 (MCQ answers D, B, A, ...)
- Section B: Questions 16(a)-16(d), ...

The JSON file has been saved to `/home/nadab/Desktop/Phys/Physics Bot/markscheme.json`.
```
**Papers affected:** Paper1-June 2022 (confirmed), likely others with large MS

### Failure Mode 2: Model Returns Malformed JSON
**Trigger:** Large markscheme extractions
**Symptom:** `json.decoder.JSONDecodeError: Expecting ',' delimiter: line 1 column 5925`
**Papers affected:** Paper1-June 2019 (confirmed)

### Failure Mode 3: Infinite Tool-Calling Loop (Other Models)
**Trigger:** Kimi K2.6, DeepSeek V4 Pro via OpenCode CLI
**Symptom:** Model sees available tools (bash, glob, read, write, etc.) and enters infinite loop calling them instead of returning text. Times out after 300s.
**Root cause:** OpenCode CLI always runs in agent mode with tools exposed. MiniMax M2.5 ignores tools; other models use them.
**Status:** Confirmed unfixable via `--pure`, prompt instructions, or `--tools ""`. These models cannot be used via OpenCode CLI for extraction.

### Failure Mode 4: Gemini API Quota Exhausted
**Status:** Free tier quota (0 requests/day) reached. Key: `AIzaSyA8pF6ynoUSiNADJj4_UY9LdepMkf68x-c`

## Fixes Already Applied

### 1. Fuzzy Markscheme Matching (`extract_questions.py`)
Added `_normalize_qnum()` and `_fuzzy_ms_lookup()` to handle granularity mismatches:
- `21(a)(ii)(1)` vs `21(a)(ii)1` → normalized match
- Parent/child aggregation for coarse/fine mismatches

### 2. File Fallback (`extract_cli.py`)
When no JSON in response, checks for `markscheme.json` or `questions.json` files written by model.

### 3. JSON Repair (`extract_cli.py`)
Installed `json-repair` library. Attempts to repair malformed JSON before failing.

### 4. Per-Paper Error Handling (`__main__.py`)
Build now continues on individual paper failures instead of crashing entire run.

### 5. Stronger Prompt Instructions
Added "CRITICAL: Return ONLY the raw JSON object inline. Do NOT save to files..."

## Current Code State

### `extract_cli.py` (lines 82-137)
```python
def call_json(...):
    # 1. Build prompt with schema + strict instructions
    # 2. Run opencode CLI with --format json
    # 3. Parse NDJSON events, collect text parts
    # 4. Try to extract and parse JSON from text
    # 5. If parse fails, try json_repair.repair_json()
    # 6. If still fails, check for fallback files (markscheme.json, questions.json)
    # 7. If all fails, raise ValueError
```

**Problem:** Steps 4-6 don't reliably handle the two main failure modes. The model behavior is non-deterministic.

### `extract_questions.py`
Two-pass extraction:
- **Pass 1 (QP):** Extracts questions + topic tags → usually works fine
- **Pass 2 (MS):** Extracts markschemes → frequently fails on large markschemes

**Prompts:**
- `QP_SYSTEM`: Standard question extraction instructions
- `MS_SYSTEM`: Markscheme extraction with MCQ and structured question rules

## Root Cause Analysis

The fundamental issue: **OpenCode CLI runs models in agent mode with tools exposed.**

When given a large extraction task (especially markschemes with 80+ entries), MiniMax M2.5:
1. Sometimes returns valid JSON inline ✅
2. Sometimes decides the output is too large and writes to a file ❌
3. Sometimes generates malformed JSON (truncated, missing commas) ❌

The `--format json` flag only affects how opencode streams output (NDJSON events), not how the model formats its text content.

## Proposed Solutions (for Claude Opus)

### Option A: Split Markscheme Extraction into Chunks
Instead of asking for ALL markschemes in one call, split the MS PDF text into sections:
- Section A (MCQs 1-15)
- Section B part 1 (Q16-Q19)
- Section B part 2 (Q20-Q23)

Run multiple `call_json()` calls and merge results. This keeps each prompt smaller and more reliable.

### Option B: Use Native PDF + Direct API
Bypass OpenCode CLI entirely. Use a direct HTTP API call to MiniMax (or another model) with:
- No tool exposure
- Direct PDF upload or text input
- Structured output via response_schema or constrained decoding

This requires finding MiniMax's API endpoint or using the `api` backend with a compatible endpoint.

### Option C: Post-Process and Retry Pipeline
1. Run extraction
2. If JSON parse fails, use regex/heuristics to extract data from whatever the model returned
3. If still fails, retry with a simpler prompt (e.g., "Extract only Q16-Q19 markschemes")
4. Log all failures for manual review

### Option D: Switch to Gemini with New API Key
Get a fresh Gemini API key (free tier: 1500 requests/day, 1M tokens/min). Gemini backend (`gemini.py`) is already implemented and tested — it just needs a valid key. Native PDF support, no truncation, no tool loops.

## File Locations

```
/home/nadab/Desktop/Phys/Physics Bot/
├── studybot/
│   ├── extract_cli.py          # OpenCode CLI backend
│   ├── extract_questions.py    # Two-pass extraction logic
│   ├── __main__.py             # CLI entry point
│   └── gemini.py               # Gemini backend (quota exhausted)
├── .env                        # API keys and backend config
├── data/studybot.db            # SQLite database
└── Physics Past Papers/
    ├── Physics Question Paper/
    │   ├── Paper 1/            # 9 papers (June 2017-2024, Nov 2020-2021, Specimen)
    │   ├── Paper 2/            # 9 papers
    │   └── Paper 3/            # 9 papers
    └── Physics Markscheme/
        ├── Paper1/             # 9 papers (note: no space)
        ├── Paper 2/            # 9 papers
        └── Paper 3/            # 9 papers
```

## Database State

```sql
Subjects: 1 (A-Level Physics OCR H556, id=1)
Topics: 491
Papers: 4 (June 2017, Paper1-June 2017, Paper1-June 2018, Paper1-June 2019)
Questions: ~211 total
```

## Reproduction

```bash
cd "/home/nadab/Desktop/Phys/Physics Bot"
.venv/bin/python -m studybot build-questions physics --limit 1
```

This will process Paper1-June 2017. To test a problematic paper:
```bash
# Edit __main__.py to filter for specific papers, or run directly:
.venv/bin/python -c "
from studybot.extract_questions import extract_paper
from studybot.db import connect
# ... setup subject_id, spec_file_id, summary
extract_paper(1, 'Paper1-June 2022', 
  Path('Physics Past Papers/Physics Question Paper/Paper 1/June 2022 QP.pdf'),
  Path('Physics Past Papers/Physics Markscheme/Paper1/June 2022 MS.pdf'),
  spec_file_id, summary)
"
```

## Key Questions for Opus


2. **Should we implement chunked extraction** (split MS into sections) to avoid large-output failures?

3. **Should we add a retry-with-simpler-prompt mechanism** when extraction fails?

4. **Is there a better backend option** (e.g., direct MiniMax API, or another model that works reliably via OpenCode CLI)?

