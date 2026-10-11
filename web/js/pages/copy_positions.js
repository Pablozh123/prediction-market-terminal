import { esc } from '../util.js';

const value = (n, digits=2) => n == null || !Number.isFinite(Number(n)) ? '—' : Number(n).toLocaleString('en-US', {maximumFractionDigits:digits});
const price = n => n == null ? '—' : value(Number(n)*100) + '¢';
const money = n => n == null ? '—' : '$' + value(n);

export function positionComparison(live, wallet='all', limit=100) {
  const groups = live.position_comparison || {};
  const names = Object.fromEntries((live.traders || []).map(t => [t.wallet, t.label && t.label !== t.wallet ? t.label : live.intelligence?.profiles?.[t.wallet]?.name || t.wallet]));
  const rows = Object.entries(groups).filter(([w]) => wallet === 'all' || w === wallet);
  return '<section style="padding:var(--sp-5) var(--sp-6)"><h2 style="font-size:var(--t-lead)">Open positions · source and copy</h2>'
    + '<p style="color:var(--ink-3)">Average entry and marked unrealized PnL before fees, at the displayed snapshot time. Marks are not executable exit quotes. Old paper holdings remain in the totals. Only new order-book copies have execution evidence. Latency uses source time and the local clock; clock skew affects it.</p>'
    + (rows.length ? '' : '<p>No open paper positions reported by /api/copy, and no source positions available.</p>')
    + rows.map(([w, positions]) => '<h3 style="font-size:var(--t-body)">' + esc(names[w] || w) + '</h3><div style="overflow-x:auto"><table style="width:100%; border-collapse:collapse; text-align:left; font-size:var(--t-small)">'
      + '<thead><tr>' + ['Market / outcome', 'Shares · source / copy', 'Avg entry · source / copy', 'Mark', 'Open PnL · source / copy', 'Latest attempt · source / copy fill', 'Delay / filled size'].map(t => '<th scope="col" style="padding:var(--sp-4)">' + t + '</th>').join('') + '</tr></thead><tbody>'
      + positions.slice(0, limit).map(p => {
        const e = p.last_execution;
        return '<tr>' + [
          esc(p.title) + '<br>' + esc(p.outcome || '') + '<br><small>' + esc(p.mark_source || 'Unknown mark source') + ' · ' + esc(p.mark_at || 'Unknown mark time') + (p.source_stale ? ' · STALE' : '') + '</small>',
          value(p.source_size) + ' / ' + value(p.copy_size),
          price(p.source_entry) + ' / ' + price(p.copy_entry),
          price(p.mark),
          money(p.source_pnl) + ' / ' + money(p.copy_pnl),
          e ? esc(e.source_side) + ' ' + price(e.source_price) + ' / ' + (e.filled_size ? price(e.copy_price) : 'no fill') + '<br><small>' + esc(e.reason) + '<br>' + esc(e.filled_at || e.observed_at) + '</small>' : 'No order-book evidence',
          e ? (e.latency_seconds == null ? '—' : value(e.latency_seconds, 3) + ' s') + '<br>' + value(e.filled_size) + ' / ' + value(e.desired_size) : '—',
        ].map(cell => '<td style="padding:var(--sp-4); border-top:1px solid var(--line-2); vertical-align:top">' + cell + '</td>').join('') + '</tr>';
      }).join('') + '</tbody></table><p>Showing ' + Math.min(limit, positions.length) + ' of ' + positions.length + ' positions in the loaded snapshot.' + (live.intelligence?.profiles?.[w]?.positions_capped ? ' Source API capped at 500 positions.' : '') + '</p></div>').join('') + '</section>';
}
