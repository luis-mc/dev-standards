"""DL157: the installer installs tzdata when the configured tz does not load (fake pip, fake zoneinfo)."""
import json
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

import _helpers  # noqa: F401
import delivery_ci_install as INS


class Fake:
    """zoneinfo that fails until pip has run; pip is recorded, never run."""
    def __init__(self, pip_rc=0, fixes=True):
        self.calls, self.installed, self.pip_rc, self.fixes = [], False, pip_rc, fixes

    def zone(self, name):
        if not self.installed:
            raise KeyError(name)
        return object()

    def run(self, cmd, **kw):
        self.calls.append(cmd)
        if self.pip_rc == 0 and self.fixes:
            self.installed = True
        return types.SimpleNamespace(returncode=self.pip_rc, stdout="", stderr="no network")


class Tz(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / ".delivery").mkdir()
        self.cfg({"tz": "Europe/Lisbon"})

    def cfg(self, d):
        (self.root / ".delivery" / "config.json").write_text(json.dumps(d))

    def go(self, fake, **kw):
        out = StringIO()
        mod = types.SimpleNamespace(ZoneInfo=fake.zone)
        with mock.patch.dict(sys.modules, {"zoneinfo": mod}), mock.patch.object(INS.subprocess, "run", fake.run), \
                redirect_stdout(out):
            INS.ensure_tzdata(str(self.root), **kw)
        return out.getvalue()

    def test_installs_when_missing(self):
        f = Fake()
        out = self.go(f, interactive=False)
        self.assertEqual(len(f.calls), 1)
        self.assertEqual(f.calls[0][1:], ["-m", "pip", "install", "--user", "tzdata"])
        self.assertIn("loads now", out)

    def test_loads_already_no_pip(self):
        f = Fake()
        f.installed = True
        self.go(f, interactive=False)
        self.assertEqual(f.calls, [])

    def test_no_tz_no_pip(self):
        self.cfg({})
        f = Fake()
        self.go(f, interactive=False)
        self.assertEqual(f.calls, [])

    def test_interactive_decline(self):
        f = Fake()
        out = self.go(f, interactive=True, ask=lambda _p: "n")
        self.assertEqual(f.calls, [])
        self.assertIn("not installed", out)

    def test_interactive_accept(self):
        f = Fake()
        self.go(f, interactive=True, ask=lambda _p: "")
        self.assertEqual(len(f.calls), 1)

    def test_pip_failure_reported(self):
        f = Fake(pip_rc=1)
        out = self.go(f, interactive=False)
        self.assertIn("install failed", out)
        self.assertIn("no network", out)

    def test_still_fails_after_pip(self):
        f = Fake(fixes=False)
        out = self.go(f, interactive=False)
        self.assertIn("still does not load", out)


if __name__ == "__main__":
    unittest.main()
