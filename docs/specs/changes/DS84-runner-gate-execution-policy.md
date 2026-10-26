---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
The Windows runner gate docs now state how the runner starts a `.ps1` hook, that the service account needs an execution policy that allows it and read access to Python, and how to test it as that account. `delivery_doctor.py` checks the account's effective PowerShell execution policy on Windows and fails when it is Restricted, AllSigned or undefined.
