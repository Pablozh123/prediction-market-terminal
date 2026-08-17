// Market Intel terminal — vanilla JS port of the design reference.
// One controller class; each workspace renders as an HTML string from state.

import { num, money, esc, spark, seriesPoints } from './util.js';
import { STUDIEN } from './studies.js';
import { apiGet, apiPost } from './api.js';
import { renderOverview, renderMarkets, renderFlow, renderCross, renderResolved } from './pages/core_pages.js';
import { renderTraders, renderWhale, renderRisk, renderTrack } from './pages/trader_pages.js';
import { renderBacktester, renderCopy, renderPortfolio } from './pages/trading_pages.js';
import { renderAlerts, renderResearch, renderSettings } from './pages/system_pages.js';
import { renderDetail, renderSearch } from './overlays.js';

// Every route stays reachable by hash. The sidebar lists a subset (see
// renderSidebar): Settings, Tracked, Copy trade, Portfolio and Resolved are
// reachable but not advertised — they describe a local paper setup that the
// public host does not run.
const PAGES = {
  overview: renderOverview, markets: renderMarkets, flow: renderFlow,
  cross: renderCross, resolved: renderResolved,
  traders: renderTraders, whale: renderWhale, risk: renderRisk, track: renderTrack,
  backtester: renderBacktester, copy: renderCopy, portfolio: renderPortfolio,
  alerts: renderAlerts, research: renderResearch, settings: renderSettings
};

// Public repository and the wallet the live runs were placed from. Both are
// facts about the project, not settings.
export const REPO_URL = 'https://github.com/Pablozh123/prediction-market-terminal';
export const ONE_PAGER_URL = REPO_URL + '/blob/main/docs/research/ONE_PAGER.md';
export const LIVE_RUN_WALLET_FULL = '0x29afe1bf37700768a640a08f1b35dad5f202f88d';
export const LIVE_RUN_WALLET = '0x29af…f88d';
// Flag log of the risk screen: newest 100 rows, with the price after the flag
// for the newest Polymarket flags (enrich=1).
const RISK_LOG_PATH = '/api/risk/log?limit=100&enrich=1';

class Terminal {
  constructor() {
    this.state = {
      // Nur das erste Segment bestimmt die Seite; das zweite waehlt weiter
      // unten die Studie aus, sobald die Studienliste steht.
      page: (location.hash || '').replace('#', '').split('/')[0] in PAGES
        ? (location.hash || '').replace('#', '').split('/')[0] : 'overview',
      tapeMin: 2500,
      tapeTracked: false,
      // Category chips on Live tape and Whale flow; 'All' shows everything.
      tapeCat: 'All', whaleCat: 'All',
      marketCat: 'All',
      marketFiltersOpen: false,
      mPlatform: 'all', mStatus: 'active', mProb: 'all', mLiq: 'all', mVol: 'all', mEnds: 'all', mAge: 'all',
      mExclude: [], mQuick: 'trending',
      // Cross-venue: the server gates at similarity 0.5 and volume on both
      // venues; the local stepper can only tighten from there.
      crossQuery: '', crossSim: 0.5, crossMaxPairs: 50, crossMinGap: 0, crossLower: 'any',
      crossPmVol: 0, crossKsVol: 0, crossMinPrice: 0, crossMaxPrice: 100,
      marketSort: 'volume',
      marketQuery: '',
      traderRank: 'pnl',
      traderQuery: '', traderFiltersOpen: false,
      tPnl: 'all', tVol: 'all',
      riskView: 'events', riskAgeCheck: false,
      // Kein daemonOn mehr: der Schalter im Frontend behauptete RUNNING, ohne
      // dass etwas lief. Der Zustand kommt aus /api/copy oder gar nicht.
      copyTab: 'orders', copyQuery: '', copySide: 'all', copyStatus2: 'all', copyMin: 'all',
      portTab: 'positions', portQuery: '', portSource: 'all', portSide: 'all', portLosers: false,
      tapeQuery: '', tapePlatform: 'all', tapeSide: 'all', tapeOutcome: 'all',
      // Whale flow: Sortierung der Wallet-Zeilen — 'total' | 'biggest' | 'prints'.
      whaleSort: 'total',
      resQuery: '', resAnswer: 'all', resWindow: 'all', resError: 'all', resSort: 'recent',
      setMarketSample: 250, setTradeSample: 250, setWhale: 2500, setBankroll: 1000, setFee: 20, setSlip: 15,
      alertTab: 'signals', alertQuery: '', alertPlatform: 'all', alertType: 'all', alertScope: 'all',
      thMove: 5, thSpread: 3, thWhale: 2500, thEnding: 72, thHolder: 40,
      riskFilter: 'all',
      detail: null,
      searchOpen: false,
      searchQuery: '',
      btStrategy: 'copy',
      btWindow: 30,
      // Default wallet for the backtester: a public Polymarket address with a
      // long trade history, so the first run returns something to look at.
      btWallet: '0x204f72f35326db932158cba6adff0b9a1da95e14',
      btSizing: 'fixed',
      btStakeFixed: 25,
      btStakePct: 2,
      btStakeMult: 1,
      btStakeKelly: 5,
      btCap: 250,
      btExposure: 50,
      btBankroll: 1000,
      btFee: 20,
      btFeeModel: 'curve',
      btSlip: 15,
      btCompare: '',
      btTab: 'log',
      // Backtester run state: nothing runs until RUN is pressed. 'idle' |
      // 'running' | 'done' | 'error'; btError carries the message, btRetryIn
      // the seconds the server asked us to wait after a 429.
      btRun: 'idle', btError: '', btRetryIn: 0, btDirty: false,
      advancedOpen: false,
      sizingSimOpen: false,
      researchTab: 0,
      liveTab: 'runs',
      alertsOn: { movers: true, volume: true, whales: true, spreads: false, holders: false, endings: true },
      settingsOn: { telegram: true, autotop: false, kalshi: true, sports: false, cache: true, admin: true },
      clock: this.utcClock(),
      // 'waiting' bis zur ersten Antwort, dann 'live' oder 'error'. Der
      // fruehere Wert 'demo' behauptete einen Demo-Datensatz, den es nicht gibt.
      live: 'waiting', liveAsOf: '', tapeAsOf: ''
    };

    // Datencontainer. Sie starten leer, nicht auf einem Demo-Satz: bis eine
    // Antwort da ist, gibt es nichts zu zeigen. Frueher standen hier zwoelf
    // erfundene Maerkte, acht erfundene Wallets und ein erfundener Tape, und
    // jede Seite rechnete ihre Kennzahlen daraus aus.
    this.markets = [];
    this.marketExtra = {};
    this.traders = [];
    this.risks = [];
    this.tape = [];
    this.crossPairs = [];
    this.studies = STUDIEN;
    // Herkunft je Container: null heisst noch keine Antwort, sonst
    // { quelle: 'live' | 'leer' | 'fehler', fehler }. Eine leere Antwort und
    // eine ausgebliebene Antwort sagen Verschiedenes, und beides ist etwas
    // anderes als eine Zeile, die jemand hingeschrieben hat.
    this.herkunft = { markets: null, tape: null, traders: null, risks: null, cross: null };
    // Research landing payloads (static JSON under ./data, also served by
    // /api/research/*): the verdict board, the live-runs strip and the field
    // notes on the Overview. Each key is null until its request answered.
    this.landing = { micro: null, runs: null, notes: null, herkunft: { micro: null, runs: null, notes: null } };
    // Zweites Adresssegment aufloesen: #research/microstructure soll die
    // Studie oeffnen, nicht die erste in der Liste.
    const segmente = (location.hash || '').replace('#', '').split('/');
    if (segmente[0] === 'research' && segmente[1]) {
      const treffer = this.studienIndexAus(segmente[1]);
      if (treffer >= 0) {
        this.state.page = 'research';
        this.state.researchTab = treffer;
        // Drittes Segment = Karte auf der Seite (#research/microstructure/<id>).
        this._pendingAnchor = segmente[2] ? segmente.join('/') : null;
      }
    }
    // Per-endpoint live payloads; templates use these when present and show
    // an empty state naming the source otherwise.
    // riskLog: the flag log of the risk screen (/api/risk/log), fetched only
    // when its tab is opened — null until then.
    this.liveData = { leaderboard: null, cross: null, risk: null, riskLog: null, alerts: null, copy: null, portfolio: null, research: {}, backtest: null, walletDetail: {} };

    this._acts = [];
    this._inps = [];
    this._focus = null;
  }

