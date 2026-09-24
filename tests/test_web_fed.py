"""Run the dependency-free Fed renderer regression checks in normal CI."""
import shutil
import subprocess
import unittest
from pathlib import Path


class WebFedTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node is not installed")
    def test_renderer(self):
        subprocess.run([shutil.which("node"), "tests/web_fed_harness.mjs"],
                       cwd=Path(__file__).resolve().parents[1], check=True,
                       capture_output=True, text=True)
