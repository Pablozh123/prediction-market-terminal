// Detail overlay (right panel) and command palette — ported from the reference.
// Wallet details show scorecard fields (n, CI, verdict, snapshot) when the API
// answered for that wallet; scores never render without their sample size.

import { esc, money, num } from './util.js';

const M = "font-family:'JetBrains Mono',monospace";
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
      accent: m.chg >= 0 ? '#C8F542' : '#FF4545',
      title: m.title,
      meta: m.venue + ' · ' + m.cat + ' · resolves ' + m.ends,
      chartLabel: 'YES PRICE · 24H',
      chartPoints: c.pts,
      chartEmpty: 'No price history loaded for this market — /api/market/<id>/history did not answer.',
      axisStart: '24h ago',
      listEmpty: 'No print of this market in the current tape window.',
      stats: [
        { label: 'YES', value: m.yes + '¢', style: STAT_VAL },
        { label: 'CHANGE 1D', value: (m.chg >= 0 ? '+' : '') + m.chg + '¢', style: STAT_VAL + '; color:' + (m.chg >= 0 ? '#C8F542' : '#FF4545') },
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
        style: M + '; font-size:13px; color:' + (t.side.indexOf('BUY') === 0 ? '#C8F542' : '#FF4545')
      })),
      // Keine Knoepfe: "Watch this market" hatte keinen Endpunkt (die
      // Watchlist wird nur gelesen), und "Open on <venue>" verlinkte auf die
      // Boerse — das Projekt setzt bewusst keine Venue-Links (Schweizer
      // Rechtslage). Ein Knopf ohne Wirkung waere schlimmer als keiner.
      primaryAction: '',
      note: ''
    };
  } else {
    const t = T.traders.find((x) => x.name === d.id);
    if (!t) return '';
    const wd = T.liveData.walletDetail[d.id];
    // Die Gewinnkurve kommt aus /api/wallet oder es gibt keine. Der frühere
    // Rueckfall zeichnete einen Zufallspfad mit Drift +0.9 unter der
    // Ueberschrift PROFIT CURVE · 90 DAYS, neben dem echten Namen einer
    // echten Wallet.
    const chartPoints = wd && wd.pnl_curve && wd.pnl_curve.length > 1 ? T.seriesPoints(wd.pnl_curve, 340, 150) : '';
    const track = wd && wd.track ? wd.track : null;
    const edge = wd && wd.realized_edge ? wd.realized_edge : null;
    const sample = wd && wd.sample ? wd.sample : null;
    const winLabel = track && track.headline_win_rate != null ? Math.round(track.headline_win_rate * 100) + '%' : (t.win != null ? Math.round(t.win * 100) + '%' : '—');
    const resolvedLabel = track && track.resolved_markets != null ? num(track.resolved_markets) : (t.resolved != null ? num(t.resolved) : '—');
    let note = '';
    if (wd) {
      const parts = [];
      if (sample) parts.push('n = ' + sample.n_resolved + ' resolved events · sample ' + sample.quality);
      if (edge && edge.ci_low != null && edge.ci_high != null) parts.push('edge CI [' + (edge.ci_low * 100).toFixed(1) + '¢, ' + (edge.ci_high * 100).toFixed(1) + '¢] · verdict ' + edge.verdict);
      if (wd.snapshot_at) parts.push('snapshot ' + String(wd.snapshot_at).slice(0, 16).replace('T', ' ') + ' UTC');
      if (track && track.resolved_capped) parts.push('resolved list capped — win rate not reliable');
      note = parts.join('<br>');
    }
    v = {
      kicker: 'WALLET',
      accent: '#C8F542',
      title: t.name,
      meta: t.wallet + (t.tags ? ' · ' + t.tags : ''),
      chartLabel: 'PROFIT CURVE · 90 DAYS',
      chartPoints,
      chartEmpty: 'No profit curve for this wallet — /api/wallet did not answer with one.',
      axisStart: '90d ago',
      listEmpty: 'No trades for this wallet — /api/wallet did not answer with any.',
      stats: [
        { label: 'PROFIT', value: money(t.pnl), style: STAT_VAL + '; color:#C8F542' },
        { label: 'WIN RATE', value: winLabel, style: STAT_VAL },
        { label: 'RESOLVED BETS', value: resolvedLabel, style: STAT_VAL },
        { label: 'VOLUME', value: money(t.vol), style: STAT_VAL }
      ],
      listLabel: 'RECENT TRADES',
      // Nur die Trades dieser Wallet. Der Rueckfall auf die ersten vier
      // Tape-Zeilen schrieb fremde Prints dieser Wallet zu.
      list: (wd && wd.recent_trades ? wd.recent_trades : []).slice(0, 4).map((x) => ({
        primary: x.market,
        secondary: x.side + ' at ' + x.price + ' · ' + x.ago,
        value: money(x.size),
        style: M + '; font-size:13px; color:' + (String(x.side).indexOf('BUY') === 0 ? '#C8F542' : '#FF4545')
      })),
      primaryAction: 'Backtest this wallet',
      // "Follow on paper" stand hier als zweiter Knopf ohne Handler; /api/track
      // liest die gefolgten Wallets nur, es gibt keinen Endpunkt zum Folgen.
      primaryAct: T.act(() => {
        const addr = (t.walletFull || '').trim();
        T.setState({ page: 'backtester', detail: null, btWallet: addr || T.state.btWallet });
        T.runBacktestLive();
      }),
      note
    };
  }

  return '<div style="position:absolute; top:0; right:0; bottom:0; width:392px; box-sizing:border-box; border-left:1px solid rgba(255,255,255,.09); background:#0A0D0F; overflow-y:auto; z-index:20; box-shadow:-24px 0 48px rgba(0,0,0,.45); animation:panelIn .22s ease-out">'
    + '<div style="display:flex; align-items:center; justify-content:space-between; padding:13px 20px; border-bottom:1px solid rgba(255,255,255,.09); background:#10151A; position:sticky; top:0">'
    + '<div style="' + M + '; font-size:10.5px; letter-spacing:.16em; color:' + v.accent + '">' + v.kicker + '</div>'
    + '<div ' + T.act(() => T.setState({ detail: null })) + ' class="hv-white" style="' + M + '; font-size:14px; color:rgba(255,255,255,.5); cursor:pointer; line-height:1">✕</div></div>'
    + '<div style="padding:20px">'
    + '<div style="font-size:19px; line-height:1.3">' + esc(v.title) + '</div>'
    + '<div style="' + M + '; font-size:11px; color:rgba(255,255,255,.45); margin-top:6px">' + esc(v.meta) + '</div>'
    + '<div style="display:grid; grid-template-columns:repeat(2,1fr); gap:10px; margin-top:18px">'
    + v.stats.map((st) =>
      '<div style="background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:10px; padding:11px 13px">'
      + '<div style="' + M + '; font-size:9.5px; letter-spacing:.13em; color:rgba(255,255,255,.45)">' + st.label + '</div>'
      + '<div style="' + st.style + '">' + st.value + '</div></div>'
    ).join('')
    + '</div>'
    + (v.note ? '<div style="' + M + '; font-size:10.5px; color:rgba(255,255,255,.45); line-height:1.7; margin-top:12px; border:1px solid rgba(255,255,255,.09); border-radius:8px; padding:9px 11px; background:#10151A">' + v.note + '</div>' : '')
    + '<div style="background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:12px; padding:14px; margin-top:14px">'
    + '<div style="' + M + '; font-size:9.5px; letter-spacing:.14em; color:rgba(255,255,255,.45); margin-bottom:10px">' + v.chartLabel + '</div>'
    + (v.chartPoints
      ? '<svg width="100%" height="150" viewBox="0 0 340 150" preserveAspectRatio="none">'
        + '<line x1="0" y1="25" x2="340" y2="25" stroke="rgba(255,255,255,.07)" />'
        + '<line x1="0" y1="70" x2="340" y2="70" stroke="rgba(255,255,255,.07)" />'
        + '<line x1="0" y1="115" x2="340" y2="115" stroke="rgba(255,255,255,.07)" />'
        + '<line x1="0" y1="145" x2="340" y2="145" stroke="rgba(255,255,255,.14)" />'
        + '<polyline points="' + v.chartPoints + '" fill="none" stroke="' + v.accent + '" stroke-width="2" /></svg>'
        + '<div style="display:flex; justify-content:space-between; ' + M + '; font-size:10px; color:rgba(255,255,255,.4); margin-top:6px">'
        + '<span>' + v.axisStart + '</span><span>now</span></div>'
      : '<div style="' + M + '; font-size:10.5px; color:rgba(255,255,255,.42); line-height:1.6">' + esc(v.chartEmpty) + '</div>')
    + '</div>'
    + '<div style="' + M + '; font-size:9.5px; letter-spacing:.14em; color:rgba(255,255,255,.45); margin:20px 0 10px">' + v.listLabel + '</div>'
    + (v.list.length ? '' : '<div style="' + M + '; font-size:10.5px; color:rgba(255,255,255,.42); line-height:1.6">' + esc(v.listEmpty) + '</div>')
    + v.list.map((it) =>
      '<div style="display:flex; align-items:center; justify-content:space-between; gap:12px; padding:10px 0; border-bottom:1px solid rgba(255,255,255,.06)">'
      + '<div style="min-width:0">'
      + '<div style="font-size:13px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis">' + esc(it.primary) + '</div>'
      + '<div style="' + M + '; font-size:10.5px; color:rgba(255,255,255,.45); margin-top:3px">' + esc(it.secondary) + '</div></div>'
      + '<div style="' + it.style + '">' + it.value + '</div></div>'
    ).join('')
    // Ein Knopf wird nur gezeichnet, wenn ein Handler daran haengt.
    + (v.primaryAction && v.primaryAct
      ? '<div style="display:flex; flex-direction:column; gap:8px; margin-top:20px">'
        + '<div ' + v.primaryAct + ' class="hv-limebg" style="font-size:13px; font-weight:600; text-align:center; color:#0A0D0F; background:#C8F542; border-radius:8px; padding:11px; cursor:pointer">' + esc(v.primaryAction) + '</div>'
        + '</div>'
      : '')
    + '</div></div>';
}

