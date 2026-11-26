#!/usr/bin/env python3
"""Self-check of a delivery project: is everything the plugin needs in place?

    delivery_doctor.py [self-check] [--root DIR] [--json]

Seven checks (an eighth, `rust`, appears only on the rust track: see below), each `ok` or `FAIL` with the fix:
  config   .delivery/config.json passes delivery_config.py validate (no errors; a missing file is fine)
  gh       `gh auth status` succeeds (the watcher and the hooks need a signed-in gh; DELIVERY_GH replaces gh in tests)
  tz       the configured `tz` loads through zoneinfo; if tzdata is missing this FAILS instead of quietly using UTC
  hooks    the plugin's hooks.json names the five hook scripts and they exist, and luismc-delivery is enabled in
           .claude/settings.json, .claude/settings.local.json or ~/.claude/settings.json (enabledPlugins)
  ledger   .delivery/ is writable and ledger.json, when present, is valid JSON
  ci       (DL15) the CI option chosen per OS (Option 1 self-hosted, Option 2 github-hosted, Option 3 cloud) and what each one needs:
           a: an entry in `runners` for that OS; b: workflow files in .github/workflows; c: ci.cloud.repo,
           status_token_env and branches, a shard for the OS, and one context per shard. FAILS when the shard table
           has a shard for an OS that was not chosen (there is no default). Nothing chosen and no shard table: ok.
           (CIR10 S6) When `/delivery-ci-setup` wrote the config (`ci.guided`), it also checks every item of the by-hand
           list that the setup printed (delivery_ci_setup.py `by_hand_items`): runner online with its labels, repository
           variables, larger runner, token variable, ruleset 'Any source'. An item it cannot read (billing, a remote
           machine, the cloud environment) FAILS until `delivery_ci_setup.py confirm ITEM`.
  rust     (DS202) only when gate.json says track rust or scripts/delivery/rust_ci.py exists; other tracks see no row.
           FAILS on: no host linker ("linker cc not found" and the fix command); clang-cl or lld-link missing when
           rust-toolchain.toml targets include Windows; rust-toolchain.toml missing or not an exact version (not
           stable); tools.json without a sha256 for rustup-init, llvm, zig or cargo-deny (missing keys are findings).
           DL-98 (D104): WARNS when a pull-request workflow has a matrix without `fail-fast: false` or a stop-at-first-failure
           flag on a suite step, unless ci.jobs.<id>.fail_fast is "on".
           WARNS (never fails) on: advisory DB cache older than 7 days or absent; under 10 GB free for target/.
           It changes nothing; each finding prints the command.
  scripts  (DL188) `ci.scripts-current`: scripts/delivery files that are older than, or missing from, the plugin's templates
           (the same plan `delivery_ci_install.py update` makes; a file in ci-install.json "keep" is ok). WARNS, never fails.
           With `ci.wait_min` set, the CI line shows that wait (10 when unset). Cached tools are found in the ci_tool cache.
  ci-filters (DL-116) WARNS (never fails) when a workflow in watcher.ci_workflows has a pull-request `paths` or `paths-ignore` filter (ci_areas_check.py).
  plugins  (DL173) `plugins.compat`: the highest installed version of each luismc-* plugin, read from the Claude plugin cache
           (~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/; DELIVERY_PLUGIN_CACHE replaces the root in tests),
           against references/plugin-compat.json. WARNS (never fails) per pair that does not fit, with
           `claude plugin update <plugin>@dev-standards`. A plugin that is not installed is skipped; with nothing to warn about there is no row. No network.
Exit 0 all ok, 1 at least one FAIL, 2 no .delivery/ folder. Standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import delivery_ci_setup as SETUP  # noqa: E402
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
    detail = "%d events registered, plugin enabled" % len(hooks["hooks"])
    if cfg.get("no_attribution") is True:
        detail += ("; note: no_attribution is on. No luismc-delivery hook advises AI attribution or re-authoring commits. "
                   "If a hosting-platform hook says to, the project rule wins: commit as the owner, add no AI "
                   "Co-Authored-By line, and do not amend commits to change the author")
    return True, detail


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


def _wait_min(cfg):
    """Minutes a job may wait for a runner: ci.wait_min, 10 when unset or bad (DL188)."""
    ci = cfg.get("ci") if isinstance(cfg.get("ci"), dict) else {}
    w = ci.get("wait_min")
    return w if isinstance(w, (int, float)) and not isinstance(w, bool) and w > 0 else C.RUNNER_WAIT_EXAMPLE_MIN


def _second_machine_note(cfg, os_name):
    """Option 1 is own runners on ANY machines. Name the machines found for the OS, and the by-hand steps to add one
    more on another machine (a note, never a failure: one runner works, it is only the first bottleneck)."""
    mine = [r for r in cfg.get("runners") or [] if isinstance(r, dict) and os_name in _runner_oses({"runners": [r]})]
    names = ", ".join(str(r.get("name")) for r in mine)
    labels = next((r.get("labels") for r in mine if r.get("labels")), None)
    steps = "; ".join("(%d) %s" % (i, t) for i, t in enumerate(C.runner_steps(os_name, labels, _wait_min(cfg)), 1))
    return "%s: %d runner(s) (%s). %s. To add a runner on another machine, by hand: %s" % (
        os_name, len(mine), names, C.add_runner_advice(_wait_min(cfg)), steps)


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


def _item(id_, status, detail):
    return {"id": id_, "status": status, "detail": detail}


# --- workflow labels (DL317, DL318) -----------------------------------------------------------------

GENERIC_VARS = ("CI_RUNS_ON", "CI_RUNS_ON_WINDOWS")
# DL394: per OS, the variables a workflow reads, first match wins (new runner service variable, then the old one).
CRSP_RUNS_ON_ORDER = (("linux", ("CRSP_RUNS_ON_LINUX", "CI_RUNS_ON")),
                 ("windows", ("CRSP_RUNS_ON_WINDOWS", "CI_RUNS_ON_WINDOWS")),
                 ("macos", ("CRSP_RUNS_ON_MACOS",)))


def _same_labels(a, b):
    """True when two variable values name the same labels (JSON compared, case ignored)."""
    def norm(v):
        try:
            v = json.loads(v)
        except (TypeError, ValueError):
            pass
        return json.dumps(v, sort_keys=True).lower()
    return norm(a) == norm(b)


def resolve_runs_on(variables):
    """DL394: [(os, variable name or None, value or None, other)] for each OS. `variable` is the first one set; `other` is the
    old variable when it is set to a different value than the winning new one (the new variable wins), else None."""
    out = []
    for o, names in CRSP_RUNS_ON_ORDER:
        set_ = [(n, str(variables.get(n) or "").strip()) for n in names]
        set_ = [(n, v) for n, v in set_ if v]
        if not set_:
            out.append((o, None, None, None))
            continue
        other = None
        if len(set_) > 1 and not _same_labels(set_[0][1], set_[1][1]):
            other = set_[1][0]
        out.append((o, set_[0][0], set_[0][1], other))
    return out


def job_var_name(job):
    """DL399: the per-job runner variable of a workflow job key: CRSP_ + the key uppercased, every non-alphanumeric as `_`."""
    return "CRSP_" + re.sub(r"[^A-Za-z0-9]", "_", str(job)).upper()


def per_job_overrides(variables):
    """DL399: sorted [(name, value)] of the set CRSP_<JOB> variables (every CRSP_ variable except CRSP_RUNS_ON_*)."""
    out = []
    for n, v in (variables or {}).items():
        if str(n).startswith("CRSP_") and not str(n).startswith("CRSP_RUNS_ON_") and str(v or "").strip():
            out.append((str(n), str(v).strip()))
    return sorted(out)


def runs_on_items(variables, tag):
    """DL394: one item that says which variable each OS resolves to, and a warn when the old and the new variable are both
    set with different values (the new one wins; delete CRSP_RUNS_ON_* or set it to the old labels to go back)."""
    if variables is None:
        return []
    res = resolve_runs_on(variables)
    parts = ["%s -> %s" % (o, "%s (%s)" % (n, v) if n else "GitHub-hosted default") for o, n, v, _ in res]
    detail = "runs-on of %s resolves: %s" % (tag, "; ".join(parts))
    jobs = per_job_overrides(variables)
    if jobs:
        detail += ". Per-job overrides (win over the OS variable): %s. To go back, delete CRSP_<JOB> and CRSP_RUNS_ON_*" % (
            "; ".join("%s (%s)" % nv for nv in jobs))
    items = [_item("workflows.runs_on:" + tag, "ok", detail)]
    clash = ["%s: %s wins over %s" % (o, n, other) for o, n, _, other in res if other]
    if clash:
        items.append(_item("workflows.runs_on_both:" + tag, "warn",
                           "%s sets the old and the new runner variable to different values (%s). The new variable wins. To go "
                           "back to the old one, delete CRSP_RUNS_ON_* or set it to the old labels." % (tag, "; ".join(clash))))
    return items
HOSTED_PREFIXES = ("ubuntu-", "windows-", "macos-")


def workflow_jobs(text):
    """[(line number, [literal labels], expression text or None)] for every `runs-on:` of a workflow file."""
    lines = text.splitlines()
    out = []
    for i, line in enumerate(lines):
        m = re.match(r"^\s*runs-on\s*:\s*(.*?)\s*(#.*)?$", line)
        if not m:
            continue
        val = m.group(1).strip()
        if not val:
            indent = len(line) - len(line.lstrip())
            labels = []
            for nxt in lines[i + 1:]:
                lm = re.match(r"^(\s*)-\s*(.+?)\s*(#.*)?$", nxt)
                if not lm or len(lm.group(1)) < indent:
                    break
                labels.append(lm.group(2).strip("\"'"))
            val = "[" + ", ".join(labels) + "]"
        if "${{" in val:
            out.append((i + 1, [], val))
            continue
        val = val.strip()
        if val.startswith("[") and val.endswith("]"):
            val = val[1:-1]
        out.append((i + 1, [x.strip().strip("\"'") for x in val.split(",") if x.strip().strip("\"'")], None))
    return out


def _config_repos(root, cfg):
    """[(OWNER/NAME or None, folder)]: the config `repos` entries (a string OWNER/NAME, or {repo, path}), else this repository."""
    out = []
    for r in cfg.get("repos") or []:
        if isinstance(r, str):
            out.append((r, None))
        elif isinstance(r, dict) and isinstance(r.get("repo"), str):
            out.append((r["repo"], r.get("path") if isinstance(r.get("path"), str) else None))
    if not out:
        res = H.gh(root, ["repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"])
        name = res[1].strip() if res and res[0] == 0 and res[1].strip() else None
        out.append((name, root))
    return out


def _online_runners(root, repo):
    """[{'labels': set of lower-case names, 'os': str}] of the online runners of the repo, or None when unreadable."""
    res = H.gh(root, ["api", "repos/%s/actions/runners?per_page=100" % repo] if repo else
               ["api", "repos/{owner}/{repo}/actions/runners?per_page=100"])
    if res is None or res[0] != 0:
        return None
    try:
        data = json.loads(res[1] or "{}")
    except ValueError:
        return None
    return [{"labels": {str(l.get("name", "")).lower() for l in r.get("labels") or [] if isinstance(l, dict)},
             "os": str(r.get("os") or "").lower(), "online": r.get("status") == "online"}
            for r in data.get("runners") or [] if isinstance(r, dict)]


def _repo_variables(root, repo):
    res = H.gh(root, ["variable", "list", "--json", "name,value"] + (["-R", repo] if repo else []))
    if res is None or res[0] != 0:
        return None
    try:
        return {v["name"]: str(v.get("value") or "").strip() for v in json.loads(res[1] or "[]") if isinstance(v, dict) and "name" in v}
    except ValueError:
        return None


def workflow_items(root, cfg):
    """DL317 (doctor part) and DL318: for each repository, each literal runs-on label is carried by an online runner of it
    (fail, with file and line), a self-hosted job names fromJSON(vars.CI_RUNS_ON[_WINDOWS]) rather than a literal label (warn),
    and CI_RUNS_ON_WINDOWS is set when the repository has a Windows self-hosted runner (warn). GitHub-hosted labels are skipped."""
    items = []
    for repo, folder in _config_repos(root, cfg):
        tag = repo or "this repository"
        runners = _online_runners(root, repo)
        variables = _repo_variables(root, repo)
        wdir = os.path.join(folder, ".github", "workflows") if folder else None
        jobs = []
        if wdir and os.path.isdir(wdir):
            for n in sorted(os.listdir(wdir)):
                if n.endswith((".yml", ".yaml")):
                    try:
                        with open(os.path.join(wdir, n), encoding="utf-8", errors="replace") as f:
                            jobs += [(n,) + j for j in workflow_jobs(f.read())]
                    except OSError:
                        continue
        if runners is None:
            items.append(_item("workflows.runners:" + tag, "warn", "cannot read the runners of %s (gh not signed in or no rights): "
                                                                   "check the runs-on labels by hand" % tag))
        online = [r for r in runners or [] if r["online"]]
        bad, loose = [], []
        for name, line, labels, expr in jobs:
            low = [l.lower() for l in labels]
            if expr is not None or not low or (len(low) == 1 and low[0].startswith(HOSTED_PREFIXES)):
                continue
            if "self-hosted" in low:
                loose.append("%s:%d (%s)" % (name, line, ", ".join(labels)))
            if runners is not None and not any(set(low) <= r["labels"] for r in online):
                bad.append("%s:%d needs [%s]" % (name, line, ", ".join(labels)))
        if runners is not None:
            items.append(_item("workflows.labels:" + tag, "fail" if bad else "ok",
                               ("no online runner of %s carries the label(s) of: %s" % (tag, "; ".join(bad))) if bad else
                               "every literal runs-on label of %d job(s) in %s is carried by an online runner" % (len(jobs), tag)))
        if loose:
            items.append(_item("workflows.generic:" + tag, "warn", "self-hosted job(s) use a literal label: %s. Use "
                               "${{ fromJSON(vars.CRSP_RUNS_ON_LINUX || vars.CI_RUNS_ON) }} (Linux) or ${{ fromJSON(vars.CRSP_RUNS_ON_WINDOWS || vars.CI_RUNS_ON_WINDOWS) }} (Windows)." % "; ".join(loose)))
        items += runs_on_items(variables, tag)
        has_win = any(r["os"] == "windows" or "windows" in r["labels"] for r in runners or [])
        if has_win and variables is not None and not (variables.get("CRSP_RUNS_ON_WINDOWS") or variables.get("CI_RUNS_ON_WINDOWS")):
            items.append(_item("workflows.windows_var:" + tag, "warn", "%s has a Windows self-hosted runner but CRSP_RUNS_ON_WINDOWS is "
                               "unset: Windows jobs cannot target the pool. Set it, for example `gh variable set CRSP_RUNS_ON_WINDOWS "
                               "--body '[\"self-hosted\", \"windows\"]'`." % tag))
        elif has_win and variables is not None and not variables.get("CRSP_RUNS_ON_WINDOWS") and "pool-" not in str(variables.get("CI_RUNS_ON_WINDOWS") or "").lower():
            # DL341: the old 3 label value still works; it does not route by pool or repository
            items.append(_item("workflows.windows_pool_labels:" + tag, "warn", "CI_RUNS_ON_WINDOWS of %s has no pool labels. It still "
                               "matches, but the pool cannot route the job. Run the pool setup with --windows-repos: it sets "
                               "[\"self-hosted\",\"Windows\",\"pool-<pool>\",\"repo-<route>\"]." % tag))
    return items


# ---- rust (DS202): only for the rust track ----------------------------------------------------------------------

RUST_TOOLS = ("rustup-init", "llvm", "zig", "cargo-deny")
ADVISORY_MAX_DAYS = 7
DISK_WARN_GB = 10


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _gate_tracks(root):
    """The tracks gate.json names (DL245): a string for one track, a list for several. [] when it says none."""
    val = _read_json(os.path.join(root, "scripts", "delivery", "gate.json")).get("track")
    names = val.split(",") if isinstance(val, str) else val if isinstance(val, list) else []
    return [n.strip() for n in names if isinstance(n, str) and n.strip() in ("ts", "go", "rust", "dotnet")]


def _rust_track(root):
    """True when the project is on the rust track: gate.json says so, or rust_ci.py exists."""
    d = os.path.join(root, "scripts", "delivery")
    return "rust" in _gate_tracks(root) or os.path.exists(os.path.join(d, "rust_ci.py"))


def _toolchain(root):
    """(channel, targets) from rust-toolchain.toml, or None when the file is missing. No tomllib: Python 3.10."""
    try:
        with open(os.path.join(root, "rust-toolchain.toml"), encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return None
    m = re.search(r'^\s*channel\s*=\s*["\']([^"\']*)["\']', text, re.M)
    t = re.search(r"^\s*targets\s*=\s*\[(.*?)\]", text, re.M | re.S)
    return (m.group(1) if m else ""), re.findall(r'["\']([^"\']+)["\']', t.group(1) if t else "")


def _tools_dir():
    env = os.environ.get("CI_TOOLS_DIR")
    return env or (os.path.join("C:/ci-tools") if os.name == "nt" else os.path.join(os.path.expanduser("~"), ".cache", "ci-tools"))


def _ci_tool_module():
    """The plugin's own ci_tool.py (the one that fills the cache), so the doctor looks where it puts files (DL188)."""
    import importlib.util
    path = os.path.join(HERE, os.pardir, "templates", "shared", "scripts", "delivery", "ci_tool.py")
    spec = importlib.util.spec_from_file_location("ci_tool_for_doctor", os.path.normpath(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


# tool name on PATH -> (pinned tool in tools.json, exe inside it)
_PINNED = {"zig": ("zig", None), "clang-cl": ("llvm", "clang-cl"), "lld-link": ("llvm", "lld-link")}


def _have(name):
    import shutil
    return bool(shutil.which(name))


def _cached(name, root):
    """True when ci_tool.py's cache holds the tool (DL188)."""
    if name in _PINNED and root:
        pinned, exe = _PINNED[name]
        try:
            ct = _ci_tool_module()
            if ct.cached_tool(pinned, ct.current_platform(), exe, os.path.join(root, "scripts", "delivery", "tools.json")):
                return True
        except Exception:  # noqa: BLE001 - an unreadable cache is "not found"
            pass
    return False


def _cc_fix():
    if os.name == "nt":
        return "python scripts/delivery/ci_tool.py tool zig"
    return "sudo apt-get install -y build-essential   (or: python3 scripts/delivery/ci_tool.py tool zig)"


def _advisory_age_days():
    """Age in days of the newest advisory DB cache folder in the tool cache, or None when there is none."""
    import glob
    paths = glob.glob(os.path.join(glob.escape(_tools_dir()), "advisory-db*")) + \
        glob.glob(os.path.join(glob.escape(_tools_dir()), "*", "advisory-db*"))
    if not paths:
        return None
    import time
    return (time.time() - max(os.path.getmtime(p) for p in paths)) / 86400


SHA_RE = re.compile(r"[0-9a-fA-F]{64}")


def _needed_platforms(targets):
    """The tools.json platforms this project uses: this host, plus Windows and Linux when the targets name them."""
    need = {_ci_tool_module().current_platform()}
    if any("windows" in t for t in targets):
        need.add("windows_x64")
    if any("linux" in t for t in targets):
        need.add("linux_x64")
    return sorted(need)


def _pin_problem(entry, need):
    """"" when the tool is pinned, else text for the finding. Flat sha256 (string or map) or `platforms` (DL188)."""
    if not isinstance(entry, dict):
        return " (no entry)"
    ok = lambda h: isinstance(h, str) and bool(SHA_RE.fullmatch(h))  # noqa: E731
    sha = entry.get("sha256")
    if isinstance(sha, str) and ok(sha):
        return ""
    if isinstance(sha, dict) and sha and all(ok(h) for h in sha.values()):
        return ""
    plats = entry.get("platforms")
    if isinstance(plats, dict):
        missing = [p for p in need if not (isinstance(plats.get(p), dict) and ok(plats[p].get("sha256")))]
        return (" (platform %s)" % ", ".join(missing)) if missing else ""
    return " (no sha256)"


def rust_items(root):
    items = []
    tc = _toolchain(root)
    if tc is None:
        items.append(_item("rust.toolchain", "fail", "rust-toolchain.toml is missing. Add it with an exact version, "
                                                     "for example: [toolchain] channel = \"1.90.0\""))
        targets = []
    else:
        channel, targets = tc
        if re.fullmatch(r"\d+\.\d+\.\d+", channel):
            items.append(_item("rust.toolchain", "ok", "rust-toolchain.toml pins %s" % channel))
        else:
            items.append(_item("rust.toolchain", "fail", "rust-toolchain.toml channel is %s, not an exact version. "
                                                         "Set channel = \"1.90.0\" (the version you build with)"
                               % (repr(channel) if channel else "missing")))
    if _have("cc") or _have("zig") or _cached("zig", root):
        items.append(_item("rust.linker", "ok", "host linker found"))
    else:
        items.append(_item("rust.linker", "fail", "linker cc not found. Fix: " + _cc_fix()))
    if any("windows" in t for t in targets):
        missing = [n for n in ("clang-cl", "lld-link") if not (_cached(n, root) or _have(n))]
        if missing:
            items.append(_item("rust.windows", "fail", "%s not found for the Windows target. Fix: "
                               "python scripts/delivery/ci_tool.py tool llvm" % " and ".join(missing)))
        else:
            items.append(_item("rust.windows", "ok", "clang-cl and lld-link found"))
    pins = _read_json(os.path.join(root, "scripts", "delivery", "tools.json"))
    need = _needed_platforms(targets)
    bad = []
    for name in RUST_TOOLS:
        problem = _pin_problem(pins.get(name), need)
        if problem:
            bad.append("%s%s" % (name, problem))
    if bad:
        items.append(_item("rust.pins", "fail", "tools.json has no sha256 pin for: %s. Fix: add each tool with "
                           "`python scripts/delivery/tools_pin.py` and commit scripts/delivery/tools.json" % ", ".join(bad)))
    else:
        items.append(_item("rust.pins", "ok", "tools.json pins %s" % ", ".join(RUST_TOOLS)))
    age = _advisory_age_days()
    if age is None:
        items.append(_item("rust.advisory", "warn", "no advisory database cache yet. It is fetched on the first "
                                                    "CI run: python scripts/delivery/rust_ci.py deny"))
    elif age > ADVISORY_MAX_DAYS:
        items.append(_item("rust.advisory", "warn", "advisory database cache is %d days old (limit %d). Refresh: "
                           "python scripts/delivery/rust_ci.py deny" % (age, ADVISORY_MAX_DAYS)))
    else:
        items.append(_item("rust.advisory", "ok", "advisory database cache is %d days old" % age))
    try:
        import shutil
        free = shutil.disk_usage(root).free / 1e9
        if free < DISK_WARN_GB:
            items.append(_item("rust.disk", "warn", "%.1f GB free; target/ and the cache need about %d GB. Fix: "
                               "cargo clean, or empty the runner _work folder" % (free, DISK_WARN_GB)))
        else:
            items.append(_item("rust.disk", "ok", "%.0f GB free" % free))
    except OSError:
        pass
    return items


def check_rust(root, cfg):
    """None (no row) unless the project is on the rust track. Warnings never fail the check."""
    if not _rust_track(root):
        return None
    items = rust_items(root)
    ok = not any(i["status"] == "fail" for i in items)
    bad = ["%s %s: %s" % (i["status"], i["id"], i["detail"]) for i in items if i["status"] != "ok"]
    return ok, "; ".join(bad) or "; ".join(i["detail"] for i in items), items


def _vtuple(text):
    parts = re.findall(r"\d+", str(text))[:3]
    return tuple(int(p) for p in parts) + (0,) * (3 - len(parts))


def installed_versions(cache=None):
    """{plugin name: highest installed version string} from <cache>/<marketplace>/<plugin>/<version>/."""
    cache = cache or os.environ.get("DELIVERY_PLUGIN_CACHE") or os.path.join(os.path.expanduser("~"), ".claude", "plugins", "cache")
    out = {}
    try:
        markets = [os.path.join(cache, m) for m in os.listdir(cache)]
    except OSError:
        return out
    for market in markets:
        try:
            plugins = os.listdir(market)
        except OSError:
            continue
        for plugin in plugins:
            try:
                versions = [v for v in os.listdir(os.path.join(market, plugin)) if re.match(r"\d+(\.\d+)*", v)]
            except OSError:
                continue
            for v in versions:
                if plugin not in out or _vtuple(v) > _vtuple(out[plugin]):
                    out[plugin] = v
    return out


def compat_items(installed=None, compat_path=None):
    """One warn item per installed plugin pair that does not meet plugin-compat.json."""
    compat = _read_json(compat_path or os.path.join(PLUGIN, "references", "plugin-compat.json")) or {}
    installed = installed_versions() if installed is None else installed
    items = []
    for plugin, needs in (compat.get("requires") or {}).items():
        if plugin not in installed:
            continue
        for other, rule in needs.items():
            if other not in installed:
                continue
            want = str(rule.get("version", "")).lstrip(">= ")
            if _vtuple(installed[other]) < _vtuple(want):
                items.append(_item("%s>%s" % (plugin, other), "warn",
                                   "%s %s needs %s >=%s, installed %s (%s). Run: claude plugin update %s@dev-standards"
                                   % (plugin, installed[plugin], other, want, installed[other], rule.get("why", ""), other)))
    return items


def scripts_items(root):
    """`ci.scripts-current`: the project's scripts/delivery files against the plugin's templates (DL188). Never fails."""
    import delivery_ci_install as INST
    tracks = _gate_tracks(root)
    if not tracks:
        tracks = ["rust"] if os.path.exists(os.path.join(root, "scripts", "delivery", "rust_ci.py")) else []
    track = ",".join(tracks) if tracks else "shared"
    keep, skip = INST.load_config(root)
    omit = set()
    if any(t in INST.PACKAGE_TRACKS for t in tracks) and not INST.has_packaged_program(root):
        # DL236: the installer skips these too (DL229), so they are not missing. DL245: with another track that
        # ships them, only the ts copy is left out and the other track's copy is checked.
        if len(tracks) > 1:
            omit = {(t, f) for t in tracks if t in INST.PACKAGE_TRACKS for f in INST.PACKAGE_FILES}
        if not any(os.path.isfile(os.path.join(INST.TEMPLATES, t, f.replace("/", os.sep)))
                   for t in tracks if t not in INST.PACKAGE_TRACKS for f in INST.PACKAGE_FILES):
            skip = set(skip) | set(INST.PACKAGE_FILES)
    stale, missing, kept, changed = [], [], [], []
    plan_items = INST.plan(tracks or ["shared"], root, "update", keep, skip, omit)
    for rel, _src, action in plan_items:
        if not rel.startswith("scripts/delivery/"):
            continue
        if action == "overwritten":
            stale.append(rel)
        elif action == "written":
            missing.append(rel)
        elif action == INST.KEPT:
            kept.append(rel)
        elif action == INST.CHANGED:
            changed.append(rel)
    for rel, _src, _a in plan_items:
        if _a == "same":
            continue   # DL212: identical to the template is ok, whatever the record or a stale .new says
        if rel.startswith("scripts/delivery/") and rel not in changed and os.path.exists(os.path.join(root, rel.replace("/", os.sep) + ".new")):
            changed.append(rel)   # DL201: a conflict or a kept file waits for a hand merge
    if not stale and not missing and not changed:
        return [_item("ci.scripts-current", "ok", "scripts/delivery matches the plugin templates%s%s"
                      % (" for tracks %s" % ", ".join(tracks) if len(tracks) > 1 else "",
                         " (kept on purpose: %s)" % ", ".join(kept) if kept else ""))]
    parts = []
    if stale:
        parts.append("older than the plugin templates: %s" % ", ".join(stale))
    if changed:
        parts.append("changed by the project, or a pending <file>.new (an update merges them; resolve a conflict in <file>.new, copy it over the file, rerun update): %s"
                     % ", ".join(changed))
    if missing:
        parts.append("missing: %s" % ", ".join(missing))
    return [_item("ci.scripts-current", "warn", "%s. Refresh: python3 <plugin>/scripts/delivery_ci_install.py update "
                  "--track %s (add --dry-run first). To keep a file you edited on purpose, list it under \"keep\" in "
                  "scripts/delivery/ci-install.json" % ("; ".join(parts), track if track != "shared" else "ts|go|rust|dotnet"))]


def check_scripts(root, cfg):
    """None when the project has no scripts/delivery. A warning never fails the check."""
    if not os.path.isdir(os.path.join(root, "scripts", "delivery")):
        return None
    items = scripts_items(root)
    bad = ["%s %s: %s" % (i["status"], i["id"], i["detail"]) for i in items if i["status"] != "ok"]
    return True, "; ".join(bad) or items[0]["detail"], items


STOP_FLAG_RE = re.compile(r"(?<![\w-])(--fail-fast|--exitfirst|--bail|-x)(?![\w-])|maxFailures")


def fail_fast_findings(text, name, cfg):
    """DL-98 (D104): lines of one workflow that stop a release PR run at its first failing suite."""
    if not re.search(r"^\s*pull_request\s*:|^\s*on\s*:.*\bpull_request\b", text, re.M):
        return []
    ci = cfg.get("ci") if isinstance(cfg.get("ci"), dict) else {}
    jobs_cfg = ci.get("jobs") if isinstance(ci.get("jobs"), dict) else {}

    def on(job):
        j = jobs_cfg.get(job)
        return isinstance(j, dict) and j.get("fail_fast") == "on"

    lines = text.splitlines()
    out, job = [], None
    in_jobs = False
    for i, line in enumerate(lines):
        if re.match(r"^jobs\s*:", line):
            in_jobs = True
            continue
        m = re.match(r"^  ([A-Za-z0-9_-]+)\s*:\s*$", line)
        if in_jobs and m:
            job = m.group(1)
        if on(job):
            continue
        m = re.match(r"^(\s*)strategy\s*:", line)
        if m:
            indent = len(m.group(1))
            block = []
            for nxt in lines[i + 1:]:
                if nxt.strip() and len(nxt) - len(nxt.lstrip()) <= indent:
                    break
                block.append(nxt)
            body = "\n".join(block)
            if re.search(r"^\s*matrix\s*:", body, re.M) and not re.search(r"^\s*fail-fast\s*:\s*false\b", body, re.M):
                out.append("%s job %s: matrix without fail-fast: false" % (name, job or "?"))
        code = line.split("#", 1)[0]
        if re.match(r"^\s*(-\s*)?(run|args)\s*:|^\s+\S", code) and STOP_FLAG_RE.search(code) and "echo" not in code:
            out.append("%s job %s line %d: stop-at-first-failure flag %s" % (
                name, job or "?", i + 1, STOP_FLAG_RE.search(code).group(0)))
    return out


def check_fail_fast(root, cfg):
    """DL-98 (D104): WARN, never fail, when a pull-request workflow can stop at the first failing suite."""
    wf = os.path.join(root, ".github", "workflows")
    if not os.path.isdir(wf):
        return None
    found = []
    for n in sorted(os.listdir(wf)):
        if not n.endswith((".yml", ".yaml")):
            continue
        try:
            with open(os.path.join(wf, n), encoding="utf-8") as f:
                found += fail_fast_findings(f.read(), n, cfg)
        except OSError:
            continue
    if not found:
        return None
    return True, "WARN DL-98 a release PR run must run every suite to the end (D104): " + "; ".join(found) + \
        ". Set `fail-fast: false`, drop the flag, or set ci.jobs.<id>.fail_fast to \"on\".", \
        [_item("ci.fail_fast", "warn", "; ".join(found))]


def check_ci_filters(root, cfg):
    """DL-116 (DS261): WARN, never fail, when a workflow the watcher requires has a pull-request path filter."""
    import importlib.util
    src = os.path.join(PLUGIN, "templates", "shared", "scripts", "delivery", "ci_areas_check.py")
    try:
        spec = importlib.util.spec_from_file_location("ci_areas_check", src)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        names = [str(n) for n in C.ci_workflows(cfg)]
        found = [f for f in mod.check(__import__("pathlib").Path(root), names) if "not found" not in f] if names else []
    except Exception:
        return None
    if not found:
        return None
    return True, "WARN DL-116 a required workflow has a pull-request path filter, so a filtered change leaves the watcher "         "without a run: " + "; ".join(found) + ". Skip by job-level `if` plus an always-run aggregate job "         "(templates/ci-snippets/ci-areas-pattern.yml).", [_item("ci.path_filter", "warn", "; ".join(found))]


def check_plugins(root, cfg):
    items = compat_items()
    if not items:
        return None      # nothing to say: no row (also when no plugin is installed)
    return True, "WARN plugins.compat: " + "; ".join(i["detail"] for i in items), items


E2E_SPEC_DEFAULT = ["e2e/*.spec.*", "*/e2e/*.spec.*"]


def e2e_gate_problem(root):
    """DL397: a hint when e2e spec files exist but gate.json has no ui-changed (e2e) step, else None."""
    import fnmatch
    gate = _read_json(os.path.join(root, "scripts", "delivery", "gate.json"))
    steps = gate.get("steps")
    if not isinstance(steps, list):
        return None
    if any(isinstance(s, dict) and s.get("scope") == "ui-changed" for s in steps):
        return None
    pats = gate.get("e2e_spec_paths")
    pats = pats if isinstance(pats, list) and pats else E2E_SPEC_DEFAULT
    try:
        out = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True, timeout=30)
        files = out.stdout.splitlines() if out.returncode == 0 else []
    except (OSError, subprocess.SubprocessError):
        return None
    hit = [f for f in files if any(fnmatch.fnmatchcase(f, str(p)) for p in pats)]
    if not hit:
        return None
    return ("no e2e step in gate.json: %d e2e spec file(s) match e2e_spec_paths (%s) but no step has scope "
            "\"ui-changed\". Add an e2e step with \"scope\": \"ui-changed\" (the kit's ts template has one), or "
            "branch_gate.py --e2e-only and the pre-push e2e check cannot pass." % (len(hit), hit[0]))


def check_gate_steps(root, cfg):
    problem = e2e_gate_problem(root)
    if problem is None:
        return None
    return False, problem, [_item("gate.e2e_step", "fail", problem)]


def _stack_module():
    """stack.py of the shipped templates (DL406)."""
    import importlib.util
    path = os.path.join(PLUGIN, "templates", "shared", "scripts", "delivery", "stack.py")
    if not os.path.exists(path):
        return None
    spec = importlib.util.spec_from_file_location("delivery_stack", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def check_stack(root, cfg):
    """DL406 (R5.66): `stack.tools`. A tool found in the files that is neither known nor declared FAILS at once,
    whatever enforcement.mode says."""
    st = _stack_module()
    if st is None:
        return False, "stack.py is missing from the plugin templates", [_item("stack.tools", "fail", "stack.py is missing")]
    items, bad = [], []
    for msg in st.problems(cfg):
        bad.append(msg)
        items.append(_item("stack.tools", "fail", msg))
    for tool, r in sorted(st.resolve(root, cfg).items()):
        where = " (%s)" % r["evidence"] if r["evidence"] else ""
        if r["status"] == "known":
            items.append(_item("stack.tools", "ok", "%s%s: known" % (tool, where)))
        elif r["status"] == "declared":
            note = "declared" if r["judged"] else "declared; delivery runs its commands but cannot judge them"
            items.append(_item("stack.tools", "ok", "%s%s: %s" % (tool, where, note)))
        else:
            msg = ("%s found (%s) but delivery cannot check it: declare it under stack in .delivery/config.json, "
                   "or remove it" % (tool, r["evidence"]))
            bad.append(msg)
            items.append(_item("stack.tools", "fail", msg))
    if bad:
        return False, "; ".join(bad[:3]), items
    return True, "%d tool(s), none unchecked" % len(items), items


CHECKS = (("config", check_config), ("gh", check_gh), ("tz", check_tz), ("hooks", check_hooks), ("ledger", check_ledger),
          ("ci", check_ci), ("rust", check_rust),
          ("scripts", check_scripts), ("fail-fast", check_fail_fast), ("ci-filters", check_ci_filters), ("plugins", check_plugins),
          ("gate-steps", check_gate_steps), ("stack", check_stack))


def run_checks(root):
    cfg = H.load_config(root)
    out = []
    for name, fn in CHECKS:
        items = None
        try:
            res = fn(root, cfg)
            if res is None:
                continue
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
