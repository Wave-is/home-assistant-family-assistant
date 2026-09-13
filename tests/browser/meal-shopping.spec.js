import { test, expect } from "./control-audit.js";

const proposal = (card) => card.locator("[data-meal-shopping-proposal]");

test("Russian parent reviews exact deficit and retries a committed transfer receipt", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/tests/fixtures/meal-shopping.html?lang=ru&actor=parent");
  const card = page.locator("family-meals-card");
  await card
    .getByRole("button", {
      name: "Рассчитать необходимые покупки",
      exact: true,
    })
    .click();
  const row = proposal(card).filter({ hasText: "Synthetic family menu" });
  await expect(row).toContainText("Требуется по плану2 l");
  await expect(row).toContainText("Учтённый остаток в кладовой0.5 l");
  await expect(row).toContainText("Осталось в списке покупок0.25 l");
  await expect(row).toContainText("Будет добавлено1.25 l");
  expect(await page.evaluate(() => window.calls.at(-1))).toMatchObject({
    action: "pantry.meal_shop_prepare",
    payload: { id: "MP000001", revision: 2 },
  });
  expect(
    await page.evaluate(() => ({
      shopping: window.fixture.shopping.length,
      status: window.fixture.pantry.meal_shopping[0].status,
    })),
  ).toEqual({ shopping: 1, status: "open" });

  await row
    .getByRole("button", { name: "Передать в список покупок", exact: true })
    .click();
  const review = card.locator('form[data-meal-shopping-form="accept"]');
  await expect(
    review.getByText(
      "Я проверил(а) все количества и хочу добавить эти позиции",
      { exact: true },
    ),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/meal-shopping-review-ru.png",
    fullPage: true,
  });
  const beforeUnchecked = await page.evaluate(() => window.calls.length);
  await review
    .getByRole("button", { name: "Передать в список покупок", exact: true })
    .click();
  expect(await page.evaluate(() => window.calls.length)).toBe(beforeUnchecked);

  await review.locator('input[name="reviewed"]').check();
  await page.evaluate(() => {
    window.loseNextAccept = true;
  });
  await review
    .getByRole("button", { name: "Передать в список покупок", exact: true })
    .click();
  await expect(
    review.getByRole("button", {
      name: "Повторить тот же запрос",
      exact: true,
    }),
  ).toBeVisible();
  const lost = await page.evaluate(() => window.calls.at(-1));
  expect(lost).toMatchObject({
    action: "pantry.meal_shop_accept",
    payload: { id: "MS000001", revision: 1 },
  });
  const committed = await page.evaluate(() => ({
    shopping: window.fixture.shopping,
    proposal: window.fixture.pantry.meal_shopping[0],
  }));
  expect(committed.shopping).toHaveLength(2);
  expect(committed.shopping[1]).toMatchObject({
    quantity: 1.25,
    unit: "l",
    status: "approved",
    note: "",
    meal_plan_id: "MP000001",
    meal_shopping_id: "MS000001",
  });
  expect(committed.proposal).toMatchObject({
    status: "accepted",
    transfer_count: 1,
  });
  expect(committed.proposal.lines[0].shopping_id).toBe(
    committed.shopping[1].id,
  );

  await review
    .getByRole("button", { name: "Повторить тот же запрос", exact: true })
    .click();
  const retried = await page.evaluate(() => window.calls.at(-1));
  expect(retried.operation_id).toBe(lost.operation_id);
  expect(retried.payload).toEqual(lost.payload);
  expect(await page.evaluate(() => window.fixture.shopping.length)).toBe(2);
  await expect(row).toContainText("Передано в список покупок");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("Ukrainian covered receipt creates nothing and remains an honest terminal record", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(
    "/tests/fixtures/meal-shopping.html?lang=uk&actor=parent&scenario=covered",
  );
  const card = page.locator("family-meals-card");
  await card
    .getByRole("button", { name: "Розрахувати необхідні покупки", exact: true })
    .click();
  const row = proposal(card);
  await expect(row).toContainText("Буде додано0 l");
  await row
    .getByRole("button", { name: "Передати до списку покупок", exact: true })
    .click();
  const review = card.locator('form[data-meal-shopping-form="accept"]');
  await review.locator('input[name="reviewed"]').check();
  await review
    .getByRole("button", { name: "Передати до списку покупок", exact: true })
    .click();
  await expect(proposal(card)).toContainText("Уже повністю покрито");
  await expect(proposal(card)).toContainText("Нічого не додано");
  expect(
    await page.evaluate(() => ({
      count: window.fixture.shopping.length,
      transfer: window.fixture.pantry.meal_shopping[0].transfer_count,
    })),
  ).toEqual({ count: 0, transfer: 0 });
  await page.screenshot({
    path: "test-results/meal-shopping-covered-uk.png",
    fullPage: true,
  });
});

