"""Build the daily set: 7 new generated questions + 3 spaced-recall past-paper questions."""
from __future__ import annotations

import json
import os
import random
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from . import llm
from . import llm_openai
from . import llm_claude_cli
from .config import (
    DAILY_NEW, DAILY_RECALL, GEN_PROVIDER, GEN_MODEL, VALIDATE_MODEL,
    ERROR_BOOST_WINDOW_DAYS, ERROR_BOOST_GRADE_MAX, ERROR_BOOST_PER_ERROR, ERROR_BOOST_CAP,
)
from .db import connect
from .srs import today_iso

# Lean version for CLI provider: strips verbose field descriptions to save tokens.
# The system prompt already explains the format; descriptions are redundant overhead.
GEN_SCHEMA_LEAN = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "text": {"type": "string"},
        "marks": {"type": "integer"},
        "markscheme": {"type": "string"},
        "scenario": {"type": "string"},
        "figure": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "type": {"type": "string", "enum": ["line", "scatter", "bar", "svg"]},
                "title": {"type": "string"},
                "xlabel": {"type": "string"},
                "ylabel": {"type": "string"},
                "x": {"type": "array", "items": {"type": "number"}},
                "series": {
                    "type": "array", "minItems": 1,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {"name": {"type": "string"}, "y": {"type": "array", "items": {"type": "number"}}},
                        "required": ["name", "y"],
                    },
                },
                "svg": {"type": "string"},
            },
            "required": ["type", "title"],
        },
    },
    "required": ["text", "marks", "markscheme", "scenario"],
}

GEN_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "text": {"type": "string", "description": "The question, in A-Level paper style. Include any required given values, and use Unicode/$...$ for math."},
        "marks": {"type": "integer", "description": "Total marks (typically 2-8)."},
        "markscheme": {"type": "string", "description": "Marking points with marks (M1/A1/B1 style) and acceptable alternatives. All mathematical expressions, equations, symbols, and variables must be in LaTeX using $...$ for inline math. Examples: $F=ma$, $\\Delta E = mc^2$, $v = u + at$, $3.2 \\times 10^{-19}\\,\\mathrm{C}$. For multi-part questions, the markscheme MUST be structured with the question part (including its text) above the marks for that part, so the reader can see which question each marking point belongs to. Example format:\n\n(a) Calculate the maximum speed of the cart. [2]\nM1: use of $E_k = \\frac{1}{2}mv^2$\nA1: $v = 4.7\\,\\mathrm{m\\,s^{-1}}$\n\n(b)(i) Explain why the speed decreases. [3]\nB1: reference to work done against friction\nB1: $E_k$ is converted to thermal energy\nB1: net force decelerates the cart\n\nDo NOT write the markscheme as a single undifferentiated block."},
        "scenario": {"type": "string", "description": "1-4 kebab-case words naming the physical scenario, e.g. 'skydiver-terminal-velocity', 'copper-tube-magnet-brake', 'loop-the-loop-min-speed'. Used to dedupe future generations."},
        "figure": {
            "type": "object",
            "additionalProperties": False,
            "description": (
                "Graph data or SVG diagram shown beside the question. Omit this field entirely when no visual is needed. "
                "For graphs (line/scatter/bar), provide chart data. "
                "For diagrams (circuits, force diagrams, ray diagrams, free-body diagrams, experimental setups), "
                "provide an inline SVG in the 'svg' field. The SVG must:\n"
                "- Be a complete, self-contained <svg> element with viewBox\n"
                "- Be no wider than 600px and no taller than 400px\n"
                "- Use LIGHT-coloured strokes (white #e4e4e7, light grey #a1a1aa) on a transparent background so the diagram is visible on a dark UI. Do NOT use black or dark grey strokes.\n"
                "- Include readable labels in a sans-serif font\n"
                "- Use standard conventions (e.g. circuit symbols, arrowheads, dashed lines for virtual images)\n"
                "Never include a figure if the question asks the student to plot, sketch, or draw something themselves."
            ),
            "properties": {
                "type": {"type": "string", "enum": ["line", "scatter", "bar", "svg"]},
                "title": {"type": "string"},
                "xlabel": {"type": "string"},
                "ylabel": {"type": "string"},
                "x": {"type": "array", "items": {"type": "number"}},
                "series": {
                    "type": "array", "minItems": 1,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {"name": {"type": "string"}, "y": {"type": "array", "items": {"type": "number"}}},
                        "required": ["name", "y"]
                    }
                },
                "svg": {"type": "string", "description": "Complete inline SVG element for the diagram."}
            },
            "required": ["type", "title"]
        }
    },
    "required": ["text", "marks", "markscheme", "scenario"],
}

