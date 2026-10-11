# BTC: CEX-Vorlauf und Polymarket-Reaktion

Stand: 11.10.2026. Lokaler Paper-Test mit öffentlichen Daten.

[Kurze Erklärung mit Ablaufgrafik und Parametern](cex_leadlag_kurz.md).

## Start und gespeicherte Ergebnisse

Im Projektordner mit der vorhandenen Python-Umgebung starten:

```powershell
python -m src.cex_leadlag record --duration 900
```

Der Recorder erfasst Binance BTC/USDT, Coinbase BTC/USD und die vollständige
Orderbuchtiefe der Polymarket-BTC-Märkte mit 5 und 15 Minuten Laufzeit. Er lädt
den aktuellen und den nächsten Kontrakt, aktualisiert die Auswahl jede Minute
innerhalb der bestehenden Verbindung und verbindet sich nach Ausfällen erneut.
Metadatenabfragen laufen unabhängig vom Empfang. Die Aufzeichnung dauert 1 bis 3’600
Sekunden. Ctrl+C beendet sie geordnet und wertet den vorhandenen Teil aus.
Für diese öffentlichen Daten ist kein API-Key nötig.

Jeder Lauf erhält einen eigenen Ordner unter `data/cex_leadlag/`:

- `events.jsonl`: validierte Preis- und Orderbuchmeldungen, Marktregeln,
  Gebühren, Abonnementwechsel, Ping-Antwortzeiten und Verbindungszustände.
  Schliessungscode und Grund werden bei einem Server-Schliessungsframe erfasst.
  Lokale Empfangszeit, monotone Zeit und
  verfügbare Börsenzeitstempel werden getrennt gespeichert.
- `manifest.json`: Datenquellen, Dauer, Fehler, Ereigniszähler, höchste beobachtete
  Belegung der 100’000 Plätze umfassenden Datenwarteschlange und SHA-256
  des Datenarchivs. Die aufgezeichneten Daten bleiben lokal und sind gitignoriert.
- `report.md` und `report.json`: Parameter, Prüfsummen der Implementierung,
  Ergebnisse je Verzögerung, Kursreaktionen, Gebühren und offene Positionen.
- `report_trades.csv`: einzelne simulierte Ein- und Ausstiege.
- `decision_inputs.jsonl`: eingefrorene Eingabedaten zum Signalzeitpunkt.
  Spätere Kurse und Handelsergebnisse sind darin nicht enthalten.

Eine vorhandene Aufzeichnung erneut auswerten:

```powershell
python -m src.cex_leadlag replay --run data/cex_leadlag/<laufordner>
python -m src.cex_leadlag replay --run data/cex_leadlag/<laufordner> --signal-source coinbase
```

Ein Replay ersetzt die Berichte und AI-Eingabedaten dieses Laufordners. Das
Datenarchiv bleibt erhalten. Vor explorativen Parameteränderungen den Bericht
der ursprünglichen Konfiguration separat sichern. Technische Feldnamen und
Befehle bleiben stabil; die Erläuterungen und erzeugten Berichte sind Deutsch.
SQLite sortiert die Ereignisse temporär auf dem Datenträger, damit nicht das
gesamte Orderbucharchiv im Arbeitsspeicher liegen muss.

## Was die Basisregel prüft

Ein BTC-Impuls von mindestens 2 Basispunkten innerhalb der vergangenen
1’000 ms löst ein Signal aus. Ein positiver Binance-Impuls kauft Up, ein
negativer kauft Down. Nach 5’000 ms wird ein Verkauf versucht. Coinbase-Renditen
werden separat als mögliche Bestätigung erfasst. Absolute USD- und
USDT-Preisniveaus werden nicht gleichgesetzt.

Beim Signal muss der Markt bereits handeln, genügend Restlaufzeit haben und
ein frisches, ungekreuztes Orderbuch mit bekannten Gebühren besitzen. Pro
Markt gilt eine Signalpause von 5’000 ms. Vier getrennte Simulationsläufe
verwenden 100, 250, 500 und 1’000 ms Ausführungsverzögerung. Jeder startet mit
100 USD Paper-Kapital, handelt 10 Anteile und hält höchstens eine Position
pro Markt. Der Kaufpreis darf weder 0.85 noch den Ask beim Signal plus 0.02
überschreiten. `--help` zeigt die veränderbaren Parameter.

Der Simulator kauft aus der zum Ausführungszeitpunkt bekannten Ask-Tiefe und
verkauft in die bekannte Bid-Tiefe. Die gesamte Menge muss verfügbar sein.
Er verwendet die dann bekannte Gebührenmetadaten-Version des Marktes.
Für unterstützte Gebühren mit Exponent 1 gilt je verbrauchter Preisstufe:

```text
Gebühr = Anteile × Gebührensatz × Preis × (1 − Preis)
```

Die aufsummierte Gebühr wird auf fünf Dezimalstellen gerundet. Unbekannte
Gebühren verhindern die Ausführung. Maker- und Volumenrabatte werden nicht
angenommen. Gebühren fallen bei Kauf und Verkauf an.

Das Replay verwendet ausschliesslich bereits empfangene Beobachtungen.
Es ersetzt einen fehlenden Kurs nie durch den ersten späteren Kurs. Bei
identischem Zeitstempel zählen die Meldungen in Aufzeichnungsreihenfolge vor
der Ausführung. Synchronisierte Börsenuhren werden nicht vorausgesetzt.
Orderbücher über zwei Sekunden Alter werden verworfen. Eine unterbrochene
Verbindung macht die Bücher ungültig; neue Deltas genügen ohne vollständigen
Snapshot nicht. Datenverlust in der Warteschlange macht den Lauf unbrauchbar.
Vor dem Replay muss die Archivprüfsumme stimmen.

