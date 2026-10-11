import assert from 'node:assert/strict';
import { intelligencePanel, signalsPanel } from '../web/js/pages/copy_intelligence.js';

const wallet = '0x' + 'a'.repeat(40);
const live = {traders: [{wallet, active: true}], intelligence: {
  watchlist: {[wallet]: ['javascript:alert(1)', 'https://x.com/example/status/123']},
  profiles: {[wallet]: {name: '<img src=x onerror=alert(1)>', snapshot_at: '2026-09-16T12:00:00Z',
    scorecard: {track: {resolved_markets: 0, settled_pnl: 0}},
    style: {buy_count: 2, longshot_share: .8, favorite_share: 0, timing_n: 0}}},
}};
const html = intelligencePanel(live);
assert(!html.includes('<img'));
assert(!html.includes('href="javascript:'));
assert(html.includes('https://x.com/example/status/123'));
assert(html.includes('Longshots'));
assert(html.includes('Timing unknown'));
assert(html.includes('Source portfolio Sharpe'));
assert(!html.includes('>$0<'));
assert(signalsPanel({intelligence:{stale:true}}).includes('Snapshot stale or incomplete'));
assert(intelligencePanel({}).includes('No research wallets imported yet'));
console.log('Copy research rendering: escaping, links, missing metrics and empty states OK');
