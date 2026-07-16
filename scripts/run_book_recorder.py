"""Daemon wrapper: record Polymarket books + tape every 2 minutes.

Read-only (public endpoints, no credentials). Runs in the foreground;
stop with Ctrl+C. For reboot persistence, the owner can add this script
to scripts/install_autostart.ps1 alongside the existing daemons.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.book_recorder import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(["--loop"]))
