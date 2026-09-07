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
const { reconcilePresenceRefresh } =
  await import("../custom_components/family_assistant/frontend/presence-view.js");
const { PRESENCE_COPY } =
  await import("../custom_components/family_assistant/frontend/presence-copy.js");

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

function ownRow(actor) {
  if (actor === "owner-1")
    return {
      member: actor,
      member_revision: 2,
      binding_revision: 3,
      subscription_revision: 1,
      enabled: true,
      can_edit: true,
      status: "reported_home",
      reason: "fresh",
      observed_at: "2026-09-07T07:30:00+00:00",
    };
  if (actor === "parent-1")
    return {
      member: actor,
      member_revision: 4,
      binding_revision: 4,
      subscription_revision: null,
      enabled: false,
      can_edit: true,
      status: "unknown",
      reason: "not_shared",
      observed_at: null,
    };
  if (actor === "adult-1")
    return {
      member: actor,
      member_revision: 3,
      binding_revision: 5,
      subscription_revision: 2,
      enabled: true,
      can_edit: true,
      status: "reported_away",
      reason: "fresh",
      observed_at: "2026-09-07T07:29:00+00:00",
    };
  if (actor === "child-1")
    return {
      member: actor,
      member_revision: 7,
      binding_revision: 8,
      subscription_revision: null,
      enabled: false,
      can_edit: true,
      status: "unknown",
      reason: "not_shared",
      observed_at: null,
    };
  return null;
}

function stateFor(role = "parent") {
  const actor = {
    owner: "owner-1",
    parent: "parent-1",
    adult: "adult-1",
    child: "child-1",
    guest: "guest-1",
  }[role];
  const parent = role === "owner" || role === "parent";
  return {
    revision: 1,
    actor,
    role,
    settings: {
      name: "Synthetic family",
      timezone: "Europe/Kyiv",
      modules: ["presence"],
    },
    members: clone(MEMBERS),
    presence: {
      self: ownRow(actor),
      shared: parent
        ? [
            {
              member: "adult-1",
              member_revision: 3,
              status: "reported_away",
              reason: "fresh",
              observed_at: "2026-09-07T07:29:00+00:00",
            },
            {
              member: "child-1",
              member_revision: 7,
              status: "unknown",
              reason: "unavailable",
              observed_at: null,
            },
          ]
        : [],
    },
  };
}

