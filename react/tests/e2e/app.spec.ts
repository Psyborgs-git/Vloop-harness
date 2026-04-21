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

  test("all sidebar navigation items render", async ({ page }) => {
    await setup(page);
    await page.goto("/");
    for (const label of ["Chat", "DSPy Components", "Pipelines", "Tools", "Settings"]) {
      await expect(page.getByText(label).first()).toBeVisible();
    }
  });

  test("connection status chip is present", async ({ page }) => {
    await setup(page);
    await page.goto("/");
    await expect(page.getByText(/connected|disconnected/i).first()).toBeVisible();
  });

  test("clicking sidebar tabs does not crash the app", async ({ page }) => {
    await setup(page);
    await page.goto("/");
    await page.getByText("DSPy Components").first().click();
    await page.getByText("Tools").first().click();
    await page.getByText("Settings").first().click();
    await page.getByText("Chat").first().click();
    await expect(page.getByText("VLoop Harness").first()).toBeVisible();
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
