// Wallet graph — the linkage layer as a page (Wallet-Graph Phase 4).
//
// Pure function over T. Reads only /api/graph, which reads only the locally
// derived entity graph and tape store: no chain or feed calls happen here.
// The page keeps the evidence ladder visible at all times — hard-linked
// entities, exchange-like candidates, and tier-3 behaviour are three separate
// blocks, and the wording is "linked over evidence" / "behaves like", never
// "is". A host without a graph says so; it never shows an empty area that
// reads as "no links".
//
// The map at the top draws the same three tiers in three colours, so the
// blocks below read as the legend of one picture: hard links in the accent,
// candidate ties in the blue reference colour, behaviour pairs dashed in the
// attention colour. Entities carry one series colour each, the same on the
// map and on their card.

import { esc, num } from '../util.js';
import { MONO as M, KARTE, LABEL, NOTIZ, kpi } from '../ui.js';
import { SERIEN_FARBEN } from '../charts.js';
import { layoutNetwork } from '../graph_layout.js';

// The three tiers, once: colour, name, what joins two wallets on that tier.
const TIER = {
  hard: { farbe: 'var(--accent)', rgb: 'var(--accent-rgb)', name: 'ON-CHAIN LINK', satz: 'verifiable transfers between two scanned accounts: direct transfer, position token moved, same funder or withdrawal target' },
  candidate: { farbe: 'var(--s4)', name: 'CANDIDATE TIE', satz: 'a counterparty that touches three or more scanned wallets — behaves like a deposit router or exchange, shown but never merged' },
  behavior: { farbe: 'var(--warn)', name: 'BEHAVIOUR', satz: 'patterns in the stored tape: order-splitting bursts and pairs on opposite sides of one book — shown next to the graph, never used to merge accounts' }
};

function shortAddr(a) {
  const s = String(a || '');
  return s.length > 12 ? s.slice(0, 6) + '…' + s.slice(-4) : s;
}

function card(title, body, sub, farbe) {
  return '<div style="' + KARTE + '; padding:var(--sp-5); margin-top:var(--sp-5)">'
    + '<div style="display:flex; align-items:baseline; justify-content:space-between; gap:var(--sp-4); flex-wrap:wrap; margin-bottom:var(--sp-4)">'
    + '<div style="display:flex; align-items:center; gap:var(--sp-3)">'
    + (farbe ? '<span style="display:inline-block; width:10px; height:10px; border-radius:2px; background:' + farbe + '"></span>' : '')
    + '<div style="' + LABEL + '">' + title + '</div></div>'
    + (sub ? '<div style="' + NOTIZ + '">' + esc(sub) + '</div>' : '') + '</div>'
    + body + '</div>';
}

function scan(T, addr, farbe) {
  // A wallet in the graph opens on the Wallet page's Linked tab.
  const a = String(addr || '');
  return '<span ' + T.act(() => { if (T.openWalletTab) T.openWalletTab(a, 'linked'); }) + ' class="hv-edge-strong" style="' + M + '; font-size:var(--t-small); color:var(--ink-1); cursor:pointer; text-decoration:underline dotted; white-space:nowrap" title="' + esc(a) + '">'
    + (farbe ? '<span style="display:inline-block; width:8px; height:8px; border-radius:50%; background:' + farbe + '; margin-right:var(--sp-2); vertical-align:middle"></span>' : '')
    + esc(shortAddr(a)) + '</span>';
}

function polygonscan(addr) {
  return '<a href="https://polygonscan.com/address/' + esc(addr) + '" target="_blank" rel="noopener" class="hv-accent" style="' + M + '; font-size:var(--t-micro); color:var(--ink-3); text-decoration:underline dotted" title="' + esc(addr) + ' — on-chain">' + esc(shortAddr(addr)) + ' ↗</a>';
}

// One evidence label per edge type, in plain language. The type names are the
// API's; the page turns each into a sentence about what was observed.
const EDGE_LABEL = {
  direct_transfer: 'direct transfer between the two wallets',
  position_transfer: 'position token moved wallet-to-wallet',
  shared_funder: 'same external funding source',
  shared_withdrawal: 'same external withdrawal target'
};

