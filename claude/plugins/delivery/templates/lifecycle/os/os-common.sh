#!/usr/bin/env bash
# DS235d: shared lifecycle checks for the Linux and macOS step scripts (LC-8 to LC-17, LC-29, LC-33).
# Sourced by linux-deb.sh, linux-rpm.sh and macos.sh. Each platform script defines the os_* hooks.
# Reads lifecycle.json (LIFECYCLE_JSON, default docs/design-system/lifecycle.json is not assumed: set it).
# Prints one line per check: "LC-9 PASS detail" or "LC-9 FAIL detail". Exit 1 when any check failed.
# Package files come from the environment: LC_PKG (this build), LC_PREV_PKG (N-1), LC_BROKEN_PKG, LC_OLDER_PKG.

LC_FAILS=0
LC_JSON="${LIFECYCLE_JSON:-lifecycle.json}"

lc_get() { # lc_get dotted.key [default]; lists print one item per line
  python3 - "$LC_JSON" "$1" "${2:-}" <<'PY'
import json, sys
path, key, default = sys.argv[1:4]
try:
    node = json.load(open(path))
    for part in key.split("."):
        node = node[part]
except Exception:
    print(default)
    sys.exit(0)
if isinstance(node, list):
    print("\n".join(str(x) for x in node))
else:
    print(node)
PY
}

lc_result() { # lc_result ID PASS|FAIL detail
  printf '%s %s %s\n' "$1" "$2" "$3"
  [ "$2" = PASS ] || LC_FAILS=$((LC_FAILS + 1))
}

lc_need() { # lc_need ID varname: fail the check when the input is missing
  if [ -z "${!2:-}" ]; then lc_result "$1" FAIL "missing input $2"; return 1; fi
}

lc_sum() { # checksums of every file under the given paths, sorted
  local p
  for p in "$@"; do [ -e "$p" ] && find "$p" -type f -exec sha256sum {} + 2>/dev/null; done | sort
}

lc_wait() { # lc_wait seconds command...
  local limit="$1" t=0; shift
  while [ "$t" -lt "$limit" ]; do "$@" && return 0; sleep 1; t=$((t + 1)); done
  return 1
}

lc_console_up() {
  curl -fsS -o /dev/null --max-time 2 "http://127.0.0.1:$(lc_get paths.console_port 0)/"
}

lc_product() { lc_get product; }
lc_service() { lc_get paths.service "$(lc_product)"; }
lc_up() { os_service_active "$(lc_service)" && lc_console_up; }

lc9() {
  lc_need LC-9 LC_PKG || return
  local rc=0
  os_install "$LC_PKG" || rc=$?
  if [ "$rc" -ne 0 ]; then lc_result LC-9 FAIL "silent install exit $rc"; return; fi
  if os_reboot_pending; then lc_result LC-9 FAIL "install asks for a reboot"; return; fi
  if lc_wait 30 lc_up; then lc_result LC-9 PASS "installed, service up, console on 127.0.0.1 within 30 s"
  else lc_result LC-9 FAIL "service or console not up in 30 s"; fi
}

lc8() {
  local cmd; cmd="$(lc_get test_interface.selftest)"
  if [ -z "$cmd" ]; then lc_result LC-8 FAIL "lifecycle.json has no test_interface.selftest"; return; fi
  if (cd / && eval "$cmd") >/dev/null 2>&1; then lc_result LC-8 PASS "self-test passed on a fresh install"
  else lc_result LC-8 FAIL "self-test failed on a fresh install"; fi
}

lc10() {
  local before after paths
  mapfile -t paths < <({ lc_get paths.config; lc_get paths.data; } | grep .)
  before="$(lc_sum "${paths[@]}")$(os_installed_version "$(lc_product)")"
  os_install "$LC_PKG" || { lc_result LC-10 FAIL "reinstall failed"; return; }
  after="$(lc_sum "${paths[@]}")$(os_installed_version "$(lc_product)")"
  if [ "$before" = "$after" ]; then lc_result LC-10 PASS "reinstall of the same version changed nothing"
  else lc_result LC-10 FAIL "reinstall changed config, data or version"; fi
}

lc11() {
  lc_need LC-11 LC_PREV_PKG || return
  local paths before after
  os_purge "$(lc_product)" >/dev/null 2>&1 || true
  os_install "$LC_PREV_PKG" || { lc_result LC-11 FAIL "install of N-1 failed"; return; }
  mapfile -t paths < <({ lc_get paths.config; lc_get paths.data; } | grep .)
  before="$(lc_sum "${paths[@]}")"
  os_install "$LC_PKG" || { lc_result LC-11 FAIL "upgrade from N-1 failed"; return; }
  after="$(lc_sum "${paths[@]}")"
  if [ -n "$before" ] && [ "$before" = "$after" ]; then lc_result LC-11 PASS "upgrade from N-1 kept config and data (checksums match)"
  else lc_result LC-11 FAIL "config or data changed, or none was seeded"; fi
}

