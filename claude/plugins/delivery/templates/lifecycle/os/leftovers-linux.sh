#!/usr/bin/env bash
# DS235d: after a purge, list what the product left on Linux. Exit 0 and no output when nothing is left (LC-15).
# Reads lifecycle.json (LIFECYCLE_JSON): product, paths.*, paths.listen_ports.
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
product="$(get product)"; service="$(get paths.service)"; service="${service:-$product}"
found=0
say() { echo "$1"; found=1; }

# files and folders
for key in paths.install paths.config paths.data paths.logs paths.legacy_data; do
  while IFS= read -r p; do [ -n "$p" ] && [ -e "$p" ] && say "file: $p"; done < <(get "$key")
done
# systemd units (also the user units the package may have enabled)
for d in /etc/systemd/system /lib/systemd/system /usr/lib/systemd/system /etc/systemd/user /usr/lib/systemd/user; do
  for u in "$d/$service".service "$d/$service".timer; do [ -e "$u" ] && say "systemd unit: $u"; done
done
# services still known to systemd
if command -v systemctl >/dev/null 2>&1; then
  systemctl list-unit-files --no-legend "$service.service" 2>/dev/null | grep -q . && say "service registered: $service"
fi
# scheduled tasks
for f in /etc/cron.d/"$service" /etc/cron.d/"$product" /etc/cron.daily/"$product"; do [ -e "$f" ] && say "scheduled task: $f"; done
# firewall rules
if command -v firewall-cmd >/dev/null 2>&1 && firewall-cmd --list-all 2>/dev/null | grep -qiw "$product"; then say "firewall rule: firewalld names $product"; fi
if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -qiw "$product"; then say "firewall rule: ufw names $product"; fi
# listening ports
while IFS= read -r port; do
  [ -n "$port" ] && ss -ltn 2>/dev/null | awk '{print $4}' | grep -q ":$port$" && say "listening port: $port"
done < <(get paths.listen_ports; get paths.console_port)
# system user the package created
if [ -n "$(get paths.system_user)" ] && getent passwd "$(get paths.system_user)" >/dev/null; then say "user: $(get paths.system_user)"; fi
exit "$found"
