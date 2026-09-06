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
const { DIETARY_COPY } = await import(
  "../custom_components/family_assistant/frontend/dietary-copy.js"
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

function activeProfile(memberId, options = {}) {
  return {
    member_id: memberId,
    status: "active",
    revision: options.revision ?? 1,
    can_edit: options.can_edit ?? true,
    can_share: options.can_share ?? false,
    likes: options.likes || ["Soup"],
    dislikes: options.dislikes || ["Olives"],
    avoid: options.avoid || ["Peanuts"],
    allergy_note: options.allergy_note ?? "Manual note",
    management: options.management || "self",
    share_with_parents: options.share_with_parents ?? false,
  };
}

function missingProfile(memberId, canEdit = true) {
  return {
    member_id: memberId,
    status: "missing",
    can_edit: canEdit,
    can_share: false,
  };
}

function stateFor(role = "adult") {
  const members = [
    { id: "adult-1", name: "Adult One", role: "adult", active: true, revision: 1 },
    { id: "parent-1", name: "Parent One", role: "parent", active: true, revision: 1 },
    { id: "child-1", name: "Child One", role: "child", active: true, revision: 1 },
    { id: "child-2", name: "Child Two", role: "child", active: true, revision: 1 },
    { id: "adult-2", name: "Adult Two", role: "adult", active: true, revision: 1 },
  ];
  const base = {
    revision: 1,
    actor: role === "parent" ? "parent-1" : role === "child" ? "child-1" : "adult-1",
    role,
    settings: {
      name: "Synthetic household",
      modules: ["pantry", "shopping"],
    },
    members,
    pantry: {
      meal_plans: [],
      meal_shopping: [],
      dietary_profiles: {
        self: null,
        managed_children: [],
        shared_adults: [],
      },
    },
  };
  if (role === "parent") {
    base.pantry.dietary_profiles.self = activeProfile("parent-1", {
      can_share: true,
      likes: ["Tea"],
      avoid: [],
      allergy_note: "",
    });
    base.pantry.dietary_profiles.managed_children = [
      activeProfile("child-1", {
        can_share: false,
        management: "parent_child",
        allergy_note: "Child note",
      }),
      missingProfile("child-2"),
    ];
    base.pantry.dietary_profiles.shared_adults = [
      activeProfile("adult-2", {
        can_edit: false,
        can_share: false,
        share_with_parents: true,
        likes: ["Pasta"],
        dislikes: [],
        avoid: ["Sesame"],
        allergy_note: "Shared manual note",
      }),
    ];
  } else if (role === "child") {
    base.pantry.dietary_profiles.self = activeProfile("child-1", {
      can_edit: false,
      can_share: false,
      management: "parent_child",
      allergy_note: "Child note",
    });
  } else if (role === "guest") {
    base.pantry.dietary_profiles = {
      self: null,
      managed_children: [],
      shared_adults: [],
    };
  } else {
    base.pantry.dietary_profiles.self = activeProfile("adult-1", {
      can_share: true,
    });
  }
  return base;
}

function locate(state, memberId) {
  const profiles = state.pantry.dietary_profiles;
  if (profiles.self?.member_id === memberId)
    return { collection: "self", index: null, row: profiles.self };
  for (const collection of ["managed_children", "shared_adults"]) {
    const index = profiles[collection].findIndex(
      (row) => row.member_id === memberId,
    );
    if (index >= 0)
      return { collection, index, row: profiles[collection][index] };
  }
  return null;
}

function replaceLocated(state, location, row) {
  if (location.collection === "self")
    state.pantry.dietary_profiles.self = row;
  else state.pantry.dietary_profiles[location.collection][location.index] = row;
}

async function setup(t, { role = "adult", language = "en" } = {}) {
  const state = stateFor(role);
  const calls = [];
  const receipts = new Map();
  const lostActions = new Set();
  const failedBeforeActions = new Set();
  const card = document.createElement("family-meals-card");
  card.setConfig({
    type: "custom:family-meals-card",
    entry_id: "synthetic",
    language,
  });
  document.body.append(card);
  t.after(() => card.remove());

  const execute = (message) => {
    calls.push(clone(message));
    if (receipts.has(message.operation_id))
      return clone(receipts.get(message.operation_id));
    if (failedBeforeActions.delete(message.action))
      throw { code: "storage_error" };
    let result;
    if (message.action === "pantry.dietary_save") {
      const location = locate(state, message.payload.member_id);
      if (!location) throw { code: "conflict" };
      const row = location.row;
      if (
        (row.revision === undefined) !== (message.payload.revision === undefined) ||
        (row.revision !== undefined && row.revision !== message.payload.revision)
      )
        throw { code: "conflict" };
      result = {
        member_id: row.member_id,
        status: "active",
        revision: (row.revision || 0) + 1,
        can_edit: true,
        can_share: location.collection === "self" && state.role !== "child",
        likes: clone(message.payload.likes),
        dislikes: clone(message.payload.dislikes),
        avoid: clone(message.payload.avoid),
        allergy_note: message.payload.allergy_note,
        management:
          location.collection === "managed_children" ? "parent_child" : "self",
        share_with_parents: row.share_with_parents === true,
      };
      replaceLocated(state, location, result);
    } else if (message.action === "pantry.dietary_access_set") {
      const location = locate(state, message.payload.member_id);
      const member = state.members.find(
        (candidate) => candidate.id === message.payload.member_id,
      );
      if (
        !location ||
        location.collection !== "self" ||
        location.row.revision !== message.payload.revision ||
        !Number.isSafeInteger(message.payload.member_revision) ||
        message.payload.member_revision < 1 ||
        member?.revision !== message.payload.member_revision
      )
        throw { code: "conflict" };
      location.row.revision += 1;
      location.row.management = "self";
      location.row.share_with_parents = message.payload.share_with_parents;
      result = location.row;
    } else if (message.action === "pantry.dietary_clear") {
      const location = locate(state, message.payload.member_id);
      if (!location || location.row.revision !== message.payload.revision)
        throw { code: "conflict" };
      result = {
        member_id: location.row.member_id,
        status: "cleared",
        revision: location.row.revision + 1,
        can_edit: true,
        can_share: false,
      };
      replaceLocated(state, location, result);
    } else if (message.action === "pantry.stock_set") {
      result = { accepted: true };
    } else {
      throw { code: "unknown_action" };
    }
    state.revision += 1;
    const receipt = clone(result);
    receipts.set(message.operation_id, receipt);
    if (lostActions.delete(message.action)) throw { code: "storage_error" };
    return clone(receipt);
  };

  card.hass = {
    language,
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
      lostActions.add(action);
    },
    failBefore(action) {
      failedBeforeActions.add(action);
    },
  };
}

