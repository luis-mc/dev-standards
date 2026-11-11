"""DL184: pool-run, apply and the doctor agree on the layer image, the template version, the agent name and CI_RUNS_ON.
Fake gh and fake docker; temp machine folder; no Docker."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from _helpers import make_root  # noqa: F401  (sets sys.path)
import test_ci_setup as T
import delivery_ci_setup as S
import delivery_doctor as D
import delivery_runner_pool as P

REPO = "acme/widget"

FAKE_GH = T.FAKE_GH.replace('path = a[1] if a[:1] == ["api"] else ""', '''if a[:2] == ["repo", "view"]:
    print(st.get("repo", ""))
    sys.exit(0 if st.get("repo") else 1)
path = a[1] if a[:1] == ["api"] else ""''')

POOL_OPT1 = {"track": "rust", "options": {"linux": 1},
             "self_hosted": {"machines": [{"name": "main", "os": "linux", "labels": ["self-hosted", "linux"]}],
                             "serial": True, "wait_min": 10, "limits": {"main": {"memory_pct": 85, "cpu_pct": 60}}}}


class FakeDocker(P.Probe):
    """The running container uses image `run_id`; the tag points at `tag_id`; `has` is what the image has."""
    platform = "linux"

    def __init__(self, run_id="sha256:new", tag_id="sha256:new", has=("wine", "xvfb-run", "dotnet"), running=True):
        self.run_id, self.tag_id, self.has, self.running = run_id, tag_id, set(has), running
        self.images_run = []

    def sh(self, argv, input=None, timeout=60):
        if argv[:2] == ["docker", "ps"]:  # the old way: shows a stale id
            return 0, "pool-main-pool-1 sha256:old\n"
        if argv[:2] == ["docker", "inspect"]:
            return (0, self.run_id + "\n") if self.running else (1, "")
        if argv[:3] == ["docker", "image", "inspect"]:
            return 0, self.tag_id + "\n"
        if argv[:2] == ["docker", "run"]:
            image = argv[argv.index("sh") + 1]
            self.images_run.append(image)
            tool = argv[-1].replace("command -v ", "")
            return (0, "") if image != "sha256:old" and tool in self.has else (1, "")
        return 0, ""


class Base(T.Base):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="gh-")
        self.gh = os.path.join(self.tmp, "fake_gh.py")
        Path(self.gh).write_text(FAKE_GH)
        self.state = os.path.join(self.tmp, "state.json")
        self.fake({})
        self.machine = os.path.join(self.tmp, "machine")
        env = mock.patch.dict(os.environ, {"DELIVERY_GH": self.gh, "FAKE_GH_STATE": self.state, "CI_STATUS_TOKEN": "",
                                           "DELIVERY_MACHINE_DIR": self.machine})
        env.start()
        self.addCleanup(env.stop)

    def make_pool(self, name="main"):
        d = os.path.join(self.machine, "pools", name)
        P.write_pool_files(name, {"cpus": 2.0, "mem_gib": 6.0}, dest=d)
        Path(d, ".env").write_text(Path(d, ".env").read_text() + "POOL_LAYERS=windows-packaging\n")
        return d


class LayerImageTests(unittest.TestCase):
    def layers(self, probe):
        out = []
        P._layer_checks(lambda n, s, d: out.append((n, s, d)), probe, "main", {"POOL_LAYERS": "windows-packaging"},
                        "      - ci-tools:/ci-tools\n", [])
        return {n: (s, d) for n, s, d in out}

    def test_uses_the_running_containers_image_not_a_stale_id(self):
        probe = FakeDocker()
        res = self.layers(probe)
        self.assertEqual(res["layer-windows-packaging"][0], "ok")
        self.assertEqual(set(probe.images_run), {"sha256:new"})

    def test_falls_back_to_the_tag_when_no_container_runs(self):
        probe = FakeDocker(running=False, tag_id="sha256:tag")
        self.assertEqual(P.container_image(probe, "main"), "sha256:tag")
        self.assertEqual(self.layers(probe)["layer-windows-packaging"][0], "ok")

    def test_missing_tool_still_fails(self):
        self.assertEqual(self.layers(FakeDocker(has=("wine",)))["layer-windows-packaging"][0], "fail")


class TemplateVersionTests(Base):
    def fstate(self, d):
        return P.pool_files_state(d)

    def test_same_version_identical_files_is_ok(self):
        d = self.make_pool()
        self.assertEqual(self.fstate(d)[0], "ok")
        self.assertEqual(P.read_pool_version(d), P.plugin_version())

    def test_same_version_edited_files_warns_drift(self):
        d = self.make_pool()
        Path(d, "Dockerfile").write_text("FROM edited\n")
        kind, detail = self.fstate(d)
        self.assertEqual(kind, "drift")
        self.assertIn("pool-refresh", detail)

    def test_newer_pool_is_not_drift_for_an_older_doctor(self):
        d = self.make_pool()
        Path(d, "Dockerfile").write_text("FROM newer-template\n")
        Path(d, P.POOL_VERSION_FILE).write_text(json.dumps({"version": "99.0.0"}))
        kind, detail = self.fstate(d)
        self.assertEqual(kind, "newer")
        self.assertIn("99.0.0", detail)
        self.assertIn("update the plugin", detail)
        self.assertNotIn("Run `delivery_ci_setup.py pool-refresh", detail)
        items = D._pool_files_items(P, None)
        self.assertEqual(items[0]["id"], "pool.main.files-current")
        self.assertNotIn("pool-refresh --yes", items[0]["detail"])

    def test_older_pool_with_different_files_is_drift(self):
        d = self.make_pool()
        Path(d, "Dockerfile").write_text("FROM old\n")
        Path(d, P.POOL_VERSION_FILE).write_text(json.dumps({"version": "0.0.1"}))
        self.assertEqual(self.fstate(d)[0], "drift")


class AgentNameAndRunsOnTests(Base):
    def agents(self, name, status="online", labels=("self-hosted", "linux", "X64", "pool-main")):
        return {"api": {"repos/{owner}/{repo}/actions/runners": {"runners": [
            {"id": 1, "name": name, "status": status, "labels": [{"name": n} for n in labels]}]}},
            "repo": REPO, "vars": {"CI_RUNS_ON": '["self-hosted", "linux", "pool-main"]', "CI_SERIAL": "true"}}

    def test_pool_machine_finds_its_pool_agent_and_lists_no_install(self):
        self.make_pool()
        root = self.project(POOL_OPT1)
        self.fake(self.agents(P.pool_agent_name("main", REPO)))
        self.assertEqual(P.pool_agent_name("main", REPO), "main-widget")
        ok, detail = self.ci(root)
        self.assertNotIn("runner:main", detail.replace("load-gate:main", ""))
        self.assertNotIn("no runner named", detail)
        self.assertNotIn("Install the GitHub runner", detail)

    def test_pool_machine_without_its_agent_says_the_pool_name(self):
        self.make_pool()
        root = self.project(POOL_OPT1)
        self.fake(self.agents("someone-else"))
        self.assertIn("no runner named main-widget", self.ci(root)[1])

    def test_pool_item_is_not_an_install_step(self):
        self.make_pool()
        root = self.project(POOL_OPT1)
        item = next(i for i in S.by_hand_items(T.load(root)) if i["id"] == "runner:main")
        self.assertEqual(item["pool"], "main")
        self.assertNotIn("config.sh", " ".join(item["steps"]))

    def test_non_pool_machine_is_unchanged(self):
        root = self.project(T.OPT1)
        items = {i["id"]: i for i in S.by_hand_items(T.load(root))}
        self.assertIn("Install the GitHub runner", items["runner:pc1"]["title"])
        self.assertEqual(json.loads(items["var:CI_RUNS_ON"]["value"]), ["self-hosted", "linux"])
        self.assertNotIn("pool", items["var:CI_RUNS_ON"])

    def test_apply_proposes_the_pool_value(self):
        self.make_pool()
        root = self.project(POOL_OPT1)
        items = {i["id"]: i for i in S.by_hand_items(T.load(root))}
        self.assertEqual(json.loads(items["var:CI_RUNS_ON"]["value"]), ["self-hosted", "linux", "pool-main"])
        self.assertIn("pool-main", items["var:CI_RUNS_ON"]["steps"][0])

    def test_pool_run_and_apply_use_the_same_value(self):
        self.assertEqual(P.expected_runs_on(["self-hosted", "linux"], "main"), ["self-hosted", "linux", "pool-main"])
        self.assertEqual(P.expected_runs_on(["self-hosted", "linux"]), ["self-hosted", "linux"])

    def test_superset_with_the_pool_label_passes_and_plain_value_does_not(self):
        self.make_pool()
        root = self.project(POOL_OPT1)
        exp = ["self-hosted", "linux", "pool-main"]
        self.assertTrue(P.runs_on_satisfied('["self-hosted","linux","pool-main","X64"]', exp, "main"))
        self.assertFalse(P.runs_on_satisfied('["self-hosted","linux"]', exp, "main"))
        self.assertFalse(P.runs_on_satisfied('["self-hosted","linux","extra"]', ["self-hosted", "linux"]))
        st = self.agents("main-widget")
        st["vars"]["CI_RUNS_ON"] = '["self-hosted","linux"]'
        self.fake(st)
        self.assertIn("CI_RUNS_ON is", self.ci(root)[1])


class EndToEndTests(Base):
    def test_pool_setup_then_apply_then_doctor_is_clean(self):
        d = self.make_pool()
        self.assertEqual(P.pool_files_state(d)[0], "ok")
        root = self.project(POOL_OPT1)
        st = {"api": {"repos/{owner}/{repo}/actions/runners": {"runners": [
            {"id": 1, "name": P.pool_agent_name("main", REPO), "status": "online",
             "labels": [{"name": n} for n in ("self-hosted", "linux", "X64", "pool-main", "repo-widget")]}]}},
            "repo": REPO, "vars": {"CI_RUNS_ON": json.dumps(P.expected_runs_on(["self-hosted", "linux"], "main")),
                                   "CI_SERIAL": "true"}}
        self.fake(st)
        ok, detail = self.ci(root)
        self.assertNotIn("runner:main", detail.replace("load-gate:main", ""))
        self.assertNotIn("var:CI_RUNS_ON", detail)
        files = D._pool_files_items(P, None)
        self.assertEqual([i["status"] for i in files], ["ok"])
        res = {}
        probe = FakeDocker()
        P._layer_checks(lambda n, s, dd: res.update({n: s}), probe, "main", {"POOL_LAYERS": "windows-packaging"},
                        "      - ci-tools:/ci-tools\n", [])
        self.assertEqual(res["layer-windows-packaging"], "ok")


if __name__ == "__main__":
    unittest.main()
