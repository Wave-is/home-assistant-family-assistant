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
const { reconcilePollsRefresh } =
  await import("../custom_components/family_assistant/frontend/polls-view.js");
const { POLLS_COPY } =
  await import("../custom_components/family_assistant/frontend/polls-copy.js");

const clone = (value) => structuredClone(value);
const tick = () => new Promise((resolve) => setTimeout(resolve, 0));
async function eventually(predicate, message = "condition was not reached") {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    if (predicate()) return;
    await tick();
  }
  assert.fail(message);
}

function futureLocal(minutes = 24 * 60) {
  return new Date(Date.now() + minutes * 60_000).toISOString().slice(0, 16);
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
  const options = [
    { id: "O1", label: "Garden" },
    { id: "O2", label: "Museum" },
  ];
  const common = {
    definition_revision: 1,
    ballot_mode: "private_mapping",
    eligible_count: 3,
    closes_at: "2030-09-08T18:00:00+00:00",
  };
  const open = {
    ...common,
    id: "PL000001",
    revision: 1,
    status: "open",
    question: "Weekend plan?",
    options: clone(options),
    can_vote: role !== "guest",
    own_ballot: role === "adult" ? { option_id: "O1", revision: 2 } : null,
    ...(parent
      ? {
          eligible: [
            { member: "parent-1", member_revision: 4, current: true },
            { member: "adult-1", member_revision: 3, current: true },
            { member: "child-1", member_revision: 7, current: true },
          ],
          created_at: "2030-09-01T10:00:00Z",
          created_by: "parent-1",
          can_close: true,
        }
      : {}),
  };
  const closed = {
    ...common,
    id: "PL000002",
    revision: 2,
    status: "closed",
    question: "Film night?",
    options: clone(options),
    can_vote: false,
    own_ballot: null,
    closed_at: "2030-09-07T18:00:00Z",
    results: [
      { option_id: "O1", count: 2 },
      { option_id: "O2", count: 1 },
    ],
    cast_count: 3,
    ...(parent
      ? {
          eligible: [
            { member: "parent-1", member_revision: 4, current: true },
            { member: "adult-1", member_revision: 3, current: true },
            { member: "child-1", member_revision: 7, current: true },
          ],
          created_at: "2030-09-01T10:00:00Z",
          created_by: "parent-1",
          can_archive: true,
        }
      : {}),
  };
  const archived = {
    ...common,
    id: "PL000003",
    revision: 3,
    status: "archived",
    question: "Old aggregate?",
    options: clone(options),
    closed_at: "2030-08-01T18:00:00Z",
    archived_at: "2030-08-02T18:00:00Z",
    results: [
      { option_id: "O1", count: 1 },
      { option_id: "O2", count: 1 },
    ],
    cast_count: 2,
    ...(role === "owner" ? { can_purge: true } : {}),
  };
  return {
    revision: 1,
    actor,
    role,
    settings: { name: "Synthetic family", timezone: "UTC", modules: ["polls"] },
    members: [
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
    ],
    polls: {
      open: role === "guest" ? [] : [open],
      closed: role === "guest" ? [] : [closed],
      archived: parent ? [archived] : [],
    },
  };
}

