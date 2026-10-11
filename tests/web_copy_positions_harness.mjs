import assert from 'node:assert/strict';
import {positionComparison} from '../web/js/pages/copy_positions.js';
const live = {traders:[{wallet:'w',label:'Example'}],position_comparison:{w:[{
  title:'<img src=x onerror=alert(1)>',outcome:'Yes',source_size:2000,copy_size:1500,
  source_entry:.5,copy_entry:.52,mark:.49,source_pnl:-20,copy_pnl:-45,
  mark_at:'2026-09-24T00:00:00Z',source_stale:true,
  last_execution:{source_side:'BUY',source_price:.5,copy_price:.52,filled_size:1500,
    desired_size:2000,latency_seconds:1.234,reason:'book_partial'}
}]}};
const html=positionComparison(live,'w');
assert(!html.includes('<img'));
for (const text of ['50¢ / 52¢','1.234 s','1,500 / 2,000','book_partial','STALE','before fees']) assert(html.includes(text), text);
assert(!positionComparison(live,'other').includes('book_partial'));
console.log('Position rendering: fill gap, latency, partial shares, missing data and escaping passed.');
