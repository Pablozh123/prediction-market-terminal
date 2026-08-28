"""Aufbereitung der statischen Analyse-JSONs aus public/data fuer die Website.

Die Dateien stammen aus dem taeglichen Review-Lauf des Analyse-Repos
(daily_review_run) und werden hier nur GELESEN und umgeformt: kein
Backend-Call, kein LLM, keine Keys. Alle Funktionen sind Streamlit-frei
und mit Fixtures testbar.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PUBLISH_FILES = (
    "queue.json",
    "kategorie_karte.json",
    "mentions_latenz.json",
    "pipeline_forward.json",
    "audit.json",
    "meta.json",
    "runs.json",
)

SCORE_BANDS = ("high", "medium", "low")

#: Publizierte Empfehlungs-Whitelist -> Anzeige-Label (Badge).
EMPFEHLUNG_LABELS = {
    "watch": "WATCH",
    "check_source": "CHECK SOURCE",
    "escalate_human": "ESCALATE HUMAN",
}

#: Kategorien, deren Konvergenzzeit eine dokumentierte Obergrenze ist
#: (enthaelt Spiel- bzw. Zeremoniedauer).
CENSORED_KATEGORIEN = ("Sport", "Popkultur", "Sports", "Pop culture")

#: Die Kennzahlen-Zeilen kommen seit terminal/category_efficiency mit
#: englischen Namen (Politics, Sports, ...), die kuratierten Beispiele der
#: Thesis tragen die deutschen (Politik, Sport, ...). Der Join laeuft ueber
#: einen normierten Schluessel, damit beide Formen zusammenfinden.
KATEGORIE_ALIAS = {
    "politik": "politics",
    "sport": "sports",
    "krypto": "crypto",
    "popkultur": "pop culture",
    "wirtschaft": "business/finance",
    "wissenschaft": "science/tech",
}


def kategorie_schluessel(name: Any) -> str:
    """Normierter Kategorienschluessel: klein, getrimmt, deutsch -> englisch."""

    key = str(name or "").strip().casefold()
    return KATEGORIE_ALIAS.get(key, key)

#: Lesbare Ticks fuer die log-Zeitachse (Minuten, 1 min bis 8 h).
LOG_TICKS = ((1, "1 min"), (5, "5 min"), (15, "15 min"), (60, "1 h"), (240, "4 h"), (480, "8 h"))


def load_publish_payload(publish_dir: Path, name: str) -> dict[str, Any] | None:
    """JSON aus dem Publish-Ordner lesen; None bei fehlend oder unlesbar."""

    path = Path(publish_dir) / name
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def filter_queue_cards(cards: list[dict[str, Any]], band: str) -> list[dict[str, Any]]:
    """Fallkarten nach Score-Band filtern; ``band`` ausserhalb der Baender = alle."""

    if band not in SCORE_BANDS:
        return list(cards)
    return [card for card in cards if card.get("score_band") == band]


def kategorie_points(karte: dict[str, Any]) -> list[dict[str, Any]]:
    """Chart-Punkte: Brier T-7 je Kategorie vs. Einpreisungs-Minuten.

    Join der Kennzahlen-Zeilen mit den Latenz-Beispielen ueber den
    Kategorienamen. Punkte ohne beide Werte werden ausgelassen. Sport und
    Popkultur sind Obergrenzen (Konvergenz enthaelt Spiel-/Zeremoniedauer)
    und werden mit ``censored=True`` markiert.
    """

    beispiel_by_kategorie = {
        kategorie_schluessel(item.get("kategorie", "")): item for item in karte.get("beispiele", [])
    }
    points: list[dict[str, Any]] = []
    for zeile in karte.get("kategorien", karte.get("zeilen", [])):
        kategorie = str(zeile.get("kategorie", ""))
        beispiel = beispiel_by_kategorie.get(kategorie_schluessel(kategorie))
        brier = zeile.get("brier_t7")
        minuten = beispiel.get("minuten_bis_konvergenz") if beispiel else None
        if brier is None or minuten is None:
            continue
        # Log-Achsen verschlucken nicht-positive Werte still. Konvention der
        # Quell-Abbildungen: vor dem Ereignis eingepreist => Untergrenze 1 Minute.
        minuten_roh = float(minuten)
        points.append(
            {
                "kategorie": kategorie,
                "minuten": max(minuten_roh, 1.0),
                "minuten_roh": minuten_roh,
                "brier_t7": float(brier),
                "censored": kategorie in CENSORED_KATEGORIEN,
                "hinweis": str(beispiel.get("praezisions_hinweis", "")) if beispiel else "",
                "n_maerkte": int(zeile.get("n_maerkte", 0) or 0),
                # Seit terminal/category_efficiency traegt jede Zeile ihr n am
                # T-7-Horizont; die Thesis-Zeilen haben es als n_t7.
                "n_t7": int(zeile.get("n_t7", 0) or 0),
            }
        )
    return points


def kategorie_horizont_rows(karte: dict[str, Any]) -> list[dict[str, Any]]:
    """Eine Zeile je Kategorie und Horizont, alte und neue Nutzlast gleich.

    Die veroeffentlichte ``kategorie_karte.json`` hatte zwei Formen. Die alte
    traegt je Kategorie flach ``brier_t7``/``brier_t1``; die neue, die
    ``category_efficiency.publish_payload`` schreibt, traegt eine Liste
    ``horizonte`` mit dem Brier, seinem 95-Prozent-Intervall
    (``brier_ci95``), n, dem Anteil bereits entschiedener Preise und dem
    Brier auf den offenen Preisen.

    Ohne das Intervall ist eine Rangfolge ueber ein Dutzend Kategorien und
    fuenf Horizonte keine Aussage: der beste von sechzig Werten ist das
    Minimum aus sechzig Ziehungen. Deshalb liest diese Funktion die neue Form,
    wo sie da ist, und faellt sonst auf die flachen Spalten zurueck, statt
    eine Tabelle mit lauter fehlenden Spalten zu erzeugen.
    """

    def _zahl(value: Any) -> float | None:
        try:
            if value is None or value == "":
                return None
            zahl = float(value)
        except (TypeError, ValueError):
            return None
        return None if zahl != zahl else zahl

    def _ganz(value: Any) -> int | None:
        zahl = _zahl(value)
        return None if zahl is None else int(zahl)

    rows: list[dict[str, Any]] = []
    for zeile in (karte or {}).get("kategorien", []) or []:
        name = str(zeile.get("kategorie", "") or "")
        if not name:
            continue
        horizonte = [h for h in (zeile.get("horizonte") or []) if h and h.get("horizont_tage") is not None]
        if not horizonte:
            horizonte = [
                {"horizont_tage": 7, "brier": zeile.get("brier_t7"),
                 "trefferquote": zeile.get("trefferquote_t7"), "n": zeile.get("n_t7")},
                {"horizont_tage": 1, "brier": zeile.get("brier_t1"),
                 "trefferquote": zeile.get("trefferquote_t1"), "n": zeile.get("n_t1")},
            ]
        for h in sorted(horizonte, key=lambda x: -int(x.get("horizont_tage", 0) or 0)):
            ci = h.get("brier_ci95") if isinstance(h.get("brier_ci95"), (list, tuple)) else [None, None]
            ci_low, ci_high = (_zahl(ci[0]), _zahl(ci[1])) if len(ci) == 2 else (None, None)
            rows.append({
                "kategorie": name,
                "horizont_tage": int(h.get("horizont_tage", 0) or 0),
                "brier": _zahl(h.get("brier")),
                # Halbe Breite des Intervalls: die Zahl, die neben dem Brier
                # entscheidet, ob zwei Kategorien ueberhaupt getrennt sind.
                "brier_halbbreite": None if ci_low is None or ci_high is None else (ci_high - ci_low) / 2.0,
                "brier_ci_low": ci_low,
                "brier_ci_high": ci_high,
                "trefferquote": _zahl(h.get("trefferquote")),
                "n": _ganz(h.get("n")),
                "anteil_entschieden": _zahl(h.get("anteil_entschieden")),
                "brier_offen": _zahl(h.get("brier_offen")),
                "n_offen": _ganz(h.get("n_offen")),
                "n_maerkte": _ganz(zeile.get("n_maerkte")),
                "median_volumen_usd": _zahl(zeile.get("median_volumen_usd")),
            })
    return rows


def kategorie_zellen_satz(rows: list[dict[str, Any]]) -> str:
    """Wie viele Zellen die Rangfolge gebildet haben, und was das bedeutet.

    Leer, wenn nichts gescored wurde. Gleiche Aussage wie auf der
    Web-Oberflaeche, damit beide Seiten denselben Vorbehalt tragen.
    """

    gescored = [r for r in rows if r.get("brier") is not None and (r.get("n") or 0) > 0]
    if not gescored:
        return ""
    n = len(gescored)
    mit_ci = any(r.get("brier_halbbreite") is not None for r in gescored)
    satz = (
        f"{n} category-by-horizon cells are scored here. The best of {n} cells is the smallest of "
        f"{n} draws, so a leading Brier is not by itself a difference"
    )
    if mit_ci:
        return satz + (
            ". The interval column is the 95% interval around each cell; two cells whose "
            "intervals overlap are not separated by this sample."
        )
    return satz + ". This payload carries no interval per cell, so no cell can be told apart from another."


def mentions_bars(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Balkendaten je ok-Fall, absteigend nach handelbarem Fenster sortiert."""

    rows: list[dict[str, Any]] = []
    for fall in payload.get("faelle", []):
        reaktion = fall.get("minuten_bis_erste_reaktion")
        konvergenz = fall.get("minuten_bis_konvergenz")
        if reaktion is None and konvergenz is None:
            continue
        fenster = fall.get("stunden_im_handelbaren_fenster")
        rows.append(
            {
                "event": str(fall.get("event", "")),
                "reaktion_min": None if reaktion is None else float(reaktion),
                "konvergenz_min": None if konvergenz is None else float(konvergenz),
                "handelbares_fenster_h": None if fenster is None else float(fenster),
                "outcome": str(fall.get("korrekt_aufgeloestes_outcome", "")),
            }
        )
    rows.sort(
        key=lambda r: (r["handelbares_fenster_h"] is None, -(r["handelbares_fenster_h"] or 0.0))
    )
    return rows


