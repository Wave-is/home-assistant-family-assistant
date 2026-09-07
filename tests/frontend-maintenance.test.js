import assert from "node:assert/strict";
import { test } from "node:test";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><body></body>", { url: "https://example.invalid" });
for (const key of ["window", "document", "HTMLElement", "customElements", "CustomEvent", "Event", "FormData"])
  globalThis[key] = dom.window[key];

await import("../custom_components/family_assistant/frontend/family-assistant.js");
const { MAINTENANCE_COPY } = await import(
  "../custom_components/family_assistant/frontend/maintenance-copy.js"
);

const clone = (value) => structuredClone(value);
const tick = () => new Promise((resolve) => setTimeout(resolve, 0));
async function eventually(predicate, message = "condition was not reached") {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    if (predicate()) return;
    await tick();
  }
  assert.fail(message);
}

function fullAsset(overrides = {}) {
  return {
    id: "MX000001",
    revision: 3,
    name: "Heating boiler",
    category: "Heating",
    location: "Utility room",
    responsible_member: "adult-1",
    responsible_member_revision: 1,
    warranty: {
      expires_on: "2027-09-01",
      vendor: "Private vendor",
      reference: "Private serial reference",
    },
    consumables: [
      {
        label: "Filter",
        unit: "piece",
        quantity: 1,
        pantry: { id: "PI000001", revision: 2 },
      },
    ],
    note: "Parent-only boiler note",
    reportable: true,
    approved_by: "parent-1",
    approved_by_revision: 1,
    status: "active",
    current: true,
    can_report: true,
    history: [
      { actor: "parent-1", at: "2026-09-07T08:00:00+00:00", action: "created" },
    ],
    ...overrides,
  };
}

function service(overrides = {}) {
  return {
    id: "D000001",
    revision: 4,
    asset_id: "MX000001",
    asset_revision: 3,
    title: "Check boiler pressure",
    assignees: ["adult-1"],
    rotation: false,
    rule: {
      frequency: "monthly",
      interval: 1,
      start_date: "2026-09-01",
      until: null,
      time: "09:00",
      timezone: "Europe/Kyiv",
      weekdays: [0],
      month_day: 1,
      exceptions: [],
      catchup_hours: 24,
    },
    due_time: "18:00",
    checklist: ["Read pressure gauge"],
    enabled: true,
    deadline_policy: { reminder_minutes: 60, grace_minutes: 30, penalty: 0 },
    effective_at: "2026-09-07T08:00:00+00:00",
    current: true,
    ...overrides,
  };
}

