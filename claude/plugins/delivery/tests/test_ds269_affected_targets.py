"""DS269: a pull request proves only the targets its changes affect (DL-125)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import _helpers  # noqa: F401  (puts scripts on the path)

SD = Path(__file__).resolve().parent.parent / "templates" / "shared" / "scripts" / "delivery"
sys.path.insert(0, str(SD))
import affected_targets as A  # noqa: E402
import lifecycle_release_check as R  # noqa: E402
import delivery_doctor as D  # noqa: E402

WIN = {"os": "windows", "distro": None, "arch": "x64", "package": "msi", "inputs": ["installer/windows/**"]}
DEB = {"os": "linux", "distro": "ubuntu-lts", "arch": "x64", "package": "deb", "inputs": ["installer/linux/**"]}
LC = {"targets": [WIN, DEB], "no_target": ["docs/**"]}


def names(changed, lc=LC):
    return A.decide(changed, lc)["targets"]


class MapTests(unittest.TestCase):
    def test_one_target(self):
        self.assertEqual(names(["installer/windows/a.wxs"]), ["windows/x64/msi"])

    def test_no_target_path_selects_none(self):
        self.assertEqual(names(["docs/a.md"]), [])
        self.assertEqual(names(["docs/a.md", "installer/linux/x"]), ["ubuntu-lts/x64/deb"])

    def test_unknown_path_selects_all(self):
        self.assertEqual(len(names(["src/lib.rs"])), 2)
        self.assertEqual(len(names(["installer/windows/a", "src/lib.rs"])), 2)

    def test_shared_paths_select_all(self):
        for p in ("docs/design-system/lifecycle.json", "scripts/lifecycle/fetch.sh", "scripts/delivery/pass_records.py",
                  "packaging/app.spec", ".github/workflows/lifecycle.yml"):
            self.assertEqual(len(names([p])), 2, p)

    def test_empty_change_and_forced_select_all(self):
        self.assertEqual(len(names([])), 2)
        self.assertEqual(len(A.decide(["docs/a.md"], LC, True)["targets"]), 2)

    def test_target_without_inputs_always_affected(self):
        lc = {"targets": [dict(WIN, inputs=[]), DEB], "no_target": ["docs/**"]}
        self.assertEqual(names(["docs/a.md"], lc), ["windows/x64/msi"])

    def test_unmapped_and_scaffold(self):
        self.assertEqual(A.unmapped(["docs/a.md", "src/a.rs", "installer/linux/x"], LC), ["src/a.rs"])
        old = {"targets": [{"os": "windows", "distro": None, "arch": "x64", "package": "msi"}]}
        new = A.scaffold(old)
        self.assertTrue(new["targets"][0]["inputs"])
        self.assertIn("no_target", new)
        self.assertNotIn("inputs", old["targets"][0])


class CliTests(unittest.TestCase):
    def run_cli(self, *args):
        d = tempfile.mkdtemp()
        f = Path(d) / "lifecycle.json"
        f.write_text(json.dumps(LC))
        r = subprocess.run([sys.executable, str(SD / "affected_targets.py"), "--lifecycle", str(f), *args],
                           capture_output=True, text=True)
        return r.returncode, r.stdout

    def test_lane_run_flag(self):
        code, out = self.run_cli("lane", "--lane", "windows", "installer/linux/x")
        self.assertEqual(code, 0)
        self.assertIn("run=false", out)
        self.assertIn("run=true", self.run_cli("lane", "--lane", "ubuntu-lts", "installer/linux/x")[1])

    def test_unreadable_base_runs_everything(self):
        code, out = self.run_cli("lane", "--lane", "windows", "--base", "no-such-ref-xyz")
        self.assertEqual(code, 0)
        self.assertIn("run=true", out)


class ReleaseCheckTests(unittest.TestCase):
    def test_unaffected_without_result_or_record_is_named(self):
        targets = [WIN, DEB]
        res = {("windows", "x64", "msi"): {"status": "pass"}}
        problems = R.check_lanes(targets, res, None, "main", {R.target_key(DEB)})
        self.assertEqual(len(problems), 1)
        self.assertIn("not affected", problems[0])
        self.assertIn("pass record", problems[0])

    def test_unaffected_record_from_a_branch_is_refused(self):
        rec = {"status": "pass", "source": "record", "record_branch": "feature", "key": "k", "shard": "s"}
        problems = R.check_lanes([DEB], {("ubuntu-lts", "x64", "deb"): rec}, lambda r: "k", "main", {R.target_key(DEB)})
        self.assertIn("refused", problems[0])

    def test_unaffected_set_from_changed_file(self):
        d = Path(tempfile.mkdtemp())
        (d / "lc.json").write_text(json.dumps(LC))
        (d / "ch.txt").write_text("installer/windows/a\n")
        off = R.unaffected_keys(str(d / "lc.json"), [WIN, DEB], None, str(d / "ch.txt"))
        self.assertEqual(off, {R.target_key(DEB)})
        self.assertEqual(R.unaffected_keys(str(d / "lc.json"), [WIN, DEB], None, None), set())


class DoctorTests(unittest.TestCase):
    def repo(self, files):
        d = Path(tempfile.mkdtemp())
        subprocess.run(["git", "init", "-q"], cwd=d, check=True)
        for rel, text in files.items():
            (d / rel).parent.mkdir(parents=True, exist_ok=True)
            (d / rel).write_text(text)
        subprocess.run(["git", "add", "-A"], cwd=d, check=True)
        return d

    def test_warns_for_unmapped_path_only(self):
        d = self.repo({"docs/design-system/lifecycle.json": json.dumps(LC), "docs/a.md": "x",
                       "installer/linux/a": "x", "src/a.rs": "x"})
        ok, msg, items = D.check_affected_targets(str(d), {})
        self.assertTrue(ok)
        self.assertIn("src/a.rs", msg)
        self.assertNotIn("installer/linux/a", msg)
        self.assertEqual(items[0]["status"], "warn")

    def test_quiet_when_all_mapped_or_no_lifecycle(self):
        d = self.repo({"docs/design-system/lifecycle.json": json.dumps(LC), "installer/linux/a": "x"})
        self.assertIsNone(D.check_affected_targets(str(d), {}))
        self.assertIsNone(D.check_affected_targets(str(self.repo({"a": "x"})), {}))

    def test_session_line(self):
        d = self.repo({"docs/design-system/lifecycle.json": json.dumps(LC), "src/a.rs": "x"})
        line = A.hook_line(str(d))
        self.assertIn("DL-125", line)
        self.assertIn("1 tracked path maps", line)
        self.assertEqual(A.hook_line(str(self.repo({"a": "x"}))), "")


if __name__ == "__main__":
    unittest.main()
