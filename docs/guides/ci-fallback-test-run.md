---
title: Set up the CI fallback and try it on a test repository
type: how-to
---
# Set up the CI fallback and try it on a test repository

Use this guide when a project uses Option 4 (its own runners first, a fallback after a wait). The rules are in the [delivery spec](../features/delivery/spec.md), section 13. The steps that start real sessions or real hosted runs are yours to start. No agent does them.

## Read this first

- **An unattended fallback can start up to an hour late.** The watcher is the session that opened the run. When no session is open, only the hourly routine starts the fallback, and a routine runs at most hourly. Plan X (the wait) with that in mind.
- Only waits for a runner count toward X. A run held back by the one-at-a-time setting does not.
- Caps are optional. Without a cap, the fallback spends as much as the waits cause. For hosted runners, set a spending limit in GitHub billing. The plugin cannot do that for you.
- Cloud sessions are Linux. Every Windows shard uses a hosted Windows runner, and only for a ready pull request.

## Set it up

1. In `.delivery/config.json`, add the block below. Pick your own `after_min` (10 is only an example).

   ```json
   {"ci": {"fallback": {
     "kind": "cloud", "after_min": 10, "only_for": "all",
     "cloud":  {"fire_url": "<API URL of the routine>", "token_env": "FALLBACK_ROUTINE_TOKEN"},
     "hosted": {"workflow": "ci-fallback.yml", "ref": "main"}}}}
   ```
2. Run `delivery_ci_install.py install`. It writes `fallback_launch.py`, `fallback_run.py` and `.github/workflows/ci-fallback.yml`.
3. In `ci-fallback.yml`, fill the step marked `PROJECT STEP` with your install commands. Keep it before the claim.
4. Create the routine for cloud shards: a routine with an API trigger whose prompt says "run what the text says". Put its URL in `fire_url` and its token in the cloud environment, under the name in `token_env`. Never write the token to a file.
5. Create the hourly safety net from `templates/shared/routines/ci-fallback-watch.json`. Nothing creates it for you.
6. In the repository ruleset, let the required checks accept "Any source". Statuses are not posted by the Actions app.

## Try it on a test repository

Use a repository that is not a product. It needs a shard table with one quick shard (`echo ok`) and the files from the install step.

1. Offline check, nothing starts: `python scripts/delivery/fallback_launch.py sweep --dry-run`. It prints how many commits it swept and how many shards it would start.
2. Hosted launch by hand: `python scripts/delivery/fallback_launch.py launch --kind hosted --sha <40-char sha> --shard <id>`. Expect one `ci-fallback` run on a hosted runner, one branch `ci-claim/<sha>/<id>/1` and one commit status on that sha.
3. Cloud launch by hand: the same command with `--kind cloud`. Expect one new session for the shard, and the same claim and status.
4. Wait test: make the main runner busy (stop it, or queue a long job), push a commit, and run `ci_watch.py <sha>` in a session. Under X it prints only the waiting line. After X it prints `fallback (...) started for shard ...` once per waiting shard, however long you keep watching.
5. Second watcher: run `fallback_launch.py sweep` while step 4 is going. It starts nothing, because `ci-fallback/<sha>/<shard>` is already reserved.
6. Race: start the main runner after the fallback has started. The first claim wins. The other job ends in seconds and posts nothing.
7. Clean up: delete the test branches `ci-fallback/*`, `ci-claim/*` and `ci-result/*` by hand.

If a step shows two statuses for one context, or a shard that ran twice, stop and report it. That is a bug.

## Tests with fakes

`python tools/test_delivery_fallback_launch.py` covers wait under X (nothing), over X (one launch per waiting shard, once), caps paused (no launch, one warning), Windows (hosted only, ready PR only), a lost claim (no tests) and the ci_watch hook. It uses no network.
