import { esc } from '../util.js';
import { kalibrierung } from '../charts.js';

const DAY = 86400;
const percent = p => Number.isFinite(p) ? (p * 100).toFixed(1) + '%' : 'No data';
const score = p => Number.isFinite(p) ? p.toFixed(4) : 'Not comparable';
const utc = t => Number.isFinite(t) ? new Date(t * 1000).toISOString().slice(0, 16).replace('T', ' ') + ' UTC' : 'No data';
const dateLabel = date => String(date).split('-').reverse().join('.');
const bucketLabel = b => b.key === 'hold' ? 'No change' : (b.min == null ? '−' + Math.abs(b.max) + '+' : b.min < 0 ? '−' + Math.abs(b.min) : '+' + b.min + (b.max == null ? '+' : '')) + ' bp';
const external = (url, label) => /^https:\/\/(www\.federalreserve\.gov|polymarket\.com|www\.cmegroup\.com|www\.spf\.com\.tw)\//.test(url || '') ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label)} ↗</a>` : '';

export function pointAt(points, t, maxAge) {
  let lo = 0, hi = points.length;
  while (lo < hi) { const mid = (lo + hi) >> 1; if (points[mid].t <= t) lo = mid + 1; else hi = mid; }
  const p = points[lo - 1];
  return p && t - p.t <= maxAge ? p : null;
}

export function comparePoints(m, outcome) {
  if (m.comparable_after == null) return [];
  return (m.cme || []).filter(c => c.t >= m.comparable_after && c.t < m.decision_ts).flatMap(c => {
    const p = pointAt(m.polymarket[outcome] || [], c.t, 7200);
    const value = c.probabilities[outcome];
    return p && Number.isFinite(value) ? [{t: c.t, p: (p.p - value) * 100, pm: p.p, cme: value, pm_t: p.t}] : [];
  });
}

// Time is measured in seconds, so the window really rescales the x-axis.
// Step lines carry an observation only to the next point or its age limit.
export function chart(series, decision, days, spread = false) {
  const start = decision - days * DAY, end = Math.min(decision, Date.now() / 1000);
  const visible = series.map(s => ({...s, points: s.points.filter(p => Number.isFinite(p.p) && p.t < decision && p.t <= end && p.t >= start - s.maxAge)}));
  if (!visible.some(s => s.points.some(p => p.t + s.maxAge >= start))) return '<div class="fed-empty">No observations in this window. For upcoming meetings, the window may not have started yet. Choose “Full history” to see the available data.</div>';
  const W = 960, H = spread ? 180 : 330, L = 52, R = 944, B = H - 38, TOP = 20;
  const max = spread ? Math.max(5, ...visible.flatMap(s => s.points.map(p => Math.abs(p.p)))) * 1.15 : 100;
  const min = spread ? -max : 0;
  const x = t => L + (t - start) / (days * DAY) * (R-L);
  const y = p => B - ((spread ? p : p * 100) - min) / (max-min) * (B-TOP);
  let svg = '';
  for (let i = 0; i <= 4; i++) {
    const v = min + (max-min) * i/4, yy = B-(B-TOP)*i/4;
    svg += `<line x1="${L}" x2="${R}" y1="${yy}" y2="${yy}" class="fed-grid"/><text x="${L-10}" y="${yy+4}" text-anchor="end">${spread ? v.toFixed(1) : v.toFixed(0)}${spread ? '' : '%'}</text>`;
  }
  for (let i=0;i<=4;i++) {
    const remaining = days * (1-i/4), label = i===4 ? 'Decision' : days===1 ? `T−${(remaining*24).toFixed(0)}h` : `T−${Number(remaining.toFixed(1))}d`;
    svg += `<text x="${L+(R-L)*i/4}" y="${H-12}" text-anchor="${i===0?'start':i===4?'end':'middle'}">${label}</text>`;
  }
  visible.forEach(s => {
    let path = '';
    s.points.forEach((p, i) => {
      const next = s.points[i+1];
      const left = Math.max(start, p.t), right = Math.min(end, p.t+s.maxAge, next ? next.t : end);
      if (right < left) return;
      path += ` M${x(left).toFixed(2)},${y(p.p).toFixed(2)} H${x(right).toFixed(2)}`;
      if (next && next.t <= end && next.t-p.t <= s.maxAge) path += ` V${y(next.p).toFixed(2)}`;
      if (p.t >= start) svg += `<circle cx="${x(p.t).toFixed(2)}" cy="${y(p.p).toFixed(2)}" r="${spread?3:2}" style="fill:${s.color}"><title>${esc(s.name + ' · ' + utc(p.t) + ' · ' + (spread ? p.p.toFixed(2)+' pp' : percent(p.p)))}</title></circle>`;
    });
    svg += `<path d="${path}" fill="none" style="stroke:${s.color}" stroke-width="2" ${s.dashed?'stroke-dasharray="7 4"':''}/>`;
  });
  if (end >= start && end < decision) svg += `<line x1="${x(end)}" x2="${x(end)}" y1="${TOP}" y2="${B}" class="fed-now"/><text x="${x(end)-5}" y="${TOP}" text-anchor="end">Now</text>`;
  return `<svg class="fed-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${spread?'Polymarket minus CME spread in percentage points':'Polymarket and CME FedWatch outcome probabilities'}, ${days} ${days===1?'day':'days'} before the decision"><title>Observations with UTC timestamps. Gaps are not interpolated.</title>${svg}</svg>`;
}

