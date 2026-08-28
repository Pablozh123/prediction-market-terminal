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
from typing import NamedTuple

WURZEL = Path(__file__).resolve().parents[1]
MONOLITH = WURZEL / "prediction_terminal.py"

#: Aufrufe, die einen Frame nur weiterreichen und die Spalten nicht aendern.
DURCHREICHER = {"head", "copy", "reset_index", "tail", "sort_values"}


def _stringliste(knoten: ast.AST) -> list[str] | None:
    """Eine Liste aus lauter String-Literalen, sonst ``None``."""

    if not isinstance(knoten, ast.List):
        return None
    spalten: list[str] = []
    for element in knoten.elts:
        if isinstance(element, ast.Constant) and isinstance(element.value, str):
            spalten.append(element.value)
        else:
            return None
    return spalten


def _clean_table_spalten(knoten: ast.AST, listen: dict[str, list[str]] | None = None) -> list[str] | None:
    """Die Spaltenliste eines ``clean_table``-Aufrufs, sonst ``None``.

    Die Liste steht entweder direkt im Aufruf oder auf einem Namen, der im
    selben Rumpf genau einmal mit einer Literalliste belegt wird.
    """

    listen = listen or {}
    while isinstance(knoten, ast.Subscript):
        knoten = knoten.value
    if isinstance(knoten, ast.Call) and isinstance(knoten.func, ast.Attribute) and knoten.func.attr in DURCHREICHER:
        return _clean_table_spalten(knoten.func.value, listen)
    if isinstance(knoten, ast.Call) and isinstance(knoten.func, ast.Name) and knoten.func.id == "clean_table":
        if len(knoten.args) < 2:
            return None
        direkt = _stringliste(knoten.args[1])
        if direkt is not None:
            return direkt
        if isinstance(knoten.args[1], ast.Name):
            return listen.get(knoten.args[1].id)
    return None


def _config_schluessel(knoten: ast.AST, dicts: dict[str, ast.Dict]) -> list[str] | None:
    """Die String-Schluessel einer ``column_config``, auch ueber Namen und ``**``.

    Die Signaltabellen teilen sich eine Konfiguration (``signal_config``) und
    erweitern sie stellenweise per ``{**signal_config, ...}``. Ohne diese
    Aufloesung faellt genau die Tabellengruppe aus der Pruefung, um die es
    geht.
    """

    if isinstance(knoten, ast.Name):
        geteilt = dicts.get(knoten.id)
        return _config_schluessel(geteilt, dicts) if geteilt is not None else None
    if not isinstance(knoten, ast.Dict):
        return None
    schluessel: list[str] = []
    for name, wert in zip(knoten.keys, knoten.values):
        if name is None:  # {**andere}
            geerbt = _config_schluessel(wert, dicts)
            if geerbt is None:
                return None
            schluessel.extend(geerbt)
        elif isinstance(name, ast.Constant) and isinstance(name.value, str):
            schluessel.append(name.value)
    return schluessel


def _basisname(knoten: ast.AST) -> str | None:
    """Der Variablenname, auf dem ein weitergereichter Frame steht."""

    while isinstance(knoten, ast.Subscript):
        knoten = knoten.value
    if isinstance(knoten, ast.Call) and isinstance(knoten.func, ast.Attribute) and knoten.func.attr in DURCHREICHER:
        return _basisname(knoten.func.value)
    if isinstance(knoten, ast.Name):
        return knoten.id
    return None


class Tabelle(NamedTuple):
    """Ein ``st.dataframe``-Aufruf, dessen Spaltenliste im Quelltext steht."""

    zeile: int
    spalten: list[str]
    schluessel: list[str]
    #: Der Ausdruck, der den Frame liefert, als Quelltext.
    quelle: str


def _pruefbare_tabellen(quelle: str) -> list[Tabelle]:
    """Je pruefbarem ``st.dataframe`` ein ``Tabelle``-Eintrag."""

    baum = ast.parse(quelle)
    treffer: list[Tabelle] = []
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
        listen = {
            name: spalten
            for name, wert in einmalig.items()
            if (spalten := _stringliste(wert)) is not None
        }
        aufgeloest = {
            name: spalten
            for name, wert in einmalig.items()
            if (spalten := _clean_table_spalten(wert, listen)) is not None
        }
        dicts = {name: wert for name, wert in einmalig.items() if isinstance(wert, ast.Dict)}

        for knoten in ast.walk(rumpf):
            if not (isinstance(knoten, ast.Call) and isinstance(knoten.func, ast.Attribute)):
                continue
            if knoten.func.attr != "dataframe" or not knoten.args:
                continue
            schluessel = None
            for schluesselwort in knoten.keywords:
                if schluesselwort.arg == "column_config":
                    schluessel = _config_schluessel(schluesselwort.value, dicts)
            if schluessel is None:
                continue
            spalten = _clean_table_spalten(knoten.args[0], listen)
            if spalten is None:
                spalten = aufgeloest.get(_basisname(knoten.args[0]))
            if spalten is None or knoten.lineno in gesehen:
                continue
            gesehen.add(knoten.lineno)
            treffer.append(
                Tabelle(knoten.lineno, spalten, schluessel, ast.get_source_segment(quelle, knoten.args[0]) or "")
            )
    return treffer


