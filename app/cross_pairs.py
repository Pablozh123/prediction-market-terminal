"""Cross-Venue-Paarung ueber die volle Marktbreite (Streamlit-frei, netzfrei).

``md.cross_venue_candidates`` kappt beide Seiten auf die Top-80 nach Volumen —
richtig fuer die interaktive Seite, aber zu eng, wenn sich die Top-Listen der
Venues kaum ueberlappen. Dieses Modul vergleicht die vollen Frames ueber einen
invertierten Token-Index (nur Paare mit mindestens zwei gemeinsamen Tokens
werden gescored) und benutzt dieselbe Aehnlichkeitsformel wie ``md``.

Bevor eine Zahl entsteht, wird gefragt, ob die beiden Seiten ueberhaupt
dasselbe fragen: Richtung der Frage, Schwelle, Fragetyp, Aufloesungstermin
(``pair_verdict``). Faellt dort etwas auf, bleibt die Spanne leer. Eine
umgekehrte Frage teilt fast jedes Wort mit ihrer Vorlage, und die Spanne
darueber ist keine Gelegenheit, sondern dieselbe Wette zweimal.

Auch was nicht auffaellt, bleibt eine Titel-Heuristik: Paare sind NICHT
verifiziert, identisch aufzuloesen — dieselbe Frage kann auf beiden Venues
verschieden settlen. Der Abnehmer muss diesen Vorbehalt mit ausliefern.

Neben der Luecke zwischen den beiden Mittelkursen liefert das Modul, was von
ihr uebrig bleibt, wenn man sie tatsaechlich nimmt. Das sind drei
verschiedene Zahlen, und nur die letzte ist eine Aussage ueber Geld:

* ``gap`` ist die Differenz der Mittelkurse. Handelbar ist sie nicht: gekauft
  wird zum Brief, verkauft zum Geld.
* ``gross_edge_cents`` ist die ausfuehrbare Spanne. Wer YES auf der billigen
  Venue zum Brief kauft und NO auf der teuren (also YES verkauft zum Geld),
  zahlt zusammen ``ask + (1 - bid)`` und bekommt bei Aufloesung 1.00, also
  bleibt ``bid_teuer - ask_billig``. Das ist immer hoechstens die
  Mittelkurs-Luecke und meist deutlich weniger.
* ``net_edge_cents`` zieht beide Gebuehrenkurven ab (``app/venue_fees.py``).
  Erst diese Zahl darf als Vorteil gelesen werden.

Ohne beidseitige Quote auf beiden Venues bleiben die letzten beiden ``None``.
Unbekannt ist nicht null.

Das Volumen der beiden Seiten steht in zwei verschiedenen Einheiten und
deshalb in zwei verschieden benannten Spalten: ``polymarket_volume_usd`` sind
Dollar, ``kalshi_volume_contracts`` sind Kontrakte. Eine Summe ueber beide
gibt es nicht (Beleg und Begruendung in ``app/venue_units.py``).
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from app import venue_fees as vf
from src import prediction_markets as md

MIN_SHARED_TOKENS = 2

#: Clip, auf dem die Gebuehrenkurven ausgewertet werden. Beide Venues rechnen
#: die Gebuehr auf die Varianz des Ausgangs, Kalshi rundet die Order auf den
#: naechsten Cent auf; auf 100 Stueck faellt diese Rundung nicht ins Gewicht.
FEE_CLIP_SHARES = 100.0


# --- Fragen die beiden Seiten ueberhaupt dasselbe? ---------------------------
#
# Die Aehnlichkeit zweier Titel misst gemeinsame Woerter. Sie ist blind fuer
# genau die Woerter, die die Frage tragen: "above" gegen "below" teilen jedes
# andere Wort, und der Matcher gibt ihnen 0.78. Wer dann die Spanne rechnet,
# bekommt eine Zahl, die wie eine Gelegenheit aussieht und keine ist. Der
# Korb "YES hier, NO dort" zahlt nur dann genau 1.00 je Paar, wenn beide
# Seiten dieselbe Frage in dieselbe Richtung stellen. Bei einer Umkehrung
# zahlt er 2.00 oder 0.00, ist also kein Korb, sondern dieselbe Wette zweimal.
#
# Was hier geprueft wird, ist deshalb kein Feinschliff der Aehnlichkeit,
# sondern die Vorfrage: Richtung, Schwelle, Fragetyp, Aufloesungstermin. Was
# auffaellt, bekommt keine Zahl. Was nicht auffaellt, ist damit nicht
# geprueft (die Regeltexte entscheiden das, siehe src/resolution_rules.py) und
# heisst deshalb ``unverified`` und nicht etwa "geprueft".

#: Nichts spricht dagegen, dass beide Seiten dieselbe Frage stellen. Das ist
#: die beste Stufe, die eine Titelpaarung erreichen kann.
PAIR_UNVERIFIED = "unverified"
#: Die beiden Seiten fragen nachweislich in entgegengesetzte Richtungen.
PAIR_OPPOSED = "opposed"
#: Sie fragen nachweislich verschiedene Dinge: andere Schwelle, anderer
#: Fragetyp, anderer Aufloesungstermin.
PAIR_DIFFERENT = "different_question"

_WORD_RE = re.compile(r"[a-z0-9]+")

#: Verneinung auf genau einer Seite. Bewusst nicht ueber ``md._tokens``: der
#: Matcher wirft "no" als Stoppwort weg und "not" ueberlebt nur zufaellig,
#: weil es drei Zeichen hat. Die Ausnahme hinter ``no`` faengt "No. 1 seed".
_NEGATION_RE = re.compile(
    r"\b(?:not|never|without|neither|nor|unable|fails?\s+to)\b|\bno\b(?!\.?\s*\d)",
    re.IGNORECASE)

#: Wortpaare, die dieselbe Groesse in entgegengesetzte Richtungen fragen.
#: Eng gehalten: ein falscher Treffer nimmt ein gutes Paar von der Seite, das
#: ist der billigere Fehler, aber umsonst soll er auch nicht passieren.
DIRECTION_GROUPS: tuple[tuple[str, frozenset[str], frozenset[str]], ...] = (
    ("threshold",
     frozenset({"above", "over", "exceed", "exceeds", "exceeding", "higher", "greater"}),
     frozenset({"below", "under", "beneath", "lower", "fewer"})),
    ("move",
     frozenset({"rise", "rises", "rising", "increase", "increases", "increasing",
                "gain", "gains", "up"}),
     frozenset({"fall", "falls", "falling", "decline", "declines", "decrease",
                "decreases", "drop", "drops", "dip", "dips", "down"})),
    ("outcome",
     frozenset({"win", "wins", "winner", "winning", "won"}),
     frozenset({"lose", "loses", "loser", "losing", "lost"})),
    ("decision",
     frozenset({"approve", "approves", "approved", "pass", "passes", "passed",
                "confirm", "confirms", "confirmed"}),
     frozenset({"reject", "rejects", "rejected", "fail", "fails", "failed",
                "block", "blocks", "blocked", "veto", "vetoes", "vetoed"})),
)

#: Dieselbe Umkehrung als Wendung. "at least" und "at most" bestehen nur aus
#: Woertern, die jeder Tokenizer als Fuellwoerter wegwirft, und genau so
#: schreibt Kalshi seine Schwellenmaerkte.
DIRECTION_PHRASES: tuple[tuple[str, str], ...] = (
    ("at least", "at most"),
    ("or more", "or less"),
    ("or more", "or fewer"),
)

#: Was eine Frage eigentlich fragt, unabhaengig von der Formulierung. Die
#: Pruefung laeuft ueber diese Gruppen statt ueber Einzelwoerter, weil
#: "gewinnt die Nominierung" und "ist der Nominierte" dieselbe Frage sind,
#: "gewinnt die Nominierung" und "tritt an" dagegen nicht. Herkunft und
#: Beleg: die beiden groessten Scheinkanten des ersten Livelaufs in
#: src/cross_venue_gaps.py, 79 und 64 Cent, waren genau diese zwei Faelle.
INTENT_WORDS: dict[str, frozenset[str]] = {
    "outcome": frozenset({"win", "wins", "won", "winner", "winning", "nominee",
                          "nomination", "nominated", "host", "hosts", "hosting",
                          "champion", "elected"}),
    "participation": frozenset({"run", "runs", "running", "ran", "candidate",
                                "enter", "announce", "declare"}),
    "margin": frozenset({"margin", "percent", "percentage", "points", "spread"}),
    "exit": frozenset({"concede", "withdraw", "resign", "drop", "suspend", "quit"}),
}

#: Spannen-Muster ("6-9%") verraten einen Margen-Markt auch ohne das Wort.
RANGE_PATTERN = re.compile(r"\d+\s*[-–]\s*\d+\s*%")

#: Schwellen, also Geldbetraege und Prozentwerte. Nur was ein $ oder ein %
#: traegt, zaehlt: eine nackte Zahl im Titel ist meistens ein Datum, und ein
#: Vergleich ueber Datumszahlen wuerde jedes zweite echte Paar wegwerfen.
_STRIKE_RE = re.compile(
    r"\$\s*(\d[\d,]*(?:\.\d+)?)\s*(k|m|mn|bn|b)?\b|(\d[\d,]*(?:\.\d+)?)\s*%")
_STRIKE_FACTORS = {"k": 1e3, "m": 1e6, "mn": 1e6, "b": 1e9, "bn": 1e9}

#: Wie weit die beiden Aufloesungstermine auseinanderliegen duerfen. Dieselbe
#: Frage schliesst auf beiden Venues selten auf die Minute gleich (Kalshi
#: nennt close_time, Polymarket endDate); eine Woche deckt diese Differenz.
#: Was darueber liegt, ist ein anderer Termin und damit eine andere Frage:
#: die September- und die Dezember-Sitzung der Fed teilen jedes Wort ausser
#: dem Monat, und der Korb ueber diese beiden ist nicht abgesichert.
MAX_RESOLUTION_GAP_DAYS = 7.0


def _words(title: str) -> set[str]:
    """Alle Woerter eines Titels, klein und ungefiltert.

    Bewusst nicht ``md._tokens``: der Matcher entfernt Stoppwoerter und alles
    unter drei Zeichen und wirft damit genau die Woerter weg, an denen die
    Richtung einer Frage haengt.
    """

    return set(_WORD_RE.findall(str(title or "").lower()))


def strikes(title: str) -> set[tuple[str, float]]:
    """Die Schwellen eines Titels als (Einheit, Wert), normiert.

    ``$68,200`` und ``$68.2k`` sind dieselbe Schwelle, ``$68,200`` und
    ``$120,000`` sind zwei verschiedene Fragen. Kalshi haengt die Schwelle
    an den Titel (``kalshi_display_title``), Polymarket schreibt sie hinein,
    also stehen sie auf beiden Seiten im Text.
    """

    out: set[tuple[str, float]] = set()
    for money, unit, percent in _STRIKE_RE.findall(str(title or "")):
        if money:
            faktor = _STRIKE_FACTORS.get((unit or "").lower(), 1.0)
            out.add(("usd", round(float(money.replace(",", "")) * faktor, 4)))
        elif percent:
            out.add(("pct", round(float(percent.replace(",", "")), 4)))
    return out


def intents(title: str) -> set[str]:
    """Welche Fragetypen ein Titel ausdrueckt."""

    tokens = _words(title)
    found = {name for name, words in INTENT_WORDS.items() if tokens & words}
    if RANGE_PATTERN.search(str(title or "")):
        found.add("margin")
    return found


def opposed_reasons(left: str, right: str) -> list[str]:
    """Warum die beiden Titel in entgegengesetzte Richtungen fragen.

    Gefordert ist ein Gegensatz, keine blosse Anwesenheit: die eine Seite
    traegt ein Wort der einen Richtung, die andere eines der anderen, und
    keine traegt beides. Sonst waere "Who wins the race?" gegen "Race
    winner?" ein Gegensatz, und das ist dieselbe Frage in zwei Wortformen.
    """

    links, rechts = _words(left), _words(right)
    reasons: list[str] = []
    for name, vorwaerts, rueckwaerts in DIRECTION_GROUPS:
        a_vor, a_zurueck = links & vorwaerts, links & rueckwaerts
        b_vor, b_zurueck = rechts & vorwaerts, rechts & rueckwaerts
        # Eine Seite, die beide Richtungen nennt ("above 4 or below 2"),
        # entscheidet nichts.
        if (a_vor and a_zurueck) or (b_vor and b_zurueck):
            continue
        for eine, andere in ((a_vor, b_zurueck), (a_zurueck, b_vor)):
            if eine and andere:
                reasons.append(
                    f"opposite direction ({name}): "
                    f"{', '.join(sorted(eine))} against {', '.join(sorted(andere))}")
                break
    links_text, rechts_text = str(left or "").lower(), str(right or "").lower()
    for vorwaerts_phrase, rueckwaerts_phrase in DIRECTION_PHRASES:
        a = (vorwaerts_phrase in links_text, rueckwaerts_phrase in links_text)
        b = (vorwaerts_phrase in rechts_text, rueckwaerts_phrase in rechts_text)
        if (a[0] and b[1] and not a[1] and not b[0]) or (a[1] and b[0] and not a[0] and not b[1]):
            reasons.append(
                f"opposite direction: '{vorwaerts_phrase}' against '{rueckwaerts_phrase}'")
    if bool(_NEGATION_RE.search(str(left or ""))) != bool(_NEGATION_RE.search(str(right or ""))):
        reasons.append("negation on one side only")
    return reasons


def question_reasons(left: str, right: str) -> list[str]:
    """Warum die beiden Titel verschiedene Dinge fragen, Richtung beiseite."""

    reasons: list[str] = []
    links, rechts = intents(left), intents(right)
    if links ^ rechts:
        reasons.append(
            "different question types: " + ", ".join(sorted(links) or ["none"])
            + " against " + ", ".join(sorted(rechts) or ["none"]))
    links_strikes, rechts_strikes = strikes(left), strikes(right)
    if links_strikes and rechts_strikes and links_strikes != rechts_strikes:
        def _label(werte: set[tuple[str, float]]) -> str:
            return ", ".join(f"{'$' if einheit == 'usd' else ''}{wert:g}"
                             f"{'%' if einheit == 'pct' else ''}"
                             for einheit, wert in sorted(werte))
        reasons.append(f"different thresholds: {_label(links_strikes)} "
                       f"against {_label(rechts_strikes)}")
    return reasons


def suspect_reasons(left: str, right: str) -> list[str]:
    """Alles, was gegen "dieselbe Frage" spricht, aus den beiden Titeln.

    Eine Definition fuer beide Abnehmer: die Web-Paarung hier und die
    Studie in ``src/cross_venue_gaps.py``. Eine leere Liste heisst nicht
    geprueft, sondern nur nicht aufgefallen.
    """

    return opposed_reasons(left, right) + question_reasons(left, right)


def _timestamp(value: Any) -> pd.Timestamp | None:
    stamp = pd.to_datetime(value, utc=True, errors="coerce")
    if stamp is None or stamp is pd.NaT or pd.isna(stamp):
        return None
    return stamp


def resolution_gap_days(left: Any, right: Any) -> float | None:
    """Abstand der beiden Aufloesungstermine in Tagen, None wenn unbekannt."""

    a, b = _timestamp(left), _timestamp(right)
    if a is None or b is None:
        return None
    return round(abs((a - b).total_seconds()) / 86400.0, 3)


def pair_verdict(pm_row: Any, ks_row: Any,
                 max_resolution_gap_days: float = MAX_RESOLUTION_GAP_DAYS) -> dict[str, Any]:
    """Urteil ueber ein Paar: ``unverified``, ``opposed`` oder ``different_question``.

    Erwartet zwei Mappings mit ``title`` und, wenn vorhanden, ``end`` bzw.
    ``end_time``. Fehlt ein Termin, wird der Terminvergleich uebersprungen
    statt geraten: unbekannt ist kein Treffer und kein Freispruch.
    """

    pm_row = pm_row if isinstance(pm_row, dict) else dict(pm_row or {})
    ks_row = ks_row if isinstance(ks_row, dict) else dict(ks_row or {})
    pm_title = str(pm_row.get("title") or "")
    ks_title = str(ks_row.get("title") or "")

    gegensatz = opposed_reasons(pm_title, ks_title)
    andere = question_reasons(pm_title, ks_title)
    abstand = resolution_gap_days(
        pm_row.get("end", pm_row.get("end_time")),
        ks_row.get("end", ks_row.get("end_time")))
    if abstand is not None and abstand > float(max_resolution_gap_days):
        andere.append(f"resolution dates {abstand:g} days apart")

    if gegensatz:
        verdict = PAIR_OPPOSED
    elif andere:
        verdict = PAIR_DIFFERENT
    else:
        verdict = PAIR_UNVERIFIED
    return {
        "verdict": verdict,
        "reasons": gegensatz + andere,
        "resolution_gap_days": abstand,
    }


def _series(frame: pd.DataFrame, name: str) -> list[Any]:
    if name in frame.columns:
        return list(frame[name])
    return [None] * len(frame)


def _quote(value: Any) -> float | None:
    """Eine Quote in (0, 1), oder None wenn keine da ist.

    Beide Venues schreiben 0.0 in best_bid/best_ask, wenn die Seite leer ist.
    Eine leere Seite ist keine Quote zu null Cent.
    """

    try:
        preis = float(value)
    except (TypeError, ValueError):
        return None
    if preis != preis or not (0.0 < preis < 1.0):
        return None
    return preis


def _rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
    titles = _series(frame, "title")
    rows = []
    for title, key, ticker, yes, bid, ask, vol24, vol, category, url, end, token in zip(
        titles,
        _series(frame, "market_key"),
        _series(frame, "ticker"),
        _series(frame, "yes_price"),
        _series(frame, "best_bid"),
        _series(frame, "best_ask"),
        _series(frame, "volume_24h"),
        _series(frame, "activity_volume"),
        _series(frame, "category"),
        _series(frame, "url"),
        _series(frame, "end_time"),
        _series(frame, "yes_token_id"),
    ):
        title = str(title or "").strip()
        try:
            yes_f = float(yes)
        except (TypeError, ValueError):
            continue
        if not title or not (0.0 < yes_f < 1.0):
            continue
        try:
            volume = float(vol24) if vol24 == vol24 and vol24 is not None else float(vol or 0.0)
        except (TypeError, ValueError):
            volume = 0.0
        rows.append({
            "title": title,
            "tokens": md._tokens(title),
            "market_key": str(key or ""),
            "ticker": str(ticker or ""),
            "yes": yes_f,
            "bid": _quote(bid),
            "ask": _quote(ask),
            "volume": volume,
            "category": str(category or ""),
            "url": str(url or ""),
            # Aufloesungstermin und Token-Id gehen mit, weil sie die beiden
            # Fragen entscheiden, die ein Titel nicht beantwortet: loesen die
            # zwei Maerkte zum selben Zeitpunkt auf, und wie tief ist das Buch
            # hinter der Quote.
            "end": end,
            "yes_token_id": str(token or ""),
            # Tiefe an der Quote, falls sie jemand nachgeschlagen hat.
            # ``None`` heisst nicht nachgeschlagen, nicht "keine Tiefe".
            "bid_size": None,
            "ask_size": None,
        })
    return rows


#: Was eine Zeile ohne rechenbare Spanne traegt. ``depth_checked`` ist dabei
#: die einzige Angabe, die auch dann etwas bedeutet: sie sagt, ob die Groesse
#: nachgeschlagen wurde oder eine Annahme ist.
EMPTY_EDGE: dict[str, Any] = {
    "gross_edge_cents": None, "fee_band_cents": None, "net_edge_cents": None,
    "edge_direction": "", "size_shares": None, "depth_checked": False,
}


def _depth(value: Any) -> float:
    """Tiefe an der Quote; unbekannt heisst unbeschraenkt, nicht null."""

    if value is None:
        return float("inf")
    try:
        size = float(value)
    except (TypeError, ValueError):
        return float("inf")
    return size if size == size else float("inf")


def basket_edge(pm_row: dict[str, Any], ks_row: dict[str, Any],
                shares: float = FEE_CLIP_SHARES) -> dict[str, Any]:
    """Die ausfuehrbare Spanne des Paares, brutto und nach beiden Gebuehren.

    Geprueft werden beide Richtungen: YES auf Polymarket gegen NO auf Kalshi
    und umgekehrt. Wer YES zum Brief kauft und auf der anderen Venue NO zum
    Brief (also ``1 - bid``), zahlt zusammen ``ask + 1 - bid`` und bekommt bei
    Aufloesung genau 1.00 je Paar. Brutto bleibt also ``bid - ask`` ueber die
    Venues hinweg. Beide Vorzeichen sind erlaubt: eine negative Spanne ist die
    Antwort "nicht handelbar", keine fehlende Antwort.

    Ohne beidseitige Quote auf beiden Venues gibt es nichts zu rechnen, dann
    bleibt alles ``None``.

    ``bid_size``/``ask_size`` sind die Stueckzahlen an der Quote. Fehlen sie,
    rechnet die Funktion auf ``shares`` Stueck und meldet
    ``depth_checked=False``: die Spanne gilt dann nur fuer die Spitze des
    Buchs, und wie viel davon dort liegt, hat niemand nachgesehen. Liegen sie
    vor, ist ``size_shares`` die Groesse, fuer die die Zahl wirklich gilt.
    """

    richtungen = (
        ("buy Polymarket, sell Kalshi",
         ("polymarket", pm_row.get("ask"), pm_row.get("ask_size"), pm_row.get("category")),
         ("kalshi", ks_row.get("bid"), ks_row.get("bid_size"), ks_row.get("category"))),
        ("buy Kalshi, sell Polymarket",
         ("kalshi", ks_row.get("ask"), ks_row.get("ask_size"), ks_row.get("category")),
         ("polymarket", pm_row.get("bid"), pm_row.get("bid_size"), pm_row.get("category"))),
    )
    bestes: dict[str, Any] | None = None
    for name, kaufen, verkaufen in richtungen:
        kauf_venue, ask, ask_size, kauf_cat = kaufen
        verkauf_venue, bid, bid_size, verkauf_cat = verkaufen
        if ask is None or bid is None:
            continue
        tiefe_kauf, tiefe_verkauf = _depth(ask_size), _depth(bid_size)
        # Nachgeschlagen und nichts da ist keine Gelegenheit zu null Stueck,
        # sondern gar keine. Ohne diesen Abbruch faellt die Gebuehr je Stueck
        # auf null (Division durch die Groesse), und die Zeile sieht
        # anschliessend besser aus als jede Zeile mit echtem Buch.
        if tiefe_kauf <= 0 or tiefe_verkauf <= 0:
            continue
        # Das zweite Bein ist NO zum Preis 1 - bid; die Gebuehrenkurve ist in
        # p symmetrisch, der Preis des Beins gehoert trotzdem hier hin.
        economics = vf.basket_economics(
            vf.BasketLeg(kauf_venue, ask, tiefe_kauf, kauf_cat),
            vf.BasketLeg(verkauf_venue, 1.0 - bid, tiefe_verkauf, verkauf_cat),
            shares=shares,
        )
        kandidat = {
            "gross_edge_cents": round(economics["gross_edge_cents"], 4),
            "fee_band_cents": round(economics["breakeven_gap_cents"], 4),
            "net_edge_cents": round(economics["net_edge_cents"], 4),
            "edge_direction": name,
            "size_shares": round(float(economics["shares"]), 4),
            "depth_checked": ask_size is not None and bid_size is not None,
        }
        if bestes is None or kandidat["net_edge_cents"] > bestes["net_edge_cents"]:
            bestes = kandidat
    return bestes or dict(EMPTY_EDGE)


#: Die drei Zahlen, die eine Mittelkurs-Luecke von einer handelbaren Spanne
#: trennen, die Richtung, in der sie gilt, und die Groesse, fuer die sie gilt.
EDGE_COLUMNS = ("gross_edge_cents", "fee_band_cents", "net_edge_cents",
                "edge_direction", "size_shares", "depth_checked")

#: Das Urteil ueber das Paar selbst und seine Begruendung. Ohne diese beiden
#: Spalten steht eine Spanne ohne die Frage da, ob die beiden Seiten
#: ueberhaupt dasselbe fragen.
PAIR_COLUMNS = ("pair_verdict", "pair_reasons")


def _quote_index(frame: pd.DataFrame) -> dict[str, dict[str, Any]]:
    """Nachschlagewerk Marktschluessel/Ticker/Titel -> Zeile mit Quotes."""

    index: dict[str, dict[str, Any]] = {}
    for row in _rows(frame):
        for key in (row["market_key"], row["ticker"], row["title"].lower()):
            if key and key not in index:
                index[key] = row
    return index


def with_basket_edge(
    candidates: pd.DataFrame,
    polymarket_markets: pd.DataFrame,
    kalshi_markets: pd.DataFrame,
    shares: float = FEE_CLIP_SHARES,
) -> pd.DataFrame:
    """``basket_edge`` an eine fertige Paar-Tabelle anhaengen.

    ``deep_cross_candidates`` rechnet die Spanne schon beim Paaren mit;
    ``md.cross_venue_candidates`` paart nach einer Suchanfrage und liefert nur
    die Mittelkurse. Ohne diese Ergaenzung steht dort eine Mittelkurs-Luecke
    unter der Ueberschrift GAP und niemand handelt einen Mittelkurs. Die
    Zeilen werden ueber Marktschluessel, Ticker oder Titel in die
    Marktframes zurueckgeschlagen, weil nur dort die Quotes stehen.

    Ein Paar ohne beidseitige Quote auf beiden Venues bekommt ``None`` und
    keine Null: unbekannt ist nicht null.

    Dasselbe gilt fuer ein Paar, das ``pair_verdict`` verwirft. Der Matcher
    dieser Tabelle kennt nur Titel, und Titel sind blind fuer die Richtung
    der Frage. Die Spanne bleibt dann leer, das Urteil steht daneben.
    """

    if candidates is None or candidates.empty:
        return candidates
    pm_index = _quote_index(polymarket_markets) if polymarket_markets is not None else {}
    ks_index = _quote_index(kalshi_markets) if kalshi_markets is not None else {}

    def _lookup(index: dict[str, dict[str, Any]], row: Any, prefix: str) -> dict[str, Any] | None:
        for feld, klein in ((f"{prefix}_market_key", False), (f"{prefix}_ticker", False),
                            (f"{prefix}_title", True)):
            key = str(row.get(feld, "") or "").strip()
            if klein:
                key = key.lower()
            if key and key in index:
                return index[key]
        return None

    edges: list[dict[str, Any]] = []
    urteile: list[dict[str, Any]] = []
    for _, row in candidates.iterrows():
        pm_row = _lookup(pm_index, row, "polymarket")
        ks_row = _lookup(ks_index, row, "kalshi")
        # Das Urteil braucht nur die Titel, und die stehen in der
        # Kandidatentabelle selbst. Die Termine kommen aus den Marktframes,
        # wenn die Zeile dort gefunden wurde.
        urteil = pair_verdict(
            {"title": row.get("polymarket_title", ""),
             "end": (pm_row or {}).get("end")},
            {"title": row.get("kalshi_title", ""),
             "end": (ks_row or {}).get("end")})
        urteile.append(urteil)
        if urteil["verdict"] != PAIR_UNVERIFIED or not (pm_row and ks_row):
            edges.append(dict(EMPTY_EDGE))
            continue
        edges.append(basket_edge(pm_row, ks_row, shares=shares))
    out = candidates.copy()
    for column in EDGE_COLUMNS:
        out[column] = [edge[column] for edge in edges]
    out["pair_verdict"] = [urteil["verdict"] for urteil in urteile]
    out["pair_reasons"] = ["; ".join(urteil["reasons"]) for urteil in urteile]
    return out


def deep_cross_candidates(
    polymarket_markets: pd.DataFrame,
    kalshi_markets: pd.DataFrame,
    min_similarity: float = 0.2,
    max_pairs: int = 150,
    include_rejected: bool = False,
) -> pd.DataFrame:
    """Beste Kalshi-Entsprechung je Polymarket-Markt, sortiert nach |Gap|.

    Rueckgabespalten entsprechen ``md.cross_venue_candidates`` (Teilmenge),
    damit nachgelagerte Mapper unveraendert funktionieren.

    Gesucht wird die beste Entsprechung, die ``pair_verdict`` nicht verwirft.
    Das ist keine Feinheit der Reihenfolge: die Umkehrung einer Frage teilt
    fast jedes Wort mit ihr und gewinnt den Aehnlichkeitsvergleich deshalb
    regelmaessig gegen die richtige Entsprechung. Wer erst paart und dann
    prueft, verliert das gute Paar an das falsche.

    Bleibt fuer einen Markt nur eine verworfene Entsprechung, faellt er
    heraus. Mit ``include_rejected`` steht er trotzdem in der Tabelle, aber
    ohne jede Spanne: nur Titel, Urteil und Begruendung. Das ist fuer die
    Oberflaeche gedacht, die sagen soll, wie viele Paare warum nicht
    gerechnet wurden, statt sie stillschweigend verschwinden zu lassen.
    """

    if polymarket_markets is None or kalshi_markets is None:
        return pd.DataFrame()
    if polymarket_markets.empty or kalshi_markets.empty:
        return pd.DataFrame()

    pm_rows = _rows(polymarket_markets)
    ks_rows = _rows(kalshi_markets)
    if not pm_rows or not ks_rows:
        return pd.DataFrame()

    token_index: dict[str, list[int]] = {}
    for idx, row in enumerate(ks_rows):
        for token in row["tokens"]:
            token_index.setdefault(token, []).append(idx)

    out: list[dict[str, Any]] = []
    for pm_row in pm_rows:
        shared_counts: dict[int, int] = {}
        for token in pm_row["tokens"]:
            for idx in token_index.get(token, ()):
                shared_counts[idx] = shared_counts.get(idx, 0) + 1
        best: dict[str, Any] | None = None
        verworfen: dict[str, Any] | None = None
        for idx, shared in shared_counts.items():
            if shared < MIN_SHARED_TOKENS:
                continue
            ks_row = ks_rows[idx]
            similarity = md.market_similarity(pm_row["title"], ks_row["title"])
            if similarity < min_similarity:
                continue
            urteil = pair_verdict(pm_row, ks_row)
            ziel = "best" if urteil["verdict"] == PAIR_UNVERIFIED else "verworfen"
            kandidat = {"similarity": similarity, "ks": ks_row, "urteil": urteil}
            if ziel == "best":
                if best is None or similarity > best["similarity"]:
                    best = kandidat
            elif verworfen is None or similarity > verworfen["similarity"]:
                verworfen = kandidat
        gewaehlt = best or (verworfen if include_rejected else None)
        if gewaehlt is None:
            continue
        ks_row = gewaehlt["ks"]
        urteil = gewaehlt["urteil"]
        gap = pm_row["yes"] - ks_row["yes"]
        spanne = (basket_edge(pm_row, ks_row) if urteil["verdict"] == PAIR_UNVERIFIED
                  else dict(EMPTY_EDGE))
        out.append({
            "similarity": gewaehlt["similarity"],
            "gap": gap,
            "abs_gap": abs(gap),
            "polymarket_market_key": pm_row["market_key"],
            "kalshi_ticker": ks_row["ticker"],
            "polymarket_title": pm_row["title"],
            "kalshi_title": ks_row["title"],
            "polymarket_yes": pm_row["yes"],
            "kalshi_yes": ks_row["yes"],
            "polymarket_bid": pm_row["bid"],
            "polymarket_ask": pm_row["ask"],
            "kalshi_bid": ks_row["bid"],
            "kalshi_ask": ks_row["ask"],
            # Zwei Spalten, zwei Einheiten, und der Name sagt welche.
            # Polymarket meldet Dollar, Kalshi Kontrakte (Beleg in
            # app/venue_units.py). Diese beiden Zahlen duerfen nicht
            # addiert werden, und genau das stand hier vorher.
            "polymarket_volume_usd": pm_row["volume"],
            "kalshi_volume_contracts": ks_row["volume"],
            "polymarket_url": pm_row["url"],
            "kalshi_url": ks_row["url"],
            "polymarket_yes_token_id": pm_row["yes_token_id"],
            "pair_verdict": urteil["verdict"],
            "pair_reasons": "; ".join(urteil["reasons"]),
            **spanne,
        })

    if not out:
        return pd.DataFrame()
    frame = pd.DataFrame(out)
    frame = frame.sort_values(["abs_gap", "similarity"], ascending=[False, False])
    # ``max_pairs`` je Klasse, nicht ueber beide: verworfene Paare haben
    # naturgemaess die groessten Luecken (deshalb sind sie ja verworfen) und
    # wuerden eine gemeinsame Bestenliste von oben her auffuellen.
    gut = frame[frame["pair_verdict"] == PAIR_UNVERIFIED].head(max_pairs)
    if not include_rejected:
        return gut.reset_index(drop=True)
    verworfen = frame[frame["pair_verdict"] != PAIR_UNVERIFIED].head(max_pairs)
    return pd.concat([gut, verworfen], ignore_index=True).reset_index(drop=True)


def _touch(levels: Any, best: str) -> tuple[float | None, float | None]:
    """(Preis, Stueckzahl) an der Spitze einer Buchseite.

    ``best`` ist ``"max"`` fuer die Geldseite und ``"min"`` fuer die
    Briefseite. Ein leeres Buch ergibt ``(None, 0.0)``: kein Preis, und
    nachweislich nichts dahinter — das ist etwas anderes als "nicht
    nachgesehen".
    """

    if levels is None or getattr(levels, "empty", True):
        return None, 0.0
    if "price" not in getattr(levels, "columns", ()):
        return None, 0.0
    preise = pd.to_numeric(levels["price"], errors="coerce")
    groessen = (pd.to_numeric(levels["size"], errors="coerce")
                if "size" in levels.columns else None)
    gueltig = preise.notna()
    if not bool(gueltig.any()):
        return None, 0.0
    position = (preise[gueltig].idxmax() if best == "max" else preise[gueltig].idxmin())
    try:
        groesse = float(groessen.get(position)) if groessen is not None else 0.0
    except (TypeError, ValueError):
        groesse = 0.0
    return _quote(preise.get(position)), (groesse if groesse == groesse else 0.0)


def with_book_depth(
    candidates: pd.DataFrame,
    polymarket_markets: pd.DataFrame,
    kalshi_markets: pd.DataFrame,
    *,
    pm_book=None,
    ks_book=None,
    max_rows: int = 12,
    shares: float = FEE_CLIP_SHARES,
) -> pd.DataFrame:
    """Die Spitzen beider Buecher nachschlagen und die Spanne neu rechnen.

    Ohne diesen Schritt steht die Spanne fuer 100 Stueck da, weil 100 der
    Clip ist, auf dem die Gebuehrenkurven ausgewertet werden — nicht weil
    jemand nachgesehen haette, ob 100 Stueck an der Quote liegen. Eine
    Spanne, die es fuer drei Kontrakte gibt, ist kein Geschaeft ueber
    hundert. Die Studie in ``src/cross_venue_gaps.py`` fragt die Buecher seit
    jeher ab, die Web-Oberflaeche tat es nicht: dieselbe Zahl, zwei
    Bedeutungen.

    Nachgeschlagen werden Preis UND Groesse an der Spitze. Der Markt-Frame
    ist bis zu fuenf Minuten alt; eine alte Quote mit einer frischen Groesse
    zu paaren waere eine dritte, noch schlechtere Zahl.

    Das Modul selbst greift nie ins Netz: ``pm_book`` und ``ks_book`` sind
    die beiden Leser (Signatur wie ``md.get_polymarket_orderbook`` bzw.
    ``md.get_kalshi_orderbook``, Rueckgabe ``(bids, asks)``). Ohne sie
    passiert nichts, und die Zeilen behalten ``depth_checked=False``.

    ``max_rows`` deckelt die Abfragen: nachgeschlagen werden die Zeilen mit
    der groessten Netto-Spanne, also die, auf die jemand reagieren wuerde.
    """

    if candidates is None or candidates.empty or (pm_book is None and ks_book is None):
        return candidates
    if "net_edge_cents" not in candidates.columns:
        return candidates
    pm_index = _quote_index(polymarket_markets) if polymarket_markets is not None else {}
    ks_index = _quote_index(kalshi_markets) if kalshi_markets is not None else {}

    netto = pd.to_numeric(candidates["net_edge_cents"], errors="coerce")
    reihenfolge = list(netto.dropna().sort_values(ascending=False).index[:max_rows])
    out = candidates.copy()
    for column in EDGE_COLUMNS:
        if column not in out.columns:
            out[column] = None

    def _seiten(leser, schluessel: str) -> tuple[dict[str, Any] | None, bool]:
        if leser is None or not schluessel:
            return None, False
        try:
            bids, asks = leser(schluessel)
            bid_preis, bid_groesse = _touch(bids, "max")
            ask_preis, ask_groesse = _touch(asks, "min")
        except Exception as exc:  # noqa: BLE001 - ein Buch weniger ist kein Ausfall
            print(f"[warn] cross depth {schluessel}: {exc}")
            return None, False
        return {"bid": bid_preis, "ask": ask_preis,
                "bid_size": bid_groesse, "ask_size": ask_groesse}, True

    for position in reihenfolge:
        row = out.loc[position]
        pm_row = pm_index.get(str(row.get("polymarket_market_key") or ""))
        ks_row = ks_index.get(str(row.get("kalshi_ticker") or ""))
        if not pm_row or not ks_row:
            continue
        pm_seiten, pm_ok = _seiten(pm_book, str(row.get("polymarket_yes_token_id")
                                                or pm_row.get("yes_token_id") or ""))
        ks_seiten, ks_ok = _seiten(ks_book, str(row.get("kalshi_ticker") or ""))
        if not (pm_ok and ks_ok):
            continue
        neu_pm = {**pm_row, **{k: v for k, v in pm_seiten.items() if v is not None or k.endswith("_size")}}
        neu_ks = {**ks_row, **{k: v for k, v in ks_seiten.items() if v is not None or k.endswith("_size")}}
        spanne = basket_edge(neu_pm, neu_ks, shares=shares)
        # Beide Buecher gelesen: auch ein leeres Ergebnis ist ein Ergebnis.
        spanne["depth_checked"] = True
        if spanne["size_shares"] is None:
            spanne["size_shares"] = 0.0
        for column, wert in spanne.items():
            out.at[position, column] = wert
    return out
