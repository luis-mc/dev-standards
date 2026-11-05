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
import json
import math
import os
import posixpath
import re
import secrets
import shutil
import subprocess
import sys
import time

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
PLAYWRIGHT_VERSION = '1.62.1'  # the pinned fallback for the Chromium system libraries (DL69); keep the Dockerfile and compose defaults equal
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
        try:
            p = subprocess.run(argv, capture_output=True, text=True, input=input, timeout=timeout)
        except (OSError, subprocess.SubprocessError):
            return None
        return p.returncode, p.stdout

    def gh(self, args, input=None):
        return self.sh(['gh'] + list(args), input=input)

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

    def wsl_vm_gib(self):
        """Memory held by the WSL VM (vmmem / vmmemWSL) in GiB; 0.0 when there is none or it cannot be read."""
        if not self.platform.startswith('win'):
            return 0.0
        r = self.sh(['powershell', '-NoProfile', '-Command',
                     "(Get-Process -Name vmmem,vmmemWSL -ErrorAction SilentlyContinue | Measure-Object WorkingSet64 -Sum).Sum"])
        text = r[1].strip() if r and r[0] == 0 else ''
        return round(int(text) / 2.0 ** 30, 1) if text.isdigit() else 0.0

    def docker_cpus(self):
        """CPUs Docker sees (`docker info --format {{.NCPU}}`, inside WSL on Windows), or None when Docker cannot be read."""
        pre = ['wsl'] if self.platform.startswith('win') else []
        r = self.sh(pre + ['docker', 'info', '--format', '{{.NCPU}}'])
        text = r[1].replace('\x00', '').strip() if r and r[0] == 0 else ''
        return int(text) if text.isdigit() and int(text) > 0 else None

    def container_gib(self):
        """{'pool': GiB used by this pool's containers, 'other': GiB used by other containers, 'others': [names]}.
        Reads `docker ps` and `docker stats` (inside WSL on Windows). Zeros when Docker cannot be read."""
        pre = ['wsl'] if self.platform.startswith('win') else []
        names = self.sh(pre + ['docker', 'ps', '--format', '{{.Names}}\t{{.Label "' + LABEL + '"}}'])
        stats = self.sh(pre + ['docker', 'stats', '--no-stream', '--format', '{{.Name}}\t{{.MemUsage}}'])
        out = {'pool': 0.0, 'other': 0.0, 'others': []}
        if not names or names[0] != 0:
            return out
        mine = {}
        for line in names[1].replace('\x00', '').splitlines():
            cols = line.rstrip('\r').split('\t')
            if cols and cols[0]:
                mine[cols[0]] = len(cols) > 1 and cols[1].strip() != ''
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
                      'Select-Object Name,State,PathName | ConvertTo-Json'])
        if r and r[0] == 0 and r[1].strip():
            try:
                data = json.loads(r[1])
            except ValueError:
                data = []
            for x in [data] if isinstance(data, dict) else data:
                out.append({'name': x.get('Name'), 'status': str(x.get('State', x.get('Status'))), 'kind': 'windows-service',
                            'folder': service_folder(x.get('PathName')) or None})
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


