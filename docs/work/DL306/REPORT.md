# DL306 report: cancel the rest of a red train run

Base check: after `git fetch origin main && git checkout -B DL306-red-run-cancel origin/main`, `ci_watch.py` and `train_freeze.py` both exist.

## What changed
- `ci_watch.py`: on a train head (top-level `train_branch_re`, default `^release/`), the first job ending failure, timed_out or cancelled prints the job, runs `gh run cancel` for every non-completed run of that head, logs the freeze lift, and exits 1 at once. Runs we cancel are never reported as a second failure. Agent branches are never cancelled. New flag `--no-cancel-on-red`; config key `ci_watch.cancel_on_red` (default on).
- Freeze: `train_freeze.py` keeps no state. It reads the live runs, so cancelling them is the lift. No change to that file or the pre-push hook.
- Tests: `claude/plugins/delivery/tests/test_dl306_red_run_cancel.py` (10 tests, fake gh).
- Docs: `docs/features/delivery/spec.md` (R5.13 sentence), `CONTRACT.md` paragraph (outside the owned list, one paragraph about this change), feature notes for `delivery` and `delivery-speed`, change note `docs/architecture/changes/DL306-red-run-cancel.md`.

## Tests
- `python3 -m unittest test_dl306_red_run_cancel`: 10 OK.
- Existing dl127, dl226, dl235, dl247, test_ci_options: OK.
- `python3 tools/test_delivery_ci.py --no-mutants`: 78 passed, 0 failed.
- `docs_check.py`: only the expected W1 on docs/work.
- `spec-lint.yml` dispatch (areas=delivery), run 43447987279: every delivery job green; only "docs check" failed, with the expected W1 on docs/work/.

## Follow-ups
- Cancelled runs take a few seconds to end, so a push right after the message can still be blocked for that moment.
- Detection reads `gh run view` jobs for each in-progress run per poll, only for pending runs.

Branch head SHA: see `git rev-parse origin/DL306-red-run-cancel` (code commit a949019).

READY
