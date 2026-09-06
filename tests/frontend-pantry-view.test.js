import assert from "node:assert/strict";
import { test } from "node:test";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><body><div id='root'></div></body>", {
  url: "http://localhost",
});
for (const key of ["window", "document", "HTMLElement", "Event", "FormData"]) {
  globalThis[key] = dom.window[key];
}

const { PANTRY_COPY } = await import(
  "../custom_components/family_assistant/frontend/pantry-copy.js"
);
const { renderPantry } = await import(
  "../custom_components/family_assistant/frontend/pantry-view.js"
);

const item = {
  id: "item-1",
  revision: 4,
  name: "Milk",
  unit: "l",
  quantity: 1,
  minimum_quantity: 3,
  category: "Food",
  location: "Fridge",
  note: "Parent-only note",
  expires_on: "2026-09-10",
  status: "active",
  low_stock: true,
  expiry_status: "expiring",
  expires_in_days: 4,
};

const archivedItem = {
  ...item,
  id: "item-old",
  revision: 8,
  name: "Old flour",
  status: "archived",
  low_stock: false,
};

const suggestions = [
  {
    id: "suggestion-open",
    revision: 2,
    pantry_id: item.id,
    source_revision: item.revision,
    quantity: 2,
    unit: "l",
    status: "open",
  },
  {
    id: "suggestion-accepted",
    revision: 3,
    pantry_id: item.id,
    source_revision: item.revision,
    quantity: 2,
    unit: "l",
    status: "accepted",
    shopping_id: "shopping-1",
  },
  {
    id: "suggestion-covered",
    revision: 3,
    pantry_id: item.id,
    source_revision: item.revision,
    quantity: 2,
    unit: "l",
    status: "covered",
    shopping_id: "shopping-2",
  },
];

function createCard({ role = "parent", language = "en", outcomes = [] } = {}) {
  let operation = 0;
  return {
    _generation: 1,
    _entry: "entry-1",
    _config: { language },
    _hass: { language },
    _data: {
      actor: "member-1",
      role,
      settings: { modules: ["pantry", "shopping"], timezone: "Europe/Kyiv" },
      pantry: {
        items: [{ ...item }],
        archived: [{ ...archivedItem }],
        suggestions: suggestions.map((value) => ({ ...value })),
      },
    },
    parent: ["owner", "parent"].includes(role),
    _writing: false,
    _pending: null,
    _actionError: null,
    _pantryDraft: null,
    calls: [],
    renders: 0,
    button(text, action, primary = false) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = text;
      if (primary) button.className = "primary";
      button.addEventListener("click", action);
      return button;
    },
    render() {
      this.renders += 1;
    },
    async command(action, payload) {
      if (this._writing) return;
      const fingerprint = JSON.stringify([this._entry, action, payload]);
      if (this._pending?.fingerprint !== fingerprint) {
        this._pending = { fingerprint, id: `operation-${++operation}` };
      }
      this._writing = true;
      this.calls.push({ action, payload, operationId: this._pending.id });
      const outcome = outcomes.shift();
      if (outcome instanceof Promise) await outcome;
      if (outcome === "fail") {
        this._actionError = "transport";
      } else {
        this._pending = null;
        this._actionError = null;
      }
      this._writing = false;
    },
  };
}

function render(card) {
  const root = document.getElementById("root");
  const body = document.createElement("div");
  root.replaceChildren(body);
  renderPantry(card, body);
  return body;
}

function button(body, text) {
  const found = [...body.querySelectorAll("button")].find(
    (node) => node.textContent === text,
  );
  assert.ok(found, `missing button: ${text}`);
  return found;
}

function field(body, name) {
  const found = body.querySelector(`[data-pantry-field="${name}"]`);
  assert.ok(found, `missing pantry field: ${name}`);
  return found;
}

function setField(body, name, value) {
  field(body, name).value = value;
}

function inputField(body, name, value) {
  const control = field(body, name);
  control.value = value;
  control.dispatchEvent(new dom.window.Event("input", { bubbles: true }));
}

