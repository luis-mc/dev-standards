#!/usr/bin/env python3
"""Shared CI pool and the guided CI setup behind it (DL30, contract: docs/features/delivery/shared-self-hosted-runners.md).

    delivery_runner_pool.py detect  [--json]
    delivery_runner_pool.py sizing  --total-gib N --used-gib N --cpus N [--docker-gib N] [--largest-shard-gib N]
    delivery_runner_pool.py plan    --repos a/b,c/d [--windows-repos e/f] [--pool NAME] [--cpus N] [--mem-gib N]
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
import re
import secrets
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

try:  # agent A's machine layer (DL32); absent on a branch that does not have it yet
    import machine_slots as MS
except Exception:  # noqa: BLE001
    MS = None

LABEL = 'dev.luismc.runner-pool'
TEMPLATES = os.path.join(os.path.dirname(HERE), 'templates', 'runner-pool')
MEM_PCT, CPU_PCT = 85, 60
VM_GIB, SIDECAR_GIB = 1.0, 1.0
RUNNER_VERSION = '2.321.0'
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


# --- detect (read only) -----------------------------------------------------------------------------------------------

def _flatten(data):
    if isinstance(data, list) and data and all(isinstance(x, list) for x in data):
        return [y for x in data for y in x]
    return data if isinstance(data, list) else []


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


def detect_services(probe):
    out = []
    if probe.platform.startswith('win'):
        r = probe.sh(['powershell', '-NoProfile', '-Command',
                      'Get-Service actions.runner.* | Select-Object Name,Status | ConvertTo-Json'])
        if r and r[0] == 0 and r[1].strip():
            try:
                data = json.loads(r[1])
            except ValueError:
                data = []
            for x in [data] if isinstance(data, dict) else data:
                out.append({'name': x.get('Name'), 'status': str(x.get('Status')), 'kind': 'windows-service'})
    else:
        r = probe.sh(['systemctl', 'list-units', 'actions.runner.*', '--all', '--no-legend', '--plain'])
        for line in (r[1] if r and r[0] == 0 else '').splitlines():
            parts = line.split()
            if parts:
                out.append({'name': parts[0], 'status': parts[3] if len(parts) > 3 else '', 'kind': 'systemd'})
    return out


def detect_folders(probe):
    """Runner folders, found by their `.runner` file. `.credentials` is never opened."""
    out = []
    for base in probe.runner_dirs:
        for d in [base] + [base.rstrip('/') + '/' + n for n in probe.listdir(base)]:
            text = probe.read_text(d + '/.runner') if probe.isfile(d + '/.runner') else None
            if text is None:
                continue
            try:
                j = json.loads(text)
            except ValueError:
                j = {}
            url = j.get('gitHubUrl') or ''
            out.append({'path': d, 'agent_id': j.get('agentId'), 'name': j.get('agentName'),
                        'repo': url.replace('https://github.com/', '') or None})
    return out


def detect_containers(probe):
    out, seen = [], set()
    for argv, how in ((['docker', 'ps', '-a', '--filter', 'label=' + LABEL, '--format', '{{.ID}}\t{{.Names}}\t{{.Status}}'], 'label'),
                      (['docker', 'ps', '-a', '--format', '{{.ID}}\t{{.Names}}\t{{.Command}}'], 'command')):
        r = probe.sh(argv)
        for line in (r[1] if r and r[0] == 0 else '').splitlines():
            cols = line.split('\t')
            if len(cols) < 3 or cols[0] in seen:
                continue
            if how == 'command' and 'Runner.Listener' not in cols[2]:
                continue
            seen.add(cols[0])
            out.append({'id': cols[0], 'name': cols[1], 'detail': cols[2], 'found_by': how, 'pool': how == 'label'})
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


def detect(probe=None, json=False):
    """What exists, read only. `json=True` returns the same facts as a JSON string (contract 12.3)."""
    probe = probe or Probe()
    found = {'github': detect_github(probe), 'services': detect_services(probe), 'folders': detect_folders(probe),
             'containers': detect_containers(probe), 'wsl': detect_wsl(probe)}
    if json:
        import json as _json
        return _json.dumps(found, indent=2)
    return found


# --- sizing (section 6.4) ---------------------------------------------------------------------------------------------

def sizing(total_gib, used_gib, cpus, docker_gib=None, largest_shard_gib=None, sidecar_gib=SIDECAR_GIB, vm_gib=VM_GIB):
    """Pool cap = the smaller of the memory room and Docker's ceiling, minus the sidecar and the VM. CPU = 60% of the CPUs."""
    room = total_gib * MEM_PCT / 100.0 - used_gib
    ceiling = room if docker_gib is None else min(room, docker_gib)
    mem = math.floor((ceiling - sidecar_gib - vm_gib) * 2) / 2.0
    cpu = max(1.0, math.floor(cpus * CPU_PCT / 100.0 * 2) / 2.0)
    out = {'mem_gib': mem, 'cpus': cpu, 'memory_room_gib': round(room, 1), 'ok': True, 'message': '',
           'wsl': {'memory': int(math.ceil(mem + sidecar_gib + vm_gib)), 'processors': int(math.ceil(cpu))}}
    if mem <= 0:
        out.update(ok=False, message='No memory is left for the pool (room %.1f GiB). Close other programs or raise the '
                                     'WSL memory in .wslconfig, then run the setup again.' % room)
    elif largest_shard_gib is not None and mem < largest_shard_gib:
        out.update(ok=False, message='The pool cap (%.1f GiB) is below the largest Linux shard (%.1f GiB). Lower that '
                                     'shard\'s memory_gib in ci-shards.json, or free memory on this machine.'
                                     % (mem, largest_shard_gib))
    return out


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


