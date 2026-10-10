// Thesis — die drei Hypothesen der Bachelorarbeit und die Schweizer
// Fallstudie, je eine Karte mit Frage, Verdikt, Diagrammen, Kennzahlen und
// der zugeklappten Methode.
//
// Liest public/data/thesis_results.json (app/thesis_results.py aus den
// Ergebnistabellen des Thesis-Repos). Jede Zahl kommt aus der Datei; diese
// Datei ordnet nur an. Diagramme aus charts.js, abhaengigkeitsfrei.

import { esc } from '../util.js';
import { diagramm, linien, kalibrierung } from '../charts.js';
import { MONO as M, KARTE } from '../ui.js';
import {
  MUTED, HR, karteKopf, methodeBlock, zahlenBlock, quelleLinks, basisZeile, seitenKopf,
  hinweisZeile, sprungliste, ohneNutzlastHtml, kachel, VERDIKT_FARBE
} from './study_blocks.js';

const DATEI = 'thesis_results.json';
const BEFEHL = 'python scripts/publish_research_pages.py --only thesis';

export function thesisAnker(s) {
  return 'research/thesis/' + String((s && s.id) || '').toLowerCase().replace(/[^a-z0-9_-]+/g, '-');
}

function raster(teile) {
  const inhalt = teile.filter(Boolean);
  if (!inhalt.length) return '';
  return '<div style="display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:var(--sp-4); margin-top:var(--sp-5)">' + inhalt.join('') + '</div>';
}

function breit(html) {
  return html ? '<div style="margin-top:var(--sp-4)">' + html + '</div>' : '';
}

// Datumsreihe fuer linien(): x-Beschriftung und Tagesabstand aus ISO-Daten.
function zeitachse(daten) {
  const ms0 = daten.length ? Date.parse(daten[0]) : 0;
  return {
    x: daten,
    xWerte: daten.map((t) => Math.round((Date.parse(t) - ms0) / 86400000))
  };
}

// ---- H1 -------------------------------------------------------------
function h1Diagramme(d) {
  const w = d.brier_wochen || {};
  const wochen = Array.isArray(w.x) && w.x.length >= 2
    ? linien(Object.assign({}, w, zeitachse(w.x)))
    : '';
  const kal = d.kalibrierung && typeof d.kalibrierung === 'object'
    ? Object.keys(d.kalibrierung).map((k) => {
      const set = d.kalibrierung[k];
      const n = (set.punkte || []).reduce((a, p) => a + (+p.n || 0), 0);
      return kalibrierung({ titel: set.label, punkte: set.punkte, hinweis: 'n ' + n + ' · ' + (set.punkte || []).length + ' bins' });
    }).join('')
    : '';
  return raster([diagramm(d.brier_quellen), null])
    + breit(wochen)
    + (kal ? '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:var(--ink-3); margin-top:var(--sp-5)">CALIBRATION ON THE 50 STATE MARKETS · predicted probability against realised frequency</div>'
      + '<div style="display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:var(--sp-4); margin-top:var(--sp-3)">' + kal + '</div>' : '')
    + breit(diagramm(d.umfragen_scopes));
}

// ---- H2 -------------------------------------------------------------
function h2Diagramme(d, ereignisse) {
  const pf = d.pfade || {};
  // Fuenf Farben, sieben Ereignisse: die drei gerichteten zuerst, dann die
  // groessten neutralen, bis die Palette voll ist. Was fehlt, sagt der Hinweis.
  let serien = Array.isArray(pf.serien) ? pf.serien.slice() : [];
  if (Array.isArray(ereignisse) && ereignisse.length === serien.length) {
    const rang = ereignisse.map((e, i) => ({ i, gerichtet: !!e.gerichtet, groesse: Math.abs((e.fenster || {}).primary_0d_to_1d || 0) }))
      .sort((a, b) => (b.gerichtet - a.gerichtet) || (b.groesse - a.groesse));
    serien = rang.map((r) => serien[r.i]);
  }
  const ausgelassen = Math.max(0, serien.length - 5);
  const pfade = serien.length
    ? linien(Object.assign({}, pf, { serien: serien.slice(0, 5), hinweis: ausgelassen ? 'directional events first; ' + ausgelassen + ' neutral event(s) in the table below' : pf.hinweis }))
    : '';
  return breit(diagramm(d.fenster)) + breit(pfade);
}

// ---- H3 -------------------------------------------------------------
function h3Diagramme(d) {
  return breit(linien(d.leadlag)) + raster([diagramm(d.granger), diagramm(d.tiers)]);
}

// ---- Swiss ----------------------------------------------------------
function swissDiagramme(d) {
  const p = d.preis || {};
  const kurve = Array.isArray(p.punkte) ? p.punkte.filter((q) => q && q.t && typeof q.wert === 'number') : [];
  let preis = '';
  if (kurve.length >= 2) {
    const achse = zeitachse(kurve.map((q) => q.t));
    const ref = p.referenz && typeof p.referenz.wert === 'number' ? Math.round(p.referenz.wert * 1000) / 10 : null;
    const marken = Array.isArray(p.marken) ? p.marken : [];
    const umfragen = kurve.map((q) => {
      const m = marken.find((mk) => mk && mk.t === q.t && typeof mk.wert === 'number');
      return m ? Math.round(m.wert * 1000) / 10 : null;
    });
    const serien = [
      { name: 'Polymarket Yes price', werte: kurve.map((q) => Math.round(q.wert * 1000) / 10) }
    ];
    if (ref !== null) serien.push({ name: p.referenz.label || 'official result', werte: kurve.map(() => ref) });
    if (umfragen.some((u) => typeof u === 'number')) serien.push({ name: 'Poll releases, Yes share', werte: umfragen });
    preis = linien({ titel: p.titel, einheit: '% Yes', hinweis: kurve.length + ' daily points · polls as single marks on their release day', x: achse.x, xWerte: achse.xWerte, serien });
  }
  return breit(preis) + raster([diagramm(d.quellen_fehler), null]) + breit(linien(d.antwort));
}

