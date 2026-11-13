# VM checks on a kvm runner

Use this to test a package in a clean distro VM, for example a Fedora VM with SELinux Enforcing. It needs a pool runner with the `kvm` label (see the runner-pool spec, R5.28, R5.29).

## Workflow example

```yaml
jobs:
  selinux:
    runs-on: [self-hosted, kvm]
    steps:
      - uses: actions/checkout@v4
      - name: Build the package
        run: make rpm policy        # writes dist/x.rpm and dist/x.pp
      - name: Prepare the VM once
        run: python3 scripts/delivery/vm_check.py prepare --distro fedora-45 --resume
      - name: Check SELinux
        run: python3 scripts/delivery/vm_check.py selinux --distro fedora-45 --install dist/x.rpm --module dist/x.pp --resume
```

Global options (`--cache`, `--images FILE`) go before the command. `prepare` is optional: `run` and `selinux` prepare what is missing. A step like it saves time when several jobs share the cache.

## Other commands

```sh
vm_check.py doctor                         # /dev/kvm, tools, cache, free disk
vm_check.py prepare --distro rocky-9 --packages "gcc make"
vm_check.py run --distro rocky-9 --copy build/app:/tmp/app --json out.json -- /tmp/app --self-test
vm_check.py prune --keep 1                 # newest image, base and snapshot per distro
```

`run` exits with the exit code of the first failing command. `--json FILE` gets the timings. Your own distros go in a file with the same shape as `vm-images.json`, passed with `--images`.

## What it costs

Measured on a real pool with KVM, Fedora 45 Cloud Base, 1 GiB, 2 CPUs.

| Step | Time | When |
|---|---|---|
| First image download and SHA-256 check (579 MB) | 166 s | once per published image |
| Image already cached | 1 s | every later run |
| Cold boot to a login | 11.6 to 11.9 s | each run without `--resume` |
| `savevm` (snapshot disk about 550 MB) | 0.7 s | once per snapshot key |
| `-loadvm` to a running VM | 0.7 s | each run with `--resume` |

## Notes

- `run -- CMD...` runs one program with its arguments. For a shell line, pass `-- sh -c 'a; b'`.
- When the checksum file cannot be read (no network), the newest cached image of the distro is used.
- First real run on a pool (13 Nov): Fedora 45, SELinux check with an rpm and a module: about 27 s cold, about 20 s with `--resume`; Enforcing, 0 AVC.

- A seed that powers off ends the VM before login. The snapshot base uses an idle seed.
- Two jobs on one cache wait on a lock, they do not build twice.
- The VM counts against the pool memory (`POOL_MEM`). The script warns when less than the VM size plus 1 GiB is free.
- A snapshot is tied to the qemu version, the host CPU model, the memory and the CPU count. If one changes, the next `--resume` run builds a new one.
