"""DL245: `install --track rust,ts` merges the files both tracks ship; one track stays as it was."""
import filecmp
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO

import _helpers  # noqa: F401
import delivery_ci_install as INS
import delivery_doctor as DOC

CI = ".github/workflows/ci.yml"
GATE = "scripts/delivery/gate.json"
SCOPE = "scripts/delivery/ci-scope.json"


def run(*argv):
    out = StringIO()
    with redirect_stdout(out), redirect_stderr(StringIO()):
        code = INS.main(list(argv))
    return code, out.getvalue()


def job_ids(text):
    head, rest = text.split("\njobs:\n", 1)
    return re.findall(r"^  ([A-Za-z0-9_-]+):\s*$", rest, re.M)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def path(self, rel):
        return os.path.join(self.tmp, rel.replace("/", os.sep))

    def read(self, rel):
        with open(self.path(rel), encoding="utf-8") as f:
            return f.read()


class Install(Base):
    def setUp(self):
        super().setUp()
        subprocess.run(["git", "init", "-q", self.tmp], check=True)
        self.code, self.out = run("install", "--track", "rust,ts", "--root", self.tmp)

    def test_installs(self):
        self.assertEqual(self.code, 0, self.out)

    def test_ci_yml_has_both_job_sets_with_unique_ids(self):
        ids = job_ids(self.read(CI))
        self.assertEqual(len(ids), len(set(ids)), ids)
        for want in ("decide", "tracks", "verify", "plan", "e2e", "verify-rust", "integration-rust", "integration-pool-rust"):
            self.assertIn(want, ids)
        self.assertEqual(ids.count("decide"), 1)

    def test_aggregate_waits_for_every_track(self):
        text = self.read(CI)
        agg = text[text.index("\n  e2e:\n"):]
        agg = agg[:agg.index("\n  verify-rust:")]
        needs = re.search(r"^    needs: \[(.*)\]", agg, re.M).group(1)
        for want in ("verify", "verify-rust", "integration-rust", "integration-pool-rust", "tracks"):
            self.assertIn(want, needs)
        self.assertIn("needs.verify-rust.result != 'cancelled'", agg)

    def test_every_track_job_is_switched_by_tracks(self):
        text = self.read(CI)
        for jid in ("verify", "verify-rust"):
            block = text[text.index("\n  %s:\n" % jid):]
            ifline = re.search(r"^    if: (.*)$", block, re.M).group(1)
            self.assertIn("needs.tracks.outputs.%s != 'false'" % ("ts" if jid == "verify" else "rust"), ifline)

    def test_workflow_is_valid_yaml(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("no PyYAML")
        data = yaml.safe_load(self.read(CI))
        for name, job in data["jobs"].items():
            for need in job.get("needs", []) if isinstance(job.get("needs"), list) else [job.get("needs")]:
                if need:
                    self.assertIn(need, data["jobs"], "%s needs %s" % (name, need))

    def test_one_gate_with_both_command_sets(self):
        gate = json.loads(self.read(GATE))
        self.assertEqual(gate["track"], ["rust", "ts"])
        names = [s["name"] for s in gate["steps"]]
        self.assertEqual(len(names), len(set(names)))
        runs = " ".join(s["run"] for s in gate["steps"])
        self.assertIn("cargo clippy", runs)
        self.assertIn("pnpm turbo run lint", runs)
        self.assertEqual(names.count("secret-scan"), 1)
        tagged = {s.get("track") for s in gate["steps"]}
        self.assertEqual(tagged, {None, "rust", "ts"})
        self.assertIn("lint-rust", gate["required_steps"])
        self.assertIn("lint-ts", gate["required_steps"])
        self.assertEqual(gate["packages"]["kind"], "pnpm-workspace")
        self.assertEqual(set(gate["scope_map"]) - {"note"}, {"rust", "ts"})

    def test_gate_loads_in_the_engine(self):
        sys.path.insert(0, os.path.join(INS.TEMPLATES, "shared", "scripts", "delivery"))
        try:
            import delivery_common as dc
        finally:
            sys.path.pop(0)
        from pathlib import Path
        cfg = dc.load_gate(Path(self.tmp))
        self.assertEqual(len(cfg["steps"]), len(json.loads(self.read(GATE))["steps"]))
        self.assertEqual(cfg["required_steps"], ["lint-rust", "typecheck-rust", "lint-ts", "typecheck-ts"])

    def test_scope_has_both_tracks(self):
        scope = json.loads(self.read(SCOPE))
        self.assertIn("crates/**", scope["tracks"]["rust"])
        self.assertIn("**/*.rs", scope["tracks"]["rust"])
        self.assertIn("packages/**", scope["tracks"]["ts"])
        self.assertIn("pnpm-lock.yaml", scope["tracks"]["ts"])
        self.assertIn(".github/**", scope["shared"])
        self.assertIn("full_files", scope)

    def test_state_keeps_a_list(self):
        state = json.loads(self.read(INS.STATE))
        self.assertEqual(state["track"], ["rust", "ts"])

    def test_every_track_file_is_there(self):
        self.assertTrue(os.path.exists(self.path("scripts/delivery/rust_ci.py")))
        self.assertTrue(os.path.exists(self.path("scripts/delivery/mock_handler_guard.py")))
        self.assertTrue(os.path.exists(self.path(".github/workflows/nightly-full.yml")))

    def test_files_both_ship_name_the_skipped_track(self):
        # package.yml: the ts copy is left out when the project has no packaged program, so no skipped line;
        # with a Dockerfile both are wanted and the first track's copy wins, with a line that names the file.
        shutil.rmtree(self.tmp)
        os.makedirs(self.tmp)
        with open(os.path.join(self.tmp, "Dockerfile"), "w") as f:
            f.write("FROM scratch\n")
        code, out = run("install", "--track", "rust,ts", "--root", self.tmp)
        self.assertEqual(code, 0, out)
        self.assertIn("note: track ts: .github/workflows/package.yml is also shipped by track rust", out)
        self.assertIn("scripts/delivery/smoke.json", out)

    def test_update_changes_nothing(self):
        before = {rel: self.read(rel) for rel in (CI, GATE, SCOPE)}
        state = self.read(INS.STATE)
        code, out = run("update", "--root", self.tmp)
        self.assertEqual(code, 0, out)
        self.assertIn("using track rust,ts", out)
        self.assertEqual(before, {rel: self.read(rel) for rel in (CI, GATE, SCOPE)})
        self.assertRegex(out, r"summary: 0 written, 0 overwritten, 0 merged, 0 conflict, 0 kept, \d+ same")
        self.assertEqual(state, self.read(INS.STATE))

    def test_project_edit_survives_update(self):
        with open(self.path(CI), "a", encoding="utf-8", newline="\n") as f:
            f.write("# project edit\n")
        with open(self.path(GATE), encoding="utf-8") as f:
            gate = json.load(f)
        gate["timeout_minutes"] = 45
        with open(self.path(GATE), "w", encoding="utf-8") as f:
            json.dump(gate, f, indent=2)
        code, out = run("update", "--root", self.tmp)
        self.assertEqual(code, 0, out)
        self.assertTrue(self.read(CI).endswith("# project edit\n"))
        self.assertEqual(json.loads(self.read(GATE))["timeout_minutes"], 45)

    def test_plugin_owned_file_merges_on_update(self):
        rel = "scripts/delivery/ci_scope.py"
        with open(self.path(rel), "a", encoding="utf-8", newline="\n") as f:
            f.write("# mine\n")
        code, out = run("update", "--root", self.tmp)
        self.assertEqual(code, 0, out)
        self.assertIn("# mine", self.read(rel))

    def test_doctor_reports_both_tracks_without_warning(self):
        items = DOC.scripts_items(self.tmp)
        self.assertEqual(items[0]["status"], "ok", items)
        self.assertIn("rust, ts", items[0]["detail"])

    def test_doctor_warns_when_a_track_file_is_missing(self):
        os.remove(self.path("scripts/delivery/rust_ci.py"))
        items = DOC.scripts_items(self.tmp)
        self.assertEqual(items[0]["status"], "warn")
        self.assertIn("rust_ci.py", items[0]["detail"])
        self.assertIn("--track rust,ts", items[0]["detail"])


class NoPackagedProgram(Base):
    def test_rust_copy_of_package_files_is_installed(self):
        code, out = run("install", "--track", "rust,ts", "--root", self.tmp)
        self.assertEqual(code, 0, out)
        self.assertIn("cargo build", self.read("scripts/delivery/smoke.json"))
        self.assertNotIn("note:", out)
        items = DOC.scripts_items(self.tmp)
        self.assertEqual(items[0]["status"], "ok", items)


class SingleTrack(Base):
    def test_single_track_is_the_template_byte_for_byte(self):
        for track in ("ts", "rust"):
            tmp = tempfile.mkdtemp()
            self.addCleanup(shutil.rmtree, tmp, True)
            code, out = run("install", "--track", track, "--root", tmp)
            self.assertEqual(code, 0, out)
            self.assertNotIn("note:", out)
            for rel in (CI, GATE, ".github/workflows/package.yml"):
                src = os.path.join(INS.TEMPLATES, track, rel.replace("/", os.sep))
                if not os.path.exists(os.path.join(tmp, rel.replace("/", os.sep))):
                    continue
                self.assertTrue(filecmp.cmp(src, os.path.join(tmp, rel.replace("/", os.sep)), shallow=False), (track, rel))
            with open(os.path.join(tmp, INS.STATE.replace("/", os.sep)), encoding="utf-8") as f:
                self.assertEqual(json.load(f)["track"], track)

    def test_plan_matches_the_old_function(self):
        """The old plan (read from main when git has it) gives the same paths, sources and actions."""
        proc = subprocess.run(["git", "show", "origin/main:claude/plugins/delivery/scripts/delivery_ci_install.py"],
                              capture_output=True, cwd=os.path.dirname(INS.__file__))
        if proc.returncode != 0 or b"def track_sources" in proc.stdout:
            self.skipTest("the old installer is not in this clone")
        old_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, old_dir, True)
        old_path = os.path.join(old_dir, "old_install.py")
        scripts = os.path.dirname(INS.__file__)
        with open(old_path, "wb") as f:
            f.write(proc.stdout.replace(b'HERE = os.path.dirname(os.path.abspath(__file__))', ("HERE = %r" % scripts).encode()))
        import importlib.util
        spec = importlib.util.spec_from_file_location("old_install", old_path)
        old = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(old)
        for track in ("ts", "rust"):
            for mode in ("install", "update"):
                self.assertEqual(old.plan(track, self.tmp, mode), INS.plan(track, self.tmp, mode), (track, mode))
                self.assertEqual(INS.plan([track], self.tmp, mode), INS.plan(track, self.tmp, mode))


