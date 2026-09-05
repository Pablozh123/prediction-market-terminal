// Arbitrage scan — the paper scanner's rolling read, as a section of the
// Cross-venue page ("Paper scanner: executable edge").
//
// Feeds off public/data/arb_scan.json, which the scanner in the
// prediction-alpha-bot repo writes (schema arb_scan/1), served as
// /api/research/arb-scan. Every figure here comes from that file; this
// module lays it out and derives nothing beyond counts, shares and ages.
// The file is produced elsewhere, so every field may be missing or null: a
// missing figure renders as a dash, never as a zero, and a missing list
// renders as a sentence that says so.
//
// Reading order follows the review's pattern for the study pages: title,
// one computed verdict sentence, the stamps, then the funnel (strategies,
// rejection reasons), the candidates themselves, the paper book, and last
// the paragraph that says what the numbers do and do not mean. The blocks
// are exported one by one; renderArbScanAbschnitt puts them together for
// core_pages.js::renderCross.

import { esc, num, money, stempel, stempelBlock, dauer } from '../util.js';
import { caveatZeile } from '../claims.js';
import { MONO as M, KARTE, LABEL, NOTIZ, kpi } from '../ui.js';

export const ARB_SCAN_DATEI = 'arb_scan.json';
export const ARB_RESOLUTIONS_DATEI = 'arb_resolutions.json';
// The element id the old study route (#research/arb-scan) scrolls to on the
// Cross-venue page. Starts with the page name: app.js drops pending anchors
// that do not.
export const ARB_ANKER = 'cross/paper-scanner';
// What the section is, in the words the study registration used to carry.
export const ARB_STUDIE = {
  title: 'Paper scanner: executable edge',
  stamp: 'paper scanner · rolling',
  note: 'Price gaps between Polymarket and Kalshi and inside one venue, screened for fees, depth and staleness, then paper-traded. The resolution rules of a pair count as unverified until a human has read both.'
};

const STRICH = '—';
const ZELLE = M + '; font-size:var(--t-small); white-space:nowrap';
const KOPF = 'padding:var(--sp-4) var(--sp-5); border-bottom:1px solid var(--line-2); background:var(--panel); position:sticky; top:0; z-index:3; ' + LABEL;
const ABSCHNITT = M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:var(--info); margin:var(--sp-6) 0 var(--sp-4)';

// Rule-match states as the scanner writes them. Anything else is shown as
// written, in the muted tone, so an unexpected value is visible rather than
// silently folded into one of the three.
const RULE_MATCH = {
  unverified: { text: 'UNVERIFIED', farbe: 'var(--ink-3)', rahmen: 'var(--line-1)' },
  reviewed: { text: 'REVIEWED', farbe: 'var(--pos)', rahmen: 'color-mix(in srgb, var(--pos) 40%, transparent)' },
  mismatch: { text: 'MISMATCH', farbe: 'var(--neg)', rahmen: 'color-mix(in srgb, var(--neg) 40%, transparent)' }
};

// Statuses that put a candidate in the upper table. Everything else (rejected,
// expired, anything unknown) goes below, folded, with its reason.
const OBEN = ['validated', 'paper_fired', 'paper', 'open', 'live'];

// A gap open for longer than this is capital waiting for resolution, not a
// price error about to close; the OPEN SINCE cell turns amber from here.
const LANGE_OFFEN_MIN = 60;

// ---- defensive readers ------------------------------------------------------

function zahl(v) {
  const n = typeof v === 'string' && v.trim() !== '' ? Number(v) : v;
  return typeof n === 'number' && isFinite(n) ? n : null;
}
function text(v) { return v == null ? '' : String(v); }
function liste(v) { return Array.isArray(v) ? v.filter((x) => x && typeof x === 'object') : []; }
function objekt(v) { return v && typeof v === 'object' && !Array.isArray(v) ? v : {}; }

function ganz(v) { const n = zahl(v); return n == null ? STRICH : num(Math.round(n)); }
function bps(v) { const n = zahl(v); return n == null ? STRICH : (Math.abs(n) % 1 ? n.toFixed(1) : String(Math.round(n))) + ' bps'; }
function usd(v) {
  const n = zahl(v);
  if (n == null) return STRICH;
  // Under $1,000 the scanner's sizes are small and the cents matter.
  if (Math.abs(n) < 1000) return (n < 0 ? '-$' : '$') + Math.abs(n).toFixed(2);
  return (n < 0 ? '-' : '') + money(Math.abs(n));
}
function vorzeichenUsd(v) { const n = zahl(v); return n == null ? STRICH : (n >= 0 ? '+$' : '-$') + Math.abs(n).toFixed(2); }
function prozent(v) { const n = zahl(v); return n == null ? STRICH : n.toFixed(1) + '%'; }
function tage(v) { const n = zahl(v); return n == null ? STRICH : (n < 100 ? n.toFixed(1) : String(Math.round(n))) + ' d'; }
function preis(v) { const n = zahl(v); return n == null ? STRICH : (n * 100).toFixed(1) + '¢'; }

function minutenSeit(iso, jetztMs) {
  if (!iso) return null;
  const t = new Date(iso);
  if (isNaN(t)) return null;
  return Math.max(0, (jetztMs - t.getTime()) / 60000);
}

function shaKurz(sha) { const s = text(sha).trim(); return s.length > 7 ? s.slice(0, 7) : s; }

// ---- pure readings, exported for the render harness -------------------------

