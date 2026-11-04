#!/usr/bin/env python3
"""Machine load for the luismc-delivery load guard (DELIVERYSPEC DL-77, DL-78): total memory use % and CPU use %.

    load.py [--json]        print the current sample and the limits in force (exit 0 under, 1 over, 2 unmeasurable)
    load.py --write         write host-load.json in the machine folder (a scheduled task runs it every 15 s)

Windows: ctypes GlobalMemoryStatusEx and GetSystemTimes. Linux: /proc/meminfo and /proc/stat. macOS: vm_stat with
sysctl hw.memsize, `top -l 2` (loadavg fallback). Standard library only, never psutil.

CPU is the delta of the raw counters between this sample and the previous cached one (never a sleep: a hook must
not wait); with no usable previous sample (none, or older than 10 min) it is the load average per core, and on
Windows without one it is unknown and the guard decides on memory only. The last samples are kept in a small cache file (TTL 10 s, so a burst of hooks
costs one sample); the CPU figure is the mean of the samples of the last 30 s (at most 3), so one spike does not decide.

Limits (project over machine over default): defaults memory 85, CPU 60. The machine file is machine.json in the
machine folder (machine_slots.machine_dir(), DL-90); the old ~/.claude/luismc-delivery-machine.json is read only when
the new file has no load_limits. A project overrides in .delivery/config.json `load_limits`, and may lower a limit
for its own work but never raise the machine limit (D21). This module only measures: it never signals, kills or
reprioritises anything.

Host load (DL-90, G3): a reader in WSL or a container measures only its VM. When host-load.json (written on the host
every 15 s by `--write`) is under 60 s old, readers use its figures; when it is older they use their own and say so
(`sample()['host']` is 'stale'). Inside a container the reader also reads the cgroup v2 figures (memory.current,
memory.max, cpu.stat) and decides on the worse of host and container.

Test seams: DELIVERY_LOAD="mem,cpu" (fixed sample, no cache), DELIVERY_LOAD_CACHE (cache path),
DELIVERY_MACHINE_CONFIG (old machine file path), DELIVERY_MACHINE_DIR (machine folder), DELIVERY_CGROUP_DIR (cgroup
v2 folder, default /sys/fs/cgroup), DELIVERY_IN_CONTAINER=1|0 (force the container check), DELIVERY_PS (a file with
`ps` output for top_processes).
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import machine_slots as MS  # noqa: E402

DEFAULT_LIMITS = {'memory_pct': 85.0, 'cpu_pct': 60.0}
CACHE_TTL = 10.0
HISTORY_WINDOW = 30.0
HISTORY_MAX = 3
RAW_MAX_AGE = 600.0


# --- limits ----------------------------------------------------------------------------------

def machine_file():
    return os.environ.get('DELIVERY_MACHINE_CONFIG') or os.path.join(os.path.expanduser('~'), '.claude',
                                                                     'luismc-delivery-machine.json')


def _read(path):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _pct(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value <= 100:
        return None
    return float(value)


def _machine_limits_layer():
    """The load_limits layer of the machine: machine.json first, the old home-folder file as the fallback."""
    new = MS.read_config_file()
    if isinstance(new, dict) and isinstance(new.get('load_limits'), dict):
        return new
    return _read(machine_file())


def limits(project_cfg=None):
    """{'memory_pct', 'cpu_pct'}: the machine over the defaults, then the project, which can only LOWER a limit
    (a value above the machine limit is ignored). A value outside 1..100 is ignored."""
    out = dict(DEFAULT_LIMITS)
    sect = (_machine_limits_layer() or {}).get('load_limits')
    if isinstance(sect, dict):
        for k in out:
            v = _pct(sect.get(k))
            if v is not None:
                out[k] = v
    proj = project_cfg.get('load_limits') if isinstance(project_cfg, dict) else None
    if isinstance(proj, dict):
        for k in out:
            v = _pct(proj.get(k))
            if v is not None and v <= out[k]:
                out[k] = v
    return out


def legacy_differs():
    """Keys of load_limits on which machine.json and the old home-folder file disagree (the doctor warns). Empty
    when either file is missing."""
    new, old = MS.read_config_file(), _read(machine_file())
    a = new.get('load_limits') if isinstance(new, dict) else None
    b = old.get('load_limits') if isinstance(old, dict) else None
    if not isinstance(a, dict) or not isinstance(b, dict):
        return []
    return sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))


# --- parsers (pure; fixtures in tests) -----------------------------------------------------------

def parse_meminfo(text):
    """Memory use % from /proc/meminfo text: (MemTotal - MemAvailable) / MemTotal."""
    vals = {}
    for line in text.splitlines():
        m = re.match(r'^(\w+):\s+(\d+)', line)
        if m:
            vals[m.group(1)] = int(m.group(2))
    total = vals.get('MemTotal')
    avail = vals.get('MemAvailable', vals.get('MemFree', 0) + vals.get('Buffers', 0) + vals.get('Cached', 0))
    if not total:
        raise ValueError('MemTotal missing')
    return round(100.0 * (total - avail) / total, 1)


def parse_proc_stat(text):
    """(busy, total) jiffies from the first `cpu` line of /proc/stat (idle and iowait count as idle)."""
    for line in text.splitlines():
        if line.startswith('cpu '):
            f = [int(x) for x in line.split()[1:9]]
            f += [0] * (8 - len(f))
            idle = f[3] + f[4]
            total = sum(f)
            return total - idle, total
    raise ValueError('no cpu line')


def cpu_between(a, b):
    """CPU use % between two (busy, total) readings."""
    dt = b[1] - a[1]
    return round(100.0 * (b[0] - a[0]) / dt, 1) if dt > 0 else 0.0


def parse_vm_stat(text, memsize):
    """Memory use % on macOS from `vm_stat` text and `sysctl hw.memsize`: free, inactive and speculative pages are
    available; active, wired and compressed pages are in use."""
    m = re.search(r'page size of (\d+) bytes', text)
    page = int(m.group(1)) if m else 4096

    def pages(name):
        mm = re.search(r'^Pages %s:\s+(\d+)' % re.escape(name), text, re.M)
        return int(mm.group(1)) if mm else 0
    if not memsize:
        raise ValueError('memsize missing')
    avail = (pages('free') + pages('inactive') + pages('speculative')) * page
    return round(max(0.0, 100.0 * (memsize - avail) / memsize), 1)


def parse_top_cpu(text):
    """CPU use % from the last `CPU usage: x% user, y% sys, z% idle` line of macOS `top -l 2`."""
    found = re.findall(r'CPU usage:.*?([\d.]+)% idle', text)
    if not found:
        raise ValueError('no CPU usage line')
    return round(100.0 - float(found[-1]), 1)


def parse_ps(text, n=5):
    """Names of the top n processes by CPU and by memory from `ps -A -o comm=,pcpu=,rss=` text (columns: name with
    possible spaces, then two numbers)."""
    rows = []
    for line in text.splitlines():
        m = re.match(r'^\s*(.+?)\s+([\d.]+)\s+(\d+)\s*$', line)
        if m:
            rows.append((os.path.basename(m.group(1).strip()), float(m.group(2)), int(m.group(3))))
    by_cpu = [r[0] for r in sorted(rows, key=lambda r: -r[1]) if r[1] > 0][:n]
    by_mem = [r[0] for r in sorted(rows, key=lambda r: -r[2])][:n]
    return {'cpu': _dedupe(by_cpu), 'mem': _dedupe(by_mem)}


def parse_powershell_csv(text, n=5):
    """Same shape from `Get-Process | ConvertTo-Csv` (Name, CPU seconds, WorkingSet bytes)."""
    rows = []
    for line in text.splitlines()[1:]:
        parts = [p.strip('"') for p in line.split('","')] if '","' in line else []
        if len(parts) == 3:
            try:
                rows.append((parts[0], float(parts[1] or 0), int(float(parts[2] or 0))))
            except ValueError:
                pass
    by_cpu = [r[0] for r in sorted(rows, key=lambda r: -r[1]) if r[1] > 0][:n]
    by_mem = [r[0] for r in sorted(rows, key=lambda r: -r[2])][:n]
    return {'cpu': _dedupe(by_cpu), 'mem': _dedupe(by_mem)}


def _dedupe(names):
    out = []
    for x in names:
        if x not in out:
            out.append(x)
    return out


# --- measurement ---------------------------------------------------------------------------------

def _run(argv, timeout=10):
    return subprocess.run(argv, capture_output=True, timeout=timeout, text=True, errors='replace').stdout


def _read_text(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def _windows_times():
    import ctypes
    from ctypes import wintypes

    class FT(ctypes.Structure):
        _fields_ = [('lo', wintypes.DWORD), ('hi', wintypes.DWORD)]
    idle, kern, user = FT(), FT(), FT()
    if not ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kern), ctypes.byref(user)):
        raise OSError('GetSystemTimes failed')

    def val(x):
        return (x.hi << 32) | x.lo
    total = val(kern) + val(user)           # kernel time includes idle time
    return total - val(idle), total


def _windows_memory():
    import ctypes
    from ctypes import wintypes

    class MS(ctypes.Structure):
        _fields_ = [('dwLength', wintypes.DWORD), ('dwMemoryLoad', wintypes.DWORD),
                    ('ullTotalPhys', ctypes.c_ulonglong), ('ullAvailPhys', ctypes.c_ulonglong),
                    ('ullTotalPageFile', ctypes.c_ulonglong), ('ullAvailPageFile', ctypes.c_ulonglong),
                    ('ullTotalVirtual', ctypes.c_ulonglong), ('ullAvailVirtual', ctypes.c_ulonglong),
                    ('ullAvailExtendedVirtual', ctypes.c_ulonglong)]
    s = MS()
    s.dwLength = ctypes.sizeof(MS)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(s)):
        raise OSError('GlobalMemoryStatusEx failed')
    return float(s.dwMemoryLoad)


def _loadavg_cpu():
    """CPU use % from the 1-minute load average per core, or None where there is no getloadavg (Windows)."""
    try:
        return min(100.0, round(100.0 * os.getloadavg()[0] / (os.cpu_count() or 1), 1))
    except (AttributeError, OSError):
        return None


def measure_now(prev=None):
    """A fresh {'mem', 'cpu', 'at', 'raw'} sample without waiting. CPU is the delta between the raw (busy, total)
    counters now and those of `prev` ({'raw': [busy, total], 'at': t}, the previous cached sample) when prev is at
    most RAW_MAX_AGE old; else the load average per core; else None (unknown: the guard decides on memory only).
    Raises when this platform cannot be measured."""
    now = time.time()
    raw = None
    if sys.platform.startswith('win'):
        raw = _windows_times()
        mem = _windows_memory()
    elif sys.platform == 'darwin':
        mem = parse_vm_stat(_run(['vm_stat']), int(_run(['sysctl', '-n', 'hw.memsize']).strip()))
    else:
        raw = parse_proc_stat(_read_text('/proc/stat'))
        mem = parse_meminfo(_read_text('/proc/meminfo'))
    cpu = None
    old = prev.get('raw') if isinstance(prev, dict) else None
    if raw and isinstance(old, (list, tuple)) and len(old) == 2 and 0 <= now - prev.get('at', -1e9) <= RAW_MAX_AGE \
            and raw[1] > old[1]:
        cpu = cpu_between(tuple(old), raw)
    if cpu is None:
        cpu = _loadavg_cpu()
    out = {'mem': mem, 'cpu': cpu, 'at': now}
    if raw:
        out['raw'] = list(raw)
    return out


def cache_file():
    """The cache path: per user, in the same ~/.claude directory as the machine file (never the shared temp dir)."""
    return os.environ.get('DELIVERY_LOAD_CACHE') or os.path.join(os.path.dirname(machine_file()),
                                                                 'luismc-delivery-load.json')


def _history():
    data = _read(cache_file())
    hist = data.get('samples') if isinstance(data, dict) else None
    return [s for s in hist if isinstance(s, dict) and isinstance(s.get('at'), (int, float))] \
        if isinstance(hist, list) else []


def read_host_load(now=None):
    """(figures, age_s) of host-load.json: figures {'mem', 'cpu'} or None when the file is missing or unreadable."""
    data = _read(MS.host_load_path())
    if not isinstance(data, dict):
        return None, None
    at = data.get('at')
    mem, cpu = data.get('mem'), data.get('cpu')
    if isinstance(mem, bool) or not isinstance(mem, (int, float)) or not isinstance(at, (int, float)):
        return None, None
    now = time.time() if now is None else now
    out = {'mem': float(mem), 'cpu': float(cpu) if isinstance(cpu, (int, float)) and not isinstance(cpu, bool) else None}
    return out, max(0.0, now - at)


def write_host_load(s=None):
    """Write host-load.json (atomic): memory %, CPU %, time. Returns the dict written."""
    s = s or sample(own_only=True)
    rec = {'mem': s['mem'], 'cpu': s['cpu'], 'at': time.time(), 'written_by': sys.platform}
    folder = MS.machine_dir()
    MS._mkdir(folder)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix='host-load.', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(rec, f)
        if not sys.platform.startswith('win'):
            os.chmod(tmp, 0o644)
        os.replace(tmp, MS.host_load_path())
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return rec


def in_container():
    env = os.environ.get('DELIVERY_IN_CONTAINER')
    if env in ('0', '1'):
        return env == '1'
    return os.path.exists('/.dockerenv') or os.path.exists('/run/.containerenv')


def parse_cpu_stat(text):
    """usage_usec from cgroup v2 cpu.stat text."""
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] == 'usage_usec':
            return int(parts[1])
    raise ValueError('no usage_usec')


def parse_cpu_max(text):
    """CPUs the cgroup may use from cpu.max text ('max 100000' or '200000 100000'); None when uncapped."""
    parts = text.split()
    if len(parts) >= 2 and parts[0] != 'max' and int(parts[1]) > 0:
        return int(parts[0]) / int(parts[1])
    return None


def measure_container(prev=None, now=None):
    """The container's own figures from cgroup v2: {'mem', 'cpu', 'cg'} (any may be None), or None when there is no
    cgroup v2 folder. mem is memory.current over memory.max (None when uncapped); cpu is the usage delta since
    `prev` (its 'cg' entry) over the CPUs the cgroup may use."""
    base = os.environ.get('DELIVERY_CGROUP_DIR') or '/sys/fs/cgroup'
    now = time.time() if now is None else now
    out = {'mem': None, 'cpu': None, 'cg': None}
    try:
        cur = int(_read_text(os.path.join(base, 'memory.current')).strip())
        mx = _read_text(os.path.join(base, 'memory.max')).strip()
        if mx.isdigit() and int(mx) > 0:
            out['mem'] = round(100.0 * cur / int(mx), 1)
    except (OSError, ValueError):
        pass
    try:
        usec = parse_cpu_stat(_read_text(os.path.join(base, 'cpu.stat')))
        out['cg'] = {'usec': usec, 'at': now}
        try:
            cpus = parse_cpu_max(_read_text(os.path.join(base, 'cpu.max'))) or float(os.cpu_count() or 1)
        except (OSError, ValueError):
            cpus = float(os.cpu_count() or 1)
        old = prev.get('cg') if isinstance(prev, dict) else None
        if isinstance(old, dict) and 0 < now - old.get('at', 0) <= RAW_MAX_AGE and usec >= old.get('usec', usec):
            out['cpu'] = min(100.0, round(100.0 * (usec - old['usec']) / 1e6 / (now - old['at']) / cpus, 1))
    except (OSError, ValueError):
        pass
    return out if (out['mem'] is not None or out['cg']) else None


def _combine(own, now):
    """Decide on the worse of the host and the container. The host figures come from host-load.json when it is under
    60 s old, else they are this reader's own. Adds 'host' ('file'|'own'|'stale') and 'container'."""
    out = dict(own)
    host, age = read_host_load(now)
    if host is not None and age <= MS.HOST_LOAD_MAX_AGE:
        out['mem'] = host['mem']
        out['cpu'] = host['cpu'] if host['cpu'] is not None else own['cpu']
        out['host'] = 'file'
    else:
        out['host'] = 'stale' if host is not None else 'own'
    ctr = own.get('container')
    if isinstance(ctr, dict):
        if ctr.get('mem') is not None:
            out['mem'] = max(out['mem'], ctr['mem'])
        if ctr.get('cpu') is not None:
            out['cpu'] = max(out['cpu'], ctr['cpu'])
    return out