// The global reach of a shared counterparty decides how the link reads:
// checked-and-private is the strong case, unchecked says so out loud.
function reachNote(p) {
  if (p.global_partners == null) return ' <span style="color:var(--ink-4)">(global reach not checked yet)</span>';
  return ' <span style="color:var(--ink-4)">(serves ' + num(p.global_partners) + (p.global_complete === false ? '+' : '') + ' addresses on-chain)</span>';
}

function edgeEvidence(edge) {
  const parts = Array.isArray(edge.evidenz && edge.evidenz.shared_counterparties)
    ? edge.evidenz.shared_counterparties : null;
  if (parts && parts.length) {
    return parts.map((p) => (p.direction === 'in' ? 'funder ' : 'target ') + polygonscan(p.counterparty) + reachNote(p)).join(' · ');
  }
  const tx = edge.evidenz && Array.isArray(edge.evidenz.tx_sample) ? edge.evidenz.tx_sample : [];
  const n = edge.evidenz && edge.evidenz.transfers != null ? edge.evidenz.transfers : tx.length;
  return num(n) + ' transfer' + (Number(n) === 1 ? '' : 's')
    + (tx.length ? ' · <span style="' + M + '; font-size:var(--t-micro); color:var(--ink-4)">' + esc(String(tx[0]).slice(0, 14)) + '…</span>' : '');
}

// A small horizontal bar: value against max, in the tier colour, with the
// number printed after it. Used for confidence, hub reach and burst size.
function balken(wert, max, farbe, text, breite) {
  const b = breite || 90;
  const anteil = max > 0 ? Math.max(0, Math.min(1, wert / max)) : 0;
  return '<span style="display:inline-flex; align-items:center; gap:var(--sp-2); white-space:nowrap">'
    + '<span style="display:inline-block; width:' + b + 'px; height:6px; border-radius:3px; background:rgba(var(--ink),.08); overflow:hidden; vertical-align:middle">'
    + '<span style="display:block; width:' + (anteil * 100).toFixed(0) + '%; height:100%; background:' + farbe + '"></span></span>'
    + '<span style="' + M + '; font-size:var(--t-micro); color:var(--ink-2)">' + esc(text) + '</span></span>';
}

// Colour of an entity by its position in the list: one series slot each,
// grey beyond the palette (the palette never reuses a colour).
function entityFarben(entities) {
  const farbe = new Map();
  entities.forEach((e, i) => {
    const f = i < SERIEN_FARBEN.length ? SERIEN_FARBEN[i] : 'rgba(var(--ink),.45)';
    (Array.isArray(e.wallets) ? e.wallets : []).forEach((w) => farbe.set(String(w).toLowerCase(), f));
  });
  return farbe;
}

// ---- the map -------------------------------------------------------------
// Nodes: every scanned wallet that appears in an entity, a candidate tie or
// a behaviour pair (capped), plus the candidate counterparties as diamonds.
// Edges: hard links (entity edges), candidate ties (counterparty to each
// wallet it touches) and the strongest opposite-side pairs.
const MAX_WALLET_NODES = 60;
const MAX_HUBS = 10;
const MAX_PAIRS = 12;

