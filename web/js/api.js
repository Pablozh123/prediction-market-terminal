// Thin fetch layer. Served by the FastAPI bridge the base is same-origin;
// opened as a plain file it falls back to the default local API port. A
// static deployment that keeps its API on another host (Pages + Railway,
// say) sets <meta name="api-base" content="https://api.example.org"> —
// scripts/build_static_site.py writes that from --api-base / API_BASE_URL.
//
// The module is importable without a browser (tests/web_api_harness.mjs):
// every use of document and location is guarded, and fetch is read from the
// global at call time so a harness can stand in for the network.

function apiBaseAusMeta() {
  if (typeof document === 'undefined') return '';
  const meta = document.querySelector('meta[name="api-base"]');
  const wert = meta && meta.content ? meta.content.trim() : '';
  return wert.replace(/\/+$/, '');
}

// Ohne gefuellte api-base kennt die statische Auslieferung ihre API
// trotzdem: die produktiven Hostnamen des Projekts sind Fakten (README —
// marketintel.dev auf Cloudflare Pages, api.marketintel.dev auf Railway),
// keine Konfiguration. Vorher hing das am Build-Schritt, und eine Pages-
// Auslieferung ohne ihn zeigte "API NOT REACHABLE", obwohl die API lief.
// Lokale Entwicklung (localhost, file://) bleibt unberuehrt.
function produktionsApi() {
  if (typeof location === 'undefined') return '';
  const h = location.hostname;
  return (h === 'marketintel.dev' || h === 'www.marketintel.dev' || h.endsWith('.prediction-market-terminal.pages.dev'))
    ? 'https://api.marketintel.dev' : '';
}

const API_BASE = apiBaseAusMeta() || produktionsApi()
  || ((typeof location !== 'undefined' && location.protocol === 'file:') ? 'http://localhost:8787' : '');

// Wo die publizierten Nutzlasten liegen, wenn kein Python laeuft. Die
// Forschungsseiten sind damit auch aus einem reinen Dateiserver lesbar, was
// fuer eine statisch ausgelieferte Fassung der einzige Weg ist.
export const STATISCH = {
  '/api/research/review-queue': 'queue.json',
  '/api/research/category-efficiency': 'kategorie_karte.json',
  '/api/research/mentions-latency': 'mentions_latenz.json',
  '/api/research/live-runs': 'runs.json',
  '/api/research/microstructure': 'microstructure.json',
  '/api/research/pilot': 'pilot.json',
  '/api/research/pipeline-forward': 'pipeline_forward.json',
  '/api/research/methodology': 'audit.json',
  '/api/research/postmortems': 'postmortems.json',
  '/api/research/field-notes': 'field_notes.json',
  '/api/research/wallet-ledger': 'wallet_ledger.json',
  '/api/research/meta': 'meta.json',
  '/api/research/arb-scan': 'arb_scan.json',
  // Die Vorschau-Studien (studies.js, preview: true).
  '/api/research/thesis': 'thesis_results.json',
  '/api/research/reddit-sentiment': 'reddit_sentiment.json',
  '/api/research/pre-registrations': 'preregistrations.json',
  '/api/research/literature': 'literature.json',
  // Our own resolution pass over the scanner's journal (schema
  // arb_resolutions/1, scripts/resolve_arb_paper.py): joined onto the
  // paper book by trade_id.
  '/api/research/arb-resolutions': 'arb_resolutions.json',
};

// Kein Endpunkt darf die Seite unbegrenzt haengen lassen. /api/risk baut beim
// ersten Aufruf einen Tagesausschnitt des Tapes auf und schlaegt dafuer
// Marktkategorien nach; ohne Deckel wartet die Oberflaeche minutenlang, ohne
// zu sagen worauf.
const TIMEOUT_MS = 45000;

// /api/risk pages a day of prints and looks up market categories on a cold
// cache — around 90 s. With the general 45 s cap the first click always
// failed and the second one hit the warm cache; the screen looked flaky when
// it was only slow. Only these routes get the longer leash. /api/backtest
// gehoert dazu, seit der Fetch das ganze Fenster in Zeitscheiben abdeckt:
// bei hyperaktiven Wallets sind das Dutzende Upstream-Seiten. /api/cross
// auch, seit das Kalshi-Universum echt ist: der kalte Aufruf blaettert 12
// Event-Seiten, vergleicht 500 gegen ~17k Titel und schlaegt zwei Dutzend
// Buecher nach — gemessen ~60-90 s.
const TIMEOUT_LANG_MS = 150000;
const LANGSAME_PFADE = ['/api/risk', '/api/backtest', '/api/cross'];

export function timeoutFuer(url) {
  const pfad = String(url || '').split('?')[0];
  return LANGSAME_PFADE.some((p) => pfad.endsWith(p)) ? TIMEOUT_LANG_MS : TIMEOUT_MS;
}

