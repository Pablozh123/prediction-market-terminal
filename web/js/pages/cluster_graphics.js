// Das eine Bild des Co-Trading-Screens: der Graph, wer mit wem zusammenhaengt.
//
// Frueher standen hier zwei Bilder nebeneinander (Graph + Wallet-Markt-
// Matrix). Die Matrix war bei 10.5px Zellenbeschriftung nicht lesbar und
// beantwortete "warum verbunden?" schlechter als eine Zeile Text pro
// Cluster — der Beleg (geteilte Maerkte, Mitglieder) steht jetzt in den
// Cluster-Karten unter dem Bild (trader_pages), farblich an den Graphen
// gekoppelt. Hier bleibt: Regel, Fenster, Graph mit beschrifteten Knoten.
//
// Reines SVG wie der Rest des Terminals; Regel und Fenster stehen im Bild
// selbst, denn ein Cluster-Bild ohne seine Regel ist nicht einzuordnen.

import { esc } from '../util.js';

const M = "font-family:'IBM Plex Mono',monospace";
const CARD = 'background:var(--panel); border:1px solid rgba(var(--ink),.09); border-radius:6px';

// Cluster-Palette. Farben sind gut unterscheidbar und halten auf Dunkel.
const CLUSTER_COLORS = [
  'var(--accent)', 'var(--info)', 'var(--warn)', 'var(--neg-soft)', 'var(--cat-teal)',
  'var(--cat-violet)', 'var(--cat-gold)', '#8FD694', '#F78FB3', 'var(--cat-blue2)'
];

const farbeVon = (i) => CLUSTER_COLORS[i % CLUSTER_COLORS.length];

/** Farbe eines Clusters (per id) — dieselbe Zuordnung wie im Graphen, damit
 *  die Karten unter dem Bild die Farbe des Bildes tragen. */
export function clusterFarbe(graph, id) {
  const cluster = (graph && graph.cluster) || [];
  const i = cluster.findIndex((c) => c.id === id);
  return farbeVon(i >= 0 ? i : 0);
}

function kopfzeile(g) {
  const k = g.kennzahl || {};
  const chip = (label, wert) =>
    '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.6); border:1px solid rgba(var(--ink),.14); '
    + 'border-radius:4px; padding:4px 9px; white-space:nowrap">' + esc(label) + ' <span style="color:var(--text)">'
    + esc(String(wert)) + '</span></div>';
  // WALLETS traegt seinen Nenner mit: 41 von 300 gescreenten ist eine andere
  // Aussage als 41 von 41. LIFT ist die Kante gegen ihre Basisrate — bei 1.0
  // treffen sich zwei Wallets genau so oft, wie zwei gleich aktive Wallets
  // sich ohne jede Absprache treffen.
  const wallets = k.wallets != null
    ? (k.wallets_im_tape ? k.wallets + ' / ' + k.wallets_im_tape : String(k.wallets))
    : '—';
  return '<div style="display:flex; gap:7px; flex-wrap:wrap; margin-top:10px">'
    + chip('WALLETS', wallets)
    + chip('LINKS', k.kanten != null ? k.kanten : '—')
    + chip('CLUSTERS', k.cluster != null ? k.cluster : '—')
    + (k.lift_median != null ? chip('MEDIAN LIFT', k.lift_median + '×') : '')
    + (k.modularitaet != null ? chip('MODULARITY', k.modularitaet) : '')
    + '</div>';
}

/** Die Kontrolle unter dem Bild: dieselbe Regel auf gemischten Wallet-Namen.
 *  Ohne sie liest sich jedes Insel-Bild als Fund, obwohl die Regel auch auf
 *  Rauschen Inseln zeichnet. */
