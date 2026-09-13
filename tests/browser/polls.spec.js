import { test, expect } from "./control-audit.js";

const review = (card) => card.locator('[data-poll-form="review"]');

async function confirm(card, label) {
  const form = review(card);
  await form.locator('[name="confirmed"]').check();
  await form.getByRole("button", { name: label, exact: true }).click();
}

test("RU parent creates a DST-disambiguated poll only after the named privacy review", async ({
  page,
}) => {
  await page.clock.install({ time: new Date("2026-10-01T12:00:00Z") });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/tests/fixtures/polls.html?lang=ru&actor=parent");
  const card = page.locator("family-polls-card");
  await card.locator(".polls-section>details summary").click();
  await expect(card).toContainText("голосование не анонимное");
  await expect(card).toContainText("не запускает рутины");
  await card
    .getByRole("button", { name: "Создать голосование", exact: true })
    .click();
  const form = card.locator('[data-poll-form="create"]');
  await form.locator('[name="question"]').fill("Куда пойдём в выходные?");
  const options = form.locator(".poll-option-editor input");
  await options.nth(0).fill("Парк");
  await options.nth(1).fill("Музей");
  await form.locator('.poll-eligible input[value="parent"]').check();
  await form.locator('.poll-eligible input[value="child"]').check();
  await form.locator('[name="closes_at"]').fill("2026-10-25T03:30");
  await expect(form.locator('[name="deadline_fold"]')).toBeVisible();
  await form.locator('[name="deadline_fold"]').selectOption("1");
  await form.locator('button[type="submit"]').click();
  await expect(review(card)).toContainText("Куда пойдём в выходные?");
  await expect(review(card)).toContainText("Alex, Sam");
  await expect(review(card)).toContainText("2026-10-25 03:30 · Europe/Kyiv");
  expect(await page.evaluate(() => window.calls.length)).toBe(0);
  await page.screenshot({
    path: "test-results/polls-create-review-ru.png",
    fullPage: true,
  });
  await confirm(card, "Сохранить проверенный запрос");
  await expect(review(card)).toHaveCount(0);
  const calls = await page.evaluate(() => window.calls);
  expect(calls).toHaveLength(1);
  expect(calls[0].action).toBe("polls.create");
  expect(calls[0].payload).toEqual({
    actor_revision: 3,
    question: "Куда пойдём в выходные?",
    options: ["Парк", "Музей"],
    eligible: [
      { member: "parent", revision: 3 },
      { member: "child", revision: 5 },
    ],
    closes_at: "2026-10-25T01:30:00.000Z",
    confirm_private_ballot_limits: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("UK child vote and revote keep the private exact operation across a lost response", async ({
  page,
}) => {
  await page.clock.install({ time: new Date("2026-10-01T12:00:00Z") });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/tests/fixtures/polls.html?lang=uk&actor=child");
  const card = page.locator("family-polls-card");
  const open = card.locator('[data-poll-id="PL000001"]');
  await expect(open.locator(".poll-results")).toHaveCount(0);
  await expect(card.locator('[data-poll-id="PL000003"]')).toHaveCount(0);
  await expect(open).not.toContainText("Alex");
  await open
    .getByRole("button", { name: "Проголосувати", exact: true })
    .click();
  let form = card.locator('[data-poll-form="vote"]');
  await form.locator('input[value="O1"]').check();
  await form.locator('button[type="submit"]').click();
  await expect(review(card)).toContainText("River park");
  await page.evaluate(() => (window.loseResponse = true));
  await confirm(card, "Зберегти перевірений запит");
  await expect(review(card)).toContainText("Результат не підтверджено");
  const frozen = await page.evaluate(() =>
    structuredClone(window.card._pollsDraft.pending),
  );
  await review(card)
    .getByRole("button", { name: "Повторити точний запит", exact: true })
    .click();
  await expect(review(card)).toHaveCount(0);
  let calls = await page.evaluate(() => window.calls);
  expect(calls).toHaveLength(2);
  expect(calls[1]).toEqual(calls[0]);
  expect(calls[1].operation_id).toBe(frozen.operation_id);
  expect(calls[1].payload).toEqual(frozen.payload);
  expect(calls[0].payload).toEqual({
    id: "PL000001",
    definition_revision: 1,
    voter_revision: 5,
    option_id: "O1",
    ballot_revision: null,
  });

  await open
    .getByRole("button", { name: "Змінити голос", exact: true })
    .click();
  form = card.locator('[data-poll-form="vote"]');
  await form.locator('input[value="O2"]').check();
  await form.locator('button[type="submit"]').click();
  await expect(review(card)).toContainText("History museum");
  await page.screenshot({
    path: "test-results/polls-revote-review-uk.png",
    fullPage: true,
  });
  await confirm(card, "Зберегти перевірений запит");
  calls = await page.evaluate(() => window.calls);
  expect(calls).toHaveLength(3);
  expect(calls[2].payload.ballot_revision).toBe(1);
  expect(calls[2].payload.option_id).toBe("O2");
});

test("role epoch and module revocation remove focused private poll DOM and detach old controls", async ({
  page,
}) => {
  await page.clock.install({ time: new Date("2026-10-01T12:00:00Z") });
  await page.goto("/tests/fixtures/polls.html?lang=en&actor=child");
  const card = page.locator("family-polls-card");
  await card.getByRole("button", { name: "Vote", exact: true }).click();
  await card.locator('[data-poll-form="vote"] input[value="O1"]').check();
  await page.evaluate(async () => {
    window.oldPollForm = window.card.shadowRoot.querySelector(
      '[data-poll-form="vote"]',
    );
    const child = window.pollFixture.members.find(
      (item) => item.id === "child",
    );
    child.role = "guest";
    child.revision += 1;
    await window.card.refresh();
    window.oldPollForm.dispatchEvent(
      new Event("submit", { bubbles: true, cancelable: true }),
    );
  });
  await expect(card.locator(".polls-section")).toHaveCount(0);
  expect(await page.evaluate(() => window.card._pollsDraft)).toBeNull();
  expect(await page.evaluate(() => window.calls.length)).toBe(0);

  await page.goto("/tests/fixtures/polls.html?lang=en&actor=parent");
  await card.getByRole("button", { name: "Create poll", exact: true }).click();
  await page.evaluate(async () => {
    window.pollFixture.settings.modules = [];
    await window.card.refresh();
  });
  await expect(card.locator(".polls-section")).toHaveCount(0);
  expect(await page.evaluate(() => window.card._pollsDraft)).toBeNull();
});

test("owner sees only closed aggregates, then explicitly archives and purges the named history row", async ({
  page,
}) => {
  await page.clock.install({ time: new Date("2026-10-01T12:00:00Z") });
  await page.goto("/tests/fixtures/polls.html?lang=en&actor=owner");
  const card = page.locator("family-polls-card");
  await expect(
    card.locator('[data-poll-id="PL000001"] .poll-results'),
  ).toHaveCount(0);
  await expect(
    card.locator('[data-poll-id="PL000002"] .poll-results'),
  ).toContainText("Comedy: 2");
  await expect(
    card.locator('[data-poll-id="PL000002"] .poll-results'),
  ).toContainText("Documentary: 1");
  await page.screenshot({
    path: "test-results/polls-owner-aggregate-en.png",
    fullPage: true,
  });

  const closed = card.locator('[data-poll-id="PL000002"]');
  await closed
    .getByRole("button", { name: "Archive poll", exact: true })
    .click();
  await expect(review(card)).toContainText("Family film?");
  await confirm(card, "Save reviewed request");
  await expect(review(card)).toHaveCount(0);
  const archived = card.locator('[data-poll-id="PL000002"]');
  await archived.locator("summary").click();
  await archived
    .getByRole("button", { name: "Permanently delete poll", exact: true })
    .click();
  await expect(review(card)).toContainText("This cannot be undone");
  expect(await page.evaluate(() => window.calls.length)).toBe(1);
  await confirm(card, "Save reviewed request");
  await expect(review(card)).toHaveCount(0);
  const calls = await page.evaluate(() => window.calls);
  expect(calls).toHaveLength(2);
  expect(calls[0].payload).toEqual({
    id: "PL000002",
    revision: 2,
    actor_revision: 1,
  });
  expect(calls[1].payload).toEqual({
    id: "PL000002",
    revision: 3,
    actor_revision: 1,
    confirm_delete: true,
  });
  await expect(card.locator('[data-poll-id="PL000002"]')).toHaveCount(0);
});
