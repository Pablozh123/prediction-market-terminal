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

const PAGES = {
  overview: renderOverview, markets: renderMarkets, flow: renderFlow,
  cross: renderCross, resolved: renderResolved,
  traders: renderTraders, whale: renderWhale, risk: renderRisk, track: renderTrack,
  backtester: renderBacktester, copy: renderCopy, portfolio: renderPortfolio,
  alerts: renderAlerts, research: renderResearch, settings: renderSettings
};

class Terminal {
  constructor() {
    this.state = {
      // Nur das erste Segment bestimmt die Seite; das zweite waehlt weiter
      // unten die Studie aus, sobald die Studienliste steht.
      page: (location.hash || '').replace('#', '').split('/')[0] in PAGES
        ? (location.hash || '').replace('#', '').split('/')[0] : 'overview',
      tapeMin: 2500,
      tapeTracked: false,
      marketCat: 'All',
      marketFiltersOpen: false,
      mPlatform: 'all', mStatus: 'active', mProb: 'all', mSpread: 'all', mLiq: 'all', mVol: 'all', mEnds: 'all', mAge: 'all',
      mExclude: [], mView: 'table', mQuick: 'trending',
      crossQuery: '', crossSim: 0.30, crossMaxPairs: 50, crossMinGap: 0, crossLower: 'any',
      crossPmVol: 0, crossKsVol: 0, crossMinPrice: 0, crossMaxPrice: 100,
      marketSort: 'volume',
      marketQuery: '',
      traderRank: 'pnl',
      traderQuery: '', traderView: 'table', traderCols: 'default', traderPeriod: 'ALL',
      traderActiveOnly: false, traderBotsOnly: false, traderFiltersOpen: false,
      tPnl: 'all', tVol: 'all', tPos: 'all', tTraits: [], tWin: 'all', tClosed: 'all', tBal: 'all', tAge: 'all', tAssets: 'all', tBotScore: 65,
      tEnrich: { positions: true, winrates: true, accounts: false },
      riskView: 'events', riskAgeCheck: false,
      copyTab: 'orders', copyQuery: '', copySide: 'all', copyStatus2: 'all', copyMin: 'all', daemonOn: true,
      portTab: 'positions', portQuery: '', portSource: 'all', portSide: 'all', portLosers: false,
      tapeQuery: '', tapePlatform: 'all', tapeSide: 'all', tapeOutcome: 'all',
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
      advancedOpen: false,
      sizingSimOpen: false,
      researchTab: 0,
      liveTab: 'runs',
      alertsOn: { movers: true, volume: true, whales: true, spreads: false, holders: false, endings: true },
      settingsOn: { telegram: true, autotop: false, kalshi: true, sports: false, cache: true, admin: true },
      clock: this.utcClock(),
      live: 'demo', liveAsOf: ''
    };

    // Datencontainer. Sie starten leer, nicht auf einem Demo-Satz: bis eine
    // Antwort da ist, gibt es nichts zu zeigen. Frueher standen hier zwoelf
    // erfundene Maerkte, acht erfundene Wallets und ein erfundener Tape, und
    // jede Seite rechnete ihre Kennzahlen daraus aus.
    this.markets = [];
    this.marketExtra = {};
    this.traders = [];
    this.traderExtra = {};
    this.risks = [];
    this.tape = [];
    this.crossPairs = [];
    this.studies = STUDIEN;
    // Herkunft je Container: null heisst noch keine Antwort, sonst
    // { quelle: 'live' | 'leer' | 'fehler', fehler }. Eine leere Antwort und
    // eine ausgebliebene Antwort sagen Verschiedenes, und beides ist etwas
    // anderes als eine Zeile, die jemand hingeschrieben hat.
    this.herkunft = { markets: null, tape: null, traders: null, risks: null, cross: null };
    // Zweites Adresssegment aufloesen: #research/microstructure soll die
    // Studie oeffnen, nicht die erste in der Liste.
    const segmente = (location.hash || '').replace('#', '').split('/');
    if (segmente[0] === 'research' && segmente[1]) {
      const treffer = this.studienIndexAus(segmente[1]);
      if (treffer >= 0) {
        this.state.page = 'research';
        this.state.researchTab = treffer;
      }
    }
    // Per-endpoint live payloads; templates use these when present, demo otherwise.
    this.liveData = { leaderboard: null, cross: null, risk: null, alerts: null, copy: null, portfolio: null, research: {}, backtest: null, walletDetail: {} };

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
      sparkPoints: spark(m.spark),
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
    } catch (err) { /* Detail behaelt die synthetische Kurve */ }
  }
  openWallet(name) {
    this.setState({ detail: { kind: 'wallet', id: name }, searchOpen: false });
    this.fetchWalletDetail(name);
  }

  marketExtraOf(m) { return this.marketExtra[m.id] || { spread: 5, age: 100, endsDays: 30, saved: false, pos: false }; }
  traderExtraOf(t) { return this.traderExtra[t.name] || { positions: 0, assets: 0, balance: 0, ageDays: 100, traits: [], bot: 20, active: 10 }; }

  tapeFiltered() {
    const s = this.state;
    return this.tape.filter((t) => {
      if (t.size < s.tapeMin) return false;
      if (s.tapeTracked && !t.tracked) return false;
      if (s.tapePlatform !== 'all' && t.venue !== s.tapePlatform) return false;
      if (s.tapeSide !== 'all' && t.side.indexOf(s.tapeSide) !== 0) return false;
      if (s.tapeOutcome !== 'all' && t.side.indexOf(s.tapeOutcome) < 0) return false;
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
      size: money(t.size), venue: t.venue,
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

  navStudy(i, label) {
    const active = this.state.page === 'research' && this.state.researchTab === i;
    const style = 'display:flex; align-items:center; justify-content:space-between; gap:8px; padding:6px 10px; border-radius:7px; cursor:pointer; margin-bottom:2px; border-left:2px solid ' + (active ? '#4F8EF7' : 'transparent') + '; background:' + (active ? 'rgba(79,142,247,.12)' : 'transparent');
    const labelStyle = 'font-size:13px; color:' + (active ? '#ffffff' : 'rgba(255,255,255,.55)') + '; font-weight:' + (active ? '600' : '400');
    return '<div ' + this.act(() => {
      this.setState({ page: 'research', researchTab: i, detail: null });
      // Eigene Adresse je Studie: eine Bewerbung wird als Link verschickt, und
      // ein Verweis auf #research landete bisher immer auf der Review queue.
      try { history.pushState(null, '', '#research/' + this.studienSlug(i)); } catch (e) { /* file:// */ }
      this.fetchPageData('research');
    }) + ' class="hv-el" style="' + style + '">'
      + '<span style="' + labelStyle + '">' + esc(label) + '</span></div>';
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
    const groups = [
      { label: 'DASHBOARD', items: [this.navItem('overview', 'Overview')] },
      // Kein Zaehler ohne Daten: eine 0 im Abzeichen liest sich als Messung,
      // solange gar nichts geladen ist.
      { label: 'MARKETS', items: [this.navItem('markets', 'Markets'), this.navItem('flow', 'Live tape', this.tape.length ? String(this.tape.length) : ''), this.navItem('cross', 'Cross-venue'), this.navItem('resolved', 'Resolved')] },
      { label: 'TRADERS', items: [this.navItem('traders', 'Leaderboard'), this.navItem('whale', 'Whale flow'), this.navItem('risk', 'Risk screen', hoheRisiken ? String(hoheRisiken) : '', 'amber'), this.navItem('track', 'Tracked')] },
      { label: 'TRADING', items: [this.navItem('copy', 'Copy trade'), this.navItem('backtester', 'Backtester'), this.navItem('portfolio', 'Portfolio')] },
      { label: 'SYSTEM', items: [this.navItem('alerts', 'Alerts'), this.navItem('settings', 'Settings')] },
      { label: 'RESEARCH', items: this.studies.map((st, i) => this.navStudy(i, st.tab)) }
    ];
    const groupHtml = groups.map((g) =>
      '<div style="margin-bottom:14px">'
      + '<div style="font-family:\'JetBrains Mono\',monospace; font-size:10px; letter-spacing:.18em; padding:0 6px 6px; color:rgba(255,255,255,.35)">' + g.label + '</div>'
      + g.items.join('') + '</div>'
    ).join('');
    // Der Kasten zeigt nur eine Summe, wenn der Papierstand gemeldet wurde.
    // Stand und Gewinn waren hier fest verdrahtet — derselbe erfundene
    // Kontostand, der auf der Copy-Seite schon geloescht wurde, nur eine
    // Ebene hoeher und auf jeder Seite sichtbar.
    const copyLive = this.liveData.copy;
    const equity = copyLive && copyLive.equity != null ? copyLive.equity : null;
    const pnl = copyLive && copyLive.pnl != null ? copyLive.pnl : null;
    const pnlPct = copyLive && copyLive.pnl_pct != null ? copyLive.pnl_pct : null;
    const equityBlock = equity == null
      ? '<div style="font-family:\'JetBrains Mono\',monospace; font-size:12px; color:rgba(255,255,255,.45); margin-top:5px; line-height:1.5">No paper account reported by /api/copy.</div>'
      : '<div style="font-family:\'JetBrains Mono\',monospace; font-size:19px; margin-top:5px">$' + num(equity.toFixed(2)) + '</div>'
        + (pnl == null ? '' : '<div style="font-family:\'JetBrains Mono\',monospace; font-size:12px; color:' + (pnl >= 0 ? '#C8F542' : '#FF4545') + '">'
          + (pnl >= 0 ? '+' : '-') + '$' + Math.abs(pnl).toFixed(2)
          + (pnlPct == null ? '' : ' · ' + (pnlPct >= 0 ? '+' : '') + pnlPct.toFixed(1) + '%') + '</div>');
    return ''
      + '<div style="display:flex; align-items:center; gap:9px; padding:0 6px 18px">'
      + '<div style="width:10px; height:10px; background:#C8F542; transform:rotate(45deg)"></div>'
      + '<div style="font-family:\'Instrument Serif\',serif; font-size:21px">Market Intel</div></div>'
      + '<div ' + this.act(() => this.setState({ searchOpen: true })) + ' class="hv-bd22" style="display:flex; align-items:center; gap:8px; background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:8px; padding:9px 10px; cursor:pointer; margin-bottom:18px">'
      + '<div style="font-family:\'JetBrains Mono\',monospace; font-size:12px; color:rgba(255,255,255,.45); flex:1">Search</div>'
      + '<div style="font-family:\'JetBrains Mono\',monospace; font-size:11px; color:rgba(255,255,255,.35); border:1px solid rgba(255,255,255,.16); border-radius:4px; padding:0 5px">/</div></div>'
      + groupHtml
      + '<div style="margin-top:auto; padding-top:16px">'
      + '<div style="border:1px solid rgba(255,255,255,.09); border-radius:10px; padding:11px 13px; background:#10151A">'
      + '<div style="font-family:\'JetBrains Mono\',monospace; font-size:9.5px; letter-spacing:.14em; color:rgba(255,255,255,.45)">PAPER EQUITY</div>'
      + equityBlock + '</div>'
      + '<div style="font-family:\'JetBrains Mono\',monospace; font-size:9.5px; line-height:1.6; color:rgba(255,255,255,.35); margin-top:12px">Research only. No orders placed. Public Polymarket &amp; Kalshi data.</div></div>';
  }

  renderTopbar() {
    const s = this.state;
    const liveDot = s.live === 'live' ? '#C8F542' : s.live === 'error' ? '#FF4545' : '#F5A623';
    const liveLabel = s.live === 'live' ? 'LIVE · POLYMARKET + KALSHI' : s.live === 'error' ? 'API GETRENNT · LETZTER STAND' : 'DEMO-DATEN · API OFFLINE';
    return ''
      + '<div style="display:flex; align-items:center; gap:10px">'
      + '<span style="width:7px; height:7px; border-radius:50%; background:' + liveDot + '; display:inline-block; animation:livePulse 1.6s ease-in-out infinite"></span>'
      + '<span style="font-family:\'JetBrains Mono\',monospace; font-size:11px; letter-spacing:.16em; color:rgba(255,255,255,.66)">' + liveLabel + ' · ' + s.clock + ' UTC</span></div>'
      + '<div style="display:flex; gap:8px">'
      + '<div class="hv-bd30" style="font-size:12.5px; color:rgba(255,255,255,.66); border:1px solid rgba(255,255,255,.16); border-radius:7px; padding:7px 13px; cursor:pointer">Sign in</div>'
      + '<div class="hv-limebg" style="font-size:12.5px; font-weight:600; color:#0A0D0F; background:#C8F542; border-radius:7px; padding:7px 13px; cursor:pointer">Get alerts</div></div>';
  }

  // ---- data layer ----
  async pollLive() {
    try {
      const [mk, tp] = await Promise.all([
        apiGet('/api/markets?limit=250'),
        apiGet('/api/tape?limit=250')
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
      this.setState({ live: 'live', liveAsOf: String(mk.as_of || '') });
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
      await this.holen('cross', '/api/cross', (cr) => {
        this.crossPairs = cr.rows || [];
        // Reale Paare liegen oft unter der Voreinstellung 0.30 — Slider einmalig anpassen.
        if (this.crossPairs.length && !this.crossPairs.some((r) => r.sim >= this.state.crossSim)) {
          const best = Math.max.apply(null, this.crossPairs.map((r) => r.sim));
          this.state.crossSim = Math.max(0.1, Math.floor(best * 50) / 50);
        }
      });
      this.herkunft.cross = this.herkunftAus('cross', this.crossPairs);
    } else if (page === 'risk') {
      // Bewusst nicht mehr von der Startseite: der erste Aufbau paged einen Tag
      // Prints und schlaegt Marktkategorien nach, das blockierte die Overview.
      await this.holen('risk', '/api/risk', (rk) => {
        this.risks = rk.events || [];
      });
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
      scoreN: r.score_n != null ? +r.score_n : null,
      scoreCi: r.score_ci || null,
      sampleBadge: r.sample_badge || null,
      tags: String(r.tags || '')
    }));
    this.traderExtra = {};
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

  runBacktestLive() {
    const s = this.state;
    clearTimeout(this._btT);
    this._btT = setTimeout(async () => {
      try {
        const resp = await apiPost('/api/backtest', {
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
        });
        if (resp && resp.stats) { this.liveData.backtest = resp; this.render(); }
      } catch (err) { this.liveData.backtest = null; }
    }, 450);
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

    document.getElementById('sidebar').innerHTML = this.renderSidebar();
    document.getElementById('topbar').innerHTML = this.renderTopbar();
    const pageFn = PAGES[this.state.page] || renderOverview;
    document.getElementById('main').innerHTML = pageFn(this);
    document.getElementById('detail').innerHTML = renderDetail(this);
    document.getElementById('search').innerHTML = renderSearch(this);

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
    setInterval(() => this.setState({ clock: this.utcClock() }), 15000);
    this.render();
    this.pollLive();
    setInterval(() => this.pollLive(), 30000);
    this.fetchPageData(this.state.page);
  }
}

const T = new Terminal();
T.mount();
export default T;
