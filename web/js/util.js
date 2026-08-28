// Shared formatting and mapping helpers, ported from the design reference.

import { MONO as M } from './ui.js';
// Owner-declared one-time deposit into the live-run wallet, verifiable
// on-chain via the wallet's USDC transfers. The public Data API cannot see
// deposits, so the figure travels with the pipeline (WALLET_DEPOSITS_USD in
// the refresh workflow) AND with the frontend: an older API host can still
// serve a ledger without einzahlungen_usd, and the ROI basis must never
// silently fall back to the buy volume.
export const EINZAHLUNGEN_USD = 300;

// Der Wallet-ROI misst den Netto-Cashflow gegen die Einzahlung. Was noch in
// offenen Positionen steckt, ist weder eingezahlt noch zurueckgeflossen und
// steht deshalb in keiner der beiden Zahlen. Solange das Wallet offene
// Positionen haelt, gehoert dieser Satz an die Kachel.
export function offeneNichtDrin(aggregat) {
  const offen = aggregat && aggregat.positionen ? +aggregat.positionen.open || 0 : 0;
  if (!offen) return '';
  return ' · ' + offen + ' open position' + (offen === 1 ? '' : 's') + ' not in it';
}

export function num(n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ','); }

export function money(n) {
  if (n >= 1000000) return '$' + (n / 1000000).toFixed(n >= 10000000 ? 1 : 2) + 'm';
  if (n >= 1000) return '$' + (n / 1000).toFixed(n >= 100000 ? 0 : 1) + 'k';
  return '$' + n.toFixed(0);
}

// Volumen ist nicht auf beiden Venues dasselbe. Polymarket meldet Dollar,
// Kalshi meldet die Zahl gehandelter Kontrakte: gemessen am 2026-08-28 war
// volume_fp eines Kalshi-Marktes exakt die Summe der count_fp aller seiner
// Trades, nicht die Summe aus count_fp mal Preis. Ein Kontrakt zahlt bei
// Aufloesung einen Dollar und wird zu seinem Preis p gehandelt, also
// ueberzeichnet die Stueckzahl den Umsatz um 1/p, bei 50 Cent also um das
// Doppelte. Herleitung in app/venue_units.py.
export const VOLUME_UNIT_USD = 'usd';
export const VOLUME_UNIT_CONTRACTS = 'contracts';

const VENUE_VOLUME_UNITS = { polymarket: VOLUME_UNIT_USD, kalshi: VOLUME_UNIT_CONTRACTS };

export function volumeUnit(platform) {
  return VENUE_VOLUME_UNITS[String(platform == null ? '' : platform).trim().toLowerCase()] || '';
}

// Stueckzahlen als Stueckzahlen. Nie mit einem Dollarzeichen davor, denn
// dann behauptet die Zahl einen Betrag, den sie nicht misst.
export function contracts(n) {
  if (n == null || !isFinite(n)) return '—';
  if (n >= 1000000) return (n / 1000000).toFixed(n >= 10000000 ? 1 : 2) + 'm contracts';
  if (n >= 1000) return (n / 1000).toFixed(n >= 100000 ? 0 : 1) + 'k contracts';
  return num(Math.round(n)) + ' contracts';
}

// Eine Volumenzahl in der Einheit, die sie tatsaechlich hat. Eine Venue ohne
// bekannte Einheit bekommt die nackte Zahl statt einer geratenen.
export function volume(n, platform) {
  if (n == null || !isFinite(n)) return '—';
  const unit = volumeUnit(platform);
  if (unit === VOLUME_UNIT_USD) return money(n);
  if (unit === VOLUME_UNIT_CONTRACTS) return contracts(n);
  return num(Math.round(n));
}

