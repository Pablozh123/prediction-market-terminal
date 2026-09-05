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

import { esc, stempelBlock } from '../util.js';
import { diagramm, fmtZahl } from '../charts.js';
import { MONO as M, KARTE } from '../ui.js';

const MUTED = 'color:var(--ink-4)';
const HR = 'border-top:1px solid var(--line-3); margin-top:var(--sp-6); padding-top:var(--sp-5)';

const VERDIKT_FARBE = { ja: 'var(--accent)', nein: 'var(--neg-soft)', offen: 'var(--warn)', kontrolle: 'var(--cat-teal)' };
// CONTROL ist bewusst kein CONFIRMED: die Studie prueft die eigene Messkette,
// nicht den Markt. Als bestaetigte Hypothese gezaehlt waere sie ein
// bestandener Selbsttest, der wie ein Befund aussieht.
const VERDIKT_TEXT = { ja: 'CONFIRMED', nein: 'REFUTED', offen: 'NOT IDENTIFIED', kontrolle: 'CONTROL' };
// Lesart lime, Gegenlesart blau, Grenze grau: drei Farben, damit die
// Gegenlesart nicht wie ein Nachtrag zur Lesart aussieht.
const DEUTUNG_FARBE = { lesart: 'var(--accent)', gegenlesart: 'var(--info)', grenze: 'var(--muted)' };

function abschnitt(titel, inhalt, zusatz) {
  if (!inhalt) return '';
  return '<div style="' + HR + '">'
    + '<h4 style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:var(--info); margin:0 0 var(--sp-4); font-weight:400">'
    + esc(titel) + (zusatz ? ' <span style="color:var(--ink-4)">' + esc(zusatz) + '</span>' : '')
    + '</h4>' + inhalt + '</div>';
}

// fmtZahl und das Balken-/Intervalldiagramm leben jetzt in ../charts.js und
// werden oben importiert; hier bleibt nur die Kartenstruktur der Studien.

function analyseBlock(analyse) {
  if (!analyse || !analyse.length) return '';
  return '<div style="display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:var(--sp-1); '
    + 'background:rgba(var(--ink),.07); border:1px solid var(--line-3); border-radius:var(--r-panel); overflow:hidden">'
    + analyse.map((a) =>
      '<div style="background:var(--panel); padding:var(--sp-5)">'
      + '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:var(--ink-3)">'
      + esc(a.titel) + '</div>'
      + '<div style="font-size:var(--t-small); color:var(--ink-1); margin-top:var(--sp-3); line-height:var(--lh-prose)">'
      + esc(a.text) + '</div></div>'
    ).join('')
    + '</div>';
}

function deutungBlock(interpretation) {
  if (!interpretation || !interpretation.length) return '';
  return interpretation.map((i) => {
    const farbe = DEUTUNG_FARBE[i.art] || 'var(--muted)';
    // color-mix, not a hex alpha suffix: farbe is always a var(--token), and
    // 'var(--accent)66' is not a colour — the shorthand was dropped and this
    // verdict bar was never drawn at all.
    return '<div style="border-left:2px solid color-mix(in srgb, ' + farbe + ' 40%, transparent); padding:var(--sp-1) 0 var(--sp-1) var(--sp-5); margin-bottom:var(--sp-5)">'
      + '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:' + farbe + '">'
      + esc(i.titel) + '</div>'
      + '<div style="font-size:var(--t-body); color:var(--ink-2); margin-top:var(--sp-3); line-height:var(--lh-prose); max-width:720px">'
      + esc(i.text) + '</div></div>';
  }).join('');
}

function zahlenBlock(zahlen) {
  if (!zahlen || !zahlen.length) return '';
  return '<div style="' + KARTE + '; padding:var(--sp-3) 0">'
    + zahlen.map((z) =>
      '<div style="display:grid; grid-template-columns:1fr auto; gap:var(--sp-5); align-items:baseline; padding:var(--sp-3) var(--sp-5); border-bottom:1px solid var(--line-3)">'
      + '<div><div style="font-size:var(--t-small); color:var(--ink-1)">' + esc(z.label) + '</div>'
      + (z.hinweis ? '<div style="font-size:var(--t-micro); ' + MUTED + '; margin-top:var(--sp-2); line-height:var(--lh-snug)">' + esc(z.hinweis) + '</div>' : '')
      + '</div>'
      + '<div style="' + M + '; font-size:var(--t-body); color:var(--text); white-space:nowrap">' + esc(fmtZahl(z.wert))
      + (z.einheit ? ' <span style="font-size:var(--t-micro); color:var(--ink-3)">' + esc(z.einheit) + '</span>' : '')
      + '</div></div>'
    ).join('')
    + '</div>';
}

