# DL65 report

Code commit: e7a897f2f81f74355672b483cbe01b00af202f92 (branch DL65-pool-cpu-and-runs-on, from DL63-runner-pool-fixes).

## What changed
1. **CPU cap.** `Probe.docker_cpus()` reads `docker info --format {{.NCPU}}` (inside WSL on Windows). `docker_ncpu` falls back to the `.wslconfig` processors value, then host CPUs. `cap_cpus` caps at NCPU - 1, minimum 1. Used in `sizing` (via `detect_host` -> `measured_sizing`) and when the pool-files step writes `POOL_CPUS`. Tests: 19/19 -> 18, NCPU 2 -> 1.
2. **CI_RUNS_ON warning.** After `gh variable set`, the step reads `.github/workflows/*.yml` of the step's `repo_path` (new `--repo-path` option on `plan`). Workflows with `runs-on:` and no `vars.CI_RUNS_ON` are listed in a warning; the step still passes. No repo path: a plain "not checked out here" note. Tested with a temp folder holding three workflows.

Docs: change note docs/architecture/changes/DL65-delivery.md. No feature spec text changed (Docs: none beyond the note).

## Commands
- `cd claude/plugins/delivery/tests && python3 -m unittest test_runner_pool test_load`: 152 tests, OK.
- `python3 tools/ci_areas.py --branch-advice`: "unreadable diff, treat as every area -> gh workflow run spec-lint.yml ...". Not run (needs gh and CI; not light).
- `python3 claude/plugins/docs/scripts/docs_check.py`: W1 (docs/work/DL63/REPORT.md, expected on a branch) and T2 warning (docs/features/test-cost/spec.md, not mine). No other findings.

READY
