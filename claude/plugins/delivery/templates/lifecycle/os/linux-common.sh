#!/usr/bin/env bash
# DS235d: Linux hooks shared by the deb and rpm step scripts. Source after os-common.sh.
HERE_OS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

os_service_active() { systemctl is-active --quiet "$1"; }
os_sessions() { loginctl list-sessions --no-legend 2>/dev/null | awk '$3 != "" {print $1}'; }
os_leftovers() { bash "$HERE_OS/leftovers-linux.sh"; }

os_lint_common() { # LC-20: unit files verify, service runs as a non-root user
  local unit user svc; svc="$(lc_service)"
  unit="$(systemctl show -p FragmentPath --value "$svc.service" 2>/dev/null)"
  if [ -z "$unit" ] || ! systemd-analyze verify "$unit" >/dev/null 2>&1; then
    lc_result LC-20 FAIL "systemd-analyze verify failed or no unit for $svc"
  else
    user="$(systemctl show -p User --value "$svc.service" 2>/dev/null)"
    if [ -n "$user" ] && [ "$user" != root ]; then lc_result LC-20 PASS "unit verifies, runs as $user"
    else lc_result LC-20 FAIL "unit runs as root"; fi
  fi
}

os_install_no_systemd() { # LC-19 part: the package installs where systemd is not running (a container)
  [ -d /run/systemd/system ] && return 0
  os_install "$LC_PKG" >/dev/null 2>&1
}
