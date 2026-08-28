"""Category efficiency: how well each market category prices things ahead of time.

For every resolved binary Polymarket market the YES price is read at fixed
horizons before its decision time (30, 14, 7, 3 and 1 days by default) and
scored against the outcome: Brier score, hit rate, and a calibration table
of predicted probability against realised frequency. Grouped by category.

The category comes from the Gamma event tags first (Sports, Politics, Crypto,
Pop Culture, Business, Science, ...), then from the title/tag classifier the
live market screens use (``market_filter_category`` in
src/prediction_markets.py). Mentions markets ("Will X say Y ...") are split
out because they are the subject of their own study on the research page.

Two measurements must not be confused, and this module only performs the
first: fixed-horizon *forecast quality* (was the T-N price right?) is not
*pricing-in speed* (how fast did a goal, a data print, an AP call move the
price?). Speed needs an external t0 per event and minute-level series; the
horizons here can never see it. What they CAN say per category is documented
in ``MESSLOGIK``, and every market carries an ``einpreisungstyp`` — the
mechanism by which its price absorbs reality (threshold tracking, running
tally, in-play game, scheduled reveal, unscheduled news) — so the per-
category figures can be read against the mechanism mix that produced them.

Network-free: scripts/category_efficiency.py fetches events and price series
through src/prediction_markets.py and hands the raw payloads to this module.
Nothing here invents a price — a market without a price at a horizon simply
does not count at that horizon, and every figure carries its sample size.
"""

from __future__ import annotations

import math
import re
import statistics
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

import pandas as pd

from app import base_rate_study as brs
from app import quant
from src import prediction_markets as pm

PROVENIENZ = "terminal/category_efficiency"

#: Days before the decision time at which the YES price is read.
DEFAULT_HORIZONS: tuple[int, ...] = (30, 14, 7, 3, 1)

#: Calibration bins over the predicted probability (T-7 by default).
DEFAULT_BIN_EDGES: tuple[float, ...] = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)

#: Output buckets, in display order. Elections, Geopolitics and
#: Tweets/Social were split out of Politics/Other in 2026-08: the cached
#: sample carried 220+ election tags, 300+ conflict/diplomacy tags and 118
#: "tweet markets" tags, and each of the three prices by a different
#: mechanism (scheduled count night, unscheduled news, public running tally).
CATEGORIES: tuple[str, ...] = (
    "Politics",
    "Elections",
    "Geopolitics",
    "Sports",
    "Crypto",
    "Pop culture",
    "Business/Finance",
    "Science/Tech",
    "Tweets/Social",
    "Weather",
    "Mentions",
    "Other",
)
OTHER = "Other"

# Gamma event tags -> bucket, in two tiers. Specific tags (a league, a coin,
# "Fed Rates", "Oscars") are checked first, in this order; the broad section
# tags ("Politics", "Sports", "Business", ...) only decide when no specific
# tag did. So an FOMC event tagged Politics + Fed Rates counts as
# business/finance, while a Fed-chair nomination tagged Trump + Fed Rates
# counts as politics because Trump sits ahead of Fed Rates in the specific
# tier. Elections beats Geopolitics (an election in a conflict country is
# still an election), Geopolitics beats Politics (a Trump–Putin summit is
# geopolitics even when tagged Trump). Labels are matched case-insensitively.
_SPECIFIC_TAG_RULES: tuple[tuple[str, frozenset[str]], ...] = (
    ("Sports", frozenset({
        "soccer", "football", "nfl", "nba", "mlb", "nhl", "wnba", "ncaa", "college football",
        "college basketball", "tennis", "golf", "ufc", "mma", "boxing", "f1", "formula 1", "nascar",
        "cricket", "rugby", "esports", "chess", "olympics", "fifa world cup", "world cup", "ucl",
        "champions league", "premier league", "la liga", "serie a", "bundesliga", "mls", "super bowl",
        "nba finals", "world series", "stanley cup", "march madness", "hockey", "baseball", "basketball",
        "cycling", "darts", "snooker", "athletics", "swimming", "table tennis", "volleyball", "handball",
        "games",
    })),
    ("Crypto", frozenset({
        "crypto prices", "bitcoin", "btc", "ethereum", "eth", "solana", "sol", "xrp", "doge",
        "dogecoin", "memecoins", "stablecoins", "defi", "airdrops", "hyperliquid", "fdv",
        "altcoins", "nft", "nfts", "binance", "coinbase", "microstrategy", "token sales", "public sales",
    })),
    ("Mentions", frozenset({"mentions", "mention markets"})),
    ("Tweets/Social", frozenset({"tweet markets", "tweets", "elon tweets", "truth social posts", "x posts"})),
    ("Elections", frozenset({
        "elections", "election", "world elections", "global elections", "presidential election",
        "governor", "mayor", "primary", "primaries", "midterms", "2026 midterms", "ballot",
        "referendum", "senate race", "house race",
    })),
    ("Geopolitics", frozenset({
        "geopolitics", "middle east", "iran", "israel", "ukraine", "russia", "china", "taiwan",
        "gaza", "ceasefire", "peace deal", "nato", "war", "u.s. x iran", "iran ceasefire",
        "north korea", "venezuela", "syria", "india", "pakistan",
    })),
    ("Politics", frozenset({
        "us politics", "trump", "trump presidency", "congress", "senate", "supreme court",
        "scotus", "uk politics", "cabinet", "executive order",
        "tariffs", "government shutdown", "gov shutdown", "impeachment", "polls", "approval rating",
        "white house",
    })),
    ("Pop culture", frozenset({
        "movies", "movie", "music", "tv", "television", "celebrities", "celebrity",
        "awards", "oscars", "academy awards", "grammys", "emmys", "golden globes", "tonys", "box office",
        "reality tv", "video games", "gaming", "rotten tomatoes", "streaming", "netflix", "spotify",
        "billboard", "eurovision", "kardashians", "taylor swift", "drake", "kanye", "youtube", "tiktok",
        "twitch", "mrbeast", "anime", "comics", "marvel", "star wars", "wwe", "podcasts",
    })),
    ("Business/Finance", frozenset({
        "economic policy", "fed", "fed rates", "fomc",
        "interest rates", "rates", "inflation", "cpi", "gdp", "jobs report", "unemployment", "stocks",
        "stock market", "s&p 500", "spx", "nasdaq", "dow", "indices", "indicies", "earnings", "ipo", "companies", "tesla", "apple",
        "nvidia", "openai valuation", "macro", "commodities", "oil", "gold", "silver", "treasury", "bonds",
        "recession", "trade", "trade deal", "mergers", "m&a", "bankruptcy", "layoffs", "ceo", "startups",
    })),
    ("Science/Tech", frozenset({
        "ai", "artificial intelligence", "openai", "chatgpt", "gpt",
        "anthropic", "google", "gemini", "grok", "xai", "llm", "space", "spacex", "starship", "nasa",
        "moon", "mars", "rocket", "health", "medicine", "vaccine", "pandemic", "pandemics",
        "covid", "fda", "climate", "energy", "nuclear", "quantum", "robots", "robotics", "self-driving",
        "tesla robotaxi", "apple event", "iphone", "software", "cybersecurity",
    })),
    ("Weather", frozenset({"temperature", "hurricane", "hurricanes", "climate & weather", "rain", "snow"})),
)
_GENERIC_TAG_RULES: tuple[tuple[str, frozenset[str]], ...] = (
    ("Sports", frozenset({"sports"})),
    ("Crypto", frozenset({"crypto"})),
    ("Geopolitics", frozenset({"world"})),
    ("Politics", frozenset({"politics"})),
    ("Pop culture", frozenset({"pop culture", "culture"})),
    ("Business/Finance", frozenset({"business", "finance", "economy", "economics"})),
    ("Science/Tech", frozenset({"science", "tech", "technology"})),
    ("Weather", frozenset({"weather"})),
)
_TAG_RULES: tuple[tuple[str, frozenset[str]], ...] = _SPECIFIC_TAG_RULES + _GENERIC_TAG_RULES

