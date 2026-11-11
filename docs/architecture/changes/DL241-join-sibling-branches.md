---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---

join.py no longer calls sibling branches cut from one shared contract branch "stacked". A real stacked stop lists its files. Each skipped branch prints a `skipped` line. A partial join prints `joined N of M branches; skipped: ...` and exits 3 (conflict or stacked), 5 (missing on the remote) or the gate refusal's code. `--allow-partial` exits 0.
