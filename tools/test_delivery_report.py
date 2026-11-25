#!/usr/bin/env python3
"""DP8 / R5.69: the warn-mode report (delivery_report.py), the warn-mode log lines and the Full Progress line.
Reads only temp folders. Standard library only."""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "claude/plugins/delivery/scripts"))
sys.path.insert(0, str(REPO / "claude/plugins/docs/scripts"))

import delivery_report as DR  # noqa: E402
import hooklib as H  # noqa: E402
import render_artifacts as R  # noqa: E402

LOG = [
    "2026-11-25T10:00:00Z\tstop:warn\tDL-31\tDL-31 an eta without a basis",
    "2026-11-25T10:05:00Z\tstop:warn\tDL-31\tDL-31 an eta without a basis",
    "2026-11-25T10:06:00Z\tpre-tool:warn\tDL-93\tDL-93 connectors",
    "2026-11-25T10:07:00Z\tstop\tDL-01\tDL-01 a real block (block mode)",
]


def project(mode="warn", log=LOG):
    d = Path(tempfile.mkdtemp(prefix="dp8-"))
    (d / ".delivery").mkdir()
    (d / ".delivery" / "config.json").write_text(json.dumps({"enforcement": {"mode": mode}}))
    if log is not None:
        (d / ".delivery" / "blocks.log").write_text("\n".join(log) + "\n")
    return d


class CountTests(unittest.TestCase):
    def test_counts_per_rule_and_skips_real_blocks(self):
        rep = DR.build(str(project()))
        self.assertEqual(rep["mode"], "warn")
        self.assertEqual(rep["total"], 3)
        self.assertEqual(rep["rules"], {"DL-31": 2, "DL-93": 1})

    def test_text_says_would_have_blocked_n_times(self):
        text = "\n".join(DR.lines(DR.build(str(project()))))
        self.assertIn("would have blocked 3 times", text)
        self.assertIn("DL-31: would have blocked 2 times", text)
        self.assertIn("DL-93: would have blocked 1 time\n" if False else "DL-93: would have blocked 1 time", text)

    def test_since_filters_old_lines(self):
        rep = DR.build(str(project()), since="2026-11-25T10:06:00Z")
        self.assertEqual(rep["rules"], {"DL-93": 1})

    def test_no_log_means_nothing_blocked(self):
        rep = DR.build(str(project(log=None)))
        self.assertEqual(rep["total"], 0)
        self.assertIn("nothing would have been blocked", DR.lines(rep)[0])

    def test_block_mode_has_no_report(self):
        rep = DR.build(str(project(mode="block")))
        self.assertIsNone(DR.summary_line(rep))
        self.assertIn("block mode", DR.lines(rep)[0])


class CommandTests(unittest.TestCase):
    def run_main(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = DR.main(list(argv))
        return code, out.getvalue()

    def test_write_makes_the_json_file(self):
        d = project()
        code, out = self.run_main("--root", str(d), "--write")
        self.assertEqual(code, 0)
        self.assertIn("would have blocked 3 times", out)
        data = json.loads((d / ".delivery" / "warn-report.json").read_text())
        self.assertEqual(data["total"], 3)

    def test_no_delivery_folder_exits_zero(self):
        d = Path(tempfile.mkdtemp(prefix="dp8-none-"))
        code, out = self.run_main("--root", str(d))
        self.assertEqual(code, 0)
        self.assertIn("No .delivery/", out)


class HookLogTests(unittest.TestCase):
    def test_force_logs_even_when_log_every_block_is_off(self):
        d = project(log=None)
        H.log_block(str(d), {}, "stop:warn", "DL-31 x", force=True)
        H.log_block(str(d), {}, "stop", "DL-01 y")          # not forced, setting off: nothing
        rep = DR.build(str(d))
        self.assertEqual(rep["rules"], {"DL-31": 1})
        self.assertEqual(rep["total"], 1)


class FullProgressTests(unittest.TestCase):
    def test_one_line_in_warn_mode(self):
        rep = DR.build(str(project()))
        line = R.warn_report_line(rep)
        self.assertIn("would have blocked 3 times across 2 rules", line)

    def test_no_line_in_block_mode_or_bad_data(self):
        self.assertIsNone(R.warn_report_line(DR.build(str(project(mode="block")))))
        self.assertIsNone(R.warn_report_line(None))
        self.assertIsNone(R.warn_report_line([1]))

    def test_zero_blocks_line(self):
        self.assertIn("nothing would have been blocked", R.warn_report_line({"mode": "warn", "total": 0, "rules": {}}))


if __name__ == "__main__":
    unittest.main()
