# Book-Imbalance-Studie (2026-05-30)

Quelle: forward-clean-2026-05-30.db — 173 Tokens' 455'914 gefilterte Snapshots' 451'636 5-Minuten-Paare.

Filter: Spread <= 0.10, Mid in (0.02, 0.98), Top-5-Tiefe >= 50 USD, Forward-Join first snapshot in [H, 2H].

| Bucket | n | bewegt | Drift 5min (c) | Hit-Rate (bewegt) | Wilson lb95 |
|---|---|---|---|---|---|
| 0.0-0.2 | 434'762 | 13.9% | +0.00 | 48.3% | 47.9% |
| 0.2-0.4 | 2'654 | 11.0% | +0.03 | 39.5% | 34.1% |
| 0.4-0.6 | 12'624 | 11.1% | -0.01 | - | - |
| 0.6-0.8 | 1'590 | 14.5% | +0.04 | 62.8% | 56.4% |
| 0.8-1.0 | 6 | 16.7% | +0.01 | 100.0% | 20.6% |

Lesart: Buckets unter 0.5 gelten als Treffer bei negativem Drift, ueber 0.5 bei positivem; die neutrale Mitte (0.4-0.6) traegt keine Richtung. Die Trefferquote ist bedingt auf Paare mit Bewegung (auf duennen Maerkten ist der 5-Minuten-Drift meist exakt null).

Caveat Datenquelle (Mai-Capture): Die Snapshots stammen aus dem Arb-Scanner-Forward-Replay; das Universum sind Basket-/Arb-Legs und damit ask-lastige Buecher (Grossteil der Paare im Bucket 0.0-0.2). Das ist Selektions-Bias, kein Marktquerschnitt. Die saubere Wiederholung laeuft auf den Recorder-Daten (src/book_recorder.py, volumenstaerkste Maerkte, beide Tokens). Keine Handelsempfehlung.