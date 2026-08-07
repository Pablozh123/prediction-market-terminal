// Leaderboard, Whale flow, Risk screen, Tracked — ported from the design reference.

import { esc, money, num } from '../util.js';
import { DEMO_WHALES, DEMO_RISK_WALLETS, DEMO_FRESH_CLUSTERS, DEMO_TIMING_CLUSTERS, DEMO_TRACKED_WALLETS } from '../demo_data.js';
import { renderClusterGraphics } from './cluster_graphics.js';

const M = "font-family:'JetBrains Mono',monospace";
const LBL9 = M + '; font-size:9px; letter-spacing:.14em; color:rgba(255,255,255,.42); margin-bottom:6px';
const HEAD_CELL = M + '; font-size:9.5px; letter-spacing:.14em; color:rgba(255,255,255,.45)';

function filterGroup(label, chipsHtml) {
  return '<div><div style="' + LBL9 + '">' + label + '</div><div style="display:flex; gap:6px; flex-wrap:wrap">' + chipsHtml + '</div></div>';
}

// ---------------------------------------------------------------- traders (leaderboard)
export function renderTraders(T) {
  const s = T.state;
  const tx = (t) => T.traderExtraOf(t);
  let tRows = T.traders.slice();
  let tCount = 0;
  if (s.traderQuery.trim()) {
    const tq = s.traderQuery.trim().toLowerCase();
    tRows = tRows.filter((t) => t.name.toLowerCase().indexOf(tq) >= 0 || t.wallet.toLowerCase().indexOf(tq) >= 0);
    tCount++;
  }
  if (s.traderActiveOnly) { tRows = tRows.filter((t) => tx(t).active >= 20); tCount++; }
  if (s.traderBotsOnly) { tRows = tRows.filter((t) => tx(t).bot >= s.tBotScore); tCount++; }
  if (s.tPnl !== 'all') { const v = { '500k': 500000, '1m': 1000000, '2m': 2000000, '5m': 5000000 }[s.tPnl]; tRows = tRows.filter((t) => t.pnl >= v); tCount++; }
  if (s.tVol !== 'all') { const v = { '10k': 10000, '100k': 100000, '1m': 1000000, '50m': 50000000 }[s.tVol]; tRows = tRows.filter((t) => t.vol >= v); tCount++; }
  if (s.tPos !== 'all') { const v = { '100': 100, '10k': 10000, '100k': 100000, '1m': 1000000 }[s.tPos]; tRows = tRows.filter((t) => tx(t).positions >= v); tCount++; }
  if (s.tTraits.length) { tRows = tRows.filter((t) => s.tTraits.every((tr) => tx(t).traits.indexOf(tr) >= 0)); tCount++; }
  if (s.tWin !== 'all') { const v = { '50': 0.5, '60': 0.6, '70': 0.7 }[s.tWin]; tRows = tRows.filter((t) => (t.win || 0) >= v); tCount++; }
  if (s.tClosed !== 'all') { const v = { '100': 100, '500': 500, '2000': 2000 }[s.tClosed]; tRows = tRows.filter((t) => (t.resolved || 0) >= v); tCount++; }
  if (s.tBal !== 'all') { const v = { '1k': 1000, '10k': 10000, '100k': 100000 }[s.tBal]; tRows = tRows.filter((t) => tx(t).balance >= v); tCount++; }
  if (s.tAge !== 'all') { tRows = s.tAge === '14' ? tRows.filter((t) => tx(t).ageDays < 14) : tRows.filter((t) => tx(t).ageDays > 365); tCount++; }
  if (s.tAssets !== 'all') { const v = { '100k': 100000, '1m': 1000000, '2m': 2000000 }[s.tAssets]; tRows = tRows.filter((t) => tx(t).assets >= v); tCount++; }
  const traderSorted = tRows.sort((a, b) => {
    if (s.traderRank === 'win') return (b.win || 0) - (a.win || 0);
    if (s.traderRank === 'score') return (b.score || 0) - (a.score || 0);
    if (s.traderRank === 'vol') return b.vol - a.vol;
    if (s.traderRank === 'roi') return (b.pnl / (b.vol || 1)) - (a.pnl / (a.vol || 1));
    return b.pnl - a.pnl;
  });

  const badge = tCount ? M + '; font-size:10px; color:#0A0D0F; background:#C8F542; border-radius:4px; padding:1px 7px' : 'display:none';
  const chevron = M + '; font-size:16px; color:rgba(255,255,255,.5); transition:transform .18s ease; transform:rotate(' + (s.traderFiltersOpen ? '90deg' : '0deg') + ')';
  const switchHtml = (on, patch) => T.toggle(on, patch);
  const asOf = T.liveData.leaderboard && T.liveData.leaderboard.as_of ? ' · snapshot ' + T.liveData.leaderboard.as_of : '';

  return '<div>'
    + '<div style="padding:20px 24px 14px; border-bottom:1px solid rgba(255,255,255,.09)">'
    + '<div style="display:flex; align-items:flex-end; justify-content:space-between; gap:20px">'
    + '<div><div style="' + M + '; font-size:10px; letter-spacing:.18em; color:#C8F542">LEADERBOARD</div>'
    + '<div style="font-family:\'Instrument Serif\',serif; font-size:30px; line-height:1.1; margin-top:5px">Who is actually good at this</div></div>'
    + '<div style="display:flex; align-items:center; gap:10px">'
    + '<input value="' + esc(s.traderQuery) + '" ' + T.inp((e) => T.setState({ traderQuery: e.target.value }), 'traderQuery') + ' placeholder="Search name or wallet…" style="background:#10151A; border:1px solid rgba(255,255,255,.16); border-radius:8px; padding:9px 12px; ' + M + '; font-size:12.5px; color:#fff; width:230px; outline:none" />'
    + '<div ' + T.act(() => T.setState({ traderQuery: '', tPnl: 'all', tVol: 'all', tPos: 'all', tTraits: [], tWin: 'all', tClosed: 'all', tBal: 'all', tAge: 'all', tAssets: 'all', traderActiveOnly: false, traderBotsOnly: false, traderPeriod: 'ALL', traderRank: 'pnl' })) + ' class="hv-bd32" style="font-size:12.5px; color:rgba(255,255,255,.6); border:1px solid rgba(255,255,255,.16); border-radius:8px; padding:9px 13px; cursor:pointer">Reset filters</div>'
    + '</div></div>'
    + '<div style="font-size:13px; color:rgba(255,255,255,.55); margin-top:10px; max-width:700px">Ranked from public Polymarket wallet data. Win rate counts resolved positions only; the sample size sits next to it so a hot streak cannot hide behind a percentage.</div>'

    + '<div style="display:flex; align-items:center; gap:20px; margin-top:14px; flex-wrap:wrap">'
    + '<div style="display:flex; align-items:center; gap:8px"><span style="' + LBL9.replace('; margin-bottom:6px', '') + '">VIEW</span><div style="display:flex; gap:6px; flex-wrap:wrap">'
    + [['table','Table'],['list','List'],['card','Cards']].map((o) => T.opt(o[1], s.traderView === o[0], { traderView: o[0] })).join('') + '</div></div>'
    + '<div style="display:flex; align-items:center; gap:8px"><span style="' + LBL9.replace('; margin-bottom:6px', '') + '">COLUMNS</span><div style="display:flex; gap:6px; flex-wrap:wrap">'
    + [['default','Default'],['research','Research'],['flow','Flow']].map((o) => T.opt(o[1], s.traderCols === o[0], { traderCols: o[0] })).join('') + '</div></div>'
    + '<div style="display:flex; align-items:center; gap:8px"><span style="' + LBL9.replace('; margin-bottom:6px', '') + '">PERIOD</span><div style="display:flex; gap:6px; flex-wrap:wrap">'
    + ['ALL','MONTH','WEEK','DAY'].map((p) => T.opt(p, s.traderPeriod === p, { traderPeriod: p })).join('') + '</div></div>'
    + '<div style="display:flex; align-items:center; gap:8px"><span style="' + LBL9.replace('; margin-bottom:6px', '') + '">RANK BY</span><div style="display:flex; gap:6px; flex-wrap:wrap">'
    + [T.tab('Smart', s.traderRank === 'score', { traderRank: 'score' }),
       T.tab('Profit', s.traderRank === 'pnl', { traderRank: 'pnl' }),
       T.tab('Volume', s.traderRank === 'vol', { traderRank: 'vol' }),
       T.tab('ROI', s.traderRank === 'roi', { traderRank: 'roi' }),
       T.tab('Win rate', s.traderRank === 'win', { traderRank: 'win' })].join('') + '</div></div>'
    + '<div style="display:flex; align-items:center; gap:8px">'
    + switchHtml(s.traderActiveOnly, { traderActiveOnly: !s.traderActiveOnly })
    + '<span style="font-size:12.5px; color:rgba(255,255,255,.7)">Active only</span>'
    + switchHtml(s.traderBotsOnly, { traderBotsOnly: !s.traderBotsOnly })
    + '<span style="font-size:12.5px; color:rgba(255,255,255,.7)">Bot-like only</span>'
    + '</div></div>'

    + '<div style="border:1px solid rgba(255,255,255,.09); border-radius:10px; margin-top:14px; overflow:hidden">'
    + '<div ' + T.act(() => T.setState({ traderFiltersOpen: !s.traderFiltersOpen })) + ' class="hv-el" style="display:flex; align-items:center; justify-content:space-between; padding:11px 15px; background:#10151A; cursor:pointer">'
    + '<div style="display:flex; align-items:center; gap:10px"><div style="font-size:13px">All filters</div><div style="' + badge + '">' + tCount + '</div></div>'
    + '<div style="' + chevron + '">›</div></div>'
    + (s.traderFiltersOpen ?
      '<div style="padding:16px; display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:16px 20px">'
      + filterGroup('PROFIT', [['all','All'],['500k','>$500k'],['1m','>$1m'],['2m','>$2m'],['5m','>$5m']].map((o) => T.opt(o[1], s.tPnl === o[0], { tPnl: o[0] })).join(''))
      + filterGroup('VOLUME', [['all','All'],['10k','>$10k'],['100k','>$100k'],['1m','>$1m'],['50m','>$50m']].map((o) => T.opt(o[1], s.tVol === o[0], { tVol: o[0] })).join(''))
      + filterGroup('OPEN POSITIONS VALUE', [['all','All'],['100','>$100'],['10k','>$10k'],['100k','>$100k'],['1m','>$1m']].map((o) => T.opt(o[1], s.tPos === o[0], { tPos: o[0] })).join(''))
      + filterGroup('TRAITS', ['Whales','Bot-like','Verified'].map((tr) => T.opt(tr, s.tTraits.indexOf(tr) >= 0, () => T.setState({ tTraits: s.tTraits.indexOf(tr) >= 0 ? s.tTraits.filter((x) => x !== tr) : s.tTraits.concat([tr]) }))).join(''))
      + filterGroup('WIN RATE', [['all','All'],['50','>50%'],['60','>60%'],['70','>70%']].map((o) => T.opt(o[1], s.tWin === o[0], { tWin: o[0] })).join(''))
      + filterGroup('MIN RESOLVED BETS', [['all','All'],['100','100+'],['500','500+'],['2000','2,000+']].map((o) => T.opt(o[1], s.tClosed === o[0], { tClosed: o[0] })).join(''))
      + filterGroup('BALANCE', [['all','All'],['1k','>$1k'],['10k','>$10k'],['100k','>$100k']].map((o) => T.opt(o[1], s.tBal === o[0], { tBal: o[0] })).join(''))
      + filterGroup('ACCOUNT AGE', [['all','All'],['14','Younger than 14d'],['365','Older than a year']].map((o) => T.opt(o[1], s.tAge === o[0], { tAge: o[0] })).join(''))
      + filterGroup('ASSETS', [['all','All'],['100k','>$100k'],['1m','>$1m'],['2m','>$2m']].map((o) => T.opt(o[1], s.tAssets === o[0], { tAssets: o[0] })).join(''))
      + '<div style="grid-column:span 2">'
      + '<div style="' + LBL9 + '">MINIMUM BOT SCORE</div>'
      + '<div style="display:flex; align-items:center; gap:10px">'
      + '<div ' + T.act(() => T.setState({ tBotScore: Math.max(0, s.tBotScore - 5) })) + ' style="width:28px; height:30px; flex:none; border:1px solid rgba(255,255,255,.16); border-radius:7px; display:flex; align-items:center; justify-content:center; ' + M + '; font-size:13px; color:rgba(255,255,255,.7); cursor:pointer">−</div>'
      + '<div style="width:70px; background:#10151A; border:1px solid rgba(255,255,255,.16); border-radius:7px; padding:6px 8px; ' + M + '; font-size:12px; text-align:center">' + s.tBotScore + '</div>'
      + '<div ' + T.act(() => T.setState({ tBotScore: Math.min(100, s.tBotScore + 5) })) + ' style="width:28px; height:30px; flex:none; border:1px solid rgba(255,255,255,.16); border-radius:7px; display:flex; align-items:center; justify-content:center; ' + M + '; font-size:13px; color:rgba(255,255,255,.7); cursor:pointer">+</div>'
      + '<span style="font-size:11.5px; color:rgba(255,255,255,.45)">only applies with bot-like filtering on</span>'
      + '</div></div>'
      + '<div><div style="' + LBL9 + '">EXTRA DATA (SLOWER)</div>'
      + '<div style="display:flex; flex-direction:column; gap:7px">'
      + [['positions','Fetch open positions'],['winrates','Fetch win rates'],['accounts','Fetch balances and account age']].map((o) => {
        const on = !!s.tEnrich[o[0]];
        const boxStyle = 'width:15px; height:15px; flex:none; border-radius:4px; display:flex; align-items:center; justify-content:center; font-size:10px; color:#0A0D0F; background:' + (on ? '#C8F542' : 'transparent') + '; border:1px solid ' + (on ? '#C8F542' : 'rgba(255,255,255,.25)');
        return '<div ' + T.act(() => T.setState({ tEnrich: Object.assign({}, s.tEnrich, { [o[0]]: !on }) })) + ' style="display:flex; align-items:center; gap:8px; cursor:pointer">'
          + '<div style="' + boxStyle + '">' + (on ? '✓' : '') + '</div>'
          + '<span style="font-size:12px; color:rgba(255,255,255,.7)">' + o[1] + '</span></div>';
      }).join('')
      + '</div></div>'
      + '</div>' : '')
    + '</div>'
    + '<div style="' + M + '; font-size:11px; color:rgba(255,255,255,.45); margin-top:12px">' + traderSorted.length + ' of ' + T.traders.length + ' wallets · period ' + s.traderPeriod + esc(asOf) + '</div>'
    + '</div>'

    + '<div style="display:grid; grid-template-columns:44px 1fr 120px 100px 118px 100px 92px; padding:10px 24px; border-bottom:1px solid rgba(255,255,255,.09); background:#10151A; ' + HEAD_CELL + '">'
    + '<div>#</div><div>WALLET</div><div style="text-align:right">PROFIT</div><div style="text-align:right">WIN RATE</div><div style="text-align:right">RESOLVED BETS</div><div style="text-align:right">VOLUME</div><div style="text-align:right">SCORE</div></div>'
    + traderSorted.map((t, i) => {
      const score = t.score;
      const avatarStyle = 'width:28px; height:28px; flex:none; border-radius:7px; background:#1C232B; border:1px solid rgba(255,255,255,.09); display:flex; align-items:center; justify-content:center; ' + M + '; font-size:12px; color:' + (score != null && score >= 80 ? '#C8F542' : 'rgba(255,255,255,.6)');
      const scoreStyle = M + '; font-size:12.5px; border-radius:5px; padding:3px 9px; ' + (score == null ? 'color:rgba(255,255,255,.4); border:1px solid rgba(255,255,255,.12)' : score >= 80 ? 'color:#0A0D0F; background:#C8F542' : score >= 60 ? 'color:rgba(255,255,255,.8); border:1px solid rgba(255,255,255,.2)' : 'color:#F5A623; border:1px solid rgba(245,166,35,.35)');
      return '<div ' + T.act(() => T.openWallet(t.name)) + ' class="hv-panel" style="display:grid; grid-template-columns:44px 1fr 120px 100px 118px 100px 92px; align-items:center; padding:13px 24px; border-bottom:1px solid rgba(255,255,255,.06); cursor:pointer; animation:rowIn .25s ease-out">'
        + '<div style="' + M + '; font-size:13px; color:rgba(255,255,255,.45)">' + (i + 1) + '</div>'
        + '<div style="display:flex; align-items:center; gap:10px; min-width:0">'
        + '<div style="' + avatarStyle + '">' + esc(t.name.charAt(0).toUpperCase()) + '</div>'
        + '<div style="min-width:0"><div style="font-size:13.5px">' + esc(t.name) + '</div>'
        + '<div style="' + M + '; font-size:10.5px; color:rgba(255,255,255,.45); margin-top:2px">' + esc(t.wallet + (t.tags ? ' · ' + t.tags : '')) + '</div></div></div>'
        + '<div style="' + M + '; font-size:14px; text-align:right; color:#C8F542">' + money(t.pnl) + '</div>'
        + '<div style="' + M + '; font-size:13px; text-align:right">' + (t.win != null ? Math.round(t.win * 100) + '%' : '—') + '</div>'
        + '<div style="' + M + '; font-size:12.5px; text-align:right; color:rgba(255,255,255,.55)">' + (t.resolved != null ? num(t.resolved) : '—') + '</div>'
        + '<div style="' + M + '; font-size:13px; text-align:right">' + money(t.vol) + '</div>'
        + '<div style="display:flex; justify-content:flex-end"><div style="' + scoreStyle + '">' + (score != null ? score : 'n/a') + '</div></div>'
        + '</div>';
    }).join('')
    + '</div>';
}

