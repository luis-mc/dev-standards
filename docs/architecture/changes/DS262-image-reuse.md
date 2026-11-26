---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---

New `image_reuse.py` (`key`, `exists`, `digest`) and the `image-reuse.yml` snippet: a base image is built once per input set, reused by digest only when main built it, and rebuilt clean every week (DS262).
