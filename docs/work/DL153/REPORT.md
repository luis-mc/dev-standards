# DL153 report

Changed: `agent_ci.py` picks branches from open ledger agents, `--task`, `--branch` or `--all`; no ledger and no flag starts nothing; task ids parse after the prefix's last `/`; help and spec R13.77 name the force-cancel API. `tools/test_ci_speedups.py` helper now passes `--all` (plain scan moved).

Tests:
- `python3 -I -m unittest discover -s claude/plugins/delivery/tests -t claude/plugins/delivery/tests -p "test_dl153*.py"`: 6 ok.
- agent_ci cases of `tools/test_ci_speedups.py` (run by name, 9 cases): all ok.
- `docs_check.py`: G1 (generated decisions.md stale, not committed by rule) and M1 on delivery-speed (answered by `Docs: none` in the commit message); see below for the final run.

CI: `gh workflow run spec-lint.yml --ref DL153-agent-ci-wave -f areas=delivery`, run 42717104613.
- Success: which areas does this change touch; delivery - runner plan, artifact pruning, packaged-program smoke test, setup preflight, branch gate and trust rule, plugin ledger/recorder/watcher/hooks, train cleanup, area mapping, change notes enforced and folded, CI scripts and workflow templates; delivery scripts, CI templates, cleanup, prune, change notes.
- Skipped: change notes, change notes folded, specs/templates/AUTHSPEC, docs plugin, model profiles, branch gate shards, artifact renderer, transcript folds.
- Failure: docs check. Two errors only: G1 (generated `docs/architecture/decisions.md` stale; generated files are not committed, the release fold rebuilds it) and W1 (this report under docs/work/; stripped before the join, D9).

Branch head: see `git rev-parse origin/DL153-agent-ci-wave` (code commit d1680caf6c5ca84213da7717dfdcf5dec9132bfe plus this report commit).

READY
