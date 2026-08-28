// Shared formatting and mapping helpers, ported from the design reference.

// Owner-declared one-time deposit into the live-run wallet, verifiable
// on-chain via the wallet's USDC transfers. The public Data API cannot see
// deposits, so the figure travels with the pipeline (WALLET_DEPOSITS_USD in
// the refresh workflow) AND with the frontend: an older API host can still
// serve a ledger without einzahlungen_usd, and the ROI basis must never
// silently fall back to the buy volume.
export const EINZAHLUNGEN_USD = 300;

export function num(n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ','); }

export function money(n) {
  if (n >= 1000000) return '$' + (n / 1000000).toFixed(n >= 10000000 ? 1 : 2) + 'm';
  if (n >= 1000) return '$' + (n / 1000).toFixed(n >= 100000 ? 0 : 1) + 'k';
  return '$' + n.toFixed(0);
}

export function esc(v) {
  return String(v == null ? '' : v)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

export function spark(arr) {
  const max = Math.max(...arr), min = Math.min(...arr);
  const span = max - min || 1;
  return arr.map((v, i) => (i * (78 / (arr.length - 1))).toFixed(1) + ',' + (3 + ((v - min) / span) * 20).toFixed(1)).join(' ');
}

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

// Ein Panel ohne Daten sagt, welche Quelle fehlt, und zeigt keine Zahl. Eine
// leere Flaeche kostet nichts; eine erfundene Kennzahl kostet die
// Glaubwuerdigkeit jeder echten Zahl daneben.
export function leerBlock(titel, satz) {
  const M = "font-family:'IBM Plex Mono',monospace";
  return '<div style="padding:26px 24px">'
    + '<div style="background:var(--panel); border:1px solid rgba(var(--ink),.09); border-radius:6px; padding:20px 22px; max-width:760px">'
    + '<div style="' + M + '; font-size:11px; letter-spacing:.14em; color:var(--warn)">' + esc(titel) + '</div>'
    + '<div style="font-size:13px; color:rgba(var(--ink),.6); margin-top:9px; line-height:1.6">' + esc(satz) + '</div>'
    + '</div></div>';
}

// Der Seitenkopf allein, damit eine Seite ohne Daten trotzdem sagt, welche
// Seite sie ist, und darunter warum sie leer ist.
export function seitenKopf(kicker, titel, farbe) {
  const M = "font-family:'IBM Plex Mono',monospace";
  return '<div style="padding:20px 24px 14px; border-bottom:1px solid rgba(var(--ink),.09)">'
    + '<div style="' + M + '; font-size:11px; letter-spacing:.18em; color:' + farbe + '">' + esc(kicker) + '</div>'
    + '<h1 style="font-size:21px; line-height:1.25; margin:6px 0 0; font-weight:600; letter-spacing:-0.01em">'
    + esc(titel) + '</h1></div>';
}

// Eine Zeile dort, wo sonst Zeilen stehen wuerden. Kurz, weil sie mitten in
// einer Liste sitzt und nicht deren Platz einnehmen soll.
export function leerZeile(satz) {
  const M = "font-family:'IBM Plex Mono',monospace";
  return '<div style="padding:22px 20px; ' + M + '; font-size:11.5px; color:rgba(var(--ink),.6); line-height:1.6">'
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

// Map one /api/tape row into the tape-row shape.
export function mapTrade(r) {
  const t = r.time ? new Date(r.time) : null;
  const mins = t && !isNaN(t) ? Math.max(0, Math.round((Date.now() - t) / 60000)) : 999;
  const ago = mins < 1 ? 'just now' : mins < 60 ? mins + ' min ago' : Math.round(mins / 60) + ' h ago';
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
    side: (String(r.side || 'BUY').toUpperCase() === 'SELL' ? 'SELL ' : 'BUY ') + (String(r.outcome || 'Yes')),
    price: ((+r.price || 0) * 100).toFixed(1) + '¢',
    size: +r.notional || Math.round((+r.size || 0) * (+r.price || 0)) || 0,
    venue: String(r.platform || 'Polymarket'),
    tracked: false
  };
}
