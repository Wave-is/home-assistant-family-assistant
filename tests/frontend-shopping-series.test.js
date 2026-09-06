import assert from "node:assert/strict";
import {test} from "node:test";
import {JSDOM} from "jsdom";

const dom = new JSDOM("<!doctype html><body></body>", {url: "http://localhost"});
for (const key of ["window", "document", "HTMLElement", "customElements", "CustomEvent", "FormData"]) {
  globalThis[key] = dom.window[key];
}

const {SHOPPING_SERIES_COPY, renderShoppingSeries} = await import(
  "../custom_components/family_assistant/frontend/shopping-series.js"
);

function createMockCard({
  role = "parent",
  isParent = true,
  lang = "en",
  timezone = "Europe/Kyiv",
  series = [],
  members = [
    {id: "p1", name: "Parent One", role: "parent", active: true},
    {id: "a1", name: "Adult One", role: "adult", active: true},
    {id: "c1", name: "Child One", role: "child", active: true},
  ],
  commandFn = null,
} = {}) {
  const commands = [];
  const card = {
    _view: "shopping",
    _data: {
      role,
      actor: "p1",
      settings: {timezone},
      members,
      shopping_series: series,
    },
    _config: {language: lang},
    _hass: {language: lang, config: {time_zone: timezone}},
    parent: isParent,
    _writing: false,
    _shoppingSeriesFormOpen: false,
    _shoppingSeriesEditingItem: null,
    commands,
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
      Object.assign(input, {name, type, value, required});
      wrap.append(input);
      form.append(wrap);
      return input;
    },
    command(action, payload) {
      commands.push({action, payload});
      if (commandFn) commandFn(action, payload);
    },
    render() {},
  };
  return card;
}

test("SHOPPING_SERIES_COPY has exact localization key parity across en, ru, and uk", () => {
  const enKeys = Object.keys(SHOPPING_SERIES_COPY.en).sort();
  const ruKeys = Object.keys(SHOPPING_SERIES_COPY.ru).sort();
  const ukKeys = Object.keys(SHOPPING_SERIES_COPY.uk).sort();

  assert.deepEqual(ruKeys, enKeys, "RU keys must match EN keys exactly");
  assert.deepEqual(ukKeys, enKeys, "UK keys must match EN keys exactly");

  // Ensure dayNames arrays have 7 days in all locales
  assert.equal(SHOPPING_SERIES_COPY.en.dayNames.length, 7);
  assert.equal(SHOPPING_SERIES_COPY.ru.dayNames.length, 7);
  assert.equal(SHOPPING_SERIES_COPY.uk.dayNames.length, 7);
});

test("creates exact typed payload for shopping.series_save", () => {
  const card = createMockCard({isParent: true, timezone: "Europe/Kyiv"});
  card._shoppingSeriesFormOpen = true;
  const body = document.createElement("div");
  renderShoppingSeries(card, body);

  const form = body.querySelector("form.shopping-series-form");
  assert.ok(form, "Series form should be rendered when open");

  // Fill in form fields
  form.querySelector('input[name="name"]').value = "Organic Apples";
  form.querySelector('input[name="quantity"]').value = "2.5";
  form.querySelector('input[name="unit"]').value = "kg";
  form.querySelector('select[name="buyer"]').value = "a1";
  form.querySelector('select[name="frequency"]').value = "weekly";
  form.querySelector('input[name="time"]').value = "09:30";
  form.querySelector('input[name="start_date"]').value = "2026-09-07";

  // Check weekdays 0 (Mon) and 4 (Fri)
  for (const box of form.querySelectorAll('input[name="weekdays"]')) {
    box.checked = box.value === "0" || box.value === "4";
  }

  // Advanced fields
  form.querySelector('input[name="store"]').value = "Farmers Market";
  form.querySelector('input[name="category"]').value = "Produce";
  form.querySelector('input[name="note"]').value = "Crisp only";
  form.querySelector('input[name="timezone"]').value = "Europe/Kyiv";
  form.querySelector('input[name="until"]').value = "2026-12-31";
  form.querySelector('input[name="interval"]').value = "2";
  form.querySelector('input[name="exceptions"]').value = "2026-10-02, 2026-10-09";
  form.querySelector('input[name="catchup_hours"]').value = "12";

  // Submit form
  form.dispatchEvent(new dom.window.Event("submit", {cancelable: true}));

  assert.equal(card.commands.length, 1);
  const cmd = card.commands[0];
  assert.equal(cmd.action, "shopping.series_save");
  assert.deepEqual(cmd.payload, {
    name: "Organic Apples",
    quantity: 2.5,
    unit: "kg",
    category: "Produce",
    store: "Farmers Market",
    note: "Crisp only",
    buyer: "a1",
    enabled: true,
    rule: {
      frequency: "weekly",
      interval: 2,
      start_date: "2026-09-07",
      until: "2026-12-31",
      time: "09:30",
      timezone: "Europe/Kyiv",
      weekdays: [0, 4],
      exceptions: ["2026-10-02", "2026-10-09"],
      catchup_hours: 12,
    },
  });
});

