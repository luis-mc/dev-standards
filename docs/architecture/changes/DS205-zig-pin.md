---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
DS205 pins Zig 0.17.1 in `tools.json` from the `ziglang` wheels on PyPI (linux x64 and arm64, windows x64, darwin x64 and arm64), each with its sha256 from the PyPI JSON API. `ci_tool.py` gets a `wheel` kind: it unpacks the wheel like a zip and keeps the exec bit, so `ci_tool.py tool zig` prints the `zig` path. `rust_ci.py` now says Zig is missing only when the pin is missing.
