---
spec: claude/plugins/artifacts/references/artifactspec.md
plugin: claude/plugins/artifacts/.claude-plugin/plugin.json
change: minor
---
The record folder is a per-project setting, `record_dir` in `.claude/artifacts.json` (under `docs/`, default `docs/artifacts`, so projects that set nothing are unchanged), read by the script, the renderer paths and every hook; the new `move-record NEW_DIR [--yes]` command moves the folder without git and writes the setting (R4.37, R4.38).
