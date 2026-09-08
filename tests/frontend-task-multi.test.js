import assert from "node:assert/strict";
import {test} from "node:test";
import {JSDOM} from "jsdom";

const dom = new JSDOM("<!doctype html><body></body>", {url: "http://localhost"});
for (const key of ["window", "document", "HTMLElement", "customElements", "CustomEvent", "FormData"]) {
  globalThis[key] = dom.window[key];
}

const {TASK_FORM_COPY, reconcileTaskFormRefresh, disposeTaskForm} = await import(
  "../custom_components/family_assistant/frontend/task-form.js"
);
const {PERSONAL_TASK_COPY} = await import(
  "../custom_components/family_assistant/frontend/personal-task-copy.js"
);
await import("../custom_components/family_assistant/frontend/family-assistant.js");

const tick = () => new Promise((r) => setTimeout(r, 0));

test("late prior-generation command must not clear the newer write lock", async () => {
  const card = make();
  delete card.command;
  const releases = [];
  card._hass.callWS = message => message.type.endsWith("/view")
    ? Promise.resolve(structuredClone(card._data))
    : new Promise(resolve => releases.push(resolve));
  const older = card.command("tasks.create", {title:"Older",assignee:"child1"}, "older-op");
  assert.equal(card._writing, true);
  card._generation++;
  card._writing = false;
  const newer = card.command("tasks.create", {title:"Newer",assignee:"child1"}, "newer-op");
  releases[0]({});
  await older;
  const newerStillWriting = card._writing;
  releases[1]({});
  await newer;
  assert.equal(newerStillWriting, true);
  assert.equal(card._writing, false);
});

function make(overrides = {}) {
  const card = document.createElement("family-tasks-card");
  card.setConfig({entry_id: "demo", language: "en", ...overrides.config});
  card._hass = {
    language: "en",
    config: {time_zone: "Pacific/Honolulu"},
    user: {id: "user-1"},
    ...overrides.hass,
  };
  card._data = {
    actor: "parent",
    role: "parent",
    settings: {name: "Demo", timezone: "Europe/Berlin", modules: ["tasks"]},
    tasks: [],
    members: [
      {id: "parent", name: "Parent", active: true, role: "parent", revision: 1},
      {id: "child1", name: "Child 1", active: true, role: "child", revision: 1},
      {id: "child2", name: "Child 2", active: true, role: "child", revision: 2},
      {id: "guest", name: "Guest", active: true, role: "guest", revision: 1},
      {id: "inactive", name: "Inactive", active: false, role: "child", revision: 1},
    ],
    ...overrides.data,
  };
  card._form = true;
  card.render();
  card.calls = [];
  card.command = async (action, payload, opId) => {
    card.calls.push({action, payload: structuredClone(payload), opId});
    if (!card._actionError) card._form = null;
  };
  return card;
}

const formOf = (card) => card.shadowRoot.querySelector("form[data-task-create]");

async function selectOneForReview(card) {
  input(card, "title", "Review boundary");
  const multi = formOf(card).elements.namedItem("multi");
  multi.checked = true;
  multi.dispatchEvent(new dom.window.Event("change", {bubbles: true}));
  const member = formOf(card).querySelector('[name="assignee_multi"][value="child1"]');
  member.checked = true;
  member.dispatchEvent(new dom.window.Event("change", {bubbles: true}));
}

test("review snapshots displayed wall time even when autofill has not emitted an input event", async () => {
  const card = make();
  await selectOneForReview(card);
  formOf(card).elements.namedItem("due_at").value = "2026-10-25T02:30";
  formOf(card).elements.namedItem("due_fold").value = "1";
  await submit(card);
  assert.equal(card._taskCreateDraft.reviewedDueAt, "2026-10-25T01:30:00.000Z");
  assert.equal(card._taskCreateDraft.due_at, "2026-10-25T02:30");
  assert.equal(card._taskCreateDraft.fold, "1");
  assert.ok(formOf(card).textContent.includes("2026-10-25 02:30"));
});

test("closing an unsent review requires a fresh confirmation when reopened", async () => {
  const card = make();
  await selectOneForReview(card);
  await submit(card);
  const confirm = formOf(card).elements.namedItem("confirm_batch");
  confirm.checked = true;
  confirm.dispatchEvent(new dom.window.Event("change", {bubbles: true}));
  card.shadowRoot.querySelector(".toolbar button").click();
  assert.equal(card._form, false);
  card.shadowRoot.querySelector(".toolbar button").click();
  assert.equal(formOf(card).elements.namedItem("confirm_batch").checked, false);
  assert.equal(formOf(card).querySelector('[type="submit"]').disabled, true);
  assert.equal(card.calls.length, 0);
});

