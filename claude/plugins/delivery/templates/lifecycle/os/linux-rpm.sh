#!/usr/bin/env bash
# DS235d: Fedora/RPM lifecycle steps (LC-8 to LC-17, LC-19, LC-20, LC-29, LC-33).
# Usage: LIFECYCLE_JSON=lifecycle.json LC_PKG=app-1.2.0.x86_64.rpm ./linux-rpm.sh all|lc9|...|lint
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=os-common.sh
. "$HERE/os-common.sh"
# shellcheck source=linux-common.sh
. "$HERE/linux-common.sh"

os_install() { dnf install -y --allow-downgrade "$1" >/dev/null 2>&1 || rpm -U --replacepkgs "$1" >/dev/null 2>&1; }
os_remove() { dnf remove -y "$1" >/dev/null 2>&1; }
# rpm has no purge: the package's own uninstaller deletes data with --delete-data.
os_purge() { local u; u="$(lc_get paths.uninstaller)"
  if [ -n "$u" ] && [ -x "$u" ]; then "$u" --delete-data >/dev/null 2>&1; fi
  dnf remove -y "$1" >/dev/null 2>&1 || true; }
os_installed_version() { rpm -q --qf '%{VERSION}-%{RELEASE}' "$1" 2>/dev/null | grep -v 'not installed'; }
os_reboot_pending() { command -v needs-restarting >/dev/null 2>&1 && ! needs-restarting -r >/dev/null 2>&1; }

os_lint() { # LC-19: rpmlint, install with no systemd running; LC-20
  local rc=0
  if command -v rpmlint >/dev/null 2>&1 && rpmlint "$LC_PKG" >/dev/null 2>&1; then
    lc_result LC-19 PASS "rpmlint clean"
  else
    lc_result LC-19 FAIL "rpmlint missing or reported errors"; rc=1
  fi
  os_install_no_systemd || lc_result LC-19 FAIL "install failed with no systemd running"
  os_lint_common
  return "$rc"
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then lc_run "${@:-all}"; fi
