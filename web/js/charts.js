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
      out += '<text x="' + rx + '" y="' + (hoehe - 8) + '" fill="rgba(255,255,255,.6)" '
        + 'font-size="11" font-family="JetBrains Mono, monospace" text-anchor="middle">'
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
      // p.farbe und p.text lassen den Aufrufer die Deutung setzen: eine
      // Hantel (zwei Lesarten derselben Zahl) faerbt nach dem Endwert und
      // beschriftet ihn, nicht die Spanne. Ohne beide bleibt es das alte
      // Intervall mit Referenzfaerbung.
      const farbe = p.farbe || (beruehrt ? '#F5A623' : '#4F8EF7');
      koerper += '<line x1="' + xa + '" y1="' + y + '" x2="' + xb + '" y2="' + y
        + '" stroke="' + farbe + '" stroke-width="3" stroke-linecap="round" stroke-opacity="' + (p.farbe ? '.45' : '1') + '" />';
      koerper += '<line x1="' + xa + '" y1="' + (y - 6) + '" x2="' + xa + '" y2="' + (y + 6)
        + '" stroke="' + farbe + '" stroke-width="2" />';
      koerper += '<line x1="' + xb + '" y1="' + (y - 6) + '" x2="' + xb + '" y2="' + (y + 6)
        + '" stroke="' + farbe + '" stroke-width="2" />';
      koerper += '<circle cx="' + xm + '" cy="' + y + '" r="4.5" fill="' + farbe + '" />';
      koerper += wertText(p.text || (fmtZahl(p.von) + ' … ' + fmtZahl(p.bis)), PLOT_R + 8, y, 'rgba(255,255,255,.75)');
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
    + '<div style="' + M + '; font-size:11px; letter-spacing:.13em; color:rgba(255,255,255,.5); margin-bottom:4px">'
    + esc(dia.titel || '') + (dia.einheit ? ' · ' + esc(dia.einheit) : '') + '</div>'
    + '<svg width="100%" viewBox="0 0 ' + BREITE + ' ' + hoehe + '" role="img" aria-label="' + esc(dia.titel || 'chart') + '">'
    + achse(sk, dia, hoehe) + koerper + '</svg></div>';
}

// Serienfarben fuer Mehrlinien-Diagramme: die vier Grundfarben des Terminals
// und ihre gedaempften Verwandten, wie ACHSEN_FARBE auf der Postmortem-Seite.
export const SERIEN_FARBEN = ['#C8F542', '#4F8EF7', '#F5A623', '#FF7A7A', '#7DE2D1', '#C792EA', '#9AB0FF', '#FFD166', '#95A0AB'];

/** Mehrere Linien ueber einer gemeinsamen Kategorienachse.
 *
 *  k: { titel, einheit, hinweis, x: ['T-30', 'T-14', ...],
 *       serien: [{ name, werte: [zahl|null, ...], farbe? }], y_label? }
 *  Ein null in werte unterbricht die Linie an der Stelle statt sie zu
 *  interpolieren — wo kein Wert ist, ist auch kein Strich. Unter zwei
 *  gueltigen Punkten in allen Serien gibt es kein Diagramm.
 */
