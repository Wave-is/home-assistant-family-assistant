import { test, expect } from "@playwright/test";

const field = (card, name, path = "") =>
  card.locator(
    `[data-condition-field="${name}"][data-condition-path="${path}"]`,
  );

test("Russian nested skip editor retains typed focus and freezes an exact failed command", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/tests/fixtures/routines.html?lang=ru");
  const card = page.locator("family-routines-card");
  await card.getByRole("button", { name: "Изменить", exact: true }).click();
  await field(card, "kind").selectOption("all");
  await field(card, "mode", "0").selectOption("holidays");
  await card
    .locator(".condition-editor")
    .getByRole("button", { name: "Добавить условие", exact: true })
    .click();
  await field(card, "kind", "1").selectOption("any");
  await field(card, "kind", "1.0").selectOption("entity_state");
  const state = field(card, "state", "1.0");
  await state.click();
  await state.pressSequentially("on", { delay: 25 });
  await expect(state).toBeFocused();
  await expect(state).toHaveValue("on");
  await field(card, "negate", "1.0").check();
  await page.evaluate(() => {
    window.failCommand = true;
  });
  await card.getByRole("button", { name: "Сохранить", exact: true }).click();
  await expect(card.getByRole("alert")).toBeVisible();
  const first = await page.evaluate(() => window.calls[0]);
  expect(first.payload.skip_when).toEqual({
    kind: "all",
    negate: false,
    conditions: [
      { kind: "mode", mode: "holidays", negate: false },
      {
        kind: "any",
        negate: false,
        conditions: [
          {
            kind: "entity_state",
            entity_id: "binary_sensor.synthetic_ready",
            state: "on",
            max_age_seconds: 120,
            negate: true,
          },
        ],
      },
    ],
  });
  await expect(field(card, "kind")).toBeDisabled();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/routine-condition-ru.png",
    fullPage: true,
  });
  await page.evaluate(() => {
    window.failCommand = false;
  });
  await card.getByRole("button", { name: "Повторить", exact: true }).click();
  await expect(card.locator(".condition-editor")).toHaveCount(0);
  const calls = await page.evaluate(() => window.calls);
  expect(calls).toHaveLength(2);
  expect(calls[1].operation_id).toBe(calls[0].operation_id);
  expect(calls[1].payload).toEqual(calls[0].payload);
});

test("Ukrainian time condition survives metadata edit and can be explicitly disabled", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/tests/fixtures/routines.html?lang=uk");
  const condition = {
    kind: "time_window",
    start: "22:00",
    end: "08:00",
    timezone: "Europe/Kyiv",
    negate: true,
  };
  await page.evaluate(async (value) => {
    window.fixture.routines.templates[0].skip_when = value;
    await window.card.refresh();
  }, condition);
  const card = page.locator("family-routines-card");
  await card.getByRole("button", { name: "Редагувати", exact: true }).click();
  await card.locator('input[name="title"]').fill("Новий заголовок");
  await expect(field(card, "start")).toHaveValue("22:00");
  await page.screenshot({
    path: "test-results/routine-condition-uk.png",
    fullPage: true,
  });
  await card.getByRole("button", { name: "Зберегти", exact: true }).click();
  expect(await page.evaluate(() => window.calls[0].payload.skip_when)).toEqual(
    condition,
  );
  await card.getByRole("button", { name: "Редагувати", exact: true }).click();
  await field(card, "kind").selectOption("");
  await expect(field(card, "start")).toHaveCount(0);
  await card.getByRole("button", { name: "Зберегти", exact: true }).click();
  expect(
    await page.evaluate(() => window.calls[1].payload.skip_when),
  ).toBeNull();
});

test("fresh allowlist revocation blocks an existing condition without sending a mutation", async ({
  page,
}) => {
  await page.goto("/tests/fixtures/routines.html");
  const card = page.locator("family-routines-card");
  await card.getByRole("button", { name: "Edit", exact: true }).click();
  await field(card, "kind").selectOption("entity_state");
  await field(card, "state").fill("on");
  await page.evaluate(async () => {
    window.fixture.routines.config.entity_allowlist = [];
    await window.card.refresh();
  });
  await card.getByRole("button", { name: "Save", exact: true }).click();
  await expect(card.getByRole("alert")).toContainText(
    "Check the skip condition",
  );
  expect(await page.evaluate(() => window.calls.length)).toBe(0);
  await expect(field(card, "state")).toHaveValue("on");
});
