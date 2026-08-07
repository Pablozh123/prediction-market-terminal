// Demo dataset — verbatim from the design reference. Used until the API answers,
// and as fallback whenever it is unreachable (status badge shows which one is live).

export const DEMO_MARKETS = [
  { id: 'fed', title: 'Fed cuts rates in September 2026', venue: 'Polymarket', cat: 'Macro', yes: 62, chg: -7, vol: 4800000, liq: 1020000, ends: '18 Sep', spark: [12, 14, 13, 20, 26, 34, 41] },
  { id: 'btc', title: 'Bitcoin above $150k on Dec 31, 2026', venue: 'Polymarket', cat: 'Crypto', yes: 38, chg: 6, vol: 3110000, liq: 840000, ends: '31 Dec', spark: [40, 36, 38, 27, 22, 17, 11] },
  { id: 'brazil', title: 'Brazil win the 2026 World Cup', venue: 'Polymarket', cat: 'Sports', yes: 21, chg: 4, vol: 2740000, liq: 610000, ends: '19 Jul', spark: [36, 34, 30, 31, 24, 20, 15] },
  { id: 'obama', title: 'Obama wins the 2028 Democratic nomination', venue: 'Polymarket', cat: 'Politics', yes: 4, chg: 2, vol: 1960000, liq: 390000, ends: 'Aug 2028', spark: [42, 44, 40, 41, 35, 33, 29] },
  { id: 'germany', title: 'Germany win on 2026-06-20', venue: 'Kalshi', cat: 'Sports', yes: 63, chg: -5, vol: 940000, liq: 220000, ends: '20 Jun', spark: [16, 14, 20, 22, 28, 32, 36] },
  { id: 'iraq', title: 'Iraq win on 2026-06-22', venue: 'Polymarket', cat: 'Sports', yes: 96, chg: 11, vol: 780000, liq: 140000, ends: '22 Jun', spark: [44, 43, 41, 38, 22, 14, 8] },
  { id: 'cpi', title: 'US CPI above 3.0% in August 2026', venue: 'Kalshi', cat: 'Macro', yes: 44, chg: -2, vol: 1420000, liq: 510000, ends: '11 Sep', spark: [22, 21, 24, 23, 26, 27, 29] },
  { id: 'gov', title: 'Government shutdown before October 2026', venue: 'Polymarket', cat: 'Politics', yes: 29, chg: 9, vol: 2210000, liq: 470000, ends: '30 Sep', spark: [46, 42, 38, 30, 24, 18, 12] },
  { id: 'eth', title: 'Ethereum above $8k on Dec 31, 2026', venue: 'Polymarket', cat: 'Crypto', yes: 17, chg: -3, vol: 890000, liq: 260000, ends: '31 Dec', spark: [18, 19, 22, 21, 26, 28, 31] },
  { id: 'korea', title: 'Korea Republic win on 2026-06-11', venue: 'Polymarket', cat: 'Sports', yes: 64, chg: 1, vol: 660000, liq: 180000, ends: '11 Jun', spark: [26, 27, 25, 26, 24, 25, 23] },
  { id: 'ecb', title: 'ECB holds rates at the September meeting', venue: 'Kalshi', cat: 'Macro', yes: 71, chg: 3, vol: 540000, liq: 200000, ends: '10 Sep', spark: [30, 29, 27, 26, 24, 22, 20] },
  { id: 'nasa', title: 'Crewed Artemis launch slips past 2027', venue: 'Polymarket', cat: 'Science', yes: 58, chg: -1, vol: 310000, liq: 95000, ends: 'Dec 2027', spark: [24, 24, 25, 26, 25, 26, 27] }
];

export const DEMO_MARKET_EXTRA = {
  fed: { spread: 2, age: 210, endsDays: 49, saved: true, pos: true },
  btc: { spread: 3, age: 400, endsDays: 153, saved: true, pos: true },
  brazil: { spread: 6, age: 320, endsDays: 12, saved: false, pos: true },
  obama: { spread: 9, age: 90, endsDays: 740, saved: false, pos: false },
  germany: { spread: 4, age: 180, endsDays: 5, saved: false, pos: false },
  iraq: { spread: 8, age: 60, endsDays: 6, saved: false, pos: false },
  cpi: { spread: 2, age: 150, endsDays: 42, saved: false, pos: false },
  gov: { spread: 5, age: 45, endsDays: 61, saved: true, pos: true },
  eth: { spread: 7, age: 400, endsDays: 153, saved: false, pos: false },
  korea: { spread: 4, age: 30, endsDays: 3, saved: false, pos: true },
  ecb: { spread: 3, age: 120, endsDays: 41, saved: false, pos: true },
  nasa: { spread: 11, age: 500, endsDays: 519, saved: false, pos: false }
};

