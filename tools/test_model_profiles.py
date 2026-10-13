#!/usr/bin/env python3
"""Check the per-skill model profiles and the claude-setup assets that carry
the agent rules.

What is checked against a repo root:
  P1  every claude/plugins/*/skills/*/SKILL.md names its skill in
      claude-setup/assets/model-profiles.json (a skill on disk but not in the
      table fails; a skill in the table but not on disk is skipped)
  P2  its `model:` and `effort:` frontmatter match its profile
  R1  agents-and-integration.md has the role lines, the section headings and
      the {{SUBAGENT_EFFORT}} placeholder
  S1  the settings template registers the SessionStart effort_drift.py hook
      and the hook file ships next to it
  M1  no model-delegation.md remains in the claude-setup assets
  E1  the settings template enables luismc-artifacts@{{MARKETPLACE}} and
      SKILL.md says how the placeholder is filled
  K1  assets/keybindings.json parses and holds exactly the Global context with
      the two transcript-folds chords and their actions; when the plugin's
      source (claude/plugins/transcript-folds/hooks/) is on the branch it names
      the same two actions, otherwise that cross-check is skipped with a
      printed message, never silently passed
  K2  SKILL.md names the luismc-transcript-folds enabledPlugins entry, the
      keybindings merge and the plugin install in its report
  D1  the owner's default, medium for Opus and Sonnet alike: every profile
      is medium, the architect agent (Opus) is medium, the settings
      template's top-level effortLevel is medium, and claude-setup recommends
      medium for both models

Each check is then proved able to fail: a clean copy of the relevant files is
mutated one way at a time, and the mutation must produce the matching finding.
The hook is exercised the same way, on small settings fixtures.

feature-artifact-new belongs to the luismc-artifacts plugin, which is edited
on its own branch; until it is joined, the real tree reports its old effort as
a P2 failure. That is expected; every other check passes.

Run:  python3 tools/test_model_profiles.py
"""
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
SETUP = "claude/plugins/project-setup/skills/claude-setup"
ASSETS = SETUP + "/assets"
PROFILES = ASSETS + "/model-profiles.json"
RULE = ASSETS + "/.claude/rules/agents-and-integration.md"
OLD_RULE = ASSETS + "/.claude/rules/model-delegation.md"
SETTINGS = ASSETS + "/.claude/settings.json"
HOOK = ASSETS + "/.claude/hooks/effort_drift.py"

RULE_LINES = [
    "## Agents",
    "- Orchestrator (strongest model):",
    "- Code agents: Sonnet at {{SUBAGENT_EFFORT}} effort;",
    "pass `effort: \"{{SUBAGENT_EFFORT}}\"` on every implementation Agent call.",
    "- Merges and checks: scripts.",
    "Log triage: `model: \"haiku\"`.",
    "- Opus agents (`model: \"opus\"`) and Sonnet agents both pass "
    "`effort: \"medium\"` unless the user chose otherwise in claude-setup.",
    "- Agents whose definition pins a model or effort keep it.",
    "- Trivial edits",
    "- Max 5 agents at once, and at most 3 when they run heavy test suites",
    "## Integrate once, deploy once",
    "## Docs",
    "- Create every doc under `docs/`.",
]
PLACEHOLDER = "{{SUBAGENT_EFFORT}}"
ARTIFACTS_PLUGIN = "luismc-artifacts@{{MARKETPLACE}}"
SKILL = SETUP + "/SKILL.md"
ARCHITECT = "claude/plugins/agents/agents/architect.md"
KEYBINDINGS = ASSETS + "/keybindings.json"
FOLDS_HOOKS = "claude/plugins/transcript-folds/hooks"
CHORDS = {"ctrl+x d": "theme:toggleSyntaxHighlighting",
          "ctrl+x f": "theme:editCustom"}
FOLDS_PLUGIN = "luismc-transcript-folds"
EXPECTED_PENDING = ("P2 feature-artifact-new",)


