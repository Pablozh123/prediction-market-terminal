// Overview (research landing), Markets, Live tape, Cross-venue, Resolved.
// Markup ported from the design reference; data flows through the Terminal
// instance (T). Nothing here invents a number: every figure names its payload
// or the panel says which payload is missing.

import { esc, money, num, herkunftSatz, leerBlock, leerZeile, seitenKopf, catChipsPresent, signedMoney, stempel, EINZAHLUNGEN_USD } from '../util.js';
import { spiegelZeit, kurzGeld } from '../charts.js';
import { studieAnker } from './microstructure_page.js';

const M = "font-family:'IBM Plex Mono',monospace";
const LBL9 = M + '; font-size:10.5px; letter-spacing:.14em; color:rgba(var(--ink),.6); margin-bottom:6px';
const HEAD_CELL = M + '; font-size:10.5px; letter-spacing:.14em; color:rgba(var(--ink),.6)';
const REPO_URL = 'https://github.com/Pablozh123/prediction-market-terminal';
const ONE_PAGER_URL = REPO_URL + '/blob/main/docs/research/ONE_PAGER.md';

function filterGroup(label, chipsHtml) {
  return '<div><div style="' + LBL9 + '">' + label + '</div><div style="display:flex; gap:6px; flex-wrap:wrap">' + chipsHtml + '</div></div>';
}

// Category chip row shared by Markets, Live tape and Whale flow: only the
// categories present in the rows are offered, 'All' first.
function catChipRow(T, rows, key, stateKey, current) {
  const cats = ['All'].concat(catChipsPresent(rows, key));
  return '<div style="display:flex; gap:7px; flex-wrap:wrap">'
    + cats.map((c) => T.chip(c.toUpperCase(), current === c, { [stateKey]: c })).join('')
    + '</div>';
}

// One-line "as of" stamp for a live block; empty when the API has not
// answered yet, so no line claims a time it does not have.
function asOfLine(iso) {
  return iso ? '<span style="' + M + '; font-size:11px; color:rgba(var(--ink),.55)">as of ' + esc(stempel(iso)) + '</span>' : '';
}

// Spaltenraster der Markttabelle — Kopfzeile und Zeilen teilen es.
const MARKT_SPALTEN = '1fr 64px 90px 76px 96px 104px 96px';

function marketRowHtml(v) {
  return '<div ' + v.act + ' class="hv-panel" style="display:grid; grid-template-columns:' + MARKT_SPALTEN + '; align-items:center; padding:13px 24px; border-bottom:1px solid rgba(var(--ink),.06); cursor:pointer">'
    + '<div style="padding-right:20px">'
    + '<div style="font-size:13.5px; line-height:1.35">' + esc(v.title) + '</div>'
    + '<div style="' + M + '; font-size:10.5px; color:rgba(var(--ink),.6); margin-top:3px">' + esc(v.meta) + '</div></div>'
    + '<div style="' + M + '; font-size:15px; text-align:right">' + v.priceLabel + '</div>'
    + '<div style="' + v.changeStyle + '">' + v.changeLabel + '</div>'
    + '<div style="' + M + '; font-size:12px; text-align:right; color:rgba(var(--ink),.55)">' + esc(v.spreadLabel || '—') + '</div>'
    + '<div style="' + M + '; font-size:12px; text-align:right; color:rgba(var(--ink),.55)">' + esc(v.liqLabel || '—') + '</div>'
    // Unter der Volumenzahl ihr Anteil am groessten Volumen der Sicht, als
    // 56px-Balken: die Standard-Sortierspalte wird so ohne Lesen scannbar.
    + '<div style="text-align:right"><div style="' + M + '; font-size:13px">' + v.volLabel + '</div>'
    + (v.volShare != null
      ? '<div style="margin:4px 0 0 auto; width:56px; height:2px; border-radius:1px; background:rgba(var(--ink),.1)">'
        + '<div style="width:' + v.volShare.toFixed(1) + '%; height:100%; border-radius:1px; background:rgba(var(--ink),.45)"></div></div>'
      : '')
    + '</div>'
    + '<div style="' + M + '; font-size:12px; text-align:right; color:rgba(var(--ink),.55)">' + esc(v.ends) + '</div></div>';
}

// One compact insight panel on the Markets page: a heading, up to five
// clickable rows (each opens its market), and an honest line when the
// loaded sample has nothing that qualifies.
function insightPanel(titel, sub, rowsHtml, leerSatz) {
  return '<div style="background:var(--panel); border:1px solid rgba(var(--ink),.09); border-radius:6px; overflow:hidden">'
    + '<div style="padding:9px 14px; border-bottom:1px solid rgba(var(--ink),.08)"><h2 style="' + M + '; font-size:11px; letter-spacing:.13em; color:var(--accent); margin:0; display:inline">' + titel + '</h2>'
    + (sub ? ' <span style="' + M + '; font-size:10.5px; color:rgba(var(--ink),.55); letter-spacing:0">· ' + sub + '</span>' : '') + '</div>'
    + (rowsHtml || '<div style="padding:12px 14px; ' + M + '; font-size:10.5px; color:rgba(var(--ink),.55)">' + esc(leerSatz) + '</div>')
    + '</div>';
}

// ---------------------------------------------------------------- overview (research landing)

// Verdict vocabulary of public/data/microstructure.json (verdikt_art) as a
// tag: label, colour. Anything unknown renders its raw value, uncoloured.
const VERDICT_TAG = {
  ja: { label: 'CONFIRMED', color: 'var(--accent)', bg: 'rgba(var(--accent-rgb),.12)' },
  nein: { label: 'REFUTED', color: 'var(--neg-soft)', bg: 'rgba(var(--neg-rgb),.12)' },
  offen: { label: 'NOT IDENTIFIED', color: 'var(--warn)', bg: 'rgba(var(--warn-rgb),.12)' },
  kontrolle: { label: 'CONTROL', color: 'var(--info)', bg: 'rgba(var(--info-rgb),.14)' }
};

function verdictTag(art) {
  const v = VERDICT_TAG[String(art || '').toLowerCase()];
  const label = v ? v.label : String(art || '—').toUpperCase();
  const style = M + '; font-size:10.5px; letter-spacing:.12em; border-radius:4px; padding:3px 8px; white-space:nowrap; '
    + (v ? 'color:' + v.color + '; background:' + v.bg : 'color:rgba(var(--ink),.55); border:1px solid rgba(var(--ink),.16)');
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

// The key number of a study: first entry of zahlen[] with its unit, and the
// sample size from basis (observations, snapshots, pairs, markets — whichever
// the study recorded). Ranges render as "a to b".
function keyNumber(study) {
  const z = study && Array.isArray(study.zahlen) && study.zahlen.length ? study.zahlen[0] : null;
  if (!z) return { value: '—', label: '', unit: '' };
  let value;
  if (Array.isArray(z.wert)) value = z.wert.map((v) => fmtWert(v)).join(' to ');
  else value = fmtWert(z.wert);
  return { value, label: String(z.label || ''), unit: String(z.einheit || '') };
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
  return '<div style="display:flex; align-items:center; justify-content:space-between; gap:12px; padding:12px 24px; border-bottom:1px solid rgba(var(--ink),.09); background:var(--panel)">'
    + '<div style="' + M + '; font-size:11px; letter-spacing:.16em; color:' + (color || 'var(--accent)') + '">' + label + '</div>'
    + '<div style="display:flex; align-items:center; gap:14px">' + (right || '') + '</div></div>';
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
    return '<div' + (neu ? ' class="tape-in"' : '') + ' style="display:grid; grid-template-columns:84px minmax(0,1fr) 110px 76px; gap:10px; align-items:baseline; padding:7px 24px; border-bottom:1px solid rgba(var(--ink),.06)">'
      + '<div style="' + M + '; font-size:10.5px; color:rgba(var(--ink),.5); white-space:nowrap">' + esc(t.ago) + '</div>'
      + '<div style="font-size:12.5px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="' + esc(t.market) + '">' + esc(t.market) + '</div>'
      + '<div style="' + M + '; font-size:10.5px; color:' + (kauf ? 'var(--pos)' : 'var(--neg)') + '; text-align:right; white-space:nowrap">' + esc(t.side) + ' ' + esc(t.price || '') + '</div>'
      + '<div style="' + M + '; font-size:11px; text-align:right">' + money(t.size) + '</div></div>';
  }).join('');
  // Merken, was diese Antwort zeigte — der naechste Poll animiert nur Neues.
  T._tapeGesehen = new Set(rows.map(schluessel));
  return '<div style="display:flex; align-items:baseline; justify-content:space-between; gap:10px; padding:14px 24px 8px; border-top:1px solid rgba(var(--ink),.06)">'
    + '<div style="' + M + '; font-size:10.5px; letter-spacing:.15em; color:rgba(var(--ink),.6)">THE TAPE, LIVE · PRINTS ≥ $2.5K</div>'
    + '<div style="' + M + '; font-size:10.5px; color:rgba(var(--ink),.5)">refreshes every 30 s · read-only</div></div>'
    + zeilen;
}

