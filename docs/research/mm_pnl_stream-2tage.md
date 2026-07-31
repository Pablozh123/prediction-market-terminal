# Paper-MM PnL-Zerlegung (stream-2tage)

Quelle: data/microstructure (Stream, ereignisgetrieben), 112 Tokens, 1,049,354 Snapshots, 39,774 Tape-Prints, 2 Tage (2026-07-30 bis 2026-07-31).

Quoting: halber Spread 0.01, gamma 0.08, Quote 50.0 USD, Inventar-Cap 250.0 USD. Maker-Oekonomie der Kategorie sports, Gebuehrenstand 2026-07-30.

| Posten | Touch-Modell (USD) | Tape-Modell (USD) |
|---|---|---|
| Fills | 2,277 | 3,260 |
| Spread-Ertrag | +2705.17 | +4579.52 |
| Markout 5min (Adverse Selektion) | -6752.96 | -532.11 |
| spaeterer Drift (Inventar) | -1212.98 | +1363.59 |
| Maker-Rebate | +426.25 | +585.77 |
| mark-to-mid (Identitaet) | -5260.77 | +5411.00 |
| Summe | -4834.52 | +5996.77 |
| Spread-Ertrag je Fill (Cents) | +118.804 | +140.476 |
| Markout je Fill (Cents) | -296.573 | -16.322 |
| Ergebnis je Fill (Cents) | -212.320 | +183.950 |
| mittleres |Inventar| (USD) | 41.62 | 75.86 |
| max |Inventar| (USD) | 957.57 | 756.20 |

## touch-Fill-Modell

Block-Bootstrap-CI 95% auf Tagesebene fuer die Tagessumme: nicht berechenbar USD.

| gamma | Fills | Spread-Ertrag | Markout | Summe | mittleres \|Inventar\| |
|---|---|---|---|---|---|
| 0.00 | 2,110 | +3056.06 | -5642.88 | -3471.88 | 125.50 |
| 0.04 | 2,115 | +2800.88 | -6189.87 | -3494.62 | 62.93 |
| 0.08 | 2,277 | +2705.17 | -6752.96 | -4834.52 | 41.62 |
| 0.16 | 2,528 | +2438.60 | -6997.19 | -5587.06 | 27.39 |
| 0.32 | 3,134 | +1835.37 | -7289.59 | -6817.28 | 17.90 |

Liquiditaets-Rewards: im Schnitt 100% der Quote-Zeit innerhalb der Reward-Spanne, 112 Maerkte, Pool-Annahme 3.0 USD pro Markt und Tag (Median der 9,562 Maerkte mit Pool, Stand 2026-07-31).

| Konkurrenz (Vielfaches des eigenen Scores) | eigener Anteil | Reward (USD) | Summe inkl. Reward (USD) |
|---|---|---|---|
| 1x | 50.0% | +42.06 | -4792.46 |
| 5x | 16.7% | +14.02 | -4820.50 |
| 20x | 4.8% | +4.01 | -4830.52 |

| Quoting-Modus | Fills | Spread-Ertrag je Fill (c) | Markout je Fill (c) | Summe (USD) | CI95 Tagessumme |
|---|---|---|---|---|---|
| symmetric | 2,277 | +118.80 | -296.57 | -4834.52 | - |
| signal | 1,415 | +120.52 | -288.60 | -2337.66 | - |
| lean | 1,825 | +120.93 | -292.80 | -3150.26 | - |

| halber Spread | Fills | Spread-Ertrag | Markout | Ertrag/Markout | Summe |
|---|---|---|---|---|---|
| 0.005 | 4,730 | +2557.80 | -11009.66 | 0.23 | -9036.19 |
| 0.010 | 2,277 | +2705.17 | -6752.96 | 0.40 | -4834.52 |
| 0.020 | 839 | +2148.22 | -3425.36 | 0.63 | -2072.32 |
| 0.040 | 233 | +1228.93 | -1934.77 | 0.64 | -1267.51 |
| 0.080 | 53 | +519.68 | -666.31 | 0.78 | -139.69 |

Walk-forward: auf den fruehen Tagen gewaehltes gamma 0.0; auf den spaeten Tagen ergibt es -3286.37 USD gegen -3286.37 USD ohne Skew (gamma 0).

## tape-Fill-Modell

Block-Bootstrap-CI 95% auf Tagesebene fuer die Tagessumme: nicht berechenbar USD.

| gamma | Fills | Spread-Ertrag | Markout | Summe | mittleres \|Inventar\| |
|---|---|---|---|---|---|
| 0.00 | 2,647 | +4810.55 | -494.28 | +6251.95 | 221.81 |
| 0.04 | 3,152 | +4816.95 | -117.47 | +6550.77 | 113.57 |
| 0.08 | 3,260 | +4579.52 | -532.11 | +5996.77 | 75.86 |
| 0.16 | 3,300 | +4067.88 | -912.80 | +4778.91 | 48.16 |
| 0.32 | 3,668 | +3263.32 | -1249.14 | +3602.06 | 34.51 |

Liquiditaets-Rewards: im Schnitt 100% der Quote-Zeit innerhalb der Reward-Spanne, 112 Maerkte, Pool-Annahme 3.0 USD pro Markt und Tag (Median der 9,562 Maerkte mit Pool, Stand 2026-07-31).

