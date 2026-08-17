// Rendert jede Seite der Web-Oberflaeche ohne Browser, einmal ganz ohne
// Nutzlast und einmal mit einer minimalen Live-Nutzlast, und schreibt das
// Ergebnis als JSON nach stdout. Der Test in tests/test_web_leerzustand.py
// liest das und prueft, dass ohne Daten keine Zahl erscheint.
//
// app.js kann nicht importiert werden, es mountet sich beim Laden selbst an
// document. Die Seitenmodule sind reine Funktionen ueber ein T-Objekt, also
// wird hier ein T gebaut, das dieselben Felder und Helfer bereitstellt.

import { esc, money, num, spark, seriesPoints } from '../web/js/util.js';
import { STUDIEN } from '../web/js/studies.js';
import { renderOverview, renderMarkets, renderFlow, renderCross, renderResolved, landingSubline, verdictCounts } from '../web/js/pages/core_pages.js';
import { renderTraders, renderWhale, renderRisk, renderTrack } from '../web/js/pages/trader_pages.js';
import { renderBacktester, renderCopy, renderPortfolio } from '../web/js/pages/trading_pages.js';
import { renderAlerts, renderResearch, renderSettings, collapseQueue } from '../web/js/pages/system_pages.js';
import { renderDetail, renderSearch } from '../web/js/overlays.js';

const SEITEN = {
  overview: renderOverview, markets: renderMarkets, flow: renderFlow,
  cross: renderCross, resolved: renderResolved,
  traders: renderTraders, whale: renderWhale, risk: renderRisk, track: renderTrack,
  backtester: renderBacktester, copy: renderCopy, portfolio: renderPortfolio,
  alerts: renderAlerts, research: renderResearch, settings: renderSettings
};

function neuesT() {
  const M = "font-family:'JetBrains Mono',monospace";
  return {
    state: {
      page: 'overview', tapeMin: 2500, tapeTracked: false, marketCat: 'All',
      tapeCat: 'All', whaleCat: 'All',
      marketFiltersOpen: false, mPlatform: 'all', mStatus: 'active', mProb: 'all',
      mLiq: 'all', mVol: 'all', mEnds: 'all', mAge: 'all',
      mExclude: [], mQuick: 'trending',
      crossQuery: '', crossSim: 0.5, crossMaxPairs: 50, crossMinGap: 0, crossLower: 'any',
      crossPmVol: 0, crossKsVol: 0, crossMinPrice: 0, crossMaxPrice: 100,
      marketSort: 'volume', marketQuery: '', traderRank: 'pnl', traderQuery: '',
      traderFiltersOpen: false,
      tPnl: 'all', tVol: 'all',
      btRun: 'idle', btError: '', btRetryIn: 0, btDirty: false,
      riskView: 'events', riskAgeCheck: false, copyTab: 'orders', copyQuery: '',
      copySide: 'all', copyStatus2: 'all', copyMin: 'all',
      portTab: 'positions', portQuery: '', portSource: 'all', portSide: 'all', portLosers: false,
      tapeQuery: '', tapePlatform: 'all', tapeSide: 'all', tapeOutcome: 'all',
      whaleSort: 'total',
      resQuery: '', resAnswer: 'all', resWindow: 'all', resError: 'all', resSort: 'recent',
      setMarketSample: 250, setTradeSample: 250, setWhale: 2500, setBankroll: 1000,
      setFee: 20, setSlip: 15, alertTab: 'signals', alertQuery: '', alertPlatform: 'all',
      alertType: 'all', alertScope: 'all', thMove: 5, thSpread: 3, thWhale: 2500,
      thEnding: 72, thHolder: 40, riskFilter: 'all', detail: null, searchOpen: false,
      searchQuery: '', btStrategy: 'copy', btWindow: 30, btWallet: '0xabc', btSizing: 'fixed',
      btStakeFixed: 25, btStakePct: 2, btStakeMult: 1, btStakeKelly: 5, btCap: 250,
      btExposure: 50, btBankroll: 1000, btFee: 20, btSlip: 15, btCompare: '', btTab: 'log',
      btFeeModel: 'curve',
      advancedOpen: false, sizingSimOpen: false, researchTab: 0, liveTab: 'runs',
      alertsOn: { movers: true, volume: true, whales: true, spreads: false, holders: false, endings: true },
      settingsOn: { telegram: true, autotop: false, kalshi: true, sports: false, cache: true, admin: true },
      clock: '00:00', live: 'waiting', liveAsOf: '', tapeAsOf: ''
    },
    markets: [], marketExtra: {}, traders: [], risks: [], tape: [],
    crossPairs: [], studies: STUDIEN,
    herkunft: { markets: null, tape: null, traders: null, risks: null, cross: null },
    // Landing payloads (Overview): null until loaded, like in app.js.
    landing: { micro: null, runs: null, notes: null, herkunft: { micro: null, runs: null, notes: null } },
    liveData: { leaderboard: null, cross: null, risk: null, riskLog: null, alerts: null, copy: null, portfolio: null, research: {}, backtest: null, walletDetail: {} },
    num, money, esc, spark,
    seriesPoints: (v, w, h) => seriesPoints(v, w, h),
    act: () => 'data-act="0"',
    inp: () => 'data-inp="0" data-key="k"',
    setState: () => {},
    opt: (l) => '<div>' + esc(l) + '</div>',
    chip: (l) => '<div>' + esc(l) + '</div>',
    tab: (l) => '<div>' + esc(l) + '</div>',
    toggle: () => '<div></div>',
    stepper: (l) => '<div>' + esc(l) + '</div>',
    changeStyle: () => M,
    marketView: (m) => ({
      title: m.title, meta: m.venue + ' · ' + m.cat, sparkPoints: m.spark ? spark(m.spark) : '',
      color: '#C8F542', priceLabel: m.yes + '¢', changeLabel: '+' + m.chg + '¢',
      changeStyle: M, volLabel: money(m.vol), ends: m.ends, act: ''
    }),
    marketExtraOf(m) { return this.marketExtra[m.id] || { spread: null, age: null, endsDays: null }; },
    // Same category filter as app.js tapeFiltered, so the chip variants below
    // exercise the real narrowing.
    tapeFiltered() {
      const s = this.state;
      return this.tape.filter((t) => t.size >= s.tapeMin && (s.tapeCat === 'All' || (t.category || 'Other') === s.tapeCat));
    },
    tapeRowView: (t) => ({
      ago: t.ago, wallet: t.wallet, market: t.market, side: t.side, price: t.price,
      size: money(t.size), venue: t.venue, category: t.category || 'Other', sideStyle: M, act: ''
    }),
    riskCardView: (r) => ({
      kind: r.kind, score: r.score, market: r.market, detail: r.detail, wallets: r.wallets,
      notional: r.notional, window: r.window, venue: r.venue, kindStyle: M, scoreStyle: M, act: ''
    }),
    go: () => {},
    goStudy: () => {},
    openWallet: () => {},
    openMarket: () => {}
  };
}

