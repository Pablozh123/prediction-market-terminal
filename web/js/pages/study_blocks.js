// Die Bausteine einer Studienkarte, wie die Thesis-, Reddit-, Preregistrierungs-
// und Literaturseite sie teilen: Verdiktmarke, Analysefelder, Lesarten,
// Zahlenblock, zugaengliche Tabelle, Quellenlinks und die drei Zustaende
// ohne Nutzlast (laedt, fehlt, Abruf gescheitert).
//
// Die Microstructure-Seite traegt dieselben Formen in eigener Fassung; sie
// bleibt unangetastet, bis ihre Tests auf diese Datei umziehen. Hier gilt
// dieselbe Regel wie dort: keine Zahl ohne Nutzlast, jede Zahl aus ihr.

import { esc, stempelBlock } from '../util.js';
import { fmtZahl } from '../charts.js';
import { MONO as M, KARTE } from '../ui.js';

export const MUTED = 'color:var(--ink-4)';
export const HR = 'border-top:1px solid var(--line-3); margin-top:var(--sp-6); padding-top:var(--sp-5)';
export const REPO_BLOB = 'https://github.com/Pablozh123/prediction-market-terminal/blob/main/';

// Fuenf Verdiktarten. 'gemischt' ist neu gegenueber der Microstructure-Seite:
// die Thesis stuetzt H1 in einem Ausschnitt und nicht im Ganzen, und ein
// halbes Ja als CONFIRMED zu fuehren waere die Uebertreibung, die das
// Register verbietet.
export const VERDIKT_FARBE = {
  ja: 'var(--accent)', nein: 'var(--neg-soft)', offen: 'var(--warn)', gemischt: 'var(--info)', kontrolle: 'var(--cat-teal)'
};
export const VERDIKT_TEXT = {
  ja: 'SUPPORTED', nein: 'NOT SUPPORTED', offen: 'NOT IDENTIFIED', gemischt: 'MIXED', kontrolle: 'CONTROL'
};
const DEUTUNG_FARBE = { lesart: 'var(--accent)', gegenlesart: 'var(--info)', grenze: 'var(--muted)' };

export function verdiktMarke(art) {
  const farbe = VERDIKT_FARBE[art] || 'var(--muted)';
  return '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:' + farbe
    + '; border:1px solid color-mix(in srgb, ' + farbe + ' 33%, transparent); border-radius:var(--r-control); padding:var(--sp-3) var(--sp-4); white-space:nowrap">'
    + (VERDIKT_TEXT[art] || 'RESULT') + '</div>';
}

export function abschnitt(titel, inhalt, zusatz) {
  if (!inhalt) return '';
  return '<div style="' + HR + '">'
    + '<h4 style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:var(--info); margin:0 0 var(--sp-4); font-weight:400">'
    + esc(titel) + (zusatz ? ' <span style="color:var(--ink-4)">' + esc(zusatz) + '</span>' : '')
    + '</h4>' + inhalt + '</div>';
}

export function kicker(text, farbe) {
  return '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:' + (farbe || 'var(--info)') + '; margin:var(--sp-6) 0 var(--sp-4)">' + esc(text) + '</div>';
}

export function analyseBlock(analyse) {
  if (!analyse || !analyse.length) return '';
  return '<div style="display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:var(--sp-1); '
    + 'background:rgba(var(--ink),.07); border:1px solid var(--line-3); border-radius:var(--r-panel); overflow:hidden">'
    + analyse.map((a) =>
      '<div style="background:var(--panel); padding:var(--sp-5)">'
      + '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:var(--ink-3)">' + esc(a.titel) + '</div>'
      + '<div style="font-size:var(--t-small); color:var(--ink-1); margin-top:var(--sp-3); line-height:var(--lh-prose)">' + esc(a.text) + '</div></div>'
    ).join('')
    + '</div>';
}

export function deutungBlock(interpretation) {
  if (!interpretation || !interpretation.length) return '';
  return interpretation.map((i) => {
    const farbe = DEUTUNG_FARBE[i.art] || 'var(--muted)';
    return '<div style="border-left:2px solid color-mix(in srgb, ' + farbe + ' 40%, transparent); padding:var(--sp-1) 0 var(--sp-1) var(--sp-5); margin-bottom:var(--sp-5)">'
      + '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:' + farbe + '">' + esc(i.titel) + '</div>'
      + '<div style="font-size:var(--t-body); color:var(--ink-2); margin-top:var(--sp-3); line-height:var(--lh-prose); max-width:720px">' + esc(i.text) + '</div></div>';
  }).join('');
}

