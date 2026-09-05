// Overview (research landing), Markets, Live tape, Cross-venue, Resolved.
// Markup ported from the design reference; data flows through the Terminal
// instance (T). Nothing here invents a number: every figure names its payload
// or the panel says which payload is missing.

import { asOfLine, esc, money, num, volume, contracts, herkunftSatz, leerBlock, leerZeile, seitenKopf, catChipsPresent, signedMoney, stempel, EINZAHLUNGEN_USD, offeneNichtDrin, tapeFenster, fensterSatz, categorySourceLabel, ledgerBotPositionen } from '../util.js';
import { caveatZeile } from '../claims.js';
import { spiegelZeit, kurzGeld, histogramm } from '../charts.js';
import { studieAnker } from './microstructure_page.js';
import { renderArbScanAbschnitt } from './arb_scan_page.js';
import { MONO as M, LABEL_BLOCK, LABEL, NOTIZ, kpi } from '../ui.js';

const REPO_URL = 'https://github.com/Pablozh123/prediction-market-terminal';
const ONE_PAGER_URL = REPO_URL + '/blob/main/docs/research/ONE_PAGER.md';

function filterGroup(label, chipsHtml) {
  return '<div><div style="' + LABEL_BLOCK + '">' + label + '</div><div style="display:flex; gap:var(--sp-3); flex-wrap:wrap">' + chipsHtml + '</div></div>';
}

// Category chip row shared by Markets, Live tape and Whale flow: only the
// categories present in the rows are offered, 'All' first.
function catChipRow(T, rows, key, stateKey, current) {
  const cats = ['All'].concat(catChipsPresent(rows, key));
  return '<div style="display:flex; gap:var(--sp-3); flex-wrap:wrap">'
    + cats.map((c) => T.chip(c.toUpperCase(), current === c, { [stateKey]: c })).join('')
    + '</div>';
}

// Spaltenraster der Markttabelle — Kopfzeile und Zeilen teilen es.
const MARKT_SPALTEN = '1fr 64px 90px 76px 96px 104px 96px';

// A clickable row keeps its handler and its tab stop but takes the table's
// row role: the view helpers in app.js hand out button actions, and an
// element cannot be both a row and a button. Without an action (a print
// whose market is not loaded) it is a plain row.
function zeilenAct(act) {
  return (act ? act.replace(/ role="[^"]*"/, '') + ' ' : '') + 'role="row"';
}

// A sortable head cell of the Markets table: the click keeps its handler and
// tab stop, the role stays the column's (a columnheader cannot also be a
// button), and aria-sort names the column the rows currently follow.
function sortKopf(T, key, richtung) {
  return T.act(() => T.setState({ marketSort: key }), { role: null })
    + ' role="columnheader" aria-sort="' + (T.state.marketSort === key ? richtung : 'none') + '"';
}

function marketRowHtml(v) {
  return '<div ' + zeilenAct(v.act) + ' class="hv-panel" style="display:grid; grid-template-columns:' + MARKT_SPALTEN + '; align-items:center; padding:var(--sp-4) var(--sp-6); border-bottom:1px solid var(--line-3); cursor:pointer">'
    + '<div role="cell" style="padding-right:var(--sp-6)">'
    + '<div style="font-size:var(--t-body); line-height:var(--lh-tight)">' + esc(v.title) + '</div>'
    + '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-3); margin-top:var(--sp-2)">' + esc(v.meta) + '</div></div>'
    + '<div role="cell" style="' + M + '; font-size:var(--t-lead); text-align:right">' + v.priceLabel + '</div>'
    + '<div role="cell" style="' + v.changeStyle + '">' + v.changeLabel + '</div>'
    + '<div role="cell" style="' + M + '; font-size:var(--t-small); text-align:right; color:var(--ink-4)">' + esc(v.spreadLabel || '—') + '</div>'
    + '<div role="cell" style="' + M + '; font-size:var(--t-small); text-align:right; color:var(--ink-4)">' + esc(v.liqLabel || '—') + '</div>'
    // Unter der Volumenzahl ihr Anteil am groessten Volumen der Sicht, als
    // 56px-Balken: die Standard-Sortierspalte wird so ohne Lesen scannbar.
    + '<div role="cell" style="text-align:right"><div style="' + M + '; font-size:var(--t-body)">' + v.volLabel + '</div>'
    + (v.volShare != null
      ? '<div style="margin:var(--sp-2) 0 0 auto; width:56px; height:2px; border-radius:1px; background:rgba(var(--ink),.1)">'
        + '<div style="width:' + v.volShare.toFixed(1) + '%; height:100%; border-radius:1px; background:rgba(var(--ink),.45)"></div></div>'
      : '')
    + '</div>'
    + '<div role="cell" style="' + M + '; font-size:var(--t-small); text-align:right; color:var(--ink-4)">' + esc(v.ends) + '</div></div>';
}

// One compact insight panel on the Markets page: a heading, up to five
// clickable rows (each opens its market), and an honest line when the
// loaded sample has nothing that qualifies.
function insightPanel(titel, sub, rowsHtml, leerSatz) {
  return '<div style="background:var(--panel); border:1px solid var(--line-2); border-radius:var(--r-panel); overflow:hidden">'
    + '<div style="padding:var(--sp-3) var(--sp-5); border-bottom:1px solid var(--line-2)"><h2 style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:var(--accent); margin:0; display:inline">' + titel + '</h2>'
    + (sub ? ' <span style="' + M + '; font-size:var(--t-micro); color:var(--ink-4); letter-spacing:var(--ls-flat)">· ' + sub + '</span>' : '') + '</div>'
    + (rowsHtml || '<div style="padding:var(--sp-4) var(--sp-5); ' + M + '; font-size:var(--t-micro); color:var(--ink-4)">' + esc(leerSatz) + '</div>')
    + '</div>';
}

// ---------------------------------------------------------------- overview (research landing)

// Verdict vocabulary of public/data/microstructure.json (verdikt_art) as a
// tag: label, colour, edge. Anything unknown renders its raw value, uncoloured.
//
// The ground is --panel and not a wash of the tag's own hue, and that is the
// whole fix: a wash of the hue moves the ground toward the text, and on paper
// the role colours have no headroom to give it. With the tint composited in
// rather than measured against the page, CONFIRMED read 4.05:1, REFUTED
// 3.86:1 and CONTROL 4.31:1. Thinning the wash does not rescue them -- at .04
// the first two still fail -- because --accent, --neg-soft and --warn clear
// the light ground by barely 0.1 to themselves. So the hue leaves the text's
// ground and moves to the edge, where it says the same thing and costs
// nothing. On --panel the four tags read 5.08 / 4.96 / 4.98 / 5.61 light and
// 8.41 / 7.11 / 6.33 / 6.36 dark.
const VERDICT_TAG = {
  ja: { label: 'CONFIRMED', color: 'var(--accent)', rand: 'rgba(var(--accent-rgb),.35)' },
  nein: { label: 'REFUTED', color: 'var(--neg-soft)', rand: 'rgba(var(--neg-rgb),.35)' },
  offen: { label: 'NOT IDENTIFIED', color: 'var(--warn)', rand: 'rgba(var(--warn-rgb),.35)' },
  kontrolle: { label: 'CONTROL', color: 'var(--info)', rand: 'rgba(var(--info-rgb),.35)' }
};

function verdictTag(art) {
  const v = VERDICT_TAG[String(art || '').toLowerCase()];
  const label = v ? v.label : String(art || '—').toUpperCase();
  const style = M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); border-radius:var(--r-control); padding:var(--sp-2) var(--sp-3); white-space:nowrap; background:var(--panel); '
    + (v ? 'color:' + v.color + '; border:1px solid ' + v.rand : 'color:var(--ink-4); border:1px solid var(--line-1)');
  return '<span style="' + style + '">' + esc(label) + '</span>';
}

// The verdict counts, derived from the payload, never typed in: prefer the
// payload's own zaehler block, fall back to counting studien[].verdikt_art.
export function verdictCounts(micro) {
  const st = micro && Array.isArray(micro.studien) ? micro.studien : [];
  const z = micro && micro.zaehler ? micro.zaehler : null;
  const zaehl = (art) => st.filter((s) => String(s.verdikt_art || '').toLowerCase() === art).length;
  const total = z && z.gesamt != null ? +z.gesamt : st.length;
  return {
    total,
    ja: z && z.ja != null ? +z.ja : zaehl('ja'),
    nein: z && z.nein != null ? +z.nein : zaehl('nein'),
    offen: z && z.offen != null ? +z.offen : zaehl('offen'),
    kontrolle: z && z.kontrolle != null ? +z.kontrolle : zaehl('kontrolle')
  };
}

// The key number of a study, and the sample size from basis (observations,
// snapshots, pairs, markets — whichever the study recorded). Ranges render
// as "a to b".
//
// Which entry of zahlen[] is the key: the first that measures something
// (a percentage, cents, dollars, ticks, hours) rather than counts the
// sample. Studies 08 to 11 led with "8 pairs matched" next to "n = 8
// pairs" — the same number twice and no finding. A count with a unit that
// is a share of the sample ("3 pairs" of 5) renders as "3 of 5 pairs".
const ZAEHL_EINHEITEN = { observations: 1, segments: 1, pairs: 1, markets: 1, tokens: 1, fills: 1, snapshots: 1 };
const BASIS_JE_EINHEIT = { pairs: 'paare', markets: 'maerkte', tokens: 'tokens', observations: 'beobachtungen', snapshots: 'snapshots' };
function istZaehlung(z) {
  const einheit = String(z.einheit || '').toLowerCase();
  return !einheit || ZAEHL_EINHEITEN[einheit] === 1;
}
function keyNumber(study) {
  const liste = study && Array.isArray(study.zahlen) ? study.zahlen.filter((z) => z && z.wert != null && z.wert !== '') : [];
  if (!liste.length) return { value: '—', label: '', unit: '' };
  const basis = study.basis || {};
  const n = (z) => { const k = BASIS_JE_EINHEIT[String(z.einheit || '').toLowerCase()]; return k && basis[k] != null ? +basis[k] : null; };
  // In payload order, the first entry that is not a bare count (no unit)
  // and not the sample size restated; when every candidate restates n
  // ("5 of 5 pairs"), the last one, which is where a study puts its
  // finding. Failing all that, the first entry as before.
  const kandidaten = liste.filter((x) => !(istZaehlung(x) && !x.einheit));
  const z = kandidaten.find((x) => !(istZaehlung(x) && n(x) != null && +x.wert === n(x)))
    || kandidaten[kandidaten.length - 1]
    || liste[0];
  let value;
  if (Array.isArray(z.wert)) value = z.wert.map((v) => fmtWert(v)).join(' to ');
  else value = fmtWert(z.wert);
  const gesamt = n(z);
  const anteil = istZaehlung(z) && z.einheit && gesamt != null && !Array.isArray(z.wert) && +z.wert <= gesamt;
  return {
    value: anteil ? value + ' of ' + num(gesamt) : value,
    label: String(z.label || ''),
    unit: String(z.einheit || '')
  };
}

function fmtWert(v) {
  if (v == null || v === '') return '—';
  const n = +v;
  if (isNaN(n)) return String(v);
  if (Math.abs(n) >= 1000) return num(Math.round(n));
  if (Number.isInteger(n)) return String(n);
  return String(Math.abs(n) < 1 ? +n.toFixed(3) : +n.toFixed(1));
}

function sampleLabel(basis) {
  if (!basis) return '';
  const order = [['beobachtungen', 'obs'], ['snapshots', 'snapshots'], ['paare', 'pairs'], ['maerkte', 'markets'], ['tokens', 'tokens']];
  for (let i = 0; i < order.length; i += 1) {
    const [k, l] = order[i];
    if (basis[k] != null && basis[k] !== '') return 'n = ' + num(basis[k]) + ' ' + l;
  }
  return '';
}

// Words the sub-line uses for counts; anything above twelve falls back to
// the digit so the sentence never lies about the payload.
const ZAHLWORT = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'eleven', 'twelve'];
function zahlwort(n) { return n >= 0 && n < ZAHLWORT.length ? ZAHLWORT[n] : String(n); }

// The sub-line of the landing, assembled from the three payloads. Each clause
// appears only when its payload answered.
export function landingSubline(landing) {
  const teile = [];
  const micro = landing && landing.micro;
  const runs = landing && landing.runs;
  if (micro && Array.isArray(micro.studien) && micro.studien.length) {
    const c = verdictCounts(micro);
    const w = zahlwort(c.total);
    teile.push(w.charAt(0).toUpperCase() + w.slice(1) + ' studies (' + c.nein + ' refuted, ' + c.ja + ' confirmed, ' + c.offen + ' not identified, ' + c.kontrolle + ' control)');
  }
  const agg = runs && runs.aggregat;
  if (agg && agg.n_runs != null) teile.push(num(agg.n_runs) + ' small-stake live runs');
  teile.push('a pre-registered pilot');
  const satz = teile.join(', ') + ' — no profitability claim.';
  return satz.charAt(0).toUpperCase() + satz.slice(1);
}

function landingLeerSatz(herkunft, datei) {
  const q = herkunft && herkunft.quelle;
  if (q === 'fehler') return datei + ' did not load: ' + (herkunft.fehler || 'unknown error') + '. Nothing is shown rather than a placeholder.';
  if (q === 'leer') return datei + ' answered without content.';
  return 'Loading ' + datei + '…';
}

function sectionHead(label, right, color) {
  return '<div style="display:flex; align-items:center; justify-content:space-between; gap:var(--sp-4); padding:var(--sp-4) var(--sp-6); border-bottom:1px solid var(--line-2); background:var(--panel)">'
    + '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:' + (color || 'var(--accent)') + '">' + label + '</div>'
    + '<div style="display:flex; align-items:center; gap:var(--sp-5)">' + (right || '') + '</div></div>';
}