// ---- The wire (landing) ----------------------------------------------------
// Ein laufendes Band der groessten Maerkte aus dem 30-s-Poll. Die Zeilen sind
// dieselben echten Reihen wie auf der Marktseite; nur die Bewegung ist Zierde
// (ambient.js schiebt das Band; der Inhalt ist fuer die Schleife verdoppelt).
// Eine Preiszelle blitzt einmal auf, wenn der Poll sie bewegt hat. Ohne
// lebende Maerkte gibt es kein Band. Fuer Screenreader ist es verborgen —
// die Maerkte stehen als richtige Tabelle einen Klick entfernt.
function wireStrip(T) {
  const maerkte = T.markets.slice().sort((a, b) => b.vol - a.vol).slice(0, 10);
  if (!maerkte.length) return '';
  const vorher = T._wireVorher instanceof Map ? T._wireVorher : null;
  const items = maerkte.map((m) => {
    const delta = vorher && vorher.has(m.id) ? m.yes - vorher.get(m.id) : 0;
    const blitz = delta > 0 ? ' class="wire-up"' : delta < 0 ? ' class="wire-dn"' : '';
    return '<span style="display:inline-flex; align-items:baseline; gap:8px; padding:0 22px; border-right:1px solid rgba(var(--ink),.1)">'
      + '<span style="color:rgba(var(--ink),.62)">' + esc(m.title) + '</span>'
      + '<span' + blitz + ' style="font-weight:600; border-radius:3px; padding:0 4px">' + num(m.yes) + '¢</span>'
      + (m.chg ? '<span style="color:' + (m.chg > 0 ? 'var(--pos)' : 'var(--neg)') + '">' + (m.chg > 0 ? '+' : '−') + Math.abs(m.chg) + '</span>' : '')
      + '</span>';
  }).join('');
  T._wireVorher = new Map(maerkte.map((m) => [m.id, m.yes]));
  return '<div aria-hidden="true" style="border-bottom:1px solid rgba(var(--ink),.09); background:var(--panel); overflow:hidden; ' + M + '; font-size:12px">'
    + '<div id="wire-row" style="display:inline-flex; white-space:nowrap; padding:9px 0; will-change:transform">' + items + items + '</div></div>';
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
    ? '<div ' + goStudy(i) + ' class="hv-accent" style="' + M + '; font-size:11px; color:' + (color || 'rgba(var(--ink),.6)') + '; cursor:pointer; padding:5px 0; white-space:nowrap">' + label + ' →</div>'
    : '');

  // ---- verdict board -----------------------------------------------------
  const studien = micro && Array.isArray(micro.studien) ? micro.studien : [];
  const counts = verdictCounts(micro);
  let board;
  if (studien.length) {
    board = '<div style="display:grid; grid-template-columns:36px 1fr 128px 190px 150px; padding:9px 24px; border-bottom:1px solid rgba(var(--ink),.09); ' + HEAD_CELL + '">'
      + '<div>#</div><div>QUESTION</div><div>VERDICT</div><div style="text-align:right">KEY NUMBER · N</div><div style="text-align:right">WINDOW</div></div>'
      + studien.map((st, i) => {
        const kn = keyNumber(st);
        const basis = st.basis || {};
        const nLabel = sampleLabel(basis);
        // Jede Zeile fuehrt direkt zu ihrer Karte auf der Microstructure-Seite,
        // nicht zum Seitenanfang: gleicher Anker wie die Sprungliste dort.
        return '<div ' + goStudy(microIdx, studieAnker(st, i)) + ' class="hv-panel" style="display:grid; grid-template-columns:36px 1fr 128px 190px 150px; align-items:center; padding:11px 24px; border-bottom:1px solid rgba(var(--ink),.06); cursor:pointer">'
          + '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.6)">' + String(i + 1).padStart(2, '0') + '</div>'
          + '<div style="padding-right:16px; min-width:0"><div style="font-size:13.5px; line-height:1.35">' + esc(st.frage || st.id || '—') + '</div>'
          // Truncated lines carry the full text as a tooltip.
          + '<div style="' + M + '; font-size:10.5px; color:rgba(var(--ink),.6); margin-top:3px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="' + esc(String(st.verdikt || '')) + '">' + esc(String(st.verdikt || '').split('. ')[0]) + '</div></div>'
          + '<div>' + verdictTag(st.verdikt_art) + '</div>'
          + '<div style="text-align:right; min-width:0"><div style="' + M + '; font-size:14px">' + esc(kn.value) + (kn.unit ? ' <span style="font-size:11px; color:rgba(var(--ink),.6)">' + esc(kn.unit) + '</span>' : '') + '</div>'
          + '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.6); margin-top:2px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="' + esc(kn.label + (nLabel ? ' · ' + nLabel : '')) + '">' + esc(kn.label) + (nLabel ? ' · ' + esc(nLabel) : '') + '</div></div>'
          + '<div style="' + M + '; font-size:11px; text-align:right; color:rgba(var(--ink),.5)">' + esc(basis.fenster || '—') + '</div></div>';
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
    ? kpiCell('NET PNL (WALLET · BOT)', signedMoney(walletNetto.wert),
      ledgerFrischer ? 'bot trades in the wallet ledger' : 'on-chain wallet, reconciled', true, walletNetto.wert)
    : kpiCell('NET PNL (FROM RUN LOGS)', agg && agg.realisierter_pnl_usd != null ? signedMoney(agg.realisierter_pnl_usd) : '—', 'no wallet reconciliation yet', true, agg && agg.realisierter_pnl_usd);
  // Die vierte Zelle: das ganze Wallet als Rendite. Bezugsgroesse ist immer
  // die einmalige Einzahlung (on-chain nachpruefbar) — aus dem Ledger, sonst
  // die deklarierte Konstante. Nie die Kaufsumme: jeder reinvestierte Dollar
  // wuerde die Basis aufblaehen und die Rendite kleinrechnen.
  const la = ledger && ledger.aggregat ? ledger.aggregat : null;
  const einzahlungen = la && la.einzahlungen_usd != null ? +la.einzahlungen_usd : EINZAHLUNGEN_USD;
  let flussZelle = kpiCell('ROI (WALLET · ALL ACTIVITY)', '—', 'wallet_ledger.json not loaded yet', false);
  if (la && la.netto_cashflow_usd != null && einzahlungen > 0) {
    const roi = (100 * +la.netto_cashflow_usd) / einzahlungen;
    flussZelle = kpiCell('ROI (WALLET · ALL ACTIVITY)', (roi >= 0 ? '+' : '') + roi.toFixed(1) + '%',
      'net cashflow ' + signedMoney(+la.netto_cashflow_usd)
      + ' on the one-time deposit of $' + num(einzahlungen.toFixed(0)), false, roi);
  }
  const runsStrip = agg
    ? '<div style="display:grid; grid-template-columns:repeat(4,1fr); border-bottom:1px solid rgba(var(--ink),.09)">'
      + kpiCell('RUNS · BETS', num(agg.n_runs != null ? agg.n_runs : '—') + ' · ' + num(agg.n_wetten != null ? agg.n_wetten : '—'),
        (walletKaeufe != null ? 'wallet buys $' + num(walletKaeufe.toFixed(0)) : 'stake ' + (agg.einsatz_usd != null ? '$' + num((+agg.einsatz_usd).toFixed(0)) + ' (from run logs)' : '—'))
        + (runs && runs.stand_utc ? ' · payload ' + esc(stempel(runs.stand_utc)) : ''), true)
      // WON · LOST aus dem Wallet-Ledger (alle aufgeloesten Positionen,
      // wertlos ausgelaufene zaehlen als verloren) — die Run-Zaehlung aus
      // runs.json sah nur die Bot-Wetten und unterschlug den Rest des
      // Wallets. Ohne Ledger bleibt die Run-Zaehlung als benannter Rueckfall.
      + (la && la.positionen_gewonnen != null && la.positionen_verloren != null
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
      '<div ' + goStudy(notesIdx) + ' class="hv-panel" style="display:grid; grid-template-columns:96px 1fr 120px; gap:12px; align-items:center; padding:11px 24px; border-bottom:1px solid rgba(var(--ink),.06); cursor:pointer">'
      + '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.6)">' + esc(String(n.date || '').slice(0, 10)) + '</div>'
      + '<div style="font-size:13px; line-height:1.35">' + esc(n.title || '—') + '</div>'
      + '<div style="' + M + '; font-size:10.5px; color:rgba(var(--ink),.6); text-align:right">' + esc(n.venue || '') + '</div></div>'
    ).join('')
    : leerZeile(landingLeerSatz(hk.notes, 'field_notes.json'));

  // ---- live data row (from the existing 30 s poll) -----------------------
  const totalVol = T.markets.reduce((a, m) => a + m.vol, 0);
  const pmCount = T.markets.filter((m) => m.venue === 'Polymarket').length;
  const ksCount = T.markets.length - pmCount;
  const whalePrints = T.tape.filter((t) => t.size >= s.setWhale).length;
  const whaleWallets = new Set(T.tape.filter((t) => t.size >= s.setWhale && t.wallet !== '—').map((t) => t.wallet)).size;
  const marktSatz = herkunftSatz(T.herkunft.markets, '/api/markets');
  const tapeSatz = herkunftSatz(T.herkunft.tape, '/api/tape');
  const hatMaerkte = T.markets.length > 0;
  const hatTape = T.tape.length > 0;
  const liveRow = '<div style="display:grid; grid-template-columns:repeat(3,1fr); border-bottom:1px solid rgba(var(--ink),.09)">'
    + kpiCell('MARKETS TRACKED', hatMaerkte ? num(T.markets.length) : '—', hatMaerkte ? num(pmCount) + ' Polymarket · ' + num(ksCount) + ' Kalshi' : esc(marktSatz), true)
    + kpiCell('VOLUME · 24H', hatMaerkte ? money(totalVol) : '—', hatMaerkte ? 'sum over the ' + num(T.markets.length) + ' markets in the sample' : esc(marktSatz), true)
    + kpiCell('PRINTS ≥ $2.5K · TAPE WINDOW', hatTape ? num(whalePrints) : '—', hatTape ? 'from ' + num(whaleWallets) + ' identified wallets' : esc(tapeSatz), false)
    + '</div>';

  const subline = landingSubline(landing);
  // Die zwei Haelften der Seite als zwei Einstiege direkt unter dem Titel:
  // links die getestete Strategie (Forschung, echte Laeufe, Bilanz), rechts
  // das Analysewerkzeug (Live-Screens). Wer die Seite oeffnet, sieht zuerst
  // diese Trennung, nicht eine Liste gleichrangiger Bloecke.
  const pfade = '<div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(280px, 1fr)); gap:12px; margin-top:16px; max-width:860px">'
    + pfadKarte(goStudy(runsIdx), 'TESTED STRATEGY', 'var(--accent)', 'Researched, then run with real money: every bet, its latency and the on-chain wallet that proves it.')
    + pfadKarte(T.act(() => T.go('markets')), 'ANALYSIS TOOL', 'var(--info)', 'Live screens on Polymarket & Kalshi: markets, tape, whale flow, cross-venue, risk.')
    + '</div>';
  // Rechts neben dem Titel, sobald der 30-s-Poll Prints liefert: das Band,
  // wie es gerade laeuft. Ohne lebende Antwort bleibt der Kopf einspaltig.
  // Hinter dem Kopf treibt der Wahrscheinlichkeits-Fluss die volle Breite
  // (ambient.js malt in die Canvas; ohne Achsen und Zahlen ist er erkennbar
  // Zierde, keine Messung). Der Verlauf davor haelt die Headline lesbar.
  return '<div>'
    + '<div style="padding:30px 24px 24px; border-bottom:1px solid rgba(var(--ink),.09); position:relative; overflow:hidden; min-height:300px; box-sizing:border-box; display:flex; align-items:center">'
    + '<canvas id="river-cv" aria-hidden="true" style="position:absolute; inset:0; width:100%; height:100%"></canvas>'
    + '<div aria-hidden="true" style="position:absolute; inset:0; pointer-events:none; background:linear-gradient(90deg, rgba(var(--bg-rgb),.92) 0%, rgba(var(--bg-rgb),.62) 40%, rgba(var(--bg-rgb),.12) 68%, rgba(var(--bg-rgb),0) 100%)"></div>'
    + '<div style="position:relative; max-width:640px">'
    + '<h1 style="font-size:26px; line-height:1.2; margin:0; font-weight:600; letter-spacing:-0.015em">Prediction-market microstructure, <em style="color:var(--accent)">measured on self-recorded books.</em></h1>'
    + '<div style="font-size:14px; color:rgba(var(--ink),.66); margin-top:8px; max-width:760px">' + esc(subline) + '</div>'
    + pfade
    + '<div style="display:flex; gap:14px; margin-top:14px; flex-wrap:wrap; ' + M + '; font-size:11px">'
    + '<a href="' + REPO_URL + '" target="_blank" rel="noopener">GitHub repository →</a>'
    + '<a href="' + ONE_PAGER_URL + '" target="_blank" rel="noopener">One-pager (docs/research/ONE_PAGER.md) →</a>'
    + (pilotIdx >= 0 ? '<span ' + goStudy(pilotIdx) + ' class="hv-accent" style="color:rgba(var(--ink),.55); cursor:pointer; display:inline-block; padding:5px 0">Pre-registered pilot →</span>' : '')
    + '</div></div>'
    + '</div>'

    // Das Band mit den groessten Maerkten laeuft direkt unter dem Kopf.
    + wireStrip(T)

    // Die getestete Strategie zuerst — sie ist das Argument der Seite; die
    // Studien liefern die Begruendung darunter.
    + sectionHead('TESTED STRATEGY · LIVE RUNS, REAL MONEY', link(runsIdx, 'EVERY BET'))
    + runsStrip

    + sectionHead('VERDICT BOARD · ' + (studien.length ? num(counts.total) + ' STUDIES' : 'MICROSTRUCTURE'),
      (micro && micro.stand_utc ? '<span style="' + M + '; font-size:11px; color:rgba(var(--ink),.55)">payload ' + esc(stempel(micro.stand_utc)) + '</span>' : '')
      + link(microIdx, 'FULL REPORT'))
    + board

    + sectionHead('FIELD NOTES', link(notesIdx, 'ALL NOTES'), 'var(--info)')
    + notesStrip

    + sectionHead('ANALYSIS TOOL · LIVE DATA', asOfLine(s.liveAsOf) + '<div ' + T.act(() => T.go('markets')) + ' class="hv-accent" style="' + M + '; font-size:11px; color:rgba(var(--ink),.6); cursor:pointer; padding:5px 0">MARKETS →</div><div ' + T.act(() => T.go('flow')) + ' class="hv-accent" style="' + M + '; font-size:11px; color:rgba(var(--ink),.6); cursor:pointer; padding:5px 0">TAPE →</div>')
    + liveRow
    // Das Tape als Streifen im Live-Block — dieselben Prints wie im Poll,
    // neue Zeilen gleiten ein, sobald sie ankommen.
    + tapeLivePanel(T)
    + '<div style="padding:22px 24px; text-align:center; ' + M + '; font-size:11px; color:rgba(var(--ink),.55)">Public data only · live blocks refresh every 30 seconds · research payloads are frozen files under ./data</div>'
    + '</div>';
}

// One of the two entry cards under the landing title; act is empty when the
// target study is not in the list, the card then renders without a cursor.
function pfadKarte(act, label, farbe, satz) {
  return '<div ' + act + (act ? ' class="hv-panel"' : '') + ' style="background:var(--panel); border:1px solid rgba(var(--ink),.09); border-radius:6px; padding:14px 16px' + (act ? '; cursor:pointer' : '') + '">'
    + '<div style="' + M + '; font-size:11px; letter-spacing:.16em; color:' + farbe + '">' + label + ' →</div>'
    + '<div style="font-size:12.5px; color:rgba(var(--ink),.6); margin-top:6px; line-height:1.5">' + satz + '</div></div>';
}

function kpiCell(label, value, sub, borderRight, signed) {
  const color = signed == null ? 'var(--text)' : (+signed >= 0 ? 'var(--pos)' : 'var(--neg)');
  return '<div style="padding:16px 20px' + (borderRight ? '; border-right:1px solid rgba(var(--ink),.09)' : '') + '">'
    + '<div style="' + M + '; font-size:11px; letter-spacing:.14em; color:rgba(var(--ink),.6)">' + label + '</div>'
    + '<div style="' + M + '; font-size:24px; margin-top:8px; color:' + color + '">' + value + '</div>'
    + '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.6); margin-top:4px">' + sub + '</div></div>';
}

// ---------------------------------------------------------------- markets
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
  const gesamtVol = T.markets.reduce((a, m) => a + m.vol, 0);
  const pmAnzahl = T.markets.filter((m) => m.venue === 'Polymarket').length;
  const spreads = T.markets.map((m) => mx(m).spread).filter((v) => v != null).sort((a, b) => a - b);
  const spreadMedian = spreads.length ? (spreads.length % 2 ? spreads[(spreads.length - 1) / 2] : (spreads[spreads.length / 2 - 1] + spreads[spreads.length / 2]) / 2) : null;
  const movers = T.markets.filter((m) => m.chg !== 0).sort((a, b) => Math.abs(b.chg) - Math.abs(a.chg)).slice(0, 5);
  const baldFaellig = T.markets.filter((m) => mx(m).endsDays != null).sort((a, b) => mx(a).endsDays - mx(b).endsDays).slice(0, 5);
  const unentschieden = T.markets.filter((m) => m.yes >= 40 && m.yes <= 60).sort((a, b) => b.vol - a.vol).slice(0, 5);
  const topMover = movers[0] || null;
  const kurz = (t) => (String(t).length > 44 ? String(t).slice(0, 43) + '…' : String(t));
  const zeile = (m, mitte, rechts) =>
    '<div ' + T.act(() => T.openMarket(m.id)) + ' class="hv-panel" style="display:grid; grid-template-columns:1fr 46px 78px; gap:8px; align-items:center; padding:8px 14px; border-bottom:1px solid rgba(var(--ink),.05); cursor:pointer">'
    + '<div style="font-size:12px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="' + esc(m.title) + '">' + esc(m.title) + '</div>'
    + '<div style="' + M + '; font-size:11.5px; text-align:right; color:rgba(var(--ink),.55)">' + mitte + '</div>'
    + '<div style="' + M + '; font-size:11.5px; text-align:right">' + rechts + '</div></div>';
  const kpiStrip = '<div style="display:grid; grid-template-columns:repeat(4,1fr); border:1px solid rgba(var(--ink),.09); border-radius:6px; margin-top:14px; overflow:hidden; background:var(--panel)">'
    + kpiCell('MARKETS IN SAMPLE', num(T.markets.length), pmAnzahl + ' Polymarket · ' + (T.markets.length - pmAnzahl) + ' Kalshi', true)
    + kpiCell('VOLUME 24H', money(gesamtVol), 'sum over the sample', true)
    + kpiCell('BIGGEST 1D MOVE', topMover ? (topMover.chg >= 0 ? '+' : '') + topMover.chg + '¢' : '—',
      topMover ? esc(kurz(topMover.title)) : 'no market in the sample moved', true, topMover ? topMover.chg : null)
    + kpiCell('MEDIAN SPREAD', spreadMedian != null ? spreadMedian + '¢' : '—',
      spreads.length ? 'n = ' + num(spreads.length) + ' markets with a quoted spread' : 'no spreads in the sample', false)
    + '</div>';
  const einblicke = '<div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(280px, 1fr)); gap:12px; margin-top:12px">'
    + insightPanel('TOP MOVERS · 1D', 'yes price · change',
      movers.map((m) => zeile(m, m.yes + '¢', '<span style="color:' + (m.chg >= 0 ? 'var(--pos)' : 'var(--neg)') + '">' + (m.chg >= 0 ? '+' : '') + m.chg + '¢</span>')).join(''),
      'no market in the sample moved in the last day')
    + insightPanel('RESOLVING NEXT', 'yes price · resolves',
      baldFaellig.map((m) => zeile(m, m.yes + '¢', esc(mx(m).endsDays <= 1 ? 'under 1 d' : 'in ' + mx(m).endsDays + ' d'))).join(''),
      'no market in the sample carries an end date')
    + insightPanel('COIN FLIPS', 'priced 40–60¢, the market is undecided · by volume',
      unentschieden.map((m) => zeile(m, m.yes + '¢', money(m.vol))).join(''),
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
    mRows = mRows.filter((m) => m.vol >= v); addChip('volume > $' + s.mVol, { mVol: 'all' });
  }
  // Date-based filters only judge rows whose date is known; a market without
  // an end date is neither "ending soon" nor "open ended".
  if (s.mEnds !== 'all') {
    const d = { '1d': 1, '7d': 7, '30d': 30 }[s.mEnds];
    mRows = s.mEnds === 'open'
      ? mRows.filter((m) => mx(m).endsDays != null && mx(m).endsDays > 180)
      : mRows.filter((m) => mx(m).endsDays != null && mx(m).endsDays <= d);
    addChip('resolves ' + (s.mEnds === 'open' ? 'far out' : 'in < ' + s.mEnds), { mEnds: 'all' });
  }
  if (s.mAge !== 'all') {
    mRows = s.mAge === '30d'
      ? mRows.filter((m) => mx(m).age != null && mx(m).age > 30)
      : mRows.filter((m) => mx(m).age != null && mx(m).age <= ({ '1d': 1, '7d': 7 })[s.mAge]);
    addChip('age ' + s.mAge, { mAge: 'all' });
  }
  if (s.mQuick === 'ending') { mRows = mRows.filter((m) => mx(m).endsDays != null && mx(m).endsDays <= 14); addChip('ending soon', { mQuick: 'trending' }); }
  if (s.mQuick === 'new') { mRows = mRows.filter((m) => mx(m).age != null && mx(m).age <= 90); addChip('new markets', { mQuick: 'trending' }); }
  const nullLast = (a, b, asc) => {
    if (a == null && b == null) return 0;
    if (a == null) return 1;
    if (b == null) return -1;
    return asc ? a - b : b - a;
  };
  mRows = mRows.sort((a, b) => {
    if (s.marketSort === 'change') return Math.abs(b.chg) - Math.abs(a.chg);
    if (s.marketSort === 'liquidity') return b.liq - a.liq;
    if (s.marketSort === 'ending') return nullLast(mx(a).endsDays, mx(b).endsDays, true);
    if (s.marketSort === 'newest') return nullLast(mx(a).age, mx(b).age, true);
    return b.vol - a.vol;
  });

  const maxVol = mRows.reduce((a, m) => Math.max(a, m.vol), 0);
  const badge = mActive.length ? M + '; font-size:11px; color:var(--on-accent); background:var(--accent); border-radius:4px; padding:1px 7px' : 'display:none';
  const chevron = M + '; font-size:16px; color:rgba(var(--ink),.5); transition:transform .18s ease; transform:rotate(' + (s.marketFiltersOpen ? '90deg' : '0deg') + ')';

  return '<div>'
    + '<div style="padding:20px 24px 14px; border-bottom:1px solid rgba(var(--ink),.09)">'
    + '<div style="display:flex; align-items:flex-end; justify-content:space-between; gap:20px">'
    + '<div><div style="' + M + '; font-size:11px; letter-spacing:.18em; color:var(--accent)">MARKETS</div>'
    + '<h1 style="font-size:21px; line-height:1.25; margin:6px 0 0; font-weight:600; letter-spacing:-0.01em">Every market, one table</h1></div>'
    + '<div style="display:flex; align-items:center; gap:10px">'
    + '<input value="' + esc(s.marketQuery) + '" ' + T.inp((e) => T.setState({ marketQuery: e.target.value }), 'marketQuery') + ' placeholder="Search markets…" style="background:var(--panel); border:1px solid rgba(var(--ink),.35); border-radius:4px; padding:9px 12px; ' + M + '; font-size:12.5px; color:var(--text); width:230px" />'
    + '<div ' + T.act(() => T.setState({ mPlatform: 'all', mStatus: 'active', mProb: 'all', mLiq: 'all', mVol: 'all', mEnds: 'all', mAge: 'all', mExclude: [], marketCat: 'All', marketQuery: '', mQuick: 'trending', marketSort: 'volume' })) + ' class="hv-bd32" style="font-size:12.5px; color:rgba(var(--ink),.6); border:1px solid rgba(var(--ink),.16); border-radius:4px; padding:9px 13px; cursor:pointer">Reset filters</div>'
    + '</div></div>'

    // Der Ueberblick zuerst: vier Kennzahlen des Ausschnitts und drei
    // Einblick-Panels (Movers, naechste Aufloesungen, 40–60¢), jede Zeile
    // oeffnet ihren Markt. Alles aus den geladenen Zeilen, nichts erfunden.
    + kpiStrip
    + einblicke

    // VIEW (Cards / Calendar) and QUICK Saved / My positions are gone: the
    // first two had no renderer, the last two filtered on flags nothing sets.
    + '<div style="display:flex; align-items:center; gap:22px; margin-top:16px; flex-wrap:wrap">'
    + '<div style="display:flex; align-items:center; gap:8px"><span style="' + LBL9.replace('; margin-bottom:6px', '') + '">QUICK</span>'
    + [['trending','By volume'],['ending','Ending soon'],['new','New']].map((o) => T.opt(o[1], s.mQuick === o[0], { mQuick: o[0] })).join('') + '</div>'
    + asOfLine(s.liveAsOf)
    + '</div>'

    + '<div style="display:flex; gap:7px; margin-top:14px; flex-wrap:wrap">'
    + cats.map((c) => T.chip((c.toUpperCase() + ' ' + (c === 'All' ? T.markets.length : catAnzahl[c] || 0)), s.marketCat === c, { marketCat: c })).join('')
    + '</div>'

    + '<div style="border:1px solid rgba(var(--ink),.09); border-radius:6px; margin-top:14px; overflow:hidden">'
    + '<div ' + T.act(() => T.setState({ marketFiltersOpen: !s.marketFiltersOpen })) + ' class="hv-el" style="display:flex; align-items:center; justify-content:space-between; padding:11px 15px; background:var(--panel); cursor:pointer">'
    + '<div style="display:flex; align-items:center; gap:10px"><div style="font-size:13px">All filters</div><div style="' + badge + '">' + mActive.length + '</div></div>'
    + '<div style="' + chevron + '">›</div></div>'
    + (s.marketFiltersOpen ?
      '<div style="padding:16px; display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:16px 20px">'
      + filterGroup('PLATFORM', [['all','All'],['Polymarket','Polymarket'],['Kalshi','Kalshi']].map((o) => T.opt(o[1], s.mPlatform === o[0], { mPlatform: o[0] })).join(''))
      + filterGroup('PROBABILITY', [['all','All'],['5-95','5–95%'],['20-80','20–80%'],['80','>80%'],['95','>95%'],['99','>99%']].map((o) => T.opt(o[1], s.mProb === o[0], { mProb: o[0] })).join(''))
      + filterGroup('LIQUIDITY', [['all','All'],['1k','>$1k'],['10k','>$10k'],['100k','>$100k']].map((o) => T.opt(o[1], s.mLiq === o[0], { mLiq: o[0] })).join(''))
      + filterGroup('VOLUME 24H', [['all','All'],['10k','>$10k'],['100k','>$100k'],['1m','>$1m']].map((o) => T.opt(o[1], s.mVol === o[0], { mVol: o[0] })).join(''))
      + filterGroup('RESOLVES IN', [['all','All'],['1d','<1 day'],['7d','<7 days'],['30d','<30 days'],['open','Open ended']].map((o) => T.opt(o[1], s.mEnds === o[0], { mEnds: o[0] })).join(''))
      + filterGroup('MARKET AGE', [['all','All'],['1d','<1 day'],['7d','<7 days'],['30d','>30 days']].map((o) => T.opt(o[1], s.mAge === o[0], { mAge: o[0] })).join(''))
      + '<div style="grid-column:span 2"><div style="' + LBL9 + '">EXCLUDE CATEGORIES</div><div style="display:flex; gap:6px; flex-wrap:wrap">'
      + cats.slice(1).map((c) => T.opt(c, s.mExclude.indexOf(c) >= 0, () => T.setState({ mExclude: s.mExclude.indexOf(c) >= 0 ? s.mExclude.filter((x) => x !== c) : s.mExclude.concat([c]) }))).join('')
      + '</div></div>'
      + '<div style="grid-column:span 2"><div style="' + LBL9 + '">SORT BY</div><div style="display:flex; gap:6px; flex-wrap:wrap">'
      + [['volume','Volume 24h'],['change','Biggest move'],['liquidity','Liquidity'],['ending','Ending soonest'],['newest','Newest']].map((o) => T.opt(o[1], s.marketSort === o[0], { marketSort: o[0] })).join('')
      + '</div></div>'
      + '</div>' : '')
    + '</div>'

    + '<div style="display:flex; align-items:center; gap:8px; margin-top:12px; flex-wrap:wrap">'
    + '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.6)">' + mRows.length + ' of ' + T.markets.length + ' markets</div>'
    + mActive.map((c) =>
      '<div ' + T.act(() => T.setState(c.reset)) + ' class="hv-bd30" style="' + M + '; font-size:11px; color:rgba(var(--ink),.7); border:1px solid rgba(var(--ink),.14); background:var(--panel-hover); border-radius:4px; padding:3px 9px; cursor:pointer">' + esc(c.label) + ' ✕</div>'
    ).join('')
    + '</div></div>'

    // No TREND column: the API carries a one-day change, not an intraday
    // path, and a two-point line under "TREND 24H" read as a curve. SPREAD
    // und LIQUIDITY kommen aus denselben API-Zeilen (unbekannt bleibt —).
    + '<div style="display:grid; grid-template-columns:' + MARKT_SPALTEN + '; align-items:center; padding:10px 24px; border-bottom:1px solid rgba(var(--ink),.09); background:var(--panel); position:sticky; top:0; z-index:3; ' + HEAD_CELL + '">'
    + '<div>MARKET</div>'
    + '<div style="text-align:right">YES</div>'
    + '<div ' + T.act(() => T.setState({ marketSort: 'change' })) + ' aria-pressed="' + (s.marketSort === 'change' ? 'true' : 'false') + '"' + ' style="text-align:right; cursor:pointer; padding:5px 0; color:' + (s.marketSort === 'change' ? 'var(--accent)' : 'rgba(var(--ink),.6)') + '">CHANGE 1D</div>'
    + '<div style="text-align:right">SPREAD</div>'
    + '<div ' + T.act(() => T.setState({ marketSort: 'liquidity' })) + ' aria-pressed="' + (s.marketSort === 'liquidity' ? 'true' : 'false') + '"' + ' style="text-align:right; cursor:pointer; padding:5px 0; color:' + (s.marketSort === 'liquidity' ? 'var(--accent)' : 'rgba(var(--ink),.6)') + '">LIQUIDITY</div>'
    + '<div ' + T.act(() => T.setState({ marketSort: 'volume' })) + ' aria-pressed="' + (s.marketSort === 'volume' ? 'true' : 'false') + '"' + ' style="text-align:right; cursor:pointer; padding:5px 0; color:' + (s.marketSort === 'volume' ? 'var(--accent)' : 'rgba(var(--ink),.6)') + '">VOLUME 24H</div>'
    + '<div ' + T.act(() => T.setState({ marketSort: 'ending' })) + ' aria-pressed="' + (s.marketSort === 'ending' ? 'true' : 'false') + '"' + ' style="text-align:right; cursor:pointer; padding:5px 0; color:' + (s.marketSort === 'ending' ? 'var(--accent)' : 'rgba(var(--ink),.6)') + '">RESOLVES</div></div>'
    + mRows.map((m) => marketRowHtml(Object.assign(T.marketView(m), {
      spreadLabel: mx(m).spread != null ? mx(m).spread + '¢' : '—',
      liqLabel: m.liq ? money(m.liq) : '—',
      volShare: maxVol > 0 && m.vol > 0 ? Math.max(2, (100 * m.vol) / maxVol) : null
    }))).join('')
    + (mRows.length === 0 ? '<div style="padding:60px; text-align:center; ' + M + '; font-size:12px; color:rgba(var(--ink),.55)">No market matches that filter.</div>' : '')
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
    const kauf = t.side.indexOf('BUY') === 0;
    bins[i][kauf ? 'oben' : 'unten'] += t.size;
    if (t.size >= PULS_MARKE_USD) marken.push({ bin: i, oben: kauf, text: t.market + ' · ' + t.side + ' · ' + money(t.size) });
  });
  const swatch = (farbe) => '<span style="display:inline-block; width:10px; height:10px; border-radius:2px; background:' + farbe + '"></span>';
  const eintrag = (inhalt) => '<div style="display:flex; align-items:center; gap:6px; ' + M + '; font-size:11px; color:rgba(var(--ink),.65)">' + inhalt + '</div>';
  const netto = buys - sells;
  const legende = eintrag(swatch('var(--pos)') + 'buys ' + money(buys))
    + eintrag(swatch('var(--neg)') + 'sells ' + money(sells))
    + eintrag('net <span style="color:' + (netto >= 0 ? 'var(--pos)' : 'var(--neg)') + '">' + kurzGeld(netto, true) + '</span>')
    + (marken.length ? eintrag('<span style="display:inline-block; width:8px; height:8px; border-radius:50%; background:var(--warn)"></span>print ≥ ' + PULS_MARKE_LABEL) : '');
  return spiegelZeit({
    titel: 'FLOW PULSE',
    hinweis: 'per ' + dauerLabel(schritt) + ' · filtered prints',
    legende, bins, marken,
    xLabels: [
      { i: 0, text: '-' + dauerLabel(nBins * schritt), anker: 'start' },
      { i: Math.floor((nBins - 1) / 2), text: '-' + dauerLabel(Math.ceil(nBins / 2) * schritt), anker: 'middle' },
      { i: nBins - 1, text: 'now', anker: 'end' }
    ]
  });
}

