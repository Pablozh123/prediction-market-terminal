// Gemeinsame SVG-Diagramme, abhaengigkeitsfrei wie der Rest des Terminals.
//
// Hierher umgezogen aus pages/microstructure_page.js, damit auch die anderen
// Seiten dieselben Formen zeichnen koennen statt eigene zu erfinden. Es gilt
// weiter die eine Regel des Frontends: keine Funktion hier erzeugt einen
// Verlauf ohne eine echte Serie dahinter — ohne Punkte kommt ein leerer
// String zurueck, und der Aufrufer zeigt seinen Leerzustand.

import { esc } from './util.js';

const M = "font-family:'IBM Plex Mono',monospace";
const CARD = 'background:var(--panel); border:1px solid rgba(var(--ink),.09); border-radius:var(--r-panel)';

const BALKEN_FARBE = { gewinn: 'var(--pos)', kosten: 'var(--neg)', summe: 'var(--info)' };

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
      + '" style="stroke:rgba(var(--ink),.28)" stroke-width="1" />';
  }
  if (typeof dia.referenz === 'number' && dia.referenz !== 0) {
    const rx = sk.x(dia.referenz);
    out += '<line x1="' + rx + '" y1="6" x2="' + rx + '" y2="' + (hoehe - 22)
      + '" style="stroke:rgba(var(--ink),.35)" stroke-width="1" stroke-dasharray="4 4" />';
    if (dia.referenz_label) {
      out += '<text x="' + rx + '" y="' + (hoehe - 8) + '" style="fill:rgba(var(--ink),.6)" '
        + 'font-size="11" font-family="IBM Plex Mono, monospace" text-anchor="middle">'
        + esc(dia.referenz_label) + '</text>';
    }
  }
  return out;
}

function labelText(text, y) {
  return '<text x="' + LABEL_X + '" y="' + (y + 4) + '" style="fill:rgba(var(--ink),.72)" font-size="11.5" '
    + 'font-family="IBM Plex Mono, monospace" text-anchor="end">' + esc(text) + '</text>';
}

function wertText(text, x, y, farbe) {
  return '<text x="' + x + '" y="' + (y + 4) + '" style="fill:' + farbe + '" font-size="11.5" '
    + 'font-family="IBM Plex Mono, monospace">' + esc(text) + '</text>';
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
        const farbe = BALKEN_FARBE[p.art] || 'var(--info)';
        const x0 = sk.x(0);
        const x1 = sk.x(w);
        koerper += labelText(gruppen[i] + ' · ' + p.label, y);
        koerper += '<rect x="' + Math.min(x0, x1) + '" y="' + (y - 8) + '" width="' + Math.abs(x1 - x0)
          + '" height="16" rx="3" style="fill:' + farbe + '" fill-opacity="' + (i === 0 ? '.45' : '.95') + '" />';
        koerper += wertText(fmtZahl(w), PLOT_R + 8, y, 'rgba(var(--ink),.75)');
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
      const farbe = p.farbe || (beruehrt ? 'var(--warn)' : 'var(--info)');
      koerper += '<line x1="' + xa + '" y1="' + y + '" x2="' + xb + '" y2="' + y
        + '" style="stroke:' + farbe + '" stroke-width="3" stroke-linecap="round" stroke-opacity="' + (p.farbe ? '.45' : '1') + '" />';
      koerper += '<line x1="' + xa + '" y1="' + (y - 6) + '" x2="' + xa + '" y2="' + (y + 6)
        + '" style="stroke:' + farbe + '" stroke-width="2" />';
      koerper += '<line x1="' + xb + '" y1="' + (y - 6) + '" x2="' + xb + '" y2="' + (y + 6)
        + '" style="stroke:' + farbe + '" stroke-width="2" />';
      koerper += '<circle cx="' + xm + '" cy="' + y + '" r="4.5" style="fill:' + farbe + '" />';
      koerper += wertText(p.text || (fmtZahl(p.von) + ' … ' + fmtZahl(p.bis)), PLOT_R + 8, y, 'rgba(var(--ink),.75)');
    } else if (typeof p.wert === 'number') {
      // p.farbe schlaegt das Vorzeichen: ein Balken, dessen Laenge einen
      // Einsatz misst und dessen Farbe ein Ergebnis traegt, kann seine Farbe
      // nicht aus der eigenen Laenge holen.
      const farbe = p.farbe || BALKEN_FARBE[p.art] || (p.wert < 0 ? 'var(--neg)' : 'var(--pos)');
      // Auf einer referenzverankerten Skala liegt die Null links ausserhalb;
      // der Balken beginnt dann an der Referenz, denn die Abweichung von ihr
      // ist die Aussage.
      const anker = sk.min > 0 && typeof dia.referenz === 'number' ? dia.referenz : 0;
      const x0 = sk.x(anker);
      const x1 = sk.x(p.wert);
      koerper += '<rect x="' + Math.min(x0, x1) + '" y="' + (y - 9) + '" width="' + Math.abs(x1 - x0)
        + '" height="18" rx="3" style="fill:' + farbe + '" fill-opacity=".92">'
        + '<title>' + esc(p.tip || (p.label + ' · ' + fmtZahl(p.wert))) + '</title></rect>';
      koerper += wertText(p.text || fmtZahl(p.wert), PLOT_R + 8, y, 'rgba(var(--ink),.78)');
    }
    y += ZEILE;
  });

  // Gedeckelte Breite: das SVG skaliert seinen Inhalt mit. Ohne Deckel wuchs
  // jede Zeile auf breiten Fenstern mit (958px Spalte = Faktor 1.5, Text
  // 17px) und ein 20-Zeilen-Diagramm stand fast 1000px hoch neben den
  // kompakten HTML-Tabellen.
  return '<div style="' + CARD + '; padding:14px 16px 10px">'
    + '<div style="' + M + '; font-size:11px; letter-spacing:.13em; color:rgba(var(--ink),.62); margin-bottom:4px">'
    + esc(dia.titel || '') + (dia.einheit ? ' · ' + esc(dia.einheit) : '') + '</div>'
    + '<svg width="100%" viewBox="0 0 ' + BREITE + ' ' + hoehe + '" role="img" aria-label="' + esc(dia.titel || 'chart') + '" style="display:block; max-width:660px">'
    + achse(sk, dia, hoehe) + koerper
    // Achsenbeschriftung nur, wenn die Referenzmarke den Platz nicht schon
    // hat: zwei zentrierte Beschriftungen auf derselben Grundlinie waeren
    // uebereinander gedruckt.
    + (dia.xLabel && !dia.referenz_label
      ? '<text x="' + ((PLOT_L + PLOT_R) / 2) + '" y="' + (hoehe - 6) + '" style="fill:rgba(var(--ink),.62)" '
        + 'font-size="10.5" font-family="IBM Plex Mono, monospace" text-anchor="middle">' + esc(dia.xLabel) + '</text>'
      : '')
    + '</svg></div>';
}

