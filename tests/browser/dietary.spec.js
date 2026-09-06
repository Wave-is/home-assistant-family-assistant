import { test, expect } from "@playwright/test";

test("Russian adult reviews exact private edits, retries a lost receipt and shares explicitly", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/tests/fixtures/dietary.html?lang=ru&actor=adult");
  const card = page.locator("family-meals-card");
  await card.getByText("Пищевые предпочтения", { exact: true }).click();
  const own = card.locator('[data-dietary-member="adult"]');
  await own.getByRole("button", { name: "Изменить предпочтения" }).click();
  const edit = card.locator('[data-dietary-form="edit"]');
  await edit.locator('[name="likes"]').fill("Яблоки\nГруши");
  await edit.locator('[name="allergy_note"]').fill("Личная тестовая заметка");
  await edit.getByRole("button", { name: "Проверить изменения" }).click();
  const review = card.locator('[data-dietary-form="save"]');
  await expect(review).toContainText("Alex");
  await expect(review).toContainText("Личная тестовая заметка");
  await expect(review).toContainText("Груши");
  expect(await page.evaluate(() => window.calls.length)).toBe(0);
  await page.screenshot({
    path: "test-results/dietary-review-ru.png",
    fullPage: true,
  });
  await review.locator('[name="reviewed"]').check();
  await page.evaluate(() => (window.loseResponse = true));
  await review
    .getByRole("button", { name: "Подтвердить", exact: true })
    .click();
  await expect(
    review.getByRole("button", { name: "Повторить тот же запрос" }),
  ).toBeVisible();
  // A separate section may replace FamilyCard's generic pending operation.
  await page.evaluate(
    () =>
      (window.card._pending = {
        id: "unrelated-operation",
        fingerprint: "other",
      }),
  );
  await review.getByRole("button", { name: "Повторить тот же запрос" }).click();
  await expect(review).toHaveCount(0);
  const calls = await page.evaluate(() => window.calls);
  expect(calls).toHaveLength(2);
  expect(calls[1]).toEqual(calls[0]);
  expect(await page.evaluate(() => window.records.adult.revision)).toBe(2);
  await card.getByText("Пищевые предпочтения", { exact: true }).click();
  await own
    .getByRole("button", { name: "Поделиться с другими родителями" })
    .click();
  const access = card.locator('[data-dietary-form="access"]');
  expect(
    await page.evaluate(() => window.records.adult.share_with_parents),
  ).toBe(false);
  await access.locator('[name="reviewed"]').check();
  await access
    .getByRole("button", { name: "Подтвердить", exact: true })
    .click();
  await expect(access).toHaveCount(0);
  expect(
    await page.evaluate(() => window.records.adult.share_with_parents),
  ).toBe(true);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("Ukrainian child can read only their own profile without controls", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/tests/fixtures/dietary.html?lang=uk&actor=child");
  const card = page.locator("family-meals-card");
  await card.locator(".dietary-section > summary").click();
  await expect(card.locator('[data-dietary-member="child"]')).toContainText(
    "Pears",
  );
  await expect(card.locator(".dietary-section button")).toHaveCount(0);
  await expect(card).not.toContainText("SYNTHETIC_ADULT_PRIVATE_NOTE");
  await page.screenshot({
    path: "test-results/dietary-child-uk.png",
    fullPage: true,
  });
});

test("Consent revocation removes readonly notes even while an unrelated form has focus", async ({
  page,
}) => {
  await page.goto("/tests/fixtures/dietary.html?lang=en&actor=parent");
  const card = page.locator("family-meals-card");
  await expect(card).toBeVisible();
  await page.evaluate(async () => {
    window.records.adult.share_with_parents = true;
    await window.card.refresh();
  });
  await card.locator(".dietary-section > summary").click();
  await expect(card).toContainText("SYNTHETIC_ADULT_PRIVATE_NOTE");
  await page.evaluate(async () => {
    const form = document.createElement("form"),
      input = document.createElement("input");
    form.append(input);
    window.card.shadowRoot.append(form);
    input.focus();
    window.records.adult.share_with_parents = false;
    await window.card.refresh();
  });
  await expect(card).not.toContainText("SYNTHETIC_ADULT_PRIVATE_NOTE");
  await expect(
    card.locator('[data-dietary-collection="shared_adults"]'),
  ).toHaveCount(0);
  expect(await page.evaluate(() => window.calls.length)).toBe(0);
});

test("Reviewed clear removes content and keeps a versioned empty record", async ({
  page,
}) => {
  await page.goto("/tests/fixtures/dietary.html?lang=en&actor=adult");
  const card = page.locator("family-meals-card");
  await card.locator(".dietary-section > summary").click();
  await card
    .getByRole("button", { name: "Clear profile", exact: true })
    .click();
  const form = card.locator('[data-dietary-form="clear"]');
  await expect(form).toContainText("Alex");
  expect(await page.evaluate(() => window.calls.length)).toBe(0);
  await form.locator('[name="reviewed"]').check();
  await form.getByRole("button", { name: "Confirm", exact: true }).click();
  await expect(form).toHaveCount(0);
  await expect(card).not.toContainText("SYNTHETIC_ADULT_PRIVATE_NOTE");
  expect(await page.evaluate(() => window.records.adult)).toEqual({
    member_id: "adult",
    revision: 2,
    status: "cleared",
    management: "self",
  });
});
