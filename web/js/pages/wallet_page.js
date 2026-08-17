// Wallet analysis — one address, read from the public Polymarket Data API.
//
// The page is a pure function over T (state + liveData.wallet[addr]). Every
// number it prints comes from /api/wallet/<addr> and carries its n, interval
// or as-of; without an answer the page says which request is missing. The
// only thing the page invents is the layout.

import { esc, money, num, signedMoney, stempel, leerBlock } from '../util.js';
import { diagramm, stepKurve, fmtZahl } from '../charts.js';

const M = "font-family:'JetBrains Mono',monospace";
const CARD = 'background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:12px';
const LBL = M + '; font-size:9.5px; letter-spacing:.14em; color:rgba(255,255,255,.45)';
const HEAD_CELL = M + '; font-size:9.5px; letter-spacing:.14em; color:rgba(255,255,255,.45)';
const NOTE = M + '; font-size:10.5px; color:rgba(255,255,255,.45); line-height:1.6';
const CELL = M + '; font-size:12px';

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
  return typeof v === 'number' && v < 0 ? '#FF4545' : '#C8F542';
}
function link(url, text) {
  return url ? '<a href="' + esc(url) + '" target="_blank" rel="noopener" style="color:inherit; text-decoration:underline dotted">' + esc(text) + '</a>' : esc(text);
}
function externalLink(url, text) {
  return '<a href="' + esc(url) + '" target="_blank" rel="noopener" class="hv-lime" style="' + M + '; font-size:11px; color:rgba(255,255,255,.7); text-decoration:underline dotted">' + esc(text) + ' ↗</a>';
}

function card(title, body, sub) {
  return '<div style="' + CARD + '; padding:16px 18px; margin-top:14px">'
    + '<div style="display:flex; align-items:baseline; justify-content:space-between; gap:12px; flex-wrap:wrap; margin-bottom:10px">'
    + '<div style="' + LBL + '">' + title + '</div>'
    + (sub ? '<div style="' + NOTE + '">' + sub + '</div>' : '') + '</div>'
    + body + '</div>';
}

function tile(label, value, sub, color) {
  return '<div style="' + CARD + '; padding:12px 14px; min-width:0">'
    + '<div style="' + LBL + '">' + label + '</div>'
    + '<div style="' + M + '; font-size:20px; margin-top:5px; color:' + (color || '#fff') + '; white-space:nowrap; overflow:hidden; text-overflow:ellipsis">' + value + '</div>'
    + (sub ? '<div style="' + NOTE + '; margin-top:3px">' + sub + '</div>' : '') + '</div>';
}