/** Rohzeilen als aufklappbare Tabelle. Zugeklappt, damit die Karte lesbar bleibt. */
function detailBlock(details, id) {
  if (!details || !details.zeilen || !details.zeilen.length) return '';
  const kopf = details.spalten.map((c, i) =>
    '<th style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps); color:var(--ink-3); '
    + 'text-align:' + (i === 0 ? 'left' : 'right') + '; padding:var(--sp-3) var(--sp-4); white-space:nowrap; '
    + 'border-bottom:1px solid var(--line-2)">' + esc(c) + '</th>').join('');
  const koerper = details.zeilen.map((zeile) =>
    '<tr>' + zeile.map((z, i) =>
      '<td style="' + (i === 0 ? 'font-size:var(--t-small)' : M + '; font-size:var(--t-small)')
      + '; color:' + (i === 0 ? 'var(--ink-2)' : 'var(--ink-3)') + '; '
      + 'text-align:' + (i === 0 ? 'left' : 'right') + '; padding:var(--sp-3) var(--sp-4); white-space:nowrap; '
      + 'border-bottom:1px solid var(--line-3)">' + esc(String(z)) + '</td>').join('')
    + '</tr>').join('');

  // Kein eigenes <details> mehr: die Rohzeilen sind der letzte Abschnitt IM
  // Methodenfeld. Zwoelf Studien mal zwei Klappfelder waren vierundzwanzig
  // Tueren auf einer Seite — und eine zugeklappte Tuer kostet trotzdem eine
  // Zeile Chrom, ein Label und eine Entscheidung.
  return '<div style="margin-top:var(--sp-5)">'
    + '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:var(--ink-4)">'
    + esc(details.titel) + ' · ' + details.zeilen.length + ' rows</div>'
    + '<div style="overflow-x:auto; border:1px solid var(--line-3); border-radius:var(--r-control); margin-top:var(--sp-3)">'
    + '<table style="width:100%; border-collapse:collapse"><thead><tr>' + kopf + '</tr></thead>'
    + '<tbody>' + koerper + '</tbody></table></div>'
    + (details.hinweis
      ? '<div style="font-size:var(--t-small); ' + MUTED + '; padding:var(--sp-3) var(--sp-1) 0; line-height:var(--lh-prose)">' + esc(details.hinweis) + '</div>'
      : '')
    + '</div>';
}

// Auch von der Cross-Venue-Seite genutzt: dort steht dieselbe Basiszeile
// unter den beiden Studien, die zu ihrer Frage gehoeren.
export function basisZeile(basis) {
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
  return '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-3)">DATA · ' + esc(teile.join(' · ')) + '</div>';
}

function quelleLinks(s) {
  const link = (pfad, text) =>
    '<a href="https://github.com/Pablozh123/prediction-market-terminal/blob/main/' + esc(pfad)
    + '" target="_blank" rel="noopener" style="' + M + '; font-size:var(--t-micro); color:var(--info); text-decoration:none; '
    + 'border:1px solid rgba(var(--info-rgb),.35); border-radius:var(--r-control); padding:var(--sp-2) var(--sp-3)">' + esc(text) + ' ↗</a>';
  return '<div style="display:flex; gap:var(--sp-3); flex-wrap:wrap; align-items:center">'
    + link(s.report, 'FULL REPORT') + link(s.modul, 'SOURCE MODULE') + '</div>';
}

