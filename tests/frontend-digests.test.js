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
const { reconcileDigestsRefresh } =
  await import("../custom_components/family_assistant/frontend/digests-view.js");
const { DIGESTS_COPY } =
  await import("../custom_components/family_assistant/frontend/digests-copy.js");

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

function stateFor(role = "parent") {
  const actor = {
    owner: "owner-1",
    parent: "parent-1",
    adult: "adult-1",
    child: "child-1",
    guest: "guest-1",
  }[role];
  const current = MEMBERS.find((item) => item.id === actor);
  return {
    revision: 1,
    actor,
    role,
    settings: {
      name: "Synthetic family",
      timezone: "Europe/Kyiv",
      modules: ["digests"],
    },
    members: clone(MEMBERS),
    digests:
      role === "guest"
        ? { policy: null, self: null }
        : {
            policy: {
              timezone: "Europe/Kyiv",
              morning: { enabled: true, time: "07:00" },
              evening: { enabled: false, time: "19:00" },
              weekly: { enabled: true, weekday: 6, time: "18:00" },
            },
            self: {
              recipient_revision: current.revision,
              subscription_revision: role === "child" ? null : 2,
              morning: role !== "child",
              evening: false,
              weekly: role === "owner",
              can_edit: true,
              health: role === "adult" ? "attention" : "ok",
            },
          },
  };
}

function previewFor(kind = "morning") {
  return {
    schema: 1,
    kind,
    window_start: "2026-09-07",
    window_end: kind === "weekly" ? "2026-09-14" : "2026-09-08",
    sections: [
      {
        key: "tasks",
        rows: [
          {
            title: "Return library book",
            status: "assigned",
            due_at: "2026-09-07T12:00:00+00:00",
          },
        ],
        count: 1,
        overflow: 0,
      },
      {
        key: "school",
        rows: [
          {
            date: "2026-09-07",
            subject: "Mathematics",
            start: "08:30",
            materials: ["Notebook"],
          },
        ],
        count: 1,
        overflow: 0,
      },
      { key: "shopping", rows: [], count: 3, overflow: 0 },
    ],
  };
}

async function setup(t, options = {}) {
  const state = stateFor(options.role);
  const calls = [];
  const receipts = new Map();
  let failure = null;
  let preview = options.preview || null;
  let previewFailure = false;
  let deferred = null;

  const execute = (message) => {
    calls.push(clone(message));
    const row = state.digests.self;
    if (receipts.has(message.operation_id)) {
      const receipt = receipts.get(message.operation_id);
      assert.equal(row.subscription_revision, receipt.revision);
      assert.equal(
        [row.morning, row.evening, row.weekly].some(Boolean)
          ? "enabled"
          : "disabled",
        receipt.status,
      );
      return clone(receipt);
    }
    assert.equal(message.action, "digests.access_set");
    assert.deepEqual(Object.keys(message.payload).sort(), [
      "evening",
      "morning",
      "recipient_revision",
      "subscription_revision",
      "weekly",
    ]);
    assert.equal(message.payload.recipient_revision, row.recipient_revision);
    assert.equal(
      message.payload.subscription_revision,
      row.subscription_revision,
    );
    if (failure === "before") {
      failure = null;
      throw Object.assign(new Error("transport failed"), {
        code: "transport_error",
      });
    }
    const revision =
      row.subscription_revision === null ? 1 : row.subscription_revision + 1;
    Object.assign(row, {
      subscription_revision: revision,
      morning: message.payload.morning,
      evening: message.payload.evening,
      weekly: message.payload.weekly,
    });
    const receipt = {
      revision,
      status: [row.morning, row.evening, row.weekly].some(Boolean)
        ? "enabled"
        : "disabled",
    };
    receipts.set(message.operation_id, receipt);
    if (failure === "after") {
      failure = null;
      throw Object.assign(new Error("response lost"), {
        code: "response_lost",
      });
    }
    return clone(receipt);
  };

  const card = document.createElement("family-digests-card");
  card.setConfig({
    type: "custom:family-digests-card",
    entry_id: "synthetic-digests",
    language: options.language || "en",
  });
  document.body.append(card);
  t.after(() => card.remove());
  card.hass = {
    language: options.language || "en",
    callWS: async (message) => {
      if (message.type === "family_assistant/view") return clone(state);
      if (message.type === "family_assistant/execute") return execute(message);
      if (message.type === "family_assistant/digest_preview") {
        calls.push(clone(message));
        if (previewFailure)
          throw Object.assign(new Error("preview failed"), {
            code: "forbidden",
          });
        if (deferred)
          return new Promise((resolve) => {
            deferred.resolve = resolve;
          });
        return clone(
          preview
            ? { ...preview, kind: message.kind }
            : previewFor(message.kind),
        );
      }
      throw new Error(`Unexpected WS ${message.type}`);
    },
  };
  await eventually(
    () =>
      card._data?.actor === state.actor &&
      (options.role === "guest" || card.shadowRoot.querySelector(".digests")),
  );
  return {
    card,
    state,
    calls,
    failBefore() {
      failure = "before";
    },
    loseResponse() {
      failure = "after";
    },
    failPreview() {
      previewFailure = true;
    },
    setPreview(value) {
      preview = value;
    },
    deferPreview() {
      deferred = {};
      return deferred;
    },
  };
}

