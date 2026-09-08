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
]) {
  globalThis[key] = dom.window[key];
}

const { FamilyCard } =
  await import("../custom_components/family_assistant/frontend/family-assistant.js");
const { renderTaskBatch, reconcileTaskBatchRefresh, disposeTaskBatch } =
  await import("../custom_components/family_assistant/frontend/task-batch-view.js");
const { TASK_BATCH_COPY } =
  await import("../custom_components/family_assistant/frontend/task-batch-copy.js");

const clone = (v) => structuredClone(v);
const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

async function eventually(predicate) {
  for (let index = 0; index < 100; index += 1) {
    if (predicate()) return;
    await tick();
  }
  assert.fail("condition was not reached in time");
}

function clickText(root, text) {
  const button = [...root.querySelectorAll("button")].find(
    (item) => item.textContent.trim() === text.trim()
  );
  assert.ok(button, `button with text "${text}"`);
  button.click();
  return button;
}

function check(root, selector, checked = true) {
  const control = root.querySelector(selector);
  assert.ok(control, `control ${selector}`);
  control.checked = checked;
  control.dispatchEvent(new window.Event("change", { bubbles: true }));
  return control;
}

function setValue(root, selector, value) {
  const control = root.querySelector(selector);
  assert.ok(control, `control ${selector}`);
  control.value = value;
  control.dispatchEvent(new window.Event("change", { bubbles: true }));
  return control;
}

const MEMBERS = [
  { id: "parent_1", name: "Parent One", role: "parent", active: true, revision: 2 },
  { id: "owner_1", name: "Owner One", role: "owner", active: true, revision: 3 },
  { id: "child_1", name: "Child One", role: "child", active: true, revision: 4 },
  { id: "child_2", name: "Child Two", role: "child", active: true, revision: 5 },
  { id: "guest_1", name: "Guest One", role: "guest", active: true, revision: 1 },
  { id: "inactive_1", name: "Inactive One", role: "parent", active: false, revision: 2 },
];

function sampleTasks() {
  return [
    { id: "T101", revision: 1, title: "Clean room", status: "assigned", assignee: "child_1" },
    { id: "T102", revision: 1, title: "Do homework", status: "in_progress", assignee: "child_2" },
    { id: "T103", revision: 2, title: "Wash dishes", status: "submitted", assignee: "child_1" },
    { id: "T104", revision: 1, title: "Take out trash", status: "completed", assignee: "child_1" },
    { id: "T105", revision: 3, title: "Walk dog", status: "cancelled", assignee: "child_2" },
    { id: "T106", revision: 1, title: "Feed cat", status: "archived", assignee: "child_1" },
  ];
}

function stateFor({ role = "parent", actor = "parent_1" } = {}) {
  return {
    revision: 1,
    actor,
    role,
    settings: {
      name: "Family Test",
      timezone: "Europe/Kyiv",
      modules: ["tasks"],
    },
    members: clone(MEMBERS),
    tasks: sampleTasks(),
    task_series: [],
    proposals: [],
  };
}

