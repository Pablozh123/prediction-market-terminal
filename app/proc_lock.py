"""Single-instance lock for the append-only recorders.

Every recorder in this repo appends CSV rows from a buffered file handle. Two
instances on the same output directory interleave partial lines, which corrupts
the data silently and is only noticed much later, during analysis. Once a
recorder is on autostart a second manual start stops being hypothetical, so the
guard belongs in the recorder rather than in a habit.

Streamlit-free, no network. Used by ``src/book_stream.py`` and
``src/kalshi_recorder.py``.
"""

from __future__ import annotations

import os
from pathlib import Path


class AlreadyRunning(RuntimeError):
    """Another instance owns the output directory."""


def pid_alive(pid: int) -> bool:
    """Is this PID a live process? Unknown states count as alive.

    Guessing "dead" on a live process is the dangerous direction: it would hand
    a second writer the same files. Guessing "alive" on a dead one only costs a
    stale lock the user can delete.
    """
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return True


def acquire(out_dir: Path, name: str = "recorder.lock") -> Path:
    """Claim the output directory, or refuse to start."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    lock = out_dir / name
    if lock.exists():
        try:
            owner = int(lock.read_text(encoding="utf-8").strip() or 0)
        except (OSError, ValueError):
            owner = 0
        if owner and owner != os.getpid() and pid_alive(owner):
            raise AlreadyRunning(
                f"recorder already running as PID {owner} (lock: {lock}). "
                f"Stop it first, or delete the lock if stale."
            )
    lock.write_text(str(os.getpid()), encoding="utf-8")
    return lock


def release(lock: Path) -> None:
    """Drop our claim. A lock owned by someone else is left alone."""
    try:
        if Path(lock).read_text(encoding="utf-8").strip() == str(os.getpid()):
            Path(lock).unlink()
    except (OSError, ValueError):
        pass
