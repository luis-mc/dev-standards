---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
DL162: `pool-refresh --yes` now copies the plugin's current pool files into the pool folder (old copies go to `bak-<time>/`), builds, and recreates the container when the image id changed. The result says whether the image was unchanged or rebuilt. The doctor gains `pool.<name>.files-current`.