  utcClock() {
    const d = new Date();
    const p = (n) => String(n).padStart(2, '0');
    return p(d.getUTCHours()) + ':' + p(d.getUTCMinutes());
  }

  // ---- formatting shared with pages ----
  num(n) { return num(n); }
  money(n) { return money(n); }
  esc(v) { return esc(v); }
  spark(a) { return spark(a); }
  seriesPoints(v, w, h) { return seriesPoints(v, w, h); }

  // ---- action / input registries (rebuilt every render) ----
  act(fn) { this._acts.push(fn); return 'data-act="' + (this._acts.length - 1) + '"'; }
  inp(fn, key) { this._inps.push(fn); return 'data-inp="' + (this._inps.length - 1) + '" data-key="' + key + '"'; }

  setState(patch) {
    Object.assign(this.state, patch);
    this.render();
  }

  // ---- shared UI atoms (styles verbatim from the reference) ----
  opt(label, active, patch) {
    const style = "font-family:'JetBrains Mono',monospace; font-size:10.5px; border-radius:5px; padding:5px 9px; cursor:pointer; " + (active ? 'color:#0A0D0F; background:#C8F542; font-weight:600' : 'color:rgba(255,255,255,.55); border:1px solid rgba(255,255,255,.14)');
    return '<div ' + this.act(typeof patch === 'function' ? patch : () => this.setState(patch)) + ' style="' + style + '">' + esc(label) + '</div>';
  }

  chip(label, active, patch) {
    const style = "font-family:'JetBrains Mono',monospace; font-size:10.5px; letter-spacing:.06em; border-radius:5px; padding:5px 10px; cursor:pointer; " + (active ? 'color:#0A0D0F; background:#C8F542; font-weight:600' : 'color:rgba(255,255,255,.55); border:1px solid rgba(255,255,255,.16)');
    return '<div ' + this.act(typeof patch === 'function' ? patch : () => this.setState(patch)) + ' style="' + style + '">' + esc(label) + '</div>';
  }

  tab(label, active, patch) {
    const style = 'font-size:12.5px; border-radius:7px; padding:7px 13px; cursor:pointer; ' + (active ? 'color:#0A0D0F; background:#C8F542; font-weight:600' : 'color:rgba(255,255,255,.6); border:1px solid rgba(255,255,255,.16)');
    return '<div ' + this.act(typeof patch === 'function' ? patch : () => this.setState(patch)) + ' style="' + style + '">' + esc(label) + '</div>';
  }

  toggle(on, patch) {
    const wrap = 'width:34px; height:19px; flex:none; border-radius:10px; padding:2px; display:flex; cursor:pointer; background:' + (on ? '#C8F542' : 'rgba(255,255,255,.14)') + '; justify-content:' + (on ? 'flex-end' : 'flex-start');
    const knob = 'width:15px; height:15px; border-radius:50%; background:' + (on ? '#0A0D0F' : 'rgba(255,255,255,.55)');
    return '<div ' + this.act(typeof patch === 'function' ? patch : () => this.setState(patch)) + ' style="' + wrap + '"><div style="' + knob + '"></div></div>';
  }

