"""Suspicious-activity helpers layered on top of the whale insider risk scores.

Pure pandas, Streamlit-free. The base event/wallet scores come from
``src.prediction_markets.whale_event_risk_scores`` / ``whale_wallet_risk_scores``;
this module adds the signals those scores cannot see on their own:

- fresh-wallet clusters: several barely-seen wallets piling into the same market
  on the same side (the classic pattern public insider screens describe),
- real account age (when the caller fetched it) as a score bonus,
- plain-language one-line stories so a non-expert can read an event card.

Everything here is a best-effort public-data screen, not a legal finding.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Any, Mapping, NamedTuple

import pandas as pd

from app.filters import numeric_col
from app.format import money, pct
from src import prediction_markets as md
from src.prediction_markets import identified_wallets

try:
    import networkx as nx
except ImportError:  # pragma: no cover - networkx ships with the environment
    nx = None

#: Whale-Schwelle, wenn die Einstellungen keine tragen.
DEFAULT_WHALE_THRESHOLD = 2500.0


def screen_thresholds(settings: Any = None) -> tuple[float, float]:
    """(whale_threshold, tape_floor) fuer JEDE Oberflaeche mit Insider-Score.

    Eine Definition, damit dieselbe Wallet nicht auf zwei Seiten zwei Zahlen
    unter demselben Namen traegt. Der Screen im API-Server las das Tape ab
    ``max(500, 20 % der Whale-Schwelle)``, die Streamlit-Seite "Suspicious"
    ab der Whale-Schwelle selbst (2500) — verschiedene Boeden bedeuten
    verschiedene Anteile (Long-Odds-Anteil, Marktkonzentration, Prints je
    Stunde) und damit verschiedene Scores.

    Der Boden ist derselbe, ab dem der Scorer Verteilungs-Signale voll
    zaehlt (``md.DISTRIBUTION_NOTIONAL_FLOOR``): mit ``min_cash=0`` fressen
    die Mikro-Prints das Fenster, mit der vollen Whale-Schwelle bleibt zu
    wenig Tape uebrig, um Anteile zu messen.
    """

    from app import app_settings as cfg
    from src import prediction_markets as md

    data = settings if settings is not None else cfg.load_settings()
    try:
        whale = float((data or {}).get("whale_threshold", DEFAULT_WHALE_THRESHOLD))
    except (TypeError, ValueError):
        whale = DEFAULT_WHALE_THRESHOLD
    if whale != whale or whale <= 0:
        whale = DEFAULT_WHALE_THRESHOLD
    return whale, max(float(md.DISTRIBUTION_NOTIONAL_FLOOR), whale * 0.2)


RISK_BANDS = ((70, "High"), (55, "Medium"), (40, "Elevated"))
WATCH_ONLY = "watch only"

# --------------------------------------------------------------------------
# What the number IS, said once, for every surface that shows it.
#
# ``RISK_BANDS`` above is the INTERNAL level vocabulary. It is the wire
# format: ``event_insider_level`` / ``wallet_insider_level`` carry it, the
# API maps it to ``sev``, the flag log stores it, and the frontend filters
# on it. It stays as it is.
#
# What follows is the DISPLAY vocabulary, and it is a different thing on
# purpose. "High" next to a number between 0 and 100 reads as a probability
# of insider trading, and the number is nothing of the kind: it is the sum
# of ten flow features against fixed point caps, with weights that were
# chosen rather than estimated, and it has never been measured against a
# single confirmed case. The bands below therefore count how much of the
# screen's checklist a row tripped, which is what the arithmetic does.
# --------------------------------------------------------------------------

#: How the number is named wherever it is shown.
SCORE_NAME = "flow-pattern score"
#: The unit. Points against fixed caps, not percent and not probability.
SCORE_UNIT = "pattern points"
#: Points at or above which the screen keeps a row (api_views, risk_log).
FLAG_FLOOR = 40.0
#: Raw sum of all caps before the clip to 100. Both surfaces pass 100 by a
#: wide margin, so a row can max out several features and still not reach
#: 100 on the others. The event side carries the bigger first-trade cap.
SCORE_RAW_MAX_EVENT = 135.0
SCORE_RAW_MAX_WALLET = 125.0
#: The event figure under the name the basis has always used.
SCORE_RAW_MAX = SCORE_RAW_MAX_EVENT

#: (floor, label, tone, what the band means). Ordered high to low; the labels
#: say how many of the checks fired, never how likely anything is.
SCORE_BANDS = (
    (70.0, "MOST PATTERNS", "warn", "tripped most of the screen's checks"),
    (55.0, "MANY PATTERNS", "warn", "tripped many of them"),
    (40.0, "SOME PATTERNS", "muted", "cleared the flag floor: gets a card and a log row"),
    (0.0, "FEW PATTERNS", "quiet", "below the flag floor: counted, not shown as a card"),
)

#: The ten features the scorer sums, with the caps each one is worth. The
#: caps ARE the weights, and they were set by hand: nothing in this repo
#: fitted them, and no column anywhere joins them to an outcome.
#: (key, name, what goes in, event cap, wallet cap)
SCORE_FEATURES = (
    ("notional", "Size of the flow",
     "dollars traded in the window; full marks at 40x the whale threshold (event) or 20x (wallet)", 15.0, 15.0),
    ("largest", "Biggest single print",
     "the largest single trade; full marks at 5x the whale threshold", 10.0, 10.0),
    ("long_odds", "Long-odds money",
     "share of the flow placed at 35 cents or below (20 cents and under count in full, 21 to 35 cents at 60 percent), "
     "plus its dollar size", 10.0, 15.0),
    ("concentration", "Concentration",
     "share of the flow done by the top wallet (event) or sitting in the top market (wallet)", 15.0, 15.0),
    ("direction", "One-sided flow",
     "net YES-versus-NO pressure; counts from 55 percent, full marks at 100", 10.0, 10.0),
    ("burst", "Speed",
     "prints per hour in the window; full marks at 30", 15.0, 10.0),
    ("late", "Late in the market",
     "share of the flow inside the market's last 48 hours", 15.0, 15.0),
    ("price_move", "Price moved their way",
     "first-to-last price change in the flow's direction; full marks at 15 cents", 10.0, 10.0),
    ("cluster", "Several wallets, or a fresh one",
     "3 or more wallets at 10+ prints an hour (event); a barely-seen wallet placing a 2x print (wallet)", 10.0, 10.0),
    ("first_trade", "First trade just before",
     "dollars from wallets whose first trade on the venue lies under 3 days before their print, full marks at 4x the "
     "whale threshold (event); the wallet's own first trade under 3 days back, half marks under 30 days (wallet)", 25.0, 15.0),
)

#: Bonuses and multipliers applied AFTER the ten features, in this module.
SCORE_ADJUSTMENTS = (
    ("fresh-wallet cluster", "up to +10 points when several barely-seen wallets take the same side"),
    ("coordinated timing", "up to +10 points when wallets hit one side within minutes"),
    ("account age", "up to +10 points when a top wallet's real on-chain age is days, not months"),
    ("context multiplier", "x0.5 to x1.15 by market subject; sports, weather and asset prices are dropped entirely"),
)


def score_band(score: Any) -> dict[str, Any]:
    """Display band of a score: ``{floor, label, tone, meaning}``.

    Deliberately NOT ``risk_level``: that one answers "which internal level
    is this" and returns High/Medium/Elevated/Low, which is the wire format.
    This one answers "what may the screen call it in front of a reader".
    """

    try:
        value = float(score or 0.0)
    except (TypeError, ValueError):
        value = 0.0
    if value != value:  # NaN
        value = 0.0
    for floor, label, tone, meaning in SCORE_BANDS:
        if value >= floor:
            return {"floor": floor, "label": label, "tone": tone, "meaning": meaning}
    last = SCORE_BANDS[-1]
    return {"floor": last[0], "label": last[1], "tone": last[2], "meaning": last[3]}


def score_band_table() -> list[dict[str, Any]]:
    """The bands as a legend: ``{from, to, label, tone, meaning}``, low to high."""

    rows: list[dict[str, Any]] = []
    ordered = sorted(SCORE_BANDS, key=lambda row: row[0])
    for index, (floor, label, tone, meaning) in enumerate(ordered):
        upper = ordered[index + 1][0] - 1 if index + 1 < len(ordered) else 100.0
        rows.append({
            "from": round(floor), "to": round(upper),
            "label": label, "tone": tone, "meaning": meaning,
        })
    return rows


def score_basis() -> dict[str, Any]:
    """Everything a surface needs to describe the score truthfully.

    One dict, so no page has to restate the arithmetic in its own words and
    then drift from it. The standing caveat is NOT in here: it lives in
    data/claims.yaml under ``insider_score_unvalidated`` and is rendered
    through the register, like every other caveat in this code base.
    """

    return {
        "name": SCORE_NAME,
        "unit": SCORE_UNIT,
        "scale": {"min": 0, "max": 100, "raw_max": SCORE_RAW_MAX_EVENT, "raw_max_wallet": SCORE_RAW_MAX_WALLET,
                  "clipped_at": 100},
        "flag_floor": round(FLAG_FLOOR),
        "weights": (
            "The caps below are the weights, and they were chosen, not estimated. "
            "No step in this repository fits them to anything."
        ),
        "features": [
            {"key": key, "name": name, "reads": reads,
             "cap_event": cap_event, "cap_wallet": cap_wallet}
            for key, name, reads, cap_event, cap_wallet in SCORE_FEATURES
        ],
        "adjustments": [{"name": name, "effect": effect} for name, effect in SCORE_ADJUSTMENTS],
        "bands": score_band_table(),
    }


#: What would have to exist before a hit rate could be put next to the score.
#: Written down so the gap is a task, not a shrug.
SCORE_VALIDATION_MISSING = (
    "a labelled set of markets where insider trading was later established "
    "(regulator finding, venue statement, court record), joined to the tape by market key",
    "the flag log running long enough on a host that keeps it: the screen scores "
    "every market in every window, so a usable denominator needs months, not a session",
    "a pre-registered rule for what counts as a hit before the counting starts, "
    "and a correction for the fact that every market is tested against every rule",
)


def score_validation() -> dict[str, Any]:
    """What was measured about this score, and what was not.

    ``against_outcome`` is ``None`` and stays ``None`` until the three items
    in ``SCORE_VALIDATION_MISSING`` exist. ``measured_instead`` points at the
    one thing the repository does measure about the screen, which is a
    different quantity and must never be shown as if it were this one.
    """

    return {
        "against_outcome": None,
        "measured_instead": {
            "quantity": "price of the flagged side at +30 min, +2 h and +24 h after the flag",
            "source": "/api/risk/log?enrich=1 (app.risk_log.flag_scoreboard)",
            "reads": (
                "whether the price followed the flagged side, over the flags this host happened "
                "to log; it says nothing about who knew what"
            ),
        },
        "missing": list(SCORE_VALIDATION_MISSING),
        # Documented public cases replayed through the screen: a regression
        # suite for the patterns, not a hit rate. It answers "would the screen
        # have shown this" for each case, and nothing about all the flow it
        # would have shown besides.
        "case_list": _case_list_summary(),
    }


def _case_list_summary() -> dict[str, Any] | None:
    try:
        from app import insider_cases

        return insider_cases.summary()
    except Exception:  # noqa: BLE001 - the basis must render without the list
        return None

# Insider-plausibility context: in some market categories there is nothing to
# "know" early (game results, weather models, public asset prices) — big flow
# there is high-roller action, not insider trading. In others the outcome is
# literally known to a small group before the public (award juries, boards,
# courts), which is where documented prediction-market insider cases happened.
CONTEXT_SPORTS = "Sports odds"
CONTEXT_MARKET_PRICES = "Crypto & market prices"
CONTEXT_WEATHER = "Weather & climate"
CONTEXT_POLITICS = "Politics & elections"
CONTEXT_GEOPOLITICS = "Geopolitics & conflict"
CONTEXT_MACRO = "Macro & central banks"
CONTEXT_AWARDS = "Awards & entertainment"
CONTEXT_CORPORATE = "Corporate & legal"
CONTEXT_GENERAL = "General"

# Groups the risk screen drops ENTIRELY — not damped, not behind a toggle.
# Sports odds and weather: game results and weather models cannot be
# insider-traded. Crypto & market prices: asset prices are public, so a whale
# there is a trader, not an insider — and the 15-minute up/down markets are
# the busiest on both venues, so left in they flood every output (events,
# wallets, fresh-wallet and timing clusters, the co-trading network) with
# noise. Every consumer (API /api/risk, Streamlit "Suspicious" page) filters
# with this tuple; ``INSIDER_PRONE_GROUPS`` is its complement.
EXCLUDED_CONTEXTS = (CONTEXT_SPORTS, CONTEXT_WEATHER, CONTEXT_MARKET_PRICES)

# The multipliers only matter for the groups that survive the exclusion above;
# the excluded groups keep a value so ``classify_insider_context`` stays total.
CONTEXT_MULTIPLIERS = {
    CONTEXT_SPORTS: 0.6,
    CONTEXT_MARKET_PRICES: 0.6,
    CONTEXT_WEATHER: 0.5,
    CONTEXT_POLITICS: 1.1,
    CONTEXT_GEOPOLITICS: 1.15,
    CONTEXT_MACRO: 1.1,
    CONTEXT_AWARDS: 1.15,
    CONTEXT_CORPORATE: 1.15,
    CONTEXT_GENERAL: 1.0,
}

CONTEXT_NOTES = {
    CONTEXT_SPORTS: "public-odds arena — big flow here is usually high rollers, not insiders",
    CONTEXT_MARKET_PRICES: "asset prices are public — whales here are traders, not insiders",
    CONTEXT_WEATHER: "model-driven outcome — insider knowledge is implausible",
    CONTEXT_POLITICS: "decisions, talks and announcements are known to officials before the public",
    CONTEXT_GEOPOLITICS: "strikes, ceasefires, sanctions and troop moves are known to officials and forces before the public",
    CONTEXT_MACRO: "rate decisions and data releases are set inside institutions before the release",
    CONTEXT_AWARDS: "results are known to juries and production staff early — documented insider territory",
    CONTEXT_CORPORATE: "decisions are known internally before announcement",
    CONTEXT_GENERAL: "",
}

# Groups where insider knowledge is plausible — the only groups the screen shows.
INSIDER_PRONE_GROUPS = (CONTEXT_GEOPOLITICS, CONTEXT_MACRO, CONTEXT_POLITICS, CONTEXT_AWARDS, CONTEXT_CORPORATE, CONTEXT_GENERAL)

_CATEGORY_GROUPS = (
    (("sport", "sports", "nba", "nfl", "mlb", "soccer", "football", "esports"), CONTEXT_SPORTS),
    (("crypto", "cryptocurrency", "finance", "stocks"), CONTEXT_MARKET_PRICES),
    # NOTE: "science" deliberately NOT here — tech/science markets are not
    # model-driven weather outcomes and must not be damped/excluded.
    (("weather", "climate"), CONTEXT_WEATHER),
    # "geopolitic" before "politic": the shorter key is inside the longer one.
    (("geopolitic", "world", "global affairs", "middle east", "conflict"), CONTEXT_GEOPOLITICS),
    (("econom", "macro", "fed rates", "inflation", "interest rate", "central bank"), CONTEXT_MACRO),
    (("politic", "election"), CONTEXT_POLITICS),
    (("entertainment", "awards", "pop culture", "culture", "music", "movies", "tv"), CONTEXT_AWARDS),
    (("business", "companies", "tech", "earnings"), CONTEXT_CORPORATE),
)

# Order matters. STRONG sports markers (leagues, esports titles, betting
# jargon) win first — a "Counter-Strike: X vs Y" market is sports even though
# "strike" appears in the politics pattern. Then the insider-prone patterns
# (corporate/legal, awards, politics) are checked BEFORE the bare "vs" token,
# so "Epic vs Apple ruling" or "Zelensky vs Putin summit" land in
# Corporate/Politics instead of being silently dropped as sports. A naked
# "X vs Y" with no other signal stays a sports matchup.
_TITLE_PATTERNS = (
    (re.compile(r"\bw?nba\b|\bnfl\b|\bmlb\b|\bnhl\b|\bufc\b|\bfinals\b|\bgrand prix\b|\bpremier league\b|\bchampions league\b|\bbundesliga\b|\bserie a\b|\bla liga\b|\bsuper bowl\b|\bworld series\b|\bworld cup\b|\bplayoffs?\b|\bopen:\s|\b(?:us|french|australian) open\b|\bwimbledon\b|\bolympic|\bspread:?\b|\bmoneyline\b|\bover/under\b|\bo/u\b|\bexact score\b|\bat halftime\b|\bboth teams to score\b|\bwins? by over\b|\b\d+(?:\.\d+)?\s+goals?\b|\([+-]?\d+(?:\.5)\)|counter[- ]strike|\bcs2\b|\bcsgo\b|\bdota\b|\bvalorant\b|\bleague of legends\b|\besports?\b|\bgolf\b|\binnings?\b|\btouchdowns?\b|\bhome runs?\b|\bstrikeouts?\b|\brebounds?\b|\bassists?\b", re.I), CONTEXT_SPORTS),
    (re.compile(r"\bceo\b|\bacquisition\b|\bmerger\b|\bipo\b|\bearnings\b|\blawsuit\b|\bcourt\b|\bruling\b|\bverdict\b|\bindicted?\b|\bconvicted\b|\bpardon\b|\bresigns?\b|\bappoints?\b|\bnominee\b|\bnomination\b|\bcabinet\b|\bsteps? down\b|\bfired\b|\brelease date\b", re.I), CONTEXT_CORPORATE),
    (re.compile(r"\boscars?\b|\bgrammys?\b|\bemmys?\b|\bgolden globe\b|\baward\b|\balbum\b|\bbox office\b|\btrailer\b|\bseason finale\b|\brenewed\b|\beurovision\b|\bperson of the year\b|\bbillboard\b", re.I), CONTEXT_AWARDS),
    (re.compile(r"\btemperature\b|\brainfall\b|\bsnowfall\b|\bhurricane\b|\bstorm\b|\bheat wave\b|\bweather\b|\bdegrees\b|°[cf]\b", re.I), CONTEXT_WEATHER),
    # Public asset prices: crypto, indices, commodities, market caps. "Up or
    # Down" is Polymarket's price-series format (Bitcoin/BNB/WTI Up or Down -
    # <window>); "hit (HIGH) $" is its commodity/valuation ladder format.
    (re.compile(r"\bbitcoin\b|\bbtc\b|\bethereum\b|\beth\b|\bsolana\b|\bxrp\b|\bdogecoin\b|\bbnb\b|\bcrypto\b|\btoken\b|\bs&p\b|\bnasdaq\b|\bstock price\b|\bshare price\b|\bgold price\b|\boil price\b|\bgas prices?\b|\bsilver price\b|\btreasury yield\b|\bclose price\b|\bexchange rate\b|\bcrude oil\b|\bwti\b|\bbrent\b|\bmarket cap\b|\bup or down\b|\b(?:hit|reach) (?:\((?:high|low)\) )?\$", re.I), CONTEXT_MARKET_PRICES),
    # Kalshi price tickers. The API tape carries the raw ticker as title
    # (KXBTC15M-26AUG16-1345, KXETHD-…, KXWTI15M-…, KXINXD-…) and "\bbtc\b"
    # cannot see "btc" inside "KXBTC15M". Every KX…15M ticker is a 15-minute
    # price up/down market; the prefix set is explicit otherwise so
    # KXETHIOPIA-… does not turn into an Ethereum market.
    (re.compile(r"\bkx[a-z0-9]{1,12}15m(?=-|\b)|\bkx(?:btc|eth|sol|xrp|doge|bnb|inx|nasdaq100|wti|gold|silver)(?:15m|d|h|w|m|y|maxy?|miny?)?(?=-|\b)", re.I), CONTEXT_MARKET_PRICES),
    # Kalshi sports and weather series carry the same problem: the API tape
    # sees "KXWNBAGAME-26AUG16-…" or "KXHIGHTHOU-…" as the title, and "\bwnba\b"
    # cannot fire inside a ticker. Series names are league/format words glued
    # together, so match the known league prefixes and the GAME/MATCH/SET/MAP
    # suffix families for sports, and the HIGH/LOW/TEMP/RAIN/SNOW families for
    # weather. Both stay excluded from the insider screen for the same reason
    # as their Polymarket counterparts.
    (re.compile(r"\bkx(?:atp|wta|mlb|nba|wnba|nfl|nhl|ufc|mma|pga|lpga|f1|nascar|mls|epl|ucl|laliga|bundesliga|seriea|ligue1|valorant|cs2|csgo|lol|dota|tennis|golf|soccer|ncaa[a-z]*|mve[a-z]*|itf[a-z]*|[a-z0-9]*(?:game|match|set|map|series|round|race|fight))(?:[a-z0-9]*)?(?=-|\b)", re.I), CONTEXT_SPORTS),
    (re.compile(r"\bkx(?:high|low|temp|rain|snow|wind|hurr|precip|heat)[a-z0-9]*(?=-|\b)", re.I), CONTEXT_WEATHER),
    # Elections first: an election in a conflict country is still an
    # election, and "Will Newsom win on 2026-11-03?" must not read as a
    # matchday. Then conflict and diplomacy, then central banks and data
    # releases, then the rest of politics. Geopolitics and macro used to fall
    # through to "General": the screen kept them but could not name them,
    # and the public cases of 2026 sit almost entirely in those two groups.
    (re.compile(r"\belections?\b|\bprimary\b|\brunoff\b|\bballot\b|\bnominee\b|\bgovernor\b|\bmayor\b|\bduma\b|\bparliamentary\b|\bmost seats\b|\bwin the presidency\b|\bpresidential\b", re.I), CONTEXT_POLITICS),
    (re.compile(r"\bcease-?fire\b|\btruce\b|\bsanctions?\b|\btreaty\b|\bmilitary\b|(?<!-)\bstrikes?\b|\bairstrikes?\b|\binvasion\b|\binvades?\b|\bnato\b|\bwar\b|\bwarfare\b|\btroops\b|\bground operation\b|\bmissiles?\b|\bnuclear\b|\bblockade\b|\bhormuz\b|\bkharg\b|\bfarsi island\b|\biran\b|\biranian\b|\bisrael\b|\bisraeli\b|\bgaza\b|\bhamas\b|\bhezbollah\b|\bhouthis?\b|\bukraine\b|\bukrainian\b|\brussia\b|\brussian\b|\bputin\b|\bzelensky?y?\b|\btaiwan\b|\bnorth korea\b|\bkim jong\b|\bnetanyahu\b|\bidf\b|\bpentagon\b|\bairspace\b|\bregime\b|\bcoup\b|\bleadership change\b|\bpeace (?:deal|agreement|talks)\b|\bsummit\b|\bno[- ]fly zone\b|\bnaval\b|\bdrones?\b|\bmaduro\b|\bvenezuela\b|\bkremlin\b|\bstrait\b", re.I), CONTEXT_GEOPOLITICS),
    (re.compile(r"\bfed\b|\bfomc\b|\bfederal reserve\b|\bfed chair\b|\bpowell\b|\binterest rates?\b|\brate (?:cut|hike|decision|change)s?\b|\bbps\b|\bbasis points?\b|\bcpi\b|\binflation\b|\bgdp\b|\brecession\b|\bunemployment\b|\bjobs? report\b|\bpayrolls?\b|\bnonfarm\b|\becb\b|\bbank of england\b|\bbank of japan\b|\bboj\b|\bboe\b|\bsnb\b|\bpce\b|\bjobless claims\b|\bdebt ceiling\b|\bcentral bank\b", re.I), CONTEXT_MACRO),
    (re.compile(r"\btariffs?\b|\bagreement\b|\bexecutive order\b|\bpresident\b|\bminister\b|\bparliament\b|\bcongress\b|\bsenate\b|\bimpeach|\bxi jinping\b|\bsigned into law\b|\bh\.r\.\s?\d|\bbill\b|\bveto\b|\bwhite house\b|\bsupreme court\b|\bscotus\b|\btrump\b|\bbiden\b|\bshutdown\b|\bgovernment\b", re.I), CONTEXT_POLITICS),
    # Spieltag-Untermaerkte ohne Kontexttitel. "Will FC Thun win on
    # 2026-08-06?" traegt kein Liga- oder Vereinswort, das der Katalog oben
    # kennt, und rutschte deshalb als "General" in den Insider-Screen. Diese
    # Regel steht bewusst hinter Politik und Konzernen: "Will the president
    # win on ..." soll weiterhin Politik bleiben, nicht Sport.
    (re.compile(r"\bfc\b|\bwin on \d{4}-\d{2}-\d{2}\b|\bwin their match\b|\bto lift the\b|^parlay · \d+ legs:", re.I), CONTEXT_SPORTS),
    (re.compile(r"\bvs\.?\b", re.I), CONTEXT_SPORTS),
)


def classify_insider_context(title: Any, category: Any = "", context_text: Any = "") -> tuple[str, float, str]:
    """Map a market to an insider-plausibility group: (group, multiplier, note).

    Title keywords win over the coarse category field so that e.g. a "CEO
    resigns" market filed under Business stays insider-prone while a generic
    sports matchup is damped even when the category is missing.
    ``context_text`` (e.g. the parent event title — "Mexico vs. South Africa")
    is scanned with the same title patterns: sub-market titles like
    "Will Mexico win on 2026-06-11?" carry no sports keyword themselves.
    """

    title_text = f"{str(title or '')} {str(context_text or '')}".strip()
    for pattern, group in _TITLE_PATTERNS:
        if pattern.search(title_text):
            return group, CONTEXT_MULTIPLIERS[group], CONTEXT_NOTES[group]
    category_text = str(category or "").strip().lower()
    if category_text:
        for keys, group in _CATEGORY_GROUPS:
            if any(key in category_text for key in keys):
                return group, CONTEXT_MULTIPLIERS[group], CONTEXT_NOTES[group]
    return CONTEXT_GENERAL, CONTEXT_MULTIPLIERS[CONTEXT_GENERAL], CONTEXT_NOTES[CONTEXT_GENERAL]


def _category_context_maps(market_categories: pd.DataFrame | None) -> tuple[dict[str, str], dict[str, str]]:
    """Build market_key -> category and market_key -> context_text lookups."""

    if market_categories is None or market_categories.empty or not {"market_key", "category"}.issubset(market_categories.columns):
        return {}, {}
    keys = market_categories["market_key"].astype(str)
    category_map = dict(zip(keys, market_categories["category"].fillna("").astype(str)))
    context_map: dict[str, str] = {}
    if "context_text" in market_categories.columns:
        context_map = dict(zip(keys, market_categories["context_text"].fillna("").astype(str)))
    return category_map, context_map


_KALSHI_TICKER_RE = re.compile(r"^KX[A-Z0-9]+(?:-[A-Z0-9.]+)+$", re.I)


def _keys_with_ticker(frame: pd.DataFrame) -> pd.Series:
    """market_key per row, or the Kalshi ticker where the key is empty —
    Kalshi prints carry no market_key, the ticker is their key."""

    keys = frame.get("market_key", pd.Series("", index=frame.index)).fillna("").astype(str)
    if "ticker" in frame.columns:
        ticker = frame["ticker"].fillna("").astype(str)
        keys = keys.where(keys.str.strip().ne("") & keys.str.lower().ne("nan"), ticker)
    return keys


def _row_key(row: Any) -> str:
    """market_key of one row, or its Kalshi ticker when the key is missing
    or NaN (a frame with both kinds of rows has NaN in the other column)."""

    for field in ("market_key", "ticker"):
        value = row.get(field, "") if hasattr(row, "get") else ""
        text = "" if value is None else str(value).strip()
        if text and text.lower() != "nan":
            return text
    return ""


def _context_with_ticker(key: Any, context_map: dict[str, str]) -> str:
    """Context text for a market key: the parent-event text, plus the key
    itself when it is a Kalshi ticker.

    The tape used to carry the Kalshi ticker as the title, and the KX…
    patterns above read it there. Now the title is the market's question
    ("Silver price up in next 15 mins?") and the ticker lives only in
    market_key — so the ticker rides along as context, and KXSILVER15M still
    says "market price", KXHIGHMIA still says "weather", whatever the
    question's wording.
    """

    key_text = str(key or "")
    extra = context_map.get(key_text, "")
    if _KALSHI_TICKER_RE.match(key_text):
        return f"{extra} {key_text}".strip()
    return extra


def risk_level(score: Any) -> str:
    try:
        value = float(score or 0.0)
    except (TypeError, ValueError):
        value = 0.0
    for threshold, label in RISK_BANDS:
        if value >= threshold:
            return label
    return "Low"


def _append_flag(flags: Any, new_flag: str) -> str:
    text = str(flags or "").strip()
    if not text or text == WATCH_ONLY:
        return new_flag
    return f"{text}; {new_flag}"


def fresh_wallet_clusters(
    trades: pd.DataFrame,
    *,
    whale_threshold: float,
    fresh_max_trades: int = 2,
    min_wallets: int = 2,
) -> pd.DataFrame:
    """Per market: how many barely-seen wallets bet meaningful size on the same side.

    "Fresh" is relative to the sampled tape (few trades in the sample but whale-sized
    notional) — the same proxy the base wallet score uses for its fresh-wallet flag.
    Returns columns: title, fresh_wallets, fresh_outcome, fresh_notional.
    """

    columns = ["platform", "title", "fresh_wallets", "fresh_outcome", "fresh_notional"]
    if trades is None or trades.empty or "wallet" not in trades or "title" not in trades:
        return pd.DataFrame(columns=columns)
    df = trades.copy()
    df["wallet"] = df["wallet"].astype(str).str.lower().str.strip()
    df = df[identified_wallets(df["wallet"])]
    if df.empty:
        return pd.DataFrame(columns=columns)
    # Clusters are wallet evidence — they must stay on the venue that produced
    # them. event_risk rows are keyed (platform, title); merging on title alone
    # would let a Polymarket cluster inflate a same-titled Kalshi row.
    df["platform"] = df.get("platform", pd.Series("", index=df.index)).fillna("").astype(str)
    df["notional"] = numeric_col(df, "notional")
    per_wallet = df.groupby("wallet").agg(trade_count=("wallet", "size"), total_notional=("notional", "sum"))
    fresh_wallets = per_wallet[
        (per_wallet["trade_count"] <= int(fresh_max_trades)) & (per_wallet["total_notional"] >= float(whale_threshold))
    ].index
    fresh = df[df["wallet"].isin(fresh_wallets)].copy()
    if fresh.empty:
        return pd.DataFrame(columns=columns)
    fresh["outcome_label"] = fresh.get("outcome", pd.Series("", index=fresh.index)).astype(str).str.upper().str.strip()
    grouped = (
        fresh.groupby(["platform", "title", "outcome_label"], dropna=False)
        .agg(fresh_wallets=("wallet", "nunique"), fresh_notional=("notional", "sum"))
        .reset_index()
    )
    grouped = grouped.sort_values(["fresh_wallets", "fresh_notional"], ascending=False)
    best = grouped.drop_duplicates(subset=["platform", "title"], keep="first").rename(columns={"outcome_label": "fresh_outcome"})
    best = best[best["fresh_wallets"] >= int(min_wallets)]
    return best[columns].reset_index(drop=True)


def apply_fresh_wallet_bonus(event_risk: pd.DataFrame, clusters: pd.DataFrame, max_bonus: float = 10.0) -> pd.DataFrame:
    """Bump event scores where a fresh-wallet cluster sits on one side; add a flag."""

    if event_risk is None or event_risk.empty:
        return event_risk
    enriched = event_risk.copy()
    if clusters is None or clusters.empty:
        enriched["fresh_wallets"] = 0
        return enriched
    merge_keys = ["platform", "title"] if "platform" in enriched.columns and "platform" in clusters.columns else ["title"]
    enriched = enriched.merge(clusters.drop(columns=[c for c in ("platform",) if c not in merge_keys and c in clusters.columns]), on=merge_keys, how="left")
    enriched["fresh_wallets"] = pd.to_numeric(enriched.get("fresh_wallets"), errors="coerce").fillna(0).astype(int)
    has_cluster = enriched["fresh_wallets"] >= 2
    bonus = (enriched["fresh_wallets"].clip(upper=4) * (max_bonus / 4.0)).where(has_cluster, 0.0)
    enriched["component_fresh_wallets"] = bonus.round(1)
    enriched["event_insider_score"] = (numeric_col(enriched, "event_insider_score") + bonus).clip(0, 100).round(0)
    enriched["event_insider_level"] = enriched["event_insider_score"].map(risk_level)
    if "event_insider_flags" in enriched:
        cluster_rows = enriched.index[has_cluster]
        for idx in cluster_rows:
            count = int(enriched.at[idx, "fresh_wallets"])
            outcome = str(enriched.at[idx, "fresh_outcome"] or "").strip()
            label = f"{count} fresh wallets on {outcome}" if outcome else f"{count} fresh wallets same side"
            enriched.at[idx, "event_insider_flags"] = _append_flag(enriched.at[idx, "event_insider_flags"], label)
    return enriched


def filter_insider_prone_trades(
    trades: pd.DataFrame,
    market_categories: pd.DataFrame | None = None,
    excluded: tuple[str, ...] = EXCLUDED_CONTEXTS,
) -> pd.DataFrame:
    """Drop trades whose market classifies into an excluded context group.

    This is the single entry gate of the risk screen: run it over the tape
    BEFORE scoring, and sports, weather and crypto/market-price prints never
    reach events, wallets, fresh-wallet or timing clusters or the co-trading
    network. (The network needs it doubly: the crypto up/down markets are the
    busiest on the venue, so dozens of wallets touch the same handful of
    markets within minutes as a matter of course and produced the largest
    cluster on the screen purely by volume.)
    """

    if trades is None or trades.empty or "title" not in trades.columns:
        return trades if trades is not None else pd.DataFrame()
    category_map, context_map = _category_context_maps(market_categories)
    keys = _keys_with_ticker(trades)
    cache: dict[tuple[str, str, str], str] = {}
    groups = [
        cache.setdefault(
            (title, category_map.get(key, ""), _context_with_ticker(key, context_map)),
            classify_insider_context(title, category_map.get(key, ""), _context_with_ticker(key, context_map))[0],
        )
        for title, key in zip(trades["title"].astype(str), keys)
    ]
    mask = [group not in excluded for group in groups]
    return trades[pd.Series(mask, index=trades.index)].reset_index(drop=True)


def exclude_contexts(frame: pd.DataFrame, excluded: tuple[str, ...] = EXCLUDED_CONTEXTS) -> pd.DataFrame:
    """Drop scored rows (events or wallets) whose ``insider_context`` is excluded.

    Second gate for callers that score the full tape first and attach the
    context afterwards (``apply_category_context`` /
    ``apply_wallet_category_context``): the same tuple as
    ``filter_insider_prone_trades`` so the two never disagree.
    """

    if frame is None or frame.empty or "insider_context" not in frame.columns:
        return frame
    return frame[~frame["insider_context"].isin(excluded)].reset_index(drop=True)


def dominant_context_map(trades: pd.DataFrame, market_categories: pd.DataFrame | None = None) -> dict[str, str]:
    """Map wallet (lowercase) -> dominant insider-context group of its flow, weighted by notional."""

    if trades is None or trades.empty or not {"wallet", "title"}.issubset(trades.columns):
        return {}
    df = trades.copy()
    df["wallet"] = df["wallet"].astype(str).str.lower().str.strip()
    df = df[identified_wallets(df["wallet"])]
    if df.empty:
        return {}
    category_map, context_map = _category_context_maps(market_categories)
    title_groups: dict[tuple[str, str, str], str] = {}
    keys = _keys_with_ticker(df)
    df["_group"] = [
        title_groups.setdefault(
            (title, category_map.get(key, ""), _context_with_ticker(key, context_map)),
            classify_insider_context(title, category_map.get(key, ""), _context_with_ticker(key, context_map))[0],
        )
        for title, key in zip(df["title"].astype(str), keys)
    ]
    df["_notional"] = numeric_col(df, "notional").clip(lower=0.0)
    weighted = df.groupby(["wallet", "_group"])["_notional"].sum().reset_index()
    dominant = weighted.sort_values("_notional", ascending=False).drop_duplicates(subset=["wallet"], keep="first")
    return dict(zip(dominant["wallet"], dominant["_group"]))


def coordinated_clusters(
    trades: pd.DataFrame,
    *,
    window_minutes: float = 30.0,
    min_wallets: int = 3,
) -> pd.DataFrame:
    """Per market: most distinct wallets hitting the same side within a tight time window.

    Public cluster exposés describe wallets that trade within minutes of each
    other on the same side — this is the tape-level approximation of that
    pattern. Returns: title, coordinated_wallets, coordinated_outcome,
    coordinated_span_minutes, coordinated_notional.
    """

    columns = ["platform", "title", "coordinated_wallets", "coordinated_outcome", "coordinated_span_minutes", "coordinated_notional"]
    if trades is None or trades.empty or not {"wallet", "title", "time"}.issubset(trades.columns):
        return pd.DataFrame(columns=columns)
    df = trades.copy()
    df["wallet"] = df["wallet"].astype(str).str.lower().str.strip()
    df = df[identified_wallets(df["wallet"])]
    df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
    df = df.dropna(subset=["time"])
    if df.empty:
        return pd.DataFrame(columns=columns)
    df["platform"] = df.get("platform", pd.Series("", index=df.index)).fillna("").astype(str)
    df["outcome_label"] = df.get("outcome", pd.Series("", index=df.index)).astype(str).str.upper().str.strip()
    df["notional"] = numeric_col(df, "notional")
    window = pd.Timedelta(minutes=float(window_minutes))
    rows: list[dict[str, Any]] = []
    for (platform, title, outcome), group in df.groupby(["platform", "title", "outcome_label"], dropna=False):
        events = group.sort_values("time")[["time", "wallet", "notional"]].to_records(index=False)
        if len(events) < min_wallets:
            continue
        best_count = 0
        best_span = 0.0
        best_notional = 0.0
        left = 0
        for right in range(len(events)):
            while events[right][0] - events[left][0] > window:
                left += 1
            in_window = events[left : right + 1]
            wallets = {record[1] for record in in_window}
            if len(wallets) > best_count:
                best_count = len(wallets)
                best_span = (events[right][0] - events[left][0]).total_seconds() / 60
                best_notional = float(sum(record[2] for record in in_window))
        if best_count >= min_wallets:
            rows.append(
                {
                    "platform": str(platform),
                    "title": str(title),
                    "coordinated_wallets": int(best_count),
                    "coordinated_outcome": str(outcome),
                    "coordinated_span_minutes": round(best_span, 1),
                    "coordinated_notional": best_notional,
                }
            )
    if not rows:
        return pd.DataFrame(columns=columns)
    result = pd.DataFrame(rows).sort_values(["coordinated_wallets", "coordinated_notional"], ascending=False)
    return result.drop_duplicates(subset=["platform", "title"], keep="first").reset_index(drop=True)


def apply_coordination_bonus(event_risk: pd.DataFrame, clusters: pd.DataFrame, max_bonus: float = 10.0) -> pd.DataFrame:
    """Bump event scores where several wallets hit the same side within minutes."""

    if event_risk is None or event_risk.empty or clusters is None or clusters.empty:
        return event_risk
    merge_keys = ["platform", "title"] if "platform" in event_risk.columns and "platform" in clusters.columns else ["title"]
    enriched = event_risk.merge(clusters.drop(columns=[c for c in ("platform",) if c not in merge_keys and c in clusters.columns]), on=merge_keys, how="left")
    enriched["coordinated_wallets"] = pd.to_numeric(enriched.get("coordinated_wallets"), errors="coerce").fillna(0).astype(int)
    has_cluster = enriched["coordinated_wallets"] >= 3
    bonus = (enriched["coordinated_wallets"].clip(upper=5) * (max_bonus / 5.0)).where(has_cluster, 0.0)
    # The base event score already pays for the same timing artifact via
    # cluster_score (+10, flag "multi-wallet burst") and burst_score — halve
    # this bonus where that flag is present to avoid triple-counting one burst.
    if "event_insider_flags" in enriched.columns:
        already_bursty = enriched["event_insider_flags"].fillna("").astype(str).str.contains("multi-wallet burst")
        bonus = bonus.where(~already_bursty, bonus / 2.0)
    enriched["component_coordination"] = bonus.round(1)
    enriched["event_insider_score"] = (numeric_col(enriched, "event_insider_score") + bonus).clip(0, 100).round(0)
    enriched["event_insider_level"] = enriched["event_insider_score"].map(risk_level)
    if "event_insider_flags" in enriched:
        for idx in enriched.index[has_cluster]:
            count = int(enriched.at[idx, "coordinated_wallets"])
            span = float(enriched.at[idx, "coordinated_span_minutes"] or 0.0)
            outcome = str(enriched.at[idx, "coordinated_outcome"] or "").strip()
            label = f"{count} wallets within {span:.0f}min on {outcome}" if outcome else f"{count} wallets within {span:.0f}min"
            enriched.at[idx, "event_insider_flags"] = _append_flag(enriched.at[idx, "event_insider_flags"], label)
    return enriched


def co_trading_network(
    trades: pd.DataFrame,
    *,
    window_minutes: float | None = None,
    min_shared: int = 2,
    max_wallets: int = 200,
    min_pair_notional: float = 0.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build the co-trading graph and its communities from the whale tape.

    Edge rule (the pattern public cluster trackers describe): two wallets are
    connected when they took the same side of at least ``min_shared`` markets —
    optionally only counting hits that landed within ``window_minutes`` of each
    other. Communities come from Louvain (weight = shared markets), which
    separates tight syndicates from incidental co-movers better than plain
    connected components; if networkx is unavailable, components are the
    fallback.

    A raw count of shared markets is not evidence on its own: two wallets that
    each touch half the board meet everywhere by arithmetic. Every edge
    therefore carries ``expected_shared`` — how many hits the pair would share
    if each had picked its markets independently, ``m_a * m_b / M`` over the
    same market-and-side universe — and ``lift``, observed over expected. A
    lift near 1 is the base rate of two busy wallets, not a syndicate. With a
    time window active the expectation ignores the window and so overstates it,
    which makes the reported lift the conservative end.

    Returns (nodes, edges):
    - nodes: wallet, cluster_id, cluster_size, shared_markets, volume, markets, trades
    - edges: wallet_a, wallet_b, shared_markets, pair_notional, expected_shared, lift
    """

    node_columns = ["wallet", "cluster_id", "cluster_size", "shared_markets", "volume", "markets", "trades"]
    edge_columns = ["wallet_a", "wallet_b", "shared_markets", "pair_notional",
                    "expected_shared", "lift"]
    empty = (pd.DataFrame(columns=node_columns), pd.DataFrame(columns=edge_columns))
    if trades is None or trades.empty or not {"wallet", "title"}.issubset(trades.columns):
        return empty
    df = trades.copy()
    df["wallet"] = df["wallet"].astype(str).str.lower().str.strip()
    df = df[identified_wallets(df["wallet"])]
    if df.empty:
        return empty
    df["outcome_label"] = df.get("outcome", pd.Series("", index=df.index)).astype(str).str.upper().str.strip()
    df["notional"] = numeric_col(df, "notional")
    by_size = df.groupby("wallet")["notional"].sum().sort_values(ascending=False)
    keep = set(by_size.head(int(max_wallets)).index)
    df = df[df["wallet"].isin(keep)]
    if df.empty:
        return empty

    use_window = window_minutes is not None and "time" in df.columns
    if use_window:
        df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
        df = df.dropna(subset=["time"])
        window = pd.Timedelta(minutes=float(window_minutes))

    pair_markets: dict[tuple[str, str], set[str]] = {}
    pair_notional: dict[tuple[str, str], float] = {}
    for (title, _outcome), group in df.groupby(["title", "outcome_label"], dropna=False):
        if use_window:
            records = group.sort_values("time")[["time", "wallet", "notional"]].to_records(index=False)
            left = 0
            # Which prints of this market a pair actually met over. Adding the
            # two notionals per co-print pair instead counted every print once
            # per partner print: three prints a side turned $12k of real flow
            # into $36k, which then cleared the "$10k paired notional" rung of
            # the rule ladder that the flow never reached.
            beteiligt: dict[tuple[str, str], set[int]] = {}
            for right in range(len(records)):
                while records[right][0] - records[left][0] > window:
                    left += 1
                for mid in range(left, right):
                    a, b = records[mid][1], records[right][1]
                    if a == b:
                        continue
                    key = (a, b) if a < b else (b, a)
                    pair_markets.setdefault(key, set()).add(str(title))
                    treffer = beteiligt.setdefault(key, set())
                    treffer.add(mid)
                    treffer.add(right)
            for key, treffer in beteiligt.items():
                pair_notional[key] = pair_notional.get(key, 0.0) + sum(
                    float(records[index][2]) for index in treffer)
        else:
            wallets_here = sorted(group.groupby("wallet")["notional"].sum().items())
            for i in range(len(wallets_here)):
                for j in range(i + 1, len(wallets_here)):
                    key = (wallets_here[i][0], wallets_here[j][0])
                    pair_markets.setdefault(key, set()).add(str(title))
                    pair_notional[key] = pair_notional.get(key, 0.0) + float(wallets_here[i][1]) + float(wallets_here[j][1])

    # Base rate of meeting at all: how many market-and-side columns each wallet
    # stands in, against how many columns the tape has. Without it an edge only
    # says "both are busy".
    spalten = df.drop_duplicates(subset=["wallet", "title", "outcome_label"])
    spalten_je_wallet = spalten.groupby("wallet").size().to_dict()
    universum = int(df.groupby(["title", "outcome_label"], dropna=False).ngroups)

    edge_rows = []
    for (a, b), markets in pair_markets.items():
        geteilt = len(markets)
        if geteilt < int(min_shared) or pair_notional.get((a, b), 0.0) < float(min_pair_notional):
            continue
        erwartet = (spalten_je_wallet.get(a, 0) * spalten_je_wallet.get(b, 0) / universum) if universum else 0.0
        edge_rows.append({
            "wallet_a": a,
            "wallet_b": b,
            "shared_markets": geteilt,
            "pair_notional": pair_notional.get((a, b), 0.0),
            "expected_shared": round(float(erwartet), 4),
            "lift": round(geteilt / erwartet, 3) if erwartet > 0 else float("nan"),
        })
    if not edge_rows:
        return empty
    edges = pd.DataFrame(edge_rows, columns=edge_columns)

    members: list[set[str]]
    if nx is not None:
        graph = nx.Graph()
        for row in edge_rows:
            # Dollar-weighted edges: strong-money pairs bind communities tighter
            # than weak-money pairs (falls back to shared-market count if $0).
            graph.add_edge(row["wallet_a"], row["wallet_b"], weight=float(row["pair_notional"]) or float(row["shared_markets"]))
        try:
            members = [set(community) for community in nx.community.louvain_communities(graph, weight="weight", seed=42)]
        except Exception:
            members = [set(component) for component in nx.connected_components(graph)]
    else:
        parent: dict[str, str] = {}

        def find(node: str) -> str:
            parent.setdefault(node, node)
            while parent[node] != node:
                parent[node] = parent[parent[node]]
                node = parent[node]
            return node

        for row in edge_rows:
            parent[find(row["wallet_a"])] = find(row["wallet_b"])
        grouped: dict[str, set[str]] = {}
        for node in parent:
            grouped.setdefault(find(node), set()).add(node)
        members = list(grouped.values())

    wallet_stats = df.groupby("wallet").agg(volume=("notional", "sum"), markets=("title", pd.Series.nunique), trades=("wallet", "size"))
    overlap: dict[str, int] = {}
    for row in edge_rows:
        overlap[row["wallet_a"]] = max(overlap.get(row["wallet_a"], 0), row["shared_markets"])
        overlap[row["wallet_b"]] = max(overlap.get(row["wallet_b"], 0), row["shared_markets"])

    communities = [community for community in members if len(community) >= 2]
    communities.sort(key=lambda community: -float(wallet_stats.loc[wallet_stats.index.isin(community), "volume"].sum()))
    node_rows = []
    for cluster_no, community in enumerate(communities, start=1):
        for wallet in sorted(community):
            stats = wallet_stats.loc[wallet] if wallet in wallet_stats.index else None
            node_rows.append(
                {
                    "wallet": wallet,
                    "cluster_id": cluster_no,
                    "cluster_size": len(community),
                    "shared_markets": overlap.get(wallet, 0),
                    "volume": float(stats["volume"]) if stats is not None else 0.0,
                    "markets": int(stats["markets"]) if stats is not None else 0,
                    "trades": int(stats["trades"]) if stats is not None else 0,
                }
            )
    if not node_rows:
        return empty
    nodes = pd.DataFrame(node_rows, columns=node_columns)
    keep_wallets = set(nodes["wallet"])
    edges = edges[edges["wallet_a"].isin(keep_wallets) & edges["wallet_b"].isin(keep_wallets)].reset_index(drop=True)
    return nodes, edges


