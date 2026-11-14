"""DL92: pool .env holds RUNNER_SHA256, a changed cap recreates the pool, the sizing floor, the memory-kill report. Fake docker only."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

from _helpers import make_root  # noqa: F401  (sets sys.path to the scripts folder)
import delivery_runner_pool as P
from test_runner_pool import FakeProbe

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "templates" / "shared" / "scripts" / "delivery"))
import ci_watch as W  # noqa: E402

POOL = Path(__file__).resolve().parent.parent / "templates" / "runner-pool"
GiB = 2 ** 30


class EnvShaTests(unittest.TestCase):
    def test_pool_files_write_runner_sha256(self):
        with tempfile.TemporaryDirectory() as d:
            dest = os.path.join(d, "pools", "main")
            P.write_pool_files("main", {"cpus": 2.0, "mem_gib": 6.0}, dest=dest, runner_version="2.400.1", runner_sha256="b" * 64)
            self.assertIn("RUNNER_SHA256=" + "b" * 64, Path(dest, ".env").read_text())

    def test_pinned_version_falls_back_to_the_pinned_sha(self):
        with tempfile.TemporaryDirectory() as d:
            dest = os.path.join(d, "pools", "main")
            P.write_pool_files("main", {"cpus": 2.0, "mem_gib": 6.0}, dest=dest)
            self.assertIn("RUNNER_SHA256=" + P.RUNNER_SHA256, Path(dest, ".env").read_text())

    def test_every_required_compose_variable_is_in_the_written_env(self):
        required = P.compose_required_vars((POOL / "compose.yaml").read_text())
        self.assertIn("RUNNER_SHA256", required)
        with tempfile.TemporaryDirectory() as d:
            dest = os.path.join(d, "pools", "main")
            P.write_pool_files("main", {"cpus": 2.0, "mem_gib": 6.0}, dest=dest)
            keys = {l.split("=")[0] for l in Path(dest, ".env").read_text().splitlines() if "=" in l}
        self.assertTrue(set(required) <= keys, set(required) - keys)


class DockerProbe(P.Probe):
    """Real files in a temp folder; docker is fake."""
    platform = "linux"

    def __init__(self, inspect):
        self.inspect = inspect

    def sh(self, argv, input=None, timeout=60):
        if argv[:2] == ["docker", "inspect"]:
            return (0, self.inspect) if self.inspect is not None else (1, "")
        return 0, ""


def checks(env, inspect="6442450944 2000000000", compose=None):
    with tempfile.TemporaryDirectory() as d:
        pd = Path(d, "pools", "main")
        pd.mkdir(parents=True)
        (pd / "compose.yaml").write_text(compose or (POOL / "compose.yaml").read_text())
        (pd / ".env").write_text(env)
        (pd / "agents.json").write_text('{"agents": []}')
        return {c["id"]: c for c in P.doctor_checks(d, DockerProbe(inspect))}

ENV_OK = "POOL_CPUS=2.0\nPOOL_MEM=6.0g\nRUNNER_SHA256=" + "a" * 64 + "\n"


class DoctorTests(unittest.TestCase):
    def test_missing_required_variable_fails_and_names_it(self):
        c = checks("POOL_CPUS=2.0\nPOOL_MEM=6.0g\n")["pool.main.required-vars"]
        self.assertEqual(c["status"], "fail")
        self.assertIn("RUNNER_SHA256", c["detail"])

    def test_present_variable_is_ok(self):
        self.assertEqual(checks(ENV_OK)["pool.main.required-vars"]["status"], "ok")

    def test_live_cap_matches(self):
        self.assertEqual(checks(ENV_OK)["pool.main.live-cap"]["status"], "ok")

    def test_live_cap_mismatch_fails_with_the_recreate_command(self):
        c = checks(ENV_OK, inspect="536870912 1000000000")["pool.main.live-cap"]
        self.assertEqual(c["status"], "fail")
        self.assertIn("0.50 GiB", c["detail"])
        self.assertIn("docker compose up -d --no-build --force-recreate pool", c["detail"])

    def test_no_container_to_inspect_adds_no_live_check(self):
        self.assertNotIn("pool.main.live-cap", checks(ENV_OK, inspect=None))


class RecreateTests(unittest.TestCase):
    def run_step(self, busy, old_env, new_env):
        probe = FakeProbe()
        envs = iter([old_env, new_env])
        probe.read_text = lambda path: None
        calls = []
        orig_read, orig_run, orig_det, orig_write = P.read_pool_env, P.subprocess.run, P.detect_github, P.write_pool_files
        P.read_pool_env = lambda pr, pool: next(envs)
        P.write_pool_files = lambda *a, **k: "C:/m/pools/main"
        P.detect_github = lambda pr: {"repos": [{"repo": "o/a", "runners": [{"name": "main-app", "os": "Linux", "busy": busy}], "error": None}], "error": None}
        P.subprocess.run = lambda argv, **k: calls.append(argv) or type("R", (), {"returncode": 0, "stderr": ""})()
        try:
            ok, text = P.Executor(probe).run({"action": "pool-files", "pool": "main", "cap": {"cpus": 4, "mem_gib": 7}})
        finally:
            P.read_pool_env, P.subprocess.run, P.detect_github, P.write_pool_files = orig_read, orig_run, orig_det, orig_write
        return ok, text, calls

    def test_changed_cap_and_idle_recreates(self):
        ok, text, calls = self.run_step(False, {"POOL_MEM": "0.5g", "POOL_CPUS": "1"}, {"POOL_MEM": "7g", "POOL_CPUS": "4"})
        self.assertTrue(ok)
        self.assertEqual(calls, [["docker", "compose", "up", "-d", "--no-build", "--force-recreate", "pool"]])
        self.assertIn("recreated", text)

    def test_changed_cap_and_busy_prints_the_command(self):
        ok, text, calls = self.run_step(True, {"POOL_MEM": "0.5g", "POOL_CPUS": "1"}, {"POOL_MEM": "7g", "POOL_CPUS": "4"})
        self.assertEqual(calls, [])
        self.assertIn("By hand", text)
        self.assertIn("--force-recreate pool", text)

    def test_unchanged_cap_does_nothing(self):
        env = {"POOL_MEM": "7g", "POOL_CPUS": "4"}
        self.assertEqual(self.run_step(False, env, dict(env))[2], [])

    def test_unreadable_runners_count_as_busy(self):
        probe = FakeProbe()
        orig = P.detect_github
        P.detect_github = lambda pr: {"repos": [], "error": "gh cannot run"}
        try:
            self.assertTrue(P.Executor(probe).runners_busy())
        finally:
            P.detect_github = orig


class FloorTests(unittest.TestCase):
    def test_small_memory_is_refused_with_a_reason(self):
        res = P.sizing(total_gib=16, used_gib=11.0, cpus=8, docker_gib=None)
        self.assertFalse(res["ok"])
        self.assertIn("below the floor of 4 GiB and 2 CPUs", res["message"])

    def test_one_cpu_is_refused(self):
        res = P.sizing(total_gib=32, used_gib=0, cpus=2, docker_gib=None)
        self.assertFalse(res["ok"])

    def test_a_low_wsl_ceiling_does_not_shrink_the_pool_when_the_machine_has_room(self):
        res = P.sizing(total_gib=32, used_gib=4, cpus=8, docker_gib=2.5)
        self.assertTrue(res["ok"])
        self.assertEqual(res["mem_gib"], 4.0)
        self.assertGreaterEqual(res["wsl"]["memory"], 6)

    def test_enough_room_is_ok(self):
        res = P.sizing(total_gib=32, used_gib=4, cpus=8, docker_gib=None)
        self.assertTrue(res["ok"])
        self.assertGreaterEqual(res["mem_gib"], 4)

    def test_the_pools_db_container_is_not_counted_as_another_container(self):
        probe = P.Probe()
        probe.platform = "linux"

        def sh(argv, input=None, timeout=60):
            if argv[:2] == ["docker", "ps"]:
                return 0, "pool-main-pool-1\t1\tpool-main\npool-main-db-1\t\tpool-main\nother\t\tdemo\n"
            return 0, "pool-main-pool-1\t1GiB / 7GiB\npool-main-db-1\t100MiB / 7GiB\nother\t200MiB / 7GiB\n"
        probe.sh = sh
        out = probe.container_gib()
        self.assertEqual(out["others"], ["other"])
        self.assertAlmostEqual(out["pool"], 1.1, places=1)


class MemoryKillReportTests(unittest.TestCase):
    JOB = {"name": "linux", "conclusion": "failure", "startedAt": "2026-01-01T10:00:00Z", "completedAt": "2026-01-01T10:05:00Z",
           "steps": [{"name": "Install (frozen lockfile)", "conclusion": "failure"}]}

    def test_exit_137_is_a_memory_kill_not_a_lockfile(self):
        note = W.diagnose(self.JOB, "Lockfile is up to date\nProcess completed with exit code 137.", cap="0.5 GiB memory, 1.0 CPUs")
        self.assertIn("killed for memory: the runner's cap is 0.5 GiB memory", note)
        self.assertNotIn("stale", note.lower())

    def test_killed_word_counts(self):
        self.assertIn("killed for memory", W.diagnose(self.JOB, "pnpm install\nKilled\n", cap="unknown"))

    def test_other_failure_has_no_note(self):
        self.assertIsNone(W.diagnose(self.JOB, "Process completed with exit code 1.", cap="x"))

    def test_slow_setup_failure_is_a_start_up_failure(self):
        job = {"steps": [{"name": "Set up runner", "conclusion": "failure"}],
               "startedAt": "2026-01-01T10:00:00Z", "completedAt": "2026-01-01T10:31:00Z"}
        note = W.diagnose(job, "", cap="0.5 GiB memory, 1.0 CPUs")
        self.assertIn("runner start-up failure", note)
        self.assertIn("pool cap (0.5 GiB memory", note)
        self.assertIn("not a lockfile", note)

    def test_quick_setup_failure_has_no_note(self):
        job = {"steps": [{"name": "Set up job", "conclusion": "failure"}],
               "startedAt": "2026-01-01T10:00:00Z", "completedAt": "2026-01-01T10:01:00Z"}
        self.assertIsNone(W.diagnose(job, "", cap="x"))

    def test_unreadable_docker_says_unknown(self):
        orig = W.subprocess.run
        W.subprocess.run = lambda *a, **k: (_ for _ in ()).throw(OSError("no docker"))
        try:
            self.assertEqual(W.pool_cap_text(), "unknown")
        finally:
            W.subprocess.run = orig


if __name__ == "__main__":
    unittest.main()
