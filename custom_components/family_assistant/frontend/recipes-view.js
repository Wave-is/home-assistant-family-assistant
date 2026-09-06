/* Explicit Mealie lookup and manual conversion into one new meal-plan draft. */

import { RECIPES_COPY } from "./recipes-copy.js";

const PARENTS = new Set(["owner", "parent"]);
const SLOTS = ["breakfast", "lunch", "dinner", "snack"];
const CANDIDATE_BLOCKERS = new Set([
  "servings_required",
  "too_many_ingredients",
]);
const ROW_BLOCKERS = new Set([
  "missing_name",
  "missing_unit",
  "missing_quantity",
  "invalid_quantity",
  "unsupported_reference",
  "manual_units",
]);
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const QUANTITY = /^(?:0|[1-9]\d*)(?:\.\d{1,3})?$/;

const node = (tag, value, className) => {
  const result = document.createElement(tag);
  if (value !== undefined && value !== null) result.textContent = String(value);
  if (className) result.className = className;
  return result;
};
const clone = (value) => JSON.parse(JSON.stringify(value));
const deepFreeze = (value) => {
  if (!value || typeof value !== "object" || Object.isFrozen(value))
    return value;
  Object.freeze(value);
  for (const child of Object.values(value)) deepFreeze(child);
  return value;
};
const copyOf = (card) => {
  const language = card._config?.language || card._hass?.language || "en";
  return RECIPES_COPY[language.split("-")[0]] || RECIPES_COPY.en;
};
const text = (copy, key, fallback) => copy[key] || fallback;

const LOCAL_STYLE = `
  .recipes-section{margin-top:16px}.recipes-content,.recipe-form,.recipe-results{display:grid;gap:12px;padding-top:12px}
  .recipe-result,.recipe-ingredient,.recipe-review{min-width:0}.recipe-ingredient{display:block}.recipe-ingredient>*+*{margin-top:10px}.recipe-ingredient>button{width:auto}
  .recipe-toolbar{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
  .recipe-toolbar .grow{flex:1}.recipe-ingredients{display:grid;gap:10px}.recipe-ingredient.removed{opacity:.72}
  .recipe-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.recipe-fields .wide{grid-column:1/-1}
  .recipe-ingredient-fields{display:grid;grid-template-columns:minmax(0,2fr) minmax(0,1fr) minmax(0,1fr);gap:8px}
  .recipe-blockers{margin:6px 0;padding-inline-start:20px}.recipe-review ul{margin:6px 0;padding-inline-start:20px}
  @media(max-width:520px){.recipe-fields,.recipe-ingredient-fields{grid-template-columns:minmax(0,1fr)}.recipe-fields .wide{grid-column:auto}}
`;

function validRevision(value) {
  return Number.isSafeInteger(value) && value >= 1;
}

function recipeSource(data) {
  const source = data?.recipe_source;
  if (
    !source ||
    source.enabled !== true ||
    source.provider !== "mealie" ||
    typeof source.revision !== "string" ||
    !source.revision
  )
    return null;
  return source;
}

function actorMember(data) {
  return (data?.members || []).find((member) => member.id === data?.actor);
}

function accessOf(card) {
  const data = card?._data;
  const member = actorMember(data);
  const source = recipeSource(data);
  if (
    !data?.actor ||
    !PARENTS.has(data?.role) ||
    member?.active !== true ||
    member?.role !== data.role ||
    !validRevision(member?.revision) ||
    !data?.settings?.modules?.includes("pantry") ||
    !source
  )
    return null;
  return {
    generation: card._generation,
    entry: card._entry,
    actor: data.actor,
    role: data.role,
    memberRevision: member.revision,
    provider: source.provider,
    sourceRevision: source.revision,
  };
}

function accessKey(access) {
  return access ? JSON.stringify(Object.values(access)) : "";
}

function sameAccess(card, expected) {
  return Boolean(expected) && accessKey(accessOf(card)) === accessKey(expected);
}

function refreshProjection(data) {
  const member = actorMember(data);
  return {
    actor: data?.actor ?? null,
    role: data?.role ?? null,
    pantry: Boolean(data?.settings?.modules?.includes("pantry")),
    source: data?.recipe_source ?? null,
    member: member
      ? {
          id: member.id,
          name: member.name,
          role: member.role,
          active: member.active,
          revision: member.revision,
        }
      : null,
  };
}