async function setup(t, options = {}) {
  const state = stateFor(options.role);
  const calls = [];
  const receipts = new Map();
  let failure = null;
  const execute = (message) => {
    calls.push(clone(message));
    const row = state.presence.self;
    if (receipts.has(message.operation_id)) {
      const receipt = receipts.get(message.operation_id);
      assert.equal(row.member, receipt.member);
      assert.equal(row.subscription_revision, receipt.revision);
      assert.equal(row.enabled ? "enabled" : "disabled", receipt.status);
      return clone(receipt);
    }
    assert.equal(message.action, "presence.access_set");
    assert.deepEqual(Object.keys(message.payload).sort(), [
      "binding_revision",
      "enabled",
      "member",
      "member_revision",
      "subscription_revision",
    ]);
    assert.deepEqual(message.payload, {
      member: state.actor,
      member_revision: row.member_revision,
      binding_revision: row.binding_revision,
      subscription_revision: row.subscription_revision,
      enabled: !row.enabled,
    });
    if (failure === "before") {
      failure = null;
      throw Object.assign(new Error("transport failed"), {
        code: "transport_error",
      });
    }
    const revision =
      row.subscription_revision === null ? 1 : row.subscription_revision + 1;
    row.subscription_revision = revision;
    row.enabled = message.payload.enabled;
    row.status = row.enabled ? "reported_home" : "unknown";
    row.reason = row.enabled ? "fresh" : "not_shared";
    row.observed_at = row.enabled ? "2026-09-07T07:31:00+00:00" : null;
    const receipt = {
      member: row.member,
      revision,
      status: row.enabled ? "enabled" : "disabled",
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

  const card = document.createElement("family-presence-card");
  card.setConfig({
    type: "custom:family-presence-card",
    entry_id: "synthetic-presence",
    language: options.language || "en",
  });
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
      (roleHidden(state.role) || card.shadowRoot.querySelector(".presence")),
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
  };
}

function roleHidden(role) {
  return role === "guest";
}

function button(card, label) {
  return [...card.shadowRoot.querySelectorAll("button")].find(
    (item) => item.textContent === label,
  );
}

function confirmReview(card) {
  const checkbox = card.shadowRoot.querySelector(
    '.presence-review input[name="confirmed"]',
  );
  assert.ok(checkbox);
  checkbox.checked = true;
  checkbox.dispatchEvent(new Event("change", { bubbles: true }));
}

test("English, Russian, and Ukrainian presence copy has exact key parity", () => {
  const english = Object.keys(PRESENCE_COPY.en).sort();
  assert.deepEqual(Object.keys(PRESENCE_COPY.ru).sort(), english);
  assert.deepEqual(Object.keys(PRESENCE_COPY.uk).sort(), english);
  for (const locale of Object.values(PRESENCE_COPY))
    for (const value of Object.values(locale)) assert.ok(value.trim());
});

test("render is pure and privacy follows the projected role and module", async (t) => {
  const parent = await setup(t, { role: "parent" });
  const before = clone(parent.state);
  parent.card.render();
  assert.deepEqual(parent.state, before);
  assert.equal(
    parent.card.shadowRoot.querySelectorAll(".presence-shared-row").length,
    2,
  );
  assert.doesNotMatch(
    parent.card.shadowRoot.textContent,
    /person\.|device_tracker\.|SecretZone/,
  );
  assert.equal(
    parent.card.shadowRoot.querySelectorAll(".presence-shared-row button")
      .length,
    0,
  );

  for (const role of ["adult", "child"]) {
    const limited = await setup(t, { role });
    assert.ok(limited.card.shadowRoot.querySelector(".presence-self"));
    assert.equal(
      limited.card.shadowRoot.querySelectorAll(".presence-shared-row").length,
      0,
    );
    assert.doesNotMatch(
      limited.card.shadowRoot.textContent,
      /Adult One.*Child One|Child One.*Adult One/,
    );
  }
  const guest = await setup(t, { role: "guest" });
  assert.equal(guest.card.shadowRoot.querySelector(".presence"), null);

  parent.state.settings.modules = [];
  delete parent.state.presence;
  await parent.card.refresh();
  assert.equal(parent.card.shadowRoot.querySelector(".presence"), null);
  assert.equal(parent.card._presenceDraft, null);
});

test("unconfigured or removed source is display-only and cannot manufacture consent", async (t) => {
  const fixture = await setup(t, { role: "child", language: "uk" });
  fixture.state.presence.self = {
    ...fixture.state.presence.self,
    binding_revision: null,
    can_edit: false,
    reason: "unconfigured",
  };
  await fixture.card.refresh();
  assert.match(fixture.card.shadowRoot.textContent, /налаштован/);
  assert.equal(button(fixture.card, PRESENCE_COPY.uk.enable), undefined);
  assert.equal(fixture.calls.length, 0);

  fixture.state.presence.self.binding_revision = 9;
  await fixture.card.refresh();
  assert.match(fixture.card.shadowRoot.textContent, /налаштован/);
  assert.equal(button(fixture.card, PRESENCE_COPY.uk.enable), undefined);
  assert.equal(fixture.calls.length, 0);
});

test("named review sends the exact self-only consent payload", async (t) => {
  const { card, calls } = await setup(t, { role: "parent", language: "ru" });
  button(card, PRESENCE_COPY.ru.enable).click();
  assert.equal(calls.length, 0);
  const review = card.shadowRoot.querySelector(".presence-review");
  assert.match(review.textContent, /Parent One/);
  assert.match(review.textContent, /4/);
  confirmReview(card);
  button(card, PRESENCE_COPY.ru.save).click();
  await eventually(() => calls.length === 1 && card._presenceDraft === null);
  assert.deepEqual(calls[0].payload, {
    member: "parent-1",
    member_revision: 4,
    binding_revision: 4,
    subscription_revision: null,
    enabled: true,
  });
  assert.equal(typeof calls[0].operation_id, "string");
});

test("precommit and committed response-loss retries keep the frozen operation", async (t) => {
  const before = await setup(t, { role: "child" });
  before.failBefore();
  button(before.card, PRESENCE_COPY.en.enable).click();
  confirmReview(before.card);
  button(before.card, PRESENCE_COPY.en.save).click();
  await eventually(
    () => before.card._presenceDraft?.pending && !before.card._writing,
  );
  const first = clone(before.card._presenceDraft.pending);
  button(before.card, PRESENCE_COPY.en.retry).click();
  await eventually(
    () => before.calls.length === 2 && before.card._presenceDraft === null,
  );
  assert.equal(before.calls[1].operation_id, first.operation_id);
  assert.deepEqual(before.calls[1].payload, first.payload);

  const committed = await setup(t, { role: "adult" });
  committed.loseResponse();
  button(committed.card, PRESENCE_COPY.en.disable).click();
  confirmReview(committed.card);
  button(committed.card, PRESENCE_COPY.en.save).click();
  await eventually(
    () => committed.card._presenceDraft?.pending && !committed.card._writing,
  );
  const frozen = clone(committed.card._presenceDraft.pending);
  assert.ok(Object.isFrozen(committed.card._presenceDraft.pending));
  assert.equal(committed.state.presence.self.subscription_revision, 3);
  button(committed.card, PRESENCE_COPY.en.retry).click();
  await eventually(
    () =>
      committed.calls.length === 2 && committed.card._presenceDraft === null,
  );
  assert.equal(committed.calls[1].operation_id, frozen.operation_id);
  assert.deepEqual(committed.calls[1].payload, frozen.payload);
});

test("member, binding, subscription, entry, generation, and detached drift are inert", async (t) => {
  const mutations = [
    (fixture) => {
      fixture.card._data.members.find(
        (row) => row.id === fixture.state.actor,
      ).revision += 1;
      fixture.card._data.presence.self.member_revision += 1;
    },
    (fixture) => {
      fixture.card._data.presence.self.binding_revision += 1;
    },
    (fixture) => {
      fixture.card._data.presence.self.subscription_revision = 1;
    },
    (fixture) => {
      fixture.card._entry = "other-entry";
    },
    (fixture) => {
      fixture.card._generation += 1;
    },
  ];
  for (const mutate of mutations) {
    const fixture = await setup(t, { role: "child" });
    button(fixture.card, PRESENCE_COPY.en.enable).click();
    confirmReview(fixture.card);
    const save = button(fixture.card, PRESENCE_COPY.en.save);
    mutate(fixture);
    save.click();
    assert.equal(fixture.calls.length, 0);
    assert.equal(fixture.card._presenceDraft, null);
  }

  const detached = await setup(t, { role: "child" });
  const open = button(detached.card, PRESENCE_COPY.en.enable);
  detached.card.remove();
  open.click();
  assert.equal(detached.card._presenceDraft, null);
  assert.equal(detached.calls.length, 0);
});

test("shared consent disappearance forces stale focused DOM to be replaced", async (t) => {
  const fixture = await setup(t, { role: "parent" });
  const previous = clone(fixture.card._data);
  fixture.card._data.presence.shared = [];
  assert.equal(reconcilePresenceRefresh(fixture.card, previous), true);
  fixture.card.render();
  assert.equal(
    fixture.card.shadowRoot.querySelectorAll(".presence-shared-row").length,
    0,
  );
  assert.doesNotMatch(
    fixture.card.shadowRoot.textContent,
    /Adult One|Child One/,
  );
});
