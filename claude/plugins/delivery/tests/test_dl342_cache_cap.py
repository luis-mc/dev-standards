"""DL342: the per-runner build cache cap (rust_ci) and the pool-side sweep and doctor warnings."""
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from _helpers import make_root  # noqa: F401  (puts the scripts folder on sys.path)
import delivery_runner_pool as P

RC = Path(__file__).resolve().parents[1] / "templates" / "rust" / "scripts" / "delivery" / "rust_ci.py"
sys.path.insert(0, str(RC.parent))
spec = importlib.util.spec_from_file_location("rust_ci_dl342", RC)
rust_ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rust_ci)

GB = 1024 ** 3
REPO = "owner/app"


def put(path, size, mtime=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    if mtime:
        os.utime(path.parent, (mtime, mtime))
        os.utime(path, (mtime, mtime))


class RustCiCap(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.run_dir = self.tmp / "runner"
        self.run_dir.mkdir()

    def key(self, name, mtime, **files):
        k = self.run_dir / name
        for rel, size in files.items():
            put(k / rel.replace("__", "/"), size)
        os.utime(k, (mtime, mtime))
        return k

    def test_oversized_current_key_is_cleaned(self):
        cur = self.key("cur", 5000, debug__incremental__a=900, debug__deps__b=700)
        msgs = rust_ci.enforce_cap(self.run_dir, cur, 500)
        self.assertEqual(len(msgs), 1)
        self.assertIn("all content of cur", msgs[0])
        self.assertTrue(cur.is_dir())
        self.assertEqual(rust_ci._tree_size(cur), 0)

    def test_incremental_only_when_that_is_enough(self):
        cur = self.key("cur", 5000, debug__incremental__a=900, debug__deps__b=100)
        msgs = rust_ci.enforce_cap(self.run_dir, cur, 500)
        self.assertEqual(len(msgs), 1)
        self.assertIn("incremental folders of cur", msgs[0])
        self.assertTrue((cur / "debug" / "deps" / "b").exists())
        self.assertFalse((cur / "debug" / "incremental").exists())

    @unittest.skipIf(os.name == "nt", "flock is POSIX only")
    def test_current_key_in_use_is_kept(self):
        import fcntl
        cur = self.key("cur", 5000, debug__big=900)
        lock = cur / "debug" / ".cargo-lock"
        lock.write_bytes(b"")
        fd = os.open(str(lock), os.O_RDWR)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            msgs = rust_ci.enforce_cap(self.run_dir, cur, 500)
        finally:
            os.close(fd)
        self.assertEqual(msgs, [])
        self.assertTrue((cur / "debug" / "big").exists())

    @unittest.skipIf(os.name == "nt", "flock is POSIX only")
    def test_total_is_under_the_cap_after_prune(self):
        old = self.key("old", 1000, d__f=400)
        newer = self.key("newer", 2000, d__f=400)
        cur = self.key("cur", 3000, d__f=400)
        cap = 500
        rust_ci.prune_target_cache(self.run_dir, cur, cap)
        rust_ci.enforce_cap(self.run_dir, cur, cap)
        total = sum(rust_ci._tree_size(p) for p in self.run_dir.iterdir())
        self.assertLessEqual(total, cap)
        self.assertFalse(old.exists())
        self.assertFalse(newer.exists())
        self.assertTrue(cur.exists())

    def test_under_cap_removes_nothing(self):
        cur = self.key("cur", 3000, d__f=100)
        self.assertEqual(rust_ci.enforce_cap(self.run_dir, cur, 500), [])


class Probe(P.Probe):
    platform = "win32"

    def __init__(self, tools, busy=(), free=(50 * GB, 100 * GB), cap=None, docker=None):
        self.tools, self.busy, self.free, self.docker, self.calls = tools, set(busy), free, docker, []
        self.mdir = tempfile.mkdtemp()
        if cap:
            Path(self.mdir, "machine.json").write_text(json.dumps({"tool_cache_cap_gb": cap}))

    def machine_dir(self):
        return self.mdir

    def gh_json(self, args):
        return {"runners": [{"name": n, "busy": True} for n in self.busy]}, None

    def cache_sweep(self, tools_dir, runner, cap_bytes, remove):
        return P.sweep_runner_cache(self.tools, runner, cap_bytes, remove)

    def disk_usage(self, path):
        return self.free

    def sh(self, argv, input=None, timeout=60):
        self.calls.append(argv)
        if argv[:2] == ["docker", "exec"] and self.docker is not None:
            return 0, json.dumps(self.docker) + "\n"
        return 0, ""


WIN = P.windows_registry_entry("main", REPO, "host1-app", "svc", "ci-app", "C:/actions-runners/app")
LIN = {"slug": "app", "user": "r-app", "repo": REPO, "private": True}


class PoolSweep(unittest.TestCase):
    def setUp(self):
        self.tools = Path(tempfile.mkdtemp())

    def fill(self, runner):
        put(self.tools / "cargo-target" / runner / "k_old" / "f", 600, 1000)
        put(self.tools / "cargo-target" / runner / "k_new" / "f", 600, 3000)
        put(self.tools / "other-cache" / runner / "e_mid" / "f", 600, 2000)

    def test_windows_runner_sweeps_oldest_first_across_categories(self):
        self.fill("host1-app")
        rows = P.sweep_pool_caches(Probe(self.tools), "main", [WIN], cap_gb=1000 / GB)
        self.assertEqual(rows[0]["os"], "windows")
        names = [os.path.basename(x[0]) for x in rows[0]["removed"]]
        self.assertEqual(names, ["k_old", "e_mid"])
        self.assertTrue((self.tools / "cargo-target" / "host1-app" / "k_new").exists())
        self.assertIn("host1-app removed 2 entries", P.sweep_lines(rows, 1)[0])

    def test_busy_runner_is_not_touched(self):
        self.fill("host1-app")
        rows = P.sweep_pool_caches(Probe(self.tools, busy=["host1-app"]), "main", [WIN], cap_gb=1000 / GB)
        self.assertEqual(rows[0]["status"], "busy")
        self.assertTrue((self.tools / "cargo-target" / "host1-app" / "k_old").exists())

    def test_other_runner_is_not_swept(self):
        self.fill("other-runner")
        rows = P.sweep_pool_caches(Probe(self.tools), "main", [WIN], cap_gb=1000 / GB)
        self.assertEqual(rows[0]["removed"], [])
        self.assertTrue((self.tools / "cargo-target" / "other-runner" / "k_old").exists())

    def test_linux_agent_runs_in_the_container(self):
        res = {"size": 5 * GB, "removed": [["/ci-tools/cargo-target/main-app/k1", GB]]}
        pr = Probe(self.tools, docker=res)
        rows = P.sweep_pool_caches(pr, "main", [LIN], cap_gb=1)
        ex = [c for c in pr.calls if c[:2] == ["docker", "exec"]][0]
        self.assertIn("pool-main-pool-1", ex)
        self.assertIn("main-app", ex)
        self.assertEqual(rows[0]["runner"], "main-app")
        self.assertEqual(rows[0]["removed"], res["removed"])

    def test_cap_comes_from_machine_json(self):
        self.assertEqual(P.tool_cache_cap_gb(Probe(self.tools)), 30.0)
        self.assertEqual(P.tool_cache_cap_gb(Probe(self.tools, cap=12)), 12.0)

    def test_doctor_warns_over_cap_and_low_disk(self):
        self.fill("host1-app")
        got = []
        pr = Probe(self.tools, cap=1000 / GB, free=(5 * GB, 100 * GB))
        P._cache_checks(lambda i, s, d: got.append((i, s, d)), pr, "main", [WIN])
        d = {i: (s, t) for i, s, t in got}
        self.assertEqual(d["cache-cap"][0], "warn")
        self.assertIn("host1-app", d["cache-cap"][1])
        self.assertEqual(d["cache-disk"][0], "warn")
        self.assertTrue((self.tools / "cargo-target" / "host1-app" / "k_old").exists())  # the doctor deletes nothing

    def test_doctor_ok_when_small_and_roomy(self):
        got = []
        P._cache_checks(lambda i, s, d: got.append((i, s)), Probe(self.tools), "main", [WIN])
        self.assertEqual(dict(got), {"cache-cap": "ok", "cache-disk": "ok"})


if __name__ == "__main__":
    unittest.main()
