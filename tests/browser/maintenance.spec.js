import { test, expect } from "@playwright/test";

const reviewForm = (card) => card.locator('[data-maintenance-form="review"]');
async function confirm(card) {
  const form = reviewForm(card);
  await form.locator('[name="reviewed"]').check();
  await form.locator('button[type="submit"]').click();
}

test("RU asset edit freezes the entire named review and recovers a committed lost response", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/tests/fixtures/maintenance.html?lang=ru");
  const card = page.locator("family-maintenance-card");
  await card
    .locator('[data-maintenance-asset="MX000001"]')
    .getByRole("button", { name: "Изменить оборудование", exact: true })
    .click();
  const edit = card.locator('[data-maintenance-form="asset_edit"]');
  await edit.locator('[name="name"]').fill("Очиститель — проверенный фильтр");
  await edit.locator('[name="note"]').fill("Проверить крепление после осмотра");
  await page.screenshot({
    path: "test-results/maintenance-edit-ru.png",
    fullPage: true,
  });
  await edit.locator('button[type="submit"]').click();
  const review = reviewForm(card);
  await expect(review).toContainText("Sam");
  await expect(review).toContainText("LOCAL-PRIVATE-REF");
  await expect(review).toContainText("Проверить крепление");
  const paragraphGap = await review
    .locator(".maintenance-review")
    .evaluate((container) => {
      const rows = [...container.querySelectorAll(":scope > p")];
      const first = rows[0].getBoundingClientRect(),
        second = rows[1].getBoundingClientRect();
      return second.top - first.bottom;
    });
  expect(paragraphGap).toBeLessThan(22);
  expect(await page.evaluate(() => window.calls.length)).toBe(0);
  await page.screenshot({
    path: "test-results/maintenance-review-ru.png",
    fullPage: true,
  });
  await page.evaluate(() => (window.loseResponse = true));
  await confirm(card);
  await expect(review).toBeVisible();
  await page.evaluate(async () => {
    window.fixture.members[1].revision++;
    window.card._pending = { id: "other", fingerprint: "other" };
    await window.card.refresh();
  });
  await expect(review).toBeVisible();
  await review.locator('button[type="submit"]').click();
  await expect(review).toHaveCount(0);
  const calls = await page.evaluate(() => window.calls);
  expect(calls).toHaveLength(2);
  expect(calls[1]).toEqual(calls[0]);
  expect(calls[0].payload.responsible_member_revision).toBe(1);
  expect(calls[0].payload.consumables[0].pantry).toEqual({
    id: "PI1",
    revision: 1,
  });
  expect(
    await page.evaluate(() => window.fixture.maintenance.assets[0].revision),
  ).toBe(2);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("Stale pantry reference cannot silently disappear during an equipment rename", async ({
  page,
}) => {
  await page.goto("/tests/fixtures/maintenance.html");
  await page.evaluate(async () => {
    window.fixture.pantry.items[0].revision++;
    await window.card.refresh();
  });
  const card = page.locator("family-maintenance-card");
  await card
    .getByRole("button", { name: "Edit equipment", exact: true })
    .click();
  const edit = card.locator('[data-maintenance-form="asset_edit"]');
  await edit.locator('[name="name"]').fill("Reviewed rename");
  const pantry = edit.locator('[name="pantry"]');
  await expect(pantry).toHaveValue("__unavailable__");
  await edit.locator('button[type="submit"]').click();
  await expect(reviewForm(card)).toHaveCount(0);
  expect(await page.evaluate(() => window.calls.length)).toBe(0);
  await pantry.selectOption("");
  await edit.locator('button[type="submit"]').click();
  await confirm(card);
  await expect(reviewForm(card)).toHaveCount(0);
  expect(
    (await page.evaluate(() => window.calls))[0].payload.consumables[0].pantry,
  ).toBeNull();
});

test("UK child fault review creates one private task without parent notes and revokes focused drafts", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/tests/fixtures/maintenance.html?lang=uk&actor=child");
  const card = page.locator("family-maintenance-card");
  await expect(card).not.toContainText("PARENT-PRIVATE-NOTE");
  await expect(card).not.toContainText("LOCAL-PRIVATE-REF");
  await card.locator('[data-maintenance-asset="MX000001"] button').click();
  const edit = card.locator('[data-maintenance-form="fault_edit"]');
  await edit.locator('[name="summary"]').fill("Чути незвичний звук");
  await edit.locator('[name="details"]').fill("Помітив сьогодні вранці");
  await edit.locator('button[type="submit"]').click();
  await page.screenshot({
    path: "test-results/maintenance-child-uk.png",
    fullPage: true,
  });
  await confirm(card);
  await expect(reviewForm(card)).toHaveCount(0);
  const calls = await page.evaluate(() => window.calls);
  expect(calls).toHaveLength(1);
  expect(calls[0].payload.reporter_member_revision).toBe(1);
  expect(calls[0].payload.attachment_ids).toEqual([]);
  expect(
    await page.evaluate(() => window.fixture.tasks[0].delivery_scope),
  ).toBe("private");
  await card.locator('[data-maintenance-asset="MX000001"] button').click();
  await edit.locator('[name="summary"]').fill("PRIVATE-UNSENT-DRAFT");
  await page.evaluate(async () => {
    window.oldForm = window.card.shadowRoot.querySelector(
      '[data-maintenance-form="fault_edit"]',
    );
    window.oldForm.querySelector("input").focus();
    window.fixture.members[1].revision++;
    await window.card.refresh();
    window.oldForm.dispatchEvent(
      new Event("submit", { bubbles: true, cancelable: true }),
    );
  });
  await expect(edit).toHaveCount(0);
  await expect(card).not.toContainText("Чути незвичний звук");
  expect(await page.evaluate(() => window.card._maintenanceDraft)).toBeNull();
  expect(await page.evaluate(() => window.calls.length)).toBe(1);
});

