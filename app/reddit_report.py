"""Baut die Nutzlast fuer ``public/data/reddit_sentiment.json``.

Die Reddit-Sentiment-Studie (Kursprojekt Data Wrangling, FHNW FS26, Live-
Lauf vom 2026-05-22) fragte, ob die Stimmung in Reddit-Diskussionen mit den
Wahrscheinlichkeiten von Polymarket-Maerkten zusammenhaengt. 29 aktive
Maerkte, 725 Posts aus sieben Subreddits, Sentiment per Twitter-RoBERTa,
Zustimmung per Zero-Shot-Stance-Modell. Der Befund ist ein sauberes Nein:
keine messbare Korrelation, Richtung in 13 von 29 Maerkten gleich.

Artefakte unter ``docs/research/reddit_sentiment/``:

* ``correlation_pairs_2026-05-22.csv``  die 29 Maerkte mit Wahrscheinlichkeit,
  Sentiment- und Stance-Score, Post-Zaehlung (die Tabelle, aus der die
  Korrelationen gerechnet werden; hier werden sie nachgerechnet)
* ``model_comparison.csv``  VADER gegen Twitter-RoBERTa
* ``semantic_filter_comparison.csv``  wie viel der semantische Filter behaelt
* ``report_tables.json``  die Tabellen des Berichts, die auf Post-Ebene
  gerechnet wurden und hier nicht reproduzierbar sind (Subreddits,
  Kategorien, Stance, Relevanz-Audit)

Die Korrelationen der Marktebene werden aus der CSV nachgerechnet und in
den Tests gegen den Bericht geprueft; so kann der Fliesstext nicht vom
Artefakt abdriften. Streamlit-frei.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from app.research_payload import (
    GEGENLESART,
    GRENZE,
    LESART,
    VERDIKT_NEIN,
    analyse,
    interpretation,
    jetzt_iso,
    lies_csv,
    lies_json,
    n_text,
    p_text,
    pearson,
    prozent,
    spearman,
    tabelle,
    zahl,
    zahl_aus,
)

ARTEFAKT_DIR = Path("docs/research/reddit_sentiment")
DATEIEN = ("correlation_pairs_2026-05-22.csv", "model_comparison.csv", "semantic_filter_comparison.csv", "report_tables.json")
REPORT = "docs/research/reddit_sentiment/report_tables.json"
MODUL = "src/sentiment.py"


def fehlende_dateien(root: Path) -> list[str]:
    return sorted(n for n in DATEIEN if not (root / ARTEFAKT_DIR / n).exists())


def _kurz(frage: str, n: int = 38) -> str:
    text = str(frage).strip().rstrip("?")
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def korrelationen(zeilen: list[dict[str, str]]) -> dict[str, Any]:
    """Pearson, Spearman und Richtungsuebereinstimmung ueber die Marktzeilen."""
    paare = [
        (zahl_aus(z.get("probability")), zahl_aus(z.get("adjusted_weighted")), zahl_aus(z.get("stance_score")))
        for z in zeilen
    ]
    paare = [(p, s, st) for p, s, st in paare if p is not None and s is not None]
    xs = [p for p, _, _ in paare]
    ys = [s for _, s, _ in paare]
    stance = [(p, st) for p, _, st in paare if st is not None]
    gleich = sum(1 for p, s in zip(xs, ys) if (p > 0.5) == (s > 0))
    return {
        "n": len(paare),
        "pearson_r": pearson(xs, ys),
        "spearman_rho": spearman(xs, ys),
        "stance_pearson_r": pearson([p for p, _ in stance], [st for _, st in stance]) if stance else None,
        "richtung_gleich": gleich,
    }


def build_payload(root: Path | str = ".", *, jetzt: datetime | None = None) -> dict[str, Any]:
    wurzel = Path(root)
    fehlend = fehlende_dateien(wurzel)
    if fehlend:
        return {
            "hinweis": HINWEIS, "stand_utc": jetzt_iso(jetzt), "kennzeichnung": "research/frozen",
            "fehlend": fehlend, "studie": None,
        }
    ordner = wurzel / ARTEFAKT_DIR
    maerkte = lies_csv(ordner / "correlation_pairs_2026-05-22.csv")
    modelle = lies_csv(ordner / "model_comparison.csv")
    filter_zeilen = lies_csv(ordner / "semantic_filter_comparison.csv")
    bericht = lies_json(ordner / "report_tables.json")

    k = korrelationen(maerkte)
    n = k["n"]
    posts = sum(int(zahl_aus(z.get("n_total"), 0) or 0) for z in maerkte)
    r = k["pearson_r"] or 0.0
    rho = k["spearman_rho"] or 0.0
    f1 = next((f for f in bericht.get("f1", []) if "Adjusted" in f.get("metrik", "")), (bericht.get("f1") or [{}])[0])
    stance_f4 = (bericht.get("f4_stance") or [{}])[0]
    kw = bericht.get("f2_kruskal_wallis") or {}
    subs = sorted(bericht.get("f2_subreddits") or [], key=lambda s: -s["mittel"])
    kats = bericht.get("f1b_kategorien") or []
    audit = bericht.get("relevanz_audit") or {}
    stich = bericht.get("stichprobe") or {}
    kategorien_n: dict[str, int] = {}
    for z in maerkte:
        kategorien_n[z.get("category", "")] = kategorien_n.get(z.get("category", ""), 0) + 1
    roberta = next((m for m in modelle if "roberta" in m.get("model", "")), {})
    vader = next((m for m in modelle if "vader" in m.get("model", "")), {})
    retention = [zahl_aus(f.get("retention_pct"), 0.0) or 0.0 for f in filter_zeilen]

    einfach = (
        f"For {n} live Polymarket markets the study pulled {n_text(posts)} Reddit posts from {stich.get('subreddits', 7)} subreddits, scored each post's mood "
        f"with a sentiment model, and compared the average mood per market with the market's probability. The two barely move together: "
        f"Pearson r = {r:+.3f} (p = {p_text(f1.get('pearson_p', 1))}), Spearman rho = {rho:+.3f} (p = {p_text(f1.get('spearman_p', 1))}). "
        f"Reading 'mood above zero' as 'Reddit expects it to happen', the direction matched the market in {k['richtung_gleich']} of {n} markets, "
        f"worse than a coin flip. A stance model, which asks whether a post supports the event rather than whether it sounds happy, did no better "
        f"(r = {stance_f4.get('pearson_r', 0):+.3f}, p = {p_text(stance_f4.get('pearson_p', 1))}). What the data do show clearly is that subreddits differ in mood "
        f"(Kruskal-Wallis H = {kw.get('H', 0):.2f}, p = {p_text(kw.get('p', 1))}): r/stocks reads {subs[0]['mittel']:+.2f} on average, r/politics {next((s['mittel'] for s in subs if s['subreddit'] == 'politics'), 0):+.2f}. "
        f"And a manual audit of {audit.get('stichprobe', 0)} retrieved posts found {audit.get('relevant', 0)} fully relevant, {audit.get('teilweise', 0)} partly and "
        f"{audit.get('irrelevant', 0)} unrelated to their market, which is the most likely reason the signal is absent: keyword search on Reddit mostly finds noise."
    )
    verdikt = (
        f"No measurable link. Across {n} markets and {n_text(posts)} posts, sentiment and market probability correlate at r = {r:+.2f} "
        f"(p = {p_text(f1.get('pearson_p', 1))}); direction agrees in {k['richtung_gleich']} of {n}. Only the mood between subreddits differs significantly."
    )
    studie = {
        "id": "reddit-sentiment",
        "frage": "Does Reddit mood track Polymarket prices?",
        "verdikt": verdikt,
        "verdikt_art": VERDIKT_NEIN,
        "analyse": analyse(
            gemessen="The correlation between a market's probability and the average sentiment of Reddit posts found for that market, plus a stance score, subreddit differences and a relevance audit of the retrieved posts.",
            wie="Market questions were turned into keyword queries, posts fetched from seven subreddits and filtered by semantic similarity to the question. Twitter-RoBERTa scored each post between -1 and +1; the market's score is the post-weighted mean. A DeBERTa zero-shot model scored stance (supports, neutral, opposes). Pearson and Spearman on the market level; Kruskal-Wallis across subreddits.",
            daten=f"{n} active Polymarket markets by volume, {n_text(posts)} posts, collected live on {str(stich.get('erhoben_utc', ''))[:10]}. Post dates range from {bericht.get('zeitraum_posts', {}).get('von', '')} to {bericht.get('zeitraum_posts', {}).get('bis', '')}.",
            entscheidung="A significant positive correlation (p below 0.05) between sentiment and probability, or direction agreement well above 50%, would have counted as a link. Neither appeared.",
        ),
        "einfach": einfach,
        "interpretation": interpretation(
            (LESART, "Reddit mood on a keyword match is not information about the event. Prices carry liquidity, specialist knowledge and market mechanics that a paragraph of text does not."),
            (GEGENLESART, "The retrieval is the weak link, not necessarily the idea: three quarters of the audited posts were about something else. A better-targeted corpus could still show a link this study could not see. And 29 markets is a small sample for a correlation."),
            (GRENZE, "One snapshot, no time dimension: this cannot say whether Reddit leads or lags the market, only that the levels do not line up. Sports made the closest approach (r = +0.50 on 15 markets, p = 0.058) and would need its own, larger test."),
        ),
        "zahlen": [
            zahl("Markets / posts", f"{n} / {n_text(posts)}", "", f"{stich.get('subreddits', 7)} subreddits"),
            zahl("Pearson r, sentiment vs probability", f"{r:+.3f}", "", f"p = {p_text(f1.get('pearson_p', 1))}"),
            zahl("Spearman rho", f"{rho:+.3f}", "", f"p = {p_text(f1.get('spearman_p', 1))}"),
            zahl("Direction agreement", f"{k['richtung_gleich']} of {n}", "", f"{prozent(k['richtung_gleich'] / n if n else 0)}%"),
            zahl("Stance score, Pearson r", f"{stance_f4.get('pearson_r', 0):+.3f}", "", f"p = {p_text(stance_f4.get('pearson_p', 1))}"),
            zahl("Kruskal-Wallis across subreddits", f"H = {kw.get('H', 0):.2f}", "", f"p = {p_text(kw.get('p', 1))}"),
            zahl("Audited posts relevant / partly / unrelated", f"{audit.get('relevant', 0)} / {audit.get('teilweise', 0)} / {audit.get('irrelevant', 0)}", "", f"of {audit.get('stichprobe', 0)} sampled"),
        ],
        "diagramme": {
            "streuung": {
                "titel": "Market probability against Reddit sentiment, one point per market",
                "xLabel": "market probability (%)",
                "yLabel": "weighted sentiment (-1 to +1)",
                "xDomain": [0, 100],
                "xReferenzen": [{"wert": 50, "label": "50%"}],
                "yReferenzen": [{"wert": 0, "label": "neutral"}],
                "punkte": [
                    {
                        "x": round((zahl_aus(z.get("probability"), 0.0) or 0.0) * 100, 1),
                        "y": round(zahl_aus(z.get("adjusted_weighted"), 0.0) or 0.0, 3),
                        "label": _kurz(z.get("question", "")),
                        "tip": f"{z.get('question', '')} · {prozent(zahl_aus(z.get('probability'), 0.0) or 0.0)}% · sentiment {zahl_aus(z.get('adjusted_weighted'), 0.0) or 0.0:+.2f} · {z.get('n_total', '')} posts · {z.get('category', '')}",
                    }
                    for z in maerkte
                ],
                "labelN": 3,
                "hinweis": f"r = {r:+.3f}, rho = {rho:+.3f}, n = {n}",
            },
            "subreddits": {
                "titel": "Mean sentiment by subreddit",
                "einheit": "score, -1 to +1",
                "referenz": 0.0,
                "referenz_label": "neutral",
                "punkte": [{"label": f"r/{s['subreddit']} (n {s['n']})", "wert": s["mittel"]} for s in subs],
            },
            "kategorien": {
                "titel": "Correlation by market category (three or more markets)",
                "einheit": "Pearson r",
                "referenz": 0.0,
                "referenz_label": "no link",
                "punkte": [{"label": f"{c['kategorie']} (n {c['n']}, p {p_text(c['p'])})", "wert": c["pearson_r"]} for c in kats],
            },
            "audit": {
                "titel": "What the retrieved posts were actually about",
                "einheit": "posts in the audit sample",
                "punkte": [
                    {"label": "Relevant to the market", "wert": audit.get("relevant", 0), "farbe": "var(--accent)"},
                    {"label": "Partly relevant", "wert": audit.get("teilweise", 0), "farbe": "var(--warn)"},
                    {"label": "Unrelated", "wert": audit.get("irrelevant", 0), "farbe": "var(--neg-soft)"},
                ],
            },
        },
        "tabellen": [
            tabelle(
                "Two sentiment models on the same posts",
                ["Model", "Pearson r", "p", "Spearman rho", "p", "Direction agreement", "Runtime (s)"],
                [
                    [
                        m.get("model", ""), f"{zahl_aus(m.get('pearson_r'), 0.0) or 0.0:+.3f}", p_text(zahl_aus(m.get("pearson_p"), 1.0) or 1.0),
                        f"{zahl_aus(m.get('spearman_rho'), 0.0) or 0.0:+.3f}", p_text(zahl_aus(m.get("spearman_p"), 1.0) or 1.0),
                        f"{prozent(zahl_aus(m.get('direction_agreement'), 0.0) or 0.0)}%", f"{zahl_aus(m.get('runtime_seconds'), 0.0) or 0.0:.1f}",
                    ]
                    for m in modelle
                ],
                f"Twitter-RoBERTa was kept: {prozent(zahl_aus(roberta.get('direction_agreement'), 0.0) or 0.0)}% direction agreement against VADER's {prozent(zahl_aus(vader.get('direction_agreement'), 0.0) or 0.0)}%, at similar correlation.",
            ),
            tabelle(
                "Every market in the sample",
                ["Market", "Category", "Probability", "Sentiment", "Stance", "Posts"],
                [
                    [
                        z.get("question", ""), z.get("category", ""), f"{prozent(zahl_aus(z.get('probability'), 0.0) or 0.0)}%",
                        f"{zahl_aus(z.get('adjusted_weighted'), 0.0) or 0.0:+.3f}", f"{zahl_aus(z.get('stance_score'), 0.0) or 0.0:+.3f}", z.get("n_total", ""),
                    ]
                    for z in maerkte
                ],
                "Sentiment is the post-weighted mean of the RoBERTa compound score; stance is the mean of the supports-minus-opposes score.",
            ),
            tabelle(
                "How much the semantic filter keeps",
                ["Market", "Raw posts", "Kept at 0.20", "Retention"],
                [
                    [f.get("market_question", ""), f.get("raw_posts", ""), f.get("retained_posts_threshold_0_20", ""), f"{prozent(zahl_aus(f.get('retention_pct'), 0.0) or 0.0, 0)}%"]
                    for f in filter_zeilen
                ],
                f"Retention ranges from {prozent(min(retention), 0) if retention else '—'}% to {prozent(max(retention), 0) if retention else '—'}%: on some questions Reddit has almost nothing on topic.",
            ),
        ],
        "basis": {"maerkte": n, "beobachtungen": posts, "fenster": str(stich.get("erhoben_utc", ""))[:10]},
        "report": REPORT,
        "modul": MODUL,
        "kategorien_n": kategorien_n,
        "schlagworte": ["reddit", "sentiment", "nlp", "negative result"],
    }
    return {
        "hinweis": HINWEIS,
        "einleitung": EINLEITUNG,
        "stand_utc": jetzt_iso(jetzt),
        "kennzeichnung": "research/frozen",
        "fehlend": [],
        "studie": studie,
    }


HINWEIS = (
    "A negative result, published as one. Course project (FHNW, spring 2026) by Pablo Cruz and Daliah Beck; "
    "the numbers are recomputed from the market table and cross-checked against the report."
)
EINLEITUNG = (
    "Before the order-book work, an earlier question: is there anything in what people say online that the price has not "
    "already got? This study took the crudest version of that idea, Reddit mood on a keyword match, and measured it against "
    "live Polymarket prices. It found nothing, and the audit of the retrieved posts says why."
)