function stateFor(role = "parent") {
  const actor = role === "parent" ? "parent-1" : role === "owner" ? "owner-1" :
    role === "child" ? "child-1" : role === "guest" ? "guest-1" : "adult-1";
  const members = [
    { id: "parent-1", name: "Parent One", role: "parent", active: true, revision: 1 },
    { id: "owner-1", name: "Owner One", role: "owner", active: true, revision: 2 },
    { id: "child-1", name: "Child One", role: "child", active: true, revision: 2 },
    { id: "adult-1", name: "Adult One", role: "adult", active: true, revision: 1 },
    { id: "other-1", name: "Other Adult", role: "adult", active: true, revision: 5 },
    { id: "guest-1", name: "Guest One", role: "guest", active: true, revision: 1 },
  ];
  const parent = ["parent", "owner"].includes(role);
  const asset = fullAsset();
  const visibleStub = {
    id: asset.id,
    revision: asset.revision,
    name: asset.name,
    category: asset.category,
    location: asset.location,
    can_report: true,
  };
  const relatedOnly = {
    id: "MX000002",
    revision: 1,
    name: "Related appliance",
    category: "Appliance",
    location: "Kitchen",
    can_report: false,
  };
  const fault = {
    id: "MF000001",
    revision: 1,
    status: "reported",
    asset_id: asset.id,
    reporter: "child-1",
    summary: "Water pressure warning",
    details: "The display showed a warning.",
    task_id: "T000001",
    task_status: "completed",
    task_revision: 2,
    assignee: "adult-1",
    created_at: "2026-09-07T08:30:00+00:00",
    ...(parent ? { asset_revision: 3, reporter_member_revision: 2 } : {}),
  };
  return {
    revision: 1,
    actor,
    role,
    settings: {
      name: "Synthetic family",
      timezone: "Europe/Kyiv",
      modules: ["maintenance", "tasks", "pantry"],
    },
    members,
    tasks: [
      {
        id: "T000001",
        revision: 2,
        title: "Water pressure warning",
        status: "completed",
        assignee: "adult-1",
        assignee_revision: 1,
        source: { kind: "maintenance_fault", asset_id: asset.id, asset_revision: 3 },
      },
    ],
    pantry: {
      items: [
        { id: "PI000001", revision: 2, status: "active", name: "Boiler filter", unit: "piece", quantity: 4 },
      ],
      archived: [], suggestions: [], meal_plans: [], meal_shopping: [],
      dietary_profiles: { self: null, managed_children: [], shared_adults: [] },
    },
    maintenance: parent
      ? {
          assets: [asset],
          faults: [fault],
          services: [service()],
          service_logs: [
            {
              id: "MH000001",
              revision: 1,
              status: "recorded",
              asset_id: asset.id,
              asset_revision: 3,
              performed_on: "2026-09-06",
              summary: "Parent-only completed service detail",
              task_id: null,
              task_revision: null,
              consumables_used: [],
              attachment_ids: [],
              actor: "parent-1",
              created_at: "2026-09-06T12:00:00+00:00",
            },
          ],
        }
      : role === "guest"
        ? { assets: [], faults: [], services: [], service_logs: [] }
        : { assets: [visibleStub, relatedOnly], faults: [fault], services: [], service_logs: [] },
  };
}

async function setup(t, { role = "parent" } = {}) {
  const state = stateFor(role);
  const calls = [];
  const receipts = new Map();
  let lostAction = null;
  const card = document.createElement("family-maintenance-card");
  card.setConfig({ type: "custom:family-maintenance-card", entry_id: "synthetic", language: "en" });
  document.body.append(card);
  t.after(() => card.remove());

  function execute(message) {
    calls.push(clone(message));
    if (receipts.has(message.operation_id)) return clone(receipts.get(message.operation_id));
    const { action, payload } = message;
    let receipt;
    if (action === "maintenance.asset_save") {
      if (payload.id) {
        const record = state.maintenance.assets.find((item) => item.id === payload.id);
        assert.equal(record.revision, payload.revision);
        Object.assign(record, clone(payload), { revision: record.revision + 1, status: "active", current: true, can_report: true });
        delete record.responsible_member_revision;
        record.responsible_member_revision = payload.responsible_member_revision;
        receipt = { id: record.id, revision: record.revision, status: record.status };
      } else {
        const record = {
          id: "MX000003", ...clone(payload), revision: 1, status: "active", current: true,
          can_report: true, history: [],
        };
        state.maintenance.assets.push(record);
        receipt = { id: record.id, revision: 1, status: "active" };
      }
    } else if (action === "maintenance.asset_retire") {
      const record = state.maintenance.assets.find((item) => item.id === payload.id);
      record.status = "retired"; record.revision += 1;
      receipt = { id: record.id, revision: record.revision, status: "retired" };
    } else if (action === "maintenance.fault_report") {
      const id = "MF000002";
      state.maintenance.faults.push({
        id, revision: 1, status: "reported", asset_id: payload.asset_id,
        reporter: state.actor, summary: payload.summary, details: payload.details,
        task_id: "T000002", task_status: "assigned", task_revision: 1,
        assignee: "adult-1", created_at: "2026-09-07T09:00:00+00:00",
      });
      receipt = { id, revision: 1, status: "reported", task_id: "T000002" };
    } else if (action === "maintenance.service_save") {
      if (payload.id) {
        const record = state.maintenance.services.find((item) => item.id === payload.id);
        Object.assign(record, clone(payload), {
          assignees: payload.assignees.map((item) => item.id),
          deadline_policy: { reminder_minutes: payload.reminder_minutes, grace_minutes: payload.grace_minutes, penalty: 0 },
          revision: record.revision + 1, current: true,
        });
        receipt = { id: record.id, revision: record.revision, enabled: record.enabled };
      } else {
        const record = {
          id: "D000002", ...clone(payload), assignees: payload.assignees.map((item) => item.id),
          deadline_policy: { reminder_minutes: payload.reminder_minutes, grace_minutes: payload.grace_minutes, penalty: 0 },
          revision: 1, current: true,
        };
        state.maintenance.services.push(record);
        receipt = { id: record.id, revision: 1, enabled: record.enabled };
      }
    } else if (action === "maintenance.service_enable") {
      const record = state.maintenance.services.find((item) => item.id === payload.id);
      record.enabled = payload.enabled; record.revision += 1;
      receipt = { id: record.id, revision: record.revision, enabled: record.enabled };
    } else if (action === "maintenance.service_log") {
      const record = {
        id: "MH000002", revision: 1, status: "recorded", ...clone(payload),
        task_id: payload.task?.id || null, task_revision: payload.task?.revision || null,
      };
      state.maintenance.service_logs.push(record);
      receipt = { id: record.id, revision: 1, status: "recorded" };
    } else throw { code: "unknown_action" };
    receipts.set(message.operation_id, clone(receipt));
    state.revision += 1;
    if (lostAction === action) {
      lostAction = null;
      throw { code: "storage_error" };
    }
    return clone(receipt);
  }

  card.hass = {
    language: "en",
    callWS: async (message) => {
      if (message.type === "family_assistant/view") return clone(state);
      if (message.type === "family_assistant/execute") return execute(message);
      throw new Error(`unexpected WebSocket type: ${message.type}`);
    },
  };
  await eventually(() => Boolean(card._data) && !card._loading);
  return {
    card, state, calls,
    lose(action) { lostAction = action; },
  };
}

