---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
The rust template adds `rust_scope.py`, which picks the crates a pull request touches and their dependents, and `rust_ci.py` fmt, check, clippy and test now honour `RUST_CRATES`. `rust_ci.py` also keeps a per-runner `CARGO_TARGET_DIR` cache, pruned by size (`RUST_TARGET_CAP_GB`), with `DELIVERY_NO_TARGET_CACHE=1` to opt out. (DL295)
