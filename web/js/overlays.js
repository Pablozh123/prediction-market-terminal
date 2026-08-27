// Detail overlay (right panel) and command palette — ported from the reference.
// Wallet details show scorecard fields (n, CI, verdict, snapshot) when the API
// answered for that wallet; scores never render without their sample size.

import { esc, money, num } from './util.js';
import { scorePartsOf } from './pages/trader_pages.js';
import { isFullAddress } from './pages/wallet_page.js';

const M = "font-family:'IBM Plex Mono',monospace";
const STAT_VAL = M + '; font-size:19px; margin-top:5px';

export function renderDetail(T) {
  const d = T.state.detail;
  if (!d) return '';
  let v;
  if (d.kind === 'market') {
    const m = T.markets.find((x) => x.id === d.id);
    if (!m) return '';
    const hist = T.liveData.marketHistory && T.liveData.marketHistory[d.id];
    // Ohne Historie kein Diagramm. Hier lief ein Zufallspfad aus dem Preis
    // als Startwert unter der Ueberschrift YES PRICE · 24H.
    const c = { pts: hist ? T.seriesPoints(hist, 340, 150) : '' };
    v = {
      kicker: 'MARKET',
      accent: m.chg >= 0 ? '#69B47E' : '#D95F52',
      title: m.title,
      meta: m.venue + ' · ' + m.cat + ' · resolves ' + m.ends,
      chartLabel: 'YES PRICE · 24H',
      chartPoints: c.pts,
      chartEmpty: 'No price history loaded for this market — /api/market/<id>/history did not answer.',
      axisStart: '24h ago',
      listEmpty: 'No print of this market in the current tape window.',
      stats: [
        { label: 'YES', value: m.yes + '¢', style: STAT_VAL },
        { label: 'CHANGE 1D', value: (m.chg >= 0 ? '+' : '') + m.chg + '¢', style: STAT_VAL + '; color:' + (m.chg >= 0 ? '#69B47E' : '#D95F52') },
        { label: 'VOLUME 24H', value: money(m.vol), style: STAT_VAL },
        { label: 'LIQUIDITY', value: money(m.liq), style: STAT_VAL }
      ],
      listLabel: 'LARGEST PRINTS · 24H',
      // Nur Prints dieses Marktes. Vorher wurde die Liste mit den ersten vier
      // Zeilen des gesamten Tapes aufgefuellt, wenn der Markt keine hatte —
      // fremde Trades unter der Ueberschrift dieses Marktes.
      list: T.tape.filter((t) => t.market === m.title).slice(0, 4).map((t) => ({
        primary: t.wallet === '—' ? 'Anonymous (Kalshi)' : t.wallet,
        secondary: t.side + ' at ' + t.price + ' · ' + t.ago,
        value: money(t.size),
        style: M + '; font-size:13px; color:' + (t.side.indexOf('BUY') === 0 ? '#69B47E' : '#D95F52')
      })),
      // Keine Knoepfe: "Watch this market" hatte keinen Endpunkt (die
      // Watchlist wird nur gelesen), und "Open on <venue>" verlinkte auf die
      // Boerse — das Projekt setzt bewusst keine Venue-Links (Schweizer
      // Rechtslage). Ein Knopf ohne Wirkung waere schlimmer als keiner.
      primaryAction: '',
      note: ''
    };
  } else {
    // A leaderboard row by name, or any wallet by address (whale flow, risk
    // screen): the drawer works from whichever it has. Not on the loaded
    // leaderboard and without an address: a card from what the tape window
    // knows about this wallet, and nothing else.
    const t = T.traders.find((x) => x.name === d.id) || null;
    const tapePrints = T.tape.filter((x) => x.wallet === d.id);
    const nurTape = !t;
    const addr = String(d.addr || (t && t.walletFull) || (tapePrints.find((x) => x.walletAddress) || {}).walletAddress || '').toLowerCase();
    const shortAddr = addr ? addr.slice(0, 6) + '…' + addr.slice(-4) : '';
    const wd = T.liveData.walletDetail[d.id];
    // Die Gewinnkurve kommt aus /api/wallet oder es gibt keine. Der frühere
    // Rueckfall zeichnete einen Zufallspfad mit Drift +0.9 unter der
    // Ueberschrift PROFIT CURVE · 90 DAYS, neben dem echten Namen einer
    // echten Wallet.
    const chartPoints = wd && wd.pnl_curve && wd.pnl_curve.length > 1 ? T.seriesPoints(wd.pnl_curve, 340, 150) : '';
    const track = wd && wd.track ? wd.track : null;
    const edge = wd && wd.realized_edge ? wd.realized_edge : null;
    const sample = wd && wd.sample ? wd.sample : null;
    const rec = wd && wd.track_record ? wd.track_record : null;
    const winLabel = track && track.headline_win_rate != null ? Math.round(track.headline_win_rate * 100) + '%' : (t && t.win != null ? Math.round(t.win * 100) + '%' : '—');
    const resolvedLabel = track && track.resolved_markets != null ? num(track.resolved_markets) : (t && t.resolved != null ? num(t.resolved) : '—');
    // Profit and volume: the leaderboard row when there is one, else the
    // settled figures of /api/wallet — never a placeholder.
    const profit = t ? t.pnl : (rec && rec.settled_pnl != null ? rec.settled_pnl : null);
    const volume = t ? t.vol : (rec && rec.volume != null ? rec.volume : null);
    const grade = (t && t.grade) || (rec && rec.grade) || '';
    let note = '';
    if (wd) {
      const parts = [];
      if (sample) parts.push('n = ' + sample.n_resolved + ' resolved events · sample ' + sample.quality);
      if (edge && edge.ci_low != null && edge.ci_high != null) parts.push('edge CI [' + (edge.ci_low * 100).toFixed(1) + '¢, ' + (edge.ci_high * 100).toFixed(1) + '¢] · verdict ' + edge.verdict);
      if (wd.snapshot_at) parts.push('snapshot ' + String(wd.snapshot_at).slice(0, 16).replace('T', ' ') + ' UTC');
      if (track && track.resolved_capped) parts.push('resolved list capped — win rate not reliable');
      note = parts.join('<br>');
    } else if (!t && addr) {
      // Until the answer is in, the tiles below carry the tape window only.
      note = 'Waiting for /api/wallet/' + esc(shortAddr) + '. Nothing beyond the tape window is shown until it answers.';
    }
    // Score components as a labelled list in the note, not the raw reason
    // string next to the address.
    const parts = t ? scorePartsOf(t) : [];
    if (parts.length) note = (note ? note + '<br>' : '') + 'score components: ' + parts.map((p) => esc(p.label) + ' ' + esc(p.value)).join(' · ');
    // Tape-only wallets without an /api/wallet answer: the tiles carry what
    // the tape window shows for this wallet (prints, notional, biggest print,
    // markets) — no profit, no win rate, because nothing here measured them.
    // Once /api/wallet answered, the settled figures of that answer stand
    // here (never a placeholder); a leaderboard row shows its own.
    const tapeNotional = tapePrints.reduce((a, x) => a + (+x.size || 0), 0);
    const tapeBiggest = tapePrints.reduce((a, x) => Math.max(a, +x.size || 0), 0);
    const tapeMarkets = tapePrints.map((x) => x.marketKey || x.market).filter((k, i, arr) => arr.indexOf(k) === i).length;
    const nurTapeTiles = nurTape && !wd;
    const stats = nurTapeTiles
      ? [
        { label: 'PRINTS · TAPE WINDOW', value: num(tapePrints.length), style: STAT_VAL },
        { label: 'MOVED · TAPE WINDOW', value: tapePrints.length ? money(tapeNotional) : '—', style: STAT_VAL },
        { label: 'BIGGEST PRINT', value: tapePrints.length ? money(tapeBiggest) : '—', style: STAT_VAL },
        { label: 'MARKETS · TAPE WINDOW', value: tapePrints.length ? num(tapeMarkets) : '—', style: STAT_VAL }
      ]
      : [
        { label: t ? 'PROFIT' : 'SETTLED PNL', value: profit != null ? money(profit) : '—', style: STAT_VAL + '; color:' + (profit != null && profit < 0 ? '#D95F52' : '#69B47E') },
        { label: 'WIN RATE', value: winLabel, style: STAT_VAL },
        { label: 'RESOLVED BETS', value: resolvedLabel, style: STAT_VAL },
        { label: 'VOLUME', value: volume != null ? money(volume) : '—', style: STAT_VAL }
      ];
    if (nurTapeTiles) {
      note = (note ? note + '<br>' : '') + esc('Not on the loaded leaderboard — no profit, win rate or score is measured for this wallet here.'
        + (addr ? '' : ' No address is known for it, so /api/wallet cannot be asked.'));
    }
    // Recent trades from /api/wallet when it answered; for a tape-only wallet
    // without that answer, its prints from the tape window.
    const wdTrades = wd && wd.recent_trades ? wd.recent_trades : [];
    const list = (wdTrades.length || !nurTape ? wdTrades : tapePrints).slice(0, 4).map((x) => ({
      primary: x.market,
      secondary: x.side + ' at ' + x.price + ' · ' + x.ago,
      value: money(x.size),
      style: M + '; font-size:13px; color:' + (String(x.side).indexOf('BUY') === 0 ? '#69B47E' : '#D95F52')
    }));
    const curveWindow = wd && wd.pnl && wd.pnl.window ? String(wd.pnl.window).toUpperCase() : '';
    v = {
      kicker: 'WALLET',
      accent: '#D9A648',
      title: t ? t.name : (wd && wd.identity && wd.identity.pseudonym) || d.id || shortAddr,
      meta: (t ? t.wallet : (addr || 'address not public')) + (grade ? ' · grade ' + grade : ''),
      chartLabel: 'PROFIT CURVE' + (curveWindow ? ' · ' + curveWindow : ''),
      chartPoints,
      chartEmpty: addr
        ? 'No profit curve for this wallet — /api/wallet did not answer with one.'
        : 'No profit curve — no address is known for this wallet, so /api/wallet was not asked.',
      axisStart: wd && wd.pnl && wd.pnl.points && wd.pnl.points.length ? String(wd.pnl.points[0].t || '').slice(0, 10) : 'start',
      listEmpty: nurTape
        ? 'No print of this wallet in the current tape window.'
        : 'No trades for this wallet — /api/wallet did not answer with any.',
      stats,
      listLabel: nurTape && !wdTrades.length ? 'PRINTS · TAPE WINDOW' : 'RECENT TRADES',
      // Nur die Trades dieser Wallet. Der Rueckfall auf die ersten vier
      // Tape-Zeilen schrieb fremde Prints dieser Wallet zu.
      list,
      // The full analysis lives on the wallet page; the drawer is the glance.
      // Both buttons need an address; without one there is no button.
      primaryAction: addr ? 'Full analysis →' : '',
      primaryAct: addr ? T.act(() => { if (T.analyseWallet) T.analyseWallet(addr); }) : '',
      // "Follow on paper" stand hier als zweiter Knopf ohne Handler; /api/track
      // liest die gefolgten Wallets nur, es gibt keinen Endpunkt zum Folgen.
      // The backtester does not auto-run: it opens with the wallet filled in
      // and waits for RUN.
      secondaryAction: addr ? 'Open in the backtester' : '',
      secondaryAct: addr ? T.act(() => {
        // go() sets the address (no duplicate history entry when already there).
        T.state.btWallet = addr || T.state.btWallet;
        T.state.btDirty = !!T.liveData.backtest;
        if (T.go) { T.go('backtester'); return; }
        T.setState({ page: 'backtester', detail: null });
        try { history.pushState(null, '', '#backtester'); } catch (e) { /* file:// */ }
      }) : '',
      note
    };
  }

  return '<div role="dialog" aria-modal="true" aria-label="' + esc(v.title || v.kicker || 'Detail') + '" style="position:absolute; top:0; right:0; bottom:0; width:392px; box-sizing:border-box; border-left:1px solid rgba(234,230,220,.09); background:#0B0B0A; overflow-y:auto; z-index:20; box-shadow:-24px 0 48px rgba(0,0,0,.45); animation:panelIn .22s ease-out">'
    + '<div style="display:flex; align-items:center; justify-content:space-between; padding:13px 20px; border-bottom:1px solid rgba(234,230,220,.09); background:#131311; position:sticky; top:0">'
    + '<div style="' + M + '; font-size:10.5px; letter-spacing:.16em; color:' + v.accent + '">' + v.kicker + '</div>'
    + '<div ' + T.act(() => T.setState({ detail: null })) + ' aria-label="Close" class="hv-white" style="' + M + '; font-size:14px; color:rgba(234,230,220,.5); cursor:pointer; line-height:1">✕</div></div>'
    + '<div style="padding:20px">'
    + '<div style="font-size:19px; line-height:1.3">' + esc(v.title) + '</div>'
    + '<div style="' + M + '; font-size:11px; color:rgba(234,230,220,.6); margin-top:6px">' + esc(v.meta) + '</div>'
    + '<div style="display:grid; grid-template-columns:repeat(2,1fr); gap:10px; margin-top:18px">'
    + v.stats.map((st) =>
      '<div style="background:#131311; border:1px solid rgba(234,230,220,.09); border-radius:6px; padding:11px 13px">'
      + '<div style="' + M + '; font-size:10.5px; letter-spacing:.13em; color:rgba(234,230,220,.6)">' + st.label + '</div>'
      + '<div style="' + st.style + '">' + st.value + '</div></div>'
    ).join('')
    + '</div>'
    + (v.note ? '<div style="' + M + '; font-size:10.5px; color:rgba(234,230,220,.6); line-height:1.7; margin-top:12px; border:1px solid rgba(234,230,220,.09); border-radius:4px; padding:9px 11px; background:#131311">' + v.note + '</div>' : '')
    + '<div style="background:#131311; border:1px solid rgba(234,230,220,.09); border-radius:6px; padding:14px; margin-top:14px">'
    + '<div style="' + M + '; font-size:10.5px; letter-spacing:.14em; color:rgba(234,230,220,.6); margin-bottom:10px">' + v.chartLabel + '</div>'
    + (v.chartPoints
      ? '<svg width="100%" height="150" viewBox="0 0 340 150" preserveAspectRatio="none" role="img" aria-label="' + esc(v.chartLabel || 'chart') + '">'
        + '<line x1="0" y1="25" x2="340" y2="25" stroke="rgba(234,230,220,.07)" />'
        + '<line x1="0" y1="70" x2="340" y2="70" stroke="rgba(234,230,220,.07)" />'
        + '<line x1="0" y1="115" x2="340" y2="115" stroke="rgba(234,230,220,.07)" />'
        + '<line x1="0" y1="145" x2="340" y2="145" stroke="rgba(234,230,220,.14)" />'
        + '<polyline points="' + v.chartPoints + '" fill="none" stroke="' + v.accent + '" stroke-width="2" /></svg>'
        + '<div style="display:flex; justify-content:space-between; ' + M + '; font-size:11px; color:rgba(234,230,220,.6); margin-top:6px">'
        + '<span>' + v.axisStart + '</span><span>now</span></div>'
      : '<div style="' + M + '; font-size:10.5px; color:rgba(234,230,220,.6); line-height:1.6">' + esc(v.chartEmpty) + '</div>')
    + '</div>'
    + '<div style="' + M + '; font-size:10.5px; letter-spacing:.14em; color:rgba(234,230,220,.6); margin:20px 0 10px">' + v.listLabel + '</div>'
    + (v.list.length ? '' : '<div style="' + M + '; font-size:10.5px; color:rgba(234,230,220,.6); line-height:1.6">' + esc(v.listEmpty) + '</div>')
    + v.list.map((it) =>
      '<div style="display:flex; align-items:center; justify-content:space-between; gap:12px; padding:10px 0; border-bottom:1px solid rgba(234,230,220,.06)">'
      + '<div style="min-width:0">'
      + '<div style="font-size:13px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="' + esc(it.primary) + '">' + esc(it.primary) + '</div>'
      + '<div style="' + M + '; font-size:10.5px; color:rgba(234,230,220,.6); margin-top:3px">' + esc(it.secondary) + '</div></div>'
      + '<div style="' + it.style + '">' + it.value + '</div></div>'
    ).join('')
    // Ein Knopf wird nur gezeichnet, wenn ein Handler daran haengt.
    + (v.primaryAction && v.primaryAct
      ? '<div style="display:flex; flex-direction:column; gap:8px; margin-top:20px">'
        + '<div ' + v.primaryAct + ' class="hv-accentbg" style="font-size:13px; font-weight:600; text-align:center; color:#0B0B0A; background:#D9A648; border-radius:4px; padding:11px; cursor:pointer">' + esc(v.primaryAction) + '</div>'
        + (v.secondaryAction && v.secondaryAct
          ? '<div ' + v.secondaryAct + ' class="hv-bd32" style="font-size:12.5px; text-align:center; color:rgba(234,230,220,.7); border:1px solid rgba(234,230,220,.16); border-radius:4px; padding:10px; cursor:pointer">' + esc(v.secondaryAction) + '</div>'
          : '')
        + '</div>'
      : '')
    + '</div></div>';
}

