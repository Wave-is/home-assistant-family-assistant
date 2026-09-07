/* Self-only controls and explicit private previews for family digests. */

import { DIGESTS_COPY } from "./digests-copy.js";
import { TASK_ITEM_COPY } from "./task-items.js";

const ROLES = new Set(["owner", "parent", "adult", "child"]);
const KINDS = ["morning", "evening", "weekly"];
const CLOCK = /^([01]\d|2[0-3]):[0-5]\d$/;
const DATE = /^\d{4}-\d{2}-\d{2}$/;
const DETAIL_KEYS = new Set(["tasks", "calendar", "routines", "school"]);
const COUNT_KEYS = new Set([
  "shopping",
  "pantry_low_stock",
  "pantry_expiring",
  "maintenance_faults",
  "maintenance_services",
  "polls_open",
  "polls_results",
]);
const DAY_MS = 24 * 60 * 60 * 1000;

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

const STYLE = `
  .digests{display:grid;gap:12px}.digest-guide{margin:0}.digest-policy,.digest-self,.digest-editor,.digest-review,.digest-preview{display:grid;gap:8px;min-width:0}
  .digests p,.digests dd,.digest-preview li{overflow-wrap:anywhere}.digest-policy p,.digest-self p,.digest-editor p,.digest-review p,.digest-preview p{margin:0}
  .digest-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.digest-kind{display:grid;gap:5px;padding:10px;border:1px solid var(--divider-color,#ddd);border-radius:10px}
  .digest-editor fieldset{display:grid;grid-template-columns:minmax(0,1fr);gap:8px;margin:0;padding:0;border:0}.digest-editor label,.digest-preview-picker label{display:flex;gap:8px;align-items:center}
  .digest-editor input{flex:0 0 auto}.digest-actions{display:flex;flex-wrap:wrap;gap:8px}.digests .digest-confirm{display:flex;flex-direction:row;justify-content:flex-start;gap:8px;align-items:flex-start}
  .digest-confirm input{flex:0 0 auto;margin-top:3px}.digest-review dl{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:6px 10px;margin:0}.digest-review dt{font-weight:600}.digest-review dd{margin:0}
  .digest-preview-picker{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;align-items:end}.digest-preview-picker label{display:grid;gap:4px}.digest-preview-section{display:grid;gap:6px}.digest-preview-section ul{margin:0;padding-inline-start:20px}
  @media(max-width:600px){.digest-grid{grid-template-columns:minmax(0,1fr)}.digest-preview-picker{grid-template-columns:minmax(0,1fr)}.digest-actions>button,.digest-preview-picker>button{width:100%}.digest-review dl{grid-template-columns:minmax(0,1fr)}.digest-review dd{margin-bottom:4px}}
`;

function languageOf(card) {
  return String(card?._config?.language || card?._hass?.language || "en").split(
    /[-_]/,
  )[0];
}

function copyOf(card) {
  return DIGESTS_COPY[languageOf(card)] || DIGESTS_COPY.en;
}

function taskCopyOf(card) {
  return TASK_ITEM_COPY[languageOf(card)] || TASK_ITEM_COPY.en;
}

function validRevision(value) {
  return Number.isSafeInteger(value) && value >= 1;
}

function validTimezone(value) {
  if (typeof value !== "string" || !value) return false;
  try {
    new Intl.DateTimeFormat("en", { timeZone: value }).format(new Date(0));
    return true;
  } catch (_error) {
    return false;
  }
}

function exactKeys(value, keys) {
  return (
    value &&
    typeof value === "object" &&
    !Array.isArray(value) &&
    JSON.stringify(Object.keys(value).sort()) ===
      JSON.stringify([...keys].sort())
  );
}

function members(card) {
  return Array.isArray(card?._data?.members) ? card._data.members : [];
}

function member(card, id) {
  return members(card).find((item) => item?.id === id) || null;
}

