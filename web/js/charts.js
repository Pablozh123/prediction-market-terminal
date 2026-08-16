// Gemeinsame SVG-Diagramme, abhaengigkeitsfrei wie der Rest des Terminals.
//
// Hierher umgezogen aus pages/microstructure_page.js, damit auch die anderen
// Seiten dieselben Formen zeichnen koennen statt eigene zu erfinden. Es gilt
// weiter die eine Regel des Frontends: keine Funktion hier erzeugt einen
// Verlauf ohne eine echte Serie dahinter — ohne Punkte kommt ein leerer
// String zurueck, und der Aufrufer zeigt seinen Leerzustand.

import { esc } from './util.js';

const M = "font-family:'JetBrains Mono',monospace";
const CARD = 'background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:12px';

const BALKEN_FARBE = { gewinn: '#C8F542', kosten: '#FF4545', summe: '#4F8EF7' };

// Diagrammgeometrie des Balken- und Intervalldiagramms. Labelspalte links,
// Balken rechts.
const BREITE = 640;
const LABEL_X = 196;
const PLOT_L = LABEL_X + 12;
// Rechts genug Platz fuer ein Intervall-Label wie "55.2 … 55.5" — mit 58px
// wurde es am SVG-Rand abgeschnitten.
const PLOT_R = BREITE - 96;
const ZEILE = 30;

export function fmtZahl(wert) {
  if (wert === null || wert === undefined) return '—';
  if (Array.isArray(wert)) return wert.map(fmtZahl).join(' to ');
  if (typeof wert !== 'number') return String(wert);
  const abs = Math.abs(wert);
  if (abs >= 10000) return wert.toLocaleString('en-US', { maximumFractionDigits: 0 });
  if (abs >= 100) return wert.toLocaleString('en-US', { maximumFractionDigits: 1 });
  if (abs >= 1) return String(Math.round(wert * 100) / 100);
  return String(Math.round(wert * 10000) / 10000);
}

/** Alle Zahlenwerte eines Diagramms, damit die Skala beide Vorzeichen fasst. */
function werteVon(dia) {
  const raus = [];
  (dia.punkte || []).forEach((p) => {
    if (Array.isArray(p.werte)) p.werte.forEach((w) => { if (typeof w === 'number') raus.push(w); });
    if (typeof p.wert === 'number') raus.push(p.wert);
    if (typeof p.von === 'number') raus.push(p.von);
    if (typeof p.bis === 'number') raus.push(p.bis);
  });
  if (typeof dia.referenz === 'number') raus.push(dia.referenz);
  return raus;
}

function skalaVon(dia) {
  const werte = werteVon(dia);
  let min = Math.min(0, ...werte);
  let max = Math.max(0, ...werte);
  // Liegt alles weit ueber null — etwa Trefferquoten um 55 mit Referenz 50 —
  // wuerde die Nullverankerung jede Differenz auf Strichbreite stauchen.
  // Dann zaehlt der Referenzwert als Anker statt der Null.
  if (typeof dia.referenz === 'number' && Math.min(...werte) > 0 && dia.referenz > 0) {
    min = Math.min(...werte, dia.referenz);
    max = Math.max(...werte, dia.referenz);
  }
  if (min === max) { max = min + 1; }
  const luft = (max - min) * 0.08;
  min -= luft; max += luft;
  const spanne = max - min;
  return {
    min, max,
    x: (w) => PLOT_L + ((w - min) / spanne) * (PLOT_R - PLOT_L)
  };
}

function achse(sk, dia, hoehe) {
  let out = '';
  const nullX = sk.x(0);
  if (sk.min < 0 && sk.max > 0) {
    out += '<line x1="' + nullX + '" y1="6" x2="' + nullX + '" y2="' + (hoehe - 22)
      + '" stroke="rgba(255,255,255,.28)" stroke-width="1" />';
  }
  if (typeof dia.referenz === 'number' && dia.referenz !== 0) {
    const rx = sk.x(dia.referenz);
    out += '<line x1="' + rx + '" y1="6" x2="' + rx + '" y2="' + (hoehe - 22)
      + '" stroke="rgba(255,255,255,.35)" stroke-width="1" stroke-dasharray="4 4" />';
    if (dia.referenz_label) {
      out += '<text x="' + rx + '" y="' + (hoehe - 8) + '" fill="rgba(255,255,255,.45)" '
        + 'font-size="10" font-family="JetBrains Mono, monospace" text-anchor="middle">'
        + esc(dia.referenz_label) + '</text>';
    }
  }
  return out;
}

