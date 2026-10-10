# Project artifacts

This folder is the record of dev-standards's project artifacts (ARTIFACTSPEC 1.0.0). It is generated and committed by
`scripts/project_artifacts.py` of the `luismc-artifacts` plugin; do not edit the JSON or the
rendered HTML by hand.

| Artifact | File | Where |
|---|---|---|
| Full Progress: dev-standards | `full-progress-dev-standards.html` | https://claude.ai/artifact/Niw1dVxGJczpzPrnyg2arv |
| Feature: Project artifacts standard | `feature-project-artifacts-standard.html` | a file in the repository, open it in a browser; never published |
| Feature: Model and effort profiles | `feature-model-and-effort-profiles.html` | a file in the repository, open it in a browser; never published |

A feature artifact is a standalone HTML file: open it in a browser, no server needed. It is
never published. Only the full-progress artifact is a claude.ai artifact; it links to the
feature files as local files.

## Recreate the full-progress artifact if it was deleted on claude.ai

The artifact is a disposable view; the record here is the source (R9.3).

1. `python <plugin>/scripts/project_artifacts.py render` writes the HTML again from `content/`,
   `registry.json` and `manifest.json`.
2. `python <plugin>/scripts/project_artifacts.py pending` lists Full Progress when it must be
   published and writes the publish copy (`.claude/artifacts-publish/`, not committed).
3. Publish that file with the Artifact tool, once at the end of the turn, to the URL in
   `manifest.json` when it still opens. When the publish is refused because the artifact no
   longer exists, list your artifacts: if one has the same title, publish to that one; only if
   none does, publish a new one. At most one artifact per title is ever created.
4. `python <plugin>/scripts/project_artifacts.py mark-published full-progress --url URL` records
   the URL and the hash of the committed render.

Change a task only with `set-task-status`; edit prose only under `content/<key>/` and then run
`edit-content <key>`.