async function hole(url, optionen) {
  const abbruch = new AbortController();
  const frist = timeoutFuer(url);
  const uhr = setTimeout(() => abbruch.abort(), frist);
  try {
    return await fetch(url, Object.assign({ signal: abbruch.signal }, optionen || {}));
  } catch (err) {
    // The browser's own text for a timed-out request is "signal is aborted
    // without reason"; the empty state should say how long it waited.
    if (err && err.name === 'AbortError') throw new Error('no answer within ' + Math.round(frist / 1000) + ' s');
    throw err;
  } finally {
    clearTimeout(uhr);
  }
}

// Ist eine Antwort auf ./data/<datei>.json die Datei, oder etwas anderes?
//
// Cloudflare Pages beantwortet einen fehlenden Pfad mit der Startseite der
// Anwendung: Status 200, text/html, Body "<!DOCTYPE html>". Vor dieser
// Pruefung lief das blind in JSON.parse, und die Seite meldete "JSON.parse:
// unexpected character at line 1 column 1" — eine Parse-Fehlermeldung fuer
// eine Datei, die es schlicht noch nicht gab (arb_scan.json, 2026-09-04).
// Drei Merkmale, jedes fuer sich reicht: kein ok-Status, ein Content-Type
// ohne "json", oder ein Body, der nicht mit { oder [ beginnt. Null heisst
// "Datei fehlt"; der Aufrufer zeigt dann den Leerzustand, der die Datei
// beim Namen nennt.
export function statischeNutzlast(ok, contentType, text) {
  if (!ok) return null;
  const typ = String(contentType || '').toLowerCase();
  if (typ && typ.indexOf('json') < 0) return null;
  // BOM und fuehrender Leerraum sind keine Aussage ueber den Inhalt.
  const koerper = String(text == null ? '' : text).replace(/^\uFEFF/, '').trimStart();
  if (!koerper || (koerper[0] !== '{' && koerper[0] !== '[')) return null;
  try {
    const daten = JSON.parse(koerper);
    return daten && typeof daten === 'object' ? daten : null;
  } catch (e) {
    return null;
  }
}

/** Publizierte Datei statt API, wenn kein Backend antwortet. Null, wenn es
 *  die Datei nicht gibt oder die Antwort keine JSON-Datei ist. */
async function statischerRueckfall(path) {
  const datei = STATISCH[path.split('?')[0]];
  if (!datei) return null;
  let res;
  try {
    res = await hole('./data/' + datei);
  } catch (e) {
    return null;
  }
  const daten = statischeNutzlast(res.ok, res.headers && res.headers.get ? res.headers.get('Content-Type') : '', await res.text());
  if (!daten) return null;
  daten._quelle = 'statisch';
  return daten;
}

// HTTP errors carry the status and, on 429, the server's retry_after_s so
// the caller can say "rate-limited, retry in N s" instead of "HTTP 429".
async function httpFehler(res) {
  const err = new Error('HTTP ' + res.status);
  err.status = res.status;
  if (res.status === 429) {
    let sekunden = Number(res.headers.get('Retry-After')) || 0;
    try {
      const daten = await res.json();
      if (daten && daten.retry_after_s != null) sekunden = Number(daten.retry_after_s) || sekunden;
    } catch (e) { /* kein JSON-Koerper */ }
    err.retryAfter = sekunden || 10;
  }
  return err;
}

export async function apiGet(path) {
  try {
    const res = await hole(API_BASE + path);
    if (!res.ok) throw await httpFehler(res);
    return await res.json();
  } catch (err) {
    const ersatz = await statischerRueckfall(path);
    if (ersatz) return ersatz;
    // Eine publizierte Datei, die die API mit 404 quittiert und die auch
    // statisch nicht da ist, fehlt — das ist ein Leerzustand ("no published
    // data for this study yet"), kein Fehler der Verbindung. Die Aufrufer
    // lesen null als leer; jeder andere Fehler bleibt einer.
    if (err && err.status === 404 && STATISCH[String(path).split('?')[0]]) return null;
    throw err;
  }
}

// Extra headers ride along (the copy desk sends X-Admin-Token). A non-2xx
// answer with a JSON {detail} carries that text on the error, so the page can
// say "max_order_equity_pct is a fraction" instead of "HTTP 400".
export async function apiPost(path, body, headers) {
  const res = await hole(API_BASE + path, {
    method: 'POST',
    headers: Object.assign({ 'Content-Type': 'application/json' }, headers || {}),
    body: JSON.stringify(body == null ? {} : body)
  });
  if (!res.ok) {
    const err = await httpFehler(res);
    try {
      const daten = await res.json();
      if (daten && daten.detail) err.detail = typeof daten.detail === 'string' ? daten.detail : JSON.stringify(daten.detail);
    } catch (e) { /* kein JSON-Koerper */ }
    throw err;
  }
  return res.json();
}

// GET with headers, without the static fallback (used for the copy desk,
// which has no published file to fall back to).
export async function apiGetRaw(path, headers) {
  const res = await hole(API_BASE + path, { headers: headers || {} });
  if (!res.ok) throw await httpFehler(res);
  return res.json();
}
