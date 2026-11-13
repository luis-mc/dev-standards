"""DL301: rust_ci.py run resolves the program on the job PATH it passes, not on this process's PATH."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "templates" / "rust" / "scripts" / "delivery"))
import rust_ci  # noqa: E402


class RunPath(unittest.TestCase):
    def test_program_is_resolved_on_the_job_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            tool_dir = Path(tmp) / "bin"
            tool_dir.mkdir()
            name = "dl301tool" + (".cmd" if os.name == "nt" else "")
            tool = tool_dir / name
            tool.write_text("@echo off\r\n" if os.name == "nt" else "#!/bin/sh\n", encoding="utf-8")
            tool.chmod(0o755)
            seen = {}

            def fake_run(cmd, cwd=None, env=None):
                seen["cmd"] = cmd
                return mock.Mock(returncode=0)

            with mock.patch.object(rust_ci, "build_env", return_value=({"PATH": str(tool_dir)}, [])), \
                    mock.patch.object(rust_ci, "isolated", return_value=False), \
                    mock.patch.object(rust_ci.subprocess, "run", side_effect=fake_run), \
                    mock.patch.dict(os.environ, {"PATH": os.defpath}):
                self.assertEqual(rust_ci.cmd_run(Path(tmp), ["--", "dl301tool", "--x"]), 0)
            self.assertEqual(Path(seen["cmd"][0]).resolve(), tool.resolve())
            self.assertEqual(seen["cmd"][1:], ["--x"])

    def test_unknown_program_is_passed_unchanged(self):
        seen = {}
        with mock.patch.object(rust_ci, "build_env", return_value=({"PATH": ""}, [])), \
                mock.patch.object(rust_ci, "isolated", return_value=False), \
                mock.patch.object(rust_ci.subprocess, "run",
                                  side_effect=lambda cmd, **k: seen.setdefault("cmd", cmd) and mock.Mock(returncode=3)):
            rust_ci.cmd_run(Path("."), ["no-such-dl301-tool"])
        self.assertEqual(seen["cmd"], ["no-such-dl301-tool"])


if __name__ == "__main__":
    unittest.main()