def frontmatter(text):
    """`key: value` lines between the first two `---` fences."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    out = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return out
        if ":" in line and not line.startswith((" ", "\t")):
            key, _, value = line.partition(":")
            out[key.strip()] = value.strip()
    return out


def profile_table(root):
    """{skill: (model, effort)} from model-profiles.json."""
    data = json.loads((root / PROFILES).read_text(encoding="utf-8"))
    table = {}
    for group in data.values():
        for skill in group["skills"]:
            table[skill] = (group["model"], group["effort"])
    return table


DEFAULT_EFFORT = {"opus": "medium", "sonnet": "medium"}


def defaults(root):
    """D1 findings: the owner's default, medium for Opus and Sonnet."""
    found = []
    try:
        data = json.loads((root / PROFILES).read_text(encoding="utf-8"))
        for name, group in data.items():
            want = DEFAULT_EFFORT.get(group["model"])
            if want and group["effort"] != want:
                found.append(f"D1 profile {name}: {group['model']} is "
                             f"{group['effort']}, want {want}")
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        pass  # P0 already reports an unreadable table
    try:
        fm = frontmatter((root / ARCHITECT).read_text(encoding="utf-8"))
    except OSError:
        fm = {}
    if fm.get("model") != "opus" or fm.get("effort") != "medium":
        found.append("D1 architect agent is not opus at medium effort")
    try:
        top = json.loads((root / SETTINGS).read_text(encoding="utf-8")).get("effortLevel")
    except (OSError, ValueError, AttributeError):
        top = None
    if top != "medium":
        found.append(f"D1 settings top-level effortLevel is {top}, want medium")
    try:
        text = " ".join((root / SKILL).read_text(encoding="utf-8").split())
    except OSError:
        text = ""
    if text.count("**Recommend medium**") < 2:
        found.append("D1 SKILL.md does not recommend medium for both models")
    if "**Recommend high**" in text:
        found.append("D1 SKILL.md recommends high for a model")
    if '| `effortLevel` | `"medium"` |' not in text:
        found.append("D1 SKILL.md effortLevel row is not medium")
    return found


def plugin_source_present(root):
    return (pathlib.Path(root) / FOLDS_HOOKS).is_dir()


def keybindings(root):
    """K1 and K2 findings: the keybindings asset, the plugin source, SKILL.md."""
    root = pathlib.Path(root)
    found = []
    try:
        data = json.loads((root / KEYBINDINGS).read_text(encoding="utf-8"))
        blocks = data["bindings"]
        assert isinstance(blocks, list)
    except (OSError, ValueError, KeyError, TypeError, AssertionError):
        found.append("K1 assets/keybindings.json is missing or does not parse")
        blocks = []
    if blocks:
        if len(blocks) != 1 or blocks[0].get("context") != "Global":
            found.append("K1 keybindings.json is not exactly one Global context")
        elif blocks[0].get("bindings") != CHORDS:
            found.append(f"K1 keybindings.json chords are not exactly {CHORDS}")
    if plugin_source_present(root):
        source = ""
        for path in sorted((root / FOLDS_HOOKS).rglob("*")):
            if path.is_file():
                source += path.read_text(encoding="utf-8", errors="replace")
        for action in CHORDS.values():
            if action not in source:
                found.append(f"K1 plugin source does not name the action {action}")
    try:
        text = " ".join((root / SKILL).read_text(encoding="utf-8").split())
    except OSError:
        text = ""
    for needle in (f'"{FOLDS_PLUGIN}@<marketplace>"', "~/.claude/keybindings.json",
                   f"claude plugin install {FOLDS_PLUGIN}@<marketplace>",
                   "/reload-plugins"):
        if needle not in text:
            found.append(f"K2 SKILL.md lacks: {needle}")
    return found