// A table inside its own horizontal scroller: the page never scrolls sideways.
function table(columns, rowsHtml, emptyText, minWidth) {
  const head = '<div style="display:grid; grid-template-columns:' + columns + '; gap:0 10px; padding:9px 14px; background:#0D1114; border-bottom:1px solid rgba(255,255,255,.09); ' + HEAD_CELL + '">';
  return '<div style="overflow-x:auto; border:1px solid rgba(255,255,255,.09); border-radius:10px">'
    + '<div style="min-width:' + (minWidth || 720) + 'px">'
    + head + '__HEAD__</div>'
    + (rowsHtml || '<div style="' + NOTE + '; padding:16px 14px">' + esc(emptyText || 'Nothing to list.') + '</div>')
    + '</div></div>';
}
function row(columns, cellsHtml, extra) {
  return '<div style="display:grid; grid-template-columns:' + columns + '; gap:0 10px; align-items:center; padding:9px 14px; border-bottom:1px solid rgba(255,255,255,.06); ' + (extra || '') + '">' + cellsHtml + '</div>';
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
  const btnStyle = 'font-size:12.5px; font-weight:600; border-radius:8px; padding:9px 14px; cursor:pointer; white-space:nowrap; '
    + (valid ? 'color:#0A0D0F; background:#C8F542' : 'color:rgba(255,255,255,.4); border:1px solid rgba(255,255,255,.14)');
  const analyse = () => { if (T.analyseWallet) T.analyseWallet(input.trim()); };
  const recent = Array.isArray(s.walletRecent) ? s.walletRecent.filter((a) => a !== EXAMPLE_WALLET) : [];
  const chip = (addr, label, title) => '<div ' + T.act(() => { if (T.analyseWallet) T.analyseWallet(addr); }) + ' class="hv-bd32" title="' + esc(title || addr) + '" style="' + M + '; font-size:10.5px; letter-spacing:.04em; border-radius:5px; padding:4px 9px; cursor:pointer; color:rgba(255,255,255,.62); border:1px solid rgba(255,255,255,.16); white-space:nowrap">' + esc(label) + '</div>';
  return '<div style="padding:20px 24px 14px; border-bottom:1px solid rgba(255,255,255,.09)">'
    + '<div style="' + M + '; font-size:10px; letter-spacing:.18em; color:#C8F542">WALLET</div>'
    + '<div style="font-family:\'Instrument Serif\',serif; font-size:30px; line-height:1.1; margin-top:5px">One wallet, read from the public feed</div>'
    + '<div style="font-size:13px; color:rgba(255,255,255,.55); margin-top:8px; max-width:800px">Paste a Polymarket proxy address. The page reads its resolved positions (both tails), open positions, the profile PnL curve and its trades from the public Data API, and prints the corrected track record next to the naive one — every figure with its sample size, interval and time stamp. Read-only, nothing is placed.</div>'
    + '<div style="display:flex; align-items:center; gap:10px; margin-top:14px; flex-wrap:wrap">'
    + '<input value="' + esc(input) + '" ' + T.inp((e) => { T.state.walletInput = e.target.value; T.render(); }, 'walletInput')
    + ' placeholder="0x… (40 hex characters)" spellcheck="false" style="flex:1; min-width:280px; max-width:520px; box-sizing:border-box; background:#10151A; border:1px solid ' + (looksLike ? 'rgba(245,166,35,.5)' : 'rgba(255,255,255,.16)') + '; border-radius:8px; padding:10px 12px; ' + M + '; font-size:12.5px; color:#fff; outline:none" />'
    + '<div ' + T.act(analyse) + (valid ? ' class="hv-limebg"' : '') + ' style="' + btnStyle + '">Analyse →</div>'
    + '</div>'
    + (looksLike ? '<div style="' + M + '; font-size:10.5px; color:#F5A623; margin-top:6px">Not a full address yet — a Polymarket wallet is 0x followed by 40 hex characters.</div>' : '')
    + '<div style="display:flex; align-items:center; gap:8px; margin-top:10px; flex-wrap:wrap">'
    + '<span style="' + LBL + '">EXAMPLE</span>' + chip(EXAMPLE_WALLET, shortAddr(EXAMPLE_WALLET) + ' · live-run wallet', EXAMPLE_WALLET + ' — the wallet the small-stake live runs were placed from')
    + (recent.length ? '<span style="' + LBL + '; margin-left:10px">RECENT</span>' + recent.slice(0, 6).map((a) => chip(a, shortAddr(a))).join('') : '')
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
    + '<div style="' + CARD + '; padding:20px 22px; max-width:760px">'
    + '<div style="' + M + '; font-size:10px; letter-spacing:.14em; color:#F5A623">' + esc(title) + '</div>'
    + '<div style="font-size:13px; color:rgba(255,255,255,.6); margin-top:9px; line-height:1.6">' + esc(text) + '</div>'
    + '<div style="display:flex; gap:8px; margin-top:12px">'
    + '<div ' + T.act(() => { if (T.fetchWallet) T.fetchWallet(addr, true); }) + ' class="hv-bd32" style="' + M + '; font-size:11px; color:rgba(255,255,255,.7); border:1px solid rgba(255,255,255,.16); border-radius:6px; padding:5px 10px; cursor:pointer">Try again</div>'
    + '</div></div></div>';
}

