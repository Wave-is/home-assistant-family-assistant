/* Mobile-friendly pantry inventory and reviewable shopping suggestions. */

import { PANTRY_COPY } from "./pantry-copy.js";

const PARENT_ROLES = new Set(["owner", "parent"]);
const ACTIVE_ROLES = new Set(["owner", "parent", "adult", "child"]);
const QUANTITY = /^(?:0|[1-9]\d*)(?:\.\d{1,3})?$/;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

const el = (tag, text, className) => {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = String(text);
  if (className) node.className = className;
  return node;
};

const copyFor = (card) => {
  const language = card._config?.language || card._hass?.language || "en";
  return PANTRY_COPY[language.split("-")[0]] || PANTRY_COPY.en;
};

const textFor = (copy, key, fallback) => copy[key] || fallback;
const snapshot = (value) => JSON.parse(JSON.stringify(value));

const formatText = (template, values) =>
  String(template).replace(/\{([a-z_]+)\}/g, (match, key) =>
    Object.hasOwn(values, key) ? String(values[key]) : match,
  );

function appendExpiryReminderInfo(card, body, copy) {
  const settings = card._data?.settings || {};
  const enabled = settings.pantry_expiry_reminders === true;
  const configuredDays = settings.pantry_expiry_days;
  const days =
    Number.isInteger(configuredDays) &&
    configuredDays >= 0 &&
    configuredDays <= 30
      ? configuredDays
      : 3;
  const timezone =
    typeof settings.timezone === "string" && settings.timezone.trim()
      ? settings.timezone
      : "UTC";
  const section = el("details", null, "pantry-expiry-info");
  section.dataset.pantryExpiryInfo = enabled ? "enabled" : "disabled";
  const title = textFor(copy, "expiry_reminders_title", "Expiry reminders");
  const status = enabled
    ? textFor(copy, "expiry_reminders_on", "Enabled.")
    : textFor(copy, "expiry_reminders_off", "Disabled.");
  section.append(el("summary", `${title}: ${status}`));
  if (enabled) {
    const key =
      days === 0 ? "expiry_reminders_window_zero" : "expiry_reminders_window";
    section.append(
      el(
        "p",
        formatText(
          textFor(
            copy,
            key,
            "After 09:00 in {timezone}, parents are notified privately for each current item revision.",
          ),
          { days, timezone },
        ),
        "sub",
      ),
      el(
        "p",
        textFor(
          copy,
          "expiry_reminders_factual",
          "Reminders do not change stock or determine food safety.",
        ),
        "sub",
      ),
    );
  }
  section.append(
    el(
      "p",
      textFor(
        copy,
        "expiry_reminders_settings",
        "The household owner can change this in the integration Settings.",
      ),
      "sub",
    ),
  );
  body.append(section);
}

function quantity(raw, field) {
  const value = String(raw ?? "").trim();
  if (!QUANTITY.test(value)) throw new Error(field);
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < 0 || parsed > 1_000_000)
    throw new Error(field);
  return parsed;
}

function isoDate(raw) {
  if (raw === "") return null;
  if (!ISO_DATE.test(raw)) throw new Error("expires_on");
  const [year, month, day] = raw.split("-").map(Number);
  if (year < 1) throw new Error("expires_on");
  const parsed = new Date(0);
  parsed.setUTCHours(0, 0, 0, 0);
  parsed.setUTCFullYear(year, month - 1, day);
  if (
    parsed.getUTCFullYear() !== year ||
    parsed.getUTCMonth() !== month - 1 ||
    parsed.getUTCDate() !== day
  ) {
    throw new Error("expires_on");
  }
  return raw;
}

function bounded(raw, field, maximum, required = false) {
  const value = String(raw ?? "").trim();
  if ((required && !value) || value.length > maximum) throw new Error(field);
  return value;
}

function inputField(form, copy, field, fallback, value = "", type = "text") {
  const label = el("label", textFor(copy, field, fallback));
  const input = document.createElement("input");
  input.type = type;
  input.name = field;
  input.value = value ?? "";
  input.dataset.pantryField = field;
  label.append(input);
  form.append(label);
  return input;
}