// Serienfarben fuer Mehrlinien-Diagramme: fuenf Plaetze in fester
// Reihenfolge, definiert in terminal.css als --s1 bis --s5.
//
// Die alte Liste hatte neun Plaetze aus den Rollen- und --cat-Tokens und
// vergab sie zyklisch. Gerechnet (nicht geschaetzt) fiel sie durch vier von
// fuenf Pruefungen: --cat-violet und --info lagen unter Protanopie bei
// Delta E 0.3, --cat-gold gegen --accent bei 5.4 fuer normalsichtige Leser,
// sechs der neun lagen unter dem Buntheitsboden und lasen sich als Grau.
// Dazu stand --pos auf Platz 3, obwohl terminal.css Gruen und Rot fuer
// Vorzeichenwerte reserviert: in einem Vier-Serien-Diagramm hiess Gruen
// gleichzeitig "Serie 3" und "positiv".
//
// Die fuenf neuen Plaetze bestehen alle fuenf Pruefungen in beiden Themes,
// siehe den Kommentar an --s1 in terminal.css. Ueber fuenf Serien wird
// nicht weiter zyklisch vergeben: zwei Serien mit derselben Farbe sind
// keine Kodierung. serienFarbe() gibt dann null zurueck, und der Aufrufer
// fasst zusammen oder teilt auf.
export const SERIEN_FARBEN = ['var(--s1)', 'var(--s2)', 'var(--s3)', 'var(--s4)', 'var(--s5)'];

