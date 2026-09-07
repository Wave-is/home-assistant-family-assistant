import assert from "node:assert/strict";
import { test } from "node:test";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><body></body>", {url: "http://localhost"});
for (const key of ["window", "document", "HTMLElement", "customElements", "CustomEvent", "FormData"]) {
  globalThis[key] = dom.window[key];
}

const {
  SHOPPING_ITEM_COPY,
  openShoppingEditor,
  reconcileShoppingEditorRefresh,
  renderShoppingEditor,
  renderShoppingItem
} = await import("../custom_components/family_assistant/frontend/shopping-items.js");

function member(id, role, revision = 1) {
  return {id, name: `${role} ${id}`, role, revision, active: true};
}

function makeCard({role = "parent", actor = "p1", shopping = [], language = "en", command} = {}) {
  const body = document.createElement("div");
  const calls = [];
  const card = {
    _entry: "entry-1",
    _generation: 4,
    _config: {language},
    _hass: {language},
    _data: {
      role,
      actor,
      settings: {modules: ["shopping"], timezone: "Europe/Kyiv"},
      members: [member("o1", "owner"), member("p1", "parent", 3), member("a1", "adult"), member("c1", "child", 8)],
      shopping
    },
    _shoppingEditorDraft: null,
    _shoppingItemAction: null,
    _shoppingSeriesDraft: null,
    _writing: false,
    _actionError: null,
    get t() { return {units: "items"}; },
    button(text, action, primary = false) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = text;
      button.className = primary ? "primary" : "";
      button.addEventListener("click", action);
      return button;
    },
    async command(action, payload, operationId) {
      calls.push({action, payload, operationId});
      if (command) await command(card, action, payload, operationId);
    },
    render() {
      body.replaceChildren();
      renderShoppingEditor(card, body);
    }
  };
  card.render();
  return {card, body, calls};
}

function input(body, name, value) {
  const control = body.querySelector(`[name='${name}']`);
  assert.ok(control, `missing ${name}`);
  control.value = value;
  control.dispatchEvent(new dom.window.Event("input", {bubbles: true}));
}

function click(body, text) {
  const button = [...body.querySelectorAll("button")].find(node => node.textContent === text);
  assert.ok(button, `missing button ${text}`);
  button.click();
}

test("localized editor copy has exact parity", () => {
  const keys = Object.keys(SHOPPING_ITEM_COPY.en).sort();
  assert.deepEqual(Object.keys(SHOPPING_ITEM_COPY.ru).sort(), keys);
  assert.deepEqual(Object.keys(SHOPPING_ITEM_COPY.uk).sort(), keys);
});

test("reviewed add sends strict metadata and explains child approval and shared note", async () => {
  const {card, body, calls} = makeCard({role: "child", actor: "c1"});
  click(body, SHOPPING_ITEM_COPY.en.editor_add_title);
  input(body, "name", "  Apples  ");
  input(body, "quantity", "1.25");
  input(body, "unit", "kg");
  input(body, "category", "Fruit");
  input(body, "store", "Market");
  input(body, "note", "Household-visible <img src=x>");
  input(body, "buyer", "c1");
  click(body, SHOPPING_ITEM_COPY.en.action_review);
  assert.match(body.textContent, /wait for parent approval/i);
  assert.match(body.textContent, /not private/i);
  assert.equal(body.querySelector("img"), null);
  click(body, SHOPPING_ITEM_COPY.en.action_confirm_add);
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(calls.length, 1);
  assert.equal(calls[0].action, "shopping.add");
  assert.match(calls[0].operationId, /^[0-9a-f-]{36}$/);
  assert.deepEqual(calls[0].payload, {
    name: "Apples", category: "Fruit", store: "Market",
    note: "Household-visible <img src=x>", buyer: "c1", quantity: 1.25, unit: "kg"
  });
});

