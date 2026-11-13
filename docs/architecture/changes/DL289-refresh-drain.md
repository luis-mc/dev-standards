---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
`pool-refresh` builds the image first, drains the pool (job-started and job-completed hooks keep a per-agent busy marker; the supervisor stops idle listeners and waits for busy ones), then recreates the container with no build. New flag `--drain-timeout`.