Fehlt beim Ausstieg ein ausreichendes Buch, bleibt die Position unbewertet
offen und bindet Kapital. Das realisierte Ergebnis schliesst sie aus. Deshalb
Gewinn immer zusammen mit offenen Positionen und deren ursprünglichem Einsatz
lesen. CEX-Kurse werden nicht als Ersatz für die offizielle Auflösung verwendet.

Pro Kandidat wird ausserdem der erste Ask-Anstieg um mindestens einen Cent
innerhalb der Haltedauer gemessen. Verbindungsabbrüche und ein vorzeitiges
Aufzeichnungsende kennzeichnen unvollständig beobachtete Fälle. Der Median
bezieht sich nur auf tatsächlich beobachtete Reaktionen. Eine solche Reaktion
nach dem Signal beweist weder Kausalität noch, dass Polymarket während des
vorangehenden CEX-Impulses noch nicht reagiert hatte.

## Grenzen der Aussage

Dieser Test prüft Wiederverkauf nach einer möglichen Kursanpassung. Ein
BTC-Impuls liefert keine direkt beobachtete Gewinnwahrscheinlichkeit von
85 %. Die aufgezeichneten Kontrakte verweisen auf Chainlink-BTC/USD-TWAP-Regeln.
Binance und Coinbase werden nicht als identische Auflösungsquelle behandelt.
Ein kalibriertes Wahrscheinlichkeitsmodell bis zur Auflösung benötigt die
exakte Referenzreihe, die Definition des Startwerts, Restlaufzeit,
Volatilitätsmerkmale und unabhängig ermittelte Ergebnisse. Dieses Modell und
ein Halten bis zur Auflösung sind bisher nicht implementiert.

Sichtbare Liquidität ist eine optimistische Fill-Annahme. Eine echte Order
kann später ankommen, den Wettlauf um den Kurs verlieren oder abgelehnt werden.
Eigener Markteinfluss, zusätzliche Infrastrukturprobleme und eine CEX-Absicherung
werden nicht simuliert. Ein kurzer positiver Lauf belegt keinen belastbaren
Handelsvorteil. Parameter werden auf älteren Daten gewählt und für spätere
Aufzeichnungen eingefroren. Die günstigste Schwelle oder Verzögerung nach
Betrachtung der Ergebnisse auszuwählen wäre keine unabhängige Validierung.

## Wie es weitergeht

1. **Zunächst Datenqualität prüfen:** Einen Lauf von 15 Minuten mit unveränderten
   Standardparametern aufnehmen. Prüfen, ob Marktwechsel funktionieren, alle
   Datenquellen liefern und offene Ausstiege oder Verbindungsabbrüche die
   Auswertung beeinflussen. Die ersten fünf Minuten dienen als Pilotdatensatz,
   nicht als unabhängiger Leistungsnachweis.
2. **Auf neuen Zeitfenstern validieren:** Mehrere getrennte Aufzeichnungen zu
   unterschiedlichen Zeiten sammeln. Die Parameter vorher festlegen und nicht
   nach jedem Ergebnis optimieren. Gebühren, Ablehnungen, offene Positionen
   und jede Verzögerung separat ausweisen. 5- und 15-Minuten-Märkte sowie
   überlappende Signale hängen am selben BTC-Kurs und sind keine unabhängigen
   Stichproben. Eine spätere Unsicherheitsanalyse muss zusammenhängende
   Zeitblöcke gemeinsam behandeln.
3. **Die 85-%-Behauptung gesondert modellieren:** Die genaue offizielle
   Referenzreihe und Marktregeln beschaffen, Startwert und verbleibende Zeit
   rekonstruieren und ein einfaches numerisches Wahrscheinlichkeitsmodell
   aufbauen. Erst auf späteren, unangetasteten Daten mit Auflösungsergebnissen
   und Kalibrierung prüfen. Für einen Kauf bis zur Auflösung muss die geschätzte
   Auszahlung den Ask, die Kaufgebühr und eine Modellreserve übersteigen.
   Für einen Wiederverkauf zählt dagegen der erwartete spätere Verkaufserlös
   nach Kosten. Das sind unterschiedliche Testziele.
4. **Jev erst gegen die numerische Basis vergleichen:** Derselbe Kandidatensatz,
   dieselben Risikogrenzen, tatsächliche Antwortzeit und API-Kosten. Ein
   Vorteil muss auf neuen Daten bestehen bleiben. Hohe Modellkonfidenz allein
   genügt nicht.

Punkt 1 wurde mit dem unten dokumentierten 15-Minuten-Lauf abgeschlossen.
Vor längeren Wiederholungen sind die beobachteten Verbindungsabbrüche und die
tatsächliche Ausführungslatenz zu untersuchen. Eine Entscheidung über echte
Orders ist damit nicht getroffen.
Der fünfminütige Pilot erzeugte rund 134 MB Daten; längere Läufe benötigen
entsprechend Speicher. Eine dauerhaft laufende Aufzeichnung ist nicht eingerichtet.

## Optionaler Vergleich mit Jev