# Tags Gamma attaches for its own UI, never a category signal.
_IGNORED_TAGS = frozenset({
    "all", "featured", "new", "trending", "recurring", "monthly", "weekly", "daily", "yearly",
    "hide from new", "parent for derivative", "pre-market", "2025 predictions", "2026 predictions",
    "best of 2025", "best of 2026", "hfc", "main election", "macro election 2", "breaking news",
})

_MENTION_RE = re.compile(r"\bsay\b.*?[\"“'‘]|\bmention(s|ed)?\b|\bwill .* say\b", re.IGNORECASE)
_TWEET_RE = re.compile(r"\btweets?\b|\bretweets?\b", re.IGNORECASE)

# Gamma spells election tags a dozen ways ("US Election", "Mayoral Elections",
# "deprec German Election", ...); a word match on the label beats any list.
_ELECTION_LABEL_RE = re.compile(r"\belections?\b", re.IGNORECASE)

# What the live classifier answers -> our bucket. It never says pop culture,
# science or business/finance, hence the tag pass first.
_FILTER_TO_BUCKET = {
    "sports": "Sports",
    "crypto": "Crypto",
    "politics": "Politics",
    "weather": "Weather",
    "finance": "Business/Finance",
    "economy": "Business/Finance",
    "business": "Business/Finance",
    "pop culture": "Pop culture",
    "culture": "Pop culture",
    "science": "Science/Tech",
    "tech": "Science/Tech",
    "mentions": "Mentions",
}


def _tag_labels(tags: Iterable[Any] | None) -> list[str]:
    labels: list[str] = []
    for tag in tags or []:
        if isinstance(tag, Mapping):
            label = tag.get("label") or tag.get("slug") or ""
        else:
            label = tag
        text = str(label or "").strip().lower()
        if text and text not in _IGNORED_TAGS:
            labels.append(text)
    return labels


def is_mentions_market(title: Any) -> bool:
    """"Will Trump say 'tariff' during the address?" and friends."""

    text = str(title or "")
    return bool(_MENTION_RE.search(text))


def classify_category(title: Any, tags: Iterable[Any] | None = None, raw_category: Any = "") -> str:
    """One of ``CATEGORIES`` for a market, from its title, event tags and raw category.

    Order: mentions by title pattern (they sit inside politics or business
    events), tweet-count markets by title pattern (Gamma files them under
    "Tweet Markets" but individual markets sometimes only say "tweet ... times"),
    then the specific event tags, then the broad section tags (see
    ``_TAG_RULES``), then the live classifier ``market_filter_category`` on
    raw category plus title, else ``Other``.
    """

    if is_mentions_market(title):
        return "Mentions"
    if _TWEET_RE.search(str(title or "")):
        return "Tweets/Social"
    labels = _tag_labels(tags)
    for bucket, words in _TAG_RULES:
        if any(label in words for label in labels):
            return bucket
        if bucket == "Elections" and any(_ELECTION_LABEL_RE.search(label) for label in labels):
            return bucket
    live = str(pm.market_filter_category(raw_category, title) or "").strip().lower()
    return _FILTER_TO_BUCKET.get(live, OTHER)


#: How a market's price absorbs reality — the mechanism, not the topic.
#: "schwelle": tracks a continuously observable underlying against a fixed
#: level (BTC >= $100k, S&P up-or-down, temperature above X); the price is
#: an option delta on the underlying, Brier measures the underlying's
#: distribution more than anyone's judgement. "zaehler": a public running
#: tally inside a window (mentions, tweet counts, box-office gross); each
#: increment moves the price stepwise and the price converges mechanically
#: near the window's end. "spielverlauf": a scheduled contest whose outcome
#: forms live in play (one match, one race) — win probability drifts
#: continuously and jumps on discrete shocks (goal, red card).
#: "serie": a tournament/season future repriced stepwise after every
#: scheduled sub-event. "stichtag": the answer appears at a known moment
#: (election night, FOMC/CPI print, award announcement, earnings).
#: "nachrichten": undated events decide (conflict news, resignations,
#: deals, open "by <date>" deadlines). "unklar": no rule matched.
EINPREISUNGSTYPEN: tuple[str, ...] = (
    "schwelle", "zaehler", "spielverlauf", "serie", "stichtag", "nachrichten", "unklar",
)

