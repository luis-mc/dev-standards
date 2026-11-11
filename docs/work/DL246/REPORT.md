# DL246 report

Base check: origin/main has `def cmd_mark_deferred` with `--local` (DL238). OK.

## What changed
- `project_artifacts.py`: `machine_work_root()` reads `work_root` from `machine.json` in the delivery machine folder. `local_work_dir` order: `--local`, project `.delivery/config.json`, machine.json, old .claude fallback with a warning naming machine.json.
- `write_local_copy`: the local page is the repo copy; every `feature-*.html` is copied beside it; each local page gets `<meta http-equiv="refresh" content="60">`. Repo and publish copies get none. Refreshed on every record change while deferred.
- `local_opened` on the entry: the browser opens once per deferral; a second mark-deferred in the same deferral does not open it.
- Rule R9.7 (artifactspec.md), task-status-update skill, artifacts spec R5.9a, notes (features/artifacts DL246, architecture DL246-local-full-progress), suite artifacts-dl246 in .claude/suites.json.
- hook_end_of_turn.py not changed (its line already shows the local path).

## Tests
- python3 tools/test_artifacts_dl246.py: 6 passed, 0 failed (the opened-once case needs Linux; it returns early elsewhere).
- run_suite.py --measure artifacts-dl238: 6 passed, 0 failed.
- python3 tools/test_project_artifacts.py: 139 passed, 0 failed, 1 skipped.
- docs_check.py: only W1 (this report), as expected.
- E2E by inspection: the dl246 cases list the files in the local folder, check each feature link target exists, and check the refresh tag is only in the local copies.
- spec-lint dispatched with areas=artifacts,docs. Both dispatches (runs 43090738242, 43090945017) were cancelled by something else; the re-run (attempt 2) of 43090738242 on 99dbb54 ended: areas OK; artifact renderer, commands and hooks OK; docs plugin OK; docs check FAILED (W1: this report under docs/work, expected); the rest skipped. Run 43090945017 attempt 2 was still pending when I stopped.

## Follow-ups
- DL238's test `writes_to_local_dir` still passes; no change needed.
- The open flag is set when an open is attempted, even if CI/no display skips it.

Code head: 99dbb54
READY
