#!/usr/bin/env python3
"""The engine of `/delivery-ci-setup` (CIR10 S6, DS180 join): guided CI setup for Options 1 to 4.

    delivery_ci_setup.py facts     [--root DIR]
    delivery_ci_setup.py apply     --answers FILE|-  [--root DIR] [--no-install] [--set-variables] [--json]
    delivery_ci_setup.py checklist [--root DIR] [--json]
    delivery_ci_setup.py confirm   ITEM...  [--root DIR]
    delivery_ci_setup.py pool-detect | pool-plan | pool-run | pool-refresh  --repos o/a,o/b [--windows-repos o/c] [--pool NAME] [--yes] [--yes-delete NAMES]

`pool-*` is the guided path for Option 1 (DL30): detect what exists, show one plan, remove old runners and build clean,
run each step after a yes. Deleting needs `--yes-delete` naming exactly what goes. It follows contract section 13:
plan first, one line per step, then Done / Left for you / What you can do now. Safe to run again.

The command file (`commands/delivery-ci-setup.md`) asks the owner every question and writes the answers as JSON.
There is no default at any question: `apply` refuses (exit 1, lists each missing answer) when one is absent. A
cap may be skipped, but only by an explicit `null`, so the owner decides and the tool never does.

Option 1 = `self-hosted`, 2 = `github-hosted`, 3 = `cloud`. Option 4 is Option 1 plus a `fallback` section (below). Answers:

  {"track": "ts", "options": {"linux": 1, "windows": "github-hosted"},
   "self_hosted": {"machines": [{"name": "pc1", "os": "linux", "labels": ["self-hosted", "linux"]}],
                   "serial": true, "wait_min": 10, "limits": {"pc1": {"memory_pct": 85, "cpu_pct": 60}}},
   "github_hosted": {"runner": {"windows": "windows-latest"}, "larger": false,
                     "monthly_minutes_cap": null, "windows_small_set_only": true},
   "cloud": {"repo": "o/r", "branches": ["release/*"], "shard_timeout_min": 30,
             "status_token_env": "CI_STATUS_TOKEN", "max_sessions_per_day": null},
   "fallback": {"options": {"linux": "cloud", "windows": "github-hosted"}, "after_min": 10,
                "max_shards_per_day": null, "max_minutes_per_month": null,
                "cloud": {"fire_url": "https://...", "token_env": "FALLBACK_TOKEN"},
                "limits": {"github-hosted": {"browser_workers": 2, "memory_gib": 8}}}}

`fallback` is optional (no section: no Option 4). When it is there, `after_min` and both caps are answered (a cap by a
number or an explicit `null`; no default). Its `options` name an OS the owner put on Option 1. It is written to
`ci.fallback` (`options`, `after_min`, `after_min_if_offline`, `only_for: all`, the caps, `cloud`, `records_branch`)
and `limits` to `ci.limits` (the keys `speed_probe.py` and `delivery_config.ci_limits()` read).

`apply` then writes `.delivery/config.json` (`ci.options`, `ci.guided`, `runners`, `ci.load_limits`, `ci.serial`,
`ci.wait_min`, `ci.hosted`, `ci.cloud`, `ci.fallback`, `ci.limits`), runs `delivery_ci_install.py install`, runs the doctor checks, and prints the
numbered by-hand list. The doctor re-checks every item of that list from the same function (`by_hand_items`). An item
the doctor cannot read (billing, a ruleset without admin rights, a remote machine) is closed by `confirm ITEM`.
It never commits or pushes. Exit 0 done, 1 refused (answers), 2 no .delivery/ folder or unreadable config.
Standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import delivery_ci as CI  # noqa: E402
import delivery_ci_install as INS  # noqa: E402
import delivery_config as C  # noqa: E402
import hooklib as H  # noqa: E402

NUMBERS = {"1": "self-hosted", "2": "github-hosted", "3": "cloud", "a": "self-hosted", "b": "github-hosted", "c": "cloud"}
NUMBER_OF = {"self-hosted": 1, "github-hosted": 2, "cloud": 3}
TOKEN_ENV = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
REPO = re.compile(r"^[^/\s]+/[^/\s]+$")

CHANGE_LATER = ("To change the choice later, run /delivery-ci-setup again. It asks every question again, rewrites the "
                "choice and prints what the new choice still needs. Nothing is removed from your machines or from GitHub. "
                "`delivery_ci.py set` changes only the option of one OS and nothing else.")


def option_of(raw):
    if isinstance(raw, bool):
        return None
    return NUMBERS.get(str(raw).strip().lower())


def _num(v, lo=1, hi=None):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v >= lo and (hi is None or v <= hi)


def _cap(section, key, label, errors):
    if key not in section:
        errors.append("%s: not answered (answer a number, or null for no cap)" % label)
    elif section[key] is not None and not _num(section[key]):
        errors.append("%s: must be a number of 1 or more, or null for no cap" % label)


def validate(a) -> list:
    """The missing or bad answers, one sentence each. No answer has a default."""
    errors = []
    if not isinstance(a, dict):
        return ["the answers are not a JSON object"]
    opts = a.get("options")
    if not isinstance(opts, dict) or not opts:
        return ["options: choose Option 1, 2 or 3 for each OS the product tests on"]
    chosen = {}
    for o, v in opts.items():
        if o not in C.CI_OS:
            errors.append("options: %r is not an OS (linux, windows, macos)" % o)
        elif option_of(v) is None:
            errors.append("options.%s: %r is not Option 1, 2 or 3" % (o, v))
        else:
            chosen[o] = option_of(v)
    if "cloud" in chosen.values() and any(o != "linux" and v == "cloud" for o, v in chosen.items()):
        errors.append("options: Option 3 (cloud sessions) runs on Linux only; pick Option 1 or 2 for the other OS")
    if a.get("track") is not None and a["track"] not in INS.TRACKS:
        errors.append("track: must be one of %s" % ", ".join(INS.TRACKS))
    if "self-hosted" in chosen.values():
        sh = a.get("self_hosted") if isinstance(a.get("self_hosted"), dict) else {}
        machines = sh.get("machines")
        if not isinstance(machines, list) or not machines:
            errors.append("self_hosted.machines: name each machine that runs a runner (a name and an OS each)")
            machines = []
        names = []
        for i, m in enumerate(machines):
            ok = (isinstance(m, dict) and isinstance(m.get("name"), str) and m["name"].strip() and m.get("os") in C.CI_OS
                  and isinstance(m.get("labels"), list) and m["labels"] and all(isinstance(x, str) and x for x in m["labels"]))
            if not ok:
                errors.append("self_hosted.machines[%d]: needs a name, an os and a non-empty list of labels" % i)
            else:
                names.append(m["name"])
        if len(set(names)) != len(names):
            errors.append("self_hosted.machines: a machine name is used twice")
        for o, v in sorted(chosen.items()):
            if v == "self-hosted" and not any(isinstance(m, dict) and m.get("os") == o for m in machines):
                errors.append("self_hosted.machines: no machine for %s (Option 1 needs at least one)" % o)
        if not isinstance(sh.get("serial"), bool):
            errors.append("self_hosted.serial: not answered (true = ready-PR runs queue one at a time)")
        if not _num(sh.get("wait_min")):
            errors.append("self_hosted.wait_min: not answered (minutes a job may wait before you add a runner; 10 is only an example)")
        limits = sh.get("limits") if isinstance(sh.get("limits"), dict) else {}
        for n in names:
            lim = limits.get(n)
            if not (isinstance(lim, dict) and _num(lim.get("memory_pct"), 1, 100) and _num(lim.get("cpu_pct"), 1, 100)):
                errors.append("self_hosted.limits.%s: not answered (memory_pct and cpu_pct ceilings, 1 to 100)" % n)
    if "github-hosted" in chosen.values():
        gh = a.get("github_hosted") if isinstance(a.get("github_hosted"), dict) else {}
        runner = gh.get("runner") if isinstance(gh.get("runner"), dict) else {}
        for o, v in sorted(chosen.items()):
            if v == "github-hosted" and not (isinstance(runner.get(o), str) and runner[o].strip()):
                errors.append("github_hosted.runner.%s: not answered (the runner label or size, e.g. ubuntu-latest)" % o)
        if not isinstance(gh.get("larger"), bool):
            errors.append("github_hosted.larger: not answered (true = larger runners, which need a paid plan)")
        _cap(gh, "monthly_minutes_cap", "github_hosted.monthly_minutes_cap", errors)
        if chosen.get("windows") == "github-hosted" and not isinstance(gh.get("windows_small_set_only"), bool):
            errors.append("github_hosted.windows_small_set_only: not answered (true = Windows runs only the small set)")
    if "cloud" in chosen.values():
        cl = a.get("cloud") if isinstance(a.get("cloud"), dict) else {}
        if not (isinstance(cl.get("repo"), str) and REPO.match(cl["repo"])):
            errors.append("cloud.repo: not answered (OWNER/NAME)")
        br = cl.get("branches")
        if not (isinstance(br, list) and br and all(isinstance(x, str) and x for x in br)):
            errors.append("cloud.branches: not answered (the branches to watch)")
        if not _num(cl.get("shard_timeout_min")):
            errors.append("cloud.shard_timeout_min: not answered (minutes before a shard counts as lost)")
        if not (isinstance(cl.get("status_token_env"), str) and TOKEN_ENV.match(cl["status_token_env"])):
            errors.append("cloud.status_token_env: not answered (the NAME of the environment variable, never the token)")
        _cap(cl, "max_sessions_per_day", "cloud.max_sessions_per_day", errors)
    errors += validate_fallback(a, chosen)
    return errors


FALLBACK_KINDS = ("cloud", "github-hosted")


def validate_fallback(a, chosen) -> list:
    """The optional Option 4 section: complete or absent. After X and both caps are answers, never defaults."""
    fb = a.get("fallback")
    errors = []
    lim = a.get("limits") if "limits" in a else (fb or {}).get("limits")
    if lim is not None:
        ok = isinstance(lim, dict) and all(
            k in FALLBACK_KINDS + ("self-hosted",) and isinstance(v, dict)
            and all(kk in C.LIMIT_KEYS and _num(vv, 0.5) for kk, vv in v.items()) for k, v in lim.items())
        if not ok:
            errors.append("limits: per option (self-hosted, github-hosted, cloud), only %s, each a number of 0.5 or more"
                          % ", ".join(C.LIMIT_KEYS))
    if fb is None:
        return errors
    if not isinstance(fb, dict):
        return errors + ["fallback: must be an object (or leave the section out for no Option 4)"]
    fopts = fb.get("options")
    if not isinstance(fopts, dict) or not fopts:
        errors.append("fallback.options: not answered (per OS: cloud or github-hosted)")
        fopts = {}
    for o, v in fopts.items():
        if o not in C.CI_OS or v not in FALLBACK_KINDS:
            errors.append("fallback.options.%s: must be an OS with the value cloud or github-hosted" % o)
        elif chosen.get(o) != "self-hosted":
            errors.append("fallback.options.%s: Option 4 needs Option 1 for %s first" % (o, o))
        elif v == "cloud" and o != "linux":
            errors.append("fallback.options.%s: cloud sessions run on Linux only" % o)
    if not _num(fb.get("after_min"), 0):
        errors.append("fallback.after_min: not answered (X, minutes of runner wait; 10 is only an example)")
    if "after_min_if_offline" in fb and not _num(fb["after_min_if_offline"], 0):
        errors.append("fallback.after_min_if_offline: must be a number of 0 or more")
    for key in ("max_shards_per_day", "max_minutes_per_month"):
        _cap(fb, key, "fallback." + key, errors)
    if "cloud" in fopts.values():
        cl = fb.get("cloud") if isinstance(fb.get("cloud"), dict) else {}
        if not (isinstance(cl.get("fire_url"), str) and cl["fire_url"].startswith("https://")):
            errors.append("fallback.cloud.fire_url: not answered (the https URL of the routine's API trigger)")
        if not (isinstance(cl.get("token_env"), str) and TOKEN_ENV.match(cl["token_env"])):
            errors.append("fallback.cloud.token_env: not answered (the NAME of the variable, never the token)")
    return errors


def apply_answers(cfg: dict, a: dict) -> dict:
    chosen = {o: option_of(v) for o, v in a["options"].items()}
    ci = cfg.get("ci") if isinstance(cfg.get("ci"), dict) else {}
    ci["options"] = chosen
    ci["guided"] = True
    for key in ("load_limits", "serial", "wait_min", "hosted", "cloud"):
        ci.pop(key, None)
    if "self-hosted" in chosen.values():
        sh = a["self_hosted"]
        runners = [r for r in cfg.get("runners") or [] if isinstance(r, dict) and r.get("name") not in
                   {m["name"] for m in sh["machines"]}]
        runners += [{"name": m["name"], "os": m["os"], "labels": list(m["labels"])} for m in sh["machines"]]
        cfg["runners"] = runners
        ci["load_limits"] = {n: {"memory_pct": v["memory_pct"], "cpu_pct": v["cpu_pct"]} for n, v in sh["limits"].items()
                        if n in {m["name"] for m in sh["machines"]}}
        ci["serial"] = sh["serial"]
        ci["wait_min"] = sh["wait_min"]
    if "github-hosted" in chosen.values():
        gh = a["github_hosted"]
        hosted = {"runner": {o: gh["runner"][o] for o, v in chosen.items() if v == "github-hosted"},
                  "larger": gh["larger"], "monthly_minutes_cap": gh["monthly_minutes_cap"]}
        if "windows_small_set_only" in gh:
            hosted["windows_small_set_only"] = gh["windows_small_set_only"]
        ci["hosted"] = hosted
    if "cloud" in chosen.values():
        cl = a["cloud"]
        ci["cloud"] = {"repo": cl["repo"], "status_token_env": cl["status_token_env"], "branches": list(cl["branches"]),
                       "shard_timeout_min": cl["shard_timeout_min"], "max_sessions_per_day": cl["max_sessions_per_day"]}
    ci.pop("fallback", None)
    fb = a.get("fallback")
    if isinstance(fb, dict):
        out = {"options": dict(fb["options"]), "after_min": fb["after_min"], "only_for": "all",
               "max_shards_per_day": fb["max_shards_per_day"], "max_minutes_per_month": fb["max_minutes_per_month"]}
        for key in ("after_min_if_offline", "records_branch"):
            if key in fb:
                out[key] = fb[key]
        if "cloud" in fb["options"].values():
            out["cloud"] = {"fire_url": fb["cloud"]["fire_url"], "token_env": fb["cloud"]["token_env"]}
        ci["fallback"] = out
    lim = a.get("limits") if "limits" in a else (fb or {}).get("limits")
    if isinstance(lim, dict):
        ci["limits"] = {k: dict(v) for k, v in lim.items()}
    cfg["ci"] = ci
    keep = {i["id"] for i in by_hand_items(cfg)}
    ci["confirmed"] = [x for x in ci.get("confirmed", []) if x in keep] if isinstance(ci.get("confirmed"), list) else []
    return cfg


# --- the by-hand list (one source for the printer and the doctor) ---------------------------------------------------

RUNNER_STEPS = {
    "linux": ["Open GitHub: repository Settings > Actions > Runners > New self-hosted runner, choose Linux. It shows the download and a token.",
              "On %(name)s run the download commands from that page, then: ./config.sh --url https://github.com/OWNER/REPO --token TOKEN --name %(name)s --labels %(labels)s",
              "Run it as a service: sudo ./svc.sh install && sudo ./svc.sh start"],
    "windows": ["Open GitHub: repository Settings > Actions > Runners > New self-hosted runner, choose Windows. It shows the download and a token.",
                "On %(name)s, in an administrator PowerShell, run the download commands from that page, then: .\\config.cmd --url https://github.com/OWNER/REPO --token TOKEN --name %(name)s --labels %(labels)s --runasservice",
                "The service starts by itself. Check it in services.msc (actions.runner.*)."],
    "macos": ["Open GitHub: repository Settings > Actions > Runners > New self-hosted runner, choose macOS. It shows the download and a token.",
              "On %(name)s run the download commands from that page, then: ./config.sh --url https://github.com/OWNER/REPO --token TOKEN --name %(name)s --labels %(labels)s",
              "Run it as a service: ./svc.sh install && ./svc.sh start"],
}


def _first_labels(cfg):
    ci = cfg.get("ci") or {}
    opts = C.ci_options(cfg)
    for o in C.CI_OS:
        if opts.get(o) == "self-hosted":
            for r in cfg.get("runners") or []:
                if isinstance(r, dict) and str(r.get("os", "")).lower() == o and isinstance(r.get("labels"), list):
                    return [x for x in r["labels"] if isinstance(x, str)]
    for o in C.CI_OS:
        if opts.get(o) == "github-hosted":
            label = ((ci.get("hosted") or {}).get("runner") or {}).get(o)
            if label:
                return label
    return None


def by_hand_items(cfg) -> list:
    """The steps only a person can do, for the options in `cfg`. Each: id, option (1 to 3), title, steps, check, value."""
    opts = C.ci_options(cfg)
    ci = cfg.get("ci") if isinstance(cfg.get("ci"), dict) else {}
    out = []
    if "self-hosted" in opts.values():
        wait = ci.get("wait_min")
        for o in C.CI_OS:
            if opts.get(o) != "self-hosted":
                continue
            for r in cfg.get("runners") or []:
                if not (isinstance(r, dict) and str(r.get("os", "")).lower() == o and r.get("name")):
                    continue
                labels = [x for x in r.get("labels", []) if isinstance(x, str)]
                sub = {"name": r["name"], "labels": ",".join(labels)}
                steps = [s % sub for s in RUNNER_STEPS[o]]
                lim = (ci.get("load_limits") or {}).get(r["name"]) or {}
                out.append({"id": "runner:%s" % r["name"], "option": 1, "check": "runner", "labels": labels,
                            "title": "Install the GitHub runner on %s (%s) with the labels %s" % (r["name"], o, ", ".join(labels)),
                            "steps": steps})
                out.append({"id": "load-gate:%s" % r["name"], "option": 1, "check": "confirm",
                            "title": "On %s set the load ceilings and the runner hook" % r["name"],
                            "steps": ["In ~/.claude/luismc-delivery-machine.json on %s set \"load_limits\": {\"memory_pct\": %s, \"cpu_pct\": %s}."
                                      % (r["name"], lim.get("memory_pct", "N"), lim.get("cpu_pct", "N")),
                                      "Set ACTIONS_RUNNER_HOOK_JOB_STARTED to scripts/runner_load_gate.ps1 (Windows; the runner rejects .cmd) or scripts/runner_load_gate.sh (Linux, macOS) in the runner's .env, and ACTIONS_RUNNER_HOOK_JOB_COMPLETED to the matching runner_job_done wrapper (README, 'CI runner gate'), then restart the runner."]})
        if ci.get("serial") is True:
            out.append({"id": "var:CI_SERIAL", "option": 1, "check": "var", "name": "CI_SERIAL", "value": "true",
                        "title": "Set the repository variable CI_SERIAL to true (ready-PR runs queue one at a time)",
                        "steps": ["gh variable set CI_SERIAL --body true"]})
        if isinstance(wait, (int, float)):
            out.append({"id": "extra-runner-note", "option": 1, "check": "note",
                        "title": "Watch the queue: if a job waits more than %s minutes, add a runner on another machine" % wait,
                        "steps": ["One runner of a label is the first bottleneck. Add a second machine by running this list's runner step on it and adding it to `runners`."]})
    if "github-hosted" in opts.values():
        hosted = ci.get("hosted") if isinstance(ci.get("hosted"), dict) else {}
        for o in C.CI_OS:
            if opts.get(o) == "github-hosted" and hosted.get("larger") is True:
                label = (hosted.get("runner") or {}).get(o, "LABEL")
                out.append({"id": "hosted-size:%s" % o, "option": 2, "check": "hosted", "label": label,
                            "title": "Create the larger %s runner named %s in the organisation settings" % (o, label),
                            "steps": ["Organisation Settings > Actions > Runners > New runner > New GitHub-hosted runner; name it %s, pick the size, and give the repository access to its group." % label]})
        out.append({"id": "spending-limit", "option": 2, "check": "confirm",
                    "title": "Set a spending limit in GitHub billing",
                    "steps": ["GitHub Settings > Billing and plans > Budgets and alerts: set a limit for Actions. This is the hard stop on cost; the plugin's counter is only the second brake.",
                              "The doctor cannot read billing. Run `delivery_ci_setup.py confirm spending-limit` when it is set."
                              + (" (Your minutes cap is %s a month.)" % hosted["monthly_minutes_cap"] if hosted.get("monthly_minutes_cap") else "")]})
    fb = ci.get("fallback") if isinstance(ci.get("fallback"), dict) else {}
    if "github-hosted" in (fb.get("options") or {}).values() and "github-hosted" not in opts.values():
        cap = fb.get("max_minutes_per_month")
        out.append({"id": "spending-limit", "option": 4, "check": "confirm",
                    "title": "Set a spending limit in GitHub billing (the hosted fallback bills per minute)",
                    "steps": ["GitHub Settings > Billing and plans > Budgets and alerts: set a limit for Actions. This is the hard stop on cost; the fallback caps are only the second brake, and they are optional.",
                              "The doctor cannot read billing. Run `delivery_ci_setup.py confirm spending-limit` when it is set."
                              + (" (Your minutes cap is %s a month.)" % cap if cap else " (You set no minutes cap.)")]})
    first = _first_labels(cfg)
    if first and ({"self-hosted", "github-hosted"} & set(opts.values())):
        value = json.dumps(first if isinstance(first, list) else first)
        out.append({"id": "var:CI_RUNS_ON", "option": 1 if "self-hosted" in opts.values() else 2, "check": "var",
                    "name": "CI_RUNS_ON", "value": value,
                    "title": "Set the repository variable CI_RUNS_ON to %s" % value,
                    "steps": ["gh variable set CI_RUNS_ON --body '%s'" % value]})
    if "cloud" in opts.values():
        cl = C.ci_cloud(cfg)
        env = cl["status_token_env"] or "TOKEN_VARIABLE"
        out.append({"id": "status-token", "option": 3, "check": "token", "env": env,
                    "title": "Create the statuses-only token and put it in the cloud environment as %s" % env,
                    "steps": ["GitHub Settings > Developer settings > Fine-grained tokens: repository %s only, permission Commit statuses: Read and write, nothing else." % (cl["repo"] or "OWNER/NAME"),
                              "Store it as the variable %s in the Claude cloud environment. Never write it to a file." % env]})
        out.append({"id": "ruleset-any-source", "option": 3, "check": "ruleset",
                    "title": "Change the ruleset so the required checks accept 'Any source'",
                    "steps": ["Repository Settings > Rules > Rulesets > the one for the default branch > Require status checks: for each cloud check, set Source to 'Any source'. The status is not posted by the Actions app."]})
        out.append({"id": "session-access", "option": 3, "check": "confirm",
                    "title": "Give the cloud sessions access to the repository",
                    "steps": ["In the Claude cloud environment, add %s as a repository the sessions may clone and push result branches to." % (cl["repo"] or "the repository"),
                              "Run `delivery_ci_setup.py confirm session-access` when done."]})
    return out


# --- the doctor's checks of the by-hand list -----------------------------------------------------------------------

def _gh_json(root, args):
    r = H.gh(root, args)
    if r is None or r[0] != 0:
        return None, ("gh cannot run" if r is None else "gh refused (admin rights needed?)")
    try:
        return json.loads(r[1] or "null"), None
    except ValueError:
        return None, "gh returned invalid JSON"


def check_item(root, cfg, item) -> tuple:
    """(state, detail). state: ok (verified), confirmed (the owner said so), open (checked, not done),
    unknown (cannot be checked here; close it with `confirm`)."""
    confirmed = item["id"] in ((cfg.get("ci") or {}).get("confirmed") or [])
    kind = item["check"]
    state, detail = "unknown", "cannot be checked here"
    if kind == "note":
        return "ok", "advice only"
    if kind == "runner":
        data, why = _gh_json(root, ["api", "repos/{owner}/{repo}/actions/runners?per_page=100"])
        if data is None or not isinstance(data, dict) or not isinstance(data.get("runners"), list):
            state, detail = "unknown", "cannot list runners (%s)" % (why or "no runner list")
        else:
            name = item["id"].split(":", 1)[1]
            mine = [r for r in data["runners"] if isinstance(r, dict) and r.get("name") == name]
            have = {str(l.get("name")).lower() for r in mine for l in r.get("labels", []) if isinstance(l, dict)}  # GitHub labels are case-insensitive
            if not mine:
                state, detail = "open", "no runner named %s is registered" % name
            elif not any(r.get("status") == "online" for r in mine):
                state, detail = "open", "runner %s is registered but offline" % name
            elif not {x.lower() for x in item["labels"]} <= have:
                state, detail = "open", "runner %s lacks the labels %s" % (name, ", ".join(sorted(x for x in item["labels"] if x.lower() not in have)))
            else:
                state, detail = "ok", "runner %s is online with its labels" % name
    elif kind == "var":
        r = H.gh(root, ["variable", "get", item["name"]])
        if r is None:
            state, detail = "unknown", "gh cannot run"
        elif r[0] != 0:
            state, detail = "open", "%s is not set" % item["name"]
        elif r[1].strip().lower() == item["value"].lower():  # label case does not matter to GitHub
            state, detail = "ok", "%s is set" % item["name"]
        else:
            state, detail = "open", "%s is %s, expected %s" % (item["name"], r[1].strip(), item["value"])
    elif kind == "hosted":
        data, why = _gh_json(root, ["api", "orgs/{owner}/actions/hosted-runners"])
        if data is None or not isinstance(data, dict) or not isinstance(data.get("runners"), list):
            state, detail = "unknown", "cannot list larger runners (%s)" % (why or "no list")
        elif any(isinstance(r, dict) and r.get("name") == item["label"] for r in data["runners"]):
            state, detail = "ok", "larger runner %s exists" % item["label"]
        else:
            state, detail = "open", "no larger runner named %s" % item["label"]
    elif kind == "token":
        if os.environ.get(item["env"]):
            state, detail = "ok", "%s is set here" % item["env"]
        else:
            state, detail = "unknown", "%s is not set here (it lives in the cloud environment)" % item["env"]
    elif kind == "ruleset":
        state, detail = _check_ruleset(root, cfg)
    elif kind == "confirm":
        state, detail = "unknown", "the doctor cannot read this"
    if confirmed and state == "unknown":
        return "confirmed", "confirmed by the owner"
    return state, detail


def _check_ruleset(root, cfg):
    listing, why = _gh_json(root, ["api", "repos/{owner}/{repo}/rulesets"])
    if not isinstance(listing, list):
        return "unknown", "cannot read rulesets (%s)" % (why or "no list")
    contexts = set(C.cloud_contexts(root, cfg))
    pinned, seen = [], 0
    for rs in listing:
        if not (isinstance(rs, dict) and rs.get("enforcement") == "active"):
            continue
        full, why = _gh_json(root, ["api", "repos/{owner}/{repo}/rulesets/%s" % rs.get("id")])
        if not isinstance(full, dict):
            return "unknown", "cannot read ruleset %s (%s)" % (rs.get("id"), why)
        for rule in full.get("rules") or []:
            if isinstance(rule, dict) and rule.get("type") == "required_status_checks":
                for chk in (rule.get("parameters") or {}).get("required_status_checks") or []:
                    if isinstance(chk, dict) and (not contexts or chk.get("context") in contexts):
                        seen += 1
                        if chk.get("integration_id") not in (None, 0):
                            pinned.append(str(chk.get("context")))
    if pinned:
        return "open", "required check(s) %s accept only one app, not 'Any source'" % ", ".join(sorted(set(pinned)))
    return "ok", ("required checks accept any source" if seen else "no active ruleset requires the cloud checks yet")


def check_by_hand(root, cfg) -> tuple:
    """(problems, notes) of the by-hand list for the doctor. Empty when the project did not use the guided setup."""
    if not (isinstance(cfg.get("ci"), dict) and cfg["ci"].get("guided") is True):
        return [], []
    problems, notes = [], []
    for it in by_hand_items(cfg):
        state, detail = check_item(root, cfg, it)
        if state == "open":
            problems.append("by hand, %s: %s" % (it["id"], detail))
        elif state == "unknown":
            problems.append("by hand, %s: %s. Do it, then run `delivery_ci_setup.py confirm %s`" % (it["id"], detail, it["id"]))
        elif state == "confirmed":
            notes.append("%s confirmed by the owner" % it["id"])
    return problems, notes


# --- printing and commands -----------------------------------------------------------------------------------------

def format_checklist(items) -> list:
    if not items:
        return ["By hand: nothing."]
    lines = ["By hand, %d step(s). The doctor re-checks each one (`delivery_doctor.py`):" % len(items)]
    for n, it in enumerate(items, 1):
        lines.append("%d. [%s] (Option %s) %s" % (n, it["id"], it["option"], it["title"]))
        lines += ["     - %s" % s for s in it["steps"]]
    return lines


def facts(root) -> dict:
    cfg = H.load_config(root)
    track = None
    for name, t in (("package.json", "ts"), ("go.mod", "go"), ("Cargo.toml", "rust")):
        if os.path.exists(os.path.join(root, name)):
            track = t
            break
    if track is None and any(n.endswith((".sln", ".csproj")) for n in os.listdir(root)):
        track = "dotnet"
    shards, err = C.load_shards(root, cfg)
    return {"track": track, "shard_table": os.path.exists(C.shard_table_path(root, cfg)), "shard_table_error": err,
            "shard_oses": sorted({s["os"] for s in shards}), "installer_workflow": os.path.exists(
                os.path.join(root, ".github", "workflows", "package.yml")),
            "options": CI.describe(cfg), "guided": bool((cfg.get("ci") or {}).get("guided"))}


def set_variables(root, cfg) -> list:
    out = []
    for it in by_hand_items(cfg):
        if it["check"] == "var":
            r = H.gh(root, ["variable", "set", it["name"], "--body", it["value"]])
            out.append("%s: %s" % (it["name"], "set" if r and r[0] == 0 else "gh refused or cannot run; set it by hand"))
    return out


def cmd_apply(args, root, path) -> int:
    raw = sys.stdin.read() if args.answers == "-" else open(args.answers, encoding="utf-8").read()
    try:
        answers = json.loads(raw)
    except ValueError as exc:
        print("delivery_ci_setup: the answers are not JSON (%s)" % exc, file=sys.stderr)
        return 1
    errors = validate(answers)
    if not args.no_install and not (isinstance(answers, dict) and answers.get("track") in INS.TRACKS):
        errors.append("track: not answered (ts, go, rust or dotnet), or use --no-install")
    if errors:
        print("delivery_ci_setup: no default is used. Missing or bad answers:", file=sys.stderr)
        for e in errors:
            print("  - %s" % e, file=sys.stderr)
        return 1
    cfg = apply_answers(CI.read_config(path), answers)
    CI.write_config(path, cfg)
    lines = ["Config written: %s" % os.path.relpath(path, root)]
    if not args.no_install:
        items = INS.plan(answers["track"], root, "install")
        INS.apply(items, root)
        counts = {}
        for _r, _s, a in items:
            counts[a] = counts.get(a, 0) + 1
        lines.append("Installer: %s" % ", ".join("%d %s" % (n, a) for a, n in sorted(counts.items())))
    if args.set_variables:
        lines += set_variables(root, cfg)
    import delivery_doctor as D
    results = D.run_checks(root)
    lines += ["Doctor (before the by-hand steps, so some FAIL lines are expected):"]
    lines += ["  %-4s %-7s %s" % ("ok" if r["ok"] else "FAIL", r["check"], r["detail"]) for r in results]
    items = by_hand_items(cfg)
    lines += format_checklist(items)
    lines.append(CHANGE_LATER)
    if args.json:
        print(json.dumps({"config": os.path.relpath(path, root), "doctor": results, "by_hand": items}))
    else:
        print("\n".join(lines))
    return 0


# --- the guided path for Option 1 (DL30, D26, D44) and the section 13 pattern ---------------------------------------------

def render_plan(pl, found) -> list:
    """Section 13, part 1: one plan before anything changes. Paths, outside changes, what needs the owner, how long."""
    from delivery_runner_pool import pool_dir
    lines = ["Plan (nothing has changed yet):"]
    gh = found["github"]
    lines.append("Found: %d repositories you administer, %d runner services, %d runner folders, %d containers."
                 % (len(gh["repos"]), len(found["services"]), len(found["folders"]), len(found["containers"])))
    if gh.get("error"):
        lines.append("  GitHub could not be read: %s" % gh["error"])
    for r in gh["repos"]:
        if r["error"]:
            lines.append("  %s: runners not readable (%s)" % (r["repo"], r["error"]))
    cap = pl.get("cap")
    if cap and cap.get("ok"):
        m = cap.get("measured") or {}
        if cap.get("source") == "kept":
            mc = cap.get("measured_cap") or {}
            how = ("kept from the pool's .env; measured now: %s GiB, %s CPUs; --resize uses the measured cap"
                   % (mc.get("mem_gib"), mc.get("cpus")))
        else:
            how = "measured on this machine unless you gave a number" if m else "from the numbers you gave"
        lines.append("Pool cap: %s GiB memory, %s CPUs (%s)." % (cap["mem_gib"], cap["cpus"], how))
        if m:
            lines.append("  Sizing inputs: total %s GiB; used outside WSL %s GiB (median of %s samples); %d%% budget %s GiB; "
                         "room %s GiB; Docker ceiling %s." % (
                             m.get("total_gib"), m.get("used_gib"), m.get("samples") or 1, 85, m.get("budget_gib"),
                             m.get("room_gib"), ("%s GiB" % m["docker_gib"]) if m.get("docker_gib") is not None else "not set"))
        if cap.get("reason"):
            lines.append("  Cap changed: %s." % cap["reason"])
    if pl.get("derived") and not pl.get("blocked"):
        import delivery_runner_pool as P
        lin, win = P.derive_repos(found)
        lines.append("Repositories (none named, taken from GitHub): Linux: %s; Windows: %s."
                     % (", ".join(lin) or "none", ", ".join(win) or "none"))
    for step in pl["steps"]:
        mark = "already set" if step["state"] == "already" else ("you run it" if step["elevated"] else
                                                                  ("asks a second yes (deletes)" if step["delete"] else "I run it"))
        lines.append("  - %s [%s]" % (step["title"], mark))
    for r in pl["refused"]:
        lines.append("  ! %s" % r["reason"])
    if pl.get("blocked"):
        lines.append("  ! %s" % pl["blocked"])
    lines.append("Writes in this repository: nothing. Writes on this machine: %s" % pool_dir(pl["pool"]))
    lines.append("Changes outside the repository: GitHub runner registrations, repository variables, Docker, the machine config.")
    lines.append("Needs you: %s." % "; ".join(pl["needs"]))
    lines.append("About %d minutes." % pl["minutes"])
    return lines


def render_summary(done, left, can_do) -> list:
    """Section 13, part 4: Done, Left for you (numbered, exact steps), What you can do now."""
    lines = ["Done"]
    lines += ["  - %s" % d for d in done] or ["  - nothing changed (everything was already set)"]
    lines.append("Left for you")
    lines += ["  %d. %s" % (i, x) for i, x in enumerate(left, 1)] or ["  nothing"]
    lines.append("What you can do now")
    lines += ["  - %s" % c for c in can_do]
    return lines


def can_do_now(pool) -> list:
    return ["`python3 scripts/delivery_ci.py slots`: who holds each CI slot and who waits.",
            "`gh workflow run pool-check.yml`: run one test job through pool \"%s\"." % pool,
            "`python3 scripts/delivery_doctor.py`: check the machine, the pool and the runners.",
            "`/delivery-ci-setup`: run again; it says what is already set and changes only what is missing."]


def cmd_pool(args, root) -> int:
    import delivery_runner_pool as P
    probe = P.Probe()
    found = P.detect(probe)
    split = lambda v: [x for x in (v or "").split(",") if x]  # noqa: E731
    if args.action == "pool-detect":
        print(json.dumps(found, indent=2))
        return 0
    if args.action == "pool-refresh":
        return cmd_pool_refresh(args, root, P, probe)
    found["pool_env"] = P.read_pool_env(probe, args.pool)
    cap = P.resolve_cap(found, args.total_gib, args.used_gib, args.cpus, args.docker_gib, args.largest_shard_gib,
                        getattr(args, "resize", False), getattr(args, "shrink", False), getattr(args, "pool_gib", None),
                        getattr(args, "pool_cpus", None))
    if cap is None:
        print("delivery_ci_setup: this machine's memory or CPUs could not be measured. Give --total-gib and --cpus.",
              file=sys.stderr)
        return 1
    if not cap["ok"]:
        print("delivery_ci_setup: %s" % cap["message"], file=sys.stderr)
        return 1
    if getattr(args, "playwright", None) and not P.valid_playwright_version(args.playwright):
        print("delivery_ci_setup: --playwright needs a version like 1.62.1", file=sys.stderr)
        return 2
    pl = P.plan(found, split(args.repos), split(args.windows_repos), args.pool, cap, repo_paths=[root], probe=probe,
                browsers=getattr(args, "browsers", None), playwright_version=getattr(args, "playwright", None),
                drop_layers=getattr(args, "drop_layer", None) or (), drop_apt=getattr(args, "drop_apt", None) or ())
    print("\n".join(render_plan(pl, found)))
    if args.action == "pool-plan":
        return 0
    if pl.get("blocked"):
        return 1
    yes_delete = set(split(args.yes_delete))

    def check(step):
        """The step's own check: a service step looks for the service; the rest use the pool module's check."""
        if step["action"] == "windows-service":
            return any(step["slug"] in (x["name"] or "") for x in P.detect_services(probe))
        return P.default_check(step, probe)
    result = P.run(pl, ask=lambda st: bool(args.yes), ask_delete=lambda st: all(n in yes_delete for n in st["names"]),
                   execute=P.Executor(probe).run, check=check)
    left = []
    if result["failed"]:
        left.append("Fix this and run the setup again: %s." % result["failed"]["title"])
    for sid in result["left"]:
        if not result["failed"] or sid != result["failed"]["id"]:
            left.append("Not run yet: %s" % sid)
    print("\n".join(render_summary(result["done"], left, can_do_now(args.pool))))
    return 1 if result["failed"] or result["left"] else 0


def pool_refresh_source(args, root):
    """DL155: the repo that asks: the first --repos entry, else OWNER/NAME of the origin remote, else the folder name."""
    first = [x.strip() for x in (getattr(args, "repos", None) or "").split(",") if x.strip()]
    if first:
        return first[0]
    try:
        out = subprocess.run(["git", "-C", root, "remote", "get-url", "origin"], capture_output=True, text=True, timeout=10).stdout.strip()
        m = re.search(r"([\w.-]+/[\w.-]+?)(?:\.git)?/?$", out)
        if m:
            return m.group(1)
    except (OSError, subprocess.SubprocessError):
        pass
    return os.path.basename(root)


def _plugin_version() -> str:
    try:
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".claude-plugin", "plugin.json"), encoding="utf-8") as f:
            return str(json.load(f).get("version") or "?")
    except (OSError, ValueError):
        return "?"


def cmd_pool_refresh(args, root, P, probe) -> int:
    """B14: rewrite RUNNER_SHA256, POOL_BROWSERS and PLAYWRIGHT_VERSION in the pool's .env and rebuild. The cap stays."""
    if getattr(args, "playwright", None) and not P.valid_playwright_version(args.playwright):
        print("delivery_ci_setup: --playwright needs a version like 1.62.1", file=sys.stderr)
        return 2
    rp = P.refresh_plan(probe, args.pool, [root], getattr(args, "browsers", None), getattr(args, "playwright", None),
                        pool_refresh_source(args, root), getattr(args, "drop_layer", None) or (), getattr(args, "drop_apt", None) or ())
    if rp.get("error"):
        print("delivery_ci_setup: %s" % rp["error"], file=sys.stderr)
        return 1
    lines = ["Refresh plan for pool \"%s\" (the cap and every other line stay):" % args.pool]
    for k, (old, new) in sorted(rp["changes"].items()):
        if k == "RUNNER_SHA256" and rp.get("sha_reason"):
            lines.append("  - %s: %s -> %s (%s)" % (k, P.short_sha(old), P.short_sha(new), rp["sha_reason"]))
        else:
            lines.append("  - %s: %s -> %s" % (k, old or "unset", new))
    ver = _plugin_version()
    lines += ["  - %s: differs from luismc-delivery %s" % (f, ver) for f in rp.get("files", [])]
    lines += ["  - layer %s%s" % (n, " (asked by %s)" % who if who else "") for n, who in rp.get("layers", [])]
    lines += ["  - %s" % n for n in rp.get("notes", [])]
    if not rp["changes"] and not rp.get("files"):
        lines.append("  - nothing to change in %s" % rp["path"])
    elif rp.get("why"):
        lines.append("  %s" % rp["why"])
    lines.append("  - then rebuild the pool image (only when no job runs)")
    print("\n".join(lines))
    if not getattr(args, "yes", False):
        return 0
    ok, detail = P.Executor(probe).refresh(rp, force=getattr(args, "force", False))
    print(detail)
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="delivery_ci_setup.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("action", choices=["facts", "apply", "checklist", "confirm", "pool-detect", "pool-plan", "pool-run",
                                           "pool-refresh"])
    ap.add_argument("items", nargs="*", help="confirm: the item ids")
    ap.add_argument("--answers", help="apply: a JSON file of answers, or - for stdin")
    ap.add_argument("--root", default=".")
    ap.add_argument("--no-install", action="store_true")
    ap.add_argument("--set-variables", action="store_true", help="apply: run `gh variable set` for the repository variables")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--repos", help="pool-*: Linux repositories, OWNER/NAME comma separated")
    ap.add_argument("--windows-repos", help="pool-*: repositories that test on Windows")
    ap.add_argument("--pool", default="main")
    ap.add_argument("--total-gib", type=float)
    ap.add_argument("--used-gib", type=float, help="pool-*: memory used outside WSL, in GiB (default: measured). Not the PC's whole use")
    ap.add_argument("--cpus", type=float, help="pool-*: this machine's CPU count (default: measured). Not the pool's CPUs")
    ap.add_argument("--docker-gib", type=float)
    ap.add_argument("--largest-shard-gib", type=float)
    ap.add_argument("--resize", action="store_true", help="pool-plan/run: use the measured cap, not the one in the pool .env")
    ap.add_argument("--shrink", action="store_true", help="pool-plan/run: allow --resize to lower POOL_MEM or POOL_CPUS")
    ap.add_argument("--pool-gib", type=float, help="pool-plan/run: the pool's memory you want, in GiB (used as given if it fits the budgets)")
    ap.add_argument("--pool-cpus", type=float, help="pool-plan/run: the pool's CPUs you want (used as given if it fits the budgets)")
    ap.add_argument("--browsers", choices=["none", "chromium"], help="pool-plan/run/refresh: set POOL_BROWSERS (default: keep the .env value; detection may raise none to chromium)")
    ap.add_argument("--drop-layer", action="append", metavar="NAME", help="pool-plan/run/refresh: remove this layer from the pool (repeatable)")
    ap.add_argument("--drop-apt", action="append", metavar="NAME", help="pool-plan/run/refresh: remove this apt package from the pool (repeatable)")
    ap.add_argument("--playwright", metavar="X", help="pool-plan/run/refresh: set PLAYWRIGHT_VERSION exactly (may lower it)")
    ap.add_argument("--force", action="store_true", help="pool-refresh: rebuild even while a pool runner is busy (warns)")
    ap.add_argument("--yes", action="store_true", help="pool-run/refresh: the owner said yes to the plan shown (not to deletions)")
    ap.add_argument("--yes-delete", help="pool-run: what the owner agreed to delete, named exactly, comma separated")
    args = ap.parse_args(argv)
    root = os.path.abspath(args.root)
    if not os.path.isdir(os.path.join(root, ".delivery")):
        print("delivery_ci_setup: no .delivery/ folder in %s" % root, file=sys.stderr)
        return 2
    path = C.config_file(root)
    try:
        cfg = CI.read_config(path)
    except (OSError, ValueError) as exc:
        print("delivery_ci_setup: cannot read %s (%s)" % (path, exc), file=sys.stderr)
        return 2
    if args.action == "facts":
        print(json.dumps(facts(root), indent=2))
        return 0
    if args.action.startswith("pool-"):
        return cmd_pool(args, root)
    if args.action == "apply":
        if not args.answers:
            print("delivery_ci_setup: apply needs --answers FILE|-", file=sys.stderr)
            return 1
        return cmd_apply(args, root, path)
    items = by_hand_items(cfg)
    if args.action == "checklist":
        print(json.dumps(items) if args.json else "\n".join(format_checklist(items)))
        return 0
    known = {i["id"] for i in items}
    bad = [x for x in args.items if x not in known]
    if not args.items or bad:
        print("delivery_ci_setup: confirm needs item ids from the list: %s" % ", ".join(sorted(known)), file=sys.stderr)
        return 1
    ci = cfg.setdefault("ci", {})
    ci["confirmed"] = sorted(set(ci.get("confirmed") or []) | set(args.items))
    CI.write_config(path, cfg)
    print("confirmed: %s" % ", ".join(args.items))
    return 0


if __name__ == "__main__":
    sys.exit(main())
