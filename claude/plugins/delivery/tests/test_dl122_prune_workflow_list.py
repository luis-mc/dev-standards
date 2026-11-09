"""DL122: the artifact-prune workflow list is project-owned (artifact_prune.workflows)."""
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


class WorkflowList(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.cfg = os.path.join(self.tmp, "config.json")
        self.wf = os.path.join(self.tmp, "artifact-prune.yml")
        shutil.copyfile(WF, self.wf)

    def set_cfg(self, obj):
        with open(self.cfg, "w", encoding="utf-8") as f:
            json.dump(obj, f)

    def test_default_when_unset_and_template_unchanged(self):
        for cfg in (None, {}, {"artifact_prune": {}}):
            if cfg is not None:
                self.set_cfg(cfg)
            self.assertEqual(AP.load_workflows(self.cfg), ["CI", "Package"])
        before = Path(self.wf).read_bytes()
        code, out, _ = run("--config", self.cfg, "--sync-workflow", self.wf)
        self.assertEqual((code, out.strip()), (0, "unchanged"))
        self.assertEqual(Path(self.wf).read_bytes(), before)
        self.assertEqual(run("--config", self.cfg, "--check-workflow", self.wf)[0], 0)

    def test_project_list_is_synced_and_checked(self):
        self.set_cfg({"artifact_prune": {"workflows": ["CI", "Package", "Installers"]}})
        self.assertEqual(run("--config", self.cfg, "--check-workflow", self.wf)[0], 1)
        code, out, _ = run("--config", self.cfg, "--sync-workflow", self.wf)
        self.assertEqual((code, out.strip()), (0, "synced"))
        self.assertIn('workflows: ["CI", "Package", "Installers"]', Path(self.wf).read_text())
        self.assertEqual(run("--config", self.cfg, "--check-workflow", self.wf)[0], 0)

    def test_print_and_bad_list(self):
        self.set_cfg({"artifact_prune": {"workflows": ["A", "B"]}})
        self.assertEqual(run("--config", self.cfg, "--print-workflows")[1].split(), ["A", "B"])
        for bad in ([], "CI", [1], ['a"b']):
            self.set_cfg({"artifact_prune": {"workflows": bad}})
            self.assertEqual(run("--config", self.cfg, "--print-workflows")[0], 2)

    def test_template_has_check_step_and_default_line(self):
        text = WF.read_text()
        self.assertIn('workflows: ["CI", "Package"]', text)
        self.assertIn("--check-workflow", text)

    def test_missing_line_is_an_error(self):
        Path(self.wf).write_text("on: {}\n")
        self.assertEqual(run("--config", self.cfg, "--sync-workflow", self.wf)[0], 2)


if __name__ == "__main__":
    unittest.main()
