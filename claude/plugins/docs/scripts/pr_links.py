#!/usr/bin/env python3
"""pr_links: where a pull request lives, so Full Progress can link it (ARTIFACTSPEC R5.65, R5.66).

Pure helpers. Nothing here runs git except `derive_from_git`, which only the writing script calls.
Standard library only.
"""
import re
import subprocess
from html import escape

PR_URL_PATTERNS = {
    'github': 'https://{host}/{repo}/pull/{n}',
    'gitlab': 'https://{host}/{repo}/-/merge_requests/{n}',
}
DEFAULT_HOSTS = {'github': 'github.com', 'gitlab': 'gitlab.com'}
PROVIDERS = ('github', 'gitlab', 'custom')

HOST_RE = re.compile(r'^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?(:\d{1,5})?$')
SEGMENT = r'[A-Za-z0-9_.-]+'
GITHUB_REPO_RE = re.compile(r'^%s/%s$' % (SEGMENT, SEGMENT))
GITLAB_REPO_RE = re.compile(r'^%s(/%s)+$' % (SEGMENT, SEGMENT))
BAD_URL_CHARS = re.compile(r'[\s"\'<>\\`]')


def problems(setting) -> list:
    """Why a `pr_links` value is not valid; [] when it is (R5.66)."""
    if not isinstance(setting, dict):
        return ['pr_links must be an object']
    out = []
    extra = sorted(set(setting) - {'provider', 'repo', 'host', 'template'})
    if extra:
        out.append('pr_links: unknown field(s) %s' % ', '.join(extra))
    provider = setting.get('provider')
    if provider not in PROVIDERS:
        return out + ['pr_links: provider must be one of %s' % ', '.join(PROVIDERS)]
    host = setting.get('host')
    if host is not None and not (isinstance(host, str) and HOST_RE.match(host)):
        out.append('pr_links: host must be a bare host name')
    if provider == 'custom':
        t = setting.get('template')
        if not isinstance(t, str) or not t.startswith('https://') or '{n}' not in t or BAD_URL_CHARS.search(t):
            out.append('pr_links: template must be an https URL with {n} and no space or quote')
        if setting.get('repo') is not None:
            out.append('pr_links: repo is not used with provider custom')
        return out
    if setting.get('template') is not None:
        out.append('pr_links: template is for provider custom only')
    repo = setting.get('repo')
    rx = GITHUB_REPO_RE if provider == 'github' else GITLAB_REPO_RE
    if not (isinstance(repo, str) and rx.match(repo) and '..' not in repo):
        out.append('pr_links: repo must be %s' % ('owner/repo' if provider == 'github' else 'group/project'))
    return out


def pr_url(setting, n):
    """The https URL of pull request `n`, or None when none can be built safely."""
    if isinstance(n, bool) or not isinstance(n, int) or n <= 0 or problems(setting):
        return None
    provider = setting['provider']
    if provider == 'custom':
        url = setting['template'].replace('{n}', str(n))
    else:
        url = PR_URL_PATTERNS[provider].format(host=setting.get('host') or DEFAULT_HOSTS[provider], repo=setting['repo'], n=n)
    if not url.lower().startswith('https://') or BAD_URL_CHARS.search(url):
        return None
    return url


def link(text: str, n, setting) -> str:
    """HTML for a PR label: an anchor when a URL can be built, else the escaped text."""
    url = pr_url(setting, n) if setting else None
    if url is None:
        return escape(text)
    return '<a href="%s" target="_blank" rel="noopener noreferrer">%s</a>' % (escape(url, quote=True), escape(text))


def parse_remote(remote: str):
    """A `pr_links` dict from a git remote URL (https or ssh; github or gitlab), else None."""
    r = (remote or '').strip()
    m = (re.match(r'^(?:ssh|git|https?)://(?:[^@/]+@)?([^/:]+)(?::\d+)?/(.+)$', r)
         or re.match(r'^[^@/\s]+@([^:/\s]+):(.+)$', r))
    if not m:
        return None
    host, path = m.group(1).lower(), re.sub(r'(\.git)?/*$', '', m.group(2).strip('/'))
    provider = 'github' if host == 'github.com' else 'gitlab' if 'gitlab' in host else None
    if provider is None:
        return None
    out = {'provider': provider, 'repo': path}
    if host != DEFAULT_HOSTS[provider]:
        out['host'] = host
    return out if not problems(out) else None


def derive_from_git(root: str):
    """`pr_links` from `git remote get-url origin` in `root`, else None. Only the writing script calls this."""
    try:
        got = subprocess.run(['git', '-C', root, 'remote', 'get-url', 'origin'], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return parse_remote(got.stdout) if got.returncode == 0 else None
