// Rendert jede Seite der Web-Oberflaeche ohne Browser, einmal ganz ohne
// Nutzlast und einmal mit einer minimalen Live-Nutzlast, und schreibt das
// Ergebnis als JSON nach stdout. Der Test in tests/test_web_leerzustand.py
// liest das und prueft, dass ohne Daten keine Zahl erscheint.
//
// app.js kann nicht importiert werden, es mountet sich beim Laden selbst an
// document. Die Seitenmodule sind reine Funktionen ueber ein T-Objekt, also
// wird hier ein T gebaut, das dieselben Felder und Helfer bereitstellt.

import { readFileSync } from 'node:fs';
import { esc, money, num, seriesPoints } from '../web/js/util.js';
import { STUDIEN } from '../web/js/studies.js';
import { renderOverview, renderMarkets, renderFlow, renderCross, renderResolved, landingSubline, verdictCounts } from '../web/js/pages/core_pages.js';
import { renderTraders, renderWhale, renderRisk, renderTrack } from '../web/js/pages/trader_pages.js';
import { renderBacktester, renderCopy, renderPortfolio } from '../web/js/pages/trading_pages.js';
import { renderAlerts, renderResearch, renderSettings, collapseQueue, fillLatenzS } from '../web/js/pages/system_pages.js';
import { renderWallet } from '../web/js/pages/wallet_page.js';
import { renderGraph } from '../web/js/pages/graph_page.js';
import { renderDetail, renderSearch } from '../web/js/overlays.js';
import { healthStand, verdiktSatz, teileChancen } from '../web/js/pages/arb_scan_page.js';

// The arbitrage scanner's file in full (schema arb_scan/1), kept under tests/
// so the harness never depends on what public/data happens to hold. Parsed
// once; every use below takes its own copy.
const ARB_FIXTURE = JSON.parse(readFileSync(new URL('./fixtures/arb_scan_example.json', import.meta.url), 'utf8'));
const arbNutzlast = () => Object.assign({ _quelle: 'live' }, JSON.parse(JSON.stringify(ARB_FIXTURE)));
// Our resolution pass over the same journal (schema arb_resolutions/1),
// joined onto the paper book by trade_id.
const AUF_FIXTURE = JSON.parse(readFileSync(new URL('./fixtures/arb_resolutions_example.json', import.meta.url), 'utf8'));
const aufNutzlast = () => Object.assign({ _quelle: 'live' }, JSON.parse(JSON.stringify(AUF_FIXTURE)));
const aufMit = (p) => (T) => { const alt = T.liveData.arbResolutions; T.liveData.arbResolutions = p; return () => { T.liveData.arbResolutions = alt; }; };
// Swap the scanner payload on the Cross-venue page for one variant.
const arbMit = (p) => (T) => { const alt = T.liveData.arbScan; T.liveData.arbScan = p; return () => { T.liveData.arbScan = alt; }; };

// 150 gelieferte Signalzeilen: mehr als eine Seite (60), weniger als der
// Schnitt des Endpunkts (400). Der zweite Aufruf setzt den Seitenzaehler.
function viele_signale(seite) {
  return (T) => {
    const alt = T.liveData.alerts;
    const altSeite = T.state.alertPage;
    const zeilen = [];
    for (let i = 0; i < 150; i += 1) {
      zeilen.push({
        time: '12:00', rule: 'WHALE PRINT', market: 'Question ' + i,
        value: '$9k', venue: 'Polymarket', watched: false
      });
    }
    T.liveData.alerts = Object.assign({}, alt, {
      signals: zeilen, page_size: 60, delivered_cap: 400,
      rule_counts: { 'WHALE PRINT': 150 }
    });
    T.state.alertPage = seite;
    return () => { T.liveData.alerts = alt; T.state.alertPage = altSeite; };
  };
}

const SEITEN = {
  overview: renderOverview, markets: renderMarkets, flow: renderFlow,
  cross: renderCross, resolved: renderResolved,
  traders: renderTraders, whale: renderWhale, risk: renderRisk, track: renderTrack,
  wallet: renderWallet, graph: renderGraph,
  backtester: renderBacktester, copy: renderCopy, portfolio: renderPortfolio,
  alerts: renderAlerts, research: renderResearch, settings: renderSettings
};

