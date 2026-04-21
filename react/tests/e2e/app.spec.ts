import { test, expect, type Page } from "@playwright/test";

// Simulate what FastAPI's injector.py injects in production
async function setup(page: Page) {
  await page.addInitScript(() => {
    (window as any).__HARNESS__ = {
      COMPONENT_ID: "root",
      API_URL: "http://localhost:8000/api/root",
      WS_URL: "ws://localhost:8000/ws/root",
      INITIAL_STATE: {},
      PERMISSIONS: [],
    };
  });

  // Mock backend API calls — tests run without a live Python server
  await page.route("**/api/providers**", (r) => r.fulfill({ json: [] }));
  await page.route("**/api/chat/sessions**", (r) => r.fulfill({ json: [] }));
  await page.route("**/api/dspy/components**", (r) => r.fulfill({ json: [] }));
  await page.route("**/api/dspy/pipelines**", (r) => r.fulfill({ json: [] }));
  await page.route("**/api/tools**", (r) => r.fulfill({ json: [] }));
  await page.route("**/api/tools/workspace**", (r) =>
    r.fulfill({ json: { workspace_root: "/tmp" } })
  );
  await page.route("**/api/tools/policy**", (r) =>
    r.fulfill({ json: { allow: [], deny: [], permanent_deny: [] } })
  );
  await page.route("**/api/settings**", (r) => r.fulfill({ json: {} }));
  await page.route("**/api/views**", (r) => r.fulfill({ json: [] }));
}

test.describe("VLoop Harness MVP", () => {
  test("page loads with correct title", async ({ page }) => {
    await setup(page);
    await page.goto("/");
    await expect(page).toHaveTitle("Vloop Harness");
  });

  test("React app mounts — #root is not empty", async ({ page }) => {
    await setup(page);
    await page.goto("/");
    await expect(page.locator("#root")).not.toBeEmpty();
  });

  test("AppBar shows brand name", async ({ page }) => {
    await setup(page);
    await page.goto("/");
    await expect(page.getByText("VLoop Harness").first()).toBeVisible();
  });

  test("chat-first render — no DSPy/Pipelines/Tools/Settings nav tabs", async ({ page }) => {
    await setup(page);
    await page.goto("/");
    // Sidebar nav tabs for DSPy, Pipelines, Tools, Settings are removed
    await expect(page.getByRole("button", { name: /DSPy Components/i })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /^Pipelines$/i })).toHaveCount(0);
    // Settings gear icon button is in the AppBar
    await expect(page.locator("[data-testid='SettingsIcon'], [aria-label='Settings']")).not.toHaveCount(0);
  });

  test("composer shows Tools, Components, and New View action buttons", async ({ page }) => {
    await page.addInitScript(() => {
      (window as any).__HARNESS__ = {
        COMPONENT_ID: "root",
        API_URL: "http://localhost:8000/api/root",
        WS_URL: "ws://localhost:8000/ws/root",
        INITIAL_STATE: {},
        PERMISSIONS: [],
      };
    });
    await page.route("**/api/providers**", (r) => r.fulfill({ json: [] }));
    await page.route("**/api/chat/sessions**", (r) =>
      r.fulfill({ json: [{ id: "s1", title: "Test", created_at: new Date().toISOString(), updated_at: new Date().toISOString() }] })
    );
    await page.route("**/api/chat/sessions/s1/messages**", (r) => r.fulfill({ json: [] }));
    await page.route("**/api/dspy/components**", (r) => r.fulfill({ json: [] }));
    await page.route("**/api/dspy/pipelines**", (r) => r.fulfill({ json: [] }));
    await page.route("**/api/tools**", (r) => r.fulfill({ json: [] }));
    await page.route("**/api/tools/workspace**", (r) =>
      r.fulfill({ json: { workspace_root: "/tmp" } })
    );
    await page.route("**/api/tools/policy**", (r) =>
      r.fulfill({ json: { allow: [], deny: [], permanent_deny: [] } })
    );
    await page.route("**/api/settings**", (r) => r.fulfill({ json: {} }));
    await page.route("**/api/views**", (r) => r.fulfill({ json: [] }));

    await page.goto("/");
    await expect(page.getByRole("button", { name: /Tools/i }).first()).toBeVisible();
    await expect(page.getByRole("button", { name: /Components/i }).first()).toBeVisible();
    await expect(page.getByRole("button", { name: /New View/i }).first()).toBeVisible();
  });

  test("connection status chip is present", async ({ page }) => {
    await setup(page);
    await page.goto("/");
    await expect(page.getByText(/connected|disconnected/i).first()).toBeVisible();
  });

  test("settings gear opens settings dialog on desktop", async ({ page }) => {
    await setup(page);
    await page.goto("/");
    const gear = page.locator("button[aria-label='Settings'], button:has([data-testid='SettingsIcon'])").first();
    await gear.click();
    // Settings dialog or drawer should appear
    await expect(page.getByText(/AI Providers/i).first()).toBeVisible();
  });

  test("settings gear opens bottom sheet on mobile viewport", async ({ page, browser }) => {
    const mobileCtx = await browser.newContext({ viewport: { width: 390, height: 844 } });
    const mobilePage = await mobileCtx.newPage();
    await mobilePage.addInitScript(() => {
      (window as any).__HARNESS__ = {
        COMPONENT_ID: "root",
        API_URL: "http://localhost:8000/api/root",
        WS_URL: "ws://localhost:8000/ws/root",
        INITIAL_STATE: {},
        PERMISSIONS: [],
      };
    });
    await mobilePage.route("**/**", (r) => r.fulfill({ json: [] }));
    await mobilePage.goto("/");
    const gear = mobilePage.locator("button[aria-label='Settings'], button:has([data-testid='SettingsIcon'])").first();
    await gear.click();
    // Bottom drawer — check Settings heading visible
    await expect(mobilePage.getByText("Settings").first()).toBeVisible();
    await mobileCtx.close();
  });

  test("no uncaught JS errors on load", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (err) => errors.push(err.message));
    await setup(page);
    await page.goto("/");
    await page.waitForTimeout(500);
    expect(errors).toHaveLength(0);
  });
});
