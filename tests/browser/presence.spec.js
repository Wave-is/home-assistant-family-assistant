import { test, expect } from "./control-audit.js";

const section = (card) => card.locator(".presence");
const review = (card) => card.locator(".presence-review");

async function confirm(card, label) {
  await review(card).locator('input[name="confirmed"]').check();
  await review(card).getByRole("button", { name: label, exact: true }).click();
}

test("RU narrow parent sees normalized shared evidence and an exact named self review", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/tests/fixtures/presence.html?lang=ru&actor=parent");
  const card = page.locator("family-presence-card");
  await expect(section(card)).toBeVisible();
  await expect(section(card)).toContainText("Taylor");
  await expect(section(card)).toContainText("По данным источника — не дома");
  await expect(section(card)).toContainText("Sam");
  await expect(section(card)).toContainText("Неизвестно");
  await expect(
    section(card).locator(".presence-shared-row button"),
  ).toHaveCount(0);
  await section(card).locator("details").click();
  await expect(section(card)).toContainText("не точное местоположение");
  await section(card)
    .getByRole("button", { name: "Включить передачу", exact: true })
    .click();
  await expect(review(card)).toContainText("Morgan");
  await expect(review(card)).toContainText("Версия привязки источника");
  expect(await page.evaluate(() => window.calls.length)).toBe(0);
  await page.screenshot({
    path: "test-results/presence-review-ru.png",
    fullPage: true,
  });
  await confirm(card, "Сохранить выбор");
  const calls = await page.evaluate(() => window.calls);
  expect(calls).toHaveLength(1);
  expect(calls[0].payload).toEqual({
    member: "parent-1",
    member_revision: 4,
    binding_revision: 4,
    subscription_revision: null,
    enabled: true,
  });
  expect(typeof calls[0].operation_id).toBe("string");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("UK child has only self consent and exact committed-response retry", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/tests/fixtures/presence.html?lang=uk&actor=child");
  const card = page.locator("family-presence-card");
  await expect(section(card).locator(".presence-self")).toContainText("Sam");
  await expect(section(card).locator(".presence-shared-row")).toHaveCount(0);
  await expect(section(card)).not.toContainText("Taylor");
  await section(card)
    .getByRole("button", { name: "Вимкнути поширення", exact: true })
    .click();
  await page.evaluate(() => (window.failMode = "after"));
  await confirm(card, "Зберегти вибір");
  await expect(
    review(card).getByRole("button", { name: "Повторити точний запит" }),
  ).toBeVisible();
  const frozen = await page.evaluate(() =>
    structuredClone(window.card._presenceDraft.pending),
  );
  expect(
    await page.evaluate(() => window.fixture.subscriptions["child-1"].revision),
  ).toBe(4);
  await page.screenshot({
    path: "test-results/presence-retry-uk.png",
    fullPage: true,
  });
  await review(card)
    .getByRole("button", { name: "Повторити точний запит" })
    .click();
  await expect(review(card)).toHaveCount(0);
  const calls = await page.evaluate(() => window.calls);
  expect(calls).toHaveLength(2);
  expect(calls[1].operation_id).toBe(frozen.operation_id);
  expect(calls[1].payload).toEqual(frozen.payload);
});

test("EN parent DOM contains no raw source, zone, coordinate, or adult controls", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1180, height: 820 });
  await page.goto("/tests/fixtures/presence.html?lang=en&actor=owner");
  const card = page.locator("family-presence-card");
  await expect(section(card)).toBeVisible();
  const text = await card.evaluate((element) => element.shadowRoot.textContent);
  expect(text).not.toMatch(
    /person\.|device_tracker\.|SecretZoneCanary|COORDINATE-CANARY|DEVICE-CANARY/,
  );
  await expect(
    section(card).locator(".presence-shared-row button"),
  ).toHaveCount(0);
  const projected = await page.evaluate(() => window.project().presence);
  expect(JSON.stringify(projected)).not.toMatch(
    /entity_id|latitude|source|SecretZoneCanary/,
  );
  await page.screenshot({
    path: "test-results/presence-parent-en.png",
    fullPage: true,
  });
});