// Wohin das Geld gerade fliesst: eine Zeile je Kategorie der gefilterten
// Prints, Balkenlaenge nach Gesamtsumme, innen der Kauf/Verkauf-Anteil.
function kategorieFlussHtml(prints) {
  if (!prints.length) return '';
  const je = {};
  prints.forEach((t) => {
    const c = t.category || 'Other';
    const e = je[c] || (je[c] = { kauf: 0, verkauf: 0 });
    e[t.side.indexOf('BUY') === 0 ? 'kauf' : 'verkauf'] += t.size;
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
    return '<div style="display:grid; grid-template-columns:104px 1fr 76px 66px; gap:10px; align-items:center; padding:8px 14px; border-bottom:1px solid rgba(var(--ink),.05)">'
      + '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.65); white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="' + esc(r.cat) + '">' + esc(r.cat.toUpperCase()) + '</div>'
      + '<div style="min-width:0"><div style="display:flex; gap:2px; width:' + breite.toFixed(1) + '%" title="' + esc('buys ' + money(r.kauf) + ' · sells ' + money(r.verkauf)) + '">'
      + seg(r.kauf, 'var(--pos)') + seg(r.verkauf, 'var(--neg)') + '</div></div>'
      + '<div style="' + M + '; font-size:11.5px; text-align:right">' + kurzGeld(r.summe) + '</div>'
      + '<div style="' + M + '; font-size:11px; text-align:right; color:rgba(var(--ink),.55)">' + kaufAnteil + '% buy</div></div>';
  }).join('');
  return insightPanel('WHERE THE MONEY FLOWS', 'filtered prints · buys vs sells', zeilen, '');
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
  const buys = tapeFiltered.filter((t) => t.side.indexOf('BUY') === 0).reduce((a, t) => a + t.size, 0);
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

  const puls = tapePulsHtml(tapeFiltered, buys, sells);
  const katFluss = kategorieFlussHtml(tapeFiltered);
  const grafiken = puls || katFluss
    ? '<div style="display:grid; grid-template-columns:' + (puls && katFluss ? 'minmax(0,1.65fr) minmax(0,1fr)' : '1fr') + '; gap:12px; padding:14px 24px; border-bottom:1px solid rgba(var(--ink),.09)">'
      + puls + katFluss + '</div>'
    : '';

  return '<div>'
    + '<div style="padding:20px 24px 14px; border-bottom:1px solid rgba(var(--ink),.09)">'
    + '<div style="display:flex; align-items:flex-end; justify-content:space-between; gap:20px">'
    + '<div><div style="' + M + '; font-size:11px; letter-spacing:.18em; color:var(--accent)">LIVE TAPE</div>'
    + '<h1 style="font-size:21px; line-height:1.25; margin:6px 0 0; font-weight:600; letter-spacing:-0.01em">Every large print as it lands</h1></div>'
    + '<div style="display:flex; align-items:center; gap:12px">'
    + asOfLine(s.tapeAsOf || s.liveAsOf)
    + '<input value="' + esc(s.tapeQuery) + '" ' + T.inp((e) => T.setState({ tapeQuery: e.target.value }), 'tapeQuery') + ' placeholder="market, wallet, trader…" style="background:var(--panel); border:1px solid rgba(var(--ink),.35); border-radius:4px; padding:9px 12px; ' + M + '; font-size:12.5px; color:var(--text); width:250px" />'
    + '</div></div>'
    + '<div style="margin-top:14px">' + filterGroup('CATEGORY', catChipRow(T, T.tape, 'category', 'tapeCat', s.tapeCat)) + '</div>'
    + '<div style="display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:14px 18px; margin-top:14px">'
    + filterGroup('MINIMUM SIZE', [
      T.chip('≥ $2.5K', s.tapeMin === 2500 && !s.tapeTracked, { tapeMin: 2500, tapeTracked: false }),
      T.chip('≥ $10K', s.tapeMin === 10000 && !s.tapeTracked, { tapeMin: 10000, tapeTracked: false })
    ].join(''))
    + filterGroup('PLATFORM', [['all','All'],['Polymarket','Polymarket'],['Kalshi','Kalshi']].map((o) => T.opt(o[1], s.tapePlatform === o[0], { tapePlatform: o[0] })).join(''))
    + filterGroup('SIDE', [['all','All'],['BUY','Buys'],['SELL','Sells']].map((o) => T.opt(o[1], s.tapeSide === o[0], { tapeSide: o[0] })).join(''))
    + filterGroup('OUTCOME', [['all','All'],['Yes','Yes'],['No','No']].map((o) => T.opt(o[1], s.tapeOutcome === o[0], { tapeOutcome: o[0] })).join(''))
    + '</div></div>'

    + '<div style="display:grid; grid-template-columns:repeat(4,1fr); border-bottom:1px solid rgba(var(--ink),.09)">'
    + kpiCell('PRINTS SHOWN', num(tapeFiltered.length),
      'of ' + num(T.tape.length) + ' in the tape window', true)
    + kpiCell('TOTAL MOVED', money(tapeNotional),
      tapeNotional ? Math.round((100 * buys) / tapeNotional) + '% buys · net ' + kurzGeld(buys - sells, true) : 'nothing passes the filters', true)
    + kpiCell('WALLETS INVOLVED', num(tapeWallets),
      tapeWallets ? num(identifiziert) + ' prints from identified wallets' : 'Kalshi publishes no wallet identities', true)
    + kpiCell('BIGGEST PRINT', groesster ? money(groesster.size) : '—',
      groesster ? esc(kurzTitel(groesster.market)) : 'no print passes the filters', false)
    + '</div>'

    + grafiken

    + '<div style="display:grid; grid-template-columns:96px 160px 1fr 110px 84px 90px 110px 96px; padding:10px 24px; border-bottom:1px solid rgba(var(--ink),.09); background:var(--panel); position:sticky; top:0; z-index:3; ' + HEAD_CELL + '">'
    + '<div>TIME</div><div>WALLET</div><div>MARKET</div><div>CATEGORY</div><div>SIDE</div><div style="text-align:right">PRICE</div><div style="text-align:right">SIZE</div><div style="text-align:right">VENUE</div></div>'
    + (tapeFiltered.length ? '' : leerZeile('No print in the tape window passes the current filters (size, category, side).'))
    + tapeFiltered.map((t0) => {
      const t = T.tapeRowView(t0);
      const neu = !erste && !gesehen.has(schluessel(t0));
      // Only a print of a loaded market opens the drawer; the other rows are
      // plain rows, not pointers that lead nowhere.
      const klickbar = t.act && t.clickable !== false;
      return '<div ' + (klickbar ? t.act + ' ' : '') + 'class="' + (klickbar ? 'hv-panel' : '') + (neu ? ' tape-in' : '') + '" style="display:grid; grid-template-columns:96px 160px 1fr 110px 84px 90px 110px 96px; align-items:center; padding:12px 24px; border-bottom:1px solid rgba(var(--ink),.06); ' + M + '; font-size:12.5px; ' + (klickbar ? 'cursor:pointer; ' : '') + '">'
        + '<div style="color:rgba(var(--ink),.55)">' + esc(t.ago) + '</div>'
        + '<div style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="' + esc(t.wallet) + '">' + esc(t.wallet) + '</div>'
        + '<div style="font-family:\'IBM Plex Sans\',sans-serif; font-size:13px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; padding-right:12px" title="' + esc(t.market) + '">' + esc(t.market) + '</div>'
        + '<div style="font-size:11px; color:rgba(var(--ink),.55)">' + esc(t.category || 'Other') + '</div>'
        + '<div style="' + t.sideStyle + '">' + esc(t.side) + '</div>'
        + '<div style="text-align:right">' + esc(t.price) + '</div>'
        + '<div style="text-align:right">' + t.size + '</div>'
        + '<div style="text-align:right; color:rgba(var(--ink),.6); font-size:11px">' + esc(t.venue) + '</div></div>';
    }).join('')
    + '</div>';
}

