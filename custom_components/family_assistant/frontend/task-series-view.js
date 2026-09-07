/* Full recurring-task editor with frozen identity lineage and exact retries. */

import { TASK_SERIES_COPY } from "./task-series-copy.js";
import {
  RECURRENCE_COPY,
  makeRecurrenceDraft,
  recurrencePayload,
  renderRecurrence,
} from "./recurrence-form.js";

const PARENTS = new Set(["owner", "parent"]);
const CLOCK = /^(?:[01]\d|2[0-3]):[0-5]\d$/;
const INTEGER = /^-?(?:0|[1-9]\d*)$/;
const node = (tag, value, className) => {
  const result = document.createElement(tag);
  if (value !== undefined && value !== null) result.textContent = String(value);
  if (className) result.className = className;
  return result;
};
const clone = (value) => JSON.parse(JSON.stringify(value));
const freeze = (value) => {
  if (!value || typeof value !== "object" || Object.isFrozen(value))
    return value;
  Object.freeze(value);
  for (const child of Object.values(value)) freeze(child);
  return value;
};

const STYLE = `
  .task-series{display:grid;gap:12px}.task-series-list,.task-series-form,.task-series-review{display:grid;gap:10px;min-width:0}
  .task-series-row{display:grid;gap:6px;padding:10px;border:1px solid var(--divider-color,#ddd);border-radius:10px;min-width:0}
  .task-series-row p,.task-series-form p,.task-series-review p{margin:0;overflow-wrap:anywhere}.task-series-actions{display:flex;gap:8px;flex-wrap:wrap}
  .task-series-form>fieldset,.task-series-members{display:grid;grid-template-columns:minmax(0,1fr);gap:8px;margin:0;padding:10px;min-width:0}
  .task-series-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.task-series-fields>.wide{grid-column:1/-1}
  .task-series-form label{display:grid;gap:4px;min-width:0}.task-series-check{display:flex!important;align-items:flex-start;gap:8px!important}
  .task-series-check input{flex:0 0 auto;margin-top:3px}.task-series-review dl{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:6px 10px;margin:0}
  .task-series-review dd{margin:0;white-space:pre-wrap;overflow-wrap:anywhere}.task-series-review dt{font-weight:600}.task-series-warning{padding:8px;border-inline-start:4px solid var(--warning-color,#d97706)}
  .task-series-unavailable{display:flex;gap:8px;align-items:center;justify-content:space-between}.task-series-unavailable button{flex:0 0 auto}
  .task-series .recurrence-fieldset{display:block;min-width:0}.task-series .recurrence-fieldset>*+*{margin-top:10px}.task-series .recurrence-row,.task-series .recurrence-weekdays{display:grid;grid-template-columns:minmax(0,1fr);gap:6px}
  @media(max-width:560px){.task-series-fields,.task-series-review dl{grid-template-columns:minmax(0,1fr)}.task-series-fields>.wide{grid-column:auto}.task-series-review dd{margin-bottom:5px}.task-series-actions>button{width:100%}.task-series-unavailable{align-items:stretch;flex-direction:column}}
`;

