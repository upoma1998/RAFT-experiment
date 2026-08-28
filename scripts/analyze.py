#!/usr/bin/env python3
"""
Answers (using merged/all_test_results.csv):
  Q1. Does resource constraint make flaky tests happen more frequently?
  Q2. How many tests become flaky ONLY under resource constraint (RAFT tests)?
  Q3. Are RAFT tests' error messages the same kind as regular flaky tests' error messages?

Writes CSVs to analysis_results/.
"""
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

from stats_lite import fisher_exact_greater, mcnemar as _mcnemar, wilcoxon_signed_rank, chi2_contingency

ROOT = Path.home() / "raft-analysis"
MERGED_CSV = ROOT / "merged" / "all_test_results.csv"
OUT = ROOT / "analysis_results"
OUT.mkdir(exist_ok=True)

CONSTRAINED_CONFIGS = ["C", "M", "D", "N"]
ALL_CONFIGS = ["Baseline"] + CONSTRAINED_CONFIGS
MIN_VALID_FOR_TEST_STATS = 10  # min runs per side to run a per-test Fisher test
ALPHA = 0.05

FAIL_STATUSES = {"failure", "error"}
PASS_STATUSES = {"pass"}
# 'skipped' and anything else (e.g. 'unknown') are excluded from valid runs


def bh_adjust(pvals):
    """Benjamini-Hochberg. pvals: list of floats (may include None). Returns list of q-values (None preserved)."""
    idx = [i for i, p in enumerate(pvals) if p is not None]
    m = len(idx)
    if m == 0:
        return [None] * len(pvals)
    ranked = sorted(idx, key=lambda i: pvals[i])
    q = [None] * len(pvals)
    prev = 1.0
    for rank in range(m, 0, -1):
        i = ranked[rank - 1]
        val = pvals[i] * m / rank
        val = min(val, prev) if rank < m else val
        val = min(val, 1.0)
        prev = val
        q[i] = val
    return q


def classify_message(msg):
    m = (msg or "").lower()
    if not m.strip():
        return "empty/none"
    if "outofmemory" in m or "out of memory" in m or "cannot allocate memory" in m or "gc overhead" in m:
        return "OOM/memory"
    if "timeout" in m or "timed out" in m or "timeoutexception" in m:
        return "timeout"
    if any(k in m for k in ["connection refused", "connectexception", "unknownhostexception",
                             "socketexception", "network is unreachable", "econnrefused",
                             "socket hang up", "enotfound", "etimedout"]):
        return "network/connection"
    if "no space left on device" in m or "disk quota" in m or "enospc" in m:
        return "disk"
    if "nullpointerexception" in m or "cannot read propert" in m or "is not a function" in m or "undefined is not" in m:
        return "null/undefined reference"
    if "concurrentmodificationexception" in m or "race condition" in m or "deadlock" in m:
        return "concurrency"
    if "indexoutofbounds" in m or "index out of range" in m:
        return "index out of bounds"
    if any(k in m for k in ["expected:", "expected <", "but was", "assertionerror", "assertequals",
                             "to equal", "to be", "assert_equal", "assertion failed"]):
        return "assertion mismatch"
    if "classnotfound" in m or "noclassdeffound" in m or "modulenotfound" in m or "cannot find module" in m:
        return "missing class/module"
    if "permission denied" in m or "eacces" in m:
        return "permission"
    if "stackoverflow" in m:
        return "stack overflow"
    return "other"


