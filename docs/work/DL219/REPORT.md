# DL219 report

Base check: `check_freshness` and `last_commit_date` present on origin/main.

## Cause
`last_commit_date` used `git log -1 --format=%cs`. That is the date in each commit's own time zone, and it counts merge commits. Reproduced with real temp repos:
- Time zone: a commit at 01:00 +1400 reads as the 11th, though it is the 10th in UTC. A doc commit in another zone reads differently, so T2 warned or not by who made the commit.
- Merge commit: a merge ref dated "now" can be the newest commit touching the code paths.
- Shallow clone (depth 1 or 2): history is cut, so dates are those of grafted commits and wrong either way.
- Author versus committer date: the check already used the committer date on both sides, so it needed no change.

## What changed
- `last_commit_date` now runs `git log --no-merges -1 --format=%ct` and returns the UTC date.
- `check_freshness` skips T2 on a shallow clone (`rev-parse --is-shallow-repository`) and prints one info line to stderr. It is not a finding, so `--strict` is not affected.
- Smallest fix the reproductions prove: UTC plus no merges fixes the full-clone and merge-ref cases; skipping covers shallow.
- Spec R5.11a, feature note, change note (patch).

## Tests
- `python3 -m unittest test_dl219_freshness_ci` (in claude/plugins/docs/tests): 6 tests OK. Against the old script 3 fail and 1 errors.
- `python3 -m unittest discover` (docs plugin suite): 200 tests OK.
- `python3 claude/plugins/docs/scripts/docs_check.py`: only W1 (this report, expected). It ran on a shallow clone here, so T2 was skipped.
- spec-lint run 43048496543, areas=docs: which areas: success; docs plugin: success; docs check: failure; all other jobs skipped. The docs check failure is W1 for this report (expected) and 3 real T2 warnings from a full clone: agents (code 2026-11-10, doc 2026-11-04), audits (2026-11-10 vs 2026-11-09), transcript-folds (2026-11-10 vs 2026-11-04). These are genuine code-after-doc cases on main, not caused by this change.

## Follow-ups
- The 3 T2 warnings above need their specs touched or verified.
- CI checkouts should use fetch-depth: 0 to run T2 at all.

Branch head SHA (code commit): 46455228e791958f2458795dbd935353189d2b9a

READY
