"""Baut die Nutzlast fuer ``public/data/literature.json``.

``docs/research/ertragsquellen_2026-07-31.md`` stellt die eigenen
Messungen der Microstructure-Studien neben die veroeffentlichte Literatur
und ordnet, welche Ertragsquellen die Daten stuetzen und welche sie
ausschliessen. Die Website braucht daraus eine Seite mit drei Bloecken:
was die eigenen Daten zeigen, was die Literatur sagt, was daraus folgt.

Die Zahlen in dieser Nutzlast sind kuratiert eingetragen, weil ihre Quelle
ein Text ist und keine Tabelle. Damit sie nicht vom Text abdriften, prueft
``tests/test_literature_context.py`` jede Zahl gegen den Markdown-Text:
was dort nicht steht, darf hier nicht stehen. Die Studien-IDs verweisen auf
die Karten der Microstructure-Seite, deren Zahlen aus den Artefakten kommen.

Streamlit-frei.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from app.research_payload import jetzt_iso, lies_text

QUELLE_MD = Path("docs/research/ertragsquellen_2026-07-31.md")
STAND = "2026-07-31"

#: Eigene Befunde: je Satz die Zahlen, die er traegt, und die Karte, deren
#: Artefakt sie liefert. Die Zahlen muessen woertlich im Markdown stehen.
EIGENE = [
    {
        "titel": "The signal is real and too small",
        "text": "Book imbalance calls the next five minutes right 55.2 percent of the time (Wilson lower bound 55.0) across 1.0 million observations. The mean gross edge is 0.03 to 0.13 cents per signal; a taker round trip costs 2.58 cents, of which 1.65 cents is fee and 0.94 cents is spread.",
        "zahlen": ["55.2", "55.0", "1.0 million", "0.03 to 0.13", "2.58", "1.65", "0.94"],
        "studie": "imbalance-takeable",
    },
    {
        "titel": "No segment flips the sign",
        "text": "34 cuts knowable before the trade, three fee categories. In the fee-free category exactly one segment survives in and out of sample, with a confidence interval that includes zero: the expected false-positive count at 34 tests.",
        "zahlen": ["34"],
        "studie": "edge-segments",
    },
    {
        "titel": "Adverse selection is a latency problem",
        "text": "At a 120-second requote the quoting earns 148 cents of spread per fill and loses 362 to 698 cents per fill to better-informed counterparties. On seconds data, same code and parameters, the markout falls from 362 to 70 cents while spread earned barely moves, 138 against 148.",
        "zahlen": ["120-second", "148", "362", "698", "70", "138"],
        "studie": "mm-staleness",
    },
    {
        "titel": "Latency explains the size, not the sign",
        "text": "With five days the daily block bootstrap runs and puts the two fill models on opposite sides of zero: touch (-12,121, -2,413) USD per day, tape (+881, +5,889). What separates them is queue position, which no number of calendar days supplies.",
        "zahlen": ["-12,121", "-2,413", "+881", "+5,889"],
        "studie": "mm-identified",
    },
    {
        "titel": "The signal does not help the market maker",
        "text": "Quoting only the side the imbalance favours does not lower markout per fill on two-minute data (minus 361 against minus 365 cents); on five days of seconds data it is worse, minus 82 against minus 70, and the total drops from 16,032 to 11,007 USD.",
        "zahlen": ["361", "365", "82", "16,032", "11,007"],
        "studie": "mm-identified",
    },
]

#: Externe Studien, wie der Text sie zitiert.
LITERATUR = [
    {
        "autoren": "Akey, Gregoire, Harvie and Martineau",
        "quelle": "SSRN 6443103, dataset public under CC-BY",
        "venue": "Polymarket",
        "stichprobe": "2.47 million users, 588 million trades",
        "befund": "68.8 percent of users lose money. Winners post limit orders, losers take with market orders.",
        "zahlen": ["2.47 million", "588 million", "68.8"],
        "kennzahl": {"label": "users who lose money", "wert": 68.8, "einheit": "%"},
    },
    {
        "autoren": "Bartlett and O'Hara",
        "quelle": "SSRN 6615739, 'Adverse Selection in Prediction Markets: Evidence from Kalshi'",
        "venue": "Kalshi",
        "stichprobe": "41.6 million trades",
        "befund": "Market makers earn twice as much per contract in single markets. The exploitable axis is the YES/NO skew, not favourite against longshot.",
        "zahlen": ["41.6 million"],
        "kennzahl": None,
    },
    {
        "autoren": "Buergi, Deng and Whelan",
        "quelle": "CEPR DP20631",
        "venue": "Polymarket",
        "stichprobe": "",
        "befund": "Takers lose around 32 percent, makers around 10 percent.",
        "zahlen": ["32", "10"],
        "kennzahl": {"label": "taker loss vs maker loss", "wert": [-32, -10], "einheit": "%"},
    },
]

#: Scheinbare Anomalien, die schon erklaert sind.
ANOMALIEN = [
    {
        "titel": "Near-certain contracts are not mispriced",
        "text": "The discount is a funding premium of 3.06 to 6.89 percent annually, because the capital is locked until resolution. After adjusting for it the significance disappears.",
        "quelle": "Gebele and Matthes, arXiv 2605.31431",
        "zahlen": ["3.06", "6.89"],
    },
    {
        "titel": "Overpriced longshots exist and sit behind the spread",
        "text": "They are about eight times smaller than the spread you would have to cross to reach them: the median half spread below 10 cents is 1,818 basis points.",
        "quelle": "Dubach, arXiv 2604.24366, preregistered",
        "zahlen": ["1,818"],
    },
    {
        "titel": "Trade direction on Polymarket is near-random to infer",
        "text": "Tick rule 49.83 percent, bulk volume 50.51 percent. Our own flow signal from the polled tape reached 51.3 percent, and the two fit together: analyses built on inferred trade direction measure little more than coin flips.",
        "quelle": "Dubach, arXiv 2604.24366",
        "zahlen": ["49.83", "50.51", "51.3"],
    },
]

#: Die dritte Ertragsquelle, gemessen am 2026-07-31.
PROGRAMM = {
    "titel": "The revenue stream that appears in no PnL calculation",
    "text": "Polymarket pays makers for presence near the mid, fill or no fill. On 2026-07-31, 9,900 markets carried a pool, 164,661 USD per day in total; median 4.00 USD per market and day, largest pool 1,770. Maker rebates of 15 to 25 percent of taker fees stack on top. The follow-up study applied the obvious lever, selecting by pool size, and found that of the 45 largest pools 14 have a completely empty qualifying band and quote 1 to 64 cents wide against a 2.5 cent band: the venue is buying liquidity that does not otherwise exist, and adverse selection is the price.",
    "zahlen": ["9,900", "164,661", "4.00", "1,770", "15 to 25", "45", "14", "1 to 64", "2.5"],
    "studie": "rewards",
}

#: Rangfolge der Ertragspfade, wie der Text sie zieht.
RANGFOLGE = [
    {"rang": 1, "pfad": "Providing liquidity, requoted fast enough", "stuetze": "own measurement and three independent studies", "text": "The bottleneck is demonstrably the staleness of the quote, not its width."},
    {"rang": 2, "pfad": "Programme revenue as its own stream", "stuetze": "own measurement of the reward pools", "text": "Rewards, rebates and open-interest compensation do not depend on a forecast and belong reported separately."},
    {"rang": 3, "pfad": "Directional bets on book signals", "stuetze": "ruled out by own measurement", "text": "The edge is real and too small, and no cut knowable before the trade changes that."},
]

GRENZEN = (
    "Eleven days of REST data and five days of seconds data, a slice of the most active markets, paper simulation without "
    "queue position and without partial fills. Queue position is now the binding limit rather than sample size; the "
    "pre-registered queue study on the Pre-registrations page is the test of exactly that."
)


def alle_zahlen() -> list[str]:
    """Jede kuratierte Zahl, fuer die Drift-Pruefung gegen den Text."""
    raus: list[str] = []
    for e in EIGENE:
        raus.extend(e["zahlen"])
    for lit in LITERATUR:
        raus.extend(lit["zahlen"])
    for a in ANOMALIEN:
        raus.extend(a["zahlen"])
    raus.extend(PROGRAMM["zahlen"])
    return raus


def kernsatz(md: str) -> str:
    """Der Absatz unter 'The finding in one sentence'."""
    if "## The finding in one sentence" not in md:
        return ""
    teil = md.split("## The finding in one sentence", 1)[1].split("## ", 1)[0]
    return " ".join(z.strip() for z in teil.strip().splitlines() if z.strip())


def build_payload(root: Path | str = ".", *, jetzt: datetime | None = None) -> dict[str, Any]:
    wurzel = Path(root)
    pfad = wurzel / QUELLE_MD
    md = lies_text(pfad) if pfad.exists() else ""
    return {
        "hinweis": HINWEIS,
        "einleitung": kernsatz(md) or EINLEITUNG,
        "stand_utc": jetzt_iso(jetzt),
        "stand_text": STAND,
        "kennzeichnung": "research/frozen",
        "fehlend": [] if md else [QUELLE_MD.as_posix()],
        "eigene": [dict(e) for e in EIGENE],
        "literatur": [dict(lit) for lit in LITERATUR],
        "anomalien": [dict(a) for a in ANOMALIEN],
        "programm": dict(PROGRAMM),
        "rangfolge": [dict(r) for r in RANGFOLGE],
        "grenzen": GRENZEN,
        "diagramme": {
            "wer_verliert": {
                "titel": "Who loses on prediction markets, per the literature",
                "einheit": "%",
                "punkte": [
                    {"label": "Polymarket users losing money (Akey et al.)", "wert": 68.8, "farbe": "var(--neg-soft)"},
                    {"label": "Taker loss (Buergi et al.)", "wert": -32.0, "farbe": "var(--neg)"},
                    {"label": "Maker loss (Buergi et al.)", "wert": -10.0, "farbe": "var(--warn)"},
                ],
            },
            "edge_gegen_kosten": {
                "titel": "Own measurement: gross edge against the cost of collecting it",
                "einheit": "cents per signal",
                "punkte": [
                    {"label": "Gross edge, imbalance (upper end)", "wert": 0.13, "farbe": "var(--pos)"},
                    {"label": "Fee leg of a taker round trip", "wert": -1.65, "farbe": "var(--neg)"},
                    {"label": "Spread leg", "wert": -0.94, "farbe": "var(--neg)"},
                    {"label": "Round trip", "wert": -2.58, "farbe": "var(--neg)"},
                ],
            },
        },
        "report": QUELLE_MD.as_posix(),
    }


HINWEIS = (
    "Own measurements placed against the published literature, as of 2026-07-31. The numbers here are quoted from that note; "
    "the note's own figures come from the Microstructure studies, each linked."
)
EINLEITUNG = (
    "Predicting direction works measurably and does not pay: the gross edge of the best book signal is about two orders of "
    "magnitude smaller than the cost of collecting it. What remains is the other side of the same transaction, posting the "
    "spread instead of paying it."
)
