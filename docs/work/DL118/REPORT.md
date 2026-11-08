# DL118 report

## What changed
- hook_session_start.py: `stop_pid` checks liveness with `machine_slots.pid_alive` (OpenProcess + GetExitCodeProcess on Windows), so a dead pid is skipped silently. A live pid whose kill fails with any OSError is recorded in `STOP_FAILED[pid]`. `rearm_old_watchers(root, ledger, installed, at=None, watcher_min=None)` still returns `(messages, stopped)`; `stopped` is a list subclass with `.failed` (pids alive but unstoppable) and `.warnings` (texts). It starts the installed watcher when any pid was stopped or failed. `prune_dead_watchers` runs at session start (fails open).
- delivery_ledger.py: `prune_watchers(led, now, alive)`.
- delivery_watch.py: heartbeat calls `prune_watchers` inside the same ledger mutation.
- Change note docs/architecture/changes/DL118-rearm-unstoppable-watchers.md.

## Exact behaviour for the spec
- Warning in additionalContext, each session start while the row's heartbeat is newer than `watcher_min`:
  `delivery_watch pid <pid> (plugin <version or unstamped>) could not be stopped: <reason>. Stop it yourself, from an Administrator shell on Windows: Stop-Process -Id <pid>.`
  On POSIX the tail is `kill <pid> (with sudo if needed).`
- The installed watcher is still started (warn, not refuse).
- A dead pid is never warned about. A live pid with a stale heartbeat is not warned about.
- Only a delivery_watch row's recorded pid is ever signalled; never by name.
- Prune: delivery_watch rows with a dead pid and a heartbeat over 24 h old are dropped. A fresh or unreadable heartbeat is kept.

## Tests
- `unittest test_dl118_rearm_unstoppable` (10): OK
- `test_dl96_watcher_rearm` (8), `test_dl109_watcher_no_windows` (9), `test_watch` (83): OK
- `unittest discover` over claude/plugins/delivery/tests (846): OK
- `tools/test_delivery_hooks.py`: not run; session guard refused the full heavy suite locally. Leave to CI.
- `ci_areas.py --branch-advice`: unreadable diff; advises `gh workflow run spec-lint.yml --ref DL118-rearm-unstoppable-watchers -f areas=specs,delivery,artifacts,profiles,transcript-folds,docs`. Not run.
- docs_check.py: not run (luismc-docs path not available here).

Branch head SHA: see the last commit on the branch (the report is committed with it).

READY
