import assert from "node:assert/strict";
import { test } from "node:test";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><body></body>", {
  url: "https://example.invalid",
});
for (const key of [
  "window",
  "document",
  "Element",
  "HTMLElement",
  "customElements",
  "CustomEvent",
  "Event",
  "FormData",
]) {
  globalThis[key] = dom.window[key];
}

await import("../custom_components/family_assistant/frontend/family-assistant.js");
const { AVAILABILITY_COPY, availabilityState, renderAvailabilityShell } =
  await import("../custom_components/family_assistant/frontend/availability-shell.js");

const PRIVATE = "PRIVATE_ROW_CANARY";

function actualCard(language = "en") {
  const card = document.createElement("family-polls-card");
  card.setConfig({ view: "polls", language });
  document.body.append(card);
  const body = card.shadowRoot.querySelector(".body");
  body.replaceChildren();
  return { card, body };
}

function dispatchCard(view, language = "en") {
  const card = document.createElement(`family-${view}-card`);
  card.setConfig({ view, language, entry_id: "entry-1" });
  document.body.append(card);
  return card;
}

function projected(modules = ["polls"], projection = undefined) {
  return {
    revision: 1,
    actor: "guest",
    role: "guest",
    settings: { name: "Family", modules },
    members: [{ id: PRIVATE, name: PRIVATE, role: "child", active: true }],
    private_payload: PRIVATE,
    ...(projection === undefined ? {} : { polls: projection }),
  };
}

test("copy has exact EN/RU/UK parity and no projected-data placeholders", () => {
  assert.deepEqual(Object.keys(AVAILABILITY_COPY).sort(), ["en", "ru", "uk"]);
  const keys = Object.keys(AVAILABILITY_COPY.en).sort();
  for (const language of ["ru", "uk"]) {
    assert.deepEqual(Object.keys(AVAILABILITY_COPY[language]).sort(), keys);
  }
  assert.equal(JSON.stringify(AVAILABILITY_COPY).includes("${"), false);
});

test("real FamilyCard resolves loading, error, module and role states fail closed", () => {
  const { card } = actualCard();
  assert.equal(availabilityState(card, "polls", undefined), "loading");
  card._data = projected([]);
  assert.equal(availabilityState(card, "polls", undefined), "module_disabled");
  card._data = projected(["polls"]);
  assert.equal(availabilityState(card, "polls", undefined), "role_unavailable");
  assert.equal(availabilityState(card, "polls", []), null);
  card._error = "PRIVATE_ERROR_CANARY";
  assert.equal(availabilityState(card, "polls", []), "error");
  card.remove();
});

test("actual five-module dispatch renders guest shell and clears every private draft", () => {
  const cases = [
    ["school", ["_schoolDraft", "_schoolWorkDraft", "_schoolReminderDraft"]],
    ["maintenance", ["_maintenanceDraft"]],
    ["polls", ["_pollsDraft"]],
    ["presence", ["_presenceDraft"]],
    ["digests", ["_digestsDraft"]],
  ];
  for (const [view, drafts] of cases) {
    const card = dispatchCard(view);
    card._data = {
      ...projected([view]),
      [view]: { private: PRIVATE },
    };
    for (const draft of drafts) card[draft] = { private: PRIVATE };
    card.render();
    const shell = card.shadowRoot.querySelector(".availability-shell");
    assert.equal(shell?.dataset.state, "role_unavailable");
    assert.equal(shell.textContent.includes(PRIVATE), false);
    for (const draft of drafts) assert.equal(card[draft], null);
    assert.equal(card.shadowRoot.querySelector(`.${view}`), null);
    card.remove();
  }
});

