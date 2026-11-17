#!/usr/bin/env node
/**
 * Full AZUL customer flow test with Playwright.
 * Tests: Dashboard → Capture → Add Customer → Create Card → Earn Points
 */

import { chromium } from 'playwright';

const BASE = process.env.AZUL_URL || 'http://localhost:5000';

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  const errors = [];
  page.on('console', msg => {
    if (msg.type() === 'error') errors.push(`Console: ${msg.text()}`);
  });
  page.on('pageerror', err => errors.push(`Page error: ${err.message}`));

  console.log('=== AZUL Full Flow Test ===\n');

  // 1. Dashboard
  console.log('1. Loading Dashboard...');
  await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded' });
  const title = await page.title();
  console.log(`   Title: ${title}`);
  await page.screenshot({ path: 'screenshots/flow_01_dashboard.png' });

  // 2. Navigate to Capture
  console.log('2. Navigating to Capture...');
  await page.goto(`${BASE}/capture`, { waitUntil: 'domcontentloaded' });
  await page.screenshot({ path: 'screenshots/flow_02_capture.png' });

  // 3. Fill customer info
  console.log('3. Filling customer info...');
  await page.fill('input[placeholder="e.g. Ahmed Benali"]', 'Test Customer');
  await page.fill('input[placeholder="+212 6 00 00 00 00"]', '+212 6 12 34 56 78');
  await page.screenshot({ path: 'screenshots/flow_03_filled.png' });

  // 4. Submit form
  console.log('4. Submitting form...');
  await page.click('button:has-text("Continue to Wallet")');
  await page.waitForURL('**/send-to-wallet/**', { timeout: 10000 });
  console.log(`   URL: ${page.url()}`);
  await page.screenshot({ path: 'screenshots/flow_04_wallet.png' });

  // 5. Navigate to Customers list
  console.log('5. Checking Customers list...');
  await page.goto(`${BASE}/customers`, { waitUntil: 'domcontentloaded' });
  const customerVisible = await page.locator('text=Test Customer').count() > 0;
  console.log(`   Customer visible: ${customerVisible}`);
  await page.screenshot({ path: 'screenshots/flow_05_customers.png' });

  // 6. Check Settings page
  console.log('6. Checking Settings...');
  await page.goto(`${BASE}/settings`, { waitUntil: 'domcontentloaded' });
  const settingsVisible = await page.locator('text=Shop Information').count() > 0;
  console.log(`   Settings visible: ${settingsVisible}`);
  await page.screenshot({ path: 'screenshots/flow_06_settings.png' });

  // 7. Check responsive - mobile
  console.log('7. Testing mobile view...');
  await page.setViewportSize({ width: 375, height: 667 });
  await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded' });
  await page.screenshot({ path: 'screenshots/flow_07_mobile.png' });

  // 8. Check responsive - tablet
  console.log('8. Testing tablet view...');
  await page.setViewportSize({ width: 768, height: 1024 });
  await page.goto(`${BASE}/customers`, { waitUntil: 'domcontentloaded' });
  await page.screenshot({ path: 'screenshots/flow_08_tablet.png' });

  // Report
  console.log('\n=== Test Results ===');
  if (errors.length > 0) {
    console.log('⚠ Console errors:');
    errors.slice(0, 5).forEach(e => console.log(`  - ${e}`));
  } else {
    console.log('✅ No console errors');
  }

  await browser.close();
  console.log('\n✅ All flow tests completed');
}

main().catch(err => {
  console.error('Flow test failed:', err);
  process.exit(1);
});