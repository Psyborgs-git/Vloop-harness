/**
 * Performance benchmarks for VLoop Harness
 */

import { test, expect } from '@playwright/test';

test.describe('Performance Benchmarks', () => {
  test('API response time - health check', async ({ request }) => {
    const startTime = Date.now();
    const response = await request.get('http://localhost:8000/');
    const endTime = Date.now();
    const duration = endTime - startTime;

    expect(response.ok()).toBeTruthy();
    expect(duration).toBeLessThan(100); // Should respond in < 100ms
  });

  test('API response time - list components', async ({ request }) => {
    const startTime = Date.now();
    const response = await request.get('http://localhost:8000/api/components');
    const endTime = Date.now();
    const duration = endTime - startTime;

    expect(response.ok()).toBeTruthy();
    expect(duration).toBeLessThan(500); // Should respond in < 500ms
  });

  test('API response time - list agent runs', async ({ request }) => {
    const startTime = Date.now();
    const response = await request.get('http://localhost:8000/api/agent-runs');
    const endTime = Date.now();
    const duration = endTime - startTime;

    expect(response.ok()).toBeTruthy();
    expect(duration).toBeLessThan(500); // Should respond in < 500ms
  });

  test('API response time - metrics summary', async ({ request }) => {
    const startTime = Date.now();
    const response = await request.get('http://localhost:8000/api/metrics/summary');
    const endTime = Date.now();
    const duration = endTime - startTime;

    expect(response.ok()).toBeTruthy();
    expect(duration).toBeLessThan(200); // Should respond in < 200ms
  });

  test('Frontend load time - initial render', async ({ page }) => {
    const startTime = Date.now();
    await page.goto('http://localhost:5173');
    const endTime = Date.now();
    const duration = endTime - startTime;

    await expect(page.locator('text=VLoop Harness')).toBeVisible();
    expect(duration).toBeLessThan(3000); // Should load in < 3s
  });

  test('Frontend load time - chat panel', async ({ page }) => {
    await page.goto('http://localhost:5173');
    
    const startTime = Date.now();
    await page.locator('[data-testid="chat-input"]').waitFor();
    const endTime = Date.now();
    const duration = endTime - startTime;

    expect(duration).toBeLessThan(2000); // Chat panel should load in < 2s
  });

  test('Frontend load time - workspace mode', async ({ page }) => {
    await page.goto('http://localhost:5173');
    
    const startTime = Date.now();
    await page.click('[data-testid="workspace-toggle"]');
    await page.locator('[data-testid="workspace-area"]').waitFor();
    const endTime = Date.now();
    const duration = endTime - startTime;

    expect(duration).toBeLessThan(1000); // Workspace should open in < 1s
  });

  test('Memory usage - repeated API calls', async ({ request }) => {
    const iterations = 100;
    const durations: number[] = [];

    for (let i = 0; i < iterations; i++) {
      const startTime = Date.now();
      await request.get('http://localhost:8000/api/components');
      const endTime = Date.now();
      durations.push(endTime - startTime);
    }

    const avgDuration = durations.reduce((a, b) => a + b, 0) / durations.length;
    const maxDuration = Math.max(...durations);

    expect(avgDuration).toBeLessThan(300); // Average should be < 300ms
    expect(maxDuration).toBeLessThan(1000); // Max should be < 1s
  });

  test('Concurrent requests - load test', async ({ request }) => {
    const concurrent = 10;
    const startTime = Date.now();

    const promises = Array.from({ length: concurrent }, () =>
      request.get('http://localhost:8000/api/components')
    );

    await Promise.all(promises);
    const endTime = Date.now();
    const duration = endTime - startTime;

    expect(duration).toBeLessThan(2000); // All requests should complete in < 2s
  });
});
