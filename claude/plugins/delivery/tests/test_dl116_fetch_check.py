"""DL116: DL-94, CI jobs fetch pinned tools through the per-runner cache."""
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from _helpers import make_root
import hook_pre_tool as P
import hooklib as H

SCRIPT = (Path(__file__).resolve().parent.parent / "templates" / "shared" / "scripts" / "delivery"
          / "workflow_fetch_check.py")
spec = importlib.util.spec_from_file_location("workflow_fetch_check", SCRIPT)
W = importlib.util.module_from_spec(spec)
spec.loader.exec_module(W)

URL = "https://example.com/owner/tool/releases/download/v1.0/tool.tar.gz"


def wf(*run_lines):
    body = "\n".join("          " + x for x in run_lines)
    return "jobs:\n  a:\n    steps:\n      - name: get\n        run: |\n" + body + "\n"


GOOD = wf("python3 scripts/delivery/ci_tool.py fetch %s --sha256 abc --name tool/1.0/tool.tar.gz" % URL)
BAD = wf("curl -sSL %s -o $RUNNER_TEMP/tool.tar.gz" % URL)


class CheckTests(unittest.TestCase):
    def test_bare_curl_into_runner_temp_flagged(self):
        out = W.check_text(BAD, "ci.yml")
        self.assertEqual(len(out), 1)
        self.assertIn("ci.yml:6: DL-94", out[0])
        self.assertIn("ci_tool.py fetch", out[0])

    def test_sha_but_into_runner_temp_flagged(self):
        out = W.check_text(wf("curl -sSL %s -o ${{ runner.temp }}/t.tgz" % URL, "sha256sum -c t.sha"), "ci.yml")
        self.assertEqual(len(out), 1)
        self.assertIn("RUNNER_TEMP", out[0])
        self.assertNotIn("no sha256", out[0])

    def test_ci_tool_line_passes(self):
        self.assertEqual(W.check_text(GOOD), [])

    def test_opt_out_with_reason_passes(self):
        t = wf("curl -sSL %s -o t.tgz  # ci-tool: ok one-off, checked by hand" % URL)
        self.assertEqual(W.check_text(t), [])

    def test_opt_out_without_reason_flagged(self):
        out = W.check_text(wf("curl -sSL %s -o t.tgz  # ci-tool: ok" % URL), "ci.yml")
        self.assertEqual(len(out), 1)
        self.assertIn("needs a reason", out[0])

    def test_invoke_webrequest_exe_flagged(self):
        out = W.check_text(wf("Invoke-WebRequest https://example.com/dl/setup.exe -OutFile setup.exe"))
        self.assertEqual(len(out), 1)
        self.assertIn("no sha256", out[0])

    def test_plain_curl_of_api_not_flagged(self):
        self.assertEqual(W.check_text(wf("curl -s https://example.com/api/status")), [])

    def test_cli_exit_codes(self):
        d = make_root()
        bad, good = d / "bad.yml", d / "good.yml"
        bad.write_text(BAD)
        good.write_text(GOOD)
        run = lambda *a: subprocess.run([sys.executable, str(SCRIPT), *a], capture_output=True, text=True)
        self.assertEqual(run(str(good)).returncode, 0)
        r = run(str(bad))
        self.assertEqual(r.returncode, 1)
        self.assertIn("DL-94", r.stdout)
        self.assertEqual(run(str(d / "missing.yml")).returncode, 2)
        self.assertEqual(run("--bogus").returncode, 2)


def write(rel, content, tool="Write", cfg=None):
    root = make_root()
    data = {"tool_name": tool, "tool_input": {"file_path": str(root / rel), "content": content}, "cwd": str(root)}
    if tool == "Edit":
        data["tool_input"] = {"file_path": str(root / rel), "old_string": "x", "new_string": content}
    c = cfg or H.load_config(str(root))
    try:
        P.check_workflow_fetch(str(root), c, data)
    except P.Deny as d:
        return str(d)
    return None


class HookTests(unittest.TestCase):
    def test_blocks_bad_workflow(self):
        out = write(".github/workflows/ci.yml", BAD)
        self.assertIn("DL-94", out)
        self.assertIn("ci.yml:6", out)
        self.assertIn("ci_tool.py fetch <url> --sha256 <hex> --name <tool>/<version>/<file>", out)

    def test_blocks_bad_edit(self):
        self.assertIn("DL-94", write(".github/workflows/ci.yml", BAD, tool="Edit"))

    def test_allows_good_workflow(self):
        self.assertIsNone(write(".github/workflows/ci.yml", GOOD))

    def test_non_workflow_file_not_checked(self):
        self.assertIsNone(write("docs/notes.yml", BAD))
        self.assertIsNone(write("scripts/get.sh", BAD))

    def test_fails_open_on_internal_error(self):
        with mock.patch.object(P, "_fetch_checker", side_effect=RuntimeError("boom")):
            self.assertIsNone(write(".github/workflows/ci.yml", BAD))

    def test_fails_open_on_parse_error(self):
        root = make_root()
        data = {"tool_name": "Write", "tool_input": {"file_path": str(root / ".github/workflows/ci.yml"),
                                                       "content": BAD}, "cwd": str(root)}
        fake = mock.Mock()
        fake.check_text.side_effect = ValueError("parse")
        with mock.patch.object(P, "_fetch_checker", return_value=fake):
            P.check_workflow_fetch(str(root), H.load_config(str(root)), data)

    def test_can_be_switched_off(self):
        root = make_root()
        cfg = H.load_config(str(root))
        cfg["checks_off"] = ["DL-94"]
        self.assertIsNone(write(".github/workflows/ci.yml", BAD, cfg=cfg))


if __name__ == "__main__":
    unittest.main()
