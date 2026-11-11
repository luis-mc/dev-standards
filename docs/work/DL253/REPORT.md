# DL253 report

Base check: load_guard.py has heavy_running, heavy_begin and the `DL54 F7: no pid and no host` comment.

## What changed
- `load_guard.py`: heavy_begin also records tool_use_id, transcript_path, timeout_ms and background. heavy_running frees an entry when (a) the transcript tail (last 4 MiB only) holds a tool_result for the call, (b) a foreground call is older than its timeout + 2 min (default timeout 120 s, max 600 s), (c) the transcript is gone or idle over 30 min. A call that returned because it went to the background, or a run_in_background launch, still counts and is freed after 30 min. slot_stale_min stays the last cap. On any doubt the entry is kept.
- Choice for run_in_background: it counts (it starts real work), with the 30 min cap, because its task end cannot be tied to the entry reliably.
- The refusal shows each entry's age and session and what was just freed as ended.
- New tests: `claude/plugins/delivery/tests/test_dl253_heavy_release.py` (10 cases).
- Docs: the DL-91 text now lives in `docs/features/runner-pool/spec.md` R5.6 (delivery spec only points to it), so I edited it there. Notes: `docs/features/delivery/changes/DL253.md`, `docs/architecture/changes/DL253-heavy-slot-release.md`.

## Tests
- `python3 -m unittest test_dl253_heavy_release test_load test_machine` (in delivery/tests): 125 OK.
- `python3 tools/test_delivery_ci.py --no-mutants`: 78 passed, 0 failed.
- `tools/test_delivery_hooks.py`: not run locally; the session guard refuses the full heavy suite. CI ran it.
- `spec-lint.yml` areas=delivery (run 43107377346): every delivery job passed. Only `docs check` failed, with the expected W1 on docs/work/.

## Follow-ups
- Pairing a backgrounded task with its completion notification would free those entries earlier than 30 min.

Branch head SHA: see `git rev-parse origin/DL253-heavy-slot-release` (the report commit follows the code commit).

READY
