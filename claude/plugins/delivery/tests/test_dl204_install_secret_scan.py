"""DL204: nothing the installer writes trips the pre-commit secret pattern or gitleaks."""
import re
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

import _helpers  # noqa: F401

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "templates" / "shared" / "scripts" / "delivery"))
import delivery_ci_install as INS
import branch_gate as BG
import delivery_common as dc

try:
    import tomllib
except ImportError:
    tomllib = None

PLUGIN = Path(__file__).resolve().parent.parent
REPO = PLUGIN.parent.parent.parent
HOOK = REPO / "claude/plugins/project-setup/skills/tech-stack-setup/assets/tooling/shared/.githooks/pre-commit"
TOML = PLUGIN / "templates" / "shared" / ".gitleaks.toml"
EXEMPT = [".delivery/ci-install-base/", ".delivery/ci-install-state.json"]


def hook_patterns():
    """The pattern and the skipped line shapes, read from the hook so the two cannot drift."""
    text = HOOK.read_text(encoding="utf-8")
    get = lambda name: re.search(r"^%s='(.*)'$" % name, text, re.M).group(1)
    pat = get("pattern").replace("[[:space:]]", r"\s")
    doc = get("doc_shape").replace("[[:space:]]", r"\s")
    ci = get("ci_dsn")
    return re.compile(pat, re.I), re.compile(doc), re.compile(ci)


def offenders(root):
    pat, doc, ci = hook_patterns()
    bad = []
    for p in sorted(Path(root).rglob("*")):
        if not p.is_file() or "__pycache__" in p.parts or p.suffix == ".md" or ".github" in p.parts:
            continue
        rel = p.relative_to(root).as_posix()
        if any(rel.startswith(e) or rel == e for e in EXEMPT):
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if re.match(r"\s*(//|#|\*)", line) or "secret-scan:ignore" in line:
                continue
            if pat.search(line) and not doc.search(line) and not ci.search(line):
                bad.append("%s:%d: %s" % (rel, n, line.strip()))
    return bad


class GuardTests(unittest.TestCase):
    def test_templates_have_no_secret_shaped_names(self):
        self.assertEqual(offenders(PLUGIN / "templates"), [])

    def test_installer_script_has_none(self):
        self.assertEqual(offenders(PLUGIN / "scripts"), [])

    def test_temp_install_has_none(self):
        for track in INS.TRACKS:
            with self.subTest(track=track), tempfile.TemporaryDirectory() as d:
                out = StringIO()
                with redirect_stdout(out), redirect_stderr(out):
                    code = INS.main(["install", "--track", track, "--root", d])
                self.assertEqual(code, 0, out.getvalue())
                self.assertEqual(offenders(d), [])

    def test_guard_catches_a_bad_name(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "x.py").write_text("by_" + "key = {}\n")
            self.assertEqual(len(offenders(d)), 1)


class AllowlistTests(unittest.TestCase):
    def test_paths_are_exactly_the_two_state_paths(self):
        text = TOML.read_text(encoding="utf-8")
        if tomllib is not None:
            paths = tomllib.loads(text)["allowlist"]["paths"]
        else:
            block = text[text.index("paths = ["):]
            paths = re.findall(r"'''(.*?)'''", block[:block.index("]")])
        self.assertEqual(sorted(paths), sorted([r"^\.delivery/ci-install-base/", r"^\.delivery/ci-install-state\.json$"]))
        rx = [re.compile(p) for p in paths]
        for ok in (".delivery/ci-install-base/scripts/a.py", ".delivery/ci-install-state.json"):
            self.assertTrue(any(r.search(ok) for r in rx), ok)
        for no in (".delivery/config.json", "scripts/a.py", "src/.delivery/ci-install-state.json"):
            self.assertFalse(any(r.search(no) for r in rx), no)

    def test_hook_skips_the_same_paths(self):
        text = HOOK.read_text(encoding="utf-8")
        self.assertIn(".delivery/ci-install-base/*|.delivery/ci-install-state.json) continue", text)


class WorkDirTests(unittest.TestCase):
    def repo(self):
        d = tempfile.mkdtemp(prefix="dl204-")
        for a in (["init", "-q"], ["config", "user.email", "t@example.com"], ["config", "user.name", "t"]):
            subprocess.run(["git"] + a, cwd=d, check=True)
        (Path(d) / "a.txt").write_text("a")
        subprocess.run(["git", "add", "."], cwd=d, check=True)
        subprocess.run(["git", "commit", "-qm", "x"], cwd=d, check=True)
        return Path(d)

    def test_untracked_work_files_are_ignored(self):
        root = self.repo()
        (root / "docs/work/T1").mkdir(parents=True)
        (root / "docs/work/T1/REPORT.md").write_text("r")
        self.assertEqual(BG.ignore_untracked_work(root, dc.dirty_paths(root)), [])

    def test_other_untracked_files_still_count(self):
        root = self.repo()
        (root / "docs/work/T1").mkdir(parents=True)
        (root / "docs/work/T1/REPORT.md").write_text("r")
        (root / "docs/other.md").write_text("o")
        self.assertEqual(BG.ignore_untracked_work(root, dc.dirty_paths(root)), ["docs/other.md"])

    def test_tracked_change_in_work_still_counts(self):
        root = self.repo()
        (root / "docs/work").mkdir(parents=True)
        (root / "docs/work/n.md").write_text("1")
        subprocess.run(["git", "add", "."], cwd=root, check=True)
        subprocess.run(["git", "commit", "-qm", "w"], cwd=root, check=True)
        (root / "docs/work/n.md").write_text("2")
        self.assertEqual(BG.ignore_untracked_work(root, dc.dirty_paths(root)), ["docs/work/n.md"])


if __name__ == "__main__":
    unittest.main()
