import { test, expect } from "./control-audit.js";

const editor = (card) => card.locator(".alarm-editor");

test("RU mobile edits every schedule field through named review", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/tests/fixtures/alarm-editor.html?lang=ru&role=parent");
  const card = page.locator("family-alarms-card");
  await card.getByRole("button", { name: "Изменить расписание", exact: true }).click();
  await expect(editor(card)).toBeVisible();
  await expect(card.locator('[name="member"]')).toBeFocused();
  await card.locator('[name="time"]').fill("06:55");
  await card.locator('[name="exceptions"]').fill("2026-09-21\n2026-09-28");
  await card.locator('[name="second_min"]').fill("11");
  await card.locator('[name="second_max"]').fill("17");
  await card.locator('[name="recheck_grace"]').fill("50");
  await card.getByRole("button", { name: "Проверить расписание", exact: true }).click();
  await expect(card.locator('[name="confirmed"]')).toBeFocused();
  await expect(card.locator(".alarm-editor-review")).toContainText("Sam");
  await expect(card.locator(".alarm-editor-review")).toContainText("Europe/Kyiv");
  await expect(card.locator(".alarm-editor-review")).toContainText("2026-09-28");
  await card.locator('[name="confirmed"]').check();
  await page.screenshot({ path: "test-results/alarm-editor-review-ru.png", fullPage: true });
  await card.getByRole("button", { name: "Сохранить расписание", exact: true }).click();
  await expect(editor(card)).toHaveCount(0);
  const calls = await page.evaluate(() => window.calls);
  expect(calls).toHaveLength(1);
  expect(calls[0].action).toBe("alarms.save");
  expect(calls[0].payload).toMatchObject({
    id: "A000001", revision: 3, member: "child", time: "06:55",
    exceptions: ["2026-09-21", "2026-09-28"], second_min: 11,
    second_max: 17, recheck_grace: 50, profile: "strict", penalty: -2,
  });
  expect(calls.some((item) => item.action === "alarms.test")).toBe(false);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("UK create is parent-only and includes advanced defaults", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/tests/fixtures/alarm-editor.html?lang=uk&role=parent");
  const card = page.locator("family-alarms-card");
  await card.getByRole("button", { name: "Додати розклад підйому", exact: true }).click();
  await card.locator('[name="name"]').fill("Вихідні");
  await card.locator('[name="member"]').selectOption("child");
  for (const box of await card.locator('[name="days"]').all()) await box.uncheck();
  await card.locator('[name="days"][value="5"]').check();
  await card.locator('[name="days"][value="6"]').check();
  await card.getByRole("button", { name: "Перевірити розклад", exact: true }).click();
  await card.locator('[name="confirmed"]').check();
  await card.getByRole("button", { name: "Створити розклад", exact: true }).click();
  const call = (await page.evaluate(() => window.calls))[0];
  expect(call.payload).toEqual({
    member: "child", name: "Вихідні", time: "07:30", days: [5, 6],
    timezone: "Europe/Kyiv", enabled: true, exceptions: [], second_min: 12,
    second_max: 18, profile: "gentle", recheck_grace: 60, penalty: 0,
  });

  await page.goto("/tests/fixtures/alarm-editor.html?lang=uk&role=child");
  const child = page.locator("family-alarms-card");
  await expect(child.getByRole("button", { name: "Додати розклад підйому", exact: true })).toHaveCount(0);
  await expect(child.getByRole("button", { name: "Змінити розклад", exact: true })).toHaveCount(0);
});

test("named review Back preserves edits and Cancel discards only unsubmitted work", async ({ page }) => {
  await page.goto("/tests/fixtures/alarm-editor.html?lang=en&role=parent");
  const card = page.locator("family-alarms-card");
  await card.getByRole("button", { name: "Edit schedule", exact: true }).click();
  await card.locator('[name="name"]').fill("Keep while going back");
  await card.getByRole("button", { name: "Review schedule", exact: true }).click();
  await card.getByRole("button", { name: "Back", exact: true }).click();
  await expect(card.locator('[name="name"]')).toHaveValue("Keep while going back");
  await card.getByRole("button", { name: "Review schedule", exact: true }).click();
  await expect(card.locator(".alarm-editor-review")).toContainText("Sam");
  await card.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(editor(card)).toHaveCount(0);
  expect(await page.evaluate(() => window.calls.length)).toBe(0);
});

test("committed response loss retries exact frozen edit operation", async ({ page }) => {
  await page.goto("/tests/fixtures/alarm-editor.html?lang=en&role=owner");
  const card = page.locator("family-alarms-card");
  await card.getByRole("button", { name: "Edit schedule", exact: true }).click();
  await card.locator('[name="name"]').fill("Changed once");
  await card.getByRole("button", { name: "Review schedule", exact: true }).click();
  await card.locator('[name="confirmed"]').check();
  await page.evaluate(() => { window.failMode = "after"; });
  await card.getByRole("button", { name: "Save schedule", exact: true }).click();
  await expect(card.getByRole("button", { name: "Retry exact request", exact: true })).toBeVisible();
  await expect(card.getByRole("button", { name: "Cancel", exact: true })).toHaveCount(0);
  await expect(card.getByRole("button", { name: "Back", exact: true })).toHaveCount(0);
  const pending = await page.evaluate(() => structuredClone(window.card._alarmEditorDraft.pending));
  await card.getByRole("button", { name: "Retry exact request", exact: true }).click();
  await expect(editor(card)).toHaveCount(0);
  const calls = await page.evaluate(() => window.calls);
  expect(calls).toHaveLength(2);
  expect(calls[1].operation_id).toBe(pending.operation_id);
  expect(calls[1].payload).toEqual(pending.payload);
  expect(await page.evaluate(() => window.fixture.alarms)).toHaveLength(1);
});

test("stale source, identity, module, and entry changes revoke focused review", async ({ page }) => {
  const mutations = [
    () => { window.fixture.alarms[0].revision += 1; },
    () => { window.fixture.members.find((item) => item.id === "child").revision += 1; },
    () => { window.fixture.settings.modules = []; },
    () => { window.fixture.role = "adult"; window.fixture.members.find((item) => item.id === "parent").role = "adult"; },
  ];
  for (let index = 0; index < mutations.length; index += 1) {
    await page.goto("/tests/fixtures/alarm-editor.html?lang=en&role=parent");
    const card = page.locator("family-alarms-card");
    await card.getByRole("button", { name: "Edit schedule", exact: true }).click();
    await card.getByRole("button", { name: "Review schedule", exact: true }).click();
    await page.evaluate(mutations[index]);
    await page.evaluate(() => window.card.refresh());
    await expect(editor(card)).toHaveCount(0);
    expect(await page.evaluate(() => window.calls.length)).toBe(0);
  }

  await page.goto("/tests/fixtures/alarm-editor.html?lang=en&role=parent");
  const card = page.locator("family-alarms-card");
  await card.getByRole("button", { name: "Edit schedule", exact: true }).click();
  await card.getByRole("button", { name: "Review schedule", exact: true }).click();
  await page.evaluate(() => { window.card._entry = "different-entry"; window.card.render(); });
  await expect(editor(card)).toHaveCount(0);
});
