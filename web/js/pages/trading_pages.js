// Backtester, Copy trade, Portfolio — ported from the design reference.
// The backtester renders live results from POST /api/backtest when available,
// otherwise an honest empty state. No panel here falls back to a fixture:
// every figure comes from the API or the cell shows that it does not.

import { esc, num, leerZeile } from '../util.js';
import { trackWatchRows } from './trader_pages.js';

const M = "font-family:'JetBrains Mono',monospace";
const LBL9 = M + '; font-size:10.5px; letter-spacing:.14em; color:rgba(255,255,255,.6); margin-bottom:6px';
const LBL95 = M + '; font-size:10.5px; letter-spacing:.14em; color:rgba(255,255,255,.6); margin-bottom:7px';
const HEAD_CELL = M + '; font-size:10.5px; letter-spacing:.14em; color:rgba(255,255,255,.6)';

const SIZING = { fixed: 'Fixed $', pct: '% of bankroll', match: 'Match trader %', kelly: 'Kelly ¼' };

// A setting changed: mark the shown result as stale. Nothing runs until RUN
// is pressed — the earlier auto-run on every stepper click hit the rate
// limit after three clicks and flickered between results.
function bt(T, patch) {
  return () => { T.setState(Object.assign({ btDirty: !!(T.liveData && T.liveData.backtest) }, patch)); };
}

/** Warum keine Zahlen dastehen. Frueher stand hier ein synthetischer Lauf. */
function ohneBacktestHtml(s) {
  const running = s && s.btRun === 'running';
  const err = s && s.btRun === 'error' ? s.btError : '';
  let kopf = 'No run to show yet';
  let text = 'Press RUN. The engine replays the wallet against recorded trades in '
    + '<span style="' + M + '">app/backtester.py</span>, so it needs the API. If the numbers stay empty, either the '
    + 'backend is not reachable, or the wallet has no trades inside the selected window.';
  if (running) {
    kopf = 'running…';
    text = 'Replaying the wallet against recorded trades. A ninety-day window on an active wallet takes a while.';
  } else if (err === 'rate-limited') {
    kopf = 'rate-limited';
    text = 'The public API allows a few backtests per minute per address. Retry in ' + (s.btRetryIn > 0 ? s.btRetryIn + ' s' : 'a moment') + '.';
  } else if (err) {
    kopf = 'The run did not answer';
    text = esc(err);
  }
  return '<div style="background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:12px; padding:22px 24px; margin-top:14px; max-width:760px">'
    + '<div style="font-size:15px; font-weight:600; color:' + (running ? '#F5A623' : err ? '#FF7A7A' : '#ffffff') + '">' + kopf + '</div>'
    + '<div style="font-size:13px; color:rgba(255,255,255,.55); margin-top:10px; line-height:1.65">' + text + '</div>'
    + '<div style="font-size:12.5px; color:rgba(255,255,255,.6); margin-top:12px; line-height:1.6">'
    + 'Nothing is estimated here. This panel used to fill itself from a generator when the '
    + 'backend was silent, which produced an equity curve that responded to every slider and '
    + 'meant nothing.'
    + '</div></div>';
}

