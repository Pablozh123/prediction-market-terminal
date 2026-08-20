// Overview (research landing), Markets, Live tape, Cross-venue, Resolved.
// Markup ported from the design reference; data flows through the Terminal
// instance (T). Nothing here invents a number: every figure names its payload
// or the panel says which payload is missing.

import { esc, money, num, herkunftSatz, leerBlock, leerZeile, seitenKopf, catChipsPresent, signedMoney, stempel } from '../util.js';
import { studieAnker } from './microstructure_page.js';

const M = "font-family:'JetBrains Mono',monospace";
const LBL9 = M + '; font-size:9px; letter-spacing:.14em; color:rgba(255,255,255,.42); margin-bottom:6px';
const HEAD_CELL = M + '; font-size:9.5px; letter-spacing:.14em; color:rgba(255,255,255,.45)';
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
  return iso ? '<span style="' + M + '; font-size:10px; color:rgba(255,255,255,.35)">as of ' + esc(stempel(iso)) + '</span>' : '';
}

// Spaltenraster der Markttabelle — Kopfzeile und Zeilen teilen es.
const MARKT_SPALTEN = '1fr 64px 90px 76px 96px 104px 96px';

function marketRowHtml(v) {
  return '<div ' + v.act + ' class="hv-panel" style="display:grid; grid-template-columns:' + MARKT_SPALTEN + '; align-items:center; padding:13px 24px; border-bottom:1px solid rgba(255,255,255,.06); cursor:pointer; animation:rowIn .25s ease-out">'
    + '<div style="padding-right:20px">'
    + '<div style="font-size:13.5px; line-height:1.35">' + esc(v.title) + '</div>'
    + '<div style="' + M + '; font-size:10.5px; color:rgba(255,255,255,.45); margin-top:3px">' + esc(v.meta) + '</div></div>'
    + '<div style="' + M + '; font-size:15px; text-align:right">' + v.priceLabel + '</div>'
    + '<div style="' + v.changeStyle + '">' + v.changeLabel + '</div>'
    + '<div style="' + M + '; font-size:12px; text-align:right; color:rgba(255,255,255,.55)">' + esc(v.spreadLabel || '—') + '</div>'
    + '<div style="' + M + '; font-size:12px; text-align:right; color:rgba(255,255,255,.55)">' + esc(v.liqLabel || '—') + '</div>'
    + '<div style="' + M + '; font-size:13px; text-align:right">' + v.volLabel + '</div>'
    + '<div style="' + M + '; font-size:12px; text-align:right; color:rgba(255,255,255,.55)">' + esc(v.ends) + '</div></div>';
}

// One compact insight panel on the Markets page: a heading, up to five
// clickable rows (each opens its market), and an honest line when the
// loaded sample has nothing that qualifies.
function insightPanel(titel, sub, rowsHtml, leerSatz) {
  return '<div style="background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:10px; overflow:hidden">'
    + '<div style="padding:9px 14px; border-bottom:1px solid rgba(255,255,255,.08)"><span style="' + M + '; font-size:10px; letter-spacing:.13em; color:#C8F542">' + titel + '</span>'
    + (sub ? ' <span style="' + M + '; font-size:9.5px; color:rgba(255,255,255,.35); letter-spacing:0">· ' + sub + '</span>' : '') + '</div>'
    + (rowsHtml || '<div style="padding:12px 14px; ' + M + '; font-size:10.5px; color:rgba(255,255,255,.35)">' + esc(leerSatz) + '</div>')
    + '</div>';
}

// ---------------------------------------------------------------- overview (research landing)

// Verdict vocabulary of public/data/microstructure.json (verdikt_art) as a
// tag: label, colour. Anything unknown renders its raw value, uncoloured.
const VERDICT_TAG = {
  ja: { label: 'CONFIRMED', color: '#C8F542', bg: 'rgba(200,245,66,.12)' },
  nein: { label: 'REFUTED', color: '#FF7A7A', bg: 'rgba(255,69,69,.12)' },
  offen: { label: 'NOT IDENTIFIED', color: '#F5A623', bg: 'rgba(245,166,35,.12)' },
  kontrolle: { label: 'CONTROL', color: '#4F8EF7', bg: 'rgba(79,142,247,.14)' }
};

