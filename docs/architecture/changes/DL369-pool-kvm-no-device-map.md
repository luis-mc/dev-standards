---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
R5.65: the pool service maps no /dev/kvm device (cgroup rule `c 10:232 rwm` instead), so Docker can restart it at daemon boot before the kvm-loader runs; the supervisor makes the /dev/kvm node itself when the host has kvm.
