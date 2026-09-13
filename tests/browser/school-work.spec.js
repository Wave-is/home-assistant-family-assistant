import { test, expect } from "./control-audit.js";

test.beforeEach(async ({ page }) => {
  await page.clock.setFixedTime(new Date("2026-09-07T07:00:00Z"));
});

test("RU mobile homework review freezes and retries one exact committed request", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/tests/fixtures/school-work.html?lang=ru&actor=parent");
  const card = page.locator("family-school-card");
  await card
    .getByRole("button", { name: "Добавить домашнее задание", exact: true })
    .click();
  const editor = card.locator(
    '[data-school-work-editor="homework_create"]',
  );
  await editor.locator('[name="title"]').fill("Проверить дроби");
  await editor
    .locator('[name="checklist"]')
    .fill("Решить четыре примера\nПоложить тетрадь");
  await editor.locator('[name="lesson"]').selectOption("0");
  await editor.locator('[name="reminder_minutes"]').fill("25");
  await editor.locator('[name="grace_minutes"]').fill("10");
  await editor
    .getByRole("button", { name: "Проверить", exact: true })
    .click();

  const review = card.locator(
    '[data-school-work-review="homework_create"]',
  );
  await expect(review).toContainText("Sam");
  await expect(review).toContainText("Проверить дроби");
  await expect(review).toContainText("Положить тетрадь");
  await expect(editor).toHaveCount(0);
  expect(await page.evaluate(() => window.calls.length)).toBe(0);
  await page.screenshot({
    path: "test-results/school-work-homework-review-ru.png",
    fullPage: true,
  });

  await review.locator('input[type="checkbox"]').check();
  await page.evaluate(() => (window.loseNext = true));
  await review
    .getByRole("button", { name: "Создать личную задачу", exact: true })
    .click();
  await expect(
    review.getByRole("button", { name: "Повторить точный запрос", exact: true }),
  ).toBeVisible();
  const afterLoss = await page.evaluate(() => ({
    calls: window.calls,
    tasks: window.fixture.tasks.map((item) => item.id),
  }));
  expect(afterLoss.calls).toHaveLength(1);
  expect(afterLoss.tasks).toHaveLength(3);
  expect(afterLoss.calls[0]).toMatchObject({
    action: "school.homework_create",
    payload: {
      member: "child",
      member_revision: 3,
      title: "Проверить дроби",
      checklist: ["Решить четыре примера", "Положить тетрадь"],
      reminder_minutes: 25,
      grace_minutes: 10,
      lesson: {
        timetable_id: "ST000001",
        timetable_revision: 4,
        date: "2026-09-07",
        lesson_index: 0,
      },
    },
  });

  await review.locator('input[type="checkbox"]').check();
  await review
    .getByRole("button", { name: "Повторить точный запрос", exact: true })
    .click();
  await expect(review).toHaveCount(0);
  const retried = await page.evaluate(() => window.calls);
  expect(retried).toHaveLength(2);
  expect(retried[1]).toEqual(retried[0]);
  expect(await page.evaluate(() => window.fixture.tasks.length)).toBe(3);
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
  ).toBe(true);
});

