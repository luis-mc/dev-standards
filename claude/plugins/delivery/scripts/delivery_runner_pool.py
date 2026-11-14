#!/usr/bin/env python3
"""Shared CI pool and the guided CI setup behind it (DL30, contract: docs/features/delivery/shared-self-hosted-runners.md).

    delivery_runner_pool.py detect  [--json]
    delivery_runner_pool.py sizing  [--total-gib N --used-gib N --cpus N] [--docker-gib N] [--largest-shard-gib N]   (measured when not given)
    delivery_runner_pool.py plan    [--repos a/b,c/d] [--windows-repos e/f] [--pool NAME] [--browsers none|chromium] [--playwright-version X.Y.Z] [--repo-path DIR]   (repositories come from detect when not given)
    delivery_runner_pool.py verify  --repos a/b --pool NAME
    delivery_runner_pool.py doctor  [--json]

`detect` is read only. It never reads a `.credentials` file. `plan` only describes. `run` (called by
delivery_ci_setup.py) shows each step, runs it after a yes, asks again before anything is deleted (naming what goes),
prints elevated steps for the owner and checks them, and stops at the first failure with what is left.
Public repositories are refused (contract section 5). Standard library only.
"""
from __future__ import annotations

import argparse
import datetime
import glob
import json
import hashlib
import math
import os
import posixpath
import re
import secrets
import shutil
import subprocess
import sys
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

try:  # the load figures (DL-77); absent only on a broken install
    import load as LOAD
except Exception:  # noqa: BLE001
    LOAD = None

try:  # agent A's machine layer (DL32); absent on a branch that does not have it yet
    import machine_slots as MS
except Exception:  # noqa: BLE001
    MS = None

LABEL = 'dev.luismc.runner-pool'
TEMPLATES = os.path.join(os.path.dirname(HERE), 'templates', 'runner-pool')
MEM_PCT, CPU_PCT = 85, 60
VM_GIB, SIDECAR_GIB = 1.0, 1.0
MIN_RUNNER_VERSION = '2.329.0'  # GitHub refuses to register a runner below this
RUNNER_VERSION = '2.338.2'  # the pinned fallback, used when the release API cannot be reached
ROOT_NEEDS = re.compile(r'\bsudo\b|\bapt-get\b|\bapt\s+install\b|--with-deps|install-deps')  # a step that needs root
BROWSERS = ('none', 'chromium')  # the image option POOL_BROWSERS (DL67); none is the default
PLAYWRIGHT_VERSION = '1.65.0'  # the pinned fallback for the Chromium system libraries (DL69); keep the Dockerfile and compose defaults equal
LOCKFILES = ('pnpm-lock.yaml', 'package-lock.json', 'yarn.lock')
RUNNER_SHA256 = 'baebf204307bac6193480852732f0aba2ae97b6c5597c244f4d5558390147c40'  # its linux-x64 tarball
HOST_LOAD_FRESH_S = 60
PRIVATE_REFUSAL = 'refused: %s is a public repository. A self-hosted runner there could run code from a fork pull request on your machine.'


# --- the probe: every read of the machine goes through here (tests replace it) ----------------------------------------

class Probe:
    platform = sys.platform
    runner_dirs = ['C:/actions-runners', os.path.expanduser('~/actions-runner'), '/opt/actions-runner']
    wslconfig = os.path.join(os.path.expanduser('~'), '.wslconfig')

    def sh(self, argv, input=None, timeout=60):
        env = None
        if argv and argv[0] == 'docker':  # DL274: Git Bash on Windows would rewrite /dev/kvm into a Windows path
            env = dict(os.environ, MSYS_NO_PATHCONV='1')
        try:
            p = subprocess.run(argv, capture_output=True, text=True, input=input, timeout=timeout, env=env)
        except (OSError, subprocess.SubprocessError):
            return None
        return p.returncode, p.stdout

    def gh(self, args, input=None):
        return self.sh(['gh'] + list(args), input=input)

    def is_admin(self):
        """DL310: True when this process is an elevated Windows administrator. Always False elsewhere."""
        if not self.platform.startswith('win'):
            return False
        try:
            import ctypes
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:  # noqa: BLE001
            return False

    def gh_json(self, args):
        r = self.gh(args)
        if r is None:
            return None, 'gh cannot run'
        if r[0] != 0:
            return None, 'gh refused (admin rights needed?)'
        try:
            return json.loads(r[1] or 'null'), None
        except ValueError:
            return None, 'gh returned invalid JSON'

    def read_text(self, path):
        try:
            with open(path, encoding='utf-8-sig') as f:
                return f.read()
        except OSError:
            return None

    def listdir(self, path):
        try:
            return sorted(os.listdir(path))
        except OSError:
            return []

    def isfile(self, path):
        return os.path.isfile(path)

    def sleep(self, sec):
        time.sleep(sec)

    def python(self):
        return sys.executable

    def python_config(self):
        """DL339: the hook Python named in the machine config ("python" in machine.json) or DELIVERY_HOOK_PYTHON, else ''."""
        v = os.environ.get('DELIVERY_HOOK_PYTHON')
        if v:
            return v
        try:
            with open(os.path.join(self.machine_dir(), 'machine.json'), encoding='utf-8') as f:
                v = json.load(f).get('python')
        except (OSError, ValueError, AttributeError):
            return ''
        return v if isinstance(v, str) else ''

    def exists(self, path):
        return os.path.exists(path)

    def cpu_count(self):
        return os.cpu_count()

    def machine_dir(self):
        return str(MS.machine_dir()) if MS else os.environ.get('DELIVERY_MACHINE_DIR', '/etc/luismc-delivery')

    def memory_gib(self):
        """(total GiB, used GiB) of this machine, or None. Total from the OS; used = the load.py memory % of the total."""
        total = None
        if self.platform.startswith('win'):
            r = self.sh(['powershell', '-NoProfile', '-Command', '(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory'])
            if r and r[0] == 0 and r[1].strip().isdigit():
                total = int(r[1].strip()) / 2.0 ** 30
        elif self.platform == 'darwin':
            r = self.sh(['sysctl', '-n', 'hw.memsize'])
            if r and r[0] == 0 and r[1].strip().isdigit():
                total = int(r[1].strip()) / 2.0 ** 30
        else:
            m = re.search(r'MemTotal:\s+(\d+)', self.read_text('/proc/meminfo') or '')
            if m:
                total = int(m.group(1)) / 2.0 ** 20
        if total is None or LOAD is None:
            return None
        try:
            pct = float(LOAD.measure_now()['mem'])
        except Exception:  # noqa: BLE001
            return None
        return round(total, 1), round(total * pct / 100.0, 1)

    def host_load(self):
        """(figures, age in seconds) of the host-load file, or (None, None)."""
        if LOAD is None:
            return None, None
        try:
            return LOAD.read_host_load()
        except Exception:  # noqa: BLE001
            return None, None

    def wsl_vm_parts(self):
        """(working set GiB, private bytes GiB) of vmmem / vmmemWSL; (0.0, 0.0) when there is none or it cannot be read.
        DL177: Windows trims the working set, so it alone under-reads the VM; private bytes are steadier."""
        if not self.platform.startswith('win'):
            return 0.0, 0.0
        r = self.sh(['powershell', '-NoProfile', '-Command',
                     "$p = Get-Process -Name vmmem,vmmemWSL -ErrorAction SilentlyContinue; "
                     "($p | Measure-Object WorkingSet64 -Sum).Sum; ($p | Measure-Object PrivateMemorySize64 -Sum).Sum"])
        lines = [x.strip() for x in (r[1].splitlines() if r and r[0] == 0 else [])]
        nums = [x for x in lines if x]
        vals = [round(int(x) / 2.0 ** 30, 1) if x.isdigit() else 0.0 for x in nums[:2]]
        while len(vals) < 2:
            vals.append(0.0)
        return vals[0], vals[1]

    def wsl_vm_gib(self):
        """Memory held by the WSL VM in GiB: the larger of the vmmem working set and its private bytes (DL177); 0.0 when
        there is none or it cannot be read. detect_host also floors it at what the containers use."""
        return max(self.wsl_vm_parts())

    def docker_run(self, args, timeout=60):
        """Run `docker <args>`. On Windows try the docker CLI on PATH first (Docker Desktop installs it) and fall back to
        `wsl docker` only when that cannot run (DL177). Returns the sh result or None."""
        r = self.sh(['docker'] + list(args), timeout=timeout)
        if self.platform.startswith('win') and (r is None or r[0] != 0):
            r2 = self.sh(['wsl', 'docker'] + list(args), timeout=timeout)
            if r2 is not None and r2[0] == 0:
                return r2
        return r

    def docker_cpus(self):
        """CPUs Docker sees (`docker info --format {{.NCPU}}`), or None when Docker cannot be read."""
        r = self.docker_run(['info', '--format', '{{.NCPU}}'])
        text = r[1].replace('\x00', '').strip() if r and r[0] == 0 else ''
        return int(text) if text.isdigit() and int(text) > 0 else None

    def container_gib(self):
        """{'pool': GiB used by this pool's containers, 'other': GiB used by other containers, 'others': [names]}.
        Reads `docker ps` and `docker stats` (Windows: the docker CLI first, then inside WSL). Zeros when Docker cannot be read."""
        names = self.docker_run(['ps', '--format', '{{.Names}}\t{{.Label "' + LABEL + '"}}\t{{.Label "com.docker.compose.project"}}'])
        stats = self.docker_run(['stats', '--no-stream', '--format', '{{.Name}}\t{{.MemUsage}}'])
        out = {'pool': 0.0, 'other': 0.0, 'others': []}
        if not names or names[0] != 0:
            return out
        mine = {}
        for line in names[1].replace('\x00', '').splitlines():
            cols = line.rstrip('\r').split('\t')
            if cols and cols[0]:
                # DL94: the pool's db container has no label; its compose project (pool-<name>) says it is the pool's.
                mine[cols[0]] = (len(cols) > 1 and cols[1].strip() != '') or (len(cols) > 2 and cols[2].strip().startswith('pool-'))
        used = {}
        for line in (stats[1].replace('\x00', '') if stats and stats[0] == 0 else '').splitlines():
            cols = line.rstrip('\r').split('\t')
            m = re.match(r'\s*([0-9.]+)\s*([KMG]i?B|B)', cols[1]) if len(cols) > 1 else None
            if m:
                used[cols[0]] = float(m.group(1)) * {'B': 1.0, 'K': 2.0 ** 10, 'M': 2.0 ** 20, 'G': 2.0 ** 30}[m.group(2)[0]] / 2.0 ** 30
        for name, is_pool in mine.items():
            if is_pool:
                out['pool'] += used.get(name, 0.0)
            else:
                out['other'] += used.get(name, 0.0)
                out['others'].append(name)
        out['pool'], out['other'] = round(out['pool'], 1), round(out['other'], 1)
        return out


# --- detect (read only) -----------------------------------------------------------------------------------------------

def _flatten(data):
    if isinstance(data, list) and data and all(isinstance(x, list) for x in data):
        return [y for x in data for y in x]
    return data if isinstance(data, list) else []


def _workflows_self_hosted(probe, repo):
    """True when a workflow file of the repository names the label `self-hosted` (read only)."""
    listing, _why = probe.gh_json(['api', 'repos/%s/contents/.github/workflows' % repo])
    for f in listing if isinstance(listing, list) else []:
        name = f.get('name') if isinstance(f, dict) else None
        if not name or not name.endswith(('.yml', '.yaml')):
            continue
        r = probe.gh(['api', 'repos/%s/contents/.github/workflows/%s' % (repo, name), '-H', 'Accept: application/vnd.github.raw'])
        if r and r[0] == 0 and 'self-hosted' in (r[1] or ''):
            return True
    return False


def detect_github(probe):
    data, why = probe.gh_json(['api', '-X', 'GET', 'user/repos', '-f', 'affiliation=owner,collaborator,organization_member',
                               '-f', 'per_page=100', '--paginate', '--slurp'])
    if data is None:
        return {'repos': [], 'error': why}
    repos = []
    for r in _flatten(data):
        if not isinstance(r, dict) or not (r.get('permissions') or {}).get('admin'):
            continue
        name = r.get('full_name')
        entry = {'repo': name, 'private': bool(r.get('private')), 'runners': [], 'error': None}
        entry['self_hosted_workflows'] = _workflows_self_hosted(probe, name) if entry['private'] else False
        rd, why = probe.gh_json(['api', 'repos/%s/actions/runners?per_page=100' % name])
        if rd is None:
            entry['error'] = why
        else:
            for x in rd.get('runners', []) if isinstance(rd, dict) else []:
                entry['runners'].append({'id': x.get('id'), 'name': x.get('name'), 'os': x.get('os'), 'status': x.get('status'),
                                         'busy': bool(x.get('busy')), 'labels': [l.get('name') for l in x.get('labels', [])
                                                                                  if isinstance(l, dict)]})
        repos.append(entry)
    return {'repos': repos, 'error': None}


def _norm(path):
    return (path or '').replace('\\', '/')


def service_folder(image_path):
    """The runner folder from a service's image path: `"C:\\x\\app1\\bin\\RunnerService.exe"` gives `C:/x/app1`."""
    text = (image_path or '').strip()
    exe = text[1:text.index('"', 1)] if text.startswith('"') and '"' in text[1:] else \
        (text[:text.lower().index('.exe') + 4] if '.exe' in text.lower() else text.split(' ')[0])
    d = posixpath.dirname(_norm(exe))
    return posixpath.dirname(d) if posixpath.basename(d).lower() == 'bin' else d


def detect_services(probe):
    out = []
    if probe.platform.startswith('win'):
        r = probe.sh(['powershell', '-NoProfile', '-Command',
                      "Get-CimInstance Win32_Service -Filter \"Name like 'actions.runner.%'\" | "
                      'Select-Object Name,State,PathName,StartName | ConvertTo-Json'])
        if r and r[0] == 0 and r[1].strip():
            try:
                data = json.loads(r[1])
            except ValueError:
                data = []
            for x in [data] if isinstance(data, dict) else data:
                out.append({'name': x.get('Name'), 'status': str(x.get('State', x.get('Status'))), 'kind': 'windows-service',
                            'folder': service_folder(x.get('PathName')) or None, 'account': x.get('StartName')})
    else:
        r = probe.sh(['systemctl', 'list-units', 'actions.runner.*', '--all', '--no-legend', '--plain'])
        for line in (r[1] if r and r[0] == 0 else '').splitlines():
            parts = line.split()
            if parts:
                out.append({'name': parts[0], 'status': parts[3] if len(parts) > 3 else '', 'kind': 'systemd'})
    return out


def detect_folders(probe, services=()):
    """Runner folders, found by their `.runner` file, plus the folder of each runner service (from its image path).
    `.credentials` is never opened."""
    out, seen = [], set()
    svc = {x['folder'] for x in services if x.get('folder')}
    cands = []
    for base in probe.runner_dirs:
        cands += [base] + [base.rstrip('/') + '/' + n for n in probe.listdir(base)]
    cands += sorted(svc)
    for d in cands:
        if d in seen:
            continue
        seen.add(d)
        text = probe.read_text(d + '/.runner') if probe.isfile(d + '/.runner') else None
        if text is None and d not in svc:
            continue
        try:
            j = json.loads((text or '{}').lstrip('\ufeff'))
        except ValueError:
            j = {}
        url = j.get('gitHubUrl') or ''
        out.append({'path': d, 'agent_id': j.get('agentId'), 'name': j.get('agentName'),
                    'repo': url.replace('https://github.com/', '') or None})
    return out


def detect_containers(probe):
    """Containers from the Docker on this machine and, on Windows, from the Docker inside WSL (`wsl docker ...`, read only).
    `via` is '' or 'wsl'; a container seen by both is listed once."""
    out, seen = [], set()
    prefixes = [('', [])] + ([('wsl', ['wsl'])] if probe.platform.startswith('win') else [])
    for via, pre in prefixes:
        for argv, how in ((['docker', 'ps', '-a', '--filter', 'label=' + LABEL, '--format', '{{.ID}}\t{{.Names}}\t{{.Status}}'], 'label'),
                          (['docker', 'ps', '-a', '--format', '{{.ID}}\t{{.Names}}\t{{.Command}}'], 'command')):
            r = probe.sh(pre + argv)
            for line in (r[1].replace('\x00', '') if r and r[0] == 0 else '').splitlines():
                cols = line.rstrip('\r').split('\t')
                if len(cols) < 3 or cols[0] in seen:
                    continue
                if how == 'command' and 'Runner.Listener' not in cols[2]:
                    continue
                seen.add(cols[0])
                out.append({'id': cols[0], 'name': cols[1], 'detail': cols[2], 'found_by': how, 'pool': how == 'label', 'via': via})
    return out


def detect_wsl(probe):
    text = probe.read_text(probe.wslconfig)
    out = {'file': probe.wslconfig, 'exists': text is not None, 'memory': None, 'processors': None}
    for line in (text or '').splitlines():
        m = re.match(r'\s*(memory|processors)\s*=\s*([0-9.]+)\s*(GB|MB)?', line, re.I)
        if m:
            out[m.group(1).lower()] = float(m.group(2)) / (1024 if (m.group(3) or '').upper() == 'MB' else 1) \
                if m.group(1).lower() == 'memory' else int(float(m.group(2)))
    return out


HOST_LOAD_MAX_AGE = 60.0  # DL177: a host-load file older than this (seconds) is ignored
HOST_SAMPLES, HOST_SAMPLE_GAP = 5, 1  # DL176: memory is read this many times, this many seconds apart; the median is used


def median(values):
    v = sorted(values)
    if not v:
        return None
    mid = len(v) // 2
    return v[mid] if len(v) % 2 else (v[mid - 1] + v[mid]) / 2.0


def detect_host(probe, samples=None, gap=None):
    """This machine's figures for sizing: platform, python, machine folder, CPUs, total and used GiB (None when unmeasurable).

    DL176: `used_gib` is the median of several samples taken `gap` seconds apart (about 5, 1 s), so another program's short
    spike does not cut the room. `used_samples` lists them."""
    n = max(1, samples if samples is not None else HOST_SAMPLES)
    gap = HOST_SAMPLE_GAP if gap is None else gap
    mem, vm, used_list = None, 0.0, []
    for i in range(n):
        if i:
            probe.sleep(gap)
        m, v = probe.memory_gib(), probe.wsl_vm_gib()
        if m is None:
            continue
        if mem is None:
            mem = m
        used_list.append((m[1], v))
    box = probe.container_gib()
    # DL177: the VM holds at least what the containers use, whatever the trimmed working set says.
    floor = round(box['pool'] + box['other'], 1)
    used_list = [(u, max(v, floor)) for u, v in used_list]
    vm = max([v for _u, v in used_list] or [0.0])
    parts = probe.wsl_vm_parts() if hasattr(probe, 'wsl_vm_parts') else (0.0, 0.0)
    used, load_used, decided, load_state = None, None, 'median', 'missing'
    if used_list:
        # The WSL VM holds the pool and every other container: leave it out of "used". With no VM (native Linux), leave
        # out the pool's own containers instead. A rerun then sees the same figure as the first run.
        used = round(max(0.0, median([u - (v if v > 0 else box['pool']) for u, v in used_list])), 1)
        figures, age = probe.host_load()
        if figures and age is not None and age <= HOST_LOAD_MAX_AGE and mem:
            # DL177: the host-load task's last sample; "fits" is judged against the larger of it and the median.
            load_state = 'fresh'
            load_used = round(max(0.0, mem[0] * figures['mem'] / 100.0 - (vm if vm > 0 else box['pool'])), 1)
            if load_used > used:
                used, decided = load_used, 'host-load file'
        elif figures:
            load_state = 'stale'
    return {'platform': probe.platform, 'python': getattr(probe, 'python_config', lambda: '')() or '', 'python_exe': _probe_python(probe), 'machine_dir': probe.machine_dir(), 'cpus': probe.cpu_count(), 'docker_cpus': docker_ncpu(probe),
            'total_gib': mem[0] if mem else None, 'used_gib': used, 'wsl_vm_gib': vm,
            'wsl_working_set_gib': parts[0], 'wsl_private_gib': parts[1], 'containers_gib': floor,
            'used_samples': [round(max(0.0, u - (v if v > 0 else box['pool'])), 1) for u, v in used_list],
            'load_used_gib': load_used, 'load_file': load_state, 'used_decided_by': decided,
            'other_containers_gib': box['other'], 'other_containers': box['others']}