function validPolicy(value) {
  return Boolean(
    exactKeys(value, ["timezone", "morning", "evening", "weekly"]) &&
    validTimezone(value.timezone) &&
    exactKeys(value.morning, ["enabled", "time"]) &&
    typeof value.morning.enabled === "boolean" &&
    CLOCK.test(value.morning.time) &&
    exactKeys(value.evening, ["enabled", "time"]) &&
    typeof value.evening.enabled === "boolean" &&
    CLOCK.test(value.evening.time) &&
    exactKeys(value.weekly, ["enabled", "weekday", "time"]) &&
    typeof value.weekly.enabled === "boolean" &&
    Number.isInteger(value.weekly.weekday) &&
    value.weekly.weekday >= 0 &&
    value.weekly.weekday <= 6 &&
    CLOCK.test(value.weekly.time),
  );
}

function validSelf(value) {
  return Boolean(
    exactKeys(value, [
      "recipient_revision",
      "subscription_revision",
      "morning",
      "evening",
      "weekly",
      "can_edit",
      "health",
    ]) &&
    validRevision(value.recipient_revision) &&
    (value.subscription_revision === null ||
      validRevision(value.subscription_revision)) &&
    KINDS.every((kind) => typeof value[kind] === "boolean") &&
    typeof value.can_edit === "boolean" &&
    ["ok", "attention"].includes(value.health) &&
    (value.subscription_revision !== null ||
      KINDS.every((kind) => value[kind] === false)),
  );
}

function digestData(card) {
  const value = card?._data?.digests;
  return value && typeof value === "object" ? value : null;
}

function selfRow(card) {
  const data = digestData(card);
  const actor = member(card, card?._data?.actor);
  if (
    !exactKeys(data, ["policy", "self"]) ||
    !validPolicy(data.policy) ||
    !validSelf(data.self) ||
    actor?.revision !== data.self.recipient_revision
  )
    return null;
  return data.self;
}

function access(card) {
  const data = card?._data;
  const actor = member(card, data?.actor);
  const self = selfRow(card);
  if (
    !data?.actor ||
    !ROLES.has(data?.role) ||
    actor?.active !== true ||
    actor.role !== data.role ||
    !validRevision(actor.revision) ||
    !Array.isArray(data?.settings?.modules) ||
    !data.settings.modules.includes("digests") ||
    !self
  )
    return null;
  return {
    generation: card._generation,
    entry: card._entry,
    actor: data.actor,
    role: data.role,
    actorRevision: actor.revision,
    policy: clone(digestData(card).policy),
  };
}

function sameAccess(card, expected) {
  const current = access(card);
  return (
    Boolean(current && expected) &&
    JSON.stringify(current) === JSON.stringify(expected)
  );
}

function previewSourcePin(card) {
  const revision = card?._data?.revision;
  const modules = card?._data?.settings?.modules;
  if (
    !Number.isSafeInteger(revision) ||
    revision < 0 ||
    !Array.isArray(modules) ||
    !modules.every((item) => typeof item === "string")
  )
    return null;
  return { revision, modules: [...modules].sort() };
}

function samePreviewSource(card, expected) {
  const current = previewSourcePin(card);
  return Boolean(
    current && expected && JSON.stringify(current) === JSON.stringify(expected),
  );
}

function selfSnapshot(value) {
  return {
    recipient_revision: value.recipient_revision,
    subscription_revision: value.subscription_revision,
    morning: value.morning,
    evening: value.evening,
    weekly: value.weekly,
    can_edit: value.can_edit,
  };
}

function sameSelf(left, right) {
  return Boolean(
    left &&
    right &&
    left.recipient_revision === right.recipient_revision &&
    left.subscription_revision === right.subscription_revision &&
    KINDS.every((kind) => left[kind] === right[kind]) &&
    left.can_edit === right.can_edit,
  );
}

function expectedRevision(source) {
  return source.subscription_revision === null
    ? 1
    : source.subscription_revision + 1;
}

