"""DL186: the installer writes .gitleaks.toml; the shared rules skip types, fields and empty values."""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

import _helpers  # noqa: F401  (puts the plugin scripts on sys.path)
import delivery_ci_install as INS

try:
    import tomllib
except ImportError:  # Python 3.10: the rules are read with a minimal parser below
    tomllib = None

PLUGIN = Path(__file__).resolve().parent.parent
REPO = PLUGIN.parent.parent.parent
SHARED = PLUGIN / "templates" / "shared" / ".gitleaks.toml"
ROOT_CFG = REPO / ".gitleaks.toml"
PS_COPY = REPO / "claude/plugins/project-setup/skills/tech-stack-setup/assets/tooling/shared/.gitleaks.toml"


def run(*argv):
    out, err = StringIO(), StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = INS.main(list(argv))
    return code, out.getvalue() + err.getvalue()


def load_rules(path):
    """{rule id: compiled regex} and the list of compiled allowlist regexes."""
    text = Path(path).read_text(encoding="utf-8")
    if tomllib is not None:
        data = tomllib.loads(text)
        rules = {r["id"]: r["regex"] for r in data["rules"]}
        allow = list(data["allowlist"]["regexes"])
    else:
        rules, allow = {}, []
        for m in re.finditer(r"id = \"([^\"]+)\"\n(?:#.*\n|description = .*\n)*regex = '''(.*?)'''", text):
            rules[m.group(1)] = m.group(2)
        block = text[text.index("regexes = ["):]
        allow = re.findall(r"'''(.*?)'''", block)
    return {k: re.compile(v) for k, v in rules.items()}, [re.compile(a) for a in allow]


def flagged(line, rules, allow):
    """Does any custom rule match the line and no allowlist regex match it?"""
    hits = [rid for rid, rx in rules.items() if rx.search(line)]
    return bool(hits) and not any(a.search(line) for a in allow)


# Built at run time so this file holds no secret-shaped line of its own.
K = "API_" + "KEY"
FALSE_POSITIVES = [
    "fn present(&self, _token: &Token, _value: &str) -> bool {",
    "    pub enrollment_secret: String,",
    "    database_url: &str,",
    "pub struct Cfg { pub db_" + "pass: String }",
    "    client_secret: string;",
    "DATABASE_" + "URL=",
    "DATABASE_" + "URL=   ",
    "DATABASE_" + "URL= # set it locally",
    K + "=",
    "SESSION_" + "SECRET=\t# generate with openssl",
]
REAL = [
    K + ' = "abc123def456ghi789"',
    "DATABASE_" + "URL=postgres://user:pass@host/db",
    "database_" + "url: postgres://user:pass@host/db",
    'my_' + 'token: "literal-value-123"',
    "export STRIPE_" + "SECRET=sk_live_abc123",
    "SESSION_" + "SECRET='hunter2hunter2'",
]


class Installer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.cfg = os.path.join(self.tmp, ".gitleaks.toml")

    def test_installs_when_missing(self):
        code, out = run("install", "--track", "ts", "--root", self.tmp)
        self.assertEqual(code, 0, out)
        self.assertTrue(os.path.isfile(self.cfg), out)
        self.assertEqual(Path(self.cfg).read_bytes().replace(b"\r\n", b"\n"),
                         SHARED.read_bytes().replace(b"\r\n", b"\n"))

    def test_keeps_a_project_file_on_install_and_update(self):
        Path(self.cfg).write_text("# acme/widget own rules\n", encoding="utf-8")
        for action in ("install", "update"):
            code, out = run(action, "--track", "ts", "--root", self.tmp)
            self.assertEqual(code, 0, out)
            self.assertEqual(Path(self.cfg).read_text(encoding="utf-8"), "# acme/widget own rules\n", action)

    def test_every_track_installs_it(self):
        for track in INS.TRACKS:
            tmp = tempfile.mkdtemp()
            self.addCleanup(shutil.rmtree, tmp, True)
            run("install", "--track", track, "--root", tmp)
            self.assertTrue(os.path.isfile(os.path.join(tmp, ".gitleaks.toml")), track)

    def test_one_source_only(self):
        self.assertTrue(SHARED.is_file())
        self.assertFalse(PS_COPY.exists(), "tech-stack-setup must not carry a second copy")


class Rules(unittest.TestCase):
    def check(self, path):
        rules, allow = load_rules(path)
        self.assertEqual(set(rules), {"project-database-url", "project-named-secret"})
        for line in FALSE_POSITIVES:
            self.assertFalse(flagged(line, rules, allow), "false positive: %r" % line)
        for line in REAL:
            self.assertTrue(flagged(line, rules, allow), "missed: %r" % line)

    def test_shared_rules(self):
        self.check(SHARED)

    def test_root_rules(self):
        self.check(ROOT_CFG)

    def test_root_and_shared_rules_are_identical(self):
        a, _ = load_rules(SHARED)
        b, _ = load_rules(ROOT_CFG)
        self.assertEqual({k: v.pattern for k, v in a.items()}, {k: v.pattern for k, v in b.items()})

    def test_empty_key_does_not_reach_the_next_line(self):
        rules, allow = load_rules(SHARED)
        text = "DATABASE_" + "URL=\nPORT=5432\n"
        self.assertFalse(any(rx.search(text) for rx in rules.values()))


class Binary(unittest.TestCase):
    """Runs gitleaks when the pinned release can be fetched. Skipped otherwise."""

    def test_gitleaks_dir(self):
        tool = PLUGIN / "templates/shared/scripts/delivery/ci_tool.py"
        try:
            p = subprocess.run([sys.executable, "-I", str(tool), "gitleaks", "--platform", "linux_x64"],
                               capture_output=True, text=True, timeout=120)
        except (OSError, subprocess.SubprocessError) as e:
            self.skipTest("ci_tool failed: %s" % e)
        exe = p.stdout.strip()
        if p.returncode != 0 or not exe or not os.path.isfile(exe):
            self.skipTest("gitleaks binary not available: %s" % (p.stderr or p.stdout)[:200])
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        Path(d, "clean.txt").write_text("\n".join(FALSE_POSITIVES) + "\n", encoding="utf-8")
        r = subprocess.run([exe, "dir", d, "--config", str(SHARED), "--no-banner", "--redact"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        Path(d, "clean.txt").unlink()
        Path(d, "real.txt").write_text("\n".join(REAL) + "\n", encoding="utf-8")
        r = subprocess.run([exe, "dir", d, "--config", str(SHARED), "--no-banner", "--redact"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
