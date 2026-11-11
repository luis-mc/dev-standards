---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
delivery_ci_install.py takes several tracks (`--track rust,ts`) and merges the ci.yml, gate.json and ci-scope.json both tracks ship. The doctor checks each track.