function nullmodellZeile(g) {
  const n = g.nullmodell;
  if (!n || !n.runs) return '';
  const wie = n.cluster > 0
    ? 'the same rule on a shuffled wallet column still returns ' + esc(String(n.cluster))
      + ' cluster' + (n.cluster === 1 ? '' : 's') + ' over ' + esc(String(n.kanten)) + ' links'
      + (n.lift_median != null ? ' at a median lift of ' + esc(String(n.lift_median)) + '×' : '')
      + ' — read the picture against that, not against zero'
    : 'the same rule on a shuffled wallet column returns nothing';
  return '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.55); margin-top:8px; line-height:1.6">'
    + 'CONTROL · ' + wie + ' (' + esc(String(n.runs)) + ' shuffle' + (n.runs === 1 ? '' : 's') + ')</div>';
}

/** Netzwerkgraph: Inseln aus cluster_layout, Kanten nach geteilten Maerkten.
 *  Knoten tragen ihr Wallet-Kuerzel als Beschriftung, solange das Bild das
 *  hergibt (bis 14 Knoten alle, darueber nur die groessten fuenf). */
function graphSvg(g) {
  const knoten = g.knoten || [];
  const kanten = g.kanten || [];
  if (!knoten.length) return '';

  const W = 720, H = 340, PAD = 46;
  const sx = (g.spanne && g.spanne.x) || [0, 1];
  const sy = (g.spanne && g.spanne.y) || [0, 1];
  const spanX = Math.max(sx[1] - sx[0], 0.001);
  const spanY = Math.max(sy[1] - sy[0], 0.001);
  // Gleicher Massstab auf beiden Achsen, sonst verzerrt die Inselform.
  const skala = Math.min((W - 2 * PAD) / spanX, (H - 2 * PAD) / spanY);
  const mx = (W - spanX * skala) / 2;
  const my = (H - spanY * skala) / 2;
  const X = (x) => mx + (x - sx[0]) * skala;
  const Y = (y) => my + (y - sy[0]) * skala;

  const clusterIndex = new Map((g.cluster || []).map((c, i) => [c.id, i]));
  const maxVol = Math.max(...knoten.map((n) => n.volumen || 0), 1);
  const maxGeteilt = Math.max(...kanten.map((e) => e.geteilt || 0), 1);

  const kantenSvg = kanten.map((e) => {
    const a = knoten[e.a], b = knoten[e.b];
    if (!a || !b) return '';
    const gleich = a.cluster === b.cluster;
    const farbe = gleich ? farbeVon(clusterIndex.get(a.cluster) || 0) : 'rgba(var(--ink),.5)';
    const staerke = 1.0 + 2.4 * ((e.geteilt || 1) / maxGeteilt);
    const basis = e.lift != null
      ? ' · ' + e.lift + '× the ' + (e.erwartet != null ? e.erwartet : '?') + ' two equally busy wallets share by chance'
      : '';
    return '<line x1="' + X(a.x).toFixed(1) + '" y1="' + Y(a.y).toFixed(1) + '" x2="' + X(b.x).toFixed(1)
      + '" y2="' + Y(b.y).toFixed(1) + '" style="stroke:' + farbe + '" stroke-opacity="'
      + (gleich ? '.55' : '.35') + '" stroke-width="' + staerke.toFixed(2) + '">'
      + '<title>' + esc((a.kurz || '') + ' + ' + (b.kurz || '') + ' · ' + (e.geteilt || 1) + ' shared market' + ((e.geteilt || 1) === 1 ? '' : 's') + basis) + '</title></line>';
  }).join('');

  // Beschriftung: das Wallet-Kuerzel neben dem Punkt. Die alte Fassung liess
  // sie ganz weg und verwies auf Hover-Tooltips — auf einem Bild, das sagen
  // soll WER sich bewegt, ist ein unbeschrifteter Punkt keine Antwort.
  const beschriften = knoten.length <= 14
    ? new Set(knoten.map((_, i) => i))
    : new Set(knoten.map((n, i) => [n.volumen || 0, i]).sort((a, b) => b[0] - a[0]).slice(0, 5).map((p) => p[1]));

  const knotenSvg = knoten.map((n, i) => {
    const farbe = farbeVon(clusterIndex.get(n.cluster) || 0);
    const r = 4.5 + 9 * Math.sqrt((n.volumen || 0) / maxVol);
    const cx = X(n.x), cy = Y(n.y);
    const links = cx > W / 2;
    const label = beschriften.has(i)
      ? '<text x="' + (links ? (cx - r - 5).toFixed(1) : (cx + r + 5).toFixed(1)) + '" y="' + (cy + 3.5).toFixed(1)
        + '" text-anchor="' + (links ? 'end' : 'start') + '" font-size="11" font-family="IBM Plex Mono, monospace" '
        + 'style="fill:rgba(var(--ink),.78)">' + esc(n.kurz || '') + '</text>'
      : '';
    return '<circle cx="' + cx.toFixed(1) + '" cy="' + cy.toFixed(1) + '" r="' + r.toFixed(1)
      + '" style="fill:' + farbe + '; stroke:var(--bg)" fill-opacity=".9" stroke-width="1.2">'
      + '<title>' + esc(n.kurz + ' · ' + n.maerkte + ' markets · ' + n.trades + ' trades') + '</title></circle>' + label;
  }).join('');

  return '<svg width="100%" viewBox="0 0 ' + W + ' ' + H + '" role="img" '
    + 'aria-label="co-trading network of wallets">'
    + kantenSvg + knotenSvg + '</svg>';
}

