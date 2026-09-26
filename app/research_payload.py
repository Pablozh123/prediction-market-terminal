"""Gemeinsame Bausteine der Forschungs-Nutzlasten fuer die Website.

Vier Studienseiten lesen ihre Zahlen aus je einem Artefakt (CSV, JSON oder
Markdown) und schreiben eine Datei nach ``public/data``: die Ergebnisse der
Bachelorarbeit (``app/thesis_results.py``), die Reddit-Sentiment-Studie
(``app/reddit_report.py``), das Preregistrierungs-Register
(``app/prereg_register.py``) und die Einordnung gegen die Literatur
(``app/literature_context.py``). Was sie teilen, steht hier: das Lesen von
CSV-Dateien, die Bausteine ``zahl`` und ``tabelle`` in genau der Form, die
``web/js/pages/study_blocks.js`` rendert, und die Pruefung, dass keine
Wallet-Adresse in eine Nutzlast geraet.

Der Grundsatz ist derselbe wie in ``app/microstructure_report.py``: Prosa ist
kuratiert, Zahlen niemals. Jede Zahl im Fliesstext wird zur Laufzeit aus
dem Artefakt gelesen und in eine Vorlage eingesetzt.

Streamlit-frei nach Projektkonvention.
"""

from __future__ import annotations

import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

# Verdikt-Arten, gemeinsam fuer alle Seiten. Die Oberflaeche faerbt danach.
VERDIKT_JA = "ja"                # gemessen und gestuetzt
VERDIKT_NEIN = "nein"            # gemessen und nicht gestuetzt
VERDIKT_OFFEN = "offen"          # nicht identifiziert, bewusst kein Urteil
VERDIKT_GEMISCHT = "gemischt"    # gestuetzt in einem Ausschnitt, nicht im Ganzen
VERDIKT_KONTROLLE = "kontrolle"  # Pruefung der Messkette, kein Marktbefund
VERDIKT_ARTEN = (VERDIKT_JA, VERDIKT_NEIN, VERDIKT_OFFEN, VERDIKT_GEMISCHT, VERDIKT_KONTROLLE)

# Arten der Interpretation, in Anzeigereihenfolge.
LESART = "lesart"
GEGENLESART = "gegenlesart"
GRENZE = "grenze"
INTERPRET_TITEL = {
    LESART: "What it suggests",
    GEGENLESART: "What else fits the same numbers",
    GRENZE: "What this cannot tell you",
}
ANALYSE_TITEL = {
    "gemessen": "What was measured",
    "wie": "How",
    "daten": "On which data",
    "entscheidung": "What would have counted as evidence",
}

#: Eine Wallet-Adresse: 0x plus vierzig Hex-Zeichen. Nichts davon darf in
#: eine veroeffentlichte Nutzlast, gleich aus welcher Quelle.
WALLET_MUSTER = re.compile(r"0x[0-9a-fA-F]{40}")


def jetzt_iso(jetzt: datetime | None = None) -> str:
    return (jetzt or datetime.now(timezone.utc)).isoformat()


def lies_csv(pfad: Path) -> list[dict[str, str]]:
    """Alle Zeilen einer CSV-Datei als Woerterbuecher (Strings, unveraendert)."""
    with pfad.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def lies_json(pfad: Path) -> Any:
    with pfad.open(encoding="utf-8") as fh:
        return json.load(fh)


def lies_text(pfad: Path) -> str:
    return pfad.read_text(encoding="utf-8")


def zahl_aus(wert: Any, standard: float | None = None) -> float | None:
    """Ein CSV-Feld als Zahl, oder ``standard`` wenn es keine ist."""
    if wert is None:
        return standard
    text = str(wert).strip()
    if not text:
        return standard
    try:
        return float(text)
    except ValueError:
        return standard


def n_text(wert: Any) -> str:
    """Tausenderpunkte fuer den Fliesstext: 205835 -> '205,835'."""
    try:
        return f"{int(round(float(wert))):,}"
    except (TypeError, ValueError):
        return str(wert)


def prozent(anteil: float, stellen: int = 1) -> str:
    """0.5523 -> '55.2' (ohne Prozentzeichen, das setzt der Satz)."""
    return f"{float(anteil) * 100:.{stellen}f}"


