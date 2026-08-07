// Alerts, Research (8 studies incl. live runs), Settings — ported from the
// design reference. Research tabs render the published JSON payloads from
// public/data/ when the API serves them, incl. their stand_utc stamp and note.

import { esc, num, herkunftSatz, leerZeile } from '../util.js';
import { renderMicrostructure } from './microstructure_page.js';

const M = "font-family:'JetBrains Mono',monospace";
const LBL9 = M + '; font-size:9px; letter-spacing:.14em; color:rgba(255,255,255,.42); margin-bottom:6px';

function filterGroup(label, chipsHtml) {
  return '<div><div style="' + LBL9 + '">' + label + '</div><div style="display:flex; gap:6px; flex-wrap:wrap">' + chipsHtml + '</div></div>';
}

// Welche publizierte Datei hinter welchem Research-Tab steht. Der Leerzustand
// nennt sie beim Namen, damit klar ist, was fehlt statt nur dass etwas fehlt.
const RESEARCH_DATEI = [
  'queue.json', 'kategorie_karte.json', 'mentions_latenz.json', 'runs.json',
  'microstructure.json', 'pilot.json', 'pipeline_forward.json', 'audit.json',
  'postmortems.json'
];

// Farbe je Achse, damit sich die Fehlerarten auf einen Blick trennen lassen.
const ACHSEN_FARBE = {
  'Rule understanding': '#F5A623',
  'Execution': '#FF7A7A',
  'Microstructure': '#4F8EF7',
  'Data': '#7DE2D1',
  'Infrastructure': '#C792EA',
};

/** Post-Mortems: neun Vorfaelle mit Ursache, Kosten, Fix und Codeverweis. */
function renderPostmortems(payload) {
  const eintraege = (payload && payload.eintraege) || [];
  if (!eintraege.length) {
    return '<div style="padding:26px 24px">'
      + '<div style="background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:12px; padding:22px 24px; max-width:720px">'
      + '<div style="font-size:16px; font-weight:600">No incidents published</div>'
      + '<div style="font-size:13px; color:rgba(255,255,255,.55); margin-top:10px; line-height:1.6">'
      + 'This page reads <span style="' + M + '">public/data/postmortems.json</span>.</div></div></div>';
  }

  const achsen = {};
  eintraege.forEach((e) => { achsen[e.achse] = (achsen[e.achse] || 0) + 1; });
  const chips = Object.entries(achsen).sort((a, b) => b[1] - a[1]).map(([achse, n]) =>
    '<div style="' + M + '; font-size:10px; color:' + (ACHSEN_FARBE[achse] || '#95A0AB')
    + '; border:1px solid ' + (ACHSEN_FARBE[achse] || '#95A0AB') + '44; border-radius:5px; padding:4px 9px">'
    + esc(achse.toUpperCase()) + ' ' + n + '</div>').join('');

  const feld = (label, wert, farbe) =>
    '<div style="margin-top:11px">'
    + '<div style="' + M + '; font-size:9px; letter-spacing:.13em; color:rgba(255,255,255,.38)">' + label + '</div>'
    + '<div style="font-size:12.5px; color:' + (farbe || 'rgba(255,255,255,.72)') + '; margin-top:4px; line-height:1.6">'
    + esc(wert || '—') + '</div></div>';

  const karten = eintraege.slice().sort((a, b) => String(b.datum).localeCompare(String(a.datum))).map((e) => {
    const farbe = ACHSEN_FARBE[e.achse] || '#95A0AB';
    return '<div style="background:#10151A; border:1px solid rgba(255,255,255,.09); border-left:2px solid ' + farbe
      + '; border-radius:10px; padding:16px 18px">'
      + '<div style="display:flex; align-items:baseline; justify-content:space-between; gap:14px; flex-wrap:wrap">'
      + '<div style="font-size:14.5px; font-weight:600; flex:1; min-width:220px">' + esc(e.titel) + '</div>'
      + '<div style="' + M + '; font-size:10px; color:' + farbe + '">' + esc(e.achse || '') + '</div></div>'
      + '<div style="' + M + '; font-size:10px; color:rgba(255,255,255,.4); margin-top:5px">'
      + esc(e.datum) + (e.profil ? ' · ' + esc(e.profil) : '') + '</div>'
      + feld('WHAT HAPPENED', e.was_passierte)
      + feld('WHAT IT COST', e.auswirkung, '#FF7A7A')
      + feld('WHAT CHANGED', e.fix, '#C8F542')
      + (e.referenz
        ? '<div style="' + M + '; font-size:10px; color:rgba(255,255,255,.35); margin-top:11px; '
          + 'border-top:1px solid rgba(255,255,255,.06); padding-top:9px">' + esc(e.referenz) + '</div>'
        : '')
      + '</div>';
  }).join('');

  return '<div style="padding:20px 24px 36px">'
    + '<div style="font-size:13.5px; color:rgba(255,255,255,.6); line-height:1.6; max-width:820px">'
    + esc((payload && payload.hinweis) || '')
    + '</div>'
    + '<div style="display:flex; gap:7px; flex-wrap:wrap; margin-top:12px">'
    + '<div style="' + M + '; font-size:10px; color:#fff; border:1px solid rgba(255,255,255,.2); border-radius:5px; padding:4px 9px">'
    + eintraege.length + ' INCIDENTS</div>' + chips + '</div>'
    + '<div style="display:grid; grid-template-columns:repeat(auto-fit,minmax(360px,1fr)); gap:14px; margin-top:16px">'
    + karten + '</div></div>';
}

function fehlendeStudieHtml(study, datei) {
  return '<div style="padding:26px 24px">'
    + '<div style="background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:12px; padding:22px 24px; max-width:720px">'
    + '<div style="font-size:16px; font-weight:600">' + esc(study.title) + '</div>'
    + '<div style="font-size:13px; color:rgba(255,255,255,.55); margin-top:10px; line-height:1.6">'
    + 'No published data for this study yet. It reads '
    + '<span style="' + M + '">public/data/' + esc(datei || 'the study payload') + '</span>, '
    + 'which the daily run writes. Nothing is shown here rather than a placeholder, '
    + 'because a made-up figure under a frozen date would be worse than an empty panel.'
    + '</div></div></div>';
}

