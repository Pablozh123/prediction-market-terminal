# CEX-Parametersuche vom 11.10.2026

## Auftrag und festgelegtes Vorgehen

Impulsgrenze, Messfenster, Haltedauer und beide Kauflimits auf den vorhandenen
Aufzeichnungen variieren und Ergebnisse nach Gebühren berichten. Bestehendes
Replay, 10 Anteile, 100 USD je unabhängiger Variante, 5 Sekunden Signalpause
und 2 Sekunden Frischegrenze bleiben erhalten. Laufzeitmodule und laufende
Datensammlung werden nicht verändert.

1. Den vollständigen Stundenlauf vom 09.10.2026 zur Parametersuche verwenden.
   Raster: 0.5/1/2/3 bp Impuls, 0.5/1/2 Sekunden Messfenster, 1/2/5/10/20
   Sekunden Haltedauer, 0.65/0.85/0.95 USD absolutes Kauflimit und
   0.01/0.02/0.05 USD erlaubter Anstieg gegenüber dem Ask beim Signal.
   Das sind 540 Kombinationen. Hauptvergleich bei 250 ms angenommener
   Einstiegsverzögerung. Werte und Ranking stehen vor Ergebnisberechnung fest.
2. Für wiederholtes Replay nur die benötigten Orderbuchzustände verdichten.
   Originalzeitpunkte, Reihenfolge gleicher Zeitpunkte, Tiefe für 10 Anteile,
   Gebühren, Frische und echte Verbindungsresets müssen identisch bleiben.
   Zuerst synthetische Paritätstests, dann Abgleich aller vier Baseline-Arme
   mit dem Originalarchiv. Kursreaktionsstatistiken werden aus verdichteten
   Ereignissen nicht übernommen.
3. Höchstens zehn Varianten mit mindestens zehn geschlossenen Trades nach
   vorsichtigem Kapitalergebnis auswählen: Kassenbestand minus Startkapital,
   also alle unaufgelösten Positionen mit Wert null. Baseline zusätzlich
   mitnehmen. Auswahl einfrieren, bevor spätere Daten ausgewertet werden.
4. Ausgewählte Varianten bei 100/250/500/1’000 ms erneut prüfen, auf dem
   Auswahlfenster und zeitlich späteren Daten vom 11.10.2026. Ein noch laufender
   Lauf darf nur als feste Momentaufnahme mit Bytegrenze, Prüfsumme und
   ausdrücklichem Zwischenstatus verwendet werden. Keine Vermischung mit
   abgeschlossenen Läufen. Jeder Lauf startet unabhängig mit 100 USD.
5. Vollständige Rastertabelle, ausgewählte Varianten, Quellen und Prüfergebnisse
   speichern und auf Deutsch berichten. Mehrfachsuche und kleine Stichprobe
   begrenzen die Aussagekraft. Bereits bekannte historische Daten sind kein
   vollständig unberührter Zukunftstest.

## Ergebnisse

Berechnet: 540 Kombinationen bei 250 ms auf dem früheren Stundenlauf. Zehn
Varianten mit mindestens zehn geschlossenen Trades wurden nach Kassenbestand
minus Startkapital ausgewählt. Die Baseline kam zusätzlich dazu. Diese elf
Varianten wurden bei 100/250/500/1’000 ms auf allen drei Zeitfenstern geprüft.
Die Auswahl wurde am 11.10.2026 um 12:46:15 Uhr Zürich eingefroren.

Anschliessend wurde das volle Raster zusätzlich auf dem vollständigen
späteren Stundenlauf berechnet. Diese Zusatzsuche ist explorativ und kein
weiterer unabhängiger Test. Sie verändert die zuvor eingefrorene Auswahl nicht.

| Datenfenster | Zeitpunkt Zürich | Dauer | Status |
|---|---|---:|---|
| Auswahl | 09.10., 19:30:58 bis 20:30:58 | 60 min | abgeschlossen |
| Spätere Prüfung 1 | 11.10., 11:48:06 bis 11:55:06 | 7 min | abgeschlossen |
| Spätere Prüfung 2 | 11.10., 11:56:43 bis 12:56:42 | 60 min | abgeschlossen und vollständig geprüft |

### Drei interessante Varianten