function input(card, name, value) {
  const form = formOf(card);
  const field = form.elements.namedItem(name);
  if (!field) return null;
  field.value = value;
  field.dispatchEvent(new dom.window.Event("input", {bubbles: true}));
  return field;
}

async function submit(card) {
  formOf(card).dispatchEvent(new dom.window.Event("submit", {bubbles: true, cancelable: true}));
  await tick();
}

test("RU/UK copy parity and plain wording check", () => {
  for (const lang of ["ru", "uk"]) {
    assert.deepEqual(
      Object.keys(TASK_FORM_COPY[lang]).sort(),
      Object.keys(TASK_FORM_COPY.en).sort()
    );
  }
  assert.match(TASK_FORM_COPY.en.multiMemberHint, /separate task/i);
  assert.match(TASK_FORM_COPY.en.multiMemberHint, /not shared completion/i);
  assert.match(TASK_FORM_COPY.ru.multiMemberHint, /отдельная задача/i);
  assert.match(TASK_FORM_COPY.ru.multiMemberHint, /не общее выполнение/i);
  assert.match(TASK_FORM_COPY.uk.multiMemberHint, /окреме завдання/i);
  assert.match(TASK_FORM_COPY.uk.multiMemberHint, /не спільне виконання/i);
});

test("child role cannot use multi-member mode and is restricted to self", async () => {
  const card = make();
  card._data.actor = "child1";
  card._data.role = "child";
  card.render();

  const form = formOf(card);
  assert.equal(form.elements.namedItem("multi"), null);

  const assigneeSelect = form.elements.namedItem("assignee");
  assert.equal(assigneeSelect.options.length, 1);
  assert.equal(assigneeSelect.options[0].value, "child1");

  card._taskCreateDraft.multi = true;
  card.render();
  assert.equal(card._taskCreateDraft.multi, false);
});

test("personal toggle disables multi mode and resets to self without reports or penalties", async () => {
  const card = make();
  const form = formOf(card);

  const multiBox = form.elements.namedItem("multi");
  const personalBox = form.elements.namedItem("personal");
  assert.ok(multiBox);
  assert.ok(personalBox);

  multiBox.checked = true;
  multiBox.dispatchEvent(new dom.window.Event("change", {bubbles: true}));
  assert.equal(card._taskCreateDraft.multi, true);
  assert.equal(personalBox.disabled, true);
  assert.equal(personalBox.checked, false);

  personalBox.disabled = false;
  personalBox.checked = true;
  personalBox.dispatchEvent(new dom.window.Event("change", {bubbles: true}));

  assert.equal(card._taskCreateDraft.multi, false);
  assert.equal(multiBox.checked, false);
  assert.equal(multiBox.disabled, true);
  assert.equal(form.elements.namedItem("assignee").value, "parent");
  assert.equal(form.elements.namedItem("report_type").value, "none");
  assert.equal(card._taskCreateDraft.report_type, "none");
  assert.equal(form.elements.namedItem("grace_minutes").value, "0");
  assert.equal(form.elements.namedItem("penalty").value, "0");
});

test("multi mode has no auto-selection, excludes guest/inactive, and enforces 1..20 limit", async () => {
  const card = make();
  const form = formOf(card);

  const multiBox = form.elements.namedItem("multi");
  multiBox.checked = true;
  multiBox.dispatchEvent(new dom.window.Event("change", {bubbles: true}));

  assert.deepEqual(card._taskCreateDraft.selectedMembers, []);

  const boxes = form.querySelectorAll('input[name="assignee_multi"]');
  const values = [...boxes].map((b) => b.value);
  assert.deepEqual(values.sort(), ["child1", "child2", "parent"].sort());
  assert.ok(!values.includes("guest"));
  assert.ok(!values.includes("inactive"));

  input(card, "title", "Multi task");
  await submit(card);
  assert.equal(card.calls.length, 0);
  assert.equal(card._taskCreateDraft.stage, "edit");
  assert.equal(card._taskCreateDraft.error, "memberCountError");

  for (let i = 1; i <= 25; i++) {
    card._data.members.push({
      id: `extra_${i}`,
      name: `Extra ${i}`,
      active: true,
      role: "child",
      revision: 1,
    });
  }
  card.render();

  card._taskCreateDraft.selectedMembers = Array.from({length: 20}, (_, i) => `extra_${i + 1}`);
  const extraBox21 = formOf(card).querySelector('input[name="assignee_multi"][value="extra_21"]');
  assert.ok(extraBox21);
  extraBox21.checked = true;
  extraBox21.dispatchEvent(new dom.window.Event("change", {bubbles: true}));
  assert.equal(card._taskCreateDraft.selectedMembers.length, 20);
});

