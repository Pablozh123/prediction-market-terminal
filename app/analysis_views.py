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
)

SCORE_BANDS = ("high", "medium", "low")

#: Publizierte Empfehlungs-Whitelist -> Anzeige-Label.
EMPFEHLUNG_LABELS = {
    "beobachten": "Beobachten",
    "quelle_pruefen": "Quelle pruefen",
    "eskalation_mensch": "An Mensch eskalieren",
}

#: Kategorien, deren Konvergenzzeit eine dokumentierte Obergrenze ist
#: (enthaelt Spiel- bzw. Zeremoniedauer).
CENSORED_KATEGORIEN = ("Sport", "Popkultur")

#: Lesbare Ticks fuer die log-Zeitachse (Minuten, 1 Min bis 8 Std).
LOG_TICKS = ((1, "1 Min"), (5, "5 Min"), (15, "15 Min"), (60, "1 Std"), (240, "4 Std"), (480, "8 Std"))


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
    for zeile in karte.get("zeilen", []):
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
    """Balkendaten je ok-Fall (Reaktion vs. Konvergenz), nach Konvergenz sortiert."""

    rows: list[dict[str, Any]] = []
    for fall in payload.get("faelle", []):
        reaktion = fall.get("minuten_bis_erste_reaktion")
        konvergenz = fall.get("minuten_bis_konvergenz")
        if reaktion is None and konvergenz is None:
            continue
        rows.append(
            {
                "event": str(fall.get("event", "")),
                "reaktion_min": None if reaktion is None else float(reaktion),
                "konvergenz_min": None if konvergenz is None else float(konvergenz),
                "handelbares_fenster_h": fall.get("stunden_im_handelbaren_fenster"),
            }
        )
    rows.sort(key=lambda r: (r["konvergenz_min"] is None, r["konvergenz_min"] or 0.0))
    return rows


def pipeline_timeline(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Zeitleisten-Zeilen des beobachtenden Paper-Laufs (nur Whitelist-Felder)."""

    rows: list[dict[str, Any]] = []
    for entry in payload.get("eintraege", []):
        rows.append(
            {
                "ts": str(entry.get("ts", "")),
                "action": str(entry.get("action", "")),
                "reason": str(entry.get("reason", "")),
                "limit_price": entry.get("limit_price"),
                "size_usd": entry.get("size_usd"),
                "best_ask": entry.get("best_ask"),
                "best_bid": entry.get("best_bid"),
            }
        )
    rows.sort(key=lambda r: r["ts"])
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
