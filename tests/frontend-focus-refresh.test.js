import assert from "node:assert/strict";
import { test } from "node:test";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><body><input id='outside'></body>", {
  url: "https://example.invalid",
  pretendToBeVisual: true,
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
const { captureFocusRefresh, renderWithFocusRefresh } =
  await import("../custom_components/family_assistant/frontend/focus-refresh.js");
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

const MEMBERS = [
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
];

function taskState() {
  return {
    revision: 12,
    actor: "parent-1",
    role: "parent",
    settings: { name: "Synthetic family", timezone: "UTC", modules: ["tasks"] },
    members: clone(MEMBERS),
    tasks: [],
    task_series: [],
  };
}

function pollState() {
  return {
    revision: 21,
    actor: "adult-1",
    role: "adult",
    settings: { name: "Synthetic family", timezone: "UTC", modules: ["polls"] },
    members: clone(MEMBERS),
    polls: {
      open: [
        {
          id: "PL000001",
          revision: 1,
          definition_revision: 1,
          status: "open",
          question: "Weekend plan?",
          options: [
            { id: "O1", label: "Garden" },
            { id: "O2", label: "Museum" },
          ],
          closes_at: "2030-09-08T18:00:00+00:00",
          ballot_mode: "private_mapping",
          eligible_count: 2,
          can_vote: true,
          own_ballot: null,
        },
      ],
      closed: [],
      archived: [],
    },
  };
}

async function setup(
  t,
  { type = "family-tasks-card", state = taskState() } = {},
) {
  const calls = [];
  const card = document.createElement(type);
  card.setConfig({
    type: `custom:${type}`,
    entry_id: "synthetic-focus",
    language: "en",
  });
  document.body.append(card);
  t.after(() => card.remove());
  card.hass = {
    language: "en",
    user: { id: "ha-user-1" },
    callWS: async (message) => {
      calls.push(clone(message));
      if (message.type === "family_assistant/view") return clone(state);
      throw new Error(`Unexpected WS ${message.type}`);
    },
  };
  await eventually(() => card._data?.revision === state.revision);
  return { card, state, calls };
}

function passiveRender(card, snapshot) {
  card._data = clone(card._data);
  return renderWithFocusRefresh(card, snapshot, () => card.render());
}

test("actual FamilyCard restores a uniquely labelled button after same-revision refresh", async (t) => {
  const { card } = await setup(t);
  const original = card.shadowRoot.querySelector(".toolbar button");
  original.focus();
  assert.equal(card.shadowRoot.activeElement, original);
  const snapshot = captureFocusRefresh(card);
  assert.equal(passiveRender(card, snapshot), true);
  const replacement = card.shadowRoot.querySelector(".toolbar button");
  assert.notEqual(replacement, original);
  assert.equal(card.shadowRoot.activeElement, replacement);
});

test("actual task archive summary keeps focus and disclosure state", async (t) => {
  const { card } = await setup(t);
  const details = card.shadowRoot.querySelector("details.tasks-archive");
  const summary = details.querySelector("summary");
  details.open = true;
  summary.focus();
  const snapshot = captureFocusRefresh(card);
  assert.equal(passiveRender(card, snapshot), true);
  const replacement = card.shadowRoot.querySelector("details.tasks-archive");
  assert.equal(replacement.open, true);
  assert.equal(
    card.shadowRoot.activeElement,
    replacement.querySelector("summary"),
  );
});

test("disclosure restoration does not deliver a toggle event to module handlers", async (t) => {
  const { card } = await setup(t);
  const details = card.shadowRoot.querySelector("details.tasks-archive");
  details.open = true;
  await tick();
  const snapshot = captureFocusRefresh(card);
  let toggles = 0;
  renderWithFocusRefresh(card, snapshot, () => {
    card.render();
    card.shadowRoot
      .querySelector("details.tasks-archive")
      .addEventListener("toggle", () => (toggles += 1));
  });
  await new Promise((resolve) => setTimeout(resolve, 120));
  assert.equal(toggles, 0);
  assert.equal(
    card.shadowRoot.querySelector("details.tasks-archive").open,
    true,
  );
});

test("immediate disclosure interaction wins over queued passive restoration", async (t) => {
  const { card } = await setup(t);
  const details = card.shadowRoot.querySelector("details.tasks-archive");
  details.open = true;
  await tick();
  const snapshot = captureFocusRefresh(card);
  let toggles = 0;
  renderWithFocusRefresh(card, snapshot, () => {
    card.render();
    card.shadowRoot
      .querySelector("details.tasks-archive")
      .addEventListener("toggle", () => (toggles += 1));
  });
  card.shadowRoot.querySelector("details.tasks-archive summary").click();
  await new Promise((resolve) => setTimeout(resolve, 120));
  assert.equal(
    card.shadowRoot.querySelector("details.tasks-archive").open,
    false,
  );
  assert.ok(toggles >= 1);
});