export const DEMO_TRADERS = [
  { name: 'Theo4', wallet: '0x9f3a…21c', pnl: 22050000, win: 0.61, resolved: 4120, vol: 148000000, score: 94, tags: 'Politics · Macro' },
  { name: 'Swisstony', wallet: '0x204f…5e14', pnl: 8410000, win: 0.58, resolved: 9840, vol: 96000000, score: 91, tags: 'Sports fader · high volume' },
  { name: 'RainMaker', wallet: '0x71c8…8ab', pnl: 6220000, win: 0.66, resolved: 1180, vol: 41000000, score: 88, tags: 'Macro only' },
  { name: 'quietsize', wallet: '0xd0e1…447', pnl: 4870000, win: 0.54, resolved: 6410, vol: 71000000, score: 82, tags: 'Market maker like' },
  { name: 'lateflow', wallet: '0x33bb…19f', pnl: 3140000, win: 0.72, resolved: 340, vol: 12000000, score: 79, tags: 'Small sample' },
  { name: 'Cassandra', wallet: '0x8e42…6d0', pnl: 2680000, win: 0.63, resolved: 2210, vol: 28000000, score: 77, tags: 'Elections' },
  { name: '0xc41b…9de', wallet: '0xc41b…9de', pnl: 1920000, win: 0.51, resolved: 5180, vol: 54000000, score: 71, tags: 'Bot-like timing' },
  { name: 'northpole', wallet: '0x5a77…c02', pnl: 1450000, win: 0.59, resolved: 1620, vol: 19000000, score: 68, tags: 'Crypto' },
  { name: 'MeanRev', wallet: '0xb219…7f5', pnl: 980000, win: 0.49, resolved: 7740, vol: 63000000, score: 64, tags: 'Fades favourites' },
  { name: 'fresh_hands', wallet: '0x0ac9…31e', pnl: 640000, win: 0.77, resolved: 91, vol: 3400000, score: 41, tags: 'Sample too small' }
];

export const DEMO_TRADER_EXTRA = {
  Theo4: { positions: 4100000, assets: 26000000, balance: 820000, ageDays: 1240, traits: ['Whales'], bot: 12, active: 84 },
  Swisstony: { positions: 1900000, assets: 9800000, balance: 210000, ageDays: 980, traits: ['Whales','Verified'], bot: 34, active: 212 },
  RainMaker: { positions: 640000, assets: 7100000, balance: 410000, ageDays: 610, traits: ['Whales'], bot: 8, active: 31 },
  quietsize: { positions: 2400000, assets: 5600000, balance: 96000, ageDays: 1400, traits: ['Bot-like'], bot: 88, active: 341 },
  lateflow: { positions: 120000, assets: 3300000, balance: 44000, ageDays: 210, traits: [], bot: 21, active: 12 },
  Cassandra: { positions: 380000, assets: 2900000, balance: 130000, ageDays: 760, traits: ['Verified'], bot: 16, active: 46 },
  '0xc41b…9de': { positions: 910000, assets: 2100000, balance: 61000, ageDays: 320, traits: ['Bot-like'], bot: 92, active: 508 },
  northpole: { positions: 210000, assets: 1600000, balance: 28000, ageDays: 440, traits: [], bot: 27, active: 24 },
  MeanRev: { positions: 1300000, assets: 1200000, balance: 18000, ageDays: 1100, traits: ['Bot-like'], bot: 71, active: 296 },
  fresh_hands: { positions: 34000, assets: 680000, balance: 9000, ageDays: 11, traits: [], bot: 5, active: 6 }
};

export const DEMO_RISKS = [
  { id: 'r1', kind: 'COORDINATED TIMING', score: 82, market: 'Iraq win on 2026-06-22', detail: 'Six wallets bought Yes inside forty seconds. Four had never traded this category before.', wallets: 6, notional: '$214k', window: '40s', venue: 'Polymarket', sev: 'high' },
  { id: 'r2', kind: 'FRESH WALLET CLUSTER', score: 71, market: 'Ecuador vs. Curaçao ends in a draw', detail: 'Four wallets funded less than three days ago took the same side within an hour.', wallets: 4, notional: '$88k', window: '58m', venue: 'Polymarket', sev: 'high' },
  { id: 'r3', kind: 'PRE-NEWS ACCUMULATION', score: 64, market: 'Fed cuts rates in September 2026', detail: 'Buying of $310k in the ninety minutes before the payrolls release, then no follow-through.', wallets: 3, notional: '$310k', window: '90m', venue: 'Polymarket', sev: 'medium' },
  { id: 'r4', kind: 'ONE-SIDED SWEEP', score: 58, market: 'Government shutdown before October 2026', detail: 'A single wallet lifted every offer up to 31c, moving the market nine cents alone.', wallets: 1, notional: '$142k', window: '12m', venue: 'Polymarket', sev: 'medium' },
  { id: 'r5', kind: 'CROSS-VENUE LEAD', score: 47, market: 'US CPI above 3.0% in August 2026', detail: 'Kalshi moved first on three of the last four prints, Polymarket followed within two minutes.', wallets: 9, notional: '$61k', window: '2m', venue: 'Both', sev: 'low' },
  { id: 'r6', kind: 'DORMANT WALLET WAKE', score: 39, market: 'Ethereum above $8k on Dec 31, 2026', detail: 'A wallet idle for eleven months returned and took a single large position.', wallets: 1, notional: '$47k', window: '1 trade', venue: 'Polymarket', sev: 'low' }
];

