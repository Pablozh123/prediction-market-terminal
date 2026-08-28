// Leaderboard, Whale flow, Risk screen, Tracked — ported from the design reference.

import { esc, money, num, herkunftSatz, leerBlock, leerZeile, seitenKopf, catChipsPresent, tapeFenster, fensterSatz } from '../util.js';
import { renderClusterGraphics, clusterFarbe } from './cluster_graphics.js';

const M = "font-family:'IBM Plex Mono',monospace";
const LBL9 = M + '; font-size:10.5px; letter-spacing:.14em; color:rgba(var(--ink),.6); margin-bottom:6px';
const HEAD_CELL = M + '; font-size:10.5px; letter-spacing:.14em; color:rgba(var(--ink),.6)';

function filterGroup(label, chipsHtml) {
  return '<div><div style="' + LBL9 + '">' + label + '</div><div style="display:flex; gap:6px; flex-wrap:wrap">' + chipsHtml + '</div></div>';
}

// Score components as a compact labelled list. Prefers the structured
// score_parts from /api/leaderboard; falls back to parsing the older
// "return 90, sharpe-proxy 60, …" string so no raw string reaches the page.
export function scorePartsOf(t) {
  if (t && Array.isArray(t.scoreParts) && t.scoreParts.length) {
    return t.scoreParts.map((p) => ({
      label: String(p.label || ''),
      value: p.value != null ? String(p.value) : '—',
      imputed: !!p.imputed
    }));
  }
  const raw = t && t.tags ? String(t.tags) : '';
  if (!raw) return [];
  return raw.split(',').map((teil) => {
    const m = teil.trim().match(/^([a-z][a-z -]*?)\s+(-?\d+(?:\.\d+)?)$/i);
    return m ? { label: m[1].replace(/-/g, ' '), value: m[2], imputed: false } : null;
  }).filter(Boolean);
}

// Ein Bestandteil, den die Leaderboard-Antwort nicht belegen kann, zeigt
// keine Zahl. Die oeffentliche Antwort traegt nur PnL und Volumen, also
// faellt die Trefferquote auf 0.50 und die Aktualitaet auf 50 zurueck — fuer
// jede Wallet dieselbe Konstante. Als Zahl daneben las sich das wie eine
// Messung dieser Wallet.
function scorePartsHtml(t) {
  const parts = scorePartsOf(t);
  if (!parts.length) return '';
  return '<div style="display:flex; gap:5px; flex-wrap:wrap; margin-top:4px">'
    + parts.map((p) => {
      const wert = p.imputed
        ? '<span style="color:rgba(var(--ink),.62); font-style:italic">assumed</span>'
        : '<span style="color:rgba(var(--ink),.8)">' + esc(p.value) + '</span>';
      const rand = p.imputed ? 'border:1px dashed rgba(var(--ink),.14)' : 'border:1px solid rgba(var(--ink),.1)';
      const titel = p.imputed
        ? ' title="' + esc(p.label + ': the public leaderboard feed carries no input for this component, so the score uses a fixed placeholder — the same one for every wallet') + '"'
        : '';
      return '<span' + titel + ' style="' + M + '; font-size:10.5px; color:rgba(var(--ink),.5); ' + rand + '; border-radius:4px; padding:1px 6px; white-space:nowrap">'
        + esc(p.label) + ' ' + wert + '</span>';
    }).join('')
    + '</div>';
}

// Ein Satz unter der Tabelle: wie viel Gewicht des Scores gemessen ist, was
// geschaetzt wurde und gegen wie viele Wallets der Score gebildet wurde.
export function scoreBasisSatz(rows) {
  const mit = rows.filter((t) => t && t.scoreBasis && t.scoreBasis.imputed && t.scoreBasis.imputed.length);
  if (!mit.length) return '';
  const b = mit[0].scoreBasis;
  const anteil = Math.round((b.measured_weight || 0) * 100);
  const n = b.cohort_n ? ' n = ' + b.cohort_n + ' wallets ranked together; the volume component is a log scale against '
    + 'that set, so it is a rank inside this cohort, not a property of the wallet.' : '';
  return 'Score basis: ' + anteil + '% of the composite weight rests on figures the public leaderboard feed carries '
    + '(profit over volume, volume). The remaining ' + (100 - anteil) + '% (' + b.imputed.join(', ') + ') uses a fixed '
    + 'placeholder that is identical for every wallet, so it separates no wallet from another.' + n;
}

