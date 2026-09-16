#!/usr/bin/env bash
set -euo pipefail
set -x

echo "============================================================"
echo "RAFT ORIGINAL-PAPER LOCAL PRELIMINARY EXPERIMENT"
echo "Project: javadelight.delight-nashorn-sandbox"
echo "Configuration: M"
echo "Runs: 300"
echo "============================================================"

echo "START:"
date

echo "GIT COMMIT:"
git rev-parse HEAD

echo "BRANCH:"
git branch --show-current

python3 original_paper_phase1_runner.py \
  --only java \
  --project javadelight.delight-nashorn-sandbox \
  --configs M \
  --runs 300

echo "END:"
date

echo "============================================================"
echo "EXPERIMENT COMPLETE"
echo "============================================================"