  stepper(valueLabel, onDown, onUp, size) {
    const s = size === 'lg';
    const btn = 'width:' + (s ? 32 : 28) + 'px; height:' + (s ? 34 : 32) + 'px; flex:none; border:1px solid rgba(255,255,255,.16); border-radius:' + (s ? 8 : 7) + 'px; display:flex; align-items:center; justify-content:center; font-family:\'JetBrains Mono\',monospace; font-size:' + (s ? 15 : 14) + 'px; color:rgba(255,255,255,.7); cursor:pointer';
    const val = 'flex:1; background:#10151A; border:1px solid rgba(255,255,255,.16); border-radius:' + (s ? 8 : 7) + 'px; padding:' + (s ? '8px 12px' : '7px 8px') + '; font-family:\'JetBrains Mono\',monospace; font-size:' + (s ? 13 : 12.5) + 'px; text-align:center';
    return '<div style="display:flex; align-items:center; gap:' + (s ? 8 : 6) + 'px">'
      + '<div ' + this.act(onDown) + ' class="hv-bd35w" style="' + btn + '">−</div>'
      + '<div style="' + val + '">' + esc(valueLabel) + '</div>'
      + '<div ' + this.act(onUp) + ' class="hv-bd35w" style="' + btn + '">+</div></div>';
  }

  changeStyle(chg) {
    return "font-family:'JetBrains Mono',monospace; font-size:13px; text-align:right; color:" + (chg >= 0 ? '#C8F542' : '#FF4545');
  }

  marketView(m) {
    return {
      title: m.title,
      meta: m.venue.toUpperCase() + ' · ' + m.cat.toUpperCase(),
      // No sparkline: the API carries a one-day change, not an intraday path.
      sparkPoints: '',
      color: m.chg >= 0 ? '#C8F542' : '#FF4545',
      priceLabel: m.yes + '¢',
      changeLabel: (m.chg >= 0 ? '+' : '') + m.chg + '¢',
      changeStyle: this.changeStyle(m.chg),
      volLabel: money(m.vol),
      ends: m.ends,
      act: this.act(() => this.openMarket(m.id))
    };
  }

  openMarket(id) {
    this.setState({ detail: { kind: 'market', id }, searchOpen: false });
    this.fetchMarketHistory(id);
  }

  async fetchMarketHistory(id) {
    if (this.state.live !== 'live' || this.liveData.marketHistory && this.liveData.marketHistory[id]) return;
    this.liveData.marketHistory = this.liveData.marketHistory || {};
    try {
      const h = await apiGet('/api/market/' + encodeURIComponent(id) + '/history?days=1&interval=5m');
      if (h && h.points && h.points.length > 1) { this.liveData.marketHistory[id] = h.points; this.render(); }
    } catch (err) { /* Detail zeigt den Leerzustand ohne Kurve */ }
  }
  openWallet(name) {
    this.setState({ detail: { kind: 'wallet', id: name }, searchOpen: false });
    this.fetchWalletDetail(name);
  }

  // Per-market extras from the API row (spread, age, days to resolution).
  // Unknown fields are null; no filter operates on a made-up default.
  marketExtraOf(m) { return this.marketExtra[m.id] || { spread: null, age: null, endsDays: null }; }

  tapeFiltered() {
    const s = this.state;
    return this.tape.filter((t) => {
      if (t.size < s.tapeMin) return false;
      if (s.tapeTracked && !t.tracked) return false;
      if (s.tapePlatform !== 'all' && t.venue !== s.tapePlatform) return false;
      if (s.tapeSide !== 'all' && t.side.indexOf(s.tapeSide) !== 0) return false;
      if (s.tapeOutcome !== 'all' && t.side.indexOf(s.tapeOutcome) < 0) return false;
      if (s.tapeCat !== 'All' && (t.category || 'Other') !== s.tapeCat) return false;
      if (s.tapeQuery.trim()) {
        const tq = s.tapeQuery.trim().toLowerCase();
        if (t.market.toLowerCase().indexOf(tq) < 0 && t.wallet.toLowerCase().indexOf(tq) < 0) return false;
      }
      return true;
    });
  }

  tapeRowView(t) {
    return {
      ago: t.ago, wallet: t.wallet, market: t.market, side: t.side, price: t.price,
      size: money(t.size), venue: t.venue, category: t.category || 'Other',
      sideStyle: "font-family:'JetBrains Mono',monospace; font-size:12.5px; color:" + (t.side.indexOf('BUY') === 0 ? '#C8F542' : '#FF4545'),
      act: this.act(() => {
        const m = this.markets.find((x) => x.title === t.market);
        if (m) this.setState({ detail: { kind: 'market', id: m.id } });
      })
    };
  }

  riskCardView(r) {
    return {
      kind: r.kind, score: r.score, market: r.market, detail: r.detail,
      wallets: r.wallets, notional: r.notional, window: r.window, venue: r.venue,
      kindStyle: "font-family:'JetBrains Mono',monospace; font-size:10.5px; letter-spacing:.12em; color:" + (r.sev === 'high' ? '#F5A623' : r.sev === 'medium' ? 'rgba(255,255,255,.66)' : 'rgba(255,255,255,.45)'),
      scoreStyle: "font-family:'JetBrains Mono',monospace; font-size:18px; color:" + (r.sev === 'high' ? '#F5A623' : 'rgba(255,255,255,.72)'),
      act: this.act(() => {
        const m = this.markets.find((x) => x.title === r.market);
        if (m) this.setState({ detail: { kind: 'market', id: m.id } });
      })
    };
  }

