import assert from "node:assert/strict";
import { test } from "node:test";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><body><div id=\"root\"></div></body>", { url: "http://localhost" });
for (const k of ["window", "document", "HTMLElement", "customElements", "CustomEvent", "FormData", "Option"]) {
  globalThis[k] = dom.window[k];
}

const { ROUTINES_COPY, renderRoutines, reconcileRoutineRefresh } = await import(
  "../custom_components/family_assistant/frontend/routines-view.js"
);

function createMockCard({
  role = "parent",
  actor = "p1",
  timezone = "UTC",
  lang = "en",
  members = [
    { id: "p1", name: "Parent One", role: "parent", active: true },
    { id: "c1", name: "Child One", role: "child", active: true },
    { id: "g1", name: "Guest One", role: "guest", active: true },
  ],
  routines = {
    templates: [],
    presets: [],
    config: { modes: ["normal"], entity_allowlist: ["binary_sensor.front_door"], revision: 1 },
    runs: [],
  },
  modules = ["routines"],
} = {}) {
  const commands = [];
  const card = {
    _generation: 1,
    _entry: "entry_1",
    _data: {
      role,
      actor,
      settings: { timezone, modules },
      members: members.map((member) => ({revision: 1, ...member, ...(member.id === actor ? {role} : {})})),
      routines,
    },
    _config: { language: lang },
    _hass: { language: lang, config: { time_zone: timezone } },
    parent: ["owner", "parent"].includes(role),
    _writing: false,
    _routineDraft: null,
    _actionError: null,
    commands,
    button(text, action, primary = false) {
      const btn = document.createElement("button");
      btn.textContent = text;
      if (primary) btn.className = "primary";
      btn.type = "button";
      btn.disabled = Boolean(card._writing);
      btn.addEventListener("click", action);
      return btn;
    },
    async command(action, payload, operationId) {
      commands.push({ action, payload });
      card.lastOperationId = operationId;
      return { success: true };
    },
    render() {},
  };
  return card;
}

function getConnectedContainer() {
  const container = document.createElement("div");
  document.getElementById("root").replaceChildren(container);
  return container;
}

test("1. ROUTINES_COPY RU UK EN key parity and non-empty values", () => {
  const enKeys = Object.keys(ROUTINES_COPY.en).sort();
  const ruKeys = Object.keys(ROUTINES_COPY.ru).sort();
  const ukKeys = Object.keys(ROUTINES_COPY.uk).sort();
  assert.deepEqual(ruKeys, enKeys, "RU keys must match EN keys");
  assert.deepEqual(ukKeys, enKeys, "UK keys must match EN keys");
  for (const k of enKeys) {
    assert.ok(typeof ROUTINES_COPY.en[k] === "string" && ROUTINES_COPY.en[k].length > 0);
    assert.ok(typeof ROUTINES_COPY.ru[k] === "string" && ROUTINES_COPY.ru[k].length > 0);
    assert.ok(typeof ROUTINES_COPY.uk[k] === "string" && ROUTINES_COPY.uk[k].length > 0);
  }
});

test("2. Guest role or routines module disabled clears drafts and outputs no controls", () => {
  const guestCard = createMockCard({ role: "guest" });
  guestCard._routineDraft = { type: "create_template", title: "Should be cleared" };
  const guestBody = getConnectedContainer();
  renderRoutines(guestCard, guestBody);
  assert.equal(guestCard._routineDraft, null);
  assert.equal(guestBody.children.length, 0);

  const noModCard = createMockCard({ modules: [] });
  noModCard._routineDraft = { type: "create_template", title: "Should be cleared" };
  const noModBody = getConnectedContainer();
  renderRoutines(noModCard, noModBody);
  assert.equal(noModCard._routineDraft, null);
  assert.equal(noModBody.children.length, 0);
});

test("3. Stale identity, entry, generation, role and detached submit perform no change", async () => {
  const card = createMockCard({ role: "parent" });
  card._routineDraft = {
    type: "create_template",
    title: "Draft 1",
    assignees: ["p1"],
    steps: [
      {
        title: "Step 1",
        raw_offset: "0",
        confirmation: "manual",
        raw_escalate: "15",
        skip_when: null,
        skip_dirty: false,
        completion_condition: null,
        completion_dirty: false,
      },
    ],
  };

  const body = getConnectedContainer();
  renderRoutines(card, body);
  const form = body.querySelector("form");
  assert.ok(form, "Form should be rendered");

  // Detach body from DOM -> submission must be ignored
  body.remove();
  form.dispatchEvent(new dom.window.Event("submit", { cancelable: true }));
  assert.equal(card.commands.length, 0);

  // Re-connect and test stale actor
  const connectedBody = getConnectedContainer();
  renderRoutines(card, connectedBody);
  card._data.actor = "other_actor";
  const form2 = connectedBody.querySelector("form");
  form2.dispatchEvent(new dom.window.Event("submit", { cancelable: true }));
  assert.equal(card.commands.length, 0);
});

