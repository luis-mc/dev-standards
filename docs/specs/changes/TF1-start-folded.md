---
plugin: claude/plugins/transcript-folds/.claude-plugin/plugin.json
change: minor
---
luismc-transcript-folds: every session starts with diffs and commands folded; a toggle (ctrl+x d, ctrl+x f, /fold-diffs, /fold-commands) lasts for that session only and is no longer kept in `$.store`, so a stray toggle never carries over.