def detect(probe=None, json=False):
    """What exists, read only. `json=True` returns the same facts as a JSON string (contract 12.3)."""
    probe = probe or Probe()
    services = detect_services(probe)
    found = {'github': detect_github(probe), 'services': services, 'folders': detect_folders(probe, services),
             'containers': detect_containers(probe), 'wsl': detect_wsl(probe), 'host': detect_host(probe)}
    if json:
        import json as _json
        return _json.dumps(found, indent=2)
    return found


def docker_ncpu(probe):
    """CPUs Docker sees: `docker info` when Docker runs, else the `.wslconfig` processors value, else the host CPUs."""
    n = probe.docker_cpus()
    if n:
        return n
    procs = detect_wsl(probe).get('processors')
    return procs or probe.cpu_count()


MIN_GIB_PER_CPU = 1.5  # DL79: a pool CPU gets at least this much memory (hosted runners have about 4 GiB per core)
WARN_GIB_PER_CPU = 1.0  # the doctor warns below this
MIN_POOL_GIB, MIN_POOL_CPUS = 4.0, 2.0  # DL94: the setup refuses a cap below this
WARN_GIB_PER_AGENT = 4.0  # DL83: the doctor warns when POOL_MEM over the agent count is below this


def cap_mem_cpus(cpus, mem_gib):
    """DL79: the CPU cap never exceeds floor(memory / MIN_GIB_PER_CPU), and never goes below 1."""
    if mem_gib is None:
        return cpus
    return max(1, min(cpus, math.floor(mem_gib / MIN_GIB_PER_CPU)))


def cap_cpus(requested, ncpu):
    """Docker refuses a CPU limit equal to the CPUs it sees, so the cap stays at NCPU - 1 (never below 1)."""
    if not ncpu:
        return requested
    return max(1, min(requested, int(ncpu) - 1))


def env_number(value):
    """A number from a .env value such as "8.5g" or "4", else None."""
    try:
        return float(str(value).strip().rstrip('gG'))
    except (TypeError, ValueError):
        return None


def keep_owner_cap(cap, pool_env, resize=False, host_cpus=None, shrink=False):
    """B14: a rerun keeps the cap already in the pool's .env; the owner chose it. The measured cap replaces it only with
    `resize`, or when the kept cap is under the floor; `reason` then says why. The kept cap sets the WSL values too."""
    if not cap:
        return cap
    env = pool_env or {}
    mem, cpus = env_number(env.get('POOL_MEM')), env_number(env.get('POOL_CPUS'))
    if mem is None or cpus is None:
        return dict(cap, source='measured')
    if resize:
        if not shrink and cap.get('ok') and (cap['mem_gib'] < mem or cap['cpus'] < cpus):
            return dict(cap, ok=False, source='measured', message=(
                '--resize would lower the pool from POOL_MEM %gg and POOL_CPUS %g in .env to %gg and %g (measured now). '
                'Nothing was changed. Close other programs and try again, give the size you want with --pool-gib and '
                '--pool-cpus, or pass --shrink if you want the lower cap.' % (mem, cpus, cap['mem_gib'], cap['cpus'])))
        return dict(cap, source='measured', reason='--resize: the measured cap replaces %g GiB and %g CPUs from .env'
                    % (mem, cpus))
    if mem < MIN_POOL_GIB or cpus < MIN_POOL_CPUS:
        return dict(cap, source='measured', reason='the cap in .env (%g GiB, %g CPUs) is under the floor of %g GiB and %g CPUs, '
                    'so the measured cap replaces it' % (mem, cpus, MIN_POOL_GIB, MIN_POOL_CPUS))
    procs = int(math.floor(cpus)) + 1
    if host_cpus:
        procs = max(1, min(procs, int(host_cpus)))
    return dict(cap, mem_gib=mem, cpus=cpus, ok=True, message='', source='kept',
                measured_cap={'mem_gib': cap.get('mem_gib'), 'cpus': cap.get('cpus')},
                wsl={'memory': int(math.ceil(mem + SIDECAR_GIB + VM_GIB)), 'processors': procs},
                cpus_text='cap kept from .env (measured now: %s GiB, %s CPUs; --resize uses that)'
                          % (cap.get('mem_gib'), cap.get('cpus')))


# --- sizing (section 6.4) ---------------------------------------------------------------------------------------------

def sizing(total_gib, used_gib, cpus, docker_gib=None, largest_shard_gib=None, sidecar_gib=SIDECAR_GIB, vm_gib=VM_GIB,
           other_gib=0.0, others_run=False, wsl_current=None, docker_cpus=None):
    """Pool cap = the smaller of the memory room and Docker's ceiling, minus the sidecar and the VM. CPU = 60% of the CPUs.

    `used_gib` is what non-WSL processes use (the WSL VM and the pool's containers are not in it), so a rerun gives the
    same cap. When other containers run in WSL (`others_run`), the pool leaves them `other_gib` and the WSL memory written
    is never below `wsl_current` nor below what they use plus this pool's cap."""
    room = total_gib * MEM_PCT / 100.0 - used_gib
    ceiling = room if docker_gib is None else min(room, docker_gib - (other_gib if others_run else 0.0))
    mem = math.floor((ceiling - sidecar_gib - vm_gib) * 2) / 2.0
    # DL94: a low WSL ceiling (an earlier run wrote it, or the file is old) must not shrink the pool: the setup raises the ceiling
    # in .wslconfig. Size up to the floor when the machine has the room.
    if mem < MIN_POOL_GIB <= math.floor((room - sidecar_gib - vm_gib) * 2) / 2.0:
        mem = MIN_POOL_GIB
    cpu = max(1.0, math.floor(cpus * CPU_PCT / 100.0 * 2) / 2.0)
    host_cpus = int(cpus)
    procs = int(math.floor(cpu)) + 1  # headroom: Docker refuses a CPU limit equal to the VM's CPUs
    if procs > host_cpus:
        cpu = max(1.0, cpu - 1)
        procs = int(math.floor(cpu)) + 1
    procs = max(1, min(procs, host_cpus))
    cpu = cap_cpus(cpu, docker_cpus)
    cpu = cap_mem_cpus(cpu, mem)
    wsl_mem = int(math.ceil(mem + sidecar_gib + vm_gib))
    if others_run:
        if wsl_current is not None:
            wsl_mem = max(wsl_mem, int(math.ceil(wsl_current)))
        wsl_mem = max(wsl_mem, int(math.ceil(other_gib + mem + sidecar_gib + vm_gib)))
    out = {'mem_gib': mem, 'cpus': cpu, 'memory_room_gib': round(room, 1), 'ok': True, 'message': '',
           'cpus_text': 'cpus %g (%g GiB at %g GiB per CPU)' % (cpu, mem, MIN_GIB_PER_CPU),
           'wsl': {'memory': wsl_mem, 'processors': procs}}
    if mem <= 0:
        out.update(ok=False, message='No memory is left for the pool (room %.1f GiB). Close other programs or raise the '
                                     'WSL memory in .wslconfig, then run the setup again.' % room)
    elif largest_shard_gib is not None and mem < largest_shard_gib:
        out.update(ok=False, message='The pool cap (%.1f GiB) is below the largest Linux shard (%.1f GiB). Lower that '
                                     'shard\'s memory_gib in ci-shards.json, or free memory on this machine.'
                                     % (mem, largest_shard_gib))
    elif 0 < mem and (mem < MIN_POOL_GIB or cpu < MIN_POOL_CPUS):
        out.update(ok=False, message='The pool cap would be %g GiB and %g CPUs, below the floor of %g GiB and %g CPUs: a frozen '
                                     'install is killed for memory under it. This machine needs about %g GiB of free memory '
                                     '(the pool also leaves 2 GiB for the sidecar and the VM) and at least %d CPUs for Docker. '
                                     'Close other programs and run the setup again.'
                                     % (mem, cpu, MIN_POOL_GIB, MIN_POOL_CPUS, MIN_POOL_GIB + 2, MIN_POOL_CPUS + 1))
    return out


def measured_sizing(found, total_gib=None, used_gib=None, cpus=None, docker_gib=None, largest_shard_gib=None):
    """Sizing with what the owner gave and, for the rest, what detect measured (memory, CPUs, the `.wslconfig` memory as
    Docker's ceiling). Returns the sizing dict plus `measured` (the inputs used), or None when memory cannot be measured."""
    host = found.get('host') or {}
    total = total_gib if total_gib is not None else host.get('total_gib')
    used = used_gib if used_gib is not None else host.get('used_gib')
    n = cpus if cpus is not None else host.get('cpus')
    docker = docker_gib if docker_gib is not None else (found.get('wsl') or {}).get('memory')
    if total is None or n is None:
        return None
    others = host.get('other_containers') or []
    res = sizing(total, used or 0.0, n, docker, largest_shard_gib, other_gib=host.get('other_containers_gib') or 0.0,
                 others_run=bool(others), wsl_current=(found.get('wsl') or {}).get('memory'),
                 docker_cpus=host.get('docker_cpus'))
    res['measured'] = {'total_gib': total, 'used_gib': used or 0.0, 'cpus': n, 'docker_gib': docker,
                       'other_containers_gib': host.get('other_containers_gib') or 0.0,
                       'budget_gib': round(total * MEM_PCT / 100.0, 1), 'room_gib': res['memory_room_gib'],
                       'samples': len(host.get('used_samples') or []),
                       'vm_gib': host.get('wsl_vm_gib'), 'working_set_gib': host.get('wsl_working_set_gib'),
                       'private_gib': host.get('wsl_private_gib'), 'containers_gib': host.get('containers_gib'),
                       'load_used_gib': host.get('load_used_gib'), 'load_file': host.get('load_file'),
                       'decided_by': host.get('used_decided_by') if used_gib is None else 'your number'}
    return res


def owner_target(cap, found, pool_gib=None, pool_cpus=None, largest_shard_gib=None):
    """DL176: the owner's own pool size (--pool-gib, --pool-cpus). It is used as given when it fits the memory budget
    (85% of the machine, leaving the sidecar and the VM), the CPU budget (60%) and the floors; else the cap comes back
    with ok False and a message that names the budget that is short. The `.wslconfig` memory rises to fit. A target
    given for one number leaves the other as `cap` has it."""
    if pool_gib is None and pool_cpus is None:
        return cap
    if not cap or not cap.get('measured'):
        return dict(cap or {}, ok=False, message='The pool size you gave cannot be checked: this machine\'s memory or CPUs '
                    'could not be measured. Give --total-gib and --cpus.')
    m = cap['measured']
    whole = lambda v: int(v) if float(v) == int(v) else float(v)  # noqa: E731  (12.0 prints as 12)
    mem = whole(pool_gib) if pool_gib is not None else cap.get('mem_gib')
    cpus = whole(pool_cpus) if pool_cpus is not None else cap.get('cpus')
    host = found.get('host') or {}
    others = host.get('other_containers') or []
    other_gib = (host.get('other_containers_gib') or 0.0) if others else 0.0
    wsl_mem = int(math.ceil(mem + SIDECAR_GIB + VM_GIB))
    if others:
        wsl_mem = max(wsl_mem, int(math.ceil(other_gib + mem + SIDECAR_GIB + VM_GIB)))
    wsl_cur = (found.get('wsl') or {}).get('memory')
    room, budget = m['room_gib'], m['budget_gib']
    cpu_budget = max(1.0, math.floor(m['cpus'] * CPU_PCT / 100.0 * 2) / 2.0)
    problems = []
    if wsl_mem > room:
        problems.append('Memory budget short: a pool of %g GiB needs %d GiB for the WSL VM (pool, %g GiB sidecar, %g GiB VM'
                        ' headroom%s), but the room is %.1f GiB (%d%% of %.1f GiB = %.1f GiB, minus %.1f GiB used outside WSL).'
                        % (mem, wsl_mem, SIDECAR_GIB, VM_GIB, ', other containers' if others else '', room, MEM_PCT,
                           m['total_gib'], budget, m['used_gib']))
    if cpus > cpu_budget:
        problems.append('CPU budget short: %g pool CPUs is over %g, which is %d%% of this machine\'s %g CPUs.'
                        % (cpus, cpu_budget, CPU_PCT, m['cpus']))
    if mem < MIN_POOL_GIB or cpus < MIN_POOL_CPUS:
        problems.append('Floor: the pool needs at least %g GiB and %g CPUs; you gave %g GiB and %g CPUs.'
                        % (MIN_POOL_GIB, MIN_POOL_CPUS, mem, cpus))
    if cpus > 0 and mem / cpus < MIN_GIB_PER_CPU:
        fit = int(math.floor(mem / MIN_GIB_PER_CPU))
        problems.append('Memory per CPU short: %g GiB for %g CPUs is under %g GiB per CPU (needs at least %g GiB). '
                        'Nearest sizes that pass: %g GiB fits %d CPUs; %g CPUs needs %g GiB.'
                        % (mem, cpus, MIN_GIB_PER_CPU, math.ceil(cpus * MIN_GIB_PER_CPU * 2) / 2.0,
                           mem, fit, cpus, math.ceil(cpus * MIN_GIB_PER_CPU * 2) / 2.0))
    if largest_shard_gib is not None and mem < largest_shard_gib:
        problems.append('The pool (%g GiB) is below the largest Linux shard (%.1f GiB).' % (mem, largest_shard_gib))
    if problems:
        return dict(cap, ok=False, message=' '.join(problems) + ' Nothing was changed.')
    procs = min(int(math.floor(cpus)) + 1, int(m['cpus'])) if m['cpus'] else int(math.floor(cpus)) + 1
    return dict(cap, mem_gib=mem, cpus=cpus, ok=True, message='', source='target',
                wsl={'memory': wsl_mem, 'processors': max(1, procs)},
                cpus_text='size set by --pool-gib/--pool-cpus',
                reason='the pool size you gave (%g GiB, %g CPUs) replaces the cap in .env' % (mem, cpus))


def resolve_cap(found, total_gib=None, used_gib=None, cpus=None, docker_gib=None, largest_shard_gib=None, resize=False,
                shrink=False, pool_gib=None, pool_cpus=None):
    """DL176: the cap for a plan: measured, then the .env cap kept (or replaced by --resize, which refuses to lower it
    without --shrink), then the owner's --pool-gib/--pool-cpus. None when memory or CPUs cannot be measured."""
    cap = measured_sizing(found, total_gib, used_gib, cpus, docker_gib, largest_shard_gib)
    cap = keep_owner_cap(cap, found.get('pool_env'), resize, (found.get('host') or {}).get('cpus'), shrink)
    if pool_gib is not None or pool_cpus is not None:
        env = found.get('pool_env') or {}
        if cap is not None and cap.get('measured'):
            # a number the owner did not give stays as the .env has it, else as measured
            cap = dict(cap, ok=True, message='')
            if cap.get('source') != 'kept':
                if env_number(env.get('POOL_MEM')) is not None and pool_gib is None:
                    cap['mem_gib'] = env_number(env.get('POOL_MEM'))
                if env_number(env.get('POOL_CPUS')) is not None and pool_cpus is None:
                    cap['cpus'] = env_number(env.get('POOL_CPUS'))
        cap = owner_target(cap, found, pool_gib, pool_cpus, largest_shard_gib)
    return cap


def derive_repos(found):
    """(linux repos, windows repos) from detect: every private repository that has a runner or a workflow that names
    `self-hosted`. Windows: a repository with a runner whose OS is Windows. A repository whose only runners are Windows
    ones, with no such workflow, gets no Linux pool agent."""
    linux, windows = [], []
    for r in found['github']['repos']:
        if r.get('private') is not True:
            continue
        runners = r['runners']
        flagged = bool(r.get('self_hosted_workflows'))
        if not runners and not flagged:
            continue
        if any(str(x.get('os')).lower() == 'windows' for x in runners):
            windows.append(r['repo'])
        if flagged or any(str(x.get('os')).lower() != 'windows' for x in runners):
            linux.append(r['repo'])
    return linux, windows


# --- plan -------------------------------------------------------------------------------------------------------------

def slug_of(repo):
    return re.sub(r'[^a-z0-9]+', '-', repo.split('/')[-1].lower()).strip('-')[:30] or 'repo'


def _step(sid, title, action, **kw):
    s = {'id': sid, 'title': title, 'action': action, 'delete': False, 'names': [], 'elevated': False, 'printed': [],
         'state': 'todo'}
    s.update(kw)
    return s


def _pool_has(found, pool, repo):
    """True when the pool already has an online agent for this repo with the pool label."""
    for r in found['github']['repos']:
        if r['repo'] == repo:
            return any(_has_label(x['labels'], 'pool-%s' % pool) and x['status'] == 'online' for x in r['runners'])
    return False


def _has_label(labels, label):
    """GitHub labels are case-insensitive."""
    return label.lower() in {str(l).lower() for l in labels or []}


def _winpath(path):
    return str(path).replace('/', '\\')


LOOP_SCRIPT = """\
import os
import sys
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import load  # noqa: E402

while True:  # one sample every 15 seconds; the task starts this at boot and keeps it running
    try:
        load.write_host_load()
    except Exception:
        pass
    time.sleep(15)
"""


def _gb(value):
    return 'unset' if value is None else '%sGB' % (int(value) if float(value) == int(value) else value)


def read_pool_env(probe, pool):
    """The KEY=value lines of the pool's .env (empty when there is none)."""
    out = {}
    for line in (probe.read_text(os.path.join(pool_dir(pool), '.env')) or '').splitlines():
        k, sep, v = line.partition('=')
        if sep:
            out[k.strip()] = v.strip()
    return out


def _wsl_values(found, cap):
    """(memory GiB, processors) to write, and whether `.wslconfig` already has at least that."""
    w = (cap or {}).get('wsl')
    if not w:
        return None, False
    cur = found.get('wsl') or {}
    enough = cur.get('memory') is not None and cur['memory'] >= w['memory'] and \
        cur.get('processors') is not None and cur['processors'] >= w['processors']
    # B14: the setup never lowers a value already in .wslconfig; lowering it is the owner's own edit.
    w = dict(w)
    if cur.get('memory') is not None:
        w['memory'] = max(w['memory'], int(math.ceil(cur['memory'])))
    if cur.get('processors'):
        w['processors'] = max(w['processors'], int(cur['processors']))
    return w, enough


def _pw_tuple(version):
    return tuple(int(x) for x in version.split('.'))


def valid_playwright_version(version):
    return bool(version) and re.fullmatch(r'\d+\.\d+\.\d+', version) is not None


_PNPM_PW = re.compile(r"(?:^|[\s'\"/])(?:@playwright/test|playwright)(?:@|/)(\d+\.\d+\.\d+)(?=[\s:'\"(_]|$)", re.M)
_YARN_HEAD = re.compile(r'(?:^|[\s"])(?:@playwright/test|playwright)@')
_YARN_VERSION = re.compile(r'^\s+version:?\s+"?(\d+\.\d+\.\d+)"?\s*$')


def playwright_in_pnpm(text):
    """The resolved Playwright versions in a pnpm-lock.yaml (v5, v6 and v9 key styles)."""
    return sorted(set(_PNPM_PW.findall(text or '')), key=_pw_tuple)