function language(card) {
  return String(card?._config?.language || card?._hass?.language || "en").split(
    /[-_]/,
  )[0];
}
function copy(card) {
  return TASK_SERIES_COPY[language(card)] || TASK_SERIES_COPY.en;
}
function validRevision(value) {
  return Number.isSafeInteger(value) && value >= 1;
}
function members(card) {
  return Array.isArray(card?._data?.members) ? card._data.members : [];
}
function member(card, id) {
  return members(card).find((item) => item?.id === id) || null;
}
function currentMember(card, id) {
  const item = member(card, id);
  return item?.active === true &&
    item.role !== "guest" &&
    validRevision(item.revision)
    ? item
    : null;
}
function seriesRows(card) {
  return Array.isArray(card?._data?.task_series) ? card._data.task_series : [];
}
function series(card, id) {
  return seriesRows(card).find((item) => item?.id === id) || null;
}
function modules(card) {
  return Array.isArray(card?._data?.settings?.modules)
    ? card._data.settings.modules
    : [];
}
function timezone(card) {
  return card?._data?.settings?.timezone || null;
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
function localDate(zone) {
  if (!validTimezone(zone)) return "";
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: zone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const value = Object.fromEntries(
    parts.map((part) => [part.type, part.value]),
  );
  return `${value.year}-${value.month}-${value.day}`;
}
function access(card) {
  const data = card?._data;
  const actor = member(card, data?.actor);
  const zone = timezone(card);
  if (
    !PARENTS.has(data?.role) ||
    actor?.active !== true ||
    actor.role !== data.role ||
    !validRevision(actor.revision) ||
    !modules(card).includes("tasks") ||
    !validTimezone(zone)
  )
    return null;
  return {
    entry: card._entry,
    generation: card._generation,
    haUser: card?._hass?.user?.id ?? null,
    actor: data.actor,
    role: data.role,
    actorRevision: actor.revision,
    timezone: zone,
  };
}
function sameAccess(card, expected) {
  const actual = access(card);
  return Boolean(
    actual && expected && JSON.stringify(actual) === JSON.stringify(expected),
  );
}
function sourceOf(item) {
  return item && validRevision(item.revision)
    ? { id: item.id, revision: item.revision, current: item.current === true }
    : null;
}
function sameSource(item, expected) {
  return Boolean(
    item &&
    expected &&
    item.id === expected.id &&
    item.revision === expected.revision &&
    item.current === expected.current,
  );
}
function snapshotMember(card, id) {
  const value = currentMember(card, id);
  return value
    ? { id: value.id, revision: value.revision, name: value.name || "" }
    : null;
}
function sameMember(card, expected) {
  const value = snapshotMember(card, expected?.id);
  return Boolean(
    value &&
    expected &&
    value.id === expected.id &&
    value.revision === expected.revision,
  );
}
function creatorSnapshot(card, row) {
  if (!row) return snapshotMember(card, card?._data?.actor);
  const value = member(card, row.creator);
  return value?.active === true &&
    PARENTS.has(value.role) &&
    validRevision(value.revision)
    ? { id: value.id, revision: value.revision, name: value.name || "" }
    : null;
}
function sameCreator(card, expected) {
  const value = member(card, expected?.id);
  return Boolean(
    expected &&
    value?.active === true &&
    PARENTS.has(value.role) &&
    value.revision === expected.revision,
  );
}
function canonicalRow(item) {
  return {
    title: item?.title,
    assignees: item?.assignees,
    assignee_revisions: item?.assignee_revisions,
    creator_revision: item?.creator_revision,
    rotation: item?.rotation,
    rule: item?.rule,
    due_time: item?.due_time,
    report_type: item?.report_type ?? "text",
    checklist: item?.checklist ?? [],
    enabled: item?.enabled,
    reminder_minutes: item?.deadline_policy?.reminder_minutes ?? 60,
    grace_minutes: item?.deadline_policy?.grace_minutes ?? 30,
    penalty: item?.deadline_policy?.penalty ?? 0,
  };
}
function canonicalPayload(payload) {
  const result = clone(payload);
  for (const key of ["id", "revision", "actor_revision"]) delete result[key];
  return result;
}
function stable(value) {
  if (Array.isArray(value)) return value.map(stable);
  if (value && typeof value === "object")
    return Object.fromEntries(
      Object.keys(value)
        .sort()
        .map((key) => [key, stable(value[key])]),
    );
  return value;
}
function sameCanonical(item, payload, revision) {
  return Boolean(
    item &&
    item.revision === revision &&
    JSON.stringify(stable(canonicalRow(item))) ===
      JSON.stringify(stable(canonicalPayload(payload))),
  );
}
function memberPinsCurrent(card, draft) {
  return Boolean(
    draft.creator &&
    sameCreator(card, draft.creator) &&
    (draft.assigneeSnapshots || []).every((item) => sameMember(card, item)),
  );
}
function pendingAllowed(card, draft) {
  if (!sameAccess(card, draft?.access) || !draft?.pending) return false;
  if (draft.intent === "save") {
    if (!draft.source) {
      const known = new Set(draft.baseline || []);
      const added = seriesRows(card).filter((item) => !known.has(item.id));
      if (!added.length) return memberPinsCurrent(card, draft);
      return added.length === 1 && sameCanonical(added[0], draft.payload, 1);
    }
    const current = series(card, draft.source.id);
    if (sameSource(current, draft.source))
      return memberPinsCurrent(card, draft);
    return sameCanonical(current, draft.payload, draft.source.revision + 1);
  }
  if (draft.intent === "toggle") {
    const current = series(card, draft.source.id);
    if (sameSource(current, draft.source)) return true;
    return Boolean(
      current &&
      current.revision === draft.source.revision + 1 &&
      current.enabled === draft.payload.enabled,
    );
  }
  return false;
}
function draftAllowed(card, draft) {
  if (!sameAccess(card, draft?.access)) return false;
  if (draft?.pending) return pendingAllowed(card, draft);
  if (draft.intent === "save") {
    const sourceOkay =
      !draft.source || sameSource(series(card, draft.source.id), draft.source);
    return (
      sourceOkay &&
      (!draft.creator || sameCreator(card, draft.creator)) &&
      (draft.assigneeSnapshots || []).every((item) => sameMember(card, item))
    );
  }
  if (draft.intent === "toggle")
    return sameSource(series(card, draft.source.id), draft.source);
  return false;
}

function projection(data) {
  return {
    actor: data?.actor ?? null,
    role: data?.role ?? null,
    timezone: data?.settings?.timezone ?? null,
    modules: (data?.settings?.modules || []).filter((item) => item === "tasks"),
    members: (data?.members || []).map(
      ({ id, name, role, active, revision }) => ({
        id,
        name,
        role,
        active,
        revision,
      }),
    ),
    series: data?.task_series ?? [],
  };
}
export function reconcileTaskSeriesRefresh(card, previousData) {
  if (!card) return false;
  const changed =
    JSON.stringify(projection(previousData)) !==
    JSON.stringify(projection(card._data));
  let force =
    changed && Boolean(card.shadowRoot?.querySelector(".task-series"));
  if (card._taskSeriesDraft && !draftAllowed(card, card._taskSeriesDraft)) {
    card._taskSeriesDraft = null;
    card._actionError = "conflict";
    force = true;
  }
  return force;
}

function button(card, label, action, primary = false) {
  const result = node("button", label, primary ? "primary" : "");
  result.type = "button";
  result.disabled = Boolean(card._writing);
  result.addEventListener("click", action);
  return result;
}
function field(label, input, className) {
  const wrap = node("label", null, className);
  wrap.append(node("span", label), input);
  return wrap;
}
function input(type, value, name) {
  const result = node("input");
  Object.assign(result, {
    type,
    value: value == null ? "" : String(value),
    name,
  });
  return result;
}
function selectField(label, name, value, choices) {
  const select = node("select");
  select.name = name;
  for (const [key, text] of choices) {
    const option = node("option", text);
    option.value = key;
    option.selected = key === value;
    select.append(option);
  }
  return field(label, select);
}
function safeText(raw, maximum, required = true) {
  if (typeof raw !== "string" || raw.length > maximum)
    throw new Error("validation");
  const value = raw.trim();
  if (required && !value) throw new Error("validation");
  return value;
}
function strictInteger(raw, minimum, maximum) {
  const value = String(raw).trim();
  if (!INTEGER.test(value)) throw new Error("validation");
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed) || parsed < minimum || parsed > maximum)
    throw new Error("validation");
  return parsed;
}
function checklist(raw) {
  if (typeof raw !== "string") throw new Error("validation");
  const lines = raw.split(/\r?\n/).filter((line) => line.trim());
  if (lines.length > 50 || lines.some((line) => line.length > 200))
    throw new Error("validation");
  return lines.map((line) => line.trim());
}
function makeValues(card, row) {
  const rule = makeRecurrenceDraft(row?.rule || null, {
    frequency: "weekly",
    interval: 1,
    start_date: localDate(timezone(card)),
    time: "07:00",
    timezone: timezone(card),
    weekdays: [0],
    catchup_hours: 24,
  });
  rule.enabled = true;
  return {
    title: row?.title || "",
    assignees: [...(row?.assignees || [])],
    rotation: row?.rotation === true,
    enabled: row?.enabled !== false,
    rule,
    due_time: row?.due_time || "20:00",
    report_type: row?.report_type || "text",
    checklist: [...(row?.checklist || [])],
    checklistText: (row?.checklist || []).join("\n"),
    reminder_minutes: row?.deadline_policy?.reminder_minutes ?? 60,
    grace_minutes: row?.deadline_policy?.grace_minutes ?? 30,
    penalty: row?.deadline_policy?.penalty ?? 0,
  };
}
function openEditor(card, row = null) {
  const accessValue = access(card);
  const creator = creatorSnapshot(card, row);
  if (!accessValue) return;
  const values = makeValues(card, row);
  const assigneeSnapshots = values.assignees
    .map((id) => snapshotMember(card, id))
    .filter(Boolean);
  card._taskSeriesDraft = {
    intent: "save",
    access: freeze(accessValue),
    source: row ? freeze(sourceOf(row)) : null,
    creator: creator ? freeze(creator) : null,
    creatorId: row?.creator || accessValue.actor,
    assigneeSnapshots,
    values,
    baseline: seriesRows(card).map((item) => item.id),
  };
  card._actionError = null;
  card.render();
}
function openToggle(card, row) {
  const accessValue = access(card);
  if (
    !accessValue ||
    !sourceOf(row) ||
    (row.enabled === false && row.current !== true)
  )
    return;
  const c = copy(card);
  const payload = freeze({
    id: row.id,
    revision: row.revision,
    actor_revision: accessValue.actorRevision,
    enabled: !row.enabled,
  });
  card._taskSeriesDraft = {
    intent: "toggle",
    access: freeze(accessValue),
    source: freeze(sourceOf(row)),
    payload,
    review: freeze({
      title: row.title,
      action: payload.enabled ? c.enable : c.disable,
    }),
    confirmed: false,
  };
  card._actionError = null;
  card.render();
}
function cancel(card) {
  card._taskSeriesDraft = null;
  card._actionError = null;
  card.render();
}
function guardedCancel(card, draft, element) {
  if (
    !element?.isConnected ||
    card._writing ||
    card._taskSeriesDraft !== draft ||
    !sameAccess(card, draft.access)
  )
    return;
  cancel(card);
}
function stale(card, draft, element) {
  if (!element?.isConnected || card._taskSeriesDraft !== draft || card._writing)
    return true;
  if (!draftAllowed(card, draft)) {
    card._taskSeriesDraft = null;
    card._actionError = "conflict";
    card.render();
    return true;
  }
  return false;
}
function showError(card, draft, code = "validation") {
  draft.error = code;
  card.render();
}

