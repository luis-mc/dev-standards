"""DL295: rust_scope.py (crate graph and scope) and the rust_ci.py target cache and package args."""
import contextlib
import hashlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "templates"
sys.path.insert(0, str(BASE / "shared" / "scripts" / "delivery"))
sys.path.insert(0, str(BASE / "rust" / "scripts" / "delivery"))
import rust_ci  # noqa: E402
import rust_scope  # noqa: E402

REL = r"^release/.+"


def write(path, text=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_ws(root, parent="crates", members=("core", "svc", "app", "solo")):
    write(root / "Cargo.toml", '[workspace]\nmembers = ["%s/*"]\n' % parent)
    cfg = {
        "core": '[package]\nname = "acme-core"\n',
        "svc": '[package]\nname = "acme-svc"\n[dependencies]\nacme-core = { workspace = true }\n',
        "app": '[package]\nname = "acme-app"\n[dependencies.acme-svc]\npath = "../svc"\n',
        "solo": '[package]\nname = "acme-solo"\n[target.\'cfg(unix)\'.dependencies]\nserde = "1"\n',
    }
    for m in members:
        write(root / parent / m / "Cargo.toml", cfg[m])
        write(root / parent / m / "src" / "lib.rs", "")


class Scope(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        make_ws(self.root)

    def d(self, changed, event="pull_request", head="feature/x"):
        return rust_scope.decide(self.root, event, head, changed, REL)

    def test_graph(self):
        names, deps = rust_scope.build_graph(self.root)
        self.assertEqual(names["crates/core"], "acme-core")
        self.assertEqual(deps["crates/svc"], {"crates/core"})
        self.assertEqual(deps["crates/app"], {"crates/svc"})
        self.assertEqual(deps["crates/solo"], set())

    def test_transitive_dependents(self):
        r = self.d(["crates/core/src/lib.rs"])
        self.assertEqual((r["run"], r["full"]), (True, False))
        self.assertEqual(r["crates"], "acme-app acme-core acme-svc")

    def test_leaf_only(self):
        self.assertEqual(self.d(["crates/app/src/lib.rs"])["crates"], "acme-app")
        self.assertEqual(self.d(["crates/solo/src/lib.rs"])["crates"], "acme-solo")

    def test_workspace_wide_is_full(self):
        for p in ("Cargo.lock", "Cargo.toml", "rust-toolchain.toml", ".cargo/config.toml",
                  "deny.toml", "scripts/delivery/rust_ci.py", ".github/workflows/ci.yml"):
            r = self.d(["crates/core/src/lib.rs", p])
            self.assertTrue(r["full"], p)
            self.assertEqual(r["crates"], "")

    def test_push_and_release_are_full(self):
        self.assertTrue(self.d([], event="push")["full"])
        r = self.d(["docs/a.md"], head="release/1.2")
        self.assertEqual((r["run"], r["full"]), (True, True))

    def test_unreadable_diff_is_full(self):
        r = self.d(None)
        self.assertEqual((r["run"], r["full"]), (True, True))

    def test_no_rust_path_skips(self):
        r = self.d(["docs/a.md", "package.json"])
        self.assertEqual((r["run"], r["full"], r["crates"]), (False, False, ""))

    def test_unknown_member_folder_is_full(self):
        write(self.root / "crates" / "fresh" / "src" / "lib.rs", "")
        r = self.d(["crates/fresh/src/lib.rs"])
        self.assertTrue(r["run"] and r["full"])

    def test_members_under_apps(self):
        root = Path(tempfile.mkdtemp())
        make_ws(root, parent="apps")
        r = rust_scope.decide(root, "pull_request", "x", ["apps/svc/src/lib.rs"], REL)
        self.assertEqual(r["crates"], "acme-app acme-svc")

    def test_config_head_re(self):
        cfg = self.root / "ci-scope.json"
        write(cfg, '{"release_pr": {"head_re": "^ship/"}}')
        self.assertEqual(rust_scope.release_re_from(cfg), "^ship/")
        self.assertEqual(rust_scope.release_re_from(self.root / "none.json"), rust_scope.DEFAULT_RELEASE_RE)

    def test_cli_writes_outputs(self):
        out = self.root / "out.txt"
        old = dict(os.environ)
        os.environ["GITHUB_OUTPUT"] = str(out)
        os.environ["RUST_CI_ROOT"] = str(self.root)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                rust_scope.main(["--event", "push", "--head-ref", "main", "--github-output"])
        finally:
            os.environ.clear()
            os.environ.update(old)
        text = out.read_text()
        self.assertIn("run=true", text)
        self.assertIn("full=true", text)
        self.assertIn("crates=\n", text)


class Cache(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "proj"
        write(self.root / "rust-toolchain.toml", '[toolchain]\nchannel = "1.90.0"\n')
        write(self.root / "Cargo.lock", "one")
        self.old = dict(os.environ)
        for k in ("CARGO_TARGET_DIR", "DELIVERY_NO_TARGET_CACHE", "RUST_CRATES", "RUST_TARGET_CAP_GB"):
            os.environ.pop(k, None)
        os.environ["CI_TOOLS_DIR"] = str(self.tmp / "cache")
        os.environ["RUNNER_NAME"] = "runner 1/x"

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.old)

    def quiet(self, fn, *a):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*a)

    def test_key_changes_with_lock(self):
        k1 = rust_ci.cache_key(self.root)
        self.assertEqual(k1, "1.90.0-" + hashlib.sha256(b"one").hexdigest()[:16])
        write(self.root / "Cargo.lock", "two")
        self.assertNotEqual(k1, rust_ci.cache_key(self.root))
        (self.root / "Cargo.lock").unlink()
        self.assertEqual(rust_ci.cache_key(self.root), "1.90.0-nolock")

    def test_env_sets_dir_and_sanitises_runner(self):
        env = self.quiet(rust_ci.target_cache_env, self.root)
        p = Path(env["CARGO_TARGET_DIR"])
        self.assertTrue(p.is_dir())
        self.assertEqual(p.parent.name, "runner_1_x")
        self.assertEqual(p.parent.parent.name, "cargo-target")

    def test_opt_out_and_preset(self):
        os.environ["DELIVERY_NO_TARGET_CACHE"] = "1"
        self.assertEqual(rust_ci.target_cache_env(self.root), {})
        del os.environ["DELIVERY_NO_TARGET_CACHE"]
        os.environ["CARGO_TARGET_DIR"] = "/somewhere"
        self.assertEqual(rust_ci.target_cache_env(self.root), {})

    def test_problem_falls_back(self):
        (self.root / "rust-toolchain.toml").unlink()
        self.assertEqual(self.quiet(rust_ci.target_cache_env, self.root), {})

    def keys(self, n):
        run = self.tmp / "runner"
        run.mkdir()
        out = []
        for i in range(n):
            k = run / ("k%d" % i)
            write(k / "debug" / "f.bin", "x" * 1000)
            os.utime(k, (1000 + i, 1000 + i))
            out.append(k)
        return run, out

    @unittest.skipIf(os.name == "nt", "no fcntl on Windows: every key counts as in use, so nothing is pruned")
    def test_prune_keeps_current_and_newest_other(self):
        run, ks = self.keys(5)
        removed = rust_ci.prune_target_cache(run, ks[1], 1500)
        self.assertEqual(sorted(removed), ["k0", "k2", "k3"])
        self.assertTrue(ks[1].exists() and ks[4].exists())

    def test_prune_cap_not_reached(self):
        run, ks = self.keys(4)
        self.assertEqual(rust_ci.prune_target_cache(run, ks[3], 10 ** 9), [])
        self.assertTrue(all(k.exists() for k in ks))

    @unittest.skipIf(os.name == "nt", "flock is POSIX only")
    def test_prune_skips_key_in_use(self):
        import fcntl
        run, ks = self.keys(4)
        lock = ks[0] / "debug" / ".cargo-lock"
        write(lock, "")
        fd = os.open(str(lock), os.O_RDWR)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            removed = rust_ci.prune_target_cache(run, ks[3], 1)
        finally:
            os.close(fd)
        self.assertNotIn("k0", removed)
        self.assertTrue(ks[0].exists())
        self.assertEqual(sorted(removed), ["k1"])  # k2 is the newest other key

    def test_crate_args(self):
        self.assertEqual(rust_ci.crate_args(), ["--workspace"])
        os.environ["RUST_CRATES"] = "  "
        self.assertEqual(rust_ci.crate_args(), ["--workspace"])
        os.environ["RUST_CRATES"] = "a b"
        self.assertEqual(rust_ci.crate_args(), ["-p", "a", "-p", "b"])

    def test_cargo_commands(self):
        calls = []
        orig = rust_ci.cmd_run
        rust_ci.cmd_run = lambda root, cmd: calls.append(cmd) or 0
        try:
            os.environ["RUST_CI_CARGO"] = "cargo"
            rust_ci.cmd_cargo(self.root, "fmt", [])
            rust_ci.cmd_cargo(self.root, "clippy", [])
            os.environ["RUST_CRATES"] = "a b"
            rust_ci.cmd_cargo(self.root, "fmt", [])
            rust_ci.cmd_cargo(self.root, "clippy", [])
            rust_ci.cmd_cargo(self.root, "test", ["--lib"])
        finally:
            rust_ci.cmd_run = orig
        self.assertEqual(calls[0], ["cargo", "fmt", "--all", "--check"])
        self.assertIn("--workspace", calls[1])
        self.assertEqual(calls[2], ["cargo", "fmt", "-p", "a", "-p", "b", "--check"])
        self.assertEqual(calls[3][-3:], ["--", "-D", "warnings"])
        self.assertIn("-p", calls[3])
        self.assertEqual(calls[4], ["cargo", "test", "--locked", "-p", "a", "-p", "b", "--lib"])


if __name__ == "__main__":
    unittest.main()
