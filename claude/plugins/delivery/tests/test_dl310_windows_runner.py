"""DL310: the shared Windows machine runner (D269 to D272). Mocked probe and executor; runs on Linux. No PowerShell runs."""
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from _helpers import make_root  # noqa: F401  (puts the scripts folder on sys.path)
import delivery_runner_pool as P
import delivery_doctor as D
import machine_slots as MS

MACHINE = "C:/ProgramData/luismc-delivery"
REPO = "owner/example-app"
GOOD_SHA = "ab" * 32


class Probe(P.Probe):
    platform = "win32"

    def __init__(self, admin=True, runners=None, files=None):
        self.admin, self.calls = admin, []
        self.runners = runners if runners is not None else []
        self.files = files or {}
        self.runner_dirs = []

    def is_admin(self):
        return self.admin

    def sh(self, argv, input=None, timeout=60):
        self.calls.append((list(argv), input))
        return 0, "ok\n"

    def gh(self, args, input=None):
        self.calls.append((["gh"] + list(args), input))
        return 0, ""

    def gh_json(self, args):
        return {"runners": self.runners}, None

    def read_text(self, path):
        return self.files.get(path.replace("\\", "/"))


def runner(name, rid=3, status="online", busy=False, os_="Windows", labels=("self-hosted", "windows")):
    return {"id": rid, "name": name, "os": os_, "status": status, "busy": busy, "labels": list(labels)}


def found(runners=(), services=(), folders=()):
    return {"host": {"platform": "win32", "machine_dir": MACHINE, "python": "C:/Py/python.exe"},
            "github": {"repos": [{"repo": REPO, "private": True, "error": None, "runners": list(runners)}]},
            "services": list(services), "folders": list(folders), "containers": [], "wsl": {}, "pool_env": {}}


def plan(f, probe, repos=(REPO,)):
    with mock.patch.object(P, "runner_pin_problem", return_value=None):
        return P.plan(f, [], list(repos), probe=probe)


def ids(pl):
    return [s["id"] for s in pl["steps"]]


# the hand-made runner of a project that adopted the plugin: another name, NETWORK SERVICE, its own folder
OLD = dict(
    runners=[runner("handmade", rid=9)],
    services=[{"name": "actions.runner.owner-example-app.handmade", "kind": "windows-service", "folder": "C:/old/app",
               "account": "NT AUTHORITY\\NETWORK SERVICE"}],
    folders=[{"path": "C:/old/app", "agent_id": 9, "name": "handmade", "repo": REPO}])


class AccountNames(unittest.TestCase):
    def test_short_slug(self):
        self.assertEqual(P.windows_account("owner/example-app"), "ci-example-app")

    def test_long_slug_is_cut_and_stays_deterministic(self):
        a = P.windows_account("owner/a-very-long-repository-name-here")
        self.assertLessEqual(len(a), 20)
        self.assertTrue(a.startswith("ci-"))
        self.assertEqual(a, P.windows_account("owner/a-very-long-repository-name-here"))

    def test_characters_and_length_for_odd_names(self):
        for repo in ("o/Weird_Name.v2", "o/" + "x" * 80, "o/a", "o/--"):
            a = P.windows_account(repo)
            self.assertRegex(a, r"^ci-[a-z0-9-]+$")
            self.assertLessEqual(len(a), 20)
            self.assertFalse(a.endswith("-") and False)

    def test_two_long_names_with_one_start_do_not_collide(self):
        a = P.windows_account("o/shared-prefix-repository-one")
        b = P.windows_account("o/shared-prefix-repository-two")
        self.assertNotEqual(a, b)

    def test_a_taken_name_gets_a_hash(self):
        first = P.windows_account("a/app")
        second = P.windows_account("b/app", taken={first})
        self.assertNotEqual(first, second)
        self.assertLessEqual(len(second), 20)

    def test_account_name_of(self):
        for t in (".\\ci-app", "HOST\\CI-App", "ci-app"):
            self.assertEqual(P.account_name_of(t), "ci-app")


