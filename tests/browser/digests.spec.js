import { test, expect } from "@playwright/test";

const section = (card) => card.locator(".digests");
const review = (card) => card.locator(".digest-review");

test("RU narrow self preference review freezes the named policy and exact payload", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/tests/fixtures/digests.html?lang=ru&actor=parent");
  const card = page.locator("family-digests-card");
  await expect(section(card)).toBeVisible();
  await expect(section(card)).toContainText("Europe/Kyiv");
  await expect(section(card)).toContainText("воскресенье");
  await expect(section(card)).not.toContainText("Alex");
  await section(card)
    .getByRole("button", { name: "Изменить настройки", exact: true })
    .click();
  await card.locator('input[name="evening"]').check();
  await card
    .getByRole("button", { name: "Проверить настройки", exact: true })
    .click();
  await expect(review(card)).toContainText("Morgan");
  await expect(review(card)).toContainText("Версия участника");
  expect(await page.evaluate(() => window.calls.length)).toBe(0);
  await review(card).locator('input[name="confirmed"]').check();
  await page.screenshot({
    path: "test-results/digests-review-ru.png",
    fullPage: true,
  });
  await review(card)
    .getByRole("button", {
      name: "Сохранить настройки дайджестов",
      exact: true,
    })
    .click();
  await expect(review(card)).toHaveCount(0);
  const calls = await page.evaluate(() => window.calls);
  expect(calls).toHaveLength(1);
  expect(calls[0].payload).toEqual({
    recipient_revision: 4,
    subscription_revision: 2,
    morning: true,
    evening: true,
    weekly: false,
  });
  expect(typeof calls[0].operation_id).toBe("string");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("UK child requests one explicit private preview with only allowlisted content", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/tests/fixtures/digests.html?lang=uk&actor=child");
  const card = page.locator("family-digests-card");
  await expect(section(card)).toContainText("Sam");
  expect(await page.evaluate(() => window.calls.length)).toBe(0);
  await card.locator('select[name="digest_kind"]').selectOption("weekly");
  await section(card)
    .getByRole("button", {
      name: "Створити особистий перегляд",
      exact: true,
    })
    .click();
  await expect(card.locator(".digest-preview-section")).toHaveCount(5);
  const calls = await page.evaluate(() => window.calls);
  expect(calls).toEqual([
    {
      type: "family_assistant/digest_preview",
      entry_id: "synthetic-digests",
      kind: "weekly",
    },
  ]);
  const text = await card.evaluate((element) => element.shadowRoot.textContent);
  expect(text).toContain("Pack school folder");
  expect(text).toContain("Mathematics");
  expect(text).toContain("Відкриті покупки: 4");
  expect(text).toContain("2026-09-07 – 2026-09-13");
  expect(text).not.toContain("2026-09-07 – 2026-09-14");
  expect(text).not.toMatch(
    /PRIVATE-|media_id|allergy|ballot|latitude|location|room/,
  );
  await page.evaluate(() => scrollTo(0, 0));
  await page.screenshot({
    path: "test-results/digests-preview-uk.png",
    fullPage: true,
  });
});

test("source refresh clears shown and delayed private previews", async ({ page }) => {
  await page.goto("/tests/fixtures/digests.html?lang=en&actor=child");
  const card = page.locator("family-digests-card");
  await section(card)
    .getByRole("button", { name: "Build private preview", exact: true })
    .click();
  await expect(card.locator(".digest-preview-section")).toHaveCount(5);
  await page.evaluate(async () => {
    window.fixture.revision += 1;
    window.fixture.settings.modules.push("tasks");
    await window.card.refresh();
  });
  await expect(card.locator(".digest-preview-section")).toHaveCount(0);
  await expect(section(card)).not.toContainText("Pack school folder");

  await page.reload();
  await section(card).waitFor();
  await page.evaluate(() => {
    const original = window.card._hass.callWS;
    let release;
    window.delayedPreview = {
      promise: new Promise((resolve) => {
        release = resolve;
      }),
      release,
    };
    window.card._hass.callWS = (message) =>
      message.type === "family_assistant/digest_preview"
        ? window.delayedPreview.promise
        : original(message);
  });
  await section(card)
    .getByRole("button", { name: "Build private preview", exact: true })
    .click();
  await page.evaluate(async () => {
    window.fixture.revision += 1;
    await window.card.refresh();
    window.delayedPreview.release({
      schema: 1,
      kind: "morning",
      window_start: "2026-09-07",
      window_end: "2026-09-08",
      sections: [
        {
          key: "tasks",
          rows: [
            { title: "STALE PRIVATE TITLE", status: "assigned", due_at: null },
          ],
          count: 1,
          overflow: 0,
        },
      ],
    });
  });
  await expect(card.locator(".digest-preview-section")).toHaveCount(0);
  await expect(section(card)).not.toContainText("STALE PRIVATE TITLE");
});

