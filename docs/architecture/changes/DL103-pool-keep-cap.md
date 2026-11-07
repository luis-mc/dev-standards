---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
A pool setup rerun now reads the pool .env and keeps its POOL_MEM and POOL_CPUS, which the owner chose; the plan says kept and shows the measured cap beside it. The measured cap replaces it only with --resize, or when the kept cap is under the 4 GiB / 2 CPU floor, and the plan gives that reason. The setup never writes a lower memory or processors value to .wslconfig. A new pool-refresh step rewrites only RUNNER_SHA256, POOL_BROWSERS and PLAYWRIGHT_VERSION and rebuilds the image when no job runs; the cap stays. The pool build writes a missing RUNNER_SHA256 to .env. The doctor's fixes for a missing variable and for missing browsers name pool-refresh (D118).