test("parent identity rebind resets stale work and committed retry stays exact for child privacy", async ({
  page,
}) => {
  await page.goto("/tests/fixtures/school-work.html?actor=parent");
  await page.evaluate(async () => {
    const task = window.fixture.tasks.find((item) => item.id === "T000001");
    task.status = "needs_changes";
    task.report = "PRIVATE STALE-EPOCH REPORT";
    task.review_note = "PRIVATE STALE-EPOCH REVIEW";
    task.deadline_events = { overdue: true };
    task.checklist[0].done = true;
    window.fixture.members.find((item) => item.id === "child").revision = 4;
    await window.syncCard();
  });
  const card = page.locator("family-school-card");
  const row = card.locator('[data-school-homework="T000001"]');
  await row.getByRole("button", { name: "Revise homework", exact: true }).click();
  const editor = card.locator(
    '[data-school-work-editor="homework_revise"]',
  );
  await editor.locator('[name="title"]').fill("Rebound current homework");
  await editor.getByRole("button", { name: "Review", exact: true }).click();
  let review = card.locator(
    '[data-school-work-review="homework_revise"]',
  );
  await review.locator('input[type="checkbox"]').check();
  await page.evaluate(() => (window.loseNext = true));
  await review
    .getByRole("button", { name: "Save homework revision", exact: true })
    .click();
  await expect(
    review.getByRole("button", { name: "Retry exact request", exact: true }),
  ).toBeVisible();
  let state = await page.evaluate(() => {
    const task = window.fixture.tasks.find((item) => item.id === "T000001");
    return { task, calls: window.calls };
  });
  expect(state.task).toMatchObject({
    status: "assigned",
    report: null,
    assignee_revision: 4,
    source: { member: "child", member_revision: 4 },
    checklist: [{ text: "Read the assigned pages", done: false }],
  });
  expect(state.task.review_note).toBeUndefined();
  expect(state.task.deadline_events).toBeUndefined();
  expect(state.task.previous_reports.at(-1)).toMatchObject({
    report: "PRIVATE STALE-EPOCH REPORT",
    review_note: "PRIVATE STALE-EPOCH REVIEW",
  });
  await review.locator('input[type="checkbox"]').check();
  await review
    .getByRole("button", { name: "Retry exact request", exact: true })
    .click();
  await expect(review).toHaveCount(0);
  state = await page.evaluate(() => ({
    calls: window.calls,
    count: window.fixture.tasks.length,
  }));
  expect(state.calls).toHaveLength(2);
  expect(state.calls[1]).toEqual(state.calls[0]);
  expect(state.calls[0].payload.member_revision).toBe(4);
  expect(state.count).toBe(2);

  await page.evaluate(async () => {
    window.fixture.actor = "child";
    window.fixture.role = "child";
    await window.syncCard();
  });
  const current = card.locator('[data-school-homework="T000001"]');
  await expect(current).toContainText("Rebound current homework");
  await expect(current).not.toContainText("PRIVATE STALE-EPOCH REPORT");
  await expect(current).not.toContainText("PRIVATE STALE-EPOCH REVIEW");
  const projected = await page.evaluate(() =>
    window.project().school.homework.find((item) => item.id === "T000001"),
  );
  expect(projected.source).toBeUndefined();
  expect(projected.previous_reports).toBeUndefined();
  expect(projected.assignee_revision).toBe(4);

  await page.evaluate(async () => {
    window.fixture.actor = "parent";
    window.fixture.role = "parent";
    window.fixture.tasks.find(
      (item) => item.id === "T000001",
    ).source.member_revision = 3;
    await window.syncCard();
    const original = window.calls[0];
    await window.card.command(
      original.action,
      structuredClone(original.payload),
      original.operation_id,
    );
  });
  await expect(card.locator('[role="alert"]')).toBeVisible();
  expect(await page.evaluate(() => window.fixture.tasks.length)).toBe(2);
});

test("synthetic server rejects missing and unknown command fields without mutation", async ({
  page,
}) => {
  await page.goto("/tests/fixtures/school-work.html?actor=parent");
  const card = page.locator("family-school-card");
  await page.evaluate(async () => {
    await window.card.command(
      "school.homework_create",
      {
        member: "child",
        member_revision: 3,
        title: "Invalid extra-field request",
        due_at: null,
        checklist: [],
        unexpected: true,
      },
      "school-work-invalid-extra",
    );
  });
  await expect(card.locator('[role="alert"]')).toBeVisible();
  await page.evaluate(async () => {
    await window.card.command(
      "school.backpack_start",
      {
        timetable_id: "ST000001",
        timetable_revision: 4,
        member: "child",
        member_revision: 3,
        date: "2026-09-07",
        routine_id: "R1",
      },
      "school-work-invalid-missing",
    );
  });
  expect(
    await page.evaluate(() => ({
      tasks: window.fixture.tasks.length,
      preparations: window.fixture.school.preparations.length,
      runs: window.fixture.routines.runs.length,
    })),
  ).toEqual({ tasks: 2, preparations: 0, runs: 0 });
});

