---
name: docs-check
description: Check a project's docs against the documentation standard and the code: layout, feature front matter, links and anchors, Source lines, test paths, version tables, generated files and reference, the code-to-doc map, files under docs/work, UX rules outside the design system, the design-system version layout (README order of work, edits to a numbered version, stale gallery), and freshness. Use before finishing a task that changed behaviour, before a pull request, or when asked whether the docs are true.
model: sonnet
effort: medium
---

# Docs — check

Runs `scripts/docs_check.py` (DOCSPEC §8).

```bash
C="${CLAUDE_PLUGIN_ROOT}/scripts/docs_check.py"
python3 "$C" --base origin/main        # all checks; exit 1 on an error
python3 "$C" map --base origin/main    # only: mapped code changed without docs
python3 "$C" drift                     # freshness and code-newer-than-doc warnings
python3 "$C" --strict --json           # warnings fail; machine-readable
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/docs_work.py" guard --base origin/main
```

A finding is `ERROR|WARNING <code> <path>: <message>`. Fix each error in the branch. Update the doc, add a change note (`docs-note`), or, when no doc is needed, put `Docs: none, <reason>` in a commit message. Do not silence a check by emptying a doc or editing a generated file. Report warnings (stale, drift) to the owner as a list. Do not mark `last_verified` before you re-read the spec against the code.
