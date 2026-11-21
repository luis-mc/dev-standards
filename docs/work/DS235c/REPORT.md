# DS235c report

Status: done. Branch `DS235c-lifecycle-conformance`.

## Files

- `claude/plugins/delivery/templates/lifecycle/CONTRACT.md`: the test interface (verbs, state object, fake server, allowed moves).
- `claude/plugins/delivery/templates/shared/scripts/delivery/lifecycle_conformance.py`: the runner (LC-3, 4, 5, 6, 7, 25, 26, 28; PASS or FAIL with reason; `--json`; pure-Python Ed25519 for the fake server).
- `claude/plugins/delivery/templates/lifecycle/rust/`: Rust core (`src/lib.rs`), test server (`src/main.rs`), `tests/conformance.rs`.
- `claude/plugins/delivery/templates/lifecycle/go/`: Go core (`updater.go`, `testiface.go`, `conformance_test.go`).
- `claude/plugins/delivery/templates/shared/scripts/delivery/tools.json`: `lifecycle-conformance` registered (no pin, no download).
- `docs/architecture/DELIVERYSPEC.md` 1b: DL-LC1, DL-LC2, DL-LC3 (new IDs only).
- `docs/features/delivery-speed/spec.md`: R5.25, R5.26 and the code map line.
- `claude/plugins/delivery/tests/test_ds235c_conformance.py`.
- Change notes: `docs/architecture/changes/DS235c-lifecycle-conformance.md`, `docs/features/delivery-speed/changes/DS235c.md`.

## Tests

| Command | Result |
|---|---|
| `python3 -m unittest test_ds235c_conformance test_ds205_zig_pin test_dl115_ci_tool` (in `claude/plugins/delivery/tests`) | 24 tests OK. Includes the Rust (`cargo test`) and Go (`go test`) cores passing all 8 checks. |
| Python fake updater | passes all 8 checks; 12 single faults (ignore signature, expiry, older version; 8 h interval; wrong backoff; ignored window; required asks; retry at 30 min; no actor; settings without window; check while unpaired) each fail exactly one check. |
| `change_notes.py check --config tools/change-notes.json` | ok |

The Rust and Go tests skip with a reason when the toolchain is missing (cargo also skips when crates cannot be fetched).

## docs_check

`python3 claude/plugins/docs/scripts/docs_check.py`: 3 errors, none to fix on this branch.

- G1 `docs/llms.txt` stale: already stale on `origin/main`. Generated file, not edited.
- G1 `docs/docs-map.json` stale: caused by the new spec rows. Generated file, the release fold rebuilds it. Not edited.
- W1 `docs/work/DS235c/REPORT.md`: expected; reports stay on the branch.

## Notes

- The brief's `lifecycle.json` schema (DS235a) is not on `main` yet. The runner reads only `test_interface` (`transport` http with `url`, or cli with `command`); `--url` and `--cmd` override it.
- DELIVERYSPEC IDs are `DL-LC1` to `DL-LC3` so they cannot collide with numbered DL IDs from other branches.
- Settled in CONTRACT.md: a remote install needs no click; the install window is a timer while `waiting`.

READY