// One line above the results: running / rate-limited / error / stale, or
// nothing when the shown result matches the current settings.
function laufStatusHtml(s, hatErgebnis) {
  if (s.btRun === 'running') {
    return '<div style="display:flex; align-items:center; gap:8px; margin-top:8px; ' + M + '; font-size:11px; color:#F5A623">'
      + '<span style="width:7px; height:7px; border-radius:50%; background:#F5A623; display:inline-block; animation:livePulse 1.2s ease-in-out infinite"></span>running…'
      + (hatErgebnis ? ' <span style="color:rgba(255,255,255,.6)">— the last result stays below until the new one lands</span>' : '') + '</div>';
  }
  if (s.btRun === 'error' && s.btError === 'rate-limited') {
    return '<div style="margin-top:8px; ' + M + '; font-size:11px; color:#F5A623">rate-limited, retry in ' + (s.btRetryIn > 0 ? s.btRetryIn + ' s' : 'a moment')
      + (hatErgebnis ? ' <span style="color:rgba(255,255,255,.6)">— the last result is kept below</span>' : '') + '</div>';
  }
  if (s.btRun === 'error' && s.btError) {
    return '<div style="margin-top:8px; ' + M + '; font-size:11px; color:#FF7A7A">' + esc(s.btError) + (hatErgebnis ? ' <span style="color:rgba(255,255,255,.6)">— the last result is kept below</span>' : '') + '</div>';
  }
  if (hatErgebnis && s.btDirty) {
    return '<div style="margin-top:8px; ' + M + '; font-size:11px; color:rgba(255,255,255,.5)">settings changed since this run — press RUN to refresh</div>';
  }
  return '';
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
  const live = T.liveData.backtest;
  const st = live && live.stats ? live.stats : null;

  // Kein synthetischer Lauf mehr. Hier stand eine Kurve aus einem
  // Zufallsgenerator mit eingebautem Drift: 0.9 aufwaerts fuer Copy, -0.25
  // abwaerts fuer Fade, Trefferquote fest 57 gegen 43 Prozent, und alles
  // reagierte auf jeden Regler. Das sah aus wie ein Backtest, war aber die
  // Behauptung, die dieses Projekt ausdruecklich nicht aufstellt. Ohne
  // Antwort vom Backend gibt es jetzt Zahlen weder gerundet noch geraten.
  const finalEq = st ? +st.final_equity : null;
  const ret = st ? +st.roi * 100 : null;
  const totalPnl = st ? +st.total_pnl : null;
  const benchPnl = st && live.benchmark_stats ? +live.benchmark_stats.total_pnl : null;
  const copied = st ? +st.copied_trades : null;
  const skippedN = st ? +st.skipped_trades : null;
  const winsN = st ? +st.wins : null;
  const lossesN = st ? +st.losses : null;
  const feesPaid = st ? +st.fees_paid : null;
  const openValue = st ? +st.open_value : null;
  const ddPct = st ? Math.abs(+st.max_drawdown) * 100 : null;
  const equityPts = st && live.equity && live.equity.length > 1
    ? T.seriesPoints(live.equity, 900, 270) : '';
  const benchPts = st && live.benchmark && live.benchmark.length > 1
    ? T.seriesPoints(live.benchmark, 900, 270) : '';
  const ddPts = st && live.drawdown && live.drawdown.length > 1
    ? T.seriesPoints(live.drawdown, 900, 220) : '';

  const simVariants = (live && live.variants ? live.variants.map((v) => ({
    name: v.name, eq: +v.final_equity, roi: +v.roi * 100, dd: Math.abs(+v.max_drawdown) * 100,
    wr: +v.win_rate * 100, copied: +v.copied_trades, skipped: +v.skipped_trades
  })) : []).sort((a, b) => b.eq - a.eq);
  const bestVariant = simVariants[0] || null;

  const shortWallet = s.btWallet.trim().length > 12 ? s.btWallet.trim().slice(0, 6) + '…' + s.btWallet.trim().slice(-4) : s.btWallet.trim();
  const gebuehrText = s.btFeeModel === 'flat' ? 'fees ' + s.btFee + ' bps flat' : 'fees on the venue curve';
  const runMeta = (s.btStrategy === 'copy' ? 'Copy' : 'Fade') + ' · last ' + s.btWindow + ' days · wallet ' + shortWallet + ' · ' + SIZING[s.btSizing] + ' · ' + gebuehrText + ' · slippage ' + s.btSlip + ' bps'
    + (live && live.stats && live.stats.window_truncated ? ' · window truncated at the engine\'s trade cap' : '');

  // Ohne Lauf keine Kacheln: jede dieser Zahlen kaeme sonst aus dem Nichts.
  const statCards = st ? [
    { label: 'FINAL EQUITY', value: '$' + finalEq.toFixed(0), sub: (ret >= 0 ? '+' : '') + ret.toFixed(1) + '% ROI', pos: ret >= 0 },
    { label: 'TOTAL P&L', value: (totalPnl >= 0 ? '+' : '-') + '$' + Math.abs(totalPnl).toFixed(0), sub: benchPnl === null ? 'no benchmark' : (totalPnl - benchPnl >= 0 ? '+' : '-') + '$' + Math.abs(totalPnl - benchPnl).toFixed(0) + ' vs flat-bet', pos: totalPnl >= 0 },
    { label: 'WIN RATE', value: Math.round((winsN / Math.max(1, copied)) * 100) + '%', sub: winsN + 'W / ' + lossesN + 'L', pos: null },
    { label: 'MAX DRAWDOWN', value: ddPct.toFixed(1) + '%', sub: 'from the running peak', pos: false },
    { label: 'TRADES COPIED', value: num(copied), sub: num(Math.max(0, skippedN)) + ' skipped', pos: null },
    { label: 'FEES PAID', value: '$' + feesPaid.toFixed(2), sub: '$' + openValue.toFixed(0) + ' still open', pos: null }
  ] : [];

  const stakeLabel = s.btSizing === 'pct' ? 'STAKE (% OF BANKROLL)' : s.btSizing === 'match' ? "MULTIPLIER (× TRADER'S SHARE)" : s.btSizing === 'kelly' ? 'ASSUMED EDGE (PROBABILITY POINTS)' : 'STAKE PER COPY ($)';
  const stakeValue = s.btSizing === 'pct' ? s.btStakePct.toFixed(1) + '%' : s.btSizing === 'match' ? '×' + s.btStakeMult.toFixed(1) : s.btSizing === 'kelly' ? s.btStakeKelly.toFixed(1) + ' pts' : '$' + s.btStakeFixed;
  const stakeHint = s.btSizing === 'pct' ? 'Each copy bets ' + s.btStakePct.toFixed(1) + '% of your bankroll — about $' + (bank * s.btStakePct / 100).toFixed(0) + ' right now.'
    : s.btSizing === 'match' ? 'If the trader puts 2% of their portfolio into a bet, you put 2% × ' + s.btStakeMult.toFixed(1) + ' of yours. Their portfolio size is read from their public profile.'
    : s.btSizing === 'kelly' ? 'Assumes every entry is worth its price plus ' + s.btStakeKelly.toFixed(1) + ' points, then stakes quarter-Kelly of equity. Conservative on purpose — the edge is an assumption.'
    : 'Every copied trade bets exactly $' + s.btStakeFixed + '. Capped at $' + s.btCap + ' per trade.';
  const stakeUp = s.btSizing === 'pct' ? { btStakePct: Math.min(100, s.btStakePct + 0.5) } : s.btSizing === 'match' ? { btStakeMult: Math.min(10, s.btStakeMult + 0.5) } : s.btSizing === 'kelly' ? { btStakeKelly: Math.min(30, s.btStakeKelly + 0.5) } : { btStakeFixed: s.btStakeFixed + 5 };
  const stakeDown = s.btSizing === 'pct' ? { btStakePct: Math.max(0.1, s.btStakePct - 0.5) } : s.btSizing === 'match' ? { btStakeMult: Math.max(0.1, s.btStakeMult - 0.5) } : s.btSizing === 'kelly' ? { btStakeKelly: Math.max(0.5, s.btStakeKelly - 0.5) } : { btStakeFixed: Math.max(1, s.btStakeFixed - 5) };

  // Weder erfundene Trades noch eine erfundene Vergleichs-Wallet. Hier lagen
  // acht ausgedachte Log-Zeilen, fuenf ausgedachte offene Positionen und eine
  // Vergleichstabelle, die die Gegenseite als Vielfaches der eigenen Zahlen
  // berechnete (Endkapital mal 0.88, PnL mal 0.72, Trefferquote fest 51).
  // Ohne Backend gibt es davon nichts zu zeigen.
  const logRows = (live && live.log ? live.log : []).map((l) => ({
    time: l.time, action: l.action, status: l.status, market: l.market, side: l.side,
    traderAmt: '$' + num(Math.round(+l.trader_amt || 0)),
    stake: +l.stake ? '$' + (+l.stake).toFixed(2) : '—',
    fill: +l.fill ? (+l.fill).toFixed(3) : '—',
    fee: +l.fee ? '$' + (+l.fee).toFixed(2) : '—',
    equity: '$' + (+l.equity).toFixed(2)
  }));

  const openRows = (live && live.open ? live.open : []).map((o) => {
    const sh = +o.shares, avg = +o.avg, mark = +o.mark;
    const cost = sh * avg, val = sh * mark, pnl = val - cost;
    return {
      market: o.market, side: o.side, shares: sh.toFixed(1), avg: avg.toFixed(3),
      mark: mark.toFixed(3), cost: '$' + cost.toFixed(2), value: '$' + val.toFixed(2),
      pnl: (pnl >= 0 ? '+' : '-') + '$' + Math.abs(pnl).toFixed(2), pnlPos: pnl >= 0
    };
  });

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
  ].join('');

  let tabBody = '';
  if (s.btTab === 'log') {
    tabBody = '<div style="border:1px solid rgba(255,255,255,.09); border-radius:12px; margin-top:12px; overflow:hidden">'
      + '<div style="display:grid; grid-template-columns:88px 74px 84px 1fr 60px 84px 78px 74px 84px 88px; gap:10px; padding:9px 16px; background:#10151A; border-bottom:1px solid rgba(255,255,255,.09); ' + M + '; font-size:10.5px; letter-spacing:.12em; color:rgba(255,255,255,.6)">'
      + '<div>TIME</div><div>ACTION</div><div>STATUS</div><div>MARKET</div><div>SIDE</div><div style="text-align:right">TRADER $</div><div style="text-align:right">STAKE</div><div style="text-align:right">FILL</div><div style="text-align:right">FEE</div><div style="text-align:right">EQUITY</div></div>'
      + logRows.map((l) =>
        '<div style="display:grid; grid-template-columns:88px 74px 84px 1fr 60px 84px 78px 74px 84px 88px; gap:10px; align-items:center; padding:10px 16px; border-bottom:1px solid rgba(255,255,255,.06); ' + M + '; font-size:11.5px">'
        + '<div style="color:rgba(255,255,255,.5)">' + esc(l.time) + '</div>'
        + '<div style="' + M + '; font-size:11.5px; color:' + (l.action === 'BUY' ? '#C8F542' : '#FF4545') + '">' + esc(l.action) + '</div>'
        + '<div><span style="' + M + '; font-size:10.5px; letter-spacing:.08em; border-radius:4px; padding:2px 6px; ' + (l.status === 'skipped' ? 'color:#F5A623; border:1px solid rgba(245,166,35,.35)' : 'color:rgba(255,255,255,.7); border:1px solid rgba(255,255,255,.18)') + '">' + esc(l.status) + '</span></div>'
        + '<div style="font-family:\'Inter\',sans-serif; font-size:12.5px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis">' + esc(l.market) + '</div>'
        + '<div style="color:rgba(255,255,255,.6)">' + esc(l.side) + '</div>'
        + '<div style="text-align:right; color:rgba(255,255,255,.5)">' + esc(l.traderAmt) + '</div>'
        + '<div style="text-align:right">' + esc(l.stake) + '</div>'
        + '<div style="text-align:right; color:rgba(255,255,255,.6)">' + esc(l.fill) + '</div>'
        + '<div style="text-align:right; color:rgba(255,255,255,.5)">' + esc(l.fee) + '</div>'
        + '<div style="text-align:right">' + esc(l.equity) + '</div></div>'
      ).join('')
      // Der Knopf "Export trade log CSV" stand hier ohne Handler. Ein Knopf,
      // der nichts tut, ist eine Behauptung ueber eine Funktion.
      + '</div>';
  } else if (s.btTab === 'open') {
    tabBody = '<div style="border:1px solid rgba(255,255,255,.09); border-radius:12px; margin-top:12px; overflow:hidden">'
      + '<div style="display:grid; grid-template-columns:1fr 62px 78px 78px 78px 88px 88px 100px; gap:10px; padding:9px 16px; background:#10151A; border-bottom:1px solid rgba(255,255,255,.09); ' + M + '; font-size:10.5px; letter-spacing:.12em; color:rgba(255,255,255,.6)">'
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
      + '<div style="display:flex; justify-content:space-between; ' + M + '; font-size:11px; color:rgba(255,255,255,.6); margin-top:8px">'
      + '<span>' + s.btWindow + 'd ago</span><span>worst: ' + (ddPct === null ? '—' : ddPct.toFixed(1) + '%') + '</span><span>today</span></div></div>';
  }

  const advChevron = M + '; font-size:16px; color:rgba(255,255,255,.5); transition:transform .18s ease; transform:rotate(' + (s.advancedOpen ? '90deg' : '0deg') + ')';
  const simChevron = M + '; font-size:16px; color:rgba(255,255,255,.5); transition:transform .18s ease; transform:rotate(' + (s.sizingSimOpen ? '90deg' : '0deg') + ')';

  return '<div>'
    + '<div style="padding:20px 24px 16px; border-bottom:1px solid rgba(255,255,255,.09)">'
    + '<div style="display:flex; align-items:flex-end; justify-content:space-between; gap:20px">'
    + '<div><div style="' + M + '; font-size:11px; letter-spacing:.18em; color:#C8F542">BACKTESTER · PAPER SIM</div>'
    + '<div style="font-family:\'Instrument Serif\',serif; font-size:30px; line-height:1.1; margin-top:5px">Replay a wallet with your own sizing</div>'
    + '<div style="font-size:13px; color:rgba(255,255,255,.55); margin-top:9px; max-width:680px">Every simulated fill is priced with fees and slippage, up to ninety days back.</div></div>'
    + '<div style="' + M + '; font-size:10.5px; color:#0A0D0F; background:#C8F542; border-radius:5px; padding:5px 10px">POLYMARKET</div>'
    + '</div></div>'

    + '<div style="display:grid; grid-template-columns:352px 1fr">'
    + '<div style="border-right:1px solid rgba(255,255,255,.09); padding:18px 20px; display:flex; flex-direction:column; gap:22px">'

    + '<div><div style="' + M + '; font-size:11px; letter-spacing:.16em; color:#C8F542; margin-bottom:9px">01 · WALLET TO REPLAY</div>'
    + '<input value="' + esc(s.btWallet) + '" ' + T.inp((e) => { T.state.btWallet = e.target.value; if (T.liveData.backtest) T.state.btDirty = true; }, 'btWallet') + ' placeholder="0x…" style="width:100%; box-sizing:border-box; background:#10151A; border:1px solid rgba(255,255,255,.16); border-radius:8px; padding:10px 12px; ' + M + '; font-size:12px; color:#fff" />'
    + '<div style="font-size:11.5px; color:rgba(255,255,255,.6); margin-top:7px; line-height:1.5">Any public Polymarket address — the default is one with a long public trade history, chosen so a first run has something to replay. Take one from the leaderboard to compare.</div></div>'

    + '<div><div style="' + M + '; font-size:11px; letter-spacing:.16em; color:#C8F542; margin-bottom:9px">02 · STAKE PER COPY</div>'
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
    + '<div style="font-size:11.5px; color:rgba(255,255,255,.6); margin-top:7px; line-height:1.5">' + stakeHint + '</div></div>'
    + '<div style="display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-top:14px">'
    + stepRow('CAP PER TRADE', '$' + s.btCap, { btCap: Math.max(10, s.btCap - 50) }, { btCap: s.btCap + 50 })
    + stepRow('MAX BANKROLL IN OPEN COPIES', s.btExposure + '%', { btExposure: Math.max(5, s.btExposure - 5) }, { btExposure: Math.min(100, s.btExposure + 5) })
    + '</div>'
    + '<div style="font-size:11.5px; color:rgba(255,255,255,.6); margin-top:7px; line-height:1.5">New copies are skipped while open copies already tie up that share of the bankroll. Sells free the room up again.</div></div>'

    + '<div><div style="' + M + '; font-size:11px; letter-spacing:.16em; color:#C8F542; margin-bottom:9px">03 · TIME WINDOW</div>'
    + '<div style="display:flex; gap:7px">'
    + [T.tab('7d', s.btWindow === 7, bt(T, { btWindow: 7 })), T.tab('30d', s.btWindow === 30, bt(T, { btWindow: 30 })), T.tab('90d', s.btWindow === 90, bt(T, { btWindow: 90 }))].join('')
    + '</div></div>'

    + '<div><div style="' + M + '; font-size:11px; letter-spacing:.16em; color:#C8F542; margin-bottom:9px">04 · STRATEGY</div>'
    + '<div style="display:flex; gap:7px">'
    + [T.tab('Copy', s.btStrategy === 'copy', bt(T, { btStrategy: 'copy' })), T.tab('Fade', s.btStrategy === 'fade', bt(T, { btStrategy: 'fade' }))].join('')
    + '</div>'
    + '<div style="font-size:11.5px; color:rgba(255,255,255,.6); margin-top:7px; line-height:1.5">' + (s.btStrategy === 'copy' ? 'Mirror every trade the wallet makes, at the same price.' : 'Fade takes the opposite side of every trade the wallet makes.') + '</div></div>'

    + '<div style="border:1px solid rgba(255,255,255,.09); border-radius:10px; overflow:hidden">'
    + '<div ' + T.act(() => T.setState({ advancedOpen: !s.advancedOpen })) + ' class="hv-el" style="display:flex; align-items:center; justify-content:space-between; padding:11px 14px; background:#10151A; cursor:pointer">'
    + '<div style="font-size:13px">Advanced settings</div><div style="' + advChevron + '">›</div></div>'
    + (s.advancedOpen ?
      '<div style="padding:14px; display:flex; flex-direction:column; gap:13px">'
      + stepRow('BANKROLL', '$' + num(s.btBankroll), { btBankroll: Math.max(100, s.btBankroll - 500) }, { btBankroll: s.btBankroll + 500 })
      + '<div style="display:grid; grid-template-columns:1fr 1fr; gap:10px">'
      + stepRow('SLIPPAGE (BPS)', s.btSlip + ' bps', { btSlip: Math.max(0, s.btSlip - 5) }, { btSlip: s.btSlip + 5 })
      + '<div><div style="' + LBL95 + '">FEE MODEL</div>'
      + '<div style="display:flex; gap:6px; margin-top:6px">'
      + T.opt('Venue curve', s.btFeeModel !== 'flat', { btFeeModel: 'curve' })
      + T.opt('Flat override', s.btFeeModel === 'flat', { btFeeModel: 'flat' })
      + '</div></div>'
      + '</div>'
      // Bis eben rechnete die Engine pauschal mit 20 bps, waehrend das
      // Gebuehrenmodell im selben Repository die echte Kurve kannte. Sie
      // haengt am Preis: rund 250 bps bei 0.50, rund 50 bps bei 0.90. In der
      // Mitte des Buchs war die Voreinstellung um mehr als das Zehnfache zu
      // billig, und zu billige Gebuehren schmeicheln jedem Ergebnis.
      + (s.btFeeModel === 'flat'
        ? '<div style="display:flex; flex-direction:column; gap:8px">'
          + stepRow('FLAT FEE (BPS)', s.btFee + ' bps', { btFee: Math.max(0, s.btFee - 5) }, { btFee: s.btFee + 5 })
          + '<div style="font-size:11px; color:#F5A623; line-height:1.5">'
          + 'A flat rate cannot match the venue: Polymarket charges about 250 bps at a price of 0.50 '
          + 'and about 50 bps at 0.90. Anything near 20 bps understates the real cost by a wide margin.'
          + '</div></div>'
        : '<div style="font-size:11.5px; color:rgba(255,255,255,.6); line-height:1.5">'
          + 'Polymarket charges the taker fee on the variance of the price, so it peaks in the middle '
          + 'of the book: about 250 bps at 0.50 and about 50 bps at 0.90, at the general category rate. '
          + 'The model lives in app/venue_fees.py and the general rate applies, because a wallet history '
          + 'carries no category.'
          + '</div>')
      + '<div><div style="' + LBL95 + '">BENCHMARK</div>'
      + '<div style="font-size:11.5px; color:rgba(255,255,255,.6); margin-top:7px; line-height:1.5">The dashed line in the results is the same trades at a constant 2% of the starting bankroll per copy. The compare-wallet field was removed: the server never read it, and the table it fed derived the other wallet from ours by fixed multipliers.</div></div>'
      + '</div>' : '')
    + '</div>'

    // The only thing that starts a run. While one runs the button is inert
    // and says so; after a 429 it says how long to wait.
    + (s.btRun === 'running'
      ? '<div style="font-size:13.5px; font-weight:600; text-align:center; color:rgba(255,255,255,.5); border:1px solid rgba(255,255,255,.16); border-radius:8px; padding:12px; cursor:default">running…</div>'
      : s.btRun === 'error' && s.btError === 'rate-limited' && s.btRetryIn > 0
        ? '<div style="font-size:13.5px; font-weight:600; text-align:center; color:#F5A623; border:1px solid rgba(245,166,35,.4); border-radius:8px; padding:12px; cursor:default">rate-limited · retry in ' + s.btRetryIn + ' s</div>'
        : '<div ' + T.act(() => { T.setState({ btTab: 'log' }); T.runBacktest(); }) + ' class="hv-limebg" style="font-size:13.5px; font-weight:600; text-align:center; color:#0A0D0F; background:#C8F542; border-radius:8px; padding:12px; cursor:pointer">RUN backtest →</div>')
    + '</div>'

    + '<div style="padding:18px 24px">'
    + '<div style="' + M + '; font-size:11.5px; color:rgba(255,255,255,.6)">' + esc(runMeta) + '</div>'
    // Without a result the empty block below carries the run state itself.
    + (st ? laufStatusHtml(s, true) : '')
    + (st ? ''

    + '<div style="display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin-top:14px">'
    + statCards.map((c) =>
      '<div style="background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:10px; padding:14px 16px">'
      + '<div style="' + M + '; font-size:10.5px; letter-spacing:.13em; color:rgba(255,255,255,.6)">' + c.label + '</div>'
      + '<div style="' + M + '; font-size:22px; margin-top:7px; color:' + (c.pos === true ? '#C8F542' : c.pos === false ? '#FF4545' : '#ffffff') + '">' + c.value + '</div>'
      + '<div style="' + M + '; font-size:11px; margin-top:5px; color:rgba(255,255,255,.6)">' + c.sub + '</div></div>'
    ).join('')
    + '</div>'

    // Keine erfundene Aufteilung der Skips mehr: hier stand 60 Prozent
    // Exposure-Deckel, 30 Prozent Kasse leer, 10 Prozent fremde Verkaeufe —
    // drei feste Anteile, die die Engine nie gemeldet hat. Der Grund je Zeile
    // steht im Trade log; hier nur die gemessene Summe.
    + (skippedN > copied ? '<div style="border:1px solid rgba(245,166,35,.3); background:rgba(245,166,35,.07); border-radius:10px; padding:12px 15px; margin-top:12px; font-size:12.5px; color:#F5A623; line-height:1.5">More skipped than copied: ' + num(skippedN) + ' of the wallet\'s trades were not mirrored. A skip happens when the exposure cap (' + s.btExposure + '%) is full, when the cash runs out, or when the wallet sells a position you never held — the trade log below marks each one. Raise the exposure cap or lower the stake to copy more of the flow.</div>' : '')

    + '<div style="background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:12px; margin-top:14px; padding:16px 18px">'
    + '<div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:12px; flex-wrap:wrap; gap:10px">'
    + '<div style="' + M + '; font-size:10.5px; letter-spacing:.14em; color:rgba(255,255,255,.55)">EQUITY CURVE</div>'
    + '<div style="display:flex; gap:16px; ' + M + '; font-size:10.5px; flex-wrap:wrap">'
    + '<span style="display:flex; align-items:center; gap:6px"><span style="width:14px; height:2px; background:#C8F542; display:inline-block"></span>' + esc(shortWallet) + '</span>'
    + '<span style="display:flex; align-items:center; gap:6px; color:rgba(255,255,255,.5)"><span style="width:14px; height:2px; background:#95A0AB; display:inline-block"></span>Flat-bet benchmark</span>'
    + (s.sizingSimOpen && bestVariant ? '<span style="display:flex; align-items:center; gap:6px; color:#F5A623"><span style="width:14px; height:2px; background:#F5A623; display:inline-block"></span>Best sizing: ' + esc(bestVariant.name) + '</span>' : '')
    + '</div></div>'
    + '<svg width="100%" height="270" viewBox="0 0 900 270" preserveAspectRatio="none">'
    + '<line x1="0" y1="20" x2="900" y2="20" stroke="rgba(255,255,255,.07)" />'
    + '<line x1="0" y1="80" x2="900" y2="80" stroke="rgba(255,255,255,.07)" />'
    + '<line x1="0" y1="140" x2="900" y2="140" stroke="rgba(255,255,255,.07)" />'
    + '<line x1="0" y1="200" x2="900" y2="200" stroke="rgba(255,255,255,.07)" />'
    + '<line x1="0" y1="258" x2="900" y2="258" stroke="rgba(255,255,255,.14)" />'
    + '<polyline points="' + benchPts + '" fill="none" stroke="#95A0AB" stroke-width="1.4" stroke-dasharray="6 4" />'
        + '<polyline points="' + equityPts + '" fill="none" stroke="' + (ret >= 0 ? '#C8F542' : '#FF4545') + '" stroke-width="2" />'
    + '</svg>'
    + '<div style="display:flex; justify-content:space-between; ' + M + '; font-size:11px; color:rgba(255,255,255,.6); margin-top:8px">'
    + '<span>' + s.btWindow + 'd ago</span><span>' + Math.round(s.btWindow / 2) + 'd ago</span><span>today</span></div></div>'

    + '<div style="display:flex; gap:6px; margin-top:16px">' + btTabs + '</div>'
    + tabBody

    + '<div style="border:1px solid rgba(255,255,255,.09); border-radius:12px; margin-top:16px; overflow:hidden">'
    + '<div ' + T.act(() => { T.setState({ sizingSimOpen: !s.sizingSimOpen, btDirty: !s.sizingSimOpen && !(live && live.variants) ? true : s.btDirty }); }) + ' class="hv-el" style="display:flex; align-items:center; justify-content:space-between; padding:13px 18px; background:#10151A; cursor:pointer">'
    + '<div style="font-size:14px">Which sizing would have been best for this wallet?</div><div style="' + simChevron + '">›</div></div>'
    + (s.sizingSimOpen && !bestVariant
      ? '<div style="padding:14px 18px; ' + M + '; font-size:11px; color:rgba(255,255,255,.5)">The variants are computed with the run — press RUN with this section open to include them.</div>'
      : '')
    + (s.sizingSimOpen && bestVariant ?
      '<div style="padding:16px 18px">'
      + '<div style="font-size:12.5px; color:rgba(255,255,255,.55); line-height:1.5">Replays the same window once per sizing rule — identical fees, slippage, cap and exposure limit. Only the stake rule changes. The winner is drawn into the chart above as the dotted amber line.</div>'
      + '<div style="font-size:13px; margin-top:12px">Best for this wallet and window: <strong style="color:#F5A623">' + esc(bestVariant.name) + '</strong> → $' + bestVariant.eq.toFixed(0) + ' final equity (' + (bestVariant.roi >= 0 ? '+' : '') + bestVariant.roi.toFixed(1) + '% ROI)</div>'
      + '<div style="border:1px solid rgba(255,255,255,.09); border-radius:10px; margin-top:14px; overflow:hidden">'
      + '<div style="display:grid; grid-template-columns:1fr 110px 96px 96px 96px 88px 88px; gap:10px; padding:9px 14px; background:#10151A; border-bottom:1px solid rgba(255,255,255,.09); ' + M + '; font-size:10.5px; letter-spacing:.12em; color:rgba(255,255,255,.6)">'
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
    // "Mirror this on paper" und "Save this setup" standen hier ohne Handler.
    // Es gibt keinen Endpunkt, der einen Backtest in den Copy-Trader
    // uebernimmt oder eine Einstellung speichert; die Knoepfe sind weg.
    : ohneBacktestHtml(s))
    + '</div></div></div>';
}

