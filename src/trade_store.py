"""Persistenter Whale-Tape-Speicher: das Gedaechtnis des Co-Trading-Netzwerks.

Der Risk-Screen baut sein Netzwerk bisher aus dem Live-Tape, und acht Seiten
Data-API sind auf dieser Venue rund ein Tag. Cluster bauen sich aber ueber
Wochen auf — der dokumentierte US-Iran-Ring lief ueber Monate —, und in einem
Tag Tape teilt kaum ein Wallet-Paar drei Maerkte. Genau deshalb faellt die
Regelleiter des Graphen so oft auf die unterste Sprosse: nicht weil keine
Struktur da waere, sondern weil das Fenster zu kurz ist (Phase 1 des
Wallet-Graph-Plans, docs/HANDOFF-WALLET-GRAPH.md).

Dieser Speicher sammelt dieselben Prints dauerhaft in SQLite. Geschrieben
wird von einem Prozess (scripts/run_trade_ingest.py als Runner; optional
traegt die API mit ``TRADE_STORE_RECORD=1`` ihre ohnehin geholten Seiten
ein), gelesen von ``extend_tape``, das das Live-Tape des Risk-Screens um das
gespeicherte Fenster anreichert. Ohne Datei aendert sich nichts — der Screen
faellt auf das reine Live-Tape zurueck, und zwar erkennbar: der Zuschnitt
reist wie ueberall am Frame mit (``md.SAMPLE_ATTR``), und ``store_note``
macht daraus den Satz unter dem Bild. "Kein Cluster" aus zwei Wochen Tape
ist ein anderer Befund als aus einem Tag, und die Bildunterschrift muss
sagen koennen, welcher von beiden es war.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

import pandas as pd

from src import prediction_markets as md

DEFAULT_STORE_PATH = Path("data") / "trade_store.sqlite"

#: Spalten, die ein Print im Speicher behaelt. Bewusst die Teilmenge des
#: Tape-Frames (get_polymarket_trades), die Screen, Kontextfilter und
#: Graph tatsaechlich lesen; ``url`` und ``platform`` sind ableitbar und
#: werden beim Laden rekonstruiert statt gespeichert.
STORED_COLUMNS = (
    "transaction_hash", "wallet", "asset", "timestamp", "side", "outcome",
    "title", "price", "size", "notional", "market_key", "slug", "trader",
)

#: Identitaet eines Prints, identisch zur Dedup-Regel von load_deep_tape:
#: ein On-Chain-Fill kann mehrere Wallets und Assets beruehren, dieselbe
#: Kombination aus allen dreien ist derselbe Print.
DEDUP_KEY = ("transaction_hash", "wallet", "asset")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    transaction_hash TEXT NOT NULL,
    wallet           TEXT NOT NULL,
    asset            TEXT NOT NULL,
    timestamp        INTEGER NOT NULL,
    side             TEXT DEFAULT '',
    outcome          TEXT DEFAULT '',
    title            TEXT DEFAULT '',
    price            REAL DEFAULT 0,
    size             REAL DEFAULT 0,
    notional         REAL DEFAULT 0,
    market_key       TEXT DEFAULT '',
    slug             TEXT DEFAULT '',
    trader           TEXT DEFAULT '',
    PRIMARY KEY (transaction_hash, wallet, asset)
);
CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades (timestamp);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS wallets (
    wallet     TEXT PRIMARY KEY,
    first_seen INTEGER NOT NULL,
    last_seen  INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS wallet_origin (
    wallet         TEXT PRIMARY KEY,
    first_trade_ts INTEGER,
    state          TEXT NOT NULL,
    fetched_at     INTEGER NOT NULL
);
"""


def store_path() -> Path:
    """Ablageort der Datei: ``TRADE_STORE_PATH`` oder data/trade_store.sqlite."""

    raw = os.environ.get("TRADE_STORE_PATH", "").strip()
    return Path(raw) if raw else DEFAULT_STORE_PATH


def window_days() -> float:
    """Lesefenster in Tagen: ``TRADE_STORE_WINDOW_DAYS`` oder 14.

    14 Tage sind der Startwert, kein Naturgesetz: lang genug, dass die
    strengen Sprossen der Regelleiter eine echte Chance haben, kurz genug,
    dass ein Paar aus dem letzten Monat nicht ewig als "aktuell" gilt.
    """

    try:
        value = float(os.environ.get("TRADE_STORE_WINDOW_DAYS", "").strip() or 14.0)
    except ValueError:
        value = 14.0
    return value if value > 0 else 14.0


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    """Verbindung mit Schema; legt Datei und Verzeichnis bei Bedarf an.

    WAL und busy_timeout wie beim Copy-Desk (src/copy_trading.py): ein
    Schreiber, gelegentliche Leser aus anderen Prozessen, keine Sperr-Kaskade.
    """

    ziel = Path(path) if path is not None else store_path()
    ziel.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(ziel), timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.executescript(_SCHEMA)
    return conn