function profileElement(card, memberId) {
  const result = [...card.shadowRoot.querySelectorAll("[data-dietary-member]")].find(
    (row) => row.dataset.dietaryMember === memberId,
  );
  assert.ok(result, `missing profile row: ${memberId}`);
  return result;
}

function button(root, label) {
  const result = [...root.querySelectorAll("button")].find(
    (candidate) => candidate.textContent === label,
  );
  assert.ok(result, `missing button: ${label}`);
  return result;
}

function form(card, kind) {
  const result = card.shadowRoot.querySelector(`[data-dietary-form="${kind}"]`);
  assert.ok(result, `missing dietary form: ${kind}`);
  return result;
}

function setField(root, name, value) {
  const field = root.querySelector(`[name="${name}"]`);
  assert.ok(field, `missing field: ${name}`);
  field.value = value;
  field.dispatchEvent(new Event("input", { bubbles: true }));
  return field;
}

function submit(target) {
  target.dispatchEvent(
    new Event("submit", { bubbles: true, cancelable: true }),
  );
}

test("real card renders only projected self, managed child, and consented adult capabilities", async (t) => {
  for (const locale of Object.values(DIETARY_COPY))
    assert.deepEqual(
      Object.keys(locale).sort(),
      Object.keys(DIETARY_COPY.en).sort(),
    );
  const parent = await setup(t, { role: "parent" });
  const beforeRender = clone(parent.state);
  parent.card.render();
  assert.deepEqual(parent.state, beforeRender);
  const child = profileElement(parent.card, "child-1");
  assert.match(child.textContent, /Child One/);
  assert.ok(button(child, DIETARY_COPY.en.edit));
  const missingChild = profileElement(parent.card, "child-2");
  assert.match(missingChild.textContent, /No profile recorded/);
  assert.ok(button(missingChild, DIETARY_COPY.en.edit));
  const shared = profileElement(parent.card, "adult-2");
  assert.match(shared.textContent, /Adult Two/);
  assert.match(shared.textContent, /Shared manual note/);
  assert.match(shared.textContent, /Read-only/);
  assert.equal(shared.querySelector("button"), null);
  assert.equal(parent.calls.length, 0);

  const childView = await setup(t, { role: "child" });
  const own = profileElement(childView.card, "child-1");
  assert.match(own.textContent, /Read-only/);
  assert.equal(own.querySelector("button"), null);
  assert.equal(childView.card.shadowRoot.textContent.includes("Adult Two"), false);

  const guest = await setup(t, { role: "guest" });
  assert.equal(guest.card.shadowRoot.querySelector(".dietary-section"), null);
  assert.equal(guest.calls.length, 0);
});