function editor(card, section, draft) {
  const c = copy(card);
  const form = node("form", null, "task-series-form");
  form.append(node("h3", draft.source ? c.edit : c.add));
  if (draft.source && draft.source.current === false)
    form.append(node("p", c.staleHelp, "task-series-warning"));
  if (!draft.creator)
    form.append(node("p", c.creatorUnavailable, "task-series-warning"));
  else
    form.append(
      node(
        "p",
        `${c.creator}: ${draft.creator.name} · ${c.version} ${draft.creator.revision}`,
        "sub",
      ),
    );
  if (draft.error) {
    const alert = node("p", c[draft.error] || c.validation, "notice");
    alert.role = "alert";
    form.append(alert);
  }
  const fields = node("div", null, "task-series-fields");
  const title = input("text", draft.values.title, "title");
  title.required = true;
  title.maxLength = 500;
  fields.append(field(c.title, title, "wide"));
  const due = input("time", draft.values.due_time, "due_time");
  due.required = true;
  fields.append(field(c.dueTime, due));
  fields.append(
    selectField(c.reportType, "report_type", draft.values.report_type, [
      ["text", c.reportText],
      ["photo", c.reportPhoto],
      ["none", c.reportNone],
    ]),
  );
  const reminder = input(
    "number",
    draft.values.reminder_minutes,
    "reminder_minutes",
  );
  Object.assign(reminder, {
    min: "0",
    max: "10080",
    step: "1",
    required: true,
  });
  const grace = input("number", draft.values.grace_minutes, "grace_minutes");
  Object.assign(grace, { min: "0", max: "1440", step: "1", required: true });
  const penalty = input("number", draft.values.penalty, "penalty");
  Object.assign(penalty, { min: "-10", max: "0", step: "1", required: true });
  fields.append(
    field(c.reminder, reminder),
    field(c.grace, grace),
    field(c.penalty, penalty),
  );
  const text = node("textarea");
  text.name = "checklist";
  text.rows = 5;
  text.value = draft.values.checklistText;
  fields.append(field(c.checklist, text, "wide"));
  form.append(fields);

  const people = node("fieldset", null, "task-series-members");
  people.append(node("legend", c.assignees));
  const selected = new Set(draft.values.assignees);
  for (const item of members(card).filter(
    (value) =>
      value.active === true &&
      value.role !== "guest" &&
      validRevision(value.revision),
  )) {
    const label = node("label", null, "task-series-check");
    const box = input("checkbox", "", "assignees");
    box.value = item.id;
    box.checked = selected.has(item.id);
    label.append(
      box,
      node("span", `${item.name} · ${c.version} ${item.revision}`),
    );
    people.append(label);
    box.addEventListener("change", () => {
      if (stale(card, draft, form)) return;
      if (box.checked) {
        if (!draft.values.assignees.includes(item.id))
          draft.values.assignees.push(item.id);
        if (!draft.assigneeSnapshots.some((pin) => pin.id === item.id))
          draft.assigneeSnapshots.push(freeze(snapshotMember(card, item.id)));
      } else {
        draft.values.assignees = draft.values.assignees.filter(
          (id) => id !== item.id,
        );
        draft.assigneeSnapshots = draft.assigneeSnapshots.filter(
          (pin) => pin.id !== item.id,
        );
      }
    });
  }
  for (const id of draft.values.assignees.filter(
    (value) => !currentMember(card, value),
  )) {
    const row = node("div", null, "task-series-unavailable");
    row.append(node("span", c.unavailableMember));
    row.append(
      button(card, c.removeUnavailable, () => {
        if (stale(card, draft, row)) return;
        draft.values.assignees = draft.values.assignees.filter(
          (value) => value !== id,
        );
        draft.assigneeSnapshots = draft.assigneeSnapshots.filter(
          (value) => value.id !== id,
        );
        card.render();
      }),
    );
    people.append(row);
  }
  form.append(people);
  const rotationLabel = node("label", null, "task-series-check");
  const rotation = input("checkbox", "", "rotation");
  rotation.checked = draft.values.rotation;
  rotationLabel.append(rotation, node("span", c.rotation));
  form.append(rotationLabel);
  const enabledLabel = node("label", null, "task-series-check");
  const enabled = input("checkbox", "", "enabled");
  enabled.checked = draft.values.enabled;
  enabledLabel.append(enabled, node("span", c.enabled));
  form.append(enabledLabel);

  const sync = (control, eventName, update) => {
    control.addEventListener(eventName, () => {
      if (stale(card, draft, form)) return;
      update();
    });
  };
  sync(title, "input", () => {
    draft.values.title = title.value;
  });
  sync(due, "input", () => {
    draft.values.due_time = due.value;
  });
  const report = form.querySelector('select[name="report_type"]');
  sync(report, "change", () => {
    draft.values.report_type = report.value;
  });
  sync(reminder, "input", () => {
    draft.values.reminder_minutes = reminder.value;
  });
  sync(grace, "input", () => {
    draft.values.grace_minutes = grace.value;
  });
  sync(penalty, "input", () => {
    draft.values.penalty = penalty.value;
  });
  sync(text, "input", () => {
    draft.values.checklistText = text.value;
  });
  sync(rotation, "change", () => {
    draft.values.rotation = rotation.checked;
  });
  sync(enabled, "change", () => {
    draft.values.enabled = enabled.checked;
  });

  const recurrence = node("div");
  form.append(recurrence);
  renderRecurrence(recurrence, draft.values.rule, {
    language: language(card),
    lockedFields: ["enabled"],
    isStale: () => !form.isConnected || !draftAllowed(card, draft),
  });
  form.append(node("p", c.futureOnly, "sub"), node("p", c.photoHelp, "sub"));
  const actions = node("div", null, "task-series-actions");
  const review = node("button", c.reviewAction, "primary");
  review.type = "submit";
  review.disabled = !draft.creator || card._writing;
  actions.append(
    review,
    button(card, c.cancel, () => guardedCancel(card, draft, form)),
  );
  form.append(actions);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (stale(card, draft, form) || !draft.creator) return;
    try {
      const data = new FormData(form);
      const ids = data.getAll("assignees").map(String);
      if (!ids.length || ids.length > 20 || new Set(ids).size !== ids.length)
        throw new Error("validation");
      const pins = ids.map((id) =>
        draft.assigneeSnapshots.find((item) => item.id === id),
      );
      if (pins.some((item) => !item || !sameMember(card, item)))
        throw new Error("staleError");
      const payload = {
        ...(draft.source
          ? { id: draft.source.id, revision: draft.source.revision }
          : {}),
        actor_revision: draft.access.actorRevision,
        creator_revision: draft.creator.revision,
        title: safeText(data.get("title"), 500),
        assignees: ids,
        assignee_revisions: Object.fromEntries(
          pins.map((item) => [item.id, item.revision]),
        ),
        rotation: data.has("rotation"),
        enabled: data.has("enabled"),
        rule: recurrencePayload(draft.values.rule),
        due_time: String(data.get("due_time")),
        report_type: String(data.get("report_type")),
        checklist: checklist(data.get("checklist")),
        reminder_minutes: strictInteger(data.get("reminder_minutes"), 0, 10080),
        grace_minutes: strictInteger(data.get("grace_minutes"), 0, 1440),
        penalty: strictInteger(data.get("penalty"), -10, 0),
      };
      if (
        !CLOCK.test(payload.due_time) ||
        !["text", "photo", "none"].includes(payload.report_type)
      )
        throw new Error("validation");
      draft.values = {
        ...draft.values,
        title: payload.title,
        assignees: ids,
        rotation: payload.rotation,
        enabled: payload.enabled,
        due_time: payload.due_time,
        report_type: payload.report_type,
        checklist: payload.checklist,
        checklistText: payload.checklist.join("\n"),
        reminder_minutes: payload.reminder_minutes,
        grace_minutes: payload.grace_minutes,
        penalty: payload.penalty,
      };
      draft.payload = freeze(payload);
      draft.review = freeze({
        title: payload.title,
        creator: draft.creator.name,
        people: pins.map(
          (item) => `${item.name} · ${c.version} ${item.revision}`,
        ),
        rule: clone(payload.rule),
      });
      draft.confirmed = false;
      draft.error = null;
      card.render();
    } catch (error) {
      showError(
        card,
        draft,
        error.message === "staleError" ? "staleError" : "validation",
      );
    }
  });
  section.append(form);
}