// ---- The tape, live (landing hero) ----------------------------------------
// The most recent large prints from the 30 s poll, on the landing. A row
// animates only when its print arrived with the latest answer — the first
// render marks nothing as new, so the landing never plays a load show, and
// motion happens exactly when the market did something. Without live tape
// (file host, sleeping API) the head stays one column; nothing is staged.
function tapeLivePanel(T) {
  const rows = (T.tape || []).slice(0, 8);
  if (!rows.length) return '';
  const schluessel = (t) => [t.ts || '', t.walletAddress || t.wallet, t.marketKey, t.side, t.size].join('|');
  const erste = !(T._tapeGesehen instanceof Set);
  const gesehen = erste ? new Set() : T._tapeGesehen;
  const zeilen = rows.map((t) => {
    const neu = !erste && !gesehen.has(schluessel(t));
    const kauf = String(t.side).indexOf('BUY') === 0;
    return '<div' + (neu ? ' class="tape-in"' : '') + ' style="display:grid; grid-template-columns:84px minmax(0,1fr) 110px 76px; gap:var(--sp-4); align-items:baseline; padding:var(--sp-3) var(--sp-6); border-bottom:1px solid var(--line-3)">'
      + '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-4); white-space:nowrap">' + esc(t.ago) + '</div>'
      + '<div style="font-size:var(--t-small); white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="' + esc(t.market) + '">' + esc(t.market) + '</div>'
      + '<div style="' + M + '; font-size:var(--t-micro); color:' + (kauf ? 'var(--pos)' : 'var(--neg)') + '; text-align:right; white-space:nowrap">' + esc(t.side) + ' ' + esc(t.price || '') + '</div>'
      + '<div style="' + M + '; font-size:var(--t-micro); text-align:right">' + money(t.size) + '</div></div>';
  }).join('');
  // Merken, was diese Antwort zeigte — der naechste Poll animiert nur Neues.
  T._tapeGesehen = new Set(rows.map(schluessel));
  return '<div style="display:flex; align-items:baseline; justify-content:space-between; gap:var(--sp-4); padding:var(--sp-5) var(--sp-6) var(--sp-3); border-top:1px solid var(--line-3)">'
    + '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:var(--ink-3)">THE TAPE, LIVE · PRINTS ≥ $2.5K</div>'
    + '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-4)">refreshes every 30 s · read-only</div></div>'
    + zeilen;
}

// ---- The wire (landing) ----------------------------------------------------
// Ein laufendes Band der groessten Maerkte aus dem 30-s-Poll. Die Zeilen sind
// dieselben echten Reihen wie auf der Marktseite; nur die Bewegung ist Zierde
// (ambient.js schiebt das Band; der Inhalt ist fuer die Schleife verdoppelt).
// Eine Preiszelle blitzt einmal auf, wenn der Poll sie bewegt hat. Ohne
// lebende Maerkte gibt es kein Band. Fuer Screenreader ist es verborgen —
// die Maerkte stehen als richtige Tabelle einen Klick entfernt.
// Die Veraenderung traegt ihr Cent-Zeichen wie der Preis daneben: sie stand
// als nackte "+35" neben "70¢", und auf der Marktseite heisst dieselbe Zahl
// "+87¢". Zwei Schreibweisen fuer dieselbe Groesse auf derselben Seite.
function wireStrip(T) {
  const maerkte = T.markets.slice().sort((a, b) => volOrd(b) - volOrd(a)).slice(0, 10);
  if (!maerkte.length) return '';
  const vorher = T._wireVorher instanceof Map ? T._wireVorher : null;
  const items = maerkte.map((m) => {
    const delta = vorher && vorher.has(m.id) ? m.yes - vorher.get(m.id) : 0;
    const blitz = delta > 0 ? ' class="wire-up"' : delta < 0 ? ' class="wire-dn"' : '';
    return '<span style="display:inline-flex; align-items:baseline; gap:var(--sp-3); padding:0 var(--sp-6); border-right:1px solid var(--line-2)">'
      + '<span style="color:var(--ink-3)">' + esc(m.title) + '</span>'
      + '<span' + blitz + ' style="font-weight:600; border-radius:3px; padding:0 var(--sp-2)">' + num(m.yes) + '¢</span>'
      + (m.chg ? '<span style="color:' + (m.chg > 0 ? 'var(--pos)' : 'var(--neg)') + '">' + (m.chg > 0 ? '+' : '−') + Math.abs(m.chg) + '¢</span>' : '')
      + '</span>';
  }).join('');
  T._wireVorher = new Map(maerkte.map((m) => [m.id, m.yes]));
  return '<div aria-hidden="true" style="border-bottom:1px solid var(--line-2); background:var(--panel); overflow:hidden; ' + M + '; font-size:var(--t-small)">'
    + '<div id="wire-row" style="display:inline-flex; white-space:nowrap; padding:var(--sp-3) 0; will-change:transform">' + items + items + '</div></div>';
}

// Die Mindestgroesse der Tape-Abfrage in app.js (min_cash=2500).
const TAPE_MIN_USD = 2500;

// Volumen zum Ordnen ueber beide Venues: Polymarket meldet Dollar, Kalshi
// Kontrakte. Ein Kontrakt zahlt einen Dollar und handelt zu p, also ist
// Kontrakte mal p die Dollarnaeherung — nur fuer die Reihenfolge, angezeigt
// wird weiter die Zahl in ihrer Einheit. Vorher stand ein Kalshi-Markt mit
// 100k Kontrakten zu 50 Cent ueber einem Polymarket-Markt mit $60k Umsatz.
function volOrd(m) {
  const v = +m.vol || 0;
  return m.venue === 'Kalshi' ? v * (Math.max(1, Math.min(99, +m.yes || 50)) / 100) : v;
}

