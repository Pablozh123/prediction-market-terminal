// Drives web/js/api.js without a browser and with a stand-in for fetch, and
// writes what apiGet returns (or throws) as JSON to stdout. The test in
// tests/test_web_api_fallback.py reads it.
//
// The case that motivated this: marketintel.dev is a Cloudflare Pages site,
// and Pages answers a missing ./data/<file>.json with the application's own
// index.html — status 200, text/html. The static fallback used to parse that
// blindly and the page showed "JSON.parse: unexpected character at line 1
// column 1" for a file that simply did not exist yet.

import { apiGet, statischeNutzlast, STATISCH } from '../web/js/api.js';

const INDEX_HTML = '<!DOCTYPE html>\n<html lang="en">\n<head><meta charset="utf-8"><title>Market Intel</title></head><body></body></html>';

function antwort(status, typ, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: (k) => (String(k).toLowerCase() === 'content-type' ? typ : null) },
    text: async () => body,
    json: async () => JSON.parse(body)
  };
}

// tabelle: [[urlSubstring, antwort | () => antwort]], first match wins; an
// unmatched URL is a JSON 404 like the FastAPI bridge answers.
function netz(tabelle) {
  globalThis.fetch = async (url) => {
    for (const [muster, res] of tabelle) {
      if (String(url).indexOf(muster) >= 0) return typeof res === 'function' ? res() : res;
    }
    return antwort(404, 'application/json', '{"detail":"unknown study"}');
  };
}

const netzTot = () => { throw new TypeError('Failed to fetch'); };

async function versuch(fn) {
  try {
    return { wert: await fn() };
  } catch (err) {
    return { fehler: String(err && err.message ? err.message : err), status: err && err.status != null ? err.status : null };
  }
}

const faelle = {};

// 1. Pages fallback: API says 404, the static path answers with index.html.
netz([['./data/arb_scan.json', antwort(200, 'text/html; charset=utf-8', INDEX_HTML)]]);
faelle.pages_liefert_startseite = await versuch(() => apiGet('/api/research/arb-scan'));

// 2. A plain 404 for the static file.
netz([['./data/arb_scan.json', antwort(404, 'text/html', '<h1>Not found</h1>')]]);
faelle.datei_404 = await versuch(() => apiGet('/api/research/arb-scan'));

// 3. The static file exists and is JSON.
netz([['./data/arb_scan.json', antwort(200, 'application/json', '{"schema":"arb_scan/1","summary":{"validated_24h":9}}')]]);
faelle.datei_json = await versuch(() => apiGet('/api/research/arb-scan'));

// 4. JSON body without a Content-Type (a bare file server): still the file.
netz([['./data/field_notes.json', antwort(200, '', '{"kennzeichnung":"curated/field-notes","notes":[]}')]]);
faelle.datei_json_ohne_typ = await versuch(() => apiGet('/api/research/field-notes'));

// 5. The API answers itself.
netz([['/api/research/arb-scan', antwort(200, 'application/json', '{"schema":"arb_scan/1","summary":{"validated_24h":3}}')]]);
faelle.api_antwortet = await versuch(() => apiGet('/api/research/arb-scan'));

// 6. No network at all for the API, Pages fallback for the file: an error,
//    because nothing answered — not an empty state.
netz([['./data/arb_scan.json', antwort(200, 'text/html', INDEX_HTML)], ['/api/research/arb-scan', netzTot]]);
faelle.netz_tot_ohne_datei = await versuch(() => apiGet('/api/research/arb-scan'));

// 7. No network for the API, but the file is there: the file.
netz([['./data/arb_scan.json', antwort(200, 'application/json', '{"schema":"arb_scan/1"}')], ['/api/research/arb-scan', netzTot]]);
faelle.netz_tot_mit_datei = await versuch(() => apiGet('/api/research/arb-scan'));

// 8. The API fails with 500 and the file is missing: that error, not "empty".
netz([['./data/arb_scan.json', antwort(200, 'text/html', INDEX_HTML)], ['/api/research/arb-scan', antwort(500, 'application/json', '{"detail":"boom"}')]]);
faelle.api_500_ohne_datei = await versuch(() => apiGet('/api/research/arb-scan'));

// 9. A path without a published file behind it: a 404 stays an error.
netz([]);
faelle.ohne_statische_datei = await versuch(() => apiGet('/api/markets'));

// 10. The API says 404 and the static fetch itself throws (offline file host).
netz([['./data/arb_scan.json', netzTot]]);
faelle.api_404_datei_netz_tot = await versuch(() => apiGet('/api/research/arb-scan'));

// The pure reader, case by case.
const rein = {
  html_200: statischeNutzlast(true, 'text/html; charset=utf-8', INDEX_HTML),
  json_404: statischeNutzlast(false, 'application/json', '{"a":1}'),
  json_ok: statischeNutzlast(true, 'application/json; charset=utf-8', '{"a":1}'),
  json_mit_bom: statischeNutzlast(true, 'application/json', '﻿  {"a":2}'),
  liste_ohne_typ: statischeNutzlast(true, '', '[1,2]'),
  html_ohne_typ: statischeNutzlast(true, '', '<!DOCTYPE html>'),
  kaputt: statischeNutzlast(true, 'application/json', '{"a":'),
  leer: statischeNutzlast(true, 'application/json', ''),
  zahl: statischeNutzlast(true, 'application/json', '42')
};

process.stdout.write(JSON.stringify({ faelle, rein, statisch: STATISCH }));
