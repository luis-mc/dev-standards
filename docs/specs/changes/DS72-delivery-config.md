---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
luismc-delivery 0.2.0: a JSON Schema and `delivery_config.py validate` for `.delivery/config.json` (unknown keys warn); the watcher obeys `watcher.*` and `runner_plan.*`, merges only a head whose CI was green and starts the runner guard itself (D6a); `enforcement` (`mode`, `block_ceiling`, `log_every_block` to `.delivery/blocks.log`); `delivery_doctor.py` self-check and a loud failure when the configured `tz` cannot load.
