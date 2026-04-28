"""Extract a hierarchical topic tree from a specification PDF."""
from __future__ import annotations

from pathlib import Path

from . import llm
from .db import connect, upsert_subject

TOPIC_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "topics": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "code": {"type": "string", "description": "Hierarchical code, e.g. '3.1.2'"},
                    "title": {"type": "string"},
                    "parent_code": {"type": ["string", "null"], "description": "Parent code, or null for top-level"},
                    "depth": {"type": "integer", "description": "0 for top-level module, 1 for subsection, 2 for learning point, etc."},
                    "content": {"type": "string", "description": "Verbatim or condensed learning objectives. Empty for parent-only nodes."},
                },
                "required": ["code", "title", "parent_code", "depth", "content"],
            },
        }
    },
    "required": ["topics"],
}


SYSTEM = """You are extracting an A-Level specification into a structured topic tree.

Rules:
- Walk the specification's content section in order.
- Use the spec's own numbering scheme as the `code` field (e.g. "3.1.2", "1.A", "P1").
- Set `parent_code` to the immediate parent's code (or null for top-level modules).
- `depth` starts at 0 for top-level modules and increments per nesting level.
- For leaf learning objectives, copy the objective text into `content`. For parent nodes, leave `content` empty.
- Be exhaustive: include every leaf learning objective. Do not skip practical / mathematical / data-handling sections.
- Do not invent codes. If the spec uses unnumbered headings, fabricate a stable kebab-case code (e.g. "practical-skills/uncertainties").
"""


def extract(subject_name: str, board: str, spec_pdf: Path) -> int:
    spec_pdf = Path(spec_pdf)
    if not spec_pdf.exists():
        raise FileNotFoundError(spec_pdf)

    print(f"Uploading spec: {spec_pdf.name}")
    file_id = llm.upload_pdf(spec_pdf)

    print("Asking Claude to extract topic tree (this may take a minute)...")
    result = llm.call_json(
        system=SYSTEM,
        user_blocks=[
            llm.doc_block(file_id, cache=True),
            llm.text_block(
                "Extract the full topic tree from this specification. "
                "Return every learning objective as a leaf node."
            ),
        ],
        schema=TOPIC_SCHEMA,
        max_tokens=32000,
    )

    topics = result["topics"]
    print(f"Extracted {len(topics)} topics. Inserting into db...")

    with connect() as conn:
        subject_id = upsert_subject(conn, subject_name, board, str(spec_pdf))
        conn.execute("UPDATE subjects SET spec_file_id = ? WHERE id = ?", (file_id, subject_id))
        # Clear existing topics for this subject to allow re-extraction
        conn.execute("DELETE FROM topics WHERE subject_id = ?", (subject_id,))

        # Two-pass: insert all, then resolve parent_id by code
        code_to_id: dict[str, int] = {}
        for t in topics:
            cur = conn.execute(
                "INSERT INTO topics(subject_id, code, title, depth, content) VALUES(?,?,?,?,?)",
                (subject_id, t["code"], t["title"], t["depth"], t["content"]),
            )
            code_to_id[t["code"]] = cur.lastrowid
        for t in topics:
            if t["parent_code"]:
                parent_id = code_to_id.get(t["parent_code"])
                if parent_id:
                    conn.execute(
                        "UPDATE topics SET parent_id = ? WHERE id = ?",
                        (parent_id, code_to_id[t["code"]]),
                    )

        # Initialize mastery rows for leaf topics (those with content)
        leaf_codes = [t["code"] for t in topics if t["content"].strip()]
        for code in leaf_codes:
            conn.execute(
                "INSERT OR IGNORE INTO mastery(topic_id) VALUES(?)",
                (code_to_id[code],),
            )

        conn.commit()

    print(f"Done. {len(leaf_codes)} leaf topics ready for study.")
    return subject_id