async function setup(t, { role = "parent", actor = "parent_1", language = "en", real = false } = {}) {
  const state = stateFor({ role, actor });
  const calls = [];
  const receipts = new Map();
  let failure = null;

  const hass = {
    user: { id: `ha-${state.actor}` },
    language,
    callWS: async (message) => {
      if (message.type === "family_assistant/view") return clone(state);
      calls.push(clone(message));
      if (receipts.has(message.operation_id)) {
        return clone(receipts.get(message.operation_id));
      }
      if (failure === "before") {
        failure = null;
        const err = new Error("network_down_before");
        err.code = "network";
        throw err;
      }
      let receipt;
      if (message.action === "batch") {
        receipt = {
          items: message.payload.commands.map((cmd) => {
            const task = state.tasks.find((t) => t.id === cmd.payload.id);
            if (task) {
              task.revision += 1;
              if (cmd.action === "tasks.complete") task.status = "completed";
              else if (cmd.action === "tasks.cancel") task.status = "cancelled";
              else if (cmd.action === "tasks.archive") task.status = "archived";
              return clone(task);
            }
            return { id: cmd.payload.id, revision: cmd.payload.revision + 1 };
          }),
        };
      } else {
        receipt = { accepted: true };
      }
      receipts.set(message.operation_id, receipt);
      if (failure === "after") {
        failure = null;
        const err = new Error("network_down_after");
        err.code = "network";
        throw err;
      }
      return clone(receipt);
    },
  };

  const card = document.createElement(real ? "family-tasks-card" : "family-assistant-card");
  assert.ok(card instanceof FamilyCard);
  card._config = { language };
  card._entry = "entry-test-1";
  card._generation = 1;
  card._data = state;
  card._hass = hass;
  card._view = "tasks";
  card._loading = false;
  card._writing = false;
  card._form = null;
  card._taskCreateDraft = null;
  card._taskMediaDraft = null;
  card._taskSeriesDraft = null;
  card._taskBatchDraft = null;
  card._actionError = null;

  const render = real
    ? () => card.render()
    : () => {
        card.shadowRoot.replaceChildren();
        const body = document.createElement("div");
        card.shadowRoot.append(body);
        renderTaskBatch(card, body);
      };

  if (!real) card.render = render;
  document.body.append(card);
  render();

  t.after(() => {
    clearInterval(card._timer);
    disposeTaskBatch(card);
    card.remove();
  });

  return {
    card,
    state,
    calls,
    setFailure(v) {
      failure = v;
    },
    render,
  };
}

// 1. Copy Parity Test across EN, RU, UK
test("parity: TASK_BATCH_COPY has exact key parity across en, ru, and uk", () => {
  const enKeys = Object.keys(TASK_BATCH_COPY.en).sort();
  const ruKeys = Object.keys(TASK_BATCH_COPY.ru).sort();
  const ukKeys = Object.keys(TASK_BATCH_COPY.uk).sort();
  assert.deepEqual(ruKeys, enKeys, "RU keys must match EN keys");
  assert.deepEqual(ukKeys, enKeys, "UK keys must match EN keys");
  assert.ok(enKeys.length >= 30, "Must have comprehensive key coverage");
});

// 2. Confirmation-Only Workflow Test
test("confirmation-only: no command sent before confirmation, and single batch command submitted after confirmation", async (t) => {
  const { card, calls } = await setup(t);
  const c = TASK_BATCH_COPY.en;

  // Open batch panel
  clickText(card.shadowRoot, c.startBatch);
  assert.ok(card._taskBatchDraft, "Draft must be open");
  assert.equal(card._taskBatchDraft.stage, "select");

  // Select two nonterminal tasks (T101 and T102)
  check(card.shadowRoot, 'input[value="T101"]', true);
  check(card.shadowRoot, 'input[value="T102"]', true);
  assert.deepEqual(card._taskBatchDraft.selectedIds.sort(), ["T101", "T102"]);

  // Proceed to review
  clickText(card.shadowRoot, c.reviewBatch);
  assert.equal(card._taskBatchDraft.stage, "review");
  assert.equal(card._taskBatchDraft.confirmed, false);
  assert.equal(calls.length, 0, "No websocket command should be sent yet");

  // Apply button should be disabled when confirm is false
  const submitBtn = card.shadowRoot.querySelector('button.primary');
  assert.ok(submitBtn.disabled, "Submit button must be disabled before confirmation");

  // Confirm
  check(card.shadowRoot, 'input[name="confirm"]', true);
  assert.equal(card._taskBatchDraft.confirmed, true);
  const activeSubmitBtn = card.shadowRoot.querySelector("button.primary");
  assert.equal(activeSubmitBtn.disabled, false);

  // Submit
  clickText(card.shadowRoot, c.applyBatch);

  await eventually(() => calls.length === 1 && card._taskBatchDraft === null);

  assert.equal(calls.length, 1);
  const call = calls[0];
  assert.equal(call.action, "batch");
  assert.equal(typeof call.operation_id, "string");
  assert.deepEqual(call.payload, {
    commands: [
      { action: "tasks.complete", payload: { id: "T101", revision: 1 } },
      { action: "tasks.complete", payload: { id: "T102", revision: 1 } },
    ],
  });
});

