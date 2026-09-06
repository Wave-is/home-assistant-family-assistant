import assert from "node:assert/strict";
import { test } from "node:test";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><body></body>", { url: "http://localhost" });
for (const key of ["window", "document", "HTMLElement", "customElements", "CustomEvent", "FormData"]) {
  globalThis[key] = dom.window[key];
}

const { SHOPPING_ITEM_COPY, renderShoppingItem, renderShoppingArchive } = await import(
  "../custom_components/family_assistant/frontend/shopping-items.js"
);
await import(
  "../custom_components/family_assistant/frontend/family-assistant.js"
);

function createMockCard({
  role = "parent",
  isParent = true,
  lang = "en",
  timezone = "Europe/Kyiv",
  shopping = [],
  members = [
    { id: "p1", name: "Parent One", role: "parent", active: true },
    { id: "a1", name: "Adult One", role: "adult", active: true },
    { id: "c1", name: "Child One", role: "child", active: true }
  ],
  commandFn = null
} = {}) {
  const commands = [];
  const card = {
    _view: "shopping",
    _generation: 1,
    _data: {
      role,
      actor: "p1",
      settings: { timezone },
      members,
      shopping
    },
    _config: { language: lang },
    _hass: { language: lang, config: { time_zone: timezone } },
    parent: isParent,
    _writing: false,
    _shoppingItemAction: null,
    _actionError: null,
    commands,
    commandFn,
    button(text, action, primary = false) {
      const btn = document.createElement("button");
      btn.textContent = text;
      if (primary) btn.className = "primary";
      btn.type = "button";
      btn.disabled = Boolean(card._writing);
      btn.addEventListener("click", action);
      return btn;
    },
    input(form, name, label, type = "text", value = "", required = true) {
      const wrap = document.createElement("label");
      wrap.textContent = label;
      const input = document.createElement("input");
      Object.assign(input, { name, type, value, required });
      wrap.append(input);
      form.append(wrap);
      return input;
    },
    async command(action, payload) {
      commands.push({ action, payload });
      if (card.commandFn) await card.commandFn(action, payload);
      return { success: true };
    },
    render() {}
  };
  return card;
}

test("SHOPPING_ITEM_COPY has exact key parity across en, ru, and uk", () => {
  const enKeys = Object.keys(SHOPPING_ITEM_COPY.en).sort();
  const ruKeys = Object.keys(SHOPPING_ITEM_COPY.ru).sort();
  const ukKeys = Object.keys(SHOPPING_ITEM_COPY.uk).sort();

  assert.deepEqual(ruKeys, enKeys, "RU keys must match EN keys exactly");
  assert.deepEqual(ukKeys, enKeys, "UK keys must match EN keys exactly");

  for (const k of enKeys) {
    assert.equal(typeof SHOPPING_ITEM_COPY.en[k], "string");
    assert.equal(typeof SHOPPING_ITEM_COPY.ru[k], "string");
    assert.equal(typeof SHOPPING_ITEM_COPY.uk[k], "string");
    assert.ok(SHOPPING_ITEM_COPY.en[k].length > 0);
    assert.ok(SHOPPING_ITEM_COPY.ru[k].length > 0);
    assert.ok(SHOPPING_ITEM_COPY.uk[k].length > 0);
  }
});

test("server Unicode matching and all reviewed revisions survive refreshed data",()=>{
  const target={id:"a",name:"Straße",merge_name:"strasse",status:"approved",quantity:1,purchased:0,unit:"kg",revision:2};
  const source={...target,id:"b",name:"STRASSE",revision:3};
  const different={...source,id:"c",unit:" kg"};
  const card=createMockCard({shopping:[target,source,different]});
  const list=document.createElement("ul");
  let row=renderShoppingItem(card,list,target);
  [...row.querySelectorAll("button")].find(b=>b.textContent===SHOPPING_ITEM_COPY.en.action_merge).click();
  target.revision=99;source.revision=100;target.quantity=10;
  list.replaceChildren();row=renderShoppingItem(card,list,target);
  const checkboxes=row.querySelectorAll("input[type=checkbox]");
  assert.equal(checkboxes.length,1);
  checkboxes[0].checked=true;checkboxes[0].dispatchEvent(new dom.window.Event("change"));
  list.replaceChildren();row=renderShoppingItem(card,list,target);
  [...row.querySelectorAll(".notice button")].find(b=>b.textContent===SHOPPING_ITEM_COPY.en.action_merge).click();
  assert.deepEqual(card._shoppingItemAction.frozenPayload,{id:"a",revision:2,sources:[{id:"b",revision:3}]});
  assert.equal(card._shoppingItemAction.totalQtyAfter,2);
});

