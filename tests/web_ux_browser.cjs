// Local read-only UX regression. Reuse an existing Playwright installation.
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'chrome' });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, colorScheme: 'dark' });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto((process.env.TERMINAL_URL || 'http://localhost:8787/') + '#markets', { waitUntil: 'domcontentloaded' });
    const table = page.getByRole('table', { name: 'Markets', exact: true });
    await table.waitFor();
    await page.evaluate(() => document.fonts.ready);
    assert.ok((await table.boundingBox()).y < 650, 'The market list must be reachable in the first screen');

    const context = page.locator('details[data-key="market-context"]');
    assert.equal(await context.getAttribute('open'), null);
    await context.locator('summary').click();
    assert.equal(await context.getAttribute('open'), '');
    await page.getByRole('button', { name: 'Switch to light theme' }).click();
    assert.equal(await context.getAttribute('open'), '', 'Context remains open across rerenders');
    await context.locator('summary').click();

    await page.getByRole('button', { name: /^All filters/ }).click();
    await page.getByRole('button', { name: 'Polymarket', exact: true }).click();
    const query = page.getByRole('textbox', { name: 'Search markets', exact: true });
    await query.fill('zzzz-no-matching-market-ux');
    await page.getByRole('heading', { name: 'No matching markets' }).waitFor();
    await page.getByRole('button', { name: 'Clear search', exact: true }).click();
    assert.equal(await query.inputValue(), '');
    assert.equal(await page.evaluate(() => document.activeElement.dataset.key), 'marketQuery');
    assert.equal(await page.getByRole('button', { name: 'Polymarket', exact: true }).getAttribute('aria-pressed'), 'true');
    await query.fill('zzzz-no-matching-market-ux');
    await page.getByRole('heading', { name: 'No matching markets' }).waitFor();
    await page.getByRole('button', { name: 'Reset filters', exact: true }).last().click();
    assert.equal(await query.inputValue(), '');
    assert.equal(await page.evaluate(() => document.activeElement.dataset.key), 'marketQuery');
    assert.equal(await page.getByRole('button', { name: 'Polymarket', exact: true }).getAttribute('aria-pressed'), 'false');
    await page.getByRole('button', { name: /^All filters/ }).click();

    const row = table.locator('[role="row"][data-key]').nth(12);
    await row.focus();
    const rowKey = await row.getAttribute('data-key');
    const scroll = await page.locator('.content').evaluate(el => el.scrollTop);
    assert.ok(scroll > 0, 'Exercise focus return after scrolling down the list');
    await page.keyboard.press('Enter');
    await page.locator('#detail [role="dialog"]').waitFor();
    await page.keyboard.press('Control+k');
    await page.locator('#search [role="dialog"]').waitFor();
    await page.keyboard.press('Escape');
    await page.locator('#search [role="dialog"]').waitFor({ state: 'hidden' });
    assert.equal(await page.locator('#detail [role="dialog"]').isVisible(), true, 'Escape closes the frontmost dialog first');
    await page.keyboard.press('Escape');
    await page.locator('#detail [role="dialog"]').waitFor({ state: 'hidden' });
    assert.equal(await page.evaluate(() => document.activeElement.dataset.key), rowKey);
    assert.equal(await page.locator('.content').evaluate(el => el.scrollTop), scroll);

    await query.focus();
    for (const shortcut of ['Control+k', 'Meta+k']) {
      await page.keyboard.press(shortcut);
      await page.locator('#search [role="dialog"]').waitFor({ timeout: 3000 });
      assert.equal(await page.evaluate(() => document.activeElement.dataset.key), 'searchQuery');
      await page.keyboard.press('Escape');
      await page.locator('#search [role="dialog"]').waitFor({ state: 'hidden' });
      assert.equal(await page.evaluate(() => document.activeElement.dataset.key), 'marketQuery');
    }
    await page.keyboard.press('/');
    assert.equal(await query.inputValue(), '/', 'Typing in an input must not open the command search');
    await query.fill('');
    await page.getByRole('button', { name: 'Search the terminal', exact: true }).click();
    await page.setViewportSize({ width: 1280, height: 600 });
    const dialog = await page.getByRole('dialog', { name: 'Search the terminal' }).boundingBox();
    assert.ok(dialog.y + dialog.height <= 600, 'Search and its close control remain inside a short viewport');
    await page.getByRole('button', { name: 'Close search', exact: true }).click();
    assert.equal(await page.evaluate(() => document.activeElement.dataset.key), 'global-search');
    assert.deepEqual(errors, []);
    console.log('PASS: table-first layout, optional context, zero-result recovery, retained filters, detail focus/scroll return, stacked dialogs, global search shortcuts and short viewport.');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
