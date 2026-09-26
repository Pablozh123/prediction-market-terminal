"""Baut die Nutzlast fuer ``public/data/thesis_results.json``.

Die Bachelorarbeit ("Informationelle Effizienz dezentraler Prognosemaerkte,
am Beispiel Polymarket im Vergleich zu traditionellen Prognosequellen",
FHNW 2026) prueft drei Hypothesen ueber die US-Praesidentschaftswahl 2024
und traegt eine Fallstudie zur Schweizer Volksabstimmung vom 14. Juni 2026
bei. Ihre Ergebnistabellen liegen im Schwester-Repository
``multi-agent-orchestration-informational-efficiency`` unter ``data/results``:

* H1 Prognoseguete: Brier-Score je Tag gegen FiveThirtyEight, Diebold-
  Mariano-Test, Kalibrierung, Umfragenvergleich je Bundesstaat.
* H2 Ereignisreaktion: kumulierte abnormale Preisaenderung um sieben
  kuratierte Ereignisse.
* H3 Wallet-Timing: Lead-Lag-Korrelation und Granger-Tests je Wallet-Tier.
* Fallstudie Schweiz: Polymarket-Preis gegen sieben Umfragen und das
  amtliche Ergebnis.

Fuer die Website braucht es daraus eine einzige Datei, je Abschnitt mit
Frage, Verdikt, Klartext-Erklaerung, Lesarten samt Gegenlesart und Grenze,
Kennzahlen, Diagrammen und Quellpfaden. Prosa ist kuratiert, Zahlen nie:
jede Zahl wird zur Laufzeit aus den Tabellen gelesen.

Wallet-Adressen (``h3_wallet_tiers.csv``) werden nie uebernommen; die
Nutzlast fuehrt Zaehlungen je Tier. ``research_payload.pruefe_redaktion``
bricht ab, wenn doch eine Adresse durchrutscht.

Streamlit-frei. Verbraucher: ``scripts/publish_research_pages.py``.
"""

from __future__ import annotations

import os
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any

from app.research_payload import (
    GEGENLESART,
    GRENZE,
    LESART,
    VERDIKT_GEMISCHT,
    VERDIKT_JA,
    analyse,
    interpretation,
    jetzt_iso,
    lies_csv,
    lies_json,
    n_text,
    p_text,
    pp,
    prozent,
    tabelle,
    zahl,
    zahl_aus,
)

#: Wo die Ergebnistabellen im Thesis-Repo liegen.
RESULTS_DIR = Path("data/results")
THESIS_REPO_URL = "https://github.com/Pablozh123/multi-agent-orchestration-informational-efficiency"
THESIS_TITEL = (
    "Informational efficiency of decentralised prediction markets: "
    "Polymarket against traditional forecast sources"
)
THESIS_FRAGE = (
    "To what degree did Polymarket process information during the 2024 US "
    "presidential election, compared with traditional forecast sources?"
)

#: Dateien je Abschnitt. Fehlt eine, faellt der Abschnitt weg und wird
#: unter ``fehlend`` gemeldet, statt die Seite zu zerlegen.
DATEIEN = {
    "h1": (
        "h1_brier_scores.csv",
        "h1_diebold_mariano.json",
        "h1_calibration_diagnostic_bins.csv",
        "h1_calibration_diagnostic_summary.csv",
        "h1_poll_claim_readiness_summary.csv",
        "h1_forecast_quality_synthesis.csv",
    ),
    "h2": ("h2_event_window_summary.csv", "h2_event_window_rows.csv"),
    "h3": (
        "thesis_h3_summary.csv",
        "h3_lead_lag_correlations.csv",
        "h3_granger_results.csv",
        "h3_wallet_distribution_inventory.json",
    ),
    "swiss": (
        "swiss_referendum_10mio_final_case_study.csv",
        "swiss_referendum_10mio_poll_accuracy.csv",
        "swiss_referendum_10mio_polymarket_price_history.csv",
        "swiss_referendum_10mio_information_response.csv",
        "swiss_referendum_10mio_live_accuracy_windows.csv",
    ),
}

QUELLEN_LABEL = {
    "polymarket": "Polymarket",
    "fivethirtyeight": "FiveThirtyEight",
    "always_50": "Always 50%",
    "prior_day": "Yesterday's Polymarket price",
}

#: Die Kalibrierungs-Sets auf Bundesstaatsebene, drei Quellen ueber dieselben
#: fuenfzig Staaten. Die kleinen "final snapshot"-Sets (8 und 13 Faelle)
#: bleiben in der Tabelle, nicht im Diagramm.
KALIBRIERUNG_SETS = (
    ("polymarket_state_final_50", "Polymarket, state markets"),
    ("rieke_state_final_50", "Rieke poll model"),
    ("two_seventy_state_final_50", "270toWin / JHK"),
)

TIER_LABEL = {
    "tier_1_top_1pct": "Top 1%",
    "tier_2_top_5pct": "Top 5%",
    "tier_3_top_10pct": "Top 10%",
    "tier_4_observed_baseline": "Everyone else",
}

#: Erwartete Richtung je Ereignis, als Vorzeichen auf dem Trump-Markt.
#: 'neutral' bleibt ohne Vorzeichen und zaehlt nicht als Treffer.
RICHTUNG_VORZEICHEN = {"trump_up": 1, "trump_down": -1, "harris_up": -1, "harris_down": 1}


def thesis_root(explizit: str | os.PathLike[str] | None = None, repo_root: Path | None = None) -> Path:
    """Wo das Thesis-Repo liegt: Argument, dann THESIS_ROOT, dann der Nachbarordner."""
    if explizit:
        return Path(explizit)
    env = os.environ.get("THESIS_ROOT", "").strip()
    if env:
        return Path(env)
    wurzel = repo_root or Path(__file__).resolve().parents[1]
    return wurzel.parent / "multi-agent-orchestration-informational-efficiency"


def fehlende_dateien(root: Path) -> list[str]:
    """Welche der erwarteten Tabellen unter ``root`` fehlen."""
    ordner = root / RESULTS_DIR
    return sorted(
        name for namen in DATEIEN.values() for name in namen
        if not (ordner / name).exists()
    )


def _pfad(root: Path, name: str) -> Path:
    return root / RESULTS_DIR / name


