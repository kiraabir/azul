#!/usr/bin/env node
/**
 * Comprehensive Playwright test for AZUL pages.
 * Tests all accessible pages for rendering, navigation, and functionality.
 */

import { chromium } from 'playwright';

const BASE = process.env.AZUL_URL || 'http://localhost:5000';
const results = [];

async function testPage(page, name, url, checks = []) {
  const result = { name, url, status: 'PASS', errors: [] };
  try {
    const response = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 10000 });
    result.httpStatus = response.status();
    if (response.status() >= 400) {
      result.status = 'FAIL';
      result.errors.push(`HTTP ${response.status()}`);
    }

    // Check console errors
    page.on('console', msg => {
      if (msg.type() === 'error') {
        result.errors.push(`Console: ${msg.text()}`);
      }
    });

    // Check for 500 errors
    if (response.status() === 500) {
      result.status = 'FAIL';
      result.errors.push('Server error (500)');
    }

    // Run custom checks
    for (const check of checks) {
      try {
        await check(page);
      } catch (err) {
        result.status = 'FAIL';
        result.errors.push(`Check failed: ${err.message}`);
      }
    }

    // Take screenshot
    await page.screenshot({ path: `screenshots/test_${name.replace(/\s/g, '_')}.png` });
    result.screenshot = `screenshots/test_${name.replace(/\s/g, '_')}.png`;

  } catch (err) {
    result.status = 'FAIL';
    result.errors.push(`Navigation: ${err.message}`);
  }
  results.push(result);
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  console.log('=== AZUL Page Test Suite ===\n');

  // Test Dashboard
  await testPage(page, 'Dashboard', `${BASE}/`, [
    async (p) => {
      const title = await p.title();
      if (!title.includes('AZUL')) throw new Error(`Expected AZUL in title, got: ${title}`);
    }
  ]);

  // Test Customers
  await testPage(page, 'Customers', `${BASE}/customers`);

  // Test Customer Detail (if exists)
  await testPage(page, 'Customer Detail', `${BASE}/customers/1`);

  // Test New Customer
  await testPage(page, 'New Customer', `${BASE}/customers/new`);

  // Test New Card
  await testPage(page, 'New Card', `${BASE}/cards/new`);

  // Test Settings
  await testPage(page, 'Settings', `${BASE}/settings`);

  // Test Capture Info
  await testPage(page, 'Capture Info', `${BASE}/capture`);

  // Test Send to Wallet (if exists)
  await testPage(page, 'Send to Wallet', `${BASE}/send-to-wallet/1`);

  // Test Submit Feedback
  await testPage(page, 'Submit Feedback', `${BASE}/feedback/1`);

  // Test Re-engagement
  await testPage(page, 'Re-engagement', `${BASE}/campaigns/re-engage`);

  // Test Tag Scan
  await testPage(page, 'Tag Scan', `${BASE}/tags/scan`);

  // Test New Tier
  await testPage(page, 'New Tier', `${BASE}/rewards/new`);

  // Test Edit Tier
  await testPage(page, 'Edit Tier', `${BASE}/rewards/1/edit`);

  // Print results
  console.log('\n=== Test Results ===');
  let passed = 0, failed = 0;
  for (const r of results) {
    const icon = r.status === 'PASS' ? '✅' : '❌';
    console.log(`${icon} ${r.name} (${r.httpStatus || 'N/A'})`);
    if (r.errors.length > 0) {
      for (const err of r.errors) {
        console.log(`   ⚠ ${err}`);
      }
    }
    if (r.status === 'PASS') passed++;
    else failed++;
  }

  console.log(`\n${passed} passed, ${failed} failed`);

  await browser.close();
  return failed === 0;
}

main().catch(err => {
  console.error('Test suite failed:', err);
  process.exit(1);
});