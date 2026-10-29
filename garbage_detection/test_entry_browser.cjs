// Run against start.sh's server; probes are mocked only for fallback/failure cases.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { pathToFileURL } = require('node:url');
const path = require('node:path');

(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const entry = pathToFileURL(path.resolve('open.html')).href;
    const lan = 'http://192.168.109.191:23071/';
    const tailscale = 'http://100.127.237.7:23071/';
    // No browser security flags: exercise a saved file against the real two IPs.
    await page.goto(entry);
    await page.waitForURL(lan, { timeout: 15000 });
    await page.locator('.entry-link').waitFor({ state: 'visible' });
    const downloadReady = page.waitForEvent('download');
    await page.locator('.entry-link').click();
    const download = await downloadReady;
    const saved = path.resolve('.runtime/downloaded-entry.html');
    await download.saveAs(saved);
    const content = fs.readFileSync(saved, 'utf8');
    assert.ok(content.includes("Number('23071')"));
    assert.ok(!content.includes('__GARBAGE_PORT__'));
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator('.entry-link').waitFor({ state: 'visible' });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);

    // A client unable to reach the LAN should still enter via Tailscale.
    await page.route('http://192.168.109.191:23071/api/ping.svg?*', route => route.abort());
    await page.goto(pathToFileURL(saved).href);
    await page.waitForURL(tailscale, { timeout: 15000 });

    await page.route('http://100.127.237.7:23071/api/ping.svg?*', route => route.abort());
    await page.goto(entry);
    await page.waitForFunction(() => !document.getElementById('retry').disabled);
    assert.match(await page.locator('#status').textContent(), /两个地址都未检测成功/);
    assert.equal(await page.locator('#addresses a').count(), 2);
    await page.unrouteAll();
    await page.locator('#retry').click();
    await page.waitForURL(lan, { timeout: 15000 });
    assert.deepEqual(errors, []);
    console.log('Entry checks passed: saved file, real LAN access, Tailscale fallback, offline retry, download, mobile layout.');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
