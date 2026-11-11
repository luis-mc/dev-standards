#!/usr/bin/env python3
"""Write the CI and delivery files into a project, or update them (DL15).

    delivery_ci_install.py install --track ts|go|rust|dotnet[,...] [--root DIR] [--dry-run]
    delivery_ci_install.py update  [--track ts|go|rust|dotnet[,...]] [--root DIR] [--dry-run]

Several tracks (DL245). `--track rust,ts` installs the shared files once and each track's files. Files two tracks ship
at one path are merged: `ci.yml` (one workflow; the ts jobs keep their ids, the other tracks' jobs end in `-<track>`;
a `tracks` job switches each track on or off from the changed files; the aggregate job waits for every track),
`gate.json` (every track's steps, tagged with `"track"`, a name both use becomes `<name>-<track>`) and `ci-scope.json`
(`tracks` and `shared` path lists). For any other shared path the first track's copy is installed and a `note:` line
names the file and the skipped track. State, `gate.json` and config keep a string for one track and a list for several.
A single track is installed exactly as before.

The sources are `templates/shared/` and `templates/<track>/` next to this plugin. They land at the same
relative path in the project (`scripts/delivery/`, `.github/workflows/`). tech-stack-setup calls `install` at
the end of its setup; it copies none of these files itself.

install  writes every file that is not there yet. A file that exists and differs is kept and listed as
         "kept"; nothing is overwritten.
update   overwrites the files the plugin owns (scripts, CONTRACT.md, tools.json, shared workflows) and keeps
         the files the project edits (the *.json maps, gate.json, smoke.json, quarantine, ci.yml, package.yml,
         nightly-full.yml). A kept file that differs is listed as "differs".

It never commits or pushes, and it does not choose the CI option: ask the owner, then run
`delivery_ci.py set`. The GitHub workflow files are always written; a project that runs an OS only in cloud
sessions (option c) deletes the jobs it does not use. `CONTRACT.md` is not installed: it stays with the plugin.

Windows deferred (DL192). On the rust track, `windows-msi-check.yml` and `package-windows.yml` are installed only when
`ci.options.windows` in `.delivery/config.json` holds a CI option. When it is absent (or `deferred`) they are skipped,
and `package.yml` runs its Windows steps only when the repository variable `CI_WINDOWS` is `on`. Choose Windows and run
`install` again to get the files.

After the run (also with --dry-run) it checks the imports (DL112). For every .py it manages under
`scripts/delivery/` it reads the `import x` and `from x import y` lines (top level and inside functions) with
`ast`. A sibling module that is not in the project is listed under "missing imports:". In a git repo, managed
files that exist but are not tracked are listed under "not in git yet (commit them):" (DL227: files that .gitignore
ignores are left out and named on one line, `ignored by .gitignore: ...`). With --dry-run the
check looks at the project as it is now plus what the run would write.

Keep and skip lists (DL120). A project may own `scripts/delivery/ci-install.json`. Install and update never
write or overwrite it. It has two lists of paths relative to the project root:

    {"keep": ["scripts/delivery/ci_watch.py"], "skip": [".github/workflows/package-windows.yml"]}

keep  `update` never overwrites these. When the template differs, the file is listed as
      "kept (ci-install.json)", and at the end one line per file says:
      "kept <path>: the plugin's version differs; diff it with <template path> and fold your change into the
      plugin or drop it". A kept file that is missing is still written.
skip  `install` and `update` never write these, even when missing. They are listed as "skipped (ci-install.json)".
Keep and report (DL201). The installer records a sha256 of every file it writes in `.delivery/ci-install-state.json`.
`update` overwrites a plugin-owned file only when it still matches that record. When the project changed it, the
file is kept, the new template goes next to it as `<file>.new`, and the run prints "kept (project changes)" with a
`git diff --no-index` command. With no record, a file that differs from the template counts as changed.
Merge by hand, then delete the .new file. A later update replaces an old .new. The plugin never commits it.

3-way merge (DL201, step 2). The installer also keeps a copy of each template as written in
`.delivery/ci-install-base/<same path>`. On `update`, a file the project changed and that has a stored base is merged:
a line-based diff3 (difflib) applies the template's changes since the base to the project file. A clean merge
writes the file (action "merged") and refreshes the base and the hash. A conflict leaves the project file as it is,
writes `<file>.new` with `<<<<<<< project` / `||||||| base` / `=======` / `>>>>>>> template` markers (action
"conflict") and prints "resolve <file>.new, then copy it over <file> and rerun update". A file with no stored base is
kept with a plain `.new`, and the new template becomes its base. Line endings: the merge runs on LF; the file keeps
the project's ending. Commit `.delivery/ci-install-base/` so every clone can merge. The run ends with
"summary: N written, N overwritten, N merged, N conflict, N kept, N same, N skipped" and exits 0 with conflicts.

A path in either list that the plugin does not manage prints a "warning:" line; it is not an error. A file that
is not valid JSON (or whose lists are not lists of strings) prints one line naming the file and exits 2. With
no ci-install.json the run is as before. The import check treats a skipped or kept file like any file on disk.
The plugin ships `ci-install.example.json` (empty lists and a `_comment`); it is copied like any template and
is never read as the real file.

Prune list sync (DL150). After `update` rewrites `.github/workflows/artifact-prune.yml` from the template, it runs
`scripts/delivery/artifact_prune.py --sync-workflow` in the project, so the project's `artifact_prune.workflows`
list is applied and does not revert. A failed sync prints the error and the fix; the update stays.

Prettier (DL218). When the project uses Prettier (a `.prettierrc*` or `prettier.config.*` file, a `prettier` key in
package.json, or prettier in its dependencies), the installer keeps a marked block in `.prettierignore`. The block
lists `.delivery/ci-install-base/` and every `*.example.json` it manages. Other lines are never touched, the file's
line endings stay, a rerun changes nothing, and `--dry-run` only lists the change. Without Prettier nothing is written.

Time zone data (DL157). Windows Python has no time zone data. After the run the installer loads the `tz` of
`.delivery/config.json` through `zoneinfo`. When that fails it runs `python -m pip install --user tzdata` (it asks
first when the terminal is interactive), says what it did, and checks again. The doctor keeps its own check.

Moved from project-setup (DL172). The installer also writes, at the same project paths as before:
`.githooks/pre-push` and `.githooks/commit-msg` (they call the delivery scripts and read `.delivery/config.json`),
and `.delivery/config.json` (project-owned: written when absent, never overwritten, also by `update`). On
`install`, a `.githooks/pre-push` that differs and is not this plugin's hook is moved to `pre-push.local` first
(the hook runs it after its guards); an existing `pre-push.local` is never replaced. It also merges the
`session_guard.py` PreToolUse entry into the project's `.claude/settings.json`: other entries stay, an entry that
is already there is not added twice, and a settings file that is not valid JSON is left alone with a warning.
`--only config,settings` (no --track needed) does just those two steps and leaves the template files alone.

Secret scan config (DL186). The CI secret-scan step runs `gitleaks git --config .gitleaks.toml`, so the installer
writes `.gitleaks.toml` (from `templates/shared/.gitleaks.toml`, the only copy; tech-stack-setup carries none) when the
project has none. The project owns it after that: `install` keeps a different one and `update` lists it as "differs".

Exit 0 done, 1 a bad track, 2 a missing template folder or a bad ci-install.json, 3 a managed script imports a sibling module that is
not in the project (the files were still written). Untracked files do not change the exit code.
Standard library only.
"""
from __future__ import annotations

import argparse
import difflib
import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
TEMPLATES = os.path.join(PLUGIN, "templates")
TRACKS = ("ts", "go", "rust", "dotnet")

# Project-edited: `update` never overwrites these (the project owns them after the first install).
PROJECT_OWNED_NAMES = {"gate.json", "smoke.json", "ci-areas.json", "ci-timings.json", "ci-scope.json",
                       "quarantine.json", "ci-shards.json", "ci-shards.example.json", "ci.yml", "package.yml", "nightly-full.yml",
                       "ci-install.json", ".gitleaks.toml"}
