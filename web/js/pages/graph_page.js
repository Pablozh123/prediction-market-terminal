// Wallet graph — the linkage layer as a page (Wallet-Graph Phase 4).
//
// Pure function over T. Reads only /api/graph, which reads only the locally
// derived entity graph and tape store: no chain or feed calls happen here.
// The page keeps the evidence ladder visible at all times — hard-linked
// entities, exchange-like candidates, and tier-3 behaviour are three separate
// blocks, and the wording is "linked over evidence" / "behaves like", never
// "is". A host without a graph says so; it never shows an empty area that
// reads as "no links".

import { esc, num } from '../util.js';
import { MONO as M, KARTE, LABEL, NOTIZ, kpi } from '../ui.js';

function shortAddr(a) {
  const s = String(a || '');
  return s.length > 12 ? s.slice(0, 6) + '…' + s.slice(-4) : s;
}

function card(title, body, sub) {
  return '<div style="' + KARTE + '; padding:var(--sp-5); margin-top:var(--sp-5)">'
    + '<div style="display:flex; align-items:baseline; justify-content:space-between; gap:var(--sp-4); flex-wrap:wrap; margin-bottom:var(--sp-4)">'
    + '<div style="' + LABEL + '">' + title + '</div>'
    + (sub ? '<div style="' + NOTIZ + '">' + esc(sub) + '</div>' : '') + '</div>'
    + body + '</div>';
}

