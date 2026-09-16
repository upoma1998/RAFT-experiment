#!/usr/bin/env bash
set -euo pipefail
set -x

echo "============================================================"
echo "RAFT ORIGINAL-PAPER SMOKE TEST"
echo "Fresh Docker container per repetition"
echo "Project: javadelight.delight-nashorn-sandbox"
echo "Configuration: M"
echo "Runs: 3"
echo "============================================================"

date

python3 original_paper_phase1_runner.py \
  --only java \
  --project javadelight.delight-nashorn-sandbox \
  --configs M \
  --runs 3

date
