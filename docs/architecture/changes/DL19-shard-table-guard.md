---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
The shard table gets suites, `part` and `members`, `limits` and `size`. New `shard_guard.py` fails when a test file is in no shard or in two shards or a shard breaks its limits. `shard_balance.py --table` cuts every suite by timings. `cloud_shard.py` sets worker, cpu and memory variables, expands `{files}` and fails a shard whose peak memory is over its limit.
