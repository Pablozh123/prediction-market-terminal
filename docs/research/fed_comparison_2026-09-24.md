# Fed-Vergleich: gespeicherte Untersuchung vom 24. September 2026

Polymarket-Preise und CME FedWatch, abgeleitet aus Fed-Funds-Futures.
Fünf vergangene Meetings mit beiden historischen Quellen erfasst.
März: 18 FedWatch-Tabellen aus dem SinoPac-Brokerarchiv, auf 0.1 Prozentpunkte
gerundet. April bis September: originale CME-CSV-Exporte.

## Gepaarter Prognosefehler

Multiclass Brier, kleiner ist besser. Identische Meetings und Tagesstichtage pro Quellenvergleich.

| Horizont | n Meetings | Polymarket | CME FedWatch |
|---|---:|---:|---:|
| T−30 | 5 | 0.240700 | 0.216928 |
| T−7 | 5 | 0.095611 | 0.092488 |
| T−1 | 5 | 0.036718 | 0.054560 |

CME liegt in dieser kleinen Stichprobe bei T−30 und T−7 näher am Ergebnis;
Polymarket bei T−1. Das ist ein deskriptiver Befund, kein belastbarer
Kalibrierungsnachweis oder Nachweis einer profitablen Strategie.

## Einzelmeetings am letzten gemeinsamen Tagesstichtag

Gezeigt wird jeweils das tatsächlich eingetretene Outcome. Die Preise sind
hier unnormalisiert, also dieselben Werte wie in der historischen Kurve.

| Meeting | Outcome | Tagesstichtag UTC | Polymarket | CME | Differenz pp |
|---|---|---|---:|---:|---:|
| 2026-03-18 | +0 bp | 2026-03-18T04:59:59+00:00 | 99.45% | 99.10% | +0.35 |
| 2026-04-29 | +0 bp | 2026-04-29T04:59:59+00:00 | 99.75% | 100.00% | -0.25 |
| 2026-06-17 | +0 bp | 2026-06-17T04:59:59+00:00 | 99.65% | 99.45% | +0.20 |
| 2026-07-29 | +0 bp | 2026-07-29T04:59:59+00:00 | 75.45% | 69.00% | +6.45 |
| 2026-09-16 | +25 bp | 2026-09-16T04:59:59+00:00 | 87.50% | 93.50% | -6.00 |

## Reproduktion und Grenzen

- `python scripts/collect_fed_comparison.py`: öffentliche Quellen erneut abrufen.
- `python scripts/collect_fed_comparison.py --offline`: aus den Rohdateien neu rechnen.
- `python scripts/import_fedwatch_archive.py`: März-Archiv rekonstruieren (Analyseumgebung mit `pdfplumber`).
- `--cme-dir PFAD`: Originaldateien `cme_YYYY-MM-DD.csv` importieren.
- Rohdateien: `data/fed_comparison/raw/`, einschliesslich fünf Fed-Mitteilungen.
- SHA-256 und Abrufzeit je Datei: `data/fed_comparison/raw/manifest.json`.
- Publizierter Datensatz: `public/data/fed_comparison.json`.
- UI: `http://localhost:8787/#fed`.

CME-Tagesstichtag ist konservativ 23:59:59 America/Chicago, kein bekannter
Intraday-Tick. Für März wird konservativ das Ende des Berichtstags verwendet,
kein CME-Schlusskurs. Archivbeobachtungen können untertägig früher entstanden
sein; die März-Scores sind deshalb zusätzlich von dieser Zeitkonvention und
der Rundung abhängig. Die Lücke während der taiwanischen Februarfeiertage
wird nicht gefüllt. Meeting-Tagesendwerte sind ausgeschlossen. Polymarket wird
rückwärts zum selben Stichtag gelesen, maximal 2 Stunden alt. Ein Horizont
verwendet das jüngste vollständige Paar davor, maximal 96 Stunden alt.
Brier-Scores verwenden vollständige auf 1 normierte Polymarket-Vektoren;
Preisdifferenzen verwenden rohe Preise. Fehlende Daten werden nicht ergänzt.

Oktober ist nach der September-Entscheidung vergleichbar. Für Dezember
ist der vorherige Oktober-Entscheid noch offen. Deshalb bleibt dessen
CME-Outcome-Zuordnung gesperrt, obwohl die rohe CME-Datei archiviert ist.
Der geprüfte Meeting-Katalog reicht bis Dezember 2026. Das ist ein gespeicherter
Abruf, kein laufender Recorder; neue Meetings/Entscheide müssen verifiziert werden.

Polymarket-Binärkontrakte und Futures auf den Monatsdurchschnitt besitzen
unterschiedliche Auszahlungen. Ein positiver Spread ist daher kein Nachweis
ausführbarer Arbitrage. Fees, Bid/Ask, Tiefe, Finanzierung und Basisrisiko sind
nicht als Handelsgewinn modelliert.

## Quellen

- [SinoPac FedWatch-Archiv](https://www.spf.com.tw/sinopacSPF/research/list.do?id=18d5d32463100000a0821ca2135dcd5d)

- [Federal Reserve Kalender](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm)
- [September-Entscheid](https://www.federalreserve.gov/newsevents/pressreleases/monetary20260916a.htm)
- [CME FedWatch und Downloads](https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html)
- [CME Methodik](https://www.cmegroup.com/articles/2023/understanding-the-cme-group-fedwatch-tool-methodology.html)
- [Polymarket September](https://polymarket.com/event/fed-decision-in-september-762)

Die genaue Herkunft jeder Originaldatei steht im Manifest und im JSON-Datensatz.
