---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---

# DL193 cargo-deny flags

The rust template's `rust_ci.py deny` passed `check --disable-fetch`. The pinned cargo-deny 0.20.2 rejects that flag. The step now passes `--offline` before `check`, so the check does not fetch the advisory database.