Einschätzung: Preisrechnung, Kosten und Ausführung bleiben deterministisch.
Jev lässt sich als Auswahlfilter prüfen, etwa bei widersprüchlichen Signalen
zwischen Börsen. Seine Auswahlwahrscheinlichkeiten sind keine kalibrierten
Gewinnwahrscheinlichkeiten für diesen BTC-Handel. TypeSafe dokumentiert selbst
Grenzen bei numerischer Präzision, der Reihenfolge von Antwortoptionen und
gezielt irreführenden Eingaben.

Der Adapter sendet ausschliesslich freigegebene numerische Merkmale und die
im Code ermittelte Übereinstimmung der Börsensignale. Markttexte, Wallet-Daten,
künftige Renditen und Ergebnisse werden nicht übertragen. Zeitüberschreitung
oder ungültige Antworten führen zur Enthaltung. Tatsächliches Modell,
Tokenverbrauch und Antwortzeit werden protokolliert. Die gemessene AI-Latenz
kommt zur simulierten Handelsverzögerung hinzu. Dies bleibt ein nachträglicher
Vergleich auf eingefrorenen Daten, kein echter Ausführungstest mit AI.

Mit `TYPESAFE_API_KEY` in der Umgebung lassen sich explizit bis zu 20
kostenpflichtige Bewertungen auslösen:

```powershell
python -m src.cex_leadlag score --run data/cex_leadlag/<laufordner> --max-calls 20 --model jev-latest
python -m src.cex_leadlag replay --run data/cex_leadlag/<laufordner> --decisions data/cex_leadlag/<laufordner>/decisions.jsonl
```

Dieselben Replay-Parameter verwenden wie bei der Erzeugung der Eingabedaten.
Bei geänderten Merkmalen enthält sich der Filter. Bereits gespeicherte
Bewertungen desselben Datensatzes werden wiederverwendet. Für grössere
Vergleiche eine feste Modellversion wählen. Kostenpflichtige Anfragen werden
nicht automatisch wiederholt. Der normale `record`-Befehl ruft Jev nicht auf.

`report_jev.*` vergleicht die volle Basisregel, `scored_control` und `jev_gate`.
Die Vergleichsauswahl handelt nur Kandidaten, die Jev zur Bewertung vorlagen,
und verwendet keine AI-Verzögerung. So wird ein Ausschnitt mit 20 Anfragen
nicht mit allen Kandidaten der Basisregel verwechselt. Fehlende, fehlgeschlagene
und abgelehnte AI-Entscheidungen handeln nicht. Im Handelsergebnis sind
Taker-Gebühren enthalten, API-Kosten jedoch nicht. Dafür Tokenverbrauch und
die tatsächlichen Kontopreise heranziehen.

## Beobachtete Läufe und Prüfung

Die erste Aufzeichnung am 09.10.2026 dauerte 120 Sekunden: 203’016
Orderbuchereignisse, 680 Binance- und 267 Coinbase-Preismeldungen. Keine
protokollierten Fehler oder Warteschlangenverluste. Die 2-bp-Schwelle auf
Binance wurde nicht erreicht. Die grössten absoluten Einsekundenrenditen
lagen bei rund 0.97 bp auf Binance und 1.75 bp auf Coinbase. Dieser ruhige
Lauf prüft die Verbindung, nicht die Profitabilität.

Die zweite Aufzeichnung dauerte 300 Sekunden bei unveränderter 2-bp-Regel:
494’434 Orderbuchereignisse, 4’566 Binance- und 1’616 Coinbase-Preismeldungen.
Ein Polymarket-Verbindungsfehler wurde protokolliert und behoben. Kein
Warteschlangenverlust. Acht Kandidaten ergaben getrennt simuliert:

| Verzögerung | Geschlossene Trades | Offene Positionen | Nettoergebnis USD | Gebühren USD |
|---|---:|---:|---:|---:|
| 100 ms | 7 | 0 | +2.70172 | 0.99828 |
| 250 ms | 6 | 0 | +1.90014 | 0.69986 |
| 500 ms | 5 | 0 | +1.23622 | 0.56378 |
| 1’000 ms | 5 | 0 | +1.55323 | 0.54677 |

Sieben Asks stiegen innerhalb von fünf Sekunden um mindestens einen Cent.
Der bedingte Median der Reaktionszeit lag bei 161.33 ms. Ein Kandidat zeigte
keine solche Reaktion. Die kleine, abhängige Stichprobe mit optimistischen
Fills belegt weder kausalen Vorlauf noch einen dauerhaften Handelsvorteil.
Die vier Verzögerungen sind keine vier unabhängigen Stichproben.

Lokaler Beleg: `data/cex_leadlag/20261009T112743Z-76a3bc/report.md` sowie JSON
und CSV im selben Ordner. Bruttoerlöse, Gebühren und Kapital wurden für alle
vier Varianten unabhängig nachgerechnet. Dies ist kein geprüfter echter
Gewinnnachweis. Es war kein TypeSafe-API-Key hinterlegt; es fand keine
kostenpflichtige Jev-Anfrage statt.

### 15-Minuten-Validierung am 09.10.2026

Lauf von 17:33:36 bis 17:48:36 Uhr Zürcher Zeit, mit unveränderten Parametern.
Das Programm beendete Aufzeichnung und Replay erfolgreich. Erfasst wurden
2’062’936 Orderbuchereignisse, 6’550 Binance- und 4’804 Coinbase-Preismeldungen.
Das Archiv umfasst rund 553 MB. Beide Outcomes aller sechs während der
Aufzeichnung aktiven Märkte hatten vollständige Snapshots: vier 5-Minuten-
und zwei 15-Minuten-Märkte. Die Auswahl folgte somit den Marktwechseln.

