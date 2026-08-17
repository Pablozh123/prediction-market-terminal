// Leaderboard, Whale flow, Risk screen, Tracked — ported from the design reference.

import { esc, money, num, herkunftSatz, leerBlock, leerZeile, seitenKopf, catChipsPresent } from '../util.js';
import { renderClusterGraphics } from './cluster_graphics.js';

const M = "font-family:'JetBrains Mono',monospace";
const LBL9 = M + '; font-size:9px; letter-spacing:.14em; color:rgba(255,255,255,.42); margin-bottom:6px';
const HEAD_CELL = M + '; font-size:9.5px; letter-spacing:.14em; color:rgba(255,255,255,.45)';

function filterGroup(label, chipsHtml) {
  return '<div><div style="' + LBL9 + '">' + label + '</div><div style="display:flex; gap:6px; flex-wrap:wrap">' + chipsHtml + '</div></div>';
}

// Score components as a compact labelled list. Prefers the structured
// score_parts from /api/leaderboard; falls back to parsing the older
// "return 90, sharpe-proxy 60, …" string so no raw string reaches the page.
export function scorePartsOf(t) {
  if (t && Array.isArray(t.scoreParts) && t.scoreParts.length) {
    return t.scoreParts.map((p) => ({ label: String(p.label || ''), value: p.value != null ? String(p.value) : '—' }));
  }
  const raw = t && t.tags ? String(t.tags) : '';
  if (!raw) return [];
  return raw.split(',').map((teil) => {
    const m = teil.trim().match(/^([a-z][a-z -]*?)\s+(-?\d+(?:\.\d+)?)$/i);
    return m ? { label: m[1].replace(/-/g, ' '), value: m[2] } : null;
  }).filter(Boolean);
}

function scorePartsHtml(t) {
  const parts = scorePartsOf(t);
  if (!parts.length) return '';
  return '<div style="display:flex; gap:5px; flex-wrap:wrap; margin-top:4px">'
    + parts.map((p) => '<span style="' + M + '; font-size:9.5px; color:rgba(255,255,255,.5); border:1px solid rgba(255,255,255,.1); border-radius:4px; padding:1px 6px; white-space:nowrap">' + esc(p.label) + ' <span style="color:rgba(255,255,255,.8)">' + esc(p.value) + '</span></span>').join('')
    + '</div>';
}