class ColumnConfigTreffenSpaltenTests(unittest.TestCase):
    def test_keine_tote_column_config(self) -> None:
        tabellen = _pruefbare_tabellen(MONOLITH.read_text(encoding="utf-8"))
        # Sicherung gegen einen Test, der nichts mehr findet und trotzdem
        # gruen ist: der Monolith fuehrt Dutzende solcher Tabellen.
        self.assertGreater(len(tabellen), 40)
        tot = [
            (t.zeile, sorted(set(t.schluessel) - set(t.spalten)))
            for t in tabellen
            if set(t.schluessel) - set(t.spalten)
        ]
        self.assertEqual(tot, [], f"column_config nennt Spalten, die der Frame nicht fuehrt: {tot}")

    def test_kalendertabelle_beschriftet_beide_volumeneinheiten(self) -> None:
        """Der konkrete Fall: Dollar und Stueck brauchen je einen Schluessel.

        Ein Tag mit 120000 Dollar Polymarket-Umsatz und 45000 gehandelten
        Kalshi-Kontrakten stand vorher als ``120000.0`` und ``45000.0`` unter
        den rohen Feldnamen da, ohne Einheit und ohne Format.
        """

        tabellen = _pruefbare_tabellen(MONOLITH.read_text(encoding="utf-8"))
        kalender = [t for t in tabellen if "volume_usd" in t.spalten and "volume_contracts" in t.spalten]
        self.assertTrue(kalender, "Kalendertabelle nicht gefunden")
        for tabelle in kalender:
            self.assertIn("volume_usd", tabelle.schluessel)
            self.assertIn("volume_contracts", tabelle.schluessel)
            self.assertNotIn("volume", tabelle.schluessel)


class SignalWertSpalteTests(unittest.TestCase):
    """Die ``value``-Spalte der Signaltabellen liest die geteilte Regel.

    Sie fuehrt je Signalart eine andere Groesse. Unter ``%.4f`` standen 62
    Prozent Halteranteil (0.6200), 3.5 Cent Bewegung (0.0350), das 4.7-fache
    Tagesvolumen (4.7000) und 12500 Dollar (12500.0000) im selben Format
    untereinander. Der Signal-Feed im Web loest das seit #111 ueber
    ``api_views.signal_value_label`` auf; der Monolith tat es nicht.
    """

    def test_der_monolith_beschriftet_statt_vier_nachkommastellen(self) -> None:
        quelle = MONOLITH.read_text(encoding="utf-8")
        self.assertIn("apv.signal_value_series(", quelle)
        self.assertNotIn('"value": st.column_config.NumberColumn(format="%.4f")', quelle)

    def test_jede_signaltabelle_laeuft_durch_die_etikettierung(self) -> None:
        """Kein ``st.dataframe`` zeigt ``value`` neben ``signal_type`` roh."""

        tabellen = _pruefbare_tabellen(MONOLITH.read_text(encoding="utf-8"))
        signaltabellen = [t for t in tabellen if "signal_type" in t.spalten and "value" in t.spalten]
        self.assertTrue(signaltabellen, "keine Signaltabelle gefunden")
        for tabelle in signaltabellen:
            self.assertIn("value", tabelle.schluessel, f"Zeile {tabelle.zeile}: value ohne Konfiguration")
            self.assertIn(
                "signal_value_labels(",
                tabelle.quelle,
                f"Zeile {tabelle.zeile}: value ohne Einheit, der Frame laeuft nicht durch signal_value_labels",
            )

    def test_der_signal_feed_reicht_jede_art_durch(self) -> None:
        """Alle Tabellen von page_monitor haengen an derselben Etikettierung.

        Die Tabs Signal Feed und Alert Hits reichen ihren Frame ueber eine
        mehrfach belegte Variable weiter, also greift die AST-Pruefung dort
        nicht. Gezaehlt wird deshalb am Quelltext.
        """

        quelle = MONOLITH.read_text(encoding="utf-8")
        # Sieben Anzeigen lesen die Signalspalte: Suche (zwei), Signal Feed,
        # Alert Hits, Fast Movers, Tight Spreads, Holder Risk, Ending Soon.
        self.assertGreaterEqual(quelle.count("signal_value_labels("), 8)


if __name__ == "__main__":
    unittest.main()
