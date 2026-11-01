---
plugin: claude/plugins/artifacts/.claude-plugin/plugin.json
change: patch
---
The end-of-turn background check fires once per marker, and the marker is removed once the turn was let through after it was told (AR52). A background command that only runs `delivery_watch.py` or `ci_watch.py` no longer arms the check (AR53).
