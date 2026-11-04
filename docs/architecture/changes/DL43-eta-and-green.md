# DL43-eta-and-green

- plugin: claude/plugins/delivery/.claude-plugin/plugin.json
- spec: docs/architecture/DELIVERYSPEC.md
- change: patch

DL-31 no longer flags past events ("failed about 2 minutes in", "started 1 minute ago"); it still flags forecasts.
DL-03 (DL46): a train is green only when every workflow that runs on pull_request has a finished run on the PR head with success or skipped. Push-only workflows are not waited on.