def detect_host(probe):
    """This machine's figures for sizing: platform, python, machine folder, CPUs, total and used GiB (None when unmeasurable)."""
    mem = probe.memory_gib()
    vm, box = probe.wsl_vm_gib(), probe.container_gib()
    used = mem[1] if mem else None
    if used is not None:
        # The WSL VM holds the pool and every other container: leave it out of "used". With no VM (native Linux), leave
        # out the pool's own containers instead. A rerun then sees the same figure as the first run.
        used = round(max(0.0, used - (vm if vm > 0 else box['pool'])), 1)
    return {'platform': probe.platform, 'python': probe.python(), 'machine_dir': probe.machine_dir(), 'cpus': probe.cpu_count(), 'docker_cpus': docker_ncpu(probe),
            'total_gib': mem[0] if mem else None, 'used_gib': used, 'wsl_vm_gib': vm,
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


def cap_cpus(requested, ncpu):
    """Docker refuses a CPU limit equal to the CPUs it sees, so the cap stays at NCPU - 1 (never below 1)."""
    if not ncpu:
        return requested
    return max(1, min(requested, int(ncpu) - 1))


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
    cpu = max(1.0, math.floor(cpus * CPU_PCT / 100.0 * 2) / 2.0)
    host_cpus = int(cpus)
    procs = int(math.floor(cpu)) + 1  # headroom: Docker refuses a CPU limit equal to the VM's CPUs
    if procs > host_cpus:
        cpu = max(1.0, cpu - 1)
        procs = int(math.floor(cpu)) + 1
    procs = max(1, min(procs, host_cpus))
    cpu = cap_cpus(cpu, docker_cpus)
    wsl_mem = int(math.ceil(mem + sidecar_gib + vm_gib))
    if others_run:
        if wsl_current is not None:
            wsl_mem = max(wsl_mem, int(math.ceil(wsl_current)))
        wsl_mem = max(wsl_mem, int(math.ceil(other_gib + mem + sidecar_gib + vm_gib)))
    out = {'mem_gib': mem, 'cpus': cpu, 'memory_room_gib': round(room, 1), 'ok': True, 'message': '',
           'wsl': {'memory': wsl_mem, 'processors': procs}}
    if mem <= 0:
        out.update(ok=False, message='No memory is left for the pool (room %.1f GiB). Close other programs or raise the '
                                     'WSL memory in .wslconfig, then run the setup again.' % room)
    elif largest_shard_gib is not None and mem < largest_shard_gib:
        out.update(ok=False, message='The pool cap (%.1f GiB) is below the largest Linux shard (%.1f GiB). Lower that '
                                     'shard\'s memory_gib in ci-shards.json, or free memory on this machine.'
                                     % (mem, largest_shard_gib))
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
                       'other_containers_gib': host.get('other_containers_gib') or 0.0}
    return res


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
            return any('pool-%s' % pool in x['labels'] and x['status'] == 'online' for x in r['runners'])
    return False


def _winpath(path):
    return str(path).replace('/', '\\')


