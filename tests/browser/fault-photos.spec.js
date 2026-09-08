import { test, expect } from "@playwright/test";
import { FAULT_PHOTO_COPY } from "../../custom_components/family_assistant/frontend/fault-photo-copy.js";
const png = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aX1sAAAAASUVORK5CYII=", "base64");
async function upload(page, lang = "en") {
  const copy = FAULT_PHOTO_COPY[lang], card = page.locator("family-maintenance-card");
  await card.getByRole("button", { name: copy.add, exact: true }).click();
  await card.locator('input[type="file"]').setInputFiles({ name: "synthetic.png", mimeType: "image/png", buffer: png });
  await card.getByRole("button", { name: copy.upload, exact: true }).click();
  await expect(card).toContainText(copy.ready);
  return card;
}
for (const lang of ["ru", "uk", "en"]) test(`${lang} mobile fault photo review and explicit private download`, async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/tests/fixtures/fault-photos.html?lang=${lang}`);
  const copy = FAULT_PHOTO_COPY[lang], card = await upload(page, lang);
  await expect(card.locator(".fault-photo img")).toBeVisible();
  expect(await page.evaluate(() => window.fixture.calls.length)).toBe(1);
  expect(await card.evaluate((node) => node.scrollWidth <= node.clientWidth + 1)).toBe(true);
  await page.screenshot({ path: `test-results/fault-photo-review-${lang}.png`, fullPage: true });
  await card.locator('[name="reviewed"]').check();
  await card.getByRole("button", { name: copy.attach, exact: true }).click();
  await expect(card.locator("[data-fault-photo-form]")).toHaveCount(0);
  expect(await page.evaluate(() => window.fixture.state.maintenance.faults[0].task_status)).toBe("assigned");
  expect(await page.evaluate(() => window.fixture.http.length)).toBe(1);
  await card.getByRole("button", { name: copy.view, exact: true }).click();
  await expect(card.locator(".fault-photo img")).toBeVisible();
  await expect.poll(() => card.locator(".fault-photo img").evaluate((node) => node.complete && node.naturalWidth > 0)).toBe(true);
  await page.evaluate(async () => { window.fixture.state.members.find((item) => item.id === "child").revision++; await window.fixture.card.refresh(); });
  await expect(card.locator(".fault-photo img")).toHaveCount(0);
});
test("owner reviews a purge reason, recovers a lost response and preserves the task", async ({ page }) => {
  await page.goto("/tests/fixtures/fault-photos.html?role=owner");
  const copy = FAULT_PHOTO_COPY.en, card = await upload(page);
  await card.locator('[name="reviewed"]').check(); await card.getByRole("button", { name: copy.attach, exact: true }).click();
  await card.getByRole("button", { name: copy.purge, exact: true }).click();
  await card.locator('[name="reason"]').fill("Synthetic obsolete photograph");
  await page.evaluate(() => window.fixture.lose.add("maintenance.fault_photo_purge"));
  await card.locator('[name="reviewed"]').check(); await card.getByRole("button", { name: copy.purge, exact: true }).click();
  await expect(card.getByRole("button", { name: copy.retry, exact: true })).toBeVisible();
  await expect(card.locator('[name="reason"]')).toBeDisabled();
  await card.getByRole("button", { name: copy.retry, exact: true }).click();
  await expect(card.locator("[data-fault-photo-form]")).toHaveCount(0);
  const calls = await page.evaluate(() => window.fixture.calls);
  expect(calls.at(-1)).toEqual(calls.at(-2));
  expect(await page.evaluate(() => window.fixture.state.maintenance.faults[0].task_status)).toBe("assigned");
});
