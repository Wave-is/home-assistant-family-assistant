import assert from "node:assert/strict";
import { test } from "node:test";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><body></body>", { url: "http://localhost" });
for (const key of ["window", "document", "HTMLElement", "customElements", "CustomEvent", "FormData"]) {
  globalThis[key] = dom.window[key];
}

const { TASK_ITEM_COPY, renderTaskItem: renderItem, renderTaskArchive } = await import(
  "../custom_components/family_assistant/frontend/task-items.js"
);
function renderTaskItem(card,list,item) {
  const index=card._data.tasks.findIndex(t=>t.id===item.id);
  if(index<0)card._data.tasks.push(item);else card._data.tasks[index]=item;
  return renderItem(card,list,item);
}
// Import family-assistant.js to define custom element family-tasks-card
await import("../custom_components/family_assistant/frontend/family-assistant.js");

const tick = () => new Promise(resolve => setTimeout(resolve, 0));

const baseData = {
  revision: 1,
  actor: "parent_1",
  role: "parent",
  settings: { name: "Demo family", timezone: "Europe/Kyiv", modules: ["tasks"] },
  members: [
    { id: "parent_1", name: "Parent One", role: "parent", active: true },
    { id: "child_1", name: "Child One", role: "child", active: true },
    { id: "child_2", name: "Child Two", role: "child", active: true },
    { id: "adult_1", name: "Adult One", role: "adult", active: true },
    { id: "guest_1", name: "Guest One", role: "guest", active: true },
    { id: "inactive_1", name: "Inactive One", role: "parent", active: false }
  ],
  tasks: []
};

function createMockCard(overrides = {}) {
  const card = {
    _view: "tasks",
    _generation: 1,
    _writing: false,
    _actionError: null,
    _taskItemAction: null,
    _config: { language: "en" },
    _hass: { language: "en", config: { time_zone: "Europe/Kyiv" } },
    _data: JSON.parse(JSON.stringify(baseData)),
    get parent() {
      return ["owner", "parent"].includes(this._data?.role);
    },
    button(text, action, primary = false) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = text;
      if (primary) btn.className = "primary";
      btn.disabled = Boolean(this._writing);
      btn.addEventListener("click", action);
      return btn;
    },
    input(form, name, label, type = "text", value = "", required = true) {
      const wrap = document.createElement("label");
      wrap.textContent = label;
      const inp = document.createElement("input");
      Object.assign(inp, { name, type, value, required });
      wrap.append(inp);
      form.append(wrap);
      return inp;
    },
    render() {},
    async command(action, payload) {
      this.lastCommand = { action, payload };
    },
    ...overrides
  };
  return card;
}

test("TASK_ITEM_COPY parity across en, ru, and uk locales", () => {
  const enKeys = Object.keys(TASK_ITEM_COPY.en).sort();
  const ruKeys = Object.keys(TASK_ITEM_COPY.ru).sort();
  const ukKeys = Object.keys(TASK_ITEM_COPY.uk).sort();
  assert.deepEqual(ruKeys, enKeys);
  assert.deepEqual(ukKeys, enKeys);
  assert.ok(enKeys.length > 20);
});

test("School homework keeps lifecycle controls but cannot open generic edit", () => {
  const card = createMockCard();
  const list = document.createElement("ul");
  document.body.append(list);
  const item = {
    id: "TSCHOOL", revision: 1, title: "Homework", assignee: "child_1",
    creator: "parent_1", status: "assigned", managed_by: "school",
    checklist: [{ text: "Read chapter", done: false }],
  };
  renderTaskItem(card, list, item);
  const labels = [...list.querySelectorAll("button")].map(button => button.textContent);
  assert.ok(!labels.includes(TASK_ITEM_COPY.en.action_edit));
  assert.ok(labels.includes(TASK_ITEM_COPY.en.action_cancel));
  assert.match(list.textContent, /School card/);
  assert.equal(list.querySelector('input[type="checkbox"]').disabled, false);
  list.remove();
});

