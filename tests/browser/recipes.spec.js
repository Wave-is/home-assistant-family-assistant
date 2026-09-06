import { test, expect } from "@playwright/test";

async function loadCandidate(page, language = "en") {
  await page.goto(`/tests/fixtures/recipes.html?lang=${language}`);
  const card = page.locator("family-meals-card");
  await card.locator(".recipes-section > summary").click();
  expect(await page.evaluate(() => window.lookups.length)).toBe(0);
  await card
    .locator('[data-recipes-form="search"] button[type="submit"]')
    .click();
  await card.locator('[data-recipe-slug="vegetable-soup"] button').click();
  await expect(card.locator('[data-recipes-form="edit"]')).toBeVisible();
  return card;
}

async function fillCandidate(card) {
  const form = card.locator('[data-recipes-form="edit"]');
  await form.locator('[name="week_start"]').fill("2026-09-07");
  await form.locator('[name="date"]').fill("2026-09-08");
  await form.locator('[name="slot"]').selectOption("dinner");
  const row = form.locator('[data-recipe-ingredient="1"]');
  await row.locator('[name="unit"]').fill("kg");
  await row.locator('[name="quantity"]').fill("0.3");
  return form;
}

test("RU recipe import requires manual correction and exact reviewed retry, creating only one private draft", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const card = await loadCandidate(page, "ru"),
    form = await fillCandidate(card);
  await form.locator('[name="servings"]').fill("6");
  await form.locator('button[type="submit"]').click();
  await expect(card.locator('[data-recipes-form="review"]')).toHaveCount(0);
  await form.locator('[name="verified_1"]').check();
  await page.screenshot({
    path: "test-results/recipes-edit-ru.png",
    fullPage: true,
  });
  await form.locator('button[type="submit"]').click();
  const review = card.locator('[data-recipes-form="review"]');
  await expect(review).toContainText("Potato: 1 kg");
  await expect(review).toContainText("Carrot: 0.3 kg");
  await expect(review).toContainText("Порции: 6");
  expect(await page.evaluate(() => window.calls.length)).toBe(0);
  await review.locator('button[type="submit"]').click();
  expect(await page.evaluate(() => window.calls.length)).toBe(0);
  await review.locator('[name="reviewed"]').check();
  await page.screenshot({
    path: "test-results/recipes-review-ru.png",
    fullPage: true,
  });
  await page.evaluate(() => (window.loseResponse = true));
  await review.locator('button[type="submit"]').click();
  await expect(
    review.getByRole("button", { name: "Повторить тот же запрос" }),
  ).toBeVisible();
  await page.evaluate(
    () => (window.card._pending = { id: "other", fingerprint: "other" }),
  );
  await review.locator('button[type="submit"]').click();
  await expect(review).toHaveCount(0);
  const calls = await page.evaluate(() => window.calls);
  expect(calls).toHaveLength(2);
  expect(calls[1]).toEqual(calls[0]);
  expect(calls[0].payload).toEqual({
    week_start: "2026-09-07",
    title: "Овощной суп",
    entries: [
      {
        date: "2026-09-08",
        slot: "dinner",
        title: "Овощной суп",
        servings: 6,
        ingredients: [
          { name: "Potato", unit: "kg", quantity: 1 },
          { name: "Carrot", unit: "kg", quantity: 0.3 },
        ],
      },
    ],
    note: "",
  });
  expect(
    await page.evaluate(() => window.fixture.pantry.meal_plans.length),
  ).toBe(1);
  expect(await page.evaluate(() => window.lookups.map((x) => x.kind))).toEqual([
    "search",
    "get",
  ]);
  expect(await page.evaluate(() => window.lookups[1].slug)).toBe(
    "vegetable-soup",
  );
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("UK source text is inert and an unresolved ingredient can only be explicitly removed", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const card = await loadCandidate(page, "uk");
  await page.evaluate(() => {
    window.card._recipesDraft.values.ingredients[1].display =
      '<img src=x onerror="window.injected=true">';
    window.card.render();
  });
  const form = await fillCandidate(card);
  await expect(form.locator("img")).toHaveCount(0);
  await form
    .locator('[data-recipe-ingredient="1"]')
    .getByRole("button", { name: "Видалити інгредієнт" })
    .click();
  await form.locator('button[type="submit"]').click();
  const review = card.locator('[data-recipes-form="review"]');
  await expect(review).toContainText("Potato: 1 kg");
  await expect(review).not.toContainText("Carrot: 0.3 kg");
  await page.screenshot({
    path: "test-results/recipes-review-uk.png",
    fullPage: true,
  });
  expect(await page.evaluate(() => window.injected)).toBeUndefined();
  expect(await page.evaluate(() => window.calls.length)).toBe(0);
});

test("A source revision change removes a focused candidate and detached review cannot save", async ({
  page,
}) => {
  const card = await loadCandidate(page);
  await fillCandidate(card);
  await card.locator('[name="verified_1"]').check();
  await card
    .locator('[data-recipes-form="edit"] button[type="submit"]')
    .click();
  await page.evaluate(async () => {
    window.oldReview = window.card.shadowRoot.querySelector(
      '[data-recipes-form="review"]',
    );
    window.oldReview.querySelector("input").focus();
    window.fixture.recipe_source.revision = "source-2";
    await window.card.refresh();
    window.oldReview.dispatchEvent(
      new Event("submit", { bubbles: true, cancelable: true }),
    );
  });
  await expect(card.locator('[data-recipes-form="review"]')).toHaveCount(0);
  await expect(card).not.toContainText("Carrot: 0.3 kg");
  expect(await page.evaluate(() => window.calls.length)).toBe(0);
});

test("Late lookup after role revocation cannot expose recipes even with focused search", async ({
  page,
}) => {
  await page.goto("/tests/fixtures/recipes.html");
  const card = page.locator("family-meals-card");
  await card.locator(".recipes-section > summary").click();
  await page.evaluate(() => (window.pauseLookup = true));
  await card
    .locator('[data-recipes-form="search"] button[type="submit"]')
    .click();
  await expect
    .poll(() => page.evaluate(() => Boolean(window.releaseLookup)))
    .toBe(true);
  await page.evaluate(async () => {
    window.card.shadowRoot.querySelector('[name="query"]').focus();
    window.fixture.role = "child";
    window.fixture.members[0].role = "child";
    window.fixture.members[0].revision++;
    await window.card.refresh();
    window.releaseLookup();
  });
  await expect(card.locator(".recipes-section")).toHaveCount(0);
  await expect(card).not.toContainText("Vegetable soup");
  expect(await page.evaluate(() => window.calls.length)).toBe(0);
});

test("Child cannot initiate a recipe request", async ({ page }) => {
  await page.goto("/tests/fixtures/recipes.html?lang=uk&actor=child");
  const card = page.locator("family-meals-card");
  await expect(card).toBeVisible();
  await expect(card.locator(".recipes-section")).toHaveCount(0);
  expect(await page.evaluate(() => window.lookups.length)).toBe(0);
});