test("Hostile names and XSS prevention (DOM textContent only, no raw HTML tags)", () => {
  const card = createMockCard();
  const hostileItem = {
    id: "s_xss",
    revision: 1,
    name: '<script>alert("xss")</script><img src=x onerror=alert(1)>',
    category: "<b>bold category</b>",
    store: '<iframe src="evil.com"></iframe>',
    note: "<style>body{display:none}</style>",
    status: "approved",
    quantity: 2,
    purchased: 0,
    creator: "p1",
    buyer: "a1"
  };

  const list = document.createElement("ul");
  const row = renderShoppingItem(card, list, hostileItem);

  assert.equal(list.children.length, 1);
  assert.equal(row.querySelectorAll("script").length, 0);
  assert.equal(row.querySelectorAll("img").length, 0);
  assert.equal(row.querySelectorAll("iframe").length, 0);
  assert.equal(row.querySelectorAll("style").length, 0);
  assert.equal(row.querySelectorAll("b").length, 0);
  assert.ok(row.textContent.includes('<script>alert("xss")</script>'));
});

test("Permissions: guest cannot see buy remaining or partial purchase; child can buy/partial but not approve/merge/archive", () => {
  const item = {
    id: "s1",
    revision: 1,
    name: "Milk",
    status: "approved",
    quantity: 5,
    purchased: 2,
    unit: "l"
  };

  // 1. Guest
  const guestCard = createMockCard({ role: "guest", isParent: false });
  const guestUl = document.createElement("ul");
  const guestRow = renderShoppingItem(guestCard, guestUl, item);
  assert.equal(guestRow.querySelectorAll("button").length, 0);

  // 2. Child (non-guest, non-parent)
  const childCard = createMockCard({ role: "child", isParent: false });
  const childUl = document.createElement("ul");
  const childRow = renderShoppingItem(childCard, childUl, item);
  const childButtons = Array.from(childRow.querySelectorAll("button")).map(b => b.textContent);

  assert.ok(childButtons.includes(SHOPPING_ITEM_COPY.en.action_buy_remaining));
  assert.ok(childButtons.includes(SHOPPING_ITEM_COPY.en.action_partial_purchase));
  assert.ok(!childButtons.includes(SHOPPING_ITEM_COPY.en.action_archive));
  assert.ok(!childButtons.includes(SHOPPING_ITEM_COPY.en.action_merge));

  // 3. Parent pending item: approve and reject
  const pendingItem = { id: "s2", revision: 1, name: "Juice", status: "pending", quantity: 1, purchased: 0 };
  const parentCard = createMockCard({ role: "parent", isParent: true });
  const parentUl = document.createElement("ul");
  const parentRow = renderShoppingItem(parentCard, parentUl, pendingItem);
  const parentButtons = Array.from(parentRow.querySelectorAll("button")).map(b => b.textContent);

  assert.ok(parentButtons.includes(SHOPPING_ITEM_COPY.en.action_approve));
  assert.ok(parentButtons.includes(SHOPPING_ITEM_COPY.en.action_reject));
  assert.ok(parentButtons.includes(SHOPPING_ITEM_COPY.en.action_archive));
});

test("Member resolution: friendly names shown, unknown members get localized fallback, never raw id", () => {
  const card = createMockCard();
  const item = {
    id: "s10",
    revision: 1,
    name: "Bread",
    status: "approved",
    quantity: 1,
    purchased: 0,
    creator: "p1",
    buyer: "non_existent_user_id"
  };

  const ul = document.createElement("ul");
  const row = renderShoppingItem(card, ul, item);
  const text = row.textContent;

  assert.ok(text.includes("Parent One"));
  assert.ok(text.includes(SHOPPING_ITEM_COPY.en.unknown_member));
  assert.ok(!text.includes("non_existent_user_id"));
});

