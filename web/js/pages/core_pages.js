// Overview, Markets, Live tape, Cross-venue, Resolved — markup ported 1:1
// from the design reference; data flows through the Terminal instance (T).

import { esc, money, num } from '../util.js';
import { DEMO_RESOLVED } from '../demo_data.js';

const M = "font-family:'JetBrains Mono',monospace";
const LBL9 = M + '; font-size:9px; letter-spacing:.14em; color:rgba(255,255,255,.42); margin-bottom:6px';
const HEAD_CELL = M + '; font-size:9.5px; letter-spacing:.14em; color:rgba(255,255,255,.45)';

function filterGroup(label, chipsHtml) {
  return '<div><div style="' + LBL9 + '">' + label + '</div><div style="display:flex; gap:6px; flex-wrap:wrap">' + chipsHtml + '</div></div>';
}

function marketRowHtml(v) {
  return '<div ' + v.act + ' class="hv-panel" style="display:grid; grid-template-columns:1fr 96px 88px 96px 108px 108px; align-items:center; padding:13px 24px; border-bottom:1px solid rgba(255,255,255,.06); cursor:pointer; animation:rowIn .25s ease-out">'
    + '<div style="padding-right:20px">'
    + '<div style="font-size:13.5px; line-height:1.35">' + esc(v.title) + '</div>'
    + '<div style="' + M + '; font-size:10.5px; color:rgba(255,255,255,.45); margin-top:3px">' + esc(v.meta) + '</div></div>'
    + '<div style="display:flex; justify-content:flex-end"><svg width="78" height="26" viewBox="0 0 78 26"><polyline points="' + v.sparkPoints + '" fill="none" stroke="' + v.color + '" stroke-width="1.6" /></svg></div>'
    + '<div style="' + M + '; font-size:15px; text-align:right">' + v.priceLabel + '</div>'
    + '<div style="' + v.changeStyle + '">' + v.changeLabel + '</div>'
    + '<div style="' + M + '; font-size:13px; text-align:right">' + v.volLabel + '</div>'
    + '<div style="' + M + '; font-size:12px; text-align:right; color:rgba(255,255,255,.55)">' + esc(v.ends) + '</div></div>';
}

