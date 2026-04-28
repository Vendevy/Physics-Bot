# studybot

A-Level study system: spec → topic tree → tagged question bank → daily 7-new + 3-recall sessions with SM-2 spaced repetition.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add BOTH API keys
python -m studybot init
```

**API Keys needed:**
- **Gemini** (free): https://aistudio.google.com/app/apikey — used for extracting questions from past papers (cheap, native PDF support)
- **Claude** (paid): https://console.anthropic.com — used for generating daily questions and grading answers (better reasoning)

## Usage

```bash
# 1. Extract the topic tree from each spec (one-time, ~30-60s each)
# Uses Claude — you only do this once per subject
python -m studybot extract-spec physics
python -m studybot extract-spec maths

# 2. Build the question bank from past papers (run once per paper, ~30-60s each)
# Uses Gemini Flash — cheap enough to process all 27 papers for under $1
python -m studybot build-questions physics              # all OCR papers
python -m studybot build-questions physics --limit 2    # test with 2 papers
python -m studybot build-questions maths \
    --qp "Mathematics Past Papers/.../A2 Pure - All Edexcel Papers.pdf" \
    --ms "Mathematics Past Papers/.../A2 Pure - All Edexcel Papers MS.pdf" \
    --label "Edexcel Pure Compilation"

# 3. Daily study session
# Uses Claude for generation + grading
python -m studybot study physics
python -m studybot study maths

# 4. Check progress (terminal)
python -m studybot progress physics

# 5. Launch web dashboard
python -m studybot dashboard        # http://localhost:5050
python -m studybot dashboard --port 8080
```

## How it works

| Task | Tool | Why |
|---|---|---|
| **Extraction** (spec + past papers) | Gemini 2.0 Flash | Native PDF parsing, 1M context, ~$0.02/paper, no rate limits |
| **Generation** (daily questions) | Claude Sonnet | Better at mimicking exam style, calibrating difficulty to mastery |
| **Grading** (feedback + scoring) | Claude Sonnet | More reliable on partial credit, gives actionable feedback |
| **Progress/Dashboard** | No LLM | Pure SQLite queries + HTML rendering |

- **Files API**: PDFs uploaded once per model, cached where possible.
- **SM-2**: per-topic ease + interval; mastery score is a 0..1 EMA of grades.
- **Daily set**: 7 new questions generated for the lowest-mastery topics, 3 past-paper questions due for spaced recall.

## Cost estimate for Physics (27 papers)

| Step | With Claude only | With Gemini + Claude |
|---|---|---|
| Extract spec | ~$0.50 | ~$0.50 (Claude) |
| Build question bank (27 papers) | ~$54–$108 | ~$0.50–$1.50 (Gemini) |
| Daily study session | ~$0.50–$1 | ~$0.50–$1 (Claude) |
| **Total to get started** | **~$55–$110** | **~$1.50–$3** |

The hybrid approach is ~50× cheaper for the one-time extraction step, with identical database quality.