test("editing a series includes id and revision, preserving optional rule data", () => {
  const existingSeries = {
    id: "B123",
    revision: 4,
    name: "Oat Milk",
    quantity: 3,
    unit: "l",
    category: "Groceries",
    store: "Supermarket",
    note: "Unsweetened",
    buyer: "a1",
    enabled: true,
    rule: {
      frequency: "monthly",
      interval: 1,
      start_date: "2026-09-01",
      until: null,
      time: "08:00",
      timezone: "Europe/Kyiv",
      month_day: 15,
      weekdays: [1, 3],
      exceptions: ["2026-12-25"],
      catchup_hours: 24,
    },
  };

  const card = createMockCard({
    isParent: true,
    series: [existingSeries],
  });
  card._shoppingSeriesFormOpen = true;
  card._shoppingSeriesEditingItem = existingSeries;

  const body = document.createElement("div");
  renderShoppingSeries(card, body);

  const form = body.querySelector("form.shopping-series-form");
  assert.ok(form);

  // Edit quantity and name, and provide updated exceptions
  form.querySelector('input[name="name"]').value = "Oat Milk (Barista)";
  form.querySelector('input[name="quantity"]').value = "4";
  form.querySelector('input[name="exceptions"]').value = "2026-12-25";

  // Submit
  form.dispatchEvent(new dom.window.Event("submit", {cancelable: true}));

  assert.equal(card.commands.length, 1);
  const cmd = card.commands[0];
  assert.equal(cmd.action, "shopping.series_save");
  assert.equal(cmd.payload.id, "B123");
  assert.equal(cmd.payload.revision, 4);
  assert.equal(cmd.payload.name, "Oat Milk (Barista)");
  assert.equal(cmd.payload.quantity, 4);
  assert.equal(cmd.payload.rule.month_day, 15);
  // Preserves existing weekdays from existing item when not in active weekly mode
  assert.deepEqual(cmd.payload.rule.weekdays, [1, 3]);
  assert.deepEqual(cmd.payload.rule.exceptions, ["2026-12-25"]);
});

