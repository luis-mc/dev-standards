"""CIR10 S6: the guided CI setup (delivery_ci_setup.py), the by-hand list and the doctor's checks of it, with a fake gh."""
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

from _helpers import make_root
import delivery_ci_setup as S
import delivery_config as C
import delivery_doctor as D

FAKE_GH = '''
import json, os, sys
st = json.load(open(os.environ["FAKE_GH_STATE"]))
a = sys.argv[1:]
if a[:2] == ["auth", "status"]:
    sys.exit(0)
if a[:2] == ["variable", "set"]:
    sys.exit(0)
if a[:2] == ["variable", "get"]:
    v = st.get("vars", {}).get(a[2])
    if v is None:
        sys.exit(1)
    print(v)
    sys.exit(0)
path = a[1] if a[:1] == ["api"] else ""
for key, val in st.get("api", {}).items():
    if path.startswith(key):
        if val is None:
            sys.exit(1)
        print(json.dumps(val))
        sys.exit(0)
sys.exit(1)
'''

MACHINE = {"name": "pc1", "os": "linux", "labels": ["self-hosted", "linux"]}
OPT1 = {"track": "ts", "options": {"linux": 1},
        "self_hosted": {"machines": [MACHINE, {"name": "win1", "os": "windows", "labels": ["self-hosted", "windows"]}],
                        "serial": True, "wait_min": 10,
                        "limits": {"pc1": {"memory_pct": 85, "cpu_pct": 60}, "win1": {"memory_pct": 80, "cpu_pct": 50}}}}
OPT2 = {"track": "ts", "options": {"linux": 2, "windows": 2},
        "github_hosted": {"runner": {"linux": "ubuntu-4core", "windows": "windows-latest"}, "larger": True,
                          "monthly_minutes_cap": None, "windows_small_set_only": True}}
OPT3 = {"track": "ts", "options": {"linux": 3},
        "cloud": {"repo": "o/r", "branches": ["release/*"], "shard_timeout_min": 30, "status_token_env": "CI_STATUS_TOKEN",
                  "max_sessions_per_day": 4}}
TABLE = {"schema": 1, "shards": [{"id": "unit", "os": "linux", "commands": ["echo ok"], "context": "unit (linux)"}]}


def load(root):
    with open(C.config_file(root), encoding="utf-8") as f:
        return json.load(f)


def cli(*argv, stdin=None):
    out, err = StringIO(), StringIO()
    with redirect_stdout(out), redirect_stderr(err), mock.patch("sys.stdin", StringIO(stdin or "")):
        code = S.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="gh-")
        self.gh = os.path.join(self.tmp, "fake_gh.py")
        Path(self.gh).write_text(FAKE_GH)
        self.state = os.path.join(self.tmp, "state.json")
        self.fake({})
        env = mock.patch.dict(os.environ, {"DELIVERY_GH": self.gh, "FAKE_GH_STATE": self.state, "CI_STATUS_TOKEN": ""})
        env.start()
        self.addCleanup(env.stop)

    def fake(self, st):
        Path(self.state).write_text(json.dumps(st))

    def project(self, answers):
        root = make_root({})
        code, out, err = cli("apply", "--answers", "-", "--root", str(root), "--no-install", stdin=json.dumps(answers))
        self.assertEqual(code, 0, err)
        wf = Path(root) / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "ci.yml").write_text("on: push\n")
        return root

    def ci(self, root):
        return D.check_ci(str(root), load(root))


