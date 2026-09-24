import { esc } from '../util.js';
import { kalibrierung } from '../charts.js';

const DAY = 86400;
const percent = p => Number.isFinite(p) ? (p * 100).toFixed(1) + '%' : 'Keine Daten';
const score = p => Number.isFinite(p) ? p.toFixed(4) : 'Nicht vergleichbar';
const utc = t => Number.isFinite(t) ? new Date(t * 1000).toISOString().slice(0, 16).replace('T', ' ') + ' UTC' : 'Keine Daten';
const dateLabel = date => String(date).split('-').reverse().join('.');
const bucketLabel = b => b.key === 'hold' ? 'Unverändert' : (b.min == null ? '−' + Math.abs(b.max) + '+' : b.min < 0 ? '−' + Math.abs(b.min) : '+' + b.min + (b.max == null ? '+' : '')) + ' bp';
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
  if (!visible.some(s => s.points.some(p => p.t + s.maxAge >= start))) return '<div class="fed-empty">Keine Beobachtungen in diesem Zeitfenster. Bei zukünftigen Meetings liegt das Fenster möglicherweise noch vor uns. «Bisher» zeigt die verfügbare Historie.</div>';
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
    const remaining = days * (1-i/4), label = i===4 ? 'Entscheid' : days===1 ? `T−${(remaining*24).toFixed(0)}h` : `T−${Number(remaining.toFixed(1))}d`;
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
  if (end >= start && end < decision) svg += `<line x1="${x(end)}" x2="${x(end)}" y1="${TOP}" y2="${B}" class="fed-now"/><text x="${x(end)-5}" y="${TOP}" text-anchor="end">Jetzt</text>`;
  return `<svg class="fed-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${spread?'Differenz Polymarket minus CME in Prozentpunkten':'Outcome-Wahrscheinlichkeiten von Polymarket und CME FedWatch'}, ${days} Tage bis zum Entscheid"><title>Messpunkte mit UTC-Zeitstempel. Lücken werden nicht interpoliert.</title>${svg}</svg>`;
}

function button(T, label, patch, selected, key) {
  return `<button type="button" ${T.act(()=>T.setState(patch), {plain:true})} data-key="${key}" class="fed-button${selected?' selected':''}" aria-pressed="${selected}">${esc(label)}</button>`;
}

function calibration(e) {
  if (!e || !e.n) return '<p class="fed-empty">Noch keine zeitlich gepaarten Daten für die Auswertung.</p>';
  return `<div class="fed-calibration">${['pm','cme'].map(source => {
    const bins = e.reliability?.[source] || [];
    return `<div><h3 style="font-size:var(--t-small)">${source==='pm'?'Polymarket':'CME FedWatch'}</h3>${kalibrierung({punkte:bins.filter(b=>b.n).map(b=>({vorhergesagt:b.forecast, realisiert:b.observed, n:b.n,ci:false}))})}</div>`;
  }).join('')}</div><p class="fed-note">Deskriptive Kalibrierung: mittlere Prognose gegen Trefferquote in fünf 20%-Bändern. Outcomes desselben Meetings sind abhängig. n = ${e.n} Meetings, zu wenig für ein belastbares Kalibrierungsurteil oder Konfidenzintervall.</p>`;
}

