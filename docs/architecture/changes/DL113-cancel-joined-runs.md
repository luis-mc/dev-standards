---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
DL113 adds `cancel_joined_runs.py`. It lists the CI runs of agent branches already merged into an integration branch and cancels them with `--yes`, so a single runner is free for the release pull request. It is a dry run by default.
