"""Old claude.ai pages, older records and the stale rule copy (ARTIFACTSPEC 1.8.0, R4.19 to R4.23, R10.6).

Shared by project_artifacts.py (which writes the record) and the hooks (which only read). Nothing here
writes the record. Standard library only.
"""
import hashlib
import json
import os
import re
import subprocess

URL_RE = re.compile(r'^https?://\S+$')
HISTORY_LIMIT = 200          # commits of manifest.json that touch a url line: the scan stops there (R4.20)
GIT_TIMEOUT = 15
STALE_RULE_REL = '.claude/rules/project-artifacts.md'
PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# SHA-256 of every rules/project-artifacts.md a released plugin version shipped, line endings normalised and
# trailing whitespace stripped (R10.6). 1.0.0 is what `init` copied into projects; 1.1.0 to 1.1.2 shipped one text.
SHIPPED_RULE_SHA256 = {
    'a90a8c5589851ae52c884aaf7fc44b383f1f1fec2a0e35b46525ac564e3d0ba5': '1.0.0',
    'da59292d536662a281d2aaeebd9b22378f0864ed657f01109c1672f1ee21c1c7': '1.1.0',
    '7641ef11f679d5fe3465e087dd14e72c67fabcff4830c9986f7bbb69dc7f827b': '1.2.0',
    '99055a7a0c9b9836009917054cc4356da41fae3a0d794e2177d761ef81011ac7': '1.3.0',
}


def rule_sha(data):
    text = data.decode('utf-8', 'replace') if isinstance(data, bytes) else data
    text = text.replace('\r\n', '\n').replace('\r', '\n').strip()
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def current_rule_sha():
    try:
        with open(os.path.join(PLUGIN_DIR, 'rules', 'project-artifacts.md'), 'rb') as f:
            return rule_sha(f.read())
    except OSError:
        return None


def is_shipped_rule(data):
    """True when `data` is a rule text a released plugin version shipped (or the current one)."""
    h = rule_sha(data)
    return h in SHIPPED_RULE_SHA256 or h == current_rule_sha()


# --- the retired and deleted lists (R4.19) -------------------------------------------------------

def _list(manifest, name):
    v = manifest.get(name)
    return [e for e in v if isinstance(e, dict)] if isinstance(v, list) else []


def retired_pages(manifest):
    return _list(manifest, 'retired')


def deleted_pages(manifest):
    return _list(manifest, 'deleted')


def known_urls(manifest):
    """URLs that are retired, deleted, or Full Progress's: none of them is ever retired again."""
    urls = {e.get('url') for e in retired_pages(manifest) + deleted_pages(manifest)}
    fp = manifest.get('full_progress_artifact')
    if isinstance(fp, dict):
        urls.add(fp.get('url'))
    urls.discard(None)
    urls.discard('')
    return urls


def retire(manifest, key, title, url, iso):
    """Add a retired page unless its URL is known. Returns True when added."""
    if not isinstance(url, str) or not URL_RE.match(url) or url in known_urls(manifest):
        return False
    if not isinstance(manifest.get('retired'), list):
        manifest['retired'] = []
    manifest['retired'].append({'key': str(key), 'title': str(title or ''), 'url': url, 'retired': iso})
    return True


def move_feature_urls(manifest, iso):
    """R4.18/R4.19: a feature entry holds no url and no published_sha256. Its url moves to `retired`.
    `iso` is a function returning the time. Returns the keys changed."""
    keys = []
    feats = manifest.get('feature_artifacts')
    for e in feats if isinstance(feats, list) else []:
        if isinstance(e, dict) and ('url' in e or 'published_sha256' in e):
            url = e.pop('url', None)
            e.pop('published_sha256', None)
            if isinstance(url, str) and url and URL_RE.match(url) and url not in known_urls(manifest):
                retire(manifest, e.get('key'), e.get('title'), url, iso())
            keys.append(str(e.get('key')))
    return keys


def mark_deleted(manifest, url, key, iso, gone=False):
    """R4.21: the page is deleted (or gone): its retired entry moves to `deleted`. Raises ValueError when the
    URL is not retired or the key does not match. Returns the deleted entry."""
    found = None
    for e in retired_pages(manifest):
        if e.get('url') == url:
            found = e
            break
    if found is None:
        raise ValueError('%s is not in the retired list' % url)
    if key and found.get('key') != key:
        raise ValueError('%s belongs to "%s", not "%s"' % (url, found.get('key'), key))
    manifest['retired'] = [e for e in manifest['retired'] if e is not found]
    entry = {'key': found.get('key', ''), 'url': url, 'deleted': iso}
    if gone:
        entry['gone'] = True
    if not isinstance(manifest.get('deleted'), list):
        manifest['deleted'] = []
    manifest['deleted'].append(entry)
    return entry


