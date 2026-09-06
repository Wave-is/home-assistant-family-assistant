import { test, expect } from "@playwright/test";

test("Russian mobile parent create/edit retry keeps exact payload and visible draft", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/tests/fixtures/pantry.html?lang=ru&actor=parent");
  const card = page.locator("family-pantry-card");
  await card
    .getByRole("button", { name: "Добавить позицию", exact: true })
    .click();
  await card.getByLabel("Название позиции", { exact: true }).fill("Молоко");
  await card.getByLabel("Единица измерения", { exact: true }).fill("l");
  await card.getByLabel("Текущее количество", { exact: true }).fill("1");
  await card.getByLabel("Минимальный остаток", { exact: true }).fill("3");
  await card
    .getByLabel("Заметка для родителей", { exact: true })
    .fill("Приватная заметка");
  await card.getByLabel("Срок годности", { exact: true }).fill("2026-09-10");
  await page.evaluate(() => (window.failCommand = true));
  await card.getByRole("button", { name: "Сохранить", exact: true }).click();
  await expect(
    card.getByRole("button", { name: "Повторить", exact: true }),
  ).toBeVisible();
  const before = await page.evaluate(() => window.calls[0]);
  expect(before.action).toBe("pantry.item_save");
  expect(before.payload).toMatchObject({
    name: "Молоко",
    unit: "l",
    quantity: 1,
    minimum_quantity: 3,
    note: "Приватная заметка",
    expires_on: "2026-09-10",
  });
  await expect(
    card.getByLabel("Заметка для родителей", { exact: true }),
  ).toHaveValue("Приватная заметка");
  await page.evaluate(() => (window.failCommand = false));
  await card.getByRole("button", { name: "Повторить", exact: true }).click();
  await expect(card.getByText("Молоко", { exact: true }).first()).toBeVisible();
  await card
    .getByRole("button", { name: "Редактировать позицию", exact: true })
    .click();
  await card.getByLabel("Срок годности", { exact: true }).fill("");
  await card
    .getByLabel("Заметка для родителей", { exact: true })
    .fill("Изменённая заметка");
  await page.screenshot({
    path: "test-results/pantry-edit-ru.png",
    fullPage: true,
  });
  await page.evaluate(() => (window.commitThenLose = true));
  await card.getByRole("button", { name: "Сохранить", exact: true }).click();
  await expect(
    card.getByRole("button", { name: "Повторить", exact: true }),
  ).toBeVisible();
  await expect(card.getByLabel("Срок годности", { exact: true })).toHaveValue(
    "",
  );
  const failed = await page.evaluate(() => window.calls.at(-1));
  expect(failed.payload).toEqual(
    expect.objectContaining({
      id: "I000001",
      expires_on: null,
      note: "Изменённая заметка",
    }),
  );
  const editOperation = failed.operation_id;
  await page.evaluate(() => (window.commitThenLose = false));
  await card.getByRole("button", { name: "Повторить", exact: true }).click();
  expect(await page.evaluate(() => window.calls.at(-1).operation_id)).toBe(
    editOperation,
  );
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("Ukrainian child can view stock but cannot see parent note, edit controls, or suggestions", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/tests/fixtures/pantry.html?lang=uk&actor=child");
  const card = page.locator("family-pantry-card");
  await expect(card.getByText("Молоко", { exact: true })).toBeVisible();
  await expect(card.getByText(/1 l/).first()).toBeVisible();
  await expect(
    card.getByRole("button", { name: "Додати позицію", exact: true }),
  ).toHaveCount(0);
  await expect(
    card.getByRole("button", { name: "Редагувати позицію", exact: true }),
  ).toHaveCount(0);
  await expect(
    card.getByText("Приватна нотатка батьків", { exact: false }),
  ).toHaveCount(0);
  await expect(
    card.getByText("Пропозиції для покупок", { exact: true }),
  ).toHaveCount(0);
  await expect(
    card.getByText("Додати до списку покупок", { exact: true }),
  ).toHaveCount(0);
  await page.screenshot({
    path: "test-results/pantry-child-uk.png",
    fullPage: true,
  });
  expect(await page.evaluate(() => window.calls.length)).toBe(0);
});