def null_model_reference(
    trades: pd.DataFrame,
    *,
    runs: int = 2,
    seed: int = 42,
    **kwargs: Any,
) -> dict[str, Any]:
    """What the same edge rule finds after the wallet column is shuffled.

    The honest control for a cluster picture. Permuting which wallet made which
    print keeps every market's crowd size and the shape of the per-wallet
    activity, and destroys only who met whom. Whatever the rule still reports
    on that tape is what it reports on nothing.

    It reports plenty: on 60 wallets each picking 20 of 120 markets at random,
    the default rule (same side of at least two markets) links all 60 into six
    clusters over 926 edges. The number belongs next to the picture, not in a
    comment.

    Returns median wallets / edges / clusters / lift and the largest modularity
    seen, plus ``runs`` and ``regel_kwargs`` so the control is reproducible.
    """

    leer = {"runs": 0, "wallets": 0, "kanten": 0, "cluster": 0,
            "modularitaet": None, "lift_median": None, "regel_kwargs": dict(kwargs)}
    if trades is None or trades.empty or "wallet" not in trades.columns:
        return leer
    wallets: list[int] = []
    kanten: list[int] = []
    cluster: list[int] = []
    lifts: list[float] = []
    modularitaeten: list[float] = []
    for lauf in range(max(1, int(runs))):
        gemischt = trades.copy()
        gemischt["wallet"] = (
            gemischt["wallet"].sample(frac=1.0, random_state=seed + lauf).to_numpy()
        )
        nodes, edges = co_trading_network(gemischt, **kwargs)
        wallets.append(int(len(nodes)))
        kanten.append(int(len(edges)))
        cluster.append(int(nodes["cluster_id"].nunique()) if not nodes.empty else 0)
        if not edges.empty and "lift" in edges:
            werte = pd.to_numeric(edges["lift"], errors="coerce").dropna()
            if not werte.empty:
                lifts.append(float(werte.median()))
        wert = network_modularity(nodes, edges)
        if wert is not None:
            modularitaeten.append(float(wert))
    def mitte(werte: list[float]) -> float | None:
        return float(pd.Series(werte).median()) if werte else None

    return {
        "runs": max(1, int(runs)),
        "wallets": int(mitte(wallets) or 0),
        "kanten": int(mitte(kanten) or 0),
        "cluster": int(mitte(cluster) or 0),
        "modularitaet": round(max(modularitaeten), 3) if modularitaeten else None,
        "lift_median": round(mitte(lifts), 3) if lifts else None,
        "regel_kwargs": dict(kwargs),
    }