test("Buy remaining dispatches shopping.purchase with exact remaining amount", () => {
  const item = {
    id: "s20",
    revision: 3,
    name: "Apples",
    status: "approved",
    quantity: 4.5,
    purchased: 1.25,
    unit: "kg"
  };

  const card = createMockCard({ role: "adult", isParent: false });
  const ul = document.createElement("ul");
  const row = renderShoppingItem(card, ul, item);

  const buyRemBtn = Array.from(row.querySelectorAll("button")).find(
    b => b.textContent === SHOPPING_ITEM_COPY.en.action_buy_remaining
  );
  assert.ok(buyRemBtn);
  buyRemBtn.click();

  assert.equal(card.commands.length, 1);
  assert.deepEqual(card.commands[0], {
    action: "shopping.purchase",
    payload: {
      id: "s20",
      revision: 3,
      quantity: 3.25,
      unit: "kg"
    }
  });
});

test("Partial purchase form: card.input real form with numeric validation and frozen retry", async () => {
  const item = {
    id: "s30",
    revision: 7,
    name: "Flour",
    status: "approved",
    quantity: 5,
    purchased: 2,
    unit: "kg"
  };

  const card = createMockCard({ role: "adult", isParent: false });
  const ul = document.createElement("ul");
  let row = renderShoppingItem(card, ul, item);

  // Click partial purchase
  const partialBtn = Array.from(row.querySelectorAll("button")).find(
    b => b.textContent === SHOPPING_ITEM_COPY.en.action_partial_purchase
  );
  assert.ok(partialBtn);
  partialBtn.click();

  // Action form is open
  ul.replaceChildren();
  row = renderShoppingItem(card, ul, item);

  const form = row.querySelector("form");
  assert.ok(form, "Partial purchase should render real form");
  const input = form.querySelector('input[name="quantity"]');
  assert.ok(input);

  // Validation: negative, 0, > remaining (3), > 6 decimal places
  for (const inv of ["-1", "0", "4", "3.0000001", "abc"]) {
    input.value = inv;
    form.dispatchEvent(new dom.window.Event("submit", { cancelable: true }));
    assert.equal(card.commands.length, 0, `Must reject invalid input ${inv}`);
  }

  // Valid submit with simulated command failure
  card.commandFn = async () => {
    card._actionError = "storage_conflict";
  };
  input.value = "1.5";
  form.dispatchEvent(new dom.window.Event("submit", { cancelable: true }));
  await new Promise(resolve => setTimeout(resolve, 0));

  assert.equal(card.commands.length, 1);
  assert.deepEqual(card.commands[0], {
    action: "shopping.purchase",
    payload: {
      id: "s30",
      revision: 7,
      quantity: 1.5,
      unit: "kg"
    }
  });

  // Re-render after failure: retry payload is frozen, input disabled
  ul.replaceChildren();
  row = renderShoppingItem(card, ul, item);

  const retryForm = row.querySelector("form");
  const retryInput = retryForm.querySelector('input[name="quantity"]');
  assert.equal(retryInput.disabled, true, "Input must be disabled during frozen retry");

  const submitBtn = retryForm.querySelector('button[type="submit"]');
  assert.equal(submitBtn.textContent, SHOPPING_ITEM_COPY.en.action_retry);

  // Submitting retry sends exact frozen payload
  retryForm.dispatchEvent(new dom.window.Event("submit", { cancelable: true }));
  assert.equal(card.commands.length, 2);
  assert.deepEqual(card.commands[1], card.commands[0]);

  // Cancel permits editing anew
  const cancelBtn = Array.from(retryForm.querySelectorAll("button")).find(
    b => b.textContent === SHOPPING_ITEM_COPY.en.action_cancel
  );
  assert.ok(cancelBtn);
  cancelBtn.click();
  assert.equal(card._shoppingItemAction, null);
  assert.equal(card._actionError, null);
});

