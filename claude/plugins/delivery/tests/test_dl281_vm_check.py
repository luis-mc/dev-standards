"""DL281: vm_check.py and the VM cache folder made by prepare_kvm. Fakes only; no KVM, no network."""
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent / "templates"
sys.path.insert(0, str(ROOT / "shared" / "scripts" / "delivery"))
sys.path.insert(0, str(ROOT / "runner-pool"))
import vm_check as V  # noqa: E402
import pool_supervisor as S  # noqa: E402

BSD = "SHA256 (img-1.qcow2) = %s\n"
SPEC = {"base_url": "http://x/", "checksum_url": "http://x/SUM", "checksum_format": "bsd", "algo": "sha256",
        "pattern": "img-*.qcow2", "user": "u"}


class FakeResp:
    def __init__(self, data):
        self.data, self.pos = data, 0

    def read(self, n=-1):
        if n < 0:
            n = len(self.data)
        chunk = self.data[self.pos:self.pos + n]
        self.pos += n
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Proc:
    def __init__(self):
        self.killed = False

    def poll(self):
        return None if not self.killed else 0

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        return 0


class Tmp(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.cache = self._t.name


class KeyTests(Tmp):
    def test_base_key_changes_with_checksum_and_packages(self):
        a = V.base_key("aa", ["x", "y"])
        self.assertEqual(a, V.base_key("aa", ["y", "x"]))
        self.assertNotEqual(a, V.base_key("bb", ["x", "y"]))
        self.assertNotEqual(a, V.base_key("aa", ["x"]))

    def test_snap_key_changes_with_qemu_cpu_mem_cpus(self):
        a = V.snap_key("k", "q1", "cpu", 1024, 2)
        self.assertEqual(a, V.snap_key("k", "q1", "cpu", 1024, 2))
        for other in (("k2", "q1", "cpu", 1024, 2), ("k", "q2", "cpu", 1024, 2), ("k", "q1", "cpu2", 1024, 2),
                      ("k", "q1", "cpu", 2048, 2), ("k", "q1", "cpu", 1024, 4)):
            self.assertNotEqual(a, V.snap_key(*other))

    def test_parse_checksums(self):
        self.assertEqual(V.parse_checksums(BSD % "AB12", "bsd", "img-*.qcow2"), ("img-1.qcow2", "ab12"))
        self.assertEqual(V.parse_checksums("ff  *a.img\n", "sums", "a.img"), ("a.img", "ff"))
        with self.assertRaises(V.VmError):
            V.parse_checksums("ff  b.img\n", "sums", "a.img")

    def test_cache_dir_order(self):
        self.assertEqual(V.cache_dir("/a", {"VM_CACHE": "/b"}), "/a")
        self.assertEqual(V.cache_dir(None, {"VM_CACHE": "/b"}), "/b")
        self.assertEqual(V.cache_dir(None, {}, writable=lambda p: True), V.SHARED_CACHE)
        self.assertTrue(V.cache_dir(None, {}, writable=lambda p: False).endswith(os.path.join(".cache", "vm-check")))


class ImageTests(Tmp):
    def fetch(self, data, digest):
        def opener(url, timeout=60):
            return FakeResp((BSD % digest).encode() if url.endswith("SUM") else data)
        return opener

    def test_download_once_then_redownload_on_new_checksum(self):
        d1, d2 = b"one", b"two"
        calls = []
        h1, h2 = hashlib.sha256(d1).hexdigest(), hashlib.sha256(d2).hexdigest()
        with mock.patch.object(V, "http_open", lambda u, timeout=60: (calls.append(u), self.fetch(d1, h1)(u))[1]):
            p1, _ = V.ensure_image(self.cache, "d", SPEC)
            V.ensure_image(self.cache, "d", SPEC)
        self.assertEqual(len([c for c in calls if not c.endswith("SUM")]), 1)
        with mock.patch.object(V, "http_open", self.fetch(d2, h2)):
            p2, _ = V.ensure_image(self.cache, "d", SPEC)
        self.assertNotEqual(p1, p2)
        self.assertEqual(Path(p2).read_bytes(), d2)

    def test_bad_checksum_leaves_nothing(self):
        with mock.patch.object(V, "http_open", self.fetch(b"data", "0" * 64)):
            with self.assertRaises(V.VmError):
                V.ensure_image(self.cache, "d", SPEC)
        self.assertEqual(os.listdir(os.path.join(self.cache, "images")), [])


@unittest.skipIf(V.fcntl is None, "needs fcntl (Linux)")
class LockTests(Tmp):
    def test_prepare_takes_the_lock_around_the_build(self):
        events = []
        real = V.fcntl.flock

        def flock(f, op):
            events.append(op)
            return real(f, op)
        with mock.patch.object(V.fcntl, "flock", flock), \
                mock.patch.object(V, "http_open", ImageTests.fetch(self, b"x", hashlib.sha256(b"x").hexdigest())):
            V.ensure_image(self.cache, "d", SPEC)
        self.assertEqual(events, [V.fcntl.LOCK_EX, V.fcntl.LOCK_UN])

    def test_second_caller_finds_the_file_and_builds_nothing(self):
        built = []
        path = os.path.join(self.cache, "bases")
        os.makedirs(path)

        @mock.patch.object(V, "ensure_image", lambda c, d, s: (os.path.join(c, "img"), "cs"))
        @mock.patch.object(V, "ensure_ssh_key", lambda c: ("k", "pub"))
        def go():
            target = os.path.join(path, "d-%s.qcow2" % V.base_key("cs", []))
            Path(target).write_bytes(b"x")
            with mock.patch.object(V, "boot_and_wait_off", lambda *a: built.append(1)):
                return V.ensure_base(self.cache, "d", SPEC, [])
        go()
        self.assertEqual(built, [])


class VmTests(Tmp):
    def make(self, resume, ssh_results=None):
        self.cmds = []
        proc = Proc()
        self.proc = proc
        base = os.path.join(self.cache, "base")
        snap = os.path.join(self.cache, "snap")
        Path(base).write_bytes(b"b")
        Path(snap).write_bytes(b"s")

        def sh(argv, input=None, timeout=None):
            self.cmds.append((argv, input))
            return 0, ""

        def spawn(argv):
            self.qemu = argv
            sock = argv[argv.index("-monitor") + 1].split(",")[0][len("unix:"):]  # Windows paths have a colon
            Path(sock).write_text("")
            return proc
        patches = [mock.patch.object(V, "sh", sh), mock.patch.object(V, "spawn", spawn),
                   mock.patch.object(V, "monitor_cmd", lambda *a, **k: ""), mock.patch.object(V, "sleep", lambda s: None)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        return V.Vm(self.cache, "d", SPEC, base, snap, "seed", "key", resume=resume)

    def test_overlay_deleted_and_qemu_killed(self):
        vm = self.make(False)
        with vm:
            work = vm.work
            self.assertTrue(os.path.isdir(work))
        self.assertFalse(os.path.exists(work))
        self.assertTrue(self.proc.killed)
        self.assertNotIn("-loadvm", self.qemu)

    def test_overlay_deleted_on_exception(self):
        vm = self.make(False)
        work = None
        with self.assertRaises(RuntimeError):
            with vm:
                work = vm.work
                raise RuntimeError("boom")
        self.assertFalse(os.path.exists(work))
        self.assertTrue(self.proc.killed)

    def test_cleanup_when_boot_fails(self):
        vm = self.make(False)
        with mock.patch.object(V, "sh", lambda argv, input=None, timeout=None: (1 if argv[0] == "ssh" else 0, "")):
            vm.timeout = -1
            with self.assertRaises(V.VmError):
                vm.__enter__()
        self.assertIsNone(vm.work)
        self.assertTrue(self.proc.killed)

    def test_resume_sets_clock_and_reseeds(self):
        vm = self.make(True)
        with mock.patch.object(V, "now", lambda: 1700000000.4):
            with vm:
                pass
        self.assertIn("-loadvm", self.qemu)
        cmds = [c[0][-1] for c in self.cmds]
        self.assertIn("sudo date -s @1700000000", cmds)
        seed = [c for c in self.cmds if c[0][-1] == "sudo tee /dev/urandom >/dev/null"]
        self.assertEqual(len(seed), 1)
        self.assertEqual(len(seed[0][1]), 256)

    def test_no_resume_no_clock_set(self):
        vm = self.make(False)
        with vm:
            pass
        self.assertFalse(any("date -s" in c[0][-1] for c in self.cmds))


class SelinuxTests(unittest.TestCase):
    def test_verdicts(self):
        self.assertIsNone(V.selinux_verdict("Enforcing\n", []))
        self.assertIn("Permissive", V.selinux_verdict("Permissive", []))
        line = "type=AVC msg=audit(1): avc:  denied  { read } for pid=1"
        why = V.selinux_verdict("Enforcing", V.count_avc("ok\n%s\n" % line))
        self.assertIn("1 AVC", why)
        self.assertIn(line, why)

    def run_selinux(self, mode, avc):
        class FakeVm:
            timings = {}
            def __init__(s): s.log = []
            def __enter__(s): return s
            def __exit__(s, *a): return False
            def copy(s, a, b): s.log.append(("copy", b))
            def ssh(s, cmd, input=None, timeout=None):
                s.log.append(cmd)
                if cmd == "getenforce": return 0, mode
                if cmd == "sudo semodule -l": return 0, "x\t1.0\n"
                if "ausearch" in cmd: return 0, avc
                return 0, ""
        fake = FakeVm()
        args = V.build_parser().parse_args(["selinux", "--distro", "d", "--install", "a/x.rpm", "--module", "a/x.pp"])
        with mock.patch.object(V, "open_vm", lambda a, d: fake):
            import io, contextlib
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = V.cmd_selinux(args, {})
        return code, out.getvalue(), fake.log

    def test_pass(self):
        code, out, log = self.run_selinux("Enforcing", "<no matches>\n")
        self.assertEqual(code, 0)
        self.assertIn("sudo dnf -y install /tmp/x.rpm", log)
        self.assertIn("sudo semodule -i /tmp/x.pp", log)

    def test_permissive_fails(self):
        code, out, _ = self.run_selinux("Permissive", "")
        self.assertEqual(code, 1)
        self.assertIn("not Enforcing", out)

    def test_avc_fails_with_lines(self):
        line = "type=AVC msg=audit(1): avc:  denied  { write } for pid=2"
        code, out, _ = self.run_selinux("Enforcing", line + "\n")
        self.assertEqual(code, 1)
        self.assertIn(line, out)


class PruneTests(Tmp):
    def test_keeps_newest_per_distro(self):
        d = os.path.join(self.cache, "bases")
        os.makedirs(d)
        for i, name in enumerate(["f-" + "a" * 16, "f-" + "b" * 16, "f-" + "c" * 16, "r-" + "a" * 16]):
            p = os.path.join(d, name + ".qcow2")
            Path(p).write_bytes(b"x")
            os.utime(p, (1000 + i, 1000 + i))
        stale = os.path.join(d, "f-x.qcow2.tmp-1")
        Path(stale).write_bytes(b"x")
        os.utime(stale, (1, 1))
        args = V.build_parser().parse_args(["--cache", self.cache, "prune"])
        import io, contextlib
        with contextlib.redirect_stdout(io.StringIO()):
            V.cmd_prune(args)
        self.assertEqual(sorted(os.listdir(d)), ["f-%s.qcow2" % ("c" * 16), "r-%s.qcow2" % ("a" * 16)])


class MemoryTests(Tmp):
    def test_warns_when_short(self):
        Path(self.cache, "memory.max").write_text(str(2 * V.GIB))
        Path(self.cache, "memory.current").write_text(str(V.GIB))
        with mock.patch.object(V, "log", lambda m: None):
            self.assertIsNotNone(V.warn_memory(1024, self.cache))
        Path(self.cache, "memory.current").write_text("0")
        self.assertIsNone(V.warn_memory(512, self.cache))
        Path(self.cache, "memory.max").write_text("max")
        self.assertIsNone(V.warn_memory(1024, self.cache))


class PrepareKvmCacheTests(unittest.TestCase):
    def test_cache_dir_has_group_and_mode(self):
        runs = []
        S.prepare_kvm({"user": "r-a"}, {"POOL_KVM": "1"}, run=runs.append, gid_of=lambda: 108,
                      group_name=lambda g: "kvm", isdir=lambda p: True, vm_cache=True)
        self.assertIn(["install", "-d", "-o", "root", "-g", "kvm", "-m", "2775", "/ci-tools/vm-cache"], runs)
        self.assertIn(["chmod", "2775", "/ci-tools/vm-cache"], runs)

    def test_no_volume_no_folder(self):
        runs = []
        S.prepare_kvm({"user": "r-a"}, {"POOL_KVM": "1"}, run=runs.append, gid_of=lambda: 108,
                      group_name=lambda g: "kvm", isdir=lambda p: False, vm_cache=True)
        self.assertEqual(runs, [["usermod", "-aG", "kvm", "r-a"]])


@unittest.skipUnless(os.environ.get("VM_CHECK_REAL") == "1", "needs real /dev/kvm; set VM_CHECK_REAL=1")
class RealTests(unittest.TestCase):
    def test_doctor(self):
        args = V.build_parser().parse_args(["doctor"])
        self.assertEqual(V.cmd_doctor(args), 0)


if __name__ == "__main__":
    unittest.main()