Vier Signale entstanden an drei unterschiedlichen Zeitpunkten; zwei Signale
gehörten zum selben CEX-Impuls in verschiedenen Märkten. Ergebnisse:

| Verzögerung | Geschlossene Trades | Offene Positionen | Nettoergebnis USD | Gebühren USD |
|---|---:|---:|---:|---:|
| 100 ms | 3 | 0 | +2.43351 | 0.96649 |
| 250 ms | 0 | 0 | 0 | 0 |
| 500 ms | 0 | 0 | 0 | 0 |
| 1’000 ms | 0 | 0 | 0 | 0 |

Bei 100 ms scheiterte ein Einstieg am Kauflimit. Ab 250 ms lagen drei Preise
bereits über dem Limit; für den vierten Kandidaten fehlte ein gültiges
Einstiegsbuch. Das Nullergebnis dieser Varianten bedeutet deshalb keine
ausgeführten Trades und keinen gemessenen Handelsverlust.

Die drei geschlossenen Trades verdienten netto 0.08213, 0.07422 und
2.27716 USD. Der letzte Trade liefert 93.58 % des gesamten Gewinns.
Eine breite, wiederholbare Profitabilität ist daraus nicht ableitbar.
Alle vier Asks reagierten um mindestens einen Cent; der Median der
beobachteten Reaktion betrug 143.23 ms. Dies bleibt eine Beschreibung
nach dem Signal und keine kalibrierte Gewinnwahrscheinlichkeit.

Datenqualität: kein erkannter Warteschlangenverlust, aber elf protokollierte
Polymarket-`ConnectionError`-Ereignisse. Die Statusmeldungen zeigen 19
Wiederverbindungsintervalle mit zusammen 58.165 Sekunden, maximal
3.943 Sekunden. Darin sind auch die vorgesehenen minutenweisen
Neuverbindungen enthalten. Diese Zeit misst den Verbindungszustand und
belegt keine lückenlose Orderbuchabdeckung. Bücher wurden bei Abbrüchen
ungültig; die Simulation verwendete sie erst nach neuen Snapshots wieder.

Archiv- und Implementierungsprüfsummen stimmen. Gewinne, Gebühren und
Kapital wurden für jede Variante unabhängig aus den Einzeltrades nachgerechnet.
Lokaler Beleg: `data/cex_leadlag/20261009T153336Z-cb36a4/report.md`,
`report.json`, `report_trades.csv` und `events.jsonl`.

Einordnung: Der mögliche Vorteil verschwand in diesem Lauf bereits zwischen
100 und 250 ms unter den festgelegten Kauflimits. Als nächster Schritt sind
deshalb Verbindungsstabilität und ein realistisches Ausführungszeitbudget zu
prüfen. Zusätzliche AI-Latenz muss daran gemessen werden; ein Jev-Mehrwert
wurde weiterhin nicht getestet.

### Zusätzliche Datensammlung und Verbindungsdiagnose

Am 09.10.2026 um 19:30:58 Uhr Zürcher Zeit wurde auf Wunsch eine weitere
Aufzeichnung über 3’600 Sekunden gestartet. Die Handelsparameter bleiben
unverändert. Lauf: `data/cex_leadlag/20261009T173058Z-fb372f/`.
Die Aufzeichnung endete am selben Tag um 20:30:58 Uhr; die vier Paper-
Auswertungen liegen vollständig vor. Am 10.10.2026 wurden Archiv, Zählungen
und finanzielle Ergebnisse unabhängig nachgerechnet. Es handelt sich um
eine begrenzte Aufzeichnung, keine Terminserie. Die abschliessenden Ergebnisse
stehen im folgenden Abschnitt zur Stundenvalidierung.

Die Statusereignisse des vorherigen 15-Minuten-Laufs wurden getrennt
nachgezählt. Von 19 Wiederverbindungslücken entfielen acht mit zusammen
20.10374 Sekunden auf die geplante minutenweise Markterneuerung und elf
mit 38.06112 Sekunden auf `ConnectionError`. Die unerwarteten Schliessungen
traten nach 3.16 bis 58.98 Sekunden Verbindungsdauer auf. Damit erklärt
der 60-Sekunden-Neustart diese elf Ereignisse nicht. Der Recorder speicherte
bisher nur die Fehlerklasse, keinen WebSocket-Schliessungscode. Eine Ursache
wie Serverfehler, Netzproblem oder Herzschlagfehler ist daraus nicht belegt.

Nach einer erfolgreichen Verbindung lagen die vollständigen Snapshots
beider Outcomes aller zu diesem Zeitpunkt aktiven Märkte nach weiteren
43.73 bis 78.03 ms vor. Diese zusätzliche Wartezeit ist in den oben genannten
Verbindungslücken nicht enthalten. Die Prüfung basiert auf lokalen
Empfangszeiten, nicht auf synchronisierten Börsenuhren.

