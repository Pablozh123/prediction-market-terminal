"""Verdict-first wallet report card: state machine, diagnosis and copy read.

Streamlit-free logic behind ``render_report_card`` in the terminal. Consumes
exclusively the canonical wallet scorecard (``app/scorecard.py``) plus one
short backtest result — never the underlying scoring systems directly.

Verdict states, checked in this fixed priority order:

1. ``flagged``       — insider screen high or wash/farm pattern; the status
                       names the flag, no skill judgement is offered.
2. ``insufficient``  — no verdict possible: sample below the gates, feed cap
                       (extremes-only), or no resolved positions at all.
3. ``luck_range``    — verdict allowed, but the 95% CI includes zero.
4. ``skilled_read``  — verdict allowed and the CI clears zero upward; worded
                       as a description of the past record, never a forecast.

``negative_read`` extends the brief's four states for a CI entirely below
zero: filing a demonstrably negative record under "luck" would be wrong.

Every template is claims-register-conform (data/claims.yaml); the tests lint
each one against the forbidden-phrase list.
"""

from __future__ import annotations

from typing import Any, Mapping

STATE_FLAGGED = "flagged"
STATE_INSUFFICIENT = "insufficient"
STATE_LUCK_RANGE = "luck_range"
STATE_SKILLED_READ = "skilled_read"
STATE_NEGATIVE_READ = "negative_read"

# A record where more than this share of gross profit sits in one market is
# concentration-driven (mirrors the one-hit flag threshold in track_record).
CONCENTRATION_DRIVER_SHARE = 0.5


def _fmt_pp(value: Any) -> str:
    try:
        return f"{float(value) * 100:+.1f}"
    except (TypeError, ValueError):
        return "?"


def _ci_text(edge: Mapping[str, Any]) -> str:
    if edge.get("ci_low") is None or edge.get("ci_high") is None:
        return "n/a"
    return f"[{_fmt_pp(edge['ci_low'])}, {_fmt_pp(edge['ci_high'])}]"


def verdict_state(scorecard: Mapping[str, Any]) -> dict[str, Any]:
    """Map one scorecard to a verdict state with status sentences (de/en) and
    the evidence that triggered it."""

    track = scorecard.get("track") or {}
    sample = scorecard.get("sample") or {}
    risk = scorecard.get("risk") or {}
    edge = scorecard.get("realized_edge") or {}

    risk_level = str(risk.get("risk_level", "") or "").strip().lower()
    farmer = bool(track.get("farmer_flag"))
    if risk_level == "high" or farmer:
        evidence = []
        if farmer:
            evidence.append("wash/farm pattern: heavy volume with near-zero edge per dollar")
        if risk_level == "high":
            evidence.append(f"insider screen level high (score {risk.get('wallet_insider_score', 0):.0f})")
        reason_en = evidence[0]
        reason_de = (
            "Wash-/Farm-Muster: hohes Volumen bei praktisch null Edge pro Dollar"
            if farmer
            else f"Insider-Screen auf Stufe hoch (Score {risk.get('wallet_insider_score', 0):.0f})"
        )
        return {
            "state": STATE_FLAGGED,
            "status": f"FLAGGED: {reason_en} — no skill read for this wallet.",
            "status_de": f"GEFLAGGT: {reason_de}. Kein Skill-Urteil fuer dieses Wallet.",
            "evidence": evidence,
        }

    n_events = int(edge.get("n_events") or 0)
    capped = bool(edge.get("capped")) or str(edge.get("verdict", "")) == "capped"
    if not sample.get("verdict_allowed") or capped or n_events == 0:
        if capped:
            reason_en = "the public feed caps winners and losers, so only the extremes are visible"
            reason_de = "der oeffentliche Feed kappt Gewinner und Verlierer, sichtbar sind nur die Extreme"
        elif n_events == 0:
            reason_en = "no resolved positions in the public feed yet"
            reason_de = "noch keine aufgeloesten Positionen im oeffentlichen Feed"
        else:
            reason_en = f"only {n_events} resolved events so far"
            reason_de = f"erst {n_events} aufgeloeste Events"
        return {
            "state": STATE_INSUFFICIENT,
            "status": f"NO VERDICT YET: {reason_en}.",
            "status_de": f"NOCH KEIN URTEIL: {reason_de}.",
            "evidence": [reason_en],
        }

    ci = _ci_text(edge)
    ci_low = edge.get("ci_low")
    ci_high = edge.get("ci_high")
    if ci_low is not None and float(ci_low) > 0:
        evidence = [f"realized edge {_fmt_pp(edge.get('edge'))} pp, 95% CI {ci} pp over {n_events} events"]
        return {
            "state": STATE_SKILLED_READ,
            "status": (
                f"RECORD BEYOND CHANCE SO FAR: entries settled {_fmt_pp(edge.get('edge'))} pp above their price "
                f"(95% CI {ci} pp over {n_events} events). A description of the past record."
            ),
            "status_de": (
                f"RECORD BISHER UEBER ZUFALL: Eintritte settelten {_fmt_pp(edge.get('edge'))} pp ueber ihrem Preis "
                f"(95%-Intervall {ci} pp ueber {n_events} Events). Beschreibung des bisherigen Records."
            ),
            "evidence": evidence,
        }
    if ci_high is not None and float(ci_high) < 0:
        evidence = [f"realized edge {_fmt_pp(edge.get('edge'))} pp, 95% CI {ci} pp over {n_events} events"]
        return {
            "state": STATE_NEGATIVE_READ,
            "status": (
                f"SYSTEMATICALLY NEGATIVE RECORD: entries settled {_fmt_pp(edge.get('edge'))} pp below their price "
                f"(95% CI {ci} pp over {n_events} events)."
            ),
            "status_de": (
                f"SYSTEMATISCH NEGATIVER RECORD: Eintritte settelten {_fmt_pp(edge.get('edge'))} pp unter ihrem Preis "
                f"(95%-Intervall {ci} pp ueber {n_events} Events)."
            ),
            "evidence": evidence,
        }
    evidence = [f"95% CI {ci} pp includes zero over {n_events} events"]
    return {
        "state": STATE_LUCK_RANGE,
        "status": f"NOT SEPARABLE FROM CHANCE: the 95% interval includes zero ({ci} pp over {n_events} events).",
        "status_de": f"VOM ZUFALL NICHT UNTERSCHEIDBAR: das 95%-Intervall umfasst null ({ci} pp ueber {n_events} Events).",
        "evidence": evidence,
    }


