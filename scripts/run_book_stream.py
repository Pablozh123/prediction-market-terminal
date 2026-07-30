"""Daemon wrapper: record Polymarket books + trades from the CLOB WebSocket.

Seconds-resolution counterpart to ``run_book_recorder.py``, which polls REST
every two minutes. Reconnects on its own; stop with Ctrl+C.

Read-only (public market channel, no credentials, no order path). For reboot
persistence the owner can add this script to scripts/install_autostart.ps1
alongside the existing daemons.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.book_stream import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(["--loop", "--duration", "600"]))
