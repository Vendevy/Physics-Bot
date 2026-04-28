"""Notebook page: surface persisted consolidation notes grouped by topic.

Rendered server-side from dashboard.py.
"""
from __future__ import annotations

import html
import sqlite3


def _md_to_html(text: str) -> str:
    """Tiny markdown subset for consolidation notes: bold, italic, code, paragraphs."""
    if not text:
        return ""
    s = html.escape(text)
    import re
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"\*(.+?)\*", r"<em>\1</em>", s)
    s = re.sub(
        r"`(.+?)`",
        r'<code style="background:rgba(255,255,255,0.06);padding:1px 5px;border-radius:4px;font-family:monospace;font-size:12px;">\1</code>',
        s,
    )
    paras = [p for p in re.split(r"\n{2,}", s) if p.strip()]
    return "".join(f"<p>{p.replace(chr(10), '<br>')}</p>" for p in paras)


def _excerpt(text: str, n: int = 220) -> str:
    text = (text or "").strip().replace("\n", " ")
    if len(text) <= n:
        return text
    return text[:n].rstrip() + "…"


def fetch_entries(conn: sqlite3.Connection, subject_id: int) -> list[dict]:
    """Return all consolidation notes for the subject with their question + topic context."""
    rows = conn.execute(
        """
        SELECT
            sq.consolidation,
            a.answered_at, a.user_answer, a.marks_awarded, a.total_marks,
            q.id AS qid, q.text AS qtext, q.qnum, q.source,
            (
                SELECT GROUP_CONCAT(t.code || ' ' || t.title, ' | ')
                FROM question_topics qt JOIN topics t ON t.id = qt.topic_id
                WHERE qt.question_id = q.id
            ) AS topic_label,
            (
                SELECT t.code FROM question_topics qt JOIN topics t ON t.id = qt.topic_id
                WHERE qt.question_id = q.id ORDER BY t.code LIMIT 1
            ) AS first_topic_code,
            (
                SELECT t.title FROM question_topics qt JOIN topics t ON t.id = qt.topic_id
                WHERE qt.question_id = q.id ORDER BY t.code LIMIT 1
            ) AS first_topic_title
        FROM session_questions sq
        JOIN sessions s ON s.id = sq.session_id
        JOIN questions q ON q.id = sq.question_id
        LEFT JOIN attempts a ON a.id = sq.attempt_id
        WHERE s.subject_id = ?
          AND COALESCE(sq.consolidation, '') != ''
        ORDER BY first_topic_code, a.answered_at DESC
        """,
        (subject_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def render(subject_name: str, subject_id: int, subjects: list[dict], entries: list[dict]) -> str:
    # Group by first topic code
    groups: dict[tuple[str, str], list[dict]] = {}
    for e in entries:
        key = (e.get("first_topic_code") or "—", e.get("first_topic_title") or "Other")
        groups.setdefault(key, []).append(e)

    subject_options = "".join(
        f'<option value="{s["id"]}"{" selected" if s["id"] == subject_id else ""}>{html.escape(s["name"])}</option>'
        for s in subjects
    )

    if not entries:
        body = """
        <div class="empty-state">
            <h2>No notes yet</h2>
            <p>After each study session, the consolidation notes you write in the review modal land here, grouped by topic.</p>
        </div>
        """
    else:
        groups_html = []
        for (code, title), items in groups.items():
            cards = []
            for e in items:
                pct = (e["marks_awarded"] / e["total_marks"] * 100) if e.get("total_marks") else 0
                if pct >= 80:
                    chip_color = "#22c55e"
                elif pct >= 50:
                    chip_color = "#eab308"
                else:
                    chip_color = "#ef4444"
                marks_chip = (
                    f'<span class="note-marks" style="color:{chip_color}">'
                    f'{e["marks_awarded"]}/{e["total_marks"]}</span>'
                    if e.get("total_marks") is not None else ""
                )
                date = (e.get("answered_at") or "")[:16]
                qsource = e.get("source") or ""
                qnum = e.get("qnum") or ""
                source_chip = (
                    f'<span class="note-source">{html.escape(qsource)} {html.escape(qnum)}</span>'
                    if qsource else ""
                )
                cards.append(f"""
                    <div class="note-card">
                        <div class="note-meta">
                            {marks_chip}
                            {source_chip}
                            <span class="note-date">{html.escape(date)}</span>
                        </div>
                        <details class="note-question">
                            <summary>Question</summary>
                            <div class="note-question-body">{html.escape(_excerpt(e.get('qtext'), 600))}</div>
                        </details>
                        <div class="note-body">{_md_to_html(e['consolidation'])}</div>
                    </div>
                """)
            groups_html.append(f"""
                <div class="topic-block">
                    <div class="topic-header">
                        <span class="topic-code">{html.escape(code)}</span>
                        <span class="topic-title">{html.escape(title)}</span>
                        <span class="topic-count">{len(items)} note{'' if len(items) == 1 else 's'}</span>
                    </div>
                    <div class="topic-notes">{''.join(cards)}</div>
                </div>
            """)
        body = "".join(groups_html)

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Notebook — PhysicsBot</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
*, *::before, *::after {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
    font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;
    background:#0a0a0a; color:#e4e4e7; min-height:100vh; line-height:1.55;
    -webkit-font-smoothing:antialiased;
}}
.header {{
    position:sticky; top:0; z-index:50;
    background:rgba(10,10,10,0.85); backdrop-filter:blur(12px);
    border-bottom:1px solid rgba(255,255,255,0.06);
}}
.header-inner {{
    max-width:900px; margin:0 auto; padding:16px 24px;
    display:flex; align-items:center; justify-content:space-between; gap:12px;
}}
.header-left h1 {{ font-size:16px; font-weight:600; letter-spacing:-0.01em; }}
.header-left p {{ font-size:13px; color:#52525b; margin-top:2px; }}
.header-actions {{ display:flex; gap:8px; align-items:center; }}
.subject-select {{
    background:#18181b; border:1px solid rgba(255,255,255,0.06);
    color:#a1a1aa; padding:8px 12px; border-radius:8px;
    font-family:inherit; font-size:13px; cursor:pointer; outline:none;
}}
.btn {{
    display:inline-flex; align-items:center; gap:6px;
    padding:8px 16px; border-radius:8px;
    border:1px solid rgba(255,255,255,0.06);
    font-family:inherit; font-size:13px; font-weight:500; cursor:pointer;
    background:#18181b; color:#a1a1aa; text-decoration:none;
    transition:background 0.2s, border-color 0.2s, color 0.2s;
}}
.btn:hover {{ background:#27272a; border-color:rgba(255,255,255,0.1); color:#e4e4e7; }}
.container {{ max-width:900px; margin:0 auto; padding:32px 24px 80px; }}
.empty-state {{ text-align:center; padding:64px 24px; color:#52525b; }}
.empty-state h2 {{ font-size:20px; font-weight:600; color:#e4e4e7; margin-bottom:10px; }}
.empty-state p {{ font-size:14px; line-height:1.6; max-width:480px; margin:0 auto; }}
.topic-block {{
    margin-bottom:32px;
}}
.topic-header {{
    display:flex; align-items:baseline; gap:10px; flex-wrap:wrap;
    padding-bottom:10px;
    border-bottom:1px solid rgba(255,255,255,0.06);
    margin-bottom:14px;
}}
.topic-code {{
    font-family:'SF Mono','Fira Code',monospace; font-size:11px;
    color:#71717a; background:rgba(255,255,255,0.04);
    padding:2px 8px; border-radius:5px;
}}
.topic-title {{ font-size:14px; font-weight:600; color:#e4e4e7; flex:1; }}
.topic-count {{
    font-size:11px; color:#52525b; font-weight:500;
    text-transform:uppercase; letter-spacing:0.05em;
}}
.topic-notes {{ display:flex; flex-direction:column; gap:10px; }}
.note-card {{
    background:rgba(255,255,255,0.02);
    border:1px solid rgba(255,255,255,0.06);
    border-left:3px solid rgba(99,102,241,0.5);
    border-radius:10px; padding:14px 16px;
}}
.note-meta {{
    display:flex; align-items:center; gap:10px; flex-wrap:wrap;
    margin-bottom:10px;
}}
.note-marks {{
    font-size:13px; font-weight:600; font-variant-numeric:tabular-nums;
}}
.note-source {{
    font-size:11px; font-weight:600; text-transform:uppercase;
    letter-spacing:0.05em; color:#52525b;
    background:rgba(255,255,255,0.04); padding:2px 8px; border-radius:4px;
}}
.note-date {{
    font-size:11px; color:#3f3f46; font-variant-numeric:tabular-nums;
    margin-left:auto;
}}
.note-question {{ margin-bottom:10px; }}
.note-question summary {{
    font-size:11px; color:#52525b; cursor:pointer; user-select:none;
    text-transform:uppercase; letter-spacing:0.05em; font-weight:600;
}}
.note-question summary::-webkit-details-marker {{ display:none; }}
.note-question summary::before {{ content:"▶ "; font-size:9px; }}
.note-question[open] summary::before {{ content:"▼ "; }}
.note-question-body {{
    font-size:12px; color:#71717a; line-height:1.6;
    margin-top:8px; padding:10px 12px;
    background:rgba(255,255,255,0.02); border-radius:6px;
}}
.note-body {{
    font-size:13px; color:#d4d4d8; line-height:1.7;
}}
.note-body p {{ margin-bottom:8px; }}
.note-body p:last-child {{ margin-bottom:0; }}
@media (max-width: 720px) {{
    .container {{ padding:20px 16px 48px; }}
    .header-inner {{ padding:12px 16px; }}
}}
</style>
</head><body>
<div class="header">
    <div class="header-inner">
        <div class="header-left">
            <h1>Notebook</h1>
            <p>{html.escape(subject_name)}</p>
        </div>
        <div class="header-actions">
            <select class="subject-select" onchange="location.href='/notebook?subject='+this.value">{subject_options}</select>
            <a href="/?subject={subject_id}" class="btn">Dashboard</a>
            <a href="/study?subject={subject_id}" class="btn">Study</a>
        </div>
    </div>
</div>
<div class="container">{body}</div>
</body></html>"""
