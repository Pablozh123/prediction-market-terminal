// Die Studienliste: Reiterbeschriftung, Titel, Kurzbeschreibung, Stempel und
// Diagrammtitel. Nur Struktur, keine Ergebnisse — jede Zahl einer Studie
// kommt aus ihrer publizierten Nutzlast in public/data. Bis die da ist,
// zeigt die Seite den Leerzustand mit dem Dateinamen.

export const STUDIEN = [
  {
    tab: 'Review queue',
    title: 'Verification queue',
    stamp: 'frozen 2026-07-14',
    note: 'Cases the daily run flagged for a human to check, ranked by how much the automated read and the market disagree.',
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
    stamp: 'frozen 2026-06-30',
    note: 'Time between a piece of content going live and the market moving more than two cents.',
    chart: 'MINUTES TO FIRST MOVE'
  },
  {
    tab: 'Live runs',
    title: 'Our own bot runs',
    stamp: 'rolling',
    note: 'Every bet the research bot placed, with the latency it hit and how the sizing simulation would have done instead.',
    chart: 'EQUITY OF THE LIVE RUNS'
  },
  {
    tab: 'Microstructure',
    title: 'Order books, recorded',
    stamp: 'rolling',
    note: 'A rolling read on the collected books plus the frozen studies: imbalance, order flow net of costs, and market-maker PnL decomposition.',
    chart: 'BOOK IMBALANCE VS NEXT MOVE'
  },
  {
    tab: 'Pilot',
    title: 'Small-stake field test',
    stamp: 'pre-registered 2026-05-02',
    note: 'Rules were frozen before the first trade. Signals are read-only, every decision is manual, and rule adherence is logged per trade.',
    chart: 'PILOT EQUITY VS RULE ADHERENCE'
  },
  {
    tab: 'Pipeline forward',
    title: 'Forward test of the pipeline',
    stamp: 'rolling',
    note: 'The analysis pipeline runs forward with no intervention, so its record cannot be fitted after the fact.',
    chart: 'FORWARD PAPER EQUITY'
  },
  {
    tab: 'Methodology',
    title: 'Method, guardrails and audit',
    stamp: 'version 4.2',
    note: 'What each score means, what it does not mean, and how the audit trail is recorded.',
    chart: ''
  },
  {
    tab: 'Postmortems',
    title: 'What went wrong, and what changed because of it',
    stamp: 'rolling',
    note: 'Every incident the live runs produced, with what happened, what it cost, and the code that changed as a result.',
    chart: ''
  }
];