export function renderOverview(T) {
  const s = T.state;
  const landing = T.landing || { micro: null, runs: null, notes: null, herkunft: {} };
  const micro = landing.micro;
  const runs = landing.runs;
  const notes = landing.notes;
  const hk = landing.herkunft || {};
  const microIdx = T.studies.findIndex((st) => st.tab === 'Microstructure');
  const runsIdx = T.studies.findIndex((st) => st.tab === 'Live runs');
  const notesIdx = T.studies.findIndex((st) => st.tab === 'Field notes');
  const pilotIdx = T.studies.findIndex((st) => st.tab === 'Pilot');
  const goStudy = (i, anker) => (i >= 0 && T.goStudy ? T.act(() => T.goStudy(i, anker)) : '');
  const link = (i, label, color) => (i >= 0
    ? '<div ' + goStudy(i) + ' class="hv-accent" style="' + M + '; font-size:var(--t-micro); color:' + (color || 'var(--ink-3)') + '; cursor:pointer; padding:var(--sp-2) 0; white-space:nowrap">' + label + ' →</div>'
    : '');

  // ---- verdict board -----------------------------------------------------
  const studien = micro && Array.isArray(micro.studien) ? micro.studien : [];
  const counts = verdictCounts(micro);
  let board;
  if (studien.length) {
    board = '<div style="display:grid; grid-template-columns:36px 1fr 128px 190px 150px; padding:var(--sp-3) var(--sp-6); border-bottom:1px solid var(--line-2); ' + LABEL + '">'
      + '<div>#</div><div>QUESTION</div><div>VERDICT</div><div style="text-align:right">KEY NUMBER · N</div><div style="text-align:right">WINDOW</div></div>'
      + studien.map((st, i) => {
        const kn = keyNumber(st);
        const basis = st.basis || {};
        const nLabel = sampleLabel(basis);
        // Jede Zeile fuehrt direkt zu ihrer Karte auf der Microstructure-Seite,
        // nicht zum Seitenanfang: gleicher Anker wie die Sprungliste dort.
        return '<div ' + goStudy(microIdx, studieAnker(st, i)) + ' class="hv-panel" style="display:grid; grid-template-columns:36px 1fr 128px 190px 150px; align-items:center; padding:var(--sp-4) var(--sp-6); border-bottom:1px solid var(--line-3); cursor:pointer">'
          + '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-3)">' + String(i + 1).padStart(2, '0') + '</div>'
          + '<div style="padding-right:var(--sp-5); min-width:0"><div style="font-size:var(--t-body); line-height:var(--lh-tight)">' + esc(st.frage || st.id || '—') + '</div>'
          // Truncated lines carry the full text as a tooltip.
          + '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-3); margin-top:var(--sp-2); white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="' + esc(String(st.verdikt || '')) + '">' + esc(String(st.verdikt || '').split('. ')[0]) + '</div></div>'
          + '<div>' + verdictTag(st.verdikt_art) + '</div>'
          + '<div style="text-align:right; min-width:0"><div style="' + M + '; font-size:var(--t-body)">' + esc(kn.value) + (kn.unit ? ' <span style="font-size:var(--t-micro); color:var(--ink-3)">' + esc(kn.unit) + '</span>' : '') + '</div>'
          + '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-3); margin-top:var(--sp-1); white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="' + esc(kn.label + (nLabel ? ' · ' + nLabel : '')) + '">' + esc(kn.label) + (nLabel ? ' · ' + esc(nLabel) : '') + '</div></div>'
          + '<div style="' + M + '; font-size:var(--t-micro); text-align:right; color:var(--ink-4)">' + esc(basis.fenster || '—') + '</div></div>';
      }).join('');
  } else {
    board = leerZeile(landingLeerSatz(hk.micro, 'microstructure.json'));
  }

  // ---- live-runs strip ----------------------------------------------------
  const agg = runs && runs.aggregat ? runs.aggregat : null;
  // Wallet-Zahlen ueberall (frischeste Quelle zuerst — der direkt geladene
  // Wallet-Ledger, sonst der aus extras, sonst der kuratierte Abgleich).
  // Die Log-Rekonstruktion steht nicht mehr auf der Landung; sie erscheint
  // nur als benannter Rueckfall, wenn es noch keine Wallet-Zahl gibt.
  const ledger = landing.ledger || (runs && runs.extras && runs.extras.wallet_ledger) || null;
  const ledgerBot = ledger && ledger.aggregat && ledger.aggregat.nach_typ ? ledger.aggregat.nach_typ.bot : null;
  const ledgerStand = ledger && ledger.stand_utc ? String(ledger.stand_utc).slice(0, 10) : '';
  const abgleichStand = agg && agg.wallet_abgleich_stand ? String(agg.wallet_abgleich_stand) : '';
  const ledgerFrischer = ledgerBot && ledgerStand && (!abgleichStand || ledgerStand > abgleichStand);
  const walletNetto = ledgerFrischer && ledgerBot.netto_cash_usd != null
    ? { wert: +ledgerBot.netto_cash_usd, stand: ledgerStand }
    : agg && agg.wallet_netto_usd != null
      ? { wert: +agg.wallet_netto_usd, stand: abgleichStand }
      : null;
  const walletKaeufe = ledgerFrischer && ledgerBot.einsatz_usd != null
    ? +ledgerBot.einsatz_usd
    : agg && agg.wallet_kaeufe_usd != null ? +agg.wallet_kaeufe_usd : null;
  const pnlZelle = walletNetto
    ? kpiCell('NET PNL (WALLET · BOT MARKETS)', signedMoney(walletNetto.wert),
      (ledgerFrischer ? 'bot markets in the wallet ledger' : 'on-chain wallet, reconciled')
      + (ledger && ledger.aggregat && ledger.aggregat.netto_cashflow_usd != null ? ' · whole wallet ' + signedMoney(+ledger.aggregat.netto_cashflow_usd) : ''), true, walletNetto.wert)
    : kpiCell('NET PNL (FROM RUN LOGS)', agg && agg.realisierter_pnl_usd != null ? signedMoney(agg.realisierter_pnl_usd) : '—', 'no wallet reconciliation yet', true, agg && agg.realisierter_pnl_usd);
  // Die vierte Zelle: das ganze Wallet als Rendite. Bezugsgroesse ist immer
  // die einmalige Einzahlung (on-chain nachpruefbar) — aus dem Ledger, sonst
  // die deklarierte Konstante. Nie die Kaufsumme: jeder reinvestierte Dollar
  // wuerde die Basis aufblaehen und die Rendite kleinrechnen.
  const la = ledger && ledger.aggregat ? ledger.aggregat : null;
  let botPos = null;
  const einzahlungen = la && la.einzahlungen_usd != null ? +la.einzahlungen_usd : EINZAHLUNGEN_USD;
  let flussZelle = kpiCell('ROI (WALLET · ALL ACTIVITY)', '—', 'wallet_ledger.json not loaded yet', false);
  if (la && la.netto_cashflow_usd != null && einzahlungen > 0) {
    const roi = (100 * +la.netto_cashflow_usd) / einzahlungen;
    flussZelle = kpiCell('ROI (WALLET · ALL ACTIVITY)', (roi >= 0 ? '+' : '') + roi.toFixed(1) + '%',
      'net cashflow ' + signedMoney(+la.netto_cashflow_usd)
      + ' on the one-time deposit of $' + num(einzahlungen.toFixed(0)) + offeneNichtDrin(la), false, roi);
  }
  const runsStrip = agg
    ? '<div style="display:grid; grid-template-columns:repeat(4,1fr); border-bottom:1px solid var(--line-2)">'
      + kpiCell('RUNS · BETS', num(agg.n_runs != null ? agg.n_runs : '—') + ' · ' + num(agg.n_wetten != null ? agg.n_wetten : '—'),
        (walletKaeufe != null ? 'wallet buys $' + num(walletKaeufe.toFixed(0)) : 'stake ' + (agg.einsatz_usd != null ? '$' + num((+agg.einsatz_usd).toFixed(0)) + ' (from run logs)' : '—'))
        + (runs && runs.stand_utc ? ' · payload ' + esc(stempel(runs.stand_utc)) : ''), true)
      // WON · LOST aus dem Wallet-Ledger (alle aufgeloesten Positionen,
      // wertlos ausgelaufene zaehlen als verloren) — die Run-Zaehlung aus
      // runs.json sah nur die Bot-Wetten und unterschlug den Rest des
      // Wallets. Ohne Ledger bleibt die Run-Zaehlung als benannter Rueckfall.
      // Dieselbe Basis wie RUNS · BETS und NET PNL daneben: die Bot-Maerkte
      // des Wallets. Die Zaehlung des ganzen Wallets (42 · 12 mit Hand- und
      // Pilot-Positionen) stand hier neben 24 Laeufen und 27 Wetten und
      // ergab 54 Ergebnisse fuer 27 Wetten.
      // Rueckfallkette: ohne Marktereignisse im Ledger die Zaehlung des
      // ganzen Wallets (so beschriftet), ohne Ledger die aus den Run-Logs.
      + ((botPos = ledgerBotPositionen(ledger))
        ? kpiCell('WON · LOST', num(botPos.won) + ' · ' + num(botPos.lost),
          (botPos.open ? num(botPos.open) + ' open · ' : '')
          + num(botPos.n) + ' bot markets in the wallet ledger, worthless counts as lost'
          + (la && la.positionen_gewonnen != null && la.positionen_verloren != null
            ? ' · whole wallet ' + num(la.positionen_gewonnen) + ' · ' + num(la.positionen_verloren) : ''), true)
        : la && la.positionen_gewonnen != null && la.positionen_verloren != null
          ? kpiCell('WON · LOST', num(la.positionen_gewonnen) + ' · ' + num(la.positionen_verloren),
            (la.positionen && +la.positionen.open ? num(la.positionen.open) + ' open · ' : '')
            + 'all wallet positions, worthless counts as lost · no profitability claim', true)
          : kpiCell('WON · LOST', num(agg.gewonnen != null ? agg.gewonnen : '—') + ' · ' + num(agg.verloren != null ? agg.verloren : '—'), (agg.offen ? num(agg.offen) + ' open' : 'none open') + ' · no profitability claim · bot runs only', true))
      + pnlZelle
      + flussZelle
      + '</div>'
    : leerZeile(landingLeerSatz(hk.runs, 'runs.json'));

  // ---- field-notes strip --------------------------------------------------
  const noteList = notes && Array.isArray(notes.notes) ? notes.notes.slice(0, 5) : [];
  const notesStrip = noteList.length
    ? noteList.map((n) =>
      '<div ' + goStudy(notesIdx) + ' class="hv-panel" style="display:grid; grid-template-columns:96px 1fr 120px; gap:var(--sp-4); align-items:center; padding:var(--sp-4) var(--sp-6); border-bottom:1px solid var(--line-3); cursor:pointer">'
      + '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-3)">' + esc(String(n.date || '').slice(0, 10)) + '</div>'
      + '<div style="font-size:var(--t-body); line-height:var(--lh-tight)">' + esc(n.title || '—') + '</div>'
      + '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-3); text-align:right">' + esc(n.venue || '') + '</div></div>'
    ).join('')
    : leerZeile(landingLeerSatz(hk.notes, 'field_notes.json'));

  // ---- live data row (from the existing 30 s poll) -----------------------
  // Diese Zelle addierte alle m.vol zu einer Zahl mit Dollarzeichen. Auf
  // Polymarket sind das Dollar, auf Kalshi Kontrakte (Beleg in
  // app/venue_units.py), also war die Summe keine Groesse. Der Dollarwert
  // steht jetzt allein fuer Polymarket, die Kalshi-Stueckzahl daneben.
  const pmVolUsd = T.markets.filter((m) => m.venue === 'Polymarket').reduce((a, m) => a + m.vol, 0);
  const ksVolContracts = T.markets.filter((m) => m.venue === 'Kalshi').reduce((a, m) => a + m.vol, 0);
  const pmCount = T.markets.filter((m) => m.venue === 'Polymarket').length;
  const ksCount = T.markets.length - pmCount;
  // /api/tape wird mit min_cash=2500 geholt (app.js pollLive); die Kachel
  // zaehlt dieselbe Schwelle. s.setWhale wurde nie an den Endpunkt gesendet:
  // hoeher gestellt zaehlte die Kachel eine Teilmenge unter der Ueberschrift
  // "≥ $2.5K", tiefer gestellt aenderte sich nichts.
  const whalePrints = T.tape.filter((t) => t.size >= TAPE_MIN_USD).length;
  const whaleWallets = new Set(T.tape.filter((t) => t.size >= TAPE_MIN_USD && t.wallet !== '—').map((t) => t.wallet)).size;
  const marktSatz = herkunftSatz(T.herkunft.markets, '/api/markets');
  const tapeSatz = herkunftSatz(T.herkunft.tape, '/api/tape');
  const hatMaerkte = T.markets.length > 0;
  const hatTape = T.tape.length > 0;
  const liveRow = '<div style="display:grid; grid-template-columns:repeat(3,1fr); border-bottom:1px solid var(--line-2)">'
    + kpiCell('MARKETS TRACKED', hatMaerkte ? num(T.markets.length) : '—', hatMaerkte ? num(pmCount) + ' Polymarket · ' + num(ksCount) + ' Kalshi' : esc(marktSatz), true)
    + kpiCell('POLYMARKET VOLUME · 24H', hatMaerkte ? money(pmVolUsd) : '—',
      hatMaerkte ? 'over ' + num(pmCount) + ' markets · Kalshi adds ' + contracts(ksVolContracts) + ', which is not a dollar figure' : esc(marktSatz), true)
    + kpiCell('PRINTS ≥ $2.5K · TAPE WINDOW', hatTape ? num(whalePrints) : '—', hatTape ? 'from ' + num(whaleWallets) + ' identified wallets' : esc(tapeSatz), false)
    + '</div>';

  const subline = landingSubline(landing);
  // Die zwei Haelften der Seite als zwei Einstiege direkt unter dem Titel:
  // links die getestete Strategie (Forschung, echte Laeufe, Bilanz), rechts
  // das Analysewerkzeug (Live-Screens). Wer die Seite oeffnet, sieht zuerst
  // diese Trennung, nicht eine Liste gleichrangiger Bloecke.
  const pfade = '<div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(280px, 1fr)); gap:var(--sp-4); margin-top:var(--sp-5); max-width:860px">'
    + pfadKarte(goStudy(runsIdx), 'TESTED STRATEGY', 'var(--accent)', 'Researched, then run with real money: every bet, its latency and the on-chain wallet that proves it.')
    + pfadKarte(T.act(() => T.go('markets')), 'ANALYSIS TOOL', 'var(--info)', 'Live screens on Polymarket & Kalshi: markets, tape, whale flow, cross-venue, risk.')
    + '</div>';
  // Rechts neben dem Titel, sobald der 30-s-Poll Prints liefert: das Band,
  // wie es gerade laeuft. Ohne lebende Antwort bleibt der Kopf einspaltig.
  // Hinter dem Kopf treibt der Wahrscheinlichkeits-Fluss die volle Breite
  // (ambient.js malt in die Canvas; ohne Achsen und Zahlen ist er erkennbar
  // Zierde, keine Messung). Der Verlauf davor haelt die Headline lesbar.
  return '<div>'
    + '<div style="padding:var(--sp-7) var(--sp-6) var(--sp-6); border-bottom:1px solid var(--line-2); position:relative; overflow:hidden; min-height:300px; box-sizing:border-box; display:flex; align-items:center">'
    + '<canvas id="river-cv" aria-hidden="true" style="position:absolute; inset:0; width:100%; height:100%"></canvas>'
    + '<div aria-hidden="true" style="position:absolute; inset:0; pointer-events:none; background:linear-gradient(90deg, rgba(var(--bg-rgb),.92) 0%, rgba(var(--bg-rgb),.62) 40%, rgba(var(--bg-rgb),.12) 68%, rgba(var(--bg-rgb),0) 100%)"></div>'
    + '<div style="position:relative; max-width:640px">'
    + '<h1 style="font-size:var(--t-hero); line-height:var(--lh-solid); margin:0; font-weight:600; letter-spacing:var(--ls-flat)">Prediction-market microstructure, <em style="color:var(--accent)">measured on self-recorded books.</em></h1>'
    + '<div style="font-size:var(--t-body); color:var(--ink-3); margin-top:var(--sp-3); max-width:760px">' + esc(subline) + '</div>'
    + pfade
    + '<div style="display:flex; gap:var(--sp-5); margin-top:var(--sp-5); flex-wrap:wrap; ' + M + '; font-size:var(--t-micro)">'
    + '<a href="' + REPO_URL + '" target="_blank" rel="noopener">GitHub repository →</a>'
    + '<a href="' + ONE_PAGER_URL + '" target="_blank" rel="noopener">One-pager (docs/research/ONE_PAGER.md) →</a>'
    + (pilotIdx >= 0 ? '<span ' + goStudy(pilotIdx) + ' class="hv-accent" style="color:var(--ink-4); cursor:pointer; display:inline-block; padding:var(--sp-2) 0">Pre-registered pilot →</span>' : '')
    + '</div></div>'
    + '</div>'

    // Das Band mit den groessten Maerkten laeuft direkt unter dem Kopf.
    + wireStrip(T)

    // Die getestete Strategie zuerst — sie ist das Argument der Seite; die
    // Studien liefern die Begruendung darunter.
    + sectionHead('TESTED STRATEGY · LIVE RUNS, REAL MONEY', link(runsIdx, 'EVERY BET'))
    + runsStrip

    + sectionHead('VERDICT BOARD · ' + (studien.length ? num(counts.total) + ' STUDIES' : 'MICROSTRUCTURE'),
      (micro && micro.stand_utc ? '<span style="' + M + '; font-size:var(--t-micro); color:var(--ink-4)">payload ' + esc(stempel(micro.stand_utc)) + '</span>' : '')
      + link(microIdx, 'FULL REPORT'))
    + board

    + sectionHead('FIELD NOTES', link(notesIdx, 'ALL NOTES'), 'var(--info)')
    + notesStrip

    + sectionHead('ANALYSIS TOOL · LIVE DATA', asOfLine(s.liveAsOf) + '<div ' + T.act(() => T.go('markets')) + ' class="hv-accent" style="' + M + '; font-size:var(--t-micro); color:var(--ink-3); cursor:pointer; padding:var(--sp-2) 0">MARKETS →</div><div ' + T.act(() => T.go('flow')) + ' class="hv-accent" style="' + M + '; font-size:var(--t-micro); color:var(--ink-3); cursor:pointer; padding:var(--sp-2) 0">TAPE →</div>')
    + liveRow
    // Das Tape als Streifen im Live-Block — dieselben Prints wie im Poll,
    // neue Zeilen gleiten ein, sobald sie ankommen.
    + tapeLivePanel(T)
    // Die Startseite ist die Flaeche, die ein Fremder zuerst sieht, und sie
    // trug bis hierher keinen einzigen Vorbehalt. score_generic sagt in
    // einem Satz, was die Zahlen darueber sind und was sie nicht sind.
    + caveatZeile('score_generic', {
      vorsatz: 'Public data only · live blocks refresh every 30 seconds · research payloads are frozen files under ./data ·',
      stil: 'padding:var(--sp-6); text-align:center; ' + M + '; font-size:var(--t-micro); color:var(--ink-4); line-height:var(--lh-prose)'
    })
    + '</div>';
}

// One of the two entry cards under the landing title; act is empty when the
// target study is not in the list, the card then renders without a cursor.
function pfadKarte(act, label, farbe, satz) {
  return '<div ' + act + (act ? ' class="hv-panel"' : '') + ' style="background:var(--panel); border:1px solid var(--line-2); border-radius:var(--r-panel); padding:var(--sp-5)' + (act ? '; cursor:pointer' : '') + '">'
    + '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:' + farbe + '">' + label + ' →</div>'
    + '<div style="font-size:var(--t-small); color:var(--ink-3); margin-top:var(--sp-3); line-height:var(--lh-snug)">' + satz + '</div></div>';
}

function kpiCell(label, value, sub, borderRight, signed) {
  return kpi({
    form: 'band', label, wert: value, sub: sub == null ? '' : sub, gross: true,
    trenner: borderRight,
    farbe: signed == null ? 'var(--text)' : (+signed >= 0 ? 'var(--pos)' : 'var(--neg)')
  });
}

// ---------------------------------------------------------------- markets
// Die Preisverteilung des geladenen Ausschnitts.
//
// Die Kachelzeile nennt Median-Spread und groessten Tagesmove; die Form
// dahinter sieht niemand. Sie beantwortet die erste Frage, die ein Bestand
// von Prediction Markets aufwirft: sind die Maerkte entschieden oder offen?
// Ein Feld, das sich an den Raendern stapelt, besteht groesstenteils aus
// Maerkten, in denen nichts mehr zu holen ist.
//
// Einheit ist Cent, nicht Dollar: der YES-Preis ist die Chance dieser Seite
// in Hundertsteln und auf beiden Boersen dieselbe Groesse. Volumen waere es
// nicht, deshalb steht es nicht in diesem Bild.
const PREIS_BIN = 5;

export function preisVerteilung(maerkte) {
  const preise = (maerkte || [])
    .map((m) => Number(m && m.yes))
    .filter((v) => v === v && v >= 0 && v <= 100);
  if (preise.length < 5) return '';
  const bins = [];
  for (let von = 0; von < 100; von += PREIS_BIN) {
    const bis = von + PREIS_BIN;
    bins.push({
      von,
      bis,
      anzahl: preise.filter((v) => (v >= von && v < bis) || (bis >= 100 && v === 100)).length
    });
  }
  const entschieden = preise.filter((v) => v < 5 || v > 95).length;
  const offen = preise.filter((v) => v >= 40 && v <= 60).length;
  const anteil = (n) => Math.round((n / preise.length) * 100);
  return histogramm({
    titel: 'WHAT THE SAMPLE BELIEVES',
    hinweis: num(preise.length) + ' markets with a quoted yes price',
    xLabel: 'yes price (cents)',
    yLabel: 'markets in the sample',
    bins,
    referenzen: [{ wert: 50, label: '50¢' }],
    zaehlEinheit: 'markets',
    xTickText: (v) => v + '¢',
    hoehe: 180,
    fussnote: anteil(entschieden) + '% of the sample trades outside 5 to 95 cents, so the crowd treats it as settled; '
      + anteil(offen) + '% sits between 40 and 60 cents. The yes price is the share price of that side in cents and '
      + 'means the same thing on both venues, unlike volume, which Polymarket reports in dollars and Kalshi counts in contracts.'
  });
}

