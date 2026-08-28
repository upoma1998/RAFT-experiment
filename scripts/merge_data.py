#!/usr/bin/env python3
"""Merge all downloaded per-batch artifact zips into consolidated CSVs.

Each artifacts_raw/<artifact_id>.zip contains (if the batch produced data):
  results/<project>.csv   (up to 5 rows-per-test batch, run_index in one offset window)
  errors/<project>.log

Read directly from the zip in-memory (no unzip binary available on this box).
We concatenate all result rows into one master CSV, and all error logs into
one master error log, tagging each with language (derived from the artifact
name, which is stored alongside each id in dedup_artifacts.tsv).
"""
import csv
import sys
import zipfile
from pathlib import Path

ROOT = Path.home() / "raft-analysis"
ARTIFACTS_RAW = ROOT / "artifacts_raw"
OUT_DIR = ROOT / "merged"
OUT_DIR.mkdir(exist_ok=True)

master_csv_path = OUT_DIR / "all_test_results.csv"
master_err_path = OUT_DIR / "all_errors.log"

HEADER = ["language", "project", "config", "run_index", "classname", "testname", "status", "message"]

# id -> artifact name (e.g. "java-apache_httpcore-Baseline-offset10"), for the language prefix
id_to_name = {}
with open(ROOT / "dedup_artifacts.tsv") as f:
    for line in f:
        parts = line.rstrip("\n").split("\t")
        if len(parts) == 2:
            id_to_name[parts[0]] = parts[1]

seen_keys = set()  # (language, project, config, run_index, classname, testname) -> dedupe exact dup rows
n_rows_written = 0
n_rows_dup_skipped = 0
n_csv_files = 0
n_err_files = 0
n_zips_seen = 0
n_zips_bad = 0

with open(master_csv_path, "w", newline="") as out_f, open(master_err_path, "w") as err_f:
    writer = csv.writer(out_f)
    writer.writerow(HEADER)

    zip_paths = sorted(ARTIFACTS_RAW.glob("*.zip"))
    for i, zpath in enumerate(zip_paths):
        n_zips_seen += 1
        if i % 500 == 0:
            print(f"  ...{i}/{len(zip_paths)} zips", file=sys.stderr)
        artifact_id = zpath.stem
        name = id_to_name.get(artifact_id, "")
        lang = name.split("-", 1)[0] if name else "?"
        try:
            zf = zipfile.ZipFile(zpath)
        except Exception as e:
            print(f"WARN bad zip {zpath}: {e}", file=sys.stderr)
            n_zips_bad += 1
            continue

        for member in zf.namelist():
            if member.startswith("results/") and member.endswith(".csv"):
                project = Path(member).stem
                n_csv_files += 1
                try:
                    content = zf.read(member).decode(errors="replace")
                except Exception as e:
                    print(f"WARN failed to read {zpath}!{member}: {e}", file=sys.stderr)
                    continue
                rows = list(csv.reader(content.splitlines()))
                if not rows:
                    continue
                body = rows[1:] if rows[0] and rows[0][0] == "project" else rows
                for row in body:
                    if len(row) != 7:
                        continue
                    proj, config, run_idx, classname, testname, status, message = row
                    key = (lang, proj, config, run_idx, classname, testname)
                    if key in seen_keys:
                        n_rows_dup_skipped += 1
                        continue
                    seen_keys.add(key)
                    writer.writerow([lang, proj, config, run_idx, classname, testname, status, message])
                    n_rows_written += 1
            elif member.startswith("errors/") and member.endswith(".log"):
                n_err_files += 1
                try:
                    content = zf.read(member).decode(errors="replace")
                except Exception as e:
                    print(f"WARN failed to read {zpath}!{member}: {e}", file=sys.stderr)
                    continue
                if content.strip():
                    err_f.write(f"##### lang={lang} artifact={artifact_id} name={name} #####\n")
                    err_f.write(content)
                    err_f.write("\n")
        zf.close()

print(f"zips seen: {n_zips_seen}")
print(f"bad/unreadable zips: {n_zips_bad}")
print(f"csv members merged: {n_csv_files}")
print(f"error log members merged: {n_err_files}")
print(f"rows written: {n_rows_written}")
print(f"duplicate rows skipped: {n_rows_dup_skipped}")
print(f"-> {master_csv_path}")
print(f"-> {master_err_path}")
