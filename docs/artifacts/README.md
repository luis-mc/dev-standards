# Artifact record: dev-standards

This folder is the record of the dev-standards project artifacts: the repo record is the
source, and the published artifacts are generated from it. It holds:

- `manifest.json`: the project, its timezone and design, the full-progress artifact and each
  feature artifact with its link, task prefix, app and file.
- `registry.json`: the task registry, the same one embedded in the full-progress artifact.
- the last published HTML of every artifact.
- `build/`: the generator (`build.py`, the content modules, `check.py`) and the two stylesheets
  it needs under `build/design/` and `build/templates/`.

## Rebuild

    python -I build/build.py <out> <dir containing design/ and templates/> "<DD Mon HH:MM>" <iso> <fp-url> --models-url <url>

`build/` itself contains `design/` and `templates/`, so it can be its own CSS root:

    python -I build/build.py out build "10 Oct 12:00" 2026-10-10T12:00+01:00 <fp-url> --models-url <url>

`<out>` gets the HTML files and a fresh `record/`. Run `python -I build/check.py <out>` to check them.

## Recreate a deleted artifact without duplicates

1. Try to open the link in `manifest.json`. If it opens, republish the HTML to that link.
2. If it no longer opens, list your artifacts and look for one with the same title. If you find
   one, write its link to the manifest.
3. Only if none exists, publish the HTML as a new artifact and write the new link to the manifest.
4. Commit the manifest to the default branch as a docs-only commit.

This manual procedure is replaced by the luismc-artifacts plugin (AR7, AR15) once it is built.