function reasonField(form, copy) {
  const input = inputField(form, copy, "reason", "Reason");
  input.maxLength = 500;
  input.required = true;
  return input;
}

function appendSubmit(form, card, copy, label, cancel) {
  const actions = el("div", null, "actions");
  const submit = card.button(label, () => {}, true);
  submit.type = "submit";
  const cancelButton = card.button(textFor(copy, "cancel", "Cancel"), cancel);
  actions.append(submit, cancelButton);
  form.append(actions);
}

function errorKey(error) {
  return error instanceof Error && error.message === "unchanged"
    ? "invalid_transition"
    : "invalid_field";
}

function payloadForItem(values, original = null) {
  const next = {
    name: bounded(values.name, "name", 200, true),
    unit: bounded(values.unit, "unit", 32, true),
    quantity: quantity(values.quantity, "quantity"),
    minimum_quantity: quantity(values.minimum_quantity, "minimum_quantity"),
    category: bounded(values.category, "category", 80),
    location: bounded(values.location, "location", 80),
    note: bounded(values.note, "note", 500),
    expires_on: isoDate(values.expires_on),
  };
  if (!original) return next;

  const payload = { id: original.id, revision: original.revision };
  for (const [key, value] of Object.entries(next)) {
    const oldValue = original[key] ?? (key === "expires_on" ? null : "");
    if (value !== oldValue) payload[key] = value;
  }
  if ("quantity" in payload || "unit" in payload) {
    payload.reason = bounded(values.reason, "reason", 500, true);
  }
  if (Object.keys(payload).length === 2) throw new Error("unchanged");
  return payload;
}

function itemValues(item = null) {
  return {
    name: item?.name ?? "",
    unit: item?.unit ?? "",
    quantity: String(item?.quantity ?? 0),
    minimum_quantity: String(item?.minimum_quantity ?? 0),
    category: item?.category ?? "",
    location: item?.location ?? "",
    note: item?.note ?? "",
    expires_on: item?.expires_on ?? "",
    reason: "",
  };
}

function rememberForm(form, draft, stale) {
  const remember = () => {
    if (stale() || draft.pending) return;
    draft.values = Object.fromEntries(new FormData(form));
  };
  for (const control of form.querySelectorAll("input,select,textarea")) {
    control.addEventListener("input", remember);
    control.addEventListener("change", remember);
  }
  return remember;
}