export function renderSearch(T) {
  const s = T.state;
  if (!s.searchOpen) return '';
  const q = s.searchQuery.trim().toLowerCase();
  // A pasted address is not in any loaded list — it is an action: open the
  // wallet page for it. A partial 0x… gets a hint row instead of silence.
  const rawQuery = s.searchQuery.trim();
  const walletActions = [];
  if (isFullAddress(rawQuery)) {
    walletActions.push({
      tag: 'ANALYSE', title: 'Analyse wallet ' + rawQuery.slice(0, 6) + '…' + rawQuery.slice(-4), meta: rawQuery + ' · opens the wallet page (#wallet/<address>)', value: '→',
      tagStyle: M + '; font-size:10.5px; letter-spacing:.12em; color:#0B0B0A; background:#D9A648; border-radius:4px; padding:3px 6px',
      act: T.act(() => { if (T.analyseWallet) T.analyseWallet(rawQuery); else T.setState({ searchOpen: false, searchQuery: '' }); })
    });
  } else if (/^0x[0-9a-fA-F]*$/.test(rawQuery) && rawQuery.length > 2) {
    walletActions.push({
      tag: 'WALLET', title: 'Paste the full address to analyse a wallet', meta: '0x followed by 40 hex characters — ' + rawQuery.length + ' of 42 so far', value: '',
      tagStyle: M + '; font-size:10.5px; letter-spacing:.12em; color:rgba(234,230,220,.6); border:1px solid rgba(234,230,220,.2); border-radius:4px; padding:3px 6px',
      act: ''
    });
  }
  const searchMarkets = T.markets.filter((m) => !q || m.title.toLowerCase().indexOf(q) >= 0).slice(0, 5).map((m) => ({
    tag: 'MARKET', title: m.title, meta: m.venue + ' · ' + m.cat, value: m.yes + '¢',
    tagStyle: M + '; font-size:10.5px; letter-spacing:.12em; color:#0B0B0A; background:#D9A648; border-radius:4px; padding:3px 6px',
    act: T.act(() => T.setState({ detail: { kind: 'market', id: m.id }, searchOpen: false, searchQuery: '' }))
  }));
  const searchTraders = T.traders.filter((t) => !q || t.name.toLowerCase().indexOf(q) >= 0).slice(0, 3).map((t) => ({
    tag: 'WALLET', title: t.name, meta: t.wallet + (t.score != null ? ' · smart score ' + t.score : ''), value: money(t.pnl),
    tagStyle: M + '; font-size:10.5px; letter-spacing:.12em; color:#0B0B0A; background:#6E9BC8; border-radius:4px; padding:3px 6px',
    act: T.act(() => { T.setState({ searchOpen: false, searchQuery: '' }); T.openWallet(t.name); })
  }));
  const results = walletActions.concat(searchMarkets, searchTraders);

  return '<div ' + T.act(() => T.setState({ searchOpen: false }), { plain: true }) + ' data-bg style="position:fixed; inset:0; background:rgba(8,8,7,.72); display:flex; align-items:flex-start; justify-content:center; padding-top:14vh; z-index:50">'
    + '<div data-stop role="dialog" aria-modal="true" aria-label="Search markets, wallets and categories" style="width:620px; background:#131311; border:1px solid rgba(234,230,220,.14); border-radius:14px; overflow:hidden; box-shadow:0 30px 80px rgba(0,0,0,.6)">'
    + '<input value="' + esc(s.searchQuery) + '" ' + T.inp((e) => T.setState({ searchQuery: e.target.value }), 'searchQuery') + ' placeholder="Search markets, wallets, categories — or paste a 0x… address to analyse it" style="width:100%; box-sizing:border-box; background:transparent; border:none; border-bottom:1px solid rgba(234,230,220,.35); padding:17px 20px; ' + M + '; font-size:14px; color:#EAE6DC" autofocus />'
    + '<div style="max-height:380px; overflow-y:auto">'
    // The first row is marked (data-result) and lightly highlighted: Enter
    // opens it (app.js keydown), so the palette works without the mouse.
    + results.map((r, i) =>
      '<div ' + r.act + ' data-result="' + i + '" class="hv-el" style="display:flex; align-items:center; gap:12px; padding:12px 20px; border-bottom:1px solid rgba(234,230,220,.05); cursor:pointer' + (i === 0 ? '; background:#1A1A17' : '') + '">'
      + '<div style="' + r.tagStyle + '">' + r.tag + '</div>'
      + '<div style="flex:1; min-width:0">'
      + '<div style="font-size:13.5px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="' + esc(r.title) + '">' + esc(r.title) + '</div>'
      + '<div style="' + M + '; font-size:10.5px; color:rgba(234,230,220,.6); margin-top:2px">' + esc(r.meta) + '</div></div>'
      + '<div style="' + M + '; font-size:12.5px; color:rgba(234,230,220,.6)">' + r.value + '</div></div>'
    ).join('')
    + '</div>'
    + '<div style="padding:10px 20px; ' + M + '; font-size:11px; color:rgba(234,230,220,.55); display:flex; gap:16px">'
    + '<span>ESC to close</span>' + (results.length ? '<span>ENTER opens the first result, ARROW KEYS walk them</span>' : '') + '<span role="status">' + results.length + ' results'
    + (!T.markets.length && !T.traders.length ? ' — nothing loaded to search: markets come from /api/markets, wallets from the leaderboard' : '') + '</span></div>'
    + '</div></div>';
}
