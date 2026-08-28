#!/usr/bin/env python3
"""Merge the duplicate 'tootallnate.java-websocket' / 'tootallnate_java-websocket'
registry entries (same upstream project, two Docker Hub tag spellings) into one
project key in merged/all_test_results.csv, renumbering the dot-variant's
run_index (1-46) to continue after the underscore-variant's (51-96) so the two
independently-collected 50-run batches combine into one 96-run dataset instead
of colliding on run_index.
"""
import csv
import shutil
from pathlib import Path

ROOT = Path.home() / "raft-analysis"
CSV_PATH = ROOT / "merged" / "all_test_results.csv"
BACKUP_PATH = ROOT / "merged" / "all_test_results.csv.pre_websocket_merge_backup"

CANONICAL = "tootallnate_java-websocket"
DUP = "tootallnate.java-websocket"
OFFSET = 50

if not BACKUP_PATH.exists():
    shutil.copy(CSV_PATH, BACKUP_PATH)
    print(f"backed up original to {BACKUP_PATH}")

tmp_path = CSV_PATH.with_suffix(".tmp")
n_changed = 0
n_total = 0
with open(CSV_PATH, newline="") as inf, open(tmp_path, "w", newline="") as outf:
    r = csv.reader(inf)
    w = csv.writer(outf)
    header = next(r)
    w.writerow(header)
    for row in r:
        n_total += 1
        lang, project, config, run_index, classname, testname, status, message = row
        if project == DUP:
            project = CANONICAL
            run_index = str(int(run_index) + OFFSET)
            n_changed += 1
        w.writerow([lang, project, config, run_index, classname, testname, status, message])

tmp_path.replace(CSV_PATH)
print(f"total rows: {n_total}, rows renumbered/relabeled: {n_changed}")
