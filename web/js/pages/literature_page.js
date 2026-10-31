// Literature — die eigenen Messungen neben der veroeffentlichten Forschung:
// was die eigenen Daten zeigen, was drei unabhaengige Studien sagen, welche
// scheinbaren Anomalien schon erklaert sind, und die Rangfolge der
// Ertragspfade, die daraus folgt. Liest public/data/literature.json
// (app/literature_context.py aus docs/research/ertragsquellen_2026-07-31.md).

import { esc } from '../util.js';
import { diagramm } from '../charts.js';
import { MONO as M, KARTE } from '../ui.js';
import { MUTED, kicker, quelleLinks, seitenKopf, hinweisZeile, ohneNutzlastHtml } from './study_blocks.js';

const DATEI = 'literature.json';
const BEFEHL = 'python scripts/publish_research_pages.py --only literature';

function befundKarte(e) {
  return '<div style="' + KARTE + '; padding:var(--sp-5)">'
    + '<div style="font-size:var(--t-body); font-weight:600; color:var(--text); line-height:var(--lh-snug)">' + esc(e.titel) + '</div>'
    + '<div style="font-size:var(--t-small); color:var(--ink-2); margin-top:var(--sp-3); line-height:var(--lh-prose)">' + esc(e.text) + '</div>'
    + (e.studie ? '<a href="#research/microstructure/' + esc(e.studie) + '" style="' + M + '; font-size:var(--t-micro); color:var(--info); display:inline-block; margin-top:var(--sp-3)">study card ' + esc(e.studie) + ' →</a>' : '')
    + (e.quelle && !e.studie ? '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-4); margin-top:var(--sp-3)">' + esc(e.quelle) + '</div>' : '')
    + '</div>';
}

function literaturKarte(l) {
  return '<div style="' + KARTE + '; padding:var(--sp-5)">'
    + '<div style="' + M + '; font-size:var(--t-micro); letter-spacing:var(--ls-caps-strong); color:var(--ink-3)">' + esc(l.venue || '') + (l.stichprobe ? ' · ' + esc(l.stichprobe) : '') + '</div>'
    + '<div style="font-size:var(--t-body); font-weight:600; color:var(--text); margin-top:var(--sp-3); line-height:var(--lh-snug)">' + esc(l.autoren) + '</div>'
    + '<div style="font-size:var(--t-small); color:var(--ink-2); margin-top:var(--sp-3); line-height:var(--lh-prose)">' + esc(l.befund) + '</div>'
    + '<div style="' + M + '; font-size:var(--t-micro); color:var(--ink-4); margin-top:var(--sp-3)">' + esc(l.quelle) + '</div>'
    + '</div>';
}

function rangZeile(r) {
  return '<div style="display:grid; grid-template-columns:44px 1fr; gap:var(--sp-4); padding:var(--sp-4) 0; border-bottom:1px solid var(--line-3)">'
    + '<div style="' + M + '; font-size:var(--t-head); color:var(--ink-3)">' + esc(String(r.rang)) + '</div>'
    + '<div><div style="font-size:var(--t-body); font-weight:600; color:var(--text)">' + esc(r.pfad) + '</div>'
    + '<div style="' + M + '; font-size:var(--t-micro); color:var(--info); margin-top:var(--sp-2)">' + esc(r.stuetze) + '</div>'
    + '<div style="font-size:var(--t-small); color:var(--ink-2); margin-top:var(--sp-2); line-height:var(--lh-prose)">' + esc(r.text) + '</div></div></div>';
}

function raster(karten) {
  if (!karten.length) return '';
  return '<div style="display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:var(--sp-4)">' + karten.join('') + '</div>';
}

export function renderLiterature(payload, study) {
  if (!payload || !Array.isArray(payload.eigene) || !payload.eigene.length) return ohneNutzlastHtml(study, DATEI, BEFEHL, payload);
  const d = payload.diagramme || {};
  const bilder = [diagramm(d.edge_gegen_kosten), diagramm(d.wer_verliert)].filter(Boolean);
  const programm = payload.programm && payload.programm.text ? payload.programm : null;
  return '<div style="padding:var(--sp-6) var(--sp-6) var(--sp-7)">'
    + seitenKopf(study.title, payload.einleitung, study, payload)
    + hinweisZeile(payload.hinweis)
    + kicker('WHAT OUR OWN DATA SHOW')
    + raster(payload.eigene.map(befundKarte))
    + (bilder.length ? '<div style="display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:var(--sp-4); margin-top:var(--sp-4)">' + bilder.join('') + '</div>' : '')
    + kicker('WHAT THE LITERATURE SAYS')
    + raster((payload.literatur || []).map(literaturKarte))
    + kicker('ANOMALIES THAT ARE ALREADY EXPLAINED', 'var(--warn)')
    + raster((payload.anomalien || []).map(befundKarte))
    + (programm ? kicker('THE THIRD REVENUE STREAM') + raster([befundKarte(programm)]) : '')
    + kicker('WHERE POSITIVE EXPECTATION CAN COME FROM, RANKED BY THE DATA', 'var(--accent)')
    + '<div style="' + KARTE + '; padding:var(--sp-2) var(--sp-5)">' + (payload.rangfolge || []).map(rangZeile).join('') + '</div>'
    + (payload.grenzen ? kicker('LIMITS', 'var(--ink-3)') + '<div style="font-size:var(--t-body); color:var(--ink-2); line-height:var(--lh-prose); max-width:760px">' + esc(payload.grenzen) + '</div>' : '')
    + '<div style="margin-top:var(--sp-6); display:flex; align-items:center; justify-content:space-between; gap:var(--sp-5); flex-wrap:wrap">'
    + '<div style="' + M + '; font-size:var(--t-micro); ' + MUTED + '">as of ' + esc(payload.stand_text || '') + ' · every figure quoted from the note; the note\'s own figures come from the Microstructure studies linked above</div>'
    + quelleLinks([{ pfad: payload.report, text: 'FULL NOTE' }])
    + '</div></div>';
}
