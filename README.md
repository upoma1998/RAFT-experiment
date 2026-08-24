# RAFT Phase 1 Reproduction (GitHub Actions runner)

Reruns the Docker-based test harness from ["The Effects of Computational
Resources on Flaky Tests"](https://doi.org/10.1109/TSE.2024.3462251) (Silva
et al., IEEE TSE 2024) using the `jonbell/raft` Docker images, at reduced
scale (50 runs per config instead of 300), across every project currently
published on Docker Hub.

- `phase1_runner.py` — drives one project through all/some of Table I's 16
  throttling configs (CPU/Memory via Docker flags, Disk via blkio limits,
  Network via `tc` in a derived image), parsing JUnit/pytest/Jest output into
  a per-project CSV plus an error log. Supports `--run-offset` so multiple
  batches can append non-overlapping runs to the same CSV.
- `phase1_registry.py` / `phase1_registry.json` — maps project keys to
  `jonbell/raft` image tags, built from the live Docker Hub tag list (89
  projects: 44 java, 20 python, 25 js).
- `.github/workflows/phase1-sweep.yml` — one `workflow_dispatch` run covers
  a single (language, project, config) combination, split into 10 jobs of 5
  runs each (offsets 0,5,...,45) so a job timeout or crash never loses more
  than 5 runs. Each job uploads its partial results CSV + error log
  (`if: always()`) regardless of whether it succeeded, timed out, or the
  image failed to pull/run.

## Running the full sweep

89 projects x 5 configs (Baseline, C, M, D, N) x 50 runs = 22,250 test-runs,
triggered as 445 separate `workflow_dispatch` calls (one per
project x config), each spawning 10 jobs = 4,450 jobs total.

`trigger_sweep.py` drives this: it reads `phase1_registry.json`, fires one
`gh workflow run phase1-sweep.yml -f language=... -f project=... -f config=...`
per combination, and logs each attempt to `trigger_log.csv` (skipping
combinations already logged `ok` on rerun, so it's safe to re-invoke after an
interruption). Requires `gh` authenticated with the `workflow` scope
(`gh auth refresh -s workflow`) since it's pushing/dispatching workflow runs.

```
python3 trigger_sweep.py                                            # fire all 445
python3 trigger_sweep.py java:tootallnate_java-websocket:Baseline   # just one, for a smoke test
```

Download artifacts afterward and merge into a local
`phase1-results/{java,python,js}/{results,errors}/` tree, using the
`offset` embedded in each artifact name to reassemble the full 0-49 run
sequence per project/config.
