"""DL179: the pool supervisor prepares a Wine prefix per agent user and exports POOL_WINE_PREFIX. Fake run/which; no Docker."""
import sys
import unittest
from pathlib import Path

POOL = Path(__file__).resolve().parent.parent / "templates" / "runner-pool"
sys.path.insert(0, str(POOL))
import pool_supervisor as SUP  # noqa: E402

A1 = {"slug": "app1", "user": "r-app1"}
A2 = {"slug": "app2", "user": "r-app2"}
HAS = lambda name: "/usr/bin/" + name  # noqa: E731
NONE = lambda name: None  # noqa: E731


class Prefix(unittest.TestCase):
    def test_prepared_as_the_agent_user(self):
        calls, logs = [], []
        out = SUP.prepare_wine_prefix(A1, "/agents", run=lambda a: calls.append(a) or 0, which=HAS,
                                      exists=lambda p: False, log=logs.append)
        self.assertEqual(out, "/agents/app1/.wine")
        self.assertEqual(len(calls), 1)
        argv = calls[0]
        self.assertEqual(argv[:4], ["runuser", "-u", "r-app1", "--"])
        joined = " ".join(argv)
        for part in ("WINEPREFIX=/agents/app1/.wine", "WINEDEBUG=-all", "timeout 180", "xvfb-run -a wineboot --init", "wineserver -w"):
            self.assertIn(part, joined)
        self.assertEqual(logs, [])

    def test_each_agent_gets_its_own(self):
        calls = []
        for a in (A1, A2):
            SUP.prepare_wine_prefix(a, "/agents", run=lambda x: calls.append(x) or 0, which=HAS, exists=lambda p: False)
        self.assertEqual([c[2] for c in calls], ["r-app1", "r-app2"])
        self.assertIn("/agents/app2/.wine", " ".join(calls[1]))

    def test_skipped_when_system_reg_exists(self):
        calls, seen = [], []
        out = SUP.prepare_wine_prefix(A1, "/agents", run=lambda a: calls.append(a) or 0, which=HAS,
                                      exists=lambda p: seen.append(p) or True)
        self.assertEqual(calls, [])
        self.assertEqual(seen, ["/agents/app1/.wine/system.reg"])
        self.assertEqual(out, "/agents/app1/.wine")

    def test_failure_is_logged_not_raised(self):
        logs = []
        SUP.prepare_wine_prefix(A1, "/agents", run=lambda a: 134, which=HAS, exists=lambda p: False, log=logs.append)
        self.assertEqual(len(logs), 1)
        self.assertIn("r-app1", logs[0])

        def boom(a):
            raise OSError("no runuser")
        SUP.prepare_wine_prefix(A1, "/agents", run=boom, which=HAS, exists=lambda p: False, log=logs.append)
        self.assertEqual(len(logs), 2)

    def test_no_wine_runs_nothing(self):
        calls = []
        out = SUP.prepare_wine_prefix(A1, "/agents", run=lambda a: calls.append(a) or 0, which=NONE, exists=lambda p: False)
        self.assertIsNone(out)
        self.assertEqual(calls, [])


class Env(unittest.TestCase):
    def sup(self, which):
        return SUP.Supervisor("/none.json", "/agents", environ={"POOL_CPUS_INT": "4"}, which=which)

    def test_env_has_prefix_with_wine(self):
        env = self.sup(HAS).agent_env(A1)
        self.assertEqual(env["POOL_WINE_PREFIX"], "/agents/app1/.wine")
        self.assertIn("CI_MAX_PARALLEL", env)

    def test_env_without_wine(self):
        self.assertNotIn("POOL_WINE_PREFIX", self.sup(NONE).agent_env(A1))

    def test_runner_still_starts_after_a_failed_prefix(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "agents.json"
            f.write_text(json.dumps({"agents": [A1]}))
            started = []
            sup = SUP.Supervisor(str(f), d, spawn=lambda a: started.append(a["slug"]) or type("P", (), {"poll": lambda s: None})(),
                                 ensure=lambda a: SUP.prepare_wine_prefix(a, d, run=lambda x: 1, which=HAS, exists=lambda p: False,
                                                                          log=lambda m: None) is not None or True)
            sup.tick()
        self.assertEqual(started, ["app1"])


class Dockerfile(unittest.TestCase):
    def test_layer_packages_unchanged(self):
        df = (POOL / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("dotnet-sdk-8.0 wine wine64 xvfb xauth msitools", df)


if __name__ == "__main__":
    unittest.main()