export function renderPantry(card, body) {
  if (!card || !body || !card._data) return;
  const role = card._data.role;
  const actor = card._data.actor;
  const moduleEnabled = card._data.settings?.modules?.includes("pantry");
  if (!ACTIVE_ROLES.has(role) || !actor || role === "guest") {
    card._pantryDraft = null;
    return;
  }
  if (!moduleEnabled) {
    card._pantryDraft = null;
    body.append(
      el(
        "div",
        textFor(copyFor(card), "module_off", "Pantry module is disabled."),
        "notice",
      ),
    );
    return;
  }

  const copy = copyFor(card);
  const parent = PARENT_ROLES.has(role) && Boolean(card.parent);
  const canCount = parent || role === "adult";
  const generation = card._generation;
  const entry = card._entry;
  const scope = JSON.stringify([generation, entry, role, actor]);
  const staleIdentity = () =>
    card._generation !== generation ||
    card._entry !== entry ||
    card._data?.role !== role ||
    card._data?.actor !== actor ||
    !card._data?.settings?.modules?.includes("pantry");
  const stale = () => staleIdentity() || !body.isConnected;

  if (card._pantryDraft) {
    if (card._pantryDraft.scope && card._pantryDraft.scope !== scope) {
      card._pantryDraft = null;
      card._actionError = "conflict";
    } else {
      card._pantryDraft.scope = scope;
    }
  }
  if (
    card._pantryDraft &&
    ((!parent &&
      [
        "new",
        "edit",
        "archive",
        "suggestion_accept",
        "suggestion_dismiss",
      ].includes(card._pantryDraft.type)) ||
      (!canCount && card._pantryDraft.type === "stock"))
  ) {
    card._pantryDraft = null;
    card._actionError = "conflict";
  }

  const pantry = card._data.pantry || {
    items: [],
    archived: [],
    suggestions: [],
  };
  const items = Array.isArray(pantry.items) ? pantry.items : [];
  const archived = Array.isArray(pantry.archived) ? pantry.archived : [];
  const suggestions = Array.isArray(pantry.suggestions)
    ? pantry.suggestions
    : [];
  const freshItem = (id, revision) =>
    (card._data?.pantry?.items || []).find(
      (item) =>
        item.id === id &&
        item.revision === revision &&
        item.status === "active",
    );
  const freshSuggestion = (id, revision) =>
    (card._data?.pantry?.suggestions || []).find(
      (item) =>
        item.id === id && item.revision === revision && item.status === "open",
    );

  const localButton = (label, action, primary = false) => {
    const button = card.button(
      label,
      () => {
        if (stale() || !button.isConnected || card._writing) return;
        action();
      },
      primary,
    );
    return button;
  };

  const openDraft = (draft, current = () => true) => {
    if (stale() || card._writing || !current()) {
      if (!staleIdentity()) {
        card._actionError = "conflict";
        card.render();
      }
      return;
    }
    card._actionError = null;
    card._pantryDraft = { ...draft, scope };
    card.render();
  };

  const closeDraft = () => {
    if (stale()) return;
    card._pantryDraft = null;
    card._actionError = null;
    card.render();
  };

  const run = async (action, payload, current) => {
    if (stale() || card._writing) return;
    const draft = card._pantryDraft;
    if (!draft) return;
    if (!draft.pending && !current()) {
      if (!staleIdentity()) {
        card._pantryDraft = null;
        card._actionError = "conflict";
        card.render();
      }
      return;
    }
    if (!draft.pending) {
      draft.pending = Object.freeze({
        action,
        payload: Object.freeze(snapshot(payload)),
      });
    }
    const pending = draft.pending;
    await card.command(pending.action, pending.payload);
    if (!staleIdentity() && card._pantryDraft === draft) {
      if (!card._actionError) card._pantryDraft = null;
      card.render();
    }
  };

  if (parent) appendExpiryReminderInfo(card, body, copy);

  if (parent) {
    body.append(
      localButton(textFor(copy, "new_item", "Add pantry item"), () =>
        openDraft({ type: "new", values: itemValues() }),
      ),
    );
  }

  // Keep the active editor above the inventory on narrow screens.
  const formHost = el("div", null, "pantry-form-host");
  body.append(formHost);

  const list = el("div", null, "pantry-list");
  if (!items.length)
    list.append(el("p", textFor(copy, "empty", "No pantry items."), "sub"));
  for (const item of items) {
    const itemId = item.id;
    const itemRevision = item.revision;
    const row = el("section", null, "item pantry-item");
    row.dataset.pantryItem = itemId;
    const heading = el("div", null, "row");
    heading.append(el("strong", item.name, "grow"));
    if (item.low_stock)
      heading.append(
        el("span", textFor(copy, "low_stock", "Low stock"), "badge"),
      );
    row.append(heading);
    row.append(
      el(
        "div",
        `${textFor(copy, "quantity", "Quantity")}: ${item.quantity} ${item.unit} · ${textFor(copy, "minimum_quantity", "Minimum")}: ${item.minimum_quantity} ${item.unit}`,
        "sub",
      ),
    );
    const metadata = [];
    if (item.category)
      metadata.push(
        `${textFor(copy, "category", "Category")}: ${item.category}`,
      );
    if (item.location)
      metadata.push(
        `${textFor(copy, "location", "Location")}: ${item.location}`,
      );
    if (item.expires_on) {
      metadata.push(
        `${textFor(copy, "expires_on", "Expiry")}: ${item.expires_on} · ${textFor(copy, `expiry_${item.expiry_status}`, item.expiry_status)}`,
      );
    } else {
      metadata.push(
        `${textFor(copy, "expires_on", "Expiry")}: ${textFor(copy, `expiry_${item.expiry_status || "none"}`, textFor(copy, "date_unknown", "Date unknown"))}`,
      );
    }
    if (metadata.length) row.append(el("div", metadata.join(" · "), "sub"));
    if (parent && item.note) {
      row.append(
        el(
          "div",
          `${textFor(copy, "note", "Private note")}: ${item.note}`,
          "sub",
        ),
      );
    }
    const actions = el("div", null, "actions");
    if (canCount) {
      actions.append(
        localButton(textFor(copy, "stock_set", "Correct quantity"), () =>
          openDraft(
            {
              type: "stock",
              title: item.name,
              itemId,
              revision: itemRevision,
              values: { quantity: String(item.quantity), reason: "" },
            },
            () => Boolean(freshItem(itemId, itemRevision)),
          ),
        ),
      );
    }
    if (parent) {
      actions.append(
        localButton(textFor(copy, "edit", "Edit"), () =>
          openDraft(
            {
              type: "edit",
              title: item.name,
              itemId,
              revision: itemRevision,
              values: itemValues(item),
            },
            () => Boolean(freshItem(itemId, itemRevision)),
          ),
        ),
        localButton(textFor(copy, "archive", "Archive"), () =>
          openDraft(
            {
              type: "archive",
              title: item.name,
              itemId,
              revision: itemRevision,
              values: { reason: "" },
            },
            () => Boolean(freshItem(itemId, itemRevision)),
          ),
        ),
      );
    }
    if (actions.children.length) row.append(actions);
    list.append(row);
  }
  const help = el("details", null, "pantry-help");
  help.append(
    el("summary", textFor(copy, "inventory_hint", "About pantry inventory")),
  );
  help.append(
    el("p", textFor(copy, "stock_hint", "Stock is manually recorded."), "sub"),
  );
  help.append(
    el("p", textFor(copy, "expiry_hint", "One expiry date per item."), "sub"),
  );
  if (parent) {
    help.append(
      el(
        "p",
        textFor(copy, "private_note_hint", "Notes are parent-private."),
        "sub",
      ),
    );
  }
  list.append(help);
  body.append(list);

  if (archived.length) {
    const archive = el("details", null, "pantry-archive");
    archive.append(el("summary", textFor(copy, "archived", "Archived items")));
    for (const item of archived) {
      const row = el("div", null, "item");
      row.dataset.pantryArchived = item.id;
      row.append(
        el("strong", item.name),
        el("div", `${item.quantity} ${item.unit}`, "sub"),
      );
      archive.append(row);
    }
    body.append(archive);
  }

  if (parent) {
    const section = el("section", null, "pantry-suggestions");
    section.append(
      el("h3", textFor(copy, "suggestions", "Shopping suggestions")),
    );
    section.append(
      el(
        "p",
        textFor(copy, "suggestion_hint", "Parent review required."),
        "sub",
      ),
    );
    if (!suggestions.length) {
      section.append(
        el(
          "p",
          textFor(copy, "no_suggestions", "No pending suggestions."),
          "sub",
        ),
      );
    }
    for (const suggestion of suggestions) {
      const suggestionId = suggestion.id;
      const suggestionRevision = suggestion.revision;
      const source =
        items.find((item) => item.id === suggestion.pantry_id) ||
        archived.find((item) => item.id === suggestion.pantry_id);
      const row = el("div", null, "item");
      row.dataset.pantrySuggestion = suggestionId;
      row.append(
        el("strong", source?.name || textFor(copy, "items", "Pantry item")),
        el("div", `${suggestion.quantity} ${suggestion.unit}`, "sub"),
      );
      if (suggestion.status === "open") {
        const actions = el("div", null, "actions");
        actions.append(
          localButton(textFor(copy, "accept", "Add to shopping list"), () =>
            openDraft(
              {
                type: "suggestion_accept",
                title: source?.name || textFor(copy, "items", "Pantry item"),
                amount: `${suggestion.quantity} ${suggestion.unit}`,
                suggestionId,
                revision: suggestionRevision,
                values: {},
              },
              () => Boolean(freshSuggestion(suggestionId, suggestionRevision)),
            ),
          ),
          localButton(textFor(copy, "dismiss", "Dismiss"), () =>
            openDraft(
              {
                type: "suggestion_dismiss",
                title: source?.name || textFor(copy, "items", "Pantry item"),
                amount: `${suggestion.quantity} ${suggestion.unit}`,
                suggestionId,
                revision: suggestionRevision,
                values: { reason: "" },
              },
              () => Boolean(freshSuggestion(suggestionId, suggestionRevision)),
            ),
          ),
        );
        row.append(actions);
      } else if (suggestion.status === "accepted") {
        row.append(
          el(
            "p",
            `${textFor(copy, "status_accepted", "Added to the shopping list")}. ${textFor(copy, "suggestion_hint", "Not ordered automatically.")}`,
            "notice",
          ),
        );
      } else if (suggestion.status === "covered") {
        row.append(
          el(
            "p",
            `${textFor(copy, "status_covered", "Already on the shopping list")}. ${textFor(copy, "suggestion_hint", "Not ordered automatically.")}`,
            "notice",
          ),
        );
      } else {
        row.append(
          el(
            "p",
            textFor(copy, `status_${suggestion.status}`, suggestion.status),
            "sub",
          ),
        );
      }
      section.append(row);
    }
    body.append(section);
  }

  const draft = card._pantryDraft;
  if (!draft) return;
  const form = el("form", null, "item pantry-form");
  form.dataset.pantryForm = draft.type;
  form.append(
    el("h3", draft.title || textFor(copy, "new_item", "Add pantry item")),
  );
  if (draft.amount) form.append(el("p", draft.amount, "sub"));
  const exactItem = draft.itemId
    ? freshItem(draft.itemId, draft.revision)
    : null;
  const projectedItem = draft.itemId
    ? (card._data?.pantry?.items || []).find(
        (value) => value.id === draft.itemId,
      )
    : null;
  const exactSuggestion = draft.suggestionId
    ? freshSuggestion(draft.suggestionId, draft.revision)
    : null;
  if (
    (draft.itemId && !exactItem && !draft.pending) ||
    (draft.suggestionId && !exactSuggestion && !draft.pending)
  ) {
    card._pantryDraft = null;
    card._actionError = "conflict";
    return;
  }
  const item = exactItem || projectedItem;
  if (!draft.values) {
    draft.values = draft.type === "edit" ? itemValues(item) : {};
  }

  if (draft.type === "new" || draft.type === "edit") {
    const original = draft.type === "edit" ? snapshot(item) : null;
    const values = draft.values;
    const name = inputField(form, copy, "name", "Name", values.name);
    name.maxLength = 200;
    name.required = true;
    const unit = inputField(form, copy, "unit", "Unit", values.unit);
    unit.maxLength = 32;
    unit.required = true;
    inputField(
      form,
      copy,
      "quantity",
      "Quantity",
      values.quantity ?? "0",
      "text",
    );
    inputField(
      form,
      copy,
      "minimum_quantity",
      "Minimum quantity",
      values.minimum_quantity ?? "0",
      "text",
    );
    const category = inputField(
      form,
      copy,
      "category",
      "Category",
      values.category,
    );
    category.maxLength = 80;
    const location = inputField(
      form,
      copy,
      "location",
      "Location",
      values.location,
    );
    location.maxLength = 80;
    const note = inputField(
      form,
      copy,
      "note",
      "Private parent note",
      values.note,
    );
    note.maxLength = 500;
    inputField(
      form,
      copy,
      "expires_on",
      "Expiry date",
      values.expires_on || "",
      "date",
    );
    if (original) {
      const reason = reasonField(form, copy);
      reason.value = values.reason || "";
      reason.required = false;
    }
    const remember = rememberForm(form, draft, stale);
    appendSubmit(
      form,
      card,
      copy,
      draft.pending
        ? textFor(copy, "retry", "Retry")
        : textFor(copy, "save", "Save"),
      closeDraft,
    );
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      if (stale() || !form.isConnected || card._writing) return;
      try {
        remember();
        const payload =
          draft.pending?.payload || payloadForItem(draft.values, original);
        run("pantry.item_save", payload, () =>
          draft.type === "new"
            ? parent
            : Boolean(freshItem(draft.itemId, draft.revision)),
        );
      } catch (error) {
        card._actionError = errorKey(error);
        card.render();
      }
    });
  } else if (draft.type === "stock") {
    inputField(
      form,
      copy,
      "quantity",
      "Quantity",
      draft.values.quantity,
      "text",
    );
    const reason = reasonField(form, copy);
    reason.value = draft.values.reason || "";
    const remember = rememberForm(form, draft, stale);
    appendSubmit(
      form,
      card,
      copy,
      draft.pending
        ? textFor(copy, "retry", "Retry")
        : textFor(copy, "save", "Save"),
      closeDraft,
    );
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      if (stale() || !form.isConnected || card._writing) return;
      try {
        remember();
        const values = draft.values;
        const payload = draft.pending?.payload || {
          id: draft.itemId,
          revision: draft.revision,
          quantity: quantity(values.quantity, "quantity"),
          reason: bounded(values.reason, "reason", 500, true),
        };
        run("pantry.stock_set", payload, () =>
          Boolean(freshItem(draft.itemId, draft.revision)),
        );
      } catch (error) {
        card._actionError = errorKey(error);
        card.render();
      }
    });
  } else if (draft.type === "archive") {
    form.append(
      el("p", textFor(copy, "archive", "Archive this pantry item?"), "notice"),
    );
    const reason = reasonField(form, copy);
    reason.value = draft.values.reason || "";
    const remember = rememberForm(form, draft, stale);
    appendSubmit(
      form,
      card,
      copy,
      draft.pending
        ? textFor(copy, "retry", "Retry")
        : textFor(copy, "archive", "Archive"),
      closeDraft,
    );
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      if (stale() || !form.isConnected || card._writing) return;
      try {
        remember();
        const values = draft.values;
        const payload = draft.pending?.payload || {
          id: draft.itemId,
          revision: draft.revision,
          reason: bounded(values.reason, "reason", 500, true),
        };
        run("pantry.item_archive", payload, () =>
          Boolean(freshItem(draft.itemId, draft.revision)),
        );
      } catch (error) {
        card._actionError = errorKey(error);
        card.render();
      }
    });
  } else if (
    draft.type === "suggestion_accept" ||
    draft.type === "suggestion_dismiss"
  ) {
    const dismiss = draft.type === "suggestion_dismiss";
    form.append(
      el(
        "p",
        dismiss
          ? textFor(copy, "dismiss", "Dismiss this shopping suggestion?")
          : textFor(
              copy,
              "suggestion_hint",
              "Add this amount to the shopping list? It will not be ordered.",
            ),
        "notice",
      ),
    );
    if (dismiss) {
      const reason = reasonField(form, copy);
      reason.value = draft.values.reason || "";
    }
    const remember = rememberForm(form, draft, stale);
    appendSubmit(
      form,
      card,
      copy,
      draft.pending
        ? textFor(copy, "retry", "Retry")
        : textFor(copy, dismiss ? "dismiss" : "accept", "Confirm"),
      closeDraft,
    );
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      if (stale() || !form.isConnected || card._writing) return;
      try {
        remember();
        const values = draft.values;
        const payload = draft.pending?.payload || {
          id: draft.suggestionId,
          revision: draft.revision,
          ...(dismiss
            ? { reason: bounded(values.reason, "reason", 500, true) }
            : {}),
        };
        run(
          dismiss ? "pantry.suggestion_dismiss" : "pantry.suggestion_accept",
          payload,
          () => Boolean(freshSuggestion(draft.suggestionId, draft.revision)),
        );
      } catch (error) {
        card._actionError = errorKey(error);
        card.render();
      }
    });
  }
  if (draft.pending) {
    for (const control of form.querySelectorAll("input,select,textarea"))
      control.disabled = true;
  }
  formHost.append(form);
}