// ---------------------------------------------------------------- whale flow
export function renderWhale(T) {
  const s = T.state;
  let rows, walletCount, total, biggest;
  if (T.state.live === 'live' && T.tape.length) {
    const byWallet = {};
    T.tape.filter((t) => t.wallet !== '—').forEach((t) => {
      const w = byWallet[t.wallet] || (byWallet[t.wallet] = { name: t.wallet, wallet: t.wallet, prints: 0, total: 0, biggest: 0, buys: 0, sells: 0, cats: {} });
      w.prints++; w.total += t.size; w.biggest = Math.max(w.biggest, t.size);
      if (t.side.indexOf('BUY') === 0) w.buys++; else w.sells++;
      const m = T.markets.find((x) => x.title === t.market);
      const cat = m ? m.cat : 'Other';
      w.cats[cat] = (w.cats[cat] || 0) + 1;
    });
    rows = Object.values(byWallet).sort((a, b) => b.total - a.total).slice(0, 20).map((w) => ({
      name: w.name, wallet: w.wallet, prints: w.prints, total: w.total, biggest: w.biggest,
      lean: w.buys && w.sells ? 'TWO-WAY' : w.buys ? 'BUYING' : 'SELLING',
      cat: Object.entries(w.cats).sort((a, b) => b[1] - a[1])[0][0]
    }));
    walletCount = Object.keys(byWallet).length;
    total = T.tape.reduce((a, t) => a + t.size, 0);
    biggest = T.tape.reduce((a, t) => Math.max(a, t.size), 0);
  } else {
    rows = DEMO_WHALES;
    walletCount = 74; total = 18400000; biggest = 214000;
  }

  return '<div>'
    + '<div style="padding:20px 24px 16px; border-bottom:1px solid rgba(255,255,255,.09)">'
    + '<div style="' + M + '; font-size:10px; letter-spacing:.18em; color:#C8F542">WHALE FLOW</div>'
    + '<div style="font-family:\'Instrument Serif\',serif; font-size:30px; line-height:1.1; margin-top:5px">Who is moving the big money</div>'
    + '<div style="font-size:13px; color:rgba(255,255,255,.55); margin-top:9px; max-width:700px">The same prints as the tape, grouped by wallet, so one wallet buying twenty times reads as one story instead of twenty rows.</div></div>'
    + '<div style="display:grid; grid-template-columns:repeat(3,1fr); border-bottom:1px solid rgba(255,255,255,.09)">'
    + '<div style="padding:16px 20px; border-right:1px solid rgba(255,255,255,.09)"><div style="' + M + '; font-size:10px; letter-spacing:.14em; color:rgba(255,255,255,.45)">WALLETS PRINTING BIG</div><div style="' + M + '; font-size:26px; margin-top:8px">' + num(walletCount) + '</div></div>'
    + '<div style="padding:16px 20px; border-right:1px solid rgba(255,255,255,.09)"><div style="' + M + '; font-size:10px; letter-spacing:.14em; color:rgba(255,255,255,.45)">TOTAL MOVED · 24H</div><div style="' + M + '; font-size:26px; margin-top:8px">' + money(total) + '</div></div>'
    + '<div style="padding:16px 20px"><div style="' + M + '; font-size:10px; letter-spacing:.14em; color:rgba(255,255,255,.45)">BIGGEST SINGLE PRINT</div><div style="' + M + '; font-size:26px; margin-top:8px">' + money(biggest) + '</div></div>'
    + '</div>'
    + '<div style="display:grid; grid-template-columns:1fr 96px 116px 116px 150px 120px; padding:10px 24px; border-bottom:1px solid rgba(255,255,255,.09); background:#10151A; ' + HEAD_CELL + '">'
    + '<div>WALLET</div><div style="text-align:right">PRINTS</div><div style="text-align:right">TOTAL</div><div style="text-align:right">BIGGEST</div><div style="text-align:right">LEANING</div><div style="text-align:right">MOSTLY IN</div></div>'
    + rows.map((w) => {
      const leanStyle = M + '; font-size:11.5px; letter-spacing:.1em; text-align:right; color:' + (w.lean === 'BUYING' ? '#C8F542' : w.lean === 'SELLING' ? '#FF4545' : w.lean === 'FADING' ? '#F5A623' : 'rgba(255,255,255,.55)');
      return '<div ' + T.act(() => T.openWallet(w.name)) + ' class="hv-panel" style="display:grid; grid-template-columns:1fr 96px 116px 116px 150px 120px; align-items:center; padding:13px 24px; border-bottom:1px solid rgba(255,255,255,.06); cursor:pointer; animation:rowIn .25s ease-out">'
        + '<div><div style="font-size:13.5px">' + esc(w.name) + '</div>'
        + '<div style="' + M + '; font-size:10.5px; color:rgba(255,255,255,.45); margin-top:3px">' + esc(w.wallet) + '</div></div>'
        + '<div style="' + M + '; font-size:13px; text-align:right; color:rgba(255,255,255,.6)">' + w.prints + '</div>'
        + '<div style="' + M + '; font-size:14px; text-align:right">' + money(w.total) + '</div>'
        + '<div style="' + M + '; font-size:13px; text-align:right; color:rgba(255,255,255,.6)">' + money(w.biggest) + '</div>'
        + '<div style="' + leanStyle + '">' + esc(w.lean) + '</div>'
        + '<div style="' + M + '; font-size:11.5px; text-align:right; color:rgba(255,255,255,.5)">' + esc(w.cat) + '</div></div>';
    }).join('')
    + '</div>';
}