LOOP_SCRIPT = """\
import os
import sys
import time

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


def browsers_note(browsers):
    """One plain sentence for the plan: what the image holds for browsers."""
    if browsers == 'chromium':
        return ('The image includes the Chromium system libraries and is larger (about 300-400 MB). '
                'Jobs install the browser itself with `playwright install chromium`.')
    return 'The image has no Chromium libraries. Set browsers: chromium to add them (about 300-400 MB more).'


def plan(found, linux_repos=None, windows_repos=None, pool='main', cap=None, serial=None, limits=None, repo_path=None,
         browsers='none', playwright_version=None, repo_paths=None, probe=None):
    """The steps, in the order of contract 6.3. A public repository gets no step; it is listed in `refused`.

    With no repositories given, they come from detect (`derive_repos`). With none derived either, the plan has no step
    and says why: it never removes a runner it does not rebuild. Removals are limited to the planned repositories.
    A runner that already belongs to this pool is kept and its steps say `already` (safe to run again)."""
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
    base = {'pool': pool, 'refused': refused, 'cap': cap, 'derived': derived, 'blocked': None}
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
    for r in found['github']['repos']:
        if r['repo'] not in planned:
            continue
        for x in r['runners']:
            if 'pool-%s' % pool in x['labels']:
                continue  # already part of this pool: kept
            steps.append(_step('remove:%s:%s' % (r['repo'], x['name']),
                               'Remove runner %s (%s) from %s' % (x['name'], x['os'], r['repo']), 'remove-runner',
                               delete=True, names=['runner %s (%s) in %s on GitHub' % (x['name'], x['os'], r['repo'])],
                               repo=r['repo'], runner_id=x['id'], runner=x['name']))
    repo_of = {f['path']: f.get('repo') for f in found['folders']}
    for svc in found['services']:
        if svc.get('kind') != 'windows-service':
            continue
        if repo_of.get(svc.get('folder')) not in planned | {None}:
            continue
        n = svc['name']
        steps.append(_step('winsvc-remove:%s' % n, 'Stop and delete the Windows runner service %s' % n, 'windows-service-remove',
                           delete=True, names=['Windows service ' + n], elevated=True, service=n,
                           printed=['sc.exe stop "%s"' % n, 'sc.exe delete "%s"' % n]))
    for f in found['folders']:
        if f.get('repo') not in planned | {None}:
            continue
        steps.append(_step('delete-folder:%s' % f['path'], 'Delete the old runner folder %s' % f['path'], 'delete-folder',
                           delete=True, names=[f['path']], path=f['path']))
    for c in found['containers']:
        if c.get('pool'):
            continue  # the pool's own container is kept
        steps.append(_step('delete-container:%s' % c['name'], 'Stop and delete the container %s' % c['name'],
                           'delete-container', delete=True, names=['container ' + c['name']], container=c['name'],
                           via=c.get('via', '')))
    steps.append(_step('machine-config', 'Write the machine config (limits, slots) through the machine layer', 'machine-config',
                       limits=limits or {}))
    if win:
        py = _winpath(host.get('python') or 'python')
        dest = host.get('machine_dir', 'C:/ProgramData/luismc-delivery').rstrip('/\\') + '/host-load'
        loop = _winpath(dest + '/host-load-loop.py')
        steps.append(_step('host-load-files', 'Copy load.py and a 15-second loop script to %s' % dest, 'host-load-files', dest=dest))
        steps.append(_step('host-load-task', 'Register the scheduled task that writes the host load file every 15 seconds',
                           'host-load-task', elevated=True,
                           printed=['schtasks /Create /TN luismc-host-load /SC ONSTART /RU SYSTEM /RL HIGHEST /F '
                                    '/TR "\\"%s\\" \\"%s\\""' % (py, loop),
                                    'schtasks /Run /TN luismc-host-load']))
    if keep_l:
        w, enough = _wsl_values(found, cap)
        if w and (win or (found.get('wsl') or {}).get('exists')):
            cur = found.get('wsl') or {}
            s1 = _step('wslconfig', 'Write %s with the pool ceiling (memory %s -> %sGB, processors %s -> %s; the old file is kept as .bak)' % (
                cur.get('file'), _gb(cur.get('memory')), w['memory'], cur.get('processors') or 'unset', w['processors']),
                'wslconfig', cap=cap)
            if enough:
                s1['state'] = 'already'
            steps.append(s1)
            if not enough:
                steps.append(_step('wsl-restart', 'Restart WSL so the ceiling applies (only when no job runs; stops every container)',
                                   'wsl-restart'))
        old = found.get('pool_env') or {}
        browsers = browsers if browsers in BROWSERS else 'none'
        pw, pw_source = resolve_playwright(probe or Probe(), browsers, playwright_version, repo_paths or ([repo_path] if repo_path else []))
        pw_text = ' Playwright %s (%s).' % (pw, pw_source) if pw else ''
        steps.append(_step('pool-files', 'Write the pool files for "%s" (compose, agents.json, .env: POOL_MEM %s -> %sg, '
                           'POOL_CPUS %s -> %s, POOL_BROWSERS %s). %s%s' % (
                               pool, old.get('POOL_MEM') or 'unset', (cap or {}).get('mem_gib', 4),
                               old.get('POOL_CPUS') or 'unset', (cap or {}).get('cpus', 1), browsers, browsers_note(browsers), pw_text),
                           'pool-files', pool=pool, cap=cap, browsers=browsers, playwright_version=pw))
        steps.append(_step('pool-up', 'Build and start the pool container', 'pool-up', pool=pool))
        for repo in keep_l:
            s = _step('agent:%s' % repo, 'Add one pool agent for %s' % repo, 'add-agent', repo=repo, pool=pool, slug=slug_of(repo))
            if _pool_has(found, pool, repo):
                s['state'] = 'already'
            steps.append(s)
    for repo in keep_w:
        slug = slug_of(repo)
        steps.append(_step('winsvc:%s' % repo, 'Windows runner service for %s with both hooks' % repo, 'windows-service',
                           repo=repo, slug=slug, elevated=True,
                           printed=['cd C:/actions-runners/%s' % slug,
                                    './config.cmd --url https://github.com/%s --token <TOKEN> --name host1-%s --labels self-hosted,windows --runasservice' % (repo, slug),
                                    'Set ACTIONS_RUNNER_HOOK_JOB_STARTED=<plugin>/scripts/runner_load_gate.ps1 and ACTIONS_RUNNER_HOOK_JOB_COMPLETED=<plugin>/scripts/runner_job_done.ps1 in C:/actions-runners/%s/.env (the runner rejects .cmd hooks)' % slug]))
    for repo in keep_l:
        value = json.dumps(['self-hosted', 'linux', 'pool-%s' % pool])
        steps.append(_step('var:CI_RUNS_ON:%s' % repo, 'Set CI_RUNS_ON for %s' % repo, 'set-variable', repo=repo,
                           name='CI_RUNS_ON', value=value, repo_path=repo_path))
        if serial is not None:
            steps.append(_step('var:CI_SERIAL:%s' % repo, 'Set CI_SERIAL for %s' % repo, 'set-variable', repo=repo,
                               name='CI_SERIAL', value='true' if serial else 'false'))
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


def write_pool_files(pool, cap, dest=None, copy_from=None, runner_version=None, browsers='none',
                     playwright_version=None):
    """Write the pool folder. `.env` holds the cap and the machine dir only (D42); the database password is a 0600 file."""
    dest = dest or pool_dir(pool)
    os.makedirs(dest, exist_ok=True)
    for name in os.listdir(TEMPLATES):
        src = os.path.join(TEMPLATES, name)
        if os.path.isfile(src) and name != 'pool-check.yml':
            copy_lf(src, os.path.join(dest, name))
    hooks_dest = os.path.join(dest, 'hooks')
    os.makedirs(hooks_dest, exist_ok=True)
    for name in os.listdir(os.path.join(TEMPLATES, 'hooks')):
        src = os.path.join(TEMPLATES, 'hooks', name)
        if os.path.isfile(src):
            copy_lf(src, os.path.join(hooks_dest, name))
    deliv = os.path.join(dest, 'delivery')
    os.makedirs(deliv, exist_ok=True)
    for name in ('runner_load_gate.py', 'runner_job_done.py', 'load.py', 'machine_slots.py'):
        src = os.path.join(copy_from or HERE, name)
        if os.path.isfile(src):
            copy_lf(src, os.path.join(deliv, name))
    with open(os.path.join(dest, '.env'), 'w', encoding='utf-8') as f:
        f.write('POOL_NAME=%s\nPOOL_CPUS=%s\nPOOL_MEM=%sg\nMACHINE_DIR=%s\nRUNNER_VERSION=%s\nPOOL_BROWSERS=%s\nPLAYWRIGHT_VERSION=%s\n' % (
            pool, (cap or {}).get('cpus', 1), (cap or {}).get('mem_gib', 4), os.path.dirname(os.path.dirname(dest)),
            runner_version or RUNNER_VERSION, browsers if browsers in BROWSERS else 'none',
            playwright_version if valid_playwright_version(playwright_version) else PLAYWRIGHT_VERSION))
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


class Executor:
    """Real step handlers. Each returns (ok, detail). Tokens go through a pipe and are never printed."""

    def __init__(self, probe=None):
        self.probe = probe or Probe()

    def run(self, step):
        h = getattr(self, 'do_' + step['action'].replace('-', '_'), None)
        if h is None:
            return False, 'no handler for %s' % step['action']
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

    def do_pool_files(self, step):
        version, _sha, source = resolve_runner(self.probe)
        cap = dict(step.get('cap') or {})
        if cap.get('cpus') is not None:
            cap['cpus'] = cap_cpus(cap['cpus'], docker_ncpu(self.probe))
        dest = write_pool_files(step['pool'], cap, runner_version=version, browsers=step.get('browsers') or 'none',
                                playwright_version=step.get('playwright_version'))
        text = 'wrote %s (runner %s, %s)' % (dest, version, source)
        if step.get('browsers') == 'chromium':
            text += '; Playwright %s' % (step.get('playwright_version') or PLAYWRIGHT_VERSION)
        return True, text

    def do_pool_up(self, step):
        version = read_pool_env(self.probe, step['pool']).get('RUNNER_VERSION') or RUNNER_VERSION
        if below_floor(version):
            return False, below_floor(version)
        sha = runner_sha(self.probe, version)
        if not sha:
            return False, 'could not read the SHA-256 of the runner release; the image is not built without it'
        browsers = read_pool_env(self.probe, step['pool']).get('POOL_BROWSERS') or 'none'
        pw = read_pool_env(self.probe, step['pool']).get('PLAYWRIGHT_VERSION')
        pw = pw if valid_playwright_version(pw) else PLAYWRIGHT_VERSION
        env = dict(os.environ, RUNNER_SHA256=sha, RUNNER_VERSION=version, POOL_BROWSERS=browsers, PLAYWRIGHT_VERSION=pw)
        p = subprocess.run(['docker', 'compose', 'up', '-d', '--build'], cwd=pool_dir(step['pool']), env=env,
                           capture_output=True, text=True)
        return p.returncode == 0, 'pool is up' if p.returncode == 0 else (p.stderr.strip()[-300:] or 'docker compose failed')

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


def run(pl, ask, ask_delete, say=print, execute=None, check=None):
    """Run the plan. `ask(step)` and `ask_delete(step)` return True for a yes. A step with state `already` is skipped.

    An elevated step is printed for the owner, then `check(step)` decides if it is done. Stops at the first failure and
    prints what is left. Returns {'done': [...], 'failed': step or None, 'left': [...], 'refused': [...]}.
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
        if step['elevated']:
            say('  Run this in an administrator shell, then answer:')
            for line in step['printed']:
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
        mine = [x for x in (data or {}).get('runners', []) if 'pool-%s' % pool in
                [l.get('name') for l in x.get('labels', []) if isinstance(l, dict)]] if isinstance(data, dict) else []
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