// The three landing payloads in the shape of public/data/*.json — small, but
// with every field the Overview reads: verdikt_art, zahlen, basis, zaehler,
// aggregat with BOTH pnl figures, notes with titles.
function landingNutzlast() {
  const studie = (id, frage, art, verdikt, wert, einheit, label, basis) => ({
    id, frage, verdikt, verdikt_art: art,
    zahlen: [{ label, wert, einheit }],
    basis
  });
  const micro = {
    _quelle: 'statisch', stand_utc: '2026-08-16T23:32:04+00:00', hinweis: 'Harness payload.',
    zaehler: { gesamt: 4, nein: 2, ja: 1, offen: 0, kontrolle: 1 },
    studien: [
      studie('h-yes', 'Does the harness board render a confirmed row?', 'ja', 'Yes. Harness hit rate above the coin flip.', 55.5, '%', 'Hit rate', { beobachtungen: 205835, fenster: '2026-07-18 to 2026-07-28' }),
      studie('h-no-1', 'Does the harness board render a refuted row?', 'nein', 'No. The edge is worth nothing after costs.', 0.0856, 'cents per firing', 'Gross edge', { beobachtungen: 205835, fenster: '2026-07-18 to 2026-07-28' }),
      studie('h-no-2', 'Does a second refuted row render?', 'nein', 'No, carry. Gaps settle in 2027.', 8, '', 'Pairs matched', { paare: 8, maerkte: 900, fenster: '2026-07-30' }),
      studie('h-ctrl', 'Does the control row render?', 'kontrolle', 'No drift found. 98.6% agreement.', 98.6, '%', 'Agreement with the venue', { beobachtungen: 72, tokens: 24, fenster: '2026-07-31' })
    ]
  };
  const runs = {
    _quelle: 'statisch', stand_utc: '2026-08-07T04:33:11+00:00', kennzeichnung: 'live/descriptive',
    aggregat: {
      n_runs: 21, n_wetten: 27, gewonnen: 25, verloren: 2, offen: 0,
      einsatz_usd: 1172.23, realisierter_pnl_usd: 288.67, roi_realisiert_pct: 24.6,
      sichtbare_tiefe_usd: 1515.04, einsatz_zu_sichtbarer_tiefe_pct: 77.4,
      wallet_netto_usd: 175.09, wallet_kaeufe_usd: 492.51, wallet_abgleich_stand: '2026-07-18'
    },
    runs: []
  };
  const notes = {
    _quelle: 'statisch', stand_utc: '2026-08-17T00:00:00+00:00', kennzeichnung: 'curated/field-notes',
    notes: [
      { date: '2026-08-01', venue: 'Polymarket', title: 'Harness note one', observation: 'x' },
      { date: '2026-08-02', venue: 'Kalshi', title: 'Harness note two', observation: 'x' },
      { date: '2026-08-03', venue: 'Polymarket', title: 'Harness note three', observation: 'x' },
      { date: '2026-08-04', venue: 'Polymarket', title: 'Harness note four', observation: 'x' },
      { date: '2026-08-05', venue: 'Kalshi', title: 'Harness note five', observation: 'x' },
      { date: '2026-08-06', venue: 'Kalshi', title: 'Harness note six must not appear', observation: 'x' }
    ]
  };
  return {
    micro, runs, notes,
    herkunft: { micro: { quelle: 'statisch' }, runs: { quelle: 'statisch' }, notes: { quelle: 'statisch' } }
  };
}

