// Microstructure — the twelve recorded-book studies, one card each.
//
// Feeds off public/data/microstructure.json (built by
// app/microstructure_report.py). Every number in here comes from that file;
// this module only lays it out. Charts are plain SVG so the page stays
// dependency free like the rest of the terminal.
//
// Each card runs in the order a reader needs: what was analysed, what the
// numbers say, how else they could be read, then the raw rows behind it.

import { esc } from '../util.js';

const M = "font-family:'JetBrains Mono',monospace";
const CARD = 'background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:12px';
const MUTED = 'color:rgba(255,255,255,.55)';
const HR = 'border-top:1px solid rgba(255,255,255,.07); margin-top:20px; padding-top:18px';

const VERDIKT_FARBE = { ja: '#C8F542', nein: '#FF7A7A', offen: '#F5A623' };
const VERDIKT_TEXT = { ja: 'CONFIRMED', nein: 'REFUTED', offen: 'NOT IDENTIFIED' };
const BALKEN_FARBE = { gewinn: '#C8F542', kosten: '#FF4545', summe: '#4F8EF7' };
// Lesart lime, Gegenlesart blau, Grenze grau: drei Farben, damit die
// Gegenlesart nicht wie ein Nachtrag zur Lesart aussieht.
const DEUTUNG_FARBE = { lesart: '#C8F542', gegenlesart: '#4F8EF7', grenze: '#95A0AB' };

// Diagrammgeometrie. Labelspalte links, Balken rechts.
const BREITE = 640;
const LABEL_X = 196;
const PLOT_L = LABEL_X + 12;
const PLOT_R = BREITE - 58;
const ZEILE = 30;

function abschnitt(titel, inhalt, zusatz) {
  if (!inhalt) return '';
  return '<div style="' + HR + '">'
    + '<div style="' + M + '; font-size:10px; letter-spacing:.15em; color:#4F8EF7; margin-bottom:12px">'
    + esc(titel) + (zusatz ? ' <span style="color:rgba(255,255,255,.32)">' + esc(zusatz) + '</span>' : '')
    + '</div>' + inhalt + '</div>';
}

function fmtZahl(wert) {
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
function diagramm(dia) {
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
      const x0 = sk.x(0);
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
function detailBlock(details) {
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

  return '<details style="' + CARD + '; padding:0; overflow:hidden">'
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

function studieKarte(s, i) {
  const farbe = VERDIKT_FARBE[s.verdikt_art] || '#95A0AB';
  const marke = VERDIKT_TEXT[s.verdikt_art] || 'RESULT';

  const zahlenUndDiagramm = '<div style="display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:12px">'
    + diagramm(s.diagramm) + zahlenBlock(s.zahlen) + '</div>';

  return '<div style="' + CARD + '; padding:22px 24px; margin-bottom:18px">'
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

    + abschnitt('WHAT WAS ANALYSED', analyseBlock(s.analyse))
    + abschnitt('WHAT THE NUMBERS SAY',
      '<div style="font-size:13.5px; color:rgba(255,255,255,.75); line-height:1.7; max-width:760px; margin-bottom:14px">'
      + esc(s.einfach) + '</div>' + zahlenUndDiagramm)
    + abschnitt('HOW TO READ IT', deutungBlock(s.interpretation))
    + abschnitt('THE ROWS BEHIND IT', detailBlock(s.details))

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
    + '<div style="display:flex; gap:12px; margin-top:16px; flex-wrap:wrap">'
    + kachel(z.gesamt || 0, 'STUDIES', '#fff')
    + kachel(z.nein || 0, 'REFUTED', '#FF7A7A')
    + kachel(z.ja || 0, 'CONFIRMED', '#C8F542')
    + kachel(z.offen || 0, 'NOT IDENTIFIED', '#F5A623')
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
