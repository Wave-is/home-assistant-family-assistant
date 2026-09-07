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

const { FamilyCard } =
  await import("../custom_components/family_assistant/frontend/family-assistant.js");
const { renderTaskSeries, reconcileTaskSeriesRefresh } =
  await import("../custom_components/family_assistant/frontend/task-series-view.js");
const { TASK_SERIES_COPY } =
  await import("../custom_components/family_assistant/frontend/task-series-copy.js");

const clone = (value) => structuredClone(value);
const tick = () => new Promise((resolve) => setTimeout(resolve, 0));
async function eventually(predicate) {
  for (let index = 0; index < 100; index += 1) {
    if (predicate()) return;
    await tick();
  }
  assert.fail("condition was not reached");
}

const MEMBERS = [
  { id: "owner", name: "Owner", role: "owner", active: true, revision: 2 },
  { id: "parent", name: "Parent", role: "parent", active: true, revision: 3 },
  { id: "child", name: "Child", role: "child", active: true, revision: 4 },
  { id: "adult", name: "Adult", role: "adult", active: true, revision: 5 },
  { id: "guest", name: "Guest", role: "guest", active: true, revision: 1 },
];
function series(overrides = {}) {
  return {
    id: "D000001",
    revision: 6,
    creator: "parent",
    creator_revision: 3,
    title: "Put bins outside",
    assignees: ["child"],
    assignee_revisions: { child: 4 },
    rotation: false,
    enabled: true,
    current: true,
    rule: {
      frequency: "weekly",
      interval: 1,
      start_date: "2026-09-07",
      until: null,
      time: "19:00",
      timezone: "Europe/Kyiv",
      weekdays: [0],
      month_day: 7,
      exceptions: [],
      catchup_hours: 24,
    },
    due_time: "07:00",
    report_type: "text",
    checklist: ["Close the lid"],
    deadline_policy: { reminder_minutes: 60, grace_minutes: 30, penalty: 0 },
    effective_at: "2026-09-07T08:00:00+00:00",
    ...overrides,
  };
}
function stateFor(role = "parent") {
  const actor = {
    owner: "owner",
    parent: "parent",
    adult: "adult",
    child: "child",
    guest: "guest",
  }[role];
  return {
    revision: 1,
    actor,
    role,
    settings: {
      name: "Test family",
      timezone: "Europe/Kyiv",
      modules: ["tasks"],
    },
    members: clone(MEMBERS),
    task_series: [series()],
    tasks: [],
    proposals: [],
  };
}
function normalizedRow(payload, id, revision) {
  return {
    id,
    revision,
    creator: payload.id ? "parent" : "parent",
    creator_revision: payload.creator_revision,
    title: payload.title,
    assignees: clone(payload.assignees),
    assignee_revisions: clone(payload.assignee_revisions),
    rotation: payload.rotation,
    enabled: payload.enabled,
    current: true,
    rule: clone(payload.rule),
    due_time: payload.due_time,
    report_type: payload.report_type,
    checklist: clone(payload.checklist),
    deadline_policy: {
      reminder_minutes: payload.reminder_minutes,
      grace_minutes: payload.grace_minutes,
      penalty: payload.penalty,
    },
    effective_at: "2026-09-07T09:00:00+00:00",
  };
}
async function setup(
  t,
  { role = "parent", language = "en", real = false } = {},
) {
  const state = stateFor(role);
  const calls = [];
  const receipts = new Map();
  let failure = null;
  const hass = {
    user: { id: `ha-${state.actor}` },
    language,
    callWS: async (message) => {
      if (message.type === "family_assistant/view") return clone(state);
      calls.push(clone(message));
      if (receipts.has(message.operation_id))
        return clone(receipts.get(message.operation_id));
      if (failure === "before") {
        failure = null;
        const error = new Error("down");
        error.code = "network";
        throw error;
      }
      const payload = message.payload;
      let receipt;
      if (message.action === "tasks.series_save") {
        const id = payload.id || "D000002";
        const revision = payload.revision ? payload.revision + 1 : 1;
        const row = normalizedRow(payload, id, revision);
        const index = state.task_series.findIndex((item) => item.id === id);
        if (index >= 0) state.task_series[index] = row;
        else state.task_series.push(row);
        receipt = clone(row);
      } else {
        const row = state.task_series.find((item) => item.id === payload.id);
        row.revision += 1;
        row.enabled = payload.enabled;
        receipt = clone(row);
      }
      receipts.set(message.operation_id, receipt);
      if (failure === "after") {
        failure = null;
        const error = new Error("lost");
        error.code = "network";
        throw error;
      }
      return clone(receipt);
    },
  };
  const card = document.createElement(
    real ? "family-tasks-card" : "family-assistant-card",
  );
  assert.ok(card instanceof FamilyCard);
  card._config = { language };
  card._entry = "entry-1";
  card._generation = 1;
  card._data = state;
  card._hass = hass;
  card._view = "tasks";
  card._loading = false;
  card._writing = false;
  card._form = null;
  card._taskCreateDraft = null;
  card._taskMediaDraft = null;
  card._actionError = null;
  const render = real
    ? () => card.render()
    : () => {
        card.shadowRoot.replaceChildren();
        const body = document.createElement("div");
        card.shadowRoot.append(body);
        renderTaskSeries(card, body);
      };
  if (!real) card.render = render;
  document.body.append(card);
  render();
  t.after(() => {
    clearInterval(card._timer);
    card.remove();
  });
  return {
    card,
    state,
    calls,
    setFailure(value) {
      failure = value;
    },
    render,
  };
}
function clickText(root, text) {
  const button = [...root.querySelectorAll("button")].find(
    (item) => item.textContent === text,
  );
  assert.ok(button, `button ${text}`);
  button.click();
  return button;
}
function setValue(root, selector, value) {
  const control = root.querySelector(selector);
  assert.ok(control, selector);
  control.value = value;
  control.dispatchEvent(new window.Event("input", { bubbles: true }));
  return control;
}
function check(root, selector, checked = true) {
  const control = root.querySelector(selector);
  assert.ok(control, selector);
  control.checked = checked;
  control.dispatchEvent(new window.Event("change", { bubbles: true }));
  return control;
}
function prepareCreate(card, c = TASK_SERIES_COPY.en) {
  clickText(card.shadowRoot, c.add);
  setValue(card.shadowRoot, 'input[name="title"]', "Water plants");
  check(card.shadowRoot, 'input[name="assignees"][value="child"]');
  setValue(
    card.shadowRoot,
    '[data-recurrence-control="start_date"]',
    "2026-09-08",
  );
  setValue(card.shadowRoot, '[data-recurrence-control="time"]', "08:30");
  setValue(card.shadowRoot, 'input[name="due_time"]', "09:00");
  card.shadowRoot.querySelector("form").requestSubmit();
}