test("renderTaskItem displays friendly names and no raw member IDs", () => {
  const card = createMockCard();
  const ul = document.createElement("ul");
  const item = {
    id: "T123",
    revision: 1,
    title: "Clean bedroom",
    assignee: "child_1",
    creator: "parent_1",
    status: "assigned",
    due_at: "2026-09-07T12:00:00Z",
    checklist: [{ text: "Make bed", done: false }],
    deadline_policy: { reminder_minutes: 60, grace_minutes: 30, penalty: 0 }
  };

  renderTaskItem(card, ul, item);
  const text = ul.textContent;

  assert.match(text, /Clean bedroom/);
  assert.match(text, /Child One/);
  assert.match(text, /Assigned/);
  assert.match(text, /Make bed/);
  assert.doesNotMatch(text, /\bchild_1\b/);
  assert.doesNotMatch(text, /\bparent_1\b/);
});

test("checklist checkbox: active for assignee/parent; disabled for submitted, guest, and non-parent non-assignee", async () => {
  const card = createMockCard();
  const ul = document.createElement("ul");
  const item = {
    id: "T1",
    revision: 2,
    title: "Morning Routine",
    assignee: "parent_1",
    status: "in_progress",
    checklist: [
      { text: "Brush teeth", done: false },
      { text: "Pack bag", done: true }
    ]
  };

  renderTaskItem(card, ul, item);
  const checkboxes = ul.querySelectorAll('input[type="checkbox"]');
  assert.equal(checkboxes.length, 2);
  assert.equal(checkboxes[0].disabled, false);

  // Toggle first checkbox
  checkboxes[0].checked = true;
  checkboxes[0].dispatchEvent(new dom.window.Event("change"));

  assert.deepEqual(card.lastCommand, {
    action: "tasks.check",
    payload: {
      id: "T1",
      revision: 2,
      checklist_index: 0,
      done: true
    }
  });

  // When task is submitted, checklist is disabled
  const submittedItem = { ...item, status: "submitted" };
  ul.replaceChildren();
  renderTaskItem(card, ul, submittedItem);
  const submittedCheckboxes = ul.querySelectorAll('input[type="checkbox"]');
  assert.equal(submittedCheckboxes[0].disabled, true);

  // When actor is guest, checklist is disabled
  const guestCard = createMockCard({
    _data: {
      ...baseData,
      actor: "guest_1",
      role: "guest"
    }
  });
  ul.replaceChildren();
  renderTaskItem(guestCard, ul, item);
  const guestCheckboxes = ul.querySelectorAll('input[type="checkbox"]');
  assert.equal(guestCheckboxes[0].disabled, true);
});

test("non-parent creator cannot edit or cancel unless they are also the current assignee", () => {
  const childCard = createMockCard({
    _data: {
      ...baseData,
      actor: "child_1",
      role: "child"
    }
  });
  const ul = document.createElement("ul");

  // Child created task, but assigned to child_2: child_1 must NOT get edit or cancel buttons
  const otherAssigneeItem = {
    id: "T55",
    revision: 1,
    title: "Help with Homework",
    creator: "child_1",
    assignee: "child_2",
    status: "assigned"
  };

  renderTaskItem(childCard, ul, otherAssigneeItem);
  const buttons = Array.from(ul.querySelectorAll("button")).map(b => b.textContent);
  assert.ok(!buttons.includes("Edit task"));
  assert.ok(!buttons.includes("Cancel task"));

  // Child created task AND is current assignee: gets edit and cancel buttons
  const ownAssignedItem = {
    id: "T56",
    revision: 1,
    title: "Feed Pet",
    creator: "child_1",
    assignee: "child_1",
    status: "assigned"
  };
  ul.replaceChildren();
  renderTaskItem(childCard, ul, ownAssignedItem);
  const ownButtons = Array.from(ul.querySelectorAll("button")).map(b => b.textContent);
  assert.ok(ownButtons.includes("Edit task"));
  assert.ok(ownButtons.includes("Cancel task"));
});