export function reconcileRecipesRefresh(card, previousData) {
  if (!card) return false;
  const projectionChanged =
    JSON.stringify(refreshProjection(previousData)) !==
    JSON.stringify(refreshProjection(card._data));
  let forceRender =
    projectionChanged &&
    Boolean(
      card._recipesDraft || card.shadowRoot?.querySelector(".recipes-section"),
    );
  if (card._recipesDraft && !sameAccess(card, card._recipesDraft.access)) {
    card._recipesDraft = null;
    card._actionError = "conflict";
    forceRender = true;
  }
  return forceRender;
}

function rawText(value, key, maximum, required = true) {
  if (typeof value !== "string" || value.length > maximum) throw new Error(key);
  const result = value.trim();
  if (required && !result) throw new Error(key);
  return result;
}

function dateValue(value, key) {
  if (typeof value !== "string" || !ISO_DATE.test(value)) throw new Error(key);
  const [year, month, day] = value.split("-").map(Number);
  if (year < 1 || year > 9999 || month < 1 || month > 12 || day < 1 || day > 31)
    throw new Error(key);
  const parsed = new Date(`${value}T00:00:00Z`);
  if (
    Number.isNaN(parsed.valueOf()) ||
    parsed.getUTCFullYear() !== year ||
    parsed.getUTCMonth() + 1 !== month ||
    parsed.getUTCDate() !== day
  )
    throw new Error(key);
  return value;
}

function monday(value) {
  const result = dateValue(value, "week_start");
  const parsed = new Date(`${result}T00:00:00Z`);
  if (
    parsed.getUTCDay() !== 1 ||
    new Date(parsed.valueOf() + 6 * 86400000).getUTCFullYear() > 9999
  )
    throw new Error("week_start");
  return result;
}

function dateWithinWeek(value, week) {
  const result = dateValue(value, "date");
  const offset =
    (new Date(`${result}T00:00:00Z`) - new Date(`${week}T00:00:00Z`)) /
    86400000;
  if (!Number.isInteger(offset) || offset < 0 || offset > 6)
    throw new Error("date");
  return result;
}

function integer(value, key, low, high) {
  const raw = String(value ?? "").trim();
  if (!/^(?:[1-9]|[1-4]\d|50)$/.test(raw)) throw new Error(key);
  const result = Number(raw);
  if (!Number.isSafeInteger(result) || result < low || result > high)
    throw new Error(key);
  return result;
}

function quantity(value) {
  const raw = String(value ?? "").trim();
  if (!QUANTITY.test(raw)) throw new Error("quantity");
  const result = Number(raw);
  if (!Number.isFinite(result) || result <= 0 || result > 1_000_000)
    throw new Error("quantity");
  return result;
}

function knownBlockers(value, allowed) {
  if (!Array.isArray(value)) throw new Error("provider_bad_response");
  const seen = new Set();
  for (const blocker of value) {
    if (
      typeof blocker !== "string" ||
      !allowed.has(blocker) ||
      seen.has(blocker)
    )
      throw new Error("provider_bad_response");
    seen.add(blocker);
  }
  return [...value];
}

function validSlug(value) {
  if (
    typeof value !== "string" ||
    value.length > 250 ||
    !/^[a-z0-9](?:[a-z0-9-]{0,248}[a-z0-9])?$/.test(value)
  )
    throw new Error("provider_bad_response");
  return value;
}

function validateSearchResponse(raw, sourceRevision, requestedPage) {
  if (!raw || typeof raw !== "object" || raw.source_revision !== sourceRevision)
    throw new Error("source_changed");
  if (
    !Number.isSafeInteger(raw.page) ||
    raw.page !== requestedPage ||
    !Number.isSafeInteger(raw.total_pages) ||
    raw.total_pages < 0 ||
    raw.total_pages > Number.MAX_SAFE_INTEGER ||
    !Array.isArray(raw.items) ||
    raw.items.length > 10
  )
    throw new Error("provider_bad_response");
  const items = raw.items.map((item) => {
    if (!item || typeof item !== "object")
      throw new Error("provider_bad_response");
    const id = item.id;
    if (!(typeof id === "string" && id.length > 0 && id.length <= 128))
      throw new Error("provider_bad_response");
    return {
      id,
      slug: validSlug(item.slug),
      name: rawText(item.name, "provider_bad_response", 120),
    };
  });
  return deepFreeze({ page: raw.page, total_pages: raw.total_pages, items });
}

