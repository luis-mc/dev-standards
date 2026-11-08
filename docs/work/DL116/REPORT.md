# DL116 report: DL-94 uncached download check

DL-94 was free (last was DL-93), so it is DL-94.

## What changed
- New `claude/plugins/delivery/templates/shared/scripts/delivery/workflow_fetch_check.py` (standard library).
- `hook_pre_tool.py`: `check_workflow_fetch` (DL-94), wired for Write, Edit and MultiEdit. It loads the checker by path from the plugin's own `templates/shared/scripts/delivery/` (one copy, no drift). Any internal error fails open. `checks_off` may list `DL-94`.
- Rule line added to `claude/plugins/project-setup/skills/claude-setup/assets/.claude/rules/agents-and-integration.md` (the file holding the other `check: DL-nn` lines).
- DELIVERYSPEC.md: DL-94 row after DL-93. Notes: `docs/architecture/changes/DL116-uncached-download-check.md` and `-spec.md`.
- Tests: `claude/plugins/delivery/tests/test_dl116_fetch_check.py` (15 tests).

## Exact behaviour (for the feature spec)
- `workflow_fetch_check.py [FILES...]`; default `.github/workflows/*.yml` and `*.yaml`. Only `run:` blocks are read (inline or `|`/`>` blocks; `\` and backtick continuations joined).
- A command is a download when it uses curl, wget, Invoke-WebRequest, iwr or urllib, on a URL containing `/releases/download/` or ending in .zip .tar.gz .tgz .exe .msi .xz (query/fragment allowed).
- Flagged when the step: has no `ci_tool.py` use; or the command writes into `$RUNNER_TEMP`, `${RUNNER_TEMP}`, `$env:RUNNER_TEMP`, `%RUNNER_TEMP%` or `${{ runner.temp }}`; or no sha256 check is in the step (`sha256sum`, `shasum -a 256`, `Get-FileHash`, `--sha256`, certutil sha256). A command that itself names `ci_tool.py` passes.
- Opt out: trailing `# ci-tool: ok <reason>`. `# ci-tool: ok` with no reason is a finding (`"# ci-tool: ok" needs a reason ...`).
- Output per finding: `<file>:<line>: DL-94 <what> (python3 scripts/delivery/ci_tool.py fetch <url> --sha256 <hex> --name <tool>/<version>/<file>)`; `<what>` joins the problems with `; `: `download not through ci_tool.py`, `writes into RUNNER_TEMP, which is wiped every job`, `no sha256 check`.
- Exit: 0 clean, 1 findings, 2 usage (unknown option or unreadable file).
- Hook: on Write (content), Edit (new_string) or MultiEdit (each new_string) of `.github/workflows/*.yml|yaml`, denies with `DL-94 <findings, up to 5, joined by " | "> Fetch pinned tools through the per-runner cache: python3 scripts/delivery/ci_tool.py fetch <url> --sha256 <hex> --name <tool>/<version>/<file>. A reviewed exception ends the line with "# ci-tool: ok <reason>".` Other files are never checked. Edit checks only the new fragment, so its line number is relative to the fragment.

## For the orchestrator (not mine to edit)
- `hooks/hooks.json` PreToolUse matcher is `Bash|PowerShell|Agent|Workflow|RemoteTrigger|AskUserQuestion|Write`. Add `Edit|MultiEdit` so DL-94 sees them; the code is ready. Write works today.
- Feature spec text (docs/features/delivery) is yours; docs_check M1 errors on the feature specs are expected until then. The G1 stale `decisions.md` error is generated and untouched.
- Today's ci.yml templates are expected to be flagged until the ci_tool.py branch lands (not edited).

## Tests
- `cd claude/plugins/delivery/tests && python3 test_dl116_fetch_check.py`: 15 OK.
- `python3 -m unittest test_pre_tool test_dl96_cloud_create`: 37 OK.
- `tools/test_delivery_hooks.py` and `tools/test_rule_tags.py`: refused locally by session_guard (heavy suites); left to CI.
- `python3 tools/ci_areas.py --branch-advice`: `gh workflow run spec-lint.yml --ref DL116-uncached-download-check -f areas=specs,delivery,profiles` (not run here).
- `docs_check.py`: 5 errors (4 M1 feature-spec, 1 G1 generated), as above.
- No mutation, no Docker.

Branch head SHA: the tip of origin/DL116-uncached-download-check (`git rev-parse origin/DL116-uncached-download-check`).

READY