// ---- sections --------------------------------------------------------------
function renderIdentity(T, d) {
  const id = d.identity || {};
  const addr = id.address || T.state.walletAddr;
  const facts = [
    ['FIRST ACTIVITY', when(id.first_activity)],
    ['LAST ACTIVITY', when(id.last_activity)],
    ['DAYS ACTIVE', id.days_active != null ? String(id.days_active) + (id.activity_truncated ? '+ (window truncated)' : '') : '—'],
    ['ACTIVITY ROWS READ', id.n_activity_rows != null ? num(id.n_activity_rows) : '—']
  ];
  const btBtn = '<div ' + T.act(() => {
    if (T.setState) T.setState({ page: 'backtester', detail: null, btWallet: addr, btDirty: !!(T.liveData && T.liveData.backtest) });
    try { history.pushState(null, '', '#backtester'); } catch (e) { /* file:// */ }
  }) + ' class="hv-bd32" style="' + M + '; font-size:11px; color:rgba(255,255,255,.7); border:1px solid rgba(255,255,255,.16); border-radius:6px; padding:6px 11px; cursor:pointer; white-space:nowrap">Replay this wallet in the backtester →</div>';
  return '<div style="' + CARD + '; padding:16px 18px">'
    + '<div style="display:flex; align-items:flex-start; justify-content:space-between; gap:16px; flex-wrap:wrap">'
    + '<div style="min-width:0">'
    + '<div style="font-size:19px">' + esc(id.pseudonym || shortAddr(addr)) + (id.pseudonym ? ' <span style="' + M + '; font-size:12px; color:rgba(255,255,255,.45)">' + esc(shortAddr(addr)) + '</span>' : '') + '</div>'
    + '<div style="' + M + '; font-size:11px; color:rgba(255,255,255,.55); margin-top:4px; word-break:break-all">' + esc(addr) + '</div>'
    + '<div style="display:flex; gap:14px; margin-top:8px; flex-wrap:wrap">'
    + (id.profile_url ? externalLink(id.profile_url, 'Polymarket profile') : '')
    + (id.polygonscan_url ? externalLink(id.polygonscan_url, 'Polygonscan') : '')
    + '</div></div>'
    + '<div style="display:flex; flex-direction:column; align-items:flex-end; gap:8px">'
    + btBtn
    + '<div style="' + NOTE + '">as of ' + esc(d.as_of || stempel(d.snapshot_at)) + ' · cached 300 s</div>'
    + '</div></div>'
    + '<div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(150px, 1fr)); gap:10px; margin-top:14px">'
    + facts.map((f) => '<div><div style="' + LBL + '">' + f[0] + '</div><div style="' + M + '; font-size:13px; margin-top:3px">' + esc(f[1]) + '</div></div>').join('')
    + '</div></div>';
}

function renderKpis(d) {
  const tr = d.track_record || null;
  const st = d.pnl && d.pnl.stats ? d.pnl.stats : null;
  const act = d.activity || null;
  const id = d.identity || {};
  const corr = tr && tr.corrected ? tr.corrected : null;
  const capNote = tr && tr.capped ? ' · capped' : '';
  const tiles = [
    tile('SETTLED PNL', tr ? dollars(tr.settled_pnl) : '—', tr ? 'n ' + num(tr.per_market ? tr.per_market.n : 0) + ' resolved markets' + capNote : 'no track record', tr ? pnlColor(tr.settled_pnl) : null),
    tile('CORRECTED WIN RATE', corr && corr.win_rate != null ? pct(corr.win_rate) : '—', corr && corr.n ? corr.wins + '/' + corr.n + ' events · 95% ' + ci(corr.ci95) + capNote : 'no resolved events'),
    tile('GRADE', tr && tr.grade ? esc(tr.grade) : '—', tr && tr.score != null ? 'score ' + tr.score + ' / 100' + (tr.survivorship_gate && !tr.survivorship_gate.ok ? ' · below sample gate' : '') : ''),
    tile('SHARPE · DAILY $', st && st.sharpe != null ? ratio(st.sharpe) : '—', st ? 'n ' + st.n_days + ' days · no capital base' : 'no PnL curve'),
    tile('MAX DRAWDOWN', st ? absDollars(st.max_drawdown) : '—', st ? pct(st.max_drawdown_pct, 1) + ' of the running peak' : 'no PnL curve', st && st.max_drawdown > 0 ? '#FF4545' : null),
    tile('DAYS ACTIVE', id.days_active != null ? String(id.days_active) : '—', id.first_activity ? 'since ' + String(id.first_activity).slice(0, 10) + (id.activity_truncated ? ' · window truncated' : '') : ''),
    tile('VOLUME TRADED', act && act.n_trades ? money(act.volume_traded) : '—', act && act.n_trades ? num(act.n_trades) + ' trades' + (act.window_truncated ? ' · window truncated' : '') : 'no trades read')
  ];
  return '<div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(160px, 1fr)); gap:10px; margin-top:14px">' + tiles.join('') + '</div>';
}

