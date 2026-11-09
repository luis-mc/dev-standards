# DL153 report

Changed: `agent_ci.py` picks branches from open ledger agents, `--task`, `--branch` or `--all`; no ledger and no flag starts nothing; task ids parse after the prefix's last `/`; help and spec R13.77 name the force-cancel API. `tools/test_ci_speedups.py` helper now passes `--all` (plain scan moved).

Tests:
- `python3 -I -m unittest discover -s claude/plugins/delivery/tests -t claude/plugins/delivery/tests -p "test_dl153*.py"`: 6 ok.
- agent_ci cases of `tools/test_ci_speedups.py` (run by name, 9 cases): all ok.
- `docs_check.py`: G1 (generated decisions.md stale, not committed by rule) and M1 on delivery-speed (answered by `Docs: none` in the commit message); see below for the final run.