test("4. Parent template creation preserves step order and rejects descending offsets with localized error", async () => {
  const card = createMockCard({ role: "parent" });
  const body = getConnectedContainer();
  renderRoutines(card, body);

  // Click "New routine"
  const newBtn = Array.from(body.querySelectorAll("button")).find(
    (b) => b.textContent === ROUTINES_COPY.en.new_template
  );
  assert.ok(newBtn);
  newBtn.click();

  // Re-render
  renderRoutines(card, body);
  assert.equal(card._routineDraft?.type, "create_template");

  // Set steps with descending offsets (Step 1: 10 min, Step 2: 5 min)
  card._routineDraft.title = "Morning Routine";
  card._routineDraft.assignees = ["p1"];
  card._routineDraft.steps = [
    {
      title: "Second Step",
      raw_offset: "10",
      confirmation: "manual",
      raw_escalate: "15",
      skip_when: null,
      skip_dirty: false,
      completion_condition: null,
      completion_dirty: false,
    },
    {
      title: "First Step",
      raw_offset: "5",
      confirmation: "manual",
      raw_escalate: "15",
      skip_when: null,
      skip_dirty: false,
      completion_condition: null,
      completion_dirty: false,
    },
  ];

  renderRoutines(card, body);
  const form = body.querySelector("form");
  form.dispatchEvent(new dom.window.Event("submit", { cancelable: true }));

  // Must reject and not sort
  assert.equal(card.commands.length, 0);
  assert.equal(card._actionError, ROUTINES_COPY.en.step_order_descending);
  assert.equal(card._routineDraft.steps[0].title, "Second Step");
  assert.equal(card._routineDraft.steps[1].title, "First Step");

  // Fix offset to non-decreasing (Step 1: 0 min, Step 2: 5 min)
  card._routineDraft.steps[0].raw_offset = "0";
  card._routineDraft.steps[1].raw_offset = "5";
  form.dispatchEvent(new dom.window.Event("submit", { cancelable: true }));

  assert.equal(card.commands.length, 1);
  assert.equal(card.commands[0].action, "routines.save");
  assert.equal(card.commands[0].payload.steps[0].title, "Second Step");
  assert.equal(card.commands[0].payload.steps[1].title, "First Step");
  assert.equal(card.commands[0].payload.steps[0].offset_minutes, 0);
  assert.equal(card.commands[0].payload.steps[1].offset_minutes, 5);
});

test("5. Negated and complex conditions survive template metadata edits", async () => {
  const complexSkip = {
    kind: "any",
    negate: false,
    conditions: [
      { kind: "mode", mode: "holidays", negate: true },
      { kind: "time_window", start: "08:00", end: "12:00", timezone: "UTC", negate: false },
    ],
  };
  const complexComp = {
    kind: "all",
    negate: false,
    conditions: [
      { kind: "entity_state", entity_id: "binary_sensor.front_door", state: "on", max_age_seconds: 60, negate: false },
    ],
  };

  const existingTemplate = {
    id: "t1",
    revision: 2,
    title: "Existing Routine",
    description: "Old description",
    enabled: true,
    assignees: ["p1"],
    rule: null,
    skip_when: complexSkip,
    steps: [
      {
        title: "Step with complex conditions",
        offset_minutes: 0,
        confirmation: "entity_state",
        escalate_minutes: null,
        skip_when: complexSkip,
        completion_condition: complexComp,
      },
    ],
  };

  const card = createMockCard({
    role: "parent",
    routines: {
      templates: [existingTemplate],
      presets: [],
      config: { modes: ["normal"], entity_allowlist: ["binary_sensor.front_door"], revision: 1 },
      runs: [],
    },
  });

  const body = getConnectedContainer();
  renderRoutines(card, body);

  // Click edit
  const editBtn = Array.from(body.querySelectorAll("button")).find(
    (b) => b.textContent === ROUTINES_COPY.en.edit
  );
  assert.ok(editBtn);
  editBtn.click();

  renderRoutines(card, body);
  assert.equal(card._routineDraft?.type, "edit_template");
  assert.equal(
    body.querySelector('[data-condition-scope="step-0-skip"] legend').textContent,
    "Skip this step when",
  );
  assert.equal(
    body.querySelector('[data-condition-scope="step-0-completion"] legend').textContent,
    "Complete this step automatically when",
  );

  // Modify title only
  card._routineDraft.title = "Updated Routine Title";
  renderRoutines(card, body);

  const form = body.querySelector("form");
  form.dispatchEvent(new dom.window.Event("submit", { cancelable: true }));

  assert.equal(card.commands.length, 1);
  const payload = card.commands[0].payload;
  assert.equal(payload.title, "Updated Routine Title");
  assert.deepEqual(payload.skip_when, complexSkip);
  assert.deepEqual(payload.steps[0].skip_when, complexSkip);
  assert.deepEqual(payload.steps[0].completion_condition, complexComp);
  assert.equal(payload.steps[0].escalate_minutes, null);
});