export function renderMarkets(T) {
  const s = T.state;
  if (!T.markets.length) {
    return '<div>' + seitenKopf('MARKETS', 'Every market, one table', 'var(--accent)')
      + leerBlock('NO MARKET DATA', herkunftSatz(T.herkunft.markets, '/api/markets')) + '</div>';
  }
  // Die Kategorienleiste kommt aus den geladenen Maerkten. Eine feste Liste
  // haette Reiter angeboten, hinter denen nichts liegt. Jeder Chip traegt
  // seine Anzahl, damit man sieht, wo etwas liegt, bevor man klickt.
  const cats = ['All'].concat(catChipsPresent(T.markets, 'cat'));
  const catAnzahl = {};
  T.markets.forEach((m) => { const c = m.cat || 'Other'; catAnzahl[c] = (catAnzahl[c] || 0) + 1; });

  const mx = (m) => T.marketExtraOf(m);

  // ---- Einblicke aus dem geladenen Ausschnitt, alle Zeilen klickbar ------
  // Getrennt, aus demselben Grund wie oben: Dollar und Stueck sind nicht
  // dieselbe Groesse und ergeben zusammen keine dritte.
  const pmVolSample = T.markets.filter((m) => m.venue === 'Polymarket').reduce((a, m) => a + m.vol, 0);
  const ksVolSample = T.markets.filter((m) => m.venue === 'Kalshi').reduce((a, m) => a + m.vol, 0);
  const pmAnzahl = T.markets.filter((m) => m.venue === 'Polymarket').length;
  const spreads = T.markets.map((m) => mx(m).spread).filter((v) => v != null).sort((a, b) => a - b);
  const spreadMedian = spreads.length ? (spreads.length % 2 ? spreads[(spreads.length - 1) / 2] : (spreads[spreads.length / 2 - 1] + spreads[spreads.length / 2]) / 2) : null;
  const movers = T.markets.filter((m) => m.chg !== 0).sort((a, b) => Math.abs(b.chg) - Math.abs(a.chg)).slice(0, 5);
  // Nur kuenftige Enddaten: Gamma traegt fuer aktive, nicht aufgeloeste
  // Maerkte oft ein Datum in der Vergangenheit, und die standen mit
  // "under 1 d" ganz oben, als loesten sie heute auf.
  const baldFaellig = T.markets.filter((m) => mx(m).endsDays != null && mx(m).endsDays >= 0).sort((a, b) => mx(a).endsDays - mx(b).endsDays).slice(0, 5);
  const unentschieden = T.markets.filter((m) => m.yes >= 40 && m.yes <= 60).sort((a, b) => volOrd(b) - volOrd(a)).slice(0, 5);
  const topMover = movers[0] || null;
  const kurz = (t) => (String(t).length > 44 ? String(t).slice(0, 43) + '…' : String(t));
  const zeile = (m, mitte, rechts) =>
    '<div ' + T.act(() => T.openMarket(m.id)) + ' class="hv-panel" style="display:grid; grid-template-columns:1fr 46px 78px; gap:var(--sp-3); align-items:center; padding:var(--sp-3) var(--sp-5); border-bottom:1px solid var(--line-3); cursor:pointer">'
    + '<div style="font-size:var(--t-small); white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="' + esc(m.title) + '">' + esc(m.title) + '</div>'
    + '<div style="' + M + '; font-size:var(--t-small); text-align:right; color:var(--ink-4)">' + mitte + '</div>'
    + '<div style="' + M + '; font-size:var(--t-small); text-align:right">' + rechts + '</div></div>';
  const preisChart = preisVerteilung(T.markets);
  const kpiStrip = '<div style="display:grid; grid-template-columns:repeat(4,1fr); border:1px solid var(--line-2); border-radius:var(--r-panel); margin-top:var(--sp-5); overflow:hidden; background:var(--panel)">'
    + kpiCell('MARKETS IN SAMPLE', num(T.markets.length), pmAnzahl + ' Polymarket · ' + (T.markets.length - pmAnzahl) + ' Kalshi', true)
    + kpiCell('POLYMARKET VOLUME 24H', money(pmVolSample), 'Kalshi trades in contracts: ' + contracts(ksVolSample), true)
    + kpiCell('BIGGEST 1D MOVE', topMover ? (topMover.chg >= 0 ? '+' : '') + topMover.chg + '¢' : '—',
      topMover ? esc(kurz(topMover.title)) : 'no market in the sample moved', true, topMover ? topMover.chg : null)
    + kpiCell('MEDIAN SPREAD', spreadMedian != null ? spreadMedian + '¢' : '—',
      spreads.length ? 'n = ' + num(spreads.length) + ' markets with a quoted spread' : 'no spreads in the sample', false)
    + '</div>';
  const einblicke = '<div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(280px, 1fr)); gap:var(--sp-4); margin-top:var(--sp-4)">'
    + insightPanel('TOP MOVERS · 1D', 'yes price · change',
      movers.map((m) => zeile(m, m.yes + '¢', '<span style="color:' + (m.chg >= 0 ? 'var(--pos)' : 'var(--neg)') + '">' + (m.chg >= 0 ? '+' : '') + m.chg + '¢</span>')).join(''),
      'no market in the sample moved in the last day')
    + insightPanel('RESOLVING NEXT', 'yes price · resolves',
      baldFaellig.map((m) => zeile(m, m.yes + '¢', esc(mx(m).endsDays <= 1 ? 'under 1 d' : 'in ' + mx(m).endsDays + ' d'))).join(''),
      'no market in the sample carries an end date')
    + insightPanel('COIN FLIPS', 'priced 40–60¢, the market is undecided · by volume',
      unentschieden.map((m) => zeile(m, m.yes + '¢', volume(m.vol, m.venue))).join(''),
      'no market in the sample is priced 40–60¢')
    + '</div>';
  let mRows = T.markets.slice();
  const mActive = [];
  const addChip = (label, reset) => mActive.push({ label, reset });
  if (s.marketQuery.trim()) {
    const q = s.marketQuery.trim().toLowerCase();
    mRows = mRows.filter((m) => m.title.toLowerCase().indexOf(q) >= 0 || m.cat.toLowerCase().indexOf(q) >= 0);
    addChip('search: ' + s.marketQuery.trim(), { marketQuery: '' });
  }
  if (s.marketCat !== 'All') { mRows = mRows.filter((m) => m.cat === s.marketCat); addChip(s.marketCat, { marketCat: 'All' }); }
  if (s.mExclude.length) { mRows = mRows.filter((m) => s.mExclude.indexOf(m.cat) < 0); addChip('excluding ' + s.mExclude.join(', '), { mExclude: [] }); }
  if (s.mPlatform !== 'all') { mRows = mRows.filter((m) => m.venue === s.mPlatform); addChip(s.mPlatform, { mPlatform: 'all' }); }
  if (s.mProb !== 'all') {
    const p = { '5-95': [5, 95], '20-80': [20, 80], '80': [80, 100], '95': [95, 100], '99': [99, 100] }[s.mProb];
    mRows = mRows.filter((m) => m.yes >= p[0] && m.yes <= p[1]);
    addChip('probability ' + s.mProb, { mProb: 'all' });
  }
  if (s.mLiq !== 'all') {
    const v = { '1k': 1000, '10k': 10000, '100k': 100000 }[s.mLiq];
    mRows = mRows.filter((m) => m.liq >= v); addChip('liquidity > $' + s.mLiq, { mLiq: 'all' });
  }
  if (s.mVol !== 'all') {
    const v = { '10k': 10000, '100k': 100000, '1m': 1000000 }[s.mVol];
    // Ohne Dollarzeichen: die Schwelle laeuft gegen die Volumenspalte jeder
    // Venue, und die zaehlt auf Kalshi Kontrakte statt Dollar.
    mRows = mRows.filter((m) => m.vol >= v); addChip('volume > ' + s.mVol + ' (venue unit)', { mVol: 'all' });
  }
  // Date-based filters only judge rows whose date is known; a market without
  // an end date is neither "ending soon" nor "open ended".
  if (s.mEnds !== 'all') {
    const d = { '1d': 1, '7d': 7, '30d': 30 }[s.mEnds];
    mRows = s.mEnds === 'open'
      ? mRows.filter((m) => mx(m).endsDays != null && mx(m).endsDays > 180)
      : mRows.filter((m) => mx(m).endsDays != null && mx(m).endsDays >= 0 && mx(m).endsDays <= d);
    addChip('resolves ' + (s.mEnds === 'open' ? 'far out' : 'in < ' + s.mEnds), { mEnds: 'all' });
  }
  if (s.mAge !== 'all') {
    mRows = s.mAge === '30d'
      ? mRows.filter((m) => mx(m).age != null && mx(m).age > 30)
      : mRows.filter((m) => mx(m).age != null && mx(m).age <= ({ '1d': 1, '7d': 7 })[s.mAge]);
    addChip('age ' + s.mAge, { mAge: 'all' });
  }
  if (s.mQuick === 'ending') { mRows = mRows.filter((m) => mx(m).endsDays != null && mx(m).endsDays >= 0 && mx(m).endsDays <= 14); addChip('ending soon', { mQuick: 'trending' }); }
  if (s.mQuick === 'new') { mRows = mRows.filter((m) => mx(m).age != null && mx(m).age <= 90); addChip('new markets', { mQuick: 'trending' }); }
  const kuenftig = (d) => (d != null && d >= 0 ? d : null);
  const nullLast = (a, b, asc) => {
    if (a == null && b == null) return 0;
    if (a == null) return 1;
    if (b == null) return -1;
    return asc ? a - b : b - a;
  };
  mRows = mRows.sort((a, b) => {
    if (s.marketSort === 'change') return Math.abs(b.chg) - Math.abs(a.chg);
    if (s.marketSort === 'liquidity') return b.liq - a.liq;
    // Ueberfaellige Enddaten (negativ) sortieren wie unbekannte ans Ende:
    // "resolves soonest" meint kuenftige Aufloesungen.
    if (s.marketSort === 'ending') return nullLast(kuenftig(mx(a).endsDays), kuenftig(mx(b).endsDays), true);
    if (s.marketSort === 'newest') return nullLast(mx(a).age, mx(b).age, true);
    return volOrd(b) - volOrd(a);
  });

  // Der Anteilsbalken vergleicht nur innerhalb einer Einheit: gegen einen
  // gemeinsamen Maximalwert saehe jeder Kalshi-Markt um 1/p zu gross aus.
  const maxVolJeVenue = mRows.reduce((a, m) => {
    a[m.venue] = Math.max(a[m.venue] || 0, m.vol);
    return a;
  }, {});
  const badge = mActive.length ? M + '; font-size:var(--t-micro); color:var(--on-accent); background:var(--accent); border-radius:var(--r-control); padding:var(--sp-1) var(--sp-3)' : 'display:none';
  const chevron = M + '; font-size:var(--t-lead); color:var(--ink-4); transition:transform .18s ease; transform:rotate(' + (s.marketFiltersOpen ? '90deg' : '0deg') + ')';

  return '<div>'
    + '<div style="padding:var(--sp-6) var(--sp-6) var(--sp-5); border-bottom:1px solid var(--line-2)">'
    + '<div style="display:flex; align-items:flex-end; justify-content:space-between; gap:var(--sp-6)">'
    + '<div><div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-max); color:var(--accent)">MARKETS</div>'
    + '<h1 style="font-size:var(--t-head); line-height:var(--lh-tight); margin:var(--sp-3) 0 0; font-weight:600; letter-spacing:var(--ls-flat)">Every market, one table</h1></div>'
    + '<div style="display:flex; align-items:center; gap:var(--sp-4)">'
    + '<input value="' + esc(s.marketQuery) + '" ' + T.inpEntprellt('marketQuery') + ' placeholder="Search markets…" style="background:var(--panel); border:1px solid var(--line-edge); border-radius:var(--r-control); padding:var(--sp-3) var(--sp-4); ' + M + '; font-size:var(--t-small); color:var(--text); width:230px" />'
    + '<div ' + T.act(() => T.setState({ mPlatform: 'all', mStatus: 'active', mProb: 'all', mLiq: 'all', mVol: 'all', mEnds: 'all', mAge: 'all', mExclude: [], marketCat: 'All', marketQuery: '', mQuick: 'trending', marketSort: 'volume' })) + ' class="hv-edge-strong" style="font-size:var(--t-small); color:var(--ink-3); border:1px solid var(--line-1); border-radius:var(--r-control); padding:var(--sp-3) var(--sp-4); cursor:pointer">Reset filters</div>'
    + '</div></div>'

    // Der Ueberblick zuerst: vier Kennzahlen des Ausschnitts und drei
    // Einblick-Panels (Movers, naechste Aufloesungen, 40–60¢), jede Zeile
    // oeffnet ihren Markt. Alles aus den geladenen Zeilen, nichts erfunden.
    + kpiStrip
    // Direkt unter der Kachelzeile: die Verteilung, aus der die Kacheln ihre
    // Kennzahlen ziehen. Ueber dem ganzen geladenen Ausschnitt, nicht ueber
    // der gefilterten Tabelle, sonst waere es ein Filterergebnis.
    + (preisChart ? '<div style="margin-top:var(--sp-4); max-width:700px">' + preisChart + '</div>' : '')
    + einblicke

    // VIEW (Cards / Calendar) and QUICK Saved / My positions are gone: the
    // first two had no renderer, the last two filtered on flags nothing sets.
    + '<div style="display:flex; align-items:center; gap:var(--sp-6); margin-top:var(--sp-5); flex-wrap:wrap">'
    + '<div style="display:flex; align-items:center; gap:var(--sp-3)"><span style="' + LABEL_BLOCK.replace('; margin-bottom:var(--sp-3)', '') + '">QUICK</span>'
    + [['trending','All'],['ending','Ending soon'],['new','New']].map((o) => T.opt(o[1], s.mQuick === o[0], { mQuick: o[0] })).join('') + '</div>'
    + asOfLine(s.liveAsOf)
    + '</div>'

    + '<div style="display:flex; gap:var(--sp-3); margin-top:var(--sp-5); flex-wrap:wrap">'
    + cats.map((c) => T.chip((c.toUpperCase() + ' ' + (c === 'All' ? T.markets.length : catAnzahl[c] || 0)), s.marketCat === c, { marketCat: c })).join('')
    + '</div>'

    + '<div style="border:1px solid var(--line-2); border-radius:var(--r-panel); margin-top:var(--sp-5); overflow:hidden">'
    + '<div ' + T.act(() => T.setState({ marketFiltersOpen: !s.marketFiltersOpen })) + ' class="hv-el" style="display:flex; align-items:center; justify-content:space-between; padding:var(--sp-4) var(--sp-5); background:var(--panel); cursor:pointer">'
    + '<div style="display:flex; align-items:center; gap:var(--sp-4)"><div style="font-size:var(--t-body)">All filters</div><div style="' + badge + '">' + mActive.length + '</div></div>'
    + '<div style="' + chevron + '">›</div></div>'
    + (s.marketFiltersOpen ?
      '<div style="padding:var(--sp-5); display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:var(--sp-5) var(--sp-6)">'
      + filterGroup('PLATFORM', [['all','All'],['Polymarket','Polymarket'],['Kalshi','Kalshi']].map((o) => T.opt(o[1], s.mPlatform === o[0], { mPlatform: o[0] })).join(''))
      + filterGroup('PROBABILITY', [['all','All'],['5-95','5–95%'],['20-80','20–80%'],['80','>80%'],['95','>95%'],['99','>99%']].map((o) => T.opt(o[1], s.mProb === o[0], { mProb: o[0] })).join(''))
      + filterGroup('LIQUIDITY', [['all','All'],['1k','>$1k'],['10k','>$10k'],['100k','>$100k']].map((o) => T.opt(o[1], s.mLiq === o[0], { mLiq: o[0] })).join(''))
      // Ohne Dollarzeichen: die Schwelle laeuft gegen die Volumenspalte
      // jeder Zeile, und die zaehlt auf Kalshi Kontrakte statt Dollar
      // (app/venue_units.js-Gegenstueck in util.js). Liquiditaet darueber
      // behaelt ihres, liquidity_dollars ist wirklich ein Betrag.
      + filterGroup('VOLUME 24H (VENUE UNIT)', [['all','All'],['10k','>10k'],['100k','>100k'],['1m','>1m']].map((o) => T.opt(o[1], s.mVol === o[0], { mVol: o[0] })).join(''))
      + filterGroup('RESOLVES IN', [['all','All'],['1d','<1 day'],['7d','<7 days'],['30d','<30 days'],['open','Open ended']].map((o) => T.opt(o[1], s.mEnds === o[0], { mEnds: o[0] })).join(''))
      + filterGroup('MARKET AGE', [['all','All'],['1d','<1 day'],['7d','<7 days'],['30d','>30 days']].map((o) => T.opt(o[1], s.mAge === o[0], { mAge: o[0] })).join(''))
      + '<div style="grid-column:span 2"><div style="' + LABEL_BLOCK + '">EXCLUDE CATEGORIES</div><div style="display:flex; gap:var(--sp-3); flex-wrap:wrap">'
      + cats.slice(1).map((c) => T.opt(c, s.mExclude.indexOf(c) >= 0, () => T.setState({ mExclude: s.mExclude.indexOf(c) >= 0 ? s.mExclude.filter((x) => x !== c) : s.mExclude.concat([c]) }))).join('')
      + '</div></div>'
      + '<div style="grid-column:span 2"><div style="' + LABEL_BLOCK + '">SORT BY</div><div style="display:flex; gap:var(--sp-3); flex-wrap:wrap">'
      + [['volume','Volume 24h'],['change','Biggest move'],['liquidity','Liquidity'],['ending','Ending soonest'],['newest','Newest']].map((o) => T.opt(o[1], s.marketSort === o[0], { marketSort: o[0] })).join('')
      + '</div></div>'
      + '</div>' : '')
    + '</div>'

    + '<div style="display:flex; align-items:center; gap:var(--sp-3); margin-top:var(--sp-4); flex-wrap:wrap">'
    + '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-3)">' + mRows.length + ' of ' + T.markets.length + ' markets</div>'
    + mActive.map((c) =>
      '<div ' + T.act(() => T.setState(c.reset)) + ' class="hv-edge-strong" style="' + M + '; font-size:var(--t-micro); color:var(--ink-2); border:1px solid var(--line-1); background:var(--panel-hover); border-radius:var(--r-control); padding:var(--sp-2) var(--sp-3); cursor:pointer">' + esc(c.label) + ' ✕</div>'
    ).join('')
    + '</div></div>'

    // No TREND column: the API carries a one-day change, not an intraday
    // path, and a two-point line under "TREND 24H" read as a curve. SPREAD
    // und LIQUIDITY kommen aus denselben API-Zeilen (unbekannt bleibt —).
    // The sortable heads used to say aria-pressed; that is a button's state
    // and a columnheader cannot carry it. aria-sort names the sorted column
    // instead: the descending ones sort biggest first, RESOLVES soonest first.
    + '<div role="table" aria-label="Markets">'
    + '<div role="row" style="display:grid; grid-template-columns:' + MARKT_SPALTEN + '; align-items:center; padding:var(--sp-4) var(--sp-6); border-bottom:1px solid var(--line-2); background:var(--panel); position:sticky; top:0; z-index:3; ' + LABEL + '">'
    + '<div role="columnheader">MARKET</div>'
    + '<div role="columnheader" style="text-align:right">YES</div>'
    + '<div ' + sortKopf(T, 'change', 'descending') + ' style="text-align:right; cursor:pointer; padding:var(--sp-2) 0; color:' + (s.marketSort === 'change' ? 'var(--accent)' : 'var(--ink-3)') + '">CHANGE 1D</div>'
    + '<div role="columnheader" style="text-align:right">SPREAD</div>'
    + '<div ' + sortKopf(T, 'liquidity', 'descending') + ' style="text-align:right; cursor:pointer; padding:var(--sp-2) 0; color:' + (s.marketSort === 'liquidity' ? 'var(--accent)' : 'var(--ink-3)') + '">LIQUIDITY</div>'
    + '<div ' + sortKopf(T, 'volume', 'descending') + ' style="text-align:right; cursor:pointer; padding:var(--sp-2) 0; color:' + (s.marketSort === 'volume' ? 'var(--accent)' : 'var(--ink-3)') + '">VOLUME 24H</div>'
    + '<div ' + sortKopf(T, 'ending', 'ascending') + ' style="text-align:right; cursor:pointer; padding:var(--sp-2) 0; color:' + (s.marketSort === 'ending' ? 'var(--accent)' : 'var(--ink-3)') + '">RESOLVES</div></div>'
    + mRows.map((m) => marketRowHtml(Object.assign(T.marketView(m), {
      spreadLabel: mx(m).spread != null ? mx(m).spread + '¢' : '—',
      liqLabel: m.liq ? money(m.liq) : '—',
      volShare: (maxVolJeVenue[m.venue] || 0) > 0 && m.vol > 0
        ? Math.max(2, (100 * m.vol) / maxVolJeVenue[m.venue]) : null
    }))).join('')
    + '</div>'
    + (mRows.length === 0 ?'<div style="padding:var(--sp-7); text-align:center; ' + M + '; font-size:var(--t-small); color:var(--ink-4)">No market matches that filter.</div>' : '')
    + '</div>';
}

