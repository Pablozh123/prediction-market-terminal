// Thin fetch layer. Served by the FastAPI bridge the base is same-origin;
// opened as a plain file it falls back to the default local API port. A
// static deployment that keeps its API on another host (Pages + Railway,
// say) sets <meta name="api-base" content="https://api.example.org"> —
// scripts/build_static_site.py writes that from --api-base / API_BASE_URL.

function apiBaseAusMeta() {
  const meta = document.querySelector('meta[name="api-base"]');
  const wert = meta && meta.content ? meta.content.trim() : '';
  return wert.replace(/\/+$/, '');
}

const API_BASE = apiBaseAusMeta() || ((location.protocol === 'file:') ? 'http://localhost:8787' : '');

// Wo die publizierten Nutzlasten liegen, wenn kein Python laeuft. Die
// Forschungsseiten sind damit auch aus einem reinen Dateiserver lesbar, was
// fuer eine statisch ausgelieferte Fassung der einzige Weg ist.
const STATISCH = {
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
};

// Kein Endpunkt darf die Seite unbegrenzt haengen lassen. /api/risk baut beim
// ersten Aufruf einen Tagesausschnitt des Tapes auf und schlaegt dafuer
// Marktkategorien nach; ohne Deckel wartet die Oberflaeche minutenlang, ohne
// zu sagen worauf.
const TIMEOUT_MS = 45000;

// /api/risk pages a day of prints and looks up market categories on a cold
// cache — around 90 s. With the general 45 s cap the first click always
// failed and the second one hit the warm cache; the screen looked flaky when
// it was only slow. Only this route gets the longer leash.
const TIMEOUT_LANG_MS = 150000;
const LANGSAME_PFADE = ['/api/risk'];

export function timeoutFuer(url) {
  const pfad = String(url || '').split('?')[0];
  return LANGSAME_PFADE.some((p) => pfad.endsWith(p)) ? TIMEOUT_LANG_MS : TIMEOUT_MS;
}

async function hole(url, optionen) {
  const abbruch = new AbortController();
  const uhr = setTimeout(() => abbruch.abort(), timeoutFuer(url));
  try {
    return await fetch(url, Object.assign({ signal: abbruch.signal }, optionen || {}));
  } finally {
    clearTimeout(uhr);
  }
}

/** Publizierte Datei statt API, wenn kein Backend antwortet. */
async function statischerRueckfall(path) {
  const datei = STATISCH[path.split('?')[0]];
  if (!datei) return null;
  const res = await hole('./data/' + datei);
  if (!res.ok) return null;
  const daten = await res.json();
  if (daten && typeof daten === 'object') daten._quelle = 'statisch';
  return daten;
}

export async function apiGet(path) {
  try {
    const res = await hole(API_BASE + path);
    if (!res.ok) throw new Error('HTTP ' + res.status);
    return await res.json();
  } catch (err) {
    const ersatz = await statischerRueckfall(path);
    if (ersatz) return ersatz;
    throw err;
  }
}

// HTTP errors carry the status and, on 429, the server's retry_after_s so
// the caller can say "rate-limited, retry in N s" instead of "HTTP 429".
export async function apiPost(path, body) {
  const res = await hole(API_BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  if (!res.ok) {
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
    throw err;
  }
  return res.json();
}