for (const [language, save, retry] of [
  ["en", "Save sharing choice", "Retry exact request"],
  ["ru", "Сохранить выбор", "Повторить точный запрос"],
  ["uk", "Зберегти вибір", "Повторити точний запит"],
]) test(`${language} narrow guardian review, lost response and child-role revocation`, async ({page}) => {
  await page.setViewportSize({width: 390, height: 844});
  await page.goto(`/tests/fixtures/presence.html?lang=${language}&actor=parent`);
  const card = page.locator("family-presence-card");
  const child = card.locator('.presence-managed-row[data-presence-member="child-1"]');
  await expect(child).toContainText("Sam");
  await expect(card.locator('.presence-shared-row[data-presence-member="child-1"]')).toHaveCount(0);
  await expect(card.locator('.presence-managed-row[data-presence-member="adult-1"]')).toHaveCount(0);
  await child.getByRole("button").click();
  await expect(review(card)).toContainText("Sam");
  await page.screenshot({path:`test-results/presence-guardian-${language}.png`, fullPage:true});
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.evaluate(() => window.failMode = "after");
  await confirm(card, save);
  await expect(review(card).getByRole("button", {name:retry, exact:true})).toBeVisible();
  await review(card).getByRole("button", {name:retry, exact:true}).click();
  await expect(review(card)).toHaveCount(0);
  const calls = await page.evaluate(() => window.calls);
  expect(calls).toHaveLength(2);
  expect(calls[1]).toEqual(calls[0]);
  expect(calls[0].action).toBe("presence.guardian_access_set");
  expect(calls[0].payload).toEqual({member:"child-1", member_revision:7, binding_revision:8, subscription_revision:3, enabled:false});
  await child.getByRole("button").click();
  await review(card).locator('input[name="confirmed"]').check();
  await page.evaluate(async () => {
    window.guardianOldSave = window.card.shadowRoot.querySelector(".presence-review button.primary");
    window.fixture.members.find((row) => row.id === "child-1").role = "adult";
    await window.card.refresh();
    window.guardianOldSave.click();
  });
  await expect(review(card)).toHaveCount(0);
  await expect(child).toHaveCount(0);
  expect(await page.evaluate(() => window.calls.length)).toBe(2);
});

test("role epoch, module, entry, and source-pin changes clear private focused DOM", async ({
  page,
}) => {
  const cases = [
    async () => {
      await page.evaluate(async () => {
        const actor = window.fixture.members.find(
          (item) => item.id === "parent-1",
        );
        actor.role = "adult";
        actor.revision += 1;
        await window.card.refresh();
      });
    },
    async () => {
      await page.evaluate(async () => {
        window.fixture.settings.modules = [];
        await window.card.refresh();
      });
    },
    async () => {
      await page.evaluate(() => (window.card._entry = "other-entry"));
    },
    async () => {
      await page.evaluate(async () => {
        window.fixture.sources["parent-1"].revision += 1;
        window.fixture.bindings["parent-1"].revision += 1;
        await window.card.refresh();
      });
    },
  ];
  for (const mutate of cases) {
    await page.goto("/tests/fixtures/presence.html?lang=en&actor=parent");
    const card = page.locator("family-presence-card");
    await section(card)
      .getByRole("button", { name: "Enable sharing", exact: true })
      .click();
    await review(card).locator('input[name="confirmed"]').check();
    await page.evaluate(() => {
      window.oldSave = window.card.shadowRoot.querySelector(
        ".presence-review button.primary",
      );
    });
    await mutate();
    await page.evaluate(() => window.oldSave.click());
    await expect(review(card)).toHaveCount(0);
    expect(await page.evaluate(() => window.card._presenceDraft)).toBeNull();
    expect(await page.evaluate(() => window.calls.length)).toBe(0);
  }
});
