# Project artifacts

This folder is the record of dev-standards's project artifacts (ARTIFACTSPEC 1.0.0). It is generated and committed by
`scripts/project_artifacts.py` of the `luismc-artifacts` plugin; do not edit the JSON or the
rendered HTML by hand.

| Artifact | File | URL |
|---|---|---|
| Full Progress: dev-standards | `full-progress-dev-standards.html` | https://claude.ai/artifact/Niw1dVxGJczpzPrnyg2arv |
| Feature: Project artifacts standard | `feature-project-artifacts-standard.html` | https://claude.ai/artifact/UUcPLxwLp89kMAQxVYb5hq |
| Feature: Model and effort profiles | `feature-model-and-effort-profiles.html` | https://claude.ai/artifact/9MMjfeWhPCwH19NV39oBBn |

## Recreate an artifact that was deleted on claude.ai

The artifacts are disposable views; the record here is the source (R9.3).

1. `python <plugin>/scripts/project_artifacts.py render` writes the HTML again from `content/`,
   `registry.json` and `manifest.json`.
2. `python <plugin>/scripts/project_artifacts.py pending` lists what must be published.
3. Publish each listed file with the Artifact tool, to the URL in `manifest.json` when it still
   opens. When the publish is refused because the artifact no longer exists, list your artifacts:
   if one has the same title, publish to that one; only if none does, publish a new one.
   At most one artifact per title is ever created.
4. `python <plugin>/scripts/project_artifacts.py mark-published KEY --url URL` records the URL
   and the hash of what was published.

Change a task only with `set-task-status`; edit prose only under `content/<key>/` and then run
`edit-content <key>`.