test("A stale service can be explicitly reviewed against the current equipment without losing recurrence", async ({
  page,
}) => {
  await page.goto("/tests/fixtures/maintenance.html");
  await page.evaluate(async () => {
    window.fixture.maintenance.assets[0].revision = 2;
    window.fixture.maintenance.services[0].current = false;
    await window.card.refresh();
  });
  const card = page.locator("family-maintenance-card");
  await card
    .getByRole("button", { name: "Edit service schedule", exact: true })
    .click();
  const edit = card.locator('[data-maintenance-form="service_edit"]');
  await edit.locator('[name="title"]').fill("Inspect reviewed filter");
  await edit.locator('button[type="submit"]').click();
  await expect(reviewForm(card)).toContainText("Sam");
  await confirm(card);
  await expect(reviewForm(card)).toHaveCount(0);
  const call = (await page.evaluate(() => window.calls))[0];
  expect(call.action).toBe("maintenance.service_save");
  expect(call.payload.asset_revision).toBe(2);
  expect(call.payload.assignees).toEqual([{ id: "child", revision: 1 }]);
  expect(call.payload.rule).toMatchObject({
    frequency: "weekly",
    weekdays: [0],
    month_day: 7,
    catchup_hours: 24,
    time: "09:00",
  });
  expect(call.payload.checklist).toEqual(["Record observation"]);
});

test("RU photo service review retries the exact lost request and later edits retain photo reports", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/tests/fixtures/maintenance.html?lang=ru");
  const card = page.locator("family-maintenance-card");
  await card
    .getByRole("button", { name: "Изменить регламент", exact: true })
    .click();
  const edit = card.locator('[data-maintenance-form="service_edit"]');
  await edit.locator('[name="report_type"]').selectOption("photo");
  await edit.locator('button[type="submit"]').click();
  const review = reviewForm(card);
  await expect(review).toContainText("Отчёт о выполнении: Фотоотчёт");
  await expect(review).toContainText("Inspect filter");
  await page.screenshot({
    path: "test-results/maintenance-photo-review-ru.png",
    fullPage: true,
  });

  await page.evaluate(() => (window.loseResponse = true));
  await confirm(card);
  await expect(review).toBeVisible();
  await review.locator('button[type="submit"]').click();
  await expect(review).toHaveCount(0);
  let calls = await page.evaluate(() => window.calls);
  expect(calls).toHaveLength(2);
  expect(calls[1]).toEqual(calls[0]);
  expect(calls[0].payload.report_type).toBe("photo");
  expect(calls[0].operation_id).toBe(calls[1].operation_id);

  await card
    .getByRole("button", { name: "Изменить регламент", exact: true })
    .click();
  await expect(edit.locator('[name="report_type"]')).toHaveValue("photo");
  await edit.locator('[name="title"]').fill("Осмотр фильтра с фото");
  await edit.locator('button[type="submit"]').click();
  await expect(review).toContainText("Осмотр фильтра с фото");
  await expect(review).toContainText("Фотоотчёт");
  await confirm(card);
  calls = await page.evaluate(() => window.calls);
  expect(calls).toHaveLength(3);
  expect(calls[2].payload.report_type).toBe("photo");
  expect(
    await page.evaluate(
      () => window.fixture.maintenance.services[0].report_type,
    ),
  ).toBe("photo");
});

