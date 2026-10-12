# Marketmaking: Queue und Verzögerung im Testfenster

Die eingefrorene Quote-Regel bestand den registrierten Primärtest bei sofortigem Quote-Wechsel. Das ist ein positives Ergebnis im Idealmodell. Für einen Echtgeldstart ist es kein belastbarer Nachweis: Bei angenommenen 250 ms Verzögerung werden beide Queue-Modelle deutlich negativ.

| Queue-Modell | Verzögerung | Simulierte Fills | Summe inkl. angenommener Rebates, USD | Ohne Rebates, USD | 95%-Intervall Tagesmittel, USD |
|---|---:|---:|---:|---:|---:|
| queue_back | 0 ms | 20'385 | +36'794.77 | +33'620.32 | +1'683.52 bis +3'553.93 |
| queue_front | 0 ms | 22'366 | +38'472.30 | +35'175.06 | +1'782.85 bis +3'705.33 |
| queue_back | 250 ms | 33'658 | −39'705.31 | −44'852.79 | −3'671.53 bis −1'833.46 |
| queue_front | 250 ms | 36'435 | −39'219.07 | −44'537.35 | −3'572.20 bis −1'839.65 |

Das Fenster umfasst den 4. bis 17. September 2026, 14 Tage mit Daten. Zwischen Buchdateien besteht eine Lücke von 29.746 Stunden. Die Summen stammen aus einer Simulation ohne gemeinsames Kapitalbudget. Inventare starten täglich neu; Restbestände werden zum letzten beobachteten Mid bewertet. Queue-Position, Fills und tatsächliche Quote-Aktivierung sind nicht durch eigene Live-Orders verifiziert. Die 250 ms sind ein Szenario, keine gemessene Orderlatenz. Deshalb sind die Summen weder realisierte Kontogewinne noch Renditen.

Originalbericht: Projekt `pmt-mm-research`, Datei `docs/research/mm_assessment_2026-09-19.md`, SHA-256 `efb7ba5be896bb87933d0144b2b68720ccc6013d8c51b29509c78d5804b0a1fc`. Die Zahlen und Quellenzuordnung sind im [portablen Snapshot](research_updates_2026-10-12.json) festgehalten. `app/research_updates.py` ist nur der Publikationsadapter, nicht das ursprüngliche Forschungsmodul.
