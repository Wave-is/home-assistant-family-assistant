import { test, expect } from "@playwright/test";

const plan = (card, title) =>
  card.locator("[data-meal-plan]").filter({ hasText: title });

test("Russian mobile parent drafts, explicitly publishes, and safely retries a committed edit", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/tests/fixtures/meals.html?lang=ru&actor=parent");
  const card = page.locator("family-meals-card");

  await card.getByRole("button", { name: "Новый план", exact: true }).click();
  const editor = card.locator('form[data-meals-form="new"]');
  await editor
    .getByLabel("Начало недели (понедельник)", { exact: true })
    .fill("2026-09-21");
  await editor
    .getByLabel("Название плана", { exact: true })
    .fill("Меню для школы");
  await editor
    .getByLabel("Заметка для родителей", { exact: true })
    .fill("Не показывать детям");
  await editor.getByLabel("Дата", { exact: true }).fill("2026-09-21");
  await editor.getByLabel("Название блюда", { exact: true }).fill("Борщ");
  await editor.getByLabel("Порции", { exact: true }).fill("4");
  await editor
    .getByRole("button", { name: "Добавить ингредиент", exact: true })
    .click();
  await editor
    .getByLabel("Название ингредиента", { exact: true })
    .fill("Свёкла");
  await editor.getByLabel("Единица измерения", { exact: true }).fill("kg");
  await editor.getByLabel("Общее количество", { exact: true }).fill("1.25");
  await editor
    .getByRole("button", { name: "Добавить блюдо", exact: true })
    .click();
  const meals = editor.locator("[data-meals-entry]");
  await meals.nth(1).getByLabel("Дата", { exact: true }).fill("2026-09-22");
  await meals
    .nth(1)
    .locator('[data-meals-path="1.slot"]')
    .selectOption("lunch");
  await meals.nth(1).getByLabel("Название блюда", { exact: true }).fill("Каша");
  await meals.nth(1).getByLabel("Порции", { exact: true }).fill("3");
  await page.screenshot({
    path: "test-results/meals-editor-ru.png",
    fullPage: true,
  });

  await editor.getByRole("button", { name: "Сохранить", exact: true }).click();
  const created = await page.evaluate(() => window.calls.at(-1));
  expect(created.action).toBe("pantry.meal_save");
  expect(created.payload).toEqual({
    week_start: "2026-09-21",
    title: "Меню для школы",
    note: "Не показывать детям",
    entries: [
      {
        date: "2026-09-21",
        slot: "breakfast",
        title: "Борщ",
        servings: 4,
        ingredients: [{ name: "Свёкла", unit: "kg", quantity: 1.25 }],
      },
      {
        date: "2026-09-22",
        slot: "lunch",
        title: "Каша",
        servings: 3,
        ingredients: [],
      },
    ],
  });
  expect(
    await page.evaluate(() => window.fixture.pantry.meal_plans.at(-1).status),
  ).toBe("draft");

  const newPlan = plan(card, "Меню для школы");
  await newPlan
    .getByRole("button", { name: "Опубликовать план", exact: true })
    .click();
  const review = card.locator('form[data-meals-form="publish"]');
  await expect(
    review.getByRole("heading", {
      name: "Опубликовать этот план питания для семьи?",
      exact: true,
    }),
  ).toBeVisible();
  const callsBeforeReview = await page.evaluate(() => window.calls.length);
  await page.screenshot({
    path: "test-results/meals-publish-review-ru.png",
    fullPage: true,
  });
  expect(await page.evaluate(() => window.calls.length)).toBe(
    callsBeforeReview,
  );
  await review.locator('input[name="reviewed"]').check();
  await review.getByRole("button", { name: "Сохранить", exact: true }).click();
  expect(await page.evaluate(() => window.calls.at(-1))).toMatchObject({
    action: "pantry.meal_publish",
    payload: { id: "MP000003", revision: 1 },
  });
  expect(
    await page.evaluate(() => window.fixture.pantry.meal_plans.at(-1).status),
  ).toBe("published");

  await newPlan
    .getByRole("button", { name: "Редактировать план", exact: true })
    .click();
  const edit = card.locator('form[data-meals-form="edit"]');
  await edit
    .getByLabel("Название плана", { exact: true })
    .fill("Меню для школы — обновлено");
  await page.evaluate(() => {
    window.commitThenLose = true;
    window.lostOnce = false;
  });
  await edit.getByRole("button", { name: "Сохранить", exact: true }).click();
  await expect(
    edit.getByRole("button", { name: "Повторить", exact: true }),
  ).toBeVisible();
  const lost = await page.evaluate(() => window.calls.at(-1));
  expect(lost.action).toBe("pantry.meal_save");
  expect(lost.payload).toEqual({
    id: "MP000003",
    revision: 2,
    title: "Меню для школы — обновлено",
  });
  expect(
    await page.evaluate(() => window.fixture.pantry.meal_plans.at(-1)),
  ).toMatchObject({ revision: 3, status: "draft" });
  await page.evaluate(() => {
    window.commitThenLose = false;
  });
  await edit.getByRole("button", { name: "Повторить", exact: true }).click();
  const retried = await page.evaluate(() => window.calls.at(-1));
  expect(retried.operation_id).toBe(lost.operation_id);
  expect(retried.payload).toEqual(lost.payload);
  expect(
    await page.evaluate(() => window.fixture.pantry.meal_plans.at(-1).revision),
  ).toBe(3);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await expect(card.getByText("null", { exact: true })).toHaveCount(0);
});