// ---------------------------------------------------------------- alerts
export function renderAlerts(T) {
  const s = T.state;
  const live = T.liveData.alerts;
  const alarmSatz = herkunftSatz(
    live ? { quelle: live._quelle === 'fehler' ? 'fehler' : 'leer', fehler: live._fehler } : null, '/api/alerts');
  const feedAll = live && live.signals ? live.signals : [];
  const feed = feedAll.filter((a) => (s.alertPlatform === 'all' || a.venue === s.alertPlatform) && (s.alertType === 'all' || a.rule === s.alertType) && (s.alertScope === 'all' || a.watched) && (!s.alertQuery.trim() || a.market.toLowerCase().indexOf(s.alertQuery.trim().toLowerCase()) >= 0));
  // Fest verdrahtet standen hier 14, 6, 31 und 4 Treffer "heute" — an jedem
  // Tag dieselben. Gezaehlt wird jetzt der ganze Scan, nicht die Tabelle:
  // die zeigt nur die ersten 60 Zeilen, und wer die zaehlt, meldet fuer eine
  // Regel null, die in Wahrheit hundertfach ausgeloest hat. Und eine Regel,
  // die der Endpunkt gar nicht auswertet, sagt das statt einer Null.
  const REGEL_SIGNAL = {
    movers: 'FAST MOVER', volume: 'VOLUME ANOMALY', whales: 'WHALE PRINT',
    spreads: 'TIGHT SPREAD', holders: 'HOLDER CONCENTRATION', endings: 'ENDING SOON'
  };
  const zaehlung = (live && live.rule_counts) || null;
  const ungeprueft = (live && live.rules_not_evaluated) || [];
  const gesamtTreffer = zaehlung ? Object.keys(zaehlung).reduce((a, k) => a + (zaehlung[k] || 0), 0) : 0;
  const trefferText = (key, an) => {
    // Eine Regel, die der Endpunkt nicht auswertet, sagt das auch dann, wenn
    // der Schalter aus ist: sonst schaltet ein Leser sie ein und wartet auf
    // Treffer, die nie kommen koennen.
    if (ungeprueft.indexOf(REGEL_SIGNAL[key]) >= 0) return 'not evaluated by this endpoint';
    if (!an) return 'off';
    if (!live || !live.signals) return 'no feed loaded';
    if (!zaehlung) return 'no count reported';
    return (zaehlung[REGEL_SIGNAL[key]] || 0) + ' in this scan';
  };
  const rules = [
    { key: 'movers', name: 'Fast movers', desc: 'A market moves more than five cents in under an hour.' },
    { key: 'volume', name: 'Volume anomaly', desc: 'An hour trades more than three times its own daily average.' },
    { key: 'whales', name: 'Whale prints', desc: 'A single trade above your whale threshold lands.' },
    { key: 'spreads', name: 'Tight spreads', desc: 'A liquid market narrows below two cents.' },
    { key: 'holders', name: 'Holder concentration', desc: 'Three wallets or fewer hold most of one side.' },
    { key: 'endings', name: 'Resolving soon', desc: 'A market you watch resolves within seventy-two hours.' }
  ];

  let body = '';
  if (s.alertTab === 'signals') {
    body = '<div>'
      + '<div style="' + M + '; font-size:11px; color:rgba(255,255,255,.45); padding:14px 24px 0">showing signals over ' + s.thMove + '¢ moves, prints above $' + num(s.thWhale) + ', spreads under ' + s.thSpread + '¢, resolving within ' + s.thEnding + ' h' + (live && live.as_of ? ' · snapshot ' + esc(live.as_of) : '') + '</div>'
      // Der Schnitt gehoert danebengeschrieben. Eine Tabelle, die 60 von 300
      // Zeilen zeigt und das verschweigt, liest sich wie der ganze Scan.
      + (zaehlung && live.shown_limit && gesamtTreffer > live.shown_limit
        ? '<div style="' + M + '; font-size:11px; color:#F5A623; padding:6px 24px 0">'
          + 'showing the top ' + live.shown_limit + ' of ' + num(gesamtTreffer) + ' signals in this scan</div>'
        : '')
      + '<div style="border:1px solid rgba(255,255,255,.09); border-radius:12px; margin:12px 24px; overflow:hidden">'
      + '<div style="display:grid; grid-template-columns:92px 170px 1fr 110px 120px; gap:10px; padding:9px 16px; background:#10151A; border-bottom:1px solid rgba(255,255,255,.09); ' + M + '; font-size:9px; letter-spacing:.12em; color:rgba(255,255,255,.45)">'
      + '<div>TIME</div><div>SIGNAL</div><div>MARKET</div><div style="text-align:right">READING</div><div style="text-align:right">VENUE</div></div>'
      + (feed.length ? '' : leerZeile(feedAll.length ? 'No signal matches these filters.' : alarmSatz))
      + feed.map((a) =>
        '<div style="display:grid; grid-template-columns:92px 170px 1fr 110px 120px; gap:10px; align-items:center; padding:11px 16px; border-bottom:1px solid rgba(255,255,255,.06)">'
        + '<div style="' + M + '; font-size:12px; color:rgba(255,255,255,.55)">' + esc(a.time) + '</div>'
        + '<div style="' + M + '; font-size:10.5px; letter-spacing:.1em; color:#C8F542">' + esc(a.rule) + '</div>'
        + '<div style="font-size:13px; padding-right:16px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis">' + esc(a.market) + '</div>'
        + '<div style="' + M + '; font-size:12.5px; text-align:right">' + esc(a.value) + '</div>'
        + '<div style="' + M + '; font-size:11.5px; text-align:right; color:rgba(255,255,255,.45)">' + esc(a.venue) + '</div></div>'
      ).join('')
      + '</div></div>';
  } else if (s.alertTab === 'rules') {
    body = '<div style="padding:16px 24px; display:grid; grid-template-columns:repeat(3,1fr); gap:14px">'
      + rules.map((a) => {
        const on = !!s.alertsOn[a.key];
        return '<div ' + T.act(() => T.setState({ alertsOn: Object.assign({}, s.alertsOn, { [a.key]: !on }) })) + ' style="border-radius:12px; padding:15px 17px; cursor:pointer; background:#10151A; border:1px solid ' + (on ? 'rgba(200,245,66,.35)' : 'rgba(255,255,255,.09)') + '">'
          + '<div style="display:flex; align-items:center; justify-content:space-between; gap:12px">'
          + '<div style="font-size:14.5px; font-weight:600">' + a.name + '</div>'
          + '<div style="width:38px; height:21px; flex:none; border-radius:11px; padding:2px; display:flex; background:' + (on ? '#C8F542' : 'rgba(255,255,255,.14)') + '; justify-content:' + (on ? 'flex-end' : 'flex-start') + '">'
          + '<div style="width:17px; height:17px; border-radius:50%; background:' + (on ? '#0A0D0F' : 'rgba(255,255,255,.55)') + '"></div></div></div>'
          + '<div style="font-size:12.5px; color:rgba(255,255,255,.55); margin-top:8px; line-height:1.45">' + a.desc + '</div>'
          + '<div style="' + M + '; font-size:10.5px; margin-top:12px; color:rgba(255,255,255,.4)">' + esc(trefferText(a.key, on)) + '</div></div>';
      }).join('')
      + '</div>';
  } else if (live && live.deliveries) {
    const dv = live.deliveries;
    body = '<div style="margin:16px 24px; border:1px solid rgba(255,255,255,.09); border-radius:12px; padding:22px; background:#10151A">'
      + '<div style="' + M + '; font-size:10.5px; letter-spacing:.14em; color:rgba(255,255,255,.55)">DELIVERY LOG</div>'
      + '<div style="font-size:13px; color:rgba(255,255,255,.6); margin-top:10px; line-height:1.5; max-width:640px">' + esc(dv.note || 'No delivery log available.') + '</div>'
      + (dv.last_scan_at ? '<div style="' + M + '; font-size:11.5px; color:rgba(255,255,255,.45); margin-top:12px">last scan ' + esc(dv.last_scan_at) + ' · ' + esc(String(dv.last_hits)) + ' hits · ' + esc(String(dv.last_sent)) + ' sent</div>' : '')
      + '</div>';
  } else {
    // Ein Zustellprotokoll ist ein Nachweis. Sechs erfundene Zeilen mit
    // Uhrzeit, Kanal und Status behaupten Versand, den es nie gab.
    body = '<div style="margin:16px 24px; border:1px solid rgba(255,255,255,.09); border-radius:12px; padding:22px; background:#10151A">'
      + '<div style="' + M + '; font-size:10.5px; letter-spacing:.14em; color:rgba(255,255,255,.55)">DELIVERY LOG</div>'
      + '<div style="font-size:13px; color:rgba(255,255,255,.6); margin-top:10px; line-height:1.5; max-width:640px">'
      + esc(alarmSatz) + '</div></div>';
  }

  return '<div>'
    + '<div style="padding:20px 24px 16px; border-bottom:1px solid rgba(255,255,255,.09)">'
    + '<div style="' + M + '; font-size:10px; letter-spacing:.18em; color:#C8F542">ALERTS</div>'
    + '<div style="font-family:\'Instrument Serif\',serif; font-size:30px; line-height:1.1; margin-top:5px">Tell me when this happens</div>'
    + '<div style="font-size:13px; color:rgba(255,255,255,.55); margin-top:9px; max-width:700px">Rules run on the public feed every minute. Switch one on and it also goes to Telegram.</div></div>'
    + '<div style="padding:16px 24px 0; display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:14px 18px">'
    + '<div><div style="' + LBL9 + '">SEARCH</div><input value="' + esc(s.alertQuery) + '" ' + T.inp((e) => T.setState({ alertQuery: e.target.value }), 'alertQuery') + ' placeholder="market, wallet, category…" style="width:100%; box-sizing:border-box; background:#10151A; border:1px solid rgba(255,255,255,.16); border-radius:7px; padding:8px 10px; ' + M + '; font-size:11.5px; color:#fff; outline:none" /></div>'
    + filterGroup('PLATFORM', [['all','All'],['Polymarket','Polymarket'],['Kalshi','Kalshi']].map((o) => T.opt(o[1], s.alertPlatform === o[0], { alertPlatform: o[0] })).join(''))
    + filterGroup('SIGNAL TYPE', [['all','All'],['WHALE PRINT','Whale prints'],['FAST MOVER','Fast movers'],['VOLUME ANOMALY','Volume']].map((o) => T.opt(o[1], s.alertType === o[0], { alertType: o[0] })).join(''))
    + filterGroup('SCOPE', [['all','Everything'],['watched','Watched only']].map((o) => T.opt(o[1], s.alertScope === o[0], { alertScope: o[0] })).join(''))
    + '</div>'
    + '<div style="padding:16px 24px 0; display:grid; grid-template-columns:repeat(5, minmax(0,1fr)); gap:14px 18px">'
    + filterGroup('MOVE AT LEAST', [3, 5, 8, 12].map((v) => T.opt(v + '¢', s.thMove === v, { thMove: v })).join(''))
    + filterGroup('SPREAD UNDER', [1, 2, 3, 5].map((v) => T.opt(v + '¢', s.thSpread === v, { thSpread: v })).join(''))
    + filterGroup('PRINT AT LEAST', [1000, 2500, 10000, 25000].map((v) => T.opt('$' + num(v), s.thWhale === v, { thWhale: v })).join(''))
    + filterGroup('RESOLVING WITHIN', [24, 48, 72, 168].map((v) => T.opt(v + ' h', s.thEnding === v, { thEnding: v })).join(''))
    + filterGroup('TOP HOLDER OVER', [25, 40, 60, 80].map((v) => T.opt(v + '%', s.thHolder === v, { thHolder: v })).join(''))
    + '</div>'
    + '<div style="display:flex; gap:6px; padding:16px 24px 0; flex-wrap:wrap">'
    + [['signals','Signals'],['rules','Rules'],['deliveries','Deliveries']].map((o) => T.tab(o[1], s.alertTab === o[0], { alertTab: o[0] })).join('')
    + '</div>'
    + body
    + '</div>';
}

