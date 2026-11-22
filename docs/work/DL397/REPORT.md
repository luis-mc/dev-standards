# DL397 (with DL400) report

## Files
- claude/plugins/delivery/scripts/delivery_ci_install.py: `merge_gate_steps`; `update` merges gate.json by step name, keeps project steps, prints added steps. `install` already kept an existing gate.json; no other path writes it.
- claude/plugins/delivery/scripts/delivery_doctor.py: `check_gate_steps` (e2e spec files tracked, no ui-changed step).
- claude/plugins/delivery/templates/shared/scripts/delivery/e2e_push_check.py: prints a "no e2e step in gate.json" hint and allows the push when there is no e2e step.
- claude/plugins/delivery/templates/shared/.githooks/pre-push: `--diff-filter=d` on the only diff there (DL400). It is the only pre-push template.
- Templates gate.json: go (`-timeout 10s`), ts (vitest `--testTimeout=10000`), dotnet (`--blame-hang-timeout 10s`). Rust left alone: `cargo test` has no per-test timeout; G1 asks for nextest. The ts e2e command is unchanged because test_e2e_chromium pins its text.
- tests/test_dl397_gate_sync.py (7 tests).
- docs: spec rows R13.92b, R5.36c; notes DL397/DL400 under docs/architecture/changes and docs/features/delivery/changes.

## Tests (from claude/plugins/delivery/tests)
- python3 -m unittest test_dl397_gate_sync test_e2e_chromium: OK (13).
- Installer, doctor, gate, e2e, template tests (245): OK after pinning the ts e2e command. The hook test fails without the fix.

## docs_check
M1 passes. One error left: W1 (docs/work/DL397/REPORT.md is on the branch). That is by design (D9); strip before the join.

## Branch head (code commit)
82fd77a3af342f97ae02d59937adc0ecb24bce64

READY