  // ---- sidebar / topbar ----
  navItem(id, label, badge, badgeColor) {
    const active = this.state.page === id;
    const style = 'display:flex; align-items:center; justify-content:space-between; gap:8px; padding:7px 10px; border-radius:7px; cursor:pointer; margin-bottom:2px; border-left:2px solid ' + (active ? '#C8F542' : 'transparent') + '; background:' + (active ? 'rgba(200,245,66,.10)' : 'transparent');
    const labelStyle = 'font-size:13.5px; color:' + (active ? '#ffffff' : 'rgba(255,255,255,.62)') + '; font-weight:' + (active ? '600' : '400');
    const badgeStyle = badge ? ("font-family:'JetBrains Mono',monospace; font-size:10px; padding:1px 6px; border-radius:3px; " + (badgeColor === 'amber' ? 'color:#F5A623; border:1px solid rgba(245,166,35,.4)' : 'color:#0A0D0F; background:#C8F542')) : 'display:none';
    return '<div ' + this.act(() => this.go(id)) + ' class="hv-el" style="' + style + '">'
      + '<span style="' + labelStyle + '">' + esc(label) + '</span>'
      + '<span style="' + badgeStyle + '">' + esc(badge || '') + '</span></div>';
  }

  // A research study as a sidebar entry. Studies keep their own routes
  // (#research/<slug>, defined by studies.js); the sidebar just groups them.
  navStudy(i, label, accent) {
    const active = this.state.page === 'research' && this.state.researchTab === i;
    const farbe = accent || '#4F8EF7';
    const style = 'display:flex; align-items:center; justify-content:space-between; gap:8px; padding:7px 10px; border-radius:7px; cursor:pointer; margin-bottom:2px; border-left:2px solid ' + (active ? farbe : 'transparent') + '; background:' + (active ? 'rgba(79,142,247,.12)' : 'transparent');
    const labelStyle = 'font-size:13.5px; color:' + (active ? '#ffffff' : 'rgba(255,255,255,.62)') + '; font-weight:' + (active ? '600' : '400');
    return '<div ' + this.act(() => this.goStudy(i)) + ' class="hv-el" style="' + style + '">'
      + '<span style="' + labelStyle + '">' + esc(label) + '</span></div>';
  }

  // Sidebar entry for a study by its tab name; missing studies render nothing
  // rather than a dead entry.
  navStudyByTab(tab, label) {
    const i = this.studies.findIndex((st) => st.tab === tab);
    return i >= 0 ? this.navStudy(i, label || tab) : '';
  }

  goStudy(i, anker) {
    // Optionaler Anker (z.B. eine Studienkarte auf der Microstructure-Seite):
    // die Seite scrollt nach dem Rendern dorthin statt oben zu landen.
    this._pendingAnchor = anker ? String(anker) : null;
    this.setState({ page: 'research', researchTab: i, detail: null });
    // Eigene Adresse je Studie: eine Bewerbung wird als Link verschickt, und
    // ein Verweis auf #research landete bisher immer auf der Review queue.
    try { history.pushState(null, '', '#' + (anker ? String(anker) : 'research/' + this.studienSlug(i))); } catch (e) { /* file:// */ }
    this.fetchPageData('research');
  }

  goStudySlug(slug) {
    const i = this.studienIndexAus(slug);
    if (i >= 0) this.goStudy(i);
  }

  studienSlug(i) {
    const st = this.studies[i];
    return st ? st.tab.toLowerCase().replace(/ /g, '-') : String(i);
  }

  studienIndexAus(slug) {
    if (!slug) return -1;
    for (let i = 0; i < this.studies.length; i += 1) {
      if (this.studienSlug(i) === slug) return i;
    }
    return -1;
  }

  go(id) {
    this.setState({ page: id, detail: null });
    // pushState statt replaceState: der Zurueck-Knopf soll funktionieren.
    try { history.pushState(null, '', '#' + id); } catch (e) { /* file:// */ }
    this.fetchPageData(id);
  }

