# DS296 report

Branch: DS296-cloud-bootstrap (from origin/DS287-integration).

## Files
- `claude/plugins/delivery/templates/shared/scripts/delivery/cloud_setup.sh` (new; installs with the other scripts/delivery files, no list to edit; added to CONTRACT.md table)
- `claude/plugins/delivery/scripts/hook_cloud_setup.py` (new SessionStart hook) and `hooks/hooks.json` entry
- `claude/plugins/delivery/scripts/ds_scripts.py` (new resolver)
- `claude/plugins/delivery/references/agent-brief-template.md` (cloud rules line)
- `claude/plugins/delivery/tests/test_ds296_cloud_setup.py` (16 tests)
- Docs: `docs/features/delivery/spec.md` (R5.95 to R5.97), `docs/features/delivery/changes/DS296.md`, `docs/architecture/changes/DS296-cloud-bootstrap.md`

## Tests (no network, no Docker)
- test_ds296_cloud_setup.py: 16 pass
- test_brief_template.py: 8 pass
- installer tests (dl112, dl120, dl150, dl201, dl204, dl218, dl227, dl236, dl385): pass
- docs_check.py: 0 errors, 0 warnings

## Contract points and notes
- Pin: the repo and ref come from `.github/workflows/dev-standards.yml`; the gitleaks version and SHA-256 come from `scripts/delivery/tools.json`, the file every ci.yml and agent_setup.sh already read. No second pin.
- (c) The delivery ci.yml templates have no pip or requirements step. The script installs the first of requirements-dev.txt, requirements-ci.txt, requirements-test.txt, requirements.txt that exists. This is a judgment call: confirm it matches what projects use.
- The hook runs as a second SessionStart entry (timeout 170 s) so it cannot disturb the ledger hook.
- The brief says "as a draft" for `gh pr create`, to match AGENTS.md (no ready PR by agents). Change if D322 means otherwise.
- Not run: the real gitleaks download and real GitHub fetch (tests use local fakes).