test("6. Conditional completion survives an in-draft manual toggle but saves null in manual mode", async () => {
  const completion = {
    kind: "entity_state",
    entity_id: "binary_sensor.front_door",
    state: "on",
    max_age_seconds: 60,
    negate: false,
  };
  const existingTemplate = {
    id: "t1",
    revision: 3,
    title: "Toggle completion",
    description: "",
    enabled: true,
    assignees: ["p1"],
    rule: null,
    skip_when: null,
    steps: [
      {
        title: "Observed step",
        offset_minutes: 0,
        confirmation: "entity_state",
        escalate_minutes: 15,
        skip_when: null,
        completion_condition: completion,
      },
    ],
  };
  const card = createMockCard({
    routines: {
      templates: [existingTemplate],
      presets: [],
      config: {
        modes: ["normal"],
        entity_allowlist: ["binary_sensor.front_door"],
        revision: 1,
      },
      runs: [],
    },
  });
  const body = getConnectedContainer();
  renderRoutines(card, body);
  [...body.querySelectorAll("button")]
    .find((button) => button.textContent === ROUTINES_COPY.en.edit)
    .click();
  renderRoutines(card, body);

  let confirmation = body.querySelector('[data-step-confirmation="0"]');
  confirmation.value = "manual";
  confirmation.dispatchEvent(new dom.window.Event("change", { bubbles: true }));
  assert.equal(body.querySelector('[data-condition-scope="step-0-completion"]'), null);
  assert.ok(body.textContent.includes(ROUTINES_COPY.en.completion_inactive_notice));
  assert.deepEqual(card._routineDraft.steps[0].completion_condition, completion);

  confirmation = body.querySelector('[data-step-confirmation="0"]');
  confirmation.value = "entity_state";
  confirmation.dispatchEvent(new dom.window.Event("change", { bubbles: true }));
  assert.equal(
    body.querySelector(
      '[data-condition-scope="step-0-completion"] [data-condition-field="state"]',
    ).value,
    "on",
  );

  confirmation = body.querySelector('[data-step-confirmation="0"]');
  confirmation.value = "manual";
  confirmation.dispatchEvent(new dom.window.Event("change", { bubbles: true }));
  body
    .querySelector("form")
    .dispatchEvent(new dom.window.Event("submit", { cancelable: true }));
  assert.equal(card.commands.length, 1);
  assert.equal(card.commands[0].payload.steps[0].confirmation, "manual");
  assert.equal(card.commands[0].payload.steps[0].completion_condition, null);
});

test("7. A frozen draft without its original operation cannot be silently replayed", async () => {
  const card = createMockCard({ role: "parent" });
  const frozenPayload = {
    id: "run_1",
    revision: 1,
    reason: "Severe weather",
  };
  card._actionError = "not_ready";
  card._routineDraft = {
    type: "cancel_run",
    run_id: "run_1",
    revision: 1,
    reason: "Severe weather",
    frozenPayload,
  };

  const activeRun = {
    id: "run_1",
    revision: 1,
    title: "Daily Run",
    member: "p1",
    status: "active",
    started_at: "2026-09-06T12:00:00Z",
    steps: [{ title: "Step 1", status: "active", confirmation: "manual", nonce: "nonce1" }],
    history: [],
  };
  card._data.routines.runs = [activeRun];

  const body = getConnectedContainer();
  renderRoutines(card, body);

  const retryBtn = Array.from(body.querySelectorAll("button")).find(
    (b) => b.textContent === ROUTINES_COPY.en.retry
  );
  assert.ok(retryBtn, "Retry button must be visible when frozen and action error exists");

  // This legacy in-memory draft lacks the original operation ID. Do not invent one.
  activeRun.revision = 2;
  const form = body.querySelector("form");
  form.dispatchEvent(new dom.window.Event("submit", { cancelable: true }));

  assert.equal(card.commands.length, 0);
  assert.equal(card._actionError, "conflict");
  assert.equal(card._routineDraft, null);
});

