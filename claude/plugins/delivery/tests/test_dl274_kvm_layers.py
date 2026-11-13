"""DL274: linux-packaging and kvm layers, the optional KVM setting. Fakes only; no Docker, no gh."""
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

from _helpers import make_root  # noqa: F401  (sets sys.path to the scripts folder)
import delivery_runner_pool as P
from test_runner_pool import FakeProbe

POOL = Path(__file__).resolve().parent.parent / "templates" / "runner-pool"
sys.path.insert(0, str(POOL))
import pool_agents as A  # noqa: E402
import pool_supervisor as S  # noqa: E402


class KvmProbe(FakeProbe):
    """Docker answers: host_exit is the exit code of `docker run --device /dev/kvm ... test`."""
    def __init__(self, host_exit=0, container_exit=0, runners=None, files=None):
        super().__init__(files)
        self.host_exit, self.container_exit, self.runners = host_exit, container_exit, runners or []

    def sh(self, argv, input=None, timeout=60):
        self.calls.append((argv, input))
        if argv[:3] == ["docker", "image", "inspect"]:
            return 1, ""
        if argv[:2] == ["docker", "run"] and "--device" in argv:
            return self.host_exit, ""
        if argv[:2] == ["docker", "exec"] and "/dev/kvm" in argv:
            return self.container_exit, ""
        return 0, ""

    def gh_json(self, args):
        return {"runners": self.runners}, None


def checks(probe, env_extra="", agents=True):
    with tempfile.TemporaryDirectory() as root:
        pool = os.path.join(root, "pools", "main")
        os.makedirs(pool)
        Path(pool, "compose.yaml").write_text("services:\n  pool:\n    volumes:\n      - ci-tools:/ci-tools\n")
        Path(pool, ".env").write_text("POOL_CPUS=2\nPOOL_MEM=8g\n" + env_extra)
        Path(pool, "agents.json").write_text('{"agents": [{"slug": "a", "user": "r-a", "repo": "o/a", "private": true}]}' if agents else '{"agents": []}')
        if "COMPOSE_FILE" in env_extra:
            Path(pool, "compose.kvm.yaml").write_text("x\n")
        out = P.doctor_checks(root, probe)
    return {c["id"].split(".", 2)[2]: c for c in out if c["id"].startswith("pool.main.")}


class LayerListTests(unittest.TestCase):
    def test_dockerfile_and_layers_agree(self):
        df = (POOL / "Dockerfile").read_text()
        for layer in ("linux-packaging", "kvm"):
            self.assertIn(layer, P.LAYERS)
            self.assertIn("*,%s,*)" % layer, df)
            for pkg in P.LAYERS[layer].split():
                self.assertIn(pkg, df, "%s missing from the Dockerfile (%s)" % (pkg, layer))
        self.assertIn("policycoreutils-python-utils", df)
        self.assertEqual(P.LAYER_TOOLS["linux-packaging"], ("dpkg-deb", "rpmbuild", "checkmodule", "semodule_package",
                                                          "gpg", "shellcheck", "systemd-analyze", "createrepo_c"))  # DL281
        self.assertEqual(P.LAYER_TOOLS["kvm"], ("qemu-system-x86_64", "cloud-localds", "ssh"))  # DL281: vm_check.py needs ssh

    def test_layers_are_accepted_in_config(self):
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, ".delivery"))
        Path(d, ".delivery", "config.json").write_text('{"pool": {"layers": ["linux-packaging", "kvm"]}}')
        layers, _a, errs = P.read_pool_layers([d])
        self.assertEqual((layers, errs), (["linux-packaging", "kvm"], []))