test("actual FamilyCard refresh changes an available poll view to generic revoked shell", async () => {
  const card = dispatchCard("polls");
  const allowed = {
    ...projected(["polls"], { open: [], closed: [], archived: [] }),
    actor: "parent",
    role: "parent",
    settings: { name: "Family", modules: ["polls"], timezone: "UTC" },
    members: [{ id: "parent", name: "Parent", role: "parent", active: true, revision: 1 }],
  };
  const revoked = {
    ...projected(["polls"], {}),
    private_payload: PRIVATE,
  };
  const responses = [allowed, revoked];
  card._hass = {
    language: "en",
    user: { id: "ha-user" },
    callWS: async () => structuredClone(responses.shift()),
  };
  await card.refresh();
  assert.notEqual(card.shadowRoot.querySelector(".polls-section"), null);
  assert.equal(card.shadowRoot.querySelector(".availability-shell"), null);

  card._pollsDraft = { private: PRIVATE };
  await card.refresh();
  const shell = card.shadowRoot.querySelector(".availability-shell");
  assert.equal(shell?.dataset.state, "role_unavailable");
  assert.equal(shell.textContent.includes(PRIVATE), false);
  assert.equal(card._pollsDraft, null);
  assert.equal(card.shadowRoot.querySelector(".polls-section"), null);
  card.remove();
});

for (const [language, state, expected] of [
  ["en", "module_disabled", "This module is disabled for this household."],
  ["ru", "role_unavailable", "Эта карточка недоступна для данной учётной записи."],
  ["uk", "loading", "Завантажую актуальні дані…"],
]) {
  test(`${language} ${state} shell uses generic status semantics and no private data`, () => {
    const { card, body } = actualCard(language);
    card._data = state === "loading" ? null : projected(state === "module_disabled" ? [] : ["polls"]);
    const result = renderAvailabilityShell(card, body, {
      module: "polls",
      projection: card._data?.polls,
    });
    assert.equal(result, state);
    const shell = body.querySelector(".availability-shell");
    assert.equal(shell.dataset.state, state);
    assert.equal(shell.getAttribute("role"), "status");
    assert.equal(shell.getAttribute("aria-live"), "polite");
    assert.equal(shell.getAttribute("aria-busy"), state === "loading" ? "true" : "false");
    assert.equal(shell.textContent.includes(expected), true);
    assert.equal(shell.textContent.includes(PRIVATE), false);
    assert.equal(shell.querySelector("button"), null);
    card.remove();
  });
}

test("error shell exposes only localized fixed copy and a keyboard-native retry", async () => {
  const { card, body } = actualCard("ru");
  card._data = projected(["polls"]);
  card._error = "PRIVATE_ERROR_CANARY";
  card._loading = true;
  let retries = 0;
  card.refresh = async () => {
    retries += 1;
  };
  assert.equal(
    renderAvailabilityShell(card, body, { module: "polls", projection: card._data.polls }),
    "error",
  );
  const shell = body.querySelector(".availability-shell");
  assert.equal(shell.getAttribute("role"), "alert");
  assert.equal(shell.getAttribute("aria-live"), "assertive");
  assert.equal(shell.textContent.includes("PRIVATE_ERROR_CANARY"), false);
  const retry = shell.querySelector("button");
  assert.equal(retry.type, "button");
  assert.equal(retry.textContent, "Повторить");
  assert.equal(retry.disabled, false);
  card._loading = false;
  retry.focus();
  retry.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  retry.click();
  await Promise.resolve();
  assert.equal(retries, 1);
  card.remove();
});

test("available or invalid explicit state appends nothing and preserves existing DOM", () => {
  const { card, body } = actualCard();
  const sentinel = document.createElement("span");
  sentinel.textContent = "existing";
  body.append(sentinel);
  card._data = projected(["polls"], []);
  assert.equal(
    renderAvailabilityShell(card, body, { module: "polls", projection: card._data.polls }),
    null,
  );
  assert.equal(renderAvailabilityShell(card, body, { state: "invented" }), null);
  assert.deepEqual([...body.children], [sentinel]);
  card.remove();
});

test("the shell supports an owning DOM realm without a global Element binding", () => {
  const { card, body } = actualCard();
  const previous = globalThis.Element;
  try {
    delete globalThis.Element;
    assert.equal(renderAvailabilityShell(card, body, { state: "loading" }), "loading");
    assert.ok(body.querySelector(".availability-loading"));
    assert.equal(renderAvailabilityShell(card, {}, { state: "loading" }), null);
  } finally {
    globalThis.Element = previous;
    card.remove();
  }
});
