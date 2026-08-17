// Microstructure — the twelve recorded-book studies, one card each.
//
// Feeds off public/data/microstructure.json (built by
// app/microstructure_report.py). Every number in here comes from that file;
// this module only lays it out. Charts are plain SVG so the page stays
// dependency free like the rest of the terminal.
//
// Jede Karte fuehrt mit Verdikt, Diagramm und Kennzahlen; die Methode, der
// erklaerende Fliesstext und die Gegenlesarten stehen vollstaendig darunter,
// zugeklappt hinter einem <details>. Nichts davon ist gekuerzt — nur die
// Reihenfolge folgt jetzt dem Leser: erst der Befund, dann die Pruefung.

import { esc } from '../util.js';
import { diagramm, fmtZahl } from '../charts.js';

const M = "font-family:'JetBrains Mono',monospace";
const CARD = 'background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:12px';
const MUTED = 'color:rgba(255,255,255,.55)';
const HR = 'border-top:1px solid rgba(255,255,255,.07); margin-top:20px; padding-top:18px';

const VERDIKT_FARBE = { ja: '#C8F542', nein: '#FF7A7A', offen: '#F5A623', kontrolle: '#7DE2D1' };
// CONTROL ist bewusst kein CONFIRMED: die Studie prueft die eigene Messkette,
// nicht den Markt. Als bestaetigte Hypothese gezaehlt waere sie ein
// bestandener Selbsttest, der wie ein Befund aussieht.
const VERDIKT_TEXT = { ja: 'CONFIRMED', nein: 'REFUTED', offen: 'NOT IDENTIFIED', kontrolle: 'CONTROL' };
// Lesart lime, Gegenlesart blau, Grenze grau: drei Farben, damit die
// Gegenlesart nicht wie ein Nachtrag zur Lesart aussieht.
const DEUTUNG_FARBE = { lesart: '#C8F542', gegenlesart: '#4F8EF7', grenze: '#95A0AB' };

function abschnitt(titel, inhalt, zusatz) {
  if (!inhalt) return '';
  return '<div style="' + HR + '">'
    + '<div style="' + M + '; font-size:10px; letter-spacing:.15em; color:#4F8EF7; margin-bottom:12px">'
    + esc(titel) + (zusatz ? ' <span style="color:rgba(255,255,255,.32)">' + esc(zusatz) + '</span>' : '')
    + '</div>' + inhalt + '</div>';
}

// fmtZahl und das Balken-/Intervalldiagramm leben jetzt in ../charts.js und
// werden oben importiert; hier bleibt nur die Kartenstruktur der Studien.

function analyseBlock(analyse) {
  if (!analyse || !analyse.length) return '';
  return '<div style="display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:1px; '
    + 'background:rgba(255,255,255,.07); border:1px solid rgba(255,255,255,.07); border-radius:10px; overflow:hidden">'
    + analyse.map((a) =>
      '<div style="background:#10151A; padding:14px 16px">'
      + '<div style="' + M + '; font-size:9.5px; letter-spacing:.12em; color:rgba(255,255,255,.42)">'
      + esc(a.titel) + '</div>'
      + '<div style="font-size:12.5px; color:rgba(255,255,255,.78); margin-top:7px; line-height:1.6">'
      + esc(a.text) + '</div></div>'
    ).join('')
    + '</div>';
}

function deutungBlock(interpretation) {
  if (!interpretation || !interpretation.length) return '';
  return interpretation.map((i) => {
    const farbe = DEUTUNG_FARBE[i.art] || '#95A0AB';
    return '<div style="border-left:2px solid ' + farbe + '66; padding:2px 0 2px 14px; margin-bottom:14px">'
      + '<div style="' + M + '; font-size:9.5px; letter-spacing:.12em; color:' + farbe + '">'
      + esc(i.titel) + '</div>'
      + '<div style="font-size:13px; color:rgba(255,255,255,.72); margin-top:6px; line-height:1.65; max-width:720px">'
      + esc(i.text) + '</div></div>';
  }).join('');
}