function renderTrackRecord(d) {
  const tr = d.track_record;
  if (!tr) return card('TRACK RECORD', '<div style="' + NOTE + '">No track record in the answer — the closed-positions feed did not yield a resolved set for this wallet.</div>');
  const cols = '1.6fr 1fr 1fr 1.4fr';
  const rateRow = (label, b, hi) => row(cols,
    cell(esc(label), 'white-space:normal; color:rgba(255,255,255,.75)')
    + cell(b && b.win_rate != null ? pct(b.win_rate) : '—', 'text-align:right; font-size:14px' + (hi ? '; color:#C8F542' : ''))
    + cell(b ? b.wins + ' / ' + b.n : '—', 'text-align:right; color:rgba(255,255,255,.6)')
    + cell(b && b.ci95 ? ci(b.ci95) : '—', 'text-align:right; color:rgba(255,255,255,.6)'));
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
    + facts.map((f) => '<div><div style="' + LBL + '">' + f[0] + '</div><div style="' + M + '; font-size:14px; margin-top:3px; color:' + (f[0] === 'SETTLED PNL' ? pnlColor(tr.settled_pnl) : (f[1] === 'FLAGGED' || f[1] === 'not passed') ? '#F5A623' : '#fff') + '">' + f[1] + '</div>'
      + (f[2] ? '<div style="' + NOTE + '; margin-top:2px">' + esc(f[2]) + '</div>' : '') + '</div>').join('')
    + '</div>';
  const top3 = Array.isArray(conc.top3) && conc.top3.length
    ? '<div style="' + NOTE + '; margin-top:10px">Top-3 markets by profit: ' + conc.top3.map((m) => esc(m.title) + ' (' + dollars(m.pnl) + ', ' + pct(m.share) + ')').join(' · ') + '</div>' : '';
  const parts = Array.isArray(tr.score_components) && tr.score_components.length
    ? '<div style="margin-top:14px"><div style="' + LBL + '">SCORE ' + (tr.score != null ? tr.score : '—') + ' / 100 · GRADE ' + esc(tr.grade || '—') + ' · COMPONENTS</div>'
      + '<div style="display:flex; gap:6px; flex-wrap:wrap; margin-top:6px">'
      + tr.score_components.map((c) => '<span style="' + M + '; font-size:10.5px; color:rgba(255,255,255,.55); border:1px solid rgba(255,255,255,.12); border-radius:4px; padding:2px 7px">' + esc(c.label) + ' <span style="color:rgba(255,255,255,.85)">' + (typeof c.value === 'number' ? (c.value >= 0 ? '' : '') + fmtZahl(c.value) : '—') + '</span>' + (c.max ? ' / ' + c.max : '') + '</span>').join('')
      + '</div></div>' : '';
  const flags = Array.isArray(tr.flags) && tr.flags.length
    ? '<div style="display:flex; gap:6px; flex-wrap:wrap; margin-top:12px">' + tr.flags.map((f) => '<span style="' + M + '; font-size:10.5px; color:#F5A623; border:1px solid rgba(245,166,35,.35); border-radius:4px; padding:2px 7px">' + esc(f) + '</span>').join('') + '</div>'
    : '<div style="' + NOTE + '; margin-top:12px">No flags: sample gate passed, no wash pattern, no one-hit concentration.</div>';
  const cov = '<div style="' + NOTE + '; margin-top:10px">' + esc(tr.coverage_note || '') + (tr.capped ? ' Both tails hit the ~50-row cap: the middle of the record is unreachable, and win rate, edge and PnL describe the extremes only.' : '') + '</div>';
  return card('TRACK RECORD · NAIVE VS CORRECTED', rates + factsHtml + top3 + parts + flags + cov, 'as of ' + esc(tr.as_of || '') + ' · ' + esc(tr.source || '') + (tr.capped ? ' · CAPPED' : ''));
}

