#!/usr/bin/env bash
# Prepares an agent sandbox (or a fresh machine) to run the branch gate.
# STACKSPEC 13.5: every scanner CI uses is installed here, at the version in
# tools.json, so the gate runs the scanner CI runs.
#
#   1. Python 3.11+            apt-get (root or sudo) or brew; else a message, exit 2
#   2. gitleaks (tools.json)   release archive for this OS/arch, SHA-256 checked
#                              against the value pinned in tools.json (no pin,
#                              including the old bare-version form: refused),
#                              installed into
#                              $DELIVERY_BIN (default ~/.local/bin)
#   3. git hooks               core.hooksPath -> .githooks, if unset
#   3b. Node                   when package.json has engines.node and the active Node
#                              major does not satisfy it, activate the lowest major
#                              that does (volta, fnm or nvm if present; else the
#                              official tarball, SHA-256 checked against the official
#                              SHASUMS256.txt). No package.json or no engines: skipped.
#   4. gate.json "setup"       each command, from the repository root
#
# Idempotent: a step already satisfied is skipped. Environment:
#   DELIVERY_BIN                  install directory for downloaded tools
#   DELIVERY_GITLEAKS_BASE_URL    release download base URL (mirrors, tests)
#   DELIVERY_NODE_INSTALLER       command run as '<cmd> <major>': installs that Node major
#                                 and prints its bin directory (tests inject it)
#   DELIVERY_NODE_BASE_URL        Node download base URL (default https://nodejs.org/dist)
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
# tools.json: {"gitleaks": {"version": "x.y.z", "sha256": {"linux_x64": "..."}}}, or the
# the old form {"gitleaks": "x.y.z"} has no pin and is refused.
gl_version=$("$py" -I -c '
import json, sys
g = json.load(open(sys.argv[1]))["gitleaks"]
print(g if isinstance(g, str) else g["version"])
' "$here/tools.json") || die "tools.json has no gitleaks version"

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

# The pinned SHA-256 for this platform; empty for the old tools.json form.
gl_sha=$("$py" -I -c '
import json, sys
g = json.load(open(sys.argv[1]))["gitleaks"]
print("" if isinstance(g, str) else g.get("sha256", {}).get(sys.argv[2], ""))
' "$here/tools.json" "${os}_${arch}") || die "tools.json is not valid"
if [ -z "$gl_sha" ]; then
  die "tools.json has no pinned SHA-256 for gitleaks $gl_version (${os}_${arch}); refusing to install. Write the pins with: python3 scripts/delivery/tools_pin.py gitleaks $gl_version"
fi

if [ -n "$dry_run" ]; then
  say "dry run: would download $base_url/$asset"
  say "dry run: would verify it against the SHA-256 pinned in tools.json for ${os}_${arch}"
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

base, asset, sums, dest, exe, pin = sys.argv[1:7]

def fetch(name):
    with urllib.request.urlopen(base.rstrip("/") + "/" + name, timeout=120) as r:
        return r.read()

archive = fetch(asset)
want = pin.lower()
if not want:
    sys.exit("agent_setup: no pinned SHA-256; nothing installed")
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
  "$py" -I "$work/install_gitleaks.py" "$base_url" "$asset" "$checksums" "$bin_dir" "$exe" "$gl_sha" ||
    die "could not install gitleaks $gl_version (download or checksum failed)"
fi

# --- 3 and 4: the repository -----------------------------------------------
root=$(git rev-parse --show-toplevel 2>/dev/null || true)
if [ -z "$root" ]; then root=$(cd "$here/../.." && pwd); fi
cd "$root"

if [ -d .githooks ] && [ -z "$(git config --get core.hooksPath 2>/dev/null || true)" ]; then
  git config core.hooksPath .githooks && say "git hooks: core.hooksPath -> .githooks"
fi

# --- 3b. Node for package.json engines.node ---------------------------------
# Lowest major that satisfies engines.node (">=24 <25" -> 24); empty when there is
# no package.json, no engines.node, or the active Node already satisfies it.
node_wanted=$("$py" -I -c '
import json, re, sys
try:
    rng = json.load(open("package.json"))["engines"]["node"]
except Exception:
    sys.exit(0)
act = int(sys.argv[1] or 0)

def ver(t):
    p = (re.findall(r"\d+", t) + ["0", "0"])[:3]
    return tuple(int(x) for x in p)

def ok(v, comp):
    m = re.match(r"^(>=|<=|>|<|=|\^|~)?\s*v?(\d+|[xX*])?(?:\.(\d+|[xX*]))?(?:\.(\d+|[xX*]))?", comp)
    if not m or m.group(2) in (None, "x", "X", "*"):
        return True
    op, parts = m.group(1) or "=", [m.group(i) for i in (2, 3, 4)]
    n = sum(1 for x in parts if x and x not in "xX*")
    lo = ver(".".join(x for x in parts if x and x not in "xX*"))
    if op == ">=": return v >= lo
    if op == ">":  return v >= (lo[0], lo[1], lo[2] + 1) if n == 3 else v[:n] > lo[:n]
    if op == "<=": return v[:n] <= lo[:n]
    if op == "<":  return v[:n] < lo[:n]
    if op == "^":  return v >= lo and v[0] == lo[0] if lo[0] else v[:2] == lo[:2] and v >= lo
    if op == "~":  return v >= lo and v[:max(n, 1) if n < 2 else 2] == lo[:max(n, 1) if n < 2 else 2]
    return v[:n] == lo[:n]

def sat(v):
    for alt in rng.split("||"):
        comps = re.sub(r"(>=|<=|>|<|=|\^|~)\s+", r"\1", alt.strip()).split()
        if all(ok(v, c) for c in comps):
            return True
    return False

def major_ok(m):
    return any(sat((m, a, b)) for a, b in ((0, 0), (0, 1), (999, 999)))

if major_ok(act):
    sys.exit(0)
for m in range(act + 1 if act else 0, 100):
    if major_ok(m):
        print(m)
        break
' "$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || true)" 2>/dev/null || true)

node_install_default() {  # $1 = major; prints the bin directory
  local m=$1 d
  if command -v volta >/dev/null 2>&1; then
    volta install "node@$m" >&2 && { echo "${VOLTA_HOME:-$HOME/.volta}/bin"; return 0; }
  fi
  if command -v fnm >/dev/null 2>&1; then
    fnm install "$m" >&2 && d=$(fnm exec --using="$m" node -p 'process.execPath' 2>/dev/null) && { dirname "$d"; return 0; }
  fi
  if [ -s "${NVM_DIR:-$HOME/.nvm}/nvm.sh" ]; then
    d=$(bash -c '. "${NVM_DIR:-$HOME/.nvm}/nvm.sh" >/dev/null; nvm install "$1" >&2 && nvm which "$1"' _ "$m") && [ -n "$d" ] && { dirname "$d"; return 0; }
  fi
  node_install_tarball "$m"
}

node_install_tarball() {  # $1 = major; official tarball, SHA-256 from the official SHASUMS256.txt
  local m=$1 plat cpu work
  case "$(uname -s)" in Linux) plat=linux ;; Darwin) plat=darwin ;; *) return 1 ;; esac
  case "$(uname -m)" in x86_64|amd64) cpu=x64 ;; aarch64|arm64) cpu=arm64 ;; *) return 1 ;; esac
  work=$(mktemp -d)
  "$py" -I - "${DELIVERY_NODE_BASE_URL:-https://nodejs.org/dist}" "$m" "$plat-$cpu" "$(dirname "$bin_dir")/node" "$work" <<'PY'
