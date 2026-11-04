# DL55 report

Method (D90): a failing test first for each finding. All four reproduced on current main, then were fixed. The tests are kept in `claude/plugins/delivery/tests/test_ledger.py` (`DL55LedgerFixTests`).

- F2 fixed. An unreadable ledger is copied to `ledger.json.broken-<time>` and `update()` raises `LedgerError`. The file is left as it was. Reads for display still fall back to empty.
- F9 fixed. `agent-eta` accepts any agent that is not done.
- F11 fixed. `--root` is accepted after the subcommand too.
- DL52 fixed. Rows with the same task and branch and one `trig_` id and one `cse_` id merge into one row; the second id is kept in `alt_ids`. `agent-eta` and `agent-done` accept either id. The hook files that create the rows are not mine and are unchanged.

Tests: delivery suite, 583 tests, OK.
Docs: README ledger lines updated; plugin change note and features/delivery change note (DL55) added. docs_check: only W1 (report under docs/work, branch-only by rule) and a README mapping warning remain.

Branch head: ba03aef16f04d4fce01216a71325e1b202d40f58