test("full named review requires explicit confirmation before atomic batch submission", async () => {
  const card = make();
  input(card, "title", "Clean the house");
  input(card, "checklist", "Living room\nKitchen");

  const multiBox = formOf(card).elements.namedItem("multi");
  multiBox.checked = true;
  multiBox.dispatchEvent(new dom.window.Event("change", {bubbles: true}));

  const m1 = formOf(card).querySelector('input[name="assignee_multi"][value="child1"]');
  const m2 = formOf(card).querySelector('input[name="assignee_multi"][value="child2"]');
  m1.checked = true;
  m1.dispatchEvent(new dom.window.Event("change", {bubbles: true}));
  m2.checked = true;
  m2.dispatchEvent(new dom.window.Event("change", {bubbles: true}));

  await submit(card);

  assert.equal(card.calls.length, 0);
  assert.equal(card._taskCreateDraft.stage, "review");
  assert.equal(card._taskCreateDraft.confirmed, false);

  const reviewForm = formOf(card);
  const textContent = reviewForm.textContent;
  assert.ok(textContent.includes("Clean the house"));
  assert.ok(textContent.includes("Child 1"));
  assert.ok(textContent.includes("Child 2"));
  assert.ok(textContent.includes("Living room"));
  assert.ok(textContent.includes("Kitchen"));

  const submitBtn = reviewForm.querySelector('button[type="submit"]');
  assert.equal(submitBtn.disabled, true);

  const confirmBox = reviewForm.elements.namedItem("confirm_batch");
  assert.ok(confirmBox);
  assert.equal(confirmBox.checked, false);

  confirmBox.checked = true;
  confirmBox.dispatchEvent(new dom.window.Event("change", {bubbles: true}));
  assert.equal(submitBtn.disabled, false);

  await submit(card);

  assert.equal(card.calls.length, 1);
  const call = card.calls[0];
  assert.equal(call.action, "batch");
  assert.equal(call.payload.commands.length, 2);

  assert.deepEqual(call.payload.commands[0], {
    action: "tasks.create",
    payload: {
      title: "Clean the house",
      assignee: "child1",
      assignee_revision: 1,
      report_type: "text",
      checklist: ["Living room", "Kitchen"],
      reminder_minutes: 60,
      grace_minutes: 30,
      penalty: 0,
    },
  });
  assert.deepEqual(call.payload.commands[1], {
    action: "tasks.create",
    payload: {
      title: "Clean the house",
      assignee: "child2",
      assignee_revision: 2,
      report_type: "text",
      checklist: ["Living room", "Kitchen"],
      reminder_minutes: 60,
      grace_minutes: 30,
      penalty: 0,
    },
  });
  assert.equal(card._taskCreateDraft, null);
});

test("lost ACK plus unrelated command: retrying retains own frozen operation_id and does not rebase", async () => {
  const card = make();
  delete card.command;
  let fail = true;
  card._hass.callWS = async (call) => {
    if (call.type === "family_assistant/view") return card._data;
    card.calls.push(structuredClone(call));
    if (fail) throw {code: "network_lost"};
    return {accepted: true};
  };

  input(card, "title", "Dishes");
  const multiBox = formOf(card).elements.namedItem("multi");
  multiBox.checked = true;
  multiBox.dispatchEvent(new dom.window.Event("change", {bubbles: true}));

  const m1 = formOf(card).querySelector('input[name="assignee_multi"][value="child1"]');
  m1.checked = true;
  m1.dispatchEvent(new dom.window.Event("change", {bubbles: true}));

  await submit(card);

  const confirmBox = formOf(card).elements.namedItem("confirm_batch");
  confirmBox.checked = true;
  confirmBox.dispatchEvent(new dom.window.Event("change", {bubbles: true}));

  await submit(card);

  assert.equal(card.calls.length, 1);
  const originalOpId = card.calls[0].operation_id;
  assert.ok(originalOpId);
  assert.equal(card._actionError, "network_lost");
  assert.ok(card._taskCreateDraft);
  assert.ok(card._taskCreateDraft.pending);

  card._pending = {fingerprint: "unrelated", id: "unrelated-op-id-999"};

  fail = false;
  await submit(card);

  assert.equal(card.calls.length, 2);
  assert.equal(card.calls[1].operation_id, originalOpId);
  assert.notEqual(card.calls[1].operation_id, "unrelated-op-id-999");
  assert.equal(card._taskCreateDraft, null);
});

