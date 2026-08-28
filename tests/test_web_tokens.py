"""Die Design-Tokens der Weboberflaeche bleiben die einzige Quelle.

Der Design-Review vom 2026-08-28 (Abschnitt C) hat das Gegenteil gemessen:
21 Schriftgroessen, 37 Ink-Alphas, 262 rohe Radien und zwei Schriftfamilien
als Literal, waehrend die Tokens dafuer in web/css/terminal.css standen und
null Aufrufstellen hatten. Diese Datei haelt den Zustand danach fest.

Geprueft wird der Quelltext, nicht das gerenderte Markup: eine neue
Aufrufstelle soll auffallen, bevor sie in einer Nutzlast landet. Ausnahmen
stehen namentlich in den Konstanten unten, mit dem Grund daneben.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

WURZEL = Path(__file__).resolve().parents[1]
JS = sorted((WURZEL / "web" / "js").rglob("*.js"))
CSS = (WURZEL / "web" / "css" / "terminal.css").read_text(encoding="utf-8")

#: Textstufen und ihre Alphawerte im dunklen Thema, aus terminal.css.
INK_STUFEN = ("--ink-1", "--ink-2", "--ink-3", "--ink-4")
#: Rahmenstufen, ebenfalls aus terminal.css.
LINIEN_STUFEN = ("--line-edge", "--line-1", "--line-2", "--line-3")
#: Die sechs Schritte der Typoleiter.
TYPO_STUFEN = ("--t-micro", "--t-small", "--t-body", "--t-lead", "--t-head", "--t-hero")
#: Die sieben Stufen der Abstandsleiter.
ABSTAND_STUFEN = ("--sp-1", "--sp-2", "--sp-3", "--sp-4", "--sp-5", "--sp-6", "--sp-7")

#: Die Eigenschaften, die den Rhythmus tragen. `inset`, `top` und Geschwister
#: stehen bewusst nicht dabei: das ist Position, kein Abstand.
ABSTAND_EIGENSCHAFTEN = (
    "padding", "padding-top", "padding-right", "padding-bottom", "padding-left",
    "margin", "margin-top", "margin-right", "margin-bottom", "margin-left",
    "gap", "row-gap", "column-gap",
)

#: Zwei Einzuege bleiben Zahlen, weil sie Ausrichtung sind und keine Stufe:
#: beide sind genau so breit wie die Rasterspalte ueber ihnen, damit der Block
#: darunter beginnt. Eine Stufe daraus zu machen hiesse, die Ausrichtung an
#: den Rhythmus zu verlieren.
AUSRICHTUNG_PX = ("108px", "222px")

#: SVG-Praesentationsattribute koennen kein var() aufnehmen. Sie tragen ihre
#: Groesse und Familie deshalb weiterhin als Zahl beziehungsweise als String,
#: und die Tickgeometrie der Diagramme ist gegen genau diese Groessen von Hand
#: gesetzt.
SVG_ATTRIBUT = re.compile(r'font-(?:size|family)="[^"]*"')


def _ohne_svg_attribute(text: str) -> str:
    return SVG_ATTRIBUT.sub("", text)


class WebTokenTest(unittest.TestCase):
    def test_terminal_css_definiert_jede_stufe_in_beiden_themes(self) -> None:
        """Die Textstufen brauchen im hellen Thema eigene Alphawerte.

        Dasselbe Alpha kauft auf den beiden Gruenden verschiedenen Kontrast;
        eine Stufe, die nur im dunklen Block steht, waere im hellen geraten.
        """

        teile = CSS.split(':root[data-theme="light"]')
        dunkel, hell = teile[0], "".join(teile[1:])
        for token in INK_STUFEN:
            with self.subTest(token=token):
                self.assertIn(token + ":", dunkel)
                self.assertIn(token + ":", hell)
        for token in LINIEN_STUFEN + TYPO_STUFEN + ABSTAND_STUFEN:
            with self.subTest(token=token):
                self.assertIn(token + ":", dunkel)

    def test_keine_rohe_schriftgroesse_im_javascript(self) -> None:
        """21 Groessen wurden zu sechs Stufen; eine siebte faellt hier auf."""

        for pfad in JS:
            treffer = re.findall(
                r"font-size:[0-9.]+px", _ohne_svg_attribute(pfad.read_text(encoding="utf-8")))
            with self.subTest(datei=pfad.name):
                self.assertEqual(treffer, [], f"{pfad.name}: {treffer[:4]}")

    def test_keine_rohen_kontroll_oder_panel_radien(self) -> None:
        """--r-control (4px) und --r-panel (6px) hatten null Aufrufstellen."""

        for pfad in JS:
            text = pfad.read_text(encoding="utf-8")
            for wert in ("border-radius:4px", "border-radius:6px"):
                with self.subTest(datei=pfad.name, wert=wert):
                    self.assertNotIn(wert, text)

    def test_keine_schriftfamilie_als_literal_in_stil_strings(self) -> None:
        """--font-ui und --font-mono hatten null Aufrufstellen im JS."""

        for pfad in JS:
            text = _ohne_svg_attribute(pfad.read_text(encoding="utf-8"))
            treffer = re.findall(r"font-family:\\?'?IBM Plex", text)
            with self.subTest(datei=pfad.name):
                self.assertEqual(treffer, [], f"{pfad.name}: {len(treffer)} Literale")

    def test_keine_textfarbe_ausserhalb_der_ink_leiter(self) -> None:
        """color: nimmt eine Stufe, keine Zahl.

        Genau hier ist der Kontrast entschieden: --ink-4 ist die Untergrenze,
        die in beiden Themes noch AA besteht (5.07:1 dunkel, 4.99:1 hell auf
        dem tiefsten Grund). Ein roh geschriebenes Alpha umgeht diese
        Entscheidung, und das ist der Weg, auf dem die 14 Knoten unter AA
        entstanden sind, die PR #118 gefunden hat.
        """

        for pfad in JS:
            text = pfad.read_text(encoding="utf-8")
            treffer = re.findall(r"(?<![-\w])color:\s*rgba\(var\(--ink\),\s*[0-9.]+\)", text)
            with self.subTest(datei=pfad.name):
                self.assertEqual(treffer, [], f"{pfad.name}: {treffer[:3]}")

    def test_kein_roher_abstand_im_javascript(self) -> None:
        """133 Polsterketten wurden sieben Stufen; eine achte faellt hier auf.

        Der Befund von Abschnitt C.2 war nicht, dass die Zahlen falsch waren,
        sondern dass es keine Basiseinheit gab: jede ganze Zahl von 1 bis 18
        kam als Polsterkomponente vor, und 87 der 133 Ketten standen genau
        ein- oder zweimal da. Eine neue rohe Zahl faengt genau so wieder an.
        """

        muster = re.compile(
            r"(?<![-\w])(" + "|".join(ABSTAND_EIGENSCHAFTEN) + r")\s*:\s*([^;'\"}\n]+)")
        for pfad in JS + [WURZEL / "web" / "css" / "terminal.css"]:
            text = pfad.read_text(encoding="utf-8")
            treffer = []
            for m in muster.finditer(text):
                for teil in m.group(2).split():
                    if teil in AUSRICHTUNG_PX:
                        continue
                    if re.fullmatch(r"\d+(?:\.\d+)?px", teil):
                        treffer.append(m.group(1) + ":" + m.group(2).strip())
            with self.subTest(datei=pfad.name):
                self.assertEqual(treffer, [], f"{pfad.name}: {treffer[:4]}")

    def test_keine_groesse_wird_in_den_stil_string_gerechnet(self) -> None:
        """Ein Wert, der als Zahl in den String faellt, entzieht sich der Suche.

        app.js::stepper hat genau das getan -- Radius, Schriftgroesse und
        Polsterung mit `+ 'px'` angehaengt -- und ist deshalb weder beim
        Token-Durchgang von PR #123 noch beim Abstandsdurchgang durch eine
        Textsuche gefunden worden. Beide Leitern lassen sich nur einhalten,
        solange die Werte im String stehen und nicht daneben.
        """

        muster = re.compile(
            r"(?:font-size|border-radius|" + "|".join(ABSTAND_EIGENSCHAFTEN)
            + r")\s*:\s*'\s*\+")
        for pfad in JS:
            text = pfad.read_text(encoding="utf-8")
            # Eine gerechnete Angabe ist erlaubt, wenn beide Zweige Stufen
            # nennen: der Zweig ist dann eine Entscheidung, keine Zahl.
            treffer = [m.group(0) for m in muster.finditer(text)
                       if not re.match(r"[^\n]{0,120}var\(--", text[m.end():m.end() + 120])]
            with self.subTest(datei=pfad.name):
                self.assertEqual(treffer, [], f"{pfad.name}: {treffer[:3]}")

    def test_die_stufen_werden_auch_benutzt(self) -> None:
        """Ein Token ohne Aufrufstellen ist der Befund, nicht die Loesung."""

        gesamt = "\n".join(p.read_text(encoding="utf-8") for p in JS)
        for token in INK_STUFEN + LINIEN_STUFEN + TYPO_STUFEN + ABSTAND_STUFEN:
            with self.subTest(token=token):
                self.assertIn("var(" + token + ")", gesamt)
        for token in ("--r-control", "--r-panel", "--font-mono", "--font-ui"):
            with self.subTest(token=token):
                self.assertIn("var(" + token + ")", gesamt)

    def test_die_kennzahlenkachel_hat_genau_einen_bauer(self) -> None:
        """Elf Bauer wurden einer; vier Nachzuegler auf der Wallet-Seite auch.

        Der Test liest die Quelle, weil eine Kopie sich beim Rendern nicht
        von der Vorlage unterscheidet: nur im Text faellt auf, dass jemand
        die Kachel wieder von Hand gebaut hat.
        """

        wallet = (WURZEL / "web" / "js" / "pages" / "wallet_page.js").read_text(encoding="utf-8")
        for name in ("tile", "kpiTile", "stTile", "riskCard"):
            with self.subTest(bauer=name):
                self.assertIn(name, wallet)
        # Kein zweiter Bauer: die Kachelflaeche steht nur noch in ui.js::kpi.
        self.assertNotIn("min-height:62px", wallet)
        self.assertNotIn("background:rgba(var(--ink),.015)", wallet)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
