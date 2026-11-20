# DL376 report: test guardrails guard (DL-99)

Branch: DL376-test-guardrails. Mode default: warn. Requirement list for the join: **DL-99** (new row in DELIVERYSPEC 1b; the join adds the rule line with `<!-- check: DL-99 -->` and the check list entry).

## Files

- `claude/plugins/delivery/templates/shared/scripts/delivery/test_guardrails.py` (new): G1 to G7, `--json`, `--mode`, read only. Scans this repository in about 0.5 s.
- `.../fast_guards.py`: `run_test_guardrails()` runs after the gate steps and project guards on every push; warn never fails, block fails on a break.
- `.../CONTRACT.md`: new last section "DL376".
- `docs/architecture/DELIVERYSPEC.md` 1b: row DL-99 (after DL-96; the IDs between are left to the other task).
- `docs/features/delivery-speed/spec.md`: R5.18 and its test row. Change notes: `docs/features/delivery-speed/changes/DL376.md`, `docs/architecture/changes/DL376-test-guardrails-plugin.md` (plugin.json, minor), `DL376-test-guardrails-spec.md` (DELIVERYSPEC, minor).
- `claude/plugins/delivery/tests/test_dl376_test_guardrails.py` (new, 14 tests).
- NOT changed: `tools.json`. It only holds pinned downloads (version + sha256); a stdlib script is not a pin, and an entry would fail its pin checks. Nothing to register.

## Tests

- `python3 -m unittest claude/plugins/delivery/tests/test_dl376_test_guardrails.py`: 14 tests OK (fixtures for vitest + Playwright, pytest, Go, nextest, plain cargo test; each guardrail broken; warn exit 0; block exit 1; off without reason reported; lower test_timeout_s accepted, higher refused; fixture scan under 2 s).
- Existing tests of fast_guards: `test_dl307_guards_on_input.py` OK (10), `test_dl154_prepush_ignore.py` OK (6, 1 skipped).
- `test_dl172_setup_bounds.py`: import error only when run from the repo root (needs `_helpers` on path); not related.
- `tools/test_delivery_gate.py` not run: the session guard refuses the full delivery-gate suite locally.
- `change_notes.py check --config tools/change-notes.json`: ok.

## docs_check

`python3 claude/plugins/docs/scripts/docs_check.py`: 2 errors, neither from this change.
- G1 `docs/architecture/decisions.md` stale: also fails on clean origin/main; generated, not committed here.
- W1 `docs/work/DL376/REPORT.md`: expected; work files stay on the branch (strip before join).

## Notes

G1 treats a missing explicit timeout as a break for every runner (the tool defaults are not trusted). A per-job `test_timeout_s` lowers the kind's limit for the whole scan, since a config file cannot be tied to one job.

Branch head SHA: see `git rev-parse origin/DL376-test-guardrails`.

READY
