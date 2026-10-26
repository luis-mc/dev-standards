# CO220 report: luismc-delivery checks

Branch `claude/CO220-delivery-checks`. Plugin version: **0.3.0 after the fold** (this branch keeps 0.2.0 and carries the minor change note `docs/specs/changes/CO220-delivery-checks.md`; the repo CI forbids a version or CHANGELOG edit on a feature branch).

## 1. DL-31 false positives (done)
`hook_stop.py`: an ETA sentence is skipped when it reports a measured duration, saving or cost (took, saves, costs, each, per, was...) or lists two or more durations; a clock time or dependency anywhere in the same bullet covers its sentences. Real ETAs ("ready in about 5 minutes", "takes about 1 hour") still flag. Tests in `tests/test_stop.py`: the three examples from the owner (no flag), real ETAs (flag), clock time in the same bullet.

## 2. DL-03 false green (done)
Cause: `hook_post_tool.py` `_rec_ci_watch` set `green_at` on any `ci_watch.py` exit 0 and, when the SHA matched no train, fell back to the first pushed train. A pass on one workflow (or another commit) therefore greened a train while the release CI was still running. The watcher read only `ci.yml` and treated `skipped` as success.
Fix: the hook never greens (event `ci_watch.passed`; red on failure; no fallback train). The watcher greens only when every `watcher.ci_workflows` workflow (default `ci.yml`) has its latest run completed with `success` on the head; missing, running, skipped or failed is not green; green is revoked (`green_at` cleared) when a required run is running again. Tests in `test_watch.py` and `test_post_tool.py`.
Not verified against the live runs of a real project (no access to it); the cause is derived from the code. Set `watcher.ci_workflows` in that project if its release CI is more than `ci.yml`.

## 3. DL-76 one CI per release (done)
New Stop check. With `pr_proven_jobs` in `.delivery/config.json`, for each merged, not cleaned train it reads the PR merge commit, compares its tree with the PR head tree (different tree: silent), lists default-branch runs of that commit and flags each non-skipped job named in the list. Off by default, no network when empty, silent on `gh` errors. Documented in the README and DELIVERYSPEC (rule text verbatim). Tests in `tests/test_stop.py`.

## Checks
Plugin suite once: 108 tests OK. `tools/test_delivery_hooks.py` once: 44 passed.
