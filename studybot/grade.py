"""Grade a user answer against a markscheme.

Output format (plain text, parsed with regex). This is used instead of
json_schema so the response can be streamed token-by-token to the UI:

    MARKS_AWARDED: <int>
    SM2_GRADE: <int 0-5>
    FEEDBACK:
    <free-form markdown>
"""
from __future__ import annotations

import re
from typing import Iterator

from . import llm
from .config import GRADER_MODEL
from .db import connect
from .srs import next_review_iso, today_iso, update_mastery, update_sm2

GRADE_SYSTEM = """You are a strict but fair A-Level examiner.

Award marks ONLY where the student's answer matches a marking point in the markscheme (or is a clearly equivalent statement).

If the student uses a valid alternative physics approach that reaches the same correct result through different reasoning, award the same marks. Do not penalize valid alternative methods even if they are not listed in the markscheme. For example, if the markscheme uses energy conservation but the student correctly uses suvat, both approaches earn full marks.

The markscheme uses LaTeX notation for mathematical expressions ($...$ for inline math). Interpret LaTeX correctly: $E_k = \\frac{1}{2}mv^2$ means kinetic energy equals half m v squared, $\\Delta V$ means change in voltage, etc. The student's answer may use plain text approximations; treat these as equivalent when the physics is correct (e.g. "E=1/2mv^2" ≈ $E_k = \\frac{1}{2}mv^2$).

Output EXACTLY this format and nothing else:

MARKS_AWARDED: <integer between 0 and the question's total marks>
SM2_GRADE: <integer 0-5> — follow the marks ratio as a baseline, then adjust ±1 for qualitative factors:
  0%→0, 15%→1, 35%→2, 55%→3, 75%→4, 90%→5. Adjust upward if the student showed correct reasoning but made a minor slip; adjust downward if they guessed correctly without understanding.
ERROR_TAGS: <comma-separated tags from: calculation, units, sig_figs, misconception, missing_explanation, wrong_method, incomplete, notation, none>
  - calculation: arithmetic or algebraic error
  - units: missing or wrong units
  - sig_figs: incorrect significant figures
  - misconception: fundamental misunderstanding of the physics
  - missing_explanation: correct calculation but lacks required explanation/justification
  - wrong_method: chose an inappropriate method entirely
  - incomplete: partial answer, didn't complete all parts
  - notation: wrong symbol or notation use
  - none: essentially correct (minor phrasing differences don't count)
  Use "none" if the answer is essentially correct.
FEEDBACK:
<short markdown feedback structured by question part. For multi-part questions, repeat each part label above the feedback for that part so the student can see which part each comment refers to. Example:

(a) Calculate the maximum speed:
✅ M1 — correct use of $E_k = \frac{1}{2}mv^2$
❌ A1 — you wrote 4.2 but the answer is 4.7 m/s² (re-check your calculation)

(b)(i) Explain why the speed decreases:
❌ B1 — you didn't mention friction doing work on the cart

Do NOT repeat the markscheme verbatim — explain what the student got and what they missed.>

Be strict on units, sig figs, and precise definitions. Be lenient on phrasing where the physics/maths content is correct.
"""

_MARKS_RE = re.compile(r"MARKS_AWARDED:\s*(-?\d+)", re.IGNORECASE)
_SM2_RE = re.compile(r"SM2_GRADE:\s*(-?\d+)", re.IGNORECASE)
_ERROR_TAGS_RE = re.compile(r"ERROR_TAGS:\s*(.+)", re.IGNORECASE)
_FEEDBACK_RE = re.compile(r"FEEDBACK:\s*\n?(.*)", re.IGNORECASE | re.DOTALL)


def _baseline_sm2(marks_awarded: int, total_marks: int) -> int:
    if total_marks <= 0:
        return 0
    ratio = marks_awarded / total_marks
    if ratio < 0.15:
        return 0
    elif ratio < 0.35:
        return 1
    elif ratio < 0.55:
        return 2
    elif ratio < 0.75:
        return 3
    elif ratio < 0.90:
        return 4
    else:
        return 5


def _build_user_blocks(question: dict, user_answer: str) -> list[dict]:
    """Two-block layout so the question + markscheme are cacheable across re-grades."""
    stable = (
        f"Question (worth {question['marks']} marks):\n{question['text']}\n\n"
        f"Markscheme:\n{question['markscheme']}\n"
    )
    answer = f"\nStudent's answer:\n{user_answer}\n\nGrade the answer."
    return [llm.text_block(stable, cache=True), llm.text_block(answer)]