function renderPnl(d) {
  const p = d.pnl || null;
  if (!p || !Array.isArray(p.points) || !p.points.length) {
    return card('PROFILE PNL CURVE', '<div style="' + NOTE + '">No PnL curve — user-pnl-api.polymarket.com did not answer for this wallet, so there is no Sharpe, drawdown or win-day share to show.</div>');
  }
  const st = p.stats || null;
  const kurve = stepKurve({
    titel: 'CUMULATIVE PNL · PROFILE CURVE · ' + String(p.window || '').toUpperCase(),
    einheit: 'USD',
    hinweis: num(p.n_points) + ' points · ' + (st ? st.n_days + ' daily changes' : '') + ' · ' + esc(p.source || ''),
    punkte: p.points.map((pt) => ({ label: String(pt.t || '').slice(0, 10), wert: +pt.pnl }))
  });
  const stats = st ? [
    ['SHARPE', ratio(st.sharpe), 'annualised, $ per day'],
    ['SORTINO', ratio(st.sortino), st.sortino == null ? 'no losing day in sample' : 'downside only'],
    ['CALMAR', ratio(st.calmar), st.calmar == null ? 'never in drawdown' : 'annual PnL / max DD'],
    ['MAX DRAWDOWN', absDollars(st.max_drawdown), pct(st.max_drawdown_pct, 1) + ' of the peak'],
    ['WIN-DAY SHARE', pct(st.win_day_rate), st.winning_days + ' up · ' + st.losing_days + ' down · n ' + st.n_days],
    ['BEST · WORST DAY', dollars(st.best_day) + ' · ' + dollars(st.worst_day), 'daily vol $' + fmtZahl(st.daily_vol)],
    ['CURVE TOTAL', dollars(st.total_pnl), 'last minus first point']
  ] : [];
  const statsHtml = st ? '<div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(150px, 1fr)); gap:12px 16px; margin-top:12px">'
    + stats.map((f) => '<div><div style="' + LBL + '">' + f[0] + '</div><div style="' + M + '; font-size:14px; margin-top:3px">' + f[1] + '</div><div style="' + NOTE + '; margin-top:2px">' + esc(f[2]) + '</div></div>').join('')
    + '</div>' : '<div style="' + NOTE + '; margin-top:10px">Curve present, statistics not computable (fewer than two daily points).</div>';
  return card('PROFILE PNL CURVE', kurve + statsHtml + '<div style="' + NOTE + '; margin-top:10px">' + esc(p.note || '') + '</div>', 'as of ' + esc(p.as_of || ''));
}

