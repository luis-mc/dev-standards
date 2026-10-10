#!/usr/bin/env bash
# Prepares an agent sandbox (or a fresh machine) to run the branch gate.
# STACKSPEC 13.5: every scanner CI uses is installed here, at the version in
# tools.json, so the gate runs the scanner CI runs.
#
#   1. Python 3.11+            apt-get (root or sudo) or brew; else a message, exit 2
#   2. gitleaks (tools.json)   release archive for this OS/arch, SHA-256 checked
#                              against the release's checksums file, installed
#                              into $DELIVERY_BIN (default ~/.local/bin)
#   3. git hooks               core.hooksPath -> .githooks, if unset
#   4. gate.json "setup"       each command, from the repository root
#
# Idempotent: a step already satisfied is skipped. Environment:
#   DELIVERY_BIN                  install directory for downloaded tools
#   DELIVERY_GITLEAKS_BASE_URL    release download base URL (mirrors, tests)
#   DELIVERY_DRY_RUN=1            print what would be downloaded, change nothing
#
# Exit: 0 ready, 2 could not prepare the machine.

set -euo pipefail

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
bin_dir=${DELIVERY_BIN:-$HOME/.local/bin}
dry_run=${DELIVERY_DRY_RUN:-}

say() { printf 'agent_setup: %s\n' "$*" >&2; }
die() { say "$*"; exit 2; }

# --- 1. Python 3.11+ -------------------------------------------------------
find_python() {
  local c
  for c in python3 python; do
    if command -v "$c" >/dev/null 2>&1 &&
       "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
      echo "$c"
      return 0
    fi
  done
  return 1
}

sudo_cmd() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  elif command -v sudo >/dev/null 2>&1 && sudo -n true >/dev/null 2>&1; then
    sudo -n "$@"
  else
    return 1
  fi
}

install_python() {
  if command -v apt-get >/dev/null 2>&1 && { [ "$(id -u)" -eq 0 ] || command -v sudo >/dev/null 2>&1; }; then
    say "installing Python with apt-get"
    sudo_cmd apt-get update -y >/dev/null || return 1
    sudo_cmd apt-get install -y python3 >/dev/null || return 1
  elif command -v brew >/dev/null 2>&1; then
    say "installing Python with brew"
    brew install python@3.12 >/dev/null || return 1
  else
    return 1
  fi
}

py=$(find_python || true)
if [ -z "$py" ]; then
  if [ -n "$dry_run" ]; then
    say "dry run: would install Python 3.11+"
    py=python3
  else
    install_python || true
    py=$(find_python || true)
    if [ -z "$py" ]; then
      die "Python 3.11+ is required and could not be installed here.
  Install it yourself (https://www.python.org/downloads/, 'apt-get install python3', or 'brew install python@3.12') and re-run this script."
    fi
  fi
fi
say "python: $("$py" --version 2>&1)"

# --- 2. gitleaks -----------------------------------------------------------
gl_version=$("$py" -I -c 'import json, sys; print(json.load(open(sys.argv[1]))["gitleaks"])' "$here/tools.json") ||
  die "tools.json has no gitleaks version"

case "$(uname -s)" in
  Linux)                os=linux;   ext=tar.gz ;;
  Darwin)               os=darwin;  ext=tar.gz ;;
  MINGW*|MSYS*|CYGWIN*) os=windows; ext=zip ;;
  *) die "unsupported OS '$(uname -s)'; install gitleaks $gl_version manually" ;;
esac
case "$(uname -m)" in
  x86_64|amd64)  arch=x64 ;;
  aarch64|arm64) arch=arm64 ;;
  i386|i686)     arch=x32 ;;
  armv7l|armv7)  arch=armv7 ;;
  armv6l|armv6)  arch=armv6 ;;
  *) die "unsupported CPU '$(uname -m)'; install gitleaks $gl_version manually" ;;