function button(root, label) {
  const result = [...root.querySelectorAll("button")].find((item) => item.textContent === label);
  assert.ok(result, `missing button: ${label}`);
  return result;
}
function form(card, kind) {
  const result = card.shadowRoot.querySelector(`[data-maintenance-form="${kind}"]`);
  assert.ok(result, `missing maintenance form: ${kind}`);
  return result;
}
function setField(root, name, value) {
  const control = root.querySelector(`[name="${name}"]`);
  assert.ok(control, `missing field: ${name}`);
  if (control.type === "checkbox") control.checked = Boolean(value);
  else control.value = value;
  control.dispatchEvent(new Event("input", { bubbles: true }));
  control.dispatchEvent(new Event("change", { bubbles: true }));
  return control;
}
function submit(target) {
  target.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
}

test("real card is inert, locale-complete, parent-full, and relationship-limited", async (t) => {
  for (const locale of Object.values(MAINTENANCE_COPY))
    assert.deepEqual(Object.keys(locale).sort(), Object.keys(MAINTENANCE_COPY.en).sort());
  const parent = await setup(t);
  const before = clone(parent.state);
  parent.card.render();
  assert.deepEqual(parent.state, before);
  assert.equal(parent.calls.length, 0);
  assert.match(parent.card.shadowRoot.textContent, /Parent-only boiler note/);
  assert.match(parent.card.shadowRoot.textContent, /Private vendor/);
  assert.match(parent.card.shadowRoot.textContent, /Parent-only completed service detail/);

  const child = await setup(t, { role: "child" });
  assert.equal(child.card.shadowRoot.textContent.includes("Parent-only boiler note"), false);
  assert.equal(child.card.shadowRoot.textContent.includes("Private vendor"), false);
  assert.equal(child.card.shadowRoot.textContent.includes("Check boiler pressure"), false);
  const reportButtons = [...child.card.shadowRoot.querySelectorAll("button")].filter(
    (item) => item.textContent === MAINTENANCE_COPY.en.report_fault,
  );
  assert.equal(reportButtons.length, 1);
  assert.equal(child.card.shadowRoot.querySelector('[data-maintenance-asset="MX000002"] button'), null);

  const guest = await setup(t, { role: "guest" });
  assert.equal(guest.card.shadowRoot.querySelector(".maintenance-section"), null);
});

