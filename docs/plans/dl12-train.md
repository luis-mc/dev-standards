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

## TC7, folded in (owner: "Add to DL12 now")

| Branch | Tasks | Owns |
|---|---|---|
| `TC7-ci-parallel-suites` | TC7 | `.github/workflows/spec-lint.yml`, `tools/ci_areas.py` and its test |

Measured on #47 (run 38143118756): the `delivery` job is 11.4 of the run's 11.6 min, five suites in series (gate 7.8, cleanup 1.5, CI scripts 1.0, smoke 0.6, change notes 0.4), with every suite's mutation pass on for any change under `scripts/delivery/**`.

1. **Mutants per suite.** `ci_areas.py` outputs one mutants flag per delivery suite, true only when that suite's own scripts, hooks or suite file change (map each suite to the files it tests, from what each suite imports or copies; a shared delivery file such as `delivery_common.py` turns on every suite that uses it). The nightly and the `mutants` dispatch input still force all of them on.
2. **Delivery suites in parallel.** The `delivery` area becomes one job per suite (gate, CI scripts, cleanup, smoke, change notes, plus any other suite now in that job), each gated by the `delivery` area as today. Whatever the branch-protection or `ci_watch` side relies on (job names, a final summary job) keeps working; if a required check is named after the old job, keep a small final job with that name that needs the new ones.

DL12 does not touch these files; TC7 does not touch DL12's.
