---
spec: claude/plugins/artifacts/references/artifactspec.md
plugin: claude/plugins/artifacts/.claude-plugin/plugin.json
change: minor
---

The plugin writes files and never git state: the record is written in `docs/artifacts/` of the working tree and left uncommitted, and the project commits and pushes it when it chooses. The plugin never runs `git commit`, `push`, `fetch`, `pull`, `reset`, `rebase`, `checkout`, `switch`, `stash`, `add` or `worktree add`/`remove`, nor a `gh` command that writes. The record worktree is retired and its old copy migrates once, by itself, when newer; `commit` and `push` are removed (they exit 1) and `migrate` is added; no hook or `pending` pushes. R4.13 to R4.17, R4.24 to R4.29, R7.6, R8.16 and R8.17 are rewritten or retired, keeping their IDs; D23 is new. The record format string stays `ARTIFACTSPEC 1.0.0`.