function renderEdge(d) {
  const e = d.edge || null;
  const pd = e && e.per_dollar ? e.per_dollar : null;
  const ps = e && e.per_share ? e.per_share : null;
  if (!e || !pd || pd.edge == null) {
    return card('REALIZED EDGE', '<div style="' + NOTE + '">No realized edge: no resolved positions with a stake in the closed-positions feed.</div>');
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
  const verdictColor = ps && ps.verdict === 'positive' ? '#C8F542' : ps && ps.verdict === 'negative' ? '#FF4545' : '#F5A623';
  const summary = '<div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(200px, 1fr)); gap:12px 16px; margin-top:12px">'
    + '<div><div style="' + LBL + '">EDGE PER $ · CLUSTER BOOTSTRAP</div><div style="' + M + '; font-size:14px; margin-top:3px; color:' + pnlColor(pd.edge) + '">' + (pd.edge * 100).toFixed(1) + '¢ per $</div><div style="' + NOTE + '; margin-top:2px">95% CI ' + (pd.ci_low != null ? '[' + (pd.ci_low * 100).toFixed(1) + '¢, ' + (pd.ci_high * 100).toFixed(1) + '¢]' : 'not computable') + ' · n ' + pd.groups + ' events · ' + (pd.significant ? 'excludes zero' : 'includes zero') + '</div></div>'
    + (ps ? '<div><div style="' + LBL + '">EDGE PER SHARE · ENTRY VS SETTLEMENT</div><div style="' + M + '; font-size:14px; margin-top:3px; color:' + verdictColor + '">' + pp(ps.edge) + ' · ' + esc(String(ps.verdict || '').toUpperCase()) + '</div><div style="' + NOTE + '; margin-top:2px">' + (ps.ci_low != null ? '95% CI [' + pp(ps.ci_low) + ', ' + pp(ps.ci_high) + '] · ' : '') + 'n ' + ps.n_events + ' events / ' + ps.n_positions + ' positions</div></div>' : '')
    + '</div>'
    + (ps && ps.headline ? '<div style="' + NOTE + '; margin-top:10px">' + esc(ps.headline) + '</div>' : '')
    + '<div style="' + NOTE + '; margin-top:6px">' + esc(pd.method || '') + (e.capped ? ' Capped tails: the sample holds the biggest wins and losses only, so the edge is biased either way.' : '') + '</div>';
  return card('REALIZED EDGE', dia + summary, 'as of ' + esc(e.as_of || '') + (e.capped ? ' · CAPPED' : ''));
}

function renderOpenPositions(T, d) {
  const op = d.open_positions || null;
  const sortKey = T.state.walletPosSort || 'value';
  const chip = (label, key) => (T.chip ? T.chip(label, sortKey === key, { walletPosSort: key }) : '<div>' + esc(label) + '</div>');
  const sortBar = '<div style="display:flex; align-items:center; gap:8px; margin-bottom:10px; flex-wrap:wrap"><span style="' + LBL + '">SORT BY</span>' + chip('Value', 'value') + chip('Unrealised', 'pnl') + chip('Cost', 'cost') + chip('Ends', 'ends') + '</div>';
  if (!op || !op.n) {
    return card('OPEN POSITIONS', '<div style="' + NOTE + '">' + esc(op && op.note ? op.note : 'No open positions in the public /positions feed.') + '</div>', op ? 'as of ' + esc(op.as_of || '') : '');
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
    cell(link(r.url, r.title), 'font-family:\'Inter\',sans-serif; font-size:12.5px')
    + cell(esc(r.outcome || '—'), 'color:' + (String(r.outcome).toLowerCase() === 'yes' ? '#C8F542' : '#FF7A7A'))
    + cell(fmtZahl(r.size), 'text-align:right; color:rgba(255,255,255,.65)')
    + cell(cents(r.avg_price), 'text-align:right; color:rgba(255,255,255,.65)')
    + cell(cents(r.current_price), 'text-align:right')
    + cell(absDollars(r.value), 'text-align:right')
    + cell(dollars(r.unrealized_pnl), 'text-align:right; color:' + pnlColor(r.unrealized_pnl))
    + cell(r.end_time ? String(r.end_time).slice(0, 10) : '—', 'color:rgba(255,255,255,.55)')
    + cell(r.status === 'worthless' ? 'resolved · not redeemed' : 'open', 'color:' + (r.status === 'worthless' ? '#F5A623' : 'rgba(255,255,255,.65)')))).join('');
  const totals = '<div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(150px, 1fr)); gap:10px; margin-bottom:12px">'
    + tile('TOTAL EXPOSURE', absDollars(op.total_exposure), 'value at current prices · ' + num(op.n) + ' positions')
    + tile('COST BASIS', absDollars(op.total_cost), 'shares × average price')
    + tile('UNREALISED', dollars(op.unrealized_pnl), 'value − cost', pnlColor(op.unrealized_pnl))
    + tile('RESOLVED · NOT REDEEMED', num(op.worthless_n || 0), 'at price 0 past end date', op.worthless_n ? '#F5A623' : null)
    + '</div>';
  const count = '<div style="' + NOTE + '; margin-bottom:8px">' + num(rows.length) + ' of ' + num(op.n) + ' positions' + (op.capped ? ' · the /positions page was full — there may be more' : '') + '</div>';
  return card('OPEN POSITIONS', totals + sortBar + count + tableWith(cols, head, body, '', 900) + '<div style="' + NOTE + '; margin-top:8px">' + esc(op.note || '') + '</div>', 'as of ' + esc(op.as_of || ''));
}

