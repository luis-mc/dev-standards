# DL414 report

Q-4 no longer blocks on a green train with no `pr` and no `release_no`. An unnumbered train that does block is named by ledger id, with the close command.

## Callers of trains_green_unmerged
- `hook_pre_tool.py` Q-4: filtered here (needs a PR or a release number).
- `hook_stop.py` check_trains: left unchanged. It already sorts a no-PR train into its own "needs a PR" list, which is a different rule and not the same bug.

So the filter is in the Q-4 block, not in `trains_green_unmerged`.

## Files changed
- claude/plugins/delivery/scripts/hook_pre_tool.py (Q-4 block)
- claude/plugins/delivery/scripts/hooklib.py (`stale_hint`)
- tools/test_delivery_hooks.py (`q4_stale_and_unnumbered_trains`)
- docs/architecture/DELIVERYSPEC.md (Q-4 line)
- docs/architecture/changes/DELIVERYSPEC/DL414.md, docs/features/delivery/changes/DL414.md (change notes, name plugin.json)

## Tests
- Named cases `q4_stale_and_unnumbered_trains`, `q4_actionable_now_denies_dialog`, `dl03_green_unmerged_blocks_and_hold_allows`: pass. The full suite is heavy, so it is left to CI. `run_suite.py` cannot run named cases for delivery-hooks, so I imported the module and called the cases.
- `docs_check.py`: one M1 error left, for `docs/features/delivery-speed/spec.md`, because the test file changed. The commit message carries `Docs: none, test-only change for that feature`.

Close command used in the message: `delivery_ledger.py close <id> --reason "stale"`. Use `close-stale --before DATE` for many entries.

Branch head SHA: see the last commit on DL414-q4-stale-entries.

CODE DONE
