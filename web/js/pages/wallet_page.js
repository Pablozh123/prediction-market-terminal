// Wallet analysis — one address, read from the public Polymarket Data API.
//
// The page is a pure function over T (state + liveData.wallet[addr]). Every
// number it prints comes from /api/wallet/<addr> and carries its n, interval
// or as-of; without an answer the page says which request is missing. The
// only thing the page invents is the layout.

import { esc, money, num, signedMoney, stempel, leerBlock } from '../util.js';
import { caveat, caveatZeile } from '../claims.js';
import { scoreBand } from '../risk_bands.js';
import { diagramm, pnlZeitkurve, kurzGeld, fmtZahl } from '../charts.js';
import { squarify, pnlIntensity } from '../treemap.js';
import { MONO as M, KARTE, LABEL, NOTIZ } from '../ui.js';

const CELL = M + '; font-size:var(--t-small)';

export const WALLET_ADDRESS_RE = /^0x[0-9a-fA-F]{40}$/;
export const EXAMPLE_WALLET = '0x29afe1bf37700768a640a08f1b35dad5f202f88d';

export function isFullAddress(v) {
  return WALLET_ADDRESS_RE.test(String(v || '').trim());
}

export function shortAddr(a) {
  const s = String(a || '');
  return s.length > 12 ? s.slice(0, 6) + '…' + s.slice(-4) : s;
}

// ---- small formatters; null stays a dash, never a zero -------------------
function pct(v, d) {
  if (v === null || v === undefined || typeof v !== 'number' || v !== v) return '—';
  return (v * 100).toFixed(d == null ? 0 : d) + '%';
}
function pp(v, d) {
  if (v === null || v === undefined || typeof v !== 'number' || v !== v) return '—';
  return (v >= 0 ? '+' : '') + (v * 100).toFixed(d == null ? 1 : d) + 'pp';
}
function ci(arr, d) {
  if (!Array.isArray(arr) || arr.length !== 2) return '';
  return '[' + pct(arr[0], d) + ', ' + pct(arr[1], d) + ']';
}
function ratio(v) {
  if (v === null || v === undefined || typeof v !== 'number' || v !== v) return '—';
  return v.toFixed(2);
}
function dollars(v) {
  if (v === null || v === undefined || typeof v !== 'number' || v !== v) return '—';
  return signedMoney(v, Math.abs(v) >= 1000 ? 0 : 2);
}
function absDollars(v) {
  if (v === null || v === undefined || typeof v !== 'number' || v !== v) return '—';
  return '$' + num(Math.abs(v).toFixed(Math.abs(v) >= 1000 ? 0 : 2));
}
function cents(v) {
  if (v === null || v === undefined || typeof v !== 'number' || v !== v) return '—';
  return (v * 100).toFixed(1) + '¢';
}
function when(iso) {
  const s = String(iso || '');
  return s ? s.slice(0, 16).replace('T', ' ') : '—';
}
function pnlColor(v) {
  return typeof v === 'number' && v < 0 ? 'var(--neg)' : 'var(--pos)';
}
function link(url, text) {
  return url ? '<a href="' + esc(url) + '" target="_blank" rel="noopener" style="color:inherit; text-decoration:underline dotted">' + esc(text) + '</a>' : esc(text);
}
function externalLink(url, text) {
  return '<a href="' + esc(url) + '" target="_blank" rel="noopener" class="hv-accent" style="' + M + '; font-size:var(--t-micro); color:var(--ink-2); text-decoration:underline dotted">' + esc(text) + ' ↗</a>';
}

function card(title, body, sub) {
  return '<div style="' + KARTE + '; padding:16px 18px; margin-top:14px">'
    + '<div style="display:flex; align-items:baseline; justify-content:space-between; gap:12px; flex-wrap:wrap; margin-bottom:10px">'
    + '<div style="' + LABEL + '">' + title + '</div>'
    + (sub ? '<div style="' + NOTIZ + '">' + sub + '</div>' : '') + '</div>'
    + body + '</div>';
}

function tile(label, value, sub, color) {
  return '<div style="' + KARTE + '; padding:12px 14px; min-width:0">'
    + '<div style="' + LABEL + '">' + label + '</div>'
    + '<div style="' + M + '; font-size:var(--t-head); margin-top:5px; color:' + (color || 'var(--text)') + '; white-space:nowrap; overflow:hidden; text-overflow:ellipsis">' + value + '</div>'
    + (sub ? '<div style="' + NOTIZ + '; margin-top:3px">' + sub + '</div>' : '') + '</div>';
}

// A table inside its own horizontal scroller: the page never scrolls sideways.
function table(columns, rowsHtml, emptyText, minWidth) {
  const head = '<div style="display:grid; grid-template-columns:' + columns + '; gap:0 10px; padding:9px 14px; background:var(--panel); border-bottom:1px solid var(--line-2); ' + LABEL + '">';
  return '<div style="overflow-x:auto; border:1px solid var(--line-2); border-radius:var(--r-panel)">'
    + '<div style="min-width:' + (minWidth || 720) + 'px">'
    + head + '__HEAD__</div>'
    + (rowsHtml || '<div style="' + NOTIZ + '; padding:16px 14px">' + esc(emptyText || 'Nothing to list.') + '</div>')
    + '</div></div>';
}
function row(columns, cellsHtml, extra) {
  return '<div style="display:grid; grid-template-columns:' + columns + '; gap:0 10px; align-items:center; padding:9px 14px; border-bottom:1px solid var(--line-3); ' + (extra || '') + '">' + cellsHtml + '</div>';
}
function cell(text, style) {
  return '<div style="' + CELL + '; ' + (style || '') + '; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap">' + text + '</div>';
}
function tableWith(columns, headCells, rowsHtml, emptyText, minWidth) {
  return table(columns, rowsHtml, emptyText, minWidth).replace('__HEAD__', headCells);
}

// ---- header: input, button, example, recent ------------------------------
function renderHeader(T) {
  const s = T.state;
  const input = String(s.walletInput || '');
  const valid = isFullAddress(input);
  const looksLike = /^0x/i.test(input.trim()) && !valid;
  const btnStyle = 'font-size:var(--t-small); font-weight:600; border-radius:var(--r-control); padding:9px 14px; cursor:pointer; white-space:nowrap; '
    + (valid ? 'color:var(--on-accent); background:var(--accent)' : 'color:var(--ink-3); border:1px solid var(--line-1)');
  const analyse = () => { if (T.analyseWallet) T.analyseWallet(input.trim()); };
  const recent = Array.isArray(s.walletRecent) ? s.walletRecent.filter((a) => a !== EXAMPLE_WALLET) : [];
  const chip = (addr, label, title) => '<div ' + T.act(() => { if (T.analyseWallet) T.analyseWallet(addr); }) + ' class="hv-bd32" title="' + esc(title || addr) + '" style="' + M + '; font-size:var(--t-micro); letter-spacing:.04em; border-radius:var(--r-control); padding:4px 9px; cursor:pointer; color:var(--ink-3); border:1px solid var(--line-1); white-space:nowrap">' + esc(label) + '</div>';
  return '<div style="padding:20px 24px 14px; border-bottom:1px solid var(--line-2)">'
    + '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:.18em; color:var(--accent)">WALLET</div>'
    + '<h1 style="font-size:var(--t-head); line-height:1.25; margin:6px 0 0; font-weight:600; letter-spacing:-0.01em">One wallet, read from the public feed</h1>'
    // Der Lese-Vorbehalt stand hier als Prosa; er ist jetzt der
    // Registereintrag wallet_reader_caveat, die Beschreibung davor
    // gehoert weiter der Seite.
    + caveatZeile('wallet_reader_caveat', {
      vorsatz: 'Paste a Polymarket proxy address. The page reads its resolved positions (both tails), open positions, the profile PnL curve and its trades from the public Data API, and prints the corrected track record next to the naive one, every figure with its sample size, interval and time stamp.',
      stil: 'font-size:var(--t-body); color:var(--ink-4); margin-top:8px; max-width:800px; line-height:1.5'
    })
    + '<div style="display:flex; align-items:center; gap:10px; margin-top:14px; flex-wrap:wrap">'
    + '<input value="' + esc(input) + '" ' + T.inp((e) => { T.state.walletInput = e.target.value; T.render(); }, 'walletInput')
    + ' placeholder="0x… (40 hex characters)" aria-label="Wallet address to analyse" spellcheck="false" style="flex:1; min-width:280px; max-width:520px; box-sizing:border-box; background:var(--panel); border:1px solid ' + (looksLike ? 'rgba(var(--warn-rgb),.5)' : 'var(--line-edge)') + '; border-radius:var(--r-control); padding:10px 12px; ' + M + '; font-size:var(--t-small); color:var(--text)" />'
    + '<div ' + T.act(analyse) + (valid ? ' class="hv-accentbg"' : '') + ' style="' + btnStyle + '">Analyse →</div>'
    + '</div>'
    + (looksLike ? '<div style="' + M + '; font-size:var(--t-micro); color:var(--warn); margin-top:6px">Not a full address yet — a Polymarket wallet is 0x followed by 40 hex characters.</div>' : '')
    + '<div style="display:flex; align-items:center; gap:8px; margin-top:10px; flex-wrap:wrap">'
    + '<span style="' + LABEL + '">EXAMPLE</span>' + chip(EXAMPLE_WALLET, shortAddr(EXAMPLE_WALLET) + ' · live-run wallet', EXAMPLE_WALLET + ' — the wallet the small-stake live runs were placed from')
    + (recent.length ? '<span style="' + LABEL + '; margin-left:10px">RECENT</span>' + recent.slice(0, 6).map((a) => chip(a, shortAddr(a))).join('') : '')
    + '</div></div>';
}

// ---- states without a payload ---------------------------------------------
function renderIntro() {
  return leerBlock('NO WALLET SELECTED', 'Paste an address above and press Analyse, or take the example wallet. Nothing is fetched until you do — the page shows no figure it has not read for that address.');
}

function renderLoading(addr) {
  return leerBlock('ANALYSING ' + shortAddr(addr).toUpperCase(), 'Reading ' + addr + ' from the public Data API — up to ~10 s, six public API calls: closed positions in both sort directions, open positions, the profile PnL curve and the activity pages. Nothing is shown until the answer is in.');
}

function renderError(T, addr, entry) {
  const status = entry && entry.status;
  const msg = entry && entry.fehler ? String(entry.fehler) : 'unknown error';
  let title = 'API DID NOT ANSWER';
  let text = '/api/wallet/' + shortAddr(addr) + ' did not answer: ' + msg + '. Nothing is shown rather than a stale or invented figure.';
  if (status === 400) { title = 'NOT A WALLET ADDRESS'; text = 'The API rejected ' + addr + ' (HTTP 400): a Polymarket wallet is 0x followed by 40 hex characters.'; }
  else if (status === 404) { title = 'NO SUCH ROUTE'; text = '/api/wallet answered 404 — the API you are talking to does not know the wallet route (older deployment?).'; }
  else if (status === 429) { title = 'RATE-LIMITED'; text = 'The API is rate-limiting this address (HTTP 429)' + (entry.retryAfter ? ' — try again in ' + entry.retryAfter + ' s.' : '.') + ' The wallet route shares the per-IP budget of the risk screen and the backtester.'; }
  else if (/HTTP 5\d\d/.test(msg)) { title = 'API ERROR'; text = '/api/wallet failed on this address (' + msg + '). The upstream Data API may be slow or down; nothing is shown in its place.'; }
  return '<div style="padding:26px 24px">'
    + '<div style="' + KARTE + '; padding:20px 22px; max-width:760px">'
    + '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:.14em; color:var(--warn)">' + esc(title) + '</div>'
    + '<div style="font-size:var(--t-body); color:var(--ink-3); margin-top:9px; line-height:1.6">' + esc(text) + '</div>'
    + '<div style="display:flex; gap:8px; margin-top:12px">'
    + '<div ' + T.act(() => { if (T.fetchWallet) T.fetchWallet(addr, true); }) + ' class="hv-bd32" style="' + M + '; font-size:var(--t-micro); color:var(--ink-2); border:1px solid var(--line-1); border-radius:var(--r-control); padding:5px 10px; cursor:pointer">Try again</div>'
    + '</div></div></div>';
}

// ---- sections --------------------------------------------------------------
export const WALLET_TABS = [
  ['overview', 'Overview'], ['record', 'Track record'], ['positions', 'Positions'],
  ['trades', 'Trades'], ['categories', 'Categories'], ['risk', 'Risk'], ['similar', 'Similar wallets']
];

function initials(name, addr) {
  const n = String(name || '').trim();
  if (n) return n.replace(/[^a-z0-9]/gi, '').slice(0, 2).toUpperCase() || n.slice(0, 2).toUpperCase();
  const a = String(addr || '').replace(/^0x/, '');
  return a.slice(0, 2).toUpperCase() || '?';
}

