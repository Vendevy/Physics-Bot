"""Progress reporting."""
from __future__ import annotations

from .db import connect


def subject_progress(subject_id: int) -> dict:
    with connect() as conn:
        leaf_total = conn.execute(
            "SELECT COUNT(*) AS n FROM topics t WHERE t.subject_id=? AND COALESCE(t.content,'')!=''",
            (subject_id,),
        ).fetchone()["n"]
        attempted = conn.execute(
            """
            SELECT COUNT(DISTINCT m.topic_id) AS n
            FROM mastery m JOIN topics t ON t.id = m.topic_id
            WHERE t.subject_id = ? AND m.last_reviewed IS NOT NULL
            """,
            (subject_id,),
        ).fetchone()["n"]
        avg_score = conn.execute(
            """
            SELECT AVG(m.score) AS s
            FROM mastery m JOIN topics t ON t.id = m.topic_id
            WHERE t.subject_id = ? AND COALESCE(t.content,'')!=''
            """,
            (subject_id,),
        ).fetchone()["s"] or 0.0
        weakest = conn.execute(
            """
            SELECT t.code, t.title, m.score, m.last_reviewed
            FROM topics t JOIN mastery m ON m.topic_id = t.id
            WHERE t.subject_id = ? AND COALESCE(t.content,'')!=''
            ORDER BY m.score ASC, COALESCE(m.last_reviewed,'0') ASC
            LIMIT 10
            """,
            (subject_id,),
        ).fetchall()
        recent = conn.execute(
            """
            SELECT a.answered_at, a.marks_awarded, a.total_marks, q.qnum, q.source
            FROM attempts a JOIN questions q ON q.id = a.question_id
            WHERE q.subject_id = ?
            ORDER BY a.answered_at DESC LIMIT 10
            """,
            (subject_id,),
        ).fetchall()

    return {
        "leaf_topics": leaf_total,
        "topics_attempted": attempted,
        "coverage_pct": round(100 * attempted / leaf_total, 1) if leaf_total else 0.0,
        "avg_mastery": round(avg_score, 3),
        "weakest": [dict(r) for r in weakest],
        "recent": [dict(r) for r in recent],
    }


def render(subject_name: str, p: dict) -> str:
    lines = [
        f"=== {subject_name} ===",
        f"Coverage:    {p['topics_attempted']}/{p['leaf_topics']} topics attempted ({p['coverage_pct']}%)",
        f"Avg mastery: {p['avg_mastery']:.2f} / 1.00",
        "",
        "Weakest topics (focus next):",
    ]
    for w in p["weakest"]:
        last = w["last_reviewed"] or "never"
        lines.append(f"  {w['score']:.2f}  {w['code']}  {w['title']}  (last: {last})")
    lines.append("")
    lines.append("Recent attempts:")
    for r in p["recent"]:
        lines.append(
            f"  {r['answered_at'][:16]}  {r['marks_awarded']}/{r['total_marks']}  "
            f"[{r['source']}] {r['qnum'] or ''}"
        )
    return "\n".join(lines)
