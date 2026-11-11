"""DL256: guided setup takes a list of tracks; the gate gives each package its own kind."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

import _helpers  # noqa: F401
import delivery_ci_install as INS
import delivery_ci_setup as S

sys.path.insert(0, os.path.join(INS.TEMPLATES, "shared", "scripts", "delivery"))
try:
    import delivery_common as dc
finally:
    sys.path.pop(0)

OPTIONS = {"linux": 2}
HOSTED = {"runner": {"linux": "ubuntu-4core"}, "larger": True, "monthly_minutes_cap": None, "windows_small_set_only": True}


def write(root, rel, text=""):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="dl256-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def mixed(self):
        write(self.tmp, "Cargo.toml", '[workspace]\nmembers = ["crates/*"]\n')
        write(self.tmp, "crates/core/Cargo.toml", '[package]\nname = "core"\n')
        write(self.tmp, "package.json", "{}")
        write(self.tmp, "pnpm-workspace.yaml", "packages:\n  - 'web/*'\n")
        write(self.tmp, "web/app/package.json", '{"name": "app"}')


class Detect(Base):
    def test_rust_and_ts_both_found_in_stable_order(self):
        write(self.tmp, "Cargo.toml")
        write(self.tmp, "package.json")
        self.assertEqual(S.detect_tracks(self.tmp), ["ts", "rust"])
        self.assertEqual(S.facts(self.tmp)["tracks"], ["ts", "rust"])

    def test_dotnet_and_go(self):
        write(self.tmp, "go.mod")
        write(self.tmp, "App.csproj")
        self.assertEqual(S.detect_tracks(self.tmp), ["go", "dotnet"])

    def test_one_track_keeps_the_old_facts_shape(self):
        write(self.tmp, "package.json")
        self.assertEqual(S.facts(self.tmp)["track"], "ts")


class Validate(unittest.TestCase):
    def test_forms(self):
        self.assertEqual(S.validate({"track": "rust", "options": OPTIONS, "github_hosted": HOSTED}), [])
        self.assertEqual(S.validate({"track": ["rust", "ts"], "options": OPTIONS, "github_hosted": HOSTED}), [])

    def test_bad_names_and_empty(self):
        self.assertTrue(S.validate({"track": ["rust", "php"], "options": OPTIONS, "github_hosted": HOSTED}))
        self.assertTrue(S.validate({"track": [], "options": OPTIONS, "github_hosted": HOSTED}))
        self.assertTrue(S.validate({"track": 3, "options": OPTIONS, "github_hosted": HOSTED}))


class Apply(Base):
    def run_apply(self, track):
        write(self.tmp, ".delivery/config.json", "{}")
        ans = os.path.join(self.tmp, "answers.json")
        write(self.tmp, "answers.json", json.dumps({"track": track, "options": OPTIONS, "github_hosted": HOSTED}))
        out = StringIO()
        with mock.patch.object(INS, "plan", return_value=[]) as plan, mock.patch.object(INS, "apply"), \
                mock.patch("delivery_doctor.run_checks", return_value=[]), \
                redirect_stdout(out), redirect_stderr(StringIO()):
            code = S.main(["apply", "--answers", ans, "--root", self.tmp])
        return code, out.getvalue(), plan

    def test_list_passes_both_tracks(self):
        code, out, plan = self.run_apply(["rust", "ts"])
        self.assertEqual(code, 0, out)
        self.assertEqual(plan.call_args[0][0], ["rust", "ts"])
        self.assertIn("Tracks: rust, ts", out)

    def test_string_still_works(self):
        code, out, plan = self.run_apply("go")
        self.assertEqual(code, 0, out)
        self.assertEqual(plan.call_args[0][0], "go")
        self.assertIn("Tracks: go", out)


class GateKinds(Base):
    def cfg(self, **extra):
        cfg = {"packages": {"kind": "pnpm-workspace"}}
        cfg.update(extra)
        return cfg

    def test_each_package_has_its_own_kind(self):
        self.mixed()
        by = {"rust": {"kind": "cargo-workspace"}, "ts": {"kind": "pnpm-workspace"}}
        kinds = dc.package_kinds(Path(self.tmp), self.cfg(packages_by_track=by))
        self.assertEqual(kinds, {"crates/core": "cargo-workspace", "web/app": "pnpm-workspace"})

    def test_old_one_kind_config_is_unchanged(self):
        self.mixed()
        cfg = self.cfg()
        self.assertEqual(dc.package_kinds(Path(self.tmp), cfg), {"web/app": "pnpm-workspace"})
        self.assertEqual(dc.discover_packages(Path(self.tmp), cfg["packages"]), ["web/app"])

    def test_step_gets_only_its_tracks_packages(self):
        ctx = mock.Mock(package_kinds={"crates/core": "cargo-workspace", "web/app": "pnpm-workspace"})
        dirs = ["crates/core", "web/app"]
        self.assertEqual(dc.step_dirs({"track": "rust"}, ctx, dirs), ["crates/core"])
        self.assertEqual(dc.step_dirs({"track": "ts"}, ctx, dirs), ["web/app"])
        self.assertEqual(dc.step_dirs({}, ctx, dirs), dirs)

    def test_single_kind_gives_every_dir_to_every_step(self):
        ctx = mock.Mock(package_kinds={"a": "pnpm-workspace", "b": "pnpm-workspace"})
        self.assertEqual(dc.step_dirs({"track": "rust"}, ctx, ["a", "b"]), ["a", "b"])


if __name__ == "__main__":
    unittest.main()