def playwright_in_npm(text):
    """The resolved versions in a package-lock.json (lockfile v1, v2 and v3)."""
    try:
        data = json.loads(text or 'null')
    except ValueError:
        return []
    found = set()
    if isinstance(data, dict):
        for key, entry in (data.get('packages') or {}).items():
            if key.endswith(('node_modules/@playwright/test', 'node_modules/playwright')) and isinstance(entry, dict):
                found.add(entry.get('version'))
        for name, entry in (data.get('dependencies') or {}).items():
            if name in ('@playwright/test', 'playwright') and isinstance(entry, dict):
                found.add(entry.get('version'))
    return sorted((v for v in found if valid_playwright_version(v)), key=_pw_tuple)


def playwright_in_yarn(text):
    """The resolved versions in a yarn.lock (classic and berry)."""
    found, in_block = set(), False
    for line in (text or '').splitlines():
        if line and not line[0].isspace() and not line.startswith('#'):
            in_block = bool(_YARN_HEAD.search(line))
        elif in_block:
            m = _YARN_VERSION.match(line)
            if m:
                found.add(m.group(1))
                in_block = False
    return sorted(found, key=_pw_tuple)


_PW_READERS = {'pnpm-lock.yaml': playwright_in_pnpm, 'package-lock.json': playwright_in_npm, 'yarn.lock': playwright_in_yarn}


def detect_playwright(probe, repo_paths):
    """The highest Playwright version found in the lockfiles of the local checkouts: (version, file) or (None, None)."""
    best, where = None, None
    for path in repo_paths or []:
        for name in LOCKFILES:
            file = os.path.join(path, name)
            versions = _PW_READERS[name](probe.read_text(file))
            if versions and (best is None or _pw_tuple(versions[-1]) > _pw_tuple(best)):
                best, where = versions[-1], file
    return best, where


def resolve_playwright(probe, browsers, flag=None, repo_paths=None):
    """(version, source text). Order: the flag, then the lockfiles, then the pin. None for browsers other than chromium."""
    if browsers != 'chromium':
        return None, None
    if flag:
        return flag, 'flag'
    version, file = detect_playwright(probe, repo_paths)
    if version:
        return version, 'detected from %s' % file
    return PLAYWRIGHT_VERSION, 'pinned'


PW_CONFIG = re.compile(r'^playwright\.config\.[A-Za-z]+$')
PW_PACKAGES = ('@playwright/test', 'playwright')
WORKSPACE_DIRS = ('packages', 'apps')


def _package_dirs(probe, path):
    """The repository root and its workspace packages (one level under packages/ and apps/)."""
    dirs = [path]
    for top in WORKSPACE_DIRS:
        for name in probe.listdir(os.path.join(path, top)) or []:
            dirs.append(os.path.join(path, top, name))
    return dirs


def playwright_use(probe, repo_path):
    """Why a local checkout counts as using Playwright (one short text), or None (DL101, D117)."""
    for d in _package_dirs(probe, repo_path):
        for name in probe.listdir(d) or []:
            if PW_CONFIG.match(name):
                return '%s found' % os.path.join(d, name).replace('\\', '/')
        try:
            pkg = json.loads(probe.read_text(os.path.join(d, 'package.json')) or '{}')
        except ValueError:
            pkg = {}
        deps = {}
        if isinstance(pkg, dict):
            for key in ('dependencies', 'devDependencies'):
                if isinstance(pkg.get(key), dict):
                    deps.update(pkg[key])
        for dep in PW_PACKAGES:
            if dep in deps:
                return '%s lists %s' % (os.path.join(d, 'package.json').replace('\\', '/'), dep)
    return None


def pick_browsers(probe, browsers, repo_paths, current=None):
    """(browsers, one line saying why). An explicit choice wins. Then the pool's current POOL_BROWSERS (`current`, from its
    .env): chromium stays chromium. Detection may raise none to chromium, never lower it (DL176)."""
    if browsers in BROWSERS:
        return browsers, None
    if current == 'chromium':
        return 'chromium', None
    for path in repo_paths or []:
        why = playwright_use(probe, path)
        if why:
            return 'chromium', 'POOL_BROWSERS set to chromium: %s (a repository served by this pool uses Playwright).' % why
    return 'none', None


def browsers_note(browsers):
    """One plain sentence for the plan: what the image holds for browsers."""
    if browsers == 'chromium':
        return ('The image includes the Chromium system libraries and is larger (about 300-400 MB). '
                'Jobs install the browser itself with `playwright install chromium`.')
    return 'The image has no Chromium libraries. Set browsers: chromium to add them (about 300-400 MB more).'


WIN_RUNNER_LABELS = ('self-hosted', 'windows')
WIN_RUNNERS_DIR = 'C:/actions-runners'


HOOK_FILES = ('runner_load_gate.py', 'runner_job_done.py', 'load.py', 'machine_slots.py')


HOOK_PYTHON_FIX = ('Install Python for all users (python.org installer, "Install for all users"), or pass the path of an all-users '
                   'python.exe as "python" in the machine config.')


def is_user_profile_path(path):
    """DL339: True when a Windows path is inside a user profile (C:\\Users\\..., %USERPROFILE% or the LOCALAPPDATA tree)."""
    p = str(path or '').replace('\\', '/').lower().rstrip('/')
    if not p:
        return False
    if re.match(r'^([a-z]:)?/users/', p) or '/appdata/local/' in p or '/appdata/roaming/' in p:
        return True
    for var in ('USERPROFILE', 'LOCALAPPDATA'):
        v = os.environ.get(var)
        if v and p.startswith(v.replace('\\', '/').lower().rstrip('/') + '/'):
            return True
    return False


def _py_version_key(path):
    m = re.search(r'python(\d+)', path.replace('\\', '/').lower())
    return int(m.group(1)) if m else 0


def _probe_python(probe):
    """The Python the probe reports (this process's on a real host), else sys.executable."""
    try:
        return (probe.python() if probe is not None and hasattr(probe, 'python') else None) or sys.executable
    except Exception:  # noqa: BLE001
        return sys.executable


def choose_hook_python(configured, exe, probe=None):
    """DL339 (R5.46): the Python a Windows hook wrapper or the host-load task runs. Returns (path, error); one is None.
    Order: the configured path; this process's Python when outside any user profile; the newest all-users install
    (Program Files, or `py -0p` output without profile paths). A per-user path is never returned, because the runner
    service account cannot read a user profile."""
    if configured:
        return _winpath(configured), None
    if exe and not is_user_profile_path(exe):
        return _winpath(exe), None
    found = []
    for pf in ('C:/Program Files', 'C:/Program Files (x86)'):
        found += glob.glob(pf + '/Python3*/python.exe')
    r = probe.sh(['py', '-0p']) if probe is not None and hasattr(probe, 'sh') else None
    if r and r[0] == 0:
        for line in (r[1] or '').splitlines():
            m = re.search(r'([A-Za-z]:[\\/].*?python[w]?\.exe)\s*$', line.strip(), re.I)
            if m:
                found.append(m.group(1))
    ok = [c for c in found if not is_user_profile_path(c) and (probe is None or not hasattr(probe, 'exists') or probe.exists(c))]
    if ok:
        return _winpath(sorted(set(ok), key=lambda c: (_py_version_key(c), c))[-1]), None
    return None, ('No Python outside a user profile was found (%s is per-user, and the runner service account cannot read it). %s'
                  % (exe or 'this Python', HOOK_PYTHON_FIX))


def hook_wrapper(python, script):
    """A PowerShell wrapper with the full path of the python, so the runner service account needs no PATH."""
    return ('# Runner hook for %s (written by the pool setup; a rerun refreshes it).\n'
            "& '%s' (Join-Path $PSScriptRoot '%s') @args\n"
            'exit $LASTEXITCODE\n' % (script, python.replace("'", "''"), script))


def windows_hooks_dir(machine_dir):
    return machine_dir.replace('\\', '/').rstrip('/') + '/runner-hooks'


def windows_runner_name(slug):
    return 'host1-%s' % slug


def windows_runner_folder(slug):
    return '%s/%s' % (WIN_RUNNERS_DIR, slug)


# --- DL316: a generic pool (D275, D278, D279) ------------------------------------------------------------------------
# A shared runner carries no project label. Windows workflows read the repository variable CI_RUNS_ON_WINDOWS, a JSON list.

GENERIC_BASE = ('self-hosted', 'windows', 'linux', 'macos', 'x64', 'x86', 'arm', 'arm64')
WIN_RUNS_ON = ('self-hosted', 'Windows', 'X64')


def configured_generic_labels():
    """The list `generic_labels` of machine.json (extra labels any project may name, such as a capability). [] when none."""
    try:
        raw = MS.read_config_file() if MS and hasattr(MS, 'read_config_file') else None
    except Exception:  # noqa: BLE001
        raw = None
    vals = (raw or {}).get('generic_labels')
    return [str(v) for v in vals if isinstance(v, str) and v.strip()] if isinstance(vals, list) else []


def generic_label_set(pool='main'):
    """Lower case names of the labels that are generic: self-hosted, OS names, architectures, the pool label, and machine.json
    `generic_labels`."""
    return {x.lower() for x in GENERIC_BASE} | {('pool-%s' % pool).lower()} | {x.lower() for x in configured_generic_labels()}


def windows_runs_on(labels, generic=None):
    """The JSON list for CI_RUNS_ON_WINDOWS: self-hosted, Windows, X64 and each generic capability label of the runner
    (a label named in machine.json `generic_labels`). Never a project name."""
    out = list(WIN_RUNS_ON)
    have = {x.lower() for x in out}
    extra = {x.lower() for x in configured_generic_labels()}
    for l in labels or []:
        if str(l).lower() in extra and str(l).lower() not in have:
            out.append(str(l))
            have.add(str(l).lower())
    return out


def workflows_naming(probe, repo, labels):
    """{label: [workflow files that name it]} read through gh. A label maps to None when the files cannot be read."""
    out = {l: [] for l in labels}
    listing, _why = probe.gh_json(['api', 'repos/%s/contents/.github/workflows' % repo])
    if not isinstance(listing, list):
        return {l: None for l in labels}
    for f in listing:
        name = f.get('name') if isinstance(f, dict) else None
        if not name or not name.endswith(('.yml', '.yaml')):
            continue
        r = probe.gh(['api', 'repos/%s/contents/.github/workflows/%s' % (repo, name), '-H', 'Accept: application/vnd.github.raw'])
        if not (r and r[0] == 0):
            return {l: None for l in labels}
        text = (r[1] or '').lower()
        for l in labels:
            if l.lower() in text:
                out[l].append(name)
    return out


def host_load_task_ps(python, loop):
    """DL320: the host-load task as PowerShell cmdlets. PowerShell 5.1 mangles the quotes of a cmd-style schtasks line."""
    return ["$a = New-ScheduledTaskAction -Execute %s -Argument %s" % (_psq(python), _psq('"%s"' % loop)),
            '$t = New-ScheduledTaskTrigger -AtStartup',
            'Register-ScheduledTask -TaskName luismc-host-load -Action $a -Trigger $t -User SYSTEM -RunLevel Highest -Force',
            'Start-ScheduledTask -TaskName luismc-host-load']


def _wanted_windows(found, repo, account=None):
    """The Windows runner already in the state this plan would create: same name, repository, folder and labels.
    Returns {'runner', 'folder', 'service'} or None. Such a runner is kept, not removed."""
    slug = slug_of(repo)
    name, folder = windows_runner_name(slug), windows_runner_folder(slug)
    gh = next((r for r in found['github']['repos'] if r['repo'] == repo), None)
    runner = next((x for x in (gh or {}).get('runners', []) if x.get('name') == name
                   and all(_has_label(x.get('labels'), l) for l in WIN_RUNNER_LABELS)), None)
    if not runner:
        return None
    fold = next((f for f in found['folders'] if _norm(f['path']).lower() == folder.lower() and f.get('repo') == repo
                 and f.get('name') == name), None)
    if not fold:
        return None
    svc = next((s for s in found['services'] if s.get('kind') == 'windows-service'
                and _norm(s.get('folder')).lower() == folder.lower()), None)
    if not svc:
        return None
    acct = account_name_of(svc.get('account'))
    # DL310: an account the setup could not read is not held against the runner; a known other account means re-register.
    return {'runner': name, 'folder': fold['path'], 'service': svc['name'], 'account': acct or None,
            'account_ok': not acct or acct == (account or windows_account(repo))}


# --- DL310: the shared Windows machine runner (D269 to D272) ----------------------------------------------------------
# One dedicated local account per runner service, one group, one machine.json and one slot queue for every runner on the
# machine. Every PowerShell part below is built from plain text; no password is ever written in it. The password is made
# inside the PowerShell process that registers the runner and goes only to config.cmd.

WIN_GROUP = 'luismc-ci-runners'
WIN_TOOLS_DIR = 'C:/ci-tools'
WIN_ACCOUNT_MAX = 20  # the longest local account name Windows takes
RUNNER_PIN = 'actions-runner'
RUNNER_PLATFORM = 'windows_x64'
CI_TOOL = os.path.join(os.path.dirname(HERE), 'templates', 'shared', 'scripts', 'delivery', 'ci_tool.py')
SID_ADMINS, SID_SYSTEM, SID_USERS = '*S-1-5-32-544', '*S-1-5-18', '*S-1-5-32-545'


def windows_account(repo, taken=()):
    """The local account of a runner service: `ci-<short slug>`, at most 20 characters, lower case letters, digits and
    hyphens. Deterministic. A slug that does not fit, or a name another repository already holds, gets a 4 character
    hash of the repository name so two repositories never share an account."""
    plain = slug_of(repo)
    name = 'ci-' + plain
    if len(name) <= WIN_ACCOUNT_MAX and name not in set(taken):
        return name
    tag = hashlib.sha1(repo.lower().encode('utf-8')).hexdigest()[:4]
    room = WIN_ACCOUNT_MAX - len('ci-') - 1 - len(tag)
    return 'ci-%s-%s' % (plain[:room].rstrip('-') or 'x', tag)


def account_name_of(text):
    """`.\\ci-app`, `HOST\\ci-app` and `ci-app` all give `ci-app` (lower case)."""
    return (text or '').replace('/', '\\').split('\\')[-1].strip().lower()


def _psq(text):
    """A PowerShell single quoted string."""
    return "'" + str(text).replace("'", "''") + "'"


RIGHTS_MARK = 'symlink-1'  # DL319: a runner whose .env lacks it is set up again, so its account gets the new right


def windows_env_text(folder, hooks_dir, tools_dir=WIN_TOOLS_DIR):
    """The runner's .env: both hooks (the runner rejects .cmd hooks), the shared tool cache, and a private Rust home."""
    return ('ACTIONS_RUNNER_HOOK_JOB_STARTED=%s/runner_load_gate.ps1\n'
            'ACTIONS_RUNNER_HOOK_JOB_COMPLETED=%s/runner_job_done.ps1\n'
            'CI_TOOLS_DIR=%s\n'
            'RUSTUP_HOME=%s/_tools/rustup\n'
            'CARGO_HOME=%s/_tools/cargo\n'
            'CI_RUNNER_RIGHTS=%s\n'
            # DL324: a ci-* account has no execution policy (Restricted), so the runner could not load the .ps1 hooks.
            # Process scope, this runner only: no machine-wide policy change.
            'PSExecutionPolicyPreference=RemoteSigned\n'
            % (hooks_dir, hooks_dir, tools_dir, folder, folder, RIGHTS_MARK))


def runner_pin_problem(pin_path=None):
    """A plain refusal text when tools.json has no real SHA-256 for the Windows runner download, else None (DL310)."""
    pin_path = pin_path or os.path.join(os.path.dirname(CI_TOOL), 'tools.json')
    try:
        with open(pin_path, encoding='utf-8') as f:
            entry = (((json.load(f).get(RUNNER_PIN) or {}).get('platforms') or {}).get(RUNNER_PLATFORM)) or {}
    except (OSError, ValueError, AttributeError):
        return 'refused: tools.json cannot be read, so the runner download cannot be checked.'
    if not entry.get('url') or sha_is_bad(entry.get('sha256')):
        return ('refused: the %s pin in tools.json has no real SHA-256 yet. The runner zip is never used unchecked. '
                'Put the SHA-256 published with the actions/runner release into the pin, then run the setup again.' % RUNNER_PIN)
    return None


def ps_header(label):
    return ['$ErrorActionPreference = %s' % _psq('Stop'), 'Write-Host %s' % _psq(label)]


def ps_machine(machine_dir, hooks_dir, tools_dir=WIN_TOOLS_DIR):
    """Group, and the rights on the shared folders. The queue and state folder: Modify. The hooks: read and execute (and the
    administrator or the person who runs the setup may rewrite them). The tool cache: Modify (ci_tool still checks SHA-256)."""
    grp, w = _psq(WIN_GROUP), lambda p: _psq(_winpath(p))  # noqa: E731
    return ps_header('Group and shared folder rights') + [
        'if (-not (Get-LocalGroup -Name %s -ErrorAction SilentlyContinue)) { New-LocalGroup -Name %s -Description %s | Out-Null }'
        % (grp, grp, _psq('Accounts of CI runner services (luismc-delivery)')),
        'New-Item -ItemType Directory -Force -Path %s, %s, %s | Out-Null' % (w(machine_dir), w(hooks_dir), w(tools_dir)),
        'icacls %s /grant "%s:(OI)(CI)M" | Out-Null' % (w(machine_dir), WIN_GROUP),
        'icacls %s /grant "%s:(OI)(CI)M" | Out-Null' % (w(tools_dir), WIN_GROUP),
        '$me = [Security.Principal.WindowsIdentity]::GetCurrent().Name',
        'icacls %s /inheritance:r /grant:r "%s:(OI)(CI)F" "%s:(OI)(CI)F" "$($me):(OI)(CI)M" "%s:(OI)(CI)RX" | Out-Null'
        % (w(hooks_dir), SID_ADMINS, SID_SYSTEM, WIN_GROUP),
    ]


# DL319, D281: the last right lets cargo-xwin make symbolic links. The loop adds the account when the line exists, so a rerun
# is idempotent.
RIGHTS_PS = [
    '$sid = (Get-LocalUser -Name $acct).SID.Value',
    "$cfg = Join-Path $env:TEMP ('luismc-rights-' + [guid]::NewGuid().ToString('N') + '.inf')",
    "$sdb = Join-Path $env:TEMP ('luismc-rights-' + [guid]::NewGuid().ToString('N') + '.sdb')",
    'secedit /export /cfg $cfg /areas USER_RIGHTS | Out-Null',
    '$text = Get-Content -Raw -Path $cfg',
    "foreach ($r in 'SeServiceLogonRight', 'SeDenyInteractiveLogonRight', 'SeDenyRemoteInteractiveLogonRight', 'SeCreateSymbolicLinkPrivilege') {",
    '  if ($text -match \"(?m)^$r\\s*=\") {',
    '    if ($text -notmatch \"(?m)^$r\\s*=.*$([regex]::Escape($sid))\") { $text = $text -replace \"(?m)^($r\\s*=.*)$\", (\'$1,*\' + $sid) }',
    '  } else {',
    '    $text = $text -replace \"(?m)^\\[Privilege Rights\\]\\s*$\", \"[Privilege Rights]`r`n$r = *$sid\"',
    '  }',
    '}',
    'Set-Content -Path $cfg -Value $text -Encoding Unicode',
    'secedit /configure /db $sdb /cfg $cfg /areas USER_RIGHTS | Out-Null',
    'Remove-Item -Force -ErrorAction SilentlyContinue $cfg, $sdb',
]


def ps_account(acct):
    """The runner's local account: not an administrator, in the group, allowed to log on as a service, denied interactive and
    remote logon. A new account gets a random password that nobody sees; the registration step sets the one it uses."""
    return ps_header('Local account %s' % acct) + [
        '$acct = %s' % _psq(acct),
        'if (-not (Get-LocalUser -Name $acct -ErrorAction SilentlyContinue)) {',
        '  $b = New-Object byte[] 24; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)',
        "  $p = ConvertTo-SecureString ('Aa1!' + [Convert]::ToBase64String($b)) -AsPlainText -Force",
        "  New-LocalUser -Name $acct -Password $p -PasswordNeverExpires -UserMayNotChangePassword -AccountNeverExpires "
        "-Description 'CI runner service (luismc-delivery)' | Out-Null",
        '}',
        'Add-LocalGroupMember -Group %s -Member $acct -ErrorAction SilentlyContinue' % _psq(WIN_GROUP),
        'Remove-LocalGroupMember -Group (Get-LocalGroup -SID %s) -Member $acct -ErrorAction SilentlyContinue'
        % _psq(SID_ADMINS.lstrip('*')),
    ] + RIGHTS_PS