function pendingAllowed(card, draft) {
  if (!sameAccess(card, draft?.access) || !draft?.pending) return false;
  const current = selfRow(card);
  if (
    !current ||
    current.recipient_revision !== draft.source.recipient_revision
  )
    return false;
  return (
    sameSelf(current, draft.source) ||
    (current.subscription_revision === expectedRevision(draft.source) &&
      KINDS.every((kind) => current[kind] === draft.values[kind]))
  );
}

function draftAllowed(card, draft) {
  if (!sameAccess(card, draft?.access)) return false;
  if (draft?.mode === "preview")
    return samePreviewSource(card, draft.sourcePin);
  if (!draft?.source) return false;
  if (draft.pending) return pendingAllowed(card, draft);
  return sameSelf(selfRow(card), draft.source);
}

function projection(data) {
  const digest = data?.digests;
  const actor = Array.isArray(data?.members)
    ? data.members.find((item) => item?.id === data?.actor)
    : null;
  return {
    actor: data?.actor ?? null,
    role: data?.role ?? null,
    module: Array.isArray(data?.settings?.modules)
      ? data.settings.modules.includes("digests")
      : false,
    member: actor
      ? {
          id: actor.id,
          name: actor.name,
          role: actor.role,
          active: actor.active,
          revision: actor.revision,
        }
      : null,
    digests: digest
      ? {
          policy: digest.policy ?? null,
          self: digest.self ?? null,
        }
      : null,
  };
}

export function reconcileDigestsRefresh(card, previousData) {
  if (!card) return false;
  const changed =
    JSON.stringify(projection(previousData)) !==
    JSON.stringify(projection(card._data));
  let force =
    changed &&
    Boolean(card._digestsDraft || card.shadowRoot?.querySelector(".digests"));
  if (card._digestsDraft && !draftAllowed(card, card._digestsDraft)) {
    card._digestsDraft = null;
    card._actionError = "conflict";
    force = true;
  }
  return force;
}

function rawText(value, maximum = 500, allowEmpty = false) {
  if (
    typeof value !== "string" ||
    value.length > maximum ||
    (!allowEmpty && !value.trim())
  )
    throw new Error("invalid_preview");
  return value;
}

function nonnegative(value) {
  if (!Number.isSafeInteger(value) || value < 0)
    throw new Error("invalid_preview");
  return value;
}

function dateValue(value) {
  if (!DATE.test(value)) return null;
  const [year, month, day] = value.split("-").map(Number);
  if (year < 1) return null;
  const parsed = new Date(0);
  parsed.setUTCHours(0, 0, 0, 0);
  parsed.setUTCFullYear(year, month - 1, day);
  if (
    parsed.getUTCFullYear() !== year ||
    parsed.getUTCMonth() !== month - 1 ||
    parsed.getUTCDate() !== day
  )
    return null;
  return parsed.getTime();
}

function inclusiveEnd(value) {
  const parsed = dateValue(value);
  return new Date(parsed - DAY_MS).toISOString().slice(0, 10);
}

function validateRow(key, row) {
  if (key === "tasks") {
    if (!exactKeys(row, ["title", "status", "due_at"]))
      throw new Error("invalid_preview");
    const dueAt = row.due_at === null ? null : rawText(row.due_at, 64);
    if (dueAt !== null && !Number.isFinite(new Date(dueAt).getTime()))
      throw new Error("invalid_preview");
    return {
      title: rawText(row.title),
      status: rawText(row.status, 40),
      due_at: dueAt,
    };
  }
  if (key === "calendar") {
    if (!exactKeys(row, ["title", "start", "all_day"]))
      throw new Error("invalid_preview");
    if (typeof row.all_day !== "boolean") throw new Error("invalid_preview");
    const start = rawText(row.start, 64);
    if (
      (row.all_day && !DATE.test(start)) ||
      (!row.all_day && !Number.isFinite(new Date(start).getTime()))
    )
      throw new Error("invalid_preview");
    return {
      title: rawText(row.title),
      start,
      all_day: row.all_day,
    };
  }
  if (key === "routines") {
    if (!exactKeys(row, ["routine_title", "step_title"]))
      throw new Error("invalid_preview");
    return {
      routine_title: rawText(row.routine_title),
      step_title: rawText(row.step_title),
    };
  }
  if (!exactKeys(row, ["date", "subject", "start", "materials"]))
    throw new Error("invalid_preview");
  if (
    !DATE.test(row.date) ||
    !CLOCK.test(row.start) ||
    !Array.isArray(row.materials) ||
    row.materials.length > 50
  )
    throw new Error("invalid_preview");
  return {
    date: row.date,
    subject: rawText(row.subject),
    start: row.start,
    materials: row.materials.map((item) => rawText(item, 200)),
  };
}

