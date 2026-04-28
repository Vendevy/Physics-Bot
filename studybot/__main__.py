"""CLI entry point. Run with: python -m studybot <command>"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .db import connect, init_db
from .extract_spec import extract as extract_spec
from .extract_questions import extract_paper, topics_summary, update_markschemes
from .daily import build_session
from .grade import grade_answer, record_attempt
from .progress import render, subject_progress
from .dashboard import start_server

FAILED_LOG = config.DATA_DIR / "failed_papers.json"


def _load_failures() -> dict[str, dict]:
    if not FAILED_LOG.exists():
        return {}
    try:
        return json.loads(FAILED_LOG.read_text())
    except json.JSONDecodeError:
        return {}


def _save_failures(failures: dict[str, dict]) -> None:
    FAILED_LOG.parent.mkdir(parents=True, exist_ok=True)
    FAILED_LOG.write_text(json.dumps(failures, indent=2))


def _record_failure(label: str, qp: Path, ms: Path, error: str) -> None:
    failures = _load_failures()
    failures[label] = {
        "qp": str(qp),
        "ms": str(ms),
        "error": error,
        "failed_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_failures(failures)


def _clear_failure(label: str) -> None:
    failures = _load_failures()
    if label in failures:
        del failures[label]
        _save_failures(failures)

SUBJECTS = {
    "physics": {
        "name": "A-Level Physics (OCR H556)",
        "board": "OCR",
        "spec": config.PHYSICS_SPEC,
        "papers_dir": config.PHYSICS_PAPERS_DIR,
        "ms_dir": config.PHYSICS_MS_DIR,
    },
    "maths": {
        "name": "A-Level Mathematics (Edexcel)",
        "board": "Edexcel",
        "spec": config.MATHS_SPEC,
        "papers_dir": None,
        "ms_dir": None,
    },
}


def cmd_init(args):
    init_db()
    print(f"Initialized db at {config.DB_PATH}")


def cmd_extract_spec(args):
    s = SUBJECTS[args.subject]
    extract_spec(s["name"], s["board"], s["spec"])


def cmd_build_questions(args):
    s = SUBJECTS[args.subject]
    with connect() as conn:
        subj = conn.execute(
            "SELECT id, spec_file_id FROM subjects WHERE name = ?", (s["name"],)
        ).fetchone()
    if subj is None or not subj["spec_file_id"]:
        print(f"Run `python -m studybot extract-spec {args.subject}` first.")
        sys.exit(1)
    subject_id = subj["id"]
    spec_file_id = subj["spec_file_id"]
    summary = topics_summary(subject_id)

    if args.subject == "physics":
        if args.retry_failed:
            failures = _load_failures()
            if not failures:
                print(f"No failures logged at {FAILED_LOG}")
                return
            jobs = [
                (label, Path(entry["qp"]), Path(entry["ms"]))
                for label, entry in failures.items()
            ]
            print(f"Retrying {len(jobs)} failed paper(s) from {FAILED_LOG}")
        else:
            qp_dir = s["papers_dir"]
            ms_dir = s["ms_dir"]
            # Recursively find all QPs, skip duplicate filenames like "... (1).pdf"
            qps = sorted([p for p in qp_dir.rglob("*QP.pdf") if " (1)" not in p.stem])
            if args.limit:
                qps = qps[: args.limit]
            jobs = []
            for qp in qps:
                # Label includes paper folder to avoid collisions (e.g. P1-June 2017)
                rel_parts = qp.relative_to(qp_dir).parts
                paper_folder = rel_parts[0].replace(" ", "") if len(rel_parts) > 1 else ""
                base_label = qp.stem.replace(" QP", "")
                label = f"{paper_folder}-{base_label}" if paper_folder else base_label

                # Search for markscheme in the matching paper subfolder first,
                # then fall back to a global search to handle naming inconsistencies.
                ms_paper_dir = ms_dir / paper_folder if paper_folder else ms_dir
                ms_candidates = list(ms_paper_dir.glob(f"{base_label} MS*.pdf"))
                if not ms_candidates:
                    ms_candidates = list(ms_dir.rglob(f"{base_label} MS*.pdf"))
                if not ms_candidates:
                    print(f"Skip (no MS): {qp}")
                    continue
                jobs.append((label, qp, ms_candidates[0]))

            if args.paper:
                wanted = set(args.paper)
                jobs = [j for j in jobs if j[0] in wanted]
                missing = wanted - {j[0] for j in jobs}
                if missing:
                    print(f"No matching paper(s): {sorted(missing)}")
                if not jobs:
                    return
                print(f"Targeting {len(jobs)} paper(s): {[j[0] for j in jobs]}")

            if args.paper_prefix:
                jobs = [j for j in jobs if j[0].startswith(args.paper_prefix)]
                if not jobs:
                    print(f"No papers match prefix: {args.paper_prefix!r}")
                    return
                print(f"Prefix {args.paper_prefix!r} → {len(jobs)} paper(s)")

        for label, qp, ms in jobs:
            if args.ms_only:
                print(f"\n[{label}]  MS-only: {ms.name}")
            else:
                print(f"\n[{label}]  QP: {qp.name}  MS: {ms.name}")
            try:
                if args.ms_only:
                    update_markschemes(subject_id, label, ms)
                else:
                    extract_paper(subject_id, label, qp, ms, spec_file_id, summary)
                _clear_failure(label)
            except Exception as e:
                print(f"  FAILED: {e}")
                _record_failure(label, qp, ms, str(e))
                continue

        remaining = _load_failures()
        if remaining:
            print(f"\n{len(remaining)} paper(s) still failing — see {FAILED_LOG}")
            print("Retry with: python -m studybot build-questions physics --retry-failed")
    else:
        # Edexcel maths bundles paper + MS in different filenames; require explicit --qp/--ms
        if not args.qp or not args.ms:
            print("For maths, pass --qp <paper.pdf> --ms <markscheme.pdf> --label <name>")
            sys.exit(1)
        extract_paper(subject_id, args.label, Path(args.qp), Path(args.ms), spec_file_id, summary)


def cmd_study(args):
    s = SUBJECTS[args.subject]
    with connect() as conn:
        subj = conn.execute("SELECT id FROM subjects WHERE name = ?", (s["name"],)).fetchone()
    if subj is None:
        print(f"No subject loaded. Run `extract-spec {args.subject}` first.")
        sys.exit(1)

    session_id = build_session(subj["id"])

    with connect() as conn:
        items = conn.execute(
            """
            SELECT sq.position, sq.kind, q.id AS qid, q.text, q.marks, q.qnum
            FROM session_questions sq JOIN questions q ON q.id = sq.question_id
            WHERE sq.session_id = ? ORDER BY sq.position
            """,
            (session_id,),
        ).fetchall()

    print(f"\n=== Daily session #{session_id} — {len(items)} questions ===\n")
    for it in items:
        print("=" * 70)
        print(f"[{it['position']+1}/{len(items)}] {it['kind'].upper()}  ({it['marks']} marks)")
        if it["qnum"]:
            print(f"Past paper Q{it['qnum']}")
        print()
        print(it["text"])
        print()
        print("Type your answer. End with a blank line:")
        lines: list[str] = []
        while True:
            try:
                line = input()
            except EOFError:
                break
            if line == "":
                if lines and lines[-1] == "":
                    lines.pop()
                    break
                if not lines:
                    break
            lines.append(line)
        answer = "\n".join(lines).strip()
        if not answer:
            print("(skipped)\n")
            continue

        print("\nGrading...")
        result = grade_answer(it["qid"], answer)
        record_attempt(
            question_id=it["qid"],
            session_id=session_id,
            position=it["position"],
            user_answer=answer,
            grade_result=result,
        )
        print(f"\n--> {result['marks_awarded']}/{result['total_marks']}  "
              f"(SM-2 grade: {result['sm2_grade']}/5)\n")
        print(result["feedback"])
        print()

    with connect() as conn:
        conn.execute(
            "UPDATE sessions SET completed_at = CURRENT_TIMESTAMP WHERE id = ?",
            (session_id,),
        )
        conn.commit()
    print("\nSession complete. Run `python -m studybot progress` to see updated mastery.")


def cmd_progress(args):
    s = SUBJECTS[args.subject]
    with connect() as conn:
        subj = conn.execute("SELECT id, name FROM subjects WHERE name = ?", (s["name"],)).fetchone()
    if subj is None:
        print(f"No subject loaded.")
        return
    p = subject_progress(subj["id"])
    print(render(subj["name"], p))


def cmd_dashboard(args):
    start_server(port=args.port)


def main():
    parser = argparse.ArgumentParser(prog="studybot")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="Create the database").set_defaults(func=cmd_init)

    p = sub.add_parser("extract-spec", help="Extract topic tree from spec PDF")
    p.add_argument("subject", choices=SUBJECTS.keys())
    p.set_defaults(func=cmd_extract_spec)

    p = sub.add_parser("build-questions", help="Extract & tag questions from past papers")
    p.add_argument("subject", choices=SUBJECTS.keys())
    p.add_argument("--limit", type=int, help="Process only first N papers (for testing)")
    p.add_argument(
        "--retry-failed",
        action="store_true",
        help="Only reprocess papers logged in data/failed_papers.json",
    )
    p.add_argument(
        "--paper",
        action="append",
        help="Only process the given paper label (repeatable, e.g. --paper Paper2-June\\ 2017)",
    )
    p.add_argument(
        "--paper-prefix",
        help="Only process papers whose label starts with this prefix (e.g. --paper-prefix Paper2-)",
    )
    p.add_argument(
        "--ms-only",
        action="store_true",
        help="Skip QP extraction; re-extract markschemes only and update existing questions",
    )
    p.add_argument("--qp", help="Question paper PDF (maths only)")
    p.add_argument("--ms", help="Markscheme PDF (maths only)")
    p.add_argument("--label", help="Label for this paper (maths only)")
    p.set_defaults(func=cmd_build_questions)

    p = sub.add_parser("study", help="Run today's session (7 new + 3 recall)")
    p.add_argument("subject", choices=SUBJECTS.keys())
    p.set_defaults(func=cmd_study)

    p = sub.add_parser("progress", help="Show mastery dashboard")
    p.add_argument("subject", choices=SUBJECTS.keys())
    p.set_defaults(func=cmd_progress)

    p = sub.add_parser("dashboard", help="Launch local web dashboard")
    p.add_argument("--port", type=int, default=5050, help="Port to run on (default: 5050)")
    p.set_defaults(func=cmd_dashboard)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
