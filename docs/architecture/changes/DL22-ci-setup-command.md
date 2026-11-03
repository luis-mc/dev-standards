---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
New command `/delivery-ci-setup` and engine `delivery_ci_setup.py`: guided CI setup for Options 1 to 3 that writes `.delivery/config.json`, runs the installer and the doctor, and prints a numbered by-hand list. The doctor `ci` check now verifies each step of that list for a project the setup configured.
