"""Helpers for the DS235b tests: run a Node guard, find Playwright and esbuild, build the fixture apps."""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

DS = Path(__file__).resolve().parent.parent / "templates" / "design-system"
GUARDS = DS / "guards"
PARTS = DS / "parts"
NODE = shutil.which("node")


def node(script, *args, env=None):
    e = dict(os.environ)
    e.update(env or {})
    p = subprocess.run([NODE, str(script), *map(str, args)], capture_output=True, text=True, env=e, timeout=300)
    return p.returncode, p.stdout + p.stderr


def have_playwright():
    if not NODE:
        return False
    p = subprocess.run([NODE, "-e", "require('playwright')"], capture_output=True, text=True,
                       env={**os.environ, "NODE_PATH": os.environ.get("NODE_PATH", "")})
    return p.returncode == 0


_NM = None


def build_modules():
    """A node_modules folder with react, react-dom and esbuild, or None when it cannot be had."""
    global _NM
    if _NM:
        return _NM
    nm = os.environ.get("DS_NODE_MODULES")
    if nm and (Path(nm) / "esbuild").exists():
        _NM = nm
        return nm
    if not NODE or not shutil.which("npm"):
        return None
    d = Path(tempfile.mkdtemp(prefix="ds235b-npm-"))
    (d / "package.json").write_text("{}")
    p = subprocess.run(["npm", "i", "--no-audit", "--no-fund", "react@18.3.1", "react-dom@18.3.1", "esbuild"],
                       cwd=d, capture_output=True, text=True, timeout=240)
    if p.returncode != 0:
        return None
    _NM = str(d / "node_modules")
    return _NM


_FX = None


def fixtures():
    """Build the fixture apps once; returns the folder, or None."""
    global _FX
    if _FX:
        return _FX
    nm = build_modules()
    if not nm:
        return None
    out = Path(tempfile.mkdtemp(prefix="ds235b-fx-"))
    rc, text = node(PARTS / "react-typescript" / "build-fixtures.mjs", out, env={"DS_NODE_MODULES": nm})
    if rc != 0:
        raise RuntimeError(text)
    _FX = out
    return out


def page(body, css="", head=""):
    tokens = (PARTS / "react-typescript" / "tokens.fixture.css").read_text()
    d = Path(tempfile.mkdtemp(prefix="ds235b-page-"))
    f = d / "page.html"
    f.write_text(f'<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
                 f'<style>{tokens}{css}</style>{head}</head><body>{body}</body></html>')
    return f