// Methode, Fliesstext und Deutung, zugeklappt. Der Inhalt ist derselbe wie
// vorher — nur steht er nicht mehr zwischen Leser und Befund. Ein <details>
// statt eines eigenen Handlers, damit die Seite eine reine Funktion bleibt.
function methodeBlock(s) {
  const roh = s.details && s.details.zeilen && s.details.zeilen.length ? detailBlock(s.details, s.id) : '';
  const inhalt = abschnitt('WHAT WAS ANALYSED', analyseBlock(s.analyse))
    + abschnitt('WHAT THE NUMBERS SAY',
      '<div style="font-size:var(--t-body); color:var(--ink-2); line-height:var(--lh-prose); max-width:760px">'
      + esc(s.einfach) + '</div>')
    + abschnitt('HOW TO READ IT', deutungBlock(s.interpretation))
    + roh;
  if (!inhalt) return '';
  // data-key: die App merkt sich geoeffnete <details> ueber Re-Renders; die
  // zwoelf Karten tragen denselben Summary-Text, also braucht jede ihre ID.
  // Ein Feld je Studie, nicht zwei: die Rohzeilen sitzen darin ganz unten.
  return '<details data-key="method:' + esc(String(s.id || '')) + '" style="' + KARTE + '; margin-top:var(--sp-5); overflow:hidden">'
    + '<summary style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps); color:var(--ink-3); '
    + 'padding:var(--sp-4) var(--sp-5); cursor:pointer; list-style:none">▸ METHOD, HOW TO READ IT'
    + (roh ? ' &amp; THE RAW ROWS' : '')
    + ' <span style="color:var(--ink-4)">· what was analysed, what else fits the numbers'
    + (roh ? ', every row behind them' : '') + '</span></summary>'
    + '<div style="padding:0 var(--sp-5) var(--sp-5); border-top:1px solid var(--line-3)">' + inhalt + '</div>'
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
  return '<div style="' + M + '; font-size:var(--t-small); color:var(--ink-4); margin-top:var(--sp-4)">'
    + [teil(z.nein, 'refuted', VERDIKT_FARBE.nein), teil(z.ja, 'confirmed', VERDIKT_FARBE.ja),
      teil(z.offen, 'not identified', VERDIKT_FARBE.offen), teil(z.kontrolle, 'control', VERDIKT_FARBE.kontrolle)].join(' · ')
    + ' <span style="color:var(--ink-4)">· ' + z.gesamt + ' studies</span></div>';
}

function sprungliste(studien) {
  if (!Array.isArray(studien) || !studien.length) return '';
  return '<div style="display:flex; gap:var(--sp-3); flex-wrap:wrap; margin-top:var(--sp-4)">'
    + studien.map((s, i) => {
      const farbe = VERDIKT_FARBE[s.verdikt_art] || 'var(--muted)';
      return '<a href="#' + esc(studieAnker(s, i)) + '" style="' + M + '; font-size:var(--t-micro); color:var(--ink-2); text-decoration:none; '
        + 'border:1px solid var(--line-1); border-left:2px solid ' + farbe + '; border-radius:var(--r-control); padding:var(--sp-2) var(--sp-3); white-space:nowrap">'
        + esc(kurzLabel(s, i)) + '</a>';
    }).join('')
    + '</div>';
}

function studieKarte(s, i) {
  const farbe = VERDIKT_FARBE[s.verdikt_art] || 'var(--muted)';
  const marke = VERDIKT_TEXT[s.verdikt_art] || 'RESULT';

  const zahlenUndDiagramm = '<div style="display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:var(--sp-4); margin-top:var(--sp-5)">'
    + diagramm(s.diagramm) + zahlenBlock(s.zahlen) + '</div>';

  return '<div id="' + esc(studieAnker(s, i)) + '" style="' + KARTE + '; padding:var(--sp-6); margin-bottom:var(--sp-5); scroll-margin-top:16px">'
    + '<div style="display:flex; align-items:flex-start; justify-content:space-between; gap:var(--sp-5); flex-wrap:wrap">'
    + '<div style="flex:1; min-width:260px">'
    + '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:var(--ink-4)">STUDY '
    + String(i + 1).padStart(2, '0') + '</div>'
    + '<h3 style="font-size:var(--t-head); font-weight:600; margin-top:var(--sp-3); line-height:var(--lh-tight)">' + esc(s.frage) + '</h3>'
    + '</div>'
    + '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:' + farbe
    + '; border:1px solid color-mix(in srgb, ' + farbe + ' 33%, transparent); border-radius:var(--r-control); padding:var(--sp-3) var(--sp-4); white-space:nowrap">' + marke + '</div>'
    + '</div>'
    + '<div style="font-size:var(--t-lead); color:' + farbe + '; margin-top:var(--sp-4); line-height:var(--lh-snug); font-weight:500; max-width:760px">'
    + esc(s.verdikt) + '</div>'

    // Befund zuerst: Diagramm und Kennzahlen direkt unter dem Verdikt.
    + zahlenUndDiagramm
    + methodeBlock(s)

    + '<div style="' + HR + '; display:flex; align-items:center; justify-content:space-between; gap:var(--sp-5); flex-wrap:wrap">'
    + basisZeile(s.basis) + quelleLinks(s) + '</div>'
    + '</div>';
}

