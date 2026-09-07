import { test, expect } from "@playwright/test";

const section = (card) => card.locator(".article-section");
const review = (card) => card.locator('[data-article-form="review"]');

async function openReview(card, language, url = "https://example.org/article") {
  const labels = {
    en: ["Read a public article", "Review article request"],
    ru: ["Прочитать публичную статью", "Проверить запрос статьи"],
    uk: ["Прочитати публічну статтю", "Перевірити запит статті"],
  }[language];
  await section(card).getByRole("button", { name: labels[0], exact: true }).click();
  await card.locator('input[name="url"]').fill(url);
  await section(card).getByRole("button", { name: labels[1], exact: true }).click();
}

async function submitReview(card, language) {
  const label = {
    en: "Fetch and summarize article",
    ru: "Загрузить и кратко изложить статью",
    uk: "Завантажити й стисло викласти статтю",
  }[language];
  await review(card).locator('input[name="confirmed"]').check();
  await review(card).getByRole("button", { name: label, exact: true }).click();
}

test("RU mobile explicit review discloses transport and sends one exact request", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/tests/fixtures/article.html?lang=ru&role=parent");
  const card = page.locator("family-conversation-card");
  await expect(section(card)).toBeVisible();
  expect(await page.evaluate(() => window.articleCalls.length)).toBe(0);
  await openReview(card, "ru");
  await expect(review(card)).toContainText("IP-адрес сервера");
  await expect(review(card)).toContainText("без семейного контекста");
  expect(await page.evaluate(() => window.articleCalls.length)).toBe(0);
  await page.screenshot({ path: "test-results/article-review-ru.png", fullPage: true });
  await submitReview(card, "ru");
  await expect(card.locator(".article-result")).toContainText("Public evidence summarized");
  const calls = await page.evaluate(() => window.articleCalls);
  expect(calls).toHaveLength(1);
  expect(calls[0]).toEqual({
    type: "family_assistant/article",
    entry_id: "synthetic-article",
    url: "https://example.org/article",
    operation_id: calls[0].operation_id,
    source_revision: "a".repeat(32),
  });
  expect(typeof calls[0].operation_id).toBe("string");
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
  ).toBe(true);
});

test("UK child opt-in gets inert transient result and child opt-out gets no form", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/tests/fixtures/article.html?lang=uk&role=child");
  const card = page.locator("family-conversation-card");
  await openReview(card, "uk");
  await submitReview(card, "uk");
  await expect(card.locator(".article-result")).toContainText("Public evidence summarized");
  await expect(card.locator(".article-source a")).toHaveAttribute(
    "href",
    "https://example.org/final",
  );
  await expect(card.locator(".article-source a")).toHaveAttribute(
    "rel",
    "noopener noreferrer",
  );
  await expect(card.locator("img")).toHaveCount(0);
  await expect(card.locator("script")).toHaveCount(0);
  await page.screenshot({ path: "test-results/article-result-uk.png", fullPage: true });
  expect(await page.evaluate(() => window.card._data.article_result)).toBeUndefined();

  await page.goto("/tests/fixtures/article.html?lang=en&role=adult&inject=on");
  const inert = page.locator("family-conversation-card");
  await openReview(inert, "en");
  await submitReview(inert, "en");
  await expect(inert.locator(".article-answer")).toContainText("<img src=x");
  await expect(inert.locator("img")).toHaveCount(0);
  await expect(inert.locator(".article-source b")).toHaveCount(0);

  await page.goto("/tests/fixtures/article.html?lang=uk&role=child&children=off");
  const denied = page.locator("family-conversation-card");
  await expect(section(denied)).toContainText("недоступне");
  await expect(section(denied).locator("form")).toHaveCount(0);
});

test("committed response loss retries exact request and ordinary chat stays usable", async ({
  page,
}) => {
  await page.goto("/tests/fixtures/article.html?lang=en&role=adult");
  const card = page.locator("family-conversation-card");
  await openReview(card, "en");
  await page.evaluate(() => (window.failure = "after"));
  await submitReview(card, "en");
  await expect(
    review(card).getByRole("button", { name: "Retry exact request", exact: true }),
  ).toBeVisible();
  const frozen = await page.evaluate(() => structuredClone(window.card._articleDraft.pending));
  await page.evaluate(async () => await window.card.refresh());
  await review(card)
    .getByRole("button", { name: "Retry exact request", exact: true })
    .click();
  await expect(card.locator(".article-result")).toBeVisible();
  const calls = await page.evaluate(() => window.articleCalls);
  expect(calls).toEqual([frozen, frozen]);

  await card.locator('input[name="message"]').fill("hello");
  await card.getByRole("button", { name: "Send", exact: true }).click();
  await expect(card).toContainText("Synthetic chat remains usable");
});

test("harmless rerender settles pending response while source revocation discards it", async ({
  page,
}) => {
  await page.goto("/tests/fixtures/article.html?lang=en&role=parent");
  const card = page.locator("family-conversation-card");
  await openReview(card, "en");
  await page.evaluate(() => window.delayArticle());
  const first = submitReview(card, "en");
  await expect.poll(() => page.evaluate(() => window.articleCalls.length)).toBe(1);
  await page.evaluate(() => window.card.render());
  await page.evaluate(() => window.delayed.release());
  await first;
  await expect(card.locator(".article-result")).toContainText("Public evidence summarized");

  await card.getByRole("button", { name: "Clear article result", exact: true }).click();
  await openReview(card, "en", "https://example.org/second");
  await page.evaluate(() => window.delayArticle());
  void submitReview(card, "en");
  await expect.poll(() => page.evaluate(() => window.articleCalls.length)).toBe(2);
  await page.evaluate(async () => {
    window.fixture.sourceRevision = "b".repeat(32);
    await window.card.refresh();
    window.delayed.release();
  });
  await expect(card.locator(".article-result")).toHaveCount(0);
  await expect(section(card)).not.toContainText("Public evidence summarized");
  expect(await page.evaluate(() => window.card._articleDraft)).toBeNull();
});

test("member module entry generation and HA-user changes revoke focused drafts and old callbacks", async ({
  page,
}) => {
  const mutations = [
    () =>
      page.evaluate(async () => {
        window.fixture.members.find((member) => member.id === "parent-1").revision += 1;
        await window.card.refresh();
      }),
    () =>
      page.evaluate(async () => {
        window.fixture.modules = [];
        await window.card.refresh();
      }),
    () => page.evaluate(() => (window.card._entry = "other-entry")),
    () => page.evaluate(() => (window.card._generation += 1)),
    () => page.evaluate(() => (window.card._hass.user.id = "other-user")),
  ];
  for (const mutate of mutations) {
    await page.goto("/tests/fixtures/article.html?lang=en&role=parent");
    const card = page.locator("family-conversation-card");
    await openReview(card, "en");
    const oldSubmit = await page.evaluateHandle(() =>
      window.card.shadowRoot.querySelector('[data-article-form="review"]'),
    );
    await mutate();
    await oldSubmit.evaluate((form) =>
      form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })),
    );
    expect(await page.evaluate(() => window.articleCalls.length)).toBe(0);
    expect(await page.evaluate(() => window.card._articleDraft)).toBeNull();
  }
});
