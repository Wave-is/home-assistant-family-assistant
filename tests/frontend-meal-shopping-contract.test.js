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
const { MEAL_SHOPPING_COPY } = await import(
  "../custom_components/family_assistant/frontend/meal-shopping-copy.js"
);

const clone = (value) => structuredClone(value);
const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

async function eventually(predicate, message = "condition was not reached") {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    if (predicate()) return;
    await tick();
  }
  assert.fail(message);
}

function mealPlan() {
  return {
    id: "MP000001",
    revision: 3,
    status: "published",
    week_start: "2026-09-07",
    title: "Autumn menu",
    note: "Private parent note",
    entries: [
      {
        date: "2026-09-07",
        slot: "dinner",
        title: "Rice soup",
        servings: 4,
        ingredients: [
          { name: "Rice", unit: "kg", quantity: 2 },
          { name: "Saffron", unit: "kg", quantity: 0.001 },
        ],
      },
    ],
    history: [],
  };
}

function openProposal() {
  return {
    id: "MS000001",
    revision: 1,
    status: "open",
    source_plan_id: "MP000001",
    source_revision: 3,
    plan_title: "Autumn menu",
    week_start: "2026-09-07",
    lines: [
      {
        name: "Rice",
        unit: "kg",
        required: 2,
        stock: 0.5,
        open_shopping: 0.5,
        deficit: 1,
        quantity: 1,
      },
      {
        name: "Saffron",
        unit: "kg",
        required: 0.001,
        stock: 0.001,
        open_shopping: 0,
        deficit: 0,
        quantity: 0,
      },
    ],
  };
}

function viewState(withProposal = false) {
  return {
    revision: 1,
    actor: "parent",
    role: "parent",
    settings: {
      name: "Synthetic household",
      modules: ["pantry", "shopping"],
    },
    members: [{ id: "parent", name: "Parent", role: "parent", active: true }],
    pantry: {
      meal_plans: [mealPlan()],
      meal_shopping: withProposal ? [openProposal()] : [],
    },
  };
}

async function setup(t, { withProposal = false } = {}) {
  const state = viewState(withProposal);
  const calls = [];
  const receipts = new Map();
  const lostActions = new Set();
  const card = document.createElement("family-meals-card");
  card.setConfig({
    type: "custom:family-meals-card",
    entry_id: "synthetic",
    language: "en",
  });
  document.body.append(card);
  t.after(() => card.remove());

  const execute = (message) => {
    calls.push(clone(message));
    if (receipts.has(message.operation_id))
      return clone(receipts.get(message.operation_id));

    let result;
    if (message.action === "pantry.meal_shop_prepare") {
      const plan = state.pantry.meal_plans.find(
        (item) =>
          item.id === message.payload.id &&
          item.revision === message.payload.revision &&
          item.status === "published",
      );
      if (!plan) throw { code: "conflict" };
      result = openProposal();
      result.source_plan_id = plan.id;
      result.source_revision = plan.revision;
      result.plan_title = plan.title;
      state.pantry.meal_shopping.push(result);
    } else if (message.action === "pantry.meal_shop_accept") {
      result = state.pantry.meal_shopping.find(
        (item) =>
          item.id === message.payload.id &&
          item.revision === message.payload.revision &&
          item.status === "open",
      );
      if (!result) throw { code: "conflict" };
      result.status = "accepted";
      result.revision += 1;
      result.transfer_count = 1;
      result.lines[0].shopping_id = "SH000001";
    } else if (message.action === "pantry.meal_save") {
      const plan = state.pantry.meal_plans.find(
        (item) =>
          item.id === message.payload.id &&
          item.revision === message.payload.revision,
      );
      if (!plan) throw { code: "conflict" };
      plan.title = message.payload.title;
      plan.revision += 1;
      plan.status = "draft";
      result = plan;
    } else {
      throw { code: "unknown_action" };
    }

    state.revision += 1;
    const receipt = clone(result);
    receipts.set(message.operation_id, receipt);
    if (lostActions.delete(message.action)) throw { code: "storage_error" };
    return clone(receipt);
  };

  card.hass = {
    language: "en",
    callWS: async (message) => {
      if (message.type === "family_assistant/view") return clone(state);
      if (message.type === "family_assistant/execute") return execute(message);
      throw new Error(`unexpected WebSocket type: ${message.type}`);
    },
  };
  await eventually(() => Boolean(card._data) && !card._loading);

  return {
    card,
    state,
    calls,
    lose(action) {
      lostActions.add(action);
    },
  };
}