export const DEMO_TAPE = [
  { ago: '2 min ago', mins: 2, wallet: 'Swisstony', market: 'Brazil win on 2026-06-13', side: 'BUY No', price: '41.5¢', size: 18400, venue: 'Polymarket', tracked: true },
  { ago: '6 min ago', mins: 6, wallet: '0x7f3a…21c', market: 'Fed cuts rates in September 2026', side: 'BUY Yes', price: '62.0¢', size: 9750, venue: 'Polymarket', tracked: false },
  { ago: '11 min ago', mins: 11, wallet: 'Theo4', market: 'Obama wins the 2028 Democratic nomination', side: 'SELL Yes', price: '4.0¢', size: 6200, venue: 'Polymarket', tracked: true },
  { ago: '14 min ago', mins: 14, wallet: '0xc41b…9de', market: 'Korea Republic win on 2026-06-11', side: 'BUY No', price: '63.5¢', size: 5050, venue: 'Polymarket', tracked: false },
  { ago: '17 min ago', mins: 17, wallet: 'quietsize', market: 'Government shutdown before October 2026', side: 'BUY Yes', price: '29.0¢', size: 24800, venue: 'Polymarket', tracked: false },
  { ago: '21 min ago', mins: 21, wallet: '—', market: 'US CPI above 3.0% in August 2026', side: 'SELL Yes', price: '44.0¢', size: 12300, venue: 'Kalshi', tracked: false },
  { ago: '25 min ago', mins: 25, wallet: 'RainMaker', market: 'ECB holds rates at the September meeting', side: 'BUY Yes', price: '71.0¢', size: 8900, venue: 'Kalshi', tracked: true },
  { ago: '29 min ago', mins: 29, wallet: '0x33bb…19f', market: 'Bitcoin above $150k on Dec 31, 2026', side: 'BUY Yes', price: '38.0¢', size: 3400, venue: 'Polymarket', tracked: false },
  { ago: '34 min ago', mins: 34, wallet: 'MeanRev', market: 'Iraq win on 2026-06-22', side: 'SELL Yes', price: '96.0¢', size: 15600, venue: 'Polymarket', tracked: false },
  { ago: '38 min ago', mins: 38, wallet: 'northpole', market: 'Ethereum above $8k on Dec 31, 2026', side: 'BUY No', price: '83.0¢', size: 2700, venue: 'Polymarket', tracked: true },
  { ago: '43 min ago', mins: 43, wallet: '0xd0e1…447', market: 'Germany win on 2026-06-20', side: 'BUY No', price: '37.0¢', size: 11200, venue: 'Kalshi', tracked: false },
  { ago: '51 min ago', mins: 51, wallet: 'Cassandra', market: 'Crewed Artemis launch slips past 2027', side: 'BUY Yes', price: '58.0¢', size: 4100, venue: 'Polymarket', tracked: false }
];

export const DEMO_COPY_ORDERS = [
  { time: '14:19', market: 'Brazil win on 2026-06-13', side: 'BUY No', theirs: '$18,400', yours: '$7,728', status: 'copied' },
  { time: '13:52', market: 'Korea Republic win on 2026-06-11', side: 'BUY No', theirs: '$5,050', yours: '$2,121', status: 'copied' },
  { time: '13:04', market: 'Germany win on 2026-06-20', side: 'BUY No', theirs: '$11,200', yours: '$0', status: 'skipped' },
  { time: '12:41', market: 'Iraq win on 2026-06-22', side: 'SELL Yes', theirs: '$15,600', yours: '$6,552', status: 'copied' },
  { time: '11:58', market: 'Uruguay win on 2026-06-21', side: 'BUY No', theirs: '$3,900', yours: '$1,638', status: 'copied' },
  { time: '10:12', market: 'Japan win on 2026-06-14', side: 'BUY No', theirs: '$7,400', yours: '$0', status: 'skipped' },
  { time: '09:30', market: 'Spain win on 2026-06-21', side: 'BUY Yes', theirs: '$2,600', yours: '$1,092', status: 'baseline' },
  { time: '08:47', market: 'Curaçao win on 2026-06-14', side: 'BUY No', theirs: '$9,100', yours: '$3,822', status: 'copied' }
];

export const DEMO_CROSS_PAIRS = [
  { event: 'Germany win on 2026-06-20', cat: 'SPORTS', pm: 58, ks: 63, pmVol: 1100000, ksVol: 500000, sim: 0.71, held: '11 min' },
  { event: 'Fed cuts rates in September 2026', cat: 'MACRO', pm: 62, ks: 60, pmVol: 4800000, ksVol: 1400000, sim: 0.64, held: '4 min' },
  { event: 'US CPI above 3.0% in August 2026', cat: 'MACRO', pm: 41, ks: 44, pmVol: 1420000, ksVol: 680000, sim: 0.58, held: '26 min' },
  { event: 'Government shutdown before October 2026', cat: 'POLITICS', pm: 29, ks: 36, pmVol: 2210000, ksVol: 390000, sim: 0.52, held: '2 h' },
  { event: 'Bitcoin above $150k on Dec 31, 2026', cat: 'CRYPTO', pm: 38, ks: 39, pmVol: 3110000, ksVol: 290000, sim: 0.69, held: '9 min' },
  { event: 'ECB holds rates at the September meeting', cat: 'MACRO', pm: 70, ks: 71, pmVol: 540000, ksVol: 160000, sim: 0.46, held: '1 h' },
  { event: 'Crewed Artemis launch slips past 2027', cat: 'SCIENCE', pm: 58, ks: 52, pmVol: 310000, ksVol: 90000, sim: 0.33, held: '3 h' }
];