function dlEntry(list, term, detail) {
  list.append(node("dt", term), node("dd", detail));
}
function recurrenceReview(card, list, rule) {
  const rc = RECURRENCE_COPY[language(card)] || RECURRENCE_COPY.en;
  dlEntry(list, rc.frequency, rc[rule.frequency] || rule.frequency);
  dlEntry(list, rc.interval, String(rule.interval));
  dlEntry(list, rc.startDate, rule.start_date);
  dlEntry(list, rc.untilDate, rule.until || "—");
  dlEntry(list, rc.time, rule.time);
  dlEntry(list, rc.timezone, rule.timezone);
  dlEntry(
    list,
    rc.weekdays,
    rule.weekdays.map((day) => rc.dayNamesFull[day]).join(", "),
  );
  dlEntry(list, rc.monthDay, String(rule.month_day));
  dlEntry(list, rc.exceptions, rule.exceptions.join("\n") || "—");
  dlEntry(list, rc.catchupHours, String(rule.catchup_hours));
}
function scheduleLabel(card, rule) {
  const rc = RECURRENCE_COPY[language(card)] || RECURRENCE_COPY.en;
  const frequency = rc[rule.frequency] || rule.frequency;
  const until = rule.until ? ` – ${rule.until}` : "";
  return `${frequency} · ${rule.start_date}${until} · ${rule.time} · ${rule.timezone}`;
}
async function execute(card, draft, root) {
  if (stale(card, draft, root)) return;
  if (!draft.confirmed) {
    draft.error = "validation";
    card.render();
    return;
  }
  if (!draft.pending)
    draft.pending = freeze({
      operation_id: crypto.randomUUID(),
      action:
        draft.intent === "toggle" ? "tasks.series_enable" : "tasks.series_save",
      payload: draft.payload,
    });
  const pending = draft.pending;
  await card.command(pending.action, pending.payload, pending.operation_id);
  if (card._taskSeriesDraft !== draft || !sameAccess(card, draft.access))
    return;
  if (!card._actionError) card._taskSeriesDraft = null;
  card.render();
}
function review(card, section, draft) {
  const c = copy(card);
  const root = node("div", null, "task-series-review");
  const isToggle = draft.intent === "toggle";
  root.append(
    node(
      "h3",
      isToggle
        ? draft.payload.enabled
          ? c.reviewEnable
          : c.reviewDisable
        : c.namedReview.replace("{title}", draft.review.title),
    ),
  );
  if (draft.error) {
    const alert = node("p", c[draft.error] || c.validation, "notice");
    alert.role = "alert";
    root.append(alert);
  }
  if (isToggle) root.append(node("p", draft.review.title));
  else {
    const list = node("dl");
    dlEntry(
      list,
      c.creator,
      `${draft.review.creator} · ${c.version} ${draft.payload.creator_revision}`,
    );
    dlEntry(list, c.people, draft.review.people.join(", "));
    dlEntry(list, c.mode, draft.payload.rotation ? c.rotationMode : c.eachMode);
    dlEntry(list, c.status, draft.payload.enabled ? c.enabled : c.disabled);
    recurrenceReview(card, list, draft.payload.rule);
    dlEntry(list, c.due, draft.payload.due_time);
    dlEntry(
      list,
      c.report,
      c[
        `report${draft.payload.report_type[0].toUpperCase()}${draft.payload.report_type.slice(1)}`
      ] || draft.payload.report_type,
    );
    dlEntry(list, c.checklist, draft.payload.checklist.join("\n") || "—");
    dlEntry(list, c.reminder, String(draft.payload.reminder_minutes));
    dlEntry(list, c.grace, String(draft.payload.grace_minutes));
    dlEntry(list, c.penalty, String(draft.payload.penalty));
    root.append(list);
    root.append(node("p", c.futureOnly, "sub"));
  }
  if (draft.pending) root.append(node("p", c.pending, "task-series-warning"));
  const confirmLabel = node("label", null, "task-series-check");
  const confirm = input("checkbox", "", "confirm");
  confirm.checked = draft.confirmed === true;
  confirm.disabled = Boolean(draft.pending);
  confirmLabel.append(
    confirm,
    node(
      "span",
      isToggle
        ? draft.payload.enabled
          ? c.confirmEnable
          : c.confirmDisable
        : c.confirm,
    ),
  );
  root.append(confirmLabel);
  confirm.addEventListener("change", () => {
    if (!stale(card, draft, root)) draft.confirmed = confirm.checked;
  });
  const actions = node("div", null, "task-series-actions");
  const submitText = draft.pending
    ? c.retry
    : isToggle
      ? draft.payload.enabled
        ? c.applyEnable
        : c.applyDisable
      : c.save;
  actions.append(
    button(card, submitText, () => execute(card, draft, root), true),
    button(card, c.cancel, () => guardedCancel(card, draft, root)),
  );
  root.append(actions);
  section.append(root);
}

