#!/usr/bin/env python3
"""DL281: boot throwaway distro VMs fast and repeatably, from a CI job on a runner labelled kvm. Linux only, standard library only.

  vm_check.py doctor
  vm_check.py prepare --distro D [--packages "a b"] [--resume]
  vm_check.py run     --distro D [--resume] [--copy LOCAL:REMOTE ...] [--script FILE] [--json FILE] [-- CMD...]
  vm_check.py selinux --distro D --install FILE.rpm [--module FILE.pp] [--resume]
  vm_check.py prune   [--keep 1]

The cache holds images, prepared bases and (with --resume) snapshot disks. Every write goes to a temp name under a lock, then is renamed."""
import argparse
import contextlib
import fnmatch
import hashlib
import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

try:
    import fcntl
except ImportError:  # Windows: the script is Linux-only, the tests still import it
    fcntl = None

HERE = os.path.dirname(os.path.abspath(__file__))
SHARED_CACHE = '/ci-tools/vm-cache'
SNAP_NAME = 'ready'
SSH_OPTS = ['-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null', '-o', 'LogLevel=ERROR',
            '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5']
GIB = 1 << 30


class VmError(Exception):
    pass


def log(msg):
    print('vm_check: ' + msg, file=sys.stderr, flush=True)


# ---- process and network seams (tests replace these) ----