export const DEMO_RESOLVED = [
  { title: 'Curaçao win on 2026-06-14', meta: 'POLYMARKET · SPORTS', yes: true, last: 98, vol: '$1.2m', when: '3 h ago', hours: 3 },
  { title: 'Fed holds rates in July 2026', meta: 'POLYMARKET · MACRO', yes: true, last: 81, vol: '$8.4m', when: '9 h ago', hours: 9 },
  { title: 'Spain win on 2026-06-21', meta: 'KALSHI · SPORTS', yes: false, last: 88, vol: '$0.9m', when: '1 d ago', hours: 26 },
  { title: 'US CPI above 3.4% in June 2026', meta: 'POLYMARKET · MACRO', yes: false, last: 34, vol: '$3.1m', when: '2 d ago', hours: 50 },
  { title: 'Belgium win on 2026-06-21', meta: 'POLYMARKET · SPORTS', yes: true, last: 70, vol: '$0.6m', when: '2 d ago', hours: 54 },
  { title: 'Senate passes the budget before July', meta: 'POLYMARKET · POLITICS', yes: false, last: 62, vol: '$2.2m', when: '4 d ago', hours: 98 },
  { title: 'Ethereum above $6k in July 2026', meta: 'POLYMARKET · CRYPTO', yes: false, last: 19, vol: '$1.4m', when: '6 d ago', hours: 150 },
  { title: 'Iran talks resume before August', meta: 'KALSHI · POLITICS', yes: true, last: 44, vol: '$0.7m', when: '8 d ago', hours: 200 }
];

export const DEMO_WHALES = [
  { name: 'quietsize', wallet: '0xd0e1…447', prints: 31, total: 2840000, biggest: 214000, lean: 'BUYING', cat: 'Politics' },
  { name: 'Swisstony', wallet: '0x204f…5e14', prints: 24, total: 1960000, biggest: 118000, lean: 'FADING', cat: 'Sports' },
  { name: 'Theo4', wallet: '0x9f3a…21c', prints: 19, total: 1740000, biggest: 96000, lean: 'SELLING', cat: 'Politics' },
  { name: 'RainMaker', wallet: '0x71c8…8ab', prints: 12, total: 1210000, biggest: 88000, lean: 'BUYING', cat: 'Macro' },
  { name: '0xc41b…9de', wallet: '0xc41b…9de', prints: 41, total: 980000, biggest: 42000, lean: 'TWO-WAY', cat: 'Sports' },
  { name: 'MeanRev', wallet: '0xb219…7f5', prints: 17, total: 760000, biggest: 61000, lean: 'FADING', cat: 'Crypto' }
];

export const DEMO_RISK_WALLETS = [
  { wallet: '0x8ac1…4f2', context: 'politics', score: 84, prints: 9, notional: '$212k', firstSeen: '6 days ago', cluster: 'C-1' },
  { wallet: '0x33e9…07b', context: 'politics', score: 78, prints: 4, notional: '$96k', firstSeen: '2 days ago', cluster: 'C-1' },
  { wallet: '0xb0d2…913', context: 'macro', score: 71, prints: 6, notional: '$148k', firstSeen: '4 months ago', cluster: '—' },
  { wallet: '0x5f77…c81', context: 'sports-adjacent', score: 62, prints: 12, notional: '$74k', firstSeen: '11 days ago', cluster: 'C-2' },
  { wallet: '0x21aa…6de', context: 'macro', score: 54, prints: 3, notional: '$61k', firstSeen: '1 year ago', cluster: '—' },
  { wallet: '0xd914…22c', context: 'politics', score: 41, prints: 2, notional: '$38k', firstSeen: '3 years ago', cluster: '—' }
];

export const DEMO_FRESH_CLUSTERS = [
  { tag: 'FUNDED WITHIN 3 DAYS', score: 82, market: 'Iraq win on 2026-06-22', detail: 'Six wallets created in the same week bought the same side within forty seconds.', wallets: ['0x8ac1…4f2','0x33e9…07b','0x91cd…5a0','0x77be…31f','0x0ac9…88d','0x4412…7e1'] },
  { tag: 'FUNDED WITHIN 3 DAYS', score: 71, market: 'Ecuador vs. Curaçao ends in a draw', detail: 'Four wallets funded from the same bridge contract, then one position each.', wallets: ['0x5f77…c81','0x9d31…44a','0xc02e…19b','0x6ba8…772'] },
  { tag: 'FIRST TRADE EVER', score: 66, market: 'Government shutdown before October 2026', detail: 'Three wallets whose very first trade was this market, all on the same side.', wallets: ['0x11fa…903','0x84cc…2b7','0xe730…65d'] },
  { tag: 'DORMANT THEN ACTIVE', score: 48, market: 'Ethereum above $8k on Dec 31, 2026', detail: 'Two wallets idle for over a year returned on the same afternoon.', wallets: ['0x2c40…8ff','0xaa19…d34'] }
];

export const DEMO_TIMING_CLUSTERS = [
  { market: 'Iraq win on 2026-06-22', wallets: 6, window: '40 s', notional: '$214k', same: true },
  { market: 'Fed cuts rates in September 2026', wallets: 3, window: '90 min', notional: '$310k', same: true },
  { market: 'Government shutdown before October 2026', wallets: 4, window: '12 min', notional: '$142k', same: true },
  { market: 'US CPI above 3.0% in August 2026', wallets: 9, window: '2 min', notional: '$61k', same: false },
  { market: 'Ecuador vs. Curaçao ends in a draw', wallets: 4, window: '58 min', notional: '$88k', same: true }
];