function renderClosed(d) {
  const c = d.closed || null;
  if (!c || !c.n) {
    return card('CLOSED POSITIONS', '<div style="' + NOTE + '">' + esc(c && c.note ? c.note : 'No resolved positions in the closed-positions feed for this wallet.') + '</div>', c ? 'as of ' + esc(c.as_of || '') : '');
  }
  const summary = '<div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(140px, 1fr)); gap:10px; margin-bottom:12px">'
    + tile('RESOLVED', num(c.n), c.capped ? 'CAPPED — both tails at ~50' : 'complete set (both tails)', c.capped ? '#F5A623' : null)
    + tile('WON', num(c.won), 'realised PnL &gt; 0', '#C8F542')
    + tile('LOST', num(c.lost), 'realised PnL &lt; 0', '#FF4545')
    + tile('FLAT', num(c.flat), 'realised PnL = 0')
    + tile('WORTHLESS · NOT REDEEMED', num(c.worthless_not_redeemed || 0), 'still in /positions at 0', c.worthless_not_redeemed ? '#F5A623' : null)
    + tile('REALISED PNL', dollars(c.realized_pnl), 'sum over the ' + num(c.n) + ' rows', pnlColor(c.realized_pnl))
    + '</div>';
  const cols = '2.2fr 60px 70px 80px 90px 100px 70px 120px';
  const head = '<div>MARKET</div><div>SIDE</div><div style="text-align:right">ENTRY</div><div style="text-align:right">SETTLED</div><div style="text-align:right">BOUGHT</div><div style="text-align:right">REALISED</div><div>RESULT</div><div>TIME</div>';
  const body = (c.rows || []).map((r) => row(cols,
    cell(link(r.url, r.title), 'font-family:\'Inter\',sans-serif; font-size:12.5px')
    + cell(esc(r.outcome || '—'), 'color:' + (String(r.outcome).toLowerCase() === 'yes' ? '#C8F542' : '#FF7A7A'))
    + cell(cents(r.avg_price), 'text-align:right; color:rgba(255,255,255,.65)')
    + cell(cents(r.current_price), 'text-align:right; color:rgba(255,255,255,.65)')
    + cell(absDollars(r.total_bought), 'text-align:right')
    + cell(dollars(r.realized_pnl), 'text-align:right; color:' + pnlColor(r.realized_pnl))
    + cell(esc(r.result || '—'), 'color:' + (r.result === 'won' ? '#C8F542' : r.result === 'lost' ? '#FF4545' : 'rgba(255,255,255,.55)'))
    + cell(when(r.time), 'color:rgba(255,255,255,.55)'))).join('');
  const count = '<div style="' + NOTE + '; margin-bottom:8px">' + num(c.shown) + ' of ' + num(c.n) + ' resolved positions, largest |PnL| first' + (c.capped ? ' · capped: only the ~50 biggest winners and ~50 biggest losers are reachable' : '') + '</div>';
  return card('CLOSED POSITIONS', summary + count + tableWith(cols, head, body, '', 900) + '<div style="' + NOTE + '; margin-top:8px">' + esc(c.note || '') + ' Source: ' + esc(c.source || '') + '</div>', 'as of ' + esc(c.as_of || '') + (c.capped ? ' · CAPPED' : ''));
}

function renderCategoriesContext(d) {
  const cats = d.categories && Array.isArray(d.categories.rows) ? d.categories.rows : [];
  const ctx = d.context || null;
  const catDia = cats.length ? diagramm({
    titel: 'STAKE BY CATEGORY', einheit: 'USD bought (label: trades · settled PnL)',
    punkte: cats.map((c) => ({ label: c.category + ' · ' + c.trades + ' t · ' + dollars(c.pnl), wert: +(+c.stake).toFixed(0) }))
  }) : '<div style="' + NOTE + '">No trades in the activity window to put in a category.</div>';
  const groups = ctx && Array.isArray(ctx.groups) ? ctx.groups : [];
  const ctxDia = groups.length ? diagramm({
    titel: 'INSIDER-CONTEXT GROUPS · SHARE OF NOTIONAL', einheit: '% of $' + num(Math.round(ctx.notional || 0)),
    punkte: groups.map((g) => ({ label: g.group + ' · ' + g.trades + ' t', wert: +((g.share || 0) * 100).toFixed(1), art: g.insider_prone ? 'summe' : 'kosten' }))
  }) : '<div style="' + NOTE + '">No trades to classify.</div>';
  const ctxLine = ctx && ctx.insider_prone_share != null
    ? '<div style="' + NOTE + '; margin-top:8px">' + pct(ctx.insider_prone_share) + ' of traded notional sits in insider-plausible groups (politics, awards, corporate/legal, general); ' + pct(ctx.excluded_share) + ' in the groups the risk screen excludes (sports odds, weather, crypto/market prices). n ' + num(ctx.n_trades) + ' trades.</div>'
    : '';
  return '<div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(340px, 1fr)); gap:14px; margin-top:14px">'
    + '<div style="' + CARD + '; padding:16px 18px"><div style="' + LBL + '; margin-bottom:10px">CATEGORIES · ' + (d.categories ? 'as of ' + esc(d.categories.as_of || '') : '') + '</div>' + catDia + '<div style="' + NOTE + '; margin-top:8px">' + esc(d.categories ? d.categories.note + ' Classifier: ' + d.categories.classifier : '') + '</div></div>'
    + '<div style="' + CARD + '; padding:16px 18px"><div style="' + LBL + '; margin-bottom:10px">INSIDER CONTEXT · ' + (ctx ? 'as of ' + esc(ctx.as_of || '') : '') + '</div>' + ctxDia + ctxLine + '<div style="' + NOTE + '; margin-top:6px">' + esc(ctx ? ctx.note : '') + '</div></div>'
    + '</div>';
}

