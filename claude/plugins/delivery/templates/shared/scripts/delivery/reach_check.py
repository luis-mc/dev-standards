#!/usr/bin/env python3
"""Check which URLs this machine can reach.

Agent sandboxes often block outbound hosts (package registries, a preview
deployment, an API). Run this first to learn what is reachable from where the
agent actually runs, instead of finding out through a confusing build failure.

GETs each URL (redirects followed, normal User-Agent) and prints a table of the
HTTP status or the error. Exit 0 when every URL answered with a status below
500, 1 otherwise (a 4xx counts as reachable: the host answered), 2 on usage
errors. Python 3.11+, standard library only.
"""
from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from urllib.parse import urlparse

USER_AGENT = "Mozilla/5.0 (compatible; reach_check/1)"


def probe(url: str, timeout: float) -> tuple[bool, str]:
    """Return (answered with a status below 500, text for the table)."""
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            final = resp.geturl()
    except urllib.error.HTTPError as exc:
        status, final = exc.code, url
    except urllib.error.URLError as exc:
        return False, f"error: {exc.reason}"
    except (OSError, ValueError) as exc:  # timeouts, resets, TLS failures
        return False, f"error: {exc}"
    note = f" (redirected to {final})" if final != url else ""
    return status < 500, f"{status}{note}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Check which URLs are reachable from here.")
    ap.add_argument("urls", nargs="+", metavar="URL")
    ap.add_argument("--timeout", type=float, default=10, help="seconds per URL (default 10)")
    args = ap.parse_args(argv)

    for url in args.urls:
        if urlparse(url).scheme not in ("http", "https"):
            print(f"reach_check: {url!r} is not an http(s) URL", file=sys.stderr)
            return 2

    rows = []
    ok = True
    for url in args.urls:
        good, text = probe(url, args.timeout)
        ok = ok and good
        rows.append(("ok" if good else "FAIL", url, text))
    width = max(len(r[1]) for r in rows)
    print(f"{'':4}  {'URL':<{width}}  RESULT")
    for mark, url, text in rows:
        print(f"{mark:<4}  {url:<{width}}  {text}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
