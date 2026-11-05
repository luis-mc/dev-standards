---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---

The runner pool has an opt-in `browsers` setting (`none` by default, or `chromium`), given with `plan --browsers`. It is written to the pool `.env` as `POOL_BROWSERS` and passed to the image build, which then installs Playwright's Chromium system libraries as root. The plan step says whether the image has them and that it is larger. The CI_RUNS_ON check now also lists workflows that need root (`sudo`, `apt-get`, `apt install`, `--with-deps`, `install-deps`).