// ---------------------------------------------------------------- research
export function renderResearch(T) {
  const s = T.state;
  const study = T.studies[s.researchTab];
  const key = study.tab;
  const payload = T.liveData.research[key] || null;

  const header = '<div style="padding:20px 24px 0; border-bottom:1px solid rgba(255,255,255,.09)">'
    + '<div style="' + M + '; font-size:10px; letter-spacing:.18em; color:#4F8EF7">RESEARCH</div>'
    + '<div style="font-family:\'Instrument Serif\',serif; font-size:30px; line-height:1.1; margin-top:5px">The studies behind the terminal</div>'
    // Frueher stand hier "Eight studies, each read-only, pre-registered and
    // dated". Vorregistriert ist bislang genau eine, und die als Entwurf mit
    // der Nummer PENDING. Der Satz nennt jetzt, was jede Studie wirklich
    // mitbringt, und das ist nachpruefbar.
    + '<div style="font-size:13px; color:rgba(255,255,255,.55); margin-top:9px; max-width:720px">Read-only studies on recorded data. Each one states its method, its sample, its time window and what it cannot show. Pick one in the sidebar.</div>'
    + '<div style="height:18px"></div></div>';

  if (s.researchTab === 3) {
    return '<div>' + header + renderLiveRuns(T, payload) + '</div>';
  }
  if (s.researchTab === 8) {
    return '<div>' + header + renderPostmortems(payload) + '</div>';
  }

  // Microstructure hat eine eigene Seite: zwoelf Studien, je Karte mit
  // Frage, Verdikt, Diagramm und Quelle. Nutzlast aus public/data.
  if (s.researchTab === 4) {
    return '<div>' + header + renderMicrostructure(payload) + '</div>';
  }

  const stamp = payload && payload.stand_utc ? String(payload.stand_utc).slice(0, 16).replace('T', ' ') + ' UTC' : study.stamp;
  const note = payload && payload.hinweis ? payload.hinweis : study.note;
  const table = buildStudyTable(T, s.researchTab, payload);
  // Ohne Nutzlast keine Zahlen. Die frueheren Demo-Werte widersprachen der
  // eigenen Forschung teils frontal: dort stand "IMBALANCE EDGE +0.4c net of
  // fees", gemessen sind -2.50 Cent. Unter einem Stempel wie
  // "frozen 2026-06-30" ist eine erfundene Zahl nicht neutral, sondern
  // belastend.
  const stats = buildStudyStats(s.researchTab, payload);
  if (!stats) {
    return '<div>' + header + fehlendeStudieHtml(study, RESEARCH_DATEI[s.researchTab]) + '</div>';
  }
  const chartLabel = study.chart;
  // Keine Zierkurve mehr, nirgends. Hier lief ein Zufallsgenerator mit
  // eingebautem Aufwaertsdrift unter Ueberschriften wie FORWARD PAPER EQUITY
  // und BRIER SCORE BY CATEGORY, auch dann, wenn echte Daten geladen waren.
  // Die Begruendung stand seit der Pilot-Ausnahme daneben und galt immer
  // schon fuer alle: eine gemalte Kurve ist eine Behauptung. Ein Diagramm
  // gibt es erst, wenn eine echte Serie in der Nutzlast liegt.
  const serie = payload && Array.isArray(payload.serie) && payload.serie.length > 1
    ? payload.serie : null;
  const pts = serie ? T.seriesPoints(serie, 900, 220) : '';

  return '<div>' + header
    + '<div style="padding:22px 24px">'
    + '<div style="display:flex; align-items:flex-start; justify-content:space-between; gap:24px">'
    + '<div style="max-width:640px">'
    + '<div style="font-size:20px; font-weight:600">' + esc(study.title) + '</div>'
    + '<div style="font-size:13.5px; color:rgba(255,255,255,.6); margin-top:8px; line-height:1.5">' + esc(note) + '</div></div>'
    + '<div style="' + M + '; font-size:10.5px; color:rgba(255,255,255,.4); border:1px solid rgba(255,255,255,.14); border-radius:6px; padding:6px 10px; white-space:nowrap">' + esc(stamp) + '</div></div>'
    + '<div style="display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-top:18px">'
    + stats.map((x) =>
      '<div style="background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:10px; padding:14px 16px">'
      + '<div style="' + M + '; font-size:9.5px; letter-spacing:.13em; color:rgba(255,255,255,.45)">' + esc(x.label) + '</div>'
      + '<div style="' + M + '; font-size:21px; margin-top:7px">' + esc(x.value) + '</div>'
      + '<div style="' + M + '; font-size:10.5px; color:rgba(255,255,255,.4); margin-top:4px">' + esc(x.note) + '</div></div>'
    ).join('')
    + '</div>'
    + (pts ? '<div style="background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:12px; margin-top:14px; padding:16px 18px">'
    + '<div style="' + M + '; font-size:10.5px; letter-spacing:.14em; color:rgba(255,255,255,.55); margin-bottom:12px">' + esc(chartLabel) + '</div>'
    + '<svg width="100%" height="220" viewBox="0 0 900 220" preserveAspectRatio="none">'
    + '<line x1="0" y1="20" x2="900" y2="20" stroke="rgba(255,255,255,.07)" />'
    + '<line x1="0" y1="75" x2="900" y2="75" stroke="rgba(255,255,255,.07)" />'
    + '<line x1="0" y1="130" x2="900" y2="130" stroke="rgba(255,255,255,.07)" />'
    + '<line x1="0" y1="210" x2="900" y2="210" stroke="rgba(255,255,255,.14)" />'
    + '<polyline points="' + pts + '" fill="none" stroke="#4F8EF7" stroke-width="2" /></svg></div>' : '')
    + (s.researchTab === 5 ? pilotAuswertungHtml(payload) : '')
    + (s.researchTab === 6 ? pipelineRegelnHtml(payload) : '')
    + table
    + '<div style="display:flex; gap:10px; margin-top:14px">'
    + '<div class="hv-bd35" style="font-size:13px; color:#fff; border:1px solid rgba(255,255,255,.2); border-radius:8px; padding:10px 16px; cursor:pointer">Download the data</div>'
    + '<div class="hv-bd35" style="font-size:13px; color:#fff; border:1px solid rgba(255,255,255,.2); border-radius:8px; padding:10px 16px; cursor:pointer">Read the method</div>'
    + '</div></div></div>';
}

// Pilot: die aus den Trades gerechnete Auswertung (api/server.py haengt sie
// als `auswertung` an). Befund, offener Ausgang und Regeltreue-Pruefung.
function pilotAuswertungHtml(payload) {
  const a = payload && payload.auswertung;
  if (!a || !a.trades || !a.trades.gesamt) return '';
  const karte = 'background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:12px';
  const rt = a.regeltreue || {};
  const punkte = (rt.punkte || []).map((p) => {
    const farbe = p.erfuellt ? '#C8F542' : '#F5A623';
    const zeichen = p.erfuellt ? '✓' : '!';
    return '<div style="display:grid; grid-template-columns:18px 1fr auto; gap:12px; align-items:baseline; padding:10px 16px; border-bottom:1px solid rgba(255,255,255,.05)">'
      + '<div style="' + M + '; font-size:13px; color:' + farbe + '">' + zeichen + '</div>'
      + '<div><div style="font-size:12.5px; color:rgba(255,255,255,.8)">' + esc(p.regel) + '</div>'
      + (p.hinweis ? '<div style="font-size:11.5px; color:#F5A623; margin-top:4px; line-height:1.5">' + esc(p.hinweis) + '</div>' : '')
      + '</div>'
      + '<div style="' + M + '; font-size:11px; color:rgba(255,255,255,.55); text-align:right; white-space:nowrap">'
      + esc(p.ist || '') + (p.soll ? ' <span style="color:rgba(255,255,255,.35)">vs ' + esc(p.soll) + '</span>' : '')
      + '</div></div>';
  }).join('');

  return '<div style="' + karte + '; margin-top:14px; padding:18px 20px">'
    + '<div style="' + M + '; font-size:10px; letter-spacing:.14em; color:#4F8EF7">WHAT THE TEST MEASURED</div>'
    + '<div style="font-size:14.5px; color:#fff; margin-top:10px; line-height:1.6; max-width:760px">' + esc(a.befund || '') + '</div>'
    + (a.offener_ausgang
      ? '<div style="font-size:13px; color:#F5A623; margin-top:12px; line-height:1.6; max-width:760px; '
        + 'border-left:2px solid rgba(245,166,35,.4); padding-left:12px">' + esc(a.offener_ausgang) + '</div>'
      : '')
    + (punkte
      ? '<div style="' + M + '; font-size:10px; letter-spacing:.14em; color:rgba(255,255,255,.45); margin:18px 0 8px">RULE ADHERENCE</div>'
        + '<div style="border:1px solid rgba(255,255,255,.09); border-radius:10px; overflow:hidden">' + punkte + '</div>'
      : '')
    + '</div>';
}

// Pipeline forward: die Entscheidungsregel in Klartext, plus die Gruende
// aus dem tatsaechlichen Lauf. Schwellenwerte werden bewusst nicht
// hartkodiert, sie stehen je Eintrag im reason-Feld des Laufs.
const PIPELINE_GRUENDE = [
  { test: /^kein_yes_ask/, text: 'Nobody was offering that side at all' },
  { test: /^kein_no_ask/, text: 'Nobody was offering the no side' },
  { test: /^yes_ask|^vollpreis/, text: 'Price including fee sat above the run cap' },
  { test: /^count|^endstand/, text: 'Word count had not passed the market threshold' },
  { test: /^skip/, text: 'Market was skipped before pricing' },
  { test: /^kein_vollpass|^verschreibungs/, text: 'Transcript was not clean enough to bet on absence' }
];

