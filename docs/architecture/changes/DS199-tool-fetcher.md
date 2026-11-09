---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---

DS199: `ci_tool.py` gains a `tool <name>` command that fetches any tool pinned in `tools.json` (raw file, archive or crate), verifies its SHA-256, unpacks or builds it once into the tool cache, and prints its bin path. `tools.json` now pins `rustup-init`, `llvm` (for `lld-link`, `clang-cl` and `llvm-lib`), `cargo-deny` and `cargo-xwin`; `tools_pin.py` gains `rustup-init`, `crate` and `entry` commands. The gitleaks pin and command are unchanged. A pinned Zig is not included yet because its download host was unreachable when the pins were made.
