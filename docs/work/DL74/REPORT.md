# DL74 report

1. agents.json: `pool_agents.save` writes in place when the target is a mount point or `os.replace` raises EBUSY/EXDEV. Atomic replace kept elsewhere. compose.yaml unchanged.
2. Rerun: `_wanted_windows` matches name, repository, folder, labels and service; a match gets no remove, service-remove or delete-folder step and the service step is `already`. Others are removed.
3. Labels: case-insensitive in plan (`_has_label`), verify, and in `delivery_ci_setup.py` (runner label check and CI_RUNS_ON compare). Stored and CI_RUNS_ON values are left as given and compare equal.
4. Hooks (D99): new step `runner-hooks` copies the hook scripts to `<machine dir>/runner-hooks` and writes the .ps1 wrappers with the full python path. The printed step names that folder. A rerun refreshes.

Outside my owned files: `scripts/delivery_ci_setup.py` (label case, needed for item 3). No ADR file for D99 was written; the spec cites it. Change notes: docs/architecture/changes/DL74-delivery.md, docs/features/delivery/changes/DL74.md. Spec text updated.

Tests:
- `cd claude/plugins/delivery/tests && python3 -m unittest test_runner_pool`: OK (127 tests)
- `python3 -m unittest discover` in the same folder: OK (657 tests)
- `python3 tools/ci_areas.py --branch-advice`: diff unreadable before commit, advises a spec-lint run in CI; not run here.
- `python3 claude/plugins/docs/scripts/docs_check.py`: 0 errors, 0 warnings.

Branch head: 346cea372ad3cec57c1cf48b2a9bc0e8d3e7a518 (before this report line)

READY