// ---------------------------------------------------------------- flow (live tape)

// Prints ab dieser Groesse tragen eine Marke im Puls-Diagramm. Fest, nicht
// der Filter-Mindestwert: der liegt bei $2.5K und wuerde jeden Balken markieren.
const PULS_MARKE_USD = 50000;
const PULS_MARKE_LABEL = '$50K';

// Minuten als Achsenlabel: unter einer Stunde in Minuten, darueber in
// Stunden mit einer Dezimalen, wo die Rundung sonst luegen wuerde (70 min
// ist 1.2h, nicht 1h).
function dauerLabel(mins) {
  if (mins < 60) return Math.round(mins) + 'min';
  const h = +(mins / 60).toFixed(1);
  return (Number.isInteger(h) ? Math.round(h) : h) + 'h';
}

// Die gefilterten Prints in Zeit-Bins fuer das gespiegelte Puls-Diagramm.
// Bin 0 ist der aelteste; die Schrittweite waechst mit dem Fenster, damit
// hoechstens ~36 Balken entstehen. Prints ohne Zeitstempel (mins 999 aus
// mapTrade) bleiben draussen — ein Balken ohne Zeit waere eine Erfindung.
function tapePulsHtml(prints, buys, sells) {
  const valid = prints.filter((t) => t.mins < 999);
  if (valid.length < 3) return '';
  const span = Math.max(5, ...valid.map((t) => t.mins));
  const schritt = [5, 10, 15, 30, 60, 120, 240].find((sc) => Math.ceil((span + 1) / sc) <= 36) || 480;
  const nBins = Math.ceil((span + 1) / schritt);
  if (nBins < 2) return '';
  const bins = Array.from({ length: nBins }, (_, i) => {
    const bis = (nBins - 1 - i) * schritt;
    // Bin-Grenzen in Minuten, solange die Schrittweite unter einer Stunde
    // liegt — gerundete Stunden machten aus "125–120 min ago" ein "2h–2h ago".
    const zeit = bis === 0 ? 'last ' + dauerLabel(schritt)
      : schritt < 60 ? (bis + schritt) + '–' + bis + ' min ago'
        : dauerLabel(bis + schritt) + '–' + dauerLabel(bis) + ' ago';
    return { oben: 0, unten: 0, zeit };
  });
  const marken = [];
  valid.forEach((t) => {
    const i = Math.min(nBins - 1, Math.max(0, nBins - 1 - Math.floor(t.mins / schritt)));
    const kauf = (t.dir || 'BUY') === 'BUY';
    bins[i][kauf ? 'oben' : 'unten'] += t.size;
    if (t.size >= PULS_MARKE_USD) marken.push({ bin: i, oben: kauf, text: t.market + ' · ' + t.side + ' · ' + money(t.size) });
  });
  const swatch = (farbe) => '<span style="display:inline-block; width:10px; height:10px; border-radius:2px; background:' + farbe + '"></span>';
  const eintrag = (inhalt) => '<div style="display:flex; align-items:center; gap:var(--sp-3); ' + M + '; font-size:var(--t-micro); color:var(--ink-3)">' + inhalt + '</div>';
  const netto = buys - sells;
  const legende = eintrag(swatch('var(--pos)') + 'buys ' + money(buys))
    + eintrag(swatch('var(--neg)') + 'sells ' + money(sells))
    + eintrag('net <span style="color:' + (netto >= 0 ? 'var(--pos)' : 'var(--neg)') + '">' + kurzGeld(netto, true) + '</span>')
    + (marken.length ? eintrag('<span style="display:inline-block; width:8px; height:8px; border-radius:50%; background:var(--warn)"></span>print ≥ ' + PULS_MARKE_LABEL) : '');
  return spiegelZeit({
    titel: 'FLOW PULSE',
    hinweis: 'per ' + dauerLabel(schritt) + ' · filtered prints',
    legende, bins, marken,
    // Die Marke sitzt auf der Bin-Mitte; Bin i deckt (nBins-i)·schritt bis
    // (nBins-1-i)·schritt Minuten zurueck, seine Mitte liegt also bei
    // (nBins-i-0.5)·schritt. Vorher nannte die Marke die linke Kante.
    xLabels: [
      { i: 0, text: '-' + dauerLabel((nBins - 0.5) * schritt), anker: 'start' },
      { i: Math.floor((nBins - 1) / 2), text: '-' + dauerLabel((nBins - Math.floor((nBins - 1) / 2) - 0.5) * schritt), anker: 'middle' },
      { i: nBins - 1, text: 'now', anker: 'end' }
    ]
  });
}

// Wohin das Geld gerade fliesst: eine Zeile je Kategorie der gefilterten
// Prints, Balkenlaenge nach Gesamtsumme, innen der Kauf/Verkauf-Anteil.
function kategorieFlussHtml(prints, kategorieHinweis) {
  if (!prints.length) return '';
  const je = {};
  prints.forEach((t) => {
    const c = t.category || 'Other';
    const e = je[c] || (je[c] = { kauf: 0, verkauf: 0 });
    e[(t.dir || 'BUY') === 'BUY' ? 'kauf' : 'verkauf'] += t.size;
  });
  const rows = Object.keys(je)
    .map((c) => ({ cat: c, kauf: je[c].kauf, verkauf: je[c].verkauf, summe: je[c].kauf + je[c].verkauf }))
    .sort((a, b) => b.summe - a.summe);
  const max = rows[0].summe || 1;
  const seg = (anteil, farbe) => (anteil > 0
    ? '<div style="flex:' + anteil.toFixed(4) + '; height:7px; border-radius:2px; background:' + farbe + '; opacity:.85"></div>'
    : '');
  const zeilen = rows.map((r) => {
    const breite = Math.max(2, (100 * r.summe) / max);
    const kaufAnteil = r.summe ? Math.round((100 * r.kauf) / r.summe) : 0;
    return '<div style="display:grid; grid-template-columns:104px 1fr 76px 66px; gap:var(--sp-4); align-items:center; padding:var(--sp-3) var(--sp-5); border-bottom:1px solid var(--line-3)">'
      + '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-3); white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="' + esc(r.cat) + '">' + esc(r.cat.toUpperCase()) + '</div>'
      + '<div style="min-width:0"><div style="display:flex; gap:var(--sp-1); width:' + breite.toFixed(1) + '%" title="' + esc('buys ' + money(r.kauf) + ' · sells ' + money(r.verkauf)) + '">'
      + seg(r.kauf, 'var(--pos)') + seg(r.verkauf, 'var(--neg)') + '</div></div>'
      + '<div style="' + M + '; font-size:var(--t-small); text-align:right">' + kurzGeld(r.summe) + '</div>'
      + '<div style="' + M + '; font-size:var(--t-micro); text-align:right; color:var(--ink-4)">' + kaufAnteil + '% buy</div></div>';
  }).join('');
  // Die Aufteilung dieses Panels IST die Kategoriezuordnung. Kam sie nicht
  // aus dem Marktuniversum, gehoert das in die Zeile, die das Panel erklaert,
  // und nicht nur ueber die Filterleiste.
  const unterzeile = 'filtered prints · buys vs sells' + (kategorieHinweis ? ' · ' + kategorieHinweis.toLowerCase() : '');
  return insightPanel('WHERE THE MONEY FLOWS', unterzeile, zeilen, '');
}