# Project-owned by relative path (the name `config.json` is too common to own by name).
PROJECT_OWNED_PATHS = {".delivery/config.json"}
HOOKS_DIR = ".githooks"
PRE_PUSH = ".githooks/pre-push"
SETTINGS = ".claude/settings.json"
GUARD_MARK = "scripts/delivery/session_guard.py"
GUARD_COMMAND = ("[ -f \"$CLAUDE_PROJECT_DIR/scripts/delivery/session_guard.py\" ] || exit 0; "
                 "if command -v python3 >/dev/null 2>&1; then python3 \"$CLAUDE_PROJECT_DIR/scripts/delivery/session_guard.py\"; "
                 "else python \"$CLAUDE_PROJECT_DIR/scripts/delivery/session_guard.py\"; fi")
SKIP_DIRS = {"__pycache__"}
SKIP_FILES = {"CONTRACT.md"}
SKIP_SUFFIXES = (".pyc", ".pyo")   # DL227: never copy compiled Python into a project


def files_of(base: str) -> list:
    out = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(f for f in filenames if f not in SKIP_FILES and not f.endswith(SKIP_SUFFIXES)):
            full = os.path.join(dirpath, name)
            out.append(os.path.relpath(full, base).replace(os.sep, "/"))
    return out


def same(a: str, b: str) -> bool:
    with open(a, "rb") as fa, open(b, "rb") as fb:
        return fa.read().replace(b"\r\n", b"\n") == fb.read().replace(b"\r\n", b"\n")


CONFIG = "scripts/delivery/ci-install.json"
SKIPPED = "skipped (ci-install.json)"
KEPT = "kept (ci-install.json)"
CHANGED = "kept (project changes)"
STATE = ".delivery/ci-install-state.json"
BASE_DIR = ".delivery/ci-install-base"
MERGED = "merged"
CONFLICT = "conflict"
MERGES = {}   # rel -> (text with LF, number of conflicts); set by merge_changed, used by apply


def digest(path: str) -> str:
    """sha256 of a file with CRLF read as LF, so the hash is the same on Windows and Linux."""
    with open(path, "rb") as f:
        return hashlib.sha256(f.read().replace(b"\r\n", b"\n")).hexdigest()


def load_state(root: str):
    """(path -> sha256 of what the installer last wrote, state file exists). A bad file counts as absent."""
    path = os.path.join(root, STATE.replace("/", os.sep))
    try:
        with open(path, "rb") as f:
            files = json.loads(f.read().decode("utf-8-sig")).get("files", {})
    except (OSError, ValueError, AttributeError):
        return {}, False
    if not isinstance(files, dict):
        return {}, False
    return {k: v for k, v in files.items() if isinstance(v, str)}, True


def plugin_version() -> str:
    try:
        with open(os.path.join(PLUGIN, ".claude-plugin", "plugin.json"), "rb") as f:
            return str(json.loads(f.read().decode("utf-8-sig")).get("version", ""))
    except (OSError, ValueError):
        return ""


