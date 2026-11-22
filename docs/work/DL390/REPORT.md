# DL390 report

## Simulation
Copied `claude/plugins/delivery/templates/shared/` into a temp git repo (default branch `master`, one commit). Ran the shipped tests there.

The kit ships one `test_*.py`: `scripts/delivery/test_guardrails.py`. It is a guard script, not a test suite. The 7 failures and 57 errors the project reported do not come from kit test files; the kit ships no others. They come from tests the project owns, or from the project's own copies.

## Failures
| # | Where | Result | Cause | Fix |
|---|---|---|---|---|
| 1 | `python3 -m unittest discover -s scripts/delivery -p 'test_*.py'` | Ran 0 tests, OK | none | none |
| 2 | `pytest scripts/delivery` | 1 error: `fixture 'st' not found` for `test_limits` | Helper function named `test_*`; pytest collects it as a test (naming, not path or branch) | Renamed to `limits_for` in `test_guardrails.py` |
| 3 | `test_guardrails.py --root .` in the sim | exit 0 (warn mode) | none; no hard-coded `main`, dev-standards path, network or OS use found | none |

Classes checked and not found in the kit's shipped test: hard-coded dev-standards paths, branch name `main`, missing fixture or config file, network, machine load, OS.

Not owned, not edited: no fault found in `delivery_common.py`, `branch_gate.py`, `delivery_ledger.py`, `project_artifacts.py` or the pre-push hook, because the shipped suite does not run them.

Gap: the project's 64 failures cannot be reproduced from the kit alone. If its tests import kit scripts, the project's failing test names are needed to trace further.

## Added
- `tools/test_kit_suite_sim.py`: runs the simulation (unittest discover, pytest if installed, the guard script) in a temp repo with a `master` branch.
- `docs/architecture/changes/DL390-kit-suite-faults.md` (plugin `plugin.json`, patch).

## Commands
- `python3 -m pytest tools/test_kit_suite_sim.py claude/plugins/delivery/tests/test_dl376_test_guardrails.py`: 17 passed.
- `python3 tools/ci_areas.py --branch-advice`: light, test locally only.
- `python3 claude/plugins/docs/scripts/docs_check.py`: 1 error, W1 for `docs/work/DL390/REPORT.md`. This is expected on an agent branch; the join strips `docs/work/`. No other finding.

Branch head (code commit): 53e583c06f1219a81a4159ee2dc1cfaa25112768

READY
