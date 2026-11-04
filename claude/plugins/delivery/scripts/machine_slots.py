#!/usr/bin/env python3
"""Machine layer for shared CI (DELIVERYSPEC DL-79, DL-90): machine config, CI slots, queue tickets, slot log.

One folder per machine (`machine_dir()`), readable and writable by every runner account:

    machine.json        the limits (section 3.1 of the shared-runners design)
    slots/slot-N.lock   one file per busy CI slot, created create-new (atomic), so two hooks never take one slot
    queue/<ticket>.json one ticket per job that waits; the name sorts in the order of service
    slot-log.jsonl      one JSON line per take and per free, trimmed to the last 5000 lines
    host-load.json      memory and CPU of the host, written every 15 s (load.py --write)

Order of service (D30): a ready pull request's run and a run on the default branch first (priority 0), every other
run next (priority 1); inside a group, first come, first served. The priority is read from the event file the runner
gives every job (`GITHUB_EVENT_PATH`).

Stale slots (D25): a holder process that is gone (same host only) frees its slot at once; any slot older than
`slot_stale_min` is freed. Every freed slot is logged with what held it.

Standard library only. This module never kills or signals a process: it only reads whether one is alive.
"""
import json
import os
import socket
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone

DEFAULT_CONFIG = {
    'load_limits': {'memory_pct': 85, 'cpu_pct': 60},
    'ci_slots': 2,
    'local_heavy': 2,
    'cloud_ci_sessions': 10,
    'slot_stale_min': 120,
    'runner_gate': {'max_wait_min': 30, 'poll_sec': 15},
    'runner_dirs': [],
}
CONFIG_KEYS = tuple(DEFAULT_CONFIG)
LOG_MAX_LINES = 5000
LOG_LOCK_STALE = 30.0
LOG_LOCK_WAIT = 10.0
HOST_LOAD_MAX_AGE = 60.0


# --- paths -------------------------------------------------------------------------------------

def machine_dir():
    """The machine folder: DELIVERY_MACHINE_DIR (tests, and /machine in the pool), else ProgramData\\luismc-delivery on
    Windows (PROGRAMDATA env var), else /etc/luismc-delivery."""
    env = os.environ.get('DELIVERY_MACHINE_DIR')
    if env:
        return env
    if sys.platform.startswith('win'):
        return os.path.join(os.environ.get('PROGRAMDATA') or 'C:\\ProgramData', 'luismc-delivery')
    return '/etc/luismc-delivery'


def config_path():
    return os.path.join(machine_dir(), 'machine.json')


def slots_dir():
    return os.path.join(machine_dir(), 'slots')


def queue_dir():
    return os.path.join(machine_dir(), 'queue')


def log_path():
    return os.path.join(machine_dir(), 'slot-log.jsonl')


def host_load_path():
    return os.path.join(machine_dir(), 'host-load.json')


def _mkdir(path):
    """Create a folder every runner account can write to (best effort: the setup grants the rights)."""
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        return False
    if not sys.platform.startswith('win'):
        try:
            os.chmod(path, 0o777)
        except OSError:
            pass
    return True


# --- config ------------------------------------------------------------------------------------