Ein separater öffentlicher Fünf-Minuten-Test lief von 19:35:31 bis 19:40:31 Uhr
mit einer festen Auswahl von acht Outcome-IDs. Er verzichtete auf den geplanten
Minutenneustart und protokollierte WebSocket-Schliessungscode und Grund sowie
Text-`PING`/`PONG`-Antwortzeiten. Der laufende Recorder und seine Handelsparameter
blieben unverändert. Script und lokale Messdaten:
`outputs/cex_leadlag_diagnostics/20261009T1737Z/`. Die Nachzählung liegt
in `stability.json`. Die offiziellen Vorgaben verlangen Text-`PING` alle
zehn Sekunden und erlauben Änderungen der abonnierten Outcome-IDs innerhalb
derselben Verbindung. Das ist ein möglicher Weg, die geplanten Lücken später
zu entfernen; eine entsprechende Recorderänderung ist noch nicht erfolgt.

Ergebnis der Diagnose: 341’807 Datenframes, 29 beantwortete Text-Pings und
eine unerwartete Schliessung nach 52.893 Sekunden. Der Server meldete Code
1013 mit dem Grund `slow consumer: send buffer full`. Nach der Wiederverbindung
lief der Rest des Tests ohne weiteren Abbruch. Der Ping-Median betrug
27.12 ms, das empirische 95. Perzentil nach der Rangmethode 36.05 ms und
das Maximum 148.51 ms. Es gab keinen protokollierten ausstehenden Ping
beim nächsten Sendetermin. Rohlog und Zusammenfassung sind
`probe_events.jsonl` und `probe_summary.json` im genannten Diagnoseordner.
Die Zählungen wurden unabhängig gegengeprüft.

Damit ist ein voller serverseitiger Sendepuffer als unmittelbarer
Schliessungsgrund in diesem separaten Test belegt. Es ist nicht bewiesen,
welche Stelle die Zustellung ausbremste oder ob alle elf historischen
Schliessungen denselben Grund hatten. [Vermutung] Ein möglicher lokaler
Engpass ist die zusätzliche UTF-8-Prüfung von `websocket-client` in Python.
Die installierte Version 1.9.0 nutzt hier keine `wsaccel`-Beschleunigung;
die Herstellerdokumentation beschreibt diese Prüfung als langsam.
Vor einer Änderung ist der tatsächliche Durchsatz mit strikter UTF-8-
Dekodierung zu messen. Die Bibliothekprüfung einfach abzuschalten und eine
behobene Ursache zu behaupten wäre durch diese Diagnose nicht gedeckt.

Prüfung dieser Erweiterung: Der Fünf-Minuten-Prozess endete erfolgreich;
Anzahl Verbindungen und Ping-Antworten stimmen mit dem Rohlog überein.
Vier SHA-256-Prüfsummen bestätigen unveränderten Recorder, Replay, Jev-Adapter
und Orderbuchkern. Die Messung fügt keine externe Abhängigkeit hinzu.

Ping-Antwortzeiten messen öffentlichen Transport, Serverantwort und die
lokale Empfangswarteschlange. Sie sind keine Orderbestätigung und kein
Nachweis, dass ein sichtbarer Preis innerhalb von 100 ms handelbar war.
Ein realistisches Budget muss zusätzlich Signalverarbeitung, gegebenenfalls
AI-Antwortzeit, Ordersignatur, Orderübertragung und Matching berücksichtigen.
In diesem Test werden keine echten Orders gesendet.

### Stundenvalidierung vom 09.10.2026, geprüft am 10.10.2026

Der Lauf von 19:30:58 bis 20:30:58 Uhr Zürich ist vollständig abgeschlossen.
Erfasst wurden 6’580’672 Orderbuchereignisse, 18’693 Binance- und 18’918
Coinbase-Preismeldungen. Das Archiv umfasst rund 1.77 GB. Beide Outcomes
aller 18 zeitlich aktiven Märkte hatten vollständige Snapshots: 13 Märkte
mit fünf Minuten und fünf Märkte mit 15 Minuten Laufzeit. Dies prüft die
Marktauswahl und das Vorhandensein von Snapshots, keine lückenlose Abdeckung.

Die unveränderte Regel erzeugte 29 Signale an 16 unterschiedlichen
Zeitpunkten. Mehrere Signale betreffen denselben Impuls in verschiedenen
Märkten und bilden deshalb keine unabhängigen Beobachtungen.
Jede Verzögerung verwendet separat 100 USD Paper-Kapital und zehn Anteile:

| Verzögerung | Geschlossen | Offen | Netto realisiert USD | Gebühren geschlossener Trades USD | Gebundener Einsatz offen USD |
|---|---:|---:|---:|---:|---:|
| 100 ms | 22 | 2 | +10.55883 | 5.69117 | 2.94840 |
| 250 ms | 17 | 2 | +6.33157 | 4.61843 | 3.15484 |
| 500 ms | 13 | 1 | +7.04144 | 3.65856 | 0.42688 |
| 1’000 ms | 8 | 0 | +0.69518 | 2.30482 | 0 |

Die offenen Positionen haben keinen beobachteten Ausstieg und bleiben
unbewertet. Wird ihr Restwert vorsichtig mit null angesetzt, bleiben in
derselben Simulation netto +7.61043, +3.17673, +6.61456 und +0.69518 USD.
Dies sind Rechenszenarien innerhalb des Paper-Modells, keine tatsächlichen
Gewinne oder garantierten Untergrenzen bei realer Ausführung.