test("Ukrainian child receives neither private proposals nor transfer controls", async ({
  page,
}) => {
  await page.goto("/tests/fixtures/meal-shopping.html?lang=uk&actor=child");
  await page.evaluate(() => {
    window.fixture.pantry.meal_shopping.push({
      id: "MSPRIVATE",
      revision: 1,
      status: "open",
      source_plan_id: "MP000001",
      source_revision: 2,
      plan_title: "PRIVATE PROPOSAL",
      week_start: "2026-09-07",
      lines: [
        {
          name: "SECRET LINE",
          unit: "l",
          required: 2,
          stock: 0.5,
          open_shopping: 0.25,
          deficit: 1.25,
          quantity: 1.25,
        },
      ],
    });
    return window.syncCard();
  });
  const card = page.locator("family-meals-card");
  await expect(
    card.getByText("Synthetic family menu", { exact: true }),
  ).toBeVisible();
  await expect(
    card.getByText(/PRIVATE PROPOSAL|SECRET LINE|PARENT PRIVATE/),
  ).toHaveCount(0);
  await expect(
    card.getByRole("button", { name: /Розрахувати|Передати/ }),
  ).toHaveCount(0);
  await expect(proposal(card)).toHaveCount(0);
  expect(await page.evaluate(() => window.calls.length)).toBe(0);
  await page.screenshot({
    path: "test-results/meal-shopping-child-uk.png",
    fullPage: true,
  });
});

test("rounding keeps unlike units separate and discloses the minimum add amount", async ({
  page,
}) => {
  await page.goto("/tests/fixtures/meal-shopping.html?scenario=rounding");
  const card = page.locator("family-meals-card");
  await card
    .getByRole("button", { name: "Calculate shopping needs", exact: true })
    .click();
  const row = proposal(card);
  await expect(row).toContainText("Recorded pantry stock0 l");
  await expect(row).toContainText("Remaining on the shopping list0.999999 l");
  await expect(row).toContainText("Uncovered amount0.000001 l");
  await expect(row).toContainText("Amount to add0.001 l");
  await expect(row).toContainText("rounded up to 0.001");
});

test("relevant changes conflict, recalculate supersedes, and stale authority controls stay inert", async ({
  page,
}) => {
  await page.goto("/tests/fixtures/meal-shopping.html");
  const card = page.locator("family-meals-card");
  const calculate = card.getByRole("button", {
    name: "Calculate shopping needs",
    exact: true,
  });
  await calculate.click();
  let row = proposal(card).filter({ hasText: "Ready for parent review" });
  await row
    .getByRole("button", { name: "Send to shopping list", exact: true })
    .click();
  let review = card.locator('form[data-meal-shopping-form="accept"]');
  await review.locator('input[name="reviewed"]').check();
  await page.evaluate(() => window.changeRelevantStock());
  await review
    .getByRole("button", { name: "Send to shopping list", exact: true })
    .click();
  await expect(card.locator('[role="alert"]')).toBeVisible();
  expect(await page.evaluate(() => window.fixture.shopping.length)).toBe(1);

  await card
    .getByRole("button", { name: "Calculate shopping needs", exact: true })
    .click();
  await expect(
    proposal(card).filter({ hasText: "Superseded by a newer calculation" }),
  ).toHaveCount(1);
  row = proposal(card).filter({ hasText: "Ready for parent review" });
  await expect(row).toContainText("Amount to add1 l");

  await row
    .getByRole("button", { name: "Send to shopping list", exact: true })
    .click();
  review = card.locator('form[data-meal-shopping-form="accept"]');
  await review.locator('input[name="reviewed"]').check();
  await page.evaluate(() => window.editSource());
  await review
    .getByRole("button", { name: "Send to shopping list", exact: true })
    .click();
  await expect(card.locator('[role="alert"]')).toBeVisible();
  expect(await page.evaluate(() => window.fixture.shopping.length)).toBe(1);

  await page.reload();
  const moduleCard = page.locator("family-meals-card");
  const staleModule = moduleCard.getByRole("button", {
    name: "Calculate shopping needs",
    exact: true,
  });
  await page.evaluate(() => window.revoke("module"));
  await staleModule.click();
  expect(await page.evaluate(() => window.calls.length)).toBe(0);
  await page.evaluate(() => window.card.render());
  await expect(
    moduleCard.getByText(
      "Enable both Pantry & household stock and Shopping to calculate meal shopping needs.",
      { exact: true },
    ),
  ).toBeVisible();

  await page.reload();
  const roleCard = page.locator("family-meals-card");
  const staleRole = roleCard.getByRole("button", {
    name: "Calculate shopping needs",
    exact: true,
  });
  await page.evaluate(() => window.revoke("role"));
  await staleRole.click();
  expect(await page.evaluate(() => window.calls.length)).toBe(0);
  await page.evaluate(() => window.card.render());
  await expect(roleCard.locator(".meal-shopping-section")).toHaveCount(0);
});
