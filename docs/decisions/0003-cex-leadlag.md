# CEX-Vorlauf: Paper-Test und optionale Decision-AI

Datum: 09.10.2026. Status: lokal für die Untersuchung implementiert.

## Ziel und Umfang

Prüfen, ob BTC-Impulse auf Binance oder Coinbase handelbaren Kursanpassungen
in Polymarket-Up/Down-Märkten vorausgehen. Die Implementierung verwendet
separate Recorder-, Replay- und AI-Module unter `src/` sowie die vorhandenen
Bausteine `BookState`, Prozesssperre, requests und websocket-client.
Öffentliche Daten werden aufgezeichnet und simuliert. Es wurden weder neue
Abhängigkeiten noch ein Orderpfad, eine Veröffentlichung oder ein geplanter
Hintergrundlauf eingerichtet.

## Entscheidung

Marktregeln, Gebühren und empfangene Daten lokal speichern. Anschliessend
Kauf und Verkauf mit unterschiedlichen Verzögerungen, tatsächlicher sichtbarer
Tiefe, Gebühren, Kapitalgrenzen und Frischeprüfungen simulieren. Die lokale
monotone Empfangszeit vermeidet die Annahme synchronisierter Börsenuhren.
Verbindungsabbrüche bleiben sichtbar; beschädigte oder verlustbehaftete
Archive werden verworfen. Nicht ausführbare Ausstiege bleiben unbewertet.
SQLite sortiert grössere Aufzeichnungen temporär auf dem Datenträger.

Eine feste Impulsregel bildet den Ausgangspunkt. Jev bewertet optional
freigegebene, zum Signalzeitpunkt eingefrorene Merkmale. Seine gemessene
Antwortzeit erhöht die simulierte Einstiegsverzögerung. Der Vergleich erfolgt
gegen dieselben Kandidaten ohne AI-Filter. Modellversion und Tokenverbrauch
werden gespeichert. Nur der separate `score`-Befehl mit API-Key kann
kostenpflichtige Anfragen auslösen.

## Begründung und Grenzen

Eine Strategie bis zur Auflösung braucht die exakte offizielle Referenzreihe
und unabhängig geprüfte Wahrscheinlichkeiten. Ein CEX-Impuls allein liefert
weder diese Ergebnisse noch eine Gewinnwahrscheinlichkeit von 85 %. Der erste
Test untersucht deshalb den Wiederverkauf nach Kursanpassungen.

Ein Decision-Modell direkt im zeitkritischen Ablauf würde seine Auswahlgüte
mit zusätzlicher Latenz vermischen. Der nachträgliche Vergleich macht beides
sichtbar. TypeSafe dokumentiert Grenzen bei Zahlenpräzision und der Reihenfolge
von Antwortoptionen. Rechenoperationen und Ausführungsprüfungen bleiben im Code.

Sichtbare Tiefe beweist keinen echten Fill. Das simulierte Ergebnis bleibt
optimistisch und muss zusammen mit offenen Positionen und möglichen API-Kosten
beurteilt werden. Nachträgliche Parametersuche ist keine unabhängige Validierung.

## Umsetzung und Prüfung

Ergänzung vom 11.10.2026: Der Empfang verwendet nach einer Messung auf echten
Frames strikte native UTF-8-Dekodierung anstelle der zusätzlichen langsamen
Bibliotheksprüfung. Metadatenabfragen laufen in einem separaten Thread;
Outcome-Abonnements wechseln auf derselben Verbindung. Geplante minutenweise
Neuverbindungen entfallen. Echte Abbrüche setzen die Bücher weiterhin zurück.
Schliessungsgründe, Ping-Antwortzeiten und die maximale Warteschlangenbelegung
werden gespeichert. Die Handelsregel und das Paper-Budget bleiben gleich.

- [x] Datenformate, Zuordnung von Up/Down-Token und Gebühren validieren.
- [x] Öffentliche BTC-Preise und Orderbücher mit Empfangszeit aufzeichnen.
- [x] Zeitlich korrekte Fills, Kosten, Kapitalgrenzen und Datenlücken prüfen.
- [x] Optionalen Jev-Adapter mit Eingabeprüfsummen und Vergleichsauswahl ergänzen.
- [x] Reale Daten aufzeichnen und Berichte erzeugen.
- [x] Dokumentation und erzeugte Berichte auf Deutsch halten, gemäss Vorgabe vom 09.10.2026.

Befehle, beobachtete Ergebnisse, Prüfergebnisse und die nächsten Schritte
stehen in der [Methodik und Auswertung](../research/cex_leadlag.md).
