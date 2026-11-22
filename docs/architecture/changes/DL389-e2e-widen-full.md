---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
The e2e step widens to the full suite only on an explicit `--full`. Other reasons that widen the gate (lockfile, root config) leave the e2e selection to the changed UI files and changed specs.
