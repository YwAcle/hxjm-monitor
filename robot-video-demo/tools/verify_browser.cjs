// Requires the four-channel simulated demo, Playwright and installed Edge.
const {chromium}=require(process.env.ROBOT_PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
const path=require('node:path');
const fs=require('node:fs');
const crypto=require('node:crypto');
(async()=>{
  const browser=await chromium.launch({headless:true,channel:'msedge'});
  const page=await browser.newPage({viewport:{width:1560,height:1100}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const base=process.env.ROBOT_TEST_URL||'http://127.0.0.1:8890';
  const waitAll=()=>page.waitForFunction(()=>[...document.querySelectorAll('[data-role="frames"]')].length===4&&[...document.querySelectorAll('[data-role="frames"]')].every(n=>Number(n.textContent)>25),{},{timeout:60000});
  const snapshots=()=>page.evaluate(()=>[...document.querySelectorAll('.camera-card')].map(card=>({id:card.id,frames:Number(card.querySelector('[data-role="frames"]').textContent),size:card.querySelector('[data-role="size"]').textContent,fps:card.querySelector('[data-role="fps"]').textContent,online:card.querySelector('.stage').classList.contains('playing')})));
  try{
    await page.goto(base,{waitUntil:'domcontentloaded'});await waitAll();
    assert((await page.locator('#mode').textContent()).includes('四路模拟'));
    assert.equal(await page.locator('#online-count').textContent(),'4 / 4');
    await page.waitForFunction(()=>[...document.querySelectorAll('[data-role="source-diagnostic"]')].length===4&&[...document.querySelectorAll('[data-role="source-diagnostic"]')].every(node=>node.dataset.stage==='forwarding'));
    assert((await page.locator('#camera_1 [data-role="source-diagnostic"]').textContent()).includes('交给 FFmpeg'));
    const first=await snapshots();
    for(const c of first)assert.equal(c.size,'640 × 360');
    await page.waitForFunction(before=>[...document.querySelectorAll('[data-role="frames"]')].every((n,i)=>Number(n.textContent)>before[i].frames+25),first);
    const hashes=[];
    for(const id of ['camera_1','camera_2','camera_3','camera_4']){
      const data=await page.locator(`#${id} video`).screenshot();hashes.push(crypto.createHash('sha256').update(data).digest('hex'));
    }
    assert.equal(new Set(hashes).size,4,'four independent visible test patterns');
    await page.screenshot({path:path.join(__dirname,'../docs/dashboard-preview.png'),fullPage:true});
    const beforeStop=await snapshots();
    await page.locator('#camera_3 .stream-details').evaluate(node=>node.open=true);
    await page.locator('#camera_2 .stream-details').evaluate(node=>node.open=true);
    await page.locator('#camera_3 [data-role="disconnect"]').click();
    assert(await page.locator('#camera_3 video').evaluate(v=>v.srcObject===null));
    await page.waitForFunction(before=>['camera_1','camera_2','camera_4'].every(id=>{const c=document.getElementById(id);return c.querySelector('.stage').classList.contains('playing')&&Number(c.querySelector('[data-role="frames"]').textContent)>before.find(x=>x.id===id).frames+25;}),beforeStop);
    assert.equal(await page.locator('#online-count').textContent(),'3 / 4');
    // Make only channel 3 signaling fail; other channels must continue decoding.
    const pattern='**/live/camera_3/whep';await page.route(pattern,route=>route.abort());
    await page.locator('#camera_3 [data-role="reconnect"]').click();
    await page.waitForFunction(()=>document.querySelector('#camera_3 [data-role="state"]').textContent.includes('重连'));
    const duringFailure=await snapshots();
    await page.waitForFunction(before=>['camera_1','camera_2','camera_4'].every(id=>Number(document.querySelector(`#${id} [data-role="frames"]`).textContent)>before.find(x=>x.id===id).frames+25),duringFailure);
    await page.unroute(pattern);await page.locator('#camera_3 [data-role="reconnect"]').click();await waitAll();
    // Stop while offer/ICE work is in flight, then restart without shared locks.
    await page.locator('#camera_2 [data-role="reconnect"]').click();await page.locator('#camera_2 [data-role="disconnect"]').click();
    assert(await page.locator('#camera_2 video').evaluate(v=>v.srcObject===null));
    await page.locator('#camera_2 [data-role="reconnect"]').click();await waitAll();
    await page.locator('#disconnect-all').click();
    assert(await page.locator('video').evaluateAll(videos=>videos.every(v=>v.srcObject===null)));
    assert.equal(await page.locator('#online-count').textContent(),'0 / 4');
    await page.locator('#reconnect-all').click();await waitAll();
    const metrics=await snapshots();
    for(const size of [{width:1280,height:900},{width:390,height:844}]){
      await page.setViewportSize(size);assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    }
    await page.screenshot({path:path.join(__dirname,'../docs/mobile-preview.png'),fullPage:true});
    assert.deepEqual(errors,[]);
    const report={passed:true,checks:['four independent H.264 -> M20 WebSocket -> RTSP -> WebRTC streams','all decoded frame counts increase','four visibly distinct sources','stop channel 3 leaves other channels decoding','channel 3 WHEP failure isolated and recoverable','stop during negotiation then reconnect','stop all releases tracks, reconnect all resumes','1280px/390px no overflow'],metrics,pageErrors:errors,hardwareTested:false};
    fs.mkdirSync(path.join(__dirname,'../artifacts'),{recursive:true});fs.writeFileSync(path.join(__dirname,'../artifacts/browser-report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));
  }finally{await page.close();await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
