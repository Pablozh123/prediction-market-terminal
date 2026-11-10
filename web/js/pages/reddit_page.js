// Reddit sentiment — eine Studie, eine Karte: Frage, Verdikt, die Punktwolke
// der 29 Maerkte, die Balken je Subreddit und Kategorie, das Audit, dann die
// Methode zugeklappt. Liest public/data/reddit_sentiment.json
// (app/reddit_report.py). Jede Zahl aus der Datei.

import { esc } from '../util.js';
import { diagramm, punktwolke } from '../charts.js';
import { MONO as M, KARTE } from '../ui.js';
import {
  MUTED, HR, karteKopf, methodeBlock, zahlenBlock, quelleLinks, basisZeile, seitenKopf,
  hinweisZeile, ohneNutzlastHtml
} from './study_blocks.js';

const DATEI = 'reddit_sentiment.json';
const BEFEHL = 'python scripts/publish_research_pages.py --only reddit';

export function renderReddit(payload, study) {
  const s = payload && payload.studie;
  if (!s || !s.frage) return ohneNutzlastHtml(study, DATEI, BEFEHL, payload);
  const d = s.diagramme || {};
  const wolke = punktwolke(d.streuung);
  const balken = [diagramm(d.subreddits), diagramm(d.kategorien), diagramm(d.audit)].filter(Boolean);
  return '<div style="padding:var(--sp-6) var(--sp-6) var(--sp-7)">'
    + seitenKopf(study.title, payload.einleitung, study, payload)
    + hinweisZeile(payload.hinweis)
    + '<div style="height:20px"></div>'
    + '<div id="research/reddit-sentiment/study" style="' + KARTE + '; padding:var(--sp-6); margin-bottom:var(--sp-5)">'
    + karteKopf('STUDY · REDDIT × POLYMARKET, LIVE RUN ' + esc(String((s.basis || {}).fenster || '')), s.frage, s.verdikt, s.verdikt_art)
    + (wolke ? '<div style="margin-top:var(--sp-5)">' + wolke + '</div>' : '')
    + (balken.length ? '<div style="display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:var(--sp-4); margin-top:var(--sp-4)">' + balken.join('') + '</div>' : '')
    + '<div style="margin-top:var(--sp-5)">' + zahlenBlock(s.zahlen) + '</div>'
    + methodeBlock(s, 'reddit')
    + '<div style="' + HR + '; display:flex; align-items:center; justify-content:space-between; gap:var(--sp-5); flex-wrap:wrap">'
    + basisZeile(s.basis)
    + quelleLinks([{ pfad: s.report, text: 'REPORT TABLES' }, { pfad: s.modul, text: 'SOURCE MODULE' }])
    + '</div></div>'
    + '<div style="font-size:var(--t-small); ' + MUTED + '; line-height:var(--lh-prose); max-width:760px">'
    + 'The market-level correlations are recomputed from the market table in this repository; the subreddit, category and stance figures come from the report, whose post-level data are not republished. '
    + '<span style="' + M + '">' + esc(String(s.report || '')) + '</span></div>'
    + '</div>';
}