function pipelineRegelnHtml(payload) {
  const eintraege = (payload && payload.eintraege) || [];
  if (!eintraege.length) return '';
  const karte = 'background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:12px';

  const zaehler = new Map();
  let sonstige = 0;
  eintraege.forEach((e) => {
    const grund = String(e.reason || '');
    const treffer = PIPELINE_GRUENDE.find((g) => g.test.test(grund));
    if (treffer) zaehler.set(treffer.text, (zaehler.get(treffer.text) || 0) + 1);
    else if (grund) sonstige += 1;
  });
  if (sonstige) zaehler.set('Other reasons', sonstige);
  const gesamt = eintraege.length;
  const gekauft = eintraege.filter((e) => String(e.action || '').toUpperCase() !== 'NONE').length;

  const regel = (titel, text) =>
    '<div style="padding:12px 16px; border-bottom:1px solid rgba(255,255,255,.05)">'
    + '<div style="' + M + '; font-size:10px; letter-spacing:.12em; color:#4F8EF7">' + esc(titel) + '</div>'
    + '<div style="font-size:12.5px; color:rgba(255,255,255,.75); margin-top:6px; line-height:1.6">' + esc(text) + '</div></div>';

  const zeilen = [...zaehler.entries()].sort((a, b) => b[1] - a[1]).map(([text, n]) =>
    '<div style="display:grid; grid-template-columns:1fr auto auto; gap:12px; align-items:baseline; padding:9px 16px; border-bottom:1px solid rgba(255,255,255,.05)">'
    + '<div style="font-size:12.5px; color:rgba(255,255,255,.75)">' + esc(text) + '</div>'
    + '<div style="' + M + '; font-size:12px; color:#fff">' + n + '</div>'
    + '<div style="' + M + '; font-size:11px; color:rgba(255,255,255,.4); width:46px; text-align:right">'
    + Math.round((n / gesamt) * 100) + '%</div></div>'
  ).join('');

  return '<div style="' + karte + '; margin-top:14px; padding:18px 20px">'
    + '<div style="' + M + '; font-size:10px; letter-spacing:.14em; color:#4F8EF7">HOW THE PIPELINE DECIDES</div>'
    + '<div style="font-size:13.5px; color:rgba(255,255,255,.65); margin-top:10px; line-height:1.6; max-width:760px">'
    + 'These are word-count markets: will a speaker say a given word often enough during an earnings call. '
    + 'The pipeline follows the live transcript and counts. It never predicts what will be said, it acts only on what has already been said.</div>'
    + '<div style="border:1px solid rgba(255,255,255,.09); border-radius:10px; overflow:hidden; margin-top:14px">'
    + regel('BUY YES', 'Only once the live count has already passed the market threshold, so the outcome is settled in fact, and only while the price including fee stays under the run cap. Above the cap there is no margin left in a decided outcome.')
    + regel('BUY NO', 'Only after the full transcript, when the final count stayed far enough below the threshold, and only at a lower cap than YES. Betting on absence breaks on a single missed word, so it needs the bigger cushion.')
    + regel('OTHERWISE NOTHING', 'Every other case is a no-trade, and each entry carries the reason that stopped it. The thresholds themselves are shown per entry, not fixed here.')
    + '</div>'
    + '<div style="' + M + '; font-size:10px; letter-spacing:.14em; color:rgba(255,255,255,.45); margin:18px 0 8px">'
    + 'WHY IT DID NOT TRADE · ' + gesamt + ' decisions, ' + gekauft + ' acted on</div>'
    + '<div style="border:1px solid rgba(255,255,255,.09); border-radius:10px; overflow:hidden">' + zeilen + '</div>'
    + '</div>';
}

function studyTableHtml(T, label, cols, head, rows) {
  const headStyle = 'display:grid; grid-template-columns:' + cols + '; gap:14px; padding:9px 18px; border-bottom:1px solid rgba(255,255,255,.09); ' + M + '; font-size:9.5px; letter-spacing:.14em; color:rgba(255,255,255,.45)';
  return '<div style="border:1px solid rgba(255,255,255,.09); border-radius:12px; margin-top:14px; overflow:hidden">'
    + '<div style="padding:11px 18px; background:#10151A; border-bottom:1px solid rgba(255,255,255,.09); ' + M + '; font-size:10.5px; letter-spacing:.14em; color:#4F8EF7">' + esc(label) + '</div>'
    + '<div style="' + headStyle + '">'
    + head.map((h, i) => '<div style="' + (i === 0 ? '' : 'text-align:right') + '">' + esc(h) + '</div>').join('')
    + '</div>'
    + rows.map((row) =>
      '<div style="display:grid; grid-template-columns:' + cols + '; gap:14px; align-items:center; padding:11px 18px; border-bottom:1px solid rgba(255,255,255,.06)">'
      + row.map((cell, i) => {
        const first = i === 0;
        const cs = String(cell);
        const neg = cs.charAt(0) === '-' && cs.indexOf('$') > 0;
        const pos = cs.charAt(0) === '+' && cs.indexOf('$') > 0;
        const style = (first ? 'font-family:Inter,sans-serif; font-size:13px' : M + '; font-size:12.5px; text-align:right') + '; color:' + (neg ? '#FF4545' : pos ? '#C8F542' : first ? '#ffffff' : 'rgba(255,255,255,.7)') + '; white-space:nowrap; overflow:hidden; text-overflow:ellipsis';
        return '<div style="' + style + '">' + esc(cs) + '</div>';
      }).join('')
      + '</div>'
    ).join('')
    + '</div>';
}

function buildStudyTable(T, tab, payload) {
  // Keine Demo-Tabelle als Rueckfall: eine erfundene Zeile in einer
  // Belegtabelle ist genau die Sorte Zahl, die auf einem Floor die
  // Glaubwuerdigkeit der echten Zeilen mitnimmt.
  if (!payload) return '';
  try {
    if (tab === 0 && payload.faelle) {
      return studyTableHtml(T, 'OPEN CASES', '110px 1fr 130px 130px 140px', ['CASE','MARKET','BAND','DISCOUNT','RECOMMENDATION'],
        payload.faelle.slice(0, 12).map((f) => [String(f.id), String(f.markt_slug || ''), String(f.score_band || ''), String(f.skeptic_abschlag != null ? f.skeptic_abschlag : '—'), String(f.empfehlung || '')]));
    }
    if (tab === 1 && payload.kategorien) {
      return studyTableHtml(T, 'BY CATEGORY', '1fr 110px 130px 120px 130px', ['CATEGORY','BRIER T-7','BRIER T-1','MARKETS','HIT RATE T-7'],
        payload.kategorien.map((k) => [String(k.kategorie), (+k.brier_t7).toFixed(3), (+k.brier_t1).toFixed(3), num(k.n_maerkte), Math.round((+k.trefferquote_t7) * 100) + '%']));
    }
    if (tab === 2 && payload.faelle) {
      return studyTableHtml(T, 'MENTIONS EVENTS', '1fr 130px 130px 130px 110px', ['EVENT','FIRST REACTION','CONVERGENCE','WINDOW (H)','STATUS'],
        payload.faelle.map((f) => [String(f.event), f.minuten_bis_erste_reaktion != null ? f.minuten_bis_erste_reaktion + ' min' : '—', f.minuten_bis_konvergenz != null ? f.minuten_bis_konvergenz + ' min' : '—', String(f.stunden_im_handelbaren_fenster != null ? f.stunden_im_handelbaren_fenster : '—'), String(f.status || '')]));
    }
    if (tab === 5 && payload.trades) {
      return studyTableHtml(T, 'PILOT TRADES', '110px 1fr 90px 110px 110px', ['DATE','MARKET','ARM','SIZE','EXIT'],
        payload.trades.slice(0, 12).map((t) => [String(t.zeitstempel_utc || '').slice(0, 10), String(t.markt_frage || ''), String(t.arm || ''), '$' + (+t.groesse_usd).toFixed(0), String(t.exit_grund || 'open')]));
    }
    if (tab === 6 && payload.laeufe) {
      return studyTableHtml(T, 'FORWARD LOG', '1fr 110px 110px 140px 110px', ['RUN','ENTRIES','BUYS','EXTRACTED $','QUOTE'],
        payload.laeufe.slice(0, 12).map((l) => [String(l.profil), num(l.n_eintraege), num(l.n_kaeufe), '$' + (+l.extraktion_gekauft_usd || 0).toFixed(0), l.extraktionsquote != null ? Math.round((+l.extraktionsquote) * 100) + '%' : '—']));
    }
    if (tab === 7 && payload.prompt_hashes) {
      return '';
    }
  } catch (err) { /* malformed payload — show nothing rather than fixtures */ }
  return '';
}