export function renderFlow(T) {
  const s = T.state;
  if (!T.tape.length) {
    return '<div>' + seitenKopf('LIVE TAPE', 'Every large print as it lands', 'var(--accent)')
      + leerBlock('NO PRINTS', herkunftSatz(T.herkunft.tape, '/api/tape')) + '</div>';
  }
  const tapeFiltered = T.tapeFiltered();
  const tapeNotional = tapeFiltered.reduce((a, t) => a + t.size, 0);
  const tapeWallets = tapeFiltered.filter((t) => t.wallet !== '—').map((t) => t.wallet).filter((v, i, arr) => arr.indexOf(v) === i).length;
  const identifiziert = tapeFiltered.filter((t) => t.wallet !== '—').length;
  const buys = tapeFiltered.filter((t) => (t.dir || 'BUY') === 'BUY').reduce((a, t) => a + t.size, 0);
  const sells = tapeNotional - buys;
  const groesster = tapeFiltered.reduce((a, t) => (t.size > (a ? a.size : -1) ? t : a), null);
  const kurzTitel = (t) => (String(t).length > 38 ? String(t).slice(0, 37) + '…' : String(t));

  // Neue Prints gleiten ein wie im Landing-Tape: animiert wird nur, was mit
  // der letzten Poll-Antwort ankam. Der Seen-Satz haelt das volle Fenster,
  // nicht die Filtersicht — ein Filterklick spielt keine Eintritte nach.
  const schluessel = (t) => [t.ts || '', t.walletAddress || t.wallet, t.marketKey, t.side, t.size].join('|');
  const erste = !(T._flowGesehen instanceof Set);
  const gesehen = erste ? new Set() : T._flowGesehen;
  T._flowGesehen = new Set(T.tape.map(schluessel));

  const fensterZeile = fensterSatz(tapeFenster(tapeFiltered));
  const puls = tapePulsHtml(tapeFiltered, buys, sells);
  const kategorieHinweis = categorySourceLabel(s.tapeCategories);
  const katFluss = kategorieFlussHtml(tapeFiltered, kategorieHinweis);
  const grafiken = puls || katFluss
    ? '<div style="display:grid; grid-template-columns:' + (puls && katFluss ? 'minmax(0,1.65fr) minmax(0,1fr)' : '1fr') + '; gap:var(--sp-4); padding:var(--sp-5) var(--sp-6); border-bottom:1px solid var(--line-2)">'
      + puls + katFluss + '</div>'
    : '';

  return '<div>'
    + '<div style="padding:var(--sp-6) var(--sp-6) var(--sp-5); border-bottom:1px solid var(--line-2)">'
    + '<div style="display:flex; align-items:flex-end; justify-content:space-between; gap:var(--sp-6)">'
    + '<div><div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-max); color:var(--accent)">LIVE TAPE</div>'
    + '<h1 style="font-size:var(--t-head); line-height:var(--lh-tight); margin:var(--sp-3) 0 0; font-weight:600; letter-spacing:var(--ls-flat)">Every large print as it lands</h1></div>'
    + '<div style="display:flex; align-items:center; gap:var(--sp-4)">'
    + asOfLine(s.tapeAsOf || s.liveAsOf)
    + '<input value="' + esc(s.tapeQuery) + '" ' + T.inpEntprellt('tapeQuery') + ' placeholder="market, wallet, trader…" style="background:var(--panel); border:1px solid var(--line-edge); border-radius:var(--r-control); padding:var(--sp-3) var(--sp-4); ' + M + '; font-size:var(--t-small); color:var(--text); width:250px" />'
    + '</div></div>'
    + '<div style="margin-top:var(--sp-5)">' + filterGroup('CATEGORY', catChipRow(T, T.tape, 'category', 'tapeCat', s.tapeCat))
    // Steht ueber der Kategorieleiste, weil sie das erste ist, was die Zeile
    // betrifft: ohne das Marktuniversum sind die Chips grober und "Other"
    // groesser, und beides waere sonst von einer echten Verteilung nicht zu
    // unterscheiden.
    + (kategorieHinweis
      ? '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:var(--warn); margin-top:var(--sp-3)">' + esc(kategorieHinweis) + '</div>'
      : '')
    + '</div>'
    + '<div style="display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:var(--sp-5); margin-top:var(--sp-5)">'
    + filterGroup('MINIMUM SIZE', [
      T.chip('≥ $2.5K', s.tapeMin === 2500 && !s.tapeTracked, { tapeMin: 2500, tapeTracked: false }),
      T.chip('≥ $10K', s.tapeMin === 10000 && !s.tapeTracked, { tapeMin: 10000, tapeTracked: false })
    ].join(''))
    + filterGroup('PLATFORM', [['all','All'],['Polymarket','Polymarket'],['Kalshi','Kalshi']].map((o) => T.opt(o[1], s.tapePlatform === o[0], { tapePlatform: o[0] })).join(''))
    + filterGroup('SIDE', [['all','All'],['BUY','Buys'],['SELL','Sells']].map((o) => T.opt(o[1], s.tapeSide === o[0], { tapeSide: o[0] })).join(''))
    + filterGroup('OUTCOME', [['all','All'],['Yes','Yes'],['No','No']].map((o) => T.opt(o[1], s.tapeOutcome === o[0], { tapeOutcome: o[0] })).join(''))
    + '</div></div>'

    + '<div style="display:grid; grid-template-columns:repeat(4,1fr); border-bottom:1px solid var(--line-2)">'
    + kpiCell('PRINTS SHOWN', num(tapeFiltered.length),
      'of ' + num(T.tape.length) + ' in the tape window', true)
    + kpiCell('TOTAL MOVED', money(tapeNotional),
      tapeNotional ? Math.round((100 * buys) / tapeNotional) + '% buys · net ' + kurzGeld(buys - sells, true) : 'nothing passes the filters', true)
    + kpiCell('WALLETS INVOLVED', num(tapeWallets),
      tapeWallets ? num(identifiziert) + ' prints from identified wallets' : 'Kalshi publishes no wallet identities', true)
    + kpiCell('BIGGEST PRINT', groesster ? money(groesster.size) : '—',
      groesster ? esc(kurzTitel(groesster.market)) : 'no print passes the filters', false)
    + '</div>'

    // Ueber welche Spanne diese vier Zahlen summiert wurden — und dass die
    // Spanne je Venue verschieden ist, weil beide gleich viele Zeilen
    // bekommen (api_views.balanced_head), Kalshi aber viel schneller druckt.
    + (fensterZeile ? '<div style="padding:var(--sp-3) var(--sp-6); border-bottom:1px solid var(--line-2); ' + M + '; font-size:var(--t-micro); color:var(--ink-4)">'
      + '<span style="letter-spacing:var(--ls-caps-strong); color:var(--ink-3); margin-right:var(--sp-3)">SUMMED OVER</span>' + esc(fensterZeile) + '</div>' : '')

    + grafiken

    + '<div role="table" aria-label="Live tape">'
    + '<div role="row" style="display:grid; grid-template-columns:96px 160px 1fr 110px 84px 90px 110px 96px; padding:var(--sp-4) var(--sp-6); border-bottom:1px solid var(--line-2); background:var(--panel); position:sticky; top:0; z-index:3; ' + LABEL + '">'
    + '<div role="columnheader">TIME</div><div role="columnheader">WALLET</div><div role="columnheader">MARKET</div><div role="columnheader">CATEGORY</div><div role="columnheader">SIDE</div><div role="columnheader" style="text-align:right">PRICE</div><div role="columnheader" style="text-align:right">SIZE</div><div role="columnheader" style="text-align:right">VENUE</div></div>'
    + (tapeFiltered.length ? '' : leerZeile('No print in the tape window passes the current filters (size, category, side).'))
    + tapeFiltered.map((t0) => {
      const t = T.tapeRowView(t0);
      const neu = !erste && !gesehen.has(schluessel(t0));
      // Only a print of a loaded market opens the drawer; the other rows are
      // plain rows, not pointers that lead nowhere.
      const klickbar = t.act && t.clickable !== false;
      return '<div ' + zeilenAct(klickbar ? t.act : '') + ' class="' + (klickbar ? 'hv-panel' : '') + (neu ? ' tape-in' : '') + '" style="display:grid; grid-template-columns:96px 160px 1fr 110px 84px 90px 110px 96px; align-items:center; padding:var(--sp-4) var(--sp-6); border-bottom:1px solid var(--line-3); ' + M + '; font-size:var(--t-small); ' + (klickbar ? 'cursor:pointer; ' : '') + '">'
        + '<div role="cell" style="color:var(--ink-4)">' + esc(t.ago) + '</div>'
        + '<div role="cell" style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="' + esc(t.wallet) + '">' + esc(t.wallet) + '</div>'
        + '<div role="cell" style="font-family:var(--font-ui); font-size:var(--t-body); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; padding-right:var(--sp-4)" title="' + esc(t.market) + '">' + esc(t.market) + '</div>'
        + '<div role="cell" style="font-size:var(--t-micro); color:var(--ink-4)">' + esc(t.category || 'Other') + '</div>'
        + '<div role="cell" style="' + t.sideStyle + '">' + esc(t.side) + '</div>'
        + '<div role="cell" style="text-align:right">' + esc(t.price) + '</div>'
        + '<div role="cell" style="text-align:right">' + t.size + '</div>'
        + '<div role="cell" style="text-align:right; color:var(--ink-3); font-size:var(--t-micro)">' + esc(t.venue) + '</div></div>';
    }).join('')
    + '</div>'
    + '</div>';
}

// ---------------------------------------------------------------- cross-venue

// The honesty gate as words, used by both the empty block and the caption.
export const CROSS_GATE_TEXT = 'similarity ≥ 0.5, volume on both venues';

// Warum ein Paar gar keine Zahl bekommt, in Worten. Die Schluessel kommen aus
// app/cross_pairs.py; ein unbekannter faellt auf den Rohwert zurueck, statt
// die Zeile verschwinden zu lassen.
const CROSS_VERDICT_TEXT = {
  opposed: 'ask in opposite directions',
  different_question: 'ask different questions'
};

// Fuer wie viele Stueck die Netto-Spanne gilt, und ob das gemessen ist.
// Ohne Buchabfrage sind es die 100 Stueck, auf denen die Gebuehrenkurven
// ausgewertet werden: eine Annahme ueber die Spitze des Buchs, keine Tiefe.
export function crossSizeLabel(c) {
  if (!c) return '';
  if (c.depthChecked) return c.size ? num(c.size) + ' at the touch' : 'no size at the touch';
  return c.net == null ? '' : 'size not checked';
}

// Die Paare, die der Paar-Check aussortiert hat: gezaehlt, benannt, und
// seit dem Universum-Fix auch gelistet — wochenlang bestand die Seite nur
// aus dem leeren Gate, und die Fast-Paare sind das, was es zu sehen gibt.
// Jede Seite traegt ihren eigenen Kurs (eine Tatsache ueber ihren Markt);
// was bewusst fehlt, sind Luecke, Spanne und Netto: zwischen zwei
// verschiedenen Fragen ist auch die Luecke keine Aussage.
function crossSuppressedBlock(sup) {
  if (!sup || !sup.total) return '';
  const nach = sup.by_verdict || {};
  const gruende = Object.keys(nach)
    .map((k) => num(nach[k]) + ' ' + (CROSS_VERDICT_TEXT[k] || k))
    .join(', ');
  const beispiele = sup.examples || [];
  const cent = (v) => (v == null ? '—' : v + '¢');
  const kurz = (t, n) => { const s = String(t || ''); return s.length > n ? s.slice(0, n - 1) + '…' : s; };
  const rest = sup.total - beispiele.length;
  // Ein Kurs-Register fuer den ganzen Block: Venue-Kuerzel links, Preis
  // rechtsbuendig, beide auf einer festen Spalte, damit die Quotes wie in
  // einem Orderbuch untereinander stehen und die Titel eine Fluchtlinie
  // teilen. Preiszelle als space-between, sonst wandert das Kuerzel mit
  // der Ziffernbreite.
  const preisZelle = (tag, wert, farbe) =>
    '<div style="' + M + '; font-size:var(--t-small); line-height:var(--lh-snug); display:flex; justify-content:space-between; align-items:baseline; gap:var(--sp-2)">'
    + '<span style="font-size:var(--t-micro); color:var(--ink-4)">' + tag + '</span>'
    + '<span style="color:' + farbe + '; font-variant-numeric:tabular-nums">' + cent(wert) + '</span></div>';
  return '<div style="border:1px solid var(--line-2); border-radius:var(--r-panel); margin-top:var(--sp-5); padding:var(--sp-5)">'
    + '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:var(--warn)">MATCHED BUT NOT PRICED · ' + num(sup.total) + '</div>'
    + '<div style="font-size:var(--t-small); color:var(--ink-3); margin-top:var(--sp-3); line-height:var(--lh-prose)">'
    + esc(gruende) + '. Two titles can share every word and still be two questions: “above $120,000” against “below $120,000” scores 0.78 on the matcher. '
    + 'A basket across a pair like that pays 2.00 in one state and 0.00 in the other, so its spread is a sign error, not an opportunity. '
    + 'Each side shows its own price; the pair carries no gap and no spread, because between two different questions the gap says nothing.</div>'
    + (beispiele.length
      ? '<div style="margin-top:var(--sp-4)">' + beispiele.map((b) => {
        const opposed = b.verdict === 'opposed';
        return '<div style="border-top:1px solid var(--line-3); padding:var(--sp-3) 0; display:grid; grid-template-columns:68px minmax(0,1fr) auto; column-gap:var(--sp-4); row-gap:var(--sp-1)">'
          + '<div style="grid-column:1; grid-row:1">' + preisZelle('PM', b.pm, 'var(--accent)') + '</div>'
          + '<div style="grid-column:2; grid-row:1; font-size:var(--t-small); line-height:var(--lh-snug)">' + esc(kurz(b.event, 120)) + '</div>'
          + '<div style="grid-column:3; grid-row:1 / span 2; text-align:right; align-self:start">'
          + '<div style="' + M + '; font-size:var(--t-micro); line-height:var(--lh-snug); color:' + (opposed ? 'var(--warn)' : 'var(--ink-3)') + '">' + esc(CROSS_VERDICT_TEXT[b.verdict] || b.verdict || '') + '</div>'
          + (b.sim ? '<div style="' + M + '; font-size:var(--t-micro); line-height:var(--lh-snug); color:var(--ink-4); margin-top:var(--sp-1)">similarity ' + Number(b.sim).toFixed(2) + '</div>' : '')
          + '</div>'
          + '<div style="grid-column:1; grid-row:2">' + preisZelle('KS', b.ks, 'var(--info)') + '</div>'
          + '<div style="grid-column:2; grid-row:2; font-size:var(--t-small); line-height:var(--lh-snug)">' + esc(kurz(b.other, 120)) + '</div>'
          + (b.why ? '<div style="grid-column:2 / span 2; grid-row:3; ' + M + '; font-size:var(--t-micro); color:var(--ink-4); margin-top:var(--sp-1); line-height:var(--lh-snug)">' + esc(b.why) + '</div>' : '')
          + '</div>';
      }).join('')
      + (rest > 0 ? '<div style="border-top:1px solid var(--line-3); ' + M + '; font-size:var(--t-micro); color:var(--ink-4); padding-top:var(--sp-3)">+ ' + num(rest) + ' more suppressed pairs not listed</div>' : '')
      + '</div>'
      : '')
    + '</div>';
}