export const DEMO_NETWORK_CLUSTERS = [
  { name: 'Cluster C-1', size: 6, shared: '9', notional: '$412k', story: 'Six wallets, all funded in the same week, appear together in nine political markets — always within five minutes of each other.' },
  { name: 'Cluster C-2', size: 4, shared: '5', notional: '$168k', story: 'Four wallets that only overlap on long-odds sports-adjacent markets. Weak signal, kept for context.' },
  { name: 'Cluster C-3', size: 3, shared: '4', notional: '$96k', story: 'Three older wallets with a stable co-trading pattern in macro. Most likely one desk running several accounts.' }
];

export const DEMO_TRACKED_WALLETS = [
  { name: 'Swisstony', wallet: '0x204f…5e14', grade: 'A', pnl: '+$18.4k', last: '2 min' },
  { name: 'Theo4', wallet: '0x9f3a…21c', grade: 'A', pnl: '+$44.1k', last: '11 min' },
  { name: 'northpole', wallet: '0x5a77…c02', grade: 'C', pnl: '-$2.1k', last: '38 min' }
];

export const DEMO_COPY_POSITIONS = [
  ['Brazil win on 2026-06-13','No','186.2','0.415','0.435','$81.00','+$3.72'],
  ['Iraq win on 2026-06-22','Yes','68.2','0.960','1.000','$68.20','+$2.73'],
  ['Korea Republic win on 2026-06-11','No','58.4','0.635','0.640','$37.38','+$0.29'],
  ['Uruguay win on 2026-06-21','No','52.0','0.315','0.300','$15.60','-$0.78'],
  ['Curaçao win on 2026-06-14','No','96.4','0.982','1.000','$96.40','+$1.74']
];

export const DEMO_CASH_ROWS = [
  ['2026-05-31','Start cash','+$1,000.00','$1,000.00'],
  ['2026-06-14','Settlement recycled','+$186.40','$412.80'],
  ['2026-06-28','Settlement recycled','+$94.10','$338.20'],
  ['2026-07-12','Manual top-up','+$0.00','$338.20'],
  ['2026-07-29','Settlement recycled','+$61.30','$312.40']
];

export const DEMO_PORT_ROWS = [
  ['Fed cuts rates in September 2026','YES','58¢','62¢','+$12.40','research'],
  ['Bitcoin above $150k on Dec 31, 2026','YES','41¢','38¢','-$6.10','research'],
  ['Government shutdown before October 2026','YES','22¢','29¢','+$18.90','research'],
  ['Brazil win the 2026 World Cup','NO','81¢','79¢','-$3.20','copy'],
  ['Korea Republic win on 2026-06-11','NO','34¢','36¢','+$4.70','copy'],
  ['ECB holds rates at the September meeting','YES','68¢','71¢','+$2.90','research']
];

export const DEMO_HIST_ROWS = [
  ['2026-07-29','Fed holds rates in July 2026','YES','74¢','100¢','+$34.20'],
  ['2026-07-24','Spain win on 2026-06-21','YES','88¢','0¢','-$25.00'],
  ['2026-07-18','US CPI above 3.4% in June 2026','NO','66¢','100¢','+$17.60'],
  ['2026-07-11','Belgium win on 2026-06-21','YES','70¢','100¢','+$10.70'],
  ['2026-07-04','Senate passes the budget before July','YES','62¢','0¢','-$25.00'],
  ['2026-06-28','Curaçao win on 2026-06-14','NO','2¢','0¢','+$1.90']
];

export const DEMO_ALERT_FEED = [
  { time: '14:18', rule: 'WHALE PRINT', market: 'Brazil win on 2026-06-13', value: '$18,400', venue: 'Polymarket', watched: true },
  { time: '14:02', rule: 'FAST MOVER', market: 'Fed cuts rates in September 2026', value: '-7¢ in 44 min', venue: 'Polymarket', watched: true },
  { time: '13:31', rule: 'VOLUME ANOMALY', market: 'Iraq win on 2026-06-22', value: '×4.2 hourly', venue: 'Polymarket', watched: false },
  { time: '12:47', rule: 'RESOLVING SOON', market: 'Korea Republic win on 2026-06-11', value: 'in 61 h', venue: 'Polymarket', watched: true },
  { time: '11:09', rule: 'WHALE PRINT', market: 'Government shutdown before October 2026', value: '$24,800', venue: 'Polymarket', watched: false },
  { time: '10:22', rule: 'TIGHT SPREAD', market: 'US CPI above 3.0% in August 2026', value: '1.8¢', venue: 'Kalshi', watched: false },
  { time: '09:40', rule: 'FAST MOVER', market: 'Germany win on 2026-06-20', value: '-5¢ in 20 min', venue: 'Kalshi', watched: false }
];

export const DEMO_DELIVERIES = [
  { time: '14:18', channel: 'Telegram', message: 'Whale print $18,400 · Brazil win on 2026-06-13', status: 'sent' },
  { time: '14:02', channel: 'Telegram', message: 'Fast mover -7¢ · Fed cuts rates in September 2026', status: 'sent' },
  { time: '13:31', channel: 'Telegram', message: 'Volume anomaly ×4.2 · Iraq win on 2026-06-22', status: 'sent' },
  { time: '12:47', channel: 'Telegram', message: 'Resolving soon · Korea Republic win on 2026-06-11', status: 'muted' },
  { time: '11:09', channel: 'Telegram', message: 'Whale print $24,800 · Government shutdown before October', status: 'failed' }
];

