# Wo sitzt die Kante? Segmentierung (july-2026)

Quelle: data/microstructure (REST, 120s-Raster), Signal imbalance mit Schwelle 0.65, Horizont 300s, 205,835 Firings an 11 Tagen (2026-07-18 bis 2026-07-28). Gebuehrenstand 2026-07-30.

Alle Schnitte sind ex ante bekannt: Spread und Preis stehen beim Entscheiden im Buch, die Signalstaerke ergibt sich aus dem Signal selbst, die Gebuehrenkategorie aus dem Markt. Kein Schnitt benutzt etwas, das erst hinterher bekannt ist.

## Gebuehrenkategorie sports (Rate 0.05)

Gesamt: netto -2.498 Cents je Signal, brutto +0.086, netto positiv in 3.8% der Faelle. Getestete Segmente: 34.

### Schnitt: spread

| Bucket | n | Brutto | Netto | Netto in-sample | Netto out-of-sample | CI95 | duenn |
|---|---|---|---|---|---|---|---|
| 0-0.5c | 62,082 | +0.075 | -1.635 | -1.724 | -1.468 | (-1.7802, -1.4673) | nein |
| 0.5-1c | 13,601 | +0.105 | -2.184 | -2.245 | -2.077 | (-2.344, -2.0253) | nein |
| 1-2c | 110,067 | +0.096 | -2.624 | -2.582 | -2.669 | (-2.7286, -2.5312) | nein |
| 2-5c | 17,443 | +0.156 | -4.022 | -4.123 | -3.904 | (-4.2407, -3.8604) | nein |
| 5-10.1c | 2,642 | -0.647 | -9.113 | -8.959 | -9.242 | (-9.7161, -8.5375) | nein |

### Schnitt: price

| Bucket | n | Brutto | Netto | Netto in-sample | Netto out-of-sample | CI95 | duenn |
|---|---|---|---|---|---|---|---|
| 0.05-0.15 | 35,353 | -0.012 | -1.715 | -1.673 | -1.777 | (-1.8601, -1.6003) | nein |
| 0.15-0.35 | 41,048 | +0.064 | -2.721 | -2.781 | -2.646 | (-2.8028, -2.654) | nein |
| 0.35-0.65 | 51,315 | +0.152 | -3.345 | -3.178 | -3.549 | (-3.4919, -3.1551) | nein |
| 0.65-0.85 | 41,434 | +0.104 | -2.676 | -2.725 | -2.613 | (-2.758, -2.6074) | nein |
| 0.85-0.95 | 36,685 | +0.090 | -1.619 | -1.584 | -1.666 | (-1.7126, -1.538) | nein |

### Schnitt: strength

| Bucket | n | Brutto | Netto | Netto in-sample | Netto out-of-sample | CI95 | duenn |
|---|---|---|---|---|---|---|---|
| 0.65-0.75 | 66,898 | +0.082 | -2.540 | -2.461 | -2.640 | (-2.6612, -2.4201) | nein |
| 0.75-0.85 | 59,388 | +0.062 | -2.470 | -2.387 | -2.590 | (-2.6045, -2.3357) | nein |
| 0.85-0.95 | 63,696 | +0.098 | -2.471 | -2.484 | -2.456 | (-2.5795, -2.3731) | nein |
| 0.95-1.01 | 15,853 | +0.141 | -2.543 | -2.506 | -2.622 | (-2.8185, -2.2577) | nein |

### Kandidaten

Keine. Von 34 getesteten Segmenten ueberlebt keines gleichzeitig die In-sample- und die Out-of-sample-Bedingung bei ausreichender Fallzahl.

## Gebuehrenkategorie politics (Rate 0.04)

Gesamt: netto -2.169 Cents je Signal, brutto +0.086, netto positiv in 4.2% der Faelle. Getestete Segmente: 34.

### Schnitt: spread

| Bucket | n | Brutto | Netto | Netto in-sample | Netto out-of-sample | CI95 | duenn |
|---|---|---|---|---|---|---|---|
| 0-0.5c | 62,082 | +0.075 | -1.327 | -1.403 | -1.185 | (-1.4555, -1.1821) | nein |
| 0.5-1c | 13,601 | +0.105 | -1.862 | -1.916 | -1.767 | (-2.0035, -1.7204) | nein |
| 1-2c | 110,067 | +0.096 | -2.287 | -2.251 | -2.325 | (-2.3797, -2.2059) | nein |
| 2-5c | 17,443 | +0.156 | -3.669 | -3.765 | -3.556 | (-3.8803, -3.5123) | nein |
| 5-10.1c | 2,642 | -0.647 | -8.747 | -8.602 | -8.869 | (-9.3611, -8.1637) | nein |

### Schnitt: price

| Bucket | n | Brutto | Netto | Netto in-sample | Netto out-of-sample | CI95 | duenn |
|---|---|---|---|---|---|---|---|
| 0.05-0.15 | 35,353 | -0.012 | -1.542 | -1.500 | -1.605 | (-1.6842, -1.4323) | nein |
| 0.15-0.35 | 41,048 | +0.064 | -2.353 | -2.404 | -2.288 | (-2.4325, -2.286) | nein |
| 0.35-0.65 | 51,315 | +0.152 | -2.859 | -2.692 | -3.063 | (-3.0056, -2.6695) | nein |
| 0.65-0.85 | 41,434 | +0.104 | -2.307 | -2.348 | -2.255 | (-2.3875, -2.2405) | nein |
| 0.85-0.95 | 36,685 | +0.090 | -1.447 | -1.410 | -1.496 | (-1.5445, -1.3685) | nein |