function buildStudyStats(tab, payload) {
  if (!payload) return null;
  try {
    if (tab === 0 && payload.faelle) {
      const high = payload.faelle.filter((f) => f.score_band === 'high').length;
      const esc2 = payload.faelle.filter((f) => f.empfehlung === 'escalate_human').length;
      return [
        { label: 'OPEN CASES', value: String(payload.faelle.length), note: high + ' high band' },
        { label: 'ESCALATED TO HUMAN', value: String(esc2), note: 'of ' + payload.faelle.length + ' raised' },
        { label: 'CHECK SOURCE', value: String(payload.faelle.filter((f) => f.empfehlung === 'check_source').length), note: 'verification steps' },
        { label: 'WATCH ONLY', value: String(payload.faelle.filter((f) => f.empfehlung === 'watch').length), note: 'no action needed' }
      ];
    }
    if (tab === 1 && payload.kategorien && payload.kategorien.length) {
      const sorted = payload.kategorien.slice().sort((a, b) => a.brier_t7 - b.brier_t7);
      const total = payload.kategorien.reduce((a, k) => a + (+k.n_maerkte || 0), 0);
      return [
        { label: 'BEST CATEGORY', value: String(sorted[0].kategorie), note: 'Brier ' + (+sorted[0].brier_t7).toFixed(3) },
        { label: 'WORST CATEGORY', value: String(sorted[sorted.length - 1].kategorie), note: 'Brier ' + (+sorted[sorted.length - 1].brier_t7).toFixed(3) },
        { label: 'MARKETS IN SAMPLE', value: num(total), note: 'resolved only' },
        { label: 'CATEGORIES', value: String(payload.kategorien.length), note: 'tracked' }
      ];
    }
    if (tab === 2 && payload.faelle && payload.faelle.length) {
      const reactions = payload.faelle.map((f) => +f.minuten_bis_erste_reaktion).filter((v) => !isNaN(v)).sort((a, b) => a - b);
      const median = reactions.length ? reactions[Math.floor(reactions.length / 2)] : null;
      const none = payload.faelle.filter((f) => f.minuten_bis_erste_reaktion == null).length;
      return [
        { label: 'MEDIAN LATENCY', value: median != null ? median + ' min' : '—', note: 'n = ' + payload.faelle.length },
        { label: 'FASTEST', value: reactions.length ? reactions[0] + ' min' : '—', note: 'first reaction' },
        { label: 'SLOWEST', value: reactions.length ? reactions[reactions.length - 1] + ' min' : '—', note: 'first reaction' },
        { label: 'NO REACTION', value: String(none), note: 'never moved 2¢' }
      ];
    }
    if (tab === 5 && payload.trades) {
      const p = payload.protokoll || {};
      const a = payload.auswertung;
      if (a && a.trades && a.trades.gesamt) {
        const sl = a.slippage || {};
        const rt = a.regeltreue || {};
        const cents = (v) => (v == null ? '—' : (v >= 0 ? '+' : '') + (v * 100).toFixed(2) + '¢');
        return [
          { label: 'STATUS', value: a.phase === 'entry_open' ? 'Open' : (a.phase === 'resolved' ? 'Resolved' : 'Entry closed'), note: 'window to ' + String(a.fenster_bis || '—') },
          { label: 'TRADES PLACED', value: String(a.trades.gesamt), note: a.trades.offen + ' still open · $' + (a.trades.kapital_usd || 0) + ' deployed' },
          { label: 'MEAN SLIPPAGE', value: cents(sl.mittel), note: (sl.teurer_als_signal || 0) + ' of ' + (sl.n || 0) + ' worse than signal' },
          { label: 'RULE ADHERENCE', value: (rt.erfuellt != null ? rt.erfuellt + ' / ' + rt.gesamt : '—'), note: 'checks passed' }
        ];
      }
      return [
        { label: 'TRADES', value: String(payload.trades.length), note: 'all manual' },
        { label: 'BUDGET', value: '$' + (p.budget_usdc != null ? p.budget_usdc : '—'), note: 'preregistered' },
        { label: 'STAKE PER TRADE', value: '$' + (p.einsatz_je_trade_usdc != null ? p.einsatz_je_trade_usdc : '—'), note: 'fixed' },
        { label: 'RULES FROZEN', value: String(p.regel_freeze_datum || '—'), note: 'before first trade' }
      ];
    }
    if (tab === 6 && payload.laeufe) {
      const entries = payload.laeufe.reduce((a, l) => a + (+l.n_eintraege || 0), 0);
      const buys = payload.laeufe.reduce((a, l) => a + (+l.n_kaeufe || 0), 0);
      return [
        { label: 'RUNS', value: String(payload.laeufe.length), note: 'forward, no edits' },
        { label: 'ENTRIES', value: num(entries), note: 'auto-published' },
        // Kein DRIFT-Feld mehr: der Wert war das Literal 'none', ohne dass
        // irgendetwas verglichen wurde. Stattdessen die Quote, die aus den
        // Laeufen tatsaechlich hervorgeht.
        { label: 'BUY DECISIONS', value: num(buys), note: entries ? Math.round((buys / entries) * 100) + '% of ' + num(entries) + ' entries' : 'of ' + num(entries) + ' entries' }
      ];
    }
    if (tab === 7 && payload.n_eintraege != null) {
      // Frueher stand hier HASH CHAIN 'intact'. Das war ein fest verdrahteter
      // String, und die Nutzlast traegt zwei flache Hash-Listen ohne
      // Vorgaengerverweise, also gar keine Kette, die man pruefen koennte.
      // Gezeigt wird jetzt, was die Datei wirklich hergibt.
      const backends = Object.entries(payload.backend_zaehler || {});
      const backend = backends.length
        ? backends.sort((a, b) => b[1] - a[1])[0]
        : ['—', 0];
      return [
        { label: 'AUDIT ENTRIES', value: num(payload.n_eintraege), note: 'roles and counters only' },
        { label: 'PROMPT HASHES', value: num((payload.prompt_hashes || []).length), note: 'SHA-256, no prompt text' },
        { label: 'OUTPUT HASHES', value: num((payload.output_hashes || []).length), note: 'SHA-256, no output text' },
        { label: 'BACKEND', value: String(backend[0]), note: backend[0] === 'mock' ? 'not a live model run' : num(backend[1]) + ' of ' + num(payload.n_eintraege) }
      ];
    }
  } catch (err) { /* malformed payload */ }
  return null;
}