def ps_unregister(repo):
    """DL315: a runner already configured in the folder is removed first, with a remove token (GitHub refuses a registration
    token here), before the folder is locked to the new account. A failure stops the script with the old runner untouched."""
    return [
        "if (Test-Path (Join-Path $folder '.runner')) {",
        '  $rt = (gh api -X POST %s --jq .token)' % _psq('repos/%s/actions/runners/remove-token' % repo),
        "  if ($LASTEXITCODE -ne 0 -or -not $rt) { throw 'gh could not make a remove token; the old runner and its folder are unchanged' }",
        '  Push-Location $folder',
        '  & .\\config.cmd remove --token $rt',
        '  $code = $LASTEXITCODE; Pop-Location; $rt = $null',
        "  if ($code -ne 0) { throw 'config.cmd remove failed; the old runner is still registered and its folder rights are unchanged' }",
        '}',
    ]


def ps_files(acct, folder, tools_dir, python, ci_tool=None, repo=None, unregister=False):
    """Download the runner through ci_tool (SHA-256 checked, cached in the tool folder), unpack it into the runner folder and
    lock the folder: Full for the account, Administrators and SYSTEM only. With `unregister`, a runner already configured
    in the folder is removed first (DL315)."""
    ci_tool = ci_tool or CI_TOOL
    f = _psq(_winpath(folder))
    return ps_header('Runner files in %s' % _winpath(folder)) + [
        '$folder = %s' % f,
    ] + (ps_unregister(repo) if unregister and repo else []) + [
        '$env:CI_TOOLS_DIR = %s' % _psq(_winpath(tools_dir)),
        'New-Item -ItemType Directory -Force -Path $folder | Out-Null',
        'if (-not (Test-Path (Join-Path $folder %s))) {' % _psq('config.cmd'),
        '  $src = & %s %s tool %s --platform %s --dir' % (_psq(_winpath(python)), _psq(_winpath(ci_tool)), RUNNER_PIN, RUNNER_PLATFORM),
        '  if ($LASTEXITCODE -ne 0 -or -not $src) { throw %s }' % _psq('the runner download failed its SHA-256 check or could not be fetched'),
        '  Copy-Item -Path (Join-Path $src %s) -Destination $folder -Recurse -Force' % _psq('*'),
        '}',
        'New-Item -ItemType Directory -Force -Path (Join-Path $folder %s), (Join-Path $folder %s) | Out-Null'
        % (_psq('_tools\\rustup'), _psq('_tools\\cargo')),
        'icacls $folder /inheritance:r /grant:r "%s:(OI)(CI)F" "%s:(OI)(CI)F" "%s:(OI)(CI)F" | Out-Null'
        % (SID_ADMINS, SID_SYSTEM, acct),
    ]


def ps_register(repo, name, acct, folder, env_text, register=True, labels=WIN_RUNNER_LABELS):
    """Write .env, then (when `register`) fetch a registration token now, make a random password, set it on the account and
    give it to config.cmd; start the service. The token and the password live in PowerShell variables only."""
    lines = ps_header('Runner service %s for %s' % (name, repo)) + [
        '$acct = %s' % _psq(acct), '$folder = %s' % _psq(_winpath(folder)),
        "Set-Content -Path (Join-Path $folder '.env') -Value @'\n%s'@ -Encoding Ascii -NoNewline" % env_text,
    ]
    if register:
        lines += [
            '$token = (gh api -X POST %s --jq .token)' % _psq('repos/%s/actions/runners/registration-token' % repo),
            "if ($LASTEXITCODE -ne 0 -or -not $token) { throw 'gh could not make a registration token (is gh signed in for this account?)' }",
            "Push-Location $folder",
            '$b = New-Object byte[] 24; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)',
            "$pw = 'Aa1!' + [Convert]::ToBase64String($b)",
            "Set-LocalUser -Name $acct -Password (ConvertTo-SecureString $pw -AsPlainText -Force)",
            '& .\\config.cmd --unattended --url %s --token $token --name %s --labels %s --runasservice '
            '--windowslogonaccount (".\\" + $acct) --windowslogonpassword $pw' % (
                _psq('https://github.com/' + repo), _psq(name), _psq(','.join(labels))),
            'if ($LASTEXITCODE -ne 0) { Pop-Location; throw %s }' % _psq('config.cmd failed'),
            'Pop-Location',
            '$token = $null; $pw = $null',
        ]
    lines += ["$svc = (Get-Content -Raw -Path (Join-Path $folder '.service')).Trim()",
              'Restart-Service -Name $svc',
              'Write-Host %s' % _psq('runner %s is set up' % name)]
    return lines


def windows_runner_script(step, setup_machine=True):
    """The whole setup of one runner as one PowerShell script text. It holds no secret: it fetches its own token and makes its
    own password at run time. The same parts run in the elevated setup."""
    lines = ['#Requires -RunAsAdministrator',
             '# DL310: shared machine runner for %s (written by the delivery setup; safe to run again).' % step['repo'],
             '# It holds no token and no password: both are made while it runs and are never written down.']
    if setup_machine:
        lines += ps_machine(step['machine_dir'], step['hooks_dir'], step['tools_dir'])
    lines += ps_account(step['account'])
    lines += ps_files(step['account'], step['folder'], step['tools_dir'], step['python'], step.get('ci_tool'),
                      step.get('repo'), step.get('register', True))
    lines += ps_register(step['repo'], step['runner'], step['account'], step['folder'], step['env_text'], step.get('register', True))
    return '\r\n'.join(lines) + '\r\n'


def runner_has_job(probe, repo, name):
    """True when GitHub lists the runner as busy. Unreadable counts as busy: a runner is touched only when it is seen idle."""
    data, _why = probe.gh_json(['api', 'repos/%s/actions/runners?per_page=100' % repo])
    if not isinstance(data, dict):
        return True
    return any(x.get('name') == name and x.get('busy') for x in data.get('runners', []))


def migration_guard(probe, step):
    """DL310: why an old-runner step must wait, else None. The new runner must be online, and the old one must have no job."""
    old = step.get('old_runner')
    if not old:
        return None
    data, _why = probe.gh_json(['api', 'repos/%s/actions/runners?per_page=100' % step['repo']])
    if not isinstance(data, dict):
        return 'the runner list of %s cannot be read, so %s is not touched' % (step['repo'], old)
    runners = {x.get('name'): x for x in data.get('runners', [])}
    new = runners.get(step.get('new_runner'))
    if not new or new.get('status') != 'online':
        return 'the new runner %s is not online yet, so %s stays' % (step.get('new_runner'), old)
    if old in runners and runners[old].get('busy'):
        return 'a job runs on %s: it is not touched. Run the setup again when the job ends.' % old
    return None


def plan(found, linux_repos=None, windows_repos=None, pool='main', cap=None, serial=None, limits=None, repo_path=None,
         browsers=None, playwright_version=None, repo_paths=None, probe=None, drop_layers=(), drop_apt=(), only=None):
    """The steps, in the order of contract 6.3. A public repository gets no step; it is listed in `refused`.

    With no repositories given, they come from detect (`derive_repos`). With none derived either, the plan has no step
    and says why: it never removes a runner it does not rebuild. Removals are limited to the planned repositories.
    A runner that already belongs to this pool is kept and its steps say `already` (safe to run again).

    `only` (DL316, D280) is 'windows' or 'linux': the plan holds only that OS's steps. The host-load steps stay in both modes
    (they are machine level)."""
    if only not in (None, 'windows', 'linux'):
        raise ValueError("only must be 'windows' or 'linux'")
    derived = not linux_repos and not windows_repos
    if derived:
        linux_repos, windows_repos = derive_repos(found)
    linux_repos, windows_repos = list(linux_repos or []), list(windows_repos or [])
    private = {r['repo']: r['private'] for r in found['github']['repos']}
    refused = []
    for repo in linux_repos + windows_repos:
        if private.get(repo) is not True:
            why = PRIVATE_REFUSAL % repo if repo in private else 'refused: %s is not a repository you administer' % repo
            refused.append({'repo': repo, 'reason': why})
    bad = {x['repo'] for x in refused}
    keep_l = [r for r in linux_repos if r not in bad]
    keep_w = [r for r in windows_repos if r not in bad]
    if only == 'windows':
        keep_l = []
    elif only == 'linux':
        keep_w = []
    base = {'pool': pool, 'refused': refused, 'cap': cap, 'derived': derived, 'blocked': None, 'only': only, 'notes': []}
    if not keep_l and not keep_w:
        base.update(steps=[], minutes=0, needs=[], blocked='No repository to plan for: none was named and detect found no '
                    'private repository with a runner or a self-hosted workflow. No runner is removed.')
        return base
    if cap is not None and cap.get('ok') is False:
        base.update(steps=[], minutes=0, needs=[], blocked='Sizing refused: %s' % cap.get('message'))
        return base
    planned = set(keep_l) | set(keep_w)
    host = found.get('host') or {}
    win = str(host.get('platform', '')).startswith('win')
    steps = [_step('idle', 'Wait until no existing runner has a job', 'wait-idle')]
    accts = {}
    for r in keep_w:
        accts[r] = windows_account(r, taken=set(accts.values()))
    wanted = {r: w for r, w in ((r, _wanted_windows(found, r, accts[r])) for r in keep_w) if w}
    # DL310: an old Windows runner of a planned repository with another name is replaced AFTER the new one is online.
    new_names = {r: windows_runner_name(slug_of(r)) for r in keep_w}
    old_win = {}  # (repo, runner name) -> the GitHub runner entry
    for r in found['github']['repos']:
        if r['repo'] in keep_w:
            for x in r['runners']:
                if str(x.get('os')).lower() == 'windows' and x['name'] != new_names[r['repo']] \
                        and not _has_label(x['labels'], 'pool-%s' % pool):
                    old_win[(r['repo'], x['name'])] = x
    old_folders = {_norm(f['path']).lower(): f for f in found['folders']
                   if (f.get('repo'), f.get('name')) in old_win
                   and _norm(f['path']).lower() != windows_runner_folder(slug_of(f['repo'])).lower()}
    old_services = {sv['name']: sv for sv in found['services'] if sv.get('kind') == 'windows-service'
                    and _norm(sv.get('folder')).lower() in old_folders}
    wanted_runners = {(r, w['runner']) for r, w in wanted.items()}
    wanted_services = {w['service'] for w in wanted.values() if w['service']}
    wanted_folders = {w['folder'].lower() for w in wanted.values()}
    for r in found['github']['repos']:
        if r['repo'] not in planned:
            continue
        for x in r['runners']:
            if _has_label(x['labels'], 'pool-%s' % pool):
                continue  # already part of this pool: kept
            if (r['repo'], x['name']) in wanted_runners:
                continue  # the Windows runner this plan would create: kept
            if (r['repo'], x['name']) in old_win:
                continue  # replaced after the new runner is online (below)
            steps.append(_step('remove:%s:%s' % (r['repo'], x['name']),
                               'Remove runner %s (%s) from %s' % (x['name'], x['os'], r['repo']), 'remove-runner',
                               delete=True, names=['runner %s (%s) in %s on GitHub' % (x['name'], x['os'], r['repo'])],
                               repo=r['repo'], runner_id=x['id'], runner=x['name']))
    repo_of = {f['path']: f.get('repo') for f in found['folders']}
    for svc in found['services']:
        if svc.get('kind') != 'windows-service' or only == 'linux':
            continue
        if repo_of.get(svc.get('folder')) not in planned | {None}:
            continue
        n = svc['name']
        if n in wanted_services or n in old_services:
            continue
        steps.append(_step('winsvc-remove:%s' % n, 'Stop and delete the Windows runner service %s' % n, 'windows-service-remove',
                           delete=True, names=['Windows service ' + n], elevated=True, service=n,
                           printed=['sc.exe stop "%s"' % n, 'sc.exe delete "%s"' % n]))
    for f in found['folders']:
        if f.get('repo') not in planned | {None}:
            continue
        if _norm(f['path']).lower() in wanted_folders or _norm(f['path']).lower() in old_folders:
            continue
        steps.append(_step('delete-folder:%s' % f['path'], 'Delete the old runner folder %s' % f['path'], 'delete-folder',
                           delete=True, names=[f['path']], path=f['path']))
    for c in found['containers']:
        if c.get('pool') or only == 'windows':
            continue  # the pool's own container is kept; a Windows-only plan leaves Linux containers alone
        steps.append(_step('delete-container:%s' % c['name'], 'Stop and delete the container %s' % c['name'],
                           'delete-container', delete=True, names=['container ' + c['name']], container=c['name'],
                           via=c.get('via', '')))
    steps.append(_step('machine-config', 'Write the machine config (limits, slots) through the machine layer', 'machine-config',
                       limits=limits or {}))
    if win:
        py, py_err = choose_hook_python(host.get('python'), host.get('python_exe') or _probe_python(probe), probe)
        dest = host.get('machine_dir', 'C:/ProgramData/luismc-delivery').rstrip('/\\') + '/host-load'
        loop = _winpath(dest + '/host-load-loop.py')
        py = py or 'python'
        steps.append(_step('host-load-files', 'Copy load.py and a 15-second loop script to %s' % dest, 'host-load-files', dest=dest))
        steps.append(_step('host-load-task', 'Register the scheduled task that writes the host load file every 15 seconds'
                           + ((' - CANNOT RUN: ' + py_err) if py_err else ''),
                           'host-load-task', elevated=True, printed=[] if py_err else host_load_task_ps(py, loop), problem=py_err))
    if keep_l:
        w, enough = _wsl_values(found, cap)
        if w and (win or (found.get('wsl') or {}).get('exists')):
            cur = found.get('wsl') or {}
            s1 = _step('wslconfig', 'Write %s with the pool ceiling (memory %s -> %sGB, processors %s -> %s; the old file is kept as .bak)' % (
                cur.get('file'), _gb(cur.get('memory')), w['memory'], cur.get('processors') or 'unset', w['processors']),
                'wslconfig', cap=dict(cap, wsl=w))
            if enough:
                s1['state'] = 'already'
            steps.append(s1)
            if not enough:
                steps.append(_step('wsl-restart', 'Restart WSL so the ceiling applies (only when no job runs; stops every container)',
                                   'wsl-restart'))
        old = found.get('pool_env') or {}
        probe = probe or Probe()
        paths = repo_paths or ([repo_path] if repo_path else [])
        browsers, why = pick_browsers(probe, browsers, paths, old.get('POOL_BROWSERS'))
        if why:
            print(why)
        # DL176: a plan keeps what the pool .env has (Playwright version, layers, apt names) unless a flag changes it.
        if browsers == 'chromium' and not playwright_version and old.get('POOL_BROWSERS') == 'chromium' \
                and valid_playwright_version(old.get('PLAYWRIGHT_VERSION')):
            pw, pw_source = old['PLAYWRIGHT_VERSION'], 'kept from the pool .env'
        else:
            pw, pw_source = resolve_playwright(probe, browsers, playwright_version, paths)
        layers, apt, lsources, lnotes = merge_pool_layers(old, [], [], None, drop_layers, drop_apt)
        env_extra = {}
        if old.get('POOL_LAYERS') is not None or old.get('POOL_APT') is not None or drop_layers or drop_apt:
            env_extra = {'POOL_LAYERS': ','.join(layers), 'POOL_APT': ' '.join(apt)}
            if old.get('POOL_LAYER_SOURCES') is not None or lsources:
                env_extra['POOL_LAYER_SOURCES'] = ','.join('%s:%s' % kv for kv in lsources.items())
        pw_text = ' Playwright %s (%s).' % (pw, pw_source) if pw else ''
        keep_text = (' Layers kept: %s.' % ', '.join(layers)) if layers else ''
        keep_text += (' Apt packages kept: %s.' % ' '.join(apt)) if apt else ''
        kept = ' (kept)' if (cap or {}).get('source') == 'kept' else ''
        steps.append(_step('pool-files', 'Write the pool files for "%s" (compose, agents.json, .env: POOL_MEM %s -> %sg%s, '
                           'POOL_CPUS %s -> %s%s, POOL_CPUSET, POOL_CPUS_INT, POOL_BROWSERS %s). %s%s%s%s' % (
                               pool, old.get('POOL_MEM') or 'unset', (cap or {}).get('mem_gib', 4), kept,
                               old.get('POOL_CPUS') or 'unset', (cap or {}).get('cpus', 1), kept, browsers,
                               browsers_note(browsers), pw_text, keep_text,
                               (' ' + cap['cpus_text'] + '.') if (cap or {}).get('cpus_text') else ''),
                           'pool-files', pool=pool, cap=cap, browsers=browsers, playwright_version=pw, env_extra=env_extra))
        steps.append(_step('pool-up', 'Build and start the pool container', 'pool-up', pool=pool))
        for repo in keep_l:
            s = _step('agent:%s' % repo, 'Add one pool agent for %s' % repo, 'add-agent', repo=repo, pool=pool, slug=slug_of(repo))
            if _pool_has(found, pool, repo):
                s['state'] = 'already'
            steps.append(s)
    machine_dir = host.get('machine_dir', 'C:/ProgramData/luismc-delivery')
    hooks_dir = windows_hooks_dir(machine_dir)
    admin = bool(win and keep_w and getattr(probe or Probe(), 'is_admin', lambda: False)())
    pin_problem = runner_pin_problem() if keep_w else None
    py, py_err = choose_hook_python(host.get('python'), host.get('python_exe') or _probe_python(probe), probe) if keep_w else (None, None)
    py = py or 'python'
    pin_problem = pin_problem or py_err  # DL339: no all-users Python: the files and service steps stop with the message
    base_w = dict(machine_dir=machine_dir, hooks_dir=hooks_dir, tools_dir=WIN_TOOLS_DIR, python=py, ci_tool=CI_TOOL)
    if keep_w:
        steps.append(_step('runner-hooks', 'Copy the runner hook scripts to the stable folder %s (rewritten on every run)' % hooks_dir,
                           'runner-hooks', dest=hooks_dir, python=py, problem=py_err))
    for repo in keep_w:  # DL310: is the .env of a kept runner what this plan would write? (unreadable counts as stale)
        w = wanted.get(repo)
        if w:
            want_env = windows_env_text(w['folder'].replace('\\', '/'), hooks_dir)
            w['env_ok'] = probe is None or probe.read_text(w['folder'] + '/.env') == want_env  # no probe: not judged
    todo_w = [r for r in keep_w if not (r in wanted and wanted[r]['account_ok'] and wanted[r]['env_ok'])]
    if admin and todo_w:
        steps.append(_step('win-machine', 'Make the group %s and set the rights: %s and the tool cache %s Modify, runner-hooks Read & Execute'
                           % (WIN_GROUP, machine_dir, WIN_TOOLS_DIR), 'windows-machine', **base_w))
    for repo in keep_w:
        slug = slug_of(repo)
        acct, folder, name = accts[repo], windows_runner_folder(slug), windows_runner_name(slug)
        w = wanted.get(repo)
        fresh = repo in todo_w
        register = not (w and w['account_ok'])  # the password changes only when the service is registered again
        data = dict(base_w, repo=repo, slug=slug, account=acct, runner=name, folder=folder, register=register,
                    env_text=windows_env_text(folder, hooks_dir), new_runner=name, pin_problem=pin_problem)
        manual = ['cd %s' % folder,
                  './config.cmd --url https://github.com/%s --token <TOKEN> --name %s --labels self-hosted,windows --runasservice '
                  '--windowslogonaccount .\\%s --windowslogonpassword <PASSWORD>' % (repo, name, acct),
                  'Set ACTIONS_RUNNER_HOOK_JOB_STARTED=%s/runner_load_gate.ps1 and ACTIONS_RUNNER_HOOK_JOB_COMPLETED=%s/runner_job_done.ps1 '
                  'in %s/.env (the runner rejects .cmd hooks), with CI_TOOLS_DIR, RUSTUP_HOME and CARGO_HOME'
                  % (hooks_dir, hooks_dir, folder)]
        if admin:
            if (register and not w) or (fresh and w and not register):  # DL319: a kept account gets the new right
                steps.append(_step('win-account:%s' % repo, 'Local account %s for the %s service (not an administrator, no interactive or '
                                   'remote logon, may log on as a service)' % (acct, name), 'windows-account', **data))
                steps.append(_step('win-files:%s' % repo, 'Download the runner (SHA-256 checked) to %s and lock the folder to %s'
                                   % (folder, acct), 'windows-files', **data))
            s = _step('winsvc:%s' % repo, 'Windows runner service for %s as %s with both hooks' % (repo, acct), 'windows-service',
                      elevated=False, printed=manual, **data)
        else:
            if fresh:
                steps.append(_step('win-script:%s' % repo, 'Write the PowerShell script that sets up everything for %s' % repo,
                                   'windows-runner-script', **dict(data, script=_winpath('%s/setup/windows-runner-%s.ps1' % (
                                       machine_dir.rstrip('/\\'), slug)))))
            run_line = 'powershell -NoProfile -ExecutionPolicy Bypass -File "%s"' % _winpath(
                '%s/setup/windows-runner-%s.ps1' % (machine_dir.rstrip('/\\'), slug))
            s = _step('winsvc:%s' % repo, 'Windows runner service for %s as %s with both hooks' % (repo, acct), 'windows-service',
                      elevated=True, printed=manual, say=['Open an administrator PowerShell and run: ' + run_line], **data)
        if not fresh:
            s['state'] = 'already'
            for x in steps:
                if x['id'] in ('win-account:%s' % repo, 'win-files:%s' % repo):
                    x['state'] = 'already'
        steps.append(s)
    # DL310: replace the old Windows runners (another name or account) once the new one is online. Each step names what goes.
    for (repo, oname), x in sorted(old_win.items()):
        common = dict(repo=repo, old_runner=oname, new_runner=new_names[repo])
        for n, sv in old_services.items():
            fold = old_folders[_norm(sv['folder']).lower()]
            if (fold.get('repo'), fold.get('name')) == (repo, oname):
                steps.append(_step('winsvc-remove:%s' % n, 'Stop and delete the old Windows runner service %s (replaced by %s)' % (n, new_names[repo]),
                                   'windows-service-remove', delete=True, names=['Windows service ' + n], elevated=not admin, service=n,
                                   printed=['sc.exe stop "%s"' % n, 'sc.exe delete "%s"' % n], **common))
        steps.append(_step('remove:%s:%s' % (repo, oname), 'Remove the old runner %s (%s) from %s' % (oname, x['os'], repo), 'remove-runner',
                           delete=True, names=['runner %s (%s) in %s on GitHub' % (oname, x['os'], repo)], runner_id=x['id'],
                           runner=oname, **common))
        for key, fold in old_folders.items():
            if (fold.get('repo'), fold.get('name')) == (repo, oname):
                steps.append(_step('delete-folder:%s' % fold['path'], 'Delete the old runner folder %s' % fold['path'], 'delete-folder',
                                   delete=True, names=[fold['path']], path=fold['path'], **common))
    generic = generic_label_set(pool)
    for repo in keep_w:  # DL316: Windows workflows read CI_RUNS_ON_WINDOWS (D278); a project label is removed only with a yes (D279)
        gh = next((r for r in found['github']['repos'] if r['repo'] == repo), None) or {}
        rn = next((x for x in gh.get('runners', []) if x.get('name') == new_names[repo]), None)
        labels = (rn or {}).get('labels') or []
        steps.append(_step('var:CI_RUNS_ON_WINDOWS:%s' % repo, 'Set CI_RUNS_ON_WINDOWS for %s' % repo, 'set-variable', repo=repo,
                           name='CI_RUNS_ON_WINDOWS', value=json.dumps(windows_runs_on(labels, generic))))
        custom = [l for l in labels if str(l).lower() not in generic]
        if rn and custom:
            named = workflows_naming(probe or Probe(), repo, custom)
            for label in custom:
                files = named.get(label)
                if files is None:
                    base['notes'].append('%s: the workflow files could not be read, so label %s on runner %s is left.'
                                         % (repo, label, rn['name']))
                elif files:
                    base['notes'].append('%s: label %s on runner %s stays; switch these workflow files to '
                                         'runs-on: ${{ fromJSON(vars.CI_RUNS_ON_WINDOWS) }}: %s.'
                                         % (repo, label, rn['name'], ', '.join(files)))
                else:
                    steps.append(_step('label-remove:%s:%s' % (repo, label), 'Remove label %s from runner %s' % (label, rn['name']),
                                       'remove-label', delete=True, names=['label %s on runner %s in %s' % (label, rn['name'], repo)],
                                       repo=repo, runner_id=rn['id'], runner=rn['name'], label=label))
    for repo in keep_l:
        value = json.dumps(expected_runs_on(['self-hosted', 'linux'], pool))  # DL184: the shared rule
        steps.append(_step('var:CI_RUNS_ON:%s' % repo, 'Set CI_RUNS_ON for %s' % repo, 'set-variable', repo=repo,
                           name='CI_RUNS_ON', value=value, repo_path=repo_path))
        if serial is not None:
            steps.append(_step('var:CI_SERIAL:%s' % repo, 'Set CI_SERIAL for %s' % repo, 'set-variable', repo=repo,
                               name='CI_SERIAL', value='true' if serial else 'false'))
    if only != 'windows':
        steps.append(_step('verify', 'Verify: each agent online with its labels, then one pool-check run per repository', 'verify',
                           repos=keep_l, pool=pool))
    n_run = sum(1 for s in steps if s['state'] == 'todo')
    base.update(steps=steps, minutes=5 + 3 * n_run, needs=['a yes for each step', 'a yes that names what is deleted']
                + (['an administrator shell for: ' + ', '.join(s['id'] for s in steps if s['elevated'])]
                   if any(s['elevated'] for s in steps) else []))
    return base


