---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
ci_scope.py gets a fourth scope, `rust-release`: a release pull request whose code files are all Rust (the optional `rust_release` block in ci-scope.json) skips the Node suites.