_LEVEL_RE = re.compile(
    r"(?:\babove\b|\bbelow\b|\bbetween\b|\bhigher than\b|\blower than\b|\bhit\b|\breach\b"
    r"|\bclose (?:above|below|at)\b|\bdip to\b|\btouch\b|\bfinish (?:above|below)\b"
    r"|\bend (?:above|below)\b|\btop\b)[^?]*?\$?\d",
    re.IGNORECASE,
)
_UPDOWN_RE = re.compile(r"\bup or down\b", re.IGNORECASE)
_COUNT_RE = re.compile(r"\bhow many times\b|\b\d+\+?\s*(?:or more\s+)?times\b", re.IGNORECASE)
_FIXTURE_RE = re.compile(r"\bvs\.?\s|\bbeat\b|\bwin (?:game|match|race)\b|\bwin on \d{4}-\d{2}-\d{2}\b", re.IGNORECASE)
_AWARD_RE = re.compile(
    r"\bwin\b.*\b(?:oscars?|academy awards?|best|grammys?|emmys?|golden globes?|tonys?|awards?)\b"
    r"|\beurovision\b|\bgame of the year\b|\bballon d'or\b",
    re.IGNORECASE,
)
_MACRO_RE = re.compile(
    r"\bfed\b|\bfomc\b|\brate (?:cut|hike)\b|\binterest rates?\b|\bcpi\b|\binflation\b"
    r"|\bjobs report\b|\bpayrolls?\b|\bunemployment rate\b|\bgdp\b|\bearnings\b",
    re.IGNORECASE,
)
_TALLY_RE = re.compile(r"\bbox office\b|\bgross\b|\bstreams\b|\bviews\b|\bsubscribers\b|\bfollowers\b", re.IGNORECASE)


def einpreisungstyp(title: Any, category: Any, lifetime_days: float | None = None) -> str:
    """One of ``EINPREISUNGSTYPEN`` for a market, from title, bucket and lifetime.

    Heuristic on purpose and reported as such: tally/threshold patterns
    first (a mentions market quoting a dollar figure is still a tally),
    sports before the threshold check so an in-game total ("above 110
    points") counts as in-play rather than as a price level, then the
    per-category default. Sports splits into single fixtures (a "vs" title
    or a market that lived under 7 days — game lines are created days out)
    and season/tournament futures.
    """

    text = str(title or "")
    cat = str(category or OTHER)
    if cat in ("Mentions", "Tweets/Social") or _COUNT_RE.search(text):
        return "zaehler"
    if cat == "Sports":
        if _FIXTURE_RE.search(text) or (lifetime_days is not None and float(lifetime_days) < 7.0):
            return "spielverlauf"
        return "serie"
    if _UPDOWN_RE.search(text) or _LEVEL_RE.search(text):
        return "schwelle"
    if cat == "Weather":
        return "schwelle"
    if cat == "Elections":
        return "stichtag"
    if cat == "Pop culture":
        if _AWARD_RE.search(text):
            return "stichtag"
        if _TALLY_RE.search(text):
            return "zaehler"
        return "nachrichten"
    if cat == "Business/Finance":
        return "stichtag" if _MACRO_RE.search(text) else "nachrichten"
    if cat in ("Politics", "Geopolitics", "Crypto", "Science/Tech"):
        return "nachrichten"
    return "unklar"


