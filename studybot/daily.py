"""Build the daily set: 7 new generated questions + 3 spaced-recall past-paper questions."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from . import llm
from .config import DAILY_NEW, DAILY_RECALL
from .db import connect
from .srs import today_iso

GEN_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "text": {"type": "string", "description": "The question, in A-Level paper style. Include any required given values, and use Unicode/$...$ for math."},
        "marks": {"type": "integer", "description": "Total marks (typically 2-8)."},
        "markscheme": {"type": "string", "description": "Marking points with marks (M1/A1/B1 style) and acceptable alternatives."},
        "figure": {
            "type": ["object", "null"],
            "description": (
                "Graph data shown beside the question. Set to null for almost all questions. "
                "Only provide a figure when the question genuinely requires the student to read or analyse a graph "
                "(e.g. 'using the graph below, determine the gradient'). Never include a figure if the question asks "
                "the student to plot or draw something themselves."
            ),
            "additionalProperties": False,
            "properties": {
                "type": {"type": "string", "enum": ["line", "scatter", "bar"]},
                "title": {"type": "string", "description": "Short caption shown above the chart"},
                "xlabel": {"type": "string", "description": "x-axis label including units, e.g. 'Time / s'"},
                "ylabel": {"type": "string", "description": "y-axis label including units, e.g. 'Velocity / m s^-1'"},
                "x": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "x values; for bar charts these are category positions"
                },
                "series": {
                    "type": "array",
                    "minItems": 1,
                    "description": "One or more data series. Each y array must have the same length as x.",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "name": {"type": "string"},
                            "y": {"type": "array", "items": {"type": "number"}}
                        },
                        "required": ["name", "y"]
                    }
                }
            },
            "required": ["type", "title", "xlabel", "ylabel", "x", "series"]
        }
    },
    "required": ["text", "marks", "markscheme", "figure"],
}

def _gen_system(subject_name: str, board: str) -> str:
    return f"""You are an examiner for {subject_name} ({board}) generating a fresh practice question on a specific topic from the official specification.

CRITICAL — subject lock:
- EVERY question MUST be a {subject_name} question. Never produce a question from another subject (psychology, biology, chemistry outside of physics chemistry crossover, etc.) even if the topic title sounds generic.
- Topics with generic-sounding titles ("Evaluation of experimental method", "Significant figures", "Mathematical skills for analysis", "Identification of variables", etc.) MUST still be framed inside a {subject_name} context — use a physics scenario such as mechanics, electricity, waves, materials, fields, thermodynamics, nuclear, quantum, or astrophysics. If the topic is about practical/experimental skills, base the experiment on a physics setup (resistance of a wire, refractive index, period of a pendulum, specific heat capacity, radioactive decay, Young's modulus, etc.).
- Use SI units, physics quantities, and physics terminology throughout.

Rules:
- Match the style, difficulty, and structure of official {board} {subject_name} exam questions.
- Pitch difficulty for a student whose current mastery on this topic is given (0=novice, 1=mastered).
- Include any data/values needed to solve it (don't write open-ended definition prompts).
- The markscheme must enumerate marking points with how each mark is awarded.
- Total marks should reflect the depth of the question.

Figures:
- Set `figure` to null for almost every question.
- Only provide a `figure` when the question literally cannot be answered without reading values or trends from a graph.
- Never include a `figure` for questions that ask the student to plot or sketch something themselves.
- When you do include a figure, the question text must reference it (e.g. "The graph above shows..."). Use realistic numerical data with sensible units.
"""


def pick_weakest_topics(subject_id: int, n: int) -> list[dict]:
    """n leaf topics with content, ordered by lowest mastery score, breaking ties by oldest review."""
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT t.id, t.code, t.title, t.content, m.score, m.last_reviewed
            FROM topics t
            JOIN mastery m ON m.topic_id = t.id
            WHERE t.subject_id = ? AND COALESCE(t.content, '') != ''
            ORDER BY m.score ASC, COALESCE(m.last_reviewed, '0') ASC, t.id ASC
            LIMIT ?
            """,
            (subject_id, n),
        ).fetchall()
        return [dict(r) for r in rows]


def pick_topics_by_id(subject_id: int, topic_ids: list[int]) -> list[dict]:
    """Fetch leaf topics by id, preserving the order given in topic_ids.
    Drops any ids that don't belong to subject_id or have no spec content."""
    if not topic_ids:
        return []
    placeholders = ",".join("?" * len(topic_ids))
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT t.id, t.code, t.title, t.content,
                   COALESCE(m.score, 0.0) AS score, m.last_reviewed
            FROM topics t
            LEFT JOIN mastery m ON m.topic_id = t.id
            WHERE t.subject_id = ?
              AND t.id IN ({placeholders})
              AND COALESCE(t.content, '') != ''
            """,
            (subject_id, *topic_ids),
        ).fetchall()
    by_id = {r["id"]: dict(r) for r in rows}
    return [by_id[tid] for tid in topic_ids if tid in by_id]


def pick_due_for_recall(subject_id: int, n: int) -> list[dict]:
    """Past-paper questions whose primary topic is due for review (next_review <= today),
    preferring topics with the longest overdue gap. Falls back to lowest-mastery if nothing is due yet."""
    today = today_iso()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT q.id AS question_id, q.text, q.marks, q.markscheme, q.qnum,
                   t.id AS topic_id, t.code, t.title,
                   m.next_review, m.score
            FROM questions q
            JOIN question_topics qt ON qt.question_id = q.id
            JOIN topics t ON t.id = qt.topic_id
            JOIN mastery m ON m.topic_id = t.id
            WHERE q.subject_id = ? AND q.source = 'past_paper'
              AND m.next_review IS NOT NULL AND m.next_review <= ?
            GROUP BY q.id
            ORDER BY m.next_review ASC
            LIMIT ?
            """,
            (subject_id, today, n),
        ).fetchall()
        results = [dict(r) for r in rows]
        if len(results) < n:
            # Fallback: weakest topics with available past-paper questions
            extra = conn.execute(
                """
                SELECT q.id AS question_id, q.text, q.marks, q.markscheme, q.qnum,
                       t.id AS topic_id, t.code, t.title,
                       m.next_review, m.score
                FROM questions q
                JOIN question_topics qt ON qt.question_id = q.id
                JOIN topics t ON t.id = qt.topic_id
                JOIN mastery m ON m.topic_id = t.id
                WHERE q.subject_id = ? AND q.source = 'past_paper'
                  AND q.id NOT IN ({})
                ORDER BY m.score ASC, RANDOM()
                LIMIT ?
                """.format(",".join("?" * len(results)) or "NULL"),
                (subject_id, *[r["question_id"] for r in results], n - len(results)),
            ).fetchall()
            results.extend(dict(r) for r in extra)
        return results