class NoDefaultTests(Base):
    def refused(self, answers):
        root = make_root({})
        code, _o, err = cli("apply", "--answers", "-", "--root", str(root), "--no-install", stdin=json.dumps(answers))
        self.assertEqual(code, 1)
        self.assertEqual(load(root), {})
        return err

    def test_nothing_answered_is_refused(self):
        self.assertIn("options:", self.refused({}))

    def test_option_1_needs_every_answer(self):
        err = self.refused({"options": {"linux": 1}, "self_hosted": {"machines": [MACHINE]}})
        for part in ("serial", "wait_min", "limits.pc1"):
            self.assertIn(part, err)

    def test_caps_must_be_answered_even_if_null(self):
        a = json.loads(json.dumps(OPT3))
        del a["cloud"]["max_sessions_per_day"]
        self.assertIn("max_sessions_per_day", self.refused(a))
        b = json.loads(json.dumps(OPT2))
        del b["github_hosted"]["monthly_minutes_cap"]
        self.assertIn("monthly_minutes_cap", self.refused(b))
        # null is an answer: the owner chose no cap
        self.assertEqual(S.validate(OPT2), [])

    def test_cloud_is_linux_only_and_track_is_needed(self):
        a = json.loads(json.dumps(OPT3))
        a["options"]["windows"] = 3
        self.assertIn("Linux only", " ".join(S.validate(a)))
        root = make_root({})
        code, _o, err = cli("apply", "--answers", "-", "--root", str(root),
                            stdin=json.dumps({k: v for k, v in OPT3.items() if k != "track"}))
        self.assertEqual(code, 1)
        self.assertIn("track", err)

    def test_missing_delivery_folder(self):
        self.assertEqual(cli("facts", "--root", tempfile.mkdtemp())[0], 2)


class ApplyTests(Base):
    def test_option_1_writes_config_runners_and_limits(self):
        root = self.project(OPT1)
        cfg = load(root)
        self.assertEqual(cfg["ci"]["options"], {"linux": "self-hosted"})
        self.assertTrue(cfg["ci"]["guided"])
        self.assertEqual({r["name"] for r in cfg["runners"]}, {"pc1", "win1"})
        self.assertEqual(cfg["ci"]["limits"]["pc1"], {"memory_pct": 85, "cpu_pct": 60})
        self.assertEqual(C.validate_file(C.config_file(root))[0], [])

    def test_option_2_and_3_configs_validate(self):
        for a in (OPT2, OPT3):
            self.assertEqual(C.validate_file(C.config_file(self.project(a)))[0], [])
        cfg = load(self.project(OPT3))
        self.assertEqual(cfg["ci"]["cloud"]["max_sessions_per_day"], 4)
        self.assertNotIn("CI_STATUS_TOKEN_VALUE", json.dumps(cfg))

    def test_install_runs_and_the_output_has_the_list_and_the_way_back(self):
        root = make_root({})
        code, out, err = cli("apply", "--answers", "-", "--root", str(root), stdin=json.dumps(OPT2))
        self.assertEqual(code, 0, err)
        self.assertTrue((Path(root) / ".github" / "workflows" / "ci.yml").exists())
        self.assertIn("Installer:", out)
        self.assertIn("Doctor", out)
        self.assertIn("By hand", out)
        self.assertIn("run /delivery-ci-setup again", out)

    def test_rerun_replaces_the_choice_and_drops_stale_confirmations(self):
        root = self.project(OPT2)
        cli("confirm", "spending-limit", "--root", str(root))
        self.assertIn("spending-limit", load(root)["ci"]["confirmed"])
        cli("apply", "--answers", "-", "--root", str(root), "--no-install", stdin=json.dumps(OPT3))
        cfg = load(root)
        self.assertEqual(cfg["ci"]["options"], {"linux": "cloud"})
        self.assertEqual(cfg["ci"]["confirmed"], [])
        self.assertNotIn("hosted", cfg["ci"])

    def test_set_variables_calls_gh(self):
        root = make_root({})
        code, out, _e = cli("apply", "--answers", "-", "--root", str(root), "--no-install", "--set-variables", stdin=json.dumps(OPT1))
        self.assertEqual(code, 0)
        self.assertIn("CI_RUNS_ON: set", out)
        self.assertIn("CI_SERIAL: set", out)

    def test_confirm_refuses_an_unknown_item(self):
        root = self.project(OPT2)
        self.assertEqual(cli("confirm", "nope", "--root", str(root))[0], 1)
        self.assertEqual(cli("confirm", "--root", str(root))[0], 1)

    def test_facts(self):
        root = make_root({})
        (Path(root) / "package.json").write_text("{}")
        code, out, _e = cli("facts", "--root", str(root))
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["track"], "ts")