function row(card, item) {
  const c = copy(card);
  const result = node("article", null, "task-series-row");
  result.dataset.taskSeriesId = item.id;
  result.append(node("strong", item.title));
  const names = (item.assignees || [])
    .map((id) => member(card, id)?.name)
    .filter(Boolean);
  result.append(
    node(
      "p",
      `${names.join(", ")} · ${item.rotation ? c.rotationMode : c.eachMode}`,
      "sub",
    ),
  );
  result.append(
    node(
      "p",
      `${scheduleLabel(card, item.rule)} → ${c.due} ${item.due_time}`,
      "sub",
    ),
  );
  result.append(
    node(
      "p",
      item.current === true ? c.current : c.needsReview,
      item.current === true ? "sub" : "task-series-warning",
    ),
  );
  if (PARENTS.has(card._data?.role)) {
    const actions = node("div", null, "task-series-actions");
    actions.append(
      button(card, c.edit, () => {
        if (
          !result.isConnected ||
          card._writing ||
          !access(card) ||
          !sameSource(series(card, item.id), sourceOf(item))
        )
          return;
        openEditor(card, series(card, item.id));
      }),
    );
    if (item.enabled || item.current === true)
      actions.append(
        button(card, item.enabled ? c.disable : c.enable, () => {
          if (
            !result.isConnected ||
            card._writing ||
            !access(card) ||
            !sameSource(series(card, item.id), sourceOf(item))
          )
            return;
          openToggle(card, series(card, item.id));
        }),
      );
    result.append(actions);
  }
  return result;
}