def _parse(text: str, total_marks: int) -> dict:
    m = _MARKS_RE.search(text)
    s = _SM2_RE.search(text)
    e = _ERROR_TAGS_RE.search(text)
    f = _FEEDBACK_RE.search(text)
    marks = int(m.group(1)) if m else 0
    marks = max(0, min(total_marks, marks))
    baseline = _baseline_sm2(marks, total_marks)
    if s:
        sm2_raw = max(0, min(5, int(s.group(1))))
        sm2 = max(baseline - 1, min(baseline + 1, sm2_raw))
    else:
        sm2 = baseline
    error_tags = []
    if e:
        error_tags = [t.strip().lower() for t in e.group(1).split(",") if t.strip() and t.strip().lower() != "none"]
    feedback = (f.group(1).strip() if f else text.strip())
    return {
        "marks_awarded": marks,
        "sm2_grade": sm2,
        "feedback": feedback,
        "total_marks": total_marks,
        "error_tags": error_tags,
    }


def _load_question(question_id: int) -> dict:
    with connect() as conn:
        q = conn.execute(
            "SELECT id, text, marks, markscheme FROM questions WHERE id = ?",
            (question_id,),
        ).fetchone()
    if q is None:
        raise ValueError(f"No question with id {question_id}")
    return dict(q)


def grade_answer(question_id: int, user_answer: str) -> dict:
    q = _load_question(question_id)
    text = llm.call_text(
        system=GRADE_SYSTEM,
        user_blocks=_build_user_blocks(q, user_answer),
        cache_system=True,
        model=GRADER_MODEL,
        max_tokens=2000,
    )
    return _parse(text, q["marks"])


def grade_answer_stream(question_id: int, user_answer: str) -> Iterator[dict]:
    """Stream grading output. Yields:
        {"delta": <str>}      — each text chunk as it arrives
        {"final": <dict>}     — once, at the end, with the parsed grade result
    """
    q = _load_question(question_id)
    full = ""
    for piece in llm.stream_text(
        system=GRADE_SYSTEM,
        user_blocks=_build_user_blocks(q, user_answer),
        cache_system=True,
        model=GRADER_MODEL,
        max_tokens=2000,
    ):
        if isinstance(piece, dict) and "__final__" in piece:
            full = piece["__final__"]
            break
        full += piece
        yield {"delta": piece}
    yield {"final": _parse(full, q["marks"])}


def record_attempt(
    *,
    question_id: int,
    session_id: int | None,
    position: int | None,
    user_answer: str,
    grade_result: dict,
    time_spent_seconds: int | None = None,
) -> int:
    """Persist the attempt + update SM-2 + mastery for all topics this question covers."""
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO attempts(question_id, user_answer, marks_awarded, total_marks, sm2_grade, feedback, time_spent_seconds, error_tags) "
            "VALUES(?,?,?,?,?,?,?,?) RETURNING id",
            (
                question_id,
                user_answer,
                grade_result["marks_awarded"],
                grade_result["total_marks"],
                grade_result["sm2_grade"],
                grade_result["feedback"],
                time_spent_seconds,
                ",".join(grade_result.get("error_tags", [])),
            ),
        )
        attempt_id = cur.fetchone()["id"]

        if session_id is not None and position is not None:
            conn.execute(
                "UPDATE session_questions SET attempt_id = ? "
                "WHERE session_id = ? AND position = ?",
                (attempt_id, session_id, position),
            )

        topic_rows = conn.execute(
            "SELECT topic_id FROM question_topics WHERE question_id = ?", (question_id,)
        ).fetchall()
        for tr in topic_rows:
            tid = tr["topic_id"]
            m = conn.execute(
                "SELECT ease, interval_days, repetitions, score FROM mastery WHERE topic_id = ?",
                (tid,),
            ).fetchone()
            if m is None:
                conn.execute("INSERT INTO mastery(topic_id) VALUES(?)", (tid,))
                ease, interval_days, repetitions, score = 2.5, 0, 0, 0.0
            else:
                ease, interval_days, repetitions, score = (
                    m["ease"],
                    m["interval_days"],
                    m["repetitions"],
                    m["score"],
                )
            new_ease, new_interval, new_reps = update_sm2(
                ease=ease,
                interval_days=interval_days,
                repetitions=repetitions,
                grade=grade_result["sm2_grade"],
            )
            new_score = update_mastery(score, grade_result["sm2_grade"])
            conn.execute(
                "UPDATE mastery SET ease=?, interval_days=?, repetitions=?, score=?, "
                "last_reviewed=?, next_review=? WHERE topic_id=?",
                (
                    new_ease,
                    new_interval,
                    new_reps,
                    new_score,
                    today_iso(),
                    next_review_iso(new_interval),
                    tid,
                ),
            )
        conn.commit()
    return attempt_id
