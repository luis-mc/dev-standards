# DL269 report

Base check: `cmd_task_add` present at origin/main.

## What changed
- `claude/plugins/docs/scripts/project_artifacts.py`: `task-add` and `set-task-status` refuse U+FFFD in every free-text option (item, detail, expected, basis, history, reason, into, no-release, rides, risk, phase, and task-add's owner, app, prefix). One line names the option and the position. `check` reports U+FFFD in registry.json task fields and in content/*.json (task ID or file, and field).
- `tools/test_artifacts_dl269.py`: 6 cases (detail refused and nothing written, item and history refused on set-task-status, accents pass, check flags a held one, clean record not flagged).
- Artifacts spec failure-modes row (the only task text rule spot); feature note `docs/features/artifacts/changes/DL269.md`; change note `docs/architecture/changes/DL269-refuse-replacement-char.md`.

## Tests
- `python3 -I tools/test_artifacts_*.py` (each): all pass; dl269 6 passed.
- `python3 -I tools/test_project_artifacts.py`: 139 passed, 0 failed, 1 skipped.
- `python3 -I tools/test_project_artifacts_hooks.py`: 101 passed.
- spec-lint run 43287116675 (areas=artifacts): "artifact renderer, commands and hooks" success. "docs check" failed only on the expected W1 for docs/work/.
- Local docs_check also showed M1 for features/docs (mapped code changed); the commit says `Docs: none` for it. The CI run did not report it.

## Follow-ups
- Strip docs/work/ before the join (docs_work.py strip).
- tools/test_artifacts_dl269.py is not mapped by any spec `code:` (warning).

Branch head: see `git rev-parse origin/DL269-refuse-replacement-char`.

READY