class ListMatchesDoctorTests(Base):
    """The printed list and the doctor read the same function: each printed item has exactly one doctor line."""

    def test_every_listed_item_is_checked_by_the_doctor(self):
        for answers in (OPT1, OPT2, OPT3, {**OPT1, "options": {"linux": 1, "windows": 2}, **{k: OPT2[k] for k in ("github_hosted",)}}):
            root = self.project(answers)
            cfg = load(root)
            items = S.by_hand_items(cfg)
            self.assertTrue(items)
            code, out, _e = cli("checklist", "--root", str(root), "--json")
            self.assertEqual([i["id"] for i in json.loads(out)], [i["id"] for i in items])
            ok, detail = self.ci(root)
            mentioned = {i["id"] for i in items if i["id"] in detail}
            for it in items:
                state, _d = S.check_item(str(root), cfg, it)
                self.assertIn(state, ("ok", "confirmed", "open", "unknown"))
                if state in ("open", "unknown"):
                    self.assertIn(it["id"], mentioned, "%s is open but the doctor does not name it" % it["id"])
            self.assertEqual(ok, not (mentioned))

    def test_printed_list_numbers_each_item_id(self):
        root = self.project(OPT3)
        lines = S.format_checklist(S.by_hand_items(load(root)))
        text = "\n".join(lines)
        for n, it in enumerate(S.by_hand_items(load(root)), 1):
            self.assertIn("%d. [%s]" % (n, it["id"]), text)

    def test_unguided_project_is_unchanged(self):
        root = make_root({"ci": {"options": {"linux": "github-hosted"}}})
        wf = Path(root) / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "ci.yml").write_text("on: push\n")
        self.assertEqual(S.check_by_hand(str(root), load(root)), ([], []))
        self.assertTrue(self.ci(root)[0])


class Option1DoctorTests(Base):
    def cfg(self, root):
        return load(root)

    def runners(self, **kw):
        online = {"id": 1, "name": "pc1", "status": kw.get("status", "online"),
                  "labels": [{"name": n} for n in kw.get("labels", ["self-hosted", "linux", "X64"])]}
        return {"runners": [online] if kw.get("present", True) else []}

    def test_runner_not_registered_is_open(self):
        root = self.project(OPT1)
        self.fake({"api": {"repos/{owner}/{repo}/actions/runners": self.runners(present=False)}, "vars": {}})
        ok, detail = self.ci(root)
        self.assertFalse(ok)
        self.assertIn("runner:pc1", detail)
        self.assertIn("no runner named pc1", detail)

    def test_offline_and_missing_label(self):
        root = self.project(OPT1)
        self.fake({"api": {"repos/{owner}/{repo}/actions/runners": self.runners(status="offline")}})
        self.assertIn("offline", self.ci(root)[1])
        self.fake({"api": {"repos/{owner}/{repo}/actions/runners": self.runners(labels=["self-hosted"])}})
        self.assertIn("lacks the labels linux", self.ci(root)[1])

    def test_everything_done_still_needs_the_machine_confirmations(self):
        root = self.project(OPT1)
        self.fake({"api": {"repos/{owner}/{repo}/actions/runners": self.runners()},
                   "vars": {"CI_RUNS_ON": '["self-hosted", "linux"]', "CI_SERIAL": "true"}})
        ok, detail = self.ci(root)
        self.assertFalse(ok)
        self.assertIn("load-gate:pc1", detail)
        self.assertNotIn("runner:pc1:", detail)
        self.assertNotIn("var:CI_RUNS_ON:", detail)
        cli("confirm", "load-gate:pc1", "--root", str(root))
        ok, detail = self.ci(root)
        self.assertTrue(ok, detail)
        self.assertIn("confirmed by the owner", detail)

    def test_cannot_list_runners_is_unknown_until_confirmed(self):
        root = self.project(OPT1)
        self.fake({"api": {"repos/{owner}/{repo}/actions/runners": None}})
        self.assertIn("cannot list runners", self.ci(root)[1])
        cli("confirm", "runner:pc1", "--root", str(root))
        self.assertNotIn("by hand, runner:pc1", self.ci(root)[1])

    def test_wrong_variable_value(self):
        root = self.project(OPT1)
        self.fake({"vars": {"CI_RUNS_ON": '"ubuntu-latest"'}})
        self.assertIn("CI_RUNS_ON is \"ubuntu-latest\", expected", self.ci(root)[1])

    def test_a_windows_machine_gets_windows_commands(self):
        a = json.loads(json.dumps(OPT1))
        a["options"] = {"linux": 1, "windows": 1}
        root = self.project(a)
        items = {i["id"]: i for i in S.by_hand_items(self.cfg(root))}
        self.assertIn("config.cmd", " ".join(items["runner:win1"]["steps"]))
        self.assertIn("config.sh", " ".join(items["runner:pc1"]["steps"]))
        self.assertIn("another machine", items["extra-runner-note"]["title"])
        self.assertIn("10 minutes", items["extra-runner-note"]["title"])