def plan(found, linux_repos, windows_repos=(), pool='main', cap=None, serial=None, limits=None):
    """The steps, in the order of contract 6.3. A public repository gets no step; it is listed in `refused`.

    A runner that already belongs to this pool is kept and its steps say `already` (safe to run again)."""
    private = {r['repo']: r['private'] for r in found['github']['repos']}
    refused, keep_l, keep_w = [], [], []
    for repo in list(linux_repos) + list(windows_repos):
        if private.get(repo) is not True:
            why = PRIVATE_REFUSAL % repo if repo in private else 'refused: %s is not a repository you administer' % repo
            refused.append({'repo': repo, 'reason': why})
    bad = {x['repo'] for x in refused}
    keep_l = [r for r in linux_repos if r not in bad]
    keep_w = [r for r in windows_repos if r not in bad]
    steps = [_step('idle', 'Wait until no existing runner has a job', 'wait-idle')]
    for r in found['github']['repos']:
        for x in r['runners']:
            if 'pool-%s' % pool in x['labels']:
                continue  # already part of this pool: kept
            steps.append(_step('remove:%s:%s' % (r['repo'], x['name']),
                               'Remove runner %s (%s) from %s' % (x['name'], x['os'], r['repo']), 'remove-runner',
                               repo=r['repo'], runner_id=x['id'], runner=x['name']))
    for f in found['folders']:
        steps.append(_step('delete-folder:%s' % f['path'], 'Delete the old runner folder %s' % f['path'], 'delete-folder',
                           delete=True, names=[f['path']], path=f['path']))
    for c in found['containers']:
        steps.append(_step('delete-container:%s' % c['name'], 'Stop and delete the container %s' % c['name'],
                           'delete-container', delete=True, names=['container ' + c['name']], container=c['name']))
    steps.append(_step('machine-config', 'Write the machine config (limits, slots) through the machine layer', 'machine-config',
                       limits=limits or {}))
    steps.append(_step('host-load-task', 'Register the scheduled task that writes the host load file every 15 seconds',
                       'host-load-task', elevated=True,
                       printed=['schtasks /Create /SC MINUTE /MO 1 /TN luismc-host-load /TR "python load.py --write" /RU SYSTEM']))
    if keep_l:
        if found['wsl'].get('exists') is False or found['wsl'].get('memory') is None:
            steps.append(_step('wslconfig', 'Write %s with the pool ceiling' % found['wsl'].get('file'), 'wslconfig',
                               cap=cap, shutdown=False))
        steps.append(_step('pool-files', 'Write the pool files for "%s" (compose, agents.json, .env with the cap only)' % pool,
                           'pool-files', pool=pool, cap=cap))
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
                                    'Set ACTIONS_RUNNER_HOOK_JOB_STARTED and ACTIONS_RUNNER_HOOK_JOB_COMPLETED in C:/actions-runners/%s/.env' % slug]))
    for repo in keep_l:
        value = json.dumps(['self-hosted', 'linux', 'pool-%s' % pool])
        steps.append(_step('var:CI_RUNS_ON:%s' % repo, 'Set CI_RUNS_ON for %s' % repo, 'set-variable', repo=repo,
                           name='CI_RUNS_ON', value=value))
        if serial is not None:
            steps.append(_step('var:CI_SERIAL:%s' % repo, 'Set CI_SERIAL for %s' % repo, 'set-variable', repo=repo,
                               name='CI_SERIAL', value='true' if serial else 'false'))
    steps.append(_step('verify', 'Verify: each agent online with its labels, then one pool-check run per repository', 'verify',
                       repos=keep_l, pool=pool))
    n_run = sum(1 for s in steps if s['state'] == 'todo')
    return {'pool': pool, 'steps': steps, 'refused': refused, 'cap': cap,
            'minutes': 5 + 3 * n_run, 'needs': ['a yes for each step', 'a yes that names what is deleted']
            + (['an administrator shell for: ' + ', '.join(s['id'] for s in steps if s['elevated'])]
               if any(s['elevated'] for s in steps) else [])}


# --- run (steps 6.3) --------------------------------------------------------------------------------------------------