function crossGateBlock(T) {
  const microIdx = T.studies.findIndex((st) => st.tab === 'Microstructure');
  // Auch mit leerem Gate hat die Antwort meist etwas zu zeigen: die
  // Fast-Paare, die der Paar-Check verworfen hat. Ohne sie sieht die Seite
  // wochenlang gleich aus und niemand kann pruefen, ob das Gate recht hat.
  const sup = (T.liveData.cross || {}).suppressed;
  return '<div style="padding:var(--sp-6)">'
    + '<div style="background:var(--panel); border:1px solid var(--line-2); border-radius:var(--r-panel); padding:var(--sp-6); max-width:760px">'
    + '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:var(--warn)">NO PAIR CLEARS THE GATE</div>'
    + '<div style="font-size:var(--t-body); color:var(--ink-3); margin-top:var(--sp-3); line-height:var(--lh-prose)">No cross-venue pair clears the match gate right now (' + CROSS_GATE_TEXT + '). '
    + 'See studies 08 and 11: the two 79¢/64¢ \'edges\' were mismatched questions.</div>'
    + (microIdx >= 0 && T.goStudy
      ? '<div ' + T.act(() => T.goStudy(microIdx)) + ' class="hv-accent" style="' + M + '; font-size:var(--t-micro); color:var(--info); margin-top:var(--sp-4); cursor:pointer">Open the microstructure report (#research/microstructure) →</div>'
      : '<a href="#research/microstructure" style="' + M + '; font-size:var(--t-micro); display:inline-block; margin-top:var(--sp-4)">Open the microstructure report →</a>')
    + '</div>'
    + '<div style="max-width:760px">' + crossSuppressedBlock(sup) + '</div>'
    + '</div>';
}

export function renderCross(T) {
  const s = T.state;
  const hk = T.herkunft.cross;
  if (!T.crossPairs.length) {
    // Three empty states, all named: request still running, request failed,
    // request answered and nothing passed the gate.
    let body;
    if (!hk) {
      body = '<div style="padding:var(--sp-6)">'
        + '<div style="background:var(--panel); border:1px solid var(--line-2); border-radius:var(--r-panel); padding:var(--sp-6); max-width:760px">'
        + '<div style="display:flex; align-items:center; gap:var(--sp-4)">'
        + '<span style="width:7px; height:7px; border-radius:50%; background:var(--warn); display:inline-block"></span>'
        + '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:var(--warn)">MATCHING PAIRS ACROSS VENUES…</div></div>'
        // Ohne Dauer liest sich der pulsierende Punkt wie eine kaputte Seite.
        // Er ist keine: der erste Aufruf blaettert beide Boersen durch.
        + '<div style="font-size:var(--t-body); color:var(--ink-4); margin-top:var(--sp-3); line-height:var(--lh-prose)">This is a live scan, not a stored file: /api/cross pages both venues (12 event pages on the Kalshi side alone), scores every title pair and re-quotes the best rows against both books — one to two minutes on a cold cache, seconds on a warm one. The gate then keeps only ' + CROSS_GATE_TEXT + '. If it fails you will see the error and a retry here, not this spinner.</div>'
        + '</div></div>';
    } else if (hk.quelle === 'fehler') {
      body = leerBlock('NO PAIRS', herkunftSatz(hk, '/api/cross'))
        + (T.neuLaden ? '<div style="padding:0 var(--sp-6) var(--sp-6)"><div ' + T.act(() => T.neuLaden('cross', 'cross')) + ' class="hv-edge-strong" style="display:inline-block; ' + M + '; font-size:var(--t-micro); color:var(--ink-2); border:1px solid var(--line-1); border-radius:var(--r-control); padding:var(--sp-3) var(--sp-4); cursor:pointer">Try again</div></div>' : '');
    } else {
      body = crossGateBlock(T);
    }
    // The paper scanner's section stands under every state of the pair
    // scan: its file is a separate, small request (liveData.arbScan) and
    // does not wait for the slow scan or share its failure.
    return '<div>' + seitenKopf('CROSS-VENUE', 'The same question, two prices', 'var(--info)') + body + renderArbScanAbschnitt(T.liveData.arbScan) + '</div>';
  }
  // Local filters can only tighten what the server let through.
  let cRows = T.crossPairs.filter((c) => Math.abs(c.pm - c.ks) >= s.crossMinGap && c.sim >= s.crossSim && c.pmVolUsd >= s.crossPmVol && c.ksVolContracts >= s.crossKsVol);
  cRows = cRows.filter((c) => c.pm >= s.crossMinPrice && c.pm <= s.crossMaxPrice && c.ks >= s.crossMinPrice && c.ks <= s.crossMaxPrice);
  if (s.crossQuery.trim()) {
    const cq = s.crossQuery.trim().toLowerCase();
    cRows = cRows.filter((c) => c.event.toLowerCase().indexOf(cq) >= 0 || c.cat.toLowerCase().indexOf(cq) >= 0);
  }
  if (s.crossLower !== 'any') cRows = cRows.filter((c) => (c.pm < c.ks ? 'Polymarket' : 'Kalshi') === s.crossLower);
  cRows = cRows.sort((a, b) => Math.abs(b.pm - b.ks) - Math.abs(a.pm - a.ks)).slice(0, s.crossMaxPairs);
  const gaps = cRows.map((c) => Math.abs(c.pm - c.ks)).sort((a, b) => a - b);
  // Die Luecke zwischen zwei Mittelkursen ist keine Spanne, die man nehmen
  // kann: gekauft wird zum Brief, verkauft zum Geld, und beide Venues
  // nehmen eine Gebuehr. Wie viele Paare danach ueberhaupt noch etwas
  // uebrig lassen, ist die einzige Zahl hier, die ueber Geld spricht.
  const netKnown = cRows.filter((c) => c.net != null).length;
  const netPositive = cRows.filter((c) => c.net != null && c.net > 0).length;
  const sims = cRows.map((c) => c.sim).sort((a, b) => a - b);
  const medianSim = sims.length ? sims[Math.floor(sims.length / 2)] : 0;
  const cl = T.liveData.cross || {};
  const gateNote = cl.candidates_before_gate != null
    ? num(T.crossPairs.length) + ' of ' + num(cl.candidates_before_gate) + ' candidate pairs clear the gate (' + CROSS_GATE_TEXT + ')'
    : num(T.crossPairs.length) + ' pairs clear the gate (' + CROSS_GATE_TEXT + ')';

  const activeChips = [].concat(
    s.crossQuery.trim() ? ['search: ' + s.crossQuery.trim()] : [],
    s.crossSim > 0.5 ? ['similarity ≥ ' + s.crossSim.toFixed(2)] : [],
    s.crossMinGap > 0 ? ['gap ≥ ' + s.crossMinGap.toFixed(1) + '¢'] : [],
    s.crossPmVol > 0 ? ['Polymarket volume > $' + num(s.crossPmVol)] : [],
    s.crossKsVol > 0 ? ['Kalshi volume > ' + num(s.crossKsVol) + ' contracts'] : [],
    s.crossLower !== 'any' ? ['cheaper on ' + s.crossLower] : [],
    (s.crossMinPrice !== 0 || s.crossMaxPrice !== 100) ? ['yes price ' + s.crossMinPrice + '–' + s.crossMaxPrice + '¢'] : []
  );

  const stepGroup = (label, valueLabel, onDown, onUp) =>
    '<div><div style="' + LABEL_BLOCK + '">' + label + '</div>'
    + '<div style="display:flex; align-items:center; gap:var(--sp-3)">'
    + '<div ' + T.act(onDown) + ' class="hv-edge-max hv-white" style="width:26px; height:30px; flex:none; border:1px solid var(--line-1); border-radius:var(--r-control); display:flex; align-items:center; justify-content:center; ' + M + '; font-size:var(--t-body); color:var(--ink-2); cursor:pointer">−</div>'
    + '<div style="flex:1; background:var(--panel); border:1px solid var(--line-1); border-radius:var(--r-control); padding:var(--sp-3); ' + M + '; font-size:var(--t-small); text-align:center">' + esc(valueLabel) + '</div>'
    + '<div ' + T.act(onUp) + ' class="hv-edge-max hv-white" style="width:26px; height:30px; flex:none; border:1px solid var(--line-1); border-radius:var(--r-control); display:flex; align-items:center; justify-content:center; ' + M + '; font-size:var(--t-body); color:var(--ink-2); cursor:pointer">+</div>'
    + '</div></div>';

  return '<div>'
    + '<div style="padding:var(--sp-6) var(--sp-6) var(--sp-5); border-bottom:1px solid var(--line-2)">'
    + '<div style="display:flex; align-items:flex-end; justify-content:space-between; gap:var(--sp-6)">'
    + '<div><div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-max); color:var(--info)">CROSS-VENUE</div>'
    + '<h1 style="font-size:var(--t-head); line-height:var(--lh-tight); margin:var(--sp-3) 0 0; font-weight:600; letter-spacing:var(--ls-flat)">The same question, two prices</h1></div>'
    + '<div style="display:flex; align-items:center; gap:var(--sp-4)">'
    + asOfLine(cl.as_of)
    + '<input value="' + esc(s.crossQuery) + '" ' + T.inpEntprellt('crossQuery') + ' placeholder="bitcoin, fed, election…" style="background:var(--panel); border:1px solid var(--line-edge); border-radius:var(--r-control); padding:var(--sp-3) var(--sp-4); ' + M + '; font-size:var(--t-small); color:var(--text); width:230px" />'
    + '<div ' + T.act(() => T.setState({ crossQuery: '', crossSim: 0.5, crossMaxPairs: 50, crossMinGap: 0, crossLower: 'any', crossPmVol: 0, crossKsVol: 0, crossMinPrice: 0, crossMaxPrice: 100 })) + ' class="hv-edge-strong" style="font-size:var(--t-small); color:var(--ink-3); border:1px solid var(--line-1); border-radius:var(--r-control); padding:var(--sp-3) var(--sp-4); cursor:pointer">Reset filters</div>'
    + '</div></div>'
    + '<div style="font-size:var(--t-body); color:var(--ink-4); margin-top:var(--sp-4); max-width:760px">Matched by title similarity, not by ticker. ' + esc(gateNote) + '. GAP is the distance between the two mid prices, and nobody trades a mid. NET OF FEES prices the basket that would capture it (buy the yes side at the ask, buy the other side at the other venue&#39;s ask) and subtracts both venues&#39; taker fee curves. The top ' + num(cl.depth_rows || 12) + ' rows by net are re-quoted against both order books, so their number holds for the size shown beneath it; the rest price the touch at the fee clip of 100 and say so. Settlement rules and resolution sources still differ, and two matched titles can still be two different questions (studies 08 and 11).</div>'
    + crossSuppressedBlock(cl.suppressed)

    + '<div style="border:1px solid var(--line-2); border-radius:var(--r-panel); margin-top:var(--sp-5); padding:var(--sp-5); display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:var(--sp-5)">'
    + stepGroup('MIN SIMILARITY (GATE 0.50)', s.crossSim.toFixed(2), () => T.setState({ crossSim: Math.max(0.5, +(s.crossSim - 0.02).toFixed(2)) }), () => T.setState({ crossSim: Math.min(0.9, +(s.crossSim + 0.02).toFixed(2)) }))
    + stepGroup('MAX PAIRS', String(s.crossMaxPairs), () => T.setState({ crossMaxPairs: Math.max(10, s.crossMaxPairs - 10) }), () => T.setState({ crossMaxPairs: Math.min(150, s.crossMaxPairs + 10) }))
    + stepGroup('MIN GAP (¢)', s.crossMinGap.toFixed(1) + '¢', () => T.setState({ crossMinGap: Math.max(0, s.crossMinGap - 0.5) }), () => T.setState({ crossMinGap: s.crossMinGap + 0.5 }))
    + '<div><div style="' + LABEL_BLOCK + '">LOWER YES ON</div><div style="display:flex; gap:var(--sp-3)">'
    + [['any','Any'],['Polymarket','Polymarket'],['Kalshi','Kalshi']].map((o) => T.opt(o[1], s.crossLower === o[0], { crossLower: o[0] })).join('')
    + '</div></div>'
    + stepGroup('MIN POLYMARKET VOLUME', s.crossPmVol ? '$' + num(s.crossPmVol) : 'any', () => T.setState({ crossPmVol: Math.max(0, s.crossPmVol - 250000) }), () => T.setState({ crossPmVol: s.crossPmVol + 250000 }))
    + stepGroup('MIN KALSHI VOLUME (CONTRACTS)', s.crossKsVol ? num(s.crossKsVol) : 'any', () => T.setState({ crossKsVol: Math.max(0, s.crossKsVol - 100000) }), () => T.setState({ crossKsVol: s.crossKsVol + 100000 }))
    + stepGroup('MIN YES PRICE', s.crossMinPrice + '¢', () => T.setState({ crossMinPrice: Math.max(0, s.crossMinPrice - 5) }), () => T.setState({ crossMinPrice: Math.min(s.crossMaxPrice, s.crossMinPrice + 5) }))
    + stepGroup('MAX YES PRICE', s.crossMaxPrice + '¢', () => T.setState({ crossMaxPrice: Math.max(s.crossMinPrice, s.crossMaxPrice - 5) }), () => T.setState({ crossMaxPrice: Math.min(100, s.crossMaxPrice + 5) }))
    + '</div>'

    + '<div style="display:flex; align-items:center; gap:var(--sp-3); margin-top:var(--sp-4); flex-wrap:wrap">'
    + activeChips.map((c) => '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-2); border:1px solid var(--line-1); background:var(--panel-hover); border-radius:var(--r-control); padding:var(--sp-2) var(--sp-3)">' + esc(c) + '</div>').join('')
    + '</div></div>'

    + '<div style="display:grid; grid-template-columns:repeat(4,1fr); border-bottom:1px solid var(--line-2)">'
    + kpi({ form: 'band', trenner: true, label: 'PAIRS SHOWN', wert: cRows.length })
    + kpi({ form: 'band', trenner: true, label: 'LARGEST GAP', farbe: 'var(--warn)', wert: (gaps.length ? gaps[gaps.length - 1] + '¢' : '—') })
    + kpi({ form: 'band', trenner: true, label: 'MEDIAN SIMILARITY', wert: (medianSim ? medianSim.toFixed(2) : '—') })
    + kpi({ form: 'band', label: 'POSITIVE NET OF FEES', farbe: netPositive ? 'var(--pos)' : 'var(--ink-3)', wert: netPositive + ' of ' + netKnown })
    + '</div>'

    + '<div role="table" aria-label="Cross-venue pairs">'
    + '<div role="row" style="display:grid; grid-template-columns:1fr 104px 104px 84px 108px 124px 112px; padding:var(--sp-4) var(--sp-6); border-bottom:1px solid var(--line-2); background:var(--panel); position:sticky; top:0; z-index:3; ' + LABEL + '">'
    // Ein Markt, zwei Volumina, zwei Einheiten. Die Summe der beiden stand
    // hier als eine Zahl mit Dollarzeichen und war keine: Kalshis Volumen
    // zaehlt Kontrakte (app/venue_units.py).
    + '<div role="columnheader">EVENT</div><div role="columnheader" style="text-align:right">POLYMARKET</div><div role="columnheader" style="text-align:right">KALSHI</div><div role="columnheader" style="text-align:right">GAP</div><div role="columnheader" style="text-align:right">PM VOL 24H</div><div role="columnheader" style="text-align:right">KALSHI VOL 24H</div><div role="columnheader" style="text-align:right">NET OF FEES</div></div>'
    + cRows.map((c) => {
      const g = Math.abs(c.pm - c.ks);
      const gapStyle = M + '; font-size:var(--t-body); text-align:right; color:' + (g >= 5 ? 'var(--warn)' : g >= 3 ? 'var(--text)' : 'var(--ink-4)');
      // Die letzte Spalte hiess HELD FOR und war in jeder Zeile ein Strich:
      // der Server hat nie etwas anderes geliefert. Hier steht jetzt die
      // einzige Zahl der Tabelle, die als Vorteil gelesen werden darf.
      const netFarbe = c.net == null ? 'var(--ink-4)' : c.net > 0 ? 'var(--pos)' : 'var(--ink-4)';
      const netLabel = c.net == null ? '—' : (c.net > 0 ? '+' : '') + c.net.toFixed(1) + '¢';
      const sizeLabel = crossSizeLabel(c);
      return '<div role="row" style="display:grid; grid-template-columns:1fr 104px 104px 84px 108px 124px 112px; align-items:center; padding:var(--sp-4) var(--sp-6); border-bottom:1px solid var(--line-3)">'
        + '<div role="cell" style="padding-right:var(--sp-6)"><div style="font-size:var(--t-body); line-height:var(--lh-tight)">' + esc(c.event) + '</div>'
        + '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-3); margin-top:var(--sp-2)">' + esc(c.cat) + ' · similarity ' + c.sim.toFixed(2) + '</div></div>'
        + '<div role="cell" style="' + M + '; font-size:var(--t-body); text-align:right; color:var(--accent)">' + c.pm + '¢</div>'
        + '<div role="cell" style="' + M + '; font-size:var(--t-body); text-align:right; color:var(--info)">' + c.ks + '¢</div>'
        + '<div role="cell" style="' + gapStyle + '">' + g + '¢</div>'
        + '<div role="cell" style="' + M + '; font-size:var(--t-small); text-align:right; color:var(--ink-3)">' + volume(c.pmVolUsd, 'Polymarket') + '</div>'
        + '<div role="cell" style="' + M + '; font-size:var(--t-small); text-align:right; color:var(--ink-3)" title="Kalshi reports volume as a contract count; one contract settles for $1, so this is not a dollar figure">' + volume(c.ksVolContracts, 'Kalshi') + '</div>'
        + '<div role="cell" style="text-align:right" title="' + esc(c.net == null ? 'no two-sided quote on both venues' : (c.dir || '') + ' · executable ' + (c.gross == null ? '—' : c.gross.toFixed(1) + '¢') + ' minus a fee threshold of ' + (c.band == null ? '—' : c.band.toFixed(1) + '¢')) + '">'
        + '<div style="' + M + '; font-size:var(--t-body); color:' + netFarbe + '">' + netLabel + '</div>'
        // Eine Spanne fuer drei Kontrakte ist kein Geschaeft ueber hundert.
        // Ohne diese Zeile stand die Zahl fuer eine Groesse da, die niemand
        // nachgeschlagen hatte.
        + (sizeLabel ? '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-4); margin-top:var(--sp-1); line-height:var(--lh-tight)">' + esc(sizeLabel) + '</div>' : '')
        + '</div></div>';
    }).join('')
    + '</div>'
    + (cRows.length === 0 ? '<div style="padding:var(--sp-7); text-align:center; ' + M + '; font-size:var(--t-small); color:var(--ink-4)">No pair passes the local filters; loosen a stepper above.</div>' : '')
    // Paper scanner: executable edge — the scanner's file, laid out under
    // the pair comparison (arb_scan_page.js).
    + renderArbScanAbschnitt(T.liveData.arbScan)
    + '</div>';
}

