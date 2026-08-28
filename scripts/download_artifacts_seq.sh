#!/usr/bin/env bash
set -u
cd ~/raft-analysis
mkdir -p artifacts_raw extracted
REPO=jiajuwang/RAFT-experiment

total=$(cut -f1 dedup_artifacts.tsv | wc -l)
n=0
ok=0
fail=0

while IFS=$'\t' read -r id name; do
  n=$((n+1))
  zippath="artifacts_raw/${id}.zip"
  if [ -f "$zippath" ] && python3 -c "import zipfile,sys; sys.exit(0 if zipfile.is_zipfile('$zippath') else 1)" 2>/dev/null; then
    ok=$((ok+1))
    continue
  fi
  success=0
  for attempt in 1 2 3; do
    if gh api "repos/${REPO}/actions/artifacts/${id}/zip" > "$zippath" 2>"artifacts_raw/${id}.err"; then
      if python3 -c "import zipfile,sys; sys.exit(0 if zipfile.is_zipfile('$zippath') else 1)" 2>/dev/null; then
        rm -f "artifacts_raw/${id}.err"
        success=1
        break
      fi
    fi
    sleep 2
  done
  if [ "$success" = "1" ]; then
    ok=$((ok+1))
  else
    fail=$((fail+1))
    echo "FAILED $id $name"
  fi
  if [ $((n % 100)) -eq 0 ]; then
    echo "PROGRESS $n/$total ok=$ok fail=$fail"
  fi
  sleep 0.2
done < dedup_artifacts.tsv

echo "DOWNLOAD DONE total=$total ok=$ok fail=$fail"
