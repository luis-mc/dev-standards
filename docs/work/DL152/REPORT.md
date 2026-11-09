# DL152 report

## What changed
- New `docs/guides/windows-packaging.md`: layer contents, how to turn it on, MSI build on the pool, and "Service permissions (WiX 5)" with the correct form and the failing form (WIX0004, WIX0010).
- `docs/features/delivery/spec.md`: added R13.76 after R13.71, the last rule in section 13.
- Change notes: `docs/architecture/changes/DL152-wix-service-dacl.md` and `docs/features/delivery/changes/DL152.md`.
- Missing link: `docs/README.md` has no guides list (it lists folders only), so the guide is not linked there.

## Tests
- `python3 claude/plugins/docs/scripts/docs_check.py`: FAIL, 2 errors. Both are G1 stale generated files: `docs/architecture/decisions.md` (already stale on main) and `docs/llms.txt` (stale because of the new guide). Rules forbid committing generated files, so I left them. The release fold must rebuild them.
- `gh workflow run spec-lint.yml --ref DL152-wix-service-dacl -f areas=delivery` (run 42716946076): overall failure.
  - docs check: failure (the same two G1 errors).
  - which areas does this change touch: success.
  - All delivery jobs (CI scripts and workflow templates, train cleanup, area mapping, runner plan, change notes enforced and folded, branch gate and trust rule, packaged-program smoke test, setup preflight, plugin ledger/recorder/watcher/hooks, artifact pruning, scripts/CI templates/cleanup/prune/change notes): success.
  - Other jobs: skipped.

## Branch head
See the branch head on origin/DL152-wix-service-dacl after the last push.

NOT READY
