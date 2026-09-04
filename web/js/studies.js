// Die Studienliste: Reiterbeschriftung, Titel, Kurzbeschreibung, Stempel und
// Diagrammtitel. Nur Struktur, keine Ergebnisse — jede Zahl einer Studie
// kommt aus ihrer publizierten Nutzlast in public/data. Bis die da ist,
// zeigt die Seite den Leerzustand mit dem Dateinamen.

export const STUDIEN = [
  // Archiviert: nicht mehr in der Seitenleiste, aber per #research/review-queue
  // erreichbar — die Zaehler stehen auf der Methodology-Seite.
  {
    tab: 'Review queue',
    title: 'Verification queue',
    stamp: 'frozen 2026-07-14 · archived',
    note: 'Cases the daily run flagged for a human to check, ranked by how much the automated read and the market disagree. The daily run ended 2026-08-07; the counters live on the Methodology page.',
    chart: 'CASES PER DAY'
  },
  {
    tab: 'Category efficiency',
    title: 'Which categories price things well',
    stamp: 'frozen 2026-06-30',
    note: 'Brier score against how many minutes a category needs to price in new information. Lower is better on both axes.',
    chart: 'BRIER SCORE BY CATEGORY'
  },
  {
    tab: 'Mentions latency',
    title: 'How fast mentions markets react',
    stamp: 'frozen 2026-08-07',
    note: 'Time between a piece of content going live and the market first standing more than one point off its pre-drop price.',
    chart: 'MINUTES TO FIRST MOVE'
  },
  // "rolling" war unwahr geworden: der letzte Publish ist vom 2026-08-07 und
  // kein Einsatz ist offen. Ein abgeschlossener Track Record ist das
  // staerkere Argument als ein toter Live-Stempel.
  {
    tab: 'Live runs',
    title: 'Our own bot runs',
    stamp: 'concluded 2026-08-07',
    note: 'Every bet the research bot placed, with the latency it hit and how the sizing simulation would have done instead. All positions are resolved; the forward paper log of the same pipeline is summarized below.',
    chart: 'EQUITY OF THE LIVE RUNS'
  },
  {
    tab: 'Microstructure',
    title: 'Order books, recorded',
    stamp: 'rolling',
    note: 'A rolling read on the collected books plus the frozen studies: imbalance, order flow net of costs, and market-maker PnL decomposition.',
    chart: 'BOOK IMBALANCE VS NEXT MOVE'
  },
  // Das Handelsfenster endete per Protokoll am 2026-08-01 — der Pilot ist ein
  // fertiges Beweisstueck, kein laufender Test.
  {
    tab: 'Pilot',
    title: 'Small-stake field test',
    stamp: 'pre-registered 2026-05-02 · completed 2026-08-01',
    note: 'Rules were frozen before the first trade. Signals are read-only, every decision is manual, and rule adherence is logged per trade. The trading window closed 2026-08-01.',
    chart: 'PILOT EQUITY VS RULE ADHERENCE'
  },
  // Archiviert: der Papier-Zwilling der Live runs (dieselbe Pipeline, gleiche
  // Laeufe). Zusammengefasst auf der Live-runs-Seite; die volle Seite bleibt
  // per #research/pipeline-forward erreichbar.
  {
    tab: 'Pipeline forward',
    title: 'Forward test of the pipeline',
    stamp: 'paper log · archived 2026-08-07',
    note: 'The word-count pipeline in watch mode: it reads the live transcript and logs, for every market, whether its rules would have allowed a bet — mostly they would not. No intervention, so the record cannot be fitted after the fact. Summarized on the Live runs page.',
    chart: 'FORWARD PAPER EQUITY'
  },
  {
    tab: 'Methodology',
    title: 'Method, guardrails and audit',
    stamp: 'version 4.2',
    note: 'What each score means, what it does not mean, and how the audit trail is recorded.',
    chart: ''
  },
  // Kuratiert, nicht "rolling": die Sammlung veraltet nicht, aber sie waechst
  // auch nur, wenn jemand einen Vorfall schreibt.
  {
    tab: 'Postmortems',
    title: 'What went wrong, and what changed because of it',
    stamp: 'curated',
    note: 'Every incident the live runs produced, with what happened, what it cost, and the code that changed as a result.',
    chart: ''
  },
  // Slug 'field-notes' (aus dem Reiter abgeleitet), Nutzlast field_notes.json.
  // Kuratierte Beobachtungen, keine Messreihe — deshalb kein Diagrammtitel.
  {
    tab: 'Field notes',
    title: 'Field notes — what the tape taught us',
    stamp: 'curated',
    note: 'Curated observations from watching the tape: what happened, the mechanism behind it, and what follows from it. Each note names its evidence or says it has none.',
    chart: ''
  }
];
