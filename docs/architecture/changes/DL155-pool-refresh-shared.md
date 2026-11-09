---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
DL155: `pool-refresh` on a shared runner pool keeps the layers and apt names other repositories set, records who asked for each layer, and never lowers the Playwright version; new flags `--drop-layer`, `--drop-apt` and `--playwright`.
