---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
The runner pool supervisor now recreates missing agent users at start. After the container is rebuilt, the `r-<slug>` users are gone while `/agents` survives. The supervisor reads the uid and gid from `/agents/<slug>`, then creates the group and the user. An agent whose folder is missing is skipped with one log line. A user that still does not exist is logged once and retried with back-off, not in a fast loop.
