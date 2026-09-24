// Source-wallet observations. All external strings are escaped; URL hosts restricted.
import { esc } from '../util.js';
import { caveat } from '../claims.js';
import { MONO as M, KARTE } from '../ui.js';

const pct = n => n == null || !Number.isFinite(Number(n)) ? 'n/a' : (Number(n) * 100).toFixed(1) + '%';
const money = n => n == null || !Number.isFinite(Number(n)) ? 'n/a' : Number(n).toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });
const short = w => String(w).slice(0, 8) + '…' + String(w).slice(-4);
const stamp = s => s ? String(s).slice(0, 16).replace('T', ' ') + ' UTC' : 'pending';
const textStyle = 'font-size:var(--t-small); color:var(--ink-3); line-height:var(--lh-prose)';
const box = KARTE + '; padding:var(--sp-5); min-width:0';

function link(url, label) {
  try {
    const u = new URL(url);
    if (u.protocol !== 'https:' || !['polymarket.com', 'x.com', 'twitter.com'].includes(u.hostname)) return esc(label);
    return '<a href="' + esc(u.href) + '" target="_blank" rel="noopener noreferrer" style="color:var(--info)">' + esc(label) + ' ↗</a>';
  } catch { return esc(label); }
}

function metric(label, value, help = '') {
  return '<div title="' + esc(help) + '"><div style="' + textStyle + '">' + esc(label) + '</div>'
    + '<div style="' + M + '; font-size:var(--t-body); margin-top:var(--sp-2)">' + esc(value) + '</div></div>';
}