export const STUDIES = [
  { tab: 'Review queue', title: 'Verification queue', stamp: 'frozen 2026-07-14', note: 'Cases the daily run flagged for a human to check, ranked by how much the automated read and the market disagree.', chart: 'CASES PER DAY', stats: [['OPEN CASES','38','21 high priority'],['CLEARED THIS WEEK','126','of 164 raised'],['MEDIAN AGE','2.4d','from raise to verdict'],['AGREEMENT','81%','human vs pipeline']] },
  { tab: 'Category efficiency', title: 'Which categories price things well', stamp: 'frozen 2026-06-30', note: 'Brier score against how many minutes a category needs to price in new information. Lower is better on both axes.', chart: 'BRIER SCORE BY CATEGORY', stats: [['BEST CATEGORY','Macro','Brier 0.118'],['WORST CATEGORY','Celebrity','Brier 0.241'],['MARKETS IN SAMPLE','2,914','resolved only'],['PRICING-IN MEDIAN','37 min','across categories']] },
  { tab: 'Mentions latency', title: 'How fast mentions markets react', stamp: 'frozen 2026-06-30', note: 'Time between a piece of content going live and the market moving more than two cents.', chart: 'MINUTES TO FIRST MOVE', stats: [['MEDIAN LATENCY','11 min','n = 412'],['FASTEST DECILE','92 s','n = 41'],['SLOWEST DECILE','2.1 h','n = 41'],['NO REACTION','18%','never moved 2¢']] },
  { tab: 'Live runs', title: 'Our own bot runs', stamp: 'rolling', note: 'Every bet the research bot placed on paper, with the latency it hit and how the sizing simulation would have done instead.', chart: 'EQUITY OF THE LIVE RUNS', stats: [['RUNS','64','since March'],['HIT RATE','54%','n = 1,208 bets'],['MEDIAN LATENCY','780 ms','signal to order'],['SIM UPLIFT','+3.1%','half Kelly vs flat']] },
  { tab: 'Microstructure', title: 'Order books, recorded', stamp: 'rolling', note: 'A rolling read on the collected books plus the three frozen studies: imbalance, order flow net of costs, and market-maker PnL decomposition.', chart: 'BOOK IMBALANCE VS NEXT MOVE', stats: [['BOOKS RECORDED','1.4m','snapshots'],['RECORDER UPTIME','99.2%','REST + WebSocket'],['IMBALANCE EDGE','+0.4¢','net of fees'],['MM PNL SPLIT','62 / 38','spread vs inventory']] },
  { tab: 'Pilot', title: 'Small-stake field test', stamp: 'pre-registered 2026-05-02', note: 'Rules were frozen before the first trade. Signals are read-only, every decision is manual, and rule adherence is logged per trade.', chart: 'PILOT EQUITY VS RULE ADHERENCE', stats: [['TRADES','87','all manual'],['RULE ADHERENCE','94%','logged per trade'],['STAKE PER TRADE','$25','fixed'],['RESULT','+$212','after 12 weeks']] },
  { tab: 'Pipeline forward', title: 'Forward test of the pipeline', stamp: 'rolling', note: 'The analysis pipeline runs forward on paper with no intervention, so its record cannot be fitted after the fact.', chart: 'FORWARD PAPER EQUITY', stats: [['FORWARD DAYS','118','uninterrupted'],['ENTRIES','341','auto-published'],['BRIER','0.164','vs 0.189 market'],['DRIFT','none','config hash stable']] },
  { tab: 'Methodology', title: 'Method, guardrails and audit', stamp: 'version 4.2', note: 'What each score means, what it does not mean, and how the audit trail is recorded.', chart: '', stats: [] },
  { tab: 'Postmortems', title: 'What went wrong, and what changed because of it', stamp: 'rolling', note: 'Every incident the live runs produced, with what happened, what it cost, and the code that changed as a result.', chart: '', stats: [] }
];

