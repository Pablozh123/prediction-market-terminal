// Backtester, Copy trade, Portfolio — ported from the design reference.
// The backtester renders live results from POST /api/backtest when available,
// otherwise an honest empty state. No panel here falls back to a fixture:
// every figure comes from the API or the cell shows that it does not.

import { esc, num, leerZeile, seriesDomain, seriesGrid } from '../util.js';
import { caveatZeile } from '../claims.js';
import { histogramm, kurzGeld } from '../charts.js';
import { trackWatchRows } from './trader_pages.js';
import { MONO as M, LABEL_BLOCK, LABEL, kpi } from '../ui.js';

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
    kopf = 'running… ' + (s.btElapsed || 0) + ' s';
    text = 'Loading the wallet\'s trades and resolutions, then replaying them. The first run on a wallet and window pages the public activity feed (up to 30,000 rows, about a minute on a hyperactive wallet); every later run on the same wallet and window reuses that data for ten minutes and answers in seconds.';
  } else if (err === 'rate-limited') {
    kopf = 'rate-limited';
    text = 'The public API allows a few backtests per minute per address. Retry in ' + (s.btRetryIn > 0 ? s.btRetryIn + ' s' : 'a moment') + '.';
  } else if (err) {
    kopf = 'The run did not answer';
    text = esc(err);
  }
  return '<div style="background:var(--panel); border:1px solid var(--line-2); border-radius:var(--r-panel); padding:var(--sp-6); margin-top:var(--sp-5); max-width:760px">'
    + '<div style="font-size:var(--t-lead); font-weight:600; color:' + (running ? 'var(--warn)' : err ? 'var(--neg-soft)' : 'var(--text)') + '">' + kopf + '</div>'
    + '<div style="font-size:var(--t-body); color:var(--ink-4); margin-top:var(--sp-4); line-height:var(--lh-prose)">' + text + '</div>'
    + '<div style="font-size:var(--t-small); color:var(--ink-3); margin-top:var(--sp-4); line-height:var(--lh-prose)">'
    + 'Nothing is estimated here. This panel used to fill itself from a generator when the '
    + 'backend was silent, which produced an equity curve that responded to every slider and '
    + 'meant nothing.'
    + '</div></div>';
}

// One line above the results: running / rate-limited / error / stale, or
// nothing when the shown result matches the current settings.
function laufStatusHtml(s, hatErgebnis) {
  if (s.btRun === 'running') {
    return '<div style="display:flex; align-items:center; gap:var(--sp-3); margin-top:var(--sp-3); ' + M + '; font-size:var(--t-micro); color:var(--warn)">'
      + '<span style="width:7px; height:7px; border-radius:50%; background:var(--warn); display:inline-block"></span>running… ' + (s.btElapsed || 0) + ' s'
      + (hatErgebnis ? ' <span style="color:var(--ink-3)">— the last result stays below until the new one lands</span>' : '') + '</div>';
  }
  if (s.btRun === 'error' && s.btError === 'rate-limited') {
    return '<div style="margin-top:var(--sp-3); ' + M + '; font-size:var(--t-micro); color:var(--warn)">rate-limited, retry in ' + (s.btRetryIn > 0 ? s.btRetryIn + ' s' : 'a moment')
      + (hatErgebnis ? ' <span style="color:var(--ink-3)">— the last result is kept below</span>' : '') + '</div>';
  }
  if (s.btRun === 'error' && s.btError) {
    return '<div style="margin-top:var(--sp-3); ' + M + '; font-size:var(--t-micro); color:var(--neg-soft)">' + esc(s.btError) + (hatErgebnis ? ' <span style="color:var(--ink-3)">— the last result is kept below</span>' : '') + '</div>';
  }
  if (hatErgebnis && s.btDirty) {
    return '<div style="margin-top:var(--sp-3); ' + M + '; font-size:var(--t-micro); color:var(--ink-4)">settings changed since this run — press RUN to refresh</div>';
  }
  return '';
}

// ---------------------------------------------------------------- backtester
// Verteilung der Trade-Ergebnisse plus die Konzentrationszeile.
//
// Sechs Statistikkarten und eine Equity-Kurve sagen, wie der Lauf endete.
// Die Frage, die ein Backtest aufwirft, beantwortet keine davon: traegt das
// Ergebnis eine Reihe von Trades oder tragen es drei? Eine Kurve, die aus
// drei Treffern besteht, sieht aus wie eine Kurve.
//
// Einheit ist Dollar je geschlossener Kopie, nicht Prozent und nicht Cent.
// Die Nulllinie steht als Referenz im Bild, denn das Vorzeichen ist hier die
// Aussage. Das Muster der Konzentrationszeile gibt es schon auf der
// Wallet-Seite (PROFIT CONCENTRATION), es liest sich hier genauso.
export function tradeVerteilung(live) {
  const v = live && live.trade_pnl ? live.trade_pnl : null;
  if (!v || !Array.isArray(v.bins) || !v.n) return '';
  const bins = v.bins
    .filter((b) => b && typeof b.von === 'number' && typeof b.bis === 'number')
    .map((b) => ({ von: b.von, bis: b.bis, anzahl: +b.anzahl || 0 }));
  if (!bins.length) return '';
  const anteil = v.top3_share != null ? Math.round(v.top3_share * 100) : null;
  const konzentration = anteil != null
    ? 'The three largest winners carry ' + anteil + '% of the gross profit ('
      + kurzGeld(v.top3) + ' of ' + kurzGeld(v.gross_win) + ' across ' + num(v.winners) + ' winning copies). '
    : 'No copy closed in profit, so there is no profit to concentrate. ';
  return histogramm({
    titel: 'RESULT PER CLOSED COPY',
    hinweis: num(v.n) + ' closed copies',
    xLabel: 'result per closed copy (USD)',
    yLabel: 'closed copies',
    bins,
    referenzen: [{ wert: 0, label: 'break even' }],
    xTickText: (x) => kurzGeld(x, true),
    zaehlEinheit: 'copies',
    hoehe: 180,
    // backtest_modeled steht im Kopf des Backtesters und gilt dem ganzen
    // Lauf, nicht nur diesem Bild. Hier stand er als zweite, handgeschriebene
    // Fassung desselben Satzes; jetzt steht er einmal, aus dem Register.
    fussnote: konzentration + 'Best ' + kurzGeld(v.best, true) + ', worst ' + kurzGeld(v.worst, true) + '.'
  });
}

