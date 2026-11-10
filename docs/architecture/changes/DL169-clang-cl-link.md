---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---

DL169: Ubuntu 24.04 ships no clang-cl, so the DL167 self-check failed the pool build. The runner-pool Dockerfile now links clang from the build-time LLVM folder as /usr/local/bin/clang-cl when clang-cl is missing; clang runs in MSVC mode under that name.
