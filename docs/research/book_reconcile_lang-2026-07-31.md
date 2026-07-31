# Buch-Abgleich Stream gegen REST (lang-2026-07-31)

24 Tokens, 8 von 8 Runden verbunden, 150 Sekunden Stream je Runde, Toleranz 1 Tick.

Vergleiche 178, davon uebereinstimmend 170, abweichend 8, nicht vergleichbar 0. Uebereinstimmungsquote 95.5%, groesste Abweichung 30.0 Ticks, mittlere 0.62 Ticks.

## Warum das noetig ist

Polymarket sendet keine Sequenznummern. Auf Kalshi verraet eine Luecke im Zaehler, dass eine Nachricht verloren ging; auf Polymarket gibt es diesen Zaehler nicht. Ein verlorenes oder falsch angewendetes Update ist damit unsichtbar - das Buch driftet lautlos, und jeder Spread, jeder Mid und jede Imbalance daraus ist falsch, ohne dass ein Test oder ein Log das zeigt. Der Abgleich gegen das REST-Buch ist der einzige Weg, den das Protokoll offen laesst.

## Lesehilfe

Eine einzelne Abweichung beweist nichts: die beiden Beobachtungen liegen Millisekunden auseinander, und ein schnelles Buch bewegt sich in dieser Zeit voellig zu Recht. Aussagekraeftig ist die Form ueber die Zeit - ob Abweichung selten und voruebergehend ist oder haeufig und wachsend. Nur das Zweite ist ein Fehler, und nur eine Zeitreihe kann die beiden auseinanderhalten. Deshalb schreibt dieses Modul eine Reihe und behauptet nichts.

Read-only-Forschung, keine Handelsempfehlung.