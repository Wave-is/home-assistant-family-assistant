import { test, expect } from "./control-audit.js";

const shell = (card) => card.locator(".availability-shell");

test("RU mobile module-off shell is generic and contains no hidden projection", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/tests/fixtures/availability-shell.html?lang=ru&state=module_disabled");
  await page.evaluate(() => window.ready);
  const card = page.locator("family-polls-card");
  await expect(shell(card)).toHaveAttribute("data-state", "module_disabled");
  await expect(shell(card)).toContainText("Этот модуль выключен для данной семьи.");
  const text = await card.evaluate((element) => element.shadowRoot.textContent);
  expect(text).not.toMatch(/PRIVATE_MEMBER|PRIVATE_NAME|PRIVATE_PAYLOAD|PRIVATE_ERROR/);
  await page.screenshot({ path: "test-results/availability-module-ru.png", fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("UK role-unavailable shell does not reveal a role or private record reason", async ({
  page,
}) => {
  await page.goto("/tests/fixtures/availability-shell.html?lang=uk&state=available");
  await page.evaluate(() => window.ready);
  const card = page.locator("family-polls-card");
  await expect(card.locator(".polls-section")).toHaveCount(1);
  await page.evaluate(() => window.transition("role_unavailable", true));
  await expect(shell(card)).toHaveAttribute("role", "status");
  await expect(shell(card)).toContainText("Ця картка недоступна для цього облікового запису.");
  await expect(shell(card)).not.toContainText(/бать|дит|гість|голосув/i);
  expect(await card.evaluate((element) => element._pollsDraft)).toBe(null);
  const text = await card.evaluate((element) => element.shadowRoot.textContent);
  expect(text).not.toMatch(/PRIVATE_PROJECTION|PRIVATE_DRAFT|PRIVATE_PAYLOAD/);
  await page.screenshot({ path: "test-results/availability-role-uk.png", fullPage: true });
});

test("EN refresh restores the real module after module availability returns", async ({ page }) => {
  await page.goto("/tests/fixtures/availability-shell.html?lang=en&state=available");
  await page.evaluate(() => window.ready);
  const card = page.locator("family-polls-card");
  await expect(card.locator(".polls-section")).toHaveCount(1);
  await expect(shell(card)).toHaveCount(0);
  await page.evaluate(() => window.transition("module_disabled", true));
  await expect(shell(card)).toHaveAttribute("data-state", "module_disabled");
  await expect(card.locator(".polls-section")).toHaveCount(0);
  expect(await card.evaluate((element) => element._pollsDraft)).toBe(null);
  await page.evaluate(() => window.transition("available"));
  await expect(shell(card)).toHaveCount(0);
  await expect(card.locator(".polls-section")).toHaveCount(1);
});