/** Health as a reading: alive, age of the last cycle, and whether to warn.
 *  Warn when the scanner says it is not alive, or when the last cycle is
 *  older than three scan intervals. Without an interval the age is shown
 *  but cannot be judged, so only the alive flag decides. */
export function healthStand(health, jetztMs) {
  const h = objekt(health);
  const jetzt = typeof jetztMs === 'number' ? jetztMs : Date.now();
  const alive = h.alive === true ? true : (h.alive === false ? false : null);
  const alterMin = minutenSeit(h.last_cycle_at, jetzt);
  const intervallMs = zahl(h.scan_interval_ms);
  const grenzeMin = intervallMs != null && intervallMs > 0 ? (3 * intervallMs) / 60000 : null;
  const zuAlt = alterMin != null && grenzeMin != null && alterMin > grenzeMin;
  const bekannt = alive != null || alterMin != null;
  return {
    alive, alterMin, grenzeMin, zuAlt, bekannt,
    warnung: bekannt && (alive === false || zuAlt),
    cycles: zahl(h.cycles_24h), errors: zahl(h.errors_24h)
  };
}

/** The one-sentence finding under the title. Renders only when the summary
 *  carries both counts it is built from; the resolved count joins when it is
 *  there. */
export function verdiktSatz(summary) {
  const s = objekt(summary);
  const raw = zahl(s.raw_candidates_24h);
  const val = zahl(s.validated_24h);
  if (raw == null || val == null) return '';
  const res = zahl(s.resolved_paper_trades);
  let satz = num(Math.round(val)) + ' validated of ' + num(Math.round(raw)) + ' raw candidate' + (Math.round(raw) === 1 ? '' : 's') + ' in 24 h';
  if (res != null) satz += ', ' + num(Math.round(res)) + ' paper trade' + (Math.round(res) === 1 ? '' : 's') + ' resolved';
  return satz + '.';
}

/** Candidates split into the upper table (validated, paper) and the folded
 *  lower one (rejected, expired, unknown status), each sorted by executable
 *  net edge, largest first, unknown edges last. */
export function teileChancen(opportunities) {
  const alle = liste(opportunities);
  const oben = [], unten = [];
  alle.forEach((o) => {
    const st = text(o.status).trim().toLowerCase();
    const abgelehnt = st ? OBEN.indexOf(st) < 0 : !!text(o.rejection_reason).trim();
    (abgelehnt ? unten : oben).push(o);
  });
  const nachEdge = (a, b) => {
    const x = zahl(a.executable_net_edge_bps), y = zahl(b.executable_net_edge_bps);
    if (x == null && y == null) return 0;
    if (x == null) return 1;
    if (y == null) return -1;
    return y - x;
  };
  oben.sort(nachEdge);
  unten.sort(nachEdge);
  return { oben, unten };
}

// ---- pieces -----------------------------------------------------------------

function leerSatz(satz) {
  return '<div style="padding:var(--sp-5); ' + M + '; font-size:var(--t-small); color:var(--ink-3); line-height:var(--lh-prose)">' + esc(satz) + '</div>';
}

function chip(textInhalt, farbe, rahmen) {
  return '<span style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps); color:' + farbe
    + '; border:1px solid ' + rahmen + '; border-radius:var(--r-control); padding:var(--sp-1) var(--sp-3); white-space:nowrap">' + esc(textInhalt) + '</span>';
}

function ruleChip(wert) {
  const key = text(wert).trim().toLowerCase();
  const r = RULE_MATCH[key || 'unverified'];
  if (r) return chip(r.text, r.farbe, r.rahmen);
  return chip(key.toUpperCase(), 'var(--muted)', 'var(--line-1)');
}

// Health strip: alive, age of the last cycle against its limit, cycles and
// errors over 24 h. The whole strip borders amber when the reading warns.
export function healthHtml(stand) {
  if (!stand.bekannt) {
    return '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-4); margin-top:var(--sp-4)">SCANNER HEALTH not in payload</div>';
  }
  const farbe = stand.warnung ? 'var(--warn)' : 'var(--pos)';
  const punkt = '<span style="width:7px; height:7px; border-radius:50%; background:' + farbe + '; display:inline-block; margin-right:var(--sp-3)"></span>';
  const teile = [];
  teile.push(punkt + (stand.alive === true ? 'ALIVE' : stand.alive === false ? 'NOT ALIVE' : 'ALIVE FLAG MISSING'));
  if (stand.alterMin != null) {
    const alter = stand.alterMin < 1 ? '&lt;1 min' : stand.alterMin < 90 ? stand.alterMin.toFixed(stand.alterMin < 10 ? 1 : 0) + ' min' : dauer(stand.alterMin);
    teile.push('last cycle ' + alter + ' ago'
      + (stand.grenzeMin != null ? ' <span style="color:var(--ink-4)">(limit ' + (stand.grenzeMin < 1 ? (stand.grenzeMin * 60).toFixed(0) + ' s' : stand.grenzeMin.toFixed(1) + ' min') + ' = 3 intervals)</span>' : ' <span style="color:var(--ink-4)">(no scan interval in payload)</span>'));
  } else {
    teile.push('last cycle time missing');
  }
  teile.push((stand.cycles == null ? STRICH : num(Math.round(stand.cycles))) + ' cycles / 24 h');
  teile.push('<span style="color:' + (stand.errors ? 'var(--warn)' : 'inherit') + '">' + (stand.errors == null ? STRICH : num(Math.round(stand.errors))) + ' error' + (stand.errors === 1 ? '' : 's') + ' / 24 h</span>');
  return '<div style="display:flex; gap:var(--sp-5); flex-wrap:wrap; align-items:center; margin-top:var(--sp-4); padding:var(--sp-3) var(--sp-4); '
    + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps); color:' + (stand.warnung ? 'var(--warn)' : 'var(--ink-2)')
    + '; border-left:2px solid ' + farbe + '; background:var(--panel)">'
    + teile.map((t) => '<span>' + t + '</span>').join('<span style="color:var(--ink-4)">·</span>')
    + '</div>';
}

