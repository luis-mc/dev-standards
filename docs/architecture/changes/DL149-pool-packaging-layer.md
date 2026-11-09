---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
DL149 adds an opt-in `windows-packaging` layer and a project apt fragment to the shared Linux pool image. The layer is turned on with `pool.layers` in `.delivery/config.json`; the fragment is `.delivery/pool.apt`. The pool rebuild now refuses while a pool runner is busy, and the doctor checks the layer tools, stray runner Dockerfiles and the tool cache volume.
