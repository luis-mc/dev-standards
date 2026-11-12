# DL274 report

**Base check:** after `git checkout -B DL274-pool-linux-kvm origin/main`, `LAYERS = {'windows-packaging'` and `def labels_for` were both present. Ready.

## What changed
- `linux-packaging` layer: Dockerfile case, `LAYERS`, `LAYER_TOOLS` (dpkg-deb, rpmbuild, checkmodule, semodule_package). `policycoreutils-python-utils` is added only when `apt-cache show` finds it.
- `kvm` layer: qemu-system-x86, qemu-utils, cloud-image-utils; tools qemu-system-x86_64, cloud-localds.
- `host_kvm()` in `delivery_runner_pool.py`: `docker run --rm --device /dev/kvm --entrypoint test <pool image or alpine> -r /dev/kvm -a -w /dev/kvm`. `Probe.sh` sets `MSYS_NO_PATHCONV=1` for every docker call. Doctor prints `kvm-host`, `kvm-compose`, `kvm-container`, `kvm-label`; `pool-plan` prints one `KVM on this host` line.
- `compose.kvm.yaml` (new): `devices: [/dev/kvm:/dev/kvm]` and `POOL_KVM=1`. No `privileged`. `compose.yaml` is unchanged. The override is chosen with `COMPOSE_FILE` in the pool `.env`.
- `pool-refresh --kvm on|off`; it also refuses `POOL_KVM=1` already in `.env` when the host check is not yes. `set_env_values` now removes a key when its value is None.
- `pool_supervisor.prepare_kvm`: reads the gid of `/dev/kvm` in the container, reuses or creates the group, `usermod -aG` the agent user.
- `labels_for` adds `kvm` when `POOL_KVM=1` and `/dev/kvm` is usable.
- Label for existing runners: **the doctor prints the exact `gh api` command** (POST to add, DELETE to remove). Chosen over the supervisor because the GitHub credentials stay on the host, not in the container.
- Docs: runner-pool spec R5.9 (layers) and new R5.28 (KVM); feature note `docs/features/runner-pool/changes/DL274.md`; change note `docs/architecture/changes/DL274-pool-linux-kvm.md`.
- One existing test edited: `test_dl101_pool_browsers.py` line 160 now ignores the `--device` docker run.

## Tests
- `python3 -m unittest test_dl274_kvm_layers` (in tests/): 18 ok.
- `python3 -m unittest discover` in claude/plugins/delivery/tests: 1540 run, 1 failure (test_dl101 docker-run assertion), fixed; test_dl101 now 16 ok.
- `python3 tools/test_delivery_ci.py --no-mutants`: 78 passed, 0 failed.
- `python3 claude/plugins/docs/scripts/docs_check.py`: only the expected W1 (docs/work) and M1 on the delivery spec, which the commit message answers with `Docs: none`.
- CI `spec-lint.yml --ref DL274-pool-linux-kvm -f areas=delivery` (run 43324993561): every delivery job success; only "docs check" failed, with the expected W1 on docs/work/DL274/REPORT.md.

## How a machine turns KVM on
1. Windows: enable nested virtualization for WSL2 (Docker Desktop then shows `/dev/kvm`). Linux: `sudo modprobe kvm_intel` (or `kvm_amd`) and make `/dev/kvm` open to your user.
2. `python3 delivery_runner_pool.py doctor` (or `delivery_ci_setup.py pool-plan`) shows `KVM on this host: yes`.
3. Optional image layer: add `"kvm"` to `pool.layers` in `.delivery/config.json`.
4. `python3 delivery_ci_setup.py pool-refresh --kvm on --yes`
5. For runners already registered, run the commands the doctor prints, e.g. `gh api -X POST repos/OWNER/REPO/actions/runners/ID/labels -f 'labels[]=kvm'`.
To turn off: `pool-refresh --kvm off --yes`, then the doctor's DELETE command.

## Follow-ups
- The label commands could be run by `pool-refresh` itself after the rebuild.
- `/delivery-ci-setup` could ask about Linux packaging, like it does for Windows installers.
- Docs check M1 on `docs/features/delivery/spec.md` is answered only by the commit message.

Branch head SHA: see `git rev-parse origin/DL274-pool-linux-kvm` (the commit after a4f23b9 that holds this report).
READY
