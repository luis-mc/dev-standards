---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
DS208 adds a vitest globalSetup template to the rust track. It builds the crates a TypeScript test spawns and exports their exe paths. The JS CI unit job installs the pinned Rust toolchain only when the Rust track is on.