function labelText(text, y) {
  return '<text x="' + LABEL_X + '" y="' + (y + 4) + '" fill="rgba(255,255,255,.72)" font-size="11.5" '
    + 'font-family="JetBrains Mono, monospace" text-anchor="end">' + esc(text) + '</text>';
}

function wertText(text, x, y, farbe) {
  return '<text x="' + x + '" y="' + (y + 4) + '" fill="' + farbe + '" font-size="11.5" '
    + 'font-family="JetBrains Mono, monospace">' + esc(text) + '</text>';
}

/** Balken- und Intervalldiagramm. Eine Zeile je Punkt, Nulllinie wenn noetig. */
export function diagramm(dia) {
  if (!dia || !dia.punkte || !dia.punkte.length) return '';
  const gruppen = Array.isArray(dia.gruppen) ? dia.gruppen : null;
  const zeilen = gruppen ? dia.punkte.length * gruppen.length : dia.punkte.length;
  const hoehe = zeilen * ZEILE + 40;
  const sk = skalaVon(dia);
  let y = 18;
  let koerper = '';

  dia.punkte.forEach((p) => {
    if (gruppen && Array.isArray(p.werte)) {
      p.werte.forEach((w, i) => {
        const farbe = BALKEN_FARBE[p.art] || '#4F8EF7';
        const x0 = sk.x(0);
        const x1 = sk.x(w);
        koerper += labelText(gruppen[i] + ' · ' + p.label, y);
        koerper += '<rect x="' + Math.min(x0, x1) + '" y="' + (y - 8) + '" width="' + Math.abs(x1 - x0)
          + '" height="16" rx="3" fill="' + farbe + '" fill-opacity="' + (i === 0 ? '.45' : '.95') + '" />';
        koerper += wertText(fmtZahl(w), PLOT_R + 8, y, 'rgba(255,255,255,.75)');
        y += ZEILE;
      });
      return;
    }

    koerper += labelText(p.label, y);
    if (typeof p.von === 'number' && typeof p.bis === 'number') {
      const xa = sk.x(p.von);
      const xb = sk.x(p.bis);
      const xm = sk.x(p.wert);
      const beruehrt = p.von <= (dia.referenz || 0) && p.bis >= (dia.referenz || 0);
      const farbe = beruehrt ? '#F5A623' : '#4F8EF7';
      koerper += '<line x1="' + xa + '" y1="' + y + '" x2="' + xb + '" y2="' + y
        + '" stroke="' + farbe + '" stroke-width="3" stroke-linecap="round" />';
      koerper += '<line x1="' + xa + '" y1="' + (y - 6) + '" x2="' + xa + '" y2="' + (y + 6)
        + '" stroke="' + farbe + '" stroke-width="2" />';
      koerper += '<line x1="' + xb + '" y1="' + (y - 6) + '" x2="' + xb + '" y2="' + (y + 6)
        + '" stroke="' + farbe + '" stroke-width="2" />';
      koerper += '<circle cx="' + xm + '" cy="' + y + '" r="4" fill="' + farbe + '" />';
      koerper += wertText(fmtZahl(p.von) + ' … ' + fmtZahl(p.bis), PLOT_R + 8, y, 'rgba(255,255,255,.75)');
    } else if (typeof p.wert === 'number') {
      const farbe = BALKEN_FARBE[p.art] || (p.wert < 0 ? '#FF4545' : '#C8F542');
      // Auf einer referenzverankerten Skala liegt die Null links ausserhalb;
      // der Balken beginnt dann an der Referenz, denn die Abweichung von ihr
      // ist die Aussage.
      const anker = sk.min > 0 && typeof dia.referenz === 'number' ? dia.referenz : 0;
      const x0 = sk.x(anker);
      const x1 = sk.x(p.wert);
      koerper += '<rect x="' + Math.min(x0, x1) + '" y="' + (y - 9) + '" width="' + Math.abs(x1 - x0)
        + '" height="18" rx="3" fill="' + farbe + '" fill-opacity=".92" />';
      koerper += wertText(fmtZahl(p.wert), PLOT_R + 8, y, 'rgba(255,255,255,.78)');
    }
    y += ZEILE;
  });

  return '<div style="' + CARD + '; padding:14px 16px 10px">'
    + '<div style="' + M + '; font-size:10px; letter-spacing:.13em; color:rgba(255,255,255,.5); margin-bottom:4px">'
    + esc(dia.titel || '') + (dia.einheit ? ' · ' + esc(dia.einheit) : '') + '</div>'
    + '<svg width="100%" viewBox="0 0 ' + BREITE + ' ' + hoehe + '" role="img" aria-label="' + esc(dia.titel || 'chart') + '">'
    + achse(sk, dia, hoehe) + koerper + '</svg></div>';
}

