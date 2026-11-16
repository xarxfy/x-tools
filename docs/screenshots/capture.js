// Takes the screenshots for the README/wiki from a seeded demo instance (see seed.py). Development only.
//   node docs/screenshots/capture.js http://127.0.0.1:18200 docs/screenshots     (needs playwright-core + a Chromium)
const { chromium } = require('playwright-core');
const [base, out] = [process.argv[2], process.argv[3]];
const shots = [
  ['overview', '/', { w: 1280, h: 860 }],
  ['services', '/services', { w: 1280, h: 760 }],
  ['docker', '/docker', { w: 1280, h: 900 }],
  ['servers', '/servers', { w: 1280, h: 760 }],
  ['server', '/servers', { w: 1280, h: 900 }],
  ['proxmox', '/proxmox', { w: 1280, h: 860 }],
  ['customer', null, { w: 1280, h: 1000 }],
  ['jobs', '/jobs', { w: 1280, h: 560 }],
  ['agents', '/settings?tab=agents', { w: 1280, h: 700 }],
  ['backup', '/settings?tab=backup', { w: 1280, h: 900 }],
];
(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROME, args: ['--no-sandbox'] });
  const ctx = await browser.newContext({ locale: 'en-US', viewport: { width: 1280, height: 900 }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  await page.goto(base + '/');
  await page.evaluate(() => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: 'admin', password: 'correct horse battery' }) }));
  for (const [name, path, v] of shots) {
    await page.setViewportSize({ width: v.w, height: v.h });
    if (path) await page.goto(base + path);
    else {
      await page.goto(base + '/customers');
      await page.getByText('ACME Shop GmbH').first().click();
    }
    if (name === 'server') { await page.getByText('web-01').first().click(); await page.getByRole('tab', { name: 'Services' }).click(); }
    await page.waitForTimeout(900);
    await page.screenshot({ path: `${out}/${name}.png` });
  }
  // dark mode and phone
  const dark = await browser.newContext({ locale: 'en-US', viewport: { width: 1280, height: 860 }, colorScheme: 'dark' });
  const dp = await dark.newPage();
  await dp.goto(base + '/');
  await dp.evaluate(() => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: 'admin', password: 'correct horse battery' }) }));
  await dp.goto(base + '/');
  await dp.waitForTimeout(900);
  await dp.screenshot({ path: `${out}/overview-dark.png` });
  const phone = await browser.newContext({ locale: 'en-US', viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 });
  const pp = await phone.newPage();
  await pp.goto(base + '/');
  await pp.evaluate(() => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: 'admin', password: 'correct horse battery' }) }));
  await pp.goto(base + '/');
  await pp.waitForTimeout(900);
  await pp.screenshot({ path: `${out}/overview-phone.png` });
  await browser.close();
})();
