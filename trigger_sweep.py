#!/usr/bin/env python3
"""Fire one workflow_dispatch of phase1-sweep.yml per (language, project, config)
combination in phase1_registry.json (89 projects x 5 configs = 445 triggers,
each spawning 10 jobs of 5 runs -> 4,450 jobs, 50 runs/config total).
Logs each trigger to trigger_log.csv so progress/failures can be audited and
reruns skip combinations already triggered successfully.

Usage:
  python3 trigger_sweep.py                                   # fire all 445
  python3 trigger_sweep.py java:tootallnate_java-websocket:Baseline  # just one (smoke test)
"""
import csv, json, subprocess, sys, time
from pathlib import Path

REPO = "jiajuwang/RAFT-experiment"
CONFIGS = ["Baseline", "C", "M", "D", "N"]
SLEEP_SEC = 1.5

ROOT = Path(__file__).parent
LOG_PATH = ROOT / "trigger_log.csv"
REGISTRY_PATH = ROOT / "phase1_registry.json"


def load_registry():
    return json.loads(REGISTRY_PATH.read_text())


def already_triggered():
    done = set()
    if LOG_PATH.exists():
        with open(LOG_PATH, newline="") as f:
            for row in csv.DictReader(f):
                if row.get("status") == "ok":
                    done.add((row["language"], row["project"], row["config"]))
    return done


def trigger(language, project, config):
    r = subprocess.run(
        ["gh", "workflow", "run", "phase1-sweep.yml", "-R", REPO,
         "-f", f"language={language}", "-f", f"project={project}", "-f", f"config={config}"],
        capture_output=True, text=True,
    )
    return r.returncode == 0, (r.stderr.strip() or r.stdout.strip())


def main():
    only = sys.argv[1:]  # optional: "language:project:config" args to run just those (smoke test)
    reg = load_registry()
    combos = []
    if only:
        for spec in only:
            lang, proj, cfg = spec.split(":")
            combos.append((lang, proj, cfg))
    else:
        for lang, projects in reg.items():
            for proj in sorted(projects.keys()):
                for cfg in CONFIGS:
                    combos.append((lang, proj, cfg))

    done = already_triggered()
    new_log = not LOG_PATH.exists()
    with open(LOG_PATH, "a", newline="") as f:
        w = csv.writer(f)
        if new_log:
            w.writerow(["timestamp", "language", "project", "config", "status", "detail"])
        total = len(combos)
        for i, (lang, proj, cfg) in enumerate(combos, 1):
            if (lang, proj, cfg) in done:
                print(f"[{i}/{total}] SKIP (already triggered) {lang}/{proj}/{cfg}")
                continue
            ok, detail = trigger(lang, proj, cfg)
            status = "ok" if ok else "FAILED"
            w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), lang, proj, cfg, status, detail])
            f.flush()
            print(f"[{i}/{total}] {status} {lang}/{proj}/{cfg} {'' if ok else detail}")
            time.sleep(SLEEP_SEC)


if __name__ == "__main__":
    main()
