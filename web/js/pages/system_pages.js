// Alerts, Research (8 studies incl. live runs), Settings — ported from the
// design reference. Research tabs render the published JSON payloads from
// public/data/ when the API serves them, incl. their stand_utc stamp and note.

import { esc, num, herkunftSatz, leerZeile, EINZAHLUNGEN_USD, offeneNichtDrin, stempelBlock } from '../util.js';
import { stepKurve, diagramm, linien, kalibrierung, fmtZahl, serienFarbe } from '../charts.js';
import { renderMicrostructure } from './microstructure_page.js';

const M = "font-family:'IBM Plex Mono',monospace";
const LBL9 = M + '; font-size:10.5px; letter-spacing:.14em; color:rgba(var(--ink),.6); margin-bottom:6px';

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
  'Rule understanding': 'var(--warn)',
  'Execution': 'var(--neg-soft)',
  'Microstructure': 'var(--info)',
  'Data': 'var(--cat-teal)',
  'Infrastructure': 'var(--cat-violet)',
  'Risk discipline': 'var(--neg)',
  'Engineering maturity': 'var(--cat-blue2)',
  'Evaluation': 'var(--accent)',
  'Detection latency': 'var(--cat-gold)',
};

// Zeitstrahl der Vorfaelle. Die Seite hatte bisher keine einzige Zahl und
// keine Grafik — 5.700 Zeichen Fliesstext, in denen das Auge nirgends landet.
// Der Strahl erfindet nichts: er traegt genau die Daten, die in der Nutzlast
// stehen, und zeigt damit das, was die Karten einzeln verbergen — die
// Vorfaelle draengen sich in einer einzigen Woche. Gleiche Tage stapeln nach
// oben; jeder Punkt nennt im Tooltip seinen Titel.
function vorfallZeitstrahl(eintraege) {
  const mitDatum = eintraege.filter((e) => e && /^\d{4}-\d{2}-\d{2}$/.test(String(e.datum)));
  if (mitDatum.length < 2) return '';
  const tag = (s) => Date.UTC(+s.slice(0, 4), +s.slice(5, 7) - 1, +s.slice(8, 10)) / 86400000;
  const tage = mitDatum.map((e) => tag(String(e.datum)));
  const min = Math.min(...tage), max = Math.max(...tage);
  const spanne = Math.max(max - min, 1);
  const L = 40, R = 600, BASIS = 58;
  const x = (t) => L + ((t - min) / spanne) * (R - L);

  const proTag = {};
  const punkte = mitDatum.map((e) => {
    const t = tag(String(e.datum));
    const stapel = (proTag[t] = (proTag[t] || 0) + 1) - 1;
    const farbe = ACHSEN_FARBE[e.achse] || 'var(--muted)';
    const cy = BASIS - 10 - stapel * 13;
    return '<circle cx="' + x(t).toFixed(1) + '" cy="' + cy + '" r="5" style="fill:' + farbe + '" fill-opacity=".9">'
      + '<title>' + esc(String(e.datum) + ' · ' + (e.achse || '') + ' · ' + (e.titel || '')) + '</title></circle>'
      + '<line x1="' + x(t).toFixed(1) + '" y1="' + (cy + 5) + '" x2="' + x(t).toFixed(1) + '" y2="' + BASIS
      + '" style="stroke:' + farbe + '" stroke-opacity=".3" stroke-width="1" />';
  }).join('');

  const marken = [min, max].map((t, i) =>
    '<text x="' + x(t).toFixed(1) + '" y="' + (BASIS + 16) + '" style="fill:rgba(var(--ink),.6)" font-size="10.5" '
    + 'font-family="IBM Plex Mono, monospace" text-anchor="' + (i === 0 ? 'start' : 'end') + '">'
    + new Date(t * 86400000).toISOString().slice(0, 10) + '</text>').join('');

  return '<div style="' + KARTE + '; padding:14px 16px 8px; margin-top:14px">'
    + '<div style="' + M + '; font-size:11px; letter-spacing:.13em; color:rgba(var(--ink),.6); margin-bottom:2px">'
    + 'WHEN THEY HAPPENED · ' + (spanne + 1) + ' DAYS, ' + mitDatum.length + ' INCIDENTS · COLOUR IS THE AXIS</div>'
    + '<svg width="100%" viewBox="0 0 640 80" role="img" aria-label="Incident timeline">'
    + '<line x1="' + L + '" y1="' + BASIS + '" x2="' + R + '" y2="' + BASIS + '" style="stroke:rgba(var(--ink),.14)" stroke-width="1" />'
    + punkte + marken + '</svg></div>';
}

/** Post-Mortems: neun Vorfaelle mit Ursache, Kosten, Fix und Codeverweis. */
function renderPostmortems(payload) {
  const eintraege = (payload && payload.eintraege) || [];
  if (!eintraege.length) {
    return '<div style="padding:26px 24px">'
      + '<div style="background:var(--panel); border:1px solid rgba(var(--ink),.09); border-radius:6px; padding:22px 24px; max-width:720px">'
      + '<div style="font-size:16px; font-weight:600">No incidents published</div>'
      + '<div style="font-size:13px; color:rgba(var(--ink),.55); margin-top:10px; line-height:1.6">'
      + 'This page reads <span style="' + M + '">public/data/postmortems.json</span>.</div></div></div>';
  }

  const achsen = {};
  eintraege.forEach((e) => { achsen[e.achse] = (achsen[e.achse] || 0) + 1; });
  const chips = Object.entries(achsen).sort((a, b) => b[1] - a[1]).map(([achse, n]) =>
    '<div style="' + M + '; font-size:11px; color:' + (ACHSEN_FARBE[achse] || 'var(--muted)')
    // color-mix, not a hex alpha suffix: every value here is a var(--token),
    // and 'var(--muted)44' is not a colour — the parser dropped the whole
    // shorthand and the border simply did not exist.
    + '; border:1px solid color-mix(in srgb, ' + (ACHSEN_FARBE[achse] || 'var(--muted)') + ' 27%, transparent); border-radius:4px; padding:4px 9px">'
    + esc(achse.toUpperCase()) + ' ' + n + '</div>').join('');

  const feld = (label, wert, farbe) =>
    '<div style="margin-top:11px">'
    + '<div style="' + M + '; font-size:10.5px; letter-spacing:.13em; color:rgba(var(--ink),.55)">' + label + '</div>'
    + '<div style="font-size:12.5px; color:' + (farbe || 'rgba(var(--ink),.72)') + '; margin-top:4px; line-height:1.6">'
    + esc(wert || '—') + '</div></div>';

  const karten = eintraege.slice().sort((a, b) => String(b.datum).localeCompare(String(a.datum))).map((e) => {
    const farbe = ACHSEN_FARBE[e.achse] || 'var(--muted)';
    return '<div style="background:var(--panel); border:1px solid rgba(var(--ink),.09); border-left:2px solid ' + farbe
      + '; border-radius:6px; padding:16px 18px">'
      + '<div style="display:flex; align-items:baseline; justify-content:space-between; gap:14px; flex-wrap:wrap">'
      + '<div style="font-size:14.5px; font-weight:600; flex:1; min-width:220px">' + esc(e.titel) + '</div>'
      + '<div style="' + M + '; font-size:11px; color:' + farbe + '">' + esc(e.achse || '') + '</div></div>'
      + '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.6); margin-top:5px">'
      + esc(e.datum) + (e.profil ? ' · ' + esc(e.profil) : '') + '</div>'
      + feld('WHAT HAPPENED', e.was_passierte)
      + feld('WHAT IT COST', e.auswirkung, 'var(--neg-soft)')
      + feld('WHAT CHANGED', e.fix, 'var(--accent)')
      // "PR #12" und "commit 8af07d6" verweisen ins Schwester-Repo, Pfade
      // unter docs/research/ ins Terminal-Repo — als Links, wo ableitbar.
      + (e.referenz
        ? '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.55); margin-top:11px; '
          + 'border-top:1px solid rgba(var(--ink),.06); padding-top:9px">' + referenzLinksHtml(e.referenz) + '</div>'
        : '')
      + '</div>';
  }).join('');

  return '<div style="padding:20px 24px 36px">'
    + '<div style="font-size:13.5px; color:rgba(var(--ink),.6); line-height:1.6; max-width:820px">'
    + esc((payload && payload.hinweis) || '')
    + '</div>'
    + '<div style="display:flex; gap:7px; flex-wrap:wrap; margin-top:12px">'
    + '<div style="' + M + '; font-size:11px; color:var(--text); border:1px solid rgba(var(--ink),.2); border-radius:4px; padding:4px 9px">'
    + eintraege.length + ' INCIDENTS</div>' + chips + '</div>'
    + vorfallZeitstrahl(eintraege)
    + '<div style="display:grid; grid-template-columns:repeat(auto-fit,minmax(360px,1fr)); gap:14px; margin-top:16px">'
    + karten + '</div></div>';
}

/** Field notes: kuratierte Beobachtungen vom Tape, je Notiz Datum, Venue,
 *  Markt, Titel, Beobachtung, Mechanismus, Folge und optional ein Beleg.
 *  Nur Struktur — jede Notiz kommt aus public/data/field_notes.json. */
function renderFieldNotes(payload, study) {
  const notes = (payload && Array.isArray(payload.notes)) ? payload.notes : [];
  const kennung = payload && payload.kennzeichnung ? String(payload.kennzeichnung).toUpperCase() : 'CURATED';
  const kopf = '<div style="display:flex; align-items:flex-start; justify-content:space-between; gap:24px">'
    + '<div style="max-width:720px">'
    + '<div style="font-size:20px; font-weight:600">Field notes — what the tape taught us</div>'
    + '<div style="font-size:13.5px; color:rgba(var(--ink),.6); margin-top:8px; line-height:1.5">'
    + esc((payload && payload.hinweis) || 'Curated observations from watching the tape: what happened, the mechanism behind it, and what follows from it. Notes, not measurements — each one names its evidence or says it has none.')
    + '</div></div>'
    + '<div style="display:flex; gap:8px">'
    + '<div style="' + M + '; font-size:10.5px; letter-spacing:.1em; border-radius:4px; padding:3px 8px; color:var(--on-accent); background:var(--info)">' + esc(kennung) + '</div>'
    + stempelBlock(study, payload, '5px 10px')
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
      + '<div style="background:var(--panel); border:1px solid rgba(var(--ink),.09); border-radius:6px; padding:22px 24px; max-width:720px; margin-top:16px">'
      + '<div style="font-size:16px; font-weight:600">No field notes published yet</div>'
      + '<div style="font-size:13px; color:rgba(var(--ink),.55); margin-top:10px; line-height:1.6">'
      + 'This page reads <span style="' + M + '">public/data/field_notes.json</span>. The file is there but its '
      + '<span style="' + M + '">notes</span> list is empty, so there is nothing to show — and nothing is invented to fill the space.'
      + '</div></div></div>';
  }

  const feld = (label, wert, farbe) => (wert
    ? '<div style="margin-top:11px">'
      + '<div style="' + M + '; font-size:10.5px; letter-spacing:.13em; color:rgba(var(--ink),.55)">' + label + '</div>'
      + '<div style="font-size:12.5px; color:' + (farbe || 'rgba(var(--ink),.72)') + '; margin-top:4px; line-height:1.6">'
      + esc(wert) + '</div></div>'
    : '');

  const venues = {};
  notes.forEach((n) => { const v = String(n.venue || 'unknown venue'); venues[v] = (venues[v] || 0) + 1; });
  const chips = Object.entries(venues).sort((a, b) => b[1] - a[1]).map(([v, n]) =>
    '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.6); border:1px solid rgba(var(--ink),.18); border-radius:4px; padding:4px 9px">'
    + esc(v.toUpperCase()) + ' ' + n + '</div>').join('');

  const karten = notes.slice().sort((a, b) => String(b.date || '').localeCompare(String(a.date || ''))).map((n) =>
    '<div style="background:var(--panel); border:1px solid rgba(var(--ink),.09); border-left:2px solid var(--info); border-radius:6px; padding:16px 18px">'
    + '<div style="display:flex; align-items:baseline; justify-content:space-between; gap:14px; flex-wrap:wrap">'
    + '<div style="font-size:14.5px; font-weight:600; flex:1; min-width:220px">' + esc(n.title || '—') + '</div>'
    + '<div style="' + M + '; font-size:11px; color:var(--info)">' + esc(n.venue || '') + '</div></div>'
    + '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.6); margin-top:5px">'
    + esc(n.date || '—') + (n.market ? ' · ' + esc(n.market) : '') + '</div>'
    + feld('OBSERVATION', n.observation)
    + feld('MECHANISM', n.mechanism, 'var(--warn)')
    + feld('CONSEQUENCE', n.consequence, 'var(--accent)')
    + (n.evidence
      ? '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.55); margin-top:11px; '
        + 'border-top:1px solid rgba(var(--ink),.06); padding-top:9px">EVIDENCE · ' + referenzLinksHtml(n.evidence) + '</div>'
      : '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.5); margin-top:11px; '
        + 'border-top:1px solid rgba(var(--ink),.06); padding-top:9px">NO EVIDENCE ATTACHED · an observation, not a finding</div>')
    + '</div>'
  ).join('');

  // Ein Index vor den Karten. Die Seite war 8.400 Zeichen ohne einen einzigen
  // Ankerpunkt — jede Notiz laeuft ueber 1.500 Zeichen, und ohne Uebersicht
  // faengt man vorne an oder gar nicht. Der Index nennt je Notiz Datum, Venue,
  // Titel und ob Belege dranhaengen; danach weiss man, welche man liest.
  const belegt = notes.filter((n) => n.evidence).length;
  const index = '<div style="border:1px solid rgba(var(--ink),.09); border-radius:6px; margin-top:14px; overflow:hidden">'
    + '<div style="padding:10px 16px; background:var(--panel); border-bottom:1px solid rgba(var(--ink),.09); display:flex; align-items:baseline; justify-content:space-between; gap:14px">'
    + '<div style="' + M + '; font-size:10.5px; letter-spacing:.14em; color:var(--info)">WHAT IS IN HERE</div>'
    + '<div style="' + M + '; font-size:10.5px; color:rgba(var(--ink),.6)">' + belegt + ' of ' + notes.length + ' carry evidence</div></div>'
    + notes.slice().sort((a, b) => String(b.date || '').localeCompare(String(a.date || ''))).map((n) =>
      '<div style="display:grid; grid-template-columns:78px 104px 1fr 122px; gap:12px; align-items:baseline; padding:8px 16px; border-bottom:1px solid rgba(var(--ink),.06)">'
      + '<div style="' + M + '; font-size:11.5px; color:rgba(var(--ink),.6)">' + esc(n.date || '—') + '</div>'
      + '<div style="' + M + '; font-size:11.5px; color:var(--info); white-space:nowrap; overflow:hidden; text-overflow:ellipsis">' + esc(n.venue || '—') + '</div>'
      + '<div style="font-size:13px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="' + esc(n.title || '') + '">' + esc(n.title || '—') + '</div>'
      + '<div style="' + M + '; font-size:10.5px; text-align:right; color:' + (n.evidence ? 'var(--accent)' : 'rgba(var(--ink),.6)') + '">'
      + (n.evidence ? 'EVIDENCE' : 'NO EVIDENCE') + '</div></div>').join('')
    + '</div>';

  return '<div style="padding:22px 24px 36px">' + kopf
    + '<div style="display:flex; gap:7px; flex-wrap:wrap; margin-top:12px">'
    + '<div style="' + M + '; font-size:11px; color:var(--text); border:1px solid rgba(var(--ink),.2); border-radius:4px; padding:4px 9px">'
    + notes.length + ' NOTE' + (notes.length === 1 ? '' : 'S') + '</div>' + chips + '</div>'
    + index
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

// While the payload is still on its way (undefined: asked, not answered) the
// page says so and names the file. Rendering the "missing" state meanwhile
// flashed "file is missing" on every open of a study — and on a slow host
// stated it for seconds. Live runs and Methodology keep their own tiles
// ("not loaded"), which stay true while loading.
function ladeStudieHtml(study, datei) {
  return '<div style="padding:26px 24px">'
    + '<div style="background:var(--panel); border:1px solid rgba(var(--ink),.09); border-radius:6px; padding:22px 24px; max-width:720px">'
    + '<div style="font-size:16px; font-weight:600">' + esc(study.title) + '</div>'
    + '<div style="display:flex; align-items:center; gap:10px; margin-top:12px">'
    + '<span style="width:7px; height:7px; border-radius:50%; background:var(--warn); display:inline-block"></span>'
    + '<span style="' + M + '; font-size:11px; letter-spacing:.08em; color:var(--warn)">loading public/data/' + esc(datei || 'the study payload') + '</span></div>'
    + '<div style="font-size:12.5px; color:rgba(var(--ink),.5); margin-top:10px; line-height:1.6">The page fills in when the payload answers; nothing is shown before, and no figure is a placeholder.</div>'
    + '</div></div>';
}