  renderSidebar() {
    const hoheRisiken = this.risks.filter((r) => r.sev === 'high').length;
    // Order is the argument: what was measured first, the record second, the
    // live feeds last. Settings, Tracked, Copy trade, Portfolio and Resolved
    // stay reachable by hash but describe a local paper setup and are not
    // listed on the public host.
    const groups = [
      { label: 'START HERE', items: [this.navItem('overview', 'Overview')] },
      { label: 'EVIDENCE', items: [
        this.navStudyByTab('Microstructure'),
        this.navStudyByTab('Live runs'),
        this.navStudyByTab('Pilot'),
        this.navStudyByTab('Category efficiency'),
        this.navStudyByTab('Mentions latency'),
        this.navStudyByTab('Pipeline forward')
      ] },
      { label: 'RECORD', items: [
        this.navStudyByTab('Postmortems', 'Post-mortems'),
        this.navStudyByTab('Field notes'),
        this.navStudyByTab('Methodology'),
        this.navStudyByTab('Review queue')
      ] },
      // Kein Zaehler ohne Daten: eine 0 im Abzeichen liest sich als Messung,
      // solange gar nichts geladen ist.
      { label: 'LIVE DATA', items: [
        this.navItem('markets', 'Markets'),
        this.navItem('flow', 'Live tape', this.tape.length ? String(this.tape.length) : ''),
        this.navItem('whale', 'Whale flow'),
        this.navItem('cross', 'Cross-venue'),
        this.navItem('traders', 'Leaderboard'),
        this.navItem('risk', 'Risk screen', hoheRisiken ? String(hoheRisiken) : '', 'amber'),
        this.navItem('alerts', 'Alerts'),
        this.navItem('backtester', 'Backtester')
      ] }
    ];
    const groupHtml = groups.map((g) =>
      '<div style="margin-bottom:14px">'
      + '<div style="font-family:\'JetBrains Mono\',monospace; font-size:10px; letter-spacing:.18em; padding:0 6px 6px; color:rgba(255,255,255,.35)">' + g.label + '</div>'
      + g.items.join('') + '</div>'
    ).join('');
    // Footer: repository, the read-only statement, and the wallet the live
    // runs were placed from. The paper-equity box that stood here reported a
    // missing paper account on the public host — a box about a thing that
    // does not exist there.
    const foot = "font-family:'JetBrains Mono',monospace; font-size:10px; line-height:1.7; color:rgba(255,255,255,.4)";
    const runsIdx = this.studies.findIndex((st) => st.tab === 'Live runs');
    return ''
      + '<div style="display:flex; align-items:center; gap:9px; padding:0 6px 18px">'
      + '<div style="width:10px; height:10px; background:#C8F542; transform:rotate(45deg)"></div>'
      + '<div style="font-family:\'Instrument Serif\',serif; font-size:21px">Market Intel</div></div>'
      + '<div ' + this.act(() => this.setState({ searchOpen: true })) + ' class="hv-bd22" style="display:flex; align-items:center; gap:8px; background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:8px; padding:9px 10px; cursor:pointer; margin-bottom:18px">'
      + '<div style="font-family:\'JetBrains Mono\',monospace; font-size:12px; color:rgba(255,255,255,.45); flex:1">Search</div>'
      + '<div style="font-family:\'JetBrains Mono\',monospace; font-size:11px; color:rgba(255,255,255,.35); border:1px solid rgba(255,255,255,.16); border-radius:4px; padding:0 5px">/</div></div>'
      + groupHtml
      + '<div style="margin-top:auto; padding-top:16px; border-top:1px solid rgba(255,255,255,.09)">'
      + '<div style="' + foot + '"><a href="' + REPO_URL + '" target="_blank" rel="noopener">github.com/Pablozh123/prediction-market-terminal</a></div>'
      + '<div style="' + foot + '; margin-top:6px">Read-only. No orders placed. Public Polymarket &amp; Kalshi data.</div>'
      + '<div style="' + foot + '; margin-top:6px">Live-run wallet '
      + (runsIdx >= 0
        ? '<span ' + this.act(() => this.goStudy(runsIdx)) + ' class="hv-lime" title="' + esc(LIVE_RUN_WALLET_FULL) + ' — every bet on the Live runs page" style="color:rgba(255,255,255,.7); cursor:pointer; text-decoration:underline dotted">' + esc(LIVE_RUN_WALLET) + '</span>'
        : esc(LIVE_RUN_WALLET))
      + '</div></div>';
  }

  renderTopbar() {
    const s = this.state;
    const liveDot = s.live === 'live' ? '#C8F542' : s.live === 'error' ? '#FF4545' : '#F5A623';
    // Drei Zustaende, alle auf Englisch: noch keine Antwort, Antwort da, Antwort
    // ausgeblieben nach einer, die da war. "Demo" gibt es nicht — es gibt
    // keinen Demo-Datensatz, den die Zeile ankuendigen koennte.
    const liveLabel = s.live === 'live' ? 'LIVE · POLYMARKET + KALSHI' : s.live === 'error' ? 'API OFFLINE · LAST KNOWN STATE' : 'WAITING FOR API';
    // "Sign in" und "Get alerts" standen rechts ohne Handler. Es gibt weder
    // eine Anmeldung noch eine Alarmzustellung, die von hier aus einzurichten
    // waere (die haengt am Scanner-Skript). Zwei Knoepfe, die nichts tun, sind
    // ein Versprechen ohne Deckung; die Leiste zeigt nur noch den Zustand.
    return ''
      + '<div style="display:flex; align-items:center; gap:10px">'
      + '<span style="width:7px; height:7px; border-radius:50%; background:' + liveDot + '; display:inline-block; animation:livePulse 1.6s ease-in-out infinite"></span>'
      + '<span style="font-family:\'JetBrains Mono\',monospace; font-size:11px; letter-spacing:.16em; color:rgba(255,255,255,.66)">' + liveLabel + ' · ' + s.clock + ' UTC</span></div>'
      + '<div style="font-family:\'JetBrains Mono\',monospace; font-size:10px; letter-spacing:.14em; color:rgba(255,255,255,.35)">MICROSTRUCTURE, MEASURED · READ-ONLY · NO ORDERS</div>';
  }

  // ---- data layer ----
  async pollLive() {
    try {
      const [mk, tp] = await Promise.all([
        apiGet('/api/markets?limit=250'),
        // Grosse Prints ab $2,5k auf beiden Venues; ohne Mindestbetrag bestuende
        // das Fenster nur aus Kalshi-Mikro-Trades der 15-Minuten-Kryptomaerkte.
        apiGet('/api/tape?limit=250&min_cash=2500')
      ]);
      const { mapMarket, mapTrade } = await import('./util.js');
      // Uebernommen wird, was kommt, auch die leere Liste. Der frühere
      // Laengen-Guard liess bei einer korrekt leeren Antwort die alten Zeilen
      // stehen und meldete daneben LIVE.
      this.markets = (mk.rows || []).map((r, i) => mapMarket(r, i));
      this.marketExtra = {};
      this.markets.forEach((m) => { this.marketExtra[m.id] = m._extra; });
      this.herkunft.markets = { quelle: this.markets.length ? 'live' : 'leer' };
      this.tape = (tp.rows || []).map((r) => mapTrade(r));
      this.herkunft.tape = { quelle: this.tape.length ? 'live' : 'leer' };
      this.setState({ live: 'live', liveAsOf: String(mk.as_of || ''), tapeAsOf: String(tp.as_of || mk.as_of || '') });
    } catch (err) {
      // Nach einem geglueckten Lauf bleibt der letzte Stand stehen, die
      // Kopfzeile sagt das bereits. Vorher gibt es nichts zu behalten.
      const text = String(err && err.message ? err.message : err);
      if (this.state.live === 'live') this.setState({ live: 'error' });
      else {
        this.herkunft.markets = { quelle: 'fehler', fehler: text };
        this.herkunft.tape = { quelle: 'fehler', fehler: text };
        this.render();
      }
    }
  }