test("UK child sees only own private homework and may explicitly review preparation", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/tests/fixtures/school-work.html?lang=uk&actor=child");
  const card = page.locator("family-school-card");
  await expect(card.getByText("Own private homework", { exact: true })).toBeVisible();
  await expect(card.getByText("SIBLING PRIVATE HOMEWORK", { exact: true })).toHaveCount(0);
  await expect(card.getByText("PRIVATE OLD REPORT", { exact: true })).toHaveCount(0);
  await expect(
    card.getByRole("button", { name: "Змінити домашнє завдання", exact: true }),
  ).toHaveCount(0);
  await expect(
    card.getByRole("button", { name: "Додати домашнє завдання", exact: true }),
  ).toBeVisible();
  await expect(
    card.getByRole("button", {
      name: "Перевірити й почати підготовку",
      exact: true,
    }),
  ).toBeVisible();
  expect(await page.evaluate(() => window.calls.length)).toBe(0);
  await page.screenshot({
    path: "test-results/school-work-child-uk.png",
    fullPage: true,
  });
});

test("changed lesson pin detaches a reviewed request before any write", async ({ page }) => {
  await page.goto("/tests/fixtures/school-work.html?actor=parent");
  const card = page.locator("family-school-card");
  await card.getByRole("button", { name: "Add homework", exact: true }).click();
  const editor = card.locator(
    '[data-school-work-editor="homework_create"]',
  );
  await editor.locator('[name="title"]').fill("Pinned lesson homework");
  await editor.locator('[name="lesson"]').selectOption("0");
  await editor.getByRole("button", { name: "Review", exact: true }).click();
  await page.evaluate(async () => {
    window.oldSchoolWorkReview = window.card.shadowRoot.querySelector(
      '[data-school-work-review="homework_create"]',
    );
    window.oldSchoolWorkReview.querySelector('input[type="checkbox"]').checked = true;
    window.fixture.school.timetables[0].revision++;
    await window.syncCard();
    window.oldSchoolWorkReview.querySelector("form").dispatchEvent(
      new Event("submit", { bubbles: true, cancelable: true }),
    );
  });
  await expect(
    card.locator('[data-school-work-review="homework_create"]'),
  ).toHaveCount(0);
  expect(await page.evaluate(() => window.calls.length)).toBe(0);
  expect(await page.evaluate(() => window.fixture.tasks.length)).toBe(2);
});

for (const kind of [
  "table_status",
  "table_revision",
  "table_epoch",
  "member_epoch",
  "routine_enabled",
  "routine_assignee",
  "date_occurrence",
]) {
  test(`${kind} change revokes a reviewed preparation before dispatch`, async ({
    page,
  }) => {
    await page.goto("/tests/fixtures/school-work.html?actor=child");
    const card = page.locator("family-school-card");
    await card
      .getByRole("button", {
        name: "Review and start preparation",
        exact: true,
      })
      .click();
    await page.evaluate(async (change) => {
      window.oldPreparationReview = window.card.shadowRoot.querySelector(
        '[data-school-work-review="backpack_start"]',
      );
      window.oldPreparationReview.querySelector('input[type="checkbox"]').checked = true;
      const table = window.fixture.school.timetables[0];
      const child = window.fixture.members.find((item) => item.id === "child");
      const routine = window.fixture.routines.templates[0];
      if (change === "table_status") table.status = "archived";
      if (change === "table_revision") table.revision++;
      if (change === "table_epoch") table.member_revision++;
      if (change === "member_epoch") child.revision++;
      if (change === "routine_enabled") routine.enabled = false;
      if (change === "routine_assignee") routine.assignees = [];
      if (change === "date_occurrence") table.exceptions.push("2026-09-07");
      await window.syncCard();
      window.oldPreparationReview.querySelector("form").dispatchEvent(
        new Event("submit", { bubbles: true, cancelable: true }),
      );
    }, kind);
    await expect(
      card.locator('[data-school-work-review="backpack_start"]'),
    ).toHaveCount(0);
    expect(await page.evaluate(() => window.calls.length)).toBe(0);
    expect(
      await page.evaluate(() => ({
        preparations: window.fixture.school.preparations.length,
        runs: window.fixture.routines.runs.length,
      })),
    ).toEqual({ preparations: 0, runs: 0 });
  });
}

