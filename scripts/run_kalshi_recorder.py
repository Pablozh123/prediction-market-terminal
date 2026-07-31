"""Daemon wrapper: record Kalshi order books + trades every 2 minutes.

Read-only (public REST endpoints, no credentials, no order path). The Kalshi
WebSocket requires an API key, which this repo does not handle, so the feed is
polled. Stop with Ctrl+C.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.kalshi_recorder import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(["--loop"]))
