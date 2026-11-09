---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---

DS202: `delivery_doctor.py` gains a `rust` check, shown only when the track is rust or `rust_ci.py` exists. It checks the host linker, `clang-cl` and `lld-link` for a Windows target, an exact version in `rust-toolchain.toml`, sha256 pins in `tools.json`, the advisory database cache age (warning after 7 days) and free disk for `target/` (warning). It changes nothing and prints the fix command. Other tracks see no new output.