def check(root):
    """Every finding for the tree at `root`, as a list of strings."""
    root = pathlib.Path(root)
    found = []
    try:
        table = profile_table(root)
    except (OSError, ValueError, KeyError) as exc:
        return [f"P0 model-profiles.json unreadable: {exc}"]

    for path in sorted((root / "claude/plugins").glob("*/skills/*/SKILL.md")):
        skill = path.parent.name
        if skill not in table:
            found.append(f"P1 {skill}: SKILL.md is not in model-profiles.json")
            continue
        fm = frontmatter(path.read_text(encoding="utf-8"))
        want_model, want_effort = table[skill]
        for key, want in (("model", want_model), ("effort", want_effort)):
            have = fm.get(key)
            if have is None:
                found.append(f"P2 {skill}: frontmatter has no {key} (want {want})")
            elif have != want:
                found.append(f"P2 {skill}: {key} is {have}, want {want}")

    rule = root / RULE
    if not rule.is_file():
        found.append("R1 agents-and-integration.md is missing")
    else:
        text = rule.read_text(encoding="utf-8")
        for needle in RULE_LINES:
            if needle not in text:
                found.append(f"R1 rule file lacks: {needle}")
        if PLACEHOLDER not in text:
            found.append("R1 rule file lacks the {{SUBAGENT_EFFORT}} placeholder")

    try:
        settings = json.loads((root / SETTINGS).read_text(encoding="utf-8"))
        entries = settings["hooks"]["SessionStart"]
        commands = [h.get("command", "") for e in entries for h in e["hooks"]]
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        commands = []
    if not any("effort_drift.py" in c for c in commands):
        found.append("S1 settings template registers no SessionStart effort_drift.py")
    if not (root / HOOK).is_file():
        found.append("S1 hooks/effort_drift.py is missing from the assets")

    if (root / OLD_RULE).exists():
        found.append("M1 model-delegation.md is still in the assets")

    try:
        enabled = json.loads((root / SETTINGS).read_text(encoding="utf-8"))["enabledPlugins"]
        on = enabled.get(ARTIFACTS_PLUGIN) is True
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        on = False
    if not on:
        found.append(f"E1 settings template does not enable {ARTIFACTS_PLUGIN}")
    try:
        skill_text = (root / SKILL).read_text(encoding="utf-8")
    except OSError:
        skill_text = ""
    if "{{MARKETPLACE}}" not in skill_text or "luismc-project-setup@" not in skill_text:
        found.append("E1 SKILL.md does not say how {{MARKETPLACE}} is filled")
    found += keybindings(root)
    found += defaults(root)
    return found


def copy_tree(dest):
    """The files check() reads, copied from the real repo into `dest`."""
    for path in (ROOT / "claude/plugins").glob("*/skills/*/SKILL.md"):
        target = dest / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    shutil.copytree(ROOT / ASSETS, dest / ASSETS)
    (dest / ARCHITECT).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / ARCHITECT, dest / ARCHITECT)
    # Make the copy clean: give every SKILL.md on disk its profile, so each
    # mutation below is the only defect in the tree.
    table = profile_table(dest)
    for path in (dest / "claude/plugins").glob("*/skills/*/SKILL.md"):
        model, effort = table.get(path.parent.name, (None, None))
        if model is None:
            continue
        text = path.read_text(encoding="utf-8")
        fm = frontmatter(text)
        if fm.get("model") != model or fm.get("effort") != effort:
            set_frontmatter(path, model, effort)