#: Per category: what the fixed horizons actually anchor to, which real-world
#: events reprice the bucket (and whether their t0 is even definable), what
#: this study can NOT see, and where a proper event-anchored latency study
#: would take its t0 from. Published verbatim under quelle.messlogik so the
#: figures are never read as something they are not.
MESSLOGIK: dict[str, dict[str, str]] = {
    "Politics": {
        "anker": "T-N zaehlt rueckwaerts vom Entscheid (min aus endDate und closedTime). Politikmaerkte loesen oft vorzeitig auf (Unterschrift, Rueckzug, Deal); dann ankert T-N an der Marktschliessung, die dem wahren Ereignis um Stunden bis Tage nachlaeuft — T-1 kann dann NACH dem Ereignis liegen und liest ein Preisniveau, das die Antwort schon kennt.",
        "einpreisung": "Getrieben von unterminierten Nachrichten: Ankuendigungen, Personalien, Abstimmungen. Ein t0 je Ereignis ist nur ueber externe Quellen definierbar (Wire-Zeitstempel, offizielles Dokument, C-SPAN), nie aus den Marktdaten selbst.",
        "nicht_gemessen": "Reaktionslatenz auf einzelne Nachrichten. Die Horizonte messen Prognoseguete zu festen Abstaenden, keine Geschwindigkeit.",
        "latenz_t0": "AP/Reuters-Wire-Zeitstempel oder amtliche Veroeffentlichung (Congress.gov, Federal Register) gegen die CLOB-Minutenserie.",
    },
    "Elections": {
        "anker": "endDate ist der Wahltermin — der sauberste Anker aller Kategorien. T-N ist hier echte Vorhersageguete vor einem bekannten Stichtag.",
        "einpreisung": "Stichtagsereignis: die Auszaehlung am Wahlabend entscheidet; davor treiben Umfragen den Preis kontinuierlich. t0 fuer eine Latenzmessung: der AP-Race-Call bzw. das amtliche Ergebnis, sekundengenau dokumentiert.",
        "nicht_gemessen": "Die Einpreisung der Auszaehlung am Wahlabend selbst (Minutenbereich; Thesis Tabelle A1 haelt 26–94 Minuten bis zu stabilen Niveaus fest).",
        "latenz_t0": "AP-Race-Call-Zeitstempel je Rennen gegen die CLOB-Minutenserie der Wahlnacht.",
    },
    "Geopolitics": {
        "anker": "Viele Maerkte tragen Platzhalter-Enddaten (\"by end of 2026\") und loesen vorzeitig auf; T-N ankert dann an closedTime und kurze Horizonte lesen teils Preise NACH dem entscheidenden Ereignis. Der Anteil bereits entschiedener Preise (anteil_entschieden) macht das sichtbar, heilt es aber nicht.",
        "einpreisung": "Unterminierte Nachrichten: Eskalation, Waffenruhe, Abkommen. t0 ist oft selbst umstritten (wann 'beginnt' eine Waffenruhe?) — Resolution-Streits und UMA-Challenges sind hier am haeufigsten.",
        "nicht_gemessen": "Reaktionslatenz auf Konfliktnachrichten; ebenso, wie oft der Markt zwischenzeitlich falsch lag (ein T-7-Preis von 0.5, der zweimal dreht, zaehlt gleich wie einer, der ruhig liegt).",
        "latenz_t0": "Wire-Zeitstempel (Reuters/AP) grosser Eskalations-/Deeskalationsmeldungen gegen die Minutenserie.",
    },
    "Sports": {
        "anker": "Bei Einzelspielen liegt endDate am Spieltag: T-1 ist eine Pre-Game-Quote, T-7 existiert fuer die meisten Spielmaerkte nicht (sie leben kuerzer und fuellen den Short-Bucket). Bei Futures (Turnier-/Saisonsieger) misst T-N die Aggregation ueber viele Spiele — zwei verschiedene Fragen im selben Bucket, deshalb der Typen-Split spielverlauf/serie.",
        "einpreisung": "Zwei Arten, beide ZWISCHEN T-1 und dem Entscheid und mit Tageshorizonten prinzipiell unsichtbar: (1) die kontinuierlich driftende Siegwahrscheinlichkeit im Spielverlauf, (2) diskrete Schocks (Tor, Platzverweis, Verletzung) mit exakt bestimmbarem t0 aus Play-by-play-Feeds.",
        "nicht_gemessen": "Jede In-Play-Bewegung. Das publizierte Super-Bowl-Beispiel (180 min bis Konvergenz) zaehlt ab Kickoff und enthaelt die Spieldauer — dokumentierte Obergrenze, keine Reaktionszeit auf ein Ereignis.",
        "latenz_t0": "Play-by-play-Zeitstempel (offizielle Liga-Feeds, ESPN/Opta) je Score-Ereignis gegen die CLOB-Serie mit fidelity=1.",
    },
    "Crypto": {
        "anker": "Der Grossteil des Buckets sind Schwellenmaerkte (Tags hit price/multi strikes): der Marktpreis folgt mechanisch dem Spot der Referenzboerse. T-N misst dort die Verteilung des Basiswerts (ein Options-Delta), nicht die Urteilskraft von Haendlern.",
        "einpreisung": "t0 exakt definierbar: die 1-Minuten-Kerze der Aufloesungsboerse (Coinbase/Binance) kreuzt die Schwelle. Bestdefinierter t0 aller Kategorien; Arbitrage haelt die Latenz nahe null (Beispiel im Datensatz: Konvergenz 44 min VOR t0). News-Krypto (ETF-Zulassung, Airdrop, Listing) verhaelt sich dagegen wie Politik: unterminiert.",
        "nicht_gemessen": "Nichts Strukturelles — aber ein guter Brier belegt hier keine Prognosefaehigkeit, sondern dass Spotpreise nachvollzogen werden.",
        "latenz_t0": "Referenzboersen-Kerze (Aufloesungsquelle laut Marktregeln) gegen die CLOB-Minutenserie.",
    },
    "Pop culture": {
        "anker": "Zeremonien und Veroeffentlichungen sind terminiert; endDate liegt am Termin, T-N davor ist echte Vorhersageguete (Prognosen aus Kritiken, Vorab-Awards, Charts).",
        "einpreisung": "Stichtag: die Verkuendung im Lauf der Zeremonie. t0 ist der Verkuendungszeitpunkt der einzelnen Kategorie, NICHT der Zeremoniebeginn — das Oscar-Beispiel (220 min ab Zeremoniebeginn) ist deshalb eine Obergrenze. Box-Office- und Chart-Maerkte sind dagegen Zaehler mit taeglich publizierten Zwischenstaenden.",
        "nicht_gemessen": "Die Minuten zwischen Verkuendung und Konvergenz; dafuer braucht es Broadcast-Zeitstempel je Award-Kategorie.",
        "latenz_t0": "Broadcast-/Social-Zeitstempel der Verkuendung (offizieller Stream) je Kategorie.",
    },
    "Business/Finance": {
        "anker": "Makro-Stichtage (FOMC-Statement 14:00 ET, CPI 08:30 ET) sind sekundengenau terminiert — endDate faellt auf den Termin, T-N davor misst echte Erwartungsbildung. Firmen-News (Deals, Ankuendigungen) sind dagegen unterminiert wie Politik.",
        "einpreisung": "Beim Datenprint entsteht die Antwort in einem Augenblick; die Einpreisung ist ein Sprung bei t0. Zwischen den Prints bewegen Fed-Reden und Datenrevisionen den Preis kontinuierlich.",
        "nicht_gemessen": "Die Sprunggeschwindigkeit nach dem Print (Sekunden bis Minuten) — mit Tageshorizonten unsichtbar, mit dem exakten Release-Zeitstempel aber praezise messbar.",
        "latenz_t0": "Offizieller Release-Zeitstempel (BLS/Fed-Kalender) gegen die CLOB-Minutenserie.",
    },
    "Science/Tech": {
        "anker": "Gemischt: Launches und Events sind (grob) terminiert, Modell-Releases und Zulassungen nicht. Vorzeitige Aufloesungen (Release erschienen) ankern an closedTime mit demselben Nachlauf-Problem wie Politik.",
        "einpreisung": "Ueberwiegend unterminierte Ankuendigungen (Release-Blogposts, FDA-Entscheide, Launch-Ergebnis). t0 je Ereignis aus offiziellen Kanaelen bestimmbar, aber nicht aus Marktdaten.",
        "nicht_gemessen": "Reaktionslatenz auf Ankuendigungen; ausserdem ist der Bucket heterogen (KI, Raumfahrt, Gesundheit) — ein einzelner Brier mittelt ueber sehr verschiedene Mechanismen.",
        "latenz_t0": "Zeitstempel der offiziellen Ankuendigung (Blogpost, Livestream, Behoerden-Release).",
    },
    "Tweets/Social": {
        "anker": "Zaehlermaerkte mit festem Fensterende: endDate ist das Fensterende, T-N liest den Preis bei bekanntem Zwischenstand des oeffentlich einsehbaren Zaehlers.",
        "einpreisung": "Jeder Post ist ein exakt gestempeltes Teilereignis; der Preis rueckt schrittweise nach und konvergiert gegen Fensterende mechanisch. Brier misst hier vor allem die Restvarianz des Zaehlers, nicht Prognosekunst.",
        "nicht_gemessen": "Die Latenz je Post (waere mit Post-Zeitstempeln exakt messbar, ist aber oekonomisch uninteressant, solange der Zwischenstand oeffentlich ist).",
        "latenz_t0": "Post-Zeitstempel der Plattform gegen die Minutenserie — nur der Vollstaendigkeit halber.",
    },
    "Weather": {
        "anker": "Schwellen auf amtlichen Messreihen (NWS/METAR): endDate ist das Messfensterende. Im aktuellen Sample fehlen Wettermaerkte, weil der Sweep die volumenstaerksten Events zuerst zieht und Tagesmaerkte darunter bleiben — eine Stichprobenluecke, keine Aussage ueber die Kategorie.",
        "einpreisung": "t0 = die Beobachtung, die die Schwelle reisst (stuendliche Messung); davor preist der Markt Wettermodelle ein, die selbst nur zu festen Laeufen (00/06/12/18 UTC) erscheinen.",
        "nicht_gemessen": "Alles — solange die Stichprobe leer ist, gibt es hier keine Zahl, und es wird keine erfunden.",
        "latenz_t0": "Zeitstempel der amtlichen Beobachtung (METAR/NWS) gegen die Minutenserie.",
    },
    "Mentions": {
        "anker": "Zaehler im Sendungsfenster; endDate ist das Sendungsende. T-N davor misst, wie gut der Sprachgebrauch einer Person vorhersagbar ist.",
        "einpreisung": "Eigene Studie auf dieser Seite: fidelity=1, t0 = Beginn der Uebertragung; Median 0.2 min bis zur ersten Reaktion, 260.7 min bis Konvergenz (enthaelt die Zeit bis zur aufloesungsrelevanten Aussage).",
        "nicht_gemessen": "Nichts darueber hinaus — Mentions ist die einzige Kategorie mit systematischer Latenzmessung statt Einzelbeispielen.",
        "latenz_t0": "Sendungs-/Transkript-Zeitstempel (siehe mentions_latenz.json).",
    },
    "Other": {
        "anker": "Restbucket plus alle Kategorien unter der Mindestgroesse (min_markets). Die Mischung wechselt von Lauf zu Lauf.",
        "einpreisung": "Kein einheitlicher Mechanismus — der Typen-Split zeigt, was gerade drinliegt.",
        "nicht_gemessen": "Zahlen aus diesem Bucket nicht interpretieren; er existiert, damit duenne Kategorien die Bestenliste nicht kippen.",
        "latenz_t0": "—",
    },
}