export const STUDY_TABLES = {
  0: { label: 'OPEN CASES', cols: '90px 1fr 110px 130px 120px', head: ['CASE','MARKET','RAISED','DISAGREEMENT','STATUS'], rows: [
    ['#2841','Iraq win on 2026-06-22','3 h ago','32¢','open'],
    ['#2839','Fed cuts rates in September 2026','5 h ago','11¢','open'],
    ['#2836','Government shutdown before October 2026','9 h ago','18¢','in review'],
    ['#2830','Ecuador vs. Curaçao ends in a draw','1 d ago','24¢','open'],
    ['#2822','US CPI above 3.0% in August 2026','2 d ago','7¢','cleared'],
    ['#2818','Crewed Artemis launch slips past 2027','2 d ago','9¢','cleared']
  ]},
  1: { label: 'BY CATEGORY', cols: '1fr 110px 130px 120px 130px', head: ['CATEGORY','BRIER','PRICING-IN','MARKETS','VERDICT'], rows: [
    ['Macro','0.118','22 min','612','efficient'],
    ['Politics','0.141','34 min','486','efficient'],
    ['Sports','0.152','9 min','1,140','fast, noisy'],
    ['Crypto','0.176','41 min','392','slow'],
    ['Science','0.203','3 h','108','thin'],
    ['Celebrity','0.241','5 h','176','avoid']
  ]},
  2: { label: 'MENTIONS EVENTS', cols: '1fr 150px 120px 120px 110px', head: ['CONTENT DROP','MARKET','FIRST MOVE','SIZE','MINUTES'], rows: [
    ['Podcast episode 418','Mentions "recession"','19:04','+6¢','7'],
    ['Late-night monologue','Mentions "tariff"','23:41','+3¢','14'],
    ['Sunday interview','Mentions "shutdown"','11:22','+9¢','4'],
    ['Keynote stream','Mentions "AGI"','17:58','+2¢','31'],
    ['Press briefing','Mentions "rate cut"','15:10','+11¢','2'],
    ['Album drop','Mentions "Grammy"','00:05','none','—']
  ]},
  3: { label: 'EVERY RUN', cols: '80px 110px 1fr 110px 100px 110px', head: ['RUN','DATE','MARKET','LATENCY','STAKE','RESULT'], rows: [
    ['R-064','2026-07-30','Fed cuts rates in September 2026','640 ms','$25','+$18.40'],
    ['R-063','2026-07-29','Government shutdown before October 2026','810 ms','$25','+$6.20'],
    ['R-062','2026-07-29','US CPI above 3.0% in August 2026','1.2 s','$25','-$25.00'],
    ['R-061','2026-07-28','Bitcoin above $150k on Dec 31, 2026','590 ms','$25','+$11.80'],
    ['R-060','2026-07-27','Iraq win on 2026-06-22','740 ms','$25','-$25.00'],
    ['R-059','2026-07-26','ECB holds rates at the September meeting','920 ms','$25','+$9.10'],
    ['R-058','2026-07-25','Korea Republic win on 2026-06-11','1.4 s','$25','+$4.70']
  ]},
  4: { label: 'THE THREE FROZEN STUDIES', cols: '1fr 130px 110px 130px 130px', head: ['STUDY','SAMPLE','RAW EDGE','NET OF FEES','VERDICT'], rows: [
    ['Book imbalance predicts the next tick','480k snapshots','+1.9¢','+0.4¢','holds, thin'],
    ['Order flow after a large print','62k prints','+3.1¢','+0.8¢','holds'],
    ['Market-maker PnL decomposition','14k quotes','—','62/38','spread carries it'],
    ['Spread widening before resolution','9.4k markets','+2.2¢','-0.1¢','gone after fees'],
    ['Queue position value','1.1m orders','+0.7¢','+0.2¢','marginal']
  ]},
  5: { label: 'PILOT TRADES', cols: '80px 110px 1fr 150px 110px', head: ['TRADE','DATE','MARKET','RULE ADHERENCE','RESULT'], rows: [
    ['P-087','2026-07-29','Fed cuts rates in September 2026','full','+$14.00'],
    ['P-086','2026-07-27','Government shutdown before October 2026','full','+$8.50'],
    ['P-085','2026-07-24','Brazil win the 2026 World Cup','entry late by 4 min','-$25.00'],
    ['P-084','2026-07-22','US CPI above 3.0% in August 2026','full','+$21.00'],
    ['P-083','2026-07-19','Bitcoin above $150k on Dec 31, 2026','size off by 20%','+$3.40'],
    ['P-082','2026-07-17','ECB holds rates at the September meeting','full','-$25.00']
  ]},
  6: { label: 'FORWARD LOG', cols: '110px 110px 110px 140px 110px', head: ['DAY','ENTRIES','OUR BRIER','MARKET BRIER','DELTA'], rows: [
    ['2026-07-30','4','0.151','0.183','-0.032'],
    ['2026-07-29','2','0.172','0.166','+0.006'],
    ['2026-07-28','3','0.148','0.191','-0.043'],
    ['2026-07-27','1','0.201','0.204','-0.003'],
    ['2026-07-26','5','0.139','0.178','-0.039'],
    ['2026-07-25','2','0.166','0.188','-0.022']
  ]},
  7: { label: 'WHAT EACH SCORE MEANS', cols: '150px 1fr 1fr 110px', head: ['SCORE','WHAT IT MEANS','WHAT IT DOES NOT MEAN','MIN SAMPLE'], rows: [
    ['Smart score','Ranking on public profit, volume and consistency','That the next trade will win','n ≥ 200'],
    ['Track record','Resolved positions only, with a confidence interval','A forecast of future returns','n ≥ 100'],
    ['Calibration','Whether stated odds matched outcomes','Skill — a coin flip calibrates perfectly','n ≥ 300'],
    ['Insider risk','Timing and funding patterns on public flow','An accusation of wrongdoing','n ≥ 3 wallets']
  ]}
};

export const DEMO_RUN_KPIS = [
  { label: 'RUNS', value: '64', sub: 'one run = one episode', color: '#ffffff' },
  { label: 'BETS', value: '1,208', sub: '654W · 512L · 42 open', color: '#ffffff' },
  { label: 'TOTAL STAKE', value: '$30,200', sub: 'wallet-reconciled', color: '#ffffff' },
  { label: 'REALIZED PNL', value: '+$3,140', sub: 'wallet-reconciled · 2026-07-29', color: '#C8F542' },
  { label: 'OPEN STAKE', value: '$1,050', sub: 'in unresolved markets', color: '#ffffff' }
];