// ---------------------------------------------------------------- traders (leaderboard)
export function renderTraders(T) {
  const s = T.state;
  if (!T.traders.length) {
    return '<div>' + seitenKopf('LEADERBOARD', 'Who is actually good at this', '#C8F542')
      + leerBlock('NO WALLETS RANKED', herkunftSatz(T.herkunft.traders, '/api/leaderboard')) + '</div>';
  }
  // Only filters that read a field the API delivers: profit, volume, name.
  // The traits / balance / age / assets / open-positions / bot-score groups
  // and the "fetch …" checkboxes filtered on constants and reached no fetch.
  let tRows = T.traders.slice();
  let tCount = 0;
  if (s.traderQuery.trim()) {
    const tq = s.traderQuery.trim().toLowerCase();
    tRows = tRows.filter((t) => t.name.toLowerCase().indexOf(tq) >= 0 || t.wallet.toLowerCase().indexOf(tq) >= 0);
    tCount++;
  }
  if (s.tPnl !== 'all') { const v = { '500k': 500000, '1m': 1000000, '2m': 2000000, '5m': 5000000 }[s.tPnl]; tRows = tRows.filter((t) => t.pnl >= v); tCount++; }
  if (s.tVol !== 'all') { const v = { '10k': 10000, '100k': 100000, '1m': 1000000, '50m': 50000000 }[s.tVol]; tRows = tRows.filter((t) => t.vol >= v); tCount++; }
  // Win rate / resolved bets come only from /api/wallet with n and CI. When
  // no row carries them the columns and the rank option are not offered.
  const hatWin = T.traders.some((t) => t.win != null);
  const hatResolved = T.traders.some((t) => t.resolved != null);
  const rank = (s.traderRank === 'win' && !hatWin) ? 'pnl' : s.traderRank;
  const traderSorted = tRows.sort((a, b) => {
    if (rank === 'win') return (b.win || 0) - (a.win || 0);
    if (rank === 'score') return (b.score == null ? -1 : b.score) - (a.score == null ? -1 : a.score);
    if (rank === 'vol') return b.vol - a.vol;
    if (rank === 'roi') return (b.pnl / (b.vol || 1)) - (a.pnl / (a.vol || 1));
    return b.pnl - a.pnl;
  });

  const badge = tCount ? M + '; font-size:10px; color:#0A0D0F; background:#C8F542; border-radius:4px; padding:1px 7px' : 'display:none';
  const chevron = M + '; font-size:16px; color:rgba(255,255,255,.5); transition:transform .18s ease; transform:rotate(' + (s.traderFiltersOpen ? '90deg' : '0deg') + ')';
  const asOf = T.liveData.leaderboard && T.liveData.leaderboard.as_of ? ' · snapshot ' + T.liveData.leaderboard.as_of : '';
  const grid = '44px 1fr 120px' + (hatWin ? ' 100px' : '') + (hatResolved ? ' 118px' : '') + ' 100px 92px';
  const rankTabs = [T.tab('Smart score', rank === 'score', { traderRank: 'score' }),
    T.tab('Profit', rank === 'pnl', { traderRank: 'pnl' }),
    T.tab('Volume', rank === 'vol', { traderRank: 'vol' }),
    T.tab('Profit / volume', rank === 'roi', { traderRank: 'roi' })]
    .concat(hatWin ? [T.tab('Win rate', rank === 'win', { traderRank: 'win' })] : []).join('');

  return '<div>'
    + '<div style="padding:20px 24px 14px; border-bottom:1px solid rgba(255,255,255,.09)">'
    + '<div style="display:flex; align-items:flex-end; justify-content:space-between; gap:20px">'
    + '<div><div style="' + M + '; font-size:10px; letter-spacing:.18em; color:#C8F542">LEADERBOARD</div>'
    + '<div style="font-family:\'Instrument Serif\',serif; font-size:30px; line-height:1.1; margin-top:5px">Who is actually good at this</div></div>'
    + '<div style="display:flex; align-items:center; gap:10px">'
    + '<input value="' + esc(s.traderQuery) + '" ' + T.inp((e) => T.setState({ traderQuery: e.target.value }), 'traderQuery') + ' placeholder="Search name or wallet…" style="background:#10151A; border:1px solid rgba(255,255,255,.16); border-radius:8px; padding:9px 12px; ' + M + '; font-size:12.5px; color:#fff; width:230px; outline:none" />'
    + '<div ' + T.act(() => T.setState({ traderQuery: '', tPnl: 'all', tVol: 'all', traderRank: 'pnl' })) + ' class="hv-bd32" style="font-size:12.5px; color:rgba(255,255,255,.6); border:1px solid rgba(255,255,255,.16); border-radius:8px; padding:9px 13px; cursor:pointer">Reset filters</div>'
    + '</div></div>'
    + '<div style="font-size:13px; color:rgba(255,255,255,.55); margin-top:10px; max-width:760px">Ranked from the public Polymarket all-time leaderboard. The smart score is a weighted composite of the components listed under each wallet; win rate and resolved-bet counts are computed per wallet with sample size and confidence interval — open a wallet to see them.</div>'

    + '<div style="display:flex; align-items:center; gap:20px; margin-top:14px; flex-wrap:wrap">'
    + '<div style="display:flex; align-items:center; gap:8px"><span style="' + LBL9.replace('; margin-bottom:6px', '') + '">RANK BY</span><div style="display:flex; gap:6px; flex-wrap:wrap">'
    + rankTabs + '</div></div>'
    + '</div>'

    + '<div style="border:1px solid rgba(255,255,255,.09); border-radius:10px; margin-top:14px; overflow:hidden">'
    + '<div ' + T.act(() => T.setState({ traderFiltersOpen: !s.traderFiltersOpen })) + ' class="hv-el" style="display:flex; align-items:center; justify-content:space-between; padding:11px 15px; background:#10151A; cursor:pointer">'
    + '<div style="display:flex; align-items:center; gap:10px"><div style="font-size:13px">Filters</div><div style="' + badge + '">' + tCount + '</div></div>'
    + '<div style="' + chevron + '">›</div></div>'
    + (s.traderFiltersOpen ?
      '<div style="padding:16px; display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:16px 20px">'
      + filterGroup('PROFIT', [['all','All'],['500k','>$500k'],['1m','>$1m'],['2m','>$2m'],['5m','>$5m']].map((o) => T.opt(o[1], s.tPnl === o[0], { tPnl: o[0] })).join(''))
      + filterGroup('VOLUME', [['all','All'],['10k','>$10k'],['100k','>$100k'],['1m','>$1m'],['50m','>$50m']].map((o) => T.opt(o[1], s.tVol === o[0], { tVol: o[0] })).join(''))
      + '</div>' : '')
    + '</div>'
    + '<div style="' + M + '; font-size:11px; color:rgba(255,255,255,.45); margin-top:12px">' + traderSorted.length + ' of ' + T.traders.length + ' wallets · all-time' + esc(asOf) + '</div>'
    + '</div>'

    + '<div style="display:grid; grid-template-columns:' + grid + '; padding:10px 24px; border-bottom:1px solid rgba(255,255,255,.09); background:#10151A; ' + HEAD_CELL + '">'
    + '<div>#</div><div>WALLET · SCORE COMPONENTS</div><div style="text-align:right">PROFIT</div>'
    + (hatWin ? '<div style="text-align:right">WIN RATE</div>' : '')
    + (hatResolved ? '<div style="text-align:right">RESOLVED BETS</div>' : '')
    + '<div style="text-align:right">VOLUME</div><div style="text-align:right">SCORE</div></div>'
    + traderSorted.map((t, i) => {
      const score = t.score;
      const avatarStyle = 'width:28px; height:28px; flex:none; border-radius:7px; background:#1C232B; border:1px solid rgba(255,255,255,.09); display:flex; align-items:center; justify-content:center; ' + M + '; font-size:12px; color:' + (score != null && score >= 80 ? '#C8F542' : 'rgba(255,255,255,.6)');
      const scoreStyle = M + '; font-size:12.5px; border-radius:5px; padding:3px 9px; ' + (score == null ? 'color:rgba(255,255,255,.4); border:1px solid rgba(255,255,255,.12)' : score >= 80 ? 'color:#0A0D0F; background:#C8F542' : score >= 60 ? 'color:rgba(255,255,255,.8); border:1px solid rgba(255,255,255,.2)' : 'color:#F5A623; border:1px solid rgba(245,166,35,.35)');
      return '<div ' + T.act(() => T.openWallet(t.name)) + ' class="hv-panel" style="display:grid; grid-template-columns:' + grid + '; align-items:center; padding:13px 24px; border-bottom:1px solid rgba(255,255,255,.06); cursor:pointer; animation:rowIn .25s ease-out">'
        + '<div style="' + M + '; font-size:13px; color:rgba(255,255,255,.45)">' + (i + 1) + '</div>'
        + '<div style="display:flex; align-items:center; gap:10px; min-width:0">'
        + '<div style="' + avatarStyle + '">' + esc(t.name.charAt(0).toUpperCase()) + '</div>'
        + '<div style="min-width:0"><div style="font-size:13.5px">' + esc(t.name) + '</div>'
        + '<div style="' + M + '; font-size:10.5px; color:rgba(255,255,255,.45); margin-top:2px">' + esc(t.wallet) + (t.grade ? ' · grade ' + esc(t.grade) : '') + '</div>'
        + scorePartsHtml(t) + '</div></div>'
        + '<div style="' + M + '; font-size:14px; text-align:right; color:' + (t.pnl >= 0 ? '#C8F542' : '#FF4545') + '">' + money(t.pnl) + '</div>'
        + (hatWin ? '<div style="' + M + '; font-size:13px; text-align:right">' + (t.win != null ? Math.round(t.win * 100) + '%' : '—') + '</div>' : '')
        + (hatResolved ? '<div style="' + M + '; font-size:12.5px; text-align:right; color:rgba(255,255,255,.55)">' + (t.resolved != null ? num(t.resolved) : '—') + '</div>' : '')
        + '<div style="' + M + '; font-size:13px; text-align:right">' + money(t.vol) + '</div>'
        + '<div style="display:flex; justify-content:flex-end"><div style="' + scoreStyle + '">' + (score != null ? score : 'n/a') + '</div></div>'
        + '</div>';
    }).join('')
    + '</div>';
}

