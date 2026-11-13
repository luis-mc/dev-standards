# DL281 report: vm_check.py

Base check: `compose.kvm.yaml` and `def prepare_kvm` were on origin/main (7ef9512).

## What changed
- `templates/shared/scripts/delivery/vm_check.py` (new): `doctor`, `prepare`, `run`, `selinux`, `prune`. Stdlib only.
- `templates/shared/scripts/delivery/vm-images.json` (new): fedora-45, rocky-9, rocky-10, debian-12, ubuntu-24.04. Checksum file is read first; the image is the file in it matching a pattern. Debian uses SHA-512.
- `pool_supervisor.py`: `prepare_vm_cache` makes `/ci-tools/vm-cache` root:<kvm group> 2775. `prepare_kvm(..., vm_cache=True)` calls it; the default is off so the existing DL274 tests are unchanged. `main` passes True.
- Tests `tests/test_dl281_vm_check.py` (22 tests, 1 skipped unless VM_CHECK_REAL=1).
- Docs: runner-pool spec R5.29 and proof row, `docs/guides/vm-checks.md`, feature note, change note `DL281-vm-check.md`.

## Decisions to check
- Resume copies the snapshot disk instead of layering an overlay on it. A qcow2 snapshot lives in the top image, so an overlay on the snapshot disk would not find `ready`. The copy is about 550 MB.
- The hostfwd port is added through the monitor (`hostfwd_add`) after boot or `-loadvm`, so the saved VM does not depend on a port.
- Global options (`--cache`, `--images`) go before the subcommand.
- The Fedora checksum URL has a `*` (the compose number) resolved from the directory listing of the images folder. Untested against the real mirror.
- Prune keeps the newest N per distro, so two projects with different package lists on one distro evict each other's base. Use `--keep 2` or more then.
- No template file list needed naming (none lists ci_watch.py by name).

## Tests
- `python3 -m unittest test_dl281_vm_check test_dl274_kvm_layers` (in tests/): 40 run, OK, 1 skipped.
- `python3 tools/test_delivery_ci.py --no-mutants`: 78 passed, 0 failed.
- `spec-lint.yml --ref DL281-vm-check -f areas=delivery` (run 43330569585): every delivery job success. Only `docs check` failed: W1 on docs/work (expected) and G1 `docs/llms.txt` stale (generated; I did not commit it; the release fold or `docs_index.py build` refreshes it because of the new guide).
- Not run: a real boot. No KVM in the cloud sandbox; `qemu` argv, monitor use and cloud-init seeds are untested on hardware.

## Try it by hand on a kvm runner
```
python3 vm_check.py doctor
python3 vm_check.py prepare --distro fedora-45 --resume
python3 vm_check.py run --distro fedora-45 --resume --json out.json -- getenforce
python3 vm_check.py selinux --distro fedora-45 --install x.rpm --module x.pp --resume
```

## Follow-ups
- First real-hardware run may need tuning (cloud-init ssh wait on Debian/Ubuntu, `power_state` on build seeds).
- Run `docs_index.py build` at the fold.
- DELIVERYSPEC / delivery-speed M1 hits were cleared with `Docs: none` in the commit message.

Branch head: see `git log` on DL281-vm-check (last commit after this report).

READY
