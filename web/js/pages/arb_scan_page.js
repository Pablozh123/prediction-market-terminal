// Arbitrage scan — the paper scanner's rolling read, as a section of the
// Cross-venue page ("Paper scanner: executable edge").
//
// Feeds off public/data/arb_scan.json, which the scanner in the
// prediction-alpha-bot repo writes (schema arb_scan/2, a superset of
// arb_scan/1), served as /api/research/arb-scan. Every figure here comes
// from that file; this module lays it out and derives nothing beyond counts,
// shares and ages. The file is produced elsewhere, so every field may be
// missing or null: a missing figure renders as a dash, never as a zero, and
// a missing list renders as a sentence that says so.
//
// Since 2026-09-05 the file carries the scanner's taxonomy (docs/specs/
// arb_taxonomie_2026-09-05.md): every candidate has a class, a capital-lock
// horizon, an automated rule screen and a person's rule review, and the
// file says in `vocabulary` what each of those words means. This module
// shows the words from the file and types none of its own; a payload from
// before the taxonomy (no `vocabulary`) falls back to the first schema's
// single candidate list.
//
// Reading order follows the review's pattern for the study pages: title,
// one computed verdict sentence, the stamps, then the funnel (strategies,
// rejection reasons), the chances, the carry candidates, the rejections with
// their gate, the cross-venue pair board with both rulebooks, the paper book,
// and last the paragraph that says what the numbers do and do not mean.
//
// The paper book also reads public/data/arb_resolutions.json, our own
// resolution pass over the scanner's journal (app/arb_resolution.py,
// scripts/resolve_arb_paper.py). Where the scanner still says open, the
// pass supplies status, settlement and figure; a row the scanner resolved
// itself keeps the scanner's own figure, or, since 2026-09-05, its own
// reason for having none (resolution_reason, e.g. filled_after_close).

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
  note: 'Price gaps between Polymarket and Kalshi and inside one venue, screened for structure, depth, fees and horizon, then paper-traded. Only a basket whose payout is fixed by contract is called arbitrage; a clean basket that locks capital past the short window is carry; a cross-venue pair counts as hedged only after a person has read both rulebooks.'
};

const STRICH = '—';
const ZELLE = M + '; font-size:var(--t-small); white-space:nowrap';
const KOPF = 'padding:var(--sp-4) var(--sp-5); border-bottom:1px solid var(--line-2); background:var(--panel); position:sticky; top:0; z-index:3; ' + LABEL;
const ABSCHNITT = M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:var(--info); margin:var(--sp-6) 0 var(--sp-4)';

// Rule-match states as the first schema writes them. Anything else is shown
// as written, in the muted tone, so an unexpected value is visible rather
// than silently folded into one of the three.
const RULE_MATCH = {
  unverified: { text: 'UNVERIFIED', farbe: 'var(--ink-3)', rahmen: 'var(--line-1)' },
  reviewed: { text: 'REVIEWED', farbe: 'var(--pos)', rahmen: 'color-mix(in srgb, var(--pos) 40%, transparent)' },
  mismatch: { text: 'MISMATCH', farbe: 'var(--neg)', rahmen: 'color-mix(in srgb, var(--neg) 40%, transparent)' }
};

// The horizon as a chip. The words are the scanner's (capital_lock_class);
// the colours say which of them may be called arbitrage.
const HORIZONT = {
  short: { text: 'ARB · SHORT', farbe: 'var(--pos)', rahmen: 'color-mix(in srgb, var(--pos) 40%, transparent)' },
  medium: { text: 'CARRY · MEDIUM', farbe: 'var(--warn)', rahmen: 'color-mix(in srgb, var(--warn) 45%, transparent)' },
  long: { text: 'CARRY · LONG', farbe: 'var(--warn)', rahmen: 'color-mix(in srgb, var(--warn) 45%, transparent)' },
  unknown: { text: 'UNDATED', farbe: 'var(--ink-4)', rahmen: 'var(--line-1)' }
};

const SCREEN = {
  structural: { text: 'STRUCTURAL', farbe: 'var(--pos)', rahmen: 'color-mix(in srgb, var(--pos) 40%, transparent)' },
  passed: { text: 'SCREEN PASSED', farbe: 'var(--ink-3)', rahmen: 'var(--line-1)' }
};

const REVIEW = {
  equivalent: { text: 'REVIEW · EQUIVALENT', farbe: 'var(--pos)', rahmen: 'color-mix(in srgb, var(--pos) 40%, transparent)' },
  not_equivalent: { text: 'REVIEW · NOT EQUIVALENT', farbe: 'var(--neg)', rahmen: 'color-mix(in srgb, var(--neg) 40%, transparent)' },
  pending: { text: 'REVIEW · PENDING', farbe: 'var(--warn)', rahmen: 'color-mix(in srgb, var(--warn) 45%, transparent)' },
  none: { text: 'NO REVIEW', farbe: 'var(--ink-4)', rahmen: 'var(--line-1)' }
};

// Statuses that put a candidate in the upper table of the first schema's
// list. Everything else (rejected, candidate, expired, anything unknown)
// goes below, folded, with its reason.
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
function cent(v) { const n = zahl(v); return n == null ? STRICH : (n > 0 ? '+' : '') + n.toFixed(2) + '¢'; }

function minutenSeit(iso, jetztMs) {
  if (!iso) return null;
  const t = new Date(iso);
  if (isNaN(t)) return null;
  return Math.max(0, (jetztMs - t.getTime()) / 60000);
}

function shaKurz(sha) { const s = text(sha).trim(); return s.length > 7 ? s.slice(0, 7) : s; }

function datum(iso) {
  const s = text(iso).trim();
  if (!s) return STRICH;
  const t = new Date(s);
  return isNaN(t) ? s : t.toISOString().slice(0, 10);
}

// ---- vocabulary -------------------------------------------------------------

/** The words the file carries, as lookups. Unknown ids come back as written,
 *  so a word the scanner added after this page was built is still visible.
 *  `bekannt` says whether the payload is of the taxonomy schema at all. */
