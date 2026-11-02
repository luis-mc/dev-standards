---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
CI options per OS (self-hosted runners, GitHub-hosted runners, Claude cloud sessions) with no default: new `ci` config keys, `delivery_ci.py` to choose and change them, `delivery_ci_install.py` to write the CI and delivery templates into a project (the templates moved here from tech-stack-setup), a `ci` doctor check, commit-status reading in the watcher and `ci_watch.py`, and starter cloud shard and status scripts.