// Identity strip: avatar, name, address, first/last activity, then the
// actions — the copy desk (follow this wallet with paper money), the
// backtester, and the two external profiles.
function renderIdentity(T, d) {
  const id = d.identity || {};
  const addr = id.address || T.state.walletAddr;
  const tr = d.track_record || null;
  const btn = (label, fn, primary, title) => '<div ' + T.act(fn) + ' class="' + (primary ? 'hv-accentbg' : 'hv-bd32') + '" title="' + esc(title || '') + '" style="' + M + '; font-size:var(--t-micro); letter-spacing:.04em; border-radius:var(--r-control); padding:6px 11px; cursor:pointer; white-space:nowrap; ' + (primary ? 'color:var(--on-accent); background:var(--accent); font-weight:600' : 'color:var(--ink-2); border:1px solid var(--line-1)') + '">' + label + '</div>';
  const follow = () => {
    // Prefill the copy desk's follow form and open it. Nothing is followed
    // until the button on that page is pressed.
    if (!T.setState) return;
    T.setState({ page: 'copy', copyTab: 'traders', detail: null, copyForm: { wallet: addr, label: id.pseudonym || '', cash: '1000', note: '' } });
    if (T.adresseSetzen) T.adresseSetzen('copy');
    if (T.fetchPageData) T.fetchPageData('copy');
  };
  const replay = () => {
    if (T.setState) T.setState({ page: 'backtester', detail: null, btWallet: addr, btDirty: !!(T.liveData && T.liveData.backtest) });
    try { history.pushState(null, '', '#backtester'); } catch (e) { /* file:// */ }
  };
  const tags = [];
  if (tr && tr.grade) tags.push('<span style="' + M + '; font-size:var(--t-micro); letter-spacing:.08em; color:' + (tr.grade === 'A' || tr.grade === 'B' ? 'var(--accent)' : tr.grade === 'F' ? 'var(--warn)' : 'var(--ink-2)') + '; border:1px solid var(--line-1); border-radius:var(--r-control); padding:2px 7px">GRADE ' + esc(tr.grade) + (tr.score != null ? ' · ' + tr.score + '/100' : '') + '</span>');
  if (tr && tr.survivorship_gate && !tr.survivorship_gate.ok) tags.push('<span style="' + M + '; font-size:var(--t-micro); letter-spacing:.08em; color:var(--warn); border:1px solid rgba(var(--warn-rgb),.35); border-radius:var(--r-control); padding:2px 7px">BELOW SAMPLE GATE</span>');
  if (tr && tr.wash_flag && tr.wash_flag.flag) tags.push('<span style="' + M + '; font-size:var(--t-micro); letter-spacing:.08em; color:var(--warn); border:1px solid rgba(var(--warn-rgb),.35); border-radius:var(--r-control); padding:2px 7px">WASH / FARMER FLAG</span>');
  if (id.days_active != null) tags.push('<span style="' + M + '; font-size:var(--t-micro); letter-spacing:.08em; color:var(--ink-3); border:1px solid var(--line-2); border-radius:var(--r-control); padding:2px 7px">' + id.days_active + (id.activity_truncated ? '+' : '') + ' DAYS ACTIVE</span>');
  return '<div style="' + KARTE + '; padding:16px 18px; position:relative; overflow:hidden">'
    + '<div style="position:absolute; left:-40px; top:-60px; width:180px; height:180px; border-radius:50%; background:radial-gradient(closest-side, rgba(var(--accent-rgb),.10), rgba(var(--accent-rgb),0)); pointer-events:none"></div>'
    + '<div style="display:flex; align-items:flex-start; justify-content:space-between; gap:16px; flex-wrap:wrap; position:relative">'
    + '<div style="display:flex; align-items:flex-start; gap:14px; min-width:0">'
    + '<div style="width:46px; height:46px; flex:none; border-radius:50%; background:linear-gradient(135deg, rgba(var(--accent-rgb),.35), rgba(var(--info-rgb),.35)); border:1px solid var(--line-1); display:flex; align-items:center; justify-content:center; ' + M + '; font-size:var(--t-lead); font-weight:600; color:var(--text)">' + esc(initials(id.pseudonym, addr)) + '</div>'
    + '<div style="min-width:0">'
    + '<div style="font-size:var(--t-head); line-height:1.2">' + esc(id.pseudonym || shortAddr(addr)) + '</div>'
    + '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-4); margin-top:4px; word-break:break-all">' + esc(addr) + '</div>'
    + '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-3); margin-top:5px">first activity ' + esc(when(id.first_activity)) + ' · last ' + esc(when(id.last_activity)) + ' · ' + (id.n_activity_rows != null ? num(id.n_activity_rows) + ' activity rows read' : 'activity not read') + '</div>'
    + (tags.length ? '<div style="display:flex; gap:6px; flex-wrap:wrap; margin-top:8px">' + tags.join('') + '</div>' : '')
    + '</div></div>'
    + '<div style="display:flex; flex-direction:column; align-items:flex-end; gap:8px">'
    + '<div style="display:flex; gap:8px; flex-wrap:wrap; justify-content:flex-end">'
    + btn('Follow on the copy desk →', follow, true, 'prefills the follow form of the paper copy desk with this address')
    + btn('Replay this wallet in the backtester →', replay, false, '')
    + (id.profile_url ? '<a href="' + esc(id.profile_url) + '" target="_blank" rel="noopener" class="hv-bd32" style="' + M + '; font-size:var(--t-micro); color:var(--ink-2); border:1px solid var(--line-1); border-radius:var(--r-control); padding:6px 11px; text-decoration:none; white-space:nowrap">Polymarket profile ↗</a>' : '')
    + (id.polygonscan_url ? '<a href="' + esc(id.polygonscan_url) + '" target="_blank" rel="noopener" class="hv-bd32" style="' + M + '; font-size:var(--t-micro); color:var(--ink-2); border:1px solid var(--line-1); border-radius:var(--r-control); padding:6px 11px; text-decoration:none; white-space:nowrap">Polygonscan ↗</a>' : '')
    + '</div>'
    + '<div style="' + NOTIZ + '">as of ' + esc(d.as_of || stempel(d.snapshot_at)) + ' · cached 300 s</div>'
    + '</div></div></div>';
}

// The KPI strip: five tiles with a tinted border (lime for a positive
// figure, red for a negative one, blue for neutral), then a thin fact line
// with the activity counts. Every figure keeps its n / CI / window note.
function kpiTile(label, value, sub, tone) {
  const border = tone === 'up' ? 'rgba(var(--pos-rgb),.35)' : tone === 'down' ? 'rgba(var(--neg-rgb),.35)' : tone === 'warn' ? 'rgba(var(--warn-rgb),.4)' : 'rgba(var(--info-rgb),.3)';
  const color = tone === 'up' ? 'var(--pos)' : tone === 'down' ? 'var(--neg)' : tone === 'warn' ? 'var(--warn)' : 'var(--text)';
  return '<div style="border:1px solid ' + border + '; border-radius:var(--r-panel); padding:12px 14px; min-height:62px; min-width:0; background:rgba(var(--ink),.015)">'
    + '<div style="' + LABEL + '">' + label + '</div>'
    + '<div style="' + M + '; font-size:var(--t-head); margin-top:5px; color:' + color + '; white-space:nowrap; overflow:hidden; text-overflow:ellipsis">' + value + '</div>'
    + (sub ? '<div style="' + NOTIZ + '; margin-top:2px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis">' + sub + '</div>' : '') + '</div>';
}

// Which PnL series carries information: the profile curve from user-pnl-api
// unless it is flat (the API's history starts late 2024; a wallet that stopped
// before that, or has not moved since, is one level for hundreds of points),
// then our own settled curve summed from the closed rows. The API says which
// in pnl.shown; older answers without it are resolved here the same way.
function pnlShown(d) {
  const p = d.pnl || null;
  if (!p) return { kind: 'none', p: null, curve: null, st: null };
  const settled = p.settled && Array.isArray(p.settled.points) && p.settled.points.length >= 2 ? p.settled : null;
  const profileOk = Array.isArray(p.points) && p.points.length >= 2;
  let kind = p.shown || (profileOk && !p.flat ? 'profile' : settled ? 'settled' : profileOk ? 'profile' : 'none');
  if (kind === 'settled' && !settled) kind = profileOk ? 'profile' : 'none';
  if (kind === 'profile' && !profileOk) kind = settled ? 'settled' : 'none';
  const curve = kind === 'settled' ? settled : kind === 'profile' ? p : null;
  return { kind, p, curve, st: curve && curve.stats ? curve.stats : null };
}

// A stats block whose sample never moved: no up day, no down day, no vol.
function statsFlat(st) {
  return !!(st && st.n_days > 0 && !st.winning_days && !st.losing_days && !(st.daily_vol > 0));
}

function renderKpis(d) {
  const tr = d.track_record || null;
  const shown = pnlShown(d);
  const st = shown.st;
  const basis = shown.kind === 'settled' ? 'settled curve' : shown.kind === 'profile' ? 'profile curve' : '';
  const flat = statsFlat(st);
  const act = d.activity || null;
  const id = d.identity || {};
  const corr = tr && tr.corrected ? tr.corrected : null;
  const capNote = tr && tr.capped ? ' · capped' : '';
  // Positionen, die gegen die Wallet aufgeloest und nie eingeloest wurden,
  // bleiben in /positions und tauchen im closed-positions-Feed nie auf. Jede
  // Quote aus diesem Feed laesst sie also weg — und es sind ausschliesslich
  // Verluste, die Quote ist damit nach oben verzerrt. Die Kachel nannte das
  // nicht; die Zahl stand allein neben ihrem CI.
  const nichtEingeloest = d.open_positions ? (Number(d.open_positions.worthless_n) || 0) : 0;
  const wertlosNote = nichtEingeloest
    ? ' · ' + num(nichtEingeloest) + ' unredeemed loss' + (nichtEingeloest === 1 ? '' : 'es') + ' not in it'
    : '';
  const tiles = [
    kpiTile('SETTLED PNL', tr ? dollars(tr.settled_pnl) : '—', tr ? 'n ' + num(tr.per_market ? tr.per_market.n : 0) + ' resolved markets' + capNote : 'no track record', tr ? (tr.settled_pnl < 0 ? 'down' : 'up') : 'neutral'),
    kpiTile('CORRECTED WIN RATE', corr && corr.win_rate != null ? pct(corr.win_rate) : '—', corr && corr.n ? corr.wins + '/' + corr.n + ' events · 95% ' + ci(corr.ci95) + capNote + wertlosNote : 'no resolved events', corr && corr.win_rate != null ? (corr.win_rate >= 0.5 ? 'up' : 'down') : 'neutral'),
    kpiTile('GRADE', tr && tr.grade ? esc(tr.grade) : '—', tr && tr.score != null ? 'score ' + tr.score + ' / 100' + (tr.survivorship_gate && !tr.survivorship_gate.ok ? ' · below sample gate' : '') : '', tr && tr.grade ? (tr.grade === 'A' || tr.grade === 'B' ? 'up' : tr.grade === 'F' ? 'warn' : 'neutral') : 'neutral'),
    kpiTile('SHARPE · DAILY $', st && st.sharpe != null ? ratio(st.sharpe) : '—', st ? (flat ? 'flat curve · no daily change' : 'n ' + st.n_days + ' d · ' + basis) : 'no PnL curve', st && st.sharpe != null ? (st.sharpe >= 0 ? 'up' : 'down') : 'neutral'),
    kpiTile('MAX DRAWDOWN', st ? absDollars(st.max_drawdown) : '—', st ? (flat ? 'flat curve · never moved' : pct(st.max_drawdown_pct, 1) + ' of peak · ' + basis) : 'no PnL curve', st && st.max_drawdown > 0 ? 'down' : 'neutral')
  ];
  const facts = [
    ['VOLUME TRADED', act && act.n_trades ? money(act.volume_traded) : '—'],
    ['TRADES', act && act.n_trades ? num(act.n_trades) + (act.window_truncated ? ' · window truncated' : '') : 'no trades read'],
    ['AVG TRADE', act && act.avg_trade_size != null ? absDollars(act.avg_trade_size) : '—'],
    ['DAYS ACTIVE', id.days_active != null ? String(id.days_active) + (id.activity_truncated ? '+ (window truncated)' : '') : '—'],
    ['SINCE', id.first_activity ? String(id.first_activity).slice(0, 10) : '—']
  ];
  return '<div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(170px, 1fr)); gap:10px; margin-top:14px">' + tiles.join('') + '</div>'
    + '<div style="display:flex; gap:18px; flex-wrap:wrap; margin-top:10px; padding:0 4px">'
    + facts.map((f) => '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-4)"><span style="letter-spacing:.1em; color:var(--ink-3)">' + f[0] + '</span> <span style="color:var(--text)">' + f[1] + '</span></div>').join('')
    + '</div>';
}