Bei 100 ms gewannen 16 der 22 geschlossenen Trades. Der grösste Gewinn
von 2.66347 USD lieferte 25.23 % des realisierten Nettoergebnisses.
Das Ergebnis hängt damit weniger an einem Einzeltrade als im vorherigen
15-Minuten-Lauf. Ein belastbarer Handelsvorteil ist dennoch nicht belegt:
Es gibt nur 16 Impulszeitpunkte in einer Stunde und die Fills beruhen
weiterhin auf sichtbarer Liquidität. Die Varianten handeln unterschiedliche
Teilmengen; die höhere Summe bei 500 gegenüber 250 ms bedeutet nicht,
dass längere Verzögerung generell hilft. Gewinne der Varianten nicht addieren.

27 Asks stiegen innerhalb des Beobachtungshorizonts um mindestens einen Cent.
Bei einem Kandidaten verhinderte eine Datenlücke die vollständige Beobachtung;
bei einem weiteren wurde keine solche Reaktion beobachtet. Der bedingte
Median der beobachteten Reaktion betrug 164.18 ms. Der Test schätzt weder
die Auflösungswahrscheinlichkeit noch einen kausalen CEX-Effekt.

Datenqualität: kein erkannter Warteschlangenverlust, aber elf Polymarket-
Verbindungsfehler. Die 63 Wiederverbindungslücken summieren sich auf
164.93063 Sekunden: 52 geplante Minutenneustarts mit 127.39750 Sekunden
und elf unerwartete Abbrüche mit 37.53313 Sekunden. Wartezeiten auf neue
Snapshots kommen hinzu. Der Schliessungsgrund der elf Ereignisse ist nicht
gespeichert; Code 1013 aus der separaten Diagnose bleibt ein eigener Befund.

Prüfung: Die SHA-256-Prüfsumme des gesamten Archivs stimmt mit dem Manifest
überein. Alle Ereigniszählungen stimmen, ebenso die vier Implementierungs-
prüfsummen. Einzeltrades aus CSV und JSON wurden mit Dezimalarithmetik
nachgerechnet: Erlös, Einstiegsbetrag, Gebühren, realisiertes Ergebnis,
offener Einsatz und verbleibendes Kapital stimmen in allen vier Varianten.
Die Nachrechnung prüft die gespeicherten Trades, keine tatsächlich erreichten
Fills. Recorder und Handelsregel wurden für diese Auswertung nicht verändert.

Belege: `data/cex_leadlag/20261009T173058Z-fb372f/report.md`, `report.json`,
`report_trades.csv`, `manifest.json` und `events.jsonl`. Die reproduzierbare
Nachrechnung und ihr Ergebnis liegen unter
`outputs/cex_leadlag_audit/20261010/verify.py` und `verification.json`.
Der folgende historische Prüfbefehl erwartet auch die damaligen
Quellprüfsummen. Seit der Empfangskorrektur meldet er deshalb beim
aktuellen Feed-Modul absichtlich eine Abweichung. Der bestätigte Prüfstand
vom 10.10.2026 bleibt in `verification.json` erhalten; die damalige
Feed-Version liegt zusätzlich unter `outputs/cex_receive_fix/20261011/cex_leadlag_feed.py.before`.

```powershell
python -X utf8 outputs/cex_leadlag_audit/20261010/verify.py
```

Damals nächster Schritt: Empfangsdurchsatz messen und die vermeidbaren
Minutenneustarts durch abonnierte Marktwechsel ersetzen. Diese Korrektur
ist unten dokumentiert. Jev bleibt ungetestet; ein sinnvoller
Vergleich muss dieselben Kandidaten und die tatsächliche zusätzliche
Antwortzeit verwenden. Der Stundenlauf enthält keine AI-Aufrufe.

### Empfangskorrektur vom 11.10.2026

Der Empfangsengpass wurde auf 3’000 echten öffentlichen Frames untersucht.
Die bisherige Python-UTF-8-Prüfung brauchte im ersten Vergleich zusammen
300.21 ms, die native strikte Dekodierung 0.50 ms. Im zweiten Vergleich
mit der tatsächlich eingebauten Funktion einschliesslich Frameprüfungen
betrugen die Mediane 346.44 ms für den alten Prüf- und Dekodierweg und
2.44 ms für den neuen Weg. Jeweils fünf Wiederholungen auf denselben
gespeicherten Inhalten. Dies misst einen lokalen Verarbeitungsschritt,
keine gesamte Empfangs- oder Orderlatenz. Last und Zeitfenster waren im
Live-Test anders als in den historischen Läufen.

Die zusätzliche Byteprüfung von `websocket-client` entfällt. Stattdessen
prüft die native UTF-8-Dekodierung weiterhin strikt. Ungültige Texte,
unerwartete Binärdaten und zu grosse Meldungen werden zurückgewiesen.
Empfangszeiten werden vor Dekodierung und JSON-Verarbeitung genommen.
Preis-, Tiefen- und Gebührenprüfungen bleiben erhalten.

Ein eigener Hintergrundthread lädt Marktinformationen. Der Empfang wartet
nicht auf diese HTTP-Abfragen. Neue Outcome-IDs werden auf derselben
WebSocket-Verbindung hinzugefügt, abgelaufene entfernt. Bestehende Bücher
werden durch diesen Wechsel nicht ungültig. Neue Tokens brauchen weiterhin
einen vollständigen Snapshot. Der bisherige Minutenneustart ist entfernt.
Bei tatsächlichen Abbrüchen bleiben Wiederverbindung, Zurücksetzen der
Bücher und die Snapshot-Pflicht erhalten. Schliessungsframes speichern
nun ihren Code und Grund; Text-Pings liefern zusätzliche Antwortzeitdaten.