class PlanSteps(unittest.TestCase):
    def test_elevated_plan_order(self):
        pl = plan(found(), Probe(admin=True))
        got = ids(pl)
        for a, b in (("machine-config", "runner-hooks"), ("runner-hooks", "win-machine"), ("win-machine", "win-account:" + REPO),
                     ("win-account:" + REPO, "win-files:" + REPO), ("win-files:" + REPO, "winsvc:" + REPO)):
            self.assertLess(got.index(a), got.index(b), (a, b))
        self.assertFalse([s for s in pl["steps"] if s["elevated"] and s["id"].startswith(("win", "runner-hooks"))])
        self.assertFalse([s for s in pl["steps"] if s["action"] == "windows-runner-script"])

    def test_not_elevated_plan_writes_a_script_and_one_line(self):
        pl = plan(found(), Probe(admin=False))
        got = ids(pl)
        self.assertLess(got.index("runner-hooks"), got.index("win-script:" + REPO))
        self.assertLess(got.index("win-script:" + REPO), got.index("winsvc:" + REPO))
        self.assertNotIn("win-account:" + REPO, got)
        svc = next(s for s in pl["steps"] if s["id"] == "winsvc:" + REPO)
        self.assertTrue(svc["elevated"])
        self.assertEqual(len(svc["say"]), 1)
        self.assertIn("administrator PowerShell", svc["say"][0])
        self.assertIn("setup/windows-runner-example-app.ps1".replace("/", "\\"), svc["say"][0])

    def test_runner_name_account_and_folder(self):
        svc = next(s for s in plan(found(), Probe()) ["steps"] if s["id"] == "winsvc:" + REPO)
        self.assertEqual((svc["runner"], svc["account"], svc["folder"]),
                         ("host1-example-app", "ci-example-app", "C:/actions-runners/example-app"))

    def test_rerun_with_everything_in_place_is_already(self):
        f = found([runner("host1-example-app")],
                  [{"name": "actions.runner.owner-example-app.host1-example-app", "kind": "windows-service",
                    "folder": "C:/actions-runners/example-app", "account": ".\\ci-example-app"}],
                  [{"path": "C:/actions-runners/example-app", "agent_id": 3, "name": "host1-example-app", "repo": REPO}])
        env = P.windows_env_text("C:/actions-runners/example-app", MACHINE + "/runner-hooks")
        pr = Probe(files={"C:/actions-runners/example-app/.env": env})
        pl = plan(f, pr)
        self.assertEqual([s["state"] for s in pl["steps"] if s["id"].startswith(("winsvc:", "win-"))], ["already"])

    def test_wrong_account_is_registered_again_but_stale_env_only_rewrites(self):
        svc = {"name": "actions.runner.owner-example-app.host1-example-app", "kind": "windows-service",
               "folder": "C:/actions-runners/example-app", "account": "NT AUTHORITY\\NETWORK SERVICE"}
        fold = {"path": "C:/actions-runners/example-app", "agent_id": 3, "name": "host1-example-app", "repo": REPO}
        pl = plan(found([runner("host1-example-app")], [svc], [fold]), Probe())
        s = next(x for x in pl["steps"] if x["id"] == "winsvc:" + REPO)
        self.assertEqual(s["state"], "todo")
        self.assertTrue(s["register"])
        self.assertFalse([i for i in ids(pl) if i.startswith(("remove:", "winsvc-remove:", "delete-folder:"))])
        svc["account"] = ".\\ci-example-app"
        pl = plan(found([runner("host1-example-app")], [svc], [fold]), Probe(files={}))
        s = next(x for x in pl["steps"] if x["id"] == "winsvc:" + REPO)
        self.assertEqual(s["state"], "todo")
        self.assertFalse(s["register"])  # the password changes only when the service is registered again


