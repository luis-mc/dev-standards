#!/usr/bin/env python3
"""Find the commits that still need cloud shards, and post their results as commit statuses (CI option c, DL15). STARTER.

    cloud_status.py pending [--root DIR] [--remote origin]
    cloud_status.py post --result FILE [--sha SHA] [--repo OWNER/NAME] [--token-env NAME]
    cloud_status.py post-ready --sha SHA [--root DIR] [--remote origin]

STARTER: the small, tested version of the contract in docs/features/delivery/spec.md (section 13). A project may
replace it with a proven one that keeps the same context names, states and the same-sha rule.

pending     The watcher routine runs this with plain git. It lists the heads of the branches in
            `ci.cloud.branches` (globs) and, for each, the cloud shards that have no result branch
            `<prefix>/<sha>/<shard id>` yet. Prints a JSON list: [{"branch", "sha", "missing": [shard ids]}].
            A shard counts as cloud when `ci.options[<its os>]` is `cloud` in .delivery/config.json.
post        Posts ONE result as a commit status: POST /repos/{owner}/{repo}/statuses/{sha} with
            context = the shard's context, state success|failure|error, a short description. It refuses
            (exit 1) when the result's sha is not --sha, so a status is only ever for the sha the shard ran on.
post-ready  Reads the result branches of one sha and posts each one.

The token is read from the environment variable named by `ci.cloud.status_token_env` (or --token-env). It is a
statuses-only token the owner creates. It is never written to a file and never printed. The API base is
https://api.github.com; DELIVERY_GITHUB_API replaces it for tests and may be plain http only on 127.0.0.1.
This script uses no GitHub Actions and no webhook, and calls no other GitHub endpoint.
Exit 0 done, 1 refused (sha mismatch, bad result), 2 error (config, token, network). Standard library only.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

API_DEFAULT = "https://api.github.com"
STATE_OF = {"success": "success", "failure": "failure", "error": "error"}
FULL_SHA = re.compile(r"[0-9a-f]{40}")


def git(*args, cwd="."):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)


def read_config(root: str) -> dict:
    try:
        with open(os.path.join(root, ".delivery", "config.json"), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def cloud_settings(cfg: dict) -> dict:
    ci = cfg.get("ci") if isinstance(cfg.get("ci"), dict) else {}
    cloud = ci.get("cloud") if isinstance(ci.get("cloud"), dict) else {}
    opts = ci.get("options") if isinstance(ci.get("options"), dict) else {}
    return {"oses": {o for o, v in opts.items() if v == "cloud"},
            "table": ci.get("shard_table") if isinstance(ci.get("shard_table"), str) else "scripts/delivery/ci-shards.json",
            "branches": [b for b in cloud.get("branches", []) if isinstance(b, str)] if isinstance(cloud.get("branches"), list) else [],
            "prefix": cloud.get("results_prefix") if isinstance(cloud.get("results_prefix"), str) and cloud.get("results_prefix") else "ci-result",
            "repo": cloud.get("repo") if isinstance(cloud.get("repo"), str) else "",
            "token_env": cloud.get("status_token_env") if isinstance(cloud.get("status_token_env"), str) else ""}


def cloud_shards(root: str, st: dict) -> list:
    with open(os.path.join(root, *st["table"].split("/")), encoding="utf-8") as f:
        table = json.load(f)
    return [s["id"] for s in table.get("shards", []) if isinstance(s, dict) and s.get("os") in st["oses"] and isinstance(s.get("id"), str)]


def ls_remote(root: str, remote: str, pattern: str) -> dict:
    """{ref name: sha} for refs/heads/<pattern>."""
    r = git("ls-remote", "--heads", remote, "refs/heads/" + pattern, cwd=root)
    if r.returncode:
        raise RuntimeError("git ls-remote failed: %s" % r.stderr.strip())
    out = {}
    for line in r.stdout.splitlines():
        sha, _, ref = line.partition("\t")
        if ref.startswith("refs/heads/"):
            out[ref[len("refs/heads/"):]] = sha
    return out


def pending(root: str, remote: str) -> list:
    st = cloud_settings(read_config(root))
    if not st["oses"]:
        return []
    if not st["branches"]:
        raise ValueError("ci.cloud.branches is empty")
    shards = cloud_shards(root, st)
    heads = {b: s for b, s in ls_remote(root, remote, "*").items()
             if not b.startswith(st["prefix"] + "/") and any(fnmatch.fnmatch(b, g) for g in st["branches"])}
    done = set(ls_remote(root, remote, st["prefix"] + "/*"))
    out = []
    for branch, sha in sorted(heads.items()):
        missing = [s for s in shards if "%s/%s/%s" % (st["prefix"], sha, s) not in done]
        if missing:
            out.append({"branch": branch, "sha": sha, "missing": missing})
    return out


def status_payload(result: dict, sha: str | None):
    """(sha, body) for one result, or raises ValueError when it must not be posted."""
    rsha = result.get("sha")
    if not isinstance(rsha, str) or not FULL_SHA.fullmatch(rsha):
        raise ValueError("the result has no full sha")
    if sha and sha.lower() != rsha:
        raise ValueError("the result ran on %s, not %s: no status is posted" % (rsha[:10], sha[:10]))
    state = STATE_OF.get(result.get("state"))
    ctx = result.get("context") or result.get("shard")
    if state is None or not isinstance(ctx, str) or not ctx.strip():
        raise ValueError("the result has no usable state and context")
    desc = str(result.get("summary") or result.get("state"))[:140]
    return rsha, {"state": state, "context": ctx, "description": desc}


def api_base() -> str:
    base = os.environ.get("DELIVERY_GITHUB_API", API_DEFAULT).rstrip("/")
    host = urllib.parse.urlparse(base)
    if host.scheme != "https" and not (host.scheme == "http" and host.hostname in ("127.0.0.1", "localhost")):
        raise ValueError("the API base must be https (plain http only for 127.0.0.1)")
    return base


def post_status(repo: str, sha: str, body: dict, token: str) -> int:
    if not re.fullmatch(r"[^/\s]+/[^/\s]+", repo):
        raise ValueError("--repo must be OWNER/NAME")
    url = "%s/repos/%s/statuses/%s" % (api_base(), repo, sha)
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST", headers={
        "Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
        "Content-Type": "application/json", "User-Agent": "luismc-delivery-cloud-status"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status


def token_from(env_name: str):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", env_name or ""):
        raise ValueError("no token variable name (set ci.cloud.status_token_env or --token-env)")
    token = os.environ.get(env_name, "")
    if not token:
        raise ValueError("the environment variable %s is empty" % env_name)
    return token


def results_for(root: str, remote: str, prefix: str, sha: str) -> list:
    """The result dicts pushed for one sha (plain git: ls-remote, fetch, show)."""
    refs = ls_remote(root, remote, "%s/%s/*" % (prefix, sha))
    out = []
    for branch in sorted(refs):
        ref = "refs/ci-fetched/" + branch
        if git("fetch", "-q", remote, "+refs/heads/%s:%s" % (branch, ref), cwd=root).returncode:
            continue
        shown = git("show", ref + ":result.json", cwd=root)
        if shown.returncode == 0:
            try:
                out.append(json.loads(shown.stdout))
            except ValueError:
                pass
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="cloud_status.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("action", choices=["pending", "post", "post-ready"])
    ap.add_argument("--root", default=".")
    ap.add_argument("--remote", default="origin")
    ap.add_argument("--result")
    ap.add_argument("--sha")
    ap.add_argument("--repo")
    ap.add_argument("--token-env")
    args = ap.parse_args(argv)
    root = os.path.abspath(args.root)
    st = cloud_settings(read_config(root))
    try:
        if args.action == "pending":
            print(json.dumps(pending(root, args.remote)))
            return 0
        repo, env_name = args.repo or st["repo"], args.token_env or st["token_env"]
        if args.action == "post":
            if not args.result:
                print("cloud_status: post needs --result", file=sys.stderr)
                return 2
            with open(args.result, encoding="utf-8") as f:
                results = [json.load(f)]
        else:
            if not args.sha or not FULL_SHA.fullmatch(args.sha.lower()):
                print("cloud_status: post-ready needs --sha with all 40 characters", file=sys.stderr)
                return 2
            results = results_for(root, args.remote, st["prefix"], args.sha.lower())
        refused = posted = 0
        for res in results:
            try:
                sha, body = status_payload(res, args.sha)
            except ValueError as exc:
                print("cloud_status: refused: %s" % exc, file=sys.stderr)
                refused += 1
                continue
            post_status(repo, sha, body, token_from(env_name))
            print("cloud_status: posted %s=%s on %s" % (body["context"], body["state"], sha[:10]))
            posted += 1
        return 1 if refused else 0
    except (ValueError, RuntimeError, OSError, urllib.error.URLError) as exc:
        print("cloud_status: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
