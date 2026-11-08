# DL113 report

## What changed
- New `claude/plugins/delivery/templates/shared/scripts/delivery/cancel_joined_runs.py`.
- New test `claude/plugins/delivery/tests/test_dl113_cancel_joined.py`.
- New change note `docs/architecture/changes/DL113-cancel-joined-runs.md`.

## Behaviour for the spec
`cancel_joined_runs.py --into <INTEGRATION> [--remote origin] [--repo OWNER/NAME] [--yes]`
- Lists branches in `git branch -r --merged <remote>/<INTEGRATION>`, minus the integration and default branch.
- Lists runs from `gh run list --json databaseId,headBranch,headSha,status,workflowName,url --limit 200` with status queued, waiting, requested, pending or in_progress, whose headBranch is a merged branch and whose headSha is an ancestor of `<remote>/<INTEGRATION>` (a branch pushed again after the join is left alone).
- Prints one `cancel <id> <branch> <workflow> <url>` line per run. Dry run by default; ends with `dry run: N run(s) would be cancelled; pass --yes to cancel`.
- With `--yes`: `gh run cancel <id>` per run, prints `cancelled <id>` or `failed <id>: <reason>`, then `N cancelled, M failed`.
- Exit 0 done (also when nothing matches), 1 a cancel failed, 2 usage error, missing `<remote>/<INTEGRATION>`, gh missing or failing to list.
- Standard library; one subprocess seam `run()`; Windows children get creationflags 0x08000000.

## Tests
- `python3 -m unittest claude/plugins/delivery/tests/test_dl113_cancel_joined.py` -> 5 tests, OK.
- `python3 tools/ci_areas.py --branch-advice` -> `heavy: delivery -> gh workflow run spec-lint.yml --ref DL113-cancel-joined-runs -f areas=delivery`. Not run here (no gh); the owner or orchestrator runs it.
- `change_notes.py check --config tools/change-notes.json` -> ok.
- `docs_check.py` -> errors M1 (feature spec not updated: the brief says the orchestrator writes it from this report) and W1 (docs/work report on the branch, expected; strip before the join). Other errors are not from this change.

Branch head: see `git rev-parse DL113-cancel-joined-runs` (the commit after this report).

The spec text and the delivery-lane advice run are left to the orchestrator.

READY
