#!/usr/bin/env bash
# DS235d: after a purge, list what the product left on macOS. Exit 0 and no output when nothing is left (LC-15).
set -u
J="${LIFECYCLE_JSON:-lifecycle.json}"
get() { python3 - "$J" "$1" <<'PY'
import json, sys
try:
    n = json.load(open(sys.argv[1]))
    for k in sys.argv[2].split("."):
        n = n[k]
except Exception:
    sys.exit(0)
print("\n".join(map(str, n)) if isinstance(n, list) else n)
PY
}
product="$(get product)"; label="$(get paths.launchd_label)"; label="${label:-$product}"
found=0
say() { echo "$1"; found=1; }

for key in paths.app paths.install paths.config paths.data paths.logs paths.legacy_data; do
  while IFS= read -r p; do [ -n "$p" ] && [ -e "$p" ] && say "file: $p"; done < <(get "$key")
done
# launchd plists, system and user
for d in /Library/LaunchDaemons /Library/LaunchAgents "$HOME/Library/LaunchAgents"; do
  for f in "$d/$label.plist" "$d"/*"$product"*.plist; do [ -e "$f" ] && say "launchd plist: $f"; done
done
launchctl print "system/$label" >/dev/null 2>&1 && say "service loaded: $label"
# package receipt
[ -n "$(get paths.pkg_id)" ] && pkgutil --pkg-info "$(get paths.pkg_id)" >/dev/null 2>&1 && say "pkg receipt: $(get paths.pkg_id)"
# firewall rule
if /usr/libexec/ApplicationFirewall/socketfilterfw --listapps 2>/dev/null | grep -qi "$product"; then say "firewall rule: application firewall names $product"; fi
# listening ports
while IFS= read -r port; do
  [ -n "$port" ] && lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1 && say "listening port: $port"
done < <(get paths.listen_ports; get paths.console_port)
exit "$found"