// 3. 20-Limit Enforcement Test
test("20limit: restricts selection to at most 20 tasks, displays count, and disables excess", async (t) => {
  const { card, state } = await setup(t);
  const c = TASK_BATCH_COPY.en;

  // Populate state with 25 eligible tasks
  state.tasks = Array.from({ length: 25 }, (_, i) => ({
    id: `T${200 + i}`,
    revision: 1,
    title: `Task ${i + 1}`,
    status: "assigned",
    assignee: "child_1",
  }));
  card.render();

  clickText(card.shadowRoot, c.startBatch);
  const draft = card._taskBatchDraft;

  // Select 20 tasks
  for (let i = 0; i < 20; i += 1) {
    check(card.shadowRoot, `input[value="T${200 + i}"]`, true);
  }
  assert.equal(draft.selectedIds.length, 20);
  assert.match(card.shadowRoot.textContent, /Selected:\s*20\s*\/\s*20/);
  assert.match(card.shadowRoot.textContent, new RegExp(c.maxLimitNotice));

  // 21st checkbox should be disabled
  const extraCheckbox = card.shadowRoot.querySelector('input[value="T220"]');
  assert.ok(extraCheckbox.disabled, "21st checkbox must be disabled once 20 are selected");

  // Attempting to select 21st manually should not increase selected count
  extraCheckbox.checked = true;
  extraCheckbox.dispatchEvent(new window.Event("change", { bubbles: true }));
  assert.equal(draft.selectedIds.length, 20);
});

// 4. Mixed Invalid Filtering Test
test("mixed invalid: excludes personal, managed_by, guests, inactive assignees, malformed IDs/revisions, and wrong statuses", async (t) => {
  const { card, state } = await setup(t);
  const c = TASK_BATCH_COPY.en;

  state.tasks = [
    // Valid non-terminal
    { id: "T_VALID1", revision: 1, title: "Valid Task", status: "assigned", assignee: "child_1" },
    // Invalid: personal
    { id: "T_PERS1", revision: 1, title: "Personal Task 1", status: "assigned", assignee: "child_1", delivery_scope: "personal" },
    { id: "T_PERS2", revision: 1, title: "Personal Task 2", status: "assigned", assignee: "child_1", personal: true },
    // Invalid: managed_by
    { id: "T_MGD", revision: 1, title: "School Task", status: "assigned", assignee: "child_1", managed_by: "school" },
    { id: "T_PRIVATE", revision: 1, title: "Maintenance fault", status: "assigned", assignee: "child_1", delivery_scope: "private" },
    { id: "T_SOURCE", revision: 1, title: "Maintenance service", status: "assigned", assignee: "child_1", source: {kind: "maintenance_service"} },
    // Invalid: guest assignee
    { id: "T_GUEST", revision: 1, title: "Guest Task", status: "assigned", assignee: "guest_1" },
    // Invalid: inactive assignee
    { id: "T_INACT", revision: 1, title: "Inactive Task", status: "assigned", assignee: "inactive_1" },
    // Invalid: unknown assignee
    { id: "T_UNK", revision: 1, title: "Unknown Assignee", status: "assigned", assignee: "non_existent" },
    // Invalid: malformed ID
    { id: "", revision: 1, title: "Empty ID", status: "assigned", assignee: "child_1" },
    { id: "   ", revision: 1, title: "Blank ID", status: "assigned", assignee: "child_1" },
    // Invalid: malformed revision
    { id: "T_REV0", revision: 0, title: "Zero Rev", status: "assigned", assignee: "child_1" },
    { id: "T_REVNEG", revision: -2, title: "Neg Rev", status: "assigned", assignee: "child_1" },
    { id: "T_REVSTR", revision: "1", title: "Str Rev", status: "assigned", assignee: "child_1" },
    // Terminal tasks: invalid for complete/cancel, valid for archive
    { id: "T_COMP", revision: 1, title: "Completed Task", status: "completed", assignee: "child_1" },
    { id: "T_CANC", revision: 1, title: "Cancelled Task", status: "cancelled", assignee: "child_2" },
    { id: "T_ARCH", revision: 1, title: "Archived Task", status: "archived", assignee: "child_1" },
  ];
  card.render();

  clickText(card.shadowRoot, c.startBatch);

  // Default action is tasks.complete -> only T_VALID1 should be eligible
  const completeEligibleCheckboxes = [...card.shadowRoot.querySelectorAll('input[name="task_select"]')];
  const completeEligibleValues = completeEligibleCheckboxes.map((b) => b.value);
  assert.deepEqual(completeEligibleValues, ["T_VALID1"]);

  // Switch action to tasks.archive -> only T_COMP and T_CANC should be eligible
  setValue(card.shadowRoot, 'select[name="batch_action"]', "tasks.archive");
  const archiveEligibleCheckboxes = [...card.shadowRoot.querySelectorAll('input[name="task_select"]')];
  const archiveEligibleValues = archiveEligibleCheckboxes.map((b) => b.value).sort();
  assert.deepEqual(archiveEligibleValues, ["T_CANC", "T_COMP"]);
});