test("real whole-save review is frozen, named, exact, and retries across another command", async (t) => {
  const fixture = await setup(t);
  const { card, state, calls } = fixture;
  button(profileElement(card, "adult-1"), DIETARY_COPY.en.edit).click();
  let editor = form(card, "edit");
  setField(editor, "likes", " Soup \nTea");
  setField(editor, "dislikes", "Olives");
  setField(editor, "avoid", "Peanuts");
  setField(editor, "allergy_note", "  <b>Manual note</b>  ");
  submit(editor);
  assert.equal(calls.length, 0);

  let review = form(card, "save");
  assert.match(review.textContent, /Adult One/);
  for (const value of ["Likes", "Dislikes", "Avoid", "Allergy note", "Soup", "Tea", "Peanuts", "<b>Manual note<\/b>"])
    assert.ok(review.textContent.includes(value), value);
  assert.equal(review.querySelector("b"), null);
  assert.ok(Object.isFrozen(card._dietaryDraft.payload));
  assert.ok(Object.isFrozen(card._dietaryDraft.payload.likes));
  const checkbox = review.elements.reviewed;
  assert.equal(checkbox.type, "checkbox");
  submit(review);
  await tick();
  assert.equal(calls.length, 0);

  checkbox.checked = true;
  checkbox.dispatchEvent(new Event("change", { bubbles: true }));
  fixture.lose("pantry.dietary_save");
  submit(review);
  await eventually(
    () =>
      calls.length === 1 &&
      card._actionError === "storage_error" &&
      Boolean(card._dietaryDraft?.pending) &&
      !card._writing,
  );
  const first = calls[0];
  const operationId = card._dietaryDraft.pending.operation_id;
  assert.equal(first.operation_id, operationId);
  assert.deepEqual(first.payload, {
    member_id: "adult-1",
    revision: 1,
    likes: ["Soup", "Tea"],
    dislikes: ["Olives"],
    avoid: ["Peanuts"],
    allergy_note: "<b>Manual note</b>",
  });
  assert.equal(state.pantry.dietary_profiles.self.revision, 2);

  state.members.find((member) => member.id === "adult-1").name = "Later name";
  await card.refresh();
  assert.match(form(card, "save").textContent, /Adult One/);
  assert.doesNotMatch(form(card, "save").textContent, /Later name/);
  await card.command("pantry.stock_set", {
    id: "PI000001",
    revision: 1,
    quantity: 1,
    reason: "Unrelated count",
  });
  assert.equal(calls.length, 2);
  assert.notEqual(calls[1].operation_id, operationId);
  assert.equal(card._dietaryDraft.pending.operation_id, operationId);
  assert.match(form(card, "save").textContent, /Adult One/);

  submit(form(card, "save"));
  await eventually(() => calls.length === 3 && card._dietaryDraft === null);
  assert.deepEqual(calls[2].payload, first.payload);
  assert.equal(calls[2].operation_id, first.operation_id);
  assert.equal(state.pantry.dietary_profiles.self.revision, 2);
  assert.equal(card.shadowRoot.querySelector("[data-dietary-form]"), null);
});

test("cross-list duplicate labels are rejected locally without losing the editor", async (t) => {
  const { card, calls } = await setup(t);
  button(profileElement(card, "adult-1"), DIETARY_COPY.en.edit).click();
  const editor = form(card, "edit");
  setField(editor, "likes", "Same");
  setField(editor, "dislikes", "");
  setField(editor, "avoid", " same ");
  submit(editor);
  await tick();
  assert.equal(calls.length, 0);
  assert.equal(card._actionError, "invalid_field");
  assert.equal(card._dietaryDraft.kind, "edit");
  assert.equal(form(card, "edit").elements.likes.value, "Same");
  assert.equal(form(card, "edit").elements.avoid.value, " same ");
});

