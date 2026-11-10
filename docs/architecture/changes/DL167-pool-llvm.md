---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
DL167: the runner pool image installs clang, lld and llvm and links clang-cl, lld-link and llvm-lib onto PATH, with a build-time self-check, so cargo-xwin can build C/C++ crates for x86_64-pc-windows-msvc.
