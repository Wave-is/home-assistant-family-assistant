import assert from "node:assert/strict";
import { test } from "node:test";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><body></body>", {
  url: "https://example.invalid",
});
for (const key of ["window", "document", "HTMLElement", "Event", "FormData"])
  globalThis[key] = dom.window[key];

const { renderMealShopping } = await import(
  "../custom_components/family_assistant/frontend/meal-shopping-view.js"
);
const { MEAL_SHOPPING_COPY } = await import(
  "../custom_components/family_assistant/frontend/meal-shopping-copy.js"
);

const tick = () => new Promise((resolve) => setTimeout(resolve, 0));
const copy = (value) => structuredClone(value);

const plan = (id, revision, status, title = `Plan ${id}`) => ({
  id,
  revision,
  status,
  title,
  week_start: "2026-09-07",
  entries: [],
});

const proposal = (status = "open") => ({
  id: "MS000001",
  revision: 1,
  status,
  source_plan_id: "MP000001",
  source_revision: 3,
  plan_title: "Autumn menu",
  week_start: "2026-09-07",
  lines: [
    {
      name: "Saffron",
      unit: "kg",
      required: 0.0004,
      stock: 0,
      open_shopping: 0,
      deficit: 0.0004,
      quantity: 0.001,
    },
    {
      name: "Rice",
      unit: "kg",
      required: 2,
      stock: 1,
      open_shopping: 1,
      deficit: 0,
      quantity: 0,
    },
  ],
});

class FaithfulCard {
  constructor(data) {
    this._data = data;
    this._config = { language: "en" };
    this._entry = "synthetic";
    this._generation = 1;
    this._writing = false;
    this._pending = null;
    this._actionError = null;
    this._mealShoppingDraft = null;
    this._mealsDraft = null;
    this.calls = [];
    this.receipts = new Map();
    this.loseNext = false;
    this.root = document.createElement("div");
    document.body.append(this.root);
    this.render();
  }

  get parent() {
    return ["owner", "parent"].includes(this._data?.role);
  }

  button(label, action, primary = false) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = label;
    if (primary) button.className = "primary";
    button.disabled = this._writing;
    button.addEventListener("click", action);
    return button;
  }

  render() {
    const body = document.createElement("div");
    body.className = "body";
    for (const item of this._data?.pantry?.meal_plans || []) {
      const row = document.createElement("section");
      row.dataset.mealPlan = item.id;
      row.append(document.createElement("div"));
      body.append(row);
    }
    this.root.replaceChildren(body);
    renderMealShopping(this, body);
  }

  async refresh() {}

  async command(action, payload, operationId) {
    if (this._writing) return;
    const generation = this._generation;
    const fingerprint = JSON.stringify([this._entry, action, payload]);
    if (this._pending?.fingerprint !== fingerprint)
      this._pending = { fingerprint, id: operationId || crypto.randomUUID() };
    const id = operationId || this._pending.id;
    this._writing = true;
    for (const button of this.root.querySelectorAll("button"))
      button.disabled = true;
    try {
      const result = await this.transport(action, payload, id);
      if (generation === this._generation) {
        this._pending = null;
        this._actionError = result?.accepted === false ? "wrong_answer" : null;
      }
    } catch (error) {
      if (generation === this._generation)
        this._actionError = error.code || "failure";
    } finally {
      this._writing = false;
      await this.refresh();
      this.render();
    }
  }

  async transport(action, payload, operationId) {
    this.calls.push({ action, payload: copy(payload), operationId });
    if (this.receipts.has(operationId))
      return copy(this.receipts.get(operationId));
    let result;
    if (action === "pantry.meal_shop_prepare") {
      const source = this._data.pantry.meal_plans.find(
        (item) =>
          item.id === payload.id &&
          item.revision === payload.revision &&
          item.status === "published",
      );
      if (!source) throw { code: "conflict" };
      result = proposal();
      result.source_plan_id = source.id;
      result.source_revision = source.revision;
      result.plan_title = source.title;
      this._data.pantry.meal_shopping.push(result);
    } else if (action === "pantry.meal_shop_accept") {
      result = this._data.pantry.meal_shopping.find(
        (item) =>
          item.id === payload.id &&
          item.revision === payload.revision &&
          item.status === "open",
      );
      if (!result) throw { code: "conflict" };
      result.status = "accepted";
      result.revision += 1;
      result.lines[0].shopping_id = "SH000001";
      result.transfer_count = 1;
    } else {
      result = { accepted: true };
    }
    this.receipts.set(operationId, copy(result));
    if (this.loseNext) {
      this.loseNext = false;
      throw { code: "storage_error" };
    }
    return copy(result);
  }

  remove() {
    this.root.remove();
  }
}

