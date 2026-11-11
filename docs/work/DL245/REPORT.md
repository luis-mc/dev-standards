# DL245 report: multi-track install

Base check: `git checkout -B DL245-multi-track-install origin/main`; `plan(track` is in delivery_ci_install.py; templates/rust and templates/ts exist. Ready.

## What changed
- `delivery_ci_install.py`: `--track rust,ts` (and `update` with a track list from config, state or gate.json). One track is installed exactly as before. New: `parse_tracks`, `track_value`, `track_sources`, `merge_ci`, `merge_gate`, `merge_scope`. The merge is a pure function of the template texts. The merged files go to a temp folder only as the source for the normal plan/apply/3-way-merge path.
  - ci.yml: ts jobs keep their ids (the held-job protocol names them); other tracks' jobs get `-<track>` (id, display name, DELIVERY_SHARD, needs). `decide` once. New `tracks` job reads ci-scope.json and switches each track on or off. The aggregate `e2e` job needs every track's jobs and fails on a failed rust job. ts `paths-ignore` drops the Rust paths. A manual run with `only` set skips the other tracks' jobs.
  - gate.json: every step tagged `track`; identical steps once; colliding names `<name>-<track>`; `required_steps`, `fail_fast_order`, `scope_map` per track; loads in the engine (`load_gate`).
  - ci-scope.json: adds `tracks` and `shared`.
  - Other shared paths (package.yml, smoke.json): first track's copy, plus a `note:` line naming the file and the skipped track. A ts project with no packaged program leaves out only the ts copy.
  - State / gate.json keep a string for one track and a list for several.
- `delivery_doctor.py`: `scripts_items` and the rust row read a track list; detail names the tracks.
- `commands/delivery-ci-setup.md` (the setup text): asks for one or more tracks.
- Spec R13.95; change notes `docs/features/delivery/changes/DL245.md`, `docs/architecture/changes/DL245-multi-track-install.md`.
- Tests: `tests/test_dl245_multi_track.py` (26 tests, temp git repos).

## Tests
- `python3 -m unittest discover -s tests -p "test_dl245*"`: 26 OK.
- `-p "test_*install*"`: 58 OK. `-p "test_*doctor*"`: 69 OK. `-p "test_dl2[0-2]*"`: 93 OK. (Two pinned things fixed on the way: the secret-pattern test disliked a name ending in `_KEY`; the dl213 test pins the `--track must be one of` message.)
- `python3 tools/test_delivery_ci.py --no-mutants`: 78 passed, 0 failed.
- `docs_check.py`: only W1 (this report under docs/work/; expected).
- spec-lint `areas=delivery`: run 43090832229 was cancelled by something else (5 suite jobs cancelled mid-step). Dispatched once more: run 43091229607. Every delivery job passed (branch gate, CI scripts and workflow templates, artifact pruning, packaged-program smoke, plugin ledger, train cleanup, setup preflight, runner plan, area mapping, change notes, aggregate). `docs check` failed on W1 only.

## Follow-ups
- `delivery_ci_setup.py` (not mine) still validates a single `track` in `apply`; with several tracks use `--no-install` and run the installer by hand.
- The gate engine reads one `packages.kind`; the merged gate uses the pnpm workspace and keeps each track's value in `packages_by_track`. Dependents for Rust steps are not computed from it.
- The rust `package.yml` is installed when ts has no packaged program; with a Dockerfile the rust copy wins and the ts copy is named in a note.
- The tracks job's globs are in ci-scope.json `tracks`; a project edits them there.

Branch head SHA: see the last commit of DL245-multi-track-install (code at 128047fd1d97bd2778bc5228a60b7332d02b597b).

READY