/** Farbe fuer Serie i, oder null jenseits der Plaetze (nicht zyklisch). */
export function serienFarbe(i) {
  return i >= 0 && i < SERIEN_FARBEN.length ? SERIEN_FARBEN[i] : null;
}

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
  const alleSerien = k.serien.filter((s) => s && Array.isArray(s.werte) && s.werte.some((w) => typeof w === 'number'));
  // Keine zyklische Farbvergabe: ab Serie 6 gaebe es keine eigene Farbe
  // mehr. Was nicht in die Plaetze passt, wird nicht heimlich in einer
  // schon vergebenen Farbe gezeichnet, sondern gezaehlt und benannt.
  const serien = alleSerien.slice(0, SERIEN_FARBEN.length);
  const ueberzaehlig = alleSerien.length - serien.length;
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
      + '" style="stroke:rgba(var(--ink),' + (f === 0 ? '.18' : '.07') + ')" stroke-width="1" />'
      + '<text x="' + (L - 6) + '" y="' + (y(w) + 4).toFixed(1) + '" style="fill:rgba(var(--ink),.6)" font-size="11" '
      + 'font-family="IBM Plex Mono, monospace" text-anchor="end">' + esc(fmtZahl(Math.round(w * 1000) / 1000)) + '</text>';
  });
  let xLabels = '';
  k.x.forEach((label, i) => {
    xLabels += '<text x="' + x(i).toFixed(1) + '" y="' + (H - 10) + '" style="fill:rgba(var(--ink),.6)" font-size="11" '
      + 'font-family="IBM Plex Mono, monospace" text-anchor="middle">' + esc(String(label)) + '</text>';
  });
  let pfade = '';
  let legende = '';
  serien.forEach((s, si) => {
    const farbe = s.farbe || serienFarbe(si);
    let d = '';
    let offen = false;
    s.werte.forEach((w, i) => {
      if (typeof w !== 'number') { offen = false; return; }
      d += (offen ? ' L ' : ' M ') + x(i).toFixed(1) + ' ' + y(w).toFixed(1);
      offen = true;
      pfade += '<circle cx="' + x(i).toFixed(1) + '" cy="' + y(w).toFixed(1) + '" r="3" style="fill:' + farbe + '">'
        + '<title>' + esc(s.name + ' · ' + k.x[i] + ' · ' + fmtZahl(w)) + '</title></circle>';
    });
    if (d) pfade += '<path d="' + d.trim() + '" fill="none" style="stroke:' + farbe + '" stroke-width="1.8" />';
    legende += '<div style="display:flex; align-items:center; gap:6px; ' + M + '; font-size:11px; color:rgba(var(--ink),.65)">'
      + '<span style="display:inline-block; width:14px; height:3px; background:' + farbe + '; border-radius:2px"></span>'
      + esc(s.name) + '</div>';
  });

  return '<div style="' + CARD + '; padding:14px 16px 10px">'
    + '<div style="display:flex; align-items:baseline; justify-content:space-between; gap:14px; flex-wrap:wrap; margin-bottom:4px">'
    + '<div style="' + M + '; font-size:11px; letter-spacing:.13em; color:rgba(var(--ink),.62)">'
    + esc(k.titel || '') + (k.einheit ? ' · ' + esc(k.einheit) : '') + '</div>'
    + (k.hinweis ? '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.62)">' + esc(k.hinweis) + '</div>' : '')
    + '</div>'
    + '<div style="display:flex; gap:12px; flex-wrap:wrap; margin:4px 0 6px">' + legende
    + (ueberzaehlig > 0
      ? '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.62)">+ ' + ueberzaehlig + ' further series not drawn — the palette has '
        + SERIEN_FARBEN.length + ' slots and does not reuse one</div>'
      : '')
    + '</div>'
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
    const farbe = daneben ? 'var(--warn)' : 'var(--info)';
    const r = 2.5 + 4.5 * Math.sqrt((+p.n || 0) / nMax);
    linie += (i === 0 ? 'M ' : ' L ') + cx.toFixed(1) + ' ' + cy.toFixed(1);
    if (ci) {
      marken += '<line x1="' + cx.toFixed(1) + '" y1="' + (S - pos(ci[0])).toFixed(1) + '" x2="' + cx.toFixed(1)
        + '" y2="' + (S - pos(ci[1])).toFixed(1) + '" style="stroke:' + farbe + '" stroke-opacity=".45" stroke-width="1" />';
    }
    marken += '<circle cx="' + cx.toFixed(1) + '" cy="' + cy.toFixed(1) + '" r="' + r.toFixed(1) + '" style="fill:' + farbe + '" fill-opacity=".9">'
      + '<title>' + esc('predicted ' + Math.round(p.vorhergesagt * 100) + '% · realised ' + Math.round(p.realisiert * 100) + '% · n ' + (p.n != null ? p.n : '—')) + '</title></circle>';
  });
  const achse = 'style="fill:rgba(var(--ink),.6)" font-size="10.5" font-family="IBM Plex Mono, monospace"';
  // Axis lettering that survives the ~200 px small multiples of the category
  // page: the ticks "0" and "1" sit at the ends of each axis, "predicted"
  // alone in the middle under the x-axis, "realised" rotated along the
  // y-axis. The former "→ realised ↑" centred under the x-axis ran into
  // "predicted 1" at that width.
  const yMitte = S / 2;
  return '<div style="' + CARD + '; padding:12px 14px 8px">'
    + '<div style="' + M + '; font-size:11px; letter-spacing:.12em; color:rgba(var(--ink),.6)">' + esc(k.titel || '') + '</div>'
    + '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.62); margin-top:2px">' + esc(k.hinweis || ('n ' + gesamt + ' · ' + punkte.length + ' bins')) + '</div>'
    + '<svg width="100%" viewBox="0 0 ' + S + ' ' + S + '" role="img" aria-label="' + esc(k.titel || 'calibration') + '" style="max-width:240px; display:block; margin:6px auto 0">'
    + '<rect x="' + PAD + '" y="' + PAD + '" width="' + (S - 2 * PAD) + '" height="' + (S - 2 * PAD) + '" fill="none" style="stroke:rgba(var(--ink),.1)" />'
    + '<line x1="' + PAD + '" y1="' + (S - PAD) + '" x2="' + (S - PAD) + '" y2="' + PAD + '" style="stroke:rgba(var(--ink),.3)" stroke-dasharray="3 3" />'
    + '<path d="' + linie + '" fill="none" style="stroke:rgba(var(--ink),.25)" stroke-width="1" />'
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
  const farbe = k.farbe || (letzte >= 0 ? 'var(--pos)' : 'var(--neg)');
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
    gitter += '<line x1="' + L + '" y1="' + yy.toFixed(1) + '" x2="' + R + '" y2="' + yy.toFixed(1) + '" style="stroke:rgba(var(--ink),.07)" stroke-width="1" />'
      + '<text x="' + (R + 8) + '" y="' + (yy + 3.5).toFixed(1) + '" style="fill:rgba(var(--ink),.6)" font-size="10.5" font-family="IBM Plex Mono, monospace">' + esc(kurzGeld(tv)) + '</text>';
  });
  let nulllinie = '';
  if (min < 0 && max > 0) {
    nulllinie = '<line x1="' + L + '" y1="' + y(0).toFixed(1) + '" x2="' + R + '" y2="' + y(0).toFixed(1)
      + '" style="stroke:rgba(var(--ink),.28)" stroke-width="1" stroke-dasharray="4 4" />';
  }

  // Datum: Anfang, Ende und bis zu zwei Zwischenmarken auf der Zeit.
  const datum = (ms) => new Date(ms).toISOString().slice(0, 10);
  const nDatum = spanne > 3 * 86400000 ? 4 : 2;
  let xLabels = '';
  for (let i = 0; i < nDatum; i += 1) {
    const ms = t0 + (spanne * i) / (nDatum - 1);
    const anker = i === 0 ? 'start' : i === nDatum - 1 ? 'end' : 'middle';
    xLabels += '<text x="' + x(ms).toFixed(1) + '" y="' + (H - 9) + '" style="fill:rgba(var(--ink),.6)" font-size="10.5" '
      + 'font-family="IBM Plex Mono, monospace" text-anchor="' + anker + '">' + esc(datum(ms)) + '</text>';
  }

  // Marken nur, wenn die Serie so duenn ist, dass jeder Punkt eine Aufloesung ist.
  let marken = '';
  if (k.marken !== false && pts.length <= 60) {
    pts.forEach((p) => {
      marken += '<circle cx="' + x(p.ms).toFixed(1) + '" cy="' + y(p.wert).toFixed(1) + '" r="2.4" style="fill:' + farbe + '"><title>' + esc(datum(p.ms) + ' · ' + kurzGeld(p.wert, true)) + '</title></circle>';
    });
  }
  const endPunkt = '<circle cx="' + x(t1).toFixed(1) + '" cy="' + y(letzte).toFixed(1) + '" r="4" style="fill:' + farbe + '; stroke:var(--panel)" stroke-width="2" />';

  return '<svg width="100%" viewBox="0 0 ' + B + ' ' + H + '" role="img" aria-label="' + esc(k.titel || 'cumulative PnL') + '" style="display:block">'
    + '<defs><linearGradient id="' + gid + '" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="' + farbe + '" stop-opacity=".28" /><stop offset="1" stop-color="' + farbe + '" stop-opacity="0" /></linearGradient></defs>'
    + gitter + nulllinie
    + '<path d="' + flaeche + '" fill="url(#' + gid + ')" stroke="none" />'
    + '<path d="' + linie + '" fill="none" style="stroke:' + farbe + '" stroke-width="2" vector-effect="non-scaling-stroke" />'
    + marken + endPunkt + xLabels
    + '</svg>';
}

/** Gespiegelte Zeitbalken: Zufluesse wachsen von der Nulllinie nach oben,
 *  Abfluesse nach unten. Beide Seiten teilen denselben $-je-px-Massstab —
 *  die Nulllinie sitzt dort, wo das Groessenverhaeltnis sie hinschiebt,
 *  damit oben und unten optisch vergleichbar bleiben.
 *
 *  k: { titel, einheit, hinweis, legende (fertiges HTML),
 *       bins: [{ oben, unten, zeit }],
 *       xLabels: [{ i, text, anker }],
 *       marken: [{ bin, oben: bool, text }] }
 *  Unter zwei Bins oder ohne einen Dollar auf beiden Seiten: kein Diagramm.
 */
