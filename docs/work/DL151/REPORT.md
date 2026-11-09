# DL151 + DL156 report

## What changed
- DL151: `delivery_ledger.stale_agents(root, record=None, led=None)` returns `[{task, id, status}]` for open agents whose task the project record (`registry.json` in `record_dir`, else the old HTML rows) shows Live, Built or Dropped. `hook_session_start.py` lists them ("Needing a check ...") with the `agent-done` fix. No record: nothing.
- DL156: `next_train_id` (next free id); `update()` refuses a new duplicate train id or a new agent row without a task (old rows still load and write); CI records match by PR number and head SHA (`_ci_train`); `show` prints `agent <task> <id> <branch>` with `-` for gaps.
- Spec R13.74, R13.75; change notes in docs/architecture/changes and docs/features/delivery/changes.
- Outside the owned list (needed so the guard does not crash the hook): `hook_post_tool.py` now records an `agent.no_task` event and skips the row when a launch has no task. Test expectations moved: test_post_tool.py (no row, `agent.no_task`), test_ledger.py and test_dl96_ledger_ids.py (seed rows with a task / write old rows directly), test_dl127_ci_watch_ledger.py (stale_agents returns dicts).

## Tests
- `python3 -m unittest test_dl151_stale_agents test_dl156_ledger_guards` (in claude/plugins/delivery/tests): OK, 14 tests.
- `python3 -m unittest discover -p "test_*.py"` (same folder): 1005 tests, OK.
- `python3 tools/test_ci_areas.py`, `tools/test_delivery_runner.py`, `tools/test_project_artifacts.py`: pass.
- `docs_check.py`: one error, G1 `docs/architecture/decisions.md` stale. It also fails on clean main; generated file, not touched.
- `gh workflow run spec-lint.yml --ref DL151-ledger-stale-guards -f areas=delivery` (run 42717945068, watched to the end): overall failure from one job only.
  - success: which areas does this change touch; all 10 `delivery - ...` jobs (area mapping, packaged-program smoke test, runner plan, CI scripts and workflow templates, change notes enforced and folded, setup preflight, artifact pruning, train cleanup, plugin ledger/recorder/watcher/hooks, branch gate and trust rule); delivery scripts, CI templates, cleanup, prune, change notes.
  - failure: docs check, with two errors. G1 `docs/architecture/decisions.md` generated file is stale: it fails the same way on clean main, and generated files are not mine to edit. W1: this report under docs/work/ (branch-only by rule D9; the join strips it).
  - skipped: change notes, change notes folded, and the non-delivery areas.

Branch head: see `git rev-parse HEAD` of origin/DL151-ledger-stale-guards (the commit after this report update).

READY