def _num(value, lo=0, hi=None, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value < lo or (hi is not None and value > hi):
        return None
    return int(value) if integer else value


def normalise_config(raw):
    """DEFAULT_CONFIG with every valid key of `raw` applied. A bad value is dropped (the default stays)."""
    out = json.loads(json.dumps(DEFAULT_CONFIG))
    if not isinstance(raw, dict):
        return out
    ll = raw.get('load_limits')
    if isinstance(ll, dict):
        for k in ('memory_pct', 'cpu_pct'):
            v = ll.get(k)
            if _num(v, 0, 100) and v > 0:
                out['load_limits'][k] = v
    for k, lo in (('ci_slots', 1), ('local_heavy', 1), ('cloud_ci_sessions', 1), ('slot_stale_min', 1)):
        v = _num(raw.get(k), lo, integer=True)
        if v is not None and raw.get(k) == v:
            out[k] = v
    rg = raw.get('runner_gate')
    if isinstance(rg, dict):
        for k in ('max_wait_min', 'poll_sec'):
            v = _num(rg.get(k), 0)
            if v is not None:
                out['runner_gate'][k] = v
        if rg.get('on_timeout') in ('fail', 'run'):
            out['runner_gate']['on_timeout'] = rg['on_timeout']
    rd = raw.get('runner_dirs')
    if isinstance(rd, list):
        out['runner_dirs'] = [x for x in rd if isinstance(x, str) and x]
    return out


def read_config_file():
    """The parsed machine.json, or None when it is missing or unreadable."""
    try:
        with open(config_path(), encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def machine_config():
    """The machine config with defaults for every missing or bad key."""
    return normalise_config(read_config_file())


def write_machine_config(cfg):
    """Write machine.json (atomic) and create the slot and queue folders. Returns the config as written. Raises
    ValueError for a key that is not part of the config, OSError when the folder cannot be written."""
    if not isinstance(cfg, dict):
        raise ValueError('machine config must be an object')
    unknown = sorted(set(cfg) - set(CONFIG_KEYS))
    if unknown:
        raise ValueError('unknown machine config key(s): ' + ', '.join(unknown))
    merged = normalise_config(cfg)
    folder = machine_dir()
    if not (_mkdir(folder) and _mkdir(slots_dir()) and _mkdir(queue_dir())):
        raise OSError('cannot create %s' % folder)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix='machine.', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as f:
            json.dump(merged, f, indent=2)
            f.write('\n')
        if not sys.platform.startswith('win'):
            os.chmod(tmp, 0o644)
        os.replace(tmp, config_path())
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return merged


# --- who is who --------------------------------------------------------------------------------

def _iso(t=None):
    return datetime.fromtimestamp(time.time() if t is None else t, timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _parse_iso(text):
    try:
        return datetime.strptime(text, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc).timestamp()
    except (TypeError, ValueError):
        return None


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def ident_from_env(env=None):
    """What identifies a job, from the environment the runner gives every hook."""
    env = os.environ if env is None else env
    return {'repo': env.get('GITHUB_REPOSITORY') or '', 'run_id': _int(env.get('GITHUB_RUN_ID')),
            'run_attempt': _int(env.get('GITHUB_RUN_ATTEMPT')) or 1, 'job': env.get('GITHUB_JOB') or '',
            'shard': env.get('DELIVERY_SHARD') or '', 'runner': env.get('RUNNER_NAME') or socket.gethostname()}


def priority_from_event(env=None):
    """0 for a ready (not draft) pull request or a run on the default branch, else 1 (D30)."""
    env = os.environ if env is None else env
    path = env.get('GITHUB_EVENT_PATH')
    event = {}
    if path:
        try:
            with open(path, encoding='utf-8') as f:
                event = json.load(f)
        except (OSError, ValueError):
            event = {}
    if not isinstance(event, dict):
        event = {}
    pr = event.get('pull_request')
    if isinstance(pr, dict):
        return 1 if pr.get('draft') else 0
    ref = env.get('GITHUB_REF') or ''
    repo = event.get('repository') if isinstance(event.get('repository'), dict) else {}
    default = repo.get('default_branch')
    if default and ref == 'refs/heads/%s' % default:
        return 0
    return 1


def holder_pid():
    """The process whose death means the job is gone: DELIVERY_HOLDER_PID, else the parent of the hook (the runner's
    worker). On Windows a shell between them (cmd, powershell) is skipped."""
    env = _int(os.environ.get('DELIVERY_HOLDER_PID'))
    if env:
        return env
    parent = os.getppid()
    if sys.platform.startswith('win'):
        try:
            up = _windows_parent(parent)
            if up and up[1].lower() in ('cmd.exe', 'powershell.exe', 'pwsh.exe'):
                return up[0] or parent
        except Exception:  # noqa: BLE001
            pass
    return parent


def _windows_parent(pid):
    """(parent pid, parent's image name) of a process, through a toolhelp snapshot; None when not found."""
    import ctypes
    from ctypes import wintypes

    class PE(ctypes.Structure):
        _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD), ('th32ProcessID', wintypes.DWORD),
                    ('th32DefaultHeapID', ctypes.c_size_t), ('th32ModuleID', wintypes.DWORD),
                    ('cntThreads', wintypes.DWORD), ('th32ParentProcessID', wintypes.DWORD),
                    ('pcPriClassBase', ctypes.c_long), ('dwFlags', wintypes.DWORD), ('szExeFile', ctypes.c_char * 260)]
    k = ctypes.windll.kernel32
    snap = k.CreateToolhelp32Snapshot(2, 0)
    rows = {}
    pe = PE()
    pe.dwSize = ctypes.sizeof(PE)
    ok = k.Process32First(snap, ctypes.byref(pe))
    while ok:
        rows[pe.th32ProcessID] = (pe.th32ParentProcessID, pe.szExeFile.decode('mbcs', 'replace'))
        ok = k.Process32Next(snap, ctypes.byref(pe))
    k.CloseHandle(snap)
    row = rows.get(pid)
    if not row:
        return None
    return row[0], (rows.get(row[0]) or (0, ''))[1]


def pid_alive(pid):
    """True when a process with this pid exists. Unknown pids (0, None) count as alive: never free on a guess."""
    if not isinstance(pid, int) or pid <= 0:
        return True
    if sys.platform.startswith('win'):
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, pid)           # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return ctypes.GetLastError() == 5            # access denied: it exists
        code = ctypes.c_ulong()
        k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return code.value == 259                         # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return True
    return True


