# DS261 to DS263 report

Branch `DS261-ci-templates`, three commits (one per task). Tests: unittest on the files added or touched, all pass.

## DS261 (DL-116, R5.74)
- `changed_areas.py` (reads `.delivery/ci-areas.json`; built on `area_select.py`), `ci_areas_check.py`, snippet `templates/ci-snippets/ci-areas-pattern.yml`, doctor warning `ci-filters`.
- The check looks at `pull_request` and `pull_request_target` only. A `push` filter stays allowed because `ci_skip_check.py` reads it.
- Open point: the shipped ts `ci.yml` still has a `pull_request` `paths-ignore`. It is not changed here. A project that lists it in `watcher.ci_workflows` gets the doctor warning.

## DS262 (DL-117, R5.75)
- `image_reuse.py` (`key`, `exists`, `digest`), snippet `templates/ci-snippets/image-reuse.yml`. Tests use a fake inspect command.

## DS263 (DL-118, DL-112 text, R5.76)
- `pass_records.py to-result` and `copy-to-main`; `lifecycle_release_check.py` accepts record results for the default branch and the same key; the ts `ci.yml` `decide` job copies the records when the push is skipped (`contents: write` on that job only).
- Not touched: `ci_skip_check.py`, `ci_watch.py`, `join.py`.

## Docs
Change notes in `docs/architecture/changes/` (plugin and DELIVERYSPEC) and in the features delivery, delivery-speed and lifecycle. Generated files were rebuilt to check and then restored, not committed; `docs_check` G1 (features/index.md stale) is therefore expected until the release fold.