test("Ukrainian child sees only the published menu without parent metadata or mutation controls", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/tests/fixtures/meals.html?lang=uk&actor=child");
  const card = page.locator("family-meals-card");
  await expect(card.getByText("Сімейне меню", { exact: true })).toBeVisible();
  await expect(card.getByText(/Овочевий суп/)).toBeVisible();
  await expect(
    card.getByText("Особиста чернетка", { exact: true }),
  ).toHaveCount(0);
  await expect(card.getByText(/ПРИМІТКА БАТЬКІВ|ПРИВАТНА ІСТОРІЯ/)).toHaveCount(
    0,
  );
  await expect(
    card.getByRole("button", {
      name: /Новий план|Редагувати план|Опублікувати план|Архівувати план/,
    }),
  ).toHaveCount(0);
  const privacy = await page.evaluate(() => ({
    sourceHasSecrets: Boolean(
      window.fixture.pantry.meal_plans[0].note &&
        window.fixture.pantry.meal_plans[0].history.length,
    ),
    sourceHasDraft: window.fixture.pantry.meal_plans.some(
      (item) => item.status === "draft",
    ),
    projected: window.card._data.pantry.meal_plans,
  }));
  expect(privacy.sourceHasSecrets).toBe(true);
  expect(privacy.sourceHasDraft).toBe(true);
  expect(privacy.projected).toHaveLength(1);
  for (const field of [
    "note",
    "history",
    "created_by",
    "created_at",
    "updated_at",
    "published_at",
    "archived_at",
    "revision",
  ])
    expect(privacy.projected[0]).not.toHaveProperty(field);
  await page.screenshot({
    path: "test-results/meals-child-uk.png",
    fullPage: true,
  });
  expect(await page.evaluate(() => window.calls.length)).toBe(0);
});

