"""Local web dashboard for PhysicsBot progress tracking.

Usage:
    python -m studybot dashboard          # opens http://localhost:5050
    python -m studybot dashboard --port 8080
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from . import config
from .db import connect, migrate
from concurrent.futures import ThreadPoolExecutor

from .daily import build_session, build_mock_session
from .grade import grade_answer, grade_answer_stream, record_attempt
from .study_html import STUDY_HTML
from . import notebook_html

# In-memory progress state for streaming session-build status.
# Keyed by build_id; each entry is {"events": [...], "done": bool, "session_id": int|None, "error": str|None}
_BUILDS: dict[str, dict] = {}
_BUILDS_LOCK = threading.Lock()


def _parse_time_spent(v) -> int | None:
    if v is None:
        return None
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    if n < 0 or n > 24 * 3600:
        return None
    return n


def _format_time(seconds: int | None) -> str:
    if seconds is None or seconds < 0:
        return "—"
    if seconds < 60:
        return f"{seconds}s"
    m, s = divmod(seconds, 60)
    if m < 60:
        return f"{m}m {s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m"

PORT = 5050


def _get_subjects() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, name, board FROM subjects ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]


def _get_subject_stats(conn: sqlite3.Connection, subject_id: int) -> dict:
    leaf_total = conn.execute(
        "SELECT COUNT(*) AS n FROM topics WHERE subject_id=? AND COALESCE(content,'')!=''",
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

    total_questions = conn.execute(
        "SELECT COUNT(*) AS n FROM questions WHERE subject_id = ?",
        (subject_id,),
    ).fetchone()["n"]

    attempts = conn.execute(
        """
        SELECT COUNT(*) AS n, SUM(a.marks_awarded) AS marks, SUM(a.total_marks) AS total
        FROM attempts a JOIN questions q ON q.id = a.question_id
        WHERE q.subject_id = ?
        """,
        (subject_id,),
    ).fetchone()
    attempt_count = attempts["n"] or 0
    accuracy = (attempts["marks"] or 0) / (attempts["total"] or 1) * 100 if attempts["total"] else 0.0

    return {
        "leaf_total": leaf_total,
        "attempted": attempted,
        "coverage_pct": round(100 * attempted / leaf_total, 1) if leaf_total else 0.0,
        "avg_mastery": avg_score,
        "avg_mastery_pct": round(avg_score * 100, 1),
        "total_questions": total_questions,
        "attempt_count": attempt_count,
        "accuracy": round(accuracy, 1),
    }


def _get_topic_tree(conn: sqlite3.Connection, subject_id: int) -> list[dict]:
    """Return a nested list of modules -> submodules -> groups -> leaf topics with mastery."""
    rows = conn.execute(
        """
        SELECT t.id, t.code, t.title, t.depth, t.parent_id, t.content,
               COALESCE(m.score, 0.0) AS score, m.last_reviewed
        FROM topics t
        LEFT JOIN mastery m ON m.topic_id = t.id
        WHERE t.subject_id = ?
        ORDER BY t.code
        """,
        (subject_id,),
    ).fetchall()

    by_id = {}
    for r in rows:
        node = dict(r)
        node["children"] = []
        by_id[node["id"]] = node

    roots = []
    for node in by_id.values():
        pid = node["parent_id"]
        if pid is None:
            roots.append(node)
        else:
            by_id[pid]["children"].append(node)

    return roots


def _compute_group_avg(node: dict) -> float:
    """Recursively compute average mastery for a node based on leaf descendants."""
    if not node.get("children"):
        return node.get("score", 0.0) or 0.0
    scores = []
    for child in node["children"]:
        scores.append(_compute_group_avg(child))
    return sum(scores) / len(scores) if scores else 0.0


def _count_leaves(node: dict) -> int:
    if not node.get("children"):
        return 1
    return sum(_count_leaves(c) for c in node["children"])


def _count_attempted(node: dict) -> int:
    if not node.get("children"):
        return 1 if node.get("last_reviewed") else 0
    return sum(_count_attempted(c) for c in node["children"])


def _unfinished_session(conn: sqlite3.Connection, subject_id: int) -> dict | None:
    """Return the most recent unfinished session for a subject, with progress counts."""
    row = conn.execute(
        """
        SELECT s.id,
               (SELECT COUNT(*) FROM session_questions WHERE session_id = s.id) AS total,
               (SELECT COUNT(*) FROM session_questions
                WHERE session_id = s.id AND attempt_id IS NOT NULL) AS done
        FROM sessions s
        WHERE s.subject_id = ? AND s.completed_at IS NULL
        ORDER BY s.started_at DESC
        LIMIT 1
        """,
        (subject_id,),
    ).fetchone()
    if not row or row["total"] == 0:
        return None
    return {"id": row["id"], "total": row["total"], "done": row["done"]}


def _get_recent_attempts(conn: sqlite3.Connection, subject_id: int, limit: int = 15) -> list[dict]:
    rows = conn.execute(
        """
        SELECT a.id, a.answered_at, a.user_answer, a.marks_awarded, a.total_marks,
               a.sm2_grade, a.feedback, a.time_spent_seconds,
               q.id AS qid, q.text AS question_text,
               q.qnum, q.source, q.marks AS q_marks,
               GROUP_CONCAT(t.code || ' ' || t.title, ' | ') AS topics
        FROM attempts a
        JOIN questions q ON q.id = a.question_id
        LEFT JOIN question_topics qt ON qt.question_id = q.id
        LEFT JOIN topics t ON t.id = qt.topic_id
        WHERE q.subject_id = ?
        GROUP BY a.id
        ORDER BY a.answered_at DESC
        LIMIT ?
        """,
        (subject_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def _sm2_label(grade: int) -> str:
    labels = {5: "Perfect", 4: "Easy", 3: "Correct", 2: "Hard", 1: "Forgot", 0: "Blackout"}
    return labels.get(grade, "Unknown")


def _build_html(subject_id: int | None = None) -> str:
    subjects = _get_subjects()
    if not subjects:
        return _error_html("No subjects found. Run `python -m studybot init` and `extract-spec` first.")

    if subject_id is None:
        subject_id = subjects[0]["id"]

    subject = next((s for s in subjects if s["id"] == subject_id), subjects[0])

    with connect() as conn:
        stats = _get_subject_stats(conn, subject_id)
        tree = _get_topic_tree(conn, subject_id)
        recent = _get_recent_attempts(conn, subject_id)
        unfinished = _unfinished_session(conn, subject_id)

    # Pre-compute averages for all nodes
    for node in tree:
        _compute_group_avg(node)

    overall = stats["avg_mastery_pct"]
    if overall >= 70:
        overall_color = "#22c55e"
    elif overall >= 40:
        overall_color = "#eab308"
    else:
        overall_color = "#a1a1aa"

    # Subject selector
    subject_options = ""
    for s in subjects:
        selected = " selected" if s["id"] == subject_id else ""
        subject_options += f'<option value="{s["id"]}"{selected}>{s["name"]}</option>'

    # Build topic tree HTML
    def render_node(node: dict, level: int) -> str:
        avg = (node.get("score", 0.0) or 0.0) * 100 if not node.get("children") else _compute_group_avg(node) * 100
        title = node["title"]
        code = node["code"]
        leaves = _count_leaves(node)
        tested = _count_attempted(node)

        if level == 0:
            return f"""
            <div class="paper-section">
                <div class="paper-header">
                    <div class="paper-header-left">
                        <h3 class="paper-title">{code} {title}</h3>
                        <span class="paper-meta">{tested}/{leaves} topics attempted</span>
                    </div>
                    <span class="paper-avg">{avg:.1f}%</span>
                </div>
                <div class="progress-bar-track">
                    <div class="progress-bar-fill" style="width: {avg:.1f}%"></div>
                </div>
                <div class="module-children">
                    {''.join(render_node(c, level + 1) for c in node.get("children", []))}
                </div>
            </div>
            """
        elif level == 1:
            return f"""
            <div class="module">
                <div class="module-header">
                    <h4 class="module-title">{code} {title}</h4>
                    <span class="module-avg">{avg:.1f}%</span>
                </div>
                <div class="progress-bar-track thin">
                    <div class="progress-bar-fill" style="width: {avg:.1f}%"></div>
                </div>
                <div class="module-children">
                    {''.join(render_node(c, level + 1) for c in node.get("children", []))}
                </div>
            </div>
            """
        elif level == 2:
            # Topic group - render children as chips
            chips = ""
            for leaf in node.get("children", []):
                leaf_avg = (leaf.get("score", 0.0) or 0.0) * 100
                if leaf_avg >= 70:
                    color = "#22c55e"
                elif leaf_avg >= 30:
                    color = "#eab308"
                elif leaf_avg > 0:
                    color = "#ef4444"
                else:
                    color = "#3f3f46"
                reviewed = "reviewed" if leaf.get("last_reviewed") else "unreviewed"
                chips += f"""
                    <div class="topic-chip {reviewed}" style="border-left-color: {color}">
                        <span class="topic-name">{leaf['code']} {leaf['title']}</span>
                        <span class="topic-meta">{leaf_avg:.0f}%</span>
                    </div>
                """
            return f"""
            <div class="topic-group">
                <div class="topic-group-header">
                    <span class="topic-group-title">{code} {title}</span>
                    <span class="topic-group-avg">{avg:.1f}%</span>
                </div>
                <div class="topics-grid">
                    {chips}
                </div>
            </div>
            """
        else:
            return ""

    tree_html = "".join(render_node(node, 0) for node in tree)

    # Recent attempts
    history_html = ""
    if recent:
        for h in recent:
            pct = (h["marks_awarded"] / h["total_marks"] * 100) if h["total_marks"] else 0
            if pct >= 80:
                result_color = "#22c55e"
                result_bg = "rgba(34, 197, 94, 0.08)"
                border_color = "rgba(34, 197, 94, 0.2)"
                result = "CORRECT"
            elif pct >= 50:
                result_color = "#eab308"
                result_bg = "rgba(234, 179, 8, 0.08)"
                border_color = "rgba(234, 179, 8, 0.2)"
                result = "PARTIAL"
            else:
                result_color = "#ef4444"
                result_bg = "rgba(239, 68, 68, 0.08)"
                border_color = "rgba(239, 68, 68, 0.2)"
                result = "INCORRECT"

            topics = h.get("topics") or "Unknown"
            qnum = h.get("qnum") or "Generated"
            source = h.get("source", "")
            date = h.get("answered_at", "")[:16]
            feedback = (h.get("feedback") or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
            question_text = (h.get("question_text") or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
            user_answer = (h.get("user_answer") or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")

            history_html += f"""
            <details class="history-item" style="border-color: {border_color}; background: {result_bg};">
                <summary class="history-summary">
                    <div class="history-left">
                        <span class="history-result" style="color: {result_color}">{result}</span>
                        <span class="history-score" style="color: {result_color}">{h['marks_awarded']}/{h['total_marks']}</span>
                        <span class="history-topic">{topics}</span>
                    </div>
                    <div class="history-right">
                        <span class="history-paper">{source} {qnum}</span>
                        <span class="history-time">{_format_time(h.get('time_spent_seconds'))}</span>
                        <span class="history-date">{date}</span>
                    </div>
                </summary>
                <div class="history-detail">
                    <div class="history-section">
                        <div class="history-section-label">Question</div>
                        <div class="history-section-content">{question_text}</div>
                    </div>
                    <div class="history-section">
                        <div class="history-section-label">Your Answer</div>
                        <div class="history-section-content">{user_answer}</div>
                    </div>
                    <div class="history-section">
                        <div class="history-section-label">Feedback</div>
                        <div class="history-section-content">{feedback}</div>
                    </div>
                </div>
            </details>
            """
    else:
        history_html = '<p class="empty-state">No attempts yet. Run <code>python -m studybot study &lt;subject&gt;</code> to start.</p>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PhysicsBot Dashboard</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        *, *::before, *::after {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
            background: #0a0a0a;
            color: #e4e4e7;
            min-height: 100vh;
            line-height: 1.5;
            -webkit-font-smoothing: antialiased;
            -moz-osx-font-smoothing: grayscale;
        }}
        .header {{
            position: sticky;
            top: 0;
            z-index: 50;
            background: rgba(10, 10, 10, 0.8);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border-bottom: 1px solid rgba(255, 255, 255, 0.06);
        }}
        .header-inner {{
            max-width: 1100px;
            margin: 0 auto;
            padding: 16px 32px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 12px;
        }}
        .header-left h1 {{
            font-size: 16px;
            font-weight: 600;
            color: #e4e4e7;
            letter-spacing: -0.01em;
        }}
        .header-left p {{
            font-size: 13px;
            color: #52525b;
            font-weight: 400;
            margin-top: 2px;
        }}
        .header-actions {{
            display: flex;
            gap: 8px;
            align-items: center;
        }}
        .subject-select {{
            background: #18181b;
            border: 1px solid rgba(255,255,255,0.06);
            color: #a1a1aa;
            padding: 8px 12px;
            border-radius: 8px;
            font-family: inherit;
            font-size: 13px;
            cursor: pointer;
            outline: none;
        }}
        .subject-select:hover {{
            border-color: rgba(255,255,255,0.1);
        }}
        .container {{
            max-width: 1100px;
            margin: 0 auto;
            padding: 32px 32px 64px;
        }}
        .section-label {{
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: #52525b;
            margin-bottom: 12px;
        }}
        .overall-card {{
            padding: 32px;
            margin-bottom: 32px;
        }}
        .overall-top {{
            display: flex;
            align-items: flex-end;
            gap: 12px;
            margin-bottom: 24px;
        }}
        .overall-number {{
            font-size: 56px;
            font-weight: 700;
            letter-spacing: -0.03em;
            line-height: 1;
            color: {overall_color};
        }}
        .overall-suffix {{
            font-size: 24px;
            font-weight: 300;
            color: #52525b;
            margin-bottom: 6px;
        }}
        .overall-sublabel {{
            font-size: 13px;
            color: #52525b;
            font-weight: 400;
            margin-bottom: 20px;
        }}
        .progress-bar-overall {{
            background: #18181b;
            border-radius: 3px;
            height: 4px;
            overflow: hidden;
            margin-bottom: 32px;
        }}
        .progress-bar-overall-fill {{
            height: 100%;
            background: {overall_color};
            border-radius: 3px;
            transition: width 0.6s ease;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 1px;
            background: rgba(255, 255, 255, 0.04);
            border-radius: 12px;
            overflow: hidden;
            border: 1px solid rgba(255, 255, 255, 0.06);
        }}
        .stat-cell {{
            background: #0a0a0a;
            padding: 20px 24px;
        }}
        .stat-value {{
            font-size: 22px;
            font-weight: 600;
            color: #e4e4e7;
            letter-spacing: -0.02em;
        }}
        .stat-label {{
            font-size: 12px;
            color: #52525b;
            font-weight: 400;
            margin-top: 4px;
        }}
        .btn {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 8px 16px;
            border-radius: 8px;
            border: 1px solid rgba(255, 255, 255, 0.06);
            font-family: inherit;
            font-size: 13px;
            font-weight: 500;
            cursor: pointer;
            transition: background 0.2s ease, border-color 0.2s ease;
            background: #18181b;
            color: #a1a1aa;
            text-decoration: none;
        }}
        .btn:hover {{
            background: #27272a;
            border-color: rgba(255, 255, 255, 0.1);
            color: #e4e4e7;
        }}
        .btn-primary {{
            background: #6366f1;
            border-color: #6366f1;
            color: #fff;
        }}
        .btn-primary:hover {{
            background: #5558e6;
            border-color: #5558e6;
            color: #fff;
        }}
        .paper-section {{
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 16px;
        }}
        .paper-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 12px;
        }}
        .paper-header-left {{
            display: flex;
            align-items: baseline;
            gap: 12px;
        }}
        .paper-title {{
            font-size: 15px;
            font-weight: 600;
            color: #e4e4e7;
        }}
        .paper-avg {{
            font-size: 14px;
            font-weight: 600;
            color: #6366f1;
            font-variant-numeric: tabular-nums;
        }}
        .paper-meta {{
            font-size: 12px;
            color: #3f3f46;
            font-weight: 400;
        }}
        .progress-bar-track {{
            background: #18181b;
            border-radius: 3px;
            height: 4px;
            overflow: hidden;
            margin-bottom: 4px;
        }}
        .progress-bar-track.thin {{
            height: 3px;
        }}
        .progress-bar-fill {{
            height: 100%;
            background: #6366f1;
            border-radius: 3px;
            transition: width 0.5s ease;
        }}
        .module {{
            margin: 20px 0 0 0;
            padding: 16px 0 0 16px;
            border-left: 1px solid rgba(255, 255, 255, 0.06);
        }}
        .module-header {{
            display: flex;
            align-items: baseline;
            justify-content: space-between;
            margin-bottom: 8px;
        }}
        .module-title {{
            font-size: 13px;
            font-weight: 500;
            color: #a1a1aa;
        }}
        .module-avg {{
            font-size: 12px;
            font-weight: 500;
            color: #52525b;
            font-variant-numeric: tabular-nums;
        }}
        .module-children {{
            margin-top: 12px;
        }}
        .topic-group {{
            margin-top: 16px;
            padding: 12px 0 0 12px;
            border-left: 1px solid rgba(255, 255, 255, 0.04);
        }}
        .topic-group-header {{
            display: flex;
            align-items: baseline;
            justify-content: space-between;
            margin-bottom: 8px;
        }}
        .topic-group-title {{
            font-size: 12px;
            font-weight: 500;
            color: #71717a;
        }}
        .topic-group-avg {{
            font-size: 12px;
            font-weight: 500;
            color: #3f3f46;
            font-variant-numeric: tabular-nums;
        }}
        .topics-grid {{
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            margin-top: 8px;
        }}
        .topic-chip {{
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid rgba(255, 255, 255, 0.04);
            border-left: 2px solid #3f3f46;
            padding: 4px 10px 4px 8px;
            border-radius: 6px;
            display: flex;
            align-items: baseline;
            gap: 8px;
            transition: background 0.2s ease;
            cursor: default;
        }}
        .topic-chip:hover {{
            background: rgba(255, 255, 255, 0.04);
        }}
        .topic-chip.reviewed {{
            opacity: 1;
        }}
        .topic-chip.unreviewed {{
            opacity: 0.6;
        }}
        .topic-name {{
            font-size: 12px;
            color: #a1a1aa;
            font-weight: 400;
        }}
        .topic-meta {{
            font-size: 11px;
            color: #3f3f46;
            font-weight: 400;
            font-variant-numeric: tabular-nums;
            white-space: nowrap;
        }}
        .history-list {{
            margin-bottom: 32px;
        }}
        .history-item {{
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 10px;
            margin-bottom: 8px;
            overflow: hidden;
            transition: border-color 0.2s ease;
        }}
        .history-item[open] {{
            border-color: rgba(255, 255, 255, 0.12);
        }}
        .history-summary {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 12px 16px;
            cursor: pointer;
            list-style: none;
            user-select: none;
        }}
        .history-summary::-webkit-details-marker {{
            display: none;
        }}
        .history-left {{
            display: flex;
            align-items: center;
            gap: 12px;
            flex-wrap: wrap;
        }}
        .history-result {{
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            min-width: 72px;
        }}
        .history-score {{
            font-size: 13px;
            font-weight: 600;
            font-variant-numeric: tabular-nums;
        }}
        .history-topic {{
            font-size: 13px;
            font-weight: 500;
            color: #d4d4d8;
        }}
        .history-right {{
            display: flex;
            align-items: center;
            gap: 12px;
        }}
        .history-paper {{
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: #52525b;
            background: rgba(255, 255, 255, 0.04);
            padding: 2px 8px;
            border-radius: 4px;
        }}
        .history-date {{
            font-size: 12px;
            color: #3f3f46;
            font-variant-numeric: tabular-nums;
        }}
        .history-time {{
            font-size: 11px;
            color: #71717a;
            font-variant-numeric: tabular-nums;
            background: rgba(255, 255, 255, 0.03);
            padding: 2px 8px;
            border-radius: 4px;
        }}
        .history-detail {{
            padding: 0 16px 16px;
            border-top: 1px solid rgba(255, 255, 255, 0.04);
        }}
        .history-section {{
            margin-top: 12px;
        }}
        .history-section-label {{
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            color: #52525b;
            margin-bottom: 4px;
        }}
        .history-section-content {{
            font-size: 13px;
            color: #a1a1aa;
            line-height: 1.6;
        }}
        .empty-state {{
            color: #3f3f46;
            font-size: 13px;
            font-weight: 400;
            padding: 8px 0;
        }}
        code {{
            font-family: 'SF Mono', 'Fira Code', monospace;
            font-size: 12px;
            background: rgba(255,255,255,0.04);
            padding: 2px 6px;
            border-radius: 4px;
            color: #a1a1aa;
        }}
        @media (max-width: 720px) {{
            .container {{ padding: 20px 16px 48px; }}
            .header-inner {{ padding: 12px 16px; }}
            .stats-grid {{ grid-template-columns: repeat(2, 1fr); }}
            .overall-number {{ font-size: 40px; }}
            .paper-section {{ padding: 16px; }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <div class="header-inner">
            <div class="header-left">
                <h1>PhysicsBot</h1>
                <p>{subject['name']}</p>
            </div>
            <div class="header-actions">
                <select class="subject-select" onchange="location.href='/?subject='+this.value">
                    {subject_options}
                </select>
                {f'''<a href="/study?subject={subject_id}" class="btn" style="text-decoration:none; background:#eab308; border-color:#eab308; color:#0a0a0a;">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                    Resume ({unfinished["done"]}/{unfinished["total"]})
                </a>''' if unfinished else ''}
                <a href="/study?subject={subject_id}" class="btn" style="text-decoration:none;">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>
                    Study
                </a>
                <a href="/notebook?subject={subject_id}" class="btn" style="text-decoration:none;">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                    Notebook
                </a>
                <button class="btn" onclick="location.reload()">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
                    Refresh
                </button>
            </div>
        </div>
    </div>

    <div class="container">
        <div class="overall-card">
            <div class="overall-top">
                <span class="overall-number">{overall:.1f}</span>
                <span class="overall-suffix">%</span>
            </div>
            <div class="overall-sublabel">{stats['leaf_total']} spec points tracked</div>
            <div class="progress-bar-overall">
                <div class="progress-bar-overall-fill" style="width: {overall:.1f}%"></div>
            </div>
        </div>

        <div class="stats-grid">
            <div class="stat-cell">
                <div class="stat-value">{stats['leaf_total']}</div>
                <div class="stat-label">Spec points</div>
            </div>
            <div class="stat-cell">
                <div class="stat-value">{stats['attempt_count']}</div>
                <div class="stat-label">Questions answered</div>
            </div>
            <div class="stat-cell">
                <div class="stat-value">{stats['accuracy']:.0f}%</div>
                <div class="stat-label">Accuracy</div>
            </div>
            <div class="stat-cell">
                <div class="stat-value">{stats['total_questions']}</div>
                <div class="stat-label">Question bank</div>
            </div>
        </div>

        <div style="height: 32px"></div>

        <p class="section-label">Recent Attempts</p>
        <div class="history-list">
            {history_html}
        </div>

        <p class="section-label">Spec Coverage</p>
        {tree_html}
    </div>
</body>
</html>"""


