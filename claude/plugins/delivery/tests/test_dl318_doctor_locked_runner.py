"""DL318: locked Windows runner folders and workflow runs-on labels in the doctor. Runs on Linux (all mocked)."""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

import _helpers  # noqa: F401
import delivery_doctor as DOC

SVC = [{"Name": "actions.runner.o-r.win1", "PathName": '"C:\\actions-runners\\win1\\bin\\RunnerService.exe"',
        "StartName": ".\\ci-win1"},
       {"Name": "Spooler", "PathName": "x", "StartName": "LocalSystem"}]


class Locked(unittest.TestCase):
    def setUp(self):
        self.rows = DOC.service_rows(SVC)

    def test_service_rows(self):
        self.assertEqual(len(self.rows), 1)
        self.assertEqual(self.rows[0]["folder"], "C:\\actions-runners\\win1")
        self.assertEqual(self.rows[0]["account"], ".\\ci-win1")

    def test_locked_folder_is_found_and_warns(self):
        with mock.patch.object(DOC, "_folder_locked", return_value=True), \
                mock.patch.object(DOC, "_account_in_group", side_effect=lambda a, g: g == DOC.WIN_GROUP):
            items = DOC.windows_runner_items([], self.rows)
        by = {i["id"].split(":")[-1]: i for i in items}
        self.assertEqual(by["account"]["status"], "ok")
        for k in (".env", "CI_TOOLS_DIR", "RUSTUP_HOME", "CARGO_HOME"):
            self.assertEqual(by[k]["status"], "warn")
            self.assertIn(DOC.NEEDS_ADMIN, by[k]["detail"])
        self.assertFalse(any("no self-hosted" in i["detail"] for i in items))

    def test_permission_error_reads_as_locked(self):
        with mock.patch("builtins.open", side_effect=PermissionError):
            self.assertTrue(DOC._folder_locked("/x"))

    def test_hook_check_never_says_no_runner(self):
        with mock.patch.object(DOC, "_runner_dirs", return_value=[]), \
                mock.patch.object(DOC, "_windows_services", return_value=self.rows), \
                mock.patch.object(DOC, "_folder_locked", return_value=True), \
                mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(DOC.HOOK_VAR, None)
            ok, detail = DOC._check_runner_hook("/r", {})
        self.assertTrue(ok)
        self.assertNotIn("no self-hosted runner found", detail)
        self.assertIn(DOC.NEEDS_ADMIN, detail)


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