def main():
    # ---- Load & aggregate ----
    # key: (lang, project, classname, testname, config) -> counts
    agg = defaultdict(lambda: {"pass": 0, "fail": 0, "skipped": 0, "other": 0})
    messages = defaultdict(lambda: defaultdict(int))  # same key -> message -> count

    print("Loading merged CSV...", file=sys.stderr)
    with open(MERGED_CSV, newline="", errors="replace") as f:
        r = csv.DictReader(f)
        n = 0
        for row in r:
            n += 1
            if n % 500000 == 0:
                print(f"  ...{n} rows", file=sys.stderr)
            lang, project, config, run_idx, classname, testname, status, message = (
                row["language"], row["project"], row["config"], row["run_index"],
                row["classname"], row["testname"], row["status"], row["message"])
            key = (lang, project, classname, testname, config)
            if status in PASS_STATUSES:
                agg[key]["pass"] += 1
            elif status in FAIL_STATUSES:
                agg[key]["fail"] += 1
                if message:
                    messages[key][message.strip()[:500]] += 1
            elif status == "skipped":
                agg[key]["skipped"] += 1
            else:
                agg[key]["other"] += 1
    print(f"Loaded {n} rows, {len(agg)} (test,config) groups", file=sys.stderr)

    # ---- 1. per_test_config_summary.csv ----
    per_test_path = OUT / "per_test_config_summary.csv"
    test_stats = {}  # (lang,project,classname,testname,config) -> dict
    with open(per_test_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["language", "project", "classname", "testname", "config",
                     "n_pass", "n_fail", "n_skipped", "n_other", "n_valid", "fail_rate", "is_flaky"])
        for key in sorted(agg):
            lang, project, classname, testname, config = key
            c = agg[key]
            n_valid = c["pass"] + c["fail"]
            fail_rate = (c["fail"] / n_valid) if n_valid else None
            is_flaky = bool(n_valid >= 2 and c["pass"] > 0 and c["fail"] > 0)
            w.writerow([lang, project, classname, testname, config,
                        c["pass"], c["fail"], c["skipped"], c["other"], n_valid,
                        f"{fail_rate:.4f}" if fail_rate is not None else "", is_flaky])
            test_stats[key] = dict(n_pass=c["pass"], n_fail=c["fail"], n_valid=n_valid,
                                    fail_rate=fail_rate, is_flaky=is_flaky)
    print(f"-> {per_test_path}", file=sys.stderr)

    # index by (lang,project,classname,testname) -> {config: stats}
    by_test = defaultdict(dict)
    for (lang, project, classname, testname, config), s in test_stats.items():
        by_test[(lang, project, classname, testname)][config] = s

    # ---- 2. test_level_baseline_vs_config_fisher.csv ----
    fisher_path = OUT / "test_level_baseline_vs_config_fisher.csv"
    fisher_rows = []  # accumulate then BH-adjust per config
    for config in CONSTRAINED_CONFIGS:
        pvals = []
        rows_for_config = []
        for test_key, cfgmap in by_test.items():
            base = cfgmap.get("Baseline")
            cur = cfgmap.get(config)
            if not base or not cur:
                continue
            if base["n_valid"] < MIN_VALID_FOR_TEST_STATS or cur["n_valid"] < MIN_VALID_FOR_TEST_STATS:
                continue
            try:
                p = fisher_exact_greater(cur["n_fail"], cur["n_pass"], base["n_fail"], base["n_pass"])
            except Exception:
                p = None
            pvals.append(p)
            rows_for_config.append((test_key, config, base, cur, p))
        qvals = bh_adjust(pvals)
        for (test_key, config, base, cur, p), q in zip(rows_for_config, qvals):
            fisher_rows.append((test_key, config, base, cur, p, q))

    with open(fisher_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["language", "project", "classname", "testname", "config",
                     "baseline_n_valid", "baseline_fail_rate", "config_n_valid", "config_fail_rate",
                     "delta_fail_rate", "fisher_p_greater", "fisher_q_bh", "significant_q05"])
        for test_key, config, base, cur, p, q in fisher_rows:
            lang, project, classname, testname = test_key
            delta = (cur["fail_rate"] or 0) - (base["fail_rate"] or 0)
            w.writerow([lang, project, classname, testname, config,
                        base["n_valid"], f"{base['fail_rate']:.4f}",
                        cur["n_valid"], f"{cur['fail_rate']:.4f}",
                        f"{delta:.4f}",
                        f"{p:.6g}" if p is not None else "",
                        f"{q:.6g}" if q is not None else "",
                        bool(q is not None and q < ALPHA)])
    print(f"-> {fisher_path}", file=sys.stderr)

    # ---- 3. flaky_rate_by_config_summary.csv (Q1: aggregate + McNemar + Wilcoxon) ----
    summary_path = OUT / "flaky_rate_by_config_summary.csv"
    with open(summary_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["config", "n_tests_present", "n_tests_flaky", "pct_flaky", "mean_fail_rate",
                     "n_paired_with_baseline", "mcnemar_b_config_flaky_only",
                     "mcnemar_c_baseline_flaky_only", "mcnemar_stat", "mcnemar_p",
                     "wilcoxon_stat", "wilcoxon_p", "mean_fail_rate_delta_vs_baseline"])
        # baseline row
        base_tests = {k: v for k, v in test_stats.items() if k[4] == "Baseline"}
        base_n = len(base_tests)
        base_flaky = sum(1 for v in base_tests.values() if v["is_flaky"])
        base_rates = [v["fail_rate"] for v in base_tests.values() if v["fail_rate"] is not None]
        base_mean = sum(base_rates) / len(base_rates) if base_rates else 0
        w.writerow(["Baseline", base_n, base_flaky,
                     f"{100*base_flaky/base_n:.2f}" if base_n else "", f"{base_mean:.4f}",
                     "", "", "", "", "", "", "", ""])

        for config in CONSTRAINED_CONFIGS:
            cfg_tests = {k: v for k, v in test_stats.items() if k[4] == config}
            cfg_n = len(cfg_tests)
            cfg_flaky = sum(1 for v in cfg_tests.values() if v["is_flaky"])
            cfg_rates = [v["fail_rate"] for v in cfg_tests.values() if v["fail_rate"] is not None]
            cfg_mean = sum(cfg_rates) / len(cfg_rates) if cfg_rates else 0

            # paired (test present in both baseline and this config)
            b_only = 0  # flaky in config, not in baseline (discordant favoring config)
            c_only = 0  # flaky in baseline, not in config
            paired_deltas = []
            n_paired = 0
            for test_key, cfgmap in by_test.items():
                base = cfgmap.get("Baseline")
                cur = cfgmap.get(config)
                if not base or not cur:
                    continue
                n_paired += 1
                if cur["is_flaky"] and not base["is_flaky"]:
                    b_only += 1
                elif base["is_flaky"] and not cur["is_flaky"]:
                    c_only += 1
                if base["fail_rate"] is not None and cur["fail_rate"] is not None:
                    paired_deltas.append(cur["fail_rate"] - base["fail_rate"])

            mstat, mp = _mcnemar(b_only, c_only)
            try:
                nonzero = [d for d in paired_deltas if d != 0]
                if len(nonzero) >= 10:
                    wstat, wp = wilcoxon_signed_rank(nonzero)
                else:
                    wstat, wp = None, None
            except Exception:
                wstat, wp = None, None
            mean_delta = (sum(paired_deltas) / len(paired_deltas)) if paired_deltas else None

            w.writerow([config, cfg_n, cfg_flaky,
                        f"{100*cfg_flaky/cfg_n:.2f}" if cfg_n else "", f"{cfg_mean:.4f}",
                        n_paired, b_only, c_only,
                        f"{mstat:.4f}" if mstat is not None else "",
                        f"{mp:.6g}" if mp is not None else "",
                        f"{wstat:.4f}" if wstat is not None else "",
                        f"{wp:.6g}" if wp is not None else "",
                        f"{mean_delta:.4f}" if mean_delta is not None else ""])
    print(f"-> {summary_path}", file=sys.stderr)

    # ---- 4. raft_tests.csv (Q2: baseline always-pass, but flaky under a constrained config) ----
    raft_path = OUT / "raft_tests.csv"
    raft_keys = []  # (test_key, config)
    with open(raft_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["language", "project", "classname", "testname", "config",
                     "baseline_n_valid", "baseline_n_fail", "config_n_valid", "config_n_fail",
                     "config_fail_rate", "fisher_p_greater", "fisher_q_bh", "significant_q05"])
        fisher_lookup = {(tk, cfg): (p, q) for tk, cfg, base, cur, p, q in fisher_rows}
        for test_key, cfgmap in by_test.items():
            base = cfgmap.get("Baseline")
            if not base or base["n_valid"] < 2 or base["n_fail"] != 0:
                continue  # require baseline to be observed and always pass
            for config in CONSTRAINED_CONFIGS:
                cur = cfgmap.get(config)
                if not cur or not cur["is_flaky"]:
                    continue
                lang, project, classname, testname = test_key
                p, q = fisher_lookup.get((test_key, config), (None, None))
                w.writerow([lang, project, classname, testname, config,
                            base["n_valid"], base["n_fail"], cur["n_valid"], cur["n_fail"],
                            f"{cur['fail_rate']:.4f}",
                            f"{p:.6g}" if p is not None else "",
                            f"{q:.6g}" if q is not None else "",
                            bool(q is not None and q < ALPHA)])
                raft_keys.append((test_key, config))
    print(f"-> {raft_path} ({len(raft_keys)} RAFT test x config rows)", file=sys.stderr)

    # ---- 5. raft_summary_by_project.csv ----
    proj_raft = defaultdict(lambda: defaultdict(int))  # (lang,project) -> config -> count
    proj_totals = defaultdict(set)  # (lang,project) -> set of test_keys seen at baseline
    for test_key, cfgmap in by_test.items():
        lang, project = test_key[0], test_key[1]
        if "Baseline" in cfgmap:
            proj_totals[(lang, project)].add(test_key)
    for test_key, config in raft_keys:
        lang, project = test_key[0], test_key[1]
        proj_raft[(lang, project)][config] += 1

    raft_summary_path = OUT / "raft_summary_by_project.csv"
    with open(raft_summary_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["language", "project", "n_tests_at_baseline"] + [f"raft_tests_{c}" for c in CONSTRAINED_CONFIGS] + ["raft_tests_any_config"])
        for (lang, project), n_base_tests in sorted(proj_totals.items()):
            counts = [proj_raft[(lang, project)].get(c, 0) for c in CONSTRAINED_CONFIGS]
            any_config_tests = set()
            for test_key, config in raft_keys:
                if test_key[0] == lang and test_key[1] == project:
                    any_config_tests.add(test_key)
            w.writerow([lang, project, len(n_base_tests)] + counts + [len(any_config_tests)])
    print(f"-> {raft_summary_path}", file=sys.stderr)

    # ---- 6/7. error message tables ----
    raft_test_set = set(tk for tk, cfg in raft_keys)  # tests that are RAFT under >=1 config
    # regular flaky = flaky at baseline (has both pass and fail at baseline)
    regular_flaky_keys = [k[:4] for k, v in test_stats.items() if k[4] == "Baseline" and v["is_flaky"]]

    raft_msg_path = OUT / "error_messages_raft.csv"
    with open(raft_msg_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["language", "project", "classname", "testname", "config", "message", "message_category", "occurrence_count"])
        for test_key, config in raft_keys:
            key = test_key + (config,)
            for msg, cnt in sorted(messages.get(key, {}).items(), key=lambda x: -x[1]):
                lang, project, classname, testname = test_key
                w.writerow([lang, project, classname, testname, config, msg, classify_message(msg), cnt])
    print(f"-> {raft_msg_path}", file=sys.stderr)

    baseline_flaky_msg_path = OUT / "error_messages_baseline_flaky.csv"
    with open(baseline_flaky_msg_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["language", "project", "classname", "testname", "message", "message_category", "occurrence_count"])
        for test_key in regular_flaky_keys:
            key = test_key + ("Baseline",)
            for msg, cnt in sorted(messages.get(key, {}).items(), key=lambda x: -x[1]):
                lang, project, classname, testname = test_key
                w.writerow([lang, project, classname, testname, msg, classify_message(msg), cnt])
    print(f"-> {baseline_flaky_msg_path}", file=sys.stderr)

    # ---- 8. error_message_category_comparison.csv (Q3) ----
    raft_cat_counts = defaultdict(int)
    for test_key, config in raft_keys:
        key = test_key + (config,)
        for msg, cnt in messages.get(key, {}).items():
            raft_cat_counts[classify_message(msg)] += cnt

    baseline_flaky_cat_counts = defaultdict(int)
    for test_key in regular_flaky_keys:
        key = test_key + ("Baseline",)
        for msg, cnt in messages.get(key, {}).items():
            baseline_flaky_cat_counts[classify_message(msg)] += cnt

    all_cats = sorted(set(raft_cat_counts) | set(baseline_flaky_cat_counts))
    cat_cmp_path = OUT / "error_message_category_comparison.csv"
    with open(cat_cmp_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["message_category", "raft_occurrences", "raft_pct",
                     "baseline_flaky_occurrences", "baseline_flaky_pct"])
        raft_total = sum(raft_cat_counts.values()) or 1
        base_total = sum(baseline_flaky_cat_counts.values()) or 1
        for cat in all_cats:
            rc = raft_cat_counts.get(cat, 0)
            bc = baseline_flaky_cat_counts.get(cat, 0)
            w.writerow([cat, rc, f"{100*rc/raft_total:.2f}", bc, f"{100*bc/base_total:.2f}"])

        # chi-square test of independence on the category-distribution contingency table
        table = [[raft_cat_counts.get(c, 0) for c in all_cats],
                  [baseline_flaky_cat_counts.get(c, 0) for c in all_cats]]
        try:
            table_nonzero_cols = [i for i in range(len(all_cats)) if table[0][i] + table[1][i] > 0]
            filtered = [[table[0][i] for i in table_nonzero_cols], [table[1][i] for i in table_nonzero_cols]]
            chi2_stat, chi2_p, dof = chi2_contingency(filtered)
        except Exception as e:
            chi2_stat, chi2_p, dof = None, None, None
        w.writerow([])
        w.writerow(["chi2_test_of_independence_raft_vs_baseline_flaky_categories"])
        w.writerow(["chi2_stat", "p_value", "dof"])
        w.writerow([f"{chi2_stat:.4f}" if chi2_stat is not None else "",
                     f"{chi2_p:.6g}" if chi2_p is not None else "", dof])
    print(f"-> {cat_cmp_path}", file=sys.stderr)

    print("DONE", file=sys.stderr)


if __name__ == "__main__":
    main()