function walletCard(wallet, p, sources, trader, T) {
  const card = p.scorecard || {}, track = card.track || {}, sample = card.sample || {};
  const cal = card.calibration || {}, style = p.style || {};
  const categories = style.categories || [];
  const name = p.name || (trader && trader.label !== wallet ? trader.label : '') || short(wallet);
  const errors = Object.keys(p.errors || {});
  let html = '<article style="' + box + '"><h3 style="margin:0; font-size:var(--t-lead); overflow-wrap:anywhere">'
    + (T ? '<button ' + T.act(() => T.setState({copyTrader: wallet, copyTab: 'positions'})) + ' style="font:inherit; color:var(--accent); background:none; border:0; cursor:pointer">' + esc(name) + '</button>' : link(p.profile_url || 'https://polymarket.com/profile/' + wallet, name)) + '</h3>'
    + '<div style="' + M + '; font-size:var(--t-micro); overflow-wrap:anywhere; margin-top:var(--sp-3)">' + esc(wallet) + '</div>'
    + '<div style="' + textStyle + '">' + (trader && trader.active ? 'Paper copy active' : 'Paper copy paused')
    + ' · Research ' + esc(stamp(p.snapshot_at)) + (p.stale ? ' · STALE' : '') + '</div>'
    + '<div style="margin-top:var(--sp-4); ' + textStyle + '">Why followed: '
    + (sources.length ? sources.map((url, i) => link(url, 'X source ' + (i + 1))).join(' · ') : 'no source post supplied') + '</div>';
  if (!p.snapshot_at) return html + '<p style="' + textStyle + '">Public wallet data is loading in the background.</p></article>';
  if (errors.length) html += '<p role="status" style="color:var(--warn)">Partial data: ' + esc(errors.join(', ')) + '. Missing values are not zero.</p>';
  html += '<div style="display:flex; flex-wrap:wrap; gap:var(--sp-4); margin:var(--sp-5) 0">'
    + categories.slice(0, 4).map(c => '<span style="border:1px solid var(--line-2); padding:var(--sp-3) var(--sp-4); border-radius:var(--r-control); font-size:var(--t-small)">' + esc(c.category) + ' ' + pct(c.share) + '</span>').join('')
    + (!categories.length ? '<span style="' + textStyle + '">Category unknown</span>' : '')
    + '<span style="' + textStyle + '">' + (style.buy_count ? (style.longshot_share >= .6 ? 'Longshots' : style.favorite_share >= .6 ? 'Favorites' : 'Mixed entry prices') : 'Entry style unknown')
    + ' · ' + (style.timing_n ? (style.early_share >= .6 ? 'Early entries' : style.late_share >= .6 ? 'Late entries' : 'Mixed timing') : 'Timing unknown') + '</span></div>'
    + '<div style="display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:var(--sp-5)">'
    + metric('Realized PnL · loaded closed set', errors.includes('resolved') || !track.resolved_markets ? 'n/a' : money(track.settled_pnl), track.coverage_note || '')
    + metric('Profitable events · winrate · n=' + (track.resolved_events || track.resolved_markets || 0), errors.includes('resolved') ? 'n/a' : pct(track.headline_win_rate), 'Canonical scorecard: legs netted per event; not individual trade fills.')
    + metric('Resolution hit rate · 95% CI · n=' + (cal.n || 0), cal.hit_rate == null ? 'n/a' : pct(cal.hit_rate) + ' [' + pct(cal.hit_low) + ', ' + pct(cal.hit_high) + ']', 'Position-level interval; legs from the same event are correlated. This is distinct from profitable-event winrate.')
    + metric('Source portfolio Sharpe', 'n/a', p.sharpe_reason || '')
    + metric('Longshots ≤20¢', pct(style.longshot_share), style.basis)
    + metric('Favorites ≥80¢', pct(style.favorite_share), style.basis)
    + metric('Early ≥7d / late ≤24h', pct(style.early_share) + ' / ' + pct(style.late_share), style.timing_basis)
    + metric('Median time to scheduled end', style.median_hours_to_end == null ? 'n/a' : Number(style.median_hours_to_end).toFixed(1) + ' h', style.timing_basis)
    + '</div><p style="' + textStyle + '">n=' + (sample.n_resolved || 0) + ' resolved events · sample size: ' + esc(sample.quality || 'unknown')
    + (track.resolved_capped ? ' · CAPPED: only winner/loser extremes, not full history' : '')
    + '<br>' + (style.buy_count || 0) + ' buys / ' + (p.activity_count || 0) + ' activity rows since ' + esc(stamp(p.activity_from))
    + (p.activity_capped ? ' · capped window' : '') + '. Timing available for ' + (style.timing_n || 0) + ' buys.'
    + '<br>Categories are heuristics; style percentages weight purchase dollars. Timing uses the scheduled end, not actual resolution.'
    + '<br>Sharpe requires a complete daily equity-return series adjusted for deposits and withdrawals.</p>'
    + '<details><summary style="cursor:pointer">What they trade · positions and recent trades</summary>'
    + '<div style="overflow-x:auto; margin-top:var(--sp-4)"><table style="width:100%; font-size:var(--t-small); text-align:left; border-collapse:collapse">'
    + '<caption style="text-align:left; margin:var(--sp-4) 0">Open positions' + (p.positions_capped ? ' · feed capped' : '') + '</caption>'
    + '<thead><tr><th scope="col">Market / outcome</th><th scope="col">Value</th><th scope="col">Entry</th><th scope="col">Unrealized</th></tr></thead><tbody>'
    + (p.positions || []).slice(0, 20).map(r => '<tr><td style="padding:var(--sp-4) var(--sp-3) var(--sp-4) 0">' + link(r.url, r.title) + '<br>' + esc(r.outcome) + '</td><td style="padding:var(--sp-2) var(--sp-3); white-space:nowrap">' + money(r.value) + '</td><td style="padding:var(--sp-2) var(--sp-3); white-space:nowrap">' + pct(r.avg_price) + '</td><td style="padding:var(--sp-2) var(--sp-3); white-space:nowrap">' + money(r.unrealized_pnl) + '</td></tr>').join('')
    + '</tbody></table></div>'
    + (!(p.positions || []).length ? '<p style="' + textStyle + '">' + (errors.includes('positions') ? 'Position read failed.' : 'No open priced positions in this read.') + '</p>' : '')
    + '<p style="' + textStyle + '">Showing up to 20 positions. Recent trades:</p>'
    + (p.recent_trades || []).map(r => '<div style="padding:var(--sp-4) 0; border-top:1px solid var(--line-3); ' + textStyle + '">' + esc(stamp(r.time)) + ' · ' + esc(r.side) + ' ' + esc(r.outcome) + ' · ' + money(r.notional) + ' @ ' + pct(r.price) + '<br>' + link(r.url, r.title) + '</div>').join('')
    + '</details></article>';
  return html;
}

export function intelligencePanel(live, T) {
  const state = live.intelligence || {}, profiles = state.profiles || {}, watchlist = state.watchlist || {};
  const traders = Object.fromEntries((live.traders || []).map(t => [t.wallet, t]));
  return '<section style="padding:var(--sp-5) var(--sp-6)"><h2 style="margin-top:0; font-size:var(--t-lead)">Source wallets</h2>'
    + '<p style="' + textStyle + '">Actual wallet history, separate from the paper accounts. Refresh every ' + ((state.refresh_seconds || 300) / 60) + ' minutes. '
    + (state.stale ? 'Waiting for a fresh snapshot.' : 'Snapshot ' + esc(stamp(state.snapshot_at)) + '.') + '</p>'
    + (!Object.keys(watchlist).length ? '<p>No research wallets imported yet.</p>' : '')
    + '<div style="display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,390px),1fr)); gap:var(--sp-5)">'
    + Object.entries(watchlist).map(([wallet, sources]) => walletCard(wallet, profiles[wallet] || {}, sources, traders[wallet], T)).join('')
    + '</div></section>';
}

