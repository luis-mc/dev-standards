"""DL394: runs-on reads RUNS_ON_<OS> first, then the old CI_RUNS_ON[_WINDOWS], then the hosted default."""
import json
import re
import unittest
from pathlib import Path

import _helpers  # noqa: F401
import delivery_doctor as DOC
import test_ci_setup as TCS

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
LINUX = ("RUNS_ON_LINUX", "CI_RUNS_ON")
WINDOWS = ("RUNS_ON_WINDOWS", "CI_RUNS_ON_WINDOWS")


def _runs_on_values():
    """[(file, job, runs-on string)] of every workflow template."""
    out = []
    for path in sorted(TEMPLATES.rglob("*.yml")):
        if "workflows" not in path.parts and path.name != "pool-check.yml":
            continue
        text = path.read_text(encoding="utf-8")
        if yaml is not None:
            doc = yaml.safe_load(text) or {}
            for job, body in (doc.get("jobs") or {}).items():
                if isinstance(body, dict) and "runs-on" in body:
                    out.append((path.name, job, body["runs-on"]))
        else:
            for m in re.finditer(r"^    runs-on:\s*(.+)$", text, re.M):
                out.append((path.name, "?", m.group(1)))
    return out


class TemplateOrder(unittest.TestCase):
    def test_every_self_hostable_runs_on_is_new_then_old_then_default(self):
        seen = 0
        for name, job, value in _runs_on_values():
            value = str(value)
            if "vars." not in value:
                continue  # a literal hosted label (lifecycle lanes, the hosted fallback) is not self-hostable here
            names = re.findall(r"vars\.([A-Z_]+)", value)
            names = [n for n in names if not n.startswith("NIGHTLY")]
            self.assertIn(tuple(names), (LINUX, WINDOWS), "%s %s: %s" % (name, job, value))
            if name != "pool-check.yml":
                self.assertRegex(value, r"\|\| '\"(ubuntu|windows)-latest\"'\) \}\}$", "%s %s needs a hosted default" % (name, job))
            seen += 1
        self.assertGreater(seen, 25)

    def test_no_template_reads_only_the_old_variable(self):
        for path in TEMPLATES.rglob("*.yml"):
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if "runs-on:" in line and "vars.CI_RUNS_ON" in line:
                    self.assertTrue("vars.RUNS_ON_" in line and line.index("vars.RUNS_ON_") < line.index("vars.CI_RUNS_ON"),
                                    "%s:%d" % (path.name, n))


class DoctorReport(unittest.TestCase):
    def test_resolve_each_os(self):
        res = {o: (n, v) for o, n, v, _ in DOC.resolve_runs_on(
            {"RUNS_ON_LINUX": '["self-hosted","linux","x"]', "CI_RUNS_ON_WINDOWS": '["self-hosted","windows"]'})}
        self.assertEqual(res["linux"][0], "RUNS_ON_LINUX")
        self.assertEqual(res["windows"][0], "CI_RUNS_ON_WINDOWS")
        self.assertEqual(res["macos"], (None, None))

    def test_report_names_the_variable_and_the_default(self):
        items = DOC.runs_on_items({"CI_RUNS_ON": '"ubuntu-latest"'}, "o/r")
        self.assertEqual([i["status"] for i in items], ["ok"])
        d = items[0]["detail"]
        self.assertIn("linux -> CI_RUNS_ON", d)
        self.assertIn("windows -> GitHub-hosted default", d)

    def test_both_set_with_different_values_warns(self):
        items = DOC.runs_on_items({"RUNS_ON_LINUX": '["self-hosted","a"]', "CI_RUNS_ON": '["self-hosted","b"]'}, "o/r")
        warn = [i for i in items if i["status"] == "warn"]
        self.assertEqual(len(warn), 1)
        self.assertIn("RUNS_ON_LINUX wins over CI_RUNS_ON", warn[0]["detail"])
        self.assertIn("delete RUNS_ON_*", warn[0]["detail"])

    def test_both_set_with_the_same_value_does_not_warn(self):
        items = DOC.runs_on_items({"RUNS_ON_LINUX": '["self-hosted", "a"]', "CI_RUNS_ON": '["self-hosted","a"]'}, "o/r")
        self.assertFalse([i for i in items if i["status"] == "warn"])

    def test_unreadable_variables_report_nothing(self):
        self.assertEqual(DOC.runs_on_items(None, "o/r"), [])


class SetupWrites(TCS.Base):
    def test_plan_sets_runs_on_linux(self):
        root = self.project(TCS.OPT1)
        self.fake({"api": {}, "vars": {}})
        detail = self.ci(root)[1]
        self.assertIn("var:RUNS_ON_LINUX", detail)
        self.assertNotIn("var:CI_RUNS_ON", detail)


if __name__ == "__main__":
    unittest.main()