function mapModel(d) {
  const entities = Array.isArray(d.entities) ? d.entities : [];
  const cands = Array.isArray(d.candidates) ? d.candidates : [];
  const pairs = d.behavior && Array.isArray(d.behavior.complementary_pairs) ? d.behavior.complementary_pairs : [];
  const farbe = entityFarben(entities);
  const wallets = new Map();
  const merken = (w, quelle) => {
    const id = String(w || '').toLowerCase();
    if (!id) return;
    const slot = wallets.get(id) || { id, entity: farbe.get(id) || null, hard: 0, cand: 0, pairs: 0 };
    slot[quelle] += 1;
    wallets.set(id, slot);
  };
  const edges = [];
  entities.forEach((e) => {
    (e.wallets || []).forEach((w) => merken(w, 'hard'));
    (e.edges || []).forEach((k) => {
      merken(k.wallet_a, 'hard'); merken(k.wallet_b, 'hard');
      edges.push({ a: String(k.wallet_a).toLowerCase(), b: String(k.wallet_b).toLowerCase(), kind: 'hard', weight: 2.2, typ: k.typ, konfidenz: k.konfidenz });
    });
  });
  const hubs = cands.slice(0, MAX_HUBS).map((c, i) => ({ id: 'hub:' + String(c.counterparty).toLowerCase(), counterparty: c.counterparty, direction: c.direction, count: c.wallet_count, i }));
  const hubIndex = new Map(hubs.map((h) => [h.id, h.i]));
  cands.slice(0, MAX_HUBS).forEach((c, i) => {
    (c.wallets || []).forEach((w) => {
      merken(w, 'cand');
      edges.push({ a: hubs[i].id, b: String(w).toLowerCase(), kind: 'candidate', weight: 0.6 });
    });
  });
  pairs.slice().sort((a, b) => (+b.events || 0) - (+a.events || 0)).slice(0, MAX_PAIRS).forEach((p) => {
    merken(p.wallet_a, 'pairs'); merken(p.wallet_b, 'pairs');
    edges.push({ a: String(p.wallet_a).toLowerCase(), b: String(p.wallet_b).toLowerCase(), kind: 'behavior', weight: 0.4, events: p.events });
  });
  // Cap: entity members first, then the most connected.
  const liste = Array.from(wallets.values()).sort((a, b) => (b.entity ? 1 : 0) - (a.entity ? 1 : 0) || (b.hard + b.cand + b.pairs) - (a.hard + a.cand + a.pairs));
  const behalten = new Set(liste.slice(0, MAX_WALLET_NODES).map((w) => w.id));
  const nodes = liste.filter((w) => behalten.has(w.id)).map((w) => ({ id: w.id, kind: 'wallet', entity: w.entity, links: w.hard + w.cand + w.pairs }))
    .concat(hubs.map((h) => ({ id: h.id, kind: 'hub', counterparty: h.counterparty, direction: h.direction, count: h.count, i: hubIndex.get(h.id) })));
  const ids = new Set(nodes.map((n) => n.id));
  return { nodes, edges: edges.filter((e) => ids.has(e.a) && ids.has(e.b)), dropped: liste.length - behalten.size, hubsDropped: Math.max(0, cands.length - hubs.length) };
}

