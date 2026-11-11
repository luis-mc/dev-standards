# DL237 report

Base check: origin/main 7bd26d6 has `[allowlist]` with `regexTarget = "line"` in the shipped `.gitleaks.toml`. Passed.

## What changed
- `claude/plugins/delivery/templates/shared/.gitleaks.toml`: two new allowlist regexes (RE2, no lookahead). Each pins the whole line.
  1. SQL placeholder (`$1`..`$99`, `?`, `:name`) bound to a `_key/_token/_secret/_pass` name, with more SQL after it. The line may hold at most one opening and one closing quote, and every `=` must be followed by a placeholder.
  2. Nested call as the value (`Some(Arc::new(x))`, `Box::new(load(x))`). The first argument is an identifier path that starts a call. No quote and no other `=` on the line.
- `claude/plugins/delivery/tests/test_dl237_gitleaks_shapes.py`: parses the toml; positive and negative fixtures built at run time; runs real gitleaks (built with `go install`) when present.
- Spec R13.3 (secret-scan paragraph), feature note `docs/features/delivery/changes/DL237.md`, change note `docs/architecture/changes/DL237-gitleaks-shapes.md`.

## Tests
- `python3 -m unittest test_dl237_gitleaks_shapes test_dl211_secret_scan test_dl186_gitleaks_config test_dl204_install_secret_scan` (in the delivery tests dir, gitleaks on PATH): 25 tests OK. The real-gitleaks test ran (not skipped): positives give no finding, negatives still give findings.
- `python3 tools/test_delivery_ci.py --no-mutants`: 78 passed, 0 failed.
- `python3 claude/plugins/docs/scripts/docs_check.py`: only W1 (this report under docs/work, expected).
- spec-lint run 43078658730 (areas=delivery), head 5bf22c4: delivery jobs all success (train cleanup, setup preflight, CI scripts and templates, branch gate and trust rule, area mapping, runner plan, change notes, ledger/recorder/watcher/hooks, artifact pruning, smoke test, aggregate). Skipped: the other area jobs and the shard job. `docs check` failed: W1 only (docs/work report; stripped before the join).

## Follow-ups
- The repository root `.gitleaks.toml` still lacks the two shapes (not owned by this task). Copy them there if wanted.
- The template description text still says "Three narrow exemptions"; not changed.
- Shapes are narrow on purpose: a SQL line with a quoted literal or a non-placeholder `=` stays scanned.

Branch head: see the last commit on DL237-gitleaks-shapes (code at 5bf22c4; this report is the next commit).

READY