test("report submission: text uses tasks.submit, photo opens the private media workflow", async () => {
  const card = createMockCard({
    _data: {
      ...baseData,
      actor: "child_1",
      role: "child"
    }
  });
  const ul = document.createElement("ul");
  const item = {
    id: "T2",
    revision: 3,
    title: "Math Homework",
    assignee: "child_1",
    creator: "child_1",
    status: "in_progress",
    report_type: "text"
  };

  renderTaskItem(card, ul, item);
  const reportBtn = Array.from(ul.querySelectorAll("button")).find(b => b.textContent === "Send report");
  reportBtn.click();

  assert.equal(card._taskItemAction.type, "submit_report");
  ul.replaceChildren();
  renderTaskItem(card, ul, item);

  const form = ul.querySelector("form");
  const input = form.querySelector('input[name="report"]');
  input.value = "Completed chapter 4 exercises 1-10";
  form.dispatchEvent(new dom.window.Event("submit"));

  assert.deepEqual(card.lastCommand, {
    action: "tasks.submit",
    payload: {
      id: "T2",
      revision: 3,
      report: "Completed chapter 4 exercises 1-10"
    }
  });

  // Photo reports have a separate verified-media workflow, never a text field.
  const photoItem = {
    id: "T3",
    revision: 1,
    title: "Clean Kitchen",
    assignee: "child_1",
    creator: "child_1",
    status: "in_progress",
    report_type: "photo"
  };
  photoItem.assignee_revision = 1;
  card._entry = "synthetic-entry";
  for (const value of card._data.members) value.revision = 1;
  card._taskItemAction = null;
  ul.replaceChildren();
  renderTaskItem(card, ul, photoItem);

  assert.ok(ul.querySelector('input[type="file"][name="photo"]'));
  assert.equal(ul.querySelector('input[name="photo"]').accept, "image/jpeg,image/png,image/webp");
  assert.doesNotMatch(ul.textContent, /Photo reports are not supported yet/);
  assert.equal(ul.querySelector('input[name="report"]'), null);
});

test("parent controls: complete, request changes with note, cancel, and archive with explicit review", async () => {
  const card = createMockCard();
  const ul = document.createElement("ul");
  const item = {
    id: "T4",
    revision: 5,
    title: "Vacuum Hallway",
    assignee: "child_1",
    creator: "parent_1",
    status: "submitted",
    report: "Done hallway"
  };

  renderTaskItem(card, ul, item);
  const buttons = Array.from(ul.querySelectorAll("button")).map(b => b.textContent);
  assert.ok(buttons.includes("Confirm done"));
  assert.ok(buttons.includes("Request changes"));
  assert.ok(buttons.includes("Cancel task"));
  assert.ok(buttons.includes("Archive"));

  // Request changes form flow
  const reqBtn = Array.from(ul.querySelectorAll("button")).find(b => b.textContent === "Request changes");
  reqBtn.click();
  assert.equal(card._taskItemAction.type, "request_changes");

  ul.replaceChildren();
  renderTaskItem(card, ul, item);
  const form = ul.querySelector("form");
  const noteInput = form.querySelector('input[name="note"]');
  noteInput.value = "Missed the rug near the entrance.";
  form.dispatchEvent(new dom.window.Event("submit"));

  assert.deepEqual(card.lastCommand, {
    action: "tasks.request_changes",
    payload: {
      id: "T4",
      revision: 5,
      note: "Missed the rug near the entrance."
    }
  });

  // Archive review confirmation
  card._taskItemAction = null;
  ul.replaceChildren();
  renderTaskItem(card, ul, item);
  const archiveBtn = Array.from(ul.querySelectorAll("button")).find(b => b.textContent === "Archive");
  archiveBtn.click();

  assert.equal(card._taskItemAction.type, "confirm_archive");
  ul.replaceChildren();
  renderTaskItem(card, ul, item);
  assert.match(ul.textContent, /Archiving permanently files this task in history/);

  const confirmArchiveBtn = Array.from(ul.querySelectorAll("button")).find(b => b.textContent === "Confirm archive");
  confirmArchiveBtn.click();

  assert.deepEqual(card.lastCommand, {
    action: "tasks.archive",
    payload: { id: "T4", revision: 5 }
  });
});

test("inactive current assignee is preserved and rendered explicitly in assignee dropdown", () => {
  const card = createMockCard();
  const ul = document.createElement("ul");
  const item = {
    id: "T77",
    revision: 1,
    title: "Old Task",
    assignee: "inactive_1",
    creator: "parent_1",
    status: "assigned",
    deadline_policy: { reminder_minutes: 60, grace_minutes: 30, penalty: 0 }
  };

  renderTaskItem(card, ul, item);
  const editBtn = Array.from(ul.querySelectorAll("button")).find(b => b.textContent === "Edit task");
  editBtn.click();

  ul.replaceChildren();
  renderTaskItem(card, ul, item);

  const form = ul.querySelector("form");
  const assigneeSelect = form.querySelector('select[name="assignee"]');
  assert.ok(assigneeSelect);

  // Selected value must be inactive_1, not silently defaulted to first active member
  assert.equal(assigneeSelect.value, "inactive_1");
  const inactiveOption = Array.from(assigneeSelect.querySelectorAll("option")).find(o => o.value === "inactive_1");
  assert.ok(inactiveOption);
  assert.equal(inactiveOption.selected, true);
});

