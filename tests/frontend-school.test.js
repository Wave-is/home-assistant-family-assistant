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

await import(
  "../custom_components/family_assistant/frontend/family-assistant.js"
);
const { SCHOOL_COPY } = await import(
  "../custom_components/family_assistant/frontend/school-copy.js"
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

function timetable(overrides = {}) {
  return {
    id: "ST000001",
    member: "child-1",
    title: "School week",
    valid_from: "2026-09-07",
    valid_until: null,
    exceptions: ["2026-09-14"],
    lessons: [
      {
        weekday: 0,
        start: "08:00",
        end: "09:00",
        subject: "Mathematics",
        room: "12",
        materials: ["Workbook"],
      },
    ],
    backpack_routine: { id: "RT000001", revision: 5 },
    backpack_routine_current: {
      id: "RT000001",
      revision: 5,
      title: "Pack school bag",
    },
    status: "active",
    revision: 3,
    history: [
      {
        actor: "parent-1",
        at: "2026-09-07T06:00:00+00:00",
        action: "created",
      },
    ],
    ...overrides,
  };
}

function stateFor(role = "parent") {
  const actor =
    role === "parent"
      ? "parent-1"
      : role === "owner"
        ? "owner-1"
        : role === "child"
          ? "child-1"
          : "adult-1";
  const members = [
    {
      id: "parent-1",
      name: "Parent One",
      role: "parent",
      active: true,
      revision: 1,
    },
    {
      id: "owner-1",
      name: "Owner One",
      role: "owner",
      active: true,
      revision: 4,
    },
    {
      id: "child-1",
      name: "Child One",
      role: "child",
      active: true,
      revision: 2,
    },
    {
      id: "child-2",
      name: "Child Two",
      role: "child",
      active: true,
      revision: 1,
    },
    {
      id: "former-1",
      name: "Former Child",
      role: "adult",
      active: true,
      revision: 3,
    },
    {
      id: "adult-1",
      name: "Adult One",
      role: "adult",
      active: true,
      revision: 1,
    },
  ];
  const timetables = [
    timetable(),
    timetable({
      id: "ST000002",
      member: "former-1",
      title: "Old school timetable",
      backpack_routine: null,
      backpack_routine_current: null,
      revision: 7,
      history: [],
    }),
  ];
  const upcoming = [
    {
      id: "ST000001:2026-09-08:0",
      timetable_id: "ST000001",
      member: "child-1",
      date: "2026-09-08",
      start: "08:00",
      end: "09:00",
      subject: "<b>Mathematics</b>",
      room: "12",
      materials: ["Workbook"],
      backpack_routine: {
        id: "RT000001",
        revision: 5,
        title: "Pack school bag",
      },
    },
    {
      id: "other-child-lesson",
      timetable_id: "ST999999",
      member: "child-2",
      date: "2026-09-08",
      start: "10:00",
      end: "11:00",
      subject: "Other child's lesson",
      room: "",
      materials: ["Private other material"],
      backpack_routine: null,
    },
  ];
  return {
    revision: 1,
    actor,
    role,
    settings: {
      name: "Synthetic family",
      timezone: "Europe/Kyiv",
      modules: ["school", "routines", "pantry"],
    },
    members,
    school: { timetables, upcoming },
    routines: {
      templates: [
        {
          id: "RT000001",
          revision: 5,
          title: "Pack school bag",
          creator: "owner-1",
          enabled: true,
          assignees: ["child-1", "child-2"],
          steps: [{ title: "Books", assignee: "child-1" }],
        },
        {
          id: "RT000002",
          revision: 1,
          title: "Disabled routine",
          creator: "owner-1",
          enabled: false,
          assignees: ["child-2"],
          steps: [],
        },
      ],
    },
    pantry: { meal_plans: [], meal_shopping: [] },
  };
}

function locateRecord(state, id) {
  return state.school.timetables.find((record) => record.id === id);
}

async function setup(t, { role = "parent" } = {}) {
  const state = stateFor(role);
  const calls = [];
  const receipts = new Map();
  let lostAction = null;
  const card = document.createElement("family-school-card");
  card.setConfig({
    type: "custom:family-school-card",
    entry_id: "synthetic",
    language: "en",
  });
  document.body.append(card);
  t.after(() => card.remove());

  const execute = (message) => {
    calls.push(clone(message));
    if (receipts.has(message.operation_id))
      return clone(receipts.get(message.operation_id));
    let receipt;
    if (message.action === "school.timetable_save") {
      const payload = message.payload;
      const member = state.members.find((item) => item.id === payload.member);
      assert.equal(payload.member_revision, member.revision);
      if (payload.id) {
        const record = locateRecord(state, payload.id);
        assert.equal(record.revision, payload.revision);
        Object.assign(record, clone(payload), {
          revision: record.revision + 1,
          status: "active",
        });
        delete record.member_revision;
        receipt = {
          id: record.id,
          revision: record.revision,
          status: record.status,
        };
      } else {
        assert.equal(
          state.school.timetables.some(
            (record) =>
              record.member === payload.member && record.status === "active",
          ),
          false,
        );
        const record = {
          id: "ST000003",
          ...clone(payload),
          revision: 1,
          status: "active",
          history: [],
          backpack_routine_current: payload.backpack_routine
            ? { ...payload.backpack_routine, title: "Pack school bag" }
            : null,
        };
        delete record.member_revision;
        state.school.timetables.push(record);
        receipt = { id: record.id, revision: 1, status: "active" };
      }
    } else if (message.action === "school.timetable_archive") {
      const record = locateRecord(state, message.payload.id);
      assert.equal(record.revision, message.payload.revision);
      record.status = "archived";
      record.revision += 1;
      receipt = {
        id: record.id,
        revision: record.revision,
        status: record.status,
      };
    } else if (message.action === "pantry.stock_set") {
      receipt = { accepted: true };
    } else throw { code: "unknown_action" };
    receipts.set(message.operation_id, clone(receipt));
    state.revision += 1;
    if (lostAction === message.action) {
      lostAction = null;
      throw { code: "storage_error" };
    }
    return clone(receipt);
  };

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
    card,
    state,
    calls,
    lose(action) {
      lostAction = action;
    },
  };
}