test("clearing buyer emits buyer: null and clearing exceptions emits exceptions: []", () => {
  const existingSeries = {
    id: "B777",
    revision: 2,
    name: "Olive Oil",
    quantity: 1,
    unit: "bottle",
    buyer: "a1",
    enabled: true,
    rule: {
      frequency: "daily",
      interval: 1,
      start_date: "2026-09-01",
      time: "08:00",
      timezone: "Europe/Kyiv",
      exceptions: ["2026-09-10"],
      catchup_hours: 24,
    },
  };

  const card = createMockCard({
    isParent: true,
    series: [existingSeries],
  });
  card._shoppingSeriesFormOpen = true;
  card._shoppingSeriesEditingItem = existingSeries;

  const body = document.createElement("div");
  renderShoppingSeries(card, body);

  const form = body.querySelector("form.shopping-series-form");
  assert.ok(form);

  // Clear buyer by selecting empty unassigned option
  form.querySelector('select[name="buyer"]').value = "";
  // Clear exceptions input
  form.querySelector('input[name="exceptions"]').value = "";

  form.dispatchEvent(new dom.window.Event("submit", {cancelable: true}));

  assert.equal(card.commands.length, 1);
  const cmd = card.commands[0];
  assert.equal(cmd.action, "shopping.series_save");
  assert.equal(cmd.payload.buyer, null, "Clearing buyer on edit must explicitly emit buyer: null");
  assert.deepEqual(cmd.payload.rule.exceptions, [], "Clearing exceptions must emit empty array []");
});

test("inactive existing buyer is preserved in form options and summary without raw fallback IDs", () => {
  const inactiveMember = {id: "inact1", name: "Departed Roommate", role: "adult", active: false};
  const existingSeries = {
    id: "B888",
    revision: 1,
    name: "Specialty Tea",
    quantity: 2,
    unit: "boxes",
    buyer: "inact1",
    enabled: true,
    rule: {
      frequency: "weekly",
      interval: 1,
      start_date: "2026-09-01",
      time: "08:00",
      timezone: "Europe/Kyiv",
      weekdays: [2],
      catchup_hours: 24,
    },
  };

  const card = createMockCard({
    isParent: true,
    series: [existingSeries],
    members: [
      {id: "p1", name: "Parent One", role: "parent", active: true},
      inactiveMember,
    ],
  });

  // Check summary rendering
  const summaryBody = document.createElement("div");
  renderShoppingSeries(card, summaryBody);

  assert.match(summaryBody.textContent, /Departed Roommate \(inactive\)/);
  assert.doesNotMatch(summaryBody.textContent, /\binact1\b/);

  // Open edit form
  card._shoppingSeriesFormOpen = true;
  card._shoppingSeriesEditingItem = existingSeries;
  const formBody = document.createElement("div");
  renderShoppingSeries(card, formBody);

  const form = formBody.querySelector("form.shopping-series-form");
  const buyerSelect = form.querySelector('select[name="buyer"]');
  assert.ok(buyerSelect);

  // The inactive buyer must be present and selected
  const selectedOpt = buyerSelect.querySelector("option:checked");
  assert.equal(selectedOpt.value, "inact1");
  assert.match(selectedOpt.textContent, /Departed Roommate \(inactive\)/);

  // Submitting an unrelated change preserves buyer: "inact1"
  form.querySelector('input[name="quantity"]').value = "3";
  form.dispatchEvent(new dom.window.Event("submit", {cancelable: true}));

  assert.equal(card.commands.length, 1);
  assert.equal(card.commands[0].payload.buyer, "inact1");
  assert.equal(card.commands[0].payload.quantity, 3);
});

test("enable and disable issue shopping.series_enable with id and revision", () => {
  const series = [
    {
      id: "B100",
      revision: 2,
      name: "Butter",
      quantity: 1,
      unit: "pack",
      enabled: true,
      rule: {frequency: "daily", interval: 1, start_date: "2026-09-01", time: "08:00", timezone: "UTC"},
    },
    {
      id: "B101",
      revision: 5,
      name: "Eggs",
      quantity: 10,
      unit: "pcs",
      enabled: false,
      rule: {frequency: "weekly", interval: 1, start_date: "2026-09-01", time: "08:00", timezone: "UTC", weekdays: [0]},
    },
  ];

  const card = createMockCard({isParent: true, series});
  const body = document.createElement("div");
  renderShoppingSeries(card, body);

  const buttons = Array.from(body.querySelectorAll("button"));
  const disableBtn = buttons.find(b => b.textContent === SHOPPING_SERIES_COPY.en.disable);
  const enableBtn = buttons.find(b => b.textContent === SHOPPING_SERIES_COPY.en.enable);

  assert.ok(disableBtn, "Disable button should exist for enabled item");
  assert.ok(enableBtn, "Enable button should exist for disabled item");

  disableBtn.click();
  assert.equal(card.commands.length, 1);
  assert.deepEqual(card.commands[0], {
    action: "shopping.series_enable",
    payload: {id: "B100", revision: 2, enabled: false},
  });

  enableBtn.click();
  assert.equal(card.commands.length, 2);
  assert.deepEqual(card.commands[1], {
    action: "shopping.series_enable",
    payload: {id: "B101", revision: 5, enabled: true},
  });
});

