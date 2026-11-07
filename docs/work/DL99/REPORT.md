# DL99 report

## What changed
- `cleanup.py` gains `--keep-fresh-since EPOCH` (local mode). It keeps a local branch whose first commit outside the default branch (with none: tip commit or reflog creation) is newer than EPOCH, or that a running agent in `.delivery/ledger.json` works on. One `cleanup: skipped <branch>: <reason>` line each (stderr), and a `kept:` row. A missing or unreadable ledger skips only the agent check.
- `join.py` records its start time and passes it to `cleanup.py --local`. Join's deletions live in cleanup.py, so the guard is there.
- New test `claude/plugins/delivery/tests/test_dl99_join_fresh_branches.py`.
- Notes: `docs/architecture/changes/DL99-join-fresh-branches.md`, `docs/features/delivery/changes/DL99.md`. No spec note: DELIVERYSPEC has no join cleanup paragraph beyond one generic line.

## Tests
- `python3 -m unittest claude/plugins/delivery/tests/test_dl99_join_fresh_branches.py`: 5 tests OK.
- `python3 tools/test_delivery_cleanup.py --no-mutants -k join`: 28 checks, 0 failed.
- `python3 tools/test_delivery_cleanup.py --no-mutants -k local`: 23 checks, 0 failed.
- `docs_check.py`: G1 (stale generated decisions.md, expected) and M1 on delivery-speed spec (covered by commit line `Docs: none`). T2 warning on test-cost is not mine.
- CI: see the last section.

## CI
`gh workflow run spec-lint.yml --ref DL99-join-keeps-fresh-branches -f areas=delivery` ran as run 42319983726 on cedc30d. The job "delivery - branch gate and trust rule" passed (2m03s). The run failed only in "docs check": G1 (stale generated decisions.md) and W1 (docs/work on branch), both expected on a branch. M1 did not fire in CI. T2 warnings are not mine.

Branch head: the commit after cedc30d that adds this section (see `git log`).

READY