export function kennzahlen(summary) {
  const s = objekt(summary);
  const pnl = zahl(s.resolved_paper_pnl_usd);
  const note = text(s.sample_note).trim();
  const tiles = [
    { label: 'RAW CANDIDATES 24H', wert: ganz(s.raw_candidates_24h), sub: 'before any check' },
    { label: 'VALIDATED 24H', wert: ganz(s.validated_24h), sub: 'passed fees, depth, staleness' },
    { label: 'PAPER FIRED 24H', wert: ganz(s.paper_fired_24h), sub: 'paper book only' },
    { label: 'OPEN PAPER POSITIONS', wert: ganz(s.open_paper_positions), sub: 'awaiting resolution' },
    { label: 'RESOLVED PAPER TRADES', wert: ganz(s.resolved_paper_trades), sub: 'n for the figure to the right' },
    { label: 'RESOLVED PAPER PNL', wert: vorzeichenUsd(pnl), ton: pnl == null ? null : (pnl >= 0 ? 'up' : 'down'), sub: note || 'paper result, not realized' }
  ];
  return '<div style="display:grid; grid-template-columns:repeat(6, minmax(0, 1fr)); gap:var(--sp-4); margin-top:var(--sp-5)">'
    + tiles.map((t) => kpi({ label: esc(t.label), wert: esc(t.wert), sub: esc(t.sub), ton: t.ton || null, kuerzen: t.label !== 'RESOLVED PAPER PNL' })).join('')
    + '</div>';
}

// Funnel per strategy: raw, validated, paper, and the reason that rejected
// most. The share is validated over raw, only where raw is a number above 0.
export function trichter(strategies) {
  const rows = liste(strategies);
  const SPALTEN = 'minmax(220px, 1.4fr) 96px 120px 96px minmax(180px, 1fr)';
  const kopf = '<div style="display:grid; grid-template-columns:' + SPALTEN + '; gap:var(--sp-4); ' + KOPF + '">'
    + '<div>STRATEGY</div><div style="text-align:right">RAW 24H</div><div style="text-align:right">VALIDATED</div><div style="text-align:right">PAPER</div><div>TOP REJECTION</div></div>';
  const koerper = rows.length ? rows.map((r) => {
    const raw = zahl(r.raw_24h), val = zahl(r.validated_24h);
    const anteil = raw != null && raw > 0 && val != null ? ' <span style="color:var(--ink-4)">' + (100 * val / raw).toFixed(val / raw < 0.1 ? 1 : 0) + '%</span>' : '';
    return '<div style="display:grid; grid-template-columns:' + SPALTEN + '; gap:var(--sp-4); align-items:baseline; padding:var(--sp-4) var(--sp-5); border-bottom:1px solid var(--line-3)">'
      + '<div><div style="font-size:var(--t-body); color:var(--ink-1)">' + esc(text(r.label).trim() || text(r.id).trim() || STRICH) + '</div>'
      + (text(r.label).trim() && text(r.id).trim() ? '<div style="' + NOTIZ + '; margin-top:var(--sp-1)">' + esc(r.id) + '</div>' : '') + '</div>'
      + '<div style="text-align:right; ' + ZELLE + '; color:var(--text)">' + ganz(raw) + '</div>'
      + '<div style="text-align:right; ' + ZELLE + '; color:var(--text)">' + ganz(val) + anteil + '</div>'
      + '<div style="text-align:right; ' + ZELLE + '; color:var(--text)">' + ganz(r.paper_24h) + '</div>'
      + '<div style="' + ZELLE + '; color:var(--ink-3); white-space:normal">' + esc(text(r.top_rejection).trim() || STRICH) + '</div>'
      + '</div>';
  }).join('') : leerSatz('No strategies in the payload.');
  return '<div style="' + ABSCHNITT + '">FUNNEL BY STRATEGY · LAST 24 H</div>'
    + '<div style="' + KARTE + '">' + kopf + koerper + '</div>';
}

