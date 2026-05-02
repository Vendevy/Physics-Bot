"""Extract a hierarchical topic tree from a specification PDF."""
from __future__ import annotations

from pathlib import Path

from . import gemini
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
- Be concise: shorten content to key phrases only, not full sentences. Example: "Derive SUVAT equations" not "Students should be able to derive the equations of motion for constant acceleration".
"""


def extract(subject_name: str, board: str, spec_pdf: Path) -> int:
    spec_pdf = Path(spec_pdf)
    if not spec_pdf.exists():
        raise FileNotFoundError(spec_pdf)

    print(f"Using Gemini to extract topic tree from: {spec_pdf.name}")
    
    # Pass 1: Extract top-level structure only
    print("  Pass 1: Extracting top-level modules...")
    result = gemini.call_json(
        system=SYSTEM,
        user_text=(
            "Extract ONLY the top-level modules (depth 0) from this specification. "
            "Return their codes and titles only, no sub-topics. "
            "Set parent_code to null for all of them."
        ),
        files=[spec_pdf],
        schema=TOPIC_SCHEMA,
        max_tokens=65536,
    )
    
    all_topics = result["topics"]
    top_level_codes = [t["code"] for t in all_topics if t["depth"] == 0]
    print(f"  Found {len(top_level_codes)} top-level modules.")
    
    # Pass 2: Extract sub-topics for each module
    for module_code in top_level_codes:
        print(f"  Pass 2: Extracting sub-topics for {module_code}...")
        result = gemini.call_json(
            system=SYSTEM,
            user_text=(
                f"Extract the full topic tree for module {module_code} ONLY from this specification. "
                "Return all learning objectives as leaf nodes. "
                "Keep content fields SHORT - just key phrases, not full sentences."
            ),
            files=[spec_pdf],
            schema=TOPIC_SCHEMA,
            max_tokens=65536,
        )
        all_topics.extend(result["topics"])
    
    # Deduplicate by code, keeping first occurrence
    seen_codes = set()
    topics = []
    for t in all_topics:
        if t["code"] not in seen_codes:
            seen_codes.add(t["code"])
            topics.append(t)
    
    print(f"Extracted {len(topics)} unique topics. Inserting into db...")

    with connect() as conn:
        subject_id = upsert_subject(conn, subject_name, board, str(spec_pdf))
        conn.execute("UPDATE subjects SET spec_file_id = ? WHERE id = ?", ("gemini-extracted", subject_id))
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
