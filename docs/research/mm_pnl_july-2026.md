# Paper-MM PnL-Zerlegung (july-2026)

Quelle: data/microstructure (REST, 120s-Raster), 4519 Tokens, 370,903 Snapshots, 679,209 Tape-Prints, 12 Tage (2026-07-18 bis 2026-07-30).

Quoting: halber Spread 0.01, gamma 0.08, Quote 50.0 USD, Inventar-Cap 250.0 USD. Maker-Oekonomie der Kategorie sports, Gebuehrenstand 2026-07-30.

| Posten | Touch-Modell (USD) | Tape-Modell (USD) |
|---|---|---|
| Fills | 32,553 | 13,341 |
| Spread-Ertrag | +43285.15 | +19781.63 |
| Markout 5min (Adverse Selektion) | -227282.81 | -48298.95 |
| spaeterer Drift (Inventar) | -14417.10 | -19037.24 |
| Maker-Rebate | +6117.93 | +2519.77 |
| mark-to-mid (Identitaet) | -198414.76 | -47554.56 |
| Summe | -192296.84 | -45034.79 |
| Spread-Ertrag je Fill (Cents) | +132.968 | +148.277 |
| Markout je Fill (Cents) | -698.193 | -362.034 |
| Ergebnis je Fill (Cents) | -590.719 | -337.567 |
| mittleres |Inventar| (USD) | 38.90 | 40.61 |
| max |Inventar| (USD) | 1449.18 | 1490.59 |

## touch-Fill-Modell

Block-Bootstrap-CI 95% auf Tagesebene fuer die Tagessumme: (-18924.1105, -12204.2181) USD.

| gamma | Fills | Spread-Ertrag | Markout | Summe | mittleres \|Inventar\| |
|---|---|---|---|---|---|
| 0.00 | 30,892 | +45432.21 | -223218.72 | -190712.65 | 82.91 |
| 0.04 | 31,823 | +44681.79 | -226771.05 | -190461.52 | 49.95 |
| 0.08 | 32,553 | +43285.15 | -227282.81 | -192296.84 | 38.90 |
| 0.16 | 33,044 | +40658.21 | -226046.65 | -198559.07 | 27.51 |
| 0.32 | 33,268 | +36720.50 | -224379.96 | -204416.14 | 20.82 |

Liquiditaets-Rewards: im Schnitt 99% der Quote-Zeit innerhalb der Reward-Spanne, 1450 Maerkte, Pool-Annahme 3.0 USD pro Markt und Tag (Median der 9,562 Maerkte mit Pool, Stand 2026-07-31).

| Konkurrenz (Vielfaches des eigenen Scores) | eigener Anteil | Reward (USD) | Summe inkl. Reward (USD) |
|---|---|---|---|
| 1x | 50.0% | +1298.62 | -190998.21 |
| 5x | 16.7% | +432.87 | -191863.96 |
| 20x | 4.8% | +123.68 | -192173.16 |

| Quoting-Modus | Fills | Spread-Ertrag je Fill (c) | Markout je Fill (c) | Summe (USD) | CI95 Tagessumme |
|---|---|---|---|---|---|
| symmetric | 32,553 | +132.97 | -698.19 | -192296.84 | (-18924.1105, -12204.2181) |
| signal | 25,623 | +130.90 | -698.99 | -157584.65 | (-15738.2326, -9919.8139) |
| lean | 29,623 | +132.33 | -701.82 | -177399.84 | (-17427.9135, -11310.4551) |

| halber Spread | Fills | Spread-Ertrag | Markout | Ertrag/Markout | Summe |
|---|---|---|---|---|---|
| 0.005 | 42,126 | +27450.11 | -242696.48 | 0.11 | -238301.36 |
| 0.010 | 32,553 | +43285.15 | -227282.81 | 0.19 | -192296.84 |
| 0.020 | 23,349 | +62329.76 | -198591.80 | 0.31 | -140942.45 |
| 0.040 | 13,671 | +71065.44 | -149900.74 | 0.47 | -81478.79 |
| 0.080 | 6,116 | +61961.24 | -90962.55 | 0.68 | -40859.12 |

Walk-forward: auf den fruehen Tagen gewaehltes gamma 0.0; auf den spaeten Tagen ergibt es -71532.83 USD gegen -71532.83 USD ohne Skew (gamma 0).

## tape-Fill-Modell

Block-Bootstrap-CI 95% auf Tagesebene fuer die Tagessumme: (-4999.2322, -2439.3496) USD.

| gamma | Fills | Spread-Ertrag | Markout | Summe | mittleres \|Inventar\| |
|---|---|---|---|---|---|
| 0.00 | 11,994 | +19614.86 | -48271.77 | -45973.29 | 93.86 |
| 0.04 | 12,884 | +20033.16 | -48557.12 | -45506.75 | 53.61 |
| 0.08 | 13,341 | +19781.63 | -48298.95 | -45034.79 | 40.61 |
| 0.16 | 13,569 | +19050.57 | -48476.76 | -43150.87 | 28.95 |
| 0.32 | 13,538 | +17800.64 | -45943.59 | -40619.01 | 21.42 |