function button(card, label) {
  const found = [...card.shadowRoot.querySelectorAll("button")].find(
    (candidate) => candidate.textContent === label,
  );
  assert.ok(found, `missing button: ${label}`);
  return found;
}

function reviewForm(card) {
  const form = card.shadowRoot.querySelector("[data-meal-shopping-form]");
  assert.ok(form, "missing meal-shopping review form");
  return form;
}

function submit(form) {
  form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
}

test("real card render is inert and prepare retries its receipt after live status advances", async (t) => {
  const fixture = await setup(t);
  const { card, state, calls } = fixture;
  const serverBefore = clone(state);
  const viewBefore = clone(card._data);
  card.render();
  card.render();
  assert.deepEqual(state, serverBefore);
  assert.deepEqual(card._data, viewBefore);
  assert.equal(calls.length, 0, "rendering must not execute a command");

  fixture.lose("pantry.meal_shop_prepare");
  button(card, MEAL_SHOPPING_COPY.en.calculate).click();
  await eventually(
    () =>
      calls.length === 1 &&
      card._actionError === "storage_error" &&
      Boolean(card._mealShoppingDraft?.pending) &&
      !card._writing,
  );
  const first = calls[0];
  const draft = card._mealShoppingDraft;
  assert.deepEqual(first.payload, { id: "MP000001", revision: 3 });
  assert.ok(Object.isFrozen(draft.pending));
  assert.ok(Object.isFrozen(draft.pending.payload));
  assert.equal(draft.original.title, "Autumn menu");

  state.pantry.meal_shopping[0].status = "superseded";
  state.pantry.meal_shopping[0].revision = 2;
  await card.refresh();
  assert.match(reviewForm(card).textContent, /Autumn menu/);
  submit(reviewForm(card));
  await eventually(
    () => calls.length === 2 && card._mealShoppingDraft === null,
  );
  assert.deepEqual(calls[1].payload, first.payload);
  assert.equal(calls[1].operation_id, first.operation_id);
  assert.equal(state.pantry.meal_shopping[0].status, "superseded");
  assert.equal(state.pantry.meal_shopping[0].revision, 2);
});

