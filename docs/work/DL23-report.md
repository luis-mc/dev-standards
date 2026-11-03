# DL23 report: CIR10 S7, Option 4 core

Status: skeleton pushed. Bodies, tests, spec text and change note follow.

## Interface for DL24

`claude/plugins/delivery/templates/shared/scripts/delivery/ci_fallback.py`. The module docstring lists every public
function with its arguments and return shape. Those are final. DL24 calls `fallback_gate` (watcher), then launches
the fallback, which calls `next_attempt` + `claim` last and `post_checked` at the end. `reap` runs in the watcher.

## Shared files (touched by this branch)

- none yet
