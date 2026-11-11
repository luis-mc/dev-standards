---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
DL237: the shipped `.gitleaks.toml` allowlist skips two more never-secret line shapes: a SQL placeholder bound to a `_key`/`_token`/`_secret`/`_pass` name with more SQL after it, and a nested call such as `Some(Arc::new(signer))`. A quote, a bare token or a second assignment on the line keeps the line scanned.
