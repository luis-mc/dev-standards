"""DL343: load the kvm module in the Docker VM before the pool starts, and check .wslconfig."""
import unittest

from _helpers import make_root  # noqa: F401  (puts the scripts folder on sys.path)
import delivery_runner_pool as P

NSENTER_TEST = "test"


class Probe(P.Probe):
    platform = "win32"

    def __init__(self, vendor="GenuineIntel", loads=("kvm_intel",), wsl=None, docker=True):
        self.vendor, self.loads, self.wsl, self.docker = vendor, set(loads), wsl, docker
        self.loaded, self.calls = False, []

    def read_text(self, path):
        return self.wsl

    def sh(self, argv, input=None, timeout=60):
        self.calls.append(list(argv))
        if not self.docker:
            return None
        if "vendor_id" in argv:
            return 0, "vendor_id\t: %s\n" % self.vendor
        if "modprobe" in argv:
            if argv[-1] in self.loads:
                self.loaded = True
            return 0, ""
        if "test" in argv:
            return (0 if self.loaded else 1), ""
        return 0, ""

    def modprobes(self):
        return [c[-1] for c in self.calls if "modprobe" in c]


ON = {"POOL_KVM": "1"}


class Autoload(unittest.TestCase):
    def test_missing_then_modprobe_then_ok(self):
        pr = Probe()
        ok, text = P.ensure_kvm(pr, ON)
        self.assertTrue(ok)
        self.assertIn("loaded kvm_intel", text)
        self.assertEqual(pr.modprobes(), ["kvm_intel"])

    def test_amd_vendor_loads_kvm_amd(self):
        pr = Probe(vendor="AuthenticAMD", loads=("kvm_amd",))
        ok, text = P.ensure_kvm(pr, ON)
        self.assertTrue(ok)
        self.assertEqual(pr.modprobes(), ["kvm_amd"])

    def test_the_helper_is_privileged_but_nothing_else_is(self):
        pr = Probe()
        P.ensure_kvm(pr, ON)
        cmd = [c for c in pr.calls if "modprobe" in c][0]
        self.assertEqual(cmd, ["docker", "run", "--rm", "--privileged", "--pid=host", "alpine", "nsenter", "-t", "1", "-m",
                               "--", "modprobe", "kvm_intel"])

    def test_still_missing_names_the_fix(self):
        ok, text = P.ensure_kvm(Probe(loads=()), ON)
        self.assertFalse(ok)
        self.assertIn("nestedVirtualization=true", text)
        self.assertIn(".wslconfig", text)
        self.assertIn("wsl --shutdown", text)

    def test_present_does_nothing(self):
        pr = Probe()
        pr.loaded = True
        self.assertEqual(P.ensure_kvm(pr, ON), (True, ""))
        self.assertEqual(pr.modprobes(), [])

    def test_pool_kvm_unset_does_nothing(self):
        for env in ({}, {"POOL_KVM": ""}, {"POOL_KVM": "0"}):
            pr = Probe()
            self.assertEqual(P.ensure_kvm(pr, env), (True, ""))
            self.assertEqual(pr.calls, [])

    def test_docker_unreadable_does_not_block(self):
        self.assertEqual(P.ensure_kvm(Probe(docker=False), ON), (True, ""))


class Wslconfig(unittest.TestCase):
    def test_missing_line_warns_with_the_line_to_add(self):
        w = P.wslconfig_nested_warning(Probe(wsl="[wsl2]\nmemory=8GB\n"), ON)
        self.assertIn("nestedVirtualization=true", w)

    def test_present_is_quiet(self):
        self.assertEqual(P.wslconfig_nested_warning(Probe(wsl="[wsl2]\nnestedVirtualization=true\n"), ON), "")

    def test_line_in_another_section_does_not_count(self):
        self.assertTrue(P.wslconfig_nested_warning(Probe(wsl="[experimental]\nnestedVirtualization=true\n"), ON))

    def test_no_file_warns(self):
        self.assertTrue(P.wslconfig_nested_warning(Probe(wsl=None), ON))

    def test_pool_kvm_unset_or_not_windows_is_quiet(self):
        self.assertEqual(P.wslconfig_nested_warning(Probe(wsl=""), {}), "")
        pr = Probe(wsl="")
        pr.platform = "linux"
        self.assertEqual(P.wslconfig_nested_warning(pr, ON), "")

    def test_doctor_check_reports_it(self):
        got = []
        P._kvm_checks(lambda i, s, d: got.append((i, s)), Probe(wsl=""), "main", ON, "/x", [])
        self.assertIn(("kvm-wslconfig", "warn"), got)


if __name__ == "__main__":
    unittest.main()