// ---------------------------------------------------------------- overview
export function renderOverview(T) {
  const s = T.state;
  const movers = T.markets.slice().sort((a, b) => Math.abs(b.chg) - Math.abs(a.chg)).slice(0, 5).map((m) => T.marketView(m));
  const topRisks = T.risks.slice(0, 3).map((r) => T.riskCardView(r));
  const tapeFiltered = T.tapeFiltered();
  const tapeRows = tapeFiltered.slice(0, 6).map((t) => T.tapeRowView(t));
  const totalVol = T.markets.reduce((a, m) => a + m.vol, 0);
  const pmCount = T.markets.filter((m) => m.venue === 'Polymarket').length;
  const ksCount = T.markets.length - pmCount;
  const whalePrints = T.tape.filter((t) => t.size >= s.setWhale).length;
  const whaleWallets = new Set(T.tape.filter((t) => t.size >= s.setWhale && t.wallet !== '—').map((t) => t.wallet)).size;
  const bestTrader = T.traders.slice().sort((a, b) => b.pnl - a.pnl)[0];
  const pmVol = T.markets.filter((m) => m.venue === 'Polymarket').reduce((a, m) => a + m.vol, 0);
  const ksVol = totalVol - pmVol;
  const pmShare = totalVol ? Math.round((pmVol / totalVol) * 100) : 50;

  const tapeFilters = [
    T.chip('≥ $2.5K', s.tapeMin === 2500 && !s.tapeTracked, { tapeMin: 2500, tapeTracked: false }),
    T.chip('≥ $10K', s.tapeMin === 10000 && !s.tapeTracked, { tapeMin: 10000, tapeTracked: false }),
    T.chip('TRACKED ONLY', s.tapeTracked, { tapeTracked: true, tapeMin: 2500 })
  ].join('');
  const demoMode = s.live !== 'live';

  return '<div>'
    + '<div style="padding:24px 24px 20px; border-bottom:1px solid rgba(255,255,255,.09)">'
    + '<div style="font-family:\'Instrument Serif\',serif; font-size:34px; line-height:1.08">Where the money moved <em style="color:#C8F542">in the last hour.</em></div>'
    + '<div style="font-size:14px; color:rgba(255,255,255,.66); margin-top:7px; max-width:660px">Public wallet flow on Polymarket and Kalshi. No account, no orders — research only.</div></div>'

    + '<div style="display:grid; grid-template-columns:repeat(4,1fr); border-bottom:1px solid rgba(255,255,255,.09)">'
    + kpiCell('MARKETS TRACKED', num(demoMode ? 1284 : T.markets.length), demoMode ? '982 Polymarket · 302 Kalshi' : num(pmCount) + ' Polymarket · ' + num(ksCount) + ' Kalshi', true)
    + kpiCell('VOLUME · 24H', money(demoMode ? 84200000 : totalVol), demoMode ? '<span style="color:#C8F542">+12.4% vs yesterday</span>' : num(T.markets.length) + ' markets in sample', true)
    + kpiCell('TRADES OVER $2.5K', num(demoMode ? 213 : whalePrints), 'from ' + num(demoMode ? 74 : whaleWallets) + ' wallets', true)
    + kpiCell('BEST WALLET · ALL TIME', money(bestTrader ? bestTrader.pnl : 22050000), esc((bestTrader ? bestTrader.name : 'Theo4') + ' · ' + (bestTrader ? bestTrader.wallet : '0x9f3a…21c')), false)
    + '</div>'

    + '<div style="display:grid; grid-template-columns:1.45fr 1fr">'
    + '<div style="border-right:1px solid rgba(255,255,255,.09)">'
    + '<div style="display:flex; align-items:center; justify-content:space-between; padding:12px 20px; border-bottom:1px solid rgba(255,255,255,.09); background:#10151A">'
    + '<div style="' + M + '; font-size:11px; letter-spacing:.16em; color:#C8F542">BIGGEST MOVES · 1H</div>'
    + '<div ' + T.act(() => T.go('markets')) + ' class="hv-lime" style="' + M + '; font-size:11px; color:rgba(255,255,255,.45); cursor:pointer">ALL ' + num(T.markets.length === 12 ? 1284 : T.markets.length) + ' →</div></div>'
    + movers.map((m) =>
      '<div ' + m.act + ' class="hv-panel" style="display:grid; grid-template-columns:1fr 78px 74px 88px; gap:12px; align-items:center; padding:13px 20px; border-bottom:1px solid rgba(255,255,255,.06); cursor:pointer; animation:rowIn .3s ease-out">'
      + '<div><div style="font-size:13.5px; line-height:1.35">' + esc(m.title) + '</div>'
      + '<div style="' + M + '; font-size:10.5px; color:rgba(255,255,255,.45); margin-top:3px">' + esc(m.meta) + '</div></div>'
      + '<svg width="78" height="26" viewBox="0 0 78 26"><polyline points="' + m.sparkPoints + '" fill="none" stroke="' + m.color + '" stroke-width="1.6" /></svg>'
      + '<div style="' + M + '; font-size:15px; text-align:right">' + m.priceLabel + '</div>'
      + '<div style="' + m.changeStyle + '">' + m.changeLabel + '</div></div>'
    ).join('')
    + '</div>'

    + '<div>'
    + '<div style="display:flex; align-items:center; justify-content:space-between; padding:12px 20px; border-bottom:1px solid rgba(255,255,255,.09); background:#10151A">'
    + '<div style="' + M + '; font-size:11px; letter-spacing:.16em; color:#F5A623">RISK FLAGS · TODAY</div>'
    + '<div ' + T.act(() => T.go('risk')) + ' class="hv-amber" style="' + M + '; font-size:11px; color:rgba(255,255,255,.45); cursor:pointer">SCREEN →</div></div>'
    + topRisks.map((r) =>
      '<div ' + r.act + ' class="hv-panel" style="padding:14px 20px; border-bottom:1px solid rgba(255,255,255,.06); cursor:pointer">'
      + '<div style="display:flex; align-items:baseline; justify-content:space-between; gap:10px">'
      + '<div style="' + r.kindStyle + '">' + esc(r.kind) + '</div>'
      + '<div style="' + r.scoreStyle + '">' + r.score + '</div></div>'
      + '<div style="font-size:13px; margin-top:5px; line-height:1.35">' + esc(r.market) + '</div>'
      + '<div style="' + M + '; font-size:11px; color:rgba(255,255,255,.45); margin-top:4px">' + esc(r.detail) + '</div></div>'
    ).join('')
    + '<div style="display:flex; align-items:center; justify-content:space-between; padding:12px 20px; border-bottom:1px solid rgba(255,255,255,.09); background:#10151A">'
    + '<div style="' + M + '; font-size:11px; letter-spacing:.16em; color:#C8F542">VOLUME BY VENUE</div>'
    + '<div style="' + M + '; font-size:11px; color:rgba(255,255,255,.45)">24H</div></div>'
    + '<div style="padding:16px 20px; display:flex; flex-direction:column; gap:13px">'
    + '<div><div style="display:flex; justify-content:space-between; ' + M + '; font-size:11.5px; margin-bottom:6px"><span style="color:rgba(255,255,255,.66)">POLYMARKET</span><span>' + money(demoMode ? 61400000 : pmVol) + '</span></div>'
    + '<div style="height:9px; background:rgba(255,255,255,.07); border-radius:2px"><div style="width:' + pmShare + '%; height:9px; background:#C8F542; border-radius:2px"></div></div></div>'
    + '<div><div style="display:flex; justify-content:space-between; ' + M + '; font-size:11.5px; margin-bottom:6px"><span style="color:rgba(255,255,255,.66)">KALSHI</span><span>' + money(demoMode ? 22800000 : ksVol) + '</span></div>'
    + '<div style="height:9px; background:rgba(255,255,255,.07); border-radius:2px"><div style="width:' + (100 - pmShare) + '%; height:9px; background:#4F8EF7; border-radius:2px"></div></div></div>'
    + '</div></div></div>'

    + '<div style="border-top:1px solid rgba(255,255,255,.09)">'
    + '<div style="display:flex; align-items:center; justify-content:space-between; padding:12px 20px; border-bottom:1px solid rgba(255,255,255,.09); background:#10151A">'
    + '<div style="' + M + '; font-size:11px; letter-spacing:.16em; color:#C8F542">LARGE TRADES · LIVE TAPE</div>'
    + '<div style="display:flex; gap:6px">' + tapeFilters + '</div></div>'
    + '<div style="display:grid; grid-template-columns:96px 150px 1fr 74px 84px 100px; padding:9px 20px; border-bottom:1px solid rgba(255,255,255,.09); ' + HEAD_CELL + '">'
    + '<div>TIME</div><div>WALLET</div><div>MARKET</div><div>SIDE</div><div style="text-align:right">PRICE</div><div style="text-align:right">SIZE</div></div>'
    + tapeRows.map((t) =>
      '<div ' + t.act + ' class="hv-panel" style="display:grid; grid-template-columns:96px 150px 1fr 74px 84px 100px; align-items:center; padding:11px 20px; border-bottom:1px solid rgba(255,255,255,.06); ' + M + '; font-size:12.5px; cursor:pointer; animation:rowIn .3s ease-out">'
      + '<div style="color:rgba(255,255,255,.55)">' + esc(t.ago) + '</div>'
      + '<div>' + esc(t.wallet) + '</div>'
      + '<div style="font-family:\'Inter\',sans-serif; font-size:13px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; padding-right:12px">' + esc(t.market) + '</div>'
      + '<div style="' + t.sideStyle + '">' + esc(t.side) + '</div>'
      + '<div style="text-align:right">' + esc(t.price) + '</div>'
      + '<div style="text-align:right">' + t.size + '</div></div>'
    ).join('')
    + '<div style="padding:26px; text-align:center; ' + M + '; font-size:11px; color:rgba(255,255,255,.35)">Public data only · updated every 15 seconds</div>'
    + '</div></div>';
}

