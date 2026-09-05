// Wie die 0-100-Zahl des Risk-Screens heissen darf.
//
// Vorher stand neben ihr HIGH / MEDIUM / ELEVATED / LOW. Neben einer Zahl
// von 0 bis 100 liest sich "HIGH" als Wahrscheinlichkeit fuer Insiderhandel,
// und das ist die Zahl nicht: sie ist die Punktesumme aus zehn Flow-Merkmalen
// gegen feste Kappen, die Gewichte sind gesetzt und nicht geschaetzt, und
// gegen einen bestaetigten Fall wurde sie nie gemessen. Die Baender zaehlen
// deshalb, wie viele Pruefungen des Screens angesprochen haben.
//
// Quelle der Wahrheit ist app/suspicion.py (SCORE_BANDS, score_band_table);
// /api/risk und /api/risk/log liefern die Tabelle als score_bands mit. Die
// eingebaute Kopie unten ist nur der Rueckfall, damit die Seite auch ohne
// Antwort oder gegen eine aeltere API beschriftet ist statt gar nicht.
//
// Das INTERNE Level (High/Medium/Elevated/Low, in der Nutzlast als "sev")
// bleibt unangetastet: daran haengen Filter, Kartenfarbe und das Flag-Log.
// Hier geht es nur darum, was ein Leser zu sehen bekommt.

import { esc } from './util.js';
import { MONO as M } from './ui.js';


// Alphas gegen die Alpha-Leiter in docs/design/review_2026-08-28.md geprueft:
// mit dem heutigen hellen --ink (reines Schwarz) liegt .66 bei 6.93:1 und
// .72 bei 8.70:1, im dunklen Thema bei 7.14:1 und 8.36:1. --warn als Text
// liegt bei 6.70:1 (dunkel) und 4.61:1 (hell). Alles ueber AA.
export const TON_FARBE = {
  warn: 'var(--warn)',
  muted: 'var(--ink-2)',
  quiet: 'var(--ink-3)'
};

// Rueckfalltabelle, wortgleich mit app/suspicion.py SCORE_BANDS.
export const EINGEBAUTE_BANDS = [
  { from: 0, to: 39, label: 'FEW PATTERNS', tone: 'quiet', meaning: 'below the flag floor: counted, not shown as a card' },
  { from: 40, to: 54, label: 'SOME PATTERNS', tone: 'muted', meaning: 'cleared the flag floor: gets a card and a log row' },
  { from: 55, to: 69, label: 'MANY PATTERNS', tone: 'warn', meaning: 'tripped many of them' },
  { from: 70, to: 100, label: 'MOST PATTERNS', tone: 'warn', meaning: "tripped most of the screen's checks" }
];

/** Die Bandtabelle aus einer Antwort, sonst die eingebaute. Immer aufsteigend. */
export function bandTabelle(live) {
  const roh = live && Array.isArray(live.score_bands) && live.score_bands.length
    ? live.score_bands : EINGEBAUTE_BANDS;
  return roh
    .filter((b) => b && b.label)
    .map((b) => ({
      from: Number(b.from) || 0,
      to: b.to == null ? 100 : Number(b.to),
      label: String(b.label),
      tone: String(b.tone || 'quiet'),
      meaning: String(b.meaning || '')
    }))
    .sort((a, b) => a.from - b.from);
}

/** Farbe eines Bandes; unbekannte Toene fallen auf die leiseste Stufe. */
export function bandFarbe(tone) {
  return TON_FARBE[tone] || TON_FARBE.quiet;
}

/**
 * Band einer Punktzahl als [Beschriftung, Farbe] -- dieselbe Signatur, die
 * die Seiten vorher von ihrem eigenen BAND() bekommen haben.
 *
 * ``roh`` darf die ganze Zeile sein: traegt sie ein vom Server gerechnetes
 * ``band``, gewinnt das, damit Karte und API nie zwei Namen fuer dieselbe
 * Zahl fuehren.
 */
export function scoreBand(score, live, roh) {
  if (roh && roh.band && roh.band.label) {
    return [String(roh.band.label), bandFarbe(roh.band.tone)];
  }
  const wert = Number(score) || 0;
  const tabelle = bandTabelle(live);
  let treffer = tabelle[0];
  tabelle.forEach((b) => { if (wert >= b.from) treffer = b; });
  return treffer ? [treffer.label, bandFarbe(treffer.tone)] : ['', TON_FARBE.quiet];
}

/**
 * Die Legende: ein Chip je Band, mit seiner Punktspanne davor. Der Chip sagt
 * die Spanne mit, damit die Beschriftung nicht als Wahrscheinlichkeit
 * gelesen werden kann -- "40-54 PTS" ist eine Punktzahl, "MEDIUM" war eine
 * Einschaetzung.
 */
export function bandChips(live) {
  return bandTabelle(live).map((b) => {
    const spanne = b.from === 0 ? 'UNDER ' + (b.to + 1) : b.to >= 100 ? b.from + '+' : b.from + '–' + b.to;
    const farbe = bandFarbe(b.tone);
    const rahmen = b.tone === 'warn' ? 'color:' + farbe + '; border:1px solid color-mix(in srgb, ' + farbe + ' 33%, transparent)'
      : 'color:' + farbe + '; border:1px solid var(--line-1)';
    return '<div title="' + esc(b.meaning) + '" style="' + M + '; font-size:var(--t-micro); border-radius:var(--r-control); padding:var(--sp-2) var(--sp-3); ' + rahmen + '">'
      + esc(spanne) + ' PTS · ' + esc(b.label) + '</div>';
  }).join('');
}

/**
 * Der Zeiger auf das, was UEBER den Screen tatsaechlich gemessen wird.
 *
 * Ein Vorbehalt, der nur sagt, was fehlt, laesst den Leser ohne Anhalt. Das
 * Flag-Log misst eine andere Groesse als der Name des Scores nahelegt (folgte
 * der Preis der geflaggten Seite?) und tut es mit n, Intervall und einem Wort
 * zum Mehrfachvergleich. Die Groesse kommt aus score_validation der Antwort.
 */
export function gemessenSatz(live) {
  const v = live && live.score_validation ? live.score_validation : null;
  const groesse = v && v.measured_instead && v.measured_instead.quantity
    ? v.measured_instead.quantity
    : 'price of the flagged side at +30 min, +2 h and +24 h after the flag';
  return 'The one outcome this screen does measure is on the Flag log tab, and it is a different '
    + 'quantity: the ' + groesse + ', reported with n, a 95% interval and a note on how many '
    + 'comparisons the flags come out of.';
}

/**
 * Eine Zeile darueber, was die Punkte sind: Merkmale, Kappen, Herkunft der
 * Gewichte. Kommt aus score_basis der Antwort; ohne Antwort steht der Satz,
 * der auch ohne Zahlen wahr ist.
 */
export function basisSatz(live) {
  const b = live && live.score_basis ? live.score_basis : null;
  const anzahl = b && Array.isArray(b.features) ? b.features.length : 9;
  const floor = b && b.flag_floor != null ? b.flag_floor : 40;
  return anzahl + ' flow features, each capped at a fixed number of points, summed and cut off at 100. '
    + 'The caps are the weights and they were chosen, not estimated. '
    + 'A row is flagged from ' + floor + ' points up.';
}