test("parent create uses complete strict lineage payload and no command before named confirmation", async (t) => {
  const { card, calls } = await setup(t);
  const c = TASK_SERIES_COPY.en;
  prepareCreate(card, c);
  assert.equal(calls.length, 0);
  assert.match(card.shadowRoot.textContent, /Review for: Water plants/);
  assert.match(card.shadowRoot.textContent, /Catchup window \(hours, 0–48\)24/);
  check(card.shadowRoot, 'input[name="confirm"]');
  clickText(card.shadowRoot, c.save);
  await eventually(() => calls.length === 1 && card._taskSeriesDraft === null);
  const message = calls[0];
  assert.equal(message.action, "tasks.series_save");
  assert.equal(typeof message.operation_id, "string");
  assert.deepEqual(message.payload.assignee_revisions, { child: 4 });
  assert.equal(message.payload.actor_revision, 3);
  assert.equal(message.payload.creator_revision, 3);
  assert.deepEqual(
    Object.keys(message.payload).sort(),
    [
      "actor_revision",
      "assignee_revisions",
      "assignees",
      "checklist",
      "creator_revision",
      "due_time",
      "enabled",
      "grace_minutes",
      "penalty",
      "reminder_minutes",
      "report_type",
      "rotation",
      "rule",
      "title",
    ].sort(),
  );
});

test("real FamilyCard tasks branch renders and completes the reviewed series flow", async (t) => {
  const { card, calls } = await setup(t, { real: true });
  const c = TASK_SERIES_COPY.en;
  prepareCreate(card, c);
  assert.equal(calls.length, 0);
  check(card.shadowRoot, 'input[name="confirm"]');
  clickText(card.shadowRoot, c.save);
  await eventually(() => calls.length === 1 && card._taskSeriesDraft === null);
  assert.equal(calls[0].action, "tasks.series_save");
  assert.match(card.shadowRoot.textContent, /Water plants/);
});

