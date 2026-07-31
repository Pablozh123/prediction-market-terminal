# Lebensdauer einer Cross-Venue-Luecke (2026-07-31)

Quelle: C:\Users\chole\Projects\prediction-market-terminal\data\microstructure, beide Stream-Recorder. Basketgroesse 100 Shares, Gegenseite hoechstens 60 Sekunden alt, Gebuehrenstand 2026-07-30. 5 von 5 Paaren mit Aufzeichnung auf beiden Seiten, 6 offene Fenster insgesamt.

| Paar | Beobachtungen | Stunden | Fenster | offen (s) | Anteil offen | laengstes (s) | median (s) | ab 5s | Spitze netto (c) |
|---|---|---|---|---|---|---|---|---|---|
| KXEUROVISIONHOST-27-SOF | 109 | 11.56 | 3 | 4828 | 11.6% | 4827 | 0.83 | 1 | +4.72 |
| KXPRESPERSON-28-DTRU | 13 | 11.56 | 0 | 0 | 0.0% | 0 | - | 0 | +0.00 |
| KXPRESPERSON-28-MRUB | 21 | 11.56 | 1 | 41626 | 100.0% | 41626 | 41625.85 | 1 | +3.18 |
| KXFRENCHPRES-27-MLEP | 27 | 11.56 | 1 | 41626 | 100.0% | 41626 | 41626.05 | 1 | +3.27 |
| KXPRESNOMD-28-JBP | 26 | 11.56 | 1 | 41626 | 100.0% | 41626 | 41625.95 | 1 | +1.17 |

## Lesehilfe

Ein offenes Fenster heisst: zu diesem Zeitpunkt haetten beide Beine zusammen nach Abzug beider Gebuehrenkurven Geld gebracht. Die Spalte Anteil offen ist der Bruchteil der beobachteten Zeit, in dem das galt. Die Spalte ab 5s zaehlt nur Fenster, die lange genug offen waren, um sie ueber einen REST-Weg oder von Hand ueberhaupt zu erreichen; kuerzere sind fuer alles ausser einer stehenden Order Theorie.

Die Zuordnung schaut ausschliesslich zurueck. Jede Kalshi-Beobachtung wird mit der letzten Polymarket-Notierung davor gepaart, und verworfen, wenn die aelter ist als die erlaubte Standzeit. Nach vorne zu schauen waere bequemer und wuerde Preise aus der Zukunft verwenden.

**Ein Fenster ist so dicht wie die Beobachtungen darin.** Die Recorder schreiben nur, wenn sich das Top of Book bewegt, und diese Maerkte bewegen sich kaum: ein Paar kann ueber elf Stunden zwei Dutzend Beobachtungen haben. Ein Fenster ueber diese Spanne heisst dann nicht, dass die Luecke nachweislich durchgehend offen war, sondern dass sie zu jedem Zeitpunkt offen war, zu dem wir hingesehen haben. Die Spalte Beobachtungen gehoert deshalb immer mitgelesen.

Der Befund passt zur annualisierten Rechnung der Schnappschuss-Studie und erklaert sie. Diese Luecken schliessen sich nicht in Sekunden, sie stehen stundenlang offen - weil sie keine Arbitrage sind. Wer sie nimmt, bindet Kapital bis zur Aufloesung, und bei 830 Tagen Restlaufzeit ist eine Kante von wenigen Cent gut ein Prozent im Jahr. Der Markt versaeumt es nicht, die Luecke zu schliessen; die Luecke ist der Preis fuer das gebundene Kapital und das Regelrisiko auf beiden Seiten.

Grenzen: die Paare sind titel-gematcht und ihre Aufloesungsregeln nicht verglichen, es bleibt also offen, ob ein Basket ueberhaupt abgesichert waere. Tiefe geht nicht ein, die Zahlen gelten fuer die Standardgroesse und nicht fuer das, was wirklich im Buch liegt. Gleichzeitige Ausfuehrung beider Beine ist unterstellt. Und ein Fenster ist eine Beobachtung, keine Gelegenheit: wer hineinginge, veraenderte es.

Read-only-Forschung, keine Handelsempfehlung.