test("parent asset edit freezes every private field and pantry link", async (t) => {
  const fixture = await setup(t);
  const row = fixture.card.shadowRoot.querySelector('[data-maintenance-asset="MX000001"]');
  button(row, MAINTENANCE_COPY.en.edit_asset).click();
  let editor = form(fixture.card, "asset_edit");
  setField(editor, "location", "Updated utility room");
  submit(editor);
  assert.equal(fixture.card._maintenanceDraft.kind, "review");
  assert.equal(fixture.calls.length, 0);
  assert.ok(Object.isFrozen(fixture.card._maintenanceDraft.payload));
  assert.deepEqual(fixture.card._maintenanceDraft.payload, {
    id: "MX000001",
    revision: 3,
    name: "Heating boiler",
    category: "Heating",
    location: "Updated utility room",
    responsible_member: "adult-1",
    responsible_member_revision: 1,
    warranty: {
      expires_on: "2027-09-01",
      vendor: "Private vendor",
      reference: "Private serial reference",
    },
    consumables: [
      { label: "Filter", unit: "piece", quantity: 1, pantry: { id: "PI000001", revision: 2 } },
    ],
    note: "Parent-only boiler note",
    reportable: true,
  });
  editor = form(fixture.card, "review");
  submit(editor);
  await tick();
  assert.equal(fixture.calls.length, 0);
  editor.elements.reviewed.checked = true;
  editor.elements.reviewed.dispatchEvent(new Event("change", { bubbles: true }));
  submit(editor);
  await eventually(() => fixture.calls.length === 1 && fixture.card._maintenanceDraft === null);
});

test("stale responsible and pantry links require explicit parent replacement", async (t) => {
  const fixture = await setup(t);
  const assetState = fixture.state.maintenance.assets[0];
  assetState.responsible_member_revision = 0;
  assetState.current = false;
  fixture.state.pantry.items[0].revision = 3;
  await fixture.card.refresh();
  const row = fixture.card.shadowRoot.querySelector('[data-maintenance-asset="MX000001"]');
  button(row, MAINTENANCE_COPY.en.edit_asset).click();
  let editor = form(fixture.card, "asset_edit");
  assert.match(editor.textContent, /Unavailable saved assignee/);
  assert.match(editor.textContent, /Unavailable saved pantry link/);
  setField(editor, "location", "A rename must not clear links");
  submit(editor);
  assert.equal(fixture.card._maintenanceDraft.kind, "asset_edit");
  assert.equal(fixture.card._actionError, "invalid_field");
  assert.equal(fixture.calls.length, 0);

  editor = form(fixture.card, "asset_edit");
  setField(editor, "responsible_member", "adult-1");
  const consumable = editor.querySelector('[data-maintenance-consumable="0"]');
  setField(consumable, "pantry", "");
  submit(editor);
  assert.equal(fixture.card._maintenanceDraft.kind, "review");
  assert.equal(fixture.card._maintenanceDraft.payload.responsible_member_revision, 1);
  assert.equal(fixture.card._maintenanceDraft.payload.consumables[0].pantry, null);
});

test("child fault report is explicit and exact retry survives target advancement", async (t) => {
  const fixture = await setup(t, { role: "child" });
  const row = fixture.card.shadowRoot.querySelector('[data-maintenance-asset="MX000001"]');
  button(row, MAINTENANCE_COPY.en.report_fault).click();
  let editor = form(fixture.card, "fault_edit");
  setField(editor, "summary", "New warning");
  setField(editor, "details", "Observed once; manually described.");
  submit(editor);
  let review = form(fixture.card, "review");
  assert.deepEqual(fixture.card._maintenanceDraft.payload, {
    asset_id: "MX000001",
    asset_revision: 3,
    reporter_member_revision: 2,
    summary: "New warning",
    details: "Observed once; manually described.",
    attachment_ids: [],
  });
  review.elements.reviewed.checked = true;
  review.elements.reviewed.dispatchEvent(new Event("change", { bubbles: true }));
  fixture.lose("maintenance.fault_report");
  submit(review);
  await eventually(() => fixture.calls.length === 1 && fixture.card._maintenanceDraft?.pending && !fixture.card._writing);
  const first = clone(fixture.calls[0]);
  fixture.state.maintenance.assets[0].revision = 4;
  await fixture.card.refresh();
  assert.equal(fixture.card._maintenanceDraft.pending.operation_id, first.operation_id);
  review = form(fixture.card, "review");
  submit(review);
  await eventually(() => fixture.calls.length === 2 && fixture.card._maintenanceDraft === null);
  assert.deepEqual(fixture.calls[1], first);
});

