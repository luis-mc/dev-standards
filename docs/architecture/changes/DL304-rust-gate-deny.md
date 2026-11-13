---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---

The rust template's branch gate runs `rust_ci.py deny` after `lint`, only when a `Cargo.toml`, `Cargo.lock` or `deny.toml` changed. Licence and advisory failures from new crates now show up before release CI. A new optional step key `when_changed` makes a step conditional on changed paths; it is validated in `delivery_common.py` and documented in `CONTRACT.md`. Other tracks are unchanged.
