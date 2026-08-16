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
import { renderOverview, renderMarkets, renderFlow, renderCross, renderResolved } from '../web/js/pages/core_pages.js';
import { renderTraders, renderWhale, renderRisk, renderTrack } from '../web/js/pages/trader_pages.js';
import { renderBacktester, renderCopy, renderPortfolio } from '../web/js/pages/trading_pages.js';
import { renderAlerts, renderResearch, renderSettings } from '../web/js/pages/system_pages.js';
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
      marketFiltersOpen: false, mPlatform: 'all', mStatus: 'active', mProb: 'all',
      mSpread: 'all', mLiq: 'all', mVol: 'all', mEnds: 'all', mAge: 'all',
      mExclude: [], mView: 'table', mQuick: 'trending',
      crossQuery: '', crossSim: 0.30, crossMaxPairs: 50, crossMinGap: 0, crossLower: 'any',
      crossPmVol: 0, crossKsVol: 0, crossMinPrice: 0, crossMaxPrice: 100,
      marketSort: 'volume', marketQuery: '', traderRank: 'pnl', traderQuery: '',
      traderView: 'table', traderCols: 'default', traderPeriod: 'ALL',
      traderActiveOnly: false, traderBotsOnly: false, traderFiltersOpen: false,
      tPnl: 'all', tVol: 'all', tPos: 'all', tTraits: [], tWin: 'all', tClosed: 'all',
      tBal: 'all', tAge: 'all', tAssets: 'all', tBotScore: 65,
      tEnrich: { positions: true, winrates: true, accounts: false },
      riskView: 'events', riskAgeCheck: false, copyTab: 'orders', copyQuery: '',
      copySide: 'all', copyStatus2: 'all', copyMin: 'all',
      portTab: 'positions', portQuery: '', portSource: 'all', portSide: 'all', portLosers: false,
      tapeQuery: '', tapePlatform: 'all', tapeSide: 'all', tapeOutcome: 'all',
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
      clock: '00:00', live: 'waiting', liveAsOf: ''
    },
    markets: [], marketExtra: {}, traders: [], traderExtra: {}, risks: [], tape: [],
    crossPairs: [], studies: STUDIEN,
    herkunft: { markets: null, tape: null, traders: null, risks: null, cross: null },
    liveData: { leaderboard: null, cross: null, risk: null, alerts: null, copy: null, portfolio: null, research: {}, backtest: null, walletDetail: {} },
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
      title: m.title, meta: m.venue + ' · ' + m.cat, sparkPoints: spark(m.spark || [0, 1]),
      color: '#C8F542', priceLabel: m.yes + '¢', changeLabel: '+' + m.chg + '¢',
      changeStyle: M, volLabel: money(m.vol), ends: m.ends, act: ''
    }),
    marketExtraOf: () => ({ spread: 5, age: 100, endsDays: 30, saved: false, pos: false }),
    traderExtraOf: () => ({ positions: 0, assets: 0, balance: 0, ageDays: 100, traits: [], bot: 20, active: 10 }),
    tapeFiltered() { return this.tape.filter((t) => t.size >= this.state.tapeMin); },
    tapeRowView: (t) => ({
      ago: t.ago, wallet: t.wallet, market: t.market, side: t.side, price: t.price,
      size: money(t.size), venue: t.venue, sideStyle: M, act: ''
    }),
    riskCardView: (r) => ({
      kind: r.kind, score: r.score, market: r.market, detail: r.detail, wallets: r.wallets,
      notional: r.notional, window: r.window, venue: r.venue, kindStyle: M, scoreStyle: M, act: ''
    }),
    go: () => {},
    openWallet: () => {},
    openMarket: () => {}
  };
}

