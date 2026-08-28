"""Pure copy-desk helpers extracted from prediction_terminal.

Neben der Frage, welche Wallet als gefolgt gilt, stehen hier die zwei
Rechnungen, die beide Oberflaechen des Copy-Desks teilen muessen, damit sie
nicht auseinanderlaufen: die Aufteilung des Ergebnisses in gebucht und
bewertet (``pnl_split``) und der Anteil tatsaechlich gespiegelter Orders
(``mirror_coverage``). Beide sind reine Funktionen ueber Zahlen; wo die
Zahlen herkommen, entscheidet der Aufrufer.
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from app.filters import bool_mask
from src import prediction_markets as md

#: Toleranz, ab der Equity minus Einzahlungen und die Summe der beiden
#: Haelften als verschieden gelten. Beides sind Dollarbetraege aus derselben
#: Datenbank, ein Cent Rundung ist Rauschen, ein Dollar ist ein Befund.
PNL_RECONCILE_TOLERANCE_USD = 0.01


def active_wallet_set(traders: pd.DataFrame | None) -> set[str]:
    if traders is None or traders.empty or "wallet" not in traders:
        return set()
    active = bool_mask(traders.get("active", pd.Series(False, index=traders.index)), False)
    wallets = (str(wallet).strip().lower() for wallet in traders.loc[active, "wallet"].tolist())
    return {wallet for wallet in wallets if md.is_polymarket_wallet(wallet)}


def stats_by_wallet(stats: pd.DataFrame | None) -> dict[str, pd.Series]:
    if stats is None or stats.empty or "wallet" not in stats:
        return {}
    return {str(row.get("wallet", "") or "").strip().lower(): row for _, row in stats.iterrows()}


def status_label(wallet: Any, active_wallets: set[str]) -> str:
    return "Following" if str(wallet or "").strip().lower() in active_wallets else ""


def _f(value: Any, default: float = 0.0) -> float:
    try:
        zahl = float(value)
    except (TypeError, ValueError):
        return default
    return default if zahl != zahl else zahl


def pnl_split(
    *,
    contributions: Any,
    realized_pnl: Any,
    unrealized_pnl: Any,
    equity: Any = None,
) -> dict[str, Any]:
    """Ergebnis des Papierkontos in gebucht und bewertet, mit einem Nenner.

    Warum getrennt: ``equity - contributions`` ist eine Zahl, in der zwei
    verschiedene Dinge stecken. Der gebuchte Teil ist Geld, das eine
    Aufloesung oder ein Verkauf tatsaechlich zurueckgegeben hat. Der
    bewertete Teil ist eine Marke auf Positionen, die noch nichts
    entschieden haben, und im Standardpfad des Papierbuchs ist diese Marke
    der zuletzt gedruckte Preis der Quelle, kein Marktkurs. Beides unter
    einer Schlagzeile zu addieren laesst einen Tisch, der gebucht im Minus
    steht, als Gewinner dastehen.

    Der Nenner ist fuer beide Haelften dasselbe eingezahlte Kapital (Startgeld
    plus jede Nachzahlung). Genau deshalb addieren sich die beiden
    Prozentwerte zur Gesamtzahl. Ein Zaehler ueber die aufgeloesten
    Positionen und ein Nenner ueber alle waere die naechste Fassung
    desselben Fehlers.

    Ohne eingezahltes Kapital gibt es keinen Prozentwert, sondern ``None``:
    die frueheren 0,0 Prozent lasen sich wie eine gemessene Null.

    ``reconciles`` prueft die Buchhaltung: Equity minus Einzahlungen muss
    gebucht plus bewertet ergeben. Stimmt das nicht, ist die Aufteilung
    keine Aufteilung, und die Oberflaeche darf sie nicht als eine zeigen.
    """

    basis = _f(contributions)
    gebucht = _f(realized_pnl)
    bewertet = _f(unrealized_pnl)
    summe = gebucht + bewertet
    gesamt = summe if equity is None else _f(equity) - basis
    residual = gesamt - summe

    def anteil(betrag: float) -> float | None:
        return (betrag / basis * 100.0) if basis > 0 else None

    return {
        "contributions": basis,
        "denominator": "contributions",
        "settled_pnl": gebucht,
        "open_pnl": bewertet,
        "total_pnl": gesamt,
        "settled_pct": anteil(gebucht),
        "open_pct": anteil(bewertet),
        "total_pct": anteil(gesamt),
        "reconciles": abs(residual) <= PNL_RECONCILE_TOLERANCE_USD,
        "residual": residual,
    }


def mirror_coverage(
    *,
    copied: Any,
    settled: Any,
    skipped: Any,
    observed: Any = 0,
) -> dict[str, Any]:
    """Anteil gespiegelter Orders, Zaehler und Nenner ueber derselben Menge.

    Eine kopierte Order wechselt beim Aufloesen den Status von ``copied`` auf
    ``settled``. Zaehlte der Zaehler nur ``copied``, fiel sie damit heraus
    und blieb im Nenner stehen: derselbe Tisch sah mit jeder Aufloesung
    schlechter aus, ohne dass sich an der Spiegelung etwas geaendert haette.

    Die Baseline-Zeilen (``seed_observed``) stehen ausserhalb des Nenners.
    Sie sind der Bestand, den die Quelle beim Anlegen schon hielt; es war
    nie zu entscheiden, ob sie gespiegelt werden. Sie kommen als eigene Zahl
    zurueck, damit sie nicht verschwiegen sind.

    Nichts zu entscheiden ist nicht hundert Prozent: dann ``None``.
    """

    kopiert = int(_f(copied))
    aufgeloest = int(_f(settled))
    uebersprungen = int(_f(skipped))
    beobachtet = int(_f(observed))
    gespiegelt = kopiert + aufgeloest
    entscheidbar = gespiegelt + uebersprungen
    return {
        "mirrored": gespiegelt,
        "actionable": entscheidbar,
        "observed": beobachtet,
        "skipped": uebersprungen,
        "coverage_pct": (gespiegelt / entscheidbar * 100.0) if entscheidbar else None,
    }


def safe_key(*parts: Any, limit: int = 90) -> str:
    text = "_".join(str(part or "") for part in parts)
    return re.sub(r"[^a-zA-Z0-9_]", "_", text)[:limit]