function hinweisKarte(text, farbe) {
  return '<div style="' + CARD + '; padding:20px 22px; margin-bottom:16px">'
    + '<div style="' + M + '; font-size:11px; letter-spacing:.14em; color:var(--info)">CO-TRADING STRUCTURE</div>'
    + '<div style="font-size:13.5px; color:' + farbe + '; margin-top:10px; line-height:1.6; max-width:720px">'
    + esc(text) + '</div></div>';
}

export function renderClusterGraphics(live) {
  // Noch keine Antwort vom Server ist etwas anderes als kein Cluster. Der
  // erste Aufbau paged den Tape und holt Marktkategorien, das dauert eine
  // Weile, und in der Zeit hier "kein Cluster" zu behaupten waere schlicht
  // falsch.
  if (!live) {
    return hinweisKarte(
      'Loading the whale tape and building the network. The first run pages about a day of '
      + 'prints and looks up the market categories, so this takes a moment.',
      'rgba(var(--ink),.6)');
  }
  if (live._quelle === 'fehler') {
    return hinweisKarte(
      'The risk endpoint did not answer: ' + (live._fehler || 'unknown error')
      + '. Nothing is shown rather than a stale or invented network.',
      'var(--warn)');
  }
  const g = live.graph;
  if (!g || !g.knoten || !g.knoten.length) {
    return hinweisKarte(
      'No co-trading cluster in the current window. That is a result, not a gap: once sports and '
      + 'crypto are excluded, the wallets left in the insider-prone markets do not repeatedly meet '
      + 'each other.',
      'rgba(var(--ink),.7)');
  }

  return '<div style="' + CARD + '; padding:18px 20px; margin-bottom:14px">'
    + '<div style="' + M + '; font-size:11px; letter-spacing:.14em; color:var(--info)">CO-TRADING STRUCTURE</div>'
    + '<div style="font-size:17px; font-weight:600; margin-top:6px">Wallets that keep meeting in the same markets</div>'
    + kopfzeile(g)
    + '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.62); margin-top:10px; line-height:1.6">'
    + 'RULE · ' + esc(g.regel || 'not stated')
    + (g.fenster ? '<br>WINDOW · ' + esc(g.fenster) : '')
    + '<br>SCOPE · insider-prone markets only, sports crypto and weather excluded'
    + (g.stand_utc ? '<br>SNAPSHOT · ' + esc(String(g.stand_utc)) : '')
    + '</div>'
    + nullmodellZeile(g)
    + '<div style="margin-top:14px">' + graphSvg(g) + '</div>'
    + '<div style="font-size:12px; color:rgba(var(--ink),.62); margin-top:8px; line-height:1.5">'
    + 'Each dot is one wallet, sized by the money it moved · a line means the two bought the same side of the same markets, thicker = more shared markets · colours are the groups detailed below · hover a line for how far above the chance rate that pair sits.'
    + '</div></div>';
}