// 5. Stale First-Send Review Test (Task and Assignee Revision Drift)
test("stale: first-send review requires reselection when selected task or assignee member revision changes", async (t) => {
  const { card, state, calls } = await setup(t);
  const c = TASK_BATCH_COPY.en;

  // Open and review
  clickText(card.shadowRoot, c.startBatch);
  check(card.shadowRoot, 'input[value="T101"]', true);
  clickText(card.shadowRoot, c.reviewBatch);
  assert.equal(card._taskBatchDraft.stage, "review");

  // Scenario 5a: task revision changes in background
  const previous1 = clone(card._data);
  state.tasks.find((item) => item.id === "T101").revision = 2;
  card._data = clone(state);
  assert.equal(reconcileTaskBatchRefresh(card, previous1), true);
  card.render();

  assert.equal(card._taskBatchDraft.stage, "select", "Stale first-send review must reset to select stage");
  assert.equal(card._taskBatchDraft.error, "staleError");
  assert.match(card.shadowRoot.textContent, new RegExp(c.staleError));
  assert.equal(calls.length, 0);

  // Reselect and review again
  check(card.shadowRoot, 'input[value="T101"]', true);
  clickText(card.shadowRoot, c.reviewBatch);
  assert.equal(card._taskBatchDraft.stage, "review");

  // Scenario 5b: assignee member revision changes in background
  const previous2 = clone(card._data);
  state.members.find((item) => item.id === "child_1").revision = 99;
  card._data = clone(state);
  assert.equal(reconcileTaskBatchRefresh(card, previous2), true);
  card.render();

  assert.equal(card._taskBatchDraft.stage, "select", "Assignee revision change must trigger reselection");
  assert.equal(card._taskBatchDraft.error, "staleError");
});

// 6. Role Change Test (Parent to Guest or Child Revocation)
test("role change: non-parent or guest role immediately revokes draft and clears private DOM", async (t) => {
  const { card, state } = await setup(t);
  const c = TASK_BATCH_COPY.en;

  clickText(card.shadowRoot, c.startBatch);
  assert.ok(card._taskBatchDraft);

  const previous = clone(card._data);
  state.role = "child";
  card._data = clone(state);

  assert.equal(reconcileTaskBatchRefresh(card, previous), true);
  card.render();

  assert.equal(card._taskBatchDraft, null, "Draft must be revoked on role demotion");
  assert.equal(card.shadowRoot.querySelector(".task-batch"), null, "Private bulk DOM must be removed");
});

