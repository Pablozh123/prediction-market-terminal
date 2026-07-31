"""Daemon wrapper: record Kalshi books + trades from the WebSocket.

Seconds-resolution counterpart to ``run_kalshi_recorder.py``, which polls REST
every two minutes. Reconnects on its own; stop with Ctrl+C.

Needs KALSHI_KEY_ID and KALSHI_PRIVATE_KEY_PATH in the environment or in a
dotenv file (see .env.example). Read-only by construction: the handshake is
signed through app/kalshi_auth.py, which signs GET only and refuses every
portfolio and order path.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.kalshi_stream import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(["--loop", "--duration", "600"]))
