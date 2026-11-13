# DL323 report: pool agents per repo

## Files
- `claude/plugins/delivery/templates/runner-pool/pool_agents.py`: `labels_for(..., route=)`, `route_of`, `next_slug`, `add_agent(..., route=)`, `--route` option. Entry stores `route` only when it differs from the slug.
- `claude/plugins/delivery/templates/runner-pool/pool-add-agent`: unchanged; it passes `"$@"`, so `--route` works.
- `claude/plugins/delivery/templates/runner-pool/pool_supervisor.py`: unchanged. It never reads labels or route; it runs one agent per entry, per slug.
- `claude/plugins/delivery/tests/test_dl323_pool_agents_per_repo.py` (9 tests).
- `docs/architecture/changes/DL323-pool-agents-per-repo.md` (plugin, minor).

## Behaviour
- `--route <slug>` sets the label `repo-<slug>`.
- No `--route`, new slug, and another entry has the same repo: the route is that entry's route and the slug becomes `<route>-N` (next free N from 2). The given slug is replaced; the output says `added: <route>-N`.
- A rerun with an existing slug keeps the old path.
- User, folder, TMPDIR, db login and roles stay per slug. `remove_agent` removes one slug only.

## Tests
- `cd claude/plugins/delivery/tests && python -m unittest test_dl323_pool_agents_per_repo test_dl231_pool_db_roles test_pool_supervisor test_dl92_pool_fixes test_runner_pool`: 202 tests, OK.
- `python tools/ci_areas.py --branch-advice`: "unreadable diff, treat as every area" (no local diff base); not run.
- `docs_check.py`: not run (`<luismc-docs>` not available here).

## Spec text
Add to `docs/features/runner-pool/spec.md` after the last R5.x (IDs to be numbered by the spec owner):
- **R5.n** Several agents may serve one repository. Every agent of a repository carries the routing label `repo-<route>`, so one `CI_RUNS_ON` matches all of them. `route` defaults to the agent's slug.
- **R5.n+1** `pool-add-agent --route <slug>` sets the route. Without it, a new agent for a repository that another entry serves reuses that entry's route and is named `<route>-2`, `-3`, and so on.
- **R5.n+2** `agents.json` stores `route`. An entry without `route` routes by its slug.
- **R5.n+3** User, folder, TMPDIR, Wine prefix and database roles stay per slug. Removing one agent leaves the others of that repository working. The pool memory and CPU cap and the machine slot limit do not change.
- Test rows: second agent gets `<route>-2` and `repo-<route>`; `agents.json` keeps both; old entry unchanged; remove keeps the other (`test_dl323_pool_agents_per_repo.py`).

## Needs
No setup change. The pool image files changed, so a running pool has the old `pool_agents.py`. To add the second agent without a rebuild, copy the file in, then add:
```
docker cp claude/plugins/delivery/templates/runner-pool/pool_agents.py POOL:/opt/pool/pool_agents.py
gh api -X POST repos/OWNER/REPO/actions/runners/registration-token --jq .token \
  | docker exec -i POOL pool-add-agent SLUG OWNER/REPO --private --route EXISTING_SLUG
```
(or omit `--route` to get `<route>-2`). The copy is lost on a container recreate until the image is rebuilt. The supervisor picks up the new `agents.json` entry as it does for any add; it needs no change.

Branch head SHA: the commit before this report update is a7718529defa069aab07928ac1908e98d97d9135.

READY
