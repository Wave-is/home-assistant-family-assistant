import assert from "node:assert/strict";
import { test } from "node:test";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><body></body>", {
  url: "https://example.invalid",
});
for (const key of [
  "window",
  "document",
  "Element",
  "HTMLElement",
  "customElements",
  "CustomEvent",
  "Event",
  "FormData",
])
  globalThis[key] = dom.window[key];

await import("../custom_components/family_assistant/frontend/family-assistant.js");
const { buildTodayModel, TODAY_COPY } =
  await import("../custom_components/family_assistant/frontend/today-view.js");

const clone = (value) => structuredClone(value);
const tick = () => new Promise((resolve) => setTimeout(resolve, 0));
async function eventually(predicate, message = "condition was not reached") {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    if (predicate()) return;
    await tick();
  }
  assert.fail(message);
}

const MEMBERS = [
  {
    id: "owner-1",
    name: "Owner One",
    role: "owner",
    active: true,
    revision: 2,
  },
  {
    id: "parent-1",
    name: "Parent One",
    role: "parent",
    active: true,
    revision: 4,
  },
  {
    id: "adult-1",
    name: "Adult One",
    role: "adult",
    active: true,
    revision: 3,
  },
  {
    id: "child-1",
    name: "Child One",
    role: "child",
    active: true,
    revision: 7,
  },
  {
    id: "guest-1",
    name: "Guest One",
    role: "guest",
    active: true,
    revision: 5,
  },
];

function iso(now, offsetHours) {
  return new Date(now + offsetHours * 60 * 60 * 1000).toISOString();
}

function utcDayTime(now, offsetHours) {
  const value = new Date(now + offsetHours * 60 * 60 * 1000);
  return {
    date: value.toISOString().slice(0, 10),
    time: value.toISOString().slice(11, 16),
  };
}

