"""Die Schutzheader der statischen Auslieferung passen zum Markup.

web/_headers traegt die CSP fuer Cloudflare Pages mit dem Hash des einzigen
Inline-Skripts (Theme-Bootstrap). Aendert jemand das Skript in index.html,
ohne den Hash nachzurechnen, blockiert der Browser den Bootstrap still und
die gespeicherte Themenwahl blitzt beim Laden — dieser Test faellt dann.
"""

from __future__ import annotations

import base64
import hashlib
import re
import unittest
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
WEB = WURZEL / "web"


def _inline_script(html: str) -> str:
    treffer = re.findall(r"<script>(.*?)</script>", html, re.S)
    assert len(treffer) == 1, treffer
    return treffer[0]


def _hash(text: str) -> str:
    return "sha256-" + base64.b64encode(hashlib.sha256(text.encode("utf-8")).digest()).decode()


class PagesHeaderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.headers = (WEB / "_headers").read_text(encoding="utf-8")
        self.index = (WEB / "index.html").read_text(encoding="utf-8")

    def test_csp_hash_passt_zum_theme_skript(self) -> None:
        hash_ = _hash(_inline_script(self.index))
        self.assertIn("'" + hash_ + "'", self.headers)
        self.assertNotIn("'unsafe-inline'", self.headers.split("script-src")[1].split(";")[0])

    def test_alle_statischen_seiten_teilen_das_skript(self) -> None:
        soll = _inline_script(self.index)
        for name in ("imprint.html", "privacy.html", "404.html"):
            with self.subTest(seite=name):
                self.assertEqual(_inline_script((WEB / name).read_text(encoding="utf-8")), soll)

    def test_schutzheader_vorhanden(self) -> None:
        block = self.headers.split("\n/*\n", 1)[1]
        for name in ("Content-Security-Policy", "Strict-Transport-Security", "X-Frame-Options",
                     "Permissions-Policy", "Referrer-Policy", "X-Content-Type-Options"):
            with self.subTest(header=name):
                self.assertIn(name + ":", block)
        hsts = [z for z in block.splitlines() if "Strict-Transport-Security" in z][0]
        self.assertNotIn("preload", hsts)
        self.assertIn("connect-src 'self' https://api.marketintel.dev", block)

    def test_sitemap_nennt_nur_vorhandene_seiten(self) -> None:
        sitemap = (WEB / "sitemap.xml").read_text(encoding="utf-8")
        urls = re.findall(r"<loc>(.*?)</loc>", sitemap)
        self.assertTrue(urls)
        for url in urls:
            pfad = url.replace("https://marketintel.dev", "").lstrip("/") or "index.html"
            with self.subTest(url=url):
                self.assertTrue((WEB / pfad).is_file(), pfad)
                html = (WEB / pfad).read_text(encoding="utf-8")
                self.assertNotIn("noindex", html)
        robots = (WEB / "robots.txt").read_text(encoding="utf-8")
        self.assertIn("Sitemap: https://marketintel.dev/sitemap.xml", robots)

    def test_security_txt_und_redirects(self) -> None:
        txt = (WEB / ".well-known" / "security.txt").read_text(encoding="utf-8")
        self.assertIn("Contact: https://", txt)
        self.assertIn("Expires: 2027-", txt)
        self.assertNotIn("[", txt)  # kein Platzhalter
        redirects = (WEB / "_redirects").read_text(encoding="utf-8")
        regeln = [z.split() for z in redirects.splitlines() if z and not z.startswith("#")]
        self.assertEqual(len(regeln), 2)
        for quelle, ziel, status in regeln:
            self.assertTrue(ziel.startswith("https://marketintel.dev/"), ziel)
            self.assertNotEqual(quelle.split("/")[2], "marketintel.dev", quelle)
            self.assertEqual(status, "301")

    def test_build_liefert_well_known_mit(self) -> None:
        import shutil
        import sys
        import tempfile
        sys.path.insert(0, str(WURZEL / "scripts"))
        from build_static_site import build  # noqa: E402

        out = Path(tempfile.mkdtemp()) / "site"
        try:
            self.assertEqual(build(out), 0)
            self.assertTrue((out / ".well-known" / "security.txt").is_file())
            self.assertTrue((out / "_redirects").is_file())
            self.assertFalse((out / ".DS_Store").exists())
        finally:
            shutil.rmtree(out.parent, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
