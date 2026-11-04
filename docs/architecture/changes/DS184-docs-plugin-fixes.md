---
plugin: claude/plugins/docs/.claude-plugin/plugin.json
change: patch
---
The docs plugin now lists each new file on its own, reads git paths and output as UTF-8, ignores a leading BOM, and keeps underscores and percent-encoded links valid in the link check. A change note only clears the map check (M1) for its own doc. Init records the real default branch, and the check warns when no base branch is found. Fold finds an aligned version table, stub titles are quoted when needed, migrate leaves inline code alone, approval dates must be real dates, and the hooks keep the exit code of a blocking script.
