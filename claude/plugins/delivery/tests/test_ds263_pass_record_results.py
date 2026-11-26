"""DS263 (DL-118): pass records as lane results (`to-result`), the release check that accepts them, and
`copy-to-main`. A local bare git repository is the remote; no network."""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

DELIVERY = Path(__file__).resolve().parent.parent / "templates" / "shared" / "scripts" / "delivery"
sys.path.insert(0, str(DELIVERY))
import pass_records as P  # noqa: E402


def load(name):
    spec = importlib.util.spec_from_file_location(name, DELIVERY / (name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


R = load("lifecycle_release_check")
ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
TARGETS = [{"os": "windows", "distro": None, "arch": "x64", "package": "msi"}]
TABLE = {"shards": [
    {"id": "win-msi", "os": "windows", "inputs": ["app"], "commands": ["echo lane"]},
    {"id": "no-inputs", "os": "windows", "commands": ["echo lane"]}]}


def git(cwd, *args):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env={**os.environ, **ENV})
    assert r.returncode == 0, (args, r.stderr)
    return r.stdout.strip()


def quiet(fn, *a):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        return fn(*a)


class Results(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="ds263-"))
        self.addCleanup(shutil.rmtree, self.base, True)
        self.remote, self.work = self.base / "remote.git", self.base / "work"
        subprocess.run(["git", "init", "-q", "--bare", str(self.remote)], check=True)
        subprocess.run(["git", "init", "-q", str(self.work)], check=True)
        git(self.work, "checkout", "-q", "-b", "main")
        (self.work / "scripts" / "delivery").mkdir(parents=True)
        (self.work / "app").mkdir()
        (self.work / "app" / "a.txt").write_text("a1")
        (self.work / "scripts" / "delivery" / "ci-shards.json").write_text(json.dumps(TABLE))
        git(self.work, "add", "-A")
        git(self.work, "commit", "-q", "-m", "c1")
        git(self.work, "remote", "add", "origin", str(self.remote))
        git(self.work, "push", "-q", "origin", "main")
        self.table = P.load_table(str(self.work), "scripts/delivery/ci-shards.json")
        self.lc = self.base / "lifecycle.json"
        self.lc.write_text(json.dumps({"product": "Demo", "targets": TARGETS}))
        self.res = self.base / "results"
        self.res.mkdir()

    def key(self, shard="win-msi"):
        return P.inputs_key(str(self.work), self.table, shard)[0]

    def record(self, as_branch, state="success", shard="win-msi"):
        rec = P.make_record(shard, self.key(shard), state, "abc", as_branch)
        ok, msg = P.write(str(self.work), "origin", P.RECORDS_BRANCH, as_branch, rec)
        self.assertTrue(ok, msg)

    def to_result(self, shard="win-msi", out=None):
        out = out or str(self.res / "windows.json")
        return quiet(P.main, ["to-result", "--shard", shard, "--out", out, "--lane", "windows", "--arch", "x64",
                              "--package", "msi", "--root", str(self.work)])

    def release(self):
        return quiet(R.main, ["check", "--lifecycle", str(self.lc), "--results", str(self.res), "--release",
                              "--root", str(self.work)])

    def edit_app(self):
        (self.work / "app" / "a.txt").write_text("a2")
        git(self.work, "add", "-A")
        git(self.work, "commit", "-q", "-m", "c2")

    # to-result
    def test_hit_writes_a_pass_result_and_the_release_check_accepts_it(self):
        self.record("main")
        self.assertEqual(self.to_result(), 0)
        r = json.loads((self.res / "windows.json").read_text())
        self.assertEqual((r["status"], r["source"], r["record_branch"], r["key"]),
                         ("pass", "record", "main", self.key()))
        self.assertEqual(self.release(), 0)

    def test_miss_exits_1_and_writes_nothing(self):
        self.assertEqual(self.to_result(), 1)
        self.assertFalse((self.res / "windows.json").exists())
        self.assertEqual(self.release(), 1)

    def test_record_of_another_branch_is_a_miss(self):
        self.record("feature")
        self.assertEqual(self.to_result(), 1)

    def test_failed_record_is_a_miss(self):
        self.record("main", state="failure")
        self.assertEqual(self.to_result(), 1)

    def test_changed_inputs_change_the_key_so_the_lane_runs(self):
        self.record("main")
        self.edit_app()
        self.assertEqual(self.to_result(), 1)

    def test_a_lane_with_no_inputs_always_runs(self):
        self.assertIsNone(self.key("no-inputs"))
        self.assertEqual(self.to_result("no-inputs"), 1)

    # the release check refuses
    def test_release_check_refuses_a_result_with_another_key(self):
        self.record("main")
        self.assertEqual(self.to_result(), 0)
        self.edit_app()          # the PR now has another key; the old result is stale
        self.assertEqual(self.release(), 1)

    def test_release_check_refuses_a_record_from_another_branch(self):
        self.record("main")
        self.assertEqual(self.to_result(), 0)
        f = self.res / "windows.json"
        r = json.loads(f.read_text())
        r["record_branch"] = "feature"
        f.write_text(json.dumps(r))
        self.assertEqual(self.release(), 1)

    def test_release_check_refuses_a_record_result_with_no_shard_or_table(self):
        f = self.res / "windows.json"
        f.write_text(json.dumps({"lane": "windows", "arch": "x64", "package": "msi", "status": "pass",
                                 "source": "record", "key": "k", "record_branch": "main"}))
        self.assertEqual(self.release(), 1)

    def test_a_real_lane_result_still_passes(self):
        (self.res / "windows.json").write_text(json.dumps(
            {"lane": "windows", "arch": "x64", "package": "msi", "status": "pass", "failed": []}))
        self.assertEqual(self.release(), 0)

    # copy-to-main
    def test_copy_to_main_copies_success_records_only(self):
        self.record("pr-1")
        rec = P.make_record("win-msi", "f" * 64, "failure", "abc", "pr-1")
        P.write(str(self.work), "origin", P.RECORDS_BRANCH, "pr-1", rec)
        self.assertEqual(self.to_result(), 1)  # nothing on main yet
        code = quiet(P.main, ["copy-to-main", "--from-branch", "pr-1", "--root", str(self.work)])
        self.assertEqual(code, 0)
        self.assertEqual(self.to_result(), 0)
        self.assertEqual(self.release(), 0)
        paths = [p for p, _ in P.list_records(str(self.work), "origin", P.RECORDS_BRANCH)]
        self.assertTrue(any(p.startswith("main/win-msi/") for p in paths))
        self.assertFalse(any(("f" * 64) in p and p.startswith("main/") for p in paths))
        copied = P.read_file(str(self.work), "origin", P.RECORDS_BRANCH, "main/win-msi/%s.json" % self.key())
        self.assertEqual((copied["branch"], copied["copied_from"], copied["state"]), ("main", "pr-1", "success"))

    def test_copy_to_main_twice_adds_nothing_and_a_record_of_main_stays(self):
        self.record("pr-1")
        n, err = P.copy_to_main(str(self.work), "origin", P.RECORDS_BRANCH, "pr-1", "main")
        self.assertEqual((n, err), (1, None))
        n, err = P.copy_to_main(str(self.work), "origin", P.RECORDS_BRANCH, "pr-1", "main")
        self.assertEqual((n, err), (0, None))

    def test_copy_to_main_without_a_records_branch_or_from_main_is_a_no_op(self):
        self.assertEqual(P.copy_to_main(str(self.work), "origin", P.RECORDS_BRANCH, "pr-1", "main"), (0, None))
        self.assertEqual(P.copy_to_main(str(self.work), "origin", P.RECORDS_BRANCH, "main", "main"), (0, None))

    def test_copy_to_main_needs_from_branch(self):
        self.assertEqual(quiet(P.main, ["copy-to-main", "--root", str(self.work)]), 2)


if __name__ == "__main__":
    unittest.main()