function overlapCard(row, profiles) {
  return '<article style="' + box + '"><h3 style="margin:0 0 var(--sp-4); font-size:var(--t-body)">' + link(row.url, row.title) + '</h3>'
    + '<div style="color:var(--' + (row.direction === 'same_outcome' ? 'accent' : 'warn') + '); font-size:var(--t-small)">'
    + row.wallet_count + ' wallets · ' + (row.direction === 'same_outcome' ? 'SAME OUTCOME' : 'DIFFERENT OUTCOMES / POSSIBLE HEDGE')
    + (row.stale ? ' · STALE' : row.partial ? ' · PARTIAL READ' : '') + '</div>'
    + '<ul style="padding-left:var(--sp-5); ' + textStyle + '">' + (row.participants || []).map(p => '<li>'
      + link('https://polymarket.com/profile/' + p.wallet, (profiles[p.wallet] || {}).name || short(p.wallet))
      + ' · ' + esc(p.outcome) + ' · buys ' + money(p.buy_notional) + ' · net +' + Number(p.net_shares).toFixed(1) + ' shares'
      + ' · ' + esc(stamp(p.last_buy_at)) + '</li>').join('') + '</ul>'
    + (row.detected_at ? '<div style="' + textStyle + '">' + (row.initial ? 'Initial observation' : 'Detected') + ' ' + esc(stamp(row.detected_at)) + '</div>' : '') + '</article>';
}

export function signalsPanel(live) {
  const state = live.intelligence || {}, profiles = state.profiles || {};
  const truncated = Object.values(profiles).filter(p => p.activity_capped && Date.parse(p.activity_from) > Date.parse(state.snapshot_at) - 86400000);
  return '<section style="padding:var(--sp-5) var(--sp-6)"><h2 style="margin-top:0; font-size:var(--t-lead)">Shared markets · last 24 hours</h2>'
    + '<p style="' + textStyle + '">At least two watched wallets with net positive purchased shares in the same conditionId. Sells in the window offset buys. ' + caveat('copy_shared_flow') + ' Checks every 5 minutes while the copy daemon runs, or when this desk is open.</p>'
    + ((state.stale || Object.keys(state.errors || {}).length) ? '<p role="status" style="color:var(--warn)">Snapshot stale or incomplete. Missing activity can hide overlaps.</p>' : '')
    + (truncated.length ? '<p style="color:var(--warn); font-size:var(--t-small)">The 500-row limit covers less than 24 hours for ' + truncated.length + ' wallet(s). Signals use only the loaded flows; earlier buys and sells may be missing.</p>' : '')
    + '<div style="display:grid; gap:var(--sp-4)">' + (state.overlaps || []).map(r => overlapCard(r, profiles)).join('')
    + (!(state.overlaps || []).length ? '<p>No shared market detected in the available window.</p>' : '') + '</div>'
    + '<h2 style="font-size:var(--t-lead)">Notification history</h2><p style="' + textStyle + '">New notices for new or returning wallet/outcome combinations. Repeated checks do not duplicate notices. Up to 100 observations retained.</p>'
    + '<div style="display:grid; gap:var(--sp-4)">' + (state.alerts || []).map(r => overlapCard(r, profiles)).join('') + '</div></section>';
}

export function signalsBanner(T, live) {
  const state = live.intelligence || {}, rows = state.overlaps || [];
  const fresh = rows.filter(r => !r.stale).length;
  if (!Object.keys(state.watchlist || {}).length) return '';
  return '<div role="status" aria-live="polite" style="margin:var(--sp-5) var(--sp-6) 0; ' + box + '">'
    + '<button type="button" ' + T.act(() => T.setState({ copyTab: 'signals' })) + ' style="background:none; border:0; color:var(--accent); font:inherit; cursor:pointer; text-align:left">'
    + fresh + ' shared markets · ' + (state.alerts || []).length + ' saved notices →</button>'
    + '<span style="' + textStyle + '; margin-left:var(--sp-4)">' + esc(stamp(state.snapshot_at)) + (state.stale ? ' · STALE' : '') + '</span></div>';
}
