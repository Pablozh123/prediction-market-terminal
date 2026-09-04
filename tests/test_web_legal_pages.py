"""Imprint and privacy policy: two static pages next to index.html.

Both pages must exist, name what the law asks for, and stay free of any
script other than the theme snippet that index.html also carries — the
content-security policy hashes exactly that snippet, so a second inline
script or an event-handler attribute would be blocked in the browser and
never noticed on the file system. The build script copies web/ wholesale,
so the pages ship to the static host without a registration step; the
last test pins that.
"""

from __future__ import annotations

import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.build_static_site import build  # noqa: E402

WURZEL = Path(__file__).resolve().parents[1]
WEB = WURZEL / "web"
IMPRINT = WEB / "imprint.html"
PRIVACY = WEB / "privacy.html"
INDEX = WEB / "index.html"

SCRIPT_RE = re.compile(r"<script\b[^>]*>(.*?)</script>", re.S | re.I)
HANDLER_RE = re.compile(r"\son[a-z]+\s*=", re.I)


def _scripts(html: str) -> list[str]:
    return [m.group(0) for m in SCRIPT_RE.finditer(html)]


def _theme_script(html: str) -> str:
    """The one inline script index.html runs before first paint."""

    inline = [s for s in _scripts(html) if "src=" not in s.split(">", 1)[0]]
    if len(inline) != 1:
        raise AssertionError(f"index.html should carry exactly one inline script, found {len(inline)}")
    return inline[0]


class LegalPagesTest(unittest.TestCase):
    def test_pages_exist(self) -> None:
        for page in (IMPRINT, PRIVACY):
            self.assertTrue(page.is_file(), f"{page.name} missing under web/")

    def test_imprint_names_the_required_items(self) -> None:
        text = IMPRINT.read_text(encoding="utf-8")
        self.assertIn("<title>Imprint · Market Intel</title>", text)
        for word in ("address", "email", "Switzerland", "Last updated: 2026-09-04"):
            self.assertIn(word, text, f"imprint.html lacks '{word}'")
        self.assertIn('href="./privacy.html"', text)
        self.assertIn('href="./"', text)

    def test_privacy_names_every_recipient(self) -> None:
        text = PRIVACY.read_text(encoding="utf-8")
        self.assertIn("<title>Privacy policy · Market Intel</title>", text)
        for word in ("Cloudflare", "Railway", "Google Fonts", "localStorage", "cookies",
                     "Last updated: 2026-09-04"):
            self.assertIn(word, text, f"privacy.html lacks '{word}'")
        self.assertIn('href="./imprint.html"', text)
        self.assertIn('href="./"', text)

    def test_placeholders_are_the_same_on_both_pages(self) -> None:
        erwartet = {"[Full name]", "[Street and number]", "[Postal code and city]", "[contact email]"}
        for page in (IMPRINT, PRIVACY):
            gefunden = set(re.findall(r"\[[A-Za-z ]+\]", page.read_text(encoding="utf-8")))
            self.assertEqual(gefunden, erwartet, f"{page.name}: unexpected placeholder set")

    def test_no_inline_handlers(self) -> None:
        for page in (IMPRINT, PRIVACY):
            text = page.read_text(encoding="utf-8")
            self.assertIsNone(HANDLER_RE.search(text), f"{page.name} has an inline event handler")

    def test_only_the_theme_script(self) -> None:
        theme = _theme_script(INDEX.read_text(encoding="utf-8"))
        for page in (IMPRINT, PRIVACY):
            skripte = _scripts(page.read_text(encoding="utf-8"))
            self.assertEqual(skripte, [theme], f"{page.name}: scripts differ from the theme snippet in index.html")

    def test_build_ships_both_pages(self) -> None:
        out = Path(tempfile.mkdtemp(prefix="mi-legal-")) / "site"
        try:
            self.assertEqual(build(out), 0)
            for name in ("imprint.html", "privacy.html"):
                self.assertTrue((out / name).is_file(), f"{name} not in the build output")
        finally:
            shutil.rmtree(out.parent, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