test("honest uncertain close message allows dismissal without claim rollback", async () => {
  const card = make();
  delete card.command;
  card._hass.callWS = async (call) => {
    if (call.type === "family_assistant/view") return card._data;
    card.calls.push(structuredClone(call));
    throw {code: "uncertain_timeout"};
  };

  input(card, "title", "Laundry");
  const multiBox = formOf(card).elements.namedItem("multi");
  multiBox.checked = true;
  multiBox.dispatchEvent(new dom.window.Event("change", {bubbles: true}));
  const m1 = formOf(card).querySelector('input[name="assignee_multi"][value="child1"]');
  m1.checked = true;
  m1.dispatchEvent(new dom.window.Event("change", {bubbles: true}));

  await submit(card);
  const confirmBox = formOf(card).elements.namedItem("confirm_batch");
  confirmBox.checked = true;
  confirmBox.dispatchEvent(new dom.window.Event("change", {bubbles: true}));
  await submit(card);

  assert.ok(card._taskCreateDraft?.pending);
  const uncertainText = TASK_FORM_COPY.en.uncertainNotice;
  assert.ok(formOf(card).textContent.includes(uncertainText));

  const closeBtn = [...formOf(card).querySelectorAll("button")].find(
    (b) => b.textContent === TASK_FORM_COPY.en.closeWithoutRollback
  );
  assert.ok(closeBtn);
  closeBtn.click();
  await tick();

  assert.equal(card._taskCreateDraft, null);
  assert.equal(card.calls.length, 1);
});

test("do not clear a new draft on late response", async () => {
  const card = make();
  let resolveCommand;
  card.command = async (action, payload, opId) => {
    await new Promise((r) => {
      resolveCommand = r;
    });
  };

  input(card, "title", "Draft 1");
  const multiBox = formOf(card).elements.namedItem("multi");
  multiBox.checked = true;
  multiBox.dispatchEvent(new dom.window.Event("change", {bubbles: true}));
  const m1 = formOf(card).querySelector('input[name="assignee_multi"][value="child1"]');
  m1.checked = true;
  m1.dispatchEvent(new dom.window.Event("change", {bubbles: true}));
  await submit(card);
  const confirmBox = formOf(card).elements.namedItem("confirm_batch");
  confirmBox.checked = true;
  confirmBox.dispatchEvent(new dom.window.Event("change", {bubbles: true}));

  const promise = submit(card);

  card._taskCreateDraft = {
    title: "Brand new user draft",
    assignee: "child2",
    stage: "edit",
    multi: false,
  };

  resolveCommand();
  await promise;
  await tick();

  assert.ok(card._taskCreateDraft);
  assert.equal(card._taskCreateDraft.title, "Brand new user draft");
});

test("stale reviewed member revision invalidates review and requires fresh confirmation", async () => {
  const card = make();
  input(card, "title", "Paint fence");

  const multiBox = formOf(card).elements.namedItem("multi");
  multiBox.checked = true;
  multiBox.dispatchEvent(new dom.window.Event("change", {bubbles: true}));
  const m1 = formOf(card).querySelector('input[name="assignee_multi"][value="child1"]');
  m1.checked = true;
  m1.dispatchEvent(new dom.window.Event("change", {bubbles: true}));

  await submit(card);
  assert.equal(card._taskCreateDraft.stage, "review");

  card._data.members.find((m) => m.id === "child1").revision = 99;

  const confirmBox = formOf(card).elements.namedItem("confirm_batch");
  confirmBox.checked = true;
  confirmBox.dispatchEvent(new dom.window.Event("change", {bubbles: true}));

  await submit(card);

  assert.equal(card.calls.length, 0);
  assert.equal(card._taskCreateDraft.stage, "edit");
  assert.equal(card._taskCreateDraft.confirmed, false);
  assert.equal(card._taskCreateDraft.error, "staleError");
});

test("detached forms and changed role/epoch reject submission", async () => {
  const card = make();
  input(card, "title", "Test task");

  const staleForm = formOf(card);
  card.render();

  staleForm.dispatchEvent(new dom.window.Event("submit", {bubbles: true, cancelable: true}));
  await tick();
  assert.equal(card.calls.length, 0);

  const freshCard = make();
  input(freshCard, "title", "Scope test");
  freshCard._generation = 999;
  await submit(freshCard);
  assert.equal(freshCard.calls.length, 0);

  const roleCard = make();
  input(roleCard, "title", "Role test");
  roleCard._data.role = "guest";
  await submit(roleCard);
  assert.equal(roleCard.calls.length, 0);
});

test("reconcileTaskFormRefresh preserves focus and draft on unrelated changes but drops on scope changes", () => {
  const card = make();
  input(card, "title", "My draft task");
  input(card, "checklist", "Step 1");

  const previousData = structuredClone(card._data);
  card._data.tasks = [{id: "T1", title: "Unrelated task"}];

  const force1 = reconcileTaskFormRefresh(card, previousData);
  assert.equal(force1, false);
  assert.ok(card._taskCreateDraft);
  assert.equal(card._taskCreateDraft.title, "My draft task");

  card._data.members.find((m) => m.id === "parent").revision = 2;
  const force2 = reconcileTaskFormRefresh(card, previousData);
  assert.equal(force2, true);
  assert.equal(card._taskCreateDraft, null);
});