// ---------------------------------------------------------------- cross-venue

// The honesty gate as words, used by both the empty block and the caption.
export const CROSS_GATE_TEXT = 'similarity ≥ 0.5, volume on both venues';

function crossGateBlock(T) {
  const microIdx = T.studies.findIndex((st) => st.tab === 'Microstructure');
  return '<div style="padding:26px 24px">'
    + '<div style="background:var(--panel); border:1px solid rgba(var(--ink),.09); border-radius:6px; padding:20px 22px; max-width:760px">'
    + '<div style="' + M + '; font-size:11px; letter-spacing:.14em; color:var(--warn)">NO PAIR CLEARS THE GATE</div>'
    + '<div style="font-size:13px; color:rgba(var(--ink),.6); margin-top:9px; line-height:1.6">No cross-venue pair clears the match gate right now (' + CROSS_GATE_TEXT + '). '
    + 'See studies 08 and 11: the two 79¢/64¢ \'edges\' were mismatched questions.</div>'
    + (microIdx >= 0 && T.goStudy
      ? '<div ' + T.act(() => T.goStudy(microIdx)) + ' class="hv-accent" style="' + M + '; font-size:11px; color:var(--info); margin-top:12px; cursor:pointer">Open the microstructure report (#research/microstructure) →</div>'
      : '<a href="#research/microstructure" style="' + M + '; font-size:11px; display:inline-block; margin-top:12px">Open the microstructure report →</a>')
    + '</div></div>';
}