const DIAGRAMME = { h1: h1Diagramme, h2: (d, s) => h2Diagramme(d, s.ereignisse), h3: h3Diagramme, swiss: swissDiagramme };

function sektionKarte(s, i, repo) {
  const d = s.diagramme || {};
  const bauer = DIAGRAMME[s.id];
  const bilder = bauer ? bauer(d, s) : '';
  const quellen = (Array.isArray(s.quellen) ? s.quellen : []).map((q) => ({ pfad: q, text: q.split('/').pop(), repo: repo ? repo.replace(/\/?$/, '/blob/main/') : undefined }));
  return '<div id="' + esc(thesisAnker(s)) + '" style="' + KARTE + '; padding:var(--sp-6); margin-bottom:var(--sp-5); scroll-margin-top:16px">'
    + karteKopf(s.kapitel || ('SECTION ' + (i + 1)), s.frage, s.verdikt, s.verdikt_art)
    + bilder
    + '<div style="margin-top:var(--sp-5)">' + zahlenBlock(s.zahlen) + '</div>'
    + methodeBlock(s, 'thesis:' + s.id)
    + '<div style="' + HR + '; display:flex; align-items:center; justify-content:space-between; gap:var(--sp-5); flex-wrap:wrap">'
    + basisZeile(s.basis) + quelleLinks(quellen) + '</div>'
    + '</div>';
}

function thesisKopf(payload, study) {
  const t = payload.thesis || {};
  const z = payload.zaehler || {};
  const hyp = Array.isArray(t.hypothesen) ? t.hypothesen : [];
  const nicht = Array.isArray(t.nicht_behauptet) ? t.nicht_behauptet : [];
  const sektionen = Array.isArray(payload.sektionen) ? payload.sektionen : [];
  return seitenKopf(t.titel || study.title, payload.einleitung, study, payload)
    + (t.frage ? '<div style="font-size:var(--t-lead); color:var(--text); margin-top:var(--sp-5); line-height:var(--lh-snug); max-width:760px; font-weight:500">' + esc(t.frage) + '</div>' : '')
    + (t.hochschule ? '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-4); margin-top:var(--sp-3)">' + esc(t.hochschule) + (t.repo ? ' · <a href="' + esc(t.repo) + '" target="_blank" rel="noopener">thesis repository ↗</a>' : '') + '</div>' : '')
    + sprungliste(sektionen.map((s) => ({ anker: thesisAnker(s), label: s.kapitel || s.id, art: s.verdikt_art })))
    + '<div style="display:flex; gap:var(--sp-4); margin-top:var(--sp-5); flex-wrap:wrap">'
    + kachel(z.gesamt || sektionen.length, 'SECTIONS', 'var(--text)')
    + kachel(z.ja || 0, 'SUPPORTED', VERDIKT_FARBE.ja)
    + kachel(z.gemischt || 0, 'MIXED', VERDIKT_FARBE.gemischt)
    + '</div>'
    + (hyp.length || nicht.length
      ? '<div style="display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:var(--sp-4); margin-top:var(--sp-5)">'
        + (hyp.length ? '<div style="' + KARTE + '; padding:var(--sp-5)"><div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:var(--info)">THE THREE HYPOTHESES</div>'
          + hyp.map((h) => '<div style="font-size:var(--t-small); color:var(--ink-1); margin-top:var(--sp-3); line-height:var(--lh-prose)"><span style="' + M + '; color:var(--ink-3)">' + esc(h.id) + '</span> ' + esc(h.text) + '</div>').join('') + '</div>' : '')
        + (nicht.length ? '<div style="' + KARTE + '; padding:var(--sp-5)"><div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:var(--warn)">WHAT THE THESIS DOES NOT CLAIM</div>'
          + nicht.map((n) => '<div style="font-size:var(--t-small); color:var(--ink-1); margin-top:var(--sp-3); line-height:var(--lh-prose)">' + esc(n) + '</div>').join('') + '</div>' : '')
        + '</div>'
      : '')
    + hinweisZeile(payload.hinweis)
    + '<div style="height:20px"></div>';
}

export function renderThesis(payload, study) {
  if (!payload || !Array.isArray(payload.sektionen) || !payload.sektionen.length) {
    return ohneNutzlastHtml(study, DATEI, BEFEHL, payload);
  }
  const fehlend = Array.isArray(payload.fehlend) && payload.fehlend.length
    ? '<div style="' + M + '; font-size:var(--t-micro); color:var(--warn); margin-bottom:var(--sp-5)">' + esc(payload.fehlend.length + ' result table(s) missing from this build: ' + payload.fehlend.join(', ')) + '</div>'
    : '';
  const repo = payload.thesis && payload.thesis.repo ? String(payload.thesis.repo) : '';
  return '<div style="padding:var(--sp-6) var(--sp-6) var(--sp-7)">'
    + thesisKopf(payload, study)
    + fehlend
    + payload.sektionen.map((s, i) => sektionKarte(s, i, repo)).join('')
    + '<div style="font-size:var(--t-small); ' + MUTED + '; line-height:var(--lh-prose); max-width:760px">Every number on this page is read from the thesis result tables named under each card; the prose is the site\'s summary of the thesis chapters, not a quotation.</div>'
    + '</div>';
}