def doctor_checks(root=None, probe=None):
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
        has_cap = 'POOL_CPUS=' in env and 'POOL_MEM=' in env
        add('cap', 'ok' if has_cap else 'fail', 'cap set in .env' if has_cap else '.env has no POOL_CPUS and POOL_MEM')
        if agents is None:
            add('users', 'fail', 'agents.json is unreadable')
        else:
            users = [a.get('user') for a in agents]
            dup = len(users) != len(set(users)) or any(not u for u in users)
            add('users', 'fail' if dup else 'ok', 'agents share a user or have none' if dup else 'one user per agent (%d)' % len(users))
            pub = [a.get('repo') for a in agents if a.get('private') is not True]
            add('private', 'fail' if pub else 'ok', 'agent for a repository not recorded private: %s' % ', '.join(map(str, pub))
                if pub else 'every agent\'s repository is private')
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
    ap.add_argument('--browsers', choices=BROWSERS, default='none', help='add the Chromium system libraries to the pool image')
    ap.add_argument('--repo-path', action='append', default=None,
                    help='a local checkout of an agent repository (workflows checked for CI_RUNS_ON; lockfiles read for the Playwright version); repeatable')
    ap.add_argument('--playwright-version', default=None, help='X.Y.Z; overrides the version found in the lockfiles (chromium only)')
    ap.add_argument('--total-gib', type=float)
    ap.add_argument('--used-gib', type=float)
    ap.add_argument('--cpus', type=float)
    ap.add_argument('--docker-gib', type=float)
    ap.add_argument('--largest-shard-gib', type=float)
    args = ap.parse_args(argv)
    split = lambda s: [x for x in s.split(',') if x]  # noqa: E731
    if args.action == 'detect':
        print(detect(json=True) if args.json else json.dumps(detect(), indent=2))
    elif args.action in ('sizing', 'plan'):
        found = detect()
        found['pool_env'] = read_pool_env(Probe(), args.pool)
        res = measured_sizing(found, args.total_gib, args.used_gib, args.cpus, args.docker_gib, args.largest_shard_gib)
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
                  browsers=args.browsers, playwright_version=args.playwright_version, repo_paths=args.repo_path or [], probe=Probe())
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
