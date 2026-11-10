---
plugin: claude/plugins/artifacts/.claude-plugin/plugin.json
change: minor
---
The ledger and ci-runs readers check the file's `schema`. A file with a missing or newer schema still reads as empty, and `check` and `pending` now print one warning that names the update. A file that does not exist stays silent.