/** Leerzustand fuer die Papier-Simulationsseiten. */
function ohnePapierDatenHtml(titel, kicker, grund) {
  return '<div>'
    + '<div style="padding:20px 24px 16px; border-bottom:1px solid rgba(255,255,255,.09)">'
    + '<div style="' + M + '; font-size:11px; letter-spacing:.18em; color:#C8F542">' + kicker + '</div>'
    + '<div style="font-family:\'Instrument Serif\',serif; font-size:30px; line-height:1.1; margin-top:5px">' + titel + '</div></div>'
    + '<div style="padding:26px 24px">'
    + '<div style="background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:12px; padding:22px 24px; max-width:760px">'
    + '<div style="font-size:15px; font-weight:600">Nothing to show</div>'
    + '<div style="font-size:13px; color:rgba(255,255,255,.55); margin-top:10px; line-height:1.65">' + grund + '</div>'
    + '<div style="font-size:12.5px; color:rgba(255,255,255,.6); margin-top:12px; line-height:1.6">'
    + 'This page used to fill itself with fixtures when the backend was silent, including a cash '
    + 'balance, a profit figure and a real wallet address as the source. None of that was measured.'
    + '</div></div></div></div>';
}

// ---------------------------------------------------------------- copy trade
// The copy desk moved to copy_page.js (traders, follow form, settings, sync);
// re-exported here so app.js and the render harness keep one import.
export { renderCopy } from './copy_page.js';

