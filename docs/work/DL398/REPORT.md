# DL398 report

## Where the advice came from
Not from this repository. Searched claude/plugins for noreply, Co-Authored-By, author, amend, re-author, attribution. The only hits are DL-74 enforcement: `hook_pre_tool.py` check_attribution (denies attribution when `no_attribution` is true), the `commit-msg` template (rejects AI Co-Authored-By when `no_attribution` is true), config schema, and docs. `hook_stop.py` has no author, amend or attribution text. No delivery hook tells an agent to add attribution or amend authors. The text came from the hosting platform's own Stop hook.

## Fix
- `delivery_doctor.py`: the `hooks` row adds a note when `no_attribution` is true: no delivery hook advises this, and the project rule wins over a platform hook.
- `test_doctor.py`: true -> note present; false -> absent (unchanged).
- DELIVERYSPEC DL-74 row text; change notes `docs/architecture/changes/DL398-no-attribution-doctor-note.md` and `docs/features/delivery/changes/DL398.md`.

## Checks
- `cd claude/plugins/delivery/tests && python3 -m unittest test_doctor test_pre_tool test_stop`: 81 tests OK
- `python3 claude/plugins/docs/scripts/docs_check.py`: 0 errors, 0 warnings

Branch head SHA: see `git rev-parse DL398-no-attribution-hook` (the commit that holds this file).

READY
