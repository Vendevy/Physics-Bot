# PhysicsBot

A-Level study system: spec → topic tree → tagged question bank → daily sessions with SM-2 spaced repetition. CLI and a local web dashboard with a full study/grading UI.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in API keys
python -m studybot init
```

**API keys** (set in `.env`):
- **Anthropic** — `ANTHROPIC_API_KEY` — generates new practice questions and grades your answers.
- **Gemini** (optional) — `GEMINI_API_KEY` — used for cheap PDF extraction of the spec and past-paper question banks. https://aistudio.google.com/app/apikey

## Bring your own past papers

The OCR / Edexcel PDFs are **not** in this repo (copyright). Drop your own files into the layout the code expects:

```
Physics Past Papers/
├─ 171726-specification-accredited-a-level-gce-physics-a-h556.pdf   # OCR H556 spec
├─ Physics Question Paper/
│   └─ Paper 2/
│       └─ June 2017 QP.pdf
│       └─ June 2018 QP.pdf
│       └─ ...
└─ Physics Markscheme/
    └─ Paper 2/
        └─ June 2017 MS.pdf
        └─ ...
```

The labels (`Paper 2`, `June 2017 QP`) are matched against the markscheme filename, so the QP / MS pairs need to share a stem (e.g. `June 2017 QP.pdf` ↔ `June 2017 MS.pdf`).

You can change the paths in `studybot/config.py` if your layout is different.

## CLI usage

```bash
# 1. Extract the topic tree from the spec (one-time, ~30–60 s)
python -m studybot extract-spec physics

# 2. Build the question bank from past papers
python -m studybot build-questions physics                 # all papers
python -m studybot build-questions physics --paper-prefix Paper2-
python -m studybot build-questions physics --retry-failed  # re-run failures from data/failed_papers.json

# 3. Terminal study session (7 new + 3 recall)
python -m studybot study physics

# 4. Terminal mastery report
python -m studybot progress physics

# 5. Web dashboard + study UI
python -m studybot dashboard          # http://localhost:5050
python -m studybot dashboard --port 8080
```

Shell shortcuts (each one cd's into the project, activates `.venv`, and runs the matching subcommand):

```bash
./dashboard.sh          # web UI (forwards extra args, e.g. ./dashboard.sh --port 8080)
./study.sh              # CLI study session
./progress.sh           # CLI mastery report
```

## Web dashboard

Open `http://localhost:5050` after `dashboard.sh`.

**Dashboard tab** — overall mastery %, per-topic mastery tree, recent attempts (expandable to see your answer + grader feedback), subject selector. A **Resume** button appears in the header whenever an unfinished study session exists.

**Study tab** (`Study` button → `/study`):
- **Topic picker** — collapsible panel on the start screen. Search and tick up to 7 specific topics, or leave empty to fall back to "weakest topics" auto-selection.
- **Live build progress** — questions are generated in parallel; the UI streams "3/7 — 4.2.1 Stationary waves" as each one finishes.
- **Streaming grader** — feedback streams token-by-token via SSE; you don't sit on a blank spinner.
- **Charts** — when the model decides a question genuinely needs a graph (e.g. v–t analysis, IV characteristics), it emits structured data which is rendered with Chart.js inline beside the question.
- **Autosave** — every keystroke in the answer box is saved to `localStorage`; close the tab and your draft is still there.
- **Resume / discard** — close the tab mid-session and a banner offers Resume (jumps to the first unanswered question) or Discard.
- **Flag** — per-question button to mark broken / OCR-mangled / disputed questions for later review.
- **Review & Consolidate** — at the end, walk back through every question with the markscheme, your answer, and the feedback. You must type a consolidation note before advancing — notes are persisted per-question.
- **Keyboard shortcuts** — Ctrl+Enter submits, →/← navigate the review modal, Esc closes it.
- **KaTeX** — LaTeX in question/markscheme/feedback (`$...$` and `$$...$$`) renders inline.

## How it works

| Job | Model | Why |
|---|---|---|
| Spec / past-paper extraction | Gemini 2.5 Flash (or Claude Haiku) | Native PDF parsing, very cheap |
| Generating new questions | Claude Sonnet 4.6 | Best at mimicking exam style and calibrating difficulty to current mastery |
| Grading answers | Claude Sonnet 4.6 | Reliable partial credit + actionable feedback |
| Dashboard / progress | No LLM | SQLite queries + HTML |

- **SM-2** spaced repetition per topic (ease, interval, repetitions). Mastery score is a 0–1 EMA of recent grades, used to pick "weakest" topics.
- **Daily set** — `DAILY_NEW=7` generated questions on the weakest topics + `DAILY_RECALL=3` past-paper questions due for spaced recall (override the constants in `studybot/config.py`).
- **Files API caching** — uploaded PDFs are tracked in `files_cache` so you don't re-upload between runs.
- **Prompt caching** — the grader splits the question + markscheme (cached) from the student answer (uncached), so re-grades on the same question hit cache.

## Cost estimate (Physics, 27 papers, OCR H556)

| Step | Claude only | Gemini + Claude |
|---|---|---|
| Extract spec | ~$0.50 | ~$0.50 |
| Build question bank (27 papers) | ~$54–108 | ~$0.50–1.50 |
| Daily session | ~$0.50–1 | ~$0.50–1 |
| **One-off setup** | **~$55–110** | **~$1.50–3** |

Hybrid is ~50× cheaper for the one-time extraction; identical DB quality.