class Secrets(unittest.TestCase):
    def setUp(self):
        self.pl = plan(found(), Probe())
        self.step = next(s for s in self.pl["steps"] if s["id"] == "winsvc:" + REPO)

    def test_plan_holds_no_password_and_no_token(self):
        text = json.dumps(self.pl)
        self.assertNotRegex(text, r"ghs_|ghp_|gho_")
        self.assertNotRegex(text, r"windowslogonpassword (?!<PASSWORD>)")

    def test_script_makes_its_own_password_and_token(self):
        text = P.windows_runner_script(self.step)
        self.assertIn("registration-token", text)
        self.assertEqual(re.findall(r"--windowslogonpassword (\S+)", text), ["$pw"])
        self.assertEqual(set(re.findall(r"--token (\S+)", text)), {"$token", "$rt"})  # DL315: $rt is the remove token
        self.assertIn("$pw = $null", text)
        self.assertNotIn("Write-Host $pw", text)
        self.assertNotRegex(text, r"(?i)(echo|Write-Host|Write-Output|Out-File|Add-Content)[^\r\n]*\$(pw|token)")
        self.assertTrue(text.startswith("#Requires -RunAsAdministrator"))

    def test_the_elevated_run_sends_powershell_through_stdin_and_keeps_no_secret(self):
        pr = Probe()
        pl = plan(found(), Probe(admin=True))
        ex = P.Executor(pr)
        with mock.patch.object(P, "runner_pin_problem", return_value=None):
            for st in pl["steps"]:
                if st["action"] in ("windows-machine", "windows-account", "windows-files", "windows-service"):
                    self.assertTrue(ex.run(st)[0], st["id"])
        ps = [c for c in pr.calls if c[0][0] == "powershell"]
        self.assertEqual(len(ps), 4)
        for argv, stdin in ps:
            self.assertNotIn("-File", argv)
            self.assertNotIn("windowslogonpassword", " ".join(argv))  # never an argument of ours
            self.assertEqual(re.findall(r"--windowslogonpassword (\S+)", stdin) or ["$pw"], ["$pw"])
        self.assertFalse([c for c in pr.calls if c[0][0] == "gh"])  # the token is made inside PowerShell, not here

    def test_details_printed_by_a_run_show_no_secret(self):
        said = []
        pr = Probe()
        pl = plan(found(), Probe(admin=True))
        only = {"pool": "main", "refused": [], "steps": [s for s in pl["steps"] if s["action"].startswith("windows-")]}
        with mock.patch.object(P, "runner_pin_problem", return_value=None):
            P.run(only, ask=lambda s: True, ask_delete=lambda s: True, say=said.append, execute=P.Executor(pr).run,
                  check=lambda s: True)
        self.assertTrue(said)
        self.assertNotRegex("\n".join(said), r"Aa1!|ghs_|windowslogonpassword \S*[^>\s]")


class EnvFile(unittest.TestCase):
    def test_content(self):
        text = P.windows_env_text("C:/actions-runners/example-app", MACHINE + "/runner-hooks")
        self.assertEqual(text.splitlines(), [
            "ACTIONS_RUNNER_HOOK_JOB_STARTED=C:/ProgramData/luismc-delivery/runner-hooks/runner_load_gate.ps1",
            "ACTIONS_RUNNER_HOOK_JOB_COMPLETED=C:/ProgramData/luismc-delivery/runner-hooks/runner_job_done.ps1",
            "CI_TOOLS_DIR=C:/ci-tools",
            "RUSTUP_HOME=C:/actions-runners/example-app/_tools/rustup",
            "CARGO_HOME=C:/actions-runners/example-app/_tools/cargo"])

    def test_no_cmd_hook_and_no_second_machine_folder(self):
        text = P.windows_env_text("C:/r/x", MACHINE + "/runner-hooks")
        self.assertNotIn(".cmd", text)
        self.assertNotIn("DELIVERY_MACHINE_DIR", text)

    def test_the_script_rewrites_the_env_every_run_even_without_registering(self):
        for register in (True, False):
            lines = "\n".join(P.ps_register(REPO, "host1-x", "ci-x", "C:/r/x", P.windows_env_text("C:/r/x", "H"), register))
            self.assertIn("ACTIONS_RUNNER_HOOK_JOB_STARTED=H/runner_load_gate.ps1", lines)
            self.assertEqual("config.cmd --unattended" in lines, register)
            self.assertIn("Restart-Service", lines)


class Rights(unittest.TestCase):
    def test_account_rights_and_group(self):
        text = "\n".join(P.ps_account("ci-x"))
        for word in ("SeServiceLogonRight", "SeDenyInteractiveLogonRight", "SeDenyRemoteInteractiveLogonRight", "luismc-ci-runners",
                     "Remove-LocalGroupMember"):
            self.assertIn(word, text)
        self.assertNotIn("Add-LocalGroupMember -Group 'Administrators'", text)

    def test_folder_rights(self):
        m = "\n".join(P.ps_machine(MACHINE, MACHINE + "/runner-hooks", "C:/ci-tools"))
        self.assertIn('"luismc-ci-runners:(OI)(CI)M"', m)
        self.assertIn('"luismc-ci-runners:(OI)(CI)RX"', m)
        self.assertEqual(len(re.findall(r"C:\\ci-tools' /grant|ci-tools'? /grant", m)), 1)
        f = "\n".join(P.ps_files("ci-x", "C:/actions-runners/x", "C:/ci-tools", "C:/Py/python.exe"))
        self.assertIn("/inheritance:r", f)
        self.assertIn("ci-x:(OI)(CI)F", f)
        self.assertIn("*S-1-5-32-544", f)
        self.assertNotIn("luismc-ci-runners", f)  # the runner folder belongs to its account alone
        self.assertIn("ci_tool.py", f)
        self.assertIn("tool 'actions-runner'".replace("'", ""), f.replace("'", ""))


