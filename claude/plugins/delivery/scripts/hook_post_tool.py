#!/usr/bin/env python3
"""PostToolUse / PostToolUseFailure recorder and UserPromptSubmit answer marker.

DELIVERYSPEC section 2 "Who writes each field". Reads the hook JSON from stdin and writes
the ledger (.delivery/ledger.json) through delivery_ledger. It only records: it never blocks,
prints nothing, exits 0 always (every error is one line on stderr), and is a no-op in a
repository without a .delivery/ folder. Standard library only.

Recorded:
  Bash   git push of a train branch (pushed), gh pr create / ready (pr, ci), gh pr merge
         (merged), msiexec / schtasks UpdateNow (installs), ci_watch.py (red on failure; green is set only by the watcher)
  Agent, RemoteTrigger create|run   an agents[] row; a fenced ```delivery block in the prompt
         gives task, branch, owns and the eta breakdown (setup, work, checks)
  Artifact publish   publishes[]
  AskUserQuestion    owner_questions[]; the next UserPromptSubmit marks them answered
  UserPromptSubmit   owner_prompt {at, session, asked_for_questions} (Q-5 reads it)

Disable: CLAUDE_DELIVERY_HOOKS=off.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import delivery_ledger as L  # noqa: E402

DEFAULT_TRAIN_RE = r"^release/\d+[a-z]?$"
FENCE_RE = re.compile(r"```delivery[ \t]*\r?\n(.*?)```", re.S)
PR_URL_RE = re.compile(r"/pull/(\d+)")
ARTIFACT_URL_RE = re.compile(r"https://claude\.ai/(?:code/)?artifact/[\w-]+")
TOOL_ERR_RE = re.compile(r"Exit code (\d+)")


def warn(msg: str) -> None:
    try:
        print("luismc-delivery: " + msg.replace("\n", " "), file=sys.stderr)
    except Exception:  # noqa: BLE001
        pass


# --- parsing helpers ---------------------------------------------------------------------

def parse_delivery_block(text: str) -> dict:
    """The first fenced ```delivery block as a dict. Lines are `key: value`:
    task, branch, where, model, effort, basis, owns (comma list), setup/work/checks (minutes),
    total (minutes, default setup+work+checks)."""
    m = FENCE_RE.search(text or "")
    if not m:
        return {}
    raw = {}
    for line in m.group(1).splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip():
            raw[key.strip().lower()] = value.strip()
    out: dict = {}
    for k in ("task", "branch", "where", "model", "effort", "basis"):
        if raw.get(k):
            out[k] = raw[k]
    if raw.get("owns"):
        out["owns"] = [g.strip() for g in re.split(r"[,\s]+", raw["owns"]) if g.strip()]
    br = {}
    for k in ("setup", "work", "checks"):
        try:
            br[k] = float(raw[k]) if k in raw else None
        except ValueError:
            br[k] = None
    br = {k: v for k, v in br.items() if v is not None}
    if br:
        out["breakdown"] = br
        try:
            out["total_min"] = float(raw["total"]) if "total" in raw else sum(br.values())
        except ValueError:
            out["total_min"] = sum(br.values())
    return out


def find_strings(obj, limit: int = 200):
    """Every string in a nested structure (depth-first, bounded)."""
    stack, n = [obj], 0
    while stack and n < limit:
        cur = stack.pop()
        if isinstance(cur, str):
            n += 1
            yield cur
        elif isinstance(cur, dict):
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)


def response_text(data: dict) -> str:
    resp = data.get("tool_response")
    if resp is None:
        resp = data.get("error", "")
    if isinstance(resp, str):
        return resp
    return "\n".join(find_strings(resp))


def split_commands(command: str) -> list[list[str]]:
    """Each simple command in a shell line as an argv list (best effort)."""
    out = []
    for part in re.split(r"&&|\|\||;|\n|\|", command or ""):
        try:
            argv = shlex.split(part, posix=True)
        except ValueError:
            argv = part.split()
        while argv and re.match(r"^\w+=", argv[0]):  # env prefix
            argv.pop(0)
        if argv:
            out.append(argv)
    return out


def _is_abs(d: str) -> bool:
    return os.path.isabs(d) or bool(re.match(r"^[A-Za-z]:[\\/]", d)) or d.startswith("/")


def _cd_target(part: str, cwd: str | None) -> str | None:
    """The directory a `cd <dir>` part moves to, or None when the part is not a cd."""
    words = part.strip().split(None, 1)
    if len(words) != 2 or words[0] != "cd":
        return None
    d = words[1].strip().strip("\"'")
    if d.startswith("/d "):
        d = d[3:].strip().strip("\"'")
    if not d or d == "-":
        return None
    return os.path.normpath(os.path.join(cwd, d)) if cwd and not _is_abs(d) else d


def split_commands_cwd(command: str, cwd: str | None) -> list[tuple[list[str], str | None]]:
    """Each simple command with the directory it runs in: `cd <dir> && ...` and `git -C <dir> ...` move it."""
    out = []
    cur = cwd
    for part in re.split(r"&&|\|\||;|\n|\|", command or ""):
        moved = _cd_target(part, cur)
        if moved is not None:
            cur = moved
            continue
        for argv in split_commands(part):
            where = cur
            if os.path.basename(argv[0]) in ("git", "git.exe") and "-C" in argv[1:3]:
                i = argv.index("-C")
                if i + 1 < len(argv):
                    d = argv[i + 1]
                    where = os.path.normpath(os.path.join(cur, d)) if cur and not _is_abs(d) else d
                    argv = argv[:i] + argv[i + 2:]
            out.append((argv, where))
    return out


def rev_parse(ref: str, cwd: str | None) -> str | None:
    try:
        p = subprocess.run(["git", "rev-parse", "--verify", "--quiet", ref], cwd=cwd or None,
                           capture_output=True, text=True, timeout=5)
        out = p.stdout.strip()
        return out if p.returncode == 0 and re.fullmatch(r"[0-9a-f]{7,64}", out) else None
    except Exception:  # noqa: BLE001
        return None


def opt_value(argv: list[str], *names: str) -> str | None:
    for i, a in enumerate(argv):
        for n in names:
            if a == n and i + 1 < len(argv):
                return argv[i + 1]
            if a.startswith(n + "="):
                return a.split("=", 1)[1]
    return None


def current_branch(cwd: str | None) -> str | None:
    try:
        p = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd or None,
                           capture_output=True, text=True, timeout=5)
        return p.stdout.strip() or None if p.returncode == 0 else None
    except Exception:  # noqa: BLE001
        return None


def pr_number(argv: list[str]) -> int | None:
    for a in argv[3:]:
        if a.isdigit():
            return int(a)
        m = PR_URL_RE.search(a)
        if m:
            return int(m.group(1))
    return None


# --- recorders (each mutates the ledger dict inside one update) -----------------------------

def is_train_branch(led: dict, cfg: dict, branch: str | None) -> bool:
    if not branch:
        return False
    if L.find_train(led, branch=branch):
        return True
    return bool(re.search(cfg.get("train_branch_re") or DEFAULT_TRAIN_RE, branch))


def rec_bash(led, data, cfg, failed: bool, now: str) -> None:
    inp = data.get("tool_input") or {}
    command = inp.get("command") or ""
    text = response_text(data)
    code_m = TOOL_ERR_RE.search(text) if failed else None
    exit_code = int(code_m.group(1)) if code_m else (1 if failed else 0)
    for argv, cwd in split_commands_cwd(command, data.get("cwd")):
        prog = os.path.basename(argv[0])
        if prog in ("git", "git.exe") and "push" in argv[:3]:
            _rec_push(led, cfg, argv, cwd, failed, now)
        elif prog in ("gh", "gh.exe") and argv[1:2] == ["pr"] and len(argv) > 2:
            _rec_gh_pr(led, cfg, argv, text, cwd, failed, now)
        elif prog in ("msiexec", "msiexec.exe") or (prog.startswith("schtasks") and "UpdateNow" in command):
            _rec_install(led, argv, command, exit_code, now)
        elif any(os.path.basename(a) == "ci_watch.py" for a in argv[:3]):
            if not inp.get("run_in_background"):    # a backgrounded start has not finished: nothing to record
                _rec_ci_watch(led, argv, exit_code, now, text)


def _rec_push(led, cfg, argv, cwd, failed, now):
    args = [a for a in argv[argv.index("push") + 1:] if not a.startswith("-")]
    branches = []
    for a in args[1:]:  # args[0] is the remote
        branches.append(a.split(":")[-1].replace("refs/heads/", "").lstrip("+"))
    if not branches:
        cur = current_branch(cwd)
        branches = [cur] if cur else []
    for b in branches:
        if not is_train_branch(led, cfg, b):
            continue
        t = L.find_train(led, branch=b)
        if t is None:
            continue
        if failed:
            L.add_event(led, "push.failed", t["id"], "hook_post_tool", now)
            continue
        if t.get("pr") and t.get("state") not in ("merged", "live", "cleaned"):
            # a fix-forward push to a release branch that already has its PR: CI starts over on the new head
            ci = t.setdefault("ci", {})
            sha = rev_parse(b, cwd)
            if sha:
                ci["head_sha"] = sha
            ci["state"] = "queued"
            ci["run_ids"] = []
            ci["started_at"] = None
            t["green_at"] = None
            t["pushed_at"] = now
            L.set_train_state(t, "ci", now)
            L.add_event(led, "train.repushed", t["id"], "hook_post_tool", now)
            continue
        L.set_train_state(t, "pushed", now)
        t["pushed_at"] = now
        L.add_event(led, "train.pushed", t["id"], "hook_post_tool", now)


def _rec_gh_pr(led, cfg, argv, text, cwd, failed, now):
    verb = argv[2]
    if verb in ("create", "ready"):
        branch = opt_value(argv, "--head", "-H") if verb == "create" else None
        if branch and ":" in branch:        # owner:branch
            branch = branch.split(":", 1)[1]
        num = None
        m = PR_URL_RE.search(text)
        if m:
            num = int(m.group(1))
        elif verb == "ready":
            num = pr_number(argv)
        t = None
        if num is not None:
            t = L.find_train(led, pr=num)
        if t is None:
            br = branch or current_branch(cwd)
            t = L.find_train(led, branch=br) if br else None
        if t is None and not failed and verb == "create" and num is not None:
            br = branch or current_branch(cwd)
            if br and re.search(cfg.get("train_branch_re") or DEFAULT_TRAIN_RE, br):
                t = L.new_train(led, br, cfg=cfg)       # a release PR opened before any train was planned
                sha = rev_parse(br, cwd)
                if sha:
                    t["ci"]["head_sha"] = sha
        if t is None or failed:
            if failed and t is not None:
                L.add_event(led, "pr.%s.failed" % verb, t["id"], "hook_post_tool", now)
            return
        if num is not None:
            t["pr"] = num
        if verb == "create" and not (t.get("ci") or {}).get("head_sha"):
            sha = rev_parse(t["branch"], cwd)
            if sha:
                t.setdefault("ci", {})["head_sha"] = sha
        if verb == "ready" or "--draft" not in argv:
            if t.get("state") in ("planned", "joining", "joined", "pushed"):
                L.set_train_state(t, "ci", now)
        L.add_event(led, "pr.%s" % verb, t["id"], "hook_post_tool", now)
    elif verb == "merge":
        num = pr_number(argv)
        t = L.find_train(led, pr=num) if num is not None else None
        if t is None:
            return
        if failed:
            L.add_event(led, "merge.failed", t["id"], "hook_post_tool", now)
            return
        L.set_train_state(t, "merged", now)
        L.add_event(led, "train.merged", t["id"], "hook_post_tool", now)


def _rec_install(led, argv, command, exit_code, now):
    if "msiexec" in command.lower():
        m = re.search(r"([\w.\-]+?)(?:[-_ ]?([\d.]{3,}))?\.msi", command)
        product, version, via = (m.group(1) if m else "msi"), (m.group(2) if m else None), "msiexec"
    else:
        m = re.search(r"(\w+?)UpdateNow", command)
        product, version, via = (m.group(1).lower() if m else "unknown"), None, "schtasks UpdateNow"
    state = "failed" if exit_code else ("installing" if via != "msiexec" else "done")
    row = {"product": product, "version": version, "via": via, "state": state,
           "started": now, "ended": now if state in ("done", "failed") else None, "log": None}
    led["installs"].append(row)
    L.add_event(led, "install.%s" % state, product, "hook_post_tool", now)


def _rec_ci_watch(led, argv, exit_code, now, text=""):
    """ci_watch.py result. A pass never turns a train green here: ci_watch.py can pass on one workflow while another
    required one still runs (RELEASE-41), so only delivery_watch.py, which reads every required workflow of the
    head commit, sets green. A failure is safe to record at once. The train is found by head SHA only."""
    if exit_code == 0 and not re.search(r"\bsucceeded\b", text or ""):   # empty or partial output: it did not finish
        return
    sha = next((a for a in argv[2:] if re.fullmatch(r"[0-9a-fA-F]{7,40}", a)), None)
    if not sha:
        return
    t = next((x for x in led["trains"] if (x.get("ci") or {}).get("head_sha", "") and
              x["ci"]["head_sha"].startswith(sha[:7])), None)
    if t is None:                       # another repository's sha, or a head no train has: record nothing but the event
        L.add_event(led, "ci_watch.no_train", sha[:7], "hook_post_tool", now)
        return
    if exit_code == 0:
        L.add_event(led, "ci_watch.passed", t["id"], "hook_post_tool", now)
    elif exit_code == 1:
        t["ci"]["state"] = "failure"
        L.set_train_state(t, "red", now)
        L.add_event(led, "ci.failure", t["id"], "hook_post_tool", now)
    else:
        L.add_event(led, "ci_watch.exit%d" % exit_code, t["id"], "hook_post_tool", now)


def rec_agent(led, data, cfg, now, where="local") -> None:
    inp = data.get("tool_input") or {}
    if where == "cloud":
        action = str(inp.get("action") or "").lower()
        if action not in ("create", "run"):
            return
        prompt = "\n".join(s for s in find_strings(inp) if "```delivery" in s) or "\n".join(find_strings(inp))
    else:
        prompt = inp.get("prompt") or ""
    blk = parse_delivery_block(prompt)
    text = response_text(data)
    ident = None
    resp = data.get("tool_response")
    if isinstance(resp, dict):
        for k in ("agentId", "agent_id", "trigger_id", "id", "session_id"):
            if isinstance(resp.get(k), str):
                ident = resp[k]
                break
    if ident is None:
        m = re.search(r"\b(trig_\w+|agent[_-]?id[:= ]+\w+|cse_\w+)", text)
        ident = m.group(1) if m else None
    bd = blk.get("breakdown") or {}
    eta = None
    if bd:
        due = None
        start = L.parse_iso(now)
        if start and blk.get("total_min") is not None:
            from datetime import timedelta
            due = L.iso(start + timedelta(minutes=blk["total_min"]))
        eta = {"total_min": blk.get("total_min"), "breakdown": bd, "basis": blk.get("basis"), "due": due}
    elif cfg.get("eta_required", True):
        L.add_event(led, "agent.no_eta", str(blk.get("task") or inp.get("description") or ""), "hook_post_tool", now)
    row = {
        "task": blk.get("task") or None, "where": blk.get("where") or where, "id": ident, "session": None,
        "launched_by": data.get("session_id") or None,
        "branch": blk.get("branch"), "base_sha": None, "head_sha": None, "owns": blk.get("owns", []),
        "model": blk.get("model") or inp.get("model"), "effort": blk.get("effort"), "started": now, "eta": eta,
        "log_path": None, "last_checked": None, "last_activity": now,
        "state": "running" if inp.get("run_in_background") or where == "cloud" else "done",
    }
    if where == "local" and not inp.get("run_in_background"):
        row["state"] = "done"  # a foreground Agent finished inside the call
    led["agents"].append(row)
    L.add_event(led, "agent.%s" % row["state"], str(row["task"] or ident or ""), "hook_post_tool", now)


