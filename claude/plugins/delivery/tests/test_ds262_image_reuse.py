"""DS262 (DL-117): image_reuse.py with a fake registry command."""
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

DELIVERY = Path(__file__).resolve().parent.parent / "templates" / "shared" / "scripts" / "delivery"
SNIPPET = Path(__file__).resolve().parent.parent / "templates" / "ci-snippets" / "image-reuse.yml"

spec = importlib.util.spec_from_file_location("image_reuse", DELIVERY / "image_reuse.py")
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)

FAKE = '''
import json, os, sys
reg = json.load(open(os.environ["FAKE_REGISTRY"]))
tag = sys.argv[1]
if tag not in reg:
    sys.stderr.write("not found\\n")
    sys.exit(1)
fmt = sys.argv[3]
if "Manifest.Digest" in fmt:
    print(reg[tag]["digest"])
else:
    print(json.dumps({"architecture": "amd64", "config": {"Labels": reg[tag].get("labels", {})}}))
'''
DIGEST = "sha256:" + "a" * 64


class Reuse(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="ds262-"))
        self.addCleanup(shutil.rmtree, self.d, True)
        (self.d / "images" / "base").mkdir(parents=True)
        (self.d / "images" / "base" / "Dockerfile").write_text("FROM scratch\n")
        (self.d / "images" / "base" / "setup.sh").write_text("echo hi\n")
        self.cfg = {"image": "ghcr.io/o/base", "inputs": ["images/base"], "tools": {"node": "22.1.0"},
                    "builder_ref": "refs/heads/main"}
        self.cfgfile = self.d / "image-inputs.json"
        self.write_cfg()
        (self.d / "fake.py").write_text(FAKE)
        self.regfile = self.d / "registry.json"
        self.regfile.write_text("{}")
        import os
        os.environ["FAKE_REGISTRY"] = str(self.regfile)
        self.addCleanup(os.environ.pop, "FAKE_REGISTRY", None)
        self.cmd = "%s %s" % (Path(sys.executable).as_posix(), (self.d / "fake.py").as_posix())

    def write_cfg(self):
        self.cfgfile.write_text(json.dumps(self.cfg))

    def key(self):
        return R.compute_key(self.d, R.load_config(self.cfgfile))[0]

    def registry(self, **tags):
        self.regfile.write_text(json.dumps(tags))

    def call(self, action, key, *extra):
        return R.main([action, "--config", str(self.cfgfile), "--key", key, "--inspect-cmd", self.cmd, *extra])

    # key
    def test_key_is_stable_and_hex(self):
        k = self.key()
        self.assertRegex(k, r"^[0-9a-f]{64}$")
        self.assertEqual(k, self.key())

    def test_key_changes_with_a_file_byte(self):
        k = self.key()
        (self.d / "images" / "base" / "setup.sh").write_text("echo ho\n")
        self.assertNotEqual(k, self.key())

    def test_key_changes_with_a_tool_version(self):
        k = self.key()
        self.cfg["tools"] = {"node": "22.1.1"}
        self.write_cfg()
        self.assertNotEqual(k, self.key())

    def test_key_changes_with_a_new_file_and_ignores_outside_files(self):
        k = self.key()
        (self.d / "other.txt").write_text("x")
        self.assertEqual(k, self.key())
        (self.d / "images" / "base" / "new.txt").write_text("x")
        self.assertNotEqual(k, self.key())

    def test_no_inputs_means_no_key(self):
        self.cfg["inputs"] = []
        self.write_cfg()
        self.assertIsNone(self.key())
        self.assertEqual(R.main(["key", "--config", str(self.cfgfile), "--root", str(self.d)]), 3)

    def test_inputs_matching_nothing_means_no_key(self):
        self.cfg["inputs"] = ["nope"]
        self.write_cfg()
        self.assertIsNone(self.key())

    def test_key_command(self):
        self.assertEqual(R.main(["key", "--config", str(self.cfgfile), "--root", str(self.d)]), 0)

    # exists and digest, with the fake registry
    def test_missing_tag_is_a_miss(self):
        self.assertEqual(self.call("exists", "k1"), 1)
        self.assertEqual(self.call("digest", "k1"), 1)

    def test_tag_built_by_main_is_a_hit(self):
        self.registry(**{"ghcr.io/o/base:k1": {"digest": DIGEST, "labels": {R.LABEL: "refs/heads/main"}}})
        self.assertEqual(self.call("exists", "k1"), 0)
        self.assertEqual(self.call("digest", "k1"), 0)

    def test_tag_built_elsewhere_is_a_miss(self):
        self.registry(**{"ghcr.io/o/base:k1": {"digest": DIGEST, "labels": {R.LABEL: "refs/heads/feature"}}})
        self.assertEqual(self.call("exists", "k1"), 1)

    def test_tag_with_no_label_is_a_miss(self):
        self.registry(**{"ghcr.io/o/base:k1": {"digest": DIGEST}})
        self.assertEqual(self.call("exists", "k1"), 1)

    def test_label_not_checked_when_no_builder_ref(self):
        del self.cfg["builder_ref"]
        self.write_cfg()
        self.registry(**{"ghcr.io/o/base:k1": {"digest": DIGEST}})
        self.assertEqual(self.call("exists", "k1"), 0)

    def test_digest_to_pin(self):
        self.registry(**{"ghcr.io/o/base:k1": {"digest": DIGEST, "labels": {R.LABEL: "refs/heads/main"}}})
        d, why = R.lookup("ghcr.io/o/base", "k1", self.cmd, "refs/heads/main")
        self.assertEqual(d, DIGEST)

    def test_broken_command_is_a_miss_not_a_pass(self):
        d, why = R.lookup("ghcr.io/o/base", "k1", "no-such-command-ds262", "refs/heads/main")
        self.assertIsNone(d)

    def test_bad_input(self):
        self.assertEqual(R.main(["exists", "--config", str(self.d / "gone.json"), "--key", "k"]), 2)
        self.assertEqual(R.main(["exists", "--config", str(self.cfgfile)]), 2)

    def test_snippet_has_the_rules(self):
        t = SNIPPET.read_text(encoding="utf-8")
        for need in ("--no-cache --pull", "type=registry", "packages: write", "builder-ref"):
            self.assertIn(need, t)
        writes = [ln for ln in t.splitlines() if ln.strip().startswith("packages: write")]
        self.assertEqual(len(writes), 1)  # the main-branch job only


if __name__ == "__main__":
    unittest.main()