// ---- left column: the stacked stat cards --------------------------------
function asideCard(title, rows, sub) {
  return '<div style="' + KARTE + '; padding:12px 14px">'
    + '<div style="' + LABEL + '; margin-bottom:8px">' + title + '</div>'
    + rows.map((r) => (r.length === 1
      ? '<div style="' + M + '; font-size:var(--t-head); margin:2px 0 4px; color:' + (r[0][1] || 'var(--text)') + '">' + r[0][0] + '</div>'
      : '<div style="display:flex; justify-content:space-between; gap:8px; padding:3px 0; font-size:var(--t-small)"><span style="color:var(--ink-4)">' + r[0] + '</span><span style="' + M + '; color:' + (r[2] || 'var(--text)') + '">' + r[1] + '</span></div>')).join('')
    + (sub ? '<div style="' + NOTIZ + '; margin-top:6px">' + sub + '</div>' : '')
    + '</div>';
}

function renderAside(d) {
  const op = d.open_positions || null;
  const c = d.closed || null;
  const tr = d.track_record || null;
  const a = d.activity || null;
  const e = d.edge || null;
  const pd = e && e.per_dollar ? e.per_dollar : null;
  const ps = e && e.per_share ? e.per_share : null;
  const cards = [];
  cards.push(asideCard('PORTFOLIO · OPEN', op && op.n
    ? [[[absDollars(op.total_exposure)]], ['cost basis', absDollars(op.total_cost)], ['unrealised', dollars(op.unrealized_pnl), pnlColor(op.unrealized_pnl)], ['positions', num(op.n) + (op.capped ? '+' : '')]]
    : [[['—']]], op && op.n ? 'value at current prices · as of ' + esc(op.as_of || '') : (op && op.note ? esc(op.note) : 'no open positions read')));
  cards.push(asideCard('PNL BREAKDOWN', [
    ['settled (track record)', tr ? dollars(tr.settled_pnl) : '—', tr ? pnlColor(tr.settled_pnl) : 'var(--ink-3)'],
    ['realised (closed rows)', c && c.n ? dollars(c.realized_pnl) : '—', c && c.n ? pnlColor(c.realized_pnl) : 'var(--ink-3)'],
    ['unrealised (open)', op && op.n ? dollars(op.unrealized_pnl) : '—', op && op.n ? pnlColor(op.unrealized_pnl) : 'var(--ink-3)'],
    // Aufgeloest, nur nicht eingeloest: ein realisierter Verlust, der in
    // /positions steht und deshalb frueher unter "unrealised" mitlief.
    ['worthless (settled loss)', op && op.worthless_n ? dollars(op.worthless_pnl || 0) : '—', op && op.worthless_n ? 'var(--warn)' : 'var(--ink-3)'],
    ['position value', op && op.n ? absDollars(op.total_exposure) : '—']
  ], tr && tr.capped ? 'closed tails capped at ~50 each' : ''));
  cards.push(asideCard('CORE STATS', [
    ['avg trade', a && a.avg_trade_size != null ? absDollars(a.avg_trade_size) : '—'],
    ['won / lost', c && c.n ? num(c.won) + ' / ' + num(c.lost) : '—'],
    ['open / resolved', (op && op.n != null ? num(op.n) : '—') + ' / ' + (c && c.n != null ? num(c.n) : '—')],
    ['buy / sell', a && a.n_trades ? num(a.buy_n) + ' / ' + num(a.sell_n) : '—'],
    ['trades / day', a && a.trades_per_day != null ? fmtZahl(a.trades_per_day) : '—'],
    ['not redeemed', op ? num(op.worthless_n || 0) : '—', op && op.worthless_n ? 'var(--warn)' : 'var(--text)']
  ], a && a.window_truncated ? 'activity window truncated' : ''));
  const buyN = a ? Number(a.buy_n) || 0 : 0;
  const sellN = a ? Number(a.sell_n) || 0 : 0;
  const share = buyN + sellN > 0 ? buyN / (buyN + sellN) : null;
  cards.push('<div style="' + KARTE + '; padding:12px 14px">'
    + '<div style="' + LABEL + '; margin-bottom:8px">BUY / SELL RATIO</div>'
    + '<div style="' + M + '; font-size:var(--t-head)">' + (share == null ? '—' : pct(share, 1)) + '</div>'
    + '<div style="height:6px; border-radius:var(--r-control); background:rgba(var(--neg-rgb),.35); margin-top:8px; overflow:hidden"><div style="width:' + (share == null ? 0 : Math.round(share * 100)) + '%; height:6px; background:var(--accent)"></div></div>'
    + '<div style="display:flex; justify-content:space-between; ' + M + '; font-size:var(--t-micro); color:var(--ink-4); margin-top:6px"><span>buy ' + num(buyN) + '</span><span>sell ' + num(sellN) + '</span></div>'
    + (share == null ? '<div style="' + NOTIZ + '; margin-top:6px">no trades in the activity window</div>' : '')
    + '</div>');
  cards.push(asideCard('REALIZED EDGE', pd && pd.edge != null
    ? [[[(pd.edge * 100).toFixed(1) + '¢ per $', pnlColor(pd.edge)]], ['95% CI', pd.ci_low != null ? '[' + (pd.ci_low * 100).toFixed(1) + '¢, ' + (pd.ci_high * 100).toFixed(1) + '¢]' : 'n/a'], ['events', num(pd.groups)], ['per share', ps ? pp(ps.edge) + ' · ' + esc(String(ps.verdict || '')) : '—']]
    : [[['—']]], pd && pd.edge != null ? (pd.significant ? 'CI excludes zero' : 'CI includes zero') + (e && e.capped ? ' · capped tails' : '') : 'no resolved positions with a stake'));
  return '<div style="display:flex; flex-direction:column; gap:10px">' + cards.join('') + '</div>';
}

// ---- overview: PnL curve, top open / top closed, treemap ---------------
function topCard(label, r, kind) {
  if (!r) return '<div style="' + KARTE + '; padding:14px 16px"><div style="' + LABEL + '">' + label + '</div><div style="' + NOTIZ + '; margin-top:8px">nothing to show</div></div>';
  const pnl = kind === 'open' ? r.unrealized_pnl : r.realized_pnl;
  const stake = kind === 'open' ? r.cost : r.total_bought;
  const now = kind === 'open' ? r.value : (Number(r.total_bought) || 0) + (Number(r.realized_pnl) || 0);
  const ret = stake > 0 ? pnl / stake : null;
  return '<div style="' + KARTE + '; padding:14px 16px; min-width:0">'
    + '<div style="display:flex; justify-content:space-between; gap:8px; align-items:baseline"><div style="' + LABEL + '">' + label + '</div>'
    + '<span style="' + M + '; font-size:var(--t-micro); letter-spacing:.08em; color:' + (String(r.outcome).toLowerCase() === 'yes' ? 'var(--accent)' : 'var(--neg-soft)') + '; border:1px solid var(--line-1); border-radius:var(--r-control); padding:1px 6px">' + esc(String(r.outcome || '—').toUpperCase()) + '</span></div>'
    + '<div style="font-family:var(--font-ui); font-size:var(--t-body); margin-top:8px; line-height:1.4; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden">' + link(r.url, r.title) + '</div>'
    + '<div style="' + M + '; font-size:var(--t-head); margin-top:8px; color:' + pnlColor(pnl) + '">' + (ret == null ? dollars(pnl) : (ret >= 0 ? '+' : '') + (ret * 100).toFixed(0) + '%') + '</div>'
    + '<div style="' + NOTIZ + '; margin-top:2px">' + absDollars(stake) + ' → ' + absDollars(now) + ' · ' + dollars(pnl) + (kind === 'open' ? ' unrealised' : ' realised') + '</div>'
    + '</div>';
}

// Tiles: area = $ at stake (open: value at current prices; closed: $
// bought), colour = PnL sign, depth = |PnL| relative to the stake. Each tile
// carries the exact figures in its title, so a hover reads them.
export function treemapItems(d, mode) {
  const out = [];
  const op = d.open_positions && Array.isArray(d.open_positions.rows) ? d.open_positions.rows : [];
  const cl = d.closed && Array.isArray(d.closed.rows) ? d.closed.rows : [];
  if (mode !== 'closed') {
    op.forEach((r) => {
      const value = Number(r.value) || 0;
      const stake = Number(r.cost) || 0;
      out.push({ value: value > 0 ? value : stake, kind: 'open', title: r.title, outcome: r.outcome, url: r.url, image: r.image || '', pnl: Number(r.unrealized_pnl) || 0, stake, now: r.current_price, avg: r.avg_price, status: r.status, ends: r.end_time });
    });
  }
  if (mode !== 'open') {
    cl.forEach((r) => {
      const stake = Number(r.total_bought) || 0;
      out.push({ value: stake, kind: 'closed', title: r.title, outcome: r.outcome, url: r.url, image: r.image || '', pnl: Number(r.realized_pnl) || 0, stake, result: r.result, avg: r.avg_price, settled: r.current_price, time: r.time });
    });
  }
  return out.filter((it) => it.value > 0);
}

// Positionen als sortierte Balken. Die Standardansicht, die Treemap sitzt
// daneben als zweite.
//
// Warum der Wechsel: die Aufgabe dieser Zahlen ist ein Groessenvergleich,
// und Flaeche ist die schwaechste Wahrnehmungsaufgabe dafuer. Die Treemap
// hatte dazu keine Achse, keine Legende und keinen Schluessel fuer ihre
// Farbintensitaet, und jede Kachel unter 56x34 Pixel blieb ohne Beschriftung.
// Laenge auf einer gemeinsamen Grundlinie loest genau das.
//
// Gezeigt werden die groessten Einsaetze, nicht alle: bei bis zu 200
// Positionen waere die Liste ein Bildlauf statt eines Vergleichs. Was nicht
// abgebildet ist, wird gezaehlt und mit seiner Summe genannt, damit die
// Auswahl nicht wie der ganze Bestand aussieht.
const POSITIONEN_IM_BALKEN = 14;

function kurzTitel(t, n) {
  const s = String(t || '');
  return s.length > n ? s.slice(0, n - 1) + '…' : s;
}

export function positionsBalken(T, d) {
  const mode = T.state.walletTreemap || 'all';
  const items = treemapItems(d, mode).slice().sort((a, b) => b.value - a.value);
  const kopf = '<div style="' + LABEL + '">POSITIONS BY SIZE</div>';
  if (!items.length) {
    // Dieselbe Ehrlichkeit wie in der Treemap: es steht dran, welcher der
    // drei Faelle vorliegt, statt dass die Flaeche einfach fehlt.
    return '<div style="' + KARTE + '; padding:16px 18px; margin-top:14px">' + kopf
      + '<div style="' + NOTIZ + '; margin-top:6px">Nothing to draw: '
      + (mode === 'open' ? 'no open positions with a value'
        : mode === 'closed' ? 'no resolved positions with a stake'
          : 'no positions with a stake in either feed') + '.</div></div>';
  }
  const gezeigt = items.slice(0, POSITIONEN_IM_BALKEN);
  const rest = items.slice(POSITIONEN_IM_BALKEN);
  const restSumme = rest.reduce((a, it) => a + (Number(it.value) || 0), 0);
  const gesamt = items.reduce((a, it) => a + (Number(it.value) || 0), 0);
  const punkte = gezeigt.map((it) => {
    const ret = it.stake > 0 ? it.pnl / it.stake : null;
    return {
      // 20 Zeichen plus " · YES": die Labelspalte von diagramm() ist 196
      // Einheiten breit, ein Zeichen in 11.5px IBM Plex Mono misst rund 6.9.
      // Bei 30 Zeichen stand der Anfang des laengsten Titels im Browser
      // gemessen ausserhalb der Zeichenflaeche.
      label: kurzTitel(it.title, 20) + ' · ' + String(it.outcome || '—').toUpperCase().slice(0, 3),
      wert: Number(it.value) || 0,
      // Laenge misst den Einsatz, Farbe traegt das Vorzeichen des Ergebnisses.
      farbe: it.pnl >= 0 ? 'var(--pos)' : 'var(--neg)',
      text: kurzGeld(Number(it.value) || 0) + '  ' + (it.pnl >= 0 ? '+' : '-') + kurzGeld(Math.abs(it.pnl)).slice(1),
      tip: String(it.title || '') + ' · ' + String(it.outcome || '').toUpperCase()
        + ' · ' + (it.kind === 'open' ? 'open' : 'closed')
        + ' · at stake ' + kurzGeld(Number(it.value) || 0)
        + ' · ' + (it.kind === 'open' ? 'unrealised ' : 'realised ') + kurzGeld(it.pnl, true)
        + (ret != null ? ' (' + (ret >= 0 ? '+' : '') + (ret * 100).toFixed(0) + '%)' : '')
    };
  });
  const chart = diagramm({
    titel: 'POSITIONS BY SIZE',
    einheit: 'dollars at stake',
    xLabel: 'at stake (USD) · bar length = stake, colour = profit or loss',
    punkte
  });
  if (!chart) return '';
  const fuss = 'Bar length is money at stake in dollars (open positions: value at current prices, closed: dollars bought). '
    + 'Colour is the sign of the result on that position, green up and red down; the number after the dollar amount is that result. '
    + (rest.length
      ? num(rest.length) + ' smaller position(s) are not drawn, ' + kurzGeld(restSumme) + ' of ' + kurzGeld(gesamt) + ' at stake in total. '
      : 'All ' + num(items.length) + ' positions are drawn. ');
  return '<div style="margin-top:14px">' + chart
    + '<div style="' + NOTIZ + '; margin-top:8px; max-width:660px">' + esc(fuss) + '</div></div>';
}

