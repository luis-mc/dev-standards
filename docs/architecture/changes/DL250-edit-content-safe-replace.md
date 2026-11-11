---
plugin: claude/plugins/docs/.claude-plugin/plugin.json
change: patch
---
`edit-content` and `retire` no longer delete a content folder in place: the replace is atomic, a locked folder stops the command with nothing changed, and invalid content restores the old folder.
