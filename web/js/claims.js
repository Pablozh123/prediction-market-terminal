// Der einzige Weg, auf dem ein Vorbehalt in die Oberflaeche kommt.
//
// Bis hierher war jeder Disclaimer im Frontend handgeschriebene Prosa, und
// data/claims.yaml hatte keinen einzigen Leser in web/: das Register, auf
// dem die Projektregel aufbaut, hat also nichts gespeist und nichts gedeckt.
// Jetzt fragt eine Seite ihren Vorbehalt unter seinem Schluessel ab:
//
//     import { caveat, caveatZeile } from '../claims.js';
//     ... + caveatZeile('screen_not_proof', { vorsatz: 'Sports odds ...' })
//
// Der Text kommt aus claims_register.js (kompiliert aus data/claims.yaml,
// siehe scripts/publish_claims.py) und steht damit vor dem ersten Netzwerk-
// zugriff bereit; ein Vorbehalt, der auf eine Antwort wartet, fehlt genau so
// lange. Antwortet /api/claims mit einer neueren Fassung, uebernimmt
// registerAktualisieren sie fuer den Rest der Sitzung.
//
// Jeder gerenderte Vorbehalt traegt data-caveat="<schluessel>": daran haengt
// die Pruefung in scripts/lint_claims.py, dass ein Registereintrag mit
// benannter Flaeche dort auch wirklich steht.

import { REGISTER } from './claims_register.js';
import { esc } from './util.js';

// Die Oberflaeche ist durchgehend englisch; das Register fuehrt beide
// Sprachen, damit derselbe Satz in einem deutschen Bericht zitierbar bleibt.
const STANDARD_SPRACHE = 'en';

let register = REGISTER && REGISTER.disclaimers ? REGISTER : { version: 0, updated: '', disclaimers: {} };
let quelle = 'eingebaut';

/** Version, Stand und Herkunft des benutzten Registers. */
export function registerStand() {
  return {
    version: register.version || 0,
    updated: register.updated || '',
    quelle,
    eintraege: Object.keys(register.disclaimers || {}).length
  };
}

// Eine Antwort von /api/claims uebernimmt nur, was auch eine ist: ein Objekt
// mit Disclaimern. Alles andere laesst den eingebauten Stand stehen, denn ein
// halb geladenes Register ist schlechter als das kompilierte.
export function registerAktualisieren(payload) {
  if (!payload || typeof payload !== 'object') return false;
  const eintraege = payload.disclaimers;
  if (!eintraege || typeof eintraege !== 'object' || !Object.keys(eintraege).length) return false;
  const gefiltert = {};
  Object.keys(eintraege).forEach((key) => {
    const row = eintraege[key];
    if (!row || typeof row !== 'object') return;
    const texte = {};
    ['de', 'en'].forEach((code) => { if (typeof row[code] === 'string' && row[code]) texte[code] = row[code]; });
    if (Object.keys(texte).length) gefiltert[key] = texte;
  });
  if (!Object.keys(gefiltert).length) return false;
  register = {
    version: payload.version || register.version || 0,
    updated: payload.updated || register.updated || '',
    disclaimers: gefiltert
  };
  quelle = 'api';
  return true;
}

/** Der reine Text eines Registereintrags, ohne Markup. Unbekannt = ''. */
export function caveatText(key, sprache) {
  const eintrag = (register.disclaimers || {})[key];
  if (!eintrag) return '';
  const gewuenscht = sprache || STANDARD_SPRACHE;
  return String(eintrag[gewuenscht] || eintrag[STANDARD_SPRACHE] || eintrag.de || eintrag.en || '');
}

/** Der Vorbehalt als Inline-Element, fuer einen Satz, der weiterlaeuft. */
export function caveat(key, opts) {
  const text = caveatText(key, opts && opts.sprache);
  if (!text) return '';
  const stil = opts && opts.stil ? ' style="' + opts.stil + '"' : '';
  return '<span data-caveat="' + esc(key) + '"' + stil + '>' + esc(text) + '</span>';
}

// Eine eigene Zeile unter einer Ueberschrift. vorsatz/nachsatz sind der
// beschreibende Teil, den die Seite selbst besitzt ("was diese Seite tut");
// der Vorbehalt daneben gehoert dem Register. Beides steht im selben Absatz,
// damit aus der Trennung im Code keine zweite Zeile auf dem Bildschirm wird.
export function caveatZeile(key, opts) {
  const o = opts || {};
  const text = caveatText(key, o.sprache);
  const vorsatz = o.vorsatz ? String(o.vorsatz) : '';
  const nachsatz = o.nachsatz ? String(o.nachsatz) : '';
  if (!text && !vorsatz && !nachsatz) return '';
  const stil = o.stil || 'font-size:var(--t-body); color:var(--ink-4); margin-top:var(--sp-3); max-width:760px; line-height:var(--lh-snug)';
  // vorsatz und nachsatz kommen aus dem Modul selbst und duerfen Markup
  // enthalten (Links, <span> in Mono); der Registertext wird immer maskiert.
  return '<div' + (text ? ' data-caveat="' + esc(key) + '"' : '') + ' style="' + stil + '">'
    + (vorsatz ? vorsatz + ' ' : '')
    + esc(text)
    + (nachsatz ? ' ' + nachsatz : '')
    + '</div>';
}