function mapSvg(T, d) {
  const m = mapModel(d);
  if (!m.nodes.length) return '';
  const B = 900, H = 440;
  const pos = layoutNetwork(m.nodes, m.edges, { breite: B, hoehe: H, rand: 46, seed: 11 });
  const stil = { hard: 'stroke:var(--accent); stroke-width:2.4; stroke-opacity:.95', candidate: 'stroke:var(--s4); stroke-width:1.1; stroke-opacity:.45', behavior: 'stroke:var(--warn); stroke-width:1.4; stroke-opacity:.75; stroke-dasharray:5 4' };
  const reihenfolge = { candidate: 0, behavior: 1, hard: 2 };
  const kanten = m.edges.slice().sort((a, b) => reihenfolge[a.kind] - reihenfolge[b.kind]).map((e) => {
    const p = pos.get(e.a), q = pos.get(e.b);
    if (!p || !q) return '';
    const titel = e.kind === 'hard' ? (EDGE_LABEL[e.typ] || e.typ) + ' · confidence ' + Math.round((+e.konfidenz || 0) * 100) + '%'
      : e.kind === 'candidate' ? 'shared counterparty (candidate tie)'
        : num(e.events) + ' opposite-side events within minutes';
    return '<line x1="' + p.x.toFixed(1) + '" y1="' + p.y.toFixed(1) + '" x2="' + q.x.toFixed(1) + '" y2="' + q.y.toFixed(1) + '" style="' + stil[e.kind] + '"><title>' + esc(titel) + '</title></line>';
  }).join('');
  const maxLinks = Math.max(1, ...m.nodes.filter((n) => n.kind === 'wallet').map((n) => n.links));
  const knoten = m.nodes.map((n) => {
    const p = pos.get(n.id);
    if (!p) return '';
    if (n.kind === 'hub') {
      const r = 5.5 + 4 * Math.min(1, (+n.count || 0) / 10);
      const klick = T.act(() => { if (T.openWalletTab) T.openWalletTab(n.counterparty, 'linked'); }, { plain: true });
      // Nur die vier groessten Gegenparteien tragen ein Label; die Adresse
      // jeder Raute stand sonst zehnmal im Bild und ueberdeckte die Knoten.
      const hubLabel = n.i < 4
        ? '<text x="' + (p.x + r + 5).toFixed(1) + '" y="' + (p.y + 3.5).toFixed(1) + '" style="fill:var(--ink-3)" font-size="10" font-family="IBM Plex Mono, monospace">' + esc(shortAddr(n.counterparty)) + '</text>'
        : '';
      return '<g ' + klick + ' style="cursor:pointer"><rect x="' + (p.x - r).toFixed(1) + '" y="' + (p.y - r).toFixed(1) + '" width="' + (2 * r).toFixed(1) + '" height="' + (2 * r).toFixed(1)
        + '" transform="rotate(45 ' + p.x.toFixed(1) + ' ' + p.y.toFixed(1) + ')" style="fill:var(--panel); stroke:var(--s4); stroke-width:2">'
        + '<title>' + esc('counterparty ' + n.counterparty + ' · ' + (n.direction === 'in' ? 'funds' : 'is paid by') + ' ' + num(n.count) + ' scanned wallets') + '</title></rect>'
        + hubLabel + '</g>';
    }
    const r = 4.5 + 5 * Math.sqrt(n.links / maxLinks);
    const fill = n.entity || 'rgba(var(--ink),.35)';
    const klick = T.act(() => { if (T.openWalletTab) T.openWalletTab(n.id, 'linked'); }, { plain: true });
    const label = n.entity
      ? '<text x="' + (p.x + r + 4).toFixed(1) + '" y="' + (p.y + 3.5).toFixed(1) + '" style="fill:var(--ink-1)" font-size="10.5" font-family="IBM Plex Mono, monospace">' + esc(shortAddr(n.id)) + '</text>'
      : '';
    return '<g ' + klick + ' style="cursor:pointer"><circle cx="' + p.x.toFixed(1) + '" cy="' + p.y.toFixed(1) + '" r="' + r.toFixed(1) + '" style="fill:' + fill + '; stroke:var(--panel)" stroke-width="1.5">'
      + '<title>' + esc(n.id + ' · ' + num(n.links) + ' link' + (n.links === 1 ? '' : 's') + (n.entity ? ' · in a linked entity' : '')) + '</title></circle>' + label + '</g>';
  }).join('');
  const legende = [
    ['<span style="display:inline-block; width:18px; height:0; border-top:2.4px solid var(--accent)"></span>', 'on-chain link'],
    ['<span style="display:inline-block; width:18px; height:0; border-top:1.2px solid var(--s4)"></span>', 'candidate tie to a shared counterparty'],
    ['<span style="display:inline-block; width:18px; height:0; border-top:1.5px dashed var(--warn)"></span>', 'opposite-side pair (behaviour)'],
    ['<span style="display:inline-block; width:9px; height:9px; border-radius:50%; background:rgba(var(--ink),.35)"></span>', 'scanned wallet · size = links'],
    ['<span style="display:inline-block; width:8px; height:8px; border:2px solid var(--s4); transform:rotate(45deg)"></span>', 'counterparty (router or exchange)'],
    ['<span style="display:inline-block; width:9px; height:9px; border-radius:50%; background:var(--s1)"></span>', 'colour = linked entity']
  ].map((l) => '<span style="display:inline-flex; align-items:center; gap:var(--sp-2); ' + M + '; font-size:var(--t-micro); color:var(--ink-3)">' + l[0] + esc(l[1]) + '</span>').join('');
  const hinweis = (m.dropped > 0 ? num(m.dropped) + ' further wallets not drawn · ' : '')
    + (m.hubsDropped > 0 ? num(m.hubsDropped) + ' smaller counterparties not drawn · ' : '')
    + 'click a node to open it';
  return '<div style="' + KARTE + '; padding:var(--sp-5); margin-top:var(--sp-5)">'
    + '<div style="display:flex; align-items:baseline; justify-content:space-between; gap:var(--sp-4); flex-wrap:wrap; margin-bottom:var(--sp-3)">'
    + '<div style="' + LABEL + '">NETWORK MAP · ' + num(m.nodes.filter((n) => n.kind === 'wallet').length) + ' WALLETS · ' + num(m.edges.length) + ' TIES</div>'
    + '<div style="' + NOTIZ + '">' + esc(hinweis) + '</div></div>'
    + '<svg width="100%" viewBox="0 0 ' + B + ' ' + H + '" role="img" aria-label="wallet network map: scanned wallets, their on-chain links, candidate counterparties and opposite-side pairs" style="display:block; max-width:1080px; background:rgba(var(--ink),.025); border-radius:var(--r-control)">'
    + kanten + knoten + '</svg>'
    + '<div style="display:flex; gap:var(--sp-5); flex-wrap:wrap; margin-top:var(--sp-3)">' + legende + '</div></div>';
}

