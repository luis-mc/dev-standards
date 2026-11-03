#!/usr/bin/env bash
# The Linux MSI recipe (CIR10 W1, W2). OPTIONAL: for a project that ships an MSI.
#
# A CI CHECK ONLY. The MSI this builds is not the file that ships: Wine cannot write LZX, so the
# cabinet is compressed with `mszip` (the Windows build uses `high`), and the file has never been
# installed. It proves "the authoring builds". The shipped MSI is built on Windows. Reopen this
# once a Windows install smoke passes on the Linux-built file at each release (decision 10).
#
# Usage:  windows-msi-linux.sh [--dry-run] [--tools scripts/delivery/windows-build-tools.json]
#                              [--cache DIR] [--out DIR]
#
# The tools file lists every download, pinned by SHA-256, and the build command:
#   {"tools": [{"name": "wix", "url": "https://...", "sha256": "<64 hex>", "file": "wix.zip"}],
#    "build": {"exe": "wix/candle.exe", "args": ["-out", "{out}/app.msi", "installer/app.wxs"]}}
# `{out}` and `{tools}` in args are replaced. The authoring must read the compression level from
# the MSI_COMPRESSION variable (the Windows command line then stays unchanged).
#
# Build tools are started by their FULL path under the cache, never found through PATH.
# --dry-run prints each step and runs nothing (no download, no Wine).
set -euo pipefail

DRY=0
TOOLS="scripts/delivery/windows-build-tools.json"
CACHE="${MSI_CACHE:-${HOME:-/tmp}/.cache/msi-build}"
OUT="build/msi"
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1 ;;
    --tools) TOOLS="$2"; shift ;;
    --cache) CACHE="$2"; shift ;;
    --out) OUT="$2"; shift ;;
    *) echo "windows-msi-linux: unknown option $1" >&2; exit 2 ;;
  esac
  shift
done

say() { echo "windows-msi-linux: $*"; }
step() { if [ "$DRY" = 1 ]; then say "would: $*"; else say "$*"; fi; }

[ -f "$TOOLS" ] || { echo "windows-msi-linux: $TOOLS not found" >&2; exit 2; }
export MSI_COMPRESSION=mszip          # W2: Wine cannot write LZX
export WINEPREFIX="$CACHE/prefix"
export WINEDEBUG="${WINEDEBUG:--all}"
TOOLDIR="$CACHE/tools"

step "use compression level mszip (MSI_COMPRESSION), Wine prefix $WINEPREFIX"
mapfile -t ROWS < <(python3 -I - "$TOOLS" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
for t in d["tools"]:
    print("\t".join([t["name"], t["url"], t["sha256"], t["file"]]))
PY
)
for row in "${ROWS[@]}"; do
  IFS=$'\t' read -r name url sha file <<<"$row"
  step "fetch $name from $url, check SHA-256 $sha"
  if [ "$DRY" = 0 ]; then
    mkdir -p "$TOOLDIR"
    [ -f "$TOOLDIR/$file" ] || curl -fsSL --retry 3 -o "$TOOLDIR/$file" "$url"
    got=$(sha256sum "$TOOLDIR/$file" | cut -d' ' -f1)
    [ "$got" = "$sha" ] || { echo "windows-msi-linux: $file has SHA-256 $got, expected $sha" >&2; exit 1; }
  fi
done

read -r EXE ARGS < <(python3 -I - "$TOOLS" "$OUT" "$TOOLDIR" <<'PY'
import json, shlex, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))["build"]
a = [x.replace("{out}", sys.argv[2]).replace("{tools}", sys.argv[3]) for x in d["args"]]
print(d["exe"], " ".join(shlex.quote(x) for x in a))
PY
)
WINE_BIN="$(command -v wine || true)"
if [ "$DRY" = 1 ]; then
  step "run xvfb-run -a ${WINE_BIN:-wine} $TOOLDIR/$EXE $ARGS"
  step "check that $OUT/*.msi exists"
  exit 0
fi
[ -n "$WINE_BIN" ] || { echo "windows-msi-linux: wine is not installed" >&2; exit 2; }
XVFB="$(command -v xvfb-run || true)"
[ -n "$XVFB" ] || { echo "windows-msi-linux: xvfb-run is not installed" >&2; exit 2; }
mkdir -p "$OUT"
eval "set -- $ARGS"
"$XVFB" -a "$WINE_BIN" "$TOOLDIR/$EXE" "$@"
ls "$OUT"/*.msi >/dev/null 2>&1 || { echo "windows-msi-linux: no MSI in $OUT" >&2; exit 1; }
say "built (a CI check only, not the shipped file): $(ls "$OUT"/*.msi)"
