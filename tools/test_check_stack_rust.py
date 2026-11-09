"""Tests for Rust as a component in check_stack.py (DS196)."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CHECK = (Path(__file__).resolve().parent.parent / "claude/plugins/project-setup/skills/"
         "tech-stack-setup/assets/check_stack.py")


def run(text, mode="--selection"):
    if mode == "--catalog":
        return subprocess.run([sys.executable, str(CHECK), "--catalog"],
                              capture_output=True, text=True)
    f = Path(tempfile.mkdtemp()) / "sel.yaml"
    f.write_text(text)
    return subprocess.run([sys.executable, str(CHECK), "--selection", str(f)],
                          capture_output=True, text=True)


class RustComponent(unittest.TestCase):
    def test_catalog_clean(self):
        p = run("", "--catalog")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_component_beside_ts_on_vercel_is_viable(self):
        p = run("api: typescript\nhosting: vercel\ncomponents:\n"
                "  - {id: rust, parts: [cli], reason: single static binary}\n")
        self.assertEqual(p.returncode, 0, p.stdout)
        self.assertNotIn("WARN", p.stdout)

    def test_rust_as_api_on_vercel_still_blocked(self):
        p = run("language: rust\nhosting: vercel\n")
        self.assertEqual(p.returncode, 1)

    def test_component_without_reason_warns(self):
        p = run("api: typescript\ncomponents: [rust]\n")
        self.assertEqual(p.returncode, 0)
        self.assertIn("without a recorded reason", p.stdout)

    def test_napi_without_matrix_warns(self):
        p = run("api: typescript\ncomponents:\n  - {id: rust, reason: x, parts: [library-napi]}\n")
        self.assertIn("napi addon without a build matrix", p.stdout)
        p = run("api: typescript\ncomponents:\n  - {id: rust, reason: x, parts: [library-napi],"
                " build_matrix: [linux-x64]}\n")
        self.assertNotIn("build matrix", p.stdout)

    def test_cross_compile_without_licence_warns(self):
        p = run("api: typescript\ncomponents:\n  - {id: rust, reason: x, cross_compile: true}\n")
        self.assertIn("without a licence note", p.stdout)
        p = run("api: typescript\ncomponents:\n  - {id: rust, reason: x, cross_compile: true,"
                " licence_note: accepted once}\n")
        self.assertNotIn("licence note", p.stdout)

    def test_napi_on_vercel_warns(self):
        p = run("api: typescript\nhosting: vercel\ncomponents:\n"
                "  - {id: rust, reason: x, parts: [library-napi], build_matrix: [linux-x64]}\n")
        self.assertIn("Vercel Linux arch", p.stdout)

    def test_windows_host_service_needs_build_option(self):
        p = run("api: typescript\ncomponents:\n  - {id: rust, reason: x, parts: [host-service],"
                " targets: [windows]}\n")
        self.assertIn("Windows target", p.stdout)

    def test_bad_part_and_bad_component_error(self):
        p = run("api: typescript\ncomponents:\n  - {id: rust, parts: [worker]}\n")
        self.assertEqual(p.returncode, 1)
        p = run("api: typescript\ncomponents: [go]\n")
        self.assertEqual(p.returncode, 1)


if __name__ == "__main__":
    unittest.main()