// Eine kleine, aber echte Nutzlast: ein Markt, ein Print, eine Wallet.
function mitDaten(T) {
  T.landing = landingNutzlast();
  T.state.liveAsOf = '2026-08-17 10:00 UTC';
  T.state.tapeAsOf = '2026-08-17 10:00 UTC';
  T.markets = [{
    id: 'm1', title: 'Example question', venue: 'Polymarket', cat: 'Macro',
    yes: 62, chg: 3, vol: 125000, liq: 40000, ends: 'Dec 2026', url: ''
  }];
  T.marketExtra = { m1: { spread: 2, age: 40, endsDays: 120 } };
  T.herkunft.markets = { quelle: 'live' };
  // Ein Polymarket-Print mit Wallet und Kategorie (die kommt vom Server ueber
  // /api/tape), dazu ein Kalshi-Print ohne Wallet: den muss Whale flow
  // ausschliessen und sagen, dass er ausgeschlossen ist.
  T.tape = [{
    ago: '2 min ago', mins: 2, wallet: 'w1', walletAddress: '0xabc',
    market: 'Example question', marketKey: 'm1', category: 'Macro',
    side: 'BUY Yes', price: '62.0¢', size: 9000,
    venue: 'Polymarket', tracked: false
  }, {
    ago: '1 min ago', mins: 1, wallet: '—', walletAddress: '',
    market: 'KXBTC15M-26AUG17-1030-T115', marketKey: 'KXBTC15M-26AUG17-1030-T115', category: 'Crypto',
    side: 'BUY Yes', price: '55.0¢', size: 3000,
    venue: 'Kalshi', tracked: false
  }];
  T.herkunft.tape = { quelle: 'live' };
  // Leaderboard row as /api/leaderboard delivers it: no win rate, no resolved
  // count (those come per wallet), a smart score with its components, and
  // the raw reason string that must NOT reach the page.
  T.traders = [{
    name: 'w1', wallet: '0xab…c', walletFull: '0xabc', pnl: 12000, win: null,
    resolved: null, vol: 90000, score: 71, grade: 'B', scoreN: null, scoreCi: null, sampleBadge: null,
    scoreParts: [{ label: 'return', value: 90, weight: 0.35 }, { label: 'sharpe proxy', value: 60, weight: 0.2 }, { label: 'volume', value: 80, weight: 0.1 }],
    tags: 'return 90, sharpe-proxy 60, drawdown-proxy 100, win 55, recency 50, volume 80'
  }];
  T.herkunft.traders = { quelle: 'live' };
  T.liveData.leaderboard = { _quelle: 'live', rows: [], as_of: '2026-08-07' };
  // Two event rows: one in the richer shape of api_views.risk_event_row
  // (side, prices, window, top wallets, components, link) and one older row
  // without those fields, which must still render without invented values.
  T.risks = [{
    kind: 'TIMING', score: 61, market: 'Example question', detail: 'three wallets, one side',
    wallets: 3, notional: '$40k', window: '2 h', venue: 'Polymarket', sev: 'medium',
    market_key: '0xc1', url: 'https://polymarket.com/event/example-question', flags: ['three wallets, one side'],
    notional_usd: 40000, category: 'Politics & geopolitics', context_note: 'decisions are known to officials before the public',
    side: 'NO buys', side_notional: 34000, side_share: 0.85,
    side_split: { buy_yes: 6000, buy_no: 34000, sell_yes: 0, sell_no: 0 },
    price_outcome: 'NO', price_first: 0.30, price_last: 0.34, price_min: 0.30, price_max: 0.34,
    first_print: '2026-08-17T09:40:00Z', last_print: '2026-08-17T10:00:00Z', window_minutes: 20, prints: 4,
    top_wallets: [
      { wallet: '0xbbb2000000000000000000000000000000000002', short: '0xbbb2…0002', notional: 26000, share: 0.65, side: 'NO buys', fresh: true, url: 'https://polymarket.com/profile/0xbbb2000000000000000000000000000000000002' },
      { wallet: '0xaaa1000000000000000000000000000000000001', short: '0xaaa1…0001', notional: 8000, share: 0.2, side: 'NO buys', fresh: false, url: 'https://polymarket.com/profile/0xaaa1000000000000000000000000000000000001' }
    ],
    components: [
      { key: 'component_notional', label: 'notional', value: 6.0, max: 15 },
      { key: 'component_concentration', label: 'top-wallet concentration', value: 9.8, max: 15 },
      { key: 'component_late', label: 'late flow', value: 0, max: 15 },
      { key: 'component_fresh_wallets', label: 'fresh-wallet cluster', value: 5.0, max: 10 },
      { key: 'context_multiplier', label: 'context multiplier', value: 1.1, max: null }
    ],
    token_id: 'tokNO'
  }, {
    kind: 'EVENT SCREEN', score: 44, market: 'KXFED-26SEP', detail: 'No individual flags — score from combined components.',
    wallets: 0, notional: '$12k', window: '3.0/h', venue: 'Kalshi', sev: 'low'
  }];
  T.herkunft.risks = { quelle: 'live' };
  T.liveData.risk = {
    _quelle: 'live',
    kpis: { events_screened: 12, high_risk_events: 1, high_risk_wallets: 2, fresh_clusters: 0, coordinated_clusters: 0 },
    wallets: [], fresh: [], timing: [], network: [], graph: null, matrix: {}
  };
  // Flag log (/api/risk/log?enrich=1): one Polymarket flag with the price
  // after the flag read for +30 min and +2 h, +24 h not yet passed; one Kalshi
  // flag without history. Newest first as the API delivers it.
  T.liveData.riskLog = {
    _quelle: 'live', as_of: '2026-08-17 10:30 UTC', count: 2, enriched: 1, enrich_max: 30, min_score: 40, dedupe_hours: 6, sampler_interval_min: 0,
    rows: [{
      flag_id: 'f1', first_seen: '2026-08-17T10:05:00Z', last_seen: '2026-08-17T10:25:00Z', times_seen: 3,
      venue: 'Polymarket', market_key: '0xc1', title: 'Example question', url: 'https://polymarket.com/event/example-question',
      category: 'Politics & geopolitics', kind: 'TIMING', flags: ['three wallets, one side'],
      side: 'NO buys', side_share: 0.85, side_notional: 34000, side_split: { buy_yes: 6000, buy_no: 34000, sell_yes: 0, sell_no: 0 },
      price_outcome: 'NO', price_at_flag: 0.34, price_min: 0.30, price_max: 0.34, notional: 40000, unique_wallets: 3, prints: 4,
      top_wallets: [{ wallet: '0xbbb2000000000000000000000000000000000002', short: '0xbbb2…0002', notional: 26000, share: 0.65, side: 'NO buys', fresh: true, url: 'https://polymarket.com/profile/0xbbb2000000000000000000000000000000000002' }],
      score: 61, sev: 'medium',
      components: [{ key: 'component_concentration', label: 'top-wallet concentration', value: 9.8, max: 15 }, { key: 'component_fresh_wallets', label: 'fresh-wallet cluster', value: 5.0, max: 10 }],
      window_start: '2026-08-17T09:40:00Z', window_end: '2026-08-17T10:00:00Z', window_minutes: 20, token_id: 'tokNO',
      after: { '30m': { price: 0.37, move_c: 3.0 }, '2h': { price: 0.31, move_c: -3.0 }, '24h': null }
    }, {
      flag_id: 'f2', first_seen: '2026-08-17T09:00:00Z', last_seen: '2026-08-17T09:00:00Z', times_seen: 1,
      venue: 'Kalshi', market_key: 'KXFED-26SEP', title: 'KXFED-26SEP', url: 'https://kalshi.com/markets/KXFED-26SEP',
      category: 'General', kind: 'LARGE PRINT', flags: ['large print'],
      side: 'YES buys', side_share: 1, side_notional: 12000, side_split: { buy_yes: 12000, buy_no: 0, sell_yes: 0, sell_no: 0 },
      price_outcome: 'YES', price_at_flag: 0.4, price_min: 0.4, price_max: 0.4, notional: 12000, unique_wallets: 0, prints: 1,
      top_wallets: [], score: 44, sev: 'low', components: [],
      window_start: '2026-08-17T08:59:00Z', window_end: '2026-08-17T08:59:00Z', window_minutes: 0, token_id: '', after: null
    }]
  };
  // One pair that clears the server gate (sim >= 0.5, volume on both venues).
  T.crossPairs = [{ event: 'Example question', cat: 'Macro', pm: 62, ks: 58, sim: 0.71, pmVol: 1200000, ksVol: 300000, held: '2 h' }];
  T.herkunft.cross = { quelle: 'live' };
  T.liveData.cross = { _quelle: 'live', rows: T.crossPairs, candidates_before_gate: 9, gate: { min_similarity: 0.5, require_volume_both: true }, as_of: '2026-08-17 10:00 UTC' };
  T.liveData.resolved = {
    _quelle: 'live',
    rows: [{ title: 'Settled question', meta: 'POLYMARKET · MACRO', yes: true, last: 91, err: 9, vol: '$1.2m', when: '2 d ago', hours: 6 }]
  };
  T.liveData.alerts = {
    _quelle: 'live', as_of: '2026-08-07',
    signals: [
      { time: '12:00', rule: 'WHALE PRINT', market: 'Example question', value: '$9k', venue: 'Polymarket', watched: false },
      // Der Tight-Spread-Schalter steht aus: diese Zeile muss verschwinden
      // und die Seite muss sagen, dass sie sie ausblendet.
      { time: '12:01', rule: 'TIGHT SPREAD', market: 'Example question', value: '1.0¢', venue: 'Polymarket', watched: false },
      // Eine Art ohne eigenen Schalter bleibt sichtbar.
      { time: '12:02', rule: 'WATCHED MARKET', market: 'Example question', value: '62.0¢', venue: 'Polymarket', watched: true }
    ],
    // Der Scan fand mehr, als die Tabelle zeigt, und eine Regel wurde gar
    // nicht ausgewertet — beide Faelle muessen sich in der Anzeige trennen.
    rule_counts: { 'WHALE PRINT': 5, 'FAST MOVER': 0, 'ENDING SOON': 120 },
    rules_not_evaluated: ['HOLDER CONCENTRATION'],
    shown_limit: 60
  };
  // Die Form von app/api_views.py copy_payload: Status und Kennzahlen da,
  // eine Order, aber kein Buch — genau der Fall, in dem frueher die
  // Rueckfallwerte der Portfolio- und Fidelity-Reiter erschienen.
  T.liveData.copy = {
    _quelle: 'live', as_of: '2026-08-07',
    status: { running: true, source: '0xab…c · w1', scale: 1, cash: 990, auto_topup: false },
    kpis: {
      equity: 1000, contributions: 1000, pnl: 0, pnl_pct: 0, source_return_pct: 0,
      mirrored: 1, total: 1, skipped: 0, fidelity: 100, config_fidelity: 100, exec_fidelity: 100,
      cash: 990, unrealized: 0, open_positions: 0
    },
    orders: [{ time: '12:00', market: 'Example question', side: 'BUY Yes', theirs: '$100', yours: '$10', status: 'copied' }],
    positions: [], cash_events: [], history: [], equity_curve: []
  };
  T.liveData.track = { _quelle: 'live', wallets: [], watchlist: [] };
  // Zwei Studien mit Nutzlast, damit die Knopfleiste der Forschungsseite
  // gerendert wird: einmal mit Verweis auf die Methodik, einmal auf ihr.
  // Die Review queue traegt einen Fall je Markt UND Zeitfenster: derselbe
  // Slug steht mehrfach da. Die Seite muss auf eine Zeile je Markt
  // zusammenfallen, den Fall mit der hoechsten Prioritaet behalten (Band,
  // dann juengster ts) und die Fensterzahl nennen.
  T.liveData.research['Review queue'] = {
    _quelle: 'live', stand_utc: '2026-08-07T00:00:00+00:00', hinweis: 'Harness payload.',
    faelle: [
      { id: 'c1', markt_slug: 'example-question', score_band: 'high', skeptic_abschlag: 0.1, empfehlung: 'watch',
        zeitfenster: '2026-05-22T20:45:00Z', ts: '2026-08-07T04:30:03+00:00', begruendung: 'kept-high-case' },
      { id: 'c2', markt_slug: 'example-question', score_band: 'low', skeptic_abschlag: -0.2, empfehlung: 'escalate_human',
        zeitfenster: '2026-05-22T21:50:00Z', ts: '2026-08-07T04:30:03+00:00', begruendung: 'dropped-low-case' },
      { id: 'c3', markt_slug: 'example-question', score_band: 'medium', skeptic_abschlag: 0.0, empfehlung: 'check_source',
        zeitfenster: '2026-05-22T21:05:00Z', ts: '2026-08-07T04:30:03+00:00', begruendung: 'dropped-medium-case' },
      { id: 'c4', markt_slug: 'second-question', score_band: 'medium', skeptic_abschlag: 0.0, empfehlung: 'check_source',
        zeitfenster: '2026-05-22T20:45:00Z', ts: '2026-08-06T04:30:03+00:00', begruendung: 'older-medium-case' },
      { id: 'c5', markt_slug: 'second-question', score_band: 'medium', skeptic_abschlag: 0.0, empfehlung: 'watch',
        zeitfenster: '2026-05-23T20:45:00Z', ts: '2026-08-07T04:30:03+00:00', begruendung: 'kept-newer-medium-case' }
    ]
  };
  // Category efficiency in der neuen Form: Horizonte, Kalibrierung, Quelle
  // und Thesis-Schnappschuss. Die alte Form (nur brier_t7/brier_t1) rendert
  // eine eigene Variante weiter unten.
  T.liveData.research['Category efficiency'] = {
    _quelle: 'live', stand_utc: '2026-08-17T00:00:00+00:00', hinweis: 'Harness payload.',
    provenienz: 'terminal/category_efficiency', horizonte_tage: [30, 7, 1],
    quelle: {
      methode: 'Harness method text.', kategorisierung: 'Harness tags.',
      datenfenster: { end_date_min: '2025-08-17T00:00:00Z', abgerufen_utc: '2026-08-17T00:00:00', events_gesichtet: 4, reihenfolge: 'volume desc' },
      auswahl: { max_per_event: 6, max_per_category_long_lived: 250, max_per_category_short_lived: 125, min_volume_usd: 1000, min_markets_per_category: 30 },
      preise: { hourly: 'h', daily: 'd' },
      einschraenkungen: ['Harness caveat.']
    },
    kategorien: [
      { kategorie: 'Politics', brier_t7: 0.1, trefferquote_t7: 0.9, brier_t1: 0.05, trefferquote_t1: 0.95, n_maerkte: 240, n_t7: 200, n_t1: 240,
        anteil_entschieden_t7: 0.4, median_volumen_usd: 12345,
        horizonte: [
          { horizont_tage: 30, brier: 0.2, trefferquote: 0.8, n: 150 },
          { horizont_tage: 7, brier: 0.1, trefferquote: 0.9, n: 200 },
          { horizont_tage: 1, brier: 0.05, trefferquote: 0.95, n: 240 }
        ],
        kalibrierung: { horizont_tage: 7, bins: [
          { von: 0, bis: 0.1, vorhergesagt: 0.03, realisiert: 0.05, realisiert_ci95: [0.01, 0.12], n: 120 },
          { von: 0.9, bis: 1, vorhergesagt: 0.96, realisiert: 0.9, realisiert_ci95: [0.82, 0.95], n: 80 }
        ] } },
      { kategorie: 'Sports', brier_t7: 0.2, trefferquote_t7: 0.7, brier_t1: 0.15, trefferquote_t1: 0.8, n_maerkte: 300, n_t7: 210, n_t1: 300,
        anteil_entschieden_t7: 0.1, median_volumen_usd: 500000,
        horizonte: [
          { horizont_tage: 30, brier: null, trefferquote: null, n: 0 },
          { horizont_tage: 7, brier: 0.2, trefferquote: 0.7, n: 210 },
          { horizont_tage: 1, brier: 0.15, trefferquote: 0.8, n: 300 }
        ],
        kalibrierung: { horizont_tage: 7, bins: [] } }
    ],
    beispiele: [{ kategorie: 'Sport', ereignis: 'Harness example', minuten_bis_konvergenz: 180.4 }],
    thesis_snapshot: { hinweis: 'Old thesis note.', stand_utc: '2026-08-07T04:30:03+00:00',
      kategorien: [{ kategorie: 'Politik', brier_t7: 0.3521, trefferquote_t7: 0.4167, brier_t1: 0.0361, n_maerkte: 73, n_t7: 12 }] }
  };
  T.liveData.research['Methodology'] = {
    _quelle: 'live', stand_utc: '2026-08-07T00:00:00+00:00', hinweis: 'Harness payload.',
    n_eintraege: 3, prompt_hashes: ['a'], output_hashes: ['b'], backend_zaehler: { mock: 3 }
  };
  // Eine Mikrostruktur-Studie mit allem, was die Karte zeigt: Diagramm mit
  // Intervallpunkt, Kennzahlen, Methode und Deutung hinter dem <details>.
  T.liveData.research['Microstructure'] = {
    _quelle: 'live', stand_utc: '2026-08-07T00:00:00+00:00',
    einleitung: 'Harness payload.', hinweis: 'Harness payload.',
    zaehler: { gesamt: 1, nein: 1, ja: 0, offen: 0, kontrolle: 0 },
    fehlend: [],
    studien: [{
      id: 'harness-study', frage: 'Does the harness study render?',
      verdikt: 'No. The harness verdict sits above the chart.', verdikt_art: 'nein',
      einfach: 'Out of 7 firings the harness pointed the right way 4 times.',
      analyse: [{ schluessel: 'gemessen', titel: 'What was measured', text: 'Harness method text.' }],
      interpretation: [{ art: 'lesart', titel: 'What it suggests', text: 'Harness reading.' }],
      zahlen: [{ label: 'Hit rate', wert: 57.1, einheit: '%' }],
      diagramm: {
        art: 'intervall', titel: 'Harness interval', einheit: 'cents',
        referenz: 0.0, referenz_label: 'break even',
        punkte: [{ label: 'All firings', wert: -2.5, von: -2.6, bis: -2.4 }]
      },
      details: { titel: 'Harness rows', spalten: ['A', 'B'], zeilen: [['x', '1']] },
      basis: { beobachtungen: 7, fenster: '2026-07-18 to 2026-07-28' },
      report: 'docs/research/README.md', modul: 'src/orderflow_study.py'
    }]
  };
  // Live runs: zwei Laeufe mit Fills und zwei ohne. Die Seite muss daraus
  // die Treppenkurve, die vollen Karten und die Einzeiler-Liste bauen.
  T.liveData.research['Live runs'] = {
    _quelle: 'live', stand_utc: '2026-08-07T00:00:00+00:00', hinweis: 'Harness payload.',
    kennzeichnung: 'live/descriptive',
    // Beide PnL-Zahlen plus wallet_kaeufe_usd fuer die Abgleichszeile.
    aggregat: {
      n_runs: 4, n_wetten: 2, gewonnen: 2, verloren: 0, offen: 0,
      einsatz_usd: 40, realisierter_pnl_usd: 24, offener_einsatz_usd: 0,
      wallet_netto_usd: 20, wallet_kaeufe_usd: 30, wallet_abgleich_stand: '2026-07-18'
    },
    runs: [
      {
        // Race-Felder je Wette (fremde_davor, verfolger_s), Preispfad nach
        // dem Fill, Repricing-Punkte und ein Event-Slug fuer den Link.
        profil: 'harness_a', episode_titel: 'Run with a fill', modus: 'live',
        event_slug: 'harness-event-a', drop_quelle: 'libsyn_rss',
        pubdate_utc: '2026-07-01T00:00:00+00:00', drop_erkannt_utc: '2026-07-01T00:00:00Z',
        n_entscheidungen: 5, eingepreist: 5, einsatz_usd: 20, realisierter_pnl_usd: 14, wallet_netto_usd: 12,
        wetten: [{ frage: 'Will the harness say "yes"?', seite: 'YES', entscheidungs_preis: 0.5,
                   avg_fill_preis: 0.5, einsatz_usd: 20, aufgeloest: true, gewonnen: true, pnl_usd: 14,
                   fill_ts_utc: '2026-07-01T00:00:10Z', fremde_davor: 0, verfolger_s: 30, tape_rang: 1,
                   preis_nach_fill: { 0: 0.5, 30: 0.55, 60: 0.6, 120: 0.7, 300: 0.8, 900: 0.9 } }],
        race: { wetten_mit_tape: 1, first_on: 1, fremde_trades_vor_uns: 0, median_verfolger_s: 30 },
        repricing: [{ frage: 'Will the harness say "yes"?', seite: 'YES', time_to_priced_s: 120, fill_nach_s: 10,
                      punkte: [[10, 0.5], [60, 0.7], [120, 0.9]] }]
      },
      {
        // Interner Klammerzusatz im Titel: muss aus dem sichtbaren Titel
        // verschwinden.
        profil: 'harness_b', episode_titel: 'Second run with a fill (URL-Prober)', modus: 'live',
        drop_quelle: 'mp3_url_prober',
        pubdate_utc: '2026-07-02T00:00:00+00:00', n_entscheidungen: 3, eingepreist: 3,
        einsatz_usd: 20, realisierter_pnl_usd: 10,
        wetten: [{ frage: 'Will it say yes twice?', seite: 'YES', entscheidungs_preis: 0.6,
                   avg_fill_preis: 0.6, einsatz_usd: 20, aufgeloest: true, gewonnen: true, pnl_usd: 10,
                   fill_ts_utc: '2026-07-02T00:00:10Z', fremde_davor: 2, verfolger_s: 60, tape_rang: 3,
                   preis_nach_fill: { 0: null, 30: null, 60: null, 120: null, 300: null, 900: 0.95 } }],
        race: { wetten_mit_tape: 1, first_on: 0, fremde_trades_vor_uns: 2, median_verfolger_s: 60 },
        repricing: []
      },
      {
        profil: 'harness_c', episode_titel: 'Run without a fill (kanalseite)', modus: 'live',
        drop_quelle: 'youtube',
        pubdate_utc: '2026-07-03T00:00:00+00:00', n_entscheidungen: 160, eingepreist: 160,
        einsatz_usd: 0, realisierter_pnl_usd: 0, wetten: []
      },
      {
        profil: 'harness_d', episode_titel: 'Second run without a fill', modus: 'live',
        pubdate_utc: '2026-07-04T00:00:00+00:00', n_entscheidungen: 7, eingepreist: 7,
        einsatz_usd: 0, realisierter_pnl_usd: 0, wetten: []
      }
    ],
    // The wallet ledger as the API merges it (extras.wallet_ledger; the
    // static site fetches wallet_ledger.json into the same shape): three
    // events — a mixed bot event, a discretionary one with the Curtis note,
    // a pilot one — and the aggregate the KPI row reads.
    extras: {
      wallet_ledger: {
        hinweis: 'Harness ledger note.', stand_utc: '2026-08-17T01:02:03+00:00',
        wallet: '0x29afe1bf37700768a640a08f1b35dad5f202f88d', kennzeichnung: 'wallet/public-api',
        aggregat: {
          einzahlungen_usd: null, kaeufe_usd: 156.35, verkaeufe_usd: 20, einloesungen_usd: 184.98,
          netto_cashflow_usd: 48.63, n_events: 3, n_maerkte: 4, n_trades: 6, n_kaeufe: 5, n_verkaeufe: 1, n_einloesungen: 3,
          positionen: { won: 2, lost: 1, flat: 0, worthless: 1, open: 0, unknown: 0 },
          positionen_gewonnen: 2, positionen_verloren: 2, positionen_wertlos: 1, positionen_offen: 0, positionen_flat: 0,
          closed_positions_capped: false, erste_aktivitaet_utc: '2026-07-18T00:48:16Z', letzte_aktivitaet_utc: '2026-08-11T17:03:24Z',
          nach_typ: { bot: { events: 1, maerkte: 2 }, discretionary: { events: 1, maerkte: 1 }, pilot: { events: 1, maerkte: 1 } }
        },
        events: [
          { event_slug: 'harness-event-a', titel: 'Harness bot event', url: 'https://polymarket.com/event/harness-event-a',
            typ: 'bot', typ_mix: 'bot + discretionary', run_profil: 'harness_a', run_im_log: true,
            von_utc: '2026-07-18T00:48:16Z', bis_utc: '2026-07-24T12:00:00Z', n_maerkte: 2, n_trades: 3, n_einloesungen: 2,
            einsatz_usd: 51.34, verkaeufe_usd: 20, einloesungen_usd: 79.81, netto_cash_usd: 48.47, pnl_usd: 45.97,
            status: { won: 1, lost: 0, flat: 0, worthless: 1, open: 0, unknown: 0 }, status_text: '1 won · 1 worthless',
            notes: ['1 of 2 markets are not in the run log of \'harness_a\' (discretionary).'],
            maerkte: [
              { titel: 'Will the harness say "yes"?', seite: 'Yes', zuordnung: 'bot', run_profil: 'harness_a', avg_preis: 0.5, shares: 82.68, einsatz_usd: 41.34, pnl_usd: 55.97, pnl_art: 'realised (API realizedPnl)', status: 'won' },
              { titel: 'Will the harness say "extra"?', seite: 'No', zuordnung: 'discretionary', run_profil: '', avg_preis: 0.5, shares: 20, einsatz_usd: 10, pnl_usd: -10, pnl_art: 'position resolved against and not redeemed (API cashPnl)', status: 'worthless' }
            ] },
          { event_slug: 'harness-curtis-e3', titel: 'Harness Curtis E3 event', url: 'https://polymarket.com/event/harness-curtis-e3',
            typ: 'discretionary', typ_mix: '', run_profil: '', run_im_log: false,
            von_utc: '2026-08-07T00:00:00Z', bis_utc: '2026-08-11T17:03:24Z', n_maerkte: 1, n_trades: 2, n_einloesungen: 0,
            einsatz_usd: 100, verkaeufe_usd: 0, einloesungen_usd: 100, netto_cash_usd: 0, pnl_usd: 0.97,
            status: { won: 1, lost: 0, flat: 0, worthless: 0, open: 0, unknown: 0 }, status_text: '1 won',
            notes: ['Forecasts pre-registered before airing: https://github.com/Pablozh123/multi-agent-orchestration-informational-efficiency/blob/main/docs/project/PREREG_CURTIS_E3_2026-08-07.md'],
            maerkte: [{ titel: 'Will anyone say "Harness" during President Curtis E3 S1?', seite: 'Yes', zuordnung: 'discretionary', run_profil: '', avg_preis: 0.95, shares: 105.3, einsatz_usd: 100, pnl_usd: 0.97, pnl_art: 'realised (API realizedPnl)', status: 'won' }] },
          { event_slug: 'harness-pilot-gdp', titel: 'Harness pilot GDP event', url: 'https://polymarket.com/event/harness-pilot-gdp',
            typ: 'pilot', typ_mix: '', run_profil: '', run_im_log: false,
            von_utc: '2026-07-22T13:07:54Z', bis_utc: '2026-07-30T00:00:00Z', n_maerkte: 1, n_trades: 1, n_einloesungen: 1,
            einsatz_usd: 5.01, verkaeufe_usd: 0, einloesungen_usd: 5.17, netto_cash_usd: 0.16, pnl_usd: 0.16,
            status: { won: 1, lost: 0, flat: 0, worthless: 0, open: 0, unknown: 0 }, status_text: '1 won',
            notes: ['Pre-registered small-stake pilot, rules frozen 2026-07-18; one of the 20 pilot trades of 2026-07-22.'],
            maerkte: [{ titel: 'Will US GDP growth in Q2 2026 be less than 1.0%?', seite: 'No', zuordnung: 'pilot', run_profil: '', avg_preis: 0.967, shares: 5.18, einsatz_usd: 5.01, pnl_usd: 0.16, pnl_art: 'realised (API realizedPnl)', status: 'won' }] }
        ]
      }
    }
  };
  // Mentions latency: zwei Ereignisse mit Zeiten, eines ohne Reaktion, ein
  // Ausschluss mit Statuscode. Median von 0.5 und 10 ist 5.25.
  T.liveData.research['Mentions latency'] = {
    _quelle: 'live', stand_utc: '2026-08-07T04:30:03+00:00', hinweis: 'Harness mentions note.',
    faelle: [
      { event: 'harness_fast', minuten_bis_erste_reaktion: 0.5, minuten_bis_konvergenz: 30, stunden_im_handelbaren_fenster: 0.5, korrekt_aufgeloestes_outcome: 'YES', status: 'ok' },
      { event: 'harness_slow', minuten_bis_erste_reaktion: 10, minuten_bis_konvergenz: 600, stunden_im_handelbaren_fenster: 9.8, korrekt_aufgeloestes_outcome: 'NO', status: 'ok' },
      { event: 'harness_none', minuten_bis_erste_reaktion: null, minuten_bis_konvergenz: null, stunden_im_handelbaren_fenster: null, korrekt_aufgeloestes_outcome: 'NO', status: 'no_reaction' }
    ],
    ausschluesse: [{ event: 'harness_excluded', status: 'ausgeschlossen_zuordnungsambiguitaet' }]
  };
  // Pilot: 20 Trades mit deutschem Exit-Grund und Signal-/Fill-Preis, die
  // Watcher-Zaehler des letzten Laufs. Kein `auswertung` (das haengt die
  // API an) und keine Serie — die Seite muss das sagen.
  const pilotTrades = [];
  for (let i = 0; i < 20; i += 1) {
    pilotTrades.push({
      zeitstempel_utc: '2026-07-22T13:07:54Z', markt_id: String(1000 + i), markt_frage: 'Harness pilot market ' + (i + 1) + '?',
      arm: 'arm2', signal_regel: 'arm2_favorit_090_097_max21d', seite: 'No',
      signalpreis: '0.930', ausfuehrungspreis: i % 2 ? '0.950' : '0.920', groesse_usd: '5.0',
      slippage: i % 2 ? '0.02' : '-0.01', exit_zeit_utc: '', exit_preis: '',
      exit_grund: 'haelt bis zur Aufloesung (Protokoll)', bemerkung: 'automatisiert (V3): fill'
    });
  }
  T.liveData.research['Pilot'] = {
    _quelle: 'live', stand_utc: '2026-08-07T04:33:12+00:00', hinweis: 'Harness pilot note.', kennzeichnung: 'pilot/preregistered',
    protokoll: { budget_usdc: 100, einsatz_je_trade_usdc: 10, regel_freeze_datum: '2026-07-18', handelsfenster_bis: '2026-08-01' },
    watcher_lauf_ts_utc: '2026-08-01T04:33:19Z',
    watcher_statistik: { maerkte: 1992, arm2_bereits_abgelaufen: 1155, gekappt: 415 },
    signal_zaehler: { 'arm2:signal': 322, 'arm1:kandidat_referenz_pruefen': 1 },
    signale_neueste: [],
    trades: pilotTrades
  };
  // Pipeline forward: zwei Laeufe mit ihren Eintraegen (die Seite zaehlt
  // ueber alle Laeufe, nicht ueber die Spiegel-Liste oben), ein Kauf.
  T.liveData.research['Pipeline forward'] = {
    _quelle: 'live', stand_utc: '2026-08-07T04:30:03+00:00', hinweis: 'Harness pipeline note.', kennzeichnung: 'observed/paper',
    eintraege: [{ action: 'NONE', reason: 'kein_yes_ask' }],
    laeufe: [
      { profil: 'harness_run_1', n_eintraege: 3, n_kaeufe: 1, extraktion_gekauft_usd: 16.08, extraktionsquote: 1,
        eintraege: [{ action: 'NONE', reason: 'kein_yes_ask' }, { action: 'NONE', reason: 'kein_yes_ask' }, { action: 'YES', reason: 'count 2 >= ziel 1, ask 0.64 <= 0.9', size_usd: 16.08 }] },
      { profil: 'harness_run_2', n_eintraege: 2, n_kaeufe: 0, extraktion_gekauft_usd: null, extraktionsquote: null,
        eintraege: [{ action: 'NONE', reason: 'yes_ask 0.99 > 0.9' }, { action: 'NONE', reason: 'kein_yes_ask' }] }
    ]
  };
  // Postmortems: eine Referenz mit PR, Commit und Repo-Pfad — die Seite
  // macht daraus Links, der Rest bleibt Text.
  T.liveData.research['Postmortems'] = {
    _quelle: 'live', stand_utc: '2026-08-07T04:33:12+00:00', hinweis: 'Harness postmortem note.', kennzeichnung: 'curated/postmortem',
    eintraege: [{ datum: '2026-07-18', profil: 'harness_a', achse: 'Evaluation', titel: 'Harness incident',
      was_passierte: 'x', auswirkung: 'y', fix: 'z',
      referenz: 'PR #12 (fill accounting); commit 8af07d6 (heartbeat); docs/research/ONE_PAGER.md; plain note' }]
  };
  return T;
}