// Rejection reasons as horizontal bars, longest first. Width is the count
// against the largest count, so the bars compare reasons with each other.
export function ablehnungen(rejections) {
  const rows = liste(rejections).map((r) => ({ reason: text(r.reason).trim(), count: zahl(r.count) }))
    .filter((r) => r.reason || r.count != null);
  rows.sort((a, b) => (b.count == null ? -1 : b.count) - (a.count == null ? -1 : a.count));
  const max = rows.reduce((m, r) => Math.max(m, r.count == null ? 0 : r.count), 0);
  const summe = rows.reduce((m, r) => m + (r.count == null ? 0 : r.count), 0);
  const balken = rows.length ? rows.map((r) => {
    const breite = max > 0 && r.count != null ? Math.max(0, Math.min(100, (100 * r.count) / max)) : 0;
    return '<div style="display:grid; grid-template-columns:minmax(200px, 280px) 1fr 72px; gap:var(--sp-4); align-items:center; padding:var(--sp-3) var(--sp-5)">'
      + '<div style="' + ZELLE + '; color:var(--ink-2); overflow:hidden; text-overflow:ellipsis" title="' + esc(r.reason) + '">' + esc(r.reason || STRICH) + '</div>'
      + '<div style="height:10px; background:rgba(var(--ink),.06); border-radius:var(--r-control); overflow:hidden">'
      + '<div style="height:100%; width:' + breite.toFixed(1) + '%; background:var(--warn); opacity:.85"></div></div>'
      + '<div style="text-align:right; ' + ZELLE + '; color:var(--text)">' + (r.count == null ? STRICH : num(Math.round(r.count))) + '</div>'
      + '</div>';
  }).join('') : leerSatz('No rejections recorded in the last 24 h.');
  return '<div style="' + ABSCHNITT + '">WHY CANDIDATES WERE REJECTED · LAST 24 H' + (rows.length ? ' · ' + num(summe) + ' REJECTIONS' : '') + '</div>'
    + '<div style="' + KARTE + '; padding:var(--sp-3) 0">' + balken + '</div>';
}

// One leg of a candidate: venue, side, price, size, role, fee.
function legsHtml(legs) {
  const rows = liste(legs);
  if (!rows.length) return '<div style="' + NOTIZ + '">No legs in the payload for this candidate.</div>';
  const SPALTEN = '110px 100px 80px 96px 80px 80px';
  return '<div style="display:grid; grid-template-columns:' + SPALTEN + '; gap:var(--sp-4); ' + LABEL + '; padding-bottom:var(--sp-2); border-bottom:1px solid var(--line-3)">'
    + '<div>VENUE</div><div>SIDE</div><div style="text-align:right">PRICE</div><div style="text-align:right">SIZE</div><div>ROLE</div><div style="text-align:right">FEE</div></div>'
    + rows.map((l) => '<div style="display:grid; grid-template-columns:' + SPALTEN + '; gap:var(--sp-4); padding:var(--sp-2) 0; ' + ZELLE + '; color:var(--ink-1)">'
      + '<div>' + esc(text(l.venue).trim() || STRICH) + '</div>'
      + '<div>' + esc(text(l.side).trim() || STRICH) + '</div>'
      + '<div style="text-align:right">' + preis(l.price) + '</div>'
      + '<div style="text-align:right">' + usd(l.size_usd) + '</div>'
      + '<div style="color:var(--ink-3)">' + esc(text(l.role).trim() || STRICH) + '</div>'
      + '<div style="text-align:right">' + usd(l.fee_usd) + '</div>'
      + '</div>').join('');
}

function venuesVon(o) {
  const direkt = Array.isArray(o.venues) ? o.venues.map((v) => text(v).trim()).filter(Boolean) : [];
  if (direkt.length) return direkt;
  const ausLegs = [];
  liste(o.legs).forEach((l) => { const v = text(l.venue).trim(); if (v && ausLegs.indexOf(v) < 0) ausLegs.push(v); });
  return ausLegs;
}

function offenSeit(o, jetztMs) {
  const sek = zahl(o.open_seconds);
  const min = sek != null ? sek / 60 : minutenSeit(o.first_seen_at, jetztMs);
  if (min == null) return { text: STRICH, lang: false };
  return { text: dauer(min), lang: min > LANGE_OFFEN_MIN };
}

const CHANCE_SPALTEN = 'minmax(230px, 1fr) 76px 76px 76px 80px 52px 66px 92px 78px';

function chanceKopf() {
  return '<div style="display:grid; grid-template-columns:' + CHANCE_SPALTEN + '; gap:var(--sp-3); ' + KOPF + '">'
    + '<div>CANDIDATE · STRATEGY · VENUES</div>'
    + '<div style="text-align:right">GROSS</div><div style="text-align:right">NET EXEC.</div>'
    + '<div style="text-align:right">DEPTH</div><div style="text-align:right">CAPITAL</div>'
    + '<div style="text-align:right">DAYS</div><div style="text-align:right">ANN.</div>'
    + '<div>RULE MATCH</div><div style="text-align:right">OPEN SINCE</div></div>';
}

