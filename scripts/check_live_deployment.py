"""Check deployment freshness without disguising HTTP/edge failures as stale code."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.smoke_live_api import fetch


def evaluate(status, headers, body, want, age_minutes, grace_minutes):
    headers = {k.lower(): v for k, v in headers.items()}
    if status == 0:
        return "error", "Health request failed at network/transport level; check connectivity and origin logs"
    if status != 200:
        edge = " Cloudflare challenge" if headers.get("cf-mitigated") == "challenge" else ""
        ray = headers.get("cf-ray", "none")
        return "error", f"Health HTTP {status}.{edge}; CF-Ray={ray}. No deployment comparison possible"
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return "error", "Health HTTP 200 but response is not JSON; check edge rules and origin routing"
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        return "error", "Health payload is not a healthy API object (ok=true required)"
    got = payload.get("commit")
    if not isinstance(got, str) or not re.fullmatch(r"[0-9a-f]{40}", got):
        return "error", "Health payload has no valid deployment commit; check RAILWAY_GIT_COMMIT_SHA"
    if got == want:
        return "current", f"Live commit matches main: {want}"
    if age_minutes < grace_minutes:
        return "deploying", f"Live={got}; main={want} is {age_minutes:.1f} min old; deployment grace period"
    return "error", f"Stale deployment: live={got}; main={want} for {age_minutes:.1f} min; check Railway deployments"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url")
    parser.add_argument("--commit", required=True)
    parser.add_argument("--commit-time", required=True, type=int)
    parser.add_argument("--grace-minutes", type=float, default=20)
    args = parser.parse_args(argv)
    status, headers, body, _ = fetch(args.base_url.rstrip("/") + "/api/health", "GET", 15)
    state, message = evaluate(status, headers, body, args.commit,
                              (time.time() - args.commit_time) / 60, args.grace_minutes)
    # Keep server-controlled header text from injecting Actions commands.
    message = message.replace("\r", " ").replace("\n", " ")
    print(("::error::" if state == "error" else "::notice::") + message)
    if output := os.environ.get("GITHUB_OUTPUT"):
        with open(output, "a", encoding="utf-8") as stream:
            stream.write(f"current={'true' if state == 'current' else 'false'}\n")
    return 1 if state == "error" else 0


if __name__ == "__main__":
    sys.exit(main())