// Der Schluessel zur Farbintensitaet der Treemap. Ohne ihn ist ein dunkleres
// Gruen nur dunkler; mit ihm sagt es, wie gross das Ergebnis gegen den
// Einsatz ist (treemap.pnlIntensity: 0.28 bis 0.78 linear ueber |PnL|/Einsatz,
// gedeckelt bei 100 Prozent).
function intensitaetsSchluessel() {
  const stufe = (anteil, text) => '<div style="display:flex; align-items:center; gap:5px">'
    + '<span style="display:inline-block; width:16px; height:10px; border-radius:2px; background:rgba(var(--pos-rgb),'
    + pnlIntensity(anteil, 1).toFixed(2) + ')"></span>'
    + '<span style="' + M + '; font-size:var(--t-micro); color:var(--ink-3)">' + text + '</span></div>';
  return '<div style="display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin-top:6px">'
    + '<span style="' + M + '; font-size:var(--t-micro); letter-spacing:.1em; color:var(--ink-3)">RESULT vs STAKE</span>'
    + stufe(0, '0%') + stufe(0.25, '25%') + stufe(0.5, '50%') + stufe(1, '100% or more')
    + '<span style="' + M + '; font-size:var(--t-micro); color:var(--ink-3)">green up, red down</span></div>';
}

function renderTreemap(T, d) {
  const mode = T.state.walletTreemap || 'all';
  const items = treemapItems(d, mode);
  const W = 1000;
  const H = 440;
  const rects = squarify(items, W, H);
  const op = d.open_positions || {};
  const cl = d.closed || {};
  const capped = (mode !== 'closed' && op.capped) || (mode !== 'open' && cl.capped);
  const head = '<div style="display:flex; align-items:baseline; justify-content:space-between; gap:12px; flex-wrap:wrap; margin-bottom:10px">'
    + '<div><div style="' + LABEL + '">POSITIONS TREEMAP</div><div style="' + NOTIZ + '; margin-top:3px">tile area = $ at stake (open: value at current prices · closed: $ bought)</div>'
    + intensitaetsSchluessel() + '</div></div>';
  if (!rects.length) {
    return '<div style="' + KARTE + '; padding:16px 18px; margin-top:14px">' + head + '<div style="' + NOTIZ + '">Nothing to tile: ' + (mode === 'open' ? 'no open positions with a value' : mode === 'closed' ? 'no resolved positions with a stake' : 'no positions with a stake in either feed') + '.</div></div>';
  }
  // Every tile carries its figures in data-tip (JSON: title, image, rows);
  // app.js shows them in a floating card on hover, whatever the tile size.
  // Larger tiles also show the market image, the title, the side and the
  // value in place. The image is the market's own, as the feed carries it.
  const tiles = rects.map((rc) => {
    const it = rc.item;
    const up = it.pnl >= 0;
    const alpha = pnlIntensity(it.pnl, it.stake);
    const bg = up ? 'rgba(var(--pos-rgb),' + alpha.toFixed(2) + ')' : 'rgba(var(--neg-rgb),' + alpha.toFixed(2) + ')';
    const wPct = (rc.w / W) * 100;
    const hPct = (rc.h / H) * 100;
    const wide = rc.w >= 110 && rc.h >= 62;
    const showImg = rc.w >= 74 && rc.h >= 58 && it.image;
    const tiny = rc.w < 56 || rc.h < 34;
    const ret = it.stake > 0 ? it.pnl / it.stake : null;
    const rows = [
      ['side', String(it.outcome || '—').toUpperCase() + ' · ' + (it.kind === 'open' ? (it.status === 'worthless' ? 'resolved, not redeemed' : 'open') : 'closed' + (it.result ? ' · ' + it.result : ''))],
      [it.kind === 'open' ? 'stake (cost)' : 'stake (bought)', absDollars(it.stake)],
      [it.kind === 'open' ? 'value now' : 'returned', absDollars(it.kind === 'open' ? it.value : (Number(it.stake) || 0) + (Number(it.pnl) || 0))],
      [it.kind === 'open' ? 'unrealised' : 'realised', dollars(it.pnl) + (ret != null ? ' (' + (ret >= 0 ? '+' : '') + (ret * 100).toFixed(0) + '%)' : '')]
    ];
    if (it.avg != null) rows.push(['avg entry', cents(it.avg)]);
    if (it.kind === 'open' && it.now != null) rows.push(['price now', cents(it.now) + ' — the market\'s current chance of this side']);
    if (it.kind === 'closed' && it.settled != null) rows.push(['settled at', cents(it.settled)]);
    if (it.kind === 'open' && it.ends) rows.push(['ends', String(it.ends).slice(0, 10)]);
    if (it.kind === 'closed' && it.time) rows.push(['resolved', String(it.time).slice(0, 10)]);
    const tip = { title: String(it.title || ''), image: String(it.image || ''), pnl: up ? 'up' : 'down', rows };
    const inner = tiny ? ''
      : '<div style="display:flex; justify-content:space-between; gap:4px; align-items:flex-start">'
        + (showImg ? '<img src="' + esc(it.image) + '" alt="" loading="lazy" style="width:' + (wide ? 34 : 26) + 'px; height:' + (wide ? 34 : 26) + 'px; border-radius:var(--r-control); object-fit:cover; flex:none; background:var(--shadow-25)" />' : '')
        + '<span style="' + M + '; font-size:var(--t-micro); letter-spacing:.06em; color:var(--ink-1); background:var(--shadow-35); border-radius:var(--r-control); padding:1px 4px; flex:none; margin-left:auto">' + esc(String(it.outcome || '').toUpperCase().slice(0, 3)) + (it.kind === 'closed' ? ' ✓' : '') + '</span></div>'
        + (wide ? '<div style="font-family:var(--font-ui); font-size:var(--t-micro); font-weight:600; line-height:1.3; color:var(--text); margin-top:5px; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden">' + esc(it.title || '') + '</div>' : '')
        + '<div style="' + M + '; font-size:' + (wide ? 'var(--t-small)' : 'var(--t-micro)') + '; color:var(--text); margin-top:auto">' + absDollars(it.value) + (wide && ret != null ? ' <span style="color:var(--ink-1)">' + (ret >= 0 ? '+' : '') + (ret * 100).toFixed(0) + '%</span>' : '') + '</div>';
    const style = 'position:absolute; left:' + ((rc.x / W) * 100).toFixed(3) + '%; top:' + ((rc.y / H) * 100).toFixed(3) + '%; width:' + wPct.toFixed(3) + '%; height:' + hPct.toFixed(3) + '%; box-sizing:border-box; padding:' + (tiny ? '0' : '6px 7px') + '; border:1px solid var(--bg); border-radius:var(--r-control); background:' + bg + '; display:flex; flex-direction:column; overflow:hidden; text-decoration:none; color:inherit';
    const attrs = 'class="tm-tile" data-tip="' + esc(JSON.stringify(tip)) + '" style="' + style + '"';
    return it.url
      ? '<a data-stop href="' + esc(it.url) + '" target="_blank" rel="noopener" ' + attrs + '>' + inner + '</a>'
      : '<div ' + attrs + '>' + inner + '</div>';
  }).join('');
  const foot = '<div style="' + NOTIZ + '; margin-top:8px">' + num(rects.length) + ' tiles' + (capped ? ' · the feeds were capped, so the middle of the record is missing here too' : '') + ' · hover a tile for its figures, click it to open the market</div>';
  return '<div style="' + KARTE + '; padding:16px 18px; margin-top:14px">' + head
    // Der Grund hinter den Kacheln war ein Hex-Literal und blieb im hellen
    // Thema dunkel. Er folgt jetzt dem Thema wie alles andere.
    + '<div style="position:relative; width:100%; height:' + H + 'px; border-radius:var(--r-control); overflow:hidden; background:var(--bg)">' + tiles + '</div>' + foot + '</div>';
}

function renderOverview(T, d) {
  const op = d.open_positions && Array.isArray(d.open_positions.rows) ? d.open_positions.rows : [];
  const cl = d.closed && Array.isArray(d.closed.rows) ? d.closed.rows : [];
  const topOpen = op.slice().sort((a, b) => (Number(b.unrealized_pnl) || 0) - (Number(a.unrealized_pnl) || 0))[0] || null;
  const topClosed = cl.slice().sort((a, b) => (Number(b.realized_pnl) || 0) - (Number(a.realized_pnl) || 0))[0] || null;
  // Balken sind die Grundansicht, die Treemap die zweite. Beide lesen
  // dieselben Positionen und denselben Alle/Offen/Geschlossen-Filter.
  const ansicht = T.state.walletPosView === 'treemap' ? 'treemap' : 'bars';
  const mode = T.state.walletTreemap || 'all';
  const umschalter = T.chip
    ? '<div style="display:flex; align-items:center; gap:16px; flex-wrap:wrap; margin-top:14px">'
      + '<div style="display:flex; align-items:center; gap:6px"><span style="' + LABEL + '">POSITION VIEW</span>'
      + T.chip('Bars', ansicht === 'bars', { walletPosView: 'bars' })
      + T.chip('Treemap', ansicht === 'treemap', { walletPosView: 'treemap' }) + '</div>'
      + '<div style="display:flex; align-items:center; gap:6px"><span style="' + LABEL + '">SET</span>'
      + T.chip('All', mode === 'all', { walletTreemap: 'all' })
      + T.chip('Open', mode === 'open', { walletTreemap: 'open' })
      + T.chip('Closed', mode === 'closed', { walletTreemap: 'closed' }) + '</div>'
      + '</div>'
    : '';
  return renderPnl(d)
    + '<div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(260px, 1fr)); gap:14px; margin-top:14px">' + topCard('TOP OPEN · BY UNREALISED', topOpen, 'open') + topCard('TOP CLOSED · BY REALISED', topClosed, 'closed') + '</div>'
    + umschalter
    + (ansicht === 'bars' ? positionsBalken(T, d) : renderTreemap(T, d));
}