def generate_question(topic: dict, *, subject_name: str, board: str) -> dict:
    """Generate one fresh question for a topic. Returns dict with text, marks, markscheme."""
    score = topic.get("score", 0.0) or 0.0
    user_text = (
        f"Subject: {subject_name} ({board})\n"
        f"Topic: {topic['code']} — {topic['title']}\n"
        f"Spec content: {topic['content']}\n"
        f"Student's current mastery on this topic: {score:.2f}\n\n"
        f"Generate one {subject_name} practice question on this topic. "
        f"Remember: the question must be a {subject_name} question, never from another subject."
    )
    return llm.call_json(
        system=_gen_system(subject_name, board),
        user_blocks=[llm.text_block(user_text)],
        schema=GEN_SCHEMA,
        cache_system=True,
        max_tokens=2000,
    )


def build_session(
    subject_id: int,
    *,
    topic_ids: list[int] | None = None,
    progress_cb: Callable[[int, int, str], None] | None = None,
    max_workers: int = 4,
) -> int:
    """Create a new session row, populate session_questions with new + recall.
    Generated questions are persisted into the questions table with source='generated'.

    If `topic_ids` is given, generate one question per topic (in that order, capped
    at DAILY_NEW). Otherwise fall back to the user's current weakest topics.

    `progress_cb(done, total, label)` is called as each question finishes generating,
    so callers (e.g. the web UI) can stream status to the user.
    """
    with connect() as conn:
        subject = conn.execute(
            "SELECT name, board FROM subjects WHERE id = ?", (subject_id,)
        ).fetchone()
    if not subject:
        raise RuntimeError(f"Subject id {subject_id} not found")
    subject_name = subject["name"]
    board = subject["board"]

    if topic_ids:
        weak = pick_topics_by_id(subject_id, topic_ids)[:DAILY_NEW]
    else:
        weak = pick_weakest_topics(subject_id, DAILY_NEW)
    recall = pick_due_for_recall(subject_id, DAILY_RECALL)

    if not weak:
        raise RuntimeError(
            "No topics found. Run `python -m studybot extract <subject>` first."
        )

    print(f"Generating {len(weak)} new questions on weakest topics...")
    total = len(weak)
    generated_map: dict[int, tuple[dict, dict]] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {
            ex.submit(generate_question, t, subject_name=subject_name, board=board): (i, t)
            for i, t in enumerate(weak)
        }
        done = 0
        for fut in as_completed(futures):
            i, t = futures[fut]
            q = fut.result()
            generated_map[i] = (t, q)
            done += 1
            label = f"{t['code']} {t['title']}"
            print(f"  [{done}/{total}] {label}")
            if progress_cb:
                progress_cb(done, total, label)
    generated = [generated_map[i] for i in range(total)]

    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO sessions(subject_id) VALUES(?) RETURNING id",
            (subject_id,),
        )
        session_id = cur.fetchone()["id"]

        position = 0
        for t, q in generated:
            fig_val = q.get("figure")
            fig_json = json.dumps(fig_val) if fig_val else None
            cur = conn.execute(
                "INSERT INTO questions(subject_id, source, text, marks, markscheme, figure) "
                "VALUES(?, 'generated', ?, ?, ?, ?) RETURNING id",
                (subject_id, q["text"], q["marks"], q["markscheme"], fig_json),
            )
            qid = cur.fetchone()["id"]
            conn.execute(
                "INSERT INTO question_topics(question_id, topic_id) VALUES(?, ?)",
                (qid, t["id"]),
            )
            conn.execute(
                "INSERT INTO session_questions(session_id, question_id, kind, position) "
                "VALUES(?,?,?,?)",
                (session_id, qid, "new", position),
            )
            position += 1

        for r in recall:
            conn.execute(
                "INSERT INTO session_questions(session_id, question_id, kind, position) "
                "VALUES(?,?,?,?)",
                (session_id, r["question_id"], "recall", position),
            )
            position += 1
        conn.commit()

    return session_id
