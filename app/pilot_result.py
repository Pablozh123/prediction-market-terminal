"""Endauswertung des vorregistrierten Pilot-Feldtests.

`public/data/pilot.json` traegt die Rohzeilen aus `trades.csv` und den
Protokollkopf, aber keine Auswertung. Dieses Modul rechnet sie zur
Anzeigezeit aus genau diesen Zeilen, damit ein neu publiziertes
`pilot.json` die Auswertung nicht ueberschreibt und die Trades die
einzige Wahrheit bleiben.

Zwei Dinge werden bewusst getrennt gehalten:

* Das Eintrittsfenster ist beendet, sobald `handelsfenster_bis` vorbei
  ist. Danach kommen keine neuen Positionen mehr dazu.
* Der Ausgang steht damit noch nicht fest. Arm 2 steigt laut Protokoll
  nur ueber die Aufloesung aus, offene Positionen bleiben offen.

Was jetzt schon messbar ist, ist die Reibung: der Abstand zwischen dem
Preis, bei dem die Regel ausgeloest hat, und dem Preis, zu dem
tatsaechlich ausgefuehrt wurde. Genau dafuer wurde der Test gebaut.

Streamlit-frei nach Projektkonvention.
"""

from __future__ import annotations

import statistics
from datetime import date, datetime, timezone
from typing import Any, Iterable, Mapping

PHASE_LAEUFT = "entry_open"
PHASE_OFFEN = "entry_closed_positions_open"
PHASE_FERTIG = "resolved"

PHASE_TEXT = {
    PHASE_LAEUFT: "Entry window open",
    PHASE_OFFEN: "Entry window closed, positions still open",
    PHASE_FERTIG: "Closed and resolved",
}


def _f(wert: Any) -> float | None:
    """Zahl aus einer CSV-Zelle, leere und kaputte Zellen werden None."""
    if wert is None:
        return None
    text = str(wert).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _werte(zeilen: Iterable[Mapping[str, Any]], feld: str) -> list[float]:
    return [w for w in (_f(z.get(feld)) for z in zeilen) if w is not None]


def _runde(wert: float | None, stellen: int = 4) -> float | None:
    return None if wert is None else round(wert, stellen)


def _phase(trades: list[Mapping[str, Any]], fenster_bis: str | None, heute: date) -> str:
    offen = [t for t in trades if _f(t.get("exit_preis")) is None]
    fenster_zu = False
    if fenster_bis:
        try:
            fenster_zu = heute > date.fromisoformat(str(fenster_bis))
        except ValueError:
            fenster_zu = False
    if not fenster_zu:
        return PHASE_LAEUFT
    return PHASE_OFFEN if offen else PHASE_FERTIG


