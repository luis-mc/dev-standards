---
plugin: claude/plugins/docs/.claude-plugin/plugin.json
change: patch
---
fetch-mermaid now checks the download against a pinned SHA-256 (MERMAID_SHA256) and refuses, writing nothing, when it differs.
