# DOC6 report: DOCSPEC pieces outside the luismc-docs plugin

Branch `claude/DOC6-docs-followups`, based on `claude/DOC2-luismc-docs` (PR #111). One draft PR.

Status: READY

## Changes
1. **join.py** (`claude/plugins/project-setup/skills/tech-stack-setup/assets/tooling/shared/scripts/delivery/join.py`; this is the copy generated into projects, it lives in luismc-project-setup, not in the delivery plugin). After the last merge it finds luismc-docs' `docs_work.py` (`$LUISMC_DOCS_WORK`, else the newest `~/.claude/plugins/cache/*/luismc-docs/*/scripts/`, else the marketplace checkout), runs `strip --apply`, commits "Strip temporary agent docs", and records each report summary in `join-result.json` (`docs_summaries`, `docs`) and `.delivery/docs-summaries.md` for the ready PR body. Plugin absent, nothing under `docs/work/`, or a failed strip: it says so and joins on. CONTRACT.md documents it.
2. **Agent brief template** (`claude/plugins/delivery/references/agent-brief-template.md`): a `docs:` key in the delivery block (paths, or `none, <reason>`), with the `Docs: none, <reason>` commit-line cross-reference. New guard `claude/plugins/delivery/tests/test_brief_template.py` (block keys and order, hook parser reads `docs`, R8.5 cited).
3. **STACKSPEC section 16** now points to DOCSPEC (layout, feature specs in `docs/features/<x>/spec.md`, archive, `docs/work/`, AGENTS.md) and no longer defines `docs/specs/` and `docs/notes/`; the line "Superseded versions move to `docs/notes/`" now says `docs/archive/`. **spec-new** (luismc-specs): a repo with `docs/docs.json` gets one-feature specs via `luismc-docs:feature-spec-new` (`docs/features/<x>/spec.md`) and cross-feature rules in `docs/architecture/<name>.md`; other repos keep `specs/`. Template step 1 updated.
4. **luismc-artifacts** `promote-to-spec KEY [--feature ID] [--apply]` (`scripts/artifact_promote.py`, `cmd_promote_to_spec`): feature page lede, sections and decided decisions to `docs/features/<ID>/spec.md` in the feature-spec template (front matter of R4.2); dry run by default; open decisions listed, not promoted; record untouched; no commit. Improved after the owner's answer to Q5 (see "Owner answers"). Skill text: new "Promote to a spec" section in `feature-artifact-new/SKILL.md`. ARTIFACTSPEC section 7 lists the command.

## Requirement map (DOCSPEC 1.0.0)
| Change | Requirement |
|---|---|
| join strips `docs/work/` with `docs_work.py strip --apply`, summaries to the PR body | R10.3 (D9); guard side R10.1, R10.2 |
| brief `docs:` line | R8.5 (D7) |
| STACKSPEC 16 and spec-new point to DOCSPEC and the new layout | R12.2 ("others point to it", D12); layout R2.1, R2.2, R4.1; archive R2.7; work R10.1; AGENTS.md R10.5 |
| artifacts promote-to-spec | R4.10 (promoted in the same branch), R10.4 (promoted before the join); template R4.2, R4.6; version untouched R4.3. Note: R8.5/R10.3 do not cover this one; R4.10 and R10.4 are the actual IDs. |

## Version bumps and change notes (no hand edits; folded on main)
- `DOC6-join-strips-docs` project-setup patch; `DOC6-stackspec-docspec` STACKSPEC minor; `DOC6-brief-docs-line` delivery patch; `DOC6-spec-new-docspec` specs patch; `DOC6-artifacts-promote` artifacts minor; `DOC6-artifactspec-promote` ARTIFACTSPEC minor.

## Tests run (only what was touched; no full suite, no Docker)
- `tools/test_delivery_gate.py --no-mutants -k join`: 99 checks, 0 failed (new scenario `join_docs_strip`: plugin present, absent, nothing to strip).
- `claude/plugins/delivery/tests` (unittest discover): 263 OK (4 new in test_brief_template.py).
- `tools/test_project_artifacts.py`: 130 passed, 0 failed, 1 skipped (3 new promote cases).
- `tools/test_project_artifacts_hooks.py`, `tools/test_delivery_hooks.py` (53 passed), `tools/test_ci_areas.py`, `tools/test_model_profiles.py`: pass.
- `spec_check.py` on invariants.md (clean) and artifactspec.md (0 errors, 1 old numbering warning); `change_notes.py check --config tools/change-notes.json`: ok; `claude plugin validate` on the marketplace and on artifacts, delivery, specs, project-setup: pass.
- Not run: GitHub CI, mutation passes.

## Owner answers (31 Oct 2026) and what changed
1. **join.py copy**: comics-organizer takes the new join.py together with its docs move. Nothing to do in this repo.
2. **PR body**, 3. **report path**, 4. **stack-profile path**: done on the follow-up branch `claude/DOC8-docs-paths` (draft PR on top of this branch); see `docs/agents/reports/DOC8.md`.
5. **promote-to-spec, improved before merge** (this branch):
   - Mapping by heading, not by position: `classify()` sends a page section to the template section its heading names: why/problem/goals to 2, what/overview to 1, how it works/steps/flow to 3, screens/visuals/mock-ups to 4, functional requirements to 5, non-functional/performance/security/privacy/limits to 6, design/data model/interfaces to 7, failure modes to 8, tests to 9, not built yet to 11, code map to 12; "for users" to 3 and "for developers" to 7. A heading that matches none goes under 3 with its own heading and is listed in the output (`unmapped`). The lede is section 1; decided decisions are the section 10 table.
   - Topics: from `meta.json` `topics`, else the `docs/docs.json` topics named in the lede or headings (limited to that list, R4.4).
   - Existing spec: merged section by section instead of refused. Your text stays; new parts are appended under `<!-- promoted from the feature page -->` (skipped when the text is already there); missing sections are inserted in template order; a template placeholder is replaced and the output says so; a decision already in the table keeps your row (a differing "chosen" is reported, not applied); empty `apps`, `topics`, `artifact` in the front matter are filled, other keys never change. The dry run prints the diff; `--apply` (alias `--yes`) writes. A second `--apply` changes nothing.
   - Tests (`tools/test_project_artifacts.py`): mapping of 22 headings, unmapped handling, topics, a page with why/FR/NFR/visuals/users/developers sections placed in template order, merge dry run (diff, nothing written), merge `--apply` (nothing of the old spec lost, idempotent), decisions merge. Change notes: `DOC8-promote-merge` (artifacts minor), `DOC8-artifactspec-promote-merge` (ARTIFACTSPEC minor). Skill text and ARTIFACTSPEC section 7 updated.
6. **Cross-feature normative specs** stay in `docs/architecture/` (kept as built).