VALIDATE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "pass": {"type": "boolean", "description": "Whether the question is correct, solvable, and self-consistent"},
        "issues": {"type": "string", "description": "Comma-separated list of issues found, or 'none' if passing"},
        "corrected_markscheme": {"type": "string", "description": "Corrected markscheme if there were issues, empty string if passing or no correction needed"},
    },
    "required": ["pass", "issues", "corrected_markscheme"],
}

VALIDATE_SYSTEM = """You are an A-Level examiner verifying a practice question for correctness before it is given to a student.

Check the following:
1. SOLVABILITY — Can the question be answered using ONLY the information given and knowledge from the specification? No missing values, no unstated assumptions.
2. TOPIC MATCH — Does the question actually exercise the spec content for the tagged topic code? If the question is solvable but tests a different topic, flag this in `issues` with the prefix 'topic-mistag:' so the caller can distinguish it from mathematical errors.
3. CONSISTENCY — Are all given values self-consistent? (e.g. if V=12 V and R=4 Ω are both given, I must equal 3 A by Ohm's law; if they conflict, flag it.)
4. MARKSCHEME ACCURACY — Does the markscheme correctly solve the question as stated? Do the marking points (M1, A1, B1) add up to the total marks? Does the final answer match the given values?
5. COMPLETENESS — Are all sub-parts of the question addressed in the markscheme?
6. FIGURES — If a figure is provided, does the question text reference it and are the data realistic? For SVG diagrams, are the physics and conventions correct (correct circuit symbols, ray directions, force vectors, etc.)?
7. LATEX FORMATTING — Are all mathematical expressions, equations, and symbols in the markscheme wrapped in $...$ LaTeX? There should be no bare Unicode math symbols (like ², ⁻¹, ×, →) outside of LaTeX delimiters.

Be lenient — only flag genuine errors that would prevent a student from answering correctly or make the markscheme wrong. Minor phrasing issues or alternative valid wordings are acceptable."""

DIFFICULTY_LABELS = {
    3: "Standard A-Level",
    4: "Difficult A-Level",
    5: "Very Difficult A-Level",
    6: "Extremely Difficult A-Level",
}

DIFFICULTY_BLURBS = {
    3: (
        "Standard A-Level difficulty — match the average difficulty of the official "
        "exam paper. Most marks are accessible to a confident A-Level student."
    ),
    4: (
        "Difficult A-Level — pitch this at the harder questions in an exam paper "
        "(extended-response / Section B style), around the 70th-percentile of exam "
        "difficulty. Pick EXACTLY ONE conceptual move from the menu below and build "
        "the question around it; the question should have at least one stretching "
        "part that goes beyond a textbook plug-and-chug calculation."
    ),
    5: (
        "Very Difficult A-Level — top 10% of exam-paper questions. COMBINE TWO "
        "conceptual moves from the menu below; at least one of the two MUST be "
        "qualitative or evaluative (not just longer arithmetic). Unfamiliar context "
        "is expected, but every required idea must already be in the spec."
    ),
    6: (
        "Extremely Difficult A-Level — stretch beyond a typical exam paper "
        "(BPhO / end-of-A-Level challenge level). COMBINE TWO OR THREE moves from "
        "the menu below; subtle traps are welcome. At least one part must require "
        "reasoning that cannot be reduced to plug-and-chug. STRICTLY within the "
        "published specification — do NOT introduce off-syllabus topics, methods, "
        "or notation. Hardness comes from depth of thinking, not from importing "
        "harder maths."
    ),
}

CONCEPTUAL_MOVES = """Conceptual-difficulty menu (pick from these — DO NOT invent off-syllabus moves):
- Synthesis: combine the given spec point with one adjacent spec point. Name the second concept explicitly in the question.
- Limiting-case reasoning: ask what happens as a quantity → 0 or → ∞, or when an idealisation (frictionless, ideal gas, in vacuum, point mass, no air resistance) is dropped.
- Qualitative-before-quantitative: the student must predict the DIRECTION of a change before any number is computed, then justify with an equation.
- Misconception trap: build the question around a known A-Level confusion (weight vs mass under acceleration; EMF vs PD under load; intensity vs amplitude; drift velocity vs signal speed; node-spacing vs wavelength; centripetal force as a separate force).
- Method evaluation: present a proposed experimental method or a student's reasoning and require the candidate to identify the flaw, a non-trivial source of uncertainty, or an improvement.
- Symbolic derivation before substitution: the answer must be obtained as an algebraic expression in given symbols first, then evaluated only at the end.
- Unfamiliar context, familiar physics: a non-textbook scenario (maglev brake, magnet falling through a copper tube, planet with non-Earth g, biomechanical lever, satellite refuelling) that maps cleanly onto one spec equation.
- Estimation with justification: Fermi-style; the student must state and defend an order-of-magnitude assumption.

Spec-bound: each chosen move must operate on the spec content given in the user message. Do NOT import equations, constants, identities, or notation that are not in the {board} {subject_name} specification. If a move would require off-syllabus tools to land, pick a different move."""


