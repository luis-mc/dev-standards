#!/usr/bin/env python3
"""DS185: regression tests for the project-setup review findings F14-F30.
One check per finding; each fails on the old code. No network.
Run: python3 tools/test_project_setup_fixes.py"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PS = ROOT / "claude/plugins/project-setup/skills"
CS = PS / "claude-setup"
TS = PS / "tech-stack-setup"
AS = PS / "auth-setup"
HOOKS = TS / "assets/tooling/shared/.githooks"
STOP = CS / "assets/.claude/hooks/questions_stop.py"
SH = shutil.which("sh") or "sh"


def sh(cmd, cwd=None, inp=None, env=None):
    e = dict(os.environ)
    e.update(env or {})
    return subprocess.run(cmd, shell=isinstance(cmd, str), cwd=cwd, input=inp,
                          capture_output=True, text=True, env=e)


def stop(msg):
    home = tempfile.mkdtemp()
    e = dict(os.environ, HOME=home, USERPROFILE=home)
    e.pop("CLAUDE_QUESTIONS_STOP", None)
    p = subprocess.run([sys.executable, str(STOP)], input=json.dumps({"last_assistant_message": msg}),
                       capture_output=True, text=True, env=e)
    return p.returncode


def repo_with_hook():
    d = Path(tempfile.mkdtemp())
    sh("git init -q . && git config user.email a@example.com && git config user.name t", cwd=d)
    (d / ".githooks").mkdir()
    shutil.copy(HOOKS / "pre-commit", d / ".githooks/pre-commit")
    os.chmod(d / ".githooks/pre-commit", 0o755)
    sh("git config core.hooksPath .githooks", cwd=d)
    return d


def commit(d, name, text="API_TOKEN=sk_live_realvalue123\n"):
    (d / name).write_text(text)
    sh(["git", "add", "-A"], cwd=d)
    return sh(["git", "commit", "-qm", "t"], cwd=d).returncode


def f14():
    e = []
    for p in (CS / "assets/.claude/settings.json", CS / "SKILL.md"):
        for ln in p.read_text().splitlines():
            if re.search(r'python3 \\?"[^"]*\\?" \|\| python', ln):
                e.append(f"F14 {p.name}: '|| python' fallback swallows exit 2")
    return e


def f15():
    d = repo_with_hook()
    e = []
    for n in ("my config.env", "café.env"):
        if commit(d, n) == 0:
            e.append(f"F15 secret in '{n}' was committed")
    return e


def f16():
    t = (TS / "SKILL.md").read_text()
    i = t.index("update-index --chmod=+x")
    ctx = t[i - 300:i + 200]
    e = []
    if "pre-commit" not in ctx:
        e.append("F16 SKILL.md does not list pre-commit as executable")
    if "chmod +x" not in ctx:
        e.append("F16 SKILL.md lacks a working-tree chmod +x")
    return e


def f17():
    e = []
    for m in ("Done. All tests pass. No open questions.",
              "The car is parked in the garage section of the docs; I updated it."):
        if stop(m) == 2:
            e.append(f"F17 blocked: {m!r}")
    if stop("I have open questions that I will ask later.") != 2:
        e.append("F17 real deferral no longer blocked")
    return e


def f18():
    e = []
    for m in ("I fixed the parser, which crashed on empty input. Files changed:\n\n- src/parse.py\n- tests/test_parse.py",
              "Done. I chose the simpler option and changed:\n- config.py\n- README.md"):
        if stop(m) == 2:
            e.append(f"F18 blocked a list of done work: {m[:30]!r}")
    if stop("Which one do you want?\n\n- A\n- B") != 2:
        e.append("F18 real options list no longer blocked")
    if stop("Pick one:\n- A\n- B") != 2:
        e.append("F18 'Pick one:' list no longer blocked")
    return e


def f19():
    d = repo_with_hook()
    (d / "big.cfg").write_text("x=1\n" * 30)
    sh("git add -A && git commit -qm a --no-verify", cwd=d)
    sh("git mv big.cfg big2.cfg", cwd=d)
    with open(d / "big2.cfg", "a") as fh:
        fh.write("DB_SECRET=hunter2hunter2\n")
    sh("git add -A", cwd=d)
    return [] if sh(["git", "commit", "-qm", "t"], cwd=d).returncode else ["F19 renamed file with secret committed"]


def f20():
    d = Path(tempfile.mkdtemp())
    sh("git init -q .", cwd=d)
    (d / "docs/architecture").mkdir(parents=True)
    (d / "docs/architecture/stack-profile.md").write_text("x")
    (d / "go.work").write_text("go 1.22\n")
    (d / "apps").mkdir()
    p = sh([sys.executable, str(TS / "assets/preflight.py"), "--require", "stack", "--for-skill", "auth-setup"], cwd=d)
    return [] if p.returncode == 0 else [f"F20 Go repo blocked: {p.stdout.strip()[:80]}"]


def f21():
    t = (AS / "SKILL.md").read_text()
    bad = [ln for ln in t.splitlines() if "../tech-stack-setup/assets/preflight.py" in ln]
    return [f"F21 relative preflight path: {bad[0].strip()}" for _ in bad[:1]]


def selection(text):
    f = Path(tempfile.mkdtemp()) / "sel.yaml"
    f.write_text(text)
    return sh([sys.executable, str(TS / "assets/check_stack.py"), "--selection", str(f)])


def f22():
    e = []
    if selection("language: go\nhosting: [fly, railway]\n").returncode != 0:
        e.append("F22 list-valued hosting reported as unknown")
    p = selection("language: go\napi_framework: next_handlers\nweb_framework: nxtjs\ncache: upstsh\n")
    if p.returncode == 0:
        e.append("F22 unknown web_framework/cache ids pass")
    if "next_handlers" not in p.stdout + p.stderr:
        e.append("F22 framework track mismatch (next_handlers on go) not reported")
    return e


def f23():
    e = []
    p = selection("language: typescript\nweb_framework: nextjs\nhosting: cloudflare\nblazor_render_mode: blazor_server\n")
    if p.returncode == 0:
        e.append("F23 blazor_server on cloudflare passes")
    if "blazor-server" in (TS / "assets/catalog/tech/hosting.yaml").read_text():
        e.append("F23 hosting.yaml still names blazor-server")
    sys.path.insert(0, str(TS / "assets"))
    import check_stack
    import yaml
    hosting = check_stack.load("tech/hosting.yaml")
    orig = check_stack.load

    def bad(name):
        d = orig(name)
        if name == "tech/hosting.yaml":
            d = json.loads(json.dumps(d))
            d["technologies"][0].setdefault("conflicts", []).append({"with": ["no_such_id"], "why": "x"})
        return d
    check_stack.load = bad
    try:
        errs = check_stack.check_catalog()
    finally:
        check_stack.load = orig
    if not any("no_such_id" in x for x in errs):
        e.append("F23 --catalog does not check conflict ids")
    return e


def f24():
    t = (CS / "assets/ci/dev-standards.yml").read_text()
    s = (CS / "SKILL.md").read_text()
    e = []
    if "branches: [main]" in t or "|| 'main'" in t:
        e.append("F24 workflow hardcodes main")
    if "{{DEFAULT_BRANCH}}" not in t or "{{DEFAULT_BRANCH}}" not in s:
        e.append("F24 no {{DEFAULT_BRANCH}} placeholder in workflow and SKILL.md")
    return e


def f25():
    t = (CS / "assets/ci/dev-standards.yml").read_text()
    return [] if "pnpm-lock.yaml" in t else ["F25 workflow always uses npm ci"]


def f27():
    d = Path(tempfile.mkdtemp())
    sh("git init -q .", cwd=d)
    (d / ".delivery").mkdir()
    shutil.copy(CS / "assets/delivery-config.json", d / ".delivery/config.json")
    msg = d / "msg"
    msg.write_text("t\n\nCo-Authored-By: A <a@example.com>\n")
    e = []
    if sh([SH, str(HOOKS / "commit-msg"), str(msg)], cwd=d).returncode != 0:
        e.append("F27 nested no_attribution true blocks")
    cfg = json.loads((d / ".delivery/config.json").read_text())
    cfg["no_attribution"] = True
    (d / ".delivery/config.json").write_text(json.dumps(cfg))
    if sh([SH, str(HOOKS / "commit-msg"), str(msg)], cwd=d).returncode == 0:
        e.append("F27 top-level true no longer blocks")
    return e


def f28():
    t = (CS / "SKILL.md").read_text()
    return [] if "gitattributes" in t else ["F28 SKILL.md has no .gitattributes LF rule for statusline.sh"]


def f29():
    c = json.loads((CS / "assets/delivery-config.json").read_text())
    return [] if c["enforcement"]["mode"] == "warn" else ["F29 template enforcement mode is not warn"]


def f30():
    sl = CS / "assets/.claude/statusline.sh"
    inp = '{"context_window":{"used_percentage":42,"total_input_tokens":1500000,"context_window_size":200000}}'
    p = sh(["bash", str(sl)], inp=inp, env={"NO_COLOR": "1"})
    if "1500k" in p.stdout:
        return ["F30 statusline shows the cumulative token total"]
    return []


CHECKS = [f14, f15, f16, f17, f18, f19, f20, f21, f22, f23, f24, f25, f27, f28, f29, f30]


def main():
    only = set(sys.argv[1:])
    errors = []
    for c in CHECKS:
        if only and c.__name__ not in only:
            continue
        try:
            errors += c()
        except Exception as ex:  # a crash is a failure
            errors.append(f"{c.__name__} crashed: {ex!r}")
    for e in errors:
        print("FAIL:", e)
    print(f"project-setup fixes: {len(errors)} problems")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
