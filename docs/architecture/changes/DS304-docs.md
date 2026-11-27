---
plugin: claude/plugins/docs/.claude-plugin/plugin.json
change: minor
task: DS304
---
docs_work.py strip --apply no longer commits: it deletes docs/work/ and prints the git commit command (owner C4). docs_check.py runs W1 only with --ready, DOCS_GATE=ready or a non-draft GitHub pull request (DOCSPEC R10.2). mark-deferred keeps the local page path and opened flag in .claude/artifacts-local.json, never in the manifest (U11). The retired hook_before_command.py is removed (U4); the artifacts session hook moves to scripts/hook_session_start_artifacts.py (S4); the vitest shim moves to tests/fixtures/ (S3). The rule file drops its repeated lines and its two definitions (E19, E20).