function zahlenBlock(zahlen) {
  if (!zahlen || !zahlen.length) return '';
  return '<div style="' + CARD + '; padding:6px 0">'
    + zahlen.map((z) =>
      '<div style="display:grid; grid-template-columns:1fr auto; gap:14px; align-items:baseline; padding:9px 16px; border-bottom:1px solid rgba(255,255,255,.05)">'
      + '<div><div style="font-size:12.5px; color:rgba(255,255,255,.78)">' + esc(z.label) + '</div>'
      + (z.hinweis ? '<div style="font-size:11px; ' + MUTED + '; margin-top:3px; line-height:1.45">' + esc(z.hinweis) + '</div>' : '')
      + '</div>'
      + '<div style="' + M + '; font-size:14px; color:#fff; white-space:nowrap">' + esc(fmtZahl(z.wert))
      + (z.einheit ? ' <span style="font-size:10.5px; color:rgba(255,255,255,.45)">' + esc(z.einheit) + '</span>' : '')
      + '</div></div>'
    ).join('')
    + '</div>';
}

/** Rohzeilen als aufklappbare Tabelle. Zugeklappt, damit die Karte lesbar bleibt. */
function detailBlock(details, id) {
  if (!details || !details.zeilen || !details.zeilen.length) return '';
  const kopf = details.spalten.map((c, i) =>
    '<th style="' + M + '; font-size:9.5px; letter-spacing:.1em; color:rgba(255,255,255,.45); '
    + 'text-align:' + (i === 0 ? 'left' : 'right') + '; padding:8px 12px; white-space:nowrap; '
    + 'border-bottom:1px solid rgba(255,255,255,.09)">' + esc(c) + '</th>').join('');
  const koerper = details.zeilen.map((zeile) =>
    '<tr>' + zeile.map((z, i) =>
      '<td style="' + (i === 0 ? 'font-size:12px' : M + '; font-size:11.5px')
      + '; color:rgba(255,255,255,' + (i === 0 ? '.75' : '.62') + '); '
      + 'text-align:' + (i === 0 ? 'left' : 'right') + '; padding:7px 12px; white-space:nowrap; '
      + 'border-bottom:1px solid rgba(255,255,255,.04)">' + esc(String(z)) + '</td>').join('')
    + '</tr>').join('');

  // data-key wie beim Methodenblock: die App merkt sich geoeffnete <details>.
  return '<details data-key="raw:' + esc(String(id || '')) + '" style="' + CARD + '; padding:0; overflow:hidden">'
    + '<summary style="' + M + '; font-size:10.5px; letter-spacing:.1em; color:rgba(255,255,255,.6); '
    + 'padding:13px 16px; cursor:pointer; list-style:none">▸ ' + esc(details.titel)
    + ' <span style="color:rgba(255,255,255,.35)">· ' + details.zeilen.length + ' rows</span></summary>'
    + '<div style="overflow-x:auto; border-top:1px solid rgba(255,255,255,.07)">'
    + '<table style="width:100%; border-collapse:collapse"><thead><tr>' + kopf + '</tr></thead>'
    + '<tbody>' + koerper + '</tbody></table></div>'
    + (details.hinweis
      ? '<div style="font-size:11.5px; ' + MUTED + '; padding:11px 16px; line-height:1.55; '
        + 'border-top:1px solid rgba(255,255,255,.05)">' + esc(details.hinweis) + '</div>'
      : '')
    + '</details>';
}

function basisZeile(basis) {
  if (!basis) return '';
  const teile = [];
  const b = basis;
  if (b.beobachtungen) teile.push(Number(b.beobachtungen).toLocaleString('en-US') + ' observations');
  if (b.snapshots) teile.push(Number(b.snapshots).toLocaleString('en-US') + ' book snapshots');
  if (b.tokens) teile.push(Number(b.tokens).toLocaleString('en-US') + ' tokens');
  if (b.maerkte) teile.push(Number(b.maerkte).toLocaleString('en-US') + ' markets');
  if (b.paare) teile.push(b.paare + ' pairs');
  if (b.tage) teile.push(b.tage + ' days');
  // Das Kalenderfenster gehoert an jede Zahl. Ohne es ist nicht zu sehen,
  // ob zwei Studien denselben Zeitraum messen.
  if (b.fenster) teile.push(b.fenster);
  if (!teile.length) return '';
  return '<div style="' + M + '; font-size:10.5px; color:rgba(255,255,255,.45)">DATA · ' + esc(teile.join(' · ')) + '</div>';
}

