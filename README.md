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

The header has three navigation buttons: **Dashboard**, **Study**, **Notebook**, plus a subject selector. A yellow **Resume** button appears whenever an unfinished study session exists for the current subject.

### Dashboard
Overall mastery %, per-topic mastery tree (paper → module → topic-group → leaf, mastery-coloured), and a recent-attempts list (expandable to see your answer + grader feedback). Each attempt row shows the elapsed time alongside the date.

### Study (`/study`)

Two modes selectable on the start screen:

#### Daily Session
- **Number of questions** — stepper input, 1–15 (defaults to `DAILY_NEW`). Plus the recall set is appended as before.
- **Difficulty selector** — four levels:
  1. **3 — Standard A-Level** (default, exam-typical)
  2. **4 — Difficult A-Level** — pick exactly one move from the conceptual-moves menu
  3. **5 — Very Difficult A-Level** — combine two moves; at least one must be qualitative or evaluative
  4. **6 — Extremely Difficult A-Level** — combine two or three moves; subtle traps, BPhO-stretch, strictly within the spec
  At L4+, the prompt injects a menu of named conceptual moves the model picks from — synthesis across spec points, limiting-case reasoning, qualitative-before-quantitative, misconception traps, method evaluation, symbolic derivation before substitution, unfamiliar context with familiar physics, and estimation with justification. Hardness comes from depth of thinking, not from importing harder maths.
- **Past-paper style anchor** — checkbox (default on). When on, one short past-paper question on the same topic is injected as a style reference (form only — the model is told to pick a fresh scenario). Turn off to generate purely from the spec content with no past-paper anchoring.
- **Anti-repetition** — every generation gets a "do not repeat" list of the last 8 generated scenarios on the same topic, with a short kebab-case `scenario` tag (e.g. `skydiver-terminal-velocity`) stored on each question for cheap deduping.
- **Topic picker** — collapsible search-and-tick of leaf topics. Pick up to N (= chosen question count) specific topics, or leave empty to auto-pick the weakest.
- **Live build progress** — questions generated in parallel; the UI streams "3/7 — 4.2.1 Stationary waves" as each one finishes.
- **Streaming grader** — feedback streams token-by-token via SSE.
- **Charts (Chart.js)** — when a question genuinely needs a graph (e.g. v–t analysis, IV characteristics, decay curve), the model emits structured data and the chart is rendered inline beside the question.
- **Autosave** — every keystroke is saved to `localStorage`.
- **Resume / discard** — close the tab and a banner offers Resume or Discard.
- **Skip** — skip any question without grading (no API cost). Recorded as 0 marks. Keyboard shortcut: Escape.
- **Flag** — per-question button to mark broken / OCR-mangled / disputed questions.
- **Time tracking** — wall-clock per question is logged on every attempt.
- **Review & Consolidate** — at the end, walk back through every question with the markscheme, your answer, and the feedback. You must type a consolidation note before advancing — notes are persisted per-question.

#### Mock Paper
- Pick a past paper from the dropdown. The picker lists every paper with extracted questions, with per-paper question count and total marks.
- Sit the paper end-to-end with a sticky **count-up timer**. **No mid-session feedback** — submission saves the answer and advances to the next question.
- "Finish & Submit Paper" on the last question batch-grades every answer in parallel and shows total awarded / possible.
- Review & Consolidate works the same as daily mode.

#### Other UX
- **Subject lock** — generated questions are explicitly framed in the active subject; even subject-agnostic topic titles ("Evaluation of experimental method", "Significant figures") get physics scenarios in physics sessions.
- **Calculus rule** (physics only) — the OCR H556 spec doesn't include calculus, so the prompt forbids dx/dt notation, integrals, and differential equations in both the question and the markscheme. Maths sessions are unaffected.
- **Keyboard shortcuts** — Ctrl+Enter submits, Escape skips, →/← navigate the review modal, Esc closes it.
- **KaTeX** — LaTeX in question/markscheme/feedback (`$...$` and `$$...$$`) renders inline.

