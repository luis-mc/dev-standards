# DL121 report: project fixes folded into five shared delivery scripts

Scripts are in claude/plugins/delivery/templates/shared/scripts/delivery/. All new behaviour is off or neutral when unset.

## artifact_prune.py
- New `--config FILE` (default `.delivery/config.json`; a missing file means none; a malformed section exits 2).
- Section `artifact_prune`: `groups` (list) and `min_age_seconds` (default 3600).
  Group: `pattern` (regex, exactly one capture group, full match; the capture is the group name), `keep` (int >= 0, default `--keep`),
  `protect_pr_heads` {`head_prefix`, `base`} (keep artifacts built from the head commit of an open PR from `head_prefix*` into `base`),
  `hold_workflow` (file name; while the newest run per head commit of that workflow failed, was cancelled or timed out in the last 24 h, every artifact of the group stays).
- For grouped artifacts beyond `keep`, also kept: runs still queued or running, artifacts younger than `min_age_seconds`.
- Extra API calls only for options set. Any failure reading them: exit 2.
- Retry for every list, workflow-run read and deletion: exponential backoff with jitter, 5 attempts, on 5xx, 429, rate limits, timeouts, dropped connections. 404 and 410 are not retried and still count as "gone". Env `ARTIFACT_PRUNE_BACKOFF` (default 2 s), `ARTIFACT_PRUNE_PAUSE` (default 0.3 s between deletions).
- Kept unchanged: `--hold NAME --hold-workflow FILE`, the REST fallback, the host check. Unset config gives the old rule.

## session_guard.py
- `repo_slug(value)` (owner/name from slug, host/owner/name, or URL, lower case) and `targets_this_repo(root, repo)`.
- `gh pr create|ready` with `-R/--repo` naming another repository than `origin` is not blocked. When origin cannot be read, the guard stays on. Heredoc splitter untouched.

## ci_scope.py
- `no_test_reads` (config list of globs): matching files never trip a `full_files` valve and are not counted as code.
- `package_json` {`file`, `keys`, `scripts`}: a change of that file trips full only when a key in `keys` (default list: name, type, main, module, exports, bin, engines, packageManager, workspaces, dependencies, devDependencies, peerDependencies, overrides, resolutions, pnpm) changed, or a script whose name matches a `scripts` glob (default `["*"]`) was added, removed or changed. Unreadable JSON or no reader: full. Not configured: the file follows `full_files` as before.
- `decide(..., read_pair=None)`; `git_pair(base)` reads the file at the merge base and at HEAD; `main` passes it when `--base` is used. `changed_from_git` kept.

## ci_watch.py
- `trim_docker_disk(is_windows, run, which, images)`, `trim_command`, `trimmed_gib`, `load_docker_trim`. `finish()` keeps its signature and trims first, then runs post-run hooks.
- Off unless `.delivery/config.json` has `ci.docker_trim: true`. Images: `ci.docker_trim_images` (default `["postgres:16"]`, first one present is used). Windows with docker only. Failure only logs a line. `--no-trim` skips it.
- The trim's child processes pass `creationflags=0x08000000`.

## cleanup.py
- `build_parser()`, `delivery_log_wanted(args, root)`, `config_delivery_log(root)`, `pre_merge_base(ctx, head, default_ref)`.
- The delivery log (train tag and Release) is now OFF by default. On with `--delivery-log` or `.delivery/config.json` `cleanup.delivery_log: true`; `--no-delivery-log` turns it off even then. Needs `--pr`, not `--dry-run`. This changes the old default (on); projects relying on it set the config key. Orchestrator: decide whether the spec says so.
- `joined_of` judges "no work of its own" against the default branch as it was before a merge commit of the train (`pre_merge_base`); a squash merge is unchanged. `--keep-fresh-since` and pass records kept.

## Tests (memory 42-45% before each run)
- `python -m unittest test_dl121_port_fixes` (in claude/plugins/delivery/tests): 20 tests OK.
- `python tools/test_artifact_prune.py --no-mutants` (ARTIFACT_PRUNE_BACKOFF=0, PAUSE=0): 23 passed, 0 failed. Changed: two mutation anchors, and the failing-delete fixture uses HTTP 403 (a 500 is now retried by design).
- `run_suite.py delivery-cleanup` cases delivery_log, joined, pr, join_cleanup: 54, 16, 13, 12 checks, 0 failed. The first full run (before the harness fix) failed 21 delivery-log checks since the log is now opt-in; the harness's `cleanup()` now adds `--delivery-log` on `--pr` runs. A full rerun is blocked by the hook for a heavy suite: left to CI.
- `run_suite.py delivery-shared-fixes` cases f12, f16, f13, f17, f18: pass. Full run is hook-held: left to CI.
- `tools/test_ci_speedups.py --no-mutants`: 8 failures, identical before and after my change (Windows stub `gh` with CRLF, environment).
- Mutation passes and Docker: not run.

Not done: spec text (orchestrator), mutation anchors for the new code.
Branch DL121-port-project-fixes, head c99fa222 (plus the commit that adds this line).

READY