def set_wsl_values(text, memory_gib, processors):
    """`.wslconfig` text with memory= and processors= set inside [wsl2] (added when missing). Other lines stay."""
    want = {'memory': '%dGB' % memory_gib, 'processors': str(processors)}
    out, sect, done = [], None, set()

    def flush():
        if sect == 'wsl2':
            for k in want:
                if k not in done:
                    out.append('%s=%s' % (k, want[k]))
                    done.add(k)
    for line in text.splitlines():
        m = re.match(r'\s*\[(.+?)\]', line)
        if m:
            flush()
            sect = m.group(1).strip().lower()
            out.append(line)
            continue
        k = re.match(r'\s*(memory|processors)\s*=', line, re.I)
        if sect == 'wsl2' and k:
            key = k.group(1).lower()
            out.append('%s=%s' % (key, want[key]))
            done.add(key)
        else:
            out.append(line)
    flush()
    if 'memory' not in done:
        out += ['', '[wsl2]'] + ['%s=%s' % (k, v) for k, v in want.items()]
    return '\n'.join(out) + '\n'


def default_check(step, probe=None):
    """Did the owner's administrator step work? Read only. Steps it does not know are not done."""
    probe = probe or Probe()
    if step.get('action') == 'windows-service-remove':
        return step['service'] not in [x['name'] for x in detect_services(probe)]
    if step.get('action') == 'windows-service':
        return any(step.get('slug', '\0') in (x['name'] or '') for x in detect_services(probe))
    if step.get('action') == 'host-load-task':
        r = probe.sh(['schtasks', '/Query', '/TN', 'luismc-host-load'])
        if r and r[0] == 0:
            return True
        # An unelevated query of a SYSTEM task is "Access is denied": unknown, not failed. A fresh host-load file proves it runs.
        _figures, age = probe.host_load()
        return age is not None and age < HOST_LOAD_FRESH_S
    return False


# --- run (steps 6.3) --------------------------------------------------------------------------------------------------

def version_tuple(version):
    return tuple(int(x) for x in re.findall(r'\d+', version or '')[:3])


def resolve_runner(probe):
    """(version, sha256, source) of the runner to build: the latest actions/runner release, else the pinned fallback.
    A release below the floor is never used."""
    data, _why = probe.gh_json(['api', 'repos/actions/runner/releases/latest'])
    tag = data.get('tag_name') if isinstance(data, dict) else None
    version = tag[1:] if isinstance(tag, str) and tag.startswith('v') else None
    if version and re.fullmatch(r'\d+\.\d+\.\d+', version) and version_tuple(version) >= version_tuple(MIN_RUNNER_VERSION):
        name = 'actions-runner-linux-x64-%s.tar.gz' % version
        for a in data.get('assets', []):
            d = a.get('digest') or ''
            if a.get('name') == name and d.startswith('sha256:') and re.fullmatch(r'[0-9a-f]{64}', d[7:]):
                return version, d[7:], 'latest release'
    return RUNNER_VERSION, RUNNER_SHA256, 'pinned fallback (the release API could not be read)'


def below_floor(version):
    """A plain refusal text when `version` is below the floor, else None."""
    if version_tuple(version) < version_tuple(MIN_RUNNER_VERSION):
        return ('refused: runner %s is below %s, the oldest version GitHub still lets register. '
                'Run the setup again to pick a newer one.' % (version, MIN_RUNNER_VERSION))
    return None


def runner_sha(probe, version=RUNNER_VERSION):
    """SHA-256 of the Linux runner tarball from the release (asset digest, else the release notes)."""
    data, _why = probe.gh_json(['api', 'repos/actions/runner/releases/tags/v%s' % version])
    if not isinstance(data, dict):
        return RUNNER_SHA256 if version == RUNNER_VERSION else None
    name = 'actions-runner-linux-x64-%s.tar.gz' % version
    for a in data.get('assets', []):
        d = a.get('digest') or ''
        if a.get('name') == name and d.startswith('sha256:'):
            return d[7:]
    body = data.get('body') or ''
    m = re.search(r'<!-- BEGIN SHA linux-x64 -->([0-9a-f]{64})<!-- END SHA linux-x64 -->', body)
    if not m:
        m = re.search(r'%s.{0,80}?([0-9a-f]{64})' % re.escape(name), body)
    return m.group(1) if m else None


def sha_is_bad(value):
    """DL165: a runner hash that is not 64 hex characters, or is one repeated character, is never right."""
    v = (value or '').strip().lower()
    return not re.fullmatch(r'[0-9a-f]{64}', v) or len(set(v)) == 1


def short_sha(value):
    v = (value or '').strip()
    return v[:8] if len(v) > 8 else (v or 'unset')


def judge_sha(probe, version, current):
    """DL165: (hash to write or keep, reason text or '', note). The pinned hash rules for the pinned version; another
    version uses the released hash; when that cannot be read the value stays (unless it is malformed)."""
    cur = (current or '').strip()
    if not cur:
        return runner_sha(probe, version), '', ''
    bad = sha_is_bad(cur)
    want = RUNNER_SHA256 if version == RUNNER_VERSION else runner_sha(probe, version)
    if want and cur.lower() != want.lower():
        return want, 'did not match the pinned hash for %s' % version if version == RUNNER_VERSION else \
            'did not match the released hash for %s' % version, ''
    if want:
        return cur, '', ''
    if bad:
        return None, '', ''
    return cur, '', ('kept RUNNER_SHA256 %s: the release hash for runner %s could not be read, so it was not checked.'
                     % (short_sha(cur), version))


def pool_dir(pool):
    base = MS.machine_dir() if MS else os.environ.get('DELIVERY_MACHINE_DIR', '/etc/luismc-delivery')
    return os.path.join(str(base), 'pools', pool)


def copy_lf(src, dst):
    """Copy a text file with LF line endings, whatever the source has (the pool runs Linux). Keeps the file mode."""
    with open(src, 'rb') as f:
        data = f.read().replace(b'\r\n', b'\n')
    with open(dst, 'wb') as f:
        f.write(data)
    shutil.copymode(src, dst)


def template_sources(copy_from=None):
    """DL162: (relative path, source path) of every file the plugin ships into a pool folder: the templates, hooks/
    and the machine scripts under delivery/."""
    out = []
    for name in sorted(os.listdir(TEMPLATES)):
        if os.path.isfile(os.path.join(TEMPLATES, name)) and name != 'pool-check.yml':
            out.append((name, os.path.join(TEMPLATES, name)))
    hooks = os.path.join(TEMPLATES, 'hooks')
    if os.path.isdir(hooks):
        for name in sorted(os.listdir(hooks)):
            if os.path.isfile(os.path.join(hooks, name)):
                out.append(('hooks/' + name, os.path.join(hooks, name)))
    for name in ('runner_load_gate.py', 'runner_job_done.py', 'load.py', 'machine_slots.py'):
        src = os.path.join(copy_from or HERE, name)
        if os.path.isfile(src):
            out.append(('delivery/' + name, src))
    return out


def _lf_bytes(path):
    try:
        with open(path, 'rb') as f:
            return f.read().replace(b'\r\n', b'\n')
    except OSError:
        return None


def pool_template_diffs(dest, copy_from=None):
    """DL162: relative paths whose content in `dest` differs from the plugin's file (line endings ignored), or is missing."""
    return [rel for rel, src in template_sources(copy_from) if _lf_bytes(src) != _lf_bytes(os.path.join(dest, *rel.split('/')))]


def copy_pool_templates(dest, copy_from=None, only=None):
    """DL162: copy the plugin's pool files (templates, hooks/, delivery/ machine scripts) into `dest` with LF endings.
    `only` limits it to those relative paths. It never touches .env, agents.json or db-admin.pw. Returns the paths written."""
    os.makedirs(dest, exist_ok=True)
    done = []
    for rel, src in template_sources(copy_from):
        if only is not None and rel not in only:
            continue
        target = os.path.join(dest, *rel.split('/'))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        copy_lf(src, target)
        done.append(rel)
    write_pool_version(dest)
    return done


# --- shared rules (DL184): pool-run, apply and the doctor all read these ---------------------------------------------

POOL_VERSION_FILE = 'pool-version.json'


def plugin_version():
    """The version of the plugin this script belongs to, from its plugin.json ('' when unreadable)."""
    try:
        with open(os.path.join(os.path.dirname(HERE), '.claude-plugin', 'plugin.json'), encoding='utf-8') as f:
            return str(json.load(f).get('version') or '')
    except (OSError, ValueError, AttributeError):
        return ''


def version_tuple(text):
    """'1.24.0' -> (1, 24, 0); () when it is not a dotted number."""
    try:
        return tuple(int(x) for x in str(text).strip().split('.'))
    except ValueError:
        return ()


def read_pool_version(dest):
    """The plugin version recorded in the pool folder by the last write of the files ('' when none)."""
    try:
        with open(os.path.join(dest, POOL_VERSION_FILE), encoding='utf-8') as f:
            return str(json.load(f).get('version') or '')
    except (OSError, ValueError, AttributeError):
        return ''


def write_pool_version(dest):
    """Record which plugin version wrote the pool files (LF endings)."""
    ver = plugin_version()
    if ver:
        with open(os.path.join(dest, POOL_VERSION_FILE), 'w', encoding='utf-8', newline='\n') as f:
            json.dump({'version': ver}, f)
            f.write('\n')


def pool_files_state(dest):
    """(kind, detail) for the pool files against this plugin's templates. kind: ok, newer (the pool was written by a newer
    plugin than this one: never a reason to refresh), drift (files differ: refresh)."""
    diff = pool_template_diffs(dest)
    mine, theirs = plugin_version(), read_pool_version(dest)
    if not diff:
        return 'ok', 'pool files match the installed plugin'
    if mine and theirs and version_tuple(theirs) > version_tuple(mine) > ():
        return 'newer', ('pool files were written by plugin %s, newer than this project\'s %s: update the plugin here '
                         '(do not refresh the pool from the older one). Differing: %s' % (theirs, mine, ', '.join(diff)))
    return 'drift', ('pool file(s) differ from the installed plugin\'s template: %s. Run `delivery_ci_setup.py pool-refresh --yes` '
                     '(old copies go to bak-<time>/).' % ', '.join(diff))


def pool_agent_name(pool, repo):
    """The name a pool agent registers under for a repository (OWNER/NAME): `<pool>-<slug>`."""
    return '%s-%s' % (pool, slug_of(repo))


def pool_exists(name, root=None):
    """True when `name` is a pool folder on this machine (it has a compose.yaml)."""
    try:
        return os.path.isfile(os.path.join(_pools_dir(root), str(name), 'compose.yaml'))
    except (OSError, TypeError, ValueError):
        return False


def expected_runs_on(base_labels, pool=None):
    """The expected CI_RUNS_ON labels: the runner's own labels, plus the pool's label when the machine is a pool."""
    labels = [x for x in base_labels if isinstance(x, str)]
    if pool and 'pool-%s' % pool not in labels:
        labels.append('pool-%s' % pool)
    return labels


def runs_on_satisfied(actual, expected, pool=None):
    """True when the CI_RUNS_ON text `actual` is right. A pool machine accepts a superset of the expected labels."""
    try:
        got = json.loads(actual) if isinstance(actual, str) else actual
    except ValueError:
        return False
    if isinstance(got, str):
        got = [got]
    if not isinstance(got, list) or not isinstance(expected, list):
        return False
    have, want = {str(x).lower() for x in got}, {str(x).lower() for x in expected}
    return have >= want if pool else have == want


def container_image(probe, pool):
    """The image the running pool container uses (`docker inspect -f '{{.Image}}'`), else the pool's tag, else None.
    The label-filtered `docker ps` shows an old image id after a rebuild, so it is not used for this."""
    r = probe.sh(['docker', 'inspect', '-f', '{{.Image}}', 'pool-%s-pool-1' % pool])
    if r is not None and r[0] == 0 and (r[1] or '').strip():
        return r[1].strip()
    r = probe.sh(['docker', 'image', 'inspect', '-f', '{{.Id}}', 'luismc-runner-pool:%s' % pool])
    if r is not None and r[0] == 0 and (r[1] or '').strip():
        return r[1].strip()
    return None


