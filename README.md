# Phase 1 RAFT Reproduction — Pipeline & Findings

Reproduction of ["The Effects of Computational Resources on Flaky Tests"](https://hub.docker.com/r/jonbell/raft/tags) (Silva et al., IEEE TSE 2024), scaled to a broad-survey design: **89 projects x 5 resource configs x 50 runs** (later corrected to 88 projects after a registry duplicate was found and merged — see "Known data issues" below), run entirely on GitHub Actions hosted runners.

## Repository layout

- `phase1_registry.py` / `phase1_registry.json` — builds the project registry from `jonbell/raft`'s Docker Hub tags.
- `phase1_runner.py` — runs a project's test suite N times under a given resource config inside the `jonbell/raft` Docker image; writes per-run JUnit-style results + an error log.
- `trigger_sweep.py` — fires the 445 `workflow_dispatch` calls (89 projects x 5 configs) that drive `.github/workflows/phase1-sweep.yml`.
- `.github/workflows/phase1-sweep.yml` — the GitHub Actions workflow: a 10-way offset matrix per (project, config), 5 runs each.
- `scripts/` — the post-collection pipeline: downloading artifacts, merging them into one dataset, the one-off registry-duplicate fix, and the statistical analysis (see §1 below for how they fit together).
- `results/` — the 8 output CSVs from that analysis, i.e. the actual findings (see §3 for what each one contains).

---

## 1. Pipeline overview

```
jonbell/raft Docker Hub tags
        |
        v
phase1_registry.py  -->  phase1_registry.json   (89 project keys, one Docker image tag each)
        |
        v
trigger_sweep.py  --(gh workflow run, 445x)-->  .github/workflows/phase1-sweep.yml
        |                                              |
        |                                              v
        |                                   10 parallel matrix jobs/run,
        |                                   5 runs each (offsets 0,5,...,45),
        |                                   phase1_runner.py inside each job
        |                                              |
        |                                              v
        |                                   actions/upload-artifact (if: always())
        |                                   name: {lang}-{project}-{config}-offset{N}
        v
download_artifacts_seq.sh  --(gh api .../artifacts/{id}/zip)-->  artifacts_raw/*.zip (4,450 files)
        |
        v
merge_data.py  -->  merged/all_test_results.csv   (11.49M rows)
        |
        v
fix_websocket_dup.py  (one-off correction, see below)
        |
        v
analyze.py + stats_lite.py  -->  analysis_results/*.csv   (8 files, published here under results/)
```

All of the scripts to the left of the arrows above live in `scripts/` (except `phase1_registry.py`, `phase1_runner.py`, `trigger_sweep.py`, and the workflow file, which live at the repo root since they predate this pipeline extension).

### 1.1 Why batches of 5 runs, not 50 or 300

GitHub Actions hosted runners have a **hard 6-hour execution cap per job** that cannot be raised. An earlier 50-run-per-job pilot lost an entire config's worth of data for one project when the job was killed mid-run, before its upload step could fire. `phase1-sweep.yml` instead runs a `strategy.matrix.offset: [0,5,10,...,45]` — 10 independent jobs per (project, config) combination, each doing only 5 runs via `phase1_runner.py --runs 5 --run-offset <offset>`. Every job uploads its own artifact with `if: always()`, so the worst-case data loss from any single crashed/timed-out job is 5 runs out of 50, not the whole batch.

`phase1_runner.py`'s `ResultWriter` also writes an error-log entry (`PULL_FAILED`, `FATAL`, `TIMEOUT`, `CONTAINER_FAILURE`, or `NO_TESTS_PARSED`) on every failure path before closing, so even a fully-failed 5-run job uploads a populated `errors/<project>.log` explaining why, instead of nothing.

### 1.2 Triggering: 445 workflow runs, 4,450 jobs

`trigger_sweep.py` loops over all 89 registry projects x 5 configs (Baseline, C=CPU, M=memory, D=disk, N=network) and fires one `gh workflow run phase1-sweep.yml -f language=... -f project=... -f config=...` per combination — 445 workflow_dispatch calls, each spawning its own 10-job offset matrix (445 x 10 = 4,450 jobs total).

### 1.3 A second GitHub limit we hadn't planned for: 24h queue-wait cap

Separately from the 6-hour *execution* cap, GitHub auto-cancels any job that waits **24 hours for a runner** without ever starting. With 4,450 jobs queued behind a ~20-way concurrency limit, throughput couldn't clear the full backlog before some jobs hit that wall: **106 of the 445 workflow runs were cancelled** (90 with zero data — all 10 offset-jobs timed out waiting; 18 with partial data), and 2 failed outright. These were identified by diffing uploaded-artifact names against the full 445-combo list, then re-triggered via `trigger_sweep.py` once concurrency slots freed up. All 108 backfilled combos succeeded on retry, bringing the sweep to 445/445 complete.

### 1.4 Downloading the artifacts

4,450 artifacts were pulled via `gh api repos/.../actions/artifacts/{id}/zip`. One bug surfaced here, worth noting since it explains why `scripts/download_artifacts_seq.sh` and `scripts/merge_data.py` are shaped the way they are:

- An initial concurrent download attempt (`xargs -P 12`) failed almost universally with `404 Not Found`, while manual single-request tests succeeded — this initially looked like a GitHub-side rate-limit/redirect race under concurrency. The real root cause, found afterward, was unrelated to concurrency at all: the box has no `unzip` binary installed, so every download's post-extraction step silently failed and got misreported as a download failure (the "404" was a red herring from an unrelated, earlier diagnostic pass). The fix was to skip the extraction step entirely and read each zip's contents directly in Python via the standard-library `zipfile` module (`download_artifacts_seq.sh` now just downloads and validates each zip; `merge_data.py` reads `results/*.csv` and `errors/*.log` straight out of the zip in memory). Downloaded sequentially with a small delay to be a well-behaved API client: **4,450/4,450 succeeded, 0 failures.**

### 1.5 Merging and analysis

`merge_data.py` concatenates every `results/<project>.csv` member across all 4,450 zips into one `merged/all_test_results.csv` (11,489,310 rows), de-duplicating exact `(language, project, config, run_index, classname, testname)` collisions — 205,983 such duplicates existed, from the 18 partially-cancelled combos above, where retrigger reran some offsets that had already produced valid data the first time.

`analyze.py` reads that master CSV and computes flakiness statistics and RAFT-test identification, using `stats_lite.py` — a small pure-Python reimplementation of the Fisher's exact test, McNemar's test, Wilcoxon signed-rank test, and chi-square test of independence that `scipy` would normally provide (no `pip`/`sudo` access on this box to install it; each function was spot-checked against known reference values, e.g. `chi2_sf(3.841, 1) ≈ 0.05`).

---

## 2. Known data issues

- **`tootallnate_java-websocket` / `tootallnate.java-websocket` duplicate (fixed).** The registry-building regex (extended earlier in this project to catch 16 previously-missed Java sub-module tags) created two separate project keys for what is the same upstream project, differing only by `_` vs `.` in the Docker tag and a one-character difference in the commit SHA (`fa3909c3` vs `fa3909c`) — almost certainly the same commit under two abbreviation lengths. `fix_websocket_dup.py` merged them: the dot-variant's rows were relabeled to the underscore-variant's project key and its `run_index` shifted +50 (1-46 -> 51-96) so the two independently-collected ~50-run batches combine into one 96-run dataset instead of colliding. All `analysis_results/*.csv` reflect the merged, corrected data. The registry file itself (`phase1_registry.json`) still has both keys — only the collected data was fixed.
- **3 JS projects produced zero usable data:** `badges-shields`, `bubenshchykov-ngrok`, `icedfrisby-icedfrisby` — every run for these consistently exceeded `phase1_runner.py`'s internal 25-minute per-run timeout (`TIMEOUT` errors in `merged/all_errors.log`), i.e. their own test suites are simply too slow to fit the budget, not a pipeline defect. **85 of the 88 (deduped) projects have usable data.**
- **50 runs/config vs. the original paper's 300.** This was a deliberate scope decision (see project history) to make an 89-project x 5-config survey tractable on free GitHub Actions runners. It gives materially less statistical power per test than the paper's design — visible directly in RQ2 below, where only 10 of 217 raw RAFT-test candidates survive multiple-testing correction. Treat single-test-level significance claims cautiously; aggregate/paired trends (RQ1) are far more robust since they pool across tens of thousands of tests.

---

## 3. What each CSV is and how to read it

All files are in the [`results/`](results/) folder. `per_test_config_summary.csv` and `test_level_baseline_vs_config_fisher.csv` are large (36-45 MB); the rest are small enough to open directly in Excel/Sheets.

Not included in this repo (too large for git / regenerable from the above): `merged/all_test_results.csv` (11.49M rows, ~1.5 GB) and `merged/all_errors.log` (~66 MB), the intermediate outputs of `scripts/merge_data.py`. Re-run the pipeline in §1 to regenerate them from the 4,450 GitHub Actions artifacts if needed.

### `per_test_config_summary.csv`
The base table everything else is derived from — one row per **(test, config)** combination actually observed in the data.

| Column | Meaning |
|---|---|
| `language` | `java`, `python`, or `js` |
| `project` | registry project key |
| `classname` | test class / file (JUnit classname, Python module path, or JS test-file name) |
| `testname` | individual test method/case name |
| `config` | `Baseline`, `C` (CPU), `M` (memory), `D` (disk), or `N` (network) |
| `n_pass` / `n_fail` | count of passing / failing (`failure`+`error` combined) runs for this test under this config |
| `n_skipped` | count of runs where the test was skipped (excluded from flakiness calc) |
| `n_other` | anything not pass/fail/skipped (rare, parser edge cases) |
| `n_valid` | `n_pass + n_fail` — the denominator used for `fail_rate` |
| `fail_rate` | `n_fail / n_valid` |
| `is_flaky` | `True` iff `n_pass > 0 AND n_fail > 0` (i.e. the test showed both outcomes under this config) |

### `test_level_baseline_vs_config_fisher.csv`
Per-test significance test: for every test with >=10 valid runs at **both** Baseline and a given constrained config, is that config's failure rate significantly higher than Baseline's? One row per (test, config) pair, config in {C, M, D, N}.

| Column | Meaning |
|---|---|
| `language`,`project`,`classname`,`testname`,`config` | identifies the test/config pair |
| `baseline_n_valid`, `baseline_fail_rate` | Baseline-side sample size and fail rate |
| `config_n_valid`, `config_fail_rate` | constrained-config-side sample size and fail rate |
| `delta_fail_rate` | `config_fail_rate - baseline_fail_rate` |
| `fisher_p_greater` | one-sided Fisher's exact test p-value (H1: config fail rate > baseline fail rate) |
| `fisher_q_bh` | Benjamini-Hochberg corrected p-value, across all tests compared for that config |
| `significant_q05` | `True` if `fisher_q_bh < 0.05` |

### `flaky_rate_by_config_summary.csv` — **answers RQ1**
One row per config (Baseline + C/M/D/N), aggregate flakiness comparison.

| Column | Meaning |
|---|---|
| `n_tests_present` | number of distinct tests observed under this config |
| `n_tests_flaky` / `pct_flaky` | count / percent of those tests that are flaky (mixed pass+fail) |
| `mean_fail_rate` | average `fail_rate` across all tests present |
| `n_paired_with_baseline` | number of tests present in **both** Baseline and this config (the paired-test population) |
| `mcnemar_b_config_flaky_only` | of paired tests: count flaky under this config but NOT flaky at Baseline |
| `mcnemar_c_baseline_flaky_only` | of paired tests: count flaky at Baseline but NOT flaky under this config |
| `mcnemar_stat`, `mcnemar_p` | McNemar's test (continuity-corrected) on the b/c discordant pairs — the primary RQ1 significance test |
| `wilcoxon_stat`, `wilcoxon_p` | Wilcoxon signed-rank test on paired per-test fail-rate deltas (normal approximation) |
| `mean_fail_rate_delta_vs_baseline` | mean of (config fail_rate - baseline fail_rate) across paired tests |

### `raft_tests.csv` — **answers RQ2**
Tests that were **completely stable at Baseline** (`n_fail == 0`, i.e. 0% baseline fail rate) but became flaky under a constrained config. This is the literal "RAFT" (Resource-Affected Flaky Test) definition. One row per (test, config) instance.

| Column | Meaning |
|---|---|
| `language`,`project`,`classname`,`testname`,`config` | identifies the instance |
| `baseline_n_valid`, `baseline_n_fail` | Baseline sample size (n_fail is always 0 by definition) |
| `config_n_valid`, `config_n_fail`, `config_fail_rate` | constrained-config sample size/failures/rate |
| `fisher_p_greater`, `fisher_q_bh`, `significant_q05` | same Fisher/BH significance test as above, carried over where available (blank if either side had <10 valid runs) |

### `raft_summary_by_project.csv`
RAFT-test counts rolled up per project. One row per project.

| Column | Meaning |
|---|---|
| `n_tests_at_baseline` | total distinct tests observed for this project at Baseline |
| `raft_tests_C` / `_M` / `_D` / `_N` | count of RAFT tests found under each config |
| `raft_tests_any_config` | count of distinct tests that are RAFT under **at least one** config (not a sum — a test RAFT under 2 configs counts once here) |

### `error_messages_raft.csv`
Every distinct failure/error message text seen for RAFT tests, under the config that made them flaky. One row per (test, config, distinct message).

| Column | Meaning |
|---|---|
| ...`config` | which constrained config produced this failure |
| `message` | the raw failure message (assertion text, exception message, etc.), truncated to 500 chars |
| `message_category` | auto-classified bucket (see below) |
| `occurrence_count` | how many of that test's runs under that config produced this exact message |

### `error_messages_baseline_flaky.csv`
Same structure, for the comparison group: tests that were **already flaky at Baseline** (ordinary flakiness, not resource-induced). Columns identical minus `config` (always Baseline).

**Message categorization** (`message_category`, used in both files above) is a simple keyword classifier over the message text: `OOM/memory`, `timeout`, `network/connection`, `disk`, `null/undefined reference`, `concurrency`, `index out of bounds`, `assertion mismatch`, `missing class/module`, `permission`, `stack overflow`, `empty/none`, or `other` (catch-all for anything not matching a known pattern).

### `error_message_category_comparison.csv` — **answers RQ3**
Aggregated category distribution, RAFT-failures vs. baseline-flaky-failures, plus a chi-square test of independence.

| Column | Meaning |
|---|---|
| `message_category` | one of the buckets above |
| `raft_occurrences`, `raft_pct` | count / percent of all RAFT-failure messages in this category |
| `baseline_flaky_occurrences`, `baseline_flaky_pct` | count / percent of all baseline-flaky-failure messages in this category |
| (trailing block) `chi2_stat`, `p_value`, `dof` | chi-square test of independence: does the category distribution differ between RAFT and baseline-flaky failures? |

---

## 4. Research questions, answered from the data

Numbers below are pulled directly from the CSVs in this folder (post websocket-merge correction).

### RQ1 — Does resource constraint make flaky tests happen more frequently?

**Yes, for CPU, memory, and network throttling — not measurably for disk throttling**, using McNemar's paired test (same test, Baseline vs. constrained) on the flaky/not-flaky classification, from `flaky_rate_by_config_summary.csv`:

| Config | Tests present | Flaky | Flaky rate | Paired w/ Baseline | Newly-flaky only | Un-flaky only | McNemar p | Wilcoxon p |
|---|---|---|---|---|---|---|---|---|
| Baseline | 74,261 | 127 | 0.17% | — | — | — | — | — |
| C (CPU) | 52,306 | 96 | 0.18% | 52,306 | 72 | 18 | **2.31e-08** | 7.40e-08 |
| M (memory) | 54,854 | 113 | 0.21% | 54,850 | 91 | 15 | **3.23e-13** | 2.21e-11 |
| D (disk) | 60,572 | 49 | 0.08% | 60,570 | 19 | 17 | 0.868 (n.s.) | 0.792 (n.s.) |
| N (network) | 74,261 | 153 | 0.21% | 74,261 | 45 | 19 | **1.78e-03** | 7.84e-11 |

Reading the "newly-flaky vs un-flaky" columns: under CPU throttling, 72 tests became flaky that weren't at Baseline, versus only 18 that stopped being flaky — a 4:1 imbalance, and McNemar's test says that's essentially impossible under the null hypothesis (p=2.3e-08). Memory throttling is the strongest effect (91 vs 15, p=3.2e-13). Network shows the same direction but a smaller, still-significant effect (45 vs 19). **Disk throttling shows no significant effect** (19 vs 17, p=0.87) — essentially a coin flip.

A second, independent signal points the same way: `n_tests_present` drops sharply under C/M/D (52,306 / 54,854 / 60,572 vs. 74,261 at Baseline and under N) — meaning a meaningful fraction of tests under CPU/memory/disk pressure didn't even produce a clean pass/fail result at all (suites crashing, OOMing, or timing out outright rather than individual tests flaking). That's a resource effect on its own, arguably more severe than flakiness, and it's *not* counted in the flaky-rate numbers above since those require `n_valid >= 2`.

One nuance: `mean_fail_rate` under C (0.66%) is actually *lower* than Baseline's (1.04%), even though more tests are classified flaky. This isn't a contradiction — it means CPU throttling converts a larger *number* of previously-always-passing tests into *occasionally*-failing ones, rather than making already-shaky tests fail more often on average.

### RQ2 — How many tests become flaky *only* under resource constraint (RAFT tests)?

Statistics-first attempt: applying Fisher's exact test (one-sided) + Benjamini-Hochberg correction to every candidate RAFT instance (from `raft_tests.csv`), only **10 of 217** test x config instances remain significant at q<0.05 (6 under C, 4 under M, 0 under D or N). That's not a promising signal on its own — with only 50 runs/config, a test that fails e.g. 2/50 times under a constrained config and 0/50 at Baseline doesn't clear a strict multiple-testing bar. This is the exact underpowered-sample effect flagged as a risk when 50 runs was chosen over the paper's 300.

Falling back to the raw operational definition you specified (baseline always-pass, constrained-config flaky, no significance filter):

- **217 test x config RAFT instances**, covering **176 unique tests** (some tests are RAFT under more than one config).
- Split by config: **M = 91**, **C = 70**, **N = 39**, **D = 17**. Memory pressure is by far the most common trigger of new flakiness, consistent with RQ1's finding that M has the strongest overall effect.
- RAFT tests are concentrated, not evenly spread: only **27 of 85 projects (32%)** have any RAFT tests at all. `raft_summary_by_project.csv`'s top contributors:
  - `pypa-setuptools` (python): 84 RAFT tests, almost entirely under M (82) with a smaller cluster under N (25) — one project accounts for ~39% of all RAFT instances found.
  - `tootallnate_java-websocket` (java): 14, spread across all four configs (11 C, 6 N, 5 M, 4 D) — the only project where every constrained config triggers some new flakiness, worth prioritizing for the root-cause deep-dive.
  - `orbit_orbit` (java): 5, `activiti_activiti` (java): 3, `apache_incubator-dubbo` (java): 1.
  - The remaining 22 projects with RAFT tests weren't in the top-5 cut but are listed in full in `raft_summary_by_project.csv`.

**Bottom line:** resource-constraint-induced flakiness is real but concentrated — a small minority of projects (and within those, often one memory-sensitive test class) account for most of it, rather than being a diffuse effect spread evenly across the corpus.

### RQ3 — Are RAFT tests' error messages the same kind as regular flaky tests' error messages?

**No — the failure-message category distributions are significantly different** (chi-square test of independence, χ²=64.69, **p=8.98e-15**, from `error_message_category_comparison.csv`):

| Category | RAFT failures | Baseline-flaky failures |
|---|---|---|
| timeout | **10.33%** (81 occurrences) | **1.19%** (10 occurrences) |
| assertion mismatch | 15.69% (123) | 16.03% (135) |
| other (uncategorized) | 73.98% (580) | 82.78% (697) |

The clearest, most interpretable difference: RAFT-test failures are **~9x more likely to be classified as timeouts** than ordinary baseline-flaky failures (10.3% vs 1.2%) — directly consistent with what resource throttling does (CPU/memory/network pressure makes operations that would otherwise finish in time run out the clock). Assertion-mismatch-style failures, by contrast, occur at essentially the *same* rate in both groups (~15-16%) — suggesting that mechanism (order-dependency, shared mutable state, race conditions manifesting as a wrong value rather than a hang) isn't specifically a resource-constraint phenomenon; it's a general flakiness mechanism that resource pressure doesn't obviously amplify or suppress.

Caveat: "other" is the largest bucket in both groups (74-83%) — the keyword classifier is deliberately conservative (matches common exception/assertion vocabulary) and doesn't attempt project-specific message parsing, so a meaningful share of both groups' real failure reasons aren't captured by the 11 named categories. The timeout-vs-assertion split above is the reliable part of this result; the "other" bucket would need manual inspection (e.g. via `error_messages_raft.csv` directly) to break down further.
