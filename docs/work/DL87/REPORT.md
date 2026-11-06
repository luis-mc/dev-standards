# DL87 report

Branch DL87-pool-tmp. Code head: 13570e0 (report commit follows it).

## Changes
1. pool_agents.py: ensure_agent_tmp makes /agents/<slug>/tmp (0700, chown to r-<slug>) and adds only missing TMPDIR, TMP, TEMP lines to .env. add_agent and a rerun for an existing agent both call it.
2. pool_supervisor.py: same helper (duplicated, so the supervisor stays stand-alone) and prepare_tmp, run after ensure_user and before each runner starts.
3. job-started.sh and job-completed.sh: clean_tmp (guarded TMPDIR clean for /agents/*, then find /tmp -user "$(id -u)"), both with || true, before the unset and exec lines.
4. Spec: "Temp files" paragraph in shared-self-hosted-runners.md. Notes: docs/architecture/changes/DL87-delivery.md, docs/features/delivery/changes/DL87.md.
5. Tests: DL87AgentTmpTests, DL87HookTests (incl. real sh run of clean_tmp with symlink check), PrepareTmpTest.
   Deviation: one existing assertion in test_runner_pool.py (test_add_is_safe_to_repeat) now also allows chmod, because a rerun runs the temp-folder chown/chmod.

## Tests
- cd claude/plugins/delivery/tests && python3 -m unittest test_runner_pool test_pool_supervisor: 156 tests OK.
- python3 tools/ci_areas.py --branch-advice: "unreadable diff, run spec-lint.yml with areas=specs,delivery,artifacts,profiles,transcript-folds,docs" (needs gh; not run, no gh/CI here).
- docs_check.py: only G1 (decisions.md stale, expected on a branch). No W1 reported.

READY
