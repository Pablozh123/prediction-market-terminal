// Backtester, Copy trade, Portfolio — ported from the design reference.
// The backtester renders live results from POST /api/backtest when available,
// otherwise the reference's deterministic synthetic curves.

import { esc, money, num } from '../util.js';
import { DEMO_COPY_POSITIONS, DEMO_CASH_ROWS, DEMO_PORT_ROWS, DEMO_HIST_ROWS } from '../demo_data.js';
import { trackWatchRows } from './trader_pages.js';

const M = "font-family:'JetBrains Mono',monospace";
const LBL9 = M + '; font-size:9px; letter-spacing:.14em; color:rgba(255,255,255,.42); margin-bottom:6px';
const LBL95 = M + '; font-size:9.5px; letter-spacing:.14em; color:rgba(255,255,255,.45); margin-bottom:7px';
const HEAD_CELL = M + '; font-size:9.5px; letter-spacing:.14em; color:rgba(255,255,255,.45)';

const SIZING = { fixed: 'Fixed $', pct: '% of bankroll', match: 'Match trader %', kelly: 'Kelly ¼' };

function bt(T, patch) {
  return () => { T.setState(patch); T.runBacktestLive(); };
}

// ---------------------------------------------------------------- backtester
export function renderBacktester(T) {
  const s = T.state;
  const bank = s.btBankroll;
  const rawStake = s.btSizing === 'pct' ? bank * s.btStakePct / 100
    : s.btSizing === 'match' ? bank * 0.02 * s.btStakeMult
    : s.btSizing === 'kelly' ? bank * 0.25 * (s.btStakeKelly / 100) / 0.45
    : s.btStakeFixed;
  const stake = Math.min(rawStake, s.btCap);
  const nPts = { 7: 26, 30: 60, 90: 110 }[s.btWindow];
  const feeDrag = (s.btFee + s.btSlip) / 260;
  const sizeF = Math.max(0.25, Math.min(3, stake / 25));
  const seed = s.btWindow * 31 + (s.btStrategy === 'copy' ? 5 : 9) + Math.round(stake) + s.btExposure;
  const drift = ((s.btStrategy === 'copy' ? 0.9 : -0.25) * sizeF * (s.btExposure / 50)) - feeDrag;
  const live = T.liveData.backtest;

  // Synthetic fallbacks (identical maths to the reference).
  const eq = T.curve(seed, nPts, 900, 270, drift, 4.2 * sizeF);
  const bench = T.curve(seed + 101, nPts, 900, 270, 0.55, 3.4);
  const best = T.curve(seed + 202, nPts, 900, 270, Math.abs(drift) * 1.45 + 0.3, 4.0);
  const cmp = s.btCompare.trim() ? T.curve(seed + 303, nPts, 900, 270, 0.45, 4.6) : null;
  const scale = bank / 1000;
  let finalEq = bank + eq.last * 11 * scale;
  let benchPnl = bench.last * 11 * scale;
  let ret = ((finalEq - bank) / bank) * 100;
  let totalPnl = finalEq - bank;
  let copied = Math.round(nPts * 1.9 * Math.min(1, s.btExposure / 55));
  let skippedN = Math.round(nPts * 2.6 - copied);
  let winsN = Math.round(copied * (s.btStrategy === 'copy' ? 0.57 : 0.43));
  let lossesN = copied - winsN;
  let feesPaid = copied * stake * (s.btFee / 10000);
  let openValue = stake * 6.4;
  let ddPct = Math.abs(eq.drawdown) * 1.1;
  let equityPts = eq.pts, benchPts = bench.pts, ddPts = T.curve(seed + 404, nPts, 900, 220, -0.35, 3.0).pts;

  if (live && live.stats) {
    const st = live.stats;
    finalEq = +st.final_equity; ret = +st.roi * 100; totalPnl = +st.total_pnl;
    benchPnl = live.benchmark_stats ? +live.benchmark_stats.total_pnl : 0;
    copied = +st.copied_trades; skippedN = +st.skipped_trades;
    winsN = +st.wins; lossesN = +st.losses;
    feesPaid = +st.fees_paid; openValue = +st.open_value;
    ddPct = Math.abs(+st.max_drawdown) * 100;
    if (live.equity && live.equity.length > 1) {
      equityPts = T.seriesPoints(live.equity, 900, 270);
      benchPts = live.benchmark && live.benchmark.length > 1 ? T.seriesPoints(live.benchmark, 900, 270) : '';
      ddPts = live.drawdown && live.drawdown.length > 1 ? T.seriesPoints(live.drawdown, 900, 220) : ddPts;
    }
  }

  const simVariants = (live && live.variants ? live.variants.map((v) => ({
    name: v.name, eq: +v.final_equity, roi: +v.roi * 100, dd: Math.abs(+v.max_drawdown) * 100,
    wr: +v.win_rate * 100, copied: +v.copied_trades, skipped: +v.skipped_trades
  })) : [
    { name: 'Fixed $25', k: 1.0 },
    { name: 'Fixed $50', k: 1.18 },
    { name: '2% of bankroll', k: 1.09 },
    { name: '5% of bankroll', k: 0.86 },
    { name: 'Match trader % ×1', k: 1.31 },
    { name: 'Kelly ¼ · 5 pts edge', k: 1.22 }
  ].map((v, i) => {
    const e = bank + eq.last * 11 * scale * v.k + (i * 3);
    return { name: v.name, eq: e, roi: ((e - bank) / bank) * 100, dd: ddPct * (2 - v.k), wr: 50 + (v.k - 1) * 26, copied: Math.round(copied * Math.min(1.3, 2 - v.k * 0.6)), skipped: Math.round(skippedN * v.k) };
  })).sort((a, b) => b.eq - a.eq);
  const bestVariant = simVariants[0];

  const shortCmp = s.btCompare.trim() ? s.btCompare.trim().slice(0, 6) + '…' + s.btCompare.trim().slice(-3) : 'compare wallet';
  const shortWallet = s.btWallet.trim().length > 12 ? s.btWallet.trim().slice(0, 6) + '…' + s.btWallet.trim().slice(-4) : s.btWallet.trim();
  const runMeta = (s.btStrategy === 'copy' ? 'Copy' : 'Fade') + ' · last ' + s.btWindow + ' days · wallet ' + shortWallet + ' · ' + SIZING[s.btSizing] + ' · fees ' + s.btFee + ' bps · slippage ' + s.btSlip + ' bps'
    + (live && live.stats && live.stats.window_truncated ? ' · window truncated (hyperactive wallet)' : '');

  const statCards = [
    { label: 'FINAL EQUITY', value: '$' + finalEq.toFixed(0), sub: (ret >= 0 ? '+' : '') + ret.toFixed(1) + '% ROI', pos: ret >= 0 },
    { label: 'TOTAL P&L', value: (totalPnl >= 0 ? '+' : '-') + '$' + Math.abs(totalPnl).toFixed(0), sub: (totalPnl - benchPnl >= 0 ? '+' : '-') + '$' + Math.abs(totalPnl - benchPnl).toFixed(0) + ' vs flat-bet', pos: totalPnl >= 0 },
    { label: 'WIN RATE', value: Math.round((winsN / Math.max(1, copied)) * 100) + '%', sub: winsN + 'W / ' + lossesN + 'L', pos: null },
    { label: 'MAX DRAWDOWN', value: ddPct.toFixed(1) + '%', sub: 'from the running peak', pos: false },
    { label: 'TRADES COPIED', value: num(copied), sub: num(Math.max(0, skippedN)) + ' skipped', pos: null },
    { label: 'FEES PAID', value: '$' + feesPaid.toFixed(2), sub: '$' + openValue.toFixed(0) + ' still open', pos: null }
  ];

  const stakeLabel = s.btSizing === 'pct' ? 'STAKE (% OF BANKROLL)' : s.btSizing === 'match' ? "MULTIPLIER (× TRADER'S SHARE)" : s.btSizing === 'kelly' ? 'ASSUMED EDGE (PROBABILITY POINTS)' : 'STAKE PER COPY ($)';
  const stakeValue = s.btSizing === 'pct' ? s.btStakePct.toFixed(1) + '%' : s.btSizing === 'match' ? '×' + s.btStakeMult.toFixed(1) : s.btSizing === 'kelly' ? s.btStakeKelly.toFixed(1) + ' pts' : '$' + s.btStakeFixed;
  const stakeHint = s.btSizing === 'pct' ? 'Each copy bets ' + s.btStakePct.toFixed(1) + '% of your bankroll — about $' + (bank * s.btStakePct / 100).toFixed(0) + ' right now.'
    : s.btSizing === 'match' ? 'If the trader puts 2% of their portfolio into a bet, you put 2% × ' + s.btStakeMult.toFixed(1) + ' of yours. Their portfolio size is read from their public profile.'
    : s.btSizing === 'kelly' ? 'Assumes every entry is worth its price plus ' + s.btStakeKelly.toFixed(1) + ' points, then stakes quarter-Kelly of equity. Conservative on purpose — the edge is an assumption.'
    : 'Every copied trade bets exactly $' + s.btStakeFixed + '. Capped at $' + s.btCap + ' per trade.';
  const stakeUp = s.btSizing === 'pct' ? { btStakePct: Math.min(100, s.btStakePct + 0.5) } : s.btSizing === 'match' ? { btStakeMult: Math.min(10, s.btStakeMult + 0.5) } : s.btSizing === 'kelly' ? { btStakeKelly: Math.min(30, s.btStakeKelly + 0.5) } : { btStakeFixed: s.btStakeFixed + 5 };
  const stakeDown = s.btSizing === 'pct' ? { btStakePct: Math.max(0.1, s.btStakePct - 0.5) } : s.btSizing === 'match' ? { btStakeMult: Math.max(0.1, s.btStakeMult - 0.5) } : s.btSizing === 'kelly' ? { btStakeKelly: Math.max(0.5, s.btStakeKelly - 0.5) } : { btStakeFixed: Math.max(1, s.btStakeFixed - 5) };

  const demoLog = [
    { t: '07-30 14:19', a: 'BUY', st: 'filled', m: 'Brazil win on 2026-06-13', side: 'No', src: 18400, fill: 0.415 },
    { t: '07-30 09:02', a: 'BUY', st: 'filled', m: 'Fed cuts rates in September 2026', side: 'Yes', src: 9750, fill: 0.620 },
    { t: '07-29 21:44', a: 'BUY', st: 'skipped', m: 'Germany win on 2026-06-20', side: 'No', src: 11200, fill: 0 },
    { t: '07-29 16:31', a: 'SELL', st: 'filled', m: 'Iraq win on 2026-06-22', side: 'Yes', src: 15600, fill: 0.960 },
    { t: '07-29 11:08', a: 'BUY', st: 'filled', m: 'Government shutdown before October 2026', side: 'Yes', src: 24800, fill: 0.290 },
    { t: '07-28 19:55', a: 'BUY', st: 'skipped', m: 'Japan win on 2026-06-14', side: 'No', src: 7400, fill: 0 },
    { t: '07-28 13:12', a: 'BUY', st: 'filled', m: 'Bitcoin above $150k on Dec 31, 2026', side: 'Yes', src: 3400, fill: 0.380 },
    { t: '07-27 22:40', a: 'SELL', st: 'filled', m: 'Korea Republic win on 2026-06-11', side: 'No', src: 5050, fill: 0.635 }
  ];
  const logRows = live && live.log ? live.log.map((l) => ({
    time: l.time, action: l.action, status: l.status, market: l.market, side: l.side,
    traderAmt: '$' + num(Math.round(+l.trader_amt || 0)),
    stake: +l.stake ? '$' + (+l.stake).toFixed(2) : '—',
    fill: +l.fill ? (+l.fill).toFixed(3) : '—',
    fee: +l.fee ? '$' + (+l.fee).toFixed(2) : '—',
    equity: '$' + (+l.equity).toFixed(2)
  })) : demoLog.map((l, i) => {
    const st_ = l.st === 'skipped' ? 0 : stake;
    return {
      time: l.t, action: l.a, status: l.st, market: l.m, side: l.side,
      traderAmt: '$' + num(l.src),
      stake: st_ ? '$' + st_.toFixed(2) : '—',
      fill: l.fill ? l.fill.toFixed(3) : '—',
      fee: st_ ? '$' + (st_ * s.btFee / 10000).toFixed(2) : '—',
      equity: '$' + (bank + (finalEq - bank) * ((i + 1) / 8)).toFixed(2)
    };
  });

  const demoOpen = [
    { m: 'Fed cuts rates in September 2026', side: 'Yes', sh: 40.3, avg: 0.580, mark: 0.620 },
    { m: 'Government shutdown before October 2026', side: 'Yes', sh: 86.2, avg: 0.220, mark: 0.290 },
    { m: 'Bitcoin above $150k on Dec 31, 2026', side: 'Yes', sh: 61.0, avg: 0.410, mark: 0.380 },
    { m: 'Brazil win on 2026-06-13', side: 'No', sh: 58.4, avg: 0.415, mark: 0.435 },
    { m: 'ECB holds rates at the September meeting', side: 'Yes', sh: 34.1, avg: 0.680, mark: 0.710 }
  ];
  const openRows = (live && live.open ? live.open.map((o) => ({ m: o.market, side: o.side, sh: +o.shares, avg: +o.avg, mark: +o.mark })) : demoOpen).map((o) => {
    const cost = o.sh * o.avg, val = o.sh * o.mark, pnl = val - cost;
    return { market: o.m, side: o.side, shares: o.sh.toFixed(1), avg: o.avg.toFixed(3), mark: o.mark.toFixed(3), cost: '$' + cost.toFixed(2), value: '$' + val.toFixed(2), pnl: (pnl >= 0 ? '+' : '-') + '$' + Math.abs(pnl).toFixed(2), pnlPos: pnl >= 0 };
  });

  const compareRows = [
    { metric: 'Final equity', a: finalEq, b: finalEq * 0.88, money: true },
    { metric: 'Total P&L', a: totalPnl, b: totalPnl * 0.72, money: true },
    { metric: 'Win rate', a: (winsN / Math.max(1, copied)) * 100, b: 51, pct: true },
    { metric: 'Max drawdown', a: ddPct, b: ddPct * 1.4, pct: true },
    { metric: 'Trades copied', a: copied, b: Math.round(copied * 1.3), plain: true }
  ];

  const stepRow = (label, valueLabel, down, up) =>
    '<div><div style="' + LBL95 + '">' + label + '</div>'
    + '<div style="display:flex; align-items:center; gap:6px">'
    + '<div ' + T.act(bt(T, down)) + ' style="width:28px; height:32px; flex:none; border:1px solid rgba(255,255,255,.16); border-radius:7px; display:flex; align-items:center; justify-content:center; ' + M + '; font-size:14px; color:rgba(255,255,255,.7); cursor:pointer">−</div>'
    + '<div style="flex:1; background:#10151A; border:1px solid rgba(255,255,255,.16); border-radius:7px; padding:7px 8px; ' + M + '; font-size:12.5px; text-align:center">' + esc(valueLabel) + '</div>'
    + '<div ' + T.act(bt(T, up)) + ' style="width:28px; height:32px; flex:none; border:1px solid rgba(255,255,255,.16); border-radius:7px; display:flex; align-items:center; justify-content:center; ' + M + '; font-size:14px; color:rgba(255,255,255,.7); cursor:pointer">+</div></div></div>';

  const btTabs = [
    T.tab('Trade log', s.btTab === 'log', { btTab: 'log' }),
    T.tab('Open positions', s.btTab === 'open', { btTab: 'open' }),
    T.tab('Drawdown', s.btTab === 'dd', { btTab: 'dd' })
  ].concat(s.btCompare.trim() ? [T.tab('Comparison', s.btTab === 'cmp', { btTab: 'cmp' })] : []).join('');

  let tabBody = '';
  if (s.btTab === 'log') {
    tabBody = '<div style="border:1px solid rgba(255,255,255,.09); border-radius:12px; margin-top:12px; overflow:hidden">'
      + '<div style="display:grid; grid-template-columns:88px 74px 84px 1fr 60px 84px 78px 74px 84px 88px; gap:10px; padding:9px 16px; background:#10151A; border-bottom:1px solid rgba(255,255,255,.09); ' + M + '; font-size:9px; letter-spacing:.12em; color:rgba(255,255,255,.45)">'
      + '<div>TIME</div><div>ACTION</div><div>STATUS</div><div>MARKET</div><div>SIDE</div><div style="text-align:right">TRADER $</div><div style="text-align:right">STAKE</div><div style="text-align:right">FILL</div><div style="text-align:right">FEE</div><div style="text-align:right">EQUITY</div></div>'
      + logRows.map((l) =>
        '<div style="display:grid; grid-template-columns:88px 74px 84px 1fr 60px 84px 78px 74px 84px 88px; gap:10px; align-items:center; padding:10px 16px; border-bottom:1px solid rgba(255,255,255,.06); ' + M + '; font-size:11.5px">'
        + '<div style="color:rgba(255,255,255,.5)">' + esc(l.time) + '</div>'
        + '<div style="' + M + '; font-size:11.5px; color:' + (l.action === 'BUY' ? '#C8F542' : '#FF4545') + '">' + esc(l.action) + '</div>'
        + '<div><span style="' + M + '; font-size:9.5px; letter-spacing:.08em; border-radius:4px; padding:2px 6px; ' + (l.status === 'skipped' ? 'color:#F5A623; border:1px solid rgba(245,166,35,.35)' : 'color:rgba(255,255,255,.7); border:1px solid rgba(255,255,255,.18)') + '">' + esc(l.status) + '</span></div>'
        + '<div style="font-family:\'Inter\',sans-serif; font-size:12.5px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis">' + esc(l.market) + '</div>'
        + '<div style="color:rgba(255,255,255,.6)">' + esc(l.side) + '</div>'
        + '<div style="text-align:right; color:rgba(255,255,255,.5)">' + esc(l.traderAmt) + '</div>'
        + '<div style="text-align:right">' + esc(l.stake) + '</div>'
        + '<div style="text-align:right; color:rgba(255,255,255,.6)">' + esc(l.fill) + '</div>'
        + '<div style="text-align:right; color:rgba(255,255,255,.5)">' + esc(l.fee) + '</div>'
        + '<div style="text-align:right">' + esc(l.equity) + '</div></div>'
      ).join('')
      + '<div style="padding:12px 16px"><span class="hv-bd35" style="font-size:12.5px; border:1px solid rgba(255,255,255,.2); border-radius:7px; padding:8px 13px; cursor:pointer; display:inline-block">Export trade log CSV</span></div>'
      + '</div>';
  } else if (s.btTab === 'open') {
    tabBody = '<div style="border:1px solid rgba(255,255,255,.09); border-radius:12px; margin-top:12px; overflow:hidden">'
      + '<div style="display:grid; grid-template-columns:1fr 62px 78px 78px 78px 88px 88px 100px; gap:10px; padding:9px 16px; background:#10151A; border-bottom:1px solid rgba(255,255,255,.09); ' + M + '; font-size:9px; letter-spacing:.12em; color:rgba(255,255,255,.45)">'
      + '<div>MARKET</div><div>SIDE</div><div style="text-align:right">SHARES</div><div style="text-align:right">AVG FILL</div><div style="text-align:right">MARK</div><div style="text-align:right">COST</div><div style="text-align:right">VALUE</div><div style="text-align:right">UNREALISED</div></div>'
      + openRows.map((o) =>
        '<div style="display:grid; grid-template-columns:1fr 62px 78px 78px 78px 88px 88px 100px; gap:10px; align-items:center; padding:10px 16px; border-bottom:1px solid rgba(255,255,255,.06); ' + M + '; font-size:11.5px">'
        + '<div style="font-family:\'Inter\',sans-serif; font-size:12.5px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis">' + esc(o.market) + '</div>'
        + '<div style="' + M + '; font-size:11.5px; color:' + (o.side === 'Yes' ? '#C8F542' : '#4F8EF7') + '">' + esc(o.side) + '</div>'
        + '<div style="text-align:right; color:rgba(255,255,255,.6)">' + o.shares + '</div>'
        + '<div style="text-align:right; color:rgba(255,255,255,.6)">' + o.avg + '</div>'
        + '<div style="text-align:right">' + o.mark + '</div>'
        + '<div style="text-align:right; color:rgba(255,255,255,.6)">' + o.cost + '</div>'
        + '<div style="text-align:right">' + o.value + '</div>'
        + '<div style="text-align:right; ' + M + '; font-size:12px; color:' + (o.pnlPos ? '#C8F542' : '#FF4545') + '">' + o.pnl + '</div></div>'
      ).join('')
      + '</div>';
  } else if (s.btTab === 'dd') {
    tabBody = '<div style="background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:12px; margin-top:12px; padding:16px 18px">'
      + '<div style="' + M + '; font-size:10.5px; letter-spacing:.14em; color:rgba(255,255,255,.55); margin-bottom:12px">DRAWDOWN FROM THE RUNNING PEAK</div>'
      + '<svg width="100%" height="220" viewBox="0 0 900 220" preserveAspectRatio="none">'
      + '<line x1="0" y1="10" x2="900" y2="10" stroke="rgba(255,255,255,.14)" />'
      + '<line x1="0" y1="70" x2="900" y2="70" stroke="rgba(255,255,255,.07)" />'
      + '<line x1="0" y1="130" x2="900" y2="130" stroke="rgba(255,255,255,.07)" />'
      + '<line x1="0" y1="190" x2="900" y2="190" stroke="rgba(255,255,255,.07)" />'
      + '<polyline points="' + ddPts + '" fill="none" stroke="#FF4545" stroke-width="2" /></svg>'
      + '<div style="display:flex; justify-content:space-between; ' + M + '; font-size:10px; color:rgba(255,255,255,.4); margin-top:8px">'
      + '<span>' + s.btWindow + 'd ago</span><span>worst: ' + ddPct.toFixed(1) + '%</span><span>today</span></div></div>';
  } else if (s.btTab === 'cmp' && s.btCompare.trim()) {
    tabBody = '<div style="border:1px solid rgba(255,255,255,.09); border-radius:12px; margin-top:12px; overflow:hidden">'
      + '<div style="display:grid; grid-template-columns:1fr 130px 130px 110px; gap:10px; padding:9px 16px; background:#10151A; border-bottom:1px solid rgba(255,255,255,.09); ' + M + '; font-size:9px; letter-spacing:.12em; color:rgba(255,255,255,.45)">'
      + '<div>METRIC</div><div style="text-align:right">' + esc(shortWallet) + '</div><div style="text-align:right">' + esc(shortCmp) + '</div><div style="text-align:right">DIFFERENCE</div></div>'
      + compareRows.map((r) => {
        const d = r.a - r.b;
        const fmt = (v) => r.money ? '$' + v.toFixed(0) : r.pct ? v.toFixed(1) + '%' : num(Math.round(v));
        return '<div style="display:grid; grid-template-columns:1fr 130px 130px 110px; gap:10px; align-items:center; padding:11px 16px; border-bottom:1px solid rgba(255,255,255,.06); ' + M + '; font-size:12.5px">'
          + '<div style="font-family:\'Inter\',sans-serif; font-size:13px">' + r.metric + '</div>'
          + '<div style="text-align:right">' + fmt(r.a) + '</div>'
          + '<div style="text-align:right; color:#4F8EF7">' + fmt(r.b) + '</div>'
          + '<div style="text-align:right; ' + M + '; font-size:12.5px; color:' + (d >= 0 ? '#C8F542' : '#FF4545') + '">' + (d >= 0 ? '+' : '-') + fmt(Math.abs(d)).replace('-', '') + '</div></div>';
      }).join('')
      + '</div>';
  }

  const advChevron = M + '; font-size:16px; color:rgba(255,255,255,.5); transition:transform .18s ease; transform:rotate(' + (s.advancedOpen ? '90deg' : '0deg') + ')';
  const simChevron = M + '; font-size:16px; color:rgba(255,255,255,.5); transition:transform .18s ease; transform:rotate(' + (s.sizingSimOpen ? '90deg' : '0deg') + ')';

  return '<div>'
    + '<div style="padding:20px 24px 16px; border-bottom:1px solid rgba(255,255,255,.09)">'
    + '<div style="display:flex; align-items:flex-end; justify-content:space-between; gap:20px">'
    + '<div><div style="' + M + '; font-size:10px; letter-spacing:.18em; color:#C8F542">BACKTESTER · PAPER SIM</div>'
    + '<div style="font-family:\'Instrument Serif\',serif; font-size:30px; line-height:1.1; margin-top:5px">Replay a wallet with your own sizing</div>'
    + '<div style="font-size:13px; color:rgba(255,255,255,.55); margin-top:9px; max-width:680px">Every simulated fill is priced with fees and slippage, up to ninety days back.</div></div>'
    + '<div style="' + M + '; font-size:10.5px; color:#0A0D0F; background:#C8F542; border-radius:5px; padding:5px 10px">POLYMARKET</div>'
    + '</div></div>'

    + '<div style="display:grid; grid-template-columns:352px 1fr">'
    + '<div style="border-right:1px solid rgba(255,255,255,.09); padding:18px 20px; display:flex; flex-direction:column; gap:22px">'

    + '<div><div style="' + M + '; font-size:10px; letter-spacing:.16em; color:#C8F542; margin-bottom:9px">01 · WALLET TO COPY</div>'
    + '<input value="' + esc(s.btWallet) + '" ' + T.inp((e) => { T.state.btWallet = e.target.value; T.runBacktestLive(); }, 'btWallet') + ' placeholder="0x…" style="width:100%; box-sizing:border-box; background:#10151A; border:1px solid rgba(255,255,255,.16); border-radius:8px; padding:10px 12px; ' + M + '; font-size:12px; color:#fff; outline:none" />'
    + '<div style="font-size:11.5px; color:rgba(255,255,255,.45); margin-top:7px; line-height:1.5">Paste any Polymarket address — for example from the leaderboard.</div></div>'

    + '<div><div style="' + M + '; font-size:10px; letter-spacing:.16em; color:#C8F542; margin-bottom:9px">02 · STAKE PER COPY</div>'
    + '<div style="display:grid; grid-template-columns:1fr 1fr; gap:6px">'
    + Object.keys(SIZING).map((k) =>
      '<div ' + T.act(bt(T, { btSizing: k })) + ' style="font-size:12px; text-align:center; border-radius:7px; padding:8px 6px; cursor:pointer; ' + (s.btSizing === k ? 'color:#0A0D0F; background:#C8F542; font-weight:600' : 'color:rgba(255,255,255,.6); border:1px solid rgba(255,255,255,.16)') + '">' + SIZING[k] + '</div>'
    ).join('')
    + '</div>'
    + '<div style="margin-top:12px"><div style="' + LBL95 + '">' + stakeLabel + '</div>'
    + '<div style="display:flex; align-items:center; gap:8px">'
    + '<div ' + T.act(bt(T, stakeDown)) + ' class="hv-bd35w" style="width:32px; height:34px; flex:none; border:1px solid rgba(255,255,255,.16); border-radius:8px; display:flex; align-items:center; justify-content:center; ' + M + '; font-size:15px; color:rgba(255,255,255,.7); cursor:pointer">−</div>'
    + '<div style="flex:1; background:#10151A; border:1px solid rgba(255,255,255,.16); border-radius:8px; padding:8px 12px; ' + M + '; font-size:13px; text-align:center">' + esc(stakeValue) + '</div>'
    + '<div ' + T.act(bt(T, stakeUp)) + ' class="hv-bd35w" style="width:32px; height:34px; flex:none; border:1px solid rgba(255,255,255,.16); border-radius:8px; display:flex; align-items:center; justify-content:center; ' + M + '; font-size:15px; color:rgba(255,255,255,.7); cursor:pointer">+</div></div>'
    + '<div style="font-size:11.5px; color:rgba(255,255,255,.45); margin-top:7px; line-height:1.5">' + stakeHint + '</div></div>'
    + '<div style="display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-top:14px">'
    + stepRow('CAP PER TRADE', '$' + s.btCap, { btCap: Math.max(10, s.btCap - 50) }, { btCap: s.btCap + 50 })
    + stepRow('MAX BANKROLL IN OPEN COPIES', s.btExposure + '%', { btExposure: Math.max(5, s.btExposure - 5) }, { btExposure: Math.min(100, s.btExposure + 5) })
    + '</div>'
    + '<div style="font-size:11.5px; color:rgba(255,255,255,.45); margin-top:7px; line-height:1.5">New copies are skipped while open copies already tie up that share of the bankroll. Sells free the room up again.</div></div>'

    + '<div><div style="' + M + '; font-size:10px; letter-spacing:.16em; color:#C8F542; margin-bottom:9px">03 · TIME WINDOW</div>'
    + '<div style="display:flex; gap:7px">'
    + [T.tab('7d', s.btWindow === 7, bt(T, { btWindow: 7 })), T.tab('30d', s.btWindow === 30, bt(T, { btWindow: 30 })), T.tab('90d', s.btWindow === 90, bt(T, { btWindow: 90 }))].join('')
    + '</div></div>'

    + '<div><div style="' + M + '; font-size:10px; letter-spacing:.16em; color:#C8F542; margin-bottom:9px">04 · STRATEGY</div>'
    + '<div style="display:flex; gap:7px">'
    + [T.tab('Copy', s.btStrategy === 'copy', bt(T, { btStrategy: 'copy' })), T.tab('Fade', s.btStrategy === 'fade', bt(T, { btStrategy: 'fade' }))].join('')
    + '</div>'
    + '<div style="font-size:11.5px; color:rgba(255,255,255,.45); margin-top:7px; line-height:1.5">' + (s.btStrategy === 'copy' ? 'Mirror every trade the wallet makes, at the same price.' : 'Fade takes the opposite side of every trade the wallet makes.') + '</div></div>'

    + '<div style="border:1px solid rgba(255,255,255,.09); border-radius:10px; overflow:hidden">'
    + '<div ' + T.act(() => T.setState({ advancedOpen: !s.advancedOpen })) + ' class="hv-el" style="display:flex; align-items:center; justify-content:space-between; padding:11px 14px; background:#10151A; cursor:pointer">'
    + '<div style="font-size:13px">Advanced settings</div><div style="' + advChevron + '">›</div></div>'
    + (s.advancedOpen ?
      '<div style="padding:14px; display:flex; flex-direction:column; gap:13px">'
      + stepRow('BANKROLL', '$' + num(s.btBankroll), { btBankroll: Math.max(100, s.btBankroll - 500) }, { btBankroll: s.btBankroll + 500 })
      + '<div style="display:grid; grid-template-columns:1fr 1fr; gap:10px">'
      + stepRow('FEE (BPS)', s.btFee + ' bps', { btFee: Math.max(0, s.btFee - 5) }, { btFee: s.btFee + 5 })
      + stepRow('SLIPPAGE (BPS)', s.btSlip + ' bps', { btSlip: Math.max(0, s.btSlip - 5) }, { btSlip: s.btSlip + 5 })
      + '</div>'
      + '<div><div style="' + LBL95 + '">COMPARE WALLET (OPTIONAL)</div>'
      + '<input value="' + esc(s.btCompare) + '" ' + T.inp((e) => { T.state.btCompare = e.target.value; T.runBacktestLive(); }, 'btCompare') + ' placeholder="0x…" style="width:100%; box-sizing:border-box; background:#10151A; border:1px solid rgba(255,255,255,.16); border-radius:7px; padding:8px 10px; ' + M + '; font-size:11.5px; color:#fff; outline:none" />'
      + '<div style="font-size:11.5px; color:rgba(255,255,255,.45); margin-top:7px; line-height:1.5">Benchmark in the results is the same trades at a constant 2% of the starting bankroll per copy.</div></div>'
      + '</div>' : '')
    + '</div>'

    + '<div ' + T.act(() => { T.setState({ btTab: 'log' }); T.runBacktestLive(); }) + ' class="hv-limebg" style="font-size:13.5px; font-weight:600; text-align:center; color:#0A0D0F; background:#C8F542; border-radius:8px; padding:12px; cursor:pointer">Run backtest →</div>'
    + '</div>'

    + '<div style="padding:18px 24px">'
    + '<div style="' + M + '; font-size:11.5px; color:rgba(255,255,255,.6)">' + esc(runMeta) + '</div>'

    + '<div style="display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin-top:14px">'
    + statCards.map((c) =>
      '<div style="background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:10px; padding:14px 16px">'
      + '<div style="' + M + '; font-size:9.5px; letter-spacing:.13em; color:rgba(255,255,255,.45)">' + c.label + '</div>'
      + '<div style="' + M + '; font-size:22px; margin-top:7px; color:' + (c.pos === true ? '#C8F542' : c.pos === false ? '#FF4545' : '#ffffff') + '">' + c.value + '</div>'
      + '<div style="' + M + '; font-size:11px; margin-top:5px; color:rgba(255,255,255,.45)">' + c.sub + '</div></div>'
    ).join('')
    + '</div>'

    + (skippedN > copied ? '<div style="border:1px solid rgba(245,166,35,.3); background:rgba(245,166,35,.07); border-radius:10px; padding:12px 15px; margin-top:12px; font-size:12.5px; color:#F5A623; line-height:1.5">Why so many skips: ' + Math.round(skippedN * 0.6) + ' hit the exposure cap (' + s.btExposure + '%), ' + Math.round(skippedN * 0.3) + ' ran out of cash, ' + Math.round(skippedN * 0.1) + ' were sells of positions you never copied. Raise the exposure cap or lower the stake to copy more of the flow.</div>' : '')

    + '<div style="background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:12px; margin-top:14px; padding:16px 18px">'
    + '<div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:12px; flex-wrap:wrap; gap:10px">'
    + '<div style="' + M + '; font-size:10.5px; letter-spacing:.14em; color:rgba(255,255,255,.55)">EQUITY CURVE</div>'
    + '<div style="display:flex; gap:16px; ' + M + '; font-size:10.5px; flex-wrap:wrap">'
    + '<span style="display:flex; align-items:center; gap:6px"><span style="width:14px; height:2px; background:#C8F542; display:inline-block"></span>' + esc(shortWallet) + '</span>'
    + '<span style="display:flex; align-items:center; gap:6px; color:rgba(255,255,255,.5)"><span style="width:14px; height:2px; background:#95A0AB; display:inline-block"></span>Flat-bet benchmark</span>'
    + (s.sizingSimOpen ? '<span style="display:flex; align-items:center; gap:6px; color:#F5A623"><span style="width:14px; height:2px; background:#F5A623; display:inline-block"></span>Best sizing: ' + esc(bestVariant.name) + '</span>' : '')
    + '</div></div>'
    + '<svg width="100%" height="270" viewBox="0 0 900 270" preserveAspectRatio="none">'
    + '<line x1="0" y1="20" x2="900" y2="20" stroke="rgba(255,255,255,.07)" />'
    + '<line x1="0" y1="80" x2="900" y2="80" stroke="rgba(255,255,255,.07)" />'
    + '<line x1="0" y1="140" x2="900" y2="140" stroke="rgba(255,255,255,.07)" />'
    + '<line x1="0" y1="200" x2="900" y2="200" stroke="rgba(255,255,255,.07)" />'
    + '<line x1="0" y1="258" x2="900" y2="258" stroke="rgba(255,255,255,.14)" />'
    + '<polyline points="' + benchPts + '" fill="none" stroke="#95A0AB" stroke-width="1.4" stroke-dasharray="6 4" />'
    + (cmp ? '<polyline points="' + cmp.pts + '" fill="none" stroke="#4F8EF7" stroke-width="2" />' : '')
    + (s.sizingSimOpen && !live ? '<polyline points="' + best.pts + '" fill="none" stroke="#F5A623" stroke-width="2" stroke-dasharray="2 4" />' : '')
    + '<polyline points="' + equityPts + '" fill="none" stroke="' + (ret >= 0 ? '#C8F542' : '#FF4545') + '" stroke-width="2" />'
    + '</svg>'
    + '<div style="display:flex; justify-content:space-between; ' + M + '; font-size:10px; color:rgba(255,255,255,.4); margin-top:8px">'
    + '<span>' + s.btWindow + 'd ago</span><span>' + Math.round(s.btWindow / 2) + 'd ago</span><span>today</span></div></div>'

    + '<div style="display:flex; gap:6px; margin-top:16px">' + btTabs + '</div>'
    + tabBody

    + '<div style="border:1px solid rgba(255,255,255,.09); border-radius:12px; margin-top:16px; overflow:hidden">'
    + '<div ' + T.act(() => { T.setState({ sizingSimOpen: !s.sizingSimOpen }); if (!s.sizingSimOpen) T.runBacktestLive(); }) + ' class="hv-el" style="display:flex; align-items:center; justify-content:space-between; padding:13px 18px; background:#10151A; cursor:pointer">'
    + '<div style="font-size:14px">Which sizing would have been best for this wallet?</div><div style="' + simChevron + '">›</div></div>'
    + (s.sizingSimOpen ?
      '<div style="padding:16px 18px">'
      + '<div style="font-size:12.5px; color:rgba(255,255,255,.55); line-height:1.5">Replays the same window once per sizing rule — identical fees, slippage, cap and exposure limit. Only the stake rule changes. The winner is drawn into the chart above as the dotted amber line.</div>'
      + '<div style="font-size:13px; margin-top:12px">Best for this wallet and window: <strong style="color:#F5A623">' + esc(bestVariant.name) + '</strong> → $' + bestVariant.eq.toFixed(0) + ' final equity (' + (bestVariant.roi >= 0 ? '+' : '') + bestVariant.roi.toFixed(1) + '% ROI)</div>'
      + '<div style="border:1px solid rgba(255,255,255,.09); border-radius:10px; margin-top:14px; overflow:hidden">'
      + '<div style="display:grid; grid-template-columns:1fr 110px 96px 96px 96px 88px 88px; gap:10px; padding:9px 14px; background:#10151A; border-bottom:1px solid rgba(255,255,255,.09); ' + M + '; font-size:9px; letter-spacing:.12em; color:rgba(255,255,255,.45)">'
      + '<div>SIZING RULE</div><div style="text-align:right">FINAL EQUITY</div><div style="text-align:right">ROI</div><div style="text-align:right">MAX DD</div><div style="text-align:right">WIN RATE</div><div style="text-align:right">COPIED</div><div style="text-align:right">SKIPPED</div></div>'
      + simVariants.map((v, i) =>
        '<div style="display:grid; grid-template-columns:1fr 110px 96px 96px 96px 88px 88px; gap:10px; align-items:center; padding:10px 14px; border-bottom:1px solid rgba(255,255,255,.06); background:' + (i === 0 ? 'rgba(245,166,35,.07)' : 'transparent') + '">'
        + '<div style="font-size:12.5px; color:' + (i === 0 ? '#F5A623' : '#ffffff') + '">' + esc(v.name) + '</div>'
        + '<div style="text-align:right; ' + M + '; font-size:12.5px">$' + v.eq.toFixed(0) + '</div>'
        + '<div style="text-align:right; ' + M + '; font-size:12.5px; color:' + (v.roi >= 0 ? '#C8F542' : '#FF4545') + '">' + (v.roi >= 0 ? '+' : '') + v.roi.toFixed(1) + '%</div>'
        + '<div style="text-align:right; ' + M + '; font-size:12.5px; color:rgba(255,255,255,.6)">' + v.dd.toFixed(1) + '%</div>'
        + '<div style="text-align:right; ' + M + '; font-size:12.5px; color:rgba(255,255,255,.6)">' + Math.round(v.wr) + '%</div>'
        + '<div style="text-align:right; ' + M + '; font-size:12.5px; color:rgba(255,255,255,.6)">' + num(v.copied) + '</div>'
        + '<div style="text-align:right; ' + M + '; font-size:12.5px; color:rgba(255,255,255,.6)">' + num(Math.max(0, v.skipped)) + '</div></div>'
      ).join('')
      + '</div></div>' : '')
    + '</div>'

    + '<div style="display:flex; gap:10px; margin-top:16px">'
    + '<div class="hv-bd35" style="font-size:13px; color:#fff; border:1px solid rgba(255,255,255,.2); border-radius:8px; padding:10px 16px; cursor:pointer">Mirror this on paper</div>'
    + '<div class="hv-bd35" style="font-size:13px; color:#fff; border:1px solid rgba(255,255,255,.2); border-radius:8px; padding:10px 16px; cursor:pointer">Save this setup</div>'
    + '</div>'
    + '</div></div></div>';
}