async function setup(t, { role = "parent", language = "en" } = {}) {
  const state = stateFor(role);
  const calls = [];
  const receipts = new Map();
  let loseNext = false;
  let failBefore = false;
  const execute = (message) => {
    calls.push(clone(message));
    if (message.action === "pantry.meal_save")
      return { id: "MP000001", revision: 1, status: "draft" };
    if (receipts.has(message.operation_id))
      return clone(receipts.get(message.operation_id));
    if (failBefore) {
      failBefore = false;
      const error = new Error("failed before commit");
      error.code = "transport_error";
      throw error;
    }
    const payload = message.payload;
    let result;
    if (message.action === "polls.create") {
      const id = `PL${String(state.polls.open.length + 10).padStart(6, "0")}`;
      state.polls.open.push({
        id,
        revision: 1,
        definition_revision: 1,
        status: "open",
        question: payload.question,
        options: payload.options.map((label, index) => ({
          id: `O${index + 1}`,
          label,
        })),
        closes_at: payload.closes_at,
        ballot_mode: "private_mapping",
        eligible_count: payload.eligible.length,
        can_vote: payload.eligible.some((item) => item.member === state.actor),
        own_ballot: null,
        eligible: payload.eligible.map((item) => ({
          member: item.member,
          member_revision: item.revision,
          current: true,
        })),
        created_at: "2030-09-01T10:00:00Z",
        created_by: state.actor,
        can_close: true,
      });
      result = { id, revision: 1, status: "open" };
    } else if (message.action === "polls.vote") {
      const row = [...state.polls.open, ...state.polls.closed].find(
        (item) => item.id === payload.id,
      );
      assert.ok(row);
      const revision =
        payload.ballot_revision === null ? 1 : payload.ballot_revision + 1;
      row.own_ballot = { option_id: payload.option_id, revision };
      result = { id: row.id, ballot_revision: revision };
    } else if (message.action === "polls.close") {
      const index = state.polls.open.findIndex(
        (item) => item.id === payload.id,
      );
      const row = state.polls.open.splice(index, 1)[0];
      row.status = "closed";
      row.revision += 1;
      row.can_vote = false;
      row.can_close = false;
      row.can_archive = true;
      row.closed_at = "2030-09-07T18:00:00Z";
      row.results = row.options.map((option) => ({
        option_id: option.id,
        count: 0,
      }));
      row.cast_count = row.own_ballot ? 1 : 0;
      state.polls.closed.push(row);
      result = { id: row.id, revision: row.revision, status: "closed" };
    } else if (message.action === "polls.archive") {
      const index = state.polls.closed.findIndex(
        (item) => item.id === payload.id,
      );
      const row = state.polls.closed.splice(index, 1)[0];
      row.status = "archived";
      row.revision += 1;
      row.archived_at = "2030-09-08T18:00:00Z";
      delete row.eligible;
      delete row.created_by;
      delete row.own_ballot;
      delete row.can_archive;
      if (state.role === "owner") row.can_purge = true;
      state.polls.archived.push(row);
      result = { id: row.id, revision: row.revision, status: "archived" };
    } else if (message.action === "polls.purge") {
      const index = state.polls.archived.findIndex(
        (item) => item.id === payload.id,
      );
      assert.notEqual(index, -1);
      state.polls.archived.splice(index, 1);
      result = { id: payload.id, status: "deleted" };
    } else {
      throw new Error(`Unexpected action ${message.action}`);
    }
    state.revision += 1;
    receipts.set(message.operation_id, result);
    if (loseNext) {
      loseNext = false;
      const error = new Error("response lost");
      error.code = "response_lost";
      throw error;
    }
    return clone(result);
  };

  const card = document.createElement("family-polls-card");
  card.setConfig({
    type: "custom:family-polls-card",
    entry_id: "synthetic",
    language,
  });
  document.body.append(card);
  t.after(() => card.remove());
  card.hass = {
    language,
    user: { id: `${state.actor}-ha` },
    callWS: async (message) => {
      if (message.type === "family_assistant/view") return clone(state);
      if (message.type === "family_assistant/execute") return execute(message);
      throw new Error(`Unexpected WS ${message.type}`);
    },
  };
  await eventually(
    () =>
      card._data?.actor === state.actor &&
      (role === "guest"
        ? !card.shadowRoot.querySelector(".polls-section")
        : card.shadowRoot.querySelector(".polls-section")),
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
  return [...card.shadowRoot.querySelectorAll("button")].find(
    (item) => item.textContent === label,
  );
}

function confirm(card) {
  const checkbox = card.shadowRoot.querySelector(
    '[data-poll-form="review"] [name="confirmed"]',
  );
  assert.ok(checkbox);
  checkbox.checked = true;
  checkbox.dispatchEvent(new Event("change", { bubbles: true }));
  button(card, POLLS_COPY[card._config.language].save).click();
}

test("English, Russian, and Ukrainian poll copy has exact key parity", () => {
  const keys = Object.keys(POLLS_COPY.en).sort();
  assert.deepEqual(Object.keys(POLLS_COPY.ru).sort(), keys);
  assert.deepEqual(Object.keys(POLLS_COPY.uk).sort(), keys);
  for (const locale of Object.values(POLLS_COPY))
    for (const value of Object.values(locale)) assert.ok(value.trim());
});

test("render is pure, guests and module revocation are hidden, and only closed rows show totals", async (t) => {
  const fixture = await setup(t);
  const before = clone(fixture.state);
  fixture.card.render();
  assert.deepEqual(fixture.state, before);
  const open = fixture.card.shadowRoot.querySelector(
    '[data-poll-id="PL000001"]',
  );
  const closed = fixture.card.shadowRoot.querySelector(
    '[data-poll-id="PL000002"]',
  );
  assert.equal(open.querySelector(".poll-results"), null);
  assert.match(open.textContent, /Totals appear only after/);
  assert.match(closed.querySelector(".poll-results").textContent, /Garden: 2/);

  const guest = await setup(t, { role: "guest" });
  assert.equal(guest.card.shadowRoot.querySelector(".polls-section"), null);
  const adult = await setup(t, { role: "adult" });
  adult.card._data.polls.archived = clone(stateFor("owner").polls.archived);
  adult.card.render();
  assert.equal(
    adult.card.shadowRoot.querySelector('[data-poll-id="PL000003"]'),
    null,
  );
  fixture.state.settings.modules = [];
  await fixture.card.refresh();
  assert.equal(fixture.card.shadowRoot.querySelector(".polls-section"), null);
  assert.equal(fixture.card._pollsDraft, null);
});

test("parent creates an exact named poll review with current member epochs and household deadline", async (t) => {
  const { card, calls } = await setup(t);
  button(card, POLLS_COPY.en.create).click();
  const form = card.shadowRoot.querySelector('[data-poll-form="create"]');
  form.querySelector('[name="question"]').value = "  Where this weekend?  ";
  form
    .querySelector('[name="question"]')
    .dispatchEvent(new Event("input", { bubbles: true }));
  const options = form.querySelectorAll(".poll-option-editor input");
  for (const [input, value] of [
    [options[0], " Park "],
    [options[1], "Museum"],
  ]) {
    input.value = value;
    input.dispatchEvent(new Event("input", { bubbles: true }));
  }
  for (const id of ["parent-1", "child-1"]) {
    const checkbox = form.querySelector(`.poll-eligible input[value="${id}"]`);
    checkbox.checked = true;
    checkbox.dispatchEvent(new Event("change", { bubbles: true }));
  }
  const closes = form.querySelector('[name="closes_at"]');
  closes.value = futureLocal();
  closes.dispatchEvent(new Event("input", { bubbles: true }));
  form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  assert.equal(calls.length, 0);
  const review = card.shadowRoot.querySelector('[data-poll-form="review"]');
  assert.match(review.textContent, /Where this weekend/);
  assert.match(review.textContent, /Parent One, Child One/);
  assert.match(review.textContent, /not anonymous/);
  confirm(card);
  await eventually(() => calls.length === 1 && card._pollsDraft === null);
  assert.deepEqual(calls[0].payload, {
    actor_revision: 4,
    question: "Where this weekend?",
    options: ["Park", "Museum"],
    eligible: [
      { member: "parent-1", revision: 4 },
      { member: "child-1", revision: 7 },
    ],
    closes_at: `${closes.value}:00.000Z`,
    confirm_private_ballot_limits: true,
  });
  assert.equal(typeof calls[0].operation_id, "string");
});

test("adult revote uses only the private own-ballot revision and a named Russian review", async (t) => {
  const { card, calls } = await setup(t, { role: "adult", language: "ru" });
  assert.equal(
    card.shadowRoot.querySelector('[data-poll-id="PL000001"] .poll-results'),
    null,
  );
  button(card, POLLS_COPY.ru.revote).click();
  let form = card.shadowRoot.querySelector('[data-poll-form="vote"]');
  form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  assert.equal(calls.length, 0);
  assert.equal(card._pollsDraft.kind, "vote");
  form = card.shadowRoot.querySelector('[data-poll-form="vote"]');
  const choice = form.querySelector('input[value="O2"]');
  choice.checked = true;
  choice.dispatchEvent(new Event("change", { bubbles: true }));
  form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  assert.equal(calls.length, 0);
  assert.match(
    card.shadowRoot.querySelector('[data-poll-form="review"]').textContent,
    /Museum/,
  );
  confirm(card);
  await eventually(() => calls.length === 1 && card._pollsDraft === null);
  assert.deepEqual(calls[0].payload, {
    id: "PL000001",
    definition_revision: 1,
    voter_revision: 3,
    option_id: "O2",
    ballot_revision: 2,
  });
  assert.equal("eligible" in calls[0].payload, false);
});

test("committed vote response loss retries the frozen request after unrelated card work", async (t) => {
  const fixture = await setup(t, { role: "adult" });
  fixture.lose();
  button(fixture.card, POLLS_COPY.en.revote).click();
  const form = fixture.card.shadowRoot.querySelector('[data-poll-form="vote"]');
  const choice = form.querySelector('input[value="O2"]');
  choice.checked = true;
  choice.dispatchEvent(new Event("change", { bubbles: true }));
  form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  confirm(fixture.card);
  await eventually(
    () => fixture.card._pollsDraft?.pending && !fixture.card._writing,
  );
  const frozen = clone(fixture.card._pollsDraft.pending);
  assert.ok(Object.isFrozen(fixture.card._pollsDraft.pending));
  assert.ok(Object.isFrozen(fixture.card._pollsDraft.pending.payload));
  await fixture.card.command("pantry.meal_save", { title: "Unrelated card" });
  button(fixture.card, POLLS_COPY.en.retry).click();
  await eventually(
    () => fixture.calls.length === 3 && fixture.card._pollsDraft === null,
  );
  assert.deepEqual(fixture.calls[2].payload, frozen.payload);
  assert.equal(fixture.calls[2].operation_id, frozen.operation_id);
  assert.deepEqual(fixture.calls[2], fixture.calls[0]);
});

test("failure before commit retains the exact reviewed vote for retry", async (t) => {
  const fixture = await setup(t, { role: "child" });
  fixture.failBefore();
  button(fixture.card, POLLS_COPY.en.vote).click();
  const form = fixture.card.shadowRoot.querySelector('[data-poll-form="vote"]');
  const choice = form.querySelector('input[value="O1"]');
  choice.checked = true;
  choice.dispatchEvent(new Event("change", { bubbles: true }));
  form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  confirm(fixture.card);
  await eventually(
    () => fixture.card._pollsDraft?.pending && !fixture.card._writing,
  );
  const frozen = clone(fixture.card._pollsDraft.pending);
  button(fixture.card, POLLS_COPY.en.retry).click();
  await eventually(
    () => fixture.calls.length === 2 && fixture.card._pollsDraft === null,
  );
  assert.deepEqual(fixture.calls[1].payload, frozen.payload);
  assert.equal(fixture.calls[1].operation_id, frozen.operation_id);
  assert.deepEqual(fixture.calls[1], fixture.calls[0]);
});

test("owner close, archive, and destructive purge each require a separate exact confirmation", async (t) => {
  const { card, calls, state } = await setup(t, {
    role: "owner",
    language: "uk",
  });
  button(card, POLLS_COPY.uk.close).click();
  assert.match(
    card.shadowRoot.querySelector('[data-poll-form="review"]').textContent,
    /Weekend plan/,
  );
  assert.equal(calls.length, 0);
  confirm(card);
  await eventually(() => calls.length === 1 && card._pollsDraft === null);
  assert.deepEqual(calls[0].payload, {
    id: "PL000001",
    revision: 1,
    actor_revision: 2,
  });

  const newlyClosed = state.polls.closed.find((item) => item.id === "PL000001");
  assert.equal(newlyClosed.status, "closed");
  const archiveRow = card.shadowRoot.querySelector('[data-poll-id="PL000001"]');
  [...archiveRow.querySelectorAll("button")]
    .find((item) => item.textContent === POLLS_COPY.uk.archive)
    .click();
  confirm(card);
  await eventually(() => calls.length === 2 && card._pollsDraft === null);
  assert.deepEqual(calls[1].payload, {
    id: "PL000001",
    revision: 2,
    actor_revision: 2,
  });

  const archived = card.shadowRoot.querySelector('[data-poll-id="PL000001"]');
  archived.open = true;
  [...archived.querySelectorAll("button")]
    .find((item) => item.textContent === POLLS_COPY.uk.purge)
    .click();
  const review = card.shadowRoot.querySelector('[data-poll-form="review"]');
  assert.match(review.textContent, /не можна скасувати/);
  assert.equal(calls.length, 2);
  confirm(card);
  await eventually(() => calls.length === 3 && card._pollsDraft === null);
  assert.deepEqual(calls[2].payload, {
    id: "PL000001",
    revision: 3,
    actor_revision: 2,
    confirm_delete: true,
  });
  assert.equal(
    state.polls.archived.some((item) => item.id === "PL000001"),
    false,
  );
});

test("stale definitions, member epochs, actor scope, and detached controls are inert", async (t) => {
  const vote = await setup(t, { role: "adult" });
  const oldVote = button(vote.card, POLLS_COPY.en.revote);
  vote.card._data = clone(vote.card._data);
  vote.card._data.polls.open[0].definition_revision = 2;
  oldVote.click();
  assert.equal(vote.card._pollsDraft, null);
  assert.equal(vote.calls.length, 0);

  const create = await setup(t);
  button(create.card, POLLS_COPY.en.create).click();
  const form = create.card.shadowRoot.querySelector(
    '[data-poll-form="create"]',
  );
  const child = form.querySelector('.poll-eligible input[value="child-1"]');
  child.checked = true;
  child.dispatchEvent(new Event("change", { bubbles: true }));
  const previous = clone(create.card._data);
  create.card._data.members.find((item) => item.id === "child-1").revision = 8;
  assert.equal(reconcilePollsRefresh(create.card, previous), true);
  assert.equal(create.card._pollsDraft, null);

  for (const mutate of [
    (fixture) => {
      fixture.card._entry = "other-entry";
    },
    (fixture) => {
      fixture.card._generation += 1;
    },
    (fixture) => {
      fixture.card._data.role = "adult";
      fixture.card._data.members.find((item) => item.id === "parent-1").role =
        "adult";
    },
    (fixture) => {
      fixture.card._data.settings.modules = [];
    },
  ]) {
    const stale = await setup(t);
    const open = button(stale.card, POLLS_COPY.en.create);
    mutate(stale);
    open.click();
    assert.equal(stale.card._pollsDraft, null);
    assert.equal(stale.calls.length, 0);
  }

  const detached = await setup(t);
  const open = button(detached.card, POLLS_COPY.en.create);
  detached.card.remove();
  open.click();
  assert.equal(detached.card._pollsDraft, null);
  assert.equal(detached.calls.length, 0);
});