export function renderTaskSeries(card, body) {
  const c = copy(card);
  const section = node("section", null, "task-series");
  section.append(node("style", STYLE));
  const guide = node("details");
  guide.append(
    node("summary", c.helpTitle),
    node("p", c.help),
    node("p", c.identityHelp),
    node("p", c.timingHelp),
  );
  section.append(guide);
  const draft = card._taskSeriesDraft;
  if (!modules(card).includes("tasks") || card?._data?.role === "guest") {
    card._taskSeriesDraft = null;
    body.append(section);
    return;
  }
  if (draft) {
    if (!draftAllowed(card, draft)) {
      card._taskSeriesDraft = null;
      card._actionError = "conflict";
    } else if (draft.payload) {
      review(card, section, draft);
      body.append(section);
      return;
    } else {
      editor(card, section, draft);
      body.append(section);
      return;
    }
  }
  if (PARENTS.has(card._data?.role))
    section.append(
      button(
        card,
        c.add,
        () => {
          if (!section.isConnected || card._writing || !access(card)) return;
          openEditor(card);
        },
        true,
      ),
    );
  const rows = seriesRows(card);
  if (!rows.length) section.append(node("p", c.empty, "empty"));
  else {
    const list = node("div", null, "task-series-list");
    for (const item of rows) list.append(row(card, item));
    section.append(list);
  }
  body.append(section);
}