export function linien(k) {
  if (!k || !Array.isArray(k.x) || k.x.length < 2 || !Array.isArray(k.serien)) return '';
  const serien = k.serien.filter((s) => s && Array.isArray(s.werte) && s.werte.some((w) => typeof w === 'number'));
  const gueltig = serien.reduce((a, s) => a + s.werte.filter((w) => typeof w === 'number').length, 0);
  if (!serien.length || gueltig < 2) return '';
  const B = 640, H = 230;
  const L = 52, R = B - 18, TOP = 16, BOT = H - 30;
  const alle = [];
  serien.forEach((s) => s.werte.forEach((w) => { if (typeof w === 'number') alle.push(w); }));
  let min = Math.min(0, ...alle);
  let max = Math.max(...alle);
  if (min === max) max = min + 1;
  const luft = (max - min) * 0.08;
  max += luft;
  const y = (w) => BOT - ((w - min) / (max - min)) * (BOT - TOP);
  const x = (i) => L + (i * (R - L)) / (k.x.length - 1);

  let raster = '';
  [0, 0.5, 1].forEach((f) => {
    const w = min + (max - min) * f;
    raster += '<line x1="' + L + '" y1="' + y(w).toFixed(1) + '" x2="' + R + '" y2="' + y(w).toFixed(1)
      + '" stroke="rgba(255,255,255,' + (f === 0 ? '.18' : '.07') + ')" stroke-width="1" />'
      + '<text x="' + (L - 6) + '" y="' + (y(w) + 4).toFixed(1) + '" fill="rgba(255,255,255,.6)" font-size="11" '
      + 'font-family="JetBrains Mono, monospace" text-anchor="end">' + esc(fmtZahl(Math.round(w * 1000) / 1000)) + '</text>';
  });
  let xLabels = '';
  k.x.forEach((label, i) => {
    xLabels += '<text x="' + x(i).toFixed(1) + '" y="' + (H - 10) + '" fill="rgba(255,255,255,.6)" font-size="11" '
      + 'font-family="JetBrains Mono, monospace" text-anchor="middle">' + esc(String(label)) + '</text>';
  });
  let pfade = '';
  let legende = '';
  serien.forEach((s, si) => {
    const farbe = s.farbe || SERIEN_FARBEN[si % SERIEN_FARBEN.length];
    let d = '';
    let offen = false;
    s.werte.forEach((w, i) => {
      if (typeof w !== 'number') { offen = false; return; }
      d += (offen ? ' L ' : ' M ') + x(i).toFixed(1) + ' ' + y(w).toFixed(1);
      offen = true;
      pfade += '<circle cx="' + x(i).toFixed(1) + '" cy="' + y(w).toFixed(1) + '" r="3" fill="' + farbe + '">'
        + '<title>' + esc(s.name + ' · ' + k.x[i] + ' · ' + fmtZahl(w)) + '</title></circle>';
    });
    if (d) pfade += '<path d="' + d.trim() + '" fill="none" stroke="' + farbe + '" stroke-width="1.8" />';
    legende += '<div style="display:flex; align-items:center; gap:6px; ' + M + '; font-size:11px; color:rgba(255,255,255,.65)">'
      + '<span style="display:inline-block; width:14px; height:3px; background:' + farbe + '; border-radius:2px"></span>'
      + esc(s.name) + '</div>';
  });

  return '<div style="' + CARD + '; padding:14px 16px 10px">'
    + '<div style="display:flex; align-items:baseline; justify-content:space-between; gap:14px; flex-wrap:wrap; margin-bottom:4px">'
    + '<div style="' + M + '; font-size:11px; letter-spacing:.13em; color:rgba(255,255,255,.5)">'
    + esc(k.titel || '') + (k.einheit ? ' · ' + esc(k.einheit) : '') + '</div>'
    + (k.hinweis ? '<div style="' + M + '; font-size:11px; color:rgba(255,255,255,.55)">' + esc(k.hinweis) + '</div>' : '')
    + '</div>'
    + '<div style="display:flex; gap:12px; flex-wrap:wrap; margin:4px 0 6px">' + legende + '</div>'
    + '<svg width="100%" viewBox="0 0 ' + B + ' ' + H + '" role="img" aria-label="' + esc(k.titel || 'lines') + '">'
    + raster + xLabels + pfade + '</svg></div>';
}

/** Kalibrierung: vorhergesagte Wahrscheinlichkeit gegen realisierte Haeufigkeit.
 *
 *  k: { titel, hinweis, punkte: [{ vorhergesagt, realisiert, n, ci?: [lo, hi] }] }
 *  Quadrat mit Diagonale; ein Punkt je Bin, Radius nach n, Bernstein wenn das
 *  Intervall der realisierten Quote die Vorhersage nicht einschliesst. Ohne
 *  Punkte kein Diagramm.
 */