test("run-start frozen retry owns its operation independently of the global command slot", async () => {
  const template={id:"U1",revision:1,title:"Routine",description:"",enabled:true,assignees:["c1"],steps:[]};
  const card=createMockCard({routines:{templates:[template],runs:[],config:{revision:1,modes:["normal"],entity_allowlist:[]}}});
  card._routineDraft={type:"start_run",template_id:"U1",revision:1,member:"c1",assignees:["c1"]};
  const body=getConnectedContainer();
  const calls=[];
  card.command=async(action,payload,operationId)=>{calls.push({action,payload:structuredClone(payload),operationId});card._actionError="storage_error";};
  renderRoutines(card,body);
  body.querySelector("form").dispatchEvent(new dom.window.Event("submit",{cancelable:true}));
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(calls.length,1);
  assert.match(calls[0].operationId,/^[0-9a-f-]{36}$/);
  card._pending={id:"another-operation",fingerprint:"unrelated"};
  renderRoutines(card,body);
  body.querySelector("form").dispatchEvent(new dom.window.Event("submit",{cancelable:true}));
  await new Promise(resolve=>setImmediate(resolve));
  assert.deepEqual(calls[1],calls[0]);
});

test("8. Step conditions use the current allowlist and untouched opaque values are not rewritten", async () => {
  const opaque = { kind: "future_condition", future_payload: "KEEP-EXACT" };
  const template = {
    id: "opaque-template",
    revision: 4,
    title: "Opaque step",
    description: "",
    enabled: true,
    assignees: ["p1"],
    rule: null,
    skip_when: null,
    steps: [
      {
        title: "Future skip",
        offset_minutes: 0,
        confirmation: "manual",
        escalate_minutes: 15,
        skip_when: opaque,
        completion_condition: null,
      },
    ],
  };
  const card = createMockCard({
    routines: {
      templates: [template],
      presets: [],
      config: {
        modes: ["normal"],
        entity_allowlist: ["binary_sensor.front_door"],
        revision: 1,
      },
      runs: [],
    },
  });
  const body = getConnectedContainer();
  renderRoutines(card, body);
  [...body.querySelectorAll("button")]
    .find((button) => button.textContent === ROUTINES_COPY.en.edit)
    .click();
  renderRoutines(card, body);
  assert.ok(body.textContent.includes("not supported by this editor"));
  card._routineDraft.title = "Metadata only";
  body
    .querySelector("form")
    .dispatchEvent(new dom.window.Event("submit", { cancelable: true }));
  assert.deepEqual(card.commands[0].payload.steps[0].skip_when, opaque);

  const guarded = createMockCard({
    routines: {
      templates: [
        {
          ...template,
          id: "allowlist-template",
          steps: [
            {
              ...template.steps[0],
              skip_when: {
                kind: "entity_state",
                entity_id: "binary_sensor.front_door",
                state: "on",
                negate: false,
              },
            },
          ],
        },
      ],
      presets: [],
      config: {
        modes: ["normal"],
        entity_allowlist: ["binary_sensor.front_door"],
        revision: 1,
      },
      runs: [],
    },
  });
  const guardedBody = getConnectedContainer();
  renderRoutines(guarded, guardedBody);
  [...guardedBody.querySelectorAll("button")]
    .find((button) => button.textContent === ROUTINES_COPY.en.edit)
    .click();
  renderRoutines(guarded, guardedBody);
  guarded._data.routines.config.entity_allowlist = [];
  guardedBody
    .querySelector("form")
    .dispatchEvent(new dom.window.Event("submit", { cancelable: true }));
  assert.equal(guarded.commands.length, 0);
  assert.equal(guarded._actionError, ROUTINES_COPY.en.condition_error);
  assert.equal(
    guarded._routineDraft.steps[0].skip_when.entity_id,
    "binary_sensor.front_door",
  );
});

