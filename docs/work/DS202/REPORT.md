# DS202 report: Rust doctor checks

## What changed
- `claude/plugins/delivery/scripts/delivery_doctor.py`: new `rust` check (`check_rust`, `rust_items`). It returns no row unless gate.json `track` is `rust` or `scripts/delivery/rust_ci.py` exists. Other tracks see no output.
- Items: `rust.toolchain` (fail: file missing, or channel not X.Y.Z, e.g. `stable`); `rust.linker` (fail: no `cc` or `zig` on PATH or in the tool cache; message `linker cc not found. Fix: ...`); `rust.windows` (fail: `clang-cl` or `lld-link` missing when a `targets` entry contains `windows`); `rust.pins` (fail: `rustup-init`, `llvm`, `zig` or `cargo-deny` lacks a 64-hex sha256 in `scripts/delivery/tools.json`; missing file, bad JSON or missing keys are findings, never a crash); `rust.advisory` (warn: no `advisory-db*` folder in the tool cache, or older than 7 days); `rust.disk` (warn: under 10 GB free).
- Warnings never fail the check. The doctor changes nothing; each finding prints the command.
- Tests: `claude/plugins/delivery/tests/test_ds202_rust_doctor.py` (14 tests).
- Change note: `docs/architecture/changes/DS202-rust-doctor.md`.
- Assumptions for the spec task: pin names and the `advisory-db*` cache folder name follow the plan; fix commands name `ci_tool.py ensure`, `tools_pin.py` and `rust_ci.py deny`, which DS199/DS200 must match.

## Tests
- `PYTHONPATH=../scripts python3 -m unittest test_ds202_rust_doctor test_doctor` (in tests/): 33 tests OK.
- `python3 tools/ci_areas.py --branch-advice`: heavy, area `delivery`.
- `gh workflow run spec-lint.yml --ref DS202-rust-doctor -f areas=delivery`, runs 42649991914 and 42650142370: both ended `cancelled`. The `docs check` job failed first and cancelled the delivery suites. Setup preflight, area mapping, runner plan and change-notes jobs passed; the suites did not finish, so there is no green delivery result.
- `python3 claude/plugins/docs/scripts/docs_check.py`: 2 errors, 2 warnings. W1 (docs/work, expected). M1: the delivery feature spec is not updated; the brief leaves the spec text to the later docs task (DS203), the change note is added. T2 warnings are for other specs.

## Verdict
Code and unit tests are done. CI is not green: the docs check M1 needs the spec update from the docs task, and the delivery suites were cancelled by that failure. Re-run the area after the spec is written.

Branch head: see `git log -1` on origin/DS202-rust-doctor.

NOT READY
