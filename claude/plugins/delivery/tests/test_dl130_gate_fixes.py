"""DL130 gate fixes: pre-push node_modules check and two-worktree resolution (DL130, DL137),
docs/work restore (DL131), UTF-8 logs (DL134), C# warning (DL141)."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGINS = HERE.parent.parent
sys.path.insert(0, str(HERE.parent / "templates" / "shared" / "scripts" / "delivery"))
import branch_gate as G  # noqa: E402

HOOK = PLUGINS / "project-setup/skills/tech-stack-setup/assets/tooling/shared/.githooks/pre-push"


def git(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True,
                          env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
                               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}).stdout


def make_repo(tmp):
    repo = Path(tmp) / "app1"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    (repo / ".githooks").mkdir()
    shutil.copy(HOOK, repo / ".githooks" / "pre-push")
    (repo / "scripts" / "delivery").mkdir(parents=True)
    (repo / "package.json").write_text("{}\n")
    (repo / ".gitignore").write_text("node_modules/\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "init")
    return repo


@unittest.skipIf(os.name == "nt" or not shutil.which("sh"), "needs sh")
class PrePushTests(unittest.TestCase):
    def test_missing_node_modules_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp)
            p = subprocess.run(["sh", str(repo / ".githooks" / "pre-push"), "origin", "x"], cwd=repo,
                               input="", capture_output=True, text=True)
            self.assertNotEqual(p.returncode, 0)
            self.assertIn("node_modules is missing in this worktree; run pnpm install --frozen-lockfile here.", p.stderr)

    def test_hook_from_old_worktree_defers_to_current(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp)
            old = Path(tmp) / "old"
            new = Path(tmp) / "new"
            git(repo, "worktree", "add", "-q", "-b", "old", str(old))
            git(repo, "worktree", "add", "-q", "-b", "new", str(new))
            (new / ".githooks" / "pre-push.local").write_text("echo LOCAL-FROM-NEW >&2\n")
            (old / ".githooks" / "pre-push.local").write_text("echo LOCAL-FROM-OLD >&2\n")
            (new / "node_modules").mkdir()
            # core.hooksPath is shared; it names the old worktree's hooks
            p = subprocess.run(["sh", str(old / ".githooks" / "pre-push"), "origin", "x"], cwd=new,
                               input="", capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn("LOCAL-FROM-NEW", p.stderr)
            self.assertNotIn("LOCAL-FROM-OLD", p.stderr)


class GateTests(unittest.TestCase):
    def test_restore_gate_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "app1"
            (repo / "docs" / "work").mkdir(parents=True)
            repo.joinpath("docs/work/a.png").write_text("old")
            git(repo, "init", "-q", "-b", "main")
            git(repo, "add", "-A")
            git(repo, "commit", "-qm", "i")
            repo.joinpath("docs/work/a.png").write_text("new")
            repo.joinpath("docs/work/b.png").write_text("new")
            (repo / "keep.txt").write_text("x")
            touched = G.restore_gate_outputs(repo)
            self.assertEqual(len(touched), 2)
            self.assertEqual(repo.joinpath("docs/work/a.png").read_text(), "old")
            self.assertFalse(repo.joinpath("docs/work/b.png").exists())
            self.assertTrue((repo / "keep.txt").exists())

    def test_decode_cp1252_and_ansi(self):
        data = b"\x1b[31mred\x1b[0m \x96 \x81 caf\xe9"
        text = G.decode_log_bytes(data)
        self.assertNotIn("\x1b", text)
        self.assertIn("red", text)
        self.assertEqual(G.decode_log_bytes("─│".encode("utf-8")), "─│")

    def test_prepare_environment(self):
        G.prepare_environment()
        self.assertEqual(os.environ["PYTHONUTF8"], "1")
        self.assertEqual(os.environ["PYTHONIOENCODING"], "utf-8")
        self.assertEqual(os.environ["FORCE_COLOR"], "0")

    def test_csharp_no_change_no_warning(self):
        self.assertEqual(G.csharp_check(Path("."), ["a.py"]), ([], []))

    def test_csharp_windows_only_warns_on_linux(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "App").mkdir()
            (root / "App" / "App.csproj").write_text("<Project><PropertyGroup><TargetFramework>net8.0-windows</TargetFramework></PropertyGroup></Project>")
            (root / "App" / "A.cs").write_text("class A {}")
            w, f = G.csharp_check(root, ["App/A.cs"], which=lambda n: "/bin/dotnet", system="Linux")
            self.assertEqual(f, [])
            self.assertTrue(w[0].startswith("C# changed, not compiled on Linux"), w)

    def test_csharp_no_dotnet_warns(self):
        w, f = G.csharp_check(Path("."), ["A.cs"], which=lambda n: None, system="Linux")
        self.assertIn("C# changed, not compiled on Linux", w[0])

    def test_csharp_builds_portable_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "L.csproj").write_text("<Project><PropertyGroup><TargetFramework>net8.0</TargetFramework></PropertyGroup></Project>")
            calls = []

            def fake(cmd, **kw):
                calls.append(cmd)
                return subprocess.CompletedProcess(cmd, 1, b"error CS0104: ambiguous", b"")
            w, f = G.csharp_check(root, ["L.csproj"], run=fake, which=lambda n: "dotnet", system="Linux")
            self.assertEqual(w, [])
            self.assertEqual(calls[0][:2], ["dotnet", "build"])
            self.assertIn("CS0104", f[0])


if __name__ == "__main__":
    unittest.main()