// ---------------------------------------------------------------- risk screen
export function renderRisk(T) {
  const s = T.state;
  const riskFiltered = T.risks.filter((r) => s.riskFilter === 'all' || r.sev === s.riskFilter);
  const live = T.liveData.risk;
  const kpis = live && live.kpis ? [
    { label: 'EVENTS SCREENED', value: String(live.kpis.events_screened) },
    { label: 'HIGH-RISK EVENTS', value: String(live.kpis.high_risk_events), amber: true },
    { label: 'HIGH-RISK WALLETS', value: String(live.kpis.high_risk_wallets), amber: true },
    { label: 'FRESH-WALLET CLUSTERS', value: String(live.kpis.fresh_clusters) },
    { label: 'COORDINATED CLUSTERS', value: String(live.kpis.coordinated_clusters) }
  ] : [
    { label: 'EVENTS SCREENED', value: '412' },
    { label: 'HIGH-RISK EVENTS', value: '2', amber: true },
    { label: 'HIGH-RISK WALLETS', value: '5', amber: true },
    { label: 'FRESH-WALLET CLUSTERS', value: '4' },
    { label: 'COORDINATED CLUSTERS', value: '3' }
  ];
  const walletRows = live && live.wallets ? live.wallets : DEMO_RISK_WALLETS;

  let body = '';
  if (s.riskView === 'events') {
    body = '<div>'
      + '<div style="display:flex; gap:6px; padding:14px 24px 0; flex-wrap:wrap">'
      + [T.tab('All', s.riskFilter === 'all', { riskFilter: 'all' }),
         T.tab('High', s.riskFilter === 'high', { riskFilter: 'high' }),
         T.tab('Watch', s.riskFilter === 'medium', { riskFilter: 'medium' })].join('')
      + '</div>'
      + '<div style="padding:18px 24px; display:grid; grid-template-columns:repeat(2,1fr); gap:14px">'
      + riskFiltered.map((r0) => {
        const r = T.riskCardView(r0);
        return '<div ' + r.act + ' class="hv-bd20" style="background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:12px; padding:16px 18px; cursor:pointer; animation:rowIn .25s ease-out">'
          + '<div style="display:flex; align-items:center; justify-content:space-between; gap:12px">'
          + '<div style="' + r.kindStyle + '">' + esc(r.kind) + '</div>'
          + '<div style="display:flex; align-items:baseline; gap:6px"><div style="' + r.scoreStyle + '">' + r.score + '</div>'
          + '<div style="' + M + '; font-size:10px; color:rgba(255,255,255,.35)">/100</div></div></div>'
          + '<div style="font-size:15px; margin-top:10px; line-height:1.35">' + esc(r.market) + '</div>'
          + '<div style="font-size:13px; color:rgba(255,255,255,.6); margin-top:7px; line-height:1.45">' + esc(r.detail) + '</div>'
          + '<div style="height:1px; background:rgba(255,255,255,.07); margin:14px 0 12px"></div>'
          + '<div style="display:flex; gap:22px">'
          + [['WALLETS', r.wallets], ['NOTIONAL', r.notional], ['WINDOW', r.window], ['VENUE', r.venue]].map((p) =>
            '<div><div style="' + M + '; font-size:9.5px; letter-spacing:.12em; color:rgba(255,255,255,.4)">' + p[0] + '</div><div style="' + M + '; font-size:14px; margin-top:3px">' + esc(String(p[1])) + '</div></div>'
          ).join('')
          + '</div></div>';
      }).join('')
      + '</div></div>';
  } else if (s.riskView === 'wallets') {
    body = '<div style="border:1px solid rgba(255,255,255,.09); border-radius:12px; margin:16px 24px; overflow:hidden">'
      + '<div style="display:grid; grid-template-columns:1fr 96px 110px 110px 130px 96px; gap:10px; padding:9px 16px; background:#10151A; border-bottom:1px solid rgba(255,255,255,.09); ' + M + '; font-size:9px; letter-spacing:.12em; color:rgba(255,255,255,.45)">'
      + '<div>WALLET</div><div style="text-align:right">SCORE</div><div style="text-align:right">WHALE PRINTS</div><div style="text-align:right">NOTIONAL</div><div style="text-align:right">FIRST SEEN</div><div style="text-align:right">CLUSTER</div></div>'
      + walletRows.map((w) => {
        const scoreStyle = M + '; font-size:12px; border-radius:5px; padding:3px 9px; ' + (w.score >= 70 ? 'color:#0A0D0F; background:#F5A623' : w.score >= 55 ? 'color:#F5A623; border:1px solid rgba(245,166,35,.35)' : 'color:rgba(255,255,255,.7); border:1px solid rgba(255,255,255,.18)');
        return '<div ' + T.act(() => T.openWallet(w.wallet)) + ' class="hv-panel" style="display:grid; grid-template-columns:1fr 96px 110px 110px 130px 96px; gap:10px; align-items:center; padding:11px 16px; border-bottom:1px solid rgba(255,255,255,.06); ' + M + '; font-size:12.5px; cursor:pointer">'
          + '<div><span style="font-family:\'Inter\',sans-serif; font-size:13px">' + esc(w.wallet) + '</span> <span style="color:rgba(255,255,255,.4); font-size:11px">· ' + esc(w.context) + '</span></div>'
          + '<div style="display:flex; justify-content:flex-end"><div style="' + scoreStyle + '">' + w.score + '</div></div>'
          + '<div style="text-align:right; color:rgba(255,255,255,.6)">' + w.prints + '</div>'
          + '<div style="text-align:right">' + esc(String(w.notional)) + '</div>'
          + '<div style="text-align:right; color:rgba(255,255,255,.6)">' + esc(w.firstSeen) + '</div>'
          + '<div style="text-align:right; color:rgba(255,255,255,.6)">' + esc(w.cluster) + '</div></div>';
      }).join('')
      + '</div>';
  } else if (s.riskView === 'fresh') {
    const freshRows = live && live.fresh && live.fresh.length ? live.fresh : DEMO_FRESH_CLUSTERS;
    body = '<div style="padding:16px 24px; display:grid; grid-template-columns:repeat(2,1fr); gap:14px">'
      + freshRows.map((c) =>
        '<div style="background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:12px; padding:16px 18px">'
        + '<div style="display:flex; align-items:center; justify-content:space-between">'
        + '<div style="' + M + '; font-size:10.5px; letter-spacing:.12em; color:#F5A623">' + esc(c.tag) + '</div>'
        + '<div style="' + M + '; font-size:16px; color:#F5A623">' + c.score + '</div></div>'
        + '<div style="font-size:14.5px; margin-top:9px">' + esc(c.market) + '</div>'
        + '<div style="font-size:12.5px; color:rgba(255,255,255,.6); margin-top:6px; line-height:1.45">' + esc(c.detail) + '</div>'
        + '<div style="display:flex; gap:7px; margin-top:12px; flex-wrap:wrap">'
        + c.wallets.map((w) => '<div style="' + M + '; font-size:10.5px; color:rgba(255,255,255,.65); background:#161C22; border:1px solid rgba(255,255,255,.09); border-radius:5px; padding:3px 8px">' + esc(w) + '</div>').join('')
        + '</div></div>'
      ).join('')
      + '</div>';
  } else if (s.riskView === 'timing') {
    const timingRows = live && live.timing && live.timing.length ? live.timing : DEMO_TIMING_CLUSTERS;
    body = '<div style="border:1px solid rgba(255,255,255,.09); border-radius:12px; margin:16px 24px; overflow:hidden">'
      + '<div style="display:grid; grid-template-columns:1fr 100px 110px 120px 120px; gap:10px; padding:9px 16px; background:#10151A; border-bottom:1px solid rgba(255,255,255,.09); ' + M + '; font-size:9px; letter-spacing:.12em; color:rgba(255,255,255,.45)">'
      + '<div>MARKET</div><div style="text-align:right">WALLETS</div><div style="text-align:right">WINDOW</div><div style="text-align:right">NOTIONAL</div><div style="text-align:right">SAME SIDE</div></div>'
      + timingRows.map((c) =>
        '<div style="display:grid; grid-template-columns:1fr 100px 110px 120px 120px; gap:10px; align-items:center; padding:11px 16px; border-bottom:1px solid rgba(255,255,255,.06); ' + M + '; font-size:12.5px">'
        + '<div style="font-family:\'Inter\',sans-serif; font-size:13px">' + esc(c.market) + '</div>'
        + '<div style="text-align:right">' + c.wallets + '</div>'
        + '<div style="text-align:right; color:rgba(255,255,255,.6)">' + esc(c.window) + '</div>'
        + '<div style="text-align:right">' + esc(c.notional) + '</div>'
        + '<div style="text-align:right; ' + M + '; font-size:12px; color:' + (c.same ? '#F5A623' : 'rgba(255,255,255,.5)') + '">' + (c.same ? 'all one side' : 'mixed') + '</div></div>'
      ).join('')
      + '</div>';
  } else {
    // Keine Demo-Cluster, solange echte fehlen: erfundene Wallet-Gruppen auf
    // einem Screen, der Verdacht behauptet, sind schlimmer als eine leere
    // Flaeche. Die Grafik darueber sagt bereits, woran es liegt.
    const networkRows = live ? (live.network || []) : [];
    body = '<div style="padding:16px 24px">'
      + renderClusterGraphics(live)
      + (networkRows.length
        ? '<div style="font-size:12.5px; color:rgba(255,255,255,.55); line-height:1.5; max-width:820px">Wallets that repeatedly trade the same markets. The rule that produced the current graph is stated above it: the screen tries the strict rule first and falls back only when it finds nothing.</div>'
        : '')
      + '<div style="display:grid; grid-template-columns:repeat(3,1fr); gap:14px; margin-top:14px">'
      + networkRows.map((n) =>
        '<div style="background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:12px; padding:16px 18px">'
        + '<div style="display:flex; align-items:center; justify-content:space-between">'
        + '<div style="font-size:14.5px; font-weight:600">' + esc(n.name) + '</div>'
        + '<div style="' + M + '; font-size:11px; color:rgba(255,255,255,.5)">' + n.size + ' wallets</div></div>'
        + '<div style="font-size:12.5px; color:rgba(255,255,255,.6); margin-top:8px; line-height:1.45">' + esc(n.story) + '</div>'
        + '<div style="display:flex; gap:20px; margin-top:12px">'
        + '<div><div style="' + M + '; font-size:9.5px; letter-spacing:.12em; color:rgba(255,255,255,.4)">SHARED MARKETS</div><div style="' + M + '; font-size:14px; margin-top:3px">' + esc(n.shared) + '</div></div>'
        + '<div><div style="' + M + '; font-size:9.5px; letter-spacing:.12em; color:rgba(255,255,255,.4)">PAIRED NOTIONAL</div><div style="' + M + '; font-size:14px; margin-top:3px">' + esc(n.notional) + '</div></div>'
        + '</div></div>'
      ).join('')
      + '</div></div>';
  }

  return '<div>'
    + '<div style="padding:20px 24px 14px; border-bottom:1px solid rgba(255,255,255,.09)">'
    + '<div style="display:flex; align-items:flex-end; justify-content:space-between; gap:20px">'
    + '<div><div style="' + M + '; font-size:10px; letter-spacing:.18em; color:#F5A623">RISK SCREEN</div>'
    + '<div style="font-family:\'Instrument Serif\',serif; font-size:30px; line-height:1.1; margin-top:5px">Trades that look like someone knew</div></div>'
    + '<div style="display:flex; align-items:center; gap:10px">'
    + T.toggle(s.riskAgeCheck, { riskAgeCheck: !s.riskAgeCheck })
    + '<span style="font-size:12.5px; color:rgba(255,255,255,.7)">Check real account ages (slower)</span>'
    + '</div></div>'
    + '<div style="font-size:13px; color:rgba(255,255,255,.55); margin-top:10px; max-width:760px">Best-effort screen on public trade data — research leads, not legal findings. Sports odds and weather are excluded: game results and weather models cannot be traded on early.</div>'
    + '<div style="display:flex; gap:7px; margin-top:12px; flex-wrap:wrap">'
    + '<div style="' + M + '; font-size:10px; color:rgba(255,255,255,.45); border:1px solid rgba(255,255,255,.12); border-radius:5px; padding:4px 9px">UNDER 40 · LOW</div>'
    + '<div style="' + M + '; font-size:10px; color:rgba(255,255,255,.6); border:1px solid rgba(255,255,255,.18); border-radius:5px; padding:4px 9px">40–54 · ELEVATED</div>'
    + '<div style="' + M + '; font-size:10px; color:#F5A623; border:1px solid rgba(245,166,35,.3); border-radius:5px; padding:4px 9px">55–69 · MEDIUM</div>'
    + '<div style="' + M + '; font-size:10px; color:#0A0D0F; background:#F5A623; border-radius:5px; padding:4px 9px">70 AND UP · HIGH</div>'
    + '</div></div>'

    + '<div style="display:grid; grid-template-columns:repeat(5,1fr); border-bottom:1px solid rgba(255,255,255,.09)">'
    + kpis.map((k, i) =>
      '<div style="padding:14px 24px' + (i < 4 ? '; border-right:1px solid rgba(255,255,255,.09)' : '') + '">'
      + '<div style="' + HEAD_CELL + '">' + k.label + '</div>'
      + '<div style="' + M + '; font-size:22px; margin-top:7px; color:' + (k.amber ? '#F5A623' : '#ffffff') + '">' + k.value + '</div></div>'
    ).join('')
    + '</div>'

    + '<div style="display:flex; gap:6px; padding:16px 24px 0; flex-wrap:wrap">'
    + [['events','Events'],['wallets','Wallets'],['fresh','Fresh-wallet clusters'],['timing','Coordinated timing'],['network','Co-trading network']].map((o) => T.tab(o[1], s.riskView === o[0], { riskView: o[0] })).join('')
    + '</div>'
    + body
    + '</div>';
}

