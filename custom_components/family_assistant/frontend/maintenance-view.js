/* Role-scoped household maintenance UI with exact reviewed mutations. */

import { MAINTENANCE_COPY } from "./maintenance-copy.js";
import {
  RECURRENCE_COPY,
  makeRecurrenceDraft,
  recurrencePayload,
  renderRecurrence,
} from "./recurrence-form.js";

const PARENTS = new Set(["owner", "parent"]);
const DATE = /^\d{4}-\d{2}-\d{2}$/;
const CLOCK = /^(?:[01]\d|2[0-3]):[0-5]\d$/;
const QUANTITY = /^(?:0|[1-9]\d{0,6})(?:\.\d{1,3})?$/;

const node = (tag, value, className) => {
  const result = document.createElement(tag);
  if (value !== undefined && value !== null) result.textContent = String(value);
  if (className) result.className = className;
  return result;
};
const clone = (value) => JSON.parse(JSON.stringify(value));
const deepFreeze = (value) => {
  if (!value || typeof value !== "object" || Object.isFrozen(value)) return value;
  Object.freeze(value);
  for (const child of Object.values(value)) deepFreeze(child);
  return value;
};

const STYLE = `
  .maintenance-section,.maintenance-list,.maintenance-form,.maintenance-fields,.maintenance-review{display:grid;gap:12px}
  .maintenance-fields{grid-template-columns:repeat(2,minmax(0,1fr))}.maintenance-fields>.wide{grid-column:1/-1}
  .maintenance-consumable{display:block;min-width:0}.maintenance-consumable>*+*{margin-top:10px}
  .maintenance-consumable-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
  .maintenance-consumable-fields>.wide{grid-column:1/-1}.maintenance-actions{display:flex;gap:8px;flex-wrap:wrap}
  .maintenance-note{white-space:pre-wrap}.maintenance-review ul{margin:6px 0;padding-inline-start:20px}
  .maintenance-review p,.maintenance-form>p{margin:2px 0}.maintenance-form>h3{margin:4px 0 8px}
  .maintenance-assignees{display:grid;grid-template-columns:minmax(0,1fr);gap:6px}.maintenance-section details{min-width:0}
  @media(max-width:520px){.maintenance-fields,.maintenance-consumable-fields{grid-template-columns:minmax(0,1fr)}.maintenance-fields>.wide,.maintenance-consumable-fields>.wide{grid-column:auto}.maintenance-actions>button{flex:1 1 auto}}
`;

function languageOf(card) {
  return (card._config?.language || card._hass?.language || "en").split("-")[0];
}

function copyOf(card) {
  return MAINTENANCE_COPY[languageOf(card)] || MAINTENANCE_COPY.en;
}

function validRevision(value) {
  return Number.isSafeInteger(value) && value >= 1;
}

function maintenanceData(data) {
  const value = data?.maintenance;
  return value && typeof value === "object" ? value : null;
}

function members(card) {
  return Array.isArray(card._data?.members) ? card._data.members : [];
}

function memberById(card, id) {
  return members(card).find((member) => member.id === id);
}

function activeMember(card, id) {
  const member = memberById(card, id);
  return member?.active === true && member.role !== "guest" && validRevision(member.revision)
    ? member
    : null;
}

function actorAccess(card) {
  const data = card?._data;
  const actor = memberById(card, data?.actor);
  if (
    !data?.actor ||
    data.role === "guest" ||
    actor?.active !== true ||
    actor.role !== data.role ||
    !validRevision(actor.revision) ||
    !data.settings?.modules?.includes("maintenance") ||
    !maintenanceData(data)
  )
    return null;
  return {
    generation: card._generation,
    entry: card._entry,
    actor: data.actor,
    role: data.role,
    actorRevision: actor.revision,
  };
}

function sameAccess(card, expected) {
  const current = actorAccess(card);
  return Boolean(current && expected) && JSON.stringify(current) === JSON.stringify(expected);
}

function tasksEnabled(card) {
  return card._data?.settings?.modules?.includes("tasks") === true;
}

function assets(card) {
  return Array.isArray(card._data?.maintenance?.assets)
    ? card._data.maintenance.assets
    : [];
}
function faults(card) {
  return Array.isArray(card._data?.maintenance?.faults)
    ? card._data.maintenance.faults
    : [];
}
function serviceLogs(card) {
  return Array.isArray(card._data?.maintenance?.service_logs)
    ? card._data.maintenance.service_logs
    : [];
}
function services(card) {
  return Array.isArray(card._data?.maintenance?.services)
    ? card._data.maintenance.services
    : [];
}
function assetById(card, id) {
  return assets(card).find((asset) => asset.id === id);
}
function serviceById(card, id) {
  return services(card).find((service) => service.id === id);
}

function sameRecord(left, right) {
  return Boolean(left && right) &&
    left.id === right.id &&
    left.revision === right.revision &&
    (left.status ?? null) === (right.status ?? null);
}

function pantryItems(card) {
  return card._data?.settings?.modules?.includes("pantry") &&
    Array.isArray(card._data?.pantry?.items)
    ? card._data.pantry.items
    : [];
}

function pantryCurrent(card, link, unit) {
  if (!link) return null;
  return pantryItems(card).find(
    (item) =>
      item.id === link.id &&
      item.revision === link.revision &&
      item.status === "active" &&
      item.unit === unit,
  ) || null;
}

function taskById(card, id) {
  return (card._data?.tasks || []).find((task) => task.id === id);
}

function relatedCompletedTasks(card, assetId) {
  const alreadyLogged = new Set(serviceLogs(card).map((log) => log.task_id).filter(Boolean));
  return (card._data?.tasks || []).filter((task) => {
    const source = task?.source;
    return task.status === "completed" &&
      source &&
      ["maintenance_fault", "maintenance_service"].includes(source.kind) &&
      source.asset_id === assetId &&
      !alreadyLogged.has(task.id) &&
      validRevision(task.revision);
  });
}

function memberSnapshot(card, id) {
  const member = activeMember(card, id);
  return member ? { id: member.id, revision: member.revision } : null;
}

function sameMemberSnapshot(card, snapshot) {
  return Boolean(snapshot) &&
    JSON.stringify(memberSnapshot(card, snapshot.id)) === JSON.stringify(snapshot);
}

