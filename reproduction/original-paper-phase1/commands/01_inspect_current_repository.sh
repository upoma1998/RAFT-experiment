#!/usr/bin/env bash

set -u
set -o pipefail
set -x

echo "============================================================"
echo "1. CURRENT DATE"
echo "============================================================"
date

echo
echo "============================================================"
echo "2. CURRENT DIRECTORY"
echo "============================================================"
pwd

echo
echo "============================================================"
echo "3. CURRENT GIT BRANCH"
echo "============================================================"
git branch --show-current

echo
echo "============================================================"
echo "4. GIT STATUS"
echo "============================================================"
git status

echo
echo "============================================================"
echo "5. CURRENT COMMIT"
echo "============================================================"
git rev-parse HEAD

echo
echo "============================================================"
echo "6. GIT REMOTES"
echo "============================================================"
git remote -v

echo
echo "============================================================"
echo "7. RECENT GIT HISTORY"
echo "============================================================"
git log --oneline --decorate -10

echo
echo "============================================================"
echo "8. REPOSITORY TOP-LEVEL FILES"
echo "============================================================"
find . -maxdepth 2 -type f \
    ! -path './.git/*' \
    | sort

echo
echo "============================================================"
echo "9. RUNNER HELP"
echo "============================================================"
python3 phase1_runner.py --help

echo
echo "============================================================"
echo "10. CURRENT DEFAULT RUN COUNT"
echo "============================================================"
grep -n "RUNS_PER_CONFIG_DEFAULT" phase1_runner.py

echo
echo "============================================================"
echo "11. CURRENT CONFIGURATION DEFINITIONS"
echo "============================================================"
grep -n -A80 "^CONFIGS" phase1_runner.py

echo
echo "============================================================"
echo "12. CURRENT COMMAND-LINE ARGUMENTS"
echo "============================================================"
grep -n -A35 "ArgumentParser" phase1_runner.py

echo
echo "============================================================"
echo "13. CURRENT REGISTRY COUNTS"
echo "============================================================"
python3 - <<'PY'
import json

with open("phase1_registry.json") as f:
    registry = json.load(f)

total = 0

for lang in ("java", "js", "python"):
    projects = registry.get(lang, {})
    print(f"{lang}: {len(projects)} projects")
    total += len(projects)

print(f"TOTAL: {total} projects")
PY

echo
echo "============================================================"
echo "14. CURRENT JAVA PROJECT KEYS"
echo "============================================================"
python3 - <<'PY'
import json

with open("phase1_registry.json") as f:
    registry = json.load(f)

for name in sorted(registry.get("java", {})):
    print(name)
PY

echo
echo "============================================================"
echo "15. CURRENT JAVASCRIPT PROJECT KEYS"
echo "============================================================"
python3 - <<'PY'
import json

with open("phase1_registry.json") as f:
    registry = json.load(f)

for name in sorted(registry.get("js", {})):
    print(name)
PY

echo
echo "============================================================"
echo "16. CURRENT PYTHON PROJECT KEYS"
echo "============================================================"
python3 - <<'PY'
import json

with open("phase1_registry.json") as f:
    registry = json.load(f)

for name in sorted(registry.get("python", {})):
    print(name)
PY

echo
echo "============================================================"
echo "17. EXISTING RESULT FILES"
echo "============================================================"
ls -lh results

echo
echo "============================================================"
echo "18. EXISTING GITHUB ACTION WORKFLOWS"
echo "============================================================"
find .github/workflows -maxdepth 1 -type f -print -exec \
    sh -c 'echo "--- $1 ---"; sed -n "1,220p" "$1"' _ {} \;

echo
echo "============================================================"
echo "INSPECTION COMPLETE"
echo "============================================================"