function kpiCell(label, value, sub, borderRight) {
  return '<div style="padding:16px 20px' + (borderRight ? '; border-right:1px solid rgba(255,255,255,.09)' : '') + '">'
    + '<div style="' + M + '; font-size:10px; letter-spacing:.14em; color:rgba(255,255,255,.45)">' + label + '</div>'
    + '<div style="' + M + '; font-size:26px; margin-top:8px">' + value + '</div>'
    + '<div style="' + M + '; font-size:11px; color:rgba(255,255,255,.45); margin-top:4px">' + sub + '</div></div>';
}

// ---------------------------------------------------------------- markets
export function renderMarkets(T) {
  const s = T.state;
  const catSet = [];
  T.markets.forEach((m) => { if (catSet.indexOf(m.cat) < 0) catSet.push(m.cat); });
  const cats = s.live === 'live' ? ['All'].concat(catSet.sort()) : ['All', 'Macro', 'Politics', 'Crypto', 'Sports', 'Science'];

  const mx = (m) => T.marketExtraOf(m);
  let mRows = T.markets.slice();
  const mActive = [];
  const addChip = (label, reset) => mActive.push({ label, reset });
  if (s.marketQuery.trim()) {
    const q = s.marketQuery.trim().toLowerCase();
    mRows = mRows.filter((m) => m.title.toLowerCase().indexOf(q) >= 0 || m.cat.toLowerCase().indexOf(q) >= 0);
    addChip('search: ' + s.marketQuery.trim(), { marketQuery: '' });
  }
  if (s.marketCat !== 'All') { mRows = mRows.filter((m) => m.cat === s.marketCat); addChip(s.marketCat, { marketCat: 'All' }); }
  if (s.mExclude.length) { mRows = mRows.filter((m) => s.mExclude.indexOf(m.cat) < 0); addChip('excluding ' + s.mExclude.join(', '), { mExclude: [] }); }
  if (s.mPlatform !== 'all') { mRows = mRows.filter((m) => m.venue === s.mPlatform); addChip(s.mPlatform, { mPlatform: 'all' }); }
  if (s.mStatus === 'closed') { mRows = []; addChip('closed only', { mStatus: 'active' }); }
  else if (s.mStatus === 'all') addChip('active + closed', { mStatus: 'active' });
  if (s.mProb !== 'all') {
    const p = { '5-95': [5, 95], '20-80': [20, 80], '80': [80, 100], '95': [95, 100], '99': [99, 100] }[s.mProb];
    mRows = mRows.filter((m) => m.yes >= p[0] && m.yes <= p[1]);
    addChip('probability ' + s.mProb, { mProb: 'all' });
  }
  if (s.mSpread !== 'all') { mRows = mRows.filter((m) => mx(m).spread < Number(s.mSpread)); addChip('spread < ' + s.mSpread + '¢', { mSpread: 'all' }); }
  if (s.mLiq !== 'all') {
    const v = { '1k': 1000, '10k': 10000, '100k': 100000 }[s.mLiq];
    mRows = mRows.filter((m) => m.liq >= v); addChip('liquidity > $' + s.mLiq, { mLiq: 'all' });
  }
  if (s.mVol !== 'all') {
    const v = { '10k': 10000, '100k': 100000, '1m': 1000000 }[s.mVol];
    mRows = mRows.filter((m) => m.vol >= v); addChip('volume > $' + s.mVol, { mVol: 'all' });
  }
  if (s.mEnds !== 'all') {
    const d = { '1d': 1, '7d': 7, '30d': 30 }[s.mEnds];
    mRows = s.mEnds === 'open' ? mRows.filter((m) => mx(m).endsDays > 180) : mRows.filter((m) => mx(m).endsDays <= d);
    addChip('resolves ' + (s.mEnds === 'open' ? 'far out' : 'in < ' + s.mEnds), { mEnds: 'all' });
  }
  if (s.mAge !== 'all') {
    mRows = s.mAge === '30d' ? mRows.filter((m) => mx(m).age > 30) : mRows.filter((m) => mx(m).age <= ({ '1d': 1, '7d': 7 })[s.mAge]);
    addChip('age ' + s.mAge, { mAge: 'all' });
  }
  if (s.mQuick === 'saved') { mRows = mRows.filter((m) => mx(m).saved); addChip('saved only', { mQuick: 'trending' }); }
  if (s.mQuick === 'positions') { mRows = mRows.filter((m) => mx(m).pos); addChip('my positions', { mQuick: 'trending' }); }
  if (s.mQuick === 'ending') { mRows = mRows.filter((m) => mx(m).endsDays <= 14); addChip('ending soon', { mQuick: 'trending' }); }
  if (s.mQuick === 'new') { mRows = mRows.filter((m) => mx(m).age <= 90); addChip('new markets', { mQuick: 'trending' }); }
  mRows = mRows.sort((a, b) => {
    if (s.marketSort === 'change') return Math.abs(b.chg) - Math.abs(a.chg);
    if (s.marketSort === 'liquidity') return b.liq - a.liq;
    if (s.marketSort === 'ending') return mx(a).endsDays - mx(b).endsDays;
    if (s.marketSort === 'newest') return mx(a).age - mx(b).age;
    return b.vol - a.vol;
  });

  const badge = mActive.length ? M + '; font-size:10px; color:#0A0D0F; background:#C8F542; border-radius:4px; padding:1px 7px' : 'display:none';
  const chevron = M + '; font-size:16px; color:rgba(255,255,255,.5); transition:transform .18s ease; transform:rotate(' + (s.marketFiltersOpen ? '90deg' : '0deg') + ')';

  return '<div>'
    + '<div style="padding:20px 24px 14px; border-bottom:1px solid rgba(255,255,255,.09)">'
    + '<div style="display:flex; align-items:flex-end; justify-content:space-between; gap:20px">'
    + '<div><div style="' + M + '; font-size:10px; letter-spacing:.18em; color:#C8F542">MARKETS</div>'
    + '<div style="font-family:\'Instrument Serif\',serif; font-size:30px; line-height:1.1; margin-top:5px">Every market, one table</div></div>'
    + '<div style="display:flex; align-items:center; gap:10px">'
    + '<input value="' + esc(s.marketQuery) + '" ' + T.inp((e) => T.setState({ marketQuery: e.target.value }), 'marketQuery') + ' placeholder="Search markets…" style="background:#10151A; border:1px solid rgba(255,255,255,.16); border-radius:8px; padding:9px 12px; ' + M + '; font-size:12.5px; color:#fff; width:230px; outline:none" />'
    + '<div ' + T.act(() => T.setState({ mPlatform: 'all', mStatus: 'active', mProb: 'all', mSpread: 'all', mLiq: 'all', mVol: 'all', mEnds: 'all', mAge: 'all', mExclude: [], marketCat: 'All', marketQuery: '', mQuick: 'trending', marketSort: 'volume' })) + ' class="hv-bd32" style="font-size:12.5px; color:rgba(255,255,255,.6); border:1px solid rgba(255,255,255,.16); border-radius:8px; padding:9px 13px; cursor:pointer">Reset filters</div>'
    + '<div class="hv-bd32" style="font-size:12.5px; color:rgba(255,255,255,.6); border:1px solid rgba(255,255,255,.16); border-radius:8px; padding:9px 13px; cursor:pointer">Save this view</div>'
    + '</div></div>'

    + '<div style="display:flex; align-items:center; gap:22px; margin-top:16px; flex-wrap:wrap">'
    + '<div style="display:flex; align-items:center; gap:8px"><span style="' + LBL9.replace('; margin-bottom:6px', '') + '">VIEW</span>'
    + [['table','Table'],['card','Cards'],['calendar','Calendar']].map((o) => T.opt(o[1], s.mView === o[0], { mView: o[0] })).join('') + '</div>'
    + '<div style="display:flex; align-items:center; gap:8px"><span style="' + LBL9.replace('; margin-bottom:6px', '') + '">QUICK</span>'
    + [['trending','Trending'],['saved','Saved'],['positions','My positions'],['ending','Ending soon'],['new','New']].map((o) => T.opt(o[1], s.mQuick === o[0], { mQuick: o[0] })).join('') + '</div>'
    + '</div>'

    + '<div style="display:flex; gap:7px; margin-top:14px; flex-wrap:wrap">'
    + cats.map((c) => T.chip(c.toUpperCase(), s.marketCat === c, { marketCat: c })).join('')
    + '</div>'

    + '<div style="border:1px solid rgba(255,255,255,.09); border-radius:10px; margin-top:14px; overflow:hidden">'
    + '<div ' + T.act(() => T.setState({ marketFiltersOpen: !s.marketFiltersOpen })) + ' class="hv-el" style="display:flex; align-items:center; justify-content:space-between; padding:11px 15px; background:#10151A; cursor:pointer">'
    + '<div style="display:flex; align-items:center; gap:10px"><div style="font-size:13px">All filters</div><div style="' + badge + '">' + mActive.length + '</div></div>'
    + '<div style="' + chevron + '">›</div></div>'
    + (s.marketFiltersOpen ?
      '<div style="padding:16px; display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:16px 20px">'
      + filterGroup('PLATFORM', [['all','All'],['Polymarket','Polymarket'],['Kalshi','Kalshi']].map((o) => T.opt(o[1], s.mPlatform === o[0], { mPlatform: o[0] })).join(''))
      + filterGroup('STATUS', [['active','Active'],['all','All'],['closed','Closed']].map((o) => T.opt(o[1], s.mStatus === o[0], { mStatus: o[0] })).join(''))
      + filterGroup('PROBABILITY', [['all','All'],['5-95','5–95%'],['20-80','20–80%'],['80','>80%'],['95','>95%'],['99','>99%']].map((o) => T.opt(o[1], s.mProb === o[0], { mProb: o[0] })).join(''))
      + filterGroup('SPREAD', [['all','All'],['3','<3¢'],['7','<7¢'],['10','<10¢']].map((o) => T.opt(o[1], s.mSpread === o[0], { mSpread: o[0] })).join(''))
      + filterGroup('LIQUIDITY', [['all','All'],['1k','>$1k'],['10k','>$10k'],['100k','>$100k']].map((o) => T.opt(o[1], s.mLiq === o[0], { mLiq: o[0] })).join(''))
      + filterGroup('VOLUME 24H', [['all','All'],['10k','>$10k'],['100k','>$100k'],['1m','>$1m']].map((o) => T.opt(o[1], s.mVol === o[0], { mVol: o[0] })).join(''))
      + filterGroup('RESOLVES IN', [['all','All'],['1d','<1 day'],['7d','<7 days'],['30d','<30 days'],['open','Open ended']].map((o) => T.opt(o[1], s.mEnds === o[0], { mEnds: o[0] })).join(''))
      + filterGroup('MARKET AGE', [['all','All'],['1d','<1 day'],['7d','<7 days'],['30d','>30 days']].map((o) => T.opt(o[1], s.mAge === o[0], { mAge: o[0] })).join(''))
      + '<div style="grid-column:span 2"><div style="' + LBL9 + '">EXCLUDE CATEGORIES</div><div style="display:flex; gap:6px; flex-wrap:wrap">'
      + cats.slice(1).map((c) => T.opt(c, s.mExclude.indexOf(c) >= 0, () => T.setState({ mExclude: s.mExclude.indexOf(c) >= 0 ? s.mExclude.filter((x) => x !== c) : s.mExclude.concat([c]) }))).join('')
      + '</div></div>'
      + '<div style="grid-column:span 2"><div style="' + LBL9 + '">SORT BY</div><div style="display:flex; gap:6px; flex-wrap:wrap">'
      + [['volume','Volume 24h'],['change','Biggest move'],['liquidity','Liquidity'],['ending','Ending soonest'],['newest','Newest']].map((o) => T.opt(o[1], s.marketSort === o[0], { marketSort: o[0] })).join('')
      + '</div></div>'
      + '</div>' : '')
    + '</div>'

    + '<div style="display:flex; align-items:center; gap:8px; margin-top:12px; flex-wrap:wrap">'
    + '<div style="' + M + '; font-size:11px; color:rgba(255,255,255,.45)">' + mRows.length + ' of ' + T.markets.length + ' markets</div>'
    + mActive.map((c) =>
      '<div ' + T.act(() => T.setState(c.reset)) + ' class="hv-bd30" style="' + M + '; font-size:11px; color:rgba(255,255,255,.7); border:1px solid rgba(255,255,255,.14); background:#161C22; border-radius:6px; padding:3px 9px; cursor:pointer">' + esc(c.label) + ' ✕</div>'
    ).join('')
    + '</div></div>'

    + '<div style="display:grid; grid-template-columns:1fr 96px 88px 96px 108px 108px; padding:10px 24px; border-bottom:1px solid rgba(255,255,255,.09); background:#10151A; ' + HEAD_CELL + '">'
    + '<div>MARKET</div>'
    + '<div style="text-align:right">TREND 24H</div>'
    + '<div style="text-align:right">YES</div>'
    + '<div ' + T.act(() => T.setState({ marketSort: 'change' })) + ' style="text-align:right; cursor:pointer; color:' + (s.marketSort === 'change' ? '#C8F542' : 'rgba(255,255,255,.45)') + '">CHANGE 1D</div>'
    + '<div ' + T.act(() => T.setState({ marketSort: 'volume' })) + ' style="text-align:right; cursor:pointer; color:' + (s.marketSort === 'volume' ? '#C8F542' : 'rgba(255,255,255,.45)') + '">VOLUME 24H</div>'
    + '<div style="text-align:right">RESOLVES</div></div>'
    + mRows.map((m) => marketRowHtml(T.marketView(m))).join('')
    + (mRows.length === 0 ? '<div style="padding:60px; text-align:center; ' + M + '; font-size:12px; color:rgba(255,255,255,.35)">No market matches that filter.</div>' : '')
    + '</div>';
}

