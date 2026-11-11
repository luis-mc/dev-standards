# DL238 report

Base check: `claude/plugins/docs/scripts/project_artifacts.py` has `def cmd_mark_deferred` on origin/main. OK.

## What changed
- `mark-deferred` gets `--local DIR` and `--no-open`. It writes the Full Progress page (same bytes as the publish copy) to `<dir>/full-progress/<project slug>/<file>`, records `local_path` on the entry, and opens it once. Work dir: `--local`, else `work_root` in `.delivery/config.json`, else the publish-copy folder. Opening is skipped with `--no-open`, with `CI` set, or with no display on Linux.
- `finish_change` refreshes the local copy on every writing command while the deferral is active; after the until time it leaves the file alone and never deletes it.
- `pending` shows the path (`local_path` in `--json`). The end-of-turn hook adds `Full Progress is deferred until HH:MM; local copy: <path>`.
- Rule text, task-status-update Publishing section and ARTIFACTSPEC R9.7 updated. Notes: `docs/architecture/changes/DL238-full-progress-local.md`, `docs/features/artifacts/changes/DL238.md`, `docs/features/docs/changes/DL238.md`.

## Tests
- `python -I tools/test_artifacts_dl238.py`: 6 passed, 0 failed.
- `python -I tools/test_project_artifacts.py`: 139 passed, 0 failed, 1 skipped.
- `python3 -m unittest discover -s claude/plugins/docs/tests -p test_hooks.py`: 16 OK.
- `tools/test_project_artifacts_hooks.py`: not run locally (heavy suite, refused by the session guard); covered by the CI job below.
- `python3 claude/plugins/docs/scripts/docs_check.py`: only G1 (generated file stale) and W1 (work report on branch); warning M1: the new test file is not mapped by a spec.
- `gh workflow run spec-lint.yml --ref DL238-full-progress-local -f areas=artifacts,docs` (run 43080697929): which areas: success; docs plugin: success; artifact renderer, commands and hooks: success; docs check: failure (G1 and W1 only, as above); all other jobs skipped.

## Follow-ups
- Map `tools/test_artifacts_dl238.py` in a spec's `code:` (M1 warning).
- G1 needs `docs_index.py build` at the release fold; W1 is cleared by `docs_work.py strip` before the join.

Branch head SHA: see `git rev-parse origin/DL238-full-progress-local`.

READY
