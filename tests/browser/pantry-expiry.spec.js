import { test, expect } from "@playwright/test";

test("Russian parent expiry policy is readable, static and owner-configured", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/tests/fixtures/pantry.html?lang=ru&actor=parent");
  const card = page.locator("family-pantry-card");
  const info = card.locator("[data-pantry-expiry-info]");
  await expect(info.locator("summary")).toContainText("Отключены");
  await page.evaluate(async () => {
    Object.assign(window.fixture.settings, {
      pantry_expiry_reminders: true,
      pantry_expiry_days: 0,
      timezone: "Europe/Kyiv",
    });
    await window.card.refresh();
    window.card.render();
  });
  await info.locator("summary").click();
  await expect(info).toContainText("Включены");
  await expect(info).toContainText("только в указанную дату");
  await expect(info).toContainText("09:00");
  await expect(info).toContainText("Europe/Kyiv");
  await expect(info).toContainText("не списывает остатки");
  await expect(info).toContainText("Владелец пространства");
  await expect(info.locator("button,input,select,form")).toHaveCount(0);
  expect(await page.evaluate(() => window.calls.length)).toBe(0);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/pantry-expiry-ru.png",
    fullPage: true,
  });
});

test("Ukrainian child does not receive the private expiry policy block", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/tests/fixtures/pantry.html?lang=uk&actor=child");
  const card = page.locator("family-pantry-card");
  await expect(card).toBeVisible();
  await page.evaluate(async () => {
    Object.assign(window.fixture.settings, {
      pantry_expiry_reminders: true,
      pantry_expiry_days: 3,
    });
    await window.card.refresh();
    window.card.render();
  });
  await expect(card.locator("[data-pantry-expiry-info]")).toHaveCount(0);
  await expect(
    card.getByText("Нагадування про термін придатності", { exact: true }),
  ).toHaveCount(0);
  expect(await page.evaluate(() => window.calls.length)).toBe(0);
  await page.screenshot({
    path: "test-results/pantry-expiry-child-uk.png",
    fullPage: true,
  });
});
