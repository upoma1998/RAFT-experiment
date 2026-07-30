# RAFT Phase 1 Reproduction (GitHub Actions runner)

Reruns the Docker-based test harness from ["The Effects of Computational
Resources on Flaky Tests"](https://doi.org/10.1109/TSE.2024.3462251) (Silva
et al., IEEE TSE 2024) using the `jonbell/raft` Docker images, at reduced
scale (10 runs per config instead of 300).

- `phase1_runner.py` — drives one project through all/some of Table I's 16
  throttling configs (CPU/Memory via Docker flags, Disk via blkio limits,
  Network via `tc` in a derived image), parsing JUnit/pytest/Jest output into
  a per-project CSV plus an error log.
- `phase1_registry.py` / `phase1_registry.json` — maps project keys to
  `jonbell/raft` image tags, built from the live Docker Hub tag list.
- `.github/workflows/phase1-{java,python,js}.yml` — one matrix job per
  project, each uploading its `results.csv` + `errors.log` as a build
  artifact.

Trigger manually via the Actions tab ("Run workflow") on each of the three
workflows. Download artifacts afterward and merge into a local
`phase1-results/{java,python,js}/{results,errors}/` tree.
