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
const { RECIPES_COPY } = await import(
  "../custom_components/family_assistant/frontend/recipes-copy.js"
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

function candidate(overrides = {}) {
  return {
    source: { provider: "mealie", id: "recipe-1", slug: "winter-soup" },
    title: "<b>Winter soup</b>",
    source_servings: { value: null, display: "Not specified" },
    ingredients: [
      {
        display: "<i>1 cup broth</i>",
        name: "Broth",
        unit: "cup",
        quantity: 1,
        blockers: [],
      },
      {
        display: "Salt to taste",
        name: "Salt",
        unit: null,
        quantity: null,
        blockers: ["missing_unit", "missing_quantity", "manual_units"],
      },
    ],
    blockers: ["servings_required"],
    ...overrides,
  };
}

function stateFor(role = "parent") {
  const actor =
    role === "owner" ? "owner-1" : role === "parent" ? "parent-1" : "adult-1";
  return {
    revision: 1,
    actor,
    role,
    settings: { name: "Synthetic", modules: ["pantry", "shopping"] },
    members: [
      {
        id: "parent-1",
        name: "Parent",
        role: "parent",
        active: true,
        revision: 1,
      },
      {
        id: "owner-1",
        name: "Owner",
        role: "owner",
        active: true,
        revision: 1,
      },
      {
        id: "adult-1",
        name: "Adult",
        role: "adult",
        active: true,
        revision: 1,
      },
    ],
    recipe_source: { enabled: true, provider: "mealie", revision: "source-a" },
    pantry: {
      meal_plans: [],
      meal_shopping: [],
      dietary_profiles: { self: null, managed_children: [], shared_adults: [] },
    },
  };
}

async function setup(
  t,
  {
    role = "parent",
    recipe = candidate(),
    searchSlug = recipe.source.slug,
    totalPages = 1,
  } = {},
) {
  const state = stateFor(role);
  const lookups = [];
  const commands = [];
  const receipts = new Map();
  let loseAction = null;
  let getDeferred = null;
  const card = document.createElement("family-meals-card");
  card.setConfig({
    type: "custom:family-meals-card",
    entry_id: "synthetic",
    language: "en",
  });
  document.body.append(card);
  t.after(() => card.remove());

  const execute = (message) => {
    commands.push(clone(message));
    if (receipts.has(message.operation_id))
      return clone(receipts.get(message.operation_id));
    let receipt;
    if (message.action === "pantry.meal_save") {
      receipt = {
        id: "MP000001",
        revision: 1,
        status: "draft",
        ...clone(message.payload),
        history: [],
      };
      state.pantry.meal_plans.push(receipt);
    } else if (message.action === "pantry.stock_set") {
      receipt = { accepted: true };
    } else {
      throw { code: "unknown_action" };
    }
    receipts.set(message.operation_id, clone(receipt));
    state.revision += 1;
    if (loseAction === message.action) {
      loseAction = null;
      throw { code: "storage_error" };
    }
    return clone(receipt);
  };

  card.hass = {
    language: "en",
    callWS: async (message) => {
      if (message.type === "family_assistant/view") return clone(state);
      if (message.type === "family_assistant/execute") return execute(message);
      if (message.type === "family_assistant/recipes") {
        lookups.push(clone(message));
        if (message.kind === "search")
          return {
            source_revision: state.recipe_source.revision,
            page: message.page,
            total_pages: totalPages,
            items: [
              { id: "recipe-1", slug: searchSlug, name: "<img>Winter soup" },
            ],
          };
        if (getDeferred) return getDeferred.promise;
        return {
          source_revision: state.recipe_source.revision,
          candidate: clone(recipe),
        };
      }
      throw new Error(`unexpected WebSocket type: ${message.type}`);
    },
  };
  await eventually(() => Boolean(card._data) && !card._loading);
  return {
    card,
    state,
    lookups,
    commands,
    lose(action) {
      loseAction = action;
    },
    deferGet() {
      let resolve;
      const promise = new Promise((done) => {
        resolve = done;
      });
      getDeferred = { promise, resolve };
      return getDeferred;
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
  const result = card.shadowRoot.querySelector(`[data-recipes-form="${kind}"]`);
  assert.ok(result, `missing recipe form: ${kind}`);
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

async function openCandidate(fixture) {
  const search = form(fixture.card, "search");
  submit(search);
  await eventually(
    () => fixture.lookups.length === 1 && !fixture.card._recipesDraft?.loading,
  );
  const result = fixture.card.shadowRoot.querySelector("[data-recipe-slug]");
  assert.ok(result);
  button(result, RECIPES_COPY.en.use_recipe).click();
  await eventually(() => fixture.card._recipesDraft?.phase === "edit");
  return form(fixture.card, "edit");
}

function completeEditor(editor) {
  setField(editor, "week_start", "2026-09-07");
  setField(editor, "date", "2026-09-09");
  setField(editor, "slot", "dinner");
  setField(editor, "title", "Winter soup plan");
  setField(editor, "servings", "4");
  const blocked = editor.querySelector('[data-recipe-ingredient="1"]');
  setField(blocked, "unit", "tsp");
  setField(blocked, "quantity", "0.5");
  const verified = blocked.querySelector('input[type="checkbox"]');
  verified.checked = true;
  verified.dispatchEvent(new Event("change", { bubbles: true }));
}

test("real card gates optional recipes to current parents and never searches on render", async (t) => {
  for (const locale of Object.values(RECIPES_COPY))
    assert.deepEqual(
      Object.keys(locale).sort(),
      Object.keys(RECIPES_COPY.en).sort(),
    );
  const fixture = await setup(t);
  const before = clone(fixture.state);
  fixture.card.render();
  assert.deepEqual(fixture.state, before);
  assert.equal(fixture.lookups.length, 0);
  assert.equal(fixture.commands.length, 0);
  assert.ok(fixture.card.shadowRoot.querySelector(".recipes-section"));

  for (const change of [
    (state) => (state.role = "adult"),
    (state) => (state.settings.modules = ["shopping"]),
    (state) => (state.recipe_source.enabled = false),
    (state) => (state.recipe_source.provider = "other"),
  ]) {
    const hidden = await setup(t);
    change(hidden.state);
    await hidden.card.refresh();
    assert.equal(
      hidden.card.shadowRoot.querySelector(".recipes-section"),
      null,
    );
    assert.equal(hidden.lookups.length, 0);
  }
});

test("explicit empty browse and get render provider text inertly and require blocked-row repair", async (t) => {
  const fixture = await setup(t);
  let editor = await openCandidate(fixture);
  assert.deepEqual(fixture.lookups[0], {
    type: "family_assistant/recipes",
    entry_id: "synthetic",
    kind: "search",
    query: "",
    page: 1,
  });
  assert.equal(fixture.lookups[1].kind, "get");
  assert.equal(fixture.lookups[1].slug, "winter-soup");
  assert.equal("id" in fixture.lookups[1], false);
  assert.match(editor.textContent, /<b>Winter soup<\/b>/);
  assert.match(editor.textContent, /<i>1 cup broth<\/i>/);
  assert.equal(editor.querySelector("b b"), null);
  assert.equal(editor.querySelector("i"), null);
  assert.match(editor.textContent, /Changing servings never scales/);

  setField(editor, "servings", "4");
  assert.equal(
    editor.querySelector('[data-recipe-ingredient="0"] [name="quantity"]')
      .value,
    "1",
  );
  submit(editor);
  await tick();
  assert.equal(fixture.commands.length, 0);
  assert.equal(fixture.card._recipesDraft.phase, "edit");

  editor = form(fixture.card, "edit");
  completeEditor(editor);
  submit(editor);
  assert.equal(fixture.card._recipesDraft.phase, "review");
  const review = form(fixture.card, "review");
  assert.match(review.textContent, /Winter soup plan/);
  assert.match(review.textContent, /Broth: 1 cup/);
  assert.match(review.textContent, /Salt: 0.5 tsp/);
  assert.equal(fixture.commands.length, 0);
});

test("exact reviewed meal-save payload and operation survive committed loss and another command", async (t) => {
  const fixture = await setup(t);
  const editor = await openCandidate(fixture);
  completeEditor(editor);
  submit(editor);
  let review = form(fixture.card, "review");
  submit(review);
  await tick();
  assert.equal(fixture.commands.length, 0);
  review.elements.reviewed.checked = true;
  review.elements.reviewed.dispatchEvent(
    new Event("change", { bubbles: true }),
  );
  fixture.lose("pantry.meal_save");
  submit(review);
  await eventually(
    () =>
      fixture.commands.length === 1 &&
      fixture.card._actionError === "storage_error" &&
      Boolean(fixture.card._recipesDraft?.pending) &&
      !fixture.card._writing,
  );
  const first = fixture.commands[0];
  assert.deepEqual(first.payload, {
    week_start: "2026-09-07",
    title: "Winter soup plan",
    entries: [
      {
        date: "2026-09-09",
        slot: "dinner",
        title: "Winter soup plan",
        servings: 4,
        ingredients: [
          { name: "Broth", unit: "cup", quantity: 1 },
          { name: "Salt", unit: "tsp", quantity: 0.5 },
        ],
      },
    ],
    note: "",
  });
  assert.equal(JSON.stringify(first.payload).includes("mealie"), false);
  assert.equal(JSON.stringify(first.payload).includes("Source line"), false);
  assert.ok(Object.isFrozen(fixture.card._recipesDraft.payload));
  assert.ok(Object.isFrozen(fixture.card._recipesDraft.pending));
  const operationId = first.operation_id;

  await fixture.card.command(
    "pantry.stock_set",
    { id: "PI000001", revision: 1, quantity: 1, reason: "Unrelated" },
    "other-operation",
  );
  assert.equal(fixture.card._recipesDraft.pending.operation_id, operationId);
  review = form(fixture.card, "review");
  assert.match(review.textContent, /Winter soup plan/);
  submit(review);
  await eventually(
    () => fixture.commands.length === 3 && fixture.card._recipesDraft === null,
  );
  assert.deepEqual(fixture.commands[2].payload, first.payload);
  assert.equal(fixture.commands[2].operation_id, operationId);
  assert.equal(fixture.state.pantry.meal_plans.length, 1);
  assert.equal(fixture.state.pantry.meal_plans[0].status, "draft");
});

test("unknown blockers fail closed and explicit removal is required above twenty retained rows", async (t) => {
  const unknown = await setup(t, {
    recipe: candidate({ blockers: ["future_blocker"] }),
  });
  const search = form(unknown.card, "search");
  submit(search);
  await eventually(
    () => unknown.lookups.length === 1 && !unknown.card._recipesDraft.loading,
  );
  button(
    unknown.card.shadowRoot.querySelector("[data-recipe-slug]"),
    RECIPES_COPY.en.use_recipe,
  ).click();
  await eventually(() => !unknown.card._recipesDraft.loading);
  assert.equal(unknown.card._recipesDraft.phase, "search");
  assert.equal(unknown.card._recipesDraft.error, "provider_bad_response");
  assert.equal(unknown.commands.length, 0);

  const manyIngredients = Array.from({ length: 21 }, (_, index) => ({
    display: `Ingredient ${index + 1}`,
    name: `Ingredient ${index + 1}`,
    unit: "g",
    quantity: 1,
    blockers: [],
  }));
  const many = await setup(t, {
    recipe: candidate({
      source_servings: { value: 2, display: "2" },
      ingredients: manyIngredients,
      blockers: ["too_many_ingredients"],
    }),
  });
  let editor = await openCandidate(many);
  assert.equal(editor.querySelectorAll("[data-recipe-ingredient]").length, 21);
  assert.equal(
    [...editor.querySelectorAll("button")].some(
      (control) => control.textContent === RECIPES_COPY.en.add_ingredient,
    ),
    false,
  );
  button(
    editor.querySelector('[data-recipe-ingredient="20"]'),
    RECIPES_COPY.en.remove_ingredient,
  ).click();
  editor = form(many.card, "edit");
  assert.match(
    editor.querySelector('[data-recipe-ingredient="20"]').textContent,
    /Removed/,
  );
  assert.equal(many.commands.length, 0);
});

test("provider-compatible repeated-hyphen slugs and large page totals remain usable", async (t) => {
  const recipe = candidate({
    source: { provider: "mealie", id: "recipe-1", slug: "soup--winter" },
  });
  const fixture = await setup(t, {
    recipe,
    searchSlug: "soup--winter",
    totalPages: 2000,
  });
  const search = form(fixture.card, "search");
  submit(search);
  await eventually(() => fixture.card._recipesDraft?.search);
  assert.equal(fixture.card._recipesDraft.search.total_pages, 2000);
  assert.ok(button(fixture.card.shadowRoot, RECIPES_COPY.en.next));
  button(
    fixture.card.shadowRoot.querySelector('[data-recipe-slug="soup--winter"]'),
    RECIPES_COPY.en.use_recipe,
  ).click();
  await eventually(() => fixture.card._recipesDraft?.phase === "edit");
  assert.equal(fixture.lookups[1].slug, "soup--winter");
});

test("source, actor member, role, entry, generation, and detached controls revoke cached recipes", async (t) => {
  const changes = [
    [
      "source",
      (fixture) => (fixture.card._data.recipe_source.revision = "source-b"),
    ],
    [
      "member",
      (fixture) =>
        (fixture.card._data.members.find(
          (member) => member.id === "parent-1",
        ).revision = 2),
    ],
    ["role", (fixture) => (fixture.card._data.role = "adult")],
    [
      "module",
      (fixture) => (fixture.card._data.settings.modules = ["shopping"]),
    ],
    ["entry", (fixture) => (fixture.card._entry = "other")],
    ["generation", (fixture) => (fixture.card._generation += 1)],
  ];
  for (const [name, change] of changes) {
    const fixture = await setup(t);
    const editor = await openCandidate(fixture);
    change(fixture);
    setField(editor, "title", "Must not survive");
    await tick();
    assert.equal(fixture.card._recipesDraft, null, `${name} retained draft`);
    assert.equal(editor.isConnected, false, `${name} retained form`);
    assert.equal(fixture.commands.length, 0, `${name} reached transport`);
  }

  const delayed = await setup(t);
  const deferred = delayed.deferGet();
  const searchForm = form(delayed.card, "search");
  submit(searchForm);
  await eventually(
    () => delayed.lookups.length === 1 && !delayed.card._recipesDraft.loading,
  );
  const result = delayed.card.shadowRoot.querySelector("[data-recipe-slug]");
  button(result, RECIPES_COPY.en.use_recipe).click();
  await eventually(() => delayed.lookups.length === 2);
  delayed.state.recipe_source.enabled = false;
  await delayed.card.refresh();
  assert.equal(delayed.card._recipesDraft, null);
  deferred.resolve({ source_revision: "source-a", candidate: candidate() });
  await tick();
  await tick();
  assert.equal(delayed.card._recipesDraft, null);
  assert.equal(
    delayed.card.shadowRoot.textContent.includes("Salt to taste"),
    false,
  );
});

test("focused unchanged search survives refresh while provider revocation forces private DOM removal", async (t) => {
  const fixture = await setup(t);
  const search = form(fixture.card, "search");
  const query = setField(search, "query", "soup");
  query.focus();
  await fixture.card.refresh();
  assert.equal(fixture.card.shadowRoot.activeElement, query);
  assert.equal(query.isConnected, true);

  submit(search);
  await eventually(() => fixture.card._recipesDraft?.search);
  const privateResult =
    fixture.card.shadowRoot.querySelector("[data-recipe-slug]");
  const unrelated = document.createElement("form");
  const input = document.createElement("input");
  unrelated.append(input);
  fixture.card.shadowRoot.querySelector(".body").prepend(unrelated);
  input.focus();
  fixture.state.recipe_source.enabled = false;
  await fixture.card.refresh();
  assert.equal(privateResult.isConnected, false);
  assert.equal(input.isConnected, false);
  assert.equal(fixture.card._recipesDraft, null);
  assert.equal(
    fixture.card.shadowRoot.textContent.includes("<img>Winter soup"),
    false,
  );

  const reset = await setup(t);
  await openCandidate(reset);
  reset.card.setConfig({
    type: "custom:family-meals-card",
    entry_id: "next",
    language: "en",
  });
  assert.equal(reset.card._recipesDraft, null);
});