// ---------------------------------------------------------------- traders (leaderboard)
export function renderTraders(T) {
  const s = T.state;
  if (!T.traders.length) {
    return '<div>' + seitenKopf('LEADERBOARD', 'Who is actually good at this', 'var(--accent)')
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

  const badge = tCount ? M + '; font-size:11px; color:var(--on-accent); background:var(--accent); border-radius:4px; padding:1px 7px' : 'display:none';
  const chevron = M + '; font-size:16px; color:rgba(var(--ink),.5); transition:transform .18s ease; transform:rotate(' + (s.traderFiltersOpen ? '90deg' : '0deg') + ')';
  const asOf = T.liveData.leaderboard && T.liveData.leaderboard.as_of ? ' · snapshot ' + T.liveData.leaderboard.as_of : '';
  const basisSatz = scoreBasisSatz(T.traders);
  const grid = '44px 1fr 120px' + (hatWin ? ' 100px' : '') + (hatResolved ? ' 118px' : '') + ' 100px 92px';
  const rankTabs = [T.tab('Smart score', rank === 'score', { traderRank: 'score' }),
    T.tab('Profit', rank === 'pnl', { traderRank: 'pnl' }),
    T.tab('Volume', rank === 'vol', { traderRank: 'vol' }),
    T.tab('Profit / volume', rank === 'roi', { traderRank: 'roi' })]
    .concat(hatWin ? [T.tab('Win rate', rank === 'win', { traderRank: 'win' })] : []).join('');

  return '<div>'
    + '<div style="padding:20px 24px 14px; border-bottom:1px solid rgba(var(--ink),.09)">'
    + '<div style="display:flex; align-items:flex-end; justify-content:space-between; gap:20px">'
    + '<div><div style="' + M + '; font-size:11px; letter-spacing:.18em; color:var(--accent)">LEADERBOARD</div>'
    + '<h1 style="font-size:21px; line-height:1.25; margin:6px 0 0; font-weight:600; letter-spacing:-0.01em">Who is actually good at this</h1></div>'
    + '<div style="display:flex; align-items:center; gap:10px">'
    + '<input value="' + esc(s.traderQuery) + '" ' + T.inp((e) => T.setState({ traderQuery: e.target.value }), 'traderQuery') + ' placeholder="Search name or wallet…" style="background:var(--panel); border:1px solid rgba(var(--ink),.35); border-radius:4px; padding:9px 12px; ' + M + '; font-size:12.5px; color:var(--text); width:230px" />'
    + '<div ' + T.act(() => T.setState({ traderQuery: '', tPnl: 'all', tVol: 'all', traderRank: 'pnl' })) + ' class="hv-bd32" style="font-size:12.5px; color:rgba(var(--ink),.6); border:1px solid rgba(var(--ink),.16); border-radius:4px; padding:9px 13px; cursor:pointer">Reset filters</div>'
    + '</div></div>'
    + '<div style="font-size:13px; color:rgba(var(--ink),.55); margin-top:10px; max-width:760px">Ranked from the public Polymarket all-time leaderboard. The smart score is a weighted composite of the components listed under each wallet; win rate and resolved-bet counts are computed per wallet with sample size and confidence interval — open a wallet to see them.</div>'

    + '<div style="display:flex; align-items:center; gap:20px; margin-top:14px; flex-wrap:wrap">'
    + '<div style="display:flex; align-items:center; gap:8px"><span style="' + LBL9.replace('; margin-bottom:6px', '') + '">RANK BY</span><div style="display:flex; gap:6px; flex-wrap:wrap">'
    + rankTabs + '</div></div>'
    + '</div>'

    + '<div style="border:1px solid rgba(var(--ink),.09); border-radius:6px; margin-top:14px; overflow:hidden">'
    + '<div ' + T.act(() => T.setState({ traderFiltersOpen: !s.traderFiltersOpen })) + ' class="hv-el" style="display:flex; align-items:center; justify-content:space-between; padding:11px 15px; background:var(--panel); cursor:pointer">'
    + '<div style="display:flex; align-items:center; gap:10px"><div style="font-size:13px">Filters</div><div style="' + badge + '">' + tCount + '</div></div>'
    + '<div style="' + chevron + '">›</div></div>'
    + (s.traderFiltersOpen ?
      '<div style="padding:16px; display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:16px 20px">'
      + filterGroup('PROFIT', [['all','All'],['500k','>$500k'],['1m','>$1m'],['2m','>$2m'],['5m','>$5m']].map((o) => T.opt(o[1], s.tPnl === o[0], { tPnl: o[0] })).join(''))
      + filterGroup('VOLUME', [['all','All'],['10k','>$10k'],['100k','>$100k'],['1m','>$1m'],['50m','>$50m']].map((o) => T.opt(o[1], s.tVol === o[0], { tVol: o[0] })).join(''))
      + '</div>' : '')
    + '</div>'
    + '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.6); margin-top:12px">' + traderSorted.length + ' of ' + T.traders.length + ' wallets · all-time' + esc(asOf) + '</div>'
    + (basisSatz ? '<div style="font-size:12px; color:rgba(var(--ink),.55); margin-top:8px; max-width:820px; line-height:1.6">' + esc(basisSatz) + '</div>' : '')
    + '</div>'

    + '<div style="display:grid; grid-template-columns:' + grid + '; padding:10px 24px; border-bottom:1px solid rgba(var(--ink),.09); background:var(--panel); ' + HEAD_CELL + '">'
    + '<div>#</div><div>WALLET · SCORE COMPONENTS</div><div style="text-align:right">PROFIT</div>'
    + (hatWin ? '<div style="text-align:right">WIN RATE</div>' : '')
    + (hatResolved ? '<div style="text-align:right">RESOLVED BETS</div>' : '')
    + '<div style="text-align:right">VOLUME</div><div style="text-align:right">SCORE</div></div>'
    + traderSorted.map((t, i) => {
      const score = t.score;
      const avatarStyle = 'width:28px; height:28px; flex:none; border-radius:4px; background:var(--panel-hover); border:1px solid rgba(var(--ink),.09); display:flex; align-items:center; justify-content:center; ' + M + '; font-size:12px; color:' + (score != null && score >= 80 ? 'var(--accent)' : 'rgba(var(--ink),.6)');
      const scoreStyle = M + '; font-size:12.5px; border-radius:4px; padding:3px 9px; ' + (score == null ? 'color:rgba(var(--ink),.6); border:1px solid rgba(var(--ink),.12)' : score >= 80 ? 'color:var(--on-accent); background:var(--accent)' : score >= 60 ? 'color:rgba(var(--ink),.8); border:1px solid rgba(var(--ink),.2)' : 'color:var(--warn); border:1px solid rgba(var(--warn-rgb),.35)');
      return '<div ' + T.act(() => T.openWallet(t.name)) + ' class="hv-panel" style="display:grid; grid-template-columns:' + grid + '; align-items:center; padding:13px 24px; border-bottom:1px solid rgba(var(--ink),.06); cursor:pointer">'
        + '<div style="' + M + '; font-size:13px; color:rgba(var(--ink),.6)">' + (i + 1) + '</div>'
        + '<div style="display:flex; align-items:center; gap:10px; min-width:0">'
        + '<div style="' + avatarStyle + '">' + esc(t.name.charAt(0).toUpperCase()) + '</div>'
        + '<div style="min-width:0"><div style="font-size:13.5px">' + esc(t.name) + '</div>'
        + '<div style="' + M + '; font-size:10.5px; color:rgba(var(--ink),.6); margin-top:2px">' + esc(t.wallet) + (t.grade ? ' · grade ' + esc(t.grade) : '') + '</div>'
        + scorePartsHtml(t) + '</div></div>'
        + '<div style="' + M + '; font-size:14px; text-align:right; color:' + (t.pnl >= 0 ? 'var(--pos)' : 'var(--neg)') + '">' + money(t.pnl) + '</div>'
        + (hatWin ? '<div style="' + M + '; font-size:13px; text-align:right">' + (t.win != null ? Math.round(t.win * 100) + '%' : '—') + '</div>' : '')
        + (hatResolved ? '<div style="' + M + '; font-size:12.5px; text-align:right; color:rgba(var(--ink),.55)">' + (t.resolved != null ? num(t.resolved) : '—') + '</div>' : '')
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
    return '<div>' + seitenKopf('WHALE FLOW', 'Who is moving the big money', 'var(--accent)')
      + leerBlock('NO PRINTS TO GROUP', herkunftSatz(T.herkunft.tape, '/api/tape')) + '</div>';
  }
  // Kalshi publishes no wallet identities, so its prints cannot be grouped
  // and are counted here only to say how many were left out.
  const ohneWallet = T.tape.filter((t) => t.wallet === '—').length;
  const mitWallet = T.tape.length - ohneWallet;
  if (!mitWallet) {
    return '<div>' + seitenKopf('WHALE FLOW', 'Who is moving the big money', 'var(--accent)')
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
    return '<div>' + seitenKopf('WHALE FLOW', 'Who is moving the big money', 'var(--accent)')
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
    if ((t.dir || 'BUY') === 'BUY') { w.buys++; w.buyDollar += size; } else { w.sells++; w.sellDollar += size; }
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
  const fensterZeile = fensterSatz(tapeFenster(grouped));
  const ausschlussSatz = ohneWallet
    ? ' ' + ohneWallet + ' Kalshi print(s) are not shown here: Kalshi publishes no wallet identities, so they cannot be grouped.'
    : '';
  const kpi = (label, value, sub, last) =>
    '<div style="padding:14px 20px' + (last ? '' : '; border-right:1px solid rgba(var(--ink),.09)') + '">'
    + '<div style="' + M + '; font-size:11px; letter-spacing:.14em; color:rgba(var(--ink),.6)">' + label + '</div>'
    + '<div style="' + M + '; font-size:24px; margin-top:7px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis">' + value + '</div>'
    + (sub ? '<div style="' + M + '; font-size:10.5px; color:rgba(var(--ink),.6); margin-top:3px">' + sub + '</div>' : '')
    + '</div>';
  // Die Spaltensummen lagen ueber der Breite des Inhaltsbereichs (1040 px
  // Minimum gegen 958 px Platz), also schob die Tabelle die Seite seitwaerts.
  // Die flexiblen Spalten bekommen kleinere Mindestbreiten; ueberlange Titel
  // faengt die Ellipse ab, wie in den anderen Tabellen auch.
  const GRID = 'minmax(140px,1.2fr) 58px 92px 92px 110px 62px minmax(110px,1fr) 108px 74px';

  return '<div>'
    + '<div style="padding:20px 24px 16px; border-bottom:1px solid rgba(var(--ink),.09)">'
    + '<div style="' + M + '; font-size:11px; letter-spacing:.18em; color:var(--accent)">WHALE FLOW</div>'
    + '<h1 style="font-size:21px; line-height:1.25; margin:6px 0 0; font-weight:600; letter-spacing:-0.01em">Who is moving the big money</h1>'
    + '<div style="font-size:13px; color:rgba(var(--ink),.55); margin-top:9px; max-width:760px">The same prints as the tape, grouped by wallet, so one wallet buying twenty times reads as one story instead of twenty rows. Every figure below is a sum over the prints in this tape window' + (whaleCat === 'All' ? '' : ' in the category ' + esc(whaleCat)) + '.' + esc(ausschlussSatz) + '</div>'
    + '<div style="display:flex; align-items:center; gap:8px; margin-top:12px; flex-wrap:wrap">'
    + '<span style="' + LBL9.replace('; margin-bottom:6px', '') + '">CATEGORY</span>'
    + catChips.map((c) => T.chip(c.toUpperCase(), whaleCat === c, { whaleCat: c })).join('')
    + '</div>'
    + '<div style="display:flex; align-items:center; gap:8px; margin-top:10px; flex-wrap:wrap">'
    + '<span style="' + LBL9.replace('; margin-bottom:6px', '') + '">SORT BY</span>'
    + T.chip('Total $', sortKey === 'total', { whaleSort: 'total' })
    + T.chip('Biggest print', sortKey === 'biggest', { whaleSort: 'biggest' })
    + T.chip('Prints', sortKey === 'prints', { whaleSort: 'prints' })
    + '<span style="' + M + '; font-size:11px; color:rgba(var(--ink),.6); margin-left:6px">' + (walletCount > SHOW ? 'top ' + SHOW + ' of ' + num(walletCount) + ' wallets' : num(walletCount) + ' wallet' + (walletCount === 1 ? '' : 's')) + ' · ' + num(grouped.length) + ' print' + (grouped.length === 1 ? '' : 's') + ' grouped</span>'
    + '</div></div>'
    + '<div style="display:grid; grid-template-columns:repeat(5,1fr); border-bottom:1px solid rgba(var(--ink),.09)">'
    + kpi('WALLETS PRINTING BIG', num(walletCount), '')
    + kpi('PRINTS GROUPED', num(grouped.length), ohneWallet ? num(ohneWallet) + ' without a wallet left out' : '')
    + kpi('$ GROUPED · THIS WINDOW', money(total), '')
    + kpi('BIGGEST SINGLE PRINT', money(biggest), '')
    + kpi('TOP CATEGORY BY $', esc(topCatLabel), esc(topCatShare), true)
    + '</div>'
    // Ueber welche Spanne die Kennzahlen summiert wurden. Ohne sie liest
    // sich "$ GROUPED · THIS WINDOW" wie eine Tagessumme, obwohl der
    // oeffentliche Feed nur die juengsten Prints liefert und die Spanne mit
    // der Aktivitaet schwankt.
    + (fensterZeile ? '<div style="padding:9px 24px; border-bottom:1px solid rgba(var(--ink),.09); ' + M + '; font-size:11px; color:rgba(var(--ink),.55)">'
      + '<span style="letter-spacing:.14em; color:rgba(var(--ink),.6); margin-right:8px">SUMMED OVER</span>' + esc(fensterZeile) + '</div>' : '')
    + '<div style="padding:10px 24px; border-bottom:1px solid rgba(var(--ink),.09); font-size:12px; color:rgba(var(--ink),.55)"><span style="' + M + '; font-size:10.5px; letter-spacing:.14em; color:rgba(var(--ink),.6); margin-right:8px">CONCENTRATION</span>' + esc(konzentrationSatz) + '</div>'
    + '<div style="display:grid; grid-template-columns:' + GRID + '; gap:0 10px; padding:10px 24px; border-bottom:1px solid rgba(var(--ink),.09); background:var(--panel); ' + HEAD_CELL + '">'
    + '<div>WALLET · VENUE</div><div style="text-align:right">PRINTS</div><div style="text-align:right">TOTAL</div><div style="text-align:right">BIGGEST</div><div style="text-align:right">LEANING</div><div style="text-align:right">MARKETS</div><div>TOP MARKET</div><div style="text-align:right">MOSTLY IN</div><div style="text-align:right">LAST PRINT</div></div>'
    + (rows.length ? '' : leerZeile('Every print in this window is anonymous — Kalshi publishes no wallet identity, so there is nothing to group by.'))
    + rows.map((w) => {
      // "MOSTLY" war ein Alphawert auf demselben Rot — bei 11 px landete das
      // bei 3.6:1 und damit unter der Lesbarkeitsschwelle. Jetzt trennt der
      // gedaempftere Farbton der Palette (var(--neg-soft)) die beiden Staerken, statt
      // Deckkraft wegzunehmen.
      const leanColor = w.lean === 'BUYING' ? 'var(--pos)' : w.lean === 'SELLING' ? 'var(--neg)' : w.lean === 'MOSTLY BUYING' ? 'rgba(var(--pos-rgb),.75)' : 'var(--neg-soft)';
      const leanStyle = M + '; font-size:11px; letter-spacing:.08em; text-align:right; color:' + leanColor;
      const topMarketShare = w.total ? Math.round(w.topMarket.dollar / w.total * 100) : 0;
      // The drawer gets the address too: most of these wallets are not on
      // the leaderboard, and without it the click opened nothing (w.wallet is
      // the full address when the print carried one, else the name again —
      // openWallet keeps only a full address).
      return '<div ' + T.act(() => T.openWallet(w.name, w.wallet !== w.name ? w.wallet : '')) + ' class="hv-panel" style="display:grid; grid-template-columns:' + GRID + '; gap:0 10px; align-items:center; padding:12px 24px; border-bottom:1px solid rgba(var(--ink),.06); cursor:pointer">'
        + '<div style="min-width:0"><div style="font-size:13.5px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="' + esc(w.name) + '">' + esc(w.name) + '</div>'
        + '<div style="' + M + '; font-size:10.5px; color:rgba(var(--ink),.6); margin-top:3px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="' + esc(w.wallet) + '">' + esc(w.wallet) + ' · ' + esc(w.venues) + '</div></div>'
        + '<div style="' + M + '; font-size:13px; text-align:right; color:rgba(var(--ink),.6)">' + w.prints + '</div>'
        + '<div style="' + M + '; font-size:14px; text-align:right">' + money(w.total) + '</div>'
        + '<div style="' + M + '; font-size:13px; text-align:right; color:rgba(var(--ink),.6)">' + money(w.biggest) + '</div>'
        + '<div><div style="' + leanStyle + '">' + esc(w.lean) + '</div>'
        + '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.6); text-align:right; margin-top:2px">' + w.buys + ' buy' + (w.buys === 1 ? '' : 's') + ' · ' + w.sells + ' sell' + (w.sells === 1 ? '' : 's') + '</div></div>'
        + '<div style="' + M + '; font-size:13px; text-align:right; color:rgba(var(--ink),.6)">' + w.marketCount + '</div>'
        + '<div style="min-width:0"><div style="font-size:12px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="' + esc(w.topMarket.title) + '">' + esc(w.topMarket.title) + '</div>'
        + '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.6); margin-top:2px">' + money(w.topMarket.dollar) + ' · ' + topMarketShare + '% of this wallet</div></div>'
        + '<div style="text-align:right"><div style="' + M + '; font-size:11.5px; color:rgba(var(--ink),.75)">' + esc(w.cat) + '</div>'
        + '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.6); margin-top:2px">' + esc(w.catShare) + ' prints</div></div>'
        + '<div style="' + M + '; font-size:11px; text-align:right; color:rgba(var(--ink),.5)">' + esc(w.lastAgo) + '</div></div>';
    }).join('')
    + '</div>';
}

// ---------------------------------------------------------------- risk screen
// Helpers for the event cards and the flag log. Every field they read comes
// from /api/risk (api_views.risk_event_row) or /api/risk/log; a missing value
// renders as "—" or "n/a", never as a default number.
const CHIP = M + '; font-size:10.5px; color:rgba(var(--ink),.55); border:1px solid rgba(var(--ink),.1); border-radius:4px; padding:1px 6px; white-space:nowrap';
const NOTE_R = M + '; font-size:11px; color:rgba(var(--ink),.6); line-height:1.6';
const LINK = 'color:var(--accent); text-decoration:none; ' + M + '; font-size:10.5px; letter-spacing:.06em';

function cents(p) {
  return (p == null || isNaN(p)) ? '—' : Math.round(Number(p) * 100) + '¢';
}

function utcShort(iso) {
  // "2026-08-16T12:20:00Z" -> "16 Aug 12:20"; the API stamps are UTC.
  const m = String(iso || '').match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
  if (!m) return '—';
  const monate = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return Number(m[3]) + ' ' + monate[Number(m[2]) - 1] + ' ' + m[4] + ':' + m[5];
}

function windowLabel(first, last, minutes) {
  if (!first && !last) return '—';
  const span = minutes == null ? '' : ' · ' + (minutes < 90 ? Math.round(minutes) + ' min' : (minutes / 60).toFixed(1) + ' h');
  return utcShort(first) + ' – ' + utcShort(last).replace(/^\d+ \w+ /, '') + ' UTC' + span;
}

// The dominant side of the flow as a chip: "NO buys $12k of $14k (86%)".
export function riskSideChip(r) {
  const side = r && r.side ? String(r.side) : '';
  if (!side) return '<span style="' + CHIP + '">side n/a</span>';
  const isNo = /^NO/.test(side);
  const isSell = /sells$/.test(side);
  const farbe = isSell ? 'var(--neg-soft)' : isNo ? 'var(--warn)' : 'var(--accent)';
  const total = r.notional_usd != null ? money(r.notional_usd) : String(r.notional || '');
  const anteil = r.side_share != null ? ' (' + Math.round(r.side_share * 100) + '%)' : '';
  return '<span style="' + M + '; font-size:10.5px; letter-spacing:.06em; color:' + farbe + '; border:1px solid color-mix(in srgb, ' + farbe + ' 33%, transparent); border-radius:4px; padding:2px 7px; white-space:nowrap">'
    + esc(side) + ' ' + esc(money(r.side_notional || 0)) + ' of ' + esc(total) + esc(anteil) + '</span>';
}

// Price of the flagged side at flag time: "NO 34¢ (30–34¢)".
export function riskPriceLabel(r) {
  if (!r || r.price_last == null) return 'price n/a';
  const out = r.price_outcome ? r.price_outcome + ' ' : '';
  const range = (r.price_min != null && r.price_max != null && (r.price_min !== r.price_max))
    ? ' (' + cents(r.price_min) + '–' + cents(r.price_max) + ')' : '';
  return out + cents(r.price_last) + range;
}

// The three families the composition bar folds the scoring parts into: how
// big the money is (grey), when and at what price it moved (amber), and who
// moved it (lime). Same grouping as the page legend; the per-part detail
// stays in the "Why?" breakdown.
const FAM_GROESSE = ['component_notional', 'component_largest'];
const FAM_TIMING = ['component_long_odds', 'component_late', 'price_move_score'];
const FAM_MUSTER = ['component_concentration', 'component_direction', 'component_burst', 'component_cluster', 'component_fresh_wallets', 'component_coordination'];

// The score as a 0-100 bar: the measured family points (after the context
// multiplier) as colored segments, threshold ticks at 40/55/70 and a marker
// at the card's score. When an older answer carries only some parts, the
// segments simply stop short of the marker — the gap is honest, nothing is
// invented to close it (the breakdown says "parts missing" the same way).
export function riskCompositionBar(components, score) {
  if (!Array.isArray(components) || !components.length) return '';
  const punkte = (keys) => components
    .filter((c) => c && keys.indexOf(c.key) >= 0)
    .reduce((acc, c) => acc + (Number(c.value) > 0 ? Number(c.value) : 0), 0);
  const ctx = components.find((c) => c && c.key === 'context_multiplier');
  const faktor = ctx && Number(ctx.value) > 0 ? Number(ctx.value) : 1;
  const groesse = punkte(FAM_GROESSE) * faktor;
  const timing = punkte(FAM_TIMING) * faktor;
  const muster = punkte(FAM_MUSTER) * faktor;
  const gesamt = groesse + timing + muster;
  if (!(gesamt > 0)) return '';
  const skala = gesamt > 100 ? 100 / gesamt : 1;
  const seg = (w, farbe) => (w > 0 ? '<div style="width:' + (w * skala).toFixed(2) + '%; background:' + farbe + '"></div>' : '');
  const tick = (p, farbe) => '<div style="position:absolute; left:' + p + '%; top:-3px; width:1px; height:16px; background:' + farbe + '"></div>';
  const wert = Math.max(0, Math.min(100, Number(score) || 0));
  return '<div style="margin-top:10px">'
    + '<div style="position:relative; height:10px">'
    + '<div style="display:flex; height:10px; border-radius:4px; overflow:hidden; background:rgba(var(--ink),.07)">'
    + seg(groesse, 'rgba(var(--ink),.42)') + seg(timing, 'var(--warn)') + seg(muster, 'var(--accent)')
    + '</div>'
    + tick(40, 'rgba(var(--ink),.28)') + tick(55, 'rgba(var(--ink),.28)') + tick(70, 'rgba(var(--warn-rgb),.6)')
    + '<div style="position:absolute; left:' + wert.toFixed(1) + '%; top:-3px; width:2px; height:16px; background:rgba(var(--ink),.9)"></div>'
    + '</div>'
    + '<div style="' + M + '; font-size:10.5px; color:rgba(var(--ink),.55); margin-top:5px">size ' + groesse.toFixed(1) + ' · price &amp; timing ' + timing.toFixed(1) + ' · wallet pattern ' + muster.toFixed(1) + '</div>'
    + '</div>';
}

// The whole flow as one bar — YES buys (lime), NO buys (amber), sells (red)
// — with the dominant-side chip below it and the remaining buckets named.
// Values come from side_split; a card without the split keeps the chip alone.
export function riskFlowRow(r) {
  const teil = r && r.side_split ? r.side_split : null;
  const kaufYes = teil ? Number(teil.buy_yes) || 0 : 0;
  const kaufNo = teil ? Number(teil.buy_no) || 0 : 0;
  const verkauf = teil ? (Number(teil.sell_yes) || 0) + (Number(teil.sell_no) || 0) : 0;
  const gesamt = kaufYes + kaufNo + verkauf;
  const seg = (w, farbe) => (w > 0 ? '<div style="width:' + ((w / gesamt) * 100).toFixed(2) + '%; background:' + farbe + '"></div>' : '');
  const balken = gesamt > 0
    ? '<div style="display:flex; height:8px; border-radius:4px; overflow:hidden; background:rgba(var(--ink),.06); margin-bottom:5px">'
      + seg(kaufYes, 'var(--accent)') + seg(kaufNo, 'var(--warn)') + seg(verkauf, 'var(--neg-soft)') + '</div>'
    : '';
  const rest = gesamt > 0
    ? [['YES buys', kaufYes, 'var(--pos)'], ['NO buys', kaufNo, 'var(--warn)'], ['sells', verkauf, 'var(--neg-soft)']]
      .filter((b) => b[1] > 0 && String(r.side || '').indexOf(b[0]) !== 0)
      .map((b) => '<span style="color:' + b[2] + '">' + b[0] + ' ' + money(b[1]) + '</span>').join(' · ')
    : '';
  return '<div style="margin-top:10px">' + balken
    + '<div style="display:flex; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap">'
    + riskSideChip(r)
    + (rest ? '<span style="' + M + '; font-size:10.5px; color:rgba(var(--ink),.55)">' + rest + '</span>' : '')
    + '</div></div>';
}

// Where the flagged side's price sat on the 0-100¢ scale: min-max band,
// marker at the last print, and how far it moved over the window.
export function riskPriceStrip(r) {
  if (!r || r.price_last == null) return '';
  const min = r.price_min != null ? Number(r.price_min) : Number(r.price_last);
  const max = r.price_max != null ? Number(r.price_max) : Number(r.price_last);
  const links = Math.max(0, Math.min(99, min * 100));
  const band = Math.max(1, Math.min(100 - links, (max - min) * 100));
  const diff = r.price_first != null ? Math.round((Number(r.price_last) - Number(r.price_first)) * 100) : null;
  const bewegt = diff == null ? '' : ' · ' + (diff === 0 ? 'unchanged in the window' : (diff > 0 ? '+' : '') + diff + '¢ in the window');
  return '<div style="flex:1; min-width:0">'
    + '<div style="position:relative; height:8px; border-radius:4px; background:rgba(var(--ink),.06)">'
    + '<div style="position:absolute; left:' + links.toFixed(1) + '%; top:0; width:' + band.toFixed(1) + '%; height:8px; border-radius:4px; background:rgba(var(--warn-rgb),.4)"></div>'
    + '<div style="position:absolute; left:' + Math.max(0, Math.min(99, Number(r.price_last) * 100)).toFixed(1) + '%; top:-2px; width:2px; height:12px; background:var(--warn)"></div>'
    + '</div>'
    + '<div style="' + M + '; font-size:10.5px; color:rgba(var(--ink),.55); margin-top:5px">at flag ' + esc(riskPriceLabel(r)) + bewegt + '</div>'
    + '</div>';
}

// The window as a tick strip: one tick per sampled print at its real
// position (print_offsets from the API, 0..1). A burst reads as a clump of
// ticks. Without offsets (older answer) the caption alone remains — the
// positions are measured, never invented.
export function riskWindowStrip(r) {
  if (!r || (!r.first_print && !r.last_print)) return '';
  const offsets = Array.isArray(r.print_offsets) ? r.print_offsets : [];
  const ticks = offsets.length
    ? '<div style="position:relative; height:8px">'
      + offsets.map((o) => '<div style="position:absolute; left:' + Math.max(0, Math.min(98, (Number(o) || 0) * 98)).toFixed(1) + '%; top:0; width:2px; height:8px; background:rgba(var(--ink),.55)"></div>').join('')
      + '<div style="position:absolute; left:0; right:0; bottom:-2px; height:1px; background:rgba(var(--ink),.12)"></div>'
      + '</div>'
    : '';
  return '<div style="flex:1; min-width:0">' + ticks
    + '<div style="' + M + '; font-size:10.5px; color:rgba(var(--ink),.55); margin-top:5px">' + esc(windowLabel(r.first_print, r.last_print, r.window_minutes)) + (r.prints ? ' · ' + r.prints + ' print' + (r.prints === 1 ? '' : 's') : '') + '</div>'
    + '</div>';
}

// Score components with points; zero components are left out (nothing to
// explain), the context multiplier is shown when it is not 1.
export function riskComponentsHtml(components) {
  if (!Array.isArray(components) || !components.length) return '';
  const teile = components.filter((c) => c && (c.key === 'context_multiplier' ? Number(c.value) !== 1 : Number(c.value) > 0));
  if (!teile.length) return '<span style="' + CHIP + '">no component above zero</span>';
  return teile.map((c) => '<span style="' + CHIP + '">' + esc(c.label) + ' <span style="color:rgba(var(--ink),.85)">'
    + (c.key === 'context_multiplier' ? '×' + esc(String(c.value)) : esc(String(c.value)) + (c.max != null ? '/' + esc(String(c.max)) : '')) + '</span></span>').join('');
}

// The score, taken apart: one row per component that scored — a plain
// label, a bar against its cap, the points, and under it what the tape
// showed and what full marks would take (both from the API: fact / rule).
// Components at zero fold into one "not found" line, the context multiplier
// closes the list, and the last line does the arithmetic so the reader can
// check the score. Older payloads without fact/rule get the bar and label.
export function riskScoreBreakdown(components, score) {
  if (!Array.isArray(components) || !components.length) return '';
  const rows = components.filter((c) => c && c.key !== 'context_multiplier');
  const ctx = components.find((c) => c && c.key === 'context_multiplier') || null;
  const scored = rows.filter((c) => Number(c.value) > 0).sort((a, b) => Number(b.value) - Number(a.value));
  const zero = rows.filter((c) => !(Number(c.value) > 0));
  const summe = scored.reduce((acc, c) => acc + Number(c.value), 0);
  const faktor = ctx ? Number(ctx.value) : 1;
  const bar = (c) => {
    const max = Number(c.max) || 1;
    const anteil = Math.max(0, Math.min(1, Number(c.value) / max));
    const voll = anteil >= 0.66;
    const farbe = voll ? 'var(--warn)' : 'rgba(var(--ink),.55)';
    const unter = [c.fact, c.rule].filter(Boolean).map((t) => esc(String(t))).join(' <span style="color:rgba(var(--ink),.5)">·</span> ')
      + (c.weight_note ? ' <span style="color:var(--warn)">' + esc(c.weight_note) + '</span>' : '');
    return '<div style="padding:6px 0; border-bottom:1px solid rgba(var(--ink),.05)">'
      + '<div style="display:flex; align-items:center; gap:10px">'
      + '<div style="flex:0 0 158px; font-size:12.5px; color:rgba(var(--ink),.85)" title="' + esc(String(c.measures || '')) + '">' + esc(String(c.label || c.key || '')) + '</div>'
      + '<div style="flex:1; height:6px; border-radius:4px; background:rgba(var(--ink),.08); overflow:hidden"><div style="width:' + (anteil * 100).toFixed(1) + '%; height:6px; background:' + farbe + '"></div></div>'
      + '<div style="flex:0 0 64px; text-align:right; ' + M + '; font-size:11.5px; color:' + (voll ? 'var(--warn)' : 'rgba(var(--ink),.8)') + '">' + esc(String(c.value)) + '<span style="color:rgba(var(--ink),.55)">/' + esc(String(c.max)) + '</span></div>'
      + '</div>'
      + (unter ? '<div style="font-size:11px; color:rgba(var(--ink),.5); margin-top:3px; padding-left:0; line-height:1.45">' + unter + '</div>' : '')
      + '</div>';
  };
  const nichts = zero.length
    ? '<div style="font-size:11px; color:rgba(var(--ink),.6); padding:7px 0; line-height:1.5"><span style="' + M + '; font-size:10.5px; letter-spacing:.12em; color:rgba(var(--ink),.55)">NOT FOUND</span> '
      + zero.map((c) => esc(String(c.label || c.key || '')).toLowerCase() + (c.fact ? ' <span style="color:rgba(var(--ink),.5)">(' + esc(String(c.fact)) + ')</span>' : '')).join(' · ') + '</div>'
    : '';
  const kontext = ctx
    ? '<div style="display:flex; align-items:baseline; gap:10px; padding:7px 0; border-top:1px solid rgba(var(--ink),.05)">'
      + '<div style="flex:0 0 158px; font-size:12.5px; color:rgba(var(--ink),.85)">' + esc(String(ctx.label || 'Context')) + '</div>'
      + '<div style="flex:1; font-size:11px; color:rgba(var(--ink),.5); line-height:1.45">' + esc(String(ctx.fact || '')) + (ctx.rule ? ' <span style="color:rgba(var(--ink),.5)">· ' + esc(String(ctx.rule)) + '</span>' : '') + '</div>'
      + '<div style="flex:0 0 64px; text-align:right; ' + M + '; font-size:11.5px; color:' + (faktor > 1 ? 'var(--warn)' : faktor < 1 ? 'rgba(var(--ink),.5)' : 'rgba(var(--ink),.8)') + '">×' + esc(String(ctx.value)) + '</div></div>'
    : '';
  // The arithmetic, checkable: parts × context = score. When the listed
  // parts do not reach the score (an older answer without every column),
  // the line says so instead of pretending they do.
  const produkt = Math.min(100, Math.round(summe * faktor));
  const stimmt = score == null || Math.abs(produkt - Number(score)) <= 1;
  const rechnung = '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.55); padding-top:8px; border-top:1px solid rgba(var(--ink),.08); margin-top:2px">'
    + summe.toFixed(1) + ' pts' + (ctx ? ' × ' + esc(String(ctx.value)) : '') + ' = <span style="color:var(--text)">' + produkt + '</span> / 100'
    + (stimmt ? '' : ' <span style="color:var(--warn)">· the card says ' + esc(String(score)) + ' — parts missing from this answer</span>')
    + ' <span style="color:rgba(var(--ink),.55)">· under 40 low · 40–54 elevated · 55–69 medium · 70+ high</span></div>';
  return '<div>' + scored.map(bar).join('') + nichts + kontext + rechnung + '</div>';
}

// Top wallets with share and profile link; "fresh" when the tape-relative
// proxy says so, nothing when it was not computed.
export function riskWalletsHtml(wallets, count) {
  if (!Array.isArray(wallets) || !wallets.length) {
    return count ? '' : '<span style="' + CHIP + '">wallet identities not public on this venue</span>';
  }
  return wallets.map((w) => {
    const label = esc(w.short || w.wallet || '—') + (w.share != null ? ' ' + Math.round(w.share * 100) + '%' : '')
      + (w.side ? ' · ' + esc(w.side) : '') + (w.fresh ? ' · fresh' : '');
    return w.url
      ? '<a data-stop href="' + esc(w.url) + '" target="_blank" rel="noopener" style="' + CHIP + '; color:var(--accent); text-decoration:none">' + label + ' ↗</a>'
      : '<span style="' + CHIP + '">' + label + '</span>';
  }).join('');
}

// Reads the book answer for a card: null when the card has no wallets or is
// not a Polymarket conditionId (Kalshi has no wallets); otherwise the cached
// entry (loading / fehler / live) after asking for it once.
function riskBookEntry(T, r) {
  if (!r || !Array.isArray(r.top_wallets) || !r.top_wallets.length) return null;
  if (String(r.venue || 'Polymarket').toLowerCase() !== 'polymarket') return null;
  const key = String(r.market_key || '');
  if (!/^0x[0-9a-f]{64}$/i.test(key)) return null;
  if (typeof T.fetchRiskBook === 'function') T.fetchRiskBook(key, r.top_wallets, r.side || '');
  const eintrag = T.liveData && T.liveData.riskBook ? T.liveData.riskBook[key] : null;
  return eintrag || { herkunft: 'loading' };
}

const BOOK_FARBE = (rel) => rel === 'adds' || rel === 'new_bet' ? 'var(--accent)' : rel === 'reduces' || rel === 'hedge' || rel === 'exit' ? 'var(--warn)' : 'rgba(var(--ink),.6)';
const BOOK_WORT = (rel) => rel === 'adds' ? 'ADDS TO BOOK' : rel === 'reduces' ? 'HEDGE / CLOSING' : rel === 'hedge' ? 'HEDGED BOTH SIDES' : rel === 'exit' ? 'EXIT' : rel === 'new_bet' ? 'NOT HELD NOW' : 'BOOK';
const BOOK_KURZ = (rel) => rel === 'adds' ? 'adds' : rel === 'reduces' ? 'hedge / closing' : rel === 'hedge' ? 'hedged' : rel === 'exit' ? 'exit' : rel === 'new_bet' ? 'not held' : 'book';

// One line for the closed card: "BOOK NOW 1 adds · 2 not held" — the
// relation counts, coloured like the full lines. "reading…" / "not read"
// while the answer is missing. Empty string when the card has no book.
export function riskBookSummary(T, r) {
  const eintrag = riskBookEntry(T, r);
  if (!eintrag) return '';
  const kopf = '<span style="' + M + '; font-size:10.5px; letter-spacing:.12em; color:rgba(var(--ink),.6)">BOOK NOW</span> ';
  const grau = '<span style="font-size:11.5px; color:rgba(var(--ink),.6)">';
  if (eintrag.herkunft === 'loading') return '<div style="margin-top:8px">' + kopf + grau + 'reading the wallets\' open positions…</span></div>';
  if (eintrag.herkunft === 'fehler') return '<div style="margin-top:8px">' + kopf + grau + 'not read (' + esc(eintrag.fehler || 'no answer') + ')</span></div>';
  const books = eintrag.data && Array.isArray(eintrag.data.wallets) ? eintrag.data.wallets : [];
  if (!books.length) return '<div style="margin-top:8px">' + kopf + grau + 'no wallet readable</span></div>';
  const zaehler = {};
  let ungelesen = 0;
  books.forEach((b) => { if (!b.read) { ungelesen += 1; return; } zaehler[b.relation || 'book'] = (zaehler[b.relation || 'book'] || 0) + 1; });
  const teile = Object.keys(zaehler).map((rel) => '<span style="' + M + '; font-size:10.5px; color:' + BOOK_FARBE(rel) + '">' + zaehler[rel] + ' ' + BOOK_KURZ(rel) + '</span>');
  if (ungelesen) teile.push('<span style="' + M + '; font-size:10.5px; color:rgba(var(--ink),.6)">' + ungelesen + ' not read</span>');
  return '<div style="margin-top:8px; display:flex; align-items:center; gap:8px; flex-wrap:wrap">' + kopf + teile.join('<span style="color:rgba(var(--ink),.5)">·</span>') + '</div>';
}

// The book behind the flow, one line per wallet: what the top wallets hold in
// this market right now (/api/risk/book), and whether the flagged flow adds to
// that book, works against it (hedge / closing / merging) or exits it. A
// wallet on 12k NO that buys YES is not a YES bet — the tape says "YES buys",
// the book says "net NO"; this line says which. Polymarket only (Kalshi has
// no wallets); read now, not at flag time; "reading" until the answer is there.
export function riskBookHtml(T, r) {
  const eintrag = riskBookEntry(T, r);
  if (!eintrag) return '';
  const kopf = '<span style="' + M + '; font-size:10.5px; letter-spacing:.12em; color:rgba(var(--ink),.6)">WALLET BOOK NOW</span> ';
  if (eintrag.herkunft === 'loading') return '<div style="margin-top:8px; font-size:11.5px; color:rgba(var(--ink),.6)">' + kopf + 'reading the wallets\' open positions in this market…</div>';
  if (eintrag.herkunft === 'fehler') return '<div style="margin-top:8px; font-size:11.5px; color:rgba(var(--ink),.6)">' + kopf + 'not read (' + esc(eintrag.fehler || 'no answer') + ')</div>';
  const books = eintrag.data && Array.isArray(eintrag.data.wallets) ? eintrag.data.wallets : [];
  if (!books.length) return '<div style="margin-top:8px; font-size:11.5px; color:rgba(var(--ink),.6)">' + kopf + 'no wallet readable</div>';
  return '<div style="margin-top:8px; display:flex; flex-direction:column; gap:4px">'
    + books.map((b) => {
      if (!b.read) return '<div style="font-size:11.5px; color:rgba(var(--ink),.6)">' + kopf + esc(b.short || b.wallet) + ' not read (' + esc(b.error || 'no answer') + ')</div>';
      const netz = b.net === 'YES' || b.net === 'NO' ? 'net ' + b.net : b.net === 'balanced' ? 'balanced' : 'flat';
      return '<div style="font-size:11.5px; line-height:1.45; color:rgba(var(--ink),.7)">' + kopf
        + '<span style="' + M + '; color:rgba(var(--ink),.85)">' + esc(b.short || b.wallet) + '</span> '
        + '<span style="' + M + '; font-size:11px; letter-spacing:.08em; color:' + BOOK_FARBE(b.relation) + '; border:1px solid color-mix(in srgb, ' + BOOK_FARBE(b.relation) + ' 33%, transparent); border-radius:4px; padding:1px 6px; margin:0 4px">' + BOOK_WORT(b.relation) + ' · ' + esc(netz) + '</span>'
        + esc(b.text || '') + '</div>';
    }).join('')
    + '</div>';
}

function marketLink(url) {
  return url ? '<a data-stop href="' + esc(url) + '" target="_blank" rel="noopener" title="Open the market" style="' + LINK + '">market ↗</a>' : '';
}

// The move after the flag: "+30 m 36¢ (+2.0)"; "not yet" when the horizon
// has not passed, "n/a" when no history could be read.
function afterCell(after, key, label) {
  const p = after && after[key];
  if (!after) return '<div><div style="' + HEAD_CELL + '">' + label + '</div><div style="' + M + '; font-size:12px; color:rgba(var(--ink),.6); margin-top:2px">n/a</div></div>';
  if (!p) return '<div><div style="' + HEAD_CELL + '">' + label + '</div><div style="' + M + '; font-size:12px; color:rgba(var(--ink),.6); margin-top:2px">not yet</div></div>';
  const move = p.move_c == null ? '' : ' <span style="color:' + (p.move_c > 0 ? 'var(--accent)' : p.move_c < 0 ? 'var(--neg-soft)' : 'rgba(var(--ink),.5)') + '">' + (p.move_c > 0 ? '+' : '') + esc(String(p.move_c)) + '</span>';
  return '<div><div style="' + HEAD_CELL + '">' + label + '</div><div style="' + M + '; font-size:12px; margin-top:2px">' + cents(p.price) + move + '</div></div>';
}

// The flag log tab: rows newest first, with the price after the flag when
// the API could read it. Fetched only when the tab is opened.
export function renderRiskLog(T) {
  const live = T.liveData.riskLog;
  const intro = '<div style="padding:14px 24px 0; font-size:13px; color:rgba(var(--ink),.6); max-width:820px; line-height:1.5">'
    + 'Every event the screen flags is logged with the side, price and wallets at that moment, so it can be checked afterwards against what happened next.'
    + (live && live.min_score != null ? ' Rows with a score of ' + esc(String(live.min_score)) + ' and up are kept; the same market and side is one row per day (updated while it keeps flagging).' : '')
    + (live && live.sampler_interval_min ? ' A background sampler re-runs the screen every ' + esc(String(live.sampler_interval_min)) + ' min.' : '')
    + '</div>';
  if (!live) {
    return intro + '<div style="display:flex; align-items:center; gap:10px; padding:16px 24px">'
      + '<span style="width:7px; height:7px; border-radius:50%; background:var(--warn); display:inline-block"></span>'
      + '<span style="' + M + '; font-size:11px; letter-spacing:.08em; color:var(--warn)">loading /api/risk/log</span>'
      + '<span style="' + M + '; font-size:10.5px; color:rgba(var(--ink),.6)">reads the log and, for the newest Polymarket flags, the price afterwards</span></div>';
  }
  if (live._quelle === 'fehler') {
    return intro + '<div style="display:flex; align-items:center; gap:12px; padding:16px 24px">'
      + '<span style="' + M + '; font-size:11px; color:var(--neg-soft)">' + esc(herkunftSatz({ quelle: 'fehler', fehler: live._fehler }, '/api/risk/log')) + '</span>'
      + (T.neuLaden ? '<div ' + T.act(() => T.neuLaden('riskLog', 'risk')) + ' class="hv-bd32" style="' + M + '; font-size:11px; color:rgba(var(--ink),.7); border:1px solid rgba(var(--ink),.16); border-radius:4px; padding:5px 10px; cursor:pointer; white-space:nowrap">Try again</div>' : '')
      + '</div>';
  }
  const rows = Array.isArray(live.rows) ? live.rows : [];
  if (!rows.length) {
    return intro + leerZeile('The flag log is empty so far — it fills as the screen flags events (score '
      + (live.min_score != null ? String(live.min_score) : '40') + ' and up); nothing has been flagged since logging started on this host.');
  }
  const kopf = '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.6); padding:12px 24px 0">' + rows.length + ' flag' + (rows.length === 1 ? '' : 's')
    + (live.enriched != null ? ' · price after the flag read for ' + live.enriched + ' of the newest ' + Math.min(rows.length, live.enrich_max || 30) + ' Polymarket flags' : '')
    + (live.as_of ? ' · as of ' + esc(String(live.as_of)) : '') + '</div>';
  return intro + kopf + '<div style="padding:12px 24px 18px; display:grid; gap:12px">'
    + rows.map((f) => {
      const sevColor = f.sev === 'high' ? 'var(--warn)' : f.sev === 'medium' ? 'rgba(var(--ink),.72)' : 'rgba(var(--ink),.5)';
      const scoreStyle = M + '; font-size:16px; color:' + sevColor;
      const preis = { price_last: f.price_at_flag, price_outcome: f.price_outcome, price_min: f.price_min, price_max: f.price_max };
      const seite = { side: f.side, side_notional: f.side_notional, side_share: f.side_share, notional_usd: f.notional };
      const hatAfter = Object.prototype.hasOwnProperty.call(f, 'after');
      return '<div style="background:var(--panel); border:1px solid rgba(var(--ink),.09); border-radius:6px; padding:14px 18px">'
        + '<div style="display:flex; align-items:flex-start; justify-content:space-between; gap:12px">'
        + '<div style="min-width:0">'
        + '<div style="' + M + '; font-size:11px; letter-spacing:.12em; color:rgba(var(--ink),.6)">' + esc(utcShort(f.last_seen)) + ' UTC · ' + esc(String(f.venue || '')) + (f.category ? ' · ' + esc(f.category) : '') + (f.times_seen > 1 ? ' · seen ' + f.times_seen + '× since ' + esc(utcShort(f.first_seen)) : '') + '</div>'
        + '<div style="font-size:14.5px; margin-top:5px; line-height:1.35">' + esc(f.title || f.market_key || '—') + (f.url ? ' ' + marketLink(f.url) : '') + '</div>'
        + '</div>'
        + '<div style="display:flex; align-items:baseline; gap:5px; flex:none"><div style="' + scoreStyle + '">' + (f.score != null ? Math.round(f.score) : '—') + '</div><div style="' + M + '; font-size:11px; color:rgba(var(--ink),.55)">/100</div></div>'
        + '</div>'
        + '<div style="display:flex; gap:8px; flex-wrap:wrap; margin-top:9px; align-items:center">' + riskSideChip(seite)
        + '<span style="' + CHIP + '">at flag ' + esc(riskPriceLabel(preis)) + '</span>'
        + '<span style="' + CHIP + '">' + esc(windowLabel(f.window_start, f.window_end, f.window_minutes)) + '</span>'
        + '<span style="' + CHIP + '">' + (f.unique_wallets || 0) + ' wallet' + (f.unique_wallets === 1 ? '' : 's') + (f.prints ? ' · ' + f.prints + ' prints' : '') + '</span></div>'
        + (hatAfter ? '<div style="display:flex; gap:22px; margin-top:10px">' + afterCell(f.after, '30m', '+30 MIN') + afterCell(f.after, '2h', '+2 H') + afterCell(f.after, '24h', '+24 H')
          + '<div><div style="' + HEAD_CELL + '">MEASURED ON</div><div style="' + M + '; font-size:12px; color:rgba(var(--ink),.55); margin-top:2px">' + (f.after ? esc(f.price_outcome || 'flagged') + ' side, from last print' : (String(f.venue).toLowerCase() === 'kalshi' ? 'Kalshi: no history read' : 'no history / not in the enriched set')) + '</div></div></div>' : '')
        + '<div style="display:flex; gap:5px; flex-wrap:wrap; margin-top:9px">' + riskWalletsHtml(f.top_wallets, f.unique_wallets) + '</div>'
        + riskBookHtml(T, { top_wallets: f.top_wallets, venue: f.venue, market_key: f.market_key, side: f.side })
        + '<div style="display:flex; gap:5px; flex-wrap:wrap; margin-top:7px">' + riskComponentsHtml(f.components) + '</div>'
        + '</div>';
    }).join('')
    + '</div>';
}

// One event card. Closed: what the screen saw — kind and score with its
// band, the market, the flow (side, price at flag, window), the top wallets,
// one line for their book, the four figures. "Why this score" opens the
// score taken apart (riskScoreBreakdown: bars, facts, arithmetic) and the
// per-wallet book lines. The open state lives in T.state.riskOpen[key] so a
// re-render keeps it.
const BAND = (score) => score >= 70 ? ['HIGH', 'var(--warn)'] : score >= 55 ? ['MEDIUM', 'var(--warn)'] : score >= 40 ? ['ELEVATED', 'rgba(var(--ink),.7)'] : ['LOW', 'rgba(var(--ink),.6)'];

export function riskEventCard(T, r0) {
  const r = T.riskCardView(r0);
  const s = T.state || {};
  const key = String(r0.market_key || r0.market || '');
  const offen = !!(s.riskOpen && s.riskOpen[key]);
  // The richer fields (side, prices, window, wallets, components, link)
  // are read from the raw row: an older payload without them renders
  // the card as before, with nothing invented in the gaps.
  const hatFlow = r0.side != null || r0.price_last != null || r0.first_print;
  // The card opens the market drawer only when the market is in the
  // loaded sample; otherwise it is a plain card (its links still work).
  const klickbar = r.act && r.clickable !== false;
  const comps = Array.isArray(r0.components) ? r0.components : [];
  const hatDetails = !!(comps.length || riskBookEntry(T, r0));
  const score = Number(r.score) || 0;
  const band = BAND(score);
  const toggle = hatDetails
    ? '<div data-stop ' + T.act(() => T.setState({ riskOpen: Object.assign({}, s.riskOpen || {}, { [key]: !offen }) })) + ' class="hv-bd32" style="' + M + '; font-size:10.5px; letter-spacing:.06em; color:' + (offen ? 'var(--text)' : 'rgba(var(--ink),.6)') + '; border:1px solid rgba(var(--ink),' + (offen ? '.3' : '.14') + '); border-radius:4px; padding:4px 9px; cursor:pointer; white-space:nowrap; user-select:none">' + (offen ? 'Why ' + score + '? ▴' : 'Why ' + score + '? ▾') + '</div>'
    : '';
  const flags = Array.isArray(r0.flags) && r0.flags.length ? r0.flags : (r.detail && !/^No individual flags/.test(r.detail) ? String(r.detail).split(' · ') : []);
  const details = offen && hatDetails
    ? '<div data-stop style="margin-top:12px; border-top:1px dashed rgba(var(--ink),.1); padding-top:10px; cursor:default">'
      + '<div style="display:flex; align-items:baseline; justify-content:space-between; gap:10px; flex-wrap:wrap">'
      + '<div style="' + M + '; font-size:10.5px; letter-spacing:.12em; color:rgba(var(--ink),.6)">WHY ' + score + ' / 100 · WHAT EACH PART SAW</div>'
      + (flags.length ? '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.6)">flags: ' + flags.map((f) => esc(String(f))).join(' · ') + '</div>' : '')
      + '</div>'
      + (comps.length ? '<div style="margin-top:6px">' + riskScoreBreakdown(comps, score) + '</div>' : '<div style="' + NOTE_R + '; margin-top:6px">' + esc(r.detail || 'No component breakdown in this answer.') + '</div>')
      + riskBookHtml(T, r0)
      + '</div>'
    : '';
  // Preis- und Fenster-Grafik teilen sich eine Zeile; fehlt eine Seite
  // (Kalshi ohne Preise, aeltere Antwort ohne Fenster), bleibt die andere.
  const preisSpalte = hatFlow ? riskPriceStrip(r0) : '';
  const fensterSpalte = hatFlow ? riskWindowStrip(r0) : '';
  const streifen = (preisSpalte || fensterSpalte)
    ? '<div style="display:flex; gap:14px; margin-top:10px">' + preisSpalte + fensterSpalte + '</div>'
    : '';
  return '<div ' + (klickbar ? r.act + ' class="hv-bd20" ' : '') + 'data-bg style="background:var(--panel); border:1px solid ' + (r0.sev === 'high' ? 'rgba(var(--warn-rgb),.3)' : 'rgba(var(--ink),.09)') + '; border-radius:6px; padding:16px 18px; ' + (klickbar ? 'cursor:pointer; ' : '') + '">'
    + '<div style="display:flex; align-items:flex-start; justify-content:space-between; gap:12px">'
    + '<div style="' + r.kindStyle + '; padding-top:4px">' + esc(r.kind) + '</div>'
    + '<div style="text-align:right; flex:none"><div style="display:flex; align-items:baseline; gap:6px; justify-content:flex-end"><div style="' + r.scoreStyle + '">' + r.score + '</div>'
    + '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.55)">/100</div></div>'
    + '<div style="' + M + '; font-size:10.5px; letter-spacing:.12em; color:' + band[1] + '">' + band[0] + '</div></div></div>'
    + '<div style="font-size:15px; margin-top:6px; line-height:1.35">' + esc(r.market) + (r0.url ? ' ' + marketLink(r0.url) : '') + '</div>'
    + '<div style="' + M + '; font-size:11px; letter-spacing:.1em; color:rgba(var(--ink),.6); margin-top:4px"' + (r0.context_note ? ' title="' + esc(r0.context_note) + '"' : '') + '>' + (r0.category ? esc(String(r0.category).toUpperCase()) + ' · ' : '') + esc(String(r.venue || '').toUpperCase()) + '</div>'
    + riskCompositionBar(comps, score)
    + (hatFlow
      ? riskFlowRow(r0)
        + streifen
        + '<div style="display:flex; gap:5px; flex-wrap:wrap; margin-top:8px">' + riskWalletsHtml(r0.top_wallets, r0.wallets) + '</div>'
        + riskBookSummary(T, r0)
      : '<div style="font-size:13px; color:rgba(var(--ink),.6); margin-top:7px; line-height:1.45">' + esc(r.detail) + '</div>')
    + '<div style="height:1px; background:rgba(var(--ink),.07); margin:14px 0 12px"></div>'
    + '<div style="display:flex; gap:22px; align-items:flex-end; justify-content:space-between; flex-wrap:wrap"><div style="display:flex; gap:22px">'
    + [['WALLETS', r.wallets], ['NOTIONAL', r.notional], ['WINDOW', r.window]].map((p) =>
      '<div><div style="' + M + '; font-size:10.5px; letter-spacing:.12em; color:rgba(var(--ink),.6)">' + p[0] + '</div><div style="' + M + '; font-size:14px; margin-top:3px">' + esc(String(p[1])) + '</div></div>'
    ).join('')
    + '</div>' + toggle + '</div>'
    + details
    + '</div>';
}

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
  // Wallets, 4 und 3 Cluster — fuenf Messwerte ohne Messung. Statt fuenf
  // gleichfoermiger Kacheln ist die Event-Seite jetzt ein Trichter: was
  // angeschaut wurde, was die Flag-Schwelle nahm, was heiss ist — die
  // Balken machen die Groessenordnung sichtbar. Ohne Antwort: "—", leere
  // Balken.
  const kp = live && live.kpis ? live.kpis : null;
  const minScore = live && live.event_min_score != null ? Math.round(Number(live.event_min_score)) : 40;
  const screened = kp && kp.events_screened != null ? Number(kp.events_screened) : null;
  const flagged = kp && kp.events_flagged != null ? Number(kp.events_flagged) : null;
  const hochEvents = kp && kp.high_risk_events != null ? Number(kp.high_risk_events) : null;
  const trichterBreite = (wert) => (screened > 0 && wert != null ? Math.max(wert > 0 ? 1.5 : 0, Math.min(100, (wert / screened) * 100)) : 0);
  const trichterZeile = (label, wert, farbe, balkenFarbe, satz) =>
    '<div style="display:flex; align-items:center; gap:12px">'
    + '<div style="flex:0 0 158px; ' + M + '; font-size:11px; letter-spacing:.08em; color:' + farbe + '">' + label + ' <span style="font-size:13px; color:' + (farbe === 'var(--warn)' ? 'var(--warn)' : 'var(--text)') + '">' + (wert != null ? wert : '—') + '</span></div>'
    + '<div style="flex:1; height:12px; border-radius:4px; background:rgba(var(--ink),.07); overflow:hidden"><div style="width:' + trichterBreite(wert).toFixed(1) + '%; height:12px; background:' + balkenFarbe + '"></div></div>'
    + '<div style="flex:0 0 210px; font-size:11px; color:rgba(var(--ink),.5)">' + satz + '</div>'
    + '</div>';
  const seitenKpi = (label, wert, amber) =>
    '<div style="flex:1; background:var(--panel); border:1px solid rgba(var(--ink),.09); border-radius:6px; padding:12px 16px; display:flex; align-items:center; justify-content:space-between; gap:10px">'
    + '<div style="' + M + '; font-size:10.5px; letter-spacing:.12em; color:rgba(var(--ink),.6)">' + label + '</div>'
    + '<div style="' + M + '; font-size:18px; color:' + (amber ? 'var(--warn)' : 'var(--text)') + '">' + (wert != null ? wert : '—') + '</div></div>';
  const trichter =
    '<div style="display:flex; gap:14px; padding:14px 24px; border-bottom:1px solid rgba(var(--ink),.09)">'
    + '<div style="flex:1; background:var(--panel); border:1px solid rgba(var(--ink),.09); border-radius:6px; padding:14px 18px; display:flex; flex-direction:column; gap:9px">'
    + '<div style="display:flex; justify-content:space-between; align-items:baseline; gap:10px">'
    + '<div style="' + M + '; font-size:10.5px; letter-spacing:.12em; color:rgba(var(--ink),.6)">THE SCREEN, AS A FUNNEL</div>'
    + '<div style="' + M + '; font-size:10.5px; color:rgba(var(--ink),.45)">floor at ' + minScore + '/100</div></div>'
    + trichterZeile('SCREENED', screened, 'rgba(var(--ink),.72)', 'rgba(var(--ink),.18)', 'every market with whale flow in the window')
    + trichterZeile('FLAGGED ≥ ' + minScore, flagged, 'rgba(var(--ink),.72)', 'rgba(var(--ink),.5)', 'cleared the flag threshold — these get cards')
    + trichterZeile('HIGH ≥ 70', hochEvents, 'var(--warn)', 'var(--warn)', 'strongest insider-like pattern')
    + '</div>'
    + '<div style="flex:0 0 280px; display:flex; flex-direction:column; gap:10px">'
    + seitenKpi('HIGH-RISK WALLETS', kp ? kp.high_risk_wallets : null, true)
    + seitenKpi('FRESH-WALLET CLUSTERS', kp ? kp.fresh_clusters : null, false)
    + seitenKpi('COORDINATED CLUSTERS', kp ? kp.coordinated_clusters : null, false)
    + '</div></div>';
  const walletRows = live && live.wallets ? live.wallets : [];

  let body = '';
  if (s.riskView === 'events') {
    // The color code of the composition bars, taught once page-level; the
    // per-part recipe lives in each card's "Why?" breakdown. The funnel
    // above already says that cards start at the flag threshold.
    const unterZahl = live ? Number(live.events_below_min) || 0 : 0;
    const swatch = (farbe, wort) => '<div style="display:flex; align-items:center; gap:7px"><div style="width:14px; height:8px; border-radius:2px; background:' + farbe + '"></div><div style="font-size:11.5px; color:rgba(var(--ink),.72)">' + wort + '</div></div>';
    const legende = '<div style="display:flex; align-items:center; justify-content:space-between; gap:16px; padding:14px 24px 0; flex-wrap:wrap">'
      + '<div style="display:flex; align-items:center; gap:16px; flex-wrap:wrap">'
      + '<span style="' + M + '; font-size:10.5px; letter-spacing:.12em; color:rgba(var(--ink),.6)">SCORE COMPOSITION</span>'
      + swatch('rgba(var(--ink),.42)', 'size of the money')
      + swatch('var(--warn)', 'price &amp; timing')
      + swatch('var(--accent)', 'wallet pattern')
      + '</div>'
      + '<div style="font-size:11.5px; color:rgba(var(--ink),.5)">ticks at 40 · 55 · 70 — low → elevated → medium → high · open <span style="' + M + '; font-size:11px">Why?</span> on a card for the full arithmetic</div>'
      + '</div>';
    // The honest empty state: with the threshold in place, "no cards" most
    // often means "everything screened was unremarkable", and the page says
    // exactly that with the numbers, instead of a bare loading sentence.
    const leerSatz = T.risks.length
      ? 'No event at this severity.'
      : (unterZahl > 0
        ? 'All ' + (live && live.kpis ? live.kpis.events_screened : unterZahl) + ' screened markets scored below the flag threshold (' + minScore + ') — nothing suspicious in this window.'
        : risikoSatz);
    const unterNote = riskFiltered.length && unterZahl > 0
      ? '<div style="padding:0 24px 18px; ' + M + '; font-size:11px; color:rgba(var(--ink),.55)">' + unterZahl + ' more market' + (unterZahl === 1 ? '' : 's') + ' screened below ' + minScore + '/100 — watch only, no card.</div>'
      : '';
    body = '<div>'
      + legende
      + '<div style="display:flex; gap:6px; padding:14px 24px 0; flex-wrap:wrap">'
      + [T.tab('All', s.riskFilter === 'all', { riskFilter: 'all' }),
         T.tab('High', s.riskFilter === 'high', { riskFilter: 'high' }),
         T.tab('Watch', s.riskFilter === 'medium', { riskFilter: 'medium' })].join('')
      + '</div>'
      + (riskFiltered.length ? '' : leerZeile(leerSatz))
      + '<div style="padding:18px 24px; display:grid; grid-template-columns:repeat(2,1fr); gap:14px">'
      + riskFiltered.map((r0) => riskEventCard(T, r0)).join('')
      + '</div>'
      + unterNote
      + '</div>';
  } else if (s.riskView === 'log') {
    body = renderRiskLog(T);
  } else if (s.riskView === 'wallets') {
    // Die Antwort auf "wer hat das platziert?": derselbe Tape wie Events,
    // nach Wallet gruppiert. Der Score allein war nichtssagend — jetzt sagt
    // die Zeile, welche Muster gefeuert haben (die Flags des Scorers), und
    // die tote CLUSTER-Spalte (immer "—") ist weg.
    const GRID_W = 'minmax(230px,1.4fr) 80px 64px 96px 96px 96px';
    const antwortDa = !!live && live._quelle !== 'fehler';
    body = '<div>'
      + '<div style="padding:14px 24px 0; font-size:12.5px; color:rgba(var(--ink),.62); line-height:1.55; max-width:860px">'
      + 'The flagged flow grouped by the wallet that placed it — the <span style="font-style:italic">who</span> behind the Events tab. '
      + 'Same 0–100 score and bands as Events: how much this wallet\'s prints look like early knowledge (size, long odds, timing, account freshness). '
      + 'The chips under each wallet say which patterns fired; <span style="' + M + '; font-size:11.5px">watch only</span> means none did — the wallet is listed for size alone.'
      + '</div>'
      + '<div style="border:1px solid rgba(var(--ink),.09); border-radius:6px; margin:14px 24px; overflow:hidden">'
      + '<div style="display:grid; grid-template-columns:' + GRID_W + '; gap:10px; padding:9px 16px; background:var(--panel); border-bottom:1px solid rgba(var(--ink),.09); ' + M + '; font-size:10.5px; letter-spacing:.12em; color:rgba(var(--ink),.6)">'
      + '<div>WALLET · WHY FLAGGED</div><div style="text-align:right">SCORE</div><div style="text-align:right">PRINTS</div><div style="text-align:right">NOTIONAL</div><div style="text-align:right">BIGGEST</div><div style="text-align:right">FIRST SEEN</div></div>'
      + (walletRows.length ? '' : leerZeile(antwortDa ? 'No wallet cleared the screen in this window — nothing in the flagged flow groups to a suspicious wallet.' : risikoSatz))
      + walletRows.map((w) => {
        const band = BAND(Number(w.score) || 0);
        const scoreStyle = M + '; font-size:12px; border-radius:4px; padding:3px 9px; ' + (w.score >= 70 ? 'color:var(--on-accent); background:var(--warn)' : w.score >= 55 ? 'color:var(--warn); border:1px solid rgba(var(--warn-rgb),.35)' : 'color:rgba(var(--ink),.7); border:1px solid rgba(var(--ink),.18)');
        const flags = Array.isArray(w.flags) ? w.flags : [];
        const flagChips = flags.map((f) => {
          const echt = f !== 'watch only';
          return '<span style="' + M + '; font-size:10.5px; white-space:nowrap; border-radius:4px; padding:1px 6px; '
            + (echt ? 'color:var(--warn); border:1px solid rgba(var(--warn-rgb),.3)' : 'color:rgba(var(--ink),.6); border:1px solid rgba(var(--ink),.12)') + '">' + esc(f) + '</span>';
        }).join('');
        return '<div ' + T.act(() => T.openWallet(w.wallet, w.address)) + ' class="hv-panel" style="display:grid; grid-template-columns:' + GRID_W + '; gap:10px; align-items:center; padding:12px 16px; border-bottom:1px solid rgba(var(--ink),.06); ' + M + '; font-size:12.5px; cursor:pointer">'
          + '<div style="min-width:0"><div style="font-family:\'IBM Plex Sans\',sans-serif; font-size:13px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="' + esc(w.address || w.wallet) + '">' + esc(w.wallet) + '</div>'
          + '<div style="font-size:11px; color:rgba(var(--ink),.62); margin-top:2px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="' + esc(w.context) + '">mostly in ' + esc(w.context) + '</div>'
          + (flagChips ? '<div style="display:flex; gap:4px; flex-wrap:wrap; margin-top:5px">' + flagChips + '</div>' : '')
          + '</div>'
          + '<div style="text-align:right"><div style="display:inline-block; ' + scoreStyle + '">' + w.score + '</div>'
          + '<div style="' + M + '; font-size:10px; letter-spacing:.1em; color:' + band[1] + '; margin-top:3px">' + band[0] + '</div></div>'
          + '<div style="text-align:right; color:rgba(var(--ink),.6)">' + w.prints + '</div>'
          + '<div style="text-align:right">' + esc(String(w.notional)) + '</div>'
          + '<div style="text-align:right; color:rgba(var(--ink),.6)">' + esc(String(w.largest || '—')) + '</div>'
          + '<div style="text-align:right; color:rgba(var(--ink),.6)">' + esc(w.firstSeen) + '</div></div>';
      }).join('')
      + '</div></div>';
  } else if (s.riskView === 'fresh') {
    // Eine Karte je Markt: WIE VIELE frische Wallets, WELCHE Seite, WIE VIEL
    // Geld — als drei benannte Zahlen statt einer amber Zahl, die wie ein
    // Score aussah und in Wahrheit der Zaehler war.
    const freshRows = live && live.fresh ? live.fresh : [];
    const antwortDa = !!live && live._quelle !== 'fehler';
    const seiteFarbe = (seite) => seite === 'YES' ? 'var(--accent)' : seite === 'NO' ? 'var(--neg-soft)' : 'rgba(var(--ink),.7)';
    body = '<div>'
      + '<div style="padding:14px 24px 0; font-size:12.5px; color:rgba(var(--ink),.62); line-height:1.55; max-width:860px">'
      + '<span style="' + M + '; font-size:11.5px">Fresh</span> = a wallet with at most two prior trades in this tape window. '
      + 'Several of them betting whale size on the same side of one market is the classic pattern of accounts created for a single bet.'
      + '</div>'
      + (freshRows.length ? '' : leerZeile(antwortDa
        ? 'No fresh-wallet cluster in this window — no market where several brand-new wallets took the same side at size. Most windows look like this; a hit shows up here and raises the market\'s event score.'
        : risikoSatz))
      + '<div style="padding:16px 24px 4px; display:grid; grid-template-columns:repeat(auto-fill,minmax(340px,1fr)); gap:14px">'
      + freshRows.map((c) => {
        const punkte = '●'.repeat(Math.min(Number(c.count) || 0, 8)) + (Number(c.count) > 8 ? '…' : '');
        return '<div style="background:var(--panel); border:1px solid rgba(var(--ink),.09); border-radius:6px; padding:16px 18px">'
          + '<div style="font-size:14.5px; line-height:1.35">' + esc(c.market) + (c.venue ? ' <span style="' + M + '; font-size:10.5px; color:rgba(var(--ink),.6)">' + esc(String(c.venue).toUpperCase()) + '</span>' : '') + '</div>'
          + '<div style="display:flex; gap:22px; margin-top:12px; align-items:flex-end; flex-wrap:wrap">'
          + '<div><div style="' + M + '; font-size:10.5px; letter-spacing:.12em; color:rgba(var(--ink),.6)">FRESH WALLETS</div>'
          + '<div style="display:flex; align-items:baseline; gap:8px; margin-top:3px"><span style="' + M + '; font-size:20px; color:var(--warn)">' + (c.count != null ? c.count : '—') + '</span>'
          + '<span style="' + M + '; font-size:11px; color:var(--warn); letter-spacing:2px">' + punkte + '</span></div></div>'
          + '<div><div style="' + M + '; font-size:10.5px; letter-spacing:.12em; color:rgba(var(--ink),.6)">ALL ON</div>'
          + '<div style="' + M + '; font-size:16px; margin-top:3px; color:' + seiteFarbe(c.side) + '">' + esc(c.side || 'same side') + '</div></div>'
          + '<div><div style="' + M + '; font-size:10.5px; letter-spacing:.12em; color:rgba(var(--ink),.6)">COMBINED</div>'
          + '<div style="' + M + '; font-size:16px; margin-top:3px">' + esc(String(c.notional || '—')) + '</div></div>'
          + '</div>'
          + '<div style="font-size:11.5px; color:rgba(var(--ink),.62); margin-top:10px; line-height:1.45">' + esc(c.detail) + '</div>'
          + '</div>';
      }).join('')
      + '</div></div>';
  } else if (s.riskView === 'timing') {
    // Je Markt ein Burst-Balken: wie eng die Wallets beieinander lagen. Der
    // Massstab ist das 30-Minuten-Suchfenster des Screens — ein Balken ueber
    // die volle Breite heisst "ueber die vollen 30 Minuten verteilt", ein
    // schmaler Streifen "innerhalb von Sekunden".
    const timingRows = live && live.timing ? live.timing : [];
    const antwortDa = !!live && live._quelle !== 'fehler';
    const GRID_T = 'minmax(200px,1.2fr) 90px minmax(150px,1fr) 110px 110px';
    body = '<div>'
      + '<div style="padding:14px 24px 0; font-size:12.5px; color:rgba(var(--ink),.62); line-height:1.55; max-width:860px">'
      + 'Markets where three or more wallets hit the same side within a 30-minute window — money arriving together. '
      + 'The bar shows how tight the burst was: the full track is 30 minutes, the filled part is the actual span.'
      + '</div>'
      + '<div style="border:1px solid rgba(var(--ink),.09); border-radius:6px; margin:14px 24px; overflow:hidden">'
      + '<div style="display:grid; grid-template-columns:' + GRID_T + '; gap:10px; padding:9px 16px; background:var(--panel); border-bottom:1px solid rgba(var(--ink),.09); ' + M + '; font-size:10.5px; letter-spacing:.12em; color:rgba(var(--ink),.6)">'
      + '<div>MARKET</div><div style="text-align:right">WALLETS</div><div>BURST · OF 30 MIN</div><div style="text-align:right">SIDE</div><div style="text-align:right">NOTIONAL</div></div>'
      + (timingRows.length ? '' : leerZeile(antwortDa
        ? 'No coordinated burst in this window — no market where three or more wallets hit the same side within 30 minutes of each other.'
        : risikoSatz))
      + timingRows.map((c) => {
        const span = Number(c.span_minutes);
        const anteil = isNaN(span) ? 0 : Math.max(0.02, Math.min(1, span / 30));
        const balken = '<div style="display:flex; align-items:center; gap:8px">'
          + '<div style="flex:1; height:7px; border-radius:4px; background:rgba(var(--ink),.08); overflow:hidden">'
          + '<div style="width:' + (anteil * 100).toFixed(1) + '%; height:7px; background:' + (c.same ? 'var(--warn)' : 'rgba(var(--ink),.45)') + '"></div></div>'
          + '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.7); white-space:nowrap">' + esc(c.window) + '</div></div>';
        return '<div style="display:grid; grid-template-columns:' + GRID_T + '; gap:10px; align-items:center; padding:12px 16px; border-bottom:1px solid rgba(var(--ink),.06); ' + M + '; font-size:12.5px">'
          + '<div style="font-family:\'IBM Plex Sans\',sans-serif; font-size:13px; min-width:0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="' + esc(c.market) + '">' + esc(c.market) + '</div>'
          + '<div style="text-align:right">' + c.wallets + '</div>'
          + balken
          + '<div style="text-align:right; ' + M + '; font-size:11.5px; color:' + (c.same ? 'var(--warn)' : 'rgba(var(--ink),.6)') + '">' + (c.same ? 'all on ' + esc(c.side || 'one side') : 'mixed') + '</div>'
          + '<div style="text-align:right">' + esc(c.notional) + '</div></div>';
      }).join('')
      + '</div></div>';
  } else {
    // Keine Demo-Cluster, solange echte fehlen: erfundene Wallet-Gruppen auf
    // einem Screen, der Verdacht behauptet, sind schlimmer als eine leere
    // Flaeche. Die Grafik darueber sagt bereits, woran es liegt.
    // Je Cluster eine Karte in der Farbe des Graphen: WER drin ist (die
    // Wallets, klickbar), WIE eng (das Muster mit Dichte) und WO sie sich
    // trafen (die geteilten Maerkte mit Summen) — der Beleg, den vorher die
    // unlesbare Wallet-Markt-Matrix tragen sollte.
    const networkRows = live ? (live.network || []) : [];
    const musterFarbe = (p) => p === 'Tight clique' ? 'var(--warn)' : p === 'Connected group' ? 'rgba(var(--ink),.8)' : 'rgba(var(--ink),.55)';
    body = '<div style="padding:16px 24px">'
      + renderClusterGraphics(live)
      + '<div style="display:grid; grid-template-columns:repeat(auto-fill,minmax(360px,1fr)); gap:14px">'
      + networkRows.map((n) => {
        const farbe = clusterFarbe(live && live.graph, n.id);
        const mitglieder = Array.isArray(n.members) ? n.members : [];
        const rest = (n.members_total || mitglieder.length) - mitglieder.length;
        const maerkte = Array.isArray(n.markets) ? n.markets : [];
        return '<div style="background:var(--panel); border:1px solid rgba(var(--ink),.09); border-left:3px solid ' + farbe + '; border-radius:6px; padding:16px 18px">'
          + '<div style="display:flex; align-items:center; justify-content:space-between; gap:10px; flex-wrap:wrap">'
          + '<div style="display:flex; align-items:center; gap:8px"><span style="width:9px; height:9px; border-radius:2px; flex:none; background:' + farbe + '"></span>'
          + '<span style="font-size:14.5px; font-weight:600">' + esc(n.name) + '</span>'
          + '<span style="' + M + '; font-size:11px; color:rgba(var(--ink),.6)">' + n.size + ' wallets</span></div>'
          + (n.pattern ? '<span style="' + M + '; font-size:10.5px; letter-spacing:.1em; color:' + musterFarbe(n.pattern) + '; border:1px solid rgba(var(--ink),.14); border-radius:4px; padding:2px 7px">' + esc(String(n.pattern).toUpperCase()) + '</span>' : '')
          + '</div>'
          + '<div style="font-size:12.5px; color:rgba(var(--ink),.62); margin-top:8px; line-height:1.45">' + esc(n.story) + '</div>'
          + (mitglieder.length
            ? '<div style="' + M + '; font-size:10.5px; letter-spacing:.12em; color:rgba(var(--ink),.6); margin-top:11px">WHO</div>'
              + '<div style="display:flex; gap:5px; flex-wrap:wrap; margin-top:5px">'
              + mitglieder.map((mm) => '<span ' + T.act(() => T.openWallet(mm.kurz, mm.wallet)) + ' class="hv-bd32" style="' + M + '; font-size:11px; color:rgba(var(--ink),.8); border:1px solid rgba(var(--ink),.16); border-radius:4px; padding:3px 8px; cursor:pointer" title="open this wallet">' + esc(mm.kurz) + '</span>').join('')
              + (rest > 0 ? '<span style="' + M + '; font-size:11px; color:rgba(var(--ink),.55); padding:3px 2px">+ ' + rest + ' more</span>' : '')
              + '</div>'
            : '')
          + (maerkte.length
            ? '<div style="' + M + '; font-size:10.5px; letter-spacing:.12em; color:rgba(var(--ink),.6); margin-top:11px">WHERE THEY MET</div>'
              + '<div style="margin-top:5px; display:grid; gap:4px">'
              + maerkte.map((mk) => '<div style="display:flex; gap:10px; align-items:baseline; font-size:12px">'
                + '<span style="color:rgba(var(--ink),.75); min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; flex:1" title="' + esc(mk.title) + '">' + esc(mk.title) + '</span>'
                + '<span style="' + M + '; font-size:11.5px; white-space:nowrap">' + esc(mk.label || '') + '</span></div>').join('')
              + '</div>'
            : '')
          + '<div style="display:flex; gap:20px; margin-top:12px">'
          + '<div><div style="' + M + '; font-size:10.5px; letter-spacing:.12em; color:rgba(var(--ink),.6)">SHARED MARKETS</div><div style="' + M + '; font-size:14px; margin-top:3px">' + esc(n.shared) + '</div></div>'
          + '<div><div style="' + M + '; font-size:10.5px; letter-spacing:.12em; color:rgba(var(--ink),.6)">PAIRED NOTIONAL</div><div style="' + M + '; font-size:14px; margin-top:3px">' + esc(n.notional) + '</div></div>'
          + '</div></div>';
      }).join('')
      + '</div></div>';
  }

  return '<div>'
    + '<div style="padding:20px 24px 14px; border-bottom:1px solid rgba(var(--ink),.09)">'
    // No "Check real account ages" toggle: /api/risk takes no such parameter,
    // so the switch flipped a colour and changed nothing.
    + '<div style="display:flex; align-items:flex-end; justify-content:space-between; gap:20px">'
    + '<div><div style="' + M + '; font-size:11px; letter-spacing:.18em; color:var(--warn)">RISK SCREEN</div>'
    + '<h1 style="font-size:21px; line-height:1.25; margin:6px 0 0; font-weight:600; letter-spacing:-0.01em">Trades that look like someone knew</h1></div>'
    + (live && live.as_of ? '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.55)">as of ' + esc(String(live.as_of)) + '</div>' : '')
    + '</div>'
    + '<div style="font-size:13px; color:rgba(var(--ink),.55); margin-top:10px; max-width:760px">Best-effort screen on public trade data — research leads, not legal findings. Sports odds, crypto &amp; market prices, and weather are excluded: game results, exchange prices and weather models cannot be traded on early.</div>'
    + '<div style="display:flex; gap:7px; margin-top:12px; flex-wrap:wrap">'
    + '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.6); border:1px solid rgba(var(--ink),.12); border-radius:4px; padding:4px 9px">UNDER 40 · LOW</div>'
    + '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.6); border:1px solid rgba(var(--ink),.18); border-radius:4px; padding:4px 9px">40–54 · ELEVATED</div>'
    + '<div style="' + M + '; font-size:11px; color:var(--warn); border:1px solid rgba(var(--warn-rgb),.3); border-radius:4px; padding:4px 9px">55–69 · MEDIUM</div>'
    + '<div style="' + M + '; font-size:11px; color:var(--on-accent); background:var(--warn); border-radius:4px; padding:4px 9px">70 AND UP · HIGH</div>'
    + '</div></div>'

    + trichter

    + (laedt
      ? '<div style="display:flex; align-items:center; gap:10px; padding:12px 24px; border-bottom:1px solid rgba(var(--ink),.09); background:var(--panel)">'
        + '<span style="width:7px; height:7px; border-radius:50%; background:var(--warn); display:inline-block"></span>'
        + '<span style="' + M + '; font-size:11px; letter-spacing:.08em; color:var(--warn)">building the day\'s tape, ~90 s on a cold cache</span>'
        + '<span style="' + M + '; font-size:10.5px; color:rgba(var(--ink),.6)">/api/risk pages a day of prints and looks up market categories; the second visit is instant</span></div>'
      : (T.herkunft.risks && T.herkunft.risks.quelle === 'fehler' && T.neuLaden
        // A failed or rate-limited request can be asked again from here;
        // nothing re-asks on its own. /api/risk shares its rate limit with
        // the backtester, so a 429 usually means "a few backtests just ran".
        ? '<div style="display:flex; align-items:center; gap:12px; padding:12px 24px; border-bottom:1px solid rgba(var(--ink),.09); background:var(--panel)">'
          + '<span style="' + M + '; font-size:11px; color:var(--neg-soft)">' + esc(risikoSatz) + '</span>'
          + '<div ' + T.act(() => T.neuLaden('risk', 'risk')) + ' class="hv-bd32" style="' + M + '; font-size:11px; color:rgba(var(--ink),.7); border:1px solid rgba(var(--ink),.16); border-radius:4px; padding:5px 10px; cursor:pointer; white-space:nowrap">Try again</div></div>'
        : ''))
    + '<div style="display:flex; gap:6px; padding:16px 24px 0; flex-wrap:wrap">'
    + [['events','Events'],['wallets','Wallets'],['fresh','Fresh-wallet clusters'],['timing','Coordinated timing'],['network','Co-trading network']].map((o) => T.tab(o[1], s.riskView === o[0], { riskView: o[0] })).join('')
    // The log is fetched only when its tab is opened (app.js openRiskLog);
    // the harness T has no such method and just switches the view.
    + T.tab('Flag log', s.riskView === 'log', () => (T.openRiskLog ? T.openRiskLog() : T.setState({ riskView: 'log' })))
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
        sparkPoints: '', color: 'rgba(var(--ink),.3)', priceLabel: '—', changeLabel: '—',
        changeStyle: M + '; font-size:13px; text-align:right; color:rgba(var(--ink),.6)',
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
    + '<div style="padding:20px 24px 16px; border-bottom:1px solid rgba(var(--ink),.09)">'
    + '<div style="' + M + '; font-size:11px; letter-spacing:.18em; color:var(--accent)">TRACKED</div>'
    + '<h1 style="font-size:21px; line-height:1.25; margin:6px 0 0; font-weight:600; letter-spacing:-0.01em">Your wallets and your watchlist</h1></div>'
    + '<div style="padding:18px 24px; border-bottom:1px solid rgba(var(--ink),.09)">'
    + '<div style="' + M + '; font-size:10.5px; letter-spacing:.14em; color:rgba(var(--ink),.55); margin-bottom:13px">WALLETS YOU FOLLOW</div>'
    + (cards.length ? '<div style="display:grid; grid-template-columns:repeat(3,1fr); gap:14px">'
    + cards.map((w) => {
      const gradeStyle = M + '; font-size:12px; border-radius:4px; padding:2px 9px; ' + (w.grade === 'A' || w.grade === 'A+' ? 'color:var(--on-accent); background:var(--accent)' : w.grade === '—' ? 'color:rgba(var(--ink),.6); border:1px solid rgba(var(--ink),.14)' : 'color:var(--warn); border:1px solid rgba(var(--warn-rgb),.35)');
      const pnlText = typeof w.pnlRaw === 'number' && T.liveData.track ? (w.pnlRaw >= 0 ? '+' : '-') + money(Math.abs(w.pnlRaw)) : w.pnl;
      const pnlStyle = M + '; font-size:14px; margin-top:3px; color:' + (String(pnlText).charAt(0) === '+' ? 'var(--pos)' : String(pnlText).charAt(0) === '-' ? 'var(--neg)' : 'rgba(var(--ink),.5)');
      return '<div ' + T.act(() => T.openWallet(w.openAs)) + ' class="hv-bd20" style="background:var(--panel); border:1px solid rgba(var(--ink),.09); border-radius:6px; padding:15px 17px; cursor:pointer">'
        + '<div style="display:flex; align-items:center; justify-content:space-between">'
        + '<div style="font-size:15px">' + esc(w.name) + '</div>'
        + '<div style="' + gradeStyle + '">' + esc(w.grade) + '</div></div>'
        + '<div style="' + M + '; font-size:10.5px; color:rgba(var(--ink),.6); margin-top:4px">' + esc(w.wallet) + '</div>'
        + '<div style="display:flex; gap:20px; margin-top:14px">'
        + '<div><div style="' + M + '; font-size:10.5px; letter-spacing:.12em; color:rgba(var(--ink),.6)">' + (w.pnlLabel || '30D PROFIT') + '</div><div style="' + pnlStyle + '">' + esc(String(pnlText)) + '</div></div>'
        + '<div><div style="' + M + '; font-size:10.5px; letter-spacing:.12em; color:rgba(var(--ink),.6)">LAST TRADE</div><div style="' + M + '; font-size:14px; margin-top:3px">' + esc(w.last) + '</div></div>'
        + '</div></div>';
    }).join('')
    + '</div>' : '<div style="' + M + '; font-size:11.5px; color:rgba(var(--ink),.6); padding:14px 0">No followed wallets reported by /api/track — the list lives in data/followed_wallets.json on the machine that runs the API, and this page only reads it.</div>')
    + '</div>'
    + '<div style="padding:18px 24px">'
    + '<div style="' + M + '; font-size:10.5px; letter-spacing:.14em; color:rgba(var(--ink),.55); margin-bottom:13px">MARKETS ON YOUR WATCHLIST</div>'
    + (watch.length ? '' : '<div style="' + M + '; font-size:11.5px; color:rgba(var(--ink),.6); padding:6px 0">'
      + esc(herkunftSatz(T.liveData.track ? { quelle: T.liveData.track._quelle === 'fehler' ? 'fehler' : 'leer', fehler: T.liveData.track._fehler } : null, '/api/track')) + '</div>')
    + watch.map((m) =>
      '<div ' + m.act + ' class="hv-panel" style="display:grid; grid-template-columns:1fr 96px 88px 96px 108px; align-items:center; padding:12px 0; border-bottom:1px solid rgba(var(--ink),.06); cursor:pointer">'
      + '<div><div style="font-size:13.5px">' + esc(m.title) + '</div>'
      + '<div style="' + M + '; font-size:10.5px; color:rgba(var(--ink),.6); margin-top:3px">' + esc(m.meta) + '</div></div>'
      + '<div style="display:flex; justify-content:flex-end"><svg width="78" height="26" viewBox="0 0 78 26" aria-hidden="true" focusable="false"><polyline points="' + m.sparkPoints + '" fill="none" style="stroke:' + m.color + '" stroke-width="1.6" /></svg></div>'
      + '<div style="' + M + '; font-size:15px; text-align:right">' + m.priceLabel + '</div>'
      + '<div style="' + m.changeStyle + '">' + m.changeLabel + '</div>'
      + '<div style="' + M + '; font-size:12px; text-align:right; color:rgba(var(--ink),.55)">' + esc(m.ends) + '</div></div>'
    ).join('')
    + '</div></div>';
}
