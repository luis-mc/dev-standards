# DS185 report: project-setup fixes (F14 to F30)

Method (D90): a failing test first for each finding, in `tools/test_project_setup_fixes.py` (run from `tools/test_claude_setup_plugins.py`). All 16 reproduced findings failed on current main and pass now.

| Finding | Result | Evidence / fix |
| --- | --- | --- |
| F14 | fixed | Stop and drift hook commands (template, SKILL.md project and user form) use `if command -v python3 ...; else python ...; fi`. SKILL.md says to replace the old form. |
| F15 | fixed | pre-commit reads names one per line with `core.quotePath=false`; `my config.env` and `café.env` with a token now block. |
| F16 | fixed | tech-stack-setup SKILL.md lists `pre-commit`, runs `chmod +x` and then `git update-index --chmod=+x`. Test checks the text (the fault was instruction text). |
| F17 | fixed | "No open questions" and a bare "parked" pass; "questions are parked" and "I have open questions" still block. |
| F18 | fixed | A list blocks only when the line above it reads as an offer to pick ("Pick one:", a question, "Options:"). "Files changed:" passes. |
| F19 | fixed | `--diff-filter=ACMR`; a renamed and edited file with a secret blocks. |
| F20 | fixed | preflight accepts pnpm-workspace.yaml, go.work, go.mod, Cargo.toml, *.sln, *.slnx; also crates/ and src/ count as roots. auth-setup text updated. |
| F21 | fixed | auth-setup uses `${CLAUDE_PLUGIN_ROOT}/skills/tech-stack-setup/assets/preflight.py` in step 0 and Mode 2 step 1. |
| F22 | fixed | check_stack iterates list values, validates every role id, and checks the api_framework track against the language. All nine catalog bundles still pass. |
| F23 | fixed | `blazor_server` in hosting.yaml; `--catalog` now checks conflict ids. |
| F24 | fixed | `{{DEFAULT_BRANCH}}` placeholder in the CI template and SKILL.md (read with `gh repo view`). |
| F25 | fixed | Design guard step picks pnpm, yarn or npm from the lockfile. |
| F26 | not reproduced | Only bash 5.2 is here; no bash 3.2 to run it on. No change made. Needs a macOS check. |
| F27 | fixed | commit-msg parses JSON with python when present and reads only the top-level key; grep fallback otherwise. |
| F28 | fixed | claude-setup SKILL.md adds an LF rule (`.claude/*.sh text eol=lf`) to `.gitattributes` for a project target. |
| F29 | fixed | Template `enforcement.mode` is `warn`; SKILL.md writes `block` only on "Block now". |
| F30 | fixed (behaviour proven, field meaning from docs) | Old script printed `1500k/200k` for the cumulative field. It now sums `current_usage` tokens, else used_percentage x window size. Field meaning is not checked against live Claude Code. |

## Other changes
- `tools/ci_areas.py`: the profiles path map line now includes `test_project_setup_fixes.py`.
- Spec `docs/features/project-setup/spec.md`: hook text and test in `code:`; note `docs/features/project-setup/changes/DS185.md`; change note `docs/architecture/changes/DS185-project-setup-fixes.md`.
- Not touched by me: `docs/features/models/spec.md` and `docs/features/test-cost/spec.md` map to files I changed (settings.json template, ci_areas.py). docs_check M1 wants a note or a commit line; the commit message says `Docs: none`.

## Tests run
- test_project_setup_fixes.py: 0 problems (16 checks).
- claude-setup-plugins, setup-pattern, questions-stop, preflight, ci-areas, change-notes, spec-check, authspec-check (via run_suite --measure): all passed.
- docs_check.py: remaining errors are the stale generated docs-map (G1, not committed), M1 for models and test-cost (see above), and W1 for this report (stays on the branch). No Docker, no mutation passes.

Branch head: see the last commit on origin/DS185-project-setup-fixes.

READY