  // Research payloads for the landing page. apiGet falls back to the static
  // ./data/*.json when no API answers, so this works on a plain file host.
  // Each key records its own outcome; a missing payload renders an empty
  // state that names the file, never a placeholder number.
  async ladeLanding() {
    const quellen = [
      ['micro', '/api/research/microstructure'],
      ['runs', '/api/research/live-runs'],
      ['notes', '/api/research/field-notes']
    ];
    await Promise.all(quellen.map(async ([key, pfad]) => {
      try {
        const antwort = await apiGet(pfad);
        if (antwort && typeof antwort === 'object') {
          this.landing[key] = antwort;
          this.landing.herkunft[key] = { quelle: antwort._quelle === 'statisch' ? 'statisch' : 'live' };
        } else {
          this.landing.herkunft[key] = { quelle: 'leer' };
        }
      } catch (err) {
        this.landing.herkunft[key] = { quelle: 'fehler', fehler: String(err && err.message ? err.message : err) };
      }
    }));
    this.render();
  }

  // Herkunft je Datenblock. Frueher entschieden Laengen-Guards: eine korrekt
  // leere Live-Antwort liess die Demo stehen, und ein Fehler wurde still
  // geschluckt. Beides fuehrte dazu, dass die Seite erfundene Zahlen zeigte
  // und dabei LIVE meldete. Jetzt wird jede Antwort abgelegt, auch die leere,
  // und ein Fehler ebenfalls, damit die Seite sagen kann, was los ist.
  async holen(schluessel, pfad, danach) {
    if (this.liveData[schluessel]) return;
    try {
      const antwort = await apiGet(pfad);
      if (antwort && typeof antwort === 'object') {
        antwort._quelle = 'live';
        this.liveData[schluessel] = antwort;
        if (danach) danach(antwort);
      } else {
        this.liveData[schluessel] = { _quelle: 'leer' };
      }
    } catch (err) {
      this.liveData[schluessel] = { _quelle: 'fehler', _fehler: String(err && err.message ? err.message : err) };
    }
    this.render();
  }

  // Der Alarm-Pfad traegt die eingestellten Schwellen. Der Endpunkt nimmt
  // Bewegung und Spread als Anteil, die Regler stehen in Cent.
  alarmPfad() {
    const s = this.state;
    return '/api/alerts'
      + '?min_move=' + (s.thMove / 100).toFixed(4)
      + '&max_spread=' + (s.thSpread / 100).toFixed(4)
      + '&min_whale=' + s.thWhale
      + '&ending_days=' + Math.max(1, Math.round(s.thEnding / 24));
  }

  // Eine geaenderte Schwelle heisst: neu scannen. Ohne das Verwerfen liefert
  // holen() die alte Antwort zurueck und die Regler blieben wirkungslos.
  alarmNeuLaden(patch) {
    Object.assign(this.state, patch);
    this.liveData.alerts = null;
    this.render();
    this.fetchPageData('alerts');
  }

  // Forget one endpoint's answer and ask again — the retry for a failed or
  // rate-limited request (holen() never re-asks on its own).
  neuLaden(schluessel, page) {
    this.liveData[schluessel] = null;
    if (schluessel === 'risk') { this.herkunft.risks = null; this.risks = []; }
    if (schluessel === 'cross') { this.herkunft.cross = null; this.crossPairs = []; }
    this.render();
    this.fetchPageData(page || schluessel);
  }

  // Open the flag-log tab of the risk screen and fetch the log once. The log
  // is not part of /api/risk: it is read only when someone wants to see it,
  // and re-read only via "Try again" (neuLaden) or a page reload.
  openRiskLog() {
    this.setState({ riskView: 'log' });
    if (!this.liveData.riskLog) this.holen('riskLog', RISK_LOG_PATH);
  }

  // Herkunft eines Containers aus der Antwort ableiten, die holen() abgelegt
  // hat. Vorhandensein entscheidet, nicht Laenge.
  herkunftAus(schluessel, zeilen) {
    const antwort = this.liveData[schluessel];
    if (!antwort) return null;
    if (antwort._quelle === 'fehler') return { quelle: 'fehler', fehler: antwort._fehler };
    return { quelle: zeilen && zeilen.length ? 'live' : 'leer' };
  }

