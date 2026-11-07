#!/usr/bin/env python3
"""Run the TypeScript design-system guard templates for real (DS188).

Builds throwaway projects in a temp dir with design_system.py (init, visuals,
promote), copies the four templates to scripts/design/, installs a pinned
vitest there and runs it. Needs git, node 20.12+ and npm with registry access.

Cases:
  clean     v1 approved, next-version drafted: every guard passes.
  archived  v1 moved to docs/archive/design-system-v1/, v2 live: layout and
            freeze guards pass (the freeze case diffs against the commit
            that still held v1).
  gap       v1 missing and not archived: the layout guard fails, and only it.
  components  the opt-in picker templates (design_system.py components --apply): their
            vitest tests (jsdom) pass and tsc --noEmit is clean (R15.10).

Run:  python3 tools/test_ds_guard_templates.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

VITEST = "3.2.4"
# The component templates' test stack, exact versions.
COMPONENT_DEPS = {"vitest": VITEST, "jsdom": "26.1.0", "react": "19.1.0", "react-dom": "19.1.0",
                  "typescript": "5.8.3", "@types/react": "19.1.8", "@types/react-dom": "19.1.6"}
ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "claude" / "plugins" / "docs"
SCRIPT = PLUGIN / "scripts" / "design_system.py"
TEMPLATES = PLUGIN / "templates" / "design-system" / "guards" / "typescript-vitest"
ENV_GIT = ["-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false"]


def run(cmd, cwd, env=None, check=True):
    import os
    e = dict(os.environ)
    e.update(env or {})
    p = subprocess.run(cmd, cwd=cwd, env=e, text=True, capture_output=True)
    if check and p.returncode != 0:
        raise SystemExit(f"FAIL: {' '.join(map(str, cmd))}\n{p.stdout}\n{p.stderr}")
    return p


def ds(proj, *args):
    run([sys.executable, str(SCRIPT), "--root", str(proj), *args], proj)


def promote(proj, n):
    ds(proj, "promote", "--approved-by", "owner", "--approved-on", f"2026-01-0{n}",
       "--evidence", "fixture", "--apply")


def commit(proj, msg):
    run(["git", *ENV_GIT, "add", "-A"], proj)
    run(["git", *ENV_GIT, "commit", "-q", "-m", msg], proj)
    return run(["git", "rev-parse", "HEAD"], proj).stdout.strip()


def base_project(tmp: Path, name: str, versions: int) -> Path:
    proj = tmp / name
    proj.mkdir()
    run(["git", "init", "-q"], proj)
    ds(proj, "init", "--apply")
    ds(proj, "visuals", "--apply")
    for n in range(1, versions + 1):
        if n > 1:  # a later promotion needs a change entry in the draft
            changes = proj / "docs" / "design-system" / "next-version" / "CHANGES.md"
            changes.write_text(changes.read_text() + f"- C{n}: fixture change\n")
        promote(proj, n)
    (proj / "src").mkdir()
    (proj / "src" / "app.ts").write_text("export const title = 'Home';\n")
    guards = proj / "scripts" / "design"
    guards.mkdir(parents=True)
    for f in TEMPLATES.glob("*.ts"):
        shutil.copy(f, guards / f.name)
    (proj / "package.json").write_text(json.dumps({
        "name": "app1", "private": True, "type": "module",
        "devDependencies": {"vitest": VITEST}}, indent=2))
    return proj


def install(proj: Path, cache: Path | None):
    if cache is not None:
        shutil.copytree(cache / "node_modules", proj / "node_modules", symlinks=True)
        return
    run(["npm", "install", "--no-audit", "--no-fund", "--save-exact", "--no-package-lock"], proj)


def vitest(proj: Path, base: str | None = None) -> dict:
    env = {"DESIGN_BASE": base} if base else {}
    p = run(["npx", "vitest", "run", "--reporter=json", "--root", str(proj)], proj, env, check=False)
    start = p.stdout.find("{")
    if start < 0:
        raise SystemExit(f"FAIL: no vitest JSON\n{p.stdout}\n{p.stderr}")
    return json.loads(p.stdout[start:])


def failed_files(result: dict) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for f in result["testResults"]:
        bad = [a["title"] for a in f["assertionResults"] if a["status"] != "passed"]
        if f["status"] != "passed" and not bad:
            bad = [f.get("message", "file failed")]
        if bad:
            out[Path(f["name"]).name] = bad
    return out


def expect(label, result, want_fail: dict[str, str] | None):
    """want_fail None: all pass. Else {file: title substring} and nothing else fails."""
    bad = failed_files(result)
    ran = sum(len(f["assertionResults"]) for f in result["testResults"])
    if want_fail is None:
        ok = not bad and ran > 0
    else:
        ok = set(bad) == set(want_fail) and all(
            any(want_fail[k] in t for t in bad[k]) for k in want_fail)
    print(f"{'PASS' if ok else 'FAIL'}: {label} ({ran} tests, failing: {bad or 'none'})")
    return ok


def components_case(tmp: Path) -> bool:
    proj = tmp / "components"
    proj.mkdir()
    run(["git", "init", "-q"], proj)
    ds(proj, "init", "--apply")
    ds(proj, "components", "--apply")
    (proj / "package.json").write_text(json.dumps({
        "name": "app2", "private": True, "type": "module", "devDependencies": COMPONENT_DEPS}, indent=2))
    (proj / "tsconfig.json").write_text(json.dumps({"compilerOptions": {
        "target": "ES2022", "module": "ESNext", "moduleResolution": "bundler", "jsx": "react-jsx",
        "strict": True, "noEmit": True, "skipLibCheck": True, "types": [],
        "lib": ["ES2022", "DOM", "DOM.Iterable"]}, "include": ["src"]}, indent=2))
    install(proj, None)
    ok = expect("component templates: keyboard, value and limits", vitest(proj), None)
    tsc = run(["npx", "tsc", "-p", "."], proj, check=False)
    print(f"{'PASS' if tsc.returncode == 0 else 'FAIL'}: component templates typecheck"
          + ("" if tsc.returncode == 0 else f"\n{tsc.stdout}{tsc.stderr}"))
    return ok and tsc.returncode == 0


def main() -> int:
    if not shutil.which("node") or not shutil.which("npm"):
        print("FAIL: node and npm are required")
        return 1
    tmp = Path(tempfile.mkdtemp(prefix="ds-guards-"))
    ok = True
    try:
        # clean
        clean = base_project(tmp, "clean", 1)
        commit(clean, "clean")
        install(clean, None)
        ok &= expect("clean fixture passes", vitest(clean, "HEAD"), None)

        # archived: v1 and v2 approved, then v1 moved to docs/archive/
        arch = base_project(tmp, "archived", 2)
        before = commit(arch, "v1 and v2")
        (arch / "docs" / "archive").mkdir()
        shutil.move(str(arch / "docs" / "design-system" / "v1"),
                    str(arch / "docs" / "archive" / "design-system-v1"))
        commit(arch, "archive v1")
        install(arch, clean)
        ok &= expect("archived v1, live v2 passes layout and freeze", vitest(arch, before), None)

        # gap: v1 deleted, not archived. The freeze diff would also flag the delete, so give it
        # no base to compare with (it then skips); this case is about the layout guard alone.
        gap = base_project(tmp, "gap", 2)
        commit(gap, "v1 and v2")
        shutil.rmtree(gap / "docs" / "design-system" / "v1")
        install(gap, clean)
        ok &= expect("v1 missing and not archived fails the layout guard", vitest(gap, "no-such-ref"),
                     {"design-system-layout.test.ts": "holds only version folders"})

        ok &= components_case(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("OK" if ok else "NOT OK")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
