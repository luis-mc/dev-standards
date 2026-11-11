---
plugin: claude/plugins/docs/.claude-plugin/plugin.json
change: patch
---

# DL251: stale Full Progress lede warning

`check` warns when the Full Progress lede names a RELEASE-n lower than the newest Live release. `render` prints the same line as a note. Only the release-number test is built; the record keeps no reliable change times for content.
