# Documentation

How the docs of this repository are kept. The rules are in DOCSPEC (the `luismc-docs` plugin); the settings are in `docs.json`.

Open `index.html` in a browser (double-click, no server). If `_site/` is missing, run `python3 <plugin>/scripts/docs_index.py build` once.

| Folder | The reader's question |
|---|---|
| `overview/` | What is this, who is it for, how do the parts fit? |
| `features/` | What does feature X do, and how is it built? One folder per feature. |
| `design-system/` | What are the UX rules, tokens, components? The only home of UX rules. |
| `architecture/` | How is the system built, and why? Binding cross-cutting specs and decision records. |
| `guides/` | How do I do task Y (set up, release, restore)? |
| `reference/` | What exactly is the value (API, CLI, config keys)? Generated. |
| `project/` | The artifacts record: progress and decisions in flight. |
| `archive/` | Superseded docs. Never binding. |

`work/` holds agent briefs and reports. It exists only on agent branches and never reaches the default branch.

Files marked generated (`index.html`, `llms.txt`, `features/index.md`, `architecture/decisions.md`, `docs-map.json`) are written by the scripts. Do not edit them by hand.