| Variante | Impuls | Messfenster | Haltedauer | Preisobergrenze | Ask-Anstieg |
|---|---:|---:|---:|---:|---:|
| A, beste Auswahl bei mindestens 10 geschlossenen Trades | 0.02 % | 0.5 s | 20 s | 0.65 USD | 0.02 USD |
| B, niedrigere Impulsgrenze, in eingefrorener Top-10-Auswahl | 0.01 % | 0.5 s | 5 s | 0.65 USD | 0.05 USD |
| Bisherige Baseline | 0.02 % | 1 s | 5 s | 0.85 USD | 0.02 USD |

Ergebnisse bei 250 ms: **realisierter Nettogewinn USD / geschlossene Trades / offene Positionen**.

| Variante | Früher 60 min | Später 7 min | Später 60 min |
|---|---:|---:|---:|
| A | +12.64 / 11 / 0 | 0.00 / 0 / 0 | 0.00 / 0 / 0 |
| B | +14.05 / 60 / 2 | +6.36 / 2 / 0 | 0.00 / 0 / 0 |
| Baseline | +6.33 / 17 / 2 | 0.00 / 0 / 0 | -0.72 / 1 / 0 |

A zahlte im Auswahlfenster 3.05873 USD Gebühren. B zahlte 17.95710 USD und
hatte zwei offene Positionen mit 3.15484 USD Einsatz. Sein vorsichtiges
Kapitalergebnis betrug deshalb +10.89106 USD statt +14.04590 USD realisiert.
Die Baseline lag bei +3.17673 USD vorsichtigem Kapitalergebnis.

Die zwei späteren Trades von B stammen aus **einem einzigen CEX-Impuls**,
der zwei Märkte betraf. Der Gewinn von +6.35981 USD nach 0.54019 USD Gebühren
wurde mit den vollständigen Originalereignissen erneut nachgerechnet. Dies
ist eine kleine, korrelierte Stichprobe und kein Nachweis dauerhafter Profitabilität.

### Empfindlichkeit gegenüber Verzögerung

Alle Werte netto nach Gebühren. Offene Positionen nicht zum realisierten Gewinn addiert.

| Verzögerung | A, Auswahl 60 min | B, Auswahl 60 min | B, spätere 7 min | B, spätere 60 min |
|---|---:|---:|---:|---:|
| 100 ms | +12.28 | +22.46 | +6.57 | +0.65 |
| 250 ms | +12.64 | +14.05 | +6.36 | 0.00 |
| 500 ms | +9.04 | +9.17 | 0.00 | 0.00 |
| 1000 ms | +0.61 | -3.51 | 0.00 | 0.00 |

Bei 500 und 1’000 ms gab es für B in beiden späteren Fenstern keine
Ausführungen. Es zählt der Preis bei angenommener Ankunft, einschliesslich
der absoluten Preisobergrenze. Schnellere Varianten handeln teilweise
andere Trades; der Gewinn muss deshalb nicht monoton mit der Latenz steigen.

### Kontrollierter Vergleich von Impuls und Haltedauer

In der Grafik sind Messfenster, Kauflimits, Stückzahl und Verzögerung fest.
Sie zeigt realisierte Gewinne und die Anzahl geschlossener sowie offener
Positionen. Offene Positionen sind weiterhin unbewertet.

![Kontrollierter Parametervergleich](../../outputs/cex_parameter_sweep/20261011/parametervergleich.png)

Ein Beispiel für die Bedeutung offener Positionen: Bei 0.005 % Impuls,
1 Sekunde Messfenster, 5 Sekunden Haltedauer und ursprünglichen Kauflimits
ergaben sich früher +2.77797 USD realisiert. Einschliesslich des vollständigen
Verlusts aller offenen Einsätze wäre das Kapitalergebnis aber −11.31232 USD.
Eine niedrigere Signalgrenze erzeugt daher nicht automatisch bessere Ergebnisse.

### Volles Raster auf der späteren Stundenaufzeichnung

35 von 540 Varianten hatten ein positives vorsichtiges Kapitalergebnis, 285 ein negatives; 220 hatten keine Trades. Viele Varianten nutzen dieselben Fills.

