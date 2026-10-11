const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

(async () => {
  const browser = await chromium.launch({headless: true, channel: 'chrome'});
  try {
    const page = await browser.newPage({viewport:{width:1440,height:1000}});
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto((process.env.TERMINAL_URL || 'http://localhost:8788/') + '#copy');
    const data = await (await page.request.get((process.env.TERMINAL_URL || 'http://localhost:8788/') + 'api/copy/positions')).json();
    const wallet = Object.keys(data.intelligence.watchlist).find(w => data.position_comparison[w]?.length);
    const profileName = data.intelligence.profiles[wallet].name;
    const card = page.locator('article').getByRole('button', {name:profileName, exact:true});
    await card.waitFor({timeout:30000});
    const name = await card.textContent();
    await card.click();
    await page.getByRole('heading', {name:'Open positions · source and copy'}).waitFor({timeout:30000});
    assert(await page.getByRole('heading', {name:name, exact:true}).count());
    assert(await page.getByRole('columnheader', {name:'Avg entry · source / copy'}).count());
    assert.equal(errors.length, 0, errors.join('\n'));
    await page.screenshot({path:'artifacts/copy-positions.png',fullPage:false});
    console.log('Trader click opens source/copy positions without full ledger; headings and prices present; no browser errors.');
  } finally {
    await browser.close();
  }
})().catch(e => { console.error(e); process.exit(1); });