export function renderSearch(T) {
  const s = T.state;
  if (!s.searchOpen) return '';
  const q = s.searchQuery.trim().toLowerCase();
  const searchMarkets = T.markets.filter((m) => !q || m.title.toLowerCase().indexOf(q) >= 0).slice(0, 5).map((m) => ({
    tag: 'MARKET', title: m.title, meta: m.venue + ' · ' + m.cat, value: m.yes + '¢',
    tagStyle: M + '; font-size:9px; letter-spacing:.12em; color:#0A0D0F; background:#C8F542; border-radius:4px; padding:3px 6px',
    act: T.act(() => T.setState({ detail: { kind: 'market', id: m.id }, searchOpen: false, searchQuery: '' }))
  }));
  const searchTraders = T.traders.filter((t) => !q || t.name.toLowerCase().indexOf(q) >= 0).slice(0, 3).map((t) => ({
    tag: 'WALLET', title: t.name, meta: t.wallet + (t.tags ? ' · ' + t.tags : ''), value: money(t.pnl),
    tagStyle: M + '; font-size:9px; letter-spacing:.12em; color:#0A0D0F; background:#4F8EF7; border-radius:4px; padding:3px 6px',
    act: T.act(() => { T.setState({ searchOpen: false, searchQuery: '' }); T.openWallet(t.name); })
  }));
  const results = searchMarkets.concat(searchTraders);

  return '<div ' + T.act(() => T.setState({ searchOpen: false })) + ' data-bg style="position:fixed; inset:0; background:rgba(5,7,9,.72); display:flex; align-items:flex-start; justify-content:center; padding-top:14vh; z-index:50">'
    + '<div data-stop style="width:620px; background:#10151A; border:1px solid rgba(255,255,255,.14); border-radius:14px; overflow:hidden; box-shadow:0 30px 80px rgba(0,0,0,.6)">'
    + '<input value="' + esc(s.searchQuery) + '" ' + T.inp((e) => T.setState({ searchQuery: e.target.value }), 'searchQuery') + ' placeholder="Search markets, wallets, categories…" style="width:100%; box-sizing:border-box; background:transparent; border:none; border-bottom:1px solid rgba(255,255,255,.09); padding:17px 20px; ' + M + '; font-size:14px; color:#fff; outline:none" autofocus />'
    + '<div style="max-height:380px; overflow-y:auto">'
    + results.map((r) =>
      '<div ' + r.act + ' class="hv-el" style="display:flex; align-items:center; gap:12px; padding:12px 20px; border-bottom:1px solid rgba(255,255,255,.05); cursor:pointer">'
      + '<div style="' + r.tagStyle + '">' + r.tag + '</div>'
      + '<div style="flex:1; min-width:0">'
      + '<div style="font-size:13.5px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis">' + esc(r.title) + '</div>'
      + '<div style="' + M + '; font-size:10.5px; color:rgba(255,255,255,.45); margin-top:2px">' + esc(r.meta) + '</div></div>'
      + '<div style="' + M + '; font-size:12.5px; color:rgba(255,255,255,.6)">' + r.value + '</div></div>'
    ).join('')
    + '</div>'
    + '<div style="padding:10px 20px; ' + M + '; font-size:10px; color:rgba(255,255,255,.35); display:flex; gap:16px">'
    + '<span>ESC to close</span><span>' + results.length + ' results</span></div>'
    + '</div></div>';
}
