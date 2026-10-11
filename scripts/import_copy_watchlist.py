"""Import [{wallet, sources: [https://x.com/.../status/...]}] into the paper desk.

Usage: python scripts/import_copy_watchlist.py data/copy_watchlist_import.json
Existing paper accounts and pause states are preserved. --refresh reads public
wallet data immediately; the API and copy daemon subsequently refresh it.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import copy_intelligence as ci
from src import copy_trading as ct


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file', type=Path)
    parser.add_argument('--db', type=Path, default=ct.DEFAULT_DB_PATH)
    parser.add_argument('--refresh', action='store_true')
    args = parser.parse_args()
    entries = json.loads(args.file.read_text(encoding='utf-8-sig'))
    state = ci.import_watchlist(entries, args.db)
    print(f"Watching {len(state['watchlist'])} wallets in {args.db}", flush=True)
    if args.refresh:
        state = ci.refresh(args.db)
        for wallet, profile in state['profiles'].items():
            print(wallet, profile.get('name'), profile.get('activity_count'), profile.get('errors'), flush=True)
        print(f"Overlaps: {len(state['overlaps'])}; errors: {len(state['errors'])}")


if __name__ == '__main__':
    main()
