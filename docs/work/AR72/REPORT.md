# AR72 report: publish settle

Full Progress is published once after a burst of record changes.

## Files
- `claude/plugins/docs/scripts/artifact_hourly.py`: `settle_sec`, `settle_wait`, second-level stamps.
- `claude/plugins/docs/scripts/project_artifacts.py`: `pending` holds Full Progress back inside the window and adds `settling`; `--refresh` lists an unchanged copy only for the hourly fail-safe or a release change; `mark-published` warns inside the window; writers stamp the time.
- `claude/plugins/docs/scripts/hook_end_of_turn.py`: says "Full Progress changes are settling; publish once after the last change" instead of blocking.
- No Artifact-tool hook exists, so the check is in `pending`, `mark-published` and the hook.
- Spec: ARTIFACTSPEC R9.13, R9.14; feature spec R5.20, R5.21; change notes for the plugin, ARTIFACTSPEC and the artifacts feature.
- Tests: `claude/plugins/docs/tests/test_ar72_publish_settle.py`; `tools/test_project_artifacts.py` (settle seam `CLAUDE_ARTIFACTS_SETTLE_SEC=0` in its env, one case rewritten).

## Test runs
- `python3 -m unittest test_ar72_publish_settle` (in tests/): 6 OK
- `python3 -m unittest test_ar70_publish_copy test_ar69_lighter_full_progress test_hooks`: OK
- `python3 tools/test_project_artifacts_hooks.py`: 101 passed
- `python3 tools/test_artifacts_ar63.py`: 7 passed
- `python3 tools/test_project_artifacts.py pending publish mark refresh hourly defer stale copy fingerprint`: passed
- `docs_check.py`: see final section.

