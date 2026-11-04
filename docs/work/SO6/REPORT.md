# SO6 report

No UI change.

## Files changed
- New: `claude/plugins/project-setup/skills/claude-setup/assets/.claude/hooks/questions_stop.py` (Stop hook, stdlib only).
- `assets/.claude/settings.json`: Stop hook entry (user form, `$HOME`). SKILL.md drops it for a project target.
- `SKILL.md`: new section "The questions Stop hook" (plan, copy script, append to `hooks.Stop`, flow chart, off switch), verify and report lines.
- Both `clarifying-questions.md` files (claude-setup asset and delivery rule): Q-1 and Q-2 tags now name the hook path.
- New `tools/test_questions_stop.py`; registered in `.claude/suites.json` and `tools/ci_areas.py` (profiles area).
- Docs: `docs/features/project-setup/spec.md` (R5.13, mermaid, proof row, code map); change notes `docs/features/project-setup/changes/SO6.md`, `docs/features/models/changes/SO6.md`, `docs/architecture/changes/SO6-questions-stop-hook.md` (project-setup plugin.json, minor), `docs/architecture/changes/SO6-questions-rule-tags.md` (delivery plugin.json, patch, because the delivery rule file changed).

## Decisions
- Off switch: env `CLAUDE_QUESTIONS_STOP=off` (shell or settings `env`) or `"questionsStop": "off"` in `~/.claude/settings.json`.
- Any AskUserQuestion call in the turn allows the stop (low false positives).
- Q-5 park exception only for point 2; a plain question at the end still blocks while agents run.
- "Addressed to the owner": last line ends with `?` and the paragraph has second person or an ask-leave phrase.
- The tag path replaces `Q-1`/`Q-2` ids in both rule files (the rule tag test allows one tag per line).
- There is no separate claude-setup feature page; the project-setup spec is the page.

## Ran (all passed)
`run_suite.py --measure` for questions-stop (0 problems), claude-setup-plugins, setup-pattern, rule-tags (71 tagged), ci-areas, model-profiles. The session guard required one measure run per new or heavy suite. No mutation passes, no Docker.

## For the owner
- `.github/workflows/spec-lint.yml` has no step for `tools/test_questions_stop.py` (not mine to edit). Add one beside the claude-setup-plugins step.
- `docs_check`: G1 (docs-map.json stale, generated, not committed) and W1 (this report, stripped before the join) remain.
- The commit footer follows the brief (Opus 5.5 line).

READY