# --- recovery from the history of manifest.json (R4.20) -------------------------------------------

def _git(cwd, args, data=None):
    try:
        return subprocess.run(['git', '-c', 'core.quotepath=off'] + list(args), cwd=cwd, capture_output=True,
                              input=data, stdin=None if data is not None else subprocess.DEVNULL,
                              timeout=GIT_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return None


def history_feature_urls(record_dir, rev='HEAD'):
    """[{key, title, url}] oldest first: every feature entry that had a url in a commit of manifest.json
    reachable from `rev`. At most HISTORY_LIMIT commits that touch a url line; one `git log` and one `git show` per commit; nothing cached."""
    r = _git(record_dir, ['log', '-n', str(HISTORY_LIMIT), '--format=%H', '-G', '"url"', rev, '--', 'manifest.json'])
    if r is None or r.returncode != 0:
        return []
    shas = r.stdout.decode('ascii', 'replace').split()
    if not shas:
        return []
    shas.reverse()
    out, seen = [], set()
    for sha in shas:                 # read-only `git show` only: the plugin never writes git state (AR50)
        r = _git(record_dir, ['show', '%s:./manifest.json' % sha])
        if r is None or r.returncode != 0:
            continue
        try:
            m = json.loads(r.stdout.decode('utf-8'))
        except ValueError:
            continue
        feats = m.get('feature_artifacts') if isinstance(m, dict) else None
        for e in feats if isinstance(feats, list) else []:
            url = e.get('url') if isinstance(e, dict) else None
            if isinstance(url, str) and URL_RE.match(url) and url not in seen and e.get('key') != 'full-progress':
                seen.add(url)
                out.append({'key': e.get('key'), 'title': e.get('title'), 'url': url})
    return out


def recover_retired(manifest, record_dir, iso, rev='HEAD'):
    """Add every history URL not already retired, deleted or Full Progress's. Returns the number added."""
    n = 0
    for h in history_feature_urls(record_dir, rev):
        if retire(manifest, h['key'], h['title'], h['url'], iso()):
            n += 1
    return n


def pending_text(entries, py):
    """The instruction for the session, one line per retired page (R4.22)."""
    lines = []
    for e in entries:
        lines.append('- %s "%s" %s' % (e.get('key'), e.get('title') or e.get('key'), e.get('url')))
    lines.append('Ask the owner to confirm, delete each confirmed page with the Artifact tool (`action: delete`), '
                 'then run: %s mark-deleted <key> --url <url> (add --gone for a page that no longer exists). '
                 'Never delete without the owner\'s confirmation.' % py)
    return '\n'.join(lines)


# --- an older record needs migrating (R4.23) -------------------------------------------------------

def migration_reasons(manifest, registry, feature_text):
    """Why the record needs migrating, read-only: feature entries holding a url, the retired status Done,
    feature files in the old fragment form. `feature_text(file)` returns a file's text or None."""
    reasons = []
    feats = [e for e in (manifest.get('feature_artifacts') or []) if isinstance(e, dict)] \
        if isinstance(manifest.get('feature_artifacts'), list) else []
    with_url = [str(e.get('key')) for e in feats if 'url' in e or 'published_sha256' in e]
    if with_url:
        reasons.append('feature artifacts %s still hold a claude.ai url' % ', '.join(sorted(with_url)))
    tasks = registry.get('tasks') if isinstance(registry, dict) and isinstance(registry.get('tasks'), list) else []
    if manifest.get('merged_status') == 'Done' or any(isinstance(t, dict) and t.get('status') == 'Done'
                                                      for t in tasks):
        reasons.append('the retired status Done is still in use')
    frag = []
    for e in feats:
        f = e.get('file')
        text = feature_text(f) if isinstance(f, str) else None
        if text and not text.lstrip('﻿ \t\r\n').lower().startswith('<!doctype'):
            frag.append(str(e.get('key')))
    if frag:
        reasons.append('feature artifacts %s are in the old fragment form' % ', '.join(sorted(frag)))
    return reasons
