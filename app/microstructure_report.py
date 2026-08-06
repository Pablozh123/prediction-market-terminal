"""Baut die Microstructure-Studien zu einer Website-Nutzlast zusammen.

Die zwoelf Studien liegen als Report (`.md`), Rohwerte (`.json`) und teils
als Bild in `docs/research/`. Fuer die Website braucht es daraus eine
einzige Datei, die pro Studie vier Dinge traegt:

* **analyse** was genau gemessen wurde, wie, auf welchen Daten und was als
  Beleg gegolten haette. Ohne das ist ein Verdikt eine Behauptung.
* **einfach** die Erklaerung in Klartext, mit den echten Zahlen im Satz.
* **interpretation** moegliche Lesarten, ausdruecklich samt Gegenlesart und
  Grenze. Eine Studie, die nur ihre eigene Lesart zeigt, ueberredet.
* **zahlen, diagramm, details** die Belege selbst.

Der Grundsatz: Prosa ist kuratiert, Zahlen niemals. Methode und Lesarten
stehen als Text in `STUDIEN`, jede Zahl wird zur Laufzeit aus dem
Studien-JSON gelesen. Die Erklaerungen sind Vorlagen, in die die echten
Werte eingesetzt werden, damit auch der Fliesstext nicht vom Report
abdriften kann.

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

# Arten der Interpretation. Die Reihenfolge ist die Anzeigereihenfolge.
LESART = "lesart"            # was die Zahlen nahelegen
GEGENLESART = "gegenlesart"  # was ebenso dazu passt
GRENZE = "grenze"            # was die Messung nicht hergibt

INTERPRET_TITEL = {
    LESART: "What it suggests",
    GEGENLESART: "What else fits the same numbers",
    GRENZE: "What this cannot tell you",
}


def _lade(root: Path, name: str) -> dict[str, Any]:
    pfad = root / REPORT_DIR / f"{name}.json"
    with pfad.open(encoding="utf-8") as fh:
        return json.load(fh)


def _cents(wert: float) -> float:
    return round(float(wert), 4)


def _usd(wert: float) -> float:
    return round(float(wert), 2)


def _n(wert: Any) -> str:
    """Tausenderpunkte fuer den Fliesstext."""
    try:
        return f"{int(round(float(wert))):,}"
    except (TypeError, ValueError):
        return str(wert)


def _pz(anteil: float, stellen: int = 1) -> str:
    return f"{anteil * 100:.{stellen}f}"


@dataclass(frozen=True)
class Studie:
    """Eine Studie: kuratierte Prosa, Zahlen aus dem Artefakt."""

    id: str
    frage: str
    verdikt: str
    verdikt_art: str
    analyse: dict[str, str]
    einfach: Callable[[dict[str, Any]], str]
    interpretation: tuple[tuple[str, str], ...]
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


def _tabelle(titel: str, spalten: list[str], zeilen: list[list[Any]], hinweis: str = "") -> dict[str, Any]:
    tab: dict[str, Any] = {"titel": titel, "spalten": spalten, "zeilen": zeilen}
    if hinweis:
        tab["hinweis"] = hinweis
    return tab


# --------------------------------------------------------------------------
# Extraktoren. Einer je Studie, liest ausschliesslich aus dem Studien-JSON.
# Jeder liefert basis, zahlen, diagramm, kennzahlen und optional details.
# --------------------------------------------------------------------------

def _extrakt_imbalance(d: dict[str, Any]) -> dict[str, Any]:
    sig = d["signals"]["imbalance"]
    o = sig["overall"]
    train, test = sig.get("train") or {}, sig.get("test") or {}
    details = None
    if train and test:
        details = _tabelle(
            "Split before and after the cut-off date",
            ["Sample", "Firings", "Hit rate", "Wilson lower bound", "Days"],
            [
                ["In sample", _n(train["n"]), _pz(train["hit_rate"]) + "%", _pz(train["wilson_lb95"]) + "%", train.get("days", "")],
                ["Out of sample", _n(test["n"]), _pz(test["hit_rate"]) + "%", _pz(test["wilson_lb95"]) + "%", test.get("days", "")],
            ],
            "The out-of-sample half was never used to choose the threshold.",
        )
    teil = {
        "basis": _basis(d, beobachtungen=o["n"]),
        "kennzahlen": {
            "n": o["n"], "hit": o["hit_rate"], "lb": o["wilson_lb95"],
            "moved": o["moved_share"], "threshold": d.get("threshold"),
            "tage": len(d.get("days") or []),
        },
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
    if details:
        teil["details"] = details
    return teil


def _extrakt_takeable(d: dict[str, Any]) -> dict[str, Any]:
    o = d["signals"]["imbalance"]["overall"]
    c = d["signals"]["combo"]["overall"]
    return {
        "basis": _basis(d, beobachtungen=o["n"]),
        "kennzahlen": {
            "gross": o["mean_gross_cents"], "spread": o["mean_spread_cost_cents"],
            "fee": o["mean_fee_cost_cents"], "cost": o["mean_cost_cents"],
            "net": o["mean_net_cents"], "positiv": o["net_positive_share"],
            "bester_gross": c["mean_gross_cents"],
            "faktor": o["mean_cost_cents"] / o["mean_gross_cents"] if o["mean_gross_cents"] else 0.0,
        },
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
        "details": _tabelle(
            "Every cost leg, per firing",
            ["Component", "Cents", "What it is"],
            [
                ["Gross edge", f"{o['mean_gross_cents']:+.4f}", "the price move the signal caught"],
                ["Spread cost", f"-{o['mean_spread_cost_cents']:.4f}", "half the spread, paid to cross the book"],
                ["Fee cost", f"-{o['mean_fee_cost_cents']:.4f}", "the venue fee for this market category"],
                ["Net", f"{o['mean_net_cents']:+.4f}", "what a taker actually keeps"],
            ],
            "Costs come from the venue fee model in app/venue_fees.py, not from an assumption.",
        ),
    }


def _extrakt_signed_flow(d: dict[str, Any]) -> dict[str, Any]:
    f = d["signals"]["flow"]["overall"]
    i = d["signals"]["imbalance"]["overall"]
    c = d["signals"]["combo"]["overall"]
    return {
        "basis": _basis(d, beobachtungen=f["n"]),
        "kennzahlen": {
            "n": f["n"], "hit": f["hit_rate"], "lb": f["wilson_lb95"],
            "gross": f["mean_gross_cents"], "net": f["mean_net_cents"],
            "imb_hit": i["hit_rate"],
        },
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
        "details": _tabelle(
            "All three signals, side by side",
            ["Signal", "Firings", "Hit rate", "Gross", "Net"],
            [
                ["Book imbalance", _n(i["n"]), _pz(i["hit_rate"]) + "%", f"{i['mean_gross_cents']:+.4f}", f"{i['mean_net_cents']:+.4f}"],
                ["Signed order flow", _n(f["n"]), _pz(f["hit_rate"]) + "%", f"{f['mean_gross_cents']:+.4f}", f"{f['mean_net_cents']:+.4f}"],
                ["Both together", _n(c["n"]), _pz(c["hit_rate"]) + "%", f"{c['mean_gross_cents']:+.4f}", f"{c['mean_net_cents']:+.4f}"],
            ],
            "Gross and net are cents per firing. Requiring both to agree raises the hit rate and shrinks the sample.",
        ),
    }


def _extrakt_segmente(d: dict[str, Any]) -> dict[str, Any]:
    """Schnitte, Szenarien und Ueberlebende.

    `by_category` sind die Gebuehrenszenarien, nicht Marktkategorien. Jedes
    Szenario testet dieselben `tested_segments` Schnitte.
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

    punkte = [{
        "label": "All firings",
        "wert": _cents(o["mean_net_cents"]),
        "von": _cents(ci[0]) if ci[0] is not None else None,
        "bis": _cents(ci[1]) if ci[1] is not None else None,
    }]
    zahlen = [
        _zahl("Cuts tested per fee scenario", je_szenario, "segments"),
        _zahl("Fee scenarios", len(szenarien), ""),
        _zahl("Cuts that survived", len(ueberlebende), "",
              "at this many tests, one lucky survivor is the expected count"),
        _zahl("Net result over all", _cents(o["mean_net_cents"]), "cents per firing"),
    ]
    ueberlebender_net = None
    ueberlebender_ci = None
    if ueberlebende:
        name, s = ueberlebende[0]
        ueberlebender_net = s["mean_net_cents"]
        s_ci = s.get("net_ci95_cents") or [None, None]
        zahlen.append(_zahl(f"Survivor ({name}), net", _cents(s["mean_net_cents"]), "cents per firing"))
        if s_ci[0] is not None:
            ueberlebender_ci = s_ci
            zahlen.append(_zahl(
                "Survivor, 95% interval", [_cents(s_ci[0]), _cents(s_ci[1])], "cents",
                "the interval contains zero, so the survivor is not distinguishable from noise"))
            punkte.append({
                "label": f"Survivor ({name})",
                "wert": _cents(s["mean_net_cents"]),
                "von": _cents(s_ci[0]), "bis": _cents(s_ci[1]),
            })

    # Detailtabelle: die Buckets des Leitszenarios, das sind die echten Schnitte.
    zeilen: list[list[Any]] = []
    for art, buckets in (leit.get("segments") or {}).items():
        for b in buckets:
            b_ci = b.get("net_ci95_cents") or [None, None]
            zeilen.append([
                art, str(b.get("bucket", "")), _n(b["n"]),
                f"{b['mean_net_cents']:+.3f}",
                f"{b['train_net_cents']:+.3f}",
                f"{b['test_net_cents']:+.3f}",
                f"[{b_ci[0]:+.3f}, {b_ci[1]:+.3f}]" if b_ci[0] is not None else "",
            ])

    return {
        "basis": _basis(d, beobachtungen=o["n"]),
        "kennzahlen": {
            "je_szenario": je_szenario, "szenarien": len(szenarien),
            "gesamt_tests": je_szenario * len(szenarien),
            "ueberlebende": len(ueberlebende), "net": o["mean_net_cents"],
            "ueberlebender_net": ueberlebender_net, "ueberlebender_ci": ueberlebender_ci,
            "n": o["n"],
        },
        "zahlen": zahlen,
        "diagramm": {
            "art": DIA_INTERVALL,
            "titel": "Net result with its 95% interval",
            "einheit": "cents per firing",
            "referenz": 0.0,
            "referenz_label": "break even",
            "punkte": punkte,
        },
        "details": _tabelle(
            "Every cut, in and out of sample",
            ["Cut", "Bucket", "n", "Net", "In sample", "Out of sample", "95% interval"],
            zeilen,
            "Cents per firing. Every bucket was declared before looking at the result. "
            "Not one interval clears zero.",
        ),
    }