def set_frontmatter(path, model, effort):
    lines = [l for l in path.read_text(encoding="utf-8").splitlines()
             if not l.startswith(("model:", "effort:"))]
    end = lines.index("---", 1)
    lines[end:end] = [f"model: {model}", f"effort: {effort}"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def edit(path, old, new):
    text = path.read_text(encoding="utf-8")
    assert old in text, f"fixture drift: {old!r} not in {path.name}"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


# (name, mutation(root), substring the findings must contain)
def m_wrong_model(r):
    set_frontmatter(r / "claude/plugins/specs/skills/spec-new/SKILL.md",
                    "sonnet", "high")


def m_wrong_effort(r):
    set_frontmatter(r / "claude/plugins/specs/skills/spec-check/SKILL.md",
                    "sonnet", "high")


def m_no_model_line(r):
    p = r / "claude/plugins/audits/skills/security-audit/SKILL.md"
    p.write_text("\n".join(l for l in p.read_text(encoding="utf-8").splitlines()
                           if not l.startswith("model:")) + "\n",
                 encoding="utf-8")


def m_unknown_skill(r):
    d = r / "claude/plugins/specs/skills/brand-new-skill"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text("---\nmodel: opus\neffort: high\n---\n",
                                encoding="utf-8")


def m_role_line(r):
    edit(r / RULE, "- Code agents: Sonnet at", "- Code workers: Sonnet at")


def m_opus_agent_line(r):
    edit(r / RULE, 'both pass `effort: "medium"`', 'both pass `effort: "high"`')


def m_opus_profile_high(r):
    p = r / PROFILES
    p.write_text(p.read_text(encoding="utf-8").replace(
        '"model": "opus", "effort": "medium"', '"model": "opus", "effort": "high"'),
        encoding="utf-8")


def m_sonnet_profile_high(r):
    p = r / PROFILES
    p.write_text(p.read_text(encoding="utf-8").replace(
        '"model": "sonnet", "effort": "medium"', '"model": "sonnet", "effort": "high"'),
        encoding="utf-8")


def m_architect_high(r):
    edit(r / ARCHITECT, "effort: medium", "effort: high")


def m_top_level_high(r):
    edit(r / SETTINGS, '"effortLevel": "medium"', '"effortLevel": "high"')


def m_skill_opus_high(r):
    edit(r / SKILL, "**Recommend medium**", "**Recommend high**")


def m_skill_sonnet_high(r):
    edit(r / SKILL, "**Recommend\n  medium**", "**Recommend high**")


def m_skill_table_high(r):
    edit(r / SKILL, '| `effortLevel` | `"medium"` |', '| `effortLevel` | `"high"` |')


def m_placeholder(r):
    p = r / RULE
    p.write_text(p.read_text(encoding="utf-8").replace(PLACEHOLDER, "high"),
                 encoding="utf-8")


def m_rule_missing(r):
    (r / RULE).unlink()


def m_no_hook_registration(r):
    p = r / SETTINGS
    data = json.loads(p.read_text(encoding="utf-8"))
    del data["hooks"]
    p.write_text(json.dumps(data), encoding="utf-8")


def m_no_hook_file(r):
    (r / HOOK).unlink()


def m_old_rule(r):
    (r / OLD_RULE).write_text("old\n", encoding="utf-8")


def m_no_enabled_plugins(r):
    p = r / SETTINGS
    data = json.loads(p.read_text(encoding="utf-8"))
    del data["enabledPlugins"]
    p.write_text(json.dumps(data), encoding="utf-8")


def m_marketplace_unexplained(r):
    p = r / SKILL
    p.write_text(p.read_text(encoding="utf-8").replace("{{MARKETPLACE}}", "x"),
                 encoding="utf-8")


def m_hardcoded_marketplace(r):
    p = r / SETTINGS
    p.write_text(p.read_text(encoding="utf-8").replace(
        "{{MARKETPLACE}}", "dev-standards"), encoding="utf-8")


def m_kb_wrong_action(r):
    edit(r / KEYBINDINGS, "theme:editCustom", "theme:other")


def m_kb_extra_chord(r):
    edit(r / KEYBINDINGS, '"ctrl+x f"', '"ctrl+x g": "x:y", "ctrl+x f"')


def m_kb_missing(r):
    (r / KEYBINDINGS).unlink()


def m_kb_plugin_mismatch(r):
    d = r / FOLDS_HOOKS
    d.mkdir(parents=True)
    (d / "transcript_folds.tsx").write_text(
        "action: 'theme:toggleSyntaxHighlighting'\n", encoding="utf-8")


def m_skill_no_folds(r):
    p = r / SKILL
    p.write_text(p.read_text(encoding="utf-8").replace(
        "~/.claude/keybindings.json", "the keys file"), encoding="utf-8")


def m_bad_json(r):
    (r / PROFILES).write_text("{", encoding="utf-8")


MUTATIONS = [
    ("P2 wrong model", m_wrong_model, "spec-new: model is sonnet, want opus"),
    ("P2 wrong effort", m_wrong_effort, "spec-check: effort is high, want medium"),
    ("P2 missing model line", m_no_model_line, "security-audit: frontmatter has no model"),
    ("P1 skill not in table", m_unknown_skill, "brand-new-skill: SKILL.md is not in"),
    ("R1 role line gone", m_role_line, "rule file lacks: - Code agents"),
    ("R1 Opus agent line wrong", m_opus_agent_line, "rule file lacks: - Opus agents"),
    ("D1 Opus profile high", m_opus_profile_high, "D1 profile judgment: opus is high"),
    ("D1 Sonnet profile high", m_sonnet_profile_high, "D1 profile mechanical: sonnet is high"),
    ("D1 architect high", m_architect_high, "D1 architect agent"),
    ("D1 top-level effort high", m_top_level_high, "top-level effortLevel is high"),
    ("D1 SKILL Opus recommends high", m_skill_opus_high, "SKILL.md does not recommend medium for both"),
    ("D1 SKILL Sonnet recommends high", m_skill_sonnet_high, "SKILL.md does not recommend medium for both"),
    ("D1 SKILL table row high", m_skill_table_high, "effortLevel row is not medium"),
    ("R1 placeholder gone", m_placeholder, "lacks the {{SUBAGENT_EFFORT}}"),
    ("R1 rule file missing", m_rule_missing, "agents-and-integration.md is missing"),
    ("S1 hook not registered", m_no_hook_registration, "registers no SessionStart"),
    ("S1 hook file missing", m_no_hook_file, "effort_drift.py is missing"),
    ("M1 old rule file present", m_old_rule, "model-delegation.md is still"),
    ("E1 plugin not enabled", m_no_enabled_plugins, "does not enable luismc-artifacts"),
    ("E1 marketplace hard-coded", m_hardcoded_marketplace, "does not enable luismc-artifacts"),
    ("E1 placeholder unexplained", m_marketplace_unexplained, "does not say how {{MARKETPLACE}}"),
    ("K1 keybinding action wrong", m_kb_wrong_action, "chords are not exactly"),
    ("K1 extra chord", m_kb_extra_chord, "chords are not exactly"),
    ("K1 keybindings missing", m_kb_missing, "keybindings.json is missing"),
    ("K1 plugin source mismatch", m_kb_plugin_mismatch,
     "plugin source does not name the action theme:editCustom"),
    ("K2 SKILL lacks keybindings", m_skill_no_folds, "SKILL.md lacks: ~/.claude/keybindings.json"),
    ("P0 profiles unreadable", m_bad_json, "model-profiles.json unreadable"),
]


def load_hook():
    spec = importlib.util.spec_from_file_location("effort_drift", ROOT / HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def hook_cases(tmp):
    """(name, ok, detail) for the SessionStart hook on settings fixtures."""
    hook = load_hook()
    home, project = tmp / "home", tmp / "proj"
    for d in (home / ".claude", project / ".claude"):
        d.mkdir(parents=True)

    def settings(path, ids):
        body = {"modelSettings": {i: {"effortLevel": "high"} for i in ids}}
        (path).write_text(json.dumps(body), encoding="utf-8")

    user_file = home / ".claude/settings.json"
    proj_file = project / ".claude/settings.json"
    local_file = project / ".claude/settings.local.json"
    base_env = {"CLAUDE_PROJECT_DIR": str(project)}
    cases = []

    def case(name, data, env, want_warning, contains=None):
        msg = hook.evaluate(data, {**base_env, **env}, str(home))
        ok = bool(msg) == want_warning and (contains is None or contains in (msg or ""))
        cases.append((name, ok, msg or "silent"))

    case("hook warns: model has no entry", {"model": "claude-opus-6"}, {},
         True, "claude-opus-6")
    settings(user_file, ["claude-opus-6"])
    case("hook silent: entry in user settings", {"model": "claude-opus-6"}, {}, False)
    settings(user_file, [])
    settings(proj_file, ["claude-opus-6"])
    case("hook silent: entry in project settings", {"model": "claude-opus-6"}, {}, False)
    proj_file.unlink()
    settings(local_file, ["claude-opus-6"])
    case("hook silent: entry in local settings", {"model": "claude-opus-6"}, {}, False)
    case("hook ignores a [1m] suffix", {"model": "claude-opus-6[1m]"}, {}, False)
    case("hook still warns for another ID", {"model": "claude-sonnet-6"}, {}, True)
    case("hook silent for a non-split model", {"model": "claude-haiku-5"}, {}, False)
    case("hook silent when disabled", {"model": "claude-sonnet-6"},
         {"CLAUDE_SETUP_EFFORT_DRIFT": "off"}, False)
    case("hook silent: no model and no env IDs", {}, {}, False)
    case("hook falls back to env IDs", {},
         {"ANTHROPIC_DEFAULT_SONNET_MODEL": "claude-sonnet-6"}, True, "claude-sonnet-6")
    case("hook env fallback silent when saved", {},
         {"ANTHROPIC_DEFAULT_OPUS_MODEL": "claude-opus-6"}, False)

    # The real entry point: stdin in, a systemMessage JSON out, exit 0.
    env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home),
           "CLAUDE_PROJECT_DIR": str(project)}
    env.pop("CLAUDE_SETUP_EFFORT_DRIFT", None)
    run = subprocess.run([sys.executable, "-I", str(ROOT / HOOK)],
                         input=json.dumps({"model": "claude-sonnet-6"}),
                         capture_output=True, text=True, env=env)
    try:
        out = json.loads(run.stdout)
        ok = run.returncode == 0 and "systemMessage" in out
    except ValueError:
        ok = False
    cases.append(("hook process: systemMessage JSON, exit 0", ok, run.stdout.strip()))
    run = subprocess.run([sys.executable, "-I", str(ROOT / HOOK)],
                         input="not json", capture_output=True, text=True, env=env)
    cases.append(("hook process: bad stdin is harmless",
                  run.returncode == 0 and not run.stdout.strip(), run.stdout.strip()))
    return cases