export function zahlenBlock(zahlen) {
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

// Eine Tabelle mit ARIA-Rollen: Kopf, Zeilen, Zellen. Die erste Spalte ist
// Text und linksbuendig, alle weiteren Zahlen und rechtsbuendig; lange Zellen
// brechen um statt abgeschnitten zu werden, weil hier Fragen und Titel
// stehen, keine Ticker.
export function tabelleBlock(tab) {
  if (!tab || !Array.isArray(tab.zeilen) || !tab.zeilen.length || !Array.isArray(tab.spalten)) return '';
  const kopf = tab.spalten.map((c, i) =>
    '<div role="columnheader" style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps); color:var(--ink-3); '
    + 'text-align:' + (i === 0 ? 'left' : 'right') + '; padding:var(--sp-3) var(--sp-4); border-bottom:1px solid var(--line-2)">' + esc(c) + '</div>').join('');
  const koerper = tab.zeilen.map((zeile) =>
    '<div role="row" style="display:contents">' + zeile.map((z, i) =>
      '<div role="cell" style="' + (i === 0 ? 'font-size:var(--t-small); color:var(--ink-2)' : M + '; font-size:var(--t-small); color:var(--ink-3); white-space:nowrap')
      + '; text-align:' + (i === 0 ? 'left' : 'right') + '; padding:var(--sp-3) var(--sp-4); border-bottom:1px solid var(--line-3); line-height:var(--lh-snug)">' + esc(String(z)) + '</div>').join('')
    + '</div>').join('');
  return '<div style="margin-top:var(--sp-5)">'
    + '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:var(--ink-4)">' + esc(tab.titel) + ' · ' + tab.zeilen.length + ' rows</div>'
    + '<div style="overflow-x:auto; border:1px solid var(--line-3); border-radius:var(--r-control); margin-top:var(--sp-3)">'
    + '<div role="table" aria-label="' + esc(tab.titel) + '" style="display:grid; grid-template-columns:minmax(200px,2fr) repeat(' + (tab.spalten.length - 1) + ', minmax(72px,auto)); min-width:100%">'
    + '<div role="row" style="display:contents">' + kopf + '</div>' + koerper + '</div></div>'
    + (tab.hinweis ? '<div style="font-size:var(--t-small); ' + MUTED + '; padding:var(--sp-3) var(--sp-1) 0; line-height:var(--lh-prose)">' + esc(tab.hinweis) + '</div>' : '')
    + '</div>';
}

// Methode, Klartext, Lesarten und Tabellen zugeklappt unter dem Befund.
export function methodeBlock(s, id) {
  const tabellen = (Array.isArray(s.tabellen) ? s.tabellen : []).map(tabelleBlock).join('');
  const inhalt = abschnitt('WHAT WAS ANALYSED', analyseBlock(s.analyse))
    + abschnitt('WHAT THE NUMBERS SAY', s.einfach
      ? '<div style="font-size:var(--t-body); color:var(--ink-2); line-height:var(--lh-prose); max-width:760px">' + esc(s.einfach) + '</div>' : '')
    + abschnitt('HOW TO READ IT', deutungBlock(s.interpretation))
    + tabellen;
  if (!inhalt) return '';
  return '<details data-key="method:' + esc(String(id || s.id || '')) + '" style="' + KARTE + '; margin-top:var(--sp-5); overflow:hidden">'
    + '<summary style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps); color:var(--ink-3); padding:var(--sp-4) var(--sp-5); cursor:pointer; list-style:none">'
    + '▸ METHOD, HOW TO READ IT' + (tabellen ? ' &amp; EVERY ROW' : '')
    + ' <span style="color:var(--ink-4)">· what was analysed, what else fits the numbers' + (tabellen ? ', the tables behind them' : '') + '</span></summary>'
    + '<div style="padding:0 var(--sp-5) var(--sp-5); border-top:1px solid var(--line-3)">' + inhalt + '</div>'
    + '</details>';
}

// Der Kopf einer Karte: Nummer oder Kapitel, Frage, Marke, Verdiktsatz.
export function karteKopf(nr, frage, verdikt, art) {
  const farbe = VERDIKT_FARBE[art] || 'var(--muted)';
  return '<div style="display:flex; align-items:flex-start; justify-content:space-between; gap:var(--sp-5); flex-wrap:wrap">'
    + '<div style="flex:1; min-width:260px">'
    + '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:var(--ink-4)">' + esc(nr) + '</div>'
    + '<h3 style="font-size:var(--t-head); font-weight:600; margin-top:var(--sp-3); line-height:var(--lh-tight)">' + esc(frage) + '</h3></div>'
    + verdiktMarke(art) + '</div>'
    + '<div style="font-size:var(--t-lead); color:' + farbe + '; margin-top:var(--sp-4); line-height:var(--lh-snug); font-weight:500; max-width:760px">' + esc(verdikt) + '</div>';
}

// Quellenlinks: Pfade in diesem Repo werden zu GitHub-Links, absolute
// Adressen bleiben, wie sie sind.
export function quelleLinks(eintraege) {
  const teile = (eintraege || []).filter((e) => e && e.pfad).map((e) => {
    const href = /^https?:\/\//.test(e.pfad) ? e.pfad : (e.repo || REPO_BLOB) + e.pfad;
    return '<a href="' + esc(href) + '" target="_blank" rel="noopener" style="' + M + '; font-size:var(--t-micro); color:var(--info); text-decoration:none; '
      + 'border:1px solid rgba(var(--info-rgb),.35); border-radius:var(--r-control); padding:var(--sp-2) var(--sp-3)">' + esc(e.text) + ' ↗</a>';
  });
  if (!teile.length) return '';
  return '<div style="display:flex; gap:var(--sp-3); flex-wrap:wrap; align-items:center">' + teile.join('') + '</div>';
}

export function basisZeile(basis) {
  if (!basis) return '';
  const teile = [];
  if (basis.beobachtungen) teile.push(Number(basis.beobachtungen).toLocaleString('en-US') + ' observations');
  if (basis.snapshots) teile.push(Number(basis.snapshots).toLocaleString('en-US') + ' snapshots');
  if (basis.maerkte) teile.push(Number(basis.maerkte).toLocaleString('en-US') + ' markets');
  if (basis.tage) teile.push(basis.tage + ' days');
  if (basis.fenster) teile.push(basis.fenster);
  if (!teile.length) return '';
  return '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-3)">DATA · ' + esc(teile.join(' · ')) + '</div>';
}

// Der Seitenkopf unter dem Brotkrumen: Titel, Einleitung, Stempel.
export function seitenKopf(titel, einleitung, study, payload) {
  return '<div style="display:flex; align-items:flex-start; justify-content:space-between; gap:var(--sp-6); flex-wrap:wrap">'
    + '<div style="max-width:760px">'
    + '<h2 style="font-size:var(--t-head); font-weight:600; margin:0">' + esc(titel) + '</h2>'
    + (einleitung ? '<div style="font-size:var(--t-body); ' + MUTED + '; margin-top:var(--sp-3); line-height:var(--lh-prose)">' + esc(einleitung) + '</div>' : '')
    + '</div>' + stempelBlock(study, payload) + '</div>';
}

export function hinweisZeile(text) {
  if (!text) return '';
  return '<div style="font-size:var(--t-small); color:var(--ink-3); margin-top:var(--sp-5); line-height:var(--lh-prose); max-width:760px; '
    + 'border-left:2px solid var(--line-1); padding-left:var(--sp-4)">' + esc(text) + '</div>';
}

// Sprungliste zu den Ankern einer Seite.
export function sprungliste(eintraege) {
  if (!eintraege || !eintraege.length) return '';
  return '<div style="display:flex; gap:var(--sp-3); flex-wrap:wrap; margin-top:var(--sp-4)">'
    + eintraege.map((e) => '<a href="#' + esc(e.anker) + '" style="' + M + '; font-size:var(--t-micro); color:var(--ink-2); text-decoration:none; '
      + 'border:1px solid var(--line-1); border-left:2px solid ' + (VERDIKT_FARBE[e.art] || 'var(--muted)') + '; border-radius:var(--r-control); padding:var(--sp-2) var(--sp-3); white-space:nowrap">'
      + esc(e.label) + '</a>').join('')
    + '</div>';
}

// Ohne Nutzlast: welche Datei fehlt und womit sie entsteht. Ein gescheiterter
// Abruf sagt das, statt wie eine leere Datei auszusehen.
export function ohneNutzlastHtml(study, datei, befehl, payload) {
  const fehler = payload && payload._quelle === 'fehler';
  return '<div style="padding:var(--sp-6)">'
    + '<div style="' + KARTE + '; padding:var(--sp-6); max-width:720px">'
    + '<h2 style="font-size:var(--t-lead); font-weight:600">' + esc(study && study.title ? study.title : 'Study') + '</h2>'
    + (fehler
      ? '<div style="font-size:var(--t-body); color:var(--warn); margin-top:var(--sp-4); line-height:var(--lh-prose)">The request for <span style="' + M + '">public/data/' + esc(datei) + '</span> failed'
        + (payload._fehler ? ' (' + esc(String(payload._fehler)) + ')' : '') + '. Nothing is shown in its place.</div>'
      : '<div style="font-size:var(--t-body); ' + MUTED + '; margin-top:var(--sp-4); line-height:var(--lh-prose)">No published data for this page yet. It reads '
        + '<span style="' + M + '">public/data/' + esc(datei) + '</span>, written by <span style="' + M + '">' + esc(befehl) + '</span>. '
        + 'Nothing is shown here rather than a placeholder.</div>')
    + '</div></div>';
}

export function kachel(wert, text, farbe) {
  return '<div style="' + KARTE + '; padding:var(--sp-4) var(--sp-5); min-width:118px">'
    + '<div style="' + M + '; font-size:var(--t-head); color:' + (farbe || 'var(--text)') + '">' + esc(String(wert)) + '</div>'
    + '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:var(--ink-3); margin-top:var(--sp-2)">' + esc(text) + '</div></div>';
}