def _drivers(scorecard: Mapping[str, Any], lang: str) -> list[str]:
    track = scorecard.get("track") or {}
    sample = scorecard.get("sample") or {}
    calibration = scorecard.get("calibration") or {}
    de = lang == "de"

    drivers: list[str] = []
    if track.get("farmer_flag"):
        drivers.append(
            "hohes Volumen bei praktisch null Edge pro Dollar" if de else "heavy volume with near-zero edge per dollar"
        )
    share = float(track.get("top_market_share") or 0.0)
    if share >= CONCENTRATION_DRIVER_SHARE:
        drivers.append(
            f"{share * 100:.0f}% des Bruttogewinns stecken in einem einzigen Markt"
            if de
            else f"{share * 100:.0f}% of gross profit sits in a single market"
        )
    if sample.get("quality") in ("insufficient", "developing"):
        n = int(sample.get("n_resolved") or 0)
        drivers.append(f"erst {n} aufgeloeste Events" if de else f"only {n} resolved events so far")
    brier = calibration.get("brier_entry")
    baseline = calibration.get("brier_baseline")
    if brier is not None and baseline is not None:
        if float(brier) < float(baseline):
            drivers.append(
                f"Eintrittspreise schlagen die Base-Rate-Benchmark (Brier {float(brier):.3f} vs {float(baseline):.3f})"
                if de
                else f"entry prices beat the base-rate benchmark (Brier {float(brier):.3f} vs {float(baseline):.3f})"
            )
        else:
            drivers.append(
                f"Eintrittspreise ohne Informationsvorsprung (Brier {float(brier):.3f} vs Benchmark {float(baseline):.3f})"
                if de
                else f"entry prices carry no edge over the base rate (Brier {float(brier):.3f} vs {float(baseline):.3f})"
            )
    risk_adjusted = float(track.get("risk_adjusted") or 0.0)
    if risk_adjusted >= 1.0:
        drivers.append("gleichmaessige Edge ueber viele Maerkte" if de else "steady edge across many markets")
    return drivers


def diagnosis_sentence(scorecard: Mapping[str, Any], lang: str = "en") -> str:
    """One sentence built from the strongest two drivers; never empty."""

    drivers = _drivers(scorecard, lang)[:2]
    de = lang == "de"
    if not drivers:
        resolved = int((scorecard.get("track") or {}).get("resolved_markets") or 0)
        if resolved:
            drivers = [
                f"Breite ueber {resolved} aufgeloeste Maerkte ohne dominanten Einzeltreiber"
                if de
                else f"breadth across {resolved} resolved markets with no single dominant driver"
            ]
        else:
            drivers = [
                "noch keine aufgeloesten Maerkte im oeffentlichen Feed"
                if de
                else "no resolved markets in the public feed yet"
            ]
    joined = (" und " if de else " and ").join(drivers)
    return (f"Gepraegt von {joined}." if de else f"Shaped by {joined}.")


def copy_summary(stats: Mapping[str, Any] | None, days: int = 90, lang: str = "en") -> dict[str, Any]:
    """Text block for the would-copying-have-paid box.

    Honest placeholder when the window holds no replayable trades — a missing
    number is reported as missing, never invented.
    """

    de = lang == "de"
    if not stats or int(stats.get("copied_trades") or 0) == 0:
        return {
            "available": False,
            "roi": None,
            "text": (
                f"Im {days}-Tage-Fenster liegen keine nachspielbaren Trades vor; ohne Daten keine Copy-Zahl."
                if de
                else f"No replayable trades in the {days}-day window; without data there is no copy number."
            ),
        }
    roi = float(stats.get("roi") or 0.0)
    trades = int(stats.get("copied_trades") or 0)
    fees = float(stats.get("fees_paid") or 0.0)
    text = (
        f"Ein Nachbau der letzten {days} Tage (fixe Stakes, netto nach Fees und Slippage-Annahme) haette "
        f"{roi * 100:+.1f}% ergeben, ueber {trades} kopierte Trades (modelliert, ${fees:,.0f} Fees)."
        if de
        else (
            f"Replaying the last {days} days at fixed stakes, net of fees and modeled slippage, would have "
            f"returned {roi * 100:+.1f}% over {trades} copied trades (modeled, ${fees:,.0f} fees)."
        )
    )
    return {"available": True, "roi": roi, "text": text}
