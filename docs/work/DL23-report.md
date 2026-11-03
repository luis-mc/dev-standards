# DL23 report: CIR10 S7, Option 4 core

Status: built, tested, draft PR open. Steps pushed: skeleton, module, tests, spec text, change notes.

## What was built

- `claude/plugins/delivery/templates/shared/scripts/delivery/ci_fallback.py` (standard library, plain git, no service).
  - `fallback_settings`: reads `ci.fallback` (options per OS, `after_min` with no default, `after_min_if_offline`,
    `only_for` = all, optional caps, `records_branch`).
  - `shard_wait_minutes`: only a `queued` job with no `started_at` counts. A pending run (CI_SERIAL) or no jobs is no wait.
  - `fallback_decision` (pure) and `fallback_gate` (decision + caps).
  - `claim` / `read_claim` / `next_attempt`: branch `ci-claim/<sha>/<shard>/<attempt>`, created by a push with an
    empty-expected lease. First claim wins, no pre-emption.
  - `post_checked`: one status per attempt. Refuses another sha, a non-holder, a superseded attempt, and a second
    post (the `ci-posted/...` branch is created first; a failed API call frees it).
  - `reap`: dead claim after the timeout -> `error` ("run lost"), attempt N+1, cap 2.
  - `reserve` / `settle`: caps counter `fallback-counter.json` on the records branch; push with retry; pauses with
    `fallback paused: daily cap` or `monthly cap`; never overruns, also with parallel callers.
  - CLI: `claim` (exit 3 = lost), `post`, `reap`, `gate`.
- Tests: `tools/test_delivery_fallback.py`, 22 tests. A bare git remote and a local HTTP status server. Cases:
  main first, fallback first, a tie (threads), main frees mid-fallback, a dead claim (attempt 2 answers), attempt 2
  dead (final), a cap hit (daily, monthly, two watchers at once), failed API retry, concurrent posts: one status.
- A real bug found by the tests: two callers could make an identical commit and both "win" (git calls the second
  push up to date). Fixed with a nonce in every marker and counter commit.

## Checks run

- `python3 tools/test_delivery_fallback.py`: 22 pass. Mutant (holder check removed) fails 3 tests.
- `claude/plugins/delivery/tests/test_ci_options.py`, `tools/test_delivery_ci.py`, `test_config.py`: pass.
- `docs_check.py`: clean except the expected D9 error for this file (strip before the join).
- `ci_areas.py --branch-advice`: heavy, area `delivery`; the CI workflow is the gate (`spec-lint.yml areas=delivery`).
  Not run here (no `gh`).

## For DL24

Call `fallback_gate` in the watcher. Launch the fallback. The fallback calls `next_attempt`, then `claim` last
(exit 3 = end quietly), runs, then `post_checked` with the same holder string. `reap` runs in the watcher per claimed shard.
`post_checked` needs the claim holder string to match exactly. The cloud path should post through `post_checked`,
not `cloud_status.py post-ready`, or the one-post rule does not cover it. `reap(results_prefix=...)` treats a pushed
result branch as a result, so the reaper does not kill a result that waits for the poster.

## Shared files touched

- `claude/plugins/delivery/references/config-schema.json` (new `ci.fallback` block).
- `docs/features/delivery/spec.md` (new subsection 13.x, R13.30 to R13.35, before `## Versions`; S11 rewrites section 13, so expect a merge there).
- Change notes: `docs/architecture/changes/DL23-option4-core-spec.md`, `...-plugin.md`.

## Open points

- The records branch name `ci-pass-records` is my default. S4 should set the real name; change `records_branch` or the default.
- `CONTRACT.md` is not updated (shared); the install list for `ci_fallback.py` is whatever the installer copies from `templates/shared`.
- The monthly minutes cap reserves the full shard timeout per hosted shard (worst case), then settles. A short run is
  counted at its real minutes after `settle`; DL24 must call `settle`.
- `T2` doc warnings: the spec was touched in this branch; the verified date is the release's business.
