#!/usr/bin/env bash
set -euo pipefail
set -x

echo "DIAGNOSTIC ONLY - NOT ORIGINAL PAPER CONFIGURATION"
echo "Project: delight-nashorn-sandbox"
echo "CPU: 4"
echo "Memory: 1 GiB"
echo "Runs: 3"

date

python3 original_paper_phase1_runner.py \
  --only java \
  --project javadelight.delight-nashorn-sandbox \
  --configs M_DIAG_1G \
  --runs 3

date