// ---------------------------------------------------------------- whale flow
export function renderWhale(T) {
  const s = T.state;
  // Die Seite ist eine Gruppierung des Tapes, nichts weiter. Ohne Tape gibt
  // es nichts zu gruppieren — hier standen bisher acht erfundene Wallets und
  // die festen Kennzahlen 74 Wallets, 18,4 Mio bewegt, 214k groesster Print.
  if (!T.tape.length) {
    return '<div>' + seitenKopf('WHALE FLOW', 'Who is moving the big money', '#C8F542')
      + leerBlock('NO PRINTS TO GROUP', herkunftSatz(T.herkunft.tape, '/api/tape')) + '</div>';
  }
  // Kalshi publishes no wallet identities, so its prints cannot be grouped
  // and are counted here only to say how many were left out.
  const ohneWallet = T.tape.filter((t) => t.wallet === '—').length;
  const mitWallet = T.tape.length - ohneWallet;
  if (!mitWallet) {
    return '<div>' + seitenKopf('WHALE FLOW', 'Who is moving the big money', '#C8F542')
      + leerBlock('NO WALLET-LEVEL PRINTS', ohneWallet + ' print(s) in the tape carry no wallet identity (Kalshi publishes none), so there is nothing to group. Polymarket prints appear here as soon as the tape has some.') + '</div>';
  }

  // Alles hier ist eine Gruppierung von T.tape — kein weiterer Abruf, keine
  // Zahl, die nicht aus einem Print dieses Fensters stammt. The category chip
  // narrows the prints before grouping, so every figure below is a sum over
  // the prints of that category only.
  const whaleCat = s.whaleCat || 'All';
  const catChips = ['All'].concat(catChipsPresent(T.tape.filter((t) => t.wallet !== '—'), 'category'));
  const grouped = T.tape.filter((t) => t.wallet !== '—' && (whaleCat === 'All' || (t.category || 'Other') === whaleCat));
  if (!grouped.length) {
    return '<div>' + seitenKopf('WHALE FLOW', 'Who is moving the big money', '#C8F542')
      + '<div style="padding:14px 24px 0; display:flex; align-items:center; gap:8px; flex-wrap:wrap"><span style="' + LBL9.replace('; margin-bottom:6px', '') + '">CATEGORY</span>'
      + catChips.map((c) => T.chip(c.toUpperCase(), whaleCat === c, { whaleCat: c })).join('') + '</div>'
      + leerBlock('NO PRINTS IN THIS CATEGORY', 'No wallet-level print in the tape window carries the category ' + whaleCat + '. Pick another chip or All.') + '</div>';
  }
  const byWallet = {};
  const catDollar = {};
  grouped.forEach((t) => {
    const w = byWallet[t.wallet] || (byWallet[t.wallet] = {
      name: t.wallet, wallet: t.walletAddress || t.wallet, prints: 0, total: 0, biggest: 0,
      buys: 0, sells: 0, buyDollar: 0, sellDollar: 0, cats: {}, markets: {}, venues: {},
      lastMins: Infinity, lastAgo: '—'
    });
    const size = +t.size || 0;
    w.prints++; w.total += size; w.biggest = Math.max(w.biggest, size);
    if (String(t.side).indexOf('BUY') === 0) { w.buys++; w.buyDollar += size; } else { w.sells++; w.sellDollar += size; }
    // Kategorie kommt vom Server (util.mapTrade); ohne Feld steht "Other".
    const cat = t.category || 'Other';
    w.cats[cat] = (w.cats[cat] || 0) + 1;
    catDollar[cat] = (catDollar[cat] || 0) + size;
    const mk = t.marketKey || t.market;
    const m = w.markets[mk] || (w.markets[mk] = { title: t.market, dollar: 0, prints: 0 });
    m.dollar += size; m.prints++;
    w.venues[t.venue || 'Polymarket'] = true;
    const mins = typeof t.mins === 'number' ? t.mins : 999;
    if (mins < w.lastMins) { w.lastMins = mins; w.lastAgo = t.ago || '—'; }
  });
  const wallets = Object.values(byWallet).map((w) => {
    const topCat = Object.entries(w.cats).sort((a, b) => b[1] - a[1])[0];
    const marketList = Object.values(w.markets).sort((a, b) => b.dollar - a.dollar);
    return {
      name: w.name, wallet: w.wallet, prints: w.prints, total: w.total, biggest: w.biggest,
      buys: w.buys, sells: w.sells,
      lean: w.buys && w.sells ? (w.buyDollar >= w.sellDollar ? 'MOSTLY BUYING' : 'MOSTLY SELLING') : w.buys ? 'BUYING' : 'SELLING',
      cat: topCat[0], catShare: topCat[1] + '/' + w.prints,
      marketCount: marketList.length, topMarket: marketList[0],
      venues: Object.keys(w.venues).join(' · '),
      lastAgo: w.lastAgo
    };
  });
  const sortKey = ['total', 'biggest', 'prints'].indexOf(s.whaleSort) >= 0 ? s.whaleSort : 'total';
  wallets.sort((a, b) => (b[sortKey] - a[sortKey]) || (b.total - a.total));
  const SHOW = 25;
  const rows = wallets.slice(0, SHOW);
  const walletCount = wallets.length;
  const total = grouped.reduce((a, t) => a + (+t.size || 0), 0);
  const biggest = grouped.reduce((a, t) => Math.max(a, +t.size || 0), 0);
  const topCatDollar = Object.entries(catDollar).sort((a, b) => b[1] - a[1])[0];
  const topCatLabel = topCatDollar ? topCatDollar[0] : '—';
  const topCatShare = topCatDollar && total ? Math.round(topCatDollar[1] / total * 100) + '% of $' : '';
  // Konzentration: welchen Anteil der gruppierten Dollar die groessten drei
  // Wallets halten. Immer nach Gesamtsumme, unabhaengig von der Sortierung.
  const byTotal = wallets.slice().sort((a, b) => b.total - a.total);
  const topN = Math.min(3, byTotal.length);
  const topDollar = byTotal.slice(0, topN).reduce((a, w) => a + w.total, 0);
  const topShare = total ? Math.round(topDollar / total * 100) : 0;
  const konzentrationSatz = topN === walletCount
    ? (walletCount === 1 ? 'One wallet accounts for all ' + money(total) + ' grouped here.' : 'All ' + walletCount + ' wallets shown hold the full ' + money(total) + ' grouped here.')
    : 'The top ' + topN + ' wallets hold ' + money(topDollar) + ' of ' + money(total) + ' grouped here (' + topShare + '%), across ' + walletCount + ' wallets.';
  const ausschlussSatz = ohneWallet
    ? ' ' + ohneWallet + ' Kalshi print(s) are not shown here: Kalshi publishes no wallet identities, so they cannot be grouped.'
    : '';
  const kpi = (label, value, sub, last) =>
    '<div style="padding:14px 20px' + (last ? '' : '; border-right:1px solid rgba(255,255,255,.09)') + '">'
    + '<div style="' + M + '; font-size:10px; letter-spacing:.14em; color:rgba(255,255,255,.45)">' + label + '</div>'
    + '<div style="' + M + '; font-size:24px; margin-top:7px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis">' + value + '</div>'
    + (sub ? '<div style="' + M + '; font-size:10.5px; color:rgba(255,255,255,.4); margin-top:3px">' + sub + '</div>' : '')
    + '</div>';
  const GRID = 'minmax(170px,1.2fr) 58px 96px 96px 128px 66px minmax(150px,1fr) 118px 78px';

  return '<div>'
    + '<div style="padding:20px 24px 16px; border-bottom:1px solid rgba(255,255,255,.09)">'
    + '<div style="' + M + '; font-size:10px; letter-spacing:.18em; color:#C8F542">WHALE FLOW</div>'
    + '<div style="font-family:\'Instrument Serif\',serif; font-size:30px; line-height:1.1; margin-top:5px">Who is moving the big money</div>'
    + '<div style="font-size:13px; color:rgba(255,255,255,.55); margin-top:9px; max-width:760px">The same prints as the tape, grouped by wallet, so one wallet buying twenty times reads as one story instead of twenty rows. Every figure below is a sum over the prints in this tape window' + (whaleCat === 'All' ? '' : ' in the category ' + esc(whaleCat)) + '.' + esc(ausschlussSatz) + '</div>'
    + '<div style="display:flex; align-items:center; gap:8px; margin-top:12px; flex-wrap:wrap">'
    + '<span style="' + LBL9.replace('; margin-bottom:6px', '') + '">CATEGORY</span>'
    + catChips.map((c) => T.chip(c.toUpperCase(), whaleCat === c, { whaleCat: c })).join('')
    + '</div>'
    + '<div style="display:flex; align-items:center; gap:8px; margin-top:10px; flex-wrap:wrap">'
    + '<span style="' + LBL9.replace('; margin-bottom:6px', '') + '">SORT BY</span>'
    + T.chip('Total $', sortKey === 'total', { whaleSort: 'total' })
    + T.chip('Biggest print', sortKey === 'biggest', { whaleSort: 'biggest' })
    + T.chip('Prints', sortKey === 'prints', { whaleSort: 'prints' })
    + '<span style="' + M + '; font-size:11px; color:rgba(255,255,255,.45); margin-left:6px">' + (walletCount > SHOW ? 'top ' + SHOW + ' of ' + num(walletCount) + ' wallets' : num(walletCount) + ' wallet' + (walletCount === 1 ? '' : 's')) + ' · ' + num(grouped.length) + ' print' + (grouped.length === 1 ? '' : 's') + ' grouped</span>'
    + '</div></div>'
    + '<div style="display:grid; grid-template-columns:repeat(5,1fr); border-bottom:1px solid rgba(255,255,255,.09)">'
    + kpi('WALLETS PRINTING BIG', num(walletCount), '')
    + kpi('PRINTS GROUPED', num(grouped.length), ohneWallet ? num(ohneWallet) + ' without a wallet left out' : '')
    + kpi('$ GROUPED · THIS WINDOW', money(total), '')
    + kpi('BIGGEST SINGLE PRINT', money(biggest), '')
    + kpi('TOP CATEGORY BY $', esc(topCatLabel), esc(topCatShare), true)
    + '</div>'
    + '<div style="padding:10px 24px; border-bottom:1px solid rgba(255,255,255,.09); font-size:12px; color:rgba(255,255,255,.55)"><span style="' + M + '; font-size:9.5px; letter-spacing:.14em; color:rgba(255,255,255,.42); margin-right:8px">CONCENTRATION</span>' + esc(konzentrationSatz) + '</div>'
    + '<div style="display:grid; grid-template-columns:' + GRID + '; gap:0 10px; padding:10px 24px; border-bottom:1px solid rgba(255,255,255,.09); background:#10151A; ' + HEAD_CELL + '">'
    + '<div>WALLET · VENUE</div><div style="text-align:right">PRINTS</div><div style="text-align:right">TOTAL</div><div style="text-align:right">BIGGEST</div><div style="text-align:right">LEANING</div><div style="text-align:right">MARKETS</div><div>TOP MARKET</div><div style="text-align:right">MOSTLY IN</div><div style="text-align:right">LAST PRINT</div></div>'
    + (rows.length ? '' : leerZeile('Every print in this window is anonymous — Kalshi publishes no wallet identity, so there is nothing to group by.'))
    + rows.map((w) => {
      const leanColor = w.lean === 'BUYING' ? '#C8F542' : w.lean === 'SELLING' ? '#FF4545' : w.lean === 'MOSTLY BUYING' ? 'rgba(200,245,66,.75)' : 'rgba(255,69,69,.75)';
      const leanStyle = M + '; font-size:11px; letter-spacing:.08em; text-align:right; color:' + leanColor;
      const topMarketShare = w.total ? Math.round(w.topMarket.dollar / w.total * 100) : 0;
      return '<div ' + T.act(() => T.openWallet(w.name)) + ' class="hv-panel" style="display:grid; grid-template-columns:' + GRID + '; gap:0 10px; align-items:center; padding:12px 24px; border-bottom:1px solid rgba(255,255,255,.06); cursor:pointer; animation:rowIn .25s ease-out">'
        + '<div style="min-width:0"><div style="font-size:13.5px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis">' + esc(w.name) + '</div>'
        + '<div style="' + M + '; font-size:10.5px; color:rgba(255,255,255,.45); margin-top:3px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis">' + esc(w.wallet) + ' · ' + esc(w.venues) + '</div></div>'
        + '<div style="' + M + '; font-size:13px; text-align:right; color:rgba(255,255,255,.6)">' + w.prints + '</div>'
        + '<div style="' + M + '; font-size:14px; text-align:right">' + money(w.total) + '</div>'
        + '<div style="' + M + '; font-size:13px; text-align:right; color:rgba(255,255,255,.6)">' + money(w.biggest) + '</div>'
        + '<div><div style="' + leanStyle + '">' + esc(w.lean) + '</div>'
        + '<div style="' + M + '; font-size:10px; color:rgba(255,255,255,.4); text-align:right; margin-top:2px">' + w.buys + ' buy' + (w.buys === 1 ? '' : 's') + ' · ' + w.sells + ' sell' + (w.sells === 1 ? '' : 's') + '</div></div>'
        + '<div style="' + M + '; font-size:13px; text-align:right; color:rgba(255,255,255,.6)">' + w.marketCount + '</div>'
        + '<div style="min-width:0"><div style="font-size:12px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis">' + esc(w.topMarket.title) + '</div>'
        + '<div style="' + M + '; font-size:10px; color:rgba(255,255,255,.4); margin-top:2px">' + money(w.topMarket.dollar) + ' · ' + topMarketShare + '% of this wallet</div></div>'
        + '<div style="text-align:right"><div style="' + M + '; font-size:11.5px; color:rgba(255,255,255,.75)">' + esc(w.cat) + '</div>'
        + '<div style="' + M + '; font-size:10px; color:rgba(255,255,255,.4); margin-top:2px">' + esc(w.catShare) + ' prints</div></div>'
        + '<div style="' + M + '; font-size:11px; text-align:right; color:rgba(255,255,255,.5)">' + esc(w.lastAgo) + '</div></div>';
    }).join('')
    + '</div>';
}