function draftAllowed(card, draft, exact = true) {
  if (!sameAccess(card, draft?.access)) return false;
  const parent = PARENTS.has(card._data.role);
  if (draft.parent && !parent) return false;
  if (draft.requiresTasks && !tasksEnabled(card)) return false;
  // A dispatched operation may already have committed. Preserve its exact retry
  // across target changes, after current authority/module checks above.
  if (draft.pending) return true;
  const asset = draft.assetId ? assetById(card, draft.assetId) : null;
  switch (draft.intent) {
    case "asset":
      return parent &&
        (!draft.source || (asset?.status === "active" && (!exact || sameRecord(draft.source, asset)))) &&
        (Boolean(draft.values?.responsibleUnavailable) ||
          sameMemberSnapshot(card, draft.responsibleSnapshot));
    case "retire":
      return parent && asset?.status === "active" && (!exact || sameRecord(draft.source, asset));
    case "fault":
      return Boolean(asset?.can_report) && (!exact || sameRecord(draft.source, asset));
    case "log": {
      if (!parent || !asset || (exact && !sameRecord(draft.source, asset))) return false;
      if (!draft.taskSnapshot) return true;
      const task = taskById(card, draft.taskSnapshot.id);
      return Boolean(task) &&
        relatedCompletedTasks(card, draft.assetId).some((item) => item.id === task.id) &&
        (!exact || sameRecord(draft.taskSnapshot, task));
    }
    case "service": {
      if (!parent || asset?.status !== "active" || asset.current !== true ||
          (exact && !sameRecord(draft.assetSource, asset))) return false;
      if (draft.source) {
        const service = serviceById(card, draft.source.id);
        if (!service || (exact && !sameRecord(draft.source, service))) return false;
      }
      return (draft.assigneeSnapshots || []).every((snapshot) => sameMemberSnapshot(card, snapshot));
    }
    case "toggle": {
      if (!parent) return false;
      const service = serviceById(card, draft.source.id);
      if (!service || (exact && !sameRecord(draft.source, service))) return false;
      if (!draft.payload.enabled) return true;
      return service.current === true && asset?.status === "active" && asset.current === true &&
        asset.revision === draft.payload.asset_revision;
    }
    default:
      return false;
  }
}

function refreshProjection(data) {
  const memberRows = (data?.members || []).map(({ id, name, role, active, revision }) => ({
    id, name, role, active, revision,
  }));
  const taskRows = (data?.tasks || []).map(({ id, revision, status, title, assignee, source }) => ({
    id, revision, status, title, assignee, source,
  }));
  const pantryRows = (data?.pantry?.items || []).map(({ id, revision, status, name, unit }) => ({
    id, revision, status, name, unit,
  }));
  return {
    actor: data?.actor ?? null,
    role: data?.role ?? null,
    modules: (data?.settings?.modules || []).filter((name) =>
      ["maintenance", "tasks", "pantry"].includes(name)),
    timezone: data?.settings?.timezone ?? null,
    maintenance: data?.maintenance ?? null,
    members: memberRows,
    tasks: taskRows,
    pantry: pantryRows,
  };
}

export function reconcileMaintenanceRefresh(card, previousData) {
  if (!card) return false;
  const changed = JSON.stringify(refreshProjection(previousData)) !==
    JSON.stringify(refreshProjection(card._data));
  let force = changed && Boolean(
    card._maintenanceDraft || card.shadowRoot?.querySelector(".maintenance-section"),
  );
  if (card._maintenanceDraft && !draftAllowed(
    card,
    card._maintenanceDraft,
    !card._maintenanceDraft.pending,
  )) {
    card._maintenanceDraft = null;
    card._actionError = "conflict";
    force = true;
  }
  return force;
}

function rawText(value, maximum, required = true) {
  if (typeof value !== "string" || value.length > maximum) throw new Error("invalid");
  const result = value.trim();
  if (required && !result) throw new Error("invalid");
  return result;
}

function strictDate(value) {
  if (typeof value !== "string" || !DATE.test(value)) throw new Error("invalid");
  const [year, month, day] = value.split("-").map(Number);
  const parsed = new Date(`${value}T00:00:00Z`);
  if (year < 1 || year > 9999 || Number.isNaN(parsed.valueOf()) ||
      parsed.getUTCFullYear() !== year || parsed.getUTCMonth() + 1 !== month ||
      parsed.getUTCDate() !== day) throw new Error("invalid");
  return value;
}

function strictInteger(value, minimum, maximum) {
  const text = String(value);
  if (!/^(?:0|[1-9]\d*)$/.test(text)) throw new Error("invalid");
  const result = Number(text);
  if (!Number.isSafeInteger(result) || result < minimum || result > maximum)
    throw new Error("invalid");
  return result;
}

function strictQuantity(value) {
  const text = String(value).trim();
  if (!QUANTITY.test(text)) throw new Error("invalid");
  const result = Number(text);
  if (!(result > 0) || result > 1_000_000) throw new Error("invalid");
  return result;
}

function localToday(card) {
  const zone = card._data?.settings?.timezone || "UTC";
  try {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone: zone, year: "numeric", month: "2-digit", day: "2-digit",
    }).formatToParts(new Date());
    const value = Object.fromEntries(parts.map((part) => [part.type, part.value]));
    return `${value.year}-${value.month}-${value.day}`;
  } catch {
    return "";
  }
}

function consumableDraft(card, item = {}) {
  const link = item.pantry ? { id: item.pantry.id, revision: item.pantry.revision } : null;
  return {
    label: item.label || "",
    unit: item.unit || "",
    quantity: item.quantity == null ? "" : String(item.quantity),
    pantry: link,
    pantryUnavailable: link && !pantryCurrent(card, link, item.unit || "") ? link : null,
    pantryDecisionRequired: Boolean(link && !pantryCurrent(card, link, item.unit || "")),
  };
}

function consumablesPayload(card, rows) {
  if (!Array.isArray(rows) || rows.length > 30) throw new Error("invalid");
  const seen = new Set();
  return rows.map((row) => {
    if (row.pantryDecisionRequired) throw new Error("invalid");
    const label = rawText(row.label, 120);
    const unit = rawText(row.unit, 24);
    const identity = `${label.toLocaleLowerCase("en-US")}\u0000${unit}`;
    if (seen.has(identity)) throw new Error("invalid");
    seen.add(identity);
    let pantry = null;
    if (row.pantry) {
      const current = pantryCurrent(card, row.pantry, unit);
      if (!current) throw new Error("invalid");
      pantry = { id: current.id, revision: current.revision };
    }
    return { label, unit, quantity: strictQuantity(row.quantity), pantry };
  });
}

function assetValues(card, record = null) {
  const responsible = record ? memberById(card, record.responsible_member) :
    members(card).find((member) => activeMember(card, member.id));
  const exact = responsible && activeMember(card, responsible.id) &&
    (!record || responsible.revision === record.responsible_member_revision);
  return {
    name: record?.name || "",
    category: record?.category || "",
    location: record?.location || "",
    responsible_member: exact ? responsible.id : null,
    responsibleUnavailable: record && !exact
      ? { id: record.responsible_member, revision: record.responsible_member_revision }
      : null,
    warranty_expires: record?.warranty?.expires_on || "",
    warranty_vendor: record?.warranty?.vendor || "",
    warranty_reference: record?.warranty?.reference || "",
    consumables: (record?.consumables || []).map((item) => consumableDraft(card, item)),
    note: record?.note || "",
    reportable: record?.reportable === true,
  };
}

