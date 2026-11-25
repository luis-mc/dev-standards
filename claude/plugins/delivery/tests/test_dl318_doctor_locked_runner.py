"""DL318: workflow runs-on labels in the doctor. Runs on Linux (all mocked)."""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

import _helpers  # noqa: F401
import delivery_doctor as DOC

WF = """name: ci
jobs:
  a:
    runs-on: [self-hosted, linux]
  b:
    runs-on: ${{ fromJSON(vars.CI_RUNS_ON) }}
  c:
    runs-on:
      - self-hosted
      - windows
  d:
    runs-on: ubuntu-latest
"""


class Workflows(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        os.makedirs(os.path.join(self.tmp, ".github", "workflows"))
        with open(os.path.join(self.tmp, ".github", "workflows", "ci.yml"), "w") as f:
            f.write(WF)

    def run_items(self, runners, variables):
        def gh(root, args, timeout=20):
            if args[0] == "api":
                return 0, json.dumps({"runners": runners})
            if args[:2] == ["variable", "list"]:
                return 0, json.dumps([{"name": k, "value": v} for k, v in variables.items()])
            return 0, "o/r\n"
        with mock.patch.object(DOC.H, "gh", gh):
            return {i["id"].split(":")[0]: i for i in DOC.workflow_items(self.tmp, {})}

    def test_parse(self):
        jobs = DOC.workflow_jobs(WF)
        self.assertEqual([j[0] for j in jobs], [4, 6, 8, 12])
        self.assertEqual(jobs[0][1], ["self-hosted", "linux"])
        self.assertEqual(jobs[2][1], ["self-hosted", "windows"])
        self.assertIsNotNone(jobs[1][2])

    def test_missing_label_fails_with_file_and_line(self):
        lin = {"os": "Linux", "status": "online", "labels": [{"name": "self-hosted"}, {"name": "Linux"}]}
        it = self.run_items([lin], {"CI_RUNS_ON": "[]"})
        self.assertEqual(it["workflows.labels"]["status"], "fail")
        self.assertIn("ci.yml:8", it["workflows.labels"]["detail"])
        self.assertNotIn("ci.yml:4", it["workflows.labels"]["detail"])

    def test_offline_runner_does_not_count(self):
        lin = {"os": "Linux", "status": "offline", "labels": [{"name": "self-hosted"}, {"name": "linux"}]}
        it = self.run_items([lin], {})
        self.assertIn("ci.yml:4", it["workflows.labels"]["detail"])

    def test_generic_warning_and_windows_var(self):
        both = [{"os": "Linux", "status": "online", "labels": [{"name": "self-hosted"}, {"name": "linux"}]},
                {"os": "Windows", "status": "online", "labels": [{"name": "self-hosted"}, {"name": "windows"}]}]
        it = self.run_items(both, {"CI_RUNS_ON": "[]"})
        self.assertEqual(it["workflows.labels"]["status"], "ok")
        self.assertEqual(it["workflows.generic"]["status"], "warn")
        self.assertEqual(it["workflows.windows_var"]["status"], "warn")
        it = self.run_items(both, {"CI_RUNS_ON_WINDOWS": '["self-hosted","windows"]'})
        self.assertNotIn("workflows.windows_var", it)


if __name__ == "__main__":
    unittest.main()
