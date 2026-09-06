import assert from "node:assert/strict";
import { test } from "node:test";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><body></body>", {
  url: "https://example.invalid",
});
for (const key of [
  "window",
  "document",
  "HTMLElement",
  "customElements",
  "CustomEvent",
  "Event",
  "FormData",
])
  globalThis[key] = dom.window[key];

await import(
  "../custom_components/family_assistant/frontend/family-assistant.js"
);
const { PANTRY_COPY } = await import(
  "../custom_components/family_assistant/frontend/pantry-copy.js"
);

const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

async function eventually(predicate, message = "condition was not reached") {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    if (predicate()) return;
    await tick();
  }
  assert.fail(message);
}

function projectedState({
  role = "parent",
  modules = ["pantry"],
  enabled,
  days,
  timezone = "Europe/Kyiv",
} = {}) {
  const settings = {
    name: "Synthetic household",
    language: "en",
    modules,
    timezone,
  };
  if (enabled !== undefined) settings.pantry_expiry_reminders = enabled;
  if (days !== undefined) settings.pantry_expiry_days = days;
  return {
    revision: 1,
    actor: "member-1",
    role,
    settings,
    members: [
      { id: "member-1", name: "Member", role, active: true, revision: 1 },
    ],
    pantry: {
      items: [
        {
          id: "PI000001",
          revision: 4,
          status: "active",
          name: "Milk",
          unit: "l",
          quantity: 1,
          minimum_quantity: 0,
          category: "",
          location: "Fridge",
          note: "Parent note",
          expires_on: "2026-09-10",
          expiry_status: "expiring",
          history: [],
        },
      ],
      archived: [],
      suggestions: [],
    },
  };
}

async function setup(t, options = {}) {
  const state = projectedState(options);
  const executeCalls = [];
  const card = document.createElement("family-pantry-card");
  card.setConfig({
    type: "custom:family-pantry-card",
    entry_id: "synthetic",
    language: options.language || "en",
  });
  document.body.append(card);
  t.after(() => card.remove());
  card.hass = {
    language: options.language || "en",
    callWS: async (message) => {
      if (message.type === "family_assistant/view")
        return structuredClone(state);
      if (message.type === "family_assistant/execute") {
        executeCalls.push(structuredClone(message));
        throw new Error("expiry information must not execute commands");
      }
      throw new Error(`unexpected WebSocket type: ${message.type}`);
    },
  };
  await eventually(() => Boolean(card._data) && !card._loading);
  return { card, state, executeCalls };
}

function info(card) {
  return card.shadowRoot.querySelector("[data-pantry-expiry-info]");
}

function button(card, label) {
  const found = [...card.shadowRoot.querySelectorAll("button")].find(
    (candidate) => candidate.textContent === label,
  );
  assert.ok(found, `missing button: ${label}`);
  return found;
}

test("missing opt-in defaults to a parent-only disabled, settings-only status", async (t) => {
  const { card, state, executeCalls } = await setup(t);
  for (const language of Object.values(PANTRY_COPY))
    assert.deepEqual(
      Object.keys(language).sort(),
      Object.keys(PANTRY_COPY.en).sort(),
    );

  const panel = info(card);
  assert.ok(panel);
  assert.equal(panel.dataset.pantryExpiryInfo, "disabled");
  assert.match(panel.textContent, /Expiry reminders/);
  assert.match(panel.textContent, /Disabled/);
  assert.match(panel.textContent, /household owner/);
  assert.match(panel.textContent, /integration's Settings/);
  assert.equal(panel.querySelector("button,input,select,form"), null);

  const before = structuredClone(state);
  card.render();
  await card.refresh();
  assert.deepEqual(state, before);
  assert.equal(executeCalls.length, 0);
});

test("enabled status is factual, localized, private, and uses the settings timezone", async (t) => {
  for (const [language, role] of [
    ["en", "parent"],
    ["ru", "owner"],
    ["uk", "parent"],
  ]) {
    const { card, executeCalls } = await setup(t, {
      language,
      role,
      enabled: true,
      days: 3,
      timezone: "Europe/Kyiv",
    });
    const panel = info(card);
    assert.ok(panel, `${language} ${role}`);
    assert.equal(panel.dataset.pantryExpiryInfo, "enabled");
    for (const key of [
      "expiry_reminders_title",
      "expiry_reminders_on",
      "expiry_reminders_factual",
      "expiry_reminders_settings",
    ]) {
      assert.ok(panel.textContent.includes(PANTRY_COPY[language][key]), key);
    }
    assert.ok(panel.textContent.includes("09:00"));
    assert.ok(panel.textContent.includes("Europe/Kyiv"));
    assert.ok(panel.textContent.includes("3"));
    assert.equal(panel.querySelector("button,input,select,form"), null);
    assert.equal(executeCalls.length, 0);
  }
});

test("zero-day lead is valid and does not fall back to three days", async (t) => {
  const { card, executeCalls } = await setup(t, {
    enabled: true,
    days: 0,
    timezone: "UTC",
  });
  const panel = info(card);
  assert.ok(panel.textContent.includes("only on the recorded expiry date"));
  assert.ok(panel.textContent.includes("09:00"));
  assert.ok(panel.textContent.includes("UTC"));
  assert.equal(panel.textContent.includes("next 3 days"), false);
  assert.equal(panel.textContent.includes("{"), false);
  assert.equal(executeCalls.length, 0);
});

test("adult, child, guest, and module-off views expose no reminder policy", async (t) => {
  for (const role of ["adult", "child", "guest"]) {
    const { card, executeCalls } = await setup(t, {
      role,
      enabled: true,
      days: 3,
    });
    assert.equal(info(card), null, role);
    assert.equal(executeCalls.length, 0);
  }

  const { card, executeCalls } = await setup(t, {
    role: "parent",
    modules: [],
    enabled: true,
    days: 3,
  });
  assert.equal(info(card), null);
  assert.ok(card.shadowRoot.textContent.includes(card.t.moduleOff));
  assert.equal(executeCalls.length, 0);
});

test("static reminder information does not disturb a pantry draft or focused form", async (t) => {
  const { card, executeCalls } = await setup(t, {
    enabled: true,
    days: 3,
  });
  button(card, PANTRY_COPY.en.new_item).click();
  let field = card.shadowRoot.querySelector('[name="name"]');
  field.value = "Typed pantry item";
  field.dispatchEvent(new Event("input", { bubbles: true }));
  field.focus();
  const draft = card._pantryDraft;
  await card.refresh();
  assert.equal(card.shadowRoot.activeElement, field);
  assert.equal(field.value, "Typed pantry item");
  assert.equal(card._pantryDraft, draft);
  assert.ok(info(card));

  card.render();
  field = card.shadowRoot.querySelector('[name="name"]');
  assert.equal(field.value, "Typed pantry item");
  assert.equal(card._pantryDraft, draft);
  assert.equal(executeCalls.length, 0);
});
