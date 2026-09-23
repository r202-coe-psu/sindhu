// Browser component integration, using real Brython + API routes.
// PLAYWRIGHT_MODULE points to installed playwright; CCTV_BROWSER is optional.
const assert = require('node:assert/strict');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const baseURL = process.env.CCTV_TEST_BASE_URL || 'http://127.0.0.1:18081';
(async () => {
  const browser = await chromium.launch({headless: true, executablePath: process.env.CCTV_BROWSER || undefined});
  try {
    const context = await browser.newContext({baseURL});
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    page.on('console', m => { if (m.type() === 'error') console.error(m.text()); });
    // Only external image loading is mocked; our routes execute normally.
    await page.route('https://hatyaicityclimate.org/**', route => route.fulfill({
      contentType: 'image/png', body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jH1sAAAAASUVORK5CYII=', 'base64')
    }));
    await context.request.post('/_test/state', {data:{failure:null,calls:[],slow_date:null}});
    await page.goto('/');
    await page.waitForFunction(() => window.cctv_test_ready === true);
    assert.ok((await (await context.request.get('/_test/state')).json()).calls.length > 0, 'water-first view loads CCTV once for map markers');
    assert.equal(await page.getByRole('tab', {name:'ระดับน้ำ',exact:true}).getAttribute('aria-selected'), 'true');
    await page.getByRole('tab', {name:'กล้อง / ภาพพื้นที่'}).click();
    await page.waitForFunction(() => document.querySelectorAll('.visual-feed-card').length === 30).catch(async e => {
      console.error('Render diagnostic', await page.locator('#visual_feed_panel').innerText(), errors);
      throw e;
    });
    const card = page.locator('.visual-feed-card').filter({has:page.getByRole('button', {name:'ดูภาพวันนี้',exact:true})}).first();
    await card.getByRole('button', {name:'ดูภาพวันนี้',exact:true}).click();
    await page.getByRole('dialog').waitFor({state:'visible'});
    await page.waitForFunction(() => document.querySelectorAll('#visual_feed_history_frames figure').length === 1);
    assert.equal(await page.locator('#visual_feed_history_counter').textContent(), 'ภาพที่ 2 จาก 2');
    assert.equal(await page.locator('#visual_feed_history_next').isVisible(), false, 'next is hidden on newest frame');
    await page.locator('#visual_feed_history_previous').click();
    assert.equal(await page.locator('#visual_feed_history_counter').textContent(), 'ภาพที่ 1 จาก 2');
    assert.equal(await page.locator('#visual_feed_history_previous').isVisible(), false, 'previous is hidden on oldest frame');
    assert.equal(await page.locator('#visual_feed_history_next').isVisible(), true);
    const dateState = page.locator('#visual_feed_history_date');
    const latest = await dateState.getAttribute('max');
    const previous = new Date(latest+'T00:00:00Z'); previous.setUTCDate(previous.getUTCDate()-1);
    const older = new Date(previous); older.setUTCDate(older.getUTCDate()-1);
    await context.request.post('/_test/state',{data:{slow_date:previous.toISOString().slice(0,10)}});
    const slowResponse = page.waitForResponse(r => r.url().includes('/history?date='+previous.toISOString().slice(0,10)));
    await page.locator('#visual_feed_7days_rail [data-date="'+previous.toISOString().slice(0,10)+'"]').click();
    await page.locator('#visual_feed_7days_rail [data-date="'+older.toISOString().slice(0,10)+'"]').click();
    await slowResponse;
    await page.waitForFunction(() => document.querySelector('#visual_feed_history_counter')?.textContent === 'ภาพที่ 2 จาก 2');
    assert.equal(await page.locator('#visual_feed_7days_rail [aria-selected="true"]').getAttribute('data-date'), older.toISOString().slice(0,10), 'late response cannot change selected date');
    const historyCalls = (await (await context.request.get('/_test/state')).json()).calls.length;
    await page.clock.install();
    await page.clock.fastForward(121000);
    assert.equal((await (await context.request.get('/_test/state')).json()).calls.length,historyCalls,'history must not poll latest');
    await page.keyboard.press('Escape');
    await page.getByRole('dialog').waitFor({state:'hidden'});
    await page.getByRole('tab',{name:'ระดับน้ำ',exact:true}).click();
    const before = (await (await context.request.get('/_test/state')).json()).calls.length;
    await page.clock.fastForward(121000);
    assert.equal((await (await context.request.get('/_test/state')).json()).calls.length,before,'water tab must not poll CCTV');
    assert.deepEqual(errors,[]);
    console.log('PASS: water-first load, 30 online CCTV cards, carousel history, late response guard, Escape, hidden polling, no page errors');
  } finally {await browser.close();}
})().catch(e => {console.error(e);process.exitCode=1;});