function nullableCanonical(value, maximum) {
  if (value === null) return null;
  return rawText(value, "provider_bad_response", maximum);
}

function validateCandidateResponse(raw, sourceRevision, requestedSlug) {
  if (!raw || typeof raw !== "object" || raw.source_revision !== sourceRevision)
    throw new Error("source_changed");
  const candidate = raw.candidate;
  if (!candidate || typeof candidate !== "object")
    throw new Error("provider_bad_response");
  const source = candidate.source;
  if (
    !source ||
    source.provider !== "mealie" ||
    validSlug(source.slug) !== requestedSlug ||
    !(
      typeof source.id === "string" &&
      source.id.length > 0 &&
      source.id.length <= 128
    )
  )
    throw new Error("provider_bad_response");
  const sourceServings = candidate.source_servings;
  if (
    !sourceServings ||
    typeof sourceServings !== "object" ||
    !(
      sourceServings.value === null ||
      Number.isSafeInteger(sourceServings.value)
    )
  )
    throw new Error("provider_bad_response");
  const ingredients = candidate.ingredients;
  if (!Array.isArray(ingredients) || ingredients.length > 100)
    throw new Error("provider_bad_response");
  const result = {
    source: {
      provider: "mealie",
      id: source.id,
      slug: requestedSlug,
    },
    title: rawText(candidate.title, "provider_bad_response", 120),
    source_servings: {
      value: sourceServings.value,
      display: rawText(
        sourceServings.display,
        "provider_bad_response",
        120,
        false,
      ),
    },
    blockers: knownBlockers(candidate.blockers, CANDIDATE_BLOCKERS),
    ingredients: ingredients.map((ingredient) => {
      if (
        !ingredient ||
        typeof ingredient !== "object" ||
        typeof ingredient.display !== "string" ||
        ingredient.display.length > 500 ||
        !(
          ingredient.quantity === null ||
          (typeof ingredient.quantity === "number" &&
            Number.isFinite(ingredient.quantity))
        )
      )
        throw new Error("provider_bad_response");
      return {
        display: ingredient.display,
        name: nullableCanonical(ingredient.name, 120),
        unit: nullableCanonical(ingredient.unit, 24),
        quantity: ingredient.quantity,
        blockers: knownBlockers(ingredient.blockers, ROW_BLOCKERS),
      };
    }),
  };
  return deepFreeze(result);
}

function manualValues(candidate) {
  const suggestedServings = candidate.source_servings.value;
  return {
    week_start: "",
    date: "",
    slot: "",
    title: candidate.title,
    servings:
      Number.isSafeInteger(suggestedServings) &&
      suggestedServings >= 1 &&
      suggestedServings <= 50
        ? String(suggestedServings)
        : "",
    ingredients: candidate.ingredients.map((ingredient) => ({
      display: ingredient.display,
      name: ingredient.name ?? "",
      unit: ingredient.unit ?? "",
      quantity: ingredient.quantity === null ? "" : String(ingredient.quantity),
      blockers: [...ingredient.blockers],
      verified: false,
      removed: false,
      added: false,
    })),
  };
}

function mealPayload(values) {
  const week = monday(values.week_start);
  const title = rawText(values.title, "title", 120);
  const retained = values.ingredients.filter(
    (ingredient) => !ingredient.removed,
  );
  if (retained.length > 20) throw new Error("ingredients");
  const ingredients = retained.map((ingredient) => {
    if (ingredient.blockers.length && ingredient.verified !== true)
      throw new Error("ingredients");
    return {
      name: rawText(ingredient.name, "name", 120),
      unit: rawText(ingredient.unit, "unit", 24),
      quantity: quantity(ingredient.quantity),
    };
  });
  return {
    week_start: week,
    title,
    entries: [
      {
        date: dateWithinWeek(values.date, week),
        slot: SLOTS.includes(values.slot)
          ? values.slot
          : (() => {
              throw new Error("slot");
            })(),
        title,
        servings: integer(values.servings, "servings", 1, 50),
        ingredients,
      },
    ],
    note: "",
  };
}