test("preparation has no optimistic completion, deduplicates, and shows terminal history", async ({
  page,
}) => {
  await page.goto("/tests/fixtures/school-work.html?lang=uk&actor=child");
  await page.evaluate(() => {
    window.fixture.routines.runs.push({
      id: "RR-UNRELATED",
      revision: 1,
      status: "active",
      template_id: "OTHER",
      member: "sibling",
    });
  });
  const card = page.locator("family-school-card");
  await card
    .getByRole("button", {
      name: "Перевірити й почати підготовку",
      exact: true,
    })
    .click();
  const review = card.locator(
    '[data-school-work-review="backpack_start"]',
  );
  await expect(review).toContainText("Pack backpack");
  expect(
    await page.evaluate(() => ({
      calls: window.calls.length,
      preparations: window.fixture.school.preparations.length,
      runs: window.fixture.routines.runs.length,
    })),
  ).toEqual({ calls: 0, preparations: 0, runs: 1 });
  await review.locator('input[type="checkbox"]').check();
  await review
    .getByRole("button", { name: "Запустити закріплену рутину", exact: true })
    .click();
  await expect(review).toHaveCount(0);
  await expect(
    card.getByRole("button", {
      name: "Перевірити й почати підготовку",
      exact: true,
    }),
  ).toHaveCount(0);
  expect(
    await page.evaluate(() => ({
      preparations: window.fixture.school.preparations.length,
      runs: window.fixture.routines.runs.length,
    })),
  ).toEqual({ preparations: 1, runs: 2 });
  await card.getByText("Нещодавні запуски підготовки", { exact: true }).click();
  await expect(card.locator('[data-school-preparation="SP000001"]')).toContainText(
    "RR000001",
  );
  await page.screenshot({
    path: "test-results/school-work-preparation-uk.png",
    fullPage: true,
  });

  const first = await page.evaluate(() => window.calls[0]);
  await page.evaluate(async (message) => {
    await window.card.command(
      message.action,
      structuredClone(message.payload),
      "school-work-explicit-duplicate",
    );
  }, first);
  await expect(card.locator('[role="alert"]')).toBeVisible();
  expect(
    await page.evaluate(() => ({
      preparations: window.fixture.school.preparations.length,
      runs: window.fixture.routines.runs.length,
    })),
  ).toEqual({ preparations: 1, runs: 2 });

  await page.evaluate(async (message) => {
    window.fixture.routines.templates[0].enabled = false;
    await window.card.command(
      message.action,
      structuredClone(message.payload),
      message.operation_id,
    );
  }, first);
  await expect(card.locator('[role="alert"]')).toBeVisible();
  expect(
    await page.evaluate(() => ({
      preparations: window.fixture.school.preparations.length,
      runs: window.fixture.routines.runs.length,
    })),
  ).toEqual({ preparations: 1, runs: 2 });

  await page.evaluate(async (message) => {
    window.fixture.routines.templates[0].enabled = true;
    window.fixture.routines.runs.find(
      (item) => item.id === "RR000001",
    ).cancellation_cause = "authorization_removed";
    await window.card.command(
      message.action,
      structuredClone(message.payload),
      message.operation_id,
    );
  }, first);
  await expect(card.locator('[role="alert"]')).toBeVisible();
  expect(
    await page.evaluate(() => ({
      preparations: window.fixture.school.preparations.length,
      runs: window.fixture.routines.runs.length,
    })),
  ).toEqual({ preparations: 1, runs: 2 });
});

for (const kind of ["module", "actor", "epoch", "entry"]) {
  test(`${kind} change revokes a focused school-work draft and detached controls stay inert`, async ({
    page,
  }) => {
    await page.goto("/tests/fixtures/school-work.html?actor=parent");
    const card = page.locator("family-school-card");
    await card.getByRole("button", { name: "Add homework", exact: true }).click();
    const editor = card.locator(
      '[data-school-work-editor="homework_create"]',
    );
    await editor.locator('[name="title"]').fill(`Stale ${kind} homework`);
    await page.evaluate(async (change) => {
      window.oldSchoolWorkEditor = window.card.shadowRoot.querySelector(
        '[data-school-work-editor="homework_create"]',
      );
      window.oldSchoolWorkEditor.querySelector('[name="title"]').focus();
      await window.revoke(change);
      window.oldSchoolWorkEditor.dispatchEvent(
        new Event("submit", { bubbles: true, cancelable: true }),
      );
    }, kind);
    await expect(
      card.locator('[data-school-work-editor="homework_create"]'),
    ).toHaveCount(0);
    expect(await page.evaluate(() => window.calls.length)).toBe(0);
    expect(await page.evaluate(() => window.fixture.tasks.length)).toBe(2);
  });
}
