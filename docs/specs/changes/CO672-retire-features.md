---
spec: claude/plugins/artifacts/references/artifactspec.md
plugin: claude/plugins/artifacts/.claude-plugin/plugin.json
change: minor
---
New `retire KEY [--yes]` removes a finished feature artifact (every task Live or Dropped) and its content, moving it to the manifest's `retired_features` list with its decisions archived in `retired/<key>.decisions.json`; its tasks keep their owner, Full Progress lists it in one collapsed line, a retired key is reused only with `feature-new --force`, and without `--yes` it is a dry run (R4.31 to R4.36).