export function kalibrierung(k) {
  if (!k || !Array.isArray(k.punkte)) return '';
  const punkte = k.punkte.filter((p) => p && typeof p.vorhergesagt === 'number' && typeof p.realisiert === 'number');
  if (!punkte.length) return '';
  const S = 200, PAD = 22;
  const pos = (v) => PAD + Math.max(0, Math.min(1, v)) * (S - 2 * PAD);
  const nMax = Math.max(1, ...punkte.map((p) => +p.n || 0));
  const gesamt = punkte.reduce((a, p) => a + (+p.n || 0), 0);
  let marken = '';
  let linie = '';
  punkte.slice().sort((a, b) => a.vorhergesagt - b.vorhergesagt).forEach((p, i) => {
    const cx = pos(p.vorhergesagt), cy = S - pos(p.realisiert);
    const ci = Array.isArray(p.ci) && p.ci.length === 2 ? p.ci : null;
    const daneben = ci && (ci[0] > p.vorhergesagt || ci[1] < p.vorhergesagt);
    const farbe = daneben ? '#F5A623' : '#4F8EF7';
    const r = 2.5 + 4.5 * Math.sqrt((+p.n || 0) / nMax);
    linie += (i === 0 ? 'M ' : ' L ') + cx.toFixed(1) + ' ' + cy.toFixed(1);
    if (ci) {
      marken += '<line x1="' + cx.toFixed(1) + '" y1="' + (S - pos(ci[0])).toFixed(1) + '" x2="' + cx.toFixed(1)
        + '" y2="' + (S - pos(ci[1])).toFixed(1) + '" stroke="' + farbe + '" stroke-opacity=".45" stroke-width="1" />';
    }
    marken += '<circle cx="' + cx.toFixed(1) + '" cy="' + cy.toFixed(1) + '" r="' + r.toFixed(1) + '" fill="' + farbe + '" fill-opacity=".9">'
      + '<title>' + esc('predicted ' + Math.round(p.vorhergesagt * 100) + '% · realised ' + Math.round(p.realisiert * 100) + '% · n ' + (p.n != null ? p.n : '—')) + '</title></circle>';
  });
  const achse = 'fill="rgba(255,255,255,.6)" font-size="10.5" font-family="JetBrains Mono, monospace"';
  // Axis lettering that survives the ~200 px small multiples of the category
  // page: the ticks "0" and "1" sit at the ends of each axis, "predicted"
  // alone in the middle under the x-axis, "realised" rotated along the
  // y-axis. The former "→ realised ↑" centred under the x-axis ran into
  // "predicted 1" at that width.
  const yMitte = S / 2;
  return '<div style="' + CARD + '; padding:12px 14px 8px">'
    + '<div style="' + M + '; font-size:11px; letter-spacing:.12em; color:rgba(255,255,255,.6)">' + esc(k.titel || '') + '</div>'
    + '<div style="' + M + '; font-size:11px; color:rgba(255,255,255,.55); margin-top:2px">' + esc(k.hinweis || ('n ' + gesamt + ' · ' + punkte.length + ' bins')) + '</div>'
    + '<svg width="100%" viewBox="0 0 ' + S + ' ' + S + '" role="img" aria-label="' + esc(k.titel || 'calibration') + '" style="max-width:240px; display:block; margin:6px auto 0">'
    + '<rect x="' + PAD + '" y="' + PAD + '" width="' + (S - 2 * PAD) + '" height="' + (S - 2 * PAD) + '" fill="none" stroke="rgba(255,255,255,.1)" />'
    + '<line x1="' + PAD + '" y1="' + (S - PAD) + '" x2="' + (S - PAD) + '" y2="' + PAD + '" stroke="rgba(255,255,255,.3)" stroke-dasharray="3 3" />'
    + '<path d="' + linie + '" fill="none" stroke="rgba(255,255,255,.25)" stroke-width="1" />'
    + marken
    // x-axis: 0 (left end), predicted (centre), 1 (right end)
    + '<text x="' + PAD + '" y="' + (S - 6) + '" ' + achse + ' text-anchor="start">0</text>'
    + '<text x="' + (S / 2) + '" y="' + (S - 6) + '" ' + achse + ' text-anchor="middle">predicted</text>'
    + '<text x="' + (S - PAD) + '" y="' + (S - 6) + '" ' + achse + ' text-anchor="end">1</text>'
    // y-axis: 1 (top end), realised (rotated, centre), 0 (bottom end)
    + '<text x="6" y="' + (PAD + 4) + '" ' + achse + '>1</text>'
    + '<text x="10" y="' + yMitte + '" ' + achse + ' text-anchor="middle" transform="rotate(-90 10 ' + yMitte + ')">realised</text>'
    + '<text x="6" y="' + (S - PAD) + '" ' + achse + '>0</text>'
    + '</svg></div>';
}

/** Kompaktes Geld fuer Achsen und Kopfzahlen: -$210.2K, $1.4M, +$22.1M. */
export function kurzGeld(wert, vorzeichen) {
  if (wert === null || wert === undefined || typeof wert !== 'number' || wert !== wert) return '—';
  const abs = Math.abs(wert);
  const zahl = abs >= 1e9 ? (abs / 1e9).toFixed(2) + 'B'
    : abs >= 1e6 ? (abs / 1e6).toFixed(abs >= 1e8 ? 0 : 1) + 'M'
      : abs >= 1e3 ? (abs / 1e3).toFixed(abs >= 1e5 ? 0 : 1) + 'K'
        : abs >= 100 ? abs.toFixed(0) : String(parseFloat(abs.toFixed(2)));
  return (wert < 0 ? '-' : vorzeichen && wert > 0 ? '+' : '') + '$' + zahl;
}

