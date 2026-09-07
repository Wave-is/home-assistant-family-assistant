import { test, expect } from "@playwright/test";

const field = (card, name, path = "") =>
  card.locator(
    `[data-condition-scope="template-skip"] [data-condition-field="${name}"][data-condition-path="${path}"]`,
  );
const scopedField = (card, scope, name, path = "") =>
  card.locator(
    `[data-condition-scope="${scope}"] [data-condition-field="${name}"][data-condition-path="${path}"]`,
  );

for (const changed of ["actor", "assignee", "template"]) {
  test(`focused routine editor clears after ${changed} revision changes`, async ({page}) => {
    await page.goto("/tests/fixtures/routines.html");
    const card=page.locator("family-routines-card");
    await card.getByRole("button",{name:"Edit",exact:true}).click();
    const title=card.locator('input[name="title"]');
    await title.fill("Unsaved synthetic draft");
    await title.focus();
    await page.evaluate(async kind=>{
      if(kind==="template") window.fixture.routines.templates[0].revision++;
      else window.fixture.members[kind==="actor"?0:1].revision++;
      await window.card.refresh();
    },changed);
    await expect(title).toHaveCount(0);
    expect(await page.evaluate(()=>window.calls)).toHaveLength(0);
  });
}

test("Russian per-step conditions survive handoff reorder and exact committed retry", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/tests/fixtures/routines.html?lang=ru");
  const card = page.locator("family-routines-card");
  await card.getByRole("button", { name: "Изменить", exact: true }).click();

  const first = card.locator('[data-routine-step-index="0"]');
  await first.locator('[data-step-assignee="0"]').selectOption("child");
  await first.getByText("Расширенное условие пропуска", { exact: true }).click();
  await scopedField(card, "step-0-skip", "kind").selectOption("all");
  await scopedField(card, "step-0-skip", "mode", "0").selectOption("holidays");
  await card
    .locator('[data-condition-scope="step-0-skip"]')
    .getByRole("button", { name: "Добавить условие", exact: true })
    .click();
  await scopedField(card, "step-0-skip", "kind", "1").selectOption(
    "time_window",
  );
  await scopedField(card, "step-0-skip", "start", "1").fill("21:00");
  await scopedField(card, "step-0-skip", "end", "1").fill("22:00");

  await first.locator('[data-step-confirmation="0"]').selectOption("entity_state");
  await card
    .locator('[data-routine-step-index="0"]')
    .getByText("Условие автоматического завершения", { exact: true })
    .click();
  await scopedField(card, "step-0-completion", "kind").selectOption("all");
  await scopedField(card, "step-0-completion", "kind", "0").selectOption(
    "entity_state",
  );
  await scopedField(card, "step-0-completion", "state", "0").fill("on");
  await card
    .locator('[data-condition-scope="step-0-completion"]')
    .getByRole("button", { name: "Добавить условие", exact: true })
    .click();
  await scopedField(card, "step-0-completion", "mode", "1").selectOption(
    "normal",
  );

  await page.screenshot({
    path: "test-results/routine-step-conditions-ru.png",
    fullPage: true,
  });
  await card
    .locator('[data-routine-step-index="0"]')
    .getByRole("button", { name: "Ниже", exact: true })
    .click();

  await page.evaluate(() => {
    window.commitThenLose = true;
  });
  await card.getByRole("button", { name: "Сохранить", exact: true }).click();
  await expect(card.getByRole("alert")).toBeVisible();
  const lost = await page.evaluate(() => window.calls[0]);
  expect(lost.payload.steps[1]).toMatchObject({
    title: "Умыться",
    assignee: "child",
    confirmation: "entity_state",
    skip_when: {
      kind: "all",
      negate: false,
      conditions: [
        { kind: "mode", mode: "holidays", negate: false },
        {
          kind: "time_window",
          start: "21:00",
          end: "22:00",
          timezone: "Europe/Kyiv",
          negate: false,
        },
      ],
    },
    completion_condition: {
      kind: "all",
      negate: false,
      conditions: [
        {
          kind: "entity_state",
          entity_id: "binary_sensor.synthetic_ready",
          state: "on",
          max_age_seconds: 120,
          negate: false,
        },
        { kind: "mode", mode: "normal", negate: false },
      ],
    },
  });
  expect(lost.payload.steps[0].skip_when).toBeNull();

  await card.getByRole("button", { name: "Повторить", exact: true }).click();
  await expect(card.locator("form")).toHaveCount(0);
  const calls = await page.evaluate(() => window.calls);
  expect(calls).toHaveLength(2);
  expect(calls[1].operation_id).toBe(calls[0].operation_id);
  expect(calls[1].payload).toEqual(calls[0].payload);
});

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
    .locator('[data-condition-scope="template-skip"]')
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

test("Ukrainian manual mode keeps a latent completion draft but knowingly removes it on save", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/tests/fixtures/routines.html?lang=uk");
  await page.evaluate(async () => {
    const step = window.fixture.routines.templates[0].steps[0];
    step.confirmation = "entity_state";
    step.completion_condition = {
      kind: "entity_state",
      entity_id: "binary_sensor.synthetic_ready",
      state: "on",
      max_age_seconds: 120,
      negate: false,
    };
    await window.card.refresh();
  });
  const card = page.locator("family-routines-card");
  await card.getByRole("button", { name: "Редагувати", exact: true }).click();
  await card
    .locator('[data-routine-step-index="0"]')
    .getByText("Умова автоматичного завершення", { exact: true })
    .click();
  await expect(
    scopedField(card, "step-0-completion", "state"),
  ).toHaveValue("on");
  await card.locator('[data-step-confirmation="0"]').selectOption("manual");
  await expect(card.getByText(/Умова завершення збережена/)).toBeVisible();
  await page.screenshot({
    path: "test-results/routine-step-manual-uk.png",
    fullPage: true,
  });
  await card.locator('[data-step-confirmation="0"]').selectOption("entity_state");
  await expect(
    scopedField(card, "step-0-completion", "state"),
  ).toHaveValue("on");
  await card.locator('[data-step-confirmation="0"]').selectOption("manual");
  await card.getByRole("button", { name: "Зберегти", exact: true }).click();
  expect(
    await page.evaluate(
      () => window.calls.at(-1).payload.steps[0].completion_condition,
    ),
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

test("English child run never renders private condition AST values", async ({ page }) => {
  await page.goto("/tests/fixtures/routines.html?child=1&lang=en");
  await page.evaluate(async () => {
    const step = window.fixture.routines.runs[0].steps[0];
    step.skip_when = {
      kind: "entity_state",
      entity_id: "sensor.PRIVATE_SKIP_CANARY",
      state: "PRIVATE_SKIP_STATE",
      negate: false,
    };
    step.completion_condition = {
      kind: "entity_state",
      entity_id: "sensor.PRIVATE_COMPLETION_CANARY",
      state: "PRIVATE_COMPLETION_STATE",
      negate: false,
    };
    await window.card.refresh();
  });
  const card = page.locator("family-routines-card");
  await expect(card.getByRole("button", { name: "Mark step done" })).toBeVisible();
  await expect(card.locator(".condition-editor")).toHaveCount(0);
  const text = await card.textContent();
  expect(text).not.toContain("PRIVATE_SKIP");
  expect(text).not.toContain("PRIVATE_COMPLETION");
});