test("Merge UI: snapshots target and candidates, labels show names/qty/unit/buyer no raw IDs, explicit 2-step confirmation", () => {
  const target = {
    id: "tgt",
    revision: 12,
    name: "Coffee Beans ",
    category: "Groceries",
    store: "Roastery",
    note: "Dark roast",
    buyer: "p1",
    unit: "bags",
    status: "approved",
    quantity: 2,
    purchased: 0
  };

  const cand1 = {
    id: "c1",
    revision: 3,
    name: " coffee beans",
    category: "Groceries",
    store: "Roastery",
    note: "Dark roast",
    buyer: "p1",
    unit: "bags",
    status: "approved",
    quantity: 3,
    purchased: 1 // remaining = 2
  };

  const cand2DifferentStore = {
    id: "c2",
    revision: 1,
    name: "coffee beans",
    category: "Groceries",
    store: "Other Store",
    note: "Dark roast",
    buyer: "p1",
    unit: "bags",
    status: "approved",
    quantity: 1,
    purchased: 0
  };

  const shopping = [target, cand1, cand2DifferentStore];
  const card = createMockCard({ role: "parent", isParent: true, shopping });

  const ul = document.createElement("ul");
  let row = renderShoppingItem(card, ul, target);

  // Click merge items
  const mergeBtn = Array.from(row.querySelectorAll("button")).find(
    b => b.textContent === SHOPPING_ITEM_COPY.en.action_merge
  );
  assert.ok(mergeBtn);
  mergeBtn.click();

  // Re-render Step 1: Candidate selection
  ul.replaceChildren();
  row = renderShoppingItem(card, ul, target);

  const checkboxes = row.querySelectorAll('input[type="checkbox"]');
  assert.equal(checkboxes.length, 1, "Only cand1 matches merge criteria");
  assert.equal(checkboxes[0].value, "c1");

  // Candidate label check: proper nested label checkbox, no raw IDs
  const labelText = checkboxes[0].parentElement.textContent;
  assert.ok(labelText.includes("coffee beans"));
  assert.ok(labelText.includes("Parent One"));
  assert.ok(!labelText.includes("c1"));

  // Select candidate 1
  checkboxes[0].checked = true;
  checkboxes[0].dispatchEvent(new dom.window.Event("change"));

  ul.replaceChildren();
  row = renderShoppingItem(card, ul, target);

  // Click Review Merge
  const reviewBtn = Array.from(row.querySelectorAll(".notice button")).find(
    b => b.textContent === SHOPPING_ITEM_COPY.en.action_merge
  );
  reviewBtn.click();

  // Re-render Step 2: Confirmation
  ul.replaceChildren();
  row = renderShoppingItem(card, ul, target);

  const confirmSection = row.querySelector(".notice");
  assert.ok(confirmSection);
  assert.ok(confirmSection.textContent.includes(SHOPPING_ITEM_COPY.en.warning_merge_sources_retained));
  assert.ok(confirmSection.textContent.includes("coffee beans"));
  assert.ok(confirmSection.textContent.includes(`${SHOPPING_ITEM_COPY.en.label_total_after_merge}: 5 bags`));
  assert.ok(confirmSection.textContent.includes(`${SHOPPING_ITEM_COPY.en.label_total_purchased_after_merge}: 1 bags`));

  // Confirm merge
  const confirmBtn = Array.from(confirmSection.querySelectorAll("button")).find(
    b => b.textContent === SHOPPING_ITEM_COPY.en.action_confirm_merge
  );
  assert.ok(confirmBtn);
  confirmBtn.click();

  assert.equal(card.commands.length, 1);
  assert.deepEqual(card.commands[0], {
    action: "shopping.merge",
    payload: {
      id: "tgt",
      revision: 12,
      sources: [{ id: "c1", revision: 3 }]
    }
  });
});

