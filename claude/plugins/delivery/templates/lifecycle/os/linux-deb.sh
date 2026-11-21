#!/usr/bin/env bash
# DS235d: Debian/Ubuntu lifecycle steps (LC-8 to LC-17, LC-19, LC-20, LC-29, LC-33).
# Usage: LIFECYCLE_JSON=lifecycle.json LC_PKG=app_1.2.0_amd64.deb ./linux-deb.sh all|lc9|lc10|...|lint
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=os-common.sh
. "$HERE/os-common.sh"
# shellcheck source=linux-common.sh
. "$HERE/linux-common.sh"

os_install() { DEBIAN_FRONTEND=noninteractive apt-get install -y --allow-downgrades ./"${1#./}" >/dev/null 2>&1 \
  || DEBIAN_FRONTEND=noninteractive dpkg -i "$1" >/dev/null 2>&1; }
os_remove() { DEBIAN_FRONTEND=noninteractive apt-get remove -y "$1" >/dev/null 2>&1; }
os_purge() { DEBIAN_FRONTEND=noninteractive apt-get purge -y "$1" >/dev/null 2>&1; }
os_installed_version() { dpkg-query -W -f='${Version}' "$1" 2>/dev/null; }
os_reboot_pending() { [ -e /var/run/reboot-required ]; }

os_lint() { # LC-19: lintian, install with no systemd running; LC-20
  local rc=0
  if command -v lintian >/dev/null 2>&1 && lintian --fail-on error "$LC_PKG" >/dev/null 2>&1; then
    lc_result LC-19 PASS "lintian clean"
  else
    lc_result LC-19 FAIL "lintian missing or reported errors"; rc=1
  fi
  os_install_no_systemd || lc_result LC-19 FAIL "install failed with no systemd running"
  os_lint_common
  return "$rc"
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then lc_run "${@:-all}"; fi
