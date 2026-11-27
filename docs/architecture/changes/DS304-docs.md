---
plugin: claude/plugins/docs/.claude-plugin/plugin.json
change: minor
task: DS304
---
docs_work.py strip --apply no longer commits: it deletes docs/work/ and prints the git commit command (owner C4). docs_check.py runs W1 only with --ready, DOCS_GATE=ready or a non-draft GitHub pull request (DOCSPEC R10.2).