lc12() {
  lc_need LC-12 LC_BROKEN_PKG || return
  local good; good="$(os_installed_version "$(lc_product)")"
  os_install "$LC_BROKEN_PKG" >/dev/null 2>&1 || true
  # The updater, not this script, rolls back; this script waits up to 5 min for the good version and a live service.
  local t=0
  while [ "$t" -lt 300 ]; do
    if [ "$(os_installed_version "$(lc_product)")" = "$good" ] && lc_up; then
      lc_result LC-12 PASS "broken build rolled back in ${t} s"; return
    fi
    sleep 1; t=$((t + 1))
  done
  lc_result LC-12 FAIL "no rollback to $good within 5 min"
}

lc13() {
  lc_need LC-13 LC_OLDER_PKG || return
  local before; before="$(os_installed_version "$(lc_product)")"
  os_install "$LC_OLDER_PKG" >/dev/null 2>&1 || true
  if [ "$(os_installed_version "$(lc_product)")" = "$before" ]; then lc_result LC-13 PASS "downgrade refused"
  else lc_result LC-13 FAIL "downgrade changed the installed version"; fi
}

lc14() {
  local p bad=0 kept=0 gone=0 keep=() all=()
  mapfile -t keep < <(lc_get keep_on_remove | grep .)
  mapfile -t all < <({ lc_get paths.config; lc_get paths.data; lc_get paths.logs; } | grep .)
  os_remove "$(lc_product)" || { lc_result LC-14 FAIL "remove failed"; return; }
  for p in "${keep[@]}"; do if [ -e "$p" ]; then kept=$((kept + 1)); else bad=$((bad + 1)); fi; done
  for p in "${all[@]}"; do
    case " ${keep[*]} " in *" $p "*) continue ;; esac
    if [ -e "$p" ]; then bad=$((bad + 1)); else gone=$((gone + 1)); fi
  done
  if [ "$bad" -eq 0 ]; then lc_result LC-14 PASS "remove kept exactly keep_on_remove ($kept kept)"
  else lc_result LC-14 FAIL "$bad path(s) differ from keep_on_remove"; fi
}

lc15() {
  os_purge "$(lc_product)" || { lc_result LC-15 FAIL "purge failed"; return; }
  local out; out="$(os_leftovers 2>&1)"; local rc=$?
  if [ "$rc" -eq 0 ]; then lc_result LC-15 PASS "purge left nothing"
  else lc_result LC-15 FAIL "leftovers: $(printf '%s' "$out" | tr '\n' ';')"; fi
}

lc16() {
  local tray; tray="$(lc_get test_interface.tray_start)"
  if [ -n "$tray" ]; then eval "$tray" >/dev/null 2>&1 & sleep 2; fi
  if os_remove "$(lc_product)" && ! os_reboot_pending; then lc_result LC-16 PASS "remove worked with the tray running, no reboot"
  else lc_result LC-16 FAIL "remove failed or asks for a reboot while the tray runs"; fi
}

lc17() {
  if [ -n "$(os_sessions)" ]; then lc_result LC-17 FAIL "a user is signed in; run on a machine with none"; return; fi
  if lc_up; then lc_result LC-17 PASS "service up with nobody signed in"
  else lc_result LC-17 FAIL "service not up with nobody signed in"; fi
}

lc29() {
  local pair; pair="$(lc_get test_interface.pair)"
  if [ -z "$pair" ]; then lc_result LC-29 FAIL "lifecycle.json has no test_interface.pair"; return; fi
  eval "$pair" >/dev/null 2>&1 || { lc_result LC-29 FAIL "pairing command failed"; return; }
  if lc_wait 30 os_service_active "$(lc_service)"; then lc_result LC-29 PASS "service running after pairing, no manual step"
  else lc_result LC-29 FAIL "service not running after pairing"; fi
}

lc33() {
  local root n=0 p legacy=0
  while IFS= read -r root; do
    [ -d "$root" ] || continue
    n=$((n + $(find "$root" -mindepth 1 -maxdepth 1 -type d -iname "*$(lc_product)*" | wc -l)))
  done < <(lc_get paths.data_roots)
  while IFS= read -r p; do [ -n "$p" ] && [ -e "$p" ] && legacy=$((legacy + 1)); done < <(lc_get paths.legacy_data)
  if [ "$n" -le 1 ] && [ "$legacy" -eq 0 ]; then lc_result LC-33 PASS "one data folder, no legacy folder left"
  else lc_result LC-33 FAIL "$n data folders, $legacy legacy folders"; fi
}

lc_run() { # lc_run check... ; "all" runs the install-time checks in order
  local c
  for c in "$@"; do
    case "$c" in
      all) lc_run lc9 lc8 lc17 lc29 lc10 lc11 lc13 lc12 lc33 lint lc16 lc14 lc15 ;;
      lint) os_lint ;;
      lc8|lc9|lc10|lc11|lc12|lc13|lc14|lc15|lc16|lc17|lc29|lc33) "$c" ;;
      *) echo "unknown check $c" >&2; return 2 ;;
    esac
  done
  [ "$LC_FAILS" -eq 0 ]
}