function stateFor(role = "parent", now = Date.now()) {
  const actor = {
    owner: "owner-1",
    parent: "parent-1",
    adult: "adult-1",
    child: "child-1",
    guest: "guest-1",
  }[role];
  const school = utcDayTime(now, 3);
  const alarm = utcDayTime(now, 4);
  const alarmWeekday =
    (new Date(`${alarm.date}T12:00:00Z`).getUTCDay() + 6) % 7;
  const tasks = [
    ...Array.from({ length: 6 }, (_, index) => ({
      id: `T-overdue-${index}`,
      title: `Overdue task ${index}`,
      assignee: "child-1",
      status: index === 5 ? "needs_changes" : "assigned",
      due_at: iso(now, -index - 1),
      report: "PRIVATE-REPORT-CANARY",
      report_attachments: [{ id: "PRIVATE-MEDIA-CANARY" }],
    })),
    ...Array.from({ length: 6 }, (_, index) => ({
      id: `T-due-${index}`,
      title: `Due task ${index}`,
      assignee: "adult-1",
      status: "in_progress",
      due_at: iso(now, index + 1),
    })),
    ...Array.from({ length: 6 }, (_, index) => ({
      id: `T-review-${index}`,
      title: `Review task ${index}`,
      assignee: "child-1",
      status: "submitted",
      due_at: iso(now, 2),
    })),
    {
      id: "T-complete",
      title: "HIDDEN-COMPLETED-CANARY",
      assignee: "child-1",
      status: "completed",
      due_at: iso(now, -10),
    },
  ];
  return {
    revision: 11,
    actor,
    role,
    settings: {
      name: "Synthetic family",
      timezone: "UTC",
      modules: [
        "tasks",
        "shopping",
        "calendar",
        "school",
        "alarms",
        "routines",
        "presence",
        "court",
      ],
    },
    members: clone(MEMBERS),
    tasks,
    shopping: [
      { id: "S1", name: "PRIVATE-SHOPPING-NAME", status: "approved" },
      { id: "S2", name: "PRIVATE-SHOPPING-NAME-2", status: "approved" },
      { id: "S3", name: "PRIVATE-SHOPPING-NAME-3", status: "pending" },
    ],
    calendar: {
      config: {},
      events: [
        {
          id: "C1",
          title: "PRIVATE-REQUEST-TITLE",
          status: "tentative",
          archived: false,
        },
        {
          id: "C2",
          title: "Archived request",
          status: "tentative",
          archived: true,
        },
      ],
      occurrences: [
        {
          id: "CO1",
          title: "Dentist visit",
          start: iso(now, 2),
          all_day: false,
          location: "PRIVATE-LOCATION-CANARY",
        },
      ],
    },
    school: {
      upcoming: [
        {
          id: "ST1",
          timetable_id: "ST-private",
          member: "child-1",
          date: school.date,
          start: school.time,
          end: "23:59",
          subject: "Mathematics",
          room: "PRIVATE-ROOM-CANARY",
          materials: ["PRIVATE-MATERIAL-CANARY"],
          backpack_routine: {
            id: "PRIVATE-ROUTINE-ID",
            revision: 8,
            title: "Private",
          },
        },
      ],
    },
    alarms: [
      {
        id: "A1",
        member: "child-1",
        name: "School alarm",
        enabled: true,
        time: alarm.time,
        days: [alarmWeekday],
        timezone: "UTC",
        exceptions: [],
        challenge: "PRIVATE-CHALLENGE-CANARY",
      },
    ],
    alarm_runs: [
      {
        id: "AR1",
        member: "child-1",
        stage: "first",
        challenge: { answer: "PRIVATE-ANSWER-CANARY" },
      },
    ],
    routines: {
      runs: [
        {
          id: "RR1",
          member: "child-1",
          title: "Morning routine",
          status: "active",
          steps: [{ title: "PRIVATE-STEP-CANARY" }],
          nonce: "PRIVATE-NONCE-CANARY",
        },
      ],
    },
    presence: {
      self: {
        member: actor,
        member_revision: MEMBERS.find((item) => item.id === actor).revision,
        binding_revision: 1,
        subscription_revision: 1,
        enabled: true,
        can_edit: true,
        status: "reported_home",
        reason: "fresh",
        observed_at: iso(now, -0.25),
        entity_id: "PRIVATE-ENTITY-CANARY",
        latitude: "PRIVATE-COORDINATE-CANARY",
      },
      shared: [
        {
          member: "adult-1",
          member_revision: 3,
          status: "reported_away",
          reason: "fresh",
          observed_at: iso(now, -0.5),
          zone: "PRIVATE-ZONE-CANARY",
        },
      ],
    },
    health: { telegram: "attention", backup: "attention" },
    delivery_issues: [
      { id: "D1", key: "PRIVATE-DELIVERY-KEY", recipient: "PRIVATE-RECIPIENT" },
    ],
    court: [
      {
        id: "C1",
        member: "child-1",
        points: 4,
        reason: "PRIVATE-COURT-REASON",
        status: "active",
      },
      {
        id: "C2",
        member: "child-1",
        points: -1,
        reason: "PRIVATE-COURT-REASON-2",
        status: "active",
      },
      {
        id: "C3",
        member: "adult-1",
        points: 8,
        reason: "PRIVATE-ARCHIVED-REASON",
        status: "archived",
      },
    ],
  };
}

async function setup(t, options = {}) {
  const now = Date.now();
  const state = stateFor(options.role, now);
  const calls = [];
  const card = document.createElement("family-assistant-card");
  card.setConfig({
    type: "custom:family-assistant-card",
    entry_id: "synthetic-today",
    view: "today",
    language: options.language || "en",
  });
  document.body.append(card);
  t.after(() => card.remove());
  card.hass = {
    language: options.language || "en",
    callWS: async (message) => {
      calls.push(clone(message));
      if (message.type === "family_assistant/view") return clone(state);
      throw new Error(`Unexpected WS ${message.type}`);
    },
  };
  await eventually(() => card._data?.actor === state.actor);
  return { card, state, calls, now };
}

test("Today English, Russian, and Ukrainian copy has exact key parity", () => {
  const english = Object.keys(TODAY_COPY.en).sort();
  assert.deepEqual(Object.keys(TODAY_COPY.ru).sort(), english);
  assert.deepEqual(Object.keys(TODAY_COPY.uk).sort(), english);
  for (const locale of Object.values(TODAY_COPY))
    for (const value of Object.values(locale)) assert.ok(value.trim());
});

