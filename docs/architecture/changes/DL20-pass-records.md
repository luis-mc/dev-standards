---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
New `pass_records.py` in the shared scripts: an inputs key per shard and pass records on a records branch. `cloud_shard.py run --records` skips a shard whose inputs already passed; `cleanup.py` removes the records of a branch it deletes. Shard tables gain optional `inputs` and `root_files`.