def pp(delta: float, stellen: int = 1) -> str:
    """Eine Differenz in Prozentpunkten mit Vorzeichen: 0.0719 -> '+7.2'."""
    return f"{float(delta) * 100:+.{stellen}f}"


def p_text(p: float) -> str:
    """Ein p-Wert, wie er in einem Satz stehen kann."""
    p = float(p)
    if p < 1e-4:
        return f"{p:.1e}"
    return f"{p:.4f}".rstrip("0").rstrip(".") if p < 0.01 else f"{p:.3f}"


def zahl(label: str, wert: Any, einheit: str = "", hinweis: str = "") -> dict[str, Any]:
    """Eine Kennzahlzeile fuer den Zahlenblock der Karte."""
    eintrag: dict[str, Any] = {"label": label, "wert": wert}
    if einheit:
        eintrag["einheit"] = einheit
    if hinweis:
        eintrag["hinweis"] = hinweis
    return eintrag


def tabelle(titel: str, spalten: list[str], zeilen: Iterable[Iterable[Any]], hinweis: str = "") -> dict[str, Any]:
    """Eine Detailtabelle; die erste Spalte ist Text, die uebrigen rechtsbuendig."""
    return {
        "titel": titel,
        "spalten": list(spalten),
        "zeilen": [list(z) for z in zeilen],
        "hinweis": hinweis,
    }


def interpretation(*paare: tuple[str, str]) -> list[dict[str, str]]:
    """Lesart, Gegenlesart, Grenze als Liste in Anzeigeform."""
    return [{"art": art, "titel": INTERPRET_TITEL[art], "text": text} for art, text in paare]


def analyse(**felder: str) -> list[dict[str, str]]:
    """Die vier Analysefelder in fester Reihenfolge; leere fallen weg."""
    return [
        {"schluessel": k, "titel": ANALYSE_TITEL[k], "text": felder[k]}
        for k in ("gemessen", "wie", "daten", "entscheidung")
        if felder.get(k)
    ]


def wallet_adressen_in(nutzlast: Any) -> list[str]:
    """Alle Wallet-Adressen, die in der serialisierten Nutzlast stehen."""
    text = json.dumps(nutzlast, ensure_ascii=False)
    return sorted(set(WALLET_MUSTER.findall(text)))


def pruefe_redaktion(nutzlast: Any) -> None:
    """Bricht ab, wenn eine Wallet-Adresse in der Nutzlast steht.

    Die Thesis-Tabellen fuehren Wallets im Klartext (``h3_wallet_tiers.csv``);
    die Website zeigt Zaehlungen, nie Adressen. Die Pruefung laeuft ueber die
    fertige Nutzlast, nicht ueber einzelne Felder, damit auch ein Umweg
    ueber einen Hinweistext auffaellt.
    """
    treffer = wallet_adressen_in(nutzlast)
    if treffer:
        raise ValueError(f"Wallet-Adresse in der Nutzlast: {treffer[0]} (+{len(treffer) - 1} weitere)")


def schreibe_nutzlast(pfad: Path, nutzlast: dict[str, Any]) -> None:
    """Schreibt die Nutzlast nach Redaktionspruefung, atomar ueber eine Temp-Datei."""
    pruefe_redaktion(nutzlast)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    tmp = pfad.with_suffix(pfad.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(nutzlast, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    tmp.replace(pfad)


def pearson(xs: list[float], ys: list[float]) -> float | None:
    """Pearson-Korrelation ohne Abhaengigkeiten; None unter drei Paaren."""
    n = len(xs)
    if n < 3 or n != len(ys):
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / (sxx * syy) ** 0.5


def raenge(werte: list[float]) -> list[float]:
    """Durchschnittsraenge (1-basiert), Bindungen gemittelt wie bei Spearman."""
    sortiert = sorted(range(len(werte)), key=lambda i: werte[i])
    raenge_aus: list[float] = [0.0] * len(werte)
    i = 0
    while i < len(sortiert):
        j = i
        while j + 1 < len(sortiert) and werte[sortiert[j + 1]] == werte[sortiert[i]]:
            j += 1
        mittel = (i + j) / 2 + 1
        for k in range(i, j + 1):
            raenge_aus[sortiert[k]] = mittel
        i = j + 1
    return raenge_aus


def spearman(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    return pearson(raenge(xs), raenge(ys))