test("actual poll radio focus is restored without changing its choice", async (t) => {
  const { card } = await setup(t, {
    type: "family-polls-card",
    state: pollState(),
  });
  const vote = [...card.shadowRoot.querySelectorAll("button")].find(
    (button) => button.textContent === POLLS_COPY.en.vote,
  );
  vote.click();
  const radio = card.shadowRoot.querySelector(
    'input[type="radio"][value="O2"]',
  );
  radio.focus();
  assert.equal(radio.checked, false);
  const snapshot = captureFocusRefresh(card);
  assert.equal(passiveRender(card, snapshot), true);
  const replacement = card.shadowRoot.querySelector(
    'input[type="radio"][value="O2"]',
  );
  assert.equal(card.shadowRoot.activeElement, replacement);
  assert.equal(replacement.checked, false);
  assert.equal(card._pollsDraft.optionId, null);
});

test("latest in-card focus wins when the user moves while refresh is pending", async (t) => {
  const { card } = await setup(t);
  const buttonA = card.shadowRoot.querySelector(".toolbar button");
  const summary = card.shadowRoot.querySelector(
    "details.tasks-archive summary",
  );
  buttonA.focus();
  const snapshot = captureFocusRefresh(card);
  summary.focus();
  assert.equal(passiveRender(card, snapshot), true);
  assert.equal(
    card.shadowRoot.activeElement,
    card.shadowRoot.querySelector("details.tasks-archive summary"),
  );
});

test("focus moved outside the card is never reclaimed", async (t) => {
  const { card } = await setup(t);
  const button = card.shadowRoot.querySelector(".toolbar button");
  button.focus();
  const snapshot = captureFocusRefresh(card);
  const outside = document.querySelector("#outside");
  outside.focus();
  assert.equal(document.activeElement, outside);
  assert.equal(passiveRender(card, snapshot), false);
  assert.equal(document.activeElement, outside);
  assert.equal(card.shadowRoot.activeElement, null);
});

test("ambiguous repeated controls fail safe instead of targeting a lookalike", async (t) => {
  const { card } = await setup(t);
  const original = card.shadowRoot.querySelector(".toolbar button");
  const duplicate = original.cloneNode(true);
  original.parentElement.append(duplicate);
  original.focus();
  const snapshot = captureFocusRefresh(card);
  assert.equal(passiveRender(card, snapshot), false);
  assert.equal(card.shadowRoot.activeElement, null);
});

test("focus matching uses the node's owning realm and needs no global Element", async (t) => {
  const { card } = await setup(t);
  const button = card.shadowRoot.querySelector(".toolbar button");
  button.focus();
  const snapshot = captureFocusRefresh(card);
  const saved = globalThis.Element;
  try {
    delete globalThis.Element;
    assert.equal(passiveRender(card, snapshot), true);
    assert.equal(
      card.shadowRoot.activeElement,
      card.shadowRoot.querySelector(".toolbar button"),
    );
  } finally {
    globalThis.Element = saved;
  }
});

test("household, actor, role, module, entry, generation, and HA-user drift deny restoration", async (t) => {
  const mutations = [
    (card) => (card._data.revision += 1),
    (card) => (card._data.actor = "adult-1"),
    (card) => {
      card._data.role = "adult";
      card._data.members.find((member) => member.id === "parent-1").role =
        "adult";
    },
    (card) =>
      (card._data.members.find((member) => member.id === "parent-1").revision +=
        1),
    (card) => (card._data.settings.modules = []),
    (card) => (card._entry = "other-entry"),
    (card) => (card._generation += 1),
    (card) => (card._hass.user.id = "ha-user-2"),
  ];
  for (const mutate of mutations) {
    const { card } = await setup(t);
    const button = card.shadowRoot.querySelector(".toolbar button");
    button.focus();
    const snapshot = captureFocusRefresh(card);
    mutate(card);
    renderWithFocusRefresh(card, snapshot, () => card.render());
    assert.notEqual(
      card.shadowRoot.activeElement?.textContent,
      button.textContent,
    );
    card.remove();
  }
});

test("a renderer-selected focus target is not overridden", async (t) => {
  const { card } = await setup(t);
  const button = card.shadowRoot.querySelector(".toolbar button");
  button.focus();
  const snapshot = captureFocusRefresh(card);
  let selected;
  const restored = renderWithFocusRefresh(card, snapshot, () => {
    card.render();
    selected = card.shadowRoot.querySelector("details.tasks-archive summary");
    selected.focus();
  });
  assert.equal(restored, false);
  assert.equal(card.shadowRoot.activeElement, selected);
});

test("existing focused-form refresh suppression keeps the live input node", async (t) => {
  const fixture = await setup(t);
  fixture.card.shadowRoot.querySelector(".toolbar button").click();
  const input = fixture.card.shadowRoot.querySelector('input[name="title"]');
  input.value = "Draft survives";
  input.focus();
  await fixture.card.refresh();
  assert.equal(
    fixture.card.shadowRoot.querySelector('input[name="title"]'),
    input,
  );
  assert.equal(input.value, "Draft survives");
  assert.equal(fixture.card.shadowRoot.activeElement, input);
});
