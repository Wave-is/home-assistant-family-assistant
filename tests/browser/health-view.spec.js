import { test, expect } from "./control-audit.js";

test("RU mobile health uses localized known and generic unknown labels", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/tests/fixtures/health-view.html?lang=ru&role=owner");
  await page.evaluate(() => window.ready);
  const card = page.locator("family-health-card");
  await expect(card.locator(".health-view")).toContainText("Семейные сводки");
  await expect(card.locator(".health-view")).toContainText("Планировщик");
  await expect(card.locator(".health-view")).toContainText("Другой компонент");
  const text = await card.evaluate((element) => element.shadowRoot.textContent);
  expect(text).not.toMatch(/PRIVATE_MODULE|PRIVATE_STATUS|PRIVATE_EVENT_ID|PRIVATE_RECIPIENT/);
  const titleBox = await card.locator(".health-delivery > strong").first().boundingBox();
  const timeBox = await card.locator(".health-delivery > time").first().boundingBox();
  expect(titleBox).not.toBeNull();
  expect(timeBox).not.toBeNull();
  expect(timeBox.y).toBeGreaterThanOrEqual(titleBox.y + titleBox.height);
  await page.screenshot({ path: "test-results/health-view-ru.png", fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("UK child receives only the fixed parent-only state", async ({ page }) => {
  await page.goto("/tests/fixtures/health-view.html?lang=uk&role=child");
  await page.evaluate(() => window.ready);
  const card = page.locator("family-health-card");
  await expect(card.locator(".health-view")).toContainText("доступні лише батькам");
  await expect(card.getByRole("button")).toHaveCount(0);
  const text = await card.evaluate((element) => element.shadowRoot.textContent);
  expect(text).not.toMatch(/PRIVATE_|Завдання|доставки невідомий/);
});

test("EN uncertain delivery requires duplicate consent and sends the exact command", async ({
  page,
}) => {
  await page.goto("/tests/fixtures/health-view.html?lang=en&role=parent");
  await page.evaluate(() => window.ready);
  const card = page.locator("family-health-card");
  await card.getByRole("button", { name: "Review and resend", exact: true }).click();
  await card.getByLabel("Reason", { exact: true }).fill("Checked the private chat");
  await card.getByRole("button", { name: "Save", exact: true }).click();
  expect(await page.evaluate(() => window.calls.length)).toBe(0);
  await card.getByRole("checkbox").check();
  await card.getByRole("button", { name: "Save", exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.calls.length)).toBe(1);
  const request = await page.evaluate(() => window.calls[0]);
  expect(request.action).toBe("notifications.retry");
  expect(request.payload).toEqual({
    id: "PRIVATE_EVENT_ID_CANARY",
    reason: "Checked the private chat",
    confirmed: true,
  });
  expect(typeof request.operation_id).toBe("string");
  expect(request.operation_id.length).toBeGreaterThan(10);
});