function rendern(T) {
  const raus = {};
  Object.entries(SEITEN).forEach(([name, fn]) => {
    try {
      raus[name] = String(fn(T));
    } catch (err) {
      raus[name] = 'RENDER-FEHLER: ' + (err && err.stack ? err.stack : err);
    }
  });
  // Overlays: Detailpanel je Art und die Suche.
  try {
    T.state.detail = { kind: 'market', id: 'm1' };
    raus['_detail_markt'] = String(renderDetail(T));
    T.state.detail = { kind: 'wallet', id: 'w1' };
    raus['_detail_wallet'] = String(renderDetail(T));
    T.state.detail = null;
    T.state.searchOpen = true;
    raus['_suche'] = String(renderSearch(T));
    T.state.searchOpen = false;
  } catch (err) {
    raus['_overlays'] = 'RENDER-FEHLER: ' + (err && err.stack ? err.stack : err);
  }
  // Reiter innerhalb einer Seite sind eigene Ansichten mit eigenen
  // Rueckfaellen. Sie werden hier einzeln durchgerendert.
  const varianten = [
    ['backtester_advanced', 'backtester', { advancedOpen: true }],
    ['backtester_flat_fee', 'backtester', { advancedOpen: true, btFeeModel: 'flat' }],
    ['alerts_rules', 'alerts', { alertTab: 'rules' }],
    ['alerts_deliveries', 'alerts', { alertTab: 'deliveries' }],
    ['risk_wallets', 'risk', { riskView: 'wallets' }],
    ['risk_fresh', 'risk', { riskView: 'fresh' }],
    ['risk_timing', 'risk', { riskView: 'timing' }],
    ['risk_network', 'risk', { riskView: 'network' }],
    ['runs_runs', 'research', { researchTab: 3, liveTab: 'runs' }],
    ['runs_timing', 'research', { researchTab: 3, liveTab: 'timing' }],
    ['runs_sim', 'research', { researchTab: 3, liveTab: 'sim' }],
    ['runs_calib', 'research', { researchTab: 3, liveTab: 'calib' }],
    ['runs_record', 'research', { researchTab: 3, liveTab: 'record' }],
    // Many runs: 15 with a fill and 6 without, like the 21 of runs.json. Every
    // one must appear — a card per run with fills, a line per run without —
    // and the ledger section must fall back to its file-naming line when the
    // payload carries no extras. Only swapped in when a Live-runs payload is
    // there (live mode); in the empty mode the page keeps its empty state.
    ['runs_runs_many', 'research', { researchTab: 3, liveTab: 'runs' }, null, (T) => {
      if (!T.liveData.research['Live runs']) return null;
      const alt = T.liveData.research['Live runs'];
      const runs = [];
      for (let i = 0; i < 15; i += 1) {
        runs.push({
          profil: 'many_fill_' + i, episode_titel: 'Many-run card ' + i, modus: 'live', event_slug: 'many-event-' + i,
          pubdate_utc: '2026-07-' + String(1 + i).padStart(2, '0') + 'T00:00:00+00:00',
          n_entscheidungen: 3, eingepreist: 3, einsatz_usd: 10, realisierter_pnl_usd: 1,
          wetten: [{ frage: 'Will many-run ' + i + ' say "yes"?', seite: 'YES', entscheidungs_preis: 0.5, avg_fill_preis: 0.5,
                     einsatz_usd: 10, aufgeloest: true, gewonnen: true, pnl_usd: 1, fill_ts_utc: '2026-07-' + String(1 + i).padStart(2, '0') + 'T00:00:10Z' }]
        });
      }
      for (let i = 0; i < 6; i += 1) {
        runs.push({ profil: 'many_empty_' + i, episode_titel: 'Many-run line ' + i, modus: 'live',
          pubdate_utc: '2026-07-2' + i + 'T00:00:00+00:00', n_entscheidungen: 2, eingepreist: 2, einsatz_usd: 0, realisierter_pnl_usd: 0, wetten: [] });
      }
      T.liveData.research['Live runs'] = {
        _quelle: 'live', stand_utc: '2026-08-07T00:00:00+00:00', hinweis: 'Many-run harness payload.', kennzeichnung: 'live/descriptive',
        aggregat: { n_runs: 21, n_wetten: 15, gewonnen: 15, verloren: 0, offen: 0, einsatz_usd: 150, realisierter_pnl_usd: 15, offener_einsatz_usd: 0 },
        runs
      };
      return () => { T.liveData.research['Live runs'] = alt; };
    }],
    // Jede weitere Studie einmal, damit ein neuer Eintrag in STUDIEN ohne
    // Renderer oder mit falschem Index hier auffaellt.
    ['research_microstructure', 'research', { researchTab: STUDIEN.findIndex((st) => st.tab === 'Microstructure') }],
    ['research_postmortems', 'research', { researchTab: STUDIEN.findIndex((st) => st.tab === 'Postmortems') }],
    ['research_field_notes', 'research', { researchTab: STUDIEN.findIndex((st) => st.tab === 'Field notes') }],
    ['research_methodology', 'research', { researchTab: STUDIEN.findIndex((st) => st.tab === 'Methodology') }],
    ['research_mentions_latency', 'research', { researchTab: STUDIEN.findIndex((st) => st.tab === 'Mentions latency') }],
    ['research_pilot', 'research', { researchTab: STUDIEN.findIndex((st) => st.tab === 'Pilot') }],
    ['research_pipeline_forward', 'research', { researchTab: STUDIEN.findIndex((st) => st.tab === 'Pipeline forward') }],
    ['research_category_efficiency', 'research', { researchTab: STUDIEN.findIndex((st) => st.tab === 'Category efficiency') }],
    // Dieselbe Seite mit der alten kategorie_karte.json (nur brier_t7 und
    // brier_t1, keine Horizonte, keine Kalibrierung): sie muss weiter
    // rendern, ohne Kurve und ohne erfundene Horizonte. Das vierte Feld
    // ersetzt die Forschungs-Nutzlast fuer diese eine Variante.
    ['research_category_efficiency_alt', 'research', { researchTab: STUDIEN.findIndex((st) => st.tab === 'Category efficiency') },
      ['Category efficiency', {
        _quelle: 'live', stand_utc: '2026-08-07T04:30:03+00:00', hinweis: 'Old-shape harness payload.',
        kategorien: [
          { kategorie: 'Politik', brier_t7: 0.3521, trefferquote_t7: 0.4167, brier_t1: 0.0361, trefferquote_t1: 0.9315, n_maerkte: 73, n_t7: 12, median_volumen_usd: 9883931.33 },
          { kategorie: 'Sport', brier_t7: 0.042, trefferquote_t7: 0.9231, brier_t1: 0.0412, trefferquote_t1: 0.95, n_maerkte: 60, n_t7: 26, median_volumen_usd: 4750770.96 }
        ],
        beispiele: []
      }]],
    ['copy_fidelity', 'copy', { copyTab: 'fidelity' }],
    ['portfolio_exposure', 'portfolio', { portTab: 'exposure' }],
    // Live tape / Whale flow narrowed by a category chip: the harness tape
    // carries one Macro print (with wallet) and one Crypto print (Kalshi, no
    // wallet). Crypto on the tape shows the Kalshi print; on Whale flow it
    // has nothing to group and must say so.
    ['flow_cat_crypto', 'flow', { tapeCat: 'Crypto' }],
    ['flow_cat_macro', 'flow', { tapeCat: 'Macro' }],
    ['whale_cat_macro', 'whale', { whaleCat: 'Macro' }],
    ['whale_cat_crypto', 'whale', { whaleCat: 'Crypto' }],
    // Cross-venue: request in flight (no answer recorded), and answered with
    // nothing clearing the gate. Both are separate from the failed request.
    ['cross_loading', 'cross', {}, null, (T) => {
      const alt = { pairs: T.crossPairs, hk: T.herkunft.cross, live: T.liveData.cross };
      T.crossPairs = []; T.herkunft.cross = null; T.liveData.cross = null;
      return () => { T.crossPairs = alt.pairs; T.herkunft.cross = alt.hk; T.liveData.cross = alt.live; };
    }],
    ['cross_gate_empty', 'cross', {}, null, (T) => {
      const alt = { pairs: T.crossPairs, hk: T.herkunft.cross, live: T.liveData.cross };
      T.crossPairs = []; T.herkunft.cross = { quelle: 'leer' };
      T.liveData.cross = { _quelle: 'live', rows: [], candidates_before_gate: 7, gate: { min_similarity: 0.5, require_volume_both: true } };
      return () => { T.crossPairs = alt.pairs; T.herkunft.cross = alt.hk; T.liveData.cross = alt.live; };
    }],
    // Backtester run states without a result: running, rate-limited, error.
    ['backtester_running', 'backtester', { btRun: 'running' }],
    ['backtester_rate_limited', 'backtester', { btRun: 'error', btError: 'rate-limited', btRetryIn: 7 }],
    ['backtester_error', 'backtester', { btRun: 'error', btError: 'HTTP 502' }],
    // Landing with one payload missing (runs failed) and one still loading.
    ['overview_partial', 'overview', {}, null, (T) => {
      const alt = T.landing;
      T.landing = {
        micro: alt.micro, runs: null, notes: null,
        herkunft: { micro: alt.herkunft.micro, runs: { quelle: 'fehler', fehler: 'HTTP 404' }, notes: null }
      };
      return () => { T.landing = alt; };
    }],
    // Risk screen while /api/risk is still building (no answer, no herkunft).
    ['risk_loading', 'risk', {}, null, (T) => {
      const alt = { live: T.liveData.risk, hk: T.herkunft.risks, risks: T.risks };
      T.liveData.risk = null; T.herkunft.risks = null; T.risks = [];
      return () => { T.liveData.risk = alt.live; T.herkunft.risks = alt.hk; T.risks = alt.risks; };
    }],
    // Flag log tab: with rows (live payload above / null in the empty run),
    // still loading, answered empty, and failed. The log is fetched only when
    // the tab is opened, so "loading" is the state right after the click.
    ['risk_log', 'risk', { riskView: 'log' }],
    ['risk_log_loading', 'risk', { riskView: 'log' }, null, (T) => {
      const alt = T.liveData.riskLog;
      T.liveData.riskLog = null;
      return () => { T.liveData.riskLog = alt; };
    }],
    ['risk_log_empty', 'risk', { riskView: 'log' }, null, (T) => {
      const alt = T.liveData.riskLog;
      T.liveData.riskLog = { _quelle: 'live', rows: [], count: 0, enriched: 0, enrich_max: 30, min_score: 40, dedupe_hours: 6, sampler_interval_min: 0, as_of: '2026-08-17 10:30 UTC' };
      return () => { T.liveData.riskLog = alt; };
    }],
    ['risk_log_error', 'risk', { riskView: 'log' }, null, (T) => {
      const alt = T.liveData.riskLog;
      T.liveData.riskLog = { _quelle: 'fehler', _fehler: 'HTTP 503' };
      return () => { T.liveData.riskLog = alt; };
    }]
  ];
  varianten.forEach(([name, seite, zustand, nutzlast, vorbereiten]) => {
    const vorher = Object.assign({}, T.state);
    Object.assign(T.state, zustand);
    let vorherNutzlast;
    if (nutzlast) {
      vorherNutzlast = T.liveData.research[nutzlast[0]];
      T.liveData.research[nutzlast[0]] = nutzlast[1];
    }
    const zurueck = vorbereiten ? vorbereiten(T) : null;
    try {
      raus[name] = String(SEITEN[seite](T));
    } catch (err) {
      raus[name] = 'RENDER-FEHLER: ' + (err && err.stack ? err.stack : err);
    }
    if (zurueck) zurueck();
    if (nutzlast) T.liveData.research[nutzlast[0]] = vorherNutzlast;
    T.state = vorher;
  });
  // Pure helpers of the landing, called directly: the sub-line and the
  // verdict counts derived from the payload (never typed in).
  raus['_landing_subline'] = landingSubline(T.landing);
  raus['_verdict_counts'] = JSON.stringify(verdictCounts(T.landing ? T.landing.micro : null));
  // Die reine Zusammenfassung der Review queue, direkt aufgerufen: eine
  // Zeile je Slug, der Fall mit der hoechsten Prioritaet, Fensterzahl und
  // -spanne. Ohne Nutzlast eine leere Liste.
  const faelle = T.liveData.research['Review queue'] ? T.liveData.research['Review queue'].faelle : null;
  raus['_collapse_queue'] = JSON.stringify(collapseQueue(faelle));
  return raus;
}

const ergebnis = { leer: rendern(neuesT()), live: rendern(mitDaten(neuesT())) };
process.stdout.write(JSON.stringify(ergebnis));