export function renderCross(T) {
  const s = T.state;
  const hk = T.herkunft.cross;
  if (!T.crossPairs.length) {
    // Three empty states, all named: request still running, request failed,
    // request answered and nothing passed the gate.
    let body;
    if (!hk) {
      body = '<div style="padding:26px 24px">'
        + '<div style="background:var(--panel); border:1px solid rgba(var(--ink),.09); border-radius:6px; padding:20px 22px; max-width:760px">'
        + '<div style="display:flex; align-items:center; gap:10px">'
        + '<span style="width:7px; height:7px; border-radius:50%; background:var(--warn); display:inline-block"></span>'
        + '<div style="' + M + '; font-size:11px; letter-spacing:.12em; color:var(--warn)">MATCHING PAIRS ACROSS VENUES…</div></div>'
        // Ohne Dauer liest sich der pulsierende Punkt wie eine kaputte Seite.
        // Er ist keine: der erste Aufruf blaettert beide Boersen durch.
        + '<div style="font-size:13px; color:rgba(var(--ink),.55); margin-top:9px; line-height:1.6">This is a live scan, not a stored file: /api/cross pages both venues and scores every title pair, which takes up to a minute on a cold cache. The gate then keeps only ' + CROSS_GATE_TEXT + '. If it fails you will see the error and a retry here, not this spinner.</div>'
        + '</div></div>';
    } else if (hk.quelle === 'fehler') {
      body = leerBlock('NO PAIRS', herkunftSatz(hk, '/api/cross'))
        + (T.neuLaden ? '<div style="padding:0 24px 24px"><div ' + T.act(() => T.neuLaden('cross', 'cross')) + ' class="hv-bd32" style="display:inline-block; ' + M + '; font-size:11px; color:rgba(var(--ink),.7); border:1px solid rgba(var(--ink),.16); border-radius:4px; padding:6px 12px; cursor:pointer">Try again</div></div>' : '');
    } else {
      body = crossGateBlock(T);
    }
    return '<div>' + seitenKopf('CROSS-VENUE', 'The same question, two prices', 'var(--info)') + body + '</div>';
  }
  // Local filters can only tighten what the server let through.
  let cRows = T.crossPairs.filter((c) => Math.abs(c.pm - c.ks) >= s.crossMinGap && c.sim >= s.crossSim && c.pmVol >= s.crossPmVol && c.ksVol >= s.crossKsVol);
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
    s.crossKsVol > 0 ? ['Kalshi volume > $' + num(s.crossKsVol)] : [],
    s.crossLower !== 'any' ? ['cheaper on ' + s.crossLower] : [],
    (s.crossMinPrice !== 0 || s.crossMaxPrice !== 100) ? ['yes price ' + s.crossMinPrice + '–' + s.crossMaxPrice + '¢'] : []
  );

  const stepGroup = (label, valueLabel, onDown, onUp) =>
    '<div><div style="' + LBL9 + '">' + label + '</div>'
    + '<div style="display:flex; align-items:center; gap:6px">'
    + '<div ' + T.act(onDown) + ' class="hv-bd35w" style="width:26px; height:30px; flex:none; border:1px solid rgba(var(--ink),.16); border-radius:4px; display:flex; align-items:center; justify-content:center; ' + M + '; font-size:13px; color:rgba(var(--ink),.7); cursor:pointer">−</div>'
    + '<div style="flex:1; background:var(--panel); border:1px solid rgba(var(--ink),.16); border-radius:4px; padding:6px 8px; ' + M + '; font-size:12px; text-align:center">' + esc(valueLabel) + '</div>'
    + '<div ' + T.act(onUp) + ' class="hv-bd35w" style="width:26px; height:30px; flex:none; border:1px solid rgba(var(--ink),.16); border-radius:4px; display:flex; align-items:center; justify-content:center; ' + M + '; font-size:13px; color:rgba(var(--ink),.7); cursor:pointer">+</div>'
    + '</div></div>';

  return '<div>'
    + '<div style="padding:20px 24px 14px; border-bottom:1px solid rgba(var(--ink),.09)">'
    + '<div style="display:flex; align-items:flex-end; justify-content:space-between; gap:20px">'
    + '<div><div style="' + M + '; font-size:11px; letter-spacing:.18em; color:var(--info)">CROSS-VENUE</div>'
    + '<h1 style="font-size:21px; line-height:1.25; margin:6px 0 0; font-weight:600; letter-spacing:-0.01em">The same question, two prices</h1></div>'
    + '<div style="display:flex; align-items:center; gap:10px">'
    + asOfLine(cl.as_of)
    + '<input value="' + esc(s.crossQuery) + '" ' + T.inp((e) => T.setState({ crossQuery: e.target.value }), 'crossQuery') + ' placeholder="bitcoin, fed, election…" style="background:var(--panel); border:1px solid rgba(var(--ink),.35); border-radius:4px; padding:9px 12px; ' + M + '; font-size:12.5px; color:var(--text); width:230px" />'
    + '<div ' + T.act(() => T.setState({ crossQuery: '', crossSim: 0.5, crossMaxPairs: 50, crossMinGap: 0, crossLower: 'any', crossPmVol: 0, crossKsVol: 0, crossMinPrice: 0, crossMaxPrice: 100 })) + ' class="hv-bd32" style="font-size:12.5px; color:rgba(var(--ink),.6); border:1px solid rgba(var(--ink),.16); border-radius:4px; padding:9px 13px; cursor:pointer">Reset filters</div>'
    + '</div></div>'
    + '<div style="font-size:13px; color:rgba(var(--ink),.55); margin-top:10px; max-width:760px">Matched by title similarity, not by ticker. ' + esc(gateNote) + '. GAP is the distance between the two mid prices; nobody trades a mid. NET OF FEES prices the basket that would capture it — buy the yes side at the ask, buy the other side at the other venue&#39;s ask — and subtracts both venues&#39; taker fee curves. Settlement rules and resolution sources still differ, and two matched titles can still be two different questions (studies 08 and 11).</div>'

    + '<div style="border:1px solid rgba(var(--ink),.09); border-radius:6px; margin-top:14px; padding:16px; display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:16px 18px">'
    + stepGroup('MIN SIMILARITY (GATE 0.50)', s.crossSim.toFixed(2), () => T.setState({ crossSim: Math.max(0.5, +(s.crossSim - 0.02).toFixed(2)) }), () => T.setState({ crossSim: Math.min(0.9, +(s.crossSim + 0.02).toFixed(2)) }))
    + stepGroup('MAX PAIRS', String(s.crossMaxPairs), () => T.setState({ crossMaxPairs: Math.max(10, s.crossMaxPairs - 10) }), () => T.setState({ crossMaxPairs: Math.min(150, s.crossMaxPairs + 10) }))
    + stepGroup('MIN GAP (¢)', s.crossMinGap.toFixed(1) + '¢', () => T.setState({ crossMinGap: Math.max(0, s.crossMinGap - 0.5) }), () => T.setState({ crossMinGap: s.crossMinGap + 0.5 }))
    + '<div><div style="' + LBL9 + '">LOWER YES ON</div><div style="display:flex; gap:6px">'
    + [['any','Any'],['Polymarket','Polymarket'],['Kalshi','Kalshi']].map((o) => T.opt(o[1], s.crossLower === o[0], { crossLower: o[0] })).join('')
    + '</div></div>'
    + stepGroup('MIN POLYMARKET VOLUME', s.crossPmVol ? '$' + num(s.crossPmVol) : 'any', () => T.setState({ crossPmVol: Math.max(0, s.crossPmVol - 250000) }), () => T.setState({ crossPmVol: s.crossPmVol + 250000 }))
    + stepGroup('MIN KALSHI VOLUME', s.crossKsVol ? '$' + num(s.crossKsVol) : 'any', () => T.setState({ crossKsVol: Math.max(0, s.crossKsVol - 100000) }), () => T.setState({ crossKsVol: s.crossKsVol + 100000 }))
    + stepGroup('MIN YES PRICE', s.crossMinPrice + '¢', () => T.setState({ crossMinPrice: Math.max(0, s.crossMinPrice - 5) }), () => T.setState({ crossMinPrice: Math.min(s.crossMaxPrice, s.crossMinPrice + 5) }))
    + stepGroup('MAX YES PRICE', s.crossMaxPrice + '¢', () => T.setState({ crossMaxPrice: Math.max(s.crossMinPrice, s.crossMaxPrice - 5) }), () => T.setState({ crossMaxPrice: Math.min(100, s.crossMaxPrice + 5) }))
    + '</div>'

    + '<div style="display:flex; align-items:center; gap:8px; margin-top:12px; flex-wrap:wrap">'
    + activeChips.map((c) => '<div style="' + M + '; font-size:11px; color:rgba(var(--ink),.7); border:1px solid rgba(var(--ink),.14); background:var(--panel-hover); border-radius:4px; padding:3px 9px">' + esc(c) + '</div>').join('')
    + '</div></div>'

    + '<div style="display:grid; grid-template-columns:repeat(4,1fr); border-bottom:1px solid rgba(var(--ink),.09)">'
    + '<div style="padding:14px 24px; border-right:1px solid rgba(var(--ink),.09)"><div style="' + HEAD_CELL + '">PAIRS SHOWN</div><div style="' + M + '; font-size:22px; margin-top:7px">' + cRows.length + '</div></div>'
    + '<div style="padding:14px 24px; border-right:1px solid rgba(var(--ink),.09)"><div style="' + HEAD_CELL + '">LARGEST GAP</div><div style="' + M + '; font-size:22px; margin-top:7px; color:var(--warn)">' + (gaps.length ? gaps[gaps.length - 1] + '¢' : '—') + '</div></div>'
    + '<div style="padding:14px 24px; border-right:1px solid rgba(var(--ink),.09)"><div style="' + HEAD_CELL + '">MEDIAN SIMILARITY</div><div style="' + M + '; font-size:22px; margin-top:7px">' + (medianSim ? medianSim.toFixed(2) : '—') + '</div></div>'
    + '<div style="padding:14px 24px"><div style="' + HEAD_CELL + '">POSITIVE NET OF FEES</div><div style="' + M + '; font-size:22px; margin-top:7px; color:' + (netPositive ? 'var(--pos)' : 'rgba(var(--ink),.6)') + '">' + netPositive + ' of ' + netKnown + '</div></div>'
    + '</div>'

    + '<div style="display:grid; grid-template-columns:1fr 118px 118px 96px 110px 118px; padding:10px 24px; border-bottom:1px solid rgba(var(--ink),.09); background:var(--panel); position:sticky; top:0; z-index:3; ' + HEAD_CELL + '">'
    + '<div>EVENT</div><div style="text-align:right">POLYMARKET</div><div style="text-align:right">KALSHI</div><div style="text-align:right">GAP</div><div style="text-align:right">VOLUME 24H</div><div style="text-align:right">NET OF FEES</div></div>'
    + cRows.map((c) => {
      const g = Math.abs(c.pm - c.ks);
      const gapStyle = M + '; font-size:14px; text-align:right; color:' + (g >= 5 ? 'var(--warn)' : g >= 3 ? 'var(--text)' : 'rgba(var(--ink),.5)');
      // Die letzte Spalte hiess HELD FOR und war in jeder Zeile ein Strich:
      // der Server hat nie etwas anderes geliefert. Hier steht jetzt die
      // einzige Zahl der Tabelle, die als Vorteil gelesen werden darf.
      const netFarbe = c.net == null ? 'rgba(var(--ink),.45)' : c.net > 0 ? 'var(--pos)' : 'rgba(var(--ink),.5)';
      const netLabel = c.net == null ? '—' : (c.net > 0 ? '+' : '') + c.net.toFixed(1) + '¢';
      return '<div style="display:grid; grid-template-columns:1fr 118px 118px 96px 110px 118px; align-items:center; padding:13px 24px; border-bottom:1px solid rgba(var(--ink),.06)">'
        + '<div style="padding-right:20px"><div style="font-size:13.5px; line-height:1.35">' + esc(c.event) + '</div>'
        + '<div style="' + M + '; font-size:10.5px; color:rgba(var(--ink),.6); margin-top:3px">' + esc(c.cat) + ' · similarity ' + c.sim.toFixed(2) + '</div></div>'
        + '<div style="' + M + '; font-size:14px; text-align:right; color:var(--accent)">' + c.pm + '¢</div>'
        + '<div style="' + M + '; font-size:14px; text-align:right; color:var(--info)">' + c.ks + '¢</div>'
        + '<div style="' + gapStyle + '">' + g + '¢</div>'
        + '<div style="' + M + '; font-size:12.5px; text-align:right; color:rgba(var(--ink),.6)">' + money(c.pmVol + c.ksVol) + '</div>'
        + '<div style="' + M + '; font-size:13px; text-align:right; color:' + netFarbe + '" title="' + esc(c.net == null ? 'no two-sided quote on both venues' : (c.dir || '') + ' · executable ' + (c.gross == null ? '—' : c.gross.toFixed(1) + '¢') + ' minus a fee threshold of ' + (c.band == null ? '—' : c.band.toFixed(1) + '¢')) + '">' + netLabel + '</div></div>';
    }).join('')
    + (cRows.length === 0 ? '<div style="padding:60px; text-align:center; ' + M + '; font-size:12px; color:rgba(var(--ink),.55)">No pair passes the local filters; loosen a stepper above.</div>' : '')
    + '</div>';
}

