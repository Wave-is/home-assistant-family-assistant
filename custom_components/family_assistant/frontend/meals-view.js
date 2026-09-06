/* Accessible weekly meal-plan editor.  Meal quantities are deliberately manual. */

import { MEALS_COPY } from "./meals-copy.js";

const PARENTS = new Set(["owner", "parent"]);
const VIEWERS = new Set(["owner", "parent", "adult", "child"]);
const SLOTS = ["breakfast", "lunch", "dinner", "snack"];
const ISO = /^\d{4}-\d{2}-\d{2}$/;

const node = (tag, text, className) => {
  const value = document.createElement(tag);
  if (text !== undefined && text !== null) value.textContent = String(text);
  if (className) value.className = className;
  return value;
};
const copyOf = (card) => {
  const lang = card._config?.language || card._hass?.language || "en";
  return MEALS_COPY[lang.split("-")[0]] || MEALS_COPY.en;
};
const text = (copy, key, fallback) => copy[key] || fallback;
const clone = (value) => JSON.parse(JSON.stringify(value));
const val = (raw, key, max, required = false) => {
  const value = String(raw ?? "").trim();
  if ((required && !value) || value.length > max) throw new Error(key);
  return value;
};
const number = (raw, key, min, max, integer = false) => {
  const value = String(raw ?? "").trim();
  const re = integer
    ? /^(?:[1-9]|[1-4]\d|50)$/
    : /^(?:0|[1-9]\d*)(?:\.\d{1,3})?$/;
  if (!re.test(value)) throw new Error(key);
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < min || parsed > max)
    throw new Error(key);
  return parsed;
};
function date(raw, key = "week_start") {
  if (!ISO.test(raw)) throw new Error(key);
  const [year, month, day] = raw.split("-").map(Number);
  if (year < 1 || year > 9999 || month < 1 || month > 12 || day < 1 || day > 31)
    throw new Error(key);
  const d = new Date(`${raw}T00:00:00Z`);
  if (
    Number.isNaN(d.valueOf()) ||
    d.getUTCFullYear() !== year ||
    d.getUTCMonth() + 1 !== month ||
    d.getUTCDate() !== day
  )
    throw new Error(key);
  return raw;
}
function monday(raw) {
  date(raw);
  const d = new Date(`${raw}T00:00:00Z`);
  if (
    d.getUTCDay() !== 1 ||
    new Date(d.valueOf() + 6 * 86400000).getUTCFullYear() > 9999
  )
    throw new Error("week_start");
  return raw;
}
function withinWeek(raw, week) {
  date(raw, "date");
  const start = new Date(`${week}T00:00:00Z`);
  const current = new Date(`${raw}T00:00:00Z`);
  const days = Math.round((current - start) / 86400000);
  if (days < 0 || days > 6) throw new Error("date");
  return raw;
}
function blankEntry(week) {
  return {
    date: week,
    slot: "breakfast",
    title: "",
    servings: "1",
    ingredients: [],
  };
}
function blankValues(plan) {
  return {
    week_start: plan?.week_start || "",
    title: plan?.title || "",
    note: plan?.note || "",
    entries: clone(plan?.entries || [blankEntry(plan?.week_start || "")]),
    reason: "",
    reviewed: false,
  };
}
function validateEntries(values) {
  const entries = values.entries || [];
  if (!Array.isArray(entries) || entries.length < 1 || entries.length > 28)
    throw new Error("entries");
  const seen = new Set();
  let ingredientCount = 0;
  return entries.map((entry) => {
    const item = {
      date: withinWeek(String(entry.date || ""), values.week_start),
      slot: String(entry.slot || ""),
      title: val(entry.title, "title", 120, true),
      servings: number(entry.servings, "servings", 1, 50, true),
      ingredients: Array.isArray(entry.ingredients) ? entry.ingredients : [],
    };
    if (!SLOTS.includes(item.slot)) throw new Error("slot");
    const identity = `${item.date}/${item.slot}`;
    if (seen.has(identity)) throw new Error("slot");
    seen.add(identity);
    if (item.ingredients.length > 20) throw new Error("ingredients");
    ingredientCount += item.ingredients.length;
    if (ingredientCount > 100) throw new Error("ingredients");
    item.ingredients = item.ingredients.map((ingredient) => ({
      name: val(ingredient.name, "name", 120, true),
      unit: val(ingredient.unit, "unit", 24, true),
      quantity: number(
        ingredient.quantity,
        "quantity",
        Number.MIN_VALUE,
        1_000_000,
      ),
    }));
    return item;
  });
}
function payload(values, plan) {
  const week = monday(String(values.week_start || ""));
  const next = {
    week_start: week,
    title: val(values.title, "title", 120, true),
    entries: validateEntries({ ...values, week_start: week }),
  };
  const note = val(values.note, "note", 500);
  if (note) next.note = note;
  if (!plan) return next;
  const result = { id: plan.id, revision: plan.revision };
  for (const key of ["week_start", "title", "entries", "note"]) {
    const old =
      key === "note"
        ? plan.note || ""
        : plan[key] || (key === "entries" ? [] : "");
    if (JSON.stringify(next[key] ?? "") !== JSON.stringify(old))
      result[key] = next[key] ?? "";
  }
  if (Object.keys(result).length === 2) throw new Error("unchanged");
  return result;
}
function field(
  form,
  copy,
  name,
  value,
  type = "text",
  required = false,
  labelKey = name,
  fallback = name,
) {
  const label = node("label", text(copy, labelKey, fallback));
  const input = document.createElement(type === "select" ? "select" : "input");
  input.type = type === "select" ? "text" : type;
  input.name = name;
  input.value = value ?? "";
  input.required = required;
  input.dataset.mealsField = name;
  label.append(input);
  form.append(label);
  return input;
}