function validatePreview(raw, requestedKind) {
  const start = dateValue(raw?.window_start);
  const end = dateValue(raw?.window_end);
  const expectedDays = requestedKind === "weekly" ? 7 : 1;
  if (
    !exactKeys(raw, [
      "schema",
      "kind",
      "window_start",
      "window_end",
      "sections",
    ]) ||
    raw.schema !== 1 ||
    raw.kind !== requestedKind ||
    start === null ||
    end === null ||
    end - start !== expectedDays * DAY_MS ||
    !Array.isArray(raw.sections) ||
    raw.sections.length > DETAIL_KEYS.size + COUNT_KEYS.size
  )
    throw new Error("invalid_preview");
  const seen = new Set();
  const sections = raw.sections.map((section) => {
    if (
      !exactKeys(section, ["key", "rows", "count", "overflow"]) ||
      typeof section.key !== "string" ||
      (!DETAIL_KEYS.has(section.key) && !COUNT_KEYS.has(section.key)) ||
      seen.has(section.key) ||
      !Array.isArray(section.rows) ||
      section.rows.length > 10
    )
      throw new Error("invalid_preview");
    seen.add(section.key);
    const count = nonnegative(section.count);
    const overflow = nonnegative(section.overflow);
    if (
      count < section.rows.length ||
      overflow > count ||
      (COUNT_KEYS.has(section.key) && section.rows.length !== 0)
    )
      throw new Error("invalid_preview");
    return {
      key: section.key,
      rows: section.rows.map((row) => validateRow(section.key, row)),
      count,
      overflow,
    };
  });
  return deepFreeze({
    schema: 1,
    kind: requestedKind,
    window_start: raw.window_start,
    window_end: raw.window_end,
    sections,
  });
}

function memberName(card, copy) {
  return member(card, card._data.actor)?.name || copy.unavailable_member;
}

function appendDefinition(list, term, description) {
  list.append(node("dt", term), node("dd", description));
}

function policyText(kind, policy, copy) {
  const item = policy[kind];
  const state = item.enabled ? copy.enabled : copy.disabled;
  if (kind === "weekly")
    return `${state} · ${copy[`day_${item.weekday}`]} · ${item.time}`;
  return `${state} · ${copy.at} ${item.time}`;
}

function dateTime(card, value) {
  if (typeof value !== "string" || !value) return null;
  const parsed = new Date(value);
  if (!Number.isFinite(parsed.getTime())) return null;
  try {
    return new Intl.DateTimeFormat(
      card?._config?.language || card?._hass?.language || "en",
      {
        dateStyle: "medium",
        timeStyle: "short",
        timeZone: digestData(card).policy.timezone,
      },
    ).format(parsed);
  } catch (_error) {
    return null;
  }
}

function rowText(card, key, row, copy) {
  if (key === "tasks") {
    const tasks = taskCopyOf(card);
    const status = tasks[`status_${row.status}`] || tasks.status_unknown;
    const due = row.due_at ? dateTime(card, row.due_at) : null;
    return `${row.title} · ${copy.task_status}: ${status}${due ? ` · ${copy.due}: ${due}` : ""}`;
  }
  if (key === "calendar") {
    const start = row.all_day ? copy.all_day : dateTime(card, row.start);
    return `${row.title} · ${start}`;
  }
  if (key === "routines") return `${row.routine_title} · ${row.step_title}`;
  const materials = row.materials.length
    ? ` · ${copy.materials}: ${row.materials.join(", ")}`
    : "";
  return `${row.date} · ${row.subject} · ${row.start}${materials}`;
}