// A candidate is one <details>: the summary is the table row, the body the
// legs and the identifiers. data-key keeps it open across the 30 s re-render.
function chanceZeile(o, i, abgelehnt, jetztMs) {
  const id = text(o.id).trim() || 'row-' + i;
  const netto = zahl(o.executable_net_edge_bps);
  const nettoFarbe = netto == null ? 'var(--ink-4)' : netto > 0 ? 'var(--pos)' : 'var(--neg-soft)';
  const offen = offenSeit(o, jetztMs);
  const venues = venuesVon(o);
  const grund = text(o.rejection_reason).trim();
  const status = text(o.status).trim();
  const unterzeile = [esc(text(o.strategy).trim() || 'strategy ' + STRICH), venues.length ? esc(venues.join(' ↔ ')) : 'venues ' + STRICH]
    .concat(abgelehnt ? ['<span style="color:var(--warn)">' + esc(status || 'rejected') + (grund ? ': ' + esc(grund) : '') + '</span>'] : (status && status.toLowerCase() !== 'validated' ? [esc(status)] : []));
  return '<details data-key="arb:opp:' + esc(id) + '" style="border-bottom:1px solid var(--line-3)">'
    + '<summary style="display:grid; grid-template-columns:' + CHANCE_SPALTEN + '; gap:var(--sp-3); align-items:center; padding:var(--sp-4) var(--sp-5); cursor:pointer; list-style:none">'
    + '<div style="min-width:0"><div style="font-size:var(--t-body); color:var(--ink-1); line-height:var(--lh-snug)">' + esc(text(o.title).trim() || STRICH) + '</div>'
    + '<div style="' + NOTIZ + '; margin-top:var(--sp-1); white-space:nowrap; overflow:hidden; text-overflow:ellipsis">' + unterzeile.join(' · ') + '</div></div>'
    + '<div style="text-align:right; ' + ZELLE + '; color:var(--text)">' + bps(o.gross_edge_bps) + '</div>'
    + '<div style="text-align:right; ' + ZELLE + '; color:' + nettoFarbe + '">' + bps(netto) + '</div>'
    + '<div style="text-align:right; ' + ZELLE + '; color:var(--text)">' + usd(o.depth_usd) + '</div>'
    + '<div style="text-align:right; ' + ZELLE + '; color:var(--text)">' + usd(o.capital_usd) + '</div>'
    + '<div style="text-align:right; ' + ZELLE + '; color:var(--text)">' + tage(o.days_to_resolution) + '</div>'
    + '<div style="text-align:right; ' + ZELLE + '; color:var(--text)">' + prozent(o.annualized_pct) + '</div>'
    + '<div>' + ruleChip(o.rule_match) + '</div>'
    + '<div style="text-align:right; ' + ZELLE + '; color:' + (offen.lang ? 'var(--warn)' : 'var(--text)') + '"' + (offen.lang ? ' title="open for over an hour: capital waiting for resolution, not a closing price error"' : '') + '>' + esc(offen.text) + '</div>'
    + '</summary>'
    + '<div style="padding:0 var(--sp-5) var(--sp-5) var(--sp-5)">'
    + '<div style="' + LABEL + '; margin-bottom:var(--sp-3)">LEGS</div>'
    + legsHtml(o.legs)
    + '<div style="' + NOTIZ + '; margin-top:var(--sp-4)">'
    + 'id ' + esc(id)
    + (text(o.market_ref).trim() ? ' · ref ' + esc(text(o.market_ref).trim()) : '')
    + (o.first_seen_at ? ' · first seen ' + esc(stempel(o.first_seen_at)) : '')
    + (o.last_seen_at ? ' · last seen ' + esc(stempel(o.last_seen_at)) : '')
    + (status ? ' · status ' + esc(status) : '')
    + (grund ? ' · rejection ' + esc(grund) : '')
    + ' · rule match ' + esc(text(o.rule_match).trim() || 'unverified')
    + '</div></div></details>';
}

export function chancen(opportunities, jetztMs) {
  const { oben, unten } = teileChancen(opportunities);
  const gesamt = oben.length + unten.length;
  const obenHtml = oben.length
    ? oben.map((o, i) => chanceZeile(o, i, false, jetztMs)).join('')
    : leerSatz(gesamt ? 'No validated candidates in the payload; every candidate below was rejected.' : 'No candidates in the payload.');
  const untenHtml = unten.length
    ? '<details data-key="arb:rejected" style="border-top:1px solid var(--line-2)">'
      + '<summary style="cursor:pointer; padding:var(--sp-4) var(--sp-5); list-style:none; ' + LABEL + '">REJECTED · ' + unten.length + ' CANDIDATE' + (unten.length === 1 ? '' : 'S') + ' WITH REASON ▸</summary>'
      + unten.map((o, i) => chanceZeile(o, i, true, jetztMs)).join('')
      + '</details>'
    : '';
  return '<div style="' + ABSCHNITT + '">CANDIDATES · ' + (oben.length ? oben.length + ' VALIDATED' : 'NONE VALIDATED') + (unten.length ? ' · ' + unten.length + ' REJECTED' : '') + '</div>'
    + '<div style="' + KARTE + '">' + chanceKopf() + obenHtml + untenHtml + '</div>'
    + '<div style="' + NOTIZ + '; margin-top:var(--sp-3)">Each row opens to its legs. GROSS is the quoted gap, NET EXEC. the gap after both legs\' fees at the quoted depth. ANN. divides the net edge by days to resolution; a small edge over many days is carry, not a mispricing.</div>';
}

/** The resolution pass as a reading: a map trade_id -> row, or null when
 *  the payload is absent, failed, or carries no trades. Exported for the
 *  render harness. */
export function aufloesungen(payload) {
  const p = payload && typeof payload === 'object' && payload._quelle !== 'leer' && payload._quelle !== 'fehler' ? payload : null;
  if (!p) return null;
  const rows = liste(p.trades);
  if (!rows.length) return null;
  const map = new Map();
  rows.forEach((r) => { const id = text(r.trade_id).trim(); if (id) map.set(id, r); });
  return { map, summary: objekt(p.summary), baskets: liste(p.baskets), generated_at: text(p.generated_at), source: text(p.source), method: text(p.method) };
}

/** What one resolved leg made: the corrected figure, which exists only
 *  where the market was open at the fill and the CLOB day price supports
 *  the entry. The as-recorded figure stays in the file; on screen it would
 *  turn a NO recorded at a few cents into hundreds of shares. */
export function legPnl(r) {
  return r ? zahl(r.pnl_corrected_usd) : null;
}