test("pure model enforces bounds, module gates, and DST alarm candidates", () => {
  const now = Date.parse("2026-10-25T01:00:00Z");
  const data = stateFor("parent", now);
  data.alarms = [
    {
      member: "child-1",
      name: "Fold alarm",
      enabled: true,
      time: "03:30",
      days: [6],
      timezone: "Europe/Kyiv",
      exceptions: [],
    },
    {
      member: "child-1",
      name: "Gap alarm",
      enabled: true,
      time: "03:30",
      days: [6],
      timezone: "Europe/Kyiv",
      exceptions: ["2026-11-01"],
    },
  ];
  for (let index = 0; index < 10; index += 1)
    data.members.push({
      id: `extra-${index}`,
      name: `Extra ${index}`,
      role: "adult",
      active: true,
      revision: 1,
    });
  const model = buildTodayModel(data, now);
  assert.equal(model.overdue.length, 4);
  assert.equal(model.overdueCount, 6);
  assert.equal(model.dueSoon.length, 4);
  assert.equal(model.submitted.length, 4);
  assert.equal(model.submittedCount, 6);
  assert.equal(model.presence.length, 2);
  assert.deepEqual(Object.keys(model.overdue[0]).sort(), [
    "assignee",
    "due",
    "due_at",
    "status",
    "title",
  ]);
  assert.deepEqual(Object.keys(model.submitted[0]).sort(), [
    "assignee",
    "title",
  ]);
  assert.deepEqual(Object.keys(model.presence[0]).sort(), [
    "member",
    "observed_at",
    "reason",
    "status",
  ]);
  assert.deepEqual(
    model.balances.find((item) => item.member === "child-1"),
    { member: "child-1", points: 3 },
  );
  assert.equal(model.balances.length, 8);
  assert.ok(model.agenda.length <= 8);
  const fold = model.agenda.find((item) => item.title === "Fold alarm");
  assert.equal(fold.at, Date.parse("2026-11-01T01:30:00Z"));

  data.settings.modules = ["tasks"];
  const gated = buildTodayModel(data, now);
  assert.equal(gated.shopping, null);
  assert.deepEqual(gated.agenda, []);
  assert.deepEqual(gated.presence, []);
  assert.deepEqual(gated.activeRuns, []);
  assert.deepEqual(gated.balances, []);
});

test("nonexistent alarm wall time is omitted for that day without silent shifting", () => {
  const now = Date.parse("2026-03-29T00:00:00Z");
  const data = stateFor("child", now);
  data.alarms = [
    {
      member: "child-1",
      name: "Spring alarm",
      enabled: true,
      time: "03:30",
      days: [6],
      timezone: "Europe/Kyiv",
      exceptions: [],
    },
  ];
  const alarm = buildTodayModel(data, now).agenda.find(
    (item) => item.title === "Spring alarm",
  );
  assert.equal(alarm.at, Date.parse("2026-04-05T00:30:00Z"));
});

test("agenda filters before caps and keeps the current local all-day event", () => {
  const now = Date.parse("2026-09-07T12:00:00Z");
  const data = stateFor("parent", now);
  data.calendar.occurrences = [
    ...Array.from({ length: 5 }, (_, index) => ({
      title: `Past ${index}`,
      start: iso(now, -index - 1),
      all_day: false,
    })),
    { title: "Today all day", start: "2026-09-07", all_day: true },
    { title: "Future valid", start: iso(now, 2), all_day: false },
  ];
  data.school.upcoming = [
    ...Array.from({ length: 5 }, () => ({
      member: "child-1",
      date: "2026-02-30",
      start: "08:00",
      subject: "Invalid school row",
    })),
    {
      member: "child-1",
      date: "2026-09-07",
      start: "15:00",
      subject: "Future lesson",
    },
  ];
  const agenda = buildTodayModel(data, now).agenda;
  assert.ok(agenda.some((item) => item.title === "Today all day"));
  assert.ok(agenda.some((item) => item.title === "Future valid"));
  assert.ok(agenda.some((item) => item.title === "Future lesson"));
  assert.equal(
    agenda.some((item) => item.title.startsWith("Past")),
    false,
  );
  assert.equal(
    agenda.some((item) => item.title === "Invalid school row"),
    false,
  );
});

test("invalid timezone and malformed dates fail closed without raw fallback", () => {
  const now = Date.parse("2026-09-07T08:00:00Z");
  const data = stateFor("parent", now);
  data.settings.timezone = "PRIVATE-INVALID-ZONE";
  assert.deepEqual(buildTodayModel(data, now), { unavailable: true });
  data.settings.timezone = "UTC";
  data.tasks[0].due_at = "2026-02-30T10:00:00Z";
  data.calendar.occurrences[0].start = "2026-02-30T10:00:00Z";
  data.school.upcoming[0].date = "2026-02-30";
  const model = buildTodayModel(data, now);
  assert.equal(model.overdueCount, 5);
  assert.equal(
    model.agenda.some((item) => item.kind === "calendar"),
    false,
  );
  assert.equal(
    model.agenda.some((item) => item.kind === "school"),
    false,
  );
});

