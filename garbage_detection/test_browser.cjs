// Optional browser smoke test; PLAYWRIGHT_MODULE may point to an existing installation.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');

(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1080 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto('http://127.0.0.1:23071/');
    for (const index of [1, 2, 3, 4]) {
      await page.locator(`[data-camera="camera_${index}"]`).click();
      await page.waitForFunction(id => document.getElementById('camera-status').textContent.includes(`摄像头 ${id} 已连接`), index, { timeout: 60000 });
      await page.waitForFunction(() => !document.getElementById('camera-image').hidden && document.getElementById('camera-image').naturalWidth > 0, null, { timeout: 15000 });
      const response = await page.request.get(`http://127.0.0.1:23071/api/frame.jpg?camera_id=camera_${index}`);
      assert.equal(response.status(), 200, `camera ${index} frame`);
      await page.screenshot({ path: `.runtime/live-camera-${index}.png`, fullPage: true });
    }
    await page.locator('[data-camera="camera_3"]').click();
    await page.waitForFunction(() => document.getElementById('camera-status').textContent.includes('已连接'), { timeout: 60000 });
    await page.locator('#live-tab').click();
    await page.waitForFunction(() => document.getElementById('camera-image').naturalWidth > 0, { timeout: 60000 });
    assert.match(await page.locator('#camera-status').textContent(), /已连接/);
    await page.screenshot({ path: '.runtime/desktop.png', fullPage: true });
    if (await page.locator('#result-tab').isEnabled()) {
      await page.locator('#result-tab').click();
      await page.waitForFunction(() => document.getElementById('result-image').naturalWidth > 0);
      await page.screenshot({ path: '.runtime/real-result.png', fullPage: true });
    }
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    await page.screenshot({ path: '.runtime/mobile.png', fullPage: true });

    // Check overlay rendering and export using an explicit fixture, separate from real inference.
    const frame = await page.request.get('http://127.0.0.1:23071/api/frame.jpg');
    assert.equal(frame.status(), 200);
    const image = (await frame.body()).toString('base64');
    const fixture = { id: 'browser-fixture', captured_at: new Date().toISOString(),
      targets: [{ label: '塑料包装', confidence: 0.85, bbox: [100, 700, 250, 900], region_id: 'r3c1', region_name: '左下' }],
      has_garbage: true, elapsed_seconds: 3.1, image: `data:image/jpeg;base64,${image}`,
      scene_description: '浏览器测试样本', reason: '测试标注布局', map_calibrated: false };
    await page.route('**/api/state?*', route => route.fulfill({ json: { camera: { online: true, captured_at: new Date().toISOString() }, job: { id: fixture.id, state: 'done' }, device: 'cpu' } }));
    await page.route('**/api/result', route => route.fulfill({ json: { result: fixture } }));
    await page.reload();
    await page.waitForSelector('.detection-box');
    assert.equal(await page.locator('#target-count').textContent(), '1个');
    assert.equal(await page.locator('.map-cell.occupied').textContent(), '左下');
    await page.waitForFunction(() => document.getElementById('result-image').naturalWidth > 0);
    const aligned = await page.evaluate(() => {
      const overlay = document.getElementById('frame-overlay').getBoundingClientRect();
      const box = document.querySelector('.detection-box').getBoundingClientRect();
      return Math.abs((box.left - overlay.left) / overlay.width - 0.1) < 0.01;
    });
    assert.equal(aligned, true);
    const downloadReady = page.waitForEvent('download');
    await page.locator('#export-button').click();
    const download = await downloadReady;
    await download.saveAs('.runtime/browser-export.json');
    const exported = JSON.parse(fs.readFileSync('.runtime/browser-export.json'));
    assert.equal(exported.map_calibrated, false);
    assert.equal('image' in exported, false);
    fixture.id = 'unlocalized-fixture';
    fixture.unlocalized = true;
    fixture.targets = [{ label: '纸屑', bbox: null, confidence: null, region_id: null, region_name: '未定位' }];
    await page.reload();
    await page.waitForSelector('#unlocalized:visible');
    assert.match(await page.locator('#target-list').textContent(), /未定位/);
    assert.equal(await page.locator('.detection-box').count(), 0);
    assert.equal(await page.locator('.map-cell.occupied').count(), 0);
    assert.equal(errors.length, 0, errors.join('\n'));
    console.log('Browser checks passed: four real camera previews, desktop/mobile layout, boxes, region map, JSON export.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
