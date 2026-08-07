// Shared formatting and mapping helpers, ported from the design reference.

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
  const M = "font-family:'JetBrains Mono',monospace";
  return '<div style="padding:26px 24px">'
    + '<div style="background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:12px; padding:20px 22px; max-width:760px">'
    + '<div style="' + M + '; font-size:10px; letter-spacing:.14em; color:#F5A623">' + esc(titel) + '</div>'
    + '<div style="font-size:13px; color:rgba(255,255,255,.6); margin-top:9px; line-height:1.6">' + esc(satz) + '</div>'
    + '</div></div>';
}

// Der Seitenkopf allein, damit eine Seite ohne Daten trotzdem sagt, welche
// Seite sie ist, und darunter warum sie leer ist.
export function seitenKopf(kicker, titel, farbe) {
  const M = "font-family:'JetBrains Mono',monospace";
  return '<div style="padding:20px 24px 14px; border-bottom:1px solid rgba(255,255,255,.09)">'
    + '<div style="' + M + '; font-size:10px; letter-spacing:.18em; color:' + farbe + '">' + esc(kicker) + '</div>'
    + '<div style="font-family:\'Instrument Serif\',serif; font-size:30px; line-height:1.1; margin-top:5px">'
    + esc(titel) + '</div></div>';
}

// Eine Zeile dort, wo sonst Zeilen stehen wuerden. Kurz, weil sie mitten in
// einer Liste sitzt und nicht deren Platz einnehmen soll.
export function leerZeile(satz) {
  const M = "font-family:'JetBrains Mono',monospace";
  return '<div style="padding:22px 20px; ' + M + '; font-size:11.5px; color:rgba(255,255,255,.42); line-height:1.6">'
    + esc(satz) + '</div>';
}

export function liveCat(raw) {
  const c = String(raw || '').toLowerCase();
  if (/macro|econ|rate|inflation|fed/.test(c)) return 'Macro';
  if (/politic|election|senate|congress|geopol/.test(c)) return 'Politics';
  if (/crypto|bitcoin|eth/.test(c)) return 'Crypto';
  if (/sport|soccer|nfl|nba|football|world cup/.test(c)) return 'Sports';
  if (/science|space|tech|ai/.test(c)) return 'Science';
  return raw ? String(raw).charAt(0).toUpperCase() + String(raw).slice(1).toLowerCase() : 'Other';
}

export function endsInfo(iso) {
  if (!iso) return { label: '—', days: 365 };
  const d = new Date(iso);
  if (isNaN(d)) return { label: '—', days: 365 };
  const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  const days = Math.max(0, Math.round((d - Date.now()) / 86400000));
  const far = d.getFullYear() > new Date().getFullYear();
  return { label: far ? months[d.getMonth()] + ' ' + d.getFullYear() : d.getDate() + ' ' + months[d.getMonth()], days };
}

export function shortWallet(w) {
  return w && String(w).length > 12 ? String(w).slice(0, 6) + '…' + String(w).slice(-3) : String(w || '');
}

// Map one /api/markets row into the shape every screen consumes.
export function mapMarket(r, i) {
  const yes = Math.round(((+r.yes_price || 0)) * 100);
  const chg = Math.round(((+r.change_1d || 0)) * 100);
  const ends = endsInfo(r.end_time);
  const from = Math.min(96, Math.max(4, yes - chg));
  // Zwei Punkte, gerade verbunden: gestern gegen heute. Hier lag vorher ein
  // Wackeln aus (k * 37 + i * 13) % 5 auf der Linie — ein erfundener
  // Intraday-Verlauf, den niemand gemessen hat, unter der Spalte TREND 24H.
  // Die 1d-Aenderung ist bekannt, der Weg dorthin nicht.
  const sparkArr = [from, yes].map((v) => Math.round(50 - Math.min(96, Math.max(4, v)) / 2));
  return {
    id: String(r.market_key || r.ticker || 'live' + i),
    title: String(r.title || '—'),
    venue: String(r.platform || 'Polymarket'),
    cat: liveCat(r.filter_category || r.category),
    yes, chg,
    vol: +r.volume_24h || +r.activity_volume || 0,
    liq: +r.liquidity || 0,
    ends: ends.label,
    url: r.url || '',
    spark: sparkArr,
    _extra: {
      spread: r.spread != null ? Math.round(+r.spread * 100) : 5,
      age: r.market_age_days != null ? Math.round(+r.market_age_days) : 100,
      endsDays: ends.days, saved: false, pos: false
    }
  };
}

// Map one /api/tape row into the tape-row shape.
export function mapTrade(r) {
  const t = r.time ? new Date(r.time) : null;
  const mins = t && !isNaN(t) ? Math.max(0, Math.round((Date.now() - t) / 60000)) : 999;
  const ago = mins < 1 ? 'just now' : mins < 60 ? mins + ' min ago' : Math.round(mins / 60) + ' h ago';
  return {
    ago, mins,
    wallet: String(r.name || r.pseudonym || '') || shortWallet(r.proxyWallet || r.wallet) || '—',
    walletAddress: String(r.proxyWallet || r.wallet || ''),
    market: String(r.title || r.market || '—'),
    side: (String(r.side || 'BUY').toUpperCase() === 'SELL' ? 'SELL ' : 'BUY ') + (String(r.outcome || 'Yes')),
    price: ((+r.price || 0) * 100).toFixed(1) + '¢',
    size: +r.notional || Math.round((+r.size || 0) * (+r.price || 0)) || 0,
    venue: String(r.platform || 'Polymarket'),
    tracked: false
  };
}
