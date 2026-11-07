# DL105 report

## What changed
- Gate text (D119): `branch_gate.py` prints two causes for a failed setup (stale lockfile, install killed for memory). Exit code 137 puts the memory sentence first. `gate_verify.py`, `CONTRACT.md`, the DL-23 deny texts in `hook_pre_tool.py` and the DL-23 rule line in project-setup say the same. Never-install-unfrozen is unchanged. No DL-23 line exists under `delivery/rules`.
- Floor-bound fixtures (D120): lowering the floor to 0 changed no test. Raising it to 8/4 broke two: `SizingTests.test_docker_ceiling_wins_when_smaller` and `DL63SizingTests.test_pool_cap_leaves_room_for_other_containers` (their results sit between the 4 and 8 GiB floors). Both now patch `MIN_POOL_GIB` to 0 so they test their subject.
- Windows (D121): mode asserts guarded by `os.name != "nt"` (4 tests plus the supervisor one); symlink test skips on OSError; `ensure_user` in `templates/runner-pool/pool_supervisor.py` uses `posixpath.join`.
- Doctor tests on Windows: cause is the fixture, not the code. `FakeProbe` treated every path starting with `C:` as fake, and a real Windows temp folder starts with `C:`. So the probe hid `compose.yaml` and the doctor saw no pool. `FakeProbe` now fakes only `C:/Work` and `C:/Users/u1`. No change to `delivery_runner_pool.py`.
- Not run on Windows (cannot); reasoned from the code.

## Tests
- `python3 -m unittest` in `claude/plugins/delivery/tests`: test_runner_pool (149 OK), test_pool_supervisor (9 OK), test_dl92_pool_fixes (23 OK), test_dl103_pool_keep_cap (17 OK), test_pre_tool (31 OK), test_dl105_gate_text (2 OK).
- `run_suite.py delivery-gate setup`: 58 checks, 0 failed (the full gate suite is refused locally by the session guard).
- `docs_check.py`: G1 expected. M1 for delivery-speed, models, project-setup covered by `Docs: none` in the commit message.
- CI: `gh workflow run spec-lint.yml --ref DL105-gate-text-portable-tests -f areas=delivery` triggered (run 42387852687) and watched with `ci_watch.py`. The delivery branch gate job passed. The docs check job failed on G1 (stale decisions) and W1 (this report) only, both expected on a branch.

Branch head SHA: see `git rev-parse DL105-gate-text-portable-tests` (the commit before this report update was c41af574c20740a878e2d28ec9b1d7b2094ce116).

READY
