# Paper-MM PnL-Zerlegung (stream-first-hour)

Quelle: data/microstructure (Stream, ereignisgetrieben), 38 Tokens, 56,482 Snapshots, 3,276 Tape-Prints, 1 Tage (2026-07-30 bis 2026-07-30).

Quoting: halber Spread 0.01, gamma 0.08, Quote 50.0 USD, Inventar-Cap 250.0 USD. Maker-Oekonomie der Kategorie sports, Gebuehrenstand 2026-07-30.

| Posten | Touch-Modell (USD) | Tape-Modell (USD) |
|---|---|---|
| Fills | 92 | 288 |
| Spread-Ertrag | +136.40 | +395.95 |
| Markout 5min (Adverse Selektion) | -238.24 | -6.48 |
| spaeterer Drift (Inventar) | +33.87 | -37.12 |
| Maker-Rebate | +17.51 | +52.04 |
| mark-to-mid (Identitaet) | -67.98 | +352.34 |
| Summe | -50.47 | +404.38 |
| Spread-Ertrag je Fill (Cents) | +148.260 | +137.481 |
| Markout je Fill (Cents) | -258.962 | -2.250 |
| Ergebnis je Fill (Cents) | -54.860 | +140.410 |
| mittleres |Inventar| (USD) | 29.56 | 50.04 |
| max |Inventar| (USD) | 166.19 | 309.01 |

## touch-Fill-Modell

Block-Bootstrap-CI 95% auf Tagesebene fuer die Tagessumme: nicht berechenbar USD.

| gamma | Fills | Spread-Ertrag | Markout | Summe | mittleres \|Inventar\| |
|---|---|---|---|---|---|
| 0.00 | 92 | +151.93 | -131.53 | +352.26 | 63.12 |
| 0.04 | 94 | +144.88 | -228.75 | +168.19 | 39.40 |
| 0.08 | 92 | +136.40 | -238.24 | -50.47 | 29.56 |
| 0.16 | 100 | +119.45 | -238.29 | -135.63 | 22.20 |
| 0.32 | 131 | +103.03 | -248.28 | -366.28 | 16.68 |

Liquiditaets-Rewards: im Schnitt 100% der Quote-Zeit innerhalb der Reward-Spanne, 36 Maerkte, Pool-Annahme 3.0 USD pro Markt und Tag (Median der 9,562 Maerkte mit Pool, Stand 2026-07-31).

| Konkurrenz (Vielfaches des eigenen Scores) | eigener Anteil | Reward (USD) | Summe inkl. Reward (USD) |
|---|---|---|---|
| 1x | 50.0% | +2.55 | -47.92 |
| 5x | 16.7% | +0.85 | -49.62 |
| 20x | 4.8% | +0.24 | -50.23 |

| Quoting-Modus | Fills | Spread-Ertrag je Fill (c) | Markout je Fill (c) | Summe (USD) | CI95 Tagessumme |
|---|---|---|---|---|---|
| symmetric | 92 | +148.26 | -258.96 | -50.47 | - |
| signal | 54 | +151.69 | -312.14 | -260.88 | - |
| lean | 80 | +147.38 | -254.74 | -62.56 | - |

| halber Spread | Fills | Spread-Ertrag | Markout | Ertrag/Markout | Summe |
|---|---|---|---|---|---|
| 0.005 | 216 | +139.63 | -304.77 | 0.46 | -94.54 |
| 0.010 | 92 | +136.40 | -238.24 | 0.57 | -50.47 |
| 0.020 | 28 | +97.52 | -68.76 | 1.42 | -202.26 |
| 0.040 | 6 | +36.45 | -57.47 | 0.63 | -219.18 |
| 0.080 | 2 | +18.63 | +0.00 | - | -147.42 |

Walk-forward: auf den fruehen Tagen gewaehltes gamma 0.0; auf den spaeten Tagen ergibt es - USD gegen - USD ohne Skew (gamma 0).

## tape-Fill-Modell

Block-Bootstrap-CI 95% auf Tagesebene fuer die Tagessumme: nicht berechenbar USD.

| gamma | Fills | Spread-Ertrag | Markout | Summe | mittleres \|Inventar\| |
|---|---|---|---|---|---|
| 0.00 | 282 | +456.67 | -81.40 | -161.32 | 163.59 |
| 0.04 | 297 | +442.41 | -51.44 | +449.91 | 85.35 |
| 0.08 | 288 | +395.95 | -6.48 | +404.38 | 50.04 |
| 0.16 | 304 | +358.36 | +4.71 | +327.00 | 32.48 |
| 0.32 | 314 | +243.99 | -38.31 | +162.72 | 24.67 |

Liquiditaets-Rewards: im Schnitt 100% der Quote-Zeit innerhalb der Reward-Spanne, 36 Maerkte, Pool-Annahme 3.0 USD pro Markt und Tag (Median der 9,562 Maerkte mit Pool, Stand 2026-07-31).

