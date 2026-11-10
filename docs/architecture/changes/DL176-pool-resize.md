---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
DL176: `pool-plan` and `pool-run` keep browsers, layers, apt names and the Playwright version from the pool `.env`, size from the median of several memory samples, refuse a `--resize` that lowers the cap without `--shrink`, and take `--pool-gib` and `--pool-cpus`.
