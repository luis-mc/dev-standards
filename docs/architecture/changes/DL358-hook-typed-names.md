---
plugin: claude/plugins/project-setup/.claude-plugin/plugin.json
change: patch
---
The shipped pre-commit hook matches secret-shaped names the way .gitleaks.toml does: typed names (`path_key: &str`) and Rust paths pass; quoted or assigned values are still blocked (DL358).