/** Treppenkurve fuer eine kumulierte Serie, ein Punkt je Schritt.
 *
 *  k: { titel, einheit, hinweis, punkte: [{ label, wert }] }. Unter zwei
 *  Punkten gibt es keine Kurve — ein einzelner Wert ist kein Verlauf.
 */
export function stepKurve(k) {
  if (!k || !Array.isArray(k.punkte) || k.punkte.length < 2) return '';
  const B = 900, H = 200;
  const L = 14, R = B - 76, TOP = 14, BOT = H - 26;
  const werte = k.punkte.map((p) => +p.wert);
  let min = Math.min(0, ...werte);
  let max = Math.max(0, ...werte);
  if (min === max) max = min + 1;
  const luft = (max - min) * 0.08;
  min -= luft; max += luft;
  const y = (w) => BOT - ((w - min) / (max - min)) * (BOT - TOP);
  const x = (i) => L + (i * (R - L)) / (k.punkte.length - 1);

  const letzte = werte[werte.length - 1];
  const farbe = k.farbe || (letzte >= 0 ? '#C8F542' : '#FF4545');

  // Treppe: erst waagerecht zum naechsten Schritt, dann senkrecht auf ihn.
  let pfad = 'M ' + x(0).toFixed(1) + ' ' + y(werte[0]).toFixed(1);
  for (let i = 1; i < werte.length; i += 1) {
    pfad += ' H ' + x(i).toFixed(1) + ' V ' + y(werte[i]).toFixed(1);
  }
  let marken = '';
  werte.forEach((w, i) => {
    marken += '<circle cx="' + x(i).toFixed(1) + '" cy="' + y(w).toFixed(1) + '" r="2.6" fill="' + farbe + '" />';
  });

  let nulllinie = '';
  if (min < 0 && max > 0) {
    nulllinie = '<line x1="' + L + '" y1="' + y(0).toFixed(1) + '" x2="' + R + '" y2="' + y(0).toFixed(1)
      + '" stroke="rgba(255,255,255,.25)" stroke-width="1" stroke-dasharray="4 4" />';
  }

  const endLabel = '<text x="' + (R + 8) + '" y="' + (y(letzte) + 4).toFixed(1) + '" fill="' + farbe
    + '" font-size="12" font-family="JetBrains Mono, monospace">' + esc(fmtZahl(letzte)) + '</text>';
  const xLabels = '<text x="' + L + '" y="' + (H - 8) + '" fill="rgba(255,255,255,.4)" font-size="10" '
    + 'font-family="JetBrains Mono, monospace">' + esc(String(k.punkte[0].label || '')) + '</text>'
    + '<text x="' + R + '" y="' + (H - 8) + '" fill="rgba(255,255,255,.4)" font-size="10" '
    + 'font-family="JetBrains Mono, monospace" text-anchor="end">' + esc(String(k.punkte[k.punkte.length - 1].label || '')) + '</text>';

  return '<div style="' + CARD + '; padding:14px 16px 10px">'
    + '<div style="display:flex; align-items:baseline; justify-content:space-between; gap:14px; flex-wrap:wrap; margin-bottom:4px">'
    + '<div style="' + M + '; font-size:10px; letter-spacing:.13em; color:rgba(255,255,255,.5)">'
    + esc(k.titel || '') + (k.einheit ? ' · ' + esc(k.einheit) : '') + '</div>'
    + (k.hinweis ? '<div style="' + M + '; font-size:10px; color:rgba(255,255,255,.38)">' + esc(k.hinweis) + '</div>' : '')
    + '</div>'
    + '<svg width="100%" viewBox="0 0 ' + B + ' ' + H + '" preserveAspectRatio="none" role="img" aria-label="' + esc(k.titel || 'series') + '">'
    + nulllinie
    + '<path d="' + pfad + '" fill="none" stroke="' + farbe + '" stroke-width="2" />'
    + marken + endLabel + xLabels
    + '</svg></div>';
}
