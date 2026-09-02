// Kraeftelayout fuer kleine Netzwerke (Wallet-Graph-Seite), abhaengigkeitsfrei
// wie der Rest des Terminals.
//
// Deterministisch: derselbe Graph landet bei jedem Render an derselben
// Stelle (eigener Zufallsgenerator mit festem Saatwert), sonst spraenge das
// Bild bei jedem 30-Sekunden-Poll. Bis etwa 120 Knoten reicht das naive
// O(n^2) je Runde; darueber kappt der Aufrufer die Menge, denn ein Bild mit
// 500 Punkten liest ohnehin niemand.

function mulberry32(seed) {
  let a = seed >>> 0;
  return function () {
    a = (a + 0x6D2B79F5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Positionen fuer nodes [{ id }] und edges [{ a, b, weight? }] in einer
 *  Box breite x hoehe, mit rand Abstand zum Rand. Rueckgabe: Map id ->
 *  { x, y }. Knoten ohne Kante werden am Rand in einen Ring gelegt, damit
 *  sie das Bild nicht in die Mitte ziehen. */
export function layoutNetwork(nodes, edges, opts) {
  const o = Object.assign({ breite: 900, hoehe: 420, rand: 40, runden: 260, seed: 7 }, opts || {});
  const ids = nodes.map((n) => String(n.id));
  const n = ids.length;
  const pos = new Map();
  if (!n) return pos;
  const index = new Map(ids.map((id, i) => [id, i]));
  const zufall = mulberry32(o.seed);
  const grad = new Array(n).fill(0);
  const kanten = [];
  (edges || []).forEach((e) => {
    const a = index.get(String(e.a)), b = index.get(String(e.b));
    if (a == null || b == null || a === b) return;
    kanten.push([a, b, Math.max(0.2, +e.weight || 1)]);
    grad[a] += 1; grad[b] += 1;
  });
  const W = o.breite - 2 * o.rand, H = o.hoehe - 2 * o.rand;
  const x = new Float64Array(n), y = new Float64Array(n);
  for (let i = 0; i < n; i += 1) {
    const winkel = zufall() * Math.PI * 2;
    const r = 0.25 + 0.2 * zufall();
    x[i] = W / 2 + Math.cos(winkel) * r * W;
    y[i] = H / 2 + Math.sin(winkel) * r * H;
  }
  // Fruchterman-Reingold: ideale Kantenlaenge k aus der Flaeche je Knoten.
  const k = Math.sqrt((W * H) / Math.max(1, n)) * 0.9;
  const dx = new Float64Array(n), dy = new Float64Array(n);
  let temp = Math.max(W, H) / 8;
  const abkuehlung = temp / (o.runden + 1);
  for (let runde = 0; runde < o.runden; runde += 1) {
    dx.fill(0); dy.fill(0);
    for (let i = 0; i < n; i += 1) {
      for (let j = i + 1; j < n; j += 1) {
        let ddx = x[i] - x[j], ddy = y[i] - y[j];
        let d2 = ddx * ddx + ddy * ddy;
        if (d2 < 0.01) { ddx = (zufall() - 0.5) * 0.1; ddy = (zufall() - 0.5) * 0.1; d2 = ddx * ddx + ddy * ddy; }
        const d = Math.sqrt(d2);
        const f = (k * k) / d;
        dx[i] += (ddx / d) * f; dy[i] += (ddy / d) * f;
        dx[j] -= (ddx / d) * f; dy[j] -= (ddy / d) * f;
      }
    }
    kanten.forEach(([a, b, w]) => {
      const ddx = x[a] - x[b], ddy = y[a] - y[b];
      const d = Math.max(0.1, Math.sqrt(ddx * ddx + ddy * ddy));
      const f = ((d * d) / k) * w;
      dx[a] -= (ddx / d) * f; dy[a] -= (ddy / d) * f;
      dx[b] += (ddx / d) * f; dy[b] += (ddy / d) * f;
    });
    for (let i = 0; i < n; i += 1) {
      // Schwerkraft zur Mitte, staerker fuer Knoten ohne Kanten, damit
      // freie Punkte nicht davondriften.
      const g = grad[i] ? 0.03 : 0.08;
      dx[i] += (W / 2 - x[i]) * g; dy[i] += (H / 2 - y[i]) * g;
      const d = Math.max(0.1, Math.sqrt(dx[i] * dx[i] + dy[i] * dy[i]));
      const schritt = Math.min(d, temp);
      x[i] = Math.min(W, Math.max(0, x[i] + (dx[i] / d) * schritt));
      y[i] = Math.min(H, Math.max(0, y[i] + (dy[i] / d) * schritt));
    }
    temp = Math.max(0.5, temp - abkuehlung);
  }
  // Auf die Box strecken, damit das Bild die Flaeche nutzt.
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  for (let i = 0; i < n; i += 1) {
    if (x[i] < minX) minX = x[i]; if (x[i] > maxX) maxX = x[i];
    if (y[i] < minY) minY = y[i]; if (y[i] > maxY) maxY = y[i];
  }
  const sx = maxX > minX ? W / (maxX - minX) : 1, sy = maxY > minY ? H / (maxY - minY) : 1;
  for (let i = 0; i < n; i += 1) {
    pos.set(ids[i], {
      x: o.rand + (n === 1 ? W / 2 : (x[i] - minX) * sx),
      y: o.rand + (n === 1 ? H / 2 : (y[i] - minY) * sy),
      grad: grad[i]
    });
  }
  return pos;
}
