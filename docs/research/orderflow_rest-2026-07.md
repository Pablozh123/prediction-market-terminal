# Order-Flow-Studie (rest-2026-07)

Quelle: data/microstructure (REST, 120s-Raster), 4489 Tokens, 370,423 Snapshots, 678,665 Tape-Prints, 11 Tage (2026-07-18 bis 2026-07-28).

Schwelle 0.65, Kostenmodell sports-Kategorie, Gebuehrenstand 2026-07-30. Kosten je Runde = Spread + zwei Taker-Gebuehren. Trefferquote bedingt auf Bewegung.

## Signal: imbalance

Beobachtungen 1,011,556 an 11 Tagen, davon bewegt 39.1%. Trefferquote 55.2% (Wilson-Untergrenze 55.0%).

| Horizont | Verzoegerung | n | Treffer | Brutto (Cents) | Spread (Cents) | Gebuehr (Cents) | Netto (Cents) | Kante erhalten |
|---|---|---|---|---|---|---|---|---|
| 300s | 0s | 205,835 | 55.5% | +0.086 | 0.938 | 1.646 | -2.498 | 100% |
| 300s | 120s | 204,191 | 53.7% | +0.030 | 0.918 | 1.645 | -2.533 | 35% |
| 900s | 0s | 201,430 | 56.8% | +0.130 | 0.920 | 1.649 | -2.439 | 100% |
| 900s | 120s | 200,099 | 55.6% | +0.080 | 0.903 | 1.649 | -2.473 | 62% |
| 900s | 300s | 200,001 | 53.8% | +0.043 | 0.904 | 1.648 | -2.509 | 33% |

Walk-forward: Train (fruehe Tage) netto -2.448 Cents, Test (spaete Tage) netto -2.546 Cents.
Block-Bootstrap-CI 95% auf Tagesebene fuer netto ohne Verzoegerung: (-2.591, -2.3561) Cents.

## Signal: flow

Beobachtungen 450,492 an 11 Tagen, davon bewegt 60.5%. Trefferquote 51.3% (Wilson-Untergrenze 51.1%).

| Horizont | Verzoegerung | n | Treffer | Brutto (Cents) | Spread (Cents) | Gebuehr (Cents) | Netto (Cents) | Kante erhalten |
|---|---|---|---|---|---|---|---|---|
| 300s | 0s | 93,868 | 51.7% | -0.002 | 1.025 | 1.849 | -2.875 | - |
| 300s | 120s | 93,344 | 51.1% | -0.003 | 1.024 | 1.841 | -2.868 | - |
| 900s | 0s | 88,126 | 51.5% | -0.052 | 0.992 | 1.866 | -2.910 | - |
| 900s | 120s | 87,711 | 51.3% | -0.054 | 0.990 | 1.862 | -2.907 | - |
| 900s | 300s | 87,443 | 50.9% | -0.035 | 0.997 | 1.851 | -2.883 | - |

Walk-forward: Train (fruehe Tage) netto -2.819 Cents, Test (spaete Tage) netto -3.001 Cents.
Block-Bootstrap-CI 95% auf Tagesebene fuer netto ohne Verzoegerung: (-3.063, -2.7353) Cents.

## Signal: combo

Beobachtungen 90,890 an 11 Tagen, davon bewegt 59.3%. Trefferquote 55.6% (Wilson-Untergrenze 55.2%).

| Horizont | Verzoegerung | n | Treffer | Brutto (Cents) | Spread (Cents) | Gebuehr (Cents) | Netto (Cents) | Kante erhalten |
|---|---|---|---|---|---|---|---|---|
| 300s | 0s | 18,891 | 56.6% | +0.211 | 0.991 | 1.823 | -2.603 | 100% |
| 300s | 120s | 18,797 | 54.0% | +0.019 | 0.959 | 1.817 | -2.756 | 9% |
| 900s | 0s | 17,793 | 57.7% | +0.276 | 0.954 | 1.837 | -2.515 | 100% |
| 900s | 120s | 17,717 | 56.2% | +0.111 | 0.921 | 1.834 | -2.645 | 40% |
| 900s | 300s | 17,692 | 53.4% | +0.073 | 0.928 | 1.825 | -2.680 | 27% |

Walk-forward: Train (fruehe Tage) netto -2.660 Cents, Test (spaete Tage) netto -2.609 Cents.
Block-Bootstrap-CI 95% auf Tagesebene fuer netto ohne Verzoegerung: (-2.74, -2.4125) Cents.

## Lesehilfe

Brutto ist die Mid-Bewegung in Signalrichtung. Netto zieht die volle Runde ab: einmal Spread kreuzen beim Entry, einmal beim Exit, plus zwei Taker-Gebuehren. Ein Signal mit hoher Trefferquote und negativem Netto ist richtig und trotzdem unhandelbar.

Die beiden Zahlen sind zugleich die Schranken der Ausfuehrungsart. Netto ist die untere Schranke (alles aggressiv genommen), brutto die obere (alles passiv gefuellt, auf Polymarket zahlen Maker keine Gebuehr). Liegt der Wert eines Signals nur zwischen diesen beiden Schranken, ist es kein Taker-Signal, sondern ein Grund, als Maker die Quotes zu verschieben. Die getrennten Spalten fuer Spread und Gebuehr zeigen, welcher der beiden Posten die Kante frisst.

Die Verzoegerungsspalte simuliert Reaktionszeit: das Signal feuert zu t, der Entry-Preis ist das Buch zu t plus Verzoegerung, der Exit bleibt bei t plus Horizont. Faellt die Kante schon bei kleinen Verzoegerungen stark, ist es ein Latenzrennen und kein Research-Edge.

Grenzen: das REST-Raster loest Verzoegerungen nur in 120-Sekunden-Schritten auf, kleinere Werte fallen deshalb auf denselben Snapshot und zeigen keinen Zerfall. Die Sekundenaufloesung liefert erst der Stream-Recorder. Der REST-Tape ist gepollt und kann Prints zwischen zwei Abrufen verpassen, was den Flow-Anteil unterschaetzt.

Read-only-Forschung, keine Handelsempfehlung.