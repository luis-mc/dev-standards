---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---

DL115: CI jobs no longer download pinned tools into the wiped job folder. A new `ci_tool.py` fetches each tool once into a cache that outlives the job, checks its SHA-256, and retries the download five times. The gitleaks step in the four track `ci.yml` templates and in this repository's secret scan uses it, and the runner pool mounts a `ci-tools` volume for the cache.