test("real checked accept keeps its named snapshot and exact operation across another command", async (t) => {
  const fixture = await setup(t, { withProposal: true });
  const { card, state, calls } = fixture;
  button(card, MEAL_SHOPPING_COPY.en.accept).click();
  let form = reviewForm(card);
  const checkbox = form.elements.reviewed;
  assert.equal(checkbox.type, "checkbox");
  assert.match(form.textContent, /Autumn menu/);
  assert.match(form.textContent, /Rice/);
  assert.ok(Object.isFrozen(card._mealShoppingDraft.original));
  assert.ok(Object.isFrozen(card._mealShoppingDraft.original.lines));

  submit(form);
  await tick();
  assert.equal(calls.length, 0, "unchecked review must be inert");
  checkbox.checked = true;
  checkbox.dispatchEvent(new Event("change", { bubbles: true }));
  fixture.lose("pantry.meal_shop_accept");
  submit(form);
  await eventually(
    () =>
      calls.length === 1 &&
      card._actionError === "storage_error" &&
      Boolean(card._mealShoppingDraft?.pending) &&
      !card._writing,
  );
  const firstAccept = calls[0];
  const pendingId = card._mealShoppingDraft.pending.operation_id;
  assert.equal(firstAccept.operation_id, pendingId);
  assert.deepEqual(firstAccept.payload, { id: "MS000001", revision: 1 });
  assert.equal(state.pantry.meal_shopping[0].status, "accepted");
  assert.equal(state.pantry.meal_shopping[0].transfer_count, 1);

  state.pantry.meal_shopping[0].plan_title = "Changed terminal title";
  await card.refresh();
  form = reviewForm(card);
  assert.match(form.textContent, /Autumn menu/);
  assert.doesNotMatch(form.textContent, /Changed terminal title/);

  await card.command("pantry.meal_save", {
    id: "MP000001",
    revision: 3,
    title: "Later menu edit",
  });
  assert.equal(calls.length, 2);
  assert.equal(calls[1].action, "pantry.meal_save");
  assert.notEqual(calls[1].operation_id, pendingId);
  assert.ok(card._mealShoppingDraft?.pending);
  assert.equal(card._mealShoppingDraft.pending.operation_id, pendingId);
  assert.match(reviewForm(card).textContent, /Autumn menu/);

  submit(reviewForm(card));
  await eventually(
    () => calls.length === 3 && card._mealShoppingDraft === null,
  );
  assert.equal(calls[2].action, "pantry.meal_shop_accept");
  assert.deepEqual(calls[2].payload, firstAccept.payload);
  assert.equal(calls[2].operation_id, firstAccept.operation_id);
  assert.equal(state.pantry.meal_shopping.length, 1);
  assert.equal(state.pantry.meal_shopping[0].revision, 2);
  assert.equal(
    card.shadowRoot.querySelector("[data-meal-shopping-form]"),
    null,
  );
});

test("real focused review rejects a stale source revision before transport", async (t) => {
  const { card, calls } = await setup(t, { withProposal: true });
  button(card, MEAL_SHOPPING_COPY.en.accept).click();
  const form = reviewForm(card);
  form.elements.reviewed.checked = true;
  form.elements.reviewed.dispatchEvent(new Event("change", { bubbles: true }));
  card._data.pantry.meal_plans[0].revision += 1;
  submit(form);
  await tick();
  assert.equal(calls.length, 0);
  assert.equal(card._actionError, "conflict");
  assert.equal(card._mealShoppingDraft, null);
});

test("real actor, role, modules, entry, and generation changes make old forms inert", async (t) => {
  const cases = [
    ["actor", (card) => (card._data.actor = "other-parent")],
    ["role", (card) => (card._data.role = "adult")],
    ["modules", (card) => (card._data.settings.modules = ["pantry"])],
    ["entry", (card) => (card._entry = "other-entry")],
    ["generation", (card) => (card._generation += 1)],
  ];
  for (const [name, change] of cases) {
    const { card, calls } = await setup(t, { withProposal: true });
    button(card, MEAL_SHOPPING_COPY.en.accept).click();
    const form = reviewForm(card);
    form.elements.reviewed.checked = true;
    change(card);
    submit(form);
    await tick();
    assert.equal(calls.length, 0, `${name} change reached transport`);
    assert.equal(card._mealShoppingDraft, null, `${name} retained a draft`);
  }
});

test("real detached form is inert and setConfig clears the current private draft", async (t) => {
  const detached = await setup(t, { withProposal: true });
  button(detached.card, MEAL_SHOPPING_COPY.en.accept).click();
  const oldForm = reviewForm(detached.card);
  const draft = detached.card._mealShoppingDraft;
  detached.card.render();
  assert.equal(oldForm.isConnected, false);
  submit(oldForm);
  await tick();
  assert.equal(detached.calls.length, 0);
  assert.equal(detached.card._mealShoppingDraft, draft);

  const reset = await setup(t, { withProposal: true });
  button(reset.card, MEAL_SHOPPING_COPY.en.accept).click();
  const resetForm = reviewForm(reset.card);
  const generation = reset.card._generation;
  reset.card.setConfig({
    type: "custom:family-meals-card",
    entry_id: "next-entry",
    language: "en",
  });
  assert.equal(reset.card._generation, generation + 1);
  assert.equal(reset.card._mealShoppingDraft, null);
  submit(resetForm);
  await tick();
  assert.equal(reset.calls.length, 0);
});