function quelleLinks(s) {
  const link = (pfad, text) =>
    '<a href="https://github.com/Pablozh123/prediction-market-terminal/blob/main/' + esc(pfad)
    + '" target="_blank" rel="noopener" style="' + M + '; font-size:10.5px; color:#4F8EF7; text-decoration:none; '
    + 'border:1px solid rgba(79,142,247,.35); border-radius:6px; padding:5px 9px">' + esc(text) + ' ↗</a>';
  return '<div style="display:flex; gap:8px; flex-wrap:wrap; align-items:center">'
    + link(s.report, 'FULL REPORT') + link(s.modul, 'SOURCE MODULE') + '</div>';
}

// Methode, Fliesstext und Deutung, zugeklappt. Der Inhalt ist derselbe wie
// vorher — nur steht er nicht mehr zwischen Leser und Befund. Ein <details>
// statt eines eigenen Handlers, damit die Seite eine reine Funktion bleibt.
function methodeBlock(s) {
  const inhalt = abschnitt('WHAT WAS ANALYSED', analyseBlock(s.analyse))
    + abschnitt('WHAT THE NUMBERS SAY',
      '<div style="font-size:13.5px; color:rgba(255,255,255,.75); line-height:1.7; max-width:760px">'
      + esc(s.einfach) + '</div>')
    + abschnitt('HOW TO READ IT', deutungBlock(s.interpretation));
  if (!inhalt) return '';
  // data-key: die App merkt sich geoeffnete <details> ueber Re-Renders; die
  // zwoelf Karten tragen denselben Summary-Text, also braucht jede ihre ID.
  return '<details data-key="method:' + esc(String(s.id || '')) + '" style="' + CARD + '; margin-top:14px; overflow:hidden">'
    + '<summary style="' + M + '; font-size:10.5px; letter-spacing:.1em; color:rgba(255,255,255,.6); '
    + 'padding:13px 16px; cursor:pointer; list-style:none">▸ METHOD &amp; HOW TO READ IT'
    + ' <span style="color:rgba(255,255,255,.35)">· what was analysed, what else fits the numbers</span></summary>'
    + '<div style="padding:0 18px 18px; border-top:1px solid rgba(255,255,255,.07)">' + inhalt + '</div>'
    + '</details>';
}

// Anker je Karte. Die Adresse bleibt unter der Research-Route, damit der
// hashchange-Handler der App auf derselben Studie landet und ein Reload die
// Seite wiederfindet: #research/microstructure/<id>.
export function studieAnker(s, i) {
  const id = String((s && s.id) || ('study-' + (i + 1))).toLowerCase().replace(/[^a-z0-9_-]+/g, '-');
  return 'research/microstructure/' + id;
}

// Kurzlabel fuer die Sprungliste: die Studien-ID in Worten ("mm-staleness"
// → "MM staleness"); ohne ID die Frage, auf wenige Woerter gekuerzt.
function kurzLabel(s, i) {
  const nr = String(i + 1).padStart(2, '0') + ' ';
  const id = String((s && s.id) || '').trim();
  if (id) {
    const worte = id.split(/[-_]+/).filter(Boolean).map((w) => (w === 'mm' ? 'MM' : w));
    if (worte.length) worte[0] = worte[0] === 'MM' ? 'MM' : worte[0].charAt(0).toUpperCase() + worte[0].slice(1);
    return nr + worte.join(' ');
  }
  const frage = String((s && s.frage) || '').replace(/\?$/, '');
  const worte = frage.split(/\s+/).filter(Boolean);
  const kurz = worte.length > 5 ? worte.slice(0, 5).join(' ') + '…' : frage;
  return nr + (kurz || ('Study ' + (i + 1)));
}