test("service editor reuses recurrence and submits current member revisions", async (t) => {
  const fixture = await setup(t);
  const asset = fixture.card.shadowRoot.querySelector('[data-maintenance-asset="MX000001"]');
  button(asset, MAINTENANCE_COPY.en.new_service).click();
  const editor = form(fixture.card, "service_edit");
  setField(editor, "title", "Annual inspection");
  setField(editor, "due_time", "17:30");
  setField(editor, "reminder_minutes", "120");
  setField(editor, "grace_minutes", "45");
  setField(editor, "checklist", "Inspect casing\nRecord reading");
  const adult = [...editor.querySelectorAll('.maintenance-assignees input[type="checkbox"][value]')]
    .find((item) => item.value === "adult-1");
  adult.checked = true;
  adult.dispatchEvent(new Event("change", { bubbles: true }));
  const recurrenceStart = editor.querySelector('[data-recurrence-control="start_date"]');
  recurrenceStart.value = "2026-09-07";
  recurrenceStart.dispatchEvent(new Event("input", { bubbles: true }));
  submit(editor);
  assert.equal(fixture.card._maintenanceDraft.kind, "review");
  const payload = fixture.card._maintenanceDraft.payload;
  assert.equal(payload.asset_id, "MX000001");
  assert.equal(payload.asset_revision, 3);
  assert.deepEqual(payload.assignees, [{ id: "adult-1", revision: 1 }]);
  assert.equal(payload.rule.start_date, "2026-09-07");
  assert.equal(payload.rule.timezone, "Europe/Kyiv");
  assert.deepEqual(payload.checklist, ["Inspect casing", "Record reading"]);
  assert.equal(payload.reminder_minutes, 120);
  assert.equal(payload.grace_minutes, 45);
});

test("stale services can be re-reviewed and retired assets accept historical logs", async (t) => {
  const fixture = await setup(t);
  fixture.state.maintenance.services[0].current = false;
  fixture.state.maintenance.assets[0].status = "retired";
  fixture.state.maintenance.assets[0].current = false;
  await fixture.card.refresh();
  let asset = fixture.card.shadowRoot.querySelector('[data-maintenance-asset="MX000001"]');
  assert.ok(button(asset, MAINTENANCE_COPY.en.manual_service_log));
  assert.equal(
    [...asset.querySelectorAll("button")].some((item) => item.textContent === MAINTENANCE_COPY.en.new_service),
    false,
  );

  // Re-activate only the asset projection: the stale series itself remains editable
  // so a parent can re-review current asset/member epochs.
  fixture.state.maintenance.assets[0].status = "active";
  fixture.state.maintenance.assets[0].current = true;
  await fixture.card.refresh();
  const serviceRow = fixture.card.shadowRoot.querySelector('[data-maintenance-service="D000001"]');
  button(serviceRow, MAINTENANCE_COPY.en.edit_service).click();
  const editor = form(fixture.card, "service_edit");
  submit(editor);
  assert.equal(fixture.card._maintenanceDraft.kind, "review");
  assert.equal(fixture.card._maintenanceDraft.payload.asset_revision, 3);
  assert.deepEqual(fixture.card._maintenanceDraft.payload.assignees, [
    { id: "adult-1", revision: 1 },
  ]);
});