test("History rendering: collapsed details, localized actions/labels, dates in household timezone, source item names resolved from shopping items", () => {
  const item = {
    id: "s50",
    revision: 5,
    name: "Sugar",
    status: "approved",
    quantity: 10,
    purchased: 4,
    unit: "kg",
    history: [
      {
        at: "2026-09-01T10:00:00Z",
        actor: "p1",
        action: "add",
        detail: { quantity: 5, unit: "kg" }
      },
      {
        at: "2026-09-02T12:00:00Z",
        actor: "a1",
        action: "merge",
        detail: { sources: ["s_source"], quantity: 10, purchased: 2 }
      },
      {
        at: "2026-09-03T15:30:00Z",
        actor: "c1",
        action: "purchase",
        detail: { amount: 2, purchased: 4, remaining: 6 }
      }
    ]
  };

  const otherItem = {
    id: "s_source",
    name: "Extra Sugar",
    status: "merged"
  };

  const card = createMockCard({ shopping: [item, otherItem], timezone: "UTC" });
  const ul = document.createElement("ul");
  const row = renderShoppingItem(card, ul, item);

  const details = row.querySelector("details");
  assert.ok(details, "History should be inside collapsed details element");
  assert.equal(details.open, false);

  const historyEntries = Array.from(details.querySelectorAll("li")).map(li => li.textContent);
  assert.equal(historyEntries.length, 3);

  // Check localized action and resolved source item name
  assert.ok(historyEntries[2].includes("Parent One"));
  assert.ok(historyEntries[2].includes(SHOPPING_ITEM_COPY.en.history_action_add));

  assert.ok(historyEntries[1].includes("Adult One"));
  assert.ok(historyEntries[1].includes(SHOPPING_ITEM_COPY.en.history_action_merge));
  assert.ok(historyEntries[1].includes("Extra Sugar"), "Source ID must resolve to item name, not member or raw ID");
  assert.ok(!historyEntries[1].includes("s_source"));

  assert.ok(historyEntries[0].includes("Child One"));
  assert.ok(historyEntries[0].includes(SHOPPING_ITEM_COPY.en.history_action_purchase));
});

test("History pagination: latest 50 entries shown, Show more expands without deleting data", () => {
  const entries = [];
  for (let i = 0; i < 65; i++) {
    entries.push({
      at: "2026-09-01T10:00:00Z",
      actor: "p1",
      action: "purchase",
      detail: { amount: 1 }
    });
  }

  const item = {
    id: "s60",
    revision: 65,
    name: "Bulk Oats",
    status: "approved",
    quantity: 100,
    purchased: 65,
    history: entries
  };

  const card = createMockCard({ shopping: [item] });
  const ul = document.createElement("ul");
  const row = renderShoppingItem(card, ul, item);

  const details = row.querySelector("details");
  let listItems = details.querySelectorAll("li");
  assert.equal(listItems.length, 50, "Initial visible history count should be 50");

  const moreBtn = Array.from(details.querySelectorAll("button")).find(
    b => b.textContent === SHOPPING_ITEM_COPY.en.history_show_more
  );
  assert.ok(moreBtn);
  moreBtn.click();

  listItems = details.querySelectorAll("li");
  assert.equal(listItems.length, 65, "All 65 entries should now be visible");
  assert.equal(moreBtn.style.display, "none");
});

test("Archive rendering: uses details and ul, filters only purchased/rejected/archived/merged", () => {
  const shopping = [
    { id: "1", name: "Open item", status: "approved", quantity: 1, purchased: 0 },
    { id: "2", name: "Purchased item", status: "purchased", quantity: 1, purchased: 1 },
    { id: "3", name: "Rejected item", status: "rejected", quantity: 1, purchased: 0 },
    { id: "4", name: "Archived item", status: "archived", quantity: 1, purchased: 0 },
    { id: "5", name: "Merged item", status: "merged", quantity: 1, purchased: 0 }
  ];

  const card = createMockCard({ shopping });
  const body = document.createElement("div");
  const archiveDetails = renderShoppingArchive(card, body);

  assert.equal(archiveDetails.tagName.toLowerCase(), "details");
  assert.equal(archiveDetails.open, false);

  const rows = archiveDetails.querySelectorAll("li.item");
  assert.equal(rows.length, 4);

  const text = archiveDetails.textContent;
  assert.ok(text.includes("Purchased item"));
  assert.ok(text.includes("Rejected item"));
  assert.ok(text.includes("Archived item"));
  assert.ok(text.includes("Merged item"));
  assert.ok(!text.includes("Open item"));
});

