# DL294 report

Base check: ci_scope.py on origin/main (0d4a9cf) has `is_release_pr` and `decide`.

## What changed
- `ci_scope.py`: new `is_rust_only(rule, code)`; `decide()` returns `rust-release` on a release PR whose code files are all Rust. Docstring says "Four scopes" and lists the `rust_release` key.
- `ts/scripts/delivery/ci-scope.json`: comment line about the optional block. No block added: the ts template has no Rust part; the rust template ships no ci-scope.json.
- `ts/.github/workflows/ci.yml` comment and `CONTRACT.md` row list the new scope.
- Scope consumers: the workflow only passes `scope` through, and `ci_run_times.py` only labels by it. Nothing enumerates scopes, so no code change was needed.
- Docs: R5.60 in `docs/features/delivery/spec.md`; notes for features/delivery and features/delivery-speed; change note `docs/architecture/changes/DL294-rust-release-scope.md`.
- Tests: `claude/plugins/delivery/tests/test_dl294_rust_release_scope.py` (8 cases).

## Tests
- `python3 -m unittest discover -s claude/plugins/delivery/tests -p "test_dl294*.py"`: 8 ok.
- `python3 tools/test_delivery_ci.py --no-mutants`: 78 passed, 0 failed.
- `tools/test_ci_speedups.py` not run locally: the session guard marks it heavy. CI ran it (delivery area).
- `gh workflow run spec-lint.yml --ref DL294-rust-release-scope -f areas=delivery` (run 43426546688): every delivery job success. Only `docs check` failed: W1 (docs/work, expected on a branch) and G1 (`docs/architecture/decisions.md` stale; generated, not edited here).

## Follow-ups
- The project's own CI plan must act on `rust-release` (run only Rust-build tests); its choice.
- Regenerate `docs/architecture/decisions.md` (`docs_index.py build`) at the release fold.
- A rust template ci-scope.json example could carry the block; none exists today.

Branch head SHA: see `git rev-parse DL294-rust-release-scope` (the final report commit).
READY