test("manual log uses exact completed task and reviewed consumables", async (t) => {
  const fixture = await setup(t);
  const asset = fixture.card.shadowRoot.querySelector('[data-maintenance-asset="MX000001"]');
  button(asset, MAINTENANCE_COPY.en.manual_service_log).click();
  let editor = form(fixture.card, "log_edit");
  setField(editor, "summary", "Replaced the filter manually");
  setField(editor, "task", JSON.stringify(["T000001", 2]));
  button(editor, MAINTENANCE_COPY.en.add_consumable).click();
  editor = form(fixture.card, "log_edit");
  const row = editor.querySelector('[data-maintenance-consumable="0"]');
  setField(row, "label", "Filter");
  setField(row, "unit", "piece");
  setField(row, "quantity", "1");
  // Unit change re-renders the pantry choices.
  editor = form(fixture.card, "log_edit");
  const refreshedRow = editor.querySelector('[data-maintenance-consumable="0"]');
  setField(refreshedRow, "pantry", JSON.stringify(["PI000001", 2]));
  submit(editor);
  const payload = fixture.card._maintenanceDraft.payload;
  assert.equal(payload.asset_id, "MX000001");
  assert.deepEqual(payload.task, { id: "T000001", revision: 2 });
  assert.deepEqual(payload.consumables_used, [
    { label: "Filter", unit: "piece", quantity: 1, pantry: { id: "PI000001", revision: 2 } },
  ]);
  assert.deepEqual(payload.attachment_ids, []);
});

test("service enable is reviewed and stale authority/private DOM are removed", async (t) => {
  const fixture = await setup(t);
  const serviceRow = fixture.card.shadowRoot.querySelector('[data-maintenance-service="D000001"]');
  button(serviceRow, MAINTENANCE_COPY.en.disable_service).click();
  let review = form(fixture.card, "review");
  assert.deepEqual(fixture.card._maintenanceDraft.payload, {
    id: "D000001", revision: 4, enabled: false, asset_revision: 3,
  });
  review.elements.reviewed.checked = true;
  review.elements.reviewed.dispatchEvent(new Event("change", { bubbles: true }));
  submit(review);
  await eventually(() => fixture.calls.length === 1 && fixture.card._maintenanceDraft === null);

  const child = await setup(t, { role: "child" });
  const row = child.card.shadowRoot.querySelector('[data-maintenance-asset="MX000001"]');
  button(row, MAINTENANCE_COPY.en.report_fault).click();
  const privateForm = form(child.card, "fault_edit");
  setField(privateForm, "details", "Private unfinished observation");
  privateForm.elements.details.focus();
  child.state.members.find((member) => member.id === "child-1").revision = 3;
  child.state.maintenance = { assets: [], faults: [], services: [], service_logs: [] };
  await child.card.refresh();
  assert.equal(privateForm.isConnected, false);
  assert.equal(child.card._maintenanceDraft, null);
  assert.equal(child.card.shadowRoot.textContent.includes("Private unfinished observation"), false);
  assert.equal(child.calls.length, 0);
});

test("fresh stale and detached forms are inert and setConfig clears drafts", async (t) => {
  const fixture = await setup(t, { role: "child" });
  const row = fixture.card.shadowRoot.querySelector('[data-maintenance-asset="MX000001"]');
  button(row, MAINTENANCE_COPY.en.report_fault).click();
  const old = form(fixture.card, "fault_edit");
  fixture.card.render();
  setField(old, "summary", "Detached value");
  submit(old);
  await tick();
  assert.equal(fixture.calls.length, 0);
  assert.ok(fixture.card._maintenanceDraft);

  fixture.card._data.maintenance.assets[0].revision = 4;
  const current = form(fixture.card, "fault_edit");
  setField(current, "summary", "Stale value");
  assert.equal(fixture.card._maintenanceDraft, null);
  assert.equal(fixture.calls.length, 0);

  button(fixture.card.shadowRoot.querySelector('[data-maintenance-asset="MX000001"]'), MAINTENANCE_COPY.en.report_fault).click();
  fixture.card.setConfig({ type: "custom:family-maintenance-card", entry_id: "next", language: "en" });
  assert.equal(fixture.card._maintenanceDraft, null);
});
