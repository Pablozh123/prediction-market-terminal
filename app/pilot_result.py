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

import math
import statistics
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Mapping

PHASE_LAEUFT = "entry_open"
PHASE_OFFEN = "entry_closed_positions_open"
PHASE_UNGEKLAERT = "entry_closed_outcome_unrecorded"
PHASE_FERTIG = "resolved"

PHASE_TEXT = {
    PHASE_LAEUFT: "Entry window open",
    PHASE_OFFEN: "Entry window closed, positions still open",
    PHASE_UNGEKLAERT: "Entry window closed, outcome not recorded",
    PHASE_FERTIG: "Closed and resolved",
}

#: Fallback fuer die laengste Haltedauer, die das Protokoll zulaesst, wenn die
#: Nutzlast sie nicht mitliefert. Arm 2 nimmt nur Maerkte mit hoechstens 21
#: Tagen Restlaufzeit, also kann keine Position laenger offen sein.
STANDARD_MAX_HALTEDAUER_TAGE = 21.0


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


def _tag(wert: Any) -> date | None:
    """Datum aus einem ISO-Zeitstempel, egal ob mit oder ohne Uhrzeit."""
    text = str(wert or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _spaetester_ausgang(
    trades: list[Mapping[str, Any]], max_haltedauer_tage: float | None
) -> date | None:
    """Der Tag, an dem nach Protokoll keine Position mehr offen sein kann.

    Arm 2 nimmt nur Maerkte mit begrenzter Restlaufzeit und steigt ausschliess-
    lich ueber die Aufloesung aus. Der letzte Eintritt plus diese Frist ist
    damit die Obergrenze, ab der eine leere Exit-Zelle keine offene Position
    mehr beschreibt, sondern ein nicht nachgetragenes Ergebnis.
    """
    tage = STANDARD_MAX_HALTEDAUER_TAGE if max_haltedauer_tage is None else float(max_haltedauer_tage)
    if tage <= 0:
        return None
    eintritte = [d for d in (_tag(t.get("zeitstempel_utc")) for t in trades) if d]
    if not eintritte:
        return None
    return max(eintritte) + timedelta(days=tage)


def _phase(
    trades: list[Mapping[str, Any]],
    fenster_bis: str | None,
    heute: date,
    spaetester_ausgang: date | None = None,
) -> str:
    offen = [t for t in trades if _f(t.get("exit_preis")) is None]
    fenster_zu = False
    if fenster_bis:
        try:
            fenster_zu = heute > date.fromisoformat(str(fenster_bis))
        except ValueError:
            fenster_zu = False
    if not fenster_zu:
        return PHASE_LAEUFT
    if not offen:
        return PHASE_FERTIG
    # Eine leere Exit-Zelle allein heisst "noch offen" nur, solange das
    # Protokoll die Position ueberhaupt noch offen sein laesst. Danach ist sie
    # ein fehlender Eintrag, und "kein Ergebnis behauptet" wuerde einen
    # Verlust genauso aussehen lassen wie eine nicht gepflegte Datei.
    if spaetester_ausgang is not None and heute > spaetester_ausgang:
        return PHASE_UNGEKLAERT
    return PHASE_OFFEN


#: Zweiseitige t-Quantile fuer 95 Prozent, Index = Freiheitsgrade.
_T95 = (12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228,
        2.201, 2.179, 2.160, 2.145, 2.131, 2.120, 2.110, 2.101, 2.093, 2.086,
        2.080, 2.074, 2.069, 2.064, 2.060, 2.056, 2.052, 2.048, 2.045, 2.042)


def _t_quantil(fg: int) -> float:
    if fg <= 0:
        return float("nan")
    return _T95[fg - 1] if fg <= len(_T95) else 1.96


def _slippage(trades: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Reibung zwischen Signalpreis und Ausfuehrungspreis.

    Positiv bedeutet teurer als das Signal. Wo die Zeile die Slippage
    nicht mitliefert, wird sie aus den beiden Preisen gerechnet.

    Der Mittelwert bekommt sein 95-Prozent-Intervall, und ``episoden`` zaehlt
    die verschiedenen Ausfuehrungszeitpunkte. Die beiden Angaben gehoeren
    zusammen: 20 Fills, die alle in derselben Sekunde eines automatisierten
    Laufs entstanden, sind 20 Positionen, aber ein einziger Moment einer
    einzigen Venue. Wer die 20 als 20 unabhaengige Messungen der Reibung liest,
    haelt das Intervall fuer schmaler, als es ist.
    """
    werte: list[float] = []
    zeiten: set[str] = set()
    for t in trades:
        direkt = _f(t.get("slippage"))
        if direkt is not None:
            werte.append(direkt)
        else:
            signal = _f(t.get("signalpreis"))
            ausfuehrung = _f(t.get("ausfuehrungspreis"))
            if signal is None or ausfuehrung is None:
                continue
            werte.append(ausfuehrung - signal)
        stempel = str(t.get("zeitstempel_utc") or "").strip()
        if stempel:
            zeiten.add(stempel)
    if not werte:
        return {"n": 0, "episoden": 0}
    mittel = statistics.mean(werte)
    ergebnis: dict[str, Any] = {
        "n": len(werte),
        # Wie viele verschiedene Momente diese n Fills abdecken.
        "episoden": len(zeiten),
        "mittel": _runde(mittel),
        "median": _runde(statistics.median(werte)),
        "bester": _runde(min(werte)),
        "schlechtester": _runde(max(werte)),
        "teurer_als_signal": sum(1 for w in werte if w > 0),
        "billiger_als_signal": sum(1 for w in werte if w < 0),
        "genau_am_signal": sum(1 for w in werte if w == 0),
        "ci_low": None,
        "ci_high": None,
    }
    if len(werte) >= 2:
        streuung = statistics.stdev(werte)
        halb = _t_quantil(len(werte) - 1) * streuung / math.sqrt(len(werte))
        ergebnis["ci_low"] = _runde(mittel - halb)
        ergebnis["ci_high"] = _runde(mittel + halb)
    return ergebnis


#: Die vorregistrierten Preisbaender je Arm, (Untergrenze, Obergrenze).
#: Arm 1 fadet eine bereits entschiedene Seite und hat deshalb keine
#: Untergrenze; Arm 2 ist das Favoritenband. Wer beide gegen 0.90 bis 0.97
#: prueft, meldet jeden Arm-1-Trade unter 0.90 als Protokollbruch, obwohl das
#: Protokoll ihn ausdruecklich erlaubt.
ARM_BAENDER: dict[str, tuple[float | None, float | None]] = {
    "arm1": (None, 0.97),
    "arm2": (0.90, 0.97),
}


def _baender(watcher: Mapping[str, Any]) -> dict[str, tuple[float | None, float | None]]:
    """Die Baender aus den Watcher-Parametern, sonst die vorregistrierten."""
    baender = dict(ARM_BAENDER)
    arm1_max = _f(watcher.get("arm1_max_entry_preis"))
    if arm1_max is not None:
        baender["arm1"] = (None, arm1_max)
    arm2_min = _f(watcher.get("arm2_min_preis"))
    arm2_max = _f(watcher.get("arm2_max_preis"))
    if arm2_min is not None or arm2_max is not None:
        unten, oben = ARM_BAENDER["arm2"]
        baender["arm2"] = (arm2_min if arm2_min is not None else unten,
                           arm2_max if arm2_max is not None else oben)
    return baender


def _band_text(band: tuple[float | None, float | None]) -> str:
    unten, oben = band
    if unten is None and oben is None:
        return "no band"
    if unten is None:
        return f"at most {oben:g}"
    if oben is None:
        return f"at least {unten:g}"
    return f"{unten:g} to {oben:g}"


def _regeltreue(
    trades: list[Mapping[str, Any]],
    protokoll: Mapping[str, Any],
    watcher: Mapping[str, Any] | None = None,
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

    baender = _baender(watcher or {})
    geprueft = 0
    ausserhalb: list[str] = []
    benutzte_arme: list[str] = []
    for t in trades:
        preis = _f(t.get("signalpreis"))
        if preis is None:
            continue
        arm = str(t.get("arm") or "").strip().lower()
        band = baender.get(arm)
        if band is None:
            # Ein unbekannter Arm hat kein vorregistriertes Band; ihn gegen das
            # Band eines anderen Arms zu pruefen waere eine erfundene Regel.
            continue
        if arm not in benutzte_arme:
            benutzte_arme.append(arm)
        geprueft += 1
        unten, oben = band
        if (unten is not None and preis < unten) or (oben is not None and preis > oben):
            ausserhalb.append(f"{arm} {preis:g}")
    beschreibung = ", ".join(f"{arm} {_band_text(baender[arm])}" for arm in sorted(benutzte_arme))
    punkte.append({
        "regel": f"Signal price inside the pre-registered band of its arm ({beschreibung or 'none used'})",
        "erfuellt": not ausserhalb,
        "ist": f"{geprueft - len(ausserhalb)} of {geprueft} inside",
        "abweichungen": ausserhalb,
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


def _stichprobe_satz(slippage: Mapping[str, Any]) -> str:
    """n, Intervall und die Zahl der Ausfuehrungsmomente hinter dem Mittelwert.

    Zwanzig Fills aus einem einzigen automatisierten Lauf sind zwanzig
    Positionen und ein Moment. Der Satz sagt beides, damit das Intervall nicht
    fuer schmaler gehalten wird, als die Stichprobe hergibt.
    """
    n = int(slippage.get("n") or 0)
    if not n:
        return ""
    teile = [f"{n} fill{'' if n == 1 else 's'}"]
    episoden = int(slippage.get("episoden") or 0)
    if episoden:
        teile.append(
            f"from {episoden} execution moment{'' if episoden == 1 else 's'}"
            + (" — one moment of one venue, not one independent draw per fill"
               if episoden == 1 and n > 1 else "")
        )
    satz = " Measured over " + " ".join(teile)
    tief, hoch = slippage.get("ci_low"), slippage.get("ci_high")
    if tief is not None and hoch is not None:
        satz += f"; 95 percent interval {tief * 100:.2f} to {hoch * 100:.2f} cents"
    return satz + "."


def _befund(slippage: Mapping[str, Any], trades: list[Mapping[str, Any]]) -> str:
    """Der eine Satz, der die bisher belastbare Messung zusammenfasst."""
    if not slippage.get("n"):
        return "No executed trades recorded yet, so there is nothing to measure."
    mittel = slippage.get("mittel") or 0.0
    stichprobe = _stichprobe_satz(slippage)
    ausfuehrungen = _werte(trades, "ausfuehrungspreis")
    if not ausfuehrungen:
        return (
            f"Average slippage was {mittel * 100:.2f} cents against the price that "
            "triggered the rule." + stichprobe
        )
    mittlerer_preis = statistics.mean(ausfuehrungen)
    spielraum = 1.0 - mittlerer_preis
    if spielraum <= 0:
        return (
            f"Average slippage was {mittel * 100:.2f} cents and the average entry "
            "left no upside at all." + stichprobe
        )
    anteil = (mittel / spielraum) * 100.0
    return (
        f"Average slippage was {mittel * 100:.2f} cents. At an average entry of "
        f"{mittlerer_preis:.3f} the whole remaining upside is {spielraum * 100:.2f} "
        f"cents, so execution friction alone consumed {anteil:.0f} percent of it "
        "before the question of being right even comes up." + stichprobe
    )


def evaluate(
    payload: Mapping[str, Any] | None, *, heute: date | None = None
) -> dict[str, Any]:
    """Rechnet die Pilot-Auswertung aus einem geladenen `pilot.json`."""
    if not payload:
        return {}
    trades = [t for t in (payload.get("trades") or []) if isinstance(t, Mapping)]
    protokoll = payload.get("protokoll") or {}
    watcher = payload.get("watcher_parameter") or {}
    tag = heute or datetime.now(timezone.utc).date()

    if not trades:
        leer_phase = _phase([], protokoll.get("handelsfenster_bis"), tag)
        return {
            "phase": leer_phase,
            "phase_text": PHASE_TEXT[leer_phase],
            "trades": {"gesamt": 0},
            "befund": "No trades were recorded in this field test.",
        }

    max_haltedauer = _f(watcher.get("arm2_max_restlaufzeit_tage"))
    spaetester_ausgang = _spaetester_ausgang(trades, max_haltedauer)
    phase = _phase(trades, protokoll.get("handelsfenster_bis"), tag, spaetester_ausgang)
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
        "regeltreue": _regeltreue(trades, protokoll, watcher),
        "befund": _befund(slippage, trades),
        # Was hier gemessen wird und was nicht. Ohne diese Trennung liest sich
        # die Slippage-Zahl als das Ergebnis des Tests, und der Test war nach
        # seinem eigenen Protokollkopf auf den Ausgang der Positionen angelegt.
        "endpunkte": {
            "gemessen": "execution friction: signal price against fill price",
            "offen": "the settled outcome of the positions, which the protocol reaches only through resolution",
            "protokoll_quelle": str(protokoll.get("quelle") or "not stated"),
            "spaetester_ausgang": spaetester_ausgang.isoformat() if spaetester_ausgang else None,
        },
    }
    if phase == PHASE_OFFEN:
        ergebnis["offener_ausgang"] = (
            f"{len(offen)} of {len(trades)} positions are still open. Arm 2 exits only "
            "through resolution, so the profit or loss of this test is not known yet "
            "and no result is claimed here."
        )
    elif phase == PHASE_UNGEKLAERT:
        frist = spaetester_ausgang.isoformat() if spaetester_ausgang else "the protocol horizon"
        ergebnis["offener_ausgang"] = (
            f"{len(offen)} of {len(trades)} positions carry no exit, but under the protocol "
            f"none of them can still be open after {frist}. The outcome of this test was "
            "not written back, so it is unknown rather than pending, and a loss would look "
            "exactly like this."
        )
    return ergebnis