export const DEMO_RUN_CARDS = [
  { profile: 'MENTIONS-V4', mode: 'REAL ORDERS', status: 'RESOLVED', title: 'Episode 418 — recession talk',
    chips: ['drop 19:02:11', 'fill +640 ms', '3 trades before us', 'next trader +2.1 s', 'repriced +6¢ in 30 s'],
    bets: [
      { market: 'Mentions "recession" 3+ times', side: 'Yes', limit: '0.42', fill: '0.44', stake: '$25.00', result: '+$31.80' },
      { market: 'Mentions "soft landing"', side: 'Yes', limit: '0.30', fill: '0.31', stake: '$25.00', result: '-$25.00' }
    ],
    footer: 'Stake $50.00 (log est.) · wallet net +$6.80', missed: '' },
  { profile: 'MENTIONS-V4', mode: 'REAL ORDERS', status: 'RESOLVED', title: 'Sunday interview — shutdown',
    chips: ['drop 11:20:04', 'fill +810 ms', '1 trade before us', 'next trader +5.4 s', 'repriced +9¢ in 30 s'],
    bets: [
      { market: 'Mentions "shutdown"', side: 'Yes', limit: '0.55', fill: '0.56', stake: '$25.00', result: '+$19.60' }
    ],
    footer: 'Stake $25.00 (log est.) · wallet net +$19.60', missed: 'Missed chances (2) — budget exhausted · 1/2 would have won' },
  { profile: 'MENTIONS-V3', mode: 'DRY RUN', status: 'OPEN', title: 'Keynote stream — AGI claims',
    chips: ['drop 17:55:40', 'fill +1.4 s', '11 trades before us', 'next trader +0.6 s', 'repriced +2¢ in 30 s'],
    bets: [
      { market: 'Mentions "AGI" before the demo', side: 'Yes', limit: '0.61', fill: '0.66', stake: '$25.00', result: 'open' }
    ],
    footer: 'Stake $25.00 (log est.) · not settled yet', missed: '' },
  { profile: 'MENTIONS-V4', mode: 'REAL ORDERS', status: 'NO FILLS', title: 'Album drop — award chatter',
    chips: ['drop 00:04:58', 'no fill', 'ask beyond cap at drop time'],
    bets: [],
    footer: 'No bet placed — every checkable market was already priced beyond the ask cap. Discipline over entry without edge.', missed: '' }
];

export const DEMO_TIMING_ROWS = [
  { run: 'R-064', market: 'Mentions "recession" 3+ times', drop: '19:02:11', fill: '19:02:12', lat: 640, before: 3, next: '+2.1 s', rep: 6 },
  { run: 'R-064', market: 'Mentions "soft landing"', drop: '19:02:11', fill: '19:02:12', lat: 720, before: 4, next: '+3.0 s', rep: 3 },
  { run: 'R-063', market: 'Mentions "shutdown"', drop: '11:20:04', fill: '11:20:05', lat: 810, before: 1, next: '+5.4 s', rep: 9 },
  { run: 'R-062', market: 'Mentions "AGI" before the demo', drop: '17:55:40', fill: '17:55:41', lat: 1400, before: 11, next: '+0.6 s', rep: 2 },
  { run: 'R-061', market: 'Mentions "tariff"', drop: '23:41:02', fill: '23:41:03', lat: 590, before: 0, next: '+8.2 s', rep: 4 },
  { run: 'R-060', market: 'Mentions "rate cut"', drop: '15:10:33', fill: '15:10:35', lat: 1900, before: 18, next: '+0.3 s', rep: 1 }
];

export const DEMO_RUN_SIM_ROWS = [
  { name: 'Flat $25 per bet (as run)', net: 3140, roi: 10.4, dd: 12.1, hit: 54, bets: 1208 },
  { name: 'Flat $50 per bet', net: 5980, roi: 9.9, dd: 19.4, hit: 54, bets: 1122 },
  { name: '2% of bankroll', net: 4410, roi: 12.8, dd: 14.6, hit: 54, bets: 1208 },
  { name: 'Half Kelly on the logged edge', net: 6720, roi: 15.9, dd: 21.8, hit: 54, bets: 1141 },
  { name: 'Skip anything above 70¢', net: 3890, roi: 14.2, dd: 9.7, hit: 61, bets: 902 }
];

export const DEMO_CALIB_ROWS = [
  { band: 'under 20¢', n: 184, paid: 14, settled: 19 },
  { band: '20–40¢', n: 296, paid: 31, settled: 34 },
  { band: '40–60¢', n: 341, paid: 49, settled: 47 },
  { band: '60–80¢', n: 262, paid: 68, settled: 61 },
  { band: 'over 80¢', n: 125, paid: 87, settled: 79 }
];

export const DEMO_TRACK_MONTHS = [
  { month: 'July 2026', runs: 14, bets: 261, stake: 6525, net: 940 },
  { month: 'June 2026', runs: 16, bets: 318, stake: 7950, net: 1210 },
  { month: 'May 2026', runs: 12, bets: 240, stake: 6000, net: -320 },
  { month: 'April 2026', runs: 13, bets: 249, stake: 6225, net: 780 },
  { month: 'March 2026', runs: 9, bets: 140, stake: 3500, net: 530 }
];
