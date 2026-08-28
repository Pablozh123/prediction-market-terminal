// Market Intel terminal — vanilla JS port of the design reference.
// One controller class; each workspace renders as an HTML string from state.

import { num, money, volume, esc, seriesPoints, tapeMatches, liveStatusLabel } from './util.js';
import { STUDIEN } from './studies.js';
import { caveatZeile, registerAktualisieren } from './claims.js';
import { apiGet, apiGetRaw, apiPost } from './api.js';
import { renderOverview, renderMarkets, renderFlow, renderCross, renderResolved } from './pages/core_pages.js';
import { renderTraders, renderWhale, renderRisk, renderTrack } from './pages/trader_pages.js';
import { renderBacktester, renderCopy, renderPortfolio } from './pages/trading_pages.js';
import { renderAlerts, renderResearch, renderSettings, ledgerVerwerfen } from './pages/system_pages.js';
import { renderWallet, isFullAddress } from './pages/wallet_page.js';
import { renderDetail, renderSearch } from './overlays.js';
import { mountAmbient } from './ambient.js';
import { MONO as M } from './ui.js';

// Every route stays reachable by hash. The sidebar lists a subset (see
// renderSidebar): Settings, Tracked, Copy trade, Portfolio and Resolved are
// reachable but not advertised — they describe a local paper setup that the
// public host does not run.
const PAGES = {
  overview: renderOverview, markets: renderMarkets, flow: renderFlow,
  cross: renderCross, resolved: renderResolved,
  traders: renderTraders, whale: renderWhale, risk: renderRisk, track: renderTrack,
  wallet: renderWallet,
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

// Sub-tabs that belong in the address, so a link can point at a tab and the
// address always says which one is open: #risk/log, #alerts/rules,
// #research/live-runs/timing. The default tab carries no segment.
const SUB_TABS = {
  risk: { key: 'riskView', standard: 'events', werte: ['events', 'wallets', 'fresh', 'timing', 'network', 'log'] },
  alerts: { key: 'alertTab', standard: 'signals', werte: ['signals', 'rules', 'deliveries'] }
};
const LIVE_RUNS_TABS = { key: 'liveTab', standard: 'runs', werte: ['runs', 'timing', 'sim', 'calib', 'record'] };
const ADRESS_SCHLUESSEL = ['riskView', 'alertTab', 'liveTab'];

class Terminal {
  constructor() {
    this.state = {
      // Set on <html> by the head script before first paint.
      theme: document.documentElement.dataset.theme === 'light' ? 'light' : 'dark',
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
      // Kein riskAgeCheck mehr: der Schalter "Check real account ages" stand
      // ohne Endpunkt dahinter — /api/risk kennt keinen solchen Parameter.
      riskView: 'events',
      // Kein daemonOn mehr: der Schalter im Frontend behauptete RUNNING, ohne
      // dass etwas lief. Der Zustand kommt aus /api/copy oder gar nicht.
      copyTab: 'traders', copyQuery: '', copySide: 'all', copyStatus2: 'all', copyMin: 'all',
      // Copy desk: trader filter for the order/position/cash/perf tabs, the
      // follow form, inline edit/top-up rows, the pending settings edit
      // (null = showing what is saved), the in-flight action, the last
      // outcome line, and the admin token (kept in localStorage, sent as
      // X-Admin-Token when the server asks for one).
      copyTrader: 'all',
      copyForm: { wallet: '', label: '', cash: '1000', note: '' },
      copyEdit: null, copyTopup: null, copySettings: null,
      copyBusy: '', copyMsg: null,
      copyToken: (() => { try { return localStorage.getItem('copyAdminToken') || ''; } catch (e) { return ''; } })(),
      portTab: 'positions', portQuery: '', portSource: 'all', portSide: 'all', portLosers: false,
      tapeQuery: '', tapePlatform: 'all', tapeSide: 'all', tapeOutcome: 'all',
      // Whale flow: Sortierung der Wallet-Zeilen — 'total' | 'biggest' | 'prints'.
      whaleSort: 'total',
      resQuery: '', resAnswer: 'all', resWindow: 'all', resError: 'all', resSort: 'recent',
      setMarketSample: 250, setTradeSample: 250, setWhale: 2500, setBankroll: 1000, setFee: 20, setSlip: 15,
      alertTab: 'signals', alertQuery: '', alertPlatform: 'all', alertType: 'all', alertScope: 'all',
      thMove: 5, thSpread: 3, thWhale: 2500, thEnding: 72, thHolder: 40,
      riskFilter: 'all', riskOpen: {},
      detail: null,
      searchOpen: false,
      searchQuery: '',
      btStrategy: 'copy',
      btWindow: 30,
      // Default wallet for the backtester: a public Polymarket address with a
      // long trade history, so the first run returns something to look at.
      btWallet: '0x204f72f35326db932158cba6adff0b9a1da95e14',
      btSizing: 'fixed',
      // Auto-Fit an: die Engine misst, wie viele Positionen die Wallet
      // hoechstens zugleich offen hat, und passt den Einsatz je Copy so an,
      // dass Bankroll und Exposure-Deckel dem Tempo folgen koennen. Was
      // angewendet wurde, steht im Ergebnis; abschaltbar neben dem Einsatz.
      btAutoFit: true,
      // Manuelle Folge-Schwelle (nur bei Auto-Fit aus): Quell-Trades unter
      // diesem Notional werden nicht kopiert, sondern als "filtered" gefuehrt.
      btMinNotional: 0,
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
      // Wallet page: the address being analysed (from #wallet/<addr> or the
      // input), the raw input, the addresses analysed this session (not
      // persisted), and the sort of the open-positions table.
      walletAddr: '', walletInput: '', walletRecent: [], walletPosSort: 'value', walletTab: 'overview', walletTreemap: 'all', walletPosView: 'bars', walletSimilarQuery: '',
      alertsOn: { movers: true, volume: true, whales: true, spreads: false, holders: false, endings: true },
      settingsOn: { telegram: true, autotop: false, kalshi: true, sports: false, cache: true, admin: true },
      clock: this.utcClock(),
      // 'waiting' bis zur ersten Antwort, dann 'live' oder 'error'; 'offline'
      // wenn die erste Antwort ausblieb (reiner Dateihost, API schlaeft). Der
      // fruehere Wert 'demo' behauptete einen Demo-Datensatz, den es nicht gibt.
      // Venues, die auf die letzte Runde nicht lesbar geantwortet haben. Die
      // Kopfzeile sagte "LIVE, POLYMARKET + KALSHI", egal was zurueckkam; ein
      // Ausfall auf einer Venue war von einer stillen Venue nicht zu
      // unterscheiden. /api/tape und /api/markets fuehren das jetzt mit.
      // Dasselbe eine Ebene tiefer: ob die Kategorie eines Prints aus dem
      // Marktuniversum kam oder nur aus seinem Titel. Ohne das Universum
      // stimmt die Kategorieleiste des Tapes nicht mehr, ohne leer zu sein.
      live: 'waiting', liveAsOf: '', tapeAsOf: '', venuesMissing: [], tapeCategories: {}
    };
    // Sub-tab from the address (#risk/log, #alerts/rules), if it names one.
    const startSegmente = (location.hash || '').replace('#', '').split('/');
    this.tabAusAdresse(startSegmente);

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
    this.landing = { micro: null, runs: null, notes: null, ledger: null, herkunft: { micro: null, runs: null, notes: null, ledger: null } };
    // Zweites Adresssegment aufloesen: #research/microstructure soll die
    // Studie oeffnen, nicht die erste in der Liste.
    const segmente = (location.hash || '').replace('#', '').split('/');
    if (segmente[0] === 'research' && segmente[1]) {
      const treffer = this.studienIndexAus(segmente[1]);
      if (treffer >= 0) {
        this.state.page = 'research';
        this.state.researchTab = treffer;
        // Drittes Segment = Karte auf der Seite (#research/microstructure/<id>)
        // oder der Reiter der Live runs (#research/live-runs/timing).
        this._pendingAnchor = segmente[2] && !this.tabAusAdresse(segmente) ? segmente.join('/') : null;
      }
    }
    // Deep link #wallet/<address>: the page opens on that wallet and fetches
    // it on mount (fetchPageData). A malformed address opens the empty page
    // with the text in the input, so the reader sees what did not parse.
    if (segmente[0] === 'wallet' && segmente[1]) {
      const kandidat = decodeURIComponent(segmente[1]).trim();
      this.state.walletInput = kandidat;
      if (isFullAddress(kandidat)) {
        this.state.walletAddr = kandidat.toLowerCase();
        this.state.walletRecent = [kandidat.toLowerCase()];
      }
    }
    // Per-endpoint live payloads; templates use these when present and show
    // an empty state naming the source otherwise.
    // riskLog: the flag log of the risk screen (/api/risk/log), fetched only
    // when its tab is opened — null until then.
    // wallet: one entry per analysed address — { herkunft: 'loading' | 'live'
    // | 'fehler', data, fehler, status, retryAfter }.
    this.liveData = { leaderboard: null, cross: null, risk: null, riskLog: null, alerts: null, copy: null, portfolio: null, research: {}, backtest: null, walletDetail: {}, wallet: {}, riskBook: {}, walletSimilar: {} };
    // Venue-weite Suche (/api/search): die Palette filtert sonst nur die
    // geladenen Top-Volumen-Maerkte — alles ausserhalb davon fand sie nie.
    // q traegt die Anfrage, zu der die Treffer gehoeren; status ist
    // 'idle' | 'laedt' | 'ok' | 'fehler'.
    this.searchRemote = { q: '', markets: [], wallets: [], status: 'idle', fehler: '' };
    this._suchTimer = null;

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
  seriesPoints(v, w, h) { return seriesPoints(v, w, h); }

  // ---- action / input registries (rebuilt every render) ----
  // Every registered action is a control, so it renders as one: focusable and
  // announced. Two opt-outs, both for containers rather than controls —
  // opts.plain for a click-to-close backdrop (a full-viewport layer is not a
  // tab stop), opts.role === null for a card that already holds a link or a
  // nested action (a button inside a button announces as neither).
  act(fn, opts) {
    this._acts.push(fn);
    const attr = 'data-act="' + (this._acts.length - 1) + '"';
    if (opts && opts.plain) return attr;
    const rolle = opts && 'role' in opts ? opts.role : 'button';
    return attr + (rolle ? ' role="' + rolle + '"' : '') + ' tabindex="0"';
  }
  inp(fn, key) { this._inps.push(fn); return 'data-inp="' + (this._inps.length - 1) + '" data-key="' + key + '"'; }

  setState(patch) {
    Object.assign(this.state, patch);
    this.render();
    // A sub-tab click rewrites the address in place (no history entry: the
    // back button leaves the page, it does not walk through its tabs).
    if (patch && ADRESS_SCHLUESSEL.some((k) => Object.prototype.hasOwnProperty.call(patch, k))) this.adresseAngleichen();
  }

  // The address the current page and sub-tab should carry, without the '#'.
  // null for research studies without tabs: their address is set by
  // goStudy() and may carry a card anchor that must survive re-renders.
  adresseSoll() {
    const s = this.state;
    if (s.page === 'research') {
      const slug = this.studienSlug(s.researchTab);
      if (slug !== 'live-runs') return null;
      return 'research/live-runs' + (s.liveTab !== LIVE_RUNS_TABS.standard && LIVE_RUNS_TABS.werte.indexOf(s.liveTab) >= 0 ? '/' + s.liveTab : '');
    }
    // The wallet page keeps its address in the hash so the link stays a deep link.
    if (s.page === 'wallet') return 'wallet' + (s.walletAddr ? '/' + s.walletAddr : '');
    const t = SUB_TABS[s.page];
    return s.page + (t && s[t.key] !== t.standard && t.werte.indexOf(s[t.key]) >= 0 ? '/' + s[t.key] : '');
  }

  adresseAngleichen() {
    const soll = this.adresseSoll();
    if (soll === null || (location.hash || '').replace('#', '') === soll) return;
    try { history.replaceState(null, '', '#' + soll); } catch (e) { /* file:// */ }
  }

  // Read a sub-tab out of the address segments into state; without a segment
  // the page opens on its default tab, so the address and the page agree.
  // Returns true when a segment named a tab (the caller then does not treat
  // it as a card anchor).
  tabAusAdresse(segmente) {
    if (!segmente || !segmente.length) return false;
    let t = SUB_TABS[segmente[0]];
    let wert = segmente[1];
    if (segmente[0] === 'research') {
      if (segmente[1] !== 'live-runs') return false;
      t = LIVE_RUNS_TABS;
      wert = segmente[2];
    }
    if (!t) return false;
    const gueltig = !!wert && t.werte.indexOf(wert) >= 0;
    this.state[t.key] = gueltig ? wert : t.standard;
    return gueltig;
  }

  // ---- shared UI atoms (styles verbatim from the reference) ----
  opt(label, active, patch) {
    const style = "font-family:var(--font-mono); font-size:var(--t-micro); border-radius:var(--r-control); padding:5px 9px; cursor:pointer; " + (active ? 'color:var(--on-accent); background:var(--accent); font-weight:600' : 'color:var(--ink-4); border:1px solid var(--line-1)');
    return '<div ' + this.act(typeof patch === 'function' ? patch : () => this.setState(patch))
      + ' aria-pressed="' + (active ? 'true' : 'false') + '" style="' + style + '">' + esc(label) + '</div>';
  }

  chip(label, active, patch) {
    const style = "font-family:var(--font-mono); font-size:var(--t-micro); letter-spacing:.06em; border-radius:var(--r-control); padding:5px 10px; cursor:pointer; " + (active ? 'color:var(--on-accent); background:var(--accent); font-weight:600' : 'color:var(--ink-4); border:1px solid var(--line-1)');
    return '<div ' + this.act(typeof patch === 'function' ? patch : () => this.setState(patch))
      + ' aria-pressed="' + (active ? 'true' : 'false') + '" style="' + style + '">' + esc(label) + '</div>';
  }

  tab(label, active, patch) {
    const style = 'font-size:var(--t-small); border-radius:var(--r-control); padding:7px 13px; cursor:pointer; ' + (active ? 'color:var(--on-accent); background:var(--accent); font-weight:600' : 'color:var(--ink-3); border:1px solid var(--line-1)');
    return '<div ' + this.act(typeof patch === 'function' ? patch : () => this.setState(patch))
      + ' aria-pressed="' + (active ? 'true' : 'false') + '" style="' + style + '">' + esc(label) + '</div>';
  }

  toggle(on, patch, label, gesperrt) {
    const wrap = 'width:34px; height:19px; flex:none; border-radius:var(--r-panel); padding:2px; display:flex; cursor:' + (gesperrt ? 'default' : 'pointer') + '; opacity:' + (gesperrt ? '.45' : '1') + '; background:' + (on ? 'var(--accent)' : 'rgba(var(--ink),.14)') + '; justify-content:' + (on ? 'flex-end' : 'flex-start');
    const knob = 'width:15px; height:15px; border-radius:50%; background:' + (on ? 'var(--on-accent)' : 'var(--ink-4)');
    // A switch, not a button: act() gives up its role so this one stands, and
    // the caller passes the label that sits above the control on screen.
    return '<div ' + this.act(typeof patch === 'function' ? patch : () => this.setState(patch), { role: null })
      + ' role="switch" aria-checked="' + (on ? 'true' : 'false') + '"'
      + (gesperrt ? ' aria-disabled="true"' : '')
      + (label ? ' aria-label="' + esc(label) + '"' : '')
      + ' style="' + wrap + '"><div style="' + knob + '"></div></div>';
  }

  stepper(valueLabel, onDown, onUp, size) {
    const s = size === 'lg';
    const btn = 'width:' + (s ? 32 : 28) + 'px; height:' + (s ? 34 : 32) + 'px; flex:none; border:1px solid var(--line-1); border-radius:' + (s ? 8 : 7) + 'px; display:flex; align-items:center; justify-content:center; font-family:var(--font-mono); font-size:' + (s ? 15 : 14) + 'px; color:var(--ink-2); cursor:pointer';
    const val = 'flex:1; background:var(--panel); border:1px solid var(--line-1); border-radius:' + (s ? 8 : 7) + 'px; padding:' + (s ? '8px 12px' : '7px 8px') + '; font-family:var(--font-mono); font-size:' + (s ? 13 : 12.5) + 'px; text-align:center';
    return '<div style="display:flex; align-items:center; gap:' + (s ? 8 : 6) + 'px">'
      + '<div ' + this.act(onDown) + ' class="hv-edge-max hv-white" style="' + btn + '">−</div>'
      + '<div style="' + val + '">' + esc(valueLabel) + '</div>'
      + '<div ' + this.act(onUp) + ' class="hv-edge-max hv-white" style="' + btn + '">+</div></div>';
  }

  changeStyle(chg) {
    return "font-family:var(--font-mono); font-size:var(--t-body); text-align:right; color:" + (chg >= 0 ? 'var(--pos)' : 'var(--neg)');
  }

  marketView(m) {
    return {
      title: m.title,
      meta: m.venue.toUpperCase() + ' · ' + m.cat.toUpperCase(),
      color: m.chg >= 0 ? 'var(--pos)' : 'var(--neg)',
      priceLabel: m.yes + '¢',
      changeLabel: (m.chg >= 0 ? '+' : '') + m.chg + '¢',
      changeStyle: this.changeStyle(m.chg),
      // Polymarket meldet Dollar, Kalshi Kontrakte. money() hat beides
      // mit einem Dollarzeichen versehen (app/venue_units.py).
      volLabel: volume(m.vol, m.venue),
      ends: m.ends,
      act: this.act(() => this.openMarket(m.id))
    };
  }

  openMarket(id) {
    this.setState({ detail: { kind: 'market', id }, searchOpen: false });
    this.fetchMarketHistory(id);
  }

  // Ein Suchtreffer von /api/search, der nicht im geladenen Universum steht:
  // erst einreihen (das Detail-Overlay liest aus this.markets), dann oeffnen.
  openRemoteMarket(m) {
    if (!this.markets.find((x) => x.id === m.id)) {
      this.markets.push(m);
      this.marketExtra[m.id] = m._extra;
    }
    this.setState({ detail: { kind: 'market', id: m.id }, searchOpen: false, searchQuery: '' });
    this.fetchMarketHistory(m.id);
  }

  // Venue-weite Suche, entprellt. Die lokale Filterung der Palette bleibt
  // sofort sichtbar; die Treffer aus /api/search kommen nach, sobald die
  // Antwort da ist, und nur wenn die Anfrage noch die aktuelle ist.
  sucheRemote(roh) {
    const q = String(roh || '').trim();
    clearTimeout(this._suchTimer);
    // Adressen sind eine Aktion, keine Suche; unter zwei Zeichen antwortet
    // der Endpunkt ohnehin leer.
    if (q.length < 2 || /^0x[0-9a-fA-F]*$/.test(q)) {
      this.searchRemote = { q: '', markets: [], wallets: [], status: 'idle', fehler: '' };
      return;
    }
    this._suchTimer = setTimeout(() => { this.sucheRemoteJetzt(q); }, 250);
  }

  async sucheRemoteJetzt(q) {
    this.searchRemote = { q, markets: [], wallets: [], status: 'laedt', fehler: '' };
    this.render();
    try {
      const r = await apiGet('/api/search?q=' + encodeURIComponent(q) + '&limit=12');
      if (this.state.searchQuery.trim() !== q) return;
      const { mapMarket } = await import('./util.js');
      this.searchRemote = {
        q,
        markets: (r.markets || []).map((row, i) => mapMarket(row, i)),
        wallets: r.wallets || [],
        status: 'ok',
        fehler: ''
      };
    } catch (err) {
      if (this.state.searchQuery.trim() !== q) return;
      this.searchRemote = { q, markets: [], wallets: [], status: 'fehler', fehler: String(err && err.message ? err.message : err) };
    }
    this.render();
  }

  async fetchMarketHistory(id) {
    if (this.state.live !== 'live' || this.liveData.marketHistory && this.liveData.marketHistory[id]) return;
    this.liveData.marketHistory = this.liveData.marketHistory || {};
    try {
      const h = await apiGet('/api/market/' + encodeURIComponent(id) + '/history?days=1&interval=5m');
      if (h && h.points && h.points.length > 1) { this.liveData.marketHistory[id] = h.points; this.render(); }
    } catch (err) { /* Detail zeigt den Leerzustand ohne Kurve */ }
  }
  // A wallet drawer for a leaderboard name or, from Whale flow and the risk
  // screen, for a wallet the leaderboard does not list. ``addr`` is optional:
  // the leaderboard rows resolve it from their name, whale/risk rows pass it
  // in so a wallet outside the leaderboard still gets its detail (/api/wallet
  // can be asked) and its "Full analysis" link; without an address the drawer
  // shows the prints of that wallet in the tape window and says what it
  // cannot show.
  openWallet(name, addr) {
    const full = addr && isFullAddress(addr) ? String(addr).trim().toLowerCase() : '';
    this.setState({ detail: { kind: 'wallet', id: name, addr: full }, searchOpen: false });
    this.fetchWalletDetail(name, full);
  }

  // The wallet page for one address: sets the route, remembers the address
  // for this session and fetches unless an answer is already there. Not
  // gated on the poll state — the API answers or the page says it did not.
  analyseWallet(addr) {
    const full = String(addr || '').trim();
    if (!isFullAddress(full)) {
      this.setState({ page: 'wallet', walletInput: full, detail: null, searchOpen: false, searchQuery: '' });
      this.adresseSetzen('wallet');
      return;
    }
    const key = full.toLowerCase();
    const recent = [key].concat((this.state.walletRecent || []).filter((a) => a !== key)).slice(0, 8);
    this.setState({ page: 'wallet', walletAddr: key, walletInput: full, walletRecent: recent, detail: null, searchOpen: false, searchQuery: '' });
    // The address is the deep link (#wallet/<addr>); adresseSetzen adds no
    // second history entry when the page already sits on it.
    this.adresseSetzen('wallet/' + key);
    this.fetchWallet(key, false);
  }

  async fetchWallet(addr, force) {
    const key = String(addr || '').toLowerCase();
    if (!isFullAddress(key)) return;
    const vorhanden = this.liveData.wallet[key];
    if (vorhanden && !force && vorhanden.herkunft !== 'fehler') return;
    this.liveData.wallet[key] = { herkunft: 'loading' };
    this.render();
    try {
      const antwort = await apiGet('/api/wallet/' + key);
      this.liveData.wallet[key] = antwort && typeof antwort === 'object'
        ? { herkunft: 'live', data: antwort }
        : { herkunft: 'live', data: null };
    } catch (err) {
      this.liveData.wallet[key] = {
        herkunft: 'fehler',
        fehler: String(err && err.message ? err.message : err),
        status: err && err.status ? err.status : null,
        retryAfter: err && err.retryAfter ? err.retryAfter : null
      };
    }
    this.render();
  }

  // Per-market extras from the API row (spread, age, days to resolution).
  // Unknown fields are null; no filter operates on a made-up default.
  marketExtraOf(m) { return this.marketExtra[m.id] || { spread: null, age: null, endsDays: null }; }

  tapeFiltered() { return this.tape.filter((t) => tapeMatches(t, this.state)); }

  // A row opens the market drawer only when that market is in the loaded
  // sample (top 250 by volume); otherwise it carries no handler and no
  // pointer, instead of looking clickable and doing nothing.
  tapeRowView(t) {
    const m = this.markets.find((x) => x.title === t.market);
    return {
      ago: t.ago, wallet: t.wallet, market: t.market, side: t.side, price: t.price,
      size: money(t.size), venue: t.venue, category: t.category || 'Other',
      sideStyle: "font-family:var(--font-mono); font-size:var(--t-small); color:" + (t.side.indexOf('BUY') === 0 ? 'var(--pos)' : 'var(--neg)'),
      act: m ? this.act(() => this.openMarket(m.id)) : '',
      clickable: !!m
    };
  }

  riskCardView(r) {
    const m = this.markets.find((x) => x.title === r.market);
    return {
      kind: r.kind, score: r.score, market: r.market, detail: r.detail,
      wallets: r.wallets, notional: r.notional, window: r.window, venue: r.venue,
      kindStyle: "font-family:var(--font-mono); font-size:var(--t-micro); letter-spacing:.12em; color:" + (r.sev === 'high' ? 'var(--warn)' : r.sev === 'medium' ? 'var(--ink-3)' : 'var(--ink-3)'),
      scoreStyle: "font-family:var(--font-mono); font-size:var(--t-head); color:" + (r.sev === 'high' ? 'var(--warn)' : 'var(--ink-2)'),
      // The card takes the focus but not the button role: it already holds the
      // market link and the WHY-this-score toggle, and a button around those
      // two announces as a button containing buttons.
      act: m ? this.act(() => this.openMarket(m.id), { role: null }) : '',
      clickable: !!m
    };
  }

  // ---- sidebar / topbar ----
  navItem(id, label, badge, badgeColor) {
    const active = this.state.page === id;
    const style = 'display:flex; align-items:center; justify-content:space-between; gap:8px; padding:7px 10px; border-radius:var(--r-control); cursor:pointer; margin-bottom:2px; border-left:2px solid ' + (active ? 'var(--accent)' : 'transparent') + '; background:' + (active ? 'rgba(var(--accent-rgb),.10)' : 'transparent');
    const labelStyle = 'font-size:var(--t-body); color:' + (active ? 'var(--text)' : 'var(--ink-3)') + '; font-weight:' + (active ? '600' : '400');
    const badgeStyle = badge ? ("font-family:var(--font-mono); font-size:var(--t-micro); padding:1px 6px; border-radius:var(--r-control); " + (badgeColor === 'amber' ? 'color:var(--warn); border:1px solid rgba(var(--warn-rgb),.4)' : 'color:var(--on-accent); background:var(--accent)')) : 'display:none';
    // A link, not a div: the router runs on the hash anyway, so the anchor
    // costs nothing and buys the tab stop, the link role, aria-current and
    // open-in-new-tab. go() still does the work — it resolves the deep
    // address (#risk/log) that a bare href cannot know.
    const act = this.act((e) => { e.preventDefault(); this.go(id); }, { role: null });
    return '<a href="#' + esc(id) + '" ' + act + (active ? ' aria-current="page"' : '')
      + ' class="hv-el" style="text-decoration:none; ' + style + '">'
      + '<span style="' + labelStyle + '">' + esc(label) + '</span>'
      + '<span style="' + badgeStyle + '">' + esc(badge || '') + '</span></a>';
  }

  // A research study as a sidebar entry. Studies keep their own routes
  // (#research/<slug>, defined by studies.js); the sidebar just groups them.
  navStudy(i, label, accent) {
    const active = this.state.page === 'research' && this.state.researchTab === i;
    const farbe = accent || 'var(--info)';
    const style = 'display:flex; align-items:center; justify-content:space-between; gap:8px; padding:7px 10px; border-radius:var(--r-control); cursor:pointer; margin-bottom:2px; border-left:2px solid ' + (active ? farbe : 'transparent') + '; background:' + (active ? 'rgba(var(--info-rgb),.12)' : 'transparent');
    const labelStyle = 'font-size:var(--t-body); color:' + (active ? 'var(--text)' : 'var(--ink-3)') + '; font-weight:' + (active ? '600' : '400');
    const act = this.act((e) => { e.preventDefault(); this.goStudy(i); }, { role: null });
    return '<a href="#research/' + esc(this.studienSlug(i)) + '" ' + act + (active ? ' aria-current="page"' : '')
      + ' class="hv-el" style="text-decoration:none; ' + style + '">'
      + '<span style="' + labelStyle + '">' + esc(label) + '</span></a>';
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
    this.adresseSetzen(anker ? String(anker) : (this.adresseSoll() || 'research/' + this.studienSlug(i)));
    this.fetchPageData('research');
  }

  // pushState statt replaceState: der Zurueck-Knopf soll funktionieren. But
  // the same address twice in a row (a second click on the open sidebar
  // entry) adds no entry — back would otherwise need two presses.
  adresseSetzen(adresse) {
    if ((location.hash || '').replace('#', '') === adresse) return;
    try { history.pushState(null, '', '#' + adresse); } catch (e) { /* file:// */ }
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
    // adresseSoll() carries the sub-tab (#risk/log) or, on the wallet page,
    // the analysed address (#wallet/<addr>), so the link stays a deep link.
    this.adresseSetzen(this.adresseSoll() || id);
    this.fetchPageData(id);
  }

  renderSidebar() {
    const hoheRisiken = this.risks.filter((r) => r.sev === 'high').length;
    // Die Seitenleiste erzaehlt den Stand ehrlich: erst der abgeschlossene
    // Track Record (Live runs zuoberst — er ist das Argument; der Pilot ist
    // per Protokoll seit 2026-08-01 fertig), dann die eingefrorenen Studien,
    // dann das kuratierte Record, dann das Analysewerkzeug. Review queue und
    // Pipeline forward sind archiviert: nicht mehr gelistet, aber per Hash
    // erreichbar — die Queue-Zaehler stehen auf Methodology, das Paper-Log
    // zusammengefasst auf Live runs. Settings, Tracked, Copy trade, Portfolio
    // und Resolved bleiben per Hash erreichbar, beschreiben aber einen
    // lokalen Papieraufbau und stehen nicht auf dem oeffentlichen Host.
    const groups = [
      { label: 'START HERE', items: [this.navItem('overview', 'Overview')] },
      { label: 'TRACK RECORD', items: [
        this.navStudyByTab('Live runs'),
        this.navStudyByTab('Pilot')
      ] },
      { label: 'STUDIES · FROZEN', items: [
        this.navStudyByTab('Microstructure'),
        this.navStudyByTab('Category efficiency'),
        this.navStudyByTab('Mentions latency')
      ] },
      { label: 'RECORD', items: [
        this.navStudyByTab('Postmortems', 'Post-mortems'),
        this.navStudyByTab('Field notes'),
        this.navStudyByTab('Methodology')
      ] },
      // Kein Zaehler ohne Daten: eine 0 im Abzeichen liest sich als Messung,
      // solange gar nichts geladen ist.
      { label: 'ANALYSIS TOOL', items: [
        this.navItem('markets', 'Markets'),
        this.navItem('flow', 'Live tape', this.tape.length ? String(this.tape.length) : ''),
        this.navItem('whale', 'Whale flow'),
        this.navItem('cross', 'Cross-venue'),
        this.navItem('traders', 'Leaderboard'),
        this.navItem('wallet', 'Wallet'),
        this.navItem('risk', 'Risk screen', hoheRisiken ? String(hoheRisiken) : '', 'amber'),
        this.navItem('alerts', 'Alerts'),
        this.navItem('backtester', 'Backtester')
      ] }
    ];
    // The copy desk is public read-only (the API's write guard decides who
    // may act), so it is listed for everyone. Portfolio stays a local
    // instrument — listed where the site runs next to its own api/server.py
    // or where this browser holds the admin token, reachable by hash
    // (#portfolio) everywhere else.
    const copyDaten = this.liveData.copy;
    const aktiv = copyDaten && copyDaten.active_count != null ? String(copyDaten.active_count) : '';
    const deskItems = [this.navItem('copy', 'Copy trade', aktiv)];
    if (this.paperDeskSichtbar()) deskItems.push(this.navItem('portfolio', 'Portfolio'));
    groups.push({ label: 'PAPER DESK', items: deskItems });
    const groupHtml = groups.map((g) =>
      '<div style="margin-bottom:14px">'
      + '<div style="font-family:var(--font-mono); font-size:var(--t-micro); letter-spacing:.18em; padding:0 6px 6px; color:var(--ink-4)">' + g.label + '</div>'
      + g.items.join('') + '</div>'
    ).join('');
    // Footer: repository, the read-only statement, and the wallet the live
    // runs were placed from. The paper-equity box that stood here reported a
    // missing paper account on the public host — a box about a thing that
    // does not exist there.
    const foot = "font-family:var(--font-mono); font-size:var(--t-micro); line-height:1.7; color:var(--ink-3)";
    const runsIdx = this.studies.findIndex((st) => st.tab === 'Live runs');
    return ''
      + '<div style="display:flex; align-items:center; gap:9px; padding:0 6px 18px">'
      + '<div style="width:10px; height:10px; background:var(--accent); transform:rotate(45deg)"></div>'
      + '<div style="font-family:var(--font-mono); font-size:var(--t-body); font-weight:600; letter-spacing:.1em; text-transform:uppercase">Market Intel</div></div>'
      + '<div ' + this.act(() => this.setState({ searchOpen: true })) + ' class="hv-edge" style="display:flex; align-items:center; gap:8px; background:var(--panel); border:1px solid var(--line-2); border-radius:var(--r-control); padding:9px 10px; cursor:pointer; margin-bottom:18px">'
      + '<div style="font-family:var(--font-mono); font-size:var(--t-small); color:var(--ink-3); flex:1">Search</div>'
      + '<div style="font-family:var(--font-mono); font-size:var(--t-micro); color:var(--ink-4); border:1px solid var(--line-1); border-radius:var(--r-control); padding:0 5px">/</div></div>'
      + groupHtml
      + '<div style="margin-top:auto; padding-top:16px; border-top:1px solid var(--line-2)">'
      + '<div style="' + foot + '"><a href="' + REPO_URL + '" target="_blank" rel="noopener">github.com/Pablozh123/prediction-market-terminal</a></div>'
      + caveatZeile('site_footer_readonly', { stil: foot + '; margin-top:6px' })
      // Die Adresse oeffnet die On-Chain-Ansicht auf Polygonscan; zur Seite
      // mit jeder Wette fuehrt daneben der eigene Live-runs-Link. Vorher
      // sprang der Klick auf die Adresse nur intern auf die Studienseite und
      // nichts fuehrte zur Kette.
      + '<div style="' + foot + '; margin-top:6px">Live-run wallet '
      + '<a href="https://polygonscan.com/address/' + esc(LIVE_RUN_WALLET_FULL) + '" target="_blank" rel="noopener" class="hv-accent" title="' + esc(LIVE_RUN_WALLET_FULL) + ' — view on-chain on Polygonscan" style="color:var(--ink-2); text-decoration:underline dotted">' + esc(LIVE_RUN_WALLET) + ' ↗</a>'
      + (runsIdx >= 0
        ? ' · <span ' + this.act(() => this.goStudy(runsIdx)) + ' class="hv-accent" title="every bet on the Live runs page" style="color:var(--ink-4); cursor:pointer; text-decoration:underline dotted">runs</span>'
        : '')
      + '</div></div>';
  }

  renderTopbar() {
    const s = this.state;
    const liveDot = s.live === 'live' ? 'var(--pos)' : (s.live === 'error' || s.live === 'offline') ? 'var(--neg)' : 'var(--warn)';
    // Vier Zustaende, alle auf Englisch: noch keine Antwort, Antwort da, Antwort
    // ausgeblieben nach einer, die da war, und gar keine Antwort (reiner
    // Dateihost oder schlafende API — die Forschungsseiten lesen dann die
    // publizierten Dateien). "Demo" gibt es nicht — es gibt keinen
    // Demo-Datensatz, den die Zeile ankuendigen koennte.
    // Die Venues stehen nicht mehr fest im Text: liveStatusLabel nennt die,
    // die geantwortet haben, und benennt eine ausgefallene. Eine Seite, die
    // LIVE auf zwei Venues meldet und eine davon nicht zeigt, luegt.
    const liveLabel = liveStatusLabel(s.live, s.venuesMissing);
    // "Sign in" und "Get alerts" standen rechts ohne Handler. Es gibt weder
    // eine Anmeldung noch eine Alarmzustellung, die von hier aus einzurichten
    // waere (die haengt am Scanner-Skript). Zwei Knoepfe, die nichts tun, sind
    // ein Versprechen ohne Deckung; die Leiste zeigt nur noch den Zustand.
    return ''
      + '<div style="display:flex; align-items:center; gap:10px">'
      + '<span style="width:7px; height:7px; border-radius:50%; background:' + liveDot + '; display:inline-block"></span>'
      + '<span style="font-family:var(--font-mono); font-size:var(--t-micro); letter-spacing:.16em; color:var(--ink-3)">' + liveLabel + ' · ' + s.clock + ' UTC</span></div>'
      + '<div style="display:flex; align-items:center; gap:14px">'
      + '<div style="font-family:var(--font-mono); font-size:var(--t-micro); letter-spacing:.14em; color:var(--ink-4)">MICROSTRUCTURE, MEASURED · READ-ONLY · NO ORDERS</div>'
      // The chip names the theme it switches TO, like every other control
      // here names its action. Colours are CSS custom properties, so the
      // flip repaints without a re-render; only this label needs state.
      + '<div ' + this.act(() => this.toggleTheme()) + ' aria-label="Switch to ' + (s.theme === 'light' ? 'dark' : 'light') + ' theme" class="hv-edge-strong" style="font-family:var(--font-mono); font-size:var(--t-micro); letter-spacing:.08em; border:1px solid var(--line-1); border-radius:var(--r-control); padding:4px 9px; cursor:pointer; color:var(--ink-2); user-select:none">'
      + (s.theme === 'light' ? 'DARK' : 'LIGHT') + '</div></div>';
  }

  // The head script in index.html applied the stored choice before first
  // paint; this flips it, persists it, and keeps the browser-chrome colour
  // (theme-color) in step.
  toggleTheme() {
    const t = this.state.theme === 'light' ? 'dark' : 'light';
    document.documentElement.dataset.theme = t;
    try { localStorage.setItem('mi-theme', t); } catch (e) { /* private mode */ }
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.content = t === 'light' ? '#F4F1EA' : '#0B0B0A';
    this.setState({ theme: t });
  }

  // ---- data layer ----
  async pollLive() {
    try {
      const [mk, tp] = await Promise.all([
        // 500 statt 250: mit dem kleinen Fenster sah die Marktseite kaum
        // Kategorien; die Antwort bleibt schlank (MARKET_FIELDS, ~200 KB).
        apiGet('/api/markets?limit=500'),
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
      // Beide Antworten fuehren, welche Venue lesbar geantwortet hat. Eine
      // Venue, die in einer der beiden fehlt, fehlt fuer die Kopfzeile.
      const fehlend = [];
      [mk, tp].forEach((antwort) => {
        ((antwort && antwort.venues_missing) || []).forEach((v) => {
          if (v && fehlend.indexOf(v) < 0) fehlend.push(v);
        });
      });
      this.setState({
        live: 'live', liveAsOf: String(mk.as_of || ''), tapeAsOf: String(tp.as_of || mk.as_of || ''),
        venuesMissing: fehlend, tapeCategories: (tp && tp.categories) || {}
      });
    } catch (err) {
      // Nach einem geglueckten Lauf bleibt der letzte Stand stehen, die
      // Kopfzeile sagt das bereits. Vorher gibt es nichts zu behalten.
      const text = String(err && err.message ? err.message : err);
      if (this.state.live === 'live') this.setState({ live: 'error' });
      else {
        // Nothing to keep: the request failed before anything ever answered.
        // The topbar says so instead of "waiting" — a static file host and a
        // sleeping API look the same from here, and both are not "waiting".
        this.herkunft.markets = { quelle: 'fehler', fehler: text };
        this.herkunft.tape = { quelle: 'fehler', fehler: text };
        this.setState({ live: 'offline' });
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
      ['notes', '/api/research/field-notes'],
      // Der Wallet-Ledger ist regelmaessig frischer als der Abgleich in
      // runs.json; die Landung bevorzugt ihn fuer die Wallet-Zellen.
      ['ledger', '/api/research/wallet-ledger']
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

  // Das Caveat-Register von /api/claims. Die Oberflaeche traegt eine
  // kompilierte Fassung mit sich (web/js/claims_register.js), also steht
  // jeder Vorbehalt schon vor dieser Anfrage; sie holt nur eine neuere
  // Fassung nach. Das ist nicht theoretisch: Frontend (Pages) und API
  // (Railway) werden getrennt ausgeliefert, ein Registereintrag kann also auf
  // der API neuer sein als im ausgelieferten Bundle. Schlaegt sie fehl,
  // bleibt der eingebaute Stand stehen und die Seite sagt nichts anderes.
  async ladeRegister() {
    try {
      const antwort = await apiGet('/api/claims');
      if (registerAktualisieren(antwort)) this.render();
    } catch (err) {
      // Kein Zustand, keine Meldung: der eingebaute Stand ist vollstaendig.
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
      await this.holenCopy();
      if (page === 'portfolio') await this.holen('track', '/api/track');
    } else if (page === 'resolved') {
      await this.holen('resolved', '/api/resolved');
    } else if (page === 'track') {
      await this.holen('track', '/api/track');
    } else if (page === 'wallet') {
      if (this.state.walletAddr) await this.fetchWallet(this.state.walletAddr, false);
    } else if (page === 'research') {
      const key = this.studies[this.state.researchTab].tab;
      // Begleiter-Nutzlasten der zusammengelegten Seiten: Live runs fasst das
      // Paper-Log (Pipeline forward) zusammen, Methodology die archivierte
      // Review queue — beide Sektionen lesen dieselben publizierten Dateien,
      // die auch die Archiv-Seiten zeigen.
      const BEGLEITER = { 'Live runs': 'Pipeline forward', 'Methodology': 'Review queue' };
      const keys = [key].concat(BEGLEITER[key] ? [BEGLEITER[key]] : []);
      for (const k of keys) {
        if (this.liveData.research[k]) continue;
        const pfad = '/api/research/' + encodeURIComponent(k.toLowerCase().replace(/ /g, '-'));
        try {
          const rs = await apiGet(pfad);
          this.liveData.research[k] = rs && typeof rs === 'object' ? rs : { _quelle: 'leer' };
        } catch (err) {
          this.liveData.research[k] = { _quelle: 'fehler', _fehler: String(err && err.message ? err.message : err) };
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
      // ``+r.pnl || 0`` machte aus einem fehlenden oder umbenannten Feld
      // einen echten, plausiblen Nullgewinn -- waehrend win, resolved und
      // score im selben Objekt daneben null korrekt durchreichen. Fehlt die
      // Zahl, bleibt sie null, und die Zeile zeigt einen Strich.
      pnl: r.pnl != null ? +r.pnl : null,
      win: r.win != null ? +r.win : null,
      resolved: r.resolved != null ? +r.resolved : null,
      vol: r.vol != null ? +r.vol : (r.volume != null ? +r.volume : null),
      score: r.score != null ? +r.score : null,
      grade: r.grade || null,
      scoreN: r.score_n != null ? +r.score_n : null,
      scoreCi: r.score_ci || null,
      sampleBadge: r.sample_badge || null,
      // Score components as a labelled list (api_views.score_parts); the raw
      // reason string is kept only as a fallback for older payloads.
      scoreParts: Array.isArray(r.score_parts) ? r.score_parts : [],
      // Worauf der Score ruht (api_views.score_basis): gemessenes Gewicht,
      // geschaetztes Gewicht, die Namen der geschaetzten Bestandteile und die
      // Groesse der gemeinsam bewerteten Menge.
      scoreBasis: r.score_basis || null,
      tags: String(r.tags || '')
    }));
  }

  // Detail for the drawer. No gate on the poll state any more: the earlier
  // `live !== 'live'` guard meant that on the static host the drawer never
  // asked at all. The address comes from the caller (whale/risk rows), the
  // leaderboard row of that name, or a tape print of that wallet — whichever
  // is known. Reuses a page answer for the same address when there is one.
  async fetchWalletDetail(name, addr) {
    const t = this.traders.find((x) => x.name === name);
    const tapeRow = this.tape.find((x) => x.wallet === name && x.walletAddress);
    const full = String(addr || (t && t.walletFull) || (tapeRow && tapeRow.walletAddress) || '').toLowerCase();
    if (!isFullAddress(full) || this.liveData.walletDetail[name]) return;
    const seite = this.liveData.wallet[full];
    if (seite && seite.herkunft === 'live' && seite.data) { this.liveData.walletDetail[name] = seite.data; this.render(); return; }
    try {
      const wd = await apiGet('/api/wallet/' + full);
      if (wd) { this.liveData.walletDetail[name] = wd; this.render(); }
    } catch (err) { /* detail stays on list data */ }
  }

  // Similar wallets (/api/wallet/<addr>/similar): asked for when the tab is
  // opened, once per address; "Try again" forces a re-read.
  fetchWalletSimilar(addr, force) {
    const key = String(addr || '').toLowerCase();
    if (!isFullAddress(key)) return;
    const vorhanden = this.liveData.walletSimilar[key];
    if (vorhanden && !force) return;
    this.liveData.walletSimilar[key] = { herkunft: 'loading' };
    apiGet('/api/wallet/' + key + '/similar')
      .then((antwort) => { this.liveData.walletSimilar[key] = { herkunft: 'live', data: antwort && typeof antwort === 'object' ? antwort : { rows: [] } }; })
      .catch((err) => { this.liveData.walletSimilar[key] = { herkunft: 'fehler', fehler: String(err && err.message ? err.message : err), status: err && err.status ? err.status : null }; })
      .then(() => this.render());
  }

  // The book of the flagged wallets in the flagged market (/api/risk/book):
  // one request per card, at most three in flight, each market once. The
  // card asks for it while rendering; until the answer is there it says
  // "reading" and never guesses a side.
  fetchRiskBook(marketKey, wallets, side) {
    const key = String(marketKey || '');
    const addrs = (wallets || []).map((w) => String((w && w.wallet) || w || '').toLowerCase()).filter((a) => isFullAddress(a));
    if (!/^0x[0-9a-f]{64}$/i.test(key) || !addrs.length || this.liveData.riskBook[key]) return;
    this.liveData.riskBook[key] = { herkunft: 'loading' };
    this._riskBookQueue = this._riskBookQueue || [];
    this._riskBookQueue.push({ key, addrs: addrs.slice(0, 5), side: String(side || '') });
    this._pumpRiskBooks();
  }

  _pumpRiskBooks() {
    this._riskBookActive = this._riskBookActive || 0;
    while (this._riskBookActive < 3 && this._riskBookQueue && this._riskBookQueue.length) {
      const job = this._riskBookQueue.shift();
      this._riskBookActive += 1;
      apiGet('/api/risk/book?market=' + encodeURIComponent(job.key) + '&wallets=' + encodeURIComponent(job.addrs.join(',')) + '&side=' + encodeURIComponent(job.side))
        .then((antwort) => { this.liveData.riskBook[job.key] = { herkunft: 'live', data: antwort }; })
        .catch((err) => { this.liveData.riskBook[job.key] = { herkunft: 'fehler', fehler: String(err && err.message ? err.message : err) }; })
        .then(() => { this._riskBookActive -= 1; this.render(); this._pumpRiskBooks(); });
    }
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
      auto_fit: !!s.btAutoFit,
      min_notional: s.btMinNotional,
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
        const status = err && err.status;
        // A static file host answers POST with 404/405/501: there is no
        // engine behind this page here, and the line should say so instead
        // of showing a bare status code.
        const meldung = text === 'HTTP 502' ? 'The backtest engine failed on this wallet and window (HTTP 502).'
          : (status === 404 || status === 405 || status === 501) ? 'No backtest API on this host (' + text + ') — the engine runs where api/server.py is served; this copy carries the research payloads only.'
            : text;
        this.setState({ btRun: 'error', btError: meldung });
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

  // ---- copy desk ----
  // The desk is the one place the page writes. Every action posts, then
  // re-reads /api/copy so the table shows the books as the server has them —
  // never an optimistic row. The outcome (or the server's reason for a
  // refusal) lands in copyMsg.
  copyHeaders() {
    const token = String(this.state.copyToken || '').trim();
    return token ? { 'X-Admin-Token': token } : {};
  }

  // Whether this host runs the desk: a local origin, or an answer that says
  // this browser may write. Decides if the sidebar lists it.
  paperDeskSichtbar() {
    const host = (location.hostname || '').toLowerCase();
    if (host === 'localhost' || host === '127.0.0.1' || location.protocol === 'file:') return true;
    // A stored admin token means this browser runs the desk on the public
    // host; the sidebar lists it and the desk is fetched at mount.
    if (String(this.state.copyToken || '').trim()) return true;
    const c = this.liveData.copy;
    return !!(c && c.write_access && c.write_access.allowed);
  }

  // ``leise`` (quiet) keeps the current answer on screen until the new one
  // is in — the periodic refresh must not flash the empty state every 30 s.
  async holenCopy(leise) {
    if (this.liveData.copy && !leise) return;
    try {
      const antwort = await apiGetRaw('/api/copy', this.copyHeaders());
      if (antwort && typeof antwort === 'object') {
        antwort._quelle = 'live';
        this.liveData.copy = antwort;
      } else {
        this.liveData.copy = { _quelle: 'leer' };
      }
    } catch (err) {
      // A failed refresh keeps the last books; the error is only worth
      // replacing them when there was nothing on screen.
      if (!leise || !this.liveData.copy) this.liveData.copy = { _quelle: 'fehler', _fehler: String(err && err.message ? err.message : err) };
    }
    this.render();
  }

  copyReload(leise) {
    if (leise) return this.holenCopy(true);
    this.liveData.copy = null;
    this.render();
    return this.holenCopy();
  }

  copyFehlerText(err) {
    if (err && err.status === 429) return 'rate-limited — retry in ' + Math.max(1, Math.round(err.retryAfter || 10)) + ' s';
    if (err && err.detail) return err.detail;
    const status = err && err.status;
    if (status === 404 || status === 405 || status === 501) return 'no copy desk API on this host (' + err.message + ') — the desk runs where api/server.py is served';
    if (status === 403) return 'not allowed from here (' + err.message + ')';
    return String(err && err.message ? err.message : err);
  }

  async copyAktion(kennung, path, body, erfolg) {
    if (this.state.copyBusy) return;
    this.setState({ copyBusy: kennung, copyMsg: null });
    try {
      const antwort = await apiPost(path, body, this.copyHeaders());
      const text = typeof erfolg === 'function' ? erfolg(antwort) : erfolg;
      this.setState({ copyBusy: '', copyMsg: text ? { kind: 'ok', text } : null });
      await this.copyReload(true);
      return antwort;
    } catch (err) {
      this.setState({ copyBusy: '', copyMsg: { kind: 'err', text: this.copyFehlerText(err) } });
      return null;
    }
  }

  copyFollow() {
    const f = this.state.copyForm || {};
    const wallet = String(f.wallet || '').trim();
    if (!wallet) { this.setState({ copyMsg: { kind: 'err', text: 'paste a wallet address (0x…) or an exact handle first' } }); return; }
    const cash = Number(String(f.cash || '').replace(/[$,]/g, ''));
    if (!(cash > 0)) { this.setState({ copyMsg: { kind: 'err', text: 'start cash must be a positive number' } }); return; }
    const kurz = (w) => (w && w.length > 12 ? w.slice(0, 6) + '…' + w.slice(-4) : w);
    this.copyAktion('follow', '/api/copy/traders', { wallet, label: f.label || '', start_cash: cash, note: f.note || '' }, (r) => {
      this.state.copyForm = { wallet: '', label: '', cash: String(cash), note: '' };
      const who = kurz(r.wallet);
      if (r.added) return 'now following ' + who + (r.seeded ? ' — baseline seeded, copying from now on' : r.seed_error ? ' — baseline not seeded yet (' + r.seed_error + '); the daemon seeds it on its first pass' : '');
      return who + ' was already followed' + (r.resumed ? ' and is active again (start cash unchanged, baseline re-seeded)' : '');
    });
  }

  copySetTrader(wallet, patch) {
    const kurz = wallet && wallet.length > 12 ? wallet.slice(0, 6) + '…' + wallet.slice(-4) : wallet;
    this.copyAktion(wallet, '/api/copy/traders/' + encodeURIComponent(wallet), patch, (r) => {
      this.state.copyEdit = null;
      if (patch.active === false) return kurz + ' paused — nothing new is booked into it until you resume';
      if (patch.active === true) return kurz + ' active again' + (r.seeded ? ' — baseline re-seeded, trades made while paused are observed only' : r.seed_error ? ' — baseline not re-seeded (' + r.seed_error + ')' : '');
      return kurz + ' updated';
    });
  }

  copyTopUp(wallet) {
    const t = this.state.copyTopup || {};
    const amount = Number(String(t.amount || '').replace(/[$,]/g, ''));
    if (!(amount > 0)) { this.setState({ copyMsg: { kind: 'err', text: 'top-up amount must be a positive number' } }); return; }
    this.copyAktion(wallet, '/api/copy/traders/' + encodeURIComponent(wallet) + '/topup', { amount }, (r) => {
      this.state.copyTopup = null;
      return 'added $' + amount.toFixed(2) + ' paper cash — cash now $' + Number(r.cash_after).toFixed(2) + ' (counted as put in)';
    });
  }

  copySaveSettings() {
    const pending = this.state.copySettings;
    if (!pending) { this.setState({ copyMsg: { kind: 'ok', text: 'nothing changed' } }); return; }
    const editable = (this.liveData.copy && this.liveData.copy.settings && this.liveData.copy.settings.editable) || Object.keys(pending);
    const body = {};
    editable.forEach((k) => { if (k in pending) body[k] = pending[k]; });
    this.copyAktion('settings', '/api/copy/settings', body, () => {
      this.state.copySettings = null;
      return 'settings saved — the daemon picks them up on its next pass';
    });
  }

  copySetToken(value) {
    const token = String(value || '').trim();
    try { if (token) localStorage.setItem('copyAdminToken', token); else localStorage.removeItem('copyAdminToken'); } catch (e) { /* private mode */ }
    this.state.copyToken = token;
    this.copyReload();
  }

  // One sync pass in the background; poll /api/copy/sync until it is done,
  // then re-read the books. The page shows "sync running…" meanwhile.
  async copySync() {
    if (this.state.copyBusy) return;
    this.setState({ copyBusy: 'sync', copyMsg: null });
    try {
      const start = await apiPost('/api/copy/sync', {}, this.copyHeaders());
      if (!start.started) {
        this.setState({ copyBusy: '', copyMsg: { kind: 'ok', text: 'a sync pass is already running' } });
        return;
      }
      const bis = Date.now() + 180000;
      let zustand = start.state;
      while (zustand && zustand.running && Date.now() < bis) {
        await new Promise((r) => setTimeout(r, 2500));
        zustand = await apiGetRaw('/api/copy/sync', this.copyHeaders());
      }
      let text;
      if (zustand && zustand.running) text = 'the sync pass is still running — the table refreshes when you press Refresh';
      else if (zustand && zustand.error) text = 'sync pass failed: ' + zustand.error;
      else if (zustand && zustand.result && zustand.result.api) {
        const a = zustand.result.api;
        text = 'sync pass done: ' + a.wallets + ' wallet(s), ' + a.copied + ' copied, ' + a.skipped + ' skipped, ' + a.duplicates + ' already known';
      } else text = 'sync pass done';
      this.setState({ copyBusy: '', copyMsg: { kind: zustand && zustand.error ? 'err' : 'ok', text } });
      await this.copyReload(true);
    } catch (err) {
      this.setState({ copyBusy: '', copyMsg: { kind: 'err', text: this.copyFehlerText(err) } });
    }
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
    // Der Fluss hinter dem Hero und das Band laufen ausserhalb des
    // State-Renders weiter; hier docken sie nur am frischen DOM an.
    mountAmbient();

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

    // The design has no visible <label> — the placeholder is the label. A
    // placeholder is not a name, and it disappears the moment someone types,
    // so mirror it into aria-label. Markup that already carries its own
    // aria-label wins; this only fills the gaps, including future fields.
    document.querySelectorAll('input[placeholder]:not([aria-label])').forEach((el) => {
      el.setAttribute('aria-label', el.getAttribute('placeholder'));
    });

    // Overlays are modal, so the keyboard follows them: into the panel when
    // it opens, back to the content when it closes. Returning to the exact
    // control that opened it is not possible here — render() has already
    // replaced the markup holding it — so <main> takes the focus rather than
    // the top of the document, which is where it would otherwise land.
    const overlayOffen = this.state.searchOpen ? 'search' : (this.state.detail ? 'detail' : '');
    if (overlayOffen !== this._overlayOffen) {
      if (overlayOffen === 'search') {
        // autofocus only fires for markup the parser inserts, and this panel
        // arrives through innerHTML — so move the caret here explicitly.
        const feld = document.querySelector('#search input');
        if (feld) feld.focus();
      } else if (overlayOffen === 'detail') {
        const zu = document.querySelector('#detail [data-act][tabindex]');
        if (zu) zu.focus();
      } else if (!overlayOffen && this._overlayOffen) {
        const m = document.getElementById('main');
        if (m) m.focus();
      }
      this._overlayOffen = overlayOffen;
    }

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
      const aktiv = document.activeElement;
      const tippt = !!(aktiv && /INPUT|TEXTAREA/.test(aktiv.tagName));
      const feld = e.target && e.target.dataset ? e.target.dataset.key : '';
      if (e.key === 'Escape') {
        // Nothing open, nothing to do — no re-render for a stray Escape.
        if (this.state.searchOpen || this.state.detail) this.setState({ searchOpen: false, detail: null });
      } else if (e.key === 'Tab' && (this.state.searchOpen || this.state.detail)) {
        // Both panels say aria-modal, so Tab cycles inside whichever is open.
        // Without this the keyboard wanders into a page the reader cannot see
        // behind it — and the drawer would be promising a modality it does
        // not keep. The palette wins when both are up; it sits on top.
        const box = document.getElementById(this.state.searchOpen ? 'search' : 'detail');
        const ziele = box ? [...box.querySelectorAll('input, [data-act][tabindex]')] : [];
        if (ziele.length) {
          const erster = ziele[0];
          const letzter = ziele[ziele.length - 1];
          if (!box.contains(document.activeElement)) { e.preventDefault(); erster.focus(); }
          else if (e.shiftKey && document.activeElement === erster) { e.preventDefault(); letzter.focus(); }
          else if (!e.shiftKey && document.activeElement === letzter) { e.preventDefault(); erster.focus(); }
        }
      } else if ((e.key === 'ArrowDown' || e.key === 'ArrowUp') && this.state.searchOpen) {
        // Down from the field steps into the results and wraps around, so the
        // list is reachable without leaving the keys the typing hand is on.
        const rows = [...document.querySelectorAll('#search [data-result]')];
        if (rows.length) {
          e.preventDefault();
          const hier = document.activeElement && document.activeElement.closest ? document.activeElement.closest('[data-result]') : null;
          const i = hier ? rows.indexOf(hier) : -1;
          rows[e.key === 'ArrowDown' ? (i + 1) % rows.length : (i <= 0 ? rows.length - 1 : i - 1)].focus();
        }
      } else if (e.key === 'Enter' && feld === 'walletInput') {
        // Enter in the wallet input = the Analyse button.
        e.preventDefault();
        this.analyseWallet(e.target.value);
      } else if (e.key === 'Enter' && feld === 'searchQuery' && isFullAddress(e.target.value)) {
        // Enter on a pasted address in the palette opens the wallet page.
        e.preventDefault();
        this.analyseWallet(e.target.value);
      } else if (e.key === '/' && !this.state.searchOpen && !tippt) {
        e.preventDefault();
        this.setState({ searchOpen: true });
      } else if ((e.key === 'Enter' || e.key === ' ') && !tippt) {
        // Enter/Space on a focused control does what a click does. Native
        // elements are left alone — a link inside a row handles its own
        // Enter, and firing the row as well would do two things at once.
        // The handler is called directly rather than through .click() so a
        // nested control never bubbles into the card around it.
        const nativ = e.target.closest ? e.target.closest('a[href],button,input,select,textarea,summary') : null;
        if (!nativ) {
          const el = e.target.closest ? e.target.closest('[data-act][tabindex]') : null;
          const fn = el ? this._acts[+el.dataset.act] : null;
          if (fn) { e.preventDefault(); fn(e); }
        }
      } else if (e.key === 'Enter' && this.state.searchOpen) {
        // Enter from the palette's own field opens the first result. Focus on
        // a result row is handled above, by that row.
        const erster = document.querySelector('#search [data-act][data-result]');
        if (erster) { e.preventDefault(); erster.click(); }
      }
    });
    // Floating card for elements that carry data-tip (the treemap tiles):
    // JSON {title, image, pnl, rows:[[label, value]]} rendered next to the
    // pointer, kept inside the viewport. One element, reused; nothing in
    // the card that is not in the attribute.
    let tipEl = document.getElementById('tip');
    if (!tipEl) { tipEl = document.createElement('div'); tipEl.id = 'tip'; document.body.appendChild(tipEl); }
        const tipMove = (e) => {
      const pad = 14;
      const w = tipEl.offsetWidth || 280;
      const h = tipEl.offsetHeight || 120;
      let x = e.clientX + pad;
      let y = e.clientY + pad;
      if (x + w > window.innerWidth - 8) x = e.clientX - w - pad;
      if (y + h > window.innerHeight - 8) y = e.clientY - h - pad;
      tipEl.style.left = Math.max(4, x) + 'px';
      tipEl.style.top = Math.max(4, y) + 'px';
    };
    document.addEventListener('mouseover', (e) => {
      const el = e.target.closest ? e.target.closest('[data-tip]') : null;
      if (!el) return;
      let tip = null;
      try { tip = JSON.parse(el.getAttribute('data-tip') || ''); } catch (err) { tip = null; }
      if (!tip || !Array.isArray(tip.rows)) return;
      const farbe = tip.pnl === 'down' ? 'var(--neg)' : 'var(--pos)';
      tipEl.innerHTML = '<div style="display:flex; gap:10px; align-items:flex-start">'
        + (tip.image ? '<img src="' + esc(tip.image) + '" alt="" style="width:40px; height:40px; border-radius:var(--r-control); object-fit:cover; flex:none; background:rgba(var(--ink),.06)" />' : '')
        + '<div style="font-family:var(--font-ui); font-size:var(--t-small); font-weight:600; line-height:1.35; color:var(--text)">' + esc(tip.title || '') + '</div></div>'
        + '<div style="margin-top:9px; display:flex; flex-direction:column; gap:3px">'
        + tip.rows.map((r) => '<div style="display:flex; justify-content:space-between; gap:14px; font-size:var(--t-small)"><span style="color:var(--ink-4)">' + esc(String(r[0])) + '</span><span style="' + M + '; color:' + (/^(unrealised|realised)$/.test(String(r[0])) ? farbe : 'var(--text)') + '; text-align:right">' + esc(String(r[1])) + '</span></div>').join('')
        + '</div>';
      tipEl.classList.add('on');
      tipMove(e);
    });
    document.addEventListener('mousemove', (e) => {
      if (!tipEl.classList.contains('on')) return;
      const el = e.target.closest ? e.target.closest('[data-tip]') : null;
      if (!el) { tipEl.classList.remove('on'); return; }
      tipMove(e);
    });
    document.addEventListener('mouseout', (e) => {
      const el = e.target.closest ? e.target.closest('[data-tip]') : null;
      if (!el) return;
      const to = e.relatedTarget && e.relatedTarget.closest ? e.relatedTarget.closest('[data-tip]') : null;
      if (to !== el) tipEl.classList.remove('on');
    });
    // Back/forward: re-read the hash so the visible page follows the address.
    window.addEventListener('hashchange', () => {
      const segmente = (location.hash || '#overview').replace('#', '').split('/');
      if (segmente[0] === 'research') {
        const i = this.studienIndexAus(segmente[1]);
        // The third segment is a card anchor (#research/microstructure/<id>)
        // unless it names a Live-runs tab (#research/live-runs/timing).
        this._pendingAnchor = segmente[2] && !this.tabAusAdresse(segmente) ? segmente.join('/') : null;
        this.setState({ page: 'research', researchTab: i >= 0 ? i : this.state.researchTab, detail: null });
        this.fetchPageData('research');
      } else if (segmente[0] === 'wallet') {
        // #wallet/<addr> from back/forward or a pasted link: analyse that
        // address; a bare #wallet just shows the page as it is.
        const kandidat = segmente[1] ? decodeURIComponent(segmente[1]).trim() : '';
        if (kandidat && isFullAddress(kandidat)) {
          if (kandidat.toLowerCase() !== this.state.walletAddr || this.state.page !== 'wallet') {
            const key = kandidat.toLowerCase();
            const recent = [key].concat((this.state.walletRecent || []).filter((a) => a !== key)).slice(0, 8);
            this.setState({ page: 'wallet', walletAddr: key, walletInput: kandidat, walletRecent: recent, detail: null });
            this.fetchWallet(key, false);
          }
        } else if (this.state.page !== 'wallet') {
          this.setState({ page: 'wallet', detail: null });
        }
      } else if (segmente[0] in PAGES) {
        // Same page, other tab (#risk → #risk/log) counts as navigation too.
        const vorher = this.state.page + '/' + (SUB_TABS[segmente[0]] ? this.state[SUB_TABS[segmente[0]].key] : '');
        this.tabAusAdresse(segmente);
        const nachher = segmente[0] + '/' + (SUB_TABS[segmente[0]] ? this.state[SUB_TABS[segmente[0]].key] : '');
        if (vorher === nachher) return;
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
    // Der Poll holt markets (~280 KB) und tape (~180 KB) und rendert danach
    // die ganze Seite neu. In einem verborgenen Tab sieht das niemand, es
    // kostet aber rund 55 MB je Stunde und auf der Marktseite alle 30 s einen
    // Render von ~114 ms. Also: nur im sichtbaren Tab, und beim Zurueckkommen
    // einmal sofort nachziehen, damit der Stand nicht veraltet wirkt.
    setInterval(() => { if (!document.hidden) this.pollLive(); }, 30000);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) this.pollLive(); });
    // The copy desk re-reads its books every 30 s while it is open (the
    // daemon writes between renders); not while an action is in flight, and
    // never mid-edit — the form values live in state and survive the render.
    setInterval(() => {
      if (this.state.page === 'copy' && !this.state.copyBusy && this.liveData.copy && this.liveData.copy._quelle === 'live') this.copyReload(true);
    }, 30000);
    // Die Seiten mit lebenden Nutzlasten (Live runs, Pilot) lesen alle 60 s
    // neu, solange sie offen sind: runs.json, pilot.json und der Wallet-
    // Ledger aendern sich durch die Publish-Laeufe, und ein einmal geladener
    // Stand blieb sonst bis zum Seiten-Reload stehen. Offene <details>
    // ueberleben den Render, weil app.js sie ueber data-key wiederherstellt.
    const REFRESH_STUDIEN = { 'Live runs': ['Live runs', 'Pipeline forward'], 'Pilot': ['Pilot'] };
    setInterval(() => {
      if (this.state.page !== 'research') return;
      const studie = this.studies[this.state.researchTab];
      const keys = studie && REFRESH_STUDIEN[studie.tab];
      if (!keys) return;
      keys.forEach((k) => { this.liveData.research[k] = null; });
      ledgerVerwerfen();
      this.fetchPageData('research');
    }, 60000);
    this.ladeLanding();
    this.ladeRegister();
    this.fetchPageData(this.state.page);
    // The desk's badge in the sidebar (active traders) needs the answer even
    // when the page opened elsewhere — only where this browser is its admin.
    if (String(this.state.copyToken || '').trim() && this.state.page !== 'copy' && this.state.page !== 'portfolio') this.holenCopy();
  }
}

const T = new Terminal();
T.mount();
export default T;