def _set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def _get_meta(conn: sqlite3.Connection, key: str) -> str:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return str(row[0]) if row else ""


def record_tape(conn: sqlite3.Connection, frame: pd.DataFrame) -> int:
    """Prints einfuegen; bereits bekannte bleiben unangetastet. Gibt die Zahl
    der neuen Zeilen zurueck.

    ``INSERT OR IGNORE`` statt Upsert mit Absicht: ein Print ist ein
    historisches Ereignis, die erste geschriebene Fassung gilt. Zeilen ohne
    vollstaendigen Dedup-Schluessel oder Zeitstempel werden verworfen —
    ein Print ohne Identitaet wuerde als Duplikat wiederkommen, sobald die
    Quelle ihn erneut liefert.
    """

    if frame is None or frame.empty:
        return 0
    df = frame.copy()
    for spalte in STORED_COLUMNS:
        if spalte not in df.columns:
            df[spalte] = "" if spalte not in ("timestamp", "price", "size", "notional") else 0
    df = df[list(STORED_COLUMNS)]
    df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce")
    for schluessel in DEDUP_KEY:
        df[schluessel] = df[schluessel].astype(str).str.strip()
        df = df[df[schluessel] != ""]
    df = df.dropna(subset=["timestamp"])
    if df.empty:
        return 0
    df["timestamp"] = df["timestamp"].astype("int64")
    df = df.drop_duplicates(subset=list(DEDUP_KEY), keep="first")

    platzhalter = ", ".join("?" for _ in STORED_COLUMNS)
    vorher = conn.total_changes
    conn.executemany(
        f"INSERT OR IGNORE INTO trades ({', '.join(STORED_COLUMNS)}) VALUES ({platzhalter})",
        list(df.itertuples(index=False, name=None)),
    )
    neu = conn.total_changes - vorher
    # First/Last-Seen je Wallet, idempotent (MIN/MAX): Ueberlappung zwischen
    # Zyklen ist der Normalfall und darf die Werte nie verschieben. Die
    # Tabelle ueberlebt ``prune`` mit Absicht — ein First-Seen ist eine
    # Untergrenze des Wallet-Alters und wird durch das Loeschen alter Prints
    # nicht falsch, nur durch das Vergessen.
    spanne = df.groupby(df["wallet"].str.lower())["timestamp"].agg(["min", "max"])
    conn.executemany(
        "INSERT INTO wallets (wallet, first_seen, last_seen) VALUES (?, ?, ?) "
        "ON CONFLICT(wallet) DO UPDATE SET "
        "first_seen = MIN(first_seen, excluded.first_seen), "
        "last_seen = MAX(last_seen, excluded.last_seen)",
        [(str(wallet), int(zeile["min"]), int(zeile["max"])) for wallet, zeile in spanne.iterrows()],
    )
    _set_meta(conn, "last_ingest_utc", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    conn.commit()
    return int(neu)


def first_seen_map(conn: sqlite3.Connection, wallets: Any | None = None) -> dict[str, int]:
    """Wallet -> erster gespeicherter Print (Unix-Sekunden), Schluessel klein.

    "First seen" heisst: zuerst gesehen, seit der Ingest laeuft — eine
    Untergrenze des Alters, kein Geburtsdatum. Genau die Richtung, die das
    Frische-Signal braucht: wen der Store seit Wochen kennt, der ist
    bewiesenermassen nicht neu; wen er heute zum ersten Mal sieht, der kann
    trotzdem alt sein und bleibt Kandidat.
    """

    if wallets is None:
        cursor = conn.execute("SELECT wallet, first_seen FROM wallets")
        return {str(w): int(ts) for w, ts in cursor.fetchall()}
    schluessel = sorted({str(w).strip().lower() for w in wallets if str(w).strip()})
    ergebnis: dict[str, int] = {}
    for start in range(0, len(schluessel), 500):
        stueck = schluessel[start:start + 500]
        marken = ",".join("?" for _ in stueck)
        cursor = conn.execute(
            f"SELECT wallet, first_seen FROM wallets WHERE wallet IN ({marken})", stueck)
        ergebnis.update({str(w): int(ts) for w, ts in cursor.fetchall()})
    return ergebnis


def origin_map(conn: sqlite3.Connection, wallets: Any | None = None) -> dict[str, dict[str, Any]]:
    """Wallet -> ``{first_trade_ts, state, fetched_at}`` from the origin cache.

    The first trade of a wallet on the venue, as the Data API named it
    (app/wallet_origin.py). Unlike ``first_seen`` this is not a floor but the
    thing itself, and it never changes once measured: one answer per wallet,
    kept for good. Keys are lowercased.
    """

    if wallets is None:
        cursor = conn.execute("SELECT wallet, first_trade_ts, state, fetched_at FROM wallet_origin")
        rows = cursor.fetchall()
    else:
        schluessel = sorted({str(w).strip().lower() for w in wallets if str(w).strip()})
        rows = []
        for start in range(0, len(schluessel), 500):
            stueck = schluessel[start:start + 500]
            marken = ",".join("?" for _ in stueck)
            rows.extend(conn.execute(
                f"SELECT wallet, first_trade_ts, state, fetched_at FROM wallet_origin WHERE wallet IN ({marken})",
                stueck).fetchall())
    return {
        str(wallet): {
            "first_trade_ts": int(stamp) if stamp is not None else None,
            "state": str(state),
            "fetched_at": int(fetched or 0),
        }
        for wallet, stamp, state, fetched in rows
    }


def record_origins(conn: sqlite3.Connection, rows: Iterable[Mapping[str, Any]]) -> int:
    """Upsert origin rows (``wallet``, ``first_trade_ts``, ``state``,
    ``fetched_at``). A measured first trade is never overwritten by a later
    ``none`` or ``error``: the venue does not un-know a trade."""

    eintraege = []
    for row in rows or []:
        wallet = str(row.get("wallet") or "").strip().lower()
        if not wallet:
            continue
        stamp = row.get("first_trade_ts")
        try:
            stamp = int(stamp) if stamp is not None else None
        except (TypeError, ValueError):
            stamp = None
        eintraege.append((wallet, stamp, str(row.get("state") or ""), int(row.get("fetched_at") or 0)))
    if not eintraege:
        return 0
    conn.executemany(
        "INSERT INTO wallet_origin (wallet, first_trade_ts, state, fetched_at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(wallet) DO UPDATE SET "
        "first_trade_ts = COALESCE(wallet_origin.first_trade_ts, excluded.first_trade_ts), "
        "state = CASE WHEN wallet_origin.state = 'measured' THEN wallet_origin.state ELSE excluded.state END, "
        "fetched_at = excluded.fetched_at",
        eintraege,
    )
    conn.commit()
    return len(eintraege)


def load_window(
    conn: sqlite3.Connection,
    days: float = 14.0,
    min_cash: float = 0.0,
    max_rows: int = 200_000,
) -> pd.DataFrame:
    """Das juengste Fenster als Tape-Frame, mit Zuschnitt-Vermerk am Frame.

    Die Spalten entsprechen ``get_polymarket_trades``; ``time`` und ``url``
    werden aus ``timestamp`` und ``slug`` rekonstruiert. ``max_rows``
    schneidet von der Gegenwart aus ab — faellt Tape heraus, sagt es der
    Vermerk (``rows_capped``), denn ein stilles Abschneiden saehe aus wie
    ein ruhiger Markt.
    """

    jetzt = datetime.now(timezone.utc).timestamp()
    grenze = int(jetzt - float(days) * 86_400)
    df = pd.read_sql_query(
        "SELECT * FROM trades WHERE timestamp >= ? AND notional >= ? "
        "ORDER BY timestamp DESC LIMIT ?",
        conn,
        params=(grenze, float(min_cash), int(max_rows)),
    )
    record: dict[str, Any] = {
        "source": "trade_store",
        "min_cash": float(min_cash),
        "rows": int(len(df)),
        "store_window_days": float(days),
        "rows_capped": bool(len(df) >= int(max_rows)),
        "store_last_ingest_utc": _get_meta(conn, "last_ingest_utc"),
    }
    if df.empty:
        leer = pd.DataFrame()
        leer.attrs[md.SAMPLE_ATTR] = record
        return leer
    df["time"] = pd.to_datetime(df["timestamp"], unit="s", utc=True, errors="coerce")
    df["platform"] = "Polymarket"
    df["url"] = "https://polymarket.com/event/" + df["slug"].astype(str)
    record["store_first_utc"] = df["time"].min().isoformat(timespec="seconds")
    record["store_last_utc"] = df["time"].max().isoformat(timespec="seconds")
    record["store_days_with_data"] = int(df["time"].dt.date.nunique())
    df.attrs[md.SAMPLE_ATTR] = record
    return df


def store_stats(conn: sqlite3.Connection) -> dict[str, Any]:
    """Bestand der Datei: Zeilen, Zeitspanne, letzter Ingest."""

    row = conn.execute(
        "SELECT COUNT(*), MIN(timestamp), MAX(timestamp) FROM trades"
    ).fetchone()
    zeilen = int(row[0] or 0)
    stats: dict[str, Any] = {
        "rows": zeilen,
        "first_utc": "",
        "last_utc": "",
        "last_ingest_utc": _get_meta(conn, "last_ingest_utc"),
    }
    if zeilen and row[1] is not None:
        stats["first_utc"] = datetime.fromtimestamp(int(row[1]), tz=timezone.utc).isoformat(timespec="seconds")
        stats["last_utc"] = datetime.fromtimestamp(int(row[2]), tz=timezone.utc).isoformat(timespec="seconds")
    return stats


def prune(conn: sqlite3.Connection, keep_days: float = 45.0) -> int:
    """Prints aelter als ``keep_days`` loeschen. Gibt die Zahl der geloeschten
    Zeilen zurueck; der Platz wird von SQLite wiederverwendet, nicht freigegeben.

    Die ``wallets``-Tabelle bleibt mit Absicht stehen: ein First-Seen ist eine
    Untergrenze des Wallet-Alters, und die wird durch das Loeschen alter
    Prints nicht falsch. Loeschte prune sie mit, saehe jede Wallet nach
    ``keep_days`` wieder wie ein Neuzugang aus, und das Frische-Signal
    bekaeme genau die Fehlalarme zurueck, die der Store ihm nimmt.
    """

    grenze = int(datetime.now(timezone.utc).timestamp() - float(keep_days) * 86_400)
    cursor = conn.execute("DELETE FROM trades WHERE timestamp < ?", (grenze,))
    conn.commit()
    return int(cursor.rowcount)


def ingest_once(
    conn: sqlite3.Connection,
    min_cash: float = 1000.0,
    pages: int = 4,
    page_size: int = 1000,
    fetch: Callable[..., pd.DataFrame] | None = None,
) -> dict[str, Any]:
    """Einen Abholzyklus fahren: Seiten holen, einfuegen, Zuschnitt melden.

    ``fetch`` existiert wie in ``paged_polymarket_trades``, damit der Zyklus
    netzfrei pruefbar ist. Der Rueckgabewert traegt den Seiten-Vermerk der
    Quelle weiter — bricht der Feed auf halber Strecke ab, steht das dort
    und nicht nur auf stdout.
    """

    tape = md.paged_polymarket_trades(min_cash, pages=pages, page_size=page_size, fetch=fetch)
    coverage = md.sample_coverage(tape)
    neu = record_tape(conn, tape) if not tape.empty else 0
    return {"fetched": int(len(tape)), "new": int(neu), "coverage": coverage}


def store_note(record: Any) -> str:
    """Der Satz ueber den Speicher-Anteil einer Stichprobe, oder "".

    Ergaenzt ``md.sample_note`` (das den Live-Anteil benennt) um das, was der
    Speicher beigetragen hat: wie viele Prints aus wie vielen Tagen, wie viele
    Tage davon ueberhaupt Daten tragen (ein Ingest-Loch ist sonst unsichtbar
    und laese sich als ruhige Woche), und wann zuletzt geschrieben wurde.
    """

    daten = dict(record) if isinstance(record, dict) else md.sample_coverage(record)
    zeilen = int(daten.get("store_rows") or 0)
    if not zeilen:
        return ""
    fenster = float(daten.get("store_window_days") or 0.0)
    tage = int(daten.get("store_days_with_data") or 0)
    teile = f"Plus persistent store: {zeilen:,} prints from a {fenster:.0f}-day window"
    if fenster and tage:
        teile += f" ({tage} of {int(round(fenster))} days hold data)"
    letzte = str(daten.get("store_last_ingest_utc") or "").strip()
    if letzte:
        teile += f", last ingest {letzte}"
    teile += "."
    gesamt = int(daten.get("combined_rows") or 0)
    if gesamt:
        teile += f" Combined tape after dedup: {gesamt:,} prints."
    if daten.get("store_rows_capped"):
        teile += " The store window was cut at its row cap, so the oldest days are missing."
    # Ein stehender Ingest hinterlaesst eine Luecke, die keine der beiden
    # Quellen benennt: das Live-Band reicht rund einen Tag zurueck, das
    # Speicherfenster endet beim letzten Ingest. Erst ab etwa einem Tag
    # Stillstand klaffen die beiden auseinander — und genau dann muss der
    # Satz unter dem Bild das sagen, sonst liest sich die Luecke als ruhige
    # Zeit.
    alter_h = _ingest_age_hours(letzte)
    if alter_h is not None and alter_h >= 24.0:
        teile += (f" The last ingest is {alter_h / 24.0:.1f} days back and the live band reaches"
                  " about one day: the tape in between is missing from this picture.")
    return teile


def _ingest_age_hours(stamp: str) -> float | None:
    """Stunden seit einem ISO-Zeitstempel, oder None bei Unlesbarem."""

    if not stamp:
        return None
    try:
        dann = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    if dann.tzinfo is None:
        dann = dann.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dann).total_seconds() / 3600.0