function kopf(payload, study) {
  const z = payload.zaehler || {};
  const kachel = (wert, text, farbe) =>
    '<div style="' + KARTE + '; padding:var(--sp-4) var(--sp-5); min-width:118px">'
    + '<div style="' + M + '; font-size:var(--t-head); color:' + farbe + '">' + esc(String(wert)) + '</div>'
    + '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:var(--ink-3); margin-top:var(--sp-2)">'
    + esc(text) + '</div></div>';

  return '<div style="padding:var(--sp-1) 0 0">'
    + '<div style="display:flex; align-items:flex-start; justify-content:space-between; gap:var(--sp-6); flex-wrap:wrap">'
    + '<div style="max-width:760px">'
    + '<h2 style="font-size:var(--t-head); font-weight:600; margin:0">Order books, recorded by this project</h2>'
    + '<div style="font-size:var(--t-body); ' + MUTED + '; margin-top:var(--sp-3); line-height:var(--lh-prose)">'
    + esc(payload.einleitung || '') + '</div></div>'
    + stempelBlock(study, payload) + '</div>'
    // Verdiktzeile aus den Karten gezaehlt und die Sprungliste zu den Ankern.
    + verdiktZeile(payload.studien)
    + sprungliste(payload.studien)
    + '<div style="display:flex; gap:var(--sp-4); margin-top:var(--sp-5); flex-wrap:wrap">'
    + kachel(z.gesamt || 0, 'STUDIES', 'var(--text)')
    + kachel(z.nein || 0, 'REFUTED', 'var(--neg-soft)')
    + kachel(z.ja || 0, 'CONFIRMED', 'var(--accent)')
    + kachel(z.offen || 0, 'NOT IDENTIFIED', 'var(--warn)')
    + (z.kontrolle ? kachel(z.kontrolle, 'CONTROL', 'var(--cat-teal)') : '')
    + '</div>'
    + (payload.hinweis
      ? '<div style="font-size:var(--t-small); color:var(--ink-3); margin-top:var(--sp-5); line-height:var(--lh-prose); max-width:760px; '
        + 'border-left:2px solid var(--line-1); padding-left:var(--sp-4)">' + esc(payload.hinweis) + '</div>'
      : '')
    + '<div style="height:20px"></div></div>';
}

export function renderMicrostructure(payload, study) {
  if (!payload || !Array.isArray(payload.studien) || !payload.studien.length) {
    return '<div style="padding:var(--sp-6)">'
      + '<div style="' + KARTE + '; padding:var(--sp-6); max-width:720px">'
      + '<div style="font-size:var(--t-lead); font-weight:600">No study data published yet</div>'
      + '<div style="font-size:var(--t-body); ' + MUTED + '; margin-top:var(--sp-3); line-height:var(--lh-prose)">The file '
      + '<span style="' + M + '">public/data/microstructure.json</span> is missing. Build it with '
      + '<span style="' + M + '">python scripts/publish_microstructure.py</span>.</div></div></div>';
  }
  const fehlend = Array.isArray(payload.fehlend) && payload.fehlend.length
    ? '<div style="' + M + '; font-size:var(--t-micro); color:var(--warn); margin-bottom:var(--sp-5)">'
      + esc(payload.fehlend.length + ' study artifact(s) missing from this build: ' + payload.fehlend.join(', '))
      + '</div>'
    : '';
  return '<div style="padding:var(--sp-6) var(--sp-6) var(--sp-7)">'
    + kopf(payload, study)
    + fehlend
    + payload.studien.map(studieKarte).join('')
    + '</div>';
}
