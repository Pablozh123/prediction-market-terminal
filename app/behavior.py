"""Verhaltens-Layer des Wallet-Graphen (Phase 3): Fingerprints und Wash-Verdacht.

Stufe 3 der Evidenz-Leiter aus docs/HANDOFF-WALLET-GRAPH.md: Verhalten wird
angezeigt und fuehrt NIE zusammen. Eine Entity entsteht nur aus harten
On-Chain-Belegen (app/entity_graph.py); was hier herauskommt, sind Muster im
oeffentlichen Handelsband, und die Sprachregel dafuer ist "verhaelt sich wie",
nie "ist" (data/claims.yaml, screen_not_proof).

Zwei Detektoren, beide ueber dem Tape-Frame (Live-Band oder Store-Fenster):

- ``order_splitting_fingerprints``: viele kleine Orders derselben Wallet auf
  derselben Marktseite in kurzer Zeit. Das ist der dokumentierte
  Order-Splitting-Fingerprint aus dem Theo-Fall (US-Wahl 2024, bis zu 71
  Wetten pro Minute), mit dem sich Konten wiedererkennen liessen. Hier wird
  er je Wallet gemessen, nicht ueber Wallets hinweg gematcht.
- ``complementary_books``: zwei Wallets stehen wiederholt zeitnah auf
  entgegengesetzten Seiten desselben Markts. Das ist die im Band sichtbare
  Haelfte eines Wash-Verdachts. Die Columbia-Methode (gerichtete Zyklen bis
  fuenf Hops im Maker-Taker-Graphen) braucht die Gegenpartei je Fill, die
  das oeffentliche Band nicht traegt; das Paar-Muster ist die ehrliche
  Naeherung aus den verfuegbaren Daten und heisst deshalb auch nur Verdacht.

Bewusst KEIN neuer 0-100-Score: die Punktesummen-Lektion aus dem
Claims-Register (insider_score_unvalidated) gilt hier erst recht. Die
Detektoren liefern Fakten - Zaehlungen, Raten, Fenster, Belegzeiten - und
die Flaeche zeigt sie als solche.

Beide Detektoren kappen das Band auf die groessten Wallets (``max_wallets``),
weil Paarvergleiche quadratisch wachsen; ``focus_wallets`` werden immer
behalten, damit die Frage "was macht DIESE Entity" nie an der Kappung
scheitert. Die Kappung steht im Ergebnis (``attrs``), nicht im Kleingedruckten.
"""

from __future__ import annotations

from typing import Any, Iterable

import pandas as pd

#: Ein Burst: so viele Prints derselben Wallet auf derselben Marktseite
#: innerhalb von ``FINGERPRINT_WINDOW_S`` Sekunden. Acht in einer Minute ist
#: weit unter Theos 71, aber weit ueber Klick-Tempo; eine Stellschraube des
#: Screens, kein validierter Schwellwert.
FINGERPRINT_WINDOW_S = 60.0
FINGERPRINT_MIN_PRINTS = 8

#: Komplementaer-Fenster und Mindestzahl an Ereignissen, bevor ein Paar
#: ueberhaupt berichtet wird. Ein einzelnes Gegenueber ist Markt, kein Muster.
COMPLEMENTARY_WINDOW_MIN = 5.0
COMPLEMENTARY_MIN_EVENTS = 4

MAX_WALLETS = 300

FINGERPRINT_COLUMNS = ["wallet", "burst_prints", "burst_seconds", "burst_market",
                       "burst_outcome", "burst_side", "burst_start", "burst_notional",
                       "prints_total", "markets"]
COMPLEMENTARY_COLUMNS = ["wallet_a", "wallet_b", "events", "markets", "notional_a",
                         "notional_b", "first_seen", "last_seen", "top_market"]


def _signed_direction(side: Any, outcome: Any) -> int:
    """BUY YES / SELL NO druecken nach oben (+1), BUY NO / SELL YES nach unten (-1).

    Dieselbe Konvention wie ``net_directional`` im Risk-Screen: entscheidend
    ist die Wirkung auf das YES-Buch, nicht das Wort auf dem Ticket.
    """

    s = str(side or "").upper().strip()
    o = str(outcome or "").upper().strip()
    if s not in ("BUY", "SELL") or o not in ("YES", "NO"):
        return 0
    up = (s == "BUY") == (o == "YES")
    return 1 if up else -1


