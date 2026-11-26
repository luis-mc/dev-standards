"""DS261 (DL-116): changed_areas.py and ci_areas_check.py."""
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

DELIVERY = Path(__file__).resolve().parent.parent / "templates" / "shared" / "scripts" / "delivery"
SNIPPET = Path(__file__).resolve().parent.parent / "templates" / "ci-snippets" / "ci-areas-pattern.yml"


def load(name):
    import sys
    sys.path.insert(0, str(DELIVERY))
    spec = importlib.util.spec_from_file_location(name, DELIVERY / (name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


A = load("changed_areas")
K = load("ci_areas_check")

CMAP = {
    "areas": {"code": ["src/**"], "web": ["apps/web/**"], "e2e": ["e2e/**"], "image": ["images/**"],
              "installer": ["installer/**"], "config": [".nvmrc", ".gitignore"]},
    "docs": ["docs/**", "**/*.md"],
    "all": [".github/**", "package.json", ".delivery/**"],
}

# A fixture tree: every path and where it must go.
TREE = {
    "src/a/b.py": ("areas", ["code"]),
    "apps/web/index.ts": ("areas", ["web"]),
    "e2e/login.spec.ts": ("areas", ["e2e"]),
    "images/base/Dockerfile": ("areas", ["image"]),
    "installer/app.wxs": ("areas", ["installer"]),
    ".nvmrc": ("areas", ["config"]),
    "docs/guide.md": ("docs", ""),
    "README.md": ("docs", ""),
    ".github/workflows/ci.yml": ("all", None),
    ".delivery/config.json": ("all", None),
    "package.json": ("all", None),
    "tools/unknown.bin": ("all", None),
}


class Areas(unittest.TestCase):
    def test_every_path_of_the_tree_maps_to_an_area_or_all(self):
        for path, (kind, areas) in TREE.items():
            got_kind, got = A.classify(path, CMAP)
            self.assertEqual(got_kind, kind, path)
            if kind == "areas":
                self.assertEqual(got, areas, path)

    def test_unknown_path_runs_everything(self):
        r = A.decide(["tools/unknown.bin"], CMAP)
        self.assertTrue(r["all"])
        self.assertTrue(all(r["flags"].values()))

    def test_unmapped_lists_the_unknown_paths_only(self):
        self.assertEqual(A.unmapped(list(TREE), CMAP), ["tools/unknown.bin"])

    def test_one_area(self):
        r = A.decide(["src/x.py"], CMAP)
        self.assertEqual(r["areas"], ["code"])
        self.assertFalse(r["all"])
        self.assertFalse(r["flags"]["installer"])

    def test_docs_only_runs_no_area(self):
        r = A.decide(["docs/a.md", "README.md"], CMAP)
        self.assertTrue(r["docs_only"])
        self.assertEqual(r["areas"], [])

    def test_mixed_areas_are_united(self):
        r = A.decide(["src/x.py", "installer/a.wxs"], CMAP)
        self.assertEqual(sorted(r["areas"]), ["code", "installer"])

    def test_no_changed_path_runs_everything(self):
        self.assertTrue(A.decide([], CMAP)["all"])

    def test_release_runs_everything_unless_config_says_no(self):
        self.assertTrue(A.decide(["src/x.py"], CMAP, release=True)["all"])
        r = A.decide(["src/x.py"], dict(CMAP, release_full=False), release=True)
        self.assertFalse(r["all"])

    def test_force_all(self):
        self.assertTrue(A.decide(["docs/a.md"], CMAP, force_all=True)["all"])

    def test_lines_and_cli(self):
        d = Path(tempfile.mkdtemp(prefix="ds261-"))
        self.addCleanup(shutil.rmtree, d, True)
        m = d / "ci-areas.json"
        m.write_text(json.dumps(CMAP))
        self.assertEqual(A.main(["--map", str(m), "src/x.py"]), 0)
        self.assertEqual(A.main(["--map", str(d / "none.json"), "src/x.py"]), 2)
        out = A.lines(A.decide(["src/x.py"], CMAP))
        self.assertIn("code=true", out)
        self.assertIn("installer=false", out)

    def test_bad_map(self):
        d = Path(tempfile.mkdtemp(prefix="ds261-"))
        self.addCleanup(shutil.rmtree, d, True)
        m = d / "ci-areas.json"
        m.write_text(json.dumps({"areas": {"code": "src"}}))
        with self.assertRaises(ValueError):
            A.load_map(m)


BAD = """name: CI
on:
  pull_request:
    types: [opened]
    paths-ignore:
      - 'docs/**'
  push:
    branches: [main]
    paths-ignore: ['docs/**']
jobs: {}
"""
GOOD = """name: CI
on:
  pull_request:
    types: [opened]
  push:
    branches: [main]
    paths-ignore: ['docs/**']
jobs: {}
"""


class Check(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="ds261c-"))
        self.addCleanup(shutil.rmtree, self.d, True)
        (self.d / ".github" / "workflows").mkdir(parents=True)
        (self.d / ".delivery").mkdir()

    def put(self, name, text, required=("ci.yml",)):
        (self.d / ".github" / "workflows" / name).write_text(text)
        (self.d / ".delivery" / "config.json").write_text(json.dumps({"watcher": {"ci_workflows": list(required)}}))

    def run_check(self):
        return K.main(["--root", str(self.d)])

    def test_pull_request_filter_fails(self):
        self.put("ci.yml", BAD)
        self.assertEqual(self.run_check(), 1)
        self.assertEqual(K.pr_filters(BAD), ["pull_request.paths-ignore"])

    def test_paths_filter_fails(self):
        self.assertEqual(K.pr_filters(BAD.replace("paths-ignore", "paths", 1)), ["pull_request.paths"])

    def test_push_filter_alone_passes(self):
        self.put("ci.yml", GOOD)
        self.assertEqual(self.run_check(), 0)

    def test_workflow_not_required_is_not_checked(self):
        self.put("ci.yml", BAD, required=("other.yml",))
        (self.d / ".github" / "workflows" / "other.yml").write_text(GOOD)
        self.assertEqual(self.run_check(), 0)

    def test_no_list_passes(self):
        (self.d / ".github" / "workflows" / "ci.yml").write_text(BAD)
        self.assertEqual(self.run_check(), 0)

    def test_missing_required_file_fails(self):
        self.put("ci.yml", GOOD, required=("gone.yml",))
        self.assertEqual(self.run_check(), 1)

    def test_bad_config_is_exit_2(self):
        (self.d / ".delivery" / "config.json").write_text("{")
        self.assertEqual(self.run_check(), 2)

    def test_doctor_warns_but_does_not_fail(self):
        import sys
        sys.path.insert(0, str(DELIVERY.parent.parent.parent.parent / "scripts"))
        import delivery_doctor as D
        self.put("ci.yml", BAD)
        cfg = {"watcher": {"ci_workflows": ["ci.yml"]}}
        ok, msg, items = D.check_ci_filters(str(self.d), cfg)
        self.assertTrue(ok)
        self.assertIn("DL-116", msg)
        self.put("ci.yml", GOOD)
        self.assertIsNone(D.check_ci_filters(str(self.d), cfg))

    def test_the_shipped_snippet_passes_its_own_check(self):
        self.assertEqual(K.pr_filters(SNIPPET.read_text(encoding="utf-8")), [])
        self.assertIn("if: always()", SNIPPET.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
