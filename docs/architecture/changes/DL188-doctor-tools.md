---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---

# DL188 doctor tools

The delivery doctor finds cached tools through `ci_tool.py` (new `cached_tool`), accepts flat and per-platform
`tools.json` pins, and fixes its `ci_tool.py` fix text (`tool`, not `ensure`). New check item `ci.scripts-current` warns
when a project's `scripts/delivery` files are older than the plugin templates. The wait shown is `ci.wait_min`.
