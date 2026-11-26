# DL420 report (DL420, DL421, DL422)

Branch: `DL420-docs-findings`.

## DL420 (scope change applied)
- New `claude/plugins/docs/scripts/ledger_links.py`, read-only. A train with branch `<TASK-ID>-integration` belongs to the release with that task ID. Its `pr` fills a release with no `pr`.
- `release_waits_on` is filled when unset: the release waits on every earlier open release when (a) its train holds commits of the other train not yet on the base branch (git rev-list; skipped if git cannot say), or (b) `deploy.serial` is true and the other train merged first.
- `render_artifacts._tasks()` applies it. `--pr` and `--release-waits-on` on the row win. No ledger: no change. `tree_mode()` is then on for any project with a linked PR.
- `deploy.serial` (boolean, default false) added to the delivery config schema, `delivery_config.deploy()` and the delivery README. Expect a rebase against DL418.
- Spec text: `docs/features/artifacts/spec.md` R5.29, `references/artifactspec.md` R5.59.

## DL421
`docs_fold.py note` sets `last_verified` to today in the doc (R5.11b in the docs spec).

## DL422
There is no `rule add` command in `design_system.py`. The flow that exists is `visuals`, so it now prints the missing `Proof: UX-n <test path>` line for each cited rule without a test (R5.26 in the docs spec). There is no separate design-system feature spec; the docs spec covers it.

## Tests
`test_dl420_ledger_links.py` (pr from ledger, ancestry wait, serial wait, explicit wins, no ledger, others), `test_dl421_dl422.py`. Delivery `test_config.py` passes. `docs_check.py`: 0 errors.