export function vokabular(payload) {
  const v = objekt(objekt(payload).vocabulary);
  const bekannt = Array.isArray(v.classes) && v.classes.length > 0;
  const karte = (rows, key) => {
    const out = {};
    liste(rows).forEach((r) => { const id = text(r[key || 'id']).trim(); if (id) out[id] = r; });
    return out;
  };
  const klassen = karte(v.classes);
  const horizonte = karte(v.capital_lock);
  const screens = karte(v.rule_screen);
  const reviews = karte(v.rule_review);
  const gruende = karte(v.rejection_reasons);
  const gates = karte(v.gates, 'gate');
  const strategien = karte(v.strategies);
  const label = (map, id, fallback) => {
    const key = text(id).trim();
    if (!key) return fallback == null ? STRICH : fallback;
    const row = map[key];
    return row && text(row.label).trim() ? text(row.label).trim() : key;
  };
  return {
    bekannt,
    klasse: (id) => label(klassen, id),
    klasseEintrag: (id) => klassen[text(id).trim()] || null,
    klassen: liste(v.classes),
    horizont: (id) => label(horizonte, id),
    screen: (id) => label(screens, id),
    review: (id) => label(reviews, id),
    grund: (id) => label(gruende, id),
    gateVon: (id) => { const row = gruende[text(id).trim()]; return row && zahl(row.gate) != null ? zahl(row.gate) : null; },
    gate: (n) => { const row = gates[String(n)]; return row && text(row.label).trim() ? text(row.label).trim() : (n == null ? '' : 'gate ' + n); },
    strategie: (id) => label(strategien, id),
    strategieKlasse: (id) => { const row = strategien[text(id).trim()]; return row ? text(row.class).trim() : ''; }
  };
}

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
    cycles: zahl(h.cycles_24h), errors: zahl(h.errors_24h),
    konfiguriertMs: zahl(h.configured_interval_ms), effektivMs: intervallMs
  };
}

/** The one-sentence finding under the title. Renders only when the summary
 *  carries both counts it is built from; the resolved count joins when it is
 *  there, the carry candidates when the file is of the taxonomy schema. */
export function verdiktSatz(summary) {
  const s = objekt(summary);
  const raw = zahl(s.raw_candidates_24h);
  const val = zahl(s.validated_24h);
  if (raw == null || val == null) return '';
  const res = zahl(s.resolved_paper_trades);
  const cand = zahl(s.candidates_24h);
  let satz = num(Math.round(val)) + ' validated of ' + num(Math.round(raw)) + ' raw candidate' + (Math.round(raw) === 1 ? '' : 's') + ' in 24 h';
  if (cand != null) satz += ', ' + num(Math.round(cand)) + ' carry candidate' + (Math.round(cand) === 1 ? '' : 's') + ' above the hurdle';
  if (res != null) satz += ', ' + num(Math.round(res)) + ' paper trade' + (Math.round(res) === 1 ? '' : 's') + ' resolved';
  return satz + '.';
}

/** Candidates split into the upper table (validated, paper) and the folded
 *  lower one (rejected, expired, unknown status), each sorted by executable
 *  net edge, largest first, unknown edges last. First-schema reading. */
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

function chip(textInhalt, farbe, rahmen, titel) {
  return '<span' + (titel ? ' title="' + esc(titel) + '"' : '') + ' style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps); color:' + farbe
    + '; border:1px solid ' + rahmen + '; border-radius:var(--r-control); padding:var(--sp-1) var(--sp-3); white-space:nowrap">' + esc(textInhalt) + '</span>';
}

function ruleChip(wert) {
  const key = text(wert).trim().toLowerCase();
  const r = RULE_MATCH[key || 'unverified'];
  if (r) return chip(r.text, r.farbe, r.rahmen);
  return chip(key.toUpperCase(), 'var(--muted)', 'var(--line-1)');
}

function horizontChip(wert, vok) {
  const key = text(wert).trim().toLowerCase();
  if (!key) return '';
  const h = HORIZONT[key];
  const titel = vok ? vok.horizont(key) : '';
  if (h) return chip(h.text, h.farbe, h.rahmen, titel);
  return chip(key.toUpperCase(), 'var(--muted)', 'var(--line-1)', titel);
}

function screenChip(wert, vok) {
  const key = text(wert).trim().toLowerCase();
  if (!key) return '';
  const titel = vok ? vok.screen(key) : '';
  const s = SCREEN[key];
  if (s) return chip(s.text, s.farbe, s.rahmen, titel);
  return chip('SCREEN · ' + key.replace(/_/g, ' ').toUpperCase(), 'var(--neg)', 'color-mix(in srgb, var(--neg) 40%, transparent)', titel);
}

function reviewChip(wert, vok) {
  const key = text(wert).trim().toLowerCase();
  if (!key) return '';
  const titel = vok ? vok.review(key) : '';
  const r = REVIEW[key];
  if (r) return chip(r.text, r.farbe, r.rahmen, titel);
  return chip('REVIEW · ' + key.toUpperCase(), 'var(--muted)', 'var(--line-1)', titel);
}

function gateChip(n, vok) {
  const g = zahl(n);
  if (g == null) return '';
  return chip('GATE ' + Math.round(g) + ' · ' + (vok ? vok.gate(Math.round(g)) : '').toUpperCase(), 'var(--ink-3)', 'var(--line-1)');
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
  if (stand.konfiguriertMs != null && stand.effektivMs != null && stand.konfiguriertMs !== stand.effektivMs) {
    teile.push('cadence ' + (stand.effektivMs / 1000).toFixed(0) + ' s kept against ' + (stand.konfiguriertMs / 1000).toFixed(0) + ' s configured');
  }
  teile.push((stand.cycles == null ? STRICH : num(Math.round(stand.cycles))) + ' cycles / 24 h');
  teile.push('<span style="color:' + (stand.errors ? 'var(--warn)' : 'inherit') + '">' + (stand.errors == null ? STRICH : num(Math.round(stand.errors))) + ' error' + (stand.errors === 1 ? '' : 's') + ' / 24 h</span>');
  return '<div style="display:flex; gap:var(--sp-5); flex-wrap:wrap; align-items:center; margin-top:var(--sp-4); padding:var(--sp-3) var(--sp-4); '
    + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps); color:' + (stand.warnung ? 'var(--warn)' : 'var(--ink-2)')
    + '; border-left:2px solid ' + farbe + '; background:var(--panel)">'
    + teile.map((t) => '<span>' + t + '</span>').join('<span style="color:var(--ink-4)">·</span>')
    + '</div>';
}