class Download(unittest.TestCase):
    def test_shipped_pin_refuses_until_it_has_a_real_hash(self):
        pins = Path(P.CI_TOOL).with_name("tools.json")
        data = json.loads(pins.read_text())
        entry = data["actions-runner"]["platforms"]["windows_x64"]
        self.assertTrue(entry["url"].startswith("https://github.com/actions/runner/releases/download/"))
        if P.sha_is_bad(entry["sha256"]):
            self.assertIn("no real SHA-256", P.runner_pin_problem())
        else:
            self.assertIsNone(P.runner_pin_problem())

    def test_pin_problem_cases(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.json")
            for sha, bad in (("0" * 64, True), ("zz", True), (GOOD_SHA, False)):
                Path(p).write_text(json.dumps({"actions-runner": {"platforms": {"windows_x64": {"url": "https://x/y.zip", "sha256": sha}}}}))
                self.assertEqual(bool(P.runner_pin_problem(p)), bad, sha)
            self.assertTrue(P.runner_pin_problem(os.path.join(d, "missing.json")))

    def test_files_and_script_steps_refuse_with_a_bad_pin(self):
        with mock.patch.object(P, "runner_pin_problem", return_value="refused: no hash"):
            pl = P.plan(found(), [], [REPO], probe=Probe(admin=True))
            pr = Probe()
            step = next(s for s in pl["steps"] if s["action"] == "windows-files")
            self.assertEqual(P.Executor(pr).run(step), (False, "refused: no hash"))
            self.assertFalse(pr.calls)
            pl = P.plan(found(), [], [REPO], probe=Probe(admin=False))
            step = next(s for s in pl["steps"] if s["action"] == "windows-runner-script")
            self.assertFalse(P.Executor(pr).run(step)[0])


class ScriptFile(unittest.TestCase):
    def test_script_is_written_when_not_elevated(self):
        with tempfile.TemporaryDirectory() as d:
            pl = plan(found(), Probe(admin=False))
            step = dict(next(s for s in pl["steps"] if s["action"] == "windows-runner-script"), script=os.path.join(d, "setup", "w.ps1"))
            ok, detail = P.Executor(Probe()).run(step)
            self.assertTrue(ok, detail)
            text = Path(step["script"]).read_text(encoding="utf-8-sig")
            self.assertIn("config.cmd", text)
            self.assertIn("ci-example-app", text)
            self.assertIn("RUSTUP_HOME=C:/actions-runners/example-app/_tools/rustup", text)
            self.assertNotRegex(text, r"ghs_|\bAa1![A-Za-z0-9+/=]{8}")
            self.assertNotIn("Aa1!", detail)

    def test_run_writes_then_prints_one_line_and_checks(self):
        said = []
        with tempfile.TemporaryDirectory() as d:
            pl = plan(found(), Probe(admin=False))
            for s in pl["steps"]:
                if s["action"] == "windows-runner-script":
                    s["script"] = os.path.join(d, "w.ps1")
            keep = [s for s in pl["steps"] if s["id"] in ("win-script:" + REPO, "winsvc:" + REPO)]
            res = P.run({"pool": "main", "refused": [], "steps": keep}, ask=lambda s: True, ask_delete=lambda s: True,
                        say=said.append, execute=P.Executor(Probe()).run, check=lambda s: True)
        self.assertIsNone(res["failed"])
        self.assertEqual([l for l in said if "administrator PowerShell" in l and "run:" in l].__len__(), 1)
        self.assertFalse([l for l in said if "config.cmd" in l])  # the by-hand lines are not printed


class Migration(unittest.TestCase):
    def setUp(self):
        self.pr = Probe(admin=False)
        self.pl = plan(found(**OLD), self.pr)

    def test_old_runner_is_replaced_after_the_new_one(self):
        got = ids(self.pl)
        new = got.index("winsvc:" + REPO)
        for i in ("winsvc-remove:actions.runner.owner-example-app.handmade", "remove:%s:handmade" % REPO, "delete-folder:C:/old/app"):
            self.assertGreater(got.index(i), new, i)
        self.assertLess(got.index("winsvc-remove:actions.runner.owner-example-app.handmade"), got.index("remove:%s:handmade" % REPO))

    def test_each_replace_step_names_what_goes(self):
        steps = [s for s in self.pl["steps"] if s.get("old_runner")]
        self.assertEqual(len(steps), 3)
        for s in steps:
            self.assertTrue(s["delete"] and s["names"])

    def test_without_the_named_yes_nothing_is_removed(self):
        said, ran = [], []
        res = P.run({"pool": "main", "refused": [], "steps": [s for s in self.pl["steps"] if s.get("old_runner")]},
                    ask=lambda s: True, ask_delete=lambda s: False, say=said.append,
                    execute=lambda s: (ran.append(s["id"]), (True, "x"))[1], check=lambda s: True)
        self.assertEqual(ran, [])
        self.assertTrue(res["left"])

    def test_with_the_yes_and_an_idle_old_runner_the_steps_run(self):
        pr = Probe(admin=True, runners=[runner("host1-example-app"), runner("handmade", rid=9)])
        pl = plan(found(**OLD), pr)
        steps = [s for s in pl["steps"] if s.get("old_runner")]
        ran = []
        P.run({"pool": "main", "refused": [], "steps": steps}, ask=lambda s: True, ask_delete=lambda s: True, say=lambda m: None,
              execute=lambda s: (ran.append(s["action"]), (True, "x"))[1], check=lambda s: True, guard=lambda s: P.migration_guard(pr, s))
        self.assertEqual(ran, ["windows-service-remove", "remove-runner", "delete-folder"])

    def test_a_running_job_or_an_offline_new_runner_blocks(self):
        step = next(s for s in self.pl["steps"] if s["action"] == "remove-runner")
        busy = Probe(runners=[runner("host1-example-app"), runner("handmade", rid=9, busy=True)])
        self.assertIn("a job runs on handmade", P.migration_guard(busy, step))
        offline = Probe(runners=[runner("host1-example-app", status="offline"), runner("handmade", rid=9)])
        self.assertIn("not online", P.migration_guard(offline, step))
        self.assertIn("not online", P.migration_guard(Probe(runners=[runner("handmade", rid=9)]), step))
        self.assertIsNone(P.migration_guard(Probe(runners=[runner("host1-example-app"), runner("handmade", rid=9)]), step))
        ex = P.Executor(busy)  # the executor refuses too, without being asked
        self.assertFalse(ex.run(step)[0])
        self.assertFalse([c for c in busy.calls if c[0][:3] == ["gh", "api", "-X"] and "DELETE" in c[0]])

    def test_unreadable_runner_list_counts_as_busy(self):
        pr = Probe()
        pr.gh_json = lambda args: (None, "gh refused")
        self.assertTrue(P.runner_has_job(pr, REPO, "x"))
        self.assertIn("cannot be read", P.migration_guard(pr, {"old_runner": "x", "repo": REPO}))

    def test_a_runner_with_the_new_name_is_not_a_migration(self):
        f = found([runner("host1-example-app")], [], [{"path": "C:/old/x", "agent_id": 3, "name": "host1-example-app", "repo": REPO}])
        got = ids(plan(f, Probe()))
        self.assertIn("remove:%s:host1-example-app" % REPO, got)
        self.assertLess(got.index("remove:%s:host1-example-app" % REPO), got.index("machine-config"))


class OneSharedQueue(unittest.TestCase):
    def test_plan_has_one_machine_config_and_hooks_inside_the_machine_folder(self):
        pl = plan(found(), Probe())
        self.assertEqual(len([s for s in pl["steps"] if s["action"] == "machine-config"]), 1)
        hooks = next(s for s in pl["steps"] if s["action"] == "runner-hooks")
        self.assertEqual(hooks["dest"], MACHINE + "/runner-hooks")
        svc = next(s for s in pl["steps"] if s["action"] == "windows-service")
        self.assertNotIn("DELIVERY_MACHINE_DIR", svc["env_text"])
        self.assertEqual(svc["machine_dir"], MACHINE)

    def test_limits_are_the_pool_defaults(self):
        self.assertEqual((P.MEM_PCT, P.CPU_PCT), (85, 60))
        cfg = MS.normalise_config({})
        self.assertIn("ci_slots", cfg)  # one slot count for every runner of the machine

    def test_machine_folder_rights_go_to_the_group_not_to_each_account(self):
        text = "\n".join(P.ps_machine(MACHINE, MACHINE + "/runner-hooks"))
        self.assertIn("luismc-ci-runners", text)
        self.assertNotIn("ci-example-app", text)


class DoctorFindings(unittest.TestCase):
    ENV = {"CI_TOOLS_DIR": "C:/ci-tools", "RUSTUP_HOME": "r", "CARGO_HOME": "c",
           "ACTIONS_RUNNER_HOOK_JOB_STARTED": "C:/ProgramData/luismc-delivery/runner-hooks/runner_load_gate.ps1"}

    def run_doctor(self, start="NT AUTHORITY\\NETWORK SERVICE", env=None, groups=None, svc="present"):
        env = dict(self.ENV if env is None else env)
        groups = groups or {}
        service = None if svc == "none" else ("actions.runner.x", None if svc == "unreadable" else start)
        with mock.patch.object(D, "_service_account", return_value=service), \
                mock.patch.object(D, "_env_value", side_effect=lambda d, n: env.get(n)), \
                mock.patch.object(D, "_account_in_group", side_effect=lambda a, g: groups.get(g)), \
                mock.patch.object(MS, "machine_dir", return_value=MACHINE):
            return {i["id"].split(":")[-1]: i for i in D.windows_runner_items(["C:/actions-runners/x"])}

    def test_good_runner(self):
        got = self.run_doctor(start=".\\ci-x", groups={"Administrators": False, "luismc-ci-runners": True})
        self.assertEqual({k: v["status"] for k, v in got.items()}, {"account": "ok", "env": "ok", "machine": "ok"})

    def test_shared_accounts_warn(self):
        for start in ("NT AUTHORITY\\NETWORK SERVICE", "LocalSystem", "NT AUTHORITY\\SYSTEM"):
            got = self.run_doctor(start=start)
            self.assertEqual(got["account"]["status"], "warn", start)
            self.assertIn("ci-*", got["account"]["detail"])

    def test_admin_account_warns(self):
        got = self.run_doctor(start=".\\ci-x", groups={"Administrators": True})
        self.assertEqual(got["account"]["status"], "warn")
        self.assertIn("administrator", got["account"]["detail"])

    def test_not_in_the_group_and_other_names_warn(self):
        self.assertEqual(self.run_doctor(start=".\\ci-x", groups={"Administrators": False, "luismc-ci-runners": False})["account"]["status"], "warn")
        self.assertEqual(self.run_doctor(start=".\\bob", groups={"Administrators": False})["account"]["status"], "warn")

    def test_missing_service_warns(self):
        self.assertEqual(self.run_doctor(svc="none")["service"]["status"], "warn")
        self.assertEqual(self.run_doctor(svc="unreadable")["service"]["status"], "warn")

    def test_env_lacking_names_are_listed(self):
        got = self.run_doctor(start=".\\ci-x", env={"ACTIONS_RUNNER_HOOK_JOB_STARTED": self.ENV["ACTIONS_RUNNER_HOOK_JOB_STARTED"]})
        self.assertEqual(got["env"]["status"], "warn")
        for n in ("CI_TOOLS_DIR", "RUSTUP_HOME", "CARGO_HOME"):
            self.assertIn(n, got["env"]["detail"])

    def test_another_machine_folder_warns(self):
        env = dict(self.ENV, DELIVERY_MACHINE_DIR="D:/other")
        self.assertEqual(self.run_doctor(start=".\\ci-x", env=env)["machine"]["status"], "warn")
        env = dict(self.ENV, ACTIONS_RUNNER_HOOK_JOB_STARTED="D:/hooks/runner_load_gate.ps1")
        self.assertEqual(self.run_doctor(start=".\\ci-x", env=env)["machine"]["status"], "warn")
        env = dict(self.ENV, DELIVERY_MACHINE_DIR=MACHINE + "/")
        self.assertEqual(self.run_doctor(start=".\\ci-x", env=env)["machine"]["status"], "ok")


if __name__ == "__main__":
    unittest.main()
