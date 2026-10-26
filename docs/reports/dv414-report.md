# DV414: delivery watcher re-reads a red release on its new head

Branch `claude/DV414-watch-red-new-head` (from `origin/main`). File: `claude/plugins/delivery/scripts/delivery_watch.py`.

## What changes
- `_recheck_red` now reads the PR's current head first. When it differs from `ci.head_sha` (a fix was pushed), the train is re-pointed to the new head (`head_sha`, `run_ids` from that head's runs, `state`) and judged by that head's runs: success -> green (and merge on green as before), failure -> stays red on the new head, queued/running -> train state `ci`. On the same head the old rule holds: only a green re-run moves the train.
- A train whose `ci` is not a dict (a string was seen in the wild) is treated as unknown: logged once per train, read as empty, healed to a dict on the next write. `_set_train` and `_revoke_green` no longer assume a dict.
- Cost: a red train now costs one `gh pr view` plus one run list per cycle (before: one run list). The existing "costs one check" test is updated for that.

## Tests (`tests/test_watch.py`, 38 pass)
Red on old head + new head green -> green and merged with `--match-head-commit <new>`; new head running -> `ci`/running; new head red -> red with the new head and run ids; string `ci` on a red train -> no crash, one log line over two cycles; string `ci` on a running train -> no crash.

## Not done
No version bump or change note (the repo folds those in separate `fold change note` commits). Ruff reports one new UP031 (percent format) matching the file's existing style; the repo is not ruff-clean on these files before this change either. Heavy-area CI (`spec-lint.yml`) not dispatched from here.