export function spiegelZeit(k) {
  if (!k || !Array.isArray(k.bins) || k.bins.length < 2) return '';
  const maxO = Math.max(0, ...k.bins.map((b) => +b.oben || 0));
  const maxU = Math.max(0, ...k.bins.map((b) => +b.unten || 0));
  if (maxO + maxU <= 0) return '';
  const B = 900, H = 224;
  const L = 12, R = B - 78, TOP = 16, BOT = H - 26;
  const skala = (BOT - TOP) / (maxO + maxU);
  const basis = TOP + maxO * skala;
  const bw = (R - L) / k.bins.length;

  let koerper = '';
  k.bins.forEach((b, i) => {
    const x = (L + i * bw + 1).toFixed(1);
    const w = Math.max(1, bw - 2).toFixed(1);
    const o = (+b.oben || 0) * skala;
    const u = (+b.unten || 0) * skala;
    const zeit = b.zeit ? b.zeit + ' · ' : '';
    if (o > 0) {
      koerper += '<rect x="' + x + '" y="' + (basis - o).toFixed(1) + '" width="' + w + '" height="' + Math.max(1.5, o).toFixed(1)
        + '" rx="1.5" style="fill:var(--pos)" fill-opacity=".85"><title>' + esc(zeit + 'buys ' + kurzGeld(+b.oben)) + '</title></rect>';
    }
    if (u > 0) {
      koerper += '<rect x="' + x + '" y="' + basis.toFixed(1) + '" width="' + w + '" height="' + Math.max(1.5, u).toFixed(1)
        + '" rx="1.5" style="fill:var(--neg)" fill-opacity=".85"><title>' + esc(zeit + 'sells ' + kurzGeld(+b.unten)) + '</title></rect>';
    }
  });

  // Nulllinie durchgezogen, die beiden Seitenmaxima als Ticks rechts.
  let achsen = '<line x1="' + L + '" y1="' + basis.toFixed(1) + '" x2="' + R + '" y2="' + basis.toFixed(1)
    + '" style="stroke:rgba(var(--ink),.28)" stroke-width="1" />';
  const tickStil = 'font-size="10.5" font-family="IBM Plex Mono, monospace"';
  if (maxO > 0) {
    achsen += '<text x="' + (R + 8) + '" y="' + (TOP + 4) + '" style="fill:var(--pos)" ' + tickStil + '>' + esc(kurzGeld(maxO)) + '</text>'
      + '<line x1="' + L + '" y1="' + TOP + '" x2="' + R + '" y2="' + TOP + '" style="stroke:rgba(var(--ink),.07)" stroke-width="1" />';
  }
  if (maxU > 0) {
    achsen += '<text x="' + (R + 8) + '" y="' + (BOT + 4) + '" style="fill:var(--neg)" ' + tickStil + '>' + esc(kurzGeld(maxU)) + '</text>'
      + '<line x1="' + L + '" y1="' + BOT + '" x2="' + R + '" y2="' + BOT + '" style="stroke:rgba(var(--ink),.07)" stroke-width="1" />';
  }
  achsen += '<text x="' + (R + 8) + '" y="' + (basis + 4).toFixed(1) + '" style="fill:rgba(var(--ink),.62)" ' + tickStil + '>0</text>';

  let xLabels = '';
  (Array.isArray(k.xLabels) ? k.xLabels : []).forEach((l) => {
    if (l.i == null || l.i < 0 || l.i >= k.bins.length) return;
    xLabels += '<text x="' + (L + (l.i + 0.5) * bw).toFixed(1) + '" y="' + (H - 9) + '" style="fill:rgba(var(--ink),.6)" font-size="10.5" '
      + 'font-family="IBM Plex Mono, monospace" text-anchor="' + (l.anker || 'middle') + '">' + esc(String(l.text)) + '</text>';
  });

  // Marken sitzen knapp ausserhalb ihres Balkens, auf der Seite des Prints.
  let marken = '';
  (Array.isArray(k.marken) ? k.marken : []).forEach((m) => {
    if (m.bin == null || m.bin < 0 || m.bin >= k.bins.length) return;
    const b = k.bins[m.bin];
    const cx = (L + (m.bin + 0.5) * bw).toFixed(1);
    const cy = m.oben
      ? Math.max(TOP - 6, basis - (+b.oben || 0) * skala - 7)
      : Math.min(BOT + 6, basis + (+b.unten || 0) * skala + 7);
    marken += '<circle cx="' + cx + '" cy="' + cy.toFixed(1) + '" r="3" style="fill:var(--warn); stroke:var(--panel)" stroke-width="1.5">'
      + '<title>' + esc(m.text || '') + '</title></circle>';
  });

  return '<div style="' + CARD + '; padding:14px 16px 10px">'
    + '<div style="display:flex; align-items:baseline; justify-content:space-between; gap:14px; flex-wrap:wrap; margin-bottom:4px">'
    + '<div style="' + M + '; font-size:11px; letter-spacing:.13em; color:rgba(var(--ink),.62)">'
    + esc(k.titel || '') + (k.einheit ? ' · ' + esc(k.einheit) : '') + '</div>'
    + (k.hinweis ? '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.62)">' + esc(k.hinweis) + '</div>' : '')
    + '</div>'
    + (k.legende ? '<div style="display:flex; gap:12px; flex-wrap:wrap; margin:4px 0 6px">' + k.legende + '</div>' : '')
    + '<svg width="100%" viewBox="0 0 ' + B + ' ' + H + '" role="img" aria-label="' + esc(k.titel || 'flow') + '">'
    + achsen + koerper + marken + xLabels + '</svg></div>';
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
  const farbe = k.farbe || (letzte >= 0 ? 'var(--pos)' : 'var(--neg)');

  // Treppe: erst waagerecht zum naechsten Schritt, dann senkrecht auf ihn.
  let pfad = 'M ' + x(0).toFixed(1) + ' ' + y(werte[0]).toFixed(1);
  for (let i = 1; i < werte.length; i += 1) {
    pfad += ' H ' + x(i).toFixed(1) + ' V ' + y(werte[i]).toFixed(1);
  }
  let marken = '';
  werte.forEach((w, i) => {
    marken += '<circle cx="' + x(i).toFixed(1) + '" cy="' + y(w).toFixed(1) + '" r="2.6" style="fill:' + farbe + '" />';
  });

  let nulllinie = '';
  if (min < 0 && max > 0) {
    nulllinie = '<line x1="' + L + '" y1="' + y(0).toFixed(1) + '" x2="' + R + '" y2="' + y(0).toFixed(1)
      + '" style="stroke:rgba(var(--ink),.25)" stroke-width="1" stroke-dasharray="4 4" />';
  }

  const endLabel = '<text x="' + (R + 8) + '" y="' + (y(letzte) + 4).toFixed(1) + '" style="fill:' + farbe
    + '" font-size="12" font-family="IBM Plex Mono, monospace">' + esc(fmtZahl(letzte)) + '</text>';
  const xLabels = '<text x="' + L + '" y="' + (H - 8) + '" style="fill:rgba(var(--ink),.6)" font-size="11" '
    + 'font-family="IBM Plex Mono, monospace">' + esc(String(k.punkte[0].label || '')) + '</text>'
    + '<text x="' + R + '" y="' + (H - 8) + '" style="fill:rgba(var(--ink),.6)" font-size="11" '
    + 'font-family="IBM Plex Mono, monospace" text-anchor="end">' + esc(String(k.punkte[k.punkte.length - 1].label || '')) + '</text>';

  return '<div style="' + CARD + '; padding:14px 16px 10px">'
    + '<div style="display:flex; align-items:baseline; justify-content:space-between; gap:14px; flex-wrap:wrap; margin-bottom:4px">'
    + '<div style="' + M + '; font-size:11px; letter-spacing:.13em; color:rgba(var(--ink),.62)">'
    + esc(k.titel || '') + (k.einheit ? ' · ' + esc(k.einheit) : '') + '</div>'
    + (k.hinweis ? '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.62)">' + esc(k.hinweis) + '</div>' : '')
    + '</div>'
    + '<svg width="100%" viewBox="0 0 ' + B + ' ' + H + '" preserveAspectRatio="none" role="img" aria-label="' + esc(k.titel || 'series') + '">'
    + nulllinie
    + '<path d="' + pfad + '" fill="none" style="stroke:' + farbe + '" stroke-width="2" />'
    + marken + endLabel + xLabels
    + '</svg></div>';
}