function renderTrackRecord(d) {
  const tr = d.track_record;
  if (!tr) return card('TRACK RECORD', '<div style="' + NOTIZ + '">No track record in the answer — the closed-positions feed did not yield a resolved set for this wallet.</div>');
  const cols = '1.6fr 1fr 1fr 1.4fr';
  const rateRow = (label, b, hi) => row(cols,
    cell(esc(label), 'white-space:normal; color:var(--ink-2)')
    + cell(b && b.win_rate != null ? pct(b.win_rate) : '—', 'text-align:right; font-size:var(--t-body)' + (hi ? '; color:var(--accent)' : ''))
    + cell(b ? b.wins + ' / ' + b.n : '—', 'text-align:right; color:var(--ink-3)')
    + cell(b && b.ci95 ? ci(b.ci95) : '—', 'text-align:right; color:var(--ink-3)'));
  const rates = tableWith(cols,
    '<div>WIN RATE</div><div style="text-align:right">RATE</div><div style="text-align:right">WINS / N</div><div style="text-align:right">95% WILSON CI</div>',
    rateRow('Naive — per position leg (what a leaderboard implies)', tr.naive, false)
    + rateRow('Per market — legs of one conditionId netted', tr.per_market, false)
    + rateRow('Corrected — per event, NegRisk legs netted', tr.corrected, true),
    '', 560);
  const gate = tr.survivorship_gate || {};
  const conc = tr.concentration || {};
  const wash = tr.wash_flag || {};
  const facts = [
    ['SETTLED PNL', dollars(tr.settled_pnl), 'sum of realised PnL over ' + num(gate.resolved_markets || 0) + ' resolved markets · $' + num(Math.round(tr.volume || 0)) + ' bought'],
    ['NEGRISK LEGS NETTED', num(tr.legs_netted || 0), tr.leg_inflation != null ? 'naive / corrected = ' + tr.leg_inflation.toFixed(2) : ''],
    ['PNL PER $ OF VOLUME', tr.pnl_per_volume != null ? (tr.pnl_per_volume * 100).toFixed(1) + '¢' : '—', 'settled PnL / bought'],
    ['WASH / FARMER FLAG', wash.flag ? 'FLAGGED' : 'not flagged', 'rule: ' + (wash.rule || '')],
    ['SURVIVORSHIP GATE', gate.ok ? 'passed' : 'not passed', num(gate.resolved_markets || 0) + ' markets over ' + (gate.span_days != null ? gate.span_days.toFixed(0) : '—') + ' d · needs ≥ ' + gate.min_markets + ' and ≥ ' + gate.min_span_days + ' d'],
    ['PROFIT CONCENTRATION', conc.top3_share != null ? pct(conc.top3_share) + ' in top 3' : '—', conc.top_market_share != null ? 'best market ' + pct(conc.top_market_share) + (conc.one_hit_flag ? ' · one-hit flag' : '') : ''],
    ['RISK-ADJUSTED', ratio(tr.risk_adjusted), 'Sharpe-like on per-market returns'],
    ['EXIT WIN RATE', tr.exit_win_rate != null ? pct(tr.exit_win_rate) : '—', 'round trips in the activity window (cross-check)']
  ];
  const factsHtml = '<div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(210px, 1fr)); gap:12px 16px; margin-top:14px">'
    + facts.map((f) => '<div><div style="' + LABEL + '">' + f[0] + '</div><div style="' + M + '; font-size:var(--t-body); margin-top:3px; color:' + (f[0] === 'SETTLED PNL' ? pnlColor(tr.settled_pnl) : (f[1] === 'FLAGGED' || f[1] === 'not passed') ? 'var(--warn)' : 'var(--text)') + '">' + f[1] + '</div>'
      + (f[2] ? '<div style="' + NOTIZ + '; margin-top:2px">' + esc(f[2]) + '</div>' : '') + '</div>').join('')
    + '</div>';
  const top3 = Array.isArray(conc.top3) && conc.top3.length
    ? '<div style="' + NOTIZ + '; margin-top:10px">Top-3 markets by profit: ' + conc.top3.map((m) => esc(m.title) + ' (' + dollars(m.pnl) + ', ' + pct(m.share) + ')').join(' · ') + '</div>' : '';
  const parts = Array.isArray(tr.score_components) && tr.score_components.length
    ? '<div style="margin-top:14px"><div style="' + LABEL + '">SCORE ' + (tr.score != null ? tr.score : '—') + ' / 100 · GRADE ' + esc(tr.grade || '—') + ' · COMPONENTS</div>'
      + '<div style="display:flex; gap:6px; flex-wrap:wrap; margin-top:6px">'
      + tr.score_components.map((c) => '<span style="' + M + '; font-size:var(--t-micro); color:var(--ink-4); border:1px solid var(--line-2); border-radius:var(--r-control); padding:2px 7px">' + esc(c.label) + ' <span style="color:var(--ink-1)">' + (typeof c.value === 'number' ? (c.value >= 0 ? '' : '') + fmtZahl(c.value) : '—') + '</span>' + (c.max ? ' / ' + c.max : '') + '</span>').join('')
      + '</div></div>' : '';
  const flags = Array.isArray(tr.flags) && tr.flags.length
    ? '<div style="display:flex; gap:6px; flex-wrap:wrap; margin-top:12px">' + tr.flags.map((f) => '<span style="' + M + '; font-size:var(--t-micro); color:var(--warn); border:1px solid rgba(var(--warn-rgb),.35); border-radius:var(--r-control); padding:2px 7px">' + esc(f) + '</span>').join('') + '</div>'
    : '<div style="' + NOTIZ + '; margin-top:12px">No flags: sample gate passed, no wash pattern, no one-hit concentration.</div>';
  const cov = '<div style="' + NOTIZ + '; margin-top:10px">' + esc(tr.coverage_note || '') + (tr.capped ? ' Both tails hit the ~50-row cap: the middle of the record is unreachable, and win rate, edge and PnL describe the extremes only.' : '') + '</div>';
  return card('TRACK RECORD · NAIVE VS CORRECTED', rates + factsHtml + top3 + parts + flags + cov, 'as of ' + esc(tr.as_of || '') + ' · ' + esc(tr.source || '') + (tr.capped ? ' · CAPPED' : ''));
}

function renderPnl(d) {
  const shown = pnlShown(d);
  const p = shown.p;
  if (shown.kind === 'none') {
    const why = p && p.flat && Array.isArray(p.points) && p.points.length
      ? esc(p.note || '')
      : 'user-pnl-api.polymarket.com did not answer for this wallet' + (p && p.settled && p.settled.n_rows ? ' and the closed rows give a single point' : ' and there are no closed rows to sum');
    return card('PNL TIMELINE', '<div style="' + NOTIZ + '">No PnL curve — ' + why + ', so there is no Sharpe, drawdown or win-day share to show.</div>', p ? 'as of ' + esc(p.as_of || '') : '');
  }
  const settled = shown.kind === 'settled';
  const c = shown.curve;
  const st = shown.st;
  const flat = statsFlat(st);
  const last = c.points[c.points.length - 1];
  const lastVal = Number(last.pnl);
  const first = String(c.points[0].t || '').slice(0, 10);
  const lastDay = String(last.t || '').slice(0, 10);
  const profileHasPoints = Array.isArray(p.points) && p.points.length > 0;

  // Head: title with a plain-words tooltip, the current PnL big at the right
  // (the way a profile page reads), the swap chip when the settled curve
  // stands in for a flat profile curve. Everything longer sits in "basis".
  const headTip = settled
    ? 'Realised PnL of the closed rows, summed in the order they resolved. Not the curve polymarket.com shows — that one is flat for this wallet.'
    : 'The curve polymarket.com shows on the profile: user-pnl-api.polymarket.com, daily points, all time.';
  const head = '<div style="display:flex; align-items:flex-end; justify-content:space-between; gap:12px; flex-wrap:wrap">'
    + '<div><div style="' + LABEL + '">' + (settled ? 'PNL TIMELINE · SETTLED CURVE' : 'PNL TIMELINE · PROFILE CURVE')
    + ' <span title="' + esc(headTip) + '" style="display:inline-block; width:13px; height:13px; line-height:13px; text-align:center; border-radius:50%; border:1px solid var(--line-1); color:var(--ink-4); font-size:var(--t-micro); letter-spacing:0; cursor:help; vertical-align:1px">i</span></div>'
    + '<div style="' + NOTIZ + '; margin-top:4px">' + (settled
      ? num(c.n_rows) + ' closed rows' + (c.capped ? ' · <span style="color:var(--warn)">capped tails</span>' : ' · complete set') + ' · ' + esc(first) + ' → ' + esc(lastDay)
      : num(c.n_points) + ' daily points · ' + esc(first) + ' → ' + esc(lastDay)) + '</div></div>'
    + '<div style="text-align:right"><div style="' + LABEL + '">' + (settled ? 'REALISED PNL' : 'CURRENT PNL') + '</div>'
    + '<div style="' + M + '; font-size:var(--t-hero); font-weight:600; line-height:1.15; color:' + pnlColor(lastVal) + '">' + esc(kurzGeld(lastVal, true)) + '</div>'
    + '<div style="' + NOTIZ + '">' + esc(dollars(lastVal)) + ' · ' + esc(lastDay) + '</div></div>'
    + '</div>';
  const swap = settled
    ? '<div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin-top:10px; ' + M + '; font-size:var(--t-micro); color:var(--warn)">'
      + '<span style="border:1px solid rgba(var(--warn-rgb),.45); border-radius:var(--r-control); padding:2px 7px; letter-spacing:.1em">PROFILE CURVE ' + (profileHasPoints ? 'FLAT' : 'MISSING') + '</span>'
      + '<span style="color:var(--warn)">' + (profileHasPoints && p.flat
        ? 'one level (' + esc(kurzGeld(Number(p.points[p.points.length - 1].pnl), true)) + ') for ' + num(p.n_points) + ' points since ' + esc(String(p.first || '').slice(0, 10)) + ' — showing our settled curve instead'
        : 'user-pnl-api did not answer — showing our settled curve instead') + '</span>'
      + '<span style="color:var(--ink-3)">details below ↓</span></div>'
    : (flat ? '<div style="margin-top:10px; ' + M + '; font-size:var(--t-micro); color:var(--warn)">Flat: the profile curve never moved in ' + num(c.n_points) + ' points, and there are no closed rows to sum instead.</div>' : '');

  const kurve = pnlZeitkurve({
    titel: settled ? 'cumulative realised PnL, settled rows' : 'cumulative PnL, profile curve',
    punkte: c.points.map((pt) => ({ t: pt.t, wert: +pt.pnl }))
  });

  // Six tiles, one figure each, one short line under it. The definitions and
  // the sample caveats live in the collapsed basis block underneath.
  const down = st ? Number(st.losing_days) || 0 : 0;
  const stTile = (label, value, sub, tone) => '<div style="border:1px solid var(--line-2); border-radius:var(--r-panel); padding:10px 12px; min-width:0; background:rgba(var(--ink),.015)">'
    + '<div style="' + LABEL + '">' + label + '</div>'
    + '<div style="' + M + '; font-size:var(--t-head); margin-top:4px; color:' + (tone || 'var(--text)') + '; white-space:nowrap; overflow:hidden; text-overflow:ellipsis">' + value + '</div>'
    + '<div style="' + NOTIZ + '; margin-top:1px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis">' + sub + '</div></div>';
  const statsHtml = st ? '<div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(140px, 1fr)); gap:8px; margin-top:12px">'
    + stTile('SHARPE', ratio(st.sharpe), flat ? 'flat curve' : 'n ' + num(st.n_days) + ' d · $/day', st.sharpe != null ? (st.sharpe >= 0 ? 'var(--pos)' : 'var(--neg)') : 'var(--ink-3)')
    + stTile('SORTINO', ratio(st.sortino), flat ? 'flat curve' : st.sortino == null ? (down + ' down day' + (down === 1 ? '' : 's') + ' · needs 3') : 'downside only · ' + num(down) + ' down d', st.sortino != null ? (st.sortino >= 0 ? 'var(--pos)' : 'var(--neg)') : 'var(--ink-3)')
    + stTile('CALMAR', ratio(st.calmar), flat ? 'flat curve' : st.calmar == null ? 'never in drawdown' : 'annual PnL / max DD', st.calmar != null ? 'var(--text)' : 'var(--ink-3)')
    + stTile('MAX DRAWDOWN', absDollars(st.max_drawdown), flat ? 'never moved' : pct(st.max_drawdown_pct, 1) + ' of peak', st.max_drawdown > 0 ? 'var(--neg)' : 'var(--text)')
    + stTile('WIN DAYS', pct(st.win_day_rate), num(st.winning_days) + ' up · ' + num(st.losing_days) + ' down' + (flat ? ' · flat' : ''), st.win_day_rate != null ? (st.win_day_rate >= 0.5 ? 'var(--pos)' : 'var(--neg)') : 'var(--ink-3)')
    + stTile('BEST · WORST DAY', esc(kurzGeld(st.best_day, true)) + ' · ' + esc(kurzGeld(st.worst_day, true)), 'vol ' + esc(kurzGeld(st.daily_vol)) + ' / day')
    + '</div>' : '<div style="' + NOTIZ + '; margin-top:10px">Curve present, statistics not computable (fewer than two daily points).</div>';

  // Basis, collapsed: what the curve is, what the ratios are, the caveats.
  const basisRows = [];
  if (settled) basisRows.push(['Curve', c.note || '']);
  else basisRows.push(['Curve', 'user-pnl-api.polymarket.com — the profile curve polymarket.com shows; daily fidelity, all time; ' + num(c.n_points) + ' points.']);
  if (settled && profileHasPoints) basisRows.push(['Profile curve', p.note || '']);
  if (settled && !profileHasPoints) basisRows.push(['Profile curve', 'user-pnl-api.polymarket.com did not answer for this wallet.']);
  basisRows.push(['Ratios', 'Daily PnL in dollars (one point per day, differenced), no capital base, annualised on 365 days; n is the number of daily changes. Sharpe = mean / sd. Sortino = mean / downside RMS over all days (target 0), shown only with 3+ losing days. Calmar = annualised mean daily PnL / max drawdown. Max drawdown = deepest fall from a running peak, % of that peak.']);
  const basis = '<details style="margin-top:10px"><summary style="' + NOTIZ + '; cursor:pointer; list-style:none; display:inline-flex; align-items:center; gap:6px"><span style="border:1px solid var(--line-1); border-radius:var(--r-control); padding:1px 7px; letter-spacing:.1em">BASIS · DEFINITIONS</span><span>as of ' + esc(p.as_of || '') + '</span></summary>'
    + '<div style="margin-top:8px; display:grid; grid-template-columns:110px 1fr; gap:6px 12px">'
    + basisRows.map((r) => '<div style="' + LABEL + '; padding-top:2px">' + esc(r[0]).toUpperCase() + '</div><div style="' + NOTIZ + '">' + esc(r[1]) + '</div>').join('')
    + '</div></details>';

  return '<div style="' + KARTE + '; padding:16px 18px; margin-top:14px">' + head + swap
    + '<div style="margin-top:12px; border:1px solid var(--line-3); border-radius:var(--r-panel); padding:10px 8px 4px; background:var(--panel)">' + kurve + '</div>'
    + statsHtml + basis + '</div>';
}