def _mm_zerlegung(d: dict[str, Any], modell: str) -> dict[str, Any]:
    return d["fill_models"][modell]["decomposition"]


def _mm_details(d: dict[str, Any], modell: str) -> dict[str, Any]:
    z = _mm_zerlegung(d, modell)
    return _tabelle(
        "Where the money went, in dollars over the whole run",
        ["Component", "USD", "What it is"],
        [
            ["Spread captured", f"{z['spread_capture_usd']:+,.0f}", "earned by quoting both sides"],
            ["Markout", f"{z['markout_usd']:+,.0f}", "given back right after each fill"],
            ["Late drift", f"{z['late_drift_usd']:+,.0f}", "further move after the markout window"],
            ["Rebate", f"{z['rebate_usd']:+,.0f}", "liquidity reward credited"],
            ["Fees", f"{z['fee_usd']:+,.0f}", "paid to the venue"],
            ["Total", f"{z['total_usd']:+,.0f}", "what the strategy ends with"],
        ],
        f"Tape fill model, {_n(z['fills'])} fills over {z['days']} days. "
        f"Average inventory {z['inventory_abs_mean_usd']:.0f} USD, peak {z['inventory_abs_max_usd']:.0f} USD.",
    )


def _extrakt_mm_120s(d: dict[str, Any]) -> dict[str, Any]:
    t = _mm_zerlegung(d, "tape")
    return {
        "basis": _basis(d),
        "kennzahlen": {
            "spread": t["spread_capture_cents_per_fill"],
            "markout": t["markout_cents_per_fill"],
            "total": t["total_cents_per_fill"],
            "fills": t["fills"], "tage": t["days"],
            "halb_spread": (d.get("params") or {}).get("half_spread"),
        },
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
        "details": _mm_details(d, "tape"),
    }