class Option2DoctorTests(Base):
    def test_larger_runner_and_variable_and_spending_limit(self):
        root = self.project(OPT2)
        self.fake({"api": {"orgs/{owner}/actions/hosted-runners": {"runners": []}}, "vars": {}})
        detail = self.ci(root)[1]
        self.assertIn("no larger runner named ubuntu-4core", detail)
        self.assertIn("var:CI_RUNS_ON", detail)
        self.assertIn("spending-limit", detail)
        self.fake({"api": {"orgs/{owner}/actions/hosted-runners": {"runners": [{"name": "ubuntu-4core"}, {"name": "windows-latest"}]}},
                   "vars": {"CI_RUNS_ON": '"ubuntu-4core"'}})
        cli("confirm", "spending-limit", "--root", str(root))
        ok, detail = self.ci(root)
        self.assertTrue(ok, detail)

    def test_spending_limit_is_in_the_list_with_or_without_a_cap(self):
        for cap in (None, 3000):
            a = json.loads(json.dumps(OPT2))
            a["github_hosted"]["monthly_minutes_cap"] = cap
            ids = [i["id"] for i in S.by_hand_items(load(self.project(a)))]
            self.assertIn("spending-limit", ids)


class Option3DoctorTests(Base):
    RULESETS = "repos/{owner}/{repo}/rulesets"

    def ruleset(self, integration_id):
        chk = {"context": "unit (linux)"}
        if integration_id is not None:
            chk["integration_id"] = integration_id
        return {"api": {self.RULESETS + "/7": {"rules": [{"type": "required_status_checks",
                                                          "parameters": {"required_status_checks": [chk]}}]},
                        self.RULESETS: [{"id": 7, "enforcement": "active"}]}}

    def project3(self):
        root = self.project(OPT3)
        p = Path(root) / "scripts" / "delivery"
        p.mkdir(parents=True)
        (p / "ci-shards.json").write_text(json.dumps(TABLE))
        return root

    def test_pinned_check_is_open_any_source_is_ok(self):
        root = self.project3()
        self.fake(self.ruleset(15368))
        self.assertIn("accept only one app", self.ci(root)[1])
        self.fake(self.ruleset(None))
        detail = self.ci(root)[1]
        self.assertNotIn("ruleset-any-source", detail)
        self.assertIn("status-token", detail)          # not set here, lives in the cloud environment
        self.assertIn("session-access", detail)

    def test_all_done(self):
        root = self.project3()
        self.fake(self.ruleset(None))
        cli("confirm", "session-access", "--root", str(root))
        with mock.patch.dict(os.environ, {"CI_STATUS_TOKEN": "x"}):
            ok, detail = self.ci(root)
        self.assertTrue(ok, detail)

    def test_ruleset_unreadable_needs_confirmation(self):
        root = self.project3()
        self.fake({"api": {self.RULESETS: None}})
        self.assertIn("cannot read rulesets", self.ci(root)[1])
        cli("confirm", "ruleset-any-source", "--root", str(root))
        self.assertNotIn("by hand, ruleset-any-source", self.ci(root)[1])

    def test_token_value_is_never_written(self):
        root = self.project3()
        with mock.patch.dict(os.environ, {"CI_STATUS_TOKEN": "secret-value-123"}):
            _c, out, _e = cli("checklist", "--root", str(root))
        self.assertNotIn("secret-value-123", out)
        self.assertNotIn("secret-value-123", Path(C.config_file(root)).read_text())


if __name__ == "__main__":
    unittest.main()
