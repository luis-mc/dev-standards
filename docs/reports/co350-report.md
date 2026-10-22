# CO350 — watcher re-checks red trains

Branch: `claude/CO350-watcher-red-rerun` (from `main`). Plugin: `luismc-delivery` 0.5.0 -> 0.5.1 (no changelog file exists; change notes are folded at release).

## Bug
`delivery_watch.py` skipped trains with ledger state `red`. A failed CI workflow re-run by the owner for the same head commit and turning green was never noticed, so no green was recorded and no merge happened.

## Fix
`pass_trains` now routes `red` trains to `_recheck_red`:
- reads the runs of the train's stored head SHA (`gh run list --commit SHA --workflow W`, same source as ci trains, never the PR check list); a re-run keeps the run id and changes status/conclusion, and a new run has a higher id, both handled by `ci_state_from_runs`;
- not green for every required workflow (still failing, running, queued, gh error) -> no write, stays red; cost: one `run list` per required workflow, no `pr view`, no cancel pass;
- green on every required workflow -> confirms the PR head is still that SHA, records `green`, then the normal `maybe_merge` path (holds respected, `--match-head-commit`, never `--auto`), then `push_next`; a PR found MERGED is recorded merged.

## Tests
- Added `RedRerunTests` (4): red -> re-run green -> merged; green with hold does not merge; red with no newer run stays red with one run-list check and no writes; red with re-run still running stays red.
- `python3 -m unittest test_watch`: 33 tests OK. Whole delivery suite (`discover -s claude/plugins/delivery/tests`): 154 OK.
- `ruff check` on the two touched files: 28 findings, identical before and after (pre-existing, no repo ruff config).