// ---------------------------------------------------------------- resolved
export function renderResolved(T) {
  const s = T.state;
  const live = T.liveData.resolved;
  // Ohne Antwort keine Zeilen. Hier lagen sechs erfundene Maerkte samt
  // Ausgang, und die Kennzahl darueber hiess "how far the crowd was off" —
  // eine Fehlermessung an Zahlen, die niemand gemessen hat.
  //
  // Die erfundenen Zeilen sind laengst weg, die Kennzahl blieb, und mit
  // echten Daten war sie strukturell null: der Feed liefert fuer einen
  // abgerechneten Markt nur noch den Abrechnungspreis, und der Ausgang wird
  // aus genau diesem Preis abgeleitet. Ueber fuenfzig echte Zeilen: fuenfzig
  // Mal null. Jetzt steht der Abrechnungspreis als das da, was er ist, und
  // eine Kachel zeigt, wie viele Zeilen ueberhaupt nicht bei 0 oder 100
  // liegen — der Nachweis am Bildschirm statt einer Behauptung im Text.
  const resAll = live && live.rows ? live.rows : [];
  if (!resAll.length) {
    return '<div>' + seitenKopf('RESOLVED', 'How the last questions ended', 'var(--accent)')
      + leerBlock('NOTHING SETTLED HERE', herkunftSatz(
        live ? { quelle: live._quelle === 'fehler' ? 'fehler' : 'leer', fehler: live._fehler } : null,
        '/api/resolved')) + '</div>';
  }
  let resRows = resAll.filter((r) => {
    if (s.resAnswer !== 'all' && (s.resAnswer === 'yes') !== r.yes) return false;
    if (s.resWindow !== 'all' && r.hours > Number(s.resWindow)) return false;
    if (s.resQuery.trim() && r.title.toLowerCase().indexOf(s.resQuery.trim().toLowerCase()) < 0) return false;
    return true;
  });
  const volValue = (v) => parseFloat(String(v).replace(/[$,]/g, '')) * (String(v).indexOf('m') >= 0 ? 1e6 : String(v).indexOf('k') >= 0 ? 1e3 : 1) || 0;
  resRows = resRows.sort((a, b) => (s.resSort === 'volume' ? volValue(b.vol) - volValue(a.vol) : a.hours - b.hours));
  // Wie viele der gezeigten Zeilen nicht bei 0 oder 100 abgerechnet haben.
  // Ist das null, steckt in diesen Daten ueberhaupt keine Abweichung
  // zwischen Menge und Ausgang, und die Kachel zeigt das, statt dass
  // die Seite es behauptet.
  const zwischen = resRows.filter((r) => r.settled_price > 0 && r.settled_price < 100).length;
  const frisch = resRows.filter((r) => r.hours <= 24).length;
  const kpis = [
    { label: 'MARKETS SHOWN', value: String(resRows.length) },
    { label: 'ENDED YES', value: resRows.filter((r) => r.yes).length + ' of ' + resRows.length },
    { label: 'SETTLED IN THE LAST 24 H', value: frisch + ' of ' + resRows.length },
    { label: 'PRICE NOT 0 OR 100', value: zwischen + ' of ' + resRows.length, amber: zwischen === 0 }
  ];

  return '<div>'
    + '<div style="padding:var(--sp-6) var(--sp-6) var(--sp-5); border-bottom:1px solid var(--line-2)">'
    + '<div style="display:flex; align-items:flex-end; justify-content:space-between; gap:var(--sp-6)">'
    + '<div><div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-max); color:var(--accent)">RESOLVED</div>'
    + '<h1 style="font-size:var(--t-head); line-height:var(--lh-tight); margin:var(--sp-3) 0 0; font-weight:600; letter-spacing:var(--ls-flat)">How the last questions ended</h1></div>'
    + '<input value="' + esc(s.resQuery) + '" ' + T.inpEntprellt('resQuery') + ' placeholder="Search resolved markets…" style="background:var(--panel); border:1px solid var(--line-edge); border-radius:var(--r-control); padding:var(--sp-3) var(--sp-4); ' + M + '; font-size:var(--t-small); color:var(--text); width:250px" />'
    + '</div>'
    + '<div style="font-size:var(--t-body); color:var(--ink-4); margin-top:var(--sp-4); max-width:700px">How each question ended, newest first, with the price it settled at.</div>'
    + '<div style="' + NOTIZ + '; margin-top:var(--sp-3); max-width:700px">' + esc(live.price_note || '') + '</div>'
    + (live.as_of ? '<div style="margin-top:var(--sp-3)">' + asOfLine(live.as_of) + '</div>' : '')
    + '<div style="display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:var(--sp-5); margin-top:var(--sp-5)">'
    + filterGroup('ANSWER', [['all','All'],['yes','Ended Yes'],['no','Ended No']].map((o) => T.opt(o[1], s.resAnswer === o[0], { resAnswer: o[0] })).join(''))
    + filterGroup('SETTLED WITHIN', [['all','All'],['24','24 hours'],['168','7 days']].map((o) => T.opt(o[1], s.resWindow === o[0], { resWindow: o[0] })).join(''))
    + filterGroup('SORT BY', [['recent','Most recent'],['volume','Volume']].map((o) => T.opt(o[1], s.resSort === o[0], { resSort: o[0] })).join(''))
    + '</div></div>'

    + '<div style="display:grid; grid-template-columns:repeat(4,1fr); border-bottom:1px solid var(--line-2)">'
    + kpis.map((k, i) => kpi({
      form: 'band', trenner: i < 3,
      label: k.label, wert: k.value, farbe: k.amber ? 'var(--warn)' : 'var(--text)'
    })).join('')
    + '</div>'

    + '<div role="table" aria-label="Resolved markets">'
    + '<div role="row" style="display:grid; grid-template-columns:1fr 110px 128px 110px 120px; padding:var(--sp-4) var(--sp-6); border-bottom:1px solid var(--line-2); background:var(--panel); position:sticky; top:0; z-index:3; ' + LABEL + '">'
    + '<div role="columnheader">MARKET</div><div role="columnheader" style="text-align:right">ANSWER</div><div role="columnheader" style="text-align:right">SETTLED PRICE</div><div role="columnheader" style="text-align:right">VOLUME</div><div role="columnheader" style="text-align:right">SETTLED</div></div>'
    + resRows.map((r) => {
      const answerStyle = M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps); border-radius:var(--r-control); padding:var(--sp-2) var(--sp-4); ' + (r.yes ? 'color:var(--on-accent); background:var(--accent)' : 'color:var(--neg-soft); border:1px solid rgba(var(--neg-rgb),.35)');
      return '<div role="row" style="display:grid; grid-template-columns:1fr 110px 128px 110px 120px; align-items:center; padding:var(--sp-4) var(--sp-6); border-bottom:1px solid var(--line-3)">'
        + '<div role="cell" style="padding-right:var(--sp-6)"><div style="font-size:var(--t-body); line-height:var(--lh-tight)">' + esc(r.title) + '</div>'
        + '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-3); margin-top:var(--sp-2)">' + esc(r.meta) + '</div></div>'
        + '<div role="cell" style="display:flex; justify-content:flex-end"><div style="' + answerStyle + '">' + (r.yes ? 'YES' : 'NO') + '</div></div>'
        + '<div role="cell" style="' + M + '; font-size:var(--t-body); text-align:right">' + r.settled_price + '¢</div>'
        + '<div role="cell" style="' + M + '; font-size:var(--t-small); text-align:right; color:var(--ink-3)">' + esc(r.vol) + '</div>'
        + '<div role="cell" style="' + M + '; font-size:var(--t-small); text-align:right; color:var(--ink-3)">' + esc(r.when) + '</div></div>';
    }).join('')
    + '</div>'
    + '</div>';
}