def write_pool_files(pool, cap, dest=None, copy_from=None, runner_version=None, browsers='none',
                     playwright_version=None, runner_sha256=None, keep_env=None):
    """Write the pool folder. `.env` holds the cap and the machine dir only (D42); the database password is a 0600 file."""
    dest = dest or pool_dir(pool)
    os.makedirs(dest, exist_ok=True)
    copy_pool_templates(dest, copy_from)
    n_cpus = max(1, int(math.floor((cap or {}).get('cpus', 1))))
    with open(os.path.join(dest, '.env'), 'w', encoding='utf-8') as f:
        f.write('POOL_CPUSET=0-%d\nPOOL_CPUS_INT=%d\n' % (n_cpus - 1, n_cpus))
        f.write('POOL_NAME=%s\nPOOL_CPUS=%s\nPOOL_MEM=%sg\nMACHINE_DIR=%s\nRUNNER_VERSION=%s\nPOOL_BROWSERS=%s\nPLAYWRIGHT_VERSION=%s\n' % (
            pool, (cap or {}).get('cpus', 1), (cap or {}).get('mem_gib', 4), os.path.dirname(os.path.dirname(dest)),
            runner_version or RUNNER_VERSION, browsers if browsers in BROWSERS else 'none',
            playwright_version if valid_playwright_version(playwright_version) else PLAYWRIGHT_VERSION))
        # DL92: compose.yaml requires RUNNER_SHA256, so `docker compose up --no-build` needs it in .env too.
        sha = runner_sha256 or (RUNNER_SHA256 if (runner_version or RUNNER_VERSION) == RUNNER_VERSION else None)
        if sha:
            f.write('RUNNER_SHA256=%s\n' % sha)
        # DL176: every other line of the old .env stays (POOL_LAYERS, POOL_APT, POOL_LAYER_SOURCES, ...).
        written = {'POOL_CPUSET', 'POOL_CPUS_INT', 'POOL_NAME', 'POOL_CPUS', 'POOL_MEM', 'MACHINE_DIR', 'RUNNER_VERSION',
                   'POOL_BROWSERS', 'PLAYWRIGHT_VERSION', 'RUNNER_SHA256'}
        for k, v in (keep_env or {}).items():
            if k not in written:
                f.write('%s=%s\n' % (k, v))
    agents = os.path.join(dest, 'agents.json')
    if not os.path.exists(agents):
        with open(agents, 'w', encoding='utf-8') as f:
            json.dump({'agents': []}, f)
    pw = os.path.join(dest, 'db-admin.pw')
    if not os.path.exists(pw):
        fd = os.open(pw, os.O_WRONLY | os.O_CREAT, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(secrets.token_urlsafe(24))
    return dest


def set_env_values(path, values):
    """Set KEY=value lines in a .env file (LF endings): a key already there is replaced in place, a new one is added at
    the end. Every other line stays."""
    try:
        with open(path, encoding='utf-8') as f:
            lines = f.read().splitlines()
    except OSError:
        lines = []
    left = {k: v for k, v in values.items() if v is not None}
    gone = {k for k, v in values.items() if v is None}  # DL274: None removes the key
    lines = [l for l in lines if l.partition('=')[0].strip() not in gone]
    for i, line in enumerate(lines):
        k = line.partition('=')[0].strip()
        if k in left:
            lines[i] = '%s=%s' % (k, left.pop(k))
    lines += ['%s=%s' % kv for kv in left.items()]
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(lines) + '\n')


def merge_pool_layers(env, layers, apt, source, drop_layers=(), drop_apt=()):
    """DL155: (layers, apt names, sources dict, notes). The pool .env lists stay; the caller's are added; drops remove."""
    cur = [x for x in (env.get('POOL_LAYERS') or '').split(',') if x]
    cur_apt = [x for x in (env.get('POOL_APT') or '').split() if x]
    sources = {}
    for item in (env.get('POOL_LAYER_SOURCES') or '').split(','):
        name, sep, who = item.partition(':')
        if sep and name:
            sources[name] = who
    notes = []
    for x in layers:
        if x not in cur:
            cur.append(x)
        if source and x not in sources:
            sources[x] = source
    for x in apt:
        if x not in cur_apt:
            cur_apt.append(x)
    for x in drop_layers or ():
        if x in cur:
            cur.remove(x)
        sources.pop(x, None)
    for x in drop_apt or ():
        if x in cur_apt:
            cur_apt.remove(x)
    for x in cur:
        if x not in layers and x not in (drop_layers or ()):
            notes.append('kept layer %s%s: the repo config does not ask for it; turning it off there does not remove it. '
                         'Pass --drop-layer %s to remove it.' % (x, ' (asked by %s)' % sources[x] if x in sources else '', x))
    sources = {k: v for k, v in sources.items() if k in cur}
    return cur, cur_apt, sources, notes


def refresh_plan(probe, pool, repo_paths=None, browsers=None, playwright_version=None, source=None, drop_layers=(), drop_apt=(), kvm=None):
    """B14: the narrow pool step. It (re)writes RUNNER_SHA256, POOL_BROWSERS and PLAYWRIGHT_VERSION in the pool's .env
    and rebuilds; the cap and every other line stay. DL155: layers and apt names already in the .env stay, the caller's
    are added (`source` is the asking repo), --drop-* removes one; PLAYWRIGHT_VERSION is never lowered unless the flag
    sets it. Returns a dict with `changes` (key -> (old, new)), or `error`."""
    env = read_pool_env(probe, pool)
    path = os.path.join(pool_dir(pool), '.env')
    if not env:
        return {'pool': pool, 'path': path, 'error': 'no pool .env at %s; run pool-run first' % path, 'changes': {}}
    version = env.get('RUNNER_VERSION') or RUNNER_VERSION
    sha, sha_reason, sha_note = judge_sha(probe, version, env.get('RUNNER_SHA256'))
    picked, why = pick_browsers(probe, browsers, repo_paths)
    if browsers not in BROWSERS and env.get('POOL_BROWSERS') == 'chromium':
        picked, why = 'chromium', None  # kept: only an explicit --browsers none removes it
    pw, pw_source = resolve_playwright(probe, picked, playwright_version, repo_paths)
    notes = [sha_note] if sha_note else []
    cur_pw = env.get('PLAYWRIGHT_VERSION')
    if pw and not playwright_version and valid_playwright_version(cur_pw) and _pw_tuple(cur_pw) > _pw_tuple(pw):
        notes.append('kept Playwright %s: it is higher than %s (%s). Pass --playwright %s to lower it.' % (cur_pw, pw, pw_source, pw))
        pw, pw_source = cur_pw, 'kept from the pool .env'
    want = {'POOL_BROWSERS': picked}
    layers, apt, lerrs = read_pool_layers(repo_paths)
    layers, apt, sources, lnotes = merge_pool_layers(env, layers, apt, source, drop_layers, drop_apt)
    notes += lnotes
    want['POOL_LAYERS'] = ','.join(layers)
    want['POOL_APT'] = ' '.join(apt)
    want['POOL_LAYER_SOURCES'] = ','.join('%s:%s' % kv for kv in sources.items())
    if sha:
        want['RUNNER_SHA256'] = sha
    if pw:
        want['PLAYWRIGHT_VERSION'] = pw
    # DL274: KVM is off unless POOL_KVM=1. --kvm on/off sets it; no flag keeps the .env value. Compose files follow the setting.
    kvm_on = (env.get('POOL_KVM') == '1') if kvm not in ('on', 'off') else kvm == 'on'
    kvm_error = None
    if kvm_on:
        host, khy = host_kvm(probe, pool)
        if host is not True:
            kvm_error = 'refused: POOL_KVM=1 but this host has no usable KVM (%s). Nothing was changed.' % khy
    if kvm_on:
        want.update({'POOL_KVM': '1', 'COMPOSE_FILE': KVM_COMPOSE, 'COMPOSE_PATH_SEPARATOR': ':'})
    else:
        want.update({'POOL_KVM': None, 'COMPOSE_FILE': None, 'COMPOSE_PATH_SEPARATOR': None})
    changes = {k: (env.get(k), v) for k, v in want.items() if (env.get(k) or ('' if k in ('POOL_LAYERS', 'POOL_APT', 'POOL_LAYER_SOURCES') else None)) != v}
    files = pool_template_diffs(pool_dir(pool))
    if files and pool_files_state(pool_dir(pool))[0] == 'newer':  # DL184: never write an older template over a newer pool
        notes.append(pool_files_state(pool_dir(pool))[1])
        files = []
    out = {'pool': pool, 'path': path, 'changes': changes, 'files': files, 'sha_reason': sha_reason if 'RUNNER_SHA256' in changes else '', 'why': why, 'playwright_source': pw_source if pw else None,
           'layers': [(x, sources.get(x)) for x in layers], 'notes': notes}
    if not sha:
        out['error'] = 'could not read the SHA-256 of runner %s; nothing was changed' % version
    if lerrs:
        out['error'] = ' '.join(lerrs) + ' Nothing was changed.'
    if kvm_error:
        out['error'] = kvm_error
    try:
        out['repos'] = [a['repo'] for a in json.loads(probe.read_text(os.path.join(pool_dir(pool), 'agents.json')) or '{}').get('agents', []) if a.get('repo')]
    except (ValueError, AttributeError, TypeError, KeyError):
        out['repos'] = []
    return out


def recreate_command(pool):
    return 'docker compose up -d --no-build --force-recreate pool'


def live_cap(probe, pool):
    """DL93: (memory bytes, nano CPUs) of the running pool container from `docker inspect`, or None when it cannot be read."""
    r = probe.sh(['docker', 'inspect', '--format', '{{.HostConfig.Memory}} {{.HostConfig.NanoCpus}}', 'pool-%s-pool-1' % pool])
    parts = r[1].split() if r and r[0] == 0 else []
    if len(parts) == 2 and all(x.isdigit() for x in parts):
        return int(parts[0]), int(parts[1])
    return None


def compose_required_vars(compose):
    """DL92: the names in every ${VAR:?message} of a compose file."""
    return sorted(set(re.findall(r'\$\{([A-Za-z_][A-Za-z0-9_]*):\?', compose or '')))


DRAIN_FILE, DRAINED_FILE, DRAIN_BUSY_FILE = 'drain', 'drained', 'drain-busy'
DRAIN_TIMEOUT_SEC = 45 * 60
DRAIN_POLL_SEC = 5


def clear_drain(pool):
    """DL289: remove the drain, drained and busy-list files of a pool (the supervisor then runs its listeners again)."""
    for name in (DRAIN_FILE, DRAINED_FILE, DRAIN_BUSY_FILE):
        try:
            os.remove(os.path.join(pool_dir(pool), name))
        except OSError:
            pass