// ---------------------------------------------------------------------------
// Gemeinsames Chrom der neuen Formen.
//
// Regeln, die hier ueberall gelten und nicht je Aufrufstelle neu entschieden
// werden: jede Achse traegt ihre Beschriftung samt Einheit, Text traegt nie
// die Datenfarbe (sondern eine Ink-Stufe ab .62, denn .5 komponiert auf dem
// hellen Grund zu 3.88:1 und faellt durch AA), jede Marke traegt einen
// Tooltip, Gitterlinien sind haarduenn und durchgezogen, und ueberlappende
// Punkte tragen einen 2px-Ring in der Flaechenfarbe statt einer Kontur.

const TICK = 'font-size="10.5" font-family="IBM Plex Mono, monospace"';
const INK62 = 'style="fill:rgba(var(--ink),.62)"';
const INK72 = 'style="fill:rgba(var(--ink),.72)"';
const GITTER = 'style="stroke:rgba(var(--ink),.09)" stroke-width="1"';

// fussnote ist Text und wird maskiert; fussnoteHtml ist fertiges Markup und
// wird es nicht. Den zweiten Kanal gibt es fuer genau einen Zweck: ein
// Vorbehalt kommt aus data/claims.yaml ueber claims.js::caveat und bringt
// sein data-caveat="<schluessel>" mit, an dem scripts/lint_claims.py haengt.
// Durch esc() gedreht waere aus dem Attribut Text geworden, und der Satz
// stuende wieder unkontrolliert in der Seite. Aufrufer geben hier nur
// Register-Markup weiter, nie zusammengesetzte Nutzerdaten.
function karte(titel, einheit, hinweis, inhalt, fussnote, fussnoteHtml) {
  const fuss = (fussnote ? esc(fussnote) : '') + (fussnoteHtml ? (fussnote ? ' ' : '') + fussnoteHtml : '');
  return '<div style="' + CARD + '; padding:14px 16px 10px">'
    + '<div style="display:flex; align-items:baseline; justify-content:space-between; gap:14px; flex-wrap:wrap; margin-bottom:6px">'
    + '<div style="' + M + '; font-size:11px; letter-spacing:.13em; color:rgba(var(--ink),.62)">'
    + esc(titel || '') + (einheit ? ' · ' + esc(einheit) : '') + '</div>'
    + (hinweis ? '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.62)">' + esc(hinweis) + '</div>' : '')
    + '</div>' + inhalt
    + (fuss ? '<div style="font-size:11.5px; line-height:1.55; color:rgba(var(--ink),.62); margin-top:8px; max-width:640px">' + fuss + '</div>' : '')
    + '</div>';
}

function achsenTitel(text, x, y, drehen) {
  if (!text) return '';
  return '<text x="' + x + '" y="' + y + '" ' + INK62 + ' ' + TICK + ' text-anchor="middle"'
    + (drehen ? ' transform="rotate(-90 ' + x + ' ' + y + ')"' : '') + '>' + esc(text) + '</text>';
}

/** Dekadenticks fuer eine logarithmische Achse, 1 und 3 je Dekade. */
function logTicks(min, max) {
  const raus = [];
  const von = Math.floor(Math.log10(Math.max(1e-9, min)));
  const bis = Math.ceil(Math.log10(Math.max(1e-9, max)));
  for (let e = von; e <= bis; e += 1) {
    [1, 3].forEach((f) => {
      const v = f * Math.pow(10, e);
      if (v >= min && v <= max) raus.push(v);
    });
  }
  return raus.length >= 2 ? raus : [min, max];
}

/** Punktwolke: zwei gemessene Groessen je Marke, plus eine schattierte Zone.
 *
 *  k: { titel, einheit, hinweis, fussnote,
 *       xLabel, yLabel,            // Beschriftung MIT Einheit, Pflicht
 *       xDomain: [min, max],       // fest, damit die Skala nicht mitwandert
 *       yLog: bool,
 *       gate: { wert, text },      // Zone unterhalb wird schattiert
 *       xReferenzen: [{ wert, label }], yReferenzen: [{ wert, label }],
 *       fussnoteHtml (fertiges Vorbehalts-Markup, siehe karte),
 *       punkte: [{ x, y, label, tip, band?: [lo, hi], hervor?: bool }],
 *       labelN }                   // wie viele Punkte direkt beschriftet werden
 *  Ohne Punkte kein Diagramm. Eine Serie, also keine Legende: der Titel
 *  sagt, was gezeichnet ist.
 */