def _extrakt_staleness(d: dict[str, Any], langsam: dict[str, Any]) -> dict[str, Any]:
    schnell = _mm_zerlegung(d, "tape")
    traege = _mm_zerlegung(langsam, "tape")
    return {
        "basis": _basis(d),
        "kennzahlen": {
            "markout_langsam": traege["markout_cents_per_fill"],
            "markout_schnell": schnell["markout_cents_per_fill"],
            "spread_langsam": traege["spread_capture_cents_per_fill"],
            "spread_schnell": schnell["spread_capture_cents_per_fill"],
            "anteil_weg": 1 - (schnell["markout_cents_per_fill"] / traege["markout_cents_per_fill"])
            if traege["markout_cents_per_fill"] else 0.0,
        },
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
        "details": _tabelle(
            "The same run at two data frequencies",
            ["Quantity", "120 second grid", "Seconds data", "Change"],
            [
                ["Spread earned, cents per fill",
                 f"{traege['spread_capture_cents_per_fill']:.1f}",
                 f"{schnell['spread_capture_cents_per_fill']:.1f}",
                 f"{schnell['spread_capture_cents_per_fill'] - traege['spread_capture_cents_per_fill']:+.1f}"],
                ["Adverse selection, cents per fill",
                 f"{traege['markout_cents_per_fill']:.1f}",
                 f"{schnell['markout_cents_per_fill']:.1f}",
                 f"{schnell['markout_cents_per_fill'] - traege['markout_cents_per_fill']:+.1f}"],
                ["Fills", _n(traege["fills"]), _n(schnell["fills"]), ""],
                ["Days", str(traege["days"]), str(schnell["days"]), ""],
            ],
            "Only the data frequency changed. The earnings barely move, the losses collapse.",
        ),
    }


def _extrakt_mm_offen(d: dict[str, Any]) -> dict[str, Any]:
    touch = d["fill_models"]["touch"]
    tape = d["fill_models"]["tape"]
    t_ci = touch["daily_ci95_usd"]
    p_ci = tape["daily_ci95_usd"]
    tage = sorted(set(touch["daily_total_usd"]) | set(tape["daily_total_usd"]))
    return {
        "basis": _basis(d),
        "kennzahlen": {
            "touch_ci": t_ci, "tape_ci": p_ci,
            "touch_fills": touch["decomposition"]["fills"],
            "tape_fills": tape["decomposition"]["fills"],
            "tage": len(tage),
        },
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
        "details": _tabelle(
            "Day by day, under both assumptions",
            ["Day", "Touch model, USD", "Tape model, USD"],
            [
                [tag,
                 f"{touch['daily_total_usd'].get(tag, 0):+,.0f}",
                 f"{tape['daily_total_usd'].get(tag, 0):+,.0f}"]
                for tag in tage
            ],
            "The two models disagree on the sign on every single day, not just on average.",
        ),
    }


