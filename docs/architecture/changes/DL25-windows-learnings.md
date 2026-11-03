---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
Templates: `windows_real.py` (Windows-only test table and guard), `windows-msi-linux.sh` and `windows-msi-check.yml` (optional Linux MSI recipe, CI check only), `package-windows.yml`, `publish_token.py` (5xx retry), `rerun_args.py` (safe re-run on Windows), `artifact_prune.py --hold`, and an installer rollback check in `smoke_packaged.py`.
