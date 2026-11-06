---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
Pool agents now have their own temp folder (`TMPDIR`, `TMP`, `TEMP` in the agent's `.env`). The job hooks empty it and delete the job user's own `/tmp` entries at job start and end. The supervisor and a rerun of `pool-add-agent` repair older agents.
