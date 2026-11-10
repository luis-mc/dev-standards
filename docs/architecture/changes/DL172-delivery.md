---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---

Moved from project-setup: the pre-push and commit-msg hooks, the .delivery/config.json template and the session_guard settings entry. delivery_ci_install.py writes them at the same project paths; install moves a different pre-push to pre-push.local; settings are merged, never overwritten.