def _json_of(path: str):
    try:
        with open(path, "rb") as f:
            data = json.loads(f.read().decode("utf-8-sig"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def known_track(root: str):
    """The track, or the tracks as "a,b" when the project uses several (DL245). None when nothing says."""
    found = known_tracks(root)
    return ",".join(found) if found else None


def _valid(val) -> list:
    names = parse_tracks(val) if isinstance(val, (str, list)) else []
    return names if names and all(n in TRACKS for n in names) else []


def known_tracks(root: str) -> list:
    """The track the project already uses (DL213): .delivery/config.json, then the install record, then the
    gate.json the installer wrote, then the project's own files. None when nothing says."""
    cfg = _json_of(os.path.join(root, ".delivery", "config.json"))
    for val in (cfg.get("track"), cfg.get("stack"), (cfg.get("ci") or {}).get("track") if isinstance(cfg.get("ci"), dict) else None,
                _json_of(os.path.join(root, STATE.replace("/", os.sep))).get("track"),
                _json_of(os.path.join(root, "scripts", "delivery", "gate.json")).get("track")):
        if _valid(val):
            return _valid(val)
    found = [t for name, t in (("package.json", "ts"), ("go.mod", "go"), ("Cargo.toml", "rust"))
             if os.path.exists(os.path.join(root, name))]   # files alone name one track: the first, as before
    try:
        if any(n.endswith((".sln", ".csproj")) for n in os.listdir(root)):
            found.append("dotnet")
    except OSError:
        pass
    return found[:1]


def save_state(items: list, root: str, old: dict, track="") -> None:
    """Record the hash of every file the run wrote or found equal to the template, and the track (DL201, DL213)."""
    files = dict(old)
    for rel, src, action in items:
        if action in ("written", "overwritten", "same", MERGED) and rel not in PROJECT_OWNED_PATHS:
            files[rel] = digest(src)
            if rel == PRUNE_WORKFLOW and action not in ("same", MERGED):
                files[rel] = digest(os.path.join(root, rel.replace("/", os.sep)))   # the sync edits it on purpose
    path = os.path.join(root, STATE.replace("/", os.sep))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps({"plugin_version": plugin_version(), "track": track, "files": dict(sorted(files.items()))}, indent=2) + "\n")


def base_path(root: str, rel: str) -> str:
    return os.path.join(root, BASE_DIR.replace("/", os.sep), rel.replace("/", os.sep))


def _text(path: str):
    """File text with CRLF read as LF, plus whether the file used CRLF. None when it is not UTF-8."""
    with open(path, "rb") as f:
        raw = f.read()
    try:
        return raw.decode("utf-8").replace("\r\n", "\n"), b"\r\n" in raw
    except UnicodeDecodeError:
        return None, False


def merge3(base: str, project: str, template: str):
    """Line-based 3-way merge (DL201). Returns (merged text, number of conflicts).

    Each side's changed hunks against `base` are found with difflib. Hunks that touch or overlap form one group.
    A group changed by one side takes that side's lines. A group both sides changed to the same text is taken once.
    Any other group is a conflict, written with <<<<<<< project / ||||||| base / ======= / >>>>>>> template."""
    b, p, t = base.splitlines(True), project.splitlines(True), template.splitlines(True)

    def hunks(other):
        sm = difflib.SequenceMatcher(None, b, other, autojunk=False)
        return [(i1, i2, other[j1:j2]) for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag != "equal"]

    events = sorted([(s_, e_, n, "t") for s_, e_, n in hunks(t)] + [(s_, e_, n, "p") for s_, e_, n in hunks(p)],
                    key=lambda ev: (ev[0], ev[1]))
    groups = []
    for ev in events:
        if groups and ev[0] <= groups[-1]["hi"]:
            groups[-1]["hi"] = max(groups[-1]["hi"], ev[1])
            groups[-1]["ev"].append(ev)
        else:
            groups.append({"lo": ev[0], "hi": ev[1], "ev": [ev]})

    def side(group, who):
        pos, out = group["lo"], []
        for s_, e_, new, w in group["ev"]:
            if w == who:
                out += b[pos:s_] + new
                pos = e_
        return out + b[pos:group["hi"]]

    out, pos, conflicts = [], 0, 0
    for g in groups:
        out += b[pos:g["lo"]]
        pos = g["hi"]
        sides = {w for *_x, w in g["ev"]}
        if sides == {"t"}:
            out += side(g, "t")
        elif sides == {"p"}:
            out += side(g, "p")
        elif side(g, "p") == side(g, "t"):
            out += side(g, "p")
        else:
            conflicts += 1

            def block(lines):
                return lines if not lines or lines[-1].endswith("\n") else lines[:-1] + [lines[-1] + "\n"]
            out += (["<<<<<<< project\n"] + block(side(g, "p")) + ["||||||| base\n"] + block(b[g["lo"]:g["hi"]])
                    + ["=======\n"] + block(side(g, "t")) + [">>>>>>> template\n"])
    out += b[pos:]
    return "".join(out), conflicts


PRUNE_LINE_RE = re.compile(r"^(?P<indent>[ \t]*)workflows:[ \t]*\[(?P<body>[^\]\r\n]*)\][ \t]*(?:#[^\r\n]*)?(?=\r?$)", re.MULTILINE)
PRUNE_PLAN = {}


def prune_names(text):
    """DL255: the names of the one-line `workflows: [...]` list in `text`, or None."""
    m = PRUNE_LINE_RE.search(text or "")
    if not m:
        return None
    try:
        names = json.loads("[" + m.group("body") + "]")
    except ValueError:
        return None
    return names if all(isinstance(n, str) for n in names) else None


def prune_set(text, names):
    """DL255: `text` with its list line set to `names` (text unchanged without such a line)."""
    line = json.dumps(names)
    return PRUNE_LINE_RE.sub(lambda m: "%sworkflows: %s" % (m.group("indent"), line), text, count=1)


def prune_rule(proj, base, tpl):
    """DL255: the project's list wins; names the template added since the base are appended once; names the
    project removed stay removed. Returns (names, added) or None when the project file has no list."""
    p = prune_names(proj)
    if p is None:
        return None
    b, t = prune_names(base), prune_names(tpl) or []
    added = [n for n in t if b is not None and n not in b and n not in p]
    return p + added, added


def plan_prune_list(items: list, root: str) -> None:
    """DL255: before `update` writes anything, work out the list the prune workflow must end with."""
    PRUNE_PLAN.clear()
    for rel, src, action in items:
        if rel != PRUNE_WORKFLOW or action not in ("overwritten", CHANGED):
            continue
        dst = os.path.join(root, rel.replace("/", os.sep))
        bp = base_path(root, rel)
        proj, _c = _text(dst)
        tpl, _c = _text(src)
        base = _text(bp)[0] if os.path.exists(bp) else None
        if proj is None or tpl is None:
            continue
        res = prune_rule(proj, base, tpl)
        if res:
            PRUNE_PLAN[rel] = (res[0], res[1], prune_names(proj))


def report_prune_list() -> None:
    plan = PRUNE_PLAN.get(PRUNE_WORKFLOW)
    if plan:
        names, added, old = plan
        print("artifact-prune list: kept %d project name(s)%s" % (
            len(old or []), ", added from template: " + ", ".join(added) if added else ", nothing added"))


def merge_changed(items: list, root: str) -> list:
    """Turn each CHANGED item that has a stored base into merged or conflict (DL201). Does not write the project file."""
    MERGES.clear()
    out = []
    for rel, src, action in items:
        bp = base_path(root, rel)
        if action == CHANGED and os.path.exists(bp):
            dst = os.path.join(root, rel.replace("/", os.sep))
            base, _a = _text(bp)
            proj, crlf = _text(dst)
            tpl, _c = _text(src)
            if None not in (base, proj, tpl):
                plan = PRUNE_PLAN.get(rel)
                if plan:
                    # DL255: merge everything but the list line, then set the list by the project's rule.
                    p_line = PRUNE_LINE_RE.search(proj).group(0)
                    flat = lambda x: PRUNE_LINE_RE.sub(lambda m: p_line, x, count=1)
                    text, n = merge3(flat(base), proj, flat(tpl))
                    text = prune_set(text, plan[0])
                else:
                    text, n = merge3(base, proj, tpl)
                if not n and text == proj and proj != tpl:
                    # DL236: nothing of the template reached the file (the base is the template, as after a
                    # base-less step-1 run). It is not a merge: keep it, write the template as <file>.new.
                    out.append((rel, src, action))
                    continue
                MERGES[rel] = (text, n, crlf)
                action = CONFLICT if n else MERGED
        out.append((rel, src, action))
    return out


def record_bases(items: list, root: str) -> None:
    """Keep a copy of each template as written, so the next update has the merge base (DL201)."""
    for rel, src, action in items:
        if rel in PROJECT_OWNED_PATHS or action not in ("written", "overwritten", "same", MERGED, CHANGED):
            continue
        if action == CHANGED and os.path.exists(base_path(root, rel)):
            continue
        text, _c = _text(src)
        if text is None:
            continue
        bp = base_path(root, rel)
        os.makedirs(os.path.dirname(bp), exist_ok=True)
        with open(bp, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)


def load_config(root: str):
    """(keep, skip) as sets of paths from the project's ci-install.json. ({}, {}) when absent. ValueError when bad."""
    path = os.path.join(root, CONFIG.replace("/", os.sep))
    if not os.path.exists(path):
        return set(), set()
    try:
        with open(path, "rb") as f:
            data = json.loads(f.read().decode("utf-8-sig"))
    except (OSError, ValueError) as e:
        raise ValueError("%s is not valid JSON (%s)" % (CONFIG, e))
    if not isinstance(data, dict):
        raise ValueError("%s must be a JSON object with keep and skip lists" % CONFIG)
    lists = []
    for key in ("keep", "skip"):
        val = data.get(key, [])
        if not isinstance(val, list) or not all(isinstance(v, str) for v in val):
            raise ValueError("%s: %r must be a list of paths" % (CONFIG, key))
        lists.append({(v.replace("\\", "/")[2:] if v.replace("\\", "/").startswith("./") else v.replace("\\", "/")) for v in val})
    return lists[0], lists[1]


# ---- several tracks in one project (DL245) ----------------------------------------------------------------------
# `--track rust,ts` installs the shared files once and each track's files. A file two tracks ship at the same path is
# merged when it has a clear structure (ci.yml, gate.json, ci-scope.json); for any other file the first track's copy
# is installed and `TRACK_NOTES` names the file and the track that was skipped. The merge is a pure function of the
# template texts, so `update` rebuilds the same merged base and its 3-way merge keeps the project's edits.
TRACK_NOTES = []          # lines to print: files two tracks ship that could not be merged; set by track_sources
MERGE_FILES = (".github/workflows/ci.yml", "scripts/delivery/gate.json", "scripts/delivery/ci-scope.json")
CI_YML = ".github/workflows/ci.yml"
GATE_JSON = "scripts/delivery/gate.json"
SCOPE_JSON = "scripts/delivery/ci-scope.json"
JOB_ID_RE = re.compile(r"^  ([A-Za-z0-9_-]+):\s*$")
# Patterns for tracks whose templates do not list them. Rust and ts patterns are read from the templates.
FALLBACK_PATHS = {"go": ["**/*.go", "go.mod", "go.sum", "cmd/**", "internal/**", "pkg/**"],
                  "dotnet": ["**/*.cs", "**/*.csproj", "**/*.sln", "**/*.props", "**/*.targets", "global.json"],
                  "ts": ["packages/**", "apps/**", "**/*.ts", "**/*.tsx", "**/*.js", "**/*.jsx", "**/*.mjs",
                         "tsconfig*.json", "eslint.config.mjs"]}
SHARED_PATHS = [".github/**", "scripts/delivery/**", ".delivery/**", ".githooks/**", ".gitleaks.toml", "tools.json"]
_MERGE_DIR = []


def parse_tracks(track) -> list:
    """A track name, "rust,ts" or a list -> the list of names, in order, without repeats."""
    if track is None:
        return []
    names = track.split(",") if isinstance(track, str) else list(track)
    out = []
    for n in names:
        n = str(n).strip()
        if n and n not in out:
            out.append(n)
    return out


def track_value(tracks):
    """What state and gate.json record: a string for one track, a list for several."""
    return tracks[0] if len(tracks) == 1 else list(tracks)


def _tpl(track: str, rel: str):
    path = os.path.join(TEMPLATES, track, rel.replace("/", os.sep))
    if not os.path.isfile(path):
        return None
    with open(path, "rb") as f:
        return f.read().decode("utf-8-sig").replace("\r\n", "\n")


def track_paths(track: str) -> list:
    """The paths a track owns, read from its templates (Rust: gate.json scope_map and the ci.yml path filter)."""
    out = []
    gate = _tpl(track, GATE_JSON)
    if gate:
        smap = json.loads(gate).get("scope_map") or {}
        out += [e for e in smap.get(track, []) if isinstance(e, str)]
    ci = _tpl(track, CI_YML)
    if ci:
        out += [e for e in workflow_path_list(ci, "paths") if not e.startswith((".github/", "tools.json"))]
    if track == "rust":
        out += ["**/*.rs", "**/Cargo.toml", "rustfmt.toml"]
    scope = _tpl(track, SCOPE_JSON)
    if scope:
        out += [e for e in json.loads(scope).get("full_files", []) if not e.startswith(("!", ".github", ".nvmrc"))]
    out += FALLBACK_PATHS.get(track, [])
    seen = []
    for e in out:
        e = e.rstrip("/") + "/**" if e.endswith("/") else e
        if e not in seen:
            seen.append(e)
    return seen


def workflow_path_list(text: str, key: str) -> list:
    """Entries of the first `<key>:` list under `on: pull_request:` (key paths or paths-ignore)."""
    out, on = [], False
    for line in text.split("\n"):
        if line.startswith("  pull_request:"):
            on = True
        elif on and re.match(r"^  \S", line):
            break
        elif on and line.strip() == key + ":":
            on = "list"
        elif on == "list":
            m = re.match(r"^\s+- '?([^'#]+?)'?\s*(#.*)?$", line)
            if not m:
                break
            out.append(m.group(1))
    return out


def merge_scope(texts: dict, tracks: list) -> str:
    """ci-scope.json for several tracks: the one template that ships it, plus `tracks` (patterns per track) and `shared`."""
    first = next(t for t in tracks if t in texts)
    data = json.loads(texts[first])
    data["tracks"] = {t: track_paths(t) for t in tracks}
    data["shared"] = list(SHARED_PATHS)
    return json.dumps(data, indent=2) + "\n"


def merge_gate(texts: dict, tracks: list) -> str:
    """One gate.json with every track's steps. A step both tracks have, word for word, is kept once. A name both use
    with different commands becomes `<name>-<track>`. Every other step carries `"track"`."""
    gates = {t: json.loads(texts[t]) for t in tracks}
    out = dict(gates[tracks[0]])
    out["track"] = list(tracks)
    out["setup"] = _union(g.get("setup", []) for g in gates.values())
    out["timeout_minutes"] = max(g.get("timeout_minutes", 0) for g in gates.values())
    for key in ("widen_on", "inert_paths", "ui_paths"):
        out[key] = _union(g.get(key, []) for g in gates.values())
    pk = [t for t in tracks if (gates[t].get("packages") or {}).get("kind") == "pnpm-workspace"]
    main = pk[0] if pk else tracks[0]
    out["packages"] = gates[main].get("packages")
    out["packages_by_track"] = {t: gates[t].get("packages") for t in tracks}
    out["lockfile_scope"] = gates[main].get("lockfile_scope", "widen")
    out["toolchain-isolated"] = any(g.get("toolchain-isolated") for g in gates.values())
    names = {}
    for t in tracks:
        for st in gates[t].get("steps", []):
            names.setdefault(st["name"], []).append((t, st))
    steps, order = [], {}
    for t in tracks:
        for st in gates[t].get("steps", []):
            same_everywhere = len(names[st["name"]]) == len(tracks) and all(s == st for _t, s in names[st["name"]])
            new = dict(st)
            if same_everywhere:
                if st["name"] in order:
                    continue
                order[st["name"]] = st["name"]
            else:
                if len(names[st["name"]]) > 1:
                    new["name"] = "%s-%s" % (st["name"], t)
                new["track"] = t
                if "paths" not in new:
                    new["paths"] = t
                order[st["name"] + "/" + t] = new["name"]
            steps.append(new)
    rank = lambda s_: 0 if s_["scope"] == "always" else 1 if s_["name"].split("-")[0] in ("lint", "typecheck") else 2  # noqa: E731
    steps = [s_ for _i, s_ in sorted(enumerate(steps), key=lambda p: (rank(p[1]), p[0]))]
    out["steps"] = steps
    out["fail_fast_order"] = [s_["name"] for s_ in steps]
    out["required_steps"] = [s_["name"] for s_ in steps if s_["name"].split("-")[0] in ("lint", "typecheck")]
    smap = {}
    for t in tracks:
        smap.update({k: v for k, v in (gates[t].get("scope_map") or {}).items() if isinstance(v, list)})
        smap.setdefault(t, track_paths(t))
    smap["note"] = "A change under one track's paths selects that track's steps only; a file under no track runs all."
    out["scope_map"] = smap
    return json.dumps(out, indent=2) + "\n"


def _union(lists) -> list:
    out = []
    for lst in lists:
        for e in lst:
            if e not in out:
                out.append(e)
    return out


def split_jobs(text: str):
    """(header lines before `jobs:`, [(job id, block lines)]). A job's block starts at the comments above its key."""
    lines = text.split("\n")
    at = lines.index("jobs:")
    body = lines[at + 1:]
    keys = [i for i, l in enumerate(body) if JOB_ID_RE.match(l)]
    starts = []
    for k in keys:
        s_ = k
        while s_ > 0 and (body[s_ - 1].startswith("  #") or body[s_ - 1] == "") and (not starts or s_ - 1 >= starts[-1] + 1):
            s_ -= 1
        starts.append(s_)
    blocks = []
    for n, k in enumerate(keys):
        end = starts[n + 1] if n + 1 < len(starts) else len(body)
        blocks.append((JOB_ID_RE.match(body[k]).group(1), body[starts[n]:end]))
    return lines[:at + 1], blocks


def _needs_of(line: str) -> list:
    m = re.match(r"^    needs:\s*(.*)$", line)
    val = m.group(1).strip()
    return [x.strip() for x in val.strip("[]").split(",") if x.strip()]


def rename_job(block: list, ids: set, suffix: str, other_env: list) -> list:
    """Suffix the job id, its `needs`, every `needs.<id>` and DELIVERY_SHARD, and the display name."""
    ordered = sorted(ids, key=len, reverse=True)
    pat = re.compile(r"(?<![A-Za-z0-9_-])needs\.(%s)(?![A-Za-z0-9_-])" % "|".join(re.escape(i) for i in ordered)) if ordered else None
    out = []
    for line in block:
        m = JOB_ID_RE.match(line)
        if m and m.group(1) in ids:
            line = "  %s%s:" % (m.group(1), suffix)
        elif re.match(r"^    needs:", line):
            names = [(n + suffix if n in ids else n) for n in _needs_of(line)]
            line = "    needs: [%s]" % ", ".join(names)
        elif re.match(r"^    name:", line):
            val = line.split(":", 1)[1].strip()
            if len(val) >= 2 and val[0] == val[-1] == "'":
                val = val[1:-1].replace("''", "'")
            elif len(val) >= 2 and val[0] == val[-1] == '"':
                val = val[1:-1]
            line = "    name: '%s (%s)'" % (val.replace("'", "''"), suffix.lstrip("-"))
        elif re.match(r"^      DELIVERY_SHARD: ", line):
            line = line + suffix
        if pat:
            line = pat.sub(lambda mm: "needs.%s%s" % (mm.group(1), suffix), line)
        out.append(line)
        if re.match(r"^    env:\s*$", line) and other_env:
            out += other_env
    return out


def gate_if(block: list, track: str) -> list:
    """Add `tracks` to `needs` and the track switch to the job's `if`."""
    out, done = [], False
    for line in block:
        if re.match(r"^    needs:", line):
            names = _needs_of(line)
            if "tracks" not in names:
                names.append("tracks")
            line = "    needs: [%s]" % ", ".join(names)
        elif re.match(r"^    if: \$\{\{ .* \}\}\s*$", line) and not done and track:
            inner = re.match(r"^    if: \$\{\{ (.*) \}\}\s*$", line).group(1)
            line = "    if: ${{ %s && needs.tracks.outputs.%s != 'false' }}" % (inner, track.replace("-", "_"))
            done = True
        out.append(line)
    return out


TRACKS_JOB = """  # ---------------------------------------------------------------------------
  # DL245: which tracks this change touches. scripts/delivery/ci-scope.json lists each track's paths under
  # `tracks` and the paths every track reads under `shared`. A push, a manual run, a file under `shared` or
  # under no track runs every track. The jobs of a track whose output is 'false' are skipped.
  # ---------------------------------------------------------------------------
  tracks:
    name: 'tracks: which languages this change touches'
    needs: decide
    if: ${{ !cancelled() && needs.decide.result != 'failure' && needs.decide.outputs.skip != 'true' && (github.event_name != 'pull_request' || !github.event.pull_request.draft) }}
    runs-on: ${{ fromJSON(vars.CI_RUNS_ON || '"ubuntu-latest"') }}
    permissions:
      contents: read
    outputs:
__OUTPUTS__
    steps:
      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4
        with:
          fetch-depth: 0
      - name: Pick the tracks
        id: pick
        env:
          EVENT: ${{ github.event_name }}
          BASE_SHA: ${{ github.event.pull_request.base.sha }}
        run: |
          python3 - <<'PY'
          import fnmatch, json, os, re, subprocess
          def rx(glob):
              out, i = "", 0
              while i < len(glob):
                  if glob.startswith("**/", i): out += "(?:.*/)?"; i += 3
                  elif glob.startswith("**", i): out += ".*"; i += 2
                  elif glob[i] == "*": out += "[^/]*"; i += 1
                  elif glob[i] == "?": out += "[^/]"; i += 1
                  else: out += re.escape(glob[i]); i += 1
              return re.compile("^" + out + "$")
          def hit(path, globs):
              return any(rx(g).match(path) for g in globs)
          try:
              cfg = json.load(open("scripts/delivery/ci-scope.json"))
              tracks, shared = cfg["tracks"], cfg.get("shared", [])
          except Exception:
              tracks, shared = None, []
          on = {t: True for t in __TRACKS__}
          if tracks and os.environ["EVENT"] == "pull_request":
              try:
                  files = subprocess.run(["git", "diff", "--name-only", os.environ["BASE_SHA"] + "...HEAD"],
                                         capture_output=True, text=True, check=True).stdout.split()
              except Exception:
                  files = []
              if files:
                  on = {t: False for t in on}
                  for f in files:
                      mine = [t for t in on if t in tracks and hit(f, tracks[t])]
                      for t in (mine or list(on)):
                          on[t] = True
          with open(os.environ["GITHUB_OUTPUT"], "a") as out:
              for t, v in on.items():
                  out.write("%s=%s\\n" % (t.replace("-", "_"), "true" if v else "false"))
                  print(t, v)
          PY
"""


def merge_ci(texts: dict, tracks: list) -> str:
    """One ci.yml. The track that owns the held-job protocol (ts, else the first) keeps its job ids. Every other track's
    jobs get the suffix `-<track>`. `decide` is written once; a `tracks` job switches each track's jobs on or off."""
    base = "ts" if "ts" in tracks else tracks[0]
    parts = {t: split_jobs(texts[t]) for t in tracks}
    header = list(parts[base][0])
    # the other tracks' path filters (`paths:`) are no longer ignored
    drop = set()
    for t in tracks:
        if t != base:
            drop.update(workflow_path_list(texts[t], "paths"))
    drop -= {".github/workflows/ci.yml", "tools.json"}
    header = [l for l in header if not (re.match(r"^\s+- '?([^'#]+?)'?\s*$", l) and re.match(r"^\s+- '?([^'#]+?)'?\s*$", l).group(1) in drop)]
    header.insert(1, "\n# DL245: one workflow for the tracks %s. Jobs of %s keep their ids; the jobs of the other tracks end in\n"
                  "# `-<track>`. The `tracks` job reads scripts/delivery/ci-scope.json and switches each track on or off."
                  % (", ".join(tracks), base))
    header = "\n".join(header).split("\n")
    jobs = []
    decide = next(b for i, b in parts[base][1] if i == "decide")
    jobs += decide
    outputs = "\n".join("      %s: ${{ steps.pick.outputs.%s }}" % (t.replace("-", "_"), t.replace("-", "_")) for t in tracks)
    jobs += (TRACKS_JOB.replace("__OUTPUTS__", outputs).replace("__TRACKS__", repr(list(tracks))).split("\n"))[:-1]
    jobs.append("")
    other_ids = []
    for t in [base] + [x for x in tracks if x != base]:
        ids = {i for i, _b in parts[t][1] if i != "decide"}
        suffix = "" if t == base else "-" + t
        env_lines = _top_env(texts[t]) if t != base else []
        for i, block in parts[t][1]:
            if i == "decide":
                continue
            agg = _is_aggregate(block, ids - {i})
            blk = rename_job(block, ids, suffix, env_lines) if suffix else block
            if suffix:
                blk = _only_guard(blk)
            blk = gate_if(blk, "" if agg else t)
            if t != base:
                other_ids.append(i + suffix)
            jobs += blk
    while jobs and jobs[-1] == "":
        jobs.pop()
    text = "\n".join(header + jobs) + "\n"
    return _extend_aggregate(text, other_ids)


def _top_env(text: str) -> list:
    """Workflow-level `env:` entries (indented for a job's env block)."""
    out, on = [], False
    for line in text.split("\n"):
        if line == "env:":
            on = True
        elif on and line.startswith("  ") and line.strip():
            out.append("    " + line)
        elif on and line.strip() and not line.startswith(" "):
            break
    return out


def _only_guard(block: list) -> list:
    """A manual run with `only` set (the ts held-job second run) runs no job of another track."""
    out, done = [], False
    for line in block:
        m = re.match(r"^    if: \$\{\{ (.*) \}\}\s*$", line)
        if m and not done:
            line = "    if: ${{ %s && (inputs.only || '') == '' }}" % m.group(1)
            done = True
        out.append(line)
    return out


def _is_aggregate(block: list, others: set) -> bool:
    for line in block:
        if re.match(r"^    needs:", line):
            return bool(others) and others <= set(_needs_of(line))
    return False


def _extend_aggregate(text: str, other_ids: list) -> str:
    """The aggregate job (it waits for every job of its track) also waits for every other track's jobs and fails when
    one of them failed."""
    if not other_ids:
        return text
    lines = text.split("\n")
    jobs_at = lines.index("jobs:")
    keys = [i for i, l in enumerate(lines) if i > jobs_at and JOB_ID_RE.match(l)]
    for n, k in enumerate(keys):
        end = keys[n + 1] if n + 1 < len(keys) else len(lines)
        ids_here = {JOB_ID_RE.match(lines[j]).group(1) for j in keys}
        block = lines[k:end]
        base_ids = ids_here - set(other_ids) - {"decide", "tracks", JOB_ID_RE.match(lines[k]).group(1)}
        if not any(re.match(r"^    needs:", l) for l in block) or not base_ids <= set(
                _needs_of(next(l for l in block if re.match(r"^    needs:", l)))):
            continue
        if any(re.match(r"^    needs:", l) and "tracks" in _needs_of(l) and set(other_ids) & set(_needs_of(l)) for l in block):
            continue
        new, res = [], " ".join("${{ needs.%s.result }}" % i for i in other_ids)
        for line in block:
            if re.match(r"^    needs:", line):
                line = "    needs: [%s]" % ", ".join(_needs_of(line) + other_ids)
            elif re.match(r"^    if: \$\{\{ .*needs\.decide\.outputs\.skip != 'true'", line):
                extra = " && ".join("needs.%s.result != 'cancelled'" % i for i in other_ids)
                line = line.replace(" && needs.decide.outputs.skip", " && %s && needs.decide.outputs.skip" % extra, 1)
            if line.startswith("      - name: Every shard passed"):
                new += ["      - name: Every job of the other tracks passed",
                        "        env:", "          RESULTS: " + res,
                        "        run: |", "          for r in $RESULTS; do",
                        "            case \"$r\" in success|skipped) ;; *) echo \"a job of another track ended: $r\"; exit 1 ;; esac",
                        "          done", ""]
                new.append(line)
                new.append("        if: ${{ needs.tracks.outputs.ts != 'false' }}")
                continue
            new.append(line)
        return "\n".join(lines[:k] + new + lines[end:])
    print("warning: the merged ci.yml has no aggregate job to extend; add the other tracks' jobs to its needs by hand")
    return text


def track_sources(tracks: list, omit=()) -> dict:
    """{relative path: template file}: shared files, then each track's. A single track is exactly the old behaviour.
    Several tracks merge ci.yml, gate.json and ci-scope.json; for any other shared path the first track's copy wins."""
    TRACK_NOTES.clear()
    sources, owners = {}, {}
    base = os.path.join(TEMPLATES, "shared")
    for rel in files_of(base):
        sources[rel] = os.path.join(base, rel.replace("/", os.sep))
    for t in tracks:
        base = os.path.join(TEMPLATES, t)
        for rel in files_of(base):
            if (t, rel) in omit:
                continue
            owners.setdefault(rel, []).append(t)
            if len(owners[rel]) == 1 or len(tracks) == 1:
                sources[rel] = os.path.join(base, rel.replace("/", os.sep))
    if len(tracks) == 1:
        return sources
    for rel, who in sorted(owners.items()):
        texts = {t: _tpl(t, rel) for t in who}
        if rel in (CI_YML, GATE_JSON) and len(who) == len(tracks):
            text = {CI_YML: merge_ci, GATE_JSON: merge_gate}[rel](texts, tracks)
        elif rel == SCOPE_JSON:
            text = merge_scope(texts, tracks)
        elif len(who) > 1:
            for t in who[1:]:
                TRACK_NOTES.append("track %s: %s is also shipped by track %s; the %s copy is installed, the %s copy is not"
                                   % (t, rel, who[0], who[0], t))
            continue
        elif rel in (CI_YML, GATE_JSON):
            TRACK_NOTES.append("track %s: %s is shipped by track %s only; installed as it is" % (who[0], rel, who[0]))
            continue
        else:
            continue
        sources[rel] = _merged_path(rel, text)
    return sources


def _merged_path(rel: str, text: str) -> str:
    if not _MERGE_DIR:
        import tempfile
        import atexit
        d = tempfile.mkdtemp(prefix="delivery-merge-")
        atexit.register(shutil.rmtree, d, True)
        _MERGE_DIR.append(d)
    path = os.path.join(_MERGE_DIR[0], rel.replace("/", os.sep))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return path


def plan(track, root: str, mode: str, keep=(), skip=(), omit=()) -> list:
    """[(relative path, source, action)] with action written | overwritten | kept | differs | same | skipped | kept (ci-install.json).

    `track` is one track name, "rust,ts" or a list (DL245). Several tracks merge the files they both ship
    (see `track_sources`). `omit` is a set of (track, path) pairs whose template copy is left out."""
    out = []
    tracks = parse_tracks(track)
    recorded = load_state(root)[0] if mode == "update" else {}
    sources = track_sources(tracks, omit)
    for rel in sorted(sources):
        src, dst = sources[rel], os.path.join(root, rel.replace("/", os.sep))
        if not os.path.exists(dst):
            action = "written"
        elif same(src, dst):
            action = "same"
        elif mode == "update" and os.path.basename(rel) not in PROJECT_OWNED_NAMES and rel not in PROJECT_OWNED_PATHS:
            action = "overwritten"
        else:
            action = "differs" if mode == "update" else "kept"
        if rel in skip and action in ("written", "overwritten"):
            action = SKIPPED
        elif rel in keep and action == "overwritten":
            action = KEPT
        if action == "overwritten" and digest(dst) != recorded.get(rel):
            action = CHANGED                              # DL201: the project changed it since the last write
        out.append((rel, src, action))
    return out


# DL192: the rust track installs the Windows workflows only when `ci.options.windows` in .delivery/config.json
# holds a CI option (self-hosted, github-hosted, cloud). Absent, or `deferred`, means Windows is deferred.
WINDOWS_FILES = (".github/workflows/windows-msi-check.yml", ".github/workflows/package-windows.yml")
WINDOWS_TRACKS = ("rust",)


def windows_deferred(root: str) -> bool:
    try:
        with open(os.path.join(root, ".delivery", "config.json"), "rb") as f:
            cfg = json.loads(f.read().decode("utf-8-sig"))
        val = cfg["ci"]["options"]["windows"]
    except (OSError, ValueError, KeyError, TypeError):
        return True
    return val not in ("self-hosted", "github-hosted", "cloud")


# DL229: the ts package.yml and smoke.json carry a `docker build` placeholder. A project with no Dockerfile and no
# packaged-program setting (a static web app) gets neither. An installed file is never deleted.
PACKAGE_FILES = (".github/workflows/package.yml", "scripts/delivery/smoke.json")
PACKAGE_TRACKS = ("ts",)
NO_PACKAGE = "no Dockerfile and no packaged-program setting"
NOPKG = "skipped (no packaged program)"


def has_packaged_program(root: str) -> bool:
    """True when a Dockerfile exists at the root (or the configured path), or .delivery/config.json has a
    `packaged_program` setting: a build command (string) or an object with `build` and/or `dockerfile`."""
    cfg = _json_of(os.path.join(root, ".delivery", "config.json"))
    setting = cfg.get("packaged_program") if isinstance(cfg, dict) else None
    paths = ["Dockerfile"]
    if isinstance(setting, str) and setting.strip():
        return True
    if isinstance(setting, dict):
        if isinstance(setting.get("build"), str) and setting["build"].strip():
            return True
        if isinstance(setting.get("dockerfile"), str) and setting["dockerfile"].strip():
            paths.append(setting["dockerfile"])
    return any(os.path.isfile(os.path.join(root, p.replace("/", os.sep))) for p in paths)


def write_config(src: str, dst: str) -> None:
    """Copy the config template without its `_` keys (_doc, _example...) (DL172)."""
    with open(src, "rb") as f:
        data = json.loads(f.read().decode("utf-8-sig"))
    data = {k: v for k, v in data.items() if not k.startswith("_")}
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(data, indent=2) + "\n")


