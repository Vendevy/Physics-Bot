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

Output EXACTLY this format and nothing else:

MARKS_AWARDED: <integer between 0 and the question's total marks>
SM2_GRADE: <integer 0-5; 0=blackout, 3=correct with effort, 5=flawless>
FEEDBACK:
<short markdown feedback. Reference marking points by name (M1, A1, B1) where appropriate. Don't repeat the markscheme verbatim — explain what the student got and what they missed.>

Be strict on units, sig figs, and precise definitions. Be lenient on phrasing where the physics/maths content is correct.
"""

_MARKS_RE = re.compile(r"MARKS_AWARDED:\s*(-?\d+)", re.IGNORECASE)
_SM2_RE = re.compile(r"SM2_GRADE:\s*(-?\d+)", re.IGNORECASE)
_FEEDBACK_RE = re.compile(r"FEEDBACK:\s*\n?(.*)", re.IGNORECASE | re.DOTALL)


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
    f = _FEEDBACK_RE.search(text)
    marks = int(m.group(1)) if m else 0
    sm2 = int(s.group(1)) if s else 0
    feedback = (f.group(1).strip() if f else text.strip())
    return {
        "marks_awarded": max(0, min(total_marks, marks)),
        "sm2_grade": max(0, min(5, sm2)),
        "feedback": feedback,
        "total_marks": total_marks,
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
            "INSERT INTO attempts(question_id, user_answer, marks_awarded, total_marks, sm2_grade, feedback, time_spent_seconds) "
            "VALUES(?,?,?,?,?,?,?) RETURNING id",
            (
                question_id,
                user_answer,
                grade_result["marks_awarded"],
                grade_result["total_marks"],
                grade_result["sm2_grade"],
                grade_result["feedback"],
                time_spent_seconds,
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
