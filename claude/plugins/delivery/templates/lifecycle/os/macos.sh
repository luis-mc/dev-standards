#!/usr/bin/env bash
# DS235d: macOS pkg lifecycle steps (LC-8 to LC-17, LC-21, LC-29, LC-33).
# Usage: LIFECYCLE_JSON=lifecycle.json LC_PKG=App-1.2.0-arm64.pkg ./macos.sh all|lc9|...|lint
# LC_UNSIGNED_DECISION=<ID> marks a build that is unsigned by decision (the contract records it).
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=os-common.sh
. "$HERE/os-common.sh"

os_install() { sudo installer -pkg "$1" -target / >/dev/null 2>&1; }
os_remove() { local u; u="$(lc_get paths.uninstaller)"; sudo "$u" >/dev/null 2>&1; }
os_purge() { local u; u="$(lc_get paths.uninstaller)"; sudo "$u" --delete-data >/dev/null 2>&1; }
os_installed_version() { pkgutil --pkg-info "$(lc_get paths.pkg_id)" 2>/dev/null | awk -F': ' '$1 == "version" {print $2}'; }
os_reboot_pending() { return 1; } # a pkg install never asks for one
os_service_active() { sudo launchctl print "system/$(lc_get paths.launchd_label "$1")" 2>/dev/null | grep -q 'state = running'; }
os_sessions() { stat -f '%Su' /dev/console 2>/dev/null | grep -v '^root$'; }
os_leftovers() { bash "$HERE/leftovers-macos.sh"; }

os_lint() { # LC-21: codesign and stapler, or unsigned by decision
  local app; app="$(lc_get paths.app)"
  if [ -n "${LC_UNSIGNED_DECISION:-}" ]; then
    lc_result LC-21 PASS "unsigned by decision $LC_UNSIGNED_DECISION"; return 0
  fi
  if codesign --verify --deep --strict "$app" >/dev/null 2>&1 && xcrun stapler validate "$LC_PKG" >/dev/null 2>&1; then
    lc_result LC-21 PASS "codesign verifies and the ticket is stapled"
  else
    lc_result LC-21 FAIL "codesign --verify or stapler failed"; return 1
  fi
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then lc_run "${@:-all}"; fi