function data({ proposals = [], modules = ["pantry", "shopping"] } = {}) {
  return {
    revision: 1,
    actor: "parent",
    role: "parent",
    settings: { modules },
    pantry: {
      meal_plans: [
        plan("MP000001", 3, "published", "Autumn menu"),
        plan("MP000002", 1, "draft"),
        plan("MP000003", 2, "archived"),
      ],
      meal_shopping: proposals,
    },
  };
}

function button(card, label) {
  const result = [...card.root.querySelectorAll("button")].find(
    (candidate) => candidate.textContent === label,
  );
  assert.ok(result, `missing button: ${label}`);
  return result;
}

function submit(card) {
  const form = card.root.querySelector("form");
  assert.ok(form, "missing review form");
  form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
}

test("copy keys match and review shows exact totals, rounded add amount, and zero lines", (t) => {
  const card = new FaithfulCard(data({ proposals: [proposal()] }));
  t.after(() => card.remove());
  for (const language of Object.values(MEAL_SHOPPING_COPY))
    assert.deepEqual(
      Object.keys(language).sort(),
      Object.keys(MEAL_SHOPPING_COPY.en).sort(),
    );
  assert.equal(
    card.calls.length,
    0,
    "rendering must never prepare automatically",
  );
  const row = card.root.querySelector(
    '[data-meal-shopping-proposal="MS000001"]',
  );
  assert.ok(row);
  assert.match(row.textContent, /Saffron/);
  assert.match(row.textContent, /Uncovered amount0.0004 kg/);
  assert.match(row.textContent, /Amount to add0.001 kg/);
  assert.match(row.textContent, /Rice/);
  assert.match(row.textContent, /Amount to add0 kg/);
  assert.match(row.textContent, /rounded up to 0.001/);
  assert.equal(
    card.root.querySelectorAll("[data-meal-plan] button").length,
    1,
    "only the published plan is eligible",
  );
});

test("calculate is explicit and committed response loss retries frozen payload and operation id", async (t) => {
  const card = new FaithfulCard(data());
  t.after(() => card.remove());
  assert.equal(card.calls.length, 0);
  card.loseNext = true;
  button(card, MEAL_SHOPPING_COPY.en.calculate).click();
  await tick();
  await tick();
  assert.equal(card.calls.length, 1);
  assert.deepEqual(card.calls[0].payload, { id: "MP000001", revision: 3 });
  const draft = card._mealShoppingDraft;
  assert.ok(draft?.pending);
  assert.ok(Object.isFrozen(draft.pending));
  assert.ok(Object.isFrozen(draft.pending.payload));
  assert.match(card.root.querySelector("form").textContent, /Autumn menu/);

  // Simulate a different card section replacing FamilyCard's current fingerprint.
  card._pending = { fingerprint: "unrelated", id: "unrelated-operation" };
  submit(card);
  await tick();
  await tick();
  assert.equal(card.calls.length, 2);
  assert.deepEqual(card.calls[1], card.calls[0]);
  assert.equal(card._data.pantry.meal_shopping.length, 1);
  assert.equal(card._mealShoppingDraft, null);
});

test("accept requires a real checkbox and keeps the named frozen review for exact retry", async (t) => {
  const card = new FaithfulCard(data({ proposals: [proposal()] }));
  t.after(() => card.remove());
  button(card, MEAL_SHOPPING_COPY.en.accept).click();
  const form = card.root.querySelector("form");
  const checkbox = form.elements.reviewed;
  assert.equal(checkbox.type, "checkbox");
  assert.match(form.textContent, /Autumn menu/);
  assert.match(form.textContent, /Saffron/);
  submit(card);
  await tick();
  assert.equal(card.calls.length, 0);

  checkbox.checked = true;
  checkbox.dispatchEvent(new Event("change", { bubbles: true }));
  card.loseNext = true;
  submit(card);
  await tick();
  await tick();
  assert.equal(card.calls.length, 1);
  assert.deepEqual(card.calls[0].payload, { id: "MS000001", revision: 1 });
  const frozen = card._mealShoppingDraft;
  assert.ok(frozen?.pending);
  assert.match(card.root.querySelector("form").textContent, /Autumn menu/);
  assert.match(card.root.textContent, /SH000001/);
  assert.match(card.root.textContent, /edit the shopping list manually/i);
  assert.equal(
    card.root.querySelector('[data-meal-plan="MP000001"] button'),
    null,
    "a terminal transfer permanently hides calculate for the plan ID",
  );

  submit(card);
  await tick();
  await tick();
  assert.deepEqual(card.calls[1], card.calls[0]);
  assert.equal(card._mealShoppingDraft, null);
  assert.equal(card._data.pantry.meal_shopping[0].revision, 2);
});