test("healthy runtime statuses do not inflate the attention count", () => {
  const data = stateFor("parent", Date.parse("2026-09-07T08:00:00Z"));
  data.health = {
    telegram: "connected",
    recipes: "connected",
    mikrotik: "network_connected",
  };
  assert.equal(buildTodayModel(data).health.signals, 0);
  data.health.conversation = "fallback";
  data.health.future_component = "future_attention_code";
  assert.equal(buildTodayModel(data).health.signals, 2);
});

test("real FamilyCard renders the bounded parent overview without mutation or private fields", async (t) => {
  const fixture = await setup(t, { role: "parent", language: "ru" });
  const before = clone(fixture.state);
  fixture.calls.length = 0;
  fixture.card.render();
  assert.deepEqual(fixture.state, before);
  assert.equal(fixture.calls.length, 0);
  const root = fixture.card.shadowRoot;
  assert.ok(root.querySelector(".today-overview"));
  assert.equal(
    root.querySelectorAll(".today-overdue .today-task-row").length,
    4,
  );
  assert.equal(
    root.querySelectorAll(".today-due-soon .today-task-row").length,
    4,
  );
  assert.equal(root.querySelectorAll(".today-approval-row").length, 4);
  assert.ok(root.querySelectorAll(".today-agenda-row").length <= 8);
  assert.equal(
    root.querySelectorAll("button, input, select, textarea, form").length,
    0,
  );
  assert.equal(root.querySelectorAll(".today-balance-row").length, 5);
  const content = root.textContent;
  assert.match(content, /Parent One|Child One/);
  assert.match(content, /Mathematics|Dentist visit|School alarm/);
  assert.match(content, /Сигналы состояния/);
  assert.doesNotMatch(
    content,
    /PRIVATE-|HIDDEN-COMPLETED|entity_id|latitude|challenge|nonce|materials|report_attachments/,
  );
});

test("adult and child omit parent-only approvals, shared presence, and health", async (t) => {
  for (const role of ["adult", "child"]) {
    const fixture = await setup(t, {
      role,
      language: role === "child" ? "uk" : "en",
    });
    const root = fixture.card.shadowRoot;
    assert.ok(root.querySelector(".today-overview"));
    assert.equal(root.querySelector(".today-approvals"), null);
    assert.equal(root.querySelector(".today-health"), null);
    assert.equal(root.querySelectorAll(".today-presence-row").length, 1);
    assert.equal(root.querySelectorAll(".today-balance-row").length, 1);
    assert.doesNotMatch(root.textContent, /PRIVATE-/);
  }
});

test("disabled modules and guest refresh remove old overview content", async (t) => {
  const fixture = await setup(t, { role: "parent" });
  assert.match(fixture.card.shadowRoot.textContent, /Mathematics/);
  fixture.state.settings.modules = ["tasks"];
  await fixture.card.refresh();
  const gated = fixture.card.shadowRoot;
  assert.equal(gated.querySelector(".today-shopping"), null);
  assert.equal(gated.querySelector(".today-agenda"), null);
  assert.equal(gated.querySelector(".today-presence"), null);
  assert.equal(gated.querySelector(".today-runs"), null);
  assert.equal(gated.querySelector(".today-balances"), null);
  assert.doesNotMatch(
    gated.textContent,
    /Mathematics|Dentist visit|Morning routine/,
  );

  fixture.state.role = "guest";
  fixture.state.actor = "guest-1";
  await fixture.card.refresh();
  assert.equal(fixture.card.shadowRoot.querySelector(".today-overview"), null);
  assert.ok(
    fixture.card.shadowRoot.querySelector(".availability-role_unavailable"),
  );
  assert.doesNotMatch(
    fixture.card.shadowRoot.textContent,
    /Overdue task|Mathematics/,
  );
});

test("invalid timezone renders a generic no-data state, not projected values", async (t) => {
  const fixture = await setup(t, { role: "parent", language: "uk" });
  fixture.state.settings.timezone = "Not/A-Timezone";
  await fixture.card.refresh();
  const root = fixture.card.shadowRoot;
  assert.ok(root.querySelector(".today-unavailable"));
  assert.match(root.textContent, /Налаштування часу родини недоступні/);
  assert.doesNotMatch(
    root.textContent,
    /Overdue task|Dentist visit|Mathematics|PRIVATE-/,
  );
  assert.equal(root.querySelectorAll("button").length, 0);
});