  async fetchPageData(page) {
    if (page === 'traders') {
      await this.holen('leaderboard', '/api/leaderboard?limit=100', (lb) => {
        this.applyLeaderboard(lb.rows || []);
      });
      this.herkunft.traders = this.herkunftAus('leaderboard', this.traders);
    } else if (page === 'cross') {
      // While the request runs the page shows a loading line; the server
      // already applies the honesty gate (similarity >= 0.5, volume on both
      // venues), so nothing here lowers a threshold to make rows appear.
      await this.holen('cross', '/api/cross', (cr) => {
        this.crossPairs = cr.rows || [];
      });
      this.herkunft.cross = this.herkunftAus('cross', this.crossPairs);
    } else if (page === 'risk') {
      // Bewusst nicht mehr von der Startseite: der erste Aufbau paged einen Tag
      // Prints und schlaegt Marktkategorien nach, das blockierte die Overview.
      // The flag log is a separate, cheaper request and only asked for while
      // its tab is open (see openRiskLog); a retry via neuLaden lands here.
      const logNeeded = this.state.riskView === 'log' && !this.liveData.riskLog;
      await Promise.all([
        this.holen('risk', '/api/risk', (rk) => {
          this.risks = rk.events || [];
        }),
        logNeeded ? this.holen('riskLog', RISK_LOG_PATH) : Promise.resolve()
      ]);
      this.herkunft.risks = this.herkunftAus('risk', this.risks);
    } else if (page === 'alerts') {
      // Die Schwellen gehoeren an den Endpunkt, der scannt. Bis eben blieben
      // sie im Frontend: der Scan lief mit seinen Voreinstellungen, und die
      // Zeile darueber nannte die Werte der Regler. Die Seite beschrieb damit
      // einen Scan, den es nicht gegeben hat.
      await this.holen('alerts', this.alarmPfad());
    } else if (page === 'copy' || page === 'portfolio') {
      await this.holen('copy', '/api/copy');
      if (page === 'portfolio') await this.holen('track', '/api/track');
    } else if (page === 'resolved') {
      await this.holen('resolved', '/api/resolved');
    } else if (page === 'track') {
      await this.holen('track', '/api/track');
    } else if (page === 'research') {
      const key = this.studies[this.state.researchTab].tab;
      if (!this.liveData.research[key]) {
        const pfad = '/api/research/' + encodeURIComponent(key.toLowerCase().replace(/ /g, '-'));
        try {
          const rs = await apiGet(pfad);
          this.liveData.research[key] = rs && typeof rs === 'object' ? rs : { _quelle: 'leer' };
        } catch (err) {
          this.liveData.research[key] = { _quelle: 'fehler', _fehler: String(err && err.message ? err.message : err) };
        }
        this.render();
      }
    }
  }

  applyLeaderboard(rows) {
    const shortW = (w) => (w && String(w).length > 12 ? String(w).slice(0, 6) + '…' + String(w).slice(-4) : String(w || ''));
    this.traders = rows.map((r) => ({
      name: String(r.name || r.pseudonym || '') || shortW(r.wallet || r.proxyWallet) || '—',
      wallet: shortW(r.wallet || r.proxyWallet),
      walletFull: String(r.wallet || r.proxyWallet || ''),
      pnl: +r.pnl || 0,
      win: r.win != null ? +r.win : null,
      resolved: r.resolved != null ? +r.resolved : null,
      vol: +r.vol || +r.volume || 0,
      score: r.score != null ? +r.score : null,
      grade: r.grade || null,
      scoreN: r.score_n != null ? +r.score_n : null,
      scoreCi: r.score_ci || null,
      sampleBadge: r.sample_badge || null,
      // Score components as a labelled list (api_views.score_parts); the raw
      // reason string is kept only as a fallback for older payloads.
      scoreParts: Array.isArray(r.score_parts) ? r.score_parts : [],
      tags: String(r.tags || '')
    }));
  }

  async fetchWalletDetail(name) {
    if (this.state.live !== 'live') return;
    const t = this.traders.find((x) => x.name === name);
    const addr = t && t.walletFull;
    if (!addr || this.liveData.walletDetail[name]) return;
    try {
      const wd = await apiGet('/api/wallet/' + addr);
      if (wd) { this.liveData.walletDetail[name] = wd; this.render(); }
    } catch (err) { /* detail stays on list data */ }
  }

  // Backtest runs only when asked. Every stepper used to fire a debounced
  // request, which on the public host meant a 429 after three clicks and a
  // panel that flickered between results. Now: RUN starts it, the page shows
  // "running…", a 429 says how long to wait, and the last result stays put.
  runBacktest() {
    const s = this.state;
    if (s.btRun === 'running') return;
    clearTimeout(this._btRetryT);
    this.setState({ btRun: 'running', btError: '', btRetryIn: 0, btDirty: false });
    const body = {
      wallet: s.btWallet.trim(),
      window_days: s.btWindow,
      strategy: s.btStrategy,
      sizing_mode: s.btSizing,
      stake_fixed: s.btStakeFixed,
      stake_pct: s.btStakePct,
      stake_mult: s.btStakeMult,
      stake_kelly: s.btStakeKelly,
      cap: s.btCap,
      exposure_pct: s.btExposure,
      bankroll: s.btBankroll,
      fee_bps: s.btFee,
      fee_model: s.btFeeModel,
      slippage_bps: s.btSlip,
      compare: s.btCompare.trim() || null,
      variants: !!s.sizingSimOpen
    };
    apiPost('/api/backtest', body).then((resp) => {
      if (resp && resp.stats) {
        this.liveData.backtest = resp;
        this.setState({ btRun: 'done', btError: '' });
      } else {
        this.setState({ btRun: 'error', btError: 'The backtest answered without statistics — nothing to show for this window.' });
      }
    }).catch((err) => {
      if (err && err.status === 429) {
        const warten = Math.max(1, Math.round(err.retryAfter || 10));
        this.setState({ btRun: 'error', btError: 'rate-limited', btRetryIn: warten });
        this._btCountdown();
      } else {
        const text = String(err && err.message ? err.message : err);
        this.setState({ btRun: 'error', btError: text === 'HTTP 502' ? 'The backtest engine failed on this wallet and window (HTTP 502).' : text });
      }
    });
  }

  // Count the retry window down so the line reads "retry in 7 s", not a
  // number that stopped being true the moment it was written.
  _btCountdown() {
    clearTimeout(this._btRetryT);
    if (this.state.btRetryIn <= 0) return;
    this._btRetryT = setTimeout(() => {
      const rest = this.state.btRetryIn - 1;
      this.setState({ btRetryIn: Math.max(0, rest) });
      if (rest > 0) this._btCountdown();
    }, 1000);
  }

