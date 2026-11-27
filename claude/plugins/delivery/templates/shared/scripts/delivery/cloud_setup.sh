#!/usr/bin/env bash
# Prepares a cloud session (Claude Code on the web, routines) of a dev-standards project (DS296).
#   a. fetches the pinned dev-standards checkout into .dev-standards-tools (shallow, quiet),
#      from the repository and ref of .github/workflows/dev-standards.yml (the same pin CI uses)
#   b. installs gitleaks at the version and SHA-256 in scripts/delivery/tools.json (fails closed)
#   c. pip installs the project's Python requirements file, when it has one
#   d. prints DEV_STANDARDS_SCRIPTS=<path of the docs scripts>
# Idempotent. Runs only when CLAUDE_CODE_REMOTE=true, or with --force by hand.
# Environment: DELIVERY_BIN (default ~/.local/bin), DELIVERY_GITLEAKS_BASE_URL (mirrors, tests),
# DEV_STANDARDS_FETCH_URL (git URL override, tests). Exit 0 ready, 2 a step failed.
set -uo pipefail

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ] && [ "${1:-}" != "--force" ]; then
  echo "cloud_setup: not a cloud session; nothing to do (use --force to run by hand)" >&2
  exit 0
fi
cd "$here/../.." || exit 2
bin_dir=${DELIVERY_BIN:-$HOME/.local/bin}
tools=.dev-standards-tools
scripts_rel=claude/plugins/docs/scripts
say() { printf 'cloud_setup: %s\n' "$*" >&2; }
py=$(command -v python3 || command -v python) || { say "python not found"; exit 2; }
rc=0

# --- a. the pinned checkout ---------------------------------------------------
wf=.github/workflows/dev-standards.yml
if [ -f "$wf" ]; then
  pin=$("$py" -I - "$wf" <<'PY'
import re, sys
repo = ref = ""
for line in open(sys.argv[1], encoding="utf-8"):
    m = re.match(r"\s*repository:\s*(\S+)", line)
    if m: repo = m.group(1)
    m = re.match(r"\s*ref:\s*([^\s#]+)", line)
    if m and repo and not ref: ref = m.group(1)
print(repo, ref)
PY
)
  repo=${pin% *}; ref=${pin#* }
  if [ -z "$repo" ] || [ -z "$ref" ] || [ "$repo" = "$ref" ]; then
    say "no repository/ref pin in $wf"; rc=2
  elif [ "$(cat "$tools/.ds-ref" 2>/dev/null)" = "$repo@$ref" ] && [ -d "$tools/$scripts_rel" ]; then
    say "dev-standards $ref already fetched"
  else
    url=${DEV_STANDARDS_FETCH_URL:-https://github.com/$repo.git}
    rm -rf "$tools" && mkdir -p "$tools" &&
    git -C "$tools" init -q &&
    git -C "$tools" fetch -q --depth 1 "$url" "$ref" &&
    git -C "$tools" checkout -q FETCH_HEAD &&
    printf '%s' "$repo@$ref" > "$tools/.ds-ref" || { say "could not fetch $repo@$ref"; rc=2; }
  fi
else
  say "$wf not found; run claude-setup to add the dev-standards pin"; rc=2
fi

# --- b. gitleaks ----------------------------------------------------------------
tj="$here/tools.json"
gl=$("$py" -I -c '
import json, sys
g = json.load(open(sys.argv[1]))["gitleaks"]
print("" if isinstance(g, str) else g["version"])' "$tj" 2>/dev/null)
case "$(uname -s)-$(uname -m)" in
  Linux-x86_64|Linux-amd64) plat=linux_x64 ;;
  Linux-aarch64|Linux-arm64) plat=linux_arm64 ;;
  Darwin-x86_64) plat=darwin_x64 ;;
  Darwin-arm64) plat=darwin_arm64 ;;
  *) plat= ;;
esac
sha=$("$py" -I -c '
import json, sys
g = json.load(open(sys.argv[1]))["gitleaks"]
print(g.get("sha256", {}).get(sys.argv[2], "") if isinstance(g, dict) else "")' "$tj" "$plat" 2>/dev/null)
if [ -z "$gl" ] || [ -z "$sha" ]; then
  say "tools.json has no pinned gitleaks SHA-256 for '$plat'; gitleaks not installed"; rc=2
elif PATH="$bin_dir:$PATH" gitleaks version 2>/dev/null | grep -qF "$gl"; then
  say "gitleaks $gl already installed"
else
  base=${DELIVERY_GITLEAKS_BASE_URL:-https://github.com/gitleaks/gitleaks/releases/download/v$gl}
  asset="gitleaks_${gl}_$plat.tar.gz"
  mkdir -p "$bin_dir" && "$py" -I - "$base" "$asset" "$bin_dir" "$sha" <<'PY' || { say "gitleaks $gl NOT installed"; rc=2; }
import hashlib, io, os, sys, tarfile, urllib.request
base, asset, dest, want = sys.argv[1:5]
try:
    with urllib.request.urlopen(base.rstrip("/") + "/" + asset, timeout=120) as r:
        data = r.read()
except Exception as e:
    sys.exit("cloud_setup: download failed: %s" % e)
got = hashlib.sha256(data).hexdigest()
if got != want.lower():
    sys.exit("cloud_setup: checksum mismatch for %s (expected %s, got %s); nothing installed" % (asset, want, got))
with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as t:
    m = t.extractfile("gitleaks")
    if m is None:
        sys.exit("cloud_setup: gitleaks not in archive")
    blob = m.read()
os.makedirs(dest, exist_ok=True)
tmp = os.path.join(dest, "gitleaks.part")
open(tmp, "wb").write(blob)
os.chmod(tmp, 0o755)
os.replace(tmp, os.path.join(dest, "gitleaks"))
print("cloud_setup: gitleaks checksum ok, installed", file=sys.stderr)
PY
fi

# --- c. Python test dependencies --------------------------------------------------
for req in requirements-dev.txt requirements-ci.txt requirements-test.txt requirements.txt; do
  if [ -f "$req" ]; then
    "$py" -m pip install -q -r "$req" >&2 || { say "pip install -r $req failed"; rc=2; }
    break
  fi
done

# --- d. where the scripts are -----------------------------------------------------
echo "DEV_STANDARDS_SCRIPTS=$tools/$scripts_rel"
exit $rc