function assetPayload(card, draft) {
  const responsible = activeMember(card, draft.values.responsible_member);
  if (!responsible || responsible.revision !== draft.responsibleSnapshot?.revision)
    throw new Error("invalid");
  const expires = draft.values.warranty_expires
    ? strictDate(draft.values.warranty_expires)
    : null;
  return {
    ...(draft.source ? { id: draft.source.id, revision: draft.source.revision } : {}),
    name: rawText(draft.values.name, 120),
    category: rawText(draft.values.category, 80, false),
    location: rawText(draft.values.location, 120, false),
    responsible_member: responsible.id,
    responsible_member_revision: responsible.revision,
    warranty: {
      expires_on: expires,
      vendor: rawText(draft.values.warranty_vendor, 120, false),
      reference: rawText(draft.values.warranty_reference, 200, false),
    },
    consumables: consumablesPayload(card, draft.values.consumables),
    note: rawText(draft.values.note, 1000, false),
    reportable: draft.values.reportable === true,
  };
}

function checklistPayload(value) {
  const rows = String(value || "").split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
  if (rows.length > 50 || rows.some((item) => item.length > 200)) throw new Error("invalid");
  return rows;
}

function serviceValues(card, service = null) {
  const selected = [];
  const unavailable = [];
  for (const id of service?.assignees || []) {
    if (activeMember(card, id)) selected.push(id);
    else unavailable.push(id);
  }
  const rule = makeRecurrenceDraft(service?.rule || null, {
    start_date: localToday(card),
    timezone: card._data?.settings?.timezone || "UTC",
    time: "09:00",
  });
  // A maintenance service always has a recurrence; top-level `enabled` controls
  // whether it currently creates tasks.
  rule.enabled = true;
  return {
    title: service?.title || "",
    assignees: selected,
    unavailableAssignees: unavailable,
    assigneeReplacementConfirmed: unavailable.length === 0,
    rotation: service?.rotation === true,
    rule,
    due_time: service?.due_time || "18:00",
    checklist: (service?.checklist || []).join("\n"),
    enabled: service ? service.enabled === true : true,
    reminder_minutes: String(service?.deadline_policy?.reminder_minutes ?? 60),
    grace_minutes: String(service?.deadline_policy?.grace_minutes ?? 30),
  };
}

function servicePayload(card, draft) {
  if (draft.values.unavailableAssignees.length && !draft.values.assigneeReplacementConfirmed)
    throw new Error("invalid");
  if (!Array.isArray(draft.values.assignees) || !draft.values.assignees.length ||
      draft.values.assignees.length > 20) throw new Error("invalid");
  const assignees = draft.values.assignees.map((id) => {
    const member = activeMember(card, id);
    const expected = draft.assigneeSnapshots.find((item) => item.id === id);
    if (!member || member.revision !== expected?.revision) throw new Error("invalid");
    return { id: member.id, revision: member.revision };
  });
  const rule = recurrencePayload(draft.values.rule);
  if (!rule || !CLOCK.test(draft.values.due_time)) throw new Error("invalid");
  return {
    ...(draft.source ? { id: draft.source.id, revision: draft.source.revision } : {}),
    asset_id: draft.assetId,
    asset_revision: draft.assetSource.revision,
    title: rawText(draft.values.title, 500),
    assignees,
    rotation: draft.values.rotation === true,
    rule,
    due_time: draft.values.due_time,
    checklist: checklistPayload(draft.values.checklist),
    enabled: draft.values.enabled === true,
    reminder_minutes: strictInteger(draft.values.reminder_minutes, 0, 10080),
    grace_minutes: strictInteger(draft.values.grace_minutes, 0, 1440),
  };
}

function input(parent, labelText, name, value, type = "text") {
  const label = node("label", labelText);
  const control = document.createElement("input");
  control.name = name;
  control.type = type;
  if (type === "checkbox") control.checked = Boolean(value);
  else control.value = value ?? "";
  label.append(control);
  parent.append(label);
  return control;
}

function textarea(parent, labelText, name, value, hint = "") {
  const label = node("label", labelText);
  const control = document.createElement("textarea");
  control.name = name;
  control.value = value ?? "";
  label.append(control);
  if (hint) label.append(node("span", hint, "sub"));
  parent.append(label);
  return control;
}

function memberName(card, id, copy) {
  return memberById(card, id)?.name || copy.unknown_member;
}

function assetName(card, id) {
  return assetById(card, id)?.name || id;
}

function appendConsumableSummary(parent, rows, copy) {
  if (!rows.length) {
    parent.append(node("p", `${copy.consumables}: ${copy.none}`, "sub"));
    return;
  }
  const list = node("ul");
  for (const item of rows) {
    const pantry = item.pantry ? ` · ${copy.pantry_item}: ${item.pantry.id}` : "";
    list.append(node("li", `${item.label}: ${item.quantity} ${item.unit}${pantry}`));
  }
  parent.append(node("p", copy.consumables), list);
}

function renderRuleSummary(parent, rule, card) {
  const locale = languageOf(card);
  const copy = RECURRENCE_COPY[locale] || RECURRENCE_COPY.en;
  const frequency = copy[rule.frequency] || rule.frequency;
  const weekdays = rule.frequency === "weekly"
    ? ` · ${rule.weekdays.map((day) => copy.dayNamesFull[day]).join(", ")}`
    : "";
  const month = rule.frequency === "monthly" ? ` · ${copy.monthDay}: ${rule.month_day}` : "";
  parent.append(
    node("p", `${frequency} · ${copy.interval}: ${rule.interval}${weekdays}${month}`),
    node("p", `${copy.startDate}: ${rule.start_date} · ${copy.untilDate}: ${rule.until || "—"}`),
    node("p", `${copy.time}: ${rule.time} · ${copy.timezone}: ${rule.timezone}`),
    node("p", `${copy.catchupHours}: ${rule.catchup_hours}`),
    node("p", `${copy.exceptions}: ${rule.exceptions.join(", ") || "—"}`),
  );
}

