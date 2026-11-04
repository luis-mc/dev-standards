# DL30 report (agent B, runner pool and setup)

Branch: DL30-runner-pool. Status: READY (see the end).

## Files changed
- New: `claude/plugins/delivery/templates/runner-pool/` (Dockerfile, compose.yaml, pool_supervisor.py, pool_agents.py, pool-add-agent, pool-remove-agent, hooks/job-started.sh, hooks/job-completed.sh, pool-check.yml)
- New: `claude/plugins/delivery/scripts/delivery_runner_pool.py`
- Changed: `scripts/delivery_ci_setup.py` (actions pool-detect, pool-plan, pool-run; render_plan, render_summary, can_do_now), `commands/delivery-ci-setup.md` (section 3a), `README.md` (own subsection)
- New tests: `tests/test_runner_pool.py` (42 tests)
- Docs: `docs/features/delivery/shared-self-hosted-runners.md` (rewritten for readers, three mermaid diagrams, contract kept under "How it is built" with the original section numbers), `docs/guides/set-up-ci.md`, `docs/overview/apps.md` (link), notes `docs/architecture/changes/DL30-runner-pool.md` and `docs/features/delivery/changes/DL30.md`

## Decisions the contract did not settle
- The add and remove agent commands are thin wrappers over `pool_agents.py` so tests can import them. They need `--private` (the setup checks privacy first); without it they refuse.
- The runner SHA-256 comes from the release asset digest, else the release notes. The build fails without it. It reaches compose as the env var RUNNER_SHA256 (not in `.env`, which holds the cap only, D42).
- The shared database admin password is a 0600 file `db-admin.pw` used as a compose secret. Each repository's own login password goes only to a 0600 `db.env` in its agent folder.
- `config.sh --token` puts the token on the command line inside the container for a moment. The runner has no stdin option.
- `detect(json=True)` returns a JSON string. `doctor_checks(root)` takes a machine folder that holds `pools/`, else the machine dir from `machine_slots.machine_dir()`.
- The setup deletes nothing by itself: a deletion step needs `--yes-delete` naming the exact path or container.
- Removing an old runner uses `DELETE /repos/{o}/{r}/actions/runners/{id}` (no token). `wsl --shutdown` is never run by the setup; it prints that the owner does it.
- Stopping and deleting an old Windows service is not automated; old runner folders and containers are deleted after their own yes. The by-hand path covers services (needs an administrator shell).
- Agent A's helpers are imported in a try (`machine_slots`). Without them the machine-config step fails with a clear reason.

## What I ran
- `python3 -I -m unittest discover -s claude/plugins/delivery/tests -t claude/plugins/delivery/tests`: 437 tests, OK (42 new).
- `python3 tools/ci_areas.py --branch-advice`: heavy delivery area; not run (CI job, per the rules).
- `docs_index.py build` then `docs_check.py`: one error, W1 (this report, expected on a task branch). Two warnings: M1 says the delivery README is not mapped by any spec `code:` list (the spec belongs to agent A), and T2 says the delivery spec is older than its code. Generated files were restored with git checkout.
- Not run: Docker, mutation passes, any real gh or machine step.

No UI change.

READY
