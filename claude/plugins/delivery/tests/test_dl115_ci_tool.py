"""DL115: ci_tool.py fetches pinned tools into a cache with retries and checksum checks."""
import contextlib
import hashlib
import io
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

DELIVERY = Path(__file__).resolve().parent.parent / "templates" / "shared" / "scripts" / "delivery"
sys.path.insert(0, str(DELIVERY))
import ci_tool  # noqa: E402

BODY = b"tool-bytes-for-dl115"
SHA = hashlib.sha256(BODY).hexdigest()


class Server:
    def __init__(self, fail_first=0, always_fail=False):
        self.hits = 0
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                outer.hits += 1
                if always_fail or outer.hits <= fail_first:
                    self.send_response(504)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Length", str(len(BODY)))
                self.end_headers()
                self.wfile.write(BODY)

            def log_message(self, *a):
                pass

        self.httpd = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_port}/tool.bin"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class CiToolTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = {"CI_TOOLS_DIR": self.tmp.name, "CI_TOOL_RETRY_DELAY": "0"}
        for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            env[k] = ""
        env["NO_PROXY"] = "127.0.0.1"
        p = mock.patch.dict(os.environ, env)
        p.start()
        self.addCleanup(p.stop)
        self.target = Path(self.tmp.name) / "t" / "1" / "tool.bin"

    def serve(self, **kw):
        s = Server(**kw)
        self.addCleanup(s.close)
        return s

    def run_main(self, url, sha=SHA):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = ci_tool.main(["fetch", url, "--sha256", sha, "--name", "t/1/tool.bin"])
        return code, out.getvalue(), err.getvalue()

    def no_partial(self):
        self.assertEqual([p for p in Path(self.tmp.name).rglob("*.partial")], [])

    def test_first_fetch_downloads_and_verifies(self):
        s = self.serve()
        code, out, _ = self.run_main(s.url)
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), str(self.target.resolve()))
        self.assertEqual(self.target.read_bytes(), BODY)
        self.no_partial()

    def test_second_fetch_makes_no_request(self):
        s = self.serve()
        self.run_main(s.url)
        code, out, _ = self.run_main(s.url)
        self.assertEqual((code, s.hits), (0, 1))
        self.assertEqual(out.strip(), str(self.target.resolve()))

    def test_corrupted_cache_is_replaced(self):
        s = self.serve()
        self.run_main(s.url)
        self.target.write_bytes(b"bad")
        code, _, _ = self.run_main(s.url)
        self.assertEqual((code, s.hits), (0, 2))
        self.assertEqual(self.target.read_bytes(), BODY)

    def test_wrong_pin_exits_1_and_leaves_no_file(self):
        s = self.serve()
        code, out, err = self.run_main(s.url, sha="0" * 64)
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("checksum mismatch", err)
        self.assertFalse(self.target.exists())
        self.no_partial()

    def test_retries_after_504(self):
        s = self.serve(fail_first=2)
        code, _, _ = self.run_main(s.url)
        self.assertEqual((code, s.hits), (0, 3))
        self.no_partial()

    def test_always_failing_server_stops_after_5_attempts(self):
        s = self.serve(always_fail=True)
        code, out, err = self.run_main(s.url)
        self.assertEqual((code, s.hits, out), (1, 5, ""))
        self.assertIn("5 attempts", err)
        self.assertIn(s.url, err)
        self.assertFalse(self.target.exists())
        self.no_partial()

    def test_ci_tools_dir_is_honoured(self):
        self.assertEqual(ci_tool.cache_dir(), Path(self.tmp.name).resolve())

    def test_usage_error_exits_2(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(ci_tool.main(["fetch", "http://x"]), 2)
            self.assertEqual(ci_tool.main(["fetch", "http://x", "--sha256", SHA, "--name", "bad"]), 2)

    def test_gitleaks_extracts_binary_once(self):
        import io as _io, tarfile
        buf = _io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as t:
            info = tarfile.TarInfo("gitleaks")
            info.size = 3
            t.addfile(info, _io.BytesIO(b"bin"))
        data = buf.getvalue()
        a = Path(self.tmp.name) / "gitleaks" / "9.9.9" / "gitleaks_9.9.9_linux_x64.tar.gz"
        a.parent.mkdir(parents=True)
        a.write_bytes(data)
        pin = {"gitleaks": {"version": "9.9.9", "sha256": {"linux_x64": hashlib.sha256(data).hexdigest()}}}
        fake = Path(self.tmp.name) / "x" / "ci_tool.py"
        fake.parent.mkdir()
        (fake.parent / "tools.json").write_text(__import__("json").dumps(pin))
        with mock.patch.object(ci_tool, "__file__", str(fake)):
            p1 = ci_tool.gitleaks("linux_x64")
            p2 = ci_tool.gitleaks("linux_x64")
        self.assertEqual(p1, p2)
        self.assertEqual(p1.read_bytes(), b"bin")
        self.assertTrue(os.access(p1, os.X_OK))


if __name__ == "__main__":
    unittest.main()