// 7. Module Change Test (Disabling Tasks Module Revokes Draft)
test("module change: disabling tasks module revokes draft and private DOM", async (t) => {
  const { card, state } = await setup(t);
  const c = TASK_BATCH_COPY.en;

  clickText(card.shadowRoot, c.startBatch);
  assert.ok(card._taskBatchDraft);

  const previous = clone(card._data);
  state.settings.modules = [];
  card._data = clone(state);

  assert.equal(reconcileTaskBatchRefresh(card, previous), true);
  card.render();

  assert.equal(card._taskBatchDraft, null);
  assert.equal(card.shadowRoot.querySelector(".task-batch"), null);
});

// 8. Generation and Entry Changes Revocation Test
test("generation/entry/user changes: clears draft and prevents late operations", async (t) => {
  const { card, state } = await setup(t);
  const c = TASK_BATCH_COPY.en;

  // Generation change
  clickText(card.shadowRoot, c.startBatch);
  assert.ok(card._taskBatchDraft);
  card._generation += 1;
  const prevGen = clone(card._data);
  assert.equal(reconcileTaskBatchRefresh(card, prevGen), true);
  assert.equal(card._taskBatchDraft, null);

  // Entry change
  card.render();
  clickText(card.shadowRoot, c.startBatch);
  assert.ok(card._taskBatchDraft);
  card._entry = "entry-new-2";
  const prevEntry = clone(card._data);
  assert.equal(reconcileTaskBatchRefresh(card, prevEntry), true);
  assert.equal(card._taskBatchDraft, null);

  // User change
  card.render();
  clickText(card.shadowRoot, c.startBatch);
  assert.ok(card._taskBatchDraft);
  card._hass.user.id = "ha-other-user";
  const prevUser = clone(card._data);
  assert.equal(reconcileTaskBatchRefresh(card, prevUser), true);
  assert.equal(card._taskBatchDraft, null);
});

// 9. Uncertain Exact Retry Test (Committed response lost, unrelated card._pending, unchanged payload retry)
test("uncertain exact retry even other command: preserves own operation ID and payload without rebasing", async (t) => {
  const { card, state, calls, setFailure } = await setup(t);
  const c = TASK_BATCH_COPY.en;

  clickText(card.shadowRoot, c.startBatch);
  check(card.shadowRoot, 'input[value="T101"]', true);
  clickText(card.shadowRoot, c.reviewBatch);
  check(card.shadowRoot, 'input[name="confirm"]', true);

  // Simulate network interruption after server processed the request
  setFailure("after");
  clickText(card.shadowRoot, c.applyBatch);

  await eventually(() => calls.length === 1 && !card._writing && card._taskBatchDraft?.pending);

  const initialOperationId = card._taskBatchDraft.pending.operation_id;
  const initialPayload = clone(card._taskBatchDraft.pending.payload);
  assert.ok(initialOperationId, "Operation ID must exist");
  assert.equal(calls[0].operation_id, initialOperationId);

  // The lost-ack refresh already observed revision 2. Now observe another
  // revision change while keeping the original reviewed payload at revision 1.
  const previous = clone(card._data);
  state.tasks.find((item) => item.id === "T101").revision += 1;
  card._data = clone(state);

  // Reconcile: task revision change is allowed for pending retry!
  assert.equal(reconcileTaskBatchRefresh(card, previous), true);
  assert.ok(card._taskBatchDraft?.pending);
  card.render();

  // Simulate an unrelated command on the card touching card._pending
  card._pending = { fingerprint: "unrelated", id: "unrelated-op-id" };

  // Verify review shows pending notice and retry button
  assert.match(card.shadowRoot.textContent, new RegExp(c.pendingNotice));
  const retryBtn = card.shadowRoot.querySelector('button.primary');
  assert.equal(retryBtn.textContent.trim(), c.retry);

  // Retry submission
  clickText(card.shadowRoot, c.retry);

  await eventually(() => calls.length === 2 && card._taskBatchDraft === null);

  // Second call must use the EXACT same operation ID and unchanged payload (NEVER REBASED)
  assert.equal(calls[1].operation_id, initialOperationId);
  assert.deepEqual(calls[1].payload, initialPayload);
  assert.equal(calls[1].payload.commands[0].payload.revision, 1, "Must never rebase revision to 2");
});

