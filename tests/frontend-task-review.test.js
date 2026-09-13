import assert from "node:assert/strict";
import {test} from "node:test";
import {JSDOM} from "jsdom";

const dom = new JSDOM("<!doctype html><body></body>", {url: "http://localhost"});
for (const key of ["window", "document", "HTMLElement", "customElements", "CustomEvent", "FormData"]) {
  globalThis[key] = dom.window[key];
}
const {TASK_FORM_COPY} = await import("../custom_components/family_assistant/frontend/task-form.js");
const {TASK_ITEM_COPY} = await import("../custom_components/family_assistant/frontend/task-items.js");
await import("../custom_components/family_assistant/frontend/family-assistant.js");
const tick = () => new Promise(resolve => setTimeout(resolve, 0));

function make({role = "parent", language = "en", task = null} = {}) {
  const card = document.createElement("family-tasks-card");
  card.setConfig({entry_id: "synthetic", language});
  card._hass = {language, config: {time_zone: "UTC"}, user: {id: "test-user"}};
  card._data = {
    actor: role === "child" ? "child" : "parent", role,
    settings: {name: "Synthetic family", timezone: "UTC", modules: ["tasks"]},
    members: [
      {id: "parent", name: "Parent", active: true, role: "parent", revision: 1},
      {id: "child", name: "Child", active: true, role: "child", revision: 1},
      {id: "sibling", name: "Sibling", active: true, role: "child", revision: 1},
    ],
    tasks: task ? [task] : [],
  };
  card._form = !task;
  card.calls = [];
  card.command = async (action, payload, operation) => {
    card.calls.push({action, payload: structuredClone(payload), operation});
  };
  card.render();
  return card;
}

const formOf = card => card.shadowRoot.querySelector("form");
function input(card, name, value) {
  const field = formOf(card).elements.namedItem(name);
  field.value = value;
  field.dispatchEvent(new dom.window.Event("input", {bubbles: true}));
  return field;
}
function toggle(card, name, checked = true) {
  const field = formOf(card).elements.namedItem(name);
  field.checked = checked;
  field.dispatchEvent(new dom.window.Event("change", {bubbles: true}));
}
async function submit(card) {
  formOf(card).dispatchEvent(new dom.window.Event("submit", {bubbles: true, cancelable: true}));
  await tick();
}
function task(extra = {}) {
  return {
    id: "T000001", revision: 1, title: "Synthetic work", assignee: "child", creator: "parent",
    status: "assigned", report_type: "text", report: null, due_at: null, checklist: [],
    deadline_policy: {reminder_minutes: 60, grace_minutes: 30, penalty: 0}, ...extra,
  };
}
function edit(card, language = "en") {
  [...card.shadowRoot.querySelectorAll("button")]
    .find(button => button.textContent === TASK_ITEM_COPY[language].action_edit).click();
}

for (const language of ["en", "ru", "uk"]) {
  test(`review policy create/edit field is localized and has actual payload (${language})`, async () => {
    const card = make({language});
    assert.ok(formOf(card).textContent.includes(TASK_FORM_COPY[language].reviewMinutes));
    const field = input(card, "review_minutes", "45");
    assert.equal(field.min, "0");
    assert.equal(field.max, "10080");
    assert.equal(field.step, "1");
    input(card, "title", "Review this");
    input(card, "assignee", "child");
    await submit(card);
    assert.equal(card.calls[0].action, "tasks.create");
    assert.equal(card.calls[0].payload.review_minutes, 45);
    assert.equal("due_at" in card.calls[0].payload, false);

    const editor = make({language, task: task({review_minutes: 45})});
    edit(editor, language);
    assert.equal(formOf(editor).elements.review_minutes.value, "45");
    assert.ok(formOf(editor).textContent.includes(TASK_ITEM_COPY[language].label_review_minutes));
    input(editor, "review_minutes", "0");
    await submit(editor);
    assert.equal(editor.calls[0].action, "tasks.revise");
    assert.equal(editor.calls[0].payload.review_minutes, 0);
  });
}

test("omitted policy stays omitted in new task and untouched existing editor", async () => {
  const card = make();
  input(card, "title", "Default off");
  assert.equal(formOf(card).elements.review_minutes.value, "0");
  await submit(card);
  assert.equal("review_minutes" in card.calls[0].payload, false);
  const editor = make({task: task()});
  edit(editor);
  await submit(editor);
  assert.equal("review_minutes" in editor.calls[0].payload, false);
});

test("personal task and child never submit reviewer policy", async () => {
  const personal = make();
  input(personal, "title", "Private reminder");
  input(personal, "review_minutes", "90");
  toggle(personal, "personal");
  assert.equal(formOf(personal).elements.review_minutes.disabled, true);
  assert.equal(formOf(personal).elements.review_minutes.value, "0");
  await submit(personal);
  assert.equal("review_minutes" in personal.calls[0].payload, false);
  const child = make({role: "child"});
  assert.equal(formOf(child).elements.namedItem("review_minutes"), null);
  input(child, "title", "My own work");
  await submit(child);
  assert.equal("review_minutes" in child.calls[0].payload, false);
  const editor = make({role: "child", task: task({creator: "child", review_minutes: 60})});
  edit(editor);
  assert.equal(formOf(editor).elements.namedItem("review_minutes"), null);
  await submit(editor);
  assert.equal("review_minutes" in editor.calls[0].payload, false);
});

test("invalid intervals do not submit and a frozen retry retains the original policy", async () => {
  const card = make();
  input(card, "title", "Bounded review");
  for (const value of ["-1", "10081", "1.5"]) {
    input(card, "review_minutes", value);
    await submit(card);
  }
  assert.equal(card.calls.length, 0);
  input(card, "review_minutes", "60");
  card.command = async (action, payload, operation) => {
    card.calls.push({action, payload: structuredClone(payload), operation});
    card._actionError = "unconfirmed";
  };
  await submit(card);
  assert.equal(formOf(card).elements.review_minutes.disabled, true);
  input(card, "review_minutes", "999");
  await submit(card);
  assert.deepEqual(card.calls[0], card.calls[1]);
  assert.equal(card.calls[1].payload.review_minutes, 60);
});

test("multi-assignee review shows and freezes the chosen review interval for each task", async () => {
  const card = make();
  input(card, "title", "Two reports");
  input(card, "review_minutes", "120");
  toggle(card, "multi");
  for (const id of ["child", "sibling"]) {
    const box = formOf(card).querySelector(`[name="assignee_multi"][value="${id}"]`);
    box.checked = true;
    box.dispatchEvent(new dom.window.Event("change", {bubbles: true}));
  }
  await submit(card);
  assert.ok(formOf(card).textContent.includes(`${TASK_FORM_COPY.en.reviewMinutes}: 120`));
  toggle(card, "confirm_batch");
  await submit(card);
  assert.equal(card.calls[0].action, "batch");
  assert.equal(card.calls[0].payload.commands.length, 2);
  for (const command of card.calls[0].payload.commands) {
    assert.equal(command.action, "tasks.create");
    assert.equal(command.payload.review_minutes, 120);
  }
});