/** "Schoene" Achsenschritte: 1, 2, 2.5, 5 x 10^k, so dass etwa n Ticks entstehen. */
function schoeneSchritte(min, max, n) {
  const spanne = max - min;
  if (!(spanne > 0)) return [min];
  const roh = spanne / Math.max(1, n);
  const zehner = Math.pow(10, Math.floor(Math.log10(roh)));
  const kandidaten = [1, 2, 2.5, 5, 10].map((f) => f * zehner);
  const schritt = kandidaten.find((k) => k >= roh) || kandidaten[kandidaten.length - 1];
  const raus = [];
  for (let v = Math.ceil(min / schritt) * schritt; v <= max + schritt * 1e-9; v += schritt) raus.push(+v.toFixed(10));
  return raus;
}

/** Zeitachsen-Kurve fuer eine kumulierte PnL-Serie: Flaeche unter der Linie,
 *  Betragsticks rechts, Datum unten, gestrichelte Nulllinie. x liegt auf der
 *  Zeit, nicht auf dem Index — 23 Schritte ueber 80 Tage stehen dort, wo sie
 *  passiert sind. Treppe (Wert gilt bis zum naechsten Punkt), weil eine
 *  realisierte Kurve zwischen zwei Aufloesungen nichts tut.
 *
 *  k: { punkte: [{ t (ISO), wert }], farbe?, hoehe?, marken? }. Unter zwei
 *  Punkten mit Zeit gibt es keine Kurve.
 */