def network_modularity(nodes: pd.DataFrame, edges: pd.DataFrame) -> float | None:
    """Weighted modularity of the detected partition (>0.3 ≈ meaningful structure)."""

    if nx is None or nodes is None or nodes.empty or edges is None or edges.empty:
        return None
    graph = nx.Graph()
    for _, edge in edges.iterrows():
        graph.add_edge(edge["wallet_a"], edge["wallet_b"], weight=float(edge["pair_notional"]) or float(edge["shared_markets"]))
    communities: dict[Any, set[str]] = {}
    for _, node in nodes.iterrows():
        communities.setdefault(node["cluster_id"], set()).add(node["wallet"])
    partition = [members for members in communities.values() if members]
    covered = set().union(*partition) if partition else set()
    for orphan in set(graph.nodes) - covered:
        partition.append({orphan})
    try:
        return float(nx.community.modularity(graph, partition, weight="weight"))
    except Exception:
        return None


def _stable_fraction(text: str) -> float:
    """A value in [0, 1) derived from ``text``, identical in every process."""

    digest = hashlib.sha256(str(text).encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") / 2 ** 32


def cluster_layout(nodes: pd.DataFrame) -> pd.DataFrame:
    """Organic island layout: cluster centers on a golden-angle spiral, members on
    a ring around each center with deterministic radial jitter.

    Bigger clusters get bigger rings; the spiral keeps islands from overlapping
    without needing a force simulation.

    The jitter is derived from a SHA-256 digest of the wallet, not from the
    builtin ``hash``: string hashing is salted per interpreter process, so the
    same tape produced a different picture on every run, the exported figure
    never matched the page, and a figure in a written text could not be
    regenerated. The digest makes the layout reproducible for real.
    """

    if nodes is None or nodes.empty:
        return nodes
    placed = nodes.copy()
    placed["x"] = 0.0
    placed["y"] = 0.0
    sizes = placed.groupby("cluster_id")["wallet"].size().sort_values(ascending=False)
    cluster_ids = list(sizes.index)
    golden_angle = math.pi * (3.0 - math.sqrt(5.0))
    ring_radius = {cid: 1.4 + 0.55 * math.sqrt(int(sizes[cid])) for cid in cluster_ids}
    centers: dict[Any, tuple[float, float]] = {}
    spread = 0.0
    for index, cluster_id in enumerate(cluster_ids):
        if index == 0:
            centers[cluster_id] = (0.0, 0.0)
            spread = ring_radius[cluster_id]
            continue
        angle = index * golden_angle
        distance = spread + ring_radius[cluster_id] + 2.5 + 1.1 * math.sqrt(index)
        centers[cluster_id] = (distance * math.cos(angle), distance * math.sin(angle))
        spread = max(spread, 0.55 * distance)
    for cluster_id in cluster_ids:
        center_x, center_y = centers[cluster_id]
        member_index = placed.index[placed["cluster_id"] == cluster_id]
        count = len(member_index)
        radius = ring_radius[cluster_id]
        for position, node_idx in enumerate(member_index):
            angle = (2 * math.pi * position) / max(count, 1)
            wallet = str(placed.at[node_idx, "wallet"])
            jitter = 0.82 + 0.36 * (_stable_fraction(wallet))
            placed.at[node_idx, "x"] = center_x + radius * jitter * math.cos(angle)
            placed.at[node_idx, "y"] = center_y + radius * jitter * math.sin(angle)
    return placed


def cluster_story(
    cluster_nodes: pd.DataFrame,
    cluster_edges: pd.DataFrame,
    trades: pd.DataFrame,
    *,
    window_minutes: float | None = 5.0,
    min_shared: int = 2,
) -> dict[str, Any]:
    """Plain-language explanation of one cluster: what it is, why it clusters, how to read it.

    Returns {headline, pattern, reasons (list[str]), top_markets (list[str]), density}.
    """

    if cluster_nodes is None or cluster_nodes.empty:
        return {"headline": "", "pattern": "", "reasons": [], "top_markets": [], "density": 0.0}
    count = int(len(cluster_nodes))
    volume = float(numeric_col(cluster_nodes, "volume").sum())
    edge_count = int(len(cluster_edges)) if cluster_edges is not None else 0
    possible_edges = count * (count - 1) / 2 or 1
    density = edge_count / possible_edges
    shared_avg = float(numeric_col(cluster_edges, "shared_markets").mean()) if cluster_edges is not None and not cluster_edges.empty else 0.0
    shared_max = float(numeric_col(cluster_edges, "shared_markets").max()) if cluster_edges is not None and not cluster_edges.empty else 0.0

    members = set(cluster_nodes["wallet"].astype(str))
    top_markets: list[str] = []
    markets_struct: list[dict[str, Any]] = []
    distinct_markets = 0
    if trades is not None and not trades.empty and {"wallet", "title"}.issubset(trades.columns):
        flow = trades.copy()
        flow["_wallet_key"] = flow["wallet"].astype(str).str.lower().str.strip()
        flow = flow[flow["_wallet_key"].isin(members)]
        if not flow.empty:
            flow["notional"] = numeric_col(flow, "notional")
            distinct_markets = int(flow["title"].nunique())
            top = flow.groupby("title")["notional"].sum().sort_values(ascending=False).head(3)
            top_markets = [f"{str(title)[:70]} ({money(value)})" for title, value in top.items()]
            # Structured for the cluster card: title and label separately, so
            # the page can lay them out instead of parsing a sentence.
            markets_struct = [{"title": str(title)[:80], "label": money(value)} for title, value in top.items()]

    window_text = f"within {window_minutes:.0f} minutes of each other" if window_minutes else "in the sampled tape"
    reasons = [
        f"Every line connects two wallets that bought the same side of at least {int(min_shared)} shared markets {window_text} — "
        f"on average {shared_avg:.1f} shared markets per linked pair (max {shared_max:.0f}).",
    ]
    if density >= 0.5:
        pattern = "Tight clique"
        reasons.append(
            f"{edge_count} of {possible_edges:.0f} possible pairs are linked ({density:.0%} density): the same wallets move together "
            "again and again — the strongest coordination pattern (syndicate-like or one operator splitting orders)."
        )
    elif density >= 0.15:
        pattern = "Connected group"
        reasons.append(
            f"{edge_count} links across {count} wallets ({density:.0%} density): a core of wallets co-moves repeatedly while others "
            "attach loosely — consistent with a coordinated core plus followers."
        )
    else:
        pattern = "Loose chain"
        reasons.append(
            f"Only {edge_count} links across {count} wallets ({density:.0%} density): wallets are chained through a few common trades — "
            "this can be herd behavior around hot markets rather than real coordination. Weakest evidence tier."
        )
    if distinct_markets:
        reasons.append(
            f"The flow concentrates in {distinct_markets} distinct markets; the heaviest shared bets are listed below — "
            "the narrower and more obscure these markets, the harder the pattern is to explain as coincidence."
        )
    headline = f"{count} wallets · {money(volume)} combined whale volume · {pattern.lower()}"
    return {"headline": headline, "pattern": pattern, "reasons": reasons, "top_markets": top_markets, "markets": markets_struct, "density": density}


def wallet_co_trading_clusters(trades: pd.DataFrame, *, min_shared: int = 2, max_wallets: int = 200) -> pd.DataFrame:
    """Legacy simple view of the co-trading communities (no timing constraint).

    Returns wallet -> cluster_id, cluster_size, shared_markets; kept as the
    stable surface for the wallet-score bonus.
    """

    nodes, _edges = co_trading_network(trades, window_minutes=None, min_shared=min_shared, max_wallets=max_wallets)
    if nodes.empty:
        return pd.DataFrame(columns=["wallet", "cluster_id", "cluster_size", "shared_markets"])
    return nodes[["wallet", "cluster_id", "cluster_size", "shared_markets"]].copy()


def apply_cluster_bonus(wallet_risk: pd.DataFrame, clusters: pd.DataFrame, bonus: float = 5.0) -> pd.DataFrame:
    """Bump wallet scores for cluster members and flag them as possibly linked."""

    if wallet_risk is None or wallet_risk.empty or clusters is None or clusters.empty:
        return wallet_risk
    enriched = wallet_risk.copy()
    enriched["_wallet_key"] = enriched["wallet"].astype(str).str.lower().str.strip()
    enriched = enriched.merge(clusters.rename(columns={"wallet": "_wallet_key"}), on="_wallet_key", how="left")
    member = enriched["cluster_id"].notna()
    enriched.loc[member, "wallet_insider_score"] = (
        numeric_col(enriched.loc[member], "wallet_insider_score") + float(bonus)
    ).clip(0, 100).round(0)
    enriched["wallet_insider_level"] = enriched["wallet_insider_score"].map(risk_level)
    if "wallet_insider_flags" in enriched:
        for idx in enriched.index[member]:
            size = int(enriched.at[idx, "cluster_size"])
            enriched.at[idx, "wallet_insider_flags"] = _append_flag(
                enriched.at[idx, "wallet_insider_flags"], f"moves with {size - 1} other wallet{'s' if size > 2 else ''}"
            )
    return enriched.drop(columns=["_wallet_key"], errors="ignore")


def apply_category_context(event_risk: pd.DataFrame, market_categories: pd.DataFrame | None = None) -> pd.DataFrame:
    """Scale event scores by insider plausibility of the market category.

    Adds columns: insider_context, context_multiplier, context_note,
    event_score_raw (pre-context score). Re-sorts by the adjusted score.
    """

    if event_risk is None or event_risk.empty:
        return event_risk
    enriched = event_risk.copy()
    category_map, context_map = _category_context_maps(market_categories)
    contexts = [
        classify_insider_context(
            row.get("title", ""),
            category_map.get(str(row.get("market_key", "")), ""),
            _context_with_ticker(_row_key(row), context_map),
        )
        for _, row in enriched.iterrows()
    ]
    enriched["insider_context"] = [group for group, _, _ in contexts]
    enriched["context_multiplier"] = [multiplier for _, multiplier, _ in contexts]
    enriched["context_note"] = [note for _, _, note in contexts]
    enriched["event_score_raw"] = numeric_col(enriched, "event_insider_score")
    enriched["event_insider_score"] = (enriched["event_score_raw"] * enriched["context_multiplier"]).clip(0, 100).round(0)
    enriched["event_insider_level"] = enriched["event_insider_score"].map(risk_level)
    return enriched.sort_values(["event_insider_score", "notional"], ascending=False).reset_index(drop=True)


def apply_wallet_category_context(
    wallet_risk: pd.DataFrame,
    trades: pd.DataFrame,
    market_categories: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Scale wallet scores by the notional-weighted insider plausibility of their flow.

    A wallet whose whale flow sits mostly in sports/crypto/weather markets is
    damped here and then dropped by ``exclude_contexts`` (high roller, not
    insider); flow concentrated in insider-prone categories keeps or gains
    weight. Adds insider_context (dominant group), context_multiplier
    (weighted) and wallet_score_raw.
    """

    if wallet_risk is None or wallet_risk.empty or trades is None or trades.empty:
        return wallet_risk
    df = trades.copy()
    df["wallet"] = df["wallet"].astype(str).str.lower().str.strip()
    df = df[identified_wallets(df["wallet"])]
    if df.empty:
        return wallet_risk
    category_map, context_map = _category_context_maps(market_categories)
    contexts = [
        classify_insider_context(
            row.get("title", ""),
            category_map.get(str(row.get("market_key", "")), ""),
            _context_with_ticker(_row_key(row), context_map),
        )
        for _, row in df.iterrows()
    ]
    df["_group"] = [group for group, _, _ in contexts]
    df["_multiplier"] = [multiplier for _, multiplier, _ in contexts]
    df["_notional"] = numeric_col(df, "notional").clip(lower=0.0)
    df["_weighted"] = df["_multiplier"] * df["_notional"]
    per_wallet = df.groupby("wallet").agg(_weighted=("_weighted", "sum"), _notional=("_notional", "sum"))
    per_wallet["context_multiplier"] = (per_wallet["_weighted"] / per_wallet["_notional"].replace({0: pd.NA})).fillna(1.0)
    dominant = (
        df.groupby(["wallet", "_group"])["_notional"].sum().reset_index().sort_values("_notional", ascending=False).drop_duplicates(subset=["wallet"], keep="first")
    )
    per_wallet = per_wallet.merge(dominant.rename(columns={"_group": "insider_context"})[["wallet", "insider_context"]], on="wallet", how="left")

    enriched = wallet_risk.copy()
    enriched["_wallet_key"] = enriched["wallet"].astype(str).str.lower().str.strip()
    enriched = enriched.merge(
        per_wallet.rename(columns={"wallet": "_wallet_key"})[["_wallet_key", "context_multiplier", "insider_context"]],
        on="_wallet_key",
        how="left",
    )
    enriched["context_multiplier"] = pd.to_numeric(enriched["context_multiplier"], errors="coerce").fillna(1.0)
    enriched["insider_context"] = enriched["insider_context"].fillna(CONTEXT_GENERAL)
    enriched["wallet_score_raw"] = numeric_col(enriched, "wallet_insider_score")
    enriched["wallet_insider_score"] = (enriched["wallet_score_raw"] * enriched["context_multiplier"]).clip(0, 100).round(0)
    enriched["wallet_insider_level"] = enriched["wallet_insider_score"].map(risk_level)
    if "wallet_insider_flags" in enriched:
        damped = enriched["context_multiplier"] <= 0.8
        boosted = enriched["context_multiplier"] >= 1.1
        for idx in enriched.index[damped]:
            group = str(enriched.at[idx, "insider_context"])
            enriched.at[idx, "wallet_insider_flags"] = _append_flag(enriched.at[idx, "wallet_insider_flags"], f"flow mostly in {group.lower()}")
        for idx in enriched.index[boosted]:
            enriched.at[idx, "wallet_insider_flags"] = _append_flag(enriched.at[idx, "wallet_insider_flags"], "insider-prone categories")
    return (
        enriched.drop(columns=["_wallet_key"], errors="ignore")
        .sort_values(["wallet_insider_score", "notional"], ascending=False)
        .reset_index(drop=True)
    )


def apply_account_age_bonus(
    wallet_risk: pd.DataFrame,
    account_stats: pd.DataFrame,
    *,
    max_age_days: float = 14.0,
    bonus: float = 10.0,
) -> pd.DataFrame:
    """Bump wallet scores where the real on-chain account age is young; add a flag.

    Nur ein gemessenes Alter zaehlt. Kam die Aktivitaet einer Wallet nicht
    vollstaendig an -- abgebrochene Seitenschleife, oder jede Seite voll --,
    dann ist der aelteste gelesene Eintrag eine untere Schranke fuer das
    Alter und kein Kontostart. Auf so eine Schranke zehn Punkte zu addieren
    und "new account (3d)" an eine jahrealte Adresse zu schreiben, waren zwei
    erfundene Aussagen aus einer fehlenden. ``account_age_state`` trennt das;
    fehlt die Spalte, gilt die Angabe wie bisher als gemessen.
    """

    if wallet_risk is None or wallet_risk.empty:
        return wallet_risk
    if account_stats is None or account_stats.empty or "wallet" not in account_stats or "account_age_days" not in account_stats:
        return wallet_risk
    spalten = ["wallet", "account_age_days"] + (["account_age_state"] if "account_age_state" in account_stats else [])
    ages = account_stats[spalten].copy()
    ages["wallet"] = ages["wallet"].astype(str).str.lower().str.strip()
    ages["account_age_days"] = pd.to_numeric(ages["account_age_days"], errors="coerce")
    if "account_age_state" in ages:
        ungemessen = ages["account_age_state"].astype(str) != "measured"
        ages.loc[ungemessen, "account_age_days"] = pd.NA
        ages = ages.drop(columns=["account_age_state"])
    enriched = wallet_risk.copy()
    enriched["_wallet_key"] = enriched["wallet"].astype(str).str.lower().str.strip()
    enriched = enriched.merge(ages.rename(columns={"wallet": "_wallet_key"}), on="_wallet_key", how="left")
    young = enriched["account_age_days"].notna() & (enriched["account_age_days"] <= float(max_age_days))
    enriched["account_age_days"] = enriched["account_age_days"]
    enriched.loc[young, "wallet_insider_score"] = (
        numeric_col(enriched.loc[young], "wallet_insider_score") + float(bonus)
    ).clip(0, 100).round(0)
    enriched["wallet_insider_level"] = enriched["wallet_insider_score"].map(risk_level)
    if "wallet_insider_flags" in enriched:
        for idx in enriched.index[young]:
            age = float(enriched.at[idx, "account_age_days"])
            enriched.at[idx, "wallet_insider_flags"] = _append_flag(
                enriched.at[idx, "wallet_insider_flags"], f"new account ({age:.0f}d)"
            )
    return enriched.drop(columns=["_wallet_key"], errors="ignore")


#: Unter so vielen gesampelten Prints sind Verteilungs-Aussagen (Konzentration,
#: Einseitigkeit, Anteile) trivial -- ein einzelner Trade ist immer "100%".
EVENT_MIN_DISTRIBUTION_PRINTS = 3


def event_story(row: pd.Series) -> str:
    """One-line plain-language summary of why an event looks suspicious."""

    notional = float(row.get("notional", 0.0) or 0.0)
    wallets = int(row.get("unique_wallets", 0) or 0)
    trades = int(row.get("trades", 0) or 0)
    sample_ok = trades >= EVENT_MIN_DISTRIBUTION_PRINTS
    parts: list[str] = []
    long_odds_share = float(row.get("long_odds_share", 0.0) or 0.0)
    if long_odds_share >= 0.4:
        parts.append(
            f"{pct(long_odds_share)} of it at long odds" if sample_ok else "placed at long odds"
        )
    late_share = float(row.get("late_share", 0.0) or 0.0)
    if late_share >= 0.4:
        parts.append(
            "heavy flow close to resolution" if sample_ok else "placed close to resolution"
        )
    top_wallet_share = float(row.get("top_wallet_share", 0.0) or 0.0)
    if sample_ok and top_wallet_share >= 0.5:
        parts.append(f"one wallet drives {pct(top_wallet_share)}")
    fresh = int(row.get("fresh_wallets", 0) or 0)
    if fresh >= 2:
        outcome = str(row.get("fresh_outcome", "") or "").strip()
        parts.append(f"{fresh} fresh wallets on {outcome}" if outcome else f"{fresh} fresh wallets on the same side")
    first_trade_wallets = int(row.get("first_trade_wallets", 0) or 0)
    if first_trade_wallets >= 1:
        youngest = float(row.get("first_trade_youngest_days", 0.0) or 0.0)
        who = "one wallet" if first_trade_wallets == 1 else f"{first_trade_wallets} wallets"
        parts.append(
            f"{money(float(row.get('first_trade_notional', 0.0) or 0.0))} from {who} whose first trade was "
            f"{_days_label(youngest)} before"
        )
    direction_share = float(row.get("event_directional_share", 0.0) or 0.0)
    direction_label = str(row.get("event_directional_label", "") or "").strip()
    if sample_ok and direction_share >= 0.8 and direction_label:
        parts.append(f"{pct(direction_share)} of flow is {direction_label}")
    price_move = float(row.get("price_move", 0.0) or 0.0)
    if price_move >= 0.03:
        parts.append(f"price moved {price_move * 100:+.0f}c behind the buys")
    if not sample_ok and trades > 0:
        parts.append("too few sampled prints to judge the flow pattern")
    print_teil = (
        f"{trades} sampled print{'s' if trades != 1 else ''}" if trades > 0 else "sampled prints"
    )
    if wallets > 0:
        base = f"{money(notional)} whale flow from {wallets} wallet{'s' if wallets != 1 else ''} ({print_teil})"
    else:
        base = f"{money(notional)} whale flow ({print_teil}; wallet identities not public on this venue)"
    return f"{base} — {'; '.join(parts)}." if parts else f"{base}; no single dominant pattern."


def wallets_for_event(trades: pd.DataFrame, wallet_risk: pd.DataFrame, title: str) -> pd.DataFrame:
    """Wallet risk rows for every wallet that traded the given market in the tape."""

    if trades is None or trades.empty or wallet_risk is None or wallet_risk.empty:
        return pd.DataFrame()
    involved = (
        trades[trades.get("title", pd.Series("", index=trades.index)).astype(str).eq(str(title))]["wallet"]
        .astype(str)
        .str.lower()
        .str.strip()
    )
    involved = {wallet for wallet in involved if wallet and wallet != "nan"}
    if not involved:
        return pd.DataFrame()
    subset = wallet_risk[wallet_risk["wallet"].astype(str).str.lower().str.strip().isin(involved)]
    return subset.sort_values("wallet_insider_score", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Flow details per event: which side, at what price, from whom, when.
#
# The base event score says "something is off here"; the owner reviewing a
# flag afterwards needs to know WHICH side the money went to, at what price,
# from which wallets and in which minutes — the market link and the price
# afterwards decide whether the flag meant anything. Everything below is a
# pure aggregation of the same trades frame the scores came from.
# ---------------------------------------------------------------------------

#: Order of the side buckets and their plain labels. "buys" of an outcome are
#: exposure to that outcome; sells are the taker leaving it.
SIDE_BUCKETS = (
    ("buy_yes", "YES buys"),
    ("buy_no", "NO buys"),
    ("sell_yes", "YES sells"),
    ("sell_no", "NO sells"),
)

#: Wallet placeholders of venues that publish no identities.
_NO_WALLET = {"", "nan", "none", "not public"}


def _side_bucket(side: Any, outcome: Any) -> str:
    """Map a print to buy_yes / buy_no / sell_yes / sell_no.

    Polymarket carries side BUY/SELL and outcome Yes/No. Kalshi carries the
    taker side (yes/no) as ``side`` and the same as ``outcome``: the taker
    took that outcome, i.e. bought it.
    """

    side_text = str(side or "").strip().upper()
    outcome_text = str(outcome or "").strip().upper()
    if outcome_text not in ("YES", "NO"):
        outcome_text = side_text if side_text in ("YES", "NO") else ""
    if not outcome_text:
        return ""
    verb = "sell" if side_text == "SELL" else "buy"
    return f"{verb}_{outcome_text.lower()}"


def _prep_flow_frame(trades: pd.DataFrame) -> pd.DataFrame:
    df = trades.copy()
    df["platform"] = df.get("platform", pd.Series("", index=df.index)).fillna("").astype(str)
    df["title"] = df.get("title", pd.Series("", index=df.index)).fillna("").astype(str)
    df = df[df["title"].str.strip().ne("")]
    if df.empty:
        return df
    df["_wallet"] = df.get("wallet", pd.Series("", index=df.index)).fillna("").astype(str).str.lower().str.strip()
    df.loc[df["_wallet"].isin(_NO_WALLET), "_wallet"] = ""
    df["_notional"] = numeric_col(df, "notional").clip(lower=0.0)
    df["_price"] = pd.to_numeric(df.get("price", pd.Series(dtype=float)), errors="coerce")
    df["_time"] = pd.to_datetime(df.get("time", pd.Series(pd.NaT, index=df.index)), utc=True, errors="coerce")
    sides = df.get("side", pd.Series("", index=df.index))
    outcomes = df.get("outcome", pd.Series("", index=df.index))
    df["_bucket"] = [_side_bucket(s, o) for s, o in zip(sides, outcomes)]
    df["_bucket_label"] = df["_bucket"].map(dict(SIDE_BUCKETS)).fillna("")
    return df


def event_flow_details(
    trades: pd.DataFrame,
    *,
    top_n: int = 3,
    fresh_max_trades: int = 2,
    whale_threshold: float | None = None,
    origins: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """Per (platform, title): side split, dominant side, prices, window, top wallets, link.

    Columns: platform, title, side_buy_yes, side_buy_no, side_sell_yes,
    side_sell_no (notional per bucket), side (label of the dominant bucket,
    e.g. "NO buys"), side_notional, side_share, price_outcome (YES/NO — the
    outcome the prices refer to), price_first, price_last, price_min,
    price_max (over the dominant-side prints, in that outcome's price),
    first_print, last_print (UTC), window_minutes, top_wallets (list of
    {wallet, notional, share, side, fresh}), url, slug, token_id (asset of the
    latest dominant-side print, Polymarket only).

    ``fresh`` per wallet uses the same tape-relative proxy as
    :func:`fresh_wallet_clusters` (few prints in the whole tape, whale-sized
    total) and is only computed when ``whale_threshold`` is given; otherwise
    it is ``None`` — the payload says "not computed" rather than "no".
    ``first_trade_days`` per wallet is the measured age of the wallet's first
    trade on the venue at its last print here (``origins``, see
    app/wallet_origin.py); None when nobody measured it, with
    ``first_trade_state`` saying so.
    """

    columns = [
        "platform", "title", "side_buy_yes", "side_buy_no", "side_sell_yes", "side_sell_no",
        "side", "side_notional", "side_share", "price_outcome", "price_first", "price_last",
        "price_min", "price_max", "first_print", "last_print", "window_minutes", "print_offsets",
        "top_wallets", "url", "slug", "token_id",
    ]
    if trades is None or trades.empty or "title" not in trades.columns:
        return pd.DataFrame(columns=columns)
    df = _prep_flow_frame(trades)
    if df.empty:
        return pd.DataFrame(columns=columns)

    origin_lookup = _origin_lookup(origins)
    fresh_set: set[str] | None = None
    if whale_threshold is not None:
        with_wallet = df[identified_wallets(df["_wallet"])]
        if not with_wallet.empty:
            per_wallet = with_wallet.groupby("_wallet").agg(n=("_wallet", "size"), total=("_notional", "sum"))
            fresh_set = set(per_wallet[(per_wallet["n"] <= int(fresh_max_trades)) & (per_wallet["total"] >= float(whale_threshold))].index)
        else:
            fresh_set = set()

    rows: list[dict[str, Any]] = []
    for (platform, title), group in df.groupby(["platform", "title"], dropna=False, sort=False):
        total = float(group["_notional"].sum())
        split = group.groupby("_bucket")["_notional"].sum()
        buckets = {key: float(split.get(key, 0.0)) for key, _ in SIDE_BUCKETS}
        dominant_key = ""
        dominant_value = 0.0
        for key, _ in SIDE_BUCKETS:
            if buckets[key] > dominant_value:
                dominant_key, dominant_value = key, buckets[key]
        side_label = dict(SIDE_BUCKETS).get(dominant_key, "")
        dominant = group[group["_bucket"].eq(dominant_key)] if dominant_key else group.iloc[0:0]
        priced = dominant[dominant["_price"].notna() & (dominant["_price"] > 0)].sort_values("_time")
        price_first = float(priced["_price"].iloc[0]) if not priced.empty else None
        price_last = float(priced["_price"].iloc[-1]) if not priced.empty else None
        price_min = float(priced["_price"].min()) if not priced.empty else None
        price_max = float(priced["_price"].max()) if not priced.empty else None
        price_outcome = dominant_key.split("_")[-1].upper() if dominant_key else ""

        times = group["_time"].dropna()
        first_print = times.min() if not times.empty else pd.NaT
        last_print = times.max() if not times.empty else pd.NaT
        window_minutes = float((last_print - first_print).total_seconds() / 60.0) if not times.empty else None
        # Position jedes Prints im Fenster (0..1), chronologisch: die Karte
        # zeichnet daraus die Tick-Leiste ("6 Prints in den ersten Minuten")
        # statt Positionen zu erfinden. Bei Fenster 0 liegen alle auf 0.
        print_offsets: list[float] = []
        if not times.empty:
            span_seconds = float((last_print - first_print).total_seconds())
            ordered = times.sort_values().head(80)
            if span_seconds > 0:
                print_offsets = [round(float((t - first_print).total_seconds() / span_seconds), 4) for t in ordered]
            else:
                print_offsets = [0.0] * int(len(ordered))

        top_wallets: list[dict[str, Any]] = []
        with_wallet = group[identified_wallets(group["_wallet"])]
        if not with_wallet.empty:
            per_wallet = with_wallet.groupby("_wallet")["_notional"].sum().sort_values(ascending=False).head(int(top_n))
            for wallet, value in per_wallet.items():
                own = with_wallet[with_wallet["_wallet"].eq(wallet)]
                own_split = own.groupby("_bucket_label")["_notional"].sum().sort_values(ascending=False)
                own_side = str(own_split.index[0]) if not own_split.empty and str(own_split.index[0]) else ""
                origin = origin_lookup.get(str(wallet))
                first_trade_days: float | None = None
                first_trade_state = ORIGIN_UNMEASURED if origin is None else origin[1]
                if origin is not None and origin[1] == ORIGIN_MEASURED and origin[0] is not None:
                    last_time = own["_time"].max()
                    if pd.notna(last_time):
                        first_trade_days = max(0.0, (last_time.timestamp() - float(origin[0])) / 86_400.0)
                top_wallets.append({
                    "wallet": str(wallet),
                    "notional": float(value),
                    "share": float(value / total) if total > 0 else 0.0,
                    "side": own_side,
                    "fresh": (wallet in fresh_set) if fresh_set is not None else None,
                    "first_trade_days": round(first_trade_days, 2) if first_trade_days is not None else None,
                    "first_trade_state": first_trade_state,
                })

        url = ""
        slug = ""
        if "url" in group.columns:
            urls = group["url"].dropna().astype(str)
            urls = urls[urls.str.strip().ne("") & urls.str.lower().ne("nan")]
            url = str(urls.iloc[0]) if not urls.empty else ""
        if "slug" in group.columns:
            slugs = group["slug"].dropna().astype(str)
            slugs = slugs[slugs.str.strip().ne("") & slugs.str.lower().ne("nan")]
            slug = str(slugs.iloc[0]) if not slugs.empty else ""
        token_id = ""
        if "asset" in dominant.columns and not dominant.empty:
            assets = dominant.sort_values("_time", ascending=False)["asset"].dropna().astype(str)
            assets = assets[assets.str.strip().ne("") & assets.str.lower().ne("nan")]
            token_id = str(assets.iloc[0]) if not assets.empty else ""

        rows.append({
            "platform": str(platform),
            "title": str(title),
            "side_buy_yes": buckets["buy_yes"],
            "side_buy_no": buckets["buy_no"],
            "side_sell_yes": buckets["sell_yes"],
            "side_sell_no": buckets["sell_no"],
            "side": side_label,
            "side_notional": dominant_value,
            "side_share": (dominant_value / total) if total > 0 else 0.0,
            "price_outcome": price_outcome,
            "price_first": price_first,
            "price_last": price_last,
            "price_min": price_min,
            "price_max": price_max,
            "first_print": first_print,
            "last_print": last_print,
            "window_minutes": window_minutes,
            "print_offsets": print_offsets,
            "top_wallets": top_wallets,
            "url": url,
            "slug": slug,
            "token_id": token_id,
        })
    return pd.DataFrame(rows, columns=columns)


def enrich_event_flow(event_risk: pd.DataFrame, trades: pd.DataFrame, **kwargs: Any) -> pd.DataFrame:
    """Attach :func:`event_flow_details` to the scored event frame (by platform + title).

    The details win over same-named base columns (the base ``side_share`` is
    the BUY-vs-SELL share, the flow ``side_share`` the share of the dominant
    YES/NO bucket — the latter is what the card and the log mean by "side").
    Only ``url`` keeps the base value when the details carry none.
    """

    if event_risk is None or event_risk.empty:
        return event_risk
    details = event_flow_details(trades, **kwargs)
    if details.empty:
        return event_risk
    merge_keys = ["platform", "title"] if "platform" in event_risk.columns else ["title"]
    if "platform" not in event_risk.columns:
        details = details.drop(columns=["platform"])
    overlap = [c for c in details.columns if c in event_risk.columns and c not in merge_keys]
    enriched = event_risk.merge(details.rename(columns={c: f"{c}__flow" for c in overlap}), on=merge_keys, how="left")
    for column in overlap:
        flow_col = f"{column}__flow"
        base = enriched[column]
        flow = enriched[flow_col]
        if column == "url":
            base_empty = base.isna() | base.astype(str).str.strip().eq("") | base.astype(str).str.lower().eq("nan")
            enriched[column] = base.where(~base_empty, flow)
        else:
            enriched[column] = flow.where(flow.notna(), base)
        enriched = enriched.drop(columns=[flow_col])
    return enriched


#: Score components an event row can carry, with label and cap. The base
#: components come from ``whale_event_risk_scores`` (component_* columns),
#: the bonuses from apply_fresh_wallet_bonus / apply_coordination_bonus.
def short_wallet(value: Any) -> str:
    text = str(value or "")
    return text[:6] + "…" + text[-4:] if len(text) > 12 else text


EVENT_COMPONENTS = (
    # key, label on the card, cap, what the component measures (one line)
    ("component_notional", "Size of the flow", 15.0, "dollars traded in this market in the window"),
    ("component_largest", "Biggest single print", 10.0, "the largest one trade"),
    ("component_long_odds", "Long-odds bet", 10.0, "money placed at 35¢ or below, 20¢ and under in full"),
    ("component_concentration", "One wallet dominates", 15.0, "share of the flow done by the top wallet"),
    ("component_direction", "One side only", 10.0, "net YES-vs-NO pressure of the flow"),
    ("component_burst", "Speed", 15.0, "prints per hour in the window"),
    ("component_late", "Late in the market", 15.0, "share of the flow inside the market's last 48 h"),
    ("price_move_score", "Price moved their way", 10.0, "price change in the flow's direction within the window"),
    ("component_cluster", "Several wallets at once", 10.0, "3+ wallets and 10+ prints an hour"),
    ("component_fresh_wallets", "Fresh wallets", 10.0, "wallets barely seen on the tape, same side"),
    ("component_coordination", "Same minute, same side", 10.0, "wallets hitting one side within minutes"),
    ("component_first_trade", "First trade just before", 25.0, "money from wallets whose first trade on the venue was days old"),
)

#: Components damped by the sample weight (a handful of prints makes every
#: distribution "100% one wallet") and by the size weight (a $2 flow too);
#: the card says so when the weight is < 1.
_SAMPLE_WEIGHTED = {"component_long_odds", "component_concentration", "component_direction", "component_burst"}
_SIZE_WEIGHTED = _SAMPLE_WEIGHTED | {"component_cluster"}


def _fnum(getter: Any, key: str, default: float = 0.0) -> float:
    try:
        value = float(getter(key, default))
    except (TypeError, ValueError):
        return default
    return default if math.isnan(value) else value


def _dollars(value: float) -> str:
    value = float(value or 0.0)
    if value >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    if value >= 1_000:
        text = f"{value / 1_000:.1f}".rstrip("0").rstrip(".")
        return f"${text}k"
    return f"${value:,.0f}"


def _days_label(days: float) -> str:
    """An age in days as people say it: minutes under an hour, hours under a day."""

    value = max(0.0, float(days or 0.0))
    if value < 1.0 / 24.0:
        return f"{value * 24 * 60:.0f} min"
    if value < 1.0:
        return f"{value * 24:.0f} h"
    return f"{value:.1f} d"


def _component_fact(key: str, getter: Any) -> tuple[str, str]:
    """(what was observed, what full marks would take) for one component —
    the plain-words line under the bar on the risk card."""

    base = _fnum(getter, "whale_base", 0.0) or 1_000.0
    trades = int(_fnum(getter, "trades", 0.0))
    if key == "component_notional":
        return (f"{_dollars(_fnum(getter, 'notional'))} traded in the window",
                f"full marks at {_dollars(base * 40)}")
    if key == "component_largest":
        return (f"largest single print {_dollars(_fnum(getter, 'largest_trade'))}",
                f"full marks at {_dollars(base * 5)}")
    if key == "component_long_odds":
        usd = _fnum(getter, "long_odds_notional")
        share = _fnum(getter, "long_odds_share")
        if usd <= 0:
            return ("no money placed at 35¢ or below", "")
        return (f"{_dollars(usd)} weighted ({share:.0%} of the flow) at 35¢ or below; 20¢ and under count in full, 21 to 35¢ at 60%",
                f"full marks near {_dollars(base * 5)} or all of the flow")
    if key == "component_concentration":
        share = _fnum(getter, "top_wallet_share")
        wallet = str(getter("top_wallet", "") or "")
        who = short_wallet(wallet) if wallet and wallet.lower() != "nan" else "the top wallet"
        return (f"{who} did {share:.0%} of the flow", "full marks when one wallet did all of it")
    if key == "component_direction":
        share = _fnum(getter, "event_directional_share")
        label = str(getter("event_directional_label", "") or "").upper()
        if share <= 0.55:
            return (f"flow split — {share:.0%} net on one side", "points start above 55% net one side")
        return (f"{share:.0%} of the money net on {label or 'one side'}", "full marks at 100% one side")
    if key == "component_burst":
        tph = _fnum(getter, "trades_per_hour")
        return (f"{trades} print{'s' if trades != 1 else ''} at {tph:.0f} an hour", "full marks from 30 an hour")
    if key == "component_late":
        share = _fnum(getter, "late_share")
        if share <= 0:
            return ("nothing inside the market's last 48 h", "")
        return (f"{share:.0%} of the flow inside the market's last 48 h", "full marks when all of it was")
    if key == "price_move_score":
        move = _fnum(getter, "price_move")
        if move <= 0:
            return ("no move in the flow's direction", "")
        return (f"price moved {move * 100:+.0f}¢ the flow's way inside the window", "full marks at +10¢")
    if key == "component_cluster":
        wallets = int(_fnum(getter, "unique_wallets"))
        tph = _fnum(getter, "trades_per_hour")
        return (f"{wallets} wallet{'s' if wallets != 1 else ''}, {tph:.0f} prints an hour",
                "all or nothing: 3+ wallets and 10+ an hour")
    if key == "component_fresh_wallets":
        fresh = int(_fnum(getter, "fresh_wallets"))
        if fresh < 2:
            return ("no cluster of barely-seen wallets", "")
        return (f"{fresh} wallets barely seen on the tape, same side", "full marks at 4")
    if key == "component_coordination":
        wallets = int(_fnum(getter, "coordinated_wallets"))
        if wallets < 3:
            return ("no three wallets on one side within minutes", "")
        span = _fnum(getter, "coordinated_span_minutes")
        outcome = str(getter("coordinated_outcome", "") or "").upper()
        halved = _fnum(getter, "component_cluster") > 0
        return (f"{wallets} wallets on {outcome or 'one side'} within {span:.0f} min",
                "full marks at 5 wallets" + ("; halved because 'several wallets at once' already scored this burst" if halved else ""))
    if key == "component_first_trade":
        measured = int(_fnum(getter, "first_trade_measured", 0.0))
        wallets = int(_fnum(getter, "first_trade_wallets", 0.0))
        horizon = _fnum(getter, "first_trade_horizon_days", FRESH_TRADE_DAYS) or FRESH_TRADE_DAYS
        if wallets <= 0:
            if measured <= 0:
                return ("first trades of the wallets not measured in this window", "")
            return (f"none of the {measured} measured wallet{'s' if measured != 1 else ''} had a first trade under "
                    f"{horizon:g} d before its print", "")
        usd = _fnum(getter, "first_trade_notional")
        youngest = _fnum(getter, "first_trade_youngest_days")
        return (f"{_dollars(usd)} from {wallets} wallet{'s' if wallets != 1 else ''} whose first trade was "
                f"{_days_label(youngest)} before the print",
                f"full marks at {_dollars(base * FIRST_TRADE_FULL_MARKS_MULTIPLE)} from such wallets")
    return ("", "")


def event_components(row: Any) -> list[dict[str, Any]]:
    """Labelled score components of one event row:
    [{key, label, value, max, measures, fact, rule, weight?}].

    ``fact`` is what the tape showed ("0x07be…5233 did 97% of the flow"),
    ``rule`` what full marks would take ("full marks when one wallet did all
    of it"), ``measures`` the one-line definition; ``weight`` < 1 names the
    sample damping on the distribution components. Only columns present on
    the row are listed (an older frame without the component columns yields
    an empty list, never invented zeros). The context multiplier is appended
    as its own entry when the row carries one.
    """

    getter = row.get if hasattr(row, "get") else (lambda key, default=None: default)
    parts: list[dict[str, Any]] = []
    sample_w = _fnum(getter, "distribution_sample_weight", 1.0)
    size_w = _fnum(getter, "distribution_size_weight", 1.0)
    floor = _fnum(getter, "distribution_size_floor", 0.0)
    trades = int(_fnum(getter, "trades", 0.0))
    notional = _fnum(getter, "notional", 0.0)
    for key, label, cap, measures in EVENT_COMPONENTS:
        value = getter(key, None)
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isnan(number):
            continue
        fact, rule = _component_fact(key, getter)
        entry: dict[str, Any] = {"key": key, "label": label, "value": round(number, 1), "max": cap,
                                 "measures": measures, "fact": fact, "rule": rule}
        gruende: list[str] = []
        weight = 1.0
        if key in _SAMPLE_WEIGHTED and sample_w < 1.0:
            weight *= sample_w
            gruende.append(f"only {trades} print{'s' if trades != 1 else ''} in the sample")
        if key in _SIZE_WEIGHTED and size_w < 1.0:
            weight *= size_w
            gruende.append(f"only {_dollars(notional)} of flow" + (f", full weight from {_dollars(floor)}" if floor > 0 else ""))
        if gruende:
            entry["weight"] = round(weight, 2)
            entry["weight_note"] = f"damped ×{weight:.2f}: " + "; ".join(gruende)
        parts.append(entry)
    multiplier = getter("context_multiplier", None)
    try:
        factor = float(multiplier)
    except (TypeError, ValueError):
        factor = None
    if factor is not None and not math.isnan(factor):
        context = str(getter("insider_context", "") or "")
        note = str(getter("context_note", "") or "")
        parts.append({"key": "context_multiplier", "label": "Context", "value": round(factor, 2), "max": None,
                      "measures": "insider plausibility of the market's subject",
                      "fact": (context + (" — " + note if note else "")) if context else note,
                      "rule": "points × the multiplier; politics, awards and corporate decisions count more, general topics ×1"})
    return parts


# ---------------------------------------------------------------------------
# First trade as freshness.
#
# The sample-relative "fresh" above (few prints in the window, a 2x print,
# first appearance in the younger half) describes the sample. The public
# cases of 2026 describe something else: a wallet whose first trade on the
# venue lies hours or days before the print in question, whatever the age of
# the address. app/wallet_origin.py measures that with one call per wallet
# and keeps the answer; the functions below turn it into points on the event
# side and on the wallet side, and the flag log carries the days.
#
# The event side is what makes a single wallet visible. A lone print gets no
# distribution points by design (one print is always "100% one wallet"), and
# the fresh-wallet cluster needs two wallets; so the pattern every tracker
# post describes, one fresh wallet with one big print, used to stop at 25
# points and never reached a card or the log. Money from a measured-fresh
# wallet now carries its own cap, and size, largest print and this cap
# together clear the flag floor without any distribution claim.
# ---------------------------------------------------------------------------

#: A wallet whose first trade on the venue lies this many days or fewer
#: before its print is fresh. Chosen against the public cases (hours to two
#: days), not estimated; env ``RISK_FRESH_TRADE_DAYS`` overrides at runtime.
FRESH_TRADE_DAYS = 3.0
#: Up to here the wallet is young: half the wallet bonus, no event points.
YOUNG_TRADE_DAYS = 30.0
#: Event cap, and the dollars from fresh wallets that earn it, as a multiple
#: of the whale threshold (4 x 2,500 = 10,000 by default).
FIRST_TRADE_EVENT_CAP = 25.0
FIRST_TRADE_FULL_MARKS_MULTIPLE = 4.0
FIRST_TRADE_WALLET_BONUS = 15.0
YOUNG_TRADE_WALLET_BONUS = 7.0
ORIGIN_MEASURED = "measured"
ORIGIN_UNMEASURED = "unmeasured"
#: The base scorer's sample-relative flag and its points, taken back when the
#: measured first trade says the wallet is old.
SAMPLE_FRESH_FLAG = "sample-fresh large wallet"
SAMPLE_FRESH_POINTS = 10.0


def fresh_trade_days(default: float = FRESH_TRADE_DAYS) -> float:
    """The freshness horizon in days: env ``RISK_FRESH_TRADE_DAYS`` or the default."""

    import os

    try:
        value = float(os.environ.get("RISK_FRESH_TRADE_DAYS", "").strip() or default)
    except ValueError:
        value = float(default)
    return value if value > 0 else float(default)


def _origin_lookup(origins: Mapping[str, Any] | None) -> dict[str, tuple[int | None, str]]:
    """Lowercased wallet -> (first_trade_ts, state) from an origins mapping.

    Accepts the rows of ``wallet_origin.first_trade_map`` or a plain
    ``{wallet: unix_seconds}`` mapping.
    """

    out: dict[str, tuple[int | None, str]] = {}
    for wallet, info in (origins or {}).items():
        key = str(wallet or "").strip().lower()
        if not key:
            continue
        if isinstance(info, Mapping):
            stamp = info.get("first_trade_ts")
            state = str(info.get("state") or ORIGIN_UNMEASURED)
        else:
            stamp = info
            state = ORIGIN_MEASURED if info is not None else ORIGIN_UNMEASURED
        try:
            stamp = int(stamp) if stamp is not None else None
        except (TypeError, ValueError):
            stamp = None
        if state == ORIGIN_MEASURED and stamp is None:
            state = ORIGIN_UNMEASURED
        out[key] = (stamp, state)
    return out


def _drop_flag(flags: Any, label: str) -> str:
    parts = [part.strip() for part in str(flags or "").split(";") if part.strip()]
    kept = [part for part in parts if part != label]
    return "; ".join(kept) if kept else WATCH_ONLY


def first_trade_ages(trades: pd.DataFrame, origins: Mapping[str, Any] | None) -> pd.DataFrame:
    """Per identified print: platform, title, wallet, time, notional,
    ``first_trade_days`` (age of the wallet's first trade at that print, NaN
    when unmeasured) and ``measured``."""

    columns = ["platform", "title", "wallet", "time", "notional", "first_trade_days", "measured"]
    if trades is None or trades.empty or not {"wallet", "title"}.issubset(trades.columns):
        return pd.DataFrame(columns=columns)
    lookup = _origin_lookup(origins)
    df = trades.copy()
    df["wallet"] = df["wallet"].astype(str).str.lower().str.strip()
    df = df[identified_wallets(df["wallet"])]
    if df.empty:
        return pd.DataFrame(columns=columns)
    df["platform"] = df.get("platform", pd.Series("", index=df.index)).fillna("").astype(str)
    df["title"] = df["title"].fillna("").astype(str)
    df["time"] = pd.to_datetime(df["time"] if "time" in df.columns else pd.Series(pd.NaT, index=df.index), utc=True, errors="coerce")
    df["notional"] = numeric_col(df, "notional").clip(lower=0.0)
    stamps = pd.to_numeric(df["wallet"].map(lambda w: lookup.get(w, (None, ORIGIN_UNMEASURED))[0]), errors="coerce")
    states = df["wallet"].map(lambda w: lookup.get(w, (None, ORIGIN_UNMEASURED))[1])
    measured = states.eq(ORIGIN_MEASURED) & stamps.notna() & df["time"].notna()
    seconds = df["time"].map(lambda t: t.timestamp() if pd.notna(t) else float("nan"))
    ages = ((seconds - stamps) / 86_400.0).clip(lower=0.0)
    df["first_trade_days"] = ages.where(measured)
    df["measured"] = measured
    return df[columns].reset_index(drop=True)


def apply_first_trade_bonus(
    event_risk: pd.DataFrame,
    trades: pd.DataFrame,
    origins: Mapping[str, Any] | None,
    *,
    whale_threshold: float,
    fresh_days: float | None = None,
    cap: float = FIRST_TRADE_EVENT_CAP,
) -> pd.DataFrame:
    """Event points for money from wallets whose first trade was fresh.

    Adds ``component_first_trade`` (0..cap), ``first_trade_wallets``,
    ``first_trade_notional``, ``first_trade_youngest_days``,
    ``first_trade_measured`` (how many of the market's wallets were measured
    at all, so "0 fresh" and "not asked" stay apart) and
    ``first_trade_horizon_days``; appends a flag. Full marks at
    ``FIRST_TRADE_FULL_MARKS_MULTIPLE`` times the whale threshold.
    """

    if event_risk is None or event_risk.empty:
        return event_risk
    horizon = float(fresh_days) if fresh_days is not None else fresh_trade_days()
    enriched = event_risk.copy()
    enriched["component_first_trade"] = 0.0
    enriched["first_trade_wallets"] = 0
    enriched["first_trade_notional"] = 0.0
    enriched["first_trade_youngest_days"] = float("nan")
    enriched["first_trade_measured"] = 0
    enriched["first_trade_horizon_days"] = horizon
    ages = first_trade_ages(trades, origins)
    if ages.empty:
        return enriched
    keys = ["platform", "title"] if "platform" in enriched.columns else ["title"]
    measured = ages[ages["measured"]]
    if measured.empty:
        return enriched
    counts = measured.groupby(keys)["wallet"].nunique().rename("_ft_measured").reset_index()
    enriched = enriched.merge(counts, on=keys, how="left")
    enriched["first_trade_measured"] = enriched["_ft_measured"].fillna(0).astype(int)
    fresh = measured[measured["first_trade_days"] <= horizon]
    if fresh.empty:
        return enriched.drop(columns=["_ft_measured"])
    grouped = (
        fresh.groupby(keys)
        .agg(_ft_notional=("notional", "sum"), _ft_wallets=("wallet", "nunique"), _ft_youngest=("first_trade_days", "min"))
        .reset_index()
    )
    enriched = enriched.merge(grouped, on=keys, how="left")
    has = enriched["_ft_wallets"].fillna(0) > 0
    enriched.loc[has, "first_trade_wallets"] = enriched.loc[has, "_ft_wallets"].astype(int)
    enriched.loc[has, "first_trade_notional"] = enriched.loc[has, "_ft_notional"].astype(float)
    enriched.loc[has, "first_trade_youngest_days"] = enriched.loc[has, "_ft_youngest"].astype(float)
    whale_base = max(float(whale_threshold or 0.0), 1_000.0)
    points = (enriched["first_trade_notional"] / (whale_base * FIRST_TRADE_FULL_MARKS_MULTIPLE)).clip(lower=0.0, upper=1.0) * float(cap)
    enriched["component_first_trade"] = points.round(1)
    enriched["event_insider_score"] = (numeric_col(enriched, "event_insider_score") + points).clip(0, 100).round(0)
    enriched["event_insider_level"] = enriched["event_insider_score"].map(risk_level)
    if "event_risk_score" in enriched.columns:
        enriched["event_risk_score"] = enriched["event_insider_score"]
        enriched["event_risk_level"] = enriched["event_insider_level"]
    if "event_insider_flags" in enriched:
        for idx in enriched.index[has]:
            count = int(enriched.at[idx, "first_trade_wallets"])
            usd = money(float(enriched.at[idx, "first_trade_notional"]))
            youngest = float(enriched.at[idx, "first_trade_youngest_days"])
            label = (
                f"fresh wallet: first trade {_days_label(youngest)} before, {usd}" if count == 1
                else f"{count} wallets with a first trade under {horizon:g} d: {usd}"
            )
            enriched.at[idx, "event_insider_flags"] = _append_flag(enriched.at[idx, "event_insider_flags"], label)
    return enriched.drop(columns=["_ft_measured", "_ft_notional", "_ft_wallets", "_ft_youngest"], errors="ignore")


def apply_first_trade_bonus_wallets(
    wallet_risk: pd.DataFrame,
    origins: Mapping[str, Any] | None,
    *,
    fresh_days: float | None = None,
    young_days: float = YOUNG_TRADE_DAYS,
    bonus: float = FIRST_TRADE_WALLET_BONUS,
    young_bonus: float = YOUNG_TRADE_WALLET_BONUS,
    now: Any = None,
) -> pd.DataFrame:
    """Wallet points for a measured first trade, and the sample-relative
    "fresh" taken back where the measurement says the wallet is old.

    Adds ``first_trade_age_days`` (age at the wallet's latest print in the
    window), ``first_trade_state`` and ``component_first_trade``. Only a
    measured origin moves anything; an unmeasured wallet keeps its score.
    """

    if wallet_risk is None or wallet_risk.empty:
        return wallet_risk
    horizon = float(fresh_days) if fresh_days is not None else fresh_trade_days()
    lookup = _origin_lookup(origins)
    enriched = wallet_risk.copy()
    enriched["first_trade_age_days"] = float("nan")
    enriched["first_trade_state"] = ORIGIN_UNMEASURED
    enriched["component_first_trade"] = 0.0
    if not lookup:
        return enriched
    reference = (
        pd.to_datetime(enriched["latest_trade"], utc=True, errors="coerce")
        if "latest_trade" in enriched.columns else pd.Series(pd.NaT, index=enriched.index)
    )
    fallback = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    if fallback.tzinfo is None:
        fallback = fallback.tz_localize("UTC")
    scores = numeric_col(enriched, "wallet_insider_score").astype(float)
    has_flags = "wallet_insider_flags" in enriched.columns
    for idx in enriched.index:
        origin = lookup.get(str(enriched.at[idx, "wallet"]).strip().lower())
        if origin is None:
            continue
        stamp, state = origin
        enriched.at[idx, "first_trade_state"] = state
        if state != ORIGIN_MEASURED or stamp is None:
            continue
        at = reference.at[idx] if pd.notna(reference.at[idx]) else fallback
        age = max(0.0, (at.timestamp() - float(stamp)) / 86_400.0)
        enriched.at[idx, "first_trade_age_days"] = age
        flags = enriched.at[idx, "wallet_insider_flags"] if has_flags else ""
        label = ""
        if age <= horizon:
            points = float(bonus)
            label = f"first trade {_days_label(age)} before this print"
        elif age <= young_days:
            points = float(young_bonus)
            label = f"first trade {age:.0f} d ago"
        else:
            points = 0.0
            if "sample_fresh" in enriched.columns and bool(enriched.at[idx, "sample_fresh"]):
                scores.at[idx] = max(0.0, float(scores.at[idx]) - SAMPLE_FRESH_POINTS)
                enriched.at[idx, "sample_fresh"] = False
                flags = _drop_flag(flags, SAMPLE_FRESH_FLAG)
        enriched.at[idx, "component_first_trade"] = points
        scores.at[idx] = float(scores.at[idx]) + points
        if label:
            flags = _append_flag(flags, label)
        if has_flags:
            enriched.at[idx, "wallet_insider_flags"] = flags
    enriched["wallet_insider_score"] = scores.clip(0, 100).round(0)
    enriched["wallet_insider_level"] = enriched["wallet_insider_score"].map(risk_level)
    if "wallet_risk_score" in enriched.columns:
        enriched["wallet_risk_score"] = enriched["wallet_insider_score"]
        enriched["wallet_risk_level"] = enriched["wallet_insider_level"]
        enriched["wallet_risk_reasons"] = enriched["wallet_insider_flags"] if has_flags else enriched.get("wallet_risk_reasons")
    order = ["wallet_insider_score"] + (["notional"] if "notional" in enriched.columns else [])
    return enriched.sort_values(order, ascending=False).reset_index(drop=True)


class ScreenResult(NamedTuple):
    """What one pass of the screen produced, in the order the surfaces read it."""

    base: pd.DataFrame
    events: pd.DataFrame
    wallets: pd.DataFrame
    fresh: pd.DataFrame
    coord: pd.DataFrame


def screen_tape(
    trades: pd.DataFrame,
    *,
    whale_threshold: float,
    now: Any = None,
    known_since: Mapping[str, int] | None = None,
    origins: Mapping[str, Any] | None = None,
    market_categories: pd.DataFrame | None = None,
    fresh_days: float | None = None,
) -> ScreenResult:
    """The whole ladder over one tape, in one place.

    Filter to the insider-prone contexts, score events and wallets, add the
    fresh-cluster and timing bonuses, the first-trade points where origins
    were measured, the context multiplier, and the flow details for the
    cards and the log. The API server, the Streamlit page and the case replay
    call this, so the same tape gives the same numbers everywhere.
    """

    empty = pd.DataFrame()
    base = filter_insider_prone_trades(trades, market_categories)
    if base is None or base.empty:
        return ScreenResult(empty, empty, empty, empty, empty)
    wallets = md.whale_wallet_risk_scores(base, whale_threshold=whale_threshold, now=now, known_since=known_since or None)
    events = md.whale_event_risk_scores(base, whale_threshold=whale_threshold, now=now)
    fresh = fresh_wallet_clusters(base, whale_threshold=whale_threshold)
    coord = coordinated_clusters(base)
    events = apply_fresh_wallet_bonus(events, fresh)
    events = apply_coordination_bonus(events, coord)
    if origins:
        events = apply_first_trade_bonus(events, base, origins, whale_threshold=whale_threshold, fresh_days=fresh_days)
        wallets = apply_first_trade_bonus_wallets(wallets, origins, fresh_days=fresh_days, now=now)
    events = apply_category_context(events, market_categories)
    if wallets is not None and not wallets.empty:
        wallets = apply_wallet_category_context(wallets, base, market_categories)
    events = enrich_event_flow(events, base, whale_threshold=whale_threshold, origins=origins)
    return ScreenResult(base, events, wallets, fresh, coord)
