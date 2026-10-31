---
id: glossary
title: Glossary
type: reference
owner: owner
last_verified: 2026-10-31
---
# Glossary

One term, one meaning. Where a word was used for two things, it appears twice with a qualifier.

| Term | Meaning | Where it is seen |
|---|---|---|
| app | One plugin of the marketplace, named `luismc-<name>`. | `docs/docs.json`, [the apps](apps.md) |
| shipped spec | A binding spec that a plugin carries as a reference: ARTIFACTSPEC, DOCSPEC, STACKSPEC, AUTHSPEC. DELIVERYSPEC sits in `docs/architecture/`. | `claude/plugins/*/references/` |
| requirement ID | The stable label of one rule in a spec, such as R4.24, U7 or DL-nn. Projects, hooks and tests cite it. It is never renumbered. | Specs, tests, rule files |
| Stack Profile | The file a generated project keeps to record which spec versions it conforms to and which vendors it chose. | `docs/architecture/stack-profile.md` in a project |
| feature spec | The one page that says what a feature does and how it is built. One folder per feature. | `docs/features/<id>/spec.md` |
| change note | A one- or two-sentence file that a branch adds instead of editing a spec's version or a plugin's `version`. | `docs/architecture/changes/` |
| fold (release) | The step that turns change notes into one version bump and one change-log entry per target, then deletes the notes. | `change_notes.py fold`, `docs_fold.py` |
| fold (transcript) | Showing a long diff or a finished command as one line in the transcript. | `luismc-transcript-folds`, the band above the prompt |
| release | One batch of task branches that are joined, tested by one ready pull request and merged together. The ledger still calls it a train. | Chat, pull request titles |
| RELEASE-n | The number the owner hears for a release. Chat uses it, never a branch name. | Chat, the artifacts record |
| train | The ledger's name for a release in flight. | `.delivery/ledger.json` |
| task branch | A short-lived branch where one agent does one task. It is deleted after the release merges. | Git, agent briefs |
| gate | The check an agent runs on its branch before pushing. It writes a result bound to the branch head and base. | `gate-result.json` |
| join | Merging the task branches of a release into one head, with a light check. It does not rerun the full gate. | `join.py` |
| cleanup | Removing merged branches, worktrees and CI refs after a release merges. | `cleanup.py`, ledger `cleaned_at` |
| ledger | The per-repository file where delivery hooks record releases, agents, runners and owner questions. It is git-ignored. | `.delivery/ledger.json` |
| rule tag | The comment at the end of a rule line that names the requirement that enforces it, or says `advice`. | `<!-- check: DL-nn -->` in rule files |
| record | The files an artifacts project is generated from: a manifest, a task registry and content. | `docs/project/` |
| task | One unit of work in the registry. Every activity is a task, the session's own included. | Feature and Full Progress artifacts |
| feature artifact | A standalone HTML status page for one feature. It lives in the repository and is never published. | `docs/project/feature-<slug>.html` |
| Full Progress | The project's one claude.ai artifact. It lists all features and tasks, and is published once at the end of a turn. | claude.ai |
| Built | Task status: finished but not yet released. | Artifacts |
| Live | Task status: released. | Artifacts |
| MADR | A decision record: context, options, decision, consequences. | `docs/architecture/decisions/` |
| generated file | A file a script writes. Never edited by hand. | `docs/index.html`, `docs/llms.txt`, `docs/docs-map.json`, `docs/features/index.md`, `docs/architecture/decisions.md` |
| docs gate | The check that blocks a branch whose mapped code changed without its doc, a change note or a `Docs: none` line. | `docs_check.py` (M1) |
