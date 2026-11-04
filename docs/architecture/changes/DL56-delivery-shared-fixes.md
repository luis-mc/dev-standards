---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
Fixes in the shared delivery scripts. The scope and area scripts now count a moved file at its old and new path and read real (non-ASCII) file names. The session guard ignores `gh pr create` inside quotes and heredocs, checks `--measure=NAME`, and accepts `--draft=true`. Change-note checks now see removed `---` lines. The heavy-job lock is written whole before it is visible, and an empty lock is not a dead owner. `dirty_paths` returns whole paths.
