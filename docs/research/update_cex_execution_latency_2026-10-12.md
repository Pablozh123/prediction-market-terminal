# CEX: Verzögerung beim Ein- und Ausstieg

Publizierter Ergebnisstand vom 12. Oktober 2026. Der zugrunde liegende
Belastungstest vom 11. Oktober verwendet sechs bereits gesehene Stundenblöcke
zwischen 14:36:44 und 20:43:02 Uhr Zürich. Er ist eine Sensitivitätsanalyse,
kein neuer unabhängiger Forward-Test.

| Angenommene Verzögerung Einstieg/Ausstieg | Geschlossene Trades | Offen | Netto geschlossen nach Gebühren, USD | Verlustuntergrenze, USD |
|---|---:|---:|---:|---:|
| 350/350 ms | 59 | 1 | +5.17888 | +5.09332 |
| 500/500 ms | 47 | 3 | −5.53763 | −7.71884 |
| 1'000/1'000 ms | 46 | 3 | −16.08475 | −18.07811 |

Die Tabelle zeigt jeweils die unveränderte Basis über alle sechs Blöcke.
Jeder Block und jede Variante starten separat mit 100 USD Paper-Kapital und
10 Anteilen. Die Untergrenze zieht den gebundenen Einstiegseinsatz offener
Positionen ab, falls diese wertlos auslaufen. Es ist kein durchgehend
finanziertes Gesamtkonto. Sichtbare Tiefe erlaubt eine optimistische
Fill-Annahme; eigene Order- und Fill-Zeiten wurden nicht gemessen.

Im 250-ms-Basisarm lagen erst 23 qualifizierende, mindestens 60 Sekunden
getrennte Impulse vor. Die positiven 350-ms- und negativen langsameren
Szenarien zeigen die Empfindlichkeit gegenüber Ausführungsannahmen. Sie
belegen weder einen dauerhaften Vorteil noch die tatsächlich erreichbare
Orderlatenz. Im Originalbericht werden weitere, teils nur fünf Blöcke
umfassende Referenzvergleiche berichtet. Diese werden hier nicht mit den
sechs Basisblöcken vermischt.

Originalquellen im Projekt `prediction-market-terminal`:
`outputs/cex_regimes/execution_latency_2026-10-11/aggregation.json`,
SHA-256 `b4f4f6b7ed14dae9c8a113b11f97ea8c5fc9f2dcc11505ab2e8162faef4e54da`,
und `docs/research/cex_execution_latency_2026-10-11.md`,
SHA-256 `028712466e4f8d910bbb31056bbbac368b6fa17f744b9a74fec09075daaf1999`.
Das ursprüngliche lokale Replay-Modul ist `scripts/cex_execution_backtest.py`.
Die publizierten Werte und Quellenprüfsummen stehen im
[portablen Snapshot](research_updates_2026-10-12.json). Der verlinkte
`app/research_updates.py` ist der Publikationsadapter. Roharchive und die
lokale Ausführungskette sind nicht Teil dieser Veröffentlichung.