function renderEdge(d) {
  const e = d.edge || null;
  const pd = e && e.per_dollar ? e.per_dollar : null;
  const ps = e && e.per_share ? e.per_share : null;
  if (!e || !pd || pd.edge == null) {
    return card('REALIZED EDGE', '<div style="' + NOTIZ + '">No realized edge: no resolved positions with a stake in the closed-positions feed.</div>');
  }
  const punkte = [];
  if (pd.ci_low != null && pd.ci_high != null) punkte.push({ label: 'All events · n ' + pd.groups, wert: +(pd.edge * 100).toFixed(2), von: +(pd.ci_low * 100).toFixed(2), bis: +(pd.ci_high * 100).toFixed(2) });
  else punkte.push({ label: 'All events · n ' + pd.groups, wert: +(pd.edge * 100).toFixed(2) });
  (e.by_category || []).forEach((c) => {
    const p = { label: c.category + ' · n ' + c.groups, wert: +(c.edge * 100).toFixed(2) };
    if (c.ci_low != null && c.ci_high != null) { p.von = +(c.ci_low * 100).toFixed(2); p.bis = +(c.ci_high * 100).toFixed(2); }
    punkte.push(p);
  });
  const dia = diagramm({ titel: 'RETURN PER $ STAKED · 95% CI', einheit: 'cents per dollar', referenz: 0, referenz_label: 'break even', punkte });
  const verdictColor = ps && ps.verdict === 'positive' ? 'var(--pos)' : ps && ps.verdict === 'negative' ? 'var(--neg)' : 'var(--warn)';
  const summary = '<div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(200px, 1fr)); gap:12px 16px; margin-top:12px">'
    + '<div><div style="' + LABEL + '">EDGE PER $ · CLUSTER BOOTSTRAP</div><div style="' + M + '; font-size:var(--t-body); margin-top:3px; color:' + pnlColor(pd.edge) + '">' + (pd.edge * 100).toFixed(1) + '¢ per $</div><div style="' + NOTIZ + '; margin-top:2px">95% CI ' + (pd.ci_low != null ? '[' + (pd.ci_low * 100).toFixed(1) + '¢, ' + (pd.ci_high * 100).toFixed(1) + '¢]' : 'not computable') + ' · n ' + pd.groups + ' events · ' + (pd.significant ? 'excludes zero' : 'includes zero') + '</div></div>'
    + (ps ? '<div><div style="' + LABEL + '">EDGE PER SHARE · ENTRY VS SETTLEMENT</div><div style="' + M + '; font-size:var(--t-body); margin-top:3px; color:' + verdictColor + '">' + pp(ps.edge) + ' · ' + esc(String(ps.verdict || '').toUpperCase()) + '</div><div style="' + NOTIZ + '; margin-top:2px">' + (ps.ci_low != null ? '95% CI [' + pp(ps.ci_low) + ', ' + pp(ps.ci_high) + '] · ' : '') + 'n ' + ps.n_events + ' events / ' + ps.n_positions + ' positions</div></div>' : '')
    + '</div>'
    + (ps && ps.headline ? '<div style="' + NOTIZ + '; margin-top:10px">' + esc(ps.headline) + '</div>' : '')
    + '<div style="' + NOTIZ + '; margin-top:6px">' + esc(pd.method || '') + (e.capped ? ' Capped tails: the sample holds the biggest wins and losses only, so the edge is biased either way.' : '') + '</div>';
  return card('REALIZED EDGE', dia + summary, 'as of ' + esc(e.as_of || '') + (e.capped ? ' · CAPPED' : ''));
}

function renderOpenPositions(T, d) {
  const op = d.open_positions || null;
  const sortKey = T.state.walletPosSort || 'value';
  const chip = (label, key) => (T.chip ? T.chip(label, sortKey === key, { walletPosSort: key }) : '<div>' + esc(label) + '</div>');
  const sortBar = '<div style="display:flex; align-items:center; gap:8px; margin-bottom:10px; flex-wrap:wrap"><span style="' + LABEL + '">SORT BY</span>' + chip('Value', 'value') + chip('Unrealised', 'pnl') + chip('Cost', 'cost') + chip('Ends', 'ends') + '</div>';
  if (!op || !op.n) {
    return card('OPEN POSITIONS', '<div style="' + NOTIZ + '">' + esc(op && op.note ? op.note : 'No open positions in the public /positions feed.') + '</div>', op ? 'as of ' + esc(op.as_of || '') : '');
  }
  const rows = (op.rows || []).slice().sort((a, b) => {
    if (sortKey === 'pnl') return (b.unrealized_pnl || 0) - (a.unrealized_pnl || 0);
    if (sortKey === 'cost') return (b.cost || 0) - (a.cost || 0);
    if (sortKey === 'ends') return String(a.end_time || '9') < String(b.end_time || '9') ? -1 : 1;
    return (b.value || 0) - (a.value || 0);
  });
  const cols = '2.2fr 60px 80px 70px 70px 90px 100px 100px 90px';
  const head = '<div>MARKET</div><div>SIDE</div><div style="text-align:right">SHARES</div><div style="text-align:right">AVG</div><div style="text-align:right">NOW</div><div style="text-align:right">VALUE</div><div style="text-align:right">UNREALISED</div><div>ENDS</div><div>STATUS</div>';
  const body = rows.map((r) => row(cols,
    cell(link(r.url, r.title), 'font-family:var(--font-ui); font-size:var(--t-small)')
    + cell(esc(r.outcome || '—'), 'color:' + (String(r.outcome).toLowerCase() === 'yes' ? 'var(--accent)' : 'var(--neg-soft)'))
    + cell(fmtZahl(r.size), 'text-align:right; color:var(--ink-3)')
    + cell(cents(r.avg_price), 'text-align:right; color:var(--ink-3)')
    + cell(cents(r.current_price), 'text-align:right')
    + cell(absDollars(r.value), 'text-align:right')
    + cell(dollars(r.unrealized_pnl), 'text-align:right; color:' + pnlColor(r.unrealized_pnl))
    + cell(r.end_time ? String(r.end_time).slice(0, 10) : '—', 'color:var(--ink-4)')
    + cell(r.status === 'worthless' ? 'resolved · not redeemed' : 'open', 'color:' + (r.status === 'worthless' ? 'var(--warn)' : 'var(--ink-3)')))).join('');
  // Die drei Buch-Kacheln beschreiben die offenen Zeilen; die wertlosen
  // sind aufgeloest und bekommen ihre eigene.
  const openN = Math.max(0, (Number(op.n) || 0) - (Number(op.worthless_n) || 0));
  const totals = '<div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(150px, 1fr)); gap:10px; margin-bottom:12px">'
    + tile('TOTAL EXPOSURE', absDollars(op.total_exposure), 'value at current prices · ' + num(openN) + ' open position' + (openN === 1 ? '' : 's'))
    + tile('COST BASIS', absDollars(op.total_cost), 'shares × average price · open only')
    + tile('UNREALISED', dollars(op.unrealized_pnl), 'value − cost · open only', pnlColor(op.unrealized_pnl))
    // Der Verlust wertloser Positionen ist aufgeloest, nicht unrealisiert.
    // Er lag bisher in derselben Summe wie der Buchgewinn der offenen
    // Positionen und stand unter der Ueberschrift UNREALISED.
    + tile('RESOLVED · NOT REDEEMED', num(op.worthless_n || 0),
      op.worthless_n ? dollars(op.worthless_pnl || 0) + ' settled loss · at price 0 past end date' : 'at price 0 past end date',
      op.worthless_n ? 'var(--warn)' : null)
    + '</div>';
  const count = '<div style="' + NOTIZ + '; margin-bottom:8px">' + num(rows.length) + ' of ' + num(op.n) + ' positions' + (op.capped ? ' · the /positions page was full — there may be more' : '') + '</div>';
  return card('OPEN POSITIONS', totals + sortBar + count + tableWith(cols, head, body, '', 900) + '<div style="' + NOTIZ + '; margin-top:8px">' + esc(op.note || '') + '</div>', 'as of ' + esc(op.as_of || ''));
}

function renderClosed(d) {
  const c = d.closed || null;
  if (!c || !c.n) {
    return card('CLOSED POSITIONS', '<div style="' + NOTIZ + '">' + esc(c && c.note ? c.note : 'No resolved positions in the closed-positions feed for this wallet.') + '</div>', c ? 'as of ' + esc(c.as_of || '') : '');
  }
  const summary = '<div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(140px, 1fr)); gap:10px; margin-bottom:12px">'
    + tile('RESOLVED', num(c.n), c.capped ? 'CAPPED — both tails at ~50' : 'complete set (both tails)', c.capped ? 'var(--warn)' : null)
    + tile('WON', num(c.won), 'realised PnL &gt; 0', 'var(--pos)')
    + tile('LOST', num(c.lost), 'realised PnL &lt; 0', 'var(--neg)')
    + tile('FLAT', num(c.flat), 'realised PnL = 0')
    + tile('WORTHLESS · NOT REDEEMED', num(c.worthless_not_redeemed || 0), 'still in /positions at 0', c.worthless_not_redeemed ? 'var(--warn)' : null)
    + tile('REALISED PNL', dollars(c.realized_pnl), 'sum over the ' + num(c.n) + ' rows', pnlColor(c.realized_pnl))
    + '</div>';
  const cols = '2.2fr 60px 70px 80px 90px 100px 70px 120px';
  const head = '<div>MARKET</div><div>SIDE</div><div style="text-align:right">ENTRY</div><div style="text-align:right">SETTLED</div><div style="text-align:right">BOUGHT</div><div style="text-align:right">REALISED</div><div>RESULT</div><div>TIME</div>';
  const body = (c.rows || []).map((r) => row(cols,
    cell(link(r.url, r.title), 'font-family:var(--font-ui); font-size:var(--t-small)')
    + cell(esc(r.outcome || '—'), 'color:' + (String(r.outcome).toLowerCase() === 'yes' ? 'var(--accent)' : 'var(--neg-soft)'))
    + cell(cents(r.avg_price), 'text-align:right; color:var(--ink-3)')
    + cell(cents(r.current_price), 'text-align:right; color:var(--ink-3)')
    + cell(absDollars(r.total_bought), 'text-align:right')
    + cell(dollars(r.realized_pnl), 'text-align:right; color:' + pnlColor(r.realized_pnl))
    + cell(esc(r.result || '—'), 'color:' + (r.result === 'won' ? 'var(--pos)' : r.result === 'lost' ? 'var(--neg)' : 'var(--ink-4)'))
    + cell(when(r.time), 'color:var(--ink-4)'))).join('');
  const count = '<div style="' + NOTIZ + '; margin-bottom:8px">' + num(c.shown) + ' of ' + num(c.n) + ' resolved positions, largest |PnL| first' + (c.capped ? ' · capped: only the ~50 biggest winners and ~50 biggest losers are reachable' : '') + '</div>';
  return card('CLOSED POSITIONS', summary + count + tableWith(cols, head, body, '', 900) + '<div style="' + NOTIZ + '; margin-top:8px">' + esc(c.note || '') + ' Source: ' + esc(c.source || '') + '</div>', 'as of ' + esc(c.as_of || '') + (c.capped ? ' · CAPPED' : ''));
}