def _settled_outcome(raw: Mapping[str, Any]) -> bool | None:
    """True/False when ``outcomePrices`` say Yes won/lost exactly, else None.

    Same rule as app.base_rate_study.event_lines: Polymarket writes "1" to the
    winner and "0" to the loser once resolved; anything else (0.5/0.5 refunds,
    still-trading prices) is not a settled outcome and is dropped.
    """

    outcomes = [str(v).strip().lower() for v in pm._as_list(raw.get("outcomes"))]
    prices = pm._as_list(raw.get("outcomePrices"))
    if outcomes[:2] != ["yes", "no"] or len(prices) < 2:
        return None
    try:
        yes_price = float(prices[0])
        no_price = float(prices[1])
    except (TypeError, ValueError):
        return None
    if (yes_price, no_price) == (1.0, 0.0):
        return True
    if (yes_price, no_price) == (0.0, 1.0):
        return False
    return None


def decision_time(end_time: Any, closed_time: Any) -> pd.Timestamp | None:
    """The earlier of end date and close time: when the question was decided.

    A market that resolves early (a team eliminated, a deadline met) closes
    long before its nominal end date, so ``endDate`` alone would read the
    price after the answer was known. A market that runs its full course
    closes one to three days after its end date (the UMA window), so
    ``closedTime`` alone would do the same. The minimum is the latest moment
    at which the outcome was still open. None without either stamp.
    """

    stamps = [s for s in (pm._safe_ts(end_time), pm._safe_ts(closed_time)) if s is not None]
    return min(stamps) if stamps else None