export function renderMeals(card, body) {
  if (!card || !body || !card._data) return;
  const role = card._data.role;
  const parent = PARENTS.has(role) && Boolean(card.parent ?? true);
  const moduleEnabled = (card._data.settings?.modules || []).includes("pantry");
  if (!VIEWERS.has(role) || !card._data.actor || role === "guest") {
    card._mealsDraft = null;
    return;
  }
  const copy = copyOf(card);
  if (!moduleEnabled) {
    card._mealsDraft = null;
    body.append(
      node(
        "div",
        text(copy, "module_off", "Meal planning module is disabled."),
        "notice",
      ),
    );
    return;
  }
  const generation = card._generation;
  const entryId = card._entry;
  const scope = JSON.stringify([generation, entryId, role, card._data.actor]);
  const actor = card._data.actor;
  const identityChanged = () =>
    card._generation !== generation ||
    card._entry !== entryId ||
    card._data?.role !== role ||
    card._data?.actor !== actor ||
    !(card._data.settings?.modules || []).includes("pantry");
  const stale = () => identityChanged() || !body.isConnected;
  const plans = Array.isArray(card._data.pantry?.meal_plans)
    ? card._data.pantry.meal_plans
    : [];
  const visible = parent
    ? plans
    : plans.filter((plan) => plan.status === "published");
  const draft = card._mealsDraft;
  if (draft && draft.scope !== scope) {
    card._mealsDraft = null;
    card._actionError = "conflict";
  }
  if (
    card._mealsDraft &&
    !parent &&
    ["new", "edit", "publish", "archive"].includes(card._mealsDraft.type)
  ) {
    card._mealsDraft = null;
    card._actionError = "conflict";
  }
  const current = (id, revision) =>
    (card._data.pantry?.meal_plans || []).find(
      (p) => p.id === id && p.revision === revision && p.status !== "archived",
    );
  const button = (label, action, primary = false) => {
    const b = card.button(
      label,
      () => {
        if (!stale() && b.isConnected && !card._writing) action();
      },
      primary,
    );
    return b;
  };
  const open = (value, valid = () => true) => {
    if (stale() || card._writing || !valid()) {
      if (!stale()) {
        card._actionError = "conflict";
        card.render();
      }
      return;
    }
    const original = value.planId
      ? clone(current(value.planId, value.revision))
      : null;
    card._actionError = null;
    card._mealsDraft = { ...value, original, scope };
    card.render();
  };
  const close = () => {
    if (!stale()) {
      card._mealsDraft = null;
      card._actionError = null;
      card.render();
    }
  };
  const run = async (action, operationPayload, valid = () => true) => {
    if (stale() || card._writing || !card._mealsDraft) return;
    const state = card._mealsDraft;
    if (!state.pending && !valid()) {
      card._mealsDraft = null;
      card._actionError = "conflict";
      card.render();
      return;
    }
    if (!state.pending)
      state.pending = {
        action,
        payload: Object.freeze(clone(operationPayload)),
      };
    await card.command(state.pending.action, state.pending.payload);
    if (
      !identityChanged() &&
      card._mealsDraft === state &&
      !card._actionError
    ) {
      card._mealsDraft = null;
      card.render();
    }
  };
  const host = node("div", null, "meals-form-host");
  body.append(host);
  body.append(node("h2", text(copy, "title", "Meal Plan")));
  if (parent)
    body.append(
      button(text(copy, "new_plan", "New plan"), () =>
        open({ type: "new", values: blankValues() }),
      ),
    );
  if (!visible.length)
    body.append(
      node(
        "p",
        parent
          ? text(copy, "empty", "No meals planned for this week.")
          : text(copy, "no_published", "No published meal plan for this week."),
        "sub",
      ),
    );
  for (const plan of visible) {
    const row = node("section", null, "meal-plan");
    row.dataset.mealPlan = plan.id;
    row.append(
      node("h3", plan.title),
      node(
        "p",
        `${plan.week_start} · ${text(copy, plan.status, plan.status)}`,
        "sub",
      ),
    );
    for (const meal of plan.entries || []) {
      const mealRow = node("div", null, "meal-entry");
      mealRow.append(
        node(
          "strong",
          `${meal.date} · ${text(copy, meal.slot, meal.slot)} · ${meal.title}`,
        ),
        node("span", ` · ${copy.servings}: ${meal.servings}`, "sub"),
      );
      if (meal.ingredients?.length)
        mealRow.append(
          node(
            "div",
            meal.ingredients
              .map((i) => `${i.name}: ${i.quantity} ${i.unit}`)
              .join(", "),
            "sub",
          ),
        );
      row.append(mealRow);
    }
    if (parent && plan.note)
      row.append(
        node("p", `${text(copy, "note", "Parent note")}: ${plan.note}`, "sub"),
      );
    if (parent && Array.isArray(plan.history) && plan.history.length) {
      const history = document.createElement("details");
      history.append(node("summary", text(copy, "history", "Plan history")));
      for (const event of plan.history) {
        const actorName =
          card._data.members?.find((member) => member.id === event.actor)
            ?.name ||
          event.actor ||
          "";
        const actionLabel = copy[`history_${event.action}`] || copy.history;
        const labels = Object.keys(event.changes || {}).map(
          (key) => copy[key === "title" ? "plan_title" : key] || copy.entries,
        );
        history.append(
          node(
            "p",
            [event.at, actorName, actionLabel, labels.join(", "), event.reason]
              .filter(Boolean)
              .join(" · "),
            "sub",
          ),
        );
      }
      row.append(history);
    }
    const actions = node("div", null, "actions");
    if (parent && plan.status !== "archived") {
      actions.append(
        button(text(copy, "edit", "Edit plan"), () =>
          open(
            {
              type: "edit",
              planId: plan.id,
              revision: plan.revision,
              values: blankValues(plan),
            },
            () => Boolean(current(plan.id, plan.revision)),
          ),
        ),
      );
      if (plan.status === "draft")
        actions.append(
          button(text(copy, "publish", "Publish plan"), () =>
            open(
              {
                type: "publish",
                planId: plan.id,
                revision: plan.revision,
                values: { reviewed: false },
              },
              () => Boolean(current(plan.id, plan.revision)),
            ),
          ),
        );
      actions.append(
        button(text(copy, "archive", "Archive plan"), () =>
          open(
            {
              type: "archive",
              planId: plan.id,
              revision: plan.revision,
              values: { reason: "", reviewed: false },
            },
            () => Boolean(current(plan.id, plan.revision)),
          ),
        ),
      );
    }
    if (actions.children.length) row.append(actions);
    body.append(row);
  }
  if (parent) {
    const help = document.createElement("details");
    help.append(
      node("summary", text(copy, "title", "Meal planning help")),
      node(
        "p",
        text(copy, "help", "Parents plan and publish weekly meals."),
        "sub",
      ),
      node(
        "p",
        text(copy, "manual_hint", "Meal quantities are manual."),
        "sub",
      ),
      node(
        "p",
        text(
          copy,
          "publish_hint",
          "Publishing makes the menu visible to family.",
        ),
        "sub",
      ),
      node(
        "p",
        text(
          copy,
          "edit_hint",
          "Editing a published plan returns it to draft.",
        ),
        "sub",
      ),
      node("p", text(copy, "private_hint", "Notes are parent-private."), "sub"),
    );
    body.append(help);
  }
  const active = card._mealsDraft;
  if (!active) return;
  if (active.scope !== scope) return;
  const form = document.createElement("form");
  form.className = "meal-plan-form";
  form.dataset.mealsForm = active.type;
  host.append(form);
  const values =
    active.values ||
    (active.values =
      active.type === "edit"
        ? blankValues(current(active.planId, active.revision))
        : {});
  if (active.type === "new" || active.type === "edit") {
    const original = active.original;
    const weekField = field(
      form,
      copy,
      "week_start",
      values.week_start,
      "date",
      true,
    );
    weekField.dataset.mealsPath = "week_start";
    const titleField = field(
      form,
      copy,
      "title",
      values.title,
      "text",
      true,
      "plan_title",
      "Plan title",
    );
    titleField.dataset.mealsPath = "title";
    const note = field(form, copy, "note", values.note);
    note.maxLength = 500;
    note.dataset.mealsPath = "note";
    const entries = node("div", null, "meal-entries");
    entries.append(node("h3", text(copy, "entries", "Planned meals")));
    const remember = () => {
      if (!stale() && !active.pending) {
        const initializeDates = active.type === "new" && !values.week_start;
        values.week_start = form.elements.week_start.value;
        values.title = form.elements.title.value;
        values.note = form.elements.note.value;
        if (initializeDates) {
          for (const [index, entry] of (values.entries || []).entries()) {
            if (entry.date) continue;
            entry.date = values.week_start;
            const control = form.querySelector(
              `[data-meals-path="${index}.date"]`,
            );
            if (control) control.value = entry.date;
          }
        }
      }
    };
    const drawEntry = (entry, index) => {
      const section = node("fieldset", null, "meal-entry-editor");
      section.dataset.mealsEntry = String(index);
      const d = field(section, copy, "date", entry.date, "date", true);
      d.dataset.mealsPath = `${index}.date`;
      const slotLabel = node("label", text(copy, "slot", "Meal slot"));
      const select = document.createElement("select");
      select.name = "slot";
      select.dataset.mealsPath = `${index}.slot`;
      for (const slot of SLOTS) {
        const option = node("option", text(copy, slot, slot));
        option.value = slot;
        option.selected = entry.slot === slot;
        select.append(option);
      }
      slotLabel.append(select);
      section.append(slotLabel);
      const title = field(
        section,
        copy,
        "meal_title",
        entry.title,
        "text",
        true,
      );
      title.dataset.mealsPath = `${index}.title`;
      const servings = field(
        section,
        copy,
        "servings",
        entry.servings,
        "text",
        true,
      );
      servings.dataset.mealsPath = `${index}.servings`;
      const ingredients = node("div", null, "meal-ingredients");
      ingredients.append(node("h4", text(copy, "ingredients", "Ingredients")));
      (entry.ingredients || []).forEach((ingredient, ingredientIndex) => {
        const line = node("div", null, "ingredient-row");
        for (const [key, fallback] of [
          ["name", "name"],
          ["unit", "unit"],
          ["quantity", "quantity"],
        ]) {
          const input = field(line, copy, key, ingredient[key]);
          input.dataset.mealsPath = `${index}.ingredients.${ingredientIndex}.${key}`;
        }
        line.append(
          button(text(copy, "remove_ingredient", "Remove ingredient"), () => {
            if (stale() || active.pending) return;
            entry.ingredients.splice(ingredientIndex, 1);
            card.render();
          }),
        );
        ingredients.append(line);
      });
      if ((entry.ingredients || []).length < 20)
        ingredients.append(
          button(text(copy, "add_ingredient", "Add ingredient"), () => {
            if (
              stale() ||
              active.pending ||
              (values.entries || []).reduce(
                (n, e) => n + e.ingredients.length,
                0,
              ) >= 100
            )
              return;
            entry.ingredients.push({ name: "", unit: "", quantity: "1" });
            card.render();
          }),
        );
      section.append(ingredients);
      if (values.entries.length > 1)
        section.append(
          button(text(copy, "remove_meal", "Remove meal"), () => {
            if (stale() || active.pending) return;
            values.entries.splice(index, 1);
            card.render();
          }),
        );
      entries.append(section);
    };
    (values.entries || []).forEach(drawEntry);
    if (values.entries.length < 28)
      entries.append(
        button(text(copy, "add_meal", "Add meal"), () => {
          if (stale() || active.pending) return;
          remember();
          values.entries.push(blankEntry(values.week_start));
          card.render();
        }),
      );
    form.append(entries);
    const syncPath = (control) => {
      const path = String(control.dataset.mealsPath || "").split(".");
      if (path.length < 2 || !control.dataset.mealsPath) return;
      let target = values.entries[Number(path.shift())];
      for (let i = 0; i < path.length - 1; i += 1) target = target[path[i]];
      target[path[path.length - 1]] = control.value;
    };
    form.querySelectorAll("input,select").forEach((control) => {
      control.addEventListener("input", () => {
        if (stale() || active.pending) return;
        syncPath(control);
        remember();
      });
      control.addEventListener("change", () => {
        if (stale() || active.pending) return;
        syncPath(control);
        remember();
      });
    });
    if (active.pending)
      form.querySelectorAll("input,select").forEach((control) => {
        control.disabled = true;
      });
    form.append(
      node(
        "p",
        text(copy, "totals_hint", "Ingredient quantities are manual totals."),
        "sub",
      ),
    );
    const actions = node("div", null, "actions");
    const submit = button(
      active.pending
        ? text(copy, "retry", "Retry")
        : text(copy, "save", "Save"),
      () => {},
      true,
    );
    submit.type = "submit";
    actions.append(submit, button(text(copy, "cancel", "Cancel"), close));
    form.append(actions);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      if (stale() || active.pending || card._writing) {
        if (active.pending)
          run(active.pending.action, active.pending.payload, () => true);
        return;
      }
      try {
        remember();
        const p = payload(values, original);
        run(
          "pantry.meal_save",
          p,
          () =>
            active.type === "new" ||
            Boolean(current(active.planId, active.revision)),
        );
      } catch (error) {
        card._actionError =
          error.message === "unchanged"
            ? "invalid_transition"
            : "invalid_field";
        if (!stale()) card.render();
      }
    });
  } else if (active.type === "publish" || active.type === "archive") {
    const plan = active.original;
    if (!current(active.planId, active.revision) && !active.pending) {
      card._mealsDraft = null;
      card._actionError = "conflict";
      return;
    }
    form.append(
      node(
        "h3",
        active.type === "publish"
          ? text(copy, "review_publish", "Publish this meal plan?")
          : text(copy, "review_archive", "Archive this meal plan?"),
      ),
      node("p", `${plan?.title || ""} · ${plan?.week_start || ""}`, "sub"),
    );
    if (active.type === "archive") {
      const reason = field(
        form,
        copy,
        "reason",
        active.values.reason,
        "text",
        true,
      );
      reason.maxLength = 500;
      reason.addEventListener("input", () => {
        if (!stale() && !active.pending) active.values.reason = reason.value;
      });
    }
    const reviewKey =
      active.type === "publish" ? "review_publish" : "review_archive";
    const check = field(
      form,
      copy,
      "reviewed",
      active.values.reviewed ? "on" : "",
      "checkbox",
      true,
      reviewKey,
      "Review and confirm",
    );
    check.checked = Boolean(active.values.reviewed);
    check.addEventListener("change", () => {
      if (!stale() && !active.pending) active.values.reviewed = check.checked;
    });
    const actions = node("div", null, "actions");
    const submit = button(
      active.pending
        ? text(copy, "retry", "Retry")
        : text(copy, "save", "Save"),
      () => {},
      true,
    );
    submit.type = "submit";
    actions.append(submit, button(text(copy, "cancel", "Cancel"), close));
    form.append(actions);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      if (stale()) return;
      active.values.reviewed = check.checked;
      if (active.type === "archive" && form.elements.reason)
        active.values.reason = form.elements.reason.value;
      if (!active.values.reviewed) return;
      try {
        const p = active.pending?.payload || {
          id: active.planId,
          revision: active.revision,
          ...(active.type === "archive"
            ? { reason: val(active.values.reason, "reason", 500, true) }
            : {}),
        };
        run(
          active.type === "publish"
            ? "pantry.meal_publish"
            : "pantry.meal_archive",
          p,
          () => Boolean(current(active.planId, active.revision)),
        );
      } catch (error) {
        card._actionError =
          error.message === "unchanged"
            ? "invalid_transition"
            : "invalid_field";
        if (!stale()) card.render();
      }
    });
  }
}