def _holder_gone(rec):
    """True when the record's holder process is dead. Only judged for a holder on this host."""
    host = rec.get('host')
    return bool(host) and host == socket.gethostname() and not pid_alive(rec.get('pid'))


# --- small file helpers -----------------------------------------------------------------------

def _read_json(path):
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _write_tmp(folder, rec, prefix):
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=prefix, suffix='.tmp')
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump(rec, f, sort_keys=True)
    if not sys.platform.startswith('win'):
        try:
            os.chmod(tmp, 0o666)
        except OSError:
            pass
    return tmp


def _create_new(path, rec):
    """Create `path` holding `rec`, only if it does not exist. The content is complete the moment the file exists
    (hard link of a finished temp file); where links are refused the file is created with O_EXCL instead."""
    folder = os.path.dirname(path)
    tmp = _write_tmp(folder, rec, '.new-')
    try:
        try:
            os.link(tmp, path)
            return True
        except FileExistsError:
            return False
        except OSError:
            pass
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return False
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(rec, f, sort_keys=True)
        return True
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


# --- the slot log ------------------------------------------------------------------------------

def _log_lock(path):
    return path + '.lock'


def _acquire_log_lock(path):
    lock = _log_lock(path)
    deadline = time.time() + LOG_LOCK_WAIT
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            return True
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(lock) > LOG_LOCK_STALE:
                    os.unlink(lock)
                    continue
            except OSError:
                pass
            if time.time() > deadline:
                return False
            time.sleep(0.01)
        except OSError:
            return False


def write_log(entry, max_lines=None):
    """Append one JSON line to the slot log and trim the file to the last `max_lines` (5000). Never raises: a log
    that cannot be written must not hold a job."""
    path = log_path()
    limit = max_lines or LOG_MAX_LINES
    try:
        _mkdir(os.path.dirname(path))
        if not _acquire_log_lock(path):
            return False
        try:
            line = json.dumps(entry, sort_keys=True) + '\n'
            with open(path, 'a', encoding='utf-8', newline='\n') as f:
                f.write(line)
            try:
                with open(path, encoding='utf-8') as f:
                    lines = f.readlines()
                if len(lines) > limit:
                    keep = lines[-limit:]
                    tmp = path + '.tmp'
                    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
                        f.writelines(keep)
                    os.replace(tmp, path)
            except OSError:
                pass
            if not sys.platform.startswith('win'):
                try:
                    os.chmod(path, 0o666)
                except OSError:
                    pass
        finally:
            try:
                os.unlink(_log_lock(path))
            except OSError:
                pass
        return True
    except OSError:
        return False


def read_log(limit=None):
    """The slot log as a list of dicts (bad lines skipped), oldest first."""
    out = []
    try:
        with open(log_path(), encoding='utf-8') as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if isinstance(rec, dict):
                    out.append(rec)
    except OSError:
        return []
    return out[-limit:] if limit else out


