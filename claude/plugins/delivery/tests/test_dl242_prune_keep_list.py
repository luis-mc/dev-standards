"""DL242: --sync-workflow keeps the workflow file's list when the config sets none."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

TPL = Path(__file__).resolve().parent.parent / "templates" / "shared"
sys.path.insert(0, str(TPL / "scripts" / "delivery"))
import artifact_prune as AP  # noqa: E402

WF = TPL / ".github" / "workflows" / "artifact-prune.yml"


def run(*argv):
    out, err = StringIO(), StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = AP.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class KeepList(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.cfg = os.path.join(self.tmp, "config.json")
        self.wf = os.path.join(self.tmp, "wf", "artifact-prune.yml")

    def put_wf(self, names):
        os.makedirs(os.path.dirname(self.wf), exist_ok=True)
        text = WF.read_text(encoding="utf-8").replace('["CI", "Package"]', json.dumps(names))
        Path(self.wf).write_text(text, encoding="utf-8", newline="")

    def list_in_file(self):
        return AP.file_workflows(self.wf)

    def sync(self):
        return run("--config", self.cfg, "--sync-workflow", self.wf)

    def test_no_section_keeps_existing_list(self):
        self.put_wf(["CI", "E2E"])
        for cfg in (None, {}, {"artifact_prune": {}}, {"artifact_prune": {"keep": 3}}):
            if cfg is not None:
                Path(self.cfg).write_text(json.dumps(cfg), encoding="utf-8")
            code, out, _ = self.sync()
            self.assertEqual(code, 0)
            self.assertIn("existing file", out)
            self.assertIn("unchanged", out)
            self.assertEqual(self.list_in_file(), ["CI", "E2E"])

    def test_config_overrides_file(self):
        self.put_wf(["CI", "E2E"])
        Path(self.cfg).write_text(json.dumps({"artifact_prune": {"workflows": ["CI", "Installers"]}}),
                                  encoding="utf-8")
        code, out, _ = self.sync()
        self.assertEqual(code, 0)
        self.assertIn("config", out)
        self.assertIn("synced", out)
        self.assertEqual(self.list_in_file(), ["CI", "Installers"])

    def test_no_file_no_config_writes_default(self):
        code, out, _ = self.sync()
        self.assertEqual(code, 0)
        self.assertIn("default", out)
        self.assertEqual(self.list_in_file(), ["CI", "Package"])

    def test_file_without_list_reports_default_and_errors(self):
        os.makedirs(os.path.dirname(self.wf))
        Path(self.wf).write_text("on: push\n", encoding="utf-8")
        code, out, err = self.sync()
        self.assertEqual(code, 2)
        self.assertIn("default", out)
        self.assertIn("no one-line", err)

    def test_source_line_is_printed_once(self):
        self.put_wf(["CI"])
        _, out, _ = self.sync()
        self.assertEqual(sum(1 for l in out.splitlines() if l.startswith("workflow list from:")), 1)


if __name__ == "__main__":
    unittest.main()
