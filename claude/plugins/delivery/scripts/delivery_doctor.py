#!/usr/bin/env python3
"""Self-check of a delivery project: is everything the plugin needs in place?

    delivery_doctor.py [self-check] [--root DIR] [--json]

Eight checks, each `ok` or `FAIL` with the fix:
  config   .delivery/config.json passes delivery_config.py validate (no errors; a missing file is fine)
  gh       `gh auth status` succeeds (the watcher and the hooks need a signed-in gh; DELIVERY_GH replaces gh in tests)
  tz       the configured `tz` loads through zoneinfo; if tzdata is missing this FAILS instead of quietly using UTC
  hooks    the plugin's hooks.json names the five hook scripts and they exist, and luismc-delivery is enabled in
           .claude/settings.json, .claude/settings.local.json or ~/.claude/settings.json (enabledPlugins)
  ledger   .delivery/ is writable and ledger.json, when present, is valid JSON
  runner   (DL-79) whether ACTIONS_RUNNER_HOOK_JOB_STARTED points at runner_load_gate on this machine: in the
           environment, in the Windows user/machine environment, or in the .env of a runner folder
           (DELIVERY_RUNNER_DIRS, `runner_dirs` in the machine file, or actions-runner* next to home, drive root and /opt).
           FAIL only when a runner folder exists without the hook; a machine with no runner is ok.
           On Windows, for a runner service whose hook is a .ps1, it also reads the PowerShell execution policy that
           applies to the service's account and FAILS when it is Restricted, AllSigned or undefined (the script would not
           start and every job would fail); an unreadable policy is reported as "cannot check", not a failure.
  ci       (DL15) the CI option chosen per OS (Option 1 self-hosted, Option 2 github-hosted, Option 3 cloud) and what each one needs:
           a: an entry in `runners` for that OS; b: workflow files in .github/workflows; c: ci.cloud.repo,
           status_token_env and branches, a shard for the OS, and one context per shard. FAILS when the shard table
           has a shard for an OS that was not chosen (there is no default). Nothing chosen and no shard table: ok.
           (CIR10 S6) When `/delivery-ci-setup` wrote the config (`ci.guided`), it also checks every item of the by-hand
           list that the setup printed (delivery_ci_setup.py `by_hand_items`): runner online with its labels, repository
           variables, larger runner, token variable, ruleset 'Any source'. An item it cannot read (billing, a remote
           machine, the cloud environment) FAILS until `delivery_ci_setup.py confirm ITEM`.
  machine  (DL-90, D45, D31) the shared CI machine layer, when any OS is Option 1 or the machine folder exists: machine.json
           exists and is readable (a difference with the old ~/.claude file is a warning naming the keys); every runner
           folder has both hooks (ACTIONS_RUNNER_HOOK_JOB_STARTED -> runner_load_gate, ..._COMPLETED -> runner_job_done;
           on Windows a .ps1 hook passes the execution policy check, a hook ending in .cmd FAILS: the runner rejects it);
           a dry-run push of a ci-wait test ref from each runner's kept checkout WARNs when it fails (the runner account
           needs git credentials); no slot is stale and no queue ticket is older than
           `slot_stale_min`; host-load.json is under 60 s old; the pool checks of delivery_runner_pool.doctor_checks(root)
           when that module imports (else skip); an Option 1 project with the repository variable CI_RUNS_ON unset FAILS
           (it would run on hosted runners and may bill minutes); the size of every runner's _work folder (a large total
           is a warning; `delivery_doctor.py clean-work` lists, `--yes` cleans runners with no job running).
           The JSON output carries the single items (id, status ok|warn|fail|skip, detail) as `items`.
Exit 0 all ok, 1 at least one FAIL, 2 no .delivery/ folder. Standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import delivery_ci_setup as SETUP  # noqa: E402
import delivery_config as C  # noqa: E402
import hooklib as H  # noqa: E402
import machine_slots as MS  # noqa: E402

PLUGIN = os.path.dirname(HERE)
HOOK_SCRIPTS = ("hook_pre_tool.py", "hook_post_tool.py", "hook_stop.py", "hook_session_start.py")
SETTINGS = (os.path.join(".claude", "settings.json"), os.path.join(".claude", "settings.local.json"))


def check_config(root, cfg):
    path = C.config_file(root)
    errors, warnings, status = C.validate_file(path)
    if errors:
        return False, "; ".join(errors[:5]) + " (run delivery_config.py validate)"
    return True, ("no config file, defaults apply" if status == "missing"
                  else "valid, %d warning(s)" % len(warnings))


def check_gh(root, cfg):
    r = H.gh(root, ["auth", "status"])
    if r is None:
        return False, "gh cannot run. Install the GitHub CLI and put it on PATH."
    if r[0] != 0:
        return False, "gh is not signed in. Run `gh auth login`."
    return True, "signed in"


def check_tz(root, cfg):
    name = cfg.get("tz") or "UTC"
    try:
        C.load_tz(name)
    except ValueError as exc:
        return False, str(exc)
    return True, name


def _enabled(path):
    data = H.read_json(path)
    plugins = data.get("enabledPlugins") if isinstance(data, dict) else None
    if not isinstance(plugins, dict):
        return False
    return any(k.split("@")[0] == "luismc-delivery" and v is True for k, v in plugins.items())


def check_hooks(root, cfg):
    hooks = H.read_json(os.path.join(PLUGIN, "hooks", "hooks.json"))
    if not isinstance(hooks, dict) or not isinstance(hooks.get("hooks"), dict):
        return False, "the plugin's hooks/hooks.json is missing or unreadable. Reinstall luismc-delivery."
    text = json.dumps(hooks)
    missing = [s for s in HOOK_SCRIPTS if s not in text or not os.path.isfile(os.path.join(HERE, s))]
    if missing:
        return False, "hooks.json or scripts/ lack %s. Reinstall luismc-delivery." % ", ".join(missing)
    places = [os.path.join(root, p) for p in SETTINGS] + [os.path.join(os.path.expanduser("~"), ".claude", "settings.json")]
    if not any(_enabled(p) for p in places):
        return False, ("luismc-delivery is not enabled for this project. Add \"luismc-delivery@dev-standards\": true to "
                       "enabledPlugins in .claude/settings.json (claude-setup does this).")
    return True, "%d events registered, plugin enabled" % len(hooks["hooks"])


def check_ledger(root, cfg):
    d = os.path.join(root, ".delivery")
    try:
        fd, tmp = tempfile.mkstemp(prefix=".doctor-", dir=d)
        os.close(fd)
        os.remove(tmp)
    except OSError as exc:
        return False, ".delivery/ is not writable (%s). Fix the folder's permissions." % exc
    path = os.path.join(d, "ledger.json")
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                json.load(f)
        except (OSError, ValueError) as exc:
            return False, "ledger.json is not valid JSON (%s). Restore it from a backup or move it aside." % exc
        if not os.access(path, os.W_OK):
            return False, "ledger.json is read-only."
    return True, "writable"


HOOK_VAR = "ACTIONS_RUNNER_HOOK_JOB_STARTED"


def _runner_dirs():
    import glob
    import load as L
    dirs = [d for d in os.environ.get("DELIVERY_RUNNER_DIRS", "").split(os.pathsep) if d]
    dirs += MS.machine_config()["runner_dirs"]
    machine = L._read(L.machine_file())
    if isinstance(machine, dict) and isinstance(machine.get("runner_dirs"), list):
        dirs += [d for d in machine["runner_dirs"] if isinstance(d, str) and d not in dirs]
    if not dirs:
        for base in (os.path.expanduser("~"), "C:\\", "/opt", "/srv"):
            dirs += glob.glob(os.path.join(base, "actions-runner*"))
    return [d for d in dirs if os.path.isfile(os.path.join(d, ".runner")) or os.path.isfile(os.path.join(d, "config.sh"))
            or os.path.isfile(os.path.join(d, "config.cmd"))]


def _hook_value(text):
    for line in text.splitlines():
        if line.strip().startswith(HOOK_VAR + "="):
            return line.split("=", 1)[1].strip()
    return None


def _is_windows():
    return sys.platform.startswith("win")


def _windows_env_hook():
    if not _is_windows():
        return None
    import subprocess
    for key in ("HKCU\\Environment", "HKLM\\SYSTEM\\CurrentControlSet\\Control\\Session Manager\\Environment"):
        try:
            out = subprocess.run(["reg", "query", key, "/v", HOOK_VAR], capture_output=True, text=True, timeout=10).stdout
        except (OSError, subprocess.SubprocessError):
            continue
        for line in out.splitlines():
            if HOOK_VAR in line:
                return line.split(None, 2)[-1].strip()
    return None

WELL_KNOWN_SIDS = {"networkservice": "S-1-5-20", "localservice": "S-1-5-19", "localsystem": "S-1-5-18", "system": "S-1-5-18"}
PS_SHELL_PATH = chr(92).join(("SOFTWARE", "Microsoft", "PowerShell", "1", "ShellIds", "Microsoft.PowerShell"))
PS_POLICY_PATH = chr(92).join(("SOFTWARE", "Policies", "Microsoft", "Windows", "PowerShell"))
FIX = ("Set RemoteSigned for that account only, from an elevated shell: registry value ExecutionPolicy (string) under "
       "HKEY_USERS\\%s\\" + PS_SHELL_PATH + ". See the README, 'CI runner gate'.")


def _service_account(runner_dir):
    """(service name, StartName) of the runner service of this folder, or None when there is none to read."""
    try:
        with open(os.path.join(runner_dir, ".service"), encoding="utf-8", errors="replace") as f:
            name = f.read().strip()
    except OSError:
        return None
    if not name:
        return None
    import subprocess
    try:
        out = subprocess.run(["sc", "qc", name], capture_output=True, text=True, timeout=15).stdout
    except (OSError, subprocess.SubprocessError):
        return name, None
    for line in out.splitlines():
        if "SERVICE_START_NAME" in line:
            return name, line.split(":", 1)[1].strip()
    return name, None


def _account_sid(account):
    key = account.lower().replace(" ", "")
    key = key.split("\\")[-1]
    if key in WELL_KNOWN_SIDS:
        return WELL_KNOWN_SIDS[key]
    import subprocess
    ps = "([System.Security.Principal.NTAccount]'%s').Translate([System.Security.Principal.SecurityIdentifier]).Value" % account.replace("'", "''")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return out if out.startswith("S-1-") else None


def _reg_value(hive, path, name):
    """The value, or None when the key or value is absent. Raises OSError (PermissionError) when it cannot be read."""
    import winreg
    try:
        with winreg.OpenKey(hive, path) as k:
            return winreg.QueryValueEx(k, name)[0]
    except FileNotFoundError:
        return None


def _effective_policy(sid):
    """(policy, scope) the way PowerShell resolves it for the account with this SID. Raises OSError when unreadable."""
    import winreg
    u, m = winreg.HKEY_USERS, winreg.HKEY_LOCAL_MACHINE
    for scope, hive, root in (("MachinePolicy", m, ""), ("UserPolicy", u, sid + "\\")):
        base = root + PS_POLICY_PATH
        if _reg_value(hive, base, "ExecutionPolicy") is None and _reg_value(hive, base, "EnableScripts") is None:
            continue
        if _reg_value(hive, base, "EnableScripts") == 0:
            return "Restricted", scope
        val = _reg_value(hive, base, "ExecutionPolicy")
        if val:
            return val, scope
    with winreg.OpenKey(u, sid):  # the account's hive must be loaded to say anything about it
        pass
    for scope, hive, path in (("CurrentUser", u, sid + "\\" + PS_SHELL_PATH), ("LocalMachine", m, PS_SHELL_PATH)):
        val = _reg_value(hive, path, "ExecutionPolicy")
        if val:
            return val, scope
    return "Undefined", "nowhere (Restricted on client Windows)"


def _execution_policy_problem(runner_dir):
    """None when the runner service account may run the .ps1 hook; else (is_failure, message)."""
    acct = _service_account(runner_dir)
    if acct is None:
        return None
    name, account = acct
    if not account:
        return False, "cannot check the PowerShell execution policy: the account of service %s is unreadable" % name
    sid = _account_sid(account)
    if not sid:
        return False, "cannot check the PowerShell execution policy of %s (SID not resolved)" % account
    try:
        policy, scope = _effective_policy(sid)
    except OSError as exc:
        return False, "cannot check the PowerShell execution policy of %s (%s)" % (account, exc)
    if policy.lower() in ("remotesigned", "unrestricted", "bypass"):
        return None
    return True, ("the PowerShell execution policy for %s is %s (%s): the runner starts the .ps1 hook with Windows PowerShell "
                  "and it would refuse the script, so every job would fail. " % (account, policy, scope) + FIX % sid)


def check_runner(root, cfg):
    ok, detail = _check_runner_hook(root, cfg)
    if ok and _is_windows():
        for d in _runner_dirs():
            try:
                with open(os.path.join(d, ".env"), encoding="utf-8", errors="replace") as f:
                    v = _hook_value(f.read())
            except OSError:
                continue
            if v and "runner_load_gate" in v and v.strip("\"'").lower().endswith(".ps1"):
                problem = _execution_policy_problem(d)
                if problem and problem[0]:
                    return False, problem[1]
                if problem:
                    detail += "; " + problem[1]
    return ok, detail


def _check_runner_hook(root, cfg):
    env = os.environ.get(HOOK_VAR) or _windows_env_hook()
    dirs = _runner_dirs()
    hooked, bare = [], []
    for d in dirs:
        try:
            with open(os.path.join(d, ".env"), encoding="utf-8", errors="replace") as f:
                v = _hook_value(f.read())
        except OSError:
            v = None
        (hooked if v and "runner_load_gate" in v else bare).append(d)
    if env and "runner_load_gate" in env and not bare:
        return True, "%s is set to %s" % (HOOK_VAR, env)
    if hooked and not bare:
        return True, "%s set in the .env of %s" % (HOOK_VAR, ", ".join(hooked))
    if env and "runner_load_gate" not in env:
        return False, "%s is set to %s, not runner_load_gate. See the README, 'CI runner gate'." % (HOOK_VAR, env)
    if bare:
        return False, ("runner folder(s) %s have no %s=...runner_load_gate hook: new jobs can start over the load limits. "
                       "See the README, 'CI runner gate' (the doctor changes nothing)." % (", ".join(bare), HOOK_VAR))
    return True, "no self-hosted runner found on this machine (nothing to hook)"


def _runner_oses(cfg):
    """The OS names (linux, windows, macos) that the `runners` entries name in their os or labels."""
    words = {"linux": {"linux"}, "windows": {"windows", "win"}, "macos": {"macos", "mac", "darwin", "osx"}}
    out = set()
    for r in cfg.get("runners") or []:
        if isinstance(r, dict):
            text = " ".join([str(r.get("os", ""))] + [x for x in r.get("labels") or [] if isinstance(x, str)]).lower()
            tokens = set(re.split(r"[^a-z0-9]+", text))
            out.update(name for name, w in words.items() if tokens & w)
    return out


def _second_machine_note(cfg, os_name):
    """Option 1 is own runners on ANY machines. Name the machines found for the OS, and the by-hand steps to add one
    more on another machine (a note, never a failure: one runner works, it is only the first bottleneck)."""
    mine = [r for r in cfg.get("runners") or [] if isinstance(r, dict) and os_name in _runner_oses({"runners": [r]})]
    names = ", ".join(str(r.get("name")) for r in mine)
    labels = next((r.get("labels") for r in mine if r.get("labels")), None)
    steps = "; ".join("(%d) %s" % (i, t) for i, t in enumerate(C.runner_steps(os_name, labels), 1))
    return "%s: %d runner(s) (%s). %s. To add a runner on another machine, by hand: %s" % (
        os_name, len(mine), names, C.add_runner_advice(), steps)


def check_ci(root, cfg):
    opts = C.ci_options(cfg)
    shards, err = C.load_shards(root, cfg)
    table_exists = os.path.exists(C.shard_table_path(root, cfg))
    if not opts and not table_exists:
        return True, "no CI option chosen and no shard table (run `delivery_ci.py set --os <os> --option 1|2|3`, ask the owner per OS)"
    problems, notes = [], []
    if table_exists and err:
        problems.append(err)
    if "cloud" in opts.values() and not table_exists:
        problems.append("an OS is Option 3 (cloud) but there is no shard table (%s)" % (err or "missing"))
    used = sorted({sh["os"] for sh in shards})
    for o in used:
        if o not in opts:
            problems.append("the shard table has a shard for %s but no CI option is chosen for it. Ask the owner, then run "
                            "`delivery_ci.py set --os %s --option 1|2|3`" % (o, o))
    chosen = {o: v for o, v in opts.items() if o in used or not shards}
    for o, v in sorted(chosen.items()):
        if v == "self-hosted":
            if o not in _runner_oses(cfg):
                problems.append("%s is Option 1 (self-hosted) but `runners` lists no %s runner. Install a runner on a machine you "
                                "run, by hand: %s" % (o, o, "; ".join("(%d) %s" % (i, t) for i, t in enumerate(C.runner_steps(o), 1))))
            else:
                notes.append(_second_machine_note(cfg, o))
        elif v == "github-hosted":
            wf = os.path.join(root, ".github", "workflows")
            if not os.path.isdir(wf) or not [n for n in os.listdir(wf) if n.endswith((".yml", ".yaml"))]:
                problems.append("%s is Option 2 (github-hosted) but .github/workflows has no workflow file" % o)
        elif v == "cloud":
            cl = C.ci_cloud(cfg)
            if not cl["repo"]:
                problems.append("%s is Option 3 (cloud) but ci.cloud.repo is not set" % o)
            if not cl["status_token_env"]:
                problems.append("%s is Option 3 (cloud) but ci.cloud.status_token_env is not set" % o)
            elif not os.environ.get(cl["status_token_env"]):
                notes.append("token variable %s is not set here (set it in the cloud environment)" % cl["status_token_env"])
            if not cl["branches"]:
                problems.append("%s is Option 3 (cloud) but ci.cloud.branches is empty" % o)
            if shards and not any(sh["os"] == o for sh in shards):
                problems.append("%s is Option 3 (cloud) but the shard table has no shard for it" % o)
    cloud_shards = [sh for sh in shards if opts.get(sh["os"]) == "cloud"]
    ctxs = [sh["context"] for sh in cloud_shards]
    for c in sorted({c for c in ctxs if ctxs.count(c) > 1}):
        problems.append("two cloud shards share the status context %r" % c)
    hand_problems, hand_notes = SETUP.check_by_hand(root, cfg)
    problems += hand_problems
    notes += hand_notes
    if problems:
        return False, "; ".join(problems)
    summary = ", ".join("%s=Option %d" % (o, C.CI_OPTION_NUMBER[v]) for o, v in sorted(opts.items())) or "no OS chosen"
    return True, "; ".join([summary, *notes])


# --- machine layer (DL-90) --------------------------------------------------------------------------

DONE_VAR = "ACTIONS_RUNNER_HOOK_JOB_COMPLETED"
WORK_WARN_GB = 20.0


def _item(id_, status, detail):
    return {"id": id_, "status": status, "detail": detail}


def _env_value(runner_dir, name):
    try:
        with open(os.path.join(runner_dir, ".env"), encoding="utf-8", errors="replace") as f:
            for line in f.read().splitlines():
                if line.strip().startswith(name + "="):
                    return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return None


def _dir_size(path):
    total = 0
    for base, _dirs, files in os.walk(path):
        for n in files:
            try:
                total += os.lstat(os.path.join(base, n)).st_size
            except OSError:
                pass
    return total


def _kept_checkout(runner_dir):
    """The git checkout a runner keeps for the ci-wait marker: DELIVERY_MARKER_ROOT in its .env, else the first
    _work/<name>/<name> folder with a .git. None when there is none."""
    root = _env_value(runner_dir, "DELIVERY_MARKER_ROOT")
    if root and os.path.exists(os.path.join(root.strip("\"'"), ".git")):
        return root.strip("\"'")
    work = os.path.join(runner_dir, "_work")
    try:
        for a in sorted(os.listdir(work)):
            for b in sorted(os.listdir(os.path.join(work, a))) if os.path.isdir(os.path.join(work, a)) else []:
                cand = os.path.join(work, a, b)
                if os.path.exists(os.path.join(cand, ".git")):
                    return cand
    except OSError:
        pass
    return None


def _push_probe(runner_dir):
    """None when the runner has no kept checkout, else (ok, detail): a dry-run push of a ci-wait test ref from it.
    A dry run contacts the remote and needs the same credentials as the real push; it writes nothing. It runs as the
    account of the doctor, which may differ from the runner account. No token is read or printed."""
    import subprocess
    root = _kept_checkout(runner_dir)
    if not root:
        return None
    fix = ("Store a fine-grained token for the runner account with contents write on the repository (git credential "
           "manager for that account), or use the runner pool. Without it the ci-wait marker cannot be written.")
    remote = _env_value(runner_dir, "DELIVERY_MARKER_REMOTE") or "origin"
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=20)
        if head.returncode != 0 or not head.stdout.strip():
            return False, "the checkout %s has no commit to push (%s)" % (root, fix)
        env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
        r = subprocess.run(["git", "push", "--dry-run", remote, "%s:refs/heads/ci-wait/doctor-check/probe" % head.stdout.strip()],
                           cwd=root, capture_output=True, text=True, timeout=60, env=env)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, "dry-run push from %s could not run (%s). %s" % (root, type(exc).__name__, fix)
    if r.returncode == 0:
        return True, "dry-run push of a ci-wait test ref from %s works" % root
    last = (r.stderr or r.stdout or "").strip().splitlines()[-1:] or ["no output"]
    return False, "dry-run push from %s failed (%s). %s" % (root, last[0][:160], fix)


def _runner_name(runner_dir):
    try:
        with open(os.path.join(runner_dir, ".runner"), encoding="utf-8-sig") as f:
            return json.load(f).get("agentName")
    except (OSError, ValueError, AttributeError):
        return None


def machine_items(root, cfg):
    """The single results of the machine check: [{'id', 'status', 'detail'}]."""
    import load as L
    opts = C.ci_options(cfg)
    dirs = _runner_dirs()
    folder = MS.machine_dir()
    used = "self-hosted" in opts.values() or os.path.exists(MS.config_path()) or os.path.isdir(MS.slots_dir())
    if not used:
        return [_item("machine.config", "skip", "no Option 1 project and no machine folder: the machine layer is not used")]
    items = []
    mcfg = MS.machine_config()
    path = MS.config_path()
    if not os.path.exists(path):
        items.append(_item("machine.config", "fail", "%s is missing. Run /delivery-ci-setup (it writes the machine config); "
                                                    "runners then use the default limits only." % path))
    elif not os.access(path, os.R_OK):
        items.append(_item("machine.config", "fail", "%s cannot be read by this account: runners run as other accounts and "
                                                    "would not see the limits. Grant read rights." % path))
    else:
        items.append(_item("machine.config", "ok", "%s: %d CI slot(s), local_heavy %d, cloud_ci_sessions %d, stale after %d min"
                           % (path, mcfg["ci_slots"], mcfg["local_heavy"], mcfg["cloud_ci_sessions"], mcfg["slot_stale_min"])))
        diff = L.legacy_differs()
        if diff:
            items.append(_item("machine.legacy", "warn", "machine.json and the old ~/.claude/luismc-delivery-machine.json differ "
                                                         "in load_limits: %s. machine.json wins; remove the old file." % ", ".join(diff)))
    for d in dirs:
        missing, policy = [], []
        for var, script in ((HOOK_VAR, "runner_load_gate"), (DONE_VAR, "runner_job_done")):
            v = _env_value(d, var)
            if v and script in v and v.strip("\"'").lower().endswith(".cmd"):
                policy.append("%s ends in .cmd: the runner rejects it (\"not a valid path to a script\") and every job fails. "
                              "Set it to the %s.ps1 wrapper (Windows) or %s.sh, then restart the runner" % (var, script, script))
            elif not (v and script in v):
                missing.append("%s=...%s" % (var, script))
            elif _is_windows() and v.strip("\"'").lower().endswith(".ps1"):
                problem = _execution_policy_problem(d)
                if problem and problem[0]:
                    policy.append(problem[1])
        if missing or policy:
            items.append(_item("machine.hooks:" + d, "fail", "; ".join(
                (["runner %s lacks %s" % (d, ", ".join(missing))] if missing else []) + policy)))
        else:
            items.append(_item("machine.hooks:" + d, "ok", "runner %s has both hooks" % d))
    if not dirs:
        items.append(_item("machine.hooks", "ok", "no runner folder found on this machine"))
    for d in dirs:
        probe = _push_probe(d)
        if probe is None:
            items.append(_item("machine.push:" + d, "ok", "runner %s has no kept checkout yet (the first job makes one)" % d))
        else:
            items.append(_item("machine.push:" + d, "ok" if probe[0] else "warn", probe[1]))
    now = __import__("time").time()
    stale = [s for s in MS.status(mcfg, now)["slots"] if not s["free"] and s.get("stale")]
    old_tickets = []
    try:
        for n in sorted(os.listdir(MS.queue_dir())):
            rec = MS._read_json(os.path.join(MS.queue_dir(), n)) if n.endswith(".json") else None
            if rec and now - (rec.get("queued_ts") or now) > mcfg["slot_stale_min"] * 60:
                old_tickets.append(n)
    except OSError:
        pass
    if stale or old_tickets:
        items.append(_item("machine.slots", "fail", "; ".join(
            ["slot %d held by %s run %s for %d min (stale: its process is gone or it is over %d min)"
             % (s["slot"], s.get("repo"), s.get("run_id"), s["age_s"] // 60, mcfg["slot_stale_min"]) for s in stale]
            + ["queue ticket %s is older than %d min" % (n, mcfg["slot_stale_min"]) for n in old_tickets])
            + " (the next gate frees them, or run machine_slots.py free-stale)"))
    else:
        items.append(_item("machine.slots", "ok", "no stale slot, no old ticket"))
    host, age = L.read_host_load()
    if host is None:
        items.append(_item("machine.hostload", "warn", "no host-load.json in %s: readers in WSL or the pool use their own "
                                                       "figures. Register the scheduled task (load.py --write)." % folder))
    elif age > MS.HOST_LOAD_MAX_AGE:
        items.append(_item("machine.hostload", "fail", "host-load.json is %d s old (limit %d s): the scheduled task that runs "
                                                       "load.py --write every 15 s is not running." % (age, MS.HOST_LOAD_MAX_AGE)))
    else:
        items.append(_item("machine.hostload", "ok", "host-load.json is %d s old" % age))
    try:
        import delivery_runner_pool as POOL  # noqa: PLC0415 - built on another branch (DL30)
    except ImportError:
        items.append(_item("pool", "skip", "delivery_runner_pool is not installed"))
    else:
        try:
            for r in POOL.doctor_checks(root):
                if isinstance(r, dict) and r.get("id"):
                    items.append(_item(str(r["id"]), r.get("status") if r.get("status") in ("ok", "warn", "fail", "skip")
                                       else "warn", str(r.get("detail") or "")))
        except Exception as exc:  # noqa: BLE001
            items.append(_item("pool", "fail", "pool checks crashed (%s: %s)" % (type(exc).__name__, exc)))
    if "self-hosted" in opts.values():
        r = H.gh(root, ["variable", "list", "--json", "name,value"])
        data = None
        if r is not None and r[0] == 0:
            try:
                data = json.loads(r[1] or "[]")
            except ValueError:
                data = None
        if data is None:
            items.append(_item("machine.runs_on", "warn", "cannot read the repository variables (gh not signed in or no rights): "
                                                          "check CI_RUNS_ON by hand"))
        elif not any(isinstance(v, dict) and v.get("name") == "CI_RUNS_ON" and str(v.get("value") or "").strip() for v in data):
            items.append(_item("machine.runs_on", "fail", "an OS is Option 1 but the repository variable CI_RUNS_ON is unset: jobs "
                                                          "would run on GitHub-hosted runners and may bill minutes. Run "
                                                          "/delivery-ci-setup, or `gh variable set CI_RUNS_ON --body '[\"self-hosted\",\"linux\"]'`."))
        else:
            items.append(_item("machine.runs_on", "ok", "CI_RUNS_ON is set"))
    sizes = [(d, _dir_size(os.path.join(d, "_work"))) for d in dirs if os.path.isdir(os.path.join(d, "_work"))]
    total = sum(sz for _, sz in sizes) / 1e9
    if sizes:
        text = "%.1f GB in the _work folders (%s)" % (total, ", ".join("%s %.1f GB" % (d, sz / 1e9) for d, sz in sizes))
        if total > WORK_WARN_GB:
            items.append(_item("machine.disk", "warn", text + ". Offer: `delivery_doctor.py clean-work` lists what can go; "
                                                         "`--yes` cleans runners with no job running."))
        else:
            items.append(_item("machine.disk", "ok", text))
    return items


def check_machine(root, cfg):
    items = machine_items(root, cfg)
    ok = not any(i["status"] == "fail" for i in items)
    detail = "; ".join("%s %s: %s" % (i["status"], i["id"], i["detail"]) for i in items if i["status"] != "ok") or \
        "; ".join(i["detail"] for i in items)
    return ok, detail, items


def clean_work(yes=False, out=print):
    """Empty the _work folder of every runner with no job running. Without `yes` it only lists. Returns the folders."""
    busy = {s.get("runner") for s in MS.status()["slots"] if not s["free"]}
    done = []
    for d in _runner_dirs():
        work = os.path.join(d, "_work")
        if not os.path.isdir(work):
            continue
        name = _runner_name(d)
        if name in busy:
            out("skip %s: runner %s has a job running" % (work, name))
            continue
        out("%s %s (%.1f GB)" % ("cleaning" if yes else "would clean", work, _dir_size(work) / 1e9))
        if yes:
            import runner_job_done as RJD
            RJD.empty_folder(work)
        done.append(work)
    return done


CHECKS = (("config", check_config), ("gh", check_gh), ("tz", check_tz), ("hooks", check_hooks), ("ledger", check_ledger),
          ("runner", check_runner), ("ci", check_ci), ("machine", check_machine))


def run_checks(root):
    cfg = H.load_config(root)
    out = []
    for name, fn in CHECKS:
        items = None
        try:
            res = fn(root, cfg)
            ok, detail = res[0], res[1]
            items = res[2] if len(res) > 2 else None
        except Exception as exc:  # noqa: BLE001 - a crashing check is a failing check
            ok, detail = False, "check crashed (%s: %s)" % (type(exc).__name__, exc)
        row = {"check": name, "ok": ok, "detail": detail}
        if items is not None:
            row["items"] = items
        out.append(row)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="delivery_doctor.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("action", nargs="?", default="self-check", choices=["self-check", "clean-work"])
    ap.add_argument("--yes", action="store_true", help="clean-work: delete, after the owner said yes")
    ap.add_argument("--root", help="repository root (default: nearest folder up with .delivery/)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if args.action == "clean-work":
        clean_work(args.yes)
        return 0
    root = os.path.abspath(args.root) if args.root else H.find_root({})
    if not root or not os.path.isdir(os.path.join(root, ".delivery")):
        print("delivery_doctor: no .delivery/ folder found", file=sys.stderr)
        return 2
    results = run_checks(root)
    if args.json:
        print(json.dumps({"root": root, "ok": all(r["ok"] for r in results), "checks": results}))
    else:
        for r in results:
            print("%-4s %-7s %s" % ("ok" if r["ok"] else "FAIL", r["check"], r["detail"]))
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
