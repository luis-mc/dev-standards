#!/usr/bin/env python3
"""Stop hook (D7): at the end of a turn, warn when mapped code changed on this branch and no doc,
change note or `Docs: none, <reason>` did. It only warns (systemMessage); the gate blocks.

Opt-in: does nothing in a repository without docs/docs.json. Fails open: any error prints nothing.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def message(root, base=None) -> str:
    import docs_lib as D
    import docs_check as C
    if not D.has_config(root):
        return ""
    cfg = D.load_config(root)
    base = base or D.default_base(root, cfg)
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


def _state_path(root: Path) -> Path:
    g = Path(root) / ".git"
    if g.is_dir():
        return g / "luismc-docs-stop.json"
    h = hashlib.sha1(str(Path(root).resolve()).encode()).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / f"luismc-docs-stop-{h}.json"


def _file_sig(root, rel) -> str:
    try:
        st = os.stat(Path(root) / rel)
        return f"{st.st_mtime_ns}:{st.st_size}"
    except OSError:
        return "-"


def _key(root, cfg):
    """(base, key) from two git calls: rev-parse (base and HEAD) and status, plus the mtime and size of each changed
    file. None on any doubt."""
    import docs_lib as D
    for cand in (f"origin/{cfg['default_branch']}", cfg["default_branch"]):
        r = D.git(root, "rev-parse", "-q", cand, "HEAD")
        if r.returncode == 0 and len(r.stdout.split()) == 2:
            base_sha, head = r.stdout.split()
            st = D.git(root, "status", "--porcelain", "-uall")
            if st.returncode != 0:
                return cand, None
            # The status text does not change when an already changed file is edited again, so each listed
            # file's mtime and size is in the key too. A quoted (unusual) path gives no key: no cache.
            paths = [ln[3:].split(" -> ")[-1] for ln in st.stdout.split("\n") if ln]
            if any(p.startswith('"') for p in paths):
                return cand, None
            files = sorted(set(paths) | {"docs/docs-map.json", "docs/docs.json"})
            h = hashlib.sha256(st.stdout.encode()).hexdigest()
            sig = "|".join(f"{p}={_file_sig(root, p)}" for p in files)
            return cand, [head, base_sha, h, hashlib.sha256(sig.encode()).hexdigest()]
    return None, None


def cached_message(root) -> str:
    import docs_lib as D
    if not D.has_config(root):
        return ""
    cfg = D.load_config(root)
    base, key = _key(root, cfg)
    if base is None or key is None:
        return message(root)
    path = _state_path(root)
    try:
        st = json.loads(path.read_text(encoding="utf-8"))
        if st.get("key") == key and isinstance(st.get("msg"), str):
            return st["msg"]
    except Exception:
        pass
    msg = message(root, base)
    try:
        tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps({"key": key, "msg": msg}), encoding="utf-8")
        os.replace(tmp, path)
    except Exception:
        pass
    return msg


def main() -> int:
    try:
        try:
            sys.stdin.read()
        except Exception:
            pass
        import docs_lib as D
        msg = cached_message(D.repo_root())
        if msg:
            print(json.dumps({"systemMessage": msg}))
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
