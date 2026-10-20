# DS72 report: Stop hook loop

Status: done, draft PR open. Branch DS72-stop-hook-loop. The plugin version is not bumped; the change note is folded on the integration branch.

## Cause
The Stop hook (DL-14, DL-18) read `cleaned_at` and `smoke.state`, which the project scripts it named never wrote, and the
existing per-session ceiling (`block_ceiling`) restarts whenever the *set* of findings changes (any DL-31 wording finding
changes the fingerprint), so the session was blocked every turn.

## What each piece does
1. **`delivery_ledger.py smoke --pr N [--run id|url]`**: with `gh`, finds the newest `smoke_workflow` run (default `Production smoke`)
   on the PR's merge commit. Success records `smoke {state: pass, at, run}` and `live_at` (state `live` when it was before live) on
   every row with that pr; failure records `fail`, exit 1; missing or unfinished records nothing, exit 1 with a plain message.
2. **`delivery_ledger.py cleaned --pr N`**: `git ls-remote --heads origin` for the train branch and cargo branches, and
   `git worktree list --porcelain` for worktrees holding them. Anything present is listed and nothing recorded (exit 1); otherwise
   `cleaned_at` and state `cleaned` on every row with that pr. Both go through `update()` (ledger lock), add an event
   (`smoke.pass|fail`, `cleaned`), and touch no CI field.
3. **Messages**: DL-14 / DL-18 name `cleanup_command` / `smoke_command` (with `{pr}`) when configured, then
   `python <abs plugin>/scripts/delivery_ledger.py cleaned|smoke --pr N`.
4. **Loop limit** (`stop_repeat_limit`, default 3, 0 = never): `hook-state.json` (`repeat:<session>`) keeps per finding a fingerprint of
   its key and the train/agent row fields it depends on. After 3 blocked turn ends with no change, the 4th and later are not blocked for it;
   one `systemMessage` per session says it is still open and names the command. A field change or a new finding blocks again.
   Applied to every rule; README lists the ones it matters for. The old `block_ceiling` is unchanged.
5. Docs: plugin README, DELIVERYSPEC (DL-14, DL-18, section 6), config-schema.json, change note `docs/specs/changes/DS72-stop-hook-loop.md`.

## Tests
`claude/plugins/delivery/tests`: `python3 -m unittest discover -s .` -> 150 tests OK (new file `test_recording.py`: smoke
success/failure/missing/unfinished with a stubbed gh, duplicates, explicit run, configured workflow; cleaned present/gone/git failure;
messages with and without configured commands; loop limit 3 blocks, notice once, silence, field change, new finding, limit 0,
separate sessions; end-to-end `main()`).

## Gate (one affected gate)
- delivery plugin tests: 150 OK.
- `change_notes.py check --config tools/change-notes.json`: ok. **`tools/test_change_notes.py` was NOT run**: the repo's session guard refuses the full
  heavy suite locally ("run named cases ... leave the full run to CI"); nothing in this change touches the change-notes tool. Run it in CI.
- `tools/spec_check.py` (spec lint): 0 errors, 0 warnings. Config validate with the new keys (`--strict`): ok.
- Secret scan: gitleaks 8.30.1 (pinned sha) over the branch commits: no leaks.
- No Docker, no full suite.

## Back-fill for comics-organizer (after the update is installed)
From the repo root, with `gh` signed in and the three branches/worktrees removed:
```
python <plugin>/scripts/delivery_ledger.py cleaned --pr 482
python <plugin>/scripts/delivery_ledger.py smoke --pr 482
python <plugin>/scripts/delivery_ledger.py cleaned --pr 486
python <plugin>/scripts/delivery_ledger.py smoke --pr 486
python <plugin>/scripts/delivery_ledger.py cleaned --pr 489
python <plugin>/scripts/delivery_ledger.py smoke --pr 489
```
`<plugin>` is the installed luismc-delivery folder (the hook message prints the absolute path). If `smoke` finds no run on a merge
commit, pass the run: `smoke --pr N --run <id|url>`. If `cleaned` lists leftovers, delete them first (cleanup.py --pr N).
