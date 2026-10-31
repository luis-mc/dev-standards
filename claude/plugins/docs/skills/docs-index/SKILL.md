---
name: docs-index
description: Build the browsable docs: docs/index.html (opens by double-click, offline, with search and the feature index by app and topic), the per-page site in docs/_site, features/index.md, decisions.md, docs-map.json and llms.txt. Use when docs changed and the generated files must be rebuilt, when a docs check says a generated file is stale, or to vendor Mermaid for offline diagrams.
model: sonnet
effort: medium
---

# Docs — index

Runs `scripts/docs_index.py` (DOCSPEC §6).

```bash
I="${CLAUDE_PLUGIN_ROOT}/scripts/docs_index.py"
python3 "$I" build                    # write every generated file and the site
python3 "$I" check                    # exit 1 if a committed generated file is stale
python3 "$I" fetch-mermaid            # vendor a pinned mermaid.js into docs/_site/vendor/ (needs network)
python3 "$I" build --mermaid PATH     # vendor a local mermaid.min.js
```

Commit the generated files except `docs/_site/` (git-ignored). Never edit them by hand. After a build, read the Gaps list and report it. If Mermaid is not vendored, diagrams show as source with a note; that is not an error.