for (const change of ["actor_revision", "assignee_revision", "assignee_role", "assignee_changed", "removed_task", "private_task"]) {
  test(`uncertain retry is revoked when ${change} changes`, async (t) => {
    const { card, state, calls, setFailure } = await setup(t);
    const c = TASK_BATCH_COPY.en;
    clickText(card.shadowRoot, c.startBatch);
    check(card.shadowRoot, 'input[value="T101"]');
    clickText(card.shadowRoot, c.reviewBatch);
    check(card.shadowRoot, 'input[name="confirm"]');
    setFailure("before");
    clickText(card.shadowRoot, c.applyBatch);
    await eventually(() => calls.length === 1 && !card._writing && card._taskBatchDraft?.pending);
    const oldRetry = card.shadowRoot.querySelector("button.primary");
    const previous = clone(card._data);
    if (change === "actor_revision") state.members.find(m => m.id === "parent_1").revision += 1;
    if (change === "assignee_revision") state.members.find(m => m.id === "child_1").revision += 1;
    if (change === "assignee_role") state.members.find(m => m.id === "child_1").role = "adult";
    if (change === "assignee_changed") state.tasks[0].assignee = "child_2";
    if (change === "removed_task") state.tasks = state.tasks.filter(item => item.id !== "T101");
    if (change === "private_task") state.tasks[0].delivery_scope = "private";
    card._data = clone(state);
    assert.equal(reconcileTaskBatchRefresh(card, previous), true);
    card.render();
    assert.equal(card._taskBatchDraft, null);
    assert.equal(card.shadowRoot.querySelector(".task-batch-review"), null);
    oldRetry.click();
    await tick();
    assert.equal(calls.length, 1);
  });
}

test("old collapsed start cannot bind a new actor revision before refresh", async (t) => {
  const { card, state, calls } = await setup(t);
  state.members.find(m => m.id === "parent_1").revision += 1;
  clickText(card.shadowRoot, TASK_BATCH_COPY.en.startBatch);
  assert.equal(card._taskBatchDraft, null);
  assert.equal(calls.length, 0);
});

// 10. Reset / Close Without Rollback Test
test("reset: cannot edit submitted uncertain batch, can close review with honest no-rollback wording", async (t) => {
  const { card, calls, setFailure } = await setup(t);
  const c = TASK_BATCH_COPY.en;

  clickText(card.shadowRoot, c.startBatch);
  check(card.shadowRoot, 'input[value="T101"]', true);
  clickText(card.shadowRoot, c.reviewBatch);
  check(card.shadowRoot, 'input[name="confirm"]', true);

  setFailure("after");
  clickText(card.shadowRoot, c.applyBatch);

  await eventually(() => calls.length === 1 && !card._writing && card._taskBatchDraft?.pending);

  // Confirm checkbox is disabled
  const confirmBox = card.shadowRoot.querySelector('input[name="confirm"]');
  assert.ok(confirmBox.disabled, "Confirmation checkbox must be disabled during uncertain pending state");

  // No back button available to edit submitted batch
  const backButtons = [...card.shadowRoot.querySelectorAll("button")].filter(
    (b) => b.textContent.trim() === c.back
  );
  assert.equal(backButtons.length, 0, "Back button must not be present for submitted batch");

  // Honest no-rollback notice is displayed
  assert.match(card.shadowRoot.textContent, new RegExp(c.uncertainNotice));

  // Click Close without rollback
  clickText(card.shadowRoot, c.closeWithoutRollback);
  assert.equal(card._taskBatchDraft, null, "Review panel must close upon honest close");
});

