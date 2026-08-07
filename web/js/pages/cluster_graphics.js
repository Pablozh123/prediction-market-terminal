// Zwei Bilder zum Co-Trading-Screen, nebeneinander und als Bild brauchbar.
//
// Links der Graph: wer haengt mit wem zusammen. Rechts die Matrix: warum.
// Eine Kante links ist genau ein Zeilenpaar rechts, das sich in mindestens
// zwei Spalten trifft — die beiden Bilder zeigen dieselbe Tatsache einmal
// als Struktur und einmal als Beleg.
//
// Beide sind reines SVG (wie der Rest des Terminals, kein Chart-Paket), und
// Regel, Fenster und Stichprobe stehen im Bild selbst. Ein Cluster-Bild ohne
// seine Regel ist nicht einzuordnen, und ein Screenshot trennt sich von
// jeder Bildunterschrift, die daneben stuende.

import { esc } from '../util.js';

const M = "font-family:'JetBrains Mono',monospace";
const CARD = 'background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:12px';

// Cluster-Palette. Farben sind gut unterscheidbar und halten auf Dunkel.
const CLUSTER_COLORS = [
  '#C8F542', '#4F8EF7', '#F5A623', '#FF7A7A', '#7DE2D1',
  '#C792EA', '#FFD166', '#8FD694', '#F78FB3', '#9AB0FF'
];

const farbeVon = (i) => CLUSTER_COLORS[i % CLUSTER_COLORS.length];

function kopfzeile(g, m) {
  const k = g.kennzahl || {};
  const chip = (label, wert) =>
    '<div style="' + M + '; font-size:10px; color:rgba(255,255,255,.55); border:1px solid rgba(255,255,255,.14); '
    + 'border-radius:5px; padding:4px 9px; white-space:nowrap">' + esc(label) + ' <span style="color:#fff">'
    + esc(String(wert)) + '</span></div>';
  return '<div style="display:flex; gap:7px; flex-wrap:wrap; margin-top:10px">'
    + chip('WALLETS', k.wallets != null ? k.wallets : '—')
    + chip('LINKS', k.kanten != null ? k.kanten : '—')
    + chip('CLUSTERS', k.cluster != null ? k.cluster : '—')
    + (k.modularitaet != null ? chip('MODULARITY', k.modularitaet) : '')
    + (m && m.cluster ? chip('MATRIX', m.cluster) : '')
    + '</div>';
}

/** Netzwerkgraph: Inseln aus cluster_layout, Kanten nach geteilten Maerkten. */
function graphSvg(g) {
  const knoten = g.knoten || [];
  const kanten = g.kanten || [];
  if (!knoten.length) return '';

  const W = 460, H = 400, PAD = 34;
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
    const farbe = gleich ? farbeVon(clusterIndex.get(a.cluster) || 0) : 'rgba(255,255,255,.28)';
    const staerke = 0.8 + 2.2 * ((e.geteilt || 1) / maxGeteilt);
    return '<line x1="' + X(a.x).toFixed(1) + '" y1="' + Y(a.y).toFixed(1) + '" x2="' + X(b.x).toFixed(1)
      + '" y2="' + Y(b.y).toFixed(1) + '" stroke="' + farbe + '" stroke-opacity="'
      + (gleich ? '.5' : '.35') + '" stroke-width="' + staerke.toFixed(2) + '" />';
  }).join('');

  const knotenSvg = knoten.map((n) => {
    const farbe = farbeVon(clusterIndex.get(n.cluster) || 0);
    const r = 3.4 + 7.6 * Math.sqrt((n.volumen || 0) / maxVol);
    return '<circle cx="' + X(n.x).toFixed(1) + '" cy="' + Y(n.y).toFixed(1) + '" r="' + r.toFixed(1)
      + '" fill="' + farbe + '" fill-opacity=".85" stroke="#0A0D0F" stroke-width="1.2">'
      + '<title>' + esc(n.kurz + ' · ' + n.maerkte + ' markets · ' + n.trades + ' trades') + '</title></circle>';
  }).join('');

  // Bewusst keine Beschriftung im Graphen: in den dichten Inseln liegt sie
  // ueber den Knoten und verdeckt genau das, was gezeigt werden soll. Die
  // Zuordnung uebernimmt die Farblegende darunter, wie in der Abbildung.
  return '<svg width="100%" viewBox="0 0 ' + W + ' ' + H + '" role="img" '
    + 'aria-label="co-trading network of wallets">'
    + kantenSvg + knotenSvg + '</svg>';
}