class ComposeTests(unittest.TestCase):
    def test_base_compose_has_no_devices_and_no_privileged(self):
        base = (POOL / "compose.yaml").read_text()
        self.assertNotIn("devices", base)
        self.assertNotIn("privileged", base)
        self.assertNotIn("kvm", base)

    def test_override_passes_kvm_never_privileged(self):
        kvm = (POOL / "compose.kvm.yaml").read_text()
        self.assertRegex(kvm, r"^\s*-\s*/dev/kvm:/dev/kvm\s*$".replace("^", "(?m)^"))
        self.assertNotRegex(kvm, r"(?m)^\s*privileged:\s*true")

    def test_refresh_unset_writes_no_kvm_keys(self):
        with tempfile.TemporaryDirectory() as d:
            os.environ["DELIVERY_MACHINE_DIR"] = d
            try:
                P.write_pool_files("main", {"cpus": 2.0, "mem_gib": 6.0}, dest=os.path.join(d, "pools", "main"))
                rp = P.refresh_plan(KvmProbe(host_exit=125), "main", [])
                self.assertNotIn("error", rp)
                for k in ("POOL_KVM", "COMPOSE_FILE", "COMPOSE_PATH_SEPARATOR"):
                    self.assertNotIn(k, rp["changes"])
            finally:
                os.environ.pop("DELIVERY_MACHINE_DIR", None)

    def test_refresh_on_sets_compose_file(self):
        with tempfile.TemporaryDirectory() as d:
            os.environ["DELIVERY_MACHINE_DIR"] = d
            try:
                P.write_pool_files("main", {"cpus": 2.0, "mem_gib": 6.0}, dest=os.path.join(d, "pools", "main"))
                rp = P.refresh_plan(KvmProbe(host_exit=0), "main", [], kvm="on")
                self.assertNotIn("error", rp)
                self.assertEqual(rp["changes"]["POOL_KVM"][1], "1")
                self.assertEqual(rp["changes"]["COMPOSE_FILE"][1], "compose.yaml:compose.kvm.yaml")
                envp = os.path.join(d, "pools", "main", ".env")
                P.set_env_values(envp, {k: v[1] for k, v in rp["changes"].items()})
                self.assertIn("COMPOSE_FILE=compose.yaml:compose.kvm.yaml", Path(envp).read_text())
                rp = P.refresh_plan(KvmProbe(host_exit=0), "main", [], kvm="off")
                P.set_env_values(envp, {k: v[1] for k, v in rp["changes"].items()})
                self.assertNotIn("KVM", Path(envp).read_text())
                self.assertNotIn("COMPOSE_FILE", Path(envp).read_text())
            finally:
                os.environ.pop("DELIVERY_MACHINE_DIR", None)

    def test_refresh_refuses_kvm_without_host_kvm(self):
        with tempfile.TemporaryDirectory() as d:
            os.environ["DELIVERY_MACHINE_DIR"] = d
            try:
                dest = os.path.join(d, "pools", "main")
                P.write_pool_files("main", {"cpus": 2.0, "mem_gib": 6.0}, dest=dest)
                rp = P.refresh_plan(KvmProbe(host_exit=125), "main", [], kvm="on")
                self.assertIn("refused", rp["error"])
                self.assertIn("no usable KVM", rp["error"])
                # POOL_KVM=1 already in .env is refused the same way
                with open(os.path.join(dest, ".env"), "a") as f:
                    f.write("POOL_KVM=1\n")
                rp = P.refresh_plan(KvmProbe(host_exit=1), "main", [])
                self.assertIn("refused", rp["error"])
            finally:
                os.environ.pop("DELIVERY_MACHINE_DIR", None)


class HostCheckTests(unittest.TestCase):
    def test_yes_no_and_unknown(self):
        self.assertEqual(P.host_kvm(KvmProbe(0))[0], True)
        ok, why = P.host_kvm(KvmProbe(1))
        self.assertFalse(ok)
        self.assertIn("not readable", why)
        ok, why = P.host_kvm(KvmProbe(125))
        self.assertFalse(ok)
        self.assertIn("not in the Docker VM", why)

    def test_uses_device_flag_without_privileged(self):
        pr = KvmProbe(0)
        P.host_kvm(pr)
        run = [a for a, _ in pr.calls if a[:2] == ["docker", "run"]][0]
        self.assertIn("--device", run)
        self.assertNotIn("--privileged", run)

    def test_msys_path_conversion_is_off_for_docker(self):
        seen = {}
        orig = P.subprocess.run

        def fake(argv, **kw):
            seen["env"] = kw.get("env")
            class R:
                returncode, stdout = 0, ""
            return R()
        P.subprocess.run = fake
        try:
            P.Probe().sh(["docker", "ps"])
            self.assertEqual(seen["env"]["MSYS_NO_PATHCONV"], "1")
            P.Probe().sh(["gh", "x"])
            self.assertIsNone(seen["env"])
        finally:
            P.subprocess.run = orig


