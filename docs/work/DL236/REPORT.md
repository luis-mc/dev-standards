# DL236 report

Base check: `delivery_doctor.py` has `ci.scripts-current` (line 896). Branch made from origin/main.

## Reproduction and cause
Temp git repos. I installed with the plugin as it was before DL204 (DL204 changed exactly `branch_gate.py` and `ci_rerun_first.py`), then ran the current `update`, then the doctor.

- With an install record (the current installer wrote it): both files are `overwritten`, the doctor says ok. Not the bug. CRLF, a different source path and a stale base copy are not causes: `same()` and `digest()` read CRLF as LF, and there is one template source.
- With no install record (an install from before DL201): update 1 keeps both files (`kept (project changes)`, `.new` written) and records the new template as the merge base. Update 2 then prints `merged` for both. The merge has nothing to apply, so the old file stays, but the record is set to the template hash. The doctor warns on exactly those two files from then on. This is the cause I found.
- Second finding, same check: on the ts track with no packaged program the installer skips `package.yml` and `smoke.json` (DL229), but the doctor reported `smoke.json` as missing.

I could not prove which of these the owner's project hit. The owner's report said "overwrote"; the first case never warns. The no-record case matches "installer reports writing them, doctor warns on those two".

## What changed
- `delivery_ci_install.py` `merge_changed`: a merge that leaves the project file as it is, while the file differs from the template, is no merge. The file stays `kept (project changes)` and the template goes to `<file>.new` again. The doctor warning is then the truth. Copying the `.new` over the file clears it.
- `delivery_doctor.py` `scripts_items`: leaves out the package files on ts with no packaged program, as the installer does.
- Spec R13.92 updated, change notes DL236 (feature, architecture).
- A file the project edited still warns; a file the installer wrote never does.

## Tests
- `python3 -m unittest test_dl236_scripts_current_after_install` (tests dir): 5 passed. 2 fail without the source change (old copy without record; ts without packaged program).
- Existing: test_dl112, 120, 150, 191, 201, 204, 212, 213, 227, 229: all OK.
- `python3 tools/test_delivery_ci.py --no-mutants`: 78 passed, 0 failed.
- `python3 claude/plugins/docs/scripts/docs_check.py`: only W1 (this report), allowed.
- spec-lint run 43078950771 (areas=delivery): every delivery job success (CI scripts and workflow templates, artifact pruning, branch gate and trust rule, change notes, area mapping, packaged-program smoke test, ledger/recorder/watcher/hooks, setup preflight, runner plan, train cleanup, delivery scripts). "docs check" failed on W1 only. Others skipped by area.

## Follow-ups
- A project edit with an unchanged template now reports `kept` with a `.new` on each update, not `merged`. Decide if that noise is fine.
- Not proven this was the owner's exact path; ask for the `update` output and `.delivery/ci-install-state.json` if the warning returns.

Branch head SHA: see `git rev-parse origin/DL236-doctor-scripts-current` (the report commit follows).

READY
