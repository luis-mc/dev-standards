# DL256 report

## Base check
`delivery_ci_install.py` takes several tracks (DL245: `--track rust,ts`, `plan` takes a list). `delivery_ci_setup.py` read `answers.get("track")`. Both present, so the work went ahead.

## What changed
- `delivery_ci_setup.py`: `track` is a string or a list, each name checked. `detect_tracks` returns every track found in the order ts, go, rust, dotnet. `facts` adds `tracks` and keeps `track` (one string for one track). `apply` passes every track to `INS.plan` (a string for one track) and prints a `Tracks:` line; `--json` has `tracks`.
- `delivery_common.py` (gate): `package_kinds` gives each package its own kind from `packages_by_track`; one repo-wide `packages.kind` works as before. A step tagged with a `track` gets only that track's packages in `{changed_dirs}` and `{affected_dirs}`. `packages_by_track` is validated. The installer already wrote `packages_by_track`, so it was not touched.
- `commands/delivery-ci-setup.md` (the setup skill is this command file): the track question tells the agent to send a list; no separate installer run.
- Spec R13.95 (setup and gate text), feature note, architecture change note.

## Tests
- `python3 -m unittest test_dl256_multi_track_setup` (new, 11 tests): OK.
- All delivery tests (`unittest discover` in claude/plugins/delivery/tests): 1490 tests, OK (3 skipped). One existing test needed `step_dirs` to tolerate a context without `package_kinds`; fixed.
- `python3 tools/test_delivery_ci.py --no-mutants`: 78 passed, 0 failed.
- `python3 claude/plugins/docs/scripts/docs_check.py`: only W1 (docs/work), expected on a branch.
- `spec-lint.yml` with `areas=delivery` (run 43112754104): all delivery jobs success; `docs check` failed only on W1 (expected).

## Follow-ups
- `docs_check` M1 wanted a doc for `docs/features/delivery-speed/spec.md` (it maps `delivery_common.py`); handled with `Docs: none` in the commit message.
- Not done: the gate's e2e/ui logic (`affected_package_dirs`, ui paths) still uses the repo-wide pnpm kind.
- `delivery_ci_install.py` not edited; no change needed.

## Branch head
Branch DL256-multi-track-setup, head: see `git log -1` on the branch.

READY
