#!/usr/bin/env bash
set -euo pipefail
set -x

echo "============================================================"
echo "DIAGNOSTIC ONLY - NOT ORIGINAL PAPER CONFIGURATION"
echo "Project: delight-nashorn-sandbox"
echo "CPU: 4"
echo "Memory: Docker memory limit disabled"
echo "Runs: 1"
echo "============================================================"

date

python3 original_paper_phase1_runner.py \
  --only java \
  --project javadelight.delight-nashorn-sandbox \
  --configs LOCAL_UNLIMITED \
  --runs 1

date