function renderCategoriesContext(d) {
  const cats = d.categories && Array.isArray(d.categories.rows) ? d.categories.rows : [];
  const ctx = d.context || null;
  const catDia = cats.length ? diagramm({
    titel: 'STAKE BY CATEGORY', einheit: 'USD bought (label: trades · settled PnL)',
    punkte: cats.map((c) => ({ label: c.category + ' · ' + c.trades + ' t · ' + dollars(c.pnl), wert: +(+c.stake).toFixed(0) }))
  }) : '<div style="' + NOTIZ + '">No trades in the activity window to put in a category.</div>';
  const groups = ctx && Array.isArray(ctx.groups) ? ctx.groups : [];
  const ctxDia = groups.length ? diagramm({
    titel: 'INSIDER-CONTEXT GROUPS · SHARE OF NOTIONAL', einheit: '% of $' + num(Math.round(ctx.notional || 0)),
    punkte: groups.map((g) => ({ label: g.group + ' · ' + g.trades + ' t', wert: +((g.share || 0) * 100).toFixed(1), art: g.insider_prone ? 'summe' : 'kosten' }))
  }) : '<div style="' + NOTIZ + '">No trades to classify.</div>';
  const ctxLine = ctx && ctx.insider_prone_share != null
    ? '<div style="' + NOTIZ + '; margin-top:8px">' + pct(ctx.insider_prone_share) + ' of traded notional sits in insider-plausible groups (politics, awards, corporate/legal, general); ' + pct(ctx.excluded_share) + ' in the groups the risk screen excludes (sports odds, weather, crypto/market prices). n ' + num(ctx.n_trades) + ' trades.</div>'
    : '';
  return '<div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(340px, 1fr)); gap:14px; margin-top:14px">'
    + '<div style="' + KARTE + '; padding:16px 18px"><div style="' + LABEL + '; margin-bottom:10px">CATEGORIES · ' + (d.categories ? 'as of ' + esc(d.categories.as_of || '') : '') + '</div>' + catDia + '<div style="' + NOTIZ + '; margin-top:8px">' + esc(d.categories ? d.categories.note + ' Classifier: ' + d.categories.classifier : '') + '</div></div>'
    + '<div style="' + KARTE + '; padding:16px 18px"><div style="' + LABEL + '; margin-bottom:10px">INSIDER CONTEXT · ' + (ctx ? 'as of ' + esc(ctx.as_of || '') : '') + '</div>' + ctxDia + ctxLine + '<div style="' + NOTIZ + '; margin-top:6px">' + esc(ctx ? ctx.note : '') + '</div></div>'
    + '</div>';
}

function renderTrades(d) {
  const a = d.activity || null;
  if (!a || !a.n_trades) {
    return card('RECENT TRADES', '<div style="' + NOTIZ + '">No trades in the public /activity feed for this wallet' + (a && a.n_rows ? ' (' + num(a.n_rows) + ' rows read, none of type TRADE)' : '') + '.</div>', a ? 'as of ' + esc(a.as_of || '') : '');
  }
  const summary = '<div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(140px, 1fr)); gap:10px; margin-bottom:12px">'
    + tile('TRADES READ', num(a.n_trades), num(a.n_rows) + ' activity rows · ' + num(a.n_redeems) + ' redemptions' + (a.window_truncated ? ' · WINDOW TRUNCATED' : ''), a.window_truncated ? 'var(--warn)' : null)
    + tile('BUY · SELL', num(a.buy_n) + ' · ' + num(a.sell_n), absDollars(a.buy_notional) + ' bought · ' + absDollars(a.sell_notional) + ' sold')
    + tile('AVG TRADE', a.avg_trade_size != null ? absDollars(a.avg_trade_size) : '—', 'notional per trade')
    + tile('TRADES / DAY', a.trades_per_day != null ? fmtZahl(a.trades_per_day) : '—', 'over ' + (a.span_days != null ? fmtZahl(a.span_days) : '—') + ' days in the window')
    + tile('NET CASH FLOW', dollars(a.net_cash_flow), 'sells + redemptions − buys · open positions not in it', pnlColor(a.net_cash_flow))
    + '</div>';
  const cols = '120px 60px 60px 70px 80px 90px 2.4fr';
  const head = '<div>TIME (UTC)</div><div>SIDE</div><div>OUTCOME</div><div style="text-align:right">PRICE</div><div style="text-align:right">SHARES</div><div style="text-align:right">NOTIONAL</div><div>MARKET</div>';
  const body = (a.trades || []).map((t) => row(cols,
    cell(when(t.time), 'color:var(--ink-4)')
    + cell(esc(t.side || '—'), 'color:' + (t.side === 'BUY' ? 'var(--pos)' : 'var(--neg)'))
    + cell(esc(t.outcome || '—'))
    + cell(cents(t.price), 'text-align:right')
    + cell(fmtZahl(t.size), 'text-align:right; color:var(--ink-3)')
    + cell(absDollars(t.notional), 'text-align:right')
    + cell(link(t.url, t.title), 'font-family:var(--font-ui); font-size:var(--t-small)'))).join('');
  const count = '<div style="' + NOTIZ + '; margin-bottom:8px">' + num(a.shown) + ' of ' + num(a.n_trades) + ' trades, newest first' + (a.window_truncated ? ' · the activity window was cut at the page cap, older trades are not read here' : '') + '</div>';
  return card('RECENT TRADES', summary + count + tableWith(cols, head, body, '', 900), 'as of ' + esc(a.as_of || '') + ' · ' + esc(a.source || '') + (a.window_truncated ? ' · WINDOW TRUNCATED' : ''));
}

function renderLimits(d) {
  const lim = Array.isArray(d.limits) ? d.limits : [];
  if (!lim.length) return '';
  const errs = d.errors && typeof d.errors === 'object' ? Object.entries(d.errors) : [];
  return card('LIMITS OF THIS READ',
    '<ul style="margin:0; padding-left:18px; font-size:var(--t-small); color:var(--ink-3); line-height:1.65">' + lim.map((l) => '<li>' + esc(l) + '</li>').join('') + '</ul>'
    + (errs.length ? '<div style="' + NOTIZ + '; margin-top:10px; color:var(--warn)">Parts that did not answer this time: ' + errs.map((e) => esc(e[0]) + ' (' + esc(e[1]) + ')').join(' · ') + '</div>' : ''));
}

// ---- risk tab: profit factor, risk/reward, streaks, conviction, heatmap ----
function riskCard(label, value, sub, tone, partial) {
  const border = tone === 'up' ? 'rgba(var(--pos-rgb),.35)' : tone === 'down' ? 'rgba(var(--neg-rgb),.35)' : tone === 'warn' ? 'rgba(var(--warn-rgb),.4)' : 'var(--line-2)';
  const color = tone === 'up' ? 'var(--pos)' : tone === 'down' ? 'var(--neg)' : tone === 'warn' ? 'var(--warn)' : 'var(--text)';
  return '<div style="' + KARTE + '; border-color:' + border + '; padding:14px 16px; min-width:0">'
    + '<div style="display:flex; justify-content:space-between; gap:8px; align-items:center"><div style="' + LABEL + '">' + label + '</div>'
    + (partial ? '<span title="the closed set is capped at ~50 rows per tail — these figures describe the biggest winners and losers only" style="' + M + '; font-size:var(--t-micro); letter-spacing:.1em; color:var(--warn); border:1px solid rgba(var(--warn-rgb),.45); border-radius:var(--r-control); padding:1px 6px">~PARTIAL</span>' : '') + '</div>'
    + '<div style="' + M + '; font-size:var(--t-hero); margin-top:8px; color:' + color + '">' + value + '</div>'
    + (sub ? '<div style="' + NOTIZ + '; margin-top:4px">' + sub + '</div>' : '') + '</div>';
}

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

// Trades by weekday and UTC hour; cell depth = share of the busiest cell.
// Every cell carries its count and notional in the title. Without trades
// the grid is not drawn (a flat grid of zeros would look like quiet
// weekends, not like an unread wallet).
function heatmapHtml(hm) {
  if (!hm || !hm.n || !Array.isArray(hm.counts)) return '<div style="' + NOTIZ + '">No trades in the activity window — nothing to place on the clock.</div>';
  let max = 0;
  hm.counts.forEach((r) => r.forEach((v) => { if (v > max) max = v; }));
  const hours = Array.from({ length: 24 }, (_, i) => i);
  const head = '<div style="display:grid; grid-template-columns:34px repeat(24, minmax(0,1fr)); gap:3px; margin-bottom:4px">'
    + '<div></div>' + hours.map((h) => '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-3); text-align:center">' + (h % 3 === 0 ? h : '') + '</div>').join('') + '</div>';
  const rows = hm.counts.map((r, wd) => '<div style="display:grid; grid-template-columns:34px repeat(24, minmax(0,1fr)); gap:3px; margin-bottom:3px">'
    + '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-4); align-self:center">' + WEEKDAYS[wd] + '</div>'
    + r.map((v, h) => {
      const a = max > 0 ? v / max : 0;
      const bg = v > 0 ? 'rgba(var(--info-rgb),' + (0.18 + a * 0.72).toFixed(2) + ')' : 'rgba(var(--ink),.04)';
      const usd = hm.notional && hm.notional[wd] ? hm.notional[wd][h] : 0;
      return '<div title="' + esc(WEEKDAYS[wd] + ' ' + String(h).padStart(2, '0') + ':00 UTC — ' + v + ' trade' + (v === 1 ? '' : 's') + (v ? ' · ' + absDollars(usd) : '')) + '" style="height:16px; border-radius:var(--r-control); background:' + bg + '"></div>';
    }).join('') + '</div>').join('');
  const busiest = hm.busiest ? WEEKDAYS[hm.busiest.weekday] + ' ' + String(hm.busiest.hour).padStart(2, '0') + ':00 UTC (' + hm.busiest.trades + (hm.busiest.trades === 1 ? ' trade)' : ' trades)') : '—';
  return head + rows
    + '<div style="' + NOTIZ + '; margin-top:8px">' + esc(hm.note || '') + ' · n ' + num(hm.n) + ' trades · busiest cell ' + esc(busiest) + '</div>';
}

function renderRiskTab(d) {
  const rp = d.risk_profile || null;
  const partial = !!(rp && rp.partial);
  const fmt = (v, digits) => (v == null ? '—' : Number(v).toFixed(digits == null ? 2 : digits));
  const bands = rp && rp.bands ? rp.bands : {};
  const cards = rp && rp.n_rows
    ? [
      riskCard('PROFIT FACTOR', fmt(rp.profit_factor), (bands.profit_factor ? esc(bands.profit_factor) + ' · ' : '') + 'wins ' + absDollars(rp.avg_win != null ? rp.avg_win * rp.n_win : 0) + ' / losses ' + absDollars(rp.avg_loss != null ? rp.avg_loss * rp.n_loss : 0),
        rp.profit_factor == null ? 'neutral' : rp.profit_factor >= 1.2 ? 'up' : rp.profit_factor >= 1 ? 'warn' : 'down', partial),
      riskCard('RISK / REWARD', fmt(rp.risk_reward), (bands.risk_reward ? esc(bands.risk_reward) + ' · ' : '') + 'avg win ' + absDollars(rp.avg_win) + ' · avg loss ' + absDollars(rp.avg_loss),
        rp.risk_reward == null ? 'neutral' : rp.risk_reward >= 1.5 ? 'up' : rp.risk_reward >= 0.8 ? 'warn' : 'down', partial),
      riskCard('WIN STREAK', String(rp.win_streak), rp.win_streak + ' consecutive winning rows' + (rp.current_streak_kind === 'win' ? ' · current run ' + rp.current_streak : ''), rp.win_streak > 0 ? 'up' : 'neutral', partial),
      riskCard('LOSS STREAK', String(rp.loss_streak), rp.loss_streak + ' consecutive losing rows' + (rp.current_streak_kind === 'loss' ? ' · current run ' + rp.current_streak : ''), rp.loss_streak > 0 ? 'down' : 'neutral', partial),
      riskCard('CONVICTION', rp.conviction == null ? '—' : fmt(rp.conviction) + '×', (bands.conviction ? esc(bands.conviction) + ' · ' : '') + 'avg stake won ' + absDollars(rp.avg_stake_win) + ' / lost ' + absDollars(rp.avg_stake_loss),
        rp.conviction == null ? 'neutral' : rp.conviction >= 1.2 ? 'up' : rp.conviction >= 0.8 ? 'warn' : 'down', partial)
    ].join('')
    : '';
  const rules = rp && rp.rules ? '<div style="' + NOTIZ + '; margin-top:10px; line-height:1.6">'
    + Object.entries(rp.rules).map((kv) => '<span style="color:var(--ink-3)">' + esc(kv[0].replace(/_/g, ' ')) + '</span>: ' + esc(kv[1])).join(' · ') + '</div>' : '';
  // Die Kachel hiess INSIDER-RISK SCORE und zeigte daneben das interne Level
  // (HIGH/MEDIUM/ELEVATED/LOW). Zusammen las sich das wie eine
  // Wahrscheinlichkeit fuer Insiderhandel. Es ist eine Punktesumme aus neun
  // Flow-Merkmalen mit gesetzten Gewichten; Name und Band kommen jetzt aus
  // ../risk_bands.js, der stehende Vorbehalt aus dem Register.
  const insiderBand = d.risk && typeof d.risk === 'object' && d.risk.wallet_insider_score != null
    ? scoreBand(d.risk.wallet_insider_score, null, d.risk) : null;
  const insider = insiderBand
    ? '<div style="' + KARTE + '; padding:14px 16px; margin-top:14px"><div style="' + LABEL + '">FLOW-PATTERN SCORE · FROM THE RISK SCREEN</div>'
      + '<div style="display:flex; gap:14px; align-items:baseline; margin-top:6px"><div style="' + M + '; font-size:var(--t-head); color:' + (d.risk.wallet_insider_score >= 70 ? 'var(--warn)' : 'var(--text)') + '">' + Math.round(d.risk.wallet_insider_score) + '<span style="font-size:var(--t-small); color:var(--ink-3)"> /100 pts</span></div>'
      + '<span style="' + M + '; font-size:var(--t-micro); letter-spacing:.1em; color:' + insiderBand[1] + '">' + esc(insiderBand[0]) + '</span></div>'
      + (Array.isArray(d.risk.flags) && d.risk.flags.length ? '<div style="display:flex; gap:6px; flex-wrap:wrap; margin-top:8px">' + d.risk.flags.map((f) => '<span style="' + M + '; font-size:var(--t-micro); color:var(--warn); border:1px solid rgba(var(--warn-rgb),.35); border-radius:var(--r-control); padding:2px 7px">' + esc(f) + '</span>').join('') + '</div>' : '<div style="' + NOTIZ + '; margin-top:6px">no flags on this wallet in the current screen</div>')
      + '<div style="' + NOTIZ + '; margin-top:8px; line-height:1.5">' + caveat('insider_score_unvalidated') + '</div>'
      + '</div>'
    : '';
  const head = card('RISK PROFILE · FROM THE RESOLVED ROWS',
    (cards ? '<div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(190px, 1fr)); gap:10px">' + cards + '</div>' : '<div style="' + NOTIZ + '">No resolved rows to read a profit factor, streaks or conviction from.</div>')
    + (rp && rp.note ? '<div style="' + NOTIZ + '; margin-top:10px">' + esc(rp.note) + '</div>' : '') + rules,
    rp ? 'as of ' + esc(rp.as_of || '') + (partial ? ' · PARTIAL (capped tails)' : '') : '');
  const clock = card('TRADING ACTIVITY · WEEKDAY × UTC HOUR', heatmapHtml(rp ? rp.heatmap : null), rp && rp.heatmap ? 'n ' + num(rp.heatmap.n) + ' trades' : '');
  return head + clock + insider;
}

