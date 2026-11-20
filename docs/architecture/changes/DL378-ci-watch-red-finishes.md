---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
ci_watch no longer cancels a red run by default (D105, DL-97): it waits for every job and lists every failed job. `ci_watch.cancel_on_red` or `--cancel-on-red` cancels only a blocking failure (setup, install, lockfile, build, checkout; `ci_watch.blocking_job_re`).