function neuesT() {
  const M = "font-family:'IBM Plex Mono',monospace";
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
      riskView: 'events', riskAgeCheck: false, copyTab: 'traders', copyQuery: '',
      copySide: 'all', copyStatus2: 'all', copyMin: 'all',
      copyTrader: 'all', copyForm: { wallet: '', label: '', cash: '1000', note: '' },
      copyEdit: null, copyTopup: null, copySettings: null, copyBusy: '', copyMsg: null, copyToken: '',
      portTab: 'positions', portQuery: '', portSource: 'all', portSide: 'all', portLosers: false,
      tapeQuery: '', tapePlatform: 'all', tapeSide: 'all', tapeOutcome: 'all',
      whaleSort: 'total',
      resQuery: '', resAnswer: 'all', resWindow: 'all', resError: 'all', resSort: 'recent',
      setMarketSample: 250, setTradeSample: 250, setWhale: 2500, setBankroll: 1000,
      setFee: 20, setSlip: 15, alertTab: 'signals', alertQuery: '', alertPlatform: 'all',
      alertType: 'all', alertScope: 'all', alertPage: 1, thMove: 5, thSpread: 3, thWhale: 2500,
      thEnding: 72, thHolder: 40, riskFilter: 'all', riskOpen: {}, detail: null, searchOpen: false,
      searchQuery: '', btStrategy: 'copy', btWindow: 30, btWallet: '0xabc', btSizing: 'fixed',
      btStakeFixed: 25, btStakePct: 2, btStakeMult: 1, btStakeKelly: 5, btCap: 250,
      btExposure: 50, btBankroll: 1000, btFee: 20, btSlip: 15, btCompare: '', btTab: 'log',
      btFeeModel: 'curve',
      advancedOpen: false, sizingSimOpen: false, researchTab: 0, liveTab: 'runs',
      walletAddr: '', walletInput: '', walletRecent: [], walletPosSort: 'value', walletTab: 'overview', walletTreemap: 'all', walletPosView: 'bars', walletSimilarQuery: '',
      alertsOn: { movers: true, volume: true, whales: true, spreads: false, holders: false, endings: true },
      settingsOn: { telegram: true, autotop: false, kalshi: true, sports: false, cache: true, admin: true },
      clock: '00:00', live: 'waiting', liveAsOf: '', tapeAsOf: ''
    },
    markets: [], marketExtra: {}, traders: [], risks: [], tape: [],
    crossPairs: [], studies: STUDIEN,
    herkunft: { markets: null, tape: null, traders: null, risks: null, cross: null },
    // Landing payloads (Overview): null until loaded, like in app.js.
    landing: { micro: null, runs: null, notes: null, ledger: null, herkunft: { micro: null, runs: null, notes: null, ledger: null } },
    liveData: { leaderboard: null, cross: null, arbScan: null, arbResolutions: null, risk: null, riskLog: null, alerts: null, copy: null, portfolio: null, research: {}, backtest: null, walletDetail: {}, wallet: {}, riskBook: {}, walletSimilar: {}, walletEntity: {}, graph: null },
    num, money, esc,
    seriesPoints: (v, w, h) => seriesPoints(v, w, h),
    act: () => 'data-act="0"',
    inp: () => 'data-inp="0" data-key="k"',
    inpEntprellt: (key) => 'data-inp="0" data-key="' + key + '"',
    setState: () => {},
    opt: (l) => '<div>' + esc(l) + '</div>',
    chip: (l) => '<div>' + esc(l) + '</div>',
    tab: (l) => '<div>' + esc(l) + '</div>',
    toggle: () => '<div></div>',
    changeStyle: () => M,
    marketView: (m) => ({
      // Leer wie in app.js::marketView: die API liefert eine Tagesaenderung,
      // keinen Intraday-Pfad. Der Harness bildet das Original ab, sonst
      // prueft er einen Zustand, den die Anwendung nie erzeugt.
      title: m.title, meta: m.venue + ' · ' + m.cat, sparkPoints: '',
      color: 'var(--pos)', priceLabel: m.yes + '¢', changeLabel: '+' + m.chg + '¢',
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
    openMarket: () => {},
    fetchRiskBook: () => {},
    fetchWalletSimilar: () => {},
    fetchWalletEntity: () => {},
    fetchGraph: () => {},
    openWalletTab: () => {}
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
      // Echte ID: die Cross-Venue-Seite liest genau sie aus der
      // Landungs-Nutzlast, um ihren eigenen Befund danebenzustellen.
      studie('cross-venue', 'Are price gaps between the two venues arbitrage?', 'nein', 'No, carry. Gaps settle in 2027.', 8, '', 'Pairs matched', { paare: 8, maerkte: 900, fenster: '2026-07-30' }),
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
  // Wallet-Ledger, 10 Tage frischer als der Abgleich in runs.json: die
  // Landung muss die Bot-Scheibe UND den Cashflow des ganzen Wallets von
  // hier nehmen, nicht die eingefrorene Zahl aus runs.json.
  const ledger = {
    _quelle: 'statisch', stand_utc: '2026-08-17T11:42:04+00:00', kennzeichnung: 'live/descriptive',
    aggregat: {
      netto_cashflow_usd: 469.25, kaeufe_usd: 1474.53, rueckfluss_usd: 1943.78,
      einzahlungen_usd: 300,
      positionen_gewonnen: 36, positionen_verloren: 18,
      positionen: { won: 36, lost: 8, flat: 1, worthless: 10, open: 0 },
      nach_typ: { bot: { events: 8, maerkte: 24, einsatz_usd: 1039.01, netto_cash_usd: 417.77 } }
    }
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
    micro, runs, notes, ledger,
    herkunft: { micro: { quelle: 'statisch' }, runs: { quelle: 'statisch' }, notes: { quelle: 'statisch' }, ledger: { quelle: 'statisch' } }
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
    dir: 'BUY', outcome: 'Yes', side: 'BUY Yes', price: '62.0¢', size: 9000,
    venue: 'Polymarket', tracked: false
  }, {
    ago: '1 min ago', mins: 1, wallet: '—', walletAddress: '',
    market: 'KXBTC15M-26AUG17-1030-T115', marketKey: 'KXBTC15M-26AUG17-1030-T115', category: 'Crypto',
    dir: 'BUY', outcome: 'Yes', side: 'BUY Yes', price: '55.0¢', size: 3000,
    venue: 'Kalshi', tracked: false
  }];
  T.herkunft.tape = { quelle: 'live' };
  // Leaderboard row as /api/leaderboard delivers it: no win rate, no resolved
  // count (those come per wallet), a smart score with its components, and
  // the raw reason string that must NOT reach the page.
  // Die Punktwolke braucht mehr als einen bewerteten Punkt und die Kohorten-
  // Skala aus der Antwort; beides steht hier, damit der Leerdurchgang zeigen
  // kann, dass ohne Nutzlast kein Diagramm entsteht.
  T.liveData.leaderboard = {
    _quelle: 'live', as_of: '2026-08-07',
    score_scale: { gate_volume: 1000, saturates_at: 5000000 }
  };
  T.traders = [{
    name: 'w2', wallet: '0xde…f', walletFull: '0xdef', pnl: 40000, win: null,
    resolved: null, vol: 2400000, score: 58, grade: 'C',
    scoreN: 250, scoreCi: [41.5, 76.5], sampleBadge: { quality: 'part measured', measured_weight: 0.65 },
    scoreParts: [{ label: 'return', value: 70, weight: 0.35, imputed: false },
      { label: 'win', value: 50, weight: 0.1, imputed: true }],
    scoreBasis: { measured_weight: 0.65, imputed_weight: 0.35, imputed: ['win'], cohort_n: 250 },
    tags: ''
  }, {
    name: 'w1', wallet: '0xab…c', walletFull: '0xabc', pnl: 12000, win: null,
    resolved: null, vol: 90000, score: 71, grade: 'B',
    scoreN: 250, scoreCi: [52.5, 87.5], sampleBadge: { quality: 'part measured', measured_weight: 0.65 },
    // "win" traegt den Ersatzwert 50, den rank_traders_by_smart_score setzt,
    // wenn der Feed keine Trefferquote hat (imputed: true). Er darf nicht als
    // gemessene Zahl erscheinen.
    scoreParts: [{ label: 'return', value: 90, weight: 0.35, imputed: false },
      { label: 'sharpe proxy', value: 60, weight: 0.2, imputed: false },
      { label: 'win', value: 50, weight: 0.1, imputed: true },
      { label: 'volume', value: 80, weight: 0.1, imputed: false }],
    scoreBasis: { measured_weight: 0.65, imputed_weight: 0.35, imputed: ['win'], cohort_n: 250 },
    tags: 'return 90, sharpe-proxy 60, drawdown-proxy 100, win 55, recency 50, volume 80'
  }];
  T.herkunft.traders = { quelle: 'live' };
  // Two event rows: one in the richer shape of api_views.risk_event_row
  // (side, prices, window, top wallets, components, link) and one older row
  // without those fields, which must still render without invented values.
  T.risks = [{
    kind: 'TIMING', score: 61, market: 'Example question', detail: 'three wallets, one side',
    wallets: 3, notional: '$40k', window: '2 h', venue: 'Polymarket', sev: 'medium',
    // A conditionId-shaped key: the wallet-book line asks /api/risk/book only
    // for those (0x + 64 hex), never for a Kalshi ticker.
    market_key: HARNESS_CONDITION, url: 'https://polymarket.com/event/example-question', flags: ['three wallets, one side'],
    notional_usd: 40000, category: 'Politics & geopolitics', context_note: 'decisions are known to officials before the public',
    side: 'NO buys', side_notional: 34000, side_share: 0.85,
    side_split: { buy_yes: 6000, buy_no: 34000, sell_yes: 0, sell_no: 0 },
    price_outcome: 'NO', price_first: 0.30, price_last: 0.34, price_min: 0.30, price_max: 0.34,
    first_print: '2026-08-17T09:40:00Z', last_print: '2026-08-17T10:00:00Z', window_minutes: 20, prints: 4,
    // Measured print positions in the window (suspicion.event_flow_details):
    // three prints in the first quarter, one at the end — a visible clump.
    print_offsets: [0, 0.11, 0.45, 1],
    top_wallets: [
      { wallet: '0xbbb2000000000000000000000000000000000002', short: '0xbbb2…0002', notional: 26000, share: 0.65, side: 'NO buys', fresh: true, url: 'https://polymarket.com/profile/0xbbb2000000000000000000000000000000000002' },
      { wallet: '0xaaa1000000000000000000000000000000000001', short: '0xaaa1…0001', notional: 8000, share: 0.2, side: 'NO buys', fresh: false, url: 'https://polymarket.com/profile/0xaaa1000000000000000000000000000000000001' }
    ],
    // Components as app.suspicion.event_components ships them: plain label,
    // points, cap, what it measures, what the tape showed, what full marks take.
    components: [
      { key: 'component_notional', label: 'Size of the flow', value: 6.0, max: 15, measures: 'dollars traded in this market in the window', fact: '$40k traded in the window', rule: 'full marks at $100k' },
      { key: 'component_concentration', label: 'One wallet dominates', value: 9.8, max: 15, measures: 'share of the flow done by the top wallet', fact: '0xbbb2…0002 did 65% of the flow', rule: 'full marks when one wallet did all of it' },
      { key: 'component_late', label: 'Late in the market', value: 0, max: 15, measures: "share of the flow inside the market's last 48 h", fact: "nothing inside the market's last 48 h", rule: '' },
      { key: 'price_move_score', label: 'Price moved their way', value: 2.7, max: 10, measures: "price change in the flow's direction within the window", fact: 'price moved +4¢ behind the buys', rule: 'full marks at +10¢' },
      { key: 'component_fresh_wallets', label: 'Fresh wallets', value: 5.0, max: 10, measures: 'wallets barely seen on the tape, same side', fact: '2 wallets barely seen on the tape, same side', rule: 'full marks at 4' },
      { key: 'context_multiplier', label: 'Context', value: 1.1, max: null, measures: "insider plausibility of the market's subject", fact: 'Politics & geopolitics — decisions are known to officials before the public', rule: 'points × the multiplier; politics, awards and corporate decisions count more, general topics ×1' }
    ],
    token_id: 'tokNO'
  }, {
    kind: 'EVENT SCREEN', score: 44, market: 'KXFED-26SEP', detail: 'No individual flags — score from combined components.',
    wallets: 0, notional: '$12k', window: '3.0/h', venue: 'Kalshi', sev: 'low'
  }];
  T.herkunft.risks = { quelle: 'live' };
  // The four sub-tabs carry one row each in the enriched shape the API now
  // sends (flags on wallets, count/side on fresh, span on timing, members +
  // markets on network) plus a two-node graph, so the tests can pin the
  // redesigned views. The "..._empty"-suffixed variants below cover the
  // honest empty states.
  T.liveData.risk = {
    _quelle: 'live',
    // The display floor of the payload travels along: cards start at 40,
    // everything screened below it is a count ("7 more markets…"), not a card.
    event_min_score: 40,
    events_below_min: 7,
    kpis: { events_screened: 9, events_flagged: 2, high_risk_events: 1, high_risk_wallets: 2, fresh_clusters: 1, coordinated_clusters: 1 },
    // Die Verteilung aller gescorten Maerkte (api_views.risk_score_bins):
    // neun Maerkte, zwei davon ueber der Flag-Schwelle 40.
    score_bins: [
      { von: 0, bis: 10, anzahl: 2, geflaggt: 0 }, { von: 10, bis: 20, anzahl: 3, geflaggt: 0 },
      { von: 20, bis: 30, anzahl: 1, geflaggt: 0 }, { von: 30, bis: 40, anzahl: 1, geflaggt: 0 },
      { von: 40, bis: 50, anzahl: 1, geflaggt: 1 }, { von: 50, bis: 60, anzahl: 0, geflaggt: 0 },
      { von: 60, bis: 70, anzahl: 0, geflaggt: 0 }, { von: 70, bis: 80, anzahl: 1, geflaggt: 1 },
      { von: 80, bis: 90, anzahl: 0, geflaggt: 0 }, { von: 90, bis: 100, anzahl: 0, geflaggt: 0 }
    ],
    wallets: [{
      wallet: 'quietwhale', address: '0xdd10000000000000000000000000000000000001',
      context: 'Xi Jinping out before 2027?', score: 71,
      flags: ['long-odds big bet', 'late-market flow'],
      prints: 4, notional: '$52.0k', largest: '$26.0k', firstSeen: '2026-08-16'
    }, {
      wallet: '0xdd20…0002', address: '0xdd20000000000000000000000000000000000002',
      context: 'Fed cuts in September?', score: 37,
      flags: ['watch only'],
      prints: 1, notional: '$450', largest: '$450', firstSeen: '2026-08-17'
    }],
    fresh: [{
      count: 4, side: 'YES', market: 'Iraq win', venue: 'Polymarket',
      notional: '$88.0k',
      detail: '4 wallets with at most two prior trades in this tape took YES for $88.0k combined.'
    }],
    timing: [{
      market: 'Iraq win', venue: 'Polymarket', wallets: 6, window: '40 s',
      span_minutes: 0.7, side: 'YES', notional: '$214.0k', same: true
    }],
    network: [{
      id: 1, name: 'Cluster C-2', size: 2, shared: '3', notional: '$63.8k',
      story: '2 wallets · $63.8k combined whale volume · tight clique',
      pattern: 'Tight clique',
      members: [
        { kurz: '0x5111…cbe1', wallet: '0x5111000000000000000000000000000000000cbe1' },
        { kurz: '0x0380…073d', wallet: '0x0380000000000000000000000000000000000073d' }
      ],
      members_total: 2,
      markets: [
        { title: 'Xi Jinping out before 2027?', label: '$41.2k' },
        { title: 'Iran leadership change?', label: '$22.6k' }
      ]
    }],
    graph: {
      knoten: [
        { wallet: '0x5111000000000000000000000000000000000cbe1', kurz: '0x5111…cbe1', x: 0.2, y: 0.4, cluster: 1, volumen: 41000, maerkte: 3, trades: 5, geteilt: 3 },
        { wallet: '0x0380000000000000000000000000000000000073d', kurz: '0x0380…073d', x: 0.8, y: 0.6, cluster: 1, volumen: 22000, maerkte: 3, trades: 4, geteilt: 3 }
      ],
      kanten: [{ a: 0, b: 1, geteilt: 3, notional: 63800, erwartet: 0.6, lift: 5.0 }],
      cluster: [{ id: 1, name: 'C-1', groesse: 2, volumen: 63800, volumen_label: '$63.8k' }],
      spanne: { x: [0, 1], y: [0, 1] },
      kennzahl: { wallets: 2, wallets_im_tape: 300, kanten: 1, cluster: 1, modularitaet: 0.4, lift_median: 5.0 },
      regel: 'same side of at least 3 markets within 5 minutes, $10k paired notional',
      // Die ganze Leiter, nicht nur die Sprosse, die getragen hat: hier
      // greift die strengste, die beiden lockereren wurden gar nicht
      // versucht (und stehen deshalb auf null, nicht auf 0).
      regel_leiter: [
        { regel: 'same side of at least 3 markets within 5 minutes, $10k paired notional', parameter: { window_minutes: 5, min_shared: 3, min_pair_notional: 10000 }, versucht: true, wallets: 2, kanten: 1, gewaehlt: true },
        { regel: 'same side of at least 2 markets within 5 minutes', parameter: { window_minutes: 5, min_shared: 2 }, versucht: false, wallets: null, kanten: null, gewaehlt: false },
        { regel: 'same side of at least 2 markets anywhere in the window, no simultaneity required', parameter: { window_minutes: null, min_shared: 2 }, versucht: false, wallets: null, kanten: null, gewaehlt: false }
      ],
      fenster: '2026-08-21 12:00 to 01:42 UTC · 13.7 h · 563 prints',
      // Die Kontrolle: dieselbe Regel auf gemischten Wallet-Namen.
      nullmodell: { runs: 2, wallets: 63, kanten: 846, cluster: 4, lift_median: 1.4 },
      stand_utc: '2026-08-28T09:00:00+00:00'
    },
    matrix: {}
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
    }],
    // Die Quote ueber die gemessenen Flags, wie risk_log.flag_scoreboard sie
    // fuer genau diese zwei Zeilen liefert.
    scoreboard: {
      as_of: '2026-08-17T10:30:00Z', flags_total: 2, flags_measured: 1,
      flags_by_venue: { Polymarket: 1, Kalshi: 1 },
      horizons: {
        '30m': { n: 1, n_decisive: 1, hits: 1, ties: 0, hit_rate: 1.0, ci95: [0.2065, 1.0], avg_move_c: 3.0, already_past: 0, sample: { n: 1, quality: 'insufficient', verdict_allowed: false } },
        '2h': { n: 1, n_decisive: 1, hits: 0, ties: 0, hit_rate: 0.0, ci95: [0.0, 0.7935], avg_move_c: -3.0, already_past: 1, sample: { n: 1, quality: 'insufficient', verdict_allowed: false } },
        '24h': { n: 0, n_decisive: 0, hits: 0, ties: 0, hit_rate: null, ci95: null, avg_move_c: null, already_past: 0, sample: { n: 0, quality: 'insufficient', verdict_allowed: false } }
      },
      basis: 'Hit = the price of the flagged side was higher at the horizon than at the flag; a flat price is a tie and leaves the ratio, both counted. Measured flags are a selected subset, not a sample: only Polymarket carries a readable price history, and only the newest 30 flags are looked up. Rows whose horizon has not passed yet are not counted anywhere.',
      multiplicity: 'Every market with a print in the tape is scored on every rule, and the screen re-runs every few minutes, so the flags are the extreme tail of many comparisons. Read one hit rate as the tail\'s behaviour, not as the accuracy of a single test.'
    }
  };
  // One pair that clears the server gate (sim >= 0.5, volume on both venues).
  // Mittelkurse 62/58, ausfuehrbar aber nur 2 Cent, und davon frisst die
  // Gebuehrenschwelle 2.7: die Zeile steht mit einer Luecke von 4 Cent und
  // einem negativen Netto da.
  // ``size``/``depthChecked``: die Spanne gilt fuer drei Stueck an der
  // Spitze, nicht fuer die hundert des Gebuehren-Clips.
  T.crossPairs = [{ event: 'Example question', cat: 'Macro', pm: 62, ks: 58, sim: 0.71, pmVolUsd: 1200000, ksVolContracts: 300000, gross: 2.0, band: 2.7, net: -0.7, dir: 'buy Kalshi, sell Polymarket', size: 3, depthChecked: true, feeDisputed: true }];
  T.herkunft.cross = { quelle: 'live' };
  T.liveData.cross = {
    _quelle: 'live', rows: T.crossPairs, candidates_before_gate: 9,
    gate: { min_similarity: 0.5, require_volume_both: true }, as_of: '2026-08-17 10:00 UTC',
    depth_rows: 12,
    // Der allgemeine Polymarket-Taker-Satz ist nicht eindeutig belegt; die
    // Netto-Spalte ruht auf ihm. Der Satz kommt aus app/venue_fees.py.
    fee_note: 'The general Polymarket taker rate is not settled: the venue documentation says 5 percent, secondary sources from the same period say 3 percent. Both ends are carried on every cost figure that rests on it.',
    fee_rate_documented: 0.05,
    fee_rate_low: 0.03,
    // Ein Paar, das der Paar-Check aussortiert hat: gezaehlt, benannt und
    // gelistet — jede Seite mit ihrem eigenen Kurs, aber ohne Luecke,
    // Spanne oder Netto.
    suppressed: {
      total: 1, by_verdict: { opposed: 1 },
      examples: [{ event: 'Bitcoin above $120,000', other: 'Bitcoin below $120,000', verdict: 'opposed', why: 'opposite direction (threshold): above against below', pm: 62, ks: 37, sim: 0.78 }]
    }
  };
  T.liveData.resolved = {
    _quelle: 'live', as_of: '2026-08-17 09:30 UTC',
    price_note: 'PRICE is the settlement price from the public closed-markets feed, not the last price before settlement. That earlier price is not in this feed; reading it would mean fetching the CLOB price history of each market at a fixed interval before close. Until that is done, no deviation between crowd and outcome is computed here.',
    rows: [
      { title: 'Settled question', meta: 'POLYMARKET · MACRO', yes: true, settled_price: 100, decisive: true, vol: '$1.2m', when: '2 d ago', hours: 6 },
      // Eine Zeile, die nicht bei 0 oder 100 abgerechnet hat: die Kachel
      // muss sie zaehlen und darf dann nicht mehr warnen.
      { title: 'Settled between the poles', meta: 'POLYMARKET · MACRO', yes: false, settled_price: 43, decisive: false, vol: '$300k', when: '30 h ago', hours: 30 }
    ]
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
    // Die Halter-Pruefung ist abgeschaltet, und der Schalter hat einen Namen.
    holder_check: {
      enabled: false, checks: 0, setting: 'alert_holder_checks',
      rules_not_evaluated: ['HOLDER CONCENTRATION'],
      note: 'Holder concentration is switched off in this deployment (alert_holder_checks = 0), so the rule is not evaluated and the threshold beside it changes nothing. Each check costs one extra holder call per market, which is why it is off by default.'
    },
    // Das Zustellprotokoll: was tatsaechlich rausging, mit n und Intervall.
    deliveries: {
      available: true, attempts: 40, sent: 36, failed: 4, distinct_signals: 31,
      rate: 0.9, ci95: [0.7694792561952611, 0.9604211124044252],
      sample: { n: 40, quality: 'adequate', verdict_allowed: true },
      channels: { telegram: { attempts: 40, sent: 36 } },
      first_delivery: '2026-08-21T09:00:00+00:00',
      last_delivery: '2026-08-28T14:25:00+00:00',
      last_failure: { at: '2026-08-28T14:20:00+00:00', channel: 'telegram', detail: 'HTTP 429: Too Many Requests' },
      chain_ok: true, chain_checked: 40, as_of: '2026-08-28T15:00:00+00:00',
      last_scan_at: '2026-08-28T14:25:00+00:00', last_hits: 47, last_sent: 10, last_deferred: 37,
      note: '36 of 40 delivery attempts succeeded, over 31 distinct signals. Attempts only: a hit above the per-scan message cap was never tried and is not in the denominator.'
    },
    shown_limit: 60
  };
  // Die Form von app/api_views.py copy_payload: Status und Kennzahlen da,
  // eine Order, aber kein Buch — genau der Fall, in dem frueher die
  // Rueckfallwerte der Portfolio- und Fidelity-Reiter erschienen.
  // Two followed traders (one paused), the settings, a fresh daemon heartbeat
  // and write access granted — the shape /api/copy answers with on the local
  // desk. Trader B has no orders and no curve: those cells must say so.
  T.liveData.copy = {
    _quelle: 'live', as_of: '2026-08-07',
    status: { running: true, source: 'w1', scale: 1, cash: 990, auto_topup: false },
    // Das Zahlenbeispiel des Copy-Desks: 1.000 eingezahlt, eine aufgeloeste
    // Kopie hat 120 gekostet, eine offene steht 300 ueber Einstand. Die
    // Schlagzeile las daraus "+180, +18,00 %" und verschwieg beides.
    // Dazu die Orderzahlen: 100 Zeilen, 40 davon nur beobachtete Baseline,
    // also 60, ueber die zu entscheiden war, und 50 gespiegelte.
    kpis: {
      equity: 1180, contributions: 1000, pnl: 180, pnl_pct: 18, source_return_pct: 0,
      settled_pnl: -120, open_pnl: 300, settled_pct: -12, open_pct: 30,
      pnl_reconciles: true, pnl_residual: 0,
      mirrored: 50, actionable: 60, observed: 40, coverage_pct: 50 / 60 * 100,
      total: 100, skipped: 10, fidelity: 83, config_fidelity: 100, exec_fidelity: 83,
      cash: 990, unrealized: 300, open_positions: 1
    },
    orders: [
      { time: '12:00', market: 'Example question', side: 'BUY Yes', kind: 'BUY', outcome: 'Yes', explain: 'the source bought Yes; the copy scaled it into the sub-account', book: 'source book now: 100 YES / 12.0k NO → net NO', theirs: '$100', yours: '$10', status: 'copied', reason: 'buy_scaled', wallet: HARNESS_TRADER_A, at: '2026-08-07T12:00:00+00:00' },
      // The row that misled: source side MERGE with outcome "Yes" is not a
      // YES bet — the kind, the sentence and the book line say so.
      { time: '12:05', market: 'Example question', side: 'MERGE Yes', kind: 'MERGE', outcome: 'Yes', explain: 'the source handed equal YES + NO shares back to the venue for $1 each — that closes exposure on both sides (a hedge unwound or an exit), it is not a bet on Yes', book: 'source book now: 100 YES / 12.0k NO → net NO', theirs: '$3,000', yours: '$30', status: 'settled', reason: 'merge_complete_set', wallet: HARNESS_TRADER_A, at: '2026-08-07T12:05:00+00:00' }
    ],
    positions: [], cash_events: [], history: [], equity_curve: [],
    traders: [
      { wallet: HARNESS_TRADER_A, label: 'w1', note: 'harness desk, slow trader', active: true, start_cash: 500, cash: 490, position_value: 10, equity: 500,
        contributions: 500, pnl: 0, pnl_pct: 0, realized_pnl: 0, unrealized_pnl: 0,
        settled_pnl: 0, open_pnl: 0, settled_pct: 0, open_pct: 0, pnl_reconciles: true,
        orders: { copied: 1, skipped: 0, settled: 0, observed: 3, total: 4 }, open_positions: 1, last_copy_at: '2026-08-07T12:00:00+00:00',
        added_at: '2026-08-06T00:00:00+00:00', seeded_at: '2026-08-06T00:00:05+00:00', baseline_cutoff_ts: 1785000000,
        equity_curve: [500, 500, 500], profile_url: 'https://polymarket.com/profile/' + HARNESS_TRADER_A,
        source_equity: 52000, neutral_ratio: 500 / 52000 },
      // Kein eingezahltes Kapital erfasst: kein Prozentwert, ein Strich.
      { wallet: HARNESS_TRADER_B, label: 'w2', note: '', active: false, start_cash: 500, cash: 500, position_value: 0, equity: 500,
        contributions: 0, pnl: 0, pnl_pct: null, realized_pnl: 0, unrealized_pnl: 0,
        settled_pnl: 0, open_pnl: 0, settled_pct: null, open_pct: null, pnl_reconciles: true,
        orders: { copied: 0, skipped: 0, settled: 0, observed: 0, total: 0 }, open_positions: 0, last_copy_at: null,
        added_at: '2026-08-07T00:00:00+00:00', seeded_at: null, baseline_cutoff_ts: null,
        equity_curve: [], profile_url: 'https://polymarket.com/profile/' + HARNESS_TRADER_B, source_equity: null, neutral_ratio: null }
    ],
    active_count: 1,
    totals: { equity: 1000, contributions: 1000, cash: 990 },
    settings: {
      target_wallet: HARNESS_TRADER_A, paper_start_cash: 1000, copy_scale: 0.01, max_order_equity_pct: 0.05, live_trading_enabled: false,
      trade_limit: 250, dynamic_sizing_enabled: true, dynamic_sizing_multiplier: 1, dynamic_stats_refresh_seconds: 300,
      dynamic_scale_max: 0, dynamic_scale_min: 0, dynamic_order_cap_from_tony: true, cash_throttle_pct: 0.25,
      auto_top_up_enabled: false, auto_top_up_amount: 1000, auto_top_up_threshold: 1, min_copy_notional: 0.01,
      editable: ['copy_scale', 'dynamic_sizing_enabled', 'dynamic_sizing_multiplier', 'max_order_equity_pct', 'cash_throttle_pct', 'auto_top_up_enabled', 'auto_top_up_amount', 'auto_top_up_threshold', 'min_copy_notional', 'trade_limit', 'dynamic_order_cap_from_tony', 'dynamic_scale_max', 'dynamic_scale_min', 'paper_start_cash']
    },
    daemon: { running: true, claims_running: true, stale: false, age_seconds: 12, reason: 'heartbeat fresh', pid: 4242, mode: 'paper_ws_chain', ws_connected: true, last_sync_at: '2026-08-07T11:59:48+00:00', last_error: null },
    sync: { running: false, started_at: null, finished_at: null, result: null, error: null },
    write_access: { allowed: true, mode: 'loopback', reason: 'local request, no admin token configured' }
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
      messlogik: {
        Politics: { anker: 'Harness anchor text.', einpreisung: 'Harness repricing text.', nicht_gemessen: 'Harness blind spot.', latenz_t0: 'Harness t0 source.' },
        Weather: { anker: 'Harness weather gap.', einpreisung: 'w', nicht_gemessen: 'w', latenz_t0: 'w' }
      },
      einschraenkungen: ['Harness caveat.']
    },
    kategorien: [
      { kategorie: 'Politics', brier_t7: 0.1, trefferquote_t7: 0.9, brier_t1: 0.05, trefferquote_t1: 0.95, n_maerkte: 240, n_t7: 200, n_t1: 240,
        anteil_entschieden_t7: 0.4, median_volumen_usd: 12345,
        brier_t7_offen: 0.15, n_t7_offen: 90,
        typen: [
          { typ: 'nachrichten', n: 200, brier_t7: 0.11, n_t7: 170, brier_t1: 0.06, n_t1: 200 },
          { typ: 'stichtag', n: 40, brier_t7: 0.05, n_t7: 30, brier_t1: 0.02, n_t1: 40 }
        ],
        horizonte: [
          { horizont_tage: 30, brier: 0.2, trefferquote: 0.8, n: 150 },
          { horizont_tage: 7, brier: 0.1, trefferquote: 0.9, n: 200, brier_offen: 0.15, trefferquote_offen: 0.8, n_offen: 90 },
          { horizont_tage: 1, brier: 0.05, trefferquote: 0.95, n: 240 }
        ],
        kalibrierung: { horizont_tage: 7, bins: [
          { von: 0, bis: 0.1, vorhergesagt: 0.03, realisiert: 0.05, realisiert_ci95: [0.01, 0.12], n: 120 },
          { von: 0.9, bis: 1, vorhergesagt: 0.96, realisiert: 0.9, realisiert_ci95: [0.82, 0.95], n: 80 }
        ] } },
      { kategorie: 'Sports', brier_t7: 0.2, trefferquote_t7: 0.7, brier_t1: 0.15, trefferquote_t1: 0.8, n_maerkte: 300, n_t7: 210, n_t1: 300,
        anteil_entschieden_t7: 0.1, median_volumen_usd: 500000,
        brier_t7_offen: 0.22, n_t7_offen: 180,
        typen: [],
        horizonte: [
          { horizont_tage: 30, brier: null, trefferquote: null, n: 0 },
          { horizont_tage: 7, brier: 0.2, trefferquote: 0.7, n: 210, brier_offen: 0.22, trefferquote_offen: 0.68, n_offen: 180 },
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
    n_eintraege: 3, prompt_hashes: ['a'], output_hashes: ['b'], backend_zaehler: { mock: 3 },
    // Wie public/data/meta.json: die vier registrierten Grundsaetze und eine
    // fuenfte Zeile, die der Publisher spaeter dazu geschrieben hat.
    disclaimer: [
      'Descriptive research artifacts from a daily, deterministic review run over public market data.',
      'Recommendations are verification steps (watch, check the source, escalate to a human), not buy or sell signals.',
      'No financial or investment advice. No return claim. Pipeline entries are observing/paper.',
      'No wallet addresses, no keys, no prompts. Audit as hashes and counters only.',
      'Model outputs are cached for 24 hours before they enter a report.'
    ]
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
      report: 'docs/research/README.md', modul: 'src/orderflow_study.py',
      // daten kommt aus app/study_datasets.py und steht nur da, wo die Datei
      // wirklich im Repo liegt. Eine Studie ohne CSV traegt nur die JSON.
      daten: [{ format: 'CSV', path: 'docs/research/orderflow_rest-2026-07.csv' },
        { format: 'JSON', path: 'docs/research/orderflow_rest-2026-07.json' }]
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
      // Ein Monat mit $100 Einsatz, davon $40 in zwei noch offenen Wetten,
      // und +$18 aus den drei aufgeloesten: 30 Prozent auf den aufgeloesten
      // Einsatz, nicht 18 Prozent auf alles.
      monthly: [{ month: '2026-07', runs: 2, bets: 5, stake: 100, net: 18, settled_bets: 3, settled_stake: 60 }],
      // Trefferquote mit 95-Prozent-Wilson-Spanne, wie
      // api_views.live_runs_win_rate sie rechnet: 2 von 3 Bot-Maerkten des
      // Ledgers gewonnen (worthless zaehlt als verloren).
      win_rate: { source: 'wallet ledger', wins: 2, losses: 1, n: 3, p: 0.6667, ci95: [0.2077, 0.9385] },
      wallet_ledger: {
        hinweis: 'Harness ledger note.', stand_utc: '2026-08-17T01:02:03+00:00',
        wallet: '0x29afe1bf37700768a640a08f1b35dad5f202f88d', kennzeichnung: 'wallet/public-api',
        aggregat: {
          einzahlungen_usd: null, kaeufe_usd: 176.35, verkaeufe_usd: 20, einloesungen_usd: 215.01,
          netto_cashflow_usd: 58.66, n_events: 4, n_maerkte: 5, n_trades: 7, n_kaeufe: 6, n_verkaeufe: 1, n_einloesungen: 4,
          positionen: { won: 3, lost: 1, flat: 0, worthless: 1, open: 0, unknown: 0 },
          positionen_gewonnen: 3, positionen_verloren: 2, positionen_wertlos: 1, positionen_offen: 0, positionen_flat: 0,
          closed_positions_capped: false, erste_aktivitaet_utc: '2026-07-02T00:00:20Z', letzte_aktivitaet_utc: '2026-08-11T17:03:24Z',
          // bot traegt einsatz/netto_cash: der Ledger (2026-08-17) ist frischer
          // als der kuratierte Abgleich (2026-07-18), die Seite muss dann die
          // Ledger-Zahlen in Kachel, LOG-VS-WALLET-Spalten und Kurve zeigen.
          nach_typ: { bot: { events: 2, maerkte: 3, einsatz_usd: 61.34, netto_cash_usd: 66.0 }, discretionary: { events: 1, maerkte: 1 }, pilot: { events: 1, maerkte: 1 } }
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
          // Zweites Bot-Event (harness_b): damit die Wallet-Kurve zwei Punkte
          // hat und jeder Lauf mit Fill im Ledger steht.
          { event_slug: 'harness-event-b', titel: 'Harness bot event B', url: '',
            typ: 'bot', typ_mix: '', run_profil: 'harness_b', run_im_log: true,
            von_utc: '2026-07-02T00:00:20Z', bis_utc: '2026-07-02T12:00:00Z', n_maerkte: 1, n_trades: 1, n_einloesungen: 1,
            einsatz_usd: 20, verkaeufe_usd: 0, einloesungen_usd: 30.03, netto_cash_usd: 10.03, pnl_usd: 10.03,
            status: { won: 1, lost: 0, flat: 0, worthless: 0, open: 0, unknown: 0 }, status_text: '1 won',
            notes: [],
            maerkte: [{ titel: 'Will it say yes twice?', seite: 'Yes', zuordnung: 'bot', run_profil: 'harness_b', avg_preis: 0.6, shares: 33.38, einsatz_usd: 20, pnl_usd: 10.03, pnl_art: 'realised (API realizedPnl)', status: 'won' }] },
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
    aggregate: {
      gesamt: { n: 2, median_minuten_bis_erste_reaktion: 5.25, median_minuten_bis_konvergenz: 315, median_stunden_im_handelbaren_fenster: 5.15 },
      je_outcome: {
        YES: { n: 1, median_minuten_bis_erste_reaktion: 0.5, median_minuten_bis_konvergenz: 30, median_stunden_im_handelbaren_fenster: 0.5 },
        NO: { n: 1, median_minuten_bis_erste_reaktion: 10, median_minuten_bis_konvergenz: 600, median_stunden_im_handelbaren_fenster: 9.8 }
      }
    },
    quelle: {
      methode: 'Harness mentions method.',
      datengrundlage: 'Harness mentions data basis.',
      einschraenkungen: ['Harness mentions caveat.']
    },
    faelle: [
      { event: 'harness_fast', minuten_bis_erste_reaktion: 0.5, minuten_bis_konvergenz: 30, stunden_im_handelbaren_fenster: 0.5, korrekt_aufgeloestes_outcome: 'YES', status: 'ok' },
      { event: 'harness_slow', minuten_bis_erste_reaktion: 10, minuten_bis_konvergenz: 600, stunden_im_handelbaren_fenster: 9.8, korrekt_aufgeloestes_outcome: 'NO', status: 'ok', erste_reaktion_zum_outcome: false },
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
  // Wallet-Ledger-Scheibe des Piloten (wie die Produktionszahlen: 10 won,
  // 6 lost, 3 worthless, 1 flat): die Seite liest W/L und Netto-Cash daraus,
  // nicht mehr aus der Trade-Liste ohne Aufloesungen.
  const pilotLedgerMaerkte = [];
  for (let i = 0; i < 20; i += 1) {
    pilotLedgerMaerkte.push({
      titel: 'Harness pilot market ' + (i + 1) + '?', seite: 'No', zuordnung: 'pilot', run_profil: '',
      einsatz_usd: 5, pnl_usd: i < 10 ? 0.2 : -5,
      status: i < 10 ? 'won' : (i < 16 ? 'lost' : (i < 19 ? 'worthless' : 'flat'))
    });
  }
  T.liveData.research['Pilot'] = {
    _quelle: 'live', stand_utc: '2026-08-07T04:33:12+00:00', hinweis: 'Harness pilot note.', kennzeichnung: 'pilot/preregistered',
    protokoll: { budget_usdc: 100, einsatz_je_trade_usdc: 10, regel_freeze_datum: '2026-07-18', handelsfenster_bis: '2026-08-01' },
    watcher_lauf_ts_utc: '2026-08-01T04:33:19Z',
    watcher_statistik: { maerkte: 1992, arm2_bereits_abgelaufen: 1155, gekappt: 415 },
    signal_zaehler: { 'arm2:signal': 322, 'arm1:kandidat_referenz_pruefen': 1 },
    signale_neueste: [],
    trades: pilotTrades,
    extras: {
      wallet_ledger: {
        stand_utc: '2026-08-27T19:10:28+00:00',
        aggregat: { nach_typ: { pilot: { events: 18, maerkte: 20, einsatz_usd: 100.16, netto_cash_usd: -11.11 } } },
        events: [{ event_slug: 'harness-pilot-all', typ: 'pilot', maerkte: pilotLedgerMaerkte }]
      }
    }
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
  // The arbitrage scanner's section on Cross-venue carries the full fixture.
  T.liveData.arbScan = arbNutzlast();
  T.liveData.arbResolutions = aufNutzlast();
  T.liveData.research['Postmortems'] = {
    _quelle: 'live', stand_utc: '2026-08-07T04:33:12+00:00', hinweis: 'Harness postmortem note.', kennzeichnung: 'curated/postmortem',
    eintraege: [{ datum: '2026-07-18', profil: 'harness_a', achse: 'Evaluation', titel: 'Harness incident',
      was_passierte: 'x', auswirkung: 'y', fix: 'z',
      referenz: 'PR #12 (fill accounting); commit 8af07d6 (heartbeat); docs/research/ONE_PAGER.md; plain note' }]
  };
  // Wallet page: one analysed address with the full /api/wallet answer
  // (shape of app/api_views.wallet_detail). Small numbers, but every block
  // the page reads: identity, track record with CIs and components, PnL
  // curve with stats, edge with CI and categories, open/closed positions,
  // activity, categories, context, limits.
  T.state.walletAddr = WALLET_HARNESS_ADDR;
  T.state.walletInput = WALLET_HARNESS_ADDR;
  T.state.walletRecent = [WALLET_HARNESS_ADDR];
  T.liveData.wallet[WALLET_HARNESS_ADDR] = { herkunft: 'live', data: walletNutzlast() };
  return T;
}

const WALLET_HARNESS_ADDR = '0xabc0000000000000000000000000000000000abc';
const HARNESS_CONDITION = '0xc1' + '0'.repeat(62);
const HARNESS_TRADER_A = '0x' + 'a'.repeat(40);
const HARNESS_TRADER_B = '0x' + 'b'.repeat(40);

function walletNutzlast() {
  return {
    wallet: WALLET_HARNESS_ADDR, snapshot_at: '2026-08-17T19:00:00+00:00', as_of: '2026-08-17 19:00 UTC',
    track: { headline_win_rate: 0.75, resolved_markets: 12, resolved_capped: false },
    realized_edge: { n_positions: 12, n_events: 11, edge: 0.05, ci_low: -0.02, ci_high: 0.12, verdict: 'thin', headline: 'Too few resolved events (11 < 30) to tell edge from chance either way.', capped: false },
    sample: { n_resolved: 11, quality: 'insufficient', verdict_allowed: false },
    errors: {},
    pnl_curve: [0, 10, 5, 20, 15, 30],
    recent_trades: [{ market: 'Harness market 0?', side: 'BUY Yes', price: '50.0¢', ago: '2026-07-01 10:00', size: 50 }],
    identity: {
      address: WALLET_HARNESS_ADDR, short: '0xabc0…0abc', pseudonym: 'harness_wallet',
      profile_url: 'https://polymarket.com/profile/' + WALLET_HARNESS_ADDR, polygonscan_url: 'https://polygonscan.com/address/' + WALLET_HARNESS_ADDR,
      first_activity: '2026-07-01T10:00:00Z', last_activity: '2026-07-05T10:00:00Z', days_active: 4.0, n_activity_rows: 4, activity_truncated: false
    },
    track_record: {
      as_of: '2026-08-17 19:00 UTC', source: 'polymarket /closed-positions, winner and loser tails unioned', capped: false,
      naive: { label: 'per position leg', win_rate: 0.75, wins: 9, n: 12, ci95: [0.468, 0.911] },
      corrected: { label: 'per event, NegRisk legs netted', win_rate: 0.7273, wins: 8, n: 11, ci95: [0.4304, 0.9051] },
      // Die untere Schranke rechnet api_views.win_rate_with_unredeemed:
      // dieselben Treffer, der nicht eingeloeste Verlust im Nenner.
      corrected_bound: { label: 'per event, with the unredeemed losses counted', win_rate: 0.6667, wins: 8, n: 12, unredeemed: 1, ci95: [0.3906, 0.8619], is_lower_bound: true },
      per_market: { label: 'per market', win_rate: 0.75, wins: 9, n: 12, ci95: [0.468, 0.911] },
      legs_netted: 1, leg_inflation: 1.03, win_rate_reliable: true,
      settled_pnl: 210.0, volume: 600.0, pnl_per_volume: 0.35, exit_win_rate: 1.0,
      wash_flag: { flag: false, rule: 'volume >= $25,000 and |settled PnL| / volume < 0.5% over >= 5 resolved markets' },
      survivorship_gate: { ok: false, resolved_markets: 12, span_days: 11.0, min_markets: 10, min_span_days: 14.0 },
      concentration: { top_market_share: 0.2222, top3_share: 0.6667, top3: [{ title: 'Harness market 0?', pnl: 60.0, share: 0.2222 }, { title: 'Harness market 2?', pnl: 60.0, share: 0.2222 }, { title: 'Harness market 4?', pnl: 60.0, share: 0.2222 }], one_hit_flag: false },
      risk_adjusted: 0.42, score: 27.0, grade: 'F',
      score_components: [{ label: 'insufficient sample (15 + resolved markets, capped at 30)', value: 27.0, max: 30 }],
      flags: ['insufficient sample (12 markets / 11d)'],
      coverage_note: 'Complete resolved set: winners and losers unioned from the public closed-positions feed.'
    },
    pnl: {
      as_of: '2026-08-17 19:00 UTC', window: 'All', source: 'user-pnl-api.polymarket.com',
      points: [{ t: '2026-07-01T00:00:00Z', pnl: 0 }, { t: '2026-07-02T00:00:00Z', pnl: 10 }, { t: '2026-07-03T00:00:00Z', pnl: 5 }, { t: '2026-07-04T00:00:00Z', pnl: 20 }, { t: '2026-07-05T00:00:00Z', pnl: 15 }, { t: '2026-07-06T00:00:00Z', pnl: 30 }],
      n_points: 6,
      // Sortino null: two losing days are below the 3-day floor (perf_metrics.MIN_DOWNSIDE_DAYS).
      stats: { n_days: 5, total_pnl: 30.0, best_day: 15.0, worst_day: -5.0, mean_day: 6.0, daily_vol: 9.6177, winning_days: 3, losing_days: 2, win_day_rate: 0.6, max_drawdown: 5.0, max_drawdown_pct: 0.25, sharpe: 11.918, sortino: null, calmar: 438.0, capital: null, return_on_capital: null, annualised_return: null },
      note: 'Ratios in dollars per day, no capital base, annualised on 365 days; n_days is the sample.'
    },
    edge: {
      as_of: '2026-08-17 19:00 UTC', capped: false,
      per_dollar: { edge: 0.35, ci_low: 0.12, ci_high: 0.55, groups: 11, significant: true, method: 'payout / cost - 1 over resolved positions; 95% CI from a cluster bootstrap resampling whole events (4000 draws)', cost_usd: 600.0, payout_usd: 810.0 },
      // Die Schranke rechnet api_views.edge_with_unredeemed: der Einsatz der
      // wertlosen Position im Nenner, ihr Ruecklauf null.
      per_dollar_bound: { label: 'return per dollar, with the unredeemed losses counted', edge: 0.3278688524590164, cost_usd: 610.0, unredeemed: 1, unredeemed_cost_usd: 10.0, is_lower_bound: true, ci_note: 'No interval: the omitted rows are not in the bootstrap sample the interval above comes from.' },
      per_share: { n_positions: 12, n_events: 11, edge: 0.05, ci_low: -0.02, ci_high: 0.12, verdict: 'thin', headline: 'Too few resolved events (11 < 30) to tell edge from chance either way.', capped: false },
      by_category: [{ category: 'Politics', groups: 7, positions: 8, cost: 400.0, pnl: 160.0, edge: 0.4, ci_low: 0.1, ci_high: 0.6 }, { category: 'Sports', groups: 4, positions: 4, cost: 200.0, pnl: 50.0, edge: 0.25, ci_low: null, ci_high: null }]
    },
    // Kalibrierung und Gewinn-Herkunft: beide liefert /api/wallet, beide
    // zeigt die Record-Karte. Ein Bucket liegt bewusst neben der Diagonalen
    // (0.20 bezahlt, 0.67 eingetreten), damit die Seite ihn markieren muss.
    calibration: {
      n: 12, hit_rate: 0.75, hit_low: 0.4681, hit_high: 0.9112,
      avg_entry: 0.62, edge_per_share: 0.13, brier_entry: 0.18, brier_baseline: 0.1875,
      buckets: [
        { bucket: '0-20%', n: 3, avg_forecast: 0.2, hit_rate: 0.6667, edge: 0.4667, hit_low: 0.2077, hit_high: 0.9385, events: 3 },
        { bucket: '60-80%', n: 4, avg_forecast: 0.7, hit_rate: 0.75, edge: 0.05, hit_low: 0.3006, hit_high: 0.9544, events: 4 },
        { bucket: '80-100%', n: 5, avg_forecast: 0.9, hit_rate: 0.8, edge: -0.1, hit_low: 0.3757, hit_high: 0.9642, events: 4 }
      ]
    },
    attribution: {
      gross_profit: 210.0, structural_share: 0.1, top_event_share: 0.45,
      remaining_share: 0.45, top_event_title: 'Harness event that carried the record',
      structural_markets: 1, positive_events: 6
    },
    open_positions: {
      // Eine offene Position (+15 Buchgewinn, 40 Kostenbasis) und eine
      // wertlose (aufgeloester Verlust -10, 10 Kostenbasis). Der Verlust
      // gehoert nicht in unrealized_pnl (api_views._wallet_positions).
      as_of: '2026-08-17 19:00 UTC', n: 2, shown: 2, capped: false, total_exposure: 55.0, total_cost: 40.0, unrealized_pnl: 15.0, worthless_n: 1, worthless_pnl: -10.0, worthless_cost: 10.0,
      rows: [
        { title: 'Open harness market A?', outcome: 'Yes', size: 100.0, avg_price: 0.4, current_price: 0.55, value: 55.0, cost: 40.0, unrealized_pnl: 15.0, pnl_pct: 0.375, end_time: '2026-12-31T00:00:00Z', market_key: '0xopenA', url: 'https://polymarket.com/event/open-a', image: 'https://polymarket-upload.s3.us-east-2.amazonaws.com/harness-open-a.png', status: 'open' },
        { title: 'Resolved against, not redeemed?', outcome: 'No', size: 20.0, avg_price: 0.5, current_price: 0.0, value: 0.0, cost: 10.0, unrealized_pnl: -10.0, pnl_pct: -1.0, end_time: '2026-06-30T00:00:00Z', market_key: '0xworthless', url: '', status: 'worthless' }
      ],
      note: 'Value at the current price; positions at price 0 past their end date resolved against the wallet and were not redeemed (worthless).'
    },
    closed: {
      as_of: '2026-08-17 19:00 UTC', capped: false, n: 12, shown: 2, won: 9, lost: 3, flat: 0, worthless_not_redeemed: 1, realized_pnl: 210.0,
      rows: [
        // total_bought is the Data API's unit, SHARES: 100 shares at 0.50 are
        // $50 at risk, so a total loss is -$50 and a win at 1.00 is +$50.
        { title: 'Harness market 1?', outcome: 'Yes', avg_price: 0.5, current_price: 0.0, total_bought: 100.0, realized_pnl: -50.0, time: '2026-06-02T00:00:00Z', market_key: '0xc1', url: 'https://polymarket.com/event/event-1', result: 'lost' },
        { title: 'Harness market 0?', outcome: 'Yes', avg_price: 0.5, current_price: 1.0, total_bought: 100.0, realized_pnl: 40.0, time: '2026-06-01T00:00:00Z', market_key: '0xc0', url: 'https://polymarket.com/event/event-0', image: 'https://polymarket-upload.s3.us-east-2.amazonaws.com/harness-event-0.jpg', result: 'won' }
      ],
      note: 'Complete resolved set: winners and losers unioned from the public closed-positions feed.',
      source: 'polymarket /closed-positions, both sort directions, ~50 rows per tail'
    },
    activity: {
      as_of: '2026-08-17 19:00 UTC', n_rows: 4, n_trades: 3, n_redeems: 1, window_truncated: false, first: '2026-07-01T10:00:00Z', last: '2026-07-05T10:00:00Z', span_days: 4.0,
      trades: [
        { time: '2026-07-03T10:00:00Z', type: 'TRADE', side: 'SELL', outcome: 'Yes', price: 0.6, size: 50.0, notional: 30.0, title: 'Harness market 0?', market_key: '0xc0', url: 'https://polymarket.com/event/event-0' },
        { time: '2026-07-02T10:00:00Z', type: 'TRADE', side: 'BUY', outcome: 'No', price: 0.25, size: 100.0, notional: 25.0, title: 'LoL: Team A vs Team B market 1?', market_key: '0xc1', url: 'https://polymarket.com/event/event-1' },
        { time: '2026-07-01T10:00:00Z', type: 'TRADE', side: 'BUY', outcome: 'Yes', price: 0.5, size: 100.0, notional: 50.0, title: 'Harness market 0?', market_key: '0xc0', url: 'https://polymarket.com/event/event-0' }
      ],
      shown: 3, buy_n: 2, sell_n: 1, buy_notional: 75.0, sell_notional: 30.0, redeem_notional: 50.0, net_cash_flow: 5.0, volume_traded: 105.0, avg_trade_size: 35.0, trades_per_day: 0.75, source: 'polymarket /activity'
    },
    categories: {
      as_of: '2026-08-17 19:00 UTC', classifier: 'market_filter_category, then the insider-context title patterns (app.suspicion)',
      rows: [{ category: 'Politics', stake: 50.0, trades: 2, pnl: 160.0, resolved_markets: 8 }, { category: 'Sports', stake: 25.0, trades: 1, pnl: 50.0, resolved_markets: 4 }],
      note: 'Stake = BUY notional in the activity window; PnL = settled PnL of resolved markets, netted per market.'
    },
    context: {
      as_of: '2026-08-17 19:00 UTC', n_trades: 3, notional: 105.0,
      groups: [{ group: 'General', notional: 80.0, trades: 2, note: '', insider_prone: true, share: 0.7619 }, { group: 'Sports odds', notional: 25.0, trades: 1, note: 'public-odds arena', insider_prone: false, share: 0.2381 }],
      insider_prone_share: 0.7619, excluded_share: 0.2381,
      note: 'Share of traded notional by insider-plausibility group (app.suspicion.classify_insider_context).'
    },
    // Risk profile from the 12 resolved rows (alternating win/loss in the
    // fixture) and the three trades on the clock: Wed/Thu/Fri 10:00 UTC.
    // Der Kopf kommt aus api_views.wallet_headline. Die Harness-Wallet liegt
    // absichtlich unter der Urteilsschwelle: dann muss der Kopf das zuerst
    // sagen und darf nicht klingen wie bei einer grossen Stichprobe.
    headline: {
      allowed: false,
      lead: 'Sample: developing, 11 resolved events. That is below the threshold for a verdict, so read every figure below as a description of what happened, not as a finding.',
      clauses: [
        '12 resolved markets over 11 days does not clear the sample gate.',
        'Corrected win rate 73% on 11 events, netted per event, 95% CI 43% to 91%.',
        'Realised edge 35.0 cents per dollar staked, 95% CI 12.0 to 55.0, excluding zero.',
        'The largest single event is 45% of gross profit.'
      ]
    },
    risk_profile: {
      as_of: '2026-08-17 19:00 UTC', partial: false, n_rows: 12, n_win: 6, n_loss: 6,
      profit_factor: 0.8, risk_reward: 0.8, conviction: 1.0, win_streak: 1, loss_streak: 1, current_streak: 1, current_streak_kind: 'loss',
      avg_win: 40, avg_loss: 50, largest_win: 40, largest_loss: -50, avg_stake_win: 50, avg_stake_loss: 50,
      bands: { profit_factor: 'losing', risk_reward: 'about even', conviction: 'even sizing' },
      note: 'closed rows: both tails of the /closed-positions feed; n 12 rows, 6 won, 6 lost',
      rules: { profit_factor: "sum of winning rows' realised PnL / |sum of losing rows'|", risk_reward: 'average winning row / average losing row (absolute)', conviction: 'average $ bought on winning rows / average $ bought on losing rows', streaks: 'longest run of consecutive winning / losing resolved rows in time order' },
      heatmap: (() => { const c = [[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]]; const u = c.map((r) => r.slice()); c[2][10] = 1; c[3][10] = 1; c[4][10] = 1; u[2][10] = 50; u[3][10] = 25; u[4][10] = 30; return { counts: c, notional: u, n: 3, tz: 'UTC', busiest: { weekday: 2, hour: 10, trades: 1 }, note: 'trades in the activity window by weekday (Mon–Sun) and UTC hour' }; })()
    },
    limits: ['Resolved positions come from the public /closed-positions feed, read in both sort directions with ~50 rows per tail.', 'Trades come from the public /activity feed in pages of 500 up to 2,000 rows.']
  };
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
    // A wallet outside the leaderboard opened by address (whale flow / risk
    // screen row): the drawer must render from the address alone.
    T.state.detail = { kind: 'wallet', id: '0xbbb2…0002', addr: '0xbbb2000000000000000000000000000000000002' };
    raus['_detail_wallet_addr'] = String(renderDetail(T));
    T.state.detail = null;
    T.state.searchOpen = true;
    raus['_suche'] = String(renderSearch(T));
    // The palette with a pasted full address, and with a partial one.
    T.state.searchQuery = '0x29afe1bf37700768a640a08f1b35dad5f202f88d';
    raus['_suche_adresse'] = String(renderSearch(T));
    T.state.searchQuery = '0x29afe1';
    raus['_suche_adresse_teil'] = String(renderSearch(T));
    T.state.searchQuery = '';
    T.state.searchOpen = false;
  } catch (err) {
    raus['_overlays'] = 'RENDER-FEHLER: ' + (err && err.stack ? err.stack : err);
  }
  // Reiter innerhalb einer Seite sind eigene Ansichten mit eigenen
  // Rueckfaellen. Sie werden hier einzeln durchgerendert.
  const varianten = [
    // Ein groesserer Marktausschnitt, damit die Preisverteilung ueberhaupt
    // etwas zu verteilen hat. Die eine Beispielzeile der Grundnutzlast ist
    // absichtlich zu duenn dafuer: aus einem Punkt entsteht kein Histogramm,
    // und der Test darueber prueft genau das.
    ['markets_verteilung', 'markets', {}, null, (T) => {
      if (!(T.herkunft.markets && T.herkunft.markets.quelle === 'live')) return null;
      const alt = { markets: T.markets, extra: T.marketExtra };
      const preise = [2, 3, 8, 14, 22, 31, 44, 48, 51, 53, 57, 66, 74, 82, 91, 96, 97, 99];
      T.markets = preise.map((yes, i) => ({
        id: 'mv' + i, title: 'Sample market ' + i + '?', venue: i % 3 === 0 ? 'Kalshi' : 'Polymarket',
        cat: 'Macro', yes, chg: 0, vol: 1000 * (i + 1), liq: 500 * (i + 1), ends: 'Dec 2026', url: ''
      }));
      T.marketExtra = {};
      T.markets.forEach((m) => { T.marketExtra[m.id] = { spread: 2, age: 10, endsDays: 30 }; });
      return () => { T.markets = alt.markets; T.marketExtra = alt.extra; };
    }],
    // Ein Lauf mit offenen Kopien: 100 kopierte Zeilen, 60 davon geschlossen
    // (35 gewonnen, 25 verloren), 40 noch offen. Die Trefferquote ist
    // 35/60 = 58 Prozent, nicht 35/100.
    ['backtester_stats', 'backtester', {}, null, (T) => {
      // Nur im Live-Durchgang: im Leerzustand darf hier keine Kurve stehen.
      if (!(T.herkunft.tape && T.herkunft.tape.quelle === 'live')) return null;
      const alt = T.liveData.backtest;
      T.liveData.backtest = {
        stats: {
          final_equity: 1050, roi: 0.05, total_pnl: 50, win_rate: 35 / 60,
          wins: 35, losses: 25, closed_trades: 63, decided_trades: 60, flat_trades: 3,
          copied_trades: 100,
          skipped_trades: 4, filtered_trades: 0, fees_paid: 3.2, open_value: 420,
          max_drawdown: -0.08, window_truncated: false, effective_start: '',
          skip_reasons: { out_of_cash: 2, exposure_cap: 2, no_position: 0, bad_data: 0, other: 0 }
        },
        equity: [1000, 1050], benchmark: [1000, 1010], drawdown: [0, -0.08], log: [],
        // api_views.trade_pnl_distribution ueber 60 geschlossene Kopien:
        // die drei groessten Gewinner tragen 45 von 120 Dollar Bruttogewinn.
        trade_pnl: {
          unit: 'USD', n: 60, best: 18.5, worst: -12.25, gross_win: 120, top3: 45,
          top3_share: 0.375, winners: 35,
          bins: [
            { von: -12.25, bis: -8, anzahl: 4 }, { von: -8, bis: -4, anzahl: 9 },
            { von: -4, bis: 0, anzahl: 12 }, { von: 0, bis: 4, anzahl: 18 },
            { von: 4, bis: 8, anzahl: 10 }, { von: 8, bis: 12, anzahl: 4 },
            { von: 12, bis: 18.5, anzahl: 3 }
          ]
        }
      };
      return () => { T.liveData.backtest = alt; };
    }],
    ['backtester_advanced', 'backtester', { advancedOpen: true }],
    ['backtester_flat_fee', 'backtester', { advancedOpen: true, btFeeModel: 'flat' }],
    // Beide Studien der Cross-Venue-Frage in der Landungs-Nutzlast: der
    // Kasten auf der Seite muss beide Befunde mit ihrer Basis zeigen.
    ['cross_beide_studien', 'cross', {}, null, (T) => {
      const alt = T.landing;
      // Im Leerlauf gibt es keine Nutzlast; dann bleibt alles wie es ist und
      // die Seite zeigt ihren Leerzustand mit dem Dateinamen.
      if (!alt || !alt.micro || !Array.isArray(alt.micro.studien)) return () => {};
      const kopie = JSON.parse(JSON.stringify(alt.micro));
      kopie.studien.push({
        id: 'gap-lifetime', frage: 'How long does such a gap stay open?',
        verdikt: 'Most stayed open at every single moment observed.', verdikt_art: 'nein',
        zahlen: [{ label: 'Pairs watched', wert: 5, einheit: '' }],
        basis: { paare: 5, fenster: '2026-07-31' }
      });
      T.landing = Object.assign({}, alt, { micro: kopie });
      return () => { T.landing = alt; };
    }],
    ['alerts_rules', 'alerts', { alertTab: 'rules' }],
    ['alerts_deliveries', 'alerts', { alertTab: 'deliveries' }],
    // Eine Lieferung, die laenger ist als eine Seite: der Fuss muss sagen,
    // wie viel gerade zu sehen ist, und weiterblaettern koennen. Vorher
    // endete die Lieferung selbst auf der Seitengroesse.
    ['alerts_lang', 'alerts', {}, null, viele_signale(1)],
    ['alerts_lang_seite2', 'alerts', {}, null, viele_signale(2)],
    ['risk_wallets', 'risk', { riskView: 'wallets' }],
    ['risk_fresh', 'risk', { riskView: 'fresh' }],
    ['risk_timing', 'risk', { riskView: 'timing' }],
    ['risk_network', 'risk', { riskView: 'network' }],
    // The same tabs when the screen answered but found nothing: the empty
    // state must say what was looked for and not found, not "live · answered".
    ['risk_fresh_empty', 'risk', { riskView: 'fresh' }, null, (T) => {
      const alt = T.liveData.risk;
      T.liveData.risk = Object.assign({}, alt, { fresh: [], timing: [], wallets: [] });
      return () => { T.liveData.risk = alt; };
    }],
    ['risk_timing_empty', 'risk', { riskView: 'timing' }, null, (T) => {
      const alt = T.liveData.risk;
      T.liveData.risk = Object.assign({}, alt, { fresh: [], timing: [], wallets: [] });
      return () => { T.liveData.risk = alt; };
    }],
    ['risk_wallets_empty', 'risk', { riskView: 'wallets' }, null, (T) => {
      const alt = T.liveData.risk;
      T.liveData.risk = Object.assign({}, alt, { fresh: [], timing: [], wallets: [] });
      return () => { T.liveData.risk = alt; };
    }],
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
    // Derselbe Reiter mit fehlgeschlagenem Abruf: der Kopf steht, und die
    // Seite sagt, dass die Datei nicht geantwortet hat, statt auszusehen
    // wie eine leere Datei.
    ['research_postmortems_fehler', 'research', { researchTab: STUDIEN.findIndex((st) => st.tab === 'Postmortems') },
      ['Postmortems', { _quelle: 'fehler', _fehler: 'HTTP 503' }]],
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
    // The paper scanner's section on Cross-venue: request still running, the
    // loader's two markers (no file, failed fetch), a file whose lists are
    // all empty, a file that carries nothing but its schema, and one whose
    // last cycle is fresh so the health strip must not warn. The served
    // fixture itself renders in the plain 'cross' page of the live pass.
    ['cross_arb_laedt', 'cross', {}, null, arbMit(null)],
    ['cross_arb_ohne_datei', 'cross', {}, null, arbMit({ _quelle: 'leer' })],
    ['cross_arb_fehler', 'cross', {}, null, arbMit({ _quelle: 'fehler', _fehler: 'HTTP 503' })],
    ['cross_arb_leere_listen', 'cross', {}, null, arbMit({
      _quelle: 'live', schema: 'arb_scan/1', generated_at: '2026-09-04T06:00:00+00:00',
      generator: { repo: 'prediction-alpha-bot', git_sha: 'abcdef0123456789', mode: 'paper' },
      disclaimer: 'Harness: empty scan.',
      health: { last_cycle_at: '2026-09-04T05:00:00+00:00', cycles_24h: 0, errors_24h: 0, scan_interval_ms: 30000, alive: false },
      summary: { raw_candidates_24h: 0, validated_24h: 0, paper_fired_24h: 0, open_paper_positions: 0, resolved_paper_trades: 0, resolved_paper_pnl_usd: null, sample_note: 'No resolved paper trades yet.' },
      strategies: [], rejections_24h: [], opportunities: [], paper_positions: []
    })],
    ['cross_arb_nur_schema', 'cross', {}, null, arbMit({ _quelle: 'live', schema: 'arb_scan/1' })],
    ['cross_arb_frisch', 'cross', {}, null, arbMit((() => { const p = arbNutzlast(); p.health.last_cycle_at = new Date().toISOString(); return p; })())],
    // The resolution pass: absent while loading, failed fetch, and a file
    // without trades. The joined state is the live pass itself.
    ['cross_arb_aufloesung_laedt', 'cross', {}, null, aufMit(null)],
    ['cross_arb_aufloesung_fehler', 'cross', {}, null, aufMit({ _quelle: 'fehler', _fehler: 'HTTP 503' })],
    ['cross_arb_aufloesung_leer', 'cross', {}, null, aufMit({ _quelle: 'live', schema: 'arb_resolutions/1', trades: [], summary: {} })],
    // Die PnL-Kurve des gefolgten Wallets ist geladen: die Zeile darunter
    // muss sagen, wessen Zahl das ist und ueber welchen Zeitraum.
    ['copy_mit_quellkurve', 'copy', {}, null, (T) => {
      const alt = T.liveData.copy;
      if (!alt || !alt.kpis) return () => {};
      T.liveData.copy = Object.assign({}, alt, {
        kpis: Object.assign({}, alt.kpis, { source_pnl_delta: 648516.4 }),
        source_curve: [0, 120000, 400000, 648516.4]
      });
      return () => { T.liveData.copy = alt; };
    }],
    ['copy_fidelity', 'copy', { copyTab: 'fidelity' }],
    // The copy desk: every tab, the trader filter, the inline edit and
    // top-up rows, a read-only host (remote, no token) and one asking for a
    // token, an action in flight, an error line, and a desk with no traders.
    ['copy_orders', 'copy', { copyTab: 'orders' }],
    ['copy_positions', 'copy', { copyTab: 'positions' }],
    ['copy_perf', 'copy', { copyTab: 'perf' }],
    ['copy_cash', 'copy', { copyTab: 'cash' }],
    ['copy_settings', 'copy', { copyTab: 'settings' }],
    ['copy_settings_dirty', 'copy', { copyTab: 'settings', copySettings: { dynamic_sizing_enabled: false, copy_scale: '0.02' } }],
    ['copy_settings_one', 'copy', { copyTab: 'settings', copySettings: { dynamic_sizing_enabled: false, copy_scale: '1' } }],
    ['copy_orders_merges', 'copy', { copyTab: 'orders', copySide: 'MERGE' }],
    ['copy_filter_b', 'copy', { copyTab: 'orders', copyTrader: HARNESS_TRADER_B }],
    ['copy_perf_filter_a', 'copy', { copyTab: 'perf', copyTrader: HARNESS_TRADER_A }],
    ['copy_edit_row', 'copy', { copyEdit: { wallet: HARNESS_TRADER_A, label: 'w1', note: 'x' } }],
    ['copy_topup_row', 'copy', { copyTopup: { wallet: HARNESS_TRADER_A, amount: '500' } }],
    ['copy_busy', 'copy', { copyBusy: 'follow' }],
    ['copy_msg_err', 'copy', { copyMsg: { kind: 'err', text: 'harness error line' } }],
    ['copy_readonly', 'copy', {}, null, (T) => {
      const alt = T.liveData.copy;
      if (alt) T.liveData.copy = Object.assign({}, alt, { write_access: { allowed: false, mode: 'locked', reason: 'writes are accepted from this machine only unless COPY_ADMIN_TOKEN is set' } });
      return () => { T.liveData.copy = alt; };
    }],
    ['copy_token_needed', 'copy', {}, null, (T) => {
      const alt = T.liveData.copy;
      if (alt) T.liveData.copy = Object.assign({}, alt, { write_access: { allowed: false, mode: 'token', reason: 'admin token required (X-Admin-Token header)' } });
      return () => { T.liveData.copy = alt; };
    }],
    ['copy_no_traders', 'copy', {}, null, (T) => {
      const alt = T.liveData.copy;
      if (alt) T.liveData.copy = Object.assign({}, alt, { traders: [], active_count: 0, orders: [], status: Object.assign({}, alt.status, { running: null, source: 'no active trader' }), daemon: { running: null, reason: 'no status file at data/copy_trader_status.json — the daemon has not run here yet' } });
      return () => { T.liveData.copy = alt; };
    }],
    ['copy_error', 'copy', {}, null, (T) => {
      const alt = T.liveData.copy;
      T.liveData.copy = { _quelle: 'fehler', _fehler: 'HTTP 404' };
      return () => { T.liveData.copy = alt; };
    }],
    // Ein Lauf, in dem eine Aufloesung unentschieden blieb: der Ausgang des
    // Marktes war nicht zu lesen, also wurde weder Gewinn noch Verlust
    // gebucht. Ungenannt saehe der Lauf vollstaendig aus.
    ['copy_sync_undecided', 'copy', {}, null, (T) => {
      const alt = T.liveData.copy;
      if (alt) T.liveData.copy = Object.assign({}, alt, { sync: {
        running: false, started_at: '2026-08-28T05:00:00Z', finished_at: '2026-08-28T05:00:12Z', error: null,
        result: { api: { wallets: 2, copied: 3, skipped: 1, duplicates: 4, errors: [] },
          settlement: { wallets: 2, copied: 1, skipped: 0, duplicates: 0, undecided: 2, errors: [] } }
      } });
      return () => { T.liveData.copy = alt; };
    }],
    // Betraege ueber tausend: alle vier Kacheln der Kopfzeile muessen
    // dieselbe Schreibweise benutzen.
    ['portfolio_gross', 'portfolio', {}, null, (T) => {
      const alt = T.liveData.copy;
      if (!alt || !alt.kpis) return () => {};
      T.liveData.copy = Object.assign({}, alt, {
        kpis: Object.assign({}, alt.kpis, { equity: 12345.6, cash: 9876.5, unrealized: 2468.9 })
      });
      return () => { T.liveData.copy = alt; };
    }],
    // Und wenn die Felder fehlen, steht ueberall ein Strich statt NaN.
    ['portfolio_ohne_zahlen', 'portfolio', {}, null, (T) => {
      const alt = T.liveData.copy;
      if (!alt || !alt.kpis) return () => {};
      const knapp = Object.assign({}, alt.kpis);
      delete knapp.equity; delete knapp.cash; delete knapp.unrealized; delete knapp.open_positions;
      T.liveData.copy = Object.assign({}, alt, { kpis: knapp });
      return () => { T.liveData.copy = alt; };
    }],
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
      // Leeres Gate, aber nicht leere Antwort: die verworfenen Fast-Paare
      // stehen unter dem Gate-Block, jede Seite mit ihrem eigenen Kurs.
      T.liveData.cross = {
        _quelle: 'live', rows: [], candidates_before_gate: 7,
        gate: { min_similarity: 0.5, require_volume_both: true },
        suppressed: {
          total: 4, by_verdict: { different_question: 4 },
          examples: [{
            event: 'Will Gavin Newsom win the 2028 US Presidential Election?',
            other: 'Will Gavin Newsom be the Democratic Presidential nominee in 2028?',
            verdict: 'different_question',
            why: 'different scope (election vs nomination): election against nominee',
            pm: 8, ks: 14, sim: 0.59
          }]
        }
      };
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
    // The wallet-book line on the risk card: answered (net NO, the NO buys add
    // to the book), and failed (not read, no side invented).
    ['risk_book', 'risk', {}, null, (T) => {
      T.liveData.riskBook[HARNESS_CONDITION] = { herkunft: 'live', data: { market_key: HARNESS_CONDITION, flagged_side: 'NO buys', wallets: [
        { wallet: '0xbbb2000000000000000000000000000000000002', short: '0xbbb2…0002', read: true, positions: 1, yes_shares: 0, no_shares: 12000, yes_value: 0, no_value: 4080, net: 'NO', net_shares: 12000, relation: 'adds', text: 'holds 0 YES / 12.0k NO now — net NO; the flagged NO buys add to that side' },
        { wallet: '0xaaa1000000000000000000000000000000000001', short: '0xaaa1…0001', read: true, positions: 2, yes_shares: 9000, no_shares: 200, yes_value: 5940, no_value: 68, net: 'YES', net_shares: 8800, relation: 'reduces', text: 'holds 9.00k YES / 200 NO now — net YES; the flagged NO buys work against a YES book (hedge / closing / merging), not a new NO bet' }
      ], dropped: 0, note: 'read now' } };
    }],
    // The card opened ("Why this score"): flags, context, score components
    // and the per-wallet book lines appear; closed, the card carries the
    // one-line book summary only.
    ['risk_open', 'risk', { riskOpen: { [HARNESS_CONDITION]: true } }, null, (T) => {
      T.liveData.riskBook[HARNESS_CONDITION] = { herkunft: 'live', data: { market_key: HARNESS_CONDITION, flagged_side: 'NO buys', wallets: [
        { wallet: '0xbbb2000000000000000000000000000000000002', short: '0xbbb2…0002', read: true, positions: 1, yes_shares: 0, no_shares: 12000, yes_value: 0, no_value: 4080, net: 'NO', net_shares: 12000, relation: 'adds', text: 'holds 0 YES / 12.0k NO now — net NO; the flagged NO buys add to that side' },
        { wallet: '0xaaa1000000000000000000000000000000000001', short: '0xaaa1…0001', read: true, positions: 2, yes_shares: 9000, no_shares: 200, yes_value: 5940, no_value: 68, net: 'YES', net_shares: 8800, relation: 'reduces', text: 'holds 9.00k YES / 200 NO now — net YES; the flagged NO buys work against a YES book (hedge / closing / merging), not a new NO bet' }
      ], dropped: 0, note: 'read now' } };
    }],
    ['risk_book_err', 'risk', {}, null, (T) => {
      T.liveData.riskBook[HARNESS_CONDITION] = { herkunft: 'fehler', fehler: 'no answer within 45 s' };
    }],
    // A wallet whose rows the feed carried but did not price: neither a book
    // nor a settled loss. The card names the shares instead of reporting the
    // gap as an empty market.
    ['risk_book_unpriced', 'risk', { riskOpen: { [HARNESS_CONDITION]: true } }, null, (T) => {
      const alt = T.liveData.riskBook[HARNESS_CONDITION];
      T.liveData.riskBook[HARNESS_CONDITION] = { herkunft: 'live', data: { market_key: HARNESS_CONDITION, flagged_side: 'NO buys', wallets: [
        { wallet: '0xbbb2000000000000000000000000000000000002', short: '0xbbb2…0002', read: true, positions: 1, yes_shares: 0, no_shares: 0, yes_value: 0, no_value: 0, net: 'none', net_shares: 0, settled_shares: 0, settled_positions: 0, unpriced_shares: 12000, unpriced_positions: 1, relation: 'unpriced', text: 'no priced position left in this market (12.0k shares in rows the feed did not price) — the flagged NO buys cannot be related to a book the feed did not price' }
      ], dropped: 0, note: 'read now' } };
      return () => { T.liveData.riskBook[HARNESS_CONDITION] = alt; };
    }],
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
    }],
    // Wallet page states: no address chosen, request in flight, failed
    // (generic / 400 / 429), and the full answer sorted by unrealised PnL.
    // The empty run has no payload: 'wallet' there is the no-address page.
    // Eine Bestenlisten-Zeile ohne Gewinn- und Volumenzahl. ``+r.pnl || 0``
    // in app.js machte daraus einen echten, plausiblen Nullgewinn; die Zeile
    // muss stattdessen einen Strich zeigen und darf nicht vor Zeilen mit
    // gemessenem Gewinn stehen.
    ['traders_pnl_unknown', 'traders', {}, null, (T) => {
      const alt = T.traders;
      T.traders = alt.concat([{
        name: 'w3', wallet: '0x12…3', walletFull: '0x123', pnl: null, win: null,
        resolved: null, vol: null, score: null, grade: null, scoreParts: [], tags: ''
      }]);
      return () => { T.traders = alt; };
    }],
    ['wallet_none', 'wallet', { walletAddr: '', walletInput: '' }],
    ['wallet_partial_input', 'wallet', { walletAddr: '', walletInput: '0x29afe1' }],
    ['wallet_loading', 'wallet', { walletAddr: WALLET_HARNESS_ADDR, walletInput: WALLET_HARNESS_ADDR }, null, (T) => {
      const alt = T.liveData.wallet[WALLET_HARNESS_ADDR];
      T.liveData.wallet[WALLET_HARNESS_ADDR] = { herkunft: 'loading' };
      return () => { if (alt) T.liveData.wallet[WALLET_HARNESS_ADDR] = alt; else delete T.liveData.wallet[WALLET_HARNESS_ADDR]; };
    }],
    ['wallet_error', 'wallet', { walletAddr: WALLET_HARNESS_ADDR, walletInput: WALLET_HARNESS_ADDR }, null, (T) => {
      const alt = T.liveData.wallet[WALLET_HARNESS_ADDR];
      T.liveData.wallet[WALLET_HARNESS_ADDR] = { herkunft: 'fehler', fehler: 'Failed to fetch', status: null };
      return () => { if (alt) T.liveData.wallet[WALLET_HARNESS_ADDR] = alt; else delete T.liveData.wallet[WALLET_HARNESS_ADDR]; };
    }],
    ['wallet_error_400', 'wallet', { walletAddr: WALLET_HARNESS_ADDR, walletInput: WALLET_HARNESS_ADDR }, null, (T) => {
      const alt = T.liveData.wallet[WALLET_HARNESS_ADDR];
      T.liveData.wallet[WALLET_HARNESS_ADDR] = { herkunft: 'fehler', fehler: 'HTTP 400', status: 400 };
      return () => { if (alt) T.liveData.wallet[WALLET_HARNESS_ADDR] = alt; else delete T.liveData.wallet[WALLET_HARNESS_ADDR]; };
    }],
    ['wallet_error_429', 'wallet', { walletAddr: WALLET_HARNESS_ADDR, walletInput: WALLET_HARNESS_ADDR }, null, (T) => {
      const alt = T.liveData.wallet[WALLET_HARNESS_ADDR];
      T.liveData.wallet[WALLET_HARNESS_ADDR] = { herkunft: 'fehler', fehler: 'HTTP 429', status: 429, retryAfter: 7 };
      return () => { if (alt) T.liveData.wallet[WALLET_HARNESS_ADDR] = alt; else delete T.liveData.wallet[WALLET_HARNESS_ADDR]; };
    }],
    // Der Abruf der Aktivitaet ist gescheitert. Die Seite darf daraus keine
    // stille Wallet machen: null Trades sind hier keine Messung.
    ['wallet_activity_unreadable', 'wallet', { walletTab: 'trades' }, null, (T) => {
      const eintrag = T.liveData.wallet[WALLET_HARNESS_ADDR];
      const alt = eintrag && eintrag.data ? eintrag.data : null;
      if (alt) {
        eintrag.data = Object.assign({}, alt, {
          activity: Object.assign({}, alt.activity, {
            n_rows: 0, n_trades: 0, trades: [], shown: 0, window_truncated: false,
            window_state: 'unreadable', error: 'MarketDataError: connection reset by peer'
          }),
          identity: Object.assign({}, alt.identity, {
            n_activity_rows: 0, days_active: null, first_activity: '', last_activity: '',
            activity_truncated: false, activity_error: 'MarketDataError: connection reset by peer'
          })
        });
      }
      return () => { if (alt) T.liveData.wallet[WALLET_HARNESS_ADDR].data = alt; };
    }],
    ['wallet_sort_pnl', 'wallet', { walletTab: 'positions', walletPosSort: 'pnl' }],
    // The tabbed main column: each tab once, plus the treemap on closed only.
    ['wallet_tab_record', 'wallet', { walletTab: 'record' }],
    ['wallet_tab_positions', 'wallet', { walletTab: 'positions' }],
    ['wallet_tab_trades', 'wallet', { walletTab: 'trades' }],
    ['wallet_tab_categories', 'wallet', { walletTab: 'categories' }],
    ['wallet_treemap_closed', 'wallet', { walletPosView: 'treemap', walletTreemap: 'closed' }],
    ['wallet_treemap_alle', 'wallet', { walletPosView: 'treemap' }],
    ['wallet_treemap_open', 'wallet', { walletPosView: 'treemap', walletTreemap: 'open' }],
    ['wallet_tab_risk', 'wallet', { walletTab: 'risk' }],
    ['wallet_tab_similar', 'wallet', { walletTab: 'similar' }],
    ['wallet_tab_similar_data', 'wallet', { walletTab: 'similar' }, null, (T) => {
      T.liveData.walletSimilar[WALLET_HARNESS_ADDR] = { herkunft: 'live', data: {
        wallet: WALLET_HARNESS_ADDR, as_of: '2026-08-18 15:00 UTC', candidates: 7,
        rows: [
          { wallet: '0x' + 'b'.repeat(40), short: '0xbbbb…bbbb', name: 'bee', shared: 2, same_side: 2, opposite_side: 0, overlap: 1.0, markets: [],
            their_positions: 12, their_value: 4200.5, summary_read: true, lb_pnl: 1500.25, lb_volume: 90000, on_leaderboard: true, profile_url: 'https://polymarket.com/profile/0x' + 'b'.repeat(40) },
          { wallet: '0x' + 'c'.repeat(40), short: '0xcccc…cccc', name: '', shared: 1, same_side: 0, opposite_side: 1, overlap: 0.5, markets: [],
            their_positions: null, their_value: null, summary_read: false, lb_pnl: null, lb_volume: null, on_leaderboard: false, profile_url: 'https://polymarket.com/profile/0x' + 'c'.repeat(40) }
        ],
        // markets_read < markets_checked: ein Abruf ist gescheitert, und der
        // Nenner der Quote sind nur die gelesenen Maerkte.
        basis: { markets_checked: 3, markets_read: 2, markets_available: 3, holders_per_token: 20, top: 10, median_shared: 1, note: "overlap among the top 20 holders per outcome of this wallet's 3 largest open markets", errors: ['0x1111111…: holders down'] }
      } };
      return () => { delete T.liveData.walletSimilar[WALLET_HARNESS_ADDR]; };
    }],
    ['wallet_tab_similar_err', 'wallet', { walletTab: 'similar' }, null, (T) => {
      T.liveData.walletSimilar[WALLET_HARNESS_ADDR] = { herkunft: 'fehler', fehler: 'HTTP 429', status: 429 };
      return () => { delete T.liveData.walletSimilar[WALLET_HARNESS_ADDR]; };
    }],
    // A wallet whose trading ended before user-pnl-api's history begins
    // (Theo4-shaped): the profile curve is one level for 630 points, so the
    // block must swap to the settled curve summed from the closed rows and
    // say why, and the KPI strip must take Sharpe / drawdown from that.
    ['wallet_flat_profile', 'wallet', { walletAddr: WALLET_HARNESS_ADDR, walletInput: WALLET_HARNESS_ADDR }, null, (T) => {
      const alt = T.liveData.wallet[WALLET_HARNESS_ADDR];
      if (!alt) return null;                       // empty mode: the page stays in its waiting state
      const voll = walletNutzlast();
      const flach = [];
      for (let i = 0; i < 630; i += 1) {
        const tag = new Date(Date.UTC(2024, 10, 28) + i * 86400000).toISOString().slice(0, 10);
        flach.push({ t: tag + 'T00:00:00Z', pnl: 22053934 });
      }
      voll.pnl = {
        as_of: '2026-08-18 15:47 UTC', window: 'All', source: 'user-pnl-api.polymarket.com (the curve polymarket.com shows on the profile)',
        points: flach, n_points: 630, first: '2024-11-28T00:00:00Z', last: '2026-08-18T15:00:00Z', flat: true,
        stats: { n_days: 628, total_pnl: 0, best_day: 0, worst_day: 0, mean_day: 0, daily_vol: 0, winning_days: 0, losing_days: 0, win_day_rate: null, max_drawdown: 0, max_drawdown_pct: 0, sharpe: null, sortino: null, calmar: null, capital: null, return_on_capital: null, annualised_return: null },
        note: "The profile curve is a flat line at $22,053,934 over its 630 points (2024-11-28 to 2026-08-18): user-pnl-api's history for this wallet begins there and nothing has changed since — no daily change, so no Sharpe, drawdown or win-day share can come out of it.",
        settled: {
          points: [{ t: '2024-10-13T22:30:57Z', pnl: 0 }, { t: '2024-10-14T22:30:57Z', pnl: 0 }, { t: '2024-10-16T15:18:39Z', pnl: 685.65 }, { t: '2024-11-11T22:30:39Z', pnl: 8302699.25 }, { t: '2024-11-12T10:03:19Z', pnl: 14363839.43 }, { t: '2025-01-01T08:27:52Z', pnl: 22069554.81 }],
          n_points: 6, n_rows: 22, first: '2024-10-14T22:30:57Z', last: '2025-01-01T08:27:52Z', total: 22069554.81, capped: false,
          stats: { n_days: 80, total_pnl: 22069554.81, best_day: 8302013.6, worst_day: -21.35, mean_day: 275869.44, daily_vol: 1339066.95, winning_days: 7, losing_days: 1, win_day_rate: 0.875, max_drawdown: 39300, max_drawdown_pct: 0.0062, sharpe: 3.936, sortino: null, calmar: 2562.15, capital: null, return_on_capital: null, annualised_return: null },
          source: 'polymarket /closed-positions, both sort directions, summed by our code',
          note: "Realised PnL of the 22 closed-position rows summed in resolution order, starting at $0 the day before the first resolution. Open positions' unrealised PnL is not in it. Complete resolved set (both tails)."
        },
        shown: 'settled'
      };
      T.liveData.wallet[WALLET_HARNESS_ADDR] = { herkunft: 'live', data: voll };
      return () => { if (alt) T.liveData.wallet[WALLET_HARNESS_ADDR] = alt; else delete T.liveData.wallet[WALLET_HARNESS_ADDR]; };
    }],
    // The same address answered with an empty read: no resolved positions,
    // no curve, no trades. Every block must say so, none may print a figure.
    ['wallet_empty_answer', 'wallet', { walletAddr: WALLET_HARNESS_ADDR, walletInput: WALLET_HARNESS_ADDR }, null, (T) => {
      const alt = T.liveData.wallet[WALLET_HARNESS_ADDR];
      T.liveData.wallet[WALLET_HARNESS_ADDR] = { herkunft: 'live', data: {
        wallet: WALLET_HARNESS_ADDR, as_of: '2026-08-17 19:00 UTC', errors: { resolved: 'HTTP 502' },
        identity: { address: WALLET_HARNESS_ADDR, short: '0xabc0…0abc', pseudonym: '', profile_url: 'https://polymarket.com/profile/' + WALLET_HARNESS_ADDR, polygonscan_url: 'https://polygonscan.com/address/' + WALLET_HARNESS_ADDR, first_activity: '', last_activity: '', days_active: null, n_activity_rows: 0, activity_truncated: false },
        track_record: null,
        pnl: { as_of: '2026-08-17 19:00 UTC', window: 'All', points: [], n_points: 0, stats: null, source: 'user-pnl-api.polymarket.com', note: 'The profile PnL curve did not answer.' },
        edge: { as_of: '2026-08-17 19:00 UTC', capped: false, per_dollar: { edge: null, ci_low: null, ci_high: null, groups: 0, significant: false, method: '' }, per_share: null, by_category: [] },
        open_positions: { as_of: '2026-08-17 19:00 UTC', rows: [], n: 0, shown: 0, capped: false, total_exposure: 0, total_cost: 0, unrealized_pnl: 0, worthless_n: 0, note: 'No open positions in the public /positions feed.' },
        closed: { as_of: '2026-08-17 19:00 UTC', capped: false, n: 0, shown: 0, won: 0, lost: 0, flat: 0, worthless_not_redeemed: 0, rows: [], realized_pnl: 0, note: 'No resolved positions found in the public feed for this wallet.', source: 'polymarket /closed-positions' },
        activity: { as_of: '2026-08-17 19:00 UTC', n_rows: 0, n_trades: 0, n_redeems: 0, window_truncated: false, first: '', last: '', span_days: null, trades: [], shown: 0, buy_n: 0, sell_n: 0, buy_notional: 0, sell_notional: 0, redeem_notional: 0, net_cash_flow: 0, volume_traded: 0, avg_trade_size: null, trades_per_day: null, source: 'polymarket /activity' },
        categories: { as_of: '2026-08-17 19:00 UTC', rows: [], classifier: 'x', note: 'x' },
        context: { as_of: '2026-08-17 19:00 UTC', n_trades: 0, notional: 0, groups: [], insider_prone_share: null, excluded_share: null, note: 'No trades in the activity window to classify.' },
        limits: ['Harness limit line.']
      } };
      return () => { if (alt) T.liveData.wallet[WALLET_HARNESS_ADDR] = alt; else delete T.liveData.wallet[WALLET_HARNESS_ADDR]; };
    }],
    ['wallet_empty_record', 'wallet', { walletAddr: WALLET_HARNESS_ADDR, walletInput: WALLET_HARNESS_ADDR, walletTab: 'record' }, null, (T) => {
      const alt = T.liveData.wallet[WALLET_HARNESS_ADDR];
      T.liveData.wallet[WALLET_HARNESS_ADDR] = { herkunft: 'live', data: {
        wallet: WALLET_HARNESS_ADDR, as_of: '2026-08-17 19:00 UTC', errors: { resolved: 'HTTP 502' },
        identity: { address: WALLET_HARNESS_ADDR, short: '0xabc0…0abc', pseudonym: '', profile_url: 'https://polymarket.com/profile/' + WALLET_HARNESS_ADDR, polygonscan_url: 'https://polygonscan.com/address/' + WALLET_HARNESS_ADDR, first_activity: '', last_activity: '', days_active: null, n_activity_rows: 0, activity_truncated: false },
        track_record: null,
        pnl: { as_of: '2026-08-17 19:00 UTC', window: 'All', points: [], n_points: 0, stats: null, source: 'user-pnl-api.polymarket.com', note: 'The profile PnL curve did not answer.' },
        edge: { as_of: '2026-08-17 19:00 UTC', capped: false, per_dollar: { edge: null, ci_low: null, ci_high: null, groups: 0, significant: false, method: '' }, per_share: null, by_category: [] },
        open_positions: { as_of: '2026-08-17 19:00 UTC', rows: [], n: 0, shown: 0, capped: false, total_exposure: 0, total_cost: 0, unrealized_pnl: 0, worthless_n: 0, note: 'No open positions in the public /positions feed.' },
        closed: { as_of: '2026-08-17 19:00 UTC', capped: false, n: 0, shown: 0, won: 0, lost: 0, flat: 0, worthless_not_redeemed: 0, rows: [], realized_pnl: 0, note: 'No resolved positions found in the public feed for this wallet.', source: 'polymarket /closed-positions' },
        activity: { as_of: '2026-08-17 19:00 UTC', n_rows: 0, n_trades: 0, n_redeems: 0, window_truncated: false, first: '', last: '', span_days: null, trades: [], shown: 0, buy_n: 0, sell_n: 0, buy_notional: 0, sell_notional: 0, redeem_notional: 0, net_cash_flow: 0, volume_traded: 0, avg_trade_size: null, trades_per_day: null, source: 'polymarket /activity' },
        categories: { as_of: '2026-08-17 19:00 UTC', rows: [], classifier: 'x', note: 'x' },
        context: { as_of: '2026-08-17 19:00 UTC', n_trades: 0, notional: 0, groups: [], insider_prone_share: null, excluded_share: null, note: 'No trades in the activity window to classify.' },
        limits: ['Harness limit line.']
      } };
      return () => { if (alt) T.liveData.wallet[WALLET_HARNESS_ADDR] = alt; else delete T.liveData.wallet[WALLET_HARNESS_ADDR]; };
    }],
    ['wallet_empty_trades', 'wallet', { walletAddr: WALLET_HARNESS_ADDR, walletInput: WALLET_HARNESS_ADDR, walletTab: 'trades' }, null, (T) => {
      const alt = T.liveData.wallet[WALLET_HARNESS_ADDR];
      T.liveData.wallet[WALLET_HARNESS_ADDR] = { herkunft: 'live', data: {
        wallet: WALLET_HARNESS_ADDR, as_of: '2026-08-17 19:00 UTC', errors: { resolved: 'HTTP 502' },
        identity: { address: WALLET_HARNESS_ADDR, short: '0xabc0…0abc', pseudonym: '', profile_url: 'https://polymarket.com/profile/' + WALLET_HARNESS_ADDR, polygonscan_url: 'https://polygonscan.com/address/' + WALLET_HARNESS_ADDR, first_activity: '', last_activity: '', days_active: null, n_activity_rows: 0, activity_truncated: false },
        track_record: null,
        pnl: { as_of: '2026-08-17 19:00 UTC', window: 'All', points: [], n_points: 0, stats: null, source: 'user-pnl-api.polymarket.com', note: 'The profile PnL curve did not answer.' },
        edge: { as_of: '2026-08-17 19:00 UTC', capped: false, per_dollar: { edge: null, ci_low: null, ci_high: null, groups: 0, significant: false, method: '' }, per_share: null, by_category: [] },
        open_positions: { as_of: '2026-08-17 19:00 UTC', rows: [], n: 0, shown: 0, capped: false, total_exposure: 0, total_cost: 0, unrealized_pnl: 0, worthless_n: 0, note: 'No open positions in the public /positions feed.' },
        closed: { as_of: '2026-08-17 19:00 UTC', capped: false, n: 0, shown: 0, won: 0, lost: 0, flat: 0, worthless_not_redeemed: 0, rows: [], realized_pnl: 0, note: 'No resolved positions found in the public feed for this wallet.', source: 'polymarket /closed-positions' },
        activity: { as_of: '2026-08-17 19:00 UTC', n_rows: 0, n_trades: 0, n_redeems: 0, window_truncated: false, first: '', last: '', span_days: null, trades: [], shown: 0, buy_n: 0, sell_n: 0, buy_notional: 0, sell_notional: 0, redeem_notional: 0, net_cash_flow: 0, volume_traded: 0, avg_trade_size: null, trades_per_day: null, source: 'polymarket /activity' },
        categories: { as_of: '2026-08-17 19:00 UTC', rows: [], classifier: 'x', note: 'x' },
        context: { as_of: '2026-08-17 19:00 UTC', n_trades: 0, notional: 0, groups: [], insider_prone_share: null, excluded_share: null, note: 'No trades in the activity window to classify.' },
        limits: ['Harness limit line.']
      } };
      return () => { if (alt) T.liveData.wallet[WALLET_HARNESS_ADDR] = alt; else delete T.liveData.wallet[WALLET_HARNESS_ADDR]; };
    }],
    // Wallet graph page with a real entity, a candidate and a behaviour block.
    ['graph_data', 'graph', {}, null, (T) => {
      const wa = '0x' + 'a'.repeat(40);
      const wb = '0x' + 'b'.repeat(40);
      const funder = '0x' + 'f'.repeat(40);
      const router = '0x' + '4'.repeat(40);
      T.liveData.graph = {
        _quelle: 'live', available: true, as_of: '2026-08-30 12:00 UTC',
        caveat: 'A best-effort behavioural screen on public trade data: research leads, not legal findings.',
        stats: { scans: 12, hard_edges: 1, candidate_edges: 3, multi_wallet_entities: 1 },
        entities: [{ entity_id: 'entity:' + wa, wallets: [wa, wb], edges: [
          { wallet_a: wa, wallet_b: wb, typ: 'shared_funder', konfidenz: 0.8, first_seen: '2026-07-01T00:00:00Z',
            evidenz: { shared_counterparties: [{ counterparty: funder, direction: 'in', counterparty_wallets: 2, global_partners: 3, global_complete: true, transfers: 22, amount: 0.48, tx_sample: ['0xabc123abc123abc'] }] } }
        ] }],
        entities_capped: false,
        candidates: [{ counterparty: router, direction: 'out', wallets: [wa, wb], wallet_count: 6, narrow_pairs: 1 }],
        candidates_capped: false,
        scans: [{ wallet: wa, scanned_at: '2026-08-30T10:00:00Z', complete: true }],
        behavior: { available: true, note: 'Tier 3 behaviour patterns from the stored tape: shown next to the entities, never used to merge accounts.',
          fingerprints: [{ wallet: wa, burst_prints: 24, burst_seconds: 24, burst_market: 'FC Utrecht vs. PSV: O/U 3.5' }],
          complementary_pairs: [{ wallet_a: wa, wallet_b: wb, events: 8, markets: 2 }] }
      };
      return () => { T.liveData.graph = null; };
    }],
    ['graph_unavailable', 'graph', {}, null, (T) => {
      // _quelle 'live' wie in app.js::fetchGraph: eine ehrliche
      // no-graph-Antwort ist ein Befund und darf nie wie Laden aussehen.
      T.liveData.graph = { _quelle: 'live', available: false,
        note: 'no entity graph on this host; run scripts/run_entity_scan.py',
        behavior: { available: true, note: 'Tier 3 behaviour patterns from the stored tape: shown next to the entities, never used to merge accounts.',
          fingerprints: [{ wallet: '0x' + 'a'.repeat(40), burst_prints: 28, burst_seconds: 33, burst_market: 'Harness burst market' }],
          complementary_pairs: [] },
        as_of: '2026-08-30 12:00 UTC' };
      return () => { T.liveData.graph = null; };
    }],
    ['wallet_tab_linked', 'wallet', { walletTab: 'linked' }, null, (T) => {
      const wb = '0x' + 'b'.repeat(40);
      const funder = '0x' + 'f'.repeat(40);
      T.liveData.walletEntity[WALLET_HARNESS_ADDR] = { herkunft: 'live', data: {
        wallet: WALLET_HARNESS_ADDR, available: true, scanned: true,
        entity_id: 'entity:' + WALLET_HARNESS_ADDR, entity_wallets: [WALLET_HARNESS_ADDR, wb],
        caveat: 'A best-effort behavioural screen on public trade data: research leads, not legal findings.',
        linked_wallets: [{ wallet: wb, typ: 'shared_funder', stufe: 1, konfidenz: 0.8, first_seen: '2026-07-01T00:00:00Z',
          evidenz: { shared_counterparties: [{ counterparty: funder, direction: 'in', counterparty_wallets: 2, transfers: 22, amount: 0.48, tx_sample: ['0xabc'] }] } }],
        candidates: [], edges: [],
        behavior: { available: true, fingerprints: [], complementary_pairs: [] }
      } };
      return () => { delete T.liveData.walletEntity[WALLET_HARNESS_ADDR]; };
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
  // Latenz je Fill, direkt aufgerufen: ein Lauf mit zwei Fills, der zweite
  // einen Tag nach dem Drop. Die Laufzahl erster_fill_s gilt nur fuer den
  // ersten; die zweite Zeile darf sie nicht erben.
  const latenzLauf = {
    profil: 'allin_july10', drop_erkannt_utc: '2026-07-10T01:17:27Z', erster_fill_s: 64.0,
    wetten: [{ fill_ts_utc: '2026-07-10T01:18:31Z' }, { fill_ts_utc: '2026-07-11T02:26:34Z' }]
  };
  const ohneDrop = {
    profil: 'kein_drop', erster_fill_s: 42.0,
    wetten: [{ fill_ts_utc: '2026-07-10T01:18:31Z' }, { fill_ts_utc: '2026-07-10T02:18:31Z' }]
  };
  raus['_fill_latenz'] = JSON.stringify({
    erster: fillLatenzS(latenzLauf, latenzLauf.wetten[0]),
    letzter: fillLatenzS(latenzLauf, latenzLauf.wetten[1]),
    ohne_drop_erster: fillLatenzS(ohneDrop, ohneDrop.wetten[0]),
    ohne_drop_spaeter: fillLatenzS(ohneDrop, ohneDrop.wetten[1]),
    ohne_alles: fillLatenzS({ wetten: [] }, {})
  });
  // Arbitrage scan, pure readings with a pinned clock: the health rule
  // (three scan intervals), the verdict sentence, and the split of the
  // candidates into the upper and the folded table.
  const letzterZyklus = Date.parse(ARB_FIXTURE.health.last_cycle_at);
  raus['_arb_health'] = JSON.stringify({
    frisch: healthStand(ARB_FIXTURE.health, letzterZyklus + 20 * 1000),
    an_der_grenze: healthStand(ARB_FIXTURE.health, letzterZyklus + 90 * 1000),
    alt: healthStand(ARB_FIXTURE.health, letzterZyklus + 3 * 60 * 1000),
    tot: healthStand({ alive: false, last_cycle_at: ARB_FIXTURE.health.last_cycle_at, scan_interval_ms: 30000, cycles_24h: 5, errors_24h: 1 }, letzterZyklus + 1000),
    leer: healthStand(null, letzterZyklus),
    ohne_intervall: healthStand({ alive: true, last_cycle_at: ARB_FIXTURE.health.last_cycle_at }, letzterZyklus + 10 * 3600 * 1000)
  });
  raus['_arb_verdikt'] = JSON.stringify({
    voll: verdiktSatz(ARB_FIXTURE.summary),
    ohne_resolved: verdiktSatz({ raw_candidates_24h: 1, validated_24h: 1 }),
    leer: verdiktSatz({}),
    nur_validated: verdiktSatz({ validated_24h: 3 }),
    null_werte: verdiktSatz({ raw_candidates_24h: 0, validated_24h: 0, resolved_paper_trades: 0 })
  });
  const teilung = teileChancen(ARB_FIXTURE.opportunities);
  raus['_arb_teilung'] = JSON.stringify({
    oben: teilung.oben.map((o) => o.id), unten: teilung.unten.map((o) => o.id),
    ohne_status: teileChancen([{ id: 'a', rejection_reason: 'x' }, { id: 'b' }, { id: 'c', status: 'weird' }]).unten.map((o) => o.id)
  });
  return raus;
}

const ergebnis = { leer: rendern(neuesT()), live: rendern(mitDaten(neuesT())) };
process.stdout.write(JSON.stringify(ergebnis));
