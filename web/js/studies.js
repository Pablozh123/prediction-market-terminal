// Die Studienliste: Reiterbeschriftung, Titel, Kurzbeschreibung und Stempel.
// Nur Struktur, keine Ergebnisse — jede Zahl einer Studie
// kommt aus ihrer publizierten Nutzlast in public/data. Bis die da ist,
// zeigt die Seite den Leerzustand mit dem Dateinamen.

// Adresssegment einer Studie: die Reiterbeschriftung in Kleinbuchstaben,
// Leerzeichen als Bindestrich. Das ist die kanonische Form, die die Adresse
// traegt.
export function studienSlug(study) {
  return String((study && study.tab) || '').toLowerCase().replace(/ /g, '-');
}

// Zum Vergleich wird jede Trennung weggelassen. Der Eintrag in der
// Seitenleiste heisst "Post-mortems", die Studie aber "Postmortems", also
// ist "#research/post-mortems" genau die Adresse, die jemand tippt, der die
// Beschriftung abschreibt. Sie zeigte auf keine Studie, und die Seite blieb
// dann still auf dem vorigen Reiter stehen: die Adresse sagte das eine, die
// Seite zeigte das andere. Verglichen wird deshalb ohne Trennzeichen.
function vergleichbar(wert) {
  return String(wert || '').toLowerCase().replace(/[^a-z0-9]/g, '');
}

/** Index der Studie zu einem Adresssegment, oder -1.
 *
 *  Bindestriche, Unterstriche und Leerzeichen spielen keine Rolle; die
 *  kanonische Adresse bleibt die aus studienSlug.
 */
export function studienIndexAus(studien, slug) {
  const gesucht = vergleichbar(slug);
  if (!gesucht) return -1;
  const liste = Array.isArray(studien) ? studien : [];
  for (let i = 0; i < liste.length; i += 1) {
    if (vergleichbar(studienSlug(liste[i])) === gesucht) return i;
  }
  return -1;
}

export const STUDIEN = [
  // Archiviert: nicht mehr in der Seitenleiste, aber per #research/review-queue
  // erreichbar — die Zaehler stehen auf der Methodology-Seite.
  {
    tab: 'Review queue',
    title: 'Verification queue',
    stamp: 'frozen 2026-07-14 · archived',
    note: 'Cases the daily run flagged for a human to check, ranked by how much the automated read and the market disagree. The daily run ended 2026-08-07; the counters live on the Methodology page.'
  },
  {
    tab: 'Category efficiency',
    title: 'Which categories price things well',
    stamp: 'frozen 2026-06-30',
    note: 'Brier score against how many minutes a category needs to price in new information. Lower is better on both axes.'
  },
  {
    tab: 'Mentions latency',
    title: 'How fast mentions markets react',
    stamp: 'frozen 2026-08-07',
    note: 'Time between a piece of content going live and the market first standing more than one point off its pre-drop price.'
  },
  // "rolling" war unwahr geworden: der letzte Publish ist vom 2026-08-07 und
  // kein Einsatz ist offen. Ein abgeschlossener Track Record ist das
  // staerkere Argument als ein toter Live-Stempel.
  {
    tab: 'Live runs',
    title: 'Our own bot runs',
    stamp: 'concluded 2026-08-07',
    note: 'Every bet the research bot placed, with the latency it hit and how the sizing simulation would have done instead. All positions are resolved; the forward paper log of the same pipeline is summarized below.'
  },
  {
    tab: 'Microstructure',
    title: 'Order books, recorded',
    stamp: 'rolling',
    note: 'A rolling read on the collected books plus the frozen studies: imbalance, order flow net of costs, and market-maker PnL decomposition.'
  },
  // Das Handelsfenster endete per Protokoll am 2026-08-01 — der Pilot ist ein
  // fertiges Beweisstueck, kein laufender Test.
  {
    tab: 'Pilot',
    title: 'Small-stake field test',
    stamp: 'pre-registered 2026-05-02 · completed 2026-08-01',
    note: 'Rules were frozen before the first trade. Signals are read-only, every decision is manual, and rule adherence is logged per trade. The trading window closed 2026-08-01.'
  },
  // Archiviert: der Papier-Zwilling der Live runs (dieselbe Pipeline, gleiche
  // Laeufe). Zusammengefasst auf der Live-runs-Seite; die volle Seite bleibt
  // per #research/pipeline-forward erreichbar.
  {
    tab: 'Pipeline forward',
    title: 'Forward test of the pipeline',
    stamp: 'paper log · archived 2026-08-07',
    note: 'The word-count pipeline in watch mode: it reads the live transcript and logs, for every market, whether its rules would have allowed a bet — mostly they would not. No intervention, so the record cannot be fitted after the fact. Summarized on the Live runs page.'
  },
  {
    tab: 'Methodology',
    title: 'Method, guardrails and audit',
    stamp: 'version 4.2',
    note: 'What each score means, what it does not mean, and how the audit trail is recorded.'
  },
  // Kuratiert, nicht "rolling": die Sammlung veraltet nicht, aber sie waechst
  // auch nur, wenn jemand einen Vorfall schreibt.
  {
    tab: 'Postmortems',
    title: 'What went wrong, and what changed because of it',
    stamp: 'curated',
    note: 'Every incident the live runs produced, with what happened, what it cost, and the code that changed as a result.'
  },
  // Slug 'field-notes' (aus dem Reiter abgeleitet), Nutzlast field_notes.json.
  // Kuratierte Beobachtungen, keine Messreihe.
  {
    tab: 'Field notes',
    title: 'Field notes — what the tape taught us',
    stamp: 'curated',
    note: 'Curated observations from watching the tape: what happened, the mechanism behind it, and what follows from it. Each note names its evidence or says it has none.'
  },
  // ---- In Vorbereitung (preview: true) ----------------------------------
  // Gebaut, geprueft, noch nicht freigeschaltet: die Seitenleiste listet sie
  // nur mit ?preview=1 (web/js/preview.js), die Suche findet sie dann, und
  // ihre Adresse zeigt sonst die Sperrkarte. Freischalten heisst: das
  // preview-Feld entfernen. Neue Eintraege gehoeren ans Ende der Liste,
  // renderResearch und RESEARCH_DATEI in system_pages.js haengen am Index.
  {
    tab: 'Thesis',
    title: 'The thesis: Polymarket against the polls, US 2024',
    stamp: 'thesis 2026 · frozen',
    note: 'Three hypotheses about one election, forecast quality, event reaction and wallet timing, plus a Swiss referendum as the case outside the US. Every number from the thesis result tables.',
    preview: true
  },
  {
    tab: 'Reddit sentiment',
    title: 'Does Reddit mood track Polymarket prices?',
    stamp: 'frozen 2026-05-22 · negative result',
    note: 'Twenty-nine live markets, 725 Reddit posts, two text models. No measurable link, and an audit of the retrieved posts that says why.',
    preview: true
  },
  {
    tab: 'Pre-registrations',
    title: 'Tests whose rules were written down first',
    stamp: 'register · rolling',
    note: 'The pilot, the queue-position study on market making and the track-record validation: hypothesis, success rule and where each stands. A test window still open shows training numbers only.',
    preview: true
  },
  {
    tab: 'Literature',
    title: 'Own measurement against the published research',
    stamp: 'as of 2026-07-31',
    note: 'What the recorded books show, what three independent studies found on far larger samples, which anomalies are already explained, and the revenue paths the data rank.',
    preview: true
  }
];