def apply(items: list, root: str) -> None:
    for rel, src, action in items:
        dst = os.path.join(root, rel.replace("/", os.sep))
        if action in ("same", "overwritten", "written") and os.path.exists(dst + ".new"):
            os.remove(dst + ".new")   # a resolved or stale .new (DL201)
        if action == CHANGED:
            shutil.copyfile(src, dst + ".new")
            continue
        if action == "overwritten" and rel in PRUNE_PLAN:
            _t, crlf = _text(src)
            text = prune_set(_t, PRUNE_PLAN[rel][0])
            with open(dst, "wb") as f:
                f.write((text.replace("\n", "\r\n") if crlf else text).encode("utf-8"))
            continue
        if action in (MERGED, CONFLICT):
            text, _n, crlf = MERGES[rel]
            data = text.replace("\n", "\r\n") if crlf else text
            target = dst if action == MERGED else dst + ".new"
            with open(target, "wb") as f:
                f.write(data.encode("utf-8"))
            if action == MERGED and os.path.exists(dst + ".new"):
                os.remove(dst + ".new")
            continue
        if action not in ("written", "overwritten"):
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if rel in PROJECT_OWNED_PATHS:
            if not os.path.exists(dst):
                write_config(src, dst)
            continue
        shutil.copyfile(src, dst)
        if rel.endswith(".sh") or rel.endswith(".py"):
            try:
                os.chmod(dst, os.stat(dst).st_mode | 0o111)
            except OSError:
                pass