test("edit preserves quantity provenance and freezes exact retry after a newer projection", async () => {
  const original = {
    id: "S1", revision: 6, status: "approved", creator: "p1", name: "Milk",
    quantity: 4, purchased: 1.5, unit: "l", category: "Dairy", store: "One",
    note: "Visible", buyer: "a1", series_id: "SS1", occurrence_id: "SS1:2026-09-07"
  };
  let attempt = 0;
  const {card, body, calls} = makeCard({shopping: [original], command: async current => {
    attempt += 1;
    current._actionError = attempt === 1 ? "connection_error" : null;
  }});
  assert.equal(openShoppingEditor(card, original), true);
  input(body, "store", "Two");
  input(body, "note", "New visible note");
  click(body, SHOPPING_ITEM_COPY.en.action_review);
  assert.match(body.textContent, /recurring template/i);
  click(body, SHOPPING_ITEM_COPY.en.action_confirm_edit);
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(calls.length, 1);
  const frozen = calls[0];
  assert.deepEqual(frozen.payload, {
    id: "S1", revision: 6, name: "Milk", category: "Dairy", store: "Two",
    note: "New visible note", buyer: "a1"
  });
  assert.equal("quantity" in frozen.payload, false);
  assert.equal("series_id" in frozen.payload, false);
  card._data.shopping = [{...original, revision: 7, purchased: 2}];
  assert.equal(reconcileShoppingEditorRefresh(card), false);
  card.render();
  assert.match(body.textContent, /may already have succeeded/i);
  click(body, SHOPPING_ITEM_COPY.en.action_retry);
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(calls.length, 2);
  assert.strictEqual(calls[1].payload, frozen.payload);
  assert.equal(calls[1].operationId, frozen.operationId);
});

test("role, actor epoch, module, buyer, and item changes revoke editable drafts", () => {
  const item = {id: "S1", revision: 2, status: "approved", creator: "p1", name: "Tea", quantity: 1, unit: "box"};
  for (const mutate of [
    card => { card._data.members.find(row => row.id === "p1").revision += 1; },
    card => { card._data.role = "adult"; },
    card => { card._data.settings.modules = []; },
    card => { card._data.shopping[0] = {...item, revision: 3}; }
  ]) {
    const {card} = makeCard({shopping: [{...item}]});
    assert.equal(openShoppingEditor(card, card._data.shopping[0]), true);
    mutate(card);
    assert.equal(reconcileShoppingEditorRefresh(card), true);
    assert.equal(card._shoppingEditorDraft, null);
  }
  const {card} = makeCard({shopping: [{...item, buyer: "a1"}]});
  openShoppingEditor(card, card._data.shopping[0]);
  card._data.members.find(row => row.id === "a1").active = false;
  assert.equal(reconcileShoppingEditorRefresh(card), true);
});

test("permissions expose edit only for the allowed open record", () => {
  const cases = [
    ["parent", "p1", "pending", "c1", true],
    ["adult", "a1", "approved", "p1", true],
    ["adult", "a1", "pending", "c1", false],
    ["child", "c1", "pending", "c1", true],
    ["child", "c1", "pending", "p1", false],
    ["parent", "p1", "purchased", "p1", false]
  ];
  for (const [role, actor, status, creator, expected] of cases) {
    const item = {id: "S1", revision: 1, status, creator, name: "Bread", quantity: 1, unit: "loaf"};
    const {card} = makeCard({role, actor, shopping: [item]});
    const list = document.createElement("ul");
    const row = renderShoppingItem(card, list, item);
    const visible = [...row.querySelectorAll("button")].some(button => button.textContent === SHOPPING_ITEM_COPY.en.action_edit);
    assert.equal(visible, expected, `${role}/${status}/${creator}`);
  }
});

test("stale merge selection is removed, while a frozen failed merge remains retryable", () => {
  const rows = [
    {id: "S1", revision: 1, status: "approved", creator: "p1", name: "Tea", merge_name: "tea", quantity: 1, purchased: 0, unit: "box"},
    {id: "S2", revision: 2, status: "approved", creator: "p1", name: "Tea", merge_name: "tea", quantity: 2, purchased: 0, unit: "box"}
  ];
  const {card} = makeCard({shopping: rows});
  card._shoppingItemAction = {type: "merge_select", targetSnapshot: {id: "S1", revision: 1}, candidates: [{id: "S2", revision: 2}]};
  card._data.shopping[1] = {...rows[1], revision: 3};
  assert.equal(reconcileShoppingEditorRefresh(card), true);
  assert.equal(card._shoppingItemAction, null);

  card._shoppingItemAction = {
    type: "merge_confirm", targetSnapshot: {id: "S1", revision: 1}, candidates: [{id: "S2", revision: 2}],
    frozenPayload: {id: "S1", revision: 1, sources: [{id: "S2", revision: 2}]}
  };
  card._actionError = "connection_error";
  assert.equal(reconcileShoppingEditorRefresh(card), false);
  assert.ok(card._shoppingItemAction);
});