function verdictTag(art) {
  const v = VERDICT_TAG[String(art || '').toLowerCase()];
  const label = v ? v.label : String(art || '—').toUpperCase();
  const style = M + '; font-size:9.5px; letter-spacing:.12em; border-radius:4px; padding:3px 8px; white-space:nowrap; '
    + (v ? 'color:' + v.color + '; background:' + v.bg : 'color:rgba(255,255,255,.55); border:1px solid rgba(255,255,255,.16)');
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
  return '<div style="display:flex; align-items:center; justify-content:space-between; gap:12px; padding:12px 24px; border-bottom:1px solid rgba(255,255,255,.09); background:#10151A">'
    + '<div style="' + M + '; font-size:11px; letter-spacing:.16em; color:' + (color || '#C8F542') + '">' + label + '</div>'
    + '<div style="display:flex; align-items:center; gap:14px">' + (right || '') + '</div></div>';
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
    ? '<div ' + goStudy(i) + ' class="hv-lime" style="' + M + '; font-size:11px; color:' + (color || 'rgba(255,255,255,.45)') + '; cursor:pointer; white-space:nowrap">' + label + ' →</div>'
    : '');

  // ---- verdict board -----------------------------------------------------
  const studien = micro && Array.isArray(micro.studien) ? micro.studien : [];
  const counts = verdictCounts(micro);
  let board;
  if (studien.length) {
    board = '<div style="display:grid; grid-template-columns:36px 1fr 128px 190px 150px; padding:9px 24px; border-bottom:1px solid rgba(255,255,255,.09); ' + HEAD_CELL + '">'
      + '<div>#</div><div>QUESTION</div><div>VERDICT</div><div style="text-align:right">KEY NUMBER · N</div><div style="text-align:right">WINDOW</div></div>'
      + studien.map((st, i) => {
        const kn = keyNumber(st);
        const basis = st.basis || {};
        const nLabel = sampleLabel(basis);
        // Jede Zeile fuehrt direkt zu ihrer Karte auf der Microstructure-Seite,
        // nicht zum Seitenanfang: gleicher Anker wie die Sprungliste dort.
        return '<div ' + goStudy(microIdx, studieAnker(st, i)) + ' class="hv-panel" style="display:grid; grid-template-columns:36px 1fr 128px 190px 150px; align-items:center; padding:11px 24px; border-bottom:1px solid rgba(255,255,255,.06); cursor:pointer; animation:rowIn .25s ease-out">'
          + '<div style="' + M + '; font-size:11px; color:rgba(255,255,255,.4)">' + String(i + 1).padStart(2, '0') + '</div>'
          + '<div style="padding-right:16px; min-width:0"><div style="font-size:13.5px; line-height:1.35">' + esc(st.frage || st.id || '—') + '</div>'
          // Truncated lines carry the full text as a tooltip.
          + '<div style="' + M + '; font-size:10.5px; color:rgba(255,255,255,.45); margin-top:3px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="' + esc(String(st.verdikt || '')) + '">' + esc(String(st.verdikt || '').split('. ')[0]) + '</div></div>'
          + '<div>' + verdictTag(st.verdikt_art) + '</div>'
          + '<div style="text-align:right; min-width:0"><div style="' + M + '; font-size:14px">' + esc(kn.value) + (kn.unit ? ' <span style="font-size:10px; color:rgba(255,255,255,.45)">' + esc(kn.unit) + '</span>' : '') + '</div>'
          + '<div style="' + M + '; font-size:10px; color:rgba(255,255,255,.4); margin-top:2px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="' + esc(kn.label + (nLabel ? ' · ' + nLabel : '')) + '">' + esc(kn.label) + (nLabel ? ' · ' + esc(nLabel) : '') + '</div></div>'
          + '<div style="' + M + '; font-size:11px; text-align:right; color:rgba(255,255,255,.5)">' + esc(basis.fenster || '—') + '</div></div>';
      }).join('');
  } else {
    board = leerZeile(landingLeerSatz(hk.micro, 'microstructure.json'));
  }

  // ---- live-runs strip ----------------------------------------------------
  const agg = runs && runs.aggregat ? runs.aggregat : null;
  // Eine PnL-Zelle, nicht zwei: die Wallet-Zahl fuehrt (frischeste Quelle
  // zuerst — der Ledger aus extras, sonst der kuratierte Abgleich), die
  // Log-Schaetzung steht in der Unterzeile. Die Methodennote dazu traegt die
  // Live-runs-Seite unter LOG VS WALLET, nicht die Landung.
  const ledger = runs && runs.extras && runs.extras.wallet_ledger;
  const ledgerBot = ledger && ledger.aggregat && ledger.aggregat.nach_typ ? ledger.aggregat.nach_typ.bot : null;
  const ledgerStand = ledger && ledger.stand_utc ? String(ledger.stand_utc).slice(0, 10) : '';
  const abgleichStand = agg && agg.wallet_abgleich_stand ? String(agg.wallet_abgleich_stand) : '';
  const walletNetto = ledgerBot && ledgerBot.netto_cash_usd != null && ledgerStand && (!abgleichStand || ledgerStand > abgleichStand)
    ? { wert: +ledgerBot.netto_cash_usd, stand: ledgerStand, quelle: 'wallet ledger' }
    : agg && agg.wallet_netto_usd != null
      ? { wert: +agg.wallet_netto_usd, stand: abgleichStand, quelle: 'on-chain wallet' }
      : null;
  const logSchaetzung = agg && agg.realisierter_pnl_usd != null ? signedMoney(agg.realisierter_pnl_usd) : '—';
  const pnlZelle = walletNetto
    ? kpiCell('NET PNL (WALLET)', signedMoney(walletNetto.wert),
      esc(walletNetto.quelle) + (walletNetto.stand ? ' · reconciled ' + esc(walletNetto.stand) : '') + ' · log estimate ' + logSchaetzung, true, walletNetto.wert)
    : kpiCell('NET PNL (LOG ESTIMATE)', logSchaetzung, 'from run logs; fill prices partly assumed · no wallet reconciliation yet', true, agg && agg.realisierter_pnl_usd);
  const runsStrip = agg
    ? '<div style="display:grid; grid-template-columns:repeat(4,1fr); border-bottom:1px solid rgba(255,255,255,.09)">'
      + kpiCell('RUNS · BETS', num(agg.n_runs != null ? agg.n_runs : '—') + ' · ' + num(agg.n_wetten != null ? agg.n_wetten : '—'), 'stake ' + (agg.einsatz_usd != null ? '$' + num((+agg.einsatz_usd).toFixed(0)) : '—') + ' (log estimate)'
        + (runs && runs.stand_utc ? ' · payload ' + esc(stempel(runs.stand_utc)) : ''), true)
      + kpiCell('WON · LOST', num(agg.gewonnen != null ? agg.gewonnen : '—') + ' · ' + num(agg.verloren != null ? agg.verloren : '—'), (agg.offen ? num(agg.offen) + ' open' : 'none open') + ' · no profitability claim', true)
      + pnlZelle
      + kpiCell('VISIBLE DEPTH AT ENTRY', agg.sichtbare_tiefe_usd != null ? '$' + num((+agg.sichtbare_tiefe_usd).toFixed(0)) : '—', agg.einsatz_zu_sichtbarer_tiefe_pct != null ? 'stake was ' + (+agg.einsatz_zu_sichtbarer_tiefe_pct).toFixed(1) + '% of visible depth' : '', false)
      + '</div>'
    : leerZeile(landingLeerSatz(hk.runs, 'runs.json'));

  // ---- field-notes strip --------------------------------------------------
  const noteList = notes && Array.isArray(notes.notes) ? notes.notes.slice(0, 5) : [];
  const notesStrip = noteList.length
    ? noteList.map((n) =>
      '<div ' + goStudy(notesIdx) + ' class="hv-panel" style="display:grid; grid-template-columns:96px 1fr 120px; gap:12px; align-items:center; padding:11px 24px; border-bottom:1px solid rgba(255,255,255,.06); cursor:pointer">'
      + '<div style="' + M + '; font-size:11px; color:rgba(255,255,255,.45)">' + esc(String(n.date || '').slice(0, 10)) + '</div>'
      + '<div style="font-size:13px; line-height:1.35">' + esc(n.title || '—') + '</div>'
      + '<div style="' + M + '; font-size:10.5px; color:rgba(255,255,255,.45); text-align:right">' + esc(n.venue || '') + '</div></div>'
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
  const liveRow = '<div style="display:grid; grid-template-columns:repeat(3,1fr); border-bottom:1px solid rgba(255,255,255,.09)">'
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
    + pfadKarte(goStudy(runsIdx), 'TESTED STRATEGY', '#C8F542', 'Researched, then run with real money: every bet, its latency and the on-chain wallet that proves it.')
    + pfadKarte(T.act(() => T.go('markets')), 'ANALYSIS TOOL', '#4F8EF7', 'Live screens on Polymarket & Kalshi: markets, tape, whale flow, cross-venue, risk.')
    + '</div>';
  return '<div>'
    + '<div style="padding:24px 24px 20px; border-bottom:1px solid rgba(255,255,255,.09)">'
    + '<div style="font-family:\'Instrument Serif\',serif; font-size:34px; line-height:1.08">Prediction-market microstructure, <em style="color:#C8F542">measured on self-recorded books.</em></div>'
    + '<div style="font-size:14px; color:rgba(255,255,255,.66); margin-top:8px; max-width:760px">' + esc(subline) + '</div>'
    + pfade
    + '<div style="display:flex; gap:14px; margin-top:14px; flex-wrap:wrap; ' + M + '; font-size:11px">'
    + '<a href="' + REPO_URL + '" target="_blank" rel="noopener">GitHub repository →</a>'
    + '<a href="' + ONE_PAGER_URL + '" target="_blank" rel="noopener">One-pager (docs/research/ONE_PAGER.md) →</a>'
    + (pilotIdx >= 0 ? '<span ' + goStudy(pilotIdx) + ' class="hv-lime" style="color:rgba(255,255,255,.55); cursor:pointer">Pre-registered pilot →</span>' : '')
    + '</div></div>'

    // Die getestete Strategie zuerst — sie ist das Argument der Seite; die
    // Studien liefern die Begruendung darunter.
    + sectionHead('TESTED STRATEGY · LIVE RUNS, REAL MONEY', link(runsIdx, 'EVERY BET'))
    + runsStrip

    + sectionHead('VERDICT BOARD · ' + (studien.length ? num(counts.total) + ' STUDIES' : 'MICROSTRUCTURE'),
      (micro && micro.stand_utc ? '<span style="' + M + '; font-size:10px; color:rgba(255,255,255,.35)">payload ' + esc(stempel(micro.stand_utc)) + '</span>' : '')
      + link(microIdx, 'FULL REPORT'))
    + board

    + sectionHead('FIELD NOTES', link(notesIdx, 'ALL NOTES'), '#4F8EF7')
    + notesStrip

    + sectionHead('ANALYSIS TOOL · LIVE DATA', asOfLine(s.liveAsOf) + '<div ' + T.act(() => T.go('markets')) + ' class="hv-lime" style="' + M + '; font-size:11px; color:rgba(255,255,255,.45); cursor:pointer">MARKETS →</div><div ' + T.act(() => T.go('flow')) + ' class="hv-lime" style="' + M + '; font-size:11px; color:rgba(255,255,255,.45); cursor:pointer">TAPE →</div>')
    + liveRow
    + '<div style="padding:22px 24px; text-align:center; ' + M + '; font-size:11px; color:rgba(255,255,255,.35)">Public data only · live blocks refresh every 30 seconds · research payloads are frozen files under ./data</div>'
    + '</div>';
}

