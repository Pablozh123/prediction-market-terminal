// Der Vorschau-Schalter fuer Seiten, die gebaut, aber noch nicht
// freigeschaltet sind (studies.js: preview: true).
//
// Ein: ?preview=1 in der Adresse, einmal geoeffnet, merkt sich der Browser
// in localStorage. Aus: ?preview=0. Ohne Schalter listet die Seitenleiste
// die Vorschau-Studien nicht, die Suche findet sie nicht, und ihre Adresse
// zeigt eine Sperrkarte statt der Seite. Die Nutzlasten liegen trotzdem
// unter ./data, weil der Build sie mitnimmt; freigeschaltet wird, indem
// das preview-Feld in studies.js faellt.
//
// Beide Quellen (Adresse, Speicher) werden hereingereicht, damit der Node-
// Harness ohne window pruefen kann, was ein Browser tun wuerde.

const SCHLUESSEL = 'mi-preview';

export function previewAn(suche, speicher) {
  let q = null;
  try {
    q = new URLSearchParams(String(suche == null ? (typeof location !== 'undefined' ? location.search : '') : suche));
  } catch (e) { q = null; }
  const wert = q ? q.get('preview') : null;
  const store = speicher !== undefined ? speicher : (typeof localStorage !== 'undefined' ? localStorage : null);
  try {
    if (wert === '1') { if (store) store.setItem(SCHLUESSEL, '1'); return true; }
    if (wert === '0') { if (store) store.removeItem(SCHLUESSEL); return false; }
    return !!store && store.getItem(SCHLUESSEL) === '1';
  } catch (e) {
    return wert === '1';
  }
}

/** Ob eine Studie hinter dem Schalter steht. */
export function gesperrt(study, an) {
  return !!(study && study.preview) && !an;
}

export function sperrkarteHtml(study) {
  const titel = study && study.title ? String(study.title) : 'This page';
  return '<div style="padding:var(--sp-6)">'
    + '<div style="background:var(--panel); border:1px solid var(--line-2); border-radius:var(--r-panel); padding:var(--sp-6); max-width:720px">'
    + '<div style="font-family:var(--font-mono); font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:var(--warn)">IN PREPARATION</div>'
    + '<h1 style="font-size:var(--t-lead); font-weight:600; margin:var(--sp-3) 0 0">' + titel.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])) + '</h1>'
    + '<div style="font-size:var(--t-body); color:var(--ink-3); margin-top:var(--sp-4); line-height:var(--lh-prose)">This study is built and reviewed but not released yet. It appears in the sidebar with the next release; nothing is shown before that.</div>'
    + '</div></div>';
}
