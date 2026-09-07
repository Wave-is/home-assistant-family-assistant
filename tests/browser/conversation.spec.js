import { test, expect } from "@playwright/test";

const chat = (card) => card.locator(".conversation-chat");

async function send(card, text, label = "Send") {
  await chat(card).getByLabel(/Message|Сообщение|Повідомлення/, { exact: true }).fill(text);
  await chat(card).getByRole("button", { name: label, exact: true }).click();
}

test("RU mobile deterministic chat and learned phrases use real card paths", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/tests/fixtures/conversation.html?lang=ru&configured=off");
  const card = page.locator("family-conversation-card");
  await expect(chat(card)).toContainText("Встроенные команды доступны");
  await send(card, "/ping", "Отправить");
  await expect(chat(card)).toContainText("I am here. Lists and tasks work without a model.");
  const call = (await page.evaluate(() => window.chatCalls))[0];
  expect(call).toEqual({
    type: "family_assistant/chat",
    entry_id: "synthetic-conversation",
    text: "/ping",
    operation_id: call.operation_id,
    session_id: call.session_id,
    actor_revision: 3,
    source_revision: "c".repeat(32),
  });
  await chat(card).getByText("Обучить фразе", { exact: true }).click();
  await chat(card).getByLabel("Непонятная фраза", { exact: true }).fill("покажи баланс");
  await chat(card)
    .getByLabel("Поддерживаемая повторяемая команда", { exact: true })
    .fill("/stats");
  await chat(card).getByRole("button", { name: "Сохранить", exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.executeCalls.length)).toBe(1);
  expect((await page.evaluate(() => window.executeCalls))[0].action).toBe("conversation.learn");
  expect(await card.locator("img").count()).toBe(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await expect(chat(card).getByRole("button", { name: "Отправить" })).toBeEnabled();
  await page.evaluate(() => (window.failure = "provider"));
  await send(card, "новый запрос после ошибки", "Отправить");
  await expect(chat(card)).toContainText("Предыдущий запрос мог выполниться");
  await page.screenshot({
    path: "test-results/conversation-new-request-warning-ru.png",
    fullPage: true,
  });
});

test("UK child receives only own transient inert reply and guest has no chat form", async ({ page }) => {
  await page.goto("/tests/fixtures/conversation.html?lang=uk&role=child");
  const card = page.locator("family-conversation-card");
  await send(card, "привіт", "Надіслати");
  await expect(chat(card).locator(".conversation-reply")).toContainText("<b>Private answer</b>");
  await expect(chat(card).locator("b")).toHaveCount(0);
  expect(await page.evaluate(() => window.card._data.conversation_reply)).toBeUndefined();

  await page.goto("/tests/fixtures/conversation.html?lang=en&role=guest");
  const denied = page.locator("family-conversation-card");
  await expect(chat(denied).locator("form")).toHaveCount(0);
});

test("committed response loss retries the exact frozen request and clears prior reply", async ({ page }) => {
  await page.goto("/tests/fixtures/conversation.html?lang=en&role=adult");
  const card = page.locator("family-conversation-card");
  await send(card, "first answer");
  await expect(chat(card).locator(".conversation-reply")).toBeVisible();
  await page.evaluate(() => (window.failure = "after"));
  await send(card, "second answer");
  await expect(chat(card).locator(".conversation-reply")).toHaveCount(0);
  await expect(chat(card).getByRole("button", { name: "Retry exact request" })).toBeVisible();
  const frozen = await page.evaluate(() => structuredClone(window.card._conversationDraft.pending));
  await chat(card).getByRole("button", { name: "Retry exact request" }).click();
  await expect(chat(card).locator(".conversation-reply")).toContainText("second answer");
  const calls = await page.evaluate(() => window.chatCalls);
  expect(calls.slice(-2)).toEqual([frozen, frozen]);

  await page.evaluate(() => (window.failure = "provider"));
  await send(card, "provider can be repaired later");
  await expect(chat(card)).toContainText("The previous request may have succeeded");
  const beforeStartOver = await page.evaluate(() => window.chatCalls.length);
  await chat(card).getByRole("button", { name: "Start a new request" }).click();
  expect(await page.evaluate(() => window.chatCalls.length)).toBe(beforeStartOver);
  await expect(chat(card).getByLabel("Message", { exact: true })).toBeEnabled();
  await expect(chat(card).getByLabel("Message", { exact: true })).toHaveValue("");

  await page.evaluate(() => (window.failure = "after"));
  await send(card, "uncertain request to abandon");
  await expect(chat(card).getByRole("button", { name: "Start a new request" })).toBeVisible();
  const uncertain = await page.evaluate(() =>
    structuredClone(window.card._conversationDraft.pending),
  );
  await chat(card).getByRole("button", { name: "Start a new request" }).click();
  expect(await page.evaluate(() => window.chatCalls.length)).toBe(beforeStartOver + 1);
  await send(card, "replacement after warning");
  const finalCalls = await page.evaluate(() => window.chatCalls);
  expect(finalCalls.at(-1).operation_id).not.toBe(uncertain.operation_id);
});

