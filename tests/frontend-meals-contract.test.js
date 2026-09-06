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
const { MEALS_COPY } = await import(
  "../custom_components/family_assistant/frontend/meals-copy.js"
);
const tick = () => new Promise((resolve) => setTimeout(resolve, 0));
const sample = () => ({
  id: "MP000001",
  revision: 1,
  status: "draft",
  week_start: "2026-09-07",
  title: "Menu",
  note: "Private",
  entries: [
    {
      date: "2026-09-07",
      slot: "dinner",
      title: "Soup",
      servings: 4,
      ingredients: [{ name: "Carrot", unit: "kg", quantity: 0.5 }],
    },
  ],
  history: [],
});

async function setup(t) {
  const data = {
    revision: 1,
    actor: "parent",
    role: "parent",
    settings: { name: "Example", modules: ["pantry"] },
    members: [],
    pantry: { meal_plans: [sample()] },
  };
  const calls = [],
    receipts = new Map();
  let lose = false;
  const card = document.createElement("family-meals-card");
  card.setConfig({
    type: "custom:family-meals-card",
    entry_id: "synthetic",
    language: "en",
  });
  document.body.append(card);
  t.after(() => card.remove());
  card.hass = {
    language: "en",
    callWS: async (message) => {
      if (message.type.endsWith("/view")) return structuredClone(data);
      calls.push(structuredClone(message));
      if (receipts.has(message.operation_id))
        return structuredClone(receipts.get(message.operation_id));
      const plan = data.pantry.meal_plans[0];
      assert.equal(message.payload.id, plan.id);
      assert.equal(message.payload.revision, plan.revision);
      if (message.action === "pantry.meal_publish") plan.status = "published";
      else if (message.action === "pantry.meal_archive")
        plan.status = "archived";
      else {
        Object.assign(plan, message.payload);
        plan.status = "draft";
      }
      plan.revision++;
      data.revision++;
      receipts.set(message.operation_id, structuredClone(plan));
      if (lose) {
        lose = false;
        throw { code: "storage_error" };
      }
      return structuredClone(plan);
    },
  };
  await tick();
  return {
    card,
    data,
    calls,
    lose: () => {
      lose = true;
    },
  };
}
function button(card, label) {
  const result = [...card.shadowRoot.querySelectorAll("button")].find(
    (b) => b.textContent === label,
  );
  assert.ok(result, `missing ${label}`);
  return result;
}
function input(card, name, value) {
  const element = card.shadowRoot.querySelector(`[name="${name}"]`);
  assert.ok(element);
  element.value = value;
  element.dispatchEvent(new Event("input", { bubbles: true }));
  return element;
}
async function submit(card) {
  card.shadowRoot
    .querySelector("form")
    .dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  await tick();
  await tick();
}

test("real meals alias, pantry gate, editor and localized keys", async (t) => {
  const { card } = await setup(t);
  assert.equal(card._view, "meals");
  button(card, MEALS_COPY.en.new_plan);
  const editor = document.createElement("family-assistant-card-editor");
  editor.setConfig({ type: "custom:family-meals-card" });
  assert.equal(editor.shadowRoot.querySelector('[name="view"]').value, "meals");
  for (const copy of Object.values(MEALS_COPY))
    assert.deepEqual(
      Object.keys(copy).sort(),
      Object.keys(MEALS_COPY.en).sort(),
    );
});
test("real command clears success draft and retains exact receipt retry after committed loss", async (t) => {
  const { card, calls, data, lose } = await setup(t);
  button(card, MEALS_COPY.en.edit).click();
  input(card, "title", "Changed");
  lose();
  await submit(card);
  assert.equal(data.pantry.meal_plans[0].revision, 2);
  assert.ok(card._mealsDraft?.pending);
  button(card, MEALS_COPY.en.retry);
  await submit(card);
  assert.deepEqual(calls[1], calls[0]);
  assert.equal(data.pantry.meal_plans[0].revision, 2);
  assert.equal(card._mealsDraft, null);
  assert.equal(card.shadowRoot.querySelector("form"), null);
});
test("real publish uses checkbox, preserves named review after loss and clears on retry", async (t) => {
  const { card, calls, lose } = await setup(t);
  button(card, MEALS_COPY.en.publish).click();
  let check = card.shadowRoot.querySelector('[name="reviewed"]');
  assert.equal(check.type, "checkbox");
  await submit(card);
  assert.equal(calls.length, 0);
  check.checked = true;
  check.dispatchEvent(new Event("change"));
  lose();
  await submit(card);
  assert.match(
    card.shadowRoot.querySelector("form").textContent,
    /Menu · 2026-09-07/,
  );
  await submit(card);
  assert.deepEqual(calls[1], calls[0]);
  assert.equal(card._mealsDraft, null);
});
test("real focused revision and actor changes cannot send stale edit", async (t) => {
  const { card, data, calls } = await setup(t);
  button(card, MEALS_COPY.en.edit).click();
  const title = input(card, "title", "Draft");
  title.focus();
  data.pantry.meal_plans[0].revision++;
  await card.refresh();
  assert.equal(card.shadowRoot.activeElement, title);
  await submit(card);
  assert.equal(calls.length, 0);
  assert.equal(card._actionError, "conflict");
  button(card, MEALS_COPY.en.edit).click();
  const old = input(card, "title", "Other draft");
  card._data.actor = "other-parent";
  old.value = "Must not mutate";
  old.dispatchEvent(new Event("input"));
  await submit(card);
  assert.equal(calls.length, 0);
  assert.equal(card._mealsDraft.values.title, "Other draft");
  card.render();
  assert.equal(card._mealsDraft, null);
});
test("module off or guest discards private drafts; re-enable does not resurrect them", async (t) => {
  const { card } = await setup(t);
  for (const change of [
    () => {
      card._data.settings.modules = [];
    },
    () => {
      card._data.role = "guest";
    },
  ]) {
    card._data.settings.modules = ["pantry"];
    card._data.role = "parent";
    card.render();
    button(card, MEALS_COPY.en.edit).click();
    change();
    card.render();
    assert.equal(card._mealsDraft, null);
  }
});
test("archive cancel and configuration reset discard draft without mutation", async (t) => {
  const { card, calls } = await setup(t);
  button(card, MEALS_COPY.en.archive).click();
  button(card, MEALS_COPY.en.cancel).click();
  assert.equal(card._mealsDraft, null);
  assert.equal(calls.length, 0);
  button(card, MEALS_COPY.en.edit).click();
  card.setConfig({ type: "custom:family-meals-card", entry_id: "next" });
  assert.equal(card._mealsDraft, null);
});

for (const [field, value] of [
  ["week_start", "9999-12-27"],
  ["week_start", "0000-01-03"],
  ["week_start", "2026-09-08"],
  ["title", "x".repeat(121)],
  ["date", "2026-09-14"],
  ["date", "2026-02-30"],
  ["servings", "1.1"],
  ["servings", "51"],
  ["quantity", "0"],
  ["quantity", "0.0001"],
  ["quantity", "1e3"],
]) {
  test(`real invalid meal ${field}=${value.slice(0, 16)} refuses before transport`, async (t) => {
    const { card, calls } = await setup(t);
    button(card, MEALS_COPY.en.edit).click();
    input(card, field, value);
    await submit(card);
    assert.equal(calls.length, 0);
    assert.equal(card._actionError, "invalid_field");
    assert.ok(card.shadowRoot.querySelector('[role="alert"]'));
    assert.ok(card._mealsDraft);
  });
}
