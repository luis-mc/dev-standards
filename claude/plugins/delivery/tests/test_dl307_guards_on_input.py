"""DL307: fast_guards runs the project's always-on guards whose inputs match a changed file."""
import argparse
import contextlib
import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "templates" / "shared" / "scripts" / "delivery"))
import delivery_common as dc  # noqa: E402
import fast_guards as F  # noqa: E402

PY = '"%s" -c ' % sys.executable.replace("\\", "/")


def guard(name, code, inputs):
    return {"name": name, "command": PY + '"%s"' % code, "inputs": inputs}


class Run(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        self.args = argparse.Namespace(timeout_minutes=1)

    def go(self, guards, files):
        ctx = SimpleNamespace(root=self.root, files=files)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok = F.run_always_on_guards(self.root, guards, ctx, self.args)
        return ok, buf.getvalue()

    def test_matching_input_runs(self):
        ok, out = self.go([guard("g", "print('hi')", ["src/**"])], ["src/a/b.ts"])
        self.assertTrue(ok)
        self.assertIn("always-on guard g: pass", out)

    def test_non_matching_is_skipped_with_reason(self):
        ok, out = self.go([guard("g", "raise SystemExit(1)", ["src/**"])], ["docs/a.md"])
        self.assertTrue(ok)
        self.assertIn("always-on guard g: skipped, no changed file matches", out)

    def test_failure_names_guard_and_tail(self):
        ok, out = self.go([guard("boundary", "print('cycle a-b'); raise SystemExit(3)", ["**/*.ts"])], ["x/y.ts"])
        self.assertFalse(ok)
        self.assertIn("FAIL always-on guard boundary", out)
        self.assertIn("cycle a-b", out)

    def test_double_star_always_runs(self):
        for f in ("README.md", "a/b/c.txt"):
            ok, out = self.go([guard("all", "print(1)", ["**"])], [f])
            self.assertIn("all: pass", out)

    def test_one_failure_does_not_hide_the_next(self):
        ok, out = self.go([guard("a", "raise SystemExit(1)", ["**"]), guard("b", "print(2)", ["**"])], ["f"])
        self.assertFalse(ok)
        self.assertIn("always-on guard b: pass", out)

    def test_glob_rules(self):
        self.assertIsNotNone(F.guard_match(["src/*.ts"], ["src/a.ts"]))
        self.assertIsNone(F.guard_match(["src/*.ts"], ["src/a/b.ts"]))
        self.assertIsNotNone(F.guard_match(["**/e2e/*.spec.ts"], ["e2e/a.spec.ts"]))
        self.assertIsNotNone(F.guard_match(["depcruise.config.js"], ["depcruise.config.js"]))


class Config(unittest.TestCase):
    def test_no_declaration_is_empty(self):
        self.assertEqual(dc._check_always_on_guards(None, "g"), [])

    def test_bad_declarations_are_refused(self):
        for bad in ("x", [1], [{"name": "a", "command": "x"}], [{"name": "a", "command": "x", "inputs": []}],
                    [{"command": "x", "inputs": ["**"]}]):
            with self.assertRaises(dc.DeliveryError):
                dc._check_always_on_guards(bad, "g")

    def test_good_declaration(self):
        g = [{"name": "a", "command": "x", "inputs": ["**"]}]
        self.assertEqual(dc._check_always_on_guards(g, "g"), g)

    def test_no_declaration_runs_old_behaviour(self):
        ctx = SimpleNamespace(cfg={"steps": []})
        self.assertFalse(ctx.cfg.get("always_on_guards") or [])


if __name__ == "__main__":
    unittest.main()