Sieben neue Tests prüfen unter anderem ungültiges UTF-8, Schliessungsgründe,
Kontrollframes, Zeitüberschreitung, Empfangszeit vor Verarbeitung und einen
Marktwechsel über 75 virtuelle Sekunden ohne neue Verbindung. Die sieben
Tests und die bisherige Orderbuch-, Gebühren-, Replay- und Jev-Abdeckung
bestanden zusammen: 145 Tests. Ruff bestand projektweit. Ponytail Review
fand keine unnötige zusätzliche Abstraktion oder Abhängigkeit.
Die Handelsregel in `src/cex_leadlag.py` blieb bytegleich.

Reproduzierbarer lokaler Vergleich, im Projektordner:

```powershell
$env:PYTHONPATH = (Get-Location).Path
python -X utf8 outputs/cex_receive_fix/20261011/benchmark.py
python -m unittest tests.test_book_stream tests.test_venue_fees tests.test_fee_schedule_parity tests.test_cex_leadlag tests.test_cex_decision tests.test_cex_leadlag_feed
python -m ruff check .
```

Messdaten, Vorher-Versionen, Profil und Quellprüfsummen liegen unter
`outputs/cex_receive_fix/20261011/`. Der siebenminütige Live-Test ist
`data/cex_leadlag/20261011T094806Z-e564fd/`.

Der Live-Test vom 11.10.2026, 11:48 bis 11:55 Uhr Zürich, ist vollständig
abgeschlossen. 477’484 Orderbuchereignisse, je eine Verbindung zu Binance,
Coinbase und Polymarket, keine protokollierten Verbindungsfehler. Ein
Marktwechsel fügte zwei Outcome-IDs hinzu und entfernte zwei alte, ohne
Neustart. Alle neuen Outcomes erhielten vollständige Snapshots, beim
Wechsel nach 22.50 ms. Die Warteschlange belegte maximal 108 von 100’000
Plätzen. Archivprüfsumme und Ereigniszählungen bestanden. Die 41 Ping-
Antworten lagen im Median bei 21.79 ms, am 95. Perzentil bei 37.80 ms,
maximal bei 329.63 ms. Dies ist keine Messung der Orderlatenz. Ein kurzer,
ruhiger Lauf belegt keine dauerhafte Fehlerfreiheit unter höherer Last.

In allen vier Replay-Varianten gab es null Signale und null Trades.
Die Signalgrenze bleibt unverändert. Qualitätsbeleg:
`data/cex_leadlag/20261011T094806Z-e564fd/quality_report.json`.
Nachrechnung der Empfangsqualität:

```powershell
python -X utf8 outputs/cex_receive_fix/20261011/quality.py data/cex_leadlag/20261011T094806Z-e564fd
```

Seit 11:56:42 Uhr Zürich laufen drei aufeinanderfolgende Stundenfenster.
Nach jedem Fenster erzeugt der bestehende Recorder automatisch die vier
Paper-Auswertungen. Der erste Block liegt unter
`data/cex_leadlag/20261011T095642Z-2c8689/` und endet voraussichtlich um
12:56:42 Uhr. Die ganze Folge dauert rund drei Stunden zuzüglich
Replay-Zeit. Starter: `outputs/cex_receive_fix/20261011/collect_three_windows.py`.
Ein Fehler beendet die Folge. Die Quellstände bleiben währenddessen fest.
Nächster offener Schritt ist die Auswertung der abgeschlossenen Blöcke,
einschliesslich Verbindungsfehlern, Warteschlange und Snapshots. Danach
folgt die Abschätzung eines realistischen Ausführungszeitbudgets.

### Zwischenergebnis und Latenzgrenzen, 11.10.2026

Eine feste Momentaufnahme des laufenden Archivs reicht von 11:56:43 bis
12:16:52 Uhr Zürich, 1’209.55 Sekunden. Sie enthält 1’333’110
Orderbuchereignisse, 2’420 Binance- und 1’272 Coinbase-Preismeldungen.
Alle drei Feeds hatten je eine Verbindung, es gab keine protokollierten
Fehler oder Trennungen. Vier Marktwechsel erfolgten ohne Neustart; alle
hinzugefügten Outcomes erhielten Snapshots. Die 120 Ping-Antworten lagen
im Median bei 22.70 ms, am 95. Perzentil bei 28.63 ms und maximal bei
37.21 ms. Dies bestätigt nur dieses bisher ruhige Zeitfenster, keinen
dauerhaft stabilen Empfang unter höherer Last. Die endgültige Prüfung auf
Datenverlust und das Warteschlangenmaximum sind erst nach Laufende verfügbar.

Der grösste gemessene Binance-Impuls über das Sekundenfenster betrug
1.5992 bp und blieb unter der unveränderten Signalgrenze von 2 bp.
Deshalb gab es in allen vier Varianten keine Signale, keine Trades und
keine Gebühren. Coinbase erreichte 2.3770 bp, ist aber nur Vergleichsquelle.
Die Regel wurde für dieses ruhige Fenster nicht gelockert.