### Notebook (`/notebook`)
Surfaces every consolidation note you've written, grouped by topic, newest first. Each entry includes the marks chip, paper-question source, date, an expandable "Question" excerpt, and your note rendered as markdown.

## How it works

| Job | Model | Why |
|---|---|---|
| Spec / past-paper extraction | Gemini 2.5 Flash (or Claude Haiku) | Native PDF parsing, very cheap |
| Generating new questions | Claude Sonnet 4.6 | Best at mimicking exam style and calibrating difficulty |
| Validating generated questions | Claude Haiku 4.5 | Checks solvability, consistency, markscheme accuracy — cheaper than Sonnet |
| Grading answers | Claude Sonnet 4.6 | Reliable partial credit + actionable feedback |
| Dashboard / progress / notebook | No LLM | SQLite queries + HTML |

### Question generation pipeline

1. **Generate** — Sonnet produces a question + markscheme on the weakest topic.
2. **Validate** — Haiku checks the question for solvability, self-consistency, markscheme accuracy, and LaTeX formatting. If it fails, the question is regenerated (up to 2 retries). If Haiku provides a corrected markscheme, the correction is applied.
3. **Calibrated grading** — When the student submits, the grader produces:
   - `MARKS_AWARDED` / `TOTAL_MARKS` — the raw mark
   - `SM2_GRADE` — calibrated from the marks ratio (0–100% maps to 0–5), then adjustable ±1 by the LLM for qualitative factors
   - `ERROR_TAGS` — categorised error types (calculation, units, sig_figs, misconception, missing_explanation, wrong_method, incomplete, notation)
   - `FEEDBACK` — structured by question part with ✅/❌ per marking point
4. **Alternative approaches** — The grader explicitly awards marks for valid alternative physics approaches, even if they aren't in the markscheme.

### Spaced repetition

- **SM-2** per topic (ease, interval, repetitions). Mastery score is a 0–1 EMA (alpha=0.2) of recent grades, used to pick "weakest" topics.
- **Error-pattern boosting** — topics with recent repeated low grades (sm2_grade ≤ 2 in the last 14 days) get an error boost of up to 0.3, pushing them higher in the weakest-topics ranking so you study what you keep getting wrong.
- **Daily set** — by default `DAILY_NEW=7` generated questions on the weakest topics + `DAILY_RECALL=3` past-paper questions due for spaced recall. Recall questions are ordered by: fewest times seen, then lowest last grade, then most overdue.
- **Mock-paper set** — every question from a chosen past paper, in original order. Batch-graded at the end.
- **Files API caching** — uploaded PDFs are tracked in `files_cache` so you don't re-upload between runs.
- **Prompt caching** — the grader splits the question + markscheme (cached) from the student answer (uncached), so re-grades on the same question hit cache.

### LaTeX in markschemes

All mathematical expressions in markschemes and feedback use LaTeX notation (`$...$` for inline math, e.g. `$E_k = \frac{1}{2}mv^2$`). This applies to:
- Generated question markschemes
- Extracted past-paper markschemes
- Grader feedback (structured by question part)

## Cost estimate (Physics, 27 papers, OCR H556)

| Step | Claude only | Gemini + Claude |
|---|---|---|
| Extract spec | ~$0.50 | ~$0.50 |
| Build question bank (27 papers) | ~$54–108 | ~$0.50–1.50 |
| Daily session (7 gen + 3 recall) | ~$0.20–0.35 | ~$0.20–0.35 |
| **One-off setup** | **~$55–110** | **~$1.50–3** |

Per-question cost breakdown (daily session):

| Call | Model | Cost |
|---|---|---|
| Generate question | Sonnet 4.6 | ~$0.01 |
| Validate question | Haiku 4.5 | ~$0.002 |
| Grade answer | Sonnet 4.6 | ~$0.01 |
| **Total per question** | | **~$0.02–0.03** |

Hybrid is ~50× cheaper for the one-time extraction; identical DB quality.