function button(root, label) {
  const result = [...root.querySelectorAll("button")].find(
    (candidate) => candidate.textContent === label,
  );
  assert.ok(result, `missing button: ${label}`);
  return result;
}

function form(card, kind) {
  const result = card.shadowRoot.querySelector(`[data-school-form="${kind}"]`);
  assert.ok(result, `missing school form: ${kind}`);
  return result;
}

function setField(root, name, value) {
  const control = root.querySelector(`[name="${name}"]`);
  assert.ok(control, `missing field: ${name}`);
  control.value = value;
  control.dispatchEvent(new Event("input", { bubbles: true }));
  control.dispatchEvent(new Event("change", { bubbles: true }));
  return control;
}

function submit(target) {
  target.dispatchEvent(
    new Event("submit", { bubbles: true, cancelable: true }),
  );
}

function fillLesson(row, values) {
  for (const [name, value] of Object.entries(values))
    setField(row, name, value);
}

test("real card is inert, localized, parent-full, child-own, and hidden from adults", async (t) => {
  for (const locale of Object.values(SCHOOL_COPY))
    assert.deepEqual(
      Object.keys(locale).sort(),
      Object.keys(SCHOOL_COPY.en).sort(),
    );
  const parent = await setup(t);
  const before = clone(parent.state);
  parent.card.render();
  assert.deepEqual(parent.state, before);
  assert.equal(parent.calls.length, 0);
  assert.match(parent.card.shadowRoot.textContent, /Europe\/Kyiv/);
  assert.match(parent.card.shadowRoot.textContent, /Former Child/);
  assert.match(parent.card.shadowRoot.textContent, /Other child's lesson/);
  assert.match(parent.card.shadowRoot.textContent, /Created/);
  assert.equal(parent.card.shadowRoot.querySelector("b"), null);
  assert.match(parent.card.shadowRoot.textContent, /<b>Mathematics<\/b>/);

  const child = await setup(t, { role: "child" });
  assert.match(child.card.shadowRoot.textContent, /<b>Mathematics<\/b>/);
  assert.equal(
    child.card.shadowRoot.textContent.includes("Other child's lesson"),
    false,
  );
  assert.equal(
    child.card.shadowRoot.textContent.includes("Private other material"),
    false,
  );
  assert.equal(
    child.card.shadowRoot.textContent.includes("Former Child"),
    false,
  );
  // School-work controls are child-authorized; timetable mutations are not.
  assert.equal(child.card.shadowRoot.querySelector(".school-section button"), null);

  const adult = await setup(t, { role: "adult" });
  assert.equal(adult.card.shadowRoot.querySelector(".school-section"), null);
  assert.equal(adult.calls.length, 0);
});

test("new timetable validates overlaps then freezes the complete replacement review", async (t) => {
  const fixture = await setup(t);
  button(fixture.card.shadowRoot, SCHOOL_COPY.en.new_timetable).click();
  let editor = form(fixture.card, "edit");
  assert.equal(editor.elements.member.value, "child-2");
  setField(editor, "title", "Autumn timetable");
  setField(editor, "valid_from", "2026-09-07");
  setField(editor, "valid_until", "2026-12-18");
  setField(editor, "exceptions", "2026-10-12\n2026-10-13");
  setField(editor, "backpack_routine", JSON.stringify(["RT000001", 5]));
  fillLesson(editor.querySelector('[data-school-lesson="0"]'), {
    weekday: "0",
    start: "08:00",
    end: "09:00",
    subject: "Mathematics",
    room: "12",
    materials: "Workbook\nPencil",
  });
  button(editor, SCHOOL_COPY.en.add_lesson).click();
  editor = form(fixture.card, "edit");
  fillLesson(editor.querySelector('[data-school-lesson="1"]'), {
    weekday: "0",
    start: "08:30",
    end: "10:00",
    subject: "Physics",
    room: "Lab",
    materials: "Notebook",
  });
  submit(editor);
  assert.equal(fixture.calls.length, 0);
  assert.equal(fixture.card._actionError, "invalid_field");
  editor = form(fixture.card, "edit");
  setField(editor.querySelector('[data-school-lesson="1"]'), "start", "09:00");
  submit(editor);
  assert.equal(fixture.card._schoolDraft.kind, "review");
  const review = form(fixture.card, "review");
  assert.match(review.textContent, /Child Two/);
  assert.match(review.textContent, /09:00–10:00/);
  assert.match(review.textContent, /Pack school bag/);
  assert.equal(fixture.calls.length, 0);
  assert.ok(Object.isFrozen(fixture.card._schoolDraft.payload));
  assert.deepEqual(fixture.card._schoolDraft.payload, {
    member: "child-2",
    member_revision: 1,
    title: "Autumn timetable",
    valid_from: "2026-09-07",
    valid_until: "2026-12-18",
    lessons: [
      {
        weekday: 0,
        start: "08:00",
        end: "09:00",
        subject: "Mathematics",
        room: "12",
        materials: ["Workbook", "Pencil"],
      },
      {
        weekday: 0,
        start: "09:00",
        end: "10:00",
        subject: "Physics",
        room: "Lab",
        materials: ["Notebook"],
      },
    ],
    backpack_routine: { id: "RT000001", revision: 5 },
    exceptions: ["2026-10-12", "2026-10-13"],
  });
});

test("new save retry keeps exact operation and payload across an unrelated command", async (t) => {
  const fixture = await setup(t);
  button(fixture.card.shadowRoot, SCHOOL_COPY.en.new_timetable).click();
  const editor = form(fixture.card, "edit");
  setField(editor, "title", "Simple timetable");
  setField(editor, "valid_from", "2026-09-07");
  fillLesson(editor.querySelector('[data-school-lesson="0"]'), {
    weekday: "1",
    start: "10:00",
    end: "11:00",
    subject: "Art",
    room: "",
    materials: "Paint",
  });
  submit(editor);
  let review = form(fixture.card, "review");
  submit(review);
  await tick();
  assert.equal(fixture.calls.length, 0);
  review.elements.reviewed.checked = true;
  review.elements.reviewed.dispatchEvent(
    new Event("change", { bubbles: true }),
  );
  fixture.lose("school.timetable_save");
  submit(review);
  await eventually(
    () =>
      fixture.calls.length === 1 &&
      fixture.card._actionError === "storage_error" &&
      Boolean(fixture.card._schoolDraft?.pending) &&
      !fixture.card._writing,
  );
  const first = fixture.calls[0];
  const operationId = first.operation_id;
  await fixture.card.command(
    "pantry.stock_set",
    { id: "PI000001", revision: 1, quantity: 1, reason: "Unrelated" },
    "unrelated-operation",
  );
  assert.equal(fixture.card._schoolDraft.pending.operation_id, operationId);
  submit(form(fixture.card, "review"));
  await eventually(
    () => fixture.calls.length === 3 && fixture.card._schoolDraft === null,
  );
  assert.deepEqual(fixture.calls[2].payload, first.payload);
  assert.equal(fixture.calls[2].operation_id, operationId);
  assert.equal(
    fixture.state.school.timetables.filter(
      (record) => record.member === "child-2" && record.status === "active",
    ).length,
    1,
  );
});

test("edit is full replacement with immutable child and exact record/member revisions", async (t) => {
  const fixture = await setup(t);
  const row = fixture.card.shadowRoot.querySelector(
    '[data-school-timetable="ST000001"]',
  );
  button(row, SCHOOL_COPY.en.edit).click();
  let editor = form(fixture.card, "edit");
  assert.equal(editor.elements.member.disabled, true);
  assert.equal(editor.elements.member.value, "child-1");
  setField(editor, "title", "Updated school week");
  submit(editor);
  assert.equal(fixture.card._schoolDraft.kind, "review");
  assert.deepEqual(
    {
      id: fixture.card._schoolDraft.payload.id,
      revision: fixture.card._schoolDraft.payload.revision,
      member: fixture.card._schoolDraft.payload.member,
      member_revision: fixture.card._schoolDraft.payload.member_revision,
    },
    { id: "ST000001", revision: 3, member: "child-1", member_revision: 2 },
  );

  fixture.card._schoolDraft.kind = "edit";
  fixture.card._schoolDraft.payload = null;
  editor = document.createElement("form");
  fixture.card._data.school.timetables[0].revision = 4;
  fixture.card.render();
  assert.equal(fixture.card._schoolDraft, null);
  assert.equal(fixture.calls.length, 0);
});

test("an unavailable raw backpack pin cannot be silently cleared by an unrelated edit", async (t) => {
  const fixture = await setup(t);
  locateRecord(fixture.state, "ST000001").backpack_routine_current = null;
  await fixture.card.refresh();
  const row = fixture.card.shadowRoot.querySelector(
    '[data-school-timetable="ST000001"]',
  );
  button(row, SCHOOL_COPY.en.edit).click();
  let editor = form(fixture.card, "edit");
  const routine = editor.elements.backpack_routine;
  assert.equal(routine.value, "__unavailable__");
  assert.match(editor.textContent, /Unavailable pinned routine/);
  assert.match(editor.textContent, /RT000001/);
  assert.match(editor.textContent, /version 5/);
  setField(editor, "title", "Rename must not drop link");
  submit(editor);
  assert.equal(fixture.card._schoolDraft.kind, "edit");
  assert.equal(fixture.card._actionError, "invalid_field");
  assert.equal(fixture.calls.length, 0);

  editor = form(fixture.card, "edit");
  setField(editor, "backpack_routine", "");
  submit(editor);
  assert.equal(fixture.card._schoolDraft.kind, "review");
  assert.equal(fixture.card._schoolDraft.payload.backpack_routine, null);
});

test("linked save retry retains the exact operation after target-side revisions advance", async (t) => {
  const fixture = await setup(t);
  const row = fixture.card.shadowRoot.querySelector(
    '[data-school-timetable="ST000001"]',
  );
  button(row, SCHOOL_COPY.en.edit).click();
  const editor = form(fixture.card, "edit");
  setField(editor, "title", "Committed linked timetable");
  submit(editor);
  let review = form(fixture.card, "review");
  review.elements.reviewed.checked = true;
  review.elements.reviewed.dispatchEvent(
    new Event("change", { bubbles: true }),
  );
  fixture.lose("school.timetable_save");
  submit(review);
  await eventually(
    () =>
      fixture.calls.length === 1 &&
      fixture.card._actionError === "storage_error" &&
      Boolean(fixture.card._schoolDraft?.pending) &&
      !fixture.card._writing,
  );
  const first = clone(fixture.calls[0]);
  assert.deepEqual(first.payload.backpack_routine, {
    id: "RT000001",
    revision: 5,
  });

  fixture.state.members.find((member) => member.id === "child-1").revision = 3;
  fixture.state.routines.templates[0].revision = 6;
  const committed = locateRecord(fixture.state, "ST000001");
  committed.revision += 1;
  committed.backpack_routine_current = null;
  await fixture.card.refresh();
  assert.equal(
    fixture.card._schoolDraft.pending.operation_id,
    first.operation_id,
  );
  review = form(fixture.card, "review");
  assert.match(review.textContent, /Pack school bag/);
  submit(review);
  await eventually(
    () => fixture.calls.length === 2 && fixture.card._schoolDraft === null,
  );
  assert.deepEqual(fixture.calls[1], first);
});

test("former-child archive uses a named frozen review and retries its committed receipt", async (t) => {
  const fixture = await setup(t);
  const row = fixture.card.shadowRoot.querySelector(
    '[data-school-timetable="ST000002"]',
  );
  assert.equal(
    [...row.querySelectorAll("button")].some(
      (item) => item.textContent === SCHOOL_COPY.en.edit,
    ),
    false,
  );
  button(row, SCHOOL_COPY.en.archive).click();
  const reasonForm = form(fixture.card, "archive_edit");
  setField(reasonForm, "reason", "No longer attends school");
  submit(reasonForm);
  let review = form(fixture.card, "archive_review");
  assert.match(review.textContent, /Former Child/);
  assert.match(review.textContent, /Old school timetable/);
  assert.match(review.textContent, /No longer attends school/);
  assert.equal(fixture.calls.length, 0);
  review.elements.reviewed.checked = true;
  review.elements.reviewed.dispatchEvent(
    new Event("change", { bubbles: true }),
  );
  fixture.lose("school.timetable_archive");
  submit(review);
  await eventually(
    () =>
      fixture.calls.length === 1 &&
      fixture.card._actionError === "storage_error" &&
      Boolean(fixture.card._schoolDraft?.pending),
  );
  const first = fixture.calls[0];
  assert.deepEqual(first.payload, {
    id: "ST000002",
    revision: 7,
    reason: "No longer attends school",
  });
  fixture.state.members.find((member) => member.id === "former-1").revision = 4;
  await fixture.card.refresh();
  assert.equal(
    fixture.card._schoolDraft.pending.operation_id,
    first.operation_id,
  );
  review = form(fixture.card, "archive_review");
  assert.match(review.textContent, /No longer attends school/);
  submit(review);
  await eventually(
    () => fixture.calls.length === 2 && fixture.card._schoolDraft === null,
  );
  assert.deepEqual(fixture.calls[1], first);
  assert.equal(locateRecord(fixture.state, "ST000002").status, "archived");
});

test("stale actor, child, record, routine, modules, entry, generation, and detached forms are inert", async (t) => {
  const changes = [
    ["actor", (fixture) => (fixture.card._data.actor = "owner-1")],
    [
      "child",
      (fixture) =>
        (fixture.card._data.members.find(
          (member) => member.id === "child-1",
        ).revision = 3),
    ],
    [
      "record",
      (fixture) => (fixture.card._data.school.timetables[0].revision = 4),
    ],
    [
      "routine",
      (fixture) => (fixture.card._data.routines.templates[0].revision = 6),
    ],
    [
      "routine module",
      (fixture) => (fixture.card._data.settings.modules = ["school", "pantry"]),
    ],
    [
      "module",
      (fixture) => (fixture.card._data.settings.modules = ["routines"]),
    ],
    ["entry", (fixture) => (fixture.card._entry = "other")],
    ["generation", (fixture) => (fixture.card._generation += 1)],
  ];
  for (const [name, change] of changes) {
    const fixture = await setup(t);
    const row = fixture.card.shadowRoot.querySelector(
      '[data-school-timetable="ST000001"]',
    );
    button(row, SCHOOL_COPY.en.edit).click();
    const editor = form(fixture.card, "edit");
    change(fixture);
    setField(editor, "title", "Must not survive");
    assert.equal(fixture.card._schoolDraft, null, `${name} retained draft`);
    assert.equal(editor.isConnected, false, `${name} retained form`);
    assert.equal(
      fixture.card.shadowRoot.textContent.includes("Must not survive"),
      false,
      `${name} retained stale child editor content`,
    );
    assert.ok(
      fixture.card.shadowRoot.querySelector('[role="alert"]'),
      `${name} did not restore the parent view with a conflict notice`,
    );
    assert.equal(fixture.calls.length, 0, `${name} reached transport`);
  }

  const detached = await setup(t);
  const row = detached.card.shadowRoot.querySelector(
    '[data-school-timetable="ST000001"]',
  );
  button(row, SCHOOL_COPY.en.edit).click();
  const oldForm = form(detached.card, "edit");
  detached.card.render();
  submit(oldForm);
  await tick();
  assert.equal(detached.calls.length, 0);
  assert.ok(detached.card._schoolDraft);
  detached.card.setConfig({
    type: "custom:family-school-card",
    entry_id: "next",
    language: "en",
  });
  assert.equal(detached.card._schoolDraft, null);
});

test("focused unchanged form survives refresh while child-role revocation removes private agenda", async (t) => {
  const fixture = await setup(t);
  const row = fixture.card.shadowRoot.querySelector(
    '[data-school-timetable="ST000001"]',
  );
  button(row, SCHOOL_COPY.en.edit).click();
  const editor = form(fixture.card, "edit");
  const title = editor.elements.title;
  title.focus();
  await fixture.card.refresh();
  assert.equal(fixture.card.shadowRoot.activeElement, title);
  assert.equal(title.isConnected, true);

  const child = await setup(t, { role: "child" });
  const privateLesson = child.card.shadowRoot.querySelector(
    "[data-school-upcoming]",
  );
  const unrelated = document.createElement("form");
  const input = document.createElement("input");
  unrelated.append(input);
  child.card.shadowRoot.querySelector(".body").prepend(unrelated);
  input.focus();
  child.state.members.find((member) => member.id === "child-1").role = "adult";
  child.state.members.find((member) => member.id === "child-1").revision = 3;
  child.state.role = "adult";
  await child.card.refresh();
  assert.equal(privateLesson.isConnected, false);
  assert.equal(input.isConnected, false);
  assert.equal(child.card.shadowRoot.querySelector(".school-section"), null);
});