test("stale source or proposal, detached controls, and changed identity cannot submit", async (t) => {
  const card = new FaithfulCard(data({ proposals: [proposal()] }));
  t.after(() => card.remove());
  const detachedAccept = button(card, MEAL_SHOPPING_COPY.en.accept);
  card.render();
  detachedAccept.click();
  assert.equal(card._mealShoppingDraft, null);

  button(card, MEAL_SHOPPING_COPY.en.accept).click();
  const form = card.root.querySelector("form");
  form.elements.reviewed.checked = true;
  form.elements.reviewed.dispatchEvent(new Event("change", { bubbles: true }));
  card._data.pantry.meal_plans[0].revision += 1;
  submit(card);
  await tick();
  assert.equal(card.calls.length, 0);
  assert.equal(card._actionError, "conflict");
  assert.equal(card._mealShoppingDraft, null);

  card._data.pantry.meal_plans[0].revision -= 1;
  card.render();
  button(card, MEAL_SHOPPING_COPY.en.accept).click();
  const revokedForm = card.root.querySelector("form");
  revokedForm.elements.reviewed.checked = true;
  card._data.pantry.meal_shopping[0].revision += 1;
  revokedForm.dispatchEvent(
    new Event("submit", { bubbles: true, cancelable: true }),
  );
  assert.equal(card.calls.length, 0);
  assert.equal(card._mealShoppingDraft, null);

  card._data.pantry.meal_shopping[0].revision -= 1;
  card.render();
  button(card, MEAL_SHOPPING_COPY.en.accept).click();
  const identityForm = card.root.querySelector("form");
  identityForm.elements.reviewed.checked = true;
  card._data.actor = "other-parent";
  identityForm.dispatchEvent(
    new Event("submit", { bubbles: true, cancelable: true }),
  );
  assert.equal(card.calls.length, 0);
  assert.equal(card._mealShoppingDraft, null);
  assert.equal(card.root.querySelector("form"), null);
});

test("disabled or revoked access clears private state; meals editor only hides it", (t) => {
  const card = new FaithfulCard(data({ modules: ["pantry"] }));
  t.after(() => card.remove());
  card._mealShoppingDraft = { private: true };
  card.render();
  assert.equal(card._mealShoppingDraft, null);
  assert.match(card.root.textContent, /Enable both Pantry/);

  card._data.settings.modules = ["pantry", "shopping"];
  card._data.role = "adult";
  card._mealShoppingDraft = { private: true };
  card.render();
  assert.equal(card._mealShoppingDraft, null);
  assert.equal(card.root.querySelector(".meal-shopping-section"), null);

  card._data.role = "parent";
  card._mealShoppingDraft = {
    type: "prepare",
    scope: JSON.stringify([
      card._generation,
      card._entry,
      card._data.actor,
      card._data.role,
    ]),
    pending: Object.freeze({}),
  };
  const pending = card._mealShoppingDraft;
  card._mealsDraft = { type: "edit" };
  card.render();
  assert.equal(card.root.querySelector(".meal-shopping-section"), null);
  assert.equal(card._mealShoppingDraft, pending);
});

test("empty enabled state is private, inert, and explains both empty collections", (t) => {
  const value = data();
  value.pantry.meal_plans = [];
  const card = new FaithfulCard(value);
  t.after(() => card.remove());
  assert.equal(card.calls.length, 0);
  assert.match(card.root.textContent, /Publish a meal plan/);
  assert.match(card.root.textContent, /No meal shopping proposals/);
  assert.equal(card.root.querySelector("form"), null);
});