esac
asset="gitleaks_${gl_version}_${os}_${arch}.${ext}"
checksums="gitleaks_${gl_version}_checksums.txt"
base_url=${DELIVERY_GITLEAKS_BASE_URL:-https://github.com/gitleaks/gitleaks/releases/download/v${gl_version}}
if [ "$os" = windows ]; then exe=gitleaks.exe; else exe=gitleaks; fi

if [ -n "$dry_run" ]; then
  say "dry run: would download $base_url/$asset"
  say "dry run: would verify it against $base_url/$checksums"
  say "dry run: would install $exe into $bin_dir"
  echo "$base_url/$asset"
  exit 0
fi

mkdir -p "$bin_dir"
bin_path=$bin_dir
# Git Bash on Windows: a PATH entry must be /c/..., not C:/... (the colon splits it).
if command -v cygpath >/dev/null 2>&1; then bin_path=$(cygpath -u "$bin_dir"); fi
export PATH="$bin_path:$PATH"
if command -v gitleaks >/dev/null 2>&1 && gitleaks version 2>/dev/null | grep -qF "$gl_version"; then
  say "gitleaks $gl_version already installed"
else
  say "installing gitleaks $gl_version into $bin_dir"
  # Download, checksum-verify and extract with Python: one code path for every OS.
  work=$(mktemp -d)
  trap 'rm -rf "$work"' EXIT
  cat > "$work/install_gitleaks.py" <<'PY'
import hashlib, io, os, sys, tarfile, urllib.request, zipfile

base, asset, sums, dest, exe = sys.argv[1:6]

def fetch(name):
    with urllib.request.urlopen(base.rstrip("/") + "/" + name, timeout=120) as r:
        return r.read()

archive = fetch(asset)
want = None
for line in fetch(sums).decode().splitlines():
    parts = line.split()
    if len(parts) == 2 and parts[1].lstrip("*") == asset:
        want = parts[0].lower()
if want is None:
    sys.exit("agent_setup: %s is not listed in %s" % (asset, sums))
got = hashlib.sha256(archive).hexdigest()
if got != want:
    sys.exit("agent_setup: checksum mismatch for %s (expected %s, got %s); nothing installed" % (asset, want, got))

if asset.endswith(".zip"):
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        data = z.read(exe)
else:
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as t:
        member = t.extractfile(exe)
        if member is None:
            sys.exit("agent_setup: %s not found in %s" % (exe, asset))
        data = member.read()

target = os.path.join(dest, exe)
tmp = target + ".part"
with open(tmp, "wb") as f:
    f.write(data)
os.chmod(tmp, 0o755)
os.replace(tmp, target)
print("agent_setup: checksum ok, installed " + target, file=sys.stderr)
PY
  "$py" -I "$work/install_gitleaks.py" "$base_url" "$asset" "$checksums" "$bin_dir" "$exe" ||
    die "could not install gitleaks $gl_version (download or checksum failed)"
fi

# --- 3 and 4: the repository -----------------------------------------------
root=$(git rev-parse --show-toplevel 2>/dev/null || true)
if [ -z "$root" ]; then root=$(cd "$here/../.." && pwd); fi
cd "$root"

if [ -d .githooks ] && [ -z "$(git config --get core.hooksPath 2>/dev/null || true)" ]; then
  git config core.hooksPath .githooks && say "git hooks: core.hooksPath -> .githooks"
fi

setup_cmds=$("$py" -I -c '
import json, sys
for cmd in json.load(open(sys.argv[1])).get("setup", []):
    print(cmd)
' "$here/gate.json")
while IFS= read -r cmd; do
  [ -n "$cmd" ] || continue
  say "setup: $cmd"
  bash -c "$cmd" </dev/null || die "setup command failed: $cmd"
done <<< "$setup_cmds"

say "ready. If gitleaks is not found in new shells, add to PATH:  export PATH=\"$bin_path:\$PATH\""
