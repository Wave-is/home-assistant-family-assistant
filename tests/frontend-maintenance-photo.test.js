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

function state() {
  return {
    revision: 1,
    actor: "parent-1",
    role: "parent",
    settings: {
      name: "Synthetic family",
      timezone: "Europe/Kyiv",
      modules: ["maintenance", "tasks"],
    },
    members: [
      {
        id: "parent-1",
        name: "Parent One",
        role: "parent",
        active: true,
        revision: 1,
      },
      {
        id: "adult-1",
        name: "Adult One",
        role: "adult",
        active: true,
        revision: 2,
      },
    ],
    tasks: [],
    maintenance: {
      assets: [
        {
          id: "MX000001",
          revision: 3,
          name: "Heating boiler",
          category: "Heating",
          location: "Utility room",
          responsible_member: "adult-1",
          responsible_member_revision: 2,
          warranty: { expires_on: null, vendor: "", reference: "" },
          consumables: [],
          note: "Parent-only note",
          reportable: false,
          approved_by: "parent-1",
          approved_by_revision: 1,
          status: "active",
          current: true,
          can_report: true,
          history: [],
        },
      ],
      faults: [],
      service_logs: [],
      services: [
        {
          id: "D000001",
          revision: 4,
          asset_id: "MX000001",
          asset_revision: 3,
          title: "Photograph boiler gauge",
          report_type: "photo",
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
          deadline_policy: {
            reminder_minutes: 60,
            grace_minutes: 30,
            penalty: 0,
          },
          effective_at: "2026-09-07T08:00:00+00:00",
          current: true,
        },
      ],
    },
  };
}

async function setup(t) {
  const current = state();
  const calls = [];
  const receipts = new Map();
  let loseNext = false;
  const card = document.createElement("family-maintenance-card");
  card.setConfig({
    type: "custom:family-maintenance-card",
    entry_id: "synthetic",
    language: "en",
  });
  document.body.append(card);
  t.after(() => card.remove());

  card.hass = {
    language: "en",
    callWS: async (message) => {
      if (message.type === "family_assistant/view") return clone(current);
      assert.equal(message.type, "family_assistant/execute");
      assert.equal(message.action, "maintenance.service_save");
      calls.push(clone(message));
      if (receipts.has(message.operation_id))
        return clone(receipts.get(message.operation_id));
      const service = current.maintenance.services.find(
        (item) => item.id === message.payload.id,
      );
      assert.ok(service);
      assert.equal(service.revision, message.payload.revision);
      Object.assign(service, clone(message.payload), {
        assignees: message.payload.assignees.map((item) => item.id),
        deadline_policy: {
          reminder_minutes: message.payload.reminder_minutes,
          grace_minutes: message.payload.grace_minutes,
          penalty: 0,
        },
        revision: service.revision + 1,
        current: true,
      });
      const receipt = {
        id: service.id,
        revision: service.revision,
        enabled: service.enabled,
      };
      receipts.set(message.operation_id, clone(receipt));
      current.revision += 1;
      if (loseNext) {
        loseNext = false;
        throw { code: "storage_error" };
      }
      return receipt;
    },
  };
  await eventually(() => Boolean(card._data) && !card._loading);
  return {
    card,
    current,
    calls,
    lose() {
      loseNext = true;
    },
  };
}

function button(root, label) {
  const result = [...root.querySelectorAll("button")].find(
    (item) => item.textContent === label,
  );
  assert.ok(result, `missing button: ${label}`);
  return result;
}

function form(card, kind) {
  const result = card.shadowRoot.querySelector(
    `[data-maintenance-form="${kind}"]`,
  );
  assert.ok(result, `missing form: ${kind}`);
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

test("service photo choice is localized, exact-reviewed, and retried frozen", async (t) => {
  for (const locale of Object.values(MAINTENANCE_COPY))
    assert.deepEqual(
      Object.keys(locale).sort(),
      Object.keys(MAINTENANCE_COPY.en).sort(),
    );

  const fixture = await setup(t);
  const serviceRow = fixture.card.shadowRoot.querySelector(
    '[data-maintenance-service="D000001"]',
  );
  assert.ok(serviceRow);
  button(serviceRow, MAINTENANCE_COPY.en.edit_service).click();
  const editor = form(fixture.card, "service_edit");
  const reportType = editor.querySelector('select[name="report_type"]');
  assert.ok(reportType);
  assert.equal(reportType.value, "photo");
  assert.deepEqual(
    [...reportType.options].map((item) => [item.value, item.textContent]),
    [
      ["text", MAINTENANCE_COPY.en.report_text],
      ["photo", MAINTENANCE_COPY.en.report_photo],
    ],
  );

  submit(editor);
  let review = form(fixture.card, "review");
  const draft = fixture.card._maintenanceDraft;
  assert.equal(draft.payload.report_type, "photo");
  assert.ok(Object.isFrozen(draft.payload));
  assert.match(review.textContent, /Completion report: Photo report/);
  setField(review, "reviewed", true);
  fixture.lose();
  submit(review);
  await eventually(
    () => fixture.calls.length === 1 && fixture.card._maintenanceDraft?.pending,
  );
  const first = clone(fixture.calls[0]);
  assert.equal(first.payload.report_type, "photo");
  assert.ok(Object.isFrozen(fixture.card._maintenanceDraft.pending));

  review = form(fixture.card, "review");
  submit(review);
  await eventually(
    () => fixture.calls.length === 2 && fixture.card._maintenanceDraft === null,
  );
  assert.deepEqual(fixture.calls[1].payload, first.payload);
  assert.equal(fixture.calls[1].operation_id, first.operation_id);
  assert.equal(fixture.current.maintenance.services[0].report_type, "photo");

  const asset = fixture.card.shadowRoot.querySelector(
    '[data-maintenance-asset="MX000001"]',
  );
  button(asset, MAINTENANCE_COPY.en.new_service).click();
  const fresh = form(fixture.card, "service_edit");
  assert.equal(fresh.querySelector('select[name="report_type"]').value, "text");
});
