#!/usr/bin/env bash
set -euo pipefail
set -x

python3 - <<'PY'
from pathlib import Path

p = Path("original_paper_phase1_runner.py")
s = p.read_text()

old = "RUNS_PER_CONFIG_DEFAULT = 10"
new = "RUNS_PER_CONFIG_DEFAULT = 300"

if old not in s:
    raise SystemExit("ERROR: expected old run-count line was not found")

s = s.replace(old, new, 1)
p.write_text(s)

print("Changed original-paper default run count from 10 to 300.")
PY

grep -n "RUNS_PER_CONFIG_DEFAULT" original_paper_phase1_runner.py