test("New service starts with an editable recurrence and creates a reviewed schedule", async ({
  page,
}) => {
  await page.goto("/tests/fixtures/maintenance.html");
  const card = page.locator("family-maintenance-card");
  await card
    .getByRole("button", { name: "Add service schedule", exact: true })
    .click();
  const form = card.locator('[data-maintenance-form="service_edit"]');
  await form.locator('[name="title"]').fill("New monthly inspection");
  await form.locator('fieldset input[value="child"]').check();
  await expect(
    form.locator('[data-recurrence-control="frequency"]'),
  ).toBeVisible();
  await form
    .locator('[data-recurrence-control="frequency"]')
    .selectOption("monthly");
  await form.locator('button[type="submit"]').click();
  await expect(reviewForm(card)).toBeVisible();
  await confirm(card);
  await expect(reviewForm(card)).toHaveCount(0);
  const calls = await page.evaluate(() => window.calls);
  expect(calls).toHaveLength(1);
  expect(calls[0].payload.rule.frequency).toBe("monthly");
  expect(calls[0].payload).not.toHaveProperty("id");
  expect(
    await page.evaluate(() => window.fixture.maintenance.services.length),
  ).toBe(2);
});

test("Retirement preserves history and still allows a manual historical service log without stock changes", async ({
  page,
}) => {
  await page.goto("/tests/fixtures/maintenance.html");
  const card = page.locator("family-maintenance-card");
  await card
    .getByRole("button", { name: "Retire equipment", exact: true })
    .click();
  const edit = card.locator('[data-maintenance-form="retire_edit"]');
  await edit.locator('[name="reason"]').fill("Replaced after review");
  await edit.locator('button[type="submit"]').click();
  await confirm(card);
  await expect(reviewForm(card)).toHaveCount(0);
  await card
    .getByRole("button", { name: "Record completed service", exact: true })
    .click();
  const log = card.locator('[data-maintenance-form="log_edit"]');
  await log.locator('[name="performed_on"]').fill("2026-09-01");
  await log.locator('[name="summary"]').fill("Manual past inspection record");
  await log.locator('button[type="submit"]').click();
  await confirm(card);
  await expect(reviewForm(card)).toHaveCount(0);
  const state = await page.evaluate(() => window.fixture);
  expect(state.maintenance.assets[0].status).toBe("retired");
  expect(state.maintenance.assets[0].history.at(-1).reason).toBe(
    "Replaced after review",
  );
  expect(state.maintenance.service_logs).toHaveLength(1);
  expect(state.pantry.items[0].quantity).toBe(3);
  expect(state.tasks).toHaveLength(0);
});

test("Tasks module revocation removes a focused service confirmation and blocks its detached submit", async ({
  page,
}) => {
  await page.goto("/tests/fixtures/maintenance.html");
  const card = page.locator("family-maintenance-card");
  await card
    .getByRole("button", { name: "Disable schedule", exact: true })
    .click();
  await expect(reviewForm(card)).toBeVisible();
  await page.evaluate(async () => {
    window.oldForm = window.card.shadowRoot.querySelector(
      '[data-maintenance-form="review"]',
    );
    window.oldForm.querySelector("input").focus();
    window.fixture.settings.modules = ["maintenance", "pantry"];
    await window.card.refresh();
    window.oldForm.dispatchEvent(
      new Event("submit", { bubbles: true, cancelable: true }),
    );
  });
  await expect(reviewForm(card)).toHaveCount(0);
  expect(await page.evaluate(() => window.calls.length)).toBe(0);
});