export function renderFed(T) {
  const data = T.liveData.fed, s = T.state;
  const header = '<div class="fed-heading"><div><p class="fed-kicker">FOMC · QUELLENVERGLEICH</p><h1 style="font-size:var(--t-hero)">Wer preist die Fed früher ein?</h1><p>Polymarket und Fed-Funds-Futures auf derselben Zeitachse.</p></div><span class="fed-badge">RESEARCH · KEINE ORDERAUSFÜHRUNG</span></div>';
  if (!data?.meetings?.length) return `<section class="fed-page">${header}<div class="fed-empty">Noch keine Vergleichsdaten geladen. Quelle: fed_comparison.json.${data?._fehler?' '+esc(data._fehler):''}</div><button type="button" class="fed-button" ${T.act(()=>T.neuLaden('fed'),{plain:true})}>Erneut laden</button></section>`;
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
  const controls = `<div class="fed-controls"><label>Meeting<select ${T.inp(e=>T.setState({fedMeeting:e.target.value,fedOutcome:null}), 'fedMeeting')}>${data.meetings.map(meeting=>`<option value="${esc(meeting.date)}" ${meeting.date===m.date?'selected':''}>${dateLabel(meeting.date)} · ${meeting.actual?'Abgeschlossen':'Kommend'}</option>`).join('')}</select></label><label>Outcome<select ${T.inp(e=>T.setState({fedOutcome:e.target.value}), 'fedOutcome')}>${m.buckets.map(b=>`<option value="${esc(b.key)}" ${outcome===b.key?'selected':''}>${esc(bucketLabel(b))}</option>`).join('')}</select></label><div><span class="fed-label">Zeitfenster vor dem Entscheid</span><div class="fed-buttons">${[30,7,1,'all'].map(d=>button(T,d==='all'?'Bisher':d===1?'1 Tag':d+' Tage',{fedWindow:d},requestedWindow===d,'fed-window-'+d)).join('')}</div></div></div>`;
  const metrics = `<div class="fed-metrics"><div><span>Polymarket · letzter Preis</span><strong style="color:var(--s1)">${percent(lastPM?.p)}</strong><small>${utc(lastPM?.t)}</small></div><div><span>CME FedWatch · letzter Tageswert</span><strong style="color:var(--s2)">${percent(lastCME?.p)}</strong><small>${utc(lastCME?.t)}</small></div><div><span>Letzte Differenz am Tagesstichtag</span><strong>${latest?`${latest.p>0?'+':''}${latest.p.toFixed(2)} pp`:'Nicht vergleichbar'}</strong><small>${latest?utc(latest.t):'Gemeinsamer Zeitpunkt fehlt'}</small></div></div>`;
  const sources = [{name:'Polymarket',points,color:'var(--s1)',maxAge:7200},{name:'CME FedWatch · Tagesdaten',points:cme,color:'var(--s2)',maxAge:4*DAY,dashed:true}];
  const issueHTML = (m.issues || []).length ? `<div class="fed-notice"><strong>Datenabdeckung</strong>${m.issues.map(i=>`<p>${esc(i)}</p>`).join('')}</div>` : '';
  const table = `<table class="fed-table"><caption>Letzte fünf Meetings · Prognosefehler zum Horizont T−${evalDays}</caption><thead><tr><th>Meeting</th><th>Entscheid</th><th>Vergleichszeitpunkt UTC</th><th>Stichtagsabstand</th><th>Polymarket Brier</th><th>CME Brier</th></tr></thead><tbody>${rows.map(r=>{
    const meeting = data.meetings.find(x=>x.date===r.meeting), b = meeting?.buckets.find(x=>x.key===r.actual);
    return `<tr><td><button type="button" class="fed-link" ${T.act(()=>T.setState({fedMeeting:r.meeting,fedOutcome:r.actual,fedWindow:evalDays}),{plain:true})}>${dateLabel(r.meeting)}</button></td><td>${b?esc(bucketLabel(b)):'Offen'}</td><td>${r.asof?utc(r.asof):'Quelle / vollständiger Vektor fehlt'}</td><td>${r.age_hours!=null?r.age_hours.toFixed(1)+' h':'n/a'}</td><td>${score(r.pm_brier)}</td><td>${score(r.cme_brier)}</td></tr>`;
  }).join('')}</tbody></table>`;
  return `<section class="fed-page">${header}${controls}<div class="fed-meta">${dateLabel(m.date)} · Entscheid ${utc(m.decision_ts)} · ${actual?'Ergebnis: '+esc(bucketLabel(actual)):'Ergebnis offen'} · ${m.baseline_upper_bps!=null?'Vorherige Obergrenze: '+(m.baseline_upper_bps/100).toFixed(2)+'%':'Vorherige Zielspanne noch unbekannt'}</div>${metrics}${issueHTML}
    <div class="fed-panel"><div class="fed-panel-title"><h2 style="font-size:var(--t-body)">${esc(bucketLabel(bucket))} · historische Einpreisung</h2><div class="fed-legend"><span style="color:var(--s1)">━━ Polymarket</span><span style="color:var(--s2)">┄┄ CME FedWatch</span></div></div>${chart(sources,m.decision_ts,days)}<p class="fed-note">X-Achse: ${days} Tage bis zum Entscheid. Y-Achse: unveränderte 0–100%. Polymarket stündlich, CME täglich. Stufen halten letzte Beobachtungen höchstens 2 h bzw. 96 h; Lücken bleiben offen. CME-Uhrzeit ist die konservative Tagesend-Konvention, kein Intraday-Tick.</p></div>
    <div class="fed-panel"><h2 style="font-size:var(--t-body)">Bewertungsdifferenz zum selben Tagesstichtag</h2>${chart([{name:'Polymarket minus CME',points:comparisons,color:'var(--s3)',maxAge:4*DAY}],m.decision_ts,days,true)}<p class="fed-note">Positiv: Polymarket bewertet das Outcome höher. Polymarket wird zum konservativen CME-Tagesstichtag rückwärts abgeglichen (max. 2 h alt). Die tatsächliche CME-Intraday-Zeit ist im CSV unbekannt. Preise bleiben unnormalisiert. Eine Differenz ist kein ausführbarer Arbitragegewinn.</p></div>
    <div class="fed-panel"><div class="fed-panel-title"><h2 style="font-size:var(--t-body)">Welche Quelle lag näher?</h2><div class="fed-buttons">${[30,7,1].map(d=>button(T,'T−'+d,{fedEval:d},evalDays===d,'fed-eval-'+d)).join('')}</div></div><div class="fed-scoreline"><b>Polymarket ${score(evaluation?.pm_brier)}</b><b>CME ${score(evaluation?.cme_brier)}</b><span>n = ${evaluation?.n || 0} gepaarte Meetings · vorläufig</span></div><p class="fed-note">Multiclass Brier: 0 ist perfekt, 2 maximal falsch. Gleiche Meetings und Tagesstichtage für beide Quellen; keine tickgenaue Synchronisation. Vollständige Polymarket-Vektoren werden nur für den Score auf Summe 1 normiert. Letzte gemeinsame Beobachtung vor T−${evalDays}, Stichtagsabstand höchstens 96 h. März stammt aus gerundeten FedWatch-Tabellen im SinoPac-Brokerarchiv. Die tatsächliche Beobachtung kann älter sein; die Zeitzone der PDF-Datenzeit ist nicht angegeben. Keine Settlement-Preise.</p>${table}<details data-key="fed-calibration"><summary>Kalibrierung ansehen · kleine Stichprobe</summary>${calibration(evaluation)}</details></div>
    <details class="fed-panel" data-key="fed-method"><summary>Methodik, Vergleichbarkeit und Datenherkunft</summary><p>Ein Polymarket-Kontrakt zahlt auf die Änderung beim einzelnen Meeting. Fed-Funds-Futures rechnen auf den monatlichen durchschnittlichen effektiven Tageszins ab. CME FedWatch leitet daraus unter Modellannahmen Wahrscheinlichkeiten für Zielspannen ab.</p><p>Der Vergleich beginnt nach dem vorherigen Meeting, sobald die damalige Zielspanne feststeht. Vorher sind CME-Zinsniveaus und einzelne Meeting-Änderungen nicht gleichbedeutend. Unterschiedliche Auszahlung, Basisrisiko, Gebühren, Finanzierung, Geld-/Briefkurse und verfügbare Tiefe sind hier nicht in einen handelbaren Nettoertrag umgerechnet.</p><p>CME-CSV-Datum: konservativ 23:59:59 America/Chicago. CME-Tageswerte des Entscheidtages sind ausgeschlossen. In der 1-Tagesansicht entstehen deshalb keine CME-Intraday-Bewegungen. Die Kurven zeigen Einpreisung; ein Vorsprung innerhalb eines Tages lässt sich mit diesen CME-Daten nicht messen.</p><p>Erstellt: ${esc(data.generated_at || '')}. Kalender geprüft bis ${esc(data.calendar_through || '')}. Kein Live-Feed; «Daten neu laden» liest den zuletzt gespeicherten Stand.</p><p>${external(m.event_url,'Polymarket-Markt')} · ${external(data.cme_url,'CME FedWatch')} ${m.cme_archive_url?' · '+external(m.cme_archive_url,'März-Brokerarchiv'):''} ${m.statement_url?' · '+external(m.statement_url,'Fed-Entscheid'):''} · <a href="./data/fed_comparison.json" download>Vergleichsdaten als JSON</a></p><p class="fed-note">Rohdaten und SHA-256-Nachweise werden lokal gespeichert. Ein neuer Abruf erfolgt über scripts/collect_fed_comparison.py. Fehlende Quellen bleiben als Lücken sichtbar.</p></details>
    <div class="fed-footer"><span>Gespeicherter Stand: ${esc(data.generated_at || '')}</span><button type="button" class="fed-button" ${T.act(()=>T.neuLaden('fed'),{plain:true})}>Daten neu laden</button></div></section>`;
}
