# CEX-Lead/Lag: erster Forward-Zwischenstand

Stand des eingefrorenen Zwischenstands: 12. Oktober 2026, 12:28 Uhr Zürich. Zwischen dem 11. Oktober 14:36:44 und dem 12. Oktober 12:24:15 wurden 21 vollständige Stundenblöcke ausgewertet. Darin liegen 46 qualifizierte, mindestens 60 Sekunden getrennte Impulse. Das sind 46 Impulse, nicht 46 Blöcke. Der vorab gesetzte erste Berichtsschwellenwert von 30 Impulsen und drei Blöcken ist erreicht. Die Bilanz ist vorläufig.

| Angenommene Einstiegsverzögerung | Geschlossene Trades | Offene Positionen | Realisiertes Netto nach Gebühren, USD | Verlustuntergrenze, USD |
|---:|---:|---:|---:|---:|
| 100 ms | 278 | 7 | +89.46586 | +86.42679 |
| 250 ms | 193 | 6 | +32.27246 | +30.61872 |
| 500 ms | 142 | 5 | −9.71918 | −12.46517 |
| 1'000 ms | 125 | 8 | −29.24675 | −32.62715 |

Jeder Block und jede Variante starten separat mit 100 USD Paper-Kapital und 10 Anteilen. Verschiedene Verzögerungen werden nicht zu einem Portfolio addiert. Das Netto umfasst geschlossene Trades nach Gebühren. Die Verlustuntergrenze zieht die gebundenen Einstiegskosten der offenen Positionen ab, wenn diese wertlos auslaufen. Feste Verzögerungen sind Annahmen; tatsächliche Order- und Fill-Zeiten wurden nicht gemessen. Aus dem positiven 250-ms-Szenario folgt daher keine reale Profitabilität.

Quelle: Projekt `prediction-market-terminal`, Datei `outputs/cex_regimes/forward/aggregation.json`, SHA-256 `77be73a51b1c9babc48fabff6e5b624044cc83ded21837ba2129fc7b74c3810f`. Das ursprüngliche lokale Laufprotokoll ist `docs/research/cex_regime_forward.md`, das Auswertungsmodul `src/cex_regimes.py`. Die für die Karte benötigten Werte liegen im [portablen Snapshot](research_updates_2026-10-12.json). Der verlinkte `app/research_updates.py` bereitet diese eingefrorenen Werte zur Publikation auf; er ist nicht das ursprüngliche Replay-Modul. Roharchive und die weiterentwickelte lokale Ausführungskette sind nicht Teil dieser Veröffentlichung.
