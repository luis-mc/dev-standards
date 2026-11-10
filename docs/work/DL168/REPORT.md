# DL168 report: ETAs from measured history

## What changed
- `delivery_ledger.py`: `agent-done` and the shipped-train close set `finished_at`; `record ci` accepts `run_started_at` and `run_completed_at`; `show` prints `eta N min, took M min` for done agents and the `cloud agents: eta median X min vs actual median Y min (last 20)` line.
- `delivery_watch.py` (not in the owns list; the brief needs the watcher to set the times): a report READY/NOT READY close sets `finished_at` to the branch tip commit time; CI runs fetch `startedAt`/`updatedAt` and a final state writes `ci.run_started_at` and `ci.run_completed_at` on the train row.
- `delivery_eta.py` (new): `estimate(root, kind, where, last)`, CLI with `--json`, "no history" under 3 samples. pool-refresh reads `jobs[]` rows with `kind: pool-refresh` (none exist yet, so it says no history).
- `hook_pre_tool.py`: DL-30 launch check refuses an eta above 1.5 x measured p75 with at least 5 samples; an `eta-reason:` line allows it; fewer than 5 samples allows it.
- Spec R13.89, change note, feature note.

## Tests
- `python -m unittest test_dl168_measured_etas` (in tests/): 11 tests, OK.
- `python -m unittest test_ledger test_pre_tool test_watch test_dl96_cloud_create test_dl127_ci_watch_ledger test_dl151_stale_agents test_dl156_ledger_guards test_dl163_ledger_join_ids test_watch_ci_runs test_stop test_post_tool`: 293 tests, OK.
- `python3 claude/plugins/docs/scripts/docs_check.py`: one error, G1 `docs/architecture/decisions.md` generated file stale. It fails the same way on clean main, so it is not from this branch. W1 for this report is expected.

## CI
`gh workflow run spec-lint.yml --ref DL168-measured-etas -f areas=delivery`, run 42804995482: all delivery jobs success (branch gate, train cleanup, setup preflight, CI scripts and templates, runner plan, artifact pruning, ledger/recorder/watcher/hooks, change notes, packaged-program smoke, area mapping, combined delivery job). Other areas skipped. `docs check` failed only on G1 (`docs/architecture/decisions.md` generated file stale), which also fails on clean main; it is not from this branch and I did not edit the generated file.

Code head (before this CI note): 4751cd9b039d031420d1a9c1fd0e8c99877782c7 plus the report commit; final head is the branch tip.

READY
