import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
os.environ["DOCS_TODAY"] = "2026-10-31"


def git(root, *a):
    return subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t", *a],
                          capture_output=True, text=True, check=True)


def make_repo(files=None, commit=True):
    d = Path(tempfile.mkdtemp(prefix="docs-"))
    git(d, "init", "-q", "-b", "main")
    for rel, text in (files or {}).items():
        w(d, rel, text)
    if commit:
        git(d, "add", "-A")
        git(d, "commit", "-q", "-m", "init")
    return d


def w(root, rel, text):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def r(root, rel):
    return (Path(root) / rel).read_text(encoding="utf-8")


def spec(fid="import", apps="[web]", topics="[library]", status="live", version="1.0.0", code="[src/import/**]", extra="", body=None):
    body = body if body is not None else "# T\n\n```mermaid\nflowchart LR\n a-->b\n```\n"
    return (f"---\nid: {fid}\ntitle: T {fid}\napps: {apps}\ntopics: {topics}\nstatus: {status}\nversion: {version}\n"
            f"owner: owner\ntype: reference\ncode: {code}\nlast_verified: 2026-10-30\n{extra}---\n{body}")


def project(extra_files=None, apps=("web",), topics=("library",)):
    """A repo that already follows the layout."""
    import json
    import docs_setup as S
    d = make_repo({"README.md": "# r\n", "src/import/a.py": "x=1\n"}, commit=False)
    w(d, "docs/docs.json", json.dumps({"schema": 1, "apps": list(apps), "topics": list(topics), "record_dir": "docs/project", "default_branch": "main", "stale_days": 90}))
    w(d, "docs/README.md", "# Docs\n")
    for n in ("README.md", "apps.md", "system.md", "glossary.md", "quality.md"):
        w(d, f"docs/overview/{n}", f"# {n}\n")
    w(d, "AGENTS.md", "# Agents\n")
    for rel, text in (extra_files or {}).items():
        w(d, rel, text)
    return d
