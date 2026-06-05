#!/usr/bin/env bash
# Phase 6: nightly research-lab pipeline.
#   1. run the universe for today (paper only)   2. top up matured scores
#   3. print the review
#
# Cron example (weekdays 22:00, after the US close):
#   0 22 * * 1-5  cd /path/to/TradingAgents && experiment/nightly.sh >> predictions/nightly.log 2>&1
#
# Requires: an LLM key in the environment (e.g. via a sourced .env) and
# `uv` available. Adjust to `python -m` if you manage your own venv.
set -euo pipefail
cd "$(dirname "$0")/.."

# Load .env if present (export every KEY=VALUE line).
if [ -f .env ]; then set -a; . ./.env; set +a; fi

RUNNER=${RUNNER:-"uv run python"}

echo "===== $(date -Is) nightly run ====="
$RUNNER -m experiment.run
$RUNNER -m experiment.score
$RUNNER -m experiment.review
echo "===== done ====="