  // Kept for callers that only want to mark the setup as changed: a click on
  // a stepper marks the current result as stale instead of re-running.
  runBacktestLive() {
    if (this.liveData.backtest && !this.state.btDirty) this.setState({ btDirty: true });
    else this.render();
  }

  // ---- render loop ----
  render() {
    this._acts = [];
    this._inps = [];
    const ae = document.activeElement;
    if (ae && ae.dataset && ae.dataset.key) {
      this._focus = { key: ae.dataset.key, start: ae.selectionStart, end: ae.selectionEnd };
    } else {
      this._focus = null;
    }

    // Was der Leser aufgeklappt hat, bleibt aufgeklappt, und die Seite bleibt,
    // wo sie war: der Poll alle 30 s baut das DOM neu auf, und ohne diese
    // beiden Schritte schloss sich jedes <details> und die Seite sprang hoch.
    const main = document.getElementById('main');
    const scroller = main ? main.closest('.content') || main : null;
    const scrollVorher = scroller ? scroller.scrollTop : 0;
    const seiteVorher = this._renderedPage;
    const offen = [];
    if (main) {
      // Schluessel: data-key, sonst Zusammenfassungstext plus Position — die
      // zwoelf Studienkarten tragen denselben Summary-Text.
      main.querySelectorAll('details').forEach((d, idx) => {
        if (!d.open) return;
        const key = d.getAttribute('data-key') || ((d.querySelector('summary') ? d.querySelector('summary').textContent.trim() : '') + '#' + idx);
        offen.push(key);
      });
    }

    document.getElementById('sidebar').innerHTML = this.renderSidebar();
    document.getElementById('topbar').innerHTML = this.renderTopbar();
    const pageFn = PAGES[this.state.page] || renderOverview;
    document.getElementById('main').innerHTML = pageFn(this);
    document.getElementById('detail').innerHTML = renderDetail(this);
    document.getElementById('search').innerHTML = renderSearch(this);

    const seiteJetzt = this.state.page + '/' + (this.state.page === 'research' ? this.state.researchTab : '');
    if (main && offen.length && seiteJetzt === seiteVorher) {
      main.querySelectorAll('details').forEach((d, idx) => {
        const key = d.getAttribute('data-key') || ((d.querySelector('summary') ? d.querySelector('summary').textContent.trim() : '') + '#' + idx);
        if (offen.indexOf(key) >= 0) d.setAttribute('open', '');
      });
    }
    if (this._pendingAnchor) {
      // Der Anker bleibt vorgemerkt, bis die Karte tatsaechlich im DOM ist:
      // die Studienseite rendert erst leer und dann noch einmal mit Nutzlast.
      const ziel = document.getElementById(this._pendingAnchor);
      if (ziel) {
        this._pendingAnchor = null;
        ziel.scrollIntoView({ block: 'start' });
      } else if (this._pendingAnchor.indexOf(this.state.page) !== 0) {
        this._pendingAnchor = null;
      } else if (scroller && seiteJetzt !== seiteVorher) {
        scroller.scrollTop = 0;
      }
    } else if (scroller) {
      scroller.scrollTop = seiteJetzt === seiteVorher ? scrollVorher : 0;
    }
    this._renderedPage = seiteJetzt;

    if (this._focus) {
      const el = document.querySelector('[data-key="' + this._focus.key + '"]');
      if (el) {
        el.focus();
        try { el.setSelectionRange(this._focus.start, this._focus.end); } catch (e) { /* number inputs */ }
      }
    }
  }

  mount() {
    document.addEventListener('click', (e) => {
      const actEl = e.target.closest('[data-act]');
      if (!actEl) return;
      if (actEl.hasAttribute('data-bg')) {
        const stop = e.target.closest('[data-stop]');
        if (stop && actEl.contains(stop)) return;
      }
      const fn = this._acts[+actEl.dataset.act];
      if (fn) fn(e);
    });
    document.addEventListener('input', (e) => {
      const el = e.target.closest('[data-inp]');
      if (!el) return;
      const fn = this._inps[+el.dataset.inp];
      if (fn) fn(e);
    });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') this.setState({ searchOpen: false, detail: null });
      else if (e.key === '/' && !this.state.searchOpen && !/INPUT|TEXTAREA/.test(document.activeElement.tagName)) {
        e.preventDefault();
        this.setState({ searchOpen: true });
      }
    });
    // Back/forward: re-read the hash so the visible page follows the address.
    window.addEventListener('hashchange', () => {
      const segmente = (location.hash || '#overview').replace('#', '').split('/');
      if (segmente[0] === 'research') {
        const i = this.studienIndexAus(segmente[1]);
        this._pendingAnchor = segmente[2] ? segmente.join('/') : null;
        this.setState({ page: 'research', researchTab: i >= 0 ? i : this.state.researchTab, detail: null });
        this.fetchPageData('research');
      } else if (segmente[0] in PAGES && segmente[0] !== this.state.page) {
        this.setState({ page: segmente[0], detail: null });
        this.fetchPageData(segmente[0]);
      }
    });
    // Die Uhr rendert nur die Kopfzeile neu: ein voller Render alle 15 s
    // schloss jedes geoeffnete <details> und warf die Scrollposition zurueck.
    setInterval(() => {
      this.state.clock = this.utcClock();
      const tb = document.getElementById('topbar');
      if (tb) tb.innerHTML = this.renderTopbar();
    }, 15000);
    this.render();
    this.pollLive();
    setInterval(() => this.pollLive(), 30000);
    this.ladeLanding();
    this.fetchPageData(this.state.page);
  }
}

const T = new Terminal();
T.mount();
export default T;
