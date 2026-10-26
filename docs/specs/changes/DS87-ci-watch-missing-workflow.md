---
plugin: claude/plugins/project-setup/.claude-plugin/plugin.json
change: patch
---
`ci_watch.py` exits 2 at once when the requested workflow does not exist in the repository, naming it and listing the repository's workflows so the caller can pass the right `--workflow`, instead of retrying the 404 five times as a transient gh error.