class Executor:
    """Real step handlers. Each returns (ok, detail). Tokens go through a pipe and are never printed."""

    def __init__(self, probe=None):
        self.probe = probe or Probe()

    def run(self, step):
        h = getattr(self, 'do_' + step['action'].replace('-', '_'), None)
        if h is None:
            return False, 'no handler for %s' % step['action']
        why = migration_guard(self.probe, step) if step.get('old_runner') else None
        if why:  # DL310: never touch an old runner with a job, nor before the new one is online
            return False, why
        try:
            return h(step)
        except Exception as exc:  # noqa: BLE001  a step must fail with a reason, never crash the run
            return False, '%s: %s' % (type(exc).__name__, exc)

    def do_wait_idle(self, step):
        found = detect_github(self.probe)
        busy = [x['name'] for r in found['repos'] for x in r['runners'] if x['busy']]
        return (not busy, 'busy: %s. Try again when they finish.' % ', '.join(busy) if busy else 'no runner is busy')

    def do_remove_runner(self, step):
        r = self.probe.gh(['api', '-X', 'DELETE', 'repos/%s/actions/runners/%s' % (step['repo'], step['runner_id'])])
        return (bool(r and r[0] == 0), 'removed from GitHub' if r and r[0] == 0 else 'gh refused the removal')

    def do_remove_label(self, step):
        """DL316: remove one custom label from one runner. Runs only after a yes that names the label (D279)."""
        r = self.probe.gh(['api', '-X', 'DELETE', 'repos/%s/actions/runners/%s/labels/%s' % (
            step['repo'], step['runner_id'], urllib.parse.quote(step['label'], safe=''))])
        return (bool(r and r[0] == 0), 'label removed' if r and r[0] == 0 else 'gh refused the label removal')

    def do_delete_folder(self, step):
        shutil.rmtree(step['path'], ignore_errors=False)
        return True, 'deleted %s' % step['path']

    def do_delete_container(self, step):
        r = self.probe.sh((['wsl'] if step.get('via') == 'wsl' else []) + ['docker', 'rm', '-f', step['container']])
        return (bool(r and r[0] == 0), 'container deleted' if r and r[0] == 0 else 'docker refused')

    def do_machine_config(self, step):
        if MS is None or not hasattr(MS, 'write_machine_config'):
            return False, 'the machine layer (machine_slots.write_machine_config) is not in this plugin yet'
        cfg = dict(MS.machine_config())
        cfg.update(step.get('limits') or {})
        MS.write_machine_config(cfg)
        return True, 'machine config written through machine_slots'

    def do_wslconfig(self, step):
        w = (step.get('cap') or {}).get('wsl')
        if not w:
            return False, 'no pool ceiling to write (sizing is missing)'
        text = self.probe.read_text(self.probe.wslconfig)
        old = detect_wsl(self.probe)
        if text is not None:
            with open(self.probe.wslconfig + '.bak', 'w', encoding='utf-8') as f:
                f.write(text)
        with open(self.probe.wslconfig, 'w', encoding='utf-8') as f:
            f.write(set_wsl_values(text or '', w['memory'], w['processors']))
        return True, ('written: memory %s -> %sGB, processors %s -> %s (the old file is kept as .wslconfig.bak). '
                      'It applies after WSL restarts.' % (_gb(old['memory']), w['memory'], old['processors'] or 'unset', w['processors']))

    def do_wsl_restart(self, step):
        found = detect_github(self.probe)
        busy = [x['name'] for r in found['repos'] for x in r['runners'] if x['busy']]
        if busy:
            return False, 'a job runs on %s. WSL was not restarted; run the setup again when it ends.' % ', '.join(busy)
        r = self.probe.sh(['wsl', '--shutdown'])
        return (bool(r and r[0] == 0), 'WSL restarted' if r and r[0] == 0 else 'wsl --shutdown failed')

    def do_host_load_files(self, step):
        dest = step['dest']
        os.makedirs(dest, exist_ok=True)
        for name in ('load.py', 'machine_slots.py'):
            shutil.copy2(os.path.join(HERE, name), dest)
        with open(os.path.join(dest, 'host-load-loop.py'), 'w', encoding='utf-8') as f:
            f.write(LOOP_SCRIPT)
        return True, 'wrote ' + dest

    def do_runner_hooks(self, step):
        """D99: copy the hook scripts to a stable folder; the wrappers call the python that runs this setup."""
        if step.get('problem'):
            return False, step['problem']
        dest = step['dest']
        os.makedirs(dest, exist_ok=True)
        for name in HOOK_FILES:
            shutil.copy2(os.path.join(HERE, name), dest)
        py = _winpath(step['python'])
        for wrapper, script in (('runner_load_gate.ps1', 'runner_load_gate.py'), ('runner_job_done.ps1', 'runner_job_done.py')):
            with open(os.path.join(dest, wrapper), 'w', encoding='utf-8', newline='\r\n') as f:
                f.write(hook_wrapper(py, script))
        return True, 'wrote the hook scripts to %s (python %s)' % (dest, py)

    def _ps(self, lines, timeout=900):
        """Run PowerShell text through stdin (never a file, never an argument). Its output is trimmed to the last lines."""
        r = self.probe.sh(['powershell', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', '-'],
                          input='\r\n'.join(lines) + '\r\n', timeout=timeout)
        if r is None:
            return False, 'PowerShell cannot run'
        tail = ' / '.join(l.strip() for l in (r[1] or '').splitlines() if l.strip())[-300:]
        return r[0] == 0, tail or ('done' if r[0] == 0 else 'PowerShell failed (exit %s)' % r[0])

    def do_windows_machine(self, step):
        return self._ps(ps_machine(step['machine_dir'], step['hooks_dir'], step['tools_dir']))

    def do_windows_account(self, step):
        return self._ps(ps_account(step['account']))

    def do_windows_files(self, step):
        if step.get('pin_problem'):
            return False, step['pin_problem']
        return self._ps(ps_files(step['account'], step['folder'], step['tools_dir'], step['python'], step.get('ci_tool'),
                      step.get('repo'), step.get('register', True)))

    def do_windows_service(self, step):
        """Write .env, then register: the token and the password are made inside PowerShell and never come back here."""
        return self._ps(ps_register(step['repo'], step['runner'], step['account'], step['folder'], step['env_text'],
                                    step.get('register', True)))

    def do_windows_runner_script(self, step):
        """Not elevated: write the script the owner runs in an administrator PowerShell. It holds no secret."""
        if step.get('pin_problem'):
            return False, step['pin_problem']
        path = step['script']
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8-sig', newline='') as f:
            f.write(windows_runner_script(step))
        return True, 'wrote %s (no token and no password in it)' % path

    def do_windows_service_remove(self, step):
        n = step['service']
        self.probe.sh(['sc.exe', 'stop', n])
        r = self.probe.sh(['sc.exe', 'delete', n])
        return (bool(r and r[0] == 0), 'service deleted' if r and r[0] == 0 else 'sc.exe delete refused')

    def do_pool_files(self, step):
        version, sha, source = resolve_runner(self.probe)
        cap = dict(step.get('cap') or {})
        if cap.get('cpus') is not None:
            cap['cpus'] = cap_cpus(cap['cpus'], docker_ncpu(self.probe))
            cap['cpus'] = cap_mem_cpus(cap['cpus'], cap.get('mem_gib'))
        old = read_pool_env(self.probe, step['pool'])
        keep = dict(old, **(step.get('env_extra') or {}))
        pw = step.get('playwright_version') or (old.get('PLAYWRIGHT_VERSION') if valid_playwright_version(old.get('PLAYWRIGHT_VERSION')) else None)
        dest = write_pool_files(step['pool'], cap, runner_version=version, browsers=step.get('browsers') or 'none',
                                playwright_version=pw, runner_sha256=sha, keep_env=keep)
        text = 'wrote %s (runner %s, %s)' % (dest, version, source)
        text += self.apply_cap(step['pool'], old, read_pool_env(self.probe, step['pool']))
        if step.get('browsers') == 'chromium':
            text += '; Playwright %s' % (step.get('playwright_version') or PLAYWRIGHT_VERSION)
        return True, text

    def runners_busy(self):
        """DL93: True when a runner has a job, or when that cannot be told (treated as busy)."""
        found = detect_github(self.probe)
        if found.get('error') or not found.get('repos'):
            return True
        return any(x['busy'] for r in found['repos'] for x in r['runners']) or any(r.get('error') for r in found['repos'])

    def apply_cap(self, pool, old, new):
        """DL93: a changed cap in .env reaches the container only when it is recreated. Do it when no job runs; else say how."""
        if not old.get('POOL_MEM') or all(env_number(old.get(k)) == env_number(new.get(k)) for k in ('POOL_MEM', 'POOL_CPUS')):
            return ''
        cmd = recreate_command(pool)
        if self.runners_busy():
            return ('. The cap changed but a job may run (or the runners cannot be read), so the pool was not recreated. '
                    'By hand: cd %s && %s' % (pool_dir(pool), cmd))
        p = subprocess.run(cmd.split(), cwd=pool_dir(pool), capture_output=True, text=True)
        if p.returncode == 0:
            return '. The cap changed (%s/%s -> %s/%s); the pool was recreated' % (
                old.get('POOL_MEM'), old.get('POOL_CPUS'), new.get('POOL_MEM'), new.get('POOL_CPUS'))
        return '. The cap changed but the recreate failed (%s). By hand: cd %s && %s' % (
            p.stderr.strip()[-200:] or 'docker compose failed', pool_dir(pool), cmd)

    def do_pool_up(self, step):
        version = read_pool_env(self.probe, step['pool']).get('RUNNER_VERSION') or RUNNER_VERSION
        if below_floor(version):
            return False, below_floor(version)
        sha = judge_sha(self.probe, version, read_pool_env(self.probe, step['pool']).get('RUNNER_SHA256'))[0]
        if not sha:
            return False, 'could not read the SHA-256 of the runner release; the image is not built without it'
        env_path = os.path.join(pool_dir(step['pool']), '.env')
        if os.path.isfile(env_path) and read_pool_env(self.probe, step['pool']).get('RUNNER_SHA256') != sha:
            # B14: a later `docker compose up --no-build` needs it in .env (compose.yaml requires it).
            set_env_values(env_path, {'RUNNER_SHA256': sha})
        env = self.pool_build_env(step['pool'], version, sha)
        p = subprocess.run(['docker', 'compose', 'up', '-d', '--build'], cwd=pool_dir(step['pool']), env=env,
                           capture_output=True, text=True)
        return p.returncode == 0, 'pool is up' if p.returncode == 0 else (p.stderr.strip()[-300:] or 'docker compose failed')

    def pool_build_env(self, pool, version, sha):
        """The environment `docker compose` needs to build the pool image."""
        pe = read_pool_env(self.probe, pool)
        pw = pe.get('PLAYWRIGHT_VERSION')
        pw = pw if valid_playwright_version(pw) else PLAYWRIGHT_VERSION
        return dict(os.environ, RUNNER_SHA256=sha, RUNNER_VERSION=version, POOL_BROWSERS=pe.get('POOL_BROWSERS') or 'none',
                    PLAYWRIGHT_VERSION=pw, POOL_LAYERS=pe.get('POOL_LAYERS') or '', POOL_APT=pe.get('POOL_APT') or '')

    def build_image(self, pool):
        """DL289: build the image only (`docker compose build`). The old container keeps serving jobs meanwhile."""
        pe = read_pool_env(self.probe, pool)
        version = pe.get('RUNNER_VERSION') or RUNNER_VERSION
        if below_floor(version):
            return False, below_floor(version)
        sha = judge_sha(self.probe, version, pe.get('RUNNER_SHA256'))[0]
        if not sha:
            return False, 'could not read the SHA-256 of the runner release; the image is not built without it'
        env_path = os.path.join(pool_dir(pool), '.env')
        if os.path.isfile(env_path) and pe.get('RUNNER_SHA256') != sha:
            set_env_values(env_path, {'RUNNER_SHA256': sha})
        p = subprocess.run(['docker', 'compose', 'build'], cwd=pool_dir(pool), env=self.pool_build_env(pool, version, sha),
                           capture_output=True, text=True)
        return p.returncode == 0, 'image built' if p.returncode == 0 else (p.stderr.strip()[-300:] or 'docker compose failed')

    def refresh(self, rp, force=False, drain_timeout=DRAIN_TIMEOUT_SEC):
        """B14: apply a refresh_plan: write the changed keys, then rebuild the image when no job runs (else say how). It
        rebuilds with no change too, so an image built before POOL_BROWSERS was set gets the libraries."""
        if rp.get('error'):
            return False, rp['error']
        text = ''
        files = rp.get('files') or []
        if files:
            bak = os.path.join(pool_dir(rp['pool']), 'bak-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
            for rel in files:
                cur = os.path.join(pool_dir(rp['pool']), *rel.split('/'))
                if os.path.isfile(cur):
                    os.makedirs(os.path.dirname(os.path.join(bak, *rel.split('/'))), exist_ok=True)
                    shutil.copy2(cur, os.path.join(bak, *rel.split('/')))
            copy_pool_templates(pool_dir(rp['pool']), only=set(files))
            text = 'copied %d pool file(s) (%s; old copies in %s)' % (len(files), ', '.join(files), bak)
        if rp['changes']:
            set_env_values(rp['path'], {k: v[1] for k, v in rp['changes'].items()})
            text += ('; ' if text else '') + 'wrote %s in %s' % (', '.join(sorted(rp['changes'])), rp['path'])
        elif not text:
            text = 'nothing to change in %s' % rp['path']
        if not force and not (rp.get('repos')) and self.runners_busy():
            return True, text + ('. A job may run (or the runners cannot be read), so the pool was not rebuilt. '
                                 'By hand: cd %s && docker compose build' % pool_dir(rp['pool']))
        # DL289: build first, while the old container keeps serving jobs.
        before = self.image_ids(rp['pool'])
        ok, detail = self.build_image(rp['pool'])
        if not ok:
            return ok, text + '; the rebuild failed: ' + detail + '. The old container keeps running.'
        cid, run_id, tag_id = self.image_ids(rp['pool'])
        b_tag = before[2]
        if not run_id or not tag_id:
            return True, text + '; build finished; could not compare the image ids, so the container was not touched'
        changed = bool(rp['changes'] or rp.get('files')) or (b_tag and tag_id != b_tag) or run_id != tag_id
        if not changed:
            return True, text + '; image unchanged (cache hit); the container already runs it'
        what = 'image rebuilt' if b_tag and tag_id != b_tag else 'image unchanged (cache hit)'
        ok, detail = self.drain_and_recreate(rp, force, drain_timeout, what)
        return ok, text + '; ' + detail

    def drain_and_recreate(self, rp, force, drain_timeout, what='image rebuilt'):
        """DL289: drain the pool, check GitHub once more, then stop and recreate the container with no build."""
        pool = rp['pool']
        warn = ''
        if force:
            busy, err = busy_pool_runners(self.probe, rp.get('repos') or [], pool)
            if busy:
                warn = 'warning: --force recreates while %s is busy; its job may fail. ' % ', '.join(busy)
        else:
            ok, msg = self.drain(pool, drain_timeout)
            if not ok:
                return False, msg
            gate_ok, gate_msg = rebuild_gate(self.probe, rp.get('repos') or [], pool, False)
            if not gate_ok:
                clear_drain(pool)
                return False, gate_msg + ' The image is built; the container was not recreated.'
        cmd = recreate_command(pool)
        if not force:
            subprocess.run(['docker', 'compose', 'stop', 'pool'], cwd=pool_dir(pool), capture_output=True, text=True)
        clear_drain(pool)  # the new container starts with no drain file
        p = subprocess.run(cmd.split(), cwd=pool_dir(pool), capture_output=True, text=True)
        if p.returncode == 0:
            return True, warn + what + ', container recreated'
        return False, warn + what + ', but the recreate failed (%s). By hand: cd %s && %s' % (
            p.stderr.strip()[-200:] or 'docker compose failed', pool_dir(pool), cmd)

    def drain(self, pool, timeout):
        """DL289: write the drain file and wait for the supervisor's drained file. On timeout remove the drain file."""
        d = pool_dir(pool)
        clear_drain(pool)
        with open(os.path.join(d, DRAIN_FILE), 'w', encoding='utf-8') as f:
            f.write('drain\n')
        waited = 0.0
        while True:
            if self.probe.isfile(os.path.join(d, DRAINED_FILE)):
                return True, ''
            if waited >= timeout:
                break
            self.probe.sleep(DRAIN_POLL_SEC)
            waited += DRAIN_POLL_SEC
        busy = [x.strip() for x in (self.probe.read_text(os.path.join(d, DRAIN_BUSY_FILE)) or '').splitlines() if x.strip()]
        clear_drain(pool)
        return False, 'refused: drain timed out, busy: %s' % (', '.join(busy) or 'unknown')

    def image_ids(self, pool):
        """DL166: (container id, image the container runs, tagged image id); an empty string when one cannot be read."""
        def one(argv):
            r = self.probe.sh(argv)
            return r[1].strip() if r and r[0] == 0 else ''
        c = 'pool-%s-pool-1' % pool
        return (one(['docker', 'inspect', '--format', '{{.Id}}', c]),
                one(['docker', 'inspect', '--format', '{{.Image}}', c]),
                one(['docker', 'image', 'inspect', '--format', '{{.Id}}', 'luismc-runner-pool:%s' % pool]))

    def do_add_agent(self, step):
        tok = self.probe.gh(['api', '-X', 'POST', 'repos/%s/actions/runners/registration-token' % step['repo'], '--jq', '.token'])
        if not tok or tok[0] != 0:
            return False, 'gh could not get a registration token for %s' % step['repo']
        r = self.probe.sh(['docker', 'exec', '-i', 'pool-%s-pool-1' % step['pool'], 'pool-add-agent', step['slug'], step['repo'],
                           '--private', '--pool', step['pool']], input=tok[1].strip() + '\n')
        return (bool(r and r[0] == 0), 'agent added' if r and r[0] == 0 else 'pool-add-agent failed')

    def do_set_variable(self, step):
        r = self.probe.gh(['variable', 'set', step['name'], '--repo', step['repo'], '--body', step['value']])
        if not (r and r[0] == 0):
            return False, 'gh refused'
        text = '%s set' % step['name']
        if step['name'] == 'CI_RUNS_ON':
            text += '. ' + self.runs_on_note(step.get('repo_path'))
        return True, text

    def runs_on_note(self, repo_path):
        """A plain note on which workflows of the local checkout do not read `vars.CI_RUNS_ON`."""
        if not repo_path:
            return 'The workflows were not checked: the repository is not checked out here.'
        folder = os.path.join(repo_path, '.github', 'workflows')
        names = [n for n in self.probe.listdir(folder) if n.endswith(('.yml', '.yaml'))]
        if not names:
            return 'The workflows were not checked: no .github/workflows folder in %s.' % repo_path
        missing = []
        for n in names:
            text = self.probe.read_text(os.path.join(folder, n)) or ''
            if 'runs-on:' in text and 'vars.CI_RUNS_ON' not in text:
                missing.append(n)
        root = [n for n in names if ROOT_NEEDS.search(self.probe.read_text(os.path.join(folder, n)) or '')]
        note = ''
        if root:
            note = (" These workflows need root to install packages, which pool jobs do not have: %s. Keep them on hosted "
                    "runners, or set browsers: chromium and use playwright install chromium without --with-deps." % ', '.join(root))
        if not missing:
            return 'Every workflow with runs-on reads it.' + note
        return ("Warning: CI_RUNS_ON is set, but these workflows do not read it: %s. "
                "Use runs-on: ${{ vars.CI_RUNS_ON || 'ubuntu-latest' }}." % ', '.join(missing)) + note

    def do_verify(self, step):
        res = verify(self.probe, step['repos'], step['pool'])
        bad = [c for c in res if c['status'] != 'ok']
        return not bad, '; '.join('%s: %s' % (c['id'], c['detail']) for c in (bad or res))


def run(pl, ask, ask_delete, say=print, execute=None, check=None, guard=None):
    """Run the plan. `ask(step)` and `ask_delete(step)` return True for a yes. A step with state `already` is skipped.

    An elevated step is printed for the owner, then `check(step)` decides if it is done. Stops at the first failure and
    prints what is left. `guard(step)` (DL310) returns a reason text when a step must wait (an old runner has a job, or the new
    runner is not online yet); the run then stops there. Returns {'done': [...], 'failed': step or None, 'left': [...], 'refused': [...]}.
    """
    execute = execute or Executor().run
    check = check or default_check
    done, left, failed = [], [], None
    steps = pl['steps']
    for r in pl.get('refused', []):
        say(r['reason'])
    for i, step in enumerate(steps):
        if step['state'] == 'already':
            say('%s: already set' % step['title'])
            done.append(step['id'])
            continue
        say('Step: %s' % step['title'])
        if step.get('public'):
            failed = step
            say('  failed: public repository (refused)')
            left = [s['id'] for s in steps[i:]]
            break
        if not ask(step):
            say('  skipped (no yes)')
            left = [s['id'] for s in steps[i:]]
            break
        if step['delete']:
            say('  This deletes: %s' % ', '.join(step['names']))
            if not ask_delete(step):
                say('  not deleted (no yes). Stopping here.')
                left = [s['id'] for s in steps[i:]]
                break
        why = guard(step) if guard else None
        if why:
            failed = step
            say('  waits: %s' % why)
            left = [s['id'] for s in steps[i:]]
            break
        if step['elevated']:
            say('  Run this in an administrator shell, then answer:')
            for line in step.get('say') or step['printed']:
                say('    ' + line)
            own = step['action'] == 'windows-service-remove'  # the pool module checks its own removal step
            ok, detail = (bool((default_check if own else check)(step)), 'checked')
            detail = 'done, checked' if ok else 'not done yet. Run the lines above, then run the setup again.'
        else:
            ok, detail = execute(step)
        say('  %s: %s' % ('done' if ok else 'failed', detail))
        if ok:
            done.append(step['id'])
        else:
            failed = step
            left = [s['id'] for s in steps[i:]]
            break
    if left:
        say('Left to do: ' + ', '.join(left))
    return {'done': done, 'failed': failed, 'left': left, 'refused': pl.get('refused', [])}


# --- verify and doctor ------------------------------------------------------------------------------------------------

def verify(probe, repos, pool, dispatch=False, polls=20, poll_sec=15):
    out = []
    for repo in repos:
        data, why = probe.gh_json(['api', 'repos/%s/actions/runners?per_page=100' % repo])
        mine = [x for x in (data or {}).get('runners', []) if _has_label(
            [l.get('name') for l in x.get('labels', []) if isinstance(l, dict)], 'pool-%s' % pool)] if isinstance(data, dict) else []
        if data is None:
            out.append({'id': 'verify.%s' % repo, 'status': 'fail', 'detail': why})
        elif not mine:
            out.append({'id': 'verify.%s' % repo, 'status': 'fail', 'detail': 'no agent with the label pool-%s' % pool})
        elif not any(x.get('status') == 'online' for x in mine):
            out.append({'id': 'verify.%s' % repo, 'status': 'fail', 'detail': 'agent is registered but offline'})
        else:
            out.append({'id': 'verify.%s' % repo, 'status': 'ok', 'detail': 'agent online with its labels'})
            if dispatch:
                out.append(_check_run(probe, repo, polls, poll_sec))
    return out


def _check_run(probe, repo, polls, poll_sec):
    r = probe.gh(['workflow', 'run', 'pool-check.yml', '--repo', repo])
    if not r or r[0] != 0:
        return {'id': 'verify.%s.run' % repo, 'status': 'fail', 'detail': 'could not start pool-check.yml (is it committed?)'}
    for _ in range(polls):
        probe.sleep(poll_sec)
        data, _why = probe.gh_json(['api', 'repos/%s/actions/workflows/pool-check.yml/runs?per_page=1' % repo])
        runs = (data or {}).get('workflow_runs', []) if isinstance(data, dict) else []
        if runs and runs[0].get('status') == 'completed':
            ok = runs[0].get('conclusion') == 'success'
            return {'id': 'verify.%s.run' % repo, 'status': 'ok' if ok else 'fail', 'detail': 'pool-check %s' % runs[0].get('conclusion')}
    return {'id': 'verify.%s.run' % repo, 'status': 'fail', 'detail': 'pool-check did not finish in time'}


def _pools_dir(root):
    if root and os.path.isdir(os.path.join(str(root), 'pools')):
        return os.path.join(str(root), 'pools')
    base = MS.machine_dir() if MS else os.environ.get('DELIVERY_MACHINE_DIR', '/etc/luismc-delivery')
    return os.path.join(str(base), 'pools')


def _served_playwright(probe, agents, repo_paths):
    """The names of served repositories that use Playwright. `repo_paths` are local checkouts; a checkout is named by the
    agent repository whose name matches its folder, else by the folder name."""
    names = [str(a.get('repo')) for a in agents or [] if a.get('repo')]
    found = []
    for path in repo_paths or []:
        if playwright_use(probe, path):
            base = os.path.basename(os.path.normpath(str(path)))
            found.append(next((r for r in names if r.split('/')[-1] == base), base))
    return found


def _browser_checks(add, probe, pool, env_vals, agents, repo_paths):
    """DL101 (D117): a Playwright repository needs the Chromium libraries in the pool image."""
    users = _served_playwright(probe, agents, repo_paths)
    if not users:
        return
    fix = 'Run `delivery_ci_setup.py pool-refresh --yes` to set POOL_BROWSERS=chromium and rebuild the image; the cap stays.'
    if (env_vals.get('POOL_BROWSERS') or 'none').strip() == 'none':
        add('browsers', 'fail', '%s uses Playwright but the pool .env has POOL_BROWSERS=none, so browser tests fail with a missing '
            'shared library. %s' % (', '.join(users), fix))
        return
    r = probe.sh(['docker', 'ps', '--filter', 'label=' + LABEL, '--format', '{{.Names}} {{.Image}}'])
    image = None
    if r is not None and r[0] == 0:
        for line in (r[1] or '').splitlines():
            name, _, img = line.partition(' ')
            if name in (pool, 'pool-%s' % pool) and img.strip():
                image = img.strip()
    if image is None:
        add('browser-libs', 'warn', 'docker cannot be read here, so the browser libraries in the image are not checked')
        return
    r = probe.sh(['docker', 'run', '--rm', '--entrypoint', 'sh', image, '-c', 'ldconfig -p | grep -q libglib-2.0'], timeout=120)
    if r is None:
        add('browser-libs', 'warn', 'docker cannot be read here, so the browser libraries in the image are not checked')
    elif r[0] != 0:
        add('browser-libs', 'fail', '%s uses Playwright but the image %s lacks the browser libraries (libglib-2.0). %s'
            % (', '.join(users), image, fix))
    else:
        add('browser-libs', 'ok', 'the image has the browser libraries')


# --- DL149: opt-in image layers and the project apt fragment --------------------------------------------------------

LAYERS = {'windows-packaging': 'dotnet-sdk-8.0 wine wine64 xvfb xauth msitools',
          'linux-packaging': 'dpkg-dev rpm make checkpolicy selinux-policy-dev policycoreutils gnupg shellcheck systemd createrepo-c',  # DL274, plus policycoreutils-python-utils when apt has it
          'kvm': 'qemu-system-x86 qemu-utils cloud-image-utils openssh-client'}  # DL281 adds ssh for vm_check.py; the Dockerfile holds the same lists
APT_NAME = re.compile(r'^[A-Za-z0-9+.\-]+$')
LAYER_TOOLS = {'windows-packaging': ('wine', 'xvfb-run', 'dotnet'),
               'linux-packaging': ('dpkg-deb', 'rpmbuild', 'checkmodule', 'semodule_package', 'gpg', 'shellcheck', 'systemd-analyze', 'createrepo_c'),
               'kvm': ('qemu-system-x86_64', 'cloud-localds', 'ssh')}


# --- DL274: optional KVM (off by default) ---------------------------------------------------------------------------

KVM_COMPOSE = 'compose.yaml:compose.kvm.yaml'
KVM_TEST = ['test', '-r', '/dev/kvm', '-a', '-w', '/dev/kvm']


def host_kvm(probe, pool='main'):
    """DL274: (True|False|None, reason). Is /dev/kvm in the Docker VM and usable? Runs `docker run --device /dev/kvm`
    on the pool image when it exists, else on alpine. None means docker could not answer."""
    image = 'luismc-runner-pool:%s' % pool
    have = probe.sh(['docker', 'image', 'inspect', '--format', '{{.Id}}', image])
    if have is None:
        return None, 'docker cannot run here, so KVM was not checked'
    if have[0] != 0:
        image = 'alpine'
    rr = probe.sh(['docker', 'run', '--rm', '--device', '/dev/kvm', '--entrypoint', 'test', image] + KVM_TEST[1:], timeout=180)
    if rr is None:
        return None, 'docker did not finish (timeout or docker cannot run), so KVM was not checked'
    if rr[0] == 0:
        return True, '/dev/kvm is present in the Docker VM and readable and writable'
    if rr[0] == 1:
        return False, '/dev/kvm is in the Docker VM but not readable and writable by the container user'
    return False, ('/dev/kvm is not in the Docker VM (docker exit %s). Windows: turn on nested virtualization for WSL2. '
                   'Linux: load the kvm module and give your user access to /dev/kvm.' % rr[0])


def kvm_runner_commands(probe, repos, pool, want):
    """DL274: (commands, error). The exact `gh api` commands that add (want=True) or remove the `kvm` label on this pool's runners."""
    cmds = []
    for repo in repos:
        data, why = probe.gh_json(['api', 'repos/%s/actions/runners' % repo])
        if not isinstance(data, dict):
            return cmds, 'could not read the runners of %s (%s)' % (repo, why or 'no answer')
        for r in data.get('runners') or []:
            if not str(r.get('name', '')).startswith(pool + '-'):
                continue
            has = 'kvm' in {l.get('name') for l in r.get('labels') or []}
            if want and not has:
                cmds.append("gh api -X POST repos/%s/actions/runners/%s/labels -f 'labels[]=kvm'" % (repo, r.get('id')))
            elif has and not want:
                cmds.append('gh api -X DELETE repos/%s/actions/runners/%s/labels/kvm' % (repo, r.get('id')))
    return cmds, None


def _kvm_checks(add, probe, pool, env_vals, compose_dir, agents):
    """DL274: pool doctor checks for KVM. Reports the host, then the pool's setting. The label is fixed by printed commands."""
    on = (env_vals.get('POOL_KVM') or '').strip() == '1'
    host, why = host_kvm(probe, pool)
    if host is None:
        add('kvm-host', 'warn' if on else 'ok', 'KVM on this host: unknown (%s)' % why)
    else:
        add('kvm-host', 'ok' if (host or not on) else 'fail', 'KVM on this host: %s (%s)' % ('yes' if host else 'no', why))
    if on:
        use = (env_vals.get('COMPOSE_FILE') or '').strip()
        if 'compose.kvm.yaml' not in use or not probe.isfile(os.path.join(compose_dir, 'compose.kvm.yaml')):
            add('kvm-compose', 'fail', 'POOL_KVM=1 but .env has no COMPOSE_FILE with compose.kvm.yaml. Run `delivery_ci_setup.py pool-refresh --kvm on --yes`.')
        else:
            add('kvm-compose', 'ok', 'compose passes /dev/kvm (compose.kvm.yaml); never privileged')
        rr = probe.sh(['docker', 'exec', 'pool-%s-pool-1' % pool] + KVM_TEST)
        if rr is None or rr[0] is None:
            add('kvm-container', 'warn', 'docker cannot be read here, so /dev/kvm in the running pool is not checked')
        else:
            add('kvm-container', 'ok' if rr[0] == 0 else 'fail',
                '/dev/kvm is usable in the running pool, so new runners get the kvm label' if rr[0] == 0
                else '/dev/kvm is not usable in the running pool. Recreate it: cd %s && %s' % (compose_dir, recreate_command(pool)))
    repos = [a.get('repo') for a in (agents or []) if a.get('repo')]
    if repos:
        cmds, err = kvm_runner_commands(probe, repos, pool, on)
        if err:
            add('kvm-label', 'warn', 'the kvm label was not checked: %s' % err)
        elif cmds:
            add('kvm-label', 'warn', 'runner labels differ from POOL_KVM=%s. Run: %s' % ('1' if on else 'unset', ' ; '.join(cmds)))
        else:
            add('kvm-label', 'ok', 'runner labels match POOL_KVM (%s)' % ('kvm label on' if on else 'no kvm label'))


def parse_pool_apt(text):
    """(names, errors) of a .delivery/pool.apt text: one package per line, # starts a comment. Names are letters, digits, + - ."""
    names, errors = [], []
    for n, line in enumerate((text or '').splitlines(), 1):
        name = line.split('#', 1)[0].strip()
        if not name:
            continue
        if not APT_NAME.match(name) or name.startswith('-'):
            errors.append('refused: .delivery/pool.apt line %d has "%s". A package name may hold only letters, digits, + - . and must not start with -.' % (n, name))
        elif name not in names:
            names.append(name)
    return names, errors


def read_pool_layers(repo_paths):
    """DL149: (layers, apt names, errors) from the repo checkouts. Layers: `pool.layers` in .delivery/config.json. Apt: .delivery/pool.apt."""
    layers, apt, errors = [], [], []
    for path in repo_paths or []:
        try:
            with open(os.path.join(str(path), '.delivery', 'config.json'), encoding='utf-8-sig') as f:
                cfg = json.load(f)
        except (OSError, ValueError):
            cfg = {}
        want = ((cfg.get('pool') or {}).get('layers') or []) if isinstance(cfg, dict) and isinstance(cfg.get('pool') or {}, dict) else []
        for x in want if isinstance(want, list) else []:
            if x not in LAYERS:
                errors.append('refused: pool.layers has "%s". The known layers are: %s.' % (x, ', '.join(sorted(LAYERS))))
            elif x not in layers:
                layers.append(x)
        try:
            with open(os.path.join(str(path), '.delivery', 'pool.apt'), encoding='utf-8-sig') as f:
                names, errs = parse_pool_apt(f.read())
        except OSError:
            names, errs = [], []
        errors += errs
        apt += [n for n in names if n not in apt]
    return layers, apt, errors


def busy_pool_runners(probe, repos, pool):
    """DL149: (names of busy pool runners, error). Reads `gh api repos/<repo>/actions/runners` for each repo; unreadable -> error."""
    busy = []
    for repo in repos:
        data, why = probe.gh_json(['api', 'repos/%s/actions/runners' % repo])
        if not isinstance(data, dict):
            return busy, 'could not read the runners of %s (%s)' % (repo, why or 'no answer')
        for r in data.get('runners') or []:
            labels = {l.get('name') for l in r.get('labels') or []}
            if r.get('busy') and ('pool-%s' % pool in labels or str(r.get('name', '')).startswith(pool + '-')):
                busy.append('%s (%s)' % (r.get('name'), repo))
    return busy, None


def rebuild_gate(probe, repos, pool, force=False):
    """DL149: (ok, message). The image is not rebuilt while a pool runner is busy; --force rebuilds with a warning."""
    busy, err = busy_pool_runners(probe, repos, pool)
    if busy:
        if force:
            return True, 'warning: --force rebuilds while %s is busy; its job may fail' % ', '.join(busy)
        return False, 'refused: pool runner busy: %s. Wait for the job or use --force.' % ', '.join(busy)
    if err:
        if force:
            return True, 'warning: --force rebuilds although %s' % err
        return False, 'refused: %s. Use --force to rebuild anyway.' % err
    return True, ''


def runners_folder_dockerfiles(repo_path):
    """DL149: Dockerfiles under a runners folder of a repo (the pool never reads them)."""
    found = []
    for base, dirs, files in os.walk(str(repo_path)):
        dirs[:] = [d for d in dirs if d not in ('.git', 'node_modules')]
        parts = os.path.relpath(base, str(repo_path)).replace('\\', '/').split('/')
        if any(p.lower() in ('runners', 'runner') for p in parts) and any(f.lower().startswith('dockerfile') for f in files):
            found += [os.path.join(os.path.relpath(base, str(repo_path)), f).replace('\\', '/') for f in files if f.lower().startswith('dockerfile')]
    return sorted(found)


def pool_container_running(probe, pool):
    """DL199: True when the pool container is running."""
    r = probe.sh(['docker', 'inspect', '-f', '{{.State.Running}}', 'pool-%s-pool-1' % pool])
    return bool(r is not None and r[0] == 0 and (r[1] or '').strip().lower() == 'true')


def _probe_layer_tool(probe, pool, image, tool, running):
    """DL199: 'ok', 'missing' (the probe ran and command -v failed) or a text naming why docker could not probe.
    A running container is probed with `docker exec`; only without one, `docker run` on the image."""
    check = 'command -v %s' % tool
    if running:
        argv, what = ['docker', 'exec', 'pool-%s-pool-1' % pool, 'sh', '-c', check], 'docker exec'
    else:
        argv, what = ['docker', 'run', '--rm', '--entrypoint', 'sh', image, '-c', check], 'docker run on %s' % image
    rr = probe.sh(argv, timeout=120)
    if rr is None:
        return '%s did not finish (timeout or docker cannot run)' % what
    if rr[0] == 0:
        return 'ok'
    if rr[0] == 1:
        return 'missing'
    return '%s failed with exit %s' % (what, rr[0])


def _layer_checks(add, probe, pool, env_vals, compose, repo_paths):
    """DL149: pool doctor checks for the layers, stray runner Dockerfiles and the tool cache."""
    layers = [x for x in (env_vals.get('POOL_LAYERS') or '').strip().split(',') if x]
    want, _apt, _errs = read_pool_layers(repo_paths)
    if set(want) - set(layers):  # DL155: the pool may hold more (other repos' layers)
        add('layers-config', 'warn', 'the repo config asks for layers [%s] but the pool .env has [%s]. Run `delivery_ci_setup.py pool-refresh --yes`.'
            % (', '.join(want), ', '.join(layers)))
    if layers:
        image = container_image(probe, pool)  # DL184: the running container's image, the tag only when none runs
        running = pool_container_running(probe, pool)
        for layer in layers:
            tools = LAYER_TOOLS.get(layer, ())
            if image is None:
                add('layer-' + layer, 'warn', 'docker cannot be read here, so the %s layer is not checked (needs %s in the image)' % (layer, ', '.join(tools)))
                continue
            missing, errors = [], []
            for tool in tools:
                state = _probe_layer_tool(probe, pool, image, tool, running)
                if state == 'missing':
                    missing.append(tool)
                elif state != 'ok':
                    errors.append(state)
            if missing:
                add('layer-' + layer, 'fail', 'the %s layer is on but the image %s lacks %s. Rebuild: delivery_ci_setup.py pool-refresh --yes' % (layer, image, ', '.join(missing)))
            elif errors:  # DL199: the probe did not run; this says nothing about the tools
                add('layer-' + layer, 'warn', 'cannot probe the %s layer: %s' % (layer, errors[0]))
            else:
                add('layer-' + layer, 'ok', 'the image has %s' % ', '.join(tools))
    for path in repo_paths or []:
        for df in runners_folder_dockerfiles(path):
            add('stray-dockerfile', 'fail', '%s is not used by the pool; the pool image is built from the plugin. Move its apt packages to .delivery/pool.apt '
                '(one name per line) or turn on a layer (pool.layers in .delivery/config.json), then run `delivery_ci_setup.py pool-refresh --yes`.' % df)
    tools_mount = re.search(r'^\s*-\s*([A-Za-z0-9_.\-]+):/ci-tools\s*$', compose or '', re.M)
    if not tools_mount:
        add('tool-cache', 'fail', 'compose.yaml has no named volume mounted at /ci-tools, so the tool cache is lost on every recreate')
    else:
        rr = probe.sh(['docker', 'exec', 'pool-%s-pool-1' % pool, 'sh', '-c', 'test -w /ci-tools'])
        if rr is None or rr[0] is None:
            add('tool-cache', 'warn', '/ci-tools is a volume (%s); docker cannot be read here, so writability is not checked' % tools_mount.group(1))
        else:
            add('tool-cache', 'ok' if rr[0] == 0 else 'fail',
                '/ci-tools is a writable volume (%s)' % tools_mount.group(1) if rr[0] == 0 else '/ci-tools is not writable in the running pool')


def doctor_checks(root=None, probe=None, repo_paths=None):
    """Checks of the pool for the doctor's `machine` check (contract 12.3). `root` may be a machine folder with `pools/`.
    Each: {"id": "pool.<name>", "status": "ok"|"warn"|"fail"|"skip", "detail": str}. No pool: one `skip`."""
    probe = probe or Probe()
    pools = _pools_dir(root)
    names = [n for n in probe.listdir(pools) if probe.isfile(os.path.join(pools, n, 'compose.yaml'))]
    if not names:
        return [{'id': 'pool.none', 'status': 'skip', 'detail': 'no pool on this machine'}]
    out = []
    for n in names:
        d = os.path.join(pools, n)
        compose = probe.read_text(os.path.join(d, 'compose.yaml')) or ''
        env = probe.read_text(os.path.join(d, '.env')) or ''
        try:
            agents = json.loads(probe.read_text(os.path.join(d, 'agents.json')) or '{}').get('agents', [])
        except (ValueError, AttributeError):
            agents = None

        def add(name, status, detail):
            out.append({'id': 'pool.%s.%s' % (n, name), 'status': status, 'detail': detail})
        add('socket', 'fail' if 'docker.sock' in compose else 'ok',
            'the Docker socket is mounted in the pool' if 'docker.sock' in compose else 'no Docker socket in the pool')
        env_has = {l.split('=', 1)[0].strip() for l in env.splitlines()
                   if '=' in l and not l.lstrip().startswith('#') and l.split('=', 1)[1].strip()}
        missing = [v for v in compose_required_vars(compose) if v not in env_has]
        add('required-vars', 'fail' if missing else 'ok',
            ('compose.yaml requires %s but .env has no value for it, so `docker compose up` fails. Run `delivery_ci_setup.py pool-refresh --yes`; it writes '
             'RUNNER_SHA256 and keeps the cap.'
             % ', '.join(missing)) if missing else 'every required variable of compose.yaml is in .env')
        ev = {l.split('=', 1)[0].strip(): l.split('=', 1)[1].strip() for l in env.splitlines() if '=' in l and not l.lstrip().startswith('#')}
        if ev.get('RUNNER_SHA256'):
            ver = ev.get('RUNNER_VERSION') or RUNNER_VERSION
            want = RUNNER_SHA256 if ver == RUNNER_VERSION else runner_sha(probe, ver)
            have = ev['RUNNER_SHA256']
            if sha_is_bad(have) or (want and have.lower() != want.lower()):
                add('runner-sha', 'warn', 'RUNNER_SHA256 %s in .env is not the pinned or released hash for runner %s, so the image build '
                    'fails its checksum. Run `delivery_ci_setup.py pool-refresh --yes`.' % (short_sha(have), ver))
            else:
                add('runner-sha', 'ok', 'RUNNER_SHA256 matches runner %s' % ver)
        has_cap = 'POOL_CPUS=' in env and 'POOL_MEM=' in env
        add('cap', 'ok' if has_cap else 'fail', 'cap set in .env' if has_cap else '.env has no POOL_CPUS and POOL_MEM')
        env_vals = dict(l.split('=', 1) for l in env.splitlines() if '=' in l and not l.startswith('#'))
        mem_g = None
        try:
            mem_g = float(str(env_vals.get('POOL_MEM', '')).strip().rstrip('gG'))
            cpu_n = float(str(env_vals.get('POOL_CPUS', '')).strip())
            ratio = mem_g / cpu_n
        except (ValueError, ZeroDivisionError):
            ratio = None
        if ratio is not None:
            low = ratio < WARN_GIB_PER_CPU
            add('mem-per-cpu', 'warn' if low else 'ok',
                ('POOL_MEM %sg over POOL_CPUS %s is %.1f GiB per CPU, under %.1f. Run the setup again with --resize to resize the pool.'
                 % (env_vals['POOL_MEM'].strip().rstrip('gG'), env_vals['POOL_CPUS'].strip(), ratio, WARN_GIB_PER_CPU)) if low
                else '%.1f GiB per CPU' % ratio)
        per_agent = mem_g / len(agents) if (mem_g is not None and agents) else None
        if per_agent is not None:
            low = per_agent < WARN_GIB_PER_AGENT
            add('mem-per-agent', 'warn' if low else 'ok',
                ('POOL_MEM %sg over %d agents is %.1f GiB each, under %.0f. Raise POOL_MEM by running the setup again with --resize on a host '
                 'with room, or use fewer agents per pool.' % (env_vals['POOL_MEM'].strip().rstrip('gG'), len(agents), per_agent,
                                                              WARN_GIB_PER_AGENT)) if low
                else '%.1f GiB per agent' % per_agent)
        if agents is None:
            add('users', 'fail', 'agents.json is unreadable')
        else:
            users = [a.get('user') for a in agents]
            dup = len(users) != len(set(users)) or any(not u for u in users)
            add('users', 'fail' if dup else 'ok', 'agents share a user or have none' if dup else 'one user per agent (%d)' % len(users))
            pub = [a.get('repo') for a in agents if a.get('private') is not True]
            add('private', 'fail' if pub else 'ok', 'agent for a repository not recorded private: %s' % ', '.join(map(str, pub))
                if pub else 'every agent\'s repository is private')
        _browser_checks(add, probe, n, env_vals, agents, repo_paths)
        _layer_checks(add, probe, n, env_vals, compose, repo_paths)
        _kvm_checks(add, probe, n, {k.strip(): v.strip() for k, v in env_vals.items()}, d, agents)
        live = live_cap(probe, n) if has_cap else None
        if live is not None:
            try:
                want_mem = float(str(env_vals.get('POOL_MEM', '')).strip().rstrip('gG')) * 2 ** 30
                want_cpu = float(str(env_vals.get('POOL_CPUS', '')).strip())
            except ValueError:
                want_mem = want_cpu = None
            if want_mem is not None:
                bad = abs(live[0] - want_mem) > 1024 * 1024 or abs(live[1] - want_cpu * 1e9) > 1e6
                add('live-cap', 'fail' if bad else 'ok',
                    ('the running container has %.2f GiB and %.2f CPUs but .env says POOL_MEM %s and POOL_CPUS %s. Recreate it: cd %s && %s'
                     % (live[0] / 2 ** 30, live[1] / 1e9, env_vals['POOL_MEM'].strip(), env_vals['POOL_CPUS'].strip(), d,
                        recreate_command(n))) if bad else 'the running container matches the cap in .env')
        r = probe.sh(['docker', 'ps', '--filter', 'label=' + LABEL, '--format', '{{.Names}}'])
        if r is None or r[0] != 0:
            add('running', 'warn', 'docker cannot be read here')
        else:
            on = n in r[1] or 'pool-%s' % n in r[1]
            add('running', 'ok' if on else 'warn', 'pool container is running with the plugin label' if on else 'pool container is not running')
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog='delivery_runner_pool.py', description=__doc__.split('\n\n')[0])
    ap.add_argument('action', choices=['detect', 'sizing', 'plan', 'verify', 'doctor'])
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--repos', default='')
    ap.add_argument('--windows-repos', default='')
    ap.add_argument('--pool', default='main')
    ap.add_argument('--browsers', choices=BROWSERS, default=None, help='add the Chromium system libraries to the pool image (default: chromium when a served repository uses Playwright, else none)')
    ap.add_argument('--repo-path', action='append', default=None,
                    help='a local checkout of an agent repository (workflows checked for CI_RUNS_ON; lockfiles read for the Playwright version); repeatable')
    ap.add_argument('--playwright-version', default=None, help='X.Y.Z; overrides the version found in the lockfiles (chromium only)')
    ap.add_argument('--total-gib', type=float)
    ap.add_argument('--used-gib', type=float, help='memory used outside WSL, in GiB (default: measured)')
    ap.add_argument('--cpus', type=float, help="this machine's CPU count (default: measured)")
    ap.add_argument('--docker-gib', type=float)
    ap.add_argument('--largest-shard-gib', type=float)
    ap.add_argument('--resize', action='store_true', help='use the measured cap instead of the one already in the pool .env')
    ap.add_argument('--shrink', action='store_true', help='allow --resize to lower POOL_MEM or POOL_CPUS')
    ap.add_argument('--pool-gib', type=float, help="the pool's memory you want, in GiB (checked against the budgets)")
    ap.add_argument('--pool-cpus', type=float, help="the pool's CPUs you want (checked against the budgets)")
    ap.add_argument('--only', choices=['windows', 'linux'], help='plan only this OS\'s steps (host-load stays in both)')
    args = ap.parse_args(argv)
    split = lambda s: [x for x in s.split(',') if x]  # noqa: E731
    if args.action == 'detect':
        print(detect(json=True) if args.json else json.dumps(detect(), indent=2))
    elif args.action in ('sizing', 'plan'):
        found = detect()
        found['pool_env'] = read_pool_env(Probe(), args.pool)
        res = resolve_cap(found, args.total_gib, args.used_gib, args.cpus, args.docker_gib, args.largest_shard_gib, args.resize,
                          args.shrink, args.pool_gib, args.pool_cpus)
        if args.action == 'sizing':
            if res is None:
                print('sizing could not measure this machine; give --total-gib and --cpus', file=sys.stderr)
                return 1
            print(json.dumps(res, indent=2))
            return 0 if res['ok'] else 1
        if args.playwright_version and not valid_playwright_version(args.playwright_version):
            print('--playwright-version must look like 1.62.1', file=sys.stderr)
            return 2
        pl = plan(found, split(args.repos), split(args.windows_repos), args.pool, res, repo_path=(args.repo_path or [None])[0],
                  browsers=args.browsers, playwright_version=args.playwright_version, repo_paths=args.repo_path or [], probe=Probe(), only=args.only)
        print(json.dumps(pl, indent=2))
        return 1 if pl['blocked'] else 0
    elif args.action == 'verify':
        res = verify(Probe(), split(args.repos), args.pool, dispatch=True)
        print(json.dumps(res, indent=2))
        return 0 if all(c['status'] == 'ok' for c in res) else 1
    else:
        res = doctor_checks()
        print(json.dumps(res, indent=2) if args.json else '\n'.join('%-5s %s: %s' % (c['status'], c['id'], c['detail']) for c in res))
        return 1 if any(c['status'] == 'fail' for c in res) else 0
    return 0


if __name__ == '__main__':
    sys.exit(main())
