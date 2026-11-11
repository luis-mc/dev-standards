# DL227 report

Base check: `not in git yet` was present in delivery_ci_install.py on origin/main. Branch DL227-installer-peer-fixes was cut from it.

## What changed
- `delivery_ci_install.py`: `files_of` skips `.pyc`/`.pyo` (it already skipped `__pycache__`). New marked `.gitignore` block (`__pycache__/`, `*.pyc`), idempotent, keeps other lines and line endings. Tracked `.pyc` under installed folders are listed with a `git rm --cached` command; never removed. Files that `git check-ignore` reports are left out of `not in git yet` and named on one line `ignored by .gitignore: ...`. A failed prune sync no longer counts the file as merged (shown as `sync failed`).
- `artifact_prune.py` (template): the root cause was CRLF line endings (the `$` anchor failed before `\r`). The match now takes any indent (or none), bare or quoted names, a trailing comment, and keeps CRLF.
- Spec R13.92 gets the three rules. Feature note `docs/features/delivery/changes/DL227.md`; change note `docs/architecture/changes/DL227-installer-peer-fixes.md`.

## Tests
- `tests/test_dl227_install_peer_fixes.py` (5 tests): OK.
- Existing: test_dl112, dl120, dl122, dl150, dl201, dl204, dl218: all OK.
- `python3 tools/test_delivery_ci.py --no-mutants`: 78 passed, 0 failed.
- `python3 tools/ci_areas.py --branch-advice`: light, test locally only.
- `docs_check.py`: G1 (decisions.md stale, generated) and W1 (docs/work on branch) only. M1 on delivery-speed is answered by a `Docs: none` line in the commit message.
- spec-lint run 43064459682 (areas=delivery): all delivery jobs success (branch gate, ledger/hooks, setup preflight, CI scripts, artifact pruning, runner plan, train cleanup, change notes, packaged smoke, area mapping, umbrella). `docs check` failed on G1/W1 only (same as local); others skipped by area.

## Follow-ups
- A stale `.pyc` already tracked in a project needs the owner to run the printed `git rm --cached` command.
- Run `docs_index.py build` at the release fold (G1); `docs_work.py strip` before join (W1).

Branch head SHA: see `git rev-parse HEAD` of the pushed branch.

READY
