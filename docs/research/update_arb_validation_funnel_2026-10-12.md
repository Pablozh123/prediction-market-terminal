# Arbitrage-Scanner: vom Rohkandidaten zur Validierung

Der Tagesbericht vom 26. September 2026 umfasst 24 Stunden. Von 335 Scanzyklen waren 278 erfolgreich und 57 fehlgeschlagen. Die Scanner meldeten 2'505 rohe Cross-Venue-YES/NO-Treffer, 838 rohe Negative-Risk-Treffer und 23 rohe Within-Market-Arbitrage-Treffer. In allen drei Familien wurden null Kandidaten validiert und null Paper-Trades ausgelöst.

Die Rohwerte sind Zählungen von Scan-Treffern, keine voneinander unabhängigen handelbaren Chancen. Insbesondere können dieselben Märkte und Quotes wiederholt erscheinen. Regelunterschiede, nicht passende Eventstruktur und zu kleiner Nettoabstand gehören zu den dokumentierten Ablehnungsgründen. Fehlgeschlagene Scanzyklen begrenzen die Abdeckung zusätzlich. Ein Quote-Forward-Replay misst Preisänderungen, keinen realisierten PnL.

Originalbericht: Projekt `prediction-alpha-bot`, Datei `docs/reports/daily-telegram-report-2026-09-26.md`, SHA-256 `184421e4088d60d12fb9cce614e7d3cb6011f1fb3f3e775a7c5c481e05f515f3`. Die Zahlen und Quellenzuordnung sind im [portablen Snapshot](research_updates_2026-10-12.json) festgehalten. `app/research_updates.py` ist nur der Publikationsadapter, nicht der ursprüngliche Scanner.
