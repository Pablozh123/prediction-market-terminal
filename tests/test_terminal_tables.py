"""Jede ``column_config``-Angabe im Monolithen muss eine Spalte treffen, die es gibt.

Anlass: die Kalendertabelle auf der Markets-Seite konfigurierte eine Spalte
``volume`` mit Dollarformat. Die Spalte hiess da schon ``volume_usd`` bzw.
``volume_contracts``, seit das Volumen nach Einheit getrennt wurde. Streamlit
ignoriert einen Schluessel, der keine Spalte trifft, wortlos: die
Konfiguration war tot, beide Volumenspalten liefen ohne Beschriftung und ohne
Format durch, und die Kalshi-Stueckzahl stand unbeschriftet neben einem
Dollarbetrag. Faellt eine solche Umbenennung wieder an, soll sie hier
auffallen und nicht erst auf der Seite.

Der Test liest den Quelltext, weil die Tabellen im Streamlit-Monolithen
stehen und nur mit laufender Streamlit-Sitzung aufrufbar waeren. Geprueft
werden nur die Aufrufe, bei denen die Spaltenliste im Quelltext steht
(``clean_table(frame, [...])``, direkt oder ueber genau eine lokale
Zuweisung); alles andere bleibt ausserhalb der Reichweite dieses Tests.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
MONOLITH = WURZEL / "prediction_terminal.py"

#: Aufrufe, die einen Frame nur weiterreichen und die Spalten nicht aendern.
DURCHREICHER = {"head", "copy", "reset_index", "tail", "sort_values"}


def _clean_table_spalten(knoten: ast.AST) -> list[str] | None:
    """Die literale Spaltenliste eines ``clean_table``-Aufrufs, sonst ``None``."""

    while isinstance(knoten, ast.Subscript):
        knoten = knoten.value
    if isinstance(knoten, ast.Call) and isinstance(knoten.func, ast.Attribute) and knoten.func.attr in DURCHREICHER:
        return _clean_table_spalten(knoten.func.value)
    if isinstance(knoten, ast.Call) and isinstance(knoten.func, ast.Name) and knoten.func.id == "clean_table":
        if len(knoten.args) >= 2 and isinstance(knoten.args[1], ast.List):
            spalten: list[str] = []
            for element in knoten.args[1].elts:
                if isinstance(element, ast.Constant) and isinstance(element.value, str):
                    spalten.append(element.value)
                else:
                    return None
            return spalten
    return None


def _basisname(knoten: ast.AST) -> str | None:
    """Der Variablenname, auf dem ein weitergereichter Frame steht."""

    while isinstance(knoten, ast.Subscript):
        knoten = knoten.value
    if isinstance(knoten, ast.Call) and isinstance(knoten.func, ast.Attribute) and knoten.func.attr in DURCHREICHER:
        return _basisname(knoten.func.value)
    if isinstance(knoten, ast.Name):
        return knoten.id
    return None


def _pruefbare_tabellen(quelle: str) -> list[tuple[int, list[str], list[str]]]:
    """(Zeile, Spalten, Konfigurationsschluessel) je pruefbarem ``st.dataframe``."""

    baum = ast.parse(quelle)
    treffer: list[tuple[int, list[str], list[str]]] = []
    gesehen: set[int] = set()
    for rumpf in ast.walk(baum):
        if not isinstance(rumpf, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Module)):
            continue
        # Nur Namen, die in diesem Rumpf genau einmal zugewiesen werden.
        # Ein zweimal beschriebener Name koennte am Aufrufort eine andere
        # Spaltenliste tragen, und dann waere die Pruefung geraten.
        einmalig: dict[str, ast.AST] = {}
        mehrfach: set[str] = set()
        for knoten in ast.walk(rumpf):
            if not isinstance(knoten, ast.Assign):
                continue
            for ziel in knoten.targets:
                if not isinstance(ziel, ast.Name):
                    continue
                if ziel.id in einmalig or ziel.id in mehrfach:
                    mehrfach.add(ziel.id)
                    einmalig.pop(ziel.id, None)
                    continue
                einmalig[ziel.id] = knoten.value
        aufgeloest = {
            name: spalten
            for name, wert in einmalig.items()
            if (spalten := _clean_table_spalten(wert)) is not None
        }

        for knoten in ast.walk(rumpf):
            if not (isinstance(knoten, ast.Call) and isinstance(knoten.func, ast.Attribute)):
                continue
            if knoten.func.attr != "dataframe" or not knoten.args:
                continue
            konfiguration = None
            for schluesselwort in knoten.keywords:
                if schluesselwort.arg == "column_config" and isinstance(schluesselwort.value, ast.Dict):
                    konfiguration = schluesselwort.value
            if konfiguration is None:
                continue
            spalten = _clean_table_spalten(knoten.args[0])
            if spalten is None:
                spalten = aufgeloest.get(_basisname(knoten.args[0]))
            if spalten is None or knoten.lineno in gesehen:
                continue
            gesehen.add(knoten.lineno)
            schluessel = [
                k.value for k in konfiguration.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)
            ]
            treffer.append((knoten.lineno, spalten, schluessel))
    return treffer


class ColumnConfigTreffenSpaltenTests(unittest.TestCase):
    def test_keine_tote_column_config(self) -> None:
        tabellen = _pruefbare_tabellen(MONOLITH.read_text(encoding="utf-8"))
        # Sicherung gegen einen Test, der nichts mehr findet und trotzdem
        # gruen ist: der Monolith fuehrt Dutzende solcher Tabellen.
        self.assertGreater(len(tabellen), 40)
        tot = [
            (zeile, sorted(set(schluessel) - set(spalten)))
            for zeile, spalten, schluessel in tabellen
            if set(schluessel) - set(spalten)
        ]
        self.assertEqual(tot, [], f"column_config nennt Spalten, die der Frame nicht fuehrt: {tot}")

    def test_kalendertabelle_beschriftet_beide_volumeneinheiten(self) -> None:
        """Der konkrete Fall: Dollar und Stueck brauchen je einen Schluessel.

        Ein Tag mit 120000 Dollar Polymarket-Umsatz und 45000 gehandelten
        Kalshi-Kontrakten stand vorher als ``120000.0`` und ``45000.0`` unter
        den rohen Feldnamen da, ohne Einheit und ohne Format.
        """

        tabellen = _pruefbare_tabellen(MONOLITH.read_text(encoding="utf-8"))
        kalender = [
            (spalten, schluessel)
            for _, spalten, schluessel in tabellen
            if "volume_usd" in spalten and "volume_contracts" in spalten
        ]
        self.assertTrue(kalender, "Kalendertabelle nicht gefunden")
        for spalten, schluessel in kalender:
            self.assertIn("volume_usd", schluessel)
            self.assertIn("volume_contracts", schluessel)
            self.assertNotIn("volume", schluessel)


if __name__ == "__main__":
    unittest.main()
