---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---

DS206 (owner decisions D148 and D146): the Rust workflow runs on a pull request only when a Rust path changed (crates/**, **/Cargo.toml, Cargo.lock, rust-toolchain.toml, rustfmt.toml, deny.toml, **/*.rs, scripts/delivery/rust_ci.py, tools.json), so Rust under apps/ runs and a JS-only change does not. The JS workflow adds the Rust-only paths to its `paths-ignore`, so a Rust-only change does not run the JS suite. Push keeps `paths-ignore` with docs and markdown. In the Rust template, `toolchain-isolated` now defaults to false, and `rust_ci.py` picks the Linux linker as system cc first, then pinned Zig, else it fails with `linker cc not found` and the fix. LLVM stays for the Windows MSVC target.