// The thresholds the numbers were judged against, as the file states them.
export function konfigZeile(config) {
  const c = objekt(config);
  if (!Object.keys(c).length) return '';
  const teile = [];
  if (zahl(c.hurdle_pct) != null) teile.push('hurdle ' + zahl(c.hurdle_pct).toFixed(1) + '% a year');
  if (zahl(c.target_size_usd) != null) teile.push('target size ' + usd(c.target_size_usd));
  if (zahl(c.min_executable_depth_usd) != null) teile.push('min executable capital ' + usd(c.min_executable_depth_usd));
  if (zahl(c.short_max_hours) != null) teile.push('short window ' + num(Math.round(zahl(c.short_max_hours))) + ' h');
  if (zahl(c.medium_max_days) != null) teile.push('medium up to ' + num(Math.round(zahl(c.medium_max_days))) + ' d');
  if (text(c.execution_role_mode).trim()) teile.push('legs priced as ' + esc(text(c.execution_role_mode).trim()));
  if (text(c.fee_model_version).trim()) teile.push('fee schedule ' + esc(text(c.fee_model_version).trim()));
  if (!teile.length) return '';
  return '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps); color:var(--ink-3); margin-top:var(--sp-3)">JUDGED AGAINST · ' + teile.join(' · ') + '</div>';
}

export function kennzahlen(summary) {
  const s = objekt(summary);
  const pnl = zahl(s.resolved_paper_pnl_usd);
  const note = text(s.sample_note).trim();
  const taxonomie = zahl(s.candidates_24h) != null || zahl(s.near_miss_24h) != null;
  const tiles = [
    { label: 'RAW CANDIDATES 24H', wert: ganz(s.raw_candidates_24h), sub: 'gross edge at the quote or the book' }
  ];
  if (taxonomie) tiles.push({ label: 'NEAR MISSES 24H', wert: ganz(s.near_miss_24h), sub: 'watch band, no edge at either' });
  tiles.push({ label: 'VALIDATED 24H', wert: ganz(s.validated_24h), sub: 'structure, depth, fees, hurdle, short lock' });
  if (taxonomie) tiles.push({ label: 'CARRY CANDIDATES 24H', wert: ganz(s.candidates_24h), sub: 'clean and above the hurdle, not fireable' });
  tiles.push(
    { label: 'PAPER FIRED 24H', wert: ganz(s.paper_fired_24h), sub: 'paper book only' },
    { label: 'OPEN PAPER POSITIONS', wert: ganz(s.open_paper_positions), sub: 'awaiting resolution' },
    { label: 'RESOLVED PAPER TRADES', wert: ganz(s.resolved_paper_trades), sub: 'n for the figure to the right' },
    { label: 'RESOLVED PAPER PNL', wert: vorzeichenUsd(pnl), ton: pnl == null ? null : (pnl >= 0 ? 'up' : 'down'), sub: note || 'paper result, not realized' }
  );
  return '<div style="display:grid; grid-template-columns:repeat(' + (taxonomie ? 4 : 6) + ', minmax(0, 1fr)); gap:var(--sp-4); margin-top:var(--sp-5)">'
    + tiles.map((t) => kpi({ label: esc(t.label), wert: esc(t.wert), sub: esc(t.sub), ton: t.ton || null, kuerzen: t.label !== 'RESOLVED PAPER PNL' })).join('')
    + '</div>';
}

// Funnel per strategy: raw, near misses, validated, carry candidates, paper,
// and the reason that rejected most. The share is validated over raw, only
// where raw is a number above 0.
export function trichter(strategies, vok) {
  const rows = liste(strategies);
  const v = vok || vokabular(null);
  const SPALTEN = v.bekannt ? 'minmax(220px, 1.4fr) 84px 84px 96px 84px 72px minmax(200px, 1fr)' : 'minmax(220px, 1.4fr) 96px 120px 96px minmax(180px, 1fr)';
  const kopf = '<div style="display:grid; grid-template-columns:' + SPALTEN + '; gap:var(--sp-4); ' + KOPF + '">'
    + '<div>STRATEGY</div><div style="text-align:right">RAW 24H</div>'
    + (v.bekannt ? '<div style="text-align:right">NEAR MISS</div>' : '')
    + '<div style="text-align:right">VALIDATED</div>'
    + (v.bekannt ? '<div style="text-align:right">CARRY</div>' : '')
    + '<div style="text-align:right">PAPER</div><div>TOP REJECTION</div></div>';
  const koerper = rows.length ? rows.map((r) => {
    const raw = zahl(r.raw_24h), val = zahl(r.validated_24h);
    const anteil = raw != null && raw > 0 && val != null ? ' <span style="color:var(--ink-4)">' + (100 * val / raw).toFixed(val / raw < 0.1 ? 1 : 0) + '%</span>' : '';
    const klasse = text(r.class).trim() || v.strategieKlasse(r.id);
    const grund = text(r.top_rejection).trim();
    return '<div style="display:grid; grid-template-columns:' + SPALTEN + '; gap:var(--sp-4); align-items:baseline; padding:var(--sp-4) var(--sp-5); border-bottom:1px solid var(--line-3)">'
      + '<div><div style="font-size:var(--t-body); color:var(--ink-1)">' + esc(text(r.label).trim() || text(r.id).trim() || STRICH) + '</div>'
      + '<div style="' + NOTIZ + '; margin-top:var(--sp-1)">' + esc(text(r.id).trim()) + (klasse ? ' · ' + esc(v.klasse(klasse)) : '') + '</div></div>'
      + '<div style="text-align:right; ' + ZELLE + '; color:var(--text)">' + ganz(raw) + '</div>'
      + (v.bekannt ? '<div style="text-align:right; ' + ZELLE + '; color:var(--ink-3)">' + ganz(r.near_miss_24h) + '</div>' : '')
      + '<div style="text-align:right; ' + ZELLE + '; color:var(--text)">' + ganz(val) + anteil + '</div>'
      + (v.bekannt ? '<div style="text-align:right; ' + ZELLE + '; color:var(--warn)">' + ganz(r.candidates_24h) + '</div>' : '')
      + '<div style="text-align:right; ' + ZELLE + '; color:var(--text)">' + ganz(r.paper_24h) + '</div>'
      + '<div style="' + ZELLE + '; color:var(--ink-3); white-space:normal">' + (grund ? esc(v.bekannt ? v.grund(grund) : grund) + (v.bekannt && v.gateVon(grund) != null ? ' <span style="color:var(--ink-4)">(gate ' + v.gateVon(grund) + ')</span>' : '') : STRICH) + '</div>'
      + '</div>';
  }).join('') : leerSatz('No strategies in the payload.');
  return '<div style="' + ABSCHNITT + '">FUNNEL BY STRATEGY · LAST 24 H</div>'
    + '<div style="' + KARTE + '">' + kopf + koerper + '</div>'
    + (v.bekannt ? '<div style="' + NOTIZ + '; margin-top:var(--sp-3)">RAW is a candidate with a gross edge at the quote or at the book; NEAR MISS is the watch band above one dollar that showed no edge at either and is counted, not journaled. CARRY is clean and above the hurdle but locks capital past the short window.</div>' : '');
}

