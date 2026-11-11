# DL212 + DL213 report

Base check: `delivery_ci_install.py` writes `.delivery/ci-install-state.json`: yes. Branch started from origin/main.

## What changed
- DL213 `delivery_ci_install.py`: `update` without `--track` reads the track from `.delivery/config.json` (`track`/`stack`/`ci.track`), then the state file, then `scripts/delivery/gate.json`, then project files (as setup detects). None known: exit 1, message names `--track` and `ts, go, rust, dotnet`. Every install/update records `"track"` in the state file. `config.json` does not hold a track today, so the state file is the usual source.
- DL212 `delivery_doctor.py` (`ci.scripts-current` only): a file the plan marks `same` (equal to the template, CRLF as LF) is ok, whatever the record or a leftover `.new` says. The installer already refreshed the record and base for `same` files on update; the new test pins this.
- Spec R13.92 text updated. Feature notes DL212/DL213 (patch) and change notes in docs/architecture/changes.

## Tests
- test_dl213_update_track.py (4), test_dl212_doctor_same_content.py (3): OK
- test_dl201_install_keep_and_report.py (11), test_doctor.py, test_dl184, test_dl188, test_dl199, test_ds202 (all OK), test_dl120, test_dl150, test_dl112: OK
- `python3 tools/test_delivery_ci.py --no-mutants`: 78 passed, 0 failed
- docs_check.py: only W1 (this report, allowed).
- spec-lint.yml areas=delivery, run 43029446552: all delivery jobs success (packaged-program smoke, runner plan, train cleanup, area mapping, setup preflight, change notes enforced and folded, branch gate and trust rule, artifact pruning, CI scripts and workflow templates, ledger/recorder/watcher/hooks, scripts/templates/cleanup/prune/change notes), area-check success. Only `docs check` failed, on W1 for this report; other jobs skipped.

## Follow-ups
- Strip docs/work before the join (`docs_work.py strip`).
- A stale `.new` beside an identical file is not deleted by update; the doctor ignores it.

Branch head SHA: see `git rev-parse origin/DL213-install-track-and-record`.

READY
