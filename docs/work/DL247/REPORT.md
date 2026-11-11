# DL247 report: ci_watch gives up with its own exit code

**Base check:** `origin/main` ci_watch.py contains `giving up, gh failed` (3 places). OK.

**Finding:** at this base the three give-up paths already `return 2`, not 0, so the "exits 0" symptom did not reproduce here. Two real defects were fixed: give-up shared code 2 with usage errors, and the third path (the open-PR lookup after a good run list) never reached five, because the run-list success reset the counter each poll; a persistent failure there ran to the timeout (exit 4).

## What changed
- `ci_watch.py`: `GIVE_UP_EXIT = 5` on all three give-up paths; the third path counts its own failures. New `resolve_repo()`: `--repo`, else `gh repo view --json nameWithOwner`, once at start; failure exits 2 at once with a clear line. All later gh calls then carry the repo (`--repo`, or `repos/OWNER/NAME` in `gh api` paths; `gh api rate_limit` has no repo).
- New `test_dl247_ci_watch_give_up.py` (7 tests): each of three paths gives 5; every call after start carries the repo; `--repo` skips the lookup; no repo exits 2; success exits 0.
- Existing tests updated to stub `resolve_repo` (dl183, dl226, dl235, and `tools/test_delivery_fallback_launch.py`), and `tools/test_delivery_ci.py` (stub answers `repo view`, maps the pinned repo to its placeholder fixtures, exit 2 -> 5 in two give-up tests). These two `tools/` files are outside the owns list; they pin ci_watch behaviour.
- Docs: delivery spec R5.56, `docs/features/delivery/changes/DL247.md`, `docs/architecture/changes/DL247-ci-watch-give-up.md`.

## Tests
- `test_dl247_ci_watch_give_up`, `test_dl235_ci_watch_quota`, `test_dl226_agent_ci_path_ci_watch`, `test_dl183_rerun_first_pending`, `test_dl127_ci_watch_ledger`: pass.
- `python3 tools/test_delivery_ci.py --no-mutants`: 78 passed, 0 failed.
- `tools/test_delivery_fallback_launch.py WatchHook`: pass.
- `docs_check.py`: only G1 (generated decisions.md) and W1 (docs/work) remain; M1 is cleared by the `Docs:` line in the commit.

## CI (spec-lint, areas=delivery)
- Run 43092982673: failed. docs check (G1, W1 only); delivery CI scripts job failed on the fallback watch-hook test (needed the `resolve_repo` stub; fixed in the next commit). All other delivery jobs success.
- Run 43093482207 (after fix): cancelled by something else; docs check failed on G1/W1 only; jobs that ran to the end succeeded; others cancelled.
- Run 43093883037 (re-dispatched once): cancelled after 20 s, all jobs cancelled.
- Run 43094012882 (dispatched a third time): cancelled again; setup preflight, change notes, area mapping, train cleanup, runner plan success; CI scripts, pruning, branch gate, smoke, ledger/watcher cancelled.
No run completed after the fix, so the full delivery area is unproven in CI.

## Follow-ups
- Find what cancels the dispatched runs (not the workflow's own concurrency: it only cancels pull_request runs).
- Dispatch spec-lint again on this branch and confirm the delivery jobs end green.

Branch head: see `git rev-parse origin/DL247-ci-watch-give-up` (the report commit follows the last code commit).

NOT READY
