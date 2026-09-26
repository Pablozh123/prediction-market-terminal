// Pre-registrations — das Register: Policy, dann je Eintrag Status, Hypothese,
// Erfolgsregel und, wo es eines gibt, das Trainingsfenster mit Diagramm.
// Liest public/data/preregistrations.json (app/prereg_register.py). Der
// Status haengt am Publikationsdatum der Datei, nicht an der Uhr des Lesers:
// die Nutzlast sagt, was am Stichtag galt, und der Stempel sagt den Stichtag.

import { esc } from '../util.js';
import { diagramm, linien } from '../charts.js';
import { MONO as M, KARTE } from '../ui.js';
import {
  MUTED, HR, abschnitt, tabelleBlock, zahlenBlock, quelleLinks, seitenKopf, hinweisZeile, ohneNutzlastHtml, kachel
} from './study_blocks.js';

const DATEI = 'preregistrations.json';
const BEFEHL = 'python scripts/publish_research_pages.py --only prereg';

const STATUS_FARBE = {
  abgeschlossen: 'var(--accent)', eingefroren: 'var(--info)', laeuft: 'var(--warn)', wartet: 'var(--warn)', entwurf: 'var(--ink-3)'
};

function statusMarke(e) {
  const farbe = STATUS_FARBE[e.status] || 'var(--muted)';
  return '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:' + farbe
    + '; border:1px solid color-mix(in srgb, ' + farbe + ' 33%, transparent); border-radius:var(--r-control); padding:var(--sp-3) var(--sp-4); white-space:nowrap">'
    + esc(e.status_text || String(e.status || '').toUpperCase()) + '</div>';
}

function feld(label, text) {
  if (!text) return '';
  return '<div style="margin-top:var(--sp-4)"><div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:var(--ink-3)">' + esc(label) + '</div>'
    + '<div style="font-size:var(--t-body); color:var(--ink-1); margin-top:var(--sp-2); line-height:var(--lh-prose); max-width:760px">' + esc(text) + '</div></div>';
}

function trainingsKurve(dia) {
  const pts = dia && Array.isArray(dia.punkte) ? dia.punkte.filter((p) => p && p.t && typeof p.wert === 'number') : [];
  if (pts.length < 2) return '';
  const ms0 = Date.parse(pts[0].t);
  return linien({
    titel: dia.titel, einheit: dia.einheit, hinweis: pts.length + ' training days',
    x: pts.map((p) => p.t), xWerte: pts.map((p) => Math.round((Date.parse(p.t) - ms0) / 86400000)),
    serien: [{ name: 'cumulative total, chosen set', werte: pts.map((p) => p.wert) }]
  });
}

