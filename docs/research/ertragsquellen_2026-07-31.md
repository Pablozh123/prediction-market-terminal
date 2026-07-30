# Woher kommt das Geld? Eigene Messung gegen Literatur (2026-07-31)

Diese Notiz fuehrt zusammen, was die eigenen Studien in `docs/research/` gemessen
haben und was die publizierte Forschung dazu sagt. Sie trifft keine Aussage
darueber, ob eine Strategie handelbar ist, sondern ordnet ein, welche Ertragswege
die Daten stuetzen und welche sie ausschliessen.

## Der Befund in einem Satz

Die Richtung vorherzusagen funktioniert messbar, lohnt sich aber nicht: die
Bruttokante des besten Buchsignals ist rund zwei Groessenordnungen kleiner als
die Kosten, sie einzusammeln. Was uebrig bleibt, ist die Gegenseite derselben
Transaktion - den Spread zu stellen statt ihn zu zahlen.

## Was die eigenen Daten zeigen

**Das Signal ist echt und zu klein.** Ueber 1,0 Millionen Beobachtungen an elf
Tagen zeigt die Buch-Imbalance eine Trefferquote von 55,2 Prozent
(Wilson-Untergrenze 55,0). Die mittlere Bruttokante betraegt 0,07 bis 0,28 Cent
je Signal. Eine Taker-Runde kostet 2,56 Cent, davon 1,65 Cent Gebuehr und 0,92
Cent Spread. Quelle: `orderflow_rest-2026-07.md`.

**Es gibt kein Segment, in dem das kippt.** 34 ex ante bekannte Schnitte
(Spread, Preisniveau, Signalstaerke, deren Kreuzung) in drei Gebuehrenkategorien.
In der gebuehrenfreien Kategorie, wo nur der Spread als Kosten bleibt, ueberlebt
ein einziges Segment beide Bedingungen - mit einem Konfidenzintervall, das die
Null einschliesst. Bei 34 Tests ist das genau die erwartete Falsch-Positiv-Rate.
Quelle: `edge_segments_july-2026.md`.

**Die Adverse Selektion ist ein Latenzproblem, kein Marktproblem.** Bei einem
Requote-Intervall von 120 Sekunden verdient das Quoting 1,4 Cent Spread je Fill
und verliert 3,6 bis 7,0 Cent an informierte Gegenparteien. Auf Sekunden-Daten,
gleicher Code, gleiche Parameter, faellt der Markout je Fill im Tape-Modell von
361 auf 4 Cent. Quelle: `mm_pnl_july-2026.md` gegen `mm_pnl_stream-first-hour.md`.
Der Stream-Lauf umfasst eine Stunde und 273 Fills und ist damit ein erster
Blick, kein Ergebnis; das steht auch im Report selbst.

**Das Signal hilft dem Market Making nicht.** Die Imbalance zu nutzen, um nur
die beguenstigte Seite zu quoten, senkt den Markout je Fill nicht (minus 361
gegen minus 365 Cent). Die bessere Gesamtsumme entsteht allein daraus, dass
weniger gehandelt wird. Weniger verlieren durch weniger handeln ist keine Kante.

## Was die Literatur dazu sagt

Drei unabhaengige Arbeiten kommen zum selben Schluss wie die eigene Messung,
auf beiden Venues und mit ungleich groesseren Stichproben.

- Akey, Gregoire, Harvie und Martineau (SSRN 6443103; Datensatz oeffentlich
  unter CC-BY): 2,47 Millionen Nutzer, 588 Millionen Trades. 68,8 Prozent
  verlieren Geld. Gewinner stellen Limit-Orders, Verlierer nehmen mit
  Market-Orders.
- Bartlett und O'Hara, "Adverse Selection in Prediction Markets: Evidence from
  Kalshi" (SSRN 6615739): 41,6 Millionen Trades. Market Maker verdienen in
  Einzelmaerkten doppelt so viel je Kontrakt. Die ausnutzbare Achse ist die
  YES/NO-Verzerrung, nicht Favorit gegen Aussenseiter.
- Buergi, Deng und Whelan (CEPR DP20631): Taker verlieren rund 32 Prozent,
  Maker rund 10 Prozent.