test("stale revision and focused authorization revocation prevent meal mutations", async ({
  page,
}) => {
  await page.goto("/tests/fixtures/meals.html?lang=en&actor=parent");
  const card = page.locator("family-meals-card");
  const published = plan(card, "Family menu");

  await published
    .getByRole("button", { name: "Edit plan", exact: true })
    .click();
  let edit = card.locator('form[data-meals-form="edit"]');
  await edit.getByLabel("Plan title", { exact: true }).fill("Stale edit");
  await page.evaluate(() => window.bumpFocusedRevision("MP000001"));
  await edit.getByRole("button", { name: "Save", exact: true }).click();
  await expect(edit).toHaveCount(0);
  expect(await page.evaluate(() => window.calls.length)).toBe(0);

  await published
    .getByRole("button", { name: "Edit plan", exact: true })
    .click();
  edit = card.locator('form[data-meals-form="edit"]');
  await edit
    .getByLabel("Plan title", { exact: true })
    .fill("Blocked by module revoke");
  await page.evaluate(() => window.revokeFocusedAccess("module"));
  await edit.getByRole("button", { name: "Save", exact: true }).click();
  expect(await page.evaluate(() => window.calls.length)).toBe(0);
  await page.evaluate(() => window.card.render());
  await expect(
    card.getByText("Enable Pantry & household stock to use meal plans.", {
      exact: true,
    }),
  ).toBeVisible();

  await page.reload();
  const freshCard = page.locator("family-meals-card");
  const freshPlan = plan(freshCard, "Family menu");
  await freshPlan
    .getByRole("button", { name: "Edit plan", exact: true })
    .click();
  const freshEdit = freshCard.locator('form[data-meals-form="edit"]');
  await freshEdit
    .getByLabel("Plan title", { exact: true })
    .fill("Blocked by role revoke");
  await page.evaluate(() => window.revokeFocusedAccess("role"));
  await freshEdit.getByRole("button", { name: "Save", exact: true }).click();
  expect(await page.evaluate(() => window.calls.length)).toBe(0);
  await page.evaluate(() => window.card.render());
  await expect(
    freshCard.getByRole("button", { name: "Edit plan", exact: true }),
  ).toHaveCount(0);
});

test("archive requires a reviewed reason and retains an immutable archived record", async ({
  page,
}) => {
  await page.goto("/tests/fixtures/meals.html?lang=en&actor=parent");
  const card = page.locator("family-meals-card");
  const draft = plan(card, "Private draft");
  const countBefore = await page.evaluate(
    () => window.fixture.pantry.meal_plans.length,
  );
  await draft
    .getByRole("button", { name: "Archive plan", exact: true })
    .click();
  const review = card.locator('form[data-meals-form="archive"]');
  await expect(
    review.getByRole("heading", {
      name: "Archive this meal plan?",
      exact: true,
    }),
  ).toBeVisible();
  expect(await page.evaluate(() => window.calls.length)).toBe(0);
  await review
    .getByLabel("Reason for change", { exact: true })
    .fill("Superseded by the school menu");
  await review.getByRole("button", { name: "Save", exact: true }).click();
  expect(await page.evaluate(() => window.calls.length)).toBe(0);
  await review.locator('input[name="reviewed"]').check();
  await review.getByRole("button", { name: "Save", exact: true }).click();
  const archived = await page.evaluate(() => ({
    call: window.calls.at(-1),
    records: window.fixture.pantry.meal_plans,
  }));
  expect(archived.call).toMatchObject({
    action: "pantry.meal_archive",
    payload: {
      id: "MP000002",
      revision: 1,
      reason: "Superseded by the school menu",
    },
  });
  expect(archived.records).toHaveLength(countBefore);
  expect(archived.records.find((item) => item.id === "MP000002")).toMatchObject(
    { status: "archived", revision: 2 },
  );
  expect(archived.call.action).not.toMatch(/delete|remove/);
  await expect(
    plan(card, "Private draft").getByRole("button", {
      name: /Edit|Publish|Archive/,
    }),
  ).toHaveCount(0);
});

test("changing household discards the scoped draft without sending it", async ({
  page,
}) => {
  await page.goto("/tests/fixtures/meals.html?lang=en&actor=parent");
  const card = page.locator("family-meals-card");
  await card.getByRole("button", { name: "New plan", exact: true }).click();
  await card
    .getByLabel("Parent note", { exact: true })
    .fill("Synthetic household A only");
  await page.evaluate(() => window.switchHousehold("other"));
  await expect(
    card.getByText("No meal plans yet.", { exact: true }),
  ).toBeVisible();
  expect(await page.evaluate(() => window.card._mealsDraft)).toBeNull();
  expect(
    await card.evaluate((element) =>
      element.shadowRoot.textContent.includes("Synthetic household A only"),
    ),
  ).toBe(false);
  expect(await page.evaluate(() => window.calls.length)).toBe(0);
});