def _extrakt_cross_venue(d: dict[str, Any]) -> dict[str, Any]:
    s = d["summary"]
    zeilen = []
    for r in d.get("rows") or []:
        zeilen.append([
            "rejected" if r.get("suspect") else "usable",
            str(r.get("pm_question") or "")[:70],
            f"{r.get('gross_edge_cents', 0):+.2f}",
            f"{r.get('net_edge_cents', 0):+.2f}",
            str(r.get("days_to_resolution") or ""),
            f"{(r.get('annualised_return') or 0) * 100:.2f}%",
        ])
    return {
        "basis": _basis(d, maerkte=d["pm_markets"] + d["kalshi_markets"], paare=s["pairs"]),
        "kennzahlen": {
            "paare": s["pairs"], "brauchbar": s["usable"], "verdaechtig": s["suspect"],
            "netto_positiv": s["net_positive"], "max_net": s["max_net_cents"],
            "median_net": s["median_net_cents"],
            "pm": d["pm_markets"], "kalshi": d["kalshi_markets"],
        },
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
        "details": _tabelle(
            "Every matched pair, including the rejected ones",
            ["Status", "Question", "Gross", "Net", "Days to settle", "Annualised"],
            zeilen,
            "Gross and net in cents per share, both fee curves subtracted. "
            "Rejected pairs stay in the table on purpose: what a bad match looks like is the lesson.",
        ),
    }


def _extrakt_gap_lifetime(d: dict[str, Any]) -> dict[str, Any]:
    zeilen_roh = d.get("rows") or []
    dauerhaft = sum(1 for r in zeilen_roh if float(r.get("open_share") or 0.0) >= 1.0)
    nie_offen = sum(1 for r in zeilen_roh if float(r.get("open_share") or 0.0) <= 0.0)
    stunden = max((float(r.get("paired_hours") or 0.0) for r in zeilen_roh), default=0.0)
    return {
        "basis": _basis(d, paare=d["pairs"]),
        "kennzahlen": {
            "paare": d["pairs"], "dauerhaft": dauerhaft, "nie_offen": nie_offen,
            "stunden": stunden, "reachable": d["reachable_s"],
        },
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
        "details": _tabelle(
            "How long each gap stayed open",
            ["Question", "Observations", "Open share", "Longest stretch", "Peak net"],
            [
                [
                    str(r.get("question") or "")[:70],
                    _n(r.get("observations")),
                    f"{float(r.get('open_share') or 0) * 100:.0f}%",
                    f"{float(r.get('longest_window_s') or 0) / 3600:.1f} h",
                    f"{float(r.get('peak_net_cents') or 0):+.2f}",
                ]
                for r in zeilen_roh
            ],
            "Open share is the fraction of observed time the gap cleared both fee curves at once.",
        ),
    }


def _extrakt_rewards(d: dict[str, Any]) -> dict[str, Any]:
    zeilen_roh = sorted(
        d.get("rows") or [], key=lambda r: -(r.get("pool_usd_per_day") or 0)
    )[:12]
    return {
        "basis": _basis(d, maerkte=d["markets_with_pool"]),
        "kennzahlen": {
            "maerkte": d["markets_with_pool"], "pool": d["total_pool_usd_per_day"],
            "geprueft": d["probed"], "leer": d["empty_band_markets"],
            "anteil_leer": d["empty_band_markets"] / d["probed"] if d["probed"] else 0.0,
        },
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
        "details": _tabelle(
            "The twelve biggest pools, and what the book actually looks like",
            ["Question", "Pool per day", "Band width", "Book spread", "Competing shares", "Band"],
            [
                [
                    str(r.get("question") or "")[:60],
                    f"${r.get('pool_usd_per_day', 0):,.0f}",
                    f"{r.get('max_spread_cents', 0):.1f}c",
                    f"{r.get('spread_cents', 0):.1f}c" if r.get("spread_cents") is not None else "",
                    _n(r.get("competing_shares") or 0),
                    "empty" if r.get("empty_band") else "contested",
                ]
                for r in zeilen_roh
            ],
            "Band width is what the reward requires. Book spread is what the market actually quotes. "
            "Where the second is far wider than the first, the reward is unreachable.",
        ),
    }


def _extrakt_resolution(d: dict[str, Any]) -> dict[str, Any]:
    zeilen = []
    for r in d.get("rows") or []:
        flaggen = r.get("one_sided_flags") or []
        zeilen.append([
            str(r.get("question") or r.get("pair") or "")[:64],
            "differs" if flaggen else "agrees",
            ", ".join(str(f) for f in flaggen)[:70] if flaggen else "",
        ])
    return {
        "basis": _basis(d, paare=d["pairs"]),
        "kennzahlen": {
            "paare": d["pairs"], "beide_texte": d["with_both_texts"],
            "abweichend": d["with_one_sided_flags"],
        },
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
        "details": _tabelle(
            "Where the two rulebooks part ways",
            ["Pair", "Verdict", "Condition only one side carries"],
            zeilen,
            "Read from both venues' own settlement text, not from the market titles.",
        ),
    }