test("9. A frozen template request may replay after its first commit advanced revision", async () => {
  const payload = {
    id: "template-retry",
    revision: 2,
    title: "Frozen template",
    description: "",
    enabled: true,
    assignees: ["p1"],
    rule: null,
    skip_when: null,
    steps: [
      {
        title: "Frozen step",
        offset_minutes: 0,
        confirmation: "manual",
        completion_condition: null,
        skip_when: null,
        escalate_minutes: 15,
      },
    ],
  };
  const card = createMockCard({
    routines: {
      templates: [{ ...payload, revision: 3 }],
      presets: [],
      config: { modes: ["normal"], entity_allowlist: [], revision: 1 },
      runs: [],
    },
  });
  card._actionError = "storage_error";
  card._routineDraft = {
    type: "edit_template",
    id: payload.id,
    revision: payload.revision,
    title: payload.title,
    description: payload.description,
    enabled: payload.enabled,
    assignees: [...payload.assignees],
    rule: null,
    skip_when: null,
    steps: [
      {
        title: "Frozen step",
        raw_offset: "0",
        confirmation: "manual",
        raw_escalate: "15",
        skip_when: null,
        skip_dirty: false,
        completion_condition: null,
        completion_dirty: false,
      },
    ],
    frozenPayload: structuredClone(payload),
    operationId: "synthetic-frozen-retry-id",
  };
  const body = getConnectedContainer();
  renderRoutines(card, body);
  body
    .querySelector("form")
    .dispatchEvent(new dom.window.Event("submit", { cancelable: true }));
  assert.equal(card.commands.length, 1);
  assert.deepEqual(card.commands[0], { action: "routines.save", payload });
  assert.equal(card.lastOperationId, "synthetic-frozen-retry-id");
});

function beginTemplate(card, body) {
  renderRoutines(card, body);
  [...body.querySelectorAll("button")].find((button) => button.textContent === ROUTINES_COPY.en.new_template).click();
  card._routineDraft.title = "Synthetic repeat-safe routine";
  card._routineDraft.assignees = ["p1"];
  card._routineDraft.steps[0].title = "Synthetic step";
  renderRoutines(card, body);
}

test("template creation retry keeps its own operation after an intervening command", async () => {
  const card = createMockCard();
  const body = getConnectedContainer();
  beginTemplate(card, body);
  const calls = [];
  card.command = async (action, payload, operationId) => {
    calls.push({action, payload: structuredClone(payload), operationId});
    card._actionError = "storage_error";
  };
  body.querySelector("form").dispatchEvent(new dom.window.Event("submit", {cancelable: true}));
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(calls.length, 1);
  assert.equal(typeof calls[0].operationId, "string");
  assert.ok(calls[0].operationId.length > 10);
  card._pending = {fingerprint: "unrelated-command", id: "different-operation"};
  renderRoutines(card, body);
  body.querySelector("form").dispatchEvent(new dom.window.Event("submit", {cancelable: true}));
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(calls[1], calls[0]);
});

test("same-ID member epoch change revokes old form and forces focused refresh", () => {
  for (const target of ["p1", "c1"]) {
    const card = createMockCard();
    const body = getConnectedContainer();
    beginTemplate(card, body);
    const previous = structuredClone(card._data);
    card._data.members.find((member) => member.id === target).revision++;
    body.querySelector("form").dispatchEvent(new dom.window.Event("submit", {cancelable: true}));
    assert.equal(card.commands.length, 0);
    assert.equal(reconcileRoutineRefresh(card, previous), true);
    assert.equal(card._routineDraft, null);
    assert.equal(card._actionError, "conflict");
  }
});