function appendPreview(card, parent, snapshot, copy) {
  parent.append(
    node("h3", `${copy.preview_title}: ${copy[snapshot.kind]}`),
    node(
      "p",
      `${copy.preview_window}: ${snapshot.window_start} – ${inclusiveEnd(snapshot.window_end)}`,
      "sub",
    ),
  );
  if (!snapshot.sections.length) {
    parent.append(node("p", copy.empty_preview, "sub"));
    return;
  }
  for (const section of snapshot.sections) {
    const item = node("section", null, "digest-preview-section");
    item.append(node("strong", `${copy[section.key]}: ${section.count}`));
    if (section.rows.length) {
      const list = node("ul");
      for (const row of section.rows)
        list.append(node("li", rowText(card, section.key, row, copy)));
      item.append(list);
    }
    if (section.overflow)
      item.append(node("p", `+${section.overflow} ${copy.more}`, "sub"));
    parent.append(item);
  }
}

export function renderDigests(card, body) {
  if (!card || !body || !card._data) return;
  const currentAccess = access(card);
  if (!currentAccess) {
    card._digestsDraft = null;
    return;
  }
  if (card._digestsDraft && !draftAllowed(card, card._digestsDraft)) {
    card._digestsDraft = null;
    card._actionError = "conflict";
  }

  const copy = copyOf(card);
  const detached = () => !body.isConnected;
  const guard = (control, draft = null) => {
    if (draft && card._digestsDraft !== draft) return false;
    if (
      !sameAccess(card, draft?.access || currentAccess) ||
      (draft && !draftAllowed(card, draft))
    ) {
      card._digestsDraft = null;
      card._actionError = "conflict";
      if (!detached() && control?.isConnected) card.render();
      return false;
    }
    return (
      !detached() &&
      Boolean(control?.isConnected) &&
      !card._writing &&
      !draft?.loading
    );
  };
  const localButton = (label, action, primary = false, draft = null) => {
    const button = card.button(
      label,
      () => {
        if (guard(button, draft)) action();
      },
      primary,
    );
    button.type = "button";
    return button;
  };
  const close = (draft) => {
    if (!guard(body, draft)) return;
    card._digestsDraft = null;
    card._actionError = null;
    card.render();
  };
  const run = async (draft) => {
    if (!guard(body, draft)) return;
    if (!draft.pending) {
      draft.pending = deepFreeze({
        action: "digests.access_set",
        payload: {
          recipient_revision: draft.source.recipient_revision,
          subscription_revision: draft.source.subscription_revision,
          morning: draft.values.morning,
          evening: draft.values.evening,
          weekly: draft.values.weekly,
        },
        operation_id: crypto.randomUUID(),
      });
    }
    const pending = draft.pending;
    await card.command(pending.action, pending.payload, pending.operation_id);
    if (
      sameAccess(card, draft.access) &&
      card._digestsDraft === draft &&
      !card._actionError
    ) {
      card._digestsDraft = null;
      card.render();
    }
  };
  const requestPreview = async (kind, control) => {
    if (!KINDS.includes(kind) || !guard(control)) return;
    const draft = {
      mode: "preview",
      access: deepFreeze(clone(currentAccess)),
      sourcePin: deepFreeze(previewSourcePin(card)),
      kind,
      loading: true,
      snapshot: null,
    };
    card._digestsDraft = draft;
    card._actionError = null;
    control.disabled = true;
    control.textContent = copy.loading;
    control.setAttribute("aria-busy", "true");
    try {
      const response = await card._hass.callWS({
        type: "family_assistant/digest_preview",
        entry_id: draft.access.entry,
        kind,
      });
      if (
        card._digestsDraft !== draft ||
        !draftAllowed(card, draft) ||
        detached()
      ) {
        if (card._digestsDraft === draft) {
          card._digestsDraft = null;
          if (!detached()) card.render();
        }
        return;
      }
      draft.snapshot = validatePreview(response, kind);
      draft.loading = false;
      card.render();
    } catch (_error) {
      if (card._digestsDraft === draft) {
        card._digestsDraft = null;
        card._actionError = "invalid_field";
        if (!detached()) card.render();
      }
    }
  };

  const section = node("section", null, "digests");
  section.append(node("style", STYLE));
  const guide = node("details", null, "digest-guide");
  guide.append(
    node("summary", copy.guide),
    node("p", copy.help, "sub"),
    node("p", copy.delivery, "sub"),
    node("p", copy.no_effects, "sub"),
    node("p", copy.options_help, "sub"),
  );
  section.append(guide);

  const draft = card._digestsDraft;
  if (draft?.mode === "preview") {
    const preview = node("section", null, "item digest-preview");
    preview.setAttribute("role", "region");
    preview.setAttribute("aria-label", copy.preview_title);
    preview.setAttribute("aria-live", "polite");
    if (draft.loading) preview.append(node("p", copy.loading, "sub"));
    else appendPreview(card, preview, draft.snapshot, copy);
    if (!draft.loading) {
      const actions = node("div", null, "digest-actions");
      actions.append(
        localButton(copy.cancel, () => close(draft), false, draft),
      );
      preview.append(actions);
    }
    section.append(preview);
    body.append(section);
    return;
  }

  if (draft?.mode === "edit") {
    const form = node("form", null, "item digest-editor");
    form.append(node("h3", copy.edit_title));
    const fields = node("fieldset");
    const checks = {};
    for (const kind of KINDS) {
      const label = node("label");
      const input = node("input");
      input.type = "checkbox";
      input.name = kind;
      input.checked = draft.values[kind];
      checks[kind] = input;
      label.append(input, node("span", copy[kind]));
      fields.append(label);
    }
    form.append(fields, node("p", copy.preference_off_hint, "sub"));
    const error = node("p", "", "sub digest-local-error");
    error.setAttribute("role", "alert");
    form.append(error);
    const actions = node("div", null, "digest-actions");
    const submit = localButton(
      copy.continue,
      () => {
        const values = Object.fromEntries(
          KINDS.map((kind) => [kind, checks[kind].checked]),
        );
        if (
          draft.source.subscription_revision === null &&
          !KINDS.some((kind) => values[kind])
        ) {
          error.textContent = copy.choose_one;
          return;
        }
        if (KINDS.every((kind) => values[kind] === draft.source[kind])) {
          error.textContent = copy.no_changes;
          return;
        }
        draft.values = values;
        draft.mode = "review";
        card.render();
      },
      true,
      draft,
    );
    submit.type = "submit";
    actions.append(
      submit,
      localButton(copy.cancel, () => close(draft), false, draft),
    );
    form.append(actions);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      if (!submit.disabled) submit.click();
    });
    section.append(form);
    body.append(section);
    return;
  }

  if (draft?.mode === "review") {
    const review = node("form", null, "item digest-review");
    review.append(node("h3", copy.review_title));
    const details = node("dl");
    appendDefinition(details, copy.person, memberName(card, copy));
    for (const kind of KINDS)
      appendDefinition(
        details,
        copy[kind],
        `${draft.values[kind] ? copy.enabled : copy.disabled} · ${copy.global_policy}: ${policyText(kind, draft.access.policy, copy)}`,
      );
    appendDefinition(
      details,
      copy.recipient_version,
      draft.source.recipient_revision,
    );
    appendDefinition(
      details,
      copy.subscription_version,
      draft.source.subscription_revision === null
        ? copy.absent
        : draft.source.subscription_revision,
    );
    review.append(details);
    const confirmation = node("label", null, "digest-confirm");
    const checkbox = node("input");
    checkbox.type = "checkbox";
    checkbox.name = "confirmed";
    checkbox.required = true;
    checkbox.disabled = Boolean(draft.pending);
    if (draft.pending) checkbox.checked = true;
    confirmation.append(checkbox, node("span", copy.confirm));
    review.append(confirmation);
    const actions = node("div", null, "digest-actions");
    const submit = localButton(
      draft.pending ? copy.retry : copy.save,
      () => run(draft),
      true,
      draft,
    );
    submit.type = "submit";
    submit.disabled = !draft.pending;
    if (!draft.pending)
      checkbox.addEventListener("change", () => {
        if (!guard(checkbox, draft)) return;
        submit.disabled = !checkbox.checked || card._writing;
      });
    actions.append(
      submit,
      localButton(copy.cancel, () => close(draft), false, draft),
    );
    review.append(actions);
    review.addEventListener("submit", (event) => {
      event.preventDefault();
      if (!submit.disabled && guard(review, draft)) run(draft);
    });
    section.append(review);
    body.append(section);
    return;
  }

  const policy = digestData(card).policy;
  const policyCard = node("section", null, "item digest-policy");
  policyCard.append(
    node("h3", copy.global_policy),
    node("p", `${copy.timezone}: ${policy.timezone}`, "sub"),
  );
  const policyGrid = node("div", null, "digest-grid");
  for (const kind of KINDS) {
    const item = node("div", null, "digest-kind");
    item.append(
      node("strong", copy[kind]),
      node("span", policyText(kind, policy, copy)),
    );
    policyGrid.append(item);
  }
  policyCard.append(policyGrid, node("p", copy.options_help, "sub"));
  section.append(policyCard);

  const self = selfRow(card);
  const selfCard = node("section", null, "item digest-self");
  selfCard.append(
    node("h3", copy.your_preferences),
    node("strong", memberName(card, copy)),
  );
  const preferenceGrid = node("div", null, "digest-grid");
  for (const kind of KINDS) {
    const item = node("div", null, "digest-kind");
    item.append(
      node("strong", copy[kind]),
      node("span", self[kind] ? copy.enabled : copy.disabled),
    );
    preferenceGrid.append(item);
  }
  selfCard.append(
    preferenceGrid,
    node(
      "p",
      `${copy.delivery_health}: ${self.health === "ok" ? copy.health_ok : copy.health_attention}`,
      "sub",
    ),
    node("p", copy.preference_off_hint, "sub"),
  );
  if (
    self.can_edit &&
    (self.subscription_revision === null ||
      self.subscription_revision < Number.MAX_SAFE_INTEGER)
  ) {
    const edit = localButton(copy.change, () => {
      const current = selfRow(card);
      if (!guard(edit) || !sameSelf(current, selfSnapshot(self))) return;
      card._digestsDraft = {
        mode: "edit",
        access: deepFreeze(clone(currentAccess)),
        source: deepFreeze(selfSnapshot(current)),
        values: Object.fromEntries(KINDS.map((kind) => [kind, current[kind]])),
        pending: null,
      };
      card._actionError = null;
      card.render();
    });
    selfCard.append(edit);
  } else if (!self.can_edit)
    selfCard.append(node("p", copy.unavailable_action, "sub"));
  section.append(selfCard);

  const preview = node("section", null, "item digest-preview-launcher");
  preview.append(
    node("h3", copy.preview_title),
    node("p", copy.preview_help, "sub"),
  );
  const picker = node("div", null, "digest-preview-picker");
  const label = node("label", copy.preview_kind);
  const select = node("select");
  select.name = "digest_kind";
  select.setAttribute("aria-label", copy.preview_kind);
  for (const kind of KINDS) {
    const option = node("option", copy[kind]);
    option.value = kind;
    select.append(option);
  }
  label.append(select);
  picker.append(label);
  const request = localButton(
    copy.preview,
    () => requestPreview(select.value, request),
    true,
  );
  picker.append(request);
  preview.append(picker);
  section.append(preview);
  body.append(section);
}