// Tiles for our own resolution pass. They sit under the scanner's tiles
// and say where the figures come from, because the scanner's own tiles
// still show zero resolved trades: its lookup never finds a settled
// market (it asks Gamma without closed=true).
export function aufloesungKennzahlen(auf) {
  if (!auf) return '';
  const s = auf.summary;
  const pnl = zahl(s.pnl_corrected_usd);
  const nKorr = zahl(s.with_corrected_pnl);
  const won = zahl(s.won_corrected);
  const lost = zahl(s.lost_corrected);
  const flat = zahl(s.flat_corrected);
  const tage = zahl(s.mean_days_held);
  const nicht = zahl(s.baskets_not_exclusive);
  const koerbe = zahl(s.baskets);
  const nach = zahl(s.filled_after_close);
  const tiles = [
    { label: 'SETTLED MARKETS', wert: ganz(s.resolved) + ' / ' + ganz(s.trades), sub: 'journal trades whose market has settled' },
    { label: 'FILLED AFTER CLOSE', wert: nach == null ? STRICH : ganz(nach), ton: nach ? 'down' : null, sub: 'paper fills on markets already closed' },
    { label: 'WON · LOST · FLAT', wert: (won == null ? STRICH : ganz(won)) + ' · ' + (lost == null ? STRICH : ganz(lost)) + ' · ' + (flat == null ? STRICH : ganz(flat)), sub: 'n = ' + (nKorr == null ? STRICH : ganz(nKorr)) + ' legs with a supported entry' },
    { label: 'MODELED PNL', wert: vorzeichenUsd(pnl), ton: pnl == null ? null : (pnl >= 0 ? 'up' : 'down'), sub: 'on ' + usd(s.cost_corrected_usd) + ' staked, before fees' },
    { label: 'MEAN DAYS TO SETTLE', wert: tage == null ? STRICH : tage.toFixed(1), sub: 'fill to closedTime, n = ' + ganz(s.days_held_n) },
    { label: 'BASKETS NOT EXCLUSIVE', wert: (nicht == null ? STRICH : ganz(nicht)) + ' / ' + (koerbe == null ? STRICH : ganz(koerbe)), sub: 'NO on every leg is no arbitrage there' }
  ];
  return '<div style="' + ABSCHNITT + '">RESOLUTION PASS · ' + esc((stempel(auf.generated_at) || 'time not in payload').toUpperCase()) + '</div>'
    + '<div style="display:grid; grid-template-columns:repeat(6, minmax(0, 1fr)); gap:var(--sp-4)">'
    + tiles.map((t) => kpi({ label: esc(t.label), wert: esc(t.wert), sub: esc(t.sub), ton: t.ton || null, kuerzen: t.label !== 'MODELED PNL' })).join('')
    + '</div>'
    + '<div style="font-size:var(--t-small); color:var(--ink-3); margin-top:var(--sp-3); max-width:760px; line-height:var(--lh-prose)">'
    + esc(auf.source ? auf.source + '. ' : '') + 'The scanner\'s own tiles above still show zero resolved trades: its lookup asks Gamma without closed=true and never finds a settled market. '
    + 'A leg gets a figure only where the market was open at the fill and the CLOB day price supports the entry; where the journal stored the other side\'s price, the entry is 1 minus the recorded one. '
    + 'Everything else carries a reason instead of a number.'
    + '</div>';
}

