# DL63 report

Code commit: c8701a2cafc7b7262e2b31f379f2c7f808f28bbe (branch DL63-runner-pool-fixes).

## What changed
1. **Host-load check.** `default_check` tries `schtasks /Query` first. If it does not return 0 (access denied), it reads the host-load file through `Probe.host_load()` and passes when the age is under 60 s. Stale or missing file = not done.
2. **Runner version.** `MIN_RUNNER_VERSION = 2.329.0`; pinned fallback `2.338.2` with its sha256. `resolve_runner` reads `releases/latest` and the linux-x64 digest; the pool-files step writes `RUNNER_VERSION` to the pool `.env`. `pool-up` refuses a version below the floor and passes version and sha to compose. `runner_sha` falls back to the pinned sha for the pinned version. Dockerfile ARG and compose default are 2.338.2.
3. **create_db / add_agent.** Role and database are two separate psql calls (role first), each idempotent (existing role gets the new password so db.env stays valid). `add_agent` skips `config.sh` when the folder has `.runner`.
4. **Memory cap.** "Used" leaves out the WSL VM (vmmem/vmmemWSL), or the pool's containers when there is no VM. Other containers in WSL are read with `docker ps/stats`; the pool leaves them room and `.wslconfig` memory is never written below its current value or below their use plus the pool cap. Step text shows old -> new for memory, processors, POOL_MEM, POOL_CPUS; the .bak stays.
5. Labels: docs already match `labels_for`; no change.

Docs: spec text in shared-self-hosted-runners.md, change note docs/architecture/changes/DL63-delivery.md, feature note docs/features/delivery/changes/DL63.md.

## Commands
- `cd claude/plugins/delivery/tests && python3 -m unittest test_runner_pool test_load`: 146 tests, OK.
- `python3 tools/ci_areas.py --branch-advice`: "unreadable diff, treat as every area -> gh workflow run spec-lint.yml ..." Not run (needs gh and CI; not light).
- `python3 claude/plugins/docs/scripts/docs_check.py`: 0 errors, 1 warning: T2 docs/features/test-cost/spec.md (code changed after the doc; not a file I own).

NOTE: the code commit SHA is above; the report commit follows it.

READY
