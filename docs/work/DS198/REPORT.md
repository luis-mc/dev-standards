# DS198 report

## What changed
- Added under `claude/plugins/project-setup/skills/tech-stack-setup/assets/tooling/rust/`: `Cargo.toml` (resolver 2, `crates/*` members, `[workspace.package]`, `[workspace.dependencies]`, fixed release profile), `rust-toolchain.toml` (exact `1.91.0`, minimal, rustfmt + clippy, empty targets; the version is a starting pin, bump it in its own change), `rustfmt.toml`, `deny.toml` (advisories, bans, licenses, sources).
- Tooling README: new "Rust wording for the invariants" section with the plan 4.4 table; tree line for `rust/` updated. No technology names in STACKSPEC.
- Change note `docs/architecture/changes/DS198-rust-tooling-assets.md` (plugin, minor).
- No product crates; catalog and check_stack.py untouched.

## Behaviour for the spec text
Copy the four files to the repo root beside `crates/guards`; every cargo command uses `--locked`; CI installs the exact toolchain version.

## Tests
- `python3 tools/ci_areas.py --branch-advice`: heavy, unreadable diff; advises `gh workflow run spec-lint.yml --ref DS198-rust-tooling-assets -f areas=specs,delivery,artifacts,profiles,transcript-folds,docs`. Not run: no `gh` CLI in this environment.
- `python3 claude/plugins/docs/scripts/docs_check.py`: 1 error, M1 (mapped code changed; the feature spec is written by the later docs task, commit says `Docs: none`). No G1/W1 seen.

