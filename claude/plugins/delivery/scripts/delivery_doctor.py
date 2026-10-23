#!/usr/bin/env python3
"""Self-check of a delivery project: is everything the plugin needs in place?

    delivery_doctor.py [self-check] [--root DIR] [--json]

Six checks, each `ok` or `FAIL` with the fix:
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
Exit 0 all ok, 1 at least one FAIL, 2 no .delivery/ folder. Standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import delivery_config as C  # noqa: E402
import hooklib as H  # noqa: E402

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
    machine = L._read(L.machine_file())
    if isinstance(machine, dict) and isinstance(machine.get("runner_dirs"), list):
        dirs += [d for d in machine["runner_dirs"] if isinstance(d, str)]
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


def _windows_env_hook():
    if not sys.platform.startswith("win"):
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


def check_runner(root, cfg):
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


CHECKS = (("config", check_config), ("gh", check_gh), ("tz", check_tz), ("hooks", check_hooks), ("ledger", check_ledger),
          ("runner", check_runner))


def run_checks(root):
    cfg = H.load_config(root)
    out = []
    for name, fn in CHECKS:
        try:
            ok, detail = fn(root, cfg)
        except Exception as exc:  # noqa: BLE001 - a crashing check is a failing check
            ok, detail = False, "check crashed (%s: %s)" % (type(exc).__name__, exc)
        out.append({"check": name, "ok": ok, "detail": detail})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="delivery_doctor.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("action", nargs="?", default="self-check", choices=["self-check"])
    ap.add_argument("--root", help="repository root (default: nearest folder up with .delivery/)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
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
