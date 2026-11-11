#!/usr/bin/env python3
"""DL263: tests for claude-setup's ci_pin.py. No network, git and marketplace stubbed.
Run: python3 tools/test_dl263_ci_pin.py"""
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CS = ROOT / "claude/plugins/project-setup/skills/claude-setup"
spec = importlib.util.spec_from_file_location("ci_pin", CS / "assets/ci_pin.py")
ci_pin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci_pin)

TEMPLATE = (CS / "assets/ci/dev-standards.yml").read_text("utf-8")


class Stub:
    def __init__(self, ver="2.4.2", expected="v2.4.2", older=True, known=True):
        self.ver, self.expected, self.older, self.known = ver, expected, older, known

    def docs_version(self):
        return self.ver if self.known else None

    def expected_ref(self):
        return self.expected if self.known else None

    def is_older(self, pin, expected):
        return self.older and pin != expected


def project(ref="v2.3.0"):
    d = Path(tempfile.mkdtemp(prefix="dl263-"))
    wf = d / ci_pin.WORKFLOW
    wf.parent.mkdir(parents=True)
    text = (TEMPLATE.replace("{{DEV_STANDARDS_REPO}}", "owner/tools")
            .replace("{{DEV_STANDARDS_REF}}", ref + "  # pinned")
            .replace("{{DEFAULT_BRANCH}}", "main"))
    wf.write_text(text, encoding="utf-8", newline="")
    return d, wf


def run(d, mode, lookup):
    out = []
    code = ci_pin.run(d, mode, lookup, out.append)
    return code, "\n".join(out)


class CiPin(unittest.TestCase):
    def test_stale_pin_is_flagged(self):
        d, _ = project("v2.3.0")
        code, out = run(d, "status", Stub())
        self.assertEqual(code, 0)
        self.assertIn("dev-standards.yml pins v2.3.0, older than the installed luismc-docs 2.4.2; "
                      "generated docs will fail G1 in CI; run ", out)

    def test_current_pin_is_quiet(self):
        d, _ = project("v2.4.2")
        code, out = run(d, "status", Stub())
        self.assertEqual(code, 0)
        self.assertNotIn("older than", out)

    def test_bump_rewrites_only_ref(self):
        d, wf = project("v2.3.0")
        before = wf.read_text("utf-8").splitlines()
        code, out = run(d, "bump", Stub())
        after = wf.read_text("utf-8").splitlines()
        self.assertEqual(code, 0)
        self.assertIn("v2.3.0 -> v2.4.2", out)
        diff = [(a, b) for a, b in zip(before, after) if a != b]
        self.assertEqual(len(before), len(after))
        self.assertEqual(len(diff), 1)
        self.assertEqual(diff[0][1].strip(), "ref: v2.4.2  # pinned")
        self.assertEqual(run(d, "bump", Stub())[0], 0)  # second run changes nothing
        self.assertEqual(wf.read_text("utf-8").splitlines(), after)

    def test_bump_keeps_crlf(self):
        d, wf = project("v2.3.0")
        wf.write_bytes(wf.read_bytes().replace(b"\n", b"\r\n"))
        run(d, "bump", Stub())
        data = wf.read_bytes()
        self.assertEqual(data.count(b"\n"), data.count(b"\r\n"))
        self.assertIn(b"ref: v2.4.2", data)

    def test_check_exit_codes(self):
        d, _ = project("v2.3.0")
        self.assertEqual(run(d, "check", Stub())[0], 1)
        d2, _ = project("v2.4.2")
        self.assertEqual(run(d2, "check", Stub())[0], 0)

    def test_missing_workflow_is_not_installed(self):
        d = Path(tempfile.mkdtemp(prefix="dl263-"))
        for mode in ("status", "check", "bump"):
            code, out = run(d, mode, Stub())
            self.assertEqual(code, 0)
            self.assertIn("not installed", out)

    def test_unknown_marketplace_is_not_an_error(self):
        d, _ = project("v2.3.0")
        code, out = run(d, "check", Stub(known=False))
        self.assertEqual(code, 0)
        self.assertIn("cannot tell", out)

    def test_unfilled_placeholder(self):
        d, _ = project("{{DEV_STANDARDS_REF}}")
        self.assertEqual(run(d, "check", Stub())[0], 1)

    def test_template_comment_names_command(self):
        self.assertIn("ci_pin.py --bump", TEMPLATE)
        self.assertNotIn("by hand", TEMPLATE)


if __name__ == "__main__":
    unittest.main()