class DoctorTests(unittest.TestCase):
    def test_off_reports_host_yes(self):
        c = checks(KvmProbe(0))
        self.assertEqual(c["kvm-host"]["status"], "ok")
        self.assertIn("yes", c["kvm-host"]["detail"])
        self.assertNotIn("kvm-compose", c)

    def test_off_reports_host_no_but_not_a_failure(self):
        c = checks(KvmProbe(125))
        self.assertEqual(c["kvm-host"]["status"], "ok")
        self.assertIn("no", c["kvm-host"]["detail"])

    def test_on_without_host_kvm_fails(self):
        c = checks(KvmProbe(125), "POOL_KVM=1\n")
        self.assertEqual(c["kvm-host"]["status"], "fail")
        self.assertEqual(c["kvm-compose"]["status"], "fail")

    def test_on_ok_and_label_command_printed(self):
        runners = [{"id": 7, "name": "main-a", "labels": [{"name": "linux"}]}]
        c = checks(KvmProbe(0, 0, runners), "POOL_KVM=1\nCOMPOSE_FILE=compose.yaml:compose.kvm.yaml\n",)
        self.assertEqual(c["kvm-container"]["status"], "ok")
        self.assertEqual(c["kvm-label"]["status"], "warn")
        self.assertIn("gh api -X POST repos/o/a/actions/runners/7/labels", c["kvm-label"]["detail"])

    def test_off_with_stale_label_prints_delete(self):
        runners = [{"id": 7, "name": "main-a", "labels": [{"name": "kvm"}]}]
        c = checks(KvmProbe(0, 0, runners))
        self.assertIn("gh api -X DELETE repos/o/a/actions/runners/7/labels/kvm", c["kvm-label"]["detail"])


class LabelTests(unittest.TestCase):
    def test_label_only_when_on_and_usable(self):
        base = ["self-hosted", "linux", "x64", "pool-main", "repo-a"]
        yes = lambda p, m: True  # noqa: E731
        no = lambda p, m: False  # noqa: E731
        self.assertEqual(A.labels_for("main", "a", kvm=False), base)
        self.assertEqual(A.labels_for("main", "a", kvm=True), base + ["kvm"])
        self.assertTrue(A.kvm_usable({"POOL_KVM": "1"}, access=yes, exists=lambda p: True))
        self.assertFalse(A.kvm_usable({}, access=yes, exists=lambda p: True))
        self.assertFalse(A.kvm_usable({"POOL_KVM": "1"}, access=no, exists=lambda p: True))
        self.assertFalse(A.kvm_usable({"POOL_KVM": "1"}, access=yes, exists=lambda p: False))


class SupervisorTests(unittest.TestCase):
    def test_group_comes_from_the_device_gid(self):
        runs = []
        S.prepare_kvm({"user": "r-a"}, {"POOL_KVM": "1"}, run=lambda a: runs.append(a), gid_of=lambda: 994, group_name=lambda g: None)
        self.assertEqual(runs, [["groupadd", "--gid", "994", "kvm"], ["usermod", "-aG", "kvm", "r-a"]])
        runs.clear()
        S.prepare_kvm({"user": "r-a"}, {"POOL_KVM": "1"}, run=lambda a: runs.append(a), gid_of=lambda: 108, group_name=lambda g: "kvm")
        self.assertEqual(runs, [["usermod", "-aG", "kvm", "r-a"]])

    def test_off_does_nothing(self):
        runs = []
        self.assertTrue(S.prepare_kvm({"user": "r-a"}, {}, run=lambda a: runs.append(a), gid_of=lambda: 1))
        self.assertEqual(runs, [])


if __name__ == "__main__":
    unittest.main()
