---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
The runner pool gets two opt-in image layers, `linux-packaging` and `kvm`, and an optional KVM setting: `POOL_KVM=1` passes `/dev/kvm` (never privileged), the doctor and `pool-plan` report host KVM, `pool-refresh --kvm on|off` sets it, and runners carry the `kvm` label.
