#!/usr/bin/env python3
"""DL-117 (DS262): reuse a base image instead of building it on every run.

    image_reuse.py key    [--config .delivery/image-inputs.json] [--root .]
    image_reuse.py exists [--config FILE] --key KEY [--image IMAGE] [--builder-ref REF] [--inspect-cmd CMD]
    image_reuse.py digest [--config FILE] --key KEY [--image IMAGE] [--builder-ref REF] [--inspect-cmd CMD]

The project owns `.delivery/image-inputs.json`:

    {"image": "ghcr.io/OWNER/base",
     "inputs": ["images/linux-base", "images/layers"],
     "tools": {"node": "22.11.0", "go": "1.23.3"},
     "builder_ref": "refs/heads/main"}

`key` prints the SHA-256 of every file under the `inputs` paths (path and content, in path order) and of the
pinned `tools`. Change one byte of an input or one tool version and the key changes. No `inputs`, or a path that
matches no file, means NO key (exit 3): the image is always built.

`exists` asks the registry whether the tag `<image>:<key>` exists. `digest` prints the digest to pin
(`<image>@sha256:...`). Both go through the inspect command, `docker buildx imagetools inspect` by default;
`--inspect-cmd` or $IMAGE_REUSE_INSPECT replaces it (tests use a fake). A reused image counts only when main
built it: the build step writes the label `org.dev-standards.builder-ref` (see LABEL), and with `--builder-ref`
(default: `builder_ref` of the config) a tag whose label differs is a miss. A registry error is a miss, never
a pass.

Exit: 0 hit (key printed, exists, digest printed); 1 miss; 2 bad input; 3 no key.
Python 3.8+, standard library only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

SCHEMA = 1
LABEL = "org.dev-standards.builder-ref"
DEFAULT_CONFIG = ".delivery/image-inputs.json"
DEFAULT_INSPECT = "docker buildx imagetools inspect"


def load_config(path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("%s: expected an object" % path)
    inputs = data.get("inputs")
    if inputs is not None and not (isinstance(inputs, list) and all(isinstance(p, str) and p for p in inputs)):
        raise ValueError("%s: `inputs` must be a list of paths" % path)
    tools = data.get("tools", {})
    if not isinstance(tools, dict):
        raise ValueError("%s: `tools` must be an object" % path)
    return data


def input_files(root: Path, inputs: list) -> list:
    """Sorted relative paths of every file under the input paths (a file or a folder); [] when none."""
    found = set()
    for p in inputs:
        base = root / p
        if base.is_file():
            found.add(Path(p).as_posix())
        elif base.is_dir():
            for f in base.rglob("*"):
                if f.is_file():
                    found.add(f.relative_to(root).as_posix())
    return sorted(found)


def compute_key(root: Path, cfg: dict):
    """(key, reason). The key is None, with the reason, when the image has no declared inputs."""
    inputs = cfg.get("inputs")
    if not inputs:
        return None, "no `inputs` listed, so the image is always built"
    files = input_files(root, inputs)
    if not files:
        return None, "the input paths match no file"
    h = hashlib.sha256()
    h.update(json.dumps({"v": SCHEMA, "tools": cfg.get("tools") or {}}, sort_keys=True,
                        separators=(",", ":")).encode())
    for rel in files:
        h.update(b"\0" + rel.encode() + b"\0")
        h.update(hashlib.sha256((root / rel).read_bytes()).digest())
    return h.hexdigest(), ""


def _run(cmd: list):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as e:
        return 127, "", str(e)
    return p.returncode, p.stdout, p.stderr


def find_labels(node):
    """The first `Labels` object in an inspect result (the key's case differs between tools)."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k.lower() == "labels" and isinstance(v, dict):
                return v
        for v in node.values():
            got = find_labels(v)
            if got is not None:
                return got
    elif isinstance(node, list):
        for v in node:
            got = find_labels(v)
            if got is not None:
                return got
    return None


def lookup(image: str, key: str, inspect_cmd: str, builder_ref=None):
    """(digest or None, why). A hit has a digest and, when builder_ref is given, a label equal to it."""
    base = shlex.split(inspect_cmd)
    tag = "%s:%s" % (image, key)
    rc, out, err = _run(base + [tag, "--format", "{{.Manifest.Digest}}"])
    digest = out.strip()
    if rc != 0 or not digest.startswith("sha256:"):
        return None, "tag %s not found%s" % (tag, (": " + err.strip()[:200]) if err.strip() else "")
    if builder_ref:
        rc, out, err = _run(base + [tag, "--format", "{{json .Image}}"])
        try:
            labels = find_labels(json.loads(out)) if rc == 0 else None
        except ValueError:
            labels = None
        got = (labels or {}).get(LABEL)
        if got != builder_ref:
            return None, "%s was not built by %s (label %s is %r)" % (tag, builder_ref, LABEL, got)
    return digest, ""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("action", choices=["key", "exists", "digest"])
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--root", default=".")
    ap.add_argument("--key")
    ap.add_argument("--image")
    ap.add_argument("--builder-ref")
    ap.add_argument("--inspect-cmd", default=os.environ.get("IMAGE_REUSE_INSPECT", DEFAULT_INSPECT))
    a = ap.parse_args(argv)
    try:
        cfg = load_config(a.config)
    except (OSError, ValueError) as e:
        print("image_reuse: cannot read the config (%s)" % e, file=sys.stderr)
        return 2
    if a.action == "key":
        key, why = compute_key(Path(a.root), cfg)
        print(key if key else "none: " + why)
        return 0 if key else 3
    image = a.image or cfg.get("image")
    if not image or not a.key:
        print("image_reuse: %s needs --key and an image (--image or `image` in the config)" % a.action,
              file=sys.stderr)
        return 2
    digest, why = lookup(image, a.key, a.inspect_cmd, a.builder_ref or cfg.get("builder_ref"))
    if digest is None:
        print("miss: " + why)
        return 1
    print("%s@%s" % (image, digest) if a.action == "digest" else "hit " + digest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
