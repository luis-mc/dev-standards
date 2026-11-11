# DL183 report

Base check: origin/main 3e36bc0; ci_rerun_first.py exists. Branch head: see `git rev-parse` of branch DL183-rerun-first-pending (last code commit 5dee06d).

## What changed
- ci_rerun_first.py: constant STATUS_CONTEXT = rerun-first/held; post_status(); `--hold-status` (sets pending when it holds; if that fails, nothing is held); `--set-status STATE`.
- ts ci.yml: plan gets `statuses: write` and passes `--hold-status`; the `e2e` job gets `statuses: write` and a closing step (checkout + always() step). Run 2: success / failure / error (cancel). Run 1: failure "first set failed; held jobs not run". No new job (the DL181 job-graph test and the DL147 rule stay true).
- ci_watch.py: `waiting for held jobs (run 2)` while the status is pending and no dispatched run has completed. It reads the status only when scripts/delivery/ci-areas.json has rerun_first true (no extra gh call otherwise).
- Spec R5.52 text extended, feature note and change note added.

## Tests (all pass)
- unittest test_dl183_rerun_first_pending, test_dl181_ci_rerun_first, test_dl147_workflow_needs: 37 OK
- python tools/test_delivery_ci.py --no-mutants: 78 passed, 0 failed
- every test file naming ci_watch under claude/plugins/delivery/tests: OK
- New test file is covered: spec-lint.yml discovers claude/plugins/delivery/tests (unittest discover).
- spec-lint run 42928122244 (areas delivery,docs): success: which areas, train cleanup, CI scripts and templates, setup preflight, ledger/recorder/watcher/hooks, branch gate, change notes enforced, artifact pruning, runner plan, docs plugin, area mapping, packaged smoke, delivery scripts summary. Skipped: change notes, change notes folded, specs/templates, branch gate shards, artifact renderer, transcript folds, model profiles. Failed: docs check, only W1 (docs/work report, expected on a task branch).

## Follow-ups / notes
- By-hand item (setup + doctor): make `rerun-first/held` a required status check. Not done (delivery_ci_setup.py and delivery_doctor.py belong to DL184).
- Limit: a second run cancelled before its e2e job starts leaves the status pending (merge stays blocked). Cancel while e2e runs gives error.
- ci_watch uses the status only; it does not read a run-1 summary.
- docs_check M1 on delivery-speed is answered by "Docs: none" in the commit message.

READY
