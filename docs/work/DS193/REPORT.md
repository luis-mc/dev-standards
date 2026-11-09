# DS193 report

Status: READY

Cause: `strip --apply` only ran `git rm` and deleted the folder. It had no commit step, so the deletions stayed staged and it exited 0. (`--base` is accepted but unused by strip.)

Changed:
- `claude/plugins/docs/scripts/docs_work.py`: after the removal, commit only `docs/work/` (`git commit --only`). If git refuses (hook, no author, lock) or deletions stay staged, exit 1, name how many are staged and print the command to finish.
- `claude/plugins/docs/tests/test_ds193_strip.py` (new): commit succeeds with nothing staged; other staged files stay staged; a failing pre-commit hook gives exit 1 with the finish command.
- `claude/plugins/docs/tests/test_work.py` (not in the owns list): one assertion flipped, since the guard now passes after the strip is committed.
- Change notes: `docs/architecture/changes/DS193-strip-commits.md`, `docs/features/docs/changes/DS193.md`.

Tests:
- `cd claude/plugins/docs/tests && python3 -m unittest discover`: 189 tests, OK.
- `python3 claude/plugins/docs/scripts/docs_check.py`: 0 errors, 0 warnings.

Windows was not run here.

READY
