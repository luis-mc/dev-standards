---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
Release assets and installers are named `<Product>-<version>-<os>-<arch>.<ext>` for every project (DL-96, LC-32). The release check requires that name per target. Updaters look for the new name first and the older `<installer_name>_<version>.<ext>` name second during one transition release.
