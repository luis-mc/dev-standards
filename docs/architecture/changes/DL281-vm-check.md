---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
Adds `vm_check.py` and `vm-images.json` to the shared delivery scripts: throwaway distro VMs on kvm runners, with a shared cache, resume snapshots and an SELinux check. The pool supervisor makes the shared cache folder.