export function punktwolke(k) {
  const pts = (k && Array.isArray(k.punkte) ? k.punkte : [])
    .filter((p) => p && typeof p.x === 'number' && typeof p.y === 'number' && p.x === p.x && p.y === p.y);
  if (!pts.length) return '';
  const B = 660, H = 320;
  const L = 62, R = B - 18, TOP = 16, BOT = H - 46;
  const xd = Array.isArray(k.xDomain) && k.xDomain.length === 2 ? k.xDomain : [0, 100];
  const xmin = xd[0], xmax = xd[1] > xd[0] ? xd[1] : xd[0] + 1;
  const x = (v) => L + ((Math.max(xmin, Math.min(xmax, v)) - xmin) / (xmax - xmin)) * (R - L);

  const yRefs = (Array.isArray(k.yReferenzen) ? k.yReferenzen : []).filter((r) => r && typeof r.wert === 'number');
  const xRefs = (Array.isArray(k.xReferenzen) ? k.xReferenzen : []).filter((r) => r && typeof r.wert === 'number' && r.wert >= xmin && r.wert <= xmax);
  const ys = pts.map((p) => p.y)
    .concat(k.gate && typeof k.gate.wert === 'number' ? [k.gate.wert] : [])
    .concat(yRefs.map((r) => r.wert));
  const log = !!k.yLog;
  // Log braucht einen positiven Boden; bei y = 0 waere die Achse unendlich.
  const roh = ys.filter((v) => (log ? v > 0 : true));
  let ymin = log ? Math.min(...roh) / 1.6 : 0;
  let ymax = Math.max(...ys, 1);
  if (log) { ymin = Math.max(1, Math.pow(10, Math.floor(Math.log10(ymin)))); ymax *= 1.25; }
  else { ymax *= 1.1; }
  const y = log
    ? (v) => BOT - ((Math.log10(Math.max(ymin, v)) - Math.log10(ymin)) / (Math.log10(ymax) - Math.log10(ymin))) * (BOT - TOP)
    : (v) => BOT - ((Math.max(ymin, Math.min(ymax, v)) - ymin) / (ymax - ymin)) * (BOT - TOP);

  // Gitter und Ticks. y zuerst, damit die Punkte darueber liegen.
  const yTicks = log ? logTicks(ymin, ymax) : schoeneSchritte(ymin, ymax, 4);
  let gitter = '';
  yTicks.forEach((v) => {
    const yy = y(v);
    if (yy < TOP - 1 || yy > BOT + 1) return;
    gitter += '<line x1="' + L + '" y1="' + yy.toFixed(1) + '" x2="' + R + '" y2="' + yy.toFixed(1) + '" ' + GITTER + ' />'
      + '<text x="' + (L - 7) + '" y="' + (yy + 3.5).toFixed(1) + '" ' + INK62 + ' ' + TICK + ' text-anchor="end">'
      + esc(k.yTickText ? k.yTickText(v) : fmtZahl(v)) + '</text>';
  });
  schoeneSchritte(xmin, xmax, 5).forEach((v) => {
    const xx = x(v);
    gitter += '<line x1="' + xx.toFixed(1) + '" y1="' + TOP + '" x2="' + xx.toFixed(1) + '" y2="' + BOT + '" ' + GITTER + ' />'
      + '<text x="' + xx.toFixed(1) + '" y="' + (BOT + 15) + '" ' + INK62 + ' ' + TICK + ' text-anchor="middle">'
      + esc(k.xTickText ? k.xTickText(v) : fmtZahl(v)) + '</text>';
  });

  // Die schattierte Zone: unterhalb des Gatters ist ein Punkt zu duenn
  // belegt. Sie liegt unter den Marken, nicht ueber ihnen.
  let zone = '';
  if (k.gate && typeof k.gate.wert === 'number' && k.gate.wert > ymin) {
    const gy = y(k.gate.wert);
    zone = '<rect x="' + L + '" y="' + gy.toFixed(1) + '" width="' + (R - L) + '" height="' + Math.max(0, BOT - gy).toFixed(1)
      + '" style="fill:rgba(var(--ink),.06)" />'
      + '<line x1="' + L + '" y1="' + gy.toFixed(1) + '" x2="' + R + '" y2="' + gy.toFixed(1)
      + '" style="stroke:rgba(var(--ink),.32)" stroke-width="1" />'
      + (k.gate.text
        ? '<text x="' + (L + 6) + '" y="' + (gy + 13).toFixed(1) + '" ' + INK62 + ' ' + TICK + '>' + esc(k.gate.text) + '</text>'
        : '');
  }
  // Referenzlinien ohne Zone: eine Schwelle, die keine Flaeche einschliesst,
  // wird als Linie gezeichnet, eine leere Schattierung waere Zierrat.
  yRefs.forEach((r) => {
    const ry = y(r.wert);
    if (ry < TOP - 1 || ry > BOT + 1) return;
    zone += '<line x1="' + L + '" y1="' + ry.toFixed(1) + '" x2="' + R + '" y2="' + ry.toFixed(1)
      + '" style="stroke:rgba(var(--ink),.4)" stroke-width="1" stroke-dasharray="3 3" />'
      + (r.label ? '<text x="' + (L + 6) + '" y="' + (ry - 5).toFixed(1) + '" ' + INK62 + ' ' + TICK + '>' + esc(r.label) + '</text>' : '');
  });
  xRefs.forEach((r) => {
    const rx = x(r.wert);
    zone += '<line x1="' + rx.toFixed(1) + '" y1="' + TOP + '" x2="' + rx.toFixed(1) + '" y2="' + BOT
      + '" style="stroke:rgba(var(--ink),.4)" stroke-width="1" stroke-dasharray="3 3" />'
      + (r.label ? '<text x="' + (rx + 4).toFixed(1) + '" y="' + (TOP + 10) + '" ' + INK62 + ' ' + TICK + '>' + esc(r.label) + '</text>' : '');
  });

  // Marken. Die Spanne zuerst (liegt unter dem Punkt), dann der Punkt mit
  // 2px-Ring in der Flaechenfarbe, damit dichte Wolken lesbar bleiben.
  let marken = '';
  pts.forEach((p) => {
    const cx = x(p.x), cy = y(p.y);
    const farbe = p.hervor ? 'var(--s1)' : 'var(--s4)';
    if (Array.isArray(p.band) && p.band.length === 2 && typeof p.band[0] === 'number' && typeof p.band[1] === 'number') {
      marken += '<line x1="' + x(p.band[0]).toFixed(1) + '" y1="' + cy.toFixed(1) + '" x2="' + x(p.band[1]).toFixed(1)
        + '" y2="' + cy.toFixed(1) + '" style="stroke:' + farbe + '" stroke-opacity=".38" stroke-width="2" stroke-linecap="round" />';
    }
    marken += '<circle cx="' + cx.toFixed(1) + '" cy="' + cy.toFixed(1) + '" r="4.5" style="fill:' + farbe
      + '; stroke:var(--panel)" stroke-width="2"><title>' + esc(p.tip || p.label || '') + '</title></circle>';
  });

  // Direktbeschriftung fuer wenige Punkte, nie fuer alle. Sie sitzt rechts
  // vom Punkt und klappt am rechten Rand nach links.
  let namen = '';
  const wieViele = k.labelN != null ? k.labelN : 5;
  pts.slice().sort((a, b) => b.x - a.x).slice(0, wieViele).forEach((p) => {
    if (!p.label) return;
    const cx = x(p.x), cy = y(p.y);
    const links = cx > L + (R - L) * 0.7;
    namen += '<text x="' + (cx + (links ? -9 : 9)).toFixed(1) + '" y="' + (cy + 3.5).toFixed(1) + '" ' + INK72 + ' '
      + TICK + ' text-anchor="' + (links ? 'end' : 'start') + '">' + esc(p.label) + '</text>';
  });

  const rahmen = '<line x1="' + L + '" y1="' + BOT + '" x2="' + R + '" y2="' + BOT + '" style="stroke:rgba(var(--ink),.28)" stroke-width="1" />'
    + '<line x1="' + L + '" y1="' + TOP + '" x2="' + L + '" y2="' + BOT + '" style="stroke:rgba(var(--ink),.28)" stroke-width="1" />';

  const svg = '<svg width="100%" viewBox="0 0 ' + B + ' ' + H + '" role="img" aria-label="' + esc(k.titel || 'scatter')
    + '" style="display:block; max-width:680px">'
    + gitter + zone + rahmen + marken + namen
    + achsenTitel(k.xLabel, (L + R) / 2, H - 8, false)
    + achsenTitel(k.yLabel, 12, (TOP + BOT) / 2, true)
    + '</svg>';
  return karte(k.titel, k.einheit, k.hinweis, svg, k.fussnote, k.fussnoteHtml);
}