function submit(body) {
  const form = body.querySelector("form[data-pantry-form]");
  assert.ok(form, "missing pantry form");
  form.dispatchEvent(
    new dom.window.Event("submit", { bubbles: true, cancelable: true }),
  );
  return form;
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

test("PANTRY_COPY has exact non-empty EN, RU, and UK parity", () => {
  const keys = Object.keys(PANTRY_COPY.en).sort();
  for (const language of ["en", "ru", "uk"]) {
    assert.deepEqual(Object.keys(PANTRY_COPY[language]).sort(), keys);
    for (const key of keys)
      assert.ok(PANTRY_COPY[language][key], `${language}.${key}`);
  }
});

test("guest sees nothing, child is read-only, adult only corrects stock, parent manages", () => {
  const guest = createCard({ role: "guest" });
  guest._pantryDraft = { type: "new" };
  assert.equal(render(guest).children.length, 0);
  assert.equal(guest._pantryDraft, null);

  const child = createCard({ role: "child" });
  const childBody = render(child);
  assert.ok(childBody.textContent.includes("Milk"));
  assert.equal(childBody.textContent.includes(item.note), false);
  assert.equal(childBody.querySelectorAll("button").length, 0);
  assert.equal(
    childBody.querySelectorAll("[data-pantry-suggestion]").length,
    0,
  );

  const adult = createCard({ role: "adult" });
  const adultBody = render(adult);
  assert.ok(adultBody.textContent.includes(PANTRY_COPY.en.stock_set));
  assert.equal(adultBody.textContent.includes(PANTRY_COPY.en.edit), false);
  assert.equal(adultBody.textContent.includes(PANTRY_COPY.en.archive), false);
  assert.equal(adultBody.textContent.includes(item.note), false);

  const parent = createCard();
  const parentBody = render(parent);
  for (const label of [
    "new_item",
    "stock_set",
    "edit",
    "archive",
    "accept",
    "dismiss",
  ]) {
    assert.ok(parentBody.textContent.includes(PANTRY_COPY.en[label]), label);
  }
  assert.ok(parentBody.textContent.includes(item.note));
  assert.ok(parentBody.querySelector("[data-pantry-archived='item-old']"));

  child._pantryDraft = {
    type: "new",
    scope: JSON.stringify([
      child._generation,
      child._entry,
      "child",
      child._data.actor,
    ]),
  };
  assert.equal(render(child).querySelector("form"), null);
  assert.equal(
    child._pantryDraft,
    null,
    "a forged parent draft must be discarded",
  );
});

test("disabled module is explained and actual RU copy is rendered", () => {
  const disabled = createCard();
  disabled._data.settings.modules = ["shopping"];
  assert.ok(render(disabled).textContent.includes(PANTRY_COPY.en.module_off));

  const russian = createCard({ language: "ru" });
  const body = render(russian);
  for (const key of [
    "new_item",
    "quantity",
    "minimum_quantity",
    "expires_on",
    "note",
    "low_stock",
  ]) {
    assert.ok(
      body.textContent.includes(PANTRY_COPY.ru[key]),
      `missing rendered RU ${key}`,
    );
  }
  assert.equal(
    body.textContent.includes(PANTRY_COPY.en.minimum_quantity),
    false,
  );
  button(body, PANTRY_COPY.ru.new_item).click();
  const formBody = render(russian);
  for (const key of [
    "name",
    "unit",
    "quantity",
    "minimum_quantity",
    "category",
    "location",
    "note",
    "expires_on",
  ]) {
    assert.ok(
      formBody.textContent.includes(PANTRY_COPY.ru[key]),
      `missing RU form ${key}`,
    );
  }
});

test("inventory renders factual stock, one expiry status, and low-stock label", () => {
  const body = render(createCard());
  const row = body.querySelector("[data-pantry-item='item-1']");
  assert.ok(row.textContent.includes("1 l"));
  assert.ok(row.textContent.includes("3 l"));
  assert.ok(row.textContent.includes("2026-09-10"));
  assert.ok(row.textContent.includes(PANTRY_COPY.en.expiry_expiring));
  assert.ok(row.textContent.includes(PANTRY_COPY.en.low_stock));
  assert.equal(row.textContent.toLowerCase().includes("medicine"), false);
  assert.equal(row.textContent.toLowerCase().includes("dose"), false);
});

test("editor is above inventory and long safety help is collapsed", () => {
  const card = createCard();
  let body = render(card);
  button(body, PANTRY_COPY.en.edit).click();
  body = render(card);

  const form = body.querySelector("form[data-pantry-form='edit']");
  const list = body.querySelector(".pantry-list");
  assert.ok(
    form.compareDocumentPosition(list) &
      dom.window.Node.DOCUMENT_POSITION_FOLLOWING,
    "the form must precede inventory on mobile",
  );
  const help = body.querySelector("details.pantry-help");
  assert.equal(help.open, false);
  assert.equal(
    help.querySelector("summary").textContent,
    PANTRY_COPY.en.inventory_hint,
  );
  assert.ok(help.textContent.includes(PANTRY_COPY.en.stock_hint));
  assert.ok(help.textContent.includes(PANTRY_COPY.en.expiry_hint));
  assert.ok(help.textContent.includes(PANTRY_COPY.en.private_note_hint));
  assert.ok(
    body.querySelector("[data-pantry-item]").compareDocumentPosition(help) &
      dom.window.Node.DOCUMENT_POSITION_FOLLOWING,
    "actual stock must appear before help",
  );
});

test("new item uses strict quantities and calendar dates before an exact save", async () => {
  const card = createCard();
  let body = render(card);
  button(body, PANTRY_COPY.en.new_item).click();
  body = render(card);

  setField(body, "name", "Rice");
  setField(body, "unit", "kg");
  setField(body, "quantity", "1e2");
  setField(body, "minimum_quantity", "2");
  setField(body, "expires_on", "2026-09-30");
  submit(body);
  await settle();
  assert.equal(card.calls.length, 0, "exponents must be rejected");

  for (const invalid of ["1/2", "-1", "1.2345", "1000000.001"]) {
    setField(body, "quantity", invalid);
    submit(body);
    await settle();
    assert.equal(
      card.calls.length,
      0,
      `invalid quantity must be rejected: ${invalid}`,
    );
  }

  setField(body, "quantity", "1.25");
  field(body, "expires_on").type = "text";
  setField(body, "expires_on", "2026-02-30");
  submit(body);
  await settle();
  assert.equal(
    card.calls.length,
    0,
    "nonexistent calendar dates must be rejected",
  );

  setField(body, "category", "Dry goods");
  setField(body, "location", "Shelf");
  setField(body, "note", "Parents only");
  setField(body, "expires_on", "2026-10-01");
  submit(body);
  await settle();
  assert.deepEqual(card.calls[0], {
    action: "pantry.item_save",
    operationId: "operation-1",
    payload: {
      name: "Rice",
      unit: "kg",
      quantity: 1.25,
      minimum_quantity: 2,
      category: "Dry goods",
      location: "Shelf",
      note: "Parents only",
      expires_on: "2026-10-01",
    },
  });
});

test("strict expiry validation accepts Gregorian years below 100", async () => {
  const card = createCard();
  let body = render(card);
  button(body, PANTRY_COPY.en.new_item).click();
  body = render(card);
  setField(body, "name", "Archive sample");
  setField(body, "unit", "piece");
  setField(body, "quantity", "0");
  setField(body, "minimum_quantity", "0");
  setField(body, "expires_on", "0001-01-01");
  submit(body);
  await settle();

  assert.equal(card.calls.length, 1);
  assert.equal(card.calls[0].payload.expires_on, "0001-01-01");
});

test("typed values survive refresh and local validation rerenders", async () => {
  const card = createCard();
  let body = render(card);
  button(body, PANTRY_COPY.en.new_item).click();
  body = render(card);
  inputField(body, "name", "Typed before refresh");
  inputField(body, "unit", "box");
  inputField(body, "quantity", "1.2345");

  body = render(card);
  assert.equal(field(body, "name").value, "Typed before refresh");
  assert.equal(field(body, "unit").value, "box");
  assert.equal(field(body, "quantity").value, "1.2345");

  submit(body);
  await settle();
  assert.equal(card.calls.length, 0);
  body = render(card);
  assert.equal(field(body, "name").value, "Typed before refresh");
  assert.equal(field(body, "quantity").value, "1.2345");
});

test("metadata edit is partial, explicitly clears expiry, and preserves omitted values", async () => {
  const card = createCard();
  let body = render(card);
  button(body, PANTRY_COPY.en.edit).click();
  body = render(card);
  setField(body, "location", "Door shelf");
  setField(body, "expires_on", "");
  submit(body);
  await settle();

  assert.deepEqual(card.calls[0].payload, {
    id: item.id,
    revision: item.revision,
    location: "Door shelf",
    expires_on: null,
  });
  for (const omitted of [
    "name",
    "unit",
    "quantity",
    "minimum_quantity",
    "category",
    "note",
  ]) {
    assert.equal(omitted in card.calls[0].payload, false, omitted);
  }
});

test("quantity or unit edits require a reason", async () => {
  const card = createCard();
  let body = render(card);
  button(body, PANTRY_COPY.en.edit).click();
  body = render(card);
  setField(body, "quantity", "2");
  submit(body);
  await settle();
  assert.equal(card.calls.length, 0);

  setField(body, "reason", "Counted carton");
  submit(body);
  await settle();
  assert.deepEqual(card.calls[0].payload, {
    id: item.id,
    revision: item.revision,
    quantity: 2,
    reason: "Counted carton",
  });
});

test("adult stock correction sends only current revision, quantity, and reason", async () => {
  const card = createCard({ role: "adult" });
  let body = render(card);
  button(body, PANTRY_COPY.en.stock_set).click();
  body = render(card);
  setField(body, "quantity", "0.125");
  setField(body, "reason", "Weighed package");
  submit(body);
  await settle();

  assert.deepEqual(card.calls[0].payload, {
    id: item.id,
    revision: item.revision,
    quantity: 0.125,
    reason: "Weighed package",
  });
  assert.equal(card.calls[0].action, "pantry.stock_set");
});

test("archive and suggestion decisions require explicit confirmation", async () => {
  const archiveCard = createCard();
  let body = render(archiveCard);
  button(body, PANTRY_COPY.en.archive).click();
  assert.equal(archiveCard.calls.length, 0);
  body = render(archiveCard);
  setField(body, "reason", "No longer tracked");
  submit(body);
  await settle();
  assert.deepEqual(archiveCard.calls[0].payload, {
    id: item.id,
    revision: item.revision,
    reason: "No longer tracked",
  });

  const acceptCard = createCard();
  body = render(acceptCard);
  button(body, PANTRY_COPY.en.accept).click();
  assert.equal(acceptCard.calls.length, 0);
  body = render(acceptCard);
  assert.equal(body.querySelector("form h3").textContent, "Milk");
  assert.ok(body.querySelector("form").textContent.includes("2 l"));
  submit(body);
  await settle();
  assert.equal(acceptCard.calls[0].action, "pantry.suggestion_accept");
  assert.deepEqual(acceptCard.calls[0].payload, {
    id: "suggestion-open",
    revision: 2,
  });

  const dismissCard = createCard();
  body = render(dismissCard);
  button(body, PANTRY_COPY.en.dismiss).click();
  body = render(dismissCard);
  submit(body);
  await settle();
  assert.equal(dismissCard.calls.length, 0, "dismissal requires a reason");
  setField(body, "reason", "Already have enough");
  submit(body);
  await settle();
  assert.equal(dismissCard.calls[0].action, "pantry.suggestion_dismiss");
});

test("suggestions identify source and quantity and never claim an order", () => {
  const body = render(createCard());
  for (const id of [
    "suggestion-open",
    "suggestion-accepted",
    "suggestion-covered",
  ]) {
    const row = body.querySelector(`[data-pantry-suggestion="${id}"]`);
    assert.ok(row.textContent.includes("Milk"));
    assert.ok(row.textContent.includes("2 l"));
  }
  assert.ok(body.textContent.includes(PANTRY_COPY.en.status_accepted));
  assert.ok(body.textContent.includes(PANTRY_COPY.en.status_covered));
  assert.ok(body.textContent.includes(PANTRY_COPY.en.suggestion_hint));
  assert.equal(body.textContent.toLowerCase().includes("order placed"), false);
});

test("stale identity, revision, detached forms, and old buttons are inert", async () => {
  const staleButtonCard = createCard();
  let body = render(staleButtonCard);
  const oldButton = button(body, PANTRY_COPY.en.edit);
  staleButtonCard._generation += 1;
  oldButton.click();
  assert.equal(staleButtonCard._pantryDraft, null);

  const staleRevisionCard = createCard();
  body = render(staleRevisionCard);
  const staleRevisionButton = button(body, PANTRY_COPY.en.edit);
  staleRevisionCard._data.pantry.items[0].revision += 1;
  staleRevisionButton.click();
  assert.equal(staleRevisionCard._pantryDraft, null);
  assert.equal(staleRevisionCard._actionError, "conflict");

  const staleFormCard = createCard();
  body = render(staleFormCard);
  button(body, PANTRY_COPY.en.stock_set).click();
  body = render(staleFormCard);
  setField(body, "reason", "Current projection changed");
  staleFormCard._data.pantry.items[0].revision += 1;
  submit(body);
  await settle();
  assert.equal(staleFormCard.calls.length, 0);

  const detachedCard = createCard();
  body = render(detachedCard);
  button(body, PANTRY_COPY.en.new_item).click();
  body = render(detachedCard);
  const form = body.querySelector("form");
  body.remove();
  form.dispatchEvent(new dom.window.Event("submit", { cancelable: true }));
  await settle();
  assert.equal(detachedCard.calls.length, 0);
});

test("failed transport retains one frozen payload and operation for exact retry", async () => {
  const card = createCard({ outcomes: ["fail", "ok"] });
  let body = render(card);
  button(body, PANTRY_COPY.en.stock_set).click();
  body = render(card);
  setField(body, "quantity", "2.5");
  setField(body, "reason", "Counted once");
  submit(body);
  await settle();

  assert.equal(card.calls.length, 1);
  assert.ok(card._pantryDraft);
  assert.ok(Object.isFrozen(card._pantryDraft.pending.payload));
  const firstPayload = card.calls[0].payload;
  const firstOperation = card.calls[0].operationId;

  // Simulate a committed write whose response was lost: refresh sees the new revision.
  card._data.pantry.items[0] = {
    ...card._data.pantry.items[0],
    revision: item.revision + 1,
    quantity: 2.5,
  };

  body = render(card);
  assert.ok(button(body, PANTRY_COPY.en.retry));
  for (const control of body.querySelectorAll("form input"))
    assert.equal(control.disabled, true);
  setField(body, "quantity", "999");
  setField(body, "reason", "Changed after failure");
  submit(body);
  await settle();

  assert.equal(card.calls.length, 2);
  assert.equal(card.calls[1].payload, firstPayload);
  assert.equal(card.calls[1].operationId, firstOperation);
  assert.equal(card._pantryDraft, null);
});

test("lost suggestion-accept response retries its exact receipt after status refresh", async () => {
  const card = createCard({ outcomes: ["fail", "ok"] });
  let body = render(card);
  button(body, PANTRY_COPY.en.accept).click();
  body = render(card);
  submit(body);
  await settle();
  const first = card.calls[0];
  assert.ok(card._pantryDraft?.pending);

  card._data.pantry.suggestions = card._data.pantry.suggestions.map((value) =>
    value.id === "suggestion-open"
      ? {
          ...value,
          revision: value.revision + 1,
          status: "accepted",
          shopping_id: "shopping-9",
        }
      : value,
  );
  body = render(card);
  assert.ok(body.querySelector("form[data-pantry-form='suggestion_accept']"));
  assert.ok(button(body, PANTRY_COPY.en.retry));
  submit(body);
  await settle();

  assert.equal(card.calls.length, 2);
  assert.equal(card.calls[1].payload, first.payload);
  assert.equal(card.calls[1].operationId, first.operationId);
  assert.deepEqual(card.calls[1].payload, {
    id: "suggestion-open",
    revision: 2,
  });
  assert.equal(card._pantryDraft, null);
});

test("permission revocation discards a frozen retry", async () => {
  const card = createCard({ outcomes: ["fail"] });
  let body = render(card);
  button(body, PANTRY_COPY.en.accept).click();
  body = render(card);
  submit(body);
  await settle();
  assert.ok(card._pantryDraft?.pending);

  card._data.role = "adult";
  card.parent = false;
  body = render(card);
  assert.equal(card._pantryDraft, null);
  assert.equal(body.querySelector("form"), null);
  assert.equal(card.calls.length, 1);
});

test("writing guard prevents duplicate submit while one command is pending", async () => {
  let release;
  const pending = new Promise((resolve) => {
    release = resolve;
  });
  const card = createCard({ outcomes: [pending] });
  let body = render(card);
  button(body, PANTRY_COPY.en.stock_set).click();
  body = render(card);
  setField(body, "quantity", "2");
  setField(body, "reason", "One count");
  submit(body);
  submit(body);
  assert.equal(card.calls.length, 1);
  release();
  await settle();
});

test("pantry and suggestion text never becomes HTML", () => {
  const attack =
    '<img src=x onerror="globalThis.pwned=true"><script>bad()</script>';
  const card = createCard();
  card._data.pantry.items[0].name = attack;
  card._data.pantry.items[0].note = attack;
  const body = render(card);

  assert.equal(body.querySelectorAll("img,script").length, 0);
  assert.ok(body.textContent.includes(attack));
  assert.equal(globalThis.pwned, undefined);
});
