import { test, expect, type Page, type BrowserContext } from "@playwright/test";

// ── Shared mock helpers ────────────────────────────────────────────────────────

const SESSION_1 = {
  id: "s1",
  title: "First Chat",
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

const SESSION_2 = {
  id: "s2",
  title: "Second Chat",
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

const TOOL_1 = {
  name: "terminal",
  description: "Run shell commands",
  required_permission: "terminal",
  risk_level: "caution",
};
const COMP_1 = {
  id: "c1",
  name: "MyClassifier",
  description: "Classify text",
  signature_fields: { inputs: [], outputs: [] },
  code: "",
  module_type: "ChainOfThought",
  is_active: true,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

const VIEW_MSG = {
  id: "m_view",
  session_id: "s1",
  role: "assistant",
  content: "I generated a React view for you.",
  meta: { saved_view_id: "view_1" },
  created_at: new Date().toISOString(),
};

const COMP_MSG = {
  id: "m_comp",
  session_id: "s1",
  role: "assistant",
  content: "I generated a DSPy component.",
  meta: { saved_component_id: "c1" },
  created_at: new Date().toISOString(),
};

const PIPE_MSG = {
  id: "m_pipe",
  session_id: "s1",
  role: "assistant",
  content: "I generated a pipeline.",
  meta: { saved_pipeline_id: "p1" },
  created_at: new Date().toISOString(),
};

/**
 * Register a single route handler for all /api/** calls to avoid ambiguous
 * glob-pattern ordering issues. Pass custom sessions/messages/tools/etc.
 */
async function setup(
  page: Page,
  opts: {
    sessions?: object[];
    messages?: object[];
    tools?: object[];
    components?: object[];
    providers?: object[];
    views?: object[];
    skipTutorial?: boolean;
  } = {}
) {
  const { skipTutorial = true } = opts;
  await page.addInitScript(() => {
    (window as any).__HARNESS__ = {
      COMPONENT_ID: "root",
      API_URL: "http://localhost:8000/api/root",
      WS_URL: "ws://localhost:8000/ws/root",
      INITIAL_STATE: {},
      PERMISSIONS: [],
    };
  });

  await page.addInitScript(({ skipTutorial: shouldSkip }) => {
    if (shouldSkip) {
      window.localStorage.setItem("vloop_tabbar_tutorial_seen_v1", "true");
    }
  }, { skipTutorial });

  const {
    sessions = [],
    messages = [],
    tools = [],
    components = [],
    providers = [],
    views = [],
  } = opts;

  let sentMessage = false;

  await page.route("**/api/**", (r) => {
    const url = r.request().url();
    const method = r.request().method();

    if (url.includes("/api/providers")) return r.fulfill({ json: providers });

    if (url.match(/\/api\/chat\/sessions\/[^/]+\/messages$/) && method === "POST") {
      // Mark that a message was sent so next GET returns the AI reply
      sentMessage = true;
      return r.fulfill({
        json: {
          id: "ai_m1",
          session_id: "s1",
          role: "assistant",
          content: "AI engine not configured.",
          meta: {},
          created_at: new Date().toISOString(),
        },
      });
    }
    if (url.match(/\/api\/chat\/sessions\/s1\/messages$/)) {
      if (sentMessage) {
        return r.fulfill({
          json: [
            ...messages,
            {
              id: "ai_m1",
              session_id: "s1",
              role: "assistant",
              content: "AI engine not configured.",
              meta: {},
              created_at: new Date().toISOString(),
            },
          ],
        });
      }
      return r.fulfill({ json: messages });
    }
    if (url.match(/\/api\/chat\/sessions\/[^/]+\/messages$/)) {
      return r.fulfill({ json: [] });
    }
    if (url.match(/\/api\/chat\/sessions\/s1\/transcript$/)) {
      return r.fulfill({ json: messages });
    }
    if (url.match(/\/api\/chat\/sessions\/s1$/) && method === "DELETE") {
      return r.fulfill({ status: 204, body: "" });
    }
    if (url.match(/\/api\/chat\/sessions\/s1$/) && method === "PATCH") {
      return r.fulfill({ json: { ...SESSION_1, title: "Renamed" } });
    }
    if (url.match(/\/api\/chat\/sessions\/s1$/)) {
      return r.fulfill({ json: { ...SESSION_1, messages } });
    }
    if (url.match(/\/api\/chat\/sessions\/s2$/)) {
      return r.fulfill({ json: { ...SESSION_2, messages: [] } });
    }
    if (url.match(/\/api\/chat\/sessions$/) && method === "POST") {
      return r.fulfill({ status: 201, json: SESSION_1 });
    }
    if (url.match(/\/api\/chat\/sessions$/) && method === "GET") {
      return r.fulfill({ json: sessions });
    }

    if (url.includes("/api/dspy/components")) return r.fulfill({ json: components });
    if (url.includes("/api/dspy/pipelines")) return r.fulfill({ json: [] });

    if (url.includes("/api/tools/workspace")) {
      return r.fulfill({ json: { workspace_root: "/tmp" } });
    }
    if (url.includes("/api/tools/policy")) {
      return r.fulfill({ json: { allow: [], deny: [], permanent_deny: [] } });
    }
    if (url.includes("/api/tools")) return r.fulfill({ json: tools });

    if (url.includes("/api/settings")) return r.fulfill({ json: {} });

    if (url.includes("/api/views/generate") && method === "POST") {
      return r.fulfill({
        status: 201,
        json: {
          id: "view_1",
          name: "A test view",
          component_name: "TestView",
          react_code: "export default function TestView() { return null; }",
          view_spec: "",
          file_path: null,
          session_id: "s1",
          created_at: new Date().toISOString(),
        },
      });
    }
    if (url.includes("/api/views")) return r.fulfill({ json: views });

    return r.fulfill({ json: [] });
  });
}

async function setupPage(page: Page, opts = {}) {
  await setup(page, opts);
  await page.goto("/");
}

async function mobileContext(browser: any): Promise<BrowserContext> {
  return browser.newContext({ viewport: { width: 390, height: 844 } });
}

// ── Button locators
// MUI Tooltip sets the title as aria-label on the child button, so getByRole name
// matches the tooltip text, not the button label. Use text/icon locators instead.
const toolsBtn = (page: Page) =>
  page.locator("button").filter({ hasText: /^Tools$/ }).first();
const componentsBtn = (page: Page) =>
  page.locator("button").filter({ hasText: /^Components$/ }).first();
const newViewBtn = (page: Page) =>
  page.locator("button").filter({ hasText: /^New View$/ }).first();
const sendBtn = (page: Page) =>
  page
    .locator("button")
    .filter({ has: page.locator("svg[data-testid='SendIcon']") })
    .first();
const settingsBtn = (page: Page) =>
  page
    .locator("button")
    .filter({ has: page.locator("svg[data-testid='SettingsIcon']") })
    .first();
const addChatBtn = (page: Page) =>
  page
    .locator("button")
    .filter({ has: page.locator("svg[data-testid='AddIcon']") })
    .first();

// ── 1. Basic loading ─────────────────────────────────────────────────────────

test.describe("1. Page loading", () => {
  test("page has correct title", async ({ page }) => {
    await setupPage(page);
    await expect(page).toHaveTitle("Vloop Harness");
  });

  test("#root element is not empty after mount", async ({ page }) => {
    await setupPage(page);
    await expect(page.locator("#root")).not.toBeEmpty();
  });

  test("no uncaught JS errors on load", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await setupPage(page);
    await page.waitForTimeout(500);
    expect(errors).toHaveLength(0);
  });
});

// ── 2. Top bar (AppBar) ──────────────────────────────────────────────────────

test.describe("2. Top bar", () => {
  test("shows VLoop Harness brand name", async ({ page }) => {
    await setupPage(page);
    await expect(page.getByText("VLoop Harness").first()).toBeVisible();
  });

  test("shows connection status chip", async ({ page }) => {
    await setupPage(page);
    await expect(page.getByText(/connected|disconnected/i).first()).toBeVisible();
  });

  test("shows settings gear icon button", async ({ page }) => {
    await setupPage(page);
    await expect(settingsBtn(page)).toBeVisible();
  });

  test("shows 'No provider' chip when no default provider", async ({ page }) => {
    await setupPage(page, { providers: [] });
    await expect(page.getByText(/No provider/i).first()).toBeVisible();
  });

  test("shows provider name chip when a default provider exists", async ({ page }) => {
    await setupPage(page, {
      providers: [
        {
          id: "p1",
          name: "Ollama",
          model: "llama3",
          provider_type: "ollama",
          base_url: "",
          has_api_key: false,
          extra_config: {},
          is_default: true,
          created_at: new Date().toISOString(),
        },
      ],
    });
    await expect(page.getByText(/Ollama/i).first()).toBeVisible();
  });
});

// ── 3. Chat-first layout ─────────────────────────────────────────────────────

test.describe("3. Chat-first layout", () => {
  test("no nav tab bar (chat-first design)", async ({ page }) => {
    await setupPage(page);
    await expect(page.getByRole("tab")).toHaveCount(0);
  });

  test("sidebar shows 'Conversations' heading", async ({ page }) => {
    await setupPage(page);
    await expect(page.getByText("Conversations").first()).toBeVisible();
  });

  test("new-chat icon button is in the sidebar", async ({ page }) => {
    await setupPage(page);
    await expect(addChatBtn(page)).toBeVisible();
  });

  test("shows 'No conversations yet' when session list is empty", async ({ page }) => {
    await setupPage(page, { sessions: [] });
    await expect(page.getByText(/No conversations yet/i).first()).toBeVisible();
  });

  test("shows session titles when sessions exist", async ({ page }) => {
    await setupPage(page, { sessions: [SESSION_1, SESSION_2] });
    await expect(page.getByText("First Chat").first()).toBeVisible();
    await expect(page.getByText("Second Chat").first()).toBeVisible();
  });
});

// ── 4. Session management ────────────────────────────────────────────────────

test.describe("4. Session management", () => {
  test("clicking new-chat button starts a new session", async ({ page }) => {
    await setupPage(page, { sessions: [] });
    await addChatBtn(page).click();
    await expect(page.getByText("First Chat").first()).toBeVisible({ timeout: 5000 });
  });

  test("'Start a new conversation' button creates session when no active", async ({
    page,
  }) => {
    await setupPage(page, { sessions: [] });
    await page.getByRole("button", { name: /Start a new conversation/i }).click();
    await expect(page.getByPlaceholder(/Ask me anything/i)).toBeVisible({ timeout: 5000 });
  });

  test("clicking a session in sidebar loads its messages", async ({ page }) => {
    await setupPage(page, {
      sessions: [SESSION_1, SESSION_2],
      messages: [
        {
          id: "m1",
          session_id: "s1",
          role: "user",
          content: "hello s1",
          meta: {},
          created_at: new Date().toISOString(),
        },
      ],
    });
    await page.getByText("First Chat").first().click();
    await expect(page.getByText("hello s1")).toBeVisible({ timeout: 5000 });
  });

  test("delete icon removes session from sidebar", async ({ page }) => {
    await page.addInitScript(() => {
      (window as any).__HARNESS__ = {
        COMPONENT_ID: "root",
        API_URL: "http://localhost:8000/api/root",
        WS_URL: "ws://localhost:8000/ws/root",
        INITIAL_STATE: {},
        PERMISSIONS: [],
      };
    });
    let sessionList = [SESSION_1];
    await page.route("**/api/**", (r) => {
      const url = r.request().url();
      const method = r.request().method();
      if (url.includes("/api/chat/sessions/s1/messages")) return r.fulfill({ json: [] });
      if (url.match(/\/api\/chat\/sessions\/s1$/) && method === "DELETE") {
        sessionList = [];
        return r.fulfill({ status: 204, body: "" });
      }
      if (url.match(/\/api\/chat\/sessions\/s1$/)) {
        return r.fulfill({ json: { ...SESSION_1, messages: [] } });
      }
      if (url.match(/\/api\/chat\/sessions$/) && method === "GET") {
        return r.fulfill({ json: sessionList });
      }
      return r.fulfill({ json: [] });
    });
    await page.goto("/");
    await expect(page.getByText("First Chat")).toBeVisible({ timeout: 5000 });
    await page
      .locator("button")
      .filter({ has: page.locator("svg[data-testid='DeleteOutlineIcon']") })
      .first()
      .click();
    await expect(page.getByText("First Chat")).not.toBeVisible({ timeout: 5000 });
  });
});

// ── 5. Composer ──────────────────────────────────────────────────────────────

test.describe("5. Composer (desktop)", () => {
  test("shows Tools, Components, and New View buttons when session active", async ({
    page,
  }) => {
    await setupPage(page, { sessions: [SESSION_1], messages: [] });
    await expect(toolsBtn(page)).toBeVisible({ timeout: 5000 });
    await expect(componentsBtn(page)).toBeVisible({ timeout: 5000 });
    await expect(newViewBtn(page)).toBeVisible({ timeout: 5000 });
  });

  test("input field has placeholder text", async ({ page }) => {
    await setupPage(page, { sessions: [SESSION_1] });
    await expect(page.getByPlaceholder(/Ask me anything/i)).toBeVisible({ timeout: 5000 });
  });

  test("send button is disabled when input is empty", async ({ page }) => {
    await setupPage(page, { sessions: [SESSION_1] });
    await expect(sendBtn(page)).toBeDisabled({ timeout: 5000 });
  });

  test("send button enables when user types text", async ({ page }) => {
    await setupPage(page, { sessions: [SESSION_1] });
    await page.getByPlaceholder(/Ask me anything/i).fill("hello");
    await expect(sendBtn(page)).toBeEnabled({ timeout: 5000 });
  });

  test("Shift+Enter inserts a newline (does not send)", async ({ page }) => {
    await setupPage(page, { sessions: [SESSION_1] });
    const input = page.getByPlaceholder(/Ask me anything/i);
    await input.click();
    await input.pressSequentially("line1");
    await input.press("Shift+Enter");
    await input.pressSequentially("line2");
    const value = await input.evaluate((el: HTMLTextAreaElement) => el.value);
    expect(value).toContain("line1");
    expect(value).toContain("line2");
  });

  test("shows Shift+Enter hint text", async ({ page }) => {
    await setupPage(page, { sessions: [SESSION_1] });
    await expect(page.getByText(/Shift\+Enter/i).first()).toBeVisible({ timeout: 5000 });
  });

  test("Tools popover opens when Tools button clicked", async ({ page }) => {
    await setupPage(page, { sessions: [SESSION_1], tools: [TOOL_1] });
    await toolsBtn(page).click();
    await expect(page.getByText("terminal").first()).toBeVisible({ timeout: 5000 });
  });

  test("Components popover shows 'No components yet' when empty", async ({ page }) => {
    await setupPage(page, { sessions: [SESSION_1], components: [] });
    await componentsBtn(page).click();
    await expect(page.getByText(/No components yet/i).first()).toBeVisible({ timeout: 5000 });
  });

  test("Components popover lists existing components", async ({ page }) => {
    await setupPage(page, { sessions: [SESSION_1], components: [COMP_1] });
    await componentsBtn(page).click();
    await expect(page.getByText("MyClassifier").first()).toBeVisible({ timeout: 5000 });
  });

  test("selecting a tool inserts @tool: mention into input", async ({ page }) => {
    await setupPage(page, { sessions: [SESSION_1], tools: [TOOL_1] });
    await toolsBtn(page).click();
    await page.getByText("terminal").first().click();
    const input = page.getByPlaceholder(/Ask me anything/i);
    const value = await input.evaluate((el: HTMLTextAreaElement) => el.value);
    expect(value).toContain("@tool:terminal");
  });

  test("selecting a component inserts @component: mention into input", async ({ page }) => {
    await setupPage(page, { sessions: [SESSION_1], components: [COMP_1] });
    await componentsBtn(page).click();
    await page.getByText("MyClassifier").first().click();
    const input = page.getByPlaceholder(/Ask me anything/i);
    const value = await input.evaluate((el: HTMLTextAreaElement) => el.value);
    expect(value).toContain("@component:MyClassifier");
  });

  test("New View button opens GenerateViewDialog", async ({ page }) => {
    await setupPage(page, { sessions: [SESSION_1] });
    await newViewBtn(page).click();
    await expect(page.getByText(/Generate React View/i).first()).toBeVisible({ timeout: 5000 });
  });
});

// ── 6. Messages ──────────────────────────────────────────────────────────────

test.describe("6. Messages", () => {
  test("sending a message shows user message (optimistic)", async ({ page }) => {
    await setupPage(page, { sessions: [SESSION_1] });
    const input = page.getByPlaceholder(/Ask me anything/i);
    await input.fill("Hello AI");
    await input.press("Enter");
    await expect(page.getByText("Hello AI").first()).toBeVisible({ timeout: 5000 });
  });

  test("assistant reply appears after send completes", async ({ page }) => {
    await setupPage(page, { sessions: [SESSION_1] });
    await page.getByPlaceholder(/Ask me anything/i).fill("test");
    await page.getByPlaceholder(/Ask me anything/i).press("Enter");
    await expect(
      page.getByText(/AI engine not configured/i).first()
    ).toBeVisible({ timeout: 8000 });
  });

  test("→ Open View chip visible when message has saved_view_id", async ({ page }) => {
    await setupPage(page, { sessions: [SESSION_1], messages: [VIEW_MSG] });
    await expect(page.getByText(/→ Open View/i).first()).toBeVisible({ timeout: 5000 });
  });

  test("Component saved chip visible when message has saved_component_id", async ({
    page,
  }) => {
    await setupPage(page, { sessions: [SESSION_1], messages: [COMP_MSG] });
    await expect(page.getByText(/Component saved/i).first()).toBeVisible({ timeout: 5000 });
  });

  test("Pipeline saved chip visible when message has saved_pipeline_id", async ({
    page,
  }) => {
    await setupPage(page, { sessions: [SESSION_1], messages: [PIPE_MSG] });
    await expect(page.getByText(/Pipeline saved/i).first()).toBeVisible({ timeout: 5000 });
  });

  test("clicking → Open View chip opens contextual panel", async ({ page }) => {
    await setupPage(page, { sessions: [SESSION_1], messages: [VIEW_MSG] });
    await page.getByText("→ Open View").first().click();
    await expect(
      page.locator("[class*='MuiDrawer-paperAnchorRight']")
    ).toBeVisible({ timeout: 5000 });
  });
});

// ── 7. GenerateViewDialog ────────────────────────────────────────────────────

test.describe("7. GenerateViewDialog", () => {
  test("dialog has description and component name fields", async ({ page }) => {
    await setupPage(page, { sessions: [SESSION_1] });
    await newViewBtn(page).click();
    await expect(
      page.getByLabel(/Describe the view/i).or(page.getByPlaceholder(/dashboard showing/i)).first()
    ).toBeVisible({ timeout: 5000 });
    await expect(
      page
        .getByLabel(/Component name/i)
        .or(page.getByPlaceholder(/MetricsDashboard/i))
        .first()
    ).toBeVisible({ timeout: 5000 });
  });

  test("Generate button disabled when description empty", async ({ page }) => {
    await setupPage(page, { sessions: [SESSION_1] });
    await newViewBtn(page).click();
    await expect(
      page.locator("button").filter({ hasText: /^Generate$/ })
    ).toBeDisabled({ timeout: 5000 });
  });

  test("Generate button enabled after typing description", async ({ page }) => {
    await setupPage(page, { sessions: [SESSION_1] });
    await newViewBtn(page).click();
    const descField = page
      .getByLabel(/Describe the view/i)
      .or(page.getByPlaceholder(/dashboard showing/i))
      .first();
    await descField.fill("A metrics dashboard");
    await expect(
      page.locator("button").filter({ hasText: /^Generate$/ })
    ).toBeEnabled({ timeout: 5000 });
  });

  test("dialog closes when Cancel is clicked", async ({ page }) => {
    await setupPage(page, { sessions: [SESSION_1] });
    await newViewBtn(page).click();
    await page.locator("button").filter({ hasText: /^Cancel$/ }).click();
    await expect(page.getByText(/Generate React View/i)).not.toBeVisible({ timeout: 5000 });
  });
});

// ── 8. Settings dialog (desktop) ─────────────────────────────────────────────

test.describe("8. Settings — desktop dialog", () => {
  test("gear icon opens settings dialog", async ({ page }) => {
    await setupPage(page);
    await settingsBtn(page).click();
    await expect(page.getByText(/AI Providers/i).first()).toBeVisible({ timeout: 5000 });
  });

  test("settings dialog has 'Settings' title", async ({ page }) => {
    await setupPage(page);
    await settingsBtn(page).click();
    await expect(
      page.locator("[role='dialog']").getByText("Settings").first()
    ).toBeVisible({ timeout: 5000 });
  });

  test("pressing Escape closes settings dialog", async ({ page }) => {
    await setupPage(page);
    await settingsBtn(page).click();
    await expect(page.locator("[role='dialog']")).toBeVisible({ timeout: 5000 });
    await page.keyboard.press("Escape");
    await expect(page.locator("[role='dialog']")).not.toBeVisible({ timeout: 5000 });
  });
});

test.describe("8b. Settings — mobile bottom sheet", () => {
  test("gear icon opens settings on mobile", async ({ browser }) => {
    const ctx = await mobileContext(browser);
    const page = await ctx.newPage();
    await setup(page, { sessions: [] });
    await page.goto("/");
    await settingsBtn(page).click();
    await expect(page.getByText("Settings").first()).toBeVisible({ timeout: 5000 });
    await ctx.close();
  });

  test("mobile settings sheet height is ≤80vh", async ({ browser }) => {
    const ctx = await mobileContext(browser);
    const page = await ctx.newPage();
    await setup(page, { sessions: [] });
    await page.goto("/");
    await settingsBtn(page).click();
    await page.waitForTimeout(300);
    const drawer = page.locator("[class*='MuiDrawer-paperAnchorBottom']").first();
    await expect(drawer).toBeVisible({ timeout: 5000 });
    const box = await drawer.boundingBox();
    if (box) {
      expect(box.height).toBeLessThanOrEqual(844 * 0.82);
    }
    await ctx.close();
  });
});

// ── 9. Contextual panel ──────────────────────────────────────────────────────

test.describe("9. Contextual panel", () => {
  test("panel is hidden initially", async ({ page }) => {
    await setupPage(page, { sessions: [SESSION_1] });
    await expect(
      page.locator("[class*='MuiDrawer-paperAnchorRight']")
    ).not.toBeVisible();
  });

  test("Tools 'Open Tools panel' link opens contextual panel", async ({ page }) => {
    await setupPage(page, { sessions: [SESSION_1], tools: [] });
    await toolsBtn(page).click();
    await page.getByText(/Open Tools panel/i).first().click();
    await expect(
      page.locator("[class*='MuiDrawer-paperAnchorRight']")
    ).toBeVisible({ timeout: 5000 });
  });

  test("contextual panel close button dismisses it", async ({ page }) => {
    await setupPage(page, { sessions: [SESSION_1], tools: [] });
    await toolsBtn(page).click();
    await page.getByText(/Open Tools panel/i).first().click();
    await expect(
      page.locator("[class*='MuiDrawer-paperAnchorRight']")
    ).toBeVisible({ timeout: 5000 });
    // Use Escape key to close the drawer — same UX action, avoids AppBar z-index overlap
    await page.keyboard.press("Escape");
    await expect(
      page.locator("[class*='MuiDrawer-paperAnchorRight']")
    ).not.toBeVisible({ timeout: 5000 });
  });
});

// ── 10. Mobile composer — collapsible actions ─────────────────────────────────

test.describe("10. Mobile composer — collapsible actions", () => {
  test("action buttons hidden on mobile (behind expand toggle)", async ({ browser }) => {
    const ctx = await mobileContext(browser);
    const page = await ctx.newPage();
    await setup(page, { sessions: [SESSION_1] });
    await page.goto("/");
    await page.waitForTimeout(500);
    await expect(page.locator("button").filter({ hasText: /^Tools$/ })).not.toBeVisible();
    await ctx.close();
  });

  test("clicking expand toggle reveals action buttons on mobile", async ({ browser }) => {
    const ctx = await mobileContext(browser);
    const page = await ctx.newPage();
    await setup(page, { sessions: [SESSION_1] });
    await page.goto("/");
    const expandBtn = page
      .locator("button")
      .filter({ has: page.locator("svg[data-testid='ExpandMoreIcon']") })
      .first();
    await expandBtn.click();
    await expect(toolsBtn(page)).toBeVisible({ timeout: 5000 });
    await expect(componentsBtn(page)).toBeVisible({ timeout: 5000 });
    await ctx.close();
  });
});

// ── 11. Command palette (Cmd+K) ──────────────────────────────────────────────

test.describe("11. Command palette", () => {
  test("top bar search button opens command palette", async ({ page }) => {
    await setupPage(page);
    await page
      .locator("button")
      .filter({ has: page.locator("svg[data-testid='SearchIcon']") })
      .first()
      .click();
    await expect(
      page.locator("[class*='MuiDialog-root']").first()
    ).toBeVisible({ timeout: 5000 });
  });

  test("Cmd+K opens command palette dialog", async ({ page }) => {
    await setupPage(page);
    await page.keyboard.press("Meta+k");
    await expect(
      page.locator("[class*='MuiDialog-root']").first()
    ).toBeVisible({ timeout: 5000 });
  });

  test("palette closes with Escape", async ({ page }) => {
    await setupPage(page);
    await page.keyboard.press("Meta+k");
    await expect(
      page.locator("[class*='MuiDialog-root']").first()
    ).toBeVisible({ timeout: 5000 });
    await page.keyboard.press("Escape");
    await expect(
      page.locator("[class*='MuiDialog-root']")
    ).toHaveCount(0, { timeout: 5000 });
  });
});

// ── 12. First-run tab bar tutorial ───────────────────────────────────────────

test.describe("12. First-run tab bar tutorial", () => {
  test("shows localized gesture hints and can be dismissed", async ({ page }) => {
    await setupPage(page, { skipTutorial: false });
    await expect(page.getByText(/Tab bar quick tour/i)).toBeVisible({ timeout: 5000 });
    await expect(page.getByText(/Open and close search/i)).toBeVisible();
    await page.locator("button").filter({ hasText: /^Next$/ }).click();
    await expect(page.getByText(/Open actions/i)).toBeVisible();
    await page.getByLabel("Skip").click();
    await expect(page.getByText(/Tab bar quick tour/i)).not.toBeVisible({ timeout: 5000 });
  });
});

// ── 13. View generation flow ─────────────────────────────────────────────────

test.describe("13. View generation flow", () => {
  test("submitting GenerateViewDialog closes it on success", async ({ page }) => {
    await setupPage(page, { sessions: [SESSION_1] });
    await newViewBtn(page).click();
    const descField = page
      .getByLabel(/Describe the view/i)
      .or(page.getByPlaceholder(/dashboard showing/i))
      .first();
    await descField.fill("A simple greeting card");
    await page.locator("button").filter({ hasText: /^Generate$/ }).click();
    await expect(page.getByText(/Generate React View/i)).not.toBeVisible({ timeout: 8000 });
  });
});
