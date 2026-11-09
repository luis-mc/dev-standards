---
plugin: claude/plugins/project-setup/.claude-plugin/plugin.json
change: minor
---

DS196: the tech-stack-setup catalog offers Rust as a component role beside any API language, with the parts cli, host-service, library-napi and library-wasm. check_stack.py accepts `{api: X, components: [rust]}` and warns on a Rust component without a recorded reason, a napi addon without a build matrix, and a cross-compile target without a licence note.