function renderTrades(d) {
  const a = d.activity || null;
  if (!a || !a.n_trades) {
    return card('RECENT TRADES', '<div style="' + NOTE + '">No trades in the public /activity feed for this wallet' + (a && a.n_rows ? ' (' + num(a.n_rows) + ' rows read, none of type TRADE)' : '') + '.</div>', a ? 'as of ' + esc(a.as_of || '') : '');
  }
  const summary = '<div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(140px, 1fr)); gap:10px; margin-bottom:12px">'
    + tile('TRADES READ', num(a.n_trades), num(a.n_rows) + ' activity rows · ' + num(a.n_redeems) + ' redemptions' + (a.window_truncated ? ' · WINDOW TRUNCATED' : ''), a.window_truncated ? '#F5A623' : null)
    + tile('BUY · SELL', num(a.buy_n) + ' · ' + num(a.sell_n), absDollars(a.buy_notional) + ' bought · ' + absDollars(a.sell_notional) + ' sold')
    + tile('AVG TRADE', a.avg_trade_size != null ? absDollars(a.avg_trade_size) : '—', 'notional per trade')
    + tile('TRADES / DAY', a.trades_per_day != null ? fmtZahl(a.trades_per_day) : '—', 'over ' + (a.span_days != null ? fmtZahl(a.span_days) : '—') + ' days in the window')
    + tile('NET CASH FLOW', dollars(a.net_cash_flow), 'sells + redemptions − buys · open positions not in it', pnlColor(a.net_cash_flow))
    + '</div>';
  const cols = '120px 60px 60px 70px 80px 90px 2.4fr';
  const head = '<div>TIME (UTC)</div><div>SIDE</div><div>OUTCOME</div><div style="text-align:right">PRICE</div><div style="text-align:right">SHARES</div><div style="text-align:right">NOTIONAL</div><div>MARKET</div>';
  const body = (a.trades || []).map((t) => row(cols,
    cell(when(t.time), 'color:rgba(255,255,255,.55)')
    + cell(esc(t.side || '—'), 'color:' + (t.side === 'BUY' ? '#C8F542' : '#FF4545'))
    + cell(esc(t.outcome || '—'))
    + cell(cents(t.price), 'text-align:right')
    + cell(fmtZahl(t.size), 'text-align:right; color:rgba(255,255,255,.65)')
    + cell(absDollars(t.notional), 'text-align:right')
    + cell(link(t.url, t.title), 'font-family:\'Inter\',sans-serif; font-size:12.5px'))).join('');
  const count = '<div style="' + NOTE + '; margin-bottom:8px">' + num(a.shown) + ' of ' + num(a.n_trades) + ' trades, newest first' + (a.window_truncated ? ' · the activity window was cut at the page cap, older trades are not read here' : '') + '</div>';
  return card('RECENT TRADES', summary + count + tableWith(cols, head, body, '', 900), 'as of ' + esc(a.as_of || '') + ' · ' + esc(a.source || '') + (a.window_truncated ? ' · WINDOW TRUNCATED' : ''));
}

function renderLimits(d) {
  const lim = Array.isArray(d.limits) ? d.limits : [];
  if (!lim.length) return '';
  const errs = d.errors && typeof d.errors === 'object' ? Object.entries(d.errors) : [];
  return card('LIMITS OF THIS READ',
    '<ul style="margin:0; padding-left:18px; font-size:12.5px; color:rgba(255,255,255,.6); line-height:1.65">' + lim.map((l) => '<li>' + esc(l) + '</li>').join('') + '</ul>'
    + (errs.length ? '<div style="' + NOTE + '; margin-top:10px; color:#F5A623">Parts that did not answer this time: ' + errs.map((e) => esc(e[0]) + ' (' + esc(e[1]) + ')').join(' · ') + '</div>' : ''));
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
      body = '<div style="padding:16px 24px 28px">'
        + renderIdentity(T, d)
        + renderKpis(d)
        + renderTrackRecord(d)
        + renderPnl(d)
        + renderEdge(d)
        + renderOpenPositions(T, d)
        + renderClosed(d)
        + renderCategoriesContext(d)
        + renderTrades(d)
        + renderLimits(d)
        + '</div>';
    }
  }
  return '<div>' + renderHeader(T) + body + '</div>';
}
