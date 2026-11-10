---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---

DL170: the MSVC CRT that cargo-xwin downloads asserts Clang 19 or newer (STL1000), and Ubuntu 24.04 defaults to clang 18. The runner-pool Dockerfile pins ARG LLVM_VERSION=19, installs clang-19, lld-19 and llvm-19, links clang-cl, clang, lld-link, llvm-lib, llvm-ar, llvm-rc and lld from that version into /usr/local/bin, and fails the build when clang-cl is older than the pin.
