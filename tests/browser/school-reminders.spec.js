import { test, expect } from "@playwright/test";

const section = (card) => card.locator(".school-reminders");
const review = (card) => card.locator(".school-reminder-review");
const row = (card, member) =>
  card.locator(`.school-reminder-row[data-school-reminder-member="${member}"]`);

async function confirm(card, label) {
  const form = review(card);
  await form.locator('input[name="confirmed"]').check();
  await form.getByRole("button", { name: label, exact: true }).click();
}

test("EN wide card keeps the timetable beside collapsed, source-free personal preferences", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1180, height: 820 });
  await page.goto("/tests/fixtures/school-reminders.html?lang=en");
  const card = page.locator("family-school-card");
  await expect(section(card)).toBeVisible();
  await expect(card).toContainText("Sam school week");
  await expect(section(card).locator("details")).not.toHaveAttribute("open", "");
  await expect(section(card).locator("select")).toHaveCount(0);
  const privateProjection = await page.evaluate(
    () => window.project().school.preparation_reminders,
  );
  expect(Object.keys(privateProjection).sort()).toEqual(["policy", "self_targets"]);
  for (const target of privateProjection.self_targets)
    expect(Object.keys(target).sort()).toEqual([
      "enabled",
      "member",
      "member_revision",
      "recipient_revision",
      "subscription_revision",
    ]);
  expect(JSON.stringify(privateProjection)).not.toMatch(
    /materials|subject|room|routine|timetable/i,
  );
  await page.screenshot({
    path: "test-results/school-reminders-wide-en.png",
    fullPage: true,
  });

  await row(card, "child-1")
    .getByRole("button", { name: "Enable for me", exact: true })
    .click();
  await expect(review(card)).toContainText("Alex");
  await expect(review(card)).toContainText("Sam");
  expect(await page.evaluate(() => window.calls.length)).toBe(0);
  await confirm(card, "Save preference");
  await expect(review(card)).toHaveCount(0);
  const calls = await page.evaluate(() => window.calls);
  expect(calls).toHaveLength(1);
  expect(calls[0].action).toBe("school.preparation_reminder_access_set");
  expect(calls[0].payload).toEqual({
    member: "child-1",
    member_revision: 7,
    recipient_revision: 4,
    subscription_revision: null,
    enabled: true,
  });
  expect(typeof calls[0].operation_id).toBe("string");
});

test("RU narrow disable review is named, exact, accessible, and does not overflow", async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/tests/fixtures/school-reminders.html?lang=ru");
  const card = page.locator("family-school-card");
  await expect(card).toContainText("CROSS-CHILD-TIMETABLE");
  await row(card, "child-2")
    .getByRole("button", { name: "Выключить для меня", exact: true })
    .click();
  await expect(review(card)).toContainText("Jamie");
  await expect(review(card)).toContainText("Alex");
  await expect(review(card).locator('input[name="confirmed"]')).toBeVisible();
  await page.screenshot({
    path: "test-results/school-reminders-review-ru.png",
    fullPage: true,
  });
  await confirm(card, "Сохранить выбор");
  const call = (await page.evaluate(() => window.calls))[0];
  expect(call.payload).toEqual({
    member: "child-2",
    member_revision: 9,
    recipient_revision: 4,
    subscription_revision: 3,
    enabled: false,
  });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
  ).toBe(true);
});

test("UK child sees only self, never cross-child source, and saves only a self preference", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/tests/fixtures/school-reminders.html?lang=uk&actor=child");
  const card = page.locator("family-school-card");
  await expect(section(card)).toBeVisible();
  await expect(section(card).locator(".school-reminder-row")).toHaveCount(1);
  await expect(row(card, "child-1")).toBeVisible();
  await expect(card).not.toContainText("Jamie");
  await expect(card).not.toContainText("CROSS-CHILD");
  await page.screenshot({
    path: "test-results/school-reminders-child-uk.png",
    fullPage: true,
  });
  await row(card, "child-1")
    .getByRole("button", { name: "Увімкнути для мене", exact: true })
    .click();
  await expect(review(card)).toContainText("Sam");
  await expect(review(card)).not.toContainText("Alex");
  await confirm(card, "Зберегти вибір");
  expect((await page.evaluate(() => window.calls))[0].payload).toEqual({
    member: "child-1",
    member_revision: 7,
    recipient_revision: 7,
    subscription_revision: null,
    enabled: true,
  });
});

test("global and Routines switches explain that an off policy saves preference only", async ({
  page,
}) => {
  await page.goto(
    "/tests/fixtures/school-reminders.html?lang=en&policy=off&routines=off",
  );
  const card = page.locator("family-school-card");
  await expect(section(card).locator(".school-reminder-policy")).toContainText(
    "nothing is scheduled or sent",
  );
  await expect(section(card).locator(".school-reminder-routines-off")).toContainText(
    "save your preference",
  );
  await row(card, "child-1")
    .getByRole("button", { name: "Enable for me", exact: true })
    .click();
  await confirm(card, "Save preference");
  await expect(review(card)).toHaveCount(0);
  expect((await page.evaluate(() => window.calls))[0].payload.enabled).toBe(true);
  expect(await page.evaluate(() => window.fixture.settings.school_preparation_reminders)).toBe(
    false,
  );
  expect(await page.evaluate(() => window.fixture.settings.modules)).toEqual(["school"]);
});