// ---- the evidence ladder --------------------------------------------------
function ladder(d) {
  const s = d.stats || {};
  const b = d.behavior || {};
  const stufen = [
    ['hard', num(s.hard_edges || 0), 'links · ' + num(s.multi_wallet_entities || 0) + ' entit' + (s.multi_wallet_entities === 1 ? 'y' : 'ies')],
    ['candidate', num((Array.isArray(d.candidates) ? d.candidates : []).length || s.candidate_edges || 0), 'counterparties · ' + num(s.candidate_edges || 0) + ' pair ties'],
    ['behavior', b.available ? num((b.fingerprints || []).length) + ' + ' + num((b.complementary_pairs || []).length) : '—', b.available ? 'bursts + opposite-side pairs' : 'no tape store on this host']
  ];
  return '<div style="display:grid; grid-template-columns:repeat(3, 1fr); gap:var(--sp-4); margin-top:var(--sp-5)">'
    + stufen.map(([key, wert, sub]) => {
      const t = TIER[key];
      return '<div style="' + KARTE + '; padding:var(--sp-4) var(--sp-5); border-top:2px solid ' + t.farbe + '">'
        + '<div style="display:flex; align-items:baseline; justify-content:space-between; gap:var(--sp-3)"><div style="' + LABEL + '; color:' + t.farbe + '">' + t.name + '</div>'
        + '<div style="' + M + '; font-size:var(--t-head); color:var(--ink-1)">' + esc(wert) + '</div></div>'
        + '<div style="' + NOTIZ + '; margin-top:var(--sp-1)">' + esc(sub) + '</div>'
        + '<div style="font-size:var(--t-small); color:var(--ink-3); line-height:var(--lh-snug); margin-top:var(--sp-3)">' + esc(t.satz) + '</div></div>';
    }).join('')
    + '</div>';
}

