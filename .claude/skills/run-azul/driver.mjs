#!/usr/bin/env node
/**
 * AZUL driver - demonstrates a complete customer -> card flow.
 * Usage: node .claude/skills/run-azul/driver.mjs
 */

import { chromium } from 'playwright';

const BASE = process.env.AZUL_URL || 'http://localhost:5000';
const OUT = process.env.AZUL_OUT || 'screenshots/customer_flow.png';

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  // 1. Dashboard
  await page.goto(`${BASE}/`);
  console.log('1. Dashboard loaded');

  // 2. Capture page
  await page.goto(`${BASE}/capture`);
  console.log('2. Capture page loaded');

  // 3. Fill customer info
  await page.fill('input[placeholder="e.g. Ahmed Benali"]', 'Ahmed Benali');
  await page.fill('input[placeholder="+212 6 00 00 00 00"]', '+212 6 12 34 56 78');
  console.log('3. Customer info filled');

  // 4. Submit form
  await page.click('button:has-text("Continue to Wallet")');
  console.log('4. Form submitted');

  // 5. Wait for redirect
  await page.waitForURL('**/send-to-wallet/**');
  console.log('5. Wallet page loaded');

  // 6. Screenshot for proof
  await page.screenshot({ path: OUT, fullPage: true });
  console.log(`6. Screenshot saved to ${OUT}`);

  await browser.close();
  console.log('Done!');
}

main().catch((err) => {
  console.error('Driver failed:', err);
  process.exit(1);
});