// Leaderboard, Whale flow, Risk screen, Tracked — ported from the design reference.

import { esc, money, num, herkunftSatz, leerBlock, leerZeile, seitenKopf, catChipsPresent, tapeFenster, fensterSatz } from '../util.js';
import { caveat, caveatZeile } from '../claims.js';
import { scoreBand, bandChips, basisSatz, gemessenSatz } from '../risk_bands.js';
import { renderClusterGraphics, clusterFarbe } from './cluster_graphics.js';
import { punktwolke, histogramm, kurzGeld } from '../charts.js';
import { MONO as M, LABEL_BLOCK, LABEL, NOTIZ, kpi } from '../ui.js';

function filterGroup(label, chipsHtml) {
  return '<div><div style="' + LABEL_BLOCK + '">' + label + '</div><div style="display:flex; gap:var(--sp-3); flex-wrap:wrap">' + chipsHtml + '</div></div>';
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
  return '<div style="display:flex; gap:var(--sp-2); flex-wrap:wrap; margin-top:var(--sp-2)">'
    + parts.map((p) => {
      const wert = p.imputed
        ? '<span style="color:var(--ink-3); font-style:italic">assumed</span>'
        : '<span style="color:var(--ink-1)">' + esc(p.value) + '</span>';
      const rand = p.imputed ? 'border:1px dashed var(--line-1)' : 'border:1px solid var(--line-2)';
      const titel = p.imputed
        ? ' title="' + esc(p.label + ': the public leaderboard feed carries no input for this component, so the score uses a fixed placeholder — the same one for every wallet') + '"'
        : '';
      return '<span' + titel + ' style="' + M + '; font-size:var(--t-micro); color:var(--ink-3); ' + rand + '; border-radius:var(--r-control); padding:var(--sp-1) var(--sp-3); white-space:nowrap">'
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

// Score gegen die Belege, die ihn tragen. Eine Punktwolke statt einer
// Pille je Zeile, und sie loest zwei Dinge auf einmal.
//
// Erstens die Projektregel: jede Score-Anzeige traegt n, Intervall,
// Sample-Abzeichen und Stichtag. Das Abzeichen in der Tabelle trug keins
// davon. Die waagerechte Spanne je Punkt ist die Ungemessen-Spanne aus
// api_views.score_interval, ausdruecklich kein Konfidenzintervall: der
// Composite ist bei gegebenen Eingaben deterministisch. Sie sagt, wohin der
// Score wandern koennte, wenn die Platzhalter Messungen waeren. Auf der
// oeffentlichen Antwort sind das 55 Prozent des Gewichts, die Spannen
// ueberlappen also quer durch die Rangliste, und genau das ist die Aussage:
// ein Composite ohne Streuung ist keine Rangfolge.
//
// Zweitens die y-Achse. Sie traegt das gehandelte Volumen in Dollar,
// logarithmisch. Aufgeloeste Wetten je Wallet waeren das bessere Mass fuer
// "genug Faelle", aber die oeffentliche Leaderboard-Antwort traegt sie
// nicht (get_polymarket_leaderboard liefert rank, trader, wallet, pnl,
// volume und sonst nichts); sie brauchen einen Abruf je Wallet und stehen
// deshalb auf der Wallet-Seite, mit n und Wilson-Intervall. Statt sie hier
// zu schaetzen steht die Groesse da, die wirklich gemessen ist, und die
// Fussnote sagt beides.
//
// Die gestrichelte Waagerechte ist die Saettigung des Volumen-Bestandteils
// (95. Perzentil der bewerteten Menge, copy_trading._log_score): darueber
// aendert mehr Volumen am Score nichts mehr. Die Senkrechten sind die
// Notengrenzen, damit die Score-Achse ueberhaupt einen Bezugsrahmen hat.
export function scoreWolkeHtml(T, rows) {
  const punkte = (rows || [])
    .filter((t) => t && typeof t.score === 'number' && t.score === t.score && +t.vol > 0)
    .map((t) => ({
      x: t.score,
      y: +t.vol,
      label: t.name,
      band: Array.isArray(t.scoreCi) && t.scoreCi.length === 2 ? t.scoreCi : null,
      tip: t.name + ' · score ' + t.score + (t.grade ? ' (' + t.grade + ')' : '')
        + (Array.isArray(t.scoreCi) && t.scoreCi.length === 2
          ? ' · unmeasured range ' + t.scoreCi[0] + ' to ' + t.scoreCi[1] : '')
        + ' · volume ' + kurzGeld(+t.vol)
    }));
  if (punkte.length < 2) return '';
  const lb = (T.liveData && T.liveData.leaderboard) || {};
  const skala = lb.score_scale || {};
  const badge = (rows.find((t) => t && t.sampleBadge) || {}).sampleBadge || null;
  const stand = lb.as_of ? String(lb.as_of) : null;
  const yRefs = [];
  if (typeof skala.saturates_at === 'number' && skala.saturates_at > 0) {
    yRefs.push({ wert: skala.saturates_at, label: 'volume component maxes out at ' + kurzGeld(skala.saturates_at) });
  }
  // Woraus der Score besteht, sagt der Basis-Satz direkt ueber dem
  // Diagramm (scoreBasisSatz, Zwilling von api_views.score_basis_note):
  // Anteil des gemessenen Gewichts, die geschaetzten Bestandteile, das
  // Kohorten-n. Das steht hier bewusst nicht noch einmal in anderen Worten.
  // Diese Fussnote traegt nur, was das Bild selbst hinzufuegt: das
  // Sample-Abzeichen und den Stichtag als Seitenfakten, und den stehenden
  // Vorbehalt zur Spanne aus dem Register.
  const fussnote = [
    badge && badge.quality ? 'Sample: ' + badge.quality + '.' : '',
    stand ? 'Snapshot ' + stand + '.' : ''
  ].filter(Boolean).join(' ');
  return punktwolke({
    titel: 'SCORE AGAINST THE EVIDENCE UNDER IT',
    hinweis: punkte.length + ' scored wallets plotted',
    xLabel: 'smart score (points out of 100)',
    yLabel: 'volume traded (USD, log)',
    xDomain: [0, 100],
    yLog: true,
    yTickText: (v) => kurzGeld(v),
    xReferenzen: [
      { wert: 40, label: 'watch' }, { wert: 55, label: 'C' },
      { wert: 70, label: 'B' }, { wert: 85, label: 'A' }
    ],
    yReferenzen: yRefs,
    punkte,
    labelN: 5,
    fussnote,
    fussnoteHtml: caveat('composite_range_not_ci')
  });
}

// Das Abzeichen selbst bleibt eine Zahl, aber es sagt beim Zeigen, wie viel
// davon gemessen ist. Die Punktwolke darueber traegt dieselbe Spanne als
// Bild; hier steht sie fuer die einzelne Zeile.
export function scoreTitel(t) {
  if (!t || t.score == null) return '';
  const teile = [];
  if (Array.isArray(t.scoreCi) && t.scoreCi.length === 2) {
    teile.push('unmeasured range ' + t.scoreCi[0] + ' to ' + t.scoreCi[1]
      + ' of 100: where the score could sit if the placeholder components were measured');
  }
  if (t.scoreN) teile.push('n = ' + t.scoreN + ' wallets ranked together');
  if (t.sampleBadge && t.sampleBadge.quality) teile.push('sample: ' + t.sampleBadge.quality);
  return teile.length ? ' title="' + esc(teile.join(' · ')) + '"' : '';
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
  // Absteigend, und eine unbekannte Zahl steht am Ende statt als Null in der
  // Mitte: ein fehlender Gewinn ist kein Rang, den die Zeile verdient hat.
  const absteigend = (x, y) => (x == null && y == null ? 0 : x == null ? 1 : y == null ? -1 : y - x);
  const roi = (t) => (t.pnl == null ? null : t.pnl / (t.vol || 1));
  const traderSorted = tRows.sort((a, b) => {
    if (rank === 'win') return (b.win || 0) - (a.win || 0);
    if (rank === 'score') return (b.score == null ? -1 : b.score) - (a.score == null ? -1 : a.score);
    if (rank === 'vol') return absteigend(a.vol, b.vol);
    if (rank === 'roi') return absteigend(roi(a), roi(b));
    return absteigend(a.pnl, b.pnl);
  });

  const badge = tCount ? M + '; font-size:var(--t-micro); color:var(--on-accent); background:var(--accent); border-radius:var(--r-control); padding:var(--sp-1) var(--sp-3)' : 'display:none';
  const chevron = M + '; font-size:var(--t-lead); color:var(--ink-4); transition:transform .18s ease; transform:rotate(' + (s.traderFiltersOpen ? '90deg' : '0deg') + ')';
  const asOf = T.liveData.leaderboard && T.liveData.leaderboard.as_of ? ' · snapshot ' + T.liveData.leaderboard.as_of : '';
  const basisSatz = scoreBasisSatz(T.traders);
  // Ueber alle gerankten Wallets, nicht ueber die gefilterte Sicht: die
  // Wolke ist der Bezugsrahmen der Score-Spalte, kein Filterergebnis.
  const scoreWolke = scoreWolkeHtml(T, T.traders);
  const grid = '44px 1fr 120px' + (hatWin ? ' 100px' : '') + (hatResolved ? ' 118px' : '') + ' 100px 92px';
  const rankTabs = [T.tab('Smart score', rank === 'score', { traderRank: 'score' }),
    T.tab('Profit', rank === 'pnl', { traderRank: 'pnl' }),
    T.tab('Volume', rank === 'vol', { traderRank: 'vol' }),
    T.tab('Profit / volume', rank === 'roi', { traderRank: 'roi' })]
    .concat(hatWin ? [T.tab('Win rate', rank === 'win', { traderRank: 'win' })] : []).join('');

  return '<div>'
    + '<div style="padding:var(--sp-6) var(--sp-6) var(--sp-5); border-bottom:1px solid var(--line-2)">'
    + '<div style="display:flex; align-items:flex-end; justify-content:space-between; gap:var(--sp-6)">'
    + '<div><div style="' + M + '; font-size:var(--t-micro); letter-spacing:.18em; color:var(--accent)">LEADERBOARD</div>'
    + '<h1 style="font-size:var(--t-head); line-height:1.25; margin:var(--sp-3) 0 0; font-weight:600; letter-spacing:-0.01em">Who is actually good at this</h1></div>'
    + '<div style="display:flex; align-items:center; gap:var(--sp-4)">'
    + '<input value="' + esc(s.traderQuery) + '" ' + T.inp((e) => T.setState({ traderQuery: e.target.value }), 'traderQuery') + ' placeholder="Search name or wallet…" style="background:var(--panel); border:1px solid var(--line-edge); border-radius:var(--r-control); padding:var(--sp-3) var(--sp-4); ' + M + '; font-size:var(--t-small); color:var(--text); width:230px" />'
    + '<div ' + T.act(() => T.setState({ traderQuery: '', tPnl: 'all', tVol: 'all', traderRank: 'pnl' })) + ' class="hv-edge-strong" style="font-size:var(--t-small); color:var(--ink-3); border:1px solid var(--line-1); border-radius:var(--r-control); padding:var(--sp-3) var(--sp-4); cursor:pointer">Reset filters</div>'
    + '</div></div>'
    // Der Vorbehalt gegen rohe PnL-Raenge stand als leaderboard_caveat im
    // Register und war auf keiner Seite zu sehen; die Beschreibung davor
    // bleibt Sache dieser Seite.
    + caveatZeile('leaderboard_caveat', {
      vorsatz: 'Ranked from the public Polymarket all-time leaderboard. The smart score is a weighted composite of the components listed under each wallet; win rate and resolved-bet counts are computed per wallet with sample size and confidence interval, so open a wallet to see them.',
      stil: 'font-size:var(--t-body); color:var(--ink-4); margin-top:var(--sp-4); max-width:760px; line-height:1.5'
    })

    + '<div style="display:flex; align-items:center; gap:var(--sp-6); margin-top:var(--sp-5); flex-wrap:wrap">'
    + '<div style="display:flex; align-items:center; gap:var(--sp-3)"><span style="' + LABEL_BLOCK.replace('; margin-bottom:var(--sp-3)', '') + '">RANK BY</span><div style="display:flex; gap:var(--sp-3); flex-wrap:wrap">'
    + rankTabs + '</div></div>'
    + '</div>'

    + '<div style="border:1px solid var(--line-2); border-radius:var(--r-panel); margin-top:var(--sp-5); overflow:hidden">'
    + '<div ' + T.act(() => T.setState({ traderFiltersOpen: !s.traderFiltersOpen })) + ' class="hv-el" style="display:flex; align-items:center; justify-content:space-between; padding:var(--sp-4) var(--sp-5); background:var(--panel); cursor:pointer">'
    + '<div style="display:flex; align-items:center; gap:var(--sp-4)"><div style="font-size:var(--t-body)">Filters</div><div style="' + badge + '">' + tCount + '</div></div>'
    + '<div style="' + chevron + '">›</div></div>'
    + (s.traderFiltersOpen ?
      '<div style="padding:var(--sp-5); display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:var(--sp-5) var(--sp-6)">'
      + filterGroup('PROFIT', [['all','All'],['500k','>$500k'],['1m','>$1m'],['2m','>$2m'],['5m','>$5m']].map((o) => T.opt(o[1], s.tPnl === o[0], { tPnl: o[0] })).join(''))
      + filterGroup('VOLUME', [['all','All'],['10k','>$10k'],['100k','>$100k'],['1m','>$1m'],['50m','>$50m']].map((o) => T.opt(o[1], s.tVol === o[0], { tVol: o[0] })).join(''))
      + '</div>' : '')
    + '</div>'
    + '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-3); margin-top:var(--sp-4)">' + traderSorted.length + ' of ' + T.traders.length + ' wallets · all-time' + esc(asOf) + '</div>'
    + (basisSatz ? '<div style="font-size:var(--t-small); color:var(--ink-3); margin-top:var(--sp-3); max-width:820px; line-height:1.6">' + esc(basisSatz) + '</div>' : '')
    + (scoreWolke ? '<div style="margin-top:var(--sp-5); max-width:700px">' + scoreWolke + '</div>' : '')
    + '</div>'

    + '<div style="display:grid; grid-template-columns:' + grid + '; padding:var(--sp-4) var(--sp-6); border-bottom:1px solid var(--line-2); background:var(--panel); ' + LABEL + '">'
    + '<div>#</div><div>WALLET · SCORE COMPONENTS</div><div style="text-align:right">PROFIT</div>'
    + (hatWin ? '<div style="text-align:right">WIN RATE</div>' : '')
    + (hatResolved ? '<div style="text-align:right">RESOLVED BETS</div>' : '')
    + '<div style="text-align:right">VOLUME</div><div style="text-align:right">SCORE</div></div>'
    + traderSorted.map((t, i) => {
      const score = t.score;
      const avatarStyle = 'width:28px; height:28px; flex:none; border-radius:var(--r-control); background:var(--panel-hover); border:1px solid var(--line-2); display:flex; align-items:center; justify-content:center; ' + M + '; font-size:var(--t-small); color:' + (score != null && score >= 80 ? 'var(--accent)' : 'var(--ink-3)');
      const scoreStyle = M + '; font-size:var(--t-small); border-radius:var(--r-control); padding:var(--sp-2) var(--sp-3); ' + (score == null ? 'color:var(--ink-3); border:1px solid var(--line-2)' : score >= 80 ? 'color:var(--on-accent); background:var(--accent)' : score >= 60 ? 'color:var(--ink-1); border:1px solid var(--line-1)' : 'color:var(--warn); border:1px solid rgba(var(--warn-rgb),.35)');
      return '<div ' + T.act(() => T.openWallet(t.name)) + ' class="hv-panel" style="display:grid; grid-template-columns:' + grid + '; align-items:center; padding:var(--sp-4) var(--sp-6); border-bottom:1px solid var(--line-3); cursor:pointer">'
        + '<div style="' + M + '; font-size:var(--t-body); color:var(--ink-3)">' + (i + 1) + '</div>'
        + '<div style="display:flex; align-items:center; gap:var(--sp-4); min-width:0">'
        + '<div style="' + avatarStyle + '">' + esc(t.name.charAt(0).toUpperCase()) + '</div>'
        + '<div style="min-width:0"><div style="font-size:var(--t-body)">' + esc(t.name) + '</div>'
        + '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-3); margin-top:var(--sp-1)">' + esc(t.wallet) + (t.grade ? ' · grade ' + esc(t.grade) : '') + '</div>'
        + scorePartsHtml(t) + '</div></div>'
        + '<div style="' + M + '; font-size:var(--t-body); text-align:right; color:' + (t.pnl == null ? 'var(--ink-3)' : (t.pnl >= 0 ? 'var(--pos)' : 'var(--neg)')) + '">' + (t.pnl != null ? money(t.pnl) : '—') + '</div>'
        + (hatWin ? '<div style="' + M + '; font-size:var(--t-body); text-align:right">' + (t.win != null ? Math.round(t.win * 100) + '%' : '—') + '</div>' : '')
        + (hatResolved ? '<div style="' + M + '; font-size:var(--t-small); text-align:right; color:var(--ink-4)">' + (t.resolved != null ? num(t.resolved) : '—') + '</div>' : '')
        + '<div style="' + M + '; font-size:var(--t-body); text-align:right">' + (t.vol != null ? money(t.vol) : '—') + '</div>'
        + '<div style="display:flex; justify-content:flex-end"><div' + scoreTitel(t) + ' style="' + scoreStyle + '">' + (score != null ? score : 'n/a') + '</div></div>'
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
      + '<div style="padding:var(--sp-5) var(--sp-6) 0; display:flex; align-items:center; gap:var(--sp-3); flex-wrap:wrap"><span style="' + LABEL_BLOCK.replace('; margin-bottom:var(--sp-3)', '') + '">CATEGORY</span>'
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
  const bandZelle = (label, value, sub, last) => kpi({
    form: 'band', label, wert: value, sub: sub || null,
    gross: true, kuerzen: true, trenner: !last
  });
  // Die Spaltensummen lagen ueber der Breite des Inhaltsbereichs (1040 px
  // Minimum gegen 958 px Platz), also schob die Tabelle die Seite seitwaerts.
  // Die flexiblen Spalten bekommen kleinere Mindestbreiten; ueberlange Titel
  // faengt die Ellipse ab, wie in den anderen Tabellen auch.
  const GRID = 'minmax(140px,1.2fr) 58px 92px 92px 110px 62px minmax(110px,1fr) 108px 74px';

  return '<div>'
    + '<div style="padding:var(--sp-6) var(--sp-6) var(--sp-5); border-bottom:1px solid var(--line-2)">'
    + '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:.18em; color:var(--accent)">WHALE FLOW</div>'
    + '<h1 style="font-size:var(--t-head); line-height:1.25; margin:var(--sp-3) 0 0; font-weight:600; letter-spacing:-0.01em">Who is moving the big money</h1>'
    + '<div style="font-size:var(--t-body); color:var(--ink-4); margin-top:var(--sp-3); max-width:760px">The same prints as the tape, grouped by wallet, so one wallet buying twenty times reads as one story instead of twenty rows. Every figure below is a sum over the prints in this tape window' + (whaleCat === 'All' ? '' : ' in the category ' + esc(whaleCat)) + '.' + esc(ausschlussSatz) + '</div>'
    + '<div style="display:flex; align-items:center; gap:var(--sp-3); margin-top:var(--sp-4); flex-wrap:wrap">'
    + '<span style="' + LABEL_BLOCK.replace('; margin-bottom:var(--sp-3)', '') + '">CATEGORY</span>'
    + catChips.map((c) => T.chip(c.toUpperCase(), whaleCat === c, { whaleCat: c })).join('')
    + '</div>'
    + '<div style="display:flex; align-items:center; gap:var(--sp-3); margin-top:var(--sp-4); flex-wrap:wrap">'
    + '<span style="' + LABEL_BLOCK.replace('; margin-bottom:var(--sp-3)', '') + '">SORT BY</span>'
    + T.chip('Total $', sortKey === 'total', { whaleSort: 'total' })
    + T.chip('Biggest print', sortKey === 'biggest', { whaleSort: 'biggest' })
    + T.chip('Prints', sortKey === 'prints', { whaleSort: 'prints' })
    + '<span style="' + M + '; font-size:var(--t-micro); color:var(--ink-3); margin-left:var(--sp-3)">' + (walletCount > SHOW ? 'top ' + SHOW + ' of ' + num(walletCount) + ' wallets' : num(walletCount) + ' wallet' + (walletCount === 1 ? '' : 's')) + ' · ' + num(grouped.length) + ' print' + (grouped.length === 1 ? '' : 's') + ' grouped</span>'
    + '</div></div>'
    + '<div style="display:grid; grid-template-columns:repeat(5,1fr); border-bottom:1px solid var(--line-2)">'
    + bandZelle('WALLETS PRINTING BIG', num(walletCount), '')
    + bandZelle('PRINTS GROUPED', num(grouped.length), ohneWallet ? num(ohneWallet) + ' without a wallet left out' : '')
    + bandZelle('$ GROUPED · THIS WINDOW', money(total), '')
    + bandZelle('BIGGEST SINGLE PRINT', money(biggest), '')
    + bandZelle('TOP CATEGORY BY $', esc(topCatLabel), esc(topCatShare), true)
    + '</div>'
    // Ueber welche Spanne die Kennzahlen summiert wurden. Ohne sie liest
    // sich "$ GROUPED · THIS WINDOW" wie eine Tagessumme, obwohl der
    // oeffentliche Feed nur die juengsten Prints liefert und die Spanne mit
    // der Aktivitaet schwankt.
    + (fensterZeile ? '<div style="padding:var(--sp-3) var(--sp-6); border-bottom:1px solid var(--line-2); ' + M + '; font-size:var(--t-micro); color:var(--ink-4)">'
      + '<span style="letter-spacing:.14em; color:var(--ink-3); margin-right:var(--sp-3)">SUMMED OVER</span>' + esc(fensterZeile) + '</div>' : '')
    + '<div style="padding:var(--sp-4) var(--sp-6); border-bottom:1px solid var(--line-2); font-size:var(--t-small); color:var(--ink-4)"><span style="' + M + '; font-size:var(--t-micro); letter-spacing:.14em; color:var(--ink-3); margin-right:var(--sp-3)">CONCENTRATION</span>' + esc(konzentrationSatz) + '</div>'
    + '<div style="display:grid; grid-template-columns:' + GRID + '; gap:0 var(--sp-4); padding:var(--sp-4) var(--sp-6); border-bottom:1px solid var(--line-2); background:var(--panel); ' + LABEL + '">'
    + '<div>WALLET · VENUE</div><div style="text-align:right">PRINTS</div><div style="text-align:right">TOTAL</div><div style="text-align:right">BIGGEST</div><div style="text-align:right">LEANING</div><div style="text-align:right">MARKETS</div><div>TOP MARKET</div><div style="text-align:right">MOSTLY IN</div><div style="text-align:right">LAST PRINT</div></div>'
    + (rows.length ? '' : leerZeile('Every print in this window is anonymous — Kalshi publishes no wallet identity, so there is nothing to group by.'))
    + rows.map((w) => {
      // "MOSTLY" war ein Alphawert auf demselben Rot — bei 11 px landete das
      // bei 3.6:1 und damit unter der Lesbarkeitsschwelle. Jetzt trennt der
      // gedaempftere Farbton der Palette (var(--neg-soft)) die beiden Staerken, statt
      // Deckkraft wegzunehmen.
      const leanColor = w.lean === 'BUYING' ? 'var(--pos)' : w.lean === 'SELLING' ? 'var(--neg)' : w.lean === 'MOSTLY BUYING' ? 'var(--pos-soft)' : 'var(--neg-soft)';
      const leanStyle = M + '; font-size:var(--t-micro); letter-spacing:.08em; text-align:right; color:' + leanColor;
      const topMarketShare = w.total ? Math.round(w.topMarket.dollar / w.total * 100) : 0;
      // The drawer gets the address too: most of these wallets are not on
      // the leaderboard, and without it the click opened nothing (w.wallet is
      // the full address when the print carried one, else the name again —
      // openWallet keeps only a full address).
      return '<div ' + T.act(() => T.openWallet(w.name, w.wallet !== w.name ? w.wallet : '')) + ' class="hv-panel" style="display:grid; grid-template-columns:' + GRID + '; gap:0 var(--sp-4); align-items:center; padding:var(--sp-4) var(--sp-6); border-bottom:1px solid var(--line-3); cursor:pointer">'
        + '<div style="min-width:0"><div style="font-size:var(--t-body); white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="' + esc(w.name) + '">' + esc(w.name) + '</div>'
        + '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-3); margin-top:var(--sp-2); white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="' + esc(w.wallet) + '">' + esc(w.wallet) + ' · ' + esc(w.venues) + '</div></div>'
        + '<div style="' + M + '; font-size:var(--t-body); text-align:right; color:var(--ink-3)">' + w.prints + '</div>'
        + '<div style="' + M + '; font-size:var(--t-body); text-align:right">' + money(w.total) + '</div>'
        + '<div style="' + M + '; font-size:var(--t-body); text-align:right; color:var(--ink-3)">' + money(w.biggest) + '</div>'
        + '<div><div style="' + leanStyle + '">' + esc(w.lean) + '</div>'
        + '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-3); text-align:right; margin-top:var(--sp-1)">' + w.buys + ' buy' + (w.buys === 1 ? '' : 's') + ' · ' + w.sells + ' sell' + (w.sells === 1 ? '' : 's') + '</div></div>'
        + '<div style="' + M + '; font-size:var(--t-body); text-align:right; color:var(--ink-3)">' + w.marketCount + '</div>'
        + '<div style="min-width:0"><div style="font-size:var(--t-small); white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="' + esc(w.topMarket.title) + '">' + esc(w.topMarket.title) + '</div>'
        + '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-3); margin-top:var(--sp-1)">' + money(w.topMarket.dollar) + ' · ' + topMarketShare + '% of this wallet</div></div>'
        + '<div style="text-align:right"><div style="' + M + '; font-size:var(--t-small); color:var(--ink-2)">' + esc(w.cat) + '</div>'
        + '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-3); margin-top:var(--sp-1)">' + esc(w.catShare) + ' prints</div></div>'
        + '<div style="' + M + '; font-size:var(--t-micro); text-align:right; color:var(--ink-4)">' + esc(w.lastAgo) + '</div></div>';
    }).join('')
    + '</div>';
}

// ---------------------------------------------------------------- risk screen
// Helpers for the event cards and the flag log. Every field they read comes
// from /api/risk (api_views.risk_event_row) or /api/risk/log; a missing value
// renders as "—" or "n/a", never as a default number.
const CHIP = M + '; font-size:var(--t-micro); color:var(--ink-4); border:1px solid var(--line-2); border-radius:var(--r-control); padding:var(--sp-1) var(--sp-3); white-space:nowrap';
const LINK = 'color:var(--accent); text-decoration:none; ' + M + '; font-size:var(--t-micro); letter-spacing:.06em';

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
  return '<span style="' + M + '; font-size:var(--t-micro); letter-spacing:.06em; color:' + farbe + '; border:1px solid color-mix(in srgb, ' + farbe + ' 33%, transparent); border-radius:var(--r-control); padding:var(--sp-1) var(--sp-3); white-space:nowrap">'
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
  return '<div style="margin-top:var(--sp-4)">'
    + '<div style="position:relative; height:10px">'
    + '<div style="display:flex; height:10px; border-radius:var(--r-control); overflow:hidden; background:rgba(var(--ink),.07)">'
    + seg(groesse, 'rgba(var(--ink),.42)') + seg(timing, 'var(--warn)') + seg(muster, 'var(--accent)')
    + '</div>'
    + tick(40, 'rgba(var(--ink),.28)') + tick(55, 'rgba(var(--ink),.28)') + tick(70, 'rgba(var(--warn-rgb),.6)')
    + '<div style="position:absolute; left:' + wert.toFixed(1) + '%; top:-3px; width:2px; height:16px; background:rgba(var(--ink),.9)"></div>'
    + '</div>'
    + '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-4); margin-top:var(--sp-2)">size ' + groesse.toFixed(1) + ' · price &amp; timing ' + timing.toFixed(1) + ' · wallet pattern ' + muster.toFixed(1) + '</div>'
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
    ? '<div style="display:flex; height:8px; border-radius:var(--r-control); overflow:hidden; background:rgba(var(--ink),.06); margin-bottom:var(--sp-2)">'
      + seg(kaufYes, 'var(--accent)') + seg(kaufNo, 'var(--warn)') + seg(verkauf, 'var(--neg-soft)') + '</div>'
    : '';
  const rest = gesamt > 0
    ? [['YES buys', kaufYes, 'var(--pos)'], ['NO buys', kaufNo, 'var(--warn)'], ['sells', verkauf, 'var(--neg-soft)']]
      .filter((b) => b[1] > 0 && String(r.side || '').indexOf(b[0]) !== 0)
      .map((b) => '<span style="color:' + b[2] + '">' + b[0] + ' ' + money(b[1]) + '</span>').join(' · ')
    : '';
  return '<div style="margin-top:var(--sp-4)">' + balken
    + '<div style="display:flex; justify-content:space-between; align-items:center; gap:var(--sp-4); flex-wrap:wrap">'
    + riskSideChip(r)
    + (rest ? '<span style="' + M + '; font-size:var(--t-micro); color:var(--ink-4)">' + rest + '</span>' : '')
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
    + '<div style="position:relative; height:8px; border-radius:var(--r-control); background:rgba(var(--ink),.06)">'
    + '<div style="position:absolute; left:' + links.toFixed(1) + '%; top:0; width:' + band.toFixed(1) + '%; height:8px; border-radius:var(--r-control); background:rgba(var(--warn-rgb),.4)"></div>'
    + '<div style="position:absolute; left:' + Math.max(0, Math.min(99, Number(r.price_last) * 100)).toFixed(1) + '%; top:-2px; width:2px; height:12px; background:var(--warn)"></div>'
    + '</div>'
    + '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-4); margin-top:var(--sp-2)">at flag ' + esc(riskPriceLabel(r)) + bewegt + '</div>'
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
    + '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-4); margin-top:var(--sp-2)">' + esc(windowLabel(r.first_print, r.last_print, r.window_minutes)) + (r.prints ? ' · ' + r.prints + ' print' + (r.prints === 1 ? '' : 's') : '') + '</div>'
    + '</div>';
}

// Score components with points; zero components are left out (nothing to
// explain), the context multiplier is shown when it is not 1.
export function riskComponentsHtml(components) {
  if (!Array.isArray(components) || !components.length) return '';
  const teile = components.filter((c) => c && (c.key === 'context_multiplier' ? Number(c.value) !== 1 : Number(c.value) > 0));
  if (!teile.length) return '<span style="' + CHIP + '">no component above zero</span>';
  return teile.map((c) => '<span style="' + CHIP + '">' + esc(c.label) + ' <span style="color:var(--ink-1)">'
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
    const farbe = voll ? 'var(--warn)' : 'var(--ink-4)';
    const unter = [c.fact, c.rule].filter(Boolean).map((t) => esc(String(t))).join(' <span style="color:var(--ink-4)">·</span> ')
      + (c.weight_note ? ' <span style="color:var(--warn)">' + esc(c.weight_note) + '</span>' : '');
    return '<div style="padding:var(--sp-3) 0; border-bottom:1px solid var(--line-3)">'
      + '<div style="display:flex; align-items:center; gap:var(--sp-4)">'
      + '<div style="flex:0 0 158px; font-size:var(--t-small); color:var(--ink-1)" title="' + esc(String(c.measures || '')) + '">' + esc(String(c.label || c.key || '')) + '</div>'
      + '<div style="flex:1; height:6px; border-radius:var(--r-control); background:rgba(var(--ink),.08); overflow:hidden"><div style="width:' + (anteil * 100).toFixed(1) + '%; height:6px; background:' + farbe + '"></div></div>'
      + '<div style="flex:0 0 64px; text-align:right; ' + M + '; font-size:var(--t-small); color:' + (voll ? 'var(--warn)' : 'var(--ink-1)') + '">' + esc(String(c.value)) + '<span style="color:var(--ink-4)">/' + esc(String(c.max)) + '</span></div>'
      + '</div>'
      + (unter ? '<div style="font-size:var(--t-micro); color:var(--ink-4); margin-top:var(--sp-2); padding-left:0; line-height:1.45">' + unter + '</div>' : '')
      + '</div>';
  };
  const nichts = zero.length
    ? '<div style="font-size:var(--t-micro); color:var(--ink-3); padding:var(--sp-3) 0; line-height:1.5"><span style="' + M + '; font-size:var(--t-micro); letter-spacing:.12em; color:var(--ink-4)">NOT FOUND</span> '
      + zero.map((c) => esc(String(c.label || c.key || '')).toLowerCase() + (c.fact ? ' <span style="color:var(--ink-4)">(' + esc(String(c.fact)) + ')</span>' : '')).join(' · ') + '</div>'
    : '';
  const kontext = ctx
    ? '<div style="display:flex; align-items:baseline; gap:var(--sp-4); padding:var(--sp-3) 0; border-top:1px solid var(--line-3)">'
      + '<div style="flex:0 0 158px; font-size:var(--t-small); color:var(--ink-1)">' + esc(String(ctx.label || 'Context')) + '</div>'
      + '<div style="flex:1; font-size:var(--t-micro); color:var(--ink-4); line-height:1.45">' + esc(String(ctx.fact || '')) + (ctx.rule ? ' <span style="color:var(--ink-4)">· ' + esc(String(ctx.rule)) + '</span>' : '') + '</div>'
      + '<div style="flex:0 0 64px; text-align:right; ' + M + '; font-size:var(--t-small); color:' + (faktor > 1 ? 'var(--warn)' : faktor < 1 ? 'var(--ink-4)' : 'var(--ink-1)') + '">×' + esc(String(ctx.value)) + '</div></div>'
    : '';
  // The arithmetic, checkable: parts × context = score. When the listed
  // parts do not reach the score (an older answer without every column),
  // the line says so instead of pretending they do.
  const produkt = Math.min(100, Math.round(summe * faktor));
  const stimmt = score == null || Math.abs(produkt - Number(score)) <= 1;
  const rechnung = '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-4); padding-top:var(--sp-3); border-top:1px solid var(--line-2); margin-top:var(--sp-1)">'
    + summe.toFixed(1) + ' pts' + (ctx ? ' × ' + esc(String(ctx.value)) : '') + ' = <span style="color:var(--text)">' + produkt + '</span> / 100'
    + (stimmt ? '' : ' <span style="color:var(--warn)">· the card says ' + esc(String(score)) + ' — parts missing from this answer</span>')
    + ' <span style="color:var(--ink-4)">· under 40 low · 40–54 elevated · 55–69 medium · 70+ high</span></div>';
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

const BOOK_FARBE = (rel) => rel === 'adds' || rel === 'new_bet' ? 'var(--accent)' : rel === 'reduces' || rel === 'hedge' || rel === 'exit' ? 'var(--warn)' : 'var(--ink-3)';
const BOOK_WORT = (rel) => rel === 'adds' ? 'ADDS TO BOOK' : rel === 'reduces' ? 'HEDGE / CLOSING' : rel === 'hedge' ? 'HEDGED BOTH SIDES' : rel === 'exit' ? 'EXIT' : rel === 'new_bet' ? 'NOT HELD NOW' : rel === 'unpriced' ? 'NOT PRICED' : 'BOOK';
// "unpriced": the feed carried the rows but no price for them. That is not
// "nothing held" — it is nothing readable, and it gets its own word so the
// card cannot report a gap in the feed as an empty book.
const BOOK_KURZ = (rel) => rel === 'adds' ? 'adds' : rel === 'reduces' ? 'hedge / closing' : rel === 'hedge' ? 'hedged' : rel === 'exit' ? 'exit' : rel === 'new_bet' ? 'not held' : rel === 'unpriced' ? 'not priced' : 'book';

// One line for the closed card: "BOOK NOW 1 adds · 2 not held" — the
// relation counts, coloured like the full lines. "reading…" / "not read"
// while the answer is missing. Empty string when the card has no book.
export function riskBookSummary(T, r) {
  const eintrag = riskBookEntry(T, r);
  if (!eintrag) return '';
  const kopf = '<span style="' + M + '; font-size:var(--t-micro); letter-spacing:.12em; color:var(--ink-3)">BOOK NOW</span> ';
  const grau = '<span style="font-size:var(--t-small); color:var(--ink-3)">';
  if (eintrag.herkunft === 'loading') return '<div style="margin-top:var(--sp-3)">' + kopf + grau + 'reading the wallets\' open positions…</span></div>';
  if (eintrag.herkunft === 'fehler') return '<div style="margin-top:var(--sp-3)">' + kopf + grau + 'not read (' + esc(eintrag.fehler || 'no answer') + ')</span></div>';
  const books = eintrag.data && Array.isArray(eintrag.data.wallets) ? eintrag.data.wallets : [];
  if (!books.length) return '<div style="margin-top:var(--sp-3)">' + kopf + grau + 'no wallet readable</span></div>';
  const zaehler = {};
  let ungelesen = 0;
  books.forEach((b) => { if (!b.read) { ungelesen += 1; return; } zaehler[b.relation || 'book'] = (zaehler[b.relation || 'book'] || 0) + 1; });
  const teile = Object.keys(zaehler).map((rel) => '<span style="' + M + '; font-size:var(--t-micro); color:' + BOOK_FARBE(rel) + '">' + zaehler[rel] + ' ' + BOOK_KURZ(rel) + '</span>');
  if (ungelesen) teile.push('<span style="' + M + '; font-size:var(--t-micro); color:var(--ink-3)">' + ungelesen + ' not read</span>');
  return '<div style="margin-top:var(--sp-3); display:flex; align-items:center; gap:var(--sp-3); flex-wrap:wrap">' + kopf + teile.join('<span style="color:var(--ink-4)">·</span>') + '</div>';
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
  const kopf = '<span style="' + M + '; font-size:var(--t-micro); letter-spacing:.12em; color:var(--ink-3)">WALLET BOOK NOW</span> ';
  if (eintrag.herkunft === 'loading') return '<div style="margin-top:var(--sp-3); font-size:var(--t-small); color:var(--ink-3)">' + kopf + 'reading the wallets\' open positions in this market…</div>';
  if (eintrag.herkunft === 'fehler') return '<div style="margin-top:var(--sp-3); font-size:var(--t-small); color:var(--ink-3)">' + kopf + 'not read (' + esc(eintrag.fehler || 'no answer') + ')</div>';
  const books = eintrag.data && Array.isArray(eintrag.data.wallets) ? eintrag.data.wallets : [];
  if (!books.length) return '<div style="margin-top:var(--sp-3); font-size:var(--t-small); color:var(--ink-3)">' + kopf + 'no wallet readable</div>';
  return '<div style="margin-top:var(--sp-3); display:flex; flex-direction:column; gap:var(--sp-2)">'
    + books.map((b) => {
      if (!b.read) return '<div style="font-size:var(--t-small); color:var(--ink-3)">' + kopf + esc(b.short || b.wallet) + ' not read (' + esc(b.error || 'no answer') + ')</div>';
      const netz = b.net === 'YES' || b.net === 'NO' ? 'net ' + b.net : b.net === 'balanced' ? 'balanced' : b.relation === 'unpriced' ? 'no price' : 'flat';
      return '<div style="font-size:var(--t-small); line-height:1.45; color:var(--ink-2)">' + kopf
        + '<span style="' + M + '; color:var(--ink-1)">' + esc(b.short || b.wallet) + '</span> '
        + '<span style="' + M + '; font-size:var(--t-micro); letter-spacing:.08em; color:' + BOOK_FARBE(b.relation) + '; border:1px solid color-mix(in srgb, ' + BOOK_FARBE(b.relation) + ' 33%, transparent); border-radius:var(--r-control); padding:var(--sp-1) var(--sp-3); margin:0 var(--sp-2)">' + BOOK_WORT(b.relation) + ' · ' + esc(netz) + '</span>'
        + esc(b.text || '') + '</div>';
    }).join('')
    + '</div>';
}

function marketLink(url) {
  return url ? '<a data-stop href="' + esc(url) + '" target="_blank" rel="noopener" title="Open the market" style="' + LINK + '">market ↗</a>' : '';
}

// The move after the flag: "+30 m 36¢ (+2.0)"; "n/a" when no history could be
// read, "not yet" while the horizon is still ahead, "no print" when it passed
// without a trade. Those last two used to share the "not yet" wording, so a
// day-old flag in a market that never traded again claimed its +24 h point was
// still pending. A horizon that had already elapsed when the sampler wrote the
// flag says so: the move happened, but not while anyone could read the flag.
function afterCell(after, key, label) {
  const zelle = (inhalt, ton) => '<div><div style="' + LABEL + '">' + label + '</div>'
    + '<div style="' + M + '; font-size:var(--t-small); ' + (ton || 'color:var(--ink-3)') + '; margin-top:var(--sp-1)">' + inhalt + '</div></div>';
  const p = after && after[key];
  if (!after) return zelle('n/a');
  if (!p) return zelle('not yet');
  if (p.no_print) return zelle('no print');
  const move = p.move_c == null ? '' : ' <span style="color:' + (p.move_c > 0 ? 'var(--accent)' : p.move_c < 0 ? 'var(--neg-soft)' : 'var(--ink-4)') + '">' + (p.move_c > 0 ? '+' : '') + esc(String(p.move_c)) + '</span>';
  const vorbei = p.already_past
    ? '<span title="This horizon had already passed when the flag was written" style="color:var(--ink-4)"> · before the flag was readable</span>'
    : '';
  return zelle(cents(p.price) + move + vorbei, 'color:var(--text)');
}

// Die Quote ueber alle gemessenen Flags. Ohne sie stand auf der Seite nur
// die Einzelbewegung je Flag, und wer den Screen beurteilen wollte, zaehlte
// gruene Zellen — und zwar in einer Auswahl (juengste zuerst, nur
// Polymarket). Die Kachel nennt n, das 95-Prozent-Intervall, die
// Stichprobenguete, den Stand und die weggelassenen Nenner.
export function flagScoreboardHtml(sb) {
  if (!sb || !sb.horizons) return '';
  const HORIZONT = { '30m': '+30 MIN', '2h': '+2 H', '24h': '+24 H' };
  const zelle = (key) => {
    const h = sb.horizons[key];
    if (!h) return '';
    const quote = h.hit_rate == null
      ? '—'
      : Math.round(h.hit_rate * 100) + '%';
    const ci = h.ci95 ? '95% [' + Math.round(h.ci95[0] * 100) + '%, ' + Math.round(h.ci95[1] * 100) + '%]' : 'no interval';
    const badge = h.sample && h.sample.quality ? h.sample.quality : '';
    const farbe = badge === 'adequate' ? 'var(--text)' : 'var(--ink-3)';
    return '<div style="min-width:150px">'
      + '<div style="' + LABEL + '">' + HORIZONT[key] + '</div>'
      + '<div style="' + M + '; font-size:var(--t-head); margin-top:var(--sp-2); color:' + farbe + '">' + quote + '</div>'
      + '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-3); margin-top:var(--sp-1)">'
      + h.hits + '/' + h.n_decisive + ' decisive · ' + esc(ci) + '</div>'
      + '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-3)">sample ' + esc(badge)
      + (h.ties ? ' · ' + h.ties + ' flat' : '')
      + (h.already_past ? ' · ' + h.already_past + ' past before readable' : '')
      + (h.avg_move_c == null ? '' : ' · avg ' + (h.avg_move_c > 0 ? '+' : '') + h.avg_move_c + 'c') + '</div>'
      + '</div>';
  };
  return '<div style="margin:var(--sp-5) var(--sp-6) 0; background:var(--panel); border:1px solid var(--line-2); border-radius:var(--r-panel); padding:var(--sp-5)">'
    + '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:.14em; color:var(--ink-3)">FLAGGED SIDE HIGHER AFTERWARDS</div>'
    + '<div style="display:flex; gap:var(--sp-6); flex-wrap:wrap; margin-top:var(--sp-4)">'
    + Object.keys(HORIZONT).map(zelle).join('') + '</div>'
    + '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-4); margin-top:var(--sp-4); line-height:1.6; max-width:860px">'
    + esc(sb.basis || '') + '</div>'
    + '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-4); margin-top:var(--sp-3); line-height:1.6; max-width:860px">'
    + esc(sb.multiplicity || '') + '</div>'
    + '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-4); margin-top:var(--sp-3)">'
    + esc(String(sb.flags_measured || 0)) + ' of ' + esc(String(sb.flags_total || 0)) + ' flags measured'
    + (sb.as_of ? ' · as of ' + esc(utcShort(sb.as_of)) + ' UTC' : '') + '</div>'
    + '</div>';
}

// The flag log tab: rows newest first, with the price after the flag when
// the API could read it. Fetched only when the tab is opened.
export function renderRiskLog(T) {
  const live = T.liveData.riskLog;
  const intro = '<div style="padding:var(--sp-5) var(--sp-6) 0; font-size:var(--t-body); color:var(--ink-3); max-width:820px; line-height:1.5">'
    + 'Every event the screen flags is logged with the side, price and wallets at that moment, so it can be checked afterwards against what happened next.'
    + (live && live.min_score != null ? ' Rows with a score of ' + esc(String(live.min_score)) + ' and up are kept; the same market and side is one row per day (updated while it keeps flagging).' : '')
    + (live && live.sampler_interval_min ? ' A background sampler re-runs the screen every ' + esc(String(live.sampler_interval_min)) + ' min.' : '')
    + '</div>';
  if (!live) {
    return intro + '<div style="display:flex; align-items:center; gap:var(--sp-4); padding:var(--sp-5) var(--sp-6)">'
      + '<span style="width:7px; height:7px; border-radius:50%; background:var(--warn); display:inline-block"></span>'
      + '<span style="' + M + '; font-size:var(--t-micro); letter-spacing:.08em; color:var(--warn)">loading /api/risk/log</span>'
      + '<span style="' + M + '; font-size:var(--t-micro); color:var(--ink-3)">reads the log and, for the newest Polymarket flags, the price afterwards</span></div>';
  }
  if (live._quelle === 'fehler') {
    return intro + '<div style="display:flex; align-items:center; gap:var(--sp-4); padding:var(--sp-5) var(--sp-6)">'
      + '<span style="' + M + '; font-size:var(--t-micro); color:var(--neg-soft)">' + esc(herkunftSatz({ quelle: 'fehler', fehler: live._fehler }, '/api/risk/log')) + '</span>'
      + (T.neuLaden ? '<div ' + T.act(() => T.neuLaden('riskLog', 'risk')) + ' class="hv-edge-strong" style="' + M + '; font-size:var(--t-micro); color:var(--ink-2); border:1px solid var(--line-1); border-radius:var(--r-control); padding:var(--sp-2) var(--sp-4); cursor:pointer; white-space:nowrap">Try again</div>' : '')
      + '</div>';
  }
  const rows = Array.isArray(live.rows) ? live.rows : [];
  if (!rows.length) {
    return intro + leerZeile('The flag log is empty so far — it fills as the screen flags events (score '
      + (live.min_score != null ? String(live.min_score) : '40') + ' and up); nothing has been flagged since logging started on this host.');
  }
  const kopf = '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-3); padding:var(--sp-4) var(--sp-6) 0">' + rows.length + ' flag' + (rows.length === 1 ? '' : 's')
    + (live.enriched != null ? ' · price after the flag read for ' + live.enriched + ' of the newest ' + Math.min(rows.length, live.enrich_max || 30) + ' Polymarket flags' : '')
    + (live.as_of ? ' · as of ' + esc(String(live.as_of)) : '') + '</div>';
  return intro + kopf + flagScoreboardHtml(live.scoreboard) + '<div style="padding:var(--sp-4) var(--sp-6) var(--sp-5); display:grid; gap:var(--sp-4)">'
    + rows.map((f) => {
      const sevColor = f.sev === 'high' ? 'var(--warn)' : f.sev === 'medium' ? 'var(--ink-2)' : 'var(--ink-4)';
      const scoreStyle = M + '; font-size:var(--t-lead); color:' + sevColor;
      const preis = { price_last: f.price_at_flag, price_outcome: f.price_outcome, price_min: f.price_min, price_max: f.price_max };
      const seite = { side: f.side, side_notional: f.side_notional, side_share: f.side_share, notional_usd: f.notional };
      const hatAfter = Object.prototype.hasOwnProperty.call(f, 'after');
      return '<div style="background:var(--panel); border:1px solid var(--line-2); border-radius:var(--r-panel); padding:var(--sp-5)">'
        + '<div style="display:flex; align-items:flex-start; justify-content:space-between; gap:var(--sp-4)">'
        + '<div style="min-width:0">'
        + '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:.12em; color:var(--ink-3)">' + esc(utcShort(f.last_seen)) + ' UTC · ' + esc(String(f.venue || '')) + (f.category ? ' · ' + esc(f.category) : '') + (f.times_seen > 1 ? ' · seen ' + f.times_seen + '× since ' + esc(utcShort(f.first_seen)) : '') + '</div>'
        + '<div style="font-size:var(--t-lead); margin-top:var(--sp-2); line-height:1.35">' + esc(f.title || f.market_key || '—') + (f.url ? ' ' + marketLink(f.url) : '') + '</div>'
        + '</div>'
        + '<div style="display:flex; align-items:baseline; gap:var(--sp-2); flex:none"><div style="' + scoreStyle + '">' + (f.score != null ? Math.round(f.score) : '—') + '</div><div style="' + M + '; font-size:var(--t-micro); color:var(--ink-4)">/100</div></div>'
        + '</div>'
        + '<div style="display:flex; gap:var(--sp-3); flex-wrap:wrap; margin-top:var(--sp-3); align-items:center">' + riskSideChip(seite)
        + '<span style="' + CHIP + '">at flag ' + esc(riskPriceLabel(preis)) + '</span>'
        + '<span style="' + CHIP + '">' + esc(windowLabel(f.window_start, f.window_end, f.window_minutes)) + '</span>'
        + '<span style="' + CHIP + '">' + (f.unique_wallets || 0) + ' wallet' + (f.unique_wallets === 1 ? '' : 's') + (f.prints ? ' · ' + f.prints + ' prints' : '') + '</span></div>'
        + (hatAfter ? '<div style="display:flex; gap:var(--sp-6); margin-top:var(--sp-4)">' + afterCell(f.after, '30m', '+30 MIN') + afterCell(f.after, '2h', '+2 H') + afterCell(f.after, '24h', '+24 H')
          + '<div><div style="' + LABEL + '">MEASURED ON</div><div style="' + M + '; font-size:var(--t-small); color:var(--ink-4); margin-top:var(--sp-1)">' + (f.after ? esc(f.price_outcome || 'flagged') + ' side, from last print' : (String(f.venue).toLowerCase() === 'kalshi' ? 'Kalshi: no history read' : 'no history / not in the enriched set')) + '</div></div></div>' : '')
        + '<div style="display:flex; gap:var(--sp-2); flex-wrap:wrap; margin-top:var(--sp-3)">' + riskWalletsHtml(f.top_wallets, f.unique_wallets) + '</div>'
        + riskBookHtml(T, { top_wallets: f.top_wallets, venue: f.venue, market_key: f.market_key, side: f.side })
        + '<div style="display:flex; gap:var(--sp-2); flex-wrap:wrap; margin-top:var(--sp-3)">' + riskComponentsHtml(f.components) + '</div>'
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
// Die Beschriftung des Bandes kommt aus ../risk_bands.js und damit aus
// app/suspicion.py: HIGH / MEDIUM / ELEVATED / LOW stand neben einer Zahl von
// 0 bis 100 und las sich als Wahrscheinlichkeit fuer Insiderhandel. Die Zahl
// ist eine Punktesumme aus neun Flow-Merkmalen mit gesetzten Gewichten, also
// zaehlen die Baender jetzt getroffene Pruefungen.
const BAND = (score, T, roh) => scoreBand(score, T && T.liveData ? T.liveData.risk : null, roh);

// Die Score-Verteilung des Screens. Der Trichter bleibt, er zaehlt drei
// Stufen; das Histogramm sagt, welche Form dahinter liegt.
//
// Ohne sie ist "77 von 100" eine Zahl ohne Bezugsrahmen: liegt 77 am oberen
// Rand eines dichten Feldes oder mitten drin? Die beiden Bandgrenzen stehen
// als senkrechte Referenzen im Bild, die geflaggte Teilmenge als zweite Lage
// in derselben Saeule, damit man sieht, wo die Karten herkommen.
export function riskScoreVerteilung(live) {
  const bins = live && Array.isArray(live.score_bins) ? live.score_bins : [];
  const gefuellt = bins.filter((b) => b && (+b.anzahl || 0) > 0);
  if (!gefuellt.length) return '';
  const minScore = live && live.event_min_score != null ? Math.round(Number(live.event_min_score)) : 40;
  const gesamt = bins.reduce((a, b) => a + (+b.anzahl || 0), 0);
  const geflaggt = bins.reduce((a, b) => a + (+b.geflaggt || 0), 0);
  return histogramm({
    titel: 'WHERE THE SCORES SIT',
    hinweis: num(gesamt) + ' markets scored',
    xLabel: 'flow-pattern score (points out of 100)',
    yLabel: 'markets screened',
    bins: bins.map((b) => ({ von: +b.von, bis: +b.bis, anzahl: +b.anzahl || 0, geflaggt: +b.geflaggt || 0 })).map((b) => ({
      von: b.von, bis: b.bis, anzahl: b.anzahl, hervor: b.geflaggt
    })),
    referenzen: [{ wert: minScore, label: 'flag ' + minScore }, { wert: 70, label: 'most patterns 70' }],
    gesamtLabel: 'screened',
    hervorLabel: 'flagged, gets a card',
    zaehlEinheit: 'markets',
    hoehe: 190,
    // Kein zweiter Vorbehalt hier: screen_not_proof steht im Kopf dieser
    // Seite, und derselbe Satz zweimal im selben Sichtfeld liest sich als
    // zwei Aussagen.
    fussnote: num(geflaggt) + ' of ' + num(gesamt) + ' scored markets cleared the flag threshold of '
      + minScore + '/100 and appear as cards.'
  });
}

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
  const band = BAND(score, T, r0);
  const toggle = hatDetails
    ? '<div data-stop ' + T.act(() => T.setState({ riskOpen: Object.assign({}, s.riskOpen || {}, { [key]: !offen }) })) + ' class="hv-edge-strong" style="' + M + '; font-size:var(--t-micro); letter-spacing:.06em; color:' + (offen ? 'var(--text)' : 'var(--ink-3)') + '; border:1px solid ' + (offen ? 'var(--line-edge)' : 'var(--line-1)') + '; border-radius:var(--r-control); padding:var(--sp-2) var(--sp-3); cursor:pointer; white-space:nowrap; user-select:none">' + (offen ? 'Why ' + score + '? ▴' : 'Why ' + score + '? ▾') + '</div>'
    : '';
  const flags = Array.isArray(r0.flags) && r0.flags.length ? r0.flags : (r.detail && !/^No individual flags/.test(r.detail) ? String(r.detail).split(' · ') : []);
  const details = offen && hatDetails
    ? '<div data-stop style="margin-top:var(--sp-4); border-top:1px dashed var(--line-2); padding-top:var(--sp-4); cursor:default">'
      + '<div style="display:flex; align-items:baseline; justify-content:space-between; gap:var(--sp-4); flex-wrap:wrap">'
      + '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:.12em; color:var(--ink-3)">WHY ' + score + ' / 100 · WHAT EACH PART SAW</div>'
      + (flags.length ? '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-3)">flags: ' + flags.map((f) => esc(String(f))).join(' · ') + '</div>' : '')
      + '</div>'
      + (comps.length ? '<div style="margin-top:var(--sp-3)">' + riskScoreBreakdown(comps, score) + '</div>' : '<div style="' + NOTIZ + '; margin-top:var(--sp-3)">' + esc(r.detail || 'No component breakdown in this answer.') + '</div>')
      + riskBookHtml(T, r0)
      + '</div>'
    : '';
  // Preis- und Fenster-Grafik teilen sich eine Zeile; fehlt eine Seite
  // (Kalshi ohne Preise, aeltere Antwort ohne Fenster), bleibt die andere.
  const preisSpalte = hatFlow ? riskPriceStrip(r0) : '';
  const fensterSpalte = hatFlow ? riskWindowStrip(r0) : '';
  const streifen = (preisSpalte || fensterSpalte)
    ? '<div style="display:flex; gap:var(--sp-5); margin-top:var(--sp-4)">' + preisSpalte + fensterSpalte + '</div>'
    : '';
  return '<div ' + (klickbar ? r.act + ' class="hv-edge" ' : '') + 'data-bg style="background:var(--panel); border:1px solid ' + (r0.sev === 'high' ? 'rgba(var(--warn-rgb),.3)' : 'var(--line-2)') + '; border-radius:var(--r-panel); padding:var(--sp-5); ' + (klickbar ? 'cursor:pointer; ' : '') + '">'
    + '<div style="display:flex; align-items:flex-start; justify-content:space-between; gap:var(--sp-4)">'
    + '<div style="' + r.kindStyle + '; padding-top:var(--sp-2)">' + esc(r.kind) + '</div>'
    + '<div style="text-align:right; flex:none"><div style="display:flex; align-items:baseline; gap:var(--sp-3); justify-content:flex-end"><div style="' + r.scoreStyle + '">' + r.score + '</div>'
    + '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-4)">/100</div></div>'
    + '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:.12em; color:' + band[1] + '">' + band[0] + '</div></div></div>'
    + '<div style="font-size:var(--t-lead); margin-top:var(--sp-3); line-height:1.35">' + esc(r.market) + (r0.url ? ' ' + marketLink(r0.url) : '') + '</div>'
    + '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:.1em; color:var(--ink-3); margin-top:var(--sp-2)"' + (r0.context_note ? ' title="' + esc(r0.context_note) + '"' : '') + '>' + (r0.category ? esc(String(r0.category).toUpperCase()) + ' · ' : '') + esc(String(r.venue || '').toUpperCase()) + '</div>'
    + riskCompositionBar(comps, score)
    + (hatFlow
      ? riskFlowRow(r0)
        + streifen
        + '<div style="display:flex; gap:var(--sp-2); flex-wrap:wrap; margin-top:var(--sp-3)">' + riskWalletsHtml(r0.top_wallets, r0.wallets) + '</div>'
        + riskBookSummary(T, r0)
      : '<div style="font-size:var(--t-body); color:var(--ink-3); margin-top:var(--sp-3); line-height:1.45">' + esc(r.detail) + '</div>')
    + '<div style="height:1px; background:rgba(var(--ink),.07); margin:var(--sp-5) 0 var(--sp-4)"></div>'
    + '<div style="display:flex; gap:var(--sp-6); align-items:flex-end; justify-content:space-between; flex-wrap:wrap"><div style="display:flex; gap:var(--sp-6)">'
    + [['WALLETS', r.wallets], ['NOTIONAL', r.notional], ['WINDOW', r.window]].map((p) =>
      '<div><div style="' + M + '; font-size:var(--t-micro); letter-spacing:.12em; color:var(--ink-3)">' + p[0] + '</div><div style="' + M + '; font-size:var(--t-body); margin-top:var(--sp-2)">' + esc(String(p[1])) + '</div></div>'
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
    '<div style="display:flex; align-items:center; gap:var(--sp-4)">'
    + '<div style="flex:0 0 158px; ' + M + '; font-size:var(--t-micro); letter-spacing:.08em; color:' + farbe + '">' + label + ' <span style="font-size:var(--t-body); color:' + (farbe === 'var(--warn)' ? 'var(--warn)' : 'var(--text)') + '">' + (wert != null ? wert : '—') + '</span></div>'
    + '<div style="flex:1; height:12px; border-radius:var(--r-control); background:rgba(var(--ink),.07); overflow:hidden"><div style="width:' + trichterBreite(wert).toFixed(1) + '%; height:12px; background:' + balkenFarbe + '"></div></div>'
    // .5 lag im dunklen Thema bei 4.49:1 und damit knapp unter AA. Die
    // Korrektur auf .62 ist hier zur Textstufe --ink-3 geworden (.60 dunkel,
    // .62 hell): gemessen 6.05:1 dunkel und 5.96:1 hell, also weiterhin weit
    // ueber der Schwelle (Alpha-Leiter in docs/design/review_2026-08-28.md).
    + '<div style="flex:0 0 210px; font-size:var(--t-micro); color:var(--ink-3)">' + satz + '</div>'
    + '</div>';
  const seitenKpi = (label, wert, amber) =>
    '<div style="flex:1; background:var(--panel); border:1px solid var(--line-2); border-radius:var(--r-panel); padding:var(--sp-4) var(--sp-5); display:flex; align-items:center; justify-content:space-between; gap:var(--sp-4)">'
    + '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:.12em; color:var(--ink-3)">' + label + '</div>'
    + '<div style="' + M + '; font-size:var(--t-head); color:' + (amber ? 'var(--warn)' : 'var(--text)') + '">' + (wert != null ? wert : '—') + '</div></div>';
  const verteilung = riskScoreVerteilung(live);
  const trichter =
    '<div style="display:flex; gap:var(--sp-5); padding:var(--sp-5) var(--sp-6)' + (verteilung ? '' : '; border-bottom:1px solid var(--line-2)') + '">'
    + '<div style="flex:1; background:var(--panel); border:1px solid var(--line-2); border-radius:var(--r-panel); padding:var(--sp-5); display:flex; flex-direction:column; gap:var(--sp-3)">'
    + '<div style="display:flex; justify-content:space-between; align-items:baseline; gap:var(--sp-4)">'
    + '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:.12em; color:var(--ink-3)">THE SCREEN, AS A FUNNEL</div>'
    + '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-3)">floor at ' + minScore + '/100</div></div>'
    + trichterZeile('SCREENED', screened, 'var(--ink-2)', 'rgba(var(--ink),.18)', 'every market with whale flow in the window')
    + trichterZeile('FLAGGED ≥ ' + minScore, flagged, 'var(--ink-2)', 'rgba(var(--ink),.5)', 'cleared the flag threshold — these get cards')
    + trichterZeile('AT 70 AND UP', hochEvents, 'var(--warn)', 'var(--warn)', 'tripped most of the checks')
    + '</div>'
    + '<div style="flex:0 0 280px; display:flex; flex-direction:column; gap:var(--sp-4)">'
    + seitenKpi('WALLETS AT 70 AND UP', kp ? kp.high_risk_wallets : null, true)
    + seitenKpi('FRESH-WALLET CLUSTERS', kp ? kp.fresh_clusters : null, false)
    + seitenKpi('COORDINATED CLUSTERS', kp ? kp.coordinated_clusters : null, false)
    + '</div></div>'
    // Unter dem Trichter, nicht daneben: der Trichter zaehlt drei Stufen,
    // das Histogramm zeigt die Verteilung, aus der sie geschnitten sind.
    + (verteilung
      ? '<div style="padding:0 var(--sp-6) var(--sp-5); border-bottom:1px solid var(--line-2)">'
        + '<div style="max-width:700px">' + verteilung + '</div></div>'
      : '');
  const walletRows = live && live.wallets ? live.wallets : [];

  let body = '';
  if (s.riskView === 'events') {
    // The color code of the composition bars, taught once page-level; the
    // per-part recipe lives in each card's "Why?" breakdown. The funnel
    // above already says that cards start at the flag threshold.
    const unterZahl = live ? Number(live.events_below_min) || 0 : 0;
    const swatch = (farbe, wort) => '<div style="display:flex; align-items:center; gap:var(--sp-3)"><div style="width:14px; height:8px; border-radius:2px; background:' + farbe + '"></div><div style="font-size:var(--t-small); color:var(--ink-2)">' + wort + '</div></div>';
    const legende = '<div style="display:flex; align-items:center; justify-content:space-between; gap:var(--sp-5); padding:var(--sp-5) var(--sp-6) 0; flex-wrap:wrap">'
      + '<div style="display:flex; align-items:center; gap:var(--sp-5); flex-wrap:wrap">'
      + '<span style="' + M + '; font-size:var(--t-micro); letter-spacing:.12em; color:var(--ink-3)">SCORE COMPOSITION</span>'
      + swatch('rgba(var(--ink),.42)', 'size of the money')
      + swatch('var(--warn)', 'price &amp; timing')
      + swatch('var(--accent)', 'wallet pattern')
      + '</div>'
      + '<div style="font-size:var(--t-small); color:var(--ink-3)">ticks at 40 · 55 · 70 points · open <span style="' + M + '; font-size:var(--t-micro)">Why?</span> on a card for the full arithmetic</div>'
      + '</div>';
    // The honest empty state: with the threshold in place, "no cards" most
    // often means "everything screened was unremarkable", and the page says
    // exactly that with the numbers, instead of a bare loading sentence.
    const leerSatz = T.risks.length
      ? 'No event in this band.'
      : (unterZahl > 0
        ? 'All ' + (live && live.kpis ? live.kpis.events_screened : unterZahl) + ' screened markets scored below the flag threshold (' + minScore + ') — nothing suspicious in this window.'
        : risikoSatz);
    const unterNote = riskFiltered.length && unterZahl > 0
      ? '<div style="padding:0 var(--sp-6) var(--sp-5); ' + M + '; font-size:var(--t-micro); color:var(--ink-4)">' + unterZahl + ' more market' + (unterZahl === 1 ? '' : 's') + ' screened below ' + minScore + '/100 — watch only, no card.</div>'
      : '';
    body = '<div>'
      + legende
      + '<div style="display:flex; gap:var(--sp-3); padding:var(--sp-5) var(--sp-6) 0; flex-wrap:wrap">'
      // Die Filter heissen nach der Punktspanne, die sie zeigen. "High" und
      // "Watch" waren Einschaetzungen fuer eine Zahl, die keine traegt.
      + [T.tab('All', s.riskFilter === 'all', { riskFilter: 'all' }),
         T.tab('70 and up', s.riskFilter === 'high', { riskFilter: 'high' }),
         T.tab('55–69', s.riskFilter === 'medium', { riskFilter: 'medium' })].join('')
      + '</div>'
      + (riskFiltered.length ? '' : leerZeile(leerSatz))
      + '<div style="padding:var(--sp-5) var(--sp-6); display:grid; grid-template-columns:repeat(2,1fr); gap:var(--sp-5)">'
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
      + '<div style="padding:var(--sp-5) var(--sp-6) 0; font-size:var(--t-small); color:var(--ink-3); line-height:1.55; max-width:860px">'
      + 'The flagged flow grouped by the wallet that placed it — the <span style="font-style:italic">who</span> behind the Events tab. '
      + 'Same 0–100 point total and the same bands as Events: how many of the screen\'s nine flow checks this wallet\'s prints tripped '
      + '(size, long odds, timing, account freshness). '
      + 'The chips under each wallet say which patterns fired; <span style="' + M + '; font-size:var(--t-small)">watch only</span> means none did — the wallet is listed for size alone.'
      + '</div>'
      + '<div style="border:1px solid var(--line-2); border-radius:var(--r-panel); margin:var(--sp-5) var(--sp-6); overflow:hidden">'
      + '<div style="display:grid; grid-template-columns:' + GRID_W + '; gap:var(--sp-4); padding:var(--sp-3) var(--sp-5); background:var(--panel); border-bottom:1px solid var(--line-2); ' + M + '; font-size:var(--t-micro); letter-spacing:.12em; color:var(--ink-3)">'
      + '<div>WALLET · WHY FLAGGED</div><div style="text-align:right">SCORE</div><div style="text-align:right">PRINTS</div><div style="text-align:right">NOTIONAL</div><div style="text-align:right">BIGGEST</div><div style="text-align:right">FIRST SEEN</div></div>'
      + (walletRows.length ? '' : leerZeile(antwortDa ? 'No wallet cleared the screen in this window — nothing in the flagged flow groups to a suspicious wallet.' : risikoSatz))
      + walletRows.map((w) => {
        const band = BAND(Number(w.score) || 0, T, w);
        const scoreStyle = M + '; font-size:var(--t-small); border-radius:var(--r-control); padding:var(--sp-2) var(--sp-3); ' + (w.score >= 70 ? 'color:var(--on-accent); background:var(--warn)' : w.score >= 55 ? 'color:var(--warn); border:1px solid rgba(var(--warn-rgb),.35)' : 'color:var(--ink-2); border:1px solid var(--line-1)');
        const flags = Array.isArray(w.flags) ? w.flags : [];
        const flagChips = flags.map((f) => {
          const echt = f !== 'watch only';
          return '<span style="' + M + '; font-size:var(--t-micro); white-space:nowrap; border-radius:var(--r-control); padding:var(--sp-1) var(--sp-3); '
            + (echt ? 'color:var(--warn); border:1px solid rgba(var(--warn-rgb),.3)' : 'color:var(--ink-3); border:1px solid var(--line-2)') + '">' + esc(f) + '</span>';
        }).join('');
        return '<div ' + T.act(() => T.openWallet(w.wallet, w.address)) + ' class="hv-panel" style="display:grid; grid-template-columns:' + GRID_W + '; gap:var(--sp-4); align-items:center; padding:var(--sp-4) var(--sp-5); border-bottom:1px solid var(--line-3); ' + M + '; font-size:var(--t-small); cursor:pointer">'
          + '<div style="min-width:0"><div style="font-family:var(--font-ui); font-size:var(--t-body); white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="' + esc(w.address || w.wallet) + '">' + esc(w.wallet) + '</div>'
          + '<div style="font-size:var(--t-micro); color:var(--ink-3); margin-top:var(--sp-1); white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="' + esc(w.context) + '">mostly in ' + esc(w.context) + '</div>'
          + (flagChips ? '<div style="display:flex; gap:var(--sp-2); flex-wrap:wrap; margin-top:var(--sp-2)">' + flagChips + '</div>' : '')
          + '</div>'
          + '<div style="text-align:right"><div style="display:inline-block; ' + scoreStyle + '">' + w.score + '</div>'
          + '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:.1em; color:' + band[1] + '; margin-top:var(--sp-2)">' + band[0] + '</div></div>'
          + '<div style="text-align:right; color:var(--ink-3)">' + w.prints + '</div>'
          + '<div style="text-align:right">' + esc(String(w.notional)) + '</div>'
          + '<div style="text-align:right; color:var(--ink-3)">' + esc(String(w.largest || '—')) + '</div>'
          + '<div style="text-align:right; color:var(--ink-3)">' + esc(w.firstSeen) + '</div></div>';
      }).join('')
      + '</div></div>';
  } else if (s.riskView === 'fresh') {
    // Eine Karte je Markt: WIE VIELE frische Wallets, WELCHE Seite, WIE VIEL
    // Geld — als drei benannte Zahlen statt einer amber Zahl, die wie ein
    // Score aussah und in Wahrheit der Zaehler war.
    const freshRows = live && live.fresh ? live.fresh : [];
    const antwortDa = !!live && live._quelle !== 'fehler';
    const seiteFarbe = (seite) => seite === 'YES' ? 'var(--accent)' : seite === 'NO' ? 'var(--neg-soft)' : 'var(--ink-2)';
    body = '<div>'
      + '<div style="padding:var(--sp-5) var(--sp-6) 0; font-size:var(--t-small); color:var(--ink-3); line-height:1.55; max-width:860px">'
      + '<span style="' + M + '; font-size:var(--t-small)">Fresh</span> = a wallet with at most two prior trades in this tape window. '
      + 'Several of them betting whale size on the same side of one market is the classic pattern of accounts created for a single bet.'
      + '</div>'
      + (freshRows.length ? '' : leerZeile(antwortDa
        ? 'No fresh-wallet cluster in this window — no market where several brand-new wallets took the same side at size. Most windows look like this; a hit shows up here and raises the market\'s event score.'
        : risikoSatz))
      + '<div style="padding:var(--sp-5) var(--sp-6) var(--sp-2); display:grid; grid-template-columns:repeat(auto-fill,minmax(340px,1fr)); gap:var(--sp-5)">'
      + freshRows.map((c) => {
        const punkte = '●'.repeat(Math.min(Number(c.count) || 0, 8)) + (Number(c.count) > 8 ? '…' : '');
        return '<div style="background:var(--panel); border:1px solid var(--line-2); border-radius:var(--r-panel); padding:var(--sp-5)">'
          + '<div style="font-size:var(--t-lead); line-height:1.35">' + esc(c.market) + (c.venue ? ' <span style="' + M + '; font-size:var(--t-micro); color:var(--ink-3)">' + esc(String(c.venue).toUpperCase()) + '</span>' : '') + '</div>'
          + '<div style="display:flex; gap:var(--sp-6); margin-top:var(--sp-4); align-items:flex-end; flex-wrap:wrap">'
          + '<div><div style="' + M + '; font-size:var(--t-micro); letter-spacing:.12em; color:var(--ink-3)">FRESH WALLETS</div>'
          + '<div style="display:flex; align-items:baseline; gap:var(--sp-3); margin-top:var(--sp-2)"><span style="' + M + '; font-size:var(--t-head); color:var(--warn)">' + (c.count != null ? c.count : '—') + '</span>'
          + '<span style="' + M + '; font-size:var(--t-micro); color:var(--warn); letter-spacing:2px">' + punkte + '</span></div></div>'
          + '<div><div style="' + M + '; font-size:var(--t-micro); letter-spacing:.12em; color:var(--ink-3)">ALL ON</div>'
          + '<div style="' + M + '; font-size:var(--t-lead); margin-top:var(--sp-2); color:' + seiteFarbe(c.side) + '">' + esc(c.side || 'same side') + '</div></div>'
          + '<div><div style="' + M + '; font-size:var(--t-micro); letter-spacing:.12em; color:var(--ink-3)">COMBINED</div>'
          + '<div style="' + M + '; font-size:var(--t-lead); margin-top:var(--sp-2)">' + esc(String(c.notional || '—')) + '</div></div>'
          + '</div>'
          + '<div style="font-size:var(--t-small); color:var(--ink-3); margin-top:var(--sp-4); line-height:1.45">' + esc(c.detail) + '</div>'
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
      + '<div style="padding:var(--sp-5) var(--sp-6) 0; font-size:var(--t-small); color:var(--ink-3); line-height:1.55; max-width:860px">'
      + 'Markets where three or more wallets hit the same side within a 30-minute window — money arriving together. '
      + 'The bar shows how tight the burst was: the full track is 30 minutes, the filled part is the actual span.'
      + '</div>'
      + '<div style="border:1px solid var(--line-2); border-radius:var(--r-panel); margin:var(--sp-5) var(--sp-6); overflow:hidden">'
      + '<div style="display:grid; grid-template-columns:' + GRID_T + '; gap:var(--sp-4); padding:var(--sp-3) var(--sp-5); background:var(--panel); border-bottom:1px solid var(--line-2); ' + M + '; font-size:var(--t-micro); letter-spacing:.12em; color:var(--ink-3)">'
      + '<div>MARKET</div><div style="text-align:right">WALLETS</div><div>BURST · OF 30 MIN</div><div style="text-align:right">SIDE</div><div style="text-align:right">NOTIONAL</div></div>'
      + (timingRows.length ? '' : leerZeile(antwortDa
        ? 'No coordinated burst in this window — no market where three or more wallets hit the same side within 30 minutes of each other.'
        : risikoSatz))
      + timingRows.map((c) => {
        const span = Number(c.span_minutes);
        const anteil = isNaN(span) ? 0 : Math.max(0.02, Math.min(1, span / 30));
        const balken = '<div style="display:flex; align-items:center; gap:var(--sp-3)">'
          + '<div style="flex:1; height:7px; border-radius:var(--r-control); background:rgba(var(--ink),.08); overflow:hidden">'
          + '<div style="width:' + (anteil * 100).toFixed(1) + '%; height:7px; background:' + (c.same ? 'var(--warn)' : 'rgba(var(--ink),.45)') + '"></div></div>'
          + '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-2); white-space:nowrap">' + esc(c.window) + '</div></div>';
        return '<div style="display:grid; grid-template-columns:' + GRID_T + '; gap:var(--sp-4); align-items:center; padding:var(--sp-4) var(--sp-5); border-bottom:1px solid var(--line-3); ' + M + '; font-size:var(--t-small)">'
          + '<div style="font-family:var(--font-ui); font-size:var(--t-body); min-width:0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="' + esc(c.market) + '">' + esc(c.market) + '</div>'
          + '<div style="text-align:right">' + c.wallets + '</div>'
          + balken
          + '<div style="text-align:right; ' + M + '; font-size:var(--t-small); color:' + (c.same ? 'var(--warn)' : 'var(--ink-3)') + '">' + (c.same ? 'all on ' + esc(c.side || 'one side') : 'mixed') + '</div>'
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
    const musterFarbe = (p) => p === 'Tight clique' ? 'var(--warn)' : p === 'Connected group' ? 'var(--ink-1)' : 'var(--ink-4)';
    body = '<div style="padding:var(--sp-5) var(--sp-6)">'
      + renderClusterGraphics(live)
      + '<div style="display:grid; grid-template-columns:repeat(auto-fill,minmax(360px,1fr)); gap:var(--sp-5)">'
      + networkRows.map((n) => {
        const farbe = clusterFarbe(live && live.graph, n.id);
        const mitglieder = Array.isArray(n.members) ? n.members : [];
        const rest = (n.members_total || mitglieder.length) - mitglieder.length;
        const maerkte = Array.isArray(n.markets) ? n.markets : [];
        return '<div style="background:var(--panel); border:1px solid var(--line-2); border-left:3px solid ' + farbe + '; border-radius:var(--r-panel); padding:var(--sp-5)">'
          + '<div style="display:flex; align-items:center; justify-content:space-between; gap:var(--sp-4); flex-wrap:wrap">'
          + '<div style="display:flex; align-items:center; gap:var(--sp-3)"><span style="width:9px; height:9px; border-radius:2px; flex:none; background:' + farbe + '"></span>'
          + '<span style="font-size:var(--t-lead); font-weight:600">' + esc(n.name) + '</span>'
          + '<span style="' + M + '; font-size:var(--t-micro); color:var(--ink-3)">' + n.size + ' wallets</span></div>'
          + (n.pattern ? '<span style="' + M + '; font-size:var(--t-micro); letter-spacing:.1em; color:' + musterFarbe(n.pattern) + '; border:1px solid var(--line-1); border-radius:var(--r-control); padding:var(--sp-1) var(--sp-3)">' + esc(String(n.pattern).toUpperCase()) + '</span>' : '')
          + '</div>'
          + '<div style="font-size:var(--t-small); color:var(--ink-3); margin-top:var(--sp-3); line-height:1.45">' + esc(n.story) + '</div>'
          + (mitglieder.length
            ? '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:.12em; color:var(--ink-3); margin-top:var(--sp-4)">WHO</div>'
              + '<div style="display:flex; gap:var(--sp-2); flex-wrap:wrap; margin-top:var(--sp-2)">'
              + mitglieder.map((mm) => '<span ' + T.act(() => T.openWallet(mm.kurz, mm.wallet)) + ' class="hv-edge-strong" style="' + M + '; font-size:var(--t-micro); color:var(--ink-1); border:1px solid var(--line-1); border-radius:var(--r-control); padding:var(--sp-2) var(--sp-3); cursor:pointer" title="open this wallet">' + esc(mm.kurz) + '</span>').join('')
              + (rest > 0 ? '<span style="' + M + '; font-size:var(--t-micro); color:var(--ink-4); padding:var(--sp-2) var(--sp-1)">+ ' + rest + ' more</span>' : '')
              + '</div>'
            : '')
          + (maerkte.length
            ? '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:.12em; color:var(--ink-3); margin-top:var(--sp-4)">WHERE THEY MET</div>'
              + '<div style="margin-top:var(--sp-2); display:grid; gap:var(--sp-2)">'
              + maerkte.map((mk) => '<div style="display:flex; gap:var(--sp-4); align-items:baseline; font-size:var(--t-small)">'
                + '<span style="color:var(--ink-2); min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; flex:1" title="' + esc(mk.title) + '">' + esc(mk.title) + '</span>'
                + '<span style="' + M + '; font-size:var(--t-small); white-space:nowrap">' + esc(mk.label || '') + '</span></div>').join('')
              + '</div>'
            : '')
          + '<div style="display:flex; gap:var(--sp-6); margin-top:var(--sp-4)">'
          + '<div><div style="' + M + '; font-size:var(--t-micro); letter-spacing:.12em; color:var(--ink-3)">SHARED MARKETS</div><div style="' + M + '; font-size:var(--t-body); margin-top:var(--sp-2)">' + esc(n.shared) + '</div></div>'
          + '<div><div style="' + M + '; font-size:var(--t-micro); letter-spacing:.12em; color:var(--ink-3)">PAIRED NOTIONAL</div><div style="' + M + '; font-size:var(--t-body); margin-top:var(--sp-2)">' + esc(n.notional) + '</div></div>'
          + '</div></div>';
      }).join('')
      + '</div></div>';
  }

  return '<div>'
    + '<div style="padding:var(--sp-6) var(--sp-6) var(--sp-5); border-bottom:1px solid var(--line-2)">'
    // No "Check real account ages" toggle: /api/risk takes no such parameter,
    // so the switch flipped a colour and changed nothing.
    + '<div style="display:flex; align-items:flex-end; justify-content:space-between; gap:var(--sp-6)">'
    + '<div><div style="' + M + '; font-size:var(--t-micro); letter-spacing:.18em; color:var(--warn)">RISK SCREEN</div>'
    + '<h1 style="font-size:var(--t-head); line-height:1.25; margin:var(--sp-3) 0 0; font-weight:600; letter-spacing:-0.01em">Trades that look like someone knew</h1></div>'
    + (live && live.as_of ? '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-4)">as of ' + esc(String(live.as_of)) + '</div>' : '')
    + '</div>'
    // Der Satz zur Beweiskraft eines Flags stand hier und noch einmal in
    // api_views.risk_payload; beide lesen jetzt screen_not_proof.
    + caveatZeile('screen_not_proof', {
      nachsatz: 'Sports odds, crypto &amp; market prices, and weather are excluded: game results, exchange prices and weather models cannot be traded on early.',
      stil: 'font-size:var(--t-body); color:var(--ink-3); margin-top:var(--sp-4); max-width:760px; line-height:1.5'
    })
    // Was die Zahl ist, bevor die Baender sie benennen. Der stehende
    // Vorbehalt kommt aus dem Register (insider_score_unvalidated), der Satz
    // davor beschreibt die Rechnung und gehoert dieser Seite.
    + '<div style="font-size:var(--t-body); color:var(--ink-3); margin-top:var(--sp-3); max-width:760px; line-height:1.5">'
    + '<span style="' + M + '; font-size:var(--t-micro); letter-spacing:.08em; color:var(--ink-2)">'
    + esc(String((live && live.score_name) || 'flow-pattern score').toUpperCase()) + ' · 0–100</span> '
    + esc(basisSatz(live)) + ' '
    + caveat('insider_score_unvalidated')
    // Und dann: was STATTDESSEN gemessen wird, mit dem Weg dorthin. Ein
    // Vorbehalt, der nur sagt, was fehlt, laesst den Leser ohne Anhalt; der
    // Flag-Log misst eine andere Groesse (folgte der Preis der geflaggten
    // Seite?) und tut es mit n und Intervall.
    + ' ' + esc(gemessenSatz(live))
    + '</div>'
    + '<div style="display:flex; gap:var(--sp-3); margin-top:var(--sp-4); flex-wrap:wrap">'
    + bandChips(live)
    + '</div></div>'

    + trichter

    + (laedt
      ? '<div style="display:flex; align-items:center; gap:var(--sp-4); padding:var(--sp-4) var(--sp-6); border-bottom:1px solid var(--line-2); background:var(--panel)">'
        + '<span style="width:7px; height:7px; border-radius:50%; background:var(--warn); display:inline-block"></span>'
        + '<span style="' + M + '; font-size:var(--t-micro); letter-spacing:.08em; color:var(--warn)">building the day\'s tape, ~90 s on a cold cache</span>'
        + '<span style="' + M + '; font-size:var(--t-micro); color:var(--ink-3)">/api/risk pages a day of prints and looks up market categories; the second visit is instant</span></div>'
      : (T.herkunft.risks && T.herkunft.risks.quelle === 'fehler' && T.neuLaden
        // A failed or rate-limited request can be asked again from here;
        // nothing re-asks on its own. /api/risk shares its rate limit with
        // the backtester, so a 429 usually means "a few backtests just ran".
        ? '<div style="display:flex; align-items:center; gap:var(--sp-4); padding:var(--sp-4) var(--sp-6); border-bottom:1px solid var(--line-2); background:var(--panel)">'
          + '<span style="' + M + '; font-size:var(--t-micro); color:var(--neg-soft)">' + esc(risikoSatz) + '</span>'
          + '<div ' + T.act(() => T.neuLaden('risk', 'risk')) + ' class="hv-edge-strong" style="' + M + '; font-size:var(--t-micro); color:var(--ink-2); border:1px solid var(--line-1); border-radius:var(--r-control); padding:var(--sp-2) var(--sp-4); cursor:pointer; white-space:nowrap">Try again</div></div>'
        : ''))
    + '<div style="display:flex; gap:var(--sp-3); padding:var(--sp-5) var(--sp-6) 0; flex-wrap:wrap">'
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
        color: 'var(--ink-4)', priceLabel: '—', changeLabel: '—',
        changeStyle: M + '; font-size:var(--t-body); text-align:right; color:var(--ink-3)',
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
    + '<div style="padding:var(--sp-6) var(--sp-6) var(--sp-5); border-bottom:1px solid var(--line-2)">'
    + '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:.18em; color:var(--accent)">TRACKED</div>'
    + '<h1 style="font-size:var(--t-head); line-height:1.25; margin:var(--sp-3) 0 0; font-weight:600; letter-spacing:-0.01em">Your wallets and your watchlist</h1></div>'
    + '<div style="padding:var(--sp-5) var(--sp-6); border-bottom:1px solid var(--line-2)">'
    + '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:.14em; color:var(--ink-4); margin-bottom:var(--sp-4)">WALLETS YOU FOLLOW</div>'
    + (cards.length ? '<div style="display:grid; grid-template-columns:repeat(3,1fr); gap:var(--sp-5)">'
    + cards.map((w) => {
      const gradeStyle = M + '; font-size:var(--t-small); border-radius:var(--r-control); padding:var(--sp-1) var(--sp-3); ' + (w.grade === 'A' || w.grade === 'A+' ? 'color:var(--on-accent); background:var(--accent)' : w.grade === '—' ? 'color:var(--ink-3); border:1px solid var(--line-1)' : 'color:var(--warn); border:1px solid rgba(var(--warn-rgb),.35)');
      const pnlText = typeof w.pnlRaw === 'number' && T.liveData.track ? (w.pnlRaw >= 0 ? '+' : '-') + money(Math.abs(w.pnlRaw)) : w.pnl;
      const pnlStyle = M + '; font-size:var(--t-body); margin-top:var(--sp-2); color:' + (String(pnlText).charAt(0) === '+' ? 'var(--pos)' : String(pnlText).charAt(0) === '-' ? 'var(--neg)' : 'var(--ink-4)');
      return '<div ' + T.act(() => T.openWallet(w.openAs)) + ' class="hv-edge" style="background:var(--panel); border:1px solid var(--line-2); border-radius:var(--r-panel); padding:var(--sp-5); cursor:pointer">'
        + '<div style="display:flex; align-items:center; justify-content:space-between">'
        + '<div style="font-size:var(--t-lead)">' + esc(w.name) + '</div>'
        + '<div style="' + gradeStyle + '">' + esc(w.grade) + '</div></div>'
        + '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-3); margin-top:var(--sp-2)">' + esc(w.wallet) + '</div>'
        + '<div style="display:flex; gap:var(--sp-6); margin-top:var(--sp-5)">'
        + '<div><div style="' + M + '; font-size:var(--t-micro); letter-spacing:.12em; color:var(--ink-3)">' + (w.pnlLabel || '30D PROFIT') + '</div><div style="' + pnlStyle + '">' + esc(String(pnlText)) + '</div></div>'
        + '<div><div style="' + M + '; font-size:var(--t-micro); letter-spacing:.12em; color:var(--ink-3)">LAST TRADE</div><div style="' + M + '; font-size:var(--t-body); margin-top:var(--sp-2)">' + esc(w.last) + '</div></div>'
        + '</div></div>';
    }).join('')
    + '</div>' : '<div style="' + M + '; font-size:var(--t-small); color:var(--ink-3); padding:var(--sp-5) 0">No followed wallets reported by /api/track — the list lives in data/followed_wallets.json on the machine that runs the API, and this page only reads it.</div>')
    + '</div>'
    + '<div style="padding:var(--sp-5) var(--sp-6)">'
    + '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:.14em; color:var(--ink-4); margin-bottom:var(--sp-4)">MARKETS ON YOUR WATCHLIST</div>'
    + (watch.length ? '' : '<div style="' + M + '; font-size:var(--t-small); color:var(--ink-3); padding:var(--sp-3) 0">'
      + esc(herkunftSatz(T.liveData.track ? { quelle: T.liveData.track._quelle === 'fehler' ? 'fehler' : 'leer', fehler: T.liveData.track._fehler } : null, '/api/track')) + '</div>')
    + watch.map((m) =>
      '<div ' + m.act + ' class="hv-panel" style="display:grid; grid-template-columns:1fr 88px 96px 108px; align-items:center; padding:var(--sp-4) 0; border-bottom:1px solid var(--line-3); cursor:pointer">'
      + '<div><div style="font-size:var(--t-body)">' + esc(m.title) + '</div>'
      + '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-3); margin-top:var(--sp-2)">' + esc(m.meta) + '</div></div>'
      + '<div style="' + M + '; font-size:var(--t-lead); text-align:right">' + m.priceLabel + '</div>'
      + '<div style="' + m.changeStyle + '">' + m.changeLabel + '</div>'
      + '<div style="' + M + '; font-size:var(--t-small); text-align:right; color:var(--ink-4)">' + esc(m.ends) + '</div></div>'
    ).join('')
    + '</div></div>';
}