test("child, adult non-parent and guest views have no controls or are empty", () => {
  const series = [
    {
      id: "B200",
      revision: 1,
      name: "Bananas",
      quantity: 5,
      unit: "pcs",
      enabled: true,
      rule: {frequency: "daily", interval: 1, start_date: "2026-09-01", time: "08:00", timezone: "UTC"},
    },
  ];

  // 1. Child view: summarizes items, no Add / Edit / Enable buttons, no internal IDs or MACs
  const childCard = createMockCard({role: "child", isParent: false, series});
  const childBody = document.createElement("div");
  renderShoppingSeries(childCard, childBody);

  assert.match(childBody.textContent, /Bananas/);
  assert.match(childBody.textContent, /Daily/);
  assert.equal(childBody.querySelectorAll("button").length, 0);
  assert.doesNotMatch(childBody.textContent, /B200/);
  assert.doesNotMatch(childBody.textContent, /[0-9a-fA-F]{2}(:[0-9a-fA-F]{2}){5}/);

  // 2. Adult non-parent view: summarizes items, no controls
  const adultCard = createMockCard({role: "adult", isParent: false, series});
  const adultBody = document.createElement("div");
  renderShoppingSeries(adultCard, adultBody);
  assert.match(adultBody.textContent, /Bananas/);
  assert.equal(adultBody.querySelectorAll("button").length, 0);

  // 3. Guest view: nothing rendered
  const guestCard = createMockCard({role: "guest", isParent: false, series});
  const guestBody = document.createElement("div");
  renderShoppingSeries(guestCard, guestBody);
  assert.equal(guestBody.children.length, 0);
});

test("safe hostile-name rendering via DOM textContent without stringbuilt HTML", () => {
  const xssName = '<img src="x" onerror="alert(1)"> <script>alert(2)</script>';
  const series = [
    {
      id: "B300",
      revision: 1,
      name: xssName,
      quantity: 1,
      unit: "<bdi>safe</bdi>",
      note: "<svg/onload=alert(3)>",
      enabled: true,
      rule: {frequency: "daily", interval: 1, start_date: "2026-09-01", time: "08:00", timezone: "UTC"},
    },
  ];

  const card = createMockCard({isParent: true, series});
  const body = document.createElement("div");
  renderShoppingSeries(card, body);

  assert.equal(body.querySelectorAll("img").length, 0);
  assert.equal(body.querySelectorAll("script").length, 0);
  assert.equal(body.querySelectorAll("svg").length, 0);
  assert.equal(body.querySelectorAll("bdi").length, 0);

  assert.ok(body.textContent.includes(xssName));
  assert.ok(body.textContent.includes("<bdi>safe</bdi>"));
  assert.ok(body.textContent.includes("<svg/onload=alert(3)>"));
});

test("explanation notice regarding unfinished purchases and no duplicate addition is clearly displayed", () => {
  const card = createMockCard({isParent: true, lang: "ru"});
  const body = document.createElement("div");
  renderShoppingSeries(card, body);

  assert.ok(body.textContent.includes(SHOPPING_SERIES_COPY.ru.duplicateNotice));
  assert.match(body.textContent, /автоматически не объединяются/);
  assert.equal(body.querySelector("details").open,false);
});

