---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
rust_ci.py links `<repo>/target` to the persistent target cache and exports DELIVERY_RUST_TARGET (DL329).
