# DL210 + DL211 report

Base check: `project-named-secret` is present in `templates/shared/.gitleaks.toml` (base origin/main).

## What changed
- DL210: `workflow_dispatch:` added to the rust, go and dotnet `ci.yml` templates (ts had it, with its `only` input).
- DL211: `gitleaks git` in all four `ci.yml` templates now passes `--log-opts="HEAD"`.
- DL211: global allowlist in `templates/shared/.gitleaks.toml` and the root `.gitleaks.toml` skips names ending in public_key; NULL/None/nil values; SQL placeholders ($1, ?, :name); a call wrapping an identifier (Some(x)); env var reads. The rule regex is unchanged (RE2 has no lookahead). Literal secrets still match.
- Tests: `test_dl210_ci_dispatch.py`, `test_dl211_secret_scan.py` (new). Spec text and notes (feature notes, architecture notes) added.

## Tests
- `python3 -m unittest test_dl210_ci_dispatch test_dl211_secret_scan test_dl186_gitleaks_config` (in delivery/tests): 12 OK.
- `python3 tools/test_delivery_ci.py --no-mutants`: 78 passed, 0 failed.
- `python3 claude/plugins/docs/scripts/docs_check.py`: only W1 (docs/work on branch, expected).
- `gh workflow run spec-lint.yml --ref DL211-ci-dispatch-and-scan -f areas=delivery`, run 43029414161, all jobs ended:
  - success: which areas, train cleanup, CI scripts and workflow templates, branch gate and trust rule, plugin ledger/recorder/watcher/hooks, artifact pruning, setup preflight, change notes enforced and folded, packaged-program smoke test, runner plan, area mapping, delivery scripts/CI templates/cleanup/prune/change notes
  - failure: docs check, W1 only (docs/work report; stripped before the join)
  - skipped: change notes folded, change notes, other areas' jobs, shard job

## Follow-ups
- The gitleaks binary test in test_dl186 skips when the binary is not fetchable; the new allowlist regexes were checked with Python `re` only (they use no lookaround, so RE2-safe).

Branch head: see `git rev-parse origin/DL211-ci-dispatch-and-scan` (code head 8d3bb09515f733212c7bf52fe08bccf171fc0618; the report commit follows).

READY