| Konkurrenz (Vielfaches des eigenen Scores) | eigener Anteil | Reward (USD) | Summe inkl. Reward (USD) |
|---|---|---|---|
| 1x | 50.0% | +42.06 | +6038.83 |
| 5x | 16.7% | +14.02 | +6010.79 |
| 20x | 4.8% | +4.01 | +6000.78 |

| Quoting-Modus | Fills | Spread-Ertrag je Fill (c) | Markout je Fill (c) | Summe (USD) | CI95 Tagessumme |
|---|---|---|---|---|---|
| symmetric | 3,260 | +140.48 | -16.32 | +5996.77 | - |
| signal | 2,374 | +135.08 | -27.44 | +3624.13 | - |
| lean | 2,881 | +140.30 | -15.80 | +4994.73 | - |

| halber Spread | Fills | Spread-Ertrag | Markout | Ertrag/Markout | Summe |
|---|---|---|---|---|---|
| 0.005 | 7,660 | +5023.78 | -1629.17 | 3.08 | +5530.63 |
| 0.010 | 3,260 | +4579.52 | -532.11 | 8.61 | +5996.77 |
| 0.020 | 901 | +3038.56 | -148.20 | 20.50 | +4076.58 |
| 0.040 | 195 | +1916.53 | +828.86 | 2.31 | +3510.23 |
| 0.080 | 41 | +335.95 | -35.27 | 9.53 | +414.43 |

Walk-forward: auf den fruehen Tagen gewaehltes gamma 0.04; auf den spaeten Tagen ergibt es +6266.37 USD gegen +6480.55 USD ohne Skew (gamma 0).

## Lesehilfe

Die drei Preisposten sind keine Schaetzung, sondern eine Identitaet: Spread-Ertrag plus Markout plus spaeterer Drift ergibt exakt den mark-to-mid Endwert je Fill. Der Spread-Ertrag ist, was das Quoting verdient hat, der Markout ist, was informierte Gegenparteien davon zurueckgeholt haben, der spaetere Drift ist der Preis des getragenen Inventars.

Die beiden Fill-Modelle klammern die Wahrheit ein. Touch fuellt nur, wenn die Gegenseite unsere Quote kreuzt, ignoriert also Fills am Touch und unterschaetzt die Fill-Zahl. Tape fuellt bei jedem kreuzenden Print, unterstellt also Queue-Prioritaet und ueberschaetzt sie. Wer nur ein Modell rechnet, waehlt sein Ergebnis mit der Annahme.

Die Spalte Ertrag/Markout in der Breiten-Tabelle ist die Break-even-Kennzahl: unter 1 frisst die Adverse Selektion mehr, als das Quoting einnimmt. Sie steigt mit der Quote-Breite, weil der Spread-Ertrag mit der Breite waechst, die Gegenbewegung aber von der Marktbewegung bestimmt wird und nicht von unserer Quote. Wo die Kennzahl 1 kreuzt, brechen zugleich die Fills ein - eine so breite Quote steht am Markt vorbei.

Maker zahlen auf Polymarket keine Gebuehr und bekommen einen Anteil der eingesammelten Taker-Gebuehren zurueck. Der Rebate ist hier die Obergrenze dieses Anteils, die tatsaechliche Tagesverteilung kann niedriger ausfallen.

Die Liquiditaets-Rewards sind der dritte Ertragsposten und der einzige, der nicht davon abhaengt, ob ein Fill zustande kommt: bezahlt wird Praesenz nahe am Mid. Der eigene Anteil laesst sich nicht berechnen, weil er von allen anderen Makern im selben Markt abhaengt, deshalb steht dort eine Spanne statt einer Zahl. Die Pool-Annahme ist der Median ueber alle Maerkte mit Pool und damit bewusst konservativ: die Verteilung ist stark rechtsschief, der groesste Pool liegt bei 1000 USD pro Tag gegen einen Median von 3. Der Hebel bei dieser Ertragsquelle ist deshalb die Marktauswahl, nicht das engere Quoten - eine Aussage, die diese Rechnung nahelegt und nicht belegt, weil hier nicht nach Pool-Groesse ausgewaehlt wurde.

Aufloesung: die Quotes werden bei jeder Bewegung des Top of Book neu gestellt, im Median unter einer Sekunde. Das ist der Fall, den der REST-Lauf nicht messen kann, und der einzige, in dem die Frage nach Market Making ueberhaupt sinnvoll gestellt ist.

ACHTUNG Stichprobe: 2 Tag(e), hoechstens 3,260 Fills. Unter 3 Tagen laesst sich weder walk-forward trennen noch ein Tages-Bootstrap rechnen, und die Auswahl der Tokens und Tageszeiten ist nicht repraesentativ. Dieser Lauf ist ein erster Blick, aus dem keine Aussage ueber Profitabilitaet folgt.

Die beiden Fill-Modelle sind sich hier nicht einmal im Vorzeichen einig. Damit ist das Ergebnis unentschieden: welches Vorzeichen man berichtet, waehlt in diesem Lauf die Fill-Annahme und nicht die Daten.

Weitere Grenzen: mark-to-mid ohne Aufloesungs-Modellierung, Quotes nur bei Mid in (0.05, 0.95) und Spread bis 0.10, keine Queue-Position, keine Teilfills. Paper-only, keine Handelsempfehlung.