// Rejection reasons as horizontal bars, longest first. Width is the count
// against the largest count, so the bars compare reasons with each other.
// With the taxonomy schema each bar names its gate and reads in plain words.
export function ablehnungen(rejections, vok) {
  const v = vok || vokabular(null);
  const rows = liste(rejections).map((r) => ({
    reason: text(r.reason).trim(), count: zahl(r.count),
    label: text(r.label).trim() || (v.bekannt ? v.grund(r.reason) : ''),
    gate: zahl(r.gate) != null ? zahl(r.gate) : v.gateVon(r.reason)
  })).filter((r) => r.reason || r.count != null);
  rows.sort((a, b) => (b.count == null ? -1 : b.count) - (a.count == null ? -1 : a.count));
  const max = rows.reduce((m, r) => Math.max(m, r.count == null ? 0 : r.count), 0);
  const summe = rows.reduce((m, r) => m + (r.count == null ? 0 : r.count), 0);
  const balken = rows.length ? rows.map((r) => {
    const breite = max > 0 && r.count != null ? Math.max(0, Math.min(100, (100 * r.count) / max)) : 0;
    return '<div style="display:grid; grid-template-columns:minmax(220px, 320px) 1fr 72px; gap:var(--sp-4); align-items:center; padding:var(--sp-3) var(--sp-5)">'
      + '<div style="min-width:0"><div style="' + ZELLE + '; color:var(--ink-2); overflow:hidden; text-overflow:ellipsis" title="' + esc(r.reason) + '">' + esc(r.label || r.reason || STRICH) + '</div>'
      + (r.label ? '<div style="' + NOTIZ + '; white-space:nowrap; overflow:hidden; text-overflow:ellipsis">' + esc(r.reason) + (r.gate != null ? ' · gate ' + r.gate + ' ' + esc(v.gate(r.gate)) : '') + '</div>' : '') + '</div>'
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

// ---- first-schema candidate list ---------------------------------------------

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

// ---- taxonomy-schema tables ---------------------------------------------------

const KLASSE_SPALTEN = 'minmax(220px, 1fr) 96px 200px 64px 72px 64px 66px 68px 50px 78px 70px';

function klasseKopf() {
  return '<div style="display:grid; grid-template-columns:' + KLASSE_SPALTEN + '; gap:var(--sp-3); ' + KOPF + '">'
    + '<div>CANDIDATE · CLASS · VENUES</div><div>HORIZON</div><div>RULES</div>'
    + '<div style="text-align:right">GROSS</div><div style="text-align:right">NET EXEC.</div><div style="text-align:right">NET $</div>'
    + '<div style="text-align:right">DEPTH</div><div style="text-align:right">CAPITAL</div>'
    + '<div style="text-align:right">DAYS</div><div style="text-align:right">ANN. · HURDLE</div><div style="text-align:right">OPEN SINCE</div></div>';
}

function terminZeile(o) {
  const r = objekt(o.resolution_at_by_venue);
  const teile = [];
  if (text(r.kalshi).trim()) teile.push('Kalshi settles ' + datum(r.kalshi));
  if (text(r.polymarket).trim()) teile.push('Polymarket settles ' + datum(r.polymarket));
  return teile.join(' · ');
}

function klasseZeile(o, i, vok, jetztMs, abgelehnt) {
  const id = text(o.id).trim() || 'row-' + i;
  const netto = zahl(o.executable_net_edge_bps);
  const nettoFarbe = netto == null ? 'var(--ink-4)' : netto > 0 ? 'var(--pos)' : 'var(--neg-soft)';
  const offen = offenSeit(o, jetztMs);
  const venues = venuesVon(o);
  const klasse = text(o.class).trim() || vok.strategieKlasse(o.strategy);
  const grund = text(o.rejection_reason).trim();
  const status = text(o.status).trim();
  const hurdle = o.hurdle_met === true ? true : (o.hurdle_met === false ? false : null);
  const annFarbe = hurdle === true ? 'var(--pos)' : hurdle === false ? 'var(--neg-soft)' : 'var(--text)';
  const unterzeile = [esc(klasse ? vok.klasse(klasse) : text(o.strategy).trim() || STRICH), esc(text(o.strategy).trim()), venues.length ? esc(venues.join(' ↔ ')) : 'venues ' + STRICH]
    .concat(abgelehnt ? ['<span style="color:var(--warn)">' + esc(grund ? vok.grund(grund) : status || 'rejected') + '</span>'] : []);
  const termine = terminZeile(o);
  return '<details data-key="arb:opp:' + esc(id) + '" style="border-bottom:1px solid var(--line-3)">'
    + '<summary style="display:grid; grid-template-columns:' + KLASSE_SPALTEN + '; gap:var(--sp-3); align-items:center; padding:var(--sp-4) var(--sp-5); cursor:pointer; list-style:none">'
    + '<div style="min-width:0"><div style="font-size:var(--t-body); color:var(--ink-1); line-height:var(--lh-snug)">' + esc(text(o.title).trim() || STRICH) + '</div>'
    + '<div style="' + NOTIZ + '; margin-top:var(--sp-1); white-space:nowrap; overflow:hidden; text-overflow:ellipsis">' + unterzeile.join(' · ') + '</div></div>'
    + '<div>' + horizontChip(o.capital_lock_class, vok) + '</div>'
    + '<div style="display:flex; gap:var(--sp-2); flex-wrap:wrap">' + screenChip(o.rule_screen, vok) + reviewChip(o.rule_review, vok) + (abgelehnt ? gateChip(o.gate_failed, vok) : '') + '</div>'
    + '<div style="text-align:right; ' + ZELLE + '; color:var(--text)">' + bps(o.gross_edge_bps) + '</div>'
    + '<div style="text-align:right; ' + ZELLE + '; color:' + nettoFarbe + '">' + bps(netto) + '</div>'
    + '<div style="text-align:right; ' + ZELLE + '; color:' + nettoFarbe + '">' + (zahl(o.net_profit_usd) == null ? STRICH : vorzeichenUsd(o.net_profit_usd)) + '</div>'
    + '<div style="text-align:right; ' + ZELLE + '; color:var(--text)">' + usd(o.depth_usd) + '</div>'
    + '<div style="text-align:right; ' + ZELLE + '; color:var(--text)">' + usd(o.capital_usd) + '</div>'
    + '<div style="text-align:right; ' + ZELLE + '; color:var(--text)">' + tage(o.days_to_resolution) + '</div>'
    + '<div style="text-align:right; ' + ZELLE + '; color:' + annFarbe + '"' + (hurdle == null ? '' : ' title="' + (hurdle ? 'above' : 'below') + ' the hurdle rate"') + '>' + prozent(o.annualized_pct) + (hurdle == null ? '' : hurdle ? ' ✓' : ' ✗') + '</div>'
    + '<div style="text-align:right; ' + ZELLE + '; color:' + (offen.lang ? 'var(--warn)' : 'var(--text)') + '"' + (offen.lang ? ' title="open for over an hour: capital waiting for resolution, not a closing price error"' : '') + '>' + esc(offen.text) + '</div>'
    + '</summary>'
    + '<div style="padding:0 var(--sp-5) var(--sp-5) var(--sp-5)">'
    + '<div style="' + LABEL + '; margin-bottom:var(--sp-3)">LEGS</div>'
    + legsHtml(o.legs)
    + '<div style="' + NOTIZ + '; margin-top:var(--sp-4)">'
    + 'id ' + esc(id)
    + (text(o.market_ref).trim() ? ' · ref ' + esc(text(o.market_ref).trim()) : '')
    + (termine ? ' · ' + esc(termine) : '')
    + (o.first_seen_at ? ' · first seen ' + esc(stempel(o.first_seen_at)) : '')
    + (o.last_seen_at ? ' · last seen ' + esc(stempel(o.last_seen_at)) : '')
    + (status ? ' · status ' + esc(status) : '')
    + (grund ? ' · rejection ' + esc(grund) + (zahl(o.gate_failed) != null ? ' at gate ' + zahl(o.gate_failed) + ' (' + esc(vok.gate(zahl(o.gate_failed))) + ')' : '') : '')
    + (text(o.rule_screen).trim() ? ' · screen ' + esc(vok.screen(o.rule_screen)) : '')
    + (text(o.rule_review).trim() ? ' · review ' + esc(vok.review(o.rule_review)) : '')
    + '</div></div></details>';
}

// The chances: rows that clear every gate and lock capital inside the short
// window. Only these may stand under a heading with the word edge.
export function chancenTafel(chances, vok, jetztMs) {
  const rows = liste(chances);
  return '<div style="' + ABSCHNITT + '">CHANCES · ' + (rows.length ? num(rows.length) + ' PASSED EVERY GATE' : 'NONE') + '</div>'
    + '<div style="' + KARTE + '">' + klasseKopf()
    + (rows.length ? rows.map((o, i) => klasseZeile(o, i, vok, jetztMs, false)).join('') : leerSatz('No candidate passed structure, executability, economics and the hurdle in the last 24 h.'))
    + '</div>'
    + '<div style="' + NOTIZ + '; margin-top:var(--sp-3)">Each row opens to its legs. NET EXEC. is the gap after both legs\' fees at the size the books showed; NET $ that gap in dollars at the same size, which is what the ranking uses. ANN. spreads the net edge over the days until settlement and is compared with the hurdle rate above.</div>';
}

// Carry candidates: clean, executable, net positive and above the hurdle,
// but locked past the short window, or a cross-venue pair whose rulebooks
// nobody has confirmed as equivalent. Never fired, never called arbitrage.
export function carryTafel(candidates, vok, config, jetztMs) {
  const rows = liste(candidates);
  const hurdle = zahl(objekt(config).hurdle_pct);
  return '<div style="' + ABSCHNITT + '; color:var(--warn)">CARRY CANDIDATES · ' + (rows.length ? num(rows.length) : 'NONE') + ' · CARRY, NOT ARBITRAGE</div>'
    + '<div style="' + KARTE + '">' + klasseKopf()
    + (rows.length ? rows.map((o, i) => klasseZeile(o, i, vok, jetztMs, false)).join('') : leerSatz('No carry candidate in the last 24 h: nothing clean, net positive and above the hurdle was locked past the short window.'))
    + '</div>'
    + '<div style="' + NOTIZ + '; margin-top:var(--sp-3)">These baskets clear structure, depth, fees' + (hurdle != null ? ' and the hurdle of ' + hurdle.toFixed(1) + '% a year' : ' and the hurdle') + ', but their payout is months away, or their two rulebooks are not yet confirmed as equivalent. The scanner journals them and does not paper-fire them; the annualised column is the price of the locked capital, and the venues charge for it.</div>';
}

// Rejections grouped by reason, each with its gate and a few example rows.
// A row that failed gate 1 carries no return figures: its payout was never a
// basket, so a number on it would be a number about nothing.
export function abgelehnteTafel(rejectedExamples, vok, jetztMs) {
  const gruppen = liste(rejectedExamples).filter((g) => text(g.reason).trim());
  if (!gruppen.length) return '';
  const summe = gruppen.reduce((m, g) => m + (zahl(g.count_24h) || 0), 0);
  return '<details data-key="arb:rejected" style="' + KARTE + '; margin-top:var(--sp-6)">'
    + '<summary style="cursor:pointer; padding:var(--sp-4) var(--sp-5); list-style:none; ' + LABEL + '">REJECTED · ' + num(summe) + ' IN 24 H · ' + gruppen.length + ' REASON' + (gruppen.length === 1 ? '' : 'S') + ' WITH EXAMPLES ▸</summary>'
    + gruppen.map((g) => {
      const beispiele = liste(g.examples);
      return '<div style="border-top:1px solid var(--line-2)">'
        + '<div style="display:flex; gap:var(--sp-4); align-items:baseline; flex-wrap:wrap; padding:var(--sp-4) var(--sp-5)">'
        + '<div style="font-size:var(--t-body); color:var(--ink-1)">' + esc(text(g.label).trim() || vok.grund(g.reason)) + '</div>'
        + '<div style="' + NOTIZ + '">' + esc(text(g.reason).trim()) + ' · ' + num(Math.round(zahl(g.count_24h) || 0)) + ' in 24 h</div>'
        + gateChip(g.gate, vok)
        + '</div>'
        + (beispiele.length ? klasseKopf() + beispiele.map((o, i) => klasseZeile(o, i, vok, jetztMs, true)).join('') : '')
        + '</div>';
    }).join('')
    + '</details>';
}

// The cross-venue pair board: stages 1 to 3 of the pair protocol, visible.
export function paarTafel(pairs, vok) {
  const rows = liste(pairs);
  const SPALTEN = 'minmax(240px, 1.3fr) 150px 170px 150px 76px 66px 80px';
  const kopf = '<div style="display:grid; grid-template-columns:' + SPALTEN + '; gap:var(--sp-3); ' + KOPF + '">'
    + '<div>PAIR · KALSHI ↔ POLYMARKET</div><div>SCREEN</div><div>REVIEW</div><div>SETTLES</div>'
    + '<div style="text-align:right">LAST NET</div><div style="text-align:right">ANN.</div><div>HEDGED</div></div>';
  const koerper = rows.length ? rows.map((p, i) => {
    const id = text(p.pair_id).trim() || 'pair-' + i;
    const ks = objekt(p.kalshi), pm = objekt(p.polymarket), last = objekt(p.last), review = objekt(p.review);
    const gap = zahl(p.resolution_gap_days);
    const hedged = p.hedged === true;
    const checklist = objekt(review.checklist);
    const punkte = Object.keys(checklist).sort((a, b) => Number(a) - Number(b)).map((k) => {
      const w = checklist[k];
      const zeichen = w === true ? '✓' : w === false ? '✗' : '·';
      return '<span style="margin-right:var(--sp-3)">' + esc(k) + ' ' + zeichen + (typeof w === 'string' ? ' ' + esc(w) : '') + '</span>';
    }).join('');
    return '<details data-key="arb:pair:' + esc(id) + '" style="border-bottom:1px solid var(--line-3)">'
      + '<summary style="display:grid; grid-template-columns:' + SPALTEN + '; gap:var(--sp-3); align-items:center; padding:var(--sp-4) var(--sp-5); cursor:pointer; list-style:none">'
      + '<div style="min-width:0"><div style="font-size:var(--t-body); color:var(--ink-1); line-height:var(--lh-snug)">' + esc(text(p.title).trim() || STRICH) + '</div>'
      + '<div style="' + NOTIZ + '; margin-top:var(--sp-1); white-space:nowrap; overflow:hidden; text-overflow:ellipsis">' + esc(text(ks.ticker).trim() || STRICH) + ' ↔ ' + esc(text(pm.slug).trim() || STRICH) + ' · ' + esc(text(p.source).trim() || STRICH) + '</div></div>'
      + '<div>' + screenChip(p.rule_screen, vok) + '</div>'
      + '<div>' + reviewChip(p.rule_review || 'none', vok) + (text(review.date).trim() ? '<div style="' + NOTIZ + '; margin-top:var(--sp-1)">' + esc(review.date) + '</div>' : '') + '</div>'
      + '<div style="' + ZELLE + '; color:var(--ink-2); white-space:normal; line-height:var(--lh-snug)">K ' + esc(datum(ks.resolution_at)) + '<br>P ' + esc(datum(pm.resolution_at)) + (gap != null ? '<div style="' + NOTIZ + '; color:' + (gap > 7 ? 'var(--warn)' : 'var(--ink-4)') + '">' + gap.toFixed(gap < 10 ? 1 : 0) + ' d apart</div>' : '') + '</div>'
      + '<div style="text-align:right; ' + ZELLE + '; color:' + (zahl(last.net_cents) == null ? 'var(--ink-4)' : zahl(last.net_cents) > 0 ? 'var(--pos)' : 'var(--neg-soft)') + '">' + cent(last.net_cents) + '</div>'
      + '<div style="text-align:right; ' + ZELLE + '; color:var(--text)">' + prozent(last.annualized_pct) + '</div>'
      + '<div>' + (hedged ? chip('HEDGED', 'var(--pos)', 'color-mix(in srgb, var(--pos) 40%, transparent)') : chip('TWO OPEN BETS', 'var(--ink-4)', 'var(--line-1)', 'not hedged until a person found both rulebooks equivalent')) + '</div>'
      + '</summary>'
      + '<div style="padding:0 var(--sp-5) var(--sp-5) var(--sp-5)">'
      + (text(p.rule_screen_detail).trim() ? '<div style="' + NOTIZ + '; margin-bottom:var(--sp-3)">screen: ' + esc(p.rule_screen_detail) + '</div>' : '')
      + '<div style="display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:var(--sp-5)">'
      + '<div><div style="' + LABEL + '; margin-bottom:var(--sp-2)">KALSHI · ' + esc(text(ks.ticker).trim()) + '</div><div style="font-size:var(--t-small); color:var(--ink-2); line-height:var(--lh-prose)">' + (text(ks.title).trim() ? '<b style="font-weight:600">' + esc(ks.title) + '</b><br>' : '') + esc(text(ks.rules_excerpt).trim() || 'no rule text in the payload') + '</div></div>'
      + '<div><div style="' + LABEL + '; margin-bottom:var(--sp-2)">POLYMARKET · ' + esc(text(pm.slug).trim()) + '</div><div style="font-size:var(--t-small); color:var(--ink-2); line-height:var(--lh-prose)">' + (text(pm.question).trim() ? '<b style="font-weight:600">' + esc(pm.question) + '</b><br>' : '') + esc(text(pm.rules_excerpt).trim() || 'no rule text in the payload') + '</div></div>'
      + '</div>'
      + (Object.keys(review).length
        ? '<div style="margin-top:var(--sp-4); font-size:var(--t-small); color:var(--ink-2); line-height:var(--lh-prose)">'
          + '<span style="' + LABEL + '">REVIEW</span> ' + esc(vok.review(review.verdict || p.rule_review)) + (text(review.reviewer).trim() ? ' · ' + esc(review.reviewer) : '') + (text(review.date).trim() ? ' · ' + esc(review.date) : '')
          + (punkte ? '<div style="' + NOTIZ + '; margin-top:var(--sp-2)">checklist: ' + punkte + '</div>' : '')
          + (text(review.note).trim() ? '<div style="margin-top:var(--sp-2)">' + esc(review.note) + '</div>' : '')
          + (text(review.source).trim() ? '<div style="' + NOTIZ + '; margin-top:var(--sp-2)">source: ' + esc(review.source) + '</div>' : '')
          + '</div>'
        : '<div style="' + NOTIZ + '; margin-top:var(--sp-4)">No review on file: nobody has read both rulebooks for this pair.</div>')
      + '<div style="' + NOTIZ + '; margin-top:var(--sp-3)">pair ' + esc(id) + (p.first_seen_at ? ' · first seen ' + esc(stempel(p.first_seen_at)) : '') + (p.last_seen_at ? ' · last seen ' + esc(stempel(p.last_seen_at)) : '') + (text(last.status).trim() ? ' · last status ' + esc(last.status) : '') + '</div>'
      + '</div></details>';
  }).join('') : leerSatz('No cross-venue pair in the payload.');
  return '<div style="' + ABSCHNITT + '">CROSS-VENUE PAIR BOARD · ' + (rows.length ? num(rows.length) + ' PAIR' + (rows.length === 1 ? '' : 'S') : 'EMPTY') + '</div>'
    + '<div style="' + KARTE + '">' + kopf + koerper + '</div>'
    + '<div style="' + NOTIZ + '; margin-top:var(--sp-3)">SCREEN is the automated read of both titles and both settlement dates; REVIEW is what a person decided after reading both rulebooks, with the seven-point checklist. HEDGED appears only after an equivalent review; until then a basket across the pair is two open bets, whatever the net column says. Each row opens to both rule texts side by side.</div>';
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
// and say where the figures come from. Until 2026-09-05 the scanner's own
// lookup asked Gamma without closed=true and never found a settled market;
// since prediction-alpha-bot#4 it asks for closed markets, and this pass
// stays as the independent check on the same journal.
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
    + esc(auf.source ? auf.source + '. ' : '') + 'An independent pass over the same journal: the scanner\'s own lookup asked Gamma without closed=true until 2026-09-05 and found no settlement, and since then the two should agree; where they differ, the difference is the finding. '
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
    // scanner still says 'open', the pass supplies status, date and figure.
    // A row the scanner has resolved itself keeps the scanner's own status
    // and figure, or its own reason where it has no figure (a fill after
    // the market's close, an entry at zero).
    const eigen = text(p.status).trim().toLowerCase();
    const r = auf && eigen !== 'resolved' ? auf.map.get(text(p.trade_id).trim()) || null : null;
    const gel = !!(r && text(r.status).trim().toLowerCase() === 'resolved');
    const pnl = gel ? legPnl(r) : zahl(p.pnl_usd);
    const status = gel ? 'resolved' : eigen;
    const settle = gel ? zahl(r.settlement_price) : null;
    const tageGel = gel ? zahl(r.days_held) : null;
    const grund = gel && pnl == null
      ? text(r.pnl_corrected_reason || r.pnl_reason).trim()
      : (eigen === 'resolved' && pnl == null ? text(p.resolution_reason).trim() : '');
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

// The classes as the file defines them: what the basket is, what it pays,
// when that payout is fixed by contract, and what breaks it.
export function klassenTafel(vok) {
  const rows = vok && vok.bekannt ? vok.klassen : [];
  if (!rows.length) return '';
  return '<div style="' + ABSCHNITT + '">WHAT THE SCANNER CALLS ARBITRAGE, AND WHAT IT DOES NOT</div>'
    + '<div style="' + KARTE + '; padding:var(--sp-3) 0">'
    + rows.map((k) => '<div style="display:grid; grid-template-columns:minmax(200px, 260px) 1fr; gap:var(--sp-4); padding:var(--sp-3) var(--sp-5); border-bottom:1px solid var(--line-3)">'
      + '<div><div style="font-size:var(--t-body); color:var(--ink-1)">' + esc(text(k.label).trim() || text(k.id)) + '</div><div style="' + NOTIZ + '">' + esc(text(k.id)) + (k.scanned === false ? ' · defined, not scanned' : '') + '</div></div>'
      + '<div style="font-size:var(--t-small); color:var(--ink-2); line-height:var(--lh-prose)">'
      + '<b style="font-weight:600">Pays</b> ' + esc(text(k.payout).trim() || STRICH) + '. '
      + (text(k.structural_when).trim() ? '<b style="font-weight:600; color:var(--pos)">Fixed by contract when</b> ' + esc(k.structural_when) + '. ' : '<b style="font-weight:600; color:var(--warn)">Never fixed by contract.</b> ')
      + '<b style="font-weight:600">Breaks on</b> ' + esc(text(k.main_risk).trim() || STRICH) + '.'
      + '</div></div>').join('')
    + '</div>';
}

export function methodik() {
  const absatz = (t) => '<div style="font-size:var(--t-body); color:var(--ink-2); line-height:var(--lh-prose); max-width:720px; margin-top:var(--sp-3)">' + t + '</div>';
  return '<div style="' + ABSCHNITT + '">HOW TO READ THIS</div>'
    + '<div style="' + KARTE + '; padding:var(--sp-5) var(--sp-6)">'
    + absatz('<b style="color:var(--ink-1); font-weight:600">Five gates, in a fixed order.</b> Structure first: is the payout fixed by contract at all? Then executability against the books that would fill it, then the economics net of both fee curves at that size, then the horizon, and last flow control. A candidate is rejected for the most fundamental reason it fails, and a candidate that fails the first gate carries no return figures, because the payout those figures assume does not exist. The rejected list names the gate next to every reason.')
    + absatz('<b style="color:var(--ink-1); font-weight:600">Executable net edge</b> is the quoted gap after the fee schedule of both venues on both legs, taken at the size the books actually showed (DEPTH), not at the mid. A gap that only exists for the first dollar is not an edge; the scanner sizes each leg to the thinner book and charges the fee curve on that size. Nothing here accounts for the slippage of a real order or for a quote that vanishes between the scan and the click.')
    + absatz('<b style="color:var(--ink-1); font-weight:600">Rules: screen and review are two different things.</b> STRUCTURAL means one contract, so both legs settle on one rulebook by construction. SCREEN PASSED means the automated read of both titles and both settlement dates noticed nothing, which is not verification. Only a person who has read both rulebooks writes REVIEW EQUIVALENT or NOT EQUIVALENT, with the seven-point checklist on the pair board; until then a cross-venue basket is two open bets, whatever the numbers say.')
    + absatz('<b style="color:var(--ink-1); font-weight:600">A gap that stays open is not a mispricing waiting to close.</b> Both legs pay out at resolution, so capital is locked until then and the annualised column just spreads a small edge over that wait. The scanner compares it with a hurdle rate stated above; below the hurdle the gap is the price of the locked capital, above it the basket is a chance if the lock is short and a carry candidate if it is not. That is carry, not arbitrage.')
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
 *  the app passes nothing. resolutions is the parsed arb_resolutions.json in
 *  the same three states; it only ever adds to the paper book. */
export function renderArbScanAbschnitt(payload, jetztMs, resolutions) {
  const eyebrow = '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-max); color:var(--info)">PAPER SCANNER · EXECUTABLE EDGE</div>';
  const huelle = (inhalt) => '<div id="' + ARB_ANKER + '" style="padding:var(--sp-6); border-top:1px solid var(--line-2); scroll-margin-top:16px">' + eyebrow + inhalt + '</div>';
  const jetzt = typeof jetztMs === 'number' ? jetztMs : Date.now();
  const p = payload && typeof payload === 'object' && payload._quelle !== 'leer' && payload._quelle !== 'fehler' ? payload : null;
  if (!p) return huelle(leerzustand(payload));
  const study = ARB_STUDIE;
  const vok = vokabular(p);

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

  // The taxonomy schema splits the candidates by what they are; the first
  // schema had one list, and a file of that shape still renders as one.
  const tafeln = vok.bekannt
    ? chancenTafel(p.chances, vok, jetzt)
      + carryTafel(p.carry_candidates, vok, p.config, jetzt)
      + abgelehnteTafel(p.rejected_examples, vok, jetzt)
      + paarTafel(p.pairs, vok)
    : chancen(p.opportunities, jetzt);

  return huelle(''
    + '<div style="display:flex; align-items:flex-start; justify-content:space-between; gap:var(--sp-6); flex-wrap:wrap; margin-top:var(--sp-3)">'
    + '<div style="max-width:720px">'
    + '<h2 style="font-size:var(--t-head); font-weight:600">' + esc(study.title) + '</h2>'
    + (verdikt ? '<div style="font-size:var(--t-lead); color:var(--text); margin-top:var(--sp-3); line-height:var(--lh-snug); font-weight:500">' + esc(verdikt) + '</div>' : '')
    + '<div style="font-size:var(--t-body); color:var(--ink-3); margin-top:var(--sp-3); line-height:var(--lh-snug)">' + esc(study.note) + '</div>'
    + konfigZeile(p.config)
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
    + trichter(p.strategies, vok)
    + ablehnungen(p.rejections_24h, vok)
    + tafeln
    + aufloesungKennzahlen(aufloesungen(auf))
    + paperBuch(p.paper_positions, p.summary, auf)
    + klassenTafel(vok)
    + methodik()
    + '<div style="display:flex; gap:var(--sp-5); align-items:center; flex-wrap:wrap; margin-top:var(--sp-6)">'
    + '<a href="./data/' + ARB_SCAN_DATEI + '" download="' + ARB_SCAN_DATEI + '" class="hv-edge-max" style="' + KNOPF + '">Download the data</a>'
    + (aufloesungen(auf) ? '<a href="./data/' + ARB_RESOLUTIONS_DATEI + '" download="' + ARB_RESOLUTIONS_DATEI + '" class="hv-edge-max" style="' + KNOPF + '">Download the resolutions</a>' : '')
    + '<div style="' + NOTIZ + '">' + esc(schnappschuss.join(' · ')) + '</div>'
    + '</div>');
}
