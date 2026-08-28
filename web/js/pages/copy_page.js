// Copy trade — the paper copy desk. Reads /api/copy; from this machine (or
// with an admin token) it also writes: follow or pause traders, change the
// sizing settings, top up a sub-account, run one sync pass. Every figure on
// the page comes from the API answer; a missing field renders as missing.
//
// The page is a pure function of (state, liveData.copy). Actions are closures
// handed to T.act(); the Terminal methods they call (copyFollow, copySetTrader,
// copySaveSettings, copySync, copyTopUp, copyReload) live in app.js.

import { esc, num, leerZeile } from '../util.js';
import { caveatZeile } from '../claims.js';
import { MONO as M, KARTE, LABEL_BLOCK } from '../ui.js';

const ACCENT = 'var(--accent)';
const POS = 'var(--pos)'; // gain green, always paired with RED
const RED = 'var(--neg)', AMBER = 'var(--warn)', BLUE = 'var(--info)';
const DIM = 'var(--ink-4)';
const INPUT = 'width:100%; box-sizing:border-box; background:var(--panel); border:1px solid var(--line-edge); border-radius:var(--r-control); padding:var(--sp-3) var(--sp-4); ' + M + '; font-size:var(--t-small); color:var(--text)';
const BTN = M + "; font-size:var(--t-micro); letter-spacing:.06em; border-radius:var(--r-control); padding:var(--sp-3) var(--sp-5); cursor:pointer; display:inline-block; user-select:none";
const BTN_PRIMARY = BTN + '; color:var(--on-accent); background:' + ACCENT + '; font-weight:600';
const BTN_GHOST = BTN + '; color:var(--ink-2); border:1px solid var(--line-1)';
const BTN_WARN = BTN + '; color:' + AMBER + '; border:1px solid rgba(var(--warn-rgb),.4)';
const BTN_OFF = BTN + '; color:var(--ink-4); border:1px solid var(--line-2); cursor:default';

export const COPY_TABS = [
  ['traders', 'Traders'], ['orders', 'Orders'], ['positions', 'Positions'], ['perf', 'Performance'],
  ['fidelity', 'Copy fidelity'], ['cash', 'Cash events'], ['settings', 'Settings']
];

function shortW(w) {
  const v = String(w || '');
  return v.length > 12 ? v.slice(0, 6) + '…' + v.slice(-4) : v;
}

// $1,234.56 with sign; the page never rounds a paper figure away.
function usd(n, digits) {
  const v = Number(n) || 0;
  const d = digits == null ? 2 : digits;
  return (v < 0 ? '-' : '') + '$' + num(Math.abs(v).toFixed(d));
}

function signedUsd(n, digits) {
  const v = Number(n) || 0;
  return (v >= 0 ? '+' : '-') + '$' + num(Math.abs(v).toFixed(digits == null ? 2 : digits));
}

function pnlColor(v) { return (Number(v) || 0) >= 0 ? POS : RED; }

// Ein Prozentwert, der auch null sein darf. Ohne eingezahltes Kapital gibt
// es keine Rendite, und die frueheren "+0.00 %" lasen sich wie eine
// gemessene Null.
function pctLabel(v) {
  if (v == null || !isFinite(Number(v))) return '—';
  const n = Number(v);
  return (n >= 0 ? '+' : '') + n.toFixed(2) + '%';
}

// Gebucht und bewertet in einer Zeile. Die Schlagzeile des Copy-Desks war
// equity minus Einzahlungen: darin steckt ein realisiertes Ergebnis (Geld,
// das eine Aufloesung zurueckgegeben hat) und eine Marke auf Positionen, die
// noch nichts entschieden haben. Ein Tisch, der gebucht 120 Dollar verloren
// hat und dessen offene Positionen 300 Dollar ueber Einstand markiert sind,
// stand als "+180, +18,00 %" da.
function splitSatz(kp) {
  if (kp == null) return '';
  return 'settled ' + signedUsd(kp.settled_pnl) + ' (' + pctLabel(kp.settled_pct) + ')'
    + ' · marked ' + signedUsd(kp.open_pnl) + ' (' + pctLabel(kp.open_pct) + ')';
}

// "12 min ago" from an ISO stamp; nothing when there is no stamp.
function ago(iso) {
  if (!iso) return '';
  const t = Date.parse(String(iso));
  if (!isFinite(t)) return String(iso);
  const sec = Math.max(0, Math.round((Date.now() - t) / 1000));
  if (sec < 90) return sec + ' s ago';
  const min = Math.round(sec / 60);
  if (min < 90) return min + ' min ago';
  const h = Math.round(min / 60);
  if (h < 36) return h + ' h ago';
  return Math.round(h / 24) + ' d ago';
}

function fmtStamp(iso) {
  if (!iso) return '—';
  const s = String(iso);
  return s.length >= 16 ? s.slice(0, 10) + ' ' + s.slice(11, 16) + ' UTC' : s;
}

function field(label, inner) {
  return '<div><div style="' + LABEL_BLOCK + '">' + label + '</div>' + inner + '</div>';
}

function textInput(T, key, value, placeholder, onInput, extraStyle) {
  return '<input value="' + esc(value == null ? '' : value) + '" ' + T.inp(onInput, key) + ' placeholder="' + esc(placeholder || '') + '" style="' + INPUT + (extraStyle ? '; ' + extraStyle : '') + '" />';
}

function button(T, label, onClick, style, title) {
  if (!onClick) return '<div style="' + (style || BTN_OFF) + '"' + (title ? ' title="' + esc(title) + '"' : '') + '>' + esc(label) + '</div>';
  return '<div ' + T.act(onClick) + ' style="' + (style || BTN_GHOST) + '"' + (title ? ' title="' + esc(title) + '"' : '') + '>' + esc(label) + '</div>';
}

// The empty state names the source; it never shows a number.
function ohneDesk(live) {
  const fehler = live && live._quelle === 'fehler' ? live._fehler : '';
  const grund = fehler
    ? '/api/copy did not answer: ' + esc(fehler) + '. The desk lives where <span style="' + M + '">api/server.py</span> runs; a static copy of the site carries no paper books.'
    : 'Waiting for /api/copy. The desk reads <span style="' + M + '">data/copy_trading.sqlite</span> through the API; until it answers there is nothing to show.';
  return '<div>'
    + '<div style="padding:var(--sp-6) var(--sp-6) var(--sp-5); border-bottom:1px solid var(--line-2)">'
    + '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:.18em; color:' + ACCENT + '">COPY TRADE · PAPER</div>'
    + '<h1 style="font-size:var(--t-head); line-height:1.25; margin:var(--sp-3) 0 0; font-weight:600; letter-spacing:-0.01em">Follow traders with fake money</h1></div>'
    + '<div style="padding:var(--sp-6)"><div style="' + KARTE + '; padding:var(--sp-6); max-width:760px">'
    + '<div style="font-size:var(--t-lead); font-weight:600">Nothing to show</div>'
    + '<div style="font-size:var(--t-body); color:' + DIM + '; margin-top:var(--sp-4); line-height:1.65">' + grund + '</div>'
    + '</div></div></div>';
}

// ---------------------------------------------------------------- traders tab