// ---------------------------------------------------------------- flow (live tape)
export function renderFlow(T) {
  const s = T.state;
  const tapeFiltered = T.tapeFiltered();
  const tapeNotional = tapeFiltered.reduce((a, t) => a + t.size, 0);
  const tapeWallets = tapeFiltered.filter((t) => t.wallet !== '—').map((t) => t.wallet).filter((v, i, arr) => arr.indexOf(v) === i).length;
  const tapeBiggest = tapeFiltered.reduce((a, t) => Math.max(a, t.size), 0);
  const kpis = [
    { label: 'PRINTS SHOWN', value: String(tapeFiltered.length) },
    { label: 'TOTAL MOVED', value: money(tapeNotional) },
    { label: 'WALLETS INVOLVED', value: String(tapeWallets) },
    { label: 'BIGGEST PRINT', value: money(tapeBiggest) }
  ];

  return '<div>'
    + '<div style="padding:20px 24px 14px; border-bottom:1px solid rgba(255,255,255,.09)">'
    + '<div style="display:flex; align-items:flex-end; justify-content:space-between; gap:20px">'
    + '<div><div style="' + M + '; font-size:10px; letter-spacing:.18em; color:#C8F542">LIVE TAPE</div>'
    + '<div style="font-family:\'Instrument Serif\',serif; font-size:30px; line-height:1.1; margin-top:5px">Every large print as it lands</div></div>'
    + '<input value="' + esc(s.tapeQuery) + '" ' + T.inp((e) => T.setState({ tapeQuery: e.target.value }), 'tapeQuery') + ' placeholder="market, wallet, trader…" style="background:#10151A; border:1px solid rgba(255,255,255,.16); border-radius:8px; padding:9px 12px; ' + M + '; font-size:12.5px; color:#fff; width:250px; outline:none" />'
    + '</div>'
    + '<div style="display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:14px 18px; margin-top:14px">'
    + filterGroup('MINIMUM SIZE', [
      T.chip('≥ $2.5K', s.tapeMin === 2500 && !s.tapeTracked, { tapeMin: 2500, tapeTracked: false }),
      T.chip('≥ $10K', s.tapeMin === 10000 && !s.tapeTracked, { tapeMin: 10000, tapeTracked: false }),
      T.chip('TRACKED ONLY', s.tapeTracked, { tapeTracked: true, tapeMin: 2500 })
    ].join(''))
    + filterGroup('PLATFORM', [['all','All'],['Polymarket','Polymarket'],['Kalshi','Kalshi']].map((o) => T.opt(o[1], s.tapePlatform === o[0], { tapePlatform: o[0] })).join(''))
    + filterGroup('SIDE', [['all','All'],['BUY','Buys'],['SELL','Sells']].map((o) => T.opt(o[1], s.tapeSide === o[0], { tapeSide: o[0] })).join(''))
    + filterGroup('OUTCOME', [['all','All'],['Yes','Yes'],['No','No']].map((o) => T.opt(o[1], s.tapeOutcome === o[0], { tapeOutcome: o[0] })).join(''))
    + '</div></div>'

    + '<div style="display:grid; grid-template-columns:repeat(4,1fr); border-bottom:1px solid rgba(255,255,255,.09)">'
    + kpis.map((k, i) =>
      '<div style="padding:14px 24px' + (i < 3 ? '; border-right:1px solid rgba(255,255,255,.09)' : '') + '">'
      + '<div style="' + HEAD_CELL + '">' + k.label + '</div>'
      + '<div style="' + M + '; font-size:22px; margin-top:7px">' + k.value + '</div></div>'
    ).join('')
    + '</div>'

    + '<div style="display:grid; grid-template-columns:96px 160px 1fr 84px 90px 110px 96px; padding:10px 24px; border-bottom:1px solid rgba(255,255,255,.09); background:#10151A; ' + HEAD_CELL + '">'
    + '<div>TIME</div><div>WALLET</div><div>MARKET</div><div>SIDE</div><div style="text-align:right">PRICE</div><div style="text-align:right">SIZE</div><div style="text-align:right">VENUE</div></div>'
    + tapeFiltered.map((t0) => {
      const t = T.tapeRowView(t0);
      return '<div ' + t.act + ' class="hv-panel" style="display:grid; grid-template-columns:96px 160px 1fr 84px 90px 110px 96px; align-items:center; padding:12px 24px; border-bottom:1px solid rgba(255,255,255,.06); ' + M + '; font-size:12.5px; cursor:pointer; animation:rowIn .25s ease-out">'
        + '<div style="color:rgba(255,255,255,.55)">' + esc(t.ago) + '</div>'
        + '<div>' + esc(t.wallet) + '</div>'
        + '<div style="font-family:\'Inter\',sans-serif; font-size:13px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; padding-right:12px">' + esc(t.market) + '</div>'
        + '<div style="' + t.sideStyle + '">' + esc(t.side) + '</div>'
        + '<div style="text-align:right">' + esc(t.price) + '</div>'
        + '<div style="text-align:right">' + t.size + '</div>'
        + '<div style="text-align:right; color:rgba(255,255,255,.45); font-size:11px">' + esc(t.venue) + '</div></div>';
    }).join('')
    + '</div>';
}