// Verdikte aus den Studien selbst gezaehlt, nicht aus dem Zaehlerfeld —
// die Zeile darf der Kartenliste nie widersprechen.
export function verdiktZaehlung(studien) {
  const z = { ja: 0, nein: 0, offen: 0, kontrolle: 0, gesamt: 0 };
  (Array.isArray(studien) ? studien : []).forEach((s) => {
    z.gesamt += 1;
    if (s && Object.prototype.hasOwnProperty.call(z, s.verdikt_art)) z[s.verdikt_art] += 1;
  });
  return z;
}

function verdiktZeile(studien) {
  const z = verdiktZaehlung(studien);
  if (!z.gesamt) return '';
  const teil = (n, text, farbe) => '<span style="color:' + farbe + '">' + n + ' ' + text + '</span>';
  return '<div style="' + M + '; font-size:11.5px; color:rgba(255,255,255,.55); margin-top:12px">'
    + [teil(z.nein, 'refuted', VERDIKT_FARBE.nein), teil(z.ja, 'confirmed', VERDIKT_FARBE.ja),
      teil(z.offen, 'not identified', VERDIKT_FARBE.offen), teil(z.kontrolle, 'control', VERDIKT_FARBE.kontrolle)].join(' · ')
    + ' <span style="color:rgba(255,255,255,.35)">· ' + z.gesamt + ' studies</span></div>';
}

function sprungliste(studien) {
  if (!Array.isArray(studien) || !studien.length) return '';
  return '<div style="display:flex; gap:6px; flex-wrap:wrap; margin-top:12px">'
    + studien.map((s, i) => {
      const farbe = VERDIKT_FARBE[s.verdikt_art] || '#95A0AB';
      return '<a href="#' + esc(studieAnker(s, i)) + '" style="' + M + '; font-size:10px; color:rgba(255,255,255,.7); text-decoration:none; '
        + 'border:1px solid rgba(255,255,255,.14); border-left:2px solid ' + farbe + '; border-radius:5px; padding:4px 8px; white-space:nowrap">'
        + esc(kurzLabel(s, i)) + '</a>';
    }).join('')
    + '</div>';
}

function studieKarte(s, i) {
  const farbe = VERDIKT_FARBE[s.verdikt_art] || '#95A0AB';
  const marke = VERDIKT_TEXT[s.verdikt_art] || 'RESULT';

  const zahlenUndDiagramm = '<div style="display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:12px; margin-top:16px">'
    + diagramm(s.diagramm) + zahlenBlock(s.zahlen) + '</div>';

  return '<div id="' + esc(studieAnker(s, i)) + '" style="' + CARD + '; padding:22px 24px; margin-bottom:18px; scroll-margin-top:16px">'
    + '<div style="display:flex; align-items:flex-start; justify-content:space-between; gap:18px; flex-wrap:wrap">'
    + '<div style="flex:1; min-width:260px">'
    + '<div style="' + M + '; font-size:10px; letter-spacing:.16em; color:rgba(255,255,255,.35)">STUDY '
    + String(i + 1).padStart(2, '0') + '</div>'
    + '<div style="font-size:19px; font-weight:600; margin-top:6px; line-height:1.35">' + esc(s.frage) + '</div>'
    + '</div>'
    + '<div style="' + M + '; font-size:9.5px; letter-spacing:.13em; color:' + farbe
    + '; border:1px solid ' + farbe + '55; border-radius:6px; padding:6px 10px; white-space:nowrap">' + marke + '</div>'
    + '</div>'
    + '<div style="font-size:14.5px; color:' + farbe + '; margin-top:12px; line-height:1.5; font-weight:500; max-width:760px">'
    + esc(s.verdikt) + '</div>'

    // Befund zuerst: Diagramm und Kennzahlen direkt unter dem Verdikt.
    + zahlenUndDiagramm
    + methodeBlock(s)
    + (s.details && s.details.zeilen && s.details.zeilen.length
      ? '<div style="margin-top:12px">' + detailBlock(s.details, s.id) + '</div>' : '')

    + '<div style="' + HR + '; display:flex; align-items:center; justify-content:space-between; gap:16px; flex-wrap:wrap">'
    + basisZeile(s.basis) + quelleLinks(s) + '</div>'
    + '</div>';
}