function traderRow(T, t, s, canWrite, busy) {
  const editing = s.copyEdit && s.copyEdit.wallet === t.wallet;
  const topping = s.copyTopup && s.copyTopup.wallet === t.wallet;
  const rowBusy = busy === t.wallet;
  const o = t.orders || {};
  const spark = t.equity_curve && t.equity_curve.length > 1
    ? '<svg width="90" height="26" viewBox="0 0 90 26" preserveAspectRatio="none" aria-hidden="true" focusable="false"><polyline points="' + T.seriesPoints(t.equity_curve, 90, 26) + '" fill="none" style="stroke:' + pnlColor(t.pnl) + '" stroke-width="1.5" /></svg>'
    : '<span style="' + M + '; font-size:var(--t-micro); color:var(--ink-4)" title="one point per daemon pass, once a minute">' + (t.equity_curve && t.equity_curve.length === 1 ? '1 point' : 'no curve yet') + '</span>';
  const state = t.active
    ? '<span style="' + M + '; font-size:var(--t-micro); letter-spacing:.1em; color:' + ACCENT + '; border:1px solid rgba(var(--accent-rgb),.35); border-radius:var(--r-control); padding:var(--sp-1) var(--sp-3)">ACTIVE</span>'
    : '<span style="' + M + '; font-size:var(--t-micro); letter-spacing:.1em; color:' + AMBER + '; border:1px solid rgba(var(--warn-rgb),.35); border-radius:var(--r-control); padding:var(--sp-1) var(--sp-3)">PAUSED</span>';
  const seeded = t.seeded_at
    ? '<span title="baseline seeded ' + esc(fmtStamp(t.seeded_at)) + ' — trades before it are observed, not copied" style="color:var(--ink-3)">baseline ' + esc(ago(t.seeded_at)) + '</span>'
    : '<span title="no baseline yet: the first daemon pass mirrors the wallet\'s positions and sets the cutoff" style="color:' + AMBER + '">not seeded yet</span>';
  // The book seed: the sub-account bought the source's open positions at
  // follow time (scaled), so its exits can be mirrored. Books from before
  // that existed are backfilled by the daemon within a pass.
  const bookSeed = t.paper_seeded_at
    ? '<span title="the source\'s open book was bought into this sub-account ' + esc(fmtStamp(t.paper_seeded_at)) + ', scaled like every order — its sells and redeems can be mirrored" style="color:var(--ink-3)">book seeded</span>'
    : '<span title="this sub-account is still 100% cash: the daemon buys the source\'s open book on its next pass" style="color:' + AMBER + '">book not seeded yet</span>';
  // A dead source produces zeros forever — say it instead of showing them.
  const idleMs = t.source_last_trade_at ? Date.now() - Date.parse(String(t.source_last_trade_at)) : null;
  const idle = idleMs != null && isFinite(idleMs) && idleMs > 14 * 86400000
    ? '<span title="newest print of the source wallet the engine has seen — a wallet that stopped trading will never produce a copy" style="color:' + AMBER + '">source idle since ' + esc(String(t.source_last_trade_at).slice(0, 10)) + '</span>'
    : '';
  const actions = !canWrite ? ''
    : rowBusy ? '<span style="' + M + '; font-size:var(--t-micro); color:' + DIM + '">working…</span>'
      : (t.active
        ? button(T, 'Pause', () => T.copySetTrader(t.wallet, { active: false }), BTN_WARN, 'stop copying this wallet; positions and history stay')
        : button(T, 'Resume', () => T.copySetTrader(t.wallet, { active: true }), BTN_PRIMARY, 're-seed the baseline and copy from now on'))
        + ' ' + button(T, editing ? 'Close' : 'Edit', () => T.setState({ copyEdit: editing ? null : { wallet: t.wallet, label: t.label || '', note: t.note || '' }, copyTopup: null }), BTN_GHOST, 'label and note')
        + ' ' + button(T, topping ? 'Close' : 'Top up', () => T.setState({ copyTopup: topping ? null : { wallet: t.wallet, amount: '500' }, copyEdit: null }), BTN_GHOST, 'add paper cash to this sub-account (counts as put in, not profit)');
  const grid = 'display:grid; grid-template-columns:minmax(180px,1.6fr) 74px 90px 90px 110px 96px 70px 96px 92px minmax(200px,1.4fr); gap:var(--sp-4); align-items:center; padding:var(--sp-4) var(--sp-5); border-bottom:1px solid var(--line-3)';
  let html = '<div style="' + grid + '">'
    + '<div><div style="font-size:var(--t-body); font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis">' + esc(t.label || shortW(t.wallet)) + '</div>'
    + '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-3); margin-top:var(--sp-1); display:flex; gap:var(--sp-3); align-items:center; flex-wrap:wrap">'
    + '<span ' + T.act(() => T.analyseWallet(t.wallet)) + ' class="hv-accent" title="open the wallet page" style="cursor:pointer; text-decoration:underline dotted">' + esc(shortW(t.wallet)) + '</span>'
    + (t.profile_url ? '<a href="' + esc(t.profile_url) + '" target="_blank" rel="noopener" style="color:' + BLUE + '">Polymarket ↗</a>' : '')
    + seeded + bookSeed + idle + '</div>'
    + (t.note ? '<div style="font-size:var(--t-small); color:var(--ink-4); margin-top:var(--sp-2); white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="' + esc(t.note) + '">' + esc(t.note) + '</div>' : '')
    // His account size as the sizing refresh last saw it, and the neutral
    // ratio (your equity ÷ his) — the number "same share of account" uses.
    + (t.source_equity != null
      ? '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-3); margin-top:var(--sp-2)">his equity ' + esc(usd(t.source_equity, 0)) + (t.neutral_ratio != null ? ' · ratio ' + esc((Number(t.neutral_ratio) * 100).toFixed(3)) + ' %' : '') + '</div>'
      : (t.active ? '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-4); margin-top:var(--sp-2)">his equity not read yet</div>' : ''))
    + '</div>'
    + '<div>' + state + '</div>'
    + '<div style="' + M + '; font-size:var(--t-small); text-align:right; color:' + DIM + '">' + usd(t.start_cash, 0) + '</div>'
    + '<div style="' + M + '; font-size:var(--t-small); text-align:right">' + usd(t.cash) + '</div>'
    + '<div style="' + M + '; font-size:var(--t-small); text-align:right">' + usd(t.equity) + '<div style="font-size:var(--t-micro); color:var(--ink-3)">' + usd(t.contributions, 0) + ' put in</div></div>'
    // Gebucht und bewertet stehen nebeneinander. Eine Prozentzahl, die
    // beides addiert, laesst einen Tisch, der gebucht im Minus steht, als
    // Gewinner dastehen; beide Haelften teilen sich den Nenner (das in
    // diesen Sub-Account eingezahlte Kapital) und addieren sich deshalb.
    + '<div style="' + M + '; font-size:var(--t-small); text-align:right; color:' + pnlColor(t.pnl) + '" title="' + esc(splitSatz(t)) + '">' + signedUsd(t.pnl)
    + '<div style="font-size:var(--t-micro)">' + esc(pctLabel(t.pnl_pct)) + '</div>'
    + '<div style="font-size:var(--t-micro); color:var(--ink-4)">settled ' + esc(pctLabel(t.settled_pct)) + ' · marked ' + esc(pctLabel(t.open_pct)) + '</div>'
    + (t.pnl_reconciles === false ? '<div style="font-size:var(--t-micro); color:' + AMBER + '">books do not add up</div>' : '')
    + '</div>'
    + '<div style="' + M + '; font-size:var(--t-small); text-align:right" title="copied / skipped (observed baseline trades not counted)">' + (o.copied || 0) + ' <span style="color:' + AMBER + '">/ ' + (o.skipped || 0) + '</span></div>'
    + '<div style="' + M + '; font-size:var(--t-small); text-align:right">' + (t.open_positions || 0) + '<div style="font-size:var(--t-micro); color:var(--ink-3)">' + (t.last_copy_at ? 'last ' + esc(ago(t.last_copy_at)) : 'no copy yet') + '</div></div>'
    + '<div style="text-align:right">' + spark + '</div>'
    + '<div style="display:flex; gap:var(--sp-3); justify-content:flex-end; flex-wrap:wrap">' + actions + '</div>'
    + '</div>';
  if (editing && canWrite) {
    const e = s.copyEdit;
    html += '<div style="display:grid; grid-template-columns:1fr 2fr auto; gap:var(--sp-4); align-items:end; padding:var(--sp-4) var(--sp-5) var(--sp-5); background:rgba(var(--ink),.02); border-bottom:1px solid var(--line-3)">'
      + field('LABEL', textInput(T, 'copyEditLabel', e.label, 'display name', (ev) => { T.state.copyEdit.label = ev.target.value; }))
      + field('NOTE — domain, cadence, why you follow', textInput(T, 'copyEditNote', e.note, 'e.g. geopolitics desk, a few trades a week', (ev) => { T.state.copyEdit.note = ev.target.value; }))
      + button(T, 'Save', () => T.copySetTrader(t.wallet, { label: T.state.copyEdit.label, note: T.state.copyEdit.note }), BTN_PRIMARY)
      + '</div>';
  }
  if (topping && canWrite) {
    html += '<div style="display:grid; grid-template-columns:160px auto 1fr; gap:var(--sp-4); align-items:end; padding:var(--sp-4) var(--sp-5) var(--sp-5); background:rgba(var(--ink),.02); border-bottom:1px solid var(--line-3)">'
      + field('TOP UP $', textInput(T, 'copyTopupAmount', s.copyTopup.amount, '500', (ev) => { T.state.copyTopup.amount = ev.target.value; }))
      + button(T, 'Add paper cash', () => T.copyTopUp(t.wallet), BTN_PRIMARY)
      + '<div style="font-size:var(--t-small); color:var(--ink-3); line-height:1.5">Booked as a cash event and counted as put in, so it can never read as profit. Off by default for the daemon (auto top-up).</div>'
      + '</div>';
  }
  return html;
}

