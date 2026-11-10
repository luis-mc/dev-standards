---
plugin: claude/plugins/project-setup/.claude-plugin/plugin.json
change: minor
---

project-setup no longer ships the pre-push and commit-msg hooks, the delivery config template or the session_guard settings entry. It calls delivery_ci_install.py for them. Repo tooling stays.