// ---------------------------------------------------------------- risk screen
export function renderRisk(T) {
  const s = T.state;
  const riskFiltered = T.risks.filter((r) => s.riskFilter === 'all' || r.sev === s.riskFilter);
  const live = T.liveData.risk;
  // While the request is in flight (no answer recorded yet) the page says
  // what it is waiting for and how long that takes on a cold cache; the
  // fetch layer gives this route 150 s instead of the usual 45.
  const laedt = !live && !T.herkunft.risks;
  const risikoSatz = laedt
    ? 'building the day\'s tape, ~90 s on a cold cache — waiting for /api/risk (it pages a day of prints and looks up market categories before it can score anything)'
    : herkunftSatz(T.herkunft.risks, '/api/risk');
  // Ein Screen, der Verdacht behauptet, darf keine erfundene Zahl tragen.
  // Hier standen 412 geprueft, 2 auffaellige Ereignisse, 5 auffaellige
  // Wallets, 4 und 3 Cluster — fuenf Messwerte ohne Messung.
  const kpis = live && live.kpis ? [
    { label: 'EVENTS SCREENED', value: String(live.kpis.events_screened) },
    { label: 'HIGH-RISK EVENTS', value: String(live.kpis.high_risk_events), amber: true },
    { label: 'HIGH-RISK WALLETS', value: String(live.kpis.high_risk_wallets), amber: true },
    { label: 'FRESH-WALLET CLUSTERS', value: String(live.kpis.fresh_clusters) },
    { label: 'COORDINATED CLUSTERS', value: String(live.kpis.coordinated_clusters) }
  ] : [
    { label: 'EVENTS SCREENED', value: '—' },
    { label: 'HIGH-RISK EVENTS', value: '—' },
    { label: 'HIGH-RISK WALLETS', value: '—' },
    { label: 'FRESH-WALLET CLUSTERS', value: '—' },
    { label: 'COORDINATED CLUSTERS', value: '—' }
  ];
  const walletRows = live && live.wallets ? live.wallets : [];

  let body = '';
  if (s.riskView === 'events') {
    body = '<div>'
      + '<div style="display:flex; gap:6px; padding:14px 24px 0; flex-wrap:wrap">'
      + [T.tab('All', s.riskFilter === 'all', { riskFilter: 'all' }),
         T.tab('High', s.riskFilter === 'high', { riskFilter: 'high' }),
         T.tab('Watch', s.riskFilter === 'medium', { riskFilter: 'medium' })].join('')
      + '</div>'
      + (riskFiltered.length ? '' : leerZeile(T.risks.length ? 'No event at this severity.' : risikoSatz))
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
      + (walletRows.length ? '' : leerZeile(risikoSatz))
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
    const freshRows = live && live.fresh ? live.fresh : [];
    body = (freshRows.length ? '' : leerZeile(risikoSatz))
      + '<div style="padding:16px 24px; display:grid; grid-template-columns:repeat(2,1fr); gap:14px">'
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
    const timingRows = live && live.timing ? live.timing : [];
    body = '<div style="border:1px solid rgba(255,255,255,.09); border-radius:12px; margin:16px 24px; overflow:hidden">'
      + '<div style="display:grid; grid-template-columns:1fr 100px 110px 120px 120px; gap:10px; padding:9px 16px; background:#10151A; border-bottom:1px solid rgba(255,255,255,.09); ' + M + '; font-size:9px; letter-spacing:.12em; color:rgba(255,255,255,.45)">'
      + '<div>MARKET</div><div style="text-align:right">WALLETS</div><div style="text-align:right">WINDOW</div><div style="text-align:right">NOTIONAL</div><div style="text-align:right">SAME SIDE</div></div>'
      + (timingRows.length ? '' : leerZeile(risikoSatz))
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
    + '<div style="font-size:13px; color:rgba(255,255,255,.55); margin-top:10px; max-width:760px">Best-effort screen on public trade data — research leads, not legal findings. Sports odds, crypto &amp; market prices, and weather are excluded: game results, exchange prices and weather models cannot be traded on early.</div>'
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

    + (laedt
      ? '<div style="display:flex; align-items:center; gap:10px; padding:12px 24px; border-bottom:1px solid rgba(255,255,255,.09); background:#10151A">'
        + '<span style="width:7px; height:7px; border-radius:50%; background:#F5A623; display:inline-block; animation:livePulse 1.2s ease-in-out infinite"></span>'
        + '<span style="' + M + '; font-size:11px; letter-spacing:.08em; color:#F5A623">building the day\'s tape, ~90 s on a cold cache</span>'
        + '<span style="' + M + '; font-size:10.5px; color:rgba(255,255,255,.4)">/api/risk pages a day of prints and looks up market categories; the second visit is instant</span></div>'
      : (T.herkunft.risks && T.herkunft.risks.quelle === 'fehler' && T.neuLaden
        // A failed or rate-limited request can be asked again from here;
        // nothing re-asks on its own. /api/risk shares its rate limit with
        // the backtester, so a 429 usually means "a few backtests just ran".
        ? '<div style="display:flex; align-items:center; gap:12px; padding:12px 24px; border-bottom:1px solid rgba(255,255,255,.09); background:#10151A">'
          + '<span style="' + M + '; font-size:11px; color:#FF7A7A">' + esc(risikoSatz) + '</span>'
          + '<div ' + T.act(() => T.neuLaden('risk', 'risk')) + ' class="hv-bd32" style="' + M + '; font-size:11px; color:rgba(255,255,255,.7); border:1px solid rgba(255,255,255,.16); border-radius:6px; padding:5px 10px; cursor:pointer; white-space:nowrap">Try again</div></div>'
        : ''))
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
  // Kein Rueckfall auf drei erfundene Wallets samt Note und 30-Tage-Gewinn.
  // Wem jemand folgt, weiss nur /api/track.
  return [];
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
  // Vier Maerkte nach Listenposition auszuwaehlen und sie Watchlist zu
  // nennen, war eine Behauptung ueber den Nutzer. Ohne /api/track ist die
  // Watchlist leer.
  return [];
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
    + '</div>' : '<div style="' + M + '; font-size:11.5px; color:rgba(255,255,255,.4); padding:14px 0">No followed wallets reported by /api/track — the list lives in data/followed_wallets.json on the machine that runs the API, and this page only reads it.</div>')
    + '</div>'
    + '<div style="padding:18px 24px">'
    + '<div style="' + M + '; font-size:10.5px; letter-spacing:.14em; color:rgba(255,255,255,.55); margin-bottom:13px">MARKETS ON YOUR WATCHLIST</div>'
    + (watch.length ? '' : '<div style="' + M + '; font-size:11.5px; color:rgba(255,255,255,.4); padding:6px 0">'
      + esc(herkunftSatz(T.liveData.track ? { quelle: T.liveData.track._quelle === 'fehler' ? 'fehler' : 'leer', fehler: T.liveData.track._fehler } : null, '/api/track')) + '</div>')
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