test("form validation rejects invalid numeric inputs and invalid rules", () => {
  const card = createMockCard({isParent: true});
  card._shoppingSeriesFormOpen = true;
  const body = document.createElement("div");
  renderShoppingSeries(card, body);

  const form = body.querySelector("form.shopping-series-form");
  const alertBox = form.querySelector('[role="alert"]');

  // Empty name
  form.querySelector('input[name="name"]').value = "   ";
  form.dispatchEvent(new dom.window.Event("submit", {cancelable: true}));
  assert.equal(card.commands.length, 0);
  assert.equal(alertBox.style.display, "block");
  assert.match(alertBox.textContent, /valid name/);

  // Invalid quantity (< 0.001)
  form.querySelector('input[name="name"]').value = "Valid Name";
  form.querySelector('input[name="quantity"]').value = "0";
  form.dispatchEvent(new dom.window.Event("submit", {cancelable: true}));
  assert.equal(card.commands.length, 0);
  assert.match(alertBox.textContent, /between 0.001 and 1000000/);

  // Invalid quantity (> 1000000)
  form.querySelector('input[name="quantity"]').value = "1000001";
  form.dispatchEvent(new dom.window.Event("submit", {cancelable: true}));
  assert.equal(card.commands.length, 0);
  assert.match(alertBox.textContent, /between 0.001 and 1000000/);

  // Invalid quantity (NaN / non-finite)
  form.querySelector('input[name="quantity"]').value = "abc";
  form.dispatchEvent(new dom.window.Event("submit", {cancelable: true}));
  assert.equal(card.commands.length, 0);
  assert.match(alertBox.textContent, /between 0.001 and 1000000/);

  // Invalid interval (> 52)
  form.querySelector('input[name="quantity"]').value = "1";
  form.querySelector('input[name="interval"]').value = "99";
  form.dispatchEvent(new dom.window.Event("submit", {cancelable: true}));
  assert.equal(card.commands.length, 0);
  assert.match(alertBox.textContent, /Interval must be an integer between 1 and 52/);

  // Weekly rule with zero weekdays selected
  form.querySelector('input[name="interval"]').value = "1";
  form.querySelector('select[name="frequency"]').value = "weekly";
  for (const box of form.querySelectorAll('input[name="weekdays"]')) {
    box.checked = false;
  }
  form.dispatchEvent(new dom.window.Event("submit", {cancelable: true}));
  assert.equal(card.commands.length, 0);
  assert.match(alertBox.textContent, /select at least one weekday/);

  // Monthly rule with invalid day (e.g. 32)
  form.querySelector('select[name="frequency"]').value = "monthly";
  form.querySelector('input[name="month_day"]').value = "32";
  form.dispatchEvent(new dom.window.Event("submit", {cancelable: true}));
  assert.equal(card.commands.length, 0);
  assert.match(alertBox.textContent, /Month day must be an integer between 1 and 31/);

  // Catchup hours invalid (> 48)
  form.querySelector('input[name="month_day"]').value = "15";
  form.querySelector('input[name="catchup_hours"]').value = "60";
  form.dispatchEvent(new dom.window.Event("submit", {cancelable: true}));
  assert.equal(card.commands.length, 0);
  assert.match(alertBox.textContent, /Catchup hours must be between 0 and 48/);
});

test("form cancellation does not submit or write commands", () => {
  let rendered = false;
  const card = createMockCard({isParent: true});
  card._shoppingSeriesFormOpen = true;
  card.render = () => {
    rendered = true;
  };

  const body = document.createElement("div");
  renderShoppingSeries(card, body);

  const cancelBtn = Array.from(body.querySelectorAll("button")).find(
    b => b.textContent === SHOPPING_SERIES_COPY.en.cancel
  );
  assert.ok(cancelBtn, "Cancel button should exist");
  cancelBtn.click();

  assert.equal(card.commands.length, 0, "No commands sent on cancel");
  assert.equal(card._shoppingSeriesFormOpen, false, "Form state closed on cancel");
  assert.equal(rendered, true, "Card render triggered on cancel");
});

