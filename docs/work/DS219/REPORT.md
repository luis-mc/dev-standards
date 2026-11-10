# DS219 report

Branch DS219-docs-merge. In progress; the last line says READY or NOT READY.

## Base check
`git fetch origin main && git checkout -B DS219-docs-merge origin/main`, then `git merge-base --is-ancestor 1d82f859 HEAD` succeeded (HEAD was 1d82f85 at the start).

## File move map (git mv, history kept)
- claude/plugins/artifacts/{design,rules,templates} -> claude/plugins/docs/{design,rules,templates}
- claude/plugins/artifacts/references/artifactspec.md -> claude/plugins/docs/references/
- claude/plugins/artifacts/scripts/*.py -> claude/plugins/docs/scripts/ (flat)
- Name clash: artifacts hook_session_start.py -> claude/plugins/docs/scripts/artifacts/hook_session_start.py (docs keeps its own scripts/hook_session_start.py). Only that file is in the subfolder; it adds the parent folder to sys.path.
- claude/plugins/artifacts/skills/* (5) -> claude/plugins/docs/skills/
- claude/plugins/specs/skills/{spec-check,spec-new} -> claude/plugins/docs/skills/
- hooks.json merged into claude/plugins/docs/hooks/hooks.json (Stop and SessionStart have two entries each; PostToolUse, PostToolUseFailure, UserPromptSubmit added; all paths use ${CLAUDE_PLUGIN_ROOT}).
- claude/plugins/artifacts and claude/plugins/specs deleted (their plugin.json too).

## References changed (by file)
- .claude-plugin/marketplace.json: two plugins removed, luismc-docs description widened. claude/plugins/docs/.claude-plugin/plugin.json: description only.
- .claude/settings.json (enabledPlugins), .claude/suites.json (new suite artifacts-ds219).
- .github/workflows/spec-lint.yml: spec-check paths, ARTIFACTSPEC step, new DS219 step.
- tools/ci_areas.py and tools/test_ci_areas.py: artifacts files inside the docs plugin map to the artifacts area; docs hooks.json runs docs and artifacts; artifactspec and spec assets stay in specs.
- tools/change-notes.json: artifactspec path.
- tools tests: test_artifacts_ar59/60/63/66/67/dl173, test_project_artifacts, test_project_artifacts_hooks, test_render_artifacts, test_model_profiles, test_spec_check, test_rule_tags, test_ds_enforcement, test_artifacts_dl173 (plugin path, fixtures keep docs/artifacts through an artifacts.json with no record_dir, hook list now has the docs hooks too).
- New tools/test_artifacts_ds219.py (record default, six cases).
- claude/plugins/delivery: references/plugin-compat.json (luismc-docs >=2.0.0 both ways), references/design-gate.md, CONTRACT.md, tests/test_dl173_compat.py.
- claude/plugins/project-setup: claude-setup SKILL.md (6 plugins, removes old keys, spec_check path), assets/.claude/settings.json, assets/ci/dev-standards.yml (SPEC_CHECK path), tech-stack-setup SKILL.md (spec_check path).
- claude/plugins/docs: scripts (messages and rule heading say luismc-docs; artifact_queue.py record default), rules/project-artifacts.md, skills (feature-spec-new, spec-new template, spec-check), references/docspec.md R13.3 and artifactspec.md (names and paths only), README.md.
- README.md (install lines, two sections renamed, six plugins), docs/overview/apps.md left for the follow-up below, docs/docs.json (apps), docs/guides/setup-skills.md, docs/guides/upgrade-stackspec-8.md (pointer line), docs/features/{artifacts,specs,docs,project-setup,delivery-speed,test-cost}/spec.md, docs/architecture/DELIVERYSPEC.md (paths).
- Tool path tools/spec_check.py replaced by claude/plugins/docs/skills/spec-check/assets/spec_check.py in docspec R13.3, the spec_check.py docstring, tech-stack-setup and the CI template.
- Version lines, change logs, version tables, requirement IDs: not touched.

## Record default (item 4)
artifact_queue.record_rel: .claude/artifacts.json record_dir, else docs/artifacts when that file exists; with no such file docs/docs.json record_dir, else docs/project; as a safety, with no setting at all a record that already sits in docs/artifacts (none in docs/project) is still found there, so old projects and the old test fixtures keep working. The fixture seed of artifacts.json was dropped for that reason. Hooks and project_artifacts.py all use this function.

## Docs
Notes: docs/architecture/changes/DS219-docs.md (major), DS219-delivery.md (patch), DS219-project-setup.md (minor). Feature notes (docs_fold.py note): artifacts, specs, docs (major), delivery, models, project-setup. Guide: docs/guides/migrate-to-luismc-docs-2.md, linked from the docs plugin README.

(Tests, CI and head SHA are filled in below.)
