# DL307 report

Base check: `fast_guards.py` exists on origin/main.

## What changed
- `delivery_common.py`: `load_gate` validates the new optional `always_on_guards` list (`{name, command, inputs}`).
- `fast_guards.py`: after the `pre_push` steps, runs each guard whose input globs match a file changed since the base, one at a time. Others are skipped with one line. `["**"]` always runs. A failure fails the run with the guard name and output tail. No list: old behaviour.
- ts `gate.json`: a `boundary` guard (dependency-cruiser) declared this way.
- Docs: CONTRACT.md, DELIVERYSPEC DL-84, delivery spec R13 new requirement, notes for delivery-speed and architecture.

## Tests
- `python3 -m unittest claude/plugins/delivery/tests/test_dl307_guards_on_input.py`: 10 ok.
- `python3 tools/test_delivery_ci.py --no-mutants`: 78 passed, 0 failed.
- test_dl154 (existing fast_guards): ok.
- `docs_check.py`: only W1 on docs/work (expected).
- CI spec-lint.yml areas=delivery run 43447898347: every delivery job success; only `docs check` failed, on W1 (expected).

## Follow-ups
- Full delivery-gate suite left to CI (heavy suite rule).
- Other tracks' gate.json (go, dotnet, rust) not given a boundary guard; rust left untouched for DL304.

Branch head SHA: see `git rev-parse DL307-guards-on-input` (report commit follows).

READY