/** Farbschluessel unter dem Graphen, statt Beschriftung mitten hinein. */
function clusterLegende(g) {
  const cluster = (g.cluster || []).filter((c) => c.groesse >= 2);
  if (!cluster.length) return '';
  return '<div style="display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); '
    + 'gap:5px 12px; margin-top:12px">'
    + cluster.map((c, i) =>
      '<div style="display:flex; align-items:center; gap:7px">'
      + '<span style="width:9px; height:9px; border-radius:2px; flex:none; background:'
      + farbeVon(i) + '"></span>'
      + '<span style="' + M + '; font-size:10px; color:rgba(255,255,255,.6); white-space:nowrap">'
      + esc(c.name + ' · ' + c.groesse + 'w · ' + c.volumen_label) + '</span></div>'
    ).join('')
    + '</div>';
}

/** Matrix: Wallet-Zeilen mal Markt-Spalten, Fuellung nach Notional. */
function matrixSvg(m) {
  const wallets = m.wallets || [];
  const maerkte = m.maerkte || [];
  const zellen = m.zellen || [];
  if (!wallets.length || !maerkte.length) return '';

  const LABEL_W = 116, KOPF_H = 26, FUSS_H = 18;
  const zellBreite = 26, zellHoehe = 21, luecke = 2;
  const W = LABEL_W + maerkte.length * (zellBreite + luecke) + 8;
  const H = KOPF_H + wallets.length * (zellHoehe + luecke) + FUSS_H;
  const maxWert = Math.max(...zellen.flat().filter((v) => v > 0), 1);

  const kopf = maerkte.map((mk, j) =>
    '<text x="' + (LABEL_W + j * (zellBreite + luecke) + zellBreite / 2) + '" y="' + (KOPF_H - 9)
    + '" text-anchor="middle" font-size="9.5" font-family="JetBrains Mono, monospace" '
    + 'fill="rgba(255,255,255,.5)">M' + (j + 1) + '</text>').join('');

  const reihen = wallets.map((w, i) => {
    const y = KOPF_H + i * (zellHoehe + luecke);
    const label = '<text x="' + (LABEL_W - 10) + '" y="' + (y + zellHoehe / 2 + 3.5) + '" text-anchor="end" '
      + 'font-size="10" font-family="JetBrains Mono, monospace" fill="rgba(255,255,255,.65)">'
      + esc(w.kurz) + '</text>';
    const felder = maerkte.map((mk, j) => {
      const wert = (zellen[i] || [])[j] || 0;
      const x = LABEL_W + j * (zellBreite + luecke);
      if (wert <= 0) {
        return '<rect x="' + x + '" y="' + y + '" width="' + zellBreite + '" height="' + zellHoehe
          + '" rx="2.5" fill="rgba(255,255,255,.045)" />';
      }
      // Wurzel-Skala: sonst verschwinden kleine Beruehrungen ganz, und die
      // Frage ist ja, ob eine Ueberschneidung ueberhaupt stattfand.
      const staerke = 0.28 + 0.72 * Math.sqrt(wert / maxWert);
      return '<rect x="' + x + '" y="' + y + '" width="' + zellBreite + '" height="' + zellHoehe
        + '" rx="2.5" fill="#C8F542" fill-opacity="' + staerke.toFixed(2) + '">'
        + '<title>' + esc(w.kurz + ' · ' + mk.markt + ' · ' + mk.seite + ' · $'
          + Math.round(wert).toLocaleString('en-US')) + '</title></rect>';
    }).join('');
    return label + felder;
  }).join('');

  const fuss = '<text x="' + LABEL_W + '" y="' + (H - 5) + '" font-size="9.5" '
    + 'font-family="JetBrains Mono, monospace" fill="rgba(255,255,255,.38)">'
    + esc('filled = wallet took that side · shade = notional') + '</text>';

  return '<svg width="100%" viewBox="0 0 ' + W + ' ' + H + '" role="img" '
    + 'aria-label="wallet by market overlap matrix">' + kopf + reihen + fuss + '</svg>';
}