test("daylight saving time fold handling: explicit placeholder, prevents silent default, allows selecting fold of original wall time", () => {
  const card = createMockCard();
  const ul = document.createElement("ul");
  // Europe/Kyiv autumn transition on 2026-10-25 repeats 03:00 to 03:59
  // Candidates are UTC-sorted: earlier +03:00, then later +02:00.
  const initialIso = "2026-10-25T01:30:00.000Z";
  const item = {
    id: "T8",
    revision: 1,
    title: "DST Task",
    assignee: "child_1",
    creator: "parent_1",
    status: "assigned",
    due_at: initialIso,
    deadline_policy: { reminder_minutes: 60, grace_minutes: 30, penalty: 0 }
  };

  renderTaskItem(card, ul, item);
  const editBtn = Array.from(ul.querySelectorAll("button")).find(b => b.textContent === "Edit task");
  editBtn.click();

  ul.replaceChildren();
  renderTaskItem(card, ul, item);
  const form = ul.querySelector("form");
  const dueInput = form.querySelector('input[name="due_at"]');
  const foldSelect = form.querySelector('select[name="due_fold"]');

  // 1. Untouched original fold: saving directly preserves exact initial ISO
  form.dispatchEvent(new dom.window.Event("submit"));
  assert.equal(card.lastCommand.payload.due_at, initialIso);

  // 2. User intentionally selects the earlier occurrence of original wall time.
  foldSelect.value = "0";
  foldSelect.dispatchEvent(new dom.window.Event("change"));
  form.dispatchEvent(new dom.window.Event("submit"));
  assert.equal(card.lastCommand.payload.due_at, "2026-10-25T00:30:00.000Z");

  // 3. User types a NEW ambiguous wall time: fold is reset to placeholder and cannot silently submit
  dueInput.value = "2026-10-25T03:45";
  dueInput.dispatchEvent(new dom.window.Event("input"));
  assert.equal(foldSelect.value, "");

  // Submitting without selecting fold is blocked
  card.lastCommand = null;
  form.dispatchEvent(new dom.window.Event("submit"));
  assert.equal(card.lastCommand, null);
  assert.match(ul.textContent, /This time occurs twice due to daylight saving time/);

  // Selecting fold 0 allows submission
  foldSelect.value = "0";
  foldSelect.dispatchEvent(new dom.window.Event("change"));
  form.dispatchEvent(new dom.window.Event("submit"));
  assert.ok(card.lastCommand);
  assert.equal(card.lastCommand.payload.due_at, "2026-10-25T00:45:00.000Z");

  // Spring forward gap error check
  dueInput.value = "2026-03-29T03:30";
  dueInput.dispatchEvent(new dom.window.Event("input"));
  assert.match(ul.textContent, /This time does not exist due to daylight saving time/);
});

test("stale form detection: rejects stale form when revision, status, or permissions change; does not silently upgrade", () => {
  const card = createMockCard();
  const ul = document.createElement("ul");
  const item = {
    id: "T9",
    revision: 3,
    title: "Stale Task",
    assignee: "child_1",
    creator: "parent_1",
    status: "assigned",
    deadline_policy: { reminder_minutes: 60, grace_minutes: 30, penalty: 0 }
  };

  renderTaskItem(card, ul, item);
  const editBtn = Array.from(ul.querySelectorAll("button")).find(b => b.textContent === "Edit task");
  editBtn.click();

  // Task on server has now been updated to revision 4
  const updatedItem = { ...item, revision: 4 };
  ul.replaceChildren();
  renderTaskItem(card, ul, updatedItem);

  // Stale notice should be displayed instead of active edit form
  assert.match(ul.textContent, /Task was updated or permissions changed/);
  assert.equal(ul.querySelector('input[name="title"]'), null);

  // If user permissions are revoked to guest
  const guestCard = createMockCard({
    _data: {
      ...baseData,
      role: "guest"
    },
    _taskItemAction: {
      type: "edit",
      itemId: "T9",
      targetRevision: 3,
      targetStatus: "assigned"
    }
  });
  ul.replaceChildren();
  renderTaskItem(guestCard, ul, item);
  assert.match(ul.textContent, /Task was updated or permissions changed/);
});

