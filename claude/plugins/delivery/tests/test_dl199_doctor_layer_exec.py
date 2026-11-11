"""DL199: the pool doctor probes layer tools with `docker exec` in the running container; a docker error is a warn, not a missing tool.
Fake probe; no Docker."""
import unittest

from _helpers import make_root  # noqa: F401  (sets sys.path)
import delivery_runner_pool as P

TOOLS = ("wine", "xvfb-run", "dotnet")


class Fake(P.Probe):
    platform = "linux"

    def __init__(self, running=True, has=TOOLS, run_rc=None, exec_rc=None):
        self.running, self.has, self.run_rc, self.exec_rc = running, set(has), run_rc, exec_rc
        self.calls = []

    def sh(self, argv, input=None, timeout=60):
        self.calls.append(argv[:3])
        if argv[:2] == ["docker", "inspect"]:
            if not self.running:
                return 1, ""
            return 0, ("true\n" if "State.Running" in argv[3] else "sha256:img\n")
        if argv[:3] == ["docker", "image", "inspect"]:
            return 0, "sha256:tag\n"
        if argv[:2] in (["docker", "exec"], ["docker", "run"]):
            forced = self.exec_rc if argv[1] == "exec" else self.run_rc
            if forced is not None:
                return forced, ""
            return (0, "") if argv[-1].replace("command -v ", "") in self.has else (1, "")
        return 0, ""


def layer(probe):
    out = []
    P._layer_checks(lambda n, s, d: out.append((n, s, d)), probe, "main", {"POOL_LAYERS": "windows-packaging"}, "", [])
    return {n: (s, d) for n, s, d in out}["layer-windows-packaging"]


class LayerExec(unittest.TestCase):
    def test_exec_used_and_ok(self):
        p = Fake()
        st, detail = layer(p)
        self.assertEqual(st, "ok")
        self.assertEqual(detail, "the image has wine, xvfb-run, dotnet")
        self.assertIn(["docker", "exec", "pool-main-pool-1"], p.calls)
        self.assertNotIn(["docker", "run", "--rm"], p.calls)

    def test_one_missing_fails(self):
        st, detail = layer(Fake(has=("wine", "dotnet")))
        self.assertEqual(st, "fail")
        self.assertIn("xvfb-run", detail)
        self.assertNotIn("wine,", detail)

    def test_docker_run_error_is_warn(self):
        st, detail = layer(Fake(running=False, run_rc=125))
        self.assertEqual(st, "warn")
        self.assertIn("cannot probe", detail)
        self.assertIn("125", detail)

    def test_exec_error_is_warn(self):
        st, detail = layer(Fake(exec_rc=126))
        self.assertEqual(st, "warn")
        self.assertIn("cannot probe", detail)

    def test_no_container_uses_docker_run_on_tag(self):
        p = Fake(running=False)
        st, _ = layer(p)
        self.assertEqual(st, "ok")
        self.assertIn(["docker", "run", "--rm"], p.calls)
        self.assertNotIn(["docker", "exec", "pool-main-pool-1"], p.calls)


if __name__ == "__main__":
    unittest.main()
