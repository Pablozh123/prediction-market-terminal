// Ruft die reinen Abbildungsfunktionen aus web/js/util.js mit rohen
// API-Zeilen auf und schreibt das Ergebnis als JSON nach stdout. Der Test in
// tests/test_web_util.py liest das und prueft die Einheiten: was unter
// welcher Ueberschrift landet, entscheidet sich hier.

import { mapMarket, mapTrade, money, liveStatusLabel } from '../web/js/util.js';
import { STUDIEN, studienSlug, studienIndexAus } from '../web/js/studies.js';

const ausgabe = {
  // Ein Markt, der heute nicht gehandelt wurde, aber ueber sein Leben 4.2m
  // Umsatz gesehen hat. activity_volume traegt in diesem Fall das
  // Lebensvolumen, nicht den Tageswert.
  ruhender_markt: mapMarket({
    market_key: '0xruht', title: 'Dormant question', platform: 'Polymarket',
    category: 'Politics', yes_price: 0.62, change_1d: 0.01, spread: 0.02,
    volume_24h: 0, activity_volume: 4200000, volume: 4200000,
    liquidity: 15000, end_time: '2026-12-31T00:00:00Z',
  }, 0),
  aktiver_markt: mapMarket({
    market_key: '0xaktiv', title: 'Busy question', platform: 'Kalshi',
    category: 'Economics', yes_price: 0.41, change_1d: -0.03, spread: 0.01,
    volume_24h: 125000, activity_volume: 125000, volume: 900000,
    liquidity: 0, end_time: '2026-09-30T00:00:00Z',
  }, 1),
  // Ein Print der Gegenseite: der Taker kauft NO zu 1 - yes.
  no_print: mapTrade({
    time: new Date().toISOString(), title: 'Busy question', market_key: 'k1',
    price: 0.15, size: 200, notional: 30, platform: 'Kalshi', outcome: 'No',
    side: 'BUY',
  }),
  geld: { null: money(0), tausend: money(1500), million: money(4200000) },
  // Die Statuszeile der Kopfleiste. Sie stand fest verdrahtet auf beiden
  // Venues, auch wenn nur eine geantwortet hatte.
  statuszeile: {
    beide: liveStatusLabel('live', []),
    kalshi_fehlt: liveStatusLabel('live', ['Kalshi']),
    polymarket_fehlt: liveStatusLabel('live', ['Polymarket']),
    keine: liveStatusLabel('live', ['Polymarket', 'Kalshi']),
    fehler: liveStatusLabel('error', ['Kalshi']),
    wartet: liveStatusLabel('waiting', []),
  },
};

// Aufloesung eines Adresssegments auf eine Studie. Der Eintrag in der
// Seitenleiste heisst "Post-mortems", die Studie "Postmortems": genau die
// Adresse, die jemand tippt, der die Beschriftung abschreibt, zeigte auf
// keine Studie, und die Seite blieb still auf dem vorigen Reiter.
const studienAdressen = {
  kanonisch: STUDIEN.map(studienSlug),
  postmortems: studienIndexAus(STUDIEN, 'postmortems'),
  mit_bindestrich: studienIndexAus(STUDIEN, 'post-mortems'),
  mit_unterstrich_und_gross: studienIndexAus(STUDIEN, 'Post_Mortems'),
  feldnotizen_ohne_strich: studienIndexAus(STUDIEN, 'fieldnotes'),
  feldnotizen_mit_strich: studienIndexAus(STUDIEN, 'field-notes'),
  unbekannt: studienIndexAus(STUDIEN, 'gibtsnicht'),
  leer: studienIndexAus(STUDIEN, ''),
  nichts: studienIndexAus(STUDIEN, null)
};

ausgabe.studien_adressen = studienAdressen;

process.stdout.write(JSON.stringify(ausgabe));