test("10. Owner allowlist validation vs parent privileges and strict format rules", async () => {
  // Parent (not owner) has no allowlist editor
  const parentCard = createMockCard({ role: "parent" });
  const parentBody = getConnectedContainer();
  renderRoutines(parentCard, parentBody);
  assert.equal(parentBody.querySelector("textarea"), null);

  // Owner card has allowlist editor
  const ownerCard = createMockCard({ role: "owner" });
  const ownerBody = getConnectedContainer();
  renderRoutines(ownerCard, ownerBody);

  const editAllowBtn = Array.from(ownerBody.querySelectorAll("button")).find(
    (b) => b.textContent === ROUTINES_COPY.en.allowlist_edit
  );
  assert.ok(editAllowBtn);
  editAllowBtn.click();

  renderRoutines(ownerCard, ownerBody);
  const form = ownerBody.querySelector("form");
  const ta = form.querySelector("textarea");

  // Invalid uppercase entity
  ta.value = "Switch.Living_Room";
  ta.dispatchEvent(new dom.window.Event("input"));
  form.dispatchEvent(new dom.window.Event("submit", { cancelable: true }));
  assert.equal(ownerCard.commands.length, 0);
  assert.equal(ownerCard._actionError, ROUTINES_COPY.en.allowlist_invalid);

  // Duplicate entity
  ta.value = "switch.living_room\nswitch.living_room";
  ta.dispatchEvent(new dom.window.Event("input"));
  form.dispatchEvent(new dom.window.Event("submit", { cancelable: true }));
  assert.equal(ownerCard.commands.length, 0);
  assert.equal(ownerCard._actionError, ROUTINES_COPY.en.allowlist_duplicate);

  // Valid entity
  ta.value = "switch.living_room\nbinary_sensor.door";
  ta.dispatchEvent(new dom.window.Event("input"));
  form.dispatchEvent(new dom.window.Event("submit", { cancelable: true }));
  assert.equal(ownerCard.commands.length, 1);
  assert.equal(ownerCard.commands[0].action, "routines.configure");
  assert.deepEqual(ownerCard.commands[0].payload.entity_allowlist, [
    "switch.living_room",
    "binary_sensor.door",
  ]);
});

test("11. Child can only confirm own active step with nonce; Parent can reasoned override", async () => {
  const activeRun = {
    id: "run_c1",
    revision: 1,
    title: "Child Morning",
    member: "c1",
    status: "active",
    started_at: "2026-09-06T07:00:00Z",
    steps: [
      {
        title: "Brush Teeth",
        status: "active",
        confirmation: "manual",
        nonce: "secret_token_123",
      },
    ],
    history: [{ actor: "system", at: "2026-09-06T07:00:00Z", action: "step_activated", reason: "" }],
  };

  // 1. Child view: c1 sees confirm button for own active step
  const childCard = createMockCard({
    role: "child",
    actor: "c1",
    routines: {
      templates: [],
      presets: [],
      config: { modes: ["normal"], revision: 1 },
      runs: [activeRun],
    },
  });
  const childBody = getConnectedContainer();
  renderRoutines(childCard, childBody);

  const confirmBtn = Array.from(childBody.querySelectorAll("button")).find(
    (b) => b.textContent === ROUTINES_COPY.en.confirm_step
  );
  assert.ok(confirmBtn, "Child must see confirm step button for their own active step");
  confirmBtn.click();

  assert.equal(childCard.commands.length, 1);
  assert.deepEqual(childCard.commands[0], {
    action: "routines.confirm",
    payload: {
      id: "run_c1",
      revision: 1,
      step: 0,
      nonce: "secret_token_123",
    },
  });

  // 2. Parent view: Parent sees override button, enters reason, and overrides
  const parentCard = createMockCard({
    role: "parent",
    actor: "p1",
    routines: {
      templates: [],
      presets: [],
      config: { modes: ["normal"], revision: 1 },
      runs: [activeRun],
    },
  });
  const parentBody = getConnectedContainer();
  renderRoutines(parentCard, parentBody);

  const overrideBtn = Array.from(parentBody.querySelectorAll("button")).find(
    (b) => b.textContent === ROUTINES_COPY.en.parent_override
  );
  assert.ok(overrideBtn, "Parent must see override button");
  overrideBtn.click();

  renderRoutines(parentCard, parentBody);
  const overrideForm = parentBody.querySelector("form");
  const reasonInput = overrideForm.querySelector('input[name="reason"]');
  reasonInput.value = "Parent checked child brushed teeth";
  reasonInput.dispatchEvent(new dom.window.Event("input"));

  overrideForm.dispatchEvent(new dom.window.Event("submit", { cancelable: true }));
  assert.equal(parentCard.commands.length, 1);
  assert.deepEqual(parentCard.commands[0], {
    action: "routines.override",
    payload: {
      id: "run_c1",
      revision: 1,
      step: 0,
      outcome: "completed",
      reason: "Parent checked child brushed teeth",
    },
  });

  // Verify system actor localization in history
  assert.ok(parentBody.textContent.includes(ROUTINES_COPY.en.system_actor));
});