class TracksJob(Base):
    """The inline script of the `tracks` job picks the tracks from the changed files."""

    def script(self):
        run("install", "--track", "rust,ts", "--root", self.tmp)
        text = self.read(CI)
        m = re.search(r"python3 - <<'PY'\n(.*?)\n          PY\n", text, re.S)
        return "\n".join(l[10:] for l in m.group(1).split("\n"))

    def pick(self, files):
        script = self.script()
        subprocess.run(["git", "init", "-q", self.tmp], check=True)
        env = dict(os.environ, EVENT="pull_request", BASE_SHA="base", GITHUB_OUTPUT=os.path.join(self.tmp, "out.txt"))
        fake = "import subprocess as _s\n_r = _s.run\nclass _P:\n    stdout = %r\n" % "\n".join(files)
        fake += "def _run(cmd, **kw):\n    return _P()\n_s.run = _run\n"
        subprocess.run([sys.executable, "-c", fake + script], cwd=self.tmp, env=env, check=True, capture_output=True)
        with open(env["GITHUB_OUTPUT"]) as f:
            return dict(l.strip().split("=") for l in f if "=" in l)

    def test_rust_change_runs_rust_only(self):
        self.assertEqual(self.pick(["crates/core/src/lib.rs"]), {"rust": "true", "ts": "false"})

    def test_pnpm_change_runs_ts_only(self):
        self.assertEqual(self.pick(["packages/ui/src/a.tsx", "apps/admin/vite.config.ts"]), {"rust": "false", "ts": "true"})

    def test_shared_or_unknown_runs_all(self):
        self.assertEqual(self.pick([".github/workflows/ci.yml"]), {"rust": "true", "ts": "true"})
        self.assertEqual(self.pick(["README.txt"]), {"rust": "true", "ts": "true"})

    def test_mixed_change_runs_both(self):
        self.assertEqual(self.pick(["Cargo.lock", "pnpm-lock.yaml"]), {"rust": "true", "ts": "true"})


class Names(unittest.TestCase):
    def test_parse_tracks(self):
        self.assertEqual(INS.parse_tracks("rust,ts"), ["rust", "ts"])
        self.assertEqual(INS.parse_tracks(" ts , ts"), ["ts"])
        self.assertEqual(INS.parse_tracks(["rust"]), ["rust"])
        self.assertEqual(INS.track_value(["ts"]), "ts")
        self.assertEqual(INS.track_value(["rust", "ts"]), ["rust", "ts"])

    def test_bad_track_exits_1(self):
        self.assertEqual(run("install", "--track", "rust,java", "--root", tempfile.mkdtemp())[0], 1)

    def test_merge_is_deterministic(self):
        a = INS.track_sources(["rust", "ts"])
        b = INS.track_sources(["rust", "ts"])
        for rel in (CI, GATE, SCOPE):
            with open(a[rel], "rb") as fa, open(b[rel], "rb") as fb:
                self.assertEqual(fa.read(), fb.read())


if __name__ == "__main__":
    unittest.main()
