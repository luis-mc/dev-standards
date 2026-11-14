---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
The pool loads kvm_intel or kvm_amd in the Docker VM before it starts or recreates with POOL_KVM=1, and the pool doctor and setup warn when .wslconfig lacks nestedVirtualization=true (DL343).