def main():
    fails = 0

    real = check(ROOT)
    expected = [f for f in real if f.startswith(EXPECTED_PENDING)]
    other = [f for f in real if f not in expected]
    print("Real tree:")
    for f in expected:
        print(f"  EXPECTED until the branches join: {f}")
    for f in other:
        print(f"  FAIL  {f}")
    if not real:
        print("  clean")
    fails += bool(real)
    if not plugin_source_present(ROOT):
        print(f"  SKIPPED K1 plugin-source cross-check: {FOLDS_HOOKS} is not on "
              "this branch; run again after the join")

    print("\nChecks can fail:")
    for name, mutate, want in MUTATIONS:
        with tempfile.TemporaryDirectory() as tmp:
            tree = pathlib.Path(tmp)
            copy_tree(tree)
            clean = check(tree)
            if clean:
                ok, detail = False, f"baseline not clean: {clean}"
            else:
                mutate(tree)
                got = check(tree)
                ok = any(want in f for f in got)
                detail = "fired" if ok else f"DID NOT FIRE (got: {got or 'nothing'})"
        print(f"  {'PASS' if ok else 'FAIL'}  {name:28} {detail}")
        fails += not ok

    print("\nSessionStart hook:")
    with tempfile.TemporaryDirectory() as tmp:
        for name, ok, detail in hook_cases(pathlib.Path(tmp)):
            print(f"  {'PASS' if ok else 'FAIL'}  {name:42} {detail[:60]}")
            fails += not ok

    print(f"\n{'FAILED' if fails else 'OK'}: {fails} failing group(s)"
          f" ({len(expected)} expected artifacts-plugin finding(s))")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