// ---- similar wallets: top holders of the same markets ---------------------
function renderSimilarTab(T, d) {
  const addr = String(T.state.walletAddr || '').toLowerCase();
  if (typeof T.fetchWalletSimilar === 'function') T.fetchWalletSimilar(addr);
  const entry = T.liveData && T.liveData.walletSimilar ? T.liveData.walletSimilar[addr] : null;
  const intro = '<div style="' + KARTE + '; padding:14px 16px; margin-top:14px; display:flex; gap:12px; align-items:flex-start">'
    + '<div style="width:34px; height:34px; flex:none; border-radius:var(--r-control); border:1px solid rgba(var(--info-rgb),.4); display:flex; align-items:center; justify-content:center; color:var(--info); ' + M + '; font-size:var(--t-body)">≡</div>'
    + '<div><div style="font-size:var(--t-body)">Similar wallets</div><div style="' + NOTIZ + '; margin-top:3px">Wallets among the top holders of this wallet\'s largest open markets, sorted by how many of those markets they share — same side or opposite side. Read from the public /holders feed when this tab is opened.</div></div></div>';
  if (!entry || entry.herkunft === 'loading') {
    return intro + card('SIMILAR WALLETS', '<div style="' + NOTIZ + '">Reading the top holders of the largest open markets — up to ~22 public API calls, a few seconds…</div>');
  }
  if (entry.herkunft === 'fehler') {
    return intro + card('SIMILAR WALLETS', '<div style="' + NOTIZ + '; color:var(--warn)">/api/wallet/' + esc(shortAddr(addr)) + '/similar did not answer: ' + esc(entry.fehler || 'unknown error') + '.</div>'
      + '<div style="margin-top:10px"><div ' + T.act(() => { if (T.fetchWalletSimilar) T.fetchWalletSimilar(addr, true); }) + ' class="hv-bd32" style="' + M + '; font-size:var(--t-micro); color:var(--ink-2); border:1px solid var(--line-1); border-radius:var(--r-control); padding:5px 10px; cursor:pointer; display:inline-block">Try again</div></div>');
  }
  const data = entry.data || {};
  const basis = data.basis || {};
  const q = String(T.state.walletSimilarQuery || '').trim().toLowerCase();
  const rowsAll = Array.isArray(data.rows) ? data.rows : [];
  const rows = q ? rowsAll.filter((r) => String(r.wallet).indexOf(q) >= 0 || String(r.name || '').toLowerCase().indexOf(q) >= 0) : rowsAll;
  const search = '<input value="' + esc(T.state.walletSimilarQuery || '') + '" ' + T.inp((e) => { T.state.walletSimilarQuery = e.target.value; T.render(); }, 'walletSimilarQuery')
    + ' placeholder="search wallet address or name…" spellcheck="false" style="width:100%; box-sizing:border-box; background:var(--panel); border:1px solid var(--line-edge); border-radius:var(--r-control); padding:9px 12px; ' + M + '; font-size:var(--t-small); color:var(--text); margin-bottom:12px" />';
  const cols = 'minmax(220px, 2fr) 110px 150px 150px 120px 90px 170px';
  const head = '<div>WALLET</div><div style="text-align:right">SHARED MARKETS</div><div style="text-align:right">THEIR OPEN POSITIONS</div><div>OVERLAP</div><div style="text-align:right">LEADERBOARD PNL</div><div style="text-align:right">VOLUME</div><div style="text-align:right">VIEW</div>';
  const body = rows.map((r) => {
    const bar = '<div style="display:flex; align-items:center; gap:8px"><div style="flex:1; height:5px; background:rgba(var(--ink),.08); border-radius:var(--r-control); overflow:hidden"><div style="width:' + Math.round((r.overlap || 0) * 100) + '%; height:5px; background:var(--info)"></div></div><span style="' + M + '; font-size:var(--t-small)">' + Math.round((r.overlap || 0) * 100) + '%</span></div>';
    const sides = (r.same_side ? r.same_side + ' same side' : '') + (r.same_side && r.opposite_side ? ' · ' : '') + (r.opposite_side ? r.opposite_side + ' opposite' : '');
    return row(cols,
      '<div style="min-width:0"><div style="' + M + '; font-size:var(--t-small); white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="' + esc(r.wallet) + '">' + (r.name ? esc(r.name) + ' <span style="color:var(--ink-3)">· ' + esc(r.short) + '</span>' : esc(r.short)) + '</div><div style="' + NOTIZ + '; white-space:nowrap; overflow:hidden; text-overflow:ellipsis">' + esc(sides || 'sides not readable') + '</div></div>'
      + cell(num(r.shared) + ' <span style="color:var(--ink-3)">/ ' + num(basis.markets_read != null ? basis.markets_read : (basis.markets_checked || 0)) + '</span>', 'text-align:right')
      + cell(r.summary_read && r.their_positions != null ? num(r.their_positions) + ' <span style="color:var(--ink-3)">· ' + absDollars(r.their_value) + '</span>' : 'not read', 'text-align:right; color:' + (r.summary_read ? 'var(--text)' : 'var(--ink-3)'))
      + cell(bar, '')
      + cell(r.on_leaderboard && r.lb_pnl != null ? dollars(r.lb_pnl) : 'not on board', 'text-align:right; color:' + (r.on_leaderboard && r.lb_pnl != null ? pnlColor(r.lb_pnl) : 'var(--ink-3)'))
      + cell(r.on_leaderboard && r.lb_volume != null ? money(r.lb_volume) : '—', 'text-align:right; color:var(--ink-3)')
      + cell('<span ' + T.act(() => { if (T.analyseWallet) T.analyseWallet(r.wallet); }) + ' class="hv-bd32" style="' + M + '; font-size:var(--t-micro); color:var(--ink-2); border:1px solid var(--line-1); border-radius:var(--r-control); padding:3px 8px; cursor:pointer">Analyse</span> '
        + (r.profile_url ? '<a href="' + esc(r.profile_url) + '" target="_blank" rel="noopener" data-stop style="' + M + '; font-size:var(--t-micro); color:var(--info); text-decoration:none; margin-left:6px">profile ↗</a>' : ''), 'text-align:right'));
  }).join('');
  const table = tableWith(cols, head, body, rowsAll.length ? 'No wallet matches the search.' : 'No overlapping top holder found in the checked markets.', 1010);
  const errs = Array.isArray(basis.errors) && basis.errors.length ? '<div style="' + NOTIZ + '; margin-top:8px; color:var(--warn)">Markets that did not answer: ' + basis.errors.map((e) => esc(e)).join(' · ') + '</div>' : '';
  // Gelesen statt nur angefragt: ein fehlgeschlagener Abruf kann keinen
  // Treffer liefern und gehoert nicht in den Nenner. Der Median sagt, wie viel
  // Ueberschneidung hier ueblich ist — die Holder-Listen sind nach Groesse
  // sortiert, also stehen dieselben grossen Wallets ueberall.
  const gelesen = basis.markets_read != null ? basis.markets_read : (basis.markets_checked || 0);
  const sub = 'as of ' + esc(data.as_of || '') + ' · ' + num(gelesen) + ' of ' + num(basis.markets_available || 0)
    + ' open markets read' + (basis.markets_checked && gelesen !== basis.markets_checked ? ' (' + num(basis.markets_checked) + ' requested)' : '')
    + ' · ' + num(data.candidates || 0) + ' wallets seen'
    + (basis.median_shared ? ' · median candidate shares ' + num(basis.median_shared) : '');
  return intro + card('SIMILAR WALLETS · TOP ' + num(rows.length) + (rowsAll.length !== rows.length ? ' OF ' + num(rowsAll.length) : ''), search + table + '<div style="' + NOTIZ + '; margin-top:8px">' + esc(basis.note || '') + '</div>' + errs, sub);
}

// ---- page ------------------------------------------------------------------
export function renderWallet(T) {
  const s = T.state;
  const addr = String(s.walletAddr || '').toLowerCase();
  let body;
  if (!addr) {
    body = renderIntro();
  } else {
    const entry = T.liveData.wallet ? T.liveData.wallet[addr] : null;
    if (!entry || entry.herkunft === 'loading') body = renderLoading(addr);
    else if (entry.herkunft === 'fehler') body = renderError(T, addr, entry);
    else if (!entry.data) body = leerBlock('EMPTY ANSWER', '/api/wallet/' + shortAddr(addr) + ' answered without a payload. That is the result, not a gap.');
    else {
      const d = entry.data;
      const tab = WALLET_TABS.some((t) => t[0] === s.walletTab) ? s.walletTab : 'overview';
      const tabs = '<div style="display:flex; gap:6px; flex-wrap:wrap; margin-bottom:2px">' + WALLET_TABS.map((t) => (T.tab ? T.tab(t[1], tab === t[0], { walletTab: t[0] }) : '<div>' + esc(t[1]) + '</div>')).join('') + '</div>';
      let main = '';
      if (tab === 'record') main = renderTrackRecord(d) + renderEdge(d);
      else if (tab === 'positions') main = renderOpenPositions(T, d) + renderClosed(d);
      else if (tab === 'trades') main = renderTrades(d);
      else if (tab === 'categories') main = renderCategoriesContext(d);
      else if (tab === 'risk') main = renderRiskTab(d);
      else if (tab === 'similar') main = renderSimilarTab(T, d);
      else main = renderOverview(T, d);
      // Left: the stacked stat cards (224px, wraps under the main column on
      // a narrow screen); right: the tabbed detail. Both read the same
      // payload, so the aside repeats what the tabs prove.
      body = '<div style="padding:16px 24px 28px">'
        + renderIdentity(T, d)
        + renderKpis(d)
        + '<div style="display:flex; gap:14px; align-items:flex-start; flex-wrap:wrap; margin-top:14px">'
        + '<div style="flex:0 0 224px; min-width:200px; max-width:100%">' + renderAside(d) + '</div>'
        + '<div style="flex:1 1 560px; min-width:0">' + tabs + main + '</div>'
        + '</div>'
        + renderLimits(d)
        + '</div>';
    }
  }
  return '<div>' + renderHeader(T) + body + '</div>';
}