test("real adult sharing and revocation require frozen explicit confirmation", async (t) => {
  const { card, state, calls } = await setup(t);
  button(profileElement(card, "adult-1"), DIETARY_COPY.en.share).click();
  let review = form(card, "access");
  assert.equal(
    card.shadowRoot.querySelectorAll("[data-dietary-member]").length,
    0,
  );
  assert.match(review.textContent, /Adult One/);
  assert.ok(Object.isFrozen(card._dietaryDraft.payload));
  assert.deepEqual(card._dietaryDraft.payload, {
    member_id: "adult-1",
    revision: 1,
    member_revision: 1,
    share_with_parents: true,
  });
  submit(review);
  await tick();
  assert.equal(calls.length, 0);
  review.elements.reviewed.checked = true;
  review.elements.reviewed.dispatchEvent(new Event("change", { bubbles: true }));
  submit(review);
  await eventually(() => calls.length === 1 && card._dietaryDraft === null);
  assert.equal(state.pantry.dietary_profiles.self.share_with_parents, true);

  button(profileElement(card, "adult-1"), DIETARY_COPY.en.stop_sharing).click();
  review = form(card, "access");
  assert.match(review.textContent, /removed from parents/);
  assert.ok(Object.isFrozen(card._dietaryDraft.payload));
  assert.deepEqual(card._dietaryDraft.payload, {
    member_id: "adult-1",
    revision: 2,
    member_revision: 1,
    share_with_parents: false,
  });
  review.elements.reviewed.checked = true;
  review.elements.reviewed.dispatchEvent(new Event("change", { bubbles: true }));
  submit(review);
  await eventually(() => calls.length === 2 && card._dietaryDraft === null);
  assert.equal(state.pantry.dietary_profiles.self.share_with_parents, false);
  assert.equal(calls[1].action, "pantry.dietary_access_set");
});

test("access retry is discarded when the frozen subject member revision advances", async (t) => {
  const fixture = await setup(t);
  const { card, state, calls } = fixture;
  button(profileElement(card, "adult-1"), DIETARY_COPY.en.share).click();
  const review = form(card, "access");
  review.elements.reviewed.checked = true;
  review.elements.reviewed.dispatchEvent(new Event("change", { bubbles: true }));
  fixture.failBefore("pantry.dietary_access_set");
  submit(review);
  await eventually(
    () =>
      calls.length === 1 &&
      card._actionError === "storage_error" &&
      Boolean(card._dietaryDraft?.pending) &&
      !card._writing,
  );
  assert.equal(calls[0].payload.member_revision, 1);
  const operationId = card._dietaryDraft.pending.operation_id;
  assert.equal(calls[0].operation_id, operationId);

  state.members.find((member) => member.id === "adult-1").revision = 2;
  await card.refresh();
  assert.equal(card._dietaryDraft, null);
  assert.equal(review.isConnected, false);
  submit(review);
  await tick();
  assert.equal(calls.length, 1);
});

test("parent consent revocation removes the shared row and child clear leaves a tombstone", async (t) => {
  const fixture = await setup(t, { role: "parent" });
  const { card, state, calls } = fixture;
  assert.match(profileElement(card, "adult-2").textContent, /Shared manual note/);
  state.pantry.dietary_profiles.shared_adults = [];
  await card.refresh();
  assert.equal(card.shadowRoot.textContent.includes("Adult Two"), false);
  assert.equal(card.shadowRoot.textContent.includes("Shared manual note"), false);

  const child = profileElement(card, "child-1");
  button(child, DIETARY_COPY.en.clear).click();
  const review = form(card, "clear");
  assert.match(review.textContent, /Child One/);
  assert.match(review.textContent, /leaves a cleared record/);
  submit(review);
  await tick();
  assert.equal(calls.length, 0);
  review.elements.reviewed.checked = true;
  review.elements.reviewed.dispatchEvent(new Event("change", { bubbles: true }));
  submit(review);
  await eventually(() => calls.length === 1 && card._dietaryDraft === null);
  assert.deepEqual(calls[0].payload, {
    member_id: "child-1",
    revision: 1,
  });
  const cleared = profileElement(card, "child-1");
  assert.match(cleared.textContent, /Profile content cleared/);
  assert.equal(cleared.textContent.includes("Child note"), false);
  assert.equal(cleared.textContent.includes("Peanuts"), false);
  assert.ok(button(cleared, DIETARY_COPY.en.edit));
  assert.equal(
    [...cleared.querySelectorAll("button")].some(
      (candidate) => candidate.textContent === DIETARY_COPY.en.clear,
    ),
    false,
  );
});

