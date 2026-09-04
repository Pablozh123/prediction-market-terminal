// Ruft die reinen Abbildungsfunktionen aus web/js/util.js mit rohen
// API-Zeilen auf und schreibt das Ergebnis als JSON nach stdout. Der Test in
// tests/test_web_util.py liest das und prueft die Einheiten: was unter
// welcher Ueberschrift landet, entscheidet sich hier.

import { mapMarket, mapTrade, money, liveStatusLabel, livePollFaellig, LIVE_ROUTEN, LIVE_TAKT_RUHIG_MS } from '../web/js/util.js';

// Der Takt des Live-Polls je Route. Auf einer Route, die die Zeilen nicht
// zeigt, soll er nur alle fuenf Minuten laufen; die Kopfzeile und der Zaehler
// am Eintrag Live tape brauchen ihn dort, der Rumpf nicht.
const T0 = 1_000_000;
const pollTakt = {
  routen: LIVE_ROUTEN,
  ruhig_ms: LIVE_TAKT_RUHIG_MS,
  // Auf einer lauten Route immer, egal wie kurz der letzte Lauf her ist.
  laute_route_sofort: livePollFaellig('markets', false, T0, T0 + 1000),
  ruhige_route_gleich_danach: livePollFaellig('research', false, T0, T0 + 1000),
  ruhige_route_nach_zwei_minuten: livePollFaellig('research', false, T0, T0 + 120000),
  ruhige_route_nach_fuenf_minuten: livePollFaellig('research', false, T0, T0 + 300000),
  // Der erste Lauf ueberhaupt wartet nicht.
  ruhige_route_ohne_vorlauf: livePollFaellig('settings', false, 0, T0),
  // Ein offenes Overlay liest die Zeilen und kann ueber jeder Route stehen.
  ruhige_route_mit_overlay: livePollFaellig('research', true, T0, T0 + 1000),
  // Eine unbekannte Route zaehlt als ruhig, nicht als laut.
  unbekannte_route: livePollFaellig('gibtsnicht', false, T0, T0 + 1000)
};

const ausgabe = {
  poll_takt: pollTakt,
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

process.stdout.write(JSON.stringify(ausgabe));