function marktLegende(m) {
  const maerkte = m.maerkte || [];
  if (!maerkte.length) return '';
  return '<div style="margin-top:10px; display:grid; gap:3px">'
    + maerkte.map((mk, j) =>
      '<div style="display:flex; gap:8px; align-items:baseline; font-size:11px">'
      + '<span style="' + M + '; color:rgba(255,255,255,.4); min-width:26px">M' + (j + 1) + '</span>'
      + '<span style="color:rgba(255,255,255,.66); overflow:hidden; text-overflow:ellipsis; white-space:nowrap">'
      + esc(mk.markt) + '</span>'
      + '<span style="' + M + '; color:#C8F542; font-size:10px; white-space:nowrap">' + esc(mk.seite) + '</span>'
      + '<span style="' + M + '; color:rgba(255,255,255,.35); font-size:10px; white-space:nowrap">'
      + mk.wallets + 'w</span></div>'
    ).join('')
    + '</div>';
}

function tafel(titel, unter, inhalt, fuss) {
  return '<div style="' + CARD + '; padding:16px 18px; min-width:0">'
    + '<div style="' + M + '; font-size:10px; letter-spacing:.14em; color:#4F8EF7">' + esc(titel) + '</div>'
    + '<div style="font-size:12.5px; color:rgba(255,255,255,.55); margin-top:6px; line-height:1.5">' + esc(unter) + '</div>'
    + '<div style="margin-top:12px">' + inhalt + '</div>'
    + (fuss || '') + '</div>';
}

function hinweisKarte(text, farbe) {
  return '<div style="' + CARD + '; padding:20px 22px; margin-bottom:16px">'
    + '<div style="' + M + '; font-size:10px; letter-spacing:.14em; color:#4F8EF7">CO-TRADING STRUCTURE</div>'
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
      'rgba(255,255,255,.6)');
  }
  if (live._quelle === 'fehler') {
    return hinweisKarte(
      'The risk endpoint did not answer: ' + (live._fehler || 'unknown error')
      + '. Nothing is shown rather than a stale or invented network.',
      '#F5A623');
  }
  const g = live.graph;
  const m = live.matrix || {};
  if (!g || !g.knoten || !g.knoten.length) {
    return hinweisKarte(
      'No co-trading cluster in the current window. That is a result, not a gap: once sports and '
      + 'crypto are excluded, the wallets left in the insider-prone markets do not repeatedly meet '
      + 'each other.',
      'rgba(255,255,255,.7)');
  }

  return '<div style="' + CARD + '; padding:18px 20px; margin-bottom:16px">'
    + '<div style="display:flex; align-items:flex-start; justify-content:space-between; gap:18px; flex-wrap:wrap">'
    + '<div style="max-width:640px">'
    + '<div style="' + M + '; font-size:10px; letter-spacing:.14em; color:#4F8EF7">CO-TRADING STRUCTURE</div>'
    + '<div style="font-size:17px; font-weight:600; margin-top:6px">Wallets that keep meeting in the same markets</div>'
    + '</div></div>'
    + kopfzeile(g, m)
    + '<div style="' + M + '; font-size:10.5px; color:rgba(255,255,255,.45); margin-top:10px; line-height:1.6">'
    + 'RULE · ' + esc(g.regel || 'not stated')
    + (g.fenster ? '<br>WINDOW · ' + esc(g.fenster) : '')
    + '<br>SCOPE · insider-prone markets only, sports crypto and weather excluded</div>'

    + '<div style="display:grid; grid-template-columns:repeat(auto-fit,minmax(330px,1fr)); gap:14px; margin-top:14px">'
    + tafel('WHO MOVES WITH WHOM',
      'Each dot is a wallet, sized by the money it moved. A line means the two took the same side of the same markets. Colour is the community the graph splits into.',
      graphSvg(g), clusterLegende(g))
    + tafel('WHY THEY ARE LINKED',
      'The same wallets against the markets they actually share. Every line on the left is a pair of rows here that meets in at least two columns.',
      matrixSvg(m), marktLegende(m))
    + '</div></div>';
}