def runner_sha(probe, version=RUNNER_VERSION):
    """SHA-256 of the Linux runner tarball from the release (asset digest, else the release notes)."""
    data, _why = probe.gh_json(['api', 'repos/actions/runner/releases/tags/v%s' % version])
    if not isinstance(data, dict):
        return None
    name = 'actions-runner-linux-x64-%s.tar.gz' % version
    for a in data.get('assets', []):
        d = a.get('digest') or ''
        if a.get('name') == name and d.startswith('sha256:'):
            return d[7:]
    m = re.search(r'%s[^0-9a-f]{0,40}([0-9a-f]{64})' % re.escape(name), data.get('body') or '')
    return m.group(1) if m else None


def pool_dir(pool):
    base = MS.machine_dir() if MS else os.environ.get('DELIVERY_MACHINE_DIR', '/etc/luismc-delivery')
    return os.path.join(str(base), 'pools', pool)


def write_pool_files(pool, cap, dest=None, copy_from=None):
    """Write the pool folder. `.env` holds the cap and the machine dir only (D42); the database password is a 0600 file."""
    dest = dest or pool_dir(pool)
    os.makedirs(dest, exist_ok=True)
    for name in os.listdir(TEMPLATES):
        src = os.path.join(TEMPLATES, name)
        if os.path.isfile(src) and name != 'pool-check.yml':
            shutil.copy2(src, os.path.join(dest, name))
    shutil.copytree(os.path.join(TEMPLATES, 'hooks'), os.path.join(dest, 'hooks'), dirs_exist_ok=True)
    deliv = os.path.join(dest, 'delivery')
    os.makedirs(deliv, exist_ok=True)
    for name in ('runner_load_gate.py', 'runner_job_done.py', 'load.py', 'machine_slots.py'):
        src = os.path.join(copy_from or HERE, name)
        if os.path.isfile(src):
            shutil.copy2(src, deliv)
    with open(os.path.join(dest, '.env'), 'w', encoding='utf-8') as f:
        f.write('POOL_NAME=%s\nPOOL_CPUS=%s\nPOOL_MEM=%sg\nMACHINE_DIR=%s\n' % (
            pool, (cap or {}).get('cpus', 1), (cap or {}).get('mem_gib', 4), os.path.dirname(os.path.dirname(dest))))
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
        r = self.probe.sh(['docker', 'rm', '-f', step['container']])
        return (bool(r and r[0] == 0), 'container deleted' if r and r[0] == 0 else 'docker refused')

    def do_machine_config(self, step):
        if MS is None or not hasattr(MS, 'write_machine_config'):
            return False, 'the machine layer (machine_slots.write_machine_config) is not in this plugin yet'
        cfg = dict(MS.machine_config())
        cfg.update(step.get('limits') or {})
        MS.write_machine_config(cfg)
        return True, 'machine config written through machine_slots'

    def do_wslconfig(self, step):
        cap = step.get('cap') or {}
        w = cap.get('wsl') or {}
        with open(self.probe.wslconfig, 'a', encoding='utf-8') as f:
            f.write('\n[wsl2]\nmemory=%sGB\nprocessors=%s\n' % (w.get('memory', 8), w.get('processors', 2)))
        return True, 'written. `wsl --shutdown` stops every container; run it yourself when no job runs.'

    def do_pool_files(self, step):
        return True, 'wrote ' + write_pool_files(step['pool'], step.get('cap'))

    def do_pool_up(self, step):
        sha = runner_sha(self.probe)
        if not sha:
            return False, 'could not read the SHA-256 of the runner release; the image is not built without it'
        env = dict(os.environ, RUNNER_SHA256=sha)
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
        return (bool(r and r[0] == 0), '%s set' % step['name'] if r and r[0] == 0 else 'gh refused')

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
    check = check or (lambda step: False)
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
            ok, detail = (bool(check(step)), 'checked')
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
    ap.add_argument('--total-gib', type=float)
    ap.add_argument('--used-gib', type=float, default=0.0)
    ap.add_argument('--cpus', type=float)
    ap.add_argument('--docker-gib', type=float)
    ap.add_argument('--largest-shard-gib', type=float)
    args = ap.parse_args(argv)
    split = lambda s: [x for x in s.split(',') if x]  # noqa: E731
    if args.action == 'detect':
        print(detect(json=True) if args.json else json.dumps(detect(), indent=2))
    elif args.action == 'sizing':
        if args.total_gib is None or args.cpus is None:
            print('sizing needs --total-gib and --cpus', file=sys.stderr)
            return 1
        res = sizing(args.total_gib, args.used_gib, args.cpus, args.docker_gib, args.largest_shard_gib)
        print(json.dumps(res, indent=2))
        return 0 if res['ok'] else 1
    elif args.action == 'plan':
        found = detect()
        cap = sizing(args.total_gib, args.used_gib, args.cpus, args.docker_gib, args.largest_shard_gib) if args.total_gib else None
        print(json.dumps(plan(found, split(args.repos), split(args.windows_repos), args.pool, cap), indent=2))
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
