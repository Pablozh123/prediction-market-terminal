# Streamed book reconciled against REST (lang-2026-07-31)

24 tokens, 8 of 8 rounds connected, 150 seconds of streaming per round, tolerance 1 tick.

Comparisons 178, of which matching 170, diverging 8, not comparable 0. Agreement rate 95.5%, largest divergence 30.0 ticks, mean 0.62 ticks.

## Why this is necessary

Polymarket sends no sequence numbers. On Kalshi a gap in the counter reveals that a message was lost; on Polymarket there is no such counter. A dropped or misapplied update is therefore invisible: the book drifts silently, and every spread, mid and imbalance derived from it is wrong without any test or log showing it. Reconciling against the REST book is the only route the protocol leaves open.

## How to read this

A single divergence proves nothing. The two observations lie milliseconds apart, and a fast book moves in that time entirely legitimately. What carries meaning is the shape over time: whether divergence is rare and transient or frequent and growing. Only the second is a defect, and only a time series can tell the two apart. That is why this module records a series and asserts nothing.

Read-only research. Not trading advice.