function field(parent, labelText, name, value, type = "text") {
  const label = node("label", labelText);
  const input = document.createElement("input");
  input.name = name;
  input.type = type;
  input.value = value ?? "";
  label.append(input);
  parent.append(label);
  return input;
}

function appendBlockers(parent, blockers, copy) {
  if (!blockers.length) return;
  const list = node("ul", null, "recipe-blockers");
  for (const blocker of blockers)
    list.append(
      node("li", text(copy, `blocker_${blocker}`, copy.provider_bad_response)),
    );
  parent.append(list);
}

function appendReview(form, draft, copy) {
  const payload = draft.payload;
  const entry = payload.entries[0];
  form.append(
    node("h3", text(copy, "review_title", "Review new meal-plan draft")),
    node("p", draft.candidate.title, "sub"),
    node(
      "p",
      text(copy, "review_hint", "This creates one new draft only."),
      "sub",
    ),
  );
  const summary = node("div", null, "recipe-review");
  for (const [label, value] of [
    [copy.week_start, payload.week_start],
    [copy.date, entry.date],
    [copy.slot, text(copy, entry.slot, entry.slot)],
    [copy.plan_title, payload.title],
    [copy.servings, entry.servings],
  ])
    summary.append(node("p", `${label}: ${value}`));
  summary.append(node("strong", copy.ingredients));
  const list = node("ul");
  for (const ingredient of entry.ingredients)
    list.append(
      node(
        "li",
        `${ingredient.name}: ${ingredient.quantity} ${ingredient.unit}`,
      ),
    );
  summary.append(list);
  form.append(summary);
}