def sample(now=None, measure=None, own_only=False):
    """The load the guard decides on: {'mem', 'cpu', 'at', 'cached', 'host'}. Reuses a sample younger than CACHE_TTL;
    else measures, stores it and smooths CPU over the recent samples. Then the host file and the container figures
    are applied (see the module doc); `own_only` and a `measure` seam skip that. Raises when unmeasurable (callers
    fail open)."""
    fixed = os.environ.get('DELIVERY_LOAD')
    if fixed:
        mem, cpu = [float(x) for x in fixed.split(',')[:2]]
        return {'mem': mem, 'cpu': cpu, 'at': time.time(), 'cached': False}
    now = time.time() if now is None else now
    s = _own_sample(now, measure)
    if own_only or measure is not None:
        return s
    return _combine(s, now)


def _own_sample(now, measure=None):
    hist = _history()
    if hist and 0 <= now - hist[-1]['at'] < CACHE_TTL:
        return dict(_smooth(hist, now), cached=True, container=hist[-1].get('container'))
    prev = next((h for h in reversed(hist) if h.get('raw')), None)
    if measure is None:
        def measure():
            s = measure_now(prev)
            if in_container():
                ctr = measure_container(next((h for h in reversed(hist) if h.get('container', {}) and
                                              (h.get('container') or {}).get('cg')), {}).get('container'), now)
                if ctr:
                    s['container'] = ctr
            return s
    s = measure()
    hist = [h for h in hist if 0 <= now - h['at'] <= HISTORY_WINDOW][-(HISTORY_MAX - 1):] + [dict(s, at=now)]
    tmp = None
    try:
        path = cache_file()
        folder = os.path.dirname(path) or '.'
        os.makedirs(folder, mode=0o700, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=folder, prefix='luismc-delivery-load.', suffix='.tmp')
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump({'samples': hist}, f)
        os.replace(tmp, path)
        tmp = None
    except OSError:
        if tmp:
            try:
                os.unlink(tmp)
            except OSError:
                pass
        pass                                   # a cache that cannot be written only costs the next hook a sample
    return dict(_smooth(hist, now), cached=False, container=s.get('container'))