test("respects _writing controls by disabling action buttons and blocking programmatic submit", () => {
  const series = [
    {
      id: "B500",
      revision: 1,
      name: "Coffee Beans",
      quantity: 1,
      unit: "kg",
      enabled: true,
      rule: {frequency: "daily", interval: 1, start_date: "2026-09-01", time: "08:00", timezone: "UTC"},
    },
  ];
  const card = createMockCard({isParent: true, series});
  card._shoppingSeriesFormOpen = true;

  const body = document.createElement("div");
  renderShoppingSeries(card, body);

  // Set card._writing to true
  card._writing = true;

  const form = body.querySelector("form.shopping-series-form");
  assert.ok(form);
  form.querySelector('input[name="name"]').value = "Dark Roast Coffee";
  form.querySelector('input[name="quantity"]').value = "2";

  // Programmatic submit attempt while _writing is true must not dispatch any command
  form.dispatchEvent(new dom.window.Event("submit", {cancelable: true}));
  assert.equal(card.commands.length, 0, "Submit handler must reject when _writing is true");

  // A render while writing also disables every actual action button.
  const writingBody = document.createElement("div");
  renderShoppingSeries(card, writingBody);
  const buttons = Array.from(writingBody.querySelectorAll("button"));
  for (const btn of buttons) {
    assert.equal(btn.disabled, true);
  }
});

test("failed save keeps entered values and never adopts a newer revision silently", async () => {
  const card = createMockCard();
  card._shoppingSeriesFormOpen = true;
  card.command = async () => { card._actionError = "conflict"; };
  const body = document.createElement("div");
  renderShoppingSeries(card, body);
  const form = body.querySelector("form");
  form.querySelector('[name="name"]').value = "Preserve my draft";
  form.querySelector('[name="quantity"]').value = "4";
  form.dispatchEvent(new dom.window.Event("submit", {cancelable:true}));
  await new Promise(resolve=>setTimeout(resolve,0));
  assert.equal(card._shoppingSeriesFormOpen, true);
  const retried = document.createElement("div");
  renderShoppingSeries(card, retried);
  assert.equal(retried.querySelector('[name="name"]').value, "Preserve my draft");
  assert.equal(retried.querySelector('[name="quantity"]').value, "4");
  assert.equal(card._shoppingSeriesDraft.id, undefined);
});

test("retrying a new draft keeps the exact payload for transport idempotency", async () => {
  const card = createMockCard();
  card._shoppingSeriesFormOpen = true;
  card.command = async (action,payload) => {
    card.commands.push({action,payload});
    card._actionError="storage_error";
  };
  const body=document.createElement("div");
  renderShoppingSeries(card,body);
  body.querySelector('[name="name"]').value="Milk";
  body.querySelector("form").dispatchEvent(new dom.window.Event("submit",{cancelable:true}));
  await new Promise(resolve=>setTimeout(resolve,0));
  const retryBody=document.createElement("div");
  renderShoppingSeries(card,retryBody);
  retryBody.querySelector("form").dispatchEvent(new dom.window.Event("submit",{cancelable:true}));
  await new Promise(resolve=>setTimeout(resolve,0));
  assert.equal(card.commands.length,2);
  assert.equal(JSON.stringify(card.commands[0]),JSON.stringify(card.commands[1]));
  assert.equal(card.commands[0].payload.buyer,null);
});

test("month_day default is derived from household-local todayStr", () => {
  const card = createMockCard({
    isParent: true,
    timezone: "UTC",
  });
  card._shoppingSeriesFormOpen = true;

  const body = document.createElement("div");
  renderShoppingSeries(card, body);

  const form = body.querySelector("form.shopping-series-form");
  const startDate = form.querySelector('input[name="start_date"]').value;
  const monthDay = form.querySelector('input[name="month_day"]').value;

  const expectedDay = Number(startDate.split("-")[2]);
  assert.equal(Number(monthDay), expectedDay, "Default month_day must match start_date day in household timezone");
});