test("deadline policy respects domain ranges (reminder 0..10080, grace 0..1440, penalty -10..0)", () => {
  const card = createMockCard();
  const ul = document.createElement("ul");
  const item = {
    id: "T10",
    revision: 1,
    title: "Policy Task",
    assignee: "child_1",
    creator: "parent_1",
    status: "assigned",
    deadline_policy: { reminder_minutes: 120, grace_minutes: 45, penalty: -2 }
  };

  renderTaskItem(card, ul, item);
  const editBtn = Array.from(ul.querySelectorAll("button")).find(b => b.textContent === "Edit task");
  editBtn.click();

  ul.replaceChildren();
  renderTaskItem(card, ul, item);

  const form = ul.querySelector("form");
  const reminderInput = form.querySelector('input[name="reminder_minutes"]');
  const graceInput = form.querySelector('input[name="grace_minutes"]');
  const penaltyInput = form.querySelector('input[name="penalty"]');

  assert.equal(reminderInput.min, "0");
  assert.equal(reminderInput.max, "10080");
  assert.equal(graceInput.min, "0");
  assert.equal(graceInput.max, "1440");
  assert.equal(penaltyInput.min, "-10");
  assert.equal(penaltyInput.max, "0");
});

test("focused editor rejects newly fetched revisions without needing DOM rerender", () => {
  const card=createMockCard(),ul=document.createElement("ul");
  const item={id:"Tfresh",revision:1,title:"Task",status:"assigned",assignee:"child_1",creator:"parent_1"};
  renderTaskItem(card,ul,item);
  [...ul.querySelectorAll("button")].find(b=>b.textContent==="Edit task").click();
  ul.replaceChildren();renderTaskItem(card,ul,item);
  card._data.tasks=[{...item,revision:2,title:"New server title"}];
  ul.querySelector("form").dispatchEvent(new dom.window.Event("submit"));
  assert.equal(card.lastCommand,undefined);
});

test("editing title retains exact deadline seconds and omits unchanged inactive assignee", () => {
  const card=createMockCard(),ul=document.createElement("ul");
  const item={id:"Texact",revision:1,title:"Task",status:"in_progress",assignee:"inactive_1",creator:"parent_1",due_at:"2026-09-07T13:15:47.123456+03:00"};
  renderTaskItem(card,ul,item);
  [...ul.querySelectorAll("button")].find(b=>b.textContent==="Edit task").click();
  ul.replaceChildren();renderTaskItem(card,ul,item);
  ul.querySelector('input[name="title"]').value="Edited";
  ul.querySelector("form").dispatchEvent(new dom.window.Event("submit"));
  assert.equal(card.lastCommand.payload.due_at,item.due_at);
  assert.equal("assignee" in card.lastCommand.payload,false);
});

test("renderTaskArchive renders collapsed details containing final tasks", () => {
  const card = createMockCard();
  card._data.tasks = [
    { id: "T11", revision: 1, title: "Active 1", status: "assigned" },
    { id: "T12", revision: 2, title: "Completed 1", status: "completed" },
    { id: "T13", revision: 3, title: "Cancelled 1", status: "cancelled" },
    { id: "T14", revision: 4, title: "Archived 1", status: "archived" }
  ];
  const body = document.createElement("div");

  const details = renderTaskArchive(card, body);
  assert.equal(details.tagName, "DETAILS");
  assert.match(details.querySelector("summary").textContent, /Archived & Completed Tasks/);

  const text = details.textContent;
  assert.match(text, /Completed 1/);
  assert.match(text, /Cancelled 1/);
  assert.match(text, /Archived 1/);
  assert.doesNotMatch(text, /Active 1/);
});

test("custom element family-tasks-card integration test", async () => {
  const cardEl = document.createElement("family-tasks-card");
  cardEl.setConfig({ entry_id: "demo_household" });

  const tasksData = {
    ...baseData,
    tasks: [
      {
        id: "T100",
        revision: 1,
        title: "Integration Task",
        assignee: "child_1",
        creator: "parent_1",
        status: "assigned",
        due_at: "2026-09-08T10:00:00Z"
      }
    ]
  };

  cardEl.hass = {
    language: "en",
    callWS: async (msg) => {
      if (msg.type === "family_assistant/view") {
        return tasksData;
      }
      return {};
    }
  };

  await tick();
  assert.ok(cardEl.shadowRoot);
  assert.match(cardEl.shadowRoot.textContent, /Integration Task/);
  assert.match(cardEl.shadowRoot.textContent, /Child One/);
});