def rec_artifact(led, data, cfg, now) -> None:
    inp = data.get("tool_input") or {}
    action = str(inp.get("action") or "publish").lower()
    if action != "publish" or inp.get("asset"):
        return
    text = response_text(data)
    m = ARTIFACT_URL_RE.search(text)
    url = m.group(0) if m else inp.get("url")
    title = None
    fp = inp.get("file_path") or ""
    if fp:
        title = Path(fp).stem
    name = title or (url or "artifact")
    vm = re.search(r"version[\"'\s:=]+(\d+)", text, re.I)
    row = next((p for p in led["publishes"] if (url and p.get("url") == url) or p.get("artifact") == name), None)
    if row is None:
        row = {"artifact": name, "url": url, "last_at": None, "last_version": None,
               "last_state_hash": None, "copy_written_at": None}
        led["publishes"].append(row)
    row["url"] = url or row.get("url")
    row["last_at"] = now
    if vm:
        row["last_version"] = int(vm.group(1))
    L.add_event(led, "publish", name, "hook_post_tool", now)


def rec_question(led, data, cfg, now) -> None:
    inp = data.get("tool_input") or {}
    qs = inp.get("questions")
    texts = []
    if isinstance(qs, list):
        for q in qs:
            t = q.get("question") if isinstance(q, dict) else q
            if isinstance(t, str) and t.strip():
                texts.append(t.strip())
    elif isinstance(inp.get("question"), str):
        texts.append(inp["question"])
    for t in texts:
        nums = [int(q["id"][1:]) for q in led["owner_questions"] if re.fullmatch(r"Q\d+", str(q.get("id", "")))]
        led["owner_questions"].append({"id": "Q%d" % (max(nums, default=0) + 1), "text": t,
                                       "asked_at": now, "answered_at": None, "blocks": []})
    if texts:
        L.add_event(led, "owner.asked", "%d" % len(texts), "hook_post_tool", now)