def sh(argv, input=None, timeout=None):
    """Run argv; return (code, output). A timeout returns code 124."""
    try:
        p = subprocess.run(argv, input=input, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        return 124, (e.stdout or b'').decode('utf-8', 'replace')
    except FileNotFoundError as e:
        return 127, str(e)
    return p.returncode, p.stdout.decode('utf-8', 'replace')


def spawn(argv):
    return subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def http_open(url, timeout=60):
    return urllib.request.urlopen(url, timeout=timeout)


def monitor_cmd(path, cmd, timeout=120.0):
    """Send one command to the qemu human monitor on a unix socket; return its text."""
    s = socket.socket(socket.AF_UNIX)
    s.settimeout(timeout)
    s.connect(path)
    try:
        s.recv(4096)  # banner
        s.sendall((cmd + '\n').encode())
        data = b''
        while not data.rstrip().endswith(b'(qemu)'):
            chunk = s.recv(4096)
            if not chunk:
                break
            data += chunk
        return data.decode('utf-8', 'replace')
    finally:
        s.close()


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


sleep = time.sleep
now = time.time
mono = time.monotonic


# ---- images file and cache ----

def load_images(extra=None):
    with open(os.path.join(HERE, 'vm-images.json'), encoding='utf-8') as f:
        distros = dict(json.load(f)['distros'])
    if extra:
        with open(extra, encoding='utf-8') as f:
            distros.update(json.load(f).get('distros', {}))
    return distros


def writable_dir(path):
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        return False
    return os.access(path, os.W_OK)


def cache_dir(arg=None, environ=None, writable=writable_dir):
    env = os.environ if environ is None else environ
    chosen = arg or env.get('VM_CACHE')
    if chosen:
        return chosen
    if writable(SHARED_CACHE):
        return SHARED_CACHE
    return os.path.join(os.path.expanduser('~'), '.cache', 'vm-check')


def sub(cache, name):
    d = os.path.join(cache, name)
    os.makedirs(d, exist_ok=True)
    return d


@contextlib.contextmanager
def lock(cache, name):
    """An exclusive lock on <cache>/locks/<name>, so two jobs never build the same thing twice."""
    path = os.path.join(sub(cache, 'locks'), name + '.lock')
    with open(path, 'a+') as f:
        if fcntl is not None:
            fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(f, fcntl.LOCK_UN)


def tmp_name(path):
    return '%s.tmp-%d' % (path, os.getpid())


def short(*parts):
    return hashlib.sha256('\n'.join(str(p) for p in parts).encode()).hexdigest()[:16]


def base_key(checksum, packages):
    return short('base', checksum, ' '.join(sorted(packages)))


def qemu_version():
    code, out = sh(['qemu-system-x86_64', '--version'])
    return out.splitlines()[0].strip() if code == 0 and out else 'unknown'


def cpu_model(path='/proc/cpuinfo'):
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            for line in f:
                if line.startswith('model name'):
                    return line.split(':', 1)[1].strip()
    except OSError:
        pass
    return 'unknown'


def snap_key(bkey, qver, cpu, mem, cpus):
    return short('snap', bkey, qver, cpu, mem, cpus)


# ---- image download ----

def fetch_text(url):
    with http_open(url) as r:
        return r.read().decode('utf-8', 'replace')


def resolve_checksum_url(spec):
    url = spec['checksum_url']
    if '*' not in url:
        return url
    base, _, last = url.rpartition('/')
    listing = fetch_text(base + '/')
    names = sorted(set(re.findall(r'href="([^"/?]+)"', listing)))
    hits = [n for n in names if fnmatch.fnmatch(n, last)]
    if not hits:
        raise VmError('no file matching %s in %s/' % (last, base))
    return base + '/' + hits[-1]


def parse_checksums(text, fmt, pattern):
    """Return (name, hex) for the last file in the checksum text whose name matches pattern."""
    found = None
    for line in text.splitlines():
        line = line.strip()
        if fmt == 'bsd':
            m = re.match(r'^SHA\d+ \((.+)\) = ([0-9a-fA-F]+)$', line)
            name, digest = (m.group(1), m.group(2)) if m else (None, None)
        else:
            m = re.match(r'^([0-9a-fA-F]+)\s+\*?(.+)$', line)
            name, digest = (m.group(2), m.group(1)) if m else (None, None)
        if name and fnmatch.fnmatch(name, pattern):
            found = (name, digest.lower())
    if not found:
        raise VmError('no image matching %s in the checksum file' % pattern)
    return found


def download(url, dest, algo, want):
    tmp = tmp_name(dest)
    h = hashlib.new(algo)
    try:
        with http_open(url, timeout=120) as r, open(tmp, 'wb') as f:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                h.update(chunk)
                f.write(chunk)
        if h.hexdigest() != want:
            raise VmError('checksum mismatch for %s: got %s, expected %s' % (url, h.hexdigest(), want))
        os.replace(tmp, dest)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def ensure_image(cache, distro, spec):
    """Return (path, checksum). Downloads once per published checksum; later calls only read the checksum file."""
    name, digest = parse_checksums(fetch_text(resolve_checksum_url(spec)), spec['checksum_format'], spec['pattern'])
    path = os.path.join(sub(cache, 'images'), '%s-%s.qcow2' % (distro, digest[:16]))
    if os.path.exists(path):
        return path, digest
    with lock(cache, 'image-' + distro):
        if not os.path.exists(path):
            log('downloading %s' % name)
            download(spec['base_url'] + name, path, spec['algo'], digest)
    return path, digest


# ---- keys, seeds and disks ----

def ensure_ssh_key(cache):
    key = os.path.join(sub(cache, 'ssh'), 'id_ed25519')
    if not os.path.exists(key):
        with lock(cache, 'ssh-key'):
            if not os.path.exists(key):
                tmp = tmp_name(key)
                for p in (tmp, tmp + '.pub'):
                    if os.path.exists(p):
                        os.remove(p)
                code, out = sh(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-C', 'vm-check', '-f', tmp])
                if code != 0:
                    raise VmError('ssh-keygen failed: ' + out.strip())
                os.chmod(tmp, 0o600)
                os.replace(tmp + '.pub', key + '.pub')
                os.replace(tmp, key)
    with open(key + '.pub', encoding='utf-8') as f:
        return key, f.read().strip()


def user_data(pubkey, packages=None, poweroff=False):
    lines = ['#cloud-config', 'ssh_authorized_keys:', '  - ' + pubkey]
    if packages:
        lines += ['package_update: true', 'packages:'] + ['  - ' + p for p in packages]
    if poweroff:
        lines += ['power_state:', '  mode: poweroff', '  timeout: 30', '  condition: true']
    return '\n'.join(lines) + '\n'


def make_seed(dest, pubkey, instance, packages=None, poweroff=False, workdir=None):
    """Build a cloud-init seed as a qcow2 file (a savevm needs every drive in qcow2)."""
    work = tempfile.mkdtemp(prefix='vmseed-', dir=workdir)
    try:
        ud, md, raw = (os.path.join(work, n) for n in ('user-data', 'meta-data', 'seed.img'))
        with open(ud, 'w', encoding='utf-8') as f:
            f.write(user_data(pubkey, packages, poweroff))
        with open(md, 'w', encoding='utf-8') as f:
            f.write('instance-id: %s\nlocal-hostname: vmcheck\n' % instance)
        for argv in (['cloud-localds', raw, ud, md], ['qemu-img', 'convert', '-O', 'qcow2', raw, dest]):
            code, out = sh(argv)
            if code != 0:
                raise VmError('%s failed: %s' % (argv[0], out.strip()))
    finally:
        shutil.rmtree(work, ignore_errors=True)


def ensure_idle_seed(cache, pubkey):
    path = os.path.join(sub(cache, 'seeds'), 'idle-%s.qcow2' % short(pubkey))
    if not os.path.exists(path):
        with lock(cache, 'seed-idle'):
            if not os.path.exists(path):
                tmp = tmp_name(path)
                make_seed(tmp, pubkey, 'vmcheck-idle')
                os.replace(tmp, path)
    return path


def make_overlay(backing, dest):
    code, out = sh(['qemu-img', 'create', '-q', '-f', 'qcow2', '-b', backing, '-F', 'qcow2', dest])
    if code != 0:
        raise VmError('qemu-img create failed: ' + out.strip())


def qemu_argv(disk, seed, mem, cpus, sock, loadvm=False):
    argv = ['qemu-system-x86_64', '-enable-kvm', '-cpu', 'host', '-m', str(mem), '-smp', str(cpus),
            '-display', 'none', '-serial', 'null', '-no-reboot',
            '-monitor', 'unix:%s,server,nowait' % sock,
            '-drive', 'file=%s,if=virtio,format=qcow2' % disk,
            '-drive', 'file=%s,if=virtio,format=qcow2,readonly=on' % seed,
            '-netdev', 'user,id=n0', '-device', 'virtio-net-pci,netdev=n0']
    if loadvm:
        argv += ['-loadvm', SNAP_NAME]
    return argv


def warn_memory(mem_mb, root='/sys/fs/cgroup'):
    """Print a warning when the pool has less than mem + 1 GiB free. Returns the warning or None."""
    def read(name):
        try:
            with open(os.path.join(root, name), encoding='utf-8') as f:
                v = f.read().strip()
            return None if v == 'max' else int(v)
        except (OSError, ValueError):
            return None
    limit, used = read('memory.max'), read('memory.current')
    if limit is None or used is None:
        return None
    if limit - used < mem_mb * (1 << 20) + GIB:
        msg = 'only %d MiB free in the pool; a %d MiB VM needs %d MiB more than that for headroom' % (
            (limit - used) >> 20, mem_mb, 1024)
        log('warning: ' + msg)
        return msg
    return None


# ---- ssh ----

class Vm:
    """One booted throwaway VM. Use as a context manager: the overlay is always deleted and qemu always killed."""

    def __init__(self, cache, distro, spec, base, snapshot, seed, key, mem=1024, cpus=2, resume=False, timeout=300):
        self.cache, self.distro, self.user = cache, distro, spec.get('user', 'root')
        self.base, self.snapshot, self.seed, self.key = base, snapshot, seed, key
        self.mem, self.cpus, self.resume, self.timeout = mem, cpus, resume, timeout
        self.work = self.proc = self.port = None
        self.timings = {}

    def __enter__(self):
        self.work = tempfile.mkdtemp(prefix='vmrun-')
        try:
            self._boot()
        except BaseException:
            self.close()
            raise
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    def close(self):
        if self.proc is not None:
            try:
                self.proc.kill()
                self.proc.wait(timeout=10)
            except Exception:
                pass
            self.proc = None
        if self.work:
            shutil.rmtree(self.work, ignore_errors=True)
            self.work = None

    def _boot(self):
        t0 = mono()
        disk = os.path.join(self.work, 'disk.qcow2')
        if self.resume:
            shutil.copyfile(self.snapshot, disk)  # the snapshot lives in this file, so it is copied, not layered
        else:
            make_overlay(self.base, disk)
        sock = os.path.join(self.work, 'mon.sock')
        self.proc = spawn(qemu_argv(disk, self.seed, self.mem, self.cpus, sock, loadvm=self.resume))
        self.port = free_port()
        self._wait_monitor(sock)
        monitor_cmd(sock, 'hostfwd_add tcp:127.0.0.1:%d-:22' % self.port)
        self.timings['qemu_start_s'] = round(mono() - t0, 2)
        self._wait_ssh()
        self.timings['boot_to_ssh_s'] = round(mono() - t0, 2)
        if self.resume:
            self._after_resume()
            self.timings['after_resume_s'] = round(mono() - t0, 2)

    def _wait_monitor(self, sock):
        end = mono() + 30
        while not os.path.exists(sock):
            if mono() > end or self.proc.poll() is not None:
                raise VmError('qemu did not start')
            sleep(0.1)

    def ssh_argv(self, cmd):
        return ['ssh', '-i', self.key, '-p', str(self.port)] + SSH_OPTS + ['%s@127.0.0.1' % self.user, cmd]

    def ssh(self, cmd, input=None, timeout=None):
        return sh(self.ssh_argv(cmd), input=input, timeout=timeout)

    def _wait_ssh(self):
        end = mono() + self.timeout
        while True:
            if self.proc.poll() is not None:
                raise VmError('qemu stopped before ssh came up')
            if self.ssh('true', timeout=20)[0] == 0:
                return
            if mono() > end:
                raise VmError('timeout: ssh did not come up in %d s' % self.timeout)
            sleep(0.5)

    def _after_resume(self):
        """A restored VM has the clock and the random pool of the moment it was saved."""
        code, out = self.ssh('sudo date -s @%d' % int(now()))
        if code != 0:
            raise VmError('could not set the guest clock: ' + out.strip())
        code, out = self.ssh('sudo tee /dev/urandom >/dev/null', input=os.urandom(256))
        if code != 0:
            raise VmError('could not reseed the guest RNG: ' + out.strip())

    def copy(self, local, remote):
        argv = ['scp', '-i', self.key, '-P', str(self.port)] + SSH_OPTS + [local, '%s@127.0.0.1:%s' % (self.user, remote)]
        code, out = sh(argv, timeout=self.timeout)
        if code != 0:
            raise VmError('scp %s failed: %s' % (local, out.strip()))


# ---- prepare ----

def boot_and_wait_off(argv, timeout):
    proc = spawn(argv)
    end = mono() + timeout
    try:
        while proc.poll() is None:
            if mono() > end:
                raise VmError('timeout: the build VM did not power off in %d s' % timeout)
            sleep(1)
        return proc.returncode
    finally:
        if proc.poll() is None:
            proc.kill()


def ensure_base(cache, distro, spec, packages, mem=1024, cpus=2):
    image, checksum = ensure_image(cache, distro, spec)
    key, pub = ensure_ssh_key(cache)
    bkey = base_key(checksum, packages)
    path = os.path.join(sub(cache, 'bases'), '%s-%s.qcow2' % (distro, bkey))
    if os.path.exists(path):
        return path, bkey, key, pub
    with lock(cache, 'base-%s-%s' % (distro, bkey)):
        if not os.path.exists(path):
            log('building base %s (%s)' % (distro, bkey))
            tmp = tmp_name(path)
            seed = tmp + '.seed'
            try:
                shutil.copyfile(image, tmp)
                code, out = sh(['qemu-img', 'resize', '-q', tmp, '8G'])
                if code != 0:
                    raise VmError('qemu-img resize failed: ' + out.strip())
                make_seed(seed, pub, 'vmcheck-build-' + bkey, packages, poweroff=True)
                sock = tmp + '.sock'
                boot_and_wait_off(qemu_argv(tmp, seed, max(mem, 1024), cpus, sock), 900)
                os.replace(tmp, path)
            finally:
                for p in (tmp, seed, tmp + '.sock'):
                    if os.path.exists(p):
                        os.remove(p)
    return path, bkey, key, pub


def ensure_snapshot(cache, distro, spec, base, bkey, key, pub, seed, mem, cpus):
    skey = snap_key(bkey, qemu_version(), cpu_model(), mem, cpus)
    path = os.path.join(sub(cache, 'snaps'), '%s-%s.qcow2' % (distro, skey))
    if os.path.exists(path):
        return path
    with lock(cache, 'snap-%s-%s' % (distro, skey)):
        if os.path.exists(path):
            return path
        log('building snapshot %s (%s)' % (distro, skey))
        tmp = tmp_name(path)
        try:
            make_overlay(base, tmp)
            vm = Vm(cache, distro, spec, base, None, seed, key, mem, cpus)
            vm.work = tempfile.mkdtemp(prefix='vmsnap-')
            try:
                sock = os.path.join(vm.work, 'mon.sock')
                vm.proc = spawn(qemu_argv(tmp, seed, mem, cpus, sock))
                vm.port = free_port()
                vm._wait_monitor(sock)
                monitor_cmd(sock, 'hostfwd_add tcp:127.0.0.1:%d-:22' % vm.port)
                vm._wait_ssh()
                out = monitor_cmd(sock, 'savevm ' + SNAP_NAME, timeout=300)
                if 'error' in out.lower():
                    raise VmError('savevm failed: ' + out.strip())
                monitor_cmd(sock, 'quit')
            finally:
                vm.close()
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
    return path


def prepare(cache, distro, spec, packages, resume, mem, cpus):
    base, bkey, key, pub = ensure_base(cache, distro, spec, packages, mem, cpus)
    seed = ensure_idle_seed(cache, pub)
    snap = ensure_snapshot(cache, distro, spec, base, bkey, key, pub, seed, mem, cpus) if resume else None
    return {'base': base, 'base_key': bkey, 'snapshot': snap, 'seed': seed, 'key': key}


# ---- commands ----

def open_vm(args, distros):
    if args.distro not in distros:
        raise VmError('unknown distro %s (known: %s)' % (args.distro, ', '.join(sorted(distros))))
    cache = cache_dir(args.cache)
    spec = distros[args.distro]
    warn_memory(args.mem)
    info = prepare(cache, args.distro, spec, args.packages.split(), args.resume, args.mem, args.cpus)
    return Vm(cache, args.distro, spec, info['base'], info['snapshot'], info['seed'], info['key'],
              args.mem, args.cpus, args.resume, args.timeout)


def cmd_prepare(args, distros):
    if args.distro not in distros:
        raise VmError('unknown distro ' + args.distro)
    cache = cache_dir(args.cache)
    t0 = mono()
    info = prepare(cache, args.distro, distros[args.distro], args.packages.split(), args.resume, args.mem, args.cpus)
    print('base: %s\nsnapshot: %s\nseconds: %.1f' % (info['base'], info['snapshot'] or '-', mono() - t0))
    return 0


def cmd_run(args, distros):
    steps, code = [], 0
    t0 = mono()
    try:
        with open_vm(args, distros) as vm:
            for item in args.copy:
                local, _, remote = item.partition(':')
                if not remote:
                    raise VmError('--copy needs LOCAL:REMOTE, got ' + item)
                vm.copy(local, remote)
            jobs = []
            for script in args.script:
                vm.copy(script, '/tmp/' + os.path.basename(script))
                jobs.append('sh /tmp/' + shlex.quote(os.path.basename(script)))
            if args.cmd:
                jobs.append(shlex.join(args.cmd))
            for job in jobs:
                t1 = mono()
                rc, out = vm.ssh(job, timeout=args.timeout)
                print(out, end='' if out.endswith('\n') or not out else '\n')
                steps.append({'cmd': job, 'code': rc, 'seconds': round(mono() - t1, 2)})
                if rc != 0:
                    code = rc
                    break
            timings = dict(vm.timings)
    except VmError as e:
        log(str(e))
        code, timings = 1, {}
        steps.append({'error': str(e)})
    if args.json:
        with open(args.json, 'w', encoding='utf-8') as f:
            json.dump({'distro': args.distro, 'resume': args.resume, 'code': code, 'timings': timings, 'steps': steps,
                       'total_s': round(mono() - t0, 2)}, f, indent=2)
    return code


def count_avc(text):
    return [l for l in text.splitlines() if 'avc:' in l.lower() and 'denied' in l.lower()]


AVC_CMD = ("if command -v ausearch >/dev/null 2>&1; then sudo ausearch -m avc -ts boot 2>&1; "
           "elif [ -r /var/log/audit/audit.log ]; then sudo cat /var/log/audit/audit.log; "
           "else sudo journalctl -b --no-pager 2>&1; fi; true")


def selinux_verdict(mode, avc_lines):
    """Return None when all is well, else a plain reason."""
    if mode.strip() != 'Enforcing':
        return 'SELinux is %s, not Enforcing' % (mode.strip() or 'unknown')
    if avc_lines:
        return '%d AVC denial(s) since boot:\n%s' % (len(avc_lines), '\n'.join(avc_lines))
    return None


def cmd_selinux(args, distros):
    args.copy, args.script, args.cmd = [], [], []
    try:
        with open_vm(args, distros) as vm:
            rc, mode = vm.ssh('getenforce')
            if rc != 0:
                raise VmError('getenforce failed: ' + mode.strip())
            reason = selinux_verdict(mode, [])
            if reason:
                print('FAIL: ' + reason)
                return 1
            files = [(args.install, 'dnf -y install /tmp/%s')]
            if args.module:
                files.append((args.module, 'semodule -i /tmp/%s'))
            for local, tmpl in files:
                name = os.path.basename(local)
                vm.copy(local, '/tmp/' + name)
                rc, out = vm.ssh('sudo ' + tmpl % shlex.quote(name), timeout=args.timeout)
                print(out, end='')
                if rc != 0:
                    print('FAIL: %s failed with code %d' % (tmpl.split()[0] + ' ' + tmpl.split()[1], rc))
                    return 1
            if args.module:
                rc, out = vm.ssh('sudo semodule -l')
                modname = os.path.splitext(os.path.basename(args.module))[0]
                if modname not in out.split():
                    print('FAIL: module %s is not listed by semodule -l' % modname)
                    return 1
                print('module listed: ' + modname)
            rc, out = vm.ssh(AVC_CMD, timeout=args.timeout)
            reason = selinux_verdict(mode, count_avc(out))
            if reason:
                print('FAIL: ' + reason)
                return 1
    except VmError as e:
        print('FAIL: ' + str(e))
        return 1
    print('PASS: Enforcing, install ok, 0 AVC denials')
    return 0


PRUNE_RE = re.compile(r'^(.+)-([0-9a-f]{16})\.qcow2$')


def cmd_prune(args, distros=None):
    cache = cache_dir(args.cache)
    removed = []
    for kind in ('images', 'bases', 'snaps'):
        d = os.path.join(cache, kind)
        if not os.path.isdir(d):
            continue
        groups = {}
        for n in os.listdir(d):
            m = PRUNE_RE.match(n)
            if m:
                groups.setdefault(m.group(1), []).append(os.path.join(d, n))
        for files in groups.values():
            files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
            removed += files[max(args.keep, 0):]
    day = now() - 86400
    for root, _dirs, names in os.walk(cache):
        for n in names:
            if '.tmp-' in n and os.path.getmtime(os.path.join(root, n)) < day:
                removed.append(os.path.join(root, n))
    for p in removed:
        with contextlib.suppress(OSError):
            os.remove(p)
        print('removed ' + p)
    print('pruned %d file(s)' % len(removed))
    return 0


def cmd_doctor(args, distros=None):
    problems = []
    kvm = os.access('/dev/kvm', os.R_OK | os.W_OK)
    print('/dev/kvm usable: %s' % ('yes' if kvm else 'no'))
    if not kvm:
        problems.append('/dev/kvm is not usable')
    for tool in ('qemu-system-x86_64', 'cloud-localds', 'qemu-img', 'ssh', 'scp', 'ssh-keygen'):
        found = shutil.which(tool)
        print('%s: %s' % (tool, found or 'missing'))
        if not found:
            problems.append(tool + ' is missing')
    cache = cache_dir(args.cache)
    ok = writable_dir(cache)
    print('cache %s writable: %s' % (cache, 'yes' if ok else 'no'))
    if not ok:
        problems.append('cache is not writable')
    else:
        print('free disk: %d GiB' % (shutil.disk_usage(cache).free >> 30))
    for p in problems:
        print('PROBLEM: ' + p)
    return 1 if problems else 0


def build_parser():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--cache', help='cache folder (default $VM_CACHE, /ci-tools/vm-cache, or ~/.cache/vm-check)')
    ap.add_argument('--images', help='extra distros file, same shape as vm-images.json')
    subs = ap.add_subparsers(dest='cmd_name', required=True)

    def common(p):
        p.add_argument('--distro', required=True)
        p.add_argument('--packages', default='', help='space-separated packages for the base')
        p.add_argument('--resume', action='store_true', help='use a saved running-VM snapshot')
        p.add_argument('--mem', type=int, default=1024, help='MiB')
        p.add_argument('--cpus', type=int, default=2)
        p.add_argument('--timeout', type=int, default=300, help='seconds for ssh and for each step')

    p = subs.add_parser('prepare')
    common(p)
    p.set_defaults(fn=cmd_prepare)
    p = subs.add_parser('run')
    common(p)
    p.add_argument('--copy', action='append', default=[], metavar='LOCAL:REMOTE')
    p.add_argument('--script', action='append', default=[], metavar='FILE')
    p.add_argument('--json', metavar='FILE')
    p.add_argument('cmd', nargs=argparse.REMAINDER, help='-- CMD...')
    p.set_defaults(fn=cmd_run)
    p = subs.add_parser('selinux')
    common(p)
    p.add_argument('--install', required=True, metavar='FILE.rpm')
    p.add_argument('--module', metavar='FILE.pp')
    p.set_defaults(fn=cmd_selinux)
    p = subs.add_parser('prune')
    p.add_argument('--keep', type=int, default=1)
    p.set_defaults(fn=cmd_prune)
    p = subs.add_parser('doctor')
    p.set_defaults(fn=cmd_doctor)
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    if getattr(args, 'cmd', None) and args.cmd[:1] == ['--']:
        args.cmd = args.cmd[1:]
    try:
        distros = load_images(args.images)
        return args.fn(args, distros)
    except VmError as e:
        log(str(e))
        return 1


if __name__ == '__main__':
    sys.exit(main())
