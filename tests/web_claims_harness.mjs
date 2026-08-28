// Ruft web/js/claims.js so auf, wie eine Seite es tut, und schreibt das
// Ergebnis als JSON nach stdout. Der Test in tests/test_web_claims.py liest
// das und prueft, was auf der Oberflaeche ankommt: der Text aus dem
// Register, sein Schluessel als data-caveat, und dass ein unbekannter
// Schluessel nichts rendert statt eines leeren Platzhalters.

import { caveat, caveatText, caveatZeile, registerAktualisieren, registerStand } from '../web/js/claims.js';
import { REGISTER } from '../web/js/claims_register.js';

const ausgabe = {
  // Der komplette kompilierte Stand: der Python-Test vergleicht ihn Zeichen
  // fuer Zeichen mit data/claims.yaml, ueber den echten Import statt ueber
  // einen zweiten Parser.
  kompiliert: REGISTER,
  stand_eingebaut: registerStand(),

  // Die Fusszeile der Seitenleiste. Genau dieser Satz stand bis zu diesem
  // Umbau als Prosa in app.js; er muss unveraendert ankommen.
  fusszeile: caveatZeile('site_footer_readonly', { stil: 'font-size:11px' }),

  // Beschreibender Teil der Seite plus Registertext in einem Absatz.
  zeile_mit_vorsatz: caveatZeile('screen_not_proof', {
    vorsatz: 'Sports odds are excluded.',
    nachsatz: 'Bands are listed below.'
  }),
  inline: caveat('score_generic'),
  text_en: caveatText('backtest_modeled'),
  text_de: caveatText('backtest_modeled', 'de'),

  // Unbekannter Schluessel: nichts. Eine Zeile, die "undefined" oder einen
  // leeren Kasten zeigt, waere schlimmer als der fehlende Satz.
  unbekannt_text: caveatText('gibt_es_nicht'),
  unbekannt_zeile: caveatZeile('gibt_es_nicht'),
  unbekannt_inline: caveat('gibt_es_nicht'),
  // Nur beschreibender Text, ohne Registereintrag: kein data-caveat.
  unbekannt_mit_vorsatz: caveatZeile('gibt_es_nicht', { vorsatz: 'Only prose.' }),
};

// Muell von /api/claims aendert nichts: der eingebaute Stand ist vollstaendig.
ausgabe.muell_angenommen = [
  registerAktualisieren(null),
  registerAktualisieren({}),
  registerAktualisieren({ disclaimers: {} }),
  registerAktualisieren({ disclaimers: { x: 'kein objekt' } })
];
ausgabe.nach_muell = caveatText('score_generic');
ausgabe.stand_nach_muell = registerStand();

// Eine neuere Fassung von /api/claims wird uebernommen.
ausgabe.api_angenommen = registerAktualisieren({
  version: 2,
  updated: '2099-01-01',
  disclaimers: { score_generic: { en: 'Newer text from the API.', de: 'Neuerer Text von der API.' } }
});
ausgabe.nach_api = caveatText('score_generic');
ausgabe.stand_nach_api = registerStand();

process.stdout.write(JSON.stringify(ausgabe));