ASK_QUESTIONS_RE = re.compile(r"\bask\s+(?:me|us)\b[^.\n]{0,30}\bquestions?\b|\bask\s+(?:me\s+)?question", re.I)


def rec_prompt(led, prompt, session, now) -> None:
    """The owner's latest prompt: when, and whether it asked for questions (Q-5 allows a dialog then)."""
    led["owner_prompt"] = {"at": now, "session": session or None,
                           "asked_for_questions": bool(ASK_QUESTIONS_RE.search(prompt))}


def mark_answered(led, now) -> int:
    n = 0
    for q in led["owner_questions"]:
        if not q.get("answered_at"):
            q["answered_at"] = now
            n += 1
    if n:
        L.add_event(led, "owner.answered", "%d" % n, "hook_post_tool", now)
    return n


# --- dispatch -----------------------------------------------------------------------------

def handle(data: dict, root=None) -> bool:
    """Apply one hook payload. Returns True when the ledger was written."""
    event = data.get("hook_event_name") or ""
    tool = data.get("tool_name") or ""
    root = root or L.find_root(data.get("cwd"))
    if root is None or not (Path(root) / L.DIR_NAME).is_dir():
        return False
    cfg = L.load_config(root)
    failed = event == "PostToolUseFailure"
    now = L.iso()

    if event == "UserPromptSubmit":
        prompt = data.get("prompt") if isinstance(data.get("prompt"), str) else ""

        def on_prompt(led):
            rec_prompt(led, prompt, data.get("session_id"), now)
            mark_answered(led, now)
        L.update(root, on_prompt)
        return True

    def fn(led):
        if tool == "Bash":
            rec_bash(led, data, cfg, failed, now)
        elif failed:
            L.add_event(led, "tool.failed", tool, "hook_post_tool", now)
        elif tool in ("Agent", "Task"):
            rec_agent(led, data, cfg, now, "local")
        elif tool == "RemoteTrigger":
            rec_agent(led, data, cfg, now, "cloud")
        elif tool == "Artifact":
            rec_artifact(led, data, cfg, now)
        elif tool == "AskUserQuestion":
            rec_question(led, data, cfg, now)

    if tool not in ("Bash", "Agent", "Task", "RemoteTrigger", "Artifact", "AskUserQuestion"):
        return False
    L.update(root, fn, wait=3)
    return True


def main() -> int:
    if os.environ.get("CLAUDE_DELIVERY_HOOKS", "on").strip().lower() in ("off", "0", "false", "no"):
        return 0
    try:
        text = sys.stdin.buffer.read().decode("utf-8", "replace")
        data = json.loads(text) if text.strip() else {}
        if isinstance(data, dict):
            handle(data)
    except Exception as exc:  # noqa: BLE001 - a recorder never fails the tool call
        warn("recorder error: %s" % exc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
