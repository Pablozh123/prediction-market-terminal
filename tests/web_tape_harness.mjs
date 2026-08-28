// Prueft die reinen Tape-Helfer aus web/js/util.js ohne Browser und gibt das
// Ergebnis als JSON nach stdout. Gelesen von tests/test_web_tape.py.
//
// Die Faelle bilden echte Antwortzeilen nach: /api/tape liefert fuer
// Polymarket side = BUY/SELL und outcome = "Yes"/"No", fuer Kalshi in
// derselben side-Spalte die genommene Seite ("yes"/"no", klein geschrieben,
// src/prediction_markets.get_kalshi_trades).

import { mapTrade, tapeMatches, tradeDirection, tradeOutcome } from '../web/js/util.js';

const jetzt = new Date().toISOString();

const roh = [
  // Polymarket: Kauf Yes, 1000 Anteile zu 25 Cent = $250 Notional.
  { platform: 'Polymarket', time: jetzt, wallet: '0x' + 'a'.repeat(40), trader: 'alpha',
    side: 'BUY', outcome: 'Yes', title: 'Fed cuts in December', market_key: '0xcond1',
    price: 0.25, size: 1000, notional: 250, category: 'Macro' },
  // Polymarket: Verkauf No.
  { platform: 'Polymarket', time: jetzt, wallet: '0x' + 'b'.repeat(40), trader: 'beta',
    side: 'SELL', outcome: 'No', title: 'Fed cuts in December', market_key: '0xcond1',
    price: 0.75, size: 400, notional: 300, category: 'Macro' },
  // Kalshi: taker_side/taker_outcome_side kommen klein an.
  { platform: 'Kalshi', time: jetzt, wallet: 'Not public', trader: 'Not public',
    side: 'no', outcome: 'no', title: 'Will BTC close above 100k?', ticker: 'KXBTC-26AUG28',
    market_key: 'KXBTC-26AUG28', price: 0.6, size: 500, notional: 300, category: 'Crypto' },
  { platform: 'Kalshi', time: jetzt, wallet: 'Not public', trader: 'Not public',
    side: 'yes', outcome: 'yes', title: 'Will BTC close above 100k?', ticker: 'KXBTC-26AUG28',
    market_key: 'KXBTC-26AUG28', price: 0.4, size: 500, notional: 200, category: 'Crypto' },
  // Mehrfachmarkt: der Ergebnisname enthaelt "No" als Teilzeichenkette.
  { platform: 'Polymarket', time: jetzt, wallet: '0x' + 'c'.repeat(40), trader: 'gamma',
    side: 'BUY', outcome: 'November', title: 'Month of the next cut', market_key: '0xcond2',
    price: 0.1, size: 5000, notional: 500, category: 'Macro' }
];

const zeilen = roh.map(mapTrade);

const basis = {
  tapeMin: 0, tapeTracked: false, tapePlatform: 'all', tapeSide: 'all',
  tapeOutcome: 'all', tapeCat: 'All', tapeQuery: ''
};
const mit = (patch) => zeilen.filter((t) => tapeMatches(t, { ...basis, ...patch }));
const summe = (rows) => rows.reduce((a, t) => a + t.size, 0);

const ausgabe = {
  richtung: zeilen.map((t) => t.dir),
  ergebnis: zeilen.map((t) => t.outcome),
  etikett: zeilen.map((t) => t.side),
  groesse: zeilen.map((t) => t.size),
  outcome_yes: mit({ tapeOutcome: 'Yes' }).map((t) => t.market + '|' + t.venue + '|' + t.outcome),
  outcome_no: mit({ tapeOutcome: 'No' }).map((t) => t.market + '|' + t.venue + '|' + t.outcome),
  side_buy_summe: summe(mit({ tapeSide: 'BUY' })),
  side_sell_summe: summe(mit({ tapeSide: 'SELL' })),
  gesamt_summe: summe(zeilen),
  kalshi_only: mit({ tapePlatform: 'Kalshi' }).length,
  // Richtung/Ergebnis einzeln, damit die Normalisierung selbst belegt ist.
  helfer: {
    dir_sell: tradeDirection('SELL'), dir_kalshi_no: tradeDirection('no'),
    dir_leer: tradeDirection(''), out_klein: tradeOutcome('no'),
    out_gross: tradeOutcome('No'), out_leer: tradeOutcome(''),
    out_name: tradeOutcome('November')
  }
};

process.stdout.write(JSON.stringify(ausgabe));
