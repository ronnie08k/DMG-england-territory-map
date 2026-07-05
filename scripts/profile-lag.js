// Profiles layer-toggle lag on the DMG territory map.
// Usage: node profile-lag.js <url>
const { chromium } = require('playwright');

const URL = process.argv[2] || 'https://dmg-england-territory-map.vercel.app/';
const THROTTLE = 4; // matches b74c633's own 4x CPU throttling baseline

const TOGGLES = [
  { id: '#toggle-heat', label: 'heatmap' },
  { id: '#toggle-points', label: 'rep-territory dots' },
  { id: '#toggle-reps', label: 'rep HQ markers' },
  { id: '#toggle-postcodes', label: 'postcode areas' },
];

async function timeAction(page, actionFn, label) {
  await page.evaluate(() => { window.__longTasks = []; });
  const t0 = Date.now();
  await actionFn();
  // Poll until no long tasks recorded for 250ms, capped at 6s.
  let lastActivity = Date.now();
  let sawAny = false;
  while (Date.now() - lastActivity < 250 && Date.now() - t0 < 6000) {
    const tasks = await page.evaluate(() => {
      const t = window.__longTasks || [];
      window.__longTasks = [];
      return t.map(x => x.duration);
    });
    if (tasks.length) {
      sawAny = true;
      lastActivity = Date.now();
    }
    await page.waitForTimeout(30);
  }
  const total = lastActivity - t0;
  return { label, totalMs: total, sawLongTasks: sawAny };
}

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();
  const cdp = await context.newCDPSession(page);
  await cdp.send('Emulation.setCPUThrottlingRate', { rate: THROTTLE });

  await page.addInitScript(() => {
    window.__longTasks = [];
    try {
      new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          window.__longTasks.push({ startTime: entry.startTime, duration: entry.duration });
        }
      }).observe({ entryTypes: ['longtask'] });
    } catch (e) {}
  });

  console.log(`Navigating to ${URL} (CPU throttle ${THROTTLE}x)...`);
  const navStart = Date.now();
  await page.goto(URL, { waitUntil: 'load' });
  const navMs = Date.now() - navStart;

  // Wait for the page to go quiescent after initial load (covers page-load lag).
  const loadSettle = await timeAction(page, async () => {}, 'initial-load-settle');
  console.log(`\nPage load: navigation ${navMs}ms, settle-after-load ${loadSettle.totalMs}ms (longTasks seen: ${loadSettle.sawLongTasks})`);

  const results = [];
  for (const { id, label } of TOGGLES) {
    const el = await page.$(id);
    if (!el) { console.log(`  [skip] ${id} not found`); continue; }

    // First click (on) - may include lazy-build cost.
    const onResult = await timeAction(page, () => el.click(), `${label}: first ON click`);
    results.push(onResult);
    console.log(`  ${onResult.label}: ${onResult.totalMs}ms (longTasks: ${onResult.sawLongTasks})`);

    // Second click (off) - steady state removal.
    const offResult = await timeAction(page, () => el.click(), `${label}: OFF click`);
    results.push(offResult);
    console.log(`  ${offResult.label}: ${offResult.totalMs}ms (longTasks: ${offResult.sawLongTasks})`);

    // Third click (on again) - steady state redraw, no build cost.
    const on2Result = await timeAction(page, () => el.click(), `${label}: second ON click (steady-state)`);
    results.push(on2Result);
    console.log(`  ${on2Result.label}: ${on2Result.totalMs}ms (longTasks: ${on2Result.sawLongTasks})`);
  }

  console.log('\n=== Summary (sorted slowest first) ===');
  results
    .slice()
    .sort((a, b) => b.totalMs - a.totalMs)
    .forEach(r => console.log(`${r.totalMs.toString().padStart(6)}ms  ${r.label}`));

  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
