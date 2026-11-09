---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---

DS200 (also covers DL125 and DL126): the Rust template gains `scripts/delivery/rust_ci.py` with `toolchain` (exact channel through the pinned `rustup-init`), `env` (linker environment: cached LLVM for the Windows MSVC target, pinned Zig or a system `cc` for the Linux host, else `linker cc not found` with the fix command), `deny` (cached RustSec clone, generated `deny.toml` copy, cache warning up to 7 days then failure), `run` (runs a command with system compilers removed from PATH when gate.json `toolchain-isolated` is true, the default) and `smoke` (debug build of each declared binary, then `--version`). The Rust `gate.json` adds `deny` and `xwin` steps, a `scope_map` for Rust paths and the `toolchain-isolated` field, and keeps widening on `Cargo.lock`. `smoke.json` gains a `binaries` list. Zig is optional because it is not pinned yet.
