"""Funding-Graph und Entity-Aufloesung: Wallets ueber On-Chain-Belege verbinden.

Phase 2 des Wallet-Graph-Plans (docs/HANDOFF-WALLET-GRAPH.md). Der dokumentierte
US-Iran-Ring bestand aus neun Konten, die einzeln unauffaellig waren und erst
als Gruppe lesbar wurden. Die Spur, ueber die sich solche Gruppen finden
lassen, liegt auf Polygon offen: Konten finanzieren einander, teilen
Finanzierungsquellen und Auszahlungsziele, oder schieben Positionen direkt
weiter. Dieses Modul haelt diese Spuren als Kanten fest und fasst Wallets,
die harte Belege verbinden, zu einer Entity zusammen.

Die Grundregel kommt aus dem Produktvorschlag und ist hier Code, nicht Stil:

- **Stufe 1 (hart, fuehrt automatisch zusammen)**: direkte Collateral-Transfers
  zwischen zwei gescannten Wallets, gemeinsame externe Finanzierungsquelle,
  gemeinsames Auszahlungsziel, direkte Positions-Transfers (ERC-1155). Jede
  Kante traegt ihre Belege: Tx-Hashes, Betraege, Zeitfenster.
- **Stufe 2 (Kandidat, fuehrt NIE zusammen)**: dieselben Muster ueber eine
  Gegenpartei, die sich wie eine Boerse verhaelt (siehe ``degree_cap``).
  Kandidaten werden berichtet, nicht gemerged.
- Stufe 3 (Verhalten, Co-Trading) lebt weiter in ``app/suspicion.py`` und
  fuehrt ebenfalls nie zusammen.

Der ``degree_cap`` ist die Stellschraube zwischen den Stufen: eine externe
Adresse, die zwei bis vier unserer Wallets finanziert, ist ein plausibler
gemeinsamer Operator; eine Adresse, die dutzende finanziert, verhaelt sich
wie eine Boersen-Hotwallet, und "beide Kunden derselben Boerse" verbindet
niemanden. Ohne Labels ist der Grad die ehrlichste verfuegbare Trennung,
und sie steht als Parameter in jeder Kante, nicht in einem Kommentar.

Sprachregel (data/claims.yaml, ``screen_not_proof``): alles hier sind
Rechercheanlaesse ueber oeffentliche On-Chain-Daten. Eine Entity sagt "diese
Konten sind ueber belegte Transfers verbunden", nie mehr; Personen werden
nicht identifiziert. Die Payload-Felder heissen deshalb ``linked_wallets``
(Stufe 1, mit Belegen) und ``candidates`` (Stufe 2), nie etwas Staerkeres.

Speicher: eigene SQLite-Datei (WAL, ein Schreiber: der Scan-Runner
``scripts/run_entity_scan.py``), getrennt vom Tape-Store, weil beide
verschiedene Lebenszyklen haben: das Tape waechst dauernd, der Graph wird
je Scan-Runde neu abgeleitet. ``rebuild_edges`` und ``assign_entities``
sind deshalb idempotent und duerfen jederzeit erneut laufen.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd

DEFAULT_GRAPH_PATH = Path("data") / "entity_graph.sqlite"

#: Kantentypen. Die Namen sind Teil der API-Payload und damit der
#: Sprachregelung: sie beschreiben den Beleg, nicht eine Behauptung
#: ueber Personen.
TYP_DIRECT = "direct_transfer"
TYP_SHARED_FUNDER = "shared_funder"
TYP_SHARED_WITHDRAWAL = "shared_withdrawal"
TYP_POSITION = "position_transfer"
TYP_SHARED_HUB = "shared_hub_candidate"

STUFE_HART = 1
STUFE_KANDIDAT = 2

#: Bis zu so vielen Wallets an einer geteilten Gegenpartei fuehrt der Fund
#: hart zusammen; darueber ist es Infrastruktur (Stufe 2, Kandidat). Zwei ist
#: der Operator-Fall (eine private Quelle speist genau zwei Konten, wie Theos
#: gemeinsame Kraken-Finanzierung von Paaren); drei und mehr sind auf Polygon
#: fast immer ein Deposit-Router oder eine Boersen-Hotwallet, denn jedes Konto
#: bekommt ohnehin eine eigene, aus einer Factory erzeugte Deposit-Adresse.
#: Ein erster Live-Lauf ueber die 50 groessten Wallets verkettete sonst 47 zu
#: einer "Entity", weil hunderte Router mit je vier Wallets knapp unter einem
#: absoluten Cap von 4 lagen und sich transitiv verbanden.
DEFAULT_MAX_SHARED_WALLETS = 2
#: Rueckwaerts-kompatibler Name; einige Aufrufer reichen ihn als Argument.
DEFAULT_DEGREE_CAP = DEFAULT_MAX_SHARED_WALLETS
#: Kandidaten, deren Finanzierungen naeher als dieses Fenster beieinander
#: liegen, bekommen mehr Konfidenz: "gleiche Hotwallet in engem Zeitfenster".
NARROW_WINDOW_HOURS = 48.0

KONFIDENZ = {
    TYP_DIRECT: 0.95,
    TYP_POSITION: 0.95,
    TYP_SHARED_FUNDER: 0.8,
    TYP_SHARED_WITHDRAWAL: 0.8,
    TYP_SHARED_HUB: 0.3,
}
KONFIDENZ_HUB_ENGES_FENSTER = 0.5

#: Ab so vielen harten Partnern gilt eine Wallet selbst als Infrastruktur
#: (Market-Maker, Relayer): ihre Kanten bleiben in der Liste, aber sie fuehren
#: keine Entity mehr zusammen. Ohne diese Schranke zieht ein einziger
#: Market-Maker, der mit 33 der 50 groessten Wallets Positionen tauscht, fast
#: den ganzen Scan-Satz zu einer "Entity" - hoher Grad ist dann ein Beleg fuer
#: das Gegenteil von gemeinsamer Kontrolle. Bei einer sauberen Zielmenge
#: (auffaellige, frische Wallets) greift die Schranke fast nie.
DEFAULT_HUB_HARD_DEGREE = 8

#: Wie viele Tx-Hashes eine Kante als Beleg mitfuehrt. Mehr waere fuer die
#: Payload nur Ballast; die vollstaendige Liste liefert jederzeit ein
#: erneuter Scan derselben Wallet.
TX_SAMPLE_LIMIT = 8

_SCHEMA = """
CREATE TABLE IF NOT EXISTS scans (
    wallet     TEXT PRIMARY KEY,
    scanned_at TEXT NOT NULL,
    transfers  INTEGER NOT NULL DEFAULT 0,
    complete   INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS funding_links (
    wallet       TEXT NOT NULL,
    counterparty TEXT NOT NULL,
    direction    TEXT NOT NULL,
    transfers    INTEGER NOT NULL DEFAULT 0,
    amount       REAL NOT NULL DEFAULT 0,
    first_ts     TEXT NOT NULL DEFAULT '',
    last_ts      TEXT NOT NULL DEFAULT '',
    tx_sample    TEXT NOT NULL DEFAULT '[]',
    PRIMARY KEY (wallet, counterparty, direction)
);
CREATE INDEX IF NOT EXISTS idx_funding_counterparty ON funding_links (counterparty, direction);
CREATE TABLE IF NOT EXISTS position_links (
    wallet       TEXT NOT NULL,
    counterparty TEXT NOT NULL,
    direction    TEXT NOT NULL,
    transfers    INTEGER NOT NULL DEFAULT 0,
    shares       REAL NOT NULL DEFAULT 0,
    first_ts     TEXT NOT NULL DEFAULT '',
    last_ts      TEXT NOT NULL DEFAULT '',
    tx_sample    TEXT NOT NULL DEFAULT '[]',
    PRIMARY KEY (wallet, counterparty, direction)
);
CREATE TABLE IF NOT EXISTS edges (
    wallet_a   TEXT NOT NULL,
    wallet_b   TEXT NOT NULL,
    typ        TEXT NOT NULL,
    stufe      INTEGER NOT NULL,
    konfidenz  REAL NOT NULL,
    evidenz    TEXT NOT NULL DEFAULT '{}',
    first_seen TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    PRIMARY KEY (wallet_a, wallet_b, typ)
);
CREATE TABLE IF NOT EXISTS wallet_entity (
    wallet    TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wallet_entity_entity ON wallet_entity (entity_id);
"""


def connect(path: Path | str = DEFAULT_GRAPH_PATH) -> sqlite3.Connection:
    """Verbindung mit Schema; WAL wie bei den anderen Stores des Repos."""

    ziel = Path(path)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(ziel), timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.executescript(_SCHEMA)
    return conn


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _iso(value: Any) -> str:
    """Zeitstempel beliebiger Herkunft als ISO-Text, oder leer."""

    if value is None:
        return ""
    stamp = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(stamp):
        return ""
    return stamp.isoformat()


def _tx_sample(values: Iterable[Any]) -> str:
    sample = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in sample:
            sample.append(text)
        if len(sample) >= TX_SAMPLE_LIMIT:
            break
    return json.dumps(sample)


def record_scan(
    conn: sqlite3.Connection,
    wallet: str,
    flows: pd.DataFrame,
    positions: pd.DataFrame | None = None,
    complete: bool = False,
    scanned_at: str | None = None,
) -> dict[str, int]:
    """Einen Wallet-Scan festhalten: externe Gegenparteien, aggregiert.

    ``flows`` ist der klassifizierte Frame aus ``ocf.classify_flows`` (plus
    ``timestamp``-Spalte, wo vorhanden). Nur ``classification == "external"``
    zaehlt: Protokoll-Adressen sind Handelsmechanik, und die ambivalenten
    Bridge-Adressen sind geteilte Infrastruktur, ueber die JEDER ein- und
    auszahlt. Eine "gemeinsame Gegenpartei", die ein Bridge-Kontrakt ist,
    verbindet niemanden, also darf sie gar nicht erst in die Tabelle.

    ``positions`` sind direkte ERC-1155-Transfers (Frame mit sender,
    recipient, shares, tx, timestamp): das haerteste Einzelsignal, denn
    normale Trades laufen ueber die Exchange-Kontrakte, nie von Wallet zu
    Wallet. Der Aufrufer hat Protokoll-Adressen bereits aussortiert.

    Ein erneuter Scan derselben Wallet ersetzt ihre Zeilen vollstaendig,
    statt zu addieren: die Quelle ist die vollstaendige (oder als gekappt
    markierte) Historie, nicht ein Inkrement.
    """

    ziel = str(wallet or "").strip().lower()
    if not ziel:
        raise ValueError("record_scan needs a wallet")
    conn.execute("DELETE FROM funding_links WHERE wallet = ?", (ziel,))
    conn.execute("DELETE FROM position_links WHERE wallet = ?", (ziel,))

    n_flows = 0
    if flows is not None and not flows.empty and "classification" in flows.columns:
        extern = flows[flows["classification"].astype(str).eq("external")].copy()
        if not extern.empty:
            extern["counterparty"] = extern["counterparty"].astype(str).str.lower()
            extern["direction"] = extern["direction"].astype(str)
            stempel = extern["timestamp"] if "timestamp" in extern.columns else pd.Series(pd.NaT, index=extern.index)
            extern["_ts"] = pd.to_datetime(stempel, utc=True, errors="coerce")
            rows = []
            for (gegen, richtung), gruppe in extern.groupby(["counterparty", "direction"]):
                rows.append((
                    ziel, gegen, richtung, int(len(gruppe)),
                    float(pd.to_numeric(gruppe["amount"], errors="coerce").fillna(0.0).sum()),
                    _iso(gruppe["_ts"].min()), _iso(gruppe["_ts"].max()),
                    _tx_sample(gruppe.get("tx", pd.Series(dtype=object))),
                ))
            conn.executemany(
                "INSERT INTO funding_links (wallet, counterparty, direction, transfers, amount,"
                " first_ts, last_ts, tx_sample) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            n_flows = int(len(extern))

    n_positions = 0
    if positions is not None and not positions.empty:
        pos = positions.copy()
        for spalte in ("sender", "recipient"):
            pos[spalte] = pos[spalte].astype(str).str.lower()
        pos = pos[(pos["sender"] == ziel) | (pos["recipient"] == ziel)]
        if not pos.empty:
            pos["direction"] = pos["recipient"].eq(ziel).map({True: "in", False: "out"})
            pos["counterparty"] = pos["sender"].where(pos["direction"].eq("in"), pos["recipient"])
            stempel = pos["timestamp"] if "timestamp" in pos.columns else pd.Series(pd.NaT, index=pos.index)
            pos["_ts"] = pd.to_datetime(stempel, utc=True, errors="coerce")
            rows = []
            for (gegen, richtung), gruppe in pos.groupby(["counterparty", "direction"]):
                rows.append((
                    ziel, gegen, richtung, int(len(gruppe)),
                    float(pd.to_numeric(gruppe.get("shares", 0.0), errors="coerce").fillna(0.0).sum()),
                    _iso(gruppe["_ts"].min()), _iso(gruppe["_ts"].max()),
                    _tx_sample(gruppe.get("tx", pd.Series(dtype=object))),
                ))
            conn.executemany(
                "INSERT INTO position_links (wallet, counterparty, direction, transfers, shares,"
                " first_ts, last_ts, tx_sample) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            n_positions = int(len(pos))

    conn.execute(
        "INSERT INTO scans (wallet, scanned_at, transfers, complete) VALUES (?, ?, ?, ?)"
        " ON CONFLICT(wallet) DO UPDATE SET scanned_at = excluded.scanned_at,"
        " transfers = excluded.transfers, complete = excluded.complete",
        (ziel, scanned_at or _now_iso(), n_flows + n_positions, 1 if complete else 0),
    )
    conn.commit()
    return {"external_transfers": n_flows, "position_transfers": n_positions}


def _merge_json(sample_a: str, sample_b: str) -> str:
    try:
        a = json.loads(sample_a or "[]")
        b = json.loads(sample_b or "[]")
    except json.JSONDecodeError:
        a, b = [], []
    return _tx_sample(list(a) + list(b))


def _min_iso(*values: str) -> str:
    kandidaten = [v for v in values if v]
    return min(kandidaten) if kandidaten else ""


def rebuild_edges(
    conn: sqlite3.Connection,
    degree_cap: int = DEFAULT_MAX_SHARED_WALLETS,
    narrow_window_hours: float = NARROW_WINDOW_HOURS,
) -> dict[str, int]:
    """Alle Kanten aus den Link-Tabellen neu ableiten. Idempotent.

    Die Kanten werden komplett verworfen und neu berechnet, nie fortge-
    schrieben: sie sind eine Ableitung aus ``funding_links`` und
    ``position_links``, und zwei Wahrheiten (die Tabellen und ein alter
    Kantenstand) koennen nur auseinanderlaufen. Ein Rebuild nach jedem Scan
    kostet Millisekunden, ein stiller Drift kostet das Vertrauen in jede
    Entity, die er erzeugt hat.
    """

    conn.execute("DELETE FROM edges")
    gescannt = {row[0] for row in conn.execute("SELECT wallet FROM scans")}
    jetzt = _now_iso()
    zaehler: dict[str, int] = {}

    def _add_edge(a: str, b: str, typ: str, stufe: int, konfidenz: float,
                  evidenz: Mapping[str, Any], first_seen: str) -> None:
        links, rechts = (a, b) if a < b else (b, a)
        conn.execute(
            "INSERT INTO edges (wallet_a, wallet_b, typ, stufe, konfidenz, evidenz, first_seen, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(wallet_a, wallet_b, typ) DO UPDATE SET"
            " stufe = excluded.stufe, konfidenz = excluded.konfidenz,"
            " evidenz = excluded.evidenz, first_seen = excluded.first_seen",
            (links, rechts, typ, stufe, float(konfidenz), json.dumps(dict(evidenz)), first_seen, jetzt),
        )
        zaehler[typ] = zaehler.get(typ, 0) + 1

    # Direkte Transfers: die Gegenpartei ist selbst eine gescannte Wallet.
    # Nur dann ist belegt, dass beide Seiten Polymarket-Konten sind; eine
    # unbekannte Adresse kann alles sein und bleibt eine Finanzierungsquelle.
    # Beide Perspektiven desselben Paars liefern dieselbe Kante; das Paar
    # wird trotzdem aus BEIDEN Richtungen versucht, weil bei einem gekappten
    # Scan auch nur eine Seite den Transfer gesehen haben kann.
    gesehen: set[tuple[str, str, str]] = set()
    for tabelle, typ in ((("funding_links", "amount"), TYP_DIRECT),
                         (("position_links", "shares"), TYP_POSITION)):
        name, betrag = tabelle
        for wallet, gegen, richtung, transfers, menge, first_ts, last_ts, tx in conn.execute(
            f"SELECT wallet, counterparty, direction, transfers, {betrag}, first_ts, last_ts, tx_sample"
            f" FROM {name}"
        ).fetchall():
            if gegen not in gescannt or gegen == wallet:
                continue
            paar = (min(wallet, gegen), max(wallet, gegen), typ)
            if paar in gesehen:
                continue
            gesehen.add(paar)
            _add_edge(wallet, gegen, typ, STUFE_HART, KONFIDENZ[typ], {
                "direction": richtung, "transfers": int(transfers),
                ("amount" if betrag == "amount" else "shares"): float(menge),
                "tx_sample": json.loads(tx or "[]"),
            }, _min_iso(first_ts, last_ts))

    # Gemeinsame externe Gegenparteien, je Richtung. Zwei Entscheidungen,
    # beide in den Belegen nachlesbar:
    #
    # 1. Die Zahl der bedienten Wallets trennt Stufe 1 von Stufe 2. Bis
    #    ``degree_cap`` (Standard 2) fuehrt der geteilte Fund hart zusammen -
    #    das ist der Operator-Fall, eine private Quelle speist genau zwei
    #    Konten. Darueber ist es auf Polygon fast immer ein Deposit-Router
    #    oder eine Boersen-Hotwallet und wird Kandidat. Der fruehere absolute
    #    Cap von 4 liess hunderte Router (je vier Wallets) knapp darunter
    #    durch, die sich transitiv zu einer 47-Wallet-"Entity" verbanden.
    #
    # 2. Ein Paar kann mehrere Gegenparteien teilen; die Belege werden je
    #    Paar GESAMMELT statt ueberschrieben. Drei geteilte Ziele sind ein
    #    staerkerer Befund als eines, und vorher ueberlebte nur das letzte.
    paare: dict[tuple[str, str, str], dict[str, Any]] = {}
    for richtung, typ in (("in", TYP_SHARED_FUNDER), ("out", TYP_SHARED_WITHDRAWAL)):
        gruppen: dict[str, list[tuple[str, int, float, str, str, str]]] = {}
        for wallet, gegen, transfers, amount, first_ts, last_ts, tx in conn.execute(
            "SELECT wallet, counterparty, transfers, amount, first_ts, last_ts, tx_sample"
            " FROM funding_links WHERE direction = ?", (richtung,)
        ).fetchall():
            if gegen in gescannt:
                continue  # schon als direkte Kante erfasst
            gruppen.setdefault(gegen, []).append((wallet, transfers, amount, first_ts, last_ts, tx))
        for gegen, mitglieder in gruppen.items():
            if len(mitglieder) < 2:
                continue
            hub = len(mitglieder) > int(degree_cap)
            for i in range(len(mitglieder)):
                for j in range(i + 1, len(mitglieder)):
                    a, b = mitglieder[i], mitglieder[j]
                    eng = _windows_close(a[3], b[3], narrow_window_hours)
                    if hub:
                        konfidenz = KONFIDENZ_HUB_ENGES_FENSTER if eng else KONFIDENZ[TYP_SHARED_HUB]
                        kanten_typ, stufe = TYP_SHARED_HUB, STUFE_KANDIDAT
                    else:
                        konfidenz = KONFIDENZ[typ]
                        kanten_typ, stufe = typ, STUFE_HART
                    links, rechts = (a[0], b[0]) if a[0] < b[0] else (b[0], a[0])
                    slot = paare.setdefault((links, rechts, kanten_typ), {
                        "stufe": stufe, "konfidenz": 0.0, "first_seen": "",
                        "shared_counterparties": [],
                    })
                    slot["konfidenz"] = max(slot["konfidenz"], konfidenz)
                    slot["first_seen"] = _min_iso(slot["first_seen"], a[3], b[3])
                    slot["shared_counterparties"].append({
                        "counterparty": gegen, "direction": richtung,
                        "counterparty_wallets": len(mitglieder),
                        "narrow_window": bool(eng),
                        "transfers": int(a[1]) + int(b[1]),
                        "amount": float(a[2]) + float(b[2]),
                        "tx_sample": json.loads(_merge_json(a[5], b[5])),
                    })
    for (links, rechts, kanten_typ), slot in paare.items():
        _add_edge(links, rechts, kanten_typ, slot["stufe"], slot["konfidenz"], {
            "shared_counterparties": slot["shared_counterparties"],
        }, slot["first_seen"])

    conn.commit()
    return zaehler


def _windows_close(first_a: str, first_b: str, hours: float) -> bool:
    """Liegen zwei Erst-Finanzierungen naeher als ``hours`` beieinander?"""

    a = pd.to_datetime(first_a or None, utc=True, errors="coerce")
    b = pd.to_datetime(first_b or None, utc=True, errors="coerce")
    if pd.isna(a) or pd.isna(b):
        return False
    return abs((a - b).total_seconds()) <= float(hours) * 3600.0


def hub_wallets(conn: sqlite3.Connection, hub_hard_degree: int = DEFAULT_HUB_HARD_DEGREE) -> set[str]:
    """Wallets mit so vielen harten Partnern, dass sie selbst Infrastruktur sind.

    Der harte Grad zaehlt ueber die Stufe-1-Kanten. Eine Wallet oberhalb der
    Schwelle ist ein Market-Maker- oder Relayer-Verdacht: sie hat mit sehr
    vielen Konten direkt Geld oder Positionen bewegt, und das ist kein
    Syndikat, sondern ihr Geschaeft.
    """

    grad: dict[str, int] = {}
    for a, b in conn.execute("SELECT wallet_a, wallet_b FROM edges WHERE stufe = ?", (STUFE_HART,)):
        grad[a] = grad.get(a, 0) + 1
        grad[b] = grad.get(b, 0) + 1
    return {wallet for wallet, n in grad.items() if n > int(hub_hard_degree)}


def assign_entities(conn: sqlite3.Connection,
                    hub_hard_degree: int = DEFAULT_HUB_HARD_DEGREE) -> dict[str, int]:
    """Union-Find ueber die Stufe-1-Kanten; Kandidaten und Hubs fuehren nie zusammen.

    Entity-Ids sind deterministisch (die lexikografisch kleinste Wallet der
    Komponente): zwei Rebuilds ueber denselben Daten ergeben dieselben Ids,
    und ein Diff zweier Staende zeigt echte Aenderungen statt neuer Nummern.
    Jede gescannte Wallet bekommt eine Entity, notfalls ihre eigene: "steht
    fuer sich" ist ein Befund, kein Fehlen.

    Eine Kante ueber eine Hub-Wallet (``hub_wallets``) fuehrt NICHT zusammen:
    die Kante bleibt in der Liste (der Transfer ist echt passiert), aber ein
    Market-Maker, der mit dem halben Scan-Satz handelt, darf ihn nicht zu
    einer Entity verschmelzen. Bei einer sauberen Zielmenge ist die Menge der
    Hubs leer und der Schritt ohne Wirkung.
    """

    hubs = hub_wallets(conn, hub_hard_degree)
    eltern: dict[str, str] = {}

    def _find(x: str) -> str:
        while eltern.get(x, x) != x:
            eltern[x] = eltern.get(eltern[x], eltern[x])
            x = eltern[x]
        return x

    def _union(a: str, b: str) -> None:
        wa, wb = _find(a), _find(b)
        if wa != wb:
            eltern[max(wa, wb)] = min(wa, wb)

    for wallet in (row[0] for row in conn.execute("SELECT wallet FROM scans")):
        eltern.setdefault(wallet, wallet)
    for a, b in conn.execute("SELECT wallet_a, wallet_b FROM edges WHERE stufe = ?", (STUFE_HART,)):
        eltern.setdefault(a, a)
        eltern.setdefault(b, b)
        if a in hubs or b in hubs:
            continue
        _union(a, b)

    conn.execute("DELETE FROM wallet_entity")
    conn.executemany(
        "INSERT INTO wallet_entity (wallet, entity_id) VALUES (?, ?)",
        [(wallet, f"entity:{_find(wallet)}") for wallet in eltern],
    )
    conn.commit()
    entities = conn.execute("SELECT COUNT(DISTINCT entity_id) FROM wallet_entity").fetchone()[0]
    verbunden = conn.execute(
        "SELECT COUNT(*) FROM (SELECT entity_id FROM wallet_entity GROUP BY entity_id HAVING COUNT(*) > 1)"
    ).fetchone()[0]
    return {"wallets": len(eltern), "entities": int(entities),
            "multi_wallet_entities": int(verbunden), "hub_wallets": len(hubs)}


def entity_view(conn: sqlite3.Connection, wallet: str) -> dict[str, Any]:
    """Die Entity einer Wallet mit allen Kanten und Belegen, als Payload-Dict.

    ``linked_wallets`` sind ueber Stufe-1-Belege verbundene Konten;
    ``candidates`` sind Stufe-2-Beobachtungen und sagen ausdruecklich nur
    "teilt eine Gegenpartei, die sich wie eine Boerse verhaelt". Eine nicht
    gescannte Wallet ist ``scanned: false`` und traegt keine leere Entity,
    denn "nicht untersucht" und "steht fuer sich" sind zwei verschiedene
    Antworten.
    """

    ziel = str(wallet or "").strip().lower()
    scan = conn.execute(
        "SELECT scanned_at, transfers, complete FROM scans WHERE wallet = ?", (ziel,)
    ).fetchone()
    if scan is None:
        return {"wallet": ziel, "scanned": False, "entity_id": None,
                "linked_wallets": [], "candidates": [], "edges": []}
    zeile = conn.execute(
        "SELECT entity_id FROM wallet_entity WHERE wallet = ?", (ziel,)).fetchone()
    entity_id = zeile[0] if zeile else f"entity:{ziel}"
    mitglieder = [row[0] for row in conn.execute(
        "SELECT wallet FROM wallet_entity WHERE entity_id = ? ORDER BY wallet", (entity_id,))]

    kanten = []
    for a, b, typ, stufe, konfidenz, evidenz, first_seen in conn.execute(
        "SELECT wallet_a, wallet_b, typ, stufe, konfidenz, evidenz, first_seen FROM edges"
        " WHERE wallet_a = ? OR wallet_b = ? ORDER BY stufe, typ", (ziel, ziel)
    ).fetchall():
        try:
            belege = json.loads(evidenz or "{}")
        except json.JSONDecodeError:
            belege = {}
        kanten.append({
            "wallet": b if a == ziel else a,
            "typ": typ, "stufe": int(stufe), "konfidenz": float(konfidenz),
            "first_seen": first_seen, "evidenz": belege,
        })

    return {
        "wallet": ziel,
        "scanned": True,
        "scanned_at": str(scan[0]),
        "scan_complete": bool(scan[2]),
        "entity_id": entity_id,
        "entity_wallets": mitglieder,
        "linked_wallets": [k for k in kanten if k["stufe"] == STUFE_HART],
        "candidates": [k for k in kanten if k["stufe"] == STUFE_KANDIDAT],
        "edges": kanten,
    }


def graph_overview(
    conn: sqlite3.Connection,
    max_entities: int = 25,
    max_candidates: int = 25,
) -> dict[str, Any]:
    """Der ganze Graph als eine Payload: die Produktflaeche liest nur das hier.

    Drei Bloecke, streng nach Evidenz getrennt: ``entities`` (nur die mit
    mehr als einer Wallet, samt ihrer harten Kanten und Belegen),
    ``candidates`` (Stufe-2-Beobachtungen, je GEGENPARTEI aggregiert: eine
    Adresse, die sechs Wallets beruehrt, ist EIN Befund, nicht fuenfzehn
    Paar-Zeilen) und ``scans`` (was ueberhaupt untersucht wurde, denn ohne
    den Nenner liest sich jede Liste als Gesamtbild). Kappungen stehen als
    ``*_capped`` in der Antwort, nicht im Kleingedruckten.
    """

    mitglieder: dict[str, list[str]] = {}
    for entity_id, wallet in conn.execute(
            "SELECT entity_id, wallet FROM wallet_entity ORDER BY entity_id, wallet"):
        mitglieder.setdefault(entity_id, []).append(wallet)
    mehrfach = sorted(
        ((eid, wallets) for eid, wallets in mitglieder.items() if len(wallets) > 1),
        key=lambda item: (-len(item[1]), item[0]))

    harte_kanten: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for a, b, typ, konfidenz, evidenz, first_seen in conn.execute(
            "SELECT wallet_a, wallet_b, typ, konfidenz, evidenz, first_seen FROM edges"
            " WHERE stufe = ? ORDER BY konfidenz DESC, typ", (STUFE_HART,)):
        try:
            belege = json.loads(evidenz or "{}")
        except json.JSONDecodeError:
            belege = {}
        harte_kanten.setdefault((a, b), []).append({
            "wallet_a": a, "wallet_b": b, "typ": typ,
            "konfidenz": float(konfidenz), "first_seen": first_seen,
            "evidenz": belege,
        })

    entities = []
    for entity_id, wallets in mehrfach[:max(0, int(max_entities))]:
        menge = set(wallets)
        kanten = [kante for (a, b), liste in harte_kanten.items()
                  if a in menge and b in menge for kante in liste]
        entities.append({"entity_id": entity_id, "wallets": wallets, "edges": kanten})

    # Kandidaten je Gegenpartei zusammenziehen. Die Kanten tragen die
    # Paar-Sicht; die Seite braucht die Adress-Sicht: wer beruehrt wie viele.
    spannen: dict[tuple[str, str], dict[str, Any]] = {}
    for a, b, evidenz in conn.execute(
            "SELECT wallet_a, wallet_b, evidenz FROM edges WHERE stufe = ?", (STUFE_KANDIDAT,)):
        try:
            belege = json.loads(evidenz or "{}")
        except json.JSONDecodeError:
            continue
        for teil in belege.get("shared_counterparties", []):
            key = (str(teil.get("counterparty", "")), str(teil.get("direction", "")))
            slot = spannen.setdefault(key, {"wallets": set(), "narrow_pairs": 0, "amount": 0.0})
            slot["wallets"].update([a, b])
            slot["narrow_pairs"] += 1 if teil.get("narrow_window") else 0
            slot["amount"] = max(slot["amount"], float(teil.get("amount") or 0.0))
    candidates = sorted(
        (
            {
                "counterparty": gegen, "direction": richtung,
                "wallets": sorted(slot["wallets"]),
                "wallet_count": len(slot["wallets"]),
                "narrow_pairs": int(slot["narrow_pairs"]),
            }
            for (gegen, richtung), slot in spannen.items()
        ),
        key=lambda item: (-item["wallet_count"], item["counterparty"]))

    scans = [
        {"wallet": wallet, "scanned_at": scanned_at, "complete": bool(complete)}
        for wallet, scanned_at, complete in conn.execute(
            "SELECT wallet, scanned_at, complete FROM scans ORDER BY scanned_at DESC")
    ]

    return {
        "stats": graph_stats(conn),
        "entities": entities,
        "entities_capped": len(mehrfach) > int(max_entities),
        "candidates": candidates[:max(0, int(max_candidates))],
        "candidates_capped": len(candidates) > int(max_candidates),
        "scans": scans,
    }


def graph_stats(conn: sqlite3.Connection) -> dict[str, Any]:
    """Bestand des Graphen fuer Log-Zeilen und Statusanzeigen."""

    stats = {
        "scans": conn.execute("SELECT COUNT(*) FROM scans").fetchone()[0],
        "edges": conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0],
        "hard_edges": conn.execute(
            "SELECT COUNT(*) FROM edges WHERE stufe = ?", (STUFE_HART,)).fetchone()[0],
        "candidate_edges": conn.execute(
            "SELECT COUNT(*) FROM edges WHERE stufe = ?", (STUFE_KANDIDAT,)).fetchone()[0],
        "entities": conn.execute(
            "SELECT COUNT(DISTINCT entity_id) FROM wallet_entity").fetchone()[0],
        "multi_wallet_entities": conn.execute(
            "SELECT COUNT(*) FROM (SELECT entity_id FROM wallet_entity"
            " GROUP BY entity_id HAVING COUNT(*) > 1)").fetchone()[0],
    }
    return {key: int(value) for key, value in stats.items()}