export function paperBuch(positions, summary, resolutions) {
  const rows = liste(positions);
  const note = text(objekt(summary).sample_note).trim();
  const auf = aufloesungen(resolutions);
  const SPALTEN = 'minmax(220px, 1fr) 150px 130px 84px 92px 84px 84px';
  const kopf = '<div style="display:grid; grid-template-columns:' + SPALTEN + '; gap:var(--sp-3); ' + KOPF + '">'
    + '<div>PAPER TRADE</div><div>STRATEGY</div><div>OPENED</div><div style="text-align:right">CAPITAL</div><div style="text-align:right">EXP. EDGE</div><div>STATUS</div><div style="text-align:right">PNL</div></div>';
  const koerper = rows.length ? rows.map((p) => {
    // Our resolution pass fills the gap the scanner leaves: where the
    // scanner still says 'open' (it never finds a settled market, because
    // it asks Gamma without closed=true), the pass supplies status, date
    // and figure. A row the scanner has resolved itself keeps the
    // scanner's own status and figure.
    const eigen = text(p.status).trim().toLowerCase();
    const r = auf && eigen !== 'resolved' ? auf.map.get(text(p.trade_id).trim()) || null : null;
    const gel = !!(r && text(r.status).trim().toLowerCase() === 'resolved');
    const pnl = gel ? legPnl(r) : zahl(p.pnl_usd);
    const status = gel ? 'resolved' : eigen;
    const settle = gel ? zahl(r.settlement_price) : null;
    const tageGel = gel ? zahl(r.days_held) : null;
    const grund = gel && pnl == null ? text(r.pnl_corrected_reason || r.pnl_reason).trim() : '';
    return '<div style="display:grid; grid-template-columns:' + SPALTEN + '; gap:var(--sp-3); align-items:center; padding:var(--sp-4) var(--sp-5); border-bottom:1px solid var(--line-3)">'
      + '<div style="min-width:0"><div style="font-size:var(--t-body); color:var(--ink-1); line-height:var(--lh-snug)">' + esc(text(p.title).trim() || STRICH) + '</div>'
      + '<div style="' + NOTIZ + '; margin-top:var(--sp-1)">' + esc(text(p.trade_id).trim() || STRICH) + (text(p.opportunity_id).trim() ? ' · from ' + esc(p.opportunity_id) : '') + '</div></div>'
      + '<div style="' + ZELLE + '; color:var(--ink-2); overflow:hidden; text-overflow:ellipsis">' + esc(text(p.strategy).trim() || STRICH) + '</div>'
      + '<div style="' + ZELLE + '; color:var(--ink-3)">' + esc(stempel(p.opened_at) || STRICH) + '</div>'
      + '<div style="text-align:right; ' + ZELLE + '; color:var(--text)">' + usd(p.capital_usd) + '</div>'
      + '<div style="text-align:right; ' + ZELLE + '; color:var(--text)">' + bps(p.expected_edge_bps) + '</div>'
      + '<div style="' + ZELLE + '; color:' + (status === 'open' ? 'var(--info)' : 'var(--ink-3)') + '">' + esc(status || STRICH)
      + (gel ? '<div style="' + NOTIZ + '; margin-top:var(--sp-1)">' + esc((stempel(r.resolved_at) || STRICH) + (tageGel == null ? '' : ' · ' + tage(tageGel))) + '</div>' : '') + '</div>'
      + '<div style="text-align:right; ' + ZELLE + '; color:' + (pnl == null ? 'var(--ink-4)' : pnl >= 0 ? 'var(--pos)' : 'var(--neg)') + '">' + (pnl == null ? (status === 'open' ? 'open' : (grund ? esc(grund) : STRICH)) : vorzeichenUsd(pnl))
      + (gel && settle != null ? '<div style="' + NOTIZ + '; margin-top:var(--sp-1)">' + esc('settled ' + preis(settle) + (text(r.entry_check).trim() === 'complement' ? ' · entry corrected' : '')) + '</div>' : '') + '</div>'
      + '</div>';
  }).join('') : leerSatz('No paper positions in the payload.');
  return '<div style="' + ABSCHNITT + '">PAPER BOOK · ' + (rows.length ? rows.length + ' POSITION' + (rows.length === 1 ? '' : 'S') : 'EMPTY') + '</div>'
    + '<div style="' + KARTE + '">' + kopf + koerper + '</div>'
    + caveatZeile('modeled_not_realized', {
      vorsatz: (note ? esc(note) + ' ' : '') + 'Paper fills assume the quoted depth was available at the quoted price.',
      stil: 'font-size:var(--t-small); color:var(--ink-3); margin-top:var(--sp-3); max-width:760px; line-height:var(--lh-prose)'
    });
}

export function methodik() {
  const absatz = (t) => '<div style="font-size:var(--t-body); color:var(--ink-2); line-height:var(--lh-prose); max-width:720px; margin-top:var(--sp-3)">' + t + '</div>';
  return '<div style="' + ABSCHNITT + '">HOW TO READ THIS</div>'
    + '<div style="' + KARTE + '; padding:var(--sp-5) var(--sp-6)">'
    + absatz('<b style="color:var(--ink-1); font-weight:600">Executable net edge</b> is the quoted gap after the fee schedule of both venues on both legs, taken at the size the books actually showed (DEPTH), not at the mid. A gap that only exists for the first dollar is not an edge; the scanner sizes each leg to the thinner book and charges the fee curve on that size. Nothing here accounts for the slippage of a real order or for a quote that vanishes between the scan and the click.')
    + absatz('<b style="color:var(--ink-1); font-weight:600">Rule match is unverified by default.</b> Two markets with the same title can resolve on different sources, at different times, or on different definitions. UNVERIFIED means nobody has read both rule texts; REVIEWED means a human did and found them equivalent; MISMATCH means they differ, and such a pair is not an arbitrage at all, whatever the numbers say.')
    + absatz('<b style="color:var(--ink-1); font-weight:600">A gap that stays open is not a mispricing waiting to close.</b> Both legs pay out at resolution, so capital is locked until then and the annualized column just spreads a small edge over that wait. Long OPEN SINCE values mean the market is charging for the capital, the counterparty risk of two venues, and the rule risk above. That is carry, not arbitrage.')
    + '</div>';
}

// The section without a usable file: which file, who writes it, why nothing
// is shown instead of a placeholder. A failed fetch is named as such; a
// request still running says so and names the file too.
export function leerzustand(payload) {
  const fehler = payload && payload._quelle === 'fehler';
  const laedt = payload == null;
  const satz = laedt
    ? 'Loading <span style="' + M + '">public/data/' + esc(ARB_SCAN_DATEI) + '</span>. The section fills in when the file answers; nothing is shown before, and no figure is a placeholder.'
    : fehler
      ? '<span style="' + M + '">public/data/' + esc(ARB_SCAN_DATEI) + '</span> did not answer: ' + esc(text(payload._fehler) || 'unknown error') + '. Nothing is shown rather than a stale or invented figure.'
      : 'No scan file yet. This section reads <span style="' + M + '">public/data/' + esc(ARB_SCAN_DATEI) + '</span>, which the arbitrage scanner in the prediction-alpha-bot repo writes on every cycle. Until that file exists here, nothing is shown: no placeholder candidate, no placeholder figure.';
  return '<div style="' + KARTE + '; padding:var(--sp-6); max-width:720px; margin-top:var(--sp-4)">'
    + '<h2 style="font-size:var(--t-lead); font-weight:600">' + esc(ARB_STUDIE.title) + '</h2>'
    + '<div style="font-size:var(--t-body); color:var(--ink-4); margin-top:var(--sp-4); line-height:var(--lh-prose)">' + satz + '</div>'
    + '</div>';
}