function button(T, label, patch, selected, key) {
  return `<button type="button" ${T.act(()=>T.setState(patch), {plain:true})} data-key="${key}" class="fed-button${selected?' selected':''}" aria-pressed="${selected}">${esc(label)}</button>`;
}

function calibration(e) {
  if (!e || !e.n) return '<p class="fed-empty">No time-matched observations available for evaluation yet.</p>';
  return `<div class="fed-calibration">${['pm','cme'].map(source => {
    const bins = e.reliability?.[source] || [];
    return `<div><h3 style="font-size:var(--t-small)">${source==='pm'?'Polymarket':'CME FedWatch'}</h3>${kalibrierung({punkte:bins.filter(b=>b.n).map(b=>({vorhergesagt:b.forecast, realisiert:b.observed, n:b.n,ci:false}))})}</div>`;
  }).join('')}</div><p class="fed-note">Descriptive calibration: mean forecast against observed frequency in five 20-percentage-point bins. Outcomes within the same meeting are dependent. n = ${e.n} meetings, too few for a reliable calibration assessment or confidence interval.</p>`;
}

export function renderFed(T) {
  const data = T.liveData.fed, s = T.state;
  const header = '<div class="fed-heading"><div><p class="fed-kicker">FOMC · SOURCE COMPARISON</p><h1 style="font-size:var(--t-hero)">Who prices in the Fed first?</h1><p>Polymarket and Fed funds futures on the same timeline.</p></div><span class="fed-badge">RESEARCH · NO ORDER EXECUTION</span></div>';
  if (!data?.meetings?.length) return `<section class="fed-page">${header}<div class="fed-empty">No comparison data loaded yet. Source: fed_comparison.json.${data?._fehler?' '+esc(data._fehler):''}</div><button type="button" class="fed-button" ${T.act(()=>T.neuLaden('fed'),{plain:true})}>Retry</button></section>`;
  const upcoming = data.meetings.find(m=>m.decision_ts>Date.now()/1000);
  const m = data.meetings.find(m=>m.date===s.fedMeeting) || upcoming || data.meetings.at(-1);
  const bucket = m.buckets.find(b=>b.key===s.fedOutcome) || m.buckets.find(b=>b.key===m.actual) || m.buckets.find(b=>b.key==='hike25') || m.buckets[0];
  const outcome = bucket.key, points = m.polymarket[outcome] || [], comparisons = comparePoints(m, outcome);
  const requestedWindow = [1,7,30].includes(Number(s.fedWindow)) ? Number(s.fedWindow) : 'all';
  const days = requestedWindow === 'all' ? Math.max(30,Math.ceil((m.decision_ts-(points[0]?.t || Date.now()/1000))/DAY)) : requestedWindow;
  const cme = (m.cme || []).map(c=>({t:c.t,p:c.probabilities[outcome]}));
  const latest = comparisons.at(-1), lastPM = points.at(-1), lastCME = cme.at(-1);
  const evalDays = [1,7,30].includes(Number(s.fedEval)) ? Number(s.fedEval) : 1;
  const evaluation = data.evaluation?.find(e=>e.days===evalDays);
  const actual = m.buckets.find(b=>b.key===m.actual);
  const rows = data.evaluation?.find(e=>e.days===evalDays)?.rows || [];
  const controls = `<div class="fed-controls"><label>Meeting<select ${T.inp(e=>T.setState({fedMeeting:e.target.value,fedOutcome:null}), 'fedMeeting')}>${data.meetings.map(meeting=>`<option value="${esc(meeting.date)}" ${meeting.date===m.date?'selected':''}>${dateLabel(meeting.date)} · ${meeting.actual?'Completed':'Upcoming'}</option>`).join('')}</select></label><label>Outcome<select ${T.inp(e=>T.setState({fedOutcome:e.target.value}), 'fedOutcome')}>${m.buckets.map(b=>`<option value="${esc(b.key)}" ${outcome===b.key?'selected':''}>${esc(bucketLabel(b))}</option>`).join('')}</select></label><div><span class="fed-label">Window before the decision</span><div class="fed-buttons">${[30,7,1,'all'].map(d=>button(T,d==='all'?'Full history':d===1?'1 day':d+' days',{fedWindow:d},requestedWindow===d,'fed-window-'+d)).join('')}</div></div></div>`;
  const metrics = `<div class="fed-metrics"><div><span>Polymarket · latest price</span><strong style="color:var(--s1)">${percent(lastPM?.p)}</strong><small>${utc(lastPM?.t)}</small></div><div><span>CME FedWatch · latest daily observation</span><strong style="color:var(--s2)">${percent(lastCME?.p)}</strong><small>${utc(lastCME?.t)}</small></div><div><span>Latest spread at the daily comparison time</span><strong>${latest?`${latest.p>0?'+':''}${latest.p.toFixed(2)} pp`:'Not comparable'}</strong><small>${latest?utc(latest.t):'No common observation time'}</small></div></div>`;
  const sources = [{name:'Polymarket',points,color:'var(--s1)',maxAge:7200},{name:'CME FedWatch · daily observations',points:cme,color:'var(--s2)',maxAge:4*DAY,dashed:true}];
  const issueHTML = (m.issues || []).length ? `<div class="fed-notice"><strong>Data coverage</strong>${m.issues.map(i=>`<p>${esc(i)}</p>`).join('')}</div>` : '';
  const table = `<table class="fed-table"><caption>Last five meetings · forecast error at T−${evalDays}</caption><thead><tr><th>Meeting</th><th>Decision</th><th>Comparison time UTC</th><th>Time before cutoff</th><th>Polymarket Brier</th><th>CME Brier</th></tr></thead><tbody>${rows.map(r=>{
    const meeting = data.meetings.find(x=>x.date===r.meeting), b = meeting?.buckets.find(x=>x.key===r.actual);
    return `<tr><td><button type="button" class="fed-link" ${T.act(()=>T.setState({fedMeeting:r.meeting,fedOutcome:r.actual,fedWindow:evalDays}),{plain:true})}>${dateLabel(r.meeting)}</button></td><td>${b?esc(bucketLabel(b)):'Pending'}</td><td>${r.asof?utc(r.asof):'Source or complete outcome vector missing'}</td><td>${r.age_hours!=null?r.age_hours.toFixed(1)+' h':'n/a'}</td><td>${score(r.pm_brier)}</td><td>${score(r.cme_brier)}</td></tr>`;
  }).join('')}</tbody></table>`;
  return `<section class="fed-page">${header}${controls}<div class="fed-meta">${dateLabel(m.date)} · Decision ${utc(m.decision_ts)} · ${actual?'Outcome: '+esc(bucketLabel(actual)):'Outcome pending'} · ${m.baseline_upper_bps!=null?'Previous upper bound: '+(m.baseline_upper_bps/100).toFixed(2)+'%':'Previous target range not yet known'}</div>${metrics}${issueHTML}
    <div class="fed-panel"><div class="fed-panel-title"><h2 style="font-size:var(--t-body)">${esc(bucketLabel(bucket))} · historical pricing</h2><div class="fed-legend"><span style="color:var(--s1)">━━ Polymarket</span><span style="color:var(--s2)">┄┄ CME FedWatch</span></div></div>${chart(sources,m.decision_ts,days)}<p class="fed-note">X-axis: ${days} ${days===1?'day':'days'} before the decision. Y-axis: fixed at 0–100%. Polymarket is hourly; CME is daily. Steps carry observations forward for at most 2 h and 96 h respectively; gaps remain visible. CME timestamps use a conservative end-of-day convention, not an intraday tick.</p></div>
    <div class="fed-panel"><h2 style="font-size:var(--t-body)">Pricing spread at the same daily comparison time</h2>${chart([{name:'Polymarket minus CME',points:comparisons,color:'var(--s3)',maxAge:4*DAY}],m.decision_ts,days,true)}<p class="fed-note">Positive values mean Polymarket prices the outcome higher. Polymarket is matched backwards to the conservative CME daily timestamp (at most 2 h old). The actual CME intraday observation time is not provided in the CSV. Prices are not normalised. A spread is not an executable arbitrage profit.</p></div>
    <div class="fed-panel"><div class="fed-panel-title"><h2 style="font-size:var(--t-body)">Which source was closer?</h2><div class="fed-buttons">${[30,7,1].map(d=>button(T,'T−'+d,{fedEval:d},evalDays===d,'fed-eval-'+d)).join('')}</div></div><div class="fed-scoreline"><b>Polymarket ${score(evaluation?.pm_brier)}</b><b>CME ${score(evaluation?.cme_brier)}</b><span>n = ${evaluation?.n || 0} paired meetings · preliminary</span></div><p class="fed-note">Multiclass Brier: 0 is perfect; 2 is the maximum error. Both sources use the same meetings and daily comparison times, without tick-level synchronisation. Complete Polymarket outcome vectors are normalised to sum to 1 for scoring only. Latest common observation before T−${evalDays}, with a maximum 96 h gap to the cutoff. March uses rounded FedWatch tables from the SinoPac broker archive. The actual observation may be older; the PDF does not specify a timezone for its data timestamp. No settlement prices are used.</p>${table}<details data-key="fed-calibration"><summary>View calibration · small sample</summary>${calibration(evaluation)}</details></div>
    <details class="fed-panel" data-key="fed-method"><summary>Methodology, comparability and data sources</summary><p>A Polymarket contract pays out on the rate change at an individual meeting. Fed funds futures settle against the monthly average effective federal funds rate. CME FedWatch derives target-range probabilities from these futures under model assumptions.</p><p>Comparison starts after the previous meeting, once its target range is known. Before then, CME rate levels and individual meeting changes are not equivalent. Differences in payoffs, basis risk, fees, funding, bid/ask spreads and available depth have not been converted into executable net returns.</p><p>CME CSV dates are conservatively timestamped at 23:59:59 America/Chicago. CME daily observations from the decision date are excluded. The 1-day view therefore does not show CME intraday moves. The curves show pricing over time; these CME data cannot measure an intraday lead.</p><p>Generated: ${esc(data.generated_at || '')}. Calendar verified through ${esc(data.calendar_through || '')}. This is not a live feed; “Reload data” reads the latest stored snapshot.</p><p>${external(m.event_url,'Polymarket market')} · ${external(data.cme_url,'CME FedWatch')} ${m.cme_archive_url?' · '+external(m.cme_archive_url,'March broker archive'):''} ${m.statement_url?' · '+external(m.statement_url,'Fed decision'):''} · <a href="./data/fed_comparison.json" download>Download comparison JSON</a></p><p class="fed-note">Raw data and SHA-256 checksums are stored locally. Refresh source data with scripts/collect_fed_comparison.py. Missing observations remain visible as gaps.</p></details>
    <div class="fed-footer"><span>Stored snapshot: ${esc(data.generated_at || '')}</span><button type="button" class="fed-button" ${T.act(()=>T.neuLaden('fed'),{plain:true})}>Reload data</button></div></section>`;
}