def _gen_system(subject_name: str, board: str, difficulty: int = 3) -> str:
    # NOTE: substring match is intentional; revisit if subjects like "Biophysics"
    # or "Mathematical Biology" are ever added.
    is_physics = "physics" in subject_name.lower()
    is_maths = "mathematics" in subject_name.lower()
    diff = difficulty if difficulty in DIFFICULTY_BLURBS else 3
    diff_blurb = DIFFICULTY_BLURBS[diff]

    spec_rules = []
    if is_physics:
        spec_rules.append(
            "Calculus is NOT in the A-Level Physics specification. NEVER use derivatives "
            "(dx/dt, d²x/dt², dy/dx notation), integrals (∫), limits, or differential "
            "equations in the question OR the markscheme. Express rates of change using "
            "gradients of graphs, ratios (Δv/Δt), or algebraic manipulation. 'Area under "
            "a graph' is fine; integral notation is not."
        )
    if is_maths:
        spec_rules.append(
            "The Edexcel Mathematical Formulae and Statistical Tables booklet is available "
            "in the exam. Do NOT ask students to derive or quote formulae that appear in "
            "the booklet as if they were unknown; treat them as available. The booklet "
            "covers: standard derivatives and integrals beyond x^n / sin / cos / e^x / "
            "ln x, the binomial series for rational n, sum formulae for arithmetic and "
            "geometric series, the trapezium rule, vector formulae, and the statistical "
            "distributions and tests. Core results that are NOT in the booklet (e.g. "
            "derivatives of x^n, sin x, cos x, e^x, ln x; integration by parts formula "
            "derivation; basic trig identities like sin²θ + cos²θ = 1) may legitimately "
            "be required to be recalled or proved."
        )
        spec_rules.append(
            "Exact-form answers are preferred where applicable. Accept and expect answers "
            "in surd form (e.g. 3√2), in terms of π, e, ln 2, etc., rather than decimal "
            "approximations, unless the question explicitly asks for a numerical value to "
            "a stated accuracy."
        )
        spec_rules.append(
            "Notation must be standard A-Level: use f'(x) and f''(x) or dy/dx and "
            "d²y/dx² for derivatives; ∫ ... dx for integrals; use proper limits on "
            "definite integrals; vectors in bold or with the i, j, k convention; column "
            "vectors where appropriate."
        )
    spec_rules.append(
        f"Stay strictly within the {board} {subject_name} specification. Do not "
        "introduce off-syllabus topics, equations, or notation."
    )
    spec_rules.append(
        "All mathematical expressions in the markscheme must use LaTeX: $...$ for "
        "inline math. For example: $E_k = \\frac{1}{2}mv^2$, $v = u + at$, "
        "$3.2 \\times 10^{-19}\\,\\mathrm{C}$. Never use Unicode approximations "
        "like ² or ⁻¹ in the markscheme — always use proper LaTeX."
    )
    spec_rules_block = "\n".join(f"- {r}" for r in spec_rules)

    moves_block = ""
    if diff >= 4:
        moves_block = "\n\n" + CONCEPTUAL_MOVES.format(board=board, subject_name=subject_name)

    if is_physics:
        svg_examples = (
            "a circuit diagram, free-body diagram, ray diagram (lenses/mirrors), "
            "force/moment diagram, experimental setup schematic, or any geometry-dependent scenario"
        )
    elif is_maths:
        svg_examples = (
            "graphs of functions y = f(x), labelled geometric figures "
            "(triangles, circles, polygons with vertices and angles labelled), "
            "coordinate axes with marked points, vector diagrams, or sketch axes "
            "for parametric curves"
        )
    else:
        svg_examples = "a diagram or geometry-dependent scenario relevant to the subject"

    return f"""You are an examiner for {subject_name} ({board}) generating a fresh practice question on a specific topic from the official specification.

CRITICAL — subject lock:
- EVERY question MUST be a {subject_name} question. Never produce a question from another subject (psychology, biology, chemistry outside of physics-chemistry crossover, etc.) even if the topic title sounds generic.
- Topics with generic-sounding titles ("Evaluation of experimental method", "Significant figures", "Mathematical skills for analysis", "Identification of variables", etc.) MUST still be framed inside a {subject_name} context. For physics, use a physics scenario such as mechanics, electricity, waves, materials, fields, thermodynamics, nuclear, quantum, or astrophysics. If the topic is about practical/experimental skills, base the experiment on a physics setup (resistance of a wire, refractive index, period of a pendulum, specific heat capacity, radioactive decay, Young's modulus, etc.).
- Use SI units, subject-appropriate quantities, and subject terminology throughout.

Specification rules:
{spec_rules_block}

Difficulty: {diff_blurb}
- The difficulty level above is the PRIMARY anchor for hardness. Use the student's per-topic mastery score (0=novice, 1=mastered) only for fine-tuning whether the question is more lead-in vs. more stretching within the chosen difficulty band.{moves_block}

Question rules:
- Match the style and structure of official {board} questions.
- If the question carries more than 4 marks, structure it as multi-part ((a), (b), (b)(i), (b)(ii), etc.) matching how {board} papers structure long questions, rather than one giant prose stem.
- Avoid reusing the canonical textbook scenario for this topic when a different real-world setup makes the same point.
- Include any data/values needed to solve it (don't write open-ended definition prompts).
- The markscheme must enumerate marking points with how each mark is awarded.
- For multi-part questions, the markscheme MUST repeat each question part (including its text) above the marking points for that part, so the reader can see which question each mark refers to. Do NOT write the markscheme as a single undifferentiated block.
- Total marks should reflect the depth of the question.

Scenario tag:
- The `scenario` field is a 1-4 kebab-case-word label naming the physical setup (e.g. "skydiver-terminal-velocity", "copper-tube-magnet-brake", "planet-with-different-g"). Make it specific enough that two questions on the same topic with different scenarios get different tags.

Figures:
- Omit the `figure` field when no visual aid is needed.
- Only provide a `figure` when the question genuinely benefits from one:
  * Graph (type: line/scatter/bar) — when the student must read values or trends from a graph.
  * SVG diagram (type: svg) — when the question involves {svg_examples}. The question text must reference the diagram explicitly (e.g. "In the diagram shown below...", "The diagram below shows...").
- Never include a `figure` for questions that ask the student to plot, sketch, or draw something themselves.
- For SVG diagrams: generate clean, accurate diagrams following standard physics conventions. Circuits use standard symbols. Force diagrams use arrow vectors. Ray diagrams show lenses/mirrors with principal axis, focal points, and ray paths. Use light-coloured strokes (white, light grey) so the diagram is clearly visible on a dark background — never use black or dark grey.
"""