// ---------------------------------------------------------------- live runs (research tab 3)
function renderLiveRuns(T, payload) {
  const s = T.state;
  const agg = payload && payload.aggregat ? payload.aggregat : null;
  const stamp = payload && payload.stand_utc ? String(payload.stand_utc).slice(0, 10) : 'rolling';

  const kpis = agg ? [
    { label: 'RUNS', value: String(agg.n_runs), sub: 'one run = one episode', color: '#ffffff' },
    { label: 'BETS', value: num(agg.n_wetten), sub: agg.gewonnen + 'W · ' + agg.verloren + 'L · ' + agg.offen + ' open', color: '#ffffff' },
    { label: 'TOTAL STAKE', value: '$' + num((+agg.einsatz_usd).toFixed(0)), sub: 'wallet-reconciled', color: '#ffffff' },
    { label: 'REALIZED PNL', value: (agg.realisierter_pnl_usd >= 0 ? '+$' : '-$') + num(Math.abs(+agg.realisierter_pnl_usd).toFixed(0)), sub: 'wallet-reconciled · ' + (agg.wallet_abgleich_stand || ''), color: agg.realisierter_pnl_usd >= 0 ? '#C8F542' : '#FF4545' },
    { label: 'OPEN STAKE', value: '$' + num((+agg.offener_einsatz_usd).toFixed(0)), sub: 'in unresolved markets', color: '#ffffff' }
  ] : [
    // Kein Rueckfall auf 64 Laeufe, 1.208 Wetten und eine Trefferquote von
    // 54 Prozent. Die Zahlen stehen in runs.json oder nirgends.
    { label: 'RUNS', value: '—', sub: 'runs.json not loaded', color: '#ffffff' },
    { label: 'BETS', value: '—', sub: 'runs.json not loaded', color: '#ffffff' },
    { label: 'TOTAL STAKE', value: '—', sub: 'runs.json not loaded', color: '#ffffff' },
    { label: 'REALIZED PNL', value: '—', sub: 'runs.json not loaded', color: '#ffffff' },
    { label: 'OPEN STAKE', value: '—', sub: 'runs.json not loaded', color: '#ffffff' }
  ];
  const laufSatz = herkunftSatz(
    payload ? { quelle: payload._quelle === 'fehler' ? 'fehler' : 'leer', fehler: payload._fehler } : null,
    'public/data/runs.json');

  const cards = payload && payload.runs ? payload.runs.slice(0, 12).map((r) => {
    const bets = (r.wetten || []).map((b) => ({
      market: b.frage, side: b.seite === 'YES' ? 'Yes' : 'No',
      limit: (+b.entscheidungs_preis).toFixed(2), fill: b.avg_fill_preis != null ? (+b.avg_fill_preis).toFixed(2) : '—',
      stake: '$' + (+b.einsatz_usd).toFixed(2),
      result: !b.aufgeloest ? 'open' : (b.pnl_usd >= 0 ? '+$' : '-$') + Math.abs(+b.pnl_usd).toFixed(2)
    }));
    const chips = [];
    if (r.drop_erkannt_utc) chips.push('drop ' + String(r.drop_erkannt_utc).slice(11, 19));
    if (r.erster_fill_s != null) chips.push('fill +' + (+r.erster_fill_s).toFixed(1) + ' s');
    if (r.n_entscheidungen != null) chips.push(num(r.n_entscheidungen) + ' decisions');
    if (r.eingepreist != null) chips.push(num(r.eingepreist) + ' priced in');
    if (r.einsatz_zu_sichtbarer_tiefe_pct != null) chips.push('stake ' + (+r.einsatz_zu_sichtbarer_tiefe_pct).toFixed(0) + '% of visible depth');
    const resolvedAll = bets.length && bets.every((b) => b.result !== 'open');
    const missedN = (r.verpasste_chancen || []).length;
    return {
      profile: String(r.profil || '').toUpperCase(), mode: String(r.modus || '').toUpperCase() === 'LIVE' ? 'REAL ORDERS' : 'DRY RUN',
      status: bets.length === 0 ? 'NO FILLS' : resolvedAll ? 'RESOLVED' : 'OPEN',
      title: r.episode_titel || r.profil, chips, bets,
      footer: 'Stake $' + (+r.einsatz_usd).toFixed(2) + ' (log est.) · wallet net ' + (r.realisierter_pnl_usd >= 0 ? '+$' : '-$') + Math.abs(+r.realisierter_pnl_usd).toFixed(2),
      missed: missedN ? 'Missed chances (' + missedN + ') — budget or cap' : ''
    };
  }) : [];

  const timingRows = payload && payload.runs ? payload.runs.flatMap((r) =>
    (r.wetten || []).filter((b) => b.fill_ts_utc).map((b) => ({
      run: String(r.profil || '').slice(0, 10),
      market: b.frage,
      drop: r.drop_erkannt_utc ? String(r.drop_erkannt_utc).slice(11, 19) : '—',
      fill: String(b.fill_ts_utc).slice(11, 19),
      lat: r.erster_fill_s != null ? Math.round(+r.erster_fill_s * 1000) : null,
      before: b.fremde_davor != null ? String(b.fremde_davor) : '—',
      next: b.verfolger_s != null ? '+' + (+b.verfolger_s).toFixed(1) + ' s' : '—',
      rep: b.preis_nach_fill_30s != null && b.avg_fill_preis != null ? Math.round((b.preis_nach_fill_30s - b.avg_fill_preis) * 100) : null
    }))
  ).slice(0, 20) : [];

  const liveTabs = [['runs','Runs'],['timing','Timing & repricing'],['sim','Sizing simulator'],['calib','Calibration'],['record','Track record']].map((o) => T.tab(o[1], s.liveTab === o[0], { liveTab: o[0] })).join('');

  let body = '';
  if (s.liveTab === 'runs') {
    body = '<div style="margin-top:14px">'
      + '<div style="font-size:12.5px; color:rgba(255,255,255,.5); line-height:1.5; max-width:820px; margin-bottom:14px">Race chips compare each fill against the public taker tape of that market: how many other trades hit between the drop and our fill, and how long until the next trader after us. The anchor is the bot\'s logged fill time — chain timestamps can differ by a few seconds.</div>'
      + (cards.length ? '' : leerZeile(laufSatz))
      + '<div style="display:flex; flex-direction:column; gap:12px">'
      + cards.map((r) => {
        const statusStyle = M + '; font-size:9.5px; letter-spacing:.1em; border-radius:4px; padding:3px 8px; ' + (r.status === 'RESOLVED' ? 'color:rgba(255,255,255,.6); border:1px solid rgba(255,255,255,.18)' : r.status === 'OPEN' ? 'color:#F5A623; border:1px solid rgba(245,166,35,.4)' : 'color:rgba(255,255,255,.4); border:1px solid rgba(255,255,255,.12)');
        return '<div style="background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:12px; padding:16px 18px">'
          + '<div style="display:flex; gap:7px; flex-wrap:wrap">'
          + '<div style="' + M + '; font-size:9.5px; letter-spacing:.1em; border-radius:4px; padding:3px 8px; color:#4F8EF7; border:1px solid rgba(79,142,247,.4)">' + esc(r.profile) + '</div>'
          + '<div style="' + M + '; font-size:9.5px; letter-spacing:.1em; border-radius:4px; padding:3px 8px; color:#4F8EF7; border:1px solid rgba(79,142,247,.4)">' + esc(r.mode) + '</div>'
          + '<div style="' + statusStyle + '">' + esc(r.status) + '</div></div>'
          + '<div style="font-size:15px; font-weight:600; margin-top:11px">' + esc(r.title) + ' <span style="' + M + '; font-size:11px; color:rgba(255,255,255,.4)">event ↗</span></div>'
          + '<div style="display:flex; gap:7px; flex-wrap:wrap; margin-top:10px">'
          + r.chips.map((c) => '<div style="' + M + '; font-size:10.5px; color:rgba(255,255,255,.65); background:#161C22; border:1px solid rgba(255,255,255,.09); border-radius:5px; padding:4px 9px">' + esc(c) + '</div>').join('')
          + '</div>'
          + '<div style="margin-top:12px; border-top:1px solid rgba(255,255,255,.07)">'
          + r.bets.map((b) =>
            '<div style="display:grid; grid-template-columns:1fr 62px 78px 78px 80px 92px; gap:10px; align-items:center; padding:9px 0; border-bottom:1px solid rgba(255,255,255,.05); ' + M + '; font-size:11.5px">'
            + '<div style="font-family:\'Inter\',sans-serif; font-size:12.5px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis">' + esc(b.market) + '</div>'
            + '<div style="' + M + '; font-size:11.5px; color:' + (b.side === 'Yes' ? '#C8F542' : '#4F8EF7') + '">' + b.side + '</div>'
            + '<div style="text-align:right; color:rgba(255,255,255,.55)">limit ' + b.limit + '</div>'
            + '<div style="text-align:right; color:rgba(255,255,255,.55)">fill ' + b.fill + '</div>'
            + '<div style="text-align:right">' + b.stake + '</div>'
            + '<div style="text-align:right; ' + M + '; font-size:12px; color:' + (b.result.charAt(0) === '+' ? '#C8F542' : b.result === 'open' ? 'rgba(255,255,255,.5)' : '#FF4545') + '">' + b.result + '</div></div>'
          ).join('')
          + '</div>'
          + '<div style="' + M + '; font-size:11px; color:rgba(255,255,255,.45); margin-top:10px">' + esc(r.footer) + '</div>'
          + (r.missed ? '<div style="' + M + '; font-size:11px; color:#F5A623; margin-top:7px">' + esc(r.missed) + '</div>' : '')
          + '</div>';
      }).join('')
      + '</div></div>';
  } else if (s.liveTab === 'timing') {
    body = '<div style="border:1px solid rgba(255,255,255,.09); border-radius:12px; margin-top:14px; overflow:hidden">'
      + '<div style="padding:11px 16px; background:#10151A; border-bottom:1px solid rgba(255,255,255,.09); ' + M + '; font-size:10.5px; letter-spacing:.14em; color:#4F8EF7">TIMING AND REPRICING PER FILL</div>'
      + '<div style="display:grid; grid-template-columns:80px 1fr 90px 90px 100px 118px 106px 106px; gap:10px; padding:9px 16px; border-bottom:1px solid rgba(255,255,255,.09); ' + M + '; font-size:9px; letter-spacing:.12em; color:rgba(255,255,255,.45)">'
      + '<div>RUN</div><div>MARKET</div><div style="text-align:right">DROP</div><div style="text-align:right">FILL</div><div style="text-align:right">LATENCY</div><div style="text-align:right">TRADES BEFORE US</div><div style="text-align:right">NEXT TRADER</div><div style="text-align:right">REPRICE 30S</div></div>'
      + (timingRows.length ? '' : leerZeile(laufSatz))
      + timingRows.map((t) => {
        const latLabel = t.lat == null ? '—' : t.lat >= 1000 ? (t.lat / 1000).toFixed(1) + ' s' : t.lat + ' ms';
        const latStyle = 'text-align:right; ' + M + '; font-size:12px; color:' + (t.lat == null ? 'rgba(255,255,255,.5)' : t.lat <= 800 ? '#C8F542' : t.lat <= 1500 ? '#F5A623' : '#FF4545');
        const repLabel = t.rep == null ? '—' : (t.rep >= 0 ? '+' : '') + t.rep + '¢';
        const repStyle = 'text-align:right; ' + M + '; font-size:12px; color:' + (t.rep != null && t.rep >= 5 ? '#C8F542' : 'rgba(255,255,255,.6)');
        return '<div style="display:grid; grid-template-columns:80px 1fr 90px 90px 100px 118px 106px 106px; gap:10px; align-items:center; padding:11px 16px; border-bottom:1px solid rgba(255,255,255,.06); ' + M + '; font-size:12px">'
          + '<div style="color:rgba(255,255,255,.55)">' + esc(t.run) + '</div>'
          + '<div style="font-family:\'Inter\',sans-serif; font-size:12.5px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis">' + esc(t.market) + '</div>'
          + '<div style="text-align:right; color:rgba(255,255,255,.55)">' + esc(t.drop) + '</div>'
          + '<div style="text-align:right; color:rgba(255,255,255,.55)">' + esc(t.fill) + '</div>'
          + '<div style="' + latStyle + '">' + latLabel + '</div>'
          + '<div style="text-align:right; color:rgba(255,255,255,.7)">' + esc(String(t.before)) + '</div>'
          + '<div style="text-align:right; color:rgba(255,255,255,.7)">' + esc(t.next) + '</div>'
          + '<div style="' + repStyle + '">' + repLabel + '</div></div>';
      }).join('')
      + '</div>';
  } else if (s.liveTab === 'sim') {
    const extras = payload && payload.extras;
    const liveSims = extras && extras.sims && extras.sims.length
      ? extras.sims.map((v) => ({ name: v.name, net: v.net, roi: v.roi, dd: null, hit: null, bets: v.bets }))
      : null;
    const simRows = liveSims || [];
    body = '<div style="margin-top:14px">'
      + '<div style="font-size:12.5px; color:rgba(255,255,255,.55); line-height:1.5; max-width:820px">Replays the same runs with a different stake rule each time — same entries, same fills, only the size changes. Caps and the per-run budget stay as they were on the day.' + (liveSims ? ' Only resolved bets with a valid fill price count; bankroll $100, no compounding.' : '') + '</div>'
      + '<div style="border:1px solid rgba(255,255,255,.09); border-radius:12px; margin-top:14px; overflow:hidden">'
      + '<div style="display:grid; grid-template-columns:1fr 110px 96px 96px 96px 104px; gap:10px; padding:9px 16px; background:#10151A; border-bottom:1px solid rgba(255,255,255,.09); ' + M + '; font-size:9px; letter-spacing:.12em; color:rgba(255,255,255,.45)">'
      + '<div>STAKE RULE</div><div style="text-align:right">NET</div><div style="text-align:right">ROI</div><div style="text-align:right">MAX DD</div><div style="text-align:right">HIT RATE</div><div style="text-align:right">BETS PLACED</div></div>'
      + (simRows.length ? '' : leerZeile(laufSatz))
      + simRows.slice().sort((a, b) => b.roi - a.roi).map((r, i) =>
        '<div style="display:grid; grid-template-columns:1fr 110px 96px 96px 96px 104px; gap:10px; align-items:center; padding:11px 16px; border-bottom:1px solid rgba(255,255,255,.06); background:' + (i === 0 ? 'rgba(200,245,66,.06)' : 'transparent') + '">'
        + '<div style="font-size:12.5px; color:' + (i === 0 ? '#C8F542' : '#ffffff') + '">' + esc(r.name) + '</div>'
        + '<div style="text-align:right; ' + M + '; font-size:12.5px; color:' + (r.net >= 0 ? '#C8F542' : '#FF4545') + '">' + (r.net >= 0 ? '+$' : '-$') + num(Math.abs(r.net).toFixed(0)) + '</div>'
        + '<div style="text-align:right; ' + M + '; font-size:12.5px; color:' + (r.roi >= 0 ? '#C8F542' : '#FF4545') + '">' + (r.roi >= 0 ? '+' : '') + r.roi.toFixed(1) + '%</div>'
        + '<div style="text-align:right; ' + M + '; font-size:12.5px; color:rgba(255,255,255,.6)">' + (r.dd != null ? r.dd.toFixed(1) + '%' : '—') + '</div>'
        + '<div style="text-align:right; ' + M + '; font-size:12.5px; color:rgba(255,255,255,.6)">' + (r.hit != null ? r.hit + '%' : '—') + '</div>'
        + '<div style="text-align:right; ' + M + '; font-size:12.5px; color:rgba(255,255,255,.6)">' + num(r.bets) + '</div></div>'
      ).join('')
      + '</div>'
      + (liveSims && extras.timing_decay && extras.timing_decay.length
        ? '<div style="border:1px solid rgba(255,255,255,.09); border-radius:12px; margin-top:14px; overflow:hidden">'
          + '<div style="padding:11px 16px; background:#10151A; border-bottom:1px solid rgba(255,255,255,.09); ' + M + '; font-size:10.5px; letter-spacing:.14em; color:#4F8EF7">SAME MODEL, DELAYED ENTRY — PNL DECAY BY DELAY</div>'
          + '<div style="display:grid; grid-template-columns:1fr 110px 130px 120px 130px 130px; gap:10px; padding:9px 16px; border-bottom:1px solid rgba(255,255,255,.09); ' + M + '; font-size:9px; letter-spacing:.12em; color:rgba(255,255,255,.45)">'
          + '<div>DELAY</div><div style="text-align:right">BETS</div><div style="text-align:right">FOREIGN REF</div><div style="text-align:right">PRICED OUT</div><div style="text-align:right">SIM PNL</div><div style="text-align:right">VS INSTANT</div></div>'
          + extras.timing_decay.map((t) =>
            '<div style="display:grid; grid-template-columns:1fr 110px 130px 120px 130px 130px; gap:10px; align-items:center; padding:10px 16px; border-bottom:1px solid rgba(255,255,255,.06); ' + M + '; font-size:12px">'
            + '<div style="font-family:\'Inter\',sans-serif; font-size:12.5px">+' + t.delay_s + ' s</div>'
            + '<div style="text-align:right; color:rgba(255,255,255,.6)">' + t.n_bets + '</div>'
            + '<div style="text-align:right; color:rgba(255,255,255,.6)">' + t.n_foreign_ref + '</div>'
            + '<div style="text-align:right; color:rgba(255,255,255,.6)">' + t.n_priced_out + '</div>'
            + '<div style="text-align:right; color:' + (t.sim_pnl_usd >= 0 ? '#C8F542' : '#FF4545') + '">' + (t.sim_pnl_usd >= 0 ? '+$' : '-$') + Math.abs(t.sim_pnl_usd).toFixed(2) + '</div>'
            + '<div style="text-align:right; color:' + (t.pnl_delta_usd >= 0 ? 'rgba(255,255,255,.6)' : '#FF4545') + '">' + (t.pnl_delta_usd >= 0 ? '+$' : '-$') + Math.abs(t.pnl_delta_usd).toFixed(2) + '</div></div>'
          ).join('')
          + '</div>'
        // Hier liefen zwei Zufallskurven mit eingebautem Aufwaertsdrift unter
        // der Ueberschrift FLAT $25 VERSUS THE BEST RULE. Eine gemalte Kurve
        // ist eine Behauptung; ohne timing_decay in der Nutzlast gibt es
        // keine.
        : '<div style="background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:12px; margin-top:14px; padding:16px 18px">'
          + '<div style="' + M + '; font-size:10.5px; letter-spacing:.14em; color:rgba(255,255,255,.55); margin-bottom:10px">DELAYED ENTRY</div>'
          + '<div style="font-size:12.5px; color:rgba(255,255,255,.5); line-height:1.5">'
          + 'No delay series in this payload — runs.json carries it under extras.timing_decay.</div></div>')
      + '</div>';
  } else if (s.liveTab === 'calib') {
    const extras = payload && payload.extras;
    const calibRows = extras && extras.calibration && extras.calibration.rows && extras.calibration.rows.length
      ? extras.calibration.rows
      : payload && payload.runs ? buildCalibFromRuns(payload.runs) : [];
    const calibNote = extras && extras.calibration
      ? ' n = ' + extras.calibration.n + (extras.calibration.hit_low != null ? ' · hit rate ' + Math.round(extras.calibration.hit_rate * 100) + '% [' + Math.round(extras.calibration.hit_low * 100) + '–' + Math.round(extras.calibration.hit_high * 100) + '%] Wilson 95%' : '') + (extras.calibration.sample_ok ? '' : ' · sample below the minimum — read with care')
      : '';
    body = '<div style="margin-top:14px">'
      + '<div style="font-size:12.5px; color:rgba(255,255,255,.55); line-height:1.5; max-width:820px">Entry price against what actually happened. A perfectly calibrated entry sits on the diagonal — above it means we paid too much.' + esc(calibNote) + '</div>'
      + '<div style="border:1px solid rgba(255,255,255,.09); border-radius:12px; margin-top:14px; overflow:hidden">'
      + '<div style="display:grid; grid-template-columns:1fr 90px 110px 110px 110px; gap:10px; padding:9px 16px; background:#10151A; border-bottom:1px solid rgba(255,255,255,.09); ' + M + '; font-size:9px; letter-spacing:.12em; color:rgba(255,255,255,.45)">'
      + '<div>ENTRY PRICE BAND</div><div style="text-align:right">BETS</div><div style="text-align:right">PAID</div><div style="text-align:right">SETTLED</div><div style="text-align:right">GAP</div></div>'
      + (calibRows.length ? '' : leerZeile(laufSatz))
      + calibRows.map((c) => {
        const gap = c.settled - c.paid;
        return '<div style="display:grid; grid-template-columns:1fr 90px 110px 110px 110px; gap:10px; align-items:center; padding:11px 16px; border-bottom:1px solid rgba(255,255,255,.06); ' + M + '; font-size:12.5px">'
          + '<div style="font-family:\'Inter\',sans-serif; font-size:13px">' + c.band + '</div>'
          + '<div style="text-align:right; color:rgba(255,255,255,.6)">' + num(c.n) + '</div>'
          + '<div style="text-align:right">' + c.paid + '¢</div>'
          + '<div style="text-align:right">' + c.settled + '¢</div>'
          + '<div style="text-align:right; ' + M + '; font-size:12.5px; color:' + (gap >= 0 ? '#C8F542' : '#FF4545') + '">' + (gap >= 0 ? '+' : '') + gap + '¢</div></div>';
      }).join('')
      + '</div></div>';
  } else {
    const extras = payload && payload.extras;
    const monthRows = extras && extras.monthly ? extras.monthly : [];
    body = '<div style="border:1px solid rgba(255,255,255,.09); border-radius:12px; margin-top:14px; overflow:hidden">'
      + '<div style="padding:11px 16px; background:#10151A; border-bottom:1px solid rgba(255,255,255,.09); ' + M + '; font-size:10.5px; letter-spacing:.14em; color:#4F8EF7">MONTH BY MONTH</div>'
      + '<div style="display:grid; grid-template-columns:1fr 90px 110px 110px 110px 100px; gap:10px; padding:9px 16px; border-bottom:1px solid rgba(255,255,255,.09); ' + M + '; font-size:9px; letter-spacing:.12em; color:rgba(255,255,255,.45)">'
      + '<div>MONTH</div><div style="text-align:right">RUNS</div><div style="text-align:right">BETS</div><div style="text-align:right">STAKE</div><div style="text-align:right">NET</div><div style="text-align:right">ROI</div></div>'
      + (monthRows.length ? '' : leerZeile(laufSatz))
      + monthRows.map((t) => {
        const roi = (t.net / t.stake) * 100;
        return '<div style="display:grid; grid-template-columns:1fr 90px 110px 110px 110px 100px; gap:10px; align-items:center; padding:11px 16px; border-bottom:1px solid rgba(255,255,255,.06); ' + M + '; font-size:12.5px">'
          + '<div style="font-family:\'Inter\',sans-serif; font-size:13px">' + t.month + '</div>'
          + '<div style="text-align:right; color:rgba(255,255,255,.6)">' + t.runs + '</div>'
          + '<div style="text-align:right; color:rgba(255,255,255,.6)">' + num(t.bets) + '</div>'
          + '<div style="text-align:right; color:rgba(255,255,255,.6)">$' + num(t.stake) + '</div>'
          + '<div style="text-align:right; ' + M + '; font-size:12.5px; color:' + (t.net >= 0 ? '#C8F542' : '#FF4545') + '">' + (t.net >= 0 ? '+$' : '-$') + num(Math.abs(t.net)) + '</div>'
          + '<div style="text-align:right; ' + M + '; font-size:12.5px; color:' + (roi >= 0 ? '#C8F542' : '#FF4545') + '">' + (roi >= 0 ? '+' : '') + roi.toFixed(1) + '%</div></div>';
      }).join('')
      + '</div>';
  }

  return '<div style="padding:20px 24px 26px">'
    + '<div style="display:flex; align-items:flex-start; justify-content:space-between; gap:24px">'
    + '<div style="max-width:660px">'
    + '<div style="font-size:20px; font-weight:600">Our own bot runs</div>'
    + '<div style="font-size:13.5px; color:rgba(255,255,255,.6); margin-top:8px; line-height:1.5">' + esc(payload && payload.hinweis ? payload.hinweis : 'Bets, reaction times and realized results of the research bot on mentions markets. One run is one episode or event.') + '</div></div>'
    + '<div style="display:flex; gap:8px">'
    + '<div style="' + M + '; font-size:9.5px; letter-spacing:.1em; border-radius:4px; padding:3px 8px; color:#0A0D0F; background:#C8F542">' + esc(payload && payload.kennzeichnung ? String(payload.kennzeichnung).toUpperCase() : 'LIVE / DESCRIPTIVE') + '</div>'
    + '<div style="' + M + '; font-size:10.5px; color:rgba(255,255,255,.4); border:1px solid rgba(255,255,255,.14); border-radius:6px; padding:5px 10px; white-space:nowrap">' + esc(stamp) + '</div>'
    + '</div></div>'
    + '<div style="display:grid; grid-template-columns:repeat(5,1fr); gap:12px; margin-top:18px">'
    + kpis.map((k) =>
      '<div style="background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:10px; padding:14px 16px">'
      + '<div style="' + M + '; font-size:9.5px; letter-spacing:.13em; color:rgba(255,255,255,.45)">' + k.label + '</div>'
      + '<div style="' + M + '; font-size:21px; margin-top:7px; color:' + k.color + '">' + k.value + '</div>'
      + '<div style="' + M + '; font-size:10.5px; color:rgba(255,255,255,.4); margin-top:4px">' + esc(k.sub) + '</div></div>'
    ).join('')
    + '</div>'
    + '<div style="display:flex; gap:6px; margin-top:18px; flex-wrap:wrap">' + liveTabs + '</div>'
    + body
    + '</div>';
}