function button(card, label) {
  return [...card.shadowRoot.querySelectorAll("button")].find(
    (item) => item.textContent === label,
  );
}

function checkbox(card, name) {
  return card.shadowRoot.querySelector(`input[name="${name}"]`);
}

function confirmReview(card) {
  const control = checkbox(card, "confirmed");
  assert.ok(control);
  control.checked = true;
  control.dispatchEvent(new Event("change", { bubbles: true }));
}

test("English, Russian, and Ukrainian digest copy has exact key parity", () => {
  const english = Object.keys(DIGESTS_COPY.en).sort();
  assert.deepEqual(Object.keys(DIGESTS_COPY.ru).sort(), english);
  assert.deepEqual(Object.keys(DIGESTS_COPY.uk).sort(), english);
  for (const locale of Object.values(DIGESTS_COPY))
    for (const value of Object.values(locale)) assert.ok(value.trim());
});

test("real card renders only current self controls and readable owner policy", async (t) => {
  const fixture = await setup(t, { role: "parent", language: "ru" });
  const before = clone(fixture.state);
  fixture.card.render();
  assert.deepEqual(fixture.state, before);
  const text = fixture.card.shadowRoot.textContent;
  assert.match(text, /Parent One/);
  assert.match(text, /Europe\/Kyiv/);
  assert.doesNotMatch(text, /Owner One|Adult One|Child One/);
  assert.equal(fixture.calls.length, 0);

  const guest = await setup(t, { role: "guest" });
  assert.equal(guest.card.shadowRoot.querySelector(".digests"), null);
  fixture.state.settings.modules = [];
  fixture.state.digests = { policy: null, self: null };
  await fixture.card.refresh();
  assert.equal(fixture.card.shadowRoot.querySelector(".digests"), null);
  assert.equal(fixture.card._digestsDraft, null);
});

test("named keyboard review sends exact self-only preferences", async (t) => {
  const fixture = await setup(t, { role: "child", language: "uk" });
  button(fixture.card, DIGESTS_COPY.uk.change).click();
  checkbox(fixture.card, "morning").checked = true;
  const editor = fixture.card.shadowRoot.querySelector(".digest-editor");
  editor.dispatchEvent(
    new Event("submit", { bubbles: true, cancelable: true }),
  );
  assert.equal(fixture.calls.length, 0);
  const review = fixture.card.shadowRoot.querySelector(".digest-review");
  assert.match(review.textContent, /Child One/);
  assert.match(review.textContent, /ще не створена/);
  confirmReview(fixture.card);
  const form = fixture.card.shadowRoot.querySelector(".digest-review");
  form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  await eventually(
    () => fixture.calls.length === 1 && fixture.card._digestsDraft === null,
  );
  assert.deepEqual(fixture.calls[0].payload, {
    recipient_revision: 7,
    subscription_revision: null,
    morning: true,
    evening: false,
    weekly: false,
  });
  assert.equal(typeof fixture.calls[0].operation_id, "string");
});

