"""Keyboard focus on the theme toggle survives the 30-second poll.

render() in web/js/app.js rebuilds the topbar on every poll and puts the
keyboard back only on an element that carries a data-key. The theme chip had
none, so a reader who had tabbed to it lost the focus every 30 s (live audit
of marketintel.dev, 2026-09-04).

The topbar is a method of the app class, and web/js/app.js mounts that class
on import against a real DOM, so tests/web_render_harness.mjs cannot draw it.
These checks read the source instead, the way test_web_leerzustand.py already
does for the topbar labels. They are deliberately literal: the attribute on
the chip, the guard around setSelectionRange, and the rule that a panel
which just took the keyboard is not overridden by the restore.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
APP_JS = WURZEL / "web" / "js" / "app.js"


def _quelle() -> str:
    return APP_JS.read_text(encoding="utf-8")


def _methode(quelle: str, name: str) -> str:
    """The source of one class method, from its head to the next method head."""

    treffer = re.search(
        rf"^  {re.escape(name)}\([^)]*\) \{{\n(.*?)^  \}}\n", quelle, re.S | re.M)
    assert treffer, f"method {name}() not found in app.js"
    return treffer.group(1)


class ThemeToggleFocusTest(unittest.TestCase):
    def test_der_theme_schalter_traegt_einen_festen_data_key(self) -> None:
        topbar = _methode(_quelle(), "renderTopbar")
        zeilen = [z for z in topbar.splitlines() if 'aria-label="Switch to ' in z]
        self.assertEqual(len(zeilen), 1, "expected exactly one theme chip in renderTopbar")
        chip = zeilen[0]
        self.assertIn('data-key="theme-toggle"', chip)
        # The input dispatcher fires on input events of [data-inp] elements
        # only; the chip is a click target and must not become one of them.
        self.assertNotIn("data-inp", chip)
        self.assertIn("this.act(", chip)

    def test_render_merkt_sich_jedes_element_mit_data_key(self) -> None:
        render = _methode(_quelle(), "render")
        # The capture keys on data-key alone — no tag-name test that would
        # limit the restore to text fields.
        self.assertIn("ae.dataset.key", render)
        kopf = render.split("this._focus = { key: ae.dataset.key")[0]
        self.assertNotIn("INPUT", kopf)
        self.assertIn("document.querySelector('[data-key=\"' + this._focus.key + '\"]')", render)

    def test_die_wiederherstellung_setzt_keinen_cursor_auf_ein_div(self) -> None:
        render = _methode(_quelle(), "render")
        aufrufe = [m.start() for m in re.finditer(r"el\.setSelectionRange\(", render)]
        self.assertEqual(len(aufrufe), 1, "expected one setSelectionRange call in render()")
        davor = render[max(0, aufrufe[0] - 400):aufrufe[0]]
        self.assertIn("typeof el.setSelectionRange === 'function'", davor)
        self.assertIn("typeof this._focus.start === 'number'", davor)

    def test_ein_geoeffnetes_panel_behaelt_die_tastatur(self) -> None:
        # "/" on the focused chip opens the palette; the restore must not pull
        # the caret back out of it. Both panels drop the remembered focus
        # when they take it.
        render = _methode(_quelle(), "render")
        self.assertIn("if (feld) { feld.focus(); this._focus = null; }", render)
        self.assertIn("if (zu) { zu.focus(); this._focus = null; }", render)
        self.assertLess(render.index("this._focus = null; }"), render.index("if (this._focus) {"))


if __name__ == "__main__":
    unittest.main()
