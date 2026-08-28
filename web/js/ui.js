// Die Rezepte, die vorher in jeder Seitendatei noch einmal standen.
//
// Das Design-Review vom 2026-08-28 hat sie ausgezaehlt: der Mono-String
// zehnmal, die Kartenflaeche sechsmal, die Tabellenkopfzelle fuenfmal, das
// Blocklabel viermal, die Notizzeile zweimal -- jedes Mal zeichengleich, und
// dazu elf verschiedene Bauer fuer dieselbe Kennzahlenkachel, von denen keine
// zwei sich ueber Polsterung und Abstand einig waren. Hier steht jedes Rezept
// einmal.
//
// Farben, Groessen und Radien kommen ausschliesslich aus den Tokens in
// web/css/terminal.css. In diese Datei gehoert kein Literal.

export const MONO = 'font-family:var(--font-mono)';
export const UI = 'font-family:var(--font-ui)';

// Die Kartenflaeche: Panel-Grund, Haarlinie, Panel-Radius.
export const KARTE = 'background:var(--panel); border:1px solid var(--line-2); border-radius:var(--r-panel)';

// Das Mikrolabel ueber einer Zahl und in jedem Tabellenkopf.
export const LABEL = MONO + '; font-size:var(--t-micro); letter-spacing:.14em; color:var(--ink-3)';
// Dasselbe Label als eigener Block ueber einem Bedienelement.
export const LABEL_BLOCK = LABEL + '; margin-bottom:6px';
// Die Notizzeile im Fliesstext: gleiche Groesse, keine Sperrung, eigener
// Zeilenabstand, weil sie umbricht.
export const NOTIZ = MONO + '; font-size:var(--t-micro); color:var(--ink-3); line-height:1.6';
// Die Unterzeile direkt unter einer Zahl. Sie ist einzeilig, deshalb kein
// eigener Zeilenabstand.
export const UNTERZEILE = MONO + '; font-size:var(--t-micro); color:var(--ink-3)';

const TON_RAHMEN = {
  up: 'rgba(var(--pos-rgb),.35)',
  down: 'rgba(var(--neg-rgb),.35)',
  warn: 'rgba(var(--warn-rgb),.4)',
  info: 'rgba(var(--info-rgb),.3)'
};
const TON_FARBE = {
  up: 'var(--pos)', down: 'var(--neg)', warn: 'var(--warn)', info: 'var(--text)'
};

// Eine Kennzahlenkachel. Zwei Formen, weil es zwei Orte gibt, an denen eine
// Zahl steht:
//
//   form 'band'  Zelle in einer Kennzahlenzeile ueber der Tabelle, von der
//                naechsten durch eine Linie getrennt, ohne eigene Flaeche.
//   form 'karte' eigenstaendige Karte in einem Raster.
//
// Alles andere ist eine Angabe, keine Variante:
//   label   Text des Mikrolabels (bereits maskiert)
//   wert    die Zahl selbst (bereits maskiert)
//   sub     Unterzeile; null laesst sie ganz weg, '' haelt den Platz
//   farbe   Farbe des Wertes; schlaegt ton
//   ton     'up' | 'down' | 'warn' | 'info' -- faerbt Wert und Rahmen
//   gross   true = --t-hero statt --t-head (die eine Zahl einer Seite)
//   trenner true = rechte Trennlinie (nur form 'band')
//   kuerzen true = eine Zeile mit Auslassungspunkten statt Umbruch
//   badge   fertiges Markup rechts neben dem Label
//   polsterung nur fuer 'band': eigene Polsterung, wenn die Zelle mit der
//              Rinne der Tabelle darunter fluchten muss statt mit sich selbst
export function kpi(o) {
  const band = o.form === 'band';
  const farbe = o.farbe || (o.ton ? TON_FARBE[o.ton] : null) || 'var(--text)';
  const rahmen = o.ton ? TON_RAHMEN[o.ton] : null;
  const huelle = band
    ? 'padding:' + (o.polsterung || '16px 20px')
      + (o.trenner ? '; border-right:1px solid var(--line-2)' : '')
    : KARTE + '; padding:14px 16px' + (rahmen ? '; border-color:' + rahmen : '');
  const kurz = o.kuerzen ? '; white-space:nowrap; overflow:hidden; text-overflow:ellipsis' : '';
  const kopf = o.badge
    ? '<div style="display:flex; justify-content:space-between; gap:8px; align-items:center">'
      + '<div style="' + LABEL + '">' + o.label + '</div>' + o.badge + '</div>'
    : '<div style="' + LABEL + '">' + o.label + '</div>';
  return '<div style="' + huelle + '">'
    + kopf
    + '<div style="' + MONO + '; font-size:' + (o.gross ? 'var(--t-hero)' : 'var(--t-head)')
    + '; margin-top:' + (band ? '8px' : '7px') + '; color:' + farbe + kurz + '">'
    + o.wert + '</div>'
    // kuerzen gilt nur fuer den Wert. Die Unterzeile darf umbrechen: sie
    // traegt Herkunft und Nenner, und ein abgeschnittenes "n 12 rows, 6 won"
    // ist schlimmer als eine zweite Zeile.
    + (o.sub == null ? ''
      : '<div style="' + UNTERZEILE + '; margin-top:4px">' + o.sub + '</div>')
    + '</div>';
}
