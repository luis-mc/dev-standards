# DL163 report

## What changed
- `delivery_ledger.py`: `link` makes a new row with a free id when no open row has the branch (it no longer falls back to another branch's row). `record` with `create` now also makes the row for `train_state` and `cargo`. The duplicate guard counts copies, so an old duplicate id cannot gain a copy. `show` warns about each duplicate id and names the fix.
- `join.py`: its ledger records pass `create=True`, so the row it makes takes the next free id.
- Spec: R13.85 added after R13.83 (R13.84 not on main yet).
- Notes: `docs/architecture/changes/DL163-ledger-join-ids.md`, `docs/features/delivery/changes/DL163.md`.
- Outside my list: `tests/test_ledger_root_worktree.py`, two cases whose expectations moved (link to an unknown branch now makes a row).

## Cause
`link` fell back to any open row when none matched, so a new release's PR attached to the previous release's row. Join records with no matching row were dropped. The guard compared id sets, so a second copy of an already duplicated id passed.

## Tests
- `python -m unittest test_dl163_ledger_join_ids test_ledger_root_worktree` (in claude/plugins/delivery/tests): OK, 17 tests.
- Full delivery tests dir (`unittest discover`): 1059 ran; the 2 failures were the moved expectations, now fixed.
- `docs_check.py`: M1 on delivery-speed (join.py mapped); handled by a `Docs: none` line in the commit message.

- spec-lint run 42722796110 (areas=delivery): which areas: success; setup preflight: success; area mapping: success; docs check: FAILURE (only W1, the report under docs/work/ on this branch, which the brief requires; no G1); delivery branch gate, change notes, CI scripts, runner plan, plugin ledger/recorder/watcher/hooks, smoke test, artifact pruning, train cleanup: cancelled after the docs check failed; the delivery aggregate job: failure (because of those cancels). The delivery suites did not run in CI, so CI did not check this change. Locally the whole delivery tests dir passed.

Branch head SHA: see `git rev-parse origin/DL163-ledger-join-ids`.

NOT READY