// ---------------------------------------------------------------- cross-venue
export function renderCross(T) {
  const s = T.state;
  let cRows = T.crossPairs.filter((c) => Math.abs(c.pm - c.ks) >= s.crossMinGap && c.sim >= s.crossSim && c.pmVol >= s.crossPmVol && c.ksVol >= s.crossKsVol);
  cRows = cRows.filter((c) => c.pm >= s.crossMinPrice && c.pm <= s.crossMaxPrice && c.ks >= s.crossMinPrice && c.ks <= s.crossMaxPrice);
  if (s.crossQuery.trim()) {
    const cq = s.crossQuery.trim().toLowerCase();
    cRows = cRows.filter((c) => c.event.toLowerCase().indexOf(cq) >= 0 || c.cat.toLowerCase().indexOf(cq) >= 0);
  }
  if (s.crossLower !== 'any') cRows = cRows.filter((c) => (c.pm < c.ks ? 'Polymarket' : 'Kalshi') === s.crossLower);
  cRows = cRows.sort((a, b) => Math.abs(b.pm - b.ks) - Math.abs(a.pm - a.ks)).slice(0, s.crossMaxPairs);
  const gaps = cRows.map((c) => Math.abs(c.pm - c.ks)).sort((a, b) => a - b);
  const medianGap = gaps.length ? gaps[Math.floor(gaps.length / 2)] : 0;
  const sims = cRows.map((c) => c.sim).sort((a, b) => a - b);
  const medianSim = sims.length ? sims[Math.floor(sims.length / 2)] : 0;

  const activeChips = [].concat(
    s.crossQuery.trim() ? ['search: ' + s.crossQuery.trim()] : [],
    s.crossSim !== 0.30 ? ['similarity ≥ ' + s.crossSim.toFixed(2)] : [],
    s.crossMinGap > 0 ? ['gap ≥ ' + s.crossMinGap.toFixed(1) + '¢'] : [],
    s.crossPmVol > 0 ? ['Polymarket volume > $' + num(s.crossPmVol)] : [],
    s.crossKsVol > 0 ? ['Kalshi volume > $' + num(s.crossKsVol)] : [],
    s.crossLower !== 'any' ? ['cheaper on ' + s.crossLower] : [],
    (s.crossMinPrice !== 0 || s.crossMaxPrice !== 100) ? ['yes price ' + s.crossMinPrice + '–' + s.crossMaxPrice + '¢'] : []
  );

  const stepGroup = (label, valueLabel, onDown, onUp) =>
    '<div><div style="' + LBL9 + '">' + label + '</div>'
    + '<div style="display:flex; align-items:center; gap:6px">'
    + '<div ' + T.act(onDown) + ' class="hv-bd35w" style="width:26px; height:30px; flex:none; border:1px solid rgba(255,255,255,.16); border-radius:7px; display:flex; align-items:center; justify-content:center; ' + M + '; font-size:13px; color:rgba(255,255,255,.7); cursor:pointer">−</div>'
    + '<div style="flex:1; background:#10151A; border:1px solid rgba(255,255,255,.16); border-radius:7px; padding:6px 8px; ' + M + '; font-size:12px; text-align:center">' + esc(valueLabel) + '</div>'
    + '<div ' + T.act(onUp) + ' class="hv-bd35w" style="width:26px; height:30px; flex:none; border:1px solid rgba(255,255,255,.16); border-radius:7px; display:flex; align-items:center; justify-content:center; ' + M + '; font-size:13px; color:rgba(255,255,255,.7); cursor:pointer">+</div>'
    + '</div></div>';

  return '<div>'
    + '<div style="padding:20px 24px 14px; border-bottom:1px solid rgba(255,255,255,.09)">'
    + '<div style="display:flex; align-items:flex-end; justify-content:space-between; gap:20px">'
    + '<div><div style="' + M + '; font-size:10px; letter-spacing:.18em; color:#4F8EF7">CROSS-VENUE</div>'
    + '<div style="font-family:\'Instrument Serif\',serif; font-size:30px; line-height:1.1; margin-top:5px">The same question, two prices</div></div>'
    + '<div style="display:flex; align-items:center; gap:10px">'
    + '<input value="' + esc(s.crossQuery) + '" ' + T.inp((e) => T.setState({ crossQuery: e.target.value }), 'crossQuery') + ' placeholder="bitcoin, fed, election…" style="background:#10151A; border:1px solid rgba(255,255,255,.16); border-radius:8px; padding:9px 12px; ' + M + '; font-size:12.5px; color:#fff; width:230px; outline:none" />'
    + '<div ' + T.act(() => T.setState({ crossQuery: '', crossSim: 0.30, crossMaxPairs: 50, crossMinGap: 0, crossLower: 'any', crossPmVol: 0, crossKsVol: 0, crossMinPrice: 0, crossMaxPrice: 100 })) + ' class="hv-bd32" style="font-size:12.5px; color:rgba(255,255,255,.6); border:1px solid rgba(255,255,255,.16); border-radius:8px; padding:9px 13px; cursor:pointer">Reset filters</div>'
    + '</div></div>'
    + '<div style="font-size:13px; color:rgba(255,255,255,.55); margin-top:10px; max-width:760px">Matched by event, not by ticker, so wording differences do not hide a gap. A gap is not free money — fees, settlement rules and resolution sources differ between the two venues.</div>'

    + '<div style="border:1px solid rgba(255,255,255,.09); border-radius:10px; margin-top:14px; padding:16px; display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:16px 18px">'
    + stepGroup('MIN SIMILARITY', s.crossSim.toFixed(2), () => T.setState({ crossSim: Math.max(0.1, s.crossSim - 0.02) }), () => T.setState({ crossSim: Math.min(0.7, s.crossSim + 0.02) }))
    + stepGroup('MAX PAIRS', String(s.crossMaxPairs), () => T.setState({ crossMaxPairs: Math.max(10, s.crossMaxPairs - 10) }), () => T.setState({ crossMaxPairs: Math.min(150, s.crossMaxPairs + 10) }))
    + stepGroup('MIN GAP (¢)', s.crossMinGap.toFixed(1) + '¢', () => T.setState({ crossMinGap: Math.max(0, s.crossMinGap - 0.5) }), () => T.setState({ crossMinGap: s.crossMinGap + 0.5 }))
    + '<div><div style="' + LBL9 + '">LOWER YES ON</div><div style="display:flex; gap:6px">'
    + [['any','Any'],['Polymarket','Polymarket'],['Kalshi','Kalshi']].map((o) => T.opt(o[1], s.crossLower === o[0], { crossLower: o[0] })).join('')
    + '</div></div>'
    + stepGroup('MIN POLYMARKET VOLUME', s.crossPmVol ? '$' + num(s.crossPmVol) : 'any', () => T.setState({ crossPmVol: Math.max(0, s.crossPmVol - 250000) }), () => T.setState({ crossPmVol: s.crossPmVol + 250000 }))
    + stepGroup('MIN KALSHI VOLUME', s.crossKsVol ? '$' + num(s.crossKsVol) : 'any', () => T.setState({ crossKsVol: Math.max(0, s.crossKsVol - 100000) }), () => T.setState({ crossKsVol: s.crossKsVol + 100000 }))
    + stepGroup('MIN YES PRICE', s.crossMinPrice + '¢', () => T.setState({ crossMinPrice: Math.max(0, s.crossMinPrice - 5) }), () => T.setState({ crossMinPrice: Math.min(s.crossMaxPrice, s.crossMinPrice + 5) }))
    + stepGroup('MAX YES PRICE', s.crossMaxPrice + '¢', () => T.setState({ crossMaxPrice: Math.max(s.crossMinPrice, s.crossMaxPrice - 5) }), () => T.setState({ crossMaxPrice: Math.min(100, s.crossMaxPrice + 5) }))
    + '</div>'

    + '<div style="display:flex; align-items:center; gap:8px; margin-top:12px; flex-wrap:wrap">'
    + activeChips.map((c) => '<div style="' + M + '; font-size:11px; color:rgba(255,255,255,.7); border:1px solid rgba(255,255,255,.14); background:#161C22; border-radius:6px; padding:3px 9px">' + esc(c) + '</div>').join('')
    + '</div></div>'

    + '<div style="display:grid; grid-template-columns:repeat(4,1fr); border-bottom:1px solid rgba(255,255,255,.09)">'
    + '<div style="padding:14px 24px; border-right:1px solid rgba(255,255,255,.09)"><div style="' + HEAD_CELL + '">CANDIDATE PAIRS</div><div style="' + M + '; font-size:22px; margin-top:7px">' + cRows.length + '</div></div>'
    + '<div style="padding:14px 24px; border-right:1px solid rgba(255,255,255,.09)"><div style="' + HEAD_CELL + '">LARGEST GAP</div><div style="' + M + '; font-size:22px; margin-top:7px; color:#F5A623">' + (gaps.length ? gaps[gaps.length - 1] + '¢' : '—') + '</div></div>'
    + '<div style="padding:14px 24px; border-right:1px solid rgba(255,255,255,.09)"><div style="' + HEAD_CELL + '">MEDIAN SIMILARITY</div><div style="' + M + '; font-size:22px; margin-top:7px">' + (medianSim ? medianSim.toFixed(2) : '—') + '</div></div>'
    + '<div style="padding:14px 24px"><div style="' + HEAD_CELL + '">MEDIAN GAP</div><div style="' + M + '; font-size:22px; margin-top:7px">' + (medianGap ? medianGap + '¢' : '—') + '</div></div>'
    + '</div>'

    + '<div style="display:grid; grid-template-columns:1fr 118px 118px 96px 110px 118px; padding:10px 24px; border-bottom:1px solid rgba(255,255,255,.09); background:#10151A; ' + HEAD_CELL + '">'
    + '<div>EVENT</div><div style="text-align:right">POLYMARKET</div><div style="text-align:right">KALSHI</div><div style="text-align:right">GAP</div><div style="text-align:right">VOLUME 24H</div><div style="text-align:right">HELD FOR</div></div>'
    + cRows.map((c) => {
      const g = Math.abs(c.pm - c.ks);
      const gapStyle = M + '; font-size:14px; text-align:right; color:' + (g >= 5 ? '#F5A623' : g >= 3 ? '#ffffff' : 'rgba(255,255,255,.5)');
      return '<div style="display:grid; grid-template-columns:1fr 118px 118px 96px 110px 118px; align-items:center; padding:13px 24px; border-bottom:1px solid rgba(255,255,255,.06); animation:rowIn .25s ease-out">'
        + '<div style="padding-right:20px"><div style="font-size:13.5px; line-height:1.35">' + esc(c.event) + '</div>'
        + '<div style="' + M + '; font-size:10.5px; color:rgba(255,255,255,.45); margin-top:3px">' + esc(c.cat) + ' · similarity ' + c.sim.toFixed(2) + '</div></div>'
        + '<div style="' + M + '; font-size:14px; text-align:right; color:#C8F542">' + c.pm + '¢</div>'
        + '<div style="' + M + '; font-size:14px; text-align:right; color:#4F8EF7">' + c.ks + '¢</div>'
        + '<div style="' + gapStyle + '">' + g + '¢</div>'
        + '<div style="' + M + '; font-size:12.5px; text-align:right; color:rgba(255,255,255,.6)">$' + ((c.pmVol + c.ksVol) / 1000000).toFixed(1) + 'm</div>'
        + '<div style="' + M + '; font-size:12px; text-align:right; color:rgba(255,255,255,.45)">' + esc(c.held) + '</div></div>';
    }).join('')
    + (cRows.length === 0 ? '<div style="padding:60px; text-align:center; ' + M + '; font-size:12px; color:rgba(255,255,255,.35)">No pair is that far apart right now.</div>' : '')
    + '</div>';
}

