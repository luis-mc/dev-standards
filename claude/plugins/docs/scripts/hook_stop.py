#!/usr/bin/env python3
"""Stop hook (D7): at the end of a turn, warn when mapped code changed on this branch and no doc,
change note or `Docs: none, <reason>` did. It only warns (systemMessage); the gate blocks.

Opt-in: does nothing in a repository without docs/docs.json. Fails open: any error prints nothing.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def message(root) -> str:
    import docs_lib as D
    import docs_check as C
    if not D.has_config(root):
        return ""
    cfg = D.load_config(root)
    base = D.default_base(root, cfg)
    found = C.check_map(root, cfg, base)
    errs = [x for x in found if x["severity"] == "error"]
    if not errs:
        return ""
    lines = ["luismc-docs: code changed without its docs (DOCSPEC 8.2). Update the doc, add a change note "
             "(docs_fold.py note --doc features/<feature> --task <TASK> --change minor --text \"...\"), "
             "or put `Docs: none, <reason>` in a commit message:"]
    lines += [f"  - {x['path']}: {x['message']}" for x in errs[:8]]
    if len(errs) > 8:
        lines.append(f"  - and {len(errs) - 8} more")
    return "\n".join(lines)


def main() -> int:
    try:
        try:
            sys.stdin.read()
        except Exception:
            pass
        import docs_lib as D
        msg = message(D.repo_root())
        if msg:
            print(json.dumps({"systemMessage": msg}))
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
