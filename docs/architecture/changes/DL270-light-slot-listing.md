---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
DL270: `delivery_ci.py slots` prints the light slots (`light 1`, `light 2`) after the CI slots. The doctor's `machine.slots` check reports a stale light lock like a stale CI slot, and its ok line counts both kinds.
