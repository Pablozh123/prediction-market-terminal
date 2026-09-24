import assert from 'node:assert/strict';
import { renderFed, chart, pointAt, comparePoints } from '../web/js/pages/fed_page.js';
import { kalibrierung } from '../web/js/charts.js';

assert.equal(pointAt([{t: 10, p: .2}, {t: 30, p: .9}], 20, 15).p, .2);
assert.equal(pointAt([{t: 10, p: .2}], 30, 15), null);
const state = {fedMeeting: '2026-09-16', fedOutcome: 'hike25', fedWindow: 7};
const m = {date: '2026-09-16', decision_ts: 1000000, actual: 'hike25', baseline_upper_bps: 375,
  comparable_after: 0, buckets: [{key: 'hike25', label: '25 bps increase'}],
  polymarket: {hike25: [{t: 900000, p: .8}, {t: 950000, p: .9}]},
  cme: [{t: 900000, probabilities: {hike25: .7}}], issues: ['<script>bad()</script>']};
assert.equal(comparePoints(m, 'hike25')[0].p, 10.000000000000009);
const T = {state, liveData: {}, act: () => '', inp: () => '', setState: () => {}};
assert.match(renderFed(T), /No comparison data/);
const actions = [];
let reloads = 0;
T.act = fn => { actions.push(fn); return ''; };
T.neuLaden = key => { assert.equal(key, 'fed'); reloads++; };
renderFed(T);
actions.at(-1)();
assert.equal(reloads, 1);
T.liveData.fed = {meetings: [m], generated_at: '2026-09-24T00:00:00Z', evaluation: []};
const html = renderFed(T);
assert.match(html, /30 days/);
assert.match(html, /7 days/);
assert.match(html, /1 day/);
assert.match(html, /&lt;script&gt;/);
assert.doesNotMatch(html, /<script>/);
assert.match(html, /CME FedWatch/);
assert.match(chart([{name:'a', points: [{t: 900000,p:.5}], color:'var(--s1)', maxAge:7200}], 1000000, 1, false), /No observations/);
assert.match(chart([{name:'a', points: [{t: 990000,p:.5}], color:'var(--s1)', maxAge:7200}], 1000000, 1, false), /T−24h/);
assert.doesNotMatch(kalibrierung({punkte:[{vorhergesagt:.8,realisiert:1,n:4,ci:false}]}), /stroke-opacity=".45"/);
console.log('Fed rendering, time windows, gaps and escaping passed');