export function renderRecipes(card, body) {
  if (!card || !body || !card._data) return;
  const access = accessOf(card);
  if (!access) {
    card._recipesDraft = null;
    return;
  }
  if (
    card._recipesDraft &&
    accessKey(card._recipesDraft.access) !== accessKey(access)
  ) {
    card._recipesDraft = null;
    card._actionError = "conflict";
  }
  if (card._mealsDraft || card._mealShoppingDraft || card._dietaryDraft) return;

  const copy = copyOf(card);
  const detached = () => !body.isConnected;
  const discardStale = (control, draft = card._recipesDraft) => {
    if (sameAccess(card, draft?.access || access)) return false;
    card._recipesDraft = null;
    card._actionError = "conflict";
    if (!detached() && control?.isConnected) card.render();
    return true;
  };
  const guard = (control, draft = null, allowLoading = false) => {
    if (draft && card._recipesDraft !== draft) return false;
    if (discardStale(control, draft)) return false;
    return (
      !detached() &&
      Boolean(control?.isConnected) &&
      !card._writing &&
      (allowLoading || !draft?.loading)
    );
  };
  const localButton = (label, action, primary = false, draft = null) => {
    const button = card.button(
      label,
      () => {
        if (!guard(button, draft)) return;
        action();
      },
      primary,
    );
    button.type = "button";
    return button;
  };
  const freshDraft = (values = {}) => ({
    access: deepFreeze(clone(access)),
    phase: "search",
    query: "",
    search: null,
    candidate: null,
    values: null,
    reviewed: false,
    error: null,
    loading: false,
    ...values,
  });
  const showError = (draft, key) => {
    if (card._recipesDraft !== draft) return;
    if (key === "source_changed") {
      card._recipesDraft = null;
      card._actionError = "conflict";
    } else if (card._recipesDraft === draft) {
      draft.loading = false;
      draft.error = key;
    }
    card.render();
  };
  const search = async (queryValue, page, control) => {
    if (!guard(control)) return;
    let query;
    try {
      query = String(queryValue ?? "").trim();
      if (query.length > 120) throw new Error("invalid");
      if (!Number.isSafeInteger(page) || page < 1 || page > 1000)
        throw new Error("invalid");
    } catch {
      card._actionError = "invalid_field";
      card.render();
      return;
    }
    const draft = freshDraft({
      query,
      phase: "search",
      loading: true,
      requestId: crypto.randomUUID(),
    });
    const requestId = draft.requestId;
    card._recipesDraft = draft;
    card._actionError = null;
    card.render();
    try {
      const response = await card._hass.callWS({
        type: "family_assistant/recipes",
        entry_id: access.entry,
        kind: "search",
        query,
        page,
      });
      if (card._recipesDraft !== draft || draft.requestId !== requestId) return;
      if (!sameAccess(card, draft.access)) {
        discardStale(body, draft);
        return;
      }
      draft.search = validateSearchResponse(
        response,
        draft.access.sourceRevision,
        page,
      );
      draft.loading = false;
      draft.error = null;
      card.render();
    } catch (error) {
      if (card._recipesDraft !== draft || draft.requestId !== requestId) return;
      showError(
        draft,
        error?.message === "source_changed"
          ? "source_changed"
          : error?.message === "provider_bad_response"
            ? "provider_bad_response"
            : "lookup_failed",
      );
    }
  };
  const getCandidate = async (draft, slug, control) => {
    if (!guard(control, draft)) return;
    draft.loading = true;
    draft.error = null;
    draft.requestId = crypto.randomUUID();
    const requestId = draft.requestId;
    card.render();
    try {
      const response = await card._hass.callWS({
        type: "family_assistant/recipes",
        entry_id: draft.access.entry,
        kind: "get",
        slug,
      });
      if (card._recipesDraft !== draft || draft.requestId !== requestId) return;
      if (!sameAccess(card, draft.access)) {
        discardStale(body, draft);
        return;
      }
      draft.candidate = validateCandidateResponse(
        response,
        draft.access.sourceRevision,
        slug,
      );
      draft.values = manualValues(draft.candidate);
      draft.phase = "edit";
      draft.loading = false;
      card.render();
    } catch (error) {
      if (card._recipesDraft !== draft || draft.requestId !== requestId) return;
      showError(
        draft,
        error?.message === "source_changed"
          ? "source_changed"
          : error?.message === "provider_bad_response"
            ? "provider_bad_response"
            : "lookup_failed",
      );
    }
  };
  const close = (draft = card._recipesDraft) => {
    if (!guard(body, draft, true)) return;
    card._recipesDraft = null;
    card._actionError = null;
    card.render();
  };
  const run = async (draft) => {
    if (!guard(body, draft)) return;
    if (!draft.pending) {
      draft.pending = deepFreeze({
        action: "pantry.meal_save",
        payload: clone(draft.payload),
        operation_id: crypto.randomUUID(),
      });
    }
    const pending = draft.pending;
    await card.command(pending.action, pending.payload, pending.operation_id);
    if (
      sameAccess(card, draft.access) &&
      card._recipesDraft === draft &&
      !card._actionError
    ) {
      card._recipesDraft = null;
      card.render();
    }
  };

  const section = node("details", null, "recipes-section");
  section.open = Boolean(card._recipesDraft);
  section.append(node("style", LOCAL_STYLE));
  section.append(node("summary", text(copy, "title", "Recipes from Mealie")));
  const content = node("div", null, "recipes-content");
  content.append(node("p", text(copy, "help", "Manual recipe import."), "sub"));
  section.append(content);

  const draft = card._recipesDraft;
  if (!draft || draft.phase === "search") {
    const searchForm = node("form", null, "recipe-form");
    searchForm.dataset.recipesForm = "search";
    const query = field(
      searchForm,
      text(copy, "query", "Recipe search"),
      "query",
      draft?.query || "",
    );
    query.maxLength = 120;
    searchForm.append(
      node("p", text(copy, "query_hint", "Leave blank to browse."), "sub"),
    );
    const actions = node("div", null, "actions");
    const searchButton = localButton(
      text(copy, "search", "Search recipes"),
      () => {},
      true,
      draft,
    );
    searchButton.type = "submit";
    actions.append(searchButton);
    if (draft)
      actions.append(
        localButton(
          text(copy, "clear", "Clear recipe search"),
          () => close(draft),
          false,
          draft,
        ),
      );
    searchForm.append(actions);
    searchForm.addEventListener("submit", (event) => {
      event.preventDefault();
      if (!guard(searchForm, draft)) return;
      void search(query.value, 1, searchForm);
    });
    content.append(searchForm);
    if (draft?.error)
      content.append(
        node("p", text(copy, draft.error, copy.lookup_failed), "notice"),
      );
    if (draft?.loading)
      content.append(
        node("p", text(copy, "loading", "Loading recipes…"), "sub"),
      );
    if (draft?.search && !draft.loading) {
      const results = node("div", null, "recipe-results");
      if (!draft.search.items.length)
        results.append(
          node("p", text(copy, "no_results", "No recipes found."), "sub"),
        );
      for (const item of draft.search.items) {
        const row = node("article", null, "item recipe-result");
        row.dataset.recipeSlug = item.slug;
        row.append(node("strong", item.name));
        row.append(
          localButton(
            text(copy, "use_recipe", "Use this recipe"),
            () => void getCandidate(draft, item.slug, row),
            false,
            draft,
          ),
        );
        results.append(row);
      }
      const pager = node("div", null, "recipe-toolbar");
      if (draft.search.page > 1)
        pager.append(
          localButton(
            copy.previous,
            () => void search(draft.query, draft.search.page - 1, pager),
            false,
            draft,
          ),
        );
      pager.append(
        node(
          "span",
          `${copy.page} ${draft.search.page} / ${draft.search.total_pages}`,
          "sub grow",
        ),
      );
      if (
        draft.search.total_pages > 0 &&
        draft.search.page < draft.search.total_pages &&
        draft.search.page < 1000
      )
        pager.append(
          localButton(
            copy.next,
            () => void search(draft.query, draft.search.page + 1, pager),
            false,
            draft,
          ),
        );
      results.append(pager);
      content.append(results);
    }
  } else if (draft.phase === "edit") {
    const form = node("form", null, "item recipe-form");
    form.dataset.recipesForm = "edit";
    form.append(node("h3", `${copy.candidate}: ${draft.candidate.title}`));
    const sourceDisplay = draft.candidate.source_servings.display;
    form.append(
      node("p", `${copy.source_servings}: ${sourceDisplay || "—"}`, "sub"),
    );
    appendBlockers(form, draft.candidate.blockers, copy);
    const fields = node("div", null, "recipe-fields");
    const controls = {
      week_start: field(
        fields,
        copy.week_start,
        "week_start",
        draft.values.week_start,
        "date",
      ),
      date: field(fields, copy.date, "date", draft.values.date, "date"),
      title: field(fields, copy.plan_title, "title", draft.values.title),
      servings: field(fields, copy.servings, "servings", draft.values.servings),
    };
    controls.title.parentElement.classList.add("wide");
    const slotLabel = node("label", copy.slot);
    const slot = document.createElement("select");
    slot.name = "slot";
    slot.append(node("option", "—"));
    slot.options[0].value = "";
    for (const value of SLOTS) {
      const option = node("option", text(copy, value, value));
      option.value = value;
      option.selected = draft.values.slot === value;
      slot.append(option);
    }
    slotLabel.append(slot);
    fields.append(slotLabel);
    controls.slot = slot;
    form.append(fields, node("p", copy.servings_hint, "sub"));
    const ingredients = node("div", null, "recipe-ingredients");
    ingredients.append(node("h4", copy.ingredients));
    draft.values.ingredients.forEach((ingredient, index) => {
      const row = node(
        "fieldset",
        null,
        `recipe-ingredient${ingredient.removed ? " removed" : ""}`,
      );
      row.dataset.recipeIngredient = String(index);
      row.append(
        node(
          "legend",
          ingredient.added
            ? copy.add_ingredient
            : `${copy.source_display}: ${ingredient.display}`,
        ),
      );
      if (ingredient.removed) {
        row.append(node("p", copy.removed, "sub"));
        row.append(
          localButton(
            copy.restore_ingredient,
            () => {
              if (!guard(row, draft)) return;
              if (
                draft.values.ingredients.filter((item) => !item.removed)
                  .length >= 20
              )
                return;
              ingredient.removed = false;
              card.render();
            },
            false,
            draft,
          ),
        );
      } else {
        appendBlockers(row, ingredient.blockers, copy);
        const rowFields = node("div", null, "recipe-ingredient-fields");
        const rowControls = {
          name: field(rowFields, copy.name, "name", ingredient.name),
          unit: field(rowFields, copy.unit, "unit", ingredient.unit),
          quantity: field(
            rowFields,
            copy.quantity,
            "quantity",
            ingredient.quantity,
          ),
        };
        row.append(rowFields);
        for (const [key, control] of Object.entries(rowControls)) {
          control.addEventListener("input", () => {
            if (!guard(control, draft)) return;
            ingredient[key] = control.value;
          });
          control.addEventListener("change", () => {
            if (!guard(control, draft)) return;
            ingredient[key] = control.value;
          });
        }
        if (ingredient.blockers.length) {
          row.append(node("strong", copy.requires_check));
          const label = node("label", null, "check");
          const checkbox = document.createElement("input");
          checkbox.type = "checkbox";
          checkbox.name = `verified_${index}`;
          checkbox.checked = ingredient.verified;
          label.append(checkbox, node("span", copy.verify_line));
          row.append(label);
          checkbox.addEventListener("change", () => {
            if (!guard(checkbox, draft)) return;
            ingredient.verified = checkbox.checked;
          });
        }
        row.append(
          localButton(
            copy.remove_ingredient,
            () => {
              if (!guard(row, draft)) return;
              ingredient.removed = true;
              card.render();
            },
            false,
            draft,
          ),
        );
      }
      ingredients.append(row);
    });
    const retainedCount = draft.values.ingredients.filter(
      (ingredient) => !ingredient.removed,
    ).length;
    if (retainedCount < 20)
      ingredients.append(
        localButton(
          copy.add_ingredient,
          () => {
            if (!guard(ingredients, draft)) return;
            draft.values.ingredients.push({
              display: "",
              name: "",
              unit: "",
              quantity: "",
              blockers: [],
              verified: false,
              removed: false,
              added: true,
            });
            card.render();
          },
          false,
          draft,
        ),
      );
    form.append(ingredients);
    for (const [key, control] of Object.entries(controls)) {
      control.addEventListener("input", () => {
        if (!guard(control, draft)) return;
        draft.values[key] = control.value;
      });
      control.addEventListener("change", () => {
        if (!guard(control, draft)) return;
        draft.values[key] = control.value;
      });
    }
    const actions = node("div", null, "actions");
    const review = localButton(copy.review, () => {}, true, draft);
    review.type = "submit";
    actions.append(
      review,
      localButton(copy.cancel, () => close(draft), false, draft),
    );
    form.append(actions);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      if (!guard(form, draft)) return;
      try {
        for (const [key, control] of Object.entries(controls))
          draft.values[key] = control.value;
        draft.payload = deepFreeze(mealPayload(draft.values));
        draft.phase = "review";
        draft.reviewed = false;
        draft.error = null;
        card._actionError = null;
        card.render();
      } catch {
        draft.error = "invalid";
        card._actionError = "invalid_field";
        card.render();
      }
    });
    if (draft.error)
      form.prepend(node("p", text(copy, draft.error, copy.invalid), "notice"));
    content.append(form);
  } else if (draft.phase === "review") {
    const form = node("form", null, "item recipe-form");
    form.dataset.recipesForm = "review";
    appendReview(form, draft, copy);
    const label = node("label", null, "check");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.name = "reviewed";
    checkbox.checked = draft.reviewed;
    checkbox.disabled = Boolean(draft.pending);
    label.append(checkbox, node("span", copy.confirm_exact));
    form.append(label);
    checkbox.addEventListener("change", () => {
      if (!guard(checkbox, draft) || draft.pending) return;
      draft.reviewed = checkbox.checked;
    });
    const actions = node("div", null, "actions");
    const submit = localButton(
      draft.pending ? copy.retry : copy.create_draft,
      () => {},
      true,
      draft,
    );
    submit.type = "submit";
    actions.append(
      submit,
      localButton(
        copy.back,
        () => {
          if (!guard(actions, draft) || draft.pending) return;
          draft.phase = "edit";
          draft.payload = null;
          draft.reviewed = false;
          card._actionError = null;
          card.render();
        },
        false,
        draft,
      ),
      localButton(copy.cancel, () => close(draft), false, draft),
    );
    form.append(actions);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      if (!guard(form, draft)) return;
      if (!draft.pending) {
        if (!checkbox.checked) return;
        draft.reviewed = true;
      }
      void run(draft);
    });
    content.append(form);
  }

  body.append(section);
}