def _smooth(hist, now):
    recent = [h for h in hist if 0 <= now - h['at'] <= HISTORY_WINDOW][-HISTORY_MAX:] or hist[-1:]
    last = recent[-1]
    cpus = [h['cpu'] for h in recent if isinstance(h.get('cpu'), (int, float))]
    cpu = round(sum(cpus) / len(cpus), 1) if cpus else 0.0      # unknown CPU counts as 0: memory decides
    return {'mem': last['mem'], 'cpu': cpu, 'at': last['at']}


def over(s, lim):
    """The list of limits the sample exceeds: [] when under, e.g. ['memory 91% > 85%']."""
    out = []
    if s['mem'] > lim['memory_pct']:
        out.append('memory %s%% > %s%%' % (_n(s['mem']), _n(lim['memory_pct'])))
    if s['cpu'] > lim['cpu_pct']:
        out.append('CPU %s%% > %s%%' % (_n(s['cpu']), _n(lim['cpu_pct'])))
    return out


def _n(x):
    return ('%g' % x) if float(x).is_integer() else '%.1f' % x


def top_processes(n=5):
    """{'cpu': [names], 'mem': [names]} of the heaviest processes (names only); empty lists when unavailable."""
    try:
        fixture = os.environ.get('DELIVERY_PS')
        if fixture:
            return parse_ps(_read_text(fixture), n)
        if sys.platform.startswith('win'):
            cmd = ('Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 40 Name,CPU,WorkingSet64 '
                   '| ConvertTo-Csv -NoTypeInformation')
            return parse_powershell_csv(_run(['powershell', '-NoProfile', '-Command', cmd], timeout=15), n)
        return parse_ps(_run(['ps', '-A', '-o', 'comm=,pcpu=,rss=']), n)
    except Exception:  # noqa: BLE001 - names are a courtesy, never a reason to fail
        return {'cpu': [], 'mem': []}


def main(argv=None):
    args = argv if argv is not None else sys.argv[1:]
    if '--write' in args:
        try:
            rec = write_host_load()
        except Exception as exc:  # noqa: BLE001
            print('load: cannot write host-load.json (%s: %s)' % (type(exc).__name__, exc), file=sys.stderr)
            return 2
        print('host-load.json: memory %s%%, CPU %s%%' % (_n(rec['mem']), _n(rec['cpu'] if rec['cpu'] is not None else 0)))
        return 0
    lim = limits()
    try:
        s = sample()
    except Exception as exc:  # noqa: BLE001
        print('load: cannot measure (%s: %s)' % (type(exc).__name__, exc), file=sys.stderr)
        return 2
    o = over(s, lim)
    if '--json' in args:
        print(json.dumps({'memory_pct': s['mem'], 'cpu_pct': s['cpu'], 'limits': lim, 'over': o}))
    else:
        print('memory %s%% (limit %s%%), CPU %s%% (limit %s%%)%s'
              % (_n(s['mem']), _n(lim['memory_pct']), _n(s['cpu']), _n(lim['cpu_pct']),
                 ': OVER ' + ', '.join(o) if o else ': ok'))
    return 1 if o else 0


if __name__ == '__main__':
    sys.exit(main())
