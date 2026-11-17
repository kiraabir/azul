#!/usr/bin/env node
/**
 * Drive AZUL web app via chromium-cli
 * This script demonstrates a complete customer -> card flow
 */

import { chromium } from 'playwright';

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  // Navigate to dashboard
  await page.goto('http://localhost:5000/');
  console.log('1. Dashboard loaded');

  // Navigate to capture page
  await page.goto('http://localhost:5000/capture');
  console.log('2. Capture page loaded');

  // Fill customer info
  await page.fill('input[placeholder="e.g. Ahmed Benali"]', 'Ahmed Benali');
  await page.fill('input[placeholder="+212 6 00 00 00 00"]', '+212 6 12 34 56 78');
  console.log('3. Customer info filled');

  // Submit form
  await page.click('button:has-text("Continue to Wallet")');
  console.log('4. Form submitted');

  // Wait for redirect
  await page.waitForURL('**/send-to-wallet/**');
  console.log('5. Wallet page loaded');

  // Screenshot for proof
  await page.screenshot({ path: 'screenshots/customer_flow.png', fullPage: true });
  console.log('6. Screenshot saved');

  await browser.close();
  console.log('Done!');
}

main().catch(console.error);