def market_rows_from_event(event: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Resolved binary markets of one raw Gamma event, ready for pricing.

    Each row: market_key, question, event_slug, event_title, tags, category,
    einpreisungstyp, vorzeitig, yes_token_id, won, decision_time, created_at,
    volume. ``vorzeitig`` is True when the market closed before its nominal
    end date — the early-resolution proxy: its decision anchor is the close,
    which lags the real-world deciding event, so short horizons there may
    read prices that already knew the answer. None when a stamp is missing.
    Markets without a settled Yes/No outcome, without a YES token or without
    a decision time are left out — none of them can be scored.
    """

    tags = list(event.get("tags") or []) if isinstance(event, Mapping) else []
    rows: list[dict[str, Any]] = []
    for market in pm.normalize_polymarket_event_markets(event):
        raw = market.get("raw") or {}
        if not raw.get("closed") and not market.get("closed"):
            continue
        won = _settled_outcome(raw)
        if won is None:
            continue
        token = market.get("yes_token_id")
        if not token:
            continue
        end_ts = pm._safe_ts(market.get("end_time"))
        closed_ts = pm._safe_ts(market.get("closed_time"))
        decided = decision_time(market.get("end_time"), market.get("closed_time"))
        if decided is None:
            continue
        title = str(market.get("title") or "")
        row = {
            "market_key": str(market.get("market_key") or ""),
            "question": title,
            "event_slug": str(market.get("event_slug") or event.get("slug") or ""),
            "event_title": str(event.get("title") or ""),
            "tags": [str(t.get("label", "")) if isinstance(t, Mapping) else str(t) for t in tags],
            "category": classify_category(title, tags, market.get("category")),
            "yes_token_id": str(token),
            "won": bool(won),
            "decision_time": decided,
            "created_at": market.get("created_at") or market.get("start_time"),
            "volume": float(market.get("volume") or 0.0),
            "vorzeitig": bool(closed_ts < end_ts) if (end_ts is not None and closed_ts is not None) else None,
        }
        row["einpreisungstyp"] = einpreisungstyp(title, row["category"], lifetime_days(row))
        rows.append(row)
    return rows


def lifetime_days(row: Mapping[str, Any]) -> float | None:
    """Days between creation and decision time; None when either stamp is missing."""

    created = pm._safe_ts(row.get("created_at"))
    decided = pm._safe_ts(row.get("decision_time"))
    if created is None or decided is None:
        return None
    return float((decided - created).total_seconds()) / 86400.0


def sample_bucket(row: Mapping[str, Any], long_life_days: float) -> str:
    """Counting key for the per-category caps: ``<category>`` or ``<category>|short``.

    Markets that lived at least ``long_life_days`` can carry a T-7 price and
    fill the main cap; shorter-lived ones (a game created three days out, a
    daily price line) count only at the near horizons and get their own,
    smaller cap so they neither crowd out the long-lived sample nor vanish.
    """

    category = str(row.get("category") or OTHER)
    life = lifetime_days(row)
    if life is not None and life < float(long_life_days):
        return f"{category}|short"
    return category


def select_markets(
    rows: Iterable[Mapping[str, Any]],
    max_per_category: int,
    max_per_event: int,
    min_volume: float,
    taken: Mapping[str, int] | None = None,
    *,
    min_life_days: float = 1.0,
    long_life_days: float = 7.0,
    max_short_per_category: int | None = None,
) -> list[dict[str, Any]]:
    """Cap one event's markets per event and per category, highest volume first.

    ``taken`` is the running count per sample bucket across earlier events
    (see ``sample_bucket``); the caller carries it forward from the return
    value. The per-event cap keeps a 60-line "World Cup winner" event from
    filling the sports bucket with correlated long shots; the per-category
    caps bound the price fetch. Markets that lived less than
    ``min_life_days`` cannot have a price at any horizon and are skipped;
    ``max_short_per_category`` (default half the main cap) bounds the
    short-lived bucket.
    """

    taken = dict(taken or {})
    short_cap = int(max_short_per_category) if max_short_per_category is not None else max(1, int(max_per_category) // 2)
    ordered = sorted(rows, key=lambda r: float(r.get("volume") or 0.0), reverse=True)
    picked: list[dict[str, Any]] = []
    per_event = 0
    for row in ordered:
        if per_event >= max_per_event:
            break
        if float(row.get("volume") or 0.0) < float(min_volume):
            continue
        life = lifetime_days(row)
        if life is not None and life < float(min_life_days):
            continue
        bucket = sample_bucket(row, long_life_days)
        cap = short_cap if bucket.endswith("|short") else int(max_per_category)
        if taken.get(bucket, 0) >= cap:
            continue
        picked.append(dict(row))
        taken[bucket] = taken.get(bucket, 0) + 1
        per_event += 1
    return picked


def caps_reached(taken: Mapping[str, int], max_per_category: int, categories: Sequence[str] = CATEGORIES) -> bool:
    """True once every named category (Other excluded) holds ``max_per_category`` long-lived markets."""

    return all(int(taken.get(c, 0)) >= int(max_per_category) for c in categories if c != OTHER)


def price_at_horizon(history: pd.DataFrame | None, decision: Any, days: float) -> float | None:
    """Last price at or before ``days`` days ahead of ``decision`` (None if unknown)."""

    return brs.price_at_lead_time(history, decision, float(days) * 24.0)


def horizon_prices(
    hourly: pd.DataFrame | None,
    daily: pd.DataFrame | None,
    decision: Any,
    horizons: Sequence[int],
) -> dict[int, float | None]:
    """YES price per horizon: hourly series first, daily whole-life series as fallback."""

    out: dict[int, float | None] = {}
    for days in horizons:
        price = price_at_horizon(hourly, decision, days)
        if price is None:
            price = price_at_horizon(daily, decision, days)
        out[int(days)] = price
    return out


def _brier(price: float, won: bool) -> float:
    return (float(price) - (1.0 if won else 0.0)) ** 2


def _hit(price: float, won: bool) -> bool:
    return (float(price) >= 0.5) == bool(won)


def _round(value: float | None, digits: int = 4) -> float | None:
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return None
    return round(float(value), digits)


#: A YES price at or beyond these bounds means the market already treated
#: the question as settled; the share of such markets is reported next to
#: every Brier score because a bucket of 0.01 long shots scores near-perfect
#: without anyone having forecast anything.
DECIDED_BOUNDS = (0.05, 0.95)


def _priced(obs: Sequence[Mapping[str, Any]], days: int) -> list[tuple[float, bool]]:
    out: list[tuple[float, bool]] = []
    for o in obs:
        price = (o.get("prices") or {}).get(days)
        if price is None:
            price = (o.get("prices") or {}).get(str(days))
        if price is not None:
            out.append((float(price), bool(o["won"])))
    return out


def _brier_ci95(paare: Sequence[tuple[float, bool]]) -> list[float | None]:
    """95%-Intervall um den mittleren Brier, ueber die Einzelfehler.

    Der Brier ist ein Mittelwert von n Einzelwerten in [0, 1], also traegt er
    denselben Standardfehler wie jeder Mittelwert: ``sd / sqrt(n)``. Ohne das
    Intervall liest sich eine Rangfolge ueber zwoelf Kategorien und fuenf
    Horizonte als Befund, obwohl 60 Zellen aus demselben Ziehungsprozess
    schon von sich aus auseinanderlaufen. Unter zwei Beobachtungen gibt es
    keine Streuung zu schaetzen.
    """

    n = len(paare)
    if n < 2:
        return [None, None]
    fehler = [_brier(p, w) for p, w in paare]
    mittel = sum(fehler) / n
    sd = statistics.stdev(fehler)
    halb = 1.96 * sd / math.sqrt(n)
    return [_round(max(0.0, mittel - halb)), _round(min(1.0, mittel + halb))]


def _horizon_stats(obs: Sequence[Mapping[str, Any]], days: int) -> dict[str, Any]:
    priced = _priced(obs, days)
    n = len(priced)
    if not n:
        return {"horizont_tage": int(days), "brier": None, "brier_ci95": [None, None],
                "trefferquote": None, "n": 0, "anteil_entschieden": None,
                "brier_offen": None, "brier_offen_ci95": [None, None],
                "trefferquote_offen": None, "n_offen": 0}
    brier = sum(_brier(p, w) for p, w in priced) / n
    hits = sum(1 for p, w in priced if _hit(p, w))
    low, high = quant.wilson_interval(hits, n)
    # The same figures over genuinely open questions only: a bucket full of
    # 0.01 long shots or 0.99 near-certainties scores a near-perfect Brier
    # without anyone having forecast anything, so cross-category comparison
    # belongs on the open subset.
    offen = [(p, w) for p, w in priced if DECIDED_BOUNDS[0] < p < DECIDED_BOUNDS[1]]
    return {
        "horizont_tage": int(days),
        "brier": _round(brier),
        "brier_ci95": _brier_ci95(priced),
        "trefferquote": _round(hits / n),
        "trefferquote_ci95": [_round(low), _round(high)],
        "n": n,
        "anteil_entschieden": _round((n - len(offen)) / n),
        "brier_offen": _round(sum(_brier(p, w) for p, w in offen) / len(offen)) if offen else None,
        "brier_offen_ci95": _brier_ci95(offen),
        "trefferquote_offen": _round(sum(1 for p, w in offen if _hit(p, w)) / len(offen)) if offen else None,
        "n_offen": len(offen),
    }


def calibration_bins(
    obs: Sequence[Mapping[str, Any]], days: int = 7, edges: Sequence[float] = DEFAULT_BIN_EDGES
) -> list[dict[str, Any]]:
    """Predicted (mean price) vs realised (share won) per probability bin, with n.

    Bins are left-closed, the last one closed on both ends. Empty bins are
    omitted rather than shown as zero — a bin nobody priced in has no
    realised frequency.
    """

    rows: list[dict[str, Any]] = []
    priced = _priced(obs, days)
    for i in range(len(edges) - 1):
        lo, hi = float(edges[i]), float(edges[i + 1])
        last = i == len(edges) - 2
        members = [(p, w) for p, w in priced if (lo <= p < hi) or (last and p == hi)]
        if not members:
            continue
        n = len(members)
        wins = sum(1 for _, w in members if w)
        low, high = quant.wilson_interval(wins, n)
        rows.append(
            {
                "von": lo,
                "bis": hi,
                "vorhergesagt": _round(sum(p for p, _ in members) / n),
                "realisiert": _round(wins / n),
                "realisiert_ci95": [_round(low), _round(high)],
                "n": n,
            }
        )
    return rows


def category_table(
    obs: Sequence[Mapping[str, Any]],
    horizons: Sequence[int] = DEFAULT_HORIZONS,
    min_markets: int = 1,
    calibration_horizon: int = 7,
) -> list[dict[str, Any]]:
    """One row per category with the legacy keys plus ``horizonte`` and ``kalibrierung``.

    ``obs`` rows: ``{"category", "won", "volume", "prices": {days: price|None}}``.
    A market counts for a category when it has a price at at least one
    horizon; categories under ``min_markets`` are folded into ``Other`` so a
    three-market bucket cannot top the best/worst list. Legacy keys
    (``brier_t7`` etc.) are None when that horizon has no observation.
    """

    horizons = [int(h) for h in horizons]
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for o in obs:
        if not any(_priced([o], h) for h in horizons):
            continue
        grouped.setdefault(str(o.get("category") or OTHER), []).append(o)

    # Fold thin categories into Other before scoring.
    folded: dict[str, list[Mapping[str, Any]]] = {}
    for name, members in grouped.items():
        target = name if (len(members) >= int(min_markets) or name == OTHER) else OTHER
        folded.setdefault(target, []).extend(members)

    rows: list[dict[str, Any]] = []
    order = {name: i for i, name in enumerate(CATEGORIES)}
    for name in sorted(folded, key=lambda k: (order.get(k, len(order)), k)):
        members = folded[name]
        stats = {h: _horizon_stats(members, h) for h in horizons}
        volumes = [float(m.get("volume") or 0.0) for m in members]
        median_vol = statistics.median(volumes) if volumes else None
        t7 = stats.get(7, _horizon_stats(members, 7))
        t1 = stats.get(1, _horizon_stats(members, 1))
        vorzeitig = [m.get("vorzeitig") for m in members if m.get("vorzeitig") is not None]
        rows.append(
            {
                "kategorie": name,
                "brier_t7": t7["brier"],
                "trefferquote_t7": t7["trefferquote"],
                "brier_t1": t1["brier"],
                "trefferquote_t1": t1["trefferquote"],
                "n_maerkte": len(members),
                "n_t7": t7["n"],
                "n_t1": t1["n"],
                "anteil_entschieden_t7": t7.get("anteil_entschieden"),
                "brier_t7_offen": t7.get("brier_offen"),
                "n_t7_offen": t7.get("n_offen"),
                "anteil_vorzeitig": _round(sum(1 for v in vorzeitig if v) / len(vorzeitig)) if vorzeitig else None,
                "median_volumen_usd": _round(median_vol, 2),
                "typen": typ_breakdown(members),
                "horizonte": [stats[h] for h in horizons],
                "kalibrierung": {
                    "horizont_tage": int(calibration_horizon),
                    "bins": calibration_bins(members, calibration_horizon),
                },
            }
        )
    return rows


def typ_breakdown(members: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Per pricing mechanism (``einpreisungstyp``): n and Brier at T-7/T-1.

    Empty when no member carries the field (payloads scored before the
    typology existed) — an all-"unklar" table would look like a finding.
    Sorted by n descending so the dominant mechanism reads first.
    """

    if not any("einpreisungstyp" in m for m in members):
        return []
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for m in members:
        grouped.setdefault(str(m.get("einpreisungstyp") or "unklar"), []).append(m)
    rows: list[dict[str, Any]] = []
    for typ in sorted(grouped, key=lambda t: (-len(grouped[t]), t)):
        t7 = _horizon_stats(grouped[typ], 7)
        t1 = _horizon_stats(grouped[typ], 1)
        rows.append({
            "typ": typ,
            "n": len(grouped[typ]),
            "brier_t7": t7["brier"],
            "n_t7": t7["n"],
            "brier_t1": t1["brier"],
            "n_t1": t1["n"],
        })
    return rows


def rescore_observations(
    candidates: Sequence[Mapping[str, Any]],
    observations: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Cached observations re-classified under the current taxonomy and typology.

    ``candidates`` (the sweep cache) carries the event tags that the slim
    observation rows drop; the join runs over market_key. Prices, outcomes
    and volumes stay exactly as cached — only ``category`` and
    ``einpreisungstyp`` are recomputed, so a taxonomy change never needs a
    refetch. An observation without a matching candidate keeps its stored
    category and is typed from title alone.
    """

    by_key = {str(c.get("market_key") or ""): c for c in candidates}
    out: list[dict[str, Any]] = []
    for o in observations:
        cand = by_key.get(str(o.get("market_key") or ""), {})
        title = str(o.get("question") or cand.get("question") or "")
        tags = cand.get("tags")
        row = dict(o)
        row["category"] = classify_category(title, tags) if tags is not None else str(o.get("category") or OTHER)
        row["einpreisungstyp"] = einpreisungstyp(title, row["category"], o.get("lifetime_days"))
        if "vorzeitig" not in row and cand.get("vorzeitig") is not None:
            row["vorzeitig"] = cand.get("vorzeitig")
        out.append(row)
    return out


def compose_payload(
    kategorien: Sequence[Mapping[str, Any]],
    previous: Mapping[str, Any] | None,
    *,
    stand_utc: str,
    horizons: Sequence[int],
    quelle: Mapping[str, Any],
    hinweis: str,
) -> dict[str, Any]:
    """The published kategorie_karte.json: new table, thesis figures preserved.

    ``beispiele`` (the pricing-speed examples the mentions page reads) are
    copied unchanged from ``previous``. The old ``kategorien`` and ``hinweis``
    move to ``thesis_snapshot`` — once. A re-run that finds a snapshot already
    there keeps that snapshot instead of snapshotting its own output.
    """

    previous = dict(previous or {})
    snapshot = previous.get("thesis_snapshot")
    if not isinstance(snapshot, Mapping):
        snapshot = {
            "hinweis": previous.get("hinweis"),
            "stand_utc": previous.get("stand_utc"),
            "kategorien": list(previous.get("kategorien") or []),
        }
    return {
        "hinweis": str(hinweis),
        "stand_utc": str(stand_utc),
        "provenienz": PROVENIENZ,
        "horizonte_tage": [int(h) for h in horizons],
        "quelle": dict(quelle),
        "kategorien": [dict(k) for k in kategorien],
        "beispiele": list(previous.get("beispiele") or []),
        "thesis_snapshot": dict(snapshot),
    }


def sample_summary(kategorien: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Totals for the log line and the ``quelle`` block: markets and n per horizon.

    ``n_vergleiche`` counts the scored category-by-horizon cells. It belongs
    next to any "which category prices best" read: the best of sixty cells is
    the maximum of sixty draws, and the gap to the runner-up is what that many
    draws produce on their own. The per-cell intervals (``brier_ci95``) are
    what settles whether a difference is one at all.
    """

    total = sum(int(k.get("n_maerkte") or 0) for k in kategorien)
    per_horizon: dict[str, int] = {}
    vergleiche = 0
    for k in kategorien:
        for h in k.get("horizonte") or []:
            key = f"T-{int(h.get('horizont_tage', 0))}"
            per_horizon[key] = per_horizon.get(key, 0) + int(h.get("n") or 0)
            if int(h.get("n") or 0) > 0:
                vergleiche += 1
    return {
        "n_maerkte": total,
        "n_kategorien": len(kategorien),
        "n_je_horizont": per_horizon,
        "n_vergleiche": vergleiche,
    }
