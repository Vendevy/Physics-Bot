#!/usr/bin/env bash
# First-time setup. Run once.
# Usage: bash setup.sh
set -euo pipefail

cd "$(dirname "$0")"

echo "==> Creating virtual environment"
python3 -m venv .venv
source .venv/bin/activate

echo "==> Installing dependencies"
pip install --upgrade pip
pip install -r requirements.txt

echo "==> Checking .env"
if [ ! -f .env ]; then
    echo "ERROR: .env not found. Create it with:"
    echo "  echo 'ANTHROPIC_API_KEY=sk-ant-api03-...' > .env && chmod 600 .env"
    exit 1
fi
if ! grep -q "^ANTHROPIC_API_KEY=sk-ant-" .env; then
    echo "ERROR: .env exists but ANTHROPIC_API_KEY looks wrong."
    echo "It should start with sk-ant-api03-"
    exit 1
fi

echo "==> Initializing database"
python -m studybot init

echo "==> Extracting OCR Physics spec into topic tree (~30-60s, ~\$2)"
python -m studybot extract-spec physics

echo "==> Building question bank — ONE paper first as a test (~30s, ~\$0.50)"
python -m studybot build-questions physics --limit 1

echo ""
echo "============================================================"
echo "Test paper extracted. Check it looks right with:"
echo "    bash progress.sh"
echo ""
echo "If happy, build the rest of the question bank (~3-4 min, ~\$5-7):"
echo "    source .venv/bin/activate && python -m studybot build-questions physics"
echo ""
echo "Then start studying with:"
echo "    bash study.sh"
echo "============================================================"