test("adult stock correction exposes quantity and reason only", async ({
  page,
}) => {
  await page.goto("/tests/fixtures/pantry.html?actor=adult");
  const card = page.locator("family-pantry-card");
  await card.getByRole("button", { name: "Set stock", exact: true }).click();
  await card.getByLabel("Current quantity", { exact: true }).fill("2");
  const callsBefore = await page.evaluate(() => window.calls.length);
  await card.getByRole("button", { name: "Save", exact: true }).click();
  expect(await page.evaluate(() => window.calls.length)).toBe(callsBefore);
  await expect(
    card.getByLabel("Reason for change", { exact: true }),
  ).toBeVisible();
  await expect(card.getByLabel("Item name", { exact: true })).toHaveCount(0);
  await expect(card.getByLabel("Parent note", { exact: true })).toHaveCount(0);
  await card.getByLabel("Reason for change", { exact: true }).fill("Counted");
  await card.getByRole("button", { name: "Save", exact: true }).click();
  const payload = await page.evaluate(() => window.calls.at(-1).payload);
  expect(payload).toMatchObject({
    id: "I000001",
    revision: 1,
    quantity: 2,
    reason: "Counted",
  });
  expect(
    await page.evaluate(() => window.fixture.pantry.items[0].quantity),
  ).toBe(2);
});

test("parent reviews suggestion before accepting shopping-list-only result", async ({
  page,
}) => {
  await page.goto("/tests/fixtures/pantry.html?lang=en&actor=parent");
  const card = page.locator("family-pantry-card");
  await card
    .getByRole("button", { name: "Add pantry item", exact: true })
    .click();
  for (const [label, value] of [
    ["Item name", "Rice"],
    ["Unit of measurement", "kg"],
    ["Current quantity", "0"],
    ["Minimum stock level", "2"],
  ])
    await card.getByLabel(label, { exact: true }).fill(value);
  await card.getByRole("button", { name: "Save", exact: true }).click();
  await expect(
    card.getByText("Shopping suggestions", { exact: true }),
  ).toBeVisible();
  const callsBefore = await page.evaluate(() => window.calls.length);
  await card
    .getByRole("button", { name: "Add to shopping list", exact: true })
    .click();
  await expect(
    card.getByText(/never ordered automatically/i).first(),
  ).toBeVisible();
  const review = card.locator('form[data-pantry-form="suggestion_accept"]');
  await expect(
    review.getByRole("heading", { name: "Rice", exact: true }),
  ).toBeVisible();
  await expect(review.getByText("2 kg", { exact: true })).toBeVisible();
  await page.screenshot({
    path: "test-results/pantry-review-en.png",
    fullPage: true,
  });
  expect(await page.evaluate(() => window.calls.length)).toBe(callsBefore);
  await page.evaluate(() => (window.commitThenLose = true));
  await card
    .locator('form[data-pantry-form="suggestion_accept"] button[type="submit"]')
    .click();
  await expect(
    card.getByRole("button", { name: "Retry", exact: true }),
  ).toBeVisible();
  const acceptOperation = await page.evaluate(
    () => window.calls.at(-1).operation_id,
  );
  await page.evaluate(() => (window.commitThenLose = false));
  await card.getByRole("button", { name: "Retry", exact: true }).click();
  expect(await page.evaluate(() => window.calls.at(-1).operation_id)).toBe(
    acceptOperation,
  );
  expect(await page.evaluate(() => window.fixture.shopping.length)).toBe(1);
  expect(await page.evaluate(() => window.fixture.shopping[0])).toMatchObject({
    status: "approved",
    purchased: 0,
    note: "",
  });
});