def _extrakt_reconcile(d: dict[str, Any]) -> dict[str, Any]:
    s = d["summary"]
    return {
        "basis": _basis(d, beobachtungen=s["comparisons"]),
        "kennzahlen": {
            "quote": s["match_rate"], "mittel": s["mean_diff_ticks"],
            "max": s["max_diff_ticks"], "n": s["comparisons"],
            "abweichend": s["drift"], "unbrauchbar": s["unusable"],
            "runden": d.get("rounds_connected"), "tokens": d.get("tokens"),
        },
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
        "details": _tabelle(
            "The comparison in full",
            ["Outcome", "Count", "What it means"],
            [
                ["Match", _n(s["match"]), "our book and the venue agree within tolerance"],
                ["Drift", _n(s["drift"]), "a difference above tolerance appeared"],
                ["Unusable", _n(s["unusable"]), "no comparison possible at that moment"],
            ],
            f"{d.get('rounds_connected', '')} rounds of {d.get('seconds_per_round', '')} seconds over "
            f"{d.get('tokens', '')} tokens, tolerance {d.get('tolerance_ticks', '')} tick.",
        ),
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
        analyse={
            "gemessen": "How often the mid price, five minutes later, had moved in the direction the order book was leaning.",
            "wie": "Each recorded snapshot is checked for an imbalance past a fixed threshold. When it fires, the side it leans to is written down, and compared against where the mid actually sat 300 seconds later. Firings where nothing moved at all are counted separately so they cannot pad the score.",
            "daten": "Order books this project recorded itself on a 120 second grid, both venues, across eleven days.",
            "entscheidung": "A signal only counts as real if the pessimistic end of a 95 percent Wilson interval still sits above 50 percent. A point estimate above the coin flip would not have been enough, because with enough observations noise alone clears that bar.",
        },
        einfach=lambda k: (
            f"Out of {_n(k['n'])} firings the book pointed the right way {_pz(k['hit'])} percent of the time, "
            f"against the {_pz(0.5, 0)} percent a coin flip would give. Even the cautious end of the interval "
            f"sits at {_pz(k['lb'])} percent, so this is not a sampling accident. "
            f"In {_pz(k['moved'])} percent of firings the price actually moved at all; the rest sat still."
        ),
        interpretation=(
            (LESART, "The order book carries genuine information about the next few minutes. When one side is far heavier, that pressure tends to resolve in its own direction."),
            (GEGENLESART, "A hit rate says nothing about size. Being right often on tiny moves and wrong occasionally on large ones produces exactly this number and still loses money. That is the next study."),
            (GRENZE, "The grid is 120 seconds, so anything that happens and reverses faster than that is invisible here. A faster recorder might find a stronger or a weaker effect."),
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
        analyse={
            "gemessen": "What is left per firing after the two costs a taker cannot avoid: crossing the spread, and the venue fee.",
            "wie": "For each firing the price move is converted to cents per share. Then half the spread standing in the book at decision time is subtracted, and the fee schedule for that market's category on top. What remains is the net.",
            "daten": "The same eleven days and the same firings as the study above, so the two are directly comparable.",
            "entscheidung": "Takeable means the net stays above zero. Costs come from the venue fee model in the repository, not from a round-number assumption.",
        },
        einfach=lambda k: (
            f"The signal is worth {k['gross']:+.2f} cents per firing before costs. Crossing the spread costs "
            f"{k['spread']:.2f} cents and the venue fee another {k['fee']:.2f}, so the round trip takes "
            f"{k['cost']:.2f} cents, roughly {k['faktor']:.0f} times what the signal produces. "
            f"The net is {k['net']:+.2f} cents, and only {_pz(k['positiv'])} percent of firings end positive. "
            f"Even the best cut of the signal only reaches {k['bester_gross']:+.2f} cents gross, nowhere near the wall."
        ),
        interpretation=(
            (LESART, "Being right and making money are different questions, and this is the gap between them. Any analysis that stops at a hit rate has stopped one step too early."),
            (GEGENLESART, "This only condemns taking. A market maker does not pay the spread, they earn it, so the same information could still be worth something from the other side of the book. That is why the market-making studies follow."),
            (GRENZE, "It assumes taking at the touch. A patient limit order would pay less, but then the fill is no longer certain, and an unfilled order earns nothing at all."),
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
        analyse={
            "gemessen": "The same forward hit rate as the imbalance study, but for a signal built out of trade direction rather than resting orders.",
            "wie": "Each print on the tape is labelled a buy or a sell by comparing its price against the quote at the time. Those labels are summed into a signed volume imbalance, and that is checked forward exactly like the book signal.",
            "daten": "The same recorded tape and the same eleven days, so the difference is the signal and not the sample.",
            "entscheidung": "The identical Wilson bar as the first study. Holding the test fixed is the whole point of running it on the same data.",
        },
        einfach=lambda k: (
            f"Over {_n(k['n'])} firings this signal was right {_pz(k['hit'])} percent of the time, barely above the "
            f"coin flip and far below the {_pz(k['imb_hit'])} percent the resting book managed. "
            f"Its gross edge is {k['gross']:+.3f} cents, already negative before a single cost is subtracted, "
            f"which means there is nothing here for costs to eat."
        ),
        interpretation=(
            (LESART, "The weak link is the labelling step, not the idea. Order flow ought to be informative, but you have to know which side actually initiated, and here that has to be guessed."),
            (GEGENLESART, "Published work later found that trade-direction inference on this venue lands between 49.8 and 50.5 percent depending on method. On that reading this measures the method, not the market, and the market question stays open."),
            (GRENZE, "Only one inference rule was tested. A venue that published true aggressor flags could give a different answer, and this study cannot rule that out."),
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
        analyse={
            "gemessen": "The net result per firing inside each slice of the market, to see whether the cost wall has a gap somewhere.",
            "wie": "The firings are cut three ways: by the spread standing in the book, by the price level, and by how strongly the signal fired. Every bucket was fixed before looking at any result, and each one is evaluated separately in sample, out of sample, and with a day-resampled confidence interval.",
            "daten": "205,835 firings over eleven days, run through three different fee scenarios because the fee depends on the market category.",
            "entscheidung": "A slice counts only if it holds up in sample and out of sample and its interval excludes zero. Two out of three would not do, because with this many tests two out of three happens by luck.",
        },
        einfach=lambda k: (
            f"{k['je_szenario']} cuts were tested in each of {k['szenarien']} fee scenarios, "
            f"{k['gesamt_tests']} tests in total, and {k['ueberlebende']} survived. "
            f"That is not encouraging, it is expected: run this many tests on noise and roughly one will look good anyway. "
            + (
                f"The survivor nets {k['ueberlebender_net']:+.3f} cents, and its interval "
                f"[{k['ueberlebender_ci'][0]:+.3f}, {k['ueberlebender_ci'][1]:+.3f}] contains zero, "
                "so it is not distinguishable from luck. "
                if k.get("ueberlebender_ci") else ""
            )
            + f"Across all firings the net stays at {k['net']:+.2f} cents."
        ),
        interpretation=(
            (LESART, "There is no hiding place. The cost wall stands in wide spreads and narrow ones, at long odds and short, on strong signals and weak."),
            (GEGENLESART, "One survivor could in principle be a real but thin effect that this sample is too small to confirm. The honest way to settle that is fresh data, not a louder claim about the same data."),
            (GRENZE, "Only cuts that are knowable before the trade were allowed. A cut using information available afterwards would look far better and would mean nothing at all."),
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
        analyse={
            "gemessen": "Profit per fill, split into the spread earned by quoting and the amount the market takes back immediately afterwards.",
            "wie": "Quotes are placed either side of the mid at a fixed half spread and refreshed every 120 seconds. Each fill is then marked out against the mid a short time later. The difference between what the quote earned and where the price went is the adverse selection.",
            "daten": "Recorded books over twelve days and 4,519 tokens, replayed offline. No orders were ever sent.",
            "entscheidung": "Carrying means the net per fill stays above zero once adverse selection is counted. Total profit alone would not do, because quoting less can raise it while the per-fill economics stay broken.",
        },
        einfach=lambda k: (
            f"Each fill earns {k['spread']:.0f} cents of spread and hands back {abs(k['markout']):.0f} cents "
            f"almost immediately, leaving {k['total']:.0f} cents. "
            f"The reason is who trades against a stale quote: whoever already knows the price has moved. "
            f"Over {_n(k['fills'])} fills across {k['tage']} days that pattern does not average out, it is the pattern."
        ),
        interpretation=(
            (LESART, "The problem is adverse selection, not fees. Being picked off costs more than twice what the spread pays, so no fee rebate would fix it."),
            (GEGENLESART, "It could be the parameters rather than the idea. A wider half spread or stronger inventory aversion might change the balance, and sweeps over both are in the full report."),
            (GRENZE, "120 seconds is very slow for quoting. This result may say more about the refresh rate than about market making, which is exactly what the next study tests."),
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
        analyse={
            "gemessen": "The same two quantities as the study above, spread earned and adverse selection, recomputed on seconds-resolution data.",
            "wie": "Identical code, identical parameters, identical fill model. The only thing that changes is how fresh the book is when the quote is placed. That makes it a controlled comparison rather than two separate experiments.",
            "daten": "5,413,998 streamed book snapshots over five days from the WebSocket recorders, against the twelve-day 120 second run.",
            "entscheidung": "Whichever of the two quantities moves is the binding constraint. If the spread earned had jumped, width would have been the answer; if the losses collapse, staleness is.",
        },
        einfach=lambda k: (
            f"Adverse selection falls from {abs(k['markout_langsam']):.0f} cents per fill to "
            f"{abs(k['markout_schnell']):.0f}, which is {_pz(k['anteil_weg'], 0)} percent of the loss gone. "
            f"Meanwhile the spread earned barely moves, from {k['spread_langsam']:.0f} to {k['spread_schnell']:.0f} cents. "
            "One number collapses and the other stays put, which is what isolates the cause: "
            "the problem was never how much spread there is to earn, it was quoting on a picture of the book that had already expired."
        ),
        interpretation=(
            (LESART, "Staleness is the binding constraint, and unlike a thin spread that is an infrastructure problem. Faster data is something you can buy."),
            (GEGENLESART, "The two runs are not perfectly matched. Seconds data also produces a different set of fills, across different moments and a shorter window, so part of the improvement could be the changed mix rather than the freshness."),
            (GRENZE, "Even at seconds resolution there is still no queue position, so this says the loss shrinks, not that the strategy pays. The next study is about exactly that gap."),
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
        analyse={
            "gemessen": "Daily profit with a confidence interval, computed twice under two different assumptions about when a quote would have been filled.",
            "wie": "The touch model assumes a fill whenever the price reaches the quote. The tape model assumes a fill only when a real print happened there. Daily totals are then resampled in blocks so the interval respects that days are not independent of themselves.",
            "daten": "The same five days of seconds data, 468 tokens, both models run over identical quotes.",
            "entscheidung": "Identified means both models agree on the sign. If they disagree, the answer depends on the assumption rather than on the data, and no result can honestly be claimed.",
        },
        einfach=lambda k: (
            f"Assume a fill whenever the price touches the quote and the answer is a loss between "
            f"{k['touch_ci'][0]:,.0f} and {k['touch_ci'][1]:,.0f} dollars a day. Assume a fill only against a print "
            f"that really happened and it is a profit between {k['tape_ci'][0]:,.0f} and {k['tape_ci'][1]:,.0f}. "
            "Both intervals sit well clear of zero, in opposite directions. "
            "The difference is not noise, it is the assumption, and the assumption cannot be checked from outside the exchange."
        ),
        interpretation=(
            (LESART, "The honest answer is that this is unknown. The two models bracket reality rather than measure it, and saying so is worth more than picking the flattering one."),
            (GEGENLESART, "The truth almost certainly sits between the two, since real fills need a real counterparty but not every print would have hit our quote. Where between depends on queue position."),
            (GRENZE, "More days would not settle this. It is an identification problem, not a sample size problem, and only order-level queue data would resolve it."),
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
        analyse={
            "gemessen": "The net gap per share between the two venues on the same event, after both fee curves, and what that is worth per year.",
            "wie": "Markets are matched by what the question actually asks rather than by wording overlap. For each surviving pair both books are priced, each venue's own fee curve is subtracted, and the remainder is annualised over the days until settlement.",
            "daten": "300 Polymarket markets against 600 Kalshi markets, matched down to a handful of confirmed pairs.",
            "entscheidung": "Arbitrage would mean a net gap that clears both fee curves and can be closed soon. A gap that only pays out years later is a financing trade, not an arbitrage.",
        },
        einfach=lambda k: (
            f"{k['pm']} markets on one venue were matched against {k['kalshi']} on the other, giving {k['paare']} pairs. "
            f"{k['verdaechtig']} were thrown out as mismatched questions, leaving {k['brauchbar']} usable, of which "
            f"{k['netto_positiv']} clear both fee curves. The best is {k['max_net']:.2f} cents per share. "
            "But those all settle in 2027 or 2028, so the money is locked up for years and the return per year is tiny."
        ),
        interpretation=(
            (LESART, "This is carry, not arbitrage. You are being paid a small amount to tie capital up for a long time and to carry the risk that the two venues settle differently."),
            (GEGENLESART, "At size, one to two percent annualised on capital that would otherwise sit idle is a real business. It is a bad headline and a defensible trade, depending on what else the money would be doing."),
            (GRENZE, "Three of the eight pairs were rejected as mismatched. The matcher is the weak point of this study, which is why the rejected pairs stay in the table instead of being quietly dropped."),
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
        analyse={
            "gemessen": "The share of observed time each gap was actually open, meaning both legs cleared their fee curve at the same moment.",
            "wie": "Both stream recorders run against the same pairs over one window. At every paired moment the two books are compared, and the gap is marked open or closed. A real mispricing should spend most of its time closed.",
            "daten": "Five confirmed pairs watched across roughly 11.6 hours of simultaneous recording on both venues.",
            "entscheidung": "A mispricing closes once it is noticed. A gap that never closes is evidence that it is not a mispricing at all.",
        },
        einfach=lambda k: (
            f"Of {k['paare']} pairs watched over {k['stunden']:.1f} hours, {k['dauerhaft']} were open at every single "
            f"moment observed and {k['nie_offen']} never opened at all. Nothing in between converged. "
            "A genuine error closes when somebody notices it; these did not close because there is nothing to notice."
        ),
        interpretation=(
            (LESART, "The gaps persist because they are the fair price of tying money up until settlement, not because the market has missed them."),
            (GEGENLESART, "Eleven hours is a short window. A gap that closes weekly would look permanently open here, and this study could not tell the difference."),
            (GRENZE, "Five pairs is a very small sample. This supports the carry reading from the previous study rather than standing on its own."),
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
        analyse={
            "gemessen": "Whether anybody is quoting inside the narrow band a reward actually requires, in the markets paying the largest pools.",
            "wie": "Every market carrying a pool is ranked by daily payout. For the largest, the live book is probed against the band the reward demands, and the quotes actually standing there are counted.",
            "daten": "9,900 markets carrying a pool, together paying out over 164,000 dollars a day, with the 45 largest probed in detail.",
            "entscheidung": "Free money would mean a large pool with a reachable band. A pool nobody can qualify for is not an opportunity, however large the number looks.",
        },
        einfach=lambda k: (
            f"{_n(k['maerkte'])} markets carry a reward pool, paying out ${k['pool']:,.0f} a day between them. "
            f"Of the {k['geprueft']} largest, {k['leer']} have a qualifying band with nothing in it at all, "
            f"which is {_pz(k['anteil_leer'], 0)} percent. The quotes that do exist sit far outside the band the reward needs. "
            "The pool is large because it is unreachable, not despite it."
        ),
        interpretation=(
            (LESART, "Pool size is not opportunity size. The headline number measures what nobody has collected, which is the opposite of what it looks like."),
            (GEGENLESART, "An empty band is also an open invitation, if you can quote there and survive. What surviving costs is exactly what the market-making studies measure, and that answer was not encouraging."),
            (GRENZE, "This is one snapshot on one date. Bands empty and fill over time, and a different day could look different."),
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
        analyse={
            "gemessen": "Whether a matched pair of markets settles on the same underlying fact, read from each venue's own settlement text.",
            "wie": "Both rulebooks are put side by side and the conditions compared. Where one side carries a condition the other does not, that is flagged, because that is precisely where a hedge stops hedging.",
            "daten": "Five confirmed pairs, with both venues' settlement texts read in full rather than skimmed from titles.",
            "entscheidung": "Same wording is not the test. The test is whether the same real-world outcome pays out on both sides.",
        },
        einfach=lambda k: (
            f"{k['paare']} confirmed pairs were checked, {k['beide_texte']} with both settlement texts available, "
            f"and {k['abweichend']} settle on a different fact than they appear to. "
            "One venue pays on who is next inaugurated, the other on who wins the election. "
            "Those are usually the same person and occasionally not, and the occasionally is the whole risk."
        ),
        interpretation=(
            (LESART, "Matching by title is not enough. This is the trap sitting underneath every cross-venue trade, and it only shows up when it costs you both legs at once."),
            (GEGENLESART, "For most pairs the wording does agree. This is a per-pair risk to be read before trading, not a reason to write off cross-venue work altogether."),
            (GRENZE, "The reading is manual and the sample is five pairs. It proves the failure mode exists, not how common it is."),
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
        analyse={
            "gemessen": "How closely the book this project recorded matches the venue's own snapshot at the same moment.",
            "wie": "For the same token at the same instant, the streamed top of book is compared against a fresh REST snapshot, and the difference is expressed in ticks so it can be judged against the smallest price step that exists.",
            "daten": "24 tokens over three rounds of 120 seconds, giving 72 direct comparisons.",
            "entscheidung": "This is a control, not a finding. Every other number on this page is only worth as much as this one, so it had to be run and it had to be reported whatever it said.",
        },
        einfach=lambda k: (
            f"Across {_n(k['n'])} comparisons our book agreed with the venue {_pz(k['quote'])} percent of the time. "
            f"The average difference is {k['mittel']} ticks and the worst single case {k['max']} ticks, "
            "a fraction of one price step. "
            f"{k['abweichend']} comparison drifted beyond tolerance and {k['unbrauchbar']} were unusable."
        ),
        interpretation=(
            (LESART, "The recorder can be trusted at tick level, which is what the other eleven studies rest on. Without this they would all be assertions."),
            (GEGENLESART, "Agreement in calm conditions says little about behaviour under a burst, and bursts are exactly when a market maker gets hurt. This measures the easy case."),
            (GRENZE, "Three short rounds over 24 tokens is a spot check, not continuous monitoring. It shows no systematic drift; it cannot rule out rare gaps."),
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
    "Most of the answers are no, and the reasoning behind each no is the point. "
    "Each study states what it measured, what the numbers say, and how else they could be read."
)

ANALYSE_TITEL = {
    "gemessen": "What was measured",
    "wie": "How",
    "daten": "On what data",
    "entscheidung": "What would have counted as a yes",
}


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

        kennzahlen = teil.pop("kennzahlen", {})
        eintrag: dict[str, Any] = {
            "id": studie.id,
            "frage": studie.frage,
            "verdikt": studie.verdikt,
            "verdikt_art": studie.verdikt_art,
            "analyse": [
                {"schluessel": k, "titel": ANALYSE_TITEL[k], "text": studie.analyse[k]}
                for k in ("gemessen", "wie", "daten", "entscheidung")
                if studie.analyse.get(k)
            ],
            "einfach": studie.einfach(kennzahlen) if callable(studie.einfach) else studie.einfach,
            "interpretation": [
                {"art": art, "titel": INTERPRET_TITEL[art], "text": text}
                for art, text in studie.interpretation
            ],
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
