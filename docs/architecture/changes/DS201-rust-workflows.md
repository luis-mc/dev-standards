---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---

DS201: the Rust `ci.yml` installs the exact channel from `rust-toolchain.toml` with `rust_ci.py toolchain` instead of `dtolnay/rust-toolchain`, applies `rust_ci.py env`, runs `rust_ci.py deny` instead of `cargo install cargo-deny || true`, uses `Swatinem/rust-cache` on hosted runners only, and filters on Rust paths so a Rust-only change skips the JS suite. The Rust `package.yml` uses the same setup and adds a Windows exe artifact (`packaged-program-windows`, cargo-xwin cross build) beside `packaged-program`. `delivery_common.py` now reads the gate.json `scope_map` and the step `paths` key: a change only under one scope skips the steps of the other scopes; a file under no scope, an unknown key, or a gate.json without `scope_map` keeps today's behaviour.