export function esc(v) {
  return String(v == null ? '' : v)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// spark(arr) stand hier: eine zweite Punktefunktion fuer eine feste 78x26-Box,
// ohne Guard fuer arr.length < 2 (bei einem Wert eine Division durch Null) und
// ohne eine einzige Aufrufstelle. seriesPoints darunter tut dasselbe, nimmt
// aber Breite und Hoehe als Argumente und faengt den Ein-Wert-Fall ab. Zwei
// Funktionen fuer eine Aufgabe, von denen eine nie gerufen wird, sind eine
// Falle: irgendwann ruft jemand die falsche.

// Der Generator curve(seed, n, w, h, drift, vol) stand hier: ein
// deterministischer Zufallspfad mit einstellbarem Aufwaertsdrift, der jede
// Kurve der Seite gezeichnet hat, wenn keine Daten da waren. Er ist weg, und
// zwar samt Funktion — solange er im Modul liegt, ruft ihn wieder jemand auf.
// Ein Diagramm entsteht nur noch aus einer echten Serie, ueber seriesPoints.

// Render an array of numbers as SVG polyline points inside a viewBox.
export function seriesPoints(values, width, height) {
  if (!values || values.length < 2) return '';
  const max = Math.max(...values), min = Math.min(...values);
  const span = max - min || 1;
  return values.map((v, i) =>
    ((i * width) / (values.length - 1)).toFixed(1) + ',' + (height - 10 - ((v - min) / span) * (height - 30)).toFixed(1)
  ).join(' ');
}

// Herkunft eines Datenblocks in einen Satz, den ein Leser ohne Kenntnis des
// Codes versteht. Drei Zustaende, und keiner davon darf als Zahl erscheinen:
// noch keine Antwort, eine leere Antwort und eine fehlgeschlagene Antwort
// sind drei verschiedene Dinge, und "kein Ergebnis" ist selbst ein Ergebnis.
export function herkunftSatz(herkunft, endpunkt) {
  const quelle = herkunft && herkunft.quelle;
  if (quelle === 'fehler') {
    return endpunkt + ' did not answer: ' + ((herkunft && herkunft.fehler) || 'unknown error')
      + '. Nothing is shown rather than a stale or invented figure.';
  }
  if (quelle === 'leer') {
    return endpunkt + ' answered, and there was nothing in this window. That is the result, not a gap.';
  }
  return 'Waiting for ' + endpunkt + '. Nothing is shown until it answers.';
}

// Alle Venues, die das Terminal liest. Die Kopfzeile nannte sie fest
// verdrahtet ("LIVE · POLYMARKET + KALSHI") und behauptete damit beide, auch
// wenn nur eine geantwortet hatte.
export const VENUES = ['Polymarket', 'Kalshi'];

// Die Statuszeile der Kopfleiste. Sie nennt die Venues, die geantwortet
// haben, und benennt die fehlende, statt beide zu behaupten.
//
// Der Fall, um den es geht: /api/tape faengt einen Parserfehler auf einer
// Venue ab, damit die andere nicht mit ausfaellt, und liefert eine halbe
// Antwort. Ohne diese Zeile war die halbe Antwort von einer ganzen nicht zu
// unterscheiden, und die Seite meldete LIVE auf beiden Venues, waehrend die
// Haelfte der Prints fehlte.
export function liveStatusLabel(live, venuesMissing) {
  if (live === 'error') return 'API OFFLINE · LAST KNOWN STATE';
  if (live === 'offline') return 'API NOT REACHABLE · RESEARCH FROM PUBLISHED FILES';
  if (live !== 'live') return 'WAITING FOR API';
  const fehlend = (venuesMissing || []).map((v) => String(v || '').trim()).filter(Boolean);
  if (!fehlend.length) return 'LIVE · ' + VENUES.join(' + ').toUpperCase();
  const da = VENUES.filter((v) => fehlend.indexOf(v) < 0);
  if (!da.length) return 'NO VENUE ANSWERING · ' + fehlend.join(' + ').toUpperCase() + ' FAILED';
  return 'PARTIAL · ' + da.join(' + ').toUpperCase() + ' ONLY · ' + fehlend.join(' + ').toUpperCase() + ' NOT ANSWERING';
}

// Ein Panel ohne Daten sagt, welche Quelle fehlt, und zeigt keine Zahl. Eine
// leere Flaeche kostet nichts; eine erfundene Kennzahl kostet die
// Glaubwuerdigkeit jeder echten Zahl daneben.
export function leerBlock(titel, satz) {
    return '<div style="padding:var(--sp-6)">'
    + '<div style="background:var(--panel); border:1px solid var(--line-2); border-radius:var(--r-panel); padding:var(--sp-6); max-width:760px">'
    + '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:.14em; color:var(--warn)">' + esc(titel) + '</div>'
    + '<div style="font-size:var(--t-body); color:var(--ink-3); margin-top:var(--sp-3); line-height:1.6">' + esc(satz) + '</div>'
    + '</div></div>';
}

// Der Seitenkopf allein, damit eine Seite ohne Daten trotzdem sagt, welche
// Seite sie ist, und darunter warum sie leer ist.
export function seitenKopf(kicker, titel, farbe) {
    return '<div style="padding:var(--sp-6) var(--sp-6) var(--sp-5); border-bottom:1px solid var(--line-2)">'
    + '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:.18em; color:' + farbe + '">' + esc(kicker) + '</div>'
    + '<h1 style="font-size:var(--t-head); line-height:1.25; margin:var(--sp-3) 0 0; font-weight:600; letter-spacing:-0.01em">'
    + esc(titel) + '</h1></div>';
}

// Eine Zeile dort, wo sonst Zeilen stehen wuerden. Kurz, weil sie mitten in
// einer Liste sitzt und nicht deren Platz einnehmen soll.
export function leerZeile(satz) {
    return '<div style="padding:var(--sp-6); ' + M + '; font-size:var(--t-small); color:var(--ink-3); line-height:1.6">'
    + esc(satz) + '</div>';
}

// Category vocabulary shared by Markets, Live tape and Whale flow. Kalshi's
// "Cross Category" is a container series for multi-event parlays, not a
// category — it folds into Other, as do empty and "uncategorized" labels.
export function liveCat(raw) {
  const c = String(raw || '').toLowerCase().trim();
  if (!c || /^(other|uncategorized|none|nan|cross[ -]?category)$/.test(c)) return 'Other';
  if (/macro|econ|rate|inflation|fed|finance/.test(c)) return 'Macro-Finance';
  if (/politic|election|senate|congress|geopol/.test(c)) return 'Politics';
  if (/crypto|bitcoin|eth/.test(c)) return 'Crypto';
  if (/sport|soccer|nfl|nba|football|world cup/.test(c)) return 'Sports';
  if (/weather|temp|hurricane/.test(c)) return 'Weather';
  if (/science|space|tech|ai/.test(c)) return 'Science';
  return String(raw).charAt(0).toUpperCase() + String(raw).slice(1).toLowerCase();
}

// Fixed order for category chip rows; anything else present in the data is
// appended alphabetically. Only categories that occur are offered.
export const CAT_ORDER = ['Politics', 'Macro-Finance', 'Sports', 'Crypto', 'Weather', 'Other'];

export function catChipsPresent(rows, key) {
  const seen = {};
  (rows || []).forEach((r) => { const c = r && r[key] ? String(r[key]) : 'Other'; seen[c] = true; });
  const known = CAT_ORDER.filter((c) => seen[c]);
  const rest = Object.keys(seen).filter((c) => CAT_ORDER.indexOf(c) < 0).sort();
  return known.concat(rest);
}

// Ends-in helper. Unknown dates stay unknown (days: null) — the earlier
// fallback of 365 days made every dateless market "open ended" in filters.
export function endsInfo(iso) {
  if (!iso) return { label: '—', days: null };
  const d = new Date(iso);
  if (isNaN(d)) return { label: '—', days: null };
  const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  const days = Math.max(0, Math.round((d - Date.now()) / 86400000));
  const far = d.getFullYear() > new Date().getFullYear();
  return { label: far ? months[d.getMonth()] + ' ' + d.getFullYear() : d.getDate() + ' ' + months[d.getMonth()], days };
}

// Signed dollar amount with two decimals: +$288.67 / -$12.00.
export function signedMoney(n, decimals) {
  const v = +n || 0;
  const d = decimals == null ? 2 : decimals;
  return (v >= 0 ? '+$' : '-$') + num(Math.abs(v).toFixed(d));
}

// "2026-08-16T23:32:04.678297+00:00" -> "2026-08-16 23:32 UTC"; short ISO dates pass through.
export function stempel(iso) {
  const s = String(iso || '');
  if (!s) return '';
  if (s.length <= 10) return s;
  return s.slice(0, 16).replace('T', ' ') + ' UTC';
}

export function shortWallet(w) {
  return w && String(w).length > 12 ? String(w).slice(0, 6) + '…' + String(w).slice(-3) : String(w || '');
}

// Map one /api/markets row into the shape every screen consumes.
export function mapMarket(r, i) {
  const yes = Math.round(((+r.yes_price || 0)) * 100);
  // change_1d from the API: the column is the one-day change, labelled 1D.
  const chg = Math.round(((+r.change_1d || 0)) * 100);
  const ends = endsInfo(r.end_time);
  // No sparkline: the API carries yesterday's change, not an intraday path.
  // A two-point line under a "TREND" heading read as a measured curve.
  return {
    id: String(r.market_key || r.ticker || 'live' + i),
    title: String(r.title || '—'),
    venue: String(r.platform || 'Polymarket'),
    cat: liveCat(r.filter_category || r.category),
    yes, chg,
    // Nur der Tageswert. Der frühere Rueckfall auf activity_volume (24h,
    // sonst Gesamtvolumen) setzte das Lebensvolumen unter die Ueberschrift
    // VOLUME 24H: ein Markt ohne Handel am Tag stand dort mit $4.2m und kam
    // durch den Filter "24h-Volumen > $1m". Ohne Handel ist der Tageswert
    // null, und null ist hier die Messung.
    vol: +r.volume_24h || 0,
    // Das Lebensvolumen als eigene Zahl, damit es nicht als Tageswert
    // auftritt und trotzdem nicht verloren geht.
    volTotal: +r.volume || +r.activity_volume || 0,
    liq: +r.liquidity || 0,
    ends: ends.label,
    url: r.url || '',
    // Unknown stays null. The earlier defaults (spread 5¢, age 100 days)
    // made filters on those fields operate on constants.
    _extra: {
      spread: r.spread != null && r.spread === r.spread ? Math.round(+r.spread * 100) : null,
      age: r.market_age_days != null && r.market_age_days === r.market_age_days ? Math.round(+r.market_age_days) : null,
      endsDays: ends.days
    }
  };
}

export function isWalletAddress(v) {
  return /^0x[0-9a-fA-F]{6,}$/.test(String(v || '').trim());
}

// Richtung eines Prints als eigenes Feld. Polymarket liefert BUY/SELL,
// Kalshi liefert in derselben Spalte die genommene Seite ("yes"/"no") —
// dort ist jeder Print ein Kauf des Takers, also BUY.
export function tradeDirection(side) {
  return String(side || '').trim().toUpperCase() === 'SELL' ? 'SELL' : 'BUY';
}

// Ergebnisname eines Prints, Schreibweise vereinheitlicht. Kalshi schreibt
// "yes"/"no" klein, Polymarket "Yes"/"No"; ohne diese Angleichung filtert
// die Auswahl OUTCOME = Yes jeden Kalshi-Print weg, weil sie auf dem
// zusammengesetzten Etikett "BUY yes" nach "Yes" sucht. Namen aus
// Mehrfachmaerkten (Teamnamen) bleiben, wie sie kommen.
export function tradeOutcome(outcome) {
  const roh = String(outcome == null ? '' : outcome).trim();
  if (!roh) return 'Yes';
  const klein = roh.toLowerCase();
  if (klein === 'yes') return 'Yes';
  if (klein === 'no') return 'No';
  return roh;
}

// Trifft ein Tape-Print die Filterauswahl der Live-Tape-Seite? Steht hier
// und nicht in app.js, damit dieselbe Regel testbar ist, die die Seite und
// jede Kennzahl darueber (TOTAL MOVED, FLOW PULSE, WHERE THE MONEY FLOWS)
// benutzt.
export function tapeMatches(t, s) {
  if (t.size < s.tapeMin) return false;
  if (s.tapeTracked && !t.tracked) return false;
  if (s.tapePlatform !== 'all' && t.venue !== s.tapePlatform) return false;
  // Richtung und Ergebnis als eigene Felder vergleichen (mapTrade). Vorher
  // lief beides ueber indexOf auf dem Etikett "BUY yes": das liess
  // OUTCOME = Yes jeden Kalshi-Print fallen (dort steht "yes" klein) und
  // liess OUTCOME = No jeden Print eines Marktes mit "November" durch.
  if (s.tapeSide !== 'all' && (t.dir || 'BUY') !== s.tapeSide) return false;
  if (s.tapeOutcome !== 'all' && (t.outcome || '') !== s.tapeOutcome) return false;
  if (s.tapeCat !== 'All' && (t.category || 'Other') !== s.tapeCat) return false;
  if (String(s.tapeQuery || '').trim()) {
    const tq = String(s.tapeQuery).trim().toLowerCase();
    if (t.market.toLowerCase().indexOf(tq) < 0 && t.wallet.toLowerCase().indexOf(tq) < 0) return false;
  }
  return true;
}

// Spanne, ueber die eine Menge von Prints summiert wurde, je Venue getrennt.
//
// Der oeffentliche Trade-Feed liefert die juengsten N Prints; wie lange die
// abdecken, haengt an der Aktivitaet. Auf dem Tape kommt dazu, dass beide
// Venues gleich viele Zeilen bekommen (api_views.balanced_head), damit die
// Kalshi-Mikrotrades die Polymarket-Prints nicht verdraengen. Dieselbe
// Zeilenzahl kann bei Kalshi Minuten und bei Polymarket Stunden bedeuten —
// eine Summe "TOTAL MOVED" ueber beide ist ohne diese Angabe nicht
// einzuordnen. Rueckgabe in Minuten; ohne verwertbare Zeit null.
export function tapeFenster(prints) {
  const gueltig = (prints || []).filter((t) => typeof t.mins === 'number' && t.mins < 999);
  if (!gueltig.length) return null;
  const spanne = (rows) => ({
    prints: rows.length,
    minuten: Math.max(...rows.map((t) => t.mins)) - Math.min(...rows.map((t) => t.mins))
  });
  const venues = {};
  gueltig.forEach((t) => { (venues[t.venue || 'Polymarket'] || (venues[t.venue || 'Polymarket'] = [])).push(t); });
  return {
    ...spanne(gueltig),
    jeVenue: Object.keys(venues).sort().map((v) => ({ venue: v, ...spanne(venues[v]) }))
  };
}

// Eine Minutenzahl als kurze Dauer: 0 min, 42 min, 3.5 h, 2.1 d.
export function dauer(minuten) {
  const m = Math.max(0, +minuten || 0);
  if (m < 1) return '<1 min';
  if (m < 90) return Math.round(m) + ' min';
  if (m < 60 * 36) return (m / 60).toFixed(1) + ' h';
  return (m / 1440).toFixed(1) + ' d';
}

// Der Fenstersatz als Text. Nennt die Venues einzeln, sobald es mehr als
// eine gibt, weil genau dort die Spannen auseinanderlaufen.
export function fensterSatz(fenster) {
  if (!fenster) return '';
  const je = fenster.jeVenue.map((v) => v.venue + ' ' + dauer(v.minuten) + ' (' + v.prints + ')').join(' · ');
  const kopf = 'Window: ' + dauer(fenster.minuten) + ' · ' + fenster.prints + ' prints';
  return fenster.jeVenue.length > 1 ? kopf + ' — ' + je : kopf;
}

// Der Stempel einer Studie und die Publish-Uhr sind zwei verschiedene
// Aussagen, und bis hierher hat die zweite die erste verschluckt.
//
// study.stamp aus studies.js sagt, was die Studie IST: "frozen 2026-06-30",
// "pre-registered 2026-05-02 · completed 2026-08-01", "paper log · archived
// 2026-08-07". Das ist eine Eigenschaft der Studie. Sie aendert sich nicht,
// wenn jemand die Nutzlast neu schreibt. payload.stand_utc sagt nur, wann
// zuletzt publiziert wurde.
//
// Vorher stand hier ueberall "stand_utc ? uhr : study.stamp". Jede publizierte
// Nutzlast traegt ein stand_utc, also gewann immer die Uhr, und damit erschien
// kein einziger Stempel aus studies.js je auf einer Seite: die
// Praeregistrierung des Piloten stand nirgends, die Einfrierdaten standen
// nirgends, und die beiden archivierten Studien sagten nicht, dass sie
// archiviert sind, waehrend die Seitenleiste sie unter STUDIES · FROZEN
// fuehrte. Bei einem Stueck, dessen Argument gerade die Vorregistrierung ist,
// war das die teuerste Zeile der Datei.
//
// Jetzt stehen beide untereinander: der Stempel als Chip, die Uhr als Zeile
// darunter. Fehlt eines von beiden, steht das andere allein.
export function publishZeit(payload) {
  return payload && payload.stand_utc
    ? String(payload.stand_utc).slice(0, 16).replace('T', ' ') + ' UTC' : '';
}

export function stempelBlock(study, payload) {
  const fest = study && study.stamp ? String(study.stamp) : '';
  const uhr = publishZeit(payload);
  const chip = M + '; font-size:var(--t-micro); color:var(--ink-3); border:1px solid var(--line-1);'
    + ' border-radius:var(--r-control); padding:var(--sp-2) var(--sp-4); white-space:nowrap';
  if (!fest && !uhr) return '';
  if (!fest) return '<div style="' + chip + '">' + esc(uhr) + '</div>';
  return '<div style="display:flex; flex-direction:column; align-items:flex-end; gap:var(--sp-2)">'
    + '<div style="' + chip + '">' + esc(fest) + '</div>'
    + (uhr ? '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-4); white-space:nowrap">published ' + esc(uhr) + '</div>' : '')
    + '</div>';
}

// Map one /api/tape row into the tape-row shape.
export function mapTrade(r) {
  const t = r.time ? new Date(r.time) : null;
  const mins = t && !isNaN(t) ? Math.max(0, Math.round((Date.now() - t) / 60000)) : 999;
  const ago = mins < 1 ? 'just now' : mins < 60 ? mins + ' min ago' : Math.round(mins / 60) + ' h ago';
  const dir = tradeDirection(r.side);
  const outcome = tradeOutcome(r.outcome);
  return {
    ago, mins,
    // Roher Zeitstempel als stabiler Schluessel: "ago" wandert mit jeder
    // Antwort, der Print selbst bleibt derselbe.
    ts: r.time ? String(r.time) : '',
    // Kalshi publishes no wallet identities: its rows carry the literal
    // "Not public". That is no wallet, so it must not become one in the
    // grouping on Whale flow — it stays a dash and the page says why.
    wallet: String(r.name || r.pseudonym || '') || (isWalletAddress(r.proxyWallet || r.wallet) ? shortWallet(r.proxyWallet || r.wallet) : '') || '—',
    walletAddress: isWalletAddress(r.proxyWallet || r.wallet) ? String(r.proxyWallet || r.wallet) : '',
    market: String(r.title || r.market || '—'),
    // Markt-Schluessel (conditionId bzw. Kalshi-Ticker), damit Whale flow
    // Maerkte zaehlen kann, ohne zwei Titel fuer denselben Markt zu halten.
    marketKey: String(r.market_key || r.ticker || r.title || ''),
    // Die Kategorie kommt vom Server (/api/tape reichert sie aus dem
    // Marktuniversum bzw. der Titel-Heuristik an). Ohne Feld heisst es
    // "Other" — kein Nachschlagen ueber den Titel in den 250 geladenen
    // Maerkten mehr, das traf fast nie und machte alles zu "Other".
    category: r.category ? liveCat(r.category) : 'Other',
    // Richtung und Ergebnis stehen einzeln da; "side" bleibt nur das
    // Etikett fuer die Anzeige. Filter und Summen lesen dir/outcome, nicht
    // Teilzeichenketten des Etiketts: "BUY November" enthaelt "No".
    dir,
    outcome,
    side: dir + ' ' + outcome,
    price: ((+r.price || 0) * 100).toFixed(1) + '¢',
    size: +r.notional || Math.round((+r.size || 0) * (+r.price || 0)) || 0,
    venue: String(r.platform || 'Polymarket'),
    tracked: false
  };
}