function followForm(T, s, live, canWrite) {
  const f = s.copyForm || { wallet: '', label: '', cash: '1000', note: '' };
  const busy = s.copyBusy === 'follow';
  const access = live.write_access || {};
  if (!canWrite) {
    const tokenBox = access.mode === 'token'
      ? '<div style="display:grid; grid-template-columns:1fr auto; gap:var(--sp-4); align-items:end; margin-top:var(--sp-4); max-width:520px">'
        + field('ADMIN TOKEN (X-Admin-Token, stored in this browser only)', textInput(T, 'copyToken', s.copyToken || '', 'paste COPY_ADMIN_TOKEN', (ev) => { T.state.copyToken = ev.target.value; }))
        + button(T, 'Use token', () => T.copySetToken(T.state.copyToken), BTN_PRIMARY)
        + '</div>'
      : '';
    return '<div style="' + KARTE + '; padding:var(--sp-5); margin:var(--sp-5) var(--sp-6) 0">'
      + '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:.14em; color:' + AMBER + '">READ-ONLY FROM HERE</div>'
      + '<div style="font-size:var(--t-body); color:' + DIM + '; margin-top:var(--sp-3); line-height:1.6">' + esc(access.reason || 'This copy of the site cannot write to the desk.')
      + (access.mode === 'locked' ? ' Open the site on the machine that runs api/server.py, or set <span style="' + M + '">COPY_ADMIN_TOKEN</span> there and paste it here.' : '') + '</div>'
      + tokenBox + '</div>';
  }
  return '<div style="' + KARTE + '; padding:var(--sp-5); margin:var(--sp-5) var(--sp-6) 0">'
    + '<div style="display:flex; justify-content:space-between; align-items:baseline; gap:var(--sp-4); flex-wrap:wrap">'
    + '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:.14em; color:' + ACCENT + '">FOLLOW A WALLET</div>'
    + '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-3)">' + esc(access.mode === 'token' ? 'writes with admin token' : 'writes allowed: local request') + '</div></div>'
    + '<div style="display:grid; grid-template-columns:2.2fr 1.2fr 0.8fr 2fr auto; gap:var(--sp-4); align-items:end; margin-top:var(--sp-4)">'
    + field('POLYMARKET WALLET · 0x… / profile URL / exact handle', textInput(T, 'copyFormWallet', f.wallet, '0x… or swisstony', (ev) => { T.state.copyForm.wallet = ev.target.value; }))
    + field('LABEL', textInput(T, 'copyFormLabel', f.label, 'e.g. Geo desk', (ev) => { T.state.copyForm.label = ev.target.value; }))
    + field('START CASH $', textInput(T, 'copyFormCash', f.cash, '1000', (ev) => { T.state.copyForm.cash = ev.target.value; }))
    + field('NOTE — domain, cadence, thesis', textInput(T, 'copyFormNote', f.note, 'e.g. elections only, ~5 trades/week', (ev) => { T.state.copyForm.note = ev.target.value; }))
    + (busy ? '<div style="' + BTN_OFF + '">following…</div>' : button(T, 'Follow wallet', () => T.copyFollow(), BTN_PRIMARY, 'opens a sub-account with this start cash and seeds the baseline now'))
    + '</div>'
    + '<div style="font-size:var(--t-small); color:var(--ink-3); margin-top:var(--sp-4); line-height:1.55">'
    + 'On follow the wallet\'s open positions are mirrored and its recent trades recorded as <span style="' + M + '">observed</span>; only what it does from that moment on is copied, into its own sub-account with the same settings as every other trader. Equal start cash keeps the traders comparable.'
    + '</div>'
    + '</div>';
}

function daemonBlock(T, live, canWrite, s) {
  const d = live.daemon || {};
  const sync = live.sync || {};
  const running = d.running === true ? true : d.running === false ? false : null;
  const farbe = running === true ? POS : running === false ? AMBER : 'var(--ink-3)';
  const text = running === true ? 'DAEMON RUNNING' : running === false ? 'DAEMON STOPPED' : 'DAEMON NEVER RAN HERE';
  const facts = [];
  if (d.mode) facts.push('mode ' + esc(d.mode));
  if (d.ws_connected != null) facts.push('websocket ' + (d.ws_connected ? 'connected' : 'not connected'));
  if (d.last_sync_at) facts.push('last pass ' + esc(ago(d.last_sync_at)));
  if (d.pid) facts.push('pid ' + esc(String(d.pid)));
  if (d.in_process) facts.push('inside the API process');
  if (d.last_error) facts.push('<span style="color:' + RED + '">' + esc(String(d.last_error)) + '</span>');
  const syncBusy = s.copyBusy === 'sync' || sync.running === true;
  let syncLine = '';
  if (sync.running) syncLine = 'sync pass running since ' + esc(ago(sync.started_at)) + '…';
  else if (sync.error) syncLine = '<span style="color:' + RED + '">last pass failed: ' + esc(sync.error) + '</span>';
  else if (sync.result && sync.result.api) {
    const a = sync.result.api, st = sync.result.settlement || {};
    syncLine = 'last pass ' + esc(ago(sync.finished_at)) + ': ' + a.wallets + ' wallet(s), ' + a.copied + ' copied, ' + a.skipped + ' skipped, ' + a.duplicates + ' already known'
      + (st.copied ? ', ' + st.copied + ' settlement(s)' : '') + (a.errors && a.errors.length ? ' — <span style="color:' + RED + '">' + esc(a.errors[0]) + '</span>' : '');
  }
  return '<div style="' + KARTE + '; padding:var(--sp-5); margin:var(--sp-5) var(--sp-6) 0">'
    + '<div style="display:flex; align-items:center; gap:var(--sp-4); flex-wrap:wrap">'
    + '<span style="width:7px; height:7px; border-radius:50%; background:' + farbe + '; display:inline-block"></span>'
    + '<span style="' + M + '; font-size:var(--t-micro); letter-spacing:.14em; color:' + farbe + '">' + text + '</span>'
    + '<span style="' + M + '; font-size:var(--t-micro); color:var(--ink-3)">' + facts.join(' · ') + '</span>'
    + '<span style="flex:1"></span>'
    + (canWrite ? (syncBusy ? '<div style="' + BTN_OFF + '">sync running…</div>' : button(T, 'Run one sync pass', () => T.copySync(), BTN_GHOST, 'one API + settlement pass over the active traders, in the background')) : '')
    + '</div>'
    + (d.reason ? '<div style="font-size:var(--t-small); color:' + DIM + '; margin-top:var(--sp-3)">' + esc(d.reason) + '</div>' : '')
    + (syncLine ? '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-3); margin-top:var(--sp-3)">' + syncLine + '</div>' : '')
    + '<div style="font-size:var(--t-small); color:var(--ink-3); margin-top:var(--sp-4); line-height:1.6">'
    + 'The daemon copies continuously (WebSocket + API, settlements every 90 s) and reads the traders and settings from this desk on every pass. '
    + (d.in_process
      ? 'Here it runs inside the API process (COPY_DAEMON=1) and restarts with it; the books sit on the host\'s volume. '
      : 'Start it in a terminal from the repo root: <span style="' + M + '; color:var(--ink-2)">.venv\\Scripts\\python.exe scripts\\run_copy_trader.py</span> '
        + '(or <span style="' + M + '; color:var(--ink-2)">scripts\\start_paper_desk.ps1</span>, which starts API and daemon together). ')
    + 'A sync pass from here books the same trades, just once, at up to 30 s latency.'
    + '</div></div>';
}

function tradersTab(T, s, live, canWrite) {
  const traders = live.traders || [];
  const busy = s.copyBusy;
  const head = 'display:grid; grid-template-columns:minmax(180px,1.6fr) 74px 90px 90px 110px 96px 70px 96px 92px minmax(200px,1.4fr); gap:var(--sp-4); padding:var(--sp-3) var(--sp-5); background:var(--panel); border-bottom:1px solid var(--line-2); ' + M + '; font-size:var(--t-micro); letter-spacing:.12em; color:var(--ink-3)';
  return followForm(T, s, live, canWrite)
    + '<div style="border:1px solid var(--line-2); border-radius:var(--r-panel); margin:var(--sp-5) var(--sp-6) 0; overflow:hidden">'
    + '<div style="overflow-x:auto"><div style="min-width:1180px">'
    + '<div style="' + head + '">'
    + '<div>TRADER</div><div>STATE</div><div style="text-align:right">START</div><div style="text-align:right">CASH</div><div style="text-align:right">EQUITY</div><div style="text-align:right">PAPER PNL · SETTLED / MARKED</div><div style="text-align:right">COPIED / SKIP</div><div style="text-align:right">OPEN</div><div style="text-align:right">EQUITY CURVE</div><div style="text-align:right">' + (canWrite ? 'ACTIONS' : '') + '</div></div>'
    + (traders.length ? traders.map((t) => traderRow(T, t, s, canWrite, busy)).join('') : leerZeile('No traders followed yet. Add the first wallet above — each one gets its own sub-account.'))
    + '</div></div></div>'
    + daemonBlock(T, live, canWrite, s);
}

// ---------------------------------------------------------------- settings tab

