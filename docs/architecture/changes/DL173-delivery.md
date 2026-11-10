---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
New `references/plugin-compat.json` lists the lowest version each luismc plugin needs of the plugins whose files it reads. `delivery_doctor.py` has a new `plugins.compat` check that warns, per installed pair that does not fit, with the `claude plugin update` command.
