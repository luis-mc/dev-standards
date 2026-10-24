---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
spec: docs/specs/delivery/DELIVERYSPEC.md
change: patch
---
The Stop hook's reply-text checks ignore inline code spans and fenced code blocks: DL-64 no longer flags the word `trains` in code (T-ids, `release/n` and ledger branch names are still flagged in code spans, since DL-64 forbids showing them to the owner), and DL-31 treats a bare `ETA` as a field name or noun, flagging only a real time promise (`ETA 16:40`, `ETA ~20 min`, `ready soon`) that lacks a clock time or its dependency.
