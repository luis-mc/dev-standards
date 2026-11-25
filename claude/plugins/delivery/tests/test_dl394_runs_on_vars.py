"""DL394: runs-on reads CRSP_RUNS_ON_<OS> first, then the old CI_RUNS_ON[_WINDOWS], then the hosted default."""
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
LINUX = ("CRSP_RUNS_ON_LINUX", "CI_RUNS_ON")
WINDOWS = ("CRSP_RUNS_ON_WINDOWS", "CI_RUNS_ON_WINDOWS")


def _runs_on_values():
    """[(file, job, runs-on string)] of every workflow template."""
    out = []
    for path in sorted(TEMPLATES.rglob("*.yml")):
        if "workflows" not in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if yaml is not None:
            doc = yaml.safe_load(text) or {}
            for job, body in (doc.get("jobs") or {}).items():
                if isinstance(body, dict) and "runs-on" in body:
                    out.append((path.name, job, body["runs-on"]))
        else:
            job = "?"  # no PyYAML: the job key is the last two-space key above the runs-on line
            for line in text.splitlines():
                k = re.match(r"^  ([A-Za-z0-9_.-]+):\s*$", line)
                if k:
                    job = k.group(1)
                r = re.match(r"^    runs-on:\s*(.+)$", line)
                if r:
                    out.append((path.name, job, r.group(1)))
    return out


class TemplateOrder(unittest.TestCase):
    def test_every_self_hostable_runs_on_is_new_then_old_then_default(self):
        seen = 0
        for name, job, value in _runs_on_values():
            value = str(value)
            if "vars." not in value:
                continue  # a literal hosted label (lifecycle lanes, the hosted fallback) is not self-hostable here
            names = re.findall(r"vars\.([A-Z0-9_]+)", value)
            names = [n for n in names if not n.startswith("NIGHTLY")]
            if name != "lifecycle-lanes.yml":  # DL399: the per-job variable comes first
                self.assertEqual(names[0], DOC.job_var_name(job), "%s %s: %s" % (name, job, value))
                names = names[1:]
            self.assertIn(tuple(names), (LINUX, WINDOWS), "%s %s: %s" % (name, job, value))
            self.assertRegex(value, r"\|\| '\"(ubuntu|windows)-latest\"'\) \}\}$", "%s %s needs a hosted default" % (name, job))
            seen += 1
        self.assertGreater(seen, 25)

    def test_no_template_reads_only_the_old_variable(self):
        for path in TEMPLATES.rglob("*.yml"):
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if "runs-on:" in line and "vars.CI_RUNS_ON" in line and "vars.CRSP_RUNS_ON_" in line:
                    self.assertTrue("vars.CRSP_RUNS_ON_" in line and line.index("vars.CRSP_RUNS_ON_") < line.index("vars.CI_RUNS_ON"),
                                    "%s:%d" % (path.name, n))


class PerJobName(unittest.TestCase):
    """DL399: CRSP_<JOB>, the job key uppercased with every non-alphanumeric turned into `_`."""

    def test_name_rule(self):
        for job, want in (("linux-suites", "CRSP_LINUX_SUITES"), ("a.b", "CRSP_A_B"), ("test2", "CRSP_TEST2"),
                          ("e2e-1.5_x", "CRSP_E2E_1_5_X"), ("lint", "CRSP_LINT")):
            self.assertEqual(DOC.job_var_name(job), want)

    def test_lifecycle_lanes_read_the_job_variable_first(self):
        text = (TEMPLATES / "lifecycle" / "os" / "lifecycle-lanes.yml").read_text(encoding="utf-8")
        n = 0
        for m in re.finditer(r"^  ([\w.-]+):\n(?:(?!^  \S).*\n)*?    runs-on: (.+)$", text, re.M):
            self.assertTrue(m.group(2).startswith("${{ fromJSON(vars.%s || vars.LIFECYCLE_RUNS_ON_" % DOC.job_var_name(m.group(1))))
            n += 1
        self.assertEqual(n, 6)

    def test_doctor_lists_per_job_overrides(self):
        v = {"CRSP_LINUX_SUITES": '["self-hosted","a"]', "CRSP_RUNS_ON_LINUX": '["self-hosted","b"]', "OTHER": "x"}
        self.assertEqual([n for n, _ in DOC.per_job_overrides(v)], ["CRSP_LINUX_SUITES"])
        d = DOC.runs_on_items(v, "o/r")[0]["detail"]
        self.assertIn("CRSP_LINUX_SUITES", d)
        self.assertNotIn("Per-job", DOC.runs_on_items({"CRSP_RUNS_ON_LINUX": '"x"'}, "o/r")[0]["detail"])


class DoctorReport(unittest.TestCase):
    def test_resolve_each_os(self):
        res = {o: (n, v) for o, n, v, _ in DOC.resolve_runs_on(
            {"CRSP_RUNS_ON_LINUX": '["self-hosted","linux","x"]', "CI_RUNS_ON_WINDOWS": '["self-hosted","windows"]'})}
        self.assertEqual(res["linux"][0], "CRSP_RUNS_ON_LINUX")
        self.assertEqual(res["windows"][0], "CI_RUNS_ON_WINDOWS")
        self.assertEqual(res["macos"], (None, None))

    def test_report_names_the_variable_and_the_default(self):
        items = DOC.runs_on_items({"CI_RUNS_ON": '"ubuntu-latest"'}, "o/r")
        self.assertEqual([i["status"] for i in items], ["ok"])
        d = items[0]["detail"]
        self.assertIn("linux -> CI_RUNS_ON", d)
        self.assertIn("windows -> GitHub-hosted default", d)

    def test_both_set_with_different_values_warns(self):
        items = DOC.runs_on_items({"CRSP_RUNS_ON_LINUX": '["self-hosted","a"]', "CI_RUNS_ON": '["self-hosted","b"]'}, "o/r")
        warn = [i for i in items if i["status"] == "warn"]
        self.assertEqual(len(warn), 1)
        self.assertIn("CRSP_RUNS_ON_LINUX wins over CI_RUNS_ON", warn[0]["detail"])
        self.assertIn("delete CRSP_RUNS_ON_*", warn[0]["detail"])

    def test_both_set_with_the_same_value_does_not_warn(self):
        items = DOC.runs_on_items({"CRSP_RUNS_ON_LINUX": '["self-hosted", "a"]', "CI_RUNS_ON": '["self-hosted","a"]'}, "o/r")
        self.assertFalse([i for i in items if i["status"] == "warn"])

    def test_unreadable_variables_report_nothing(self):
        self.assertEqual(DOC.runs_on_items(None, "o/r"), [])


class SetupWrites(TCS.Base):
    def test_plan_sets_runs_on_linux(self):
        root = self.project(TCS.OPT1)
        self.fake({"api": {}, "vars": {}})
        detail = self.ci(root)[1]
        self.assertIn("var:CRSP_RUNS_ON_LINUX", detail)
        self.assertNotIn("var:CI_RUNS_ON", detail)


if __name__ == "__main__":
    unittest.main()
