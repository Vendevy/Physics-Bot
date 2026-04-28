#!/usr/bin/env bash
# Launch the PhysicsBot web dashboard at http://localhost:5050
# Usage: bash dashboard.sh [--port N]
set -euo pipefail

cd "$(dirname "$0")"
source .venv/bin/activate
python -m studybot dashboard "$@"
