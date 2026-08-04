"""Tests for the single-instance recorder lock.

The regression these guard against cost real data. On Windows the previous
liveness check reported every dead pid as alive, so a recorder that crashed
left a lock nothing could clear, and the next start refused with "already
running" until someone deleted the file by hand. Both stream recorders sat
dead for hours that way.
"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from app import proc_lock


class PidAliveTests(unittest.TestCase):
    def test_our_own_process_is_alive(self):
        self.assertTrue(proc_lock.pid_alive(os.getpid()))

    def test_zero_and_negative_are_not_processes(self):
        self.assertFalse(proc_lock.pid_alive(0))
        self.assertFalse(proc_lock.pid_alive(-1))

    def test_an_exited_process_is_dead(self):
        """The case the old check got wrong, and the reason locks went stale."""
        proc = subprocess.Popen([sys.executable, "-c", "pass"],
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        proc.wait(timeout=30)
        self.assertFalse(proc_lock.pid_alive(proc.pid))

    def test_a_running_child_is_alive(self):
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        try:
            self.assertTrue(proc_lock.pid_alive(proc.pid))
        finally:
            proc.kill()
            proc.wait(timeout=30)

    def test_checking_a_process_does_not_kill_it(self):
        """os.kill(pid, 0) routes to TerminateProcess on Windows.

        A liveness check that terminates what it inspects would have taken down
        a healthy recorder the moment a second start was attempted.
        """
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        try:
            proc_lock.pid_alive(proc.pid)
            self.assertIsNone(proc.poll(), "the check terminated the process")
        finally:
            proc.kill()
            proc.wait(timeout=30)


class AcquireTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.out_dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_acquire_writes_our_pid(self):
        lock = proc_lock.acquire(self.out_dir, "t.lock")
        self.assertEqual(lock.read_text(encoding="utf-8").strip(), str(os.getpid()))

    def test_a_stale_lock_is_taken_over(self):
        """A crashed recorder must not block the next start forever."""
        proc = subprocess.Popen([sys.executable, "-c", "pass"],
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        proc.wait(timeout=30)
        (self.out_dir / "t.lock").write_text(str(proc.pid), encoding="utf-8")

        lock = proc_lock.acquire(self.out_dir, "t.lock")
        self.assertEqual(lock.read_text(encoding="utf-8").strip(), str(os.getpid()))

    def test_a_live_owner_blocks_a_second_instance(self):
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        try:
            (self.out_dir / "t.lock").write_text(str(proc.pid), encoding="utf-8")
            with self.assertRaises(proc_lock.AlreadyRunning):
                proc_lock.acquire(self.out_dir, "t.lock")
        finally:
            proc.kill()
            proc.wait(timeout=30)

    def test_our_own_lock_does_not_block_us(self):
        (self.out_dir / "t.lock").write_text(str(os.getpid()), encoding="utf-8")
        proc_lock.acquire(self.out_dir, "t.lock")

    def test_an_unreadable_lock_is_replaced(self):
        (self.out_dir / "t.lock").write_text("not a pid", encoding="utf-8")
        lock = proc_lock.acquire(self.out_dir, "t.lock")
        self.assertEqual(lock.read_text(encoding="utf-8").strip(), str(os.getpid()))

    def test_release_removes_only_our_own_lock(self):
        lock = proc_lock.acquire(self.out_dir, "t.lock")
        proc_lock.release(lock)
        self.assertFalse(lock.exists())

        lock.write_text("999999", encoding="utf-8")
        proc_lock.release(lock)
        self.assertTrue(lock.exists(), "released a lock belonging to someone else")


if __name__ == "__main__":
    unittest.main()