def _error_html(msg: str) -> str:
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Error</title>
    <style>body{{background:#0a0a0a;color:#e4e4e7;font-family:Inter,sans-serif;padding:40px;}}</style>
    </head><body><h2>PhysicsBot Dashboard</h2><p>{msg}</p></body></html>"""


class DashboardHandler(SimpleHTTPRequestHandler):
    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        return json.loads(body) if body else {}

    def _send_json(self, data: dict, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            subject_id = qs.get("subject", [None])[0]
            if subject_id:
                try:
                    subject_id = int(subject_id)
                except ValueError:
                    subject_id = None
            html = _build_html(subject_id)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode())
        elif path == "/study":
            html = STUDY_HTML.replace("{{DAILY_NEW}}", str(config.DAILY_NEW)).replace("{{DAILY_RECALL}}", str(config.DAILY_RECALL))
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode())
        elif path == "/notebook":
            self._handle_notebook(qs)
        elif path == "/api/study/complete":
            self._handle_study_complete(qs)
        elif path == "/api/study/build-status":
            self._handle_build_status(qs)
        elif path == "/api/study/resume":
            self._handle_study_resume(qs)
        elif path == "/api/study/topics":
            self._handle_study_topics(qs)
        elif path == "/api/papers":
            self._handle_papers(qs)
        else:
            self.send_error(404)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/study/start":
            self._handle_study_start()
        elif path == "/api/study/submit":
            self._handle_study_submit()
        elif path == "/api/study/submit-stream":
            self._handle_study_submit_stream()
        elif path == "/api/study/consolidate":
            self._handle_study_consolidate()
        elif path == "/api/study/flag":
            self._handle_study_flag()
        elif path == "/api/study/discard":
            self._handle_study_discard()
        elif path == "/api/study/mock-start":
            self._handle_mock_start()
        elif path == "/api/study/mock-submit":
            self._handle_mock_submit()
        else:
            self.send_error(404)

    def _resolve_subject_id(self, requested) -> int | None:
        """Use the requested subject if it exists; otherwise the first subject."""
        with connect() as conn:
            if requested is not None:
                row = conn.execute(
                    "SELECT id FROM subjects WHERE id = ?", (requested,)
                ).fetchone()
                if row:
                    return row["id"]
            row = conn.execute("SELECT id FROM subjects ORDER BY id LIMIT 1").fetchone()
            return row["id"] if row else None

    def _handle_study_start(self):
        """Kick off session generation in a background thread, return a build_id.
        Client polls /api/study/build-status?build_id=… for progress + final session_id."""
        try:
            data = self._read_json()
            requested = data.get("subject_id")
            if requested is not None:
                try:
                    requested = int(requested)
                except (TypeError, ValueError):
                    requested = None
            subject_id = self._resolve_subject_id(requested)
            if subject_id is None:
                self._send_json({"ok": False, "error": "No subject found. Run extract-spec first."})
                return

            raw_topics = data.get("topic_ids") or []
            topic_ids: list[int] = []
            for t in raw_topics:
                try:
                    topic_ids.append(int(t))
                except (TypeError, ValueError):
                    pass
            topic_ids = topic_ids or None

            try:
                n_new = int(data.get("n_new")) if data.get("n_new") is not None else None
            except (TypeError, ValueError):
                n_new = None
            try:
                difficulty = int(data.get("difficulty", 3))
            except (TypeError, ValueError):
                difficulty = 3
            if difficulty not in (3, 4, 5, 6):
                difficulty = 3

            build_id = f"b{int(datetime.now().timestamp() * 1000)}"
            with _BUILDS_LOCK:
                _BUILDS[build_id] = {"events": [], "done": False, "session_id": None, "error": None}

            def progress_cb(done, total, label):
                with _BUILDS_LOCK:
                    _BUILDS[build_id]["events"].append({"done": done, "total": total, "label": label})

            def worker():
                try:
                    sid = build_session(
                        subject_id,
                        topic_ids=topic_ids,
                        n_new=n_new,
                        difficulty=difficulty,
                        progress_cb=progress_cb,
                    )
                    with _BUILDS_LOCK:
                        _BUILDS[build_id]["session_id"] = sid
                        _BUILDS[build_id]["done"] = True
                except Exception as e:
                    with _BUILDS_LOCK:
                        _BUILDS[build_id]["error"] = str(e)
                        _BUILDS[build_id]["done"] = True

            threading.Thread(target=worker, daemon=True).start()
            self._send_json({"ok": True, "build_id": build_id})
        except Exception as e:
            self._send_json({"ok": False, "error": str(e)})

    def _handle_build_status(self, qs: dict):
        build_id = qs.get("build_id", [None])[0]
        with _BUILDS_LOCK:
            state = _BUILDS.get(build_id)
            if not state:
                self._send_json({"ok": False, "error": "Unknown build_id"})
                return
            payload = {
                "ok": True,
                "events": list(state["events"]),
                "done": state["done"],
                "error": state["error"],
                "session_id": state["session_id"],
            }
        if state["done"] and state["session_id"]:
            payload["questions"] = self._fetch_session_questions(state["session_id"])
            with _BUILDS_LOCK:
                _BUILDS.pop(build_id, None)
        self._send_json(payload)

    def _fetch_session_questions(self, session_id: int) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                """
                SELECT sq.position, sq.kind, q.id AS question_id, q.text, q.marks,
                       q.qnum, q.markscheme, q.figure
                FROM session_questions sq
                JOIN questions q ON q.id = sq.question_id
                WHERE sq.session_id = ?
                ORDER BY sq.position
                """,
                (session_id,),
            ).fetchall()
        return [
            {
                "position": r["position"],
                "question_id": r["question_id"],
                "text": r["text"],
                "marks": r["marks"],
                "qnum": r["qnum"] or "",
                "kind": r["kind"],
                "markscheme": r["markscheme"] or "",
                "figure": json.loads(r["figure"]) if r["figure"] else None,
            }
            for r in rows
        ]

    def _handle_study_resume(self, qs: dict):
        """Return the most recent unfinished session for a subject, or null if none."""
        try:
            requested = qs.get("subject_id", [None])[0]
            if requested is not None:
                try:
                    requested = int(requested)
                except ValueError:
                    requested = None
            subject_id = self._resolve_subject_id(requested)
            if subject_id is None:
                self._send_json({"ok": True, "session_id": None})
                return
            with connect() as conn:
                row = conn.execute(
                    """
                    SELECT id FROM sessions
                    WHERE subject_id = ? AND completed_at IS NULL
                    ORDER BY started_at DESC LIMIT 1
                    """,
                    (subject_id,),
                ).fetchone()
            if not row:
                self._send_json({"ok": True, "session_id": None})
                return
            session_id = row["id"]
            questions = self._fetch_session_questions(session_id)
            # Determine which positions already have an attempt
            with connect() as conn:
                attempted = conn.execute(
                    """
                    SELECT sq.position, a.marks_awarded, a.total_marks, a.sm2_grade,
                           a.feedback, a.user_answer, sq.consolidation
                    FROM session_questions sq
                    LEFT JOIN attempts a ON a.id = sq.attempt_id
                    WHERE sq.session_id = ?
                    ORDER BY sq.position
                    """,
                    (session_id,),
                ).fetchall()
            attempts = []
            for r in attempted:
                if r["marks_awarded"] is not None:
                    attempts.append({
                        "position": r["position"],
                        "marks_awarded": r["marks_awarded"],
                        "total_marks": r["total_marks"],
                        "sm2_grade": r["sm2_grade"],
                        "feedback": r["feedback"] or "",
                        "user_answer": r["user_answer"] or "",
                        "consolidation": r["consolidation"] or "",
                    })
            self._send_json({
                "ok": True,
                "session_id": session_id,
                "questions": questions,
                "attempts": attempts,
            })
        except Exception as e:
            self._send_json({"ok": False, "error": str(e)})

    def _handle_study_submit(self):
        try:
            data = self._read_json()
            session_id = data.get("session_id")
            position = data.get("position")
            answer = data.get("answer", "").strip()
            time_spent = _parse_time_spent(data.get("time_spent_seconds"))
            if session_id is None or position is None:
                self._send_json({"ok": False, "error": "Missing session_id or position"})
                return
            # Get question_id from session
            with connect() as conn:
                row = conn.execute(
                    "SELECT question_id FROM session_questions WHERE session_id = ? AND position = ?",
                    (session_id, position),
                ).fetchone()
            if not row:
                self._send_json({"ok": False, "error": "Question not found in session"})
                return
            question_id = row["question_id"]
            result = grade_answer(question_id, answer)
            record_attempt(
                question_id=question_id,
                session_id=session_id,
                position=position,
                user_answer=answer,
                grade_result=result,
                time_spent_seconds=time_spent,
            )
            self._send_json({
                "ok": True,
                "marks_awarded": result["marks_awarded"],
                "total_marks": result["total_marks"],
                "sm2_grade": result["sm2_grade"],
                "feedback": result["feedback"],
            })
        except Exception as e:
            self._send_json({"ok": False, "error": str(e)})

    def _handle_study_topics(self, qs: dict):
        """Return all leaf topics (with content) for a subject for the picker UI."""
        try:
            requested = qs.get("subject_id", [None])[0]
            if requested is not None:
                try:
                    requested = int(requested)
                except ValueError:
                    requested = None
            subject_id = self._resolve_subject_id(requested)
            if subject_id is None:
                self._send_json({"ok": False, "error": "No subject"})
                return
            with connect() as conn:
                rows = conn.execute(
                    """
                    SELECT t.id, t.code, t.title,
                           COALESCE(m.score, 0.0) AS score,
                           m.last_reviewed
                    FROM topics t
                    LEFT JOIN mastery m ON m.topic_id = t.id
                    WHERE t.subject_id = ? AND COALESCE(t.content, '') != ''
                    ORDER BY t.code
                    """,
                    (subject_id,),
                ).fetchall()
            topics = [
                {
                    "id": r["id"],
                    "code": r["code"],
                    "title": r["title"],
                    "score": float(r["score"] or 0.0),
                    "reviewed": r["last_reviewed"] is not None,
                }
                for r in rows
            ]
            self._send_json({"ok": True, "topics": topics})
        except Exception as e:
            self._send_json({"ok": False, "error": str(e)})

    def _handle_papers(self, qs: dict):
        try:
            requested = qs.get("subject_id", [None])[0]
            if requested is not None:
                try:
                    requested = int(requested)
                except ValueError:
                    requested = None
            subject_id = self._resolve_subject_id(requested)
            if subject_id is None:
                self._send_json({"ok": False, "error": "No subject"})
                return
            with connect() as conn:
                rows = conn.execute(
                    """
                    SELECT p.id, p.label,
                           (SELECT COUNT(*) FROM questions q WHERE q.paper_id = p.id) AS n_questions,
                           (SELECT COALESCE(SUM(q.marks), 0) FROM questions q WHERE q.paper_id = p.id) AS total_marks
                    FROM papers p
                    WHERE p.subject_id = ?
                    ORDER BY p.label
                    """,
                    (subject_id,),
                ).fetchall()
            papers = [
                {
                    "id": r["id"],
                    "label": r["label"],
                    "n_questions": r["n_questions"],
                    "total_marks": r["total_marks"],
                }
                for r in rows
                if r["n_questions"] > 0
            ]
            self._send_json({"ok": True, "papers": papers})
        except Exception as e:
            self._send_json({"ok": False, "error": str(e)})

    def _handle_mock_start(self):
        try:
            data = self._read_json()
            requested = data.get("subject_id")
            if requested is not None:
                try:
                    requested = int(requested)
                except (TypeError, ValueError):
                    requested = None
            subject_id = self._resolve_subject_id(requested)
            if subject_id is None:
                self._send_json({"ok": False, "error": "No subject"})
                return
            try:
                paper_id = int(data.get("paper_id"))
            except (TypeError, ValueError):
                self._send_json({"ok": False, "error": "Missing or invalid paper_id"})
                return
            session_id = build_mock_session(subject_id, paper_id)
            questions = self._fetch_session_questions(session_id)
            with connect() as conn:
                paper = conn.execute(
                    "SELECT label FROM papers WHERE id = ?", (paper_id,)
                ).fetchone()
                total_marks = sum(q["marks"] for q in questions)
            self._send_json({
                "ok": True,
                "session_id": session_id,
                "questions": questions,
                "paper_label": paper["label"] if paper else "",
                "total_marks": total_marks,
            })
        except Exception as e:
            self._send_json({"ok": False, "error": str(e)})

    def _handle_mock_submit(self):
        """Batch-grade every answer in a mock session in parallel.
        Body: {session_id, attempts: [{position, answer, time_spent_seconds?}]}."""
        try:
            data = self._read_json()
            session_id = data.get("session_id")
            raw_attempts = data.get("attempts") or []
            if session_id is None:
                self._send_json({"ok": False, "error": "Missing session_id"})
                return
            with connect() as conn:
                rows = conn.execute(
                    """
                    SELECT sq.position, sq.question_id
                    FROM session_questions sq
                    WHERE sq.session_id = ?
                    """,
                    (session_id,),
                ).fetchall()
            qid_by_pos = {r["position"]: r["question_id"] for r in rows}

            jobs: list[tuple[int, int, str, int | None]] = []
            for a in raw_attempts:
                try:
                    pos = int(a.get("position"))
                except (TypeError, ValueError):
                    continue
                qid = qid_by_pos.get(pos)
                if qid is None:
                    continue
                ans = (a.get("answer") or "").strip()
                if not ans:
                    continue  # skip blank answers
                ts = _parse_time_spent(a.get("time_spent_seconds"))
                jobs.append((pos, qid, ans, ts))

            results: dict[int, dict] = {}
            with ThreadPoolExecutor(max_workers=4) as ex:
                futures = {ex.submit(grade_answer, qid, ans): (pos, qid, ans, ts) for (pos, qid, ans, ts) in jobs}
                for fut in futures:
                    pos, qid, ans, ts = futures[fut]
                    try:
                        result = fut.result()
                    except Exception as ge:
                        results[pos] = {"error": str(ge)}
                        continue
                    record_attempt(
                        question_id=qid,
                        session_id=session_id,
                        position=pos,
                        user_answer=ans,
                        grade_result=result,
                        time_spent_seconds=ts,
                    )
                    results[pos] = result

            with connect() as conn:
                conn.execute(
                    "UPDATE sessions SET completed_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (session_id,),
                )
                conn.commit()

            total_awarded = sum(r.get("marks_awarded", 0) for r in results.values() if "marks_awarded" in r)
            total_possible = sum(r.get("total_marks", 0) for r in results.values() if "total_marks" in r)
            self._send_json({
                "ok": True,
                "session_id": session_id,
                "total_awarded": total_awarded,
                "total_possible": total_possible,
                "graded_count": sum(1 for r in results.values() if "marks_awarded" in r),
            })
        except Exception as e:
            self._send_json({"ok": False, "error": str(e)})

    def _handle_notebook(self, qs: dict):
        try:
            requested = qs.get("subject", [None])[0]
            if requested is not None:
                try:
                    requested = int(requested)
                except ValueError:
                    requested = None
            subject_id = self._resolve_subject_id(requested)
            subjects = _get_subjects()
            if subject_id is None or not subjects:
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(_error_html("No subjects found.").encode())
                return
            subject = next((s for s in subjects if s["id"] == subject_id), subjects[0])
            with connect() as conn:
                entries = notebook_html.fetch_entries(conn, subject_id)
            page = notebook_html.render(subject["name"], subject_id, subjects, entries)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(page.encode())
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(_error_html(f"Notebook error: {e}").encode())

    def _handle_study_submit_stream(self):
        """Stream the grader's output as Server-Sent Events.
        Body: {session_id, position, answer, time_spent_seconds?}."""
        try:
            data = self._read_json()
            session_id = data.get("session_id")
            position = data.get("position")
            answer = data.get("answer", "").strip()
            time_spent = _parse_time_spent(data.get("time_spent_seconds"))
            if session_id is None or position is None:
                self._send_json({"ok": False, "error": "Missing session_id or position"})
                return
            with connect() as conn:
                row = conn.execute(
                    "SELECT question_id FROM session_questions WHERE session_id = ? AND position = ?",
                    (session_id, position),
                ).fetchone()
            if not row:
                self._send_json({"ok": False, "error": "Question not found in session"})
                return
            question_id = row["question_id"]
        except Exception as e:
            self._send_json({"ok": False, "error": str(e)})
            return

        # Switch to SSE response mode
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        def emit(obj):
            self.wfile.write(f"data: {json.dumps(obj)}\n\n".encode())
            self.wfile.flush()

        try:
            final_result = None
            for ev in grade_answer_stream(question_id, answer):
                if "delta" in ev:
                    emit({"type": "delta", "text": ev["delta"]})
                elif "final" in ev:
                    final_result = ev["final"]
            if final_result is None:
                emit({"type": "error", "message": "No grade produced"})
                return
            record_attempt(
                question_id=question_id,
                session_id=session_id,
                position=position,
                user_answer=answer,
                grade_result=final_result,
                time_spent_seconds=time_spent,
            )
            emit({"type": "final", **final_result})
        except Exception as e:
            try:
                emit({"type": "error", "message": str(e)})
            except Exception:
                pass

    def _handle_study_consolidate(self):
        try:
            data = self._read_json()
            session_id = data.get("session_id")
            position = data.get("position")
            note = data.get("note", "")
            if session_id is None or position is None:
                self._send_json({"ok": False, "error": "Missing session_id or position"})
                return
            with connect() as conn:
                conn.execute(
                    "UPDATE session_questions SET consolidation = ? "
                    "WHERE session_id = ? AND position = ?",
                    (note, session_id, position),
                )
                conn.commit()
            self._send_json({"ok": True})
        except Exception as e:
            self._send_json({"ok": False, "error": str(e)})

    def _handle_study_flag(self):
        try:
            data = self._read_json()
            question_id = data.get("question_id")
            reason = (data.get("reason") or "").strip()
            flagged = 1 if data.get("flagged", True) else 0
            if question_id is None:
                self._send_json({"ok": False, "error": "Missing question_id"})
                return
            with connect() as conn:
                conn.execute(
                    "UPDATE questions SET flagged = ?, flag_reason = ? WHERE id = ?",
                    (flagged, reason or None, question_id),
                )
                conn.commit()
            self._send_json({"ok": True})
        except Exception as e:
            self._send_json({"ok": False, "error": str(e)})

    def _handle_study_discard(self):
        try:
            data = self._read_json()
            session_id = data.get("session_id")
            if session_id is None:
                self._send_json({"ok": False, "error": "Missing session_id"})
                return
            with connect() as conn:
                conn.execute(
                    "UPDATE sessions SET completed_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (session_id,),
                )
                conn.commit()
            self._send_json({"ok": True})
        except Exception as e:
            self._send_json({"ok": False, "error": str(e)})

    def _handle_study_complete(self, qs: dict):
        try:
            session_id = qs.get("session_id", [None])[0]
            if not session_id:
                self._send_json({"ok": False, "error": "Missing session_id"})
                return
            session_id = int(session_id)
            with connect() as conn:
                # Mark session completed
                conn.execute(
                    "UPDATE sessions SET completed_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (session_id,),
                )
                # Fetch all attempts for this session in original session order
                rows = conn.execute(
                    """
                    SELECT a.question_id, a.user_answer, a.marks_awarded, a.total_marks,
                           a.sm2_grade, a.feedback, sq.position, sq.consolidation,
                           q.text, q.markscheme, q.qnum, q.source, q.figure
                    FROM session_questions sq
                    JOIN attempts a ON a.id = sq.attempt_id
                    JOIN questions q ON q.id = sq.question_id
                    WHERE sq.session_id = ?
                    ORDER BY sq.position
                    """,
                    (session_id,),
                ).fetchall()
            attempts = []
            for r in rows:
                attempts.append({
                    "question_id": r["question_id"],
                    "position": r["position"],
                    "text": r["text"],
                    "user_answer": r["user_answer"],
                    "marks_awarded": r["marks_awarded"],
                    "total_marks": r["total_marks"],
                    "sm2_grade": r["sm2_grade"],
                    "feedback": r["feedback"],
                    "markscheme": r["markscheme"] or "",
                    "qnum": r["qnum"] or "",
                    "source": r["source"],
                    "consolidation": r["consolidation"] or "",
                    "figure": json.loads(r["figure"]) if r["figure"] else None,
                })
            self._send_json({"ok": True, "attempts": attempts})
        except Exception as e:
            self._send_json({"ok": False, "error": str(e)})

    def log_message(self, format, *args):
        pass


def start_server(port: int = PORT):
    migrate()
    server = ThreadingHTTPServer(("127.0.0.1", port), DashboardHandler)
    server.daemon_threads = True
    print(f"PhysicsBot Dashboard running at http://localhost:{port}")
    print(f"Database: {config.DB_PATH}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
        server.server_close()


if __name__ == "__main__":
    start_server()
