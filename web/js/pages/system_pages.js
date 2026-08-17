// Alerts, Research (8 studies incl. live runs), Settings — ported from the
// design reference. Research tabs render the published JSON payloads from
// public/data/ when the API serves them, incl. their stand_utc stamp and note.

import { esc, num, herkunftSatz, leerZeile } from '../util.js';
import { stepKurve, diagramm, linien, kalibrierung, fmtZahl, SERIEN_FARBEN } from '../charts.js';
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
  'postmortems.json', 'field_notes.json'
];

// Farbe je Achse, damit sich die Fehlerarten auf einen Blick trennen lassen.
// Die Palette bleibt bei den vier Grundfarben des Terminals (Limette, Blau,
// Bernstein, Rot) und ihren gedaempften Varianten; jede Achse aus
// public/data/postmortems.json hat einen Eintrag, sonst faellt sie auf Grau.
const ACHSEN_FARBE = {
  'Rule understanding': '#F5A623',
  'Execution': '#FF7A7A',
  'Microstructure': '#4F8EF7',
  'Data': '#7DE2D1',
  'Infrastructure': '#C792EA',
  'Risk discipline': '#FF4545',
  'Engineering maturity': '#9AB0FF',
  'Evaluation': '#C8F542',
  'Detection latency': '#FFD166',
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
      // "PR #12" und "commit 8af07d6" verweisen ins Schwester-Repo, Pfade
      // unter docs/research/ ins Terminal-Repo — als Links, wo ableitbar.
      + (e.referenz
        ? '<div style="' + M + '; font-size:10px; color:rgba(255,255,255,.35); margin-top:11px; '
          + 'border-top:1px solid rgba(255,255,255,.06); padding-top:9px">' + referenzLinksHtml(e.referenz) + '</div>'
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

/** Field notes: kuratierte Beobachtungen vom Tape, je Notiz Datum, Venue,
 *  Markt, Titel, Beobachtung, Mechanismus, Folge und optional ein Beleg.
 *  Nur Struktur — jede Notiz kommt aus public/data/field_notes.json. */
function renderFieldNotes(payload) {
  const notes = (payload && Array.isArray(payload.notes)) ? payload.notes : [];
  const kennung = payload && payload.kennzeichnung ? String(payload.kennzeichnung).toUpperCase() : 'CURATED';
  const stempel = payload && payload.stand_utc
    ? String(payload.stand_utc).slice(0, 16).replace('T', ' ') + ' UTC' : 'curated';
  const kopf = '<div style="display:flex; align-items:flex-start; justify-content:space-between; gap:24px">'
    + '<div style="max-width:720px">'
    + '<div style="font-size:20px; font-weight:600">Field notes — what the tape taught us</div>'
    + '<div style="font-size:13.5px; color:rgba(255,255,255,.6); margin-top:8px; line-height:1.5">'
    + esc((payload && payload.hinweis) || 'Curated observations from watching the tape: what happened, the mechanism behind it, and what follows from it. Notes, not measurements — each one names its evidence or says it has none.')
    + '</div></div>'
    + '<div style="display:flex; gap:8px">'
    + '<div style="' + M + '; font-size:9.5px; letter-spacing:.1em; border-radius:4px; padding:3px 8px; color:#0A0D0F; background:#4F8EF7">' + esc(kennung) + '</div>'
    + '<div style="' + M + '; font-size:10.5px; color:rgba(255,255,255,.4); border:1px solid rgba(255,255,255,.14); border-radius:6px; padding:5px 10px; white-space:nowrap">' + esc(stempel) + '</div>'
    + '</div></div>';

  if (!payload) {
    return '<div style="padding:22px 24px">' + kopf
      + '<div style="margin-top:16px">' + leerZeile(herkunftSatz(null, 'public/data/field_notes.json')) + '</div></div>';
  }
  if (payload._quelle === 'fehler') {
    return '<div style="padding:22px 24px">' + kopf
      + '<div style="margin-top:16px">' + leerZeile(herkunftSatz({ quelle: 'fehler', fehler: payload._fehler }, 'public/data/field_notes.json')) + '</div></div>';
  }
  if (!notes.length) {
    return '<div style="padding:22px 24px">' + kopf
      + '<div style="background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:12px; padding:22px 24px; max-width:720px; margin-top:16px">'
      + '<div style="font-size:16px; font-weight:600">No field notes published yet</div>'
      + '<div style="font-size:13px; color:rgba(255,255,255,.55); margin-top:10px; line-height:1.6">'
      + 'This page reads <span style="' + M + '">public/data/field_notes.json</span>. The file is there but its '
      + '<span style="' + M + '">notes</span> list is empty, so there is nothing to show — and nothing is invented to fill the space.'
      + '</div></div></div>';
  }

  const feld = (label, wert, farbe) => (wert
    ? '<div style="margin-top:11px">'
      + '<div style="' + M + '; font-size:9px; letter-spacing:.13em; color:rgba(255,255,255,.38)">' + label + '</div>'
      + '<div style="font-size:12.5px; color:' + (farbe || 'rgba(255,255,255,.72)') + '; margin-top:4px; line-height:1.6">'
      + esc(wert) + '</div></div>'
    : '');

  const venues = {};
  notes.forEach((n) => { const v = String(n.venue || 'unknown venue'); venues[v] = (venues[v] || 0) + 1; });
  const chips = Object.entries(venues).sort((a, b) => b[1] - a[1]).map(([v, n]) =>
    '<div style="' + M + '; font-size:10px; color:rgba(255,255,255,.6); border:1px solid rgba(255,255,255,.18); border-radius:5px; padding:4px 9px">'
    + esc(v.toUpperCase()) + ' ' + n + '</div>').join('');

  const karten = notes.slice().sort((a, b) => String(b.date || '').localeCompare(String(a.date || ''))).map((n) =>
    '<div style="background:#10151A; border:1px solid rgba(255,255,255,.09); border-left:2px solid #4F8EF7; border-radius:10px; padding:16px 18px">'
    + '<div style="display:flex; align-items:baseline; justify-content:space-between; gap:14px; flex-wrap:wrap">'
    + '<div style="font-size:14.5px; font-weight:600; flex:1; min-width:220px">' + esc(n.title || '—') + '</div>'
    + '<div style="' + M + '; font-size:10px; color:#4F8EF7">' + esc(n.venue || '') + '</div></div>'
    + '<div style="' + M + '; font-size:10px; color:rgba(255,255,255,.4); margin-top:5px">'
    + esc(n.date || '—') + (n.market ? ' · ' + esc(n.market) : '') + '</div>'
    + feld('OBSERVATION', n.observation)
    + feld('MECHANISM', n.mechanism, '#F5A623')
    + feld('CONSEQUENCE', n.consequence, '#C8F542')
    + (n.evidence
      ? '<div style="' + M + '; font-size:10px; color:rgba(255,255,255,.35); margin-top:11px; '
        + 'border-top:1px solid rgba(255,255,255,.06); padding-top:9px">EVIDENCE · ' + referenzLinksHtml(n.evidence) + '</div>'
      : '<div style="' + M + '; font-size:10px; color:rgba(255,255,255,.3); margin-top:11px; '
        + 'border-top:1px solid rgba(255,255,255,.06); padding-top:9px">NO EVIDENCE ATTACHED · an observation, not a finding</div>')
    + '</div>'
  ).join('');

  return '<div style="padding:22px 24px 36px">' + kopf
    + '<div style="display:flex; gap:7px; flex-wrap:wrap; margin-top:12px">'
    + '<div style="' + M + '; font-size:10px; color:#fff; border:1px solid rgba(255,255,255,.2); border-radius:5px; padding:4px 9px">'
    + notes.length + ' NOTE' + (notes.length === 1 ? '' : 'S') + '</div>' + chips + '</div>'
    + '<div style="display:grid; grid-template-columns:repeat(auto-fit,minmax(360px,1fr)); gap:14px; margin-top:16px">'
    + karten + '</div></div>';
}

// ---------------------------------------------------------------- review queue
// queue.json traegt einen Fall je Markt UND Zeitfenster: derselbe Slug steht
// zehnmal da, einmal je Fuenf-Minuten-Fenster des Laufs. Die Seite zeigt eine
// Zeile je Markt und behaelt den Fall mit der hoechsten Prioritaet (Band
// high > medium > low, dann der juengste ts, dann das juengste Fenster);
// dessen Begruendung und Skeptiker-Felder bleiben unveraendert. Zusaetzlich
// traegt die Zeile, wie viele Fenster zusammengefallen sind und welche Spanne
// sie ueberdecken. Reine Funktion, damit sie fuer den statischen und den
// API-Pfad gleich rechnet und im Render-Harness pruefbar ist.
const BAND_RANG = { high: 3, medium: 2, low: 1 };

export function collapseQueue(faelle) {
  if (!Array.isArray(faelle)) return [];
  const rang = (f) => BAND_RANG[String(f && f.score_band || '').toLowerCase()] || 0;
  const zeit = (v) => String(v || '');
  const proMarkt = new Map();
  faelle.forEach((f) => {
    if (!f) return;
    const slug = String(f.markt_slug || f.id || '');
    let eintrag = proMarkt.get(slug);
    if (!eintrag) {
      eintrag = { best: f, fenster: [] };
      proMarkt.set(slug, eintrag);
    } else {
      const b = eintrag.best;
      const neuer = rang(f) > rang(b)
        || (rang(f) === rang(b) && zeit(f.ts) > zeit(b.ts))
        || (rang(f) === rang(b) && zeit(f.ts) === zeit(b.ts) && zeit(f.zeitfenster) > zeit(b.zeitfenster));
      if (neuer) eintrag.best = f;
    }
    if (f.zeitfenster) eintrag.fenster.push(String(f.zeitfenster));
    else eintrag.fenster.push('');
  });
  const zeilen = [];
  proMarkt.forEach((eintrag) => {
    const bekannt = eintrag.fenster.filter(Boolean).sort();
    zeilen.push(Object.assign({}, eintrag.best, {
      windows_n: eintrag.fenster.length,
      windows_first: bekannt.length ? bekannt[0] : null,
      windows_last: bekannt.length ? bekannt[bekannt.length - 1] : null
    }));
  });
  zeilen.sort((a, b) => (rang(b) - rang(a))
    || zeit(b.ts).localeCompare(zeit(a.ts))
    || String(a.markt_slug || '').localeCompare(String(b.markt_slug || '')));
  return zeilen;
}

// "10 · 05-22 20:45 → 21:50": Anzahl der Fenster und ihre Spanne, kompakt.
function fensterText(zeile) {
  const kurz = (iso) => {
    const s = String(iso || '');
    if (s.length < 16) return s;
    return s.slice(5, 10) + ' ' + s.slice(11, 16);
  };
  const n = zeile.windows_n || 1;
  if (!zeile.windows_first) return String(n);
  if (n === 1 || zeile.windows_first === zeile.windows_last) return n + ' · ' + kurz(zeile.windows_first);
  const a = kurz(zeile.windows_first);
  const b = kurz(zeile.windows_last);
  // Gleicher Tag: das Datum nur einmal.
  const gleicherTag = a.slice(0, 5) === b.slice(0, 5);
  return n + ' · ' + a + ' → ' + (gleicherTag ? b.slice(6) : b);
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
  const holderInaktiv = ungeprueft.indexOf('HOLDER CONCENTRATION') >= 0;
  // Arten, die im Scan vorkommen, aber in keiner gelieferten Zeile: der
  // Endpunkt sortiert nach Schwere und schneidet dann ab, eine ganze Art
  // kann also unter den Schnitt fallen.
  const gelieferteArten = feedAll.map((a) => a.rule);
  const verschluckt = zaehlung
    ? Object.keys(zaehlung)
      .filter((art) => zaehlung[art] > 0 && gelieferteArten.indexOf(art) < 0)
      .map((art) => [art, zaehlung[art]])
    : [];
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
    { key: 'movers', name: 'Fast movers', desc: 'A market moves more than the move threshold in under an hour.' },
    { key: 'volume', name: 'Volume anomaly', desc: 'An hour trades more than three times its own daily average.' },
    { key: 'whales', name: 'Whale prints', desc: 'A single trade above the print threshold lands.' },
    { key: 'spreads', name: 'Tight spreads', desc: 'A market narrows below the spread threshold.' },
    { key: 'holders', name: 'Holder concentration', desc: 'Three wallets or fewer hold most of one side.' },
    { key: 'endings', name: 'Resolving soon', desc: 'A market resolves inside the resolving window.' }
  ];

  // Die Schalter lagen bis eben nur im Frontend-Zustand und taten nichts:
  // die Signalliste zeigte Tight-Spread-Zeilen auch bei ausgeschaltetem
  // Schalter. Sie blenden jetzt die Signalarten aus, die sie benennen. Was
  // sie nicht tun, ist den Scanner steuern — der laeuft ueber die Schwellen,
  // und die Karten sagen die Trefferzahl des ganzen Scans, nicht der Anzeige.
  const abgeschaltet = rules
    .filter((r) => !s.alertsOn[r.key])
    .map((r) => REGEL_SIGNAL[r.key]);
  // Signalarten ohne eigenen Schalter — etwa WATCHED MARKET, an dem der
  // Scope-Filter haengt — bleiben sichtbar. Ein Schalter blendet aus, was er
  // benennt, und sonst nichts.
  const sichtbar = (a) => abgeschaltet.indexOf(a.rule) < 0;
  const ausgeblendet = feedAll.length - feedAll.filter(sichtbar).length;
  const feed = feedAll.filter((a) =>
    sichtbar(a)
    && (s.alertPlatform === 'all' || a.venue === s.alertPlatform)
    && (s.alertType === 'all' || a.rule === s.alertType)
    && (s.alertScope === 'all' || a.watched)
    && (!s.alertQuery.trim() || a.market.toLowerCase().indexOf(s.alertQuery.trim().toLowerCase()) >= 0));

  let body = '';
  if (s.alertTab === 'signals') {
    body = '<div>'
      + '<div style="' + M + '; font-size:11px; color:rgba(255,255,255,.45); padding:14px 24px 0">showing signals over ' + s.thMove + '¢ moves, prints above $' + num(s.thWhale) + ', spreads under ' + s.thSpread + '¢, resolving within ' + s.thEnding + ' h' + (live && live.as_of ? ' · snapshot ' + esc(live.as_of) : '') + '</div>'
      // Der Schnitt gehoert danebengeschrieben. Eine Tabelle, die 60 von 300
      // Zeilen zeigt und das verschweigt, liest sich wie der ganze Scan.
      + (zaehlung && live.shown_limit && gesamtTreffer > live.shown_limit
        ? '<div style="' + M + '; font-size:11px; color:#F5A623; padding:6px 24px 0">'
          + 'showing the top ' + live.shown_limit + ' of ' + num(gesamtTreffer) + ' signals in this scan, ranked by severity'
          // Welche Art der Schnitt komplett verschluckt. Ohne den Zusatz
          // widerspricht die Regelkarte scheinbar der Tabelle: sie meldet
          // hundert Treffer fuer eine Art, von der keine Zeile zu sehen ist.
          + (verschluckt.length
            ? ' · none of ' + verschluckt.map((a) => esc(a[0]) + ' (' + num(a[1]) + ')').join(', ') + ' made the cut'
            : '')
          + '</div>'
        : '')
      + '<div style="border:1px solid rgba(255,255,255,.09); border-radius:12px; margin:12px 24px; overflow:hidden">'
      + '<div style="display:grid; grid-template-columns:92px 170px 1fr 110px 120px; gap:10px; padding:9px 16px; background:#10151A; border-bottom:1px solid rgba(255,255,255,.09); ' + M + '; font-size:9px; letter-spacing:.12em; color:rgba(255,255,255,.45)">'
      + '<div>TIME</div><div>SIGNAL</div><div>MARKET</div><div style="text-align:right">READING</div><div style="text-align:right">VENUE</div></div>'
      + (ausgeblendet
        ? '<div style="' + M + '; font-size:11px; color:rgba(255,255,255,.45); padding:6px 24px 0">'
          + num(ausgeblendet) + ' signal' + (ausgeblendet === 1 ? '' : 's') + ' hidden by the rule switches</div>'
        : '')
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
    // Frueher stand hier "Switch one on and it also goes to Telegram". Der
    // Versand haengt am Scanner-Skript und an dessen Konfiguration, nicht an
    // diesen Schaltern — die entscheiden, was diese Seite zeigt.
    + '<div style="font-size:13px; color:rgba(255,255,255,.55); margin-top:9px; max-width:700px">The thresholds below are sent to the scan. The switches decide which of its signal types this page shows; Telegram delivery is configured on the scanner, not here.</div></div>'
    + '<div style="padding:16px 24px 0; display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:14px 18px">'
    + '<div><div style="' + LBL9 + '">SEARCH</div><input value="' + esc(s.alertQuery) + '" ' + T.inp((e) => T.setState({ alertQuery: e.target.value }), 'alertQuery') + ' placeholder="market, wallet, category…" style="width:100%; box-sizing:border-box; background:#10151A; border:1px solid rgba(255,255,255,.16); border-radius:7px; padding:8px 10px; ' + M + '; font-size:11.5px; color:#fff; outline:none" /></div>'
    + filterGroup('PLATFORM', [['all','All'],['Polymarket','Polymarket'],['Kalshi','Kalshi']].map((o) => T.opt(o[1], s.alertPlatform === o[0], { alertPlatform: o[0] })).join(''))
    + filterGroup('SIGNAL TYPE', [['all','All'],['WHALE PRINT','Whale prints'],['FAST MOVER','Fast movers'],['VOLUME ANOMALY','Volume']].map((o) => T.opt(o[1], s.alertType === o[0], { alertType: o[0] })).join(''))
    + filterGroup('SCOPE', [['all','Everything'],['watched','Watched only']].map((o) => T.opt(o[1], s.alertScope === o[0], { alertScope: o[0] })).join(''))
    + '</div>'
    // Diese vier Schwellen gehen an den Endpunkt und loesen einen neuen Scan
    // aus. Frueher aenderten sie nur den Text darueber.
    + '<div style="padding:16px 24px 0; display:grid; grid-template-columns:repeat(5, minmax(0,1fr)); gap:14px 18px">'
    + filterGroup('MOVE AT LEAST', [3, 5, 8, 12].map((v) => T.opt(v + '¢', s.thMove === v, () => T.alarmNeuLaden({ thMove: v }))).join(''))
    + filterGroup('SPREAD UNDER', [1, 2, 3, 5].map((v) => T.opt(v + '¢', s.thSpread === v, () => T.alarmNeuLaden({ thSpread: v }))).join(''))
    + filterGroup('PRINT AT LEAST', [1000, 2500, 10000, 25000].map((v) => T.opt('$' + num(v), s.thWhale === v, () => T.alarmNeuLaden({ thWhale: v }))).join(''))
    + filterGroup('RESOLVING WITHIN', [24, 48, 72, 168].map((v) => T.opt(v + ' h', s.thEnding === v, () => T.alarmNeuLaden({ thEnding: v }))).join(''))
    // Die Holder-Schwelle bleibt ohne Wirkung, solange der Endpunkt die
    // Regel nicht auswertet. Der Regler sagt es, statt Wirkung vorzutaeuschen.
    + filterGroup('TOP HOLDER OVER'
      + (holderInaktiv ? ' <span style="color:#F5A623">· not evaluated</span>' : ''),
      [25, 40, 60, 80].map((v) => T.opt(v + '%', s.thHolder === v, { thHolder: v })).join(''))
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
  // Field notes haengen am Slug, nicht an der Position: die Liste waechst am
  // Ende, und ein Index wuerde beim naechsten Eintrag verrutschen.
  if (studienSlug(study) === 'field-notes') {
    return '<div>' + header + renderFieldNotes(payload) + '</div>';
  }

  // Microstructure hat eine eigene Seite: zwoelf Studien, je Karte mit
  // Frage, Verdikt, Diagramm und Quelle. Nutzlast aus public/data.
  if (s.researchTab === 4) {
    return '<div>' + header + renderMicrostructure(payload) + '</div>';
  }
  // Category efficiency: Kennzahlen, Balken je Horizont, Brier ueber den
  // Horizont, Kalibrierung je Kategorie und die Tabelle mit allen Horizonten.
  if (s.researchTab === 1) {
    return '<div>' + header + renderCategoryEfficiency(T, payload, study) + '</div>';
  }
  // Methodology: die vier Zaehler aus audit.json plus der Methodentext, der
  // auch ohne die Datei steht — er ist Dokumentation, keine Messung.
  if (studienSlug(study) === 'methodology') {
    return '<div>' + header + renderMethodology(T, payload, study) + '</div>';
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
    // Je Studie ihre Diagramme und Zusatzbloecke (Mentions latency, Pilot,
    // Pipeline forward), am Slug aufgehaengt statt am Index.
    + studienExtrasHtml(studienSlug(study), payload)
    + table
    + studienKnoepfe(T, s.researchTab)
    + '</div></div>';
}

// Der Slug einer Studie, wie er in der Adresse und in api.js STATISCH steht.
function studienSlug(study) {
  return String(study && study.tab ? study.tab : '').toLowerCase().replace(/ /g, '-');
}

// Zwei Knoepfe, die etwas tun. "Download the data" war ein Div ohne Ziel und
// ist jetzt ein Link auf die publizierte Datei der Studie unter ./data/, die
// api/server.py und ein reiner Dateiserver gleichermassen ausliefern. "Read
// the method" springt auf die Methodik-Studie und ist dort selbst nicht da.
function studienKnoepfe(T, tab) {
  const KNOPF = 'font-size:13px; color:#fff; border:1px solid rgba(255,255,255,.2); border-radius:8px; padding:10px 16px; cursor:pointer; text-decoration:none; display:inline-block';
  const datei = RESEARCH_DATEI[tab];
  const methodik = T.studies.findIndex((st) => studienSlug(st) === 'methodology');
  const teile = [];
  if (datei) {
    teile.push('<a href="./data/' + esc(datei) + '" download="' + esc(datei) + '" class="hv-bd35" style="' + KNOPF + '">Download the data</a>');
  }
  if (methodik >= 0 && methodik !== tab) {
    teile.push('<div ' + T.act(() => {
      T.setState({ page: 'research', researchTab: methodik, detail: null });
      try { history.pushState(null, '', '#research/methodology'); } catch (e) { /* file:// */ }
      T.fetchPageData('research');
    }) + ' class="hv-bd35" style="' + KNOPF + '">Read the method</div>');
  }
  if (!teile.length) return '';
  return '<div style="display:flex; gap:10px; margin-top:14px">' + teile.join('') + '</div>';
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
// Die Reihenfolge zaehlt: der erste passende Test gewinnt. "endstand X >
// grenze Y" ist ein NO-Ausschluss (das Wort fiel zu oft), nicht "count
// below threshold" — frueher landete beides unter einem Text.
const PIPELINE_GRUENDE = [
  { test: /^kein_yes_ask/, text: 'No YES ask in the book' },
  { test: /^kein_no_ask/, text: 'No NO ask in the book' },
  { test: /^yes_ask|^vollpreis/, text: 'YES ask (incl. fee) above the run cap' },
  { test: /^no_ask/, text: 'NO ask above the NO cap' },
  { test: /^endstand .*>/, text: 'Final count above the NO limit' },
  { test: /^count|^endstand/, text: 'Word count had not passed the market threshold' },
  { test: /^basisrate_veto/, text: 'Base-rate veto over the past weeks' },
  { test: /^skip/, text: 'Market was skipped before pricing' },
  { test: /^kein_vollpass|^verschreibungs/, text: 'Transcript was not clean enough to bet on absence' }
];

// All decision entries of the forward test: the union over laeufe[].eintraege
// when the runs carry their entries, else the top-level list (which mirrors
// one run only, see the payload note).
export function pipelineEintraege(payload) {
  const laeufe = payload && Array.isArray(payload.laeufe) ? payload.laeufe : [];
  const ausLaeufen = [];
  laeufe.forEach((l) => { if (l && Array.isArray(l.eintraege)) ausLaeufen.push(...l.eintraege); });
  if (ausLaeufen.length) return { eintraege: ausLaeufen, quelle: laeufe.length + ' runs' };
  const oben = payload && Array.isArray(payload.eintraege) ? payload.eintraege : [];
  return { eintraege: oben, quelle: oben.length ? 'the top-level list (one run)' : '' };
}

// Counts: total checks, checks that ended in a buy, and the no-trade reasons
// in plain words, largest first.
export function pipelineZaehlung(eintraege) {
  const zaehler = new Map();
  let sonstige = 0;
  let gekauft = 0;
  eintraege.forEach((e) => {
    if (String((e && e.action) || '').toUpperCase() !== 'NONE') { gekauft += 1; return; }
    const grund = String((e && e.reason) || '');
    const treffer = PIPELINE_GRUENDE.find((g) => g.test.test(grund));
    if (treffer) zaehler.set(treffer.text, (zaehler.get(treffer.text) || 0) + 1);
    else if (grund) sonstige += 1;
  });
  if (sonstige) zaehler.set('Other reasons', sonstige);
  const gruende = [...zaehler.entries()].sort((a, b) => b[1] - a[1]);
  return { gesamt: eintraege.length, gekauft, keine: eintraege.length - gekauft, gruende };
}

// Headline of the forward test, from the counts alone.
function pipelineHeadlineHtml(payload) {
  const { eintraege, quelle } = pipelineEintraege(payload);
  if (!eintraege.length) return '';
  const z = pipelineZaehlung(eintraege);
  const anteil = z.gesamt ? (z.gekauft / z.gesamt) * 100 : 0;
  const top = z.gruende.length ? z.gruende[0] : null;
  const chart = diagramm({
    titel: 'WHY IT DID NOT TRADE · REASON COUNTS · ' + num(z.keine) + ' NO-TRADES ACROSS ' + quelle.toUpperCase(),
    einheit: 'decision checks',
    punkte: z.gruende.map(([text, n]) => ({ label: text, wert: n, art: 'kosten' }))
  });
  return '<div style="background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:12px; margin-top:14px; padding:18px 20px">'
    + '<div style="' + M + '; font-size:10px; letter-spacing:.14em; color:#4F8EF7">WHAT THE FORWARD TEST FOUND</div>'
    + '<div style="font-size:15px; color:#fff; margin-top:10px; line-height:1.6; max-width:820px">'
    + 'Almost nothing was tradable: ' + num(z.gekauft) + ' of ' + num(z.gesamt) + ' rule-compliant decision checks ended in a buy ('
    + (anteil < 10 ? anteil.toFixed(1) : Math.round(anteil)) + '%)'
    + (top ? ' · dominant reason: ' + esc(top[0].charAt(0).toLowerCase() + top[0].slice(1)) + ' (' + num(top[1]) + ' of ' + num(z.keine) + ' no-trades, ' + Math.round((top[1] / Math.max(1, z.keine)) * 100) + '%)' : '')
    + '.</div>'
    + '<div style="font-size:12px; color:rgba(255,255,255,.5); margin-top:8px; line-height:1.5">Counted over ' + esc(quelle) + ' in pipeline_forward.json. No equity curve: the file carries decision fields and best book prices only — no fills, no wallet data, no return claim.</div>'
    + (chart ? '<div style="margin-top:14px">' + chart + '</div>' : '')
    + '</div>';
}

function pipelineRegelnHtml(payload) {
  const { eintraege } = pipelineEintraege(payload);
  if (!eintraege.length) return '';
  const karte = 'background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:12px';
  const z = pipelineZaehlung(eintraege);
  const gesamt = z.gesamt;
  const gekauft = z.gekauft;

  const regel = (titel, text) =>
    '<div style="padding:12px 16px; border-bottom:1px solid rgba(255,255,255,.05)">'
    + '<div style="' + M + '; font-size:10px; letter-spacing:.12em; color:#4F8EF7">' + esc(titel) + '</div>'
    + '<div style="font-size:12.5px; color:rgba(255,255,255,.75); margin-top:6px; line-height:1.6">' + esc(text) + '</div></div>';

  const zeilen = z.gruende.map(([text, n]) =>
    '<div style="display:grid; grid-template-columns:1fr auto auto; gap:12px; align-items:baseline; padding:9px 16px; border-bottom:1px solid rgba(255,255,255,.05)">'
    + '<div style="font-size:12.5px; color:rgba(255,255,255,.75)">' + esc(text) + '</div>'
    + '<div style="' + M + '; font-size:12px; color:#fff">' + num(n) + '</div>'
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
    + 'WHY IT DID NOT TRADE · ' + num(gesamt) + ' decision checks, ' + num(gekauft) + ' acted on · share of all checks</div>'
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
      // Eine Zeile je Markt; WINDOWS sagt, wie viele Zeitfenster darin
      // stecken. Der gezeigte Fall ist der mit der hoechsten Prioritaet.
      const maerkte = collapseQueue(payload.faelle);
      return studyTableHtml(T, 'OPEN CASES · ONE ROW PER MARKET, HIGHEST-PRIORITY WINDOW SHOWN', '110px 1fr 200px 90px 100px 140px', ['CASE','MARKET','WINDOWS','BAND','DISCOUNT','RECOMMENDATION'],
        maerkte.slice(0, 12).map((f) => [String(f.id), String(f.markt_slug || ''), fensterText(f), String(f.score_band || ''), String(f.skeptic_abschlag != null ? f.skeptic_abschlag : '—'), String(f.empfehlung || '')]));
    }
    if (tab === 2 && payload.faelle) {
      // Jede Zeile traegt auch das aufgeloeste Outcome und den Status, wie
      // die Datei sie fuehrt.
      return studyTableHtml(T, 'MENTIONS EVENTS · ' + payload.faelle.length + ' OF ' + payload.faelle.length, '1fr 130px 130px 120px 110px 100px', ['EVENT','FIRST REACTION','CONVERGENCE','WINDOW (H)','RESOLVED','STATUS'],
        payload.faelle.map((f) => [String(f.event), f.minuten_bis_erste_reaktion != null ? f.minuten_bis_erste_reaktion + ' min' : '—', f.minuten_bis_konvergenz != null ? f.minuten_bis_konvergenz + ' min' : '—', String(f.stunden_im_handelbaren_fenster != null ? f.stunden_im_handelbaren_fenster : '—'), String(f.korrekt_aufgeloestes_outcome || '—'), String(f.status || '—')]));
    }
    if (tab === 5 && payload.trades) {
      // Alle Trades, nicht zwoelf; Feldwerte auf Englisch uebersetzt.
      const n = payload.trades.length;
      return studyTableHtml(T, 'PILOT TRADES · ' + n + ' OF ' + n, '96px 1fr 60px 56px 76px 76px 76px 70px 190px', ['DATE','MARKET','ARM','SIDE','SIGNAL','FILL','SLIP','SIZE','EXIT'],
        payload.trades.map((t) => [
          String(t.zeitstempel_utc || '').slice(0, 10), String(t.markt_frage || ''),
          pilotEnglisch(String(t.arm || '')), String(t.seite || '—'),
          t.signalpreis != null && t.signalpreis !== '' ? (+t.signalpreis).toFixed(3) : '—',
          t.ausfuehrungspreis != null && t.ausfuehrungspreis !== '' ? (+t.ausfuehrungspreis).toFixed(3) : '—',
          pilotSlippageCents(t) != null ? (pilotSlippageCents(t) >= 0 ? '+' : '') + pilotSlippageCents(t).toFixed(1) + '¢' : '—',
          '$' + (+t.groesse_usd).toFixed(0), pilotEnglisch(String(t.exit_grund || 'open'))]));
    }
    if (tab === 6 && payload.laeufe) {
      const n = payload.laeufe.length;
      return studyTableHtml(T, 'FORWARD LOG · ' + n + ' OF ' + n + ' RUNS', '1fr 110px 110px 140px 110px', ['RUN','ENTRIES','BUYS','EXTRACTED $','QUOTE'],
        payload.laeufe.map((l) => [String(l.profil), num(l.n_eintraege), num(l.n_kaeufe), '$' + (+l.extraktion_gekauft_usd || 0).toFixed(0), l.extraktionsquote != null ? Math.round((+l.extraktionsquote) * 100) + '%' : '—']));
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
      // Gezaehlt werden Maerkte, nicht Fenster: 34 Faelle ueber 7 Slugs sind
      // 7 offene Maerkte. Die Empfehlungen zaehlen den je Markt behaltenen
      // Fall, damit Kacheln und Tabelle dieselben Zeilen meinen.
      const maerkte = collapseQueue(payload.faelle);
      const fenster = payload.faelle.length;
      const high = maerkte.filter((f) => f.score_band === 'high').length;
      const esc2 = maerkte.filter((f) => f.empfehlung === 'escalate_human').length;
      const einheit = maerkte.length === 1 ? ' market' : ' markets';
      return [
        { label: 'OPEN CASES', value: maerkte.length + einheit, note: fenster + ' window' + (fenster === 1 ? '' : 's') + ' · ' + high + ' high band' },
        { label: 'ESCALATED TO HUMAN', value: String(esc2), note: 'of ' + maerkte.length + einheit },
        { label: 'CHECK SOURCE', value: String(maerkte.filter((f) => f.empfehlung === 'check_source').length), note: 'verification steps' },
        { label: 'WATCH ONLY', value: String(maerkte.filter((f) => f.empfehlung === 'watch').length), note: 'no action needed' }
      ];
    }
    if (tab === 2 && payload.faelle && payload.faelle.length) {
      const reactions = payload.faelle.filter((f) => f.minuten_bis_erste_reaktion != null).map((f) => +f.minuten_bis_erste_reaktion).filter((v) => !isNaN(v)).sort((a, b) => a - b);
      // Echter Median (bei gerader Anzahl das Mittel der beiden mittleren),
      // derselbe wie die Referenzlinie im Diagramm darunter.
      const median = medianVon(reactions);
      const none = payload.faelle.filter((f) => f.minuten_bis_erste_reaktion == null).length;
      return [
        { label: 'MEDIAN LATENCY', value: median != null ? fmtZahl(median) + ' min' : '—', note: 'n = ' + reactions.length + ' events with a reaction · first move ≥ 2¢' },
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
      // Statischer Pfad ohne auswertung: Stueckzahl und Einsatz kommen aus
      // den Trades selbst; der Protokollwert steht daneben, und eine
      // Abweichung wird als solche benannt statt als "fixed" behauptet.
      const offen = payload.trades.filter((t) => !t.exit_zeit_utc && !t.exit_preis).length;
      const groessen = payload.trades.map((t) => +t.groesse_usd).filter((v) => !isNaN(v));
      const einheitlich = groessen.length > 0 && groessen.every((v) => v === groessen[0]);
      const soll = p.einsatz_je_trade_usdc != null ? +p.einsatz_je_trade_usdc : null;
      return [
        { label: 'TRADES', value: String(payload.trades.length), note: offen + ' still open · exit via resolution' },
        { label: 'BUDGET', value: '$' + (p.budget_usdc != null ? p.budget_usdc : '—'), note: 'preregistered' },
        { label: 'STAKE PER TRADE', value: groessen.length ? (einheitlich ? '$' + groessen[0] : '$' + Math.min(...groessen) + '–' + Math.max(...groessen)) : '—',
          note: soll != null ? 'protocol $' + soll + (einheitlich && groessen[0] !== soll ? ' · deviates from the frozen text' : '') : 'no protocol stake in the file' },
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

// ---------------------------------------------------------------- category efficiency (research tab 1)
// Die Zeilen der Nutzlast in eine Form, die alte und neue kategorie_karte.json
// gleich behandelt: je Kategorie eine Liste von Horizonten. Die alte Datei
// kennt nur brier_t7/brier_t1 (n_t7, kein n_t1) und keine Kalibrierung —
// dann gibt es genau die zwei Horizonte, und n steht als unbekannt da, wo
// die Datei es nicht traegt.
function kategorieZeilen(payload) {
  const roh = payload && Array.isArray(payload.kategorien) ? payload.kategorien : [];
  const zahl = (v) => (v == null || v === '' || isNaN(+v) ? null : +v);
  return roh.filter((k) => k && k.kategorie != null).map((k) => {
    let horizonte = Array.isArray(k.horizonte)
      ? k.horizonte.filter((h) => h && h.horizont_tage != null).map((h) => ({
        tage: +h.horizont_tage, brier: zahl(h.brier), treffer: zahl(h.trefferquote),
        n: h.n == null ? null : +h.n, entschieden: zahl(h.anteil_entschieden)
      }))
      : [];
    if (!horizonte.length) {
      horizonte = [
        { tage: 7, brier: zahl(k.brier_t7), treffer: zahl(k.trefferquote_t7), n: k.n_t7 == null ? null : +k.n_t7, entschieden: null },
        { tage: 1, brier: zahl(k.brier_t1), treffer: zahl(k.trefferquote_t1), n: k.n_t1 == null ? null : +k.n_t1, entschieden: null }
      ];
    }
    horizonte.sort((a, b) => b.tage - a.tage);
    const bins = k.kalibrierung && Array.isArray(k.kalibrierung.bins) ? k.kalibrierung.bins : [];
    return {
      name: String(k.kategorie),
      maerkte: k.n_maerkte == null ? null : +k.n_maerkte,
      medianVol: zahl(k.median_volumen_usd),
      entschiedenT7: zahl(k.anteil_entschieden_t7),
      horizonte,
      kalibrierungTage: k.kalibrierung && k.kalibrierung.horizont_tage != null ? +k.kalibrierung.horizont_tage : 7,
      bins: bins.filter((b) => b && b.vorhergesagt != null && b.realisiert != null).map((b) => ({
        vorhergesagt: +b.vorhergesagt, realisiert: +b.realisiert, n: b.n == null ? null : +b.n,
        ci: Array.isArray(b.realisiert_ci95) && b.realisiert_ci95.length === 2 ? [+b.realisiert_ci95[0], +b.realisiert_ci95[1]] : null
      }))
    };
  });
}

function horizontVon(zeile, tage) {
  return zeile.horizonte.find((h) => h.tage === tage) || null;
}

function renderCategoryEfficiency(T, payload, study) {
  const karte = 'background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:12px';
  const stamp = payload && payload.stand_utc ? String(payload.stand_utc).slice(0, 16).replace('T', ' ') + ' UTC' : study.stamp;
  const note = payload && payload.hinweis ? payload.hinweis : study.note;
  const kopf = '<div style="display:flex; align-items:flex-start; justify-content:space-between; gap:24px">'
    + '<div style="max-width:720px">'
    + '<div style="font-size:20px; font-weight:600">' + esc(study.title) + '</div>'
    + '<div style="font-size:13.5px; color:rgba(255,255,255,.6); margin-top:8px; line-height:1.5">' + esc(note) + '</div></div>'
    + '<div style="' + M + '; font-size:10.5px; color:rgba(255,255,255,.4); border:1px solid rgba(255,255,255,.14); border-radius:6px; padding:6px 10px; white-space:nowrap">' + esc(stamp) + '</div></div>';

  if (!payload) {
    return fehlendeStudieHtml(study, RESEARCH_DATEI[1]);
  }
  if (payload._quelle === 'fehler') {
    return '<div style="padding:22px 24px">' + kopf
      + '<div style="margin-top:16px">' + leerZeile(herkunftSatz({ quelle: 'fehler', fehler: payload._fehler }, 'public/data/kategorie_karte.json')) + '</div></div>';
  }
  const zeilen = kategorieZeilen(payload);
  if (!zeilen.length) {
    return '<div style="padding:22px 24px">' + kopf
      + '<div style="' + karte + '; padding:22px 24px; max-width:720px; margin-top:16px">'
      + '<div style="font-size:16px; font-weight:600">No categories in the published file</div>'
      + '<div style="font-size:13px; color:rgba(255,255,255,.55); margin-top:10px; line-height:1.6">'
      + 'This page reads <span style="' + M + '">public/data/kategorie_karte.json</span>. The file is there but its '
      + '<span style="' + M + '">kategorien</span> list is empty, so nothing is drawn — and nothing is invented to fill the space.'
      + '</div></div></div>';
  }

  // Kennzahlen: Maerkte, Kategorien, beste und schlechteste bei T-7 — je mit n.
  const gesamt = zeilen.reduce((a, z) => a + (z.maerkte || 0), 0);
  const mitT7 = zeilen.filter((z) => { const h = horizontVon(z, 7); return h && h.brier != null; })
    .sort((a, b) => horizontVon(a, 7).brier - horizontVon(b, 7).brier);
  const nT7 = zeilen.reduce((a, z) => { const h = horizontVon(z, 7); return a + (h && h.n ? h.n : 0); }, 0);
  const nT7Werte = mitT7.map((z) => horizontVon(z, 7).n).filter((n) => n != null);
  const kpi = (label, wert, hinweis) =>
    '<div style="' + karte + '; border-radius:10px; padding:14px 16px">'
    + '<div style="' + M + '; font-size:9.5px; letter-spacing:.13em; color:rgba(255,255,255,.45)">' + esc(label) + '</div>'
    + '<div style="' + M + '; font-size:21px; margin-top:7px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis">' + esc(wert) + '</div>'
    + '<div style="' + M + '; font-size:10.5px; color:rgba(255,255,255,.4); margin-top:4px">' + esc(hinweis) + '</div></div>';
  const brierText = (z, tage) => {
    const h = horizontVon(z, tage);
    return 'Brier ' + h.brier.toFixed(3) + ' · n ' + (h.n != null ? num(h.n) : '—');
  };
  const kpis = [
    kpi('MARKETS IN SAMPLE', gesamt ? num(gesamt) : '—', gesamt ? 'resolved binary markets · ' + (nT7 ? num(nT7) + ' priced at T-7' : 'no T-7 count published') : 'no market counts in the file'),
    kpi('CATEGORIES', String(zeilen.length), nT7Werte.length ? 'T-7 samples from ' + num(Math.min(...nT7Werte)) + ' to ' + num(Math.max(...nT7Werte)) : 'no T-7 sample sizes published'),
    kpi('BEST AT T-7', mitT7.length ? mitT7[0].name : '—', mitT7.length ? brierText(mitT7[0], 7) : 'no Brier at T-7 in the file'),
    kpi('WORST AT T-7', mitT7.length ? mitT7[mitT7.length - 1].name : '—', mitT7.length ? brierText(mitT7[mitT7.length - 1], 7) : 'no Brier at T-7 in the file')
  ].join('');

  // Balken je Kategorie fuer T-7 und T-1, n im Label. Sortiert nach Brier,
  // beste oben. Ohne Werte an einem Horizont bleibt die Karte weg.
  const balken = (tage) => {
    const punkte = zeilen
      .map((z) => ({ z, h: horizontVon(z, tage) }))
      .filter((p) => p.h && p.h.brier != null)
      .sort((a, b) => a.h.brier - b.h.brier)
      .map((p) => ({ label: p.z.name + ' · n ' + (p.h.n != null ? num(p.h.n) : '—'), wert: p.h.brier, art: 'summe' }));
    return diagramm({ titel: 'BRIER AT T-' + tage + ' BY CATEGORY', einheit: '0 = perfect, 0.25 = always 50%', punkte });
  };
  const balkenT7 = balken(7);
  const balkenT1 = balken(1);
  const balkenHtml = balkenT7 || balkenT1
    ? '<div style="display:grid; grid-template-columns:repeat(auto-fit,minmax(360px,1fr)); gap:12px; margin-top:12px">'
      + (balkenT7 || '') + (balkenT1 || '') + '</div>'
    : '<div style="' + karte + '; padding:16px 18px; margin-top:12px; ' + M + '; font-size:11.5px; color:rgba(255,255,255,.45)">'
      + 'No Brier score at T-7 or T-1 in the payload — no bars are drawn.</div>';

  // Brier ueber den Horizont, eine Linie je Kategorie — nur wenn die Datei
  // mehr als die zwei Legacy-Horizonte traegt.
  const hatHorizonte = (payload.kategorien || []).some((k) => k && Array.isArray(k.horizonte) && k.horizonte.length);
  const alleTage = [];
  zeilen.forEach((z) => z.horizonte.forEach((h) => { if (alleTage.indexOf(h.tage) < 0) alleTage.push(h.tage); }));
  alleTage.sort((a, b) => b - a);
  const linienHtml = hatHorizonte && alleTage.length > 1
    ? linien({
      titel: 'BRIER BY HORIZON', einheit: 'days before the decision, per category',
      hinweis: 'each point carries its own n — see the table',
      x: alleTage.map((t) => 'T-' + t),
      serien: zeilen.map((z, i) => ({
        name: z.name, farbe: SERIEN_FARBEN[i % SERIEN_FARBEN.length],
        werte: alleTage.map((t) => { const h = horizontVon(z, t); return h && h.brier != null ? h.brier : null; })
      }))
    })
    : '';

  // Kalibrierung je Kategorie, klein, nur wo Bins da sind.
  const kalib = zeilen.filter((z) => z.bins.length).map((z) => {
    const n = z.bins.reduce((a, b) => a + (b.n || 0), 0);
    return kalibrierung({
      titel: z.name.toUpperCase(),
      hinweis: 'T-' + z.kalibrierungTage + ' · n ' + num(n) + ' · ' + z.bins.length + ' bins',
      punkte: z.bins
    });
  }).filter(Boolean);
  const kalibHtml = kalib.length
    ? '<div style="' + M + '; font-size:10.5px; letter-spacing:.14em; color:#4F8EF7; margin:18px 0 8px">CALIBRATION AT T-' + (zeilen.find((z) => z.bins.length) || {}).kalibrierungTage + ' · PREDICTED VS REALISED</div>'
      + '<div style="font-size:12px; color:rgba(255,255,255,.5); margin-bottom:10px; line-height:1.5">A dot on the diagonal means the price was right on average in that bin; dot size follows n, the bar is the 95% interval of the realised share, amber when it misses the prediction.</div>'
      + '<div style="display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:12px">' + kalib.join('') + '</div>'
    : (hatHorizonte
      ? '<div style="' + karte + '; padding:14px 18px; margin-top:12px; ' + M + '; font-size:11px; color:rgba(255,255,255,.4)">No calibration bins in this payload — kategorie_karte.json carries them under kategorien[].kalibrierung.</div>'
      : '');

  // Kompakte Tabelle mit allen Horizonten. Zwei Zeilen je Zelle: Brier oben,
  // Trefferquote und n darunter.
  const spalten = '1fr 76px ' + alleTage.map(() => '118px').join(' ') + ' 96px 108px';
  const kopfzeile = '<div style="display:grid; grid-template-columns:' + spalten + '; gap:12px; padding:9px 18px; border-bottom:1px solid rgba(255,255,255,.09); ' + M + '; font-size:9.5px; letter-spacing:.14em; color:rgba(255,255,255,.45)">'
    + '<div>CATEGORY</div><div style="text-align:right">MARKETS</div>'
    + alleTage.map((t) => '<div style="text-align:right">T-' + t + ' BRIER · HIT · N</div>').join('')
    + '<div style="text-align:right">≤5% OR ≥95% AT T-7</div><div style="text-align:right">MEDIAN VOLUME</div></div>';
  const zelle = (h) => {
    if (!h || h.brier == null) return '<div style="text-align:right; ' + M + '; font-size:12px; color:rgba(255,255,255,.3)">—</div>';
    return '<div style="text-align:right; ' + M + '">'
      + '<div style="font-size:12.5px; color:rgba(255,255,255,.85)">' + h.brier.toFixed(3) + '</div>'
      + '<div style="font-size:10px; color:rgba(255,255,255,.4); margin-top:2px">' + (h.treffer != null ? Math.round(h.treffer * 100) + '%' : '—') + ' · n ' + (h.n != null ? num(h.n) : '—') + '</div></div>';
  };
  const tabelle = '<div style="border:1px solid rgba(255,255,255,.09); border-radius:12px; margin-top:16px; overflow:hidden">'
    + '<div style="padding:11px 18px; background:#10151A; border-bottom:1px solid rgba(255,255,255,.09); ' + M + '; font-size:10.5px; letter-spacing:.14em; color:#4F8EF7">BY CATEGORY AND HORIZON</div>'
    + kopfzeile
    + zeilen.map((z) =>
      '<div style="display:grid; grid-template-columns:' + spalten + '; gap:12px; align-items:center; padding:9px 18px; border-bottom:1px solid rgba(255,255,255,.06)">'
      + '<div style="font-size:13px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis">' + esc(z.name) + '</div>'
      + '<div style="text-align:right; ' + M + '; font-size:12.5px; color:rgba(255,255,255,.7)">' + (z.maerkte != null ? num(z.maerkte) : '—') + '</div>'
      + alleTage.map((t) => zelle(horizontVon(z, t))).join('')
      + '<div style="text-align:right; ' + M + '; font-size:12px; color:rgba(255,255,255,.55)">' + (z.entschiedenT7 != null ? Math.round(z.entschiedenT7 * 100) + '%' : '—') + '</div>'
      + '<div style="text-align:right; ' + M + '; font-size:12px; color:rgba(255,255,255,.55)">' + (z.medianVol != null ? '$' + num(Math.round(z.medianVol)) : '—') + '</div>'
      + '</div>').join('')
    + '</div>';

  // Methode und Stichprobe, zugeklappt: was gerechnet wurde, wie die
  // Stichprobe zustande kam, was sie nicht kann — plus die Thesis-Zahlen,
  // die diese Tabelle abloest.
  const q = payload.quelle && typeof payload.quelle === 'object' ? payload.quelle : null;
  const snap = payload.thesis_snapshot && Array.isArray(payload.thesis_snapshot.kategorien) && payload.thesis_snapshot.kategorien.length ? payload.thesis_snapshot : null;
  const absatz = (titel, text) => (text
    ? '<div style="margin-top:10px"><div style="' + M + '; font-size:9px; letter-spacing:.13em; color:rgba(255,255,255,.38)">' + titel + '</div>'
      + '<div style="font-size:12.5px; color:rgba(255,255,255,.7); margin-top:4px; line-height:1.6">' + esc(text) + '</div></div>'
    : '');
  const methodeHtml = q || snap
    ? '<details style="margin-top:14px; ' + karte + '; padding:0 18px">'
      + '<summary style="cursor:pointer; padding:12px 0; ' + M + '; font-size:10.5px; letter-spacing:.14em; color:rgba(255,255,255,.55); list-style:none">METHOD, SAMPLE &amp; WHAT IT CANNOT SHOW ▸</summary>'
      + '<div style="padding-bottom:14px">'
      + (q ? absatz('WHAT WAS MEASURED', q.methode) + absatz('HOW MARKETS WERE CATEGORISED', q.kategorisierung) : '')
      + (q && q.datenfenster ? absatz('DATA WINDOW', 'events with an end date from ' + String(q.datenfenster.end_date_min || '').slice(0, 10) + ', fetched ' + String(q.datenfenster.abgerufen_utc || '').slice(0, 16).replace('T', ' ') + ' UTC · ' + num(q.datenfenster.events_gesichtet || 0) + ' events scanned · ' + q.datenfenster.reihenfolge) : '')
      + (q && q.auswahl ? absatz('SAMPLE SELECTION', 'at most ' + q.auswahl.max_per_event + ' markets per event, ' + q.auswahl.max_per_category_long_lived + ' long-lived and ' + q.auswahl.max_per_category_short_lived + ' short-lived markets per category, minimum volume $' + num(q.auswahl.min_volume_usd) + ', categories under ' + q.auswahl.min_markets_per_category + ' markets fold into Other') : '')
      + (q && q.preise ? absatz('PRICE SERIES', 'hourly: ' + q.preise.hourly + ' · daily: ' + q.preise.daily) : '')
      + (q && Array.isArray(q.einschraenkungen) && q.einschraenkungen.length
        ? '<div style="margin-top:10px"><div style="' + M + '; font-size:9px; letter-spacing:.13em; color:rgba(255,255,255,.38)">WHAT IT CANNOT SHOW</div>'
          + '<ul style="margin:4px 0 0 18px; padding:0; font-size:12.5px; color:rgba(255,255,255,.7); line-height:1.6">'
          + q.einschraenkungen.map((e) => '<li>' + esc(e) + '</li>').join('') + '</ul></div>'
        : '')
      + (snap
        ? '<div style="margin-top:12px"><div style="' + M + '; font-size:9px; letter-spacing:.13em; color:rgba(255,255,255,.38)">THESIS FIGURES THIS TABLE REPLACES' + (snap.stand_utc ? ' · ' + esc(String(snap.stand_utc).slice(0, 10)) : '') + '</div>'
          + (snap.hinweis ? '<div style="font-size:12px; color:rgba(255,255,255,.5); margin-top:4px; line-height:1.5">' + esc(snap.hinweis) + '</div>' : '')
          + '<div style="' + M + '; font-size:11px; color:rgba(255,255,255,.6); margin-top:6px; line-height:1.7">'
          + snap.kategorien.map((k) => esc(String(k.kategorie)) + ': Brier T-7 ' + (k.brier_t7 != null ? (+k.brier_t7).toFixed(3) : '—') + ' (n ' + (k.n_t7 != null ? k.n_t7 : '—') + ') · T-1 ' + (k.brier_t1 != null ? (+k.brier_t1).toFixed(3) : '—') + ' · ' + (k.n_maerkte != null ? k.n_maerkte : '—') + ' markets').join('<br>')
          + '</div></div>'
        : '')
      + '</div></details>'
    : '';

  return '<div style="padding:22px 24px">' + kopf
    + '<div style="display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-top:18px">' + kpis + '</div>'
    + balkenHtml
    + (linienHtml ? '<div style="margin-top:12px">' + linienHtml + '</div>' : '')
    + kalibHtml
    + tabelle
    + methodeHtml
    + studienKnoepfe(T, 1)
    + '</div>';
}

// ---------------------------------------------------------------- live runs (research tab 3)
function renderLiveRuns(T, payload) {
  const s = T.state;
  const agg = payload && payload.aggregat ? payload.aggregat : null;
  const stamp = payload && payload.stand_utc ? String(payload.stand_utc).slice(0, 10) : 'rolling';

  // Zwei PnL-Zahlen, beide beschriftet: die aus den Logs rekonstruierte (die
  // Nutzlast nimmt den Preisdeckel an, wo die FAK-Antwort keinen Fillpreis
  // trug) und die wallet-abgeglichene Netto-Zahl mit ihrem Stand. Frueher
  // stand die Log-Zahl unter "REALIZED PNL · wallet-reconciled" — falsch
  // beschriftet, und die Kachel TOTAL STAKE dazu.
  const walletStand = agg && agg.wallet_abgleich_stand ? String(agg.wallet_abgleich_stand) : '';
  const firstTaker = firstTakerKpi(payload);
  const kpis = agg ? [
    { label: 'RUNS', value: String(agg.n_runs), sub: 'one run = one episode or event', color: '#ffffff' },
    { label: 'BETS', value: num(agg.n_wetten), sub: agg.gewonnen + 'W · ' + agg.verloren + 'L · ' + agg.offen + ' open', color: '#ffffff' },
    { label: 'TOTAL STAKE', value: '$' + num((+agg.einsatz_usd).toFixed(0)), sub: 'log estimate · cap assumed where no fill price', color: '#ffffff' },
    { label: 'LOG-RECONSTRUCTED PNL', value: (agg.realisierter_pnl_usd >= 0 ? '+$' : '-$') + num(Math.abs(+agg.realisierter_pnl_usd).toFixed(0)), sub: 'from run logs' + (agg.roi_realisiert_pct != null ? ' · ' + (+agg.roi_realisiert_pct).toFixed(1) + '% on log stake' : ''), color: agg.realisierter_pnl_usd >= 0 ? '#C8F542' : '#FF4545' },
    { label: 'WALLET-RECONCILED NET' + (walletStand ? ' (AS OF ' + walletStand + ')' : ''),
      value: agg.wallet_netto_usd != null ? (+agg.wallet_netto_usd >= 0 ? '+$' : '-$') + num(Math.abs(+agg.wallet_netto_usd).toFixed(0)) : '—',
      sub: agg.wallet_netto_usd != null ? 'on-chain wallet statement · cash truth' : 'runs.json carries no wallet_netto_usd',
      color: agg.wallet_netto_usd == null ? '#ffffff' : +agg.wallet_netto_usd >= 0 ? '#C8F542' : '#FF4545' },
    { label: 'FIRST TAKER', value: firstTaker.value, sub: firstTaker.sub, color: '#ffffff' },
    { label: 'OPEN STAKE', value: '$' + num((+agg.offener_einsatz_usd).toFixed(0)), sub: 'in unresolved markets', color: '#ffffff' }
  ] : [
    // Kein Rueckfall auf 64 Laeufe, 1.208 Wetten und eine Trefferquote von
    // 54 Prozent. Die Zahlen stehen in runs.json oder nirgends.
    { label: 'RUNS', value: '—', sub: 'runs.json not loaded', color: '#ffffff' },
    { label: 'BETS', value: '—', sub: 'runs.json not loaded', color: '#ffffff' },
    { label: 'TOTAL STAKE', value: '—', sub: 'runs.json not loaded', color: '#ffffff' },
    { label: 'LOG-RECONSTRUCTED PNL', value: '—', sub: 'runs.json not loaded', color: '#ffffff' },
    { label: 'WALLET-RECONCILED NET', value: '—', sub: 'runs.json not loaded', color: '#ffffff' },
    { label: 'FIRST TAKER', value: '—', sub: 'runs.json not loaded', color: '#ffffff' },
    { label: 'OPEN STAKE', value: '—', sub: 'runs.json not loaded', color: '#ffffff' }
  ];
  const abgleichHtml = agg ? abgleichTabelleHtml(payload, agg) : '';
  const laufSatz = herkunftSatz(
    payload ? { quelle: payload._quelle === 'fehler' ? 'fehler' : 'leer', fehler: payload._fehler } : null,
    'public/data/runs.json');

  const alleKarten = payload && payload.runs ? payload.runs.map((r) => {
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
    // Die Drop-Quelle als Chip statt als Klammerzusatz im Titel: "(kanalseite)"
    // und "(URL-Prober)" waren interne Bezeichner im sichtbaren Titel.
    if (r.drop_quelle && DROP_QUELLE_TEXT[String(r.drop_quelle)]) chips.push('drop via ' + DROP_QUELLE_TEXT[String(r.drop_quelle)]);
    const resolvedAll = bets.length && bets.every((b) => b.result !== 'open');
    const missedN = (r.verpasste_chancen || []).length;
    // Je Lauf zwei Zahlen, beide benannt: realisierter_pnl_usd ist die
    // Log-Rekonstruktion, wallet_netto_usd der Wallet-Abgleich — frueher
    // stand die Log-Zahl als "wallet net" in der Fusszeile.
    const logPnl = (r.realisierter_pnl_usd >= 0 ? '+$' : '-$') + Math.abs(+r.realisierter_pnl_usd).toFixed(2);
    const walletNet = r.wallet_netto_usd != null
      ? (+r.wallet_netto_usd >= 0 ? '+$' : '-$') + Math.abs(+r.wallet_netto_usd).toFixed(2)
      : 'not reconciled for this run';
    return {
      profile: String(r.profil || '').toUpperCase(), mode: String(r.modus || '').toUpperCase() === 'LIVE' ? 'REAL ORDERS' : 'DRY RUN',
      status: bets.length === 0 ? 'NO FILLS' : resolvedAll ? 'RESOLVED' : 'OPEN',
      title: episodenTitel(r), url: episodenUrl(r), chips, bets,
      footer: 'Stake $' + (+r.einsatz_usd).toFixed(2) + ' (log est.) · log PnL ' + logPnl + ' · wallet net ' + walletNet,
      missed: missedN ? 'Missed chances (' + missedN + ') — budget or cap' : ''
    };
  }) : [];
  // Ein Lauf ohne Wette traegt drei Zahlen und sonst nichts. Als volle Karte
  // wiederholt er 150 Pixel lang "nichts passiert" und verdraengt die Laeufe,
  // in denen etwas passierte — er wird zur einzeiligen Zeile weiter unten.
  const cards = alleKarten.filter((r) => r.bets.length).slice(0, 12);
  const ohneFills = alleKarten.filter((r) => !r.bets.length);

  // Kumulierte realisierte PnL je Lauf, geordnet nach dem ersten Fill des
  // Laufs — dem Moment, in dem tatsaechlich Geld gebunden wurde. Nicht jeder
  // Lauf traegt ein pubdate (Earnings-Calls haben keins), aber jeder Lauf
  // mit PnL traegt Fills. Fehlt einem PnL-Lauf jeder Zeitstempel, gibt es
  // keine Kurve statt einer falsch geordneten: die Summe der Kurve muss die
  // Kachel daruber reproduzieren.
  const equityPunkte = (() => {
    if (!payload || !Array.isArray(payload.runs)) return [];
    const mitZeit = [];
    for (const r of payload.runs) {
      if (r.realisierter_pnl_usd == null) continue;
      const fillZeiten = (r.wetten || []).map((b) => b.fill_ts_utc).filter(Boolean).sort();
      const zeit = fillZeiten[0] || r.pubdate_utc || r.drop_erkannt_utc;
      if (!zeit) return [];
      mitZeit.push({ zeit: String(zeit), pnl: +r.realisierter_pnl_usd });
    }
    mitZeit.sort((a, b) => a.zeit.localeCompare(b.zeit));
    let summe = 0;
    return mitZeit.map((r) => {
      summe += r.pnl;
      return { label: r.zeit.slice(5, 10), wert: Math.round(summe * 100) / 100 };
    });
  })();
  const equityChart = equityPunkte.length > 1 ? stepKurve({
    titel: 'CUMULATIVE REALIZED PNL BY RUN',
    einheit: 'USD · log-reconstructed',
    hinweis: agg && agg.wallet_netto_usd != null
      ? 'wallet-reconciled net ' + (+agg.wallet_netto_usd >= 0 ? '+$' : '-$')
        + Math.abs(+agg.wallet_netto_usd).toFixed(0)
        + (agg.wallet_abgleich_stand ? ' as of ' + agg.wallet_abgleich_stand : '')
        + ' — the two figures differ, see the note above'
      : '',
    punkte: equityPunkte
  }) : '';

  const timingRows = payload && payload.runs ? payload.runs.flatMap((r) =>
    (r.wetten || []).filter((b) => b.fill_ts_utc).map((b) => ({
      run: String(r.profil || '').slice(0, 10),
      market: b.frage,
      drop: r.drop_erkannt_utc ? String(r.drop_erkannt_utc).slice(11, 19) : '—',
      fill: String(b.fill_ts_utc).slice(11, 19),
      lat: r.erster_fill_s != null ? Math.round(+r.erster_fill_s * 1000) : null,
      before: b.fremde_davor != null ? String(b.fremde_davor) : '—',
      next: b.verfolger_s != null ? '+' + (+b.verfolger_s).toFixed(1) + ' s' : '—',
      // runs.json traegt den Pfad als preis_nach_fill {"0","30",…,"900"};
      // frueher wurde ein Feld preis_nach_fill_30s gelesen, das es nie gab,
      // und die Spalte blieb leer.
      rep: nachFillDelta(b, '30'),
      rep900: nachFillDelta(b, '900')
    }))
  ) : [];

  const liveTabs = [['runs','Runs'],['timing','Timing & repricing'],['sim','Sizing simulator'],['calib','Calibration'],['record','Track record']].map((o) => T.tab(o[1], s.liveTab === o[0], { liveTab: o[0] })).join('');

  let body = '';
  if (s.liveTab === 'runs') {
    body = '<div style="margin-top:14px">'
      + '<div style="font-size:12.5px; color:rgba(255,255,255,.5); line-height:1.5; max-width:820px; margin-bottom:14px">Race chips compare each fill against the public taker tape of that market: how many other trades hit between the drop and our fill, and how long until the next trader after us. The anchor is the bot\'s logged fill time — chain timestamps can differ by a few seconds.</div>'
      + (alleKarten.length ? '' : leerZeile(laufSatz))
      + '<div style="display:flex; flex-direction:column; gap:12px">'
      + cards.map((r) => {
        const statusStyle = M + '; font-size:9.5px; letter-spacing:.1em; border-radius:4px; padding:3px 8px; ' + (r.status === 'RESOLVED' ? 'color:rgba(255,255,255,.6); border:1px solid rgba(255,255,255,.18)' : r.status === 'OPEN' ? 'color:#F5A623; border:1px solid rgba(245,166,35,.4)' : 'color:rgba(255,255,255,.4); border:1px solid rgba(255,255,255,.12)');
        return '<div style="background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:12px; padding:16px 18px">'
          + '<div style="display:flex; gap:7px; flex-wrap:wrap">'
          + '<div style="' + M + '; font-size:9.5px; letter-spacing:.1em; border-radius:4px; padding:3px 8px; color:#4F8EF7; border:1px solid rgba(79,142,247,.4)">' + esc(r.profile) + '</div>'
          + '<div style="' + M + '; font-size:9.5px; letter-spacing:.1em; border-radius:4px; padding:3px 8px; color:#4F8EF7; border:1px solid rgba(79,142,247,.4)">' + esc(r.mode) + '</div>'
          + '<div style="' + statusStyle + '">' + esc(r.status) + '</div></div>'
          // "event ↗" war toter Text ohne Ziel. Jetzt ein Link auf die
          // Event-Seite, wenn die Nutzlast einen Slug oder eine URL traegt,
          // sonst nichts.
          + '<div style="font-size:15px; font-weight:600; margin-top:11px">' + esc(r.title)
          + (r.url ? ' <a href="' + esc(r.url) + '" target="_blank" rel="noopener" style="' + M + '; font-size:11px; color:#4F8EF7; text-decoration:none">event ↗</a>' : '')
          + '</div>'
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
      + '</div>'
      // Die Laeufe ohne Fill, einzeilig: Profil, Episode, die zwei Zahlen,
      // die sie tragen. Nichts faellt weg — nur die 150 Leerpixel je Lauf.
      + (ohneFills.length
        ? '<div style="border:1px solid rgba(255,255,255,.09); border-radius:12px; margin-top:14px; overflow:hidden">'
          + '<div style="padding:10px 16px; background:#10151A; border-bottom:1px solid rgba(255,255,255,.09); ' + M + '; font-size:10px; letter-spacing:.12em; color:rgba(255,255,255,.5)">RUNS WITHOUT A FILL · ' + ohneFills.length
          + ' <span style="color:rgba(255,255,255,.35); letter-spacing:0">· the decision layer ran and placed nothing — one line per run</span></div>'
          + ohneFills.map((r) =>
            '<div style="display:flex; align-items:center; gap:10px; padding:9px 16px; border-bottom:1px solid rgba(255,255,255,.05)">'
            + '<div style="' + M + '; font-size:9.5px; letter-spacing:.08em; color:#4F8EF7; border:1px solid rgba(79,142,247,.35); border-radius:4px; padding:2px 7px; white-space:nowrap">' + esc(r.profile) + '</div>'
            + '<div style="font-size:12.5px; color:rgba(255,255,255,.75); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; flex:1">' + esc(r.title) + '</div>'
            + '<div style="' + M + '; font-size:10.5px; color:rgba(255,255,255,.45); white-space:nowrap">' + esc(r.chips.filter((c) => /decisions|priced/.test(c)).join(' · ') || '—') + '</div>'
            + '<div style="' + M + '; font-size:10.5px; color:rgba(255,255,255,.35); white-space:nowrap">' + esc(r.mode.toLowerCase()) + ' · no fills</div>'
            + '</div>').join('')
          + '</div>'
        : '')
      + '</div>';
  } else if (s.liveTab === 'timing') {
    // Erst die Kurven, dann die Tabelle: Repricing je Wette als Treppe aus
    // repricing[].punkte, dazu die Verzoegerungsreihe aus extras.timing_decay,
    // wenn die API sie anhaengt. Ohne Punkte kein Diagramm, die Tabelle bleibt.
    const repricingHtml = repricingKurvenHtml(payload);
    const decayHtml = timingDecayLinienHtml(payload);
    const repSpalten = '80px 1fr 90px 90px 100px 118px 106px 96px 96px';
    body = repricingHtml + decayHtml
      + '<div style="border:1px solid rgba(255,255,255,.09); border-radius:12px; margin-top:14px; overflow:hidden">'
      + '<div style="padding:11px 16px; background:#10151A; border-bottom:1px solid rgba(255,255,255,.09); ' + M + '; font-size:10.5px; letter-spacing:.14em; color:#4F8EF7">TIMING AND REPRICING PER FILL · ' + timingRows.length + ' FILLS</div>'
      + '<div style="display:grid; grid-template-columns:' + repSpalten + '; gap:10px; padding:9px 16px; border-bottom:1px solid rgba(255,255,255,.09); ' + M + '; font-size:9px; letter-spacing:.12em; color:rgba(255,255,255,.45)">'
      + '<div>RUN</div><div>MARKET</div><div style="text-align:right">DROP</div><div style="text-align:right">FILL</div><div style="text-align:right">LATENCY</div><div style="text-align:right">TRADES BEFORE US</div><div style="text-align:right">NEXT TRADER</div><div style="text-align:right">REPRICE 30 S</div><div style="text-align:right">REPRICE 900 S</div></div>'
      + (timingRows.length ? '' : leerZeile(laufSatz))
      + timingRows.map((t) => {
        const latLabel = t.lat == null ? '—' : t.lat >= 1000 ? (t.lat / 1000).toFixed(1) + ' s' : t.lat + ' ms';
        const latStyle = 'text-align:right; ' + M + '; font-size:12px; color:' + (t.lat == null ? 'rgba(255,255,255,.5)' : t.lat <= 800 ? '#C8F542' : t.lat <= 1500 ? '#F5A623' : '#FF4545');
        const repLabel = (v) => (v == null ? '—' : (v >= 0 ? '+' : '') + v + '¢');
        const repStyle = (v) => 'text-align:right; ' + M + '; font-size:12px; color:' + (v != null && v >= 5 ? '#C8F542' : v != null && v <= -5 ? '#FF4545' : 'rgba(255,255,255,.6)');
        return '<div style="display:grid; grid-template-columns:' + repSpalten + '; gap:10px; align-items:center; padding:11px 16px; border-bottom:1px solid rgba(255,255,255,.06); ' + M + '; font-size:12px">'
          + '<div style="color:rgba(255,255,255,.55)">' + esc(t.run) + '</div>'
          + '<div style="font-family:\'Inter\',sans-serif; font-size:12.5px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis">' + esc(t.market) + '</div>'
          + '<div style="text-align:right; color:rgba(255,255,255,.55)">' + esc(t.drop) + '</div>'
          + '<div style="text-align:right; color:rgba(255,255,255,.55)">' + esc(t.fill) + '</div>'
          + '<div style="' + latStyle + '">' + latLabel + '</div>'
          + '<div style="text-align:right; color:rgba(255,255,255,.7)">' + esc(String(t.before)) + '</div>'
          + '<div style="text-align:right; color:rgba(255,255,255,.7)">' + esc(t.next) + '</div>'
          + '<div style="' + repStyle(t.rep) + '">' + repLabel(t.rep) + '</div>'
          + '<div style="' + repStyle(t.rep900) + '">' + repLabel(t.rep900) + '</div></div>';
      }).join('')
      + '</div>';
  } else if (s.liveTab === 'sim') {
    const extras = payload && payload.extras;
    // "As executed" ist eine Simulation ueber die Log-Schaetzungen der Fills,
    // kein Kassenwert — die Zeile sagt es, damit die Zahl nicht neben der
    // wallet-abgeglichenen Netto-Zahl der Kacheln als dritte PnL gelesen wird.
    const liveSims = extras && extras.sims && extras.sims.length
      ? extras.sims.map((v) => ({
        name: /^as executed$/i.test(String(v.name || '')) ? 'As executed — simulated on log-estimated fills, not cash' : v.name,
        net: v.net, roi: v.roi, dd: null, hit: null, bets: v.bets
      }))
      : null;
    const simRows = liveSims || [];
    body = '<div style="margin-top:14px">'
      + '<div style="font-size:12.5px; color:rgba(255,255,255,.55); line-height:1.5; max-width:820px">Replays the same runs with a different stake rule each time — same entries, same fills, only the size changes. Caps and the per-run budget stay as they were on the day.' + (liveSims ? ' Only resolved bets with a valid fill price count; bankroll $100, no compounding.' : '') + ' Every figure in this tab is a simulation on log-estimated fills — not cash; the cash figure is the wallet-reconciled net in the tiles above.</div>'
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
    // Das Kalibrierungsquadrat aus charts.js ueber den Baendern; die Tabelle
    // bleibt darunter. Ohne Baender kein Diagramm.
    const calibN = calibRows.reduce((a, c) => a + (+c.n || 0), 0);
    const calibChart = kalibrierung({
      titel: 'ENTRY PRICE VS SETTLED SHARE · ' + calibRows.length + ' BANDS',
      hinweis: 'n ' + calibN + ' resolved bets · ' + calibRows.length + ' entry-price bands · dot size follows n',
      punkte: calibRows.map((c) => ({ vorhergesagt: (+c.paid) / 100, realisiert: (+c.settled) / 100, n: +c.n || 0 }))
    });
    body = '<div style="margin-top:14px">'
      + '<div style="font-size:12.5px; color:rgba(255,255,255,.55); line-height:1.5; max-width:820px">Entry price against what actually happened. A perfectly calibrated entry sits on the diagonal — above it means we paid too much.' + esc(calibNote) + '</div>'
      + (calibChart ? '<div style="margin-top:14px; max-width:420px">' + calibChart + '</div>' : '')
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
    + '<div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(150px, 1fr)); gap:12px; margin-top:18px">'
    + kpis.map((k) =>
      '<div style="background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:10px; padding:14px 16px">'
      + '<div style="' + M + '; font-size:9.5px; letter-spacing:.13em; color:rgba(255,255,255,.45)">' + esc(k.label) + '</div>'
      + '<div style="' + M + '; font-size:21px; margin-top:7px; color:' + k.color + '; white-space:nowrap">' + esc(k.value) + '</div>'
      + '<div style="' + M + '; font-size:10.5px; color:rgba(255,255,255,.4); margin-top:4px">' + esc(k.sub) + '</div></div>'
    ).join('')
    + '</div>'
    // Log gegen Wallet in einer Zeile, mit dem Satz, warum sie auseinander
    // liegen, und der Adresse, ueber die jeder den Abgleich nachrechnen kann.
    + abgleichHtml
    // Die versprochene Kurve der Seite: kumulierte PnL je Lauf, aus den
    // publizierten Laufwerten. Ohne Serie kein Diagramm.
    + (equityChart ? '<div style="margin-top:12px">' + equityChart + '</div>' : '')
    // Preispfad nach dem Fill je Wette, aus preis_nach_fill. Ohne Pfade
    // steht da, welches Feld fehlt.
    + postFillPfadeHtml(payload)
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

// ---- live runs: helpers for the KPI row, the reconciliation table and the charts

// The wallet the live runs were placed from. Shown as text so anyone can rerun
// the reconciliation against the public Polymarket Data API for this address.
const LIVE_RUN_WALLET = '0x29afe1bf37700768a640a08f1b35dad5f202f88d';

// Drop sources as they appear in runs.json (drop_quelle), in plain words.
const DROP_QUELLE_TEXT = {
  libsyn_rss: 'RSS feed',
  youtube: 'YouTube channel page',
  mp3_url_prober: 'MP3 URL probe'
};

// Sampling grid of preis_nach_fill in runs.json: seconds after our fill.
const NACH_FILL_SEKUNDEN = ['0', '30', '60', '120', '300', '900'];

function medianVon(werte) {
  const w = werte.filter((v) => typeof v === 'number' && !isNaN(v)).sort((a, b) => a - b);
  if (!w.length) return null;
  const mitte = Math.floor(w.length / 2);
  return w.length % 2 ? w[mitte] : (w[mitte - 1] + w[mitte]) / 2;
}

function sekundenText(s) {
  if (s == null) return '—';
  const v = Math.round(+s);
  if (v >= 3600) return (v / 3600).toFixed(1) + ' h';
  if (v >= 120) return (v / 60).toFixed(1) + ' min';
  return v + ' s';
}

// Episode title without the internal parentheticals "(kanalseite)" and
// "(URL-Prober)"; the drop source moves into a chip. Empty title → profile.
export function episodenTitel(r) {
  const roh = String((r && r.episode_titel) || '').replace(/\s*\((kanalseite|url-prober)\)\s*/gi, ' ').replace(/\s{2,}/g, ' ').trim();
  return roh || String((r && r.profil) || '');
}

// Event link when the payload carries one: an explicit url, else the
// Polymarket event slug. Nothing is guessed beyond that.
function episodenUrl(r) {
  if (!r) return '';
  if (r.url) return String(r.url);
  if (r.event_url) return String(r.event_url);
  if (r.event_slug) return 'https://polymarket.com/event/' + encodeURIComponent(String(r.event_slug));
  return '';
}

// Cents between the price of the traded side t seconds after our fill and our
// average fill price; null when either is missing.
function nachFillDelta(b, sek) {
  const pfad = b && b.preis_nach_fill;
  if (!pfad || typeof pfad !== 'object' || typeof pfad[sek] !== 'number' || b.avg_fill_preis == null) return null;
  return Math.round((pfad[sek] - +b.avg_fill_preis) * 100);
}

// The quoted word(s) of a mentions question, e.g. 'Will "Korea" or "Korean" be
// said…' → 'Korea / Korean'; otherwise the question cut short.
function kurzFrage(frage) {
  const s = String(frage || '');
  const zitate = [];
  const re = /"([^"]+)"/g;
  let m;
  while ((m = re.exec(s)) !== null) zitate.push(m[1]);
  if (zitate.length) return zitate.join(' / ');
  return s.length > 28 ? s.slice(0, 27) + '…' : s;
}

// FIRST TAKER: from the per-bet race fields (fremde_davor = foreign trades
// between drop and our fill, verfolger_s = seconds to the next buyer). Falls
// back to the per-run race aggregates; says so when neither is there.
export function firstTakerKpi(payload) {
  const runs = payload && Array.isArray(payload.runs) ? payload.runs : [];
  let mitTape = 0;
  let erste = 0;
  const verfolger = [];
  runs.forEach((r) => (r.wetten || []).forEach((b) => {
    if (b.fremde_davor == null || isNaN(+b.fremde_davor)) return;
    mitTape += 1;
    if (+b.fremde_davor === 0) erste += 1;
    if (b.verfolger_s != null && !isNaN(+b.verfolger_s)) verfolger.push(+b.verfolger_s);
  }));
  if (mitTape) {
    const med = medianVon(verfolger);
    return {
      value: erste + ' of ' + mitTape,
      sub: 'first on the traded side · ' + mitTape + ' tape-reconciled bets · median ' + (med != null ? sekundenText(med) : '—') + ' to the next buyer'
    };
  }
  let y = 0;
  let x = 0;
  const mediane = [];
  runs.forEach((r) => {
    const race = r && r.race;
    if (!race || race.wetten_mit_tape == null) return;
    y += +race.wetten_mit_tape || 0;
    x += +race.first_on || 0;
    if (race.median_verfolger_s != null) mediane.push(+race.median_verfolger_s);
  });
  if (y) {
    const med = medianVon(mediane);
    return { value: x + ' of ' + y, sub: 'first on the traded side · run-level race fields · median of run medians ' + (med != null ? sekundenText(med) : '—') + ' to the next buyer' };
  }
  return { value: '—', sub: runs.length ? 'no race fields (fremde_davor, verfolger_s, race) in runs.json' : 'runs.json not loaded' };
}

// One-row reconciliation: log stake vs wallet buys, log PnL vs wallet net,
// plus why they differ and the address anyone can check.
function abgleichTabelleHtml(payload, agg) {
  const geld = (v, vorzeichen) => {
    if (v == null || isNaN(+v)) return '—';
    const abs = num(Math.abs(+v).toFixed(2));
    if (!vorzeichen) return '$' + abs;
    return (+v >= 0 ? '+$' : '-$') + abs;
  };
  const stand = agg.wallet_abgleich_stand ? String(agg.wallet_abgleich_stand) : '';
  // Runs whose first fill came after the wallet reconciliation date are
  // log-only: the two columns do not cover the same set of runs.
  const runs = Array.isArray(payload.runs) ? payload.runs : [];
  const nachStand = stand
    ? runs.filter((r) => {
      const fills = (r.wetten || []).map((b) => String(b.fill_ts_utc || '')).filter(Boolean).sort();
      return fills.length && fills[0].slice(0, 10) > stand;
    }).length
    : 0;
  const zelle = (label, wert, farbe) =>
    '<div><div style="' + M + '; font-size:9px; letter-spacing:.13em; color:rgba(255,255,255,.4)">' + esc(label) + '</div>'
    + '<div style="' + M + '; font-size:15px; margin-top:5px; color:' + (farbe || '#fff') + '; white-space:nowrap">' + esc(wert) + '</div></div>';
  const farbeVon = (v) => (v == null ? '#fff' : +v >= 0 ? '#C8F542' : '#FF4545');
  return '<div style="background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:12px; margin-top:12px; padding:14px 18px">'
    + '<div style="' + M + '; font-size:10px; letter-spacing:.14em; color:#4F8EF7">RECONCILIATION · LOG VS WALLET' + (stand ? ' · WALLET AS OF ' + esc(stand) : '') + '</div>'
    + '<div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(150px, 1fr)); gap:14px; margin-top:12px">'
    + zelle('LOG STAKE', geld(agg.einsatz_usd, false))
    + zelle('WALLET BUYS', geld(agg.wallet_kaeufe_usd, false))
    + zelle('LOG-RECONSTRUCTED PNL', geld(agg.realisierter_pnl_usd, true), farbeVon(agg.realisierter_pnl_usd))
    + zelle('WALLET-RECONCILED NET', geld(agg.wallet_netto_usd, true), farbeVon(agg.wallet_netto_usd))
    + '</div>'
    + '<div style="font-size:12.5px; color:rgba(255,255,255,.6); margin-top:12px; line-height:1.6; max-width:860px">'
    + 'Why they differ: where the FAK order status returned no fill price, the log reconstruction assumes the price cap — the order response <span style="' + M + '">price</span> is the cap, not the fill — which overstates the stake and understates the shares; the wallet statement is the cash truth (post-mortem 2026-07-18, "Log reconstruction diverged from the wallet statement").'
    + (stand ? ' Wallet columns are as of ' + esc(stand) + (nachStand ? '; ' + nachStand + ' run' + (nachStand === 1 ? '' : 's') + ' with fills after that date ' + (nachStand === 1 ? 'is' : 'are') + ' log-only, so the two columns do not cover the same set of runs.' : '.') : '')
    + '</div>'
    + '<div style="' + M + '; font-size:10.5px; color:rgba(255,255,255,.45); margin-top:8px; line-height:1.6">'
    + 'Wallet ' + LIVE_RUN_WALLET + ' · anyone can rerun the check against the public Polymarket Data API for this address.'
    + '</div></div>';
}

// Post-fill price paths, one line per bet, coloured by outcome. Bets without a
// recorded path are counted, not drawn.
function postFillPfadeHtml(payload) {
  const runs = payload && Array.isArray(payload.runs) ? payload.runs : [];
  if (!runs.length) return '';
  const serien = [];
  let ohnePfad = 0;
  let gesamt = 0;
  runs.forEach((r) => (r.wetten || []).forEach((b) => {
    gesamt += 1;
    const pfad = b.preis_nach_fill;
    const werte = pfad && typeof pfad === 'object'
      ? NACH_FILL_SEKUNDEN.map((k) => (typeof pfad[k] === 'number' ? pfad[k] : null))
      : [];
    if (!werte.some((w) => typeof w === 'number')) { ohnePfad += 1; return; }
    const farbe = !b.aufgeloest ? '#95A0AB' : b.gewonnen ? '#C8F542' : '#FF4545';
    serien.push({ name: kurzFrage(b.frage) + ' · ' + String(b.seite || ''), werte, farbe });
  }));
  if (!gesamt) return '';
  const chart = serien.length ? linien({
    titel: 'POST-FILL PRICE PATH · ' + serien.length + ' OF ' + gesamt + ' BETS',
    einheit: 'price of the traded side after our fill · lime won, red lost, grey open',
    hinweis: 'x = seconds after fill' + (ohnePfad ? ' · ' + ohnePfad + ' bet' + (ohnePfad === 1 ? '' : 's') + ' without a recorded path' : ''),
    x: NACH_FILL_SEKUNDEN.map((s) => s + ' s'),
    serien
  }) : '';
  if (!chart) {
    return '<div style="background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:12px; margin-top:12px; padding:14px 18px; ' + M + '; font-size:11px; color:rgba(255,255,255,.45)">'
      + 'No post-fill price paths in this payload — runs.json carries them per bet under wetten[].preis_nach_fill (0…900 s).</div>';
  }
  return '<div style="margin-top:12px">' + chart + '</div>';
}

// Repricing after the drop, one step curve per bet from repricing[].punkte
// ([seconds after drop, price of the traded side]). Small multiples.
function repricingKurvenHtml(payload) {
  const runs = payload && Array.isArray(payload.runs) ? payload.runs : [];
  if (!runs.length) return '';
  const kurven = [];
  runs.forEach((r) => {
    const liste = Array.isArray(r.repricing) ? r.repricing : [];
    liste.forEach((e) => {
      const punkte = Array.isArray(e && e.punkte)
        ? e.punkte.filter((p) => Array.isArray(p) && p.length === 2 && typeof p[1] === 'number').map((p) => ({ label: sekundenText(p[0]), wert: p[1] }))
        : [];
      if (punkte.length < 2) return;
      const meta = [];
      if (e.fill_nach_s != null) meta.push('our fill ' + sekundenText(e.fill_nach_s) + ' after drop');
      if (e.time_to_priced_s != null) meta.push('priced in after ' + sekundenText(e.time_to_priced_s));
      kurven.push(stepKurve({
        titel: (kurzFrage(e.frage) + ' · ' + String(e.seite || '')).toUpperCase(),
        einheit: String(r.profil || ''),
        hinweis: meta.join(' · ') || (punkte.length + ' points'),
        farbe: '#4F8EF7',
        punkte
      }));
    });
  });
  if (!kurven.length) {
    return '<div style="background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:12px; margin-top:14px; padding:14px 18px; ' + M + '; font-size:11px; color:rgba(255,255,255,.45)">'
      + 'No repricing paths in this payload — runs.json carries them per run under repricing[].punkte.</div>';
  }
  return '<div style="margin-top:14px">'
    + '<div style="' + M + '; font-size:10.5px; letter-spacing:.14em; color:#4F8EF7; margin-bottom:4px">REPRICING AFTER THE DROP · ' + kurven.length + (kurven.length === 1 ? ' BET' : ' BETS') + '</div>'
    + '<div style="font-size:12px; color:rgba(255,255,255,.5); margin-bottom:10px; line-height:1.5">Price of the traded side against seconds after the drop, from the public tape; the caption names when our fill landed and when the market had priced the outcome in.</div>'
    + '<div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(320px, 1fr)); gap:12px">' + kurven.join('') + '</div>'
    + '</div>';
}

// Delayed-entry series (extras.timing_decay, attached by the API) as lines.
// Static payloads without extras render nothing here; the table in the sizing
// tab says where the series would come from.
function timingDecayLinienHtml(payload) {
  const decay = payload && payload.extras && Array.isArray(payload.extras.timing_decay) ? payload.extras.timing_decay : [];
  if (decay.length < 2) return '';
  const chart = linien({
    titel: 'SAME MODEL, DELAYED ENTRY · SIMULATED PNL BY DELAY',
    einheit: 'USD · simulation on log-estimated fills, not cash',
    hinweis: decay[0].n_bets != null ? 'n ' + decay[0].n_bets + ' bets at +0 s' : '',
    x: decay.map((t) => '+' + t.delay_s + ' s'),
    serien: [
      { name: 'simulated PnL (USD)', farbe: '#C8F542', werte: decay.map((t) => (typeof t.sim_pnl_usd === 'number' ? t.sim_pnl_usd : null)) }
    ]
  });
  return chart ? '<div style="margin-top:14px">' + chart + '</div>' : '';
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

// ---------------------------------------------------------------- per-study extras (dispatched by slug)
// Diagramme und Zusatzbloecke der Studien, die ueber den generischen Pfad
// rendern (Kacheln, Tabelle, Knoepfe). Was hier steht, kommt zwischen die
// Kacheln und die Tabelle. Jede Funktion gibt '' zurueck, wenn die Nutzlast
// nichts hergibt — und sagt dann in einer Zeile, welches Feld fehlt.
function studienExtrasHtml(slug, payload) {
  if (!payload) return '';
  if (slug === 'mentions-latency') return mentionsExtrasHtml(payload);
  if (slug === 'pilot') return pilotExtrasHtml(payload);
  if (slug === 'pipeline-forward') return pipelineHeadlineHtml(payload) + pipelineRegelnHtml(payload);
  return '';
}

const KARTE = 'background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:12px';

function hinweisKarte(text) {
  return '<div style="' + KARTE + '; margin-top:14px; padding:14px 18px; ' + M + '; font-size:11px; color:rgba(255,255,255,.45); line-height:1.6">' + esc(text) + '</div>';
}

// ---- mentions latency: two bar charts with a median line, the exclusions,
// and the one-line method note.
function mentionsExtrasHtml(payload) {
  const faelle = Array.isArray(payload.faelle) ? payload.faelle : [];
  const ausschluesse = Array.isArray(payload.ausschluesse) ? payload.ausschluesse : [];
  const balken = (feld, titel) => {
    const punkte = faelle
      .filter((f) => f && f[feld] != null && !isNaN(+f[feld]))
      .map((f) => ({ label: String(f.event || '—'), wert: +f[feld], art: 'summe' }))
      .sort((a, b) => a.wert - b.wert);
    if (!punkte.length) return '';
    const werte = punkte.map((p) => p.wert);
    const median = medianVon(werte);
    const lo = Math.min(...werte);
    const hi = Math.max(...werte);
    return diagramm({
      titel: titel + ' · n ' + punkte.length,
      einheit: 'minutes after the content drop · linear scale, ' + fmtZahl(lo) + ' to ' + fmtZahl(hi) + ' min · dashed line = median ' + fmtZahl(median),
      referenz: median,
      referenz_label: 'median ' + fmtZahl(median) + ' min',
      punkte
    });
  };
  const reaktion = balken('minuten_bis_erste_reaktion', 'MINUTES TO FIRST REACTION (≥ 2¢ MOVE) PER EVENT');
  const konvergenz = balken('minuten_bis_konvergenz', 'MINUTES TO CONVERGENCE PER EVENT');
  const charts = reaktion || konvergenz
    ? '<div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(360px, 1fr)); gap:12px; margin-top:14px">' + reaktion + konvergenz + '</div>'
    : hinweisKarte('No reaction or convergence minutes in this payload — mentions_latenz.json carries them per event under faelle[].minuten_bis_erste_reaktion and minuten_bis_konvergenz.');
  const methode = '<div style="' + KARTE + '; margin-top:12px; padding:14px 18px">'
    + '<div style="' + M + '; font-size:10px; letter-spacing:.14em; color:#4F8EF7">HOW TO READ IT</div>'
    + '<div style="font-size:12.5px; color:rgba(255,255,255,.65); margin-top:8px; line-height:1.6; max-width:860px">'
    + 'First reaction is the first move of at least 2¢ after the content went live; convergence is the time until the price had settled on the outcome that later resolved, as measured by the daily run'
    + (payload.hinweis ? ' — the published note reads: "' + esc(payload.hinweis) + '"' : '')
    + '. The RESOLVED column shows the outcome the market settled to; the tradeable window is the hours between first reaction and convergence in which the outcome was still priced below certainty. Both bar charts use a linear axis — one slow event stretches the scale, so read the median line, not the longest bar.'
    + '</div></div>';
  const ausschlussHtml = ausschluesse.length
    ? '<div style="border:1px solid rgba(255,255,255,.09); border-radius:12px; margin-top:12px; overflow:hidden">'
      + '<div style="padding:10px 16px; background:#10151A; border-bottom:1px solid rgba(255,255,255,.09); ' + M + '; font-size:10px; letter-spacing:.12em; color:#F5A623">EXCLUDED EVENTS · ' + ausschluesse.length + ' <span style="color:rgba(255,255,255,.35); letter-spacing:0">· listed, not counted in the medians</span></div>'
      + ausschluesse.map((a) =>
        '<div style="display:grid; grid-template-columns:1fr auto; gap:12px; padding:9px 16px; border-bottom:1px solid rgba(255,255,255,.05)">'
        + '<div style="' + M + '; font-size:12px; color:rgba(255,255,255,.75)">' + esc(String((a && a.event) || '—')) + '</div>'
        + '<div style="' + M + '; font-size:11px; color:#F5A623">' + esc(ausschlussText(a && a.status)) + '</div></div>').join('')
      + '</div>'
    : hinweisKarte('No exclusions listed in mentions_latenz.json (ausschluesse is empty).');
  return charts + methode + ausschlussHtml;
}

// Exclusion status codes of mentions_latenz.json in plain words; unknown codes
// are shown as they are.
function ausschlussText(status) {
  const s = String(status || '');
  const KARTEI = {
    ausgeschlossen_zuordnungsambiguitaet: 'excluded · ambiguous mapping between content and market',
    ausgeschlossen_keine_daten: 'excluded · no price data',
    ausgeschlossen_kein_drop: 'excluded · no drop timestamp'
  };
  return KARTEI[s] || (s ? s.replace(/^ausgeschlossen_?/, 'excluded · ').replace(/_/g, ' ') : '—');
}

// ---- pilot: English field values, slippage chart, watcher funnel, and the
// honest line where the equity chart would be.
const PILOT_WOERTER = [
  [/haelt bis zur aufloesung \(protokoll\)/i, 'held to resolution (protocol)'],
  [/haelt bis zur aufloesung/i, 'held to resolution'],
  [/aufloesung/gi, 'resolution'],
  [/protokoll/gi, 'protocol'],
  [/automatisiert/gi, 'automated'],
  [/manuell/gi, 'manual'],
  [/offen/gi, 'open'],
  [/geschlossen/gi, 'closed'],
  [/^arm(\d)$/i, 'arm $1']
];

export function pilotEnglisch(text) {
  let s = String(text == null ? '' : text);
  PILOT_WOERTER.forEach(([re, ersatz]) => { s = s.replace(re, ersatz); });
  return s;
}

// Slippage in cents: the payload's own slippage field (execution minus signal
// price) or, failing that, the difference of the two prices.
function pilotSlippageCents(t) {
  if (!t) return null;
  if (t.slippage != null && t.slippage !== '' && !isNaN(+t.slippage)) return Math.round(+t.slippage * 1000) / 10;
  if (t.ausfuehrungspreis === '' || t.signalpreis === '' || t.ausfuehrungspreis == null || t.signalpreis == null) return null;
  const a = +t.ausfuehrungspreis;
  const b = +t.signalpreis;
  if (isNaN(a) || isNaN(b)) return null;
  return Math.round((a - b) * 1000) / 10;
}

// Watcher counters of pilot.json in plain words. Unknown keys are humanised,
// not dropped.
const WATCHER_TEXT = {
  maerkte: 'markets scanned',
  gekappt: 'cut off by the per-run signal cap',
  arm2_bereits_abgelaufen: 'arm 2 · already expired',
  arm1_bereits_signalisiert: 'arm 1 · already signalled',
  bereits_gehandelt: 'already traded (max 1 per market)',
  arm2_gamma_vorfilter: 'arm 2 · failed the Gamma pre-filter',
  arm2_preis_ausserhalb_090_097: 'arm 2 · price outside 0.90–0.97',
  arm2_aufloesungsregel_unklar: 'arm 2 · resolution rule unclear',
  arm1_preis_ueber_097: 'arm 1 · price above 0.97',
  arm2_tiefe_unter_20: 'arm 2 · book depth under $20',
  'arm2:signal': 'arm 2 signals',
  'arm1:kandidat_referenz_pruefen': 'arm 1 candidates (reference to verify)'
};
function watcherText(key) {
  return WATCHER_TEXT[key] || String(key).replace(/^arm(\d)[:_]/, 'arm $1 · ').replace(/_/g, ' ');
}

function pilotExtrasHtml(payload) {
  const trades = Array.isArray(payload.trades) ? payload.trades : [];
  const teile = [];

  // The promised chart has no series: say so instead of drawing one.
  const offen = trades.filter((t) => !t.exit_zeit_utc && !t.exit_preis).length;
  teile.push(hinweisKarte('PILOT EQUITY VS RULE ADHERENCE: no series — pilot.json carries no equity curve'
    + (trades.length ? ' and ' + offen + ' of ' + trades.length + ' positions exit only through resolution, so no equity path exists yet' : '')
    + '. Below instead: execution against signal price per trade, and the watcher funnel of the last run.'));

  // Slippage per trade, execution minus signal, in cents. Positive = paid more.
  const punkte = trades.map((t) => ({ t, c: pilotSlippageCents(t) })).filter((x) => x.c != null)
    .map((x) => ({
      label: kurzFrage(x.t.markt_frage).slice(0, 34) + ' · ' + String(x.t.seite || ''),
      wert: x.c,
      art: x.c > 0 ? 'kosten' : 'gewinn'
    }));
  if (punkte.length) {
    const werte = punkte.map((p) => p.wert);
    const mittel = werte.reduce((a, v) => a + v, 0) / werte.length;
    const teurer = werte.filter((v) => v > 0).length;
    teile.push(diagramm({
      titel: 'SLIPPAGE PER TRADE · EXECUTION MINUS SIGNAL PRICE · n ' + punkte.length,
      einheit: 'cents · red = paid more than the signal price · ' + teurer + ' of ' + punkte.length + ' worse than signal · mean ' + (mittel >= 0 ? '+' : '') + mittel.toFixed(2) + '¢',
      referenz: Math.round(mittel * 100) / 100,
      referenz_label: 'mean ' + (mittel >= 0 ? '+' : '') + mittel.toFixed(2) + '¢',
      punkte
    }));
  } else if (trades.length) {
    teile.push(hinweisKarte('No signal/execution prices in the trades (signalpreis, ausfuehrungspreis) — no slippage chart.'));
  }

  // Watcher funnel from the last read-only run.
  const stat = payload.watcher_statistik && typeof payload.watcher_statistik === 'object' ? payload.watcher_statistik : null;
  const signale = payload.signal_zaehler && typeof payload.signal_zaehler === 'object' ? payload.signal_zaehler : null;
  if (stat || signale) {
    const fp = [];
    if (stat && stat.maerkte != null) fp.push({ label: watcherText('maerkte'), wert: +stat.maerkte, art: 'summe' });
    if (stat) {
      Object.entries(stat).filter(([k]) => k !== 'maerkte').sort((a, b) => (+b[1]) - (+a[1]))
        .forEach(([k, v]) => { if (v != null && !isNaN(+v)) fp.push({ label: watcherText(k), wert: +v, art: 'kosten' }); });
    }
    if (signale) {
      Object.entries(signale).sort((a, b) => (+b[1]) - (+a[1]))
        .forEach(([k, v]) => { if (v != null && !isNaN(+v)) fp.push({ label: watcherText(k), wert: +v, art: 'gewinn' }); });
    }
    const lauf = payload.watcher_lauf_ts_utc ? String(payload.watcher_lauf_ts_utc).slice(0, 16).replace('T', ' ') + ' UTC' : '';
    const chart = diagramm({
      titel: 'WATCHER FUNNEL · LAST RUN' + (lauf ? ' ' + lauf : ''),
      einheit: 'markets · blue scanned, red rejected (reason), lime signals',
      punkte: fp
    });
    if (chart) {
      const summe = signale ? Object.values(signale).reduce((a, v) => a + (+v || 0), 0) : 0;
      teile.push('<div style="' + KARTE + '; margin-top:14px; padding:14px 18px">'
        + '<div style="' + M + '; font-size:10px; letter-spacing:.14em; color:#4F8EF7">READ-ONLY WATCHER · WHAT THE SCAN THREW OUT</div>'
        + '<div style="font-size:12.5px; color:rgba(255,255,255,.6); margin-top:8px; line-height:1.6; max-width:860px">'
        + (stat && stat.maerkte != null ? num(stat.maerkte) + ' markets scanned' : 'markets scanned: not in the file')
        + (signale ? ' · ' + num(summe) + ' rule matches (' + Object.entries(signale).map(([k, v]) => num(v) + ' ' + watcherText(k)).join(', ') + ')' : '')
        + '. Signals are rule matches, not recommendations; each rejection reason is a pre-registered gate.</div>'
        + '<div style="margin-top:12px">' + chart + '</div></div>');
    }
  } else {
    teile.push(hinweisKarte('No watcher counters in pilot.json (watcher_statistik, signal_zaehler) — no funnel drawn.'));
  }

  // The API-side evaluation (auswertung), when served.
  teile.push(pilotAuswertungHtml(payload));
  return teile.join('');
}

// ---------------------------------------------------------------- methodology (slug methodology, audit.json)
// Vier Zaehler aus audit.json und der Methodentext der Studien. Der Text ist
// Dokumentation, keine Messung: er steht auch, wenn audit.json fehlt — die
// Kacheln sagen dann, welche Datei fehlt.
const ONE_PAGER_URL = 'https://github.com/Pablozh123/prediction-market-terminal/blob/main/docs/research/ONE_PAGER.md';

function renderMethodology(T, payload, study) {
  const stamp = payload && payload.stand_utc ? String(payload.stand_utc).slice(0, 16).replace('T', ' ') + ' UTC' : study.stamp;
  const note = payload && payload.hinweis ? payload.hinweis : study.note;
  const stats = buildStudyStats(7, payload) || [
    { label: 'AUDIT ENTRIES', value: '—', note: 'audit.json not loaded' },
    { label: 'PROMPT HASHES', value: '—', note: 'audit.json not loaded' },
    { label: 'OUTPUT HASHES', value: '—', note: 'audit.json not loaded' },
    { label: 'BACKEND', value: '—', note: 'audit.json not loaded' }
  ];
  const backend = payload && payload.backend_zaehler && typeof payload.backend_zaehler === 'object' ? payload.backend_zaehler : null;
  const mockN = backend && backend.mock != null ? +backend.mock : 0;
  const backendGesamt = backend ? Object.values(backend).reduce((a, v) => a + (+v || 0), 0) : 0;
  const rollen = payload && payload.rollen_zaehler && typeof payload.rollen_zaehler === 'object' ? payload.rollen_zaehler : null;
  const backendSatz = backend
    ? (mockN && mockN === backendGesamt
      ? 'audit.json says it plainly: backend counter mock ' + num(mockN) + ' of ' + num(backendGesamt) + ' entries' + (rollen ? ' (' + Object.entries(rollen).map(([k, v]) => k + ' ' + num(v)).join(', ') + ')' : '') + ' — every case narrative and skeptic review in the review queue is mock output, not a live model run.'
      : 'Backend counter in audit.json: ' + Object.entries(backend).map(([k, v]) => k + ' ' + num(v)).join(', ') + (mockN ? ' — the mock share of the review-queue narratives is not a live model run.' : '.'))
    : 'audit.json is not loaded here, so the backend of the last agent run cannot be stated on this page; the default is the deterministic mock.';

  const abschnitt = (titel, text) =>
    '<div style="' + KARTE + '; padding:16px 18px">'
    + '<div style="' + M + '; font-size:10px; letter-spacing:.14em; color:#4F8EF7">' + esc(titel) + '</div>'
    + '<div style="font-size:13px; color:rgba(255,255,255,.72); margin-top:8px; line-height:1.65">' + text + '</div></div>';
  const mono = (t) => '<span style="' + M + '">' + esc(t) + '</span>';

  const sektionen = [
    abschnitt('WHAT A STUDY OBSERVATION IS',
      'A study runs over the recorded books, never over a live feed. Each recorded snapshot is checked for the study\'s condition — say, a book imbalance past a fixed threshold. When it fires, the side it leans to is written down and compared against where the mid actually sat a fixed horizon later (300 s in the headline cell), with no decision delay between the firing and the entry price. Firings where nothing moved at all are counted separately so they cannot pad the score. Where a study runs several horizon and delay cells over the same snapshots, the cells are reported one by one and never pooled: every snapshot feeds each of them, and a pooled n would exceed the number of snapshots it came from.'),
    abschnitt('HIT RATE AND WILSON LOWER BOUND',
      'The hit rate is the share of firings that pointed the right way. Every hit rate is reported with the lower bound of its 95% Wilson score interval, so a small sample cannot claim more than it can support: 55.5% on 205,835 firings carries a lower bound of 55.2 and is real; 51.7% for signed flow at the same cell carries 51.3 and, with a gross edge that is negative before costs, is not usable. Below the minimum sample the number stays visible and reads as a hint only.'),
    abschnitt('ROUND-TRIP COST = SPREAD + FEE',
      'For each firing the price move is converted to cents per share. Then half the spread standing in the book at decision time is subtracted, and the fee schedule of that market\'s category on top. What remains is the net. In the headline cell the round trip is 2.58 cents — 1.646 cents of fee and 0.938 of spread — against a mean gross edge of 0.09 cents per firing, which is why a signal can be real and untradable at the same time.'),
    abschnitt('FILL MODELS: TOUCH VS TAPE, AND THE MARKOUT IDENTITY',
      'Two fill models bracket the truth. The touch model assumes a fill whenever the price reaches the quote; the tape model assumes a fill only when a real print happened there. Each fill is marked out against the mid a short time later; the difference between what the quote earned and where the price went is the adverse selection. The decomposition is an identity, not an estimate: spread capture plus markout plus late drift reconstructs the terminal mark-to-mid exactly, asserted to nine decimal places in the tests. When the two models sit on opposite sides of zero, the sign would be chosen by the fill assumption rather than by the data, and the verdict is "not identified".'),
    abschnitt('BLOCK BOOTSTRAP',
      'Daily totals are resampled in blocks so the interval respects that days are not independent of themselves. Below three days of data the block bootstrap cannot run at all, which is why the earlier two-day market-making study reported the fill-model disagreement as a caveat rather than an interval; with five days it runs and places the two fill models on opposite sides of zero with neither interval touching it.'),
    abschnitt('CROSS-VENUE MATCHING AND FEE CURVES',
      'Markets on the two venues are matched by what the question actually asks, not by wording overlap; two apparent 79 and 64 cent edges were mismatched pairs and stay in the report as the lesson. For each surviving pair both books are priced, each venue\'s own fee curve is subtracted, size is capped by the real depth, and the remainder is annualised over the days until settlement. Both rulebooks are then put side by side, because a resolution clause one side carries and the other does not is precisely where a hedge stops hedging.'),
    abschnitt('WALLET RECONCILIATION VS LOG',
      'The live-run PnL is shown twice on purpose. The log-reconstructed figure comes from the bot\'s own logs; where the FAK order status returned no fill price, it assumes the price cap (the order response ' + mono('price') + ' is the cap, not the fill), which overstates the stake and understates the shares. The wallet-reconciled net is what the on-chain wallet statement shows and is the cash truth, dated by its reconciliation day. Both are labelled wherever they appear, and the wallet address ' + mono(LIVE_RUN_WALLET) + ' is public, so anyone can rerun the check against the Polymarket Data API.'),
    abschnitt('PRE-REGISTRATION POLICY',
      'Pre-registered means: hypothesis, primary metric, success threshold, cohort and exclusion rules are fixed before the first look at the outcome period, and externally time-stamped. Results are published in both directions — a failure and an insufficient sample are both citable results — and every analysis outside the pre-registered primary test is marked exploratory. The pilot froze its rules before the first trade and reports its own deviation from the frozen text (stake halved) as a deviation; the track-record validation is drafted for AsPredicted and listed as pending until submitted.'),
    abschnitt('AGENT LAYER GUARDRAILS',
      'Agents read exclusively through the MCP read layer: four read-only tools, at most 50 rows per response, wallet addresses masked. The skeptic can only lower a case\'s priority (deduction between -0.3 and 0), never raise it; recommendations come from a fixed whitelist (watch, check source, escalate to a human); a redaction gate aborts a publish that contains wallet-address patterns or key-like strings; and the default backend is a deterministic mock with no network access — productive LLM mode is an explicit flag. '
      + '<span style="color:#F5A623">' + esc(backendSatz) + '</span>')
  ];

  return '<div style="padding:22px 24px">'
    + '<div style="display:flex; align-items:flex-start; justify-content:space-between; gap:24px">'
    + '<div style="max-width:720px">'
    + '<div style="font-size:20px; font-weight:600">' + esc(study.title) + '</div>'
    + '<div style="font-size:13.5px; color:rgba(255,255,255,.6); margin-top:8px; line-height:1.5">' + esc(note) + '</div></div>'
    + '<div style="' + M + '; font-size:10.5px; color:rgba(255,255,255,.4); border:1px solid rgba(255,255,255,.14); border-radius:6px; padding:6px 10px; white-space:nowrap">' + esc(stamp) + '</div></div>'
    + '<div style="display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-top:18px">'
    + stats.map((x) =>
      '<div style="' + KARTE + '; border-radius:10px; padding:14px 16px">'
      + '<div style="' + M + '; font-size:9.5px; letter-spacing:.13em; color:rgba(255,255,255,.45)">' + esc(x.label) + '</div>'
      + '<div style="' + M + '; font-size:21px; margin-top:7px">' + esc(x.value) + '</div>'
      + '<div style="' + M + '; font-size:10.5px; color:rgba(255,255,255,.4); margin-top:4px">' + esc(x.note) + '</div></div>'
    ).join('')
    + '</div>'
    + (payload ? '' : '<div style="margin-top:12px">' + leerZeile(herkunftSatz(null, 'public/data/audit.json')) + '</div>')
    + '<div style="' + M + '; font-size:10.5px; letter-spacing:.14em; color:#4F8EF7; margin:20px 0 10px">HOW THE STUDIES ARE MEASURED</div>'
    + '<div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(380px, 1fr)); gap:12px">' + sektionen.join('') + '</div>'
    + '<div style="display:flex; gap:10px; margin-top:14px; flex-wrap:wrap">'
    + '<a href="' + ONE_PAGER_URL + '" target="_blank" rel="noopener" class="hv-bd35" style="font-size:13px; color:#fff; border:1px solid rgba(255,255,255,.2); border-radius:8px; padding:10px 16px; text-decoration:none; display:inline-block">Read the full one-pager ↗</a>'
    + '</div>'
    + studienKnoepfe(T, T.studies.findIndex((st) => studienSlug(st) === 'methodology'))
    + '</div>';
}

// ---------------------------------------------------------------- reference links (post-mortems, field notes)
// "PR #12", "commit 8af07d6" and docs/research/<file>.md become links where the
// target is derivable; everything else stays plain text.
const SISTER_REPO = 'https://github.com/Pablozh123/multi-agent-orchestration-informational-efficiency';
const TERMINAL_REPO = 'https://github.com/Pablozh123/prediction-market-terminal';

export function referenzLinksHtml(text) {
  const roh = String(text == null ? '' : text);
  if (!roh) return '';
  const muster = /(PR #(\d+))|(commit ([0-9a-f]{7,40}))|(docs\/research\/[A-Za-z0-9_.\-]+\.md)/g;
  let raus = '';
  let letzte = 0;
  let m;
  const link = (href, label) => '<a href="' + esc(href) + '" target="_blank" rel="noopener" style="color:#4F8EF7; text-decoration:none">' + esc(label) + ' ↗</a>';
  while ((m = muster.exec(roh)) !== null) {
    raus += esc(roh.slice(letzte, m.index));
    if (m[1]) raus += link(SISTER_REPO + '/pull/' + m[2], m[1]);
    else if (m[3]) raus += link(SISTER_REPO + '/commit/' + m[4], m[3]);
    else if (m[5]) raus += link(TERMINAL_REPO + '/blob/main/' + m[5], m[5]);
    letzte = m.index + m[0].length;
  }
  raus += esc(roh.slice(letzte));
  return raus;
}
