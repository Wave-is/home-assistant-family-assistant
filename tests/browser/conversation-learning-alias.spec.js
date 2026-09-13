import { test, expect } from "./control-audit.js";
import { CONVERSATION_COPY } from "../../custom_components/family_assistant/frontend/conversation-copy.js";

const alias = {
  id: "L000003",
  kind: "member_alias",
  source: "Junipr",
  canonical: "Juniper",
  active: true,
  effective: true,
  revision: 2,
  provenance: "model_name_repair",
};

async function seed(page, rows = [alias], language = "en") {
  await page.goto(`/tests/fixtures/conversation.html?lang=${language}&role=parent`);
  await page.evaluate(async (rows) => {
    window.fixture.learned.push(...rows);
    await window.card.refresh();
  }, rows);
  return page.locator("family-conversation-card");
}

async function openLearning(card) {
  const learning = card.locator(".conversation-learning");
  if ((await learning.getAttribute("open")) === null)
    await learning.locator("summary").click();
  return learning;
}

for (const language of ["en", "ru", "uk"]) {
  test(`${language} learned name spelling is explained, private text stays inert and Disable preserves other phrases`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const copy = CONVERSATION_COPY[language];
    const row = { ...alias, source: "<img src=x onerror=alert(1)>", canonical: "<b>Juniper</b>" };
    const card = await seed(page, [row], language);
    let learning = await openLearning(card);
    const item = learning.locator(".item").filter({ hasText: copy.learned_name });
    await expect(item).toContainText(`${row.source} → ${row.canonical}`);
    await expect(item).toContainText(copy.learned_name_hint);
    await expect(item).not.toContainText(copy.learned_name_inactive);
    await expect(learning.locator("img,b")).toHaveCount(0);
    expect(await page.evaluate(() => window.executeCalls)).toEqual([]);
    expect(await page.evaluate(() => window.chatCalls)).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);

    await item.getByRole("button", { name: copy.forget, exact: true }).click();
    await expect.poll(() => page.evaluate(() => window.fixture.learned.find(row => row.id === "L000003").active)).toBe(false);
    learning = await openLearning(card);
    await expect(learning).not.toContainText(copy.learned_name);
    await expect(learning).toContainText("/stats");
    const calls = await page.evaluate(() => window.executeCalls);
    expect(calls).toHaveLength(1);
    expect(calls[0]).toEqual({
      type: "family_assistant/execute", entry_id: "synthetic-conversation",
      action: "conversation.forget", payload: { id: "L000003" }, operation_id: calls[0].operation_id,
    });
    expect(await page.evaluate(() => window.fixture.learned.find(row => row.id === "L000001").active)).toBe(true);
  });
}

test("an active but ineffective spelling explains the stale binding and can still be disabled", async ({ page }) => {
  const card = await seed(page, [{ ...alias, effective: false }]);
  const learning = await openLearning(card);
  const item = learning.locator(".item").filter({ hasText: CONVERSATION_COPY.en.learned_name });
  await expect(item).toContainText("Junipr → Juniper");
  await expect(item).toContainText(CONVERSATION_COPY.en.learned_name_inactive);
  await expect(item.getByRole("button", { name: "Disable phrase", exact: true })).toBeEnabled();
  await item.getByRole("button", { name: "Disable phrase", exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.fixture.learned.find(row => row.id === "L000003").active)).toBe(false);
  expect((await page.evaluate(() => window.executeCalls))[0].payload).toEqual({ id: "L000003" });
});

test("disabled aliases stay hidden and the existing explicit phrase form retains its exact contract", async ({ page }) => {
  const card = await seed(page, [{ ...alias, active: false, effective: false }]);
  const learning = await openLearning(card);
  await expect(learning).not.toContainText("Junipr");
  await expect(learning).not.toContainText(CONVERSATION_COPY.en.learned_name);
  await learning.getByLabel("Unrecognized phrase", { exact: true }).fill("my private overview");
  await learning.getByLabel("Supported reusable command", { exact: true }).fill("/stats");
  await learning.getByRole("button", { name: "Save", exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.executeCalls.length)).toBe(1);
  expect((await page.evaluate(() => window.executeCalls))[0]).toMatchObject({
    action: "conversation.learn", payload: { source: "my private overview", canonical: "/stats" },
  });
  expect(await page.evaluate(() => window.fixture.learned.find(row => row.id === "L000003").active)).toBe(false);
});

test("failed alias Disable retains the record and retries the same operation without disabling a sibling", async ({ page }) => {
  const card = await seed(page);
  await page.evaluate(() => {
    const original = window.card._hass.callWS.bind(window.card._hass);
    window.aliasCalls = [];
    window.card._hass.callWS = async request => {
      if (request.type === "family_assistant/execute" && request.action === "conversation.forget") {
        window.aliasCalls.push(structuredClone(request));
        if (window.aliasCalls.length === 1)
          throw Object.assign(new Error("not_ready"), { code: "not_ready" });
      }
      return original(request);
    };
  });
  let learning = await openLearning(card);
  await learning.locator(".item").filter({ hasText: CONVERSATION_COPY.en.learned_name })
    .getByRole("button", { name: "Disable phrase", exact: true }).click();
  await expect(card.getByRole("alert")).toBeVisible();
  expect(await page.evaluate(() => window.fixture.learned.find(row => row.id === "L000003").active)).toBe(true);
  learning = await openLearning(card);
  await learning.locator(".item").filter({ hasText: CONVERSATION_COPY.en.learned_name })
    .getByRole("button", { name: "Disable phrase", exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.fixture.learned.find(row => row.id === "L000003").active)).toBe(false);
  await expect(card.getByRole("alert")).toHaveCount(0);
  const calls = await page.evaluate(() => window.aliasCalls);
  expect(calls).toHaveLength(2);
  expect(calls[1]).toEqual(calls[0]);
  expect(calls[0].payload).toEqual({ id: "L000003" });
  expect(await page.evaluate(() => window.fixture.learned.find(row => row.id === "L000001").active)).toBe(true);
});

test("old alias Disable cannot write after an actor epoch change and module revocation hides private rows", async ({ page }) => {
  const card = await seed(page);
  const learning = await openLearning(card);
  const oldButton = await learning.locator(".item").filter({ hasText: CONVERSATION_COPY.en.learned_name })
    .getByRole("button", { name: "Disable phrase", exact: true }).elementHandle();
  await page.evaluate(async () => {
    window.fixture.members.find(row => row.id === window.fixture.actor).revision++;
    window.fixture.learned = [];
    await window.card.refresh();
  });
  await oldButton.evaluate(button => button.click());
  expect(await page.evaluate(() => window.executeCalls)).toEqual([]);
  await expect(card).not.toContainText("Junipr");

  await page.evaluate(async row => {
    window.fixture.learned = [row];
    window.fixture.modules = [];
    await window.card.refresh();
  }, alias);
  await expect(card.locator(".conversation-learning")).toHaveCount(0);
  expect(await page.evaluate(() => window.executeCalls)).toEqual([]);
});