// ---------------------------------------------------------------- portfolio
export function renderPortfolio(T) {
  const s = T.state;
  const live = T.liveData.copy;
  const kp = live && live.kpis ? live.kpis : null;
  if (!kp) {
    return ohnePapierDatenHtml('Your paper book', 'PORTFOLIO · PAPER',
      'The positions here come from the same paper sub-account as the copy page. '
      + 'Without the API there is no book to show.');
  }
  const equityPts = live && live.equity_curve && live.equity_curve.length > 1 ? T.seriesPoints(live.equity_curve, 900, 220) : '';
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
    const baseRows = livePortRows || [];
    const rows = baseRows.filter((r) => (s.portSource === 'all' || r[5] === s.portSource) && (s.portSide === 'all' || r[1] === s.portSide) && (!s.portLosers || r[4].charAt(0) === '-') && (!s.portQuery.trim() || r[0].toLowerCase().indexOf(s.portQuery.trim().toLowerCase()) >= 0));
    body = '<div>'
      + '<div style="padding:14px 24px 0; display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:14px 18px">'
      + '<div><div style="' + LBL9 + '">SEARCH</div><input value="' + esc(s.portQuery) + '" ' + T.inp((e) => T.setState({ portQuery: e.target.value }), 'portQuery') + ' placeholder="market or wallet…" style="width:100%; box-sizing:border-box; background:#10151A; border:1px solid rgba(255,255,255,.16); border-radius:7px; padding:8px 10px; ' + M + '; font-size:11.5px; color:#fff" /></div>'
      + '<div><div style="' + LBL9 + '">SOURCE</div><div style="display:flex; gap:6px; flex-wrap:wrap">'
      + [['all','All'],['research','Research'],['copy','Copy trade']].map((o) => T.opt(o[1], s.portSource === o[0], { portSource: o[0] })).join('') + '</div></div>'
      + '<div><div style="' + LBL9 + '">SIDE</div><div style="display:flex; gap:6px; flex-wrap:wrap">'
      + [['all','All'],['YES','Yes'],['NO','No']].map((o) => T.opt(o[1], s.portSide === o[0], { portSide: o[0] })).join('') + '</div></div>'
      + '<div><div style="' + LBL9 + '">SHOW</div><div style="display:flex; gap:6px; flex-wrap:wrap">'
      + [['all','Everything'],['losers','Losing only']].map((o) => T.opt(o[1], (s.portLosers ? 'losers' : 'all') === o[0], { portLosers: o[0] === 'losers' })).join('') + '</div></div>'
      + '</div>'
      + '<div style="border:1px solid rgba(255,255,255,.09); border-radius:12px; margin:14px 24px; overflow:hidden">'
      + '<div style="display:grid; grid-template-columns:1fr 76px 92px 92px 100px 100px; gap:10px; padding:9px 16px; background:#10151A; border-bottom:1px solid rgba(255,255,255,.09); ' + M + '; font-size:10.5px; letter-spacing:.12em; color:rgba(255,255,255,.6)">'
      + '<div>MARKET</div><div style="text-align:right">SIDE</div><div style="text-align:right">ENTRY</div><div style="text-align:right">NOW</div><div style="text-align:right">PROFIT</div><div style="text-align:right">SOURCE</div></div>'
      + (rows.length ? '' : leerZeile(baseRows.length ? 'No position matches these filters.' : 'No open positions in the paper book reported by /api/copy.'))
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
      + '<div style="background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:10px; padding:14px 16px"><div style="' + M + '; font-size:10.5px; letter-spacing:.13em; color:rgba(255,255,255,.6)">COPY EQUITY</div><div style="' + M + '; font-size:21px; margin-top:7px">$' + num((+kp.equity).toFixed(2)) + '</div></div>'
      + '<div style="background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:10px; padding:14px 16px"><div style="' + M + '; font-size:10.5px; letter-spacing:.13em; color:rgba(255,255,255,.6)">RESEARCH CASH</div><div style="' + M + '; font-size:21px; margin-top:7px">$' + (+kp.cash).toFixed(2) + '</div></div>'
      + '<div style="background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:10px; padding:14px 16px"><div style="' + M + '; font-size:10.5px; letter-spacing:.13em; color:rgba(255,255,255,.6)">EVERYTHING TOGETHER</div><div style="' + M + '; font-size:21px; margin-top:7px; color:#C8F542">$' + num(((+kp.equity) + (+kp.cash)).toFixed(2)) + '</div></div>'
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
    // Keine erfundene Aufteilung mehr: hier standen MACRO $412, POLITICS
    // $268, CRYPTO $143, SPORTS $72 als Rueckfall, wenn das Buch leer war.
    // Ein leeres Buch hat keine Aufteilung, und das steht dann da.
    let alloc = [];
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
    const keinBuch = 'No open positions in the paper book reported by /api/copy — nothing to break down.';
    body = '<div style="padding:16px 24px; display:grid; grid-template-columns:1fr 1fr; gap:20px">'
      + '<div><div style="' + M + '; font-size:10.5px; letter-spacing:.14em; color:rgba(255,255,255,.55); margin-bottom:14px">BY CATEGORY</div>'
      + '<div style="display:flex; flex-direction:column; gap:14px">'
      + (alloc.length ? '' : leerZeile(keinBuch))
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
        // Hier standen $268 · 26%, $641 · 61%, $392 · 38% und $312 · 23% als
        // Rueckfall — vier Konzentrationswerte fuer ein Buch ohne Positionen.
        : leerZeile(keinBuch))
      + '</div></div></div>';
  } else if (s.portTab === 'history') {
    const histRows = liveHistRows || [];
    body = '<div style="border:1px solid rgba(255,255,255,.09); border-radius:12px; margin:14px 24px; overflow:hidden">'
      + '<div style="display:grid; grid-template-columns:110px 1fr 78px 92px 92px 100px; gap:10px; padding:9px 16px; background:#10151A; border-bottom:1px solid rgba(255,255,255,.09); ' + M + '; font-size:10.5px; letter-spacing:.12em; color:rgba(255,255,255,.6)">'
      + '<div>DATE</div><div>MARKET</div><div style="text-align:right">SIDE</div><div style="text-align:right">ENTRY</div><div style="text-align:right">EXIT</div><div style="text-align:right">RESULT</div></div>'
      + (histRows.length ? '' : leerZeile('No settled paper trades reported by /api/copy yet.'))
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
        + '<div style="' + M + '; font-size:10.5px; color:rgba(255,255,255,.6); margin-top:3px">' + esc(m.meta) + '</div></div>'
        + '<div style="display:flex; justify-content:flex-end"><svg width="78" height="26" viewBox="0 0 78 26"><polyline points="' + m.sparkPoints + '" fill="none" stroke="' + m.color + '" stroke-width="1.6" /></svg></div>'
        + '<div style="' + M + '; font-size:15px; text-align:right">' + m.priceLabel + '</div>'
        + '<div style="' + m.changeStyle + '">' + m.changeLabel + '</div>'
        + '<div style="' + M + '; font-size:12px; text-align:right; color:rgba(255,255,255,.55)">' + esc(m.ends) + '</div></div>'
      ).join('')
      + '</div>';
  }

  return '<div>'
    + '<div style="padding:20px 24px 16px; border-bottom:1px solid rgba(255,255,255,.09)">'
    + '<div style="' + M + '; font-size:11px; letter-spacing:.18em; color:#C8F542">PORTFOLIO · PAPER</div>'
    + '<div style="font-family:\'Instrument Serif\',serif; font-size:30px; line-height:1.1; margin-top:5px">What you would be holding</div></div>'
    + '<div style="display:grid; grid-template-columns:repeat(4,1fr); border-bottom:1px solid rgba(255,255,255,.09)">'
    + '<div style="padding:16px 20px; border-right:1px solid rgba(255,255,255,.09)"><div style="' + M + '; font-size:11px; letter-spacing:.14em; color:rgba(255,255,255,.6)">VALUE NOW</div><div style="' + M + '; font-size:26px; margin-top:8px">$' + num((+kp.equity).toFixed(2)) + '</div></div>'
    // Keine Rueckfallwerte in der Kennzahlenzeile: hier standen 14 offene
    // Positionen, +$28.60 unrealisiert und $312.40 freie Kasse, sobald das
    // Feld in der Antwort fehlte. Ein fehlendes Feld ist jetzt ein Strich.
    // Und das Vorzeichen des Unrealisierten kommt aus der Zahl, nicht aus dem
    // Template — vorher stand "+$" fest davor, in Gruen, auch bei Verlust.
    + '<div style="padding:16px 20px; border-right:1px solid rgba(255,255,255,.09)"><div style="' + M + '; font-size:11px; letter-spacing:.14em; color:rgba(255,255,255,.6)">OPEN POSITIONS</div><div style="' + M + '; font-size:26px; margin-top:8px">' + (kp.open_positions != null ? num(kp.open_positions) : '—') + '</div></div>'
    + '<div style="padding:16px 20px; border-right:1px solid rgba(255,255,255,.09)"><div style="' + M + '; font-size:11px; letter-spacing:.14em; color:rgba(255,255,255,.6)">UNREALISED</div><div style="' + M + '; font-size:26px; margin-top:8px; color:' + (kp.unrealized == null ? 'rgba(255,255,255,.6)' : +kp.unrealized >= 0 ? '#C8F542' : '#FF4545') + '">' + (kp.unrealized != null ? (+kp.unrealized >= 0 ? '+' : '-') + '$' + Math.abs(+kp.unrealized).toFixed(2) : '—') + '</div></div>'
    + '<div style="padding:16px 20px"><div style="' + M + '; font-size:11px; letter-spacing:.14em; color:rgba(255,255,255,.6)">CASH FREE</div><div style="' + M + '; font-size:26px; margin-top:8px">' + (kp.cash != null ? '$' + (+kp.cash).toFixed(2) : '—') + '</div></div>'
    + '</div>'
    + '<div style="display:flex; gap:6px; padding:16px 24px 0; flex-wrap:wrap">' + portTabs + '</div>'
    + body
    + '</div>';
}