# ---------------------------------------------------------------- H1

def _wochen(zeilen: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Wochenmittel je Quelle. 194 Tagespunkte waeren auf 640 Einheiten nur Rauschen."""
    gruppen: "OrderedDict[str, list[dict[str, str]]]" = OrderedDict()
    for z in zeilen:
        try:
            tag = datetime.strptime(z["date"], "%Y-%m-%d")
        except (KeyError, ValueError):
            continue
        jahr, woche, _ = tag.isocalendar()
        gruppen.setdefault(f"{jahr}-W{woche:02d}", []).append(z)
    raus = []
    for schluessel, rows in gruppen.items():
        eintrag: dict[str, Any] = {"woche": schluessel, "von": rows[0]["date"], "tage": len(rows)}
        for feld in ("bs_polymarket", "bs_fivethirtyeight", "bs_always_50"):
            werte = [zahl_aus(r.get(feld)) for r in rows]
            werte = [w for w in werte if w is not None]
            eintrag[feld] = round(sum(werte) / len(werte), 4) if werte else None
        raus.append(eintrag)
    return raus


def _h1(root: Path) -> dict[str, Any]:
    tage = lies_csv(_pfad(root, "h1_brier_scores.csv"))
    dm = lies_json(_pfad(root, "h1_diebold_mariano.json"))
    bins = lies_csv(_pfad(root, "h1_calibration_diagnostic_bins.csv"))
    kal_summary = lies_csv(_pfad(root, "h1_calibration_diagnostic_summary.csv"))
    readiness = {r["summary_id"]: r for r in lies_csv(_pfad(root, "h1_poll_claim_readiness_summary.csv"))}
    synthese = lies_csv(_pfad(root, "h1_forecast_quality_synthesis.csv"))

    n_tage = len(tage)
    mittel: dict[str, float] = {}
    for quelle in ("polymarket", "fivethirtyeight", "always_50", "prior_day"):
        werte = [zahl_aus(z.get(f"bs_{quelle}")) for z in tage]
        werte = [w for w in werte if w is not None]
        mittel[quelle] = sum(werte) / len(werte) if werte else float("nan")
    # An wie vielen Tagen lag Polymarket unter FiveThirtyEight?
    pm_besser = sum(
        1 for z in tage
        if (zahl_aus(z.get("bs_polymarket")) or 0) < (zahl_aus(z.get("bs_fivethirtyeight")) or 0)
    )
    fenster = f"{tage[0]['date']} to {tage[-1]['date']}" if tage else ""

    dm_pm_538 = next((d for d in dm if d.get("source_1") == "Polymarket" and d.get("source_2") == "FiveThirtyEight"), {})
    dm_pm_vortag = next((d for d in dm if d.get("source_1") == "Polymarket" and "Vortag" in str(d.get("source_2"))), {})

    stuetz = int(zahl_aus(readiness.get("primary_polymarket_support_count", {}).get("value"), 0) or 0)
    vergleiche = int(zahl_aus(readiness.get("primary_comparison_count", {}).get("value"), 0) or 0)
    anteil = zahl_aus(readiness.get("primary_polymarket_support_share", {}).get("value"), 0.0) or 0.0
    gegenbeispiele = int(zahl_aus(readiness.get("counterexample_row_count", {}).get("value"), 0) or 0)
    breit_bewiesen = int(zahl_aus(readiness.get("broad_claim_proven", {}).get("value"), 0) or 0) == 1

    scopes_gesamt = len(synthese)
    scopes_mehrheit = sum(1 for s in synthese if str(s.get("majority_cases_supports_polymarket")).lower() == "true")

    kal_punkte = {}
    for set_id, label in KALIBRIERUNG_SETS:
        punkte = []
        for b in bins:
            if b.get("forecast_source_id") != set_id:
                continue
            punkte.append({
                "vorhergesagt": round(zahl_aus(b.get("mean_forecast_probability"), 0.0) or 0.0, 4),
                "realisiert": round(zahl_aus(b.get("observed_frequency"), 0.0) or 0.0, 4),
                "n": int(zahl_aus(b.get("case_count"), 0) or 0),
                "bin": b.get("bin_label", ""),
            })
        if punkte:
            kal_punkte[set_id] = {"label": label, "punkte": punkte}
    kal_zeilen = []
    for s in kal_summary:
        kal_zeilen.append([
            s.get("forecast_source_label", ""),
            int(zahl_aus(s.get("case_count"), 0) or 0),
            round(zahl_aus(s.get("mean_brier_loss"), 0.0) or 0.0, 4),
            round(zahl_aus(s.get("expected_calibration_error"), 0.0) or 0.0, 3),
            round(zahl_aus(s.get("brier_skill_vs_50_percent"), 0.0) or 0.0, 3),
        ])

    pm = mittel["polymarket"]
    ft = mittel["fivethirtyeight"]
    wochen = _wochen(tage)
    einfach = (
        f"On every one of the {n_text(n_tage)} days where both existed ({fenster}), the Polymarket price was "
        f"closer to the outcome than FiveThirtyEight's model: mean Brier score {pm:.3f} against {ft:.3f}, where lower is better "
        f"and a coin flip scores {mittel['always_50']:.3f}. A Diebold-Mariano test puts the gap at p = {p_text(dm_pm_538.get('p_value', 1))}. "
        f"That is the easy part. The thesis then asked whether Polymarket beats poll-based sources on the state level too, and "
        f"the answer is bounded: in the pre-specified scope of {n_text(vergleiche)} state-date comparisons Polymarket had the lower "
        f"loss in {n_text(stuetz)} ({prozent(anteil)}%), but across all {scopes_gesamt} evidence scopes the poll-based comparator "
        f"wins the majority of cases in {scopes_gesamt - scopes_mehrheit}, so the broad claim that Polymarket is simply better "
        f"stays unproven. Yesterday's Polymarket price scores the same as today's ({mittel['prior_day']:.3f}, p = "
        f"{p_text(dm_pm_vortag.get('p_value', 1))}): the market moves slowly on the daily grid."
    )
    verdikt = (
        f"Mixed. Lower forecast error than FiveThirtyEight on all {n_text(n_tage)} overlap days ({pm:.3f} vs {ft:.3f}) "
        f"and in {n_text(stuetz)} of {n_text(vergleiche)} state-date rows, but poll-based models win most state cases in "
        f"{scopes_gesamt - scopes_mehrheit} of {scopes_gesamt} scopes. A bounded advantage, not general dominance."
    )
    return {
        "id": "h1",
        "kapitel": "H1 · Forecast quality",
        "frage": "Was the Polymarket price a better forecast than FiveThirtyEight and the polls?",
        "verdikt": verdikt,
        "verdikt_art": VERDIKT_GEMISCHT,
        "analyse": analyse(
            gemessen="The daily Brier score of each source against the resolved outcome of the 2024 presidential market, and the same loss on state markets against three poll-based comparators.",
            wie="Brier score = (forecast probability minus outcome)^2, averaged per source. Diebold-Mariano compares the two daily loss series. The state-level comparison counts, row by row, which source had the lower loss; calibration bins group forecasts by predicted probability and compare against the realised frequency.",
            daten=f"{n_text(n_tage)} overlapping daily rows ({fenster}); {n_text(vergleiche)} state-date rows in the pre-specified poll scope; 50 state markets for calibration.",
            entscheidung="A lower mean Brier score with a Diebold-Mariano p-value below 0.05 would support H1 for the daily series. The broad claim required Polymarket to win the majority of cases in every evidence scope, which it did not.",
        ),
        "einfach": einfach,
        "interpretation": interpretation(
            (LESART, "On the national daily series the market beat the model by a wide and stable margin. On state markets the picture flips depending on how the poll is turned into a probability, which is exactly why the thesis reports a bounded result."),
            (GEGENLESART, "One resolved election is one draw. 194 daily rows are repeated looks at the same outcome, not 194 independent tests; the tiny p-value measures consistency across days, not evidence across elections."),
            (GRENZE, "Forecast quality on a daily grid says nothing about reaction speed within a day, and nothing about whether any of it was tradable after fees. Both are separate questions on this site."),
        ),
        "zahlen": [
            zahl("Mean Brier, Polymarket", round(pm, 4), "", "lower is better"),
            zahl("Mean Brier, FiveThirtyEight", round(ft, 4)),
            zahl("Mean Brier, always 50%", round(mittel["always_50"], 4), "", "the coin-flip baseline"),
            zahl("Days Polymarket had the lower loss", f"{pm_besser} of {n_tage}"),
            zahl("Diebold-Mariano, Polymarket vs 538", f"p = {p_text(dm_pm_538.get('p_value', 1))}", "", f"statistic {dm_pm_538.get('dm_statistic', 0):.1f}"),
            zahl("State-date rows favouring Polymarket", f"{n_text(stuetz)} of {n_text(vergleiche)}", "", f"{prozent(anteil)}% in the pre-specified scope"),
            zahl("Evidence scopes where polls win most cases", f"{scopes_gesamt - scopes_mehrheit} of {scopes_gesamt}", "", f"{gegenbeispiele} audit rows contradict the strong claim"),
        ],
        "diagramme": {
            "brier_quellen": {
                "titel": "Mean Brier score by source",
                "einheit": "lower is better",
                "punkte": [
                    {"label": QUELLEN_LABEL[q], "wert": round(mittel[q], 4)}
                    for q in ("polymarket", "prior_day", "always_50", "fivethirtyeight")
                ],
            },
            "brier_wochen": {
                "titel": "Weekly mean Brier score",
                "einheit": "squared forecast error",
                "hinweis": f"{n_text(n_tage)} daily rows, averaged per ISO week",
                "x": [w["von"] for w in wochen],
                "serien": [
                    {"name": "Polymarket", "werte": [w["bs_polymarket"] for w in wochen]},
                    {"name": "FiveThirtyEight", "werte": [w["bs_fivethirtyeight"] for w in wochen]},
                    {"name": "Always 50%", "werte": [w["bs_always_50"] for w in wochen]},
                ],
            },
            "kalibrierung": kal_punkte,
            "umfragen_scopes": {
                "titel": "Share of cases where Polymarket had the lower loss, by evidence scope",
                "einheit": "%",
                "referenz": 50.0,
                "referenz_label": "even split",
                "punkte": [
                    {
                        "label": f"{s.get('evidence_label', '')} (n {n_text(s.get('case_count', 0))})",
                        "wert": round((zahl_aus(s.get("polymarket_lower_loss_share"), 0.0) or 0.0) * 100, 1),
                    }
                    for s in synthese
                ],
            },
        },
        "tabellen": [
            tabelle(
                "Every evidence scope of the poll comparison",
                ["Scope", "Comparator", "Cases", "Polymarket lower", "Mean Brier PM", "Mean Brier comparator", "Majority for PM"],
                [
                    [
                        s.get("evidence_label", ""), s.get("comparator_label", ""), int(zahl_aus(s.get("case_count"), 0) or 0),
                        int(zahl_aus(s.get("polymarket_lower_loss_count"), 0) or 0),
                        round(zahl_aus(s.get("mean_polymarket_brier"), 0.0) or 0.0, 4),
                        round(zahl_aus(s.get("mean_comparator_brier"), 0.0) or 0.0, 4),
                        "yes" if str(s.get("majority_cases_supports_polymarket")).lower() == "true" else "no",
                    ]
                    for s in synthese
                ],
                "Cases are daily rows, resolved outcomes or state-date rows depending on the scope; the units differ and the rows are not pooled.",
            ),
            tabelle(
                "Calibration by source",
                ["Source", "Cases", "Mean Brier", "Expected calibration error", "Skill vs 50%"],
                kal_zeilen,
                "Expected calibration error is the n-weighted mean gap between predicted probability and realised frequency across bins.",
            ),
        ],
        "basis": {"tage": n_tage, "fenster": fenster, "beobachtungen": vergleiche},
        "quellen": [
            "data/results/h1_brier_scores.csv", "data/results/h1_diebold_mariano.json",
            "data/results/h1_poll_claim_readiness_summary.csv", "data/results/h1_forecast_quality_synthesis.csv",
            "data/results/h1_calibration_diagnostic_bins.csv",
        ],
        "schlagworte": ["brier", "diebold-mariano", "calibration", "polls"],
        "breite_behauptung_bewiesen": breit_bewiesen,
    }


# ---------------------------------------------------------------- H2

def _h2(root: Path) -> dict[str, Any]:
    summary = lies_csv(_pfad(root, "h2_event_window_summary.csv"))
    rows = lies_csv(_pfad(root, "h2_event_window_rows.csv"))

    ereignisse: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
    for s in summary:
        e = ereignisse.setdefault(s["event_id"], {
            "id": s["event_id"], "datum": s.get("event_date", ""), "titel": s.get("title", ""),
            "art": s.get("event_type", ""), "erwartet": s.get("expected_direction", ""),
            "quelle_url": s.get("source_url", ""), "relevanz": zahl_aus(s.get("relevance_score")),
            "fenster": {},
        })
        e["fenster"][s.get("window_label", "")] = round((zahl_aus(s.get("final_cumulative_abnormal_change"), 0.0) or 0.0) * 100, 2)
    for e in ereignisse.values():
        pfad = [
            {"tag": int(zahl_aus(r.get("relative_day"), 0) or 0), "wert": round((zahl_aus(r.get("cumulative_abnormal_change"), 0.0) or 0.0) * 100, 2)}
            for r in rows if r.get("event_id") == e["id"] and r.get("window_label") == "secondary_minus_1d_to_3d"
        ]
        e["pfad"] = sorted(pfad, key=lambda p: p["tag"])
        primaer = e["fenster"].get("primary_0d_to_1d")
        vz = RICHTUNG_VORZEICHEN.get(e["erwartet"])
        e["gerichtet"] = vz is not None
        e["treffer"] = (vz is not None and primaer is not None and (primaer > 0) == (vz > 0)) if vz else None

    gerichtet = [e for e in ereignisse.values() if e["gerichtet"]]
    treffer = sum(1 for e in gerichtet if e["treffer"])
    groesstes = max(ereignisse.values(), key=lambda e: abs(e["fenster"].get("primary_0d_to_1d", 0.0)))
    neutral = [e for e in ereignisse.values() if not e["gerichtet"]]
    neutral_max = max((abs(e["fenster"].get("primary_0d_to_1d", 0.0)) for e in neutral), default=0.0)
    n_ev = len(ereignisse)
    schaetz = int(zahl_aus(summary[0].get("estimation_observations"), 0) or 0) if summary else 0

    einfach = (
        f"Seven public events of the 2024 campaign were fixed in advance, each with the direction a reasonable observer would "
        f"expect for the Trump-wins market. For each event the thesis measures how much the price moved beyond its normal drift "
        f"(the abnormal change) from the event day to the next. The largest move belongs to the event '{groesstes['titel']}': "
        f"{pp(groesstes['fenster'].get('primary_0d_to_1d', 0) / 100)} percentage points in one day. All {len(gerichtet)} events with an expected "
        f"direction moved that way ({treffer} of {len(gerichtet)}); the {len(neutral)} events without one, the debates and the running-mate picks, "
        f"scatter within {neutral_max:.1f} points of zero. Daily prices cannot say how fast the move happened, only that it did."
    )
    verdikt = (
        f"Supported on daily data. {treffer} of {len(gerichtet)} directional events moved the expected way, the largest "
        f"{pp(groesstes['fenster'].get('primary_0d_to_1d', 0) / 100)} pp within a day; neutral events stayed within {neutral_max:.1f} pp of zero."
    )
    return {
        "id": "h2",
        "kapitel": "H2 · Event reaction",
        "frage": "Did the price react to public campaign events, and in the expected direction?",
        "verdikt": verdikt,
        "verdikt_art": VERDIKT_JA,
        "analyse": analyse(
            gemessen="The cumulative abnormal change of the Trump-wins probability in a primary window (event day to the next day) and a secondary window (one day before to three days after).",
            wie=f"An event study on daily closes. The normal daily drift is estimated from the {schaetz} trading days before each event; abnormal change is the observed change minus that drift, summed over the window.",
            daten=f"{n_ev} pre-curated events between {ereignisse[next(iter(ereignisse))]['datum']} and {list(ereignisse.values())[-1]['datum']}, each with a source link and an expected direction fixed before measurement.",
            entscheidung="Directional events moving in the expected direction, with a magnitude beyond the pre-event drift, count as support; a neutral event moving as much as a directional one would weaken it.",
        ),
        "einfach": einfach,
        "interpretation": interpretation(
            (LESART, "The price absorbs public news within a day, in the direction the news implies. That is what a semi-strong efficient market is supposed to do."),
            (GEGENLESART, "Seven events are seven data points, hand-picked because they were obviously important. The abnormal change is measured against a short drift estimate, so a noisy pre-event window changes the number."),
            (GRENZE, "Daily closes cannot separate 'reacted in minutes' from 'reacted by the next day'. The seconds-level reaction question is answered on the Mentions latency and Live runs pages, on different markets."),
        ),
        "zahlen": [
            zahl("Events", n_ev, "", f"{len(gerichtet)} directional, {len(neutral)} neutral"),
            zahl("Directional events moving as expected", f"{treffer} of {len(gerichtet)}"),
            zahl("Largest one-day move", f"{pp(groesstes['fenster'].get('primary_0d_to_1d', 0) / 100)} pp", "", groesstes["titel"]),
            zahl("Largest neutral-event move", f"{neutral_max:.1f} pp", "", "absolute, primary window"),
        ],
        "diagramme": {
            "fenster": {
                "titel": "Abnormal change in the Trump-wins probability, event day to next day",
                "einheit": "percentage points",
                "referenz": 0.0,
                "referenz_label": "no abnormal move",
                "punkte": [
                    {
                        "label": f"{e['datum'][5:]} {e['titel']}",
                        "wert": e["fenster"].get("primary_0d_to_1d", 0.0),
                        "tip": f"{e['titel']} · expected {e['erwartet'].replace('_', ' ')} · {pp(e['fenster'].get('primary_0d_to_1d', 0) / 100)} pp",
                    }
                    for e in ereignisse.values()
                ],
            },
            "pfade": {
                "titel": "Cumulative abnormal change, one day before to three days after",
                "einheit": "percentage points",
                "x": ["-1", "0", "+1", "+2", "+3"],
                "xWerte": [-1, 0, 1, 2, 3],
                "serien": [
                    {
                        "name": e["titel"],
                        "werte": [next((p["wert"] for p in e["pfad"] if p["tag"] == t), None) for t in (-1, 0, 1, 2, 3)],
                    }
                    for e in ereignisse.values()
                ],
            },
        },
        "ereignisse": [
            {k: v for k, v in e.items() if k != "pfad"} for e in ereignisse.values()
        ],
        "tabellen": [
            tabelle(
                "Every event and both windows",
                ["Event", "Date", "Expected", "0d to +1d (pp)", "-1d to +3d (pp)", "Moved as expected"],
                [
                    [
                        e["titel"], e["datum"], e["erwartet"].replace("_", " "),
                        f"{e['fenster'].get('primary_0d_to_1d', 0.0):+.1f}", f"{e['fenster'].get('secondary_minus_1d_to_3d', 0.0):+.1f}",
                        "n/a" if e["treffer"] is None else ("yes" if e["treffer"] else "no"),
                    ]
                    for e in ereignisse.values()
                ],
                "Positive values favour Trump. Neutral events carry no expectation and are listed as n/a.",
            ),
        ],
        "basis": {"beobachtungen": n_ev, "fenster": "2024-05-30 to 2024-09-11"},
        "quellen": ["data/results/h2_event_window_summary.csv", "data/results/h2_event_window_rows.csv"],
        "schlagworte": ["event study", "abnormal return", "reaction"],
    }


# ---------------------------------------------------------------- H3

def _h3(root: Path) -> dict[str, Any]:
    summary = lies_csv(_pfad(root, "thesis_h3_summary.csv"))
    korr = lies_csv(_pfad(root, "h3_lead_lag_correlations.csv"))
    granger = lies_csv(_pfad(root, "h3_granger_results.csv"))
    inventar = lies_json(_pfad(root, "h3_wallet_distribution_inventory.json"))

    tiers: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
    for s in summary:
        if s.get("summary_type") == "wallet_tier":
            tiers[s["label"]] = {"id": s["label"], "label": TIER_LABEL.get(s["label"], s["label"]), "wallets": int(zahl_aus(s.get("value"), 0) or 0)}
    zeilen_modell = next((int(zahl_aus(s.get("value"), 0) or 0) for s in summary if s.get("summary_id") == "h3_model_row_count"), 0)

    lags = sorted({int(zahl_aus(k.get("lag_days"), 0) or 0) for k in korr})
    for t in tiers.values():
        t["korrelation"] = {
            int(zahl_aus(k.get("lag_days"), 0) or 0): round(zahl_aus(k.get("correlation"), 0.0) or 0.0, 4)
            for k in korr if k.get("tier") == t["id"]
        }
        t["granger"] = {
            int(zahl_aus(g.get("lag_days"), 0) or 0): zahl_aus(g.get("p_value"), 1.0) or 1.0
            for g in granger if g.get("tier") == t["id"]
        }
        t["n"] = next((int(zahl_aus(g.get("observation_count"), 0) or 0) for g in granger if g.get("tier") == t["id"]), 0)
        if t["granger"]:
            lag_min = min(t["granger"], key=lambda lag: t["granger"][lag])
            t["granger_min"] = {"lag": lag_min, "p": t["granger"][lag_min]}
        if t["korrelation"]:
            lag_max = max(t["korrelation"], key=lambda lag: abs(t["korrelation"][lag]))
            t["korrelation_max"] = {"lag": lag_max, "r": t["korrelation"][lag_max]}

    tests = sum(len(t["granger"]) for t in tiers.values())
    bonferroni = 0.05 / tests if tests else 0.05
    signifikant = [(t, lag, p) for t in tiers.values() for lag, p in t["granger"].items() if p < 0.05]
    signifikant_bonf = [(t, lag, p) for t, lag, p in signifikant if p < bonferroni]
    top = tiers.get("tier_1_top_1pct") or next(iter(tiers.values()))
    konz = (inventar.get("diagnostics") or {}).get("concentration") or {}
    quant = (inventar.get("diagnostics") or {}).get("cumulative_amount_usd_quantiles") or {}
    n_wallets = sum(t["wallets"] for t in tiers.values())
    zeitraum = inventar.get("input") or {}

    einfach = (
        f"The thesis sorted {n_text(n_wallets)} wallets with at least {n_text(quant.get('min', 0))} USD of observed buying into tiers by how much they "
        f"traded, then asked whether a tier's daily buying volume moved before the price did. For the top 1% "
        f"({top['wallets']} wallets) the answer is a weak yes: buying on one day correlates with the next day's price change at "
        f"r = {top.get('korrelation_max', {}).get('r', 0):+.3f}, and a Granger test at lag 1 gives p = {p_text(top.get('granger_min', {}).get('p', 1))}. "
        f"The other three tiers show nothing (smallest p between {p_text(min(t['granger_min']['p'] for t in tiers.values() if t['id'] != top['id']))} and "
        f"{p_text(max(t['granger_min']['p'] for t in tiers.values() if t['id'] != top['id']))}). Across {tests} tier-lag tests "
        f"{len(signifikant)} fall below 0.05 and {len(signifikant_bonf)} survive a Bonferroni correction ({bonferroni:.4f}). "
        f"One wallet alone accounts for {prozent(konz.get('top_1_wallet_share', 0))}% of all observed volume, so the top tier is largely one actor."
    )
    verdikt = (
        f"Supported for one tier and one lag. The top 1% ({top['wallets']} wallets) lead the next day's price change "
        f"(r {top.get('korrelation_max', {}).get('r', 0):+.3f}, Granger p {p_text(top.get('granger_min', {}).get('p', 1))}); "
        f"the other tiers show no timing signal. A diagnostic of timing, not a causal finding."
    )
    return {
        "id": "h3",
        "kapitel": "H3 · Wallet timing",
        "frage": "Did large wallets move before the price moved?",
        "verdikt": verdikt,
        "verdikt_art": VERDIKT_JA,
        "analyse": analyse(
            gemessen="Lead-lag correlation between a tier's daily change in buying volume (log scale) and the daily change of the Trump-wins price, plus a Granger causality test per tier and lag.",
            wie="Wallets are ranked by cumulative buy volume; the top 1%, 5% and 10% and the remainder form four tiers. For each tier and lag from 0 to 7 days the correlation is computed, and an F-test asks whether the tier's past activity improves the forecast of the price change beyond the price's own past.",
            daten=f"{n_text(n_wallets)} wallets, {n_text(zeilen_modell)} aligned tier-day rows, {top['n']} observations per test, {zeitraum.get('date_range_start', '')[:10]} to {zeitraum.get('date_range_end', '')[:10]}. Buy-side trades only.",
            entscheidung="A Granger p-value below 0.05 for a tier would count as a timing signal; with 28 tests, the Bonferroni threshold is what a sceptical reader applies.",
        ),
        "einfach": einfach,
        "interpretation": interpretation(
            (LESART, "The largest wallets buy a day before prices move their way. Whether they cause the move, react to something the price has not seen yet, or simply are the move (their own orders shift the price) cannot be separated on daily data."),
            (GEGENLESART, "Twenty-eight tests at a 5% threshold produce one or two hits by chance. The lag-1 result survives Bonferroni, the lag-2 result does not. And the top tier is dominated by a single wallet, so this is closer to a case study of one actor than a statement about a class of traders."),
            (GRENZE, "Buy-only data, daily alignment, one election. Nothing here says that following these wallets would have paid anything after spreads and fees; the copy-trading forensics on this site say it did not."),
        ),
        "zahlen": [
            zahl("Wallets in the top 1% tier", top["wallets"], "", f"of {n_text(n_wallets)} observed"),
            zahl("Top-tier lead correlation, lag 1", f"{top.get('korrelation_max', {}).get('r', 0):+.3f}", "", f"n {top['n']}"),
            zahl("Top-tier Granger p, lag 1", p_text(top.get("granger_min", {}).get("p", 1)), "", f"Bonferroni threshold {bonferroni:.4f} over {tests} tests"),
            zahl("Tests below 0.05 / surviving Bonferroni", f"{len(signifikant)} / {len(signifikant_bonf)}", "", f"of {tests}"),
            zahl("Share of volume from the single largest wallet", f"{prozent(konz.get('top_1_wallet_share', 0))}%", "", f"top 10 wallets: {prozent(konz.get('top_10_wallet_share', 0))}%"),
        ],
        "diagramme": {
            "leadlag": {
                "titel": "Correlation between tier buying and the next days' price change",
                "einheit": "Pearson r",
                "hinweis": "lag in days: activity on day t against price change on day t + lag",
                "x": [str(lag) for lag in lags],
                "xWerte": lags,
                "serien": [
                    {"name": t["label"], "werte": [t["korrelation"].get(lag) for lag in lags]}
                    for t in tiers.values()
                ],
            },
            "granger": {
                "titel": "Smallest Granger p-value per tier",
                "einheit": "p-value",
                "referenz": 0.05,
                "referenz_label": "p = 0.05",
                "punkte": [
                    {"label": f"{t['label']} (lag {t['granger_min']['lag']}, {t['wallets']} wallets)", "wert": round(t["granger_min"]["p"], 4),
                     "farbe": "var(--accent)" if t["granger_min"]["p"] < bonferroni else "var(--ink-3)"}
                    for t in tiers.values() if t.get("granger_min")
                ],
            },
            "tiers": {
                "titel": "Wallets per tier",
                "einheit": "wallets",
                "punkte": [{"label": t["label"], "wert": t["wallets"]} for t in tiers.values()],
            },
        },
        "tabellen": [
            tabelle(
                "Granger p-values, every tier and lag",
                ["Tier", "Wallets"] + [f"lag {lag}" for lag in lags if lag > 0],
                [
                    [t["label"], t["wallets"]] + [p_text(t["granger"][lag]) if lag in t["granger"] else "" for lag in lags if lag > 0]
                    for t in tiers.values()
                ],
                f"Bonferroni threshold for {tests} tests: {bonferroni:.4f}.",
            ),
        ],
        "basis": {"beobachtungen": zeilen_modell, "fenster": f"{zeitraum.get('date_range_start', '')[:10]} to {zeitraum.get('date_range_end', '')[:10]}"},
        "quellen": ["data/results/thesis_h3_summary.csv", "data/results/h3_lead_lag_correlations.csv", "data/results/h3_granger_results.csv", "data/results/h3_wallet_distribution_inventory.json"],
        "schlagworte": ["granger", "lead-lag", "wallet tiers"],
    }


# ---------------------------------------------------------------- Swiss case

def _tagesletzte(preise: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Der letzte Preis je Kalendertag: 504 Stundenwerte werden zu einer lesbaren Kurve."""
    tage: "OrderedDict[str, float]" = OrderedDict()
    for p in preise:
        ts = str(p.get("observed_at_utc", ""))
        wert = zahl_aus(p.get("yes_probability"))
        if len(ts) < 10 or wert is None:
            continue
        tage[ts[:10]] = wert
    return [{"t": tag, "wert": round(w, 4)} for tag, w in tage.items()]


def _swiss(root: Path) -> dict[str, Any]:
    fall = lies_csv(_pfad(root, "swiss_referendum_10mio_final_case_study.csv"))[0]
    umfragen = lies_csv(_pfad(root, "swiss_referendum_10mio_poll_accuracy.csv"))
    preise = lies_csv(_pfad(root, "swiss_referendum_10mio_polymarket_price_history.csv"))
    antwort = lies_csv(_pfad(root, "swiss_referendum_10mio_information_response.csv"))
    live = lies_csv(_pfad(root, "swiss_referendum_10mio_live_accuracy_windows.csv"))

    amtlich_ja = zahl_aus(fall.get("official_yes_share"), 0.0) or 0.0
    letzter_pm = zahl_aus(fall.get("latest_live_polymarket_yes_probability"), 0.0) or 0.0
    pm_fehler = zahl_aus(fall.get("latest_live_polymarket_vote_share_abs_error"), 0.0) or 0.0
    live_n = int(zahl_aus(fall.get("live_observation_rows"), 0) or 0)
    beats_anteil = int(zahl_aus(fall.get("live_polymarket_beats_raw_vote_share_count"), 0) or 0)
    beats_binaer = int(zahl_aus(fall.get("live_polymarket_beats_raw_binary_proxy_count"), 0) or 0)
    hist_n = int(zahl_aus(fall.get("history_observation_rows"), 0) or 0)
    hist_beats = int(zahl_aus(fall.get("history_polymarket_beats_raw_vote_share_count"), 0) or 0)
    kurve = _tagesletzte(preise)

    finale = [u for u in umfragen if str(u.get("final_poll_for_source")).lower() == "true"]
    finale_fehler = [abs(zahl_aus(u.get("raw_yes_abs_error"), 0.0) or 0.0) for u in finale]
    poll_ja = [zahl_aus(u.get("yes_share"), 0.0) or 0.0 for u in finale]
    richtung_ja = sum(1 for u in umfragen if str(u.get("poll_direction_against_50pct", "")).startswith("raw_yes_at_or_above"))

    labels = {}
    for a in antwort:
        labels[a.get("information_processing_label", "")] = labels.get(a.get("information_processing_label", ""), 0) + 1
    gleich_48 = sum(1 for a in antwort if str(a.get("alignment_48h")) == "same_direction")
    mit_signal = sum(1 for a in antwort if a.get("poll_signal_direction") in ("up", "down"))

    einfach = (
        f"The initiative was rejected with {prozent(amtlich_ja, 2)}% Yes. Polymarket's last live price before the result put Yes at "
        f"{prozent(letzter_pm)}%, so as a vote-share estimate the market was {pm_fehler * 100:.1f} points off, while the three final polls were "
        f"{min(finale_fehler) * 100:.1f} to {max(finale_fehler) * 100:.1f} points off ({', '.join(f'{prozent(p, 0)}%' for p in poll_ja)} Yes). "
        f"Read as a binary call the picture reverses: in all {live_n} live comparison windows the market's probability was further on the correct "
        f"No side than any poll proxy ({beats_binaer} of {live_n}), and on vote share the market beat the matched poll in {beats_anteil} of {live_n}. "
        f"Over the {hist_n} hourly history rows since April the market was closer than the poll on vote share {hist_beats} times. "
        f"After {mit_signal} poll releases with a direction, the price ended up moving the same way within 48 hours in {gleich_48}; the responses were "
        f"slow, small and sometimes opposite. A price is a probability, a poll is a share, and the thesis keeps the two readings apart."
    )
    verdikt = (
        f"Right side, wrong number. Polymarket priced Yes at {prozent(letzter_pm)}% against an official {prozent(amtlich_ja, 2)}%: further from the "
        f"vote share than every final poll, yet on the correct No side in all {live_n} live windows. A bounded side case, not a test of efficiency."
    )
    return {
        "id": "swiss",
        "kapitel": "Case study · Swiss referendum, 14 June 2026",
        "frage": "Outside the US: did the market read a Swiss referendum better than the polls?",
        "verdikt": verdikt,
        "verdikt_art": VERDIKT_GEMISCHT,
        "analyse": analyse(
            gemessen="The Polymarket Yes price for the popular initiative 'No 10-million Switzerland' against seven published polls and the official result, both as a vote-share estimate and as a binary call.",
            wie="Hourly price snapshots from the Polymarket price history, matched to the most recent poll at each observation. Vote-share error is |price minus official Yes share|; the binary proxy scores each source's Brier loss against the rejection. Poll releases are followed for 48 hours to see whether the price moved the same way as the poll signal.",
            daten=f"{n_text(hist_n)} hourly price rows from {kurve[0]['t'] if kurve else ''} to {kurve[-1]['t'] if kurve else ''}, {live_n} live comparison windows in the final week, {len(umfragen)} polls from three institutes, the official result from admin.ch.",
            entscheidung="A lower vote-share error than the final polls would have supported the market as an estimator; a lower binary Brier loss supports it as a probability. The two disagree, which is the finding.",
        ),
        "einfach": einfach,
        "interpretation": interpretation(
            (LESART, "The market was confident of a No and right about it; the polls tracked the vote share and were right about that. Neither source was wrong on its own terms."),
            (GEGENLESART, "A thin, US-dollar market on a Swiss vote has few informed participants; a 21.5% price on a 45% outcome may say more about who trades there than about information. The polls all leaned No too, so the direction was not hard."),
            (GRENZE, "One referendum. Comparing a probability with a vote share needs a proxy in one direction or the other, and both proxies are documented as proxies. Nothing here measures whether the gap was tradable."),
        ),
        "zahlen": [
            zahl("Official Yes share", f"{prozent(amtlich_ja, 2)}%", "", fall.get("official_outcome", "")),
            zahl("Last live Polymarket Yes price", f"{prozent(letzter_pm)}%", "", f"{pm_fehler * 100:.1f} points from the vote share"),
            zahl("Final polls, Yes", ", ".join(f"{prozent(p, 0)}%" for p in poll_ja), "", "SRG/gfs.bern, Tamedia/LeeWas, YouGov"),
            zahl("Live windows where the market won on vote share", f"{beats_anteil} of {live_n}"),
            zahl("Live windows where the market won as a binary call", f"{beats_binaer} of {live_n}"),
            zahl("Poll releases followed by a same-direction move within 48 h", f"{gleich_48} of {mit_signal}"),
        ],
        "diagramme": {
            "preis": {
                "titel": "Polymarket Yes price, daily last value",
                "einheit": "probability",
                "punkte": kurve,
                "marken": [
                    {
                        "t": str(u.get("published_at_utc", ""))[:10],
                        "wert": round(zahl_aus(u.get("yes_share"), 0.0) or 0.0, 4),
                        "label": f"{u.get('source_name', '')} {prozent(zahl_aus(u.get('yes_share'), 0.0) or 0.0, 0)}% Yes",
                    }
                    for u in umfragen
                ],
                "referenz": {"wert": round(amtlich_ja, 4), "label": f"official Yes {prozent(amtlich_ja, 2)}%"},
            },
            "quellen_fehler": {
                "titel": "Distance from the official Yes share, final sources",
                "einheit": "percentage points",
                "punkte": [{"label": f"Polymarket ({prozent(letzter_pm)}% Yes)", "wert": round(pm_fehler * 100, 1)}]
                + [
                    {"label": f"{u.get('source_name', '')} ({prozent(zahl_aus(u.get('yes_share'), 0.0) or 0.0, 0)}% Yes)", "wert": round(abs(zahl_aus(u.get("raw_yes_abs_error"), 0.0) or 0.0) * 100, 1)}
                    for u in finale
                ],
            },
            # Eine Linie je Horizont ueber den Umfragen, nicht eine je Umfrage:
            # sieben Umfragen haetten die fuenf Farbplaetze gesprengt, und die
            # Frage ist ohnehin, ob der Preis nach 1, 6, 24 oder 48 Stunden
            # in die Richtung der Umfrage gelaufen ist.
            "antwort": {
                "titel": "Price change after each poll release, by horizon",
                "einheit": "percentage points",
                "hinweis": "x: poll release in order of publication; positive = Yes price up",
                "x": [f"{str(a.get('poll_published_at_utc', ''))[5:10]} {str(a.get('poll_source', '')).split('/')[0]}" for a in antwort],
                "serien": [
                    {
                        "name": f"after {h.replace('h', ' h')}",
                        "werte": [round((zahl_aus(a.get(f"polymarket_change_{h}"), 0.0) or 0.0) * 100, 1) for a in antwort],
                    }
                    for h in ("1h", "6h", "24h", "48h")
                ],
            },
        },
        "tabellen": [
            tabelle(
                "Every poll against the official result",
                ["Poll", "Published", "Yes", "No", "Undecided", "Yes error (pp)", "Final"],
                [
                    [
                        u.get("source_name", ""), str(u.get("published_at_utc", ""))[:10],
                        f"{prozent(zahl_aus(u.get('yes_share'), 0.0) or 0.0, 0)}%", f"{prozent(zahl_aus(u.get('no_share'), 0.0) or 0.0, 0)}%",
                        f"{prozent(zahl_aus(u.get('undecided_share'), 0.0) or 0.0, 0)}%",
                        f"{(zahl_aus(u.get('raw_yes_signed_error'), 0.0) or 0.0) * 100:+.1f}",
                        "yes" if str(u.get("final_poll_for_source")).lower() == "true" else "",
                    ]
                    for u in umfragen
                ],
                f"{richtung_ja} of {len(umfragen)} polls had Yes at or above 50%; every final poll leaned No.",
            ),
            tabelle(
                "Price response to poll releases",
                ["Poll", "Poll signal", "+1 h", "+6 h", "+24 h", "+48 h", "Classification"],
                [
                    [
                        f"{a.get('poll_source', '')} {str(a.get('poll_published_at_utc', ''))[:10]}",
                        a.get("poll_signal_direction", ""),
                    ] + [f"{(zahl_aus(a.get(f'polymarket_change_{h}'), 0.0) or 0.0) * 100:+.1f}" for h in ("1h", "6h", "24h", "48h")]
                    + [str(a.get("information_processing_label", "")).replace("_", " ")]
                    for a in antwort
                ],
                "Poll signal is the direction of the decided Yes share against the previous poll; the first poll has no predecessor.",
            ),
        ],
        "basis": {"beobachtungen": live_n, "snapshots": hist_n, "fenster": f"{kurve[0]['t'] if kurve else ''} to {kurve[-1]['t'] if kurve else ''}"},
        "quellen": [
            "data/results/swiss_referendum_10mio_final_case_study.csv", "data/results/swiss_referendum_10mio_poll_accuracy.csv",
            "data/results/swiss_referendum_10mio_polymarket_price_history.csv", "data/results/swiss_referendum_10mio_information_response.csv",
        ],
        "amtlich": {
            "titel": fall.get("official_title", ""), "datum": fall.get("vote_date", ""), "ergebnis": fall.get("official_outcome", ""),
            "ja": round(amtlich_ja, 4), "quelle_url": fall.get("official_dashboard_url", ""),
        },
        "schlagworte": ["referendum", "polls", "switzerland"],
        "live_zeilen": len(live),
    }


# ---------------------------------------------------------------- Nutzlast

ABSCHNITTE = (("h1", _h1), ("h2", _h2), ("h3", _h3), ("swiss", _swiss))

HINWEIS = (
    "Results of the bachelor thesis behind this site, read from its published result tables. "
    "Descriptive research on public market data; every number is computed from the artifact it cites."
)
EINLEITUNG = (
    "The thesis asked one question about one election: how much information did Polymarket process during the 2024 US "
    "presidential race, compared with FiveThirtyEight and the polls? It answers through three proxies, forecast quality, "
    "reaction to public events and the timing of large wallets, and adds a Swiss referendum as a case outside the US. "
    "The verdicts below are the thesis's own, with the numbers they rest on."
)


def build_payload(root: Path | str | None = None, *, jetzt: datetime | None = None) -> dict[str, Any]:
    """Baut die Nutzlast; fehlende Abschnitte werden gemeldet, nicht erfunden."""
    wurzel = thesis_root(root)
    sektionen = []
    fehlend: list[str] = []
    for schluessel, bauer in ABSCHNITTE:
        fehlende = [n for n in DATEIEN[schluessel] if not _pfad(wurzel, n).exists()]
        if fehlende:
            fehlend.extend(fehlende)
            continue
        sektionen.append(bauer(wurzel))
    zaehler = {
        "gesamt": len(sektionen),
        "ja": sum(1 for s in sektionen if s["verdikt_art"] == VERDIKT_JA),
        "gemischt": sum(1 for s in sektionen if s["verdikt_art"] == VERDIKT_GEMISCHT),
    }
    return {
        "hinweis": HINWEIS,
        "einleitung": EINLEITUNG,
        "thesis": {
            "titel": THESIS_TITEL,
            "frage": THESIS_FRAGE,
            "hochschule": "FHNW School of Business, BSc Business AI, 2026",
            "repo": THESIS_REPO_URL,
            "hypothesen": [
                {"id": "H1", "text": "Forecast quality: the Polymarket price carries a lower Brier loss than traditional forecast sources."},
                {"id": "H2", "text": "Event reaction: the price moves in the expected direction around curated public events."},
                {"id": "H3", "text": "Wallet timing: the activity of large wallets leads the price change."},
            ],
            "nicht_behauptet": [
                "No claim of universal efficiency: one election, one market family.",
                "No intraday speed claim from daily data.",
                "No causal insider claim from timing correlations.",
                "No profitability claim of any kind.",
            ],
        },
        "stand_utc": jetzt_iso(jetzt),
        "kennzeichnung": "research/thesis",
        "zaehler": zaehler,
        "sektionen": sektionen,
        "fehlend": sorted(set(fehlend)),
    }