// Eine kleine, aber echte Nutzlast: ein Markt, ein Print, eine Wallet.
function mitDaten(T) {
  T.markets = [{
    id: 'm1', title: 'Example question', venue: 'Polymarket', cat: 'Macro',
    yes: 62, chg: 3, vol: 125000, liq: 40000, ends: 'Dec 2026', url: '', spark: [19, 19]
  }];
  T.marketExtra = { m1: { spread: 2, age: 40, endsDays: 120, saved: false, pos: false } };
  T.herkunft.markets = { quelle: 'live' };
  T.tape = [{
    ago: '2 min ago', mins: 2, wallet: 'w1', walletAddress: '0xabc',
    market: 'Example question', side: 'BUY Yes', price: '62.0¢', size: 9000,
    venue: 'Polymarket', tracked: false
  }];
  T.herkunft.tape = { quelle: 'live' };
  T.traders = [{
    name: 'w1', wallet: '0xab…c', walletFull: '0xabc', pnl: 12000, win: 0.6,
    resolved: 300, vol: 90000, score: 71, scoreN: 300, scoreCi: null, sampleBadge: null, tags: ''
  }];
  T.herkunft.traders = { quelle: 'live' };
  T.liveData.leaderboard = { _quelle: 'live', rows: [], as_of: '2026-08-07' };
  T.risks = [{
    kind: 'TIMING', score: 61, market: 'Example question', detail: 'three wallets, one side',
    wallets: 3, notional: '$40k', window: '2 h', venue: 'Polymarket', sev: 'medium'
  }];
  T.herkunft.risks = { quelle: 'live' };
  T.liveData.risk = {
    _quelle: 'live',
    kpis: { events_screened: 12, high_risk_events: 1, high_risk_wallets: 2, fresh_clusters: 0, coordinated_clusters: 0 },
    wallets: [], fresh: [], timing: [], network: [], graph: null, matrix: {}
  };
  T.crossPairs = [{ event: 'Example question', cat: 'Macro', pm: 62, ks: 58, sim: 0.44, pmVol: 1200000, ksVol: 300000, held: '2 h' }];
  T.herkunft.cross = { quelle: 'live' };
  T.liveData.cross = { _quelle: 'live', rows: T.crossPairs };
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
  T.liveData.research['Review queue'] = {
    _quelle: 'live', stand_utc: '2026-08-07T00:00:00+00:00', hinweis: 'Harness payload.',
    faelle: [{ id: 'c1', markt_slug: 'example-question', score_band: 'high', skeptic_abschlag: 0.1, empfehlung: 'watch' }]
  };
  T.liveData.research['Methodology'] = {
    _quelle: 'live', stand_utc: '2026-08-07T00:00:00+00:00', hinweis: 'Harness payload.',
    n_eintraege: 3, prompt_hashes: ['a'], output_hashes: ['b'], backend_zaehler: { mock: 3 }
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
    // Jede weitere Studie einmal, damit ein neuer Eintrag in STUDIEN ohne
    // Renderer oder mit falschem Index hier auffaellt.
    ['research_postmortems', 'research', { researchTab: STUDIEN.findIndex((st) => st.tab === 'Postmortems') }],
    ['research_field_notes', 'research', { researchTab: STUDIEN.findIndex((st) => st.tab === 'Field notes') }],
    ['research_methodology', 'research', { researchTab: STUDIEN.findIndex((st) => st.tab === 'Methodology') }],
    ['copy_fidelity', 'copy', { copyTab: 'fidelity' }],
    ['portfolio_exposure', 'portfolio', { portTab: 'exposure' }]
  ];
  varianten.forEach(([name, seite, zustand]) => {
    const vorher = Object.assign({}, T.state);
    Object.assign(T.state, zustand);
    try {
      raus[name] = String(SEITEN[seite](T));
    } catch (err) {
      raus[name] = 'RENDER-FEHLER: ' + (err && err.stack ? err.stack : err);
    }
    T.state = vorher;
  });
  return raus;
}

const ergebnis = { leer: rendern(neuesT()), live: rendern(mitDaten(neuesT())) };
process.stdout.write(JSON.stringify(ergebnis));
