#!/usr/bin/env python3
"""SessionStart hook (D7): hand the agent the docs rule in a repository that opted in with
docs/docs.json. Prints hookSpecificOutput.additionalContext. Fails open."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

RULE = """Documentation standard (luismc-docs, DOCSPEC):
- Docs live in docs/ by reader question: overview, features (one folder per feature, spec.md), design-system, architecture, guides, reference, project. Start at docs/README.md.
- Change behaviour -> update the feature spec in the same branch and add a change note (docs_fold.py note). Never edit a version table: the release fold writes it. No doc needed -> `Docs: none, <reason>` in a commit message.
- UX rules live only in docs/design-system/; a feature spec shows its screens and cites rules by ID.
- Agent briefs and reports go in docs/work/ on your branch only, never into a PR for the default branch. Standing rules go in AGENTS.md.
- Never hand-edit generated files (docs/index.html, llms.txt, features/index.md, architecture/decisions.md, docs-map.json, reference/). Rebuild with docs_index.py build.
- Before finishing run docs_check.py. Scripts: ${CLAUDE_PLUGIN_ROOT}/scripts/."""


def main() -> int:
    try:
        try:
            sys.stdin.read()
        except Exception:
            pass
        import docs_lib as D
        root = D.repo_root()
        if not D.has_config(root):
            return 0
        text = RULE.replace("${CLAUDE_PLUGIN_ROOT}", str(Path(__file__).resolve().parent.parent))
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}))
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