Das nachträglich beste Ergebnis betrug +0.73 USD aus 2 geschlossenen Trades, nach 0.32640 USD Gebühren; 0 Positionen offen. Parameter: 0.01 % über 0.5 Sekunden, 10 Sekunden Haltedauer, maximal 0.95 USD und Ask +0.01 USD. Dies ist eine weitere explorative Suche und keine unabhängig bestätigte Strategie.

### Prüfung und Grenzen

- 155 passende Tests und Ruff projektweit bestanden.
- Vier Baseline-Arme und eine alternative Parameterkombination stimmten
  exakt mit dem vollständigen Replay überein, einschliesslich Signalmerkmalen,
  Tiefe, Gebühren, Frische, Positionen und Kapitalständen.
- Zwei zusätzliche spätere positive Ergebnisse wurden mit vollständigen
  Originalereignissen und geprüften Präfixprüfsummen nachgerechnet.
- Die Handels- und Recorder-Module blieben unverändert. Keine echten Orders
  oder kostenpflichtigen AI-Aufrufe.
- Das alte Auswahlfenster hat die bereits dokumentierten Empfangslücken.
  Der spätere Stundenlauf ist inzwischen abgeschlossen: kein erkannter
  Datenverlust, keine Verbindungsfehler, zwölf Marktwechsel ohne Neustart,
  vollständige Snapshots, Queue-Maximum 811 von 100’000.
- Sichtbare Liquidität ist eine optimistische Fill-Annahme. Verzögerungen
  sind simuliert, keine gemessenen Orderzeiten.
- Die Messfenster sind Sollwerte. Die bestehende Regel nimmt den letzten
  CEX-Tick vor dem Zielzeitpunkt und erlaubt dort bis zu zwei Sekunden
  zusätzlichen Abstand. Bei seltenen Trades kann die tatsächlich verglichene
  Zeitspanne deshalb länger sein. Diese bestehende Regel blieb unverändert.
- Bei 540 Versuchen kann ein guter historischer Treffer zufällig entstehen.
  Bereits bekannte historische Daten sind kein unberührter Zukunftstest.
- 20 Sekunden Haltedauer können fortgesetzte Kursbewegungen einfangen.
  Das Ergebnis beweist keine reine Ausnutzung einer Preisverzögerung.

### Reproduktion und Dateien

```powershell
python -X utf8 -m scripts.cex_parameter_sweep
$env:PYTHONPATH = (Get-Location).Path
python -X utf8 outputs/cex_parameter_sweep/20261011/extend_validation_grid.py
python -X utf8 outputs/cex_parameter_sweep/20261011/audit_later.py
python -X utf8 outputs/cex_parameter_sweep/20261011/report_results.py
python -m unittest tests.test_cex_parameter_sweep tests.test_cex_leadlag
python -m ruff check .
```

Ein erneuter Hauptlauf friert für ein laufendes Archiv einen neuen Präfix ein.
Die hier ausgewerteten Bytegrenzen, Prüfsummen und Zeitpunkte stehen in den
JSON-Dateien. Originalarchive und bestehende Standardberichte bleiben erhalten.

Unter `outputs/cex_parameter_sweep/20261011/`: `grid_spec.json`,
`grid_results.csv`, `later_grid_results.csv`, `selected.json`, `comparison.json`,
`later_audit.json`, `quality_summary.json` sowie die Grafik.

Nächster offener Schritt: A und B mit bereits eingefrorenen Parametern auf
weiteren abgeschlossenen Stundenfenstern prüfen. Keine automatische Übernahme
in einen echten Orderpfad oder Änderung der laufenden Basisregel.
Die ursprüngliche 50-Minuten-Momentaufnahme und ihre Zusatzsuche bleiben unter `comparison.json` und `later_grid_results.csv` erhalten. Der Abschlussvergleich verwendet `completed_hour.json` und `completed_hour_grid.csv`. Dessen Auswahl blieb unverändert eingefroren. Alle vier Baseline-Arme und eine alternative Parameterkombination wurden auf dem vollständigen späteren Stundenlauf nochmals auf Parität geprüft.

Zusätzlicher Reproduktionsschritt vor diesem Bericht:

```powershell
python -X utf8 outputs/cex_parameter_sweep/20261011/completed_hour.py
```