// ---------------------------------------------------------------- resolved
export function renderResolved(T) {
  const s = T.state;
  const live = T.liveData.resolved;
  // Ohne Antwort keine Zeilen. Hier lagen sechs erfundene Maerkte samt
  // Ausgang, und die Kennzahl darueber hiess "how far the crowd was off" —
  // eine Fehlermessung an Zahlen, die niemand gemessen hat.
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
    if (s.resError !== 'all' && r.err < Number(s.resError)) return false;
    if (s.resQuery.trim() && r.title.toLowerCase().indexOf(s.resQuery.trim().toLowerCase()) < 0) return false;
    return true;
  });
  const volValue = (v) => parseFloat(String(v).replace(/[$,]/g, '')) * (String(v).indexOf('m') >= 0 ? 1e6 : String(v).indexOf('k') >= 0 ? 1e3 : 1) || 0;
  resRows = resRows.sort((a, b) => (s.resSort === 'error' ? b.err - a.err : s.resSort === 'volume' ? volValue(b.vol) - volValue(a.vol) : a.hours - b.hours));
  const avgErr = resRows.length ? Math.round(resRows.reduce((a, r) => a + r.err, 0) / resRows.length) : 0;
  const worst = resRows.reduce((a, r) => (r.err > (a ? a.err : -1) ? r : a), null);
  const kpis = [
    { label: 'MARKETS SHOWN', value: String(resRows.length) },
    { label: 'CROWD OFF BY, ON AVERAGE', value: avgErr + '¢' },
    { label: 'BIGGEST SURPRISE', value: worst ? worst.err + '¢' : '—', amber: true },
    { label: 'ENDED YES', value: resRows.filter((r) => r.yes).length + ' of ' + resRows.length }
  ];

  return '<div>'
    + '<div style="padding:20px 24px 14px; border-bottom:1px solid rgba(var(--ink),.09)">'
    + '<div style="display:flex; align-items:flex-end; justify-content:space-between; gap:20px">'
    + '<div><div style="' + M + '; font-size:11px; letter-spacing:.18em; color:var(--accent)">RESOLVED</div>'
    + '<h1 style="font-size:21px; line-height:1.25; margin:6px 0 0; font-weight:600; letter-spacing:-0.01em">How the last questions ended</h1></div>'
    + '<input value="' + esc(s.resQuery) + '" ' + T.inp((e) => T.setState({ resQuery: e.target.value }), 'resQuery') + ' placeholder="Search resolved markets…" style="background:var(--panel); border:1px solid rgba(var(--ink),.35); border-radius:4px; padding:9px 12px; ' + M + '; font-size:12.5px; color:var(--text); width:250px" />'
    + '</div>'
    + '<div style="font-size:13px; color:rgba(var(--ink),.55); margin-top:10px; max-width:700px">The last price before settlement next to the answer. The gap between the two is what the crowd got wrong.</div>'
    + '<div style="display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:14px 18px; margin-top:14px">'
    + filterGroup('ANSWER', [['all','All'],['yes','Ended Yes'],['no','Ended No']].map((o) => T.opt(o[1], s.resAnswer === o[0], { resAnswer: o[0] })).join(''))
    + filterGroup('SETTLED WITHIN', [['all','All'],['24','24 hours'],['168','7 days']].map((o) => T.opt(o[1], s.resWindow === o[0], { resWindow: o[0] })).join(''))
    + filterGroup('CROWD WAS OFF BY', [['all','Any'],['25','25¢ or more'],['50','50¢ or more']].map((o) => T.opt(o[1], s.resError === o[0], { resError: o[0] })).join(''))
    + filterGroup('SORT BY', [['recent','Most recent'],['error','Biggest surprise'],['volume','Volume']].map((o) => T.opt(o[1], s.resSort === o[0], { resSort: o[0] })).join(''))
    + '</div></div>'

    + '<div style="display:grid; grid-template-columns:repeat(4,1fr); border-bottom:1px solid rgba(var(--ink),.09)">'
    + kpis.map((k, i) =>
      '<div style="padding:14px 24px' + (i < 3 ? '; border-right:1px solid rgba(var(--ink),.09)' : '') + '">'
      + '<div style="' + HEAD_CELL + '">' + k.label + '</div>'
      + '<div style="' + M + '; font-size:22px; margin-top:7px; color:' + (k.amber ? 'var(--warn)' : 'var(--text)') + '">' + k.value + '</div></div>'
    ).join('')
    + '</div>'

    + '<div style="display:grid; grid-template-columns:1fr 110px 118px 128px 110px 120px; padding:10px 24px; border-bottom:1px solid rgba(var(--ink),.09); background:var(--panel); position:sticky; top:0; z-index:3; ' + HEAD_CELL + '">'
    + '<div>MARKET</div><div style="text-align:right">ANSWER</div><div style="text-align:right">LAST PRICE</div><div style="text-align:right">CROWD OFF BY</div><div style="text-align:right">VOLUME</div><div style="text-align:right">SETTLED</div></div>'
    + resRows.map((r) => {
      const answerStyle = M + '; font-size:11px; letter-spacing:.1em; border-radius:4px; padding:3px 10px; ' + (r.yes ? 'color:var(--on-accent); background:var(--accent)' : 'color:var(--neg-soft); border:1px solid rgba(var(--neg-rgb),.35)');
      const errStyle = M + '; font-size:14px; text-align:right; color:' + (r.err >= 50 ? 'var(--neg)' : r.err >= 25 ? 'var(--warn)' : 'rgba(var(--ink),.6)');
      return '<div style="display:grid; grid-template-columns:1fr 110px 118px 128px 110px 120px; align-items:center; padding:13px 24px; border-bottom:1px solid rgba(var(--ink),.06)">'
        + '<div style="padding-right:20px"><div style="font-size:13.5px; line-height:1.35">' + esc(r.title) + '</div>'
        + '<div style="' + M + '; font-size:10.5px; color:rgba(var(--ink),.6); margin-top:3px">' + esc(r.meta) + '</div></div>'
        + '<div style="display:flex; justify-content:flex-end"><div style="' + answerStyle + '">' + (r.yes ? 'YES' : 'NO') + '</div></div>'
        + '<div style="' + M + '; font-size:14px; text-align:right">' + r.last + '¢</div>'
        + '<div style="' + errStyle + '">' + r.err + '¢</div>'
        + '<div style="' + M + '; font-size:12.5px; text-align:right; color:rgba(var(--ink),.6)">' + esc(r.vol) + '</div>'
        + '<div style="' + M + '; font-size:12px; text-align:right; color:rgba(var(--ink),.6)">' + esc(r.when) + '</div></div>';
    }).join('')
    + '</div>';
}
