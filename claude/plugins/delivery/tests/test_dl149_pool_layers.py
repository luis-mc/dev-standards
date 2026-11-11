"""DL149: the windows-packaging layer, .delivery/pool.apt, the busy refusal, the doctor findings. Fake probe only; no Docker."""
import json
import os
import re
import tempfile
import unittest
from pathlib import Path

from _helpers import make_root  # noqa: F401  (sets sys.path to the scripts folder)
import delivery_runner_pool as P
from test_runner_pool import FakeProbe

POOL = Path(__file__).resolve().parent.parent / "templates" / "runner-pool"


def repo(layers=None, apt=None):
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, ".delivery"))
    if layers is not None:
        Path(d, ".delivery", "config.json").write_text(json.dumps({"pool": {"layers": layers}}))
    if apt is not None:
        Path(d, ".delivery", "pool.apt").write_text(apt)
    return d


class GhProbe(FakeProbe):
    def __init__(self, runners):
        super().__init__()
        self.runners = runners

    def gh_json(self, args):
        return ({"runners": self.runners}, None) if self.runners is not None else (None, "gh refused")


class DockerfileTests(unittest.TestCase):
    def test_layer_is_a_build_arg_off_by_default(self):
        df = (POOL / "Dockerfile").read_text()
        self.assertIn("ARG POOL_LAYERS=\n", df)
        self.assertIn("ARG POOL_APT=\n", df)
        self.assertIn("dotnet-sdk-8.0 wine wine64 xvfb xauth msitools", df)
        self.assertEqual(P.LAYERS["windows-packaging"], "dotnet-sdk-8.0 wine wine64 xvfb xauth msitools")
        comp = (POOL / "compose.yaml").read_text()
        self.assertIn("POOL_LAYERS: ${POOL_LAYERS:-}", comp)
        self.assertIn("POOL_APT: ${POOL_APT:-}", comp)

    def test_env_with_and_without_layer(self):
        probe = FakeProbe()
        with tempfile.TemporaryDirectory() as d:
            os.environ["DELIVERY_MACHINE_DIR"] = d
            try:
                P.write_pool_files("main", {"cpus": 2.0, "mem_gib": 6.0}, dest=os.path.join(d, "pools", "main"))
                rp = P.refresh_plan(probe, "main", [repo()])
                self.assertEqual(rp["changes"].get("POOL_LAYERS", (None, ""))[1], "") if "POOL_LAYERS" in rp["changes"] else None
                rp = P.refresh_plan(probe, "main", [repo(["windows-packaging"], "# c\nlibfoo-dev\n")])
                self.assertNotIn("error", rp)
                self.assertEqual(rp["changes"]["POOL_LAYERS"][1], "windows-packaging")
                self.assertEqual(rp["changes"]["POOL_APT"][1], "libfoo-dev")
            finally:
                os.environ.pop("DELIVERY_MACHINE_DIR", None)


class FragmentTests(unittest.TestCase):
    def test_valid(self):
        names, errs = P.parse_pool_apt("# tools\nlibc++-dev  # c\n\ng++-12\nlibfoo1.2\n")
        self.assertEqual(names, ["libc++-dev", "g++-12", "libfoo1.2"])
        self.assertEqual(errs, [])

    def test_refuses_bad_names(self):
        for bad in ("foo;rm -rf /", "a b", "$(x)", "-oAPT::x", "foo_bar", "a/b"):
            names, errs = P.parse_pool_apt(bad + "\n")
            self.assertEqual(names, [], bad)
            self.assertTrue(errs and "line 1" in errs[0] and errs[0].startswith("refused"), bad)

    def test_unknown_layer_refused(self):
        _l, _a, errs = P.read_pool_layers([repo(["gpu"])])
        self.assertIn('"gpu"', errs[0])

    def test_refresh_plan_error_on_bad_fragment(self):
        probe = FakeProbe()
        with tempfile.TemporaryDirectory() as d:
            os.environ["DELIVERY_MACHINE_DIR"] = d
            try:
                P.write_pool_files("main", {"cpus": 2.0, "mem_gib": 6.0}, dest=os.path.join(d, "pools", "main"))
                rp = P.refresh_plan(probe, "main", [repo(None, "bad name!\n")])
                self.assertIn("refused", rp["error"])
            finally:
                os.environ.pop("DELIVERY_MACHINE_DIR", None)


class BusyTests(unittest.TestCase):
    R = [{"name": "main-app1", "busy": True, "labels": [{"name": "pool-main"}]},
         {"name": "host1-old", "busy": True, "labels": [{"name": "self-hosted"}]}]

    def test_refuses_and_names_the_runner(self):
        ok, msg = P.rebuild_gate(GhProbe(self.R), ["owner/example-app"], "main")
        self.assertFalse(ok)
        self.assertIn("main-app1", msg)
        self.assertNotIn("host1-old", msg)

    def test_force_warns(self):
        ok, msg = P.rebuild_gate(GhProbe(self.R), ["owner/example-app"], "main", force=True)
        self.assertTrue(ok)
        self.assertTrue(msg.startswith("warning"))

    def test_idle_passes_and_unreadable_refuses(self):
        idle = [dict(self.R[0], busy=False)]
        self.assertEqual(P.rebuild_gate(GhProbe(idle), ["owner/example-app"], "main"), (True, ""))
        self.assertFalse(P.rebuild_gate(GhProbe(None), ["owner/example-app"], "main")[0])


class DoctorTests(unittest.TestCase):
    def checks(self, env, compose, repo_paths, sh):
        out = []
        probe = FakeProbe()
        probe.sh = sh
        P._layer_checks(lambda n, s, d: out.append((n, s, d)), probe, "main", env, compose, repo_paths)
        return {n: (s, d) for n, s, d in out}

    COMPOSE = "    volumes:\n      - agents:/agents\n      - ci-tools:/ci-tools\n"

    def test_layer_tools_missing(self):
        def sh(argv, input=None, timeout=60):
            if argv[:2] == ["docker", "inspect"]:  # DL184: the running container's image
                return 0, "sha256:img1\n"
            if "command -v wine" in " ".join(argv):
                return 1, ""
            return 0, ""
        res = self.checks({"POOL_LAYERS": "windows-packaging"}, self.COMPOSE, [repo(["windows-packaging"])], sh)
        self.assertEqual(res["layer-windows-packaging"][0], "fail")
        self.assertIn("wine", res["layer-windows-packaging"][1])
        self.assertEqual(res["tool-cache"][0], "ok")

    def test_cannot_check_without_docker(self):
        res = self.checks({"POOL_LAYERS": "windows-packaging"}, self.COMPOSE, [repo(["windows-packaging"])], lambda *a, **k: None)
        self.assertEqual(res["layer-windows-packaging"][0], "warn")

    def test_stray_dockerfile_and_cache_volume(self):
        r = repo()
        os.makedirs(os.path.join(r, "infra", "runners", "linux"))
        Path(r, "infra", "runners", "linux", "Dockerfile").write_text("FROM ubuntu\n")
        res = self.checks({}, "services: {}\n", [r], lambda *a, **k: None)
        self.assertEqual(res["stray-dockerfile"][0], "fail")
        self.assertIn(".delivery/pool.apt", res["stray-dockerfile"][1])
        self.assertEqual(res["tool-cache"][0], "fail")

    def test_config_vs_env_drift_warns(self):
        res = self.checks({}, self.COMPOSE, [repo(["windows-packaging"])], lambda *a, **k: None)
        self.assertEqual(res["layers-config"][0], "warn")


if __name__ == "__main__":
    unittest.main()