def keep_old_pre_push(items: list, root: str) -> None:
    """`install` only: a project's own pre-push hook becomes pre-push.local, so it survives (DL172)."""
    for rel, src, action in items:
        if rel != PRE_PUSH or action != "kept":
            continue
        dst = os.path.join(root, rel.replace("/", os.sep))
        local = dst + ".local"
        if os.path.exists(local):
            continue
        with open(dst, "rb") as f:
            text = f.read()
        if b"fast_guards.py" in text:
            continue                                     # an older copy of this hook: update replaces it
        os.replace(dst, local)
        print("moved %s to %s (it runs after the guards)" % (rel, rel + ".local"))
        shutil.copyfile(src, dst)
        try:
            os.chmod(dst, os.stat(dst).st_mode | 0o111)
        except OSError:
            pass
        for i, (r, s_, a) in enumerate(items):
            if r == rel:
                items[i] = (r, s_, "written")


def merge_session_guard(root: str, dry_run: bool = False) -> str:
    """Add the session_guard PreToolUse entry to .claude/settings.json. Returns what happened (DL172)."""
    path = os.path.join(root, SETTINGS.replace("/", os.sep))
    data = {}
    if os.path.exists(path):
        try:
            with open(path, "rb") as f:
                data = json.loads(f.read().decode("utf-8-sig"))
        except (OSError, ValueError):
            return "warning: %s is not valid JSON; the session_guard entry was not added" % SETTINGS
        if not isinstance(data, dict):
            return "warning: %s is not a JSON object; the session_guard entry was not added" % SETTINGS
    hooks = data.get("hooks", {})
    pre = hooks.get("PreToolUse", []) if isinstance(hooks, dict) else None
    if not isinstance(pre, list):
        return "warning: %s has an unexpected hooks.PreToolUse; the session_guard entry was not added" % SETTINGS
    for entry in pre:
        for h in (entry.get("hooks", []) if isinstance(entry, dict) else []):
            if isinstance(h, dict) and GUARD_MARK in str(h.get("command", "")):
                return "same"
    if dry_run:
        return "would add"
    pre.append({"matcher": "Bash", "hooks": [{"type": "command", "command": GUARD_COMMAND}]})
    hooks["PreToolUse"] = pre
    data["hooks"] = hooks
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(data, indent=2) + "\n")
    return "added"


