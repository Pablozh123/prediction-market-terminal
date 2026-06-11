# Zusammenarbeit: Codex + Claude

Dieses Dokument ist das gemeinsame Arbeitsteilungs-Board. **Vor jedem Arbeitsbeginn lesen** und den eigenen Eintrag im Board aktualisieren. So arbeiten zwei Agenten ohne gemeinsames Gedächtnis trotzdem konfliktfrei zusammen. Koordinator ist der Mensch (chole).

## Regeln

1. **Branch-Namen** mit Besitzer: `codex/<feature>` bzw. `claude/<feature>`. `main` bleibt immer stabil und kompilierbar.
2. **`prediction_terminal.py` editiert immer nur EIN Agent gleichzeitig** — diese 10.000-Zeilen-Datei ist der Haupt-Konfliktpunkt bei Merges.
3. **Klein und häufig committen** — nach jedem abgeschlossenen Schritt. Ein Commit ist ein Rollback-Punkt.
4. **Sync nur über `main`** per Merge / Pull Request. Vor jedem Merge: `python -m py_compile` und Tests grün.
5. **Board-Disziplin:** eigenen Eintrag auf `in Arbeit` setzen, bevor man startet; auf `fertig` nach dem Merge.
6. Niemals `git add -A` blind — vorher `git status` prüfen (keine venv, kein zip, keine Daten).

## Rollen

| Agent | Ort | Verantwortung |
|---|---|---|
| **Codex** | Host (Windows) | Code & Features: UI-Seiten, `prediction_terminal.py`, API-Anbindung. Schreibt und committet auf dem Host. |
| **Claude** | Cowork | Code-Review (auf Diffs/Branches), Design-Specs für neue Features, Thesis-Texte in `docs/`, Tests. Schreibt in der Regel **nicht** direkt in die Code-Dateien. |

## Arbeits-Board

| Feature / Thema | Owner | Branch | Status | Notiz |
|---|---|---|---|---|
| Website-Features + Handoff | Codex | `codex/follow-traders-ui-split-fixes` | bereit fuer Claude-Review | aktueller Branch liegt 16 Commits vor `main`; siehe `docs/CLAUDE_HANDOFF.md` |
| Multi-Trader-Copytrading — Spec | Claude | `claude/multitrader-spec` | geplant | Design-Dokument für Codex |
| Multi-Trader-Copytrading — Umsetzung | Codex | `codex/multitrader` | wartet auf Spec | erst nach Spec-Merge starten |
| Code-Review: copy_trading + API-Layer | Claude | `claude/review` | geplant | Findings-Report in `docs/` |
| Thesis: Methodik & informationelle Effizienz | Claude | `claude/thesis-methodik` | geplant | nur `docs/`, kein Code-Konflikt |

## Sync-Workflow

1. Branch von aktuellem `main` ziehen: `git switch -c codex/<feature> main`
2. Arbeiten, klein committen, am Ende `python -m py_compile` + Tests laufen lassen.
3. Nach `main` bringen:
   - Mit GitHub-Remote: pushen und Pull Request öffnen (Claude reviewt den Diff).
   - Lokal ohne Remote: `git switch main && git merge --no-ff codex/<feature>`
4. Konflikte am Merge lösen. Faustregel: `prediction_terminal.py` gehört zu jedem Zeitpunkt nur einem Branch.
5. Board-Eintrag auf `fertig` setzen.

## Hinweis zu Claude-Zugriff

Claudes Datei-Cache kann in einer laufenden Session bei sehr grossen Dateien veralten. Für `prediction_terminal.py` und `src/prediction_markets.py` ist daher **Codex auf dem Host die verlässliche Quelle**. Claude reviewt diese Dateien am besten anhand von Git-Diffs oder in einer frischen Session.

## Scope-Grenze: Klon vs. Erweiterung

Es gibt zwei getrennte Schichten, die sich nicht widersprechen dürfen:

- **Referenz-Klon (Codex, abgeschlossen):** bildete die damalige Referenzseite nach — Features, Filter, Tools. Externe Referenz-Datenquellen wurden inzwischen vollständig durch Polymarket/Kalshi-Public-APIs ersetzt.
- **Multi-Trader-Copytrading (Erweiterung):** bewusst *über* den Klon hinaus (Spec: `docs/spec_multitrader_copytrading.md`), als eigene Seite/Modul, möglichst getrennt von den Klon-Teilen in `prediction_terminal.py`.

Regel: Während der Klon-Phase wird die Copytrading-Erweiterung **nicht** angefasst, und der Klon baut bestehendes Copytrading **nicht zurück**.

## Phasen

- **Phase 1 (abgeschlossen, Codex):** Referenz-Klon bis zu einem stabilen, nach `main` gemergten Meilenstein. Abschluss mit Tag `v1-clone`. In dieser Phase **keine** Multi-Trader-Arbeit.
- **Phase 2 (danach):** Multi-Trader-Copytrading laut Spec, als isolierte Schicht. Start **erst nach** `v1-clone`.

## Aktueller Handoff

Claude Desktop soll vor neuer Arbeit `docs/CLAUDE_HANDOFF.md` lesen. Der aktuelle Branch kann vor `main` liegen; immer `git status --short --branch` und `git log --oneline main..HEAD` pruefen.