function kopf(payload) {
  const z = payload.zaehler || {};
  const stempel = payload.stand_utc
    ? String(payload.stand_utc).slice(0, 16).replace('T', ' ') + ' UTC'
    : 'rolling';
  const kachel = (wert, text, farbe) =>
    '<div style="' + CARD + '; padding:13px 16px; min-width:118px">'
    + '<div style="' + M + '; font-size:22px; color:' + farbe + '">' + esc(String(wert)) + '</div>'
    + '<div style="' + M + '; font-size:9.5px; letter-spacing:.12em; color:rgba(255,255,255,.45); margin-top:5px">'
    + esc(text) + '</div></div>';

  return '<div style="padding:2px 0 0">'
    + '<div style="display:flex; align-items:flex-start; justify-content:space-between; gap:24px; flex-wrap:wrap">'
    + '<div style="max-width:760px">'
    + '<div style="font-size:20px; font-weight:600">Order books, recorded by this project</div>'
    + '<div style="font-size:13.5px; ' + MUTED + '; margin-top:9px; line-height:1.6">'
    + esc(payload.einleitung || '') + '</div></div>'
    + '<div style="' + M + '; font-size:10.5px; color:rgba(255,255,255,.4); border:1px solid rgba(255,255,255,.14); '
    + 'border-radius:6px; padding:6px 10px; white-space:nowrap">' + esc(stempel) + '</div></div>'
    // Verdiktzeile aus den Karten gezaehlt und die Sprungliste zu den Ankern.
    + verdiktZeile(payload.studien)
    + sprungliste(payload.studien)
    + '<div style="display:flex; gap:12px; margin-top:16px; flex-wrap:wrap">'
    + kachel(z.gesamt || 0, 'STUDIES', '#fff')
    + kachel(z.nein || 0, 'REFUTED', '#FF7A7A')
    + kachel(z.ja || 0, 'CONFIRMED', '#C8F542')
    + kachel(z.offen || 0, 'NOT IDENTIFIED', '#F5A623')
    + (z.kontrolle ? kachel(z.kontrolle, 'CONTROL', '#7DE2D1') : '')
    + '</div>'
    + (payload.hinweis
      ? '<div style="font-size:12px; color:rgba(255,255,255,.45); margin-top:14px; line-height:1.55; max-width:760px; '
        + 'border-left:2px solid rgba(255,255,255,.14); padding-left:12px">' + esc(payload.hinweis) + '</div>'
      : '')
    + '<div style="height:20px"></div></div>';
}

export function renderMicrostructure(payload) {
  if (!payload || !Array.isArray(payload.studien) || !payload.studien.length) {
    return '<div style="padding:26px 24px">'
      + '<div style="' + CARD + '; padding:22px 24px; max-width:720px">'
      + '<div style="font-size:16px; font-weight:600">No study data published yet</div>'
      + '<div style="font-size:13px; ' + MUTED + '; margin-top:9px; line-height:1.6">The file '
      + '<span style="' + M + '">public/data/microstructure.json</span> is missing. Build it with '
      + '<span style="' + M + '">python scripts/publish_microstructure.py</span>.</div></div></div>';
  }
  const fehlend = Array.isArray(payload.fehlend) && payload.fehlend.length
    ? '<div style="' + M + '; font-size:11px; color:#F5A623; margin-bottom:14px">'
      + esc(payload.fehlend.length + ' study artifact(s) missing from this build: ' + payload.fehlend.join(', '))
      + '</div>'
    : '';
  return '<div style="padding:22px 24px 40px">'
    + kopf(payload)
    + fehlend
    + payload.studien.map(studieKarte).join('')
    + '</div>';
}
