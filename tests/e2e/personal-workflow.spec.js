import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("vts-model-setup-reviewed", "e2e");
  });
  await page.goto("/");
  await expect(page.locator("header.top-header")).toBeVisible();
});

test("shell has no serious accessibility violations", async ({ page }) => {
  const results = await new AxeBuilder({ page }).analyze();
  const serious = results.violations.filter((item) => ["serious", "critical"].includes(item.impact));
  expect(serious, serious.map((item) => `${item.id}: ${item.help}`).join("\n")).toEqual([]);
});

test("guided mode persists and keeps the all-tools escape hatch", async ({ page }) => {
  await page.locator(".header-more-menu > summary").click();
  await page.locator("[data-experience-mode='guided']").click();
  await expect(page.locator("body")).toHaveAttribute("data-experience-mode", "guided");
  await expect(page.locator("[data-guided-all-tools]")).toBeVisible();
  await page.reload();
  await expect(page.locator("body")).toHaveAttribute("data-experience-mode", "guided");
});

test("assistant dialog moves and restores focus", async ({ page }) => {
  await page.locator(".header-more-menu > summary").click();
  const opener = page.locator("#btn-project-assistant");
  await opener.click();
  const dialog = page.locator("#project-assistant-drawer");
  await expect(dialog).toHaveAttribute("aria-hidden", "false");
  await expect(page.locator("#rag-chat-input")).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveAttribute("aria-hidden", "true");
  await expect(opener).toBeFocused();
});

test("global pages hide project workflow navigation", async ({ page }) => {
  for (const pageId of ["history", "settings", "model-guide"]) {
    await page.locator(`.training-shared-nav [data-page='${pageId}']`).click();
    await expect(page.locator("#training-module-divider")).toBeHidden();
    await expect(page.locator("#cnn-mode-nav")).toBeHidden();
    await expect(page.locator("#rnn-mode-nav")).toBeHidden();
    await expect(page.locator("#tabular-mode-nav")).toBeHidden();
  }
});

test("project workflow pages show the matching project navigation", async ({ page }) => {
  const state = await page.evaluate(async () => {
    const [{ appState }, { renderTrainingModeSidebar }] = await Promise.all([
      import("/static/state.js"),
      import("/static/pages/training_modes.js"),
    ]);
    appState.currentProjectId = "e2e-cnn-project";
    appState.currentProject = { id: appState.currentProjectId, architecture: "cnn" };
    appState.currentPage = "dataset";
    renderTrainingModeSidebar();
    return {
      dividerHidden: document.querySelector("#training-module-divider").classList.contains("hidden"),
      cnnHidden: document.querySelector("#cnn-mode-nav").classList.contains("hidden"),
      rnnHidden: document.querySelector("#rnn-mode-nav").classList.contains("hidden"),
      tabularHidden: document.querySelector("#tabular-mode-nav").classList.contains("hidden"),
    };
  });
  expect(state).toEqual({
    dividerHidden: false,
    cnnHidden: false,
    rnnHidden: true,
    tabularHidden: true,
  });
});

for (const width of [1280, 1100, 841, 840]) {
  test(`responsive shell remains operable at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 800 });
    const sidebar = page.locator("aside.sidebar");
    await expect(sidebar).toBeVisible();
    await expect(page.locator("#header-project-title")).toBeVisible();
    const box = await sidebar.boundingBox();
    expect(box.width).toBeGreaterThanOrEqual(width <= 840 ? 1 : 70);
  });
}

test("reduced motion removes shell transition duration", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  const duration = await page.locator("aside.sidebar").evaluate((node) => getComputedStyle(node).transitionDuration);
  expect(duration.split(",").every((value) => parseFloat(value) === 0)).toBeTruthy();
});

test("project generation aborts delayed responses from the previous project", async ({ page }) => {
  await page.route("**/api/scope-probe/A", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 250));
    await route.fulfill({ json: { project: "A" } });
  });
  await page.route("**/api/scope-probe/B", (route) => route.fulfill({ json: { project: "B" } }));

  const result = await page.evaluate(async () => {
    const [{ projectScope }, { apiFetch }] = await Promise.all([
      import("/static/core/project_scope.js"),
      import("/static/api.js"),
    ]);
    const scopeA = projectScope.begin("A");
    const delayedA = apiFetch("/api/scope-probe/A", { projectScope: scopeA })
      .then((value) => ({ status: "resolved", value }))
      .catch((error) => ({ status: "rejected", name: error.name }));
    await new Promise((resolve) => setTimeout(resolve, 25));
    const scopeB = projectScope.begin("B");
    const currentB = await apiFetch("/api/scope-probe/B", { projectScope: scopeB });
    return { delayedA: await delayedA, currentB, current: projectScope.capture().projectId };
  });

  expect(result.delayedA).toEqual({ status: "rejected", name: "AbortError" });
  expect(result.currentB).toEqual({ project: "B" });
  expect(result.current).toBe("B");
});

test("LabelMe state is derived only from the supplied project", async ({ page }) => {
  const states = await page.evaluate(async () => {
    const { deriveLabelMeState } = await import("/static/state.js");
    return {
      syncedA: deriveLabelMeState({ images: [{ filename: "a.png", status: "annotated" }] }),
      unsyncedB: deriveLabelMeState({ images: [{ filename: "b.png", status: "pending" }] }),
      empty: deriveLabelMeState(null),
    };
  });
  expect(states.syncedA.synced).toBeTruthy();
  expect(states.unsyncedB.synced).toBeFalsy();
  expect(states.empty).toMatchObject({ synced: false, totalImages: 0, jsonCount: 0 });
});