// ---------------------------------------------------------------- copy trade
export function renderCopy(T) {
  const s = T.state;
  const live = T.liveData.copy;
  const st = live && live.status ? live.status : { running: s.daemonOn, source: '0x204f…5e14 · Swisstony', scale: 0.42, cash: 312.40, auto_topup: false };
  const kp = live && live.kpis ? live.kpis : { equity: 1043.18, contributions: 1000.00, pnl: 43.18, source_return_pct: 5.9, mirrored: 214, total: 231, skipped: 17, fidelity: 96, config_fidelity: 98, exec_fidelity: 94 };
  const orders = live && live.orders ? live.orders : T.copyOrders;
  const positions = live && live.positions ? live.positions : DEMO_COPY_POSITIONS;
  const cashRows = live && live.cash_events ? live.cash_events : DEMO_CASH_ROWS;
  const equityPts = live && live.equity_curve && live.equity_curve.length > 1 ? T.seriesPoints(live.equity_curve, 760, 240) : T.curve(4711, 60, 760, 240, 0.9, 3.4).pts;
  const srcPts = live && live.source_curve && live.source_curve.length > 1 ? T.seriesPoints(live.source_curve, 900, 200) : T.curve(4712, 60, 900, 200, 1.05, 3.0).pts;
  const minePts = live && live.equity_curve && live.equity_curve.length > 1 ? T.seriesPoints(live.equity_curve, 900, 200) : T.curve(4713, 60, 900, 200, 0.92, 3.2).pts;

  const copyTabs = [['orders','Orders'],['positions','Positions'],['perf','Performance'],['fidelity','Copy fidelity'],['cash','Cash events']].map((o) => T.tab(o[1], s.copyTab === o[0], { copyTab: o[0] })).join('');

  let body = '';
  if (s.copyTab === 'orders') {
    const rows = orders.filter((o) => {
      if (s.copyStatus2 !== 'all' && o.status !== s.copyStatus2) return false;
      if (s.copySide !== 'all' && o.side.indexOf(s.copySide) !== 0) return false;
      if (s.copyMin !== 'all' && Number(String(o.theirs).replace(/[$,]/g, '')) < Number(s.copyMin)) return false;
      if (s.copyQuery.trim() && o.market.toLowerCase().indexOf(s.copyQuery.trim().toLowerCase()) < 0) return false;
      return true;
    });
    body = '<div>'
      + '<div style="padding:14px 24px 0; display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:14px 18px">'
      + '<div><div style="' + LBL9 + '">SEARCH</div><input value="' + esc(s.copyQuery) + '" ' + T.inp((e) => T.setState({ copyQuery: e.target.value }), 'copyQuery') + ' placeholder="market or transaction…" style="width:100%; box-sizing:border-box; background:#10151A; border:1px solid rgba(255,255,255,.16); border-radius:7px; padding:8px 10px; ' + M + '; font-size:11.5px; color:#fff; outline:none" /></div>'
      + '<div><div style="' + LBL9 + '">SIDE</div><div style="display:flex; gap:6px; flex-wrap:wrap">'
      + [['all','All'],['BUY','Buys'],['SELL','Sells']].map((o) => T.opt(o[1], s.copySide === o[0], { copySide: o[0] })).join('') + '</div></div>'
      + '<div><div style="' + LBL9 + '">STATUS</div><div style="display:flex; gap:6px; flex-wrap:wrap">'
      + [['all','All'],['copied','Copied'],['baseline','Baseline'],['skipped','Skipped']].map((o) => T.opt(o[1], s.copyStatus2 === o[0], { copyStatus2: o[0] })).join('') + '</div></div>'
      + '<div><div style="' + LBL9 + '">MINIMUM SIZE THEY TRADED</div><div style="display:flex; gap:6px; flex-wrap:wrap">'
      + [['all','Any'],['5000','>$5k'],['10000','>$10k'],['15000','>$15k']].map((o) => T.opt(o[1], s.copyMin === o[0], { copyMin: o[0] })).join('') + '</div></div>'
      + '</div>'
      + '<div style="border:1px solid rgba(255,255,255,.09); border-radius:12px; margin:14px 24px; overflow:hidden">'
      + '<div style="display:grid; grid-template-columns:92px 1fr 78px 96px 96px 92px 110px; gap:10px; padding:9px 16px; background:#10151A; border-bottom:1px solid rgba(255,255,255,.09); ' + M + '; font-size:9px; letter-spacing:.12em; color:rgba(255,255,255,.45)">'
      + '<div>TIME</div><div>MARKET</div><div style="text-align:right">SIDE</div><div style="text-align:right">THEY SPENT</div><div style="text-align:right">YOU SPENT</div><div style="text-align:right">LATENCY</div><div style="text-align:right">STATUS</div></div>'
      + rows.map((o, i) =>
        '<div style="display:grid; grid-template-columns:92px 1fr 78px 96px 96px 92px 110px; gap:10px; align-items:center; padding:11px 16px; border-bottom:1px solid rgba(255,255,255,.06)">'
        + '<div style="' + M + '; font-size:12px; color:rgba(255,255,255,.55)">' + esc(o.time) + '</div>'
        + '<div style="font-family:\'Inter\',sans-serif; font-size:12.5px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis">' + esc(o.market) + '</div>'
        + '<div style="' + M + '; font-size:12px; text-align:right; color:' + (o.side.indexOf('BUY') === 0 ? '#C8F542' : '#FF4545') + '">' + esc(o.side) + '</div>'
        + '<div style="' + M + '; font-size:12px; text-align:right; color:rgba(255,255,255,.55)">' + esc(o.theirs) + '</div>'
        + '<div style="' + M + '; font-size:12px; text-align:right">' + esc(o.yours) + '</div>'
        + '<div style="' + M + '; font-size:12px; text-align:right; color:rgba(255,255,255,.55)">' + (o.latency_ms != null ? o.latency_ms + ' ms' : (900 + i * 140) + ' ms') + '</div>'
        + '<div style="' + M + '; font-size:11px; text-align:right; color:' + (o.status === 'copied' ? '#C8F542' : o.status === 'skipped' ? '#F5A623' : 'rgba(255,255,255,.6)') + '">' + esc(o.status.toUpperCase()) + '</div></div>'
      ).join('')
      + '</div></div>';
  } else if (s.copyTab === 'positions') {
    body = '<div style="border:1px solid rgba(255,255,255,.09); border-radius:12px; margin:14px 24px; overflow:hidden">'
      + '<div style="display:grid; grid-template-columns:1fr 62px 78px 78px 78px 88px 100px; gap:10px; padding:9px 16px; background:#10151A; border-bottom:1px solid rgba(255,255,255,.09); ' + M + '; font-size:9px; letter-spacing:.12em; color:rgba(255,255,255,.45)">'
      + '<div>MARKET</div><div style="text-align:right">SIDE</div><div style="text-align:right">SHARES</div><div style="text-align:right">AVG FILL</div><div style="text-align:right">MARK</div><div style="text-align:right">VALUE</div><div style="text-align:right">UNREALISED</div></div>'
      + positions.map((r) =>
        '<div style="display:grid; grid-template-columns:1fr 62px 78px 78px 78px 88px 100px; gap:10px; align-items:center; padding:11px 16px; border-bottom:1px solid rgba(255,255,255,.06)">'
        + r.map((v, i) => {
          const style = i === 0 ? "font-family:'Inter',sans-serif; font-size:12.5px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis" : M + '; font-size:12px; text-align:right; color:' + (i === 6 ? (String(v).charAt(0) === '+' ? '#C8F542' : '#FF4545') : i === 1 ? (v === 'Yes' ? '#C8F542' : '#4F8EF7') : 'rgba(255,255,255,.75)');
          return '<div style="' + style + '">' + esc(String(v)) + '</div>';
        }).join('')
        + '</div>'
      ).join('')
      + '</div>';
  } else if (s.copyTab === 'perf') {
    body = '<div style="padding:16px 24px">'
      + '<div style="background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:12px; padding:16px 18px">'
      + '<div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:12px; flex-wrap:wrap; gap:10px">'
      + '<div style="' + M + '; font-size:10.5px; letter-spacing:.14em; color:rgba(255,255,255,.55)">EQUITY VS CASH PUT IN</div>'
      + '<div style="display:flex; gap:14px; ' + M + '; font-size:10.5px">'
      + '<span style="display:flex; align-items:center; gap:6px"><span style="width:14px; height:2px; background:#C8F542; display:inline-block"></span>Your paper equity</span>'
      + '<span style="display:flex; align-items:center; gap:6px; color:rgba(255,255,255,.5)"><span style="width:14px; height:2px; background:rgba(255,255,255,.35); display:inline-block"></span>Cash put in</span>'
      + '</div></div>'
      + '<svg width="100%" height="240" viewBox="0 0 900 240" preserveAspectRatio="none">'
      + '<line x1="0" y1="20" x2="900" y2="20" stroke="rgba(255,255,255,.07)" />'
      + '<line x1="0" y1="80" x2="900" y2="80" stroke="rgba(255,255,255,.07)" />'
      + '<line x1="0" y1="140" x2="900" y2="140" stroke="rgba(255,255,255,.07)" />'
      + '<line x1="0" y1="230" x2="900" y2="230" stroke="rgba(255,255,255,.14)" />'
      + '<polyline points="0,190 900,190" fill="none" stroke="rgba(255,255,255,.35)" stroke-width="1.5" stroke-dasharray="5 4" />'
      + '<polyline points="' + equityPts + '" fill="none" stroke="#C8F542" stroke-width="2" /></svg></div>'
      + '<div style="background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:12px; padding:16px 18px; margin-top:14px">'
      + '<div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:12px; flex-wrap:wrap; gap:10px">'
      + '<div style="' + M + '; font-size:10.5px; letter-spacing:.14em; color:rgba(255,255,255,.55)">YOUR RETURN VERSUS THE SOURCE WALLET</div>'
      + '<div style="display:flex; gap:14px; ' + M + '; font-size:10.5px">'
      + '<span style="display:flex; align-items:center; gap:6px"><span style="width:14px; height:2px; background:#C8F542; display:inline-block"></span>You</span>'
      + '<span style="display:flex; align-items:center; gap:6px; color:#4F8EF7"><span style="width:14px; height:2px; background:#4F8EF7; display:inline-block"></span>Swisstony</span>'
      + '</div></div>'
      + '<svg width="100%" height="200" viewBox="0 0 900 200" preserveAspectRatio="none">'
      + '<line x1="0" y1="20" x2="900" y2="20" stroke="rgba(255,255,255,.07)" />'
      + '<line x1="0" y1="100" x2="900" y2="100" stroke="rgba(255,255,255,.07)" />'
      + '<line x1="0" y1="190" x2="900" y2="190" stroke="rgba(255,255,255,.14)" />'
      + '<polyline points="' + srcPts + '" fill="none" stroke="#4F8EF7" stroke-width="2" />'
      + '<polyline points="' + minePts + '" fill="none" stroke="#C8F542" stroke-width="2" /></svg></div>'
      + '</div>';
  } else if (s.copyTab === 'fidelity') {
    const fid = live && live.fidelity_detail;
    let gapCosts;
    if (fid && fid.execution) {
      const skips = Object.entries(fid.execution.lost_to_skips || {}).sort((a, b) => b[1] - a[1]);
      const clamps = +fid.execution.lost_to_clamps || 0;
      const total = skips.reduce((a, kv) => a + (+kv[1] || 0), 0) + clamps;
      gapCosts = skips.map(([reason, value]) =>
        '<div style="display:flex; justify-content:space-between; font-size:13px"><span style="color:rgba(255,255,255,.7)">Skipped: ' + esc(reason) + '</span><span style="' + M + '; color:#FF4545">-$' + (+value).toFixed(2) + '</span></div>'
      ).join('')
        + '<div style="display:flex; justify-content:space-between; font-size:13px"><span style="color:rgba(255,255,255,.7)">Clamped (cash throttle / order cap)</span><span style="' + M + '; color:rgba(255,255,255,.6)">-$' + clamps.toFixed(2) + '</span></div>'
        + '<div style="display:flex; justify-content:space-between; font-size:13px; border-top:1px solid rgba(255,255,255,.09); padding-top:11px"><span>Total drag (24h)</span><span style="' + M + '; color:#FF4545">-$' + total.toFixed(2) + '</span></div>';
    } else {
      gapCosts = '<div style="display:flex; justify-content:space-between; font-size:13px"><span style="color:rgba(255,255,255,.7)">Skipped for lack of cash</span><span style="' + M + '; color:#FF4545">-$11.40</span></div>'
        + '<div style="display:flex; justify-content:space-between; font-size:13px"><span style="color:rgba(255,255,255,.7)">Filled at a worse price</span><span style="' + M + '; color:#FF4545">-$4.20</span></div>'
        + '<div style="display:flex; justify-content:space-between; font-size:13px"><span style="color:rgba(255,255,255,.7)">Rounded position sizes</span><span style="' + M + '; color:rgba(255,255,255,.6)">-$0.90</span></div>'
        + '<div style="display:flex; justify-content:space-between; font-size:13px; border-top:1px solid rgba(255,255,255,.09); padding-top:11px"><span>Total drag</span><span style="' + M + '; color:#FF4545">-$16.50</span></div>';
    }
    const throttleShare = fid && fid.execution && kp.total ? Math.round((kp.skipped / Math.max(1, kp.total)) * 100) : 7;
    body = '<div style="padding:16px 24px; display:grid; grid-template-columns:1fr 1fr; gap:16px">'
      + '<div><div style="' + M + '; font-size:10.5px; letter-spacing:.14em; color:rgba(255,255,255,.55); margin-bottom:14px">WHERE THE COPY DRIFTS</div>'
      + '<div style="display:flex; flex-direction:column; gap:14px">'
      + fidelityBar('Settings vs a neutral mirror', kp.config_fidelity + '%', Math.min(100, kp.config_fidelity), '#C8F542')
      + fidelityBar('Filled vs what you wanted', kp.exec_fidelity + '%', Math.min(100, kp.exec_fidelity), '#C8F542')
      + fidelityBar('Orders skipped', throttleShare + '% of orders', Math.min(100, throttleShare), '#F5A623', '#F5A623')
      + '</div></div>'
      + '<div><div style="' + M + '; font-size:10.5px; letter-spacing:.14em; color:rgba(255,255,255,.55); margin-bottom:14px">WHAT THE GAP COSTS</div>'
      + '<div style="display:flex; flex-direction:column; gap:11px">' + gapCosts + '</div></div></div>';
  } else {
    body = '<div style="border:1px solid rgba(255,255,255,.09); border-radius:12px; margin:14px 24px; overflow:hidden">'
      + '<div style="display:grid; grid-template-columns:110px 1fr 120px 120px; gap:10px; padding:9px 16px; background:#10151A; border-bottom:1px solid rgba(255,255,255,.09); ' + M + '; font-size:9px; letter-spacing:.12em; color:rgba(255,255,255,.45)">'
      + '<div>DATE</div><div>WHAT HAPPENED</div><div style="text-align:right">AMOUNT</div><div style="text-align:right">CASH AFTER</div></div>'
      + cashRows.map((r) =>
        '<div style="display:grid; grid-template-columns:110px 1fr 120px 120px; gap:10px; align-items:center; padding:11px 16px; border-bottom:1px solid rgba(255,255,255,.06)">'
        + r.map((v, i) => {
          const style = i === 1 ? "font-family:'Inter',sans-serif; font-size:12.5px" : M + '; font-size:12px; text-align:' + (i === 0 ? 'left' : 'right') + '; color:' + (i === 2 && v !== '+$0.00' ? '#C8F542' : 'rgba(255,255,255,.75)');
          return '<div style="' + style + '">' + esc(String(v)) + '</div>';
        }).join('')
        + '</div>'
      ).join('')
      + '</div>';
  }

  const daemonOn = st.running != null ? !!st.running : s.daemonOn;
  return '<div>'
    + '<div style="padding:20px 24px 16px; border-bottom:1px solid rgba(255,255,255,.09)">'
    + '<div style="' + M + '; font-size:10px; letter-spacing:.18em; color:#C8F542">COPY TRADE · PAPER</div>'
    + '<div style="font-family:\'Instrument Serif\',serif; font-size:30px; line-height:1.1; margin-top:5px">Mirror a wallet with fake money</div>'
    + '<div style="font-size:13px; color:rgba(255,255,255,.55); margin-top:9px; max-width:700px">Every buy the source wallet makes is scaled to your sub-account and booked at the printed price. Nothing is sent to a venue.</div></div>'

    + '<div style="display:flex; align-items:center; gap:26px; padding:13px 24px; border-bottom:1px solid rgba(255,255,255,.09); background:#10151A">'
    + '<div style="display:flex; align-items:center; gap:8px">'
    + '<span style="width:7px; height:7px; border-radius:50%; background:' + (daemonOn ? '#C8F542' : '#F5A623') + '; display:inline-block; animation:livePulse 1.6s ease-in-out infinite"></span>'
    + '<span style="' + M + '; font-size:11px; letter-spacing:.14em; color:' + (daemonOn ? '#C8F542' : '#F5A623') + '">' + (daemonOn ? 'RUNNING' : 'STOPPED') + '</span></div>'
    + '<div style="' + M + '; font-size:11.5px; color:rgba(255,255,255,.6)">SOURCE <span style="color:#fff">' + esc(st.source) + '</span></div>'
    + '<div style="' + M + '; font-size:11.5px; color:rgba(255,255,255,.6)">SCALE <span style="color:#fff">' + (+st.scale).toFixed(2) + '×</span></div>'
    + '<div style="' + M + '; font-size:11.5px; color:rgba(255,255,255,.6)">CASH LEFT <span style="color:#fff">$' + (+st.cash).toFixed(2) + '</span></div>'
    + '<div style="' + M + '; font-size:11px; color:#F5A623; border:1px solid rgba(245,166,35,.35); border-radius:5px; padding:3px 8px">AUTO TOP-UP ' + (st.auto_topup ? 'ON' : 'OFF') + '</div>'
    + '</div>'

    + '<div style="display:grid; grid-template-columns:repeat(4,1fr); border-bottom:1px solid rgba(255,255,255,.09)">'
    + '<div style="padding:16px 20px; border-right:1px solid rgba(255,255,255,.09)"><div style="' + M + '; font-size:10px; letter-spacing:.14em; color:rgba(255,255,255,.45)">SUB-ACCOUNT EQUITY</div><div style="' + M + '; font-size:26px; margin-top:8px">$' + num((+kp.equity).toFixed(2)) + '</div><div style="' + M + '; font-size:11px; color:rgba(255,255,255,.45); margin-top:4px">$' + num((+kp.contributions).toFixed(2)) + ' put in</div></div>'
    + '<div style="padding:16px 20px; border-right:1px solid rgba(255,255,255,.09)"><div style="' + M + '; font-size:10px; letter-spacing:.14em; color:rgba(255,255,255,.45)">PROFIT ON PAPER</div><div style="' + M + '; font-size:26px; margin-top:8px; color:' + (kp.pnl >= 0 ? '#C8F542' : '#FF4545') + '">' + (kp.pnl >= 0 ? '+' : '-') + '$' + Math.abs(kp.pnl).toFixed(2) + '</div><div style="' + M + '; font-size:11px; color:rgba(255,255,255,.45); margin-top:4px">' + (kp.source_pnl_delta != null ? 'source wallet ' + (kp.source_pnl_delta >= 0 ? '+' : '-') + '$' + num(Math.abs(kp.source_pnl_delta).toFixed(0)) + ' same window' : 'source wallet +' + (+kp.source_return_pct).toFixed(1) + '% same window') + '</div></div>'
    + '<div style="padding:16px 20px; border-right:1px solid rgba(255,255,255,.09)"><div style="' + M + '; font-size:10px; letter-spacing:.14em; color:rgba(255,255,255,.45)">ORDERS MIRRORED</div><div style="' + M + '; font-size:26px; margin-top:8px">' + kp.mirrored + ' <span style="font-size:15px; color:rgba(255,255,255,.45)">/ ' + kp.total + '</span></div><div style="' + M + '; font-size:11px; color:#F5A623; margin-top:4px">' + kp.skipped + ' skipped — no cash</div></div>'
    + '<div style="padding:16px 20px"><div style="' + M + '; font-size:10px; letter-spacing:.14em; color:rgba(255,255,255,.45)">HOW CLOSE TO THE SOURCE</div><div style="' + M + '; font-size:26px; margin-top:8px">' + kp.fidelity + '%</div><div style="' + M + '; font-size:11px; color:rgba(255,255,255,.45); margin-top:4px">config ' + kp.config_fidelity + '% · execution ' + kp.exec_fidelity + '%</div></div>'
    + '</div>'

    + '<div style="display:flex; align-items:center; gap:8px; padding:14px 24px; border-bottom:1px solid rgba(255,255,255,.09); flex-wrap:wrap">'
    + '<div class="hv-limebg" style="font-size:12.5px; font-weight:600; color:#0A0D0F; background:#C8F542; border-radius:7px; padding:8px 14px; cursor:pointer">Sync now</div>'
    + '<div class="hv-bd35" style="font-size:12.5px; color:#fff; border:1px solid rgba(255,255,255,.2); border-radius:7px; padding:8px 14px; cursor:pointer">Seed baseline</div>'
    + '<div ' + T.act(() => T.setState({ daemonOn: !s.daemonOn })) + ' style="font-size:12.5px; border-radius:7px; padding:8px 14px; cursor:pointer; ' + (daemonOn ? 'color:#FF7A7A; border:1px solid rgba(255,69,69,.35)' : 'color:#0A0D0F; background:#C8F542; font-weight:600') + '">' + (daemonOn ? 'Stop the copier' : 'Start the copier') + '</div>'
    + '<div class="hv-bd35" style="font-size:12.5px; color:#fff; border:1px solid rgba(255,255,255,.2); border-radius:7px; padding:8px 14px; cursor:pointer">Export CSV</div>'
    + '<div style="' + M + '; font-size:11px; color:rgba(255,255,255,.4); margin-left:6px">' + (daemonOn ? 'Running · last sync 40 s ago · next in 20 s' : 'Stopped · nothing is being mirrored') + '</div>'
    + '</div>'

    + '<div style="display:flex; gap:6px; padding:16px 24px 0; flex-wrap:wrap">' + copyTabs + '</div>'
    + body
    + '</div>';
}