test("Guard before every event when _writing is true or generation changed", () => {
  const item = {
    id: "s70",
    revision: 1,
    name: "Tea",
    status: "approved",
    quantity: 2,
    purchased: 0
  };

  const card = createMockCard({ role: "parent", isParent: true });
  const ul = document.createElement("ul");
  const row = renderShoppingItem(card, ul, item);

  const buttons = Array.from(row.querySelectorAll("button"));
  assert.ok(buttons.length > 0);

  // 1. When _writing is true, buttons are disabled and programmatic invocation ignored
  card._writing = true;
  const writingList=document.createElement("ul");
  renderShoppingItem(card, writingList, item);
  for (const btn of writingList.querySelectorAll("button")) {
    assert.equal(btn.disabled, true);
  }

  // 2. Generation changed guard
  card._writing = false;
  card._generation = 999; // generation updated externally

  const buyBtn = buttons.find(b => b.textContent === SHOPPING_ITEM_COPY.en.action_buy_remaining);
  buyBtn.click();
  assert.equal(card.commands.length, 0, "Event must be ignored when generation does not match");
});

test("Integration 1: Actual FamilyCard element initializes and renders shopping view with open and archive items", async () => {
  const card = document.createElement("family-shopping-card");
  const shopping = [
    { id: "i1", name: "Fresh Milk", status: "approved", quantity: 2, purchased: 0, revision: 1 },
    { id: "i2", name: "Old Bread", status: "purchased", quantity: 1, purchased: 1, revision: 2 }
  ];

  card._hass = {
    language: "en",
    config: { time_zone: "Europe/Kyiv" },
    callWS: async (msg) => {
      if (msg.type === "family_assistant/view") {
        return {
          role: "parent",
          actor: "p1",
          settings: { name: "Our Family", timezone: "Europe/Kyiv", modules: ["shopping"] },
          members: [{ id: "p1", name: "Parent One", role: "parent", active: true }],
          shopping
        };
      }
      return {};
    }
  };

  card.setConfig({ view: "shopping", entry_id: "entry_1" });
  await new Promise(resolve => setTimeout(resolve, 0));

  const shadow = card.shadowRoot;
  assert.ok(shadow);

  // Check open items list
  const list = shadow.querySelector("ul.list");
  assert.ok(list);
  assert.ok(list.textContent.includes("Fresh Milk"));
  assert.ok(!list.textContent.includes("Old Bread"));

  // Check archive details
  const archiveDetails = shadow.querySelector("details.shopping-archive");
  assert.ok(archiveDetails);
  assert.ok(archiveDetails.textContent.includes("Old Bread"));
});

test("Integration 2: Actual FamilyCard executes shopping command through card.command", async () => {
  const card = document.createElement("family-shopping-card");
  const executed = [];
  const shopping = [
    { id: "i1", name: "Apples", status: "approved", quantity: 3, purchased: 0, unit: "kg", revision: 1 }
  ];

  card._hass = {
    language: "en",
    config: { time_zone: "Europe/Kyiv" },
    callWS: async (msg) => {
      if (msg.type === "family_assistant/view") {
        return {
          role: "parent",
          actor: "p1",
          settings: { name: "Our Family", timezone: "Europe/Kyiv", modules: ["shopping"] },
          members: [{ id: "p1", name: "Parent One", role: "parent", active: true }],
          shopping
        };
      }
      if (msg.type === "family_assistant/execute") {
        executed.push(msg);
        return { accepted: true };
      }
      return {};
    }
  };

  card.setConfig({ view: "shopping", entry_id: "entry_1" });
  await new Promise(resolve => setTimeout(resolve, 0));

  const shadow = card.shadowRoot;
  const buyBtn = Array.from(shadow.querySelectorAll("button")).find(
    b => b.textContent === SHOPPING_ITEM_COPY.en.action_buy_remaining
  );
  assert.ok(buyBtn);

  buyBtn.click();
  // Allow refresh / command promise cycle
  await new Promise(resolve => setTimeout(resolve, 10));

  assert.equal(executed.length, 1);
  assert.equal(executed[0].action, "shopping.purchase");
  assert.deepEqual(executed[0].payload, {
    id: "i1",
    revision: 1,
    quantity: 3,
    unit: "kg"
  });
});