/** Histogramm: Saeulen ueber gleich breiten Bins, mit Referenzlinien.
 *
 *  k: { titel, einheit, hinweis, fussnote, xLabel, yLabel,
 *       bins: [{ von, bis, anzahl, hervor? }],
 *       hervorLabel, gesamtLabel,          // Legende, sobald es zwei Lagen gibt
 *       referenzen: [{ wert, label }],     // senkrecht, in x-Einheiten
 *       xTickText, zaehlEinheit, hoehe,
 *       fussnoteHtml (fertiges Vorbehalts-Markup, siehe karte) }
 *  Ohne einen Bin mit Inhalt kein Diagramm.
 */
export function histogramm(k) {
  const bins = (k && Array.isArray(k.bins) ? k.bins : [])
    .filter((b) => b && typeof b.von === 'number' && typeof b.bis === 'number' && (+b.anzahl || 0) >= 0);
  if (!bins.length || !bins.some((b) => (+b.anzahl || 0) > 0)) return '';
  const B = 660, H = k.hoehe || 210;
  const L = 52, R = B - 14, TOP = 14, BOT = H - 42;
  const xmin = Math.min(...bins.map((b) => b.von));
  const xmax = Math.max(...bins.map((b) => b.bis));
  const spanne = xmax > xmin ? xmax - xmin : 1;
  const x = (v) => L + ((v - xmin) / spanne) * (R - L);
  const maxN = Math.max(1, ...bins.map((b) => +b.anzahl || 0));
  const yTicks = schoeneSchritte(0, maxN, 3);
  const yMax = Math.max(maxN, yTicks[yTicks.length - 1] || maxN);
  const y = (n) => BOT - (n / yMax) * (BOT - TOP);

  let gitter = '';
  yTicks.forEach((v) => {
    const yy = y(v);
    if (yy < TOP - 1 || yy > BOT + 1) return;
    gitter += '<line x1="' + L + '" y1="' + yy.toFixed(1) + '" x2="' + R + '" y2="' + yy.toFixed(1) + '" ' + GITTER + ' />'
      + '<text x="' + (L - 7) + '" y="' + (yy + 3.5).toFixed(1) + '" ' + INK62 + ' ' + TICK + ' text-anchor="end">' + esc(fmtZahl(v)) + '</text>';
  });

  // Saeulen: 2px Luecke in der Flaechenfarbe zwischen benachbarten Bins,
  // 4px Radius nur am Datenende, eckig auf der Grundlinie.
  const RAD = 4;
  const binText = (v) => (k.xTickText ? k.xTickText(v) : fmtZahl(v));
  let saeulen = '';
  bins.forEach((b) => {
    const n = +b.anzahl || 0;
    if (n <= 0) return;
    const x0 = x(b.von) + 1;
    const w = Math.max(1.5, x(b.bis) - 1 - x0);
    const beschriftung = binText(b.von) + ' to ' + binText(b.bis);
    const h = Math.max(1.5, BOT - y(n));
    const r = Math.max(0, Math.min(RAD, w / 2, h));
    const oben = BOT - h;
    const pfad = 'M ' + x0.toFixed(1) + ' ' + BOT + ' V ' + (oben + r).toFixed(1)
      + ' Q ' + x0.toFixed(1) + ' ' + oben.toFixed(1) + ' ' + (x0 + r).toFixed(1) + ' ' + oben.toFixed(1)
      + ' H ' + (x0 + w - r).toFixed(1)
      + ' Q ' + (x0 + w).toFixed(1) + ' ' + oben.toFixed(1) + ' ' + (x0 + w).toFixed(1) + ' ' + (oben + r).toFixed(1)
      + ' V ' + BOT + ' Z';
    saeulen += '<path d="' + pfad + '" style="fill:var(--s4)" fill-opacity=".85"><title>'
      + esc(beschriftung + ' · ' + fmtZahl(n) + (k.zaehlEinheit ? ' ' + k.zaehlEinheit : '')
        + (b.hervor != null ? ' · ' + fmtZahl(+b.hervor || 0) + ' ' + (k.hervorLabel || 'flagged') : ''))
      + '</title></path>';
    if (b.hervor != null && (+b.hervor || 0) > 0) {
      const hh = Math.max(1.5, BOT - y(+b.hervor));
      saeulen += '<rect x="' + x0.toFixed(1) + '" y="' + (BOT - hh).toFixed(1) + '" width="' + w.toFixed(1)
        + '" height="' + hh.toFixed(1) + '" style="fill:var(--s1)" fill-opacity=".9"><title>'
        + esc(beschriftung + ' · ' + fmtZahl(+b.hervor) + ' ' + (k.hervorLabel || 'flagged')) + '</title></rect>';
    }
  });

  // x-Ticks an echten Bin-Kanten, hoechstens sechs Beschriftungen.
  const kanten = bins.map((b) => b.von).concat([xmax]);
  const schritt = Math.max(1, Math.ceil(kanten.length / 6));
  let xLabels = '';
  kanten.forEach((v, i) => {
    if (i % schritt !== 0 && i !== kanten.length - 1) return;
    // Die aeussersten beiden Marken haengen sonst zur Haelfte aus dem SVG:
    // im Browser gemessen, die letzte Marke von RESULT PER CLOSED COPY
    // stand zur Haelfte rechts ausserhalb der Zeichenflaeche.
    const anker = i === 0 ? 'start' : i === kanten.length - 1 ? 'end' : 'middle';
    xLabels += '<text x="' + x(v).toFixed(1) + '" y="' + (BOT + 15) + '" ' + INK62 + ' ' + TICK + ' text-anchor="' + anker + '">'
      + esc(binText(v)) + '</text>';
  });

  let refs = '';
  (Array.isArray(k.referenzen) ? k.referenzen : []).forEach((r) => {
    if (!r || typeof r.wert !== 'number' || r.wert < xmin || r.wert > xmax) return;
    const rx = x(r.wert);
    refs += '<line x1="' + rx.toFixed(1) + '" y1="' + TOP + '" x2="' + rx.toFixed(1) + '" y2="' + BOT
      + '" style="stroke:rgba(var(--ink),.4)" stroke-width="1" stroke-dasharray="3 3" />'
      + (r.label ? '<text x="' + (rx + 4).toFixed(1) + '" y="' + (TOP + 10) + '" ' + INK62 + ' ' + TICK + '>' + esc(r.label) + '</text>' : '');
  });

  const grund = '<line x1="' + L + '" y1="' + BOT + '" x2="' + R + '" y2="' + BOT + '" style="stroke:rgba(var(--ink),.28)" stroke-width="1" />';
  const swatch = (farbe, text) => '<div style="display:flex; align-items:center; gap:6px; ' + M + '; font-size:11px; color:rgba(var(--ink),.65)">'
    + '<span style="display:inline-block; width:10px; height:10px; border-radius:2px; background:' + farbe + '"></span>' + esc(text) + '</div>';
  const legende = k.hervorLabel
    ? '<div style="display:flex; gap:14px; flex-wrap:wrap; margin:0 0 6px">'
      + swatch('var(--s4)', k.gesamtLabel || 'all') + swatch('var(--s1)', k.hervorLabel) + '</div>'
    : '';
  const svg = legende + '<svg width="100%" viewBox="0 0 ' + B + ' ' + H + '" role="img" aria-label="' + esc(k.titel || 'histogram')
    + '" style="display:block; max-width:680px">'
    + gitter + saeulen + refs + grund + xLabels
    + achsenTitel(k.xLabel, (L + R) / 2, H - 8, false)
    + achsenTitel(k.yLabel, 11, (TOP + BOT) / 2, true)
    + '</svg>';
  return karte(k.titel, k.einheit, k.hinweis, svg, k.fussnote, k.fussnoteHtml);
}