function renderEntities(T, d) {
  const entities = Array.isArray(d.entities) ? d.entities : [];
  if (!entities.length) {
    return card('LINKED ENTITIES',
      '<div style="' + NOTIZ + '">No two scanned wallets are joined by hard on-chain evidence yet — a result, not a missing read. '
      + num((d.stats && d.stats.scans) || 0) + ' wallets scanned, and each stands on its own so far.</div>', null, TIER.hard.farbe);
  }
  const farben = entityFarben(entities);
  const body = entities.map((e, i) => {
    const wallets = Array.isArray(e.wallets) ? e.wallets : [];
    const edges = Array.isArray(e.edges) ? e.edges : [];
    const farbe = i < SERIEN_FARBEN.length ? SERIEN_FARBEN[i] : 'rgba(var(--ink),.45)';
    const chips = wallets.map((w) => '<span style="' + M + '; font-size:var(--t-small); border:1px solid var(--line-1); border-radius:var(--r-control); padding:var(--sp-1) var(--sp-3); color:var(--ink-1)">' + scan(T, w, farben.get(String(w).toLowerCase())) + '</span>').join(' ');
    const rows = edges.map((edge) => '<div style="display:grid; grid-template-columns:230px 130px 1fr; gap:var(--sp-4); align-items:baseline; padding:var(--sp-2) 0; border-top:1px solid var(--line-3)">'
      + '<span style="' + M + '; font-size:var(--t-micro); color:var(--accent)">' + esc(EDGE_LABEL[edge.typ] || edge.typ) + '</span>'
      + balken(+edge.konfidenz || 0, 1, 'var(--accent)', 'confidence ' + Math.round((+edge.konfidenz || 0) * 100) + '%', 60)
      + '<span style="' + NOTIZ + '">' + edgeEvidence(edge) + (edge.first_seen ? ' · since ' + esc(String(edge.first_seen).slice(0, 10)) : '') + '</span></div>').join('');
    return '<div style="border:1px solid var(--line-1); border-left:1px solid ' + farbe + '; border-radius:var(--r-panel); padding:var(--sp-4); margin-bottom:var(--sp-4)">'
      + '<div style="display:flex; align-items:center; justify-content:space-between; gap:var(--sp-4); flex-wrap:wrap; margin-bottom:var(--sp-3)">'
      + '<div style="display:flex; align-items:center; gap:var(--sp-3)"><span style="display:inline-block; width:12px; height:12px; border-radius:50%; background:' + farbe + '"></span>'
      + '<div style="' + M + '; font-size:var(--t-small); color:var(--ink-1)">entity ' + (i + 1) + ' · ' + wallets.length + ' wallets · ' + edges.length + ' on-chain link' + (edges.length === 1 ? '' : 's') + '</div></div></div>'
      + '<div style="display:flex; flex-wrap:wrap; gap:var(--sp-2); margin-bottom:var(--sp-3)">' + chips + '</div>'
      + rows + '</div>';
  }).join('');
  const sub = 'accounts joined by verifiable money or position movements; every link lists its evidence'
    + (d.entities_capped ? ' · more not shown' : '');
  return card('LINKED ENTITIES', body, sub, TIER.hard.farbe);
}

function renderCandidates(T, d) {
  const cands = Array.isArray(d.candidates) ? d.candidates : [];
  if (!cands.length) {
    return card('CANDIDATES · SHARED COUNTERPARTIES',
      '<div style="' + NOTIZ + '">No counterparty ties three or more scanned wallets together.</div>', null, TIER.candidate.farbe);
  }
  const scans = (d.stats && d.stats.scans) || Math.max(...cands.map((c) => +c.wallet_count || 0), 1);
  const farben = entityFarben(Array.isArray(d.entities) ? d.entities : []);
  const kopf = '<div style="display:grid; grid-template-columns:150px 110px 170px 1fr; gap:var(--sp-4); padding:var(--sp-2) 0; ' + LABEL + '; border-bottom:1px solid var(--line-2)">'
    + '<div>COUNTERPARTY</div><div>DIRECTION</div><div>SCANNED WALLETS TOUCHED</div><div>WALLETS</div></div>';
  const body = cands.map((c) => {
    const wallets = Array.isArray(c.wallets) ? c.wallets : [];
    const chips = wallets.slice(0, 10).map((w) => scan(T, w, farben.get(String(w).toLowerCase()))).join(' <span style="color:var(--ink-4)">·</span> ');
    const dir = c.direction === 'in' ? '→ funds' : '← is paid by';
    return '<div style="display:grid; grid-template-columns:150px 110px 170px 1fr; gap:var(--sp-4); align-items:baseline; padding:var(--sp-3) 0; border-top:1px solid var(--line-3)">'
      + '<span style="' + M + '; font-size:var(--t-small); color:var(--ink-1)"><span style="display:inline-block; width:7px; height:7px; border:1.5px solid var(--s4); transform:rotate(45deg); margin-right:var(--sp-2)"></span>' + polygonscan(c.counterparty) + '</span>'
      + '<span style="' + M + '; font-size:var(--t-micro); color:var(--ink-3)">' + esc(dir) + '</span>'
      + balken(+c.wallet_count || 0, scans, 'var(--s4)', num(c.wallet_count) + ' of ' + num(scans) + (c.narrow_pairs ? ' · ' + c.narrow_pairs + ' pair' + (c.narrow_pairs === 1 ? '' : 's') + ' within 48h' : ''), 70)
      + '<span style="' + NOTIZ + '; min-width:0">' + chips + (wallets.length > 10 ? ' <span style="color:var(--ink-4)">+' + (wallets.length - 10) + '</span>' : '') + '</span></div>';
  }).join('');
  return card('CANDIDATES · SHARED COUNTERPARTIES', kopf + body,
    'a counterparty that touches three or more wallets behaves like a deposit router or exchange — shown, never merged'
    + (d.candidates_capped ? ' · more not shown' : ''), TIER.candidate.farbe);
}