// The sizing mode is a reading of three CopySettings fields, and choosing
// one writes them: "same share" = dynamic sizing on (order = his notional x
// your equity / his equity x multiplier); "fixed %" = dynamic off, copy_scale
// < 1; "dollar for dollar" = dynamic off, copy_scale = 1. Nothing else on the
// engine changes — the mode is how the page talks about those fields.
export function sizingModeOf(f) {
  if (f && f.dynamic_sizing_enabled) return 'share';
  return Number(f && f.copy_scale) === 1 ? 'one' : 'fixed';
}

function pctInputValue(fraction) {
  const v = Number(fraction);
  if (!isFinite(v)) return '';
  const p = v * 100;
  return String(Math.round(p * 10000) / 10000);
}

// One line per active trader: what a $1,000 source bet becomes under the
// current mode, from the source equity the sizing refresh last saw. No
// source equity yet -> says so instead of a made-up ratio.
function sizingExampleRows(traders, f, mode) {
  const rows = (traders || []).filter((t) => t.active);
  if (!rows.length) return '<div style="font-size:var(--t-small); color:var(--ink-3)">No active trader yet — follow one and the example fills in with its equity.</div>';
  const mult = Number(f.dynamic_sizing_multiplier) || 0;
  const cap = Number(f.max_order_equity_pct) || 0;
  const scaleMax = Number(f.dynamic_scale_max) || 0;
  const fixed = Number(f.copy_scale) || 0;
  return rows.map((t) => {
    const eq = Number(t.equity) || 0;
    const src = t.source_equity == null ? null : Number(t.source_equity);
    let text;
    if (mode === 'share') {
      if (!src || !(src > 0) || !(eq > 0)) {
        text = 'source equity not read yet (the daemon reads it on its first pass) — no ratio to show';
      } else {
        const ratio = eq / src * (mult || 1);
        const bet = 1000;
        let mine = bet * ratio;
        const clipped = [];
        if (scaleMax > 0 && ratio > scaleMax) { mine = bet * scaleMax; clipped.push('max ' + pctInputValue(scaleMax) + ' % of his trade'); }
        if (cap > 0 && mine > eq * cap) { mine = eq * cap; clipped.push('order cap ' + pctInputValue(cap) + ' % of your equity'); }
        text = 'his equity ' + usd(src, 0) + ' · your sub-account ' + usd(eq, 0) + ' → ratio ' + (ratio * 100).toFixed(3) + ' %: his $1,000 bet (' + (bet / src * 100).toFixed(2) + ' % of his account) = ' + usd(mine, 2) + ' here (' + (eq > 0 ? (mine / eq * 100).toFixed(2) : '—') + ' % of yours)'
          + (clipped.length ? ' — clipped by ' + clipped.join(' and ') : '');
      }
    } else if (mode === 'fixed') {
      let mine = 1000 * fixed;
      const clipped = cap > 0 && eq > 0 && mine > eq * cap ? ' — clipped to ' + usd(eq * cap, 2) + ' by the order cap' : '';
      text = 'his $1,000 bet → ' + usd(mine, 2) + ' here (' + pctInputValue(fixed) + ' % of his trade, whatever his account size)' + clipped;
    } else {
      const clipped = eq > 0 && cap > 0 ? ' — the order cap (' + pctInputValue(cap) + ' % of ' + usd(eq, 0) + ' = ' + usd(eq * cap, 2) + ') and the cash throttle will clip most of it' : '';
      text = 'his $1,000 bet → $1,000 here, dollar for dollar' + clipped;
    }
    return '<div style="font-size:var(--t-small); line-height:1.5; color:var(--ink-2)"><span style="' + M + '; color:var(--ink-1)">' + esc(t.label || shortW(t.wallet)) + '</span> — ' + text + '</div>';
  }).join('');
}

function settingsTab(T, s, live, canWrite) {
  const saved = live.settings || {};
  const f = s.copySettings || saved;
  const dirty = !!s.copySettings;
  const busy = s.copyBusy === 'settings';
  const patch = (changes) => { const next = Object.assign({}, T.state.copySettings || saved, changes); T.setState({ copySettings: next }); };
  const set = (key) => (ev) => { const next = Object.assign({}, T.state.copySettings || saved); next[key] = ev.target.value; T.state.copySettings = next; };
  // Percent fields: the input shows 5 for a stored 0.05 and writes 0.05 back.
  const setPct = (key) => (ev) => { const next = Object.assign({}, T.state.copySettings || saved); const v = parseFloat(String(ev.target.value).replace(',', '.')); next[key] = isFinite(v) ? String(v / 100) : ev.target.value; T.state.copySettings = next; };
  const flip = (key) => () => { const next = Object.assign({}, T.state.copySettings || saved); next[key] = !next[key]; T.setState({ copySettings: next }); };
  const hintHtml = (hint) => (hint ? '<div style="font-size:var(--t-micro); color:var(--ink-3); margin-top:var(--sp-2); line-height:1.45">' + hint + '</div>' : '');
  const numField = (key, label, hint) => field(label, textInput(T, 'copySet_' + key, f[key], '', set(key)) + hintHtml(hint));
  const pctField = (key, label, hint) => field(label, textInput(T, 'copySetPct_' + key, pctInputValue(f[key]), '', setPct(key)) + hintHtml(hint));
  const boolField = (key, label, hint) => '<div><div style="' + LABEL_BLOCK + '">' + label + '</div><div style="display:flex; align-items:center; gap:var(--sp-4); padding:var(--sp-3) 0">' + T.toggle(!!f[key], canWrite ? flip(key) : () => {}, label, !canWrite) + '<span style="' + M + '; font-size:var(--t-micro); color:' + DIM + '">' + (f[key] ? 'on' : 'off') + '</span></div>' + hintHtml(hint) + '</div>';
  const mode = sizingModeOf(f);
  const chooseMode = (m) => () => {
    if (!canWrite) return;
    if (m === 'share') patch({ dynamic_sizing_enabled: true });
    else if (m === 'one') patch({ dynamic_sizing_enabled: false, copy_scale: '1' });
    else patch({ dynamic_sizing_enabled: false, copy_scale: Number(f.copy_scale) === 1 || !(Number(f.copy_scale) > 0) ? '0.01' : f.copy_scale });
  };
  const modeCard = (m, title, line) => {
    const on = mode === m;
    return '<div ' + T.act(chooseMode(m)) + ' style="flex:1; min-width:200px; border:1px solid ' + (on ? ACCENT : 'var(--line-1)') + '; background:' + (on ? 'rgba(var(--accent-rgb),.08)' : 'transparent') + '; border-radius:var(--r-panel); padding:var(--sp-4) var(--sp-5); cursor:' + (canWrite ? 'pointer' : 'default') + '">'
      + '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:.12em; color:' + (on ? ACCENT : 'var(--ink-2)') + '">' + (on ? '● ' : '○ ') + title + '</div>'
      + '<div style="font-size:var(--t-small); color:var(--ink-4); margin-top:var(--sp-3); line-height:1.45">' + line + '</div></div>';
  };
  const grid = 'display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:var(--sp-5) var(--sp-6)';
  const modeFields = mode === 'share'
    ? numField('dynamic_sizing_multiplier', 'MULTIPLIER', '1 = exactly his share of account. 0.5 = half his share, 2 = double.')
      + pctField('dynamic_scale_max', 'MAX % OF HIS TRADE (0 = uncapped)', 'A hard lid on the ratio. A small account following a big one is well below it anyway; a big account following a small one gets clipped here.')
      + boolField('dynamic_order_cap_from_tony', 'LET THE ORDER CAP FOLLOW HIS LARGEST POSITION', 'A source that puts 20 % into one market gets a 20 % per-order cap here too, so his conviction bets are not clipped by the base cap below.')
    : mode === 'fixed'
      ? pctField('copy_scale', '% OF HIS TRADE', 'Every order is this share of what he moved. 1 = his $1,000 becomes $10 here, regardless of either account size.')
      : '<div style="font-size:var(--t-small); color:var(--ink-4); line-height:1.5; grid-column:span 2">Every order is booked at his notional. Only sensible when your sub-account is about the size of his — otherwise the order cap and the cash throttle below clip almost every trade and the copy stops resembling him.</div>';
  return '<div style="padding:var(--sp-5) var(--sp-6)">'
    + '<div style="' + KARTE + '; padding:var(--sp-5) var(--sp-6)">'
    + '<div style="display:flex; justify-content:space-between; align-items:baseline; gap:var(--sp-4); flex-wrap:wrap; margin-bottom:var(--sp-4)">'
    + '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:.14em; color:var(--ink-4)">SIZING MODE — THE SAME FOR EVERY TRADER</div>'
    + '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-3)">saved in copy_settings.json · the daemon reads it on every pass · live trading stays off</div></div>'
    + '<div style="display:flex; gap:var(--sp-4); flex-wrap:wrap; margin-bottom:var(--sp-5)">'
    + modeCard('share', 'SAME SHARE OF ACCOUNT', 'He bets $1,000 = 1 % of his account → you bet 1 % of your sub-account. Order = his notional × (your equity ÷ his equity) × multiplier. The faithful scaled mirror.')
    + modeCard('fixed', 'FIXED % OF HIS TRADE', 'Every order is a fixed fraction of what he moved, e.g. 1 %. Simple, but ignores how big the bet was for him.')
    + modeCard('one', 'DOLLAR FOR DOLLAR', 'He bets $1,000 → you bet $1,000. 1:1 on notional; only makes sense with a sub-account about his size.')
    + '</div>'
    + '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:.14em; color:var(--ink-3); margin-bottom:var(--sp-3)">WHAT A $1,000 BET OF HIS BECOMES HERE, PER ACTIVE TRADER</div>'
    + '<div style="display:flex; flex-direction:column; gap:var(--sp-2); margin-bottom:var(--sp-5); padding:var(--sp-4); border:1px solid var(--line-2); border-radius:var(--r-control)">' + sizingExampleRows(live.traders, f, mode) + '</div>'
    + '<div style="' + grid + '">'
    + modeFields
    + '</div>'
    + '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:.14em; color:var(--ink-3); margin:var(--sp-6) 0 var(--sp-4)">LIMITS AND CASH — APPLY IN EVERY MODE</div>'
    + '<div style="' + grid + '">'
    + pctField('max_order_equity_pct', 'MAX PER ORDER · % OF YOUR EQUITY', 'Cap per order. 5 = at most 5 % of the sub-account in one order.')
    + pctField('cash_throttle_pct', 'CASH THROTTLE · % OF REMAINING CASH', 'One order may spend at most this share of the cash left; 25 keeps a drought from starving later trades. 0 = off.')
    + numField('min_copy_notional', 'MIN COPY NOTIONAL $', 'Orders below this are skipped as dust.')
    + numField('trade_limit', 'TRADES PER API POLL', 'How many recent source trades each pass inspects (250 covers a busy hour).')
    + boolField('auto_top_up_enabled', 'AUTO TOP-UP', 'Off by default: a sub-account out of cash skips buys visibly until settlements recycle cash. On prints paper money — it distorts the comparison.')
    + numField('auto_top_up_amount', 'AUTO TOP-UP AMOUNT $', '')
    + numField('auto_top_up_threshold', 'AUTO TOP-UP BELOW $', '')
    + '</div>'
    + '<div style="display:flex; gap:var(--sp-4); align-items:center; margin-top:var(--sp-5); flex-wrap:wrap">'
    + (canWrite
      ? (busy ? '<div style="' + BTN_OFF + '">saving…</div>' : button(T, 'Save settings', () => T.copySaveSettings(), dirty ? BTN_PRIMARY : BTN_GHOST))
        + (dirty ? button(T, 'Discard changes', () => T.setState({ copySettings: null }), BTN_GHOST) : '')
      : '<span style="' + M + '; font-size:var(--t-micro); color:' + AMBER + '">read-only from here</span>')
    + '<span style="' + M + '; font-size:var(--t-micro); color:var(--ink-3)">mode now: ' + (mode === 'share' ? 'same share of account × ' + esc(String(f.dynamic_sizing_multiplier)) : mode === 'one' ? 'dollar for dollar' : 'fixed ' + esc(pctInputValue(f.copy_scale)) + ' % of his trade') + (dirty ? ' · unsaved changes' : '') + '</span>'
    + '</div></div></div>';
}

