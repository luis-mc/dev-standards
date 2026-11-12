# DL275 report

**Base check:** origin/main has `'ci_watch passed'` and `def current_task_id` in hook_after_command.py.

## What changed
- `hook_after_command.py`: a `ci_watch.py` or `gh run watch` result now takes its task from the watched head. `ci_watch.py` uses the first non-option argument as the sha: if it is the current head, the current task (as before); else the first task branch (remote, then local) whose head is that sha. `gh run watch <id>` uses `gh run view <id> --json headBranch,headSha` (seam `CLAUDE_ARTIFACTS_GH`); no answer means no event. A head on no task branch, or a task already Live in the registry, queues nothing. It never falls back to the current branch.
- Exit codes: the existing rule already holds. A pipe (`| tail`), `;` or `||` after the watch makes the code untrusted, so no event. New tests pin that a failed or untrusted watch never yields 'passed'.
- Tests: new `claude/plugins/docs/tests/test_dl275_ci_watch_task.py` (9 cases). Existing `tools/test_project_artifacts_hooks.py` rows now watch `HEAD` and use a gh stub for `gh run watch`.
- Docs: `docs/features/artifacts/spec.md` R6.3 sentence, `docs/features/artifacts/changes/DL275.md`, `docs/architecture/changes/DL275-ci-watch-task.md`.

## Tests
- `python3 -I claude/plugins/docs/tests/test_dl275_ci_watch_task.py`: 9 passed.
- `python3 -I tools/test_project_artifacts_hooks.py`: 101 passed, 0 failed.
- `python3 -I tools/test_artifacts_ar59.py`: 9 passed. `tools/test_artifacts_ar60.py`: 6 passed.
- `docs_check.py` locally: only W1 (docs/work, expected) and M1 for features/docs, answered by the commit line `Docs: none for features/docs`.
- `gh workflow run spec-lint.yml --ref DL275-ci-watch-task -f areas=docs` (run 43324569706): docs plugin job success; docs check failed only on W1 for docs/work/DL275/REPORT.md (expected on a branch). All other jobs skipped by the area plan.

## Follow-ups
- ARTIFACTSPEC (`claude/plugins/docs/references/artifactspec.md`, section 8.1 / R8.8) is not in my file list and is untouched. It does not yet say where the after-command hook takes the watch task from.
- `ci_watch.py --workflow x.yml <sha>` (option before the sha) picks the option's value as the sha and queues nothing. Safe, but worth documenting.
- Run `docs_work.py strip` before the release join.

Branch head SHA: see `git rev-parse origin/DL275-ci-watch-task` (the report commit follows d1187263d3e7500751505e37fac04089577d2446).

READY