def _slippage(trades: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Reibung zwischen Signalpreis und Ausfuehrungspreis.

    Positiv bedeutet teurer als das Signal. Wo die Zeile die Slippage
    nicht mitliefert, wird sie aus den beiden Preisen gerechnet.
    """
    werte: list[float] = []
    for t in trades:
        direkt = _f(t.get("slippage"))
        if direkt is not None:
            werte.append(direkt)
            continue
        signal = _f(t.get("signalpreis"))
        ausfuehrung = _f(t.get("ausfuehrungspreis"))
        if signal is not None and ausfuehrung is not None:
            werte.append(ausfuehrung - signal)
    if not werte:
        return {"n": 0}
    return {
        "n": len(werte),
        "mittel": _runde(statistics.mean(werte)),
        "median": _runde(statistics.median(werte)),
        "bester": _runde(min(werte)),
        "schlechtester": _runde(max(werte)),
        "teurer_als_signal": sum(1 for w in werte if w > 0),
        "billiger_als_signal": sum(1 for w in werte if w < 0),
        "genau_am_signal": sum(1 for w in werte if w == 0),
    }


def _regeltreue(
    trades: list[Mapping[str, Any]], protokoll: Mapping[str, Any]
) -> dict[str, Any]:
    """Prueft die Trades gegen den eingefrorenen Protokollkopf.

    Abweichungen werden ausgewiesen, nicht geglaettet. Eine bestandene
    Pruefung ohne Gegenprobe waere wertlos.
    """
    punkte: list[dict[str, Any]] = []

    regeln = {str(t.get("signal_regel") or "").strip() for t in trades if t.get("signal_regel")}
    punkte.append({
        "regel": "Every trade cites the frozen signal rule",
        "erfuellt": len(regeln) == 1 and bool(regeln),
        "ist": ", ".join(sorted(regeln)) or "none",
    })

    preise = _werte(trades, "signalpreis")
    ausserhalb = [p for p in preise if not 0.90 <= p <= 0.97]
    punkte.append({
        "regel": "Signal price inside the pre-registered 0.90 to 0.97 band",
        "erfuellt": not ausserhalb,
        "ist": f"{len(preise) - len(ausserhalb)} of {len(preise)} inside",
    })

    soll_einsatz = _f(protokoll.get("einsatz_je_trade_usdc"))
    einsaetze = _werte(trades, "groesse_usd")
    abweichend = (
        [e for e in einsaetze if abs(e - soll_einsatz) > 1e-9] if soll_einsatz else []
    )
    punkt: dict[str, Any] = {
        "regel": "Stake per trade matches the protocol",
        "erfuellt": bool(einsaetze) and not abweichend,
        "ist": (
            f"{_runde(statistics.median(einsaetze), 2)} USDC actual"
            if einsaetze else "no stake recorded"
        ),
        "soll": f"{soll_einsatz} USDC" if soll_einsatz else "not stated",
    }
    if abweichend and soll_einsatz:
        punkt["hinweis"] = (
            "Stake was halved against the written protocol. The budget still "
            "holds, so this bought twice the sample instead of twice the size. "
            "It is a deviation from the frozen text and is reported as one."
        )
    punkte.append(punkt)

    budget = _f(protokoll.get("budget_usdc"))
    eingesetzt = sum(einsaetze)
    punkte.append({
        "regel": "Capital deployed stays inside the budget",
        "erfuellt": budget is None or eingesetzt <= budget + 1e-9,
        "ist": f"{_runde(eingesetzt, 2)} USDC deployed",
        "soll": f"{budget} USDC budget" if budget else "not stated",
    })

    return {
        "punkte": punkte,
        "erfuellt": sum(1 for p in punkte if p["erfuellt"]),
        "gesamt": len(punkte),
    }


def _befund(slippage: Mapping[str, Any], trades: list[Mapping[str, Any]]) -> str:
    """Der eine Satz, der die bisher belastbare Messung zusammenfasst."""
    if not slippage.get("n"):
        return "No executed trades recorded yet, so there is nothing to measure."
    mittel = slippage.get("mittel") or 0.0
    ausfuehrungen = _werte(trades, "ausfuehrungspreis")
    if not ausfuehrungen:
        return (
            f"Average slippage was {mittel * 100:.2f} cents against the price that "
            "triggered the rule."
        )
    mittlerer_preis = statistics.mean(ausfuehrungen)
    spielraum = 1.0 - mittlerer_preis
    if spielraum <= 0:
        return (
            f"Average slippage was {mittel * 100:.2f} cents and the average entry "
            "left no upside at all."
        )
    anteil = (mittel / spielraum) * 100.0
    return (
        f"Average slippage was {mittel * 100:.2f} cents. At an average entry of "
        f"{mittlerer_preis:.3f} the whole remaining upside is {spielraum * 100:.2f} "
        f"cents, so execution friction alone consumed {anteil:.0f} percent of it "
        "before the question of being right even comes up."
    )


def evaluate(
    payload: Mapping[str, Any] | None, *, heute: date | None = None
) -> dict[str, Any]:
    """Rechnet die Pilot-Auswertung aus einem geladenen `pilot.json`."""
    if not payload:
        return {}
    trades = [t for t in (payload.get("trades") or []) if isinstance(t, Mapping)]
    protokoll = payload.get("protokoll") or {}
    tag = heute or datetime.now(timezone.utc).date()

    if not trades:
        return {
            "phase": _phase([], protokoll.get("handelsfenster_bis"), tag),
            "phase_text": PHASE_TEXT[_phase([], protokoll.get("handelsfenster_bis"), tag)],
            "trades": {"gesamt": 0},
            "befund": "No trades were recorded in this field test.",
        }

    phase = _phase(trades, protokoll.get("handelsfenster_bis"), tag)
    offen = [t for t in trades if _f(t.get("exit_preis")) is None]
    geschlossen = [t for t in trades if _f(t.get("exit_preis")) is not None]
    arme: dict[str, int] = {}
    for t in trades:
        arm = str(t.get("arm") or "unknown")
        arme[arm] = arme.get(arm, 0) + 1

    einsaetze = _werte(trades, "groesse_usd")
    tiefen = _werte(trades, "orderbuchtiefe_einstieg_usd")
    signale = _werte(trades, "signalpreis")
    ausfuehrungen = _werte(trades, "ausfuehrungspreis")
    slippage = _slippage(trades)

    ergebnis: dict[str, Any] = {
        "phase": phase,
        "phase_text": PHASE_TEXT[phase],
        "fenster_bis": protokoll.get("handelsfenster_bis"),
        "regel_freeze": protokoll.get("regel_freeze_datum"),
        "trades": {
            "gesamt": len(trades),
            "offen": len(offen),
            "geschlossen": len(geschlossen),
            "je_arm": arme,
            "kapital_usd": _runde(sum(einsaetze), 2),
            "erster": min((str(t.get("zeitstempel_utc") or "") for t in trades), default=""),
            "letzter": max((str(t.get("zeitstempel_utc") or "") for t in trades), default=""),
        },
        "preise": {
            "signal_mittel": _runde(statistics.mean(signale)) if signale else None,
            "ausfuehrung_mittel": _runde(statistics.mean(ausfuehrungen)) if ausfuehrungen else None,
            "buchtiefe_median_usd": _runde(statistics.median(tiefen), 2) if tiefen else None,
            "buchtiefe_min_usd": _runde(min(tiefen), 2) if tiefen else None,
        },
        "slippage": slippage,
        "regeltreue": _regeltreue(trades, protokoll),
        "befund": _befund(slippage, trades),
    }
    if phase == PHASE_OFFEN:
        ergebnis["offener_ausgang"] = (
            f"{len(offen)} of {len(trades)} positions are still open. Arm 2 exits only "
            "through resolution, so the profit or loss of this test is not known yet "
            "and no result is claimed here."
        )
    return ergebnis