test("new all-disabled preference is blocked before review", async (t) => {
  const fixture = await setup(t, { role: "child" });
  button(fixture.card, DIGESTS_COPY.en.change).click();
  button(fixture.card, DIGESTS_COPY.en.continue).click();
  assert.ok(fixture.card.shadowRoot.querySelector(".digest-editor"));
  assert.match(fixture.card.shadowRoot.textContent, /at least one/);
  assert.equal(fixture.calls.length, 0);
});

test("precommit and committed response loss preserve exact frozen requests", async (t) => {
  const before = await setup(t, { role: "adult" });
  before.failBefore();
  button(before.card, DIGESTS_COPY.en.change).click();
  checkbox(before.card, "evening").checked = true;
  button(before.card, DIGESTS_COPY.en.continue).click();
  confirmReview(before.card);
  button(before.card, DIGESTS_COPY.en.save).click();
  await eventually(
    () => before.card._digestsDraft?.pending && !before.card._writing,
  );
  const first = clone(before.card._digestsDraft.pending);
  button(before.card, DIGESTS_COPY.en.retry).click();
  await eventually(
    () => before.calls.length === 2 && before.card._digestsDraft === null,
  );
  assert.equal(before.calls[1].operation_id, first.operation_id);
  assert.deepEqual(before.calls[1].payload, first.payload);

  const after = await setup(t, { role: "owner" });
  after.loseResponse();
  button(after.card, DIGESTS_COPY.en.change).click();
  checkbox(after.card, "weekly").checked = false;
  button(after.card, DIGESTS_COPY.en.continue).click();
  confirmReview(after.card);
  button(after.card, DIGESTS_COPY.en.save).click();
  await eventually(
    () => after.card._digestsDraft?.pending && !after.card._writing,
  );
  const frozen = clone(after.card._digestsDraft.pending);
  assert.ok(Object.isFrozen(after.card._digestsDraft.pending));
  after.state.revision += 1;
  await after.card.refresh();
  assert.ok(after.card._digestsDraft?.pending);
  button(after.card, DIGESTS_COPY.en.retry).click();
  await eventually(
    () => after.calls.length === 2 && after.card._digestsDraft === null,
  );
  assert.equal(after.calls[1].operation_id, frozen.operation_id);
  assert.deepEqual(after.calls[1].payload, frozen.payload);
});

test("explicit preview is bounded, private, and never automatic", async (t) => {
  const fixture = await setup(t, { role: "child" });
  assert.equal(fixture.calls.length, 0);
  const select = fixture.card.shadowRoot.querySelector(
    'select[name="digest_kind"]',
  );
  select.value = "weekly";
  button(fixture.card, DIGESTS_COPY.en.preview).click();
  await eventually(() =>
    fixture.card.shadowRoot.querySelector(".digest-preview-section"),
  );
  assert.deepEqual(fixture.calls[0], {
    type: "family_assistant/digest_preview",
    entry_id: "synthetic-digests",
    kind: "weekly",
  });
  const text = fixture.card.shadowRoot.textContent;
  assert.match(text, /Return library book/);
  assert.match(text, /Mathematics/);
  assert.match(text, /Open shopping: 3/);
  assert.match(text, /2026-09-07 – 2026-09-13/);
  assert.doesNotMatch(text, /2026-09-07 – 2026-09-14/);
  assert.doesNotMatch(text, /entity_id|media_id|ballot|allergy|latitude/);
});

