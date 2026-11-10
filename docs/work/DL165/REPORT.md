# DL165 / DL166 report

## What changed
- `delivery_runner_pool.py`: `judge_sha` and `sha_is_bad` (R13.86). A hash that is not 64 hex, or is one repeated character, is wrong. Pinned version: the pinned hash wins. Other version: the released hash; an unreadable release keeps the value and adds a plan note. `do_pool_up` uses the same judgement. New doctor check `pool.<name>.runner-sha` in `doctor_checks`; `delivery_doctor.py` already lists those checks, so it needed no edit.
- `delivery_runner_pool.py`: `image_ids` reads container id, container image and tagged image before and after the build (R13.87). The result is `image rebuilt`, `container recreated` or `image unchanged (cache hit)`. Force-recreate runs only when the container still runs an older image than the tag. A failed build says the old container keeps running.
- `delivery_ci_setup.py`: the plan line shows the short old and pinned hash and the reason. A failed build already returned 1 through `refresh()`; a test now covers exit code 1.
- Spec R13.86 and R13.87, change note, feature note `docs/features/delivery/changes/DL165.md`.
- `test_dl103_pool_keep_cap.py`: one fixture moved from `'c'*64` to the pinned hash (a repeated hash is now wrong).

## Which test reached the real machine folder
None could be found. I ran the whole delivery suite (1081 tests) with `DELIVERY_MACHINE_DIR` set to an absent decoy folder. Nothing was created there, and nothing under `/etc/luismc-delivery`. The likely cause is `_helpers.py`, which uses `os.environ.setdefault("DELIVERY_MACHINE_DIR", ...)`: when the variable already points at the real folder, tests use it. `_helpers.py` is not in my owns list, so I left it. Suggest plain assignment there. The guard test `GuardTests` runs the refresh path with the variable unset and the default patched to a temp path. It asserts the real default is never opened for writing.

## Tests
- `python3 -m unittest test_dl165_pool_refresh_hash_result` (in tests/): 15 tests OK.
- `test_dl162_pool_refresh_files`, `test_runner_pool`, `test_dl92_pool_fixes`, `test_machine`, `test_dl103_pool_keep_cap`: OK.
- Full delivery suite: 1081 tests; the one failure (dl103 fixture) was fixed as above.
- `docs_check.py`: G1 (`docs/architecture/decisions.md` stale) fails the same way on a clean origin/main. It is a generated file; I did not commit it.
- spec-lint run 42775351847 (areas=delivery): all delivery jobs success (train cleanup, setup preflight, CI scripts and templates, area mapping, branch gate, runner plan, ledger/hooks, change notes, packaged smoke, artifact pruning, scripts summary). Skipped: change-notes folded, change notes, shard job, specs/AUTHSPEC, transcript folds, model profiles, docs plugin, artifact renderer. Failed: `docs check` on G1 only (pre-existing, see above).

READY
