#!/usr/bin/env bash
# Show progress dashboard.
# Usage: bash progress.sh
set -euo pipefail

cd "$(dirname "$0")"
source .venv/bin/activate
python -m studybot progress physics
