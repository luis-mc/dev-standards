#!/usr/bin/env python3
"""Machine load for the luismc-delivery load guard (DELIVERYSPEC DL-77, DL-78): total memory use % and CPU use %.

    load.py [--json]        print the current sample and the limits in force (exit 0 under, 1 over, 2 unmeasurable)

Windows: ctypes GlobalMemoryStatusEx and GetSystemTimes. Linux: /proc/meminfo and /proc/stat. macOS: vm_stat with
sysctl hw.memsize, `top -l 2` (loadavg fallback). Standard library only, never psutil.

CPU is the delta of the raw counters between this sample and the previous cached one (never a sleep: a hook must
not wait); with no usable previous sample (none, or older than 10 min) it is the load average per core, and on
Windows without one it is unknown and the guard decides on memory only. The last samples are kept in a small cache file (TTL 10 s, so a burst of hooks
costs one sample); the CPU figure is the mean of the samples of the last 30 s (at most 3), so one spike does not decide.

Limits (project over machine over default): defaults memory 85, CPU 60; the machine file is
~/.claude/luismc-delivery-machine.json {"load_limits": {"memory_pct": 85, "cpu_pct": 60}}; a project overrides in
.delivery/config.json `load_limits`. This module only measures: it never signals, kills or reprioritises anything.

Test seams: DELIVERY_LOAD="mem,cpu" (fixed sample, no cache), DELIVERY_LOAD_CACHE (cache path),
DELIVERY_MACHINE_CONFIG (machine file path), DELIVERY_PS (a file with `ps` output for top_processes).
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time

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


def limits(project_cfg=None):
    """{'memory_pct', 'cpu_pct'}: project config over the machine file over the defaults. A value outside 1..100 is
    ignored (the next layer applies)."""
    out = dict(DEFAULT_LIMITS)
    layers = [_read(machine_file()), project_cfg]
    for layer in layers:
        sect = layer.get('load_limits') if isinstance(layer, dict) else None
        if isinstance(sect, dict):
            for k in out:
                v = _pct(sect.get(k))
                if v is not None:
                    out[k] = v
    return out


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


def sample(now=None, measure=None):
    """The load the guard decides on: {'mem', 'cpu', 'at', 'cached'}. Reuses a sample younger than CACHE_TTL; else
    measures, stores it and smooths CPU over the recent samples. Raises when unmeasurable (callers fail open)."""
    fixed = os.environ.get('DELIVERY_LOAD')
    if fixed:
        mem, cpu = [float(x) for x in fixed.split(',')[:2]]
        return {'mem': mem, 'cpu': cpu, 'at': time.time(), 'cached': False}
    now = time.time() if now is None else now
    hist = _history()
    if hist and 0 <= now - hist[-1]['at'] < CACHE_TTL:
        return dict(_smooth(hist, now), cached=True)
    prev = next((h for h in reversed(hist) if h.get('raw')), None)
    s = (measure or (lambda: measure_now(prev)))()
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
    return dict(_smooth(hist, now), cached=False)


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