Liquiditaets-Rewards: im Schnitt 99% der Quote-Zeit innerhalb der Reward-Spanne, 1450 Maerkte, Pool-Annahme 3.0 USD pro Markt und Tag (Median der 9,562 Maerkte mit Pool, Stand 2026-07-31).

| Konkurrenz (Vielfaches des eigenen Scores) | eigener Anteil | Reward (USD) | Summe inkl. Reward (USD) |
|---|---|---|---|
| 1x | 50.0% | +1298.62 | -43736.16 |
| 5x | 16.7% | +432.87 | -44601.91 |
| 20x | 4.8% | +123.68 | -44911.11 |

| Quoting-Modus | Fills | Spread-Ertrag je Fill (c) | Markout je Fill (c) | Summe (USD) | CI95 Tagessumme |
|---|---|---|---|---|---|
| symmetric | 13,341 | +148.28 | -362.03 | -45034.79 | (-4999.2322, -2439.3496) |
| signal | 10,378 | +145.41 | -365.47 | -41326.72 | (-4540.5633, -2258.1129) |
| lean | 12,103 | +146.14 | -364.33 | -41072.40 | (-4628.5566, -2142.5131) |

| halber Spread | Fills | Spread-Ertrag | Markout | Ertrag/Markout | Summe |
|---|---|---|---|---|---|
| 0.005 | 20,012 | +15591.61 | -49164.90 | 0.32 | -49201.72 |
| 0.010 | 13,341 | +19781.63 | -48298.95 | 0.41 | -45034.79 |
| 0.020 | 8,341 | +23997.20 | -42326.33 | 0.57 | -28373.02 |
| 0.040 | 4,672 | +27140.99 | -31683.93 | 0.86 | -8458.39 |
| 0.080 | 1,971 | +21408.35 | -20350.46 | 1.05 | -5187.05 |

Walk-forward: auf den fruehen Tagen gewaehltes gamma 0.32; auf den spaeten Tagen ergibt es -16398.95 USD gegen -16403.21 USD ohne Skew (gamma 0).

## Lesehilfe

Die drei Preisposten sind keine Schaetzung, sondern eine Identitaet: Spread-Ertrag plus Markout plus spaeterer Drift ergibt exakt den mark-to-mid Endwert je Fill. Der Spread-Ertrag ist, was das Quoting verdient hat, der Markout ist, was informierte Gegenparteien davon zurueckgeholt haben, der spaetere Drift ist der Preis des getragenen Inventars.

Die beiden Fill-Modelle klammern die Wahrheit ein. Touch fuellt nur, wenn die Gegenseite unsere Quote kreuzt, ignoriert also Fills am Touch und unterschaetzt die Fill-Zahl. Tape fuellt bei jedem kreuzenden Print, unterstellt also Queue-Prioritaet und ueberschaetzt sie. Wer nur ein Modell rechnet, waehlt sein Ergebnis mit der Annahme.

Die Spalte Ertrag/Markout in der Breiten-Tabelle ist die Break-even-Kennzahl: unter 1 frisst die Adverse Selektion mehr, als das Quoting einnimmt. Sie steigt mit der Quote-Breite, weil der Spread-Ertrag mit der Breite waechst, die Gegenbewegung aber von der Marktbewegung bestimmt wird und nicht von unserer Quote. Wo die Kennzahl 1 kreuzt, brechen zugleich die Fills ein - eine so breite Quote steht am Markt vorbei.

Maker zahlen auf Polymarket keine Gebuehr und bekommen einen Anteil der eingesammelten Taker-Gebuehren zurueck. Der Rebate ist hier die Obergrenze dieses Anteils, die tatsaechliche Tagesverteilung kann niedriger ausfallen.

Die Liquiditaets-Rewards sind der dritte Ertragsposten und der einzige, der nicht davon abhaengt, ob ein Fill zustande kommt: bezahlt wird Praesenz nahe am Mid. Der eigene Anteil laesst sich nicht berechnen, weil er von allen anderen Makern im selben Markt abhaengt, deshalb steht dort eine Spanne statt einer Zahl. Die Pool-Annahme ist der Median ueber alle Maerkte mit Pool und damit bewusst konservativ: die Verteilung ist stark rechtsschief, der groesste Pool liegt bei 1000 USD pro Tag gegen einen Median von 3. Der Hebel bei dieser Ertragsquelle ist deshalb die Marktauswahl, nicht das engere Quoten - eine Aussage, die diese Rechnung nahelegt und nicht belegt, weil hier nicht nach Pool-Groesse ausgewaehlt wurde.

Wichtigste Einschraenkung, und zugleich der eigentliche Befund: das 120-Sekunden-Raster bedeutet, dass jede Quote zwei Minuten unveraendert im Buch steht. Genau diese Standzeit ist die gemessene Adverse Selektion - gefuellt wird man bevorzugt dann, wenn der Markt an der veralteten Quote vorbeigelaufen ist. Ein echter Market Maker requotet im Millisekundenbereich. Diese Zahlen messen deshalb nicht, ob Market Making auf Polymarket funktioniert, sondern was passiert, wenn man zwei Minuten lang nicht nachzieht.

Weitere Grenzen: mark-to-mid ohne Aufloesungs-Modellierung, Quotes nur bei Mid in (0.05, 0.95) und Spread bis 0.10, keine Queue-Position, keine Teilfills. Paper-only, keine Handelsempfehlung.