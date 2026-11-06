# DL86 report

- Dockerfile: ARG GH_VERSION=2.103.3, GH_SHA256 (64 hex); gh tarball downloaded, `sha256sum -c`, installed to /usr/local/bin/gh (0755), tarball and folder removed in one RUN. Placed before the runner step, outside POOL_BROWSERS.
- pool-check.yml: gh added to the tool loop; prints first line of `gh --version`.
- Spec: shared-self-hosted-runners.md step 8 tools sentence now lists gh (pinned tarball, SHA-256).
- Tests: new class DL86GhTests (2 tests) in test_runner_pool.py.
- Notes: docs/architecture/changes/DL86-delivery.md; docs/features/delivery/changes/DL86.md (docs_fold note).

## Commands
- `cd claude/plugins/delivery/tests && python3 -m unittest test_runner_pool`: 145 tests, OK.
- `python3 tools/ci_areas.py --branch-advice`: "unreadable diff, treat as every area" (run before any commit). It advises `gh workflow run spec-lint.yml --ref DL86-pool-gh -f areas=...`. Not run here (heavy; no gh CLI auth for workflows).
- `python3 claude/plugins/docs/scripts/docs_check.py`: only G1 (decisions.md stale, expected on a branch). No other findings.

Branch head SHA: see the last commit on DL86-pool-gh.

READY