function equityDomain(bankroll, ...serien) {
  const alle = [];
  serien.forEach((serie) => (serie || []).forEach((v) => { if (typeof v === 'number' && v === v) alle.push(v); }));
  if (!alle.length) return null;
  const basis = typeof bankroll === 'number' && bankroll > 0 ? bankroll : alle[0];
  const rand = basis * 0.1;
  let min = Math.min(basis - rand, ...alle);
  let max = Math.max(basis + rand, ...alle);
  const luft = (max - min) * 0.05;
  min -= luft; max += luft;
  if (min === max) max = min + 1;
  return { min, max };
}

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
  // Nenner der Trefferquote: entschiedene POSITIONEN, nicht Ausstiegszeilen
  // und erst recht nicht alle kopierten Zeilen. closed_trades zaehlte lange
  // jeden Teilverkauf einzeln: eine in drei Tranchen abgebaute Position
  // stand dreifach in Zaehler und Nenner. decided_trades sind die Positionen
  // mit einem Ergebnis, flat_trades die, die genau ihre Kosten zurueckgaben.
  const closedN = st ? (+st.closed_trades || 0) : null;
  const decidedN = st ? (+st.decided_trades || 0) : null;
  const flatN = st ? (+st.flat_trades || 0) : 0;
  const skippedN = st ? +st.skipped_trades : null;
  const winsN = st ? +st.wins : null;
  const lossesN = st ? +st.losses : null;
  const feesPaid = st ? +st.fees_paid : null;
  const openValue = st ? +st.open_value : null;
  const ddPct = st ? Math.abs(+st.max_drawdown) * 100 : null;
  // Equity und Benchmark auf einer Skala mit Nullpunkt: getrennt skaliert
  // endete ein Benchmark 40 Prozent unter der Wallet auf derselben Hoehe.
  // Skala um die Bankroll herum, mindestens zehn Prozent nach beiden
  // Seiten, weiter nur, wenn die Kurven es verlangen. Mit der Null im Bild
  // war ein Lauf von plus fuenf Prozent eine Gerade; ohne Mindestspanne
  // fuellte ein halbes Prozent Rauschen die ganze Hoehe. Beide Serien
  // teilen sich die Skala, die Startlinie steht als Referenz im Bild.
  const eqDom = st ? equityDomain(bank, live.equity, live.benchmark) : null;
  const equityPts = st && live.equity && live.equity.length > 1
    ? T.seriesPoints(live.equity, 900, 270, eqDom) : '';
  const benchPts = st && live.benchmark && live.benchmark.length > 1
    ? T.seriesPoints(live.benchmark, 900, 270, eqDom) : '';
  const eqGrid = seriesGrid(eqDom, 900, 270, (v) => kurzGeld(v));
  // Startlinie: die Bankroll als Referenz, damit ueber und unter Wasser
  // ablesbar ist, ohne dass die Null im Bild sein muss.
  const startY = eqDom ? (270 - 10 - ((bank - eqDom.min) / (eqDom.max - eqDom.min || 1)) * (270 - 30)) : null;
  const startLinie = startY !== null
    ? '<line x1="0" y1="' + startY.toFixed(1) + '" x2="900" y2="' + startY.toFixed(1) + '" style="stroke:rgba(var(--ink),.35)" stroke-dasharray="2 4" vector-effect="non-scaling-stroke" />'
      + '<text x="896" y="' + (startY - 4).toFixed(1) + '" text-anchor="end" style="fill:var(--ink-3)" font-size="10" font-family="IBM Plex Mono, monospace">start ' + esc(kurzGeld(bank)) + '</text>'
    : '';
  // Drawdown ist ein Anteil vom Hoch, 0 bis -1: die Skala reicht von null
  // bis zum tiefsten Punkt, nicht vom tiefsten bis zum hoechsten Wert.
  const ddDom = st && live.drawdown && live.drawdown.length > 1 ? seriesDomain(live.drawdown) : null;
  const ddPts = ddDom ? T.seriesPoints(live.drawdown, 900, 220, ddDom) : '';
  const ddGrid = seriesGrid(ddDom, 900, 220, (v) => (v * 100).toFixed(0) + '%');

  const simVariants = (live && live.variants ? live.variants.map((v) => ({
    name: v.name, eq: +v.final_equity, roi: +v.roi * 100, dd: Math.abs(+v.max_drawdown) * 100,
    wr: +v.win_rate * 100, closed: +v.closed_trades || 0, decided: +v.decided_trades || 0,
    copied: +v.copied_trades, skipped: +v.skipped_trades
  })) : []).sort((a, b) => b.eq - a.eq);
  const bestVariant = simVariants[0] || null;

  // Achsen aus der Kurve selbst: bei einem abgeschnittenen Fenster beginnt
  // sie an der Datenkante (Stundenaufloesung), nicht am angefragten Starttag.
  const curveVon = live && live.curve_start ? live.curve_start.replace('T', ' ') + ' UTC' : s.btWindow + 'd ago';
  const curveMitte = live && live.curve_start ? '' : Math.round(s.btWindow / 2) + 'd ago';
  // Gemessene Skip-Gruende aus der Engine; null solange kein Lauf da ist.
  const reasons = st && st.skip_reasons ? st.skip_reasons : null;
  const reasonText = reasons ? [
    reasons.out_of_cash ? num(reasons.out_of_cash) + ' out of cash' : '',
    reasons.exposure_cap ? num(reasons.exposure_cap) + ' at the exposure cap (' + s.btExposure + '%)' : '',
    reasons.no_position ? num(reasons.no_position) + ' sells of positions never held' : '',
    reasons.bad_data ? num(reasons.bad_data) + ' unusable rows' : '',
    reasons.other ? num(reasons.other) + ' other' : ''
  ].filter(Boolean).join(' · ') : '';
  const bankrollBound = reasons ? (reasons.out_of_cash + reasons.exposure_cap) : 0;
  const filteredN = st ? +st.filtered_trades || 0 : 0;
  // Gemessene Filter-Gruende aus der Engine: Schwelle, fremder Verkauf,
  // Nachkauf in eine Position, die schon mit vollem Einsatz laeuft.
  const filterReasons = st && st.filter_reasons ? st.filter_reasons : null;
  const filterText = filterReasons ? [
    filterReasons.already_following ? num(filterReasons.already_following) + ' adds to positions already held at the full stake' : '',
    filterReasons.below_threshold ? num(filterReasons.below_threshold) + ' entries below the follow threshold' : '',
    filterReasons.sell_not_followed ? num(filterReasons.sell_not_followed) + ' sells of positions never followed' : '',
    filterReasons.other ? num(filterReasons.other) + ' other' : ''
  ].filter(Boolean).join(' · ') : '';
  // Auto-Fit-Ergebnis der Engine: entweder eine Folge-Schwelle (den
  // groessten Einstiegen der Wallet beim eingestellten Einsatz folgen)
  // oder ein geschrumpfter Einsatz (allem folgen, kleiner kopieren).
  const autoFit = st && st.auto_fit ? st.auto_fit : null;
  const autoFitText = autoFit && autoFit.applied
    ? (autoFit.mode === 'threshold'
      ? 'auto-fit: following the wallet\'s ' + num(autoFit.followed_positions) + ' largest entries (≥ $' + num(Math.round(+autoFit.follow_threshold)) + ') at $' + (+autoFit.stake).toFixed(2) + ' per copy'
      : 'auto-fit $' + (+autoFit.stake).toFixed(2) + ' per copy (wallet peaks at ' + num(autoFit.peak_concurrent) + ' open positions)')
      + (autoFit.hindsight ? ', chosen with hindsight' : '')
    : '';

  const shortWallet = s.btWallet.trim().length > 12 ? s.btWallet.trim().slice(0, 6) + '…' + s.btWallet.trim().slice(-4) : s.btWallet.trim();
  const gebuehrText = s.btFeeModel === 'flat' ? 'fees ' + s.btFee + ' bps flat' : 'fees on the venue curve';
  const runMeta = (s.btStrategy === 'copy' ? 'Copy' : 'Fade') + ' · last ' + s.btWindow + ' days · wallet ' + shortWallet + ' · ' + SIZING[s.btSizing]
    + (autoFitText ? ' · ' + autoFitText : '') + ' · ' + gebuehrText + ' · slippage ' + s.btSlip + ' bps'
    + (live && live.stats && live.stats.window_truncated
      ? ' · window truncated at the engine\'s trade cap' + (live.stats.effective_start ? ' — data reaches back to ' + live.stats.effective_start : '')
      : '')
    // "Match trader %": woran die Anteile haengen. Die Kasse kommt vom
    // Polygon-RPC; ist sie nicht lesbar, steht das dran.
    + (live && live.trader_portfolio
      ? ' · trader portfolio $' + num(Math.round(+live.trader_portfolio.total))
        + (live.trader_portfolio.cash_read ? ' (open positions + cash)' : ' (open positions only, cash not readable)')
      : '')
    // Bewertungskurve: wie viele Positionen unterwegs zum Marktpreis
    // stehen. Ohne Verlauf laeuft eine gehaltene Position als Gerade.
    + (st && st.mark_to_market && st.mark_to_market.positions_total
      ? ' · open copies marked to market ' + (st.mark_to_market.interval === '1d' ? 'daily' : st.mark_to_market.interval === '6h' ? 'every 6 hours' : 'hourly')
        + ' for ' + num(st.mark_to_market.positions_marked) + ' of ' + num(st.mark_to_market.positions_total) + ' positions'
        + (st.mark_to_market.positions_marked < st.mark_to_market.positions_total ? ' (the rest at cost until they close)' : '')
      : '')
    // Woher die Zahlen kommen und wie frisch: die Trades des Fensters
    // werden je Wallet und Fenster zehn Minuten wiederverwendet.
    + (live && live.data_loaded_at
      ? ' · ' + num(live.data_rows || 0) + ' trades loaded ' + String(live.data_loaded_at).replace('T', ' ').replace('Z', ' UTC') + ', reused for 10 min'
      : '')
    + (s.btRun === 'done' && s.btElapsed ? ' · answered in ' + s.btElapsed + ' s' : '');

  // Ohne Lauf keine Kacheln: jede dieser Zahlen kaeme sonst aus dem Nichts.
  const verteilungChart = st ? tradeVerteilung(live) : '';
  const statCards = st ? [
    { label: 'FINAL EQUITY', value: '$' + finalEq.toFixed(0), sub: (ret >= 0 ? '+' : '') + ret.toFixed(1) + '% ROI', pos: ret >= 0 },
    // Der Untertitel nennt den noch offenen Teil, sobald es einen gibt:
    // Positionen in Maerkten, die am Fensterende nicht entschieden waren,
    // stecken zum letzten Preis in dieser Zahl.
    { label: 'TOTAL P&L', value: (totalPnl >= 0 ? '+' : '-') + '$' + Math.abs(totalPnl).toFixed(0),
      sub: (st.unrealized_pnl != null && Math.abs(+st.unrealized_pnl) >= 0.5)
        ? (+st.unrealized_pnl >= 0 ? '+' : '-') + '$' + Math.abs(+st.unrealized_pnl).toFixed(0) + ' of it still unresolved'
        : (benchPnl === null ? 'no benchmark' : (totalPnl - benchPnl >= 0 ? '+' : '-') + '$' + Math.abs(totalPnl - benchPnl).toFixed(0) + ' vs flat-bet'),
      pos: totalPnl >= 0 },
    // n dazu: ohne die Zahl der entschiedenen Positionen sagt die Quote
    // nicht, wie viel sie wiegt: 3 von 4 und 300 von 400 lesen sich sonst
    // gleich. Positionen, die genau ihre Kosten zurueckgaben, stehen daneben
    // statt den Nenner zu fuellen.
    { label: 'WIN RATE', value: decidedN ? Math.round((winsN / decidedN) * 100) + '%' : '—',
      sub: decidedN
        ? winsN + 'W / ' + lossesN + 'L of ' + num(decidedN) + ' decided positions'
          + (flatN ? ' · ' + num(flatN) + ' back at cost' : '')
        : (closedN ? num(closedN) + ' closed, none decided' : 'no position closed yet'), pos: null },
    { label: 'MAX DRAWDOWN', value: ddPct.toFixed(1) + '%', sub: 'from the running peak', pos: false },
    { label: 'TRADES COPIED', value: num(copied), sub: num(Math.max(0, skippedN)) + ' skipped' + (filteredN ? ' · ' + num(filteredN) + ' filtered' : ''), pos: null },
    { label: 'FEES PAID', value: '$' + feesPaid.toFixed(2), sub: '$' + openValue.toFixed(0) + ' still open', pos: null }
  ] : [];

  const stakeLabel = s.btSizing === 'pct' ? 'STAKE (% OF BANKROLL)' : s.btSizing === 'match' ? "MULTIPLIER (× TRADER'S SHARE)" : s.btSizing === 'kelly' ? 'ASSUMED EDGE (PROBABILITY POINTS)' : 'STAKE PER COPY ($)';
  const stakeHint = s.btSizing === 'pct' ? 'Each copy bets ' + s.btStakePct.toFixed(1) + '% of your bankroll — about $' + (bank * s.btStakePct / 100).toFixed(0) + ' right now.'
    : s.btSizing === 'match' ? 'If the trader puts 2% of their portfolio into a bet, you put 2% × ' + s.btStakeMult.toFixed(1) + ' of yours, add for add. Their portfolio size is read at run time: open positions at market value plus USDC cash.'
    : s.btSizing === 'kelly' ? 'Assumes every entry is worth its price plus ' + s.btStakeKelly.toFixed(1) + ' points, then stakes quarter-Kelly of equity. Conservative on purpose — the edge is an assumption.'
    : 'Every followed position gets exactly $' + s.btStakeFixed + ' at entry. When the wallet adds to a position you already hold, the copy is only topped back up after a partial exit; the add is otherwise logged as filtered. Capped at $' + s.btCap + ' per position.';

  // Weder erfundene Trades noch eine erfundene Vergleichs-Wallet. Hier lagen
  // acht ausgedachte Log-Zeilen, fuenf ausgedachte offene Positionen und eine
  // Vergleichstabelle, die die Gegenseite als Vielfaches der eigenen Zahlen
  // berechnete (Endkapital mal 0.88, PnL mal 0.72, Trefferquote fest 51).
  // Ohne Backend gibt es davon nichts zu zeigen.
  // Das Log zeigt, was die Engine getan hat; bewusst nicht gefolgte
  // Zeilen ("filtered", bei aktiven Wallets Zehntausende) kommen als
  // Stichprobe hinter einem Schalter, sonst verdraengten sie jeden Trade.
  const logFiltered = live && Array.isArray(live.log_filtered) ? live.log_filtered : [];
  const logQuelle = (live && live.log ? live.log : []).concat(s.btShowFiltered ? logFiltered : [])
    .sort((a, b) => String(b.time || '').localeCompare(String(a.time || '')));
  const logRows = logQuelle.map((l) => ({
    time: l.time, action: l.action, status: l.status, market: l.market, side: l.side, note: l.note || '',
    pnl: l.realized_pnl == null ? '' : (l.realized_pnl >= 0 ? '+' : '-') + '$' + Math.abs(+l.realized_pnl).toFixed(2),
    traderAmt: '$' + num(Math.round(+l.trader_amt || 0)),
    stake: +l.stake ? '$' + (+l.stake).toFixed(2) : '—',
    fill: +l.fill ? (+l.fill).toFixed(3) : '—',
    fee: +l.fee ? '$' + (+l.fee).toFixed(2) : '—',
    // Kein Kontostand, kein Kontostand: eine Zeile ohne laufende
    // Equity (Abrechnung am Fensterrand) druckte hier $0.00.
    equity: l.equity == null ? '—' : '$' + (+l.equity).toFixed(2)
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

  // Zahlenfeld mit Minus/Plus UND freier Eingabe: die Knopfschritte
  // (500 Dollar Bankroll, 5 Dollar Einsatz) waren die einzige Bedienung,
  // und wer 1.250 Dollar oder 12 Dollar meinte, kam nie dorthin. Tippen
  // setzt den Zustand ohne Neuzeichnen, der naechste RUN liest ihn.
  const numFeld = (label, key, value, o) => {
    const step = o.step || 1, min = o.min == null ? -Infinity : o.min, max = o.max == null ? Infinity : o.max;
    const rund = (v) => Math.round(Math.min(max, Math.max(min, v)) * 100) / 100;
    const patch = (v) => { const p = {}; p[key] = rund(v); return p; };
    const knopf = (zeichen, ziel) => '<div ' + T.act(bt(T, ziel)) + ' class="hv-edge-max hv-white" role="button" aria-label="' + esc(label + ' ' + (zeichen === '+' ? 'up' : 'down')) + '" style="width:28px; height:32px; flex:none; border:1px solid var(--line-1); border-radius:var(--r-control); display:flex; align-items:center; justify-content:center; ' + M + '; font-size:var(--t-body); color:var(--ink-2); cursor:pointer">' + zeichen + '</div>';
    const tippen = T.inp((e) => {
      const v = parseFloat(e.target.value);
      if (!isFinite(v)) return;
      T.state[key] = rund(v);
      if (T.liveData.backtest) T.state.btDirty = true;
    }, key);
    return '<div><div style="' + LABEL_BLOCK + '">' + label + '</div>'
      + '<div style="display:flex; align-items:center; gap:var(--sp-3)">'
      + knopf('−', patch(value - step))
      + '<div style="flex:1; min-width:0; display:flex; align-items:center; background:var(--panel); border:1px solid var(--line-1); border-radius:var(--r-control)">'
      + (o.prefix ? '<span style="padding-left:var(--sp-3); ' + M + '; font-size:var(--t-small); color:var(--ink-3)">' + esc(o.prefix) + '</span>' : '')
      + '<input type="number" inputmode="decimal" value="' + esc(String(value)) + '" step="' + step + '"' + (isFinite(min) ? ' min="' + min + '"' : '') + (isFinite(max) ? ' max="' + max + '"' : '')
      + ' ' + tippen + ' aria-label="' + esc(label) + '" style="flex:1; width:100%; min-width:0; background:transparent; border:0; outline:none; padding:var(--sp-3) var(--sp-2); ' + M + '; font-size:var(--t-small); color:var(--text); text-align:center" />'
      + (o.unit ? '<span style="padding-right:var(--sp-3); ' + M + '; font-size:var(--t-small); color:var(--ink-3)">' + esc(o.unit) + '</span>' : '')
      + '</div>'
      + knopf('+', patch(value + step))
      + '</div></div>';
  };

  const btTabs = [
    T.tab('Trade log', s.btTab === 'log', { btTab: 'log' }),
    T.tab('Open positions', s.btTab === 'open', { btTab: 'open' }),
    T.tab('Drawdown', s.btTab === 'dd', { btTab: 'dd' })
  ].join('');

  let tabBody = '';
  if (s.btTab === 'log') {
    const logKopf = '<div style="display:flex; align-items:center; justify-content:space-between; gap:var(--sp-4); flex-wrap:wrap; padding:var(--sp-3) var(--sp-5); background:var(--panel); border-bottom:1px solid var(--line-2); ' + M + '; font-size:var(--t-micro); color:var(--ink-3)">'
      + '<span>' + (live && live.log_total != null ? num(live.log_total) + ' engine actions, newest ' + num((live.log || []).length) + ' shown' : num(logRows.length) + ' rows')
      + (live && live.log_filtered_total ? ' · ' + num(live.log_filtered_total) + ' filtered (not followed on purpose)' : '') + '</span>'
      + (logFiltered.length
        ? '<span ' + T.act(() => T.setState({ btShowFiltered: !s.btShowFiltered })) + ' style="cursor:pointer; color:var(--accent)">' + (s.btShowFiltered ? 'hide the filtered sample' : 'show a sample of ' + num(logFiltered.length) + ' filtered rows') + '</span>'
        : '')
      + '</div>';
    tabBody = '<div style="border:1px solid var(--line-2); border-radius:var(--r-panel); margin-top:var(--sp-4); overflow:clip">'
      + logKopf
      + '<div role="table" aria-label="Backtest trades">'
      + '<div role="row" style="display:grid; grid-template-columns:88px 74px 84px 1fr 60px 84px 78px 74px 84px 88px; gap:var(--sp-4); padding:var(--sp-3) var(--sp-5); background:var(--panel); position:sticky; top:0; z-index:3; border-bottom:1px solid var(--line-2); ' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:var(--ink-3)">'
      + '<div role="columnheader">TIME</div><div role="columnheader">ACTION</div><div role="columnheader">STATUS</div><div role="columnheader">MARKET</div><div role="columnheader">SIDE</div><div role="columnheader" style="text-align:right">TRADER $</div><div role="columnheader" style="text-align:right">STAKE</div><div role="columnheader" style="text-align:right">FILL</div><div role="columnheader" style="text-align:right">RESULT</div><div role="columnheader" style="text-align:right">EQUITY</div></div>'
      + (logRows.length ? '' : leerZeile('No engine action in this window: nothing was copied, skipped or settled.'))
      + logRows.map((l) =>
        '<div role="row" style="display:grid; grid-template-columns:88px 74px 84px 1fr 60px 84px 78px 74px 84px 88px; gap:var(--sp-4); align-items:center; padding:var(--sp-4) var(--sp-5); border-bottom:1px solid var(--line-3); ' + M + '; font-size:var(--t-small)' + (l.status === 'filtered' ? '; opacity:.6' : '') + '">'
        + '<div role="cell" style="color:var(--ink-4)">' + esc(l.time) + '</div>'
        + '<div role="cell" style="' + M + '; font-size:var(--t-small); color:' + (l.action === 'BUY' ? 'var(--pos)' : l.action === 'RESOLVE' ? 'var(--info)' : 'var(--neg)') + '">' + esc(l.action) + '</div>'
        + '<div role="cell"><span title="' + esc(l.note) + '" style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps); border-radius:var(--r-control); padding:var(--sp-1) var(--sp-3); ' + (l.status === 'skipped' ? 'color:var(--warn); border:1px solid rgba(var(--warn-rgb),.35)' : 'color:var(--ink-2); border:1px solid var(--line-1)') + '">' + esc(l.status) + '</span></div>'
        + '<div role="cell" style="font-family:var(--font-ui); font-size:var(--t-small); white-space:nowrap; overflow:hidden; text-overflow:ellipsis">' + esc(l.market) + '</div>'
        + '<div role="cell" style="color:var(--ink-3)">' + esc(l.side) + '</div>'
        + '<div role="cell" style="text-align:right; color:var(--ink-4)">' + esc(l.traderAmt) + '</div>'
        + '<div role="cell" style="text-align:right">' + esc(l.stake) + '</div>'
        + '<div role="cell" style="text-align:right; color:var(--ink-3)">' + esc(l.fill) + '</div>'
        + '<div role="cell" style="text-align:right; color:' + (l.pnl ? (l.pnl.charAt(0) === '+' ? 'var(--pos)' : 'var(--neg)') : 'var(--ink-4)') + '">' + esc(l.pnl || l.fee) + '</div>'
        + '<div role="cell" style="text-align:right">' + esc(l.equity) + '</div></div>'
      ).join('')
      + '</div>'
      // Der Knopf "Export trade log CSV" stand hier ohne Handler. Ein Knopf,
      // der nichts tut, ist eine Behauptung ueber eine Funktion.
      + '</div>';
  } else if (s.btTab === 'open') {
    tabBody = '<div role="table" aria-label="Backtest open positions" style="border:1px solid var(--line-2); border-radius:var(--r-panel); margin-top:var(--sp-4); overflow:clip">'
      + '<div role="row" style="display:grid; grid-template-columns:1fr 62px 78px 78px 78px 88px 88px 100px; gap:var(--sp-4); padding:var(--sp-3) var(--sp-5); background:var(--panel); position:sticky; top:0; z-index:3; border-bottom:1px solid var(--line-2); ' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:var(--ink-3)">'
      + '<div role="columnheader">MARKET</div><div role="columnheader">SIDE</div><div role="columnheader" style="text-align:right">SHARES</div><div role="columnheader" style="text-align:right">AVG FILL</div><div role="columnheader" style="text-align:right">MARK</div><div role="columnheader" style="text-align:right">COST</div><div role="columnheader" style="text-align:right">VALUE</div><div role="columnheader" style="text-align:right">UNREALISED</div></div>'
      + openRows.map((o) =>
        '<div role="row" style="display:grid; grid-template-columns:1fr 62px 78px 78px 78px 88px 88px 100px; gap:var(--sp-4); align-items:center; padding:var(--sp-4) var(--sp-5); border-bottom:1px solid var(--line-3); ' + M + '; font-size:var(--t-small)">'
        + '<div role="cell" style="font-family:var(--font-ui); font-size:var(--t-small); white-space:nowrap; overflow:hidden; text-overflow:ellipsis">' + esc(o.market) + '</div>'
        + '<div role="cell" style="' + M + '; font-size:var(--t-small); color:' + (o.side === 'Yes' ? 'var(--accent)' : 'var(--info)') + '">' + esc(o.side) + '</div>'
        + '<div role="cell" style="text-align:right; color:var(--ink-3)">' + o.shares + '</div>'
        + '<div role="cell" style="text-align:right; color:var(--ink-3)">' + o.avg + '</div>'
        + '<div role="cell" style="text-align:right">' + o.mark + '</div>'
        + '<div role="cell" style="text-align:right; color:var(--ink-3)">' + o.cost + '</div>'
        + '<div role="cell" style="text-align:right">' + o.value + '</div>'
        + '<div role="cell" style="text-align:right; ' + M + '; font-size:var(--t-small); color:' + (o.pnlPos ? 'var(--pos)' : 'var(--neg)') + '">' + o.pnl + '</div></div>'
      ).join('')
      + '</div>';
  } else if (s.btTab === 'dd') {
    tabBody = '<div style="background:var(--panel); border:1px solid var(--line-2); border-radius:var(--r-panel); margin-top:var(--sp-4); padding:var(--sp-5)">'
      + '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:var(--ink-4); margin-bottom:var(--sp-4)">DRAWDOWN FROM THE RUNNING PEAK</div>'
      + '<svg width="100%" height="220" viewBox="0 0 900 220" preserveAspectRatio="none" role="img" aria-label="Drawdown from the running peak">'
      + ddGrid
      + '<polyline points="' + ddPts + '" fill="none" style="stroke:var(--neg)" stroke-width="2" vector-effect="non-scaling-stroke" /></svg>'
      + '<div style="display:flex; justify-content:space-between; ' + M + '; font-size:var(--t-micro); color:var(--ink-3); margin-top:var(--sp-3)">'
      + '<span>' + esc(curveVon) + '</span><span>worst: ' + (ddPct === null ? '—' : ddPct.toFixed(1) + '%') + '</span><span>today</span></div></div>';
  }

  const advChevron = M + '; font-size:var(--t-lead); color:var(--ink-4); transition:transform .18s ease; transform:rotate(' + (s.advancedOpen ? '90deg' : '0deg') + ')';
  const simChevron = M + '; font-size:var(--t-lead); color:var(--ink-4); transition:transform .18s ease; transform:rotate(' + (s.sizingSimOpen ? '90deg' : '0deg') + ')';

  return '<div>'
    + '<div style="padding:var(--sp-6) var(--sp-6) var(--sp-5); border-bottom:1px solid var(--line-2)">'
    + '<div style="display:flex; align-items:flex-end; justify-content:space-between; gap:var(--sp-6)">'
    + '<div><div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-max); color:var(--accent)">BACKTESTER · PAPER SIM</div>'
    + '<h1 style="font-size:var(--t-head); line-height:var(--lh-tight); margin:var(--sp-3) 0 0; font-weight:600; letter-spacing:var(--ls-flat)">Replay a wallet with your own sizing</h1>'
    // backtest_modeled stand im Register und auf keiner Seite: die Kopfzeile
    // beschrieb die Simulation, sagte aber nirgends, dass ihre Zahlen
    // modelliert und nicht realisiert sind.
    + caveatZeile('backtest_modeled', {
      vorsatz: 'Every simulated fill is priced with fees and slippage, up to a year back. Long windows on very active wallets stop at the engine\'s cap of 30,000 trades; the run line says where the data really starts.',
      stil: 'font-size:var(--t-body); color:var(--ink-4); margin-top:var(--sp-3); max-width:680px; line-height:var(--lh-snug)'
    }) + '</div>'
    + '<div style="' + M + '; font-size:var(--t-micro); color:var(--on-accent); background:var(--accent); border-radius:var(--r-control); padding:var(--sp-2) var(--sp-4)">POLYMARKET</div>'
    + '</div></div>'

    + '<div style="display:grid; grid-template-columns:352px 1fr">'
    + '<div style="border-right:1px solid var(--line-2); padding:var(--sp-5) var(--sp-6); display:flex; flex-direction:column; gap:var(--sp-6)">'

    + '<div><div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:var(--accent); margin-bottom:var(--sp-3)">01 · WALLET TO REPLAY</div>'
    + '<input value="' + esc(s.btWallet) + '" ' + T.inp((e) => { T.state.btWallet = e.target.value; if (T.liveData.backtest) T.state.btDirty = true; }, 'btWallet') + ' aria-label="Wallet address to replay" placeholder="0x…" style="width:100%; box-sizing:border-box; background:var(--panel); border:1px solid var(--line-edge); border-radius:var(--r-control); padding:var(--sp-4); ' + M + '; font-size:var(--t-small); color:var(--text)" />'
    + '<div style="font-size:var(--t-small); color:var(--ink-3); margin-top:var(--sp-3); line-height:var(--lh-snug)">Any public Polymarket address — the default is one with a long public trade history, chosen so a first run has something to replay. Take one from the leaderboard to compare.</div></div>'

    + '<div><div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:var(--accent); margin-bottom:var(--sp-3)">02 · STAKE PER COPY</div>'
    + '<div style="display:grid; grid-template-columns:1fr 1fr; gap:var(--sp-3)">'
    + Object.keys(SIZING).map((k) =>
      '<div ' + T.act(bt(T, { btSizing: k })) + ' style="font-size:var(--t-small); text-align:center; border-radius:var(--r-control); padding:var(--sp-3); cursor:pointer; ' + (s.btSizing === k ? 'color:var(--on-accent); background:var(--accent); font-weight:600' : 'color:var(--ink-3); border:1px solid var(--line-1)') + '">' + SIZING[k] + '</div>'
    ).join('')
    + '</div>'
    + '<div style="margin-top:var(--sp-4)">'
    + (s.btSizing === 'pct' ? numFeld(stakeLabel, 'btStakePct', s.btStakePct, { step: 0.5, min: 0.1, max: 100, unit: '%' })
      : s.btSizing === 'match' ? numFeld(stakeLabel, 'btStakeMult', s.btStakeMult, { step: 0.5, min: 0.1, max: 10, prefix: '×' })
      : s.btSizing === 'kelly' ? numFeld(stakeLabel, 'btStakeKelly', s.btStakeKelly, { step: 0.5, min: 0.5, max: 30, unit: 'pts' })
      : numFeld(stakeLabel, 'btStakeFixed', s.btStakeFixed, { step: 5, min: 1, prefix: '$' }))
    + '<div style="font-size:var(--t-small); color:var(--ink-3); margin-top:var(--sp-3); line-height:var(--lh-snug)">' + stakeHint + '</div></div>'
    // Auto-Fit: die Engine misst die Hoechstzahl gleichzeitig offener
    // Quell-Positionen und passt den Einsatz je Copy so an, dass Bankroll
    // und Exposure-Deckel dem Tempo der Wallet folgen koennen. Nur bei
    // Fixed $ und % of bankroll — die anderen Modi dimensionieren selbst.
    + (s.btSizing === 'fixed' || s.btSizing === 'pct'
      ? '<div style="margin-top:var(--sp-4)"><div style="' + LABEL_BLOCK + '">AUTO-FIT STAKE TO THE WALLET\'S PACE</div>'
        + '<div style="display:flex; gap:var(--sp-3)">'
        + T.opt('Auto-fit on', !!s.btAutoFit, bt(T, { btAutoFit: true }))
        + T.opt('Manual stake', !s.btAutoFit, bt(T, { btAutoFit: false }))
        + '</div>'
        + '<div style="font-size:var(--t-small); color:var(--ink-3); margin-top:var(--sp-3); line-height:var(--lh-snug)">'
        + (s.btAutoFit
          ? 'The engine measures how many positions the wallet holds at once (sells and resolutions free a slot again) and sizes each copy so the bankroll is used at that peak: it raises the stake when the flow fits with room to spare, follows only the wallet\'s largest entries when it does not fit at your stake (smaller ones are marked "filtered", not failed), and shrinks the stake when no threshold separates them. What was applied is named in the result.'
          : 'The stake above is used as set. If the wallet\'s pace outruns it, the result names the skipped share and what auto-fit would do.')
        + '</div>'
        + (!s.btAutoFit
          ? '<div style="margin-top:var(--sp-4)">' + numFeld('MIN TRADE TO COPY ($, 0 = ALL)', 'btMinNotional', s.btMinNotional, { step: 25, min: 0, prefix: '$' }) + '</div>'
          : '')
        + '</div>'
      : '')
    + '<div style="display:grid; grid-template-columns:1fr 1fr; gap:var(--sp-4); margin-top:var(--sp-5)">'
    + numFeld('CAP PER POSITION', 'btCap', s.btCap, { step: 50, min: 10, prefix: '$' })
    + numFeld('MAX BANKROLL IN OPEN COPIES', 'btExposure', s.btExposure, { step: 5, min: 5, max: 100, unit: '%' })
    + '</div>'
    + '<div style="font-size:var(--t-small); color:var(--ink-3); margin-top:var(--sp-3); line-height:var(--lh-snug)">New copies are skipped while open copies already tie up that share of the bankroll. Cash recycles during the window: a mirrored sell and every market that resolves (won or lost) pays out at its own time and is available for the next copy.</div></div>'

    + '<div><div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:var(--accent); margin-bottom:var(--sp-3)">03 · TIME WINDOW</div>'
    + '<div style="display:flex; gap:var(--sp-3)">'
    + [7, 30, 90, 180, 365].map((d) => T.tab(d === 365 ? '1y' : d + 'd', s.btWindow === d, bt(T, { btWindow: d }))).join('')
    + '</div></div>'

    + '<div><div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:var(--accent); margin-bottom:var(--sp-3)">04 · STRATEGY</div>'
    + '<div style="display:flex; gap:var(--sp-3)">'
    + [T.tab('Copy', s.btStrategy === 'copy', bt(T, { btStrategy: 'copy' })), T.tab('Fade', s.btStrategy === 'fade', bt(T, { btStrategy: 'fade' }))].join('')
    + '</div>'
    + '<div style="font-size:var(--t-small); color:var(--ink-3); margin-top:var(--sp-3); line-height:var(--lh-snug)">' + (s.btStrategy === 'copy' ? 'Mirror every trade the wallet makes, at the same price.' : 'Fade takes the opposite side of every trade the wallet makes.') + '</div></div>'

    + '<div style="border:1px solid var(--line-2); border-radius:var(--r-panel); overflow:hidden">'
    + '<div ' + T.act(() => T.setState({ advancedOpen: !s.advancedOpen })) + ' class="hv-el" style="display:flex; align-items:center; justify-content:space-between; padding:var(--sp-4) var(--sp-5); background:var(--panel); cursor:pointer">'
    + '<div style="font-size:var(--t-body)">Advanced settings</div><div style="' + advChevron + '">›</div></div>'
    + (s.advancedOpen ?
      '<div style="padding:var(--sp-5); display:flex; flex-direction:column; gap:var(--sp-4)">'
      + numFeld('BANKROLL', 'btBankroll', s.btBankroll, { step: 500, min: 100, prefix: '$' })
      + '<div style="display:grid; grid-template-columns:1fr 1fr; gap:var(--sp-4)">'
      + numFeld('SLIPPAGE (BPS)', 'btSlip', s.btSlip, { step: 5, min: 0, unit: 'bps' })
      + '<div><div style="' + LABEL_BLOCK + '">FEE MODEL</div>'
      + '<div style="display:flex; gap:var(--sp-3); margin-top:var(--sp-3)">'
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
        ? '<div style="display:flex; flex-direction:column; gap:var(--sp-3)">'
          + numFeld('FLAT FEE (BPS)', 'btFee', s.btFee, { step: 5, min: 0, unit: 'bps' })
          + '<div style="font-size:var(--t-micro); color:var(--warn); line-height:var(--lh-snug)">'
          + 'A flat rate cannot match the venue: Polymarket charges about 250 bps at a price of 0.50 '
          + 'and about 50 bps at 0.90. Anything near 20 bps understates the real cost by a wide margin.'
          + '</div></div>'
        : '<div style="font-size:var(--t-small); color:var(--ink-3); line-height:var(--lh-snug)">'
          + 'Polymarket charges the taker fee on the variance of the price, so it peaks in the middle '
          + 'of the book: about 250 bps at 0.50 and about 50 bps at 0.90, at the general category rate. '
          + 'The model lives in app/venue_fees.py and the general rate applies, because a wallet history '
          + 'carries no category.'
          + '</div>')
      + '<div><div style="' + LABEL_BLOCK + '">BENCHMARK</div>'
      + '<div style="font-size:var(--t-small); color:var(--ink-3); margin-top:var(--sp-3); line-height:var(--lh-snug)">The dashed line in the results is the same trades at a constant 2% of the starting bankroll per copy. The compare-wallet field was removed: the server never read it, and the table it fed derived the other wallet from ours by fixed multipliers.</div></div>'
      + '</div>' : '')
    + '</div>'

    // The only thing that starts a run. While one runs the button is inert
    // and says so; after a 429 it says how long to wait.
    + (s.btRun === 'running'
      ? '<div style="font-size:var(--t-body); font-weight:600; text-align:center; color:var(--ink-4); border:1px solid var(--line-1); border-radius:var(--r-control); padding:var(--sp-4); cursor:default">running… ' + (s.btElapsed || 0) + ' s</div>'
      : s.btRun === 'error' && s.btError === 'rate-limited' && s.btRetryIn > 0
        ? '<div style="font-size:var(--t-body); font-weight:600; text-align:center; color:var(--warn); border:1px solid rgba(var(--warn-rgb),.4); border-radius:var(--r-control); padding:var(--sp-4); cursor:default">rate-limited · retry in ' + s.btRetryIn + ' s</div>'
        : '<div ' + T.act(() => { T.setState({ btTab: 'log' }); T.runBacktest(); }) + ' class="hv-accentbg" style="font-size:var(--t-body); font-weight:600; text-align:center; color:var(--on-accent); background:var(--accent); border-radius:var(--r-control); padding:var(--sp-4); cursor:pointer">RUN backtest →</div>')
    + '</div>'

    + '<div style="padding:var(--sp-5) var(--sp-6)">'
    + '<div style="' + M + '; font-size:var(--t-small); color:var(--ink-3)">' + esc(runMeta) + '</div>'
    // Without a result the empty block below carries the run state itself.
    + (st ? laufStatusHtml(s, true) : '')
    + (st ? ''

    + '<div style="display:grid; grid-template-columns:repeat(3,1fr); gap:var(--sp-4); margin-top:var(--sp-5)">'
    + statCards.map((c) => kpi({
      label: c.label, wert: c.value, sub: c.sub,
      farbe: c.pos === true ? 'var(--pos)' : c.pos === false ? 'var(--neg)' : 'var(--text)'
    })).join('')
    + '</div>'
    // Direkt unter den Kacheln: dieselbe Menge geschlossener Kopien, aber
    // als Verteilung statt als Quote. Ohne sie steht nicht da, ob das
    // Ergebnis von drei Trades getragen wird.
    + (verteilungChart ? '<div style="margin-top:var(--sp-4); max-width:700px">' + verteilungChart + '</div>' : '')

    // Keine erfundene Aufteilung der Skips mehr: hier stand 60 Prozent
    // Exposure-Deckel, 30 Prozent Kasse leer, 10 Prozent fremde Verkaeufe —
    // drei feste Anteile, die die Engine nie gemeldet hat. Der Grund je Zeile
    // steht im Trade log; hier nur die gemessene Summe.
    + (skippedN > copied ? '<div style="border:1px solid rgba(var(--warn-rgb),.3); background:rgba(var(--warn-rgb),.07); border-radius:var(--r-panel); padding:var(--sp-4) var(--sp-5); margin-top:var(--sp-4); font-size:var(--t-small); color:var(--warn); line-height:var(--lh-snug)">More skipped than copied: ' + num(skippedN) + ' of the wallet\'s trades were not mirrored'
      + (reasonText ? ' — ' + reasonText : '')
      + '.'
      + (bankrollBound > skippedN / 2
        ? (autoFit && autoFit.applied
          // Auto-Fit lief bereits: die verbleibenden Skips sind der Teil
          // des Flows, den diese Bankroll grundsaetzlich nicht halten kann.
          ? ' Auto-fit ' + (autoFit.mode === 'threshold'
            ? 'already narrowed the follow set to the wallet\'s ' + num(autoFit.followed_positions) + ' largest entries'
            : 'already sized each copy down to $' + (+autoFit.stake).toFixed(2))
            + ', but the wallet peaks at ' + num(autoFit.peak_concurrent) + ' open positions — the remaining skips are the flow beyond what $' + num(s.btBankroll) + ' can hold. Only a larger bankroll follows this wallet fully.'
          : ' The bankroll cannot follow this wallet\'s pace at this stake: with $' + num(s.btBankroll) + ' and about $' + Math.round(stake) + ' per copy, at most ' + Math.max(1, Math.floor(bank * s.btExposure / 100 / Math.max(1, stake))) + ' copies can be open at once.'
            + (s.btSizing === 'match' || s.btSizing === 'kelly'
              ? ' This sizing scales with the wallet, add for add, so the cap and the bankroll are the only levers: raise the exposure cap, lower the ' + (s.btSizing === 'match' ? 'multiplier' : 'assumed edge') + ', or raise the bankroll.'
              : autoFit && autoFit.stake != null
              ? ' Auto-fit would follow the wallet\'s largest entries at your stake (it measured a peak of ' + num(autoFit.peak_concurrent) + ' open positions) — switch it on next to the stake and re-run.'
              : ' Lower the stake, raise the bankroll, or raise the exposure cap to copy more of the flow.'))
        : ' The trade log below marks each one.')
      + '</div>' : '')

    // Gefilterte Trades sind eine bewusste Auswahl, kein Versagen — eine
    // neutrale Zeile statt einer Warnung.
    + (filteredN > 0 ? '<div style="border:1px solid var(--line-2); border-radius:var(--r-panel); padding:var(--sp-4) var(--sp-5); margin-top:var(--sp-4); font-size:var(--t-small); color:var(--ink-3); line-height:var(--lh-snug)">'
      + num(filteredN) + ' of the wallet\'s trades were deliberately not followed ("filtered" in the trade log)'
      + (filterText ? ': ' + filterText + '.' : '.')
      + (autoFit && autoFit.applied && autoFit.mode === 'threshold'
        ? ' The $' + num(Math.round(+autoFit.follow_threshold)) + ' threshold is the one auto-fit chose so the followed flow fits the bankroll.'
        : (s.btMinNotional > 0 ? ' The follow threshold is your $' + num(s.btMinNotional) + '.' : ''))
      + (filterReasons && filterReasons.already_following
        ? ' The stake is per position: the first entry gets it, later adds by the wallet are not topped up unless a partial exit made room.'
        : '')
      + '</div>' : '')

    // Auto-Fit liest das ganze Fenster, bevor der erste Trade kopiert wird.
    // Das gehoert neben das Ergebnis, nicht in eine Fussnote.
    + (autoFit && autoFit.hindsight && autoFit.note
      ? '<div style="border:1px solid rgba(var(--warn-rgb),.3); background:rgba(var(--warn-rgb),.07); border-radius:var(--r-panel); padding:var(--sp-4) var(--sp-5); margin-top:var(--sp-4); font-size:var(--t-small); color:var(--warn); line-height:var(--lh-snug)">'
        + esc(autoFit.note) + '</div>'
      : '')

    + '<div style="background:var(--panel); border:1px solid var(--line-2); border-radius:var(--r-panel); margin-top:var(--sp-5); padding:var(--sp-5)">'
    + '<div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:var(--sp-4); flex-wrap:wrap; gap:var(--sp-4)">'
    + '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:var(--ink-4)">EQUITY CURVE</div>'
    + '<div style="display:flex; gap:var(--sp-5); ' + M + '; font-size:var(--t-micro); flex-wrap:wrap">'
    + '<span style="display:flex; align-items:center; gap:var(--sp-3)"><span style="width:14px; height:2px; background:var(--accent); display:inline-block"></span>' + esc(shortWallet) + '</span>'
    + '<span style="display:flex; align-items:center; gap:var(--sp-3); color:var(--ink-4)"><span style="width:14px; height:2px; background:var(--muted); display:inline-block"></span>Flat-bet benchmark</span>'
    + (s.sizingSimOpen && bestVariant ? '<span style="display:flex; align-items:center; gap:var(--sp-3); color:var(--warn)"><span style="width:14px; height:2px; background:var(--warn); display:inline-block"></span>Highest final equity: ' + esc(bestVariant.name) + '</span>' : '')
    + '</div></div>'
    + '<svg width="100%" height="270" viewBox="0 0 900 270" preserveAspectRatio="none" role="img" aria-label="Equity for the replayed wallet against the flat-bet benchmark, one dollar scale around the starting bankroll">'
    + eqGrid
    + startLinie
    + '<polyline points="' + benchPts + '" fill="none" style="stroke:var(--muted)" stroke-width="1.4" stroke-dasharray="6 4" vector-effect="non-scaling-stroke" />'
        + '<polyline points="' + equityPts + '" fill="none" style="stroke:' + (ret >= 0 ? 'var(--pos)' : 'var(--neg)') + '" stroke-width="2" vector-effect="non-scaling-stroke" />'
    + '</svg>'
    + '<div style="display:flex; justify-content:space-between; ' + M + '; font-size:var(--t-micro); color:var(--ink-3); margin-top:var(--sp-3)">'
    + '<span>' + esc(curveVon) + '</span><span>' + esc(curveMitte) + '</span><span>today</span></div></div>'

    + '<div style="display:flex; gap:var(--sp-3); margin-top:var(--sp-5)">' + btTabs + '</div>'
    + tabBody

    + '<div style="border:1px solid var(--line-2); border-radius:var(--r-panel); margin-top:var(--sp-5); overflow:clip">'
    + '<div ' + T.act(() => { T.setState({ sizingSimOpen: !s.sizingSimOpen, btDirty: !s.sizingSimOpen && !(live && live.variants) ? true : s.btDirty }); }) + ' class="hv-el" style="display:flex; align-items:center; justify-content:space-between; padding:var(--sp-4) var(--sp-5); background:var(--panel); cursor:pointer">'
    + '<div style="font-size:var(--t-body)">Which sizing would have ended this window with the most equity?</div><div style="' + simChevron + '">›</div></div>'
    + (s.sizingSimOpen && !bestVariant
      ? '<div style="padding:var(--sp-5); ' + M + '; font-size:var(--t-micro); color:var(--ink-4)">The variants are computed with the run — press RUN with this section open to include them.</div>'
      : '')
    + (s.sizingSimOpen && bestVariant ?
      '<div style="padding:var(--sp-5)">'
      + caveatZeile('backtest_modeled', {
        vorsatz: 'Replays the same window once per sizing rule, with identical fees, slippage, cap and exposure limit. Only the stake rule changes. The rule that ends with the most equity is drawn into the chart above as the dotted amber line; leading in this window is a fact about this window.',
        stil: 'font-size:var(--t-small); color:var(--ink-4); line-height:var(--lh-snug)'
      })
      + '<div style="font-size:var(--t-body); margin-top:var(--sp-4)">Highest final equity in this window: <strong style="color:var(--warn)">' + esc(bestVariant.name) + '</strong> → $' + bestVariant.eq.toFixed(0) + ' final equity (' + (bestVariant.roi >= 0 ? '+' : '') + bestVariant.roi.toFixed(1) + '% ROI)</div>'
      + '<div role="table" aria-label="Sizing rules compared" style="border:1px solid var(--line-2); border-radius:var(--r-panel); margin-top:var(--sp-5); overflow:clip">'
      + '<div role="row" style="display:grid; grid-template-columns:1fr 110px 96px 96px 96px 88px 88px; gap:var(--sp-4); padding:var(--sp-3) var(--sp-5); background:var(--panel); position:sticky; top:0; z-index:3; border-bottom:1px solid var(--line-2); ' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:var(--ink-3)">'
      + '<div role="columnheader">SIZING RULE</div><div role="columnheader" style="text-align:right">FINAL EQUITY</div><div role="columnheader" style="text-align:right">ROI</div><div role="columnheader" style="text-align:right">MAX DD</div><div role="columnheader" style="text-align:right">WIN RATE</div><div role="columnheader" style="text-align:right">COPIED</div><div role="columnheader" style="text-align:right">SKIPPED</div></div>'
      + simVariants.map((v, i) =>
        '<div role="row" style="display:grid; grid-template-columns:1fr 110px 96px 96px 96px 88px 88px; gap:var(--sp-4); align-items:center; padding:var(--sp-4) var(--sp-5); border-bottom:1px solid var(--line-3); background:' + (i === 0 ? 'rgba(var(--warn-rgb),.07)' : 'transparent') + '">'
        + '<div role="cell" style="font-size:var(--t-small); color:' + (i === 0 ? 'var(--warn)' : 'var(--text)') + '">' + esc(v.name) + '</div>'
        + '<div role="cell" style="text-align:right; ' + M + '; font-size:var(--t-small)">$' + v.eq.toFixed(0) + '</div>'
        + '<div role="cell" style="text-align:right; ' + M + '; font-size:var(--t-small); color:' + (v.roi >= 0 ? 'var(--pos)' : 'var(--neg)') + '">' + (v.roi >= 0 ? '+' : '') + v.roi.toFixed(1) + '%</div>'
        + '<div role="cell" style="text-align:right; ' + M + '; font-size:var(--t-small); color:var(--ink-3)">' + v.dd.toFixed(1) + '%</div>'
        + '<div role="cell" style="text-align:right; ' + M + '; font-size:var(--t-small); color:var(--ink-3)">' + (v.decided ? Math.round(v.wr) + '% <span style="font-size:var(--t-micro); color:var(--ink-4)">n ' + num(v.decided) + '</span>' : '—') + '</div>'
        + '<div role="cell" style="text-align:right; ' + M + '; font-size:var(--t-small); color:var(--ink-3)">' + num(v.copied) + '</div>'
        + '<div role="cell" style="text-align:right; ' + M + '; font-size:var(--t-small); color:var(--ink-3)">' + num(Math.max(0, v.skipped)) + '</div></div>'
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
    + '<div style="padding:var(--sp-6) var(--sp-6) var(--sp-5); border-bottom:1px solid var(--line-2)">'
    + '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-max); color:var(--accent)">' + kicker + '</div>'
    + '<h1 style="font-size:var(--t-head); line-height:var(--lh-tight); margin:var(--sp-3) 0 0; font-weight:600; letter-spacing:var(--ls-flat)">' + titel + '</h1></div>'
    + '<div style="padding:var(--sp-6)">'
    + '<div style="background:var(--panel); border:1px solid var(--line-2); border-radius:var(--r-panel); padding:var(--sp-6); max-width:760px">'
    + '<div style="font-size:var(--t-lead); font-weight:600">Nothing to show</div>'
    + '<div style="font-size:var(--t-body); color:var(--ink-4); margin-top:var(--sp-4); line-height:var(--lh-prose)">' + grund + '</div>'
    + '<div style="font-size:var(--t-small); color:var(--ink-3); margin-top:var(--sp-4); line-height:var(--lh-prose)">'
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
  const portDom = live && live.equity_curve && live.equity_curve.length > 1 ? seriesDomain(live.equity_curve) : null;
  const equityPts = portDom ? T.seriesPoints(live.equity_curve, 900, 220, portDom) : '';
  const portGrid = seriesGrid(portDom, 900, 220, (v) => kurzGeld(v));
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
      + '<div style="padding:var(--sp-5) var(--sp-6) 0; display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:var(--sp-5)">'
      + '<div><div style="' + LABEL_BLOCK + '">SEARCH</div><input value="' + esc(s.portQuery) + '" ' + T.inp((e) => T.setState({ portQuery: e.target.value }), 'portQuery') + ' placeholder="market or wallet…" style="width:100%; box-sizing:border-box; background:var(--panel); border:1px solid var(--line-edge); border-radius:var(--r-control); padding:var(--sp-3) var(--sp-4); ' + M + '; font-size:var(--t-small); color:var(--text)" /></div>'
      + '<div><div style="' + LABEL_BLOCK + '">SOURCE</div><div style="display:flex; gap:var(--sp-3); flex-wrap:wrap">'
      // Nur Quellen, die es gibt: jede Zeile hier stammt aus dem Copy-Buch,
      // ein "Research"-Filter fand nie eine Zeile.
      + [['all','All'],['copy','Copy trade']].map((o) => T.opt(o[1], s.portSource === o[0], { portSource: o[0] })).join('') + '</div></div>'
      + '<div><div style="' + LABEL_BLOCK + '">SIDE</div><div style="display:flex; gap:var(--sp-3); flex-wrap:wrap">'
      + [['all','All'],['YES','Yes'],['NO','No']].map((o) => T.opt(o[1], s.portSide === o[0], { portSide: o[0] })).join('') + '</div></div>'
      + '<div><div style="' + LABEL_BLOCK + '">SHOW</div><div style="display:flex; gap:var(--sp-3); flex-wrap:wrap">'
      + [['all','Everything'],['losers','Losing only']].map((o) => T.opt(o[1], (s.portLosers ? 'losers' : 'all') === o[0], { portLosers: o[0] === 'losers' })).join('') + '</div></div>'
      + '</div>'
      + '<div role="table" aria-label="Portfolio positions" style="border:1px solid var(--line-2); border-radius:var(--r-panel); margin:var(--sp-5) var(--sp-6); overflow:clip">'
      + '<div role="row" style="display:grid; grid-template-columns:1fr 76px 92px 92px 100px 100px; gap:var(--sp-4); padding:var(--sp-3) var(--sp-5); background:var(--panel); position:sticky; top:0; z-index:3; border-bottom:1px solid var(--line-2); ' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:var(--ink-3)">'
      + '<div role="columnheader">MARKET</div><div role="columnheader" style="text-align:right">SIDE</div><div role="columnheader" style="text-align:right">ENTRY</div><div role="columnheader" style="text-align:right">NOW</div><div role="columnheader" style="text-align:right">PROFIT</div><div role="columnheader" style="text-align:right">SOURCE</div></div>'
      + (rows.length ? '' : leerZeile(baseRows.length ? 'No position matches these filters.' : 'No open positions in the paper book reported by /api/copy.'))
      + rows.map((r) =>
        '<div role="row" style="display:grid; grid-template-columns:1fr 76px 92px 92px 100px 100px; gap:var(--sp-4); align-items:center; padding:var(--sp-4) var(--sp-5); border-bottom:1px solid var(--line-3)">'
        + r.map((v, i) => {
          const style = i === 0 ? "font-family:var(--font-ui); font-size:var(--t-small); white-space:nowrap; overflow:hidden; text-overflow:ellipsis" : M + '; font-size:var(--t-small); text-align:right; color:' + (i === 4 ? (v.charAt(0) === '+' ? 'var(--pos)' : 'var(--neg)') : i === 1 ? (v === 'YES' ? 'var(--pos)' : 'var(--info)') : 'var(--ink-2)');
          return '<div role="cell" style="' + style + '">' + esc(String(v)) + '</div>';
        }).join('')
        + '</div>'
      ).join('')
      + '</div></div>';
  } else if (s.portTab === 'copy') {
    body = '<div style="padding:var(--sp-5) var(--sp-6)">'
      + '<div style="display:grid; grid-template-columns:repeat(3,1fr); gap:var(--sp-4)">'
      + '<div style="background:var(--panel); border:1px solid var(--line-2); border-radius:var(--r-panel); padding:var(--sp-5)"><div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:var(--ink-3)">COPY EQUITY</div><div style="' + M + '; font-size:var(--t-head); margin-top:var(--sp-3)">$' + num((+kp.equity).toFixed(2)) + '</div></div>'
      + '<div style="background:var(--panel); border:1px solid var(--line-2); border-radius:var(--r-panel); padding:var(--sp-5)"><div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:var(--ink-3)">RESEARCH CASH</div><div style="' + M + '; font-size:var(--t-head); margin-top:var(--sp-3)">$' + (+kp.cash).toFixed(2) + '</div></div>'
      + '<div style="background:var(--panel); border:1px solid var(--line-2); border-radius:var(--r-panel); padding:var(--sp-5)"><div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:var(--ink-3)">EVERYTHING TOGETHER</div><div style="' + M + '; font-size:var(--t-head); margin-top:var(--sp-3); color:var(--accent)">$' + num(((+kp.equity) + (+kp.cash)).toFixed(2)) + '</div></div>'
      + '</div>'
      + '<div style="background:var(--panel); border:1px solid var(--line-2); border-radius:var(--r-panel); padding:var(--sp-5); margin-top:var(--sp-5)">'
      + '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:var(--ink-4); margin-bottom:var(--sp-4)">COMBINED EQUITY</div>'
      + '<svg width="100%" height="220" viewBox="0 0 900 220" preserveAspectRatio="none" role="img" aria-label="Combined equity">'
      + portGrid
      + '<polyline points="' + equityPts + '" fill="none" style="stroke:var(--accent)" stroke-width="2" vector-effect="non-scaling-stroke" /></svg></div>'
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
        label, value: '$' + value.toFixed(0), pct: Math.round(value / total * 100), color: i < 2 ? 'var(--accent)' : 'var(--info)'
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
    body = '<div style="padding:var(--sp-5) var(--sp-6); display:grid; grid-template-columns:1fr 1fr; gap:var(--sp-6)">'
      + '<div><div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:var(--ink-4); margin-bottom:var(--sp-5)">BY CATEGORY</div>'
      + '<div style="display:flex; flex-direction:column; gap:var(--sp-5)">'
      + (alloc.length ? '' : leerZeile(keinBuch))
      + alloc.map((a) =>
        '<div><div style="display:flex; justify-content:space-between; ' + M + '; font-size:var(--t-small); margin-bottom:var(--sp-3)"><span style="color:var(--ink-3)">' + a.label + '</span><span>' + a.value + '</span></div>'
        + '<div style="height:8px; background:rgba(var(--ink),.07); border-radius:2px"><div style="width:' + a.pct + '%; height:8px; background:' + a.color + '; border-radius:2px"></div></div></div>'
      ).join('')
      + '</div></div>'
      + '<div><div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:var(--ink-4); margin-bottom:var(--sp-5)">CONCENTRATION</div>'
      + '<div style="display:flex; flex-direction:column; gap:var(--sp-4)">'
      + (conc
        ? '<div style="display:flex; justify-content:space-between; font-size:var(--t-body)"><span style="color:var(--ink-2)">Biggest single position</span><span style="' + M + '">' + conc.biggest + '</span></div>'
        + '<div style="display:flex; justify-content:space-between; font-size:var(--t-body)"><span style="color:var(--ink-2)">Top three positions</span><span style="' + M + '">' + conc.top3 + '</span></div>'
        + '<div style="display:flex; justify-content:space-between; font-size:var(--t-body)"><span style="color:var(--ink-2)">Cash not deployed</span><span style="' + M + '">' + conc.cash + '</span></div>'
        // Hier standen $268 · 26%, $641 · 61%, $392 · 38% und $312 · 23% als
        // Rueckfall — vier Konzentrationswerte fuer ein Buch ohne Positionen.
        : leerZeile(keinBuch))
      + '</div></div></div>';
  } else if (s.portTab === 'history') {
    const histRows = liveHistRows || [];
    body = '<div role="table" aria-label="Portfolio history" style="border:1px solid var(--line-2); border-radius:var(--r-panel); margin:var(--sp-5) var(--sp-6); overflow:clip">'
      + '<div role="row" style="display:grid; grid-template-columns:110px 1fr 78px 92px 92px 100px; gap:var(--sp-4); padding:var(--sp-3) var(--sp-5); background:var(--panel); position:sticky; top:0; z-index:3; border-bottom:1px solid var(--line-2); ' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:var(--ink-3)">'
      + '<div role="columnheader">DATE</div><div role="columnheader">MARKET</div><div role="columnheader" style="text-align:right">SIDE</div><div role="columnheader" style="text-align:right">ENTRY</div><div role="columnheader" style="text-align:right">EXIT</div><div role="columnheader" style="text-align:right">RESULT</div></div>'
      + (histRows.length ? '' : leerZeile('No settled paper trades reported by /api/copy yet.'))
      + histRows.map((r) =>
        '<div role="row" style="display:grid; grid-template-columns:110px 1fr 78px 92px 92px 100px; gap:var(--sp-4); align-items:center; padding:var(--sp-4) var(--sp-5); border-bottom:1px solid var(--line-3)">'
        + r.map((v, i) => {
          const style = i === 1 ? "font-family:var(--font-ui); font-size:var(--t-small); white-space:nowrap; overflow:hidden; text-overflow:ellipsis" : M + '; font-size:var(--t-small); text-align:' + (i === 0 ? 'left' : 'right') + '; color:' + (i === 5 ? (v.charAt(0) === '+' ? 'var(--pos)' : 'var(--neg)') : i === 2 ? (v === 'YES' ? 'var(--pos)' : 'var(--info)') : 'var(--ink-2)');
          return '<div role="cell" style="' + style + '">' + esc(String(v)) + '</div>';
        }).join('')
        + '</div>'
      ).join('')
      + '</div>';
  } else {
    body = '<div style="padding:var(--sp-5) var(--sp-6)">'
      + watch.map((m) =>
        '<div ' + m.act + ' class="hv-panel" style="display:grid; grid-template-columns:1fr 88px 96px 108px; align-items:center; padding:var(--sp-4) 0; border-bottom:1px solid var(--line-3); cursor:pointer">'
        + '<div><div style="font-size:var(--t-body)">' + esc(m.title) + '</div>'
        + '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-3); margin-top:var(--sp-2)">' + esc(m.meta) + '</div></div>'
        + '<div style="' + M + '; font-size:var(--t-lead); text-align:right">' + m.priceLabel + '</div>'
        + '<div style="' + m.changeStyle + '">' + m.changeLabel + '</div>'
        + '<div style="' + M + '; font-size:var(--t-small); text-align:right; color:var(--ink-4)">' + esc(m.ends) + '</div></div>'
      ).join('')
      + '</div>';
  }

  return '<div>'
    + '<div style="padding:var(--sp-6) var(--sp-6) var(--sp-5); border-bottom:1px solid var(--line-2)">'
    + '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-max); color:var(--accent)">PORTFOLIO · PAPER</div>'
    + '<h1 style="font-size:var(--t-head); line-height:var(--lh-tight); margin:var(--sp-3) 0 0; font-weight:600; letter-spacing:var(--ls-flat)">What you would be holding</h1></div>'
    + '<div style="display:grid; grid-template-columns:repeat(4,1fr); border-bottom:1px solid var(--line-2)">'
    + '<div style="padding:var(--sp-5) var(--sp-6); border-right:1px solid var(--line-2)"><div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:var(--ink-3)">VALUE NOW</div><div style="' + M + '; font-size:var(--t-hero); margin-top:var(--sp-3)">' + (kp.equity != null ? '$' + num((+kp.equity).toFixed(2)) : '—') + '</div></div>'
    // Keine Rueckfallwerte in der Kennzahlenzeile: hier standen 14 offene
    // Positionen, +$28.60 unrealisiert und $312.40 freie Kasse, sobald das
    // Feld in der Antwort fehlte. Ein fehlendes Feld ist jetzt ein Strich —
    // seit eben auch bei VALUE NOW, das als einzige der vier Kacheln
    // ungeprueft rechnete und ohne das Feld "$NaN" schrieb.
    // Und das Vorzeichen des Unrealisierten kommt aus der Zahl, nicht aus dem
    // Template — vorher stand "+$" fest davor, in Gruen, auch bei Verlust.
    // Alle vier Betraege gehen durch num(): $1,000.00 neben $1000.00 in
    // derselben Zeile sind zwei Schreibweisen fuer dieselbe Zahl.
    + '<div style="padding:var(--sp-5) var(--sp-6); border-right:1px solid var(--line-2)"><div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:var(--ink-3)">OPEN POSITIONS</div><div style="' + M + '; font-size:var(--t-hero); margin-top:var(--sp-3)">' + (kp.open_positions != null ? num(kp.open_positions) : '—') + '</div></div>'
    + '<div style="padding:var(--sp-5) var(--sp-6); border-right:1px solid var(--line-2)"><div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:var(--ink-3)">UNREALISED</div><div style="' + M + '; font-size:var(--t-hero); margin-top:var(--sp-3); color:' + (kp.unrealized == null ? 'var(--ink-3)' : +kp.unrealized >= 0 ? 'var(--pos)' : 'var(--neg)') + '">' + (kp.unrealized != null ? (+kp.unrealized >= 0 ? '+' : '-') + '$' + num(Math.abs(+kp.unrealized).toFixed(2)) : '—') + '</div></div>'
    + '<div style="padding:var(--sp-5) var(--sp-6)"><div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:var(--ink-3)">CASH FREE</div><div style="' + M + '; font-size:var(--t-hero); margin-top:var(--sp-3)">' + (kp.cash != null ? '$' + num((+kp.cash).toFixed(2)) : '—') + '</div></div>'
    + '</div>'
    + '<div style="display:flex; gap:var(--sp-3); padding:var(--sp-5) var(--sp-6) 0; flex-wrap:wrap">' + portTabs + '</div>'
    + body
    + '</div>';
}