test("harmless refresh settles a pending reply but source revocation discards it", async ({ page }) => {
  await page.goto("/tests/fixtures/conversation.html?lang=en&role=parent");
  const card = page.locator("family-conversation-card");
  await page.evaluate(() => window.delayChat());
  void send(card, "settle after refresh");
  await expect.poll(() => page.evaluate(() => window.chatCalls.length)).toBe(1);
  await page.evaluate(async () => {
    await window.card.refresh();
    window.lastDelay.release();
  });
  await expect(chat(card).locator(".conversation-reply")).toContainText("settle after refresh");

  await page.evaluate(() => window.delayChat());
  void send(card, "must be revoked");
  await expect.poll(() => page.evaluate(() => window.chatCalls.length)).toBe(2);
  await page.evaluate(async () => {
    window.fixture.sourceRevision = "d".repeat(32);
    await window.card.refresh();
  });
  await page.evaluate(() => window.delayChat());
  void send(card, "new current request");
  await expect.poll(() => page.evaluate(() => window.chatCalls.length)).toBe(3);
  await page.evaluate(() => window.allDelays[1].release());
  await page.waitForTimeout(20);
  expect(await page.evaluate(() => window.card._conversationDraft.loading)).toBe(true);
  await expect(chat(card)).not.toContainText("must be revoked");
  await page.evaluate(() => window.allDelays[2].release());
  await expect(chat(card).locator(".conversation-reply")).toContainText(
    "new current request",
  );

  await page.goto("/tests/fixtures/conversation.html?lang=en&role=parent");
  const rebound = page.locator("family-conversation-card");
  await page.evaluate(() => window.delayChat());
  void send(rebound, "actor epoch private response");
  await expect.poll(() => page.evaluate(() => window.chatCalls.length)).toBe(1);
  await page.evaluate(async () => {
    window.fixture.members.find((item) => item.id === "parent-1").revision += 1;
    await window.card.refresh();
    window.allDelays[0].release();
  });
  await expect(chat(rebound)).not.toContainText("actor epoch private response");
  expect(await page.evaluate(() => window.card._conversationDraft?.reply ?? null)).toBeNull();
});

test("identity/module changes revoke focused state and detach discards pending completion", async ({ page }) => {
  const mutations = [
    () =>
      page.evaluate(async () => {
        window.fixture.members.find((item) => item.id === "parent-1").revision += 1;
        await window.card.refresh();
      }),
    () =>
      page.evaluate(async () => {
        window.fixture.modules = [];
        await window.card.refresh();
      }),
    () =>
      page.evaluate(async () => {
        window.fixture.malformedSource = true;
        await window.card.refresh();
      }),
    () =>
      page.evaluate(() =>
        window.card.setConfig({
          ...window.card._config,
          entry_id: "other-entry",
        }),
      ),
    () => page.evaluate(() => window.card.setConfig({ ...window.card._config })),
    () =>
      page.evaluate(() => {
        window.card.hass = {
          ...window.card._hass,
          user: { id: "other-user" },
        };
      }),
  ];
  for (const mutate of mutations) {
    await page.goto("/tests/fixtures/conversation.html?lang=en&role=parent");
    const card = page.locator("family-conversation-card");
    await chat(card).getByLabel("Message", { exact: true }).fill("private focused draft");
    await mutate();
    expect(
      await page.evaluate(() => window.card._conversationDraft?.text ?? null),
    ).not.toBe("private focused draft");
    const currentInput = chat(card).locator('input[name="message"]');
    if (await currentInput.count())
      await expect(currentInput).not.toHaveValue("private focused draft");
  }

  await page.goto("/tests/fixtures/conversation.html?lang=en&role=parent");
  const detachedForget = await chat(page.locator("family-conversation-card"))
    .locator(".conversation-learning .item button")
    .elementHandle();
  await page.evaluate(() => window.card.remove());
  await detachedForget.evaluate((button) => button.click());
  expect(await page.evaluate(() => window.executeCalls.length)).toBe(0);

  await page.goto("/tests/fixtures/conversation.html?lang=en&role=parent");
  await page.evaluate(() => window.delayChat());
  const card = page.locator("family-conversation-card");
  void send(card, "private detached response");
  await expect.poll(() => page.evaluate(() => window.chatCalls.length)).toBe(1);
  await page.evaluate(() => {
    window.card.remove();
    window.lastDelay.release();
  });
  await page.waitForTimeout(20);
  expect(await page.evaluate(() => window.card._conversationDraft)).toBeNull();
  await page.evaluate(() => document.querySelector("main").append(window.card));
  await expect(chat(card)).not.toContainText("private detached response");
});