// One of the two entry cards under the landing title; act is empty when the
// target study is not in the list, the card then renders without a cursor.
function pfadKarte(act, label, farbe, satz) {
  return '<div ' + act + (act ? ' class="hv-panel"' : '') + ' style="background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:12px; padding:14px 16px' + (act ? '; cursor:pointer' : '') + '">'
    + '<div style="' + M + '; font-size:10px; letter-spacing:.16em; color:' + farbe + '">' + label + ' →</div>'
    + '<div style="font-size:12.5px; color:rgba(255,255,255,.6); margin-top:6px; line-height:1.5">' + satz + '</div></div>';
}

function kpiCell(label, value, sub, borderRight, signed) {
  const color = signed == null ? '#ffffff' : (+signed >= 0 ? '#C8F542' : '#FF4545');
  return '<div style="padding:16px 20px' + (borderRight ? '; border-right:1px solid rgba(255,255,255,.09)' : '') + '">'
    + '<div style="' + M + '; font-size:10px; letter-spacing:.14em; color:rgba(255,255,255,.45)">' + label + '</div>'
    + '<div style="' + M + '; font-size:24px; margin-top:8px; color:' + color + '">' + value + '</div>'
    + '<div style="' + M + '; font-size:11px; color:rgba(255,255,255,.45); margin-top:4px">' + sub + '</div></div>';
}