// ---------------------------------------------------------------- tracked
export function trackWalletCards(T) {
  const live = T.liveData.track;
  if (live && live.wallets && live.wallets.length) {
    return live.wallets.map((w) => ({
      name: w.name || w.wallet,
      wallet: w.wallet && w.wallet.length > 12 ? w.wallet.slice(0, 6) + '…' + w.wallet.slice(-4) : w.wallet,
      grade: w.grade || '—',
      pnl: w.pnl != null ? (w.pnl >= 0 ? '+' : '-') + money(Math.abs(w.pnl)) : '—',
      pnlRaw: w.pnl,
      last: '—',
      openAs: w.name || w.wallet,
      pnlLabel: 'ALL-TIME PROFIT'
    }));
  }
  return DEMO_TRACKED_WALLETS.map((w) => ({ name: w.name, wallet: w.wallet, grade: w.grade, pnl: w.pnl, pnlRaw: w.pnl.charAt(0) === '+' ? 1 : -1, last: w.last, openAs: w.name, pnlLabel: '30D PROFIT' }));
}

export function trackWatchRows(T) {
  const live = T.liveData.track;
  if (live && live.watchlist && live.watchlist.length) {
    return live.watchlist.map((item) => {
      const m = T.markets.find((x) => x.id === item.market_key || x.title === item.title);
      if (m) return T.marketView(m);
      return {
        title: item.title, meta: (item.platform || '').toUpperCase() + ' · WATCHLIST',
        sparkPoints: '', color: 'rgba(255,255,255,.3)', priceLabel: '—', changeLabel: '—',
        changeStyle: M + '; font-size:13px; text-align:right; color:rgba(255,255,255,.4)',
        volLabel: '—', ends: '—', act: ''
      };
    });
  }
  return [T.markets[0], T.markets[1], T.markets[7], T.markets[6]].filter(Boolean).map((m) => T.marketView(m));
}

