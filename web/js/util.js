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

// Deterministic pseudo-random walk used for every chart in demo mode.
export function curve(seed, n, width, height, drift, vol) {
  let s = seed, v = 0, out = [], peak = 0, low = 0;
  const rnd = () => { s = (s * 1103515245 + 12345) % 2147483648; return s / 2147483648; };
  for (let i = 0; i < n; i++) {
    v += drift + (rnd() - 0.5) * vol;
    out.push(v);
    if (v > peak) peak = v;
    if (v - peak < low) low = v - peak;
  }
  const max = Math.max(...out, 1), min = Math.min(...out, -1);
  const span = max - min || 1;
  const pts = out.map((val, i) => ((i * width) / (n - 1)).toFixed(1) + ',' + (height - 10 - ((val - min) / span) * (height - 30)).toFixed(1)).join(' ');
  return { pts, last: out[out.length - 1], drawdown: low };
}

// Render an array of numbers as SVG polyline points inside a viewBox.
export function seriesPoints(values, width, height) {
  if (!values || values.length < 2) return '';
  const max = Math.max(...values), min = Math.min(...values);
  const span = max - min || 1;
  return values.map((v, i) =>
    ((i * width) / (values.length - 1)).toFixed(1) + ',' + (height - 10 - ((v - min) / span) * (height - 30)).toFixed(1)
  ).join(' ');
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
  const sparkArr = [0, 1, 2, 3, 4, 5, 6].map((k) => {
    const v = from + (yes - from) * (k / 6) + ((k * 37 + i * 13) % 5) - 2;
    return Math.round(50 - Math.min(96, Math.max(4, v)) / 2);
  });
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