// ---------------------------------------------------------------- markets
export function renderMarkets(T) {
  const s = T.state;
  if (!T.markets.length) {
    return '<div>' + seitenKopf('MARKETS', 'Every market, one table', '#C8F542')
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
    '<div ' + T.act(() => T.openMarket(m.id)) + ' class="hv-panel" style="display:grid; grid-template-columns:1fr 46px 78px; gap:8px; align-items:center; padding:8px 14px; border-bottom:1px solid rgba(255,255,255,.05); cursor:pointer">'
    + '<div style="font-size:12px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="' + esc(m.title) + '">' + esc(m.title) + '</div>'
    + '<div style="' + M + '; font-size:11.5px; text-align:right; color:rgba(255,255,255,.55)">' + mitte + '</div>'
    + '<div style="' + M + '; font-size:11.5px; text-align:right">' + rechts + '</div></div>';
  const kpiStrip = '<div style="display:grid; grid-template-columns:repeat(4,1fr); border:1px solid rgba(255,255,255,.09); border-radius:10px; margin-top:14px; overflow:hidden; background:#10151A">'
    + kpiCell('MARKETS IN SAMPLE', num(T.markets.length), pmAnzahl + ' Polymarket · ' + (T.markets.length - pmAnzahl) + ' Kalshi', true)
    + kpiCell('VOLUME 24H', money(gesamtVol), 'sum over the sample', true)
    + kpiCell('BIGGEST 1D MOVE', topMover ? (topMover.chg >= 0 ? '+' : '') + topMover.chg + '¢' : '—',
      topMover ? esc(kurz(topMover.title)) : 'no market in the sample moved', true, topMover ? topMover.chg : null)
    + kpiCell('MEDIAN SPREAD', spreadMedian != null ? spreadMedian + '¢' : '—',
      spreads.length ? 'n = ' + num(spreads.length) + ' markets with a quoted spread' : 'no spreads in the sample', false)
    + '</div>';
  const einblicke = '<div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(280px, 1fr)); gap:12px; margin-top:12px">'
    + insightPanel('TOP MOVERS · 1D', 'yes price · change',
      movers.map((m) => zeile(m, m.yes + '¢', '<span style="color:' + (m.chg >= 0 ? '#C8F542' : '#FF4545') + '">' + (m.chg >= 0 ? '+' : '') + m.chg + '¢</span>')).join(''),
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

  const badge = mActive.length ? M + '; font-size:10px; color:#0A0D0F; background:#C8F542; border-radius:4px; padding:1px 7px' : 'display:none';
  const chevron = M + '; font-size:16px; color:rgba(255,255,255,.5); transition:transform .18s ease; transform:rotate(' + (s.marketFiltersOpen ? '90deg' : '0deg') + ')';

  return '<div>'
    + '<div style="padding:20px 24px 14px; border-bottom:1px solid rgba(255,255,255,.09)">'
    + '<div style="display:flex; align-items:flex-end; justify-content:space-between; gap:20px">'
    + '<div><div style="' + M + '; font-size:10px; letter-spacing:.18em; color:#C8F542">MARKETS</div>'
    + '<div style="font-family:\'Instrument Serif\',serif; font-size:30px; line-height:1.1; margin-top:5px">Every market, one table</div></div>'
    + '<div style="display:flex; align-items:center; gap:10px">'
    + '<input value="' + esc(s.marketQuery) + '" ' + T.inp((e) => T.setState({ marketQuery: e.target.value }), 'marketQuery') + ' placeholder="Search markets…" style="background:#10151A; border:1px solid rgba(255,255,255,.16); border-radius:8px; padding:9px 12px; ' + M + '; font-size:12.5px; color:#fff; width:230px; outline:none" />'
    + '<div ' + T.act(() => T.setState({ mPlatform: 'all', mStatus: 'active', mProb: 'all', mLiq: 'all', mVol: 'all', mEnds: 'all', mAge: 'all', mExclude: [], marketCat: 'All', marketQuery: '', mQuick: 'trending', marketSort: 'volume' })) + ' class="hv-bd32" style="font-size:12.5px; color:rgba(255,255,255,.6); border:1px solid rgba(255,255,255,.16); border-radius:8px; padding:9px 13px; cursor:pointer">Reset filters</div>'
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

    + '<div style="border:1px solid rgba(255,255,255,.09); border-radius:10px; margin-top:14px; overflow:hidden">'
    + '<div ' + T.act(() => T.setState({ marketFiltersOpen: !s.marketFiltersOpen })) + ' class="hv-el" style="display:flex; align-items:center; justify-content:space-between; padding:11px 15px; background:#10151A; cursor:pointer">'
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
    + '<div style="' + M + '; font-size:11px; color:rgba(255,255,255,.45)">' + mRows.length + ' of ' + T.markets.length + ' markets</div>'
    + mActive.map((c) =>
      '<div ' + T.act(() => T.setState(c.reset)) + ' class="hv-bd30" style="' + M + '; font-size:11px; color:rgba(255,255,255,.7); border:1px solid rgba(255,255,255,.14); background:#161C22; border-radius:6px; padding:3px 9px; cursor:pointer">' + esc(c.label) + ' ✕</div>'
    ).join('')
    + '</div></div>'

    // No TREND column: the API carries a one-day change, not an intraday
    // path, and a two-point line under "TREND 24H" read as a curve. SPREAD
    // und LIQUIDITY kommen aus denselben API-Zeilen (unbekannt bleibt —).
    + '<div style="display:grid; grid-template-columns:' + MARKT_SPALTEN + '; padding:10px 24px; border-bottom:1px solid rgba(255,255,255,.09); background:#10151A; ' + HEAD_CELL + '">'
    + '<div>MARKET</div>'
    + '<div style="text-align:right">YES</div>'
    + '<div ' + T.act(() => T.setState({ marketSort: 'change' })) + ' style="text-align:right; cursor:pointer; color:' + (s.marketSort === 'change' ? '#C8F542' : 'rgba(255,255,255,.45)') + '">CHANGE 1D</div>'
    + '<div style="text-align:right">SPREAD</div>'
    + '<div ' + T.act(() => T.setState({ marketSort: 'liquidity' })) + ' style="text-align:right; cursor:pointer; color:' + (s.marketSort === 'liquidity' ? '#C8F542' : 'rgba(255,255,255,.45)') + '">LIQUIDITY</div>'
    + '<div ' + T.act(() => T.setState({ marketSort: 'volume' })) + ' style="text-align:right; cursor:pointer; color:' + (s.marketSort === 'volume' ? '#C8F542' : 'rgba(255,255,255,.45)') + '">VOLUME 24H</div>'
    + '<div ' + T.act(() => T.setState({ marketSort: 'ending' })) + ' style="text-align:right; cursor:pointer; color:' + (s.marketSort === 'ending' ? '#C8F542' : 'rgba(255,255,255,.45)') + '">RESOLVES</div></div>'
    + mRows.map((m) => marketRowHtml(Object.assign(T.marketView(m), {
      spreadLabel: mx(m).spread != null ? mx(m).spread + '¢' : '—',
      liqLabel: m.liq ? money(m.liq) : '—'
    }))).join('')
    + (mRows.length === 0 ? '<div style="padding:60px; text-align:center; ' + M + '; font-size:12px; color:rgba(255,255,255,.35)">No market matches that filter.</div>' : '')
    + '</div>';
}

// ---------------------------------------------------------------- flow (live tape)
export function renderFlow(T) {
  const s = T.state;
  if (!T.tape.length) {
    return '<div>' + seitenKopf('LIVE TAPE', 'Every large print as it lands', '#C8F542')
      + leerBlock('NO PRINTS', herkunftSatz(T.herkunft.tape, '/api/tape')) + '</div>';
  }
  const tapeFiltered = T.tapeFiltered();
  const tapeNotional = tapeFiltered.reduce((a, t) => a + t.size, 0);
  const tapeWallets = tapeFiltered.filter((t) => t.wallet !== '—').map((t) => t.wallet).filter((v, i, arr) => arr.indexOf(v) === i).length;
  const tapeBiggest = tapeFiltered.reduce((a, t) => Math.max(a, t.size), 0);
  const kpis = [
    { label: 'PRINTS SHOWN', value: String(tapeFiltered.length) },
    { label: 'TOTAL MOVED', value: money(tapeNotional) },
    { label: 'WALLETS INVOLVED', value: String(tapeWallets) },
    { label: 'BIGGEST PRINT', value: money(tapeBiggest) }
  ];

  return '<div>'
    + '<div style="padding:20px 24px 14px; border-bottom:1px solid rgba(255,255,255,.09)">'
    + '<div style="display:flex; align-items:flex-end; justify-content:space-between; gap:20px">'
    + '<div><div style="' + M + '; font-size:10px; letter-spacing:.18em; color:#C8F542">LIVE TAPE</div>'
    + '<div style="font-family:\'Instrument Serif\',serif; font-size:30px; line-height:1.1; margin-top:5px">Every large print as it lands</div></div>'
    + '<div style="display:flex; align-items:center; gap:12px">'
    + asOfLine(s.tapeAsOf || s.liveAsOf)
    + '<input value="' + esc(s.tapeQuery) + '" ' + T.inp((e) => T.setState({ tapeQuery: e.target.value }), 'tapeQuery') + ' placeholder="market, wallet, trader…" style="background:#10151A; border:1px solid rgba(255,255,255,.16); border-radius:8px; padding:9px 12px; ' + M + '; font-size:12.5px; color:#fff; width:250px; outline:none" />'
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

    + '<div style="display:grid; grid-template-columns:repeat(4,1fr); border-bottom:1px solid rgba(255,255,255,.09)">'
    + kpis.map((k, i) =>
      '<div style="padding:14px 24px' + (i < 3 ? '; border-right:1px solid rgba(255,255,255,.09)' : '') + '">'
      + '<div style="' + HEAD_CELL + '">' + k.label + '</div>'
      + '<div style="' + M + '; font-size:22px; margin-top:7px">' + k.value + '</div></div>'
    ).join('')
    + '</div>'

    + '<div style="display:grid; grid-template-columns:96px 160px 1fr 110px 84px 90px 110px 96px; padding:10px 24px; border-bottom:1px solid rgba(255,255,255,.09); background:#10151A; ' + HEAD_CELL + '">'
    + '<div>TIME</div><div>WALLET</div><div>MARKET</div><div>CATEGORY</div><div>SIDE</div><div style="text-align:right">PRICE</div><div style="text-align:right">SIZE</div><div style="text-align:right">VENUE</div></div>'
    + (tapeFiltered.length ? '' : leerZeile('No print in the tape window passes the current filters (size, category, side).'))
    + tapeFiltered.map((t0) => {
      const t = T.tapeRowView(t0);
      // Only a print of a loaded market opens the drawer; the other rows are
      // plain rows, not pointers that lead nowhere.
      const klickbar = t.act && t.clickable !== false;
      return '<div ' + (klickbar ? t.act + ' class="hv-panel"' : '') + ' style="display:grid; grid-template-columns:96px 160px 1fr 110px 84px 90px 110px 96px; align-items:center; padding:12px 24px; border-bottom:1px solid rgba(255,255,255,.06); ' + M + '; font-size:12.5px; ' + (klickbar ? 'cursor:pointer; ' : '') + 'animation:rowIn .25s ease-out">'
        + '<div style="color:rgba(255,255,255,.55)">' + esc(t.ago) + '</div>'
        + '<div style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="' + esc(t.wallet) + '">' + esc(t.wallet) + '</div>'
        + '<div style="font-family:\'Inter\',sans-serif; font-size:13px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; padding-right:12px" title="' + esc(t.market) + '">' + esc(t.market) + '</div>'
        + '<div style="font-size:11px; color:rgba(255,255,255,.55)">' + esc(t.category || 'Other') + '</div>'
        + '<div style="' + t.sideStyle + '">' + esc(t.side) + '</div>'
        + '<div style="text-align:right">' + esc(t.price) + '</div>'
        + '<div style="text-align:right">' + t.size + '</div>'
        + '<div style="text-align:right; color:rgba(255,255,255,.45); font-size:11px">' + esc(t.venue) + '</div></div>';
    }).join('')
    + '</div>';
}

// ---------------------------------------------------------------- cross-venue

// The honesty gate as words, used by both the empty block and the caption.
export const CROSS_GATE_TEXT = 'similarity ≥ 0.5, volume on both venues';

function crossGateBlock(T) {
  const microIdx = T.studies.findIndex((st) => st.tab === 'Microstructure');
  return '<div style="padding:26px 24px">'
    + '<div style="background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:12px; padding:20px 22px; max-width:760px">'
    + '<div style="' + M + '; font-size:10px; letter-spacing:.14em; color:#F5A623">NO PAIR CLEARS THE GATE</div>'
    + '<div style="font-size:13px; color:rgba(255,255,255,.6); margin-top:9px; line-height:1.6">No cross-venue pair clears the match gate right now (' + CROSS_GATE_TEXT + '). '
    + 'See studies 08 and 11: the two 79¢/64¢ \'edges\' were mismatched questions.</div>'
    + (microIdx >= 0 && T.goStudy
      ? '<div ' + T.act(() => T.goStudy(microIdx)) + ' class="hv-lime" style="' + M + '; font-size:11px; color:#4F8EF7; margin-top:12px; cursor:pointer">Open the microstructure report (#research/microstructure) →</div>'
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
        + '<div style="background:#10151A; border:1px solid rgba(255,255,255,.09); border-radius:12px; padding:20px 22px; max-width:760px">'
        + '<div style="display:flex; align-items:center; gap:10px">'
        + '<span style="width:7px; height:7px; border-radius:50%; background:#F5A623; display:inline-block; animation:livePulse 1.2s ease-in-out infinite"></span>'
        + '<div style="' + M + '; font-size:11px; letter-spacing:.12em; color:#F5A623">MATCHING PAIRS ACROSS VENUES…</div></div>'
        + '<div style="font-size:13px; color:rgba(255,255,255,.55); margin-top:9px; line-height:1.6">Waiting for /api/cross. It pages both venues and scores every title pair; the gate keeps only ' + CROSS_GATE_TEXT + '.</div>'
        + '</div></div>';
    } else if (hk.quelle === 'fehler') {
      body = leerBlock('NO PAIRS', herkunftSatz(hk, '/api/cross'))
        + (T.neuLaden ? '<div style="padding:0 24px 24px"><div ' + T.act(() => T.neuLaden('cross', 'cross')) + ' class="hv-bd32" style="display:inline-block; ' + M + '; font-size:11px; color:rgba(255,255,255,.7); border:1px solid rgba(255,255,255,.16); border-radius:6px; padding:6px 12px; cursor:pointer">Try again</div></div>' : '');
    } else {
      body = crossGateBlock(T);
    }
    return '<div>' + seitenKopf('CROSS-VENUE', 'The same question, two prices', '#4F8EF7') + body + '</div>';
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
  const medianGap = gaps.length ? gaps[Math.floor(gaps.length / 2)] : 0;
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
    + '<div ' + T.act(onDown) + ' class="hv-bd35w" style="width:26px; height:30px; flex:none; border:1px solid rgba(255,255,255,.16); border-radius:7px; display:flex; align-items:center; justify-content:center; ' + M + '; font-size:13px; color:rgba(255,255,255,.7); cursor:pointer">−</div>'
    + '<div style="flex:1; background:#10151A; border:1px solid rgba(255,255,255,.16); border-radius:7px; padding:6px 8px; ' + M + '; font-size:12px; text-align:center">' + esc(valueLabel) + '</div>'
    + '<div ' + T.act(onUp) + ' class="hv-bd35w" style="width:26px; height:30px; flex:none; border:1px solid rgba(255,255,255,.16); border-radius:7px; display:flex; align-items:center; justify-content:center; ' + M + '; font-size:13px; color:rgba(255,255,255,.7); cursor:pointer">+</div>'
    + '</div></div>';

  return '<div>'
    + '<div style="padding:20px 24px 14px; border-bottom:1px solid rgba(255,255,255,.09)">'
    + '<div style="display:flex; align-items:flex-end; justify-content:space-between; gap:20px">'
    + '<div><div style="' + M + '; font-size:10px; letter-spacing:.18em; color:#4F8EF7">CROSS-VENUE</div>'
    + '<div style="font-family:\'Instrument Serif\',serif; font-size:30px; line-height:1.1; margin-top:5px">The same question, two prices</div></div>'
    + '<div style="display:flex; align-items:center; gap:10px">'
    + asOfLine(cl.as_of)
    + '<input value="' + esc(s.crossQuery) + '" ' + T.inp((e) => T.setState({ crossQuery: e.target.value }), 'crossQuery') + ' placeholder="bitcoin, fed, election…" style="background:#10151A; border:1px solid rgba(255,255,255,.16); border-radius:8px; padding:9px 12px; ' + M + '; font-size:12.5px; color:#fff; width:230px; outline:none" />'
    + '<div ' + T.act(() => T.setState({ crossQuery: '', crossSim: 0.5, crossMaxPairs: 50, crossMinGap: 0, crossLower: 'any', crossPmVol: 0, crossKsVol: 0, crossMinPrice: 0, crossMaxPrice: 100 })) + ' class="hv-bd32" style="font-size:12.5px; color:rgba(255,255,255,.6); border:1px solid rgba(255,255,255,.16); border-radius:8px; padding:9px 13px; cursor:pointer">Reset filters</div>'
    + '</div></div>'
    + '<div style="font-size:13px; color:rgba(255,255,255,.55); margin-top:10px; max-width:760px">Matched by title similarity, not by ticker. ' + esc(gateNote) + '. A gap is not free money — fees, settlement rules and resolution sources differ between the two venues, and two matched titles can still be two different questions (studies 08 and 11).</div>'

    + '<div style="border:1px solid rgba(255,255,255,.09); border-radius:10px; margin-top:14px; padding:16px; display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:16px 18px">'
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
    + activeChips.map((c) => '<div style="' + M + '; font-size:11px; color:rgba(255,255,255,.7); border:1px solid rgba(255,255,255,.14); background:#161C22; border-radius:6px; padding:3px 9px">' + esc(c) + '</div>').join('')
    + '</div></div>'

    + '<div style="display:grid; grid-template-columns:repeat(4,1fr); border-bottom:1px solid rgba(255,255,255,.09)">'
    + '<div style="padding:14px 24px; border-right:1px solid rgba(255,255,255,.09)"><div style="' + HEAD_CELL + '">PAIRS SHOWN</div><div style="' + M + '; font-size:22px; margin-top:7px">' + cRows.length + '</div></div>'
    + '<div style="padding:14px 24px; border-right:1px solid rgba(255,255,255,.09)"><div style="' + HEAD_CELL + '">LARGEST GAP</div><div style="' + M + '; font-size:22px; margin-top:7px; color:#F5A623">' + (gaps.length ? gaps[gaps.length - 1] + '¢' : '—') + '</div></div>'
    + '<div style="padding:14px 24px; border-right:1px solid rgba(255,255,255,.09)"><div style="' + HEAD_CELL + '">MEDIAN SIMILARITY</div><div style="' + M + '; font-size:22px; margin-top:7px">' + (medianSim ? medianSim.toFixed(2) : '—') + '</div></div>'
    + '<div style="padding:14px 24px"><div style="' + HEAD_CELL + '">MEDIAN GAP</div><div style="' + M + '; font-size:22px; margin-top:7px">' + (medianGap ? medianGap + '¢' : '—') + '</div></div>'
    + '</div>'

    + '<div style="display:grid; grid-template-columns:1fr 118px 118px 96px 110px 118px; padding:10px 24px; border-bottom:1px solid rgba(255,255,255,.09); background:#10151A; ' + HEAD_CELL + '">'
    + '<div>EVENT</div><div style="text-align:right">POLYMARKET</div><div style="text-align:right">KALSHI</div><div style="text-align:right">GAP</div><div style="text-align:right">VOLUME 24H</div><div style="text-align:right">HELD FOR</div></div>'
    + cRows.map((c) => {
      const g = Math.abs(c.pm - c.ks);
      const gapStyle = M + '; font-size:14px; text-align:right; color:' + (g >= 5 ? '#F5A623' : g >= 3 ? '#ffffff' : 'rgba(255,255,255,.5)');
      return '<div style="display:grid; grid-template-columns:1fr 118px 118px 96px 110px 118px; align-items:center; padding:13px 24px; border-bottom:1px solid rgba(255,255,255,.06); animation:rowIn .25s ease-out">'
        + '<div style="padding-right:20px"><div style="font-size:13.5px; line-height:1.35">' + esc(c.event) + '</div>'
        + '<div style="' + M + '; font-size:10.5px; color:rgba(255,255,255,.45); margin-top:3px">' + esc(c.cat) + ' · similarity ' + c.sim.toFixed(2) + '</div></div>'
        + '<div style="' + M + '; font-size:14px; text-align:right; color:#C8F542">' + c.pm + '¢</div>'
        + '<div style="' + M + '; font-size:14px; text-align:right; color:#4F8EF7">' + c.ks + '¢</div>'
        + '<div style="' + gapStyle + '">' + g + '¢</div>'
        + '<div style="' + M + '; font-size:12.5px; text-align:right; color:rgba(255,255,255,.6)">' + money(c.pmVol + c.ksVol) + '</div>'
        + '<div style="' + M + '; font-size:12px; text-align:right; color:rgba(255,255,255,.45)">' + esc(c.held) + '</div></div>';
    }).join('')
    + (cRows.length === 0 ? '<div style="padding:60px; text-align:center; ' + M + '; font-size:12px; color:rgba(255,255,255,.35)">No pair passes the local filters; loosen a stepper above.</div>' : '')
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
    return '<div>' + seitenKopf('RESOLVED', 'How the last questions ended', '#C8F542')
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
    + '<div style="padding:20px 24px 14px; border-bottom:1px solid rgba(255,255,255,.09)">'
    + '<div style="display:flex; align-items:flex-end; justify-content:space-between; gap:20px">'
    + '<div><div style="' + M + '; font-size:10px; letter-spacing:.18em; color:#C8F542">RESOLVED</div>'
    + '<div style="font-family:\'Instrument Serif\',serif; font-size:30px; line-height:1.1; margin-top:5px">How the last questions ended</div></div>'
    + '<input value="' + esc(s.resQuery) + '" ' + T.inp((e) => T.setState({ resQuery: e.target.value }), 'resQuery') + ' placeholder="Search resolved markets…" style="background:#10151A; border:1px solid rgba(255,255,255,.16); border-radius:8px; padding:9px 12px; ' + M + '; font-size:12.5px; color:#fff; width:250px; outline:none" />'
    + '</div>'
    + '<div style="font-size:13px; color:rgba(255,255,255,.55); margin-top:10px; max-width:700px">The last price before settlement next to the answer. The gap between the two is what the crowd got wrong.</div>'
    + '<div style="display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:14px 18px; margin-top:14px">'
    + filterGroup('ANSWER', [['all','All'],['yes','Ended Yes'],['no','Ended No']].map((o) => T.opt(o[1], s.resAnswer === o[0], { resAnswer: o[0] })).join(''))
    + filterGroup('SETTLED WITHIN', [['all','All'],['24','24 hours'],['168','7 days']].map((o) => T.opt(o[1], s.resWindow === o[0], { resWindow: o[0] })).join(''))
    + filterGroup('CROWD WAS OFF BY', [['all','Any'],['25','25¢ or more'],['50','50¢ or more']].map((o) => T.opt(o[1], s.resError === o[0], { resError: o[0] })).join(''))
    + filterGroup('SORT BY', [['recent','Most recent'],['error','Biggest surprise'],['volume','Volume']].map((o) => T.opt(o[1], s.resSort === o[0], { resSort: o[0] })).join(''))
    + '</div></div>'

    + '<div style="display:grid; grid-template-columns:repeat(4,1fr); border-bottom:1px solid rgba(255,255,255,.09)">'
    + kpis.map((k, i) =>
      '<div style="padding:14px 24px' + (i < 3 ? '; border-right:1px solid rgba(255,255,255,.09)' : '') + '">'
      + '<div style="' + HEAD_CELL + '">' + k.label + '</div>'
      + '<div style="' + M + '; font-size:22px; margin-top:7px; color:' + (k.amber ? '#F5A623' : '#ffffff') + '">' + k.value + '</div></div>'
    ).join('')
    + '</div>'

    + '<div style="display:grid; grid-template-columns:1fr 110px 118px 128px 110px 120px; padding:10px 24px; border-bottom:1px solid rgba(255,255,255,.09); background:#10151A; ' + HEAD_CELL + '">'
    + '<div>MARKET</div><div style="text-align:right">ANSWER</div><div style="text-align:right">LAST PRICE</div><div style="text-align:right">CROWD OFF BY</div><div style="text-align:right">VOLUME</div><div style="text-align:right">SETTLED</div></div>'
    + resRows.map((r) => {
      const answerStyle = M + '; font-size:11px; letter-spacing:.1em; border-radius:5px; padding:3px 10px; ' + (r.yes ? 'color:#0A0D0F; background:#C8F542' : 'color:#FF7A7A; border:1px solid rgba(255,69,69,.35)');
      const errStyle = M + '; font-size:14px; text-align:right; color:' + (r.err >= 50 ? '#FF4545' : r.err >= 25 ? '#F5A623' : 'rgba(255,255,255,.6)');
      return '<div style="display:grid; grid-template-columns:1fr 110px 118px 128px 110px 120px; align-items:center; padding:13px 24px; border-bottom:1px solid rgba(255,255,255,.06); animation:rowIn .25s ease-out">'
        + '<div style="padding-right:20px"><div style="font-size:13.5px; line-height:1.35">' + esc(r.title) + '</div>'
        + '<div style="' + M + '; font-size:10.5px; color:rgba(255,255,255,.45); margin-top:3px">' + esc(r.meta) + '</div></div>'
        + '<div style="display:flex; justify-content:flex-end"><div style="' + answerStyle + '">' + (r.yes ? 'YES' : 'NO') + '</div></div>'
        + '<div style="' + M + '; font-size:14px; text-align:right">' + r.last + '¢</div>'
        + '<div style="' + errStyle + '">' + r.err + '¢</div>'
        + '<div style="' + M + '; font-size:12.5px; text-align:right; color:rgba(255,255,255,.6)">' + esc(r.vol) + '</div>'
        + '<div style="' + M + '; font-size:12px; text-align:right; color:rgba(255,255,255,.45)">' + esc(r.when) + '</div></div>';
    }).join('')
    + '</div>';
}