export function renderMaintenance(card, body) {
  if (!card || !body || !card._data) return;
  const access = actorAccess(card);
  if (!access) {
    card._maintenanceDraft = null;
    return;
  }
  if (card._maintenanceDraft && !draftAllowed(
    card,
    card._maintenanceDraft,
    !card._maintenanceDraft.pending,
  )) {
    card._maintenanceDraft = null;
    card._actionError = "conflict";
  }
  const copy = copyOf(card);
  const parent = PARENTS.has(access.role);
  const detached = () => !body.isConnected;
  const guard = (control, draft = null, exact = true) => {
    if (draft && card._maintenanceDraft !== draft) return false;
    if (!sameAccess(card, draft?.access || access) ||
        (draft && !draftAllowed(card, draft, exact && !draft.pending))) {
      card._maintenanceDraft = null;
      card._actionError = "conflict";
      if (!detached() && control?.isConnected) card.render();
      return false;
    }
    return !detached() && Boolean(control?.isConnected) && !card._writing;
  };
  const button = (label, action, primary = false, draft = null) => {
    const result = card.button(label, () => {
      if (guard(result, draft)) action();
    }, primary);
    result.type = "button";
    return result;
  };
  const close = (draft) => {
    if (!guard(body, draft, false)) return;
    card._maintenanceDraft = null;
    card._actionError = null;
    card.render();
  };
  const run = async (draft) => {
    if (!guard(body, draft, !draft.pending)) return;
    if (!draft.pending) draft.pending = deepFreeze({
      action: draft.action,
      payload: clone(draft.payload),
      operation_id: crypto.randomUUID(),
    });
    const pending = draft.pending;
    await card.command(pending.action, pending.payload, pending.operation_id);
    if (sameAccess(card, draft.access) && card._maintenanceDraft === draft && !card._actionError) {
      card._maintenanceDraft = null;
      card.render();
    }
  };

  const openAsset = (record = null) => {
    if (!parent || !guard(body) || (record && !sameRecord(record, assetById(card, record.id)))) return;
    const values = assetValues(card, record);
    const responsible = values.responsible_member ? activeMember(card, values.responsible_member) : null;
    card._maintenanceDraft = {
      intent: "asset", kind: "asset_edit", parent: true, requiresTasks: false,
      access: deepFreeze(clone(access)), source: record ? deepFreeze(clone(record)) : null,
      assetId: record?.id || null, values,
      responsibleSnapshot: responsible ? deepFreeze(memberSnapshot(card, responsible.id)) : null,
      targetName: record?.name || copy.new_asset,
    };
    card._actionError = null;
    card.render();
  };
  const openRetire = (record) => {
    if (!parent || !guard(body) || record?.status !== "active" ||
        !sameRecord(record, assetById(card, record.id))) return;
    card._maintenanceDraft = {
      intent: "retire", kind: "retire_edit", parent: true, requiresTasks: false,
      access: deepFreeze(clone(access)), source: deepFreeze(clone(record)),
      assetId: record.id, targetName: record.name, reason: "",
    };
    card._actionError = null;
    card.render();
  };
  const openFault = (record) => {
    if (!guard(body) || !tasksEnabled(card) || !record?.can_report ||
        !sameRecord(record, assetById(card, record.id))) return;
    card._maintenanceDraft = {
      intent: "fault", kind: "fault_edit", parent: false, requiresTasks: true,
      access: deepFreeze(clone(access)), source: deepFreeze(clone(record)),
      assetId: record.id, targetName: record.name, summary: "", details: "",
    };
    card._actionError = null;
    card.render();
  };
  const openLog = (record) => {
    if (!parent || !guard(body) || !sameRecord(record, assetById(card, record.id))) return;
    card._maintenanceDraft = {
      intent: "log", kind: "log_edit", parent: true, requiresTasks: false,
      access: deepFreeze(clone(access)), source: deepFreeze(clone(record)),
      assetId: record.id, targetName: record.name, performed_on: localToday(card),
      summary: "", task: null, taskSnapshot: null, consumables: [],
    };
    card._actionError = null;
    card.render();
  };
  const openService = (record, service = null) => {
    if (!parent || !guard(body) || !tasksEnabled(card) || record?.status !== "active" ||
        record.current !== true || !sameRecord(record, assetById(card, record.id)) ||
        (service && !sameRecord(service, serviceById(card, service.id)))) return;
    const values = serviceValues(card, service);
    const snapshots = values.assignees.map((id) => deepFreeze(memberSnapshot(card, id)));
    card._maintenanceDraft = {
      intent: "service", kind: "service_edit", parent: true, requiresTasks: true,
      access: deepFreeze(clone(access)), source: service ? deepFreeze(clone(service)) : null,
      assetSource: deepFreeze(clone(record)), assetId: record.id, targetName: record.name,
      values, assigneeSnapshots: snapshots,
    };
    card._actionError = null;
    card.render();
  };
  const openToggle = (service) => {
    if (!parent || !guard(body) || !tasksEnabled(card) ||
        !sameRecord(service, serviceById(card, service.id))) return;
    const enabling = service.enabled !== true;
    const asset = assetById(card, service.asset_id);
    if (enabling && (!service.current || asset?.current !== true || asset.status !== "active" ||
        asset.revision !== service.asset_revision)) return;
    const payload = deepFreeze({
      id: service.id,
      revision: service.revision,
      enabled: enabling,
      asset_revision: service.asset_revision,
    });
    card._maintenanceDraft = {
      intent: "toggle", kind: "review", parent: true, requiresTasks: true,
      access: deepFreeze(clone(access)), source: deepFreeze(clone(service)),
      assetId: service.asset_id, targetName: service.title,
      payload, action: "maintenance.service_enable", reviewed: false,
    };
    card._actionError = null;
    card.render();
  };

  const section = node("section", null, "maintenance-section");
  section.append(node("style", STYLE));
  const guidance = node("details", null, "item");
  guidance.append(
    node("summary", copy.help),
    node("p", parent ? copy.parent_help : copy.limited_help, "sub"),
    node("p", `${copy.timezone}: ${card._data.settings?.timezone || "UTC"}`, "sub"),
    node("p", copy.safety_note, "notice"),
  );
  section.append(guidance);

  const draft = card._maintenanceDraft;
  if (!draft) {
    const assetSection = node("section", null, "item maintenance-list");
    assetSection.append(node("h3", copy.assets));
    if (parent) assetSection.append(button(copy.new_asset, () => openAsset(), true));
    if (!assets(card).length) assetSection.append(node("p", copy.no_assets, "sub"));
    for (const asset of assets(card)) {
      const item = node("article", null, "item");
      item.dataset.maintenanceAsset = asset.id;
      item.append(node("strong", asset.name));
      item.append(node("p", [asset.category, asset.location].filter(Boolean).join(" · "), "sub"));
      if (parent) {
        item.append(node("p", `${asset.status === "retired" ? copy.status_retired : copy.status_active} · ${copy.responsible}: ${memberName(card, asset.responsible_member, copy)}`, "sub"));
        if (asset.current === false) item.append(node("p", copy.current_warning, "notice"));
        const details = node("details");
        details.append(node("summary", copy.warranty));
        details.append(
          node("p", `${copy.warranty_expires}: ${asset.warranty?.expires_on || "—"}`),
          node("p", `${copy.vendor}: ${asset.warranty?.vendor || "—"}`),
          node("p", `${copy.reference}: ${asset.warranty?.reference || "—"}`),
          node("p", `${copy.reportable}: ${asset.reportable ? copy.enabled : copy.disabled}`),
        );
        appendConsumableSummary(details, asset.consumables || [], copy);
        if (asset.note) details.append(node("p", asset.note, "maintenance-note"));
        item.append(details);
        if (asset.history?.length) {
          const history = node("details");
          history.append(node("summary", copy.history));
          for (const event of asset.history) history.append(node(
            "p",
            `${event.at} · ${memberName(card, event.actor, copy)} · ${copy[`action_${event.action}`] || event.action}${event.reason ? ` · ${event.reason}` : ""}`,
            "sub",
          ));
          item.append(history);
        }
      }
      const actions = node("div", null, "maintenance-actions");
      if (asset.can_report && tasksEnabled(card)) actions.append(button(copy.report_fault, () => openFault(asset), false));
      if (parent && asset.status === "active") {
        actions.append(button(copy.edit_asset, () => openAsset(asset)));
        if (asset.current && tasksEnabled(card)) actions.append(button(copy.new_service, () => openService(asset)));
        actions.append(button(copy.retire_asset, () => openRetire(asset)));
      }
      if (parent) actions.append(button(copy.manual_service_log, () => openLog(asset)));
      if (actions.children.length) item.append(actions);
      assetSection.append(item);
    }
    section.append(assetSection);

    const faultSection = node("section", null, "item maintenance-list");
    faultSection.append(node("h3", copy.active_faults));
    if (!faults(card).length) faultSection.append(node("p", copy.no_faults, "sub"));
    for (const fault of faults(card)) {
      const item = node("article", null, "item");
      item.dataset.maintenanceFault = fault.id;
      item.append(node("strong", fault.summary));
      const taskStatus = card.t?.[fault.task_status] || fault.task_status || fault.status;
      item.append(node("p", `${assetName(card, fault.asset_id)} · ${taskStatus}`, "sub"));
      if (fault.task_id) item.append(node("p", `${copy.linked_task}: ${fault.task_id}`, "sub"));
      if (parent) item.append(node("p", `${copy.reporter}: ${memberName(card, fault.reporter, copy)} · ${copy.reported_at}: ${fault.created_at}`, "sub"));
      if (fault.details) item.append(node("p", fault.details, "maintenance-note"));
      faultSection.append(item);
    }
    section.append(faultSection);

    if (parent) {
      const serviceSection = node("section", null, "item maintenance-list");
      serviceSection.append(node("h3", copy.services), node("p", copy.schedule_note, "sub"));
      if (!services(card).length) serviceSection.append(node("p", copy.no_services, "sub"));
      for (const service of services(card)) {
        const item = node("article", null, "item");
        item.dataset.maintenanceService = service.id;
        item.append(node("strong", service.title));
        item.append(node("p", `${assetName(card, service.asset_id)} · ${service.enabled ? copy.enabled : copy.disabled}`, "sub"));
        item.append(node("p", `${copy.assignees}: ${(service.assignees || []).map((id) => memberName(card, id, copy)).join(", ")}`, "sub"));
        if (!service.current) item.append(node("p", copy.current_warning, "notice"));
        const actions = node("div", null, "maintenance-actions");
        const asset = assetById(card, service.asset_id);
        if (asset?.current && asset.status === "active")
          actions.append(button(copy.edit_service, () => openService(asset, service)));
        if (service.enabled || service.current)
          actions.append(button(service.enabled ? copy.disable_service : copy.enable_service, () => openToggle(service)));
        if (actions.children.length) item.append(actions);
        serviceSection.append(item);
      }
      section.append(serviceSection);

      const logSection = node("details", null, "item maintenance-list");
      logSection.append(node("summary", copy.service_history));
      if (!serviceLogs(card).length) logSection.append(node("p", copy.no_service_history, "sub"));
      for (const log of serviceLogs(card)) {
        const item = node("article", null, "item");
        item.append(node("strong", `${log.performed_on} · ${assetName(card, log.asset_id)}`));
        item.append(node("p", log.summary, "maintenance-note"));
        appendConsumableSummary(item, log.consumables_used || [], copy);
        if (log.task_id) item.append(node("p", `${copy.linked_task}: ${log.task_id}`, "sub"));
        logSection.append(item);
      }
      section.append(logSection);
    }
  } else if (draft.kind === "asset_edit") {
    const form = node("form", null, "item maintenance-form");
    form.dataset.maintenanceForm = "asset_edit";
    form.append(node("h3", draft.source ? copy.edit_asset : copy.new_asset));
    const fields = node("div", null, "maintenance-fields");
    const controls = {
      name: input(fields, copy.asset_name, "name", draft.values.name),
      category: input(fields, copy.category, "category", draft.values.category),
      location: input(fields, copy.location, "location", draft.values.location),
      warranty_expires: input(fields, copy.warranty_expires, "warranty_expires", draft.values.warranty_expires, "date"),
      warranty_vendor: input(fields, copy.vendor, "warranty_vendor", draft.values.warranty_vendor),
      warranty_reference: input(fields, copy.reference, "warranty_reference", draft.values.warranty_reference),
      note: textarea(fields, copy.note, "note", draft.values.note, copy.privacy_note),
      reportable: input(fields, copy.reportable, "reportable", draft.values.reportable, "checkbox"),
    };
    controls.note.parentElement.classList.add("wide");
    const responsibleLabel = node("label", copy.responsible);
    const responsible = document.createElement("select");
    responsible.name = "responsible_member";
    if (draft.values.responsibleUnavailable) {
      const option = node("option", `${copy.assignee_unavailable}: ${draft.values.responsibleUnavailable.id}`);
      option.value = "__unavailable__"; option.selected = true; option.disabled = true;
      responsible.append(option);
    }
    for (const member of members(card).filter((candidate) => activeMember(card, candidate.id))) {
      const option = node("option", member.name);
      option.value = member.id;
      option.selected = draft.values.responsible_member === member.id;
      responsible.append(option);
    }
    responsibleLabel.append(responsible);
    fields.append(responsibleLabel);
    form.append(fields);
    for (const [key, control] of Object.entries(controls)) {
      const update = () => {
        if (!guard(control, draft)) return;
        draft.values[key] = control.type === "checkbox" ? control.checked : control.value;
      };
      control.addEventListener("input", update); control.addEventListener("change", update);
    }
    responsible.addEventListener("change", () => {
      if (!guard(responsible, draft)) return;
      const member = activeMember(card, responsible.value);
      if (!member) return;
      draft.values.responsible_member = member.id;
      draft.values.responsibleUnavailable = null;
      draft.responsibleSnapshot = deepFreeze(memberSnapshot(card, member.id));
    });
    const consumables = node("div", null, "maintenance-list");
    consumables.append(node("h4", copy.consumables), node("p", copy.pantry_hint, "sub"));
    draft.values.consumables.forEach((row, index) => {
      const fieldset = node("fieldset", null, "maintenance-consumable");
      fieldset.dataset.maintenanceConsumable = String(index);
      fieldset.append(node("legend", `${copy.consumable_label} ${index + 1}`));
      const rowFields = node("div", null, "maintenance-consumable-fields");
      const rowControls = {
        label: input(rowFields, copy.consumable_label, "label", row.label),
        unit: input(rowFields, copy.unit, "unit", row.unit),
        quantity: input(rowFields, copy.quantity, "quantity", row.quantity, "number"),
      };
      const renderedUnit = row.unit;
      rowControls.quantity.min = "0.001"; rowControls.quantity.max = "1000000"; rowControls.quantity.step = "0.001";
      const pantryLabel = node("label", copy.pantry_item);
      const pantry = document.createElement("select"); pantry.name = "pantry";
      const none = node("option", copy.none); none.value = ""; pantry.append(none);
      if (row.pantryDecisionRequired) {
        const unavailable = node("option", `${copy.pantry_unavailable}: ${row.pantryUnavailable.id} · ${copy.revision} ${row.pantryUnavailable.revision}`);
        unavailable.value = "__unavailable__"; unavailable.disabled = true; unavailable.selected = true;
        pantry.append(unavailable);
        pantryLabel.append(node("span", copy.pantry_unavailable_hint, "notice"));
      }
      for (const item of pantryItems(card).filter((item) => item.status === "active" && item.unit === row.unit)) {
        const option = node("option", `${item.name} · ${item.unit}`);
        option.value = JSON.stringify([item.id, item.revision]);
        option.selected = row.pantry?.id === item.id && row.pantry?.revision === item.revision;
        pantry.append(option);
      }
      pantryLabel.append(pantry); rowFields.append(pantryLabel); fieldset.append(rowFields);
      for (const [key, control] of Object.entries(rowControls)) {
        const update = () => { if (guard(control, draft)) row[key] = control.value; };
        control.addEventListener("input", update); control.addEventListener("change", update);
      }
      rowControls.unit.addEventListener("change", () => {
        if (!guard(rowControls.unit, draft)) return;
        if (row.pantry && row.unit !== renderedUnit) {
          row.pantryUnavailable = clone(row.pantry);
          row.pantryDecisionRequired = true;
          card.render();
          return;
        }
        pantry.replaceChildren(none);
        for (const item of pantryItems(card).filter((item) => item.status === "active" && item.unit === row.unit)) {
          const option = node("option", `${item.name} · ${item.unit}`);
          option.value = JSON.stringify([item.id, item.revision]);
          pantry.append(option);
        }
      });
      pantry.addEventListener("change", () => {
        if (!guard(pantry, draft)) return;
        if (!pantry.value) { row.pantry = null; row.pantryDecisionRequired = false; }
        else {
          try {
            const [id, revision] = JSON.parse(pantry.value);
            const current = pantryCurrent(card, { id, revision }, row.unit);
            if (!current) throw new Error("stale");
            row.pantry = { id, revision }; row.pantryDecisionRequired = false;
          } catch {
            card._maintenanceDraft = null; card._actionError = "conflict"; card.render();
          }
        }
      });
      fieldset.append(button(copy.remove_consumable, () => {
        draft.values.consumables.splice(index, 1); card.render();
      }, false, draft));
      consumables.append(fieldset);
    });
    if (draft.values.consumables.length < 30) consumables.append(button(copy.add_consumable, () => {
      draft.values.consumables.push(consumableDraft(card)); card.render();
    }, false, draft));
    form.append(consumables);
    const actions = node("div", null, "maintenance-actions");
    const review = button(copy.review_asset, () => {}, true, draft); review.type = "submit";
    actions.append(review, button(copy.cancel, () => close(draft), false, draft)); form.append(actions);
    form.addEventListener("submit", (event) => {
      event.preventDefault(); if (!guard(form, draft)) return;
      try {
        draft.payload = deepFreeze(assetPayload(card, draft));
        draft.action = "maintenance.asset_save"; draft.kind = "review"; draft.reviewed = false;
        draft.targetName = draft.payload.name; card._actionError = null; card.render();
      } catch { card._actionError = "invalid_field"; card.render(); }
    });
    section.append(form);
  } else if (draft.kind === "fault_edit") {
    const form = node("form", null, "item maintenance-form"); form.dataset.maintenanceForm = "fault_edit";
    form.append(node("h3", copy.report_fault), node("p", draft.targetName, "sub"), node("p", copy.attachments_unavailable, "sub"));
    const summary = input(form, copy.fault_summary, "summary", draft.summary);
    const details = textarea(form, copy.fault_details, "details", draft.details);
    summary.addEventListener("input", () => { if (guard(summary, draft)) draft.summary = summary.value; });
    details.addEventListener("input", () => { if (guard(details, draft)) draft.details = details.value; });
    const actions = node("div", null, "maintenance-actions");
    const review = button(copy.review_fault, () => {}, true, draft); review.type = "submit";
    actions.append(review, button(copy.cancel, () => close(draft), false, draft)); form.append(actions);
    form.addEventListener("submit", (event) => {
      event.preventDefault(); if (!guard(form, draft)) return;
      try {
        draft.payload = deepFreeze({
          asset_id: draft.assetId, asset_revision: draft.source.revision,
          reporter_member_revision: draft.access.actorRevision,
          summary: rawText(summary.value, 200), details: rawText(details.value, 2000, false),
          attachment_ids: [],
        });
        draft.action = "maintenance.fault_report"; draft.kind = "review"; draft.reviewed = false;
        card._actionError = null; card.render();
      } catch { card._actionError = "invalid_field"; card.render(); }
    });
    section.append(form);
  } else if (draft.kind === "retire_edit") {
    const form = node("form", null, "item maintenance-form"); form.dataset.maintenanceForm = "retire_edit";
    form.append(node("h3", copy.retire_asset), node("p", draft.targetName, "sub"));
    const reason = input(form, copy.retire_reason, "reason", draft.reason);
    reason.addEventListener("input", () => { if (guard(reason, draft)) draft.reason = reason.value; });
    const actions = node("div", null, "maintenance-actions");
    const review = button(copy.review_retire, () => {}, true, draft); review.type = "submit";
    actions.append(review, button(copy.cancel, () => close(draft), false, draft)); form.append(actions);
    form.addEventListener("submit", (event) => {
      event.preventDefault(); if (!guard(form, draft)) return;
      try {
        draft.payload = deepFreeze({ id: draft.source.id, revision: draft.source.revision, reason: rawText(reason.value, 500) });
        draft.action = "maintenance.asset_retire"; draft.kind = "review"; draft.reviewed = false;
        card._actionError = null; card.render();
      } catch { card._actionError = "invalid_field"; card.render(); }
    });
    section.append(form);
  } else if (draft.kind === "log_edit") {
    const form = node("form", null, "item maintenance-form"); form.dataset.maintenanceForm = "log_edit";
    form.append(node("h3", copy.manual_service_log), node("p", draft.targetName, "sub"), node("p", copy.attachments_unavailable, "sub"));
    const performed = input(form, copy.performed_on, "performed_on", draft.performed_on, "date");
    const summary = textarea(form, copy.service_summary, "summary", draft.summary);
    const taskLabel = node("label", copy.service_task); const task = document.createElement("select"); task.name = "task";
    const noTask = node("option", copy.none); noTask.value = ""; task.append(noTask);
    for (const item of relatedCompletedTasks(card, draft.assetId)) {
      const option = node("option", item.title); option.value = JSON.stringify([item.id, item.revision]);
      option.selected = draft.task?.id === item.id && draft.task?.revision === item.revision; task.append(option);
    }
    taskLabel.append(task); form.append(taskLabel);
    performed.addEventListener("input", () => { if (guard(performed, draft)) draft.performed_on = performed.value; });
    summary.addEventListener("input", () => { if (guard(summary, draft)) draft.summary = summary.value; });
    task.addEventListener("change", () => {
      if (!guard(task, draft)) return;
      if (!task.value) { draft.task = null; draft.taskSnapshot = null; return; }
      try {
        const [id, revision] = JSON.parse(task.value); const current = taskById(card, id);
        if (!current || current.revision !== revision || current.status !== "completed") throw new Error("stale");
        draft.task = { id, revision }; draft.taskSnapshot = deepFreeze(clone(current));
      } catch { card._maintenanceDraft = null; card._actionError = "conflict"; card.render(); }
    });
    // Service-log consumables use the same bounded editor as assets, without source rows.
    const rows = node("div", null, "maintenance-list"); rows.append(node("h4", copy.consumables_used), node("p", copy.pantry_hint, "sub"));
    draft.consumables.forEach((row, index) => {
      const fieldset = node("fieldset", null, "maintenance-consumable"); fieldset.dataset.maintenanceConsumable = String(index);
      fieldset.append(node("legend", `${copy.consumable_label} ${index + 1}`));
      const fields = node("div", null, "maintenance-consumable-fields");
      const label = input(fields, copy.consumable_label, "label", row.label);
      const unit = input(fields, copy.unit, "unit", row.unit);
      const quantity = input(fields, copy.quantity, "quantity", row.quantity, "number"); quantity.step = "0.001";
      const renderedUnit = row.unit;
      const pantryLabel = node("label", copy.pantry_item);
      const pantry = document.createElement("select"); pantry.name = "pantry";
      const none = node("option", copy.none); none.value = ""; pantry.append(none);
      if (row.pantryDecisionRequired) {
        const unavailable = node("option", `${copy.pantry_unavailable}: ${row.pantryUnavailable.id} · ${copy.revision} ${row.pantryUnavailable.revision}`);
        unavailable.value = "__unavailable__"; unavailable.disabled = true; unavailable.selected = true;
        pantry.append(unavailable);
        pantryLabel.append(node("span", copy.pantry_unavailable_hint, "notice"));
      }
      for (const item of pantryItems(card).filter((item) => item.status === "active" && item.unit === row.unit)) {
        const option = node("option", `${item.name} · ${item.unit}`);
        option.value = JSON.stringify([item.id, item.revision]);
        option.selected = row.pantry?.id === item.id && row.pantry?.revision === item.revision;
        pantry.append(option);
      }
      pantryLabel.append(pantry); fields.append(pantryLabel);
      for (const [key, control] of [["label", label], ["unit", unit], ["quantity", quantity]])
        control.addEventListener("input", () => { if (guard(control, draft)) row[key] = control.value; });
      unit.addEventListener("change", () => {
        if (!guard(unit, draft)) return;
        if (row.pantry && row.unit !== renderedUnit) {
          row.pantryUnavailable = clone(row.pantry); row.pantryDecisionRequired = true;
          card.render();
          return;
        }
        pantry.replaceChildren(none);
        for (const item of pantryItems(card).filter((item) => item.status === "active" && item.unit === row.unit)) {
          const option = node("option", `${item.name} · ${item.unit}`);
          option.value = JSON.stringify([item.id, item.revision]);
          pantry.append(option);
        }
      });
      pantry.addEventListener("change", () => {
        if (!guard(pantry, draft)) return;
        if (!pantry.value) { row.pantry = null; row.pantryDecisionRequired = false; return; }
        try {
          const [id, revision] = JSON.parse(pantry.value);
          const current = pantryCurrent(card, { id, revision }, row.unit);
          if (!current) throw new Error("stale");
          row.pantry = { id, revision }; row.pantryDecisionRequired = false;
        } catch { card._maintenanceDraft = null; card._actionError = "conflict"; card.render(); }
      });
      fieldset.append(fields, button(copy.remove_consumable, () => { draft.consumables.splice(index, 1); card.render(); }, false, draft)); rows.append(fieldset);
    });
    if (draft.consumables.length < 30) rows.append(button(copy.add_consumable, () => { draft.consumables.push(consumableDraft(card)); card.render(); }, false, draft));
    form.append(rows);
    const actions = node("div", null, "maintenance-actions"); const review = button(copy.review_log, () => {}, true, draft); review.type = "submit";
    actions.append(review, button(copy.cancel, () => close(draft), false, draft)); form.append(actions);
    form.addEventListener("submit", (event) => {
      event.preventDefault(); if (!guard(form, draft)) return;
      try {
        const day = strictDate(performed.value); if (day > localToday(card)) throw new Error("invalid");
        draft.payload = deepFreeze({
          asset_id: draft.assetId, asset_revision: draft.source.revision, performed_on: day,
          summary: rawText(summary.value, 2000), task: draft.task ? clone(draft.task) : null,
          consumables_used: consumablesPayload(card, draft.consumables), attachment_ids: [],
        });
        draft.action = "maintenance.service_log"; draft.kind = "review"; draft.reviewed = false;
        card._actionError = null; card.render();
      } catch { card._actionError = "invalid_field"; card.render(); }
    });
    section.append(form);
  } else if (draft.kind === "service_edit") {
    const form = node("form", null, "item maintenance-form"); form.dataset.maintenanceForm = "service_edit";
    form.append(node("h3", draft.source ? copy.edit_service : copy.new_service), node("p", draft.targetName, "sub"), node("p", copy.schedule_note, "sub"));
    if (draft.source?.current === false) form.append(node("p", copy.current_warning, "notice"));
    const fields = node("div", null, "maintenance-fields");
    const title = input(fields, copy.service_title, "title", draft.values.title);
    const due = input(fields, copy.due_time, "due_time", draft.values.due_time, "time");
    const reminder = input(fields, copy.reminder_minutes, "reminder_minutes", draft.values.reminder_minutes, "number");
    const grace = input(fields, copy.grace_minutes, "grace_minutes", draft.values.grace_minutes, "number");
    const checklist = textarea(fields, copy.checklist, "checklist", draft.values.checklist, copy.checklist_hint); checklist.parentElement.classList.add("wide");
    const rotation = input(fields, copy.rotation_hint, "rotation", draft.values.rotation, "checkbox");
    const enabled = input(fields, copy.enabled, "enabled", draft.values.enabled, "checkbox");
    form.append(fields);
    for (const [key, control] of [["title", title], ["due_time", due], ["reminder_minutes", reminder], ["grace_minutes", grace], ["checklist", checklist], ["rotation", rotation], ["enabled", enabled]]) {
      const update = () => { if (guard(control, draft)) draft.values[key] = control.type === "checkbox" ? control.checked : control.value; };
      control.addEventListener("input", update); control.addEventListener("change", update);
    }
    const assignees = node("fieldset", null, "maintenance-assignees"); assignees.append(node("legend", copy.assignees));
    for (const id of draft.values.unavailableAssignees) assignees.append(node("p", `${copy.assignee_unavailable}: ${id}`, "notice"));
    for (const member of members(card).filter((candidate) => activeMember(card, candidate.id))) {
      const label = node("label", null, "check"); const box = document.createElement("input"); box.type = "checkbox"; box.value = member.id;
      box.checked = draft.values.assignees.includes(member.id); label.append(box, node("span", member.name)); assignees.append(label);
      box.addEventListener("change", () => {
        if (!guard(box, draft)) return;
        draft.values.assignees = [...assignees.querySelectorAll('input[type="checkbox"][value]')].filter((item) => item.checked && item !== replacement).map((item) => item.value);
        draft.assigneeSnapshots = draft.values.assignees.map((id) => deepFreeze(memberSnapshot(card, id)));
      });
    }
    let replacement = null;
    if (draft.values.unavailableAssignees.length) {
      const label = node("label", null, "check"); replacement = document.createElement("input"); replacement.type = "checkbox"; replacement.name = "replace_assignees";
      replacement.checked = draft.values.assigneeReplacementConfirmed; label.append(replacement, node("span", copy.confirm_assignee_replacement)); assignees.append(node("p", copy.assignee_unavailable_hint, "sub"), label);
      replacement.addEventListener("change", () => { if (guard(replacement, draft)) draft.values.assigneeReplacementConfirmed = replacement.checked; });
    }
    form.append(assignees);
    renderRecurrence(form, draft.values.rule, {
      language: languageOf(card), lockedFields: ["enabled"],
      isStale: () => !guard(form, draft),
      onChange: () => {},
    });
    const actions = node("div", null, "maintenance-actions"); const review = button(copy.review_service, () => {}, true, draft); review.type = "submit";
    actions.append(review, button(copy.cancel, () => close(draft), false, draft)); form.append(actions);
    form.addEventListener("submit", (event) => {
      event.preventDefault(); if (!guard(form, draft)) return;
      try {
        draft.payload = deepFreeze(servicePayload(card, draft));
        draft.action = "maintenance.service_save"; draft.kind = "review"; draft.reviewed = false;
        card._actionError = null; card.render();
      } catch { card._actionError = "invalid_field"; card.render(); }
    });
    section.append(form);
  } else if (draft.kind === "review") {
    const form = node("form", null, "item maintenance-form"); form.dataset.maintenanceForm = "review";
    const heading = {
      asset: copy.review_asset, fault: copy.review_fault, log: copy.review_log,
      service: copy.review_service, retire: copy.review_retire, toggle: copy.review_toggle,
    }[draft.intent];
    form.append(node("h3", heading), node("p", draft.targetName, "sub"));
    const review = node("div", null, "maintenance-review");
    if (draft.intent === "asset") {
      review.append(
        node("p", `${copy.category}: ${draft.payload.category || "—"}`),
        node("p", `${copy.location}: ${draft.payload.location || "—"}`),
        node("p", `${copy.responsible}: ${memberName(card, draft.payload.responsible_member, copy)}`),
        node("p", `${copy.warranty_expires}: ${draft.payload.warranty.expires_on || "—"}`),
        node("p", `${copy.vendor}: ${draft.payload.warranty.vendor || "—"}`),
        node("p", `${copy.reference}: ${draft.payload.warranty.reference || "—"}`),
        node("p", `${copy.reportable}: ${draft.payload.reportable ? copy.enabled : copy.disabled}`),
        node("p", `${copy.note}: ${draft.payload.note || "—"}`, "maintenance-note"),
      );
      appendConsumableSummary(review, draft.payload.consumables, copy);
    } else if (draft.intent === "fault") {
      review.append(node("p", draft.payload.summary), node("p", draft.payload.details || "—", "maintenance-note"), node("p", copy.attachments_unavailable, "sub"));
    } else if (draft.intent === "log") {
      review.append(node("p", `${copy.performed_on}: ${draft.payload.performed_on}`), node("p", draft.payload.summary, "maintenance-note"), node("p", `${copy.service_task}: ${draft.payload.task?.id || copy.none}`));
      appendConsumableSummary(review, draft.payload.consumables_used, copy);
    } else if (draft.intent === "service") {
      review.append(
        node("p", draft.payload.title),
        node("p", `${copy.assignees}: ${draft.payload.assignees.map((item) => memberName(card, item.id, copy)).join(", ")}`),
        node("p", `${copy.rotation}: ${draft.payload.rotation ? copy.enabled : copy.disabled}`),
        node("p", `${copy.due_time}: ${draft.payload.due_time}`),
        node("p", `${copy.enabled}: ${draft.payload.enabled ? copy.enabled : copy.disabled}`),
        node("p", `${copy.reminder_minutes}: ${draft.payload.reminder_minutes}`),
        node("p", `${copy.grace_minutes}: ${draft.payload.grace_minutes}`),
        node("p", `${copy.checklist}: ${draft.payload.checklist.join(" · ") || copy.none}`),
      );
      renderRuleSummary(review, draft.payload.rule, card);
    } else if (draft.intent === "retire") {
      review.append(node("p", `${copy.retire_reason}: ${draft.payload.reason}`, "maintenance-note"));
    } else if (draft.intent === "toggle") {
      review.append(node("p", draft.payload.enabled ? copy.enable_service : copy.disable_service));
    }
    form.append(review);
    if (draft.pending) form.append(node("p", copy.retry_hint, "notice"));
    const label = node("label", null, "check"); const checked = document.createElement("input"); checked.type = "checkbox"; checked.name = "reviewed";
    checked.checked = draft.reviewed === true; checked.disabled = Boolean(draft.pending);
    const confirmation = {
      asset: copy.confirm_asset, fault: copy.confirm_fault, log: copy.confirm_log,
      service: copy.confirm_service, retire: copy.confirm_retire, toggle: copy.confirm_toggle,
    }[draft.intent];
    label.append(checked, node("span", confirmation)); form.append(label);
    checked.addEventListener("change", () => { if (guard(checked, draft) && !draft.pending) draft.reviewed = checked.checked; });
    const actions = node("div", null, "maintenance-actions"); const submit = button(draft.pending ? copy.retry_exact : copy.save, () => {}, true, draft); submit.type = "submit";
    actions.append(submit, button(copy.cancel, () => close(draft), false, draft)); form.append(actions);
    form.addEventListener("submit", (event) => {
      event.preventDefault(); if (!guard(form, draft, !draft.pending)) return;
      if (!draft.pending && !checked.checked) return;
      draft.reviewed = true; void run(draft);
    });
    section.append(form);
  }
  body.append(section);
}