function renderBehavior(T, d) {
  const b = d.behavior || {};
  if (!b.available) {
    return card('BEHAVIOUR · TIER 3',
      '<div style="' + NOTIZ + '">' + esc(b.note || 'No trade store on this host, so no behaviour read.') + '</div>', null, TIER.behavior.farbe);
  }
  const fps = Array.isArray(b.fingerprints) ? b.fingerprints : [];
  const pairs = Array.isArray(b.complementary_pairs) ? b.complementary_pairs : [];
  const farben = entityFarben(Array.isArray(d.entities) ? d.entities : []);
  const maxPrints = Math.max(1, ...fps.map((f) => +f.burst_prints || 0));
  const maxEvents = Math.max(1, ...pairs.map((p) => +p.events || 0));
  const fpBody = fps.length ? fps.slice(0, 12).map((f) => '<div style="display:grid; grid-template-columns:150px 200px 1fr; gap:var(--sp-4); align-items:baseline; padding:var(--sp-2) 0; border-top:1px solid var(--line-3)">'
    + '<span>' + scan(T, f.wallet, farben.get(String(f.wallet).toLowerCase())) + '</span>'
    + balken(+f.burst_prints || 0, maxPrints, 'var(--warn)', num(f.burst_prints) + ' prints in ' + num(Math.round(f.burst_seconds)) + ' s', 70)
    + '<span style="' + NOTIZ + '; white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="' + esc(String(f.burst_market || '')) + '">' + esc(String(f.burst_market || '').slice(0, 60)) + '</span></div>').join('')
    : '<div style="' + NOTIZ + '">No order-splitting bursts in the stored window.</div>';
  const pairBody = pairs.length ? pairs.slice().sort((a, b2) => (+b2.events || 0) - (+a.events || 0)).slice(0, 12).map((p) => '<div style="display:grid; grid-template-columns:260px 200px 1fr; gap:var(--sp-4); align-items:baseline; padding:var(--sp-2) 0; border-top:1px solid var(--line-3)">'
    + '<span style="' + M + '; font-size:var(--t-small)">' + scan(T, p.wallet_a, farben.get(String(p.wallet_a).toLowerCase())) + ' <span style="color:var(--warn)">⇄</span> ' + scan(T, p.wallet_b, farben.get(String(p.wallet_b).toLowerCase())) + '</span>'
    + balken(+p.events || 0, maxEvents, 'var(--warn)', num(p.events) + ' opposite-side events', 70)
    + '<span style="' + NOTIZ + '">in ' + num(p.markets) + ' market' + (+p.markets === 1 ? '' : 's') + '</span></div>').join('')
    : '<div style="' + NOTIZ + '">No pairs repeatedly on opposite sides of the same book.</div>';
  const pairNote = '<div style="' + NOTIZ + '; margin-bottom:var(--sp-2)">Two accounts repeatedly on opposite sides of the same book within minutes. Most often that is market making, arbitrage or plain disagreement; it reads as wash trading only when the pair also shares funding — check the entity and candidate blocks above.</div>';
  return card('BEHAVIOUR · TIER 3',
    '<div style="' + LABEL + '; margin-bottom:var(--sp-2)">ORDER-SPLITTING FINGERPRINTS' + (fps.length > 12 ? ' · TOP 12 OF ' + num(fps.length) : '') + '</div>' + fpBody
    + '<div style="' + LABEL + '; margin:var(--sp-4) 0 var(--sp-2)">OPPOSITE-SIDE PAIRS' + (pairs.length > 12 ? ' · TOP 12 OF ' + num(pairs.length) + ' BY EVENTS' : '') + '</div>' + pairNote + pairBody,
    'patterns in the stored tape' + (b.tape_rows ? ' · ' + num(b.tape_rows) + ' prints stored' : '') + ' — shown next to the graph, never used to merge accounts', TIER.behavior.farbe);
}

