# DL44, DL45, TC12 report

## Files changed
- `claude/plugins/delivery/templates/shared/scripts/delivery/agent_setup.sh` (DL44: new step 3b)
- `tools/test_delivery_gate.py` (5 new Node scenarios in `sc_agent_setup`)
- `docs/guides/cloud-routines.md` (new, DL45; also holds a short Node paragraph)
- `docs/architecture/changes/DL44-node-routines-testcost.md` (plugin note, patch)
- `docs/features/delivery/changes/DL44.md` (docs_fold note, patch)
- `docs/features/test-cost/spec.md` (TC12: `last_verified: 2026-11-04`)

## Decisions
- DL44: the engines range is read with a small built-in parser (>=, >, <=, <, =, ^, ~, x-ranges, `||`). The lowest major that has any version satisfying it is chosen. Installer order: volta, fnm, nvm, then the official tarball (latest patch of that major from the SHASUMS256.txt of nodejs.org; SHA-256 checked before extract). Corepack does not manage Node, so it is not used. A failed install prints a line and continues with the active Node (exit 0).
- Tests inject the installer through `DELIVERY_NODE_INSTALLER`; the tarball download path is not run in tests (no network). `DELIVERY_NODE_BASE_URL` can point it at a mirror.
- DL45: there was no cloud-routine guide, so I made `docs/guides/cloud-routines.md`.
- TC12: the two 4 Nov commits (e519949, 819c7fc) only add `tools/test_setup_pattern.py` and `tools/test_questions_stop.py` to the `profiles` area in `ci_areas.py`. R5.1 to R5.9 and section 7 still hold. No behaviour text changed, so no note, only the verified date.

## Ran
- `python3 tools/test_delivery_gate.py --no-mutants -k agent_setup`: 28 checks, 0 failed.
- `change_notes.py check`: ok.
- `python3 tools/ci_areas.py --branch-advice`: light (test locally only).
- `docs_check.py`: T2 on test-cost is gone. Left: W1 (this report, expected on a task branch) and G1 for `docs/features/index.md` and `docs/llms.txt` (generated files, not committed; `index.md` is stale on main too).
- No mutation pass, no Docker.

## Not touched
AR55 and DL43/DL46 files.

READY