test("committed response loss keeps frozen payload and operation id despite target epoch drift", async (t) => {
  const { card, state, calls, setFailure } = await setup(t);
  const c = TASK_SERIES_COPY.en;
  prepareCreate(card, c);
  check(card.shadowRoot, 'input[name="confirm"]');
  setFailure("after");
  clickText(card.shadowRoot, c.save);
  await eventually(
    () =>
      calls.length === 1 && !card._writing && card._taskSeriesDraft?.pending,
  );
  const first = clone(calls[0]);
  state.members.find((item) => item.id === "child").revision = 5;
  const previous = clone(card._data);
  card._data = clone(state);
  assert.equal(reconcileTaskSeriesRefresh(card, previous), true);
  card.render();
  assert.match(
    card.shadowRoot.textContent,
    /exact reviewed request is pending/,
  );
  clickText(card.shadowRoot, c.retry);
  await eventually(() => calls.length === 2 && card._taskSeriesDraft === null);
  assert.equal(calls[1].operation_id, first.operation_id);
  assert.deepEqual(calls[1].payload, first.payload);
});

test("uncommitted member drift and detached controls cannot submit or rebase", async (t) => {
  const { card, state, calls } = await setup(t);
  const c = TASK_SERIES_COPY.en;
  clickText(card.shadowRoot, c.add);
  const detached = card.shadowRoot.querySelector("form");
  const previous = card._data;
  state.members.find((item) => item.id === "parent").revision = 4;
  card._data = clone(state);
  assert.equal(reconcileTaskSeriesRefresh(card, previous), true);
  card.render();
  detached.requestSubmit();
  await tick();
  assert.equal(calls.length, 0);
  assert.equal(card._taskSeriesDraft, null);
});

test("stale series supports explicit current-epoch review but cannot be directly enabled", async (t) => {
  const { card, state, calls } = await setup(t);
  const c = TASK_SERIES_COPY.en;
  state.task_series[0].current = false;
  state.members.find((item) => item.id === "child").revision = 5;
  card.render();
  const row = card.shadowRoot.querySelector('[data-task-series-id="D000001"]');
  assert.match(row.textContent, /Paused for identity review/);
  assert.equal(
    [...row.querySelectorAll("button")].some(
      (item) => item.textContent === c.enable,
    ),
    false,
  );
  clickText(row, c.edit);
  card.shadowRoot.querySelector("form").requestSubmit();
  assert.deepEqual(card._taskSeriesDraft.payload.assignee_revisions, {
    child: 5,
  });
  check(card.shadowRoot, 'input[name="confirm"]');
  clickText(card.shadowRoot, c.save);
  await eventually(() => calls.length === 1);
  assert.equal(calls[0].payload.id, "D000001");
  assert.equal(calls[0].payload.revision, 6);
});

test("failed-before-commit retry keeps exact request only while frozen members remain current", async (t) => {
  const { card, calls, setFailure } = await setup(t);
  const c = TASK_SERIES_COPY.en;
  clickText(card.shadowRoot, c.edit);
  card.shadowRoot.querySelector("form").requestSubmit();
  check(card.shadowRoot, 'input[name="confirm"]');
  setFailure("before");
  clickText(card.shadowRoot, c.save);
  await eventually(
    () =>
      calls.length === 1 && !card._writing && card._taskSeriesDraft?.pending,
  );
  const first = clone(calls[0]);
  clickText(card.shadowRoot, c.retry);
  await eventually(() => calls.length === 2 && card._taskSeriesDraft === null);
  assert.equal(calls[1].operation_id, first.operation_id);
  assert.deepEqual(calls[1].payload, first.payload);
});

test("toggle is reviewed, exact, and stale enable is absent", async (t) => {
  const { card, calls } = await setup(t);
  const c = TASK_SERIES_COPY.en;
  clickText(card.shadowRoot, c.disable);
  assert.equal(calls.length, 0);
  assert.match(card.shadowRoot.textContent, /Review disable/);
  check(card.shadowRoot, 'input[name="confirm"]');
  clickText(card.shadowRoot, c.applyDisable);
  await eventually(() => calls.length === 1);
  assert.deepEqual(calls[0].payload, {
    id: "D000001",
    revision: 6,
    actor_revision: 3,
    enabled: false,
  });
});

test("child projection is read-only and renderer never emits hidden lineage", async (t) => {
  const { card, state } = await setup(t, { role: "child", language: "uk" });
  state.task_series = [
    series({
      creator: undefined,
      creator_revision: undefined,
      assignee_revisions: undefined,
    }),
  ];
  card.render();
  assert.match(card.shadowRoot.textContent, /Put bins outside/);
  assert.equal(card.shadowRoot.querySelectorAll("button").length, 0);
  assert.doesNotMatch(
    card.shadowRoot.textContent,
    /parent|creator_revision|assignee_revisions/i,
  );
});