test("EN committed response loss retries the exact frozen operation", async ({
  page,
}) => {
  await page.goto("/tests/fixtures/digests.html?lang=en&actor=adult");
  const card = page.locator("family-digests-card");
  await section(card)
    .getByRole("button", { name: "Change preferences", exact: true })
    .click();
  await card.locator('input[name="morning"]').check();
  await card
    .getByRole("button", { name: "Review preferences", exact: true })
    .click();
  await review(card).locator('input[name="confirmed"]').check();
  await page.evaluate(() => (window.failMode = "after"));
  await review(card)
    .getByRole("button", { name: "Save digest preferences", exact: true })
    .click();
  await expect(
    review(card).getByRole("button", { name: "Retry exact request" }),
  ).toBeVisible();
  const frozen = await page.evaluate(() =>
    structuredClone(window.card._digestsDraft.pending),
  );
  await page.evaluate(async () => {
    window.fixture.revision += 1;
    await window.card.refresh();
  });
  await expect(
    review(card).getByRole("button", { name: "Retry exact request" }),
  ).toBeVisible();
  await review(card)
    .getByRole("button", { name: "Retry exact request", exact: true })
    .click();
  await expect(review(card)).toHaveCount(0);
  const calls = await page.evaluate(() => window.calls);
  expect(calls).toHaveLength(2);
  expect(calls[1].operation_id).toBe(frozen.operation_id);
  expect(calls[1].payload).toEqual(frozen.payload);
});

test("policy, member, module, and entry changes clear focused private state", async ({
  page,
}) => {
  const cases = [
    async () => {
      await page.evaluate(async () => {
        window.fixture.policy.morning.time = "07:15";
        await window.card.refresh();
      });
    },
    async () => {
      await page.evaluate(async () => {
        const actor = window.fixture.members.find(
          (item) => item.id === "parent-1",
        );
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
  ];
  for (const mutate of cases) {
    await page.goto("/tests/fixtures/digests.html?lang=en&actor=parent");
    const card = page.locator("family-digests-card");
    await section(card)
      .getByRole("button", { name: "Change preferences", exact: true })
      .click();
    await card.locator('input[name="evening"]').check();
    await card
      .getByRole("button", { name: "Review preferences", exact: true })
      .click();
    await review(card).locator('input[name="confirmed"]').check();
    await page.evaluate(() => {
      window.oldSave = window.card.shadowRoot.querySelector(
        ".digest-review button.primary",
      );
    });
    await mutate();
    await page.evaluate(() => window.oldSave.click());
    await expect(review(card)).toHaveCount(0);
    expect(await page.evaluate(() => window.card._digestsDraft)).toBeNull();
    expect(await page.evaluate(() => window.calls.length)).toBe(0);
  }

  await page.goto("/tests/fixtures/digests.html?lang=en&actor=parent");
  await page.evaluate(() => (window.previewFailure = true));
  const card = page.locator("family-digests-card");
  await section(card)
    .getByRole("button", { name: "Build private preview", exact: true })
    .click();
  await expect(card.locator(".digest-preview-section")).toHaveCount(0);
  expect(await page.evaluate(() => window.card._digestsDraft)).toBeNull();
});