// ---------------------------------------------------------------- resolved
export function renderResolved(T) {
  const s = T.state;
  const resAll = DEMO_RESOLVED.map((r) => Object.assign({}, r, { err: r.yes ? 100 - r.last : r.last }));
  let resRows = resAll.filter((r) => {
    if (s.resAnswer !== 'all' && (s.resAnswer === 'yes') !== r.yes) return false;
    if (s.resWindow !== 'all' && r.hours > Number(s.resWindow)) return false;
    if (s.resError !== 'all' && r.err < Number(s.resError)) return false;
    if (s.resQuery.trim() && r.title.toLowerCase().indexOf(s.resQuery.trim().toLowerCase()) < 0) return false;
    return true;
  });
  resRows = resRows.sort((a, b) => (s.resSort === 'error' ? b.err - a.err : s.resSort === 'volume' ? parseFloat(b.vol.replace(/[$m]/g, '')) - parseFloat(a.vol.replace(/[$m]/g, '')) : a.hours - b.hours));
  const avgErr = resRows.length ? Math.round(resRows.reduce((a, r) => a + r.err, 0) / resRows.length) : 0;
  const worst = resRows.reduce((a, r) => (r.err > (a ? a.err : -1) ? r : a), null);
  const kpis = [
    { label: 'MARKETS SHOWN', value: String(resRows.length) },
    { label: 'CROWD OFF BY, ON AVERAGE', value: avgErr + '¢' },
    { label: 'BIGGEST SURPRISE', value: worst ? worst.err + '¢' : '—', amber: true },
    { label: 'ENDED YES', value: resRows.filter((r) => r.yes).length + ' of ' + resRows.length }
  ];

  return '<div>'
    + '<div style="padding:20px 24px 14px; border-bottom:1px solid rgba(255,255,255,.09)">'
    + '<div style="display:flex; align-items:flex-end; justify-content:space-between; gap:20px">'
    + '<div><div style="' + M + '; font-size:10px; letter-spacing:.18em; color:#C8F542">RESOLVED</div>'
    + '<div style="font-family:\'Instrument Serif\',serif; font-size:30px; line-height:1.1; margin-top:5px">How the last questions ended</div></div>'
    + '<input value="' + esc(s.resQuery) + '" ' + T.inp((e) => T.setState({ resQuery: e.target.value }), 'resQuery') + ' placeholder="Search resolved markets…" style="background:#10151A; border:1px solid rgba(255,255,255,.16); border-radius:8px; padding:9px 12px; ' + M + '; font-size:12.5px; color:#fff; width:250px; outline:none" />'
    + '</div>'
    + '<div style="font-size:13px; color:rgba(255,255,255,.55); margin-top:10px; max-width:700px">The last price before settlement next to the answer. The gap between the two is what the crowd got wrong.</div>'
    + '<div style="display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:14px 18px; margin-top:14px">'
    + filterGroup('ANSWER', [['all','All'],['yes','Ended Yes'],['no','Ended No']].map((o) => T.opt(o[1], s.resAnswer === o[0], { resAnswer: o[0] })).join(''))
    + filterGroup('SETTLED WITHIN', [['all','All'],['24','24 hours'],['168','7 days']].map((o) => T.opt(o[1], s.resWindow === o[0], { resWindow: o[0] })).join(''))
    + filterGroup('CROWD WAS OFF BY', [['all','Any'],['25','25¢ or more'],['50','50¢ or more']].map((o) => T.opt(o[1], s.resError === o[0], { resError: o[0] })).join(''))
    + filterGroup('SORT BY', [['recent','Most recent'],['error','Biggest surprise'],['volume','Volume']].map((o) => T.opt(o[1], s.resSort === o[0], { resSort: o[0] })).join(''))
    + '</div></div>'

    + '<div style="display:grid; grid-template-columns:repeat(4,1fr); border-bottom:1px solid rgba(255,255,255,.09)">'
    + kpis.map((k, i) =>
      '<div style="padding:14px 24px' + (i < 3 ? '; border-right:1px solid rgba(255,255,255,.09)' : '') + '">'
      + '<div style="' + HEAD_CELL + '">' + k.label + '</div>'
      + '<div style="' + M + '; font-size:22px; margin-top:7px; color:' + (k.amber ? '#F5A623' : '#ffffff') + '">' + k.value + '</div></div>'
    ).join('')
    + '</div>'

    + '<div style="display:grid; grid-template-columns:1fr 110px 118px 128px 110px 120px; padding:10px 24px; border-bottom:1px solid rgba(255,255,255,.09); background:#10151A; ' + HEAD_CELL + '">'
    + '<div>MARKET</div><div style="text-align:right">ANSWER</div><div style="text-align:right">LAST PRICE</div><div style="text-align:right">CROWD OFF BY</div><div style="text-align:right">VOLUME</div><div style="text-align:right">SETTLED</div></div>'
    + resRows.map((r) => {
      const answerStyle = M + '; font-size:11px; letter-spacing:.1em; border-radius:5px; padding:3px 10px; ' + (r.yes ? 'color:#0A0D0F; background:#C8F542' : 'color:#FF7A7A; border:1px solid rgba(255,69,69,.35)');
      const errStyle = M + '; font-size:14px; text-align:right; color:' + (r.err >= 50 ? '#FF4545' : r.err >= 25 ? '#F5A623' : 'rgba(255,255,255,.6)');
      return '<div style="display:grid; grid-template-columns:1fr 110px 118px 128px 110px 120px; align-items:center; padding:13px 24px; border-bottom:1px solid rgba(255,255,255,.06); animation:rowIn .25s ease-out">'
        + '<div style="padding-right:20px"><div style="font-size:13.5px; line-height:1.35">' + esc(r.title) + '</div>'
        + '<div style="' + M + '; font-size:10.5px; color:rgba(255,255,255,.45); margin-top:3px">' + esc(r.meta) + '</div></div>'
        + '<div style="display:flex; justify-content:flex-end"><div style="' + answerStyle + '">' + (r.yes ? 'YES' : 'NO') + '</div></div>'
        + '<div style="' + M + '; font-size:14px; text-align:right">' + r.last + '¢</div>'
        + '<div style="' + errStyle + '">' + r.err + '¢</div>'
        + '<div style="' + M + '; font-size:12.5px; text-align:right; color:rgba(255,255,255,.6)">' + esc(r.vol) + '</div>'
        + '<div style="' + M + '; font-size:12px; text-align:right; color:rgba(255,255,255,.45)">' + esc(r.when) + '</div></div>';
    }).join('')
    + '</div>';
}