test("real refresh preserves unchanged focus but forces revoked private projection out of the DOM", async (t) => {
  const fixture = await setup(t, { role: "parent" });
  const { card, state } = fixture;
  button(profileElement(card, "parent-1"), DIETARY_COPY.en.edit).click();
  let editor = form(card, "edit");
  const likes = editor.elements.likes;
  likes.focus();
  await card.refresh();
  assert.equal(card.shadowRoot.activeElement, likes);
  assert.equal(likes.isConnected, true);

  state.pantry.dietary_profiles.shared_adults = [];
  await card.refresh();
  assert.equal(likes.isConnected, false);
  assert.equal(card.shadowRoot.textContent.includes("Shared manual note"), false);
  assert.ok(card._dietaryDraft);
  assert.equal(form(card, "edit").elements.likes.value, "Tea");

  card._dietaryDraft = null;
  card.render();
  const host = card.shadowRoot.querySelector(".body");
  const unrelated = document.createElement("form");
  const unrelatedInput = document.createElement("input");
  unrelated.append(unrelatedInput);
  host.prepend(unrelated);
  unrelatedInput.focus();
  state.pantry.dietary_profiles.self = null;
  await card.refresh();
  assert.equal(unrelatedInput.isConnected, false);
  assert.equal(card.shadowRoot.textContent.includes("Tea"), false);
});

test("real stale scopes and source revisions clear focused private forms before transport", async (t) => {
  const changes = [
    ["actor", (card) => (card._data.actor = "other")],
    ["role", (card) => (card._data.role = "child")],
    ["module", (card) => (card._data.settings.modules = ["shopping"])],
    ["entry", (card) => (card._entry = "other-entry")],
    ["generation", (card) => (card._generation += 1)],
    [
      "revision",
      (card) => (card._data.pantry.dietary_profiles.self.revision += 1),
    ],
    [
      "member revision",
      (card) =>
        (card._data.members.find((member) => member.id === "adult-1").revision +=
          1),
    ],
  ];
  for (const [name, change] of changes) {
    const { card, calls } = await setup(t);
    button(profileElement(card, "adult-1"), DIETARY_COPY.en.edit).click();
    const editor = form(card, "edit");
    change(card);
    setField(editor, "likes", "Must not survive");
    await tick();
    assert.equal(calls.length, 0, `${name} reached transport`);
    assert.equal(card._dietaryDraft, null, `${name} retained a private draft`);
    assert.equal(editor.isConnected, false, `${name} retained the old form`);
  }
});

test("focused role flip and detached real forms cannot retain or submit broadened data", async (t) => {
  const flipped = await setup(t);
  button(profileElement(flipped.card, "adult-1"), DIETARY_COPY.en.edit).click();
  let editor = form(flipped.card, "edit");
  const likes = editor.elements.likes;
  likes.focus();
  flipped.state.role = "child";
  flipped.state.actor = "child-1";
  flipped.state.pantry.dietary_profiles = stateFor("child").pantry.dietary_profiles;
  await flipped.card.refresh();
  assert.equal(likes.isConnected, false);
  likes.value = "Old adult draft";
  likes.dispatchEvent(new Event("input", { bubbles: true }));
  assert.equal(flipped.card._dietaryDraft, null);
  assert.equal(editor.isConnected, false);
  assert.equal(flipped.calls.length, 0);
  const child = profileElement(flipped.card, "child-1");
  assert.equal(child.querySelector("button"), null);

  const detached = await setup(t);
  button(profileElement(detached.card, "adult-1"), DIETARY_COPY.en.edit).click();
  editor = form(detached.card, "edit");
  const draft = detached.card._dietaryDraft;
  detached.card.render();
  assert.equal(editor.isConnected, false);
  submit(editor);
  await tick();
  assert.equal(detached.calls.length, 0);
  assert.equal(detached.card._dietaryDraft, draft);

  const resetForm = form(detached.card, "edit");
  detached.card.setConfig({
    type: "custom:family-meals-card",
    entry_id: "next-entry",
    language: "en",
  });
  assert.equal(detached.card._dietaryDraft, null);
  submit(resetForm);
  await tick();
  assert.equal(detached.calls.length, 0);
});
