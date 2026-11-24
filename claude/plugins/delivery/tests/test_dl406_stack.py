import json
import sys
import unittest
from pathlib import Path

from _helpers import make_root
import delivery_config as C
import delivery_doctor as D

TPL = Path(__file__).resolve().parent.parent / "templates" / "shared" / "scripts" / "delivery"
sys.path.insert(0, str(TPL))
import stack as S  # noqa: E402


def repo(files, cfg=None, track=None):
    root = make_root(cfg)
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    if track:
        (root / "scripts" / "delivery").mkdir(parents=True)
        (root / "scripts" / "delivery" / "gate.json").write_text(json.dumps({"track": track}))
    return root


def run(root, cfg=None):
    return D.check_stack(str(root), cfg if cfg is not None else {})


def details(items):
    return [i["detail"] for i in items]


class StackTest(unittest.TestCase):
    def test_default_ts_project_unchanged(self):
        root = repo({"pnpm-lock.yaml": "", "vitest.config.ts": "", "playwright.config.ts": "",
                     "package.json": '{"jest": {}}'}, track="ts")
        ok, _, items = run(root)
        self.assertTrue(ok)
        self.assertTrue(all(i["status"] == "ok" for i in items))
        self.assertEqual({r["status"] for r in S.resolve(str(root), {}).values()}, {"known"})

    def test_cypress_undeclared_fails(self):
        ok, _, items = run(repo({"cypress.config.ts": ""}))
        self.assertFalse(ok)
        self.assertIn("cypress found (cypress.config.ts) but delivery cannot check it: declare it under stack in "
                      ".delivery/config.json, or remove it", details(items))

    def test_fails_whatever_enforcement_says(self):
        root = repo({"cypress.config.ts": ""})
        self.assertFalse(run(root, {"enforcement": {"mode": "warn"}})[0])

    def test_cypress_declared_ok(self):
        cfg = {"stack": {"e2e": ["cypress"]}}
        ok, _, items = run(repo({"cypress.config.ts": ""}, cfg), cfg)
        self.assertTrue(ok)
        self.assertIn("declared; delivery runs its commands but cannot judge them", items[0]["detail"])

    def test_pytest_selenium(self):
        root = repo({"pytest.ini": "", "requirements-dev.txt": "pytest\nselenium==4\n"})
        self.assertEqual(S.detect_tools(str(root)), {"pytest": "pytest.ini", "selenium": "requirements-dev.txt"})
        ok, _, items = run(root)
        self.assertFalse(ok)
        self.assertTrue(any("selenium found" in d for d in details(items)))
        cfg = {"stack": {"e2e": ["selenium"], "unit": ["pytest"]}}
        ok, _, items = run(root, cfg)
        self.assertTrue(ok)
        self.assertIn("pytest (pytest.ini): declared", details(items))

    def test_pyproject_pytest(self):
        root = repo({"pyproject.toml": "[tool.pytest.ini_options]\n"})
        self.assertIn("pytest", S.detect_tools(str(root)))

    def test_gradle(self):
        root = repo({"build.gradle.kts": ""})
        self.assertFalse(run(root)[0])
        cfg = {"stack": {"build": ["gradle"], "test_globs": ["src/test/**/*.java"]}}
        self.assertTrue(run(root, cfg)[0])

    def test_yarn(self):
        root = repo({"yarn.lock": ""})
        self.assertFalse(run(root)[0])
        self.assertTrue(run(root, {"stack": {"package_manager": "yarn"}})[0])

    def test_detect_the_rest(self):
        files = {"go.mod": "", "Cargo.toml": "", "app.sln": "", "pom.xml": "", "Gemfile": "", "composer.json": "{}",
                 "package-lock.json": ""}
        self.assertEqual(set(S.detect_tools(str(repo(files)))),
                         {"go", "cargo", "dotnet", "maven", "bundler", "composer", "npm"})

    def test_dependency_folders_ignored(self):
        root = repo({"node_modules/x/yarn.lock": "", "a/b/c/yarn.lock": ""})
        self.assertEqual(S.detect_tools(str(root)), {})

    def test_schema_accepts_block_and_refuses_unknown_field(self):
        good = {"stack": {"e2e": ["cypress"], "unit": ["pytest"], "package_manager": "yarn", "build": ["gradle"],
                          "e2e_spec_globs": ["cypress/e2e/**/*.cy.*"], "test_globs": ["src/test/**/*.java"]}}
        self.assertEqual(C.validate_config(good), ([], []))
        self.assertEqual(S.problems(good), [])
        bad = {"stack": {"e2e": ["cypress"], "colour": "red"}}
        errors, warnings = C.validate_config(bad)
        self.assertTrue(any("stack.colour" in w for w in warnings + errors))
        self.assertTrue(any("stack.colour" in p for p in S.problems(bad)))
        self.assertFalse(run(repo({}), bad)[0])
        self.assertTrue(C.validate_config({"stack": {"e2e": "cypress"}})[0])
        self.assertIs(C.load_schema()["properties"]["stack"]["additionalProperties"], False)

    def test_registered(self):
        self.assertIn("stack", [n for n, _ in D.CHECKS])


if __name__ == "__main__":
    unittest.main()
