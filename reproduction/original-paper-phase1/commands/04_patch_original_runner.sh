#!/usr/bin/env bash
set -euo pipefail
set -x

echo "============================================================"
echo "PATCHING RUNNER TO MATCH ORIGINAL RAFT PHASE I"
echo "============================================================"

python3 - <<'PY'
from pathlib import Path
import re

p = Path("original_paper_phase1_runner.py")

if not p.exists():
    raise SystemExit("ERROR: original_paper_phase1_runner.py does not exist")

s = p.read_text()

# ------------------------------------------------------------
# 1. Original paper: 300 executions per configuration
# ------------------------------------------------------------
s, n = re.subn(
    r'^RUNS_PER_CONFIG_DEFAULT\s*=\s*\d+\s*$',
    'RUNS_PER_CONFIG_DEFAULT = 300',
    s,
    count=1,
    flags=re.MULTILINE
)

if n != 1:
    raise SystemExit("ERROR: Could not find RUNS_PER_CONFIG_DEFAULT")

# ------------------------------------------------------------
# 2. Keep original-paper results separate
# ------------------------------------------------------------
old_result = 'RESULTS_ROOT = ROOT / "phase1-results"'
new_result = (
    'RESULTS_ROOT = ROOT / '
    '"reproduction/original-paper-phase1/results/raw"'
)

if old_result in s:
    s = s.replace(old_result, new_result, 1)
elif new_result not in s:
    raise SystemExit("ERROR: Could not identify RESULTS_ROOT")

# ------------------------------------------------------------
# 3. Use our reconstructed original-paper registry if present
# ------------------------------------------------------------
old_registry = '"phase1_registry.json"'
new_registry = '"original_paper_phase1_registry.json"'

if Path("original_paper_phase1_registry.json").exists():
    s = s.replace(old_registry, new_registry)
    print("Using original_paper_phase1_registry.json")
else:
    print(
        "WARNING: original_paper_phase1_registry.json not found. "
        "Registry reference was not changed."
    )

# ------------------------------------------------------------
# 4. Restore the 16 Phase-I configurations from Table I
# ------------------------------------------------------------

lines = s.splitlines()

try:
    start = next(
        i for i, line in enumerate(lines)
        if line.startswith("CONFIGS = {")
    )
except StopIteration:
    raise SystemExit("ERROR: CONFIGS block not found")

try:
    end = next(
        i for i in range(start + 1, len(lines))
        if lines[i].strip() == "}"
    )
except StopIteration:
    raise SystemExit("ERROR: end of CONFIGS block not found")

replacement = '''CONFIGS = {
    "Baseline": dict(cpus=4,   mem="16g",  disk=None,      net=None),
    "C":        dict(cpus=0.1, mem="16g",  disk=None,      net=None),
    "M":        dict(cpus=4,   mem="512m", disk=None,      net=None),
    "D":        dict(cpus=4,   mem="16g",  disk=(50, 100), net=None),
    "N":        dict(cpus=4,   mem="16g",  disk=None,      net=(1500, 512)),
    "CM":       dict(cpus=0.1, mem="512m", disk=None,      net=None),
    "CN":       dict(cpus=0.1, mem="16g",  disk=None,      net=(1500, 512)),
    "MN":       dict(cpus=4,   mem="512m", disk=None,      net=(1500, 512)),
    "CD":       dict(cpus=0.1, mem="16g",  disk=(50, 100), net=None),
    "MD":       dict(cpus=4,   mem="512m", disk=(50, 100), net=None),
    "DN":       dict(cpus=4,   mem="16g",  disk=(50, 100), net=(1500, 512)),
    "CMN":      dict(cpus=0.1, mem="512m", disk=None,      net=(1500, 512)),
    "CMD":      dict(cpus=0.1, mem="512m", disk=(50, 100), net=None),
    "CDN":      dict(cpus=0.1, mem="16g",  disk=(50, 100), net=(1500, 512)),
    "MDN":      dict(cpus=4,   mem="512m", disk=(50, 100), net=(1500, 512)),
    "CMDN":     dict(cpus=0.1, mem="512m", disk=(50, 100), net=(1500, 512)),
}'''.splitlines()

lines[start:end + 1] = replacement

p.write_text("\n".join(lines) + "\n")

print()
print("Successfully patched:", p)
PY

echo
echo "============================================================"
echo "VERIFY RUN COUNT"
echo "============================================================"
grep -n "RUNS_PER_CONFIG_DEFAULT" original_paper_phase1_runner.py

echo
echo "============================================================"
echo "VERIFY RESULTS DIRECTORY"
echo "============================================================"
grep -n "RESULTS_ROOT" original_paper_phase1_runner.py | head

echo
echo "============================================================"
echo "VERIFY REGISTRY"
echo "============================================================"
grep -n "phase1_registry" original_paper_phase1_runner.py || true

echo
echo "============================================================"
echo "VERIFY CONFIGURATIONS"
echo "============================================================"
grep -n -A18 "^CONFIGS =" original_paper_phase1_runner.py

echo
echo "============================================================"
echo "PYTHON SYNTAX CHECK"
echo "============================================================"
python3 -m py_compile original_paper_phase1_runner.py

echo "Python syntax check PASSED."

echo
echo "============================================================"
echo "PATCH COMPLETE"
echo "============================================================"
