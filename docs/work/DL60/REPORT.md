# DL60 report: runner pool on Windows

Branch: DL60-runner-pool-windows

## Bugs and fixes
1. Runner SHA: `runner_sha()` first reads `<!-- BEGIN SHA linux-x64 -->HEX<!-- END SHA linux-x64 -->`, else `name.{0,80}?HEX`. Test: `dl60_runner_sha_reads_the_marked_release_note` (exact release line).
2. CPU headroom: `sizing()` sets wsl processors to floor(cpu)+1, capped at the host CPU count. If the cap would bite, pool cpu drops by 1 (min 1.0). `POOL_CPUS` (in `.env`) and `processors` both come from the one `sizing()` dict, so the plan and the step agree. Test: `dl60_processors_leave_headroom_over_the_pool_cpus` (all host sizes 1..64).
   - Memory 7GB vs 10GB: inside one run the plan and the `wslconfig` step share the same cap dict, so they cannot differ. They differ across runs: `pool-plan` and `pool-run` each measure again, and the result depends on used memory (host load) and on the existing `.wslconfig` memory (the Docker ceiling). A plan printed after a 7GB `.wslconfig` existed, and a later run measured with no ceiling or less load, gives 10GB. Not changed: the step already uses the plan's numbers. Run `pool-run` straight after `pool-plan` and give `--used-gib`/`--docker-gib` to pin them.
3. CRLF: `.gitattributes` line added; `write_pool_files()` now copies templates, hooks/ and delivery/*.py through `copy_lf()` (LF, mode kept). Test: `dl60_pool_files_are_written_with_lf`.
4. Runner folder permissions: add does `cp -a /opt/runner/. /agents/SLUG`, then chown -R, then runs `./config.sh` with cwd `/agents/SLUG` as r-SLUG; remove uses the same folder. `/opt/runner` stays pristine. The supervisor already ran `/agents/SLUG/run.sh` with that cwd, so it needed no change. Test: `dl60_each_agent_runs_in_its_own_copy_of_the_runner`.

## Tests
- New tests each fail before the fix (checked with the fix stashed): 4 FAIL, then 4 PASS after.
- `python3 tools/test_delivery_runner.py -k dl60`: all passed. The full file was not run: a local hook refuses this heavy suite; CI runs it.
- `python3 -m unittest test_runner_pool` (in claude/plugins/delivery/tests): 79 OK.
- `python3 tools/ci_areas.py --branch-advice`: "unreadable diff, treat as every area -> gh workflow run spec-lint.yml ..." Not run (heavy; left to CI).
- `python3 claude/plugins/docs/scripts/docs_check.py`: see the run output in the commit step.

## Docs
Change note added. No feature spec describes pool sizing or agent folders: `Docs: none` in the commit message.
READY
