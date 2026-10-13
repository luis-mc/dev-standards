---
plugin: claude/plugins/project-setup/.claude-plugin/plugin.json
change: minor
---
claude-setup now installs luismc-transcript-folds at user level on every run: it adds the `luismc-transcript-folds@<marketplace>` entry to `~/.claude/settings.json` and merges two chords (`ctrl+x d`, `ctrl+x f`) from the new asset `keybindings.json` into `~/.claude/keybindings.json`, showing any chord bound to another action as a conflict in the single confirmation.
