#!/usr/bin/env python3
"""Ask the publish service for a token, and retry when it answers 5xx (CIR10 W5).

    publish_token.py --url URL [--header "Name: value" ...] [--data TEXT] [--out FILE]
                     [--delays 1,2,4]

POSTs once, and again after each delay in `--delays` (seconds, default 1,2,4) while the
answer is a 5xx or the connection fails. A 4xx is final: it is not retried. The body of the
first 2xx answer goes to `--out` (default stdout). The token is never printed anywhere else.
Exit: 0 got a token, 1 gave up, 2 usage. Python 3.11+, standard library only.
"""
from __future__ import annotations

import argparse
import sys
import time
import urllib.error
import urllib.request

sys.dont_write_bytecode = True


def fetch(url: str, headers: dict[str, str], data: bytes, delays: list[float],
          opener=urllib.request.urlopen, sleep=time.sleep) -> tuple[int, str]:
    """(0, body) on success, (1, reason) when out of tries or on a 4xx."""
    reason = ""
    for attempt in range(len(delays) + 1):
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with opener(req, timeout=30) as resp:
                return 0, resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            reason = "HTTP %d" % exc.code
            if exc.code < 500:
                return 1, reason
        except (OSError, ValueError) as exc:
            reason = "no answer (%s)" % type(exc).__name__
        if attempt < len(delays):
            print("publish-token: %s, retrying in %g s" % (reason, delays[attempt]), file=sys.stderr)
            sleep(delays[attempt])
    return 1, reason


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="publish_token.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--url", required=True)
    ap.add_argument("--header", action="append", default=[])
    ap.add_argument("--data", default="")
    ap.add_argument("--out")
    ap.add_argument("--delays", default="1,2,4")
    args = ap.parse_args(argv)
    try:
        delays = [float(x) for x in args.delays.split(",") if x.strip()]
        headers = dict(h.split(":", 1) for h in args.header)
    except ValueError:
        print("publish-token: bad --delays or --header", file=sys.stderr)
        return 2
    headers = {k.strip(): v.strip() for k, v in headers.items()}
    code, body = fetch(args.url, headers, args.data.encode("utf-8"), delays)
    if code:
        print("publish-token: gave up: %s" % body, file=sys.stderr)
        return 1
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(body)
    else:
        sys.stdout.write(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
