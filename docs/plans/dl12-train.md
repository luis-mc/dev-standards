# DL12 train

Integration branch `DL12-integration`; one agent branch cut from it.

| Branch | Tasks | Owns |
|---|---|---|
| `DL12-delivery-log-times` | DL12 | `.../tooling/shared/scripts/delivery/delivery_log.py`, the delivery-log paragraph of `.../delivery/CONTRACT.md`, the delivery-log scenarios in `tools/test_delivery_cleanup.py`, one change note |
| `DL12-integration` (orchestrator) | DL13 | `docs/upgrades/stackspec-8.0.0.md`, this file |

DL12, two fixes to the delivery log written to the train's release notes:

1. **Times say UTC.** Every time in the table is UTC; say so. The table keeps `YYYY-MM-DD HH:MM` cells, the column headers say `(UTC)` once each for the time columns (Finished, Joined, CI start, CI end, Merged, Live), and the footnote says "Times are UTC."
2. **CI start is the first run, not the last head's.** Today `ci_of` reads only the runs on the ready pull request's final head, so after a fix-forward CI start is the last round's start and the earlier rounds' testing time is counted as waiting. CI start becomes the earliest start among the runs on the ready pull request's branch created at or after the pull request was created (`gh pr view --json createdAt`, `gh run list --branch <head> ...`); CI end stays the latest end of the runs on the final head; queueing is the longest wait among all of those runs. If the branch listing fails, fall back to today's head-only figures.

Rows already in the release notes still win (a later call only fills what is missing).

Rules: change note `docs/specs/changes/DL12-delivery-log-times.md`, `plugin:` the luismc-project-setup `plugin.json`, `change: patch` (STACKSPEC text does not change). Never edit version lines. Test locally only `tools/test_delivery_cleanup.py` with `--no-mutants` (and add a mutant for the first-run rule at the end of the MUTANTS list). No branch CI runs. The ready PR's CI is the one full run.