test("guest and module revocation clear private draft without action", async (t) => {
  const { card, state, calls } = await setup(t);
  const c = TASK_SERIES_COPY.en;
  clickText(card.shadowRoot, c.add);
  const previous = card._data;
  state.settings.modules = [];
  card._data = clone(state);
  assert.equal(reconcileTaskSeriesRefresh(card, previous), true);
  card.render();
  assert.equal(card._taskSeriesDraft, null);
  assert.equal(calls.length, 0);
  assert.doesNotMatch(card.shadowRoot.textContent, /Water plants/);
});

test("unavailable original creator blocks save and exposes no transfer control", async (t) => {
  const { card, state, calls } = await setup(t);
  const c = TASK_SERIES_COPY.en;
  state.members.find((item) => item.id === "parent").active = false;
  state.actor = "owner";
  state.role = "owner";
  card._hass.user.id = "ha-owner";
  card.render();
  clickText(card.shadowRoot, c.edit);
  assert.match(card.shadowRoot.textContent, /cannot be transferred/);
  assert.equal(
    card.shadowRoot.querySelector('button[type="submit"]')?.disabled,
    true,
  );
  assert.equal(calls.length, 0);
});

test("owner edit is discarded when the immutable original creator epoch changes", async (t) => {
  const { card, state, calls } = await setup(t, { role: "owner" });
  const c = TASK_SERIES_COPY.en;
  clickText(card.shadowRoot, c.edit);
  const previous = card._data;
  state.members.find((item) => item.id === "parent").revision = 4;
  card._data = clone(state);
  assert.equal(reconcileTaskSeriesRefresh(card, previous), true);
  assert.equal(card._taskSeriesDraft, null);
  assert.equal(calls.length, 0);
});

test("harmless projection refresh preserves every typed scalar and recurrence value", async (t) => {
  const { card, state } = await setup(t);
  const c = TASK_SERIES_COPY.en;
  clickText(card.shadowRoot, c.add);
  setValue(card.shadowRoot, 'input[name="title"]', "Typed title");
  setValue(card.shadowRoot, 'textarea[name="checklist"]', "First\nSecond");
  setValue(card.shadowRoot, 'input[name="reminder_minutes"]', "17");
  setValue(card.shadowRoot, '[data-recurrence-control="catchup_hours"]', "0");
  const previous = clone(card._data);
  state.members.find((item) => item.id === "adult").name = "Harmless rename";
  card._data = clone(state);
  assert.equal(reconcileTaskSeriesRefresh(card, previous), true);
  card.render();
  assert.equal(
    card.shadowRoot.querySelector('input[name="title"]').value,
    "Typed title",
  );
  assert.equal(
    card.shadowRoot.querySelector('textarea[name="checklist"]').value,
    "First\nSecond",
  );
  assert.equal(
    card.shadowRoot.querySelector('input[name="reminder_minutes"]').value,
    "17",
  );
  assert.equal(
    card.shadowRoot.querySelector('[data-recurrence-control="catchup_hours"]')
      .value,
    "0",
  );
});

test("detached cancel from an old editor cannot clear a newer draft", async (t) => {
  const { card } = await setup(t);
  const c = TASK_SERIES_COPY.en;
  clickText(card.shadowRoot, c.add);
  const oldCancel = [...card.shadowRoot.querySelectorAll("button")].find(
    (item) => item.textContent === c.cancel,
  );
  const replacement = { marker: "newer" };
  card._taskSeriesDraft = replacement;
  card.shadowRoot.replaceChildren();
  oldCancel.click();
  assert.equal(card._taskSeriesDraft, replacement);
});

test("zero penalty and catchup are valid while malformed date fails locally", async (t) => {
  const { card, calls } = await setup(t);
  const c = TASK_SERIES_COPY.en;
  clickText(card.shadowRoot, c.add);
  setValue(card.shadowRoot, 'input[name="title"]', "Test");
  check(card.shadowRoot, 'input[name="assignees"][value="child"]');
  setValue(
    card.shadowRoot,
    '[data-recurrence-control="start_date"]',
    "2026-02-30",
  );
  setValue(card.shadowRoot, '[data-recurrence-control="catchup_hours"]', "0");
  card.shadowRoot.querySelector("form").requestSubmit();
  assert.equal(calls.length, 0);
  assert.match(card.shadowRoot.textContent, /Check every field/);
});