function fehlendeStudieHtml(study, datei) {
  return '<div style="padding:26px 24px">'
    + '<div style="background:var(--panel); border:1px solid rgba(var(--ink),.09); border-radius:6px; padding:22px 24px; max-width:720px">'
    + '<div style="font-size:16px; font-weight:600">' + esc(study.title) + '</div>'
    + '<div style="font-size:13px; color:rgba(var(--ink),.55); margin-top:10px; line-height:1.6">'
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
      + '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.6); padding:14px 24px 0">showing signals over ' + s.thMove + '¢ moves, prints above $' + num(s.thWhale) + ', spreads under ' + s.thSpread + '¢, resolving within ' + s.thEnding + ' h' + (live && live.as_of ? ' · snapshot ' + esc(live.as_of) : '') + '</div>'
      // Der Schnitt gehoert danebengeschrieben. Eine Tabelle, die 60 von 300
      // Zeilen zeigt und das verschweigt, liest sich wie der ganze Scan.
      + (zaehlung && live.shown_limit && gesamtTreffer > live.shown_limit
        ? '<div style="' + M + '; font-size:11px; color:var(--warn); padding:6px 24px 0">'
          + 'showing the top ' + live.shown_limit + ' of ' + num(gesamtTreffer) + ' signals in this scan, ranked by severity'
          // Welche Art der Schnitt komplett verschluckt. Ohne den Zusatz
          // widerspricht die Regelkarte scheinbar der Tabelle: sie meldet
          // hundert Treffer fuer eine Art, von der keine Zeile zu sehen ist.
          + (verschluckt.length
            ? ' · none of ' + verschluckt.map((a) => esc(a[0]) + ' (' + num(a[1]) + ')').join(', ') + ' made the cut'
            : '')
          + '</div>'
        : '')
      + '<div style="border:1px solid rgba(var(--ink),.09); border-radius:6px; margin:12px 24px; overflow:hidden">'
      + '<div style="display:grid; grid-template-columns:92px 170px 1fr 110px 120px; gap:10px; padding:9px 16px; background:var(--panel); border-bottom:1px solid rgba(var(--ink),.09); ' + M + '; font-size:10.5px; letter-spacing:.12em; color:rgba(var(--ink),.6)">'
      + '<div>TIME</div><div>SIGNAL</div><div>MARKET</div><div style="text-align:right">READING</div><div style="text-align:right">VENUE</div></div>'
      + (ausgeblendet
        ? '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.6); padding:6px 24px 0">'
          + num(ausgeblendet) + ' signal' + (ausgeblendet === 1 ? '' : 's') + ' hidden by the rule switches</div>'
        : '')
      + (feed.length ? '' : leerZeile(feedAll.length ? 'No signal matches these filters.' : alarmSatz))
      + feed.map((a) =>
        '<div style="display:grid; grid-template-columns:92px 170px 1fr 110px 120px; gap:10px; align-items:center; padding:11px 16px; border-bottom:1px solid rgba(var(--ink),.06)">'
        + '<div style="' + M + '; font-size:12px; color:rgba(var(--ink),.55)">' + esc(a.time) + '</div>'
        + '<div style="' + M + '; font-size:10.5px; letter-spacing:.1em; color:var(--accent)">' + esc(a.rule) + '</div>'
        + '<div style="font-size:13px; padding-right:16px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="' + esc(a.market) + '">' + esc(a.market) + '</div>'
        + '<div style="' + M + '; font-size:12.5px; text-align:right">' + esc(a.value) + '</div>'
        + '<div style="' + M + '; font-size:11.5px; text-align:right; color:rgba(var(--ink),.6)">' + esc(a.venue) + '</div></div>'
      ).join('')
      + '</div></div>';
  } else if (s.alertTab === 'rules') {
    body = '<div style="padding:16px 24px; display:grid; grid-template-columns:repeat(3,1fr); gap:14px">'
      + rules.map((a) => {
        const on = !!s.alertsOn[a.key];
        return '<div ' + T.act(() => T.setState({ alertsOn: Object.assign({}, s.alertsOn, { [a.key]: !on }) })) + ' style="border-radius:6px; padding:15px 17px; cursor:pointer; background:var(--panel); border:1px solid ' + (on ? 'rgba(var(--accent-rgb),.35)' : 'rgba(var(--ink),.09)') + '">'
          + '<div style="display:flex; align-items:center; justify-content:space-between; gap:12px">'
          + '<div style="font-size:14.5px; font-weight:600">' + a.name + '</div>'
          + '<div style="width:38px; height:21px; flex:none; border-radius:6px; padding:2px; display:flex; background:' + (on ? 'var(--accent)' : 'rgba(var(--ink),.14)') + '; justify-content:' + (on ? 'flex-end' : 'flex-start') + '">'
          + '<div style="width:17px; height:17px; border-radius:50%; background:' + (on ? 'var(--on-accent)' : 'rgba(var(--ink),.55)') + '"></div></div></div>'
          + '<div style="font-size:12.5px; color:rgba(var(--ink),.55); margin-top:8px; line-height:1.45">' + a.desc + '</div>'
          + '<div style="' + M + '; font-size:10.5px; margin-top:12px; color:rgba(var(--ink),.6)">' + esc(trefferText(a.key, on)) + '</div></div>';
      }).join('')
      + '</div>';
  } else if (live && live.deliveries) {
    const dv = live.deliveries;
    body = '<div style="margin:16px 24px; border:1px solid rgba(var(--ink),.09); border-radius:6px; padding:22px; background:var(--panel)">'
      + '<div style="' + M + '; font-size:10.5px; letter-spacing:.14em; color:rgba(var(--ink),.55)">DELIVERY LOG</div>'
      + '<div style="font-size:13px; color:rgba(var(--ink),.6); margin-top:10px; line-height:1.5; max-width:640px">' + esc(dv.note || 'No delivery log available.') + '</div>'
      + (dv.last_scan_at ? '<div style="' + M + '; font-size:11.5px; color:rgba(var(--ink),.6); margin-top:12px">last scan ' + esc(dv.last_scan_at) + ' · ' + esc(String(dv.last_hits)) + ' hits · ' + esc(String(dv.last_sent)) + ' sent</div>' : '')
      + '</div>';
  } else {
    // Ein Zustellprotokoll ist ein Nachweis. Sechs erfundene Zeilen mit
    // Uhrzeit, Kanal und Status behaupten Versand, den es nie gab.
    body = '<div style="margin:16px 24px; border:1px solid rgba(var(--ink),.09); border-radius:6px; padding:22px; background:var(--panel)">'
      + '<div style="' + M + '; font-size:10.5px; letter-spacing:.14em; color:rgba(var(--ink),.55)">DELIVERY LOG</div>'
      + '<div style="font-size:13px; color:rgba(var(--ink),.6); margin-top:10px; line-height:1.5; max-width:640px">'
      + esc(alarmSatz) + '</div></div>';
  }

  return '<div>'
    + '<div style="padding:20px 24px 16px; border-bottom:1px solid rgba(var(--ink),.09)">'
    + '<div style="' + M + '; font-size:11px; letter-spacing:.18em; color:var(--accent)">ALERTS</div>'
    + '<h1 style="font-size:21px; line-height:1.25; margin:6px 0 0; font-weight:600; letter-spacing:-0.01em">Tell me when this happens</h1>'
    // Frueher stand hier "Switch one on and it also goes to Telegram". Der
    // Versand haengt am Scanner-Skript und an dessen Konfiguration, nicht an
    // diesen Schaltern — die entscheiden, was diese Seite zeigt.
    + '<div style="font-size:13px; color:rgba(var(--ink),.55); margin-top:9px; max-width:700px">The thresholds below are sent to the scan. The switches decide which of its signal types this page shows; Telegram delivery is configured on the scanner, not here.</div></div>'
    + '<div style="padding:16px 24px 0; display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:14px 18px">'
    + '<div><div style="' + LBL9 + '">SEARCH</div><input value="' + esc(s.alertQuery) + '" ' + T.inp((e) => T.setState({ alertQuery: e.target.value }), 'alertQuery') + ' placeholder="market, wallet, category…" style="width:100%; box-sizing:border-box; background:var(--panel); border:1px solid rgba(var(--ink),.35); border-radius:4px; padding:8px 10px; ' + M + '; font-size:11.5px; color:var(--text)" /></div>'
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
      + (holderInaktiv ? ' <span style="color:var(--warn)">· not evaluated</span>' : ''),
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
  const roh = T.liveData.research[key];
  const payload = roh || null;
  // undefined = asked and not answered yet; null/{_quelle} = answered.
  const laedt = roh === undefined;

  // Eine Zeile statt der grossen Ueberschrift auf jedem Reiter: "The studies
  // behind the terminal" plus Erklaersatz standen zehnmal identisch ueber
  // jeder Studie und schoben deren eigenen Titel unter die Falz. Der
  // Brotkrumen sagt, wo man ist; den Pitch traegt die Startseite.
  const header = '<div style="padding:16px 24px 0">'
    + '<h1 style="' + M + '; font-size:11px; letter-spacing:.18em; color:var(--info); margin:0; font-weight:400">RESEARCH · ' + esc(String(study.tab || '').toUpperCase()) + '</h1></div>';

  if (s.researchTab === 3) {
    return '<div>' + header + renderLiveRuns(T, payload) + '</div>';
  }
  if (laedt && studienSlug(study) !== 'methodology') {
    return '<div>' + header + ladeStudieHtml(study, RESEARCH_DATEI[s.researchTab]) + '</div>';
  }
  if (s.researchTab === 8) {
    return '<div>' + header + renderPostmortems(payload) + '</div>';
  }
  // Field notes haengen am Slug, nicht an der Position: die Liste waechst am
  // Ende, und ein Index wuerde beim naechsten Eintrag verrutschen.
  if (studienSlug(study) === 'field-notes') {
    return '<div>' + header + renderFieldNotes(payload, study) + '</div>';
  }

  // Microstructure hat eine eigene Seite: zwoelf Studien, je Karte mit
  // Frage, Verdikt, Diagramm und Quelle. Nutzlast aus public/data.
  if (s.researchTab === 4) {
    return '<div>' + header + renderMicrostructure(payload, study) + '</div>';
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

  const note = payload && payload.hinweis ? payload.hinweis : study.note;
  const table = buildStudyTable(T, s.researchTab, payload);
  // Ohne Nutzlast keine Zahlen. Die frueheren Demo-Werte widersprachen der
  // eigenen Forschung teils frontal: dort stand "IMBALANCE EDGE +0.4c net of
  // fees", gemessen sind -2.50 Cent. Unter einem Stempel wie
  // "frozen 2026-06-30" ist eine erfundene Zahl nicht neutral, sondern
  // belastend.
  // Der Pilot liest seine Wallet-Wahrheit (W/L, Netto-Cash) aus demselben
  // Ledger wie die Live-runs-Seite; die anderen Studien brauchen ihn nicht.
  const pilotLedger = s.researchTab === 5 ? walletLedgerVon(T, payload) : null;
  const stats = buildStudyStats(s.researchTab, payload, pilotLedger);
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
    + '<div style="font-size:13.5px; color:rgba(var(--ink),.6); margin-top:8px; line-height:1.5">' + esc(note) + '</div></div>'
    + stempelBlock(study, payload) + '</div>'
    // So viele Spalten wie Kacheln: der Pilot traegt mit der Wallet-Kachel
    // fuenf, die uebrigen Studien weiter ihre drei oder vier.
    + '<div style="display:grid; grid-template-columns:repeat(' + stats.length + ',1fr); gap:12px; margin-top:18px">'
    + stats.map((x) =>
      '<div style="background:var(--panel); border:1px solid rgba(var(--ink),.09); border-radius:6px; padding:14px 16px">'
      + '<div style="' + M + '; font-size:10.5px; letter-spacing:.13em; color:rgba(var(--ink),.6)">' + esc(x.label) + '</div>'
      + '<div style="' + M + '; font-size:21px; margin-top:7px">' + esc(x.value) + '</div>'
      + '<div style="' + M + '; font-size:10.5px; color:rgba(var(--ink),.6); margin-top:4px">' + esc(x.note) + '</div></div>'
    ).join('')
    + '</div>'
    + (pts ? '<div style="background:var(--panel); border:1px solid rgba(var(--ink),.09); border-radius:6px; margin-top:14px; padding:16px 18px">'
    + '<div style="' + M + '; font-size:10.5px; letter-spacing:.14em; color:rgba(var(--ink),.55); margin-bottom:12px">' + esc(chartLabel) + '</div>'
    + '<svg width="100%" height="220" viewBox="0 0 900 220" preserveAspectRatio="none" role="img" aria-label="' + esc(chartLabel) + '">'
    + '<line x1="0" y1="20" x2="900" y2="20" style="stroke:rgba(var(--ink),.07)" />'
    + '<line x1="0" y1="75" x2="900" y2="75" style="stroke:rgba(var(--ink),.07)" />'
    + '<line x1="0" y1="130" x2="900" y2="130" style="stroke:rgba(var(--ink),.07)" />'
    + '<line x1="0" y1="210" x2="900" y2="210" style="stroke:rgba(var(--ink),.14)" />'
    + '<polyline points="' + pts + '" fill="none" style="stroke:var(--info)" stroke-width="2" /></svg></div>' : '')
    // Je Studie ihre Diagramme und Zusatzbloecke (Mentions latency, Pilot,
    // Pipeline forward), am Slug aufgehaengt statt am Index.
    + studienExtrasHtml(studienSlug(study), payload, pilotLedger)
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
  const KNOPF = 'font-size:13px; color:var(--text); border:1px solid rgba(var(--ink),.2); border-radius:4px; padding:10px 16px; cursor:pointer; text-decoration:none; display:inline-block';
  const datei = RESEARCH_DATEI[tab];
  const methodik = T.studies.findIndex((st) => studienSlug(st) === 'methodology');
  const teile = [];
  if (datei) {
    teile.push('<a href="./data/' + esc(datei) + '" download="' + esc(datei) + '" class="hv-bd35" style="' + KNOPF + '">Download the data</a>');
  }
  if (methodik >= 0 && methodik !== tab) {
    // goStudy sets the address and fetches; the harness T has no such method.
    teile.push('<div ' + T.act(() => {
      if (T.goStudy) { T.goStudy(methodik); return; }
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
function pilotAuswertungHtml(payload, abgeschlossen) {
  const a = payload && payload.auswertung;
  if (!a || !a.trades || !a.trades.gesamt) return '';
  const karte = 'background:var(--panel); border:1px solid rgba(var(--ink),.09); border-radius:6px';
  const rt = a.regeltreue || {};
  const punkte = (rt.punkte || []).map((p) => {
    const farbe = p.erfuellt ? 'var(--accent)' : 'var(--warn)';
    const zeichen = p.erfuellt ? '✓' : '!';
    return '<div style="display:grid; grid-template-columns:18px 1fr auto; gap:12px; align-items:baseline; padding:10px 16px; border-bottom:1px solid rgba(var(--ink),.05)">'
      + '<div style="' + M + '; font-size:13px; color:' + farbe + '">' + zeichen + '</div>'
      + '<div><div style="font-size:12.5px; color:rgba(var(--ink),.8)">' + esc(p.regel) + '</div>'
      + (p.hinweis ? '<div style="font-size:11.5px; color:var(--warn); margin-top:4px; line-height:1.5">' + esc(p.hinweis) + '</div>' : '')
      + '</div>'
      + '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.55); text-align:right; white-space:nowrap">'
      + esc(p.ist || '') + (p.soll ? ' <span style="color:rgba(var(--ink),.55)">vs ' + esc(p.soll) + '</span>' : '')
      + '</div></div>';
  }).join('');

  return '<div style="' + karte + '; margin-top:14px; padding:18px 20px">'
    + '<div style="' + M + '; font-size:11px; letter-spacing:.14em; color:var(--info)">WHAT THE TEST MEASURED</div>'
    + '<div style="font-size:14.5px; color:var(--text); margin-top:10px; line-height:1.6; max-width:760px">' + esc(a.befund || '') + '</div>'
    // Der servergerechnete Satz "N positions are still open" stammt aus der
    // Trade-Liste ohne Aufloesungen; sobald das Wallet abgerechnet hat,
    // steht der Ausgang in der Karte HOW IT ENDED und der Satz entfaellt.
    + (a.offener_ausgang && !abgeschlossen
      ? '<div style="font-size:13px; color:var(--warn); margin-top:12px; line-height:1.6; max-width:760px; '
        + 'border-left:2px solid rgba(var(--warn-rgb),.4); padding-left:12px">' + esc(a.offener_ausgang) + '</div>'
      : '')
    + (punkte
      ? '<div style="' + M + '; font-size:11px; letter-spacing:.14em; color:rgba(var(--ink),.6); margin:18px 0 8px">RULE ADHERENCE</div>'
        + '<div style="border:1px solid rgba(var(--ink),.09); border-radius:6px; overflow:hidden">' + punkte + '</div>'
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

// Headline of the forward test, from the counts alone. Der Trichter steht
// genau einmal auf der Seite: frueher zeigte die Regel-Karte dieselben
// Gruende noch einmal als Tabelle (Anteil an allen Checks statt an den
// No-Trades) — zwei Darstellungen derselben Zaehlung lasen sich wie zwei
// Befunde.
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
  return '<div style="background:var(--panel); border:1px solid rgba(var(--ink),.09); border-radius:6px; margin-top:14px; padding:18px 20px">'
    + '<div style="' + M + '; font-size:11px; letter-spacing:.14em; color:var(--info)">WHAT THE FORWARD TEST FOUND</div>'
    + '<div style="font-size:15px; color:var(--text); margin-top:10px; line-height:1.6; max-width:820px">'
    + 'Almost nothing was tradable: of ' + num(z.gesamt) + ' decision checks, only ' + num(z.gekauft) + ' ended in a paper buy ('
    + (anteil < 10 ? anteil.toFixed(1) : Math.round(anteil)) + '%)'
    + (top ? ' — most common stopper: ' + esc(top[0].charAt(0).toLowerCase() + top[0].slice(1)) + ' (' + num(top[1]) + ' of ' + num(z.keine) + ' no-trades, ' + Math.round((top[1] / Math.max(1, z.keine)) * 100) + '%)' : '')
    + '.</div>'
    + '<div style="font-size:12px; color:rgba(var(--ink),.5); margin-top:8px; line-height:1.5">Counted over ' + esc(quelle) + ' in pipeline_forward.json. No equity curve on purpose: the log carries decisions and best book prices only — no fills, no wallet data, no return claim. What the same pipeline did with real money is on the Live runs page.</div>'
    + (chart ? '<div style="margin-top:14px">' + chart + '</div>' : '')
    + '</div>';
}

function pipelineRegelnHtml(payload) {
  const { eintraege } = pipelineEintraege(payload);
  if (!eintraege.length) return '';
  const karte = 'background:var(--panel); border:1px solid rgba(var(--ink),.09); border-radius:6px';

  const regel = (titel, text) =>
    '<div style="padding:12px 16px; border-bottom:1px solid rgba(var(--ink),.05)">'
    + '<div style="' + M + '; font-size:11px; letter-spacing:.12em; color:var(--info)">' + esc(titel) + '</div>'
    + '<div style="font-size:12.5px; color:rgba(var(--ink),.75); margin-top:6px; line-height:1.6">' + esc(text) + '</div></div>';

  return '<div style="' + karte + '; margin-top:14px; padding:18px 20px">'
    + '<div style="' + M + '; font-size:11px; letter-spacing:.14em; color:var(--info)">HOW THE PIPELINE DECIDES</div>'
    + '<div style="font-size:13.5px; color:rgba(var(--ink),.65); margin-top:10px; line-height:1.6; max-width:760px">'
    + 'These are word-count markets: will a speaker say a given word often enough during an episode, call or speech. '
    + 'The pipeline follows the live transcript and counts. It never predicts what will be said, it acts only on what has already been said. '
    + 'One run is one broadcast; every market it checks becomes one row in the log, buy or no-trade.</div>'
    + '<div style="border:1px solid rgba(var(--ink),.09); border-radius:6px; overflow:hidden; margin-top:14px">'
    + regel('BUY YES', 'Only once the live count has already passed the market threshold, so the outcome is settled in fact, and only while the price including fee stays under the run cap. Above the cap there is no margin left in a decided outcome.')
    + regel('BUY NO', 'Only after the full transcript, when the final count stayed far enough below the threshold, and only at a lower cap than YES. Betting on absence breaks on a single missed word, so it needs the bigger cushion.')
    + regel('OTHERWISE NOTHING', 'Every other case is a no-trade, and each entry carries the reason that stopped it. The thresholds themselves are shown per entry, not fixed here.')
    + '</div>'
    + '<div style="font-size:12px; color:rgba(var(--ink),.5); margin-top:12px; line-height:1.5; max-width:760px">'
    + 'Reading the run table below: EXTRACTED $ is the dollar value the run&#39;s buys actually captured of what its already-decided outcomes offered within the caps; QUOTE is that share — 100% means it caught everything its own rules allowed.</div>'
    + '</div>';
}

function studyTableHtml(T, label, cols, head, rows) {
  // Kompakte Zeilen wie in den Live-runs- und Ledger-Tabellen: die alten
  // 11px/18px-Polster und 13px-Zellen machten jede Studientabelle im
  // Vergleich zum Rest der Seite auffallend gross.
  const headStyle = 'display:grid; grid-template-columns:' + cols + '; gap:10px; padding:7px 14px; border-bottom:1px solid rgba(var(--ink),.09); ' + M + '; font-size:9.5px; letter-spacing:.13em; color:rgba(var(--ink),.6)';
  return '<div style="border:1px solid rgba(var(--ink),.09); border-radius:6px; margin-top:14px; overflow:hidden">'
    + '<div style="padding:9px 14px; background:var(--panel); border-bottom:1px solid rgba(var(--ink),.09); ' + M + '; font-size:10.5px; letter-spacing:.14em; color:var(--info)">' + esc(label) + '</div>'
    + '<div style="' + headStyle + '">'
    + head.map((h, i) => '<div style="' + (i === 0 ? '' : 'text-align:right') + '">' + esc(h) + '</div>').join('')
    + '</div>'
    + rows.map((row) =>
      '<div style="display:grid; grid-template-columns:' + cols + '; gap:10px; align-items:center; padding:8px 14px; border-bottom:1px solid rgba(var(--ink),.06)">'
      + row.map((cell, i) => {
        const first = i === 0;
        const cs = String(cell);
        const neg = cs.charAt(0) === '-' && cs.indexOf('$') > 0;
        const pos = cs.charAt(0) === '+' && cs.indexOf('$') > 0;
        const style = (first ? 'font-family:IBM Plex Sans,sans-serif; font-size:12.5px' : M + '; font-size:11.5px; text-align:right') + '; color:' + (neg ? 'var(--neg)' : pos ? 'var(--pos)' : first ? 'var(--text)' : 'rgba(var(--ink),.7)') + '; white-space:nowrap; overflow:hidden; text-overflow:ellipsis';
        return '<div style="' + style + '" title="' + esc(cs) + '">' + esc(cs) + '</div>';
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
        payload.faelle.map((f) => [String(f.event), reaktionsSekunden(f) != null ? fmtZahl(reaktionsSekunden(f)) + ' s' + (f.erste_reaktion_zum_outcome === false ? ' (away)' : '') : '—', f.minuten_bis_konvergenz != null ? dauerText(f.minuten_bis_konvergenz) : '—', String(f.stunden_im_handelbaren_fenster != null ? f.stunden_im_handelbaren_fenster : '—'), String(f.korrekt_aufgeloestes_outcome || '—'), String(f.status || '—')]));
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

// Wallet-Wahrheit des Piloten aus dem Ledger: Zaehlung der als pilot
// markierten Maerkte plus Netto-Cash und Einsatz aus dem Typ-Aggregat.
// null ohne Ledger oder ohne Pilot-Maerkte darin.
export function pilotLedgerStand(ledger) {
  if (!ledger || !Array.isArray(ledger.events)) return null;
  const z = { n: 0, won: 0, lost: 0, flat: 0, open: 0 };
  ledger.events.forEach((e) => (Array.isArray(e.maerkte) ? e.maerkte : []).forEach((m) => {
    if (String(m.zuordnung || '') !== 'pilot') return;
    z.n += 1;
    const st = String(m.status || '');
    if (st === 'won') z.won += 1;
    else if (st === 'lost' || st === 'worthless') z.lost += 1;
    else if (st === 'flat') z.flat += 1;
    else if (st === 'open') z.open += 1;
  }));
  if (!z.n) return null;
  const typ = ledger.aggregat && ledger.aggregat.nach_typ ? ledger.aggregat.nach_typ.pilot : null;
  return {
    pos: z,
    settled: z.open === 0,
    netto: typ && typ.netto_cash_usd != null ? +typ.netto_cash_usd : null,
    einsatz: typ && typ.einsatz_usd != null ? +typ.einsatz_usd : null,
    stand: ledger.stand_utc ? String(ledger.stand_utc).slice(0, 10) : ''
  };
}

// W-und-L-Satz der Pilot-Positionen, wie ihn Kacheln und Karten teilen.
function pilotWlText(pos) {
  return pos.won + 'W · ' + pos.lost + 'L'
    + (pos.flat ? ' · ' + pos.flat + ' flat' : '')
    + (pos.open ? ' · ' + pos.open + ' open' : '');
}

function buildStudyStats(tab, payload, ledger) {
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
      // Median und FASTEST in exakten Sekunden (Zeitstempel-Differenz),
      // nicht in gerundeten Minuten — die Rundung auf 0.1 min machte aus
      // 7 s und 33 s dieselbe Zahl.
      const mitReaktion = payload.faelle.filter((f) => reaktionsSekunden(f) != null)
        .sort((a, b) => reaktionsSekunden(a) - reaktionsSekunden(b));
      const sek = mitReaktion.map(reaktionsSekunden);
      const medianSek = medianVon(sek);
      const none = payload.faelle.filter((f) => f.minuten_bis_erste_reaktion == null).length;
      // Die Extremwerte tragen ihr Outcome: der langsamste Fall ist ein
      // NO-Markt, dessen erste Bewegung Drift war — ohne das Label laese
      // sich "86.7 min" als Markt, der eine gefallene Aussage verschlief.
      const extremNote = (f) => 'first reaction · resolved ' + String(f.korrekt_aufgeloestes_outcome || '—')
        + (f.erste_reaktion_zum_outcome === false ? ' · first move went the wrong way' : '');
      return [
        { label: 'MEDIAN LATENCY', value: medianSek != null ? fmtZahl(medianSek) + ' s' : '—', note: 'gap drop → first deviating minute-grid point · n = ' + sek.length + ' events · first move > 1 point off the pre-drop baseline' },
        { label: 'FASTEST', value: sek.length ? fmtZahl(sek[0]) + ' s' : '—', note: mitReaktion.length ? extremNote(mitReaktion[0]) : 'first reaction' },
        { label: 'SLOWEST', value: mitReaktion.length ? dauerText(mitReaktion[mitReaktion.length - 1].minuten_bis_erste_reaktion) : '—', note: mitReaktion.length ? extremNote(mitReaktion[mitReaktion.length - 1]) : 'first reaction' },
        { label: 'NO REACTION', value: String(none), note: 'never moved > 1 point' }
      ];
    }
    if (tab === 5 && payload.trades) {
      const p = payload.protokoll || {};
      const a = payload.auswertung;
      // W und L wie auf den anderen Seiten aus dem Wallet-Ledger, nicht aus
      // der Trade-Liste: die trades.csv kennt keine Aufloesungen, und "still
      // open" stand noch da, als das ganze Wallet laengst abgerechnet war.
      const wl = pilotLedgerStand(ledger);
      const nettoKachel = wl && wl.netto != null
        ? {
          label: 'NET CASH (WALLET · PILOT)',
          value: (wl.netto >= 0 ? '+$' : '-$') + Math.abs(wl.netto).toFixed(0),
          note: 'sells + redemptions - buys' + (wl.stand ? ' · as of ' + wl.stand : '')
        }
        : null;
      if (a && a.trades && a.trades.gesamt) {
        const sl = a.slippage || {};
        const rt = a.regeltreue || {};
        const cents = (v) => (v == null ? '—' : (v >= 0 ? '+' : '') + (v * 100).toFixed(2) + '¢');
        return [
          { label: 'STATUS', value: wl && wl.settled ? 'Resolved' : (a.phase === 'entry_open' ? 'Open' : (a.phase === 'resolved' ? 'Resolved' : 'Entry closed')), note: 'window to ' + String(a.fenster_bis || '—') },
          { label: 'TRADES PLACED', value: String(a.trades.gesamt), note: wl ? pilotWlText(wl.pos) + ' · wallet, worthless counts as lost' : a.trades.offen + ' still open · $' + (a.trades.kapital_usd || 0) + ' deployed' }
        ].concat(nettoKachel ? [nettoKachel] : []).concat([
          { label: 'MEAN SLIPPAGE', value: cents(sl.mittel), note: (sl.teurer_als_signal || 0) + ' of ' + (sl.n || 0) + ' worse than signal' },
          { label: 'RULE ADHERENCE', value: (rt.erfuellt != null ? rt.erfuellt + ' / ' + rt.gesamt : '—'), note: 'checks passed' }
        ]);
      }
      // Statischer Pfad ohne auswertung: Stueckzahl und Einsatz kommen aus
      // den Trades selbst; der Protokollwert steht daneben, und eine
      // Abweichung wird als solche benannt statt als "fixed" behauptet.
      const offen = payload.trades.filter((t) => !t.exit_zeit_utc && !t.exit_preis).length;
      const groessen = payload.trades.map((t) => +t.groesse_usd).filter((v) => !isNaN(v));
      const einheitlich = groessen.length > 0 && groessen.every((v) => v === groessen[0]);
      const soll = p.einsatz_je_trade_usdc != null ? +p.einsatz_je_trade_usdc : null;
      return [
        { label: 'TRADES', value: String(payload.trades.length), note: wl ? pilotWlText(wl.pos) + ' · wallet, worthless counts as lost' : offen + ' still open · exit via resolution' }
      ].concat(nettoKachel ? [nettoKachel] : []).concat([
        { label: 'BUDGET', value: '$' + (p.budget_usdc != null ? p.budget_usdc : '—'), note: 'preregistered' },
        { label: 'STAKE PER TRADE', value: groessen.length ? (einheitlich ? '$' + groessen[0] : '$' + Math.min(...groessen) + '–' + Math.max(...groessen)) : '—',
          note: soll != null ? 'protocol $' + soll + (einheitlich && groessen[0] !== soll ? ' · deviates from the frozen text' : '') : 'no protocol stake in the file' },
        { label: 'RULES FROZEN', value: String(p.regel_freeze_datum || '—'), note: 'before first trade' }
      ]);
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
        n: h.n == null ? null : +h.n, entschieden: zahl(h.anteil_entschieden),
        brierOffen: zahl(h.brier_offen), nOffen: h.n_offen == null ? null : +h.n_offen,
        // Intervall um den Brier: ohne das ist eine Rangfolge ueber viele
        // Zellen keine Aussage. Aeltere Dateien tragen es nicht.
        brierCi: Array.isArray(h.brier_ci95) && h.brier_ci95[0] != null
          ? [zahl(h.brier_ci95[0]), zahl(h.brier_ci95[1])] : null
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
      typen: Array.isArray(k.typen) ? k.typen.filter((t) => t && t.typ != null).map((t) => ({
        typ: String(t.typ), n: t.n == null ? null : +t.n,
        brierT1: zahl(t.brier_t1), nT1: t.n_t1 == null ? null : +t.n_t1
      })) : [],
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

// Ordnungszahl fuer die Befundzeile. Reicht so weit wie eine Kategorienliste.
function ordinalWort(n) {
  const w = ['', 'first', 'second', 'third', 'fourth', 'fifth', 'sixth', 'seventh',
    'eighth', 'ninth', 'tenth', 'eleventh', 'twelfth'];
  return w[n] || (n + 'th');
}

// Der Befund oben auf der Seite wird gerechnet, nicht getippt. Die Behauptung
// erscheint nur, wenn die Zahlen sie tragen: die Spanne auf offenen Preisen
// muss enger sein als die auf allen, und mindestens eine Kategorie muss beim
// Wechsel der Lesart drei Raenge oder mehr abrutschen. Traegt die Datei kein
// brier_offen, gibt es keinen Befund und keine Karte — statt einer Behauptung,
// die die Stichprobe nicht deckt.
function befundVon(zeilen) {
  const mit = zeilen.filter((z) => {
    const h = horizontVon(z, 7);
    return h && h.brier != null && h.brierOffen != null;
  });
  if (mit.length < 4) return null;
  const brier = (z) => horizontVon(z, 7).brier;
  const offen = (z) => horizontVon(z, 7).brierOffen;
  const nachAllen = mit.slice().sort((a, b) => brier(a) - brier(b));
  const nachOffen = mit.slice().sort((a, b) => offen(a) - offen(b));
  // Other ist der Restkorb (quelle.auswahl.min_markets_per_category faltet
  // kleine Kategorien hinein), keine Kategorie. Fuer die Raenge zaehlt er
  // mit — als Vergleichspol in der Befundzeile taugt er nicht.
  const echt = nachAllen.filter((z) => z.name !== 'Other');
  const spanneAlle = brier(nachAllen[nachAllen.length - 1]) - brier(nachAllen[0]);
  const spanneOffen = offen(nachOffen[nachOffen.length - 1]) - offen(nachOffen[0]);
  if (spanneOffen >= spanneAlle) return null;

  let faller = null;
  mit.forEach((z) => {
    const sturz = nachOffen.indexOf(z) - nachAllen.indexOf(z);
    if (!faller || sturz > faller.sturz) {
      faller = { z, sturz, rangAlle: nachAllen.indexOf(z) + 1, rangOffen: nachOffen.indexOf(z) + 1 };
    }
  });
  if (!faller || faller.sturz < 3) return null;

  const pol = echt.length >= 2 ? echt : nachAllen;
  return {
    n: mit.length,
    minOffen: offen(nachOffen[0]),
    maxOffen: offen(nachOffen[nachOffen.length - 1]),
    bester: pol[0],
    schlechtester: pol[pol.length - 1],
    faktor: brier(pol[0]) > 0 ? brier(pol[pol.length - 1]) / brier(pol[0]) : null,
    faller
  };
}

// n, unter dem eine Kategorie nicht ranggeeignet ist. Sie steht trotzdem da —
// nur gedaempft und als thin markiert, statt zu verschwinden.
const OFFEN_DUENN = 20;

function renderCategoryEfficiency(T, payload, study) {
  const karte = 'background:var(--panel); border:1px solid rgba(var(--ink),.09); border-radius:6px';

  // Kopf: Titel und EINE Zeile Stichprobe. Der lange Absatz aus der Nutzlast
  // (payload.hinweis) steht unveraendert im Methodenfeld weiter unten — er
  // wird verschoben, nicht gekuerzt.
  const kopf = (unterzeile) => '<div style="display:flex; align-items:flex-start; justify-content:space-between; gap:24px">'
    + '<div style="max-width:760px">'
    + '<div style="font-size:20px; font-weight:600">' + esc(study.title) + '</div>'
    + '<div style="' + M + '; font-size:11.5px; color:rgba(var(--ink),.6); margin-top:8px; line-height:1.5">' + unterzeile + '</div></div>'
    + stempelBlock(study, payload) + '</div>';

  if (!payload) {
    return fehlendeStudieHtml(study, RESEARCH_DATEI[1]);
  }
  if (payload._quelle === 'fehler') {
    return '<div style="padding:22px 24px">' + kopf(esc(study.note))
      + '<div style="margin-top:16px">' + leerZeile(herkunftSatz({ quelle: 'fehler', fehler: payload._fehler }, 'public/data/kategorie_karte.json')) + '</div></div>';
  }
  const zeilen = kategorieZeilen(payload);
  if (!zeilen.length) {
    return '<div style="padding:22px 24px">' + kopf(esc(study.note))
      + '<div style="' + karte + '; padding:22px 24px; max-width:720px; margin-top:16px">'
      + '<div style="font-size:16px; font-weight:600">No categories in the published file</div>'
      + '<div style="font-size:13px; color:rgba(var(--ink),.55); margin-top:10px; line-height:1.6">'
      + 'This page reads <span style="' + M + '">public/data/kategorie_karte.json</span>. The file is there but its '
      + '<span style="' + M + '">kategorien</span> list is empty, so nothing is drawn — and nothing is invented to fill the space.'
      + '</div></div></div>';
  }

  const gesamt = zeilen.reduce((a, z) => a + (z.maerkte || 0), 0);
  const hatOffenT7 = zeilen.some((z) => { const h = horizontVon(z, 7); return h && h.brierOffen != null; });
  const nT7 = zeilen.reduce((a, z) => { const h = horizontVon(z, 7); return a + (h && h.n ? h.n : 0); }, 0);
  const alleTage = [];
  zeilen.forEach((z) => z.horizonte.forEach((h) => { if (alleTage.indexOf(h.tage) < 0) alleTage.push(h.tage); }));
  alleTage.sort((a, b) => b - a);

  const unterzeile = (gesamt ? num(gesamt) + ' resolved binary markets' : 'sample size not published')
    + ' · ' + zeilen.length + ' categories'
    + ' · Polymarket YES price at ' + alleTage.length + ' fixed horizon' + (alleTage.length === 1 ? '' : 's')
    + (alleTage.length ? ' (T-' + alleTage[0] + ' to T-' + alleTage[alleTage.length - 1] + ')' : '');

  // Rangfolge: auf offenen Preisen, wenn die Datei sie traegt. Der
  // Gesamt-Brier kuert sonst die Kategorie mit den meisten schon
  // entschiedenen Preisen — genau der Effekt, den die Seite zeigen will.
  const rangwert = (z) => { const h = horizontVon(z, 7); return hatOffenT7 ? h.brierOffen : h.brier; };
  const rangfolge = zeilen
    .filter((z) => { const h = horizontVon(z, 7); return h && rangwert(z) != null; })
    .sort((a, b) => rangwert(a) - rangwert(b));

  // ---- Befund
  const b = hatOffenT7 ? befundVon(zeilen) : null;
  const f3 = (v) => v.toFixed(3);
  const fallDec = b ? b.faller.z.entschiedenT7 : null;
  const befundHtml = b
    ? '<div style="' + karte + '; padding:18px 20px; margin-top:16px">'
      + '<div style="' + M + '; font-size:10.5px; letter-spacing:.14em; color:var(--accent)">THE FINDING</div>'
      + '<div style="font-size:17px; font-weight:600; margin-top:9px; line-height:1.35; max-width:900px">'
      + 'Most of the gap between categories is settled questions, not sharper pricing.</div>'
      + '<div style="font-size:13px; color:rgba(var(--ink),.6); margin-top:9px; line-height:1.6; max-width:900px">'
      + 'Scored on every price, ' + esc(b.bester.name) + ' (' + f3(horizontVon(b.bester, 7).brier) + ') '
      + (b.faktor ? 'looks ' + b.faktor.toFixed(1) + '× better than ' : 'leads ')
      + esc(b.schlechtester.name) + ' (' + f3(horizontVon(b.schlechtester, 7).brier) + '). '
      + 'Scored only on prices still genuinely open at T-7, all ' + b.n + ' categories land between '
      + f3(b.minOffen) + ' and ' + f3(b.maxOffen) + ' — and ' + esc(b.faller.z.name) + ' falls from '
      + ordinalWort(b.faller.rangAlle) + ' to ' + (b.faller.rangOffen === b.n ? 'last' : ordinalWort(b.faller.rangOffen)) + '.'
      + (fallDec != null ? ' Its headline score came from ' + Math.round(fallDec * 100)
        + '% of its questions already trading outside 5–95 cents.' : '')
      + '</div></div>'
    : '';

  // ---- Kennzahlen
  const kpi = (label, wert, hinweis) =>
    '<div style="' + karte + '; border-radius:6px; padding:14px 16px">'
    + '<div style="' + M + '; font-size:10.5px; letter-spacing:.13em; color:rgba(var(--ink),.6)">' + esc(label) + '</div>'
    + '<div style="' + M + '; font-size:21px; margin-top:7px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis">' + esc(wert) + '</div>'
    + '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.6); margin-top:4px">' + esc(hinweis) + '</div></div>';

  // Die mittlere Kachel traegt immer die Spanne des vergleichbaren Briers —
  // auf offenen Preisen, wo die Datei sie hergibt, sonst auf allen. Die
  // rechte nennt den Anteil schon entschiedener Preise; fehlt der, tritt die
  // Stichprobenspanne an ihre Stelle, damit nicht zweimal dasselbe dasteht.
  const offenWerte = rangfolge.map((z) => horizontVon(z, 7).brierOffen).filter((v) => v != null);
  const alleWerte = rangfolge.map((z) => horizontVon(z, 7).brier).filter((v) => v != null);
  const decWerte = zeilen.map((z) => z.entschiedenT7).filter((v) => v != null);
  const nT7Werte = rangfolge.map((z) => horizontVon(z, 7).n).filter((v) => v != null);
  const spanne = hatOffenT7 && offenWerte.length ? offenWerte : alleWerte;
  const kpis = [
    kpi('MARKETS IN SAMPLE', gesamt ? num(gesamt) : '—',
      gesamt ? (nT7 ? num(nT7) + ' of them priced at T-7' : 'no T-7 count published') : 'no market counts in the file'),
    spanne.length
      ? kpi(hatOffenT7 ? 'OPEN-PRICE BRIER AT T-7' : 'BRIER AT T-7',
        f3(Math.min(...spanne)) + ' – ' + f3(Math.max(...spanne)),
        'the whole spread across ' + zeilen.length + ' categories')
      : kpi('CATEGORIES', String(zeilen.length), 'no Brier at T-7 in the file'),
    decWerte.length
      ? kpi('ALREADY DECIDED AT T-7', Math.round(Math.min(...decWerte) * 100) + '% – ' + Math.round(Math.max(...decWerte) * 100) + '%',
        'share trading outside 5–95 cents')
      : kpi('CATEGORIES', String(zeilen.length),
        nT7Werte.length ? 'T-7 samples from ' + num(Math.min(...nT7Werte)) + ' to ' + num(Math.max(...nT7Werte)) : 'no decided share published')
  ].join('');

  // ---- Hantel: dieselbe Zahl, zwei Lesarten. Der Strich laeuft vom Brier
  // ueber alle Preise zum Brier ueber die offenen; der Punkt sitzt auf dem
  // offenen, weil der die vergleichbare Zahl ist.
  const hantelPunkte = rangfolge.map((z) => {
    const h = horizontVon(z, 7);
    const duenn = h.nOffen != null && h.nOffen < OFFEN_DUENN;
    const wert = hatOffenT7 ? h.brierOffen : h.brier;
    return {
      label: z.name,
      von: Math.min(h.brier, wert),
      bis: Math.max(h.brier, wert),
      wert,
      farbe: duenn ? 'rgba(var(--ink),.5)' : (wert >= 0.2 ? 'var(--warn)' : 'var(--info)'),
      text: f3(wert) + '  n ' + (h.nOffen != null ? num(h.nOffen) : (h.n != null ? num(h.n) : '—')) + (duenn ? ' thin' : '')
    };
  });
  const hantelHtml = hatOffenT7 && hantelPunkte.length
    ? '<div style="margin-top:12px">' + diagramm({
      titel: 'BRIER AT T-7 · ALL PRICES → OPEN PRICES ONLY',
      einheit: 'tick = all prices, dot = open prices (0.05 < p < 0.95) · 0.25 = always saying 50%',
      punkte: hantelPunkte
    }) + '</div>'
    : '<div style="margin-top:12px">' + (diagramm({
      titel: 'BRIER AT T-7 BY CATEGORY',
      einheit: '0 = perfect, 0.25 = always saying 50%',
      punkte: rangfolge.map((z) => ({ label: z.name + ' · n ' + (horizontVon(z, 7).n != null ? num(horizontVon(z, 7).n) : '—'), wert: horizontVon(z, 7).brier, art: 'summe' }))
    }) || '<div style="' + karte + '; padding:16px 18px; ' + M + '; font-size:11.5px; color:rgba(var(--ink),.6)">'
      + 'No Brier score at T-7 in the payload — no chart is drawn.</div>') + '</div>';

  // ---- Kompakte Tabelle, auf offenen Preisen sortiert. Alle Horizonte und
  // Trefferquoten stehen im Klappfeld darunter.
  const tabSpalten = '1fr 118px 108px 96px 92px 116px';
  const tabKopf = '<div style="display:grid; grid-template-columns:' + tabSpalten + '; gap:12px; padding:9px 18px; border-bottom:1px solid rgba(var(--ink),.09); ' + M + '; font-size:10.5px; letter-spacing:.14em; color:rgba(var(--ink),.6)">'
    + '<div>CATEGORY</div>'
    + '<div style="text-align:right">' + (hatOffenT7 ? 'OPEN BRIER' : 'BRIER T-7') + '</div>'
    + '<div style="text-align:right">' + (hatOffenT7 ? 'ALL PRICES' : 'HIT RATE') + '</div>'
    + '<div style="text-align:right">DECIDED</div><div style="text-align:right">MARKETS</div>'
    + '<div style="text-align:right">MEDIAN VOLUME</div></div>';
  const tabelle = '<div style="border:1px solid rgba(var(--ink),.09); border-radius:6px; margin-top:14px; overflow:hidden">'
    + '<div style="padding:11px 18px; background:var(--panel); border-bottom:1px solid rgba(var(--ink),.09); display:flex; align-items:baseline; justify-content:space-between; gap:16px">'
    + '<div style="' + M + '; font-size:10.5px; letter-spacing:.14em; color:var(--info)">'
    + (hatOffenT7 ? 'RANKED ON OPEN PRICES AT T-7' : 'RANKED ON BRIER AT T-7') + '</div>'
    + '<div style="' + M + '; font-size:10.5px; color:rgba(var(--ink),.6)">every horizon and hit rate → in the panel below</div></div>'
    + tabKopf
    + rangfolge.map((z) => {
      const h = horizontVon(z, 7);
      const wert = hatOffenT7 ? h.brierOffen : h.brier;
      const duenn = h.nOffen != null && h.nOffen < OFFEN_DUENN;
      const balken = Math.round(Math.min(wert / 0.26, 1) * 92);
      return '<div style="display:grid; grid-template-columns:' + tabSpalten + '; gap:12px; align-items:center; padding:9px 18px; border-bottom:1px solid rgba(var(--ink),.06)">'
        + '<div style="display:flex; align-items:center; gap:10px; min-width:0">'
        + '<div style="font-size:13px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; color:' + (duenn ? 'rgba(var(--ink),.6)' : 'var(--text)') + '" title="' + esc(z.name) + '">' + esc(z.name) + '</div>'
        + '<div style="height:6px; flex:none; width:' + balken + 'px; border-radius:4px; background:' + (duenn ? 'rgba(var(--ink),.25)' : (wert >= 0.2 ? 'var(--warn)' : 'var(--info)')) + '; opacity:.85"></div>'
        + (duenn ? '<div style="' + M + '; font-size:10.5px; letter-spacing:.08em; color:rgba(var(--ink),.6); border:1px solid rgba(var(--ink),.16); border-radius:4px; padding:1px 5px; white-space:nowrap">THIN n ' + num(h.nOffen) + '</div>' : '')
        + '</div>'
        + '<div style="text-align:right; ' + M + '; font-size:12.5px; color:' + (duenn ? 'rgba(var(--ink),.6)' : 'rgba(var(--ink),.92)') + '">' + f3(wert) + '</div>'
        + '<div style="text-align:right; ' + M + '; font-size:12.5px; color:rgba(var(--ink),.6)">' + (hatOffenT7 ? f3(h.brier) : (h.treffer != null ? Math.round(h.treffer * 100) + '%' : '—')) + '</div>'
        + '<div style="text-align:right; ' + M + '; font-size:12.5px; color:rgba(var(--ink),.6)">' + (z.entschiedenT7 != null ? Math.round(z.entschiedenT7 * 100) + '%' : '—') + '</div>'
        + '<div style="text-align:right; ' + M + '; font-size:12.5px; color:rgba(var(--ink),.6)">' + (z.maerkte != null ? num(z.maerkte) : '—') + '</div>'
        + '<div style="text-align:right; ' + M + '; font-size:12px; color:rgba(var(--ink),.6)">' + (z.medianVol != null ? '$' + num(Math.round(z.medianVol)) : '—') + '</div>'
        + '</div>';
    }).join('')
    + '</div>';

  // ---- Klappfeld 1: alle Horizonte, Trefferquoten, Kalibrierung. Nichts
  // davon faellt weg — es steht nur nicht mehr dreimal untereinander.
  const hatHorizonte = (payload.kategorien || []).some((k) => k && Array.isArray(k.horizonte) && k.horizonte.length);
  const linienHtml = hatHorizonte && alleTage.length > 1
    ? linien({
      titel: 'BRIER BY HORIZON', einheit: 'days before the decision, per category',
      hinweis: 'each point carries its own n — see the table',
      x: alleTage.map((t) => 'T-' + t),
      serien: zeilen.map((z, i) => ({
        name: z.name, farbe: serienFarbe(i),
        werte: alleTage.map((t) => { const h = horizontVon(z, t); return h && h.brier != null ? h.brier : null; })
      }))
    })
    : '';

  const kalib = zeilen.filter((z) => z.bins.length).map((z) => {
    const n = z.bins.reduce((a, x) => a + (x.n || 0), 0);
    return kalibrierung({
      titel: z.name.toUpperCase(),
      hinweis: 'T-' + z.kalibrierungTage + ' · n ' + num(n) + ' · ' + z.bins.length + ' bins',
      punkte: z.bins
    });
  }).filter(Boolean);

  const vollSpalten = '1fr ' + alleTage.map(() => '118px').join(' ');
  const vollKopf = '<div style="display:grid; grid-template-columns:' + vollSpalten + '; gap:12px; padding:9px 18px; border-bottom:1px solid rgba(var(--ink),.09); ' + M + '; font-size:10.5px; letter-spacing:.14em; color:rgba(var(--ink),.6)">'
    + '<div>CATEGORY</div>'
    + alleTage.map((t) => '<div style="text-align:right">T-' + t + ' BRIER ±95% · HIT · N</div>').join('') + '</div>';
  const zelle = (h) => {
    if (!h || h.brier == null) return '<div style="text-align:right; ' + M + '; font-size:12px; color:rgba(var(--ink),.5)">—</div>';
    return '<div style="text-align:right; ' + M + '">'
      + '<div style="font-size:12.5px; color:rgba(var(--ink),.85)">' + f3(h.brier)
      + (h.brierCi ? '<span style="font-size:10.5px; color:rgba(var(--ink),.5)"> ±' + ((h.brierCi[1] - h.brierCi[0]) / 2).toFixed(3) + '</span>' : '')
      + '</div>'
      + '<div style="font-size:11px; color:rgba(var(--ink),.6); margin-top:2px">' + (h.treffer != null ? Math.round(h.treffer * 100) + '%' : '—') + ' · n ' + (h.n != null ? num(h.n) : '—') + '</div></div>';
  };
  const vollTabelle = '<div style="border:1px solid rgba(var(--ink),.09); border-radius:6px; margin-top:12px; overflow:hidden">'
    + vollKopf
    + zeilen.map((z) => '<div style="display:grid; grid-template-columns:' + vollSpalten + '; gap:12px; align-items:center; padding:9px 18px; border-bottom:1px solid rgba(var(--ink),.06)">'
      + '<div style="font-size:13px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="' + esc(z.name) + '">' + esc(z.name) + '</div>'
      + alleTage.map((t) => zelle(horizontVon(z, t))).join('')
      + '</div>').join('')
    + '</div>';

  // Mehrfachvergleich: die Tabelle ist ein Gitter aus Kategorie x Horizont.
  // Die beste Zelle ist das Minimum aus so vielen Ziehungen, also gehoert
  // die Zahl der Zellen und der Hinweis auf die Intervalle daneben.
  const zellenMitBrier = zeilen.reduce((a, z) => a + z.horizonte.filter((h) => h && h.brier != null).length, 0);
  const hatBrierCi = zeilen.some((z) => z.horizonte.some((h) => h && h.brierCi));
  const vergleichHtml = zellenMitBrier > 1
    ? '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.6); margin-top:10px; line-height:1.6">'
      + zellenMitBrier + ' category-by-horizon cells are scored here. The best of ' + zellenMitBrier
      + ' cells is the smallest of ' + zellenMitBrier + ' draws, so a leading Brier is not by itself a difference'
      + (hatBrierCi ? ' — the ± figure is the 95% interval around each cell, and two cells whose intervals overlap are not separated by this sample.' : '.')
      + '</div>'
    : '';

  // Der Titel verspricht nur, was drin ist: ohne Kalibrierungsbins heisst das
  // Feld nicht "& CALIBRATION".
  const horizontHtml = '<details style="margin-top:12px; ' + karte + '; padding:0 18px">'
    + '<summary style="cursor:pointer; padding:12px 0; ' + M + '; font-size:10.5px; letter-spacing:.14em; color:rgba(var(--ink),.6); list-style:none">ALL HORIZONS &amp; HIT RATES'
    + (kalib.length ? ', PLUS CALIBRATION' : '') + ' ▸</summary>'
    + '<div style="padding-bottom:14px">'
    + vollTabelle
    + vergleichHtml
    + (linienHtml ? '<div style="margin-top:12px">' + linienHtml + '</div>' : '')
    + (kalib.length
      ? '<div style="' + M + '; font-size:10.5px; letter-spacing:.14em; color:var(--info); margin:16px 0 8px">CALIBRATION AT T-' + (zeilen.find((z) => z.bins.length) || {}).kalibrierungTage + ' · PREDICTED VS REALISED</div>'
        + '<div style="font-size:12px; color:rgba(var(--ink),.6); margin-bottom:10px; line-height:1.5">A dot on the diagonal means the price was right on average in that bin; dot size follows n, the bar is the 95% interval of the realised share, amber when it misses the prediction.</div>'
        + '<div style="display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:12px">' + kalib.join('') + '</div>'
      : '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.6); margin-top:12px">No calibration bins in this payload — kategorie_karte.json carries them under kategorien[].kalibrierung.</div>')
    + '</div></details>';

  // ---- Klappfeld 2: Einpreisungs-Logik je Kategorie (unveraendert).
  const q = payload.quelle && typeof payload.quelle === 'object' ? payload.quelle : null;
  const absatz = (titel, text) => (text
    ? '<div style="margin-top:10px"><div style="' + M + '; font-size:10.5px; letter-spacing:.13em; color:rgba(var(--ink),.55)">' + titel + '</div>'
      + '<div style="font-size:12.5px; color:rgba(var(--ink),.7); margin-top:4px; line-height:1.6">' + esc(text) + '</div></div>'
    : '');
  const messlogik = q && q.messlogik && typeof q.messlogik === 'object' ? q.messlogik : null;
  let messlogikHtml = '';
  if (messlogik) {
    const namen = zeilen.map((z) => z.name).filter((n) => messlogik[n]);
    Object.keys(messlogik).forEach((n) => { if (namen.indexOf(n) < 0) namen.push(n); });
    const block = (name) => {
      const m = messlogik[name] || {};
      const zeile = zeilen.find((z) => z.name === name);
      const typZeile = zeile && zeile.typen.length
        ? zeile.typen.map((t) => t.typ + ' n ' + (t.n != null ? num(t.n) : '—') + (t.brierT1 != null ? ' (Brier T-1 ' + t.brierT1.toFixed(3) + ')' : '')).join(' · ')
        : '';
      return '<div style="margin-top:14px; padding-top:12px; border-top:1px solid rgba(var(--ink),.07)">'
        + '<div style="font-size:13px; font-weight:600">' + esc(name) + '</div>'
        + (typZeile ? '<div style="' + M + '; font-size:11px; color:var(--info); margin-top:4px">' + esc(typZeile) + '</div>' : '')
        + absatz('ANCHOR OF THE HORIZONS', m.anker)
        + absatz('WHAT REPRICES IT', m.einpreisung)
        + absatz('NOT MEASURED HERE', m.nicht_gemessen)
        + absatz('T0 FOR A LATENCY STUDY', m.latenz_t0)
        + '</div>';
    };
    messlogikHtml = '<details style="margin-top:10px; ' + karte + '; padding:0 18px">'
      + '<summary style="cursor:pointer; padding:12px 0; ' + M + '; font-size:10.5px; letter-spacing:.14em; color:rgba(var(--ink),.6); list-style:none">PRICING-IN LOGIC BY CATEGORY ▸</summary>'
      + '<div style="padding-bottom:14px">'
      + '<div style="font-size:12px; color:rgba(var(--ink),.6); line-height:1.5">These horizons measure forecast quality, never pricing-in speed: in-play moves and news reactions happen between T-1 and the decision and are invisible above. Per category: what the horizons anchor to, which real-world events reprice it, what stays unmeasured, and where an event-anchored latency study would take its t0 from. The blue line is the sample&#39;s pricing-mechanism mix.</div>'
      + namen.map(block).join('')
      + '</div></details>';
  }

  // ---- Klappfeld 3: Methode. Hier landet jetzt auch der lange Absatz, der
  // frueher ueber der ersten Zahl stand — Wort fuer Wort derselbe Text.
  const snap = payload.thesis_snapshot && Array.isArray(payload.thesis_snapshot.kategorien) && payload.thesis_snapshot.kategorien.length ? payload.thesis_snapshot : null;
  const langerHinweis = payload.hinweis ? String(payload.hinweis) : '';
  const methodeHtml = q || snap || langerHinweis
    ? '<details style="margin-top:10px; ' + karte + '; padding:0 18px">'
      + '<summary style="cursor:pointer; padding:12px 0; ' + M + '; font-size:10.5px; letter-spacing:.14em; color:rgba(var(--ink),.6); list-style:none">METHOD, SAMPLE &amp; WHAT IT CANNOT SHOW ▸</summary>'
      + '<div style="padding-bottom:14px">'
      + (langerHinweis ? '<div style="font-size:12.5px; color:rgba(var(--ink),.7); line-height:1.65; max-width:900px">' + esc(langerHinweis) + '</div>' : '')
      + (q ? absatz('WHAT WAS MEASURED', q.methode) + absatz('HOW MARKETS WERE CATEGORISED', q.kategorisierung) : '')
      + (q && q.datenfenster ? absatz('DATA WINDOW', 'events with an end date from ' + String(q.datenfenster.end_date_min || '').slice(0, 10) + ', fetched ' + String(q.datenfenster.abgerufen_utc || '').slice(0, 16).replace('T', ' ') + ' UTC · ' + num(q.datenfenster.events_gesichtet || 0) + ' events scanned · ' + q.datenfenster.reihenfolge) : '')
      + (q && q.auswahl ? absatz('SAMPLE SELECTION', 'at most ' + q.auswahl.max_per_event + ' markets per event, ' + q.auswahl.max_per_category_long_lived + ' long-lived and ' + q.auswahl.max_per_category_short_lived + ' short-lived markets per category, minimum volume $' + num(q.auswahl.min_volume_usd) + ', categories under ' + q.auswahl.min_markets_per_category + ' markets fold into Other') : '')
      + (q && q.preise ? absatz('PRICE SERIES', 'hourly: ' + q.preise.hourly + ' · daily: ' + q.preise.daily) : '')
      + (q && Array.isArray(q.einschraenkungen) && q.einschraenkungen.length
        ? '<div style="margin-top:10px"><div style="' + M + '; font-size:10.5px; letter-spacing:.13em; color:rgba(var(--ink),.55)">WHAT IT CANNOT SHOW</div>'
          + '<ul style="margin:4px 0 0 18px; padding:0; font-size:12.5px; color:rgba(var(--ink),.7); line-height:1.6">'
          + q.einschraenkungen.map((e) => '<li>' + esc(e) + '</li>').join('') + '</ul></div>'
        : '')
      + (snap
        ? '<div style="margin-top:12px"><div style="' + M + '; font-size:10.5px; letter-spacing:.13em; color:rgba(var(--ink),.55)">THESIS FIGURES THIS TABLE REPLACES' + (snap.stand_utc ? ' · ' + esc(String(snap.stand_utc).slice(0, 10)) : '') + '</div>'
          + (snap.hinweis ? '<div style="font-size:12px; color:rgba(var(--ink),.6); margin-top:4px; line-height:1.5">' + esc(snap.hinweis) + '</div>' : '')
          + '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.6); margin-top:6px; line-height:1.7">'
          + snap.kategorien.map((k) => esc(String(k.kategorie)) + ': Brier T-7 ' + (k.brier_t7 != null ? (+k.brier_t7).toFixed(3) : '—') + ' (n ' + (k.n_t7 != null ? k.n_t7 : '—') + ') · T-1 ' + (k.brier_t1 != null ? (+k.brier_t1).toFixed(3) : '—') + ' · ' + (k.n_maerkte != null ? k.n_maerkte : '—') + ' markets').join('<br>')
          + '</div></div>'
        : '')
      + '</div></details>'
    : '';

  return '<div style="padding:22px 24px">' + kopf(esc(unterzeile))
    + befundHtml
    + '<div style="display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin-top:12px">' + kpis + '</div>'
    + hantelHtml
    + tabelle
    + horizontHtml
    + messlogikHtml
    + methodeHtml
    + studienKnoepfe(T, 1)
    + '</div>';
}

// ---------------------------------------------------------------- live runs (research tab 3)
function renderLiveRuns(T, payload) {
  const s = T.state;
  const agg = payload && payload.aggregat ? payload.aggregat : null;
  // Kein "rolling" mehr: der letzte Publish ist datiert, kein Einsatz offen.

  // Zwei PnL-Zahlen, beide beschriftet: die aus den Logs rekonstruierte (die
  // Nutzlast nimmt den Preisdeckel an, wo die FAK-Antwort keinen Fillpreis
  // trug) und die wallet-abgeglichene Netto-Zahl mit ihrem Stand. Frueher
  // stand die Log-Zahl unter "REALIZED PNL · wallet-reconciled" — falsch
  // beschriftet, und die Kachel TOTAL STAKE dazu.
  const walletStand = agg && agg.wallet_abgleich_stand ? String(agg.wallet_abgleich_stand) : '';
  // Der Wallet-Ledger traegt einen frischeren Stand als der kuratierte
  // Abgleich in runs.json, sobald scripts/wallet_ledger.py erneut lief. Dann
  // kommen die Wallet-Spalten oben aus dem Ledger (nur Bot-Maerkte), mit
  // dessen Stand beschriftet — sonst stehen Kacheln vom 18. Juli neben einem
  // Ledger vom 17. August und die Seite widerspricht sich selbst.
  const ledger = walletLedgerVon(T, payload);
  const ledgerBot = ledger && ledger.aggregat && ledger.aggregat.nach_typ ? ledger.aggregat.nach_typ.bot : null;
  const ledgerStand = ledger && ledger.stand_utc ? String(ledger.stand_utc).slice(0, 10) : '';
  const frisch = ledgerBot && ledgerBot.netto_cash_usd != null && ledgerStand && (!walletStand || ledgerStand > walletStand)
    ? { stand: ledgerStand, kaeufe: ledgerBot.einsatz_usd, netto: +ledgerBot.netto_cash_usd }
    : null;
  // Je Lauf die Wallet-Sicht aus dem Ledger: Eventtitel/-URL und die Summe
  // der API-realisierten PnL der Bot-Maerkte dieses Laufs. Fuer Laeufe ohne
  // kuratierten Abgleich (wallet_netto_usd null) ist das die einzige
  // publizierte Wallet-Zahl; der Titel ersetzt den rohen Profilnamen.
  const ledgerJeLauf = {};
  if (ledger && Array.isArray(ledger.events)) {
    ledger.events.forEach((e) => {
      const slotVon = (profil) => ledgerJeLauf[profil] || (ledgerJeLauf[profil] = { pnl: 0, n: 0, titel: '', url: '', von: '' });
      (Array.isArray(e.maerkte) ? e.maerkte : []).forEach((m) => {
        if (String(m.zuordnung || '') !== 'bot' || !m.run_profil) return;
        const slot = slotVon(String(m.run_profil));
        if (m.pnl_usd != null && !isNaN(+m.pnl_usd)) { slot.pnl += +m.pnl_usd; slot.n += 1; }
      });
      if (e.run_profil) {
        const slot = slotVon(String(e.run_profil));
        if (!slot.titel && e.titel) slot.titel = String(e.titel);
        if (!slot.url && e.url) slot.url = String(e.url);
        if (!slot.von && e.von_utc) slot.von = String(e.von_utc);
      }
    });
  }
  const firstTaker = firstTakerKpi(payload);
  // Eine Zahlenwelt, nicht zwei: jede Geld-Kachel traegt die Wallet-Zahl
  // (Kassenwahrheit, frischeste Quelle zuerst). Die Log-Rekonstruktion
  // verwirrte mehr als sie erklaerte und ist von der Seite verschwunden;
  // sie erscheint nur noch als Rueckfall, wenn es keine Wallet-Zahl gibt,
  // und sagt dann, woher sie kommt.
  const nettoKachel = agg && (() => {
    if (frisch) return {
      label: 'NET PNL (WALLET, AS OF ' + frisch.stand + ')',
      value: (frisch.netto >= 0 ? '+$' : '-$') + num(Math.abs(frisch.netto).toFixed(0)),
      sub: 'cash truth from the on-chain wallet',
      color: frisch.netto >= 0 ? 'var(--pos)' : 'var(--neg)'
    };
    if (agg.wallet_netto_usd != null) return {
      label: 'NET PNL (WALLET' + (walletStand ? ', AS OF ' + walletStand : '') + ')',
      value: (+agg.wallet_netto_usd >= 0 ? '+$' : '-$') + num(Math.abs(+agg.wallet_netto_usd).toFixed(0)),
      sub: 'cash truth from the on-chain wallet',
      color: +agg.wallet_netto_usd >= 0 ? 'var(--pos)' : 'var(--neg)'
    };
    return {
      label: 'NET PNL (FROM RUN LOGS)',
      value: agg.realisierter_pnl_usd != null
        ? (agg.realisierter_pnl_usd >= 0 ? '+$' : '-$') + num(Math.abs(+agg.realisierter_pnl_usd).toFixed(0))
        : '—',
      sub: 'no wallet reconciliation yet',
      color: agg.realisierter_pnl_usd >= 0 ? 'var(--pos)' : 'var(--neg)'
    };
  })();
  // Statt der Stake-Summe die Rendite, dieselbe Rechnung wie auf der
  // Overview: Netto-Cashflow des ganzen Wallets gegen die einmalige
  // Einzahlung (on-chain nachpruefbar) — aus dem Ledger, sonst die
  // deklarierte Konstante. Nie die Kaufsumme als Basis: reinvestierte
  // Dollars wuerden die Rendite kleinrechnen.
  const la = ledger && ledger.aggregat ? ledger.aggregat : null;
  const einzahlungen = la && la.einzahlungen_usd != null ? +la.einzahlungen_usd : EINZAHLUNGEN_USD;
  const roiKachel = (la && la.netto_cashflow_usd != null && einzahlungen > 0)
    ? (() => {
      const roi = (100 * +la.netto_cashflow_usd) / einzahlungen;
      return {
        label: 'ROI (WALLET · ALL ACTIVITY)',
        value: (roi >= 0 ? '+' : '') + roi.toFixed(1) + '%',
        sub: 'net cashflow ' + (+la.netto_cashflow_usd >= 0 ? '+$' : '-$') + num(Math.abs(+la.netto_cashflow_usd).toFixed(0))
          + ' on the one-time deposit of $' + num(einzahlungen.toFixed(0)) + offeneNichtDrin(la),
        color: roi >= 0 ? 'var(--pos)' : 'var(--neg)'
      };
    })()
    : { label: 'ROI (WALLET)', value: '—', sub: 'wallet_ledger.json not loaded yet', color: 'var(--text)' };
  // W und L wie auf der Overview aus dem Wallet-Ledger, nicht aus der
  // Log-Rekonstruktion: gezaehlt werden die Bot-Maerkte des Wallets,
  // wertlos ausgelaufene zaehlen als verloren. Mehrere Fills desselben
  // Markts sind eine Wallet-Position, darum steht die Marktzahl dabei.
  // Ohne Ledger bleibt die Log-Zaehlung als benannter Rueckfall.
  let botPositionen = null;
  if (ledger && Array.isArray(ledger.events)) {
    const z = { n: 0, won: 0, lost: 0, open: 0 };
    ledger.events.forEach((e) => (Array.isArray(e.maerkte) ? e.maerkte : []).forEach((m) => {
      if (String(m.zuordnung || '') !== 'bot') return;
      z.n += 1;
      const st = String(m.status || '');
      if (st === 'won') z.won += 1;
      else if (st === 'lost' || st === 'worthless') z.lost += 1;
      else if (st === 'open') z.open += 1;
    }));
    if (z.n) botPositionen = z;
  }
  const betsKachel = agg && botPositionen
    ? { label: 'BETS', value: num(agg.n_wetten), sub: botPositionen.won + 'W · ' + botPositionen.lost + 'L · ' + botPositionen.open + ' open · ' + num(botPositionen.n) + ' bot markets in the wallet, worthless counts as lost', color: 'var(--text)' }
    : { label: 'BETS', value: agg ? num(agg.n_wetten) : '—', sub: agg ? agg.gewonnen + 'W · ' + agg.verloren + 'L · ' + agg.offen + ' open · from run logs' : '', color: 'var(--text)' };
  const kpis = agg ? [
    { label: 'RUNS', value: String(agg.n_runs), sub: 'one run = one episode or event', color: 'var(--text)' },
    betsKachel,
    roiKachel,
    nettoKachel,
    { label: 'FIRST TAKER', value: firstTaker.value, sub: firstTaker.sub, color: 'var(--text)' },
    { label: 'OPEN STAKE', value: '$' + num((+agg.offener_einsatz_usd).toFixed(0)), sub: 'in unresolved markets', color: 'var(--text)' }
  ] : [
    // Kein Rueckfall auf 64 Laeufe, 1.208 Wetten und eine Trefferquote von
    // 54 Prozent. Die Zahlen stehen in runs.json oder nirgends.
    { label: 'RUNS', value: '—', sub: 'runs.json not loaded', color: 'var(--text)' },
    { label: 'BETS', value: '—', sub: 'runs.json not loaded', color: 'var(--text)' },
    { label: 'ROI (WALLET)', value: '—', sub: 'runs.json not loaded', color: 'var(--text)' },
    { label: 'NET PNL', value: '—', sub: 'runs.json not loaded', color: 'var(--text)' },
    { label: 'FIRST TAKER', value: '—', sub: 'runs.json not loaded', color: 'var(--text)' },
    { label: 'OPEN STAKE', value: '—', sub: 'runs.json not loaded', color: 'var(--text)' }
  ];
  const laufSatz = herkunftSatz(
    payload ? { quelle: payload._quelle === 'fehler' ? 'fehler' : 'leer', fehler: payload._fehler } : null,
    'public/data/runs.json');

  const alleKarten = payload && payload.runs ? payload.runs.map((r) => {
    const ledgerLauf = ledgerJeLauf[String(r.profil || '')] || null;
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
    // Eine PnL-Zahl je Lauf, die Wallet-Sicht zuerst: kuratierter Abgleich,
    // sonst die Summe der API-realisierten PnL der Bot-Maerkte aus dem
    // Ledger, sonst die Log-Zahl — die dann sagt, dass sie aus dem Log
    // kommt. Die frueheren Doppel-Zahlen ("· log estimate …") sind weg.
    const geldMit = (v) => (+v >= 0 ? '+$' : '-$') + Math.abs(+v).toFixed(2);
    const pnlSatz = r.wallet_netto_usd != null
      ? 'PnL ' + geldMit(r.wallet_netto_usd) + ' (wallet)'
      : ledgerLauf && ledgerLauf.n
        ? 'PnL ' + geldMit(ledgerLauf.pnl) + ' (wallet)'
        : 'PnL ' + geldMit(r.realisierter_pnl_usd) + ' (from the run log, not yet in the wallet statement)';
    // Sortierschluessel: erster Fill, sonst Drop/Pubdate, sonst das Datum des
    // Ledger-Events — Laeufe ohne jeden Zeitstempel sortieren ans Ende.
    const fillZeiten = (r.wetten || []).map((b) => String(b.fill_ts_utc || '')).filter(Boolean).sort();
    return {
      profil: String(r.profil || ''),
      profile: String(r.profil || '').toUpperCase(), mode: String(r.modus || '').toUpperCase() === 'LIVE' ? 'REAL ORDERS' : 'DRY RUN',
      status: bets.length === 0 ? 'NO FILLS' : resolvedAll ? 'RESOLVED' : 'OPEN',
      title: laufTitel(r, ledgerLauf), url: episodenUrl(r) || (ledgerLauf ? ledgerLauf.url : ''), chips, bets,
      zeit: fillZeiten[0] || String(r.drop_erkannt_utc || r.pubdate_utc || (ledgerLauf && ledgerLauf.von) || ''),
      einsatzLog: +r.einsatz_usd, pnlLog: r.realisierter_pnl_usd != null ? +r.realisierter_pnl_usd : null,
      footer: 'Stake $' + (+r.einsatz_usd).toFixed(2) + ' · ' + pnlSatz,
      missed: missedN ? 'Missed chances (' + missedN + ') — budget or cap' : ''
    };
  }) : [];
  // Ein Lauf ohne Wette traegt drei Zahlen und sonst nichts. Als volle Karte
  // wiederholt er 150 Pixel lang "nichts passiert" und verdraengt die Laeufe,
  // in denen etwas passierte — er wird zur einzeiligen Zeile weiter unten.
  // Kein Deckel auf den Karten: jeder Lauf mit Fill ist eine Karte, jeder
  // ohne Fill eine Zeile — zusammen alle Laeufe aus runs.json. Beide Listen
  // neueste zuerst, wie die Ledger-Tabelle darunter; vorher standen die
  // Karten in Dateireihenfolge und die Earnings-Laeufe klumpten oben.
  const nachZeit = (a, b) => String(b.zeit || '').localeCompare(String(a.zeit || ''));
  const cards = alleKarten.filter((r) => r.bets.length).sort(nachZeit);
  const ohneFills = alleKarten.filter((r) => !r.bets.length).sort(nachZeit);

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
  // Dieselbe Zahl wie die PnL-Kachel: kumulierte Wallet-PnL je Lauf, aus den
  // Bot-Maerkten des Ledgers, nach erstem Fill geordnet. Die Log-Kurve endete
  // bei +$289 neben einer Kachel mit +$418 und las sich als Fehler. Nur wenn
  // jeder Lauf mit Fill im Ledger steht, sonst waere die Kurve eine Mischung
  // zweier Methoden — dann Rueckfall auf die Log-Reihe, so beschriftet.
  const walletPunkte = (() => {
    if (!payload || !Array.isArray(payload.runs)) return [];
    const mitZeit = [];
    for (const r of payload.runs) {
      if (!(r.wetten || []).length) continue;
      const lauf = ledgerJeLauf[String(r.profil || '')];
      if (!lauf || !lauf.n) return [];
      const fillZeiten = (r.wetten || []).map((b) => b.fill_ts_utc).filter(Boolean).sort();
      const zeit = fillZeiten[0] || r.drop_erkannt_utc || r.pubdate_utc || lauf.von;
      if (!zeit) return [];
      mitZeit.push({ zeit: String(zeit), pnl: lauf.pnl });
    }
    mitZeit.sort((a, b) => a.zeit.localeCompare(b.zeit));
    let summe = 0;
    return mitZeit.map((r) => {
      summe += r.pnl;
      return { label: r.zeit.slice(5, 10), wert: Math.round(summe * 100) / 100 };
    });
  })();
  const equityChart = walletPunkte.length > 1 ? stepKurve({
    titel: 'CUMULATIVE WALLET PNL BY RUN',
    einheit: 'USD · wallet, bot markets',
    hinweis: 'last bot fill ' + walletPunkte[walletPunkte.length - 1].label
      + (ledgerStand ? ' · wallet as of ' + ledgerStand : ''),
    punkte: walletPunkte
  }) : equityPunkte.length > 1 ? stepKurve({
    titel: 'CUMULATIVE PNL BY RUN',
    einheit: 'USD · from run logs',
    hinweis: agg && agg.wallet_netto_usd != null
      ? 'wallet net ' + (+agg.wallet_netto_usd >= 0 ? '+$' : '-$')
        + Math.abs(+agg.wallet_netto_usd).toFixed(0)
        + (agg.wallet_abgleich_stand ? ' as of ' + agg.wallet_abgleich_stand : '')
      : 'no wallet reconciliation yet',
    punkte: equityPunkte
  }) : '';

  const timingRows = payload && payload.runs ? payload.runs.flatMap((r) =>
    (r.wetten || []).filter((b) => b.fill_ts_utc).map((b) => ({
      run: String(r.profil || '').slice(0, 10),
      market: b.frage,
      drop: r.drop_erkannt_utc ? String(r.drop_erkannt_utc).slice(11, 19) : '—',
      fill: String(b.fill_ts_utc).slice(11, 19),
      lat: (() => { const s = fillLatenzS(r, b); return s == null ? null : Math.round(s * 1000); })(),
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
    // EINE Tabelle fuer alles: jedes Wallet-Event (Bot-Zeilen oeffnen sich
    // aufs volle Laufdetail — Chips, Wetten, Latenz), der Pilot gruppiert,
    // die Laeufe ohne Fill als NO-FILLS-Zeilen. Karten gibt es nur noch als
    // Rueckfall, wenn kein Ledger geladen ist — vorher standen acht Karten,
    // dann die Tabelle mit denselben Events, dann der Rest: drei Darstellungen
    // fuer eine Sache.
    body = '<div style="margin-top:14px">'
      // Der Erklaertext steht im zugeklappten WHAT THIS TABLE IS des
      // Tabellenabschnitts — hier nur noch im Rueckfall ohne Ledger.
      + (!ledger
        ? '<div style="font-size:12.5px; color:rgba(var(--ink),.5); line-height:1.5; max-width:820px; margin-bottom:14px">Race chips compare each fill against the public taker tape of that market: how many other trades hit between the drop and our fill, and how long until the next trader after us. The anchor is the bot\'s logged fill time — chain timestamps can differ by a few seconds.</div>'
        : '')
      + (alleKarten.length ? '' : leerZeile(laufSatz))
      + (!ledger && cards.length
        ? '<div style="' + M + '; font-size:11px; letter-spacing:.12em; color:rgba(var(--ink),.5); margin-bottom:10px">RUNS WITH FILLS · ' + cards.length
          + ' <span style="color:rgba(var(--ink),.55); letter-spacing:0">· newest first</span></div>'
          + '<div style="display:flex; flex-direction:column; gap:12px">'
          + cards.map((r) => {
            const statusStyle = M + '; font-size:10.5px; letter-spacing:.1em; border-radius:4px; padding:3px 8px; ' + (r.status === 'RESOLVED' ? 'color:rgba(var(--ink),.6); border:1px solid rgba(var(--ink),.18)' : r.status === 'OPEN' ? 'color:var(--warn); border:1px solid rgba(var(--warn-rgb),.4)' : 'color:rgba(var(--ink),.6); border:1px solid rgba(var(--ink),.12)');
            return '<div style="background:var(--panel); border:1px solid rgba(var(--ink),.09); border-radius:6px; padding:16px 18px">'
              + '<div style="display:flex; gap:7px; flex-wrap:wrap">'
              + '<div style="' + M + '; font-size:10.5px; letter-spacing:.1em; border-radius:4px; padding:3px 8px; color:var(--info); border:1px solid rgba(var(--info-rgb),.4)">' + esc(r.profile) + '</div>'
              + '<div style="' + M + '; font-size:10.5px; letter-spacing:.1em; border-radius:4px; padding:3px 8px; color:var(--info); border:1px solid rgba(var(--info-rgb),.4)">' + esc(r.mode) + '</div>'
              + '<div style="' + statusStyle + '">' + esc(r.status) + '</div></div>'
              + '<div style="font-size:15px; font-weight:600; margin-top:11px">' + esc(r.title)
              + (r.url ? ' <a href="' + esc(r.url) + '" target="_blank" rel="noopener" style="' + M + '; font-size:11px; color:var(--info); text-decoration:none">event ↗</a>' : '')
              + '</div>'
              + '<div style="display:flex; gap:7px; flex-wrap:wrap; margin-top:10px">'
              + r.chips.map((c) => '<div style="' + M + '; font-size:10.5px; color:rgba(var(--ink),.65); background:var(--panel-hover); border:1px solid rgba(var(--ink),.09); border-radius:4px; padding:4px 9px">' + esc(c) + '</div>').join('')
              + '</div>'
              + '<div style="margin-top:12px; border-top:1px solid rgba(var(--ink),.07)">' + laufWettenHtml(r) + '</div>'
              + '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.6); margin-top:10px">' + esc(r.footer) + '</div>'
              + (r.missed ? '<div style="' + M + '; font-size:11px; color:var(--warn); margin-top:7px">' + esc(r.missed) + '</div>' : '')
              + '</div>';
          }).join('')
          + '</div>'
        : '')
      + (ohneFills.length && !ledger
        ? '<div style="border:1px solid rgba(var(--ink),.09); border-radius:6px; margin-top:14px; overflow:hidden">'
          + '<div style="padding:10px 16px; background:var(--panel); border-bottom:1px solid rgba(var(--ink),.09); ' + M + '; font-size:11px; letter-spacing:.12em; color:rgba(var(--ink),.5)">RUNS WITHOUT A FILL · ' + ohneFills.length
          + ' <span style="color:rgba(var(--ink),.55); letter-spacing:0">· the decision layer ran and placed nothing — one line per run, newest first</span></div>'
          + ohneFills.map((r) =>
            '<div style="display:flex; align-items:center; gap:10px; padding:9px 16px; border-bottom:1px solid rgba(var(--ink),.05)">'
            + '<div style="' + M + '; font-size:10.5px; letter-spacing:.08em; color:var(--info); border:1px solid rgba(var(--info-rgb),.35); border-radius:4px; padding:2px 7px; white-space:nowrap">' + esc(r.profile) + '</div>'
            + '<div style="font-size:12.5px; color:rgba(var(--ink),.75); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; flex:1" title="' + esc(r.title) + '">' + esc(r.title) + '</div>'
            + '<div style="' + M + '; font-size:10.5px; color:rgba(var(--ink),.6); white-space:nowrap">' + esc(r.chips.filter((c) => /decisions|priced/.test(c)).join(' · ') || '—') + '</div>'
            + '<div style="' + M + '; font-size:10.5px; color:rgba(var(--ink),.55); white-space:nowrap">' + esc(r.mode.toLowerCase()) + ' · no fills</div>'
            + '</div>').join('')
          + '</div>'
        : '')
      + walletLedgerHtml(T, payload, ohneFills, ledger ? cards : [])
      + '</div>';
  } else if (s.liveTab === 'timing') {
    // Erst die Kurven, dann die Tabelle: Repricing je Wette als Treppe aus
    // repricing[].punkte, dazu die Verzoegerungsreihe aus extras.timing_decay,
    // wenn die API sie anhaengt. Ohne Punkte kein Diagramm, die Tabelle bleibt.
    const repricingHtml = repricingKurvenHtml(payload);
    const decayHtml = timingDecayLinienHtml(payload);
    const repSpalten = '80px 1fr 90px 90px 100px 118px 106px 96px 96px';
    body = repricingHtml + decayHtml
      + '<div style="border:1px solid rgba(var(--ink),.09); border-radius:6px; margin-top:14px; overflow:hidden">'
      + '<div style="padding:11px 16px; background:var(--panel); border-bottom:1px solid rgba(var(--ink),.09); ' + M + '; font-size:10.5px; letter-spacing:.14em; color:var(--info)">TIMING AND REPRICING PER FILL · ' + timingRows.length + ' FILLS</div>'
      + '<div style="display:grid; grid-template-columns:' + repSpalten + '; gap:10px; padding:9px 16px; border-bottom:1px solid rgba(var(--ink),.09); ' + M + '; font-size:10.5px; letter-spacing:.12em; color:rgba(var(--ink),.6)">'
      + '<div>RUN</div><div>MARKET</div><div style="text-align:right">DROP</div><div style="text-align:right">FILL</div><div style="text-align:right">LATENCY</div><div style="text-align:right">TRADES BEFORE US</div><div style="text-align:right">NEXT TRADER</div><div style="text-align:right">REPRICE 30 S</div><div style="text-align:right">REPRICE 900 S</div></div>'
      + (timingRows.length ? '' : leerZeile(laufSatz))
      + timingRows.map((t) => {
        // Ueber einer Sekunde in Sekunden, ueber zwei Minuten in Minuten oder
        // Stunden: der spaeteste Fill eines Laufs liegt einen Tag nach dem
        // Drop, und "90547.0 s" liest kein Mensch.
        const latLabel = t.lat == null ? '—'
          : t.lat >= 120000 ? sekundenText(t.lat / 1000)
            : t.lat >= 1000 ? (t.lat / 1000).toFixed(1) + ' s' : t.lat + ' ms';
        const latStyle = 'text-align:right; ' + M + '; font-size:12px; color:' + (t.lat == null ? 'rgba(var(--ink),.5)' : t.lat <= 800 ? 'var(--pos)' : t.lat <= 1500 ? 'var(--warn)' : 'var(--neg)');
        const repLabel = (v) => (v == null ? '—' : (v >= 0 ? '+' : '') + v + '¢');
        const repStyle = (v) => 'text-align:right; ' + M + '; font-size:12px; color:' + (v != null && v >= 5 ? 'var(--pos)' : v != null && v <= -5 ? 'var(--neg)' : 'rgba(var(--ink),.6)');
        return '<div style="display:grid; grid-template-columns:' + repSpalten + '; gap:10px; align-items:center; padding:11px 16px; border-bottom:1px solid rgba(var(--ink),.06); ' + M + '; font-size:12px">'
          + '<div style="color:rgba(var(--ink),.55)">' + esc(t.run) + '</div>'
          + '<div style="font-family:\'IBM Plex Sans\',sans-serif; font-size:12.5px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="' + esc(t.market) + '">' + esc(t.market) + '</div>'
          + '<div style="text-align:right; color:rgba(var(--ink),.55)">' + esc(t.drop) + '</div>'
          + '<div style="text-align:right; color:rgba(var(--ink),.55)">' + esc(t.fill) + '</div>'
          + '<div style="' + latStyle + '">' + latLabel + '</div>'
          + '<div style="text-align:right; color:rgba(var(--ink),.7)">' + esc(String(t.before)) + '</div>'
          + '<div style="text-align:right; color:rgba(var(--ink),.7)">' + esc(t.next) + '</div>'
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
      + '<div style="font-size:12.5px; color:rgba(var(--ink),.55); line-height:1.5; max-width:820px">Replays the same runs with a different stake rule each time — same entries, same fills, only the size changes. Caps and the per-run budget stay as they were on the day.' + (liveSims ? ' Only resolved bets with a valid fill price count; bankroll $100, no compounding.' : '') + ' Every figure in this tab is a simulation on log-estimated fills — not cash; the cash figure is the wallet-reconciled net in the tiles above.</div>'
      + '<div style="border:1px solid rgba(var(--ink),.09); border-radius:6px; margin-top:14px; overflow:hidden">'
      + '<div style="display:grid; grid-template-columns:1fr 110px 96px 96px 96px 104px; gap:10px; padding:9px 16px; background:var(--panel); border-bottom:1px solid rgba(var(--ink),.09); ' + M + '; font-size:10.5px; letter-spacing:.12em; color:rgba(var(--ink),.6)">'
      + '<div>STAKE RULE</div><div style="text-align:right">NET</div><div style="text-align:right">ROI</div><div style="text-align:right">MAX DD</div><div style="text-align:right">HIT RATE</div><div style="text-align:right">BETS PLACED</div></div>'
      + (simRows.length ? '' : leerZeile(laufSatz))
      + simRows.slice().sort((a, b) => b.roi - a.roi).map((r, i) =>
        '<div style="display:grid; grid-template-columns:1fr 110px 96px 96px 96px 104px; gap:10px; align-items:center; padding:11px 16px; border-bottom:1px solid rgba(var(--ink),.06); background:' + (i === 0 ? 'rgba(var(--accent-rgb),.06)' : 'transparent') + '">'
        + '<div style="font-size:12.5px; color:' + (i === 0 ? 'var(--accent)' : 'var(--text)') + '">' + esc(r.name) + '</div>'
        + '<div style="text-align:right; ' + M + '; font-size:12.5px; color:' + (r.net >= 0 ? 'var(--pos)' : 'var(--neg)') + '">' + (r.net >= 0 ? '+$' : '-$') + num(Math.abs(r.net).toFixed(0)) + '</div>'
        + '<div style="text-align:right; ' + M + '; font-size:12.5px; color:' + (r.roi >= 0 ? 'var(--pos)' : 'var(--neg)') + '">' + (r.roi >= 0 ? '+' : '') + r.roi.toFixed(1) + '%</div>'
        + '<div style="text-align:right; ' + M + '; font-size:12.5px; color:rgba(var(--ink),.6)">' + (r.dd != null ? r.dd.toFixed(1) + '%' : '—') + '</div>'
        + '<div style="text-align:right; ' + M + '; font-size:12.5px; color:rgba(var(--ink),.6)">' + (r.hit != null ? r.hit + '%' : '—') + '</div>'
        + '<div style="text-align:right; ' + M + '; font-size:12.5px; color:rgba(var(--ink),.6)">' + num(r.bets) + '</div></div>'
      ).join('')
      + '</div>'
      + (liveSims && extras.timing_decay && extras.timing_decay.length
        ? '<div style="border:1px solid rgba(var(--ink),.09); border-radius:6px; margin-top:14px; overflow:hidden">'
          + '<div style="padding:11px 16px; background:var(--panel); border-bottom:1px solid rgba(var(--ink),.09); ' + M + '; font-size:10.5px; letter-spacing:.14em; color:var(--info)">SAME MODEL, DELAYED ENTRY — PNL DECAY BY DELAY</div>'
          + '<div style="display:grid; grid-template-columns:1fr 110px 130px 120px 130px 130px; gap:10px; padding:9px 16px; border-bottom:1px solid rgba(var(--ink),.09); ' + M + '; font-size:10.5px; letter-spacing:.12em; color:rgba(var(--ink),.6)">'
          + '<div>DELAY</div><div style="text-align:right">BETS</div><div style="text-align:right">FOREIGN REF</div><div style="text-align:right">PRICED OUT</div><div style="text-align:right">SIM PNL</div><div style="text-align:right">VS INSTANT</div></div>'
          + extras.timing_decay.map((t) =>
            '<div style="display:grid; grid-template-columns:1fr 110px 130px 120px 130px 130px; gap:10px; align-items:center; padding:10px 16px; border-bottom:1px solid rgba(var(--ink),.06); ' + M + '; font-size:12px">'
            + '<div style="font-family:\'IBM Plex Sans\',sans-serif; font-size:12.5px">+' + t.delay_s + ' s</div>'
            + '<div style="text-align:right; color:rgba(var(--ink),.6)">' + t.n_bets + '</div>'
            + '<div style="text-align:right; color:rgba(var(--ink),.6)">' + t.n_foreign_ref + '</div>'
            + '<div style="text-align:right; color:rgba(var(--ink),.6)">' + t.n_priced_out + '</div>'
            + '<div style="text-align:right; color:' + (t.sim_pnl_usd >= 0 ? 'var(--pos)' : 'var(--neg)') + '">' + (t.sim_pnl_usd >= 0 ? '+$' : '-$') + Math.abs(t.sim_pnl_usd).toFixed(2) + '</div>'
            + '<div style="text-align:right; color:' + (t.pnl_delta_usd >= 0 ? 'rgba(var(--ink),.6)' : 'var(--neg)') + '">' + (t.pnl_delta_usd >= 0 ? '+$' : '-$') + Math.abs(t.pnl_delta_usd).toFixed(2) + '</div></div>'
          ).join('')
          + '</div>'
        // Hier liefen zwei Zufallskurven mit eingebautem Aufwaertsdrift unter
        // der Ueberschrift FLAT $25 VERSUS THE BEST RULE. Eine gemalte Kurve
        // ist eine Behauptung; ohne timing_decay in der Nutzlast gibt es
        // keine.
        : '<div style="background:var(--panel); border:1px solid rgba(var(--ink),.09); border-radius:6px; margin-top:14px; padding:16px 18px">'
          + '<div style="' + M + '; font-size:10.5px; letter-spacing:.14em; color:rgba(var(--ink),.55); margin-bottom:10px">DELAYED ENTRY</div>'
          + '<div style="font-size:12.5px; color:rgba(var(--ink),.5); line-height:1.5">'
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
      + '<div style="font-size:12.5px; color:rgba(var(--ink),.55); line-height:1.5; max-width:820px">Entry price against what actually happened. A perfectly calibrated entry sits on the diagonal — above it means we paid too much.' + esc(calibNote) + '</div>'
      + (calibChart ? '<div style="margin-top:14px; max-width:420px">' + calibChart + '</div>' : '')
      + '<div style="border:1px solid rgba(var(--ink),.09); border-radius:6px; margin-top:14px; overflow:hidden">'
      + '<div style="display:grid; grid-template-columns:1fr 90px 110px 110px 110px; gap:10px; padding:9px 16px; background:var(--panel); border-bottom:1px solid rgba(var(--ink),.09); ' + M + '; font-size:10.5px; letter-spacing:.12em; color:rgba(var(--ink),.6)">'
      + '<div>ENTRY PRICE BAND</div><div style="text-align:right">BETS</div><div style="text-align:right">PAID</div><div style="text-align:right">SETTLED</div><div style="text-align:right">GAP</div></div>'
      + (calibRows.length ? '' : leerZeile(laufSatz))
      + calibRows.map((c) => {
        const gap = c.settled - c.paid;
        return '<div style="display:grid; grid-template-columns:1fr 90px 110px 110px 110px; gap:10px; align-items:center; padding:11px 16px; border-bottom:1px solid rgba(var(--ink),.06); ' + M + '; font-size:12.5px">'
          + '<div style="font-family:\'IBM Plex Sans\',sans-serif; font-size:13px">' + c.band + '</div>'
          + '<div style="text-align:right; color:rgba(var(--ink),.6)">' + num(c.n) + '</div>'
          + '<div style="text-align:right">' + c.paid + '¢</div>'
          + '<div style="text-align:right">' + c.settled + '¢</div>'
          + '<div style="text-align:right; ' + M + '; font-size:12.5px; color:' + (gap >= 0 ? 'var(--pos)' : 'var(--neg)') + '">' + (gap >= 0 ? '+' : '') + gap + '¢</div></div>';
      }).join('')
      + '</div></div>';
  } else {
    const extras = payload && payload.extras;
    const monthRows = extras && extras.monthly ? extras.monthly : [];
    body = '<div style="border:1px solid rgba(var(--ink),.09); border-radius:6px; margin-top:14px; overflow:hidden">'
      + '<div style="padding:11px 16px; background:var(--panel); border-bottom:1px solid rgba(var(--ink),.09); ' + M + '; font-size:10.5px; letter-spacing:.14em; color:var(--info)">MONTH BY MONTH</div>'
      + '<div style="display:grid; grid-template-columns:1fr 90px 110px 110px 110px 100px; gap:10px; padding:9px 16px; border-bottom:1px solid rgba(var(--ink),.09); ' + M + '; font-size:10.5px; letter-spacing:.12em; color:rgba(var(--ink),.6)">'
      + '<div>MONTH</div><div style="text-align:right">RUNS</div><div style="text-align:right">BETS</div><div style="text-align:right">STAKE</div><div style="text-align:right">NET</div><div style="text-align:right">NET / SETTLED STAKE</div></div>'
      + (monthRows.length ? '' : leerZeile(laufSatz))
      + monthRows.map((t) => {
        // Der Zaehler zaehlt nur aufgeloeste Wetten, also gehoert in den
        // Nenner nur deren Einsatz. Vorher stand hier net / stake ueber
        // ALLE Wetten des Monats, offene eingeschlossen — das drueckte jede
        // Quote nach unten. Und die Spalte hiess ROI: die Wallet-Rendite
        // dieses Projekts rechnet gegen die einmalige Einzahlung (siehe die
        // Kachel ROI · WALLET), nicht gegen einen Einsatz.
        const basis = +t.settled_stake || 0;
        const quote = basis > 0 ? (t.net / basis) * 100 : null;
        const offen = Math.max(0, (+t.bets || 0) - (+t.settled_bets || 0));
        return '<div style="display:grid; grid-template-columns:1fr 90px 110px 110px 110px 100px; gap:10px; align-items:center; padding:11px 16px; border-bottom:1px solid rgba(var(--ink),.06); ' + M + '; font-size:12.5px">'
          + '<div style="font-family:\'IBM Plex Sans\',sans-serif; font-size:13px">' + t.month + '</div>'
          + '<div style="text-align:right; color:rgba(var(--ink),.6)">' + t.runs + '</div>'
          + '<div style="text-align:right; color:rgba(var(--ink),.6)">' + num(t.bets) + '</div>'
          + '<div style="text-align:right; color:rgba(var(--ink),.6)">$' + num(t.stake) + '</div>'
          + '<div style="text-align:right; ' + M + '; font-size:12.5px; color:' + (t.net >= 0 ? 'var(--pos)' : 'var(--neg)') + '">' + (t.net >= 0 ? '+$' : '-$') + num(Math.abs(t.net)) + '</div>'
          + '<div style="text-align:right; ' + M + '; font-size:12.5px; color:' + (quote == null ? 'rgba(var(--ink),.5)' : quote >= 0 ? 'var(--pos)' : 'var(--neg)') + '">'
          + (quote == null ? 'no bet settled' : (quote >= 0 ? '+' : '') + quote.toFixed(1) + '% <span style="font-size:10.5px; color:rgba(var(--ink),.45)">of $' + num(Math.round(basis)) + (offen ? ' · ' + offen + ' open' : '') + '</span>') + '</div></div>';
      }).join('')
      + '<div style="padding:9px 16px; ' + M + '; font-size:10.5px; color:rgba(var(--ink),.5); line-height:1.6">'
      + 'NET is the settled result of the bets placed that month; the last column divides it by the stake of the settled bets only, so open stake does not dilute it. '
      + 'This is a return on stake, not the wallet return — the wallet return is measured against the one-time deposit and is shown as ROI · WALLET above.</div>'
      + '</div>';
  }

  return '<div style="padding:20px 24px 26px">'
    + '<div style="display:flex; align-items:flex-start; justify-content:space-between; gap:24px">'
    + '<div style="max-width:660px">'
    + '<div style="font-size:20px; font-weight:600">Our own bot runs</div>'
    + '<div style="font-size:13.5px; color:rgba(var(--ink),.6); margin-top:8px; line-height:1.5">' + esc(payload && payload.hinweis ? payload.hinweis : 'Bets, reaction times and realized results of the research bot on mentions markets. One run is one episode or event.') + '</div></div>'
    + '<div style="display:flex; gap:8px">'
    + '<div style="' + M + '; font-size:10.5px; letter-spacing:.1em; border-radius:4px; padding:3px 8px; color:var(--on-accent); background:var(--accent)">' + esc(payload && payload.kennzeichnung ? String(payload.kennzeichnung).toUpperCase() : 'LIVE / DESCRIPTIVE') + '</div>'
    + stempelBlock(T.studies[3], payload, '5px 10px')
    + '</div></div>'
    + '<div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(150px, 1fr)); gap:12px; margin-top:18px">'
    + kpis.map((k) =>
      '<div style="background:var(--panel); border:1px solid rgba(var(--ink),.09); border-radius:6px; padding:14px 16px">'
      + '<div style="' + M + '; font-size:10.5px; letter-spacing:.13em; color:rgba(var(--ink),.6)">' + esc(k.label) + '</div>'
      + '<div style="' + M + '; font-size:21px; margin-top:7px; color:' + k.color + '; white-space:nowrap">' + esc(k.value) + '</div>'
      + '<div style="' + M + '; font-size:10.5px; color:rgba(var(--ink),.6); margin-top:4px">' + esc(k.sub) + '</div></div>'
    ).join('')
    + '</div>'
    // Die Adresse, ueber die jeder jede Zahl der Seite nachrechnen kann —
    // der aufklappbare LOG-VS-WALLET-Block, der hier stand, erklaerte eine
    // zweite Zahlenwelt, die die Seite nicht mehr zeigt.
    + '<div style="' + M + '; font-size:10.5px; color:rgba(var(--ink),.6); margin-top:10px; line-height:1.6">'
    + 'Wallet ' + walletLinkHtml() + ' · the headline figures come from the public Polymarket Data API for this address — anyone can rerun the check.'
    + '</div>'
    // Die versprochene Kurve der Seite: kumulierte PnL je Lauf, aus den
    // publizierten Laufwerten. Ohne Serie kein Diagramm.
    + (equityChart ? '<div style="margin-top:12px">' + equityChart + '</div>' : '')
    // Der Preispfad nach dem Fill (preis_nach_fill) wird hier nicht mehr
    // gezeichnet — Wunsch des Wallet-Inhabers; die Daten bleiben in runs.json
    // und die Spalten REPRICE 30 S / 900 S im Timing-Reiter lesen sie weiter.
    + '<div style="display:flex; gap:6px; margin-top:18px; flex-wrap:wrap">' + liveTabs + '</div>'
    + body
    + paperLogHtml(T)
    + '</div>';
}

// Der Knopf zu einer archivierten Studienseite: nicht mehr in der
// Seitenleiste, aber die volle Seite bleibt am Slug erreichbar.
function archivKnopf(T, slug, label) {
  const idx = T.studies.findIndex((st) => studienSlug(st) === slug);
  if (idx < 0) return '';
  return '<div ' + T.act(() => {
    if (T.goStudy) { T.goStudy(idx); return; }
    T.setState({ page: 'research', researchTab: idx, detail: null });
    try { history.pushState(null, '', '#research/' + slug); } catch (e) { /* file:// */ }
    T.fetchPageData('research');
  }) + ' class="hv-bd35" style="font-size:12.5px; color:var(--text); border:1px solid rgba(var(--ink),.2); border-radius:4px; padding:8px 14px; cursor:pointer; display:inline-block">' + esc(label) + '</div>';
}

// Forward paper log, zusammengefasst auf der Live-runs-Seite: dieselbe
// Wortzaehler-Pipeline im Watch-Modus, je Lauf Entscheidungen, Papier-Kaeufe
// und Extraktion aus pipeline_forward.json (laedt neben runs.json, app.js
// BEGLEITER). Nur Zaehlwerte aus der Nutzlast — keine Equity, kein
// Return-Claim; die volle Archivseite haengt am Slug pipeline-forward.
function paperLogHtml(T) {
  const pf = T.liveData && T.liveData.research ? T.liveData.research['Pipeline forward'] : null;
  const karte = 'background:var(--panel); border:1px solid rgba(var(--ink),.09); border-radius:6px; margin-top:14px; padding:18px 20px';
  const kopf = '<div style="' + M + '; font-size:11px; letter-spacing:.14em; color:var(--info)">FORWARD PAPER LOG · SAME PIPELINE, NO MONEY</div>';
  if (!pf || pf._quelle === 'fehler') {
    const satz = pf && pf._quelle === 'fehler'
      ? 'pipeline_forward.json did not answer: ' + String(pf._fehler || 'no answer')
      : 'reading pipeline_forward.json…';
    return '<div style="' + karte + '">' + kopf
      + '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.55); margin-top:8px">' + esc(satz) + '</div></div>';
  }
  const laeufe = Array.isArray(pf.laeufe) ? pf.laeufe : [];
  const stand = pf.stand_utc ? String(pf.stand_utc).slice(0, 10) : '';
  const entscheidungen = laeufe.reduce((a, l) => a + (+l.n_eintraege || 0), 0);
  const kaeufe = laeufe.reduce((a, l) => a + (+l.n_kaeufe || 0), 0);
  const zeilen = laeufe.map((l) => {
    const quote = l.extraktionsquote != null ? Math.round(+l.extraktionsquote * 100) + '%' : '—';
    const gekauft = l.extraktion_gekauft_usd != null ? '$' + num(Math.round(+l.extraktion_gekauft_usd)) : '—';
    return '<div style="display:grid; grid-template-columns:1fr 110px 110px 130px; gap:10px; align-items:center; padding:9px 16px; border-bottom:1px solid rgba(var(--ink),.06); ' + M + '; font-size:12px">'
      + '<div style="font-family:\'IBM Plex Sans\',sans-serif; font-size:13px">' + esc(String(l.profil || '—')) + '</div>'
      + '<div style="text-align:right; color:rgba(var(--ink),.6)">' + num(+l.n_eintraege || 0) + '</div>'
      + '<div style="text-align:right">' + num(+l.n_kaeufe || 0) + '</div>'
      + '<div style="text-align:right; color:rgba(var(--ink),.6)">' + esc(gekauft) + ' · ' + esc(quote) + '</div></div>';
  }).join('');
  return '<div style="' + karte + '">'
    + '<div style="display:flex; align-items:baseline; justify-content:space-between; gap:12px; flex-wrap:wrap">' + kopf
    + '<div style="' + M + '; font-size:10.5px; color:rgba(var(--ink),.55)">' + num(laeufe.length) + ' paper runs · ' + num(entscheidungen) + ' decisions · ' + num(kaeufe) + ' paper buys' + (stand ? ' · ' + esc(stand) : '') + '</div></div>'
    + '<div style="font-size:12.5px; color:rgba(var(--ink),.6); margin-top:8px; line-height:1.55; max-width:820px">The same word-count pipeline in watch mode: it reads the live transcript and logs, per market, whether its rules would have allowed a bet — mostly they would not. Decisions and best book prices only, no fills, no wallet data, no return claim. What the same pipeline did with real money is the record above.</div>'
    + (zeilen
      ? '<div style="border:1px solid rgba(var(--ink),.09); border-radius:6px; margin-top:12px; overflow:hidden">'
        + '<div style="display:grid; grid-template-columns:1fr 110px 110px 130px; gap:10px; padding:8px 16px; background:var(--bg); border-bottom:1px solid rgba(var(--ink),.09); ' + M + '; font-size:10.5px; letter-spacing:.12em; color:rgba(var(--ink),.6)">'
        + '<div>RUN PROFILE</div><div style="text-align:right">DECISIONS</div><div style="text-align:right">PAPER BUYS</div><div style="text-align:right">EXTRACTION</div></div>'
        + zeilen + '</div>'
      : '<div style="margin-top:10px">' + leerZeile('pipeline_forward.json carries no runs.') + '</div>')
    + '<div style="display:flex; gap:10px; margin-top:12px; flex-wrap:wrap">'
    + archivKnopf(T, 'pipeline-forward', 'Open the full paper log')
    + '<a href="./data/pipeline_forward.json" download="pipeline_forward.json" class="hv-bd35" style="font-size:12.5px; color:var(--text); border:1px solid rgba(var(--ink),.2); border-radius:4px; padding:8px 14px; text-decoration:none; display:inline-block">Download the data</a>'
    + '</div></div>';
}

// Die archivierte Review queue als Abschnitt der Methodology-Seite: der
// taegliche Lauf endete 2026-08-07, die Queue ist seit 2026-07-14
// eingefroren — die Zaehler bleiben hier lesbar, die volle Seite haengt am
// Slug review-queue (app.js BEGLEITER laedt queue.json mit).
function queueArchivHtml(T) {
  const q = T.liveData && T.liveData.research ? T.liveData.research['Review queue'] : null;
  const karte = 'background:var(--panel); border:1px solid rgba(var(--ink),.09); border-radius:6px; margin-top:14px; padding:16px 18px';
  const kopf = '<div style="' + M + '; font-size:11px; letter-spacing:.14em; color:var(--info)">HUMAN VERIFICATION QUEUE · ARCHIVED</div>';
  const zahl = q
    ? (q._quelle === 'fehler'
      ? 'queue.json did not answer: ' + String(q._fehler || 'no answer')
      : num(Array.isArray(q.faelle) ? q.faelle.length : 0) + ' flagged cases'
        + (q.stand_utc ? ' · last run ' + String(q.stand_utc).slice(0, 10) : ''))
    : 'reading queue.json…';
  return '<div style="' + karte + '">'
    + '<div style="display:flex; align-items:baseline; justify-content:space-between; gap:12px; flex-wrap:wrap">' + kopf
    + '<div style="' + M + '; font-size:10.5px; color:rgba(var(--ink),.55)">' + esc(zahl) + '</div></div>'
    + '<div style="font-size:12.5px; color:rgba(var(--ink),.6); margin-top:8px; line-height:1.55; max-width:820px">Cases the daily run flagged for a human to check, ranked by how much the automated read and the market disagree. The queue froze 2026-07-14 and the daily run ended 2026-08-07 — a closed record, kept verifiable, not an ongoing process.</div>'
    + '<div style="display:flex; gap:10px; margin-top:12px; flex-wrap:wrap">'
    + archivKnopf(T, 'review-queue', 'Open the archived queue')
    + '<a href="./data/queue.json" download="queue.json" class="hv-bd35" style="font-size:12.5px; color:var(--text); border:1px solid rgba(var(--ink),.2); border-radius:4px; padding:8px 14px; text-decoration:none; display:inline-block">Download the data</a>'
    + '</div></div>';
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

// The address as links: the address itself opens the on-chain view on
// Polygonscan, next to it the Polymarket profile with the same trades in
// market terms.
function walletLinkHtml(adresse) {
  const a = String(adresse || LIVE_RUN_WALLET);
  return '<a href="https://polygonscan.com/address/' + esc(a) + '" target="_blank" rel="noopener" style="color:var(--info); text-decoration:none" title="view on-chain on Polygonscan">' + esc(a) + ' ↗</a>'
    + ' · <a href="https://polymarket.com/profile/' + esc(a) + '" target="_blank" rel="noopener" style="color:var(--info); text-decoration:none">Polymarket profile ↗</a>';
}

// Drop sources as they appear in runs.json (drop_quelle), in plain words.
const DROP_QUELLE_TEXT = {
  libsyn_rss: 'RSS feed',
  youtube: 'YouTube channel page',
  mp3_url_prober: 'MP3 URL probe'
};

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

// Card title for a run: its own episode title; without one the event title
// from the wallet ledger, else the event slug in words (trailing timestamp
// digits stripped), else the raw profile. The earnings runs carry no
// episode_titel and used to head their cards with "earnings_axp_july24"
// while the ledger below showed the same event with its real title.
function laufTitel(r, ledgerLauf) {
  const eigen = episodenTitel(r);
  if (eigen && eigen !== String((r && r.profil) || '')) return eigen;
  if (ledgerLauf && ledgerLauf.titel) return ledgerLauf.titel;
  const slug = String((r && r.event_slug) || '').replace(/-\d{8,}$/, '').replace(/-/g, ' ').trim();
  if (slug) return slug.charAt(0).toUpperCase() + slug.slice(1);
  return eigen;
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

// Latenz EINES Fills in Sekunden: sein fill_ts_utc minus drop_erkannt_utc des
// Laufs. Hier stand die Laufzahl erster_fill_s, und die gilt nur fuer den
// FRUEHESTEN Fill des Laufs — in der Tabelle "pro Fill" trug damit jede Zeile
// desselben Laufs dieselbe Zahl. Bei allin_july10 (drop 2026-07-10T01:17:27Z,
// erster_fill_s 64) las die letzte von sieben Zeilen so 64.0 s, obwohl ihr
// Fill am naechsten Tag lag: 90.547 s nach dem Drop, Faktor 1.415. Ohne
// Drop-Zeitstempel bleibt erster_fill_s als Rueckfall, aber nur fuer die
// Zeile, fuer die er gilt; alle anderen bekommen einen Strich.
export function fillLatenzS(run, bet) {
  const drop = Date.parse(String((run && run.drop_erkannt_utc) || ''));
  const fill = Date.parse(String((bet && bet.fill_ts_utc) || ''));
  if (!isNaN(drop) && !isNaN(fill)) return (fill - drop) / 1000;
  if (!run || run.erster_fill_s == null || !bet || !bet.fill_ts_utc) return null;
  const zeiten = (run.wetten || []).map((b) => String(b.fill_ts_utc || '')).filter(Boolean).sort();
  return zeiten.length && String(bet.fill_ts_utc) === zeiten[0] ? +run.erster_fill_s : null;
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

// ---- wallet ledger: everything the wallet did, by event (wallet_ledger.json)

// Module-level cache for the static path (marketintel.dev): the file is
// fetched once, then every render reads it from here. When the API answers,
// the ledger already sits in payload.extras.wallet_ledger and no fetch runs.
const LEDGER = { daten: null, laedt: false, fehler: '' };

// Fuer den 60-s-Refresh der Live-runs-Seite (app.js): den einmal geladenen
// Ledger verwerfen, damit der naechste Render die Datei neu holt.
export function ledgerVerwerfen() {
  if (!LEDGER.laedt) { LEDGER.daten = null; LEDGER.fehler = ''; }
}

// The ledger for this render: from the runs payload's extras (API), else
// from the module cache (static), else kick off the one fetch and return
// null — the caller renders an honest "loading" line and T.render() draws
// the section once the file is in. Outside a browser (the render harness)
// nothing is fetched.
function walletLedgerVon(T, payload) {
  const extras = payload && payload.extras;
  if (extras && extras.wallet_ledger && typeof extras.wallet_ledger === 'object') return extras.wallet_ledger;
  if (LEDGER.daten) return LEDGER.daten;
  const imBrowser = typeof window !== 'undefined' && typeof fetch === 'function';
  if (!LEDGER.laedt && !LEDGER.fehler && imBrowser) {
    LEDGER.laedt = true;
    fetch('./data/wallet_ledger.json')
      .then((res) => { if (!res.ok) throw new Error('HTTP ' + res.status); return res.json(); })
      .then((daten) => { LEDGER.daten = daten && typeof daten === 'object' ? daten : null; if (!LEDGER.daten) LEDGER.fehler = 'empty file'; })
      .catch((err) => { LEDGER.fehler = String(err && err.message ? err.message : err); })
      .then(() => { LEDGER.laedt = false; if (T && typeof T.render === 'function') T.render(); });
  }
  return null;
}

const LEDGER_TYP_FARBE = { bot: 'var(--info)', discretionary: 'var(--warn)', pilot: 'var(--accent)' };

function ledgerTypChip(typ) {
  const farbe = LEDGER_TYP_FARBE[typ] || 'var(--muted)';
  return '<span style="' + M + '; font-size:10.5px; letter-spacing:.1em; border-radius:4px; padding:2px 7px; color:' + farbe + '; border:1px solid color-mix(in srgb, ' + farbe + ' 40%, transparent); white-space:nowrap">' + esc(String(typ || '—').toUpperCase()) + '</span>';
}

// Chip for a run that placed nothing and left no wallet trace — muted, so
// the money rows stand out against the process rows in the same table.
function noFillChip() {
  return '<span style="' + M + '; font-size:10.5px; letter-spacing:.1em; border-radius:4px; padding:2px 7px; color:rgba(var(--ink),.5); border:1px solid rgba(var(--ink),.22); white-space:nowrap">NO FILLS</span>';
}

// The bet rows of a run (market, side, limit, fill, stake, log result) —
// shared by the fallback cards and the run detail inside a table row.
function laufWettenHtml(k) {
  return k.bets.map((b) =>
    '<div style="display:grid; grid-template-columns:1fr 62px 78px 78px 80px 92px; gap:10px; align-items:center; padding:9px 0; border-bottom:1px solid rgba(var(--ink),.05); ' + M + '; font-size:11.5px">'
    + '<div style="font-family:\'IBM Plex Sans\',sans-serif; font-size:12.5px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="' + esc(b.market) + '">' + esc(b.market) + '</div>'
    + '<div style="' + M + '; font-size:11.5px; color:' + (b.side === 'Yes' ? 'var(--accent)' : 'var(--info)') + '">' + b.side + '</div>'
    + '<div style="text-align:right; color:rgba(var(--ink),.55)">limit ' + b.limit + '</div>'
    + '<div style="text-align:right; color:rgba(var(--ink),.55)">fill ' + b.fill + '</div>'
    + '<div style="text-align:right">' + b.stake + '</div>'
    + '<div style="text-align:right; ' + M + '; font-size:12px; color:' + (b.result.charAt(0) === '+' ? 'var(--pos)' : b.result === 'open' ? 'rgba(var(--ink),.5)' : 'var(--neg)') + '">' + b.result + '</div></div>'
  ).join('');
}

// The full run detail inside an expanded table row: profile and episode,
// the chips (latency, decisions, depth, drop source), the bet rows, the log
// footer. The wallet figure of the event is the PNL column of the row above,
// so the footer states only the log side.
function laufDetailHtml(k) {
  const geldMit = (v) => (v == null ? '—' : (+v >= 0 ? '+$' : '-$') + Math.abs(+v).toFixed(2));
  return '<div style="margin:6px 0 2px">'
    + '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.6); margin-bottom:6px">' + esc('run ' + k.profil + (k.title ? ' · ' + k.title : '') + ' · ' + k.mode.toLowerCase() + ' · ' + k.status.toLowerCase()) + '</div>'
    + (k.chips.length
      ? '<div style="display:flex; gap:6px; flex-wrap:wrap; margin-bottom:4px">'
        + k.chips.map((c) => '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.6); background:var(--panel-hover); border:1px solid rgba(var(--ink),.09); border-radius:4px; padding:3px 8px">' + esc(c) + '</div>').join('')
        + '</div>'
      : '')
    + laufWettenHtml(k)
    + '<div style="' + M + '; font-size:10.5px; color:rgba(var(--ink),.6); margin-top:8px">' + esc('Stake $' + k.einsatzLog.toFixed(2) + ' — the wallet figure is the PNL column of this row') + '</div>'
    + (k.missed ? '<div style="' + M + '; font-size:10.5px; color:var(--warn); margin-top:5px">' + esc(k.missed) + '</div>' : '')
    + '</div>';
}

function ledgerGeld(v, vorzeichen) {
  if (v == null || isNaN(+v)) return '—';
  const abs = num(Math.abs(+v).toFixed(2));
  if (!vorzeichen) return '$' + abs;
  return (+v >= 0 ? '+$' : '-$') + abs;
}

function ledgerFarbe(v) {
  return v == null || isNaN(+v) ? 'rgba(var(--ink),.5)' : +v >= 0 ? 'var(--pos)' : 'var(--neg)';
}

// "1 sell", "6 sells" — the KPI sub-lines count things.
function ledgerZahlwort(n, einzahl, mehrzahl) {
  const z = n == null ? 0 : +n;
  return num(z) + ' ' + (z === 1 ? einzahl : mehrzahl);
}

// A ledger note as text with its https links clickable (the Curtis E3 note
// carries the pre-registration document of the sister repo).
function ledgerNotizHtml(text) {
  const roh = String(text == null ? '' : text);
  const muster = /https?:\/\/[^\s)]+/g;
  let raus = '';
  let letzte = 0;
  let m;
  while ((m = muster.exec(roh)) !== null) {
    raus += esc(roh.slice(letzte, m.index));
    raus += '<a href="' + esc(m[0]) + '" target="_blank" rel="noopener" style="color:var(--info); text-decoration:none">' + esc(m[0].replace(/^https?:\/\//, '')) + ' ↗</a>';
    letzte = m.index + m[0].length;
  }
  return raus + esc(roh.slice(letzte));
}

// One line per market inside an event's <details>: side, price, shares,
// stake, PnL as the API states it, status, and which log it belongs to.
function ledgerMarktZeile(m) {
  const status = String(m.status || '—');
  const statusFarbe = status === 'won' ? 'var(--pos)' : (status === 'lost' || status === 'worthless') ? 'var(--neg)' : 'rgba(var(--ink),.55)';
  const zuordnung = String(m.zuordnung || '');
  return '<div style="display:grid; grid-template-columns:1fr 44px 70px 70px 84px 92px 78px 110px; gap:8px; align-items:center; padding:7px 0; border-top:1px solid rgba(var(--ink),.05); ' + M + '; font-size:11px">'
    + '<div style="font-family:\'IBM Plex Sans\',sans-serif; font-size:12px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="' + esc(m.titel || '') + '">' + esc(m.titel || '—') + '</div>'
    + '<div style="color:' + (String(m.seite).toLowerCase() === 'yes' ? 'var(--accent)' : 'var(--info)') + '">' + esc(m.seite || '—') + '</div>'
    + '<div style="text-align:right; color:rgba(var(--ink),.55)">' + (m.avg_preis != null ? 'avg ' + (+m.avg_preis).toFixed(2) : '—') + '</div>'
    + '<div style="text-align:right; color:rgba(var(--ink),.55)">' + (m.shares != null ? num((+m.shares).toFixed(0)) + ' sh' : '—') + '</div>'
    + '<div style="text-align:right">' + ledgerGeld(m.einsatz_usd, false) + '</div>'
    + '<div style="text-align:right; color:' + ledgerFarbe(m.pnl_usd) + '" title="' + esc(m.pnl_art || '') + '">' + ledgerGeld(m.pnl_usd, true) + '</div>'
    + '<div style="color:' + statusFarbe + '">' + esc(status) + '</div>'
    + '<div style="color:rgba(var(--ink),.6); white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="' + esc(zuordnung + (m.run_profil ? ' · ' + m.run_profil : '')) + '">' + esc(zuordnung + (m.run_profil ? ' · ' + m.run_profil : '')) + '</div>'
    + '</div>';
}

// Die PnL-Zahl eines Events benennen. Sie summiert den abgerechneten PnL
// aufgeloester Maerkte UND den Buchgewinn noch offener Positionen (die API
// liefert dort cashPnl). "API realised PnL" war dafuer der falsche Name,
// sobald ein Markt des Events noch laeuft.
export function ledgerPnlSatz(e) {
  const offen = e && e.pnl_offen_usd != null ? +e.pnl_offen_usd : 0;
  if (!offen) return 'settled PnL ' + ledgerGeld(e ? e.pnl_usd : null, true);
  return 'PnL ' + ledgerGeld(e.pnl_usd, true) + ', of which ' + ledgerGeld(offen, true)
    + ' unrealised on open positions';
}

// The section: KPI row from aggregat, then ONE table for everything — every
// wallet event (bot rows open to the full run detail: chips, bets, latency;
// the pilot's many small events grouped into one expandable row) plus the
// runs that placed nothing and left no wallet trace. Runs whose event
// already sits in the table (bot ran, placed nothing, a human traded the
// same event by hand) are noted on that event instead of listed twice.
// Without the file: the honest line naming it.
function walletLedgerHtml(T, payload, ohneFills, karten) {
  const KOPF = '<div style="' + M + '; font-size:10.5px; letter-spacing:.14em; color:var(--info)">ALL EVENTS · RUNS AND WALLET</div>';
  const karte = 'background:var(--panel); border:1px solid rgba(var(--ink),.09); border-radius:6px';
  const ledger = walletLedgerVon(T, payload);
  if (!ledger || !ledger.aggregat || !Array.isArray(ledger.events)) {
    const satz = LEDGER.laedt
      ? 'Loading the wallet ledger (public/data/wallet_ledger.json)…'
      : 'No wallet ledger loaded — this section reads public/data/wallet_ledger.json'
        + (LEDGER.fehler ? ' (' + LEDGER.fehler + ')' : '')
        + '. scripts/wallet_ledger.py rebuilds it read-only from the public Polymarket Data API for wallet ' + LIVE_RUN_WALLET + '.';
    return '<div style="margin-top:22px">' + KOPF
      + '<div style="' + karte + '; margin-top:8px; padding:14px 18px; ' + M + '; font-size:11px; color:rgba(var(--ink),.6); line-height:1.6">' + esc(satz) + '</div></div>';
  }
  const agg = ledger.aggregat;
  const events = ledger.events.slice().sort((a, b) => String(b.von_utc || '').localeCompare(String(a.von_utc || '')));
  const stand = ledger.stand_utc ? String(ledger.stand_utc).slice(0, 16).replace('T', ' ') + ' UTC' : '—';
  const nachTyp = agg.nach_typ || {};
  const typZahl = (t) => (nachTyp[t] && nachTyp[t].events != null ? nachTyp[t].events : 0);
  const pos = agg.positionen || {};
  // Eine Textzeile statt einer zweiten KPI-Reihe: die Kacheln oben messen
  // die Bot-Laeufe, hier stand ein zweiter Kachelblock mit den Zahlen der
  // ganzen Wallet daneben — zwei Stakes, zwei Netto-Zahlen, doppelte Optik.
  // Die Wallet-Summen sind eine beschriftete Zeile ueber der Tabelle.
  const metaTeile = [
    num(agg.n_events != null ? agg.n_events : events.length) + ' events (' + typZahl('bot') + ' bot · ' + typZahl('discretionary') + ' discretionary · ' + typZahl('pilot') + ' pilot)'
  ];
  if (agg.n_trades != null) {
    metaTeile.push(num(agg.n_trades) + ' trades ('
      + [agg.n_kaeufe != null ? ledgerZahlwort(agg.n_kaeufe, 'buy', 'buys') : '',
        agg.n_verkaeufe != null ? ledgerZahlwort(agg.n_verkaeufe, 'sell', 'sells') : '',
        agg.n_einloesungen != null ? ledgerZahlwort(agg.n_einloesungen, 'redemption', 'redemptions') : ''].filter(Boolean).join(' · ') + ')');
  }
  if (agg.kaeufe_usd != null) metaTeile.push('buys ' + ledgerGeld(agg.kaeufe_usd, false));
  if (agg.netto_cashflow_usd != null) metaTeile.push('net cash flow ' + ledgerGeld(agg.netto_cashflow_usd, true) + ' (sells + redemptions − buys)');
  if (agg.positionen_gewonnen != null || agg.positionen_verloren != null) {
    metaTeile.push('positions ' + (agg.positionen_gewonnen != null ? agg.positionen_gewonnen : '—') + ' won / ' + (agg.positionen_verloren != null ? agg.positionen_verloren : '—') + ' lost'
      + (pos.worthless ? ' (' + pos.worthless + ' expired worthless)' : '') + (pos.flat ? ' · ' + pos.flat + ' flat' : '') + (pos.open ? ' · ' + pos.open + ' open' : ''));
  }
  if (agg.closed_positions_capped) metaTeile.push('closed feed capped at 50 per tail');
  const metaZeile = '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.55); margin-top:8px; line-height:1.7">Whole wallet: ' + esc(metaTeile.join(' · ')) + '</div>';

  const spalten = '92px 1fr 118px 64px 96px 96px 150px';
  // Laeufe ohne Fill: eine eigene Zeile nur, wenn kein Wallet-Event denselben
  // run_profil traegt — sonst steht der Vermerk am Event, statt dass dasselbe
  // Event zweimal in der Tabelle auftaucht.
  const referenziert = new Set();
  events.forEach((e) => {
    if (e.run_profil) referenziert.add(String(e.run_profil));
    (Array.isArray(e.maerkte) ? e.maerkte : []).forEach((m) => { if (m.run_profil) referenziert.add(String(m.run_profil)); });
  });
  const ohneFillJeProfil = {};
  (ohneFills || []).forEach((r) => { if (r.profil) ohneFillJeProfil[r.profil] = r; });
  const laeufe = (ohneFills || []).filter((r) => !r.profil || !referenziert.has(r.profil));
  const entscheidungenVon = (r) => (r && r.chips ? r.chips.filter((c) => /decisions|priced/.test(c)).join(' · ') : '');
  // Laeufe MIT Fills: ihr Detail (Chips, Wetten, Latenz) steckt im
  // aufklappbaren Bot-Event, das dieselben Trades von der Kette zeigt. Ein
  // Fill-Lauf, den kein Event referenziert, wird zur eigenen Bot-Zeile —
  // sonst verschwaende er aus der Tabelle.
  const karteJeProfil = {};
  (karten || []).forEach((k) => { if (k.profil) karteJeProfil[k.profil] = k; });
  const kartenOhneEvent = (karten || []).filter((k) => !k.profil || !referenziert.has(k.profil));

  const eventZeile = (e) => {
    const datum = String(e.von_utc || '').slice(0, 10) || '—';
    const bis = String(e.bis_utc || '').slice(0, 10);
    const zeitraum = bis && bis !== datum ? datum + ' → ' + bis : datum;
    const typ = String(e.typ || 'discretionary');
    // A mixed event ("bot + discretionary") shows the other part next to the chip.
    const mixRest = String(e.typ_mix || '').split(' + ').filter((t) => t && t !== typ).join(' + ');
    const notes = Array.isArray(e.notes) ? e.notes : [];
    const alleMaerkte = Array.isArray(e.maerkte) ? e.maerkte : [];
    const lauf = e.run_profil ? ohneFillJeProfil[String(e.run_profil)] : null;
    const karte = e.run_profil ? karteJeProfil[String(e.run_profil)] : null;
    // Mit eingebettetem Laufdetail zeigen die Ledger-Zeilen nur noch die
    // Maerkte, die NICHT aus dem Lauf stammen (von Hand gehandelt) — die
    // Bot-Maerkte stehen als Wetten mit Limit/Fill/Latenz im Laufdetail.
    const maerkte = karte ? alleMaerkte.filter((m) => String(m.zuordnung || '') !== 'bot') : alleMaerkte;
    // data-key: app.js keeps open <details> across re-renders by this key.
    return '<details data-key="ledger:' + esc(String(e.event_slug || e.titel || '')) + '" style="border-bottom:1px solid rgba(var(--ink),.06)">'
      + '<summary style="display:grid; grid-template-columns:' + spalten + '; gap:10px; align-items:center; padding:10px 16px; cursor:pointer; list-style:none">'
      + '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.55); white-space:nowrap" title="' + esc(zeitraum) + '">' + esc(datum) + '</div>'
      + '<div style="font-size:12.5px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="' + esc(e.titel || e.event_slug || '') + '">'
      + (e.url ? '<a href="' + esc(e.url) + '" target="_blank" rel="noopener" style="color:var(--text); text-decoration:none" title="' + esc((e.titel || e.event_slug || '') + ' — open the event on Polymarket') + '">' + esc(e.titel || e.event_slug || '—') + ' <span style="' + M + '; font-size:11px; color:var(--info)">↗</span></a>' : esc(e.titel || e.event_slug || '—'))
      + (e.run_profil ? ' <span style="' + M + '; font-size:11px; color:rgba(var(--ink),.6)">' + esc(e.run_profil) + '</span>' : '')
      + '</div>'
      + '<div style="display:flex; gap:4px; align-items:center; flex-wrap:wrap">' + ledgerTypChip(typ)
      + (mixRest ? '<span style="' + M + '; font-size:10.5px; color:rgba(var(--ink),.6)">+ ' + esc(mixRest) + '</span>' : '') + '</div>'
      + '<div style="text-align:right; ' + M + '; font-size:11.5px; color:rgba(var(--ink),.7)">' + num(e.n_maerkte != null ? e.n_maerkte : alleMaerkte.length) + '</div>'
      + '<div style="text-align:right; ' + M + '; font-size:11.5px">' + ledgerGeld(e.einsatz_usd, false) + '</div>'
      + '<div style="text-align:right; ' + M + '; font-size:11.5px; color:' + ledgerFarbe(e.pnl_usd != null ? e.pnl_usd : e.netto_cash_usd) + '" title="' + esc(ledgerPnlSatz(e) + ' · cash flow ' + ledgerGeld(e.netto_cash_usd, true)) + '">' + ledgerGeld(e.pnl_usd != null ? e.pnl_usd : e.netto_cash_usd, true) + '</div>'
      + '<div style="' + M + '; font-size:10.5px; color:rgba(var(--ink),.6); white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="' + esc(e.status_text || '') + '">' + esc(e.status_text || '—') + '</div>'
      + '</summary>'
      + '<div style="padding:4px 16px 12px 108px">'
      + '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.6); margin-bottom:4px">'
      + esc(zeitraum + ' · ' + ledgerZahlwort(e.n_trades, 'trade', 'trades') + ' · ' + ledgerZahlwort(e.n_einloesungen, 'redemption', 'redemptions') + ' · cash flow ' + ledgerGeld(e.netto_cash_usd, true) + (e.pnl_usd != null ? ' · ' + ledgerPnlSatz(e) : ''))
      + '</div>'
      + (lauf
        ? '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.6); margin-bottom:4px">'
          + esc('The bot ran on this event and placed nothing (' + (entscheidungenVon(lauf) || 'no decisions logged') + ') — these trades were placed by hand.')
          + '</div>'
        : '')
      + (karte ? laufDetailHtml(karte) : '')
      + (karte && maerkte.length
        ? '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.6); margin:8px 0 2px">PLACED BY HAND ON THE SAME EVENT</div>'
        : '')
      + maerkte.map(ledgerMarktZeile).join('')
      + (notes.length ? '<div style="font-size:11.5px; color:rgba(var(--ink),.55); margin-top:8px; line-height:1.5">' + notes.map((n) => ledgerNotizHtml(n)).join('<br>') + '</div>' : '')
      + '</div></details>';
  };

  // Der Pilot ist ein Block aus vielen Kleinst-Events desselben Tages: als
  // 18 fast identische Zeilen verdraengte er die Laeufe. Eine Zeile mit den
  // Summen, aufklappbar auf die einzelnen Events.
  const pilotEvents = events.filter((e) => String(e.typ || '') === 'pilot');
  const andere = events.filter((e) => String(e.typ || '') !== 'pilot');
  const pilotGruppe = (() => {
    if (!pilotEvents.length) return null;
    const summe = (f) => (pilotEvents.every((e) => e[f] == null) ? null
      : Math.round(pilotEvents.reduce((a, e) => a + (e[f] != null && !isNaN(+e[f]) ? +e[f] : 0), 0) * 100) / 100);
    const maerkteN = pilotEvents.reduce((a, e) => a + (e.n_maerkte != null ? +e.n_maerkte : (e.maerkte || []).length), 0);
    const st = { won: 0, lost: 0, worthless: 0, flat: 0, open: 0 };
    pilotEvents.forEach((e) => { const sst = e.status || {}; Object.keys(st).forEach((k) => { st[k] += +sst[k] || 0; }); });
    const statusText = [st.won ? st.won + ' won' : '', st.lost ? st.lost + ' lost' : '', st.worthless ? st.worthless + ' worthless' : '', st.flat ? st.flat + ' flat' : '', st.open ? st.open + ' open' : ''].filter(Boolean).join(' · ');
    const zeit = pilotEvents.reduce((a, e) => (String(e.von_utc || '') > a ? String(e.von_utc || '') : a), '');
    const pnl = summe('pnl_usd');
    const html = '<details data-key="ledger:pilot-group" style="border-bottom:1px solid rgba(var(--ink),.06)">'
      + '<summary style="display:grid; grid-template-columns:' + spalten + '; gap:10px; align-items:center; padding:10px 16px; cursor:pointer; list-style:none">'
      + '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.55); white-space:nowrap">' + esc(zeit.slice(0, 10) || '—') + '</div>'
      + '<div style="font-size:12.5px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis">Pre-registered pilot — ' + pilotEvents.length + ' small event' + (pilotEvents.length === 1 ? '' : 's') + ' <span style="' + M + '; font-size:11px; color:rgba(var(--ink),.6)">click for each one</span></div>'
      + '<div style="display:flex; gap:4px; align-items:center">' + ledgerTypChip('pilot') + '</div>'
      + '<div style="text-align:right; ' + M + '; font-size:11.5px; color:rgba(var(--ink),.7)">' + num(maerkteN) + '</div>'
      + '<div style="text-align:right; ' + M + '; font-size:11.5px">' + ledgerGeld(summe('einsatz_usd'), false) + '</div>'
      + '<div style="text-align:right; ' + M + '; font-size:11.5px; color:' + ledgerFarbe(pnl) + '" title="' + esc('sum of ' + ledgerPnlSatz({ pnl_usd: pnl, pnl_offen_usd: summe('pnl_offen_usd') }) + ' · sum of cash flow ' + ledgerGeld(summe('netto_cash_usd'), true)) + '">' + ledgerGeld(pnl, true) + '</div>'
      + '<div style="' + M + '; font-size:10.5px; color:rgba(var(--ink),.6); white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="' + esc(statusText) + '">' + esc(statusText || '—') + '</div>'
      + '</summary>'
      + '<div style="padding:4px 16px 12px 108px">'
      + pilotEvents.map((e) =>
        '<div style="display:grid; grid-template-columns:76px 1fr 96px 96px 130px; gap:8px; align-items:center; padding:7px 0; border-top:1px solid rgba(var(--ink),.05); ' + M + '; font-size:11px">'
        + '<div style="color:rgba(var(--ink),.6); white-space:nowrap">' + esc(String(e.von_utc || '').slice(0, 10) || '—') + '</div>'
        + '<div style="font-family:\'IBM Plex Sans\',sans-serif; font-size:12px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="' + esc(e.titel || e.event_slug || '') + '">'
        + (e.url ? '<a href="' + esc(e.url) + '" target="_blank" rel="noopener" style="color:var(--text); text-decoration:none">' + esc(e.titel || e.event_slug || '—') + ' <span style="' + M + '; font-size:11px; color:var(--info)">↗</span></a>' : esc(e.titel || e.event_slug || '—'))
        + '</div>'
        + '<div style="text-align:right">' + ledgerGeld(e.einsatz_usd, false) + '</div>'
        + '<div style="text-align:right; color:' + ledgerFarbe(e.pnl_usd != null ? e.pnl_usd : e.netto_cash_usd) + '">' + ledgerGeld(e.pnl_usd != null ? e.pnl_usd : e.netto_cash_usd, true) + '</div>'
        + '<div style="color:rgba(var(--ink),.55); white-space:nowrap; overflow:hidden; text-overflow:ellipsis">' + esc(e.status_text || '—') + '</div>'
        + '</div>').join('')
      + '</div></details>';
    return { zeit, html };
  })();

  // Eine Zeile je Lauf ohne Fill und ohne Wallet-Event: das Prozessprotokoll
  // neben den Geldzeilen, damit alles unterhalb der Karten in einer Tabelle
  // steht.
  const laufZeile = (r) => '<div style="display:grid; grid-template-columns:' + spalten + '; gap:10px; align-items:center; padding:10px 16px; border-bottom:1px solid rgba(var(--ink),.06)">'
    + '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.6); white-space:nowrap">' + esc(String(r.zeit || '').slice(0, 10) || '—') + '</div>'
    + '<div style="font-size:12.5px; color:rgba(var(--ink),.7); white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="' + esc(r.title) + '">'
    + (r.url ? '<a href="' + esc(r.url) + '" target="_blank" rel="noopener" style="color:rgba(var(--ink),.7); text-decoration:none">' + esc(r.title) + ' <span style="' + M + '; font-size:11px; color:var(--info)">↗</span></a>' : esc(r.title))
    + ' <span style="' + M + '; font-size:11px; color:rgba(var(--ink),.55)">' + esc(r.profil) + '</span></div>'
    + '<div style="display:flex; gap:4px; align-items:center">' + noFillChip() + '</div>'
    + '<div style="text-align:right; ' + M + '; font-size:11.5px; color:rgba(var(--ink),.55)">—</div>'
    + '<div style="text-align:right; ' + M + '; font-size:11.5px; color:rgba(var(--ink),.55)">—</div>'
    + '<div style="text-align:right; ' + M + '; font-size:11.5px; color:rgba(var(--ink),.55)">—</div>'
    + '<div style="' + M + '; font-size:10.5px; color:rgba(var(--ink),.6); white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="' + esc(entscheidungenVon(r)) + '">' + esc((entscheidungenVon(r) ? entscheidungenVon(r) + ' · ' : '') + 'placed nothing') + '</div>'
    + '</div>';

  // Ein Fill-Lauf ohne Ledger-Event: eigene aufklappbare Bot-Zeile, Zahlen
  // aus dem Log und so beschriftet.
  const karteZeile = (k) => '<details data-key="ledger:run:' + esc(k.profil) + '" style="border-bottom:1px solid rgba(var(--ink),.06)">'
    + '<summary style="display:grid; grid-template-columns:' + spalten + '; gap:10px; align-items:center; padding:10px 16px; cursor:pointer; list-style:none">'
    + '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.55); white-space:nowrap">' + esc(String(k.zeit || '').slice(0, 10) || '—') + '</div>'
    + '<div style="font-size:12.5px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="' + esc(k.title) + '">'
    + (k.url ? '<a href="' + esc(k.url) + '" target="_blank" rel="noopener" style="color:var(--text); text-decoration:none">' + esc(k.title) + ' <span style="' + M + '; font-size:11px; color:var(--info)">↗</span></a>' : esc(k.title))
    + ' <span style="' + M + '; font-size:11px; color:rgba(var(--ink),.6)">' + esc(k.profil) + '</span></div>'
    + '<div style="display:flex; gap:4px; align-items:center">' + ledgerTypChip('bot') + '</div>'
    + '<div style="text-align:right; ' + M + '; font-size:11.5px; color:rgba(var(--ink),.7)">' + num(k.bets.length) + '</div>'
    + '<div style="text-align:right; ' + M + '; font-size:11.5px" title="from the run log — not yet in the wallet statement">' + ledgerGeld(k.einsatzLog, false) + '</div>'
    + '<div style="text-align:right; ' + M + '; font-size:11.5px; color:' + ledgerFarbe(k.pnlLog) + '" title="from the run log — not yet in the wallet statement">' + ledgerGeld(k.pnlLog, true) + '</div>'
    + '<div style="' + M + '; font-size:10.5px; color:rgba(var(--ink),.6); white-space:nowrap">' + esc(k.status.toLowerCase() + ' · from the run log') + '</div>'
    + '</summary>'
    + '<div style="padding:4px 16px 12px 108px">' + laufDetailHtml(k) + '</div></details>';

  const eintraege = andere.map((e) => ({ zeit: String(e.von_utc || ''), html: eventZeile(e) }))
    .concat(pilotGruppe ? [pilotGruppe] : [])
    .concat(laeufe.map((r) => ({ zeit: String(r.zeit || ''), html: laufZeile(r) })))
    .concat(kartenOhneEvent.map((k) => ({ zeit: String(k.zeit || ''), html: karteZeile(k) })));
  eintraege.sort((a, b) => b.zeit.localeCompare(a.zeit));
  const zeilen = eintraege.map((z) => z.html).join('');

  const kopfzeile = events.length + ' WALLET EVENTS'
    + (pilotEvents.length > 1 ? ' (' + pilotEvents.length + ' PILOT IN ONE ROW)' : '')
    + (laeufe.length ? ' + ' + laeufe.length + ' RUN' + (laeufe.length === 1 ? '' : 'S') + ' WITHOUT A TRADE' : '')
    + (kartenOhneEvent.length ? ' + ' + kartenOhneEvent.length + ' RUN' + (kartenOhneEvent.length === 1 ? '' : 'S') + ' NOT IN THE LEDGER' : '')
    + ' · NEWEST FIRST';
  const tabelle = '<div style="border:1px solid rgba(var(--ink),.09); border-radius:6px; margin-top:12px; overflow:hidden">'
    + '<div style="padding:10px 16px; background:var(--panel); border-bottom:1px solid rgba(var(--ink),.09); ' + M + '; font-size:11px; letter-spacing:.12em; color:rgba(var(--ink),.5)">'
    + kopfzeile + ' <span style="color:rgba(var(--ink),.55); letter-spacing:0">· click a row for its markets — bot rows open to the full run detail</span></div>'
    + '<div style="display:grid; grid-template-columns:' + spalten + '; gap:10px; padding:8px 16px; border-bottom:1px solid rgba(var(--ink),.09); ' + M + '; font-size:10.5px; letter-spacing:.12em; color:rgba(var(--ink),.6)">'
    + '<div>DATE</div><div>EVENT</div><div>TYPE</div><div style="text-align:right">MARKETS</div><div style="text-align:right">STAKE</div><div style="text-align:right">PNL</div><div>STATUS</div></div>'
    + (eintraege.length ? zeilen : leerZeile('The ledger holds no events — wallet_ledger.json lists none for this wallet.'))
    + '</div>';

  const legende = '<div style="font-size:11.5px; color:rgba(var(--ink),.5); margin-top:10px; line-height:1.6">'
    + ledgerTypChip('bot') + ' market and side appear in a runs.json run log — open the row for the full run detail (latency, decisions, every bet) · '
    + ledgerTypChip('discretionary') + ' placed by hand, in no run log · '
    + ledgerTypChip('pilot') + ' one of the pre-registered pilot trades of 2026-07-22 (rules frozen 2026-07-18)'
    + (laeufe.length ? ' · ' + noFillChip() + ' the bot ran and placed nothing — no wallet trace; listed so every run sits in this one table' : '') + '. '
    + 'PnL is the API\'s realised figure per market (unrealised for positions not yet redeemed); the cash flow of an event can differ. Deposits are not in the Data API.'
    + '</div>';

  // Der lange Herkunftstext der Tabelle plus die Race-Chip-Erklaerung
  // zugeklappt: wer wissen will, wie die Tabelle gebaut ist, klappt auf —
  // die Seite selbst bleibt eine Kachelreihe und eine Tabelle.
  const erklaerung = '<details data-key="ledger-was" style="' + karte + '; margin-top:10px; padding:0 16px">'
    + '<summary style="cursor:pointer; padding:11px 0; list-style:none; ' + M + '; font-size:11px; letter-spacing:.14em; color:rgba(var(--ink),.5)">WHAT THIS TABLE IS &amp; HOW TO READ THE RUN DETAIL ▸</summary>'
    + '<div style="padding-bottom:12px; font-size:12.5px; color:rgba(var(--ink),.6); line-height:1.6">'
    + esc(ledger.hinweis || '')
    + '<div style="margin-top:8px">Race chips in an opened bot row compare each fill against the public taker tape of that market: how many other trades hit between the drop and our fill, and how long until the next trader after us. The anchor is the bot\'s logged fill time — chain timestamps can differ by a few seconds.</div>'
    + '</div></details>';

  return '<div style="margin-top:22px">'
    + '<div style="display:flex; align-items:flex-start; justify-content:space-between; gap:16px; flex-wrap:wrap">'
    + '<div style="max-width:860px">' + KOPF + metaZeile
    + '<div style="' + M + '; font-size:10.5px; color:rgba(var(--ink),.6); margin-top:5px">Wallet ' + walletLinkHtml(ledger.wallet)
    + (agg.erste_aktivitaet_utc ? ' · first activity ' + esc(String(agg.erste_aktivitaet_utc).slice(0, 10)) : '')
    + (agg.letzte_aktivitaet_utc ? ' · last activity ' + esc(String(agg.letzte_aktivitaet_utc).slice(0, 10)) : '')
    + ' · <a href="./data/wallet_ledger.json" download="wallet_ledger.json" style="color:var(--info); text-decoration:none">download the ledger</a></div>'
    + '</div>'
    + '<div style="display:flex; gap:8px; align-items:center">'
    + '<div style="' + M + '; font-size:10.5px; letter-spacing:.1em; border-radius:4px; padding:3px 8px; color:var(--on-accent); background:var(--accent)">' + esc(String(ledger.kennzeichnung || 'wallet/public-api').toUpperCase()) + '</div>'
    + '<div style="' + M + '; font-size:10.5px; color:rgba(var(--ink),.6); border:1px solid rgba(var(--ink),.14); border-radius:4px; padding:5px 10px; white-space:nowrap">as of ' + esc(stand) + '</div>'
    + '</div></div>'
    + erklaerung
    + tabelle + legende
    + '</div>';
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
        farbe: 'var(--info)',
        punkte
      }));
    });
  });
  if (!kurven.length) {
    return '<div style="background:var(--panel); border:1px solid rgba(var(--ink),.09); border-radius:6px; margin-top:14px; padding:14px 18px; ' + M + '; font-size:11px; color:rgba(var(--ink),.6)">'
      + 'No repricing paths in this payload — runs.json carries them per run under repricing[].punkte.</div>';
  }
  return '<div style="margin-top:14px">'
    + '<div style="' + M + '; font-size:10.5px; letter-spacing:.14em; color:var(--info); margin-bottom:4px">REPRICING AFTER THE DROP · ' + kurven.length + (kurven.length === 1 ? ' BET' : ' BETS') + '</div>'
    + '<div style="font-size:12px; color:rgba(var(--ink),.5); margin-bottom:10px; line-height:1.5">Price of the traded side against seconds after the drop, from the public tape; the caption names when our fill landed and when the market had priced the outcome in.</div>'
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
      { name: 'simulated PnL (USD)', farbe: 'var(--accent)', werte: decay.map((t) => (typeof t.sim_pnl_usd === 'number' ? t.sim_pnl_usd : null)) }
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
    + '<div ' + T.act(down) + ' class="hv-bd35w" style="width:28px; height:32px; flex:none; border:1px solid rgba(var(--ink),.16); border-radius:4px; display:flex; align-items:center; justify-content:center; ' + M + '; font-size:14px; color:rgba(var(--ink),.7); cursor:pointer">−</div>'
    + '<div style="flex:1; background:var(--panel); border:1px solid rgba(var(--ink),.16); border-radius:4px; padding:7px 8px; ' + M + '; font-size:12.5px; text-align:center">' + esc(valueLabel) + '</div>'
    + '<div ' + T.act(up) + ' class="hv-bd35w" style="width:28px; height:32px; flex:none; border:1px solid rgba(var(--ink),.16); border-radius:4px; display:flex; align-items:center; justify-content:center; ' + M + '; font-size:14px; color:rgba(var(--ink),.7); cursor:pointer">+</div></div></div>';

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
    + '<div style="padding:20px 24px 16px; border-bottom:1px solid rgba(var(--ink),.09)">'
    + '<div style="' + M + '; font-size:11px; letter-spacing:.18em; color:var(--accent)">SETTINGS</div>'
    + '<h1 style="font-size:21px; line-height:1.25; margin:6px 0 0; font-weight:600; letter-spacing:-0.01em">How much data, and where it goes</h1></div>'
    + '<div style="padding:20px 24px 0; max-width:1000px">'
    + '<div style="' + M + '; font-size:10.5px; letter-spacing:.14em; color:var(--accent); margin-bottom:12px">HOW MUCH DATA TO PULL</div>'
    + '<div style="display:grid; grid-template-columns:repeat(3,1fr); gap:16px">'
    + stepRow('MARKETS PER PULL', num(s.setMarketSample), () => T.setState({ setMarketSample: Math.max(50, s.setMarketSample - 50) }), () => T.setState({ setMarketSample: Math.min(2000, s.setMarketSample + 50) }))
    + stepRow('TRADES PER PULL', num(s.setTradeSample), () => T.setState({ setTradeSample: Math.max(50, s.setTradeSample - 50) }), () => T.setState({ setTradeSample: Math.min(2000, s.setTradeSample + 50) }))
    + stepRow('WHALE THRESHOLD', '$' + num(s.setWhale), () => T.setState({ setWhale: Math.max(500, s.setWhale - 500) }), () => T.setState({ setWhale: s.setWhale + 500 }))
    + '</div>'
    + '<div style="font-size:11.5px; color:rgba(var(--ink),.6); margin-top:9px; line-height:1.5">Bigger samples mean slower pages. The whale threshold decides what counts as a large print everywhere in the terminal.</div>'
    + '<div style="' + M + '; font-size:10.5px; letter-spacing:.14em; color:var(--accent); margin:22px 0 12px">BACKTESTER DEFAULTS</div>'
    + '<div style="display:grid; grid-template-columns:repeat(3,1fr); gap:16px">'
    + stepRow('BANKROLL', '$' + num(s.setBankroll), () => T.setState({ setBankroll: Math.max(100, s.setBankroll - 500) }), () => T.setState({ setBankroll: s.setBankroll + 500 }))
    + stepRow('FEE (BPS)', s.setFee + ' bps', () => T.setState({ setFee: Math.max(0, s.setFee - 5) }), () => T.setState({ setFee: s.setFee + 5 }))
    + stepRow('SLIPPAGE (BPS)', s.setSlip + ' bps', () => T.setState({ setSlip: Math.max(0, s.setSlip - 5) }), () => T.setState({ setSlip: s.setSlip + 5 }))
    + '</div>'
    + '<div style="' + M + '; font-size:10.5px; letter-spacing:.14em; color:var(--accent); margin:22px 0 12px">SWITCHES</div>'
    + '</div>'
    + '<div style="padding:20px 24px; display:grid; grid-template-columns:repeat(2,1fr); gap:16px; max-width:1000px">'
    + settingRows.map((o) => {
      const on = !!s.settingsOn[o.key];
      return '<div style="background:var(--panel); border:1px solid rgba(var(--ink),.09); border-radius:6px; padding:16px 18px">'
        + '<div style="display:flex; align-items:center; justify-content:space-between; gap:14px">'
        + '<div><div style="font-size:14.5px; font-weight:600">' + o.name + '</div>'
        + '<div style="font-size:12.5px; color:rgba(var(--ink),.55); margin-top:6px; line-height:1.45">' + o.desc + '</div></div>'
        + '<div ' + T.act(() => T.setState({ settingsOn: Object.assign({}, s.settingsOn, { [o.key]: !on }) })) + ' style="width:38px; height:21px; flex:none; border-radius:6px; padding:2px; display:flex; cursor:pointer; background:' + (on ? 'var(--accent)' : 'rgba(var(--ink),.14)') + '; justify-content:' + (on ? 'flex-end' : 'flex-start') + '">'
        + '<div style="width:17px; height:17px; border-radius:50%; background:' + (on ? 'var(--on-accent)' : 'rgba(var(--ink),.55)') + '"></div></div></div>'
        + '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.6); margin-top:12px">' + o.value + '</div></div>';
    }).join('')
    + '</div>'
    + '<div style="padding:0 24px 30px; ' + M + '; font-size:10.5px; color:rgba(var(--ink),.55); line-height:1.7; max-width:760px">Research tool only — no investment advice, no order placement, no venue affiliation. Public Polymarket and Kalshi data, provided as-is. Settings are locked to allowlisted accounts on a public deployment.</div>'
    + '</div>';
}

// ---------------------------------------------------------------- per-study extras (dispatched by slug)
// Diagramme und Zusatzbloecke der Studien, die ueber den generischen Pfad
// rendern (Kacheln, Tabelle, Knoepfe). Was hier steht, kommt zwischen die
// Kacheln und die Tabelle. Jede Funktion gibt '' zurueck, wenn die Nutzlast
// nichts hergibt — und sagt dann in einer Zeile, welches Feld fehlt.
function studienExtrasHtml(slug, payload, ledger) {
  if (!payload) return '';
  if (slug === 'mentions-latency') return mentionsExtrasHtml(payload);
  if (slug === 'pilot') return pilotExtrasHtml(payload, ledger);
  if (slug === 'pipeline-forward') return pipelineHeadlineHtml(payload) + pipelineRegelnHtml(payload);
  return '';
}

const KARTE = 'background:var(--panel); border:1px solid rgba(var(--ink),.09); border-radius:6px';

function hinweisKarte(text) {
  return '<div style="' + KARTE + '; margin-top:14px; padding:14px 18px; ' + M + '; font-size:11px; color:rgba(var(--ink),.6); line-height:1.6">' + esc(text) + '</div>';
}

// Dauer in menschlicher Einheit. Unter einer Minute sagt die Anzeige
// "< 1 min" statt Sekunden: das Preisraster ist fidelity=1 (ein Punkt je
// Minute), Sekundenwerte waeren Praezision, die die Messung nicht hat.
// Exakter Sekundenabstand Drop -> erster abweichender Rasterpunkt; das
// Payload traegt ihn als sekunden_bis_erste_reaktion, alte Nutzlasten
// fallen auf Minuten*60 zurueck.
function reaktionsSekunden(f) {
  if (f && f.sekunden_bis_erste_reaktion != null && !isNaN(+f.sekunden_bis_erste_reaktion)) return +f.sekunden_bis_erste_reaktion;
  if (f && f.minuten_bis_erste_reaktion != null && !isNaN(+f.minuten_bis_erste_reaktion)) return Math.round(+f.minuten_bis_erste_reaktion * 60);
  return null;
}

function dauerText(minuten) {
  const m = +minuten;
  if (minuten == null || isNaN(m)) return '—';
  if (m < 1) return '< 1 min';
  if (m < 10) return (Math.round(m * 10) / 10) + ' min';
  if (m < 90) return Math.round(m) + ' min';
  if (m < 2880) return (Math.round(m / 6) / 10) + ' h';
  return (Math.round(m / 144) / 10) + ' d';
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
  // Ein Diagramm, EINE Zeile je Ereignis: Reaktion und Konvergenz sind zwei
  // Messungen desselben Ereignisses, also eine Spanne auf einer Achse —
  // Punkt = erste Bewegung, Linienende = ausgepreist, die Spanne dazwischen
  // ist das handelbare Fenster. Zwei Zeilen je Ereignis (24 Balken) machten
  // die Karte doppelt so hoch wie noetig und lasen sich wie zwei Befunde.
  // Nur Faelle, die BEIDE Zahlen tragen — eine fehlende Konvergenz als 0 zu
  // zeichnen laese sie wie sofortiges Einpreisen aussehen. Fehlt einer, faellt
  // der Fall aus diesem Diagramm und das n im Titel sagt es.
  const vollstaendig = (f) => f && f.minuten_bis_erste_reaktion != null && !isNaN(+f.minuten_bis_erste_reaktion)
    && f.minuten_bis_konvergenz != null && !isNaN(+f.minuten_bis_konvergenz);
  const beide = faelle.filter(vollstaendig)
    .map((f) => ({
      label: String(f.event || '—'),
      von: +f.minuten_bis_erste_reaktion,
      bis: +f.minuten_bis_konvergenz,
      sek: reaktionsSekunden(f),
      outcome: String(f.korrekt_aufgeloestes_outcome || '—'),
      weg: f.erste_reaktion_zum_outcome === false,
      fenster: f.stunden_im_handelbaren_fenster
    }))
    .sort((a, b) => a.bis - b.bis);
  const medReaktion = beide.length ? medianVon(beide.map((p) => p.von)) : null;
  // Log-Zeitachse statt linear: die Spannen reichen von Minuten bis Tage —
  // linear war jede Zeile unter einer Stunde ein unlesbarer Strich am Rand.
  // Alles unter dem 1-Minuten-Preisraster sitzt gesammelt bei "<=1 min";
  // eine Farbe fuer alle Zeilen, das Outcome steht als Text an der Zeile
  // (das Gruen/Blau-Paar der Tokens fiel im Palettencheck durch).
  const paar = (() => {
    if (!beide.length) return '';
    const LX = 196, PL = 208, PR = 544, ZH = 22, TOP = 16;
    const hi = Math.max(...beide.map((p) => p.bis)) * 1.2;
    const lmax = Math.max(Math.log10(hi), 0.1);
    const x = (v) => (v <= 1 ? PL : PL + (Math.log10(v) / lmax) * (PR - PL));
    const hoehe = TOP + beide.length * ZH + 26;
    let svg = '';
    [[1, '≤1 min'], [10, '10 min'], [60, '1 h'], [600, '10 h'], [4320, '3 d']].forEach(([w, t]) => {
      if (w > hi) return;
      const tx = x(w);
      svg += '<line x1="' + tx + '" y1="' + (TOP - 6) + '" x2="' + tx + '" y2="' + (hoehe - 20) + '" style="stroke:rgba(var(--ink),' + (w === 1 ? '.18' : '.08') + ')" stroke-width="1" />'
        + '<text x="' + tx + '" y="' + (hoehe - 6) + '" style="fill:rgba(var(--ink),.55)" font-size="10.5" font-family="JetBrains Mono, monospace" text-anchor="middle">' + t + '</text>';
    });
    if (medReaktion != null && medReaktion > 1) {
      svg += '<line x1="' + x(medReaktion) + '" y1="' + (TOP - 6) + '" x2="' + x(medReaktion) + '" y2="' + (hoehe - 20) + '" style="stroke:rgba(var(--ink),.35)" stroke-width="1" stroke-dasharray="4 4" />';
    }
    let y = TOP + 10;
    beide.forEach((p) => {
      const xa = x(p.von), xb = x(p.bis);
      svg += '<g><title>' + esc(p.label + ' — first reaction ' + (p.sek != null ? fmtZahl(p.sek) + ' s' : fmtZahl(p.von) + ' min')
        + (p.weg ? ' (moved away from the outcome)' : '') + ', fully priced in ' + fmtZahl(p.bis) + ' min'
        + (p.fenster != null ? ', tradeable window ' + fmtZahl(p.fenster) + ' h' : '') + ', resolved ' + p.outcome) + '</title>'
        + '<text x="' + LX + '" y="' + (y + 4) + '" style="fill:rgba(var(--ink),.72)" font-size="11" font-family="JetBrains Mono, monospace" text-anchor="end">' + esc(p.label) + '</text>'
        + '<line x1="' + xa + '" y1="' + y + '" x2="' + xb + '" y2="' + y + '" style="stroke:var(--info)" stroke-width="2" stroke-opacity=".5" />'
        + '<circle cx="' + xa + '" cy="' + y + '" r="4" style="fill:var(--info)" />'
        + '<line x1="' + xb + '" y1="' + (y - 5) + '" x2="' + xb + '" y2="' + (y + 5) + '" style="stroke:var(--info)" stroke-width="2" />'
        + '<text x="' + (PR + 8) + '" y="' + (y + 4) + '" style="fill:rgba(var(--ink),.75)" font-size="11" font-family="JetBrains Mono, monospace">' + esc(dauerText(p.bis) + ' · ' + p.outcome) + '</text></g>';
      y += ZH;
    });
    const medSek = medianVon(beide.map((p) => p.sek).filter((s) => s != null && !isNaN(+s)));
    const medText = medSek != null
      ? ' · median first reaction ' + fmtZahl(medSek) + ' s' + (medReaktion != null && medReaktion > 1 ? ' (dashed line)' : '')
      : (medReaktion == null ? '' : ' · median first reaction ' + fmtZahl(medReaktion) + ' min' + (medReaktion > 1 ? ' (dashed line)' : ''));
    return '<div style="' + KARTE + '; padding:14px 16px 10px">'
      + '<div style="' + M + '; font-size:11px; letter-spacing:.13em; color:rgba(var(--ink),.5); margin-bottom:4px">'
      + 'FIRST REACTION → FULLY PRICED IN · n ' + beide.length
      + ' · log time axis after broadcast start · dot = first &gt; 1-point move (values under the 1-minute grid sit at ≤1 min) · line end = durably priced on the winning side' + medText + '</div>'
      + '<svg width="100%" viewBox="0 0 640 ' + hoehe + '" role="img" aria-label="First reaction and convergence per event">' + svg + '</svg></div>';
  })();
  const reaktion = paar || balken('minuten_bis_erste_reaktion', 'MINUTES TO FIRST REACTION (> 1-POINT MOVE) PER EVENT');
  // Der Klartext VOR dem Bild: was die beiden Uhren messen und wo sie
  // starten — ohne das las sich "first reaction 86.7 min" als Markt, der
  // eine gefallene Aussage verschlief.
  const lead = '<div style="margin-top:14px; font-size:12.5px; color:rgba(var(--ink),.7); line-height:1.6; max-width:860px">'
    + 'Twelve broadcasts, each with a market on whether something would be said. Both clocks start when the broadcast starts — not when the words are said. '
    + 'The dot is the first time the price moved at all; the end of the line is when it had durably settled on the side that later won. The span between them is the tradeable window.</div>';
  const charts = reaktion
    ? lead + '<div style="margin-top:10px">' + reaktion + '</div>'
    : hinweisKarte('No reaction or convergence minutes in this payload — mentions_latenz.json carries them per event under faelle[].minuten_bis_erste_reaktion and minuten_bis_konvergenz.');
  // YES- und NO-Faelle messen verschiedene Mechanismen (Reaktion auf eine
  // gefallene Aussage vs. Zerfall der Resthoffnung ohne Ereignis) — die
  // Mediane kommen getrennt aus der Datei, sobald sie aggregate traegt.
  const agg = payload.aggregate && typeof payload.aggregate === 'object' ? payload.aggregate : null;
  const jeOutcome = agg && agg.je_outcome && typeof agg.je_outcome === 'object' ? agg.je_outcome : null;
  const splitKachel = (name, o, deutung) => (o && o.n != null
    ? '<div style="' + KARTE + '; padding:14px 16px">'
      + '<div style="' + M + '; font-size:11px; letter-spacing:.14em; color:var(--info)">RESOLVED ' + esc(name) + ' · n ' + num(o.n) + '</div>'
      + '<div style="' + M + '; font-size:12.5px; color:rgba(var(--ink),.85); margin-top:8px; line-height:1.8">'
      + 'median first reaction ' + (o.median_sekunden_bis_erste_reaktion != null ? fmtZahl(o.median_sekunden_bis_erste_reaktion) + ' s' : esc(dauerText(o.median_minuten_bis_erste_reaktion))) + '<br>'
      + 'median convergence ' + esc(dauerText(o.median_minuten_bis_konvergenz)) + '<br>'
      + 'median tradeable window ' + fmtZahl(o.median_stunden_im_handelbaren_fenster) + ' h</div>'
      + '<div style="font-size:11.5px; color:rgba(var(--ink),.6); margin-top:8px; line-height:1.5">' + esc(deutung) + '</div></div>'
    : '');
  const split = jeOutcome
    ? '<div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(280px, 1fr)); gap:12px; margin-top:12px">'
      + splitKachel('YES', jeOutcome.YES, 'The utterance did happen — but t0 is the broadcast start, not the moment the words were said, so even here the first tick is not necessarily the market hearing them.')
      + splitKachel('NO', jeOutcome.NO, 'No triggering event: the first move is drift, and certainty only comes once the broadcast is (almost) over.')
      + '</div>'
    : '';
  const methode = '<div style="' + KARTE + '; margin-top:12px; padding:14px 18px">'
    + '<div style="' + M + '; font-size:11px; letter-spacing:.14em; color:var(--info)">HOW TO READ IT</div>'
    + '<div style="font-size:12.5px; color:rgba(var(--ink),.65); margin-top:8px; line-height:1.6; max-width:860px">'
    + 'First reaction is the first minute the price stands more than 1 point away from its pre-drop baseline (the median of the 60 minutes before the drop) — in either direction, so it is a price move, not proof the market heard anything; rows marked (away) moved away from the outcome that later resolved. It is measured from the start of the transmission, not from the moment of the resolving statement: a first reaction of several minutes on a NO market is drift while nothing was said, not a market slow to react to a met condition. Convergence is the time until the price durably stayed past 0.9 (YES) or below 0.1 (NO), as measured by the daily run'
    + (payload.hinweis ? ' — the published note reads: "' + esc(payload.hinweis) + '"' : '')
    + '. The RESOLVED column shows the outcome the market settled to. The tradeable window is the hours after the drop in which the price stayed strictly between 0.1 and 0.9 — measured on the price series itself, so it can start before the first 1-point reaction and is not simply convergence minus reaction. The chart uses a log time axis so minutes and days fit on one line. The FIRST REACTION column gives the exact second gap between the curated drop timestamp and the first minute-grid price point that deviated — read it with its grain: the series has one point per minute and several drop times are only hour-precise, so "7 s" means the first grid point after t0 already stood off baseline, not that the first trade came 7 seconds in.'
    + '</div></div>';
  const ausschlussHtml = ausschluesse.length
    ? '<div style="border:1px solid rgba(var(--ink),.09); border-radius:6px; margin-top:12px; overflow:hidden">'
      + '<div style="padding:10px 16px; background:var(--panel); border-bottom:1px solid rgba(var(--ink),.09); ' + M + '; font-size:11px; letter-spacing:.12em; color:var(--warn)">EXCLUDED EVENTS · ' + ausschluesse.length + ' <span style="color:rgba(var(--ink),.55); letter-spacing:0">· listed, not counted in the medians</span></div>'
      + ausschluesse.map((a) =>
        '<div style="display:grid; grid-template-columns:1fr auto; gap:12px; padding:9px 16px; border-bottom:1px solid rgba(var(--ink),.05)">'
        + '<div style="' + M + '; font-size:12px; color:rgba(var(--ink),.75)">' + esc(String((a && a.event) || '—')) + '</div>'
        + '<div style="' + M + '; font-size:11px; color:var(--warn)">' + esc(ausschlussText(a && a.status)) + '</div></div>').join('')
      + '</div>'
    : hinweisKarte('No exclusions listed in mentions_latenz.json (ausschluesse is empty).');
  // Methode, Datengrundlage und Grenzen, zugeklappt — direkt aus der Datei,
  // damit die Seite nichts behauptet, was die Nutzlast nicht traegt.
  const quelle = payload.quelle && typeof payload.quelle === 'object' ? payload.quelle : null;
  const quelleAbsatz = (titel, text) => (text
    ? '<div style="margin-top:10px"><div style="' + M + '; font-size:10.5px; letter-spacing:.13em; color:rgba(var(--ink),.55)">' + titel + '</div>'
      + '<div style="font-size:12.5px; color:rgba(var(--ink),.7); margin-top:4px; line-height:1.6">' + esc(text) + '</div></div>'
    : '');
  const quelleHtml = quelle
    ? '<details style="margin-top:12px; ' + KARTE + '; padding:0 18px">'
      + '<summary style="cursor:pointer; padding:12px 0; ' + M + '; font-size:10.5px; letter-spacing:.14em; color:rgba(var(--ink),.55); list-style:none">METHOD, SAMPLE &amp; WHAT IT CANNOT SHOW ▸</summary>'
      + '<div style="padding-bottom:14px">'
      + quelleAbsatz('WHAT WAS MEASURED', quelle.methode)
      + quelleAbsatz('DATA BASIS', quelle.datengrundlage)
      + (Array.isArray(quelle.einschraenkungen) && quelle.einschraenkungen.length
        ? '<div style="margin-top:10px"><div style="' + M + '; font-size:10.5px; letter-spacing:.13em; color:rgba(var(--ink),.55)">WHAT IT CANNOT SHOW</div>'
          + '<ul style="margin:4px 0 0 18px; padding:0; font-size:12.5px; color:rgba(var(--ink),.7); line-height:1.6">'
          + quelle.einschraenkungen.map((e) => '<li>' + esc(String(e)) + '</li>').join('') + '</ul></div>'
        : '')
      + '</div></details>'
    : '';
  return charts + split + methode + ausschlussHtml + quelleHtml;
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

function pilotExtrasHtml(payload, ledger) {
  const trades = Array.isArray(payload.trades) ? payload.trades : [];
  const teile = [];

  // Der Abschluss zuerst, aus dem Wallet-Ledger: die trades.csv kennt keine
  // Aufloesungen, und die Seite behauptete "still open", als das Wallet
  // laengst abgerechnet hatte.
  const wl = pilotLedgerStand(ledger);
  const abgeschlossen = wl && wl.settled;
  if (abgeschlossen) {
    teile.push('<div style="' + KARTE + '; margin-top:14px; padding:16px 18px">'
      + '<div style="' + M + '; font-size:11px; letter-spacing:.14em; color:var(--accent)">HOW IT ENDED · WALLET</div>'
      + '<div style="font-size:13.5px; color:var(--text); margin-top:8px; line-height:1.6; max-width:760px">'
      + 'All ' + wl.pos.n + ' positions have resolved: ' + esc(pilotWlText(wl.pos)) + ' (wallet, worthless counts as lost).'
      + (wl.netto != null
        ? ' Net cash of the pilot: ' + (wl.netto >= 0 ? '+$' : '-$') + Math.abs(wl.netto).toFixed(2)
          + (wl.einsatz != null ? ' on $' + wl.einsatz.toFixed(0) + ' deployed' : '')
          + ' — sells + redemptions minus buys, from the public wallet ledger' + (wl.stand ? ' as of ' + wl.stand : '') + '.'
        : '')
      + '</div></div>');
  }

  // The promised chart has no series: say so instead of drawing one.
  const offen = trades.filter((t) => !t.exit_zeit_utc && !t.exit_preis).length;
  teile.push(hinweisKarte('PILOT EQUITY VS RULE ADHERENCE: no series — pilot.json carries no equity curve'
    + (abgeschlossen
      ? '; every position exited through resolution, the wallet outcome is in the card above'
      : (trades.length ? ' and ' + offen + ' of ' + trades.length + ' positions exit only through resolution, so no equity path exists yet' : ''))
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
        + '<div style="' + M + '; font-size:11px; letter-spacing:.14em; color:var(--info)">READ-ONLY WATCHER · WHAT THE SCAN THREW OUT</div>'
        + '<div style="font-size:12.5px; color:rgba(var(--ink),.6); margin-top:8px; line-height:1.6; max-width:860px">'
        + (stat && stat.maerkte != null ? num(stat.maerkte) + ' markets scanned' : 'markets scanned: not in the file')
        + (signale ? ' · ' + num(summe) + ' rule matches (' + Object.entries(signale).map(([k, v]) => num(v) + ' ' + watcherText(k)).join(', ') + ')' : '')
        + '. Signals are rule matches, not recommendations; each rejection reason is a pre-registered gate.</div>'
        + '<div style="margin-top:12px">' + chart + '</div></div>');
    }
  } else {
    teile.push(hinweisKarte('No watcher counters in pilot.json (watcher_statistik, signal_zaehler) — no funnel drawn.'));
  }

  // The API-side evaluation (auswertung), when served.
  teile.push(pilotAuswertungHtml(payload, abgeschlossen));
  return teile.join('');
}

// ---------------------------------------------------------------- methodology (slug methodology, audit.json)
// Vier Zaehler aus audit.json und der Methodentext der Studien. Der Text ist
// Dokumentation, keine Messung: er steht auch, wenn audit.json fehlt — die
// Kacheln sagen dann, welche Datei fehlt.
const ONE_PAGER_URL = 'https://github.com/Pablozh123/prediction-market-terminal/blob/main/docs/research/ONE_PAGER.md';

// Eine Zeile Kernaussage je Methodenabschnitt. Die Seite war 5.800 Zeichen
// Fliesstext in neun Spalten; jetzt laesst sie sich in neun Zeilen
// ueberfliegen und der Absatz darunter qualifiziert die Zeile. Jeder Satz
// stammt aus dem Absatz, den er zusammenfasst — keine neue Behauptung.
const KERNSATZ = {
  'WHAT A STUDY OBSERVATION IS': 'Recorded books only, one fixed horizon per cell, cells never pooled.',
  'HIT RATE AND WILSON LOWER BOUND': 'Every hit rate carries the lower bound of its 95% interval, so a small sample cannot overclaim.',
  'ROUND-TRIP COST = SPREAD + FEE': 'A 2.58 cent round trip against 0.09 cents of gross edge — real and untradable at the same time.',
  'FILL MODELS: TOUCH VS TAPE, AND THE MARKOUT IDENTITY': 'Two fill models bracket the truth; when they straddle zero the verdict is "not identified".',
  'BLOCK BOOTSTRAP': 'Days are resampled in blocks; under three days no interval can be computed at all.',
  'CROSS-VENUE MATCHING AND FEE CURVES': 'Pairs are matched by what the question asks, not by wording — two apparent edges were mismatches.',
  'WALLET RECONCILIATION VS LOG': 'The page shows the wallet figures; the log reconstruction stays in runs.json as raw data.',
  'PRE-REGISTRATION POLICY': 'Rules fixed and time-stamped before the outcome period, and failures published too.',
  'AGENT LAYER GUARDRAILS': 'Read-only tools, capped rows, a skeptic that can only lower priority, mock backend by default.'
};

function renderMethodology(T, payload, study) {
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
    + '<div style="' + M + '; font-size:11px; letter-spacing:.14em; color:var(--info)">' + esc(titel) + '</div>'
    + (KERNSATZ[titel] ? '<div style="font-size:13.5px; color:var(--text); font-weight:500; margin-top:7px; line-height:1.45">' + esc(KERNSATZ[titel]) + '</div>' : '')
    + '<div style="font-size:13px; color:rgba(var(--ink),.72); margin-top:8px; line-height:1.65">' + text + '</div></div>';
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
      'The live-runs page shows the wallet-reconciled figures: what the on-chain wallet statement records as buys and net PnL, dated by its reconciliation day — the cash truth. The bot\'s own logs also reconstruct a stake and PnL, but where the FAK order status returned no fill price that reconstruction assumes the price cap (the order response ' + mono('price') + ' is the cap, not the fill), which overstates the stake and understates the shares — so the log figures stay in runs.json as raw data and appear on the page only where no wallet figure exists yet, labelled as coming from the run log. The wallet address ' + mono(LIVE_RUN_WALLET) + ' is public, so anyone can rerun the check against the Polymarket Data API.'),
    abschnitt('PRE-REGISTRATION POLICY',
      'Pre-registered means: hypothesis, primary metric, success threshold, cohort and exclusion rules are fixed before the first look at the outcome period, and externally time-stamped. Results are published in both directions — a failure and an insufficient sample are both citable results — and every analysis outside the pre-registered primary test is marked exploratory. The pilot froze its rules before the first trade and reports its own deviation from the frozen text (stake halved) as a deviation; the track-record validation is drafted for AsPredicted and listed as pending until submitted.'),
    abschnitt('AGENT LAYER GUARDRAILS',
      'Agents read exclusively through the MCP read layer: four read-only tools, at most 50 rows per response, wallet addresses masked. The skeptic can only lower a case\'s priority (deduction between -0.3 and 0), never raise it; recommendations come from a fixed whitelist (watch, check source, escalate to a human); a redaction gate aborts a publish that contains wallet-address patterns or key-like strings; and the default backend is a deterministic mock with no network access — productive LLM mode is an explicit flag. '
      + '<span style="color:var(--warn)">' + esc(backendSatz) + '</span>')
  ];

  return '<div style="padding:22px 24px">'
    + '<div style="display:flex; align-items:flex-start; justify-content:space-between; gap:24px">'
    + '<div style="max-width:720px">'
    + '<div style="font-size:20px; font-weight:600">' + esc(study.title) + '</div>'
    + '<div style="font-size:13.5px; color:rgba(var(--ink),.6); margin-top:8px; line-height:1.5">' + esc(note) + '</div></div>'
    + stempelBlock(study, payload) + '</div>'
    + '<div style="display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-top:18px">'
    + stats.map((x) =>
      '<div style="' + KARTE + '; border-radius:6px; padding:14px 16px">'
      + '<div style="' + M + '; font-size:10.5px; letter-spacing:.13em; color:rgba(var(--ink),.6)">' + esc(x.label) + '</div>'
      + '<div style="' + M + '; font-size:21px; margin-top:7px">' + esc(x.value) + '</div>'
      + '<div style="' + M + '; font-size:10.5px; color:rgba(var(--ink),.6); margin-top:4px">' + esc(x.note) + '</div></div>'
    ).join('')
    + '</div>'
    + (payload ? '' : '<div style="margin-top:12px">' + leerZeile(herkunftSatz(null, 'public/data/audit.json')) + '</div>')
    + '<div style="' + M + '; font-size:10.5px; letter-spacing:.14em; color:var(--info); margin:20px 0 10px">HOW THE STUDIES ARE MEASURED</div>'
    + '<div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(380px, 1fr)); gap:12px">' + sektionen.join('') + '</div>'
    + queueArchivHtml(T)
    + '<div style="display:flex; gap:10px; margin-top:14px; flex-wrap:wrap">'
    + '<a href="' + ONE_PAGER_URL + '" target="_blank" rel="noopener" class="hv-bd35" style="font-size:13px; color:var(--text); border:1px solid rgba(var(--ink),.2); border-radius:4px; padding:10px 16px; text-decoration:none; display:inline-block">Read the full one-pager ↗</a>'
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
  const link = (href, label) => '<a href="' + esc(href) + '" target="_blank" rel="noopener" style="color:var(--info); text-decoration:none">' + esc(label) + ' ↗</a>';
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
