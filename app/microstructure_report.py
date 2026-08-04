"""Baut die Microstructure-Studien zu einer Website-Nutzlast zusammen.

Die zwoelf Studien liegen als Report (`.md`), Rohwerte (`.json`) und teils
als Bild in `docs/research/`. Fuer die Website braucht es daraus eine
einzige Datei, die pro Studie die Frage, das Verdikt, die Datenbasis, die
tragenden Zahlen und ein Diagramm mitbringt.

Der Grundsatz hier: Prosa ist kuratiert, Zahlen niemals. Frage, Verdikt
und Erklaerung stehen in `STUDIEN`, jede einzelne Zahl wird zur Laufzeit
aus dem Studien-JSON gelesen. Damit kann die Website nicht von den
Reports abdriften, und ein neu gerechneter Report schlaegt ohne Codeaenderung
durch.

Streamlit-frei nach Projektkonvention. Verbraucher sind
`scripts/publish_microstructure.py` und `app/api_views.py`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

REPORT_DIR = Path("docs/research")

# Verdikt-Arten. Steuert nur die Einfaerbung in der Oberflaeche.
VERDIKT_NEIN = "nein"      # gemessen und widerlegt
VERDIKT_JA = "ja"          # gemessen und bestaetigt
VERDIKT_OFFEN = "offen"    # nicht identifiziert, bewusst kein Urteil

# Diagrammarten, die das Frontend rendern kann.
DIA_KOSTEN = "kosten"        # Balken mit Summenlinie: Vorteil gegen Kosten
DIA_VERGLEICH = "vergleich"  # gruppierte Balken: zwei Szenarien
DIA_INTERVALL = "intervall"  # Konfidenzintervalle gegen eine Nulllinie
DIA_QUOTE = "quote"          # Quote gegen eine Referenzquote
DIA_ANTEIL = "anteil"        # Teil von Ganzem


def _lade(root: Path, name: str) -> dict[str, Any]:
    pfad = root / REPORT_DIR / f"{name}.json"
    with pfad.open(encoding="utf-8") as fh:
        return json.load(fh)


def _cents(wert: float) -> float:
    return round(float(wert), 4)


def _usd(wert: float) -> float:
    return round(float(wert), 2)


@dataclass(frozen=True)
class Studie:
    """Eine Studie mit kuratierter Prosa und einem Zahlen-Extraktor."""

    id: str
    frage: str
    verdikt: str
    verdikt_art: str
    einfach: str
    quelle: str
    report: str
    modul: str
    extrakt: Callable[[dict[str, Any]], dict[str, Any]]
    bild: str | None = None
    schlagworte: tuple[str, ...] = field(default_factory=tuple)


def _basis(werte: dict[str, Any], **zusatz: Any) -> dict[str, Any]:
    """Datenbasis in einheitlicher Form, leere Felder fliegen raus."""
    basis = {
        "beobachtungen": zusatz.get("beobachtungen"),
        "snapshots": werte.get("snapshots"),
        "tokens": werte.get("tokens"),
        "tage": len(werte["days"]) if isinstance(werte.get("days"), list) else werte.get("days"),
        "maerkte": zusatz.get("maerkte"),
        "paare": zusatz.get("paare"),
    }
    return {k: v for k, v in basis.items() if v is not None}


def _zahl(label: str, wert: Any, einheit: str = "", hinweis: str = "") -> dict[str, Any]:
    eintrag: dict[str, Any] = {"label": label, "wert": wert}
    if einheit:
        eintrag["einheit"] = einheit
    if hinweis:
        eintrag["hinweis"] = hinweis
    return eintrag


# --------------------------------------------------------------------------
# Extraktoren. Einer je Studie, liest ausschliesslich aus dem Studien-JSON.
# --------------------------------------------------------------------------

def _extrakt_imbalance(d: dict[str, Any]) -> dict[str, Any]:
    o = d["signals"]["imbalance"]["overall"]
    return {
        "basis": _basis(d, beobachtungen=o["n"]),
        "zahlen": [
            _zahl("Hit rate", round(o["hit_rate"] * 100, 1), "%",
                  "share of firings where the book moved the predicted way"),
            _zahl("Wilson lower bound (95%)", round(o["wilson_lb95"] * 100, 1), "%",
                  "even the pessimistic end of the interval sits above the coin flip"),
            _zahl("Firings", o["n"], "observations"),
            _zahl("Of those, price actually moved", round(o["moved_share"] * 100, 1), "%"),
        ],
        "diagramm": {
            "art": DIA_QUOTE,
            "titel": "Hit rate against a coin flip",
            "einheit": "%",
            "referenz": 50.0,
            "referenz_label": "coin flip",
            "punkte": [
                {"label": "Hit rate", "wert": round(o["hit_rate"] * 100, 1)},
                {"label": "Wilson lower bound", "wert": round(o["wilson_lb95"] * 100, 1)},
            ],
        },
    }


def _extrakt_takeable(d: dict[str, Any]) -> dict[str, Any]:
    o = d["signals"]["imbalance"]["overall"]
    c = d["signals"]["combo"]["overall"]
    return {
        "basis": _basis(d, beobachtungen=o["n"]),
        "zahlen": [
            _zahl("Gross edge, imbalance", _cents(o["mean_gross_cents"]), "cents per firing"),
            _zahl("Gross edge, best cut", _cents(c["mean_gross_cents"]), "cents per firing"),
            _zahl("Spread cost", _cents(o["mean_spread_cost_cents"]), "cents"),
            _zahl("Fee cost", _cents(o["mean_fee_cost_cents"]), "cents"),
            _zahl("Round trip total", _cents(o["mean_cost_cents"]), "cents"),
            _zahl("Net result", _cents(o["mean_net_cents"]), "cents",
                  "what is left after both cost legs"),
            _zahl("Firings that end net positive", round(o["net_positive_share"] * 100, 1), "%"),
        ],
        "diagramm": {
            "art": DIA_KOSTEN,
            "titel": "The edge is real and still too small to take",
            "einheit": "cents per firing",
            "punkte": [
                {"label": "Gross edge", "wert": _cents(o["mean_gross_cents"]), "art": "gewinn"},
                {"label": "Spread cost", "wert": -_cents(o["mean_spread_cost_cents"]), "art": "kosten"},
                {"label": "Fee cost", "wert": -_cents(o["mean_fee_cost_cents"]), "art": "kosten"},
                {"label": "Net", "wert": _cents(o["mean_net_cents"]), "art": "summe"},
            ],
        },
    }


def _extrakt_signed_flow(d: dict[str, Any]) -> dict[str, Any]:
    f = d["signals"]["flow"]["overall"]
    i = d["signals"]["imbalance"]["overall"]
    return {
        "basis": _basis(d, beobachtungen=f["n"]),
        "zahlen": [
            _zahl("Hit rate", round(f["hit_rate"] * 100, 1), "%"),
            _zahl("Wilson lower bound (95%)", round(f["wilson_lb95"] * 100, 1), "%"),
            _zahl("Gross edge", _cents(f["mean_gross_cents"]), "cents per firing",
                  "already negative before any cost is subtracted"),
            _zahl("Firings", f["n"], "observations"),
        ],
        "diagramm": {
            "art": DIA_QUOTE,
            "titel": "Signed flow against imbalance and a coin flip",
            "einheit": "%",
            "referenz": 50.0,
            "referenz_label": "coin flip",
            "punkte": [
                {"label": "Signed order flow", "wert": round(f["hit_rate"] * 100, 1)},
                {"label": "Book imbalance", "wert": round(i["hit_rate"] * 100, 1)},
            ],
        },
    }


def _extrakt_segmente(d: dict[str, Any]) -> dict[str, Any]:
    """Schnitte, Szenarien und Ueberlebende.

    `by_category` sind die Gebuehrenszenarien, nicht Marktkategorien. Jedes
    Szenario testet dieselben `tested_segments` Schnitte. Ueberlebende
    stehen je Szenario in `survivors`.
    """
    szenarien = d["by_category"]
    leit = szenarien.get("sports") or next(iter(szenarien.values()))
    o = leit["overall"]
    je_szenario = int(leit.get("tested_segments") or 0)
    ueberlebende = [
        (name, s)
        for name, szenario in szenarien.items()
        for s in szenario.get("survivors", [])
    ]
    ci = o.get("net_ci95_cents") or [None, None]

    punkte = [
        {
            "label": "All firings",
            "wert": _cents(o["mean_net_cents"]),
            "von": _cents(ci[0]) if ci[0] is not None else None,
            "bis": _cents(ci[1]) if ci[1] is not None else None,
        },
    ]
    zahlen = [
        _zahl("Cuts tested per fee scenario", je_szenario, "segments"),
        _zahl("Fee scenarios", len(szenarien), ""),
        _zahl("Cuts that survived", len(ueberlebende), "",
              "at this many tests, one lucky survivor is the expected count"),
        _zahl("Net result over all", _cents(o["mean_net_cents"]), "cents per firing"),
    ]
    if ueberlebende:
        name, s = ueberlebende[0]
        s_ci = s.get("net_ci95_cents") or [None, None]
        zahlen.append(
            _zahl(f"Survivor ({name}), net", _cents(s["mean_net_cents"]), "cents per firing")
        )
        if s_ci[0] is not None:
            zahlen.append(
                _zahl("Survivor, 95% interval", [_cents(s_ci[0]), _cents(s_ci[1])], "cents",
                      "the interval contains zero, so the survivor is not distinguishable from noise")
            )
            punkte.append({
                "label": f"Survivor ({name})",
                "wert": _cents(s["mean_net_cents"]),
                "von": _cents(s_ci[0]),
                "bis": _cents(s_ci[1]),
            })

    return {
        "basis": _basis(d, beobachtungen=o["n"]),
        "zahlen": zahlen,
        "diagramm": {
            "art": DIA_INTERVALL,
            "titel": "Net result with its 95% interval",
            "einheit": "cents per firing",
            "referenz": 0.0,
            "referenz_label": "break even",
            "punkte": punkte,
        },
    }


def _mm_zahlen(d: dict[str, Any], modell: str) -> dict[str, Any]:
    return d["fill_models"][modell]["decomposition"]


def _extrakt_mm_120s(d: dict[str, Any]) -> dict[str, Any]:
    t = _mm_zahlen(d, "tape")
    return {
        "basis": _basis(d),
        "zahlen": [
            _zahl("Spread earned", round(t["spread_capture_cents_per_fill"], 1), "cents per fill"),
            _zahl("Adverse selection", round(t["markout_cents_per_fill"], 1), "cents per fill",
                  "what the market takes back right after the fill"),
            _zahl("Net", round(t["total_cents_per_fill"], 1), "cents per fill"),
            _zahl("Fills", t["fills"], ""),
        ],
        "diagramm": {
            "art": DIA_VERGLEICH,
            "titel": "Earned against lost, per fill",
            "einheit": "cents per fill",
            "punkte": [
                {"label": "Spread earned", "wert": round(t["spread_capture_cents_per_fill"], 1), "art": "gewinn"},
                {"label": "Adverse selection", "wert": round(t["markout_cents_per_fill"], 1), "art": "kosten"},
            ],
        },
    }


def _extrakt_staleness(d: dict[str, Any], langsam: dict[str, Any]) -> dict[str, Any]:
    schnell = _mm_zahlen(d, "tape")
    traege = _mm_zahlen(langsam, "tape")
    return {
        "basis": _basis(d),
        "zahlen": [
            _zahl("Adverse selection at 120s", round(traege["markout_cents_per_fill"], 1), "cents per fill"),
            _zahl("Adverse selection on seconds data", round(schnell["markout_cents_per_fill"], 1), "cents per fill"),
            _zahl("Spread earned at 120s", round(traege["spread_capture_cents_per_fill"], 1), "cents per fill"),
            _zahl("Spread earned on seconds data", round(schnell["spread_capture_cents_per_fill"], 1), "cents per fill"),
        ],
        "diagramm": {
            "art": DIA_VERGLEICH,
            "titel": "Same code, same parameters, faster quotes",
            "einheit": "cents per fill",
            "gruppen": ["120 second requote", "seconds data"],
            "punkte": [
                {"label": "Spread earned", "art": "gewinn",
                 "werte": [round(traege["spread_capture_cents_per_fill"], 1),
                           round(schnell["spread_capture_cents_per_fill"], 1)]},
                {"label": "Adverse selection", "art": "kosten",
                 "werte": [round(traege["markout_cents_per_fill"], 1),
                           round(schnell["markout_cents_per_fill"], 1)]},
            ],
        },
    }


def _extrakt_mm_offen(d: dict[str, Any]) -> dict[str, Any]:
    touch = d["fill_models"]["touch"]
    tape = d["fill_models"]["tape"]
    t_ci = touch["daily_ci95_usd"]
    p_ci = tape["daily_ci95_usd"]
    return {
        "basis": _basis(d),
        "zahlen": [
            _zahl("Touch model, daily", [_usd(t_ci[0]), _usd(t_ci[1])], "USD per day",
                  "assumes a fill whenever the price touches our quote"),
            _zahl("Tape model, daily", [_usd(p_ci[0]), _usd(p_ci[1])], "USD per day",
                  "assumes a fill only against a print that actually happened"),
            _zahl("Fills, touch", touch["decomposition"]["fills"], ""),
            _zahl("Fills, tape", tape["decomposition"]["fills"], ""),
        ],
        "diagramm": {
            "art": DIA_INTERVALL,
            "titel": "Two fill models, opposite sides of zero",
            "einheit": "USD per day",
            "referenz": 0.0,
            "referenz_label": "break even",
            "punkte": [
                {"label": "Touch model", "wert": _usd((t_ci[0] + t_ci[1]) / 2),
                 "von": _usd(t_ci[0]), "bis": _usd(t_ci[1])},
                {"label": "Tape model", "wert": _usd((p_ci[0] + p_ci[1]) / 2),
                 "von": _usd(p_ci[0]), "bis": _usd(p_ci[1])},
            ],
        },
    }


def _extrakt_cross_venue(d: dict[str, Any]) -> dict[str, Any]:
    s = d["summary"]
    return {
        "basis": _basis(d, maerkte=d["pm_markets"] + d["kalshi_markets"], paare=s["pairs"]),
        "zahlen": [
            _zahl("Pairs matched", s["pairs"], ""),
            _zahl("Usable after review", s["usable"], ""),
            _zahl("Rejected as mismatched", s["suspect"], ""),
            _zahl("Clear both fee curves", s["net_positive"], ""),
            _zahl("Best net gap", _cents(s["max_net_cents"]), "cents"),
            _zahl("Median net gap", _cents(s["median_net_cents"]), "cents"),
        ],
        "diagramm": {
            "art": DIA_ANTEIL,
            "titel": "What survives the filters",
            "einheit": "pairs",
            "punkte": [
                {"label": "Matched", "wert": s["pairs"]},
                {"label": "Usable", "wert": s["usable"]},
                {"label": "Clear both fee curves", "wert": s["net_positive"]},
            ],
        },
    }


def _extrakt_gap_lifetime(d: dict[str, Any]) -> dict[str, Any]:
    zeilen = d.get("rows") or []
    dauerhaft = sum(1 for r in zeilen if float(r.get("open_share") or 0.0) >= 1.0)
    nie_offen = sum(1 for r in zeilen if float(r.get("open_share") or 0.0) <= 0.0)
    stunden = max((float(r.get("paired_hours") or 0.0) for r in zeilen), default=0.0)
    return {
        "basis": _basis(d, paare=d["pairs"]),
        "zahlen": [
            _zahl("Pairs watched", d["pairs"], ""),
            _zahl("Open at every moment observed", dauerhaft, "pairs"),
            _zahl("Never open at all", nie_offen, "pairs"),
            _zahl("Observation window", round(stunden, 1), "hours"),
            _zahl("Assumed reachability", d["reachable_s"], "seconds",
                  "how fast both legs would have to be hit"),
        ],
        "diagramm": {
            "art": DIA_ANTEIL,
            "titel": "Gaps that never closed",
            "einheit": "pairs",
            "punkte": [
                {"label": "Pairs watched", "wert": d["pairs"]},
                {"label": "Open the whole time", "wert": dauerhaft},
            ],
        },
    }


def _extrakt_rewards(d: dict[str, Any]) -> dict[str, Any]:
    return {
        "basis": _basis(d, maerkte=d["markets_with_pool"]),
        "zahlen": [
            _zahl("Markets carrying a pool", d["markets_with_pool"], ""),
            _zahl("Pool paid out", _usd(d["total_pool_usd_per_day"]), "USD per day"),
            _zahl("Largest pools probed", d["probed"], "markets"),
            _zahl("Of those, qualifying band empty", d["empty_band_markets"], "markets",
                  "nobody quotes inside the band the reward requires"),
        ],
        "diagramm": {
            "art": DIA_ANTEIL,
            "titel": "The biggest pools nobody can reach",
            "einheit": "markets",
            "punkte": [
                {"label": "Largest pools probed", "wert": d["probed"]},
                {"label": "Qualifying band empty", "wert": d["empty_band_markets"]},
            ],
        },
    }


def _extrakt_resolution(d: dict[str, Any]) -> dict[str, Any]:
    return {
        "basis": _basis(d, paare=d["pairs"]),
        "zahlen": [
            _zahl("Confirmed pairs", d["pairs"], ""),
            _zahl("Both rulebooks read side by side", d["with_both_texts"], "pairs"),
            _zahl("Wording differs on who wins", d["with_one_sided_flags"], "pairs"),
        ],
        "diagramm": {
            "art": DIA_ANTEIL,
            "titel": "Same event, different rulebook",
            "einheit": "pairs",
            "punkte": [
                {"label": "Pairs checked", "wert": d["pairs"]},
                {"label": "Rulebooks disagree", "wert": d["with_one_sided_flags"]},
            ],
        },
    }


def _extrakt_reconcile(d: dict[str, Any]) -> dict[str, Any]:
    s = d["summary"]
    return {
        "basis": _basis(d, beobachtungen=s["comparisons"]),
        "zahlen": [
            _zahl("Agreement with the venue", round(s["match_rate"] * 100, 1), "%"),
            _zahl("Mean divergence", s["mean_diff_ticks"], "ticks"),
            _zahl("Largest divergence", s["max_diff_ticks"], "ticks"),
            _zahl("Comparisons", s["comparisons"], ""),
        ],
        "diagramm": {
            "art": DIA_QUOTE,
            "titel": "Does our recorded book match the venue",
            "einheit": "%",
            "referenz": 100.0,
            "referenz_label": "perfect agreement",
            "punkte": [
                {"label": "Agreement", "wert": round(s["match_rate"] * 100, 1)},
            ],
        },
    }


# --------------------------------------------------------------------------
# Kuratierte Studienliste. Reihenfolge ist die Erzaehlreihenfolge der Seite.
# --------------------------------------------------------------------------

STUDIEN: tuple[Studie, ...] = (
    Studie(
        id="imbalance-direction",
        frage="Does book imbalance predict which way the price moves?",
        verdikt="Yes. 55.2% hit rate, and the pessimistic end of the interval is still above the coin flip.",
        verdikt_art=VERDIKT_JA,
        einfach=(
            "When far more money sits on one side of the order book than the other, the "
            "price tends to move that way. Over a million firings, that happened 55 times "
            "in 100 instead of the 50 a coin flip would give. The signal is real."
        ),
        quelle="orderflow_rest-2026-07",
        report="docs/research/orderflow_rest-2026-07.md",
        modul="src/orderflow_study.py",
        bild="orderflow_rest-2026-07.png",
        extrakt=_extrakt_imbalance,
        schlagworte=("signal", "order book"),
    ),
    Studie(
        id="imbalance-takeable",
        frage="Can that signal be taken as a taker?",
        verdikt="No. The edge is worth about a tenth of a cent against a 2.56 cent round trip.",
        verdikt_art=VERDIKT_NEIN,
        einfach=(
            "This is the sentence the whole strand turns on. Being right 55% of the time "
            "is worthless if acting on it costs more than being right pays. Crossing the "
            "spread and paying the fee costs roughly twenty times what the signal is worth. "
            "A real edge, and still unusable."
        ),
        quelle="orderflow_rest-2026-07",
        report="docs/research/orderflow_rest-2026-07.md",
        modul="app/venue_fees.py",
        extrakt=_extrakt_takeable,
        schlagworte=("cost", "fees", "key result"),
    ),
    Studie(
        id="signed-flow",
        frage="Is signed order flow a usable signal?",
        verdikt="No. 51.3% hit rate, and the gross edge is negative before any cost.",
        verdikt_art=VERDIKT_NEIN,
        einfach=(
            "Signed flow means guessing whether each trade was a buy or a sell and following "
            "the imbalance. It barely beats a coin flip here. Published work later explained "
            "why: on this venue that guess is close to random. Most third-party smart money "
            "flow analytics rest on exactly that guess."
        ),
        quelle="orderflow_rest-2026-07",
        report="docs/research/orderflow_rest-2026-07.md",
        modul="src/orderflow_study.py",
        extrakt=_extrakt_signed_flow,
        schlagworte=("signal", "negative result"),
    ),
    Studie(
        id="edge-segments",
        frage="Does any segment of the market rescue the signal?",
        verdikt="No. One cut survives out of many, which is what pure chance predicts.",
        verdikt_art=VERDIKT_NEIN,
        einfach=(
            "If the signal does not pay overall, maybe it pays somewhere specific, in wide "
            "spreads or in one category. Every cut was fixed before looking. Exactly one "
            "survived, and its interval still contains zero. Test enough slices and one "
            "will look good by accident, so a single survivor is the expected count, not a "
            "finding."
        ),
        quelle="edge_segments_july-2026",
        report="docs/research/edge_segments_july-2026.md",
        modul="src/edge_segments.py",
        bild="edge_segments_july-2026.png",
        extrakt=_extrakt_segmente,
        schlagworte=("multiple testing", "negative result"),
    ),
    Studie(
        id="mm-120s",
        frage="Does market making carry at a 120 second requote?",
        verdikt="No. Adverse selection takes 362 cents per fill against 148 cents of spread earned.",
        verdikt_art=VERDIKT_NEIN,
        einfach=(
            "Instead of crossing the spread, quote both sides and earn it. The problem is who "
            "trades against a stale quote: whoever knows the price has already moved. Every "
            "fill earns a bit of spread and immediately gives back more than twice as much."
        ),
        quelle="mm_pnl_july-2026",
        report="docs/research/mm_pnl_july-2026.md",
        modul="src/mm_pnl.py",
        bild="mm_pnl_july-2026.png",
        extrakt=_extrakt_mm_120s,
        schlagworte=("market making", "adverse selection"),
    ),
    Studie(
        id="mm-staleness",
        frage="Is the binding constraint spread width or quote staleness?",
        verdikt="Staleness. On seconds data the loss per fill falls from 362 to 70 cents while the spread earned barely moves.",
        verdikt_art=VERDIKT_JA,
        einfach=(
            "Same code, same parameters, only faster data. Almost all of the loss disappears "
            "and the earnings stay put. That isolates the cause: the problem was never how "
            "much spread there is to earn, it was quoting on a picture of the book that had "
            "already gone out of date."
        ),
        quelle="mm_pnl_stream-5tage",
        report="docs/research/mm_pnl_stream-5tage.md",
        modul="src/mm_pnl.py",
        bild="mm_pnl_stream-5tage.png",
        extrakt=lambda d: {},  # wird in build_payload mit dem 120s-Lauf verschraenkt
        schlagworte=("market making", "key result"),
    ),
    Studie(
        id="mm-identified",
        frage="Does market making pay, once the bootstrap can run?",
        verdikt="Not identified. Two fill models land on opposite sides of zero and neither interval touches it.",
        verdikt_art=VERDIKT_OFFEN,
        einfach=(
            "Whether this makes money depends entirely on an assumption nobody can observe "
            "from outside: would our quote actually have been filled. Assume a fill whenever "
            "the price touches it and the answer is a clear loss. Assume a fill only against "
            "a print that really happened and it is a clear profit. Both intervals are far "
            "from zero, in opposite directions. What would settle it is queue position, not "
            "more data. Saying so is the honest answer."
        ),
        quelle="mm_pnl_stream-5tage",
        report="docs/research/mm_pnl_stream-5tage.md",
        modul="src/mm_pnl.py",
        extrakt=_extrakt_mm_offen,
        schlagworte=("market making", "not identified", "key result"),
    ),
    Studie(
        id="cross-venue",
        frage="Are price gaps between the two venues arbitrage?",
        verdikt="No, carry. The gaps that survive settle in 2027 or 2028, worth 0.5 to 1.8 percent annualised.",
        verdikt_art=VERDIKT_NEIN,
        einfach=(
            "The same event often trades at different prices on the two venues. Most of those "
            "gaps are matching errors rather than mispricings. Of the ones that hold up and "
            "clear both fee curves, the money is only released years later, so the return per "
            "year is tiny. It is a slow carry trade, not free money."
        ),
        quelle="cross_venue_gaps_2026-07-31",
        report="docs/research/cross_venue_gaps_2026-07-31.md",
        modul="src/cross_venue_gaps.py",
        extrakt=_extrakt_cross_venue,
        schlagworte=("cross venue", "arbitrage"),
    ),
    Studie(
        id="gap-lifetime",
        frage="How long does such a gap stay open?",
        verdikt="Most stayed open at every single moment observed.",
        verdikt_art=VERDIKT_NEIN,
        einfach=(
            "A real mispricing closes once people notice it. These did not close at all over "
            "the whole observation window. That is the clearest evidence that they are not "
            "mispricings but a fair price for tying money up until settlement."
        ),
        quelle="gap_lifetime_2026-07-31",
        report="docs/research/gap_lifetime_2026-07-31.md",
        modul="src/gap_lifetime.py",
        extrakt=_extrakt_gap_lifetime,
        schlagworte=("cross venue",),
    ),
    Studie(
        id="rewards",
        frage="Are the large liquidity reward pools free money?",
        verdikt="No. Many of the biggest pools have a completely empty qualifying band.",
        verdikt_art=VERDIKT_NEIN,
        einfach=(
            "Venues pay traders for quoting close to the middle. The pools look large. But in "
            "many of the biggest ones nobody quotes inside the narrow band the reward actually "
            "requires, and the quotes that exist sit far outside it. The pool is large because "
            "it is unreachable, not despite it."
        ),
        quelle="reward_selection_2026-07-31",
        report="docs/research/reward_selection_2026-07-31.md",
        modul="src/reward_selection.py",
        extrakt=_extrakt_rewards,
        schlagworte=("rewards", "negative result"),
    ),
    Studie(
        id="resolution-rules",
        frage="Do two venues settle the same event the same way?",
        verdikt="No. One asks who is inaugurated, the other who wins the election.",
        verdikt_art=VERDIKT_NEIN,
        einfach=(
            "This is the trap underneath every cross venue trade. Two markets can look like "
            "the same question and settle on different facts. A basket built across such a "
            "pair does not hedge, it loses both legs at once. The rulebooks have to be read, "
            "the titles are not enough."
        ),
        quelle="resolution_rules_2026-07-31",
        report="docs/research/resolution_rules_2026-07-31.md",
        modul="src/resolution_rules.py",
        extrakt=_extrakt_resolution,
        schlagworte=("cross venue", "settlement risk"),
    ),
    Studie(
        id="book-reconcile",
        frage="Does our own recorded book drift against the venue?",
        verdikt="No. 98.6% agreement, mean divergence 0.07 ticks.",
        verdikt_art=VERDIKT_JA,
        einfach=(
            "Every number above rests on books this project recorded itself, so the recorder "
            "has to be checked too. Compared against the venue's own snapshot it agrees almost "
            "always, and where it differs the gap is a fraction of one tick. This study exists "
            "so the others can be believed."
        ),
        quelle="book_reconcile_tick-2026-07-31",
        report="docs/research/book_reconcile_tick-2026-07-31.md",
        modul="src/book_reconcile.py",
        extrakt=_extrakt_reconcile,
        schlagworte=("data quality", "control"),
    ),
)

HINWEIS = (
    "Descriptive microstructure research on data this project recorded itself. "
    "Every figure is produced by a tested module in this repository. "
    "No profitability claim is made anywhere in this work."
)

EINLEITUNG = (
    "Four recorders run continuously across both venues: REST pollers on a 120 second grid "
    "and event driven WebSocket recorders that write on every change at the top of the book. "
    "The studies below ask, in order, whether anything in that data can be turned into money. "
    "Most of the answers are no, and the reasoning behind each no is the point."
)


def build_payload(root: Path | str = ".", *, jetzt: datetime | None = None) -> dict[str, Any]:
    """Baut die Nutzlast fuer `public/data/microstructure.json`.

    Fehlende Studiendateien werden uebersprungen und unter `fehlend`
    gemeldet, damit eine unvollstaendige Arbeitskopie die Seite nicht
    zerlegt.
    """
    wurzel = Path(root)
    zeit = jetzt or datetime.now(timezone.utc)
    studien: list[dict[str, Any]] = []
    fehlend: list[str] = []
    rohdaten: dict[str, dict[str, Any]] = {}

    for studie in STUDIEN:
        if studie.quelle not in rohdaten:
            try:
                rohdaten[studie.quelle] = _lade(wurzel, studie.quelle)
            except FileNotFoundError:
                fehlend.append(studie.quelle)
                continue
        daten = rohdaten[studie.quelle]

        if studie.id == "mm-staleness":
            try:
                langsam = rohdaten.get("mm_pnl_july-2026") or _lade(wurzel, "mm_pnl_july-2026")
            except FileNotFoundError:
                fehlend.append("mm_pnl_july-2026")
                continue
            rohdaten.setdefault("mm_pnl_july-2026", langsam)
            teil = _extrakt_staleness(daten, langsam)
        else:
            teil = studie.extrakt(daten)

        eintrag: dict[str, Any] = {
            "id": studie.id,
            "frage": studie.frage,
            "verdikt": studie.verdikt,
            "verdikt_art": studie.verdikt_art,
            "einfach": studie.einfach,
            "report": studie.report,
            "modul": studie.modul,
            "schlagworte": list(studie.schlagworte),
            "gebuehrenmodell": daten.get("fee_model_version"),
        }
        if studie.bild:
            eintrag["bild"] = f"docs/research/{studie.bild}"
        eintrag.update(teil)
        studien.append(eintrag)

    zaehler = {
        "gesamt": len(studien),
        "nein": sum(1 for s in studien if s["verdikt_art"] == VERDIKT_NEIN),
        "ja": sum(1 for s in studien if s["verdikt_art"] == VERDIKT_JA),
        "offen": sum(1 for s in studien if s["verdikt_art"] == VERDIKT_OFFEN),
    }

    return {
        "hinweis": HINWEIS,
        "einleitung": EINLEITUNG,
        "stand_utc": zeit.isoformat(),
        "kennzeichnung": "research/frozen",
        "zaehler": zaehler,
        "studien": studien,
        "fehlend": fehlend,
    }