test("failed, malformed, stale, and detached previews leave no private snapshot", async (t) => {
  const failed = await setup(t, { role: "parent" });
  failed.failPreview();
  button(failed.card, DIGESTS_COPY.en.preview).click();
  await eventually(() => failed.card._digestsDraft === null);
  assert.equal(
    failed.card.shadowRoot.querySelector(".digest-preview-section"),
    null,
  );

  const malformed = await setup(t, { role: "parent" });
  const unsafe = previewFor();
  unsafe.sections[0].rows[0].id = "PRIVATE-ID-CANARY";
  malformed.setPreview(unsafe);
  button(malformed.card, DIGESTS_COPY.en.preview).click();
  await eventually(() => malformed.card._digestsDraft === null);
  assert.doesNotMatch(
    malformed.card.shadowRoot.textContent,
    /PRIVATE-ID-CANARY/,
  );

  const stale = await setup(t, { role: "parent" });
  const pending = stale.deferPreview();
  button(stale.card, DIGESTS_COPY.en.preview).click();
  stale.card._data.members.find(
    (item) => item.id === stale.state.actor,
  ).revision += 1;
  stale.card._data.digests.self.recipient_revision += 1;
  const previous = clone(stale.state);
  assert.equal(reconcileDigestsRefresh(stale.card, previous), true);
  stale.card.render();
  pending.resolve(previewFor());
  await tick();
  assert.equal(stale.card._digestsDraft, null);
  assert.equal(
    stale.card.shadowRoot.querySelector(".digest-preview-section"),
    null,
  );
  assert.doesNotMatch(stale.card.shadowRoot.textContent, /Building preview/);

  const detached = await setup(t, { role: "parent" });
  const request = button(detached.card, DIGESTS_COPY.en.preview);
  detached.card.remove();
  request.click();
  assert.equal(detached.calls.length, 0);
  assert.equal(detached.card._digestsDraft, null);
});

test("shown and in-flight previews are cleared by source revision or module drift", async (t) => {
  const shown = await setup(t, { role: "parent" });
  button(shown.card, DIGESTS_COPY.en.preview).click();
  await eventually(() => shown.card._digestsDraft?.snapshot);
  assert.match(shown.card.shadowRoot.textContent, /Return library book/);
  shown.state.revision += 1;
  shown.state.settings.modules.push("tasks");
  await shown.card.refresh();
  assert.equal(shown.card._digestsDraft, null);
  assert.doesNotMatch(shown.card.shadowRoot.textContent, /Return library book/);

  const pendingFixture = await setup(t, { role: "parent" });
  const pending = pendingFixture.deferPreview();
  button(pendingFixture.card, DIGESTS_COPY.en.preview).click();
  pendingFixture.state.revision += 1;
  await pendingFixture.card.refresh();
  pending.resolve(previewFor());
  await tick();
  assert.equal(pendingFixture.card._digestsDraft, null);
  assert.doesNotMatch(
    pendingFixture.card.shadowRoot.textContent,
    /Return library book/,
  );
});

test("preview requires canonical dates and exact daily or weekly windows", async (t) => {
  for (const preview of [
    { ...previewFor(), window_start: "2026-02-30", window_end: "2026-03-01" },
    { ...previewFor(), window_end: "2026-09-09" },
    { ...previewFor("weekly"), window_end: "2026-09-15" },
  ]) {
    const fixture = await setup(t, { role: "parent", preview });
    const select = fixture.card.shadowRoot.querySelector(
      'select[name="digest_kind"]',
    );
    select.value = preview.kind;
    button(fixture.card, DIGESTS_COPY.en.preview).click();
    await eventually(() => fixture.card._digestsDraft === null);
    assert.equal(
      fixture.card.shadowRoot.querySelector(".digest-preview-section"),
      null,
    );
  }
});

test("policy, authority, module, entry, and generation drift make old review controls inert", async (t) => {
  const mutations = [
    (fixture) => {
      fixture.card._data.digests.policy.morning.time = "07:15";
    },
    (fixture) => {
      fixture.card._data.members.find(
        (item) => item.id === fixture.state.actor,
      ).revision += 1;
      fixture.card._data.digests.self.recipient_revision += 1;
    },
    (fixture) => {
      fixture.card._data.digests.self.subscription_revision += 1;
    },
    (fixture) => {
      fixture.card._data.settings.modules = [];
    },
    (fixture) => {
      fixture.card._entry = "other-entry";
    },
    (fixture) => {
      fixture.card._generation += 1;
    },
  ];
  for (const mutate of mutations) {
    const fixture = await setup(t, { role: "parent" });
    button(fixture.card, DIGESTS_COPY.en.change).click();
    checkbox(fixture.card, "evening").checked = true;
    button(fixture.card, DIGESTS_COPY.en.continue).click();
    confirmReview(fixture.card);
    const save = button(fixture.card, DIGESTS_COPY.en.save);
    mutate(fixture);
    save.click();
    assert.equal(fixture.calls.length, 0);
    assert.equal(fixture.card._digestsDraft, null);
  }
});
