---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
The runner pool now installs the Chromium system libraries for the Playwright version the projects use. With `browsers: chromium`, `plan` reads the resolved version from the lockfiles of the local agent repositories (`--repo-path`, repeatable) and takes the highest. `--playwright-version X.Y.Z` overrides it. With neither, the pin is now 1.62.1. The version goes to the pool `.env` and the build, and the `pool-files` step says where it came from.
