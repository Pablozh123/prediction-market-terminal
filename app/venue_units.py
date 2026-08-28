"""Was eine Volumenzahl auf welcher Venue bedeutet, und was man damit rechnen darf.

Der Kern in einem Satz: Polymarket meldet Volumen in Dollar, Kalshi meldet es
in Kontrakten. Beide Zahlen standen im Terminal unter derselben Ueberschrift
und mit demselben Dollarzeichen, und die Cross-Venue-Tabelle hat sie addiert.

Beleg, gemessen am 2026-08-28 gegen die oeffentlichen Endpunkte
``/trade-api/v2/markets`` und ``/trade-api/v2/markets/trades``:

1. Die Feldnamen sagen es selbst. Jedes Dollar-Feld traegt das Suffix
   ``_dollars`` (``liquidity_dollars``, ``yes_bid_dollars``,
   ``last_price_dollars``, ``notional_value_dollars``). Volumen, Open Interest
   und Ordergroessen tragen stattdessen ``_fp`` (``volume_fp``,
   ``volume_24h_fp``, ``open_interest_fp``, ``yes_bid_size_fp``). Ein Feld
   ``volume_dollars`` gibt es nicht, weder auf ``external-api.kalshi.com``
   noch auf ``api.elections.kalshi.com``.

2. Die Arithmetik bestaetigt es. Fuer den Markt
   ``KXWTAMATCH-26AUG27VIDBAR-BAR`` meldete die API ``volume_fp = 896792.27``,
   waehrend die Summe von ``count_fp`` ueber alle 4399 Trades desselben
   Marktes exakt 896792.27 ergab. Die Summe von ``count_fp * Preis`` ergab
   dagegen 636041.30. Das Volumenfeld zaehlt also Stueck, nicht Dollar.

3. ``notional_value_dollars`` ist 1.0000: ein Kontrakt zahlt bei Aufloesung
   einen Dollar. Gehandelt wird er zu seinem Preis p, also sind die
   umgesetzten Dollar ``Stueck * p`` und nicht ``Stueck``. Genau deshalb
   ueberzeichnet die rohe Stueckzahl den Dollarumsatz um den Faktor ``1/p``:
   fuer ``KXMLBGAME-26AUG271915LADATL-LAD`` standen 4157305 Kontrakten
   1680422 tatsaechlich umgesetzte Dollar gegenueber, Faktor 2.47 bei einem
   mittleren Preis von 0.4039.

Was daraus folgt und was dieses Modul durchsetzt: eine Stueckzahl bekommt nie
ein Dollarzeichen, und eine Stueckzahl wird nie zu einem Dollarbetrag addiert.
Umgerechnet wird nur dort, wo ein Preis wirklich gemessen vorliegt, also am
einzelnen Trade (``contracts_to_usd``). Aus der Marktzeile allein laesst sich
der Dollarumsatz nicht rekonstruieren: der Durchschnittspreis ueber die
Lebenszeit des Marktes steht dort nicht, und der aktuelle Mittelkurs ist er
nicht. Lieber keine Zahl als eine Zahl in der falschen Einheit.

Streamlit-frei und netzfrei.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

#: Volumen in Dollar (Polymarket rechnet in USDC, also in Dollar).
USD = "usd"

#: Volumen als Stueckzahl gehandelter Kontrakte (Kalshi).
CONTRACTS = "contracts"

#: Einheit unbekannt. Nicht dasselbe wie null und nicht dasselbe wie Dollar.
UNKNOWN = ""

#: Venue -> Einheit ihrer Volumen- und Open-Interest-Felder.
VENUE_VOLUME_UNITS: dict[str, str] = {
    "polymarket": USD,
    "kalshi": CONTRACTS,
}

#: Was ein Kalshi-Kontrakt bei Aufloesung zahlt (``notional_value_dollars``).
#: Die Obergrenze des Dollarumsatzes, nicht der Umsatz selbst.
KALSHI_CONTRACT_NOTIONAL_USD = 1.0

#: Herkunft des Belegs, damit die Frage nicht ein drittes Mal gestellt wird.
UNIT_EVIDENCE = {
    "kalshi": (
        "Feldsuffixe der Kalshi-API (_dollars gegen _fp) plus Gegenprobe am "
        "Markt KXWTAMATCH-26AUG27VIDBAR-BAR: volume_fp 896792.27 gleich "
        "sum(count_fp) ueber alle Trades, ungleich sum(count_fp * Preis) "
        "636041.30 (gemessen 2026-08-28)"
    ),
    "polymarket": (
        "Gamma-API meldet volume und volumeNum in USDC, also in Dollar"
    ),
}


def volume_unit(platform: Any) -> str:
    """Einheit der Volumenfelder einer Venue, oder ``UNKNOWN``."""

    return VENUE_VOLUME_UNITS.get(str(platform or "").strip().casefold(), UNKNOWN)


def is_usd(platform: Any) -> bool:
    """Meldet diese Venue ihr Volumen in Dollar?"""

    return volume_unit(platform) == USD


def _as_float(value: Any) -> float | None:
    try:
        zahl = float(value)
    except (TypeError, ValueError):
        return None
    if zahl != zahl:  # NaN
        return None
    return zahl


def format_volume(value: Any, platform: Any) -> str:
    """Eine Volumenzahl mit der Einheit, die sie tatsaechlich hat.

    Dollar bekommen ein Dollarzeichen, Kontrakte bekommen das Wort. Eine
    Venue ohne bekannte Einheit bekommt die nackte Zahl, denn eine geratene
    Einheit waere schlimmer als gar keine.
    """

    zahl = _as_float(value)
    if zahl is None:
        return "-"
    einheit = volume_unit(platform)
    if einheit == USD:
        from app.format import money

        return money(zahl)
    if einheit == CONTRACTS:
        from app.format import contracts

        return contracts(zahl)
    return f"{zahl:,.0f}"


def format_volume_markdown(value: Any, platform: Any) -> str:
    """Wie ``format_volume``, aber das Dollarzeichen ist markdown-sicher."""

    return format_volume(value, platform).replace("$", "\\$")


def combined_volume(entries: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Volumen mehrerer Venues zusammenfassen, ohne Einheiten zu mischen.

    ``entries`` sind Abbildungen mit ``platform`` und ``volume``. Teilen sich
    alle Eintraege eine Einheit, kommt die Summe zurueck. Sonst kommt
    ``total = None`` zurueck, zusammen mit der Summe je Einheit. Der Aufrufer
    entscheidet dann, ob er zwei Zahlen zeigt oder einen Strich, aber eine
    gemischte Summe kann er hier nicht mehr bekommen.
    """

    je_einheit = _je_einheit(entries)
    if not je_einheit:
        return {"total": None, "unit": UNKNOWN, "by_unit": {}, "mixed": False}
    if len(je_einheit) == 1:
        einheit, summe = next(iter(je_einheit.items()))
        return {"total": summe, "unit": einheit, "by_unit": dict(je_einheit),
                "mixed": False}
    return {"total": None, "unit": UNKNOWN, "by_unit": dict(je_einheit),
            "mixed": True}


