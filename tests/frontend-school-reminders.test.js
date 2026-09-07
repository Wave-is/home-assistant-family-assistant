import assert from "node:assert/strict";
import { test } from "node:test";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><body></body>", { url: "https://example.invalid" });
for (const key of ["window", "document", "HTMLElement", "customElements", "CustomEvent", "Event", "FormData"])
  globalThis[key] = dom.window[key];

await import("../custom_components/family_assistant/frontend/family-assistant.js");
const { reconcileSchoolRemindersRefresh } = await import(
  "../custom_components/family_assistant/frontend/school-reminders-view.js"
);
const { SCHOOL_REMINDERS_COPY } = await import(
  "../custom_components/family_assistant/frontend/school-reminders-copy.js"
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

function stateFor(role = "parent", { policyEnabled = true, routines = true } = {}) {
  const actor =
    role === "owner"
      ? "owner-1"
      : role === "parent"
        ? "parent-1"
        : role === "child"
          ? "child-1"
          : role === "adult"
            ? "adult-1"
            : "guest-1";
  const activeRole = ["owner", "parent", "child"].includes(role);
  return {
    revision: 1,
    actor,
    role,
    settings: {
      name: "Synthetic family",
      timezone: "Europe/Kyiv",
      modules: ["school", ...(routines ? ["routines"] : [])],
    },
    members: [
      { id: "owner-1", name: "Owner One", role: "owner", active: true, revision: 2 },
      { id: "parent-1", name: "Parent One", role: "parent", active: true, revision: 4 },
      { id: "child-1", name: "Child One", role: "child", active: true, revision: 7 },
      { id: "child-2", name: "Child Two", role: "child", active: true, revision: 9 },
      { id: "adult-1", name: "Adult One", role: "adult", active: true, revision: 3 },
      { id: "guest-1", name: "Guest One", role: "guest", active: true, revision: 5 },
    ],
    school: {
      timetables: [],
      upcoming: [],
      homework: [],
      preparations: [],
      preparation_reminders: activeRole
        ? {
            policy: {
              enabled: policyEnabled,
              days_before: 1,
              time: "20:00",
              timezone: "Europe/Kyiv",
            },
            self_targets:
              role === "child"
                ? [
                    {
                      member: "child-1",
                      member_revision: 7,
                      recipient_revision: 7,
                      enabled: false,
                      subscription_revision: null,
                    },
                  ]
                : [
                    {
                      member: "child-1",
                      member_revision: 7,
                      recipient_revision: role === "owner" ? 2 : 4,
                      enabled: false,
                      subscription_revision: null,
                    },
                    {
                      member: "child-2",
                      member_revision: 9,
                      recipient_revision: role === "owner" ? 2 : 4,
                      enabled: true,
                      subscription_revision: 3,
                    },
                  ],
          }
        : { policy: null, self_targets: [] },
    },
    routines: { templates: [] },
    tasks: [],
  };
}

async function setup(t, options = {}) {
  const state = stateFor(options.role, options);
  const calls = [];
  const receipts = new Map();
  let loseNext = false;
  let failBefore = false;
  const execute = (message) => {
    calls.push(clone(message));
    if (receipts.has(message.operation_id)) return clone(receipts.get(message.operation_id));
    if (message.action === "pantry.meal_save") return { id: "MP000001", revision: 1, status: "draft" };
    assert.equal(message.action, "school.preparation_reminder_access_set");
    if (failBefore) {
      failBefore = false;
      const error = new Error("request failed before commit");
      error.code = "transport_error";
      throw error;
    }
    const current = state.school.preparation_reminders.self_targets.find(
      (row) => row.member === message.payload.member,
    );
    assert.ok(current);
    assert.deepEqual(message.payload, {
      member: current.member,
      member_revision: current.member_revision,
      recipient_revision: current.recipient_revision,
      subscription_revision: current.subscription_revision,
      enabled: !current.enabled,
    });
    const revision = current.subscription_revision === null ? 1 : current.subscription_revision + 1;
    current.enabled = message.payload.enabled;
    current.subscription_revision = revision;
    const receipt = { member: current.member, enabled: current.enabled, revision };
    receipts.set(message.operation_id, receipt);
    if (loseNext) {
      loseNext = false;
      const error = new Error("response lost");
      error.code = "response_lost";
      throw error;
    }
    return clone(receipt);
  };

  const card = document.createElement("family-school-card");
  card.setConfig({ type: "custom:family-school-card", entry_id: "synthetic", language: options.language || "en" });
  document.body.append(card);
  t.after(() => card.remove());
  card.hass = {
    language: options.language || "en",
    callWS: async (message) => {
      if (message.type === "family_assistant/view") return clone(state);
      if (message.type === "family_assistant/execute") return execute(message);
      throw new Error(`Unexpected WS ${message.type}`);
    },
  };
  await eventually(
    () =>
      card._data?.actor === state.actor &&
      (!state.school.preparation_reminders.policy || card.shadowRoot.querySelector(".school-reminders")),
  );
  return {
    card,
    state,
    calls,
    lose() {
      loseNext = true;
    },
    failBefore() {
      failBefore = true;
    },
  };
}

function button(card, label) {
  return [...card.shadowRoot.querySelectorAll("button")].find((item) => item.textContent === label);
}

function confirmReview(card) {
  const checkbox = card.shadowRoot.querySelector('.school-reminder-review input[name="confirmed"]');
  assert.ok(checkbox);
  checkbox.checked = true;
  checkbox.dispatchEvent(new Event("change", { bubbles: true }));
}

test("English, Russian, and Ukrainian reminder copy has exact key parity", () => {
  const english = Object.keys(SCHOOL_REMINDERS_COPY.en).sort();
  assert.deepEqual(Object.keys(SCHOOL_REMINDERS_COPY.ru).sort(), english);
  assert.deepEqual(Object.keys(SCHOOL_REMINDERS_COPY.uk).sort(), english);
  for (const locale of Object.values(SCHOOL_REMINDERS_COPY))
    for (const value of Object.values(locale)) assert.ok(value.trim());
});

test("render is pure and role/module revocation removes reminder content", async (t) => {
  const fixture = await setup(t);
  const before = clone(fixture.state);
  fixture.card.render();
  assert.deepEqual(fixture.state, before);
  assert.equal(fixture.card.shadowRoot.querySelectorAll(".school-reminder-row").length, 2);

  for (const role of ["adult", "guest"]) {
    const hidden = await setup(t, { role });
    assert.equal(hidden.card.shadowRoot.querySelector(".school-reminders"), null);
    assert.equal(hidden.card._schoolReminderDraft, null);
  }

  fixture.state.settings.modules = ["routines"];
  await fixture.card.refresh();
  assert.equal(fixture.card.shadowRoot.querySelector(".school-reminders"), null);
  assert.equal(fixture.card._schoolReminderDraft, null);
});

test("child sees and can review only the projected self preference", async (t) => {
  const { card, calls } = await setup(t, { role: "child", language: "uk" });
  const rows = card.shadowRoot.querySelectorAll(".school-reminder-row");
  assert.equal(rows.length, 1);
  assert.equal(rows[0].dataset.schoolReminderMember, "child-1");
  button(card, SCHOOL_REMINDERS_COPY.uk.enable).click();
  assert.equal(calls.length, 0);
  assert.match(card.shadowRoot.querySelector(".school-reminder-review").textContent, /Child One/);
});

test("globally off and Routines off explain no scheduling but still save a preference", async (t) => {
  const { card, calls } = await setup(t, { policyEnabled: false, routines: false });
  assert.ok(card.shadowRoot.querySelector(".school-reminder-policy"));
  assert.ok(card.shadowRoot.querySelector(".school-reminder-routines-off"));
  button(card, SCHOOL_REMINDERS_COPY.en.enable).click();
  confirmReview(card);
  button(card, SCHOOL_REMINDERS_COPY.en.save).click();
  await eventually(() => calls.length === 1 && card._schoolReminderDraft === null);
  assert.equal(calls[0].payload.subscription_revision, null);
  assert.equal(calls[0].payload.enabled, true);
});

test("exact named review sends all revisions and cleans up after success", async (t) => {
  const { card, calls } = await setup(t);
  button(card, SCHOOL_REMINDERS_COPY.en.disable).click();
  assert.equal(calls.length, 0);
  const review = card.shadowRoot.querySelector(".school-reminder-review");
  assert.match(review.textContent, /Child Two/);
  assert.match(review.textContent, /Parent One/);
  confirmReview(card);
  button(card, SCHOOL_REMINDERS_COPY.en.save).click();
  await eventually(() => calls.length === 1 && card._schoolReminderDraft === null);
  assert.deepEqual(calls[0].payload, {
    member: "child-2",
    member_revision: 9,
    recipient_revision: 4,
    subscription_revision: 3,
    enabled: false,
  });
  assert.equal(typeof calls[0].operation_id, "string");
});

test("failed-before-commit retry preserves the exact payload and operation id", async (t) => {
  const fixture = await setup(t);
  fixture.failBefore();
  button(fixture.card, SCHOOL_REMINDERS_COPY.en.enable).click();
  confirmReview(fixture.card);
  button(fixture.card, SCHOOL_REMINDERS_COPY.en.save).click();
  await eventually(() => fixture.calls.length === 1 && fixture.card._schoolReminderDraft?.pending && !fixture.card._writing);
  const frozen = clone(fixture.card._schoolReminderDraft.pending);
  button(fixture.card, SCHOOL_REMINDERS_COPY.en.retry).click();
  await eventually(() => fixture.calls.length === 2 && fixture.card._schoolReminderDraft === null);
  assert.deepEqual(fixture.calls[1].payload, frozen.payload);
  assert.equal(fixture.calls[1].operation_id, frozen.operation_id);
});

test("committed response loss retries the frozen operation after unrelated pending state", async (t) => {
  const fixture = await setup(t);
  fixture.lose();
  button(fixture.card, SCHOOL_REMINDERS_COPY.en.disable).click();
  confirmReview(fixture.card);
  button(fixture.card, SCHOOL_REMINDERS_COPY.en.save).click();
  await eventually(() => fixture.calls.length === 1 && fixture.card._schoolReminderDraft?.pending && !fixture.card._writing);
  const frozen = clone(fixture.card._schoolReminderDraft.pending);
  assert.ok(Object.isFrozen(fixture.card._schoolReminderDraft.pending));
  assert.ok(Object.isFrozen(fixture.card._schoolReminderDraft.pending.payload));
  assert.equal(fixture.state.school.preparation_reminders.self_targets[1].subscription_revision, 4);
  await fixture.card.command("pantry.meal_save", { week_start: "2026-09-07", title: "Other section", entries: [], note: "" });
  button(fixture.card, SCHOOL_REMINDERS_COPY.en.retry).click();
  await eventually(() => fixture.calls.length === 3 && fixture.card._schoolReminderDraft === null);
  assert.equal(fixture.calls[2].operation_id, frozen.operation_id);
  assert.deepEqual(fixture.calls[2].payload, frozen.payload);
});

test("stale revisions, result-version drift, and detached controls are inert", async (t) => {
  const stale = await setup(t);
  const oldOpen = button(stale.card, SCHOOL_REMINDERS_COPY.en.enable);
  const replacement = clone(stale.card._data);
  replacement.school.preparation_reminders.self_targets[0].member_revision = 8;
  replacement.members.find((item) => item.id === "child-1").revision = 8;
  stale.card._data = replacement;
  oldOpen.click();
  assert.equal(stale.card._schoolReminderDraft, null);
  assert.equal(stale.calls.length, 0);

  const drift = await setup(t);
  drift.lose();
  button(drift.card, SCHOOL_REMINDERS_COPY.en.disable).click();
  confirmReview(drift.card);
  button(drift.card, SCHOOL_REMINDERS_COPY.en.save).click();
  await eventually(() => drift.card._schoolReminderDraft?.pending && !drift.card._writing);
  const previous = clone(drift.card._data);
  drift.card._data.school.preparation_reminders.self_targets[1].subscription_revision = 5;
  assert.equal(reconcileSchoolRemindersRefresh(drift.card, previous), true);
  assert.equal(drift.card._schoolReminderDraft, null);

  const detached = await setup(t);
  const detachedOpen = button(detached.card, SCHOOL_REMINDERS_COPY.en.enable);
  detached.card.remove();
  detachedOpen.click();
  assert.equal(detached.card._schoolReminderDraft, null);
  assert.equal(detached.calls.length, 0);
});

test("actor, entry, generation, and target epoch changes invalidate reviews", async (t) => {
  for (const change of [
    (fixture) => {
      fixture.card._data.role = "adult";
      fixture.card._data.members.find((item) => item.id === "parent-1").role = "adult";
    },
    (fixture) => {
      fixture.card._entry = "another-entry";
    },
    (fixture) => {
      fixture.card._generation += 1;
    },
    (fixture) => {
      fixture.card._data.members.find((item) => item.id === "child-1").revision = 8;
      fixture.card._data.school.preparation_reminders.self_targets[0].member_revision = 8;
    },
  ]) {
    const fixture = await setup(t);
    button(fixture.card, SCHOOL_REMINDERS_COPY.en.enable).click();
    confirmReview(fixture.card);
    const save = button(fixture.card, SCHOOL_REMINDERS_COPY.en.save);
    change(fixture);
    save.click();
    assert.equal(fixture.calls.length, 0);
    assert.equal(fixture.card._schoolReminderDraft, null);
  }
});
