#!/usr/bin/env bash
# Run a daily physics study session (7 new + 3 recall).
# Usage: bash study.sh
set -euo pipefail

cd "$(dirname "$0")"
source .venv/bin/activate
python -m studybot study physics
