#!/usr/bin/env bash
set -euo pipefail
set -x

echo "=============================================="
echo "RAFT ORIGINAL-PAPER LOCAL SMOKE EXPERIMENT"
echo "Project: javadelight.delight-nashorn-sandbox"
echo "Configurations: M, CM"
echo "Runs per configuration: 3"
echo "=============================================="

date

python3 original_paper_phase1_runner.py \
  --only java \
  --project javadelight.delight-nashorn-sandbox \
  --configs M,CM \
  --runs 3

date

echo "=============================================="
echo "EXPERIMENT FINISHED"
echo "=============================================="
