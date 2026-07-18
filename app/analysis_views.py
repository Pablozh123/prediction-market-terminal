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
CENSORED_KATEGORIEN = ("Sport", "Popkultur")

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
        str(item.get("kategorie", "")): item for item in karte.get("beispiele", [])
    }
    points: list[dict[str, Any]] = []
    for zeile in karte.get("kategorien", karte.get("zeilen", [])):
        kategorie = str(zeile.get("kategorie", ""))
        beispiel = beispiel_by_kategorie.get(kategorie)
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
            }
        )
    return points


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


def run_kpis(payload: dict[str, Any]) -> dict[str, Any]:
    """Aggregat-Kennzahlen mit Defaults fuer die Dashboard-Kopfzeile."""

    aggregat = payload.get("aggregat") or {}
    return {
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
        rows.append(
            {
                "frage": str(wette.get("frage", "")),
                "seite": str(wette.get("seite", "")),
                "entscheidungs_preis": wette.get("entscheidungs_preis"),
                "avg_fill_preis": wette.get("avg_fill_preis"),
                "shares": wette.get("shares"),
                "einsatz_usd": wette.get("einsatz_usd"),
                "sweep_clips": int(wette.get("sweep_clips", 1) or 1),
                "status_label": label,
                "status_klasse": klasse,
                "payout_usd": wette.get("payout_usd"),
                "pnl_usd": wette.get("pnl_usd"),
                "roi_pct": wette.get("roi_pct"),
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
                "einsatz_usd": run.get("einsatz_usd"),
                "pnl_usd": run.get("realisierter_pnl_usd"),
                "race_first": race_str,
                "sichtbare_tiefe_usd": run.get("sichtbare_tiefe_usd"),
                "einsatz_zu_sichtbarer_tiefe_pct": run.get(
                    "einsatz_zu_sichtbarer_tiefe_pct"
                ),
                "wallet_netto_usd": run.get("wallet_netto_usd"),
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