def volume_by_unit(platforms: Iterable[Any],
                   volumes: Iterable[Any]) -> dict[str, float]:
    """Volumen zweier paralleler Spalten nach Einheit getrennt aufsummiert.

    Der Weg fuer Tabellen und Frames: ``platforms`` und ``volumes`` sind die
    beiden Spalten, das Ergebnis ist ``{"usd": ..., "contracts": ...}`` mit
    einem Eintrag je vorkommender Einheit. Eine Einheit ohne Zeilen fehlt,
    denn nicht gemessen ist nicht null.

    Wer eine Gesamtsumme braucht, bekommt sie hier absichtlich nicht: die
    gaebe es nur, wenn alle Zeilen dieselbe Einheit haetten, und dafuer ist
    ``combined_volume`` zustaendig.
    """

    return {einheit: summe for einheit, summe in _je_einheit(
        {"platform": p, "volume": v} for p, v in zip(platforms, volumes)
    ).items()}


def _je_einheit(entries: Iterable[Mapping[str, Any]]) -> dict[str, float]:
    summen: dict[str, float] = {}
    for entry in entries or ():
        zahl = _as_float(entry.get("volume"))
        if zahl is None:
            continue
        einheit = volume_unit(entry.get("platform"))
        summen[einheit] = summen.get(einheit, 0.0) + zahl
    return summen


def contracts_to_usd(count: Any, price: Any) -> float | None:
    """Kontrakte in Dollar, aber nur mit einem echten Preis.

    Der Preis muss der Preis sein, zu dem gehandelt wurde, also aus dem Trade
    kommen. Ohne brauchbaren Preis kommt ``None`` zurueck und nicht etwa die
    Stueckzahl: das war der ganze Fehler.
    """

    stueck = _as_float(count)
    preis = _as_float(price)
    if stueck is None or preis is None:
        return None
    if not (0.0 < preis <= 1.0):
        return None
    return stueck * preis * KALSHI_CONTRACT_NOTIONAL_USD
