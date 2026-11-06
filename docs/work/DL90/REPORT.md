# DL90 report

- find_root (delivery_ledger.py): a `.delivery/` counts only with config.json or ledger.json; a git worktree (.git file with gitdir `.../worktrees/...`) resolves to its main checkout through `commondir` (else the parent of `worktrees`), by file reads only. Fallbacks (any .delivery, then .git) are unchanged.
- Callers: hook_post_tool.py (two calls) and delivery_watch.py use this find_root and now reach the main ledger from a worktree. The other hooks use hooklib.find_root, a separate function, not changed (not in my files). None relied on stopping at a worktree.
- New `link --pr N [--sha] [--branch]`: train by --branch, else PR head branch, else the only open train; refuses when ambiguous; writes event `train.link`.
- Spec: one paragraph after R5.2 in docs/features/delivery/spec.md. Notes: docs/architecture/changes/DL90-delivery.md, docs/features/delivery/changes/DL90.md.
- Tests: `python3 -m unittest test_ledger_root_worktree test_ledger test_post_tool` (117) OK; `test_watch` (83) OK.
- ci_areas --branch-advice: "unreadable diff, run everything" (heavy CI workflow); not run, too heavy.
- docs_check: only G1 stale decisions.md (expected). No W1 shown.

READY