function scan(T, addr) {
  // A wallet in the graph opens on the Wallet page's Linked tab.
  const a = String(addr || '');
  return '<span ' + T.act(() => { if (T.openWalletTab) T.openWalletTab(a, 'linked'); }) + ' class="hv-edge-strong" style="' + M + '; font-size:var(--t-small); color:var(--ink-1); cursor:pointer; text-decoration:underline dotted" title="' + esc(a) + '">' + esc(shortAddr(a)) + '</span>';
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

function edgeEvidence(edge) {
  const parts = Array.isArray(edge.evidenz && edge.evidenz.shared_counterparties)
    ? edge.evidenz.shared_counterparties : null;
  if (parts && parts.length) {
    return parts.map((p) => (p.direction === 'in' ? 'funder ' : 'target ') + polygonscan(p.counterparty)).join(' · ');
  }
  const tx = edge.evidenz && Array.isArray(edge.evidenz.tx_sample) ? edge.evidenz.tx_sample : [];
  const n = edge.evidenz && edge.evidenz.transfers != null ? edge.evidenz.transfers : tx.length;
  return num(n) + ' transfer' + (Number(n) === 1 ? '' : 's')
    + (tx.length ? ' · <span style="' + M + '; font-size:var(--t-micro); color:var(--ink-4)">' + esc(String(tx[0]).slice(0, 14)) + '…</span>' : '');
}

function renderEntities(T, d) {
  const entities = Array.isArray(d.entities) ? d.entities : [];
  if (!entities.length) {
    return card('LINKED ENTITIES',
      '<div style="' + NOTIZ + '">No two scanned wallets are joined by hard on-chain evidence yet — a result, not a missing read. '
      + num((d.stats && d.stats.scans) || 0) + ' wallets scanned, and each stands on its own so far.</div>');
  }
  const body = entities.map((e) => {
    const wallets = Array.isArray(e.wallets) ? e.wallets : [];
    const edges = Array.isArray(e.edges) ? e.edges : [];
    const chips = wallets.map((w) => '<span style="' + M + '; font-size:var(--t-small); border:1px solid var(--line-1); border-radius:var(--r-control); padding:var(--sp-1) var(--sp-3); color:var(--ink-1)">' + scan(T, w) + '</span>').join(' ');
    const rows = edges.map((edge) => '<div style="display:flex; gap:var(--sp-3); align-items:baseline; padding:var(--sp-2) 0; border-top:1px solid var(--line-3)">'
      + '<span style="' + M + '; font-size:var(--t-micro); color:var(--accent); white-space:nowrap">' + esc(EDGE_LABEL[edge.typ] || edge.typ) + '</span>'
      + '<span style="' + NOTIZ + '">' + edgeEvidence(edge) + '</span></div>').join('');
    return '<div style="border:1px solid var(--line-1); border-radius:var(--r-panel); padding:var(--sp-4); margin-bottom:var(--sp-4)">'
      + '<div style="display:flex; align-items:baseline; justify-content:space-between; gap:var(--sp-4); flex-wrap:wrap; margin-bottom:var(--sp-3)">'
      + '<div style="' + M + '; font-size:var(--t-small); color:var(--ink-1)">' + wallets.length + ' wallets · ' + edges.length + ' hard edge' + (edges.length === 1 ? '' : 's') + '</div></div>'
      + '<div style="display:flex; flex-wrap:wrap; gap:var(--sp-2); margin-bottom:var(--sp-3)">' + chips + '</div>'
      + rows + '</div>';
  }).join('');
  const sub = 'joined by direct transfers, shared funders or shared withdrawal targets — union-find over tier-1 evidence'
    + (d.entities_capped ? ' · more not shown' : '');
  return card('LINKED ENTITIES', body, sub);
}

function renderCandidates(T, d) {
  const cands = Array.isArray(d.candidates) ? d.candidates : [];
  if (!cands.length) {
    return card('CANDIDATES · SHARED COUNTERPARTIES',
      '<div style="' + NOTIZ + '">No counterparty ties three or more scanned wallets together.</div>');
  }
  const body = cands.map((c) => {
    const wallets = Array.isArray(c.wallets) ? c.wallets : [];
    const chips = wallets.slice(0, 12).map((w) => scan(T, w)).join(' <span style="color:var(--ink-4)">·</span> ');
    const dir = c.direction === 'in' ? 'funds' : 'is paid by';
    return '<div style="padding:var(--sp-3) 0; border-top:1px solid var(--line-3)">'
      + '<div style="display:flex; gap:var(--sp-3); align-items:baseline; flex-wrap:wrap">'
      + '<span style="' + M + '; font-size:var(--t-small); color:var(--ink-1)">' + polygonscan(c.counterparty) + '</span>'
      + '<span style="' + NOTIZ + '">' + dir + ' <b style="color:var(--ink-1)">' + c.wallet_count + '</b> scanned wallets'
      + (c.narrow_pairs ? ' · ' + c.narrow_pairs + ' pair' + (c.narrow_pairs === 1 ? '' : 's') + ' within 48h' : '') + '</span></div>'
      + '<div style="' + NOTIZ + '; margin-top:var(--sp-2)">' + chips + (wallets.length > 12 ? ' <span style="color:var(--ink-4)">+' + (wallets.length - 12) + '</span>' : '') + '</div></div>';
  }).join('');
  return card('CANDIDATES · SHARED COUNTERPARTIES', body,
    'a counterparty that touches three or more wallets behaves like a deposit router or exchange — shown, never merged'
    + (d.candidates_capped ? ' · more not shown' : ''));
}

function renderBehavior(T, d) {
  const b = d.behavior || {};
  if (!b.available) {
    return card('BEHAVIOUR · TIER 3',
      '<div style="' + NOTIZ + '">' + esc(b.note || 'No trade store on this host, so no behaviour read.') + '</div>');
  }
  const fps = Array.isArray(b.fingerprints) ? b.fingerprints : [];
  const pairs = Array.isArray(b.complementary_pairs) ? b.complementary_pairs : [];
  const fpBody = fps.length ? fps.slice(0, 12).map((f) => '<div style="padding:var(--sp-2) 0; border-top:1px solid var(--line-3); display:flex; gap:var(--sp-3); align-items:baseline; flex-wrap:wrap">'
    + '<span style="' + M + '; font-size:var(--t-small)">' + scan(T, f.wallet) + '</span>'
    + '<span style="' + NOTIZ + '"><b style="color:var(--ink-1)">' + num(f.burst_prints) + '</b> prints in ' + num(Math.round(f.burst_seconds)) + 's on ' + esc(String(f.burst_market || '').slice(0, 48)) + '</span></div>').join('')
    : '<div style="' + NOTIZ + '">No order-splitting bursts in the stored window.</div>';
  const pairBody = pairs.length ? pairs.slice(0, 12).map((p) => '<div style="padding:var(--sp-2) 0; border-top:1px solid var(--line-3); display:flex; gap:var(--sp-3); align-items:baseline; flex-wrap:wrap">'
    + '<span style="' + M + '; font-size:var(--t-small)">' + scan(T, p.wallet_a) + ' <span style="color:var(--ink-4)">vs</span> ' + scan(T, p.wallet_b) + '</span>'
    + '<span style="' + NOTIZ + '"><b style="color:var(--ink-1)">' + num(p.events) + '</b> opposite-side events in ' + num(p.markets) + ' markets</span></div>').join('')
    : '<div style="' + NOTIZ + '">No pairs repeatedly on opposite sides of the same book.</div>';
  return card('BEHAVIOUR · TIER 3',
    '<div style="' + LABEL + '; margin-bottom:var(--sp-2)">ORDER-SPLITTING FINGERPRINTS</div>' + fpBody
    + '<div style="' + LABEL + '; margin:var(--sp-4) 0 var(--sp-2)">COMPLEMENTARY BOOKS · WASH SUSPICION</div>' + pairBody,
    'patterns in the stored tape — shown next to the graph, never used to merge accounts');
}

function intro(d) {
  const s = d.stats || {};
  const tiles = [
    kpi({ label: 'WALLETS SCANNED', wert: num(s.scans || 0) }),
    kpi({ label: 'HARD EDGES', wert: num(s.hard_edges || 0) }),
    kpi({ label: 'LINKED ENTITIES', wert: num(s.multi_wallet_entities || 0) }),
    kpi({ label: 'CANDIDATES', wert: num(s.candidate_edges || 0) })
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
    + renderEntities(T, d)
    + renderCandidates(T, d)
    + renderBehavior(T, d)
    + (d.caveat ? '<div style="' + NOTIZ + '; margin-top:var(--sp-5); max-width:80ch">' + esc(d.caveat) + '</div>' : '')
    + (d.as_of ? '<div style="' + NOTIZ + '; margin-top:var(--sp-4)">as of ' + esc(d.as_of) + '</div>' : '')
    + '</div>';
}
