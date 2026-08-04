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


#: Windows: a handle that may only be queried, never signalled.
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
#: GetExitCodeProcess reports this while the process is still running.
_STILL_ACTIVE = 259
#: OpenProcess sets this when no process carries the requested id.
_ERROR_INVALID_PARAMETER = 87


def _pid_alive_windows(pid: int) -> bool:
    """Liveness by querying the process, never by signalling it.

    ``os.kill(pid, 0)`` is the portable idiom and is wrong on Windows in both
    directions. For a dead pid it raises OSError rather than
    ProcessLookupError, which reads as "unknown, assume alive" and makes every
    stale lock permanent. For a live pid it is worse: on Windows os.kill routes
    to TerminateProcess, so the liveness check would kill the very recorder it
    was asked about.
    """
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ctypes.get_last_error() != _ERROR_INVALID_PARAMETER
    try:
        code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return True
        return code.value == _STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def pid_alive(pid: int) -> bool:
    """Is this PID a live process? Unknown states count as alive.

    Guessing "dead" on a live process is the dangerous direction: it would hand
    a second writer the same files. Guessing "alive" on a dead one only costs a
    stale lock the user can delete.

    The one known false positive is a process that exited with code 259, which
    is indistinguishable from still running. That keeps the bias in the safe
    direction.
    """
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            return _pid_alive_windows(pid)
        except OSError:
            return True
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