import hashlib, os, re, sys, tarfile, urllib.request
base, major, plat, dest, work = sys.argv[1:6]
base = base.rstrip("/")
def fetch(url):
    with urllib.request.urlopen(url, timeout=300) as r:
        return r.read()
sums = fetch("%s/latest-v%s.x/SHASUMS256.txt" % (base, major)).decode()
m = re.search(r"^([0-9a-f]{64})\s+(node-v(\d+\.\d+\.\d+)-%s\.tar\.xz)$" % re.escape(plat), sums, re.M)
if not m:
    sys.exit("agent_setup: no Node %s tarball for %s in SHASUMS256.txt" % (major, plat))
want, name, full = m.groups()
data = fetch("%s/v%s/%s" % (base, full, name))
if hashlib.sha256(data).hexdigest() != want:
    sys.exit("agent_setup: checksum mismatch for %s; nothing installed" % name)
tmp = os.path.join(work, name)
open(tmp, "wb").write(data)
os.makedirs(dest, exist_ok=True)
with tarfile.open(tmp, "r:xz") as t:
    t.extractall(dest, filter="data")
print(os.path.join(dest, name[:-len(".tar.xz")], "bin"))
PY
  local rc=$?
  rm -rf "$work"
  return $rc
}

if [ -n "$node_wanted" ]; then
  say "node: package.json engines.node needs Node $node_wanted"
  if [ -n "${DELIVERY_NODE_INSTALLER:-}" ]; then
    node_bin=$("$DELIVERY_NODE_INSTALLER" "$node_wanted") || node_bin=
  else
    node_bin=$(node_install_default "$node_wanted") || node_bin=
  fi
  if [ -n "$node_bin" ] && [ -d "$node_bin" ]; then
    export PATH="$node_bin:$PATH"
    say "node: active Node was $(node -p 'process.versions.node' 2>/dev/null || echo none) -> now using Node $node_wanted from $node_bin (add to PATH in new shells)"
  else
    say "node: could not install Node $node_wanted; continuing with the active Node"
  fi
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