export function pnlZeitkurve(k) {
  const pts = (k && Array.isArray(k.punkte) ? k.punkte : [])
    .map((p) => ({ ms: Date.parse(String(p.t || '')), wert: +p.wert }))
    .filter((p) => p.ms === p.ms && p.wert === p.wert)
    .sort((a, b) => a.ms - b.ms);
  if (pts.length < 2) return '';
  const B = 900, H = k.hoehe || 250;
  const L = 12, R = B - 74, TOP = 14, BOT = H - 28;
  const werte = pts.map((p) => p.wert);
  let min = Math.min(0, ...werte);
  let max = Math.max(0, ...werte);
  if (min === max) max = min + 1;
  const luft = (max - min) * 0.06;
  min -= luft; max += luft;
  const t0 = pts[0].ms, t1 = pts[pts.length - 1].ms;
  const spanne = Math.max(1, t1 - t0);
  const x = (ms) => L + ((ms - t0) / spanne) * (R - L);
  const y = (w) => BOT - ((w - min) / (max - min)) * (BOT - TOP);
  const letzte = werte[werte.length - 1];
  const farbe = k.farbe || (letzte >= 0 ? '#C8F542' : '#FF4545');
  const gid = 'pnlgrad' + Math.abs(Math.round(letzte * 100) + pts.length).toString(36);

  // Treppe nach rechts, dann Flaeche bis zur Nulllinie (oder zum Boden).
  let linie = 'M ' + x(pts[0].ms).toFixed(1) + ' ' + y(pts[0].wert).toFixed(1);
  for (let i = 1; i < pts.length; i += 1) {
    linie += ' H ' + x(pts[i].ms).toFixed(1) + ' V ' + y(pts[i].wert).toFixed(1);
  }
  const boden = (min < 0 && max > 0) ? y(0) : BOT;
  const flaeche = linie + ' V ' + boden.toFixed(1) + ' H ' + x(pts[0].ms).toFixed(1) + ' Z';

  // Betragsticks rechts mit feinen Gitterlinien.
  const ticks = schoeneSchritte(min + luft, max - luft, 4);
  let gitter = '';
  ticks.forEach((tv) => {
    const yy = y(tv);
    if (yy < TOP - 1 || yy > BOT + 1) return;
    gitter += '<line x1="' + L + '" y1="' + yy.toFixed(1) + '" x2="' + R + '" y2="' + yy.toFixed(1) + '" stroke="rgba(255,255,255,.07)" stroke-width="1" />'
      + '<text x="' + (R + 8) + '" y="' + (yy + 3.5).toFixed(1) + '" fill="rgba(255,255,255,.6)" font-size="10.5" font-family="JetBrains Mono, monospace">' + esc(kurzGeld(tv)) + '</text>';
  });
  let nulllinie = '';
  if (min < 0 && max > 0) {
    nulllinie = '<line x1="' + L + '" y1="' + y(0).toFixed(1) + '" x2="' + R + '" y2="' + y(0).toFixed(1)
      + '" stroke="rgba(255,255,255,.28)" stroke-width="1" stroke-dasharray="4 4" />';
  }

  // Datum: Anfang, Ende und bis zu zwei Zwischenmarken auf der Zeit.
  const datum = (ms) => new Date(ms).toISOString().slice(0, 10);
  const nDatum = spanne > 3 * 86400000 ? 4 : 2;
  let xLabels = '';
  for (let i = 0; i < nDatum; i += 1) {
    const ms = t0 + (spanne * i) / (nDatum - 1);
    const anker = i === 0 ? 'start' : i === nDatum - 1 ? 'end' : 'middle';
    xLabels += '<text x="' + x(ms).toFixed(1) + '" y="' + (H - 9) + '" fill="rgba(255,255,255,.6)" font-size="10.5" '
      + 'font-family="JetBrains Mono, monospace" text-anchor="' + anker + '">' + esc(datum(ms)) + '</text>';
  }

  // Marken nur, wenn die Serie so duenn ist, dass jeder Punkt eine Aufloesung ist.
  let marken = '';
  if (k.marken !== false && pts.length <= 60) {
    pts.forEach((p) => {
      marken += '<circle cx="' + x(p.ms).toFixed(1) + '" cy="' + y(p.wert).toFixed(1) + '" r="2.4" fill="' + farbe + '"><title>' + esc(datum(p.ms) + ' · ' + kurzGeld(p.wert, true)) + '</title></circle>';
    });
  }
  const endPunkt = '<circle cx="' + x(t1).toFixed(1) + '" cy="' + y(letzte).toFixed(1) + '" r="4" fill="' + farbe + '" stroke="#10151A" stroke-width="2" />';

  return '<svg width="100%" viewBox="0 0 ' + B + ' ' + H + '" role="img" aria-label="' + esc(k.titel || 'cumulative PnL') + '" style="display:block">'
    + '<defs><linearGradient id="' + gid + '" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="' + farbe + '" stop-opacity=".28" /><stop offset="1" stop-color="' + farbe + '" stop-opacity="0" /></linearGradient></defs>'
    + gitter + nulllinie
    + '<path d="' + flaeche + '" fill="url(#' + gid + ')" stroke="none" />'
    + '<path d="' + linie + '" fill="none" stroke="' + farbe + '" stroke-width="2" vector-effect="non-scaling-stroke" />'
    + marken + endPunkt + xLabels
    + '</svg>';
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
  const xLabels = '<text x="' + L + '" y="' + (H - 8) + '" fill="rgba(255,255,255,.6)" font-size="11" '
    + 'font-family="JetBrains Mono, monospace">' + esc(String(k.punkte[0].label || '')) + '</text>'
    + '<text x="' + R + '" y="' + (H - 8) + '" fill="rgba(255,255,255,.6)" font-size="11" '
    + 'font-family="JetBrains Mono, monospace" text-anchor="end">' + esc(String(k.punkte[k.punkte.length - 1].label || '')) + '</text>';

  return '<div style="' + CARD + '; padding:14px 16px 10px">'
    + '<div style="display:flex; align-items:baseline; justify-content:space-between; gap:14px; flex-wrap:wrap; margin-bottom:4px">'
    + '<div style="' + M + '; font-size:11px; letter-spacing:.13em; color:rgba(255,255,255,.5)">'
    + esc(k.titel || '') + (k.einheit ? ' · ' + esc(k.einheit) : '') + '</div>'
    + (k.hinweis ? '<div style="' + M + '; font-size:11px; color:rgba(255,255,255,.55)">' + esc(k.hinweis) + '</div>' : '')
    + '</div>'
    + '<svg width="100%" viewBox="0 0 ' + B + ' ' + H + '" preserveAspectRatio="none" role="img" aria-label="' + esc(k.titel || 'series') + '">'
    + nulllinie
    + '<path d="' + pfad + '" fill="none" stroke="' + farbe + '" stroke-width="2" />'
    + marken + endLabel + xLabels
    + '</svg></div>';
}
