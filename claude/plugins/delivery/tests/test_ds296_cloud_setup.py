"""DS296: cloud bootstrap. No network: the dev-standards checkout and the gitleaks download are local fakes."""
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

import _helpers  # noqa: F401  (puts scripts/ on the path)
import ds_scripts

PLUGIN = Path(__file__).resolve().parent.parent
SHARED = PLUGIN / "templates" / "shared" / "scripts" / "delivery"
HOOK = PLUGIN / "scripts" / "hook_cloud_setup.py"
BRIEF = PLUGIN / "references" / "agent-brief-template.md"
PLAT = {("Linux", "x86_64"): "linux_x64", ("Linux", "aarch64"): "linux_arm64"}.get(
    (os.uname().sysname, os.uname().machine))


def git(*a, cwd=None):
    subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})


def tarball(content=b"#!/bin/sh\necho 8.30.1\n"):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        info = tarfile.TarInfo("gitleaks")
        info.size = len(content)
        info.mode = 0o755
        t.addfile(info, io.BytesIO(content))
    return buf.getvalue()


@unittest.skipUnless(PLAT, "linux only")
class CloudSetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ds296-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = self.tmp / "home"
        self.home.mkdir()
        # the fake dev-standards repository
        self.ds = self.tmp / "ds"
        (self.ds / "claude/plugins/docs/scripts").mkdir(parents=True)
        (self.ds / "claude/plugins/docs/scripts/docs_check.py").write_text("print('ok')\n")
        git("init", "-q", cwd=self.ds)
        git("add", "-A", cwd=self.ds)
        git("commit", "-q", "-m", "x", cwd=self.ds)
        self.sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.ds, capture_output=True, text=True).stdout.strip()
        # the project
        self.proj = self.tmp / "proj"
        d = self.proj / "scripts" / "delivery"
        d.mkdir(parents=True)
        shutil.copy(SHARED / "cloud_setup.sh", d)
        (self.proj / ".delivery").mkdir()
        wf = self.proj / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "dev-standards.yml").write_text(
            "      - uses: actions/checkout@v4\n        with:\n          repository: owner/ds\n"
            "          ref: %s\n          path: .dev-standards-tools\n" % self.sha)
        # the gitleaks fake
        self.archive = tarball()
        self.dl = self.tmp / "dl"
        self.dl.mkdir()
        self.set_pin("8.30.1", hashlib.sha256(self.archive).hexdigest())

    def set_pin(self, version, sha):
        (self.proj / "scripts/delivery/tools.json").write_text(
            json.dumps({"gitleaks": {"version": version, "sha256": {PLAT: sha}}}))
        (self.dl / ("gitleaks_%s_%s.tar.gz" % (version, PLAT))).write_bytes(self.archive)

    def run_setup(self, *args, remote=True):
        env = {**os.environ, "HOME": str(self.home), "DELIVERY_BIN": str(self.home / "bin"),
               "DELIVERY_GITLEAKS_BASE_URL": self.dl.as_uri(), "DEV_STANDARDS_FETCH_URL": str(self.ds)}
        env.pop("CLAUDE_CODE_REMOTE", None)
        if remote:
            env["CLAUDE_CODE_REMOTE"] = "true"
        return subprocess.run(["bash", str(self.proj / "scripts/delivery/cloud_setup.sh"), *args],
                              cwd=self.proj, env=env, capture_output=True, text=True)

    def test_full_run_fetches_installs_and_prints_path(self):
        r = self.run_setup()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("DEV_STANDARDS_SCRIPTS=.dev-standards-tools/claude/plugins/docs/scripts", r.stdout)
        self.assertTrue((self.proj / ".dev-standards-tools/claude/plugins/docs/scripts/docs_check.py").is_file())
        self.assertTrue((self.home / "bin" / "gitleaks").is_file())

    def test_second_run_is_idempotent(self):
        self.assertEqual(self.run_setup().returncode, 0)
        marker = self.proj / ".dev-standards-tools" / "marker"
        marker.write_text("kept")
        r = self.run_setup()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(marker.exists(), "a fetched pin is not fetched again")
        self.assertIn("already installed", r.stderr)

    def test_not_remote_does_nothing_unless_forced(self):
        r = self.run_setup(remote=False)
        self.assertEqual(r.returncode, 0)
        self.assertFalse((self.proj / ".dev-standards-tools").exists())
        self.assertEqual(self.run_setup("--force", remote=False).returncode, 0)
        self.assertTrue((self.proj / ".dev-standards-tools").exists())

    def test_checksum_mismatch_fails_closed(self):
        self.set_pin("8.30.1", "0" * 64)
        r = self.run_setup()
        self.assertEqual(r.returncode, 2)
        self.assertIn("checksum mismatch", r.stderr)
        self.assertFalse((self.home / "bin" / "gitleaks").exists())

    def test_reads_the_pin_from_tools_json(self):
        # Change the pinned version: the script asks for that asset, which the fake does not serve.
        (self.proj / "scripts/delivery/tools.json").write_text(
            json.dumps({"gitleaks": {"version": "9.9.9", "sha256": {PLAT: hashlib.sha256(self.archive).hexdigest()}}}))
        r = self.run_setup()
        self.assertEqual(r.returncode, 2)
        self.assertIn("download failed", r.stderr)
        self.assertIn("9.9.9", r.stderr)
        self.assertFalse((self.home / "bin" / "gitleaks").exists())

    def test_script_has_no_pin_of_its_own(self):
        text = (SHARED / "cloud_setup.sh").read_text()
        pin = json.loads((SHARED / "tools.json").read_text())["gitleaks"]
        self.assertNotIn(pin["version"], text)
        for sha in pin["sha256"].values():
            self.assertNotIn(sha, text)
        for ci in (PLUGIN / "templates").glob("*/.github/workflows/ci.yml"):
            self.assertNotIn(pin["sha256"]["linux_x64"], ci.read_text(), ci)

    def test_missing_workflow_pin_fails(self):
        (self.proj / ".github/workflows/dev-standards.yml").unlink()
        self.assertEqual(self.run_setup().returncode, 2)


class HookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ds296h-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        (self.tmp / ".delivery").mkdir()
        (self.tmp / "scripts/delivery").mkdir(parents=True)

    def run_hook(self, remote, script=None, **env):
        if script is not None:
            (self.tmp / "scripts/delivery/cloud_setup.sh").write_text(script)
        e = {**os.environ, **env}
        e.pop("CLAUDE_CODE_REMOTE", None)
        if remote:
            e["CLAUDE_CODE_REMOTE"] = "true"
        return subprocess.run([sys.executable, str(HOOK)], input=json.dumps({"cwd": str(self.tmp)}),
                              capture_output=True, text=True, env=e)

    def test_local_does_nothing(self):
        r = self.run_hook(False, "echo DEV_STANDARDS_SCRIPTS=x\n")
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_cloud_runs_setup_and_names_path(self):
        r = self.run_hook(True, "echo DEV_STANDARDS_SCRIPTS=some/path\n")
        self.assertEqual(r.returncode, 0)
        ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("DEV_STANDARDS_SCRIPTS=some/path", ctx)

    def test_failure_never_blocks(self):
        r = self.run_hook(True, "echo boom >&2\nexit 2\n")
        self.assertEqual(r.returncode, 0)
        self.assertIn("exited 2", r.stderr)
        self.assertIn("DEV_STANDARDS_SCRIPTS", r.stdout)

    def test_timeout_never_blocks(self):
        r = self.run_hook(True, "sleep 5\n", DELIVERY_CLOUD_SETUP_TIMEOUT="1")
        self.assertEqual(r.returncode, 0)
        self.assertIn("skipped", r.stderr)

    def test_no_script_or_no_delivery_does_nothing(self):
        (self.tmp / "scripts/delivery/cloud_setup.sh").write_text("echo x\n")
        shutil.rmtree(self.tmp / ".delivery")
        self.assertEqual(self.run_hook(True).stdout, "")

    def test_registered_in_hooks_json(self):
        hooks = json.loads((PLUGIN / "hooks/hooks.json").read_text())["hooks"]["SessionStart"]
        self.assertTrue(any("hook_cloud_setup.py" in h["command"] for e in hooks for h in e["hooks"]))


class ResolverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ds296r-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        os.environ.pop("DEV_STANDARDS_SCRIPTS", None)
        self.plugin = self.tmp / "p" / "delivery"
        self.plugin.mkdir(parents=True)

    def mk(self, path):
        path.mkdir(parents=True)
        (path / "docs_check.py").write_text("")
        return str(path)

    def test_cache_then_checkout(self):
        proj = self.tmp / "proj"
        checkout = self.mk(proj / ds_scripts.CHECKOUT)
        self.assertEqual(ds_scripts.resolve(str(proj), str(self.tmp / "h"), str(self.plugin)), checkout)
        cache = self.mk(self.tmp / "h/.claude/plugins/cache/m/luismc-docs/2.0.0/scripts")
        newer = self.mk(self.tmp / "h/.claude/plugins/cache/m/luismc-docs/2.10.0/scripts")
        self.assertEqual(ds_scripts.resolve(str(proj), str(self.tmp / "h"), str(self.plugin)), newer)
        self.assertNotEqual(newer, cache)

    def test_none_when_absent(self):
        self.assertIsNone(ds_scripts.resolve(str(self.tmp), str(self.tmp / "h"), str(self.plugin)))


class BriefTests(unittest.TestCase):
    def test_brief_names_pr_rule_and_scripts_var(self):
        t = BRIEF.read_text(encoding="utf-8")
        self.assertIn("gh pr create", t)
        self.assertIn("$DEV_STANDARDS_SCRIPTS", t)
        self.assertIn("never hand-write change notes", t)


if __name__ == "__main__":
    unittest.main()