def imported_names(path: str) -> set:
    """Top-level module names a Python file imports (module level and inside functions)."""
    try:
        with open(path, "rb") as f:
            tree = ast.parse(f.read())
    except (OSError, SyntaxError, ValueError):
        return set()
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def missing_imports(items: list, root: str) -> list:
    """[(script, module)]: sibling modules a managed scripts/delivery/*.py imports that are not on disk in the project.

    A sibling is a module name that has a shipped file next to the script. With --dry-run nothing was written,
    so a file the run would write still counts as missing, but only when the importing script is already in the
    project (a dry run on an empty project has nothing to report).
    """
    shipped = {rel for rel, _s, _a in items}
    out = []
    for rel, src, _a in items:
        if not (rel.startswith("scripts/delivery/") and rel.endswith(".py")):
            continue
        if not os.path.exists(os.path.join(root, rel.replace("/", os.sep))):
            continue
        folder = rel.rsplit("/", 1)[0]
        for name in sorted(imported_names(src)):
            sibling = "%s/%s.py" % (folder, name)
            if sibling in shipped and not os.path.exists(os.path.join(root, sibling.replace("/", os.sep))):
                out.append((rel, name))
    return out


def untracked(items: list, root: str) -> list:
    """Managed files that exist in the project but are not tracked by git. [] when it is not a git repo."""
    try:
        proc = subprocess.run(["git", "-C", root, "ls-files", "-z"], capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return []
    tracked = set(proc.stdout.decode("utf-8", "replace").split("\0"))
    loose = [rel for rel, _s, a in items if os.path.exists(os.path.join(root, rel.replace("/", os.sep)))
             and rel not in tracked]
    return [rel for rel in loose if rel not in ignored_by_git(loose, root)]


def ignored_by_git(rels: list, root: str) -> set:
    """DL227: the paths in `rels` that .gitignore ignores (`git check-ignore`). An empty set when git cannot say."""
    if not rels:
        return set()
    try:
        proc = subprocess.run(["git", "-C", root, "check-ignore", "-z", "--stdin"], capture_output=True,
                              input="\0".join(rels).encode("utf-8"))
    except OSError:
        return set()
    return set(proc.stdout.decode("utf-8", "replace").split("\0")) - {""}


PRUNE_WORKFLOW = ".github/workflows/artifact-prune.yml"
PRUNE_SCRIPT = "scripts/delivery/artifact_prune.py"


SYNC_FAILED = "sync failed"


def sync_prune_workflow(items: list, root: str) -> bool:
    """DL150: apply artifact_prune.workflows after `update` rewrote the template's workflow. Never raises.
    False when the sync failed (DL227: the caller then does not report the file as merged)."""
    if not any(rel == PRUNE_WORKFLOW and action in ("overwritten", MERGED) for rel, _s, action in items):
        return True
    script = os.path.join(root, PRUNE_SCRIPT.replace("/", os.sep))
    if not os.path.exists(script):
        print("could not sync %s: %s is not in the project. Fix: run `python %s --sync-workflow` once it is."
              % (PRUNE_WORKFLOW, PRUNE_SCRIPT, PRUNE_SCRIPT))
        return False
    try:
        proc = subprocess.run([sys.executable, script, "--sync-workflow"], cwd=root, capture_output=True, text=True)
    except OSError as e:
        proc = None
        detail = str(e)
    else:
        detail = (proc.stderr or proc.stdout).strip()
    if proc is not None and proc.returncode == 0:
        print("artifact_prune: %s" % (proc.stdout.strip() or "synced"))
        return True
    print("could not sync %s: %s" % (PRUNE_WORKFLOW, detail))
    print("The update is kept. Fix the error, then run `python %s --sync-workflow` in the project." % PRUNE_SCRIPT)
    return False


GITIGNORE = ".gitignore"
GI_BEGIN = "# luismc-delivery: compiled Python (do not edit this block)"
GI_END = "# luismc-delivery: end of compiled Python"


def gitignore(root: str, dry_run: bool = False) -> str:
    """DL227: keep a marked block in .gitignore that ignores __pycache__/ and *.pyc.
    Returns "same", "written" or "updated" ("would be ..." on a dry run). Other lines and line endings stay."""
    block = [GI_BEGIN, "__pycache__/", "*.pyc", GI_END]
    path = os.path.join(root, GITIGNORE)
    raw = b""
    if os.path.exists(path):
        with open(path, "rb") as f:
            raw = f.read()
    text = raw.decode("utf-8")
    eol = "\r\n" if "\r\n" in text else "\n"
    lines = text.replace("\r\n", "\n").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if GI_BEGIN in lines and GI_END in lines[lines.index(GI_BEGIN):]:
        i = lines.index(GI_BEGIN)
        new = lines[:i] + block + lines[lines.index(GI_END, i) + 1:]
    else:
        new = lines + block
    data = (eol.join(new) + eol).encode("utf-8")
    if data == raw:
        return "same"
    action = "updated" if raw else "written"
    if dry_run:
        return "would be " + action
    with open(path, "wb") as f:
        f.write(data)
    return action


def tracked_pyc(items: list, root: str) -> list:
    """DL227: tracked .pyc files under installed folders. Reported only; never removed."""
    try:
        proc = subprocess.run(["git", "-C", root, "ls-files", "-z"], capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return []
    dirs = {rel.rsplit("/", 1)[0] + "/" for rel, _s, _a in items if "/" in rel}
    out = []
    for f in proc.stdout.decode("utf-8", "replace").split("\0"):
        if f.endswith((".pyc", ".pyo")) and any(f.startswith(d) for d in dirs):
            out.append(f)
    return out


PRETTIERIGNORE = ".prettierignore"
PI_BEGIN = "# luismc-delivery: installer copies (do not edit this block)"
PI_END = "# luismc-delivery: end of installer copies"


def uses_prettier(root: str) -> bool:
    """DL218: a Prettier config file, a `prettier` key in package.json, or prettier as a dependency."""
    try:
        names = os.listdir(root)
    except OSError:
        return False
    if any(n.startswith(".prettierrc") or n.startswith("prettier.config.") for n in names):
        return True
    data = _json_of(os.path.join(root, "package.json"))
    if not isinstance(data, dict):
        return False
    if "prettier" in data:
        return True
    return any(isinstance(data.get(k), dict) and "prettier" in data[k] for k in ("dependencies", "devDependencies"))


def prettierignore(items: list, root: str, dry_run: bool = False) -> str:
    """DL218: keep a marked block in .prettierignore that lists the installer's own copies.
    Returns "" (no Prettier), "same", "written" or "updated" ("would ..." on a dry run)."""
    if not uses_prettier(root):
        return ""
    paths = [BASE_DIR + "/"] + sorted(rel for rel, _s, a in items if rel.endswith(".example.json") and a != SKIPPED)
    block = [PI_BEGIN] + paths + [PI_END]
    path = os.path.join(root, PRETTIERIGNORE)
    raw = b""
    if os.path.exists(path):
        with open(path, "rb") as f:
            raw = f.read()
    text = raw.decode("utf-8")
    eol = "\r\n" if "\r\n" in text else "\n"
    lines = text.replace("\r\n", "\n").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if PI_BEGIN in lines and PI_END in lines[lines.index(PI_BEGIN):]:
        i = lines.index(PI_BEGIN)
        j = lines.index(PI_END, i)
        new = lines[:i] + block + lines[j + 1:]
    else:
        new = lines + block
    data = (eol.join(new) + eol).encode("utf-8")
    if data == raw:
        return "same"
    action = "updated" if raw else "written"
    if dry_run:
        return "would be " + action
    with open(path, "wb") as f:
        f.write(data)
    return action


def tz_name(root: str):
    """The `tz` key of .delivery/config.json, or None."""
    try:
        with open(os.path.join(root, ".delivery", "config.json"), "rb") as f:
            val = json.loads(f.read().decode("utf-8-sig")).get("tz")
    except (OSError, ValueError, AttributeError):
        return None
    return val if isinstance(val, str) and val else None


def tz_loads(name: str) -> bool:
    try:
        from zoneinfo import ZoneInfo
        ZoneInfo(name)
        return True
    except Exception:  # noqa: BLE001 - ZoneInfoNotFoundError, ValueError, ImportError
        return name in ("UTC", "Etc/UTC")


def ensure_tzdata(root: str, interactive=None, ask=input) -> None:
    """DL157: when the configured tz does not load, install tzdata with pip (--user) and check again."""
    name = tz_name(root)
    if not name or tz_loads(name):
        return
    cmd = [sys.executable, "-m", "pip", "install", "--user", "tzdata"]
    if interactive is None:
        interactive = sys.stdin is not None and sys.stdin.isatty()
    print("time zone %r does not load (no time zone data)." % name)
    if interactive:
        try:
            answer = ask("Install tzdata with `python -m pip install --user tzdata`? [Y/n] ")
        except EOFError:
            answer = "n"
        if answer.strip().lower() not in ("", "y", "yes"):
            print("tzdata not installed. Run `python -m pip install --user tzdata`; until then times fall back to UTC.")
            return
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        ok = proc.returncode == 0
        detail = (proc.stderr or proc.stdout).strip()
    except OSError as e:
        ok, detail = False, str(e)
    if not ok:
        print("tzdata install failed: %s\nRun `python -m pip install --user tzdata` by hand; until then times fall back to UTC."
              % detail)
        return
    print("ran `python -m pip install --user tzdata`")
    if tz_loads(name):
        print("time zone %r loads now." % name)
    else:
        print("time zone %r still does not load; check the `tz` key or restart the shell." % name)


def only_steps(root: str, only: set, action: str, dry_run: bool) -> int:
    if "config" in only:
        src = os.path.join(TEMPLATES, "shared", ".delivery", "config.json")
        dst = os.path.join(root, ".delivery", "config.json")
        if os.path.exists(dst):
            print("same        .delivery/config.json (kept: the project owns it)")
        else:
            if not dry_run:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                write_config(src, dst)
            print("written     .delivery/config.json")
    if "settings" in only:
        print("settings    %s: %s" % (SETTINGS, merge_session_guard(root, dry_run)))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="delivery_ci_install.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("action", choices=["install", "update"])
    ap.add_argument("--track", default=None)
    ap.add_argument("--only", default=None, help="config,settings: write only .delivery/config.json and/or the session_guard settings entry")
    ap.add_argument("--root", default=".", help="the project root (default: the current folder)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    only = set(args.only.split(",")) if args.only else None
    if only is not None and not only <= {"config", "settings"}:
        print("delivery_ci_install: --only takes config and/or settings", file=sys.stderr)
        return 1
    if only is not None and args.track is None:
        return only_steps(os.path.abspath(args.root), only, args.action, args.dry_run)
    if args.track is None and args.action == "update":
        args.track = known_track(os.path.abspath(args.root))   # DL213
        if args.track is not None:
            print("delivery_ci_install: using track %s from the project" % args.track)
    tracks = parse_tracks(args.track)
    if not tracks or not all(t in TRACKS for t in tracks):
        print("delivery_ci_install: --track must be one of %s (several: comma-separated, e.g. rust,ts; the project does not say which it uses)" % ", ".join(TRACKS), file=sys.stderr)
        return 1
    missing_tpl = [t for t in ["shared"] + tracks if not os.path.isdir(os.path.join(TEMPLATES, t))]
    if missing_tpl:
        print("delivery_ci_install: no templates for %r under %s" % (missing_tpl[-1] if missing_tpl[-1] != "shared" else args.track, TEMPLATES), file=sys.stderr)
        return 2
    root = os.path.abspath(args.root)
    try:
        keep, skip = load_config(root)
    except ValueError as e:
        print("delivery_ci_install: %s" % e, file=sys.stderr)
        return 2
    if any(t in WINDOWS_TRACKS for t in tracks) and windows_deferred(root):
        skip = set(skip) | set(WINDOWS_FILES)
        print("Windows is deferred (no ci.options.windows in .delivery/config.json): the Windows workflows are not installed. "
              "Choose it with `delivery_ci.py set`, then run install again.")
    no_package = any(t in PACKAGE_TRACKS for t in tracks) and not has_packaged_program(root)
    omit = set()
    if no_package and len(tracks) > 1:
        # DL245: with another track the package files come from that track; only the ts copy is left out.
        omit = {(t, f) for t in tracks if t in PACKAGE_TRACKS for f in PACKAGE_FILES}
        no_package = not any(f for t in tracks if t not in PACKAGE_TRACKS
                             for f in PACKAGE_FILES if os.path.isfile(os.path.join(TEMPLATES, t, f.replace("/", os.sep))))
    user_skip = set(skip)
    if no_package:
        skip = set(skip) | set(PACKAGE_FILES)
    old_state, had_state = load_state(root)
    items = plan(tracks, root, args.action, keep, skip, omit)
    for note in TRACK_NOTES:
        print("note: " + note)
    if no_package:
        items = [(r, sr, NOPKG if r in PACKAGE_FILES and a == SKIPPED and r not in (user_skip) else a) for r, sr, a in items]
    if args.action == "update":
        plan_prune_list(items, root)
        items = merge_changed(items, root)
    managed = {rel for rel, _s, _a in items}
    for rel in sorted((keep | skip) - managed):
        print("warning: %s lists %s, which the plugin does not manage" % (CONFIG, rel))
    if not args.dry_run:
        if args.action == "install":
            keep_old_pre_push(items, root)
        apply(items, root)
        print("settings    %s: %s" % (SETTINGS, merge_session_guard(root)))
    pi = prettierignore(items, root, args.dry_run)
    gi = gitignore(root, args.dry_run)
    if not args.dry_run and args.action == "update":
        if any(r == PRUNE_WORKFLOW and a in ("overwritten", MERGED) for r, _s, a in items):
            report_prune_list()
        if not sync_prune_workflow(items, root):
            items = [(r, sr, SYNC_FAILED if r == PRUNE_WORKFLOW and a == MERGED else a) for r, sr, a in items]
    if not args.dry_run:
        save_state(items, root, old_state, track_value(tracks))
        record_bases(items, root)
    if not args.dry_run:
        ensure_tzdata(root)
    for rel, _src, action in items:
        if action != "same":
            print("%-11s %s" % (action, rel))
    if pi and pi != "same":
        print("%-11s %s (installer copies, Prettier)" % (pi, PRETTIERIGNORE))
    if gi != "same":
        print("%-11s %s (compiled Python)" % (gi, GITIGNORE))
    if no_package:
        for rel, _s, a in items:
            if rel in PACKAGE_FILES and a == NOPKG:
                print("skipped: %s (%s)" % (NO_PACKAGE, rel))
            elif rel in PACKAGE_FILES and a != "written":
                print("%s is installed and kept: %s; the installer never deletes it" % (rel, NO_PACKAGE))
    counts = {}
    for _r, _s, a in items:
        counts[a] = counts.get(a, 0) + 1
    print("delivery_ci_install: %s" % ", ".join("%d %s" % (n, a) for a, n in sorted(counts.items())))
    for rel, src, action in items:
        if action == KEPT:
            print("kept %s: the plugin's version differs; diff it with %s and fold your change into the plugin or drop it"
                  % (rel, os.path.relpath(src, PLUGIN).replace(os.sep, "/")))
    order = ("written", "overwritten", MERGED, CONFLICT, "kept", "same", "skipped")
    tally = dict.fromkeys(order, 0)
    for _r, _s, a in items:
        key = "kept" if a in (CHANGED, KEPT) else "skipped" if a in (SKIPPED, NOPKG) else a
        if key in tally:
            tally[key] += 1
    print("summary: %s" % ", ".join("%d %s" % (tally[k], k) for k in order))
    for rel, _s, a in items:
        if a == CONFLICT:
            print("conflict %s: %d conflict(s); resolve %s.new, then copy it over %s and rerun update"
                  % (rel, MERGES[rel][1], rel, rel))
    changed = [rel for rel, _s, a in items if a == CHANGED]
    for rel in changed:
        print("kept (project changes): %s; new template in %s.new; compare with: git diff --no-index %s %s.new"
              % (rel, rel, rel, rel))
    if changed:
        print("Merge by hand, then delete the .new files. The plugin never commits them. "
              "The new template is now the merge base, so the next update can merge.")
        if not args.dry_run and not had_state:
            print("No install record was found, so this first update after DL201 is careful: every file that "
                  "differs from the template was kept.")
    loose = untracked(items, root)
    if loose:
        print("not in git yet (commit them):")
        for rel in loose:
            print("  " + rel)
    quiet = ignored_by_git([rel for rel, _s, _a in items], root)
    quiet = sorted(r for r in quiet if os.path.exists(os.path.join(root, r.replace("/", os.sep))))
    if quiet:
        print("ignored by .gitignore: " + ", ".join(quiet))
    pyc = tracked_pyc(items, root)
    if pyc:
        print("tracked .pyc files (the installer does not remove them):")
        for f in pyc:
            print("  " + f)
        print("Untrack them with: git rm --cached " + " ".join(pyc))
    missing = missing_imports(items, root)
    if missing:
        print("missing imports:")
        for rel, name in missing:
            print("  %s imports %s.py, which is not in %s" % (rel, name, rel.rsplit("/", 1)[0]))
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
