# Buch-Abgleich Stream gegen REST (2026-07-31)

10 Tokens, 3 von 3 Runden verbunden, 40 Sekunden Stream je Runde, Toleranz 1 Tick.

Vergleiche 30, davon uebereinstimmend 30, abweichend 0, nicht vergleichbar 0. Uebereinstimmungsquote 100.0%, groesste Abweichung 0.0 Ticks, mittlere 0.00 Ticks.

## Warum das noetig ist

Polymarket sendet keine Sequenznummern. Auf Kalshi verraet eine Luecke im Zaehler, dass eine Nachricht verloren ging; auf Polymarket gibt es diesen Zaehler nicht. Ein verlorenes oder falsch angewendetes Update ist damit unsichtbar - das Buch driftet lautlos, und jeder Spread, jeder Mid und jede Imbalance daraus ist falsch, ohne dass ein Test oder ein Log das zeigt. Der Abgleich gegen das REST-Buch ist der einzige Weg, den das Protokoll offen laesst.

## Lesehilfe

Eine einzelne Abweichung beweist nichts: die beiden Beobachtungen liegen Millisekunden auseinander, und ein schnelles Buch bewegt sich in dieser Zeit voellig zu Recht. Aussagekraeftig ist die Form ueber die Zeit - ob Abweichung selten und voruebergehend ist oder haeufig und wachsend. Nur das Zweite ist ein Fehler, und nur eine Zeitreihe kann die beiden auseinanderhalten. Deshalb schreibt dieses Modul eine Reihe und behauptet nichts.

Read-only-Forschung, keine Handelsempfehlung.