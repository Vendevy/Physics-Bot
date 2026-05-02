"""Extract individual questions from a question paper + markscheme, tagged to topics.

Two-pass approach for reliability:
  1. Extract questions + topic tags from QP + spec
  2. Extract markschemes from MS, matched by qnum

Backend is selected by EXTRACT_BACKEND in .env:
  anthropic         — Claude via Anthropic SDK with native PDF + caching (recommended)
  claude            — Legacy Claude Haiku backend using pdftotext (deprecated)
  gemini            — Gemini Flash via Google SDK (cheap, native PDF, 1M context)
  api               — OpenAI-compatible API (uses EXTRACT_API_KEY + EXTRACT_MODEL)
  cli               — OpenCode CLI (uses local opencode binary)
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from .db import connect

_BACKEND = os.getenv("EXTRACT_BACKEND", "anthropic").lower()
if _BACKEND == "anthropic":
    from . import extract_anthropic as _backend  # type: ignore[assignment]
elif _BACKEND == "gemini":
    from . import gemini as _backend  # type: ignore[assignment]
elif _BACKEND == "api":
    from . import extract_api as _backend  # type: ignore[assignment]
elif _BACKEND == "cli":
    from . import extract_cli as _backend  # type: ignore[assignment]
else:
    from . import extract_claude as _backend  # type: ignore[assignment]

QUESTIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "qnum": {"type": "string", "description": "e.g. '3(b)(ii)' or '7'"},
                    "text": {
                        "type": "string",
                        "description": "Full question text including any sub-stems and given values. Use Unicode for symbols and $...$ for inline math where LaTeX improves readability (e.g. $E = mc^2$, $v = u + at$).",
                    },
                    "marks": {"type": "integer"},
                    "topic_codes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of topic codes from the spec that this question assesses. Use 1-3 codes.",
                    },
                },
                "required": ["qnum", "text", "marks", "topic_codes"],
            },
        }
    },
    "required": ["questions"],
}

MARKSCHEME_SCHEMA = {
    "type": "object",
    "properties": {
        "markschemes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "qnum": {"type": "string", "description": "Question number, e.g. '3(b)(ii)'"},
                    "markscheme": {
                        "type": "string",
                        "description": "The FULL markscheme text for this question part. Include all marking points (M1, A1, B1), acceptable answers, and guidance. Copy verbatim from the markscheme PDF.",
                    },
                },
                "required": ["qnum", "markscheme"],
            },
        }
    },
    "required": ["markschemes"],
}

QP_SYSTEM = """You are extracting questions from an A-Level past paper and tagging them to the official spec topic codes.

You will be given two PDFs:
1. The official specification — use it to assign topic_codes.
2. The question paper.

Rules:
- Extract each numbered question (and sub-question) as a separate entry.
- For multi-part questions, EACH leaf part is a separate entry (e.g. 3(a), 3(b)(i), 3(b)(ii)).
- `marks` is the marks for that specific leaf part.
- `topic_codes` must be exact codes from the spec (e.g. "3.1.2"). Use 1-3 codes per question.
- Do NOT include multiple-choice option lists as separate questions; treat the MCQ as one item.
- Skip cover-page material, formulae lists, and assessment-objective tables.
- Output must be valid JSON.
"""

MS_SYSTEM = """You are extracting markscheme entries from an OCR A-Level Physics markscheme.

Section A (multiple choice, questions 1–30):
- These appear as a simple answer table/list (e.g. "1 B", "2 C", ...).
- Extract each as a separate entry with qnum "1", "2", etc. and markscheme = the correct letter.

Section B (structured questions):
- The markscheme uses tables with columns: Question, Answer, Marks, Guidance.
- Extract EACH row as a separate entry at whatever granularity the markscheme uses.
- qnum format: "16(a)", "17(b)(i)", "21(a)(ii)(1)" — always with parentheses for sub-parts.
- markscheme: For each question part, repeat the question part text above the marking points, so the reader can see which question each mark refers to. Format each part as:

  16(a) [question text or summary from the paper]
  M1: ...
  A1: ...
  
  16(b)(i) [question text or summary from the paper]
  B1: ...