def _prepared(trades: pd.DataFrame, max_wallets: int,
              focus_wallets: Iterable[str] | None) -> pd.DataFrame:
    if trades is None or trades.empty:
        return pd.DataFrame()
    needed = {"wallet", "market_key", "time"}
    if not needed.issubset(trades.columns):
        return pd.DataFrame()
    df = trades.copy()
    df["wallet"] = df["wallet"].astype(str).str.lower().str.strip()
    df = df[df["wallet"].str.startswith("0x")]
    df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
    df = df.dropna(subset=["time"])
    df["notional"] = pd.to_numeric(df.get("notional"), errors="coerce").fillna(0.0)
    df["sign"] = [
        _signed_direction(side, outcome)
        for side, outcome in zip(df.get("side", ""), df.get("outcome", ""))
    ]
    if df.empty:
        return df
    fokus = {str(w).lower().strip() for w in (focus_wallets or []) if str(w).strip()}
    by_size = df.groupby("wallet")["notional"].sum().sort_values(ascending=False)
    keep = set(by_size.head(int(max_wallets)).index) | fokus
    return df[df["wallet"].isin(keep)].reset_index(drop=True)


def order_splitting_fingerprints(
    trades: pd.DataFrame,
    *,
    window_seconds: float = FINGERPRINT_WINDOW_S,
    min_prints: int = FINGERPRINT_MIN_PRINTS,
    max_wallets: int = MAX_WALLETS,
    focus_wallets: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Wallets, die eine Marktseite in viele schnelle Prints zerlegen.

    Je Wallet der dichteste Burst: die maximale Zahl Prints derselben
    (Markt, Outcome, Seite) innerhalb von ``window_seconds``, samt Beginn,
    Spanne und Notional des Bursts. Berichtet wird nur, was ``min_prints``
    erreicht; alles darunter ist normales Nachlegen.
    """

    df = _prepared(trades, max_wallets, focus_wallets)
    if df.empty:
        return pd.DataFrame(columns=FINGERPRINT_COLUMNS)
    fenster = pd.Timedelta(seconds=float(window_seconds))
    rows: list[dict[str, Any]] = []
    for wallet, je_wallet in df.groupby("wallet"):
        best: dict[str, Any] | None = None
        for (markt, outcome, seite), gruppe in je_wallet.groupby(
                [je_wallet["market_key"].astype(str),
                 je_wallet.get("outcome", "").astype(str).str.upper(),
                 je_wallet.get("side", "").astype(str).str.upper()]):
            zeiten = gruppe.sort_values("time")
            stamps = list(zeiten["time"])
            betraege = list(zeiten["notional"])
            links = 0
            for rechts in range(len(stamps)):
                while stamps[rechts] - stamps[links] > fenster:
                    links += 1
                dicht = rechts - links + 1
                if best is None or dicht > best["burst_prints"]:
                    titel = zeiten.get("title")
                    best = {
                        "burst_prints": dicht,
                        "burst_seconds": float((stamps[rechts] - stamps[links]).total_seconds()),
                        "burst_market": (str(titel.iloc[0]) if titel is not None and len(titel) else str(markt)),
                        "burst_outcome": str(outcome),
                        "burst_side": str(seite),
                        "burst_start": stamps[links].isoformat(),
                        "burst_notional": float(sum(betraege[links:rechts + 1])),
                    }
        if best is not None and best["burst_prints"] >= int(min_prints):
            rows.append({
                "wallet": wallet, **best,
                "prints_total": int(len(je_wallet)),
                "markets": int(je_wallet["market_key"].astype(str).nunique()),
            })
    if not rows:
        return pd.DataFrame(columns=FINGERPRINT_COLUMNS)
    return (pd.DataFrame(rows, columns=FINGERPRINT_COLUMNS)
            .sort_values("burst_prints", ascending=False).reset_index(drop=True))


def complementary_books(
    trades: pd.DataFrame,
    *,
    window_minutes: float = COMPLEMENTARY_WINDOW_MIN,
    min_events: int = COMPLEMENTARY_MIN_EVENTS,
    max_wallets: int = MAX_WALLETS,
    focus_wallets: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Paare, die wiederholt zeitnah gegeneinander im selben Markt stehen.

    Ein Ereignis: zwei verschiedene Wallets mit entgegengesetzter Wirkung auf
    dasselbe Buch (``_signed_direction``) innerhalb von ``window_minutes``.
    Das Notional wird je Seite ueber die tatsaechlich beteiligten Prints
    summiert (jeder Print einmal, wie im Co-Trading-Netz): ein Burst gegen
    einen Einzelprint zaehlt sonst denselben Dollar zigfach.
    """

    df = _prepared(trades, max_wallets, focus_wallets)
    if df.empty:
        return pd.DataFrame(columns=COMPLEMENTARY_COLUMNS)
    df = df[df["sign"] != 0]
    if df.empty:
        return pd.DataFrame(columns=COMPLEMENTARY_COLUMNS)
    fenster = pd.Timedelta(minutes=float(window_minutes))

    ereignisse: dict[tuple[str, str], int] = {}
    maerkte: dict[tuple[str, str], set[str]] = {}
    beteiligt: dict[tuple[str, str], dict[str, set[tuple[str, int]]]] = {}
    zeiten_paar: dict[tuple[str, str], list[pd.Timestamp]] = {}
    markt_zaehler: dict[tuple[str, str], dict[str, int]] = {}
    betrag: dict[tuple[str, int], float] = {}
    titel_je_markt: dict[str, str] = {}

    for markt, gruppe in df.groupby(df["market_key"].astype(str)):
        if not markt:
            continue
        titel = gruppe.get("title")
        titel_je_markt[markt] = str(titel.iloc[0]) if titel is not None and len(titel) else markt
        records = gruppe.sort_values("time").reset_index(drop=True)
        stamps = list(records["time"])
        wallets = list(records["wallet"])
        signs = list(records["sign"])
        notionals = list(records["notional"])
        links = 0
        for rechts in range(len(records)):
            while stamps[rechts] - stamps[links] > fenster:
                links += 1
            for mitte in range(links, rechts):
                if wallets[mitte] == wallets[rechts] or signs[mitte] == signs[rechts]:
                    continue
                a, b = sorted((wallets[mitte], wallets[rechts]))
                key = (a, b)
                ereignisse[key] = ereignisse.get(key, 0) + 1
                maerkte.setdefault(key, set()).add(markt)
                markt_zaehler.setdefault(key, {})[markt] = markt_zaehler.get(key, {}).get(markt, 0) + 1
                zeiten_paar.setdefault(key, []).append(stamps[rechts])
                seiten = beteiligt.setdefault(key, {a: set(), b: set()})
                for index in (mitte, rechts):
                    seiten[wallets[index]].add((markt, index))
                    betrag[(markt, index)] = float(notionals[index])

    rows: list[dict[str, Any]] = []
    for key, anzahl in ereignisse.items():
        if anzahl < int(min_events):
            continue
        a, b = key
        stamps = sorted(zeiten_paar[key])
        top_markt = max(markt_zaehler[key].items(), key=lambda item: item[1])[0]
        rows.append({
            "wallet_a": a, "wallet_b": b,
            "events": int(anzahl),
            "markets": int(len(maerkte[key])),
            "notional_a": float(sum(betrag[p] for p in beteiligt[key][a])),
            "notional_b": float(sum(betrag[p] for p in beteiligt[key][b])),
            "first_seen": stamps[0].isoformat(),
            "last_seen": stamps[-1].isoformat(),
            "top_market": titel_je_markt.get(top_markt, top_markt),
        })
    if not rows:
        return pd.DataFrame(columns=COMPLEMENTARY_COLUMNS)
    return (pd.DataFrame(rows, columns=COMPLEMENTARY_COLUMNS)
            .sort_values("events", ascending=False).reset_index(drop=True))


def behavior_report(
    trades: pd.DataFrame,
    wallets: Iterable[str] | None = None,
    *,
    max_wallets: int = MAX_WALLETS,
) -> dict[str, Any]:
    """Beide Detektoren als Payload-Dict, optional auf eine Wallet-Menge gefiltert.

    ``wallets`` filtert das ERGEBNIS, nicht das Band: der Wash-Partner einer
    Entity-Wallet steht oft ausserhalb der Entity, und ein vorab gefiltertes
    Band koennte ihn gar nicht erst sehen. Die Menge wird zugleich als
    ``focus_wallets`` durch die Kappung gereicht.
    """

    fokus = [str(w).lower().strip() for w in (wallets or []) if str(w).strip()]
    fingerprints = order_splitting_fingerprints(trades, max_wallets=max_wallets, focus_wallets=fokus)
    paare = complementary_books(trades, max_wallets=max_wallets, focus_wallets=fokus)
    if fokus:
        menge = set(fokus)
        if not fingerprints.empty:
            fingerprints = fingerprints[fingerprints["wallet"].isin(menge)]
        if not paare.empty:
            paare = paare[paare["wallet_a"].isin(menge) | paare["wallet_b"].isin(menge)]
    return {
        "fingerprints": fingerprints.to_dict(orient="records"),
        "complementary_pairs": paare.to_dict(orient="records"),
        "params": {
            "fingerprint_window_s": FINGERPRINT_WINDOW_S,
            "fingerprint_min_prints": FINGERPRINT_MIN_PRINTS,
            "complementary_window_min": COMPLEMENTARY_WINDOW_MIN,
            "complementary_min_events": COMPLEMENTARY_MIN_EVENTS,
            "max_wallets": int(max_wallets),
        },
        "tape_rows": int(0 if trades is None else len(trades)),
    }