function fidelityBar(label, valueLabel, pct, color, valueColor) {
  return '<div>'
    + '<div style="display:flex; justify-content:space-between; font-size:12.5px; margin-bottom:6px"><span style="color:rgba(255,255,255,.7)">' + label + '</span><span style="' + M + (valueColor ? '; color:' + valueColor : '') + '">' + valueLabel + '</span></div>'
    + '<div style="height:7px; background:rgba(255,255,255,.07); border-radius:2px"><div style="width:' + pct + '%; height:7px; background:' + color + '; border-radius:2px"></div></div></div>';
}

// ---------------------------------------------------------------- portfolio
export function renderPortfolio(T) {
  const s = T.state;
  const live = T.liveData.copy;
  const kp = live && live.kpis ? live.kpis : { equity: 1043.18, cash: 312.40, unrealized: 28.60, open_positions: 14 };
  const equityPts = live && live.equity_curve && live.equity_curve.length > 1 ? T.seriesPoints(live.equity_curve, 900, 220) : T.curve(4711, 60, 900, 220, 0.9, 3.4).pts;
  const watch = trackWatchRows(T);
  // Live-Positionen des Copy-Traders in die Portfolio-Zeilen [Markt, Seite, Entry, Now, Profit, Quelle]
  const livePortRows = live && live.positions && live.positions.length ? live.positions.map((r) => [
    r[0], String(r[1] || 'Yes').toUpperCase(),
    Math.round(parseFloat(r[3]) * 100) + '¢', Math.round(parseFloat(r[4]) * 100) + '¢',
    r[6], 'copy'
  ]) : null;
  const liveHistRows = live && live.history && live.history.length ? live.history : null;

  const portTabs = [['positions','Positions'],['copy','Copy equity'],['exposure','Exposure'],['history','History'],['watchlist','Watchlist']].map((o) => T.tab(o[1], s.portTab === o[0], { portTab: o[0] })).join('');

  let body = '';
  if (s.portTab === 'positions') {
    const baseRows = livePortRows || DEMO_PORT_ROWS;
    const rows = baseRows.filter((r) => (s.portSource === 'all' || r[5] === s.portSource) && (s.portSide === 'all' || r[1] === s.portSide) && (!s.portLosers || r[4].charAt(0) === '-') && (!s.portQuery.trim() || r[0].toLowerCase().indexOf(s.portQuery.trim().toLowerCase()) >= 0));
    body = '<div>'
      + '<div style="padding:14px 24px 0; display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:14px 18px">'
      + '<div><div style="' + LBL9 + '">SEARCH</div><input value="' + esc(s.portQuery) + '" ' + T.inp((e) => T.setState({ portQuery: e.target.value }), 'portQuery') + ' placeholder="market or wallet…" style="width:100%; box-sizing:border-box; background:#10151A; border:1px solid rgba(255,255,255,.16); border-radius:7px; padding:8px 10px; ' + M + '; font-size:11.5px; color:#fff; outline:none" /></div>'
      + '<div><div style="' + LBL9 + '">SOURCE</div><div style="display:flex; gap:6px; flex-wrap:wrap">'
      + [['all','All'],['research','Research'],['copy','Copy trade']].map((o) => T.opt(o[1], s.portSource === o[0], { portSource: o[0] })).join('') + '</div></div>'
      + '<div><div style="' + LBL9 + '">SIDE</div><div style="display:flex; gap:6px; flex-wrap:wrap">'
      + [['all','All'],['YES','Yes'],['NO','No']].map((o) => T.opt(o[1], s.portSide === o[0], { portSide: o[0] })).join('') + '</div></div>'
      + '<div><div style="' + LBL9 + '">SHOW</div><div style="display:flex; gap:6px; flex-wrap:wrap">'
      + [['all','Everything'],['losers','Losing only']].map((o) => T.opt(o[1], (s.portLosers ? 'losers' : 'all') === o[0], { portLosers: o[0] === 'losers' })).join('') + '</div></div>'
      + '</div>'
      + '<div style="border:1px solid rgba(255,255,255,.09); border-radius:12px; margin:14px 24px; overflow:hidden">'
      + '<div style="display:grid; grid-template-columns:1fr 76px 92px 92px 100px 100px; gap:10px; padding:9px 16px; background:#10151A; border-bottom:1px solid rgba(255,255,255,.09); ' + M + '; font-size:9px; letter-spacing:.12em; color:rgba(255,255,255,.45)">'
      + '<div>MARKET</div><div style="text-align:right">SIDE</div><div style="text-align:right">ENTRY</div><div style="text-align:right">NOW</div><div style="text-align:right">PROFIT</div><div style="text-align:right">SOURCE</div></div>'
      + rows.map((r) =>
        '<div style="display:grid; grid-template-columns:1fr 76px 92px 92px 100px 100px; gap:10px; align-items:center; padding:11px 16px; border-bottom:1px solid rgba(255,255,255,.06)">'
        + r.map((v, i) => {
          const style = i === 0 ? "font-family:'Inter',sans-serif; font-size:12.5px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis" : M + '; font-size:12px; text-align:right; color:' + (i === 4 ? (v.charAt(0) === '+' ? '#C8F542' : '#FF4545') : i === 1 ? (v === 'YES' ? '#C8F542' : '#4F8EF7') : 'rgba(255,255,255,.7)');
          return '<div style="' + style + '">' + esc(String(v)) + '</div>';
        }).join('')
        + '</div>'
      ).join('')
      + '</div></div>';
  } else if (s.portTab === 'copy') {
    body = '<div style="padding:16px 24px">'
      + '<div style="display:grid; grid-template-columns:repeat(3,1fr); gap:12px">'
      + '<div style="background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:10px; padding:14px 16px"><div style="' + M + '; font-size:9.5px; letter-spacing:.13em; color:rgba(255,255,255,.45)">COPY EQUITY</div><div style="' + M + '; font-size:21px; margin-top:7px">$' + num((+kp.equity).toFixed(2)) + '</div></div>'
      + '<div style="background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:10px; padding:14px 16px"><div style="' + M + '; font-size:9.5px; letter-spacing:.13em; color:rgba(255,255,255,.45)">RESEARCH CASH</div><div style="' + M + '; font-size:21px; margin-top:7px">$' + (+kp.cash).toFixed(2) + '</div></div>'
      + '<div style="background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:10px; padding:14px 16px"><div style="' + M + '; font-size:9.5px; letter-spacing:.13em; color:rgba(255,255,255,.45)">EVERYTHING TOGETHER</div><div style="' + M + '; font-size:21px; margin-top:7px; color:#C8F542">$' + num(((+kp.equity) + (+kp.cash)).toFixed(2)) + '</div></div>'
      + '</div>'
      + '<div style="background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:12px; padding:16px 18px; margin-top:14px">'
      + '<div style="' + M + '; font-size:10.5px; letter-spacing:.14em; color:rgba(255,255,255,.55); margin-bottom:12px">COMBINED EQUITY</div>'
      + '<svg width="100%" height="220" viewBox="0 0 900 220" preserveAspectRatio="none">'
      + '<line x1="0" y1="20" x2="900" y2="20" stroke="rgba(255,255,255,.07)" />'
      + '<line x1="0" y1="90" x2="900" y2="90" stroke="rgba(255,255,255,.07)" />'
      + '<line x1="0" y1="160" x2="900" y2="160" stroke="rgba(255,255,255,.07)" />'
      + '<line x1="0" y1="210" x2="900" y2="210" stroke="rgba(255,255,255,.14)" />'
      + '<polyline points="' + equityPts + '" fill="none" stroke="#C8F542" stroke-width="2" /></svg></div>'
      + '</div>';
  } else if (s.portTab === 'exposure') {
    let alloc = [
      { label: 'MACRO', value: '$412', pct: 46, color: '#C8F542' },
      { label: 'POLITICS', value: '$268', pct: 30, color: '#C8F542' },
      { label: 'CRYPTO', value: '$143', pct: 16, color: '#4F8EF7' },
      { label: 'SPORTS', value: '$72', pct: 8, color: '#4F8EF7' }
    ];
    let conc = null;
    if (live && live.positions && live.positions.length) {
      const byCat = {};
      const values = [];
      live.positions.forEach((r) => {
        const value = parseFloat(String(r[5]).replace(/[$,]/g, '')) || 0;
        values.push(value);
        const m = T.markets.find((x) => x.title === r[0]);
        const cat = (m ? m.cat : 'Other').toUpperCase();
        byCat[cat] = (byCat[cat] || 0) + value;
      });
      const total = values.reduce((a, v) => a + v, 0) || 1;
      alloc = Object.entries(byCat).sort((a, b) => b[1] - a[1]).slice(0, 6).map(([label, value], i) => ({
        label, value: '$' + value.toFixed(0), pct: Math.round(value / total * 100), color: i < 2 ? '#C8F542' : '#4F8EF7'
      }));
      const sorted = values.slice().sort((a, b) => b - a);
      const cash = +kp.cash || 0;
      conc = {
        biggest: '$' + (sorted[0] || 0).toFixed(0) + ' · ' + Math.round((sorted[0] || 0) / total * 100) + '%',
        top3: '$' + sorted.slice(0, 3).reduce((a, v) => a + v, 0).toFixed(0) + ' · ' + Math.round(sorted.slice(0, 3).reduce((a, v) => a + v, 0) / total * 100) + '%',
        cash: '$' + cash.toFixed(0) + ' · ' + Math.round(cash / (total + cash) * 100) + '%'
      };
    }
    body = '<div style="padding:16px 24px; display:grid; grid-template-columns:1fr 1fr; gap:20px">'
      + '<div><div style="' + M + '; font-size:10.5px; letter-spacing:.14em; color:rgba(255,255,255,.55); margin-bottom:14px">BY CATEGORY</div>'
      + '<div style="display:flex; flex-direction:column; gap:14px">'
      + alloc.map((a) =>
        '<div><div style="display:flex; justify-content:space-between; ' + M + '; font-size:11.5px; margin-bottom:6px"><span style="color:rgba(255,255,255,.66)">' + a.label + '</span><span>' + a.value + '</span></div>'
        + '<div style="height:8px; background:rgba(255,255,255,.07); border-radius:2px"><div style="width:' + a.pct + '%; height:8px; background:' + a.color + '; border-radius:2px"></div></div></div>'
      ).join('')
      + '</div></div>'
      + '<div><div style="' + M + '; font-size:10.5px; letter-spacing:.14em; color:rgba(255,255,255,.55); margin-bottom:14px">CONCENTRATION</div>'
      + '<div style="display:flex; flex-direction:column; gap:11px">'
      + (conc
        ? '<div style="display:flex; justify-content:space-between; font-size:13px"><span style="color:rgba(255,255,255,.7)">Biggest single position</span><span style="' + M + '">' + conc.biggest + '</span></div>'
        + '<div style="display:flex; justify-content:space-between; font-size:13px"><span style="color:rgba(255,255,255,.7)">Top three positions</span><span style="' + M + '">' + conc.top3 + '</span></div>'
        + '<div style="display:flex; justify-content:space-between; font-size:13px"><span style="color:rgba(255,255,255,.7)">Cash not deployed</span><span style="' + M + '">' + conc.cash + '</span></div>'
        : '<div style="display:flex; justify-content:space-between; font-size:13px"><span style="color:rgba(255,255,255,.7)">Biggest single position</span><span style="' + M + '">$268 · 26%</span></div>'
        + '<div style="display:flex; justify-content:space-between; font-size:13px"><span style="color:rgba(255,255,255,.7)">Top three positions</span><span style="' + M + '">$641 · 61%</span></div>'
        + '<div style="display:flex; justify-content:space-between; font-size:13px"><span style="color:rgba(255,255,255,.7)">Resolving within 7 days</span><span style="' + M + '; color:#F5A623">$392 · 38%</span></div>'
        + '<div style="display:flex; justify-content:space-between; font-size:13px"><span style="color:rgba(255,255,255,.7)">Cash not deployed</span><span style="' + M + '">$312 · 23%</span></div>')
      + '</div></div></div>';
  } else if (s.portTab === 'history') {
    const histRows = liveHistRows || DEMO_HIST_ROWS;
    body = '<div style="border:1px solid rgba(255,255,255,.09); border-radius:12px; margin:14px 24px; overflow:hidden">'
      + '<div style="display:grid; grid-template-columns:110px 1fr 78px 92px 92px 100px; gap:10px; padding:9px 16px; background:#10151A; border-bottom:1px solid rgba(255,255,255,.09); ' + M + '; font-size:9px; letter-spacing:.12em; color:rgba(255,255,255,.45)">'
      + '<div>DATE</div><div>MARKET</div><div style="text-align:right">SIDE</div><div style="text-align:right">ENTRY</div><div style="text-align:right">EXIT</div><div style="text-align:right">RESULT</div></div>'
      + histRows.map((r) =>
        '<div style="display:grid; grid-template-columns:110px 1fr 78px 92px 92px 100px; gap:10px; align-items:center; padding:11px 16px; border-bottom:1px solid rgba(255,255,255,.06)">'
        + r.map((v, i) => {
          const style = i === 1 ? "font-family:'Inter',sans-serif; font-size:12.5px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis" : M + '; font-size:12px; text-align:' + (i === 0 ? 'left' : 'right') + '; color:' + (i === 5 ? (v.charAt(0) === '+' ? '#C8F542' : '#FF4545') : i === 2 ? (v === 'YES' ? '#C8F542' : '#4F8EF7') : 'rgba(255,255,255,.7)');
          return '<div style="' + style + '">' + esc(String(v)) + '</div>';
        }).join('')
        + '</div>'
      ).join('')
      + '</div>';
  } else {
    body = '<div style="padding:16px 24px">'
      + watch.map((m) =>
        '<div ' + m.act + ' class="hv-panel" style="display:grid; grid-template-columns:1fr 96px 88px 96px 108px; align-items:center; padding:12px 0; border-bottom:1px solid rgba(255,255,255,.06); cursor:pointer">'
        + '<div><div style="font-size:13.5px">' + esc(m.title) + '</div>'
        + '<div style="' + M + '; font-size:10.5px; color:rgba(255,255,255,.45); margin-top:3px">' + esc(m.meta) + '</div></div>'
        + '<div style="display:flex; justify-content:flex-end"><svg width="78" height="26" viewBox="0 0 78 26"><polyline points="' + m.sparkPoints + '" fill="none" stroke="' + m.color + '" stroke-width="1.6" /></svg></div>'
        + '<div style="' + M + '; font-size:15px; text-align:right">' + m.priceLabel + '</div>'
        + '<div style="' + m.changeStyle + '">' + m.changeLabel + '</div>'
        + '<div style="' + M + '; font-size:12px; text-align:right; color:rgba(255,255,255,.55)">' + esc(m.ends) + '</div></div>'
      ).join('')
      + '</div>';
  }

  return '<div>'
    + '<div style="padding:20px 24px 16px; border-bottom:1px solid rgba(255,255,255,.09)">'
    + '<div style="' + M + '; font-size:10px; letter-spacing:.18em; color:#C8F542">PORTFOLIO · PAPER</div>'
    + '<div style="font-family:\'Instrument Serif\',serif; font-size:30px; line-height:1.1; margin-top:5px">What you would be holding</div></div>'
    + '<div style="display:grid; grid-template-columns:repeat(4,1fr); border-bottom:1px solid rgba(255,255,255,.09)">'
    + '<div style="padding:16px 20px; border-right:1px solid rgba(255,255,255,.09)"><div style="' + M + '; font-size:10px; letter-spacing:.14em; color:rgba(255,255,255,.45)">VALUE NOW</div><div style="' + M + '; font-size:26px; margin-top:8px">$' + num((+kp.equity).toFixed(2)) + '</div></div>'
    + '<div style="padding:16px 20px; border-right:1px solid rgba(255,255,255,.09)"><div style="' + M + '; font-size:10px; letter-spacing:.14em; color:rgba(255,255,255,.45)">OPEN POSITIONS</div><div style="' + M + '; font-size:26px; margin-top:8px">' + (kp.open_positions != null ? kp.open_positions : 14) + '</div></div>'
    + '<div style="padding:16px 20px; border-right:1px solid rgba(255,255,255,.09)"><div style="' + M + '; font-size:10px; letter-spacing:.14em; color:rgba(255,255,255,.45)">UNREALISED</div><div style="' + M + '; font-size:26px; margin-top:8px; color:#C8F542">+$' + (kp.unrealized != null ? (+kp.unrealized).toFixed(2) : '28.60') + '</div></div>'
    + '<div style="padding:16px 20px"><div style="' + M + '; font-size:10px; letter-spacing:.14em; color:rgba(255,255,255,.45)">CASH FREE</div><div style="' + M + '; font-size:26px; margin-top:8px">$' + (kp.cash != null ? (+kp.cash).toFixed(2) : '312.40') + '</div></div>'
    + '</div>'
    + '<div style="display:flex; gap:6px; padding:16px 24px 0; flex-wrap:wrap">' + portTabs + '</div>'
    + body
    + '</div>';
}