function buildCalibFromRuns(runs) {
  const bands = [
    { band: 'under 20¢', lo: 0, hi: 0.2, prices: [], wins: [] },
    { band: '20–40¢', lo: 0.2, hi: 0.4, prices: [], wins: [] },
    { band: '40–60¢', lo: 0.4, hi: 0.6, prices: [], wins: [] },
    { band: '60–80¢', lo: 0.6, hi: 0.8, prices: [], wins: [] },
    { band: 'over 80¢', lo: 0.8, hi: 1.01, prices: [], wins: [] }
  ];
  runs.forEach((r) => (r.wetten || []).forEach((b) => {
    if (!b.aufgeloest || b.avg_fill_preis == null) return;
    const p = +b.avg_fill_preis;
    const band = bands.find((x) => p >= x.lo && p < x.hi);
    if (band) { band.prices.push(p); band.wins.push(b.gewonnen ? 1 : 0); }
  }));
  return bands.filter((b) => b.prices.length).map((b) => ({
    band: b.band, n: b.prices.length,
    paid: Math.round((b.prices.reduce((a, v) => a + v, 0) / b.prices.length) * 100),
    settled: Math.round((b.wins.reduce((a, v) => a + v, 0) / b.wins.length) * 100)
  }));
}

// ---------------------------------------------------------------- settings
export function renderSettings(T) {
  const s = T.state;
  const stepRow = (label, valueLabel, down, up) =>
    '<div><div style="' + LBL9 + '">' + label + '</div>'
    + '<div style="display:flex; align-items:center; gap:6px">'
    + '<div ' + T.act(down) + ' class="hv-bd35w" style="width:28px; height:32px; flex:none; border:1px solid rgba(255,255,255,.16); border-radius:7px; display:flex; align-items:center; justify-content:center; ' + M + '; font-size:14px; color:rgba(255,255,255,.7); cursor:pointer">−</div>'
    + '<div style="flex:1; background:#10151A; border:1px solid rgba(255,255,255,.16); border-radius:7px; padding:7px 8px; ' + M + '; font-size:12.5px; text-align:center">' + esc(valueLabel) + '</div>'
    + '<div ' + T.act(up) + ' class="hv-bd35w" style="width:28px; height:32px; flex:none; border:1px solid rgba(255,255,255,.16); border-radius:7px; display:flex; align-items:center; justify-content:center; ' + M + '; font-size:14px; color:rgba(255,255,255,.7); cursor:pointer">+</div></div></div>';

  const settingRows = [
    // Der Wert stand hier als "chat 4711 · verified" — eine erfundene
    // Chat-Kennung, die daneben behauptet, sie sei geprueft.
    { key: 'telegram', name: 'Telegram delivery', desc: 'Send every alert that fires to your Telegram chat.', value: 'chat id and token live in the environment, not here' },
    { key: 'autotop', name: 'Auto top-up on the paper account', desc: 'Refill the sub-account when it runs out of cash instead of skipping buys.', value: 'off by default — skipped buys stay visible' },
    { key: 'kalshi', name: 'Include Kalshi', desc: 'Pull Kalshi markets and trades alongside Polymarket.', value: 'no wallet identities available there' },
    { key: 'sports', name: 'Score sports markets for insider risk', desc: 'Sports odds and weather are excluded by default — there is nothing to know early.', value: 'leave off unless you are testing' },
    { key: 'cache', name: 'Cache API responses', desc: 'Reuse public API responses for sixty seconds.', value: '250 markets · 250 trades per pull' },
    { key: 'admin', name: 'Lock settings to allowlisted accounts', desc: 'On a public deployment only signed-in admins can change anything here.', value: 'fails closed when auth is configured' }
  ];

  return '<div>'
    + '<div style="padding:20px 24px 16px; border-bottom:1px solid rgba(255,255,255,.09)">'
    + '<div style="' + M + '; font-size:10px; letter-spacing:.18em; color:#C8F542">SETTINGS</div>'
    + '<div style="font-family:\'Instrument Serif\',serif; font-size:30px; line-height:1.1; margin-top:5px">How much data, and where it goes</div></div>'
    + '<div style="padding:20px 24px 0; max-width:1000px">'
    + '<div style="' + M + '; font-size:10.5px; letter-spacing:.14em; color:#C8F542; margin-bottom:12px">HOW MUCH DATA TO PULL</div>'
    + '<div style="display:grid; grid-template-columns:repeat(3,1fr); gap:16px">'
    + stepRow('MARKETS PER PULL', num(s.setMarketSample), () => T.setState({ setMarketSample: Math.max(50, s.setMarketSample - 50) }), () => T.setState({ setMarketSample: Math.min(2000, s.setMarketSample + 50) }))
    + stepRow('TRADES PER PULL', num(s.setTradeSample), () => T.setState({ setTradeSample: Math.max(50, s.setTradeSample - 50) }), () => T.setState({ setTradeSample: Math.min(2000, s.setTradeSample + 50) }))
    + stepRow('WHALE THRESHOLD', '$' + num(s.setWhale), () => T.setState({ setWhale: Math.max(500, s.setWhale - 500) }), () => T.setState({ setWhale: s.setWhale + 500 }))
    + '</div>'
    + '<div style="font-size:11.5px; color:rgba(255,255,255,.45); margin-top:9px; line-height:1.5">Bigger samples mean slower pages. The whale threshold decides what counts as a large print everywhere in the terminal.</div>'
    + '<div style="' + M + '; font-size:10.5px; letter-spacing:.14em; color:#C8F542; margin:22px 0 12px">BACKTESTER DEFAULTS</div>'
    + '<div style="display:grid; grid-template-columns:repeat(3,1fr); gap:16px">'
    + stepRow('BANKROLL', '$' + num(s.setBankroll), () => T.setState({ setBankroll: Math.max(100, s.setBankroll - 500) }), () => T.setState({ setBankroll: s.setBankroll + 500 }))
    + stepRow('FEE (BPS)', s.setFee + ' bps', () => T.setState({ setFee: Math.max(0, s.setFee - 5) }), () => T.setState({ setFee: s.setFee + 5 }))
    + stepRow('SLIPPAGE (BPS)', s.setSlip + ' bps', () => T.setState({ setSlip: Math.max(0, s.setSlip - 5) }), () => T.setState({ setSlip: s.setSlip + 5 }))
    + '</div>'
    + '<div style="' + M + '; font-size:10.5px; letter-spacing:.14em; color:#C8F542; margin:22px 0 12px">SWITCHES</div>'
    + '</div>'
    + '<div style="padding:20px 24px; display:grid; grid-template-columns:repeat(2,1fr); gap:16px; max-width:1000px">'
    + settingRows.map((o) => {
      const on = !!s.settingsOn[o.key];
      return '<div style="background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:12px; padding:16px 18px">'
        + '<div style="display:flex; align-items:center; justify-content:space-between; gap:14px">'
        + '<div><div style="font-size:14.5px; font-weight:600">' + o.name + '</div>'
        + '<div style="font-size:12.5px; color:rgba(255,255,255,.55); margin-top:6px; line-height:1.45">' + o.desc + '</div></div>'
        + '<div ' + T.act(() => T.setState({ settingsOn: Object.assign({}, s.settingsOn, { [o.key]: !on }) })) + ' style="width:38px; height:21px; flex:none; border-radius:11px; padding:2px; display:flex; cursor:pointer; background:' + (on ? '#C8F542' : 'rgba(255,255,255,.14)') + '; justify-content:' + (on ? 'flex-end' : 'flex-start') + '">'
        + '<div style="width:17px; height:17px; border-radius:50%; background:' + (on ? '#0A0D0F' : 'rgba(255,255,255,.55)') + '"></div></div></div>'
        + '<div style="' + M + '; font-size:11px; color:rgba(255,255,255,.4); margin-top:12px">' + o.value + '</div></div>';
    }).join('')
    + '</div>'
    + '<div style="padding:0 24px 30px; ' + M + '; font-size:10.5px; color:rgba(255,255,255,.35); line-height:1.7; max-width:760px">Research tool only — no investment advice, no order placement, no venue affiliation. Public Polymarket and Kalshi data, provided as-is. Settings are locked to allowlisted accounts on a public deployment.</div>'
    + '</div>';
}