test("precommit and committed-response-loss retries preserve the exact frozen request", async ({
  page,
}) => {
  const card = page.locator("family-school-card");
  await page.goto("/tests/fixtures/school-reminders.html?lang=en");
  await row(card, "child-1")
    .getByRole("button", { name: "Enable for me", exact: true })
    .click();
  await page.evaluate(() => (window.failMode = "before"));
  await confirm(card, "Save preference");
  await expect(review(card).getByRole("button", { name: "Retry exact request" })).toBeVisible();
  const before = (await page.evaluate(() => window.calls))[0];
  await review(card).getByRole("button", { name: "Retry exact request" }).click();
  await expect(review(card)).toHaveCount(0);
  let calls = await page.evaluate(() => window.calls);
  expect(calls).toHaveLength(2);
  expect(calls[1]).toEqual(before);

  await page.goto("/tests/fixtures/school-reminders.html?lang=en");
  await row(card, "child-2")
    .getByRole("button", { name: "Disable for me", exact: true })
    .click();
  await page.evaluate(() => (window.failMode = "after"));
  await confirm(card, "Save preference");
  await expect(review(card).getByRole("button", { name: "Retry exact request" })).toBeVisible();
  expect(await page.evaluate(() => window.fixture.subscriptions["parent-1|child-2"].revision)).toBe(4);
  const committed = (await page.evaluate(() => window.calls))[0];
  await page.evaluate(() => (window.card._pending = { id: "other", fingerprint: "other" }));
  await review(card).getByRole("button", { name: "Retry exact request" }).click();
  await expect(review(card)).toHaveCount(0);
  calls = await page.evaluate(() => window.calls);
  expect(calls).toHaveLength(2);
  expect(calls[1]).toEqual(committed);
});

test("actor, School module, entry, generation, and child epoch changes clear focused drafts", async ({
  page,
}) => {
  const card = page.locator("family-school-card");
  const cases = [
    async () => {
      await page.evaluate(async () => {
        window.oldSave = window.card.shadowRoot.querySelector(
          ".school-reminder-review button.primary",
        );
        window.fixture.actor = "adult-1";
        await window.card.refresh();
        window.oldSave.click();
      });
    },
    async () => {
      await page.evaluate(async () => {
        window.oldSave = window.card.shadowRoot.querySelector(
          ".school-reminder-review button.primary",
        );
        window.fixture.settings.modules = ["routines"];
        await window.card.refresh();
        window.oldSave.click();
      });
    },
    async () => {
      await page.evaluate(() => {
        window.oldSave = window.card.shadowRoot.querySelector(
          ".school-reminder-review button.primary",
        );
        window.card._entry = "other-entry";
        window.oldSave.click();
      });
    },
    async () => {
      await page.evaluate(() => {
        window.oldSave = window.card.shadowRoot.querySelector(
          ".school-reminder-review button.primary",
        );
        window.card._generation += 1;
        window.oldSave.click();
      });
    },
    async () => {
      await page.evaluate(async () => {
        window.oldSave = window.card.shadowRoot.querySelector(
          ".school-reminder-review button.primary",
        );
        window.fixture.members.find((item) => item.id === "child-1").revision += 1;
        await window.card.refresh();
        window.oldSave.click();
      });
    },
  ];
  for (const mutate of cases) {
    await page.goto("/tests/fixtures/school-reminders.html?lang=en");
    await row(card, "child-1")
      .getByRole("button", { name: "Enable for me", exact: true })
      .click();
    await review(card).locator('input[name="confirmed"]').check();
    await mutate();
    await expect(review(card)).toHaveCount(0);
    expect(await page.evaluate(() => window.card._schoolReminderDraft)).toBeNull();
    expect(await page.evaluate(() => window.calls.length)).toBe(0);
  }
});

test("subscription revision drift requires a fresh named review", async ({ page }) => {
  await page.goto("/tests/fixtures/school-reminders.html?lang=en");
  const card = page.locator("family-school-card");
  await row(card, "child-1")
    .getByRole("button", { name: "Enable for me", exact: true })
    .click();
  await review(card).locator('input[name="confirmed"]').check();
  await page.evaluate(async () => {
    window.fixture.subscriptions["parent-1|child-1"] = {
      recipient: "parent-1",
      recipient_revision: 4,
      member: "child-1",
      member_revision: 7,
      enabled: false,
      revision: 1,
    };
    await window.card.refresh();
  });
  await expect(review(card)).toHaveCount(0);
  expect(await page.evaluate(() => window.calls.length)).toBe(0);

  await row(card, "child-1")
    .getByRole("button", { name: "Enable for me", exact: true })
    .click();
  await expect(review(card)).toContainText("1");
  await confirm(card, "Save preference");
  expect((await page.evaluate(() => window.calls))[0].payload.subscription_revision).toBe(1);
});
