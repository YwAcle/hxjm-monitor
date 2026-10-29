// Run against a simulated demo and a separate hardware-mode web server.
const {chromium, request} = require(process.env.ROBOT_PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const http = require('node:http');

(async () => {
  const browser = await chromium.launch({headless: true, channel: 'msedge'});
  const context = await browser.newContext({viewport: {width: 1560, height: 1100}});
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const hardware = process.env.ROBOT_HARDWARE_TEST_URL || 'http://127.0.0.1:8891';
  const simulated = process.env.ROBOT_TEST_URL || 'http://127.0.0.1:8890';
  const api = await request.newContext({baseURL: hardware});
  let failStream = false;
  const streams = new Set();
  const upstreamRequests = new Set();
  // Sever an actual SSE TCP connection; browser offline emulation can leave an
  // already-open EventSource socket intact in Chromium.
  const proxy = http.createServer((req, res) => {
    const isStream = req.url.startsWith('/api/telemetry/events');
    if (isStream && failStream) { res.writeHead(503); res.end(); return; }
    if (isStream) { streams.add(res); res.on('close', () => streams.delete(res)); }
    const upstream = http.request(new URL(req.url, hardware), {method:req.method, headers:req.headers}, response => {
      res.writeHead(response.statusCode, response.headers);
      response.pipe(res);
    });
    upstreamRequests.add(upstream);
    upstream.on('close', () => upstreamRequests.delete(upstream));
    upstream.on('error', () => res.destroy());
    res.on('close', () => upstream.destroy());
    req.pipe(upstream);
  });
  await new Promise(resolve => proxy.listen(0, '127.0.0.1', resolve));
  const proxyURL = `http://127.0.0.1:${proxy.address().port}`;
  const send = async (device, state) => {
    const response = await api.post(`/api/devices/${device}/state`, {data: {state}});
    assert.equal(response.status(), 200);
  };
  const current = device => page.locator(`#device-${device} .device-current`);
  try {
    await page.goto(proxyURL);
    await page.waitForSelector('#device-dog');
    assert.equal(await current('dog').textContent(), '等待设备状态');
    assert.equal(await current('arm').textContent(), '等待设备状态');
    assert.equal(await page.locator('.state-options .active').count(), 0);
    // A web-only hardware-mode server needs no connected camera for this test;
    // telemetry remains empty until the POSTs below.
    await send('dog', 'adjusting');
    await send('arm', 'holding_return');
    await page.waitForFunction(() => document.querySelector('#device-dog .device-current').textContent === '移动');
    await page.waitForFunction(() => document.querySelector('#device-arm .device-current').textContent === '保持抓取并回到初始位置等待');
    assert((await page.locator('#device-dog .device-description').textContent()).includes('最终抓取位置'));
    assert.equal(await page.locator('.state-options .active').count(), 2);
    for (const state of ['pre_grasp', 'grasping', 'pre_place', 'placing', 'stopped']) {
      await send('arm', state);
      await page.waitForSelector(`#device-arm [data-state="${state}"].active`);
    }
    await page.waitForFunction(() => document.querySelectorAll('.state-options .active').length === 0, {}, {timeout: 10000});
    assert.equal(await current('dog').textContent(), '当前状态未知');
    await send('dog', 'standing');
    await page.waitForSelector('#device-dog [data-state="standing"].active');
    failStream = true;
    for (const response of streams) response.destroy();
    await page.waitForFunction(() => document.querySelector('#device-dog .device-current').textContent === '状态不可用', {}, {timeout: 10000});
    assert.equal(await page.locator('.state-options .active').count(), 0);
    await send('dog', 'navigating');
    failStream = false;
    await page.waitForSelector('#device-dog [data-state="navigating"].active', {timeout: 10000});
    await send('dog', 'unknown');
    await page.waitForFunction(() => document.querySelector('#device-dog .device-current').textContent === '设备上报未知');
    assert.equal(await page.locator('#device-dog .state-options .active').count(), 0);
    // Switch to automatic simulation and confirm it is explicitly marked.
    await page.goto(simulated);
    await page.waitForSelector('#device-arm .state-options .active');
    assert((await page.locator('#device-dog [data-source]').textContent()).includes('非实物状态'));
    assert.equal(await page.locator('#device-dog .state-options li').count(), 4);
    assert.equal(await page.locator('#device-arm .state-options li').count(), 6);
    const first = await current('arm').textContent();
    await page.waitForFunction(before => document.querySelector('#device-arm .device-current').textContent !== before, first, {timeout: 25000});
    for (const size of [{width:1560,height:1100}, {width:800,height:900}, {width:390,height:844}]) {
      await page.setViewportSize(size);
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      assert.equal(await page.locator('.camera-card').count(), 4);
    }
    assert.deepEqual(errors, []);
    const report = {passed: true, checks: ['hardware starts unknown', 'two independent devices update via HTTP and SSE', 'all six arm states render', 'adjusting description matches grasp-position adjustment', 'stale observations remove highlight', 'disconnected browser removes highlight', 'automatic SSE reconnect', 'explicit unknown clears highlight', 'simulation is labeled and advances', '1560/800/390px no horizontal overflow'], pageErrors: errors, hardwareTested: false};
    fs.mkdirSync(path.join(__dirname, '../artifacts'), {recursive: true});
    fs.writeFileSync(path.join(__dirname, '../artifacts/telemetry-browser-report.json'), JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report, null, 2));
  } finally {
    await api.dispose();
    await context.close();
    await browser.close();
    for (const upstream of upstreamRequests) upstream.destroy();
    proxy.closeAllConnections();
    await new Promise(resolve => proxy.close(resolve));
  }
})().catch(error => {console.error(error); process.exitCode = 1;});