MAX_VALIDATE_RETRIES = 2

_PLOT_SKETCH_RE = re.compile(
    r"\b(sketch|plot|draw|on\s+the\s+axes\s+below|on\s+the\s+grid)\b",
    re.IGNORECASE,
)


def pick_weakest_topics(subject_id: int, n: int) -> list[dict]:
    """n leaf topics with content, ordered by lowest (mastery - error_boost),
    so topics with recent repeated errors are prioritised over their mastery alone."""
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT t.id, t.code, t.title, t.content, m.score, m.last_reviewed,
                   COALESCE(ep.error_boost, 0.0) AS error_boost
            FROM topics t
            JOIN mastery m ON m.topic_id = t.id
            LEFT JOIN (
                SELECT qt.topic_id,
                       CASE
                           WHEN COUNT(*) * {ERROR_BOOST_PER_ERROR} < {ERROR_BOOST_CAP}
                           THEN COUNT(*) * {ERROR_BOOST_PER_ERROR}
                           ELSE {ERROR_BOOST_CAP}
                       END AS error_boost
                FROM attempts a
                JOIN question_topics qt ON qt.question_id = a.question_id
                WHERE a.answered_at >= date('now', '-{ERROR_BOOST_WINDOW_DAYS} days')
                  AND a.sm2_grade <= {ERROR_BOOST_GRADE_MAX}
                GROUP BY qt.topic_id
            ) ep ON ep.topic_id = t.id
            WHERE t.subject_id = ? AND COALESCE(t.content, '') != ''
            ORDER BY (m.score - COALESCE(ep.error_boost, 0.0)) ASC,
                     COALESCE(m.last_reviewed, '0') ASC, t.id ASC
            LIMIT ?
            """,
            (subject_id, n),
        ).fetchall()
        return [dict(r) for r in rows]


def pick_random_topics(subject_id: int, n: int) -> list[dict]:
    """n leaf topics with content, chosen uniformly at random."""
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT t.id, t.code, t.title, t.content,
                   COALESCE(m.score, 0.0) AS score, m.last_reviewed
            FROM topics t
            LEFT JOIN mastery m ON m.topic_id = t.id
            WHERE t.subject_id = ? AND COALESCE(t.content, '') != ''
            """,
            (subject_id,),
        ).fetchall()
    all_topics = [dict(r) for r in rows]
    return random.sample(all_topics, min(n, len(all_topics)))


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
    """Past-paper questions whose primary topic is due for review (next_review <= today).
    Prefers questions seen fewer times and with lower last-attempt scores to avoid
    re-serving questions the student has already mastered."""
    today = today_iso()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT q.id AS question_id, q.text, q.marks, q.markscheme, q.qnum,
                   t.id AS topic_id, t.code, t.title,
                   m.next_review, m.score,
                   (SELECT COUNT(*) FROM session_questions sq WHERE sq.question_id = q.id) AS times_seen,
                   (SELECT a.sm2_grade FROM attempts a
                    WHERE a.question_id = q.id ORDER BY a.id DESC LIMIT 1) AS last_grade
            FROM questions q
            JOIN question_topics qt ON qt.question_id = q.id
            JOIN topics t ON t.id = qt.topic_id
            JOIN mastery m ON m.topic_id = t.id
            WHERE q.subject_id = ? AND q.source = 'past_paper'
              AND m.next_review IS NOT NULL AND m.next_review <= ?
            GROUP BY q.id
            ORDER BY times_seen ASC, COALESCE(last_grade, 0) ASC, m.next_review ASC
            LIMIT ?
            """,
            (subject_id, today, n),
        ).fetchall()
        results = [dict(r) for r in rows]
        if len(results) < n:
            existing_ids = [r["question_id"] for r in results]
            placeholders = ",".join("?" * len(existing_ids)) if existing_ids else "NULL"
            extra_params = (subject_id, *existing_ids, n - len(results))
            extra = conn.execute(
                f"""
                SELECT q.id AS question_id, q.text, q.marks, q.markscheme, q.qnum,
                       t.id AS topic_id, t.code, t.title,
                       m.next_review, m.score,
                       (SELECT COUNT(*) FROM session_questions sq WHERE sq.question_id = q.id) AS times_seen,
                       (SELECT a.sm2_grade FROM attempts a
                        WHERE a.question_id = q.id ORDER BY a.id DESC LIMIT 1) AS last_grade
                FROM questions q
                JOIN question_topics qt ON qt.question_id = q.id
                JOIN topics t ON t.id = qt.topic_id
                JOIN mastery m ON m.topic_id = t.id
                WHERE q.subject_id = ? AND q.source = 'past_paper'
                  AND q.id NOT IN ({placeholders})
                ORDER BY m.score ASC, times_seen ASC, RANDOM()
                LIMIT ?
                """,
                extra_params,
            ).fetchall()
            results.extend(dict(r) for r in extra)
        return results


def _recent_for_topic(topic_id: int, n: int = 8) -> list[dict]:
    """Most recent generated questions on this topic — scenario tag + first 120 chars of text."""
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT q.scenario, substr(q.text, 1, 120) AS snippet
            FROM questions q
            JOIN question_topics qt ON qt.question_id = q.id
            WHERE qt.topic_id = ? AND q.source = 'generated'
            ORDER BY q.id DESC LIMIT ?
            """,
            (topic_id, n),
        ).fetchall()
        return [dict(r) for r in rows]


