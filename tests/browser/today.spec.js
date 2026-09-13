import { expect, test } from "./control-audit.js";

const card = (page) => page.locator("family-assistant-card");
const overview = (page) => card(page).locator(".today-overview");

test("EN parent Today is bounded, display-only, and contains no private source detail", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/tests/fixtures/today.html?lang=en&actor=parent");
  await expect(overview(page)).toBeVisible();
  await expect(overview(page)).toContainText("Pack school folder");
  await expect(overview(page)).toContainText("Check homework report");
  await expect(overview(page)).toContainText("Music lesson");
  await expect(overview(page)).toContainText("Mathematics");
  await expect(overview(page)).toContainText("Morning alarm");
  await expect(overview(page)).toContainText("Morning routine");
  await expect(overview(page)).toContainText("Taylor");
  await expect(overview(page)).toContainText("Health signals");
  await expect(overview(page)).toContainText("Current points");
  await expect(overview(page)).not.toContainText(
    "Private pending title not shown",
  );
  await expect(
    card(page).locator("button, input, select, textarea, form"),
  ).toHaveCount(0);
  expect(await page.evaluate(() => window.calls)).toEqual([
    {
      type: "family_assistant/view",
      entry_id: "synthetic-today",
    },
  ]);
  const text = await overview(page).textContent();
  expect(text).not.toMatch(/PRIVATE-|media|coordinate|challenge|nonce/);
  await page.screenshot({
    path: "test-results/today-parent-en.png",
    fullPage: true,
  });
});

test("RU narrow child sees only current authorized rows and responsive navigation", async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/tests/fixtures/today.html?lang=ru&actor=child");
  await expect(overview(page)).toBeVisible();
  await expect(overview(page)).toContainText("Mathematics");
  await expect(overview(page)).toContainText("Sam");
  await expect(
    card(page).locator(".today-approvals, .today-health"),
  ).toHaveCount(0);
  await expect(card(page).locator(".today-presence-row")).toHaveCount(1);
  await expect(card(page).locator(".today-balance-row")).toHaveCount(1);
  await expect(overview(page)).not.toContainText("Taylor");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/today-child-ru.png",
    fullPage: true,
  });
});

test("module and role refreshes remove formerly visible overview sections", async ({
  page,
}) => {
  await page.goto("/tests/fixtures/today.html?lang=uk&actor=parent");
  await expect(overview(page)).toContainText("Mathematics");
  await page.evaluate(() => window.disableModule("school"));
  await expect(overview(page)).not.toContainText("Mathematics");
  await expect(
    card(page).locator('.today-agenda-row[data-kind="school"]'),
  ).toHaveCount(0);

  await page.evaluate(() => window.setRole("guest"));
  await expect(
    card(page).locator(".availability-role_unavailable"),
  ).toBeVisible();
  await expect(card(page).locator(".today-overview")).toHaveCount(0);
  const text = await card(page).evaluate(
    (element) => element.shadowRoot.textContent,
  );
  expect(text).not.toMatch(/Pack school|Morning routine|Mathematics|Taylor/);
});

test("disabled projected modules remain hidden even when stale buckets survive locally", async ({
  page,
}) => {
  await page.goto("/tests/fixtures/today.html?lang=en&actor=adult");
  await expect(overview(page)).toContainText("Music lesson");
  await page.evaluate(async () => {
    const stale = window.project();
    window.fixture.modules = ["tasks"];
    stale.settings.modules = ["tasks"];
    window.card._data = stale;
    window.card.render();
  });
  await expect(
    card(page).locator(
      ".today-agenda, .today-shopping, .today-runs, .today-presence, .today-balances",
    ),
  ).toHaveCount(0);
  await expect(overview(page)).not.toContainText("Music lesson");
  await expect(overview(page)).not.toContainText("Morning routine");
});