def pipeline_laeufe(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Laeufe des Paper-Artefakts, juengster zuerst (Reihenfolge der Quelle).

    Aeltere Artefakte kennen nur die obersten Felder; daraus wird ein einzelner
    Lauf gebildet, damit die Seite eine Quelle hat. Gezaehlt wird nicht neu --
    ``n_eintraege``/``n_kaeufe`` stammen aus dem Artefakt, fehlen sie, werden
    sie aus den Eintraegen abgeleitet.
    """

    roh = payload.get("laeufe")
    if not isinstance(roh, list) or not roh:
        eintraege = payload.get("eintraege", []) or []
        if not eintraege:
            return []
        roh = [
            {
                "profil": "",
                "eintraege": eintraege,
                "wortzaehler_endstaende": payload.get("wortzaehler_endstaende", {}) or {},
            }
        ]

    laeufe: list[dict[str, Any]] = []
    for lauf in roh:
        if not isinstance(lauf, dict):
            continue
        eintraege = lauf.get("eintraege", []) or []
        n_kaeufe = lauf.get("n_kaeufe")
        if n_kaeufe is None:
            n_kaeufe = sum(
                1 for e in eintraege if str(e.get("action", "NONE")) != "NONE"
            )
        laeufe.append(
            {
                "profil": str(lauf.get("profil", "")),
                "n_eintraege": int(lauf.get("n_eintraege", len(eintraege))),
                "n_kaeufe": int(n_kaeufe),
                "eintraege": eintraege,
                "wortzaehler_endstaende": lauf.get("wortzaehler_endstaende", {}) or {},
                # Extraktionsquote (seit 27.07. im Artefakt): Ausfuehrungs-
                # guete des Sweeps — gekaufte vs. im Kaufmoment unter dem
                # Preisdeckel verfuegbare Buch-Tiefe. None bei aelteren
                # Artefakten oder Laeufen ohne Kaeufe. Keine PnL-Aussage.
                "extraktion_gekauft_usd": lauf.get("extraktion_gekauft_usd"),
                "extraktion_verfuegbar_usd": lauf.get("extraktion_verfuegbar_usd"),
                "extraktionsquote": lauf.get("extraktionsquote"),
            }
        )
    return laeufe


def pipeline_default_lauf(laeufe: list[dict[str, Any]]) -> int:
    """Index des Laufs, den die obersten Artefakt-Felder spiegeln.

    Gleiche Regel wie im Publish-Schritt: juengster Lauf mit Kaeufen, sonst der
    juengste ueberhaupt. Damit zeigt die Seite denselben Lauf, den ``hinweis``
    als Profil nennt.
    """

    for i, lauf in enumerate(laeufe):
        if lauf.get("n_kaeufe"):
            return i
    return 0


def pipeline_timeline(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Zeilen des beobachtenden Paper-Laufs in Log-Reihenfolge (Whitelist-Felder)."""

    rows: list[dict[str, Any]] = []
    for entry in payload.get("eintraege", []):
        rows.append(
            {
                "action": str(entry.get("action", "")),
                "reason": str(entry.get("reason", "")),
                "limit_price": entry.get("limit_price"),
                "bestes_angebot": entry.get("bestes_angebot"),
                "bestes_gebot": entry.get("bestes_gebot"),
                "size_usd": entry.get("size_usd"),
                # Je Kauf: verfuegbare Tiefe unterm Deckel + Quote in
                # PROZENT fuer die Anzeige (None bei Nicht-Kaeufen und
                # aelteren Artefakten).
                "verfuegbar_usd": entry.get("verfuegbar_usd"),
                "extraktionsquote": (
                    None
                    if entry.get("extraktionsquote") is None
                    else round(float(entry["extraktionsquote"]) * 100, 1)
                ),
            }
        )
    return rows


def pipeline_action_counts(payload: dict[str, Any]) -> dict[str, int]:
    """Zaehler je Entscheidung (z.B. {'NONE': 34, 'YES': 1})."""

    counts: dict[str, int] = {}
    for entry in payload.get("eintraege", []):
        action = str(entry.get("action", ""))
        counts[action] = counts.get(action, 0) + 1
    return counts


def format_sekunden(value: Any) -> str:
    """Sekunden menschenlesbar: unter 2 Minuten in s, sonst in Minuten."""

    if value is None:
        return "--"
    seconds = float(value)
    if seconds < 120:
        return f"{seconds:.0f} s"
    return f"{seconds / 60.0:.0f} min"


def _run_kpis_aus_laeufen(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Kopfzahlen direkt aus den Laufwerten, wenn kein Aggregat vorliegt.

    Ueber public/data/runs.json reproduziert das die publizierten Zahlen
    exakt (23 Laeufe, 27 Wetten, 25W/2L, $1.172,23 Einsatz, +$288,67).
    """

    wetten = [w for run in runs for w in (run.get("wetten") or [])]
    aufgeloest = [w for w in wetten if w.get("aufgeloest") and w.get("gewonnen") is not None]
    einsatz = sum(float(w.get("einsatz_usd") or 0.0) for w in wetten)
    aufgeloester_einsatz = sum(float(w.get("einsatz_usd") or 0.0) for w in aufgeloest)
    payout = sum(float(w.get("payout_usd") or 0.0) for w in aufgeloest)
    pnl = sum(float(w.get("pnl_usd") or 0.0) for w in aufgeloest)
    return {
        "n_runs": len(runs),
        "n_wetten": len(wetten),
        "gewonnen": sum(1 for w in aufgeloest if w.get("gewonnen")),
        "verloren": sum(1 for w in aufgeloest if not w.get("gewonnen")),
        "offen": len(wetten) - len(aufgeloest),
        "einsatz_usd": round(einsatz, 2),
        "aufgeloester_einsatz_usd": round(aufgeloester_einsatz, 2),
        "realisierter_payout_usd": round(payout, 2),
        "realisierter_pnl_usd": round(pnl, 2),
        "roi_realisiert_pct": round(pnl / aufgeloester_einsatz * 100.0, 1) if aufgeloester_einsatz > 0 else None,
        "offener_einsatz_usd": round(einsatz - aufgeloester_einsatz, 2),
    }


def run_kpis(payload: dict[str, Any]) -> dict[str, Any]:
    """Aggregat-Kennzahlen mit Defaults fuer die Dashboard-Kopfzeile.

    Ohne ``aggregat`` wurde hier fuer jede Zahl 0 zurueckgegeben, und die
    Seite druckte "Runs 0" ueber die Karten von 23 Laeufen: ein Standardwert
    in der Rolle einer Messung. Traegt die Nutzlast Laeufe, aber kein
    Aggregat, werden die Kopfzahlen aus den Laeufen gerechnet und ``basis``
    sagt, woher sie kommen.
    """

    aggregat = payload.get("aggregat") or {}
    runs = list(payload.get("runs") or [])
    if not aggregat and runs:
        return dict(
            _run_kpis_aus_laeufen(runs),
            wallet_netto_usd=None,
            wallet_kaeufe_usd=None,
            wallet_abgleich_stand=None,
            basis="recomputed",
        )
    return {
        "basis": "published" if aggregat else "empty",
        "n_runs": int(aggregat.get("n_runs", 0) or 0),
        "n_wetten": int(aggregat.get("n_wetten", 0) or 0),
        "gewonnen": int(aggregat.get("gewonnen", 0) or 0),
        "verloren": int(aggregat.get("verloren", 0) or 0),
        "offen": int(aggregat.get("offen", 0) or 0),
        "einsatz_usd": float(aggregat.get("einsatz_usd", 0.0) or 0.0),
        "aufgeloester_einsatz_usd": float(
            aggregat.get("aufgeloester_einsatz_usd", 0.0) or 0.0
        ),
        "realisierter_payout_usd": float(
            aggregat.get("realisierter_payout_usd", 0.0) or 0.0
        ),
        "realisierter_pnl_usd": float(
            aggregat.get("realisierter_pnl_usd", 0.0) or 0.0
        ),
        "roi_realisiert_pct": aggregat.get("roi_realisiert_pct"),
        "offener_einsatz_usd": float(
            aggregat.get("offener_einsatz_usd", 0.0) or 0.0
        ),
        # Wallet-Wahrheit (kuratierter Abgleich); None ohne Overlay.
        "wallet_netto_usd": aggregat.get("wallet_netto_usd"),
        "wallet_kaeufe_usd": aggregat.get("wallet_kaeufe_usd"),
        "wallet_abgleich_stand": aggregat.get("wallet_abgleich_stand"),
    }


def run_latenz_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Latenz-Zeilen je Run fuer die Balken auf der Latenz-Seite."""

    rows: list[dict[str, Any]] = []
    for run in payload.get("runs", []):
        rows.append(
            {
                "profil": str(run.get("profil", "")),
                "quelle": str(run.get("drop_quelle", "")),
                "episode_titel": str(run.get("episode_titel", "")),
                "erkennungslatenz_s": run.get("erkennungslatenz_s"),
                "erste_entscheidung_s": run.get("erste_entscheidung_s"),
                "erster_fill_s": run.get("erster_fill_s"),
                "n_wetten": len(run.get("wetten", []) or []),
            }
        )
    return rows


def wette_status(wette: dict[str, Any]) -> tuple[str, str]:
    """(Anzeige-Label, Statusklasse win/loss/open) fuer eine Wette."""

    if not wette.get("aufgeloest"):
        return "OPEN", "open"
    if wette.get("gewonnen"):
        return "WON", "win"
    return "LOST", "loss"


def run_wetten_rows(run: dict[str, Any]) -> list[dict[str, Any]]:
    """Wetten eines Runs als flache Anzeigezeilen (inkl. Statusklasse)."""

    rows: list[dict[str, Any]] = []
    for wette in run.get("wetten", []) or []:
        label, klasse = wette_status(wette)
        # Verifizierte Fill-Werte (Wallet-Abgleich oder exakte FAK-Antwort)
        # ersetzen die Log-Schaetzungen; sonst Log-Werte mit Flag False.
        verifiziert = wette.get("wallet_avg_fill_preis") is not None
        einsatz = (
            wette.get("wallet_einsatz_usd")
            if verifiziert else wette.get("einsatz_usd")
        )
        shares = (
            wette.get("wallet_shares") if verifiziert else wette.get("shares")
        )
        pnl = (
            wette.get("wallet_pnl_usd")
            if verifiziert and wette.get("wallet_pnl_usd") is not None
            else wette.get("pnl_usd")
        )
        payout = wette.get("payout_usd")
        roi = wette.get("roi_pct")
        if verifiziert and pnl is not None and einsatz:
            payout = round(float(einsatz) + float(pnl), 2)
            roi = round(float(pnl) / float(einsatz) * 100.0, 1)
        rows.append(
            {
                "frage": str(wette.get("frage", "")),
                "seite": str(wette.get("seite", "")),
                "entscheidungs_preis": wette.get("entscheidungs_preis"),
                "avg_fill_preis": (
                    wette.get("wallet_avg_fill_preis")
                    if verifiziert else wette.get("avg_fill_preis")
                ),
                "fill_verifiziert": verifiziert,
                "shares": shares,
                "einsatz_usd": einsatz,
                "sweep_clips": int(wette.get("sweep_clips", 1) or 1),
                "status_label": label,
                "status_klasse": klasse,
                "payout_usd": payout,
                "pnl_usd": pnl,
                "roi_pct": roi,
                "aktueller_yes_preis": wette.get("aktueller_yes_preis"),
                "tape_rang": wette.get("tape_rang"),
                "fremde_davor": wette.get("fremde_davor"),
                "fremdvolumen_davor_usd": wette.get("fremdvolumen_davor_usd"),
                "verfolger_s": wette.get("verfolger_s"),
            }
        )
    return rows


def run_verpasste_rows(run: dict[str, Any]) -> list[dict[str, Any]]:
    """Verpasste Chancen (Budget-Skips) eines Runs als Tabellenzeilen."""

    rows: list[dict[str, Any]] = []
    for chance in run.get("verpasste_chancen", []) or []:
        waere = chance.get("waere_gewonnen")
        limit = chance.get("limit_preis")
        # Hypothetischer ROI je $1 zum uebersprungenen Limit-Preis.
        roi = None
        if waere is not None and limit and 0.0 < float(limit) < 1.0:
            roi = (1.0 - float(limit)) / float(limit) * 100.0 if waere else -100.0
        rows.append(
            {
                "frage": str(chance.get("frage", "")),
                "seite": str(chance.get("seite", "")),
                "limit_preis": limit,
                "grund": str(chance.get("grund", "")),
                "waere_gewonnen": waere,
                "hypo_roi_pct": roi,
            }
        )
    return rows


def audit_hash_rows(audit: dict[str, Any], limit: int = 50) -> list[dict[str, str]]:
    """Hash-Liste (Prompt/Output je Call) fuer die Audit-Ansicht, gekappt."""

    prompts = [str(h) for h in audit.get("prompt_hashes", [])]
    outputs = [str(h) for h in audit.get("output_hashes", [])]
    rows = [
        {"call": str(i + 1), "prompt_hash": p, "output_hash": o}
        for i, (p, o) in enumerate(zip(prompts, outputs))
    ]
    return rows[:limit]


def track_record_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Konsolidierter Track-Record: eine Zeile je Run fuer die Gesamtsicht."""

    rows: list[dict[str, Any]] = []
    for run in payload.get("runs", []):
        wetten = run.get("wetten", []) or []
        aufgeloest = [
            w for w in wetten
            if w.get("aufgeloest") and w.get("gewonnen") is not None
        ]
        race = run.get("race") or {}
        race_str = None
        if race.get("wetten_mit_tape"):
            race_str = f"{race.get('first_on', 0)}/{race.get('wetten_mit_tape')}"
        rows.append(
            {
                "profil": str(run.get("profil", "")),
                "episode_titel": str(run.get("episode_titel", "")),
                "quelle": str(run.get("drop_quelle", "")),
                "erkennungslatenz_s": run.get("erkennungslatenz_s"),
                "erster_fill_s": run.get("erster_fill_s"),
                "n_wetten": len(wetten),
                "gewonnen": sum(1 for w in aufgeloest if w.get("gewonnen")),
                "verloren": sum(1 for w in aufgeloest if not w.get("gewonnen")),
                # Cash wallet-first: Log-Werte nur als Fallback (Basis-Flag).
                "einsatz_usd": (
                    run.get("wallet_kaeufe_usd")
                    if run.get("wallet_kaeufe_usd") is not None
                    else run.get("einsatz_usd")
                ),
                "pnl_usd": (
                    run.get("wallet_netto_usd")
                    if run.get("wallet_netto_usd") is not None
                    else run.get("realisierter_pnl_usd")
                ),
                "cash_basis": (
                    "wallet" if run.get("wallet_netto_usd") is not None
                    else "log"
                ),
                "race_first": race_str,
                "sichtbare_tiefe_usd": run.get("sichtbare_tiefe_usd"),
                "einsatz_zu_sichtbarer_tiefe_pct": run.get(
                    "einsatz_zu_sichtbarer_tiefe_pct"
                ),
            }
        )
    return rows


def postmortem_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Kuratierte Vorfaelle, neueste zuerst; Felder unveraendert."""

    eintraege = list(payload.get("eintraege", []) or [])
    return sorted(eintraege, key=lambda e: str(e.get("datum", "")), reverse=True)


def pilot_overview(payload: dict[str, Any]) -> dict[str, Any]:
    """Kopfzahlen des vorregistrierten Piloten fuer die Pilot-Seite."""

    protokoll = payload.get("protokoll", {}) or {}
    zaehler = payload.get("signal_zaehler", {}) or {}
    return {
        "budget_usdc": protokoll.get("budget_usdc"),
        "einsatz_je_trade_usdc": protokoll.get("einsatz_je_trade_usdc"),
        "regel_freeze_datum": str(protokoll.get("regel_freeze_datum", "")),
        "handelsfenster_bis": str(protokoll.get("handelsfenster_bis", "")),
        "quelle": str(protokoll.get("quelle", "")),
        "arm1_kurz": str(protokoll.get("arm1_kurz", "")),
        "arm2_kurz": str(protokoll.get("arm2_kurz", "")),
        "watcher_lauf_ts_utc": payload.get("watcher_lauf_ts_utc"),
        "n_signale": sum(int(v) for v in zaehler.values()),
        "zaehler": {str(k): int(v) for k, v in zaehler.items()},
        "n_trades": len(payload.get("trades", []) or []),
    }


def pilot_signal_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Neueste Watcher-Signale fuer die Pilot-Tabelle (bereits gekappt)."""

    return list(payload.get("signale_neueste", []) or [])