### Schnitt: strength

| Bucket | n | Brutto | Netto | Netto in-sample | Netto out-of-sample | CI95 | duenn |
|---|---|---|---|---|---|---|---|
| 0.65-0.75 | 66,898 | +0.082 | -2.200 | -2.122 | -2.298 | (-2.3125, -2.0894) | nein |
| 0.75-0.85 | 59,388 | +0.062 | -2.145 | -2.070 | -2.255 | (-2.2667, -2.0241) | nein |
| 0.85-0.95 | 63,696 | +0.098 | -2.148 | -2.154 | -2.142 | (-2.2512, -2.0593) | nein |
| 0.95-1.01 | 15,853 | +0.141 | -2.216 | -2.167 | -2.317 | (-2.4634, -1.9576) | nein |

### Kandidaten

Keine. Von 34 getesteten Segmenten ueberlebt keines gleichzeitig die In-sample- und die Out-of-sample-Bedingung bei ausreichender Fallzahl.

## Gebuehrenkategorie geopolitics (Rate 0.0)

Gesamt: netto -0.853 Cents je Signal, brutto +0.086, netto positiv in 8.4% der Faelle. Getestete Segmente: 34.

### Schnitt: spread

| Bucket | n | Brutto | Netto | Netto in-sample | Netto out-of-sample | CI95 | duenn |
|---|---|---|---|---|---|---|---|
| 0-0.5c | 62,082 | +0.075 | -0.097 | -0.122 | -0.051 | (-0.1499, -0.0408) | nein |
| 0.5-1c | 13,601 | +0.105 | -0.574 | -0.599 | -0.530 | (-0.6405, -0.5015) | nein |
| 1-2c | 110,067 | +0.096 | -0.936 | -0.926 | -0.948 | (-0.9797, -0.8902) | nein |
| 2-5c | 17,443 | +0.156 | -2.256 | -2.333 | -2.167 | (-2.4459, -2.1237) | nein |
| 5-10.1c | 2,642 | -0.647 | -7.285 | -7.175 | -7.376 | (-7.9073, -6.6446) | nein |

### Schnitt: price

| Bucket | n | Brutto | Netto | Netto in-sample | Netto out-of-sample | CI95 | duenn |
|---|---|---|---|---|---|---|---|
| 0.05-0.15 | 35,353 | -0.012 | -0.852 | -0.808 | -0.917 | (-0.9927, -0.7459) | nein |
| 0.15-0.35 | 41,048 | +0.064 | -0.880 | -0.897 | -0.859 | (-0.9654, -0.8007) | nein |
| 0.35-0.65 | 51,315 | +0.152 | -0.914 | -0.746 | -1.119 | (-1.0606, -0.7291) | nein |
| 0.65-0.85 | 41,434 | +0.104 | -0.834 | -0.841 | -0.824 | (-0.9177, -0.7498) | nein |
| 0.85-0.95 | 36,685 | +0.090 | -0.758 | -0.714 | -0.817 | (-0.8655, -0.6793) | nein |

### Schnitt: strength

| Bucket | n | Brutto | Netto | Netto in-sample | Netto out-of-sample | CI95 | duenn |
|---|---|---|---|---|---|---|---|
| 0.65-0.75 | 66,898 | +0.082 | -0.840 | -0.767 | -0.933 | (-0.9094, -0.7649) | nein |
| 0.75-0.85 | 59,388 | +0.062 | -0.848 | -0.800 | -0.917 | (-0.9229, -0.776) | nein |
| 0.85-0.95 | 63,696 | +0.098 | -0.857 | -0.834 | -0.883 | (-0.9313, -0.7852) | nein |
| 0.95-1.01 | 15,853 | +0.141 | -0.906 | -0.814 | -1.099 | (-1.0848, -0.7201) | nein |

### Kandidaten (positiv in-sample UND out-of-sample, nicht duenn)

| Segment | n | Netto | out-of-sample | CI95 |
|---|---|---|---|---|
| spread x strength: 0-0.5c x 0.95-1.01 | 6,323 | +0.008 | +0.438 | (-0.1124, 0.2033) |

## Lesehilfe

Die Spalte out-of-sample ist die einzige, die zaehlt. Ein Segment, das nur in-sample positiv ist, ist genau das, was Data Mining gratis liefert: bei genuegend vielen Schnitten sieht immer irgendeiner gut aus. Die Zahl der getesteten Segmente steht deshalb im Kopf jedes Abschnitts, damit die Auswahlwahrscheinlichkeit sichtbar bleibt.

Die Gebuehrenkategorien sind das schaerfste Instrument in dieser Tabelle, weil sie denselben Datensatz unter verschiedenen Kosten zeigen. Geopolitik ist gebuehrenfrei, dort bleibt als Kosten nur der Spread. Bleibt die Kante auch dort negativ, liegt es nicht an den Gebuehren, sondern daran, dass die Bewegung zu klein ist.

Duenne Segmente sind markiert und aus der Kandidatenliste ausgeschlossen, aber absichtlich mit abgedruckt: ein Segment mit 40 Beobachtungen und grosser Zahl ist kein Fund, sondern Rauschen, und das soll man sehen statt es wegzulassen.

Read-only-Forschung, keine Handelsempfehlung.