// ---- section ----------------------------------------------------------------

/** The section on the Cross-venue page. payload is the parsed arb_scan.json,
 *  one of the loader's markers ({ _quelle: 'leer' | 'fehler' }), or null while
 *  the request runs. jetztMs is injectable so the harness can pin the clock;
 *  the app passes nothing. */
export function renderArbScanAbschnitt(payload, jetztMs, resolutions) {
  const eyebrow = '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-max); color:var(--info)">PAPER SCANNER · EXECUTABLE EDGE</div>';
  const huelle = (inhalt) => '<div id="' + ARB_ANKER + '" style="padding:var(--sp-6); border-top:1px solid var(--line-2); scroll-margin-top:16px">' + eyebrow + inhalt + '</div>';
  const jetzt = typeof jetztMs === 'number' ? jetztMs : Date.now();
  const p = payload && typeof payload === 'object' && payload._quelle !== 'leer' && payload._quelle !== 'fehler' ? payload : null;
  if (!p) return huelle(leerzustand(payload));
  const study = ARB_STUDIE;

  const gen = objekt(p.generator);
  // The resolution pass explains the paper book's rows; without rows it
  // has nothing to explain and stays away.
  const auf = liste(p.paper_positions).length ? resolutions : null;
  const health = healthStand(p.health, jetzt);
  const verdikt = verdiktSatz(p.summary);
  const kennung = text(p.kennzeichnung).trim() || ((text(gen.mode).trim() || 'paper') + ' scanner / descriptive');
  const sha = shaKurz(gen.git_sha);
  const schnappschuss = ['Snapshot ' + (stempel(p.generated_at) || 'time not in payload')]
    .concat(text(gen.repo).trim() ? ['generator ' + text(gen.repo).trim() + (sha ? '@' + sha : '')] : (sha ? ['generator @' + sha] : []))
    .concat(text(gen.mode).trim() ? ['mode ' + text(gen.mode).trim()] : [])
    .concat(text(p.schema).trim() ? ['schema ' + text(p.schema).trim()] : []);
  const KNOPF = 'font-size:var(--t-body); color:var(--text); border:1px solid var(--line-1); border-radius:var(--r-control); padding:var(--sp-4) var(--sp-5); cursor:pointer; text-decoration:none; display:inline-block';

  return huelle(''
    + '<div style="display:flex; align-items:flex-start; justify-content:space-between; gap:var(--sp-6); flex-wrap:wrap; margin-top:var(--sp-3)">'
    + '<div style="max-width:720px">'
    + '<h2 style="font-size:var(--t-head); font-weight:600">' + esc(study.title) + '</h2>'
    + (verdikt ? '<div style="font-size:var(--t-lead); color:var(--text); margin-top:var(--sp-3); line-height:var(--lh-snug); font-weight:500">' + esc(verdikt) + '</div>' : '')
    + '<div style="font-size:var(--t-body); color:var(--ink-3); margin-top:var(--sp-3); line-height:var(--lh-snug)">' + esc(study.note) + '</div>'
    + '</div>'
    + '<div style="display:flex; gap:var(--sp-3); align-items:flex-start">'
    + '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps); border-radius:var(--r-control); padding:var(--sp-2) var(--sp-3); color:var(--on-accent); background:var(--accent); white-space:nowrap">' + esc(kennung.toUpperCase()) + '</div>'
    + stempelBlock(study, { stand_utc: p.generated_at })
    + '</div></div>'
    + healthHtml(health)
    + (text(p.disclaimer).trim()
      ? '<div style="font-size:var(--t-small); color:var(--ink-3); margin-top:var(--sp-4); line-height:var(--lh-prose); max-width:760px; border-left:2px solid var(--line-1); padding-left:var(--sp-4)">'
        + '<span style="' + LABEL + '">GENERATOR\'S DISCLAIMER</span><br>' + esc(text(p.disclaimer).trim()) + '</div>'
      : '')
    + caveatZeile('parity_not_arbitrage', { stil: 'font-size:var(--t-small); color:var(--ink-4); margin-top:var(--sp-3); max-width:760px; line-height:var(--lh-prose)' })
    + kennzahlen(p.summary)
    + trichter(p.strategies)
    + ablehnungen(p.rejections_24h)
    + chancen(p.opportunities, jetzt)
    + aufloesungKennzahlen(aufloesungen(auf))
    + paperBuch(p.paper_positions, p.summary, auf)
    + methodik()
    + '<div style="display:flex; gap:var(--sp-5); align-items:center; flex-wrap:wrap; margin-top:var(--sp-6)">'
    + '<a href="./data/' + ARB_SCAN_DATEI + '" download="' + ARB_SCAN_DATEI + '" class="hv-edge-max" style="' + KNOPF + '">Download the data</a>'
    + (aufloesungen(auf) ? '<a href="./data/' + ARB_RESOLUTIONS_DATEI + '" download="' + ARB_RESOLUTIONS_DATEI + '" class="hv-edge-max" style="' + KNOPF + '">Download the resolutions</a>' : '')
    + '<div style="' + NOTIZ + '">' + esc(schnappschuss.join(' · ')) + '</div>'
    + '</div>');
}
