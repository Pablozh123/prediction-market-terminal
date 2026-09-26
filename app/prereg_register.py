"""Baut die Nutzlast fuer ``public/data/preregistrations.json``.

Das Register der praeregistrierten Tests dieses Projekts, wie es
``docs/research/preregistrations.md`` fuehrt, plus die Studien, die daran
haengen:

* der Echtgeld-Pilot (Regeln eingefroren 2026-05-02, Handelsfenster zu am
  2026-08-01, eigene Seite ``#research/pilot``),
* die Queue-Studie zum Market Making (intern eingefroren 2026-09-03,
  Testfenster 2026-09-04 bis 2026-09-17; das Trainingsfenster aus
  ``docs/research/mm_queue_train.json`` waehlt den Parametersatz),
* die Track-Record-Validierung (AsPredicted-Entwurf, noch nicht eingereicht).

Der Status der Queue-Studie haengt am Datum: vor dem Testfenster
"eingefroren", waehrend "Testfenster laeuft, Tag k von 14", danach "wartet
auf die einmalige Auswertung". Das Datum kommt von aussen (``jetzt``),
damit der Test es setzen kann.

Prosa kuratiert, Zahlen aus dem Artefakt. Streamlit-frei.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from app.research_payload import jetzt_iso, lies_json, lies_text, n_text, tabelle, zahl

REPORT_DIR = Path("docs/research")
REGISTER_MD = "preregistrations.md"
QUEUE_PREREG_MD = "preregistration_mm_queue_2026-09-03.md"
QUEUE_TRAIN_JSON = "mm_queue_train.json"
ASPREDICTED_MD = "aspredicted_draft_track_record_validation.md"

STATUS_ABGESCHLOSSEN = "abgeschlossen"
STATUS_EINGEFROREN = "eingefroren"
STATUS_LAEUFT = "laeuft"
STATUS_WARTET = "wartet"
STATUS_ENTWURF = "entwurf"
STATUS_TEXT = {
    STATUS_ABGESCHLOSSEN: "COMPLETED",
    STATUS_EINGEFROREN: "FROZEN",
    STATUS_LAEUFT: "TEST WINDOW RUNNING",
    STATUS_WARTET: "AWAITING THE ONE SCORING",
    STATUS_ENTWURF: "DRAFT",
}

#: Der Pilot traegt seine Daten aus dem Protokoll; die Seite dazu ist die
#: Pilot-Seite. Hier steht nur der Registereintrag.
PILOT = {
    "id": "pilot",
    "titel": "Small-stake field test of two tail-fade signal arms",
    "eingefroren": "2026-05-02",
    "fenster": "2026-05-02 to 2026-08-01",
    "extern": "internal, git timestamp",
    "status": STATUS_ABGESCHLOSSEN,
    "ergebnis": "Trading window closed 2026-08-01; every trade and its rule adherence is on the Pilot page. The stake was halved against the frozen text and is reported as a deviation.",
    "seite": "research/pilot",
    "dokument": "docs/research/preregistrations.md",
}

_DATUM = re.compile(r"(\d{4}-\d{2}-\d{2})")


def _policy(md: str) -> list[str]:
    """Die nummerierten Punkte unter '## Policy'."""
    teil = md.split("## Policy", 1)[1].split("## ", 1)[0] if "## Policy" in md else ""
    return [re.sub(r"^\d+\.\s*", "", z).strip() for z in teil.splitlines() if re.match(r"^\d+\.", z.strip())]


def _testfenster(prereg_md: str) -> tuple[str, str]:
    """Von/bis des Testfensters aus dem Preregistrierungstext."""
    m = re.search(r"Test window:\s*(\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2})", prereg_md)
    return (m.group(1), m.group(2)) if m else ("", "")


def queue_status(von: str, bis: str, heute: date) -> tuple[str, str]:
    """Status und Satz zum Testfenster am Stichtag."""
    try:
        d_von = date.fromisoformat(von)
        d_bis = date.fromisoformat(bis)
    except ValueError:
        return STATUS_EINGEFROREN, "test window not dated"
    tage = (d_bis - d_von).days + 1
    if heute < d_von:
        return STATUS_EINGEFROREN, f"test window opens {von}"
    if heute <= d_bis:
        return STATUS_LAEUFT, f"day {(heute - d_von).days + 1} of {tage}, closes {bis}"
    return STATUS_WARTET, f"test window closed {bis}; scored once with the frozen parameters, reported whatever it says"


def _queue_eintrag(root: Path, heute: date) -> dict[str, Any]:
    prereg = lies_text(root / REPORT_DIR / QUEUE_PREREG_MD)
    train = lies_json(root / REPORT_DIR / QUEUE_TRAIN_JSON)
    von, bis = _testfenster(prereg)
    status, satz = queue_status(von, bis, heute)
    eingefroren = _DATUM.search(prereg.split("Frozen", 1)[1]) if "Frozen" in prereg else None
    gewaehlt = train.get("chosen") or {}
    agg = train.get("aggregates") or []
    modelle = list(train.get("models") or [])
    kandidaten = train.get("candidates") or []
    referenz = next((a for a in agg if a.get("model") == "tape"), None)
    tage = train.get("days") or []

    # Kurz, weil das Diagramm den Modellnamen davorsetzt und die Labelspalte
    # bei 44 Zeichen kuerzt: "queue_front · spread 0.005 · gamma 0.08".
    def label(a: dict[str, Any]) -> str:
        return f"spread {a.get('half_spread')} · gamma {a.get('gamma')}"

    # Gruppiertes Balkendiagramm: je Kandidat der Gesamtbetrag in beiden
    # Queue-Modellen. Der Gewinner steht in der Nutzlast unter `gewaehlt`.
    punkte = []
    for k in kandidaten:
        werte = []
        for m in modelle:
            a = next((x for x in agg if x.get("model") == m and x.get("half_spread") == k.get("half_spread") and x.get("gamma") == k.get("gamma")), None)
            werte.append(round(a["total_usd"], 0) if a else None)
        punkte.append({"label": label(k), "werte": werte})
    tagestotale = gewaehlt.get("daily_totals") or {}
    kurve = [{"t": t, "wert": round(float(v), 2)} for t, v in sorted(tagestotale.items())]
    kum = 0.0
    kumuliert = []
    for p in kurve:
        kum += p["wert"]
        kumuliert.append({"t": p["t"], "wert": round(kum, 2)})

    return {
        "id": "mm-queue",
        "titel": "Does symmetric market making pay once queue position is modelled?",
        "eingefroren": eingefroren.group(1) if eingefroren else "2026-09-03",
        "fenster": f"{von} to {bis}",
        "extern": "internal, git timestamp (not submitted to AsPredicted)",
        "status": status,
        "status_satz": satz,
        "hypothese": "H1: symmetric quoting at the chosen parameters earns a positive daily total net of adverse selection, inventory drift and maker rebate, in both queue fill models, over the test window. H0: it does not, in at least one of the two.",
        "primaermetrik": "Daily total USD of the chosen parameter set; success is a daily block-bootstrap 95% interval above zero in both queue_front and queue_back. Fewer than ten scored test days is reported as an insufficient sample.",
        "wahlregel": f"Six candidates (half spread in 0.005, 0.01, 0.02 x gamma in 0, 0.08), scored on every training day; the chosen set is the highest training total in {train.get('choice_model', 'queue_back')} among candidates with at least {n_text(train.get('min_fills_for_choice', 1000))} fills.",
        "gewaehlt": {
            "half_spread": gewaehlt.get("half_spread"), "gamma": gewaehlt.get("gamma"), "latency_s": gewaehlt.get("latency_s"),
            "modell": gewaehlt.get("model"), "fills": gewaehlt.get("fills"), "total_usd": gewaehlt.get("total_usd"),
            "mean_daily_usd": gewaehlt.get("mean_daily_usd"), "daily_ci95_usd": gewaehlt.get("daily_ci95_usd"),
            "spread_capture_cents_per_fill": gewaehlt.get("spread_capture_cents_per_fill"),
            "markout_cents_per_fill": gewaehlt.get("markout_cents_per_fill"),
        },
        "training": {
            "tage": len(tage), "von": tage[0] if tage else "", "bis": tage[-1] if tage else "",
            "kandidaten": len(kandidaten), "modelle": modelle,
        },
        "zahlen": [
            zahl("Training days", len(tage), "", f"{tage[0] if tage else ''} to {tage[-1] if tage else ''}"),
            zahl("Chosen parameters", f"half spread {gewaehlt.get('half_spread')}, gamma {gewaehlt.get('gamma')}", "", f"by the pre-registered rule in {gewaehlt.get('model', '')}"),
            zahl("Training total, chosen set", f"{gewaehlt.get('total_usd', 0):+,.0f}", "USD", f"{n_text(gewaehlt.get('fills', 0))} modelled fills"),
            zahl("Daily 95% interval, training", f"{(gewaehlt.get('daily_ci95_usd') or [0, 0])[0]:,.0f} to {(gewaehlt.get('daily_ci95_usd') or [0, 0])[1]:,.0f}", "USD", "training only, nothing here is a result"),
            zahl(
                f"Tape model reference (half spread {referenz.get('half_spread')}, gamma {referenz.get('gamma')})" if referenz else "Tape model reference",
                f"{referenz.get('total_usd', 0):+,.0f}" if referenz else "—", "USD",
                "the published fill model the queue models replace; at the published parameters, not the chosen set",
            ),
        ],
        "diagramme": {
            "kandidaten": {
                "titel": "Training total per candidate, both queue models",
                "einheit": "USD over the training days",
                "gruppen": modelle,
                "punkte": punkte,
            },
            "tage": {
                "titel": "Chosen set, cumulative training total by day",
                "einheit": "USD",
                "punkte": kumuliert,
            },
        },
        "tabellen": [
            tabelle(
                "Every candidate and model on the training days",
                ["Model", "Half spread", "Gamma", "Fills", "Total (USD)", "Mean/day", "CI95 daily", "Spread/fill (c)", "Markout/fill (c)"],
                [
                    [
                        a.get("model", ""), a.get("half_spread", ""), a.get("gamma", ""), n_text(a.get("fills", 0)),
                        f"{a.get('total_usd', 0):+,.0f}", f"{a.get('mean_daily_usd', 0):+,.0f}",
                        f"({(a.get('daily_ci95_usd') or [0, 0])[0]:,.0f}, {(a.get('daily_ci95_usd') or [0, 0])[1]:,.0f})",
                        f"{a.get('spread_capture_cents_per_fill', 0):+.1f}", f"{a.get('markout_cents_per_fill', 0):+.1f}",
                    ]
                    for a in agg
                ],
                "Training window only. The test window is scored once, with the chosen set, after it closes.",
            ),
        ],
        "seite": "research/microstructure/mm-identified",
        "dokument": f"docs/research/{QUEUE_PREREG_MD}",
        "report": f"docs/research/{QUEUE_TRAIN_JSON.replace('.json', '.md')}",
        "modul": "src/mm_queue_study.py",
    }


def _track_record_eintrag(root: Path) -> dict[str, Any]:
    md = lies_text(root / REPORT_DIR / ASPREDICTED_MD)
    titel = md.splitlines()[0].lstrip("# ").split(":", 1)[-1].strip() if md else "Out-of-sample persistence of the corrected wallet track-record score"
    schwelle = re.search(r"rho\s*(?:>=|≥)\s*\+?([0-9.]+)", md)
    n_min = re.search(r"(?:at least|mindestens)\s+(\d+)\s+wallets", md, re.I)
    frist = re.search(r"by\s+(\d{4}-\d{2}-\d{2})", md)
    return {
        "id": "track-record-validation",
        "titel": titel,
        "eingefroren": "",
        "fenster": "period 2 starts at submission; scored after it closes",
        "extern": "AsPredicted draft, not yet submitted",
        "status": STATUS_ENTWURF,
        "status_satz": "nine-question draft ready; the submission date fixes the split between period 1 and period 2",
        "hypothese": "A wallet's corrected composite track-record score, computed only from period 1, rank-correlates positively with the wallet's realised edge in period 2.",
        "primaermetrik": (
            "Spearman rho between the period-1 score and the period-2 realised edge across wallets"
            + (f"; success is rho at or above +{schwelle.group(1)} with a one-sided p below 0.05" if schwelle else "")
            + (f", on at least {n_min.group(1)} wallets" if n_min else "")
            + (f". Published either way by {frist.group(1)}." if frist else ".")
        ),
        "seite": "wallet",
        "dokument": f"docs/research/{ASPREDICTED_MD}",
    }


def build_payload(root: Path | str = ".", *, jetzt: datetime | None = None) -> dict[str, Any]:
    wurzel = Path(root)
    zeit = jetzt or datetime.now(timezone.utc)
    heute = zeit.date()
    fehlend = [n for n in (REGISTER_MD, QUEUE_PREREG_MD, QUEUE_TRAIN_JSON, ASPREDICTED_MD) if not (wurzel / REPORT_DIR / n).exists()]
    register = lies_text(wurzel / REPORT_DIR / REGISTER_MD) if (wurzel / REPORT_DIR / REGISTER_MD).exists() else ""
    eintraege: list[dict[str, Any]] = [dict(PILOT)]
    if QUEUE_PREREG_MD not in fehlend and QUEUE_TRAIN_JSON not in fehlend:
        eintraege.append(_queue_eintrag(wurzel, heute))
    if ASPREDICTED_MD not in fehlend:
        eintraege.append(_track_record_eintrag(wurzel))
    for e in eintraege:
        e["status_text"] = STATUS_TEXT.get(e["status"], e["status"].upper())
    zaehler = {s: sum(1 for e in eintraege if e["status"] == s) for s in STATUS_TEXT}
    return {
        "hinweis": HINWEIS,
        "einleitung": EINLEITUNG,
        # Die Oberflaeche ist englisch; das Register fuehrt die Policy auf
        # Deutsch. Beide stehen in der Nutzlast, damit der deutsche Wortlaut
        # zitierbar bleibt und die Seite nicht uebersetzt.
        "policy": POLICY_STANDARD,
        "policy_de": _policy(register),
        "stand_utc": jetzt_iso(zeit),
        "kennzeichnung": "research/register",
        "zaehler": zaehler,
        "eintraege": eintraege,
        "fehlend": fehlend,
        "register": f"docs/research/{REGISTER_MD}",
    }


POLICY_STANDARD = [
    "Pre-registered means: hypothesis, primary metric, success threshold, cohort and exclusion rules are fixed before the first look at the outcome period and externally time-stamped.",
    "Results are published in both directions: a failure opens a negative-results register, an insufficient sample is published as such; both are citable results.",
    "Every analysis outside the pre-registered primary test is exploratory and labelled as such everywhere.",
]
HINWEIS = (
    "The register of every test whose rules were written down before its data were seen. "
    "A test window that is still open shows its training numbers only; nothing in a training window is a result."
)
EINLEITUNG = (
    "Three tests on this site were, or are being, run against rules fixed in advance: the small-stake pilot, the queue-position study "
    "on market making, and a validation of the wallet track-record score. This page lists each with its hypothesis, its success rule and where it stands."
)
