# DL33 report: setup clarity

## Files changed
- Skills: claude-setup, docs-setup, design-system-setup, tech-stack-setup, auth-setup (SKILL.md each). Added a setup pattern section or step text to each. Nothing removed.
- Tests: tools/test_setup_pattern.py (new, checks all five skills), tools/test_claude_setup_plugins.py (checks claude-setup and calls the new test, so CI runs it with no workflow change).
- Docs: docs/guides/setup-skills.md (new, mermaid flow per setup, what you can do after), small paragraphs in docs/features/project-setup/spec.md and docs/features/docs/spec.md (project-setup spec `code:` now lists the two tests).
- Notes: docs/features/project-setup/changes/DL33.md, docs/features/docs/changes/DL33.md (docs_fold.py note), docs/architecture/changes/DL33-setup-clarity.md and DL33-setup-clarity-docs.md.

## Decisions the brief did not settle
- Plugin change notes: a note names one plugin only, so there are two files (project-setup, docs) instead of one.
- The new test is called from test_claude_setup_plugins.py, because registering a new suite means editing files I do not own (.claude/suites.json, ci_areas.py, spec-lint.yml).
- Detection in tests is case-insensitive for the phrases "plan first", "one line per step", "safe to run again", and exact for the three bold headings.
- The by-hand lists now run after a yes: docs.json edit (docs-setup), CONFIG and test runner edit (design-system-setup), plugin install commands (claude-setup).
- No UI change.

## Ran
- python3 tools/test_claude_setup_plugins.py: 8 plugins, 0 problems; test_setup_pattern: 5 skills, 0 problems.
- docs plugin unit tests (unittest discover): 132 OK.
- change_notes.py check: ok.
- docs_check.py: only W1 (docs/work, by design on this branch) and T2 freshness warnings. Generated files reverted.

READY