def _style_exemplar_for_topic(topic_id: int) -> str | None:
    """One random past-paper question text snippet on this topic, for style anchoring."""
    with connect() as conn:
        row = conn.execute(
            """
            SELECT substr(q.text, 1, 200) AS snippet
            FROM questions q
            JOIN question_topics qt ON qt.question_id = q.id
            WHERE qt.topic_id = ? AND q.source = 'past_paper'
            ORDER BY RANDOM() LIMIT 1
            """,
            (topic_id,),
        ).fetchone()
        return row["snippet"] if row else None


def _other_past_paper_snippets(topic_id: int, exemplar_prefix: str | None, n: int = 3) -> list[str]:
    """Short snippets of other past-paper questions on this topic (excluding the style exemplar)."""
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT substr(q.text, 1, 120) AS snippet
            FROM questions q
            JOIN question_topics qt ON qt.question_id = q.id
            WHERE qt.topic_id = ? AND q.source = 'past_paper'
            ORDER BY RANDOM() LIMIT ?
            """,
            (topic_id, n + 1),
        ).fetchall()
    results: list[str] = []
    excl = exemplar_prefix[:120] if exemplar_prefix else None
    for r in rows:
        s = r["snippet"]
        if excl and s == excl:
            continue
        results.append(s)
        if len(results) >= n:
            break
    return results


def _llm_json(
    *,
    system: str,
    user_text: str,
    schema: dict,
    model: str,
    max_tokens: int = 16000,
) -> Any:
    provider = os.environ.get("GEN_PROVIDER", GEN_PROVIDER)
    print(f"  [DEBUG] _llm_json: provider={provider}, model={model}")
    if provider == "deepseek":
        return llm_openai.call_json_openai(
            system=system, user_text=user_text, schema=schema,
            model=model, max_tokens=max_tokens,
        )
    elif provider == "claude-cli":
        return llm_claude_cli.call_json(
            system=system, user_text=user_text, schema=schema,
            model=model, max_tokens=max_tokens,
        )
    else:
        return llm.call_json(
            system=system,
            user_blocks=[llm.text_block(user_text)],
            schema=schema,
            model=model,
            max_tokens=max_tokens,
            cache_system=True,
        )


def _validate_question(q: dict, subject_name: str, board: str, topic_content: str,
                       topic_code: str = "", topic_title: str = "") -> dict:
    """Validate a generated question for solvability, consistency, and markscheme accuracy.
    Returns dict with keys: 'pass' (bool), 'issues' (str), 'corrected' (str|None)."""
    print(f"[DEBUG] _validate_question: marks={q.get('marks', '?')} model={VALIDATE_MODEL}")
    parts = [
        f"Subject: {subject_name} ({board})",
        f"Topic tag: {topic_code} — {topic_title}\nTopic spec: {topic_content}",
        f"Question ({q.get('marks', '?')} marks):\n{q.get('text', '')}",
        f"Markscheme:\n{q.get('markscheme', '')}",
    ]
    if q.get("figure"):
        parts.append(f"Figure data: {json.dumps(q['figure'])}")

    user_text = "\n\n".join(parts)
    max_tokens = 2000
    for attempt in range(3):
        try:
            _cur_provider = os.environ.get("GEN_PROVIDER", GEN_PROVIDER)
            if _cur_provider == "claude-cli":
                result = llm_claude_cli.call_json(
                    system=VALIDATE_SYSTEM,
                    user_text=user_text,
                    schema=VALIDATE_SCHEMA,
                    model=VALIDATE_MODEL,
                    max_tokens=max_tokens,
                )
            else:
                result = llm.call_json(
                    system=VALIDATE_SYSTEM,
                    user_blocks=[llm.text_block(user_text)],
                    schema=VALIDATE_SCHEMA,
                    cache_system=False,
                    model=VALIDATE_MODEL,
                    max_tokens=max_tokens,
                )
            break
        except Exception as e:
            if attempt < 2:
                max_tokens *= 2
                print(f"  [DEBUG] Validation failed (attempt {attempt + 1}), retrying with max_tokens={max_tokens}")
            else:
                raise
    return {
        "pass": bool(result.get("pass", False)),
        "issues": result.get("issues", ""),
        "corrected": result.get("corrected_markscheme"),
    }


def generate_question(
    topic: dict,
    *,
    subject_name: str,
    board: str,
    difficulty: int = 3,
    use_past_paper_style: bool = True,
    model: str | None = None,
) -> dict:
    """Generate one fresh question for a topic. Returns dict with text, marks, markscheme.

    `use_past_paper_style`: when True (default), inject one short past-paper snippet on
    the same topic as a style anchor (form-only). When False, generate purely from the
    spec content + do-not-repeat list, no past-paper anchoring.
    `model`: override the generation model; defaults to GEN_MODEL.
    """
    print(f"[DEBUG] generate_question: topic={topic.get('code')} model={model or GEN_MODEL}")
    score = topic.get("score", 0.0) or 0.0
    diff_label = DIFFICULTY_LABELS.get(difficulty, DIFFICULTY_LABELS[3])

    _provider = os.environ.get("GEN_PROVIDER", GEN_PROVIDER)
    # For CLI provider, truncate spec content to keep prompt lean.
    spec_content = topic["content"]
    if _provider == "claude-cli" and len(spec_content) > 600:
        spec_content = spec_content[:600] + "…"

    parts = [
        f"Subject: {subject_name} ({board})",
        f"Topic: {topic['code']} — {topic['title']}",
        f"Spec content: {spec_content}",
        f"Student's current mastery on this topic: {score:.2f}",
        f"Required difficulty level: {diff_label} (level {difficulty}).",
    ]

    recent = _recent_for_topic(topic["id"]) if topic.get("id") is not None else []
    if recent:
        bullets = []
        for r in recent:
            tag = r.get("scenario")
            snippet = (r.get("snippet") or "").replace("\n", " ").strip()
            if tag:
                bullets.append(f"- [{tag}] {snippet}")
            else:
                bullets.append(f"- {snippet}")
        parts.append(
            "Do NOT repeat any of these recent scenarios on this topic — pick a "
            "different physical setup, different numerical regime, and different "
            "question stem (calculate / explain / derive / evaluate / design):\n"
            + "\n".join(bullets)
        )

    exemplar = (
        _style_exemplar_for_topic(topic["id"])
        if use_past_paper_style and topic.get("id") is not None
        else None
    )
    if exemplar:
        exemplar_clean = exemplar.replace("\n", " ").strip()
        parts.append(
            "Style reference (form only — the student has already done this exact "
            "past-paper question, so match its register and mark-density but pick "
            "a FRESH scenario; do NOT reuse the numbers, objects, or sub-parts):\n"
            f"  {exemplar_clean}"
        )

    if topic.get("id") is not None:
        others = _other_past_paper_snippets(topic["id"], exemplar, n=3)
        if others:
            bullets = [f"- {s.replace(chr(10), ' ').strip()}" for s in others]
            parts.append(
                "For reference, students have also seen these past-paper questions on "
                "this topic — do NOT reuse their specific numerical values, named "
                "objects, or sub-part structure:\n" + "\n".join(bullets)
            )

    parts.append(
        f"Generate one {subject_name} practice question on this topic at the required "
        f"difficulty level. Remember: the question must be a {subject_name} question, "
        f"never from another subject."
    )
    user_text = "\n\n".join(parts)

    _provider = os.environ.get("GEN_PROVIDER", GEN_PROVIDER)
    _schema = GEN_SCHEMA_LEAN if _provider == "claude-cli" else GEN_SCHEMA
    return _llm_json(
        system=_gen_system(subject_name, board, difficulty),
        user_text=user_text,
        schema=_schema,
        model=model or GEN_MODEL,
        max_tokens=6000,
    )


def build_session(
    subject_id: int,
    *,
    topic_ids: list[int] | None = None,
    topic_mode: str = "weakest",
    n_new: int | None = None,
    difficulty: int = 3,
    use_past_paper_style: bool = True,
    validate: bool = True,
    progress_cb: Callable[[int, int, str], None] | None = None,
    max_workers: int = 4,
    gen_model: str | None = None,
) -> int:
    """Create a new session row, populate session_questions with new + recall.
    Generated questions are persisted into the questions table with source='generated'.

    If `topic_ids` is given, generate one question per topic (in that order, capped
    at `n_new`). Otherwise `topic_mode` controls auto-selection: 'weakest' (default)
    or 'random'.

    `n_new` overrides DAILY_NEW for this session; clamped to [1, 15].
    `difficulty` is 3..6 (Standard, Difficult, Very Difficult, Extremely Difficult).
    `validate` — when True, each generated question is checked by a validation call;
    if it fails, the question is regenerated (up to MAX_VALIDATE_RETRIES times).
    If the validation provides a corrected markscheme, the correction is applied.
    `gen_model` — override the generation model; defaults to GEN_MODEL from config.

    `progress_cb(done, total, label)` is called as each question finishes generating,
    so callers (e.g. the web UI) can stream status to the user.
    """
    gen_model = gen_model or GEN_MODEL
    provider = os.environ.get("GEN_PROVIDER", GEN_PROVIDER)
    print(f"[DEBUG] build_session start: subject_id={subject_id}, n_new={n_new}, difficulty={difficulty}, model={gen_model}, validate={validate}, provider={provider}")
    with connect() as conn:
        subject = conn.execute(
            "SELECT name, board FROM subjects WHERE id = ?", (subject_id,)
        ).fetchone()
    if not subject:
        raise RuntimeError(f"Subject id {subject_id} not found")
    subject_name = subject["name"]
    board = subject["board"]

    n_new_eff = max(1, min(15, n_new)) if n_new else DAILY_NEW
    difficulty = difficulty if difficulty in DIFFICULTY_LABELS else 3

    if topic_ids:
        weak = pick_topics_by_id(subject_id, topic_ids)[:n_new_eff]
    elif topic_mode == "random":
        weak = pick_random_topics(subject_id, n_new_eff)
    else:
        weak = pick_weakest_topics(subject_id, n_new_eff)
    recall = pick_due_for_recall(subject_id, DAILY_RECALL)

    if not weak:
        raise RuntimeError(
            "No topics found. Run `python -m studybot extract <subject>` first."
        )

    def _generate_one(topic: dict) -> dict:
        def _gen_with_required_fields() -> dict:
            # Guard against generator returning a dict missing required fields
            # (would crash the INSERT downstream). Regenerate if so.
            for gen_attempt in range(MAX_VALIDATE_RETRIES + 1):
                qg = generate_question(
                    topic,
                    subject_name=subject_name,
                    board=board,
                    difficulty=difficulty,
                    use_past_paper_style=use_past_paper_style,
                    model=gen_model,
                )
                missing = [k for k in ("text", "marks", "markscheme") if k not in qg]
                if not missing:
                    return qg
                print(
                    f"  [DEBUG] generated question missing {missing}"
                    f" (attempt {gen_attempt + 1}); regenerating"
                )
            # Last-resort fallback so the session can still be built.
            qg.setdefault("text", "")
            qg.setdefault("marks", 1)
            qg.setdefault("markscheme", "")
            return qg

        q = _gen_with_required_fields()
        if q.get("figure") is not None and _PLOT_SKETCH_RE.search(q.get("text", "")):
            fig = q["figure"]
            is_data_chart = (
                fig.get("type") in ("line", "scatter", "bar") and bool(fig.get("series"))
            )
            if not is_data_chart:
                print(f"[DEBUG] Dropped figure on plot/sketch question (topic={topic.get('code', '?')})")
                q["figure"] = None
        if not validate:
            return q
        for attempt in range(MAX_VALIDATE_RETRIES + 1):
            v = _validate_question(q, subject_name, board, topic.get("content", ""),
                                   topic.get("code", ""), topic.get("title", ""))
            if v["pass"]:
                return q
            is_mistag = v["issues"].startswith("topic-mistag:")
            if v["corrected"] and not is_mistag:
                q["markscheme"] = v["corrected"]
                return q
            if attempt < MAX_VALIDATE_RETRIES:
                print(f"    Validation failed (attempt {attempt + 1}): {v['issues']}")
                q = generate_question(
                    topic,
                    subject_name=subject_name,
                    board=board,
                    difficulty=difficulty,
                    use_past_paper_style=use_past_paper_style,
                    model=gen_model,
                )
            else:
                print(f"    Using unvalidated question after {MAX_VALIDATE_RETRIES + 1} attempts")
        return q

    _mode_label = "random topics" if (not topic_ids and topic_mode == "random") else "weakest topics" if not topic_ids else "selected topics"
    print(f"Generating {len(weak)} new questions on {_mode_label}...")
    total = len(weak)
    generated_map: dict[int, tuple[dict, dict]] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {
            ex.submit(_generate_one, t): (i, t)
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
                "INSERT INTO questions(subject_id, source, text, marks, markscheme, figure, scenario) "
                "VALUES(?, 'generated', ?, ?, ?, ?, ?) RETURNING id",
                (subject_id, q["text"], q["marks"], q["markscheme"], fig_json, q.get("scenario")),
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


def build_mock_session(subject_id: int, paper_id: int) -> int:
    """Create a mock-paper session: every question from the chosen past paper, in order."""
    with connect() as conn:
        paper = conn.execute(
            "SELECT id, label FROM papers WHERE id = ? AND subject_id = ?",
            (paper_id, subject_id),
        ).fetchone()
        if not paper:
            raise RuntimeError(f"Paper {paper_id} not found for subject {subject_id}")
        questions = conn.execute(
            """
            SELECT id, qnum FROM questions
            WHERE paper_id = ? AND subject_id = ?
            ORDER BY id
            """,
            (paper_id, subject_id),
        ).fetchall()
        if not questions:
            raise RuntimeError(f"No questions tagged to paper {paper['label']}")

        cur = conn.execute(
            "INSERT INTO sessions(subject_id, mode, paper_id) VALUES(?, 'mock_paper', ?) RETURNING id",
            (subject_id, paper_id),
        )
        session_id = cur.fetchone()["id"]
        for position, q in enumerate(questions):
            conn.execute(
                "INSERT INTO session_questions(session_id, question_id, kind, position) "
                "VALUES(?,?,?,?)",
                (session_id, q["id"], "mock", position),
            )
        conn.commit()
    return session_id
