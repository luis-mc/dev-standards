import io
import json
import os
import sys
import tempfile
import unittest
import zoneinfo
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from _helpers import L, make_root
import delivery_doctor as D
import delivery_config as C


def stub_gh(rc):
    d = Path(tempfile.mkdtemp(prefix="ghstub-"))
    (d / "gh.py").write_text("import sys\nsys.exit(%d)\n" % rc)
    return str(d / "gh.py")


def enabled_root(cfg=None, plugin_id="luismc-delivery@dev-standards"):
    root = make_root(cfg if cfg is not None else {})
    (root / ".claude").mkdir()
    (root / ".claude" / "settings.json").write_text(json.dumps({"enabledPlugins": {plugin_id: True}}))
    return root


def run(root, gh_rc=0, home=None):
    env = {"DELIVERY_GH": stub_gh(gh_rc), "HOME": home or tempfile.mkdtemp(), "USERPROFILE": home or tempfile.mkdtemp()}
    with mock.patch.dict(os.environ, env):
        return {r["check"]: r for r in D.run_checks(str(root))}


class DoctorTests(unittest.TestCase):
    def test_all_ok(self):
        res = run(enabled_root({"tz": "Europe/Lisbon"}))
        self.assertTrue(all(r["ok"] for r in res.values()), res)
        self.assertEqual(set(res), {"config", "gh", "tz", "hooks", "ledger"})

    def test_invalid_config_fails(self):
        res = run(enabled_root({"enforcement": {"mode": "stop"}}))
        self.assertFalse(res["config"]["ok"])
        self.assertIn("enforcement.mode", res["config"]["detail"])

    def test_gh_not_signed_in_fails(self):
        res = run(enabled_root(), gh_rc=1)
        self.assertFalse(res["gh"]["ok"])
        self.assertIn("gh auth login", res["gh"]["detail"])

    def test_gh_missing_fails(self):
        root = enabled_root()
        with mock.patch.dict(os.environ, {"DELIVERY_GH": "/nonexistent/gh"}):
            self.assertFalse({r["check"]: r for r in D.run_checks(str(root))}["gh"]["ok"])

    def test_bad_tz_fails_loudly_not_utc(self):
        res = run(enabled_root({"tz": "Mars/Base"}))
        self.assertFalse(res["tz"]["ok"])
        self.assertIn("tzdata", res["tz"]["detail"])

    def test_missing_tzdata_fails_for_a_real_zone_but_utc_still_works(self):
        err = zoneinfo.ZoneInfoNotFoundError("No time zone found with key Europe/Lisbon")
        with mock.patch("zoneinfo.ZoneInfo", side_effect=err):
            self.assertFalse(run(enabled_root({"tz": "Europe/Lisbon"}))["tz"]["ok"])
            self.assertTrue(run(enabled_root({"tz": "UTC"}))["tz"]["ok"])

    def test_ledger_owner_tz_warns_on_stderr_before_falling_back(self):
        L._TZ_WARNED.clear()
        err = io.StringIO()
        with mock.patch("zoneinfo.ZoneInfo", side_effect=zoneinfo.ZoneInfoNotFoundError("x")), redirect_stderr(err):
            tz = L.owner_tz(cfg={"tz": "Europe/Lisbon"})
            L.owner_tz(cfg={"tz": "Europe/Lisbon"})
        self.assertEqual(tz, L.timezone.utc)
        self.assertEqual(err.getvalue().count("cannot be loaded"), 1)
        self.assertIn("tzdata", err.getvalue())

    def test_hooks_need_plugin_enabled(self):
        res = run(make_root({}))
        self.assertFalse(res["hooks"]["ok"])
        self.assertIn("enabledPlugins", res["hooks"]["detail"])
        home = tempfile.mkdtemp()
        (Path(home) / ".claude").mkdir()
        (Path(home) / ".claude" / "settings.json").write_text(json.dumps({"enabledPlugins": {"luismc-delivery@x": True}}))
        self.assertTrue(run(make_root({}), home=home)["hooks"]["ok"])
        off = enabled_root()
        (off / ".claude" / "settings.json").write_text(json.dumps({"enabledPlugins": {"luismc-delivery@x": False}}))
        self.assertFalse(run(off)["hooks"]["ok"])

    def test_hooks_json_missing_script_fails(self):
        root = enabled_root()
        with mock.patch.object(D, "HOOK_SCRIPTS", ("hook_nope.py",)):
            self.assertFalse(run(root)["hooks"]["ok"])

    def test_ledger_unwritable_or_corrupt_fails(self):
        root = enabled_root()
        (root / ".delivery" / "ledger.json").write_text("{nope")
        self.assertFalse(run(root)["ledger"]["ok"])
        (root / ".delivery" / "ledger.json").write_text("{}")
        self.assertTrue(run(root)["ledger"]["ok"])
        with mock.patch("tempfile.mkstemp", side_effect=PermissionError("denied")):
            res = run(root)
        self.assertFalse(res["ledger"]["ok"])
        self.assertIn("not writable", res["ledger"]["detail"])

    def test_cli_exit_codes_and_output(self):
        root = enabled_root({"tz": "Mars/Base"})
        buf = io.StringIO()
        with mock.patch.dict(os.environ, {"DELIVERY_GH": stub_gh(0)}), redirect_stdout(buf):
            self.assertEqual(D.main(["self-check", "--root", str(root)]), 1)
        self.assertIn("FAIL tz", buf.getvalue())
        with redirect_stderr(io.StringIO()):
            self.assertEqual(D.main(["--root", tempfile.mkdtemp()]), 2)
        ok = enabled_root({"tz": "Europe/Lisbon"})
        buf = io.StringIO()
        with mock.patch.dict(os.environ, {"DELIVERY_GH": stub_gh(0)}), redirect_stdout(buf):
            self.assertEqual(D.main(["--root", str(ok), "--json"]), 0)
        self.assertTrue(json.loads(buf.getvalue())["ok"])


if __name__ == "__main__":
    unittest.main()
