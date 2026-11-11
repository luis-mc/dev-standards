# DL193 report (done)

## Base check
Branch made from origin/DS228-integration. `rust_ci.py` is present.

## Flag evidence (cargo-deny 0.20.2)
I built the exact release (`cargo install --locked cargo-deny@0.20.2`) and ran it.
- `cargo deny check --disable-fetch` -> `error: unexpected argument '--disable-fetch' found`.
- `cargo deny check --offline` -> `error: unexpected argument '--offline' found` (not a check flag).
- `cargo deny --help` lists `--offline` (top-level): "Run without accessing the network."
- Source, `src/cargo-deny/main.rs`: `Arg::new("offline").long("offline").help("Run without accessing the network.").long_help("...Disables fetching crates, advisory databases, and std-replacement-data")`. It is added to the top-level command (`GraphContext::fill(cmd)`), so it goes before the subcommand.
- Source, `src/cargo-deny/check.rs`: "Previously we had a separate check-only flag to disable fetching the advisory database ... but now we just use this single flag that is used for all subcommands". With `offline`, `advisories::Fetch::Disallow(maximum_db_staleness)` is used.

## What changed
- `cmd_deny` now runs `cargo deny --config <cfg> --offline check`.
- `test_ds200_rust_ci.py` asserts `--offline check`.
- New `test_dl193_cargo_deny_flags.py` asserts the exact argv of both calls.
- Feature note `docs/features/delivery/changes/DL193.md`; change note `docs/architecture/changes/DL193-cargo-deny-flags.md`.

## Tests
- `python3 -m unittest test_ds200_rust_ci test_dl193_cargo_deny_flags` (in the tests dir): 18 tests OK.
- `python3 tools/test_delivery_ci.py --no-mutants`: 78 passed, 0 failed.
- `docs_check.py`: only W1 (this report under docs/work, expected) and a T2 warning.
- spec-lint run 42937989695 (areas=delivery,docs): all delivery jobs and docs plugin success; `docs check` failed on M1 (delivery-speed spec maps rust_ci.py) and W1. M1 is fixed by `Docs: none` in the commit message of this report commit; W1 is expected. 

## Follow-ups
- cargo-deny with `--offline` checks the db age against `maximum_db_staleness` (git fetch time), separate from this script's 7-day cache stamp.
- delivery-speed spec maps rust_ci.py; its owner may want a note.

- Rerun 42938358935: every job success or skipped except `docs check`, which fails only on W1 (expected, this report).

Branch head SHA: see `git rev-parse origin/DL193-cargo-deny-flags` (the commit that holds this report).

READY