def extend_tape(
    live: pd.DataFrame,
    days: float | None = None,
    min_cash: float = 0.0,
    path: Path | str | None = None,
) -> pd.DataFrame:
    """Das Live-Tape um das gespeicherte Fenster anreichern.

    Fail-soft in jede Richtung: keine Datei, leere Datei oder ein Lesefehler
    geben das Live-Tape unveraendert zurueck — der Risk-Screen verhaelt sich
    dann exakt wie vor dieser Datei. Mit Speicher kommt die Vereinigung
    beider Baender (Dedup ueber ``DEDUP_KEY``), und der Vermerk des
    Live-Tapes behaelt seine Felder: ``md.sample_note`` beschreibt weiter
    den Live-Anteil, die ``store_*``-Felder tragen den Speicher-Anteil, und
    ``store_note`` macht daraus den zweiten Satz der Bildunterschrift.
    """

    ziel = Path(path) if path is not None else store_path()
    if not ziel.exists():
        return live
    try:
        conn = connect(ziel)
    except sqlite3.Error as exc:
        print(f"[warn] trade store open: {exc}")
        return live
    try:
        gespeichert = load_window(conn, days=days if days is not None else window_days(), min_cash=min_cash)
    except (sqlite3.Error, pd.errors.DatabaseError) as exc:
        print(f"[warn] trade store read: {exc}")
        return live
    finally:
        try:
            conn.close()
        except sqlite3.Error:
            pass
    if gespeichert.empty:
        return live

    speicher_record = md.sample_coverage(gespeichert)
    record = dict(md.sample_coverage(live))
    record.setdefault("source", "polymarket_trades")
    record["store_rows"] = int(speicher_record.get("rows") or 0)
    for schluessel in ("store_window_days", "store_first_utc", "store_last_utc",
                       "store_days_with_data", "store_last_ingest_utc"):
        if speicher_record.get(schluessel):
            record[schluessel] = speicher_record[schluessel]
    record["store_rows_capped"] = bool(speicher_record.get("rows_capped"))

    if live is None or live.empty:
        zusammen = gespeichert.copy()
    else:
        zusammen = pd.concat([live, gespeichert], ignore_index=True, sort=False)
        vorhanden = [s for s in DEDUP_KEY if s in zusammen.columns]
        if vorhanden:
            zusammen = zusammen.drop_duplicates(subset=vorhanden, keep="first")
        if "time" in zusammen.columns:
            zusammen = zusammen.sort_values("time", ascending=False)
        zusammen = zusammen.reset_index(drop=True)
    record["combined_rows"] = int(len(zusammen))
    zusammen.attrs[md.SAMPLE_ATTR] = record
    return zusammen


def maybe_record(frame: pd.DataFrame) -> int:
    """Live geholte Seiten in den Speicher uebernehmen, wenn das gewollt ist.

    ``TRADE_STORE_RECORD=1`` heisst: auch der API-Prozess traegt bei, was er
    ohnehin geholt hat. Standard ist aus — auf einem Host mit eigenem
    Ingest-Runner schreibt genau ein Prozess, und auf einem Host ohne
    Volume waere jede Schreibung nach dem naechsten Deploy wieder weg.
    Fehler landen als Warnung auf stdout und nie beim Aufrufer.
    """

    if os.environ.get("TRADE_STORE_RECORD", "").strip() != "1":
        return 0
    if frame is None or frame.empty:
        return 0
    try:
        conn = connect()
    except sqlite3.Error as exc:
        print(f"[warn] trade store open for record: {exc}")
        return 0
    try:
        return record_tape(conn, frame)
    except sqlite3.Error as exc:
        print(f"[warn] trade store record: {exc}")
        return 0
    finally:
        try:
            conn.close()
        except sqlite3.Error:
            pass