export function renderTrack(T) {
  const watch = trackWatchRows(T);
  const cards = trackWalletCards(T);
  return '<div>'
    + '<div style="padding:20px 24px 16px; border-bottom:1px solid rgba(255,255,255,.09)">'
    + '<div style="' + M + '; font-size:10px; letter-spacing:.18em; color:#C8F542">TRACKED</div>'
    + '<div style="font-family:\'Instrument Serif\',serif; font-size:30px; line-height:1.1; margin-top:5px">Your wallets and your watchlist</div></div>'
    + '<div style="padding:18px 24px; border-bottom:1px solid rgba(255,255,255,.09)">'
    + '<div style="' + M + '; font-size:10.5px; letter-spacing:.14em; color:rgba(255,255,255,.55); margin-bottom:13px">WALLETS YOU FOLLOW</div>'
    + (cards.length ? '<div style="display:grid; grid-template-columns:repeat(3,1fr); gap:14px">'
    + cards.map((w) => {
      const gradeStyle = M + '; font-size:12px; border-radius:5px; padding:2px 9px; ' + (w.grade === 'A' || w.grade === 'A+' ? 'color:#0A0D0F; background:#C8F542' : w.grade === '—' ? 'color:rgba(255,255,255,.45); border:1px solid rgba(255,255,255,.14)' : 'color:#F5A623; border:1px solid rgba(245,166,35,.35)');
      const pnlText = typeof w.pnlRaw === 'number' && T.liveData.track ? (w.pnlRaw >= 0 ? '+' : '-') + money(Math.abs(w.pnlRaw)) : w.pnl;
      const pnlStyle = M + '; font-size:14px; margin-top:3px; color:' + (String(pnlText).charAt(0) === '+' ? '#C8F542' : String(pnlText).charAt(0) === '-' ? '#FF4545' : 'rgba(255,255,255,.5)');
      return '<div ' + T.act(() => T.openWallet(w.openAs)) + ' class="hv-bd20" style="background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:12px; padding:15px 17px; cursor:pointer">'
        + '<div style="display:flex; align-items:center; justify-content:space-between">'
        + '<div style="font-size:15px">' + esc(w.name) + '</div>'
        + '<div style="' + gradeStyle + '">' + esc(w.grade) + '</div></div>'
        + '<div style="' + M + '; font-size:10.5px; color:rgba(255,255,255,.45); margin-top:4px">' + esc(w.wallet) + '</div>'
        + '<div style="display:flex; gap:20px; margin-top:14px">'
        + '<div><div style="' + M + '; font-size:9.5px; letter-spacing:.12em; color:rgba(255,255,255,.4)">' + (w.pnlLabel || '30D PROFIT') + '</div><div style="' + pnlStyle + '">' + esc(String(pnlText)) + '</div></div>'
        + '<div><div style="' + M + '; font-size:9.5px; letter-spacing:.12em; color:rgba(255,255,255,.4)">LAST TRADE</div><div style="' + M + '; font-size:14px; margin-top:3px">' + esc(w.last) + '</div></div>'
        + '</div></div>';
    }).join('')
    + '</div>' : '<div style="' + M + '; font-size:11.5px; color:rgba(255,255,255,.4); padding:14px 0">No followed wallets on this machine yet — follow one from the leaderboard in the Streamlit terminal and it appears here.</div>')
    + '</div>'
    + '<div style="padding:18px 24px">'
    + '<div style="' + M + '; font-size:10.5px; letter-spacing:.14em; color:rgba(255,255,255,.55); margin-bottom:13px">MARKETS ON YOUR WATCHLIST</div>'
    + watch.map((m) =>
      '<div ' + m.act + ' class="hv-panel" style="display:grid; grid-template-columns:1fr 96px 88px 96px 108px; align-items:center; padding:12px 0; border-bottom:1px solid rgba(255,255,255,.06); cursor:pointer">'
      + '<div><div style="font-size:13.5px">' + esc(m.title) + '</div>'
      + '<div style="' + M + '; font-size:10.5px; color:rgba(255,255,255,.45); margin-top:3px">' + esc(m.meta) + '</div></div>'
      + '<div style="display:flex; justify-content:flex-end"><svg width="78" height="26" viewBox="0 0 78 26"><polyline points="' + m.sparkPoints + '" fill="none" stroke="' + m.color + '" stroke-width="1.6" /></svg></div>'
      + '<div style="' + M + '; font-size:15px; text-align:right">' + m.priceLabel + '</div>'
      + '<div style="' + m.changeStyle + '">' + m.changeLabel + '</div>'
      + '<div style="' + M + '; font-size:12px; text-align:right; color:rgba(255,255,255,.55)">' + esc(m.ends) + '</div></div>'
    ).join('')
    + '</div></div>';
}
