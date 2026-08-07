// Thin fetch layer. Served by the FastAPI bridge the base is same-origin;
// opened as a plain file it falls back to the default local API port.

const API_BASE = (location.protocol === 'file:') ? 'http://localhost:8787' : '';

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
  '/api/research/meta': 'meta.json',
};

// Kein Endpunkt darf die Seite unbegrenzt haengen lassen. /api/risk baut beim
// ersten Aufruf einen Tagesausschnitt des Tapes auf und schlaegt dafuer
// Marktkategorien nach; ohne Deckel wartet die Oberflaeche minutenlang, ohne
// zu sagen worauf.
const TIMEOUT_MS = 45000;

async function hole(url, optionen) {
  const abbruch = new AbortController();
  const uhr = setTimeout(() => abbruch.abort(), TIMEOUT_MS);
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

export async function apiPost(path, body) {
  const res = await hole(API_BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  if (!res.ok) throw new Error('HTTP ' + res.status);
  return res.json();
}