// ---------------------------------------------------------------- the page

export function renderCopy(T) {
  const s = T.state;
  const live = T.liveData.copy;
  const st = live && live.status ? live.status : null;
  const kp = live && live.kpis ? live.kpis : null;
  if (!st || !kp) return ohneDesk(live);

  const traders = live.traders || [];
  const canWrite = !!(live.write_access && live.write_access.allowed);
  const filter = s.copyTrader || 'all';
  const labelOf = {};
  traders.forEach((t) => { labelOf[t.wallet] = t.label || shortW(t.wallet); });
  const orders = (live.orders || []).filter((o) => filter === 'all' || String(o.wallet || '').toLowerCase() === filter);
  const positions = (live.positions || []).filter((r) => filter === 'all' || String(r[7] || '').toLowerCase() === filter);
  const cashRows = (live.cash_events || []).filter((r) => filter === 'all' || String(r[4] || '').toLowerCase() === filter);
  const filtered = traders.find((t) => t.wallet === filter) || null;
  const equityCurve = filtered ? (filtered.equity_curve || []) : (live.equity_curve || []);
  const equityPts = equityCurve.length > 1 ? T.seriesPoints(equityCurve, 900, 240) : '';
  const firstActive = traders.find((t) => t.active) || null;
  const showSource = live.source_curve && live.source_curve.length > 1 && (filter === 'all' || (firstActive && firstActive.wallet === filter));
  const srcPts = showSource ? T.seriesPoints(live.source_curve, 900, 200) : '';
  const minePts = equityCurve.length > 1 ? T.seriesPoints(equityCurve, 900, 200) : '';
  const tab = s.copyTab || 'traders';

  const copyTabs = COPY_TABS.map((o) => T.tab(o[1], tab === o[0], { copyTab: o[0] })).join('');
  const traderChips = (tab === 'orders' || tab === 'positions' || tab === 'perf' || tab === 'cash') && traders.length > 1
    ? '<div style="display:flex; gap:var(--sp-3); padding:var(--sp-4) var(--sp-6) 0; flex-wrap:wrap; align-items:center"><span style="' + LABEL_BLOCK + '; margin:0 var(--sp-2) 0 0">TRADER</span>'
      + T.opt('All', filter === 'all', { copyTrader: 'all' })
      + traders.map((t) => T.opt(t.label || shortW(t.wallet), filter === t.wallet, { copyTrader: t.wallet })).join('')
      + '</div>'
    : '';

  let body = '';
  if (tab === 'traders') {
    body = tradersTab(T, s, live, canWrite);
  } else if (tab === 'settings') {
    body = settingsTab(T, s, live, canWrite);
  } else if (tab === 'orders') {
    // What a row IS comes from the API (kind + explain): a MERGE is both
    // sides handed back for cash, not a bet on the outcome printed next to
    // it; a REDEEM / RESOLUTION is the market settling. The book line is the
    // engine's mirror of the source wallet's holdings in that market now.
    const kindOf = (o) => String(o.kind || (o.side || '').split(' ')[0] || '').toUpperCase();
    const rows = orders.filter((o) => {
      if (s.copyStatus2 !== 'all' && o.status !== s.copyStatus2) return false;
      const k = kindOf(o);
      if (s.copySide === 'SETTLE' ? !(k === 'MERGE' || k === 'REDEEM' || k === 'RESOLUTION' || k === 'SPLIT' || k === 'CONVERT') : (s.copySide !== 'all' && k !== s.copySide)) return false;
      if (s.copyMin !== 'all' && Number(String(o.theirs).replace(/[^0-9.-]/g, '')) < Number(s.copyMin)) return false;
      if (s.copyQuery.trim() && o.market.toLowerCase().indexOf(s.copyQuery.trim().toLowerCase()) < 0) return false;
      return true;
    });
    const grid = 'display:grid; grid-template-columns:92px 120px 1fr 118px 96px 96px 120px; gap:var(--sp-4)';
    const kindStyle = (k) => k === 'BUY' ? POS : k === 'SELL' ? RED : k === 'MERGE' ? AMBER : k === 'REDEEM' || k === 'RESOLUTION' ? BLUE : 'var(--ink-3)';
    body = '<div>'
      + '<div style="padding:var(--sp-5) var(--sp-6) 0; display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:var(--sp-5)">'
      + '<div><div style="' + LABEL_BLOCK + '">SEARCH</div><input value="' + esc(s.copyQuery) + '" ' + T.inp((e) => T.setState({ copyQuery: e.target.value }), 'copyQuery') + ' aria-label="Search the copy desk by market" placeholder="market…" style="' + INPUT + '" /></div>'
      + '<div><div style="' + LABEL_BLOCK + '">KIND</div><div style="display:flex; gap:var(--sp-3); flex-wrap:wrap">'
      + [['all', 'All'], ['BUY', 'Buys'], ['SELL', 'Sells'], ['MERGE', 'Merges'], ['SETTLE', 'Merges + settlements']].map((o) => T.opt(o[1], s.copySide === o[0], { copySide: o[0] })).join('') + '</div></div>'
      + '<div><div style="' + LABEL_BLOCK + '">STATUS</div><div style="display:flex; gap:var(--sp-3); flex-wrap:wrap">'
      + [['all', 'All'], ['copied', 'Copied'], ['settled', 'Settled'], ['seed_observed', 'Baseline'], ['skipped', 'Skipped']].map((o) => T.opt(o[1], s.copyStatus2 === o[0], { copyStatus2: o[0] })).join('') + '</div></div>'
      + '<div><div style="' + LABEL_BLOCK + '">MINIMUM SIZE THEY TRADED</div><div style="display:flex; gap:var(--sp-3); flex-wrap:wrap">'
      + [['all', 'Any'], ['1000', '>$1k'], ['5000', '>$5k'], ['10000', '>$10k']].map((o) => T.opt(o[1], s.copyMin === o[0], { copyMin: o[0] })).join('') + '</div></div>'
      + '</div>'
      + '<div style="padding:var(--sp-4) var(--sp-6) 0; font-size:var(--t-small); color:var(--ink-3); line-height:1.5">'
      + '<span style="' + M + '; color:' + POS + '">BUY</span> / <span style="' + M + '; color:' + RED + '">SELL</span> are the source\'s trades, scaled into the sub-account. '
      + '<span style="' + M + '; color:' + AMBER + '">MERGE</span> = the source handed equal YES + NO shares back for $1 each — closes both sides, no direction. '
      + '<span style="' + M + '; color:' + BLUE + '">REDEEM / RESOLUTION</span> = the market settled. Every row says what it was and what the source holds in that market now.'
      + '</div>'
      + '<div style="border:1px solid var(--line-2); border-radius:var(--r-panel); margin:var(--sp-5) var(--sp-6); overflow:hidden">'
      + '<div style="' + grid + '; padding:var(--sp-3) var(--sp-5); background:var(--panel); border-bottom:1px solid var(--line-2); ' + M + '; font-size:var(--t-micro); letter-spacing:.12em; color:var(--ink-3)">'
      + '<div>TIME</div><div>TRADER</div><div>MARKET</div><div style="text-align:right">KIND · SIDE</div><div style="text-align:right">THEY MOVED</div><div style="text-align:right">YOU MOVED</div><div style="text-align:right">STATUS</div></div>'
      + (rows.length ? '' : leerZeile(orders.length ? 'No order matches these filters.' : 'No paper orders reported by /api/copy yet.'))
      + rows.map((o) => {
        const farbe = o.status === 'copied' || o.status === 'settled' ? POS : o.status === 'skipped' ? AMBER : 'var(--ink-4)';
        const label = o.status === 'seed_observed' ? 'BASELINE' : String(o.status).toUpperCase();
        const k = kindOf(o);
        const seite = k === 'BUY' || k === 'SELL' ? k + ' ' + esc(o.outcome || String(o.side || '').split(' ').slice(1).join(' ')) : k;
        const teile = [];
        if (o.explain) teile.push(esc(o.explain));
        if (o.book) teile.push('<span style="' + M + '; color:var(--ink-2)">' + esc(o.book) + '</span>');
        if (o.reason && o.status === 'skipped') teile.push('skipped: ' + esc(o.reason));
        return '<div style="padding:var(--sp-4) var(--sp-5); border-bottom:1px solid var(--line-3)">'
          + '<div style="' + grid + '; align-items:center">'
          + '<div style="' + M + '; font-size:var(--t-small); color:' + DIM + '" title="' + esc(o.at || '') + '">' + esc(o.time) + '</div>'
          + '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-3); white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="' + esc(o.wallet || '') + '">' + esc(labelOf[o.wallet] || shortW(o.wallet) || '—') + '</div>'
          + '<div style="font-family:var(--font-ui); font-size:var(--t-small); white-space:nowrap; overflow:hidden; text-overflow:ellipsis">' + esc(o.market) + '</div>'
          + '<div style="' + M + '; font-size:var(--t-small); text-align:right; color:' + kindStyle(k) + '">' + seite + '</div>'
          + '<div style="' + M + '; font-size:var(--t-small); text-align:right; color:' + DIM + '">' + esc(o.theirs) + '</div>'
          + '<div style="' + M + '; font-size:var(--t-small); text-align:right">' + esc(o.yours) + '</div>'
          + '<div style="' + M + '; font-size:var(--t-micro); text-align:right; color:' + farbe + '" title="' + esc(o.reason || '') + '">' + esc(label) + '</div></div>'
          // 222px ist keine Abstandsstufe, sondern die Summe der Spalten
          // links davon: die Begruendungszeile beginnt unter dem Markt.
          + (teile.length ? '<div style="font-size:var(--t-micro); color:var(--ink-3); margin-top:var(--sp-2); padding-left:222px; line-height:1.45">' + teile.join(' · ') + '</div>' : '')
          + '</div>';
      }).join('')
      + '</div></div>';
  } else if (tab === 'positions') {
    const grid = 'display:grid; grid-template-columns:120px 1fr 62px 78px 78px 78px 88px 100px; gap:var(--sp-4)';
    body = '<div style="border:1px solid var(--line-2); border-radius:var(--r-panel); margin:var(--sp-5) var(--sp-6); overflow:hidden">'
      + '<div style="' + grid + '; padding:var(--sp-3) var(--sp-5); background:var(--panel); border-bottom:1px solid var(--line-2); ' + M + '; font-size:var(--t-micro); letter-spacing:.12em; color:var(--ink-3)">'
      + '<div>TRADER</div><div>MARKET</div><div style="text-align:right">SIDE</div><div style="text-align:right">SHARES</div><div style="text-align:right">AVG FILL</div><div style="text-align:right">MARK</div><div style="text-align:right">VALUE</div><div style="text-align:right">UNREALISED</div></div>'
      + (positions.length ? '' : leerZeile('No open paper positions reported by /api/copy.'))
      + positions.map((r) =>
        '<div style="' + grid + '; align-items:center; padding:var(--sp-4) var(--sp-5); border-bottom:1px solid var(--line-3)">'
        + '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-3); white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="' + esc(r[7] || '') + '">' + esc(labelOf[r[7]] || shortW(r[7]) || '—') + '</div>'
        + r.slice(0, 7).map((v, i) => {
          const style = i === 0 ? "font-family:var(--font-ui); font-size:var(--t-small); white-space:nowrap; overflow:hidden; text-overflow:ellipsis" : M + '; font-size:var(--t-small); text-align:right; color:' + (i === 6 ? (String(v).charAt(0) === '+' ? POS : RED) : i === 1 ? (v === 'Yes' ? POS : BLUE) : 'var(--ink-2)');
          return '<div style="' + style + '">' + esc(String(v)) + '</div>';
        }).join('')
        + '</div>'
      ).join('')
      + '</div>';
  } else if (tab === 'perf') {
    const putIn = filtered ? filtered.contributions : kp.contributions;
    const sourceName = firstActive ? (firstActive.label || shortW(firstActive.wallet)) : 'source wallet';
    body = '<div style="padding:var(--sp-5) var(--sp-6)">'
      + '<div style="' + KARTE + '; padding:var(--sp-5)">'
      + '<div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:var(--sp-4); flex-wrap:wrap; gap:var(--sp-4)">'
      + '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:.14em; color:var(--ink-4)">' + (filtered ? esc((filtered.label || shortW(filtered.wallet)).toUpperCase()) + ' — ' : 'ALL SUB-ACCOUNTS — ') + 'EQUITY VS CASH PUT IN</div>'
      + '<div style="display:flex; gap:var(--sp-5); ' + M + '; font-size:var(--t-micro)">'
      + '<span style="display:flex; align-items:center; gap:var(--sp-3)"><span style="width:14px; height:2px; background:' + ACCENT + '; display:inline-block"></span>Paper equity</span>'
      + '<span style="display:flex; align-items:center; gap:var(--sp-3); color:var(--ink-4)"><span style="width:14px; height:2px; background:rgba(var(--ink),.35); display:inline-block"></span>Cash put in ' + esc(usd(putIn, 0)) + '</span>'
      + '</div></div>'
      + (equityPts
        ? '<svg width="100%" height="240" viewBox="0 0 900 240" preserveAspectRatio="none" role="img" aria-label="Paper equity over time, against the benchmark">'
          + '<line x1="0" y1="20" x2="900" y2="20" style="stroke:rgba(var(--ink),.07)" /><line x1="0" y1="80" x2="900" y2="80" style="stroke:rgba(var(--ink),.07)" /><line x1="0" y1="140" x2="900" y2="140" style="stroke:rgba(var(--ink),.07)" /><line x1="0" y1="230" x2="900" y2="230" style="stroke:rgba(var(--ink),.14)" />'
          + '<polyline points="' + equityPts + '" fill="none" style="stroke:' + ACCENT + '" stroke-width="2" /></svg>'
        : leerZeile('No equity curve yet — the daemon (or a sync pass) records one point per minute per trader.'))
      + '</div>'
      + '<div style="' + KARTE + '; padding:var(--sp-5); margin-top:var(--sp-5)">'
      + '<div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:var(--sp-4); flex-wrap:wrap; gap:var(--sp-4)">'
      + '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:.14em; color:var(--ink-4)">YOUR RETURN VERSUS THE SOURCE WALLET</div>'
      + '<div style="display:flex; gap:var(--sp-5); ' + M + '; font-size:var(--t-micro)">'
      + '<span style="display:flex; align-items:center; gap:var(--sp-3)"><span style="width:14px; height:2px; background:' + ACCENT + '; display:inline-block"></span>You</span>'
      + '<span style="display:flex; align-items:center; gap:var(--sp-3); color:' + BLUE + '"><span style="width:14px; height:2px; background:' + BLUE + '; display:inline-block"></span>' + esc(sourceName) + ' (official PnL, 1 month)</span>'
      + '</div></div>'
      + (srcPts || minePts
        ? '<svg width="100%" height="200" viewBox="0 0 900 200" preserveAspectRatio="none" role="img" aria-label="Your paper equity against the trader you follow">'
          + '<line x1="0" y1="20" x2="900" y2="20" style="stroke:rgba(var(--ink),.07)" /><line x1="0" y1="100" x2="900" y2="100" style="stroke:rgba(var(--ink),.07)" /><line x1="0" y1="190" x2="900" y2="190" style="stroke:rgba(var(--ink),.14)" />'
          + (srcPts ? '<polyline points="' + srcPts + '" fill="none" style="stroke:' + BLUE + '" stroke-width="2" />' : '')
          + (minePts ? '<polyline points="' + minePts + '" fill="none" style="stroke:' + ACCENT + '" stroke-width="2" />' : '') + '</svg>'
        : leerZeile('Neither curve has two points yet.'))
      + (showSource ? '' : '<div style="font-size:var(--t-small); color:var(--ink-3); margin-top:var(--sp-3)">The source overlay is loaded for the first active trader only' + (firstActive ? ' (' + esc(firstActive.label || shortW(firstActive.wallet)) + ')' : '') + '.</div>')
      + '</div></div>';
  } else if (tab === 'fidelity') {
    const fid = live && live.fidelity_detail;
    let gapCosts;
    if (fid && fid.execution) {
      const skips = Object.entries(fid.execution.lost_to_skips || {}).sort((a, b) => b[1] - a[1]);
      const clamps = +fid.execution.lost_to_clamps || 0;
      const total = skips.reduce((a, kv) => a + (+kv[1] || 0), 0) + clamps;
      gapCosts = skips.map(([reason, value]) =>
        '<div style="display:flex; justify-content:space-between; font-size:var(--t-body)"><span style="color:var(--ink-2)">Skipped: ' + esc(reason) + '</span><span style="' + M + '; color:' + RED + '">-$' + (+value).toFixed(2) + '</span></div>'
      ).join('')
        + '<div style="display:flex; justify-content:space-between; font-size:var(--t-body)"><span style="color:var(--ink-2)">Clamped (cash throttle / order cap)</span><span style="' + M + '; color:var(--ink-3)">-$' + clamps.toFixed(2) + '</span></div>'
        + '<div style="display:flex; justify-content:space-between; font-size:var(--t-body); border-top:1px solid var(--line-2); padding-top:var(--sp-4)"><span>Total drag (24h)</span><span style="' + M + '; color:' + RED + '">-$' + total.toFixed(2) + '</span></div>';
    } else {
      gapCosts = leerZeile('No execution breakdown in this /api/copy answer — fidelity_detail is missing. Nothing is shown rather than an estimate.');
    }
    // Anteil an dem, worueber zu entscheiden war, nicht an jeder Zeile: die
    // Baseline-Zeilen sind kein uebersprungener Auftrag.
    const entscheidbar = kp.actionable != null ? kp.actionable : kp.total;
    const throttleShare = entscheidbar ? Math.round((kp.skipped / entscheidbar) * 100) : null;
    body = '<div style="padding:var(--sp-5) var(--sp-6); display:grid; grid-template-columns:1fr 1fr; gap:var(--sp-5)">'
      + '<div><div style="' + M + '; font-size:var(--t-micro); letter-spacing:.14em; color:var(--ink-4); margin-bottom:var(--sp-5)">WHERE THE COPY DRIFTS (ALL TRADERS)</div>'
      + '<div style="display:flex; flex-direction:column; gap:var(--sp-5)">'
      + fidelityBar('Settings vs a neutral mirror', kp.config_fidelity + '%', Math.min(100, kp.config_fidelity), ACCENT)
      + fidelityBar('Filled vs what you wanted', kp.exec_fidelity + '%', Math.min(100, kp.exec_fidelity), ACCENT)
      + fidelityBar('Orders skipped', throttleShare == null ? '— no orders yet' : throttleShare + '% of orders', throttleShare == null ? 0 : Math.min(100, throttleShare), AMBER, AMBER)
      + '</div></div>'
      + '<div><div style="' + M + '; font-size:var(--t-micro); letter-spacing:.14em; color:var(--ink-4); margin-bottom:var(--sp-5)">WHAT THE GAP COSTS</div>'
      + '<div style="display:flex; flex-direction:column; gap:var(--sp-4)">' + gapCosts + '</div></div></div>';
  } else {
    const grid = 'display:grid; grid-template-columns:110px 120px 1fr 120px 120px; gap:var(--sp-4)';
    body = '<div style="border:1px solid var(--line-2); border-radius:var(--r-panel); margin:var(--sp-5) var(--sp-6); overflow:hidden">'
      + '<div style="' + grid + '; padding:var(--sp-3) var(--sp-5); background:var(--panel); border-bottom:1px solid var(--line-2); ' + M + '; font-size:var(--t-micro); letter-spacing:.12em; color:var(--ink-3)">'
      + '<div>DATE</div><div>TRADER</div><div>WHAT HAPPENED</div><div style="text-align:right">AMOUNT</div><div style="text-align:right">CASH AFTER</div></div>'
      + (cashRows.length ? '' : leerZeile('No cash events reported by /api/copy. Start cash is not an event; top-ups are.'))
      + cashRows.map((r) =>
        '<div style="' + grid + '; align-items:center; padding:var(--sp-4) var(--sp-5); border-bottom:1px solid var(--line-3)">'
        + '<div style="' + M + '; font-size:var(--t-small); color:var(--ink-2)">' + esc(String(r[0])) + '</div>'
        + '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-3); white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="' + esc(r[4] || '') + '">' + esc(labelOf[r[4]] || shortW(r[4]) || '—') + '</div>'
        + '<div style="font-family:var(--font-ui); font-size:var(--t-small)">' + esc(String(r[1])) + '</div>'
        + '<div style="' + M + '; font-size:var(--t-small); text-align:right; color:' + (String(r[2]).charAt(0) === '+' && r[2] !== '+$0.00' ? POS : 'var(--ink-2)') + '">' + esc(String(r[2])) + '</div>'
        + '<div style="' + M + '; font-size:var(--t-small); text-align:right; color:var(--ink-2)">' + esc(String(r[3] || '')) + '</div>'
        + '</div>'
      ).join('')
      + '</div>';
  }

  // Daemon state from the answer or not at all — never a switch in the page.
  const daemonOn = st.running === true ? true : st.running === false ? false : null;
  const daemonFarbe = daemonOn === true ? ACCENT : daemonOn === false ? AMBER : 'var(--ink-3)';
  const daemonText = daemonOn === true ? 'RUNNING' : daemonOn === false ? 'STOPPED' : 'STATE NOT REPORTED';
  const activeCount = live.active_count != null ? live.active_count : traders.filter((t) => t.active).length;
  const totals = live.totals || { equity: kp.equity, contributions: kp.contributions };
  const msg = s.copyMsg
    ? '<div style="margin:var(--sp-4) var(--sp-6) 0; padding:var(--sp-3) var(--sp-4); border-radius:var(--r-control); ' + M + '; font-size:var(--t-small); display:flex; justify-content:space-between; gap:var(--sp-4); '
      + (s.copyMsg.kind === 'err' ? 'color:' + RED + '; border:1px solid rgba(var(--neg-rgb),.35); background:rgba(var(--neg-rgb),.06)' : 'color:' + POS + '; border:1px solid rgba(var(--pos-rgb),.3); background:rgba(var(--pos-rgb),.05)') + '">'
      + '<span>' + esc(s.copyMsg.text) + '</span><span ' + T.act(() => T.setState({ copyMsg: null })) + ' style="cursor:pointer; color:var(--ink-4)">dismiss</span></div>'
    : '';
  const access = live.write_access || {};
  const accessText = !access.mode ? '' : access.allowed ? (access.mode === 'token' ? 'WRITES · TOKEN' : 'WRITES · LOCAL') : 'READ-ONLY';
  return '<div>'
    + '<div style="padding:var(--sp-6) var(--sp-6) var(--sp-5); border-bottom:1px solid var(--line-2)">'
    + '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:.18em; color:' + ACCENT + '">COPY TRADE · PAPER</div>'
    + '<h1 style="font-size:var(--t-head); line-height:1.25; margin:var(--sp-3) 0 0; font-weight:600; letter-spacing:-0.01em">Follow traders with fake money</h1>'
    // Der Vorbehalt zum Papierkonto stand hier als Prosa und ist jetzt der
    // Registereintrag paper_desk_only.
    + caveatZeile('paper_desk_only', {
      vorsatz: 'Every buy a followed wallet makes is scaled into that wallet\'s own sub-account and booked at the printed price. Equal start cash, equal settings, so the sub-accounts are the comparison.',
      stil: 'font-size:var(--t-body); color:' + DIM + '; margin-top:var(--sp-3); max-width:760px; line-height:1.5'
    }) + '</div>'

    + '<div style="display:flex; align-items:center; gap:var(--sp-6); padding:var(--sp-4) var(--sp-6); border-bottom:1px solid var(--line-2); background:var(--panel); flex-wrap:wrap">'
    + '<div style="display:flex; align-items:center; gap:var(--sp-3)" title="' + esc((live.daemon && live.daemon.reason) || '') + '">'
    + '<span style="width:7px; height:7px; border-radius:50%; background:' + daemonFarbe + '; display:inline-block"></span>'
    + '<span style="' + M + '; font-size:var(--t-micro); letter-spacing:.14em; color:' + daemonFarbe + '">' + daemonText + '</span></div>'
    + '<div style="' + M + '; font-size:var(--t-small); color:var(--ink-3)">FOLLOWING <span style="color:var(--text)">' + activeCount + ' active</span>' + (traders.length > activeCount ? ' <span style="color:' + AMBER + '">' + (traders.length - activeCount) + ' paused</span>' : '') + '</div>'
    + '<div style="' + M + '; font-size:var(--t-small); color:var(--ink-3)">SOURCE <span style="color:var(--text)">' + esc(st.source) + '</span></div>'
    + '<div style="' + M + '; font-size:var(--t-small); color:var(--ink-3)">SCALE <span style="color:var(--text)">' + (+st.scale).toFixed(4) + '×</span></div>'
    + '<div style="' + M + '; font-size:var(--t-small); color:var(--ink-3)">CASH LEFT <span style="color:var(--text)">' + esc(usd(st.cash)) + '</span></div>'
    + '<div style="' + M + '; font-size:var(--t-micro); color:' + AMBER + '; border:1px solid rgba(var(--warn-rgb),.35); border-radius:var(--r-control); padding:var(--sp-2) var(--sp-3)">AUTO TOP-UP ' + (st.auto_topup ? 'ON' : 'OFF') + '</div>'
    + (accessText ? '<div style="' + M + '; font-size:var(--t-micro); color:' + (access.allowed ? ACCENT : 'var(--ink-4)') + '; border:1px solid var(--line-1); border-radius:var(--r-control); padding:var(--sp-2) var(--sp-3)" title="' + esc(access.reason || '') + '">' + accessText + '</div>' : '')
    + '</div>'

    + '<div style="display:grid; grid-template-columns:repeat(4,1fr); border-bottom:1px solid var(--line-2)">'
    + '<div style="padding:var(--sp-5) var(--sp-6); border-right:1px solid var(--line-2)"><div style="' + M + '; font-size:var(--t-micro); letter-spacing:.14em; color:var(--ink-3)">ALL SUB-ACCOUNTS · EQUITY</div><div style="' + M + '; font-size:var(--t-hero); margin-top:var(--sp-3)">' + esc(usd(totals.equity)) + '</div><div style="' + M + '; font-size:var(--t-micro); color:var(--ink-3); margin-top:var(--sp-2)">' + esc(usd(totals.contributions)) + ' put in</div></div>'
    // Die Kachel nannte eine Zahl fuer beides. Gebucht ist Geld, das eine
    // Aufloesung oder ein Verkauf zurueckgegeben hat; bewertet ist eine
    // Marke auf Positionen, die noch nichts entschieden haben (im
    // Standardpfad zum zuletzt gedruckten Preis der Quelle). Beide Zeilen
    // rechnen gegen dasselbe eingezahlte Kapital und addieren sich deshalb.
    + '<div style="padding:var(--sp-5) var(--sp-6); border-right:1px solid var(--line-2)"><div style="' + M + '; font-size:var(--t-micro); letter-spacing:.14em; color:var(--ink-3)">PROFIT ON PAPER · SETTLED VS MARKED</div><div style="' + M + '; font-size:var(--t-hero); margin-top:var(--sp-3); color:' + pnlColor(kp.pnl) + '">' + esc(signedUsd(kp.pnl)) + ' <span style="font-size:var(--t-body); color:var(--ink-3)">' + esc(pctLabel(kp.pnl_pct)) + '</span></div>'
    + '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-2); margin-top:var(--sp-2)">' + esc(splitSatz(kp)) + '</div>'
    + (kp.pnl_reconciles === false ? '<div style="' + M + '; font-size:var(--t-micro); color:' + AMBER + '; margin-top:var(--sp-2)">the two halves do not add up to the equity change (' + esc(signedUsd(kp.pnl_residual)) + ' unaccounted), so this is not a breakdown</div>' : '')
    + '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-3); margin-top:var(--sp-2)">'
    + (kp.source_pnl_delta != null ? 'first source ' + (kp.source_pnl_delta >= 0 ? '+' : '-') + '$' + num(Math.abs(kp.source_pnl_delta).toFixed(0)) + ' same window' : 'source wallet return not loaded') + '</div></div>'
    // Nenner ist, worueber zu entscheiden war. Vorher stand hier
    // kp.mirrored / kp.total: der Zaehler zaehlte nur ``copied``, der Nenner
    // jede Zeile. Eine kopierte Order, die aufgeloest wurde, fiel damit aus
    // dem Zaehler und blieb im Nenner, und die Baseline-Zeilen (Bestand der
    // Quelle beim Anlegen) standen nur im Nenner.
    + '<div style="padding:var(--sp-5) var(--sp-6); border-right:1px solid var(--line-2)"><div style="' + M + '; font-size:var(--t-micro); letter-spacing:.14em; color:var(--ink-3)">ORDERS MIRRORED</div><div style="' + M + '; font-size:var(--t-hero); margin-top:var(--sp-3)">' + kp.mirrored + ' <span style="font-size:var(--t-lead); color:var(--ink-3)">/ ' + (kp.actionable != null ? kp.actionable : kp.total) + '</span></div><div style="' + M + '; font-size:var(--t-micro); color:' + AMBER + '; margin-top:var(--sp-2)">' + kp.skipped + ' skipped</div>'
    + (kp.observed ? '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-4); margin-top:var(--sp-2)">' + kp.observed + ' baseline rows, never ours to mirror</div>' : '')
    + '</div>'
    + '<div style="padding:var(--sp-5) var(--sp-6)"><div style="' + M + '; font-size:var(--t-micro); letter-spacing:.14em; color:var(--ink-3)">HOW CLOSE TO THE SOURCE</div><div style="' + M + '; font-size:var(--t-hero); margin-top:var(--sp-3)">' + kp.fidelity + '%</div><div style="' + M + '; font-size:var(--t-micro); color:var(--ink-3); margin-top:var(--sp-2)">config ' + kp.config_fidelity + '% · execution ' + kp.exec_fidelity + '%</div></div>'
    + '</div>'

    + '<div style="display:flex; align-items:center; gap:var(--sp-3); padding:var(--sp-4) var(--sp-6); border-bottom:1px solid var(--line-2); flex-wrap:wrap">'
    + '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-3)">' + (canWrite ? 'This page writes to data/copy_trading.sqlite and data/copy_settings.json; the daemon (scripts/run_copy_trader.py) copies from them.' : 'Read-only view of the copy desk; the daemon runs where api/server.py runs.')
    + (live.as_of ? ' · snapshot ' + esc(String(live.as_of)) : '') + '</div>'
    + '<span style="flex:1"></span>'
    + button(T, 'Refresh', () => T.copyReload(), BTN_GHOST, 'ask /api/copy again')
    + '</div>'
    + msg
    + '<div style="display:flex; gap:var(--sp-3); padding:var(--sp-5) var(--sp-6) 0; flex-wrap:wrap">' + copyTabs + '</div>'
    + traderChips
    + body
    + '</div>';
}

function fidelityBar(label, valueLabel, pct, color, valueColor) {
  return '<div>'
    + '<div style="display:flex; justify-content:space-between; font-size:var(--t-small); margin-bottom:var(--sp-3)"><span style="color:var(--ink-2)">' + label + '</span><span style="' + M + (valueColor ? '; color:' + valueColor : '') + '">' + valueLabel + '</span></div>'
    + '<div style="height:7px; background:rgba(var(--ink),.07); border-radius:2px"><div style="width:' + pct + '%; height:7px; background:' + color + '; border-radius:2px"></div></div></div>';
}
