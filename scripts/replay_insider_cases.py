"""Replay the documented insider cases (data/insider_cases.yaml) through the risk screen.

    python scripts/replay_insider_cases.py            # table, exit 1 when an expectation fails
    python scripts/replay_insider_cases.py --json     # the same as JSON

Each case is rebuilt as a small synthetic tape from the numbers its source
documents (size, price, wallets, prints, first trade) and run through the
production ladder (app.suspicion.screen_tape). The table says, per case,
what the screen made of it and whether that met the documented expectation.
tests/test_insider_cases.py runs the same check in CI.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import insider_cases  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--json", action="store_true", help="print the results as JSON")
    parser.add_argument("--whale-threshold", type=float, default=insider_cases.DEFAULT_WHALE_THRESHOLD)
    args = parser.parse_args(argv)

    results = insider_cases.replay_all(whale_threshold=args.whale_threshold)
    if args.json:
        print(json.dumps(results, indent=2, default=str))
    else:
        width = max((len(r["id"]) for r in results), default=10)
        print(f"{'case':<{width}}  {'expect':<8}  {'context':<24}  {'event':>5}  {'flag':<5}  {'wallet':>6}  ok")
        for r in results:
            if not r.get("replayable", True):
                print(f"{r['id']:<{width}}  {r['expectation']:<8}  {'(documented, not replayed)':<24}")
                continue
            event = "excl" if r.get("excluded") else (f"{r['event_score']:.0f}" if r.get("event_score") is not None else "-")
            wallet = f"{r['wallet_score']:.0f}" if r.get("wallet_score") is not None else "-"
            print(f"{r['id']:<{width}}  {r['expectation']:<8}  {str(r.get('context') or ''):<24}  {event:>5}  "
                  f"{'yes' if r.get('flagged') else 'no':<5}  {wallet:>6}  {'ok' if r.get('ok') else 'MISS'}")
            if r.get("problems"):
                print(f"{'':<{width}}  problems: {'; '.join(r['problems'])}")
        failed = [r for r in results if not r.get("ok", True)]
        print(f"\n{len(results)} cases, {len(failed)} missed expectation")
    return 1 if any(not r.get("ok", True) for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
