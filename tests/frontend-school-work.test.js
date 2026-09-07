import assert from "node:assert/strict";
import { test } from "node:test";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><body></body>", { url: "https://example.invalid" });
for (const key of ["window", "document", "HTMLElement", "customElements", "CustomEvent", "Event", "FormData"])
  globalThis[key] = dom.window[key];

await import("../custom_components/family_assistant/frontend/family-assistant.js");
const { reconcileSchoolWorkRefresh } = await import(
  "../custom_components/family_assistant/frontend/school-work-view.js"
);
const { SCHOOL_WORK_COPY } = await import(
  "../custom_components/family_assistant/frontend/school-work-copy.js"
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

function localDay(offset = 0, zone = "Europe/Kyiv") {
  const parts = new Intl.DateTimeFormat("en-US-u-ca-gregory-nu-latn", {
    timeZone: zone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  const day = new Date(`${values.year}-${values.month}-${values.day}T00:00:00Z`);
  day.setUTCDate(day.getUTCDate() + offset);
  return day.toISOString().slice(0, 10);
}

function task(overrides = {}) {
  return {
    id: "T000001",
    title: "Read chapter 4",
    assignee: "child-1",
    assignee_revision: 2,
    creator: "parent-1",
    due_at: "2026-10-25T00:30:00+00:00",
    created_at: "2026-09-07T07:00:00+00:00",
    status: "assigned",
    revision: 3,
    report_type: "text",
    report: null,
    delivery_scope: "private",
    managed_by: "school",
    deadline_policy: { reminder_minutes: 60, grace_minutes: 30, penalty: 0 },
    checklist: [{ text: "Pages 20–25", done: false }],
    source: {
      kind: "school_homework",
      member: "child-1",
      member_revision: 2,
      lesson: {
        timetable_id: "ST000001",
        timetable_revision: 4,
        date: localDay(1),
        lesson_index: 0,
      },
    },
    ...overrides,
  };
}

function timetable(overrides = {}) {
  return {
    id: "ST000001",
    member: "child-1",
    member_revision: 2,
    title: "School week",
    valid_from: "2026-01-01",
    valid_until: null,
    exceptions: [],
    lessons: [
      {
        weekday: (new Date(`${localDay(1)}T00:00:00Z`).getUTCDay() + 6) % 7,
        start: "09:00",
        end: "09:45",
        subject: "Mathematics",
        room: "12",
        materials: ["Workbook"],
      },
    ],
    backpack_routine: { id: "RT000001", revision: 5 },
    backpack_routine_current: { id: "RT000001", revision: 5, title: "Pack school bag" },
    status: "active",
    revision: 4,
    history: [],
    ...overrides,
  };
}

function stateFor(role = "parent") {
  const actor = role === "parent" ? "parent-1" : role === "owner" ? "owner-1" : role === "child" ? "child-1" : role === "adult" ? "adult-1" : "guest-1";
  const date = localDay(1);
  const table = timetable();
  const homework = role === "child" ? [{ ...task(), source: undefined }] : [task()];
  if (role === "adult" || role === "guest") homework.length = 0;
  return {
    revision: 1,
    actor,
    role,
    settings: {
      name: "Synthetic family",
      timezone: "Europe/Kyiv",
      modules: ["school", "tasks", "routines"],
    },
    members: [
      { id: "parent-1", name: "Parent One", role: "parent", active: true, revision: 1 },
      { id: "owner-1", name: "Owner One", role: "owner", active: true, revision: 1 },
      { id: "child-1", name: "Child One", role: "child", active: true, revision: 2 },
      { id: "child-2", name: "Child Two", role: "child", active: true, revision: 7 },
      { id: "adult-1", name: "Adult One", role: "adult", active: true, revision: 1 },
      { id: "guest-1", name: "Guest One", role: "guest", active: true, revision: 1 },
    ],
    school: {
      timetables: [table],
      upcoming: [
        {
          id: `${table.id}:${date}:0`,
          timetable_id: table.id,
          member: "child-1",
          date,
          start: "09:00",
          end: "09:45",
          subject: "Mathematics",
          room: "12",
          materials: ["Workbook"],
          backpack_routine: { id: "RT000001", revision: 5, title: "Pack school bag" },
        },
      ],
      homework,
      preparations: [],
    },
    routines: { templates: [] },
    tasks: [],
  };
}

async function setup(t, { role = "parent", language = "en" } = {}) {
  const state = stateFor(role);
  const calls = [];
  const receipts = new Map();
  let loseAction = null;
  let failBeforeAction = null;
  const execute = (message) => {
    calls.push(clone(message));
    if (receipts.has(message.operation_id)) return clone(receipts.get(message.operation_id));
    if (failBeforeAction === message.action) {
      failBeforeAction = null;
      const error = new Error("request failed before commit");
      error.code = "transport_error";
      throw error;
    }
    const payload = message.payload;
    let receipt;
    if (message.action === "school.homework_create") {
      const target = state.members.find((item) => item.id === payload.member);
      assert.equal(payload.member_revision, target.revision);
      const created = task({
        id: `T${String(state.school.homework.length + 2).padStart(6, "0")}`,
        title: payload.title,
        assignee: payload.member,
        assignee_revision: payload.member_revision,
        due_at: payload.due_at,
        checklist: payload.checklist.map((text) => ({ text, done: false })),
        deadline_policy: { reminder_minutes: payload.reminder_minutes, grace_minutes: payload.grace_minutes, penalty: 0 },
        source: { kind: "school_homework", member: payload.member, member_revision: payload.member_revision, lesson: clone(payload.lesson) },
        revision: 1,
      });
      state.school.homework.push(created);
      receipt = { id: created.id, revision: 1, status: "assigned" };
    } else if (message.action === "school.homework_revise") {
      const current = state.school.homework.find((item) => item.id === payload.id);
      assert.equal(current.revision, payload.revision);
      Object.assign(current, {
        title: payload.title,
        due_at: payload.due_at,
        assignee_revision: payload.member_revision,
        deadline_policy: { reminder_minutes: payload.reminder_minutes, grace_minutes: payload.grace_minutes, penalty: 0 },
        revision: current.revision + 1,
      });
      current.source.member_revision = payload.member_revision;
      receipt = { id: current.id, revision: current.revision, status: current.status };
    } else if (message.action === "school.backpack_start") {
      const marker = {
        id: "SP000001",
        revision: 1,
        status: "started",
        timetable_id: payload.timetable_id,
        member: payload.member,
        date: payload.date,
        run_id: "RR000001",
        run_status: "active",
      };
      state.school.preparations.push(marker);
      receipt = { id: marker.id, revision: 1, status: "started", run_id: marker.run_id };
    } else {
      throw new Error(`Unexpected action ${message.action}`);
    }
    receipts.set(message.operation_id, receipt);
    if (loseAction === message.action) {
      loseAction = null;
      const error = new Error("response lost");
      error.code = "response_lost";
      throw error;
    }
    return clone(receipt);
  };
  const card = document.createElement("family-school-card");
  card.setConfig({ type: "custom:family-school-card", entry_id: "synthetic", language });
  document.body.append(card);
  t.after(() => card.remove());
  card.hass = {
    language,
    callWS: async (message) => {
      if (message.type === "family_assistant/view") return clone(state);
      if (message.type === "family_assistant/execute") return execute(message);
      throw new Error(`Unexpected WS ${message.type}`);
    },
  };
  await eventually(() => card._data?.actor === state.actor);
  return {
    card,
    state,
    calls,
    lose(action) {
      loseAction = action;
    },
    failBefore(action) {
      failBeforeAction = action;
    },
  };
}

function button(card, label) {
  return [...card.shadowRoot.querySelectorAll("button")].find((item) => item.textContent === label);
}

function input(root, name) {
  return root.querySelector(`[name="${name}"]`);
}

test("render is pure and adult, guest, and module gates expose no school work", async (t) => {
  const fixture = await setup(t);
  const before = clone(fixture.state);
  fixture.card.render();
  assert.deepEqual(fixture.state, before);

  for (const role of ["adult", "guest"]) {
    const isolated = await setup(t, { role });
    assert.equal(isolated.card.shadowRoot.querySelector(".school-work"), null);
    assert.equal(isolated.card._schoolWorkDraft, null);
  }
  fixture.state.settings.modules = ["school"];
  await fixture.card.refresh();
  assert.equal(button(fixture.card, SCHOOL_WORK_COPY.en.new_homework), undefined);
  assert.equal(button(fixture.card, SCHOOL_WORK_COPY.en.start_preparation), undefined);
});

test("child creates only own private homework after exact review", async (t) => {
  const { card, calls } = await setup(t, { role: "child" });
  button(card, SCHOOL_WORK_COPY.en.new_homework).click();
  const form = card.shadowRoot.querySelector('[data-school-work-editor="homework_create"]');
  assert.equal(input(form, "member"), null);
  input(form, "title").value = "Finish algebra";
  input(form, "checklist").value = "Exercises 1–4\nPack workbook";
  input(form, "lesson").value = "0";
  input(form, "reminder_minutes").value = "30";
  input(form, "grace_minutes").value = "15";
  form.querySelector('button[type="submit"]').click();
  assert.equal(calls.length, 0);
  const review = card.shadowRoot.querySelector('[data-school-work-review="homework_create"]');
  assert.match(review.textContent, /Child One/);
  assert.match(review.textContent, /Mathematics/);
  review.querySelector('input[type="checkbox"]').checked = true;
  review.querySelector('button[type="submit"]').click();
  await eventually(() => calls.length === 1);
  assert.equal(calls[0].action, "school.homework_create");
  assert.deepEqual(calls[0].payload, {
    member: "child-1",
    member_revision: 2,
    title: "Finish algebra",
    due_at: null,
    checklist: ["Exercises 1–4", "Pack workbook"],
    reminder_minutes: 30,
    grace_minutes: 15,
    lesson: {
      timetable_id: "ST000001",
      timetable_revision: 4,
      date: localDay(1),
      lesson_index: 0,
    },
  });
  assert.equal(typeof calls[0].operation_id, "string");
  await eventually(() => card._schoolWorkDraft === null);
});

test("parent revise preserves checklist and ambiguous due instant in named review", async (t) => {
  const { card, calls } = await setup(t);
  button(card, SCHOOL_WORK_COPY.en.revise_homework).click();
  const form = card.shadowRoot.querySelector('[data-school-work-editor="homework_revise"]');
  input(form, "title").value = "Read chapter carefully";
  assert.equal(input(form, "checklist"), null);
  form.querySelector('button[type="submit"]').click();
  const review = card.shadowRoot.querySelector('[data-school-work-review="homework_revise"]');
  assert.match(review.textContent, /Pages 20–25/);
  assert.match(review.textContent, /Child One/);
  review.querySelector('input[type="checkbox"]').checked = true;
  review.querySelector('button[type="submit"]').click();
  await eventually(() => calls.length === 1);
  assert.deepEqual(calls[0].payload, {
    id: "T000001",
    revision: 3,
    member_revision: 2,
    title: "Read chapter carefully",
    due_at: "2026-10-25T00:30:00+00:00",
    reminder_minutes: 60,
    grace_minutes: 30,
  });
});

test("lost revise response retries the frozen payload and operation after task advancement", async (t) => {
  const { card, state, calls, lose } = await setup(t);
  lose("school.homework_revise");
  button(card, SCHOOL_WORK_COPY.en.revise_homework).click();
  const form = card.shadowRoot.querySelector('[data-school-work-editor="homework_revise"]');
  input(form, "title").value = "Frozen named revision";
  form.querySelector('button[type="submit"]').click();
  let review = card.shadowRoot.querySelector('[data-school-work-review="homework_revise"]');
  review.querySelector('input[type="checkbox"]').checked = true;
  review.querySelector('button[type="submit"]').click();
  await eventually(
    () =>
      calls.length === 1 &&
      card._schoolWorkDraft?.pending &&
      !card._writing &&
      card.shadowRoot.querySelector('[data-school-work-review="homework_revise"]'),
  );
  assert.equal(state.school.homework[0].revision, 4);
  assert.match(card.shadowRoot.textContent, /Frozen named revision/);
  const frozen = clone(card._schoolWorkDraft.pending);
  review = card.shadowRoot.querySelector('[data-school-work-review="homework_revise"]');
  review.querySelector('input[type="checkbox"]').checked = true;
  review.querySelector('button[type="submit"]').click();
  await eventually(() => calls.length === 2);
  assert.equal(calls[1].operation_id, calls[0].operation_id);
  assert.deepEqual(calls[1].payload, frozen.payload);
  assert.equal(calls[1].payload.revision, 3);
  await eventually(() => card._schoolWorkDraft === null);
});

test("stale child epoch revise names the reassignment reset and freezes current member revision", async (t) => {
  const { card, state, calls } = await setup(t);
  const current = state.members.find((item) => item.id === "child-1");
  current.revision = 3;
  state.school.homework[0].assignee_revision = 2;
  state.school.homework[0].source.member_revision = 2;
  await card.refresh();
  button(card, SCHOOL_WORK_COPY.en.revise_homework).click();
  const editor = card.shadowRoot.querySelector('[data-school-work-editor="homework_revise"]');
  assert.match(editor.textContent, /reassigns this homework/i);
  input(editor, "title").value = "Reapprove current child";
  editor.querySelector('button[type="submit"]').click();
  const review = card.shadowRoot.querySelector('[data-school-work-review="homework_revise"]');
  assert.match(review.textContent, /progress, report, review note, and deadline state reset/i);
  review.querySelector('input[type="checkbox"]').checked = true;
  review.querySelector('button[type="submit"]').click();
  await eventually(() => calls.length === 1);
  assert.equal(calls[0].payload.member_revision, 3);
  assert.equal(calls[0].payload.id, "T000001");
});

test("stale child epoch revise retries the same operation after failure before commit", async (t) => {
  const { card, state, calls, failBefore } = await setup(t);
  const current = state.members.find((item) => item.id === "child-1");
  current.revision = 3;
  state.school.homework[0].assignee_revision = 2;
  state.school.homework[0].source.member_revision = 2;
  await card.refresh();
  failBefore("school.homework_revise");
  button(card, SCHOOL_WORK_COPY.en.revise_homework).click();
  const editor = card.shadowRoot.querySelector('[data-school-work-editor="homework_revise"]');
  input(editor, "title").value = "Frozen epoch rebind";
  editor.querySelector('button[type="submit"]').click();
  let review = card.shadowRoot.querySelector('[data-school-work-review="homework_revise"]');
  review.querySelector('input[type="checkbox"]').checked = true;
  review.querySelector('button[type="submit"]').click();
  await eventually(
    () => calls.length === 1 && card._schoolWorkDraft?.pending && !card._writing,
  );
  assert.equal(state.school.homework[0].revision, 3);
  assert.equal(state.school.homework[0].assignee_revision, 2);
  const frozen = clone(card._schoolWorkDraft.pending);
  review = card.shadowRoot.querySelector('[data-school-work-review="homework_revise"]');
  review.querySelector('input[type="checkbox"]').checked = true;
  review.querySelector('button[type="submit"]').click();
  await eventually(() => calls.length === 2);
  assert.equal(calls[1].operation_id, calls[0].operation_id);
  assert.deepEqual(calls[1].payload, frozen.payload);
  assert.equal(calls[1].payload.member_revision, 3);
});

test("backpack preparation freezes exactly seven source fields and shows honest run marker", async (t) => {
  const { card, calls } = await setup(t);
  button(card, SCHOOL_WORK_COPY.en.start_preparation).click();
  const review = card.shadowRoot.querySelector('[data-school-work-review="backpack_start"]');
  assert.match(review.textContent, /Pack school bag/);
  assert.match(review.textContent, /School week \(version 4\)/);
  assert.equal(calls.length, 0);
  review.querySelector('input[type="checkbox"]').checked = true;
  review.querySelector('button[type="submit"]').click();
  await eventually(() => calls.length === 1);
  assert.equal(calls[0].action, "school.backpack_start");
  assert.deepEqual(Object.keys(calls[0].payload).sort(), [
    "date",
    "member",
    "member_revision",
    "routine_id",
    "routine_revision",
    "timetable_id",
    "timetable_revision",
  ]);
  await eventually(() => card.shadowRoot.querySelector('[data-school-preparation="SP000001"]'));
  const marker = card.shadowRoot.querySelector('[data-school-preparation="SP000001"]');
  assert.match(marker.textContent, /active/i);
  assert.match(card.shadowRoot.textContent, /Routines card/);
});

test("focused private form is cleared on identity, epoch, and module revocation", async (t) => {
  const { card, state } = await setup(t);
  button(card, SCHOOL_WORK_COPY.en.revise_homework).click();
  const form = card.shadowRoot.querySelector('[data-school-work-editor="homework_revise"]');
  input(form, "title").value = "Private unsaved note";
  input(form, "title").focus();
  state.members.find((item) => item.id === "parent-1").revision += 1;
  await card.refresh();
  assert.equal(card._schoolWorkDraft, null);
  assert.doesNotMatch(card.shadowRoot.textContent, /Private unsaved note/);

  button(card, SCHOOL_WORK_COPY.en.revise_homework).click();
  state.settings.timezone = "UTC";
  await card.refresh();
  assert.equal(card._schoolWorkDraft, null);

  button(card, SCHOOL_WORK_COPY.en.revise_homework).click();
  state.settings.modules = ["school", "routines"];
  await card.refresh();
  assert.equal(card._schoolWorkDraft, null);
  assert.equal(card.shadowRoot.querySelector('[data-school-work-editor="homework_revise"]'), null);
});

test("task statuses and deadlines use localized task copy and household wall time", async (t) => {
  const ru = await setup(t, { language: "ru" });
  const row = ru.card.shadowRoot.querySelector('[data-school-homework="T000001"]');
  assert.match(row.textContent, /Назначена/);
  assert.match(row.textContent, /Europe\/Kyiv/);
  assert.doesNotMatch(row.textContent, /2026-10-25T00:30:00\+00:00/);

  const uk = await setup(t, { language: "uk" });
  assert.match(
    uk.card.shadowRoot.querySelector('[data-school-homework="T000001"]').textContent,
    /Призначено/,
  );
});

test("detached controls and stale target revisions are inert; setConfig clears draft", async (t) => {
  const { card, state, calls } = await setup(t);
  button(card, SCHOOL_WORK_COPY.en.new_homework).click();
  const staleForm = card.shadowRoot.querySelector('[data-school-work-editor="homework_create"]');
  input(staleForm, "title").value = "Detached secret";
  input(staleForm, "checklist").value = "One step";
  card.render();
  staleForm.dispatchEvent(new dom.window.Event("submit", { bubbles: true, cancelable: true }));
  await tick();
  assert.equal(calls.length, 0);

  const liveForm = card.shadowRoot.querySelector('[data-school-work-editor="homework_create"]');
  state.members.find((item) => item.id === "child-1").revision += 1;
  liveForm.dispatchEvent(new dom.window.Event("submit", { bubbles: true, cancelable: true }));
  await tick();
  assert.equal(calls.length, 0);

  card.setConfig({ type: "custom:family-school-card", entry_id: "synthetic", language: "en" });
  assert.equal(card._schoolWorkDraft, null);
});

test("reconcile forces removal when a visible private homework row disappears", async (t) => {
  const { card, state } = await setup(t, { role: "child" });
  assert.match(card.shadowRoot.textContent, /Read chapter 4/);
  const previous = clone(state);
  state.school.homework = [];
  card._data = clone(state);
  assert.equal(reconcileSchoolWorkRefresh(card, previous), true);
  card.render();
  assert.doesNotMatch(card.shadowRoot.textContent, /Read chapter 4/);
});

test("English, Russian, and Ukrainian copy retains explicit privacy and routine wording", () => {
  for (const language of ["en", "ru", "uk"]) {
    assert.deepEqual(
      Object.keys(SCHOOL_WORK_COPY[language]).sort(),
      Object.keys(SCHOOL_WORK_COPY.en).sort(),
    );
    assert.ok(SCHOOL_WORK_COPY[language].private_hint);
    assert.ok(SCHOOL_WORK_COPY[language].routines_hint);
    assert.ok(SCHOOL_WORK_COPY[language].confirm_homework);
    assert.ok(SCHOOL_WORK_COPY[language].confirm_preparation);
  }
});
