# Studien aktualisieren

**Ziel:** Neuere belegte Forschung im bestehenden Studienbereich zeigen, die
Buchabgleich-Kontrolle aus der Studienliste entfernen und die Erneuerung der
historischen Arbeiten nachvollziehbar planen.

**Autorisierung:** Nutzerauftrag vom 12.10.2026 nach Sichtung der Recherche.
**Aufbau:** Bestehender Payload-Builder und Renderer, portable versionierte
Ergebnissnapshots, keine zusätzliche Abhängigkeit. Website Englisch,
Forschungsagenda Deutsch (Schweiz). Bestehende uncommittete Arbeiten erhalten.

## Fertig-Kriterien

- [x] Sechs neuere Studien zu CEX, Ausführungsverzögerung, MM, Quellengeschwindigkeit,
  Arb-Prüfung und Fed-Vergleich mit Datenzeitraum, Quellen, Zahlen und Grenzen.
- [x] `book-reconcile` entfällt aus Nutzlast, Zählern und generierten Studienseiten;
  historische Kontrollberichte und Forschungsdaten bleiben erhalten.
- [x] Aktuelle und historische Arbeiten sind erkennbar getrennt. Publikationsdatum
  wird nicht als Beobachtungszeitraum ausgegeben.
- [x] Historische Studien erhalten konkrete nächste Forschungsfragen. Keine neue
  Parameterwahl auf Testdaten, keine Sammler, Trades oder kostenpflichtigen APIs.
- [x] Forschungsagenda beurteilt 1–11 einzeln und priorisiert Arb und finanziertes MM.
- [x] 200 gezielte Tests, Ruff, Syntax, Build und Browserprüfung bestanden.
  Gesamtsuite und globaler Claims-Lint haben dokumentierte Einschränkungen in `docs/HANDOFF.md`.

## Umsetzung

1. Regressionen für entfernte Kontrolle, neue Karten, Zeiträume und Folgefragen
   zuerst prüfen. Separater Worker erstellt portable Quellensnapshots und Karten.
2. Karten in den gemeinsamen Builder integrieren; aktuelle Studien zuerst anzeigen,
   historische IDs und bestehende Links erhalten. Nachfolgefragen als geplant zeigen.
3. Statische Studienseiten, Übersicht und Studienbeschreibung angleichen. Historische
   Zahlen nicht allein durch neue Exportzeitstempel aktualisieren.
4. Nutzlast lokal erzeugen, Prüfungen ausführen, fachliches Review und Ponytail-Review.
   Ergebnis und tatsächliche Prüfungen in `docs/HANDOFF.md` festhalten.

## Arbeitsteilung

- Hauptagent: Builder, bestehende Tests, Renderer, statische Seiten, Integration.
- Worker Research-Paket: neue `app/research_updates.py`, Quellensnapshot, Kartenberichte,
  zugehörige Tests. Kein zusätzliches Importwerkzeug nötig.
- Worker Forschungsagenda: `docs/research/research_renewal_2026-10-12.md`.

## Entscheidungen

- Keine blinde Neuberechnung auf mehr Zeilen. Zuerst Ausführbarkeit, Datenabdeckung,
  unabhängige Ereigniseinheiten und unverbrauchte Testfenster prüfen.
- Lokale Änderungen bleiben reviewbar im bestehenden Arbeitsstand. Keine Änderungen
  an Produktionssystemen oder anderen Projektordnern.