CRITICAL:
- Extract EVERY entry — do not skip MCQs or structured questions.
- Include marking points (M1, A1, B1), acceptable answers, and examiner guidance.
- ALL mathematical expressions, equations, symbols, and variables must be in LaTeX: $...$ for inline math.
  Examples: $F=ma$, $\\Delta E = mc^2$, $v = u + at$, $3.2 \\times 10^{-19}\\,\\mathrm{C}$, $\\lambda = \\frac{d \\sin\\theta}{n}$.
  Never use bare Unicode approximations like ², ⁻¹, →, or × outside of LaTeX delimiters — always use proper LaTeX.
- Output must be valid JSON.
"""


def _normalize_qnum(q: str) -> str:
    """Strip spaces and parentheses so e.g. 21(a)(ii)(1) and 21(a)(ii)1 both become 21aii1."""
    return q.lower().replace("(", "").replace(")", "").replace(" ", "")


def _fuzzy_ms_lookup(qnum: str, markschemes: dict[str, str]) -> str:
    """Find a markscheme for qnum, tolerating granularity mismatches.

    Tries in order:
    1. Exact match.
    2. Parent match: strip sub-parts until a match is found (17(b)(i) → 17(b) → 17).
    3. Child aggregation: collect all MS entries whose qnum starts with this qnum prefix.
    4. Normalized match: ignore parenthesis/spacing differences (21(a)(ii)(1) ↔ 21(a)(ii)1).
    """
    if qnum in markschemes:
        return markschemes[qnum]

    # Parent match — walk up the hierarchy
    parts = qnum
    while "(" in parts:
        parts = parts[: parts.rfind("(")]
        if parts in markschemes:
            return markschemes[parts]

    # Child aggregation — MS is more granular than QP
    prefix = qnum + "("
    children = [v for k, v in markschemes.items() if k.startswith(prefix)]
    if children:
        return "\n\n".join(children)

    # Normalized match — tolerate parenthesis differences
    norm_qp = _normalize_qnum(qnum)
    matches = [v for k, v in markschemes.items() if _normalize_qnum(k) == norm_qp]
    if matches:
        return "\n\n".join(matches)

    return ""


def extract_paper(
    subject_id: int,
    label: str,
    qp_path: Path,
    ms_path: Path,
    spec_file_id: str,
    spec_topics_summary: str,
) -> int:
    qp_path, ms_path = Path(qp_path), Path(ms_path)

    # ── Pass 1: Extract questions + topic tags from QP + spec ──
    print("  Pass 1: Extracting questions + topic tags...")
    qp_result = _backend.call_json(
        system=QP_SYSTEM,
        user_text=(
            "Spec topic codes available for tagging:\n\n"
            + spec_topics_summary
            + "\n\nExtract every question (leaf parts only) from the question paper."
        ),
        files=[qp_path],
        schema=QUESTIONS_SCHEMA,
    )
    questions = {q["qnum"]: q for q in qp_result["questions"]}
    print(f"    Got {len(questions)} questions.")

    # ── Pass 2: Extract markschemes from MS ──
    print("  Pass 2: Extracting markschemes...")
    ms_result = _backend.call_json(
        system=MS_SYSTEM,
        user_text=(
            "Extract the markscheme for every question part in this markscheme PDF. "
            "Include ALL marking points, acceptable answers, and guidance. "
            "Question numbers must match the question paper exactly (e.g. 3(b)(ii))."
        ),
        files=[ms_path],
        schema=MARKSCHEME_SCHEMA,
    )
    markschemes = {m["qnum"]: m["markscheme"] for m in ms_result["markschemes"]}
    print(f"    Got {len(markschemes)} markschemes.")

    # Merge with fuzzy fallback for granularity mismatches
    merged = []
    for qnum, q in questions.items():
        merged.append({
            "qnum": qnum,
            "text": q["text"],
            "marks": q["marks"],
            "markscheme": _fuzzy_ms_lookup(qnum, markschemes),
            "topic_codes": q["topic_codes"],
        })

    matched = sum(1 for m in merged if m["markscheme"])
    print(f"  Merged {len(merged)} questions, {matched} with markschemes.")

    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO papers(subject_id, label, qp_path, ms_path, qp_file_id, ms_file_id, extracted_at) "
            "VALUES(?,?,?,?,?,?,?) "
            "ON CONFLICT(subject_id, label) DO UPDATE SET "
            "  qp_file_id=excluded.qp_file_id, ms_file_id=excluded.ms_file_id, extracted_at=excluded.extracted_at "
            "RETURNING id",
            (
                subject_id,
                label,
                str(qp_path),
                str(ms_path),
                "",
                "",
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        paper_id = cur.fetchone()["id"]

        conn.execute("DELETE FROM questions WHERE paper_id = ?", (paper_id,))

        code_map = {
            row["code"]: row["id"]
            for row in conn.execute(
                "SELECT id, code FROM topics WHERE subject_id = ?", (subject_id,)
            ).fetchall()
        }

        for q in merged:
            cur = conn.execute(
                "INSERT INTO questions(paper_id, subject_id, source, qnum, text, marks, markscheme) "
                "VALUES(?,?,?,?,?,?,?)",
                (paper_id, subject_id, "past_paper", q["qnum"], q["text"], q["marks"], q["markscheme"]),
            )
            qid = cur.lastrowid
            for code in q["topic_codes"]:
                tid = code_map.get(code)
                if tid:
                    conn.execute(
                        "INSERT OR IGNORE INTO question_topics(question_id, topic_id) VALUES(?, ?)",
                        (qid, tid),
                    )
        conn.commit()
    return paper_id


def update_markschemes(subject_id: int, label: str, ms_path: Path) -> int:
    """Re-extract markschemes only and update existing questions in place.

    Use when the question extraction is already correct but the markscheme
    pass needs a stronger model. Leaves question text and topic tags untouched.
    """
    ms_path = Path(ms_path)

    with connect() as conn:
        paper = conn.execute(
            "SELECT id FROM papers WHERE subject_id = ? AND label = ?",
            (subject_id, label),
        ).fetchone()
        if paper is None:
            raise ValueError(f"Paper not found: {label} (run build-questions first)")
        paper_id = paper["id"]
        existing = conn.execute(
            "SELECT id, qnum FROM questions WHERE paper_id = ?", (paper_id,)
        ).fetchall()
        if not existing:
            raise ValueError(f"No questions stored for {label}")

    print("  Re-extracting markschemes only...")
    ms_result = _backend.call_json(
        system=MS_SYSTEM,
        user_text=(
            "Extract the markscheme for every question part in this markscheme PDF. "
            "Include ALL marking points, acceptable answers, and guidance. "
            "Question numbers must match the question paper exactly (e.g. 3(b)(ii))."
        ),
        files=[ms_path],
        schema=MARKSCHEME_SCHEMA,
    )
    markschemes = {m["qnum"]: m["markscheme"] for m in ms_result["markschemes"]}
    print(f"    Got {len(markschemes)} markschemes.")

    updated = 0
    with connect() as conn:
        for q in existing:
            ms_text = _fuzzy_ms_lookup(q["qnum"], markschemes)
            if ms_text:
                conn.execute(
                    "UPDATE questions SET markscheme = ? WHERE id = ?",
                    (ms_text, q["id"]),
                )
                updated += 1
        conn.execute(
            "UPDATE papers SET ms_path = ?, extracted_at = ? WHERE id = ?",
            (str(ms_path), datetime.now(timezone.utc).isoformat(), paper_id),
        )
        conn.commit()

    print(f"  Updated {updated}/{len(existing)} markschemes.")
    return paper_id


def topics_summary(subject_id: int) -> str:
    """Compact text summary of topics for context-tagging prompts."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT code, title, depth FROM topics WHERE subject_id = ? ORDER BY id",
            (subject_id,),
        ).fetchall()
    return "\n".join(f"{'  ' * r['depth']}{r['code']}: {r['title']}" for r in rows)
