// Squarified treemap layout (Bruls, Huizing, van Wijk 2000) — pure geometry.
//
// squarify(items, width, height) takes items with a positive `value` and
// returns one rectangle per item, {x, y, w, h, item}, tiling the given box so
// that every tile's area is proportional to its value and the tiles come out
// as square as the algorithm can make them. Values <= 0 are dropped (a tile
// with no area is not a tile). The caller decides what "value" is and how
// to colour it; this file knows nothing about markets.

function worst(row, side, total) {
  // Highest aspect ratio a row of tiles would have if laid along `side`
  // with the row's summed area scaled to `total` (the area of the free box).
  if (!row.length) return Infinity;
  const sum = row.reduce((a, r) => a + r.area, 0);
  if (sum <= 0) return Infinity;
  const s2 = sum * sum;
  const w2 = side * side;
  let max = 0;
  let min = Infinity;
  for (const r of row) { if (r.area > max) max = r.area; if (r.area < min) min = r.area; }
  return Math.max((w2 * max) / s2, s2 / (w2 * min));
}

function layoutRow(row, box) {
  // Lay `row` along the shorter side of `box`; return the box that remains.
  const sum = row.reduce((a, r) => a + r.area, 0);
  const out = [];
  if (box.w >= box.h) {
    // Column on the left, tiles stacked top to bottom.
    const colW = sum / box.h;
    let y = box.y;
    for (const r of row) {
      const h = colW > 0 ? r.area / colW : 0;
      out.push({ x: box.x, y, w: colW, h, item: r.item });
      y += h;
    }
    return { rects: out, rest: { x: box.x + colW, y: box.y, w: box.w - colW, h: box.h } };
  }
  const rowH = sum / box.w;
  let x = box.x;
  for (const r of row) {
    const w = rowH > 0 ? r.area / rowH : 0;
    out.push({ x, y: box.y, w, h: rowH, item: r.item });
    x += w;
  }
  return { rects: out, rest: { x: box.x, y: box.y + rowH, w: box.w, h: box.h - rowH } };
}

export function squarify(items, width, height) {
  const usable = (items || []).filter((it) => it && Number(it.value) > 0 && isFinite(Number(it.value)));
  if (!usable.length || !(width > 0) || !(height > 0)) return [];
  const total = usable.reduce((a, it) => a + Number(it.value), 0);
  const scale = (width * height) / total;
  const nodes = usable
    .map((it) => ({ item: it, area: Number(it.value) * scale }))
    .sort((a, b) => b.area - a.area);
  const rects = [];
  let box = { x: 0, y: 0, w: width, h: height };
  let row = [];
  for (const node of nodes) {
    const side = Math.min(box.w, box.h);
    if (!row.length || worst(row.concat(node), side) <= worst(row, side)) {
      row.push(node);
      continue;
    }
    const laid = layoutRow(row, box);
    rects.push(...laid.rects);
    box = laid.rest;
    row = [node];
  }
  if (row.length) rects.push(...layoutRow(row, box).rects);
  return rects;
}

// Depth of colour for a tile: |pnl / stake| mapped to 0..1 with a floor so a
// tile is never invisible and a cap so one outlier does not wash the rest.
export function pnlIntensity(pnl, stake) {
  const p = Number(pnl);
  const s = Number(stake);
  if (!isFinite(p) || !(s > 0)) return 0.35;
  const ratio = Math.min(1, Math.abs(p) / s);
  return INTENSITY_FLOOR + ratio * (INTENSITY_CEIL - INTENSITY_FLOOR);
}

// Der Boden und die Decke der Farbtiefe stehen hier einmal, damit der
// Schluessel neben der Treemap dieselben Werte zeigt wie die Kacheln.
export const INTENSITY_FLOOR = 0.28;
export const INTENSITY_CEIL = 0.78;