Zwei Anomalien, die naheliegen, sind bereits erklaert und keine Kante:

- Nahezu sichere Kontrakte sind nicht falsch bepreist. Der Abschlag ist eine
  Finanzierungspraemie von 3,06 bis 6,89 Prozent jaehrlich, weil das Kapital bis
  zur Aufloesung gebunden ist (Gebele und Matthes, arXiv 2605.31431). Nach
  Bereinigung verschwindet die Signifikanz.
- Ueberteuerte Aussenseiter auf Polymarket existieren, sind aber rund achtmal
  kleiner als der Spread, den man kreuzen muesste. Der mediane halbe Spread im
  Bereich unter 10 Cent betraegt 1.818 Basispunkte (Dubach, arXiv 2604.24366,
  vorregistriert).

Ein Ergebnis derselben Arbeit erklaert unabhaengig unser eigenes Nullresultat:
die Richtungsbestimmung von Trades ist auf Polymarket nahezu zufaellig
(Tick-Regel 49,83 Prozent, Bulk-Volume 50,51 Prozent). Unser Flow-Signal aus dem
gepollten Tape kam auf 51,3 Prozent Trefferquote. Beides passt zusammen und
heisst: Analysen, die auf abgeleiteter Handelsrichtung aufbauen, messen kaum
mehr als Muenzwuerfe.

## Die dritte Ertragsquelle, die in keiner PnL-Rechnung steht

Polymarket bezahlt Maker fuer blosse Praesenz nahe am Mid, unabhaengig davon, ob
ein Fill zustande kommt. Eigene Messung an der CLOB-API am 2026-07-31: 9.562
Maerkte mit Pool, zusammen 139.138 USD pro Tag. Median 3,00 USD je Markt und
Tag, Mittelwert 14,55, groesster Pool 1.000. Die modale Konfiguration bezahlt
Quotes innerhalb von 4,5 Cent um den Mid ab 20 Shares Groesse. Der Scoring-Regel
nach ist der Score quadratisch in der Naehe zum Mid.

Dazu kommen Maker-Rebates von 15 bis 25 Prozent der eingesammelten
Taker-Gebuehren, waehrend Maker selbst keine Gebuehr zahlen, sowie auf der
US-Plattform eine negative Maker-Gebuehr. Die drei Stroeme stapeln sich.

In unserer Simulation faellt der Reward-Posten klein aus (2,25 USD auf 34
Maerkte in einer Stunde), weil die Rechnung mit dem Median-Pool und ohne
Marktauswahl arbeitet. Genau darin liegt der Hinweis: der Hebel dieser
Ertragsquelle ist die Auswahl der Maerkte nach Pool-Groesse, nicht engeres
Quoten. Das legt die Rechnung nahe und belegt es nicht.

## Was daraus folgt

Fuer die Frage, wo positive Erwartung herkommen kann, ordnen die Daten die
Wege so:

1. **Liquiditaet stellen, schnell genug requotet.** Der einzige Weg, den sowohl
   die eigene Messung als auch drei unabhaengige Arbeiten stuetzen. Der
   Engpass ist nachweislich die Standzeit der Quote, nicht die Quote-Breite.
2. **Programmertraege als eigener Strom.** Rewards, Rebates und
   Open-Interest-Verguetung haengen nicht an einer Prognose. Sie gehoeren
   getrennt ausgewiesen, sonst schreibt man Programmgeld einer Handelsidee gut.
3. **Richtungswetten auf Buchsignale.** Nach dieser Messung nicht. Die Kante
   ist real und zu klein, und kein ex ante bekanntes Segment aendert das.

## Grenzen

Elf Tage REST-Daten und eine Stunde Sekunden-Daten, ein Venue, ein Ausschnitt
der aktivsten Maerkte, Papier-Simulation ohne Queue-Position und ohne Teilfills.
Der Sekunden-Befund ist der wichtigste und zugleich der duennste; er wiederholt
sich erst dann als Ergebnis, wenn mehrere Tage Stream-Material vorliegen und
walk-forward getrennt werden kann. Die Gebuehrenraten stammen aus der
Venue-Dokumentation vom 2026-07-30 und sind ueberschreibbar.

Read-only-Forschung, keine Handelsempfehlung, keine Renditeaussage.