def _log_entry(ident, **fields):
    keys = ('repo', 'run_id', 'run_attempt', 'job', 'shard')
    entry = {k: ident.get(k) for k in keys}
    entry.update({k: v for k, v in fields.items() if v is not None})
    entry.setdefault('runner', ident.get('runner'))
    return entry


# --- queue tickets -----------------------------------------------------------------------------

def enqueue(ident, priority=None, now=None):
    """Write a ticket in queue/. Returns the ticket dict (with its `file` and `queued_at`). The name is
    <priority>-<time in ns>-<random>, so a sorted listing is the order of service (D30)."""
    _mkdir(queue_dir())
    now = time.time() if now is None else now
    prio = priority_from_event() if priority is None else priority
    name = '%d-%019d-%s.json' % (prio, int(now * 1e9), uuid.uuid4().hex[:8])
    rec = dict(ident, priority=prio, queued_at=_iso(now), queued_ts=now, pid=holder_pid(), host=socket.gethostname(),
               gate_pid=os.getpid(), file=name)
    if not _create_new(os.path.join(queue_dir(), name), rec):
        raise OSError('cannot write ticket %s' % name)
    return rec


def dequeue(ticket):
    try:
        os.unlink(os.path.join(queue_dir(), ticket['file']))
    except (OSError, KeyError, TypeError):
        pass


def queue_list(cfg=None, now=None, prune=True):
    """The live tickets in order of service. A ticket whose gate process is gone, or older than slot_stale_min, is
    dropped (when prune is true)."""
    cfg = cfg or machine_config()
    now = time.time() if now is None else now
    out = []
    try:
        names = sorted(n for n in os.listdir(queue_dir()) if n.endswith('.json') and not n.startswith('.'))
    except OSError:
        return []
    for name in names:
        path = os.path.join(queue_dir(), name)
        rec = _read_json(path)
        if rec is None:
            continue
        rec['file'] = name
        age = now - (rec.get('queued_ts') or now)
        dead = (rec.get('host') == socket.gethostname() and not pid_alive(rec.get('gate_pid')))
        if dead or age > cfg['slot_stale_min'] * 60:
            if prune:
                try:
                    os.unlink(path)
                except OSError:
                    pass
            continue
        out.append(rec)
    return out


def is_first(ticket, cfg=None, now=None):
    q = queue_list(cfg, now)
    return bool(q) and q[0].get('file') == ticket.get('file')


# --- slots -------------------------------------------------------------------------------------

def slot_path(n):
    return os.path.join(slots_dir(), 'slot-%d.lock' % n)


def read_slots(cfg=None):
    """[{'slot': n, 'holder': dict|None}] for slots 1..ci_slots. A lock with unreadable content has holder {}."""
    cfg = cfg or machine_config()
    out = []
    for n in range(1, cfg['ci_slots'] + 1):
        p = slot_path(n)
        if os.path.exists(p):
            rec = _read_json(p)
            if rec is None:
                try:
                    rec = {'taken_ts': os.path.getmtime(p)}
                except OSError:
                    rec = None
            out.append({'slot': n, 'holder': rec})
        else:
            out.append({'slot': n, 'holder': None})
    return out


def free_count(cfg=None):
    return sum(1 for s in read_slots(cfg) if s['holder'] is None)


def take_slot(ident, cfg=None, queued_ts=None, now=None):
    """Try to take a free slot. Returns the lock record (with `slot` and `token`) or None when every slot is busy.
    Creating the lock file is atomic, so two callers never get the same slot. Writes the take line of the log."""
    cfg = cfg or machine_config()
    _mkdir(slots_dir())
    now = time.time() if now is None else now
    for n in range(1, cfg['ci_slots'] + 1):
        rec = dict(ident, slot=n, token=uuid.uuid4().hex, pid=holder_pid(), host=socket.gethostname(),
                   taken_at=_iso(now), taken_ts=now)
        if _create_new(slot_path(n), rec):
            write_log(_log_entry(ident, queued_at=_iso(queued_ts if queued_ts else now), slot_at=_iso(now), slot=n))
            return rec
    return None