function intro(d) {
  const s = d.stats || {};
  const tiles = [
    kpi({ label: 'WALLETS SCANNED', wert: num(s.scans || 0), sub: 'the denominator of every list below' }),
    // "On-chain links", nicht "edges": eine Wallet-Seite daneben zeigt
    // REALIZED EDGE im Trading-Sinn, und derselbe Begriff fuer eine
    // Graphkante wuerde als Alpha gelesen.
    kpi({ label: 'ON-CHAIN LINKS', wert: num(s.hard_edges || 0), sub: 'verifiable transfers between scanned accounts', farbe: TIER.hard.farbe }),
    kpi({ label: 'LINKED ENTITIES', wert: num(s.multi_wallet_entities || 0), sub: 'groups of two or more wallets', farbe: TIER.hard.farbe }),
    kpi({ label: 'CANDIDATES', wert: num(s.candidate_edges || 0), sub: 'pair ties over a shared counterparty', farbe: TIER.candidate.farbe })
  ].join('');
  return '<div style="' + KARTE + '; padding:var(--sp-5); margin-top:var(--sp-5)">'
    + '<div style="font-size:var(--t-lead); line-height:var(--lh-solid)">Wallet graph</div>'
    + '<div style="' + NOTIZ + '; margin-top:var(--sp-2); max-width:70ch">Accounts linked over public on-chain evidence, not single-wallet scores. Hard evidence (direct transfers, shared funders, position moves) joins wallets into an <b>entity</b>; an exchange-like counterparty is a <b>candidate</b>, shown but never merged; trading <b>behaviour</b> is shown beside both. No persons are identified — accounts are linked over documented transfers.</div>'
    + '<div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(150px, 1fr)); gap:var(--sp-4); margin-top:var(--sp-5)">' + tiles + '</div></div>';
}

export function renderGraph(T) {
  if (typeof T.fetchGraph === 'function') T.fetchGraph();
  const entry = T.liveData ? T.liveData.graph : null;
  const head = '<div style="padding:var(--sp-5) var(--sp-6) var(--sp-7)">';
  if (!entry || entry._quelle === 'loading') {
    return head + '<div style="' + KARTE + '; padding:var(--sp-6); ' + NOTIZ + '">Reading the local entity graph…</div></div>';
  }
  if (entry._quelle === 'fehler') {
    return head + '<div style="' + KARTE + '; padding:var(--sp-6); ' + NOTIZ + '; color:var(--warn)">/api/graph did not answer: ' + esc(entry._fehler || 'unknown error') + '.</div></div>';
  }
  const d = entry;
  if (!d.available) {
    // Kein Graph ist ein Befund, kein Ladezustand - und das Verhalten aus
    // dem Tape-Store gibt es auch ohne Graphen, sobald der Host einen
    // Store traegt (auf dem Deploy-Host laeuft der Aufbau zuerst).
    return head + intro({ stats: {} })
      + card('NO GRAPH ON THIS HOST YET',
        '<div style="' + NOTIZ + '">' + esc(d.note || 'No entity graph here.') + ' The graph is built by the entity scan into a local database; until it exists there is nothing to link by, which is a state, not an error.</div>')
      + renderBehavior(T, d)
      + (d.as_of ? '<div style="' + NOTIZ + '; margin-top:var(--sp-4)">as of ' + esc(d.as_of) + '</div>' : '')
      + '</div>';
  }
  return head + intro(d)
    + ladder(d)
    + mapSvg(T, d)
    + renderEntities(T, d)
    + renderCandidates(T, d)
    + renderBehavior(T, d)
    + (d.caveat ? '<div style="' + NOTIZ + '; margin-top:var(--sp-5); max-width:80ch">' + esc(d.caveat) + '</div>' : '')
    + (d.as_of ? '<div style="' + NOTIZ + '; margin-top:var(--sp-4)">as of ' + esc(d.as_of) + '</div>' : '')
    + '</div>';
}
