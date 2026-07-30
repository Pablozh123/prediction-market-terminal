# Paper-MM PnL-Zerlegung (july-2026)

Quelle: data/microstructure (REST, 120s-Raster), 4489 Tokens, 370,423 Snapshots, 678,665 Tape-Prints, 11 Tage (2026-07-18 bis 2026-07-28).

Quoting: halber Spread 0.01, gamma 0.08, Quote 50.0 USD, Inventar-Cap 250.0 USD. Maker-Oekonomie der Kategorie sports, Gebuehrenstand 2026-07-30.

| Posten | Touch-Modell (USD) | Tape-Modell (USD) |
|---|---|---|
| Fills | 32,522 | 13,330 |
| Spread-Ertrag | +43249.86 | +19773.76 |
| Markout 5min (Adverse Selektion) | -226800.91 | -48149.94 |
| spaeterer Drift (Inventar) | -14355.77 | -18877.78 |
| Maker-Rebate | +6112.68 | +2518.26 |
| mark-to-mid (Identitaet) | -197906.83 | -47253.96 |
| Summe | -191794.15 | -44735.70 |
| Spread-Ertrag je Fill (Cents) | +132.986 | +148.340 |
| Markout je Fill (Cents) | -697.377 | -361.215 |
| Ergebnis je Fill (Cents) | -589.737 | -335.602 |
| mittleres |Inventar| (USD) | 38.90 | 40.60 |
| max |Inventar| (USD) | 1449.18 | 1490.59 |

## touch-Fill-Modell

Block-Bootstrap-CI 95% auf Tagesebene fuer die Tagessumme: (-19709.4697, -15189.0143) USD.

| gamma | Fills | Spread-Ertrag | Markout | Summe | mittleres \|Inventar\| |
|---|---|---|---|---|---|
| 0.00 | 30,866 | +45393.96 | -222742.24 | -190237.44 | 82.89 |
| 0.04 | 31,792 | +44640.92 | -226290.74 | -189889.28 | 49.95 |
| 0.08 | 32,522 | +43249.86 | -226800.91 | -191794.15 | 38.90 |
| 0.16 | 33,013 | +40624.05 | -225560.54 | -198081.38 | 27.51 |
| 0.32 | 33,240 | +36695.37 | -223893.72 | -204086.46 | 20.81 |

| halber Spread | Fills | Spread-Ertrag | Markout | Ertrag/Markout | Summe |
|---|---|---|---|---|---|
| 0.005 | 42,091 | +27430.02 | -242195.96 | 0.11 | -237711.34 |
| 0.010 | 32,522 | +43249.86 | -226800.91 | 0.19 | -191794.15 |
| 0.020 | 23,325 | +62271.13 | -198129.01 | 0.31 | -140211.00 |
| 0.040 | 13,659 | +70996.12 | -149482.90 | 0.47 | -81094.70 |
| 0.080 | 6,106 | +61874.80 | -90601.57 | 0.68 | -40897.74 |

Walk-forward: auf den fruehen Tagen gewaehltes gamma 0.04; auf den spaeten Tagen ergibt es -90024.97 USD gegen -90115.81 USD ohne Skew (gamma 0).

## tape-Fill-Modell

Block-Bootstrap-CI 95% auf Tagesebene fuer die Tagessumme: (-5166.9912, -2784.1748) USD.

| gamma | Fills | Spread-Ertrag | Markout | Summe | mittleres \|Inventar\| |
|---|---|---|---|---|---|
| 0.00 | 11,985 | +19604.66 | -48124.39 | -46482.45 | 93.85 |
| 0.04 | 12,873 | +20023.49 | -48407.03 | -45316.96 | 53.60 |
| 0.08 | 13,330 | +19773.76 | -48149.94 | -44735.70 | 40.60 |
| 0.16 | 13,559 | +19044.41 | -48328.68 | -42929.74 | 28.95 |
| 0.32 | 13,525 | +17789.62 | -45791.39 | -40385.26 | 21.42 |

| halber Spread | Fills | Spread-Ertrag | Markout | Ertrag/Markout | Summe |
|---|---|---|---|---|---|
| 0.005 | 19,993 | +15579.56 | -49003.27 | 0.32 | -49122.39 |
| 0.010 | 13,330 | +19773.76 | -48149.94 | 0.41 | -44735.70 |
| 0.020 | 8,333 | +23981.09 | -42183.37 | 0.57 | -28310.84 |
| 0.040 | 4,670 | +27132.43 | -31557.60 | 0.86 | -8446.11 |
| 0.080 | 1,969 | +21390.88 | -20232.87 | 1.06 | -5102.78 |

Walk-forward: auf den fruehen Tagen gewaehltes gamma 0.32; auf den spaeten Tagen ergibt es -22953.55 USD gegen -26568.69 USD ohne Skew (gamma 0).

## Lesehilfe

Die drei Preisposten sind keine Schaetzung, sondern eine Identitaet: Spread-Ertrag plus Markout plus spaeterer Drift ergibt exakt den mark-to-mid Endwert je Fill. Der Spread-Ertrag ist, was das Quoting verdient hat, der Markout ist, was informierte Gegenparteien davon zurueckgeholt haben, der spaetere Drift ist der Preis des getragenen Inventars.

Die beiden Fill-Modelle klammern die Wahrheit ein. Touch fuellt nur, wenn die Gegenseite unsere Quote kreuzt, ignoriert also Fills am Touch und unterschaetzt die Fill-Zahl. Tape fuellt bei jedem kreuzenden Print, unterstellt also Queue-Prioritaet und ueberschaetzt sie. Wer nur ein Modell rechnet, waehlt sein Ergebnis mit der Annahme.

Die Spalte Ertrag/Markout in der Breiten-Tabelle ist die Break-even-Kennzahl: unter 1 frisst die Adverse Selektion mehr, als das Quoting einnimmt. Sie steigt mit der Quote-Breite, weil der Spread-Ertrag mit der Breite waechst, die Gegenbewegung aber von der Marktbewegung bestimmt wird und nicht von unserer Quote. Wo die Kennzahl 1 kreuzt, brechen zugleich die Fills ein - eine so breite Quote steht am Markt vorbei.

Maker zahlen auf Polymarket keine Gebuehr und bekommen einen Anteil der eingesammelten Taker-Gebuehren zurueck. Der Rebate ist hier die Obergrenze dieses Anteils, die tatsaechliche Tagesverteilung kann niedriger ausfallen.

Wichtigste Einschraenkung, und zugleich der eigentliche Befund: das 120-Sekunden-Raster bedeutet, dass jede Quote zwei Minuten unveraendert im Buch steht. Genau diese Standzeit ist die gemessene Adverse Selektion - gefuellt wird man bevorzugt dann, wenn der Markt an der veralteten Quote vorbeigelaufen ist. Ein echter Market Maker requotet im Millisekundenbereich. Diese Zahlen messen deshalb nicht, ob Market Making auf Polymarket funktioniert, sondern was passiert, wenn man zwei Minuten lang nicht nachzieht. Die Wiederholung auf den Sekunden-Daten des Stream-Recorders ist der Test, der die Frage wirklich beantwortet.

Weitere Grenzen: mark-to-mid ohne Aufloesungs-Modellierung, Quotes nur bei Mid in (0.05, 0.95) und Spread bis 0.10, keine Queue-Position, keine Teilfills. Paper-only, keine Handelsempfehlung.