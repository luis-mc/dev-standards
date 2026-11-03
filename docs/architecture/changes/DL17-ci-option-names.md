---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
CI options are named Option 1 to 4. Option 1 is the user's own self-hosted runners on any machines they run. `delivery_ci.py set` takes 1, 2 or 3 (the config names and the old letters still work) and `delivery_ci.py add-runner` prints the by-hand steps to add a runner on another machine. The `ci` doctor check names the runners it found and those steps for each OS. The config schema gains an empty `ci.fallback` block for Option 4.
