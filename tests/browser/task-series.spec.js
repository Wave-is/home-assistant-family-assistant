import { test, expect } from "@playwright/test";

const card = (page) => page.locator("family-tasks-card");

test("RU narrow parent creates only after a complete named recurrence review", async ({
  page,
}) => {
  await page.clock.install({ time: new Date("2026-09-07T12:00:00Z") });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/tests/fixtures/task-series.html?lang=ru&actor=parent");
  const root = card(page);
  await root
    .getByRole("button", { name: "Добавить регулярную задачу", exact: true })
    .click();
  await root.locator('input[name="title"]').fill("Полить растения");
  await root.locator('input[name="assignees"][value="child"]').check();
  await root
    .locator('[data-recurrence-control="start_date"]')
    .fill("2026-09-08");
  await root.locator('select[name="report_type"]').selectOption("photo");
  await root
    .locator('textarea[name="checklist"]')
    .fill("Проверить землю\nПолить");
  await root.locator('button[type="submit"]').click();
  await expect(root.locator(".task-series-review")).toContainText(
    "Полить растения",
  );
  await expect(root.locator(".task-series-review")).toContainText(
    "Sam · Версия 5",
  );
  expect(await page.evaluate(() => window.calls.length)).toBe(0);
  await page.screenshot({
    path: "test-results/task-series-review-ru.png",
    fullPage: true,
  });
  await root.locator('input[name="confirm"]').check();
  await root
    .getByRole("button", { name: "Сохранить регулярную задачу", exact: true })
    .click();
  await expect(root.locator(".task-series-review")).toHaveCount(0);
  const calls = await page.evaluate(() => window.calls);
  expect(calls).toHaveLength(1);
  expect(calls[0].action).toBe("tasks.series_save");
  expect(calls[0].payload.actor_revision).toBe(3);
  expect(calls[0].payload.creator_revision).toBe(3);
  expect(calls[0].payload.assignee_revisions).toEqual({ child: 5 });
  expect(calls[0].payload.report_type).toBe("photo");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("UK child gets a read-only current series without parent lineage", async ({
  page,
}) => {
  await page.goto("/tests/fixtures/task-series.html?lang=uk&actor=child");
  const root = card(page);
  await expect(root).toContainText("Take recycling out");
  await expect(root.locator(".task-series button")).toHaveCount(0);
  await expect(root).not.toContainText("Alex");
  await expect(root).not.toContainText("creator_revision");
});

test("stale identity is explicitly reviewed and committed response loss retries exact operation", async ({
  page,
}) => {
  await page.goto("/tests/fixtures/task-series.html?lang=en&actor=parent");
  await page.evaluate(async () => window.rebindChild());
  const root = card(page);
  await expect(root).toContainText("Paused for identity review");
  await expect(
    root.getByRole("button", { name: "Enable", exact: true }),
  ).toHaveCount(0);
  await root
    .getByRole("button", { name: "Review and edit", exact: true })
    .click();
  await root.locator('button[type="submit"]').click();
  await expect(root.locator(".task-series-review")).toContainText(
    "Sam · Version 6",
  );
  await root.locator('input[name="confirm"]').check();
  await page.evaluate(() => (window.loseResponse = true));
  await root
    .getByRole("button", { name: "Save recurring task", exact: true })
    .click();
  await expect(root).toContainText("exact reviewed request is pending");
  const frozen = await page.evaluate(() =>
    structuredClone(window.card._taskSeriesDraft.pending),
  );
  await root
    .getByRole("button", { name: "Retry exact request", exact: true })
    .click();
  await expect(root.locator(".task-series-review")).toHaveCount(0);
  const calls = await page.evaluate(() => window.calls);
  expect(calls).toHaveLength(2);
  expect(calls[1]).toEqual(calls[0]);
  expect(calls[1].operation_id).toBe(frozen.operation_id);
  expect(calls[1].payload).toEqual(frozen.payload);
});

test("module revocation removes a focused private editor and detaches old form", async ({
  page,
}) => {
  await page.goto("/tests/fixtures/task-series.html?lang=en&actor=parent");
  const root = card(page);
  await root
    .getByRole("button", { name: "Add recurring task", exact: true })
    .click();
  await page.evaluate(async () => {
    window.oldSeriesForm = window.card.shadowRoot.querySelector("form");
    await window.revoke();
    window.oldSeriesForm.dispatchEvent(
      new Event("submit", { bubbles: true, cancelable: true }),
    );
  });
  await expect(root.locator(".task-series-form")).toHaveCount(0);
  expect(await page.evaluate(() => window.card._taskSeriesDraft)).toBeNull();
  expect(await page.evaluate(() => window.calls.length)).toBe(0);
});