def _remove_if_token(path, token):
    """Delete a lock only when it still holds `token`. The file is renamed away first, so a lock that was freed and
    taken again in between is put back instead of deleted."""
    side = '%s.free-%s' % (path, uuid.uuid4().hex[:8])
    try:
        os.rename(path, side)
    except OSError:
        return False
    rec = _read_json(side)
    ok = token is None or (rec or {}).get('token') == token
    if ok:
        try:
            os.unlink(side)
        except OSError:
            pass
        return True
    try:
        os.link(side, path)
    except OSError:
        pass
    try:
        os.unlink(side)
    except OSError:
        pass
    return False


def free_slot(lock, outcome='ran', now=None):
    """Free the slot named by a lock record from take_slot or read_slots. Writes the released line. Returns True
    when this call freed it."""
    now = time.time() if now is None else now
    if not isinstance(lock, dict) or not lock.get('slot'):
        return False
    if not _remove_if_token(slot_path(lock['slot']), lock.get('token')):
        return False
    write_log(_log_entry(lock, slot=lock['slot'], slot_at=lock.get('taken_at'), released_at=_iso(now),
                         outcome=outcome))
    return True


def find_held(ident, cfg=None):
    """The locks held by this job (matched on repo, run, attempt and job; the runner name too when both have one)."""
    out = []
    for s in read_slots(cfg):
        h = s['holder']
        if not h or h.get('repo') != ident.get('repo') or h.get('run_id') != ident.get('run_id'):
            continue
        if h.get('job') != ident.get('job') or (h.get('run_attempt') or 1) != (ident.get('run_attempt') or 1):
            continue
        out.append(dict(h, slot=s['slot']))
    return out


def free_stale(cfg=None, now=None):
    """Free every stale slot: a holder process that is gone (same host) at once, any slot older than slot_stale_min.
    Returns [{'slot', 'reason', 'holder'}] of what this call freed."""
    cfg = cfg or machine_config()
    now = time.time() if now is None else now
    freed = []
    for s in read_slots(cfg):
        h = s['holder']
        if h is None:
            continue
        reason = None
        if _holder_gone(h):
            reason = 'holder process gone'
        elif now - (h.get('taken_ts') or now) > cfg['slot_stale_min'] * 60:
            reason = 'older than %d min' % cfg['slot_stale_min']
        if not reason:
            continue
        lock = dict(h, slot=s['slot'])
        if h.get('token'):
            ok = free_slot(lock, 'stale-freed', now)
        else:                                             # a lock with no readable content: no token to check
            ok = _remove_if_token(slot_path(s['slot']), None)
            if ok:
                write_log(_log_entry(lock, slot=s['slot'], released_at=_iso(now), outcome='stale-freed'))
        if ok:
            freed.append({'slot': s['slot'], 'reason': reason, 'holder': h})
    return freed


# --- status ------------------------------------------------------------------------------------

def status(cfg=None, now=None):
    """{'slots': [...], 'queue': [...]} with ages in seconds, for `delivery_ci.py slots` and the doctor."""
    cfg = cfg or machine_config()
    now = time.time() if now is None else now
    slots = []
    for s in read_slots(cfg):
        h = s['holder']
        item = {'slot': s['slot'], 'free': h is None}
        if h is not None:
            item.update(repo=h.get('repo'), run_id=h.get('run_id'), job=h.get('job'), shard=h.get('shard'),
                        runner=h.get('runner'), pid=h.get('pid'),
                        age_s=round(now - (h.get('taken_ts') or now)),
                        stale=_holder_gone(h) or now - (h.get('taken_ts') or now) > cfg['slot_stale_min'] * 60)
        slots.append(item)
    queue = []
    for t in queue_list(cfg, now, prune=False):
        queue.append({'repo': t.get('repo'), 'run_id': t.get('run_id'), 'job': t.get('job'), 'shard': t.get('shard'),
                      'priority': t.get('priority'), 'wait_s': round(now - (t.get('queued_ts') or now))})
    return {'slots': slots, 'queue': queue}


def main(argv=None):
    args = argv if argv is not None else sys.argv[1:]
    if args[:1] == ['status']:
        print(json.dumps(status()))
        return 0
    if args[:1] == ['free-stale']:
        print(json.dumps([{'slot': f['slot'], 'reason': f['reason']} for f in free_stale()]))
        return 0
    print('usage: machine_slots.py status | free-stale', file=sys.stderr)
    return 2


if __name__ == '__main__':
    sys.exit(main())
