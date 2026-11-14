---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
The Rust build cache cap now also cleans an oversized current key, the pool sweeps each runner's tool cache over `tool_cache_cap_gb` (default 30 GB) with a new `cache-sweep` action, and the pool doctor warns on an oversized cache and on free disk under 10% (DL342).
