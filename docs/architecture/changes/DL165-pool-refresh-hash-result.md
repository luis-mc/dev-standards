---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
DL165: pool-refresh replaces a wrong or placeholder RUNNER_SHA256 in the pool .env with the pinned or released hash, and the doctor warns about it. DL166: pool-refresh exits non-zero when the build fails and keeps the old container, and it reports image rebuilt, container recreated or cache hit from image ids read before and after the build.