function eintragKarte(e) {
  const d = e.diagramme || {};
  const bilder = [diagramm(d.kandidaten), trainingsKurve(d.tage)].filter(Boolean);
  const meta = [
    e.eingefroren ? 'frozen ' + e.eingefroren : '',
    e.fenster ? 'window ' + e.fenster : '',
    e.extern || ''
  ].filter(Boolean).join(' · ');
  const links = [];
  if (e.dokument) links.push({ pfad: e.dokument, text: 'PRE-REGISTRATION' });
  if (e.report) links.push({ pfad: e.report, text: 'TRAINING REPORT' });
  if (e.modul) links.push({ pfad: e.modul, text: 'SOURCE MODULE' });
  const seite = e.seite ? '<a href="#' + esc(e.seite) + '" style="' + M + '; font-size:var(--t-micro); color:var(--info)">open the page this test belongs to →</a>' : '';
  return '<div id="research/pre-registrations/' + esc(String(e.id || '')) + '" style="' + KARTE + '; padding:var(--sp-6); margin-bottom:var(--sp-5); scroll-margin-top:16px">'
    + '<div style="display:flex; align-items:flex-start; justify-content:space-between; gap:var(--sp-5); flex-wrap:wrap">'
    + '<div style="flex:1; min-width:260px">'
    + '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:var(--ink-4)">' + esc(meta) + '</div>'
    + '<h3 style="font-size:var(--t-head); font-weight:600; margin-top:var(--sp-3); line-height:var(--lh-tight)">' + esc(e.titel) + '</h3></div>'
    + statusMarke(e) + '</div>'
    + (e.status_satz ? '<div style="font-size:var(--t-lead); color:' + (STATUS_FARBE[e.status] || 'var(--text)') + '; margin-top:var(--sp-4); line-height:var(--lh-snug); font-weight:500; max-width:760px">' + esc(e.status_satz) + '</div>' : '')
    + feld('HYPOTHESIS', e.hypothese)
    + feld('PRIMARY METRIC AND SUCCESS RULE', e.primaermetrik)
    + feld('HOW THE PARAMETERS WERE CHOSEN', e.wahlregel)
    + feld('RESULT', e.ergebnis)
    + (bilder.length ? '<div style="display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:var(--sp-4); margin-top:var(--sp-5)">' + bilder.join('') + '</div>' : '')
    + (e.zahlen && e.zahlen.length ? '<div style="margin-top:var(--sp-5)">' + zahlenBlock(e.zahlen) + '</div>' : '')
    + (Array.isArray(e.tabellen) && e.tabellen.length
      ? '<details data-key="prereg:' + esc(String(e.id || '')) + '" style="' + KARTE + '; margin-top:var(--sp-5); overflow:hidden">'
        + '<summary style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps); color:var(--ink-3); padding:var(--sp-4) var(--sp-5); cursor:pointer; list-style:none">▸ EVERY ROW OF THE TRAINING WINDOW</summary>'
        + '<div style="padding:0 var(--sp-5) var(--sp-5); border-top:1px solid var(--line-3)">' + e.tabellen.map(tabelleBlock).join('') + '</div></details>'
      : '')
    + '<div style="' + HR + '; display:flex; align-items:center; justify-content:space-between; gap:var(--sp-5); flex-wrap:wrap">' + seite + quelleLinks(links) + '</div>'
    + '</div>';
}

export function renderPrereg(payload, study) {
  const eintraege = payload && Array.isArray(payload.eintraege) ? payload.eintraege : [];
  if (!eintraege.length) return ohneNutzlastHtml(study, DATEI, BEFEHL, payload);
  const z = payload.zaehler || {};
  const policy = Array.isArray(payload.policy) ? payload.policy : [];
  return '<div style="padding:var(--sp-6) var(--sp-6) var(--sp-7)">'
    + seitenKopf(study.title, payload.einleitung, study, payload)
    + '<div style="display:flex; gap:var(--sp-4); margin-top:var(--sp-5); flex-wrap:wrap">'
    + kachel(eintraege.length, 'REGISTERED TESTS', 'var(--text)')
    + kachel(z.abgeschlossen || 0, 'COMPLETED', STATUS_FARBE.abgeschlossen)
    + kachel((z.laeuft || 0) + (z.eingefroren || 0) + (z.wartet || 0), 'OPEN', STATUS_FARBE.laeuft)
    + kachel(z.entwurf || 0, 'DRAFT', 'var(--ink-3)')
    + '</div>'
    + (policy.length ? abschnitt('THE POLICY',
      '<ol style="margin:0; padding-left:var(--sp-6); max-width:760px">' + policy.map((p) => '<li style="font-size:var(--t-body); color:var(--ink-2); line-height:var(--lh-prose); margin-bottom:var(--sp-3)">' + esc(p) + '</li>').join('') + '</ol>') : '')
    + hinweisZeile(payload.hinweis)
    + '<div style="height:20px"></div>'
    + eintraege.map(eintragKarte).join('')
    + (payload.register ? '<div style="font-size:var(--t-small); ' + MUTED + '; line-height:var(--lh-prose)">Register file: <span style="' + M + '">' + esc(payload.register) + '</span></div>' : '')
    + '</div>';
}