/** Intervall-Marke: ein Punkt mit seiner Spanne auf einer beschrifteten
 *  Leiste. Kein Diagramm: bei kleinem n ist die Spanne die Information,
 *  nicht die Form.
 *
 *  k: { wert, ci: [lo, hi], domain: [min, max], ticks: [{ wert, text }],
 *       label, breite }
 *  Ohne Wert oder ohne Intervall kommt nichts zurueck.
 */
export function intervallMarke(k) {
  if (!k || typeof k.wert !== 'number' || !Array.isArray(k.ci) || k.ci.length !== 2) return '';
  if (typeof k.ci[0] !== 'number' || typeof k.ci[1] !== 'number') return '';
  const dom = Array.isArray(k.domain) && k.domain.length === 2 ? k.domain : [0, 1];
  const min = dom[0], max = dom[1] > dom[0] ? dom[1] : dom[0] + 1;
  const B = 240, H = 26;
  const L = 4, R = B - 4, Y = 9;
  const x = (v) => L + ((Math.max(min, Math.min(max, v)) - min) / (max - min)) * (R - L);
  const ticks = Array.isArray(k.ticks) && k.ticks.length
    ? k.ticks
    : [{ wert: min, text: String(min) }, { wert: max, text: String(max) }];
  let achse = '<line x1="' + L + '" y1="' + Y + '" x2="' + R + '" y2="' + Y + '" style="stroke:rgba(var(--ink),.14)" stroke-width="4" stroke-linecap="round" />';
  ticks.forEach((t) => {
    if (!t || typeof t.wert !== 'number') return;
    const tx = x(t.wert);
    achse += '<text x="' + tx.toFixed(1) + '" y="' + (H - 2) + '" ' + INK62 + ' font-size="9.5" '
      + 'font-family="IBM Plex Mono, monospace" text-anchor="' + (t.wert <= min ? 'start' : t.wert >= max ? 'end' : 'middle') + '">'
      + esc(t.text) + '</text>';
  });
  const spanne = '<line x1="' + x(k.ci[0]).toFixed(1) + '" y1="' + Y + '" x2="' + x(k.ci[1]).toFixed(1) + '" y2="' + Y
    + '" style="stroke:var(--s4)" stroke-width="4" stroke-linecap="round" stroke-opacity=".55" />';
  const punkt = '<circle cx="' + x(k.wert).toFixed(1) + '" cy="' + Y + '" r="4" style="fill:var(--s4); stroke:var(--panel)" stroke-width="2" />';
  return '<svg width="' + (k.breite || B) + '" viewBox="0 0 ' + B + ' ' + H + '" role="img" aria-label="'
    + esc(k.label || 'interval') + '" style="display:block; max-width:100%">'
    + '<title>' + esc(k.label || '') + '</title>' + achse + spanne + punkt + '</svg>';
}
