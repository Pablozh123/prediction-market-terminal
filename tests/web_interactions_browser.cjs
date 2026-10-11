// Run against the local terminal. PLAYWRIGHT_MODULE may point at an existing
// Playwright installation; no package is added to the application.
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

(async () => {
  const { help: helpMarkup } = await import('../web/js/help.js');
  const markup = helpMarkup('quoted"key', '<img src=x>', 'A "quote" & <script>text</script>');
  assert.doesNotMatch(markup, /<script>|<img/);
  assert.match(markup, /quoted&quot;key/);
  assert.match(markup, /&lt;script&gt;/);
  const browser = await chromium.launch({ headless: true, channel: 'chrome' });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, colorScheme: 'dark' });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(process.env.TERMINAL_URL || 'http://localhost:8787/', { waitUntil: 'domcontentloaded' });
    await page.locator('.research-summary').waitFor();
    await page.evaluate(() => document.fonts.ready);
    const help = page.getByRole('button', { name: 'About frozen studies', exact: true });
    await help.hover({ timeout: 3000 });
    const popup = page.getByRole('tooltip');
    await popup.waitFor({ state: 'visible' });
    assert.match(await popup.innerText(), /historical sample/i);
    await popup.hover();
    await page.waitForTimeout(250);
    assert.equal(await popup.isVisible(), true, 'Help stays visible while the pointer reads it');
    await page.keyboard.press('Escape');
    await popup.waitFor({ state: 'hidden' });
    await help.focus();
    await popup.waitFor({ state: 'visible' });
    assert.equal(await help.getAttribute('aria-describedby'), 'context-help');
    await page.keyboard.press('Escape');
    await popup.waitFor({ state: 'hidden' });
    assert.equal(await help.getAttribute('aria-expanded'), 'false');
    await page.keyboard.press('Enter');
    await popup.waitFor({ state: 'visible' });
    await page.locator('#main h1').click();
    await popup.waitFor({ state: 'hidden' });

    // A selected navigation entry must retain its visible selection on hover.
    const nav = page.getByRole('link', { name: 'Overview', exact: true });
    const selected = await nav.evaluate(el => getComputedStyle(el).backgroundColor);
    await nav.hover();
    await page.waitForTimeout(200);
    assert.equal(await nav.evaluate(el => getComputedStyle(el).backgroundColor), selected);
    await page.getByRole('link', { name: 'Markets', exact: true }).click();
    const option = page.getByRole('button', { name: 'Ending soon', exact: true });
    await option.waitFor();
    const base = await option.evaluate(el => getComputedStyle(el).backgroundColor);
    await option.hover();
    await page.waitForTimeout(200);
    assert.notEqual(await option.evaluate(el => getComputedStyle(el).backgroundColor), base);
    const before = await option.boundingBox();
    await option.click();
    assert.equal(await option.getAttribute('aria-pressed'), 'true');
    assert.deepEqual(await option.boundingBox(), before, 'Selection must not resize a filter');

    const spread = page.getByRole('button', { name: 'About median spread', exact: true });
    for (const theme of ['dark', 'light']) {
      if (theme === 'light') await page.getByRole('button', { name: 'Switch to light theme' }).click();
      await spread.hover();
      await popup.waitFor({ state: 'visible' });
      const box = await popup.boundingBox();
      assert.ok(box.x >= 8 && box.x + box.width <= 1432, 'Help stays inside viewport');
      assert.match(await popup.innerText(), /bid.*ask/i);
      await page.keyboard.press('Escape');
    }
    await page.emulateMedia({ reducedMotion: 'reduce' });
    assert.ok(parseFloat(await option.evaluate(el => getComputedStyle(el).transitionDuration)) < .01);
    assert.deepEqual(errors, []);
    console.log('PASS: hover, stable selection, help by mouse/keyboard, Escape, light-dismiss, viewport bounds and reduced motion.');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
