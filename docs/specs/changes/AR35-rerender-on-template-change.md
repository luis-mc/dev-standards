---
spec: claude/plugins/artifacts/references/artifactspec.md
plugin: claude/plugins/artifacts/.claude-plugin/plugin.json
change: patch
---
Every writing command also renders each page whose file differs from a fresh render (R7.5), so a plugin upgrade that changes the templates or the stylesheet brings every page up to date at the next status change instead of leaving the untouched pages in the older look until someone runs `render`.