// 11. Detached Callbacks Test
test("detached callbacks: clicking detached controls from superseded draft has no effect", async (t) => {
  const { card } = await setup(t);
  const c = TASK_BATCH_COPY.en;

  clickText(card.shadowRoot, c.startBatch);
  const oldDraft = card._taskBatchDraft;
  const detachedCancel = [...card.shadowRoot.querySelectorAll("button")].find(
    (b) => b.textContent.trim() === c.cancel
  );

  // Replace draft with a new active draft
  const newDraft = { marker: "new" };
  card._taskBatchDraft = newDraft;
  card.shadowRoot.replaceChildren();

  // Click old detached cancel button
  detachedCancel.click();
  await tick();

  assert.equal(card._taskBatchDraft, newDraft, "Superseded draft must not be cleared by detached callback");
});

// 12. Late Response Protection Test
test("late response: scope change during await prevents late response from mutating another draft/entry", async (t) => {
  const { card, calls } = await setup(t);
  const c = TASK_BATCH_COPY.en;

  let resolveCommand;
  card.command = () =>
    new Promise((resolve) => {
      resolveCommand = resolve;
    });

  clickText(card.shadowRoot, c.startBatch);
  check(card.shadowRoot, 'input[value="T101"]', true);
  clickText(card.shadowRoot, c.reviewBatch);
  check(card.shadowRoot, 'input[name="confirm"]', true);

  // Trigger execute
  clickText(card.shadowRoot, c.applyBatch);

  // Switch card entry while command is awaiting
  card._entry = "entry-switched";
  const otherDraft = { marker: "different_entry_draft" };
  card._taskBatchDraft = otherDraft;

  // Resolve late command
  resolveCommand();
  await tick();

  assert.equal(card._taskBatchDraft, otherDraft, "Late response must not overwrite or clear new draft");
});

// 13. XSS Safety Test
test("XSS: malicious task titles, IDs, and member names are safely rendered via textContent", async (t) => {
  const { card, state } = await setup(t);
  const c = TASK_BATCH_COPY.en;

  state.tasks = [
    {
      id: "<script>alert('id')</script>",
      revision: 1,
      title: "<img src=x onerror=alert('title')>",
      status: "assigned",
      assignee: "child_1",
    },
  ];
  state.members.find((m) => m.id === "child_1").name = "<svg onload=alert('name')>";
  card.render();

  clickText(card.shadowRoot, c.startBatch);

  // Check that no script, img, or svg tags were parsed into the DOM
  const evilNodes = card.shadowRoot.querySelectorAll("script, img, svg");
  assert.equal(evilNodes.length, 0, "No executable DOM nodes should be created");

  // Literal text should be present
  assert.match(card.shadowRoot.textContent, /<script>alert\('id'\)<\/script>/);
  assert.match(card.shadowRoot.textContent, /<img src=x onerror=alert\('title'\)>/);
  assert.match(card.shadowRoot.textContent, /<svg onload=alert\('name'\)>/);
});

// 14. Real FamilyCard Integration Test
test("real FamilyCard: full component renders collapsed panel and completes batch action flow", async (t) => {
  const { card, calls } = await setup(t, { real: true });
  const c = TASK_BATCH_COPY.en;

  // In full real FamilyCard, verify collapsed details element exists
  const details = card.shadowRoot.querySelector(".task-batch details");
  assert.ok(details, "Details element must exist in real FamilyCard tasks view");

  clickText(details, c.startBatch);
  assert.ok(card._taskBatchDraft);

  check(card.shadowRoot, 'input[value="T101"]', true);
  clickText(card.shadowRoot, c.reviewBatch);
  check(card.shadowRoot, 'input[name="confirm"]', true);
  clickText(card.shadowRoot, c.applyBatch);

  await eventually(() => calls.length === 1 && card._taskBatchDraft === null);

  assert.equal(calls[0].action, "batch");
  assert.equal(calls[0].payload.commands[0].action, "tasks.complete");
});