Das Präfix wurde bis zu einer vollständigen Zeile eingefroren, seine
SHA-256 erneut geprüft und für das Replay mit SQLite nach Empfangszeit
sortiert. Das aktive Archiv und sein Manifest wurden nicht verändert.
Die finanzielle Nachrechnung bestand für alle Zwischenvarianten und die
vier Varianten des historischen Stundenlaufs. Skript und Ergebnisse:
`outputs/cex_receive_fix/20261011/interim.py` und `interim_report.json`.
Der Bericht enthält Bytegrenze, Präfixprüfsumme, Quellprüfsummen und genaue
Zeitpunkte. Das Skript wertet bei erneutem Aufruf einen neuen aktuellen
Präfix aus; die im Bericht gespeicherte Grenze bezeichnet den damaligen Stand.

Die echte Gesamtlatenz von Erkennung bis Fill ist bisher nicht gemessen.
Der Recorder sammelt live, die Handelsentscheidungen entstehen nachträglich
im Replay. Die 100/250/500/1’000 ms sind dort angenommene Verzögerungen ab
lokalem Empfang des auslösenden CEX-Ticks, keine gemessenen Orderzeiten.
Das Sekundenfenster ist ein rückwärts gerichtetes Messfenster und kein
zusätzliches Warten nach jedem Signal. Auch Ping misst keine Orderannahme,
Matching-Zeit oder Fill-Bestätigung.

Für einen späteren Ausführungstest sind getrennte monotone Messpunkte nötig:
Empfang, fertiges Signal, abgeschlossene Risikoprüfung, Signatur, Versand,
Orderantwort und bestätigter Trade. Lokale Bücher und Risikogrenzen sollten
im Speicher liegen; Archivierung und externe AI-Abfragen gehören nicht in
den zeitkritischen Ablauf. Wiederverwendete Verbindungen und vorbereitete
Metadaten vermeiden zusätzlichen Aufwand. Ob Netzwerkstandort oder Signieren
danach dominieren, muss gemessen werden. Ein Standortwechsel ist ohne
Vergleichsmessung noch keine belegte Verbesserung.

Die aktuelle offizielle Dokumentation unterscheidet angenommene Orders
von gematchten Orders und kennt marktbedingte Verzögerungen. Um 12:18 Uhr
Zürich meldete die öffentliche CLOB-API für die geprüften 5- und
15-Minuten-Märkte `seconds_delay: 0`; Gamma lieferte dazu keinen Wert.
Dies ist eine Metadatenangabe, keine Messung der echten Matching-Dauer.
Beleg: `outputs/cex_receive_fix/20261011/current_market_delay.json`.
[Orderstatus und Verzögerungen](https://docs.polymarket.com/trading/place-orders),
[Trade- und Settlement-Bestätigungen](https://docs.polymarket.com/trading/realtime-order-updates).

Stand vor der Empfangskorrektur: 22 eigene Tests und insgesamt 138 Tests einschliesslich der vorhandenen
Orderbuch- und Gebührenmodule bestanden. Ruff bestand projektweit. Der
Gesamtlauf blieb an der vorhandenen Streamlit-Seite `copy-trade` hängen;
ein separater Lauf reproduzierte deren 60-Sekunden-Zeitüberschreitung.
Ein weiterer Lauf ohne genau diesen Test führte 2’900 Tests aus, mit einem
Fehler und einer vorgesehenen Auslassung: Der bestehende Claims-Lint beanstandet
`web/js/pages/copy_intelligence.js:101`. Diese zuvor unversionierte Datei wurde
hier nicht verändert. Ein vollständig grüner Gesamtlauf wird nicht behauptet.

Nach der Sprachumstellung bestanden dieselben 138 Tests und Ruff erneut.
Beide vorhandenen Berichte wurden auf Deutsch neu erzeugt. Alle Trades,
Gebühren, Kapitalstände und finanziellen Ergebnisse blieben identisch.

```powershell
python -m unittest tests.test_cex_leadlag tests.test_cex_decision
python -m ruff check src/cex_leadlag.py src/cex_leadlag_feed.py src/cex_decision.py tests/test_cex_leadlag.py tests/test_cex_decision.py
```

Ponytail Review entfernte unnötige Initialisierungen und doppelte
Berichtszeilen. Keine neue externe Abhängigkeit. Die lokale Projektkarte wurde
mit `graphify update . --no-cluster` aktualisiert. Der Intendant-Agenda-Zugriff
scheiterte an HTTP 426, weil der CLI-Endpunkt TLS verlangt. Offene Punkte
bleiben deshalb in dieser Datei und `docs/HANDOFF.md` festgehalten.

## Primärquellen

- [Binance: WebSocket-Daten](https://developers.binance.com/docs/binance-spot-api-docs/web-socket-streams)
- [Coinbase: WebSocket-Kanäle](https://docs.cdp.coinbase.com/exchange/websocket-feed/channels)
- [Polymarket: Echtzeitdaten](https://docs.polymarket.com/market-data/realtime-data)
- [websocket-client: Empfang von Daten und Schliessungsframes](https://websocket-client.readthedocs.io/en/latest/_modules/websocket/_core.html)
- [websocket-client: dokumentierte Performancegrenzen](https://websocket-client.readthedocs.io/en/latest/faq.html)
- [Polymarket: Marktmetadaten](https://docs.polymarket.com/market-data/market-details)
- [Polymarket: Gebühren](https://docs.polymarket.com/trading/fees)
- [TypeSafe: API-Schema](https://api.typesafe.ai/openapi.json)
- [Jev 1.13: dokumentierte Grenzen, Stand 02.10.2026](https://docs.typesafe.ai/model-jaggedness/jev-1.13)