| Konkurrenz (Vielfaches des eigenen Scores) | eigener Anteil | Reward (USD) | Summe inkl. Reward (USD) |
|---|---|---|---|
| 1x | 50.0% | +2.55 | +406.93 |
| 5x | 16.7% | +0.85 | +405.23 |
| 20x | 4.8% | +0.24 | +404.62 |

| Quoting-Modus | Fills | Spread-Ertrag je Fill (c) | Markout je Fill (c) | Summe (USD) | CI95 Tagessumme |
|---|---|---|---|---|---|
| symmetric | 288 | +137.48 | -2.25 | +404.38 | - |
| signal | 226 | +138.22 | +26.83 | +193.34 | - |
| lean | 254 | +144.01 | +20.66 | +321.07 | - |

| halber Spread | Fills | Spread-Ertrag | Markout | Ertrag/Markout | Summe |
|---|---|---|---|---|---|
| 0.005 | 617 | +369.95 | -155.19 | 2.38 | +203.49 |
| 0.010 | 288 | +395.95 | -6.48 | 61.10 | +404.38 |
| 0.020 | 56 | +213.15 | +1.85 | 115.21 | +222.30 |
| 0.040 | 11 | +193.53 | -1.13 | 171.78 | +87.72 |
| 0.080 | 1 | +5.81 | +0.00 | - | -45.99 |

Walk-forward: auf den fruehen Tagen gewaehltes gamma 0.04; auf den spaeten Tagen ergibt es - USD gegen - USD ohne Skew (gamma 0).

## Lesehilfe

Die drei Preisposten sind keine Schaetzung, sondern eine Identitaet: Spread-Ertrag plus Markout plus spaeterer Drift ergibt exakt den mark-to-mid Endwert je Fill. Der Spread-Ertrag ist, was das Quoting verdient hat, der Markout ist, was informierte Gegenparteien davon zurueckgeholt haben, der spaetere Drift ist der Preis des getragenen Inventars.

Die beiden Fill-Modelle klammern die Wahrheit ein. Touch fuellt nur, wenn die Gegenseite unsere Quote kreuzt, ignoriert also Fills am Touch und unterschaetzt die Fill-Zahl. Tape fuellt bei jedem kreuzenden Print, unterstellt also Queue-Prioritaet und ueberschaetzt sie. Wer nur ein Modell rechnet, waehlt sein Ergebnis mit der Annahme.

Die Spalte Ertrag/Markout in der Breiten-Tabelle ist die Break-even-Kennzahl: unter 1 frisst die Adverse Selektion mehr, als das Quoting einnimmt. Sie steigt mit der Quote-Breite, weil der Spread-Ertrag mit der Breite waechst, die Gegenbewegung aber von der Marktbewegung bestimmt wird und nicht von unserer Quote. Wo die Kennzahl 1 kreuzt, brechen zugleich die Fills ein - eine so breite Quote steht am Markt vorbei.

Maker zahlen auf Polymarket keine Gebuehr und bekommen einen Anteil der eingesammelten Taker-Gebuehren zurueck. Der Rebate ist hier die Obergrenze dieses Anteils, die tatsaechliche Tagesverteilung kann niedriger ausfallen.

Die Liquiditaets-Rewards sind der dritte Ertragsposten und der einzige, der nicht davon abhaengt, ob ein Fill zustande kommt: bezahlt wird Praesenz nahe am Mid. Der eigene Anteil laesst sich nicht berechnen, weil er von allen anderen Makern im selben Markt abhaengt, deshalb steht dort eine Spanne statt einer Zahl. Die Pool-Annahme ist der Median ueber alle Maerkte mit Pool und damit bewusst konservativ: die Verteilung ist stark rechtsschief, der groesste Pool liegt bei 1000 USD pro Tag gegen einen Median von 3. Der Hebel bei dieser Ertragsquelle ist deshalb die Marktauswahl, nicht das engere Quoten - eine Aussage, die diese Rechnung nahelegt und nicht belegt, weil hier nicht nach Pool-Groesse ausgewaehlt wurde.

Aufloesung: die Quotes werden bei jeder Bewegung des Top of Book neu gestellt, im Median unter einer Sekunde. Das ist der Fall, den der REST-Lauf nicht messen kann, und der einzige, in dem die Frage nach Market Making ueberhaupt sinnvoll gestellt ist.

ACHTUNG Stichprobe: 1 Tag(e), hoechstens 288 Fills. Unter 3 Tagen laesst sich weder walk-forward trennen noch ein Tages-Bootstrap rechnen, und die Auswahl der Tokens und Tageszeiten ist nicht repraesentativ. Dieser Lauf ist ein erster Blick, aus dem keine Aussage ueber Profitabilitaet folgt.

Die beiden Fill-Modelle sind sich hier nicht einmal im Vorzeichen einig. Damit ist das Ergebnis unentschieden: welches Vorzeichen man berichtet, waehlt in diesem Lauf die Fill-Annahme und nicht die Daten.

Weitere Grenzen: mark-to-mid ohne Aufloesungs-Modellierung, Quotes nur bei Mid in (0.05, 0.95) und Spread bis 0.10, keine Queue-Position, keine Teilfills. Paper-only, keine Handelsempfehlung.