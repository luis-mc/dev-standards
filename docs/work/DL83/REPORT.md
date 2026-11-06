# DL83 report

## Changes
1. Supervisor: `per_agent_parallel` and `Supervisor.agent_env`. Each agent starts with a env copy where CI_MAX_PARALLEL = max(1, POOL_CPUS_INT or CI_MAX_PARALLEL // agents in agents.json). One log line per agent start. A restart after a change in agents.json uses the new count. `popen_spawn` takes env; the injectable spawn style is kept.
2. Doctor: new `mem-per-agent` check, warns under 4 GiB per agent, names POOL_MEM, the agent count and the fix.
3. Spec: Job hint row in docs/features/delivery/shared-self-hosted-runners.md. Notes: docs/architecture/changes/DL83-delivery.md, docs/features/delivery/changes/DL83.md.
4. Tests: 5/2 -> 2, 5/1 -> 5, 1/3 -> 1, spawned env value, doctor warn at 8 GiB with 3 agents and ok with 1.

## Commands
- `cd claude/plugins/delivery/tests && python3 -m unittest test_pool_supervisor test_runner_pool`: 143 tests OK.
- `python3 claude/plugins/docs/scripts/docs_check.py`: 0 errors, 0 warnings.
- `python3 tools/ci_areas.py --branch-advice`: "unreadable diff", advises a heavy `gh workflow run spec-lint.yml`; not run (not light, no gh here).

- Branch head: see the commit after this one (code head 2242f5d3a00e91d68634a1299dec7eb2d18a8991).

READY
