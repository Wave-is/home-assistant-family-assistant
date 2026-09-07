/* Private school homework and explicit backpack preparation UI. */

import { wallTime, wallTimeCandidates } from "./local-time.js";
import { SCHOOL_WORK_COPY } from "./school-work-copy.js";
import { TASK_ITEM_COPY } from "./task-items.js";

const PARENTS = new Set(["owner", "parent"]);
const ROLES = new Set(["owner", "parent", "child"]);
const REVISABLE = new Set(["assigned", "accepted", "in_progress", "needs_changes"]);
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

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
  .school-work{display:grid;gap:14px;margin-top:16px}.school-work-group{display:grid;gap:10px}
  .school-work-help{margin:0}.school-work-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
  .school-work-fields>.wide{grid-column:1/-1}.school-work-form{display:grid;gap:12px}
  .school-work-form fieldset{display:block;min-width:0}.school-work-form fieldset>*+*{margin-top:10px}
  .school-work-form textarea{min-height:90px}.school-work-list{display:grid;gap:8px}
  .school-work-row{min-width:0}.school-work-row p{overflow-wrap:anywhere}.school-work-review ul{margin:6px 0;padding-inline-start:20px}
  .school-work-confirm{margin-top:8px}.school-work-actions{display:flex;flex-wrap:wrap;gap:8px}
  @media(max-width:520px){.school-work-fields{grid-template-columns:minmax(0,1fr)}.school-work-fields>.wide{grid-column:auto}.school-work-actions>button{width:100%}}
`;

function copyOf(card) {
  const language = card?._config?.language || card?._hass?.language || "en";
  return SCHOOL_WORK_COPY[language.split("-")[0]] || SCHOOL_WORK_COPY.en;
}

function validRevision(value) {
  return Number.isSafeInteger(value) && value >= 1;
}

function members(card) {
  return Array.isArray(card?._data?.members) ? card._data.members : [];
}

function member(card, id) {
  return members(card).find((item) => item.id === id);
}

function child(card, id) {
  const item = member(card, id);
  return item?.active === true && item.role === "child" && validRevision(item.revision)
    ? item
    : null;
}

function access(card) {
  const data = card?._data;
  const actor = member(card, data?.actor);
  if (
    !data?.actor ||
    !ROLES.has(data?.role) ||
    actor?.active !== true ||
    actor.role !== data.role ||
    !validRevision(actor.revision) ||
    !data?.settings?.modules?.includes("school") ||
    !data.school ||
    typeof data.school !== "object"
  )
    return null;
  return {
    generation: card._generation,
    entry: card._entry,
    actor: data.actor,
    role: data.role,
    actorRevision: actor.revision,
    timezone: data.settings?.timezone || "UTC",
  };
}

function sameAccess(card, expected) {
  const current = access(card);
  return Boolean(current && expected) && JSON.stringify(current) === JSON.stringify(expected);
}

function homework(card) {
  return Array.isArray(card?._data?.school?.homework) ? card._data.school.homework : [];
}

function preparations(card) {
  return Array.isArray(card?._data?.school?.preparations)
    ? card._data.school.preparations
    : [];
}

function timetables(card) {
  return Array.isArray(card?._data?.school?.timetables)
    ? card._data.school.timetables
    : [];
}

function upcoming(card) {
  return Array.isArray(card?._data?.school?.upcoming) ? card._data.school.upcoming : [];
}

function currentTask(card, id) {
  return homework(card).find((item) => item.id === id);
}

function actorCanTarget(card, memberId) {
  const scope = access(card);
  if (!scope) return null;
  const target = child(card, memberId);
  if (!target) return null;
  return PARENTS.has(scope.role) || (scope.role === "child" && scope.actor === memberId)
    ? target
    : null;
}

function modules(card, ...required) {
  const enabled = card?._data?.settings?.modules;
  return Array.isArray(enabled) && required.every((name) => enabled.includes(name));
}

function parseDate(value) {
  if (!ISO_DATE.test(value || "")) return null;
  const [year, month, day] = value.split("-").map(Number);
  const result = new Date(0);
  result.setUTCFullYear(year, month - 1, day);
  result.setUTCHours(0, 0, 0, 0);
  return result.getUTCFullYear() === year && result.getUTCMonth() + 1 === month && result.getUTCDate() === day
    ? result
    : null;
}

function localDates(zone) {
  try {
    const parts = new Intl.DateTimeFormat("en-US-u-ca-gregory-nu-latn", {
      timeZone: zone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).formatToParts(new Date());
    const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
    const today = `${values.year}-${values.month}-${values.day}`;
    const parsed = parseDate(today);
    if (!parsed) return [];
    const tomorrow = new Date(parsed.valueOf() + 86400000).toISOString().slice(0, 10);
    return [today, tomorrow];
  } catch {
    return [];
  }
}

function lessonOptions(card, memberId) {
  const options = [];
  for (const row of upcoming(card)) {
    if (row?.member !== memberId || !parseDate(row.date)) continue;
    const table = timetables(card).find(
      (item) =>
        item?.id === row.timetable_id &&
        item.status === "active" &&
        item.member === memberId &&
        validRevision(item.revision),
    );
    if (!table || !Array.isArray(table.lessons)) continue;
    const prefix = `${table.id}:${row.date}:`;
    if (typeof row.id !== "string" || !row.id.startsWith(prefix)) continue;
    const rawIndex = row.id.slice(prefix.length);
    if (!/^\d+$/.test(rawIndex)) continue;
    const index = Number(rawIndex);
    if (!Number.isSafeInteger(index) || index < 0 || index >= table.lessons.length) continue;
    const lesson = table.lessons[index];
    const date = parseDate(row.date);
    if (!lesson || lesson.weekday !== (date.getUTCDay() + 6) % 7) continue;
    options.push({
      payload: {
        timetable_id: table.id,
        timetable_revision: table.revision,
        date: row.date,
        lesson_index: index,
      },
      label: `${row.date} · ${row.start || ""}–${row.end || ""} · ${row.subject || ""}`,
    });
  }
  return options;
}

function sameLesson(left, right) {
  return JSON.stringify(left ?? null) === JSON.stringify(right ?? null);
}

function lessonStillCurrent(card, memberId, selected) {
  return selected === null || lessonOptions(card, memberId).some((item) => sameLesson(item.payload, selected));
}

function preparationOptions(card) {
  if (!modules(card, "school", "routines")) return [];
  const scope = access(card);
  if (!scope) return [];
  const allowedDates = new Set(localDates(card._data.settings?.timezone || "UTC"));
  const started = new Set(preparations(card).map((item) => `${item.timetable_id}|${item.date}`));
  const seen = new Set();
  const result = [];
  for (const row of upcoming(card)) {
    if (!allowedDates.has(row?.date) || started.has(`${row.timetable_id}|${row.date}`)) continue;
    const target = actorCanTarget(card, row.member);
    const routine = row.backpack_routine;
    const table = timetables(card).find(
      (item) => item?.id === row.timetable_id && item.status === "active" && item.member === row.member,
    );
    if (!target || !table || !validRevision(table.revision) || !validRevision(routine?.revision)) continue;
    if (typeof routine.id !== "string" || !routine.id) continue;
    const key = `${table.id}|${row.date}`;
    if (seen.has(key)) continue;
    seen.add(key);
    result.push({
      payload: {
        timetable_id: table.id,
        timetable_revision: table.revision,
        member: target.id,
        member_revision: target.revision,
        date: row.date,
        routine_id: routine.id,
        routine_revision: routine.revision,
      },
      childName: target.name || target.id,
      timetableTitle: table.title || table.id,
      routineTitle: routine.title || routine.id,
      lessonLabel: `${row.date} · ${row.start || ""}–${row.end || ""} · ${row.subject || ""}`,
    });
  }
  return result;
}

function pendingAllowed(card, draft) {
  if (!sameAccess(card, draft?.access) || !draft.pending) return false;
  const payload = draft.pending.payload;
  if (draft.intent === "homework_create")
    return modules(card, "school", "tasks") && actorCanTarget(card, payload.member)?.revision === payload.member_revision;
  if (draft.intent === "homework_revise") {
    if (!PARENTS.has(card._data.role) || !modules(card, "school", "tasks")) return false;
    const item = currentTask(card, payload.id);
    const target = child(card, item?.assignee);
    const source = item?.source;
    const shared = Boolean(
      item &&
        source?.kind === "school_homework" &&
        source.member === item.assignee &&
        target?.revision === payload.member_revision,
    );
    const preCommit =
      item?.revision === payload.revision && REVISABLE.has(item?.status);
    const postCommit =
      source?.member_revision === payload.member_revision &&
      item?.assignee_revision === payload.member_revision;
    return shared && (preCommit || postCommit);
  }
  if (draft.intent === "backpack_start") {
    if (!modules(card, "school", "routines")) return false;
    const target = actorCanTarget(card, payload.member);
    const table = timetables(card).find((item) => item.id === payload.timetable_id);
    const rawLink = table?.backpack_routine;
    const currentLink = table && Object.hasOwn(table, "backpack_routine_current")
      ? table.backpack_routine_current
      : rawLink;
    return Boolean(
      target?.revision === payload.member_revision &&
        table?.status === "active" &&
        table.member === payload.member &&
        table.revision === payload.timetable_revision &&
        rawLink?.id === payload.routine_id &&
        rawLink.revision === payload.routine_revision &&
        currentLink?.id === payload.routine_id &&
        currentLink.revision === payload.routine_revision,
    );
  }
  return false;
}

function draftAllowed(card, draft, exact = true) {
  if (!sameAccess(card, draft?.access)) return false;
  if (draft.pending) return pendingAllowed(card, draft);
  if (draft.intent === "homework_create") {
    const target = actorCanTarget(card, draft.memberId);
    return Boolean(
      modules(card, "school", "tasks") &&
        target?.revision === draft.memberRevision &&
        (!exact || lessonStillCurrent(card, draft.memberId, draft.review?.payload?.lesson ?? draft.lesson)),
    );
  }
  if (draft.intent === "homework_revise") {
    const item = currentTask(card, draft.taskId);
    const target = child(card, draft.memberId);
    return Boolean(
      PARENTS.has(card._data.role) &&
        modules(card, "school", "tasks") &&
        target?.revision === draft.memberRevision &&
        item?.assignee === draft.memberId &&
        (!exact || (item.revision === draft.taskRevision && REVISABLE.has(item.status))),
    );
  }
  if (draft.intent === "backpack_start") {
    if (!modules(card, "school", "routines")) return false;
    const match = preparationOptions(card).find((item) => sameLesson(item.payload, draft.review?.payload));
    return Boolean(match);
  }
  return false;
}

function projection(data) {
  return {
    actor: data?.actor ?? null,
    role: data?.role ?? null,
    modules: (data?.settings?.modules || []).filter((item) => ["school", "tasks", "routines"].includes(item)),
    timezone: data?.settings?.timezone ?? null,
    members: (data?.members || []).map(({ id, name, role, active, revision }) => ({ id, name, role, active, revision })),
    school: data?.school
      ? {
          homework: data.school.homework || [],
          preparations: data.school.preparations || [],
          timetables: data.school.timetables || [],
          upcoming: data.school.upcoming || [],
        }
      : null,
  };
}

export function reconcileSchoolWorkRefresh(card, previousData) {
  if (!card) return false;
  const changed = JSON.stringify(projection(previousData)) !== JSON.stringify(projection(card._data));
  let force = changed && Boolean(card._schoolWorkDraft || card.shadowRoot?.querySelector(".school-work"));
  if (card._schoolWorkDraft && !draftAllowed(card, card._schoolWorkDraft, !card._schoolWorkDraft.pending)) {
    card._schoolWorkDraft = null;
    card._actionError = "conflict";
    force = true;
  }
  return force;
}

function taskLabel(card, item) {
  const language = card?._config?.language || card?._hass?.language || "en";
  const copy = TASK_ITEM_COPY[language.split("-")[0]] || TASK_ITEM_COPY.en;
  return copy[`status_${item?.status}`] || copy.status_unknown;
}

function dueLabel(card, value) {
  if (!value) return "";
  const zone = card._data?.settings?.timezone || "UTC";
  try {
    return `${wallTime(value, zone).replace("T", " ")} · ${zone}`;
  } catch {
    return zone;
  }
}

function memberName(card, id, copy) {
  return member(card, id)?.name || copy.unavailable_member;
}

function policyOf(item) {
  return {
    reminder: item?.deadline_policy?.reminder_minutes ?? 60,
    grace: item?.deadline_policy?.grace_minutes ?? 30,
  };
}

function initialDue(item, zone) {
  if (!item?.due_at) return { wall: "", original: null, fold: null };
  try {
    const wall = wallTime(item.due_at, zone);
    const candidates = wallTimeCandidates(wall, zone);
    const fold = candidates.length === 2
      ? candidates.findIndex((candidate) => Math.floor(Date.parse(candidate) / 60000) === Math.floor(Date.parse(item.due_at) / 60000))
      : null;
    return { wall, original: item.due_at, fold: fold >= 0 ? fold : null };
  } catch {
    return { wall: "", original: item.due_at, fold: null };
  }
}

function checklistText(item) {
  return Array.isArray(item?.checklist)
    ? item.checklist.map((entry) => (typeof entry === "string" ? entry : entry?.text || "")).filter(Boolean)
    : [];
}

function makeDue(form, card, draft, copy, frozen) {
  const input = card.input(form, "due_at", copy.due, "datetime-local", draft.dueWall || "", false);
  input.disabled = frozen;
  const gap = node("p", copy.dst_gap, "notice");
  const ambiguous = node("p", copy.dst_ambiguous, "notice");
  gap.hidden = true;
  ambiguous.hidden = true;
  const foldLabel = node("label", copy.dst_choice);
  const fold = node("select");
  fold.name = "due_fold";
  for (const [value, label] of [["", copy.dst_choose], ["0", copy.dst_first], ["1", copy.dst_second]]) {
    const option = node("option", label);
    option.value = value;
    fold.append(option);
  }
  fold.value = draft.dueFold === null || draft.dueFold === undefined ? "" : String(draft.dueFold);
  fold.disabled = frozen;
  foldLabel.append(fold);
  foldLabel.hidden = true;
  form.append(gap, ambiguous, foldLabel);
  const candidates = () => {
    gap.hidden = true;
    ambiguous.hidden = true;
    foldLabel.hidden = true;
    if (!input.value) return [];
    try {
      const values = wallTimeCandidates(input.value, card._data.settings?.timezone || "UTC");
      if (!values.length) gap.hidden = false;
      if (values.length === 2) foldLabel.hidden = false;
      return values;
    } catch {
      gap.hidden = false;
      return [];
    }
  };
  if (input.value) candidates();
  input.addEventListener("input", () => {
    if (frozen || !sameAccess(card, draft.access) || !input.isConnected) return;
    draft.dueWall = input.value;
    if (input.value !== draft.originalWall) {
      draft.dueFold = null;
      draft.foldChanged = true;
      fold.value = "";
    }
    candidates();
  });
  fold.addEventListener("change", () => {
    if (frozen || !sameAccess(card, draft.access) || !fold.isConnected) return;
    draft.dueFold = fold.value === "" ? null : Number(fold.value);
    draft.foldChanged = true;
    ambiguous.hidden = true;
  });
  return {
    value() {
      const wall = input.value.trim();
      if (!wall) return null;
      const values = candidates();
      if (!values.length) throw new Error("due");
      if (wall === draft.originalWall && !draft.foldChanged && draft.originalDue) return draft.originalDue;
      if (values.length === 1) return values[0];
      if (!["0", "1"].includes(fold.value)) {
        ambiguous.hidden = false;
        throw new Error("due");
      }
      return values[Number(fold.value)];
    },
  };
}

function appendReview(container, card, draft, copy) {
  const review = draft.review;
  const box = node("section", null, "item school-work-review");
  box.dataset.schoolWorkReview = draft.intent;
  box.append(node("h3", draft.intent === "backpack_start" ? copy.review_preparation : copy.review_homework));
  const list = node("ul");
  const add = (label, value) => list.append(node("li", `${label}: ${value ?? copy.none}`));
  add(copy.child, review.childName);
  if (draft.intent === "backpack_start") {
    add(copy.school_date, review.payload.date);
    add(copy.timetable, `${review.timetableTitle} (${copy.version} ${review.payload.timetable_revision})`);
    add(copy.lesson, review.lessonLabel);
    add(copy.routine, `${review.routineTitle} (${copy.version} ${review.payload.routine_revision})`);
  } else {
    add(copy.homework_title, review.payload.title);
    add(copy.due_label, review.dueLabel || copy.none);
    add(copy.reminder, review.payload.reminder_minutes);
    add(copy.grace, review.payload.grace_minutes);
    add(copy.lesson, review.lessonLabel || copy.no_lesson);
    const checklist = node("li", `${copy.checklist}:`);
    const nested = node("ul");
    for (const item of review.checklist) nested.append(node("li", item));
    if (!review.checklist.length) nested.append(node("li", copy.none));
    checklist.append(nested);
    list.append(checklist);
    if (draft.intent === "homework_revise")
      box.append(node("p", draft.identityReset ? copy.identity_reset : copy.preserved, draft.identityReset ? "notice" : "sub"));
  }
  box.append(list);
  const form = node("form", null, "school-work-form");
  const label = node("label", null, "check school-work-confirm");
  const check = node("input");
  check.type = "checkbox";
  check.required = true;
  check.disabled = Boolean(card._writing);
  label.append(check, node("span", draft.intent === "backpack_start" ? copy.confirm_preparation : copy.confirm_homework));
  form.append(label);
  const actions = node("div", null, "school-work-actions");
  const submit = node("button", draft.pending ? copy.retry : draft.intent === "backpack_start" ? copy.start_routine : draft.intent === "homework_create" ? copy.create_homework : copy.save_revision, "primary");
  submit.type = "submit";
  submit.disabled = Boolean(card._writing);
  const cancel = card.button(copy.cancel, () => {
    if (!form.isConnected || !sameAccess(card, draft.access) || card._writing) return;
    card._schoolWorkDraft = null;
    card._actionError = null;
    card.render();
  });
  actions.append(submit, cancel);
  form.append(actions);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!form.isConnected || !check.checked) return;
    void send(card, form.closest(".school-work"), draft);
  });
  box.append(form);
  container.append(box);
}

async function send(card, body, draft) {
  if (!body?.isConnected || card._writing || card._schoolWorkDraft !== draft || !draftAllowed(card, draft, !draft.pending)) return;
  if (!draft.pending) {
    draft.pending = deepFreeze({
      action: `school.${draft.intent}`,
      payload: clone(draft.review.payload),
      operation_id: crypto.randomUUID(),
    });
  }
  const pending = draft.pending;
  await card.command(pending.action, pending.payload, pending.operation_id);
  if (sameAccess(card, draft.access) && card._schoolWorkDraft === draft && !card._actionError) {
    card._schoolWorkDraft = null;
    card.render();
  }
}

function openHomework(card, item = null) {
  const scope = access(card);
  const isRevise = Boolean(item);
  const memberId = isRevise ? item.assignee : scope.role === "child" ? scope.actor : members(card).find((value) => value.active && value.role === "child")?.id;
  const target = actorCanTarget(card, memberId);
  if (!scope || !target || !modules(card, "school", "tasks") || (isRevise && (!PARENTS.has(scope.role) || !REVISABLE.has(item.status)))) return;
  const zone = card._data.settings?.timezone || "UTC";
  const due = initialDue(item, zone);
  const policy = policyOf(item);
  const sourceLesson = isRevise ? item.source?.lesson ?? null : null;
  card._schoolWorkDraft = {
    intent: isRevise ? "homework_revise" : "homework_create",
    access: scope,
    memberId: target.id,
    memberRevision: target.revision,
    taskId: item?.id || null,
    taskRevision: item?.revision || null,
    title: item?.title || "",
    dueWall: due.wall,
    originalWall: due.wall,
    originalDue: due.original,
    dueFold: due.fold,
    foldChanged: false,
    checklist: checklistText(item),
    lesson: sourceLesson,
    reminder: policy.reminder,
    grace: policy.grace,
    preservedChecklist: checklistText(item),
    preservedLesson: clone(sourceLesson),
    identityReset: Boolean(isRevise && item.assignee_revision !== target.revision),
    review: null,
    pending: null,
  };
  card._actionError = null;
  card.render();
}

function renderEditor(section, card, draft, copy) {
  const frozen = Boolean(draft.review);
  const form = node("form", null, "item school-work-form");
  form.dataset.schoolWorkEditor = draft.intent;
  form.append(node("h3", draft.intent === "homework_create" ? copy.new_homework : copy.revise_homework));
  const fields = node("div", null, "school-work-fields");
  let childSelect = null;
  if (draft.intent === "homework_create" && PARENTS.has(card._data.role)) {
    const label = node("label", copy.child);
    childSelect = node("select");
    childSelect.name = "member";
    for (const item of members(card).filter((value) => value.active && value.role === "child" && validRevision(value.revision))) {
      const option = node("option", item.name || item.id);
      option.value = item.id;
      childSelect.append(option);
    }
    childSelect.value = draft.memberId;
    childSelect.disabled = frozen;
    label.append(childSelect);
    fields.append(label);
  } else {
    const label = node("p", `${copy.child}: ${memberName(card, draft.memberId, copy)}`, "sub");
    fields.append(label);
  }
  const title = card.input(fields, "title", copy.homework_title, "text", draft.title, true);
  title.maxLength = 500;
  title.disabled = frozen;
  title.closest("label")?.classList.add("wide");
  form.append(fields);
  const due = makeDue(form, card, draft, copy, frozen);
  let checklist = null;
  let lessonSelect = null;
  if (draft.intent === "homework_create") {
    const checkLabel = node("label", copy.checklist, "wide");
    checklist = node("textarea");
    checklist.name = "checklist";
    checklist.value = draft.checklist.join("\n");
    checklist.maxLength = 10049;
    checklist.disabled = frozen;
    checkLabel.append(checklist, node("span", copy.checklist_hint, "sub"));
    form.append(checkLabel);
    const lessonLabel = node("label", copy.lesson);
    lessonSelect = node("select");
    lessonSelect.name = "lesson";
    lessonSelect.disabled = frozen;
    lessonLabel.append(lessonSelect);
    form.append(lessonLabel);
  } else {
    form.append(node("p", draft.identityReset ? copy.identity_reset : copy.preserved, draft.identityReset ? "notice" : "sub"));
  }
  const policy = node("fieldset");
  policy.append(node("legend", copy.policy));
  const policyFields = node("div", null, "school-work-fields");
  const reminder = card.input(policyFields, "reminder_minutes", copy.reminder, "number", String(draft.reminder), true);
  reminder.min = "0";
  reminder.max = "10080";
  reminder.step = "1";
  reminder.disabled = frozen;
  const grace = card.input(policyFields, "grace_minutes", copy.grace, "number", String(draft.grace), true);
  grace.min = "0";
  grace.max = "1440";
  grace.step = "1";
  grace.disabled = frozen;
  policy.append(policyFields);
  form.append(policy);
  const notice = node("p", copy.required, "notice");
  notice.hidden = true;
  form.append(notice);

  const rebuildLessons = () => {
    if (!lessonSelect) return;
    const choices = lessonOptions(card, draft.memberId);
    lessonSelect.replaceChildren();
    const none = node("option", copy.no_lesson);
    none.value = "";
    lessonSelect.append(none);
    choices.forEach((choice, index) => {
      const option = node("option", choice.label);
      option.value = String(index);
      lessonSelect.append(option);
      if (sameLesson(choice.payload, draft.lesson)) lessonSelect.value = String(index);
    });
    lessonSelect._choices = choices;
  };
  rebuildLessons();
  childSelect?.addEventListener("change", () => {
    if (frozen || !childSelect.isConnected || !sameAccess(card, draft.access)) return;
    const target = actorCanTarget(card, childSelect.value);
    if (!target) return;
    draft.memberId = target.id;
    draft.memberRevision = target.revision;
    draft.lesson = null;
    rebuildLessons();
  });
  lessonSelect?.addEventListener("change", () => {
    if (frozen || !lessonSelect.isConnected || !sameAccess(card, draft.access)) return;
    draft.lesson = lessonSelect.value === "" ? null : clone(lessonSelect._choices[Number(lessonSelect.value)]?.payload ?? null);
  });
  const actions = node("div", null, "school-work-actions");
  const review = node("button", copy.review, "primary");
  review.type = "submit";
  review.disabled = frozen || Boolean(card._writing);
  const cancel = card.button(copy.cancel, () => {
    if (!form.isConnected || card._writing || !sameAccess(card, draft.access)) return;
    card._schoolWorkDraft = null;
    card._actionError = null;
    card.render();
  });
  actions.append(review, cancel);
  form.append(actions);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (frozen || !form.isConnected || card._writing || card._schoolWorkDraft !== draft || !draftAllowed(card, draft)) return;
    try {
      const target = actorCanTarget(card, childSelect?.value || draft.memberId);
      const titleValue = title.value.trim();
      const reminderValue = Number(reminder.value);
      const graceValue = Number(grace.value);
      if (!target || !titleValue || title.value.length > 500 || !Number.isInteger(reminderValue) || reminderValue < 0 || reminderValue > 10080 || !Number.isInteger(graceValue) || graceValue < 0 || graceValue > 1440) throw new Error("required");
      const dueAt = due.value();
      let payload;
      let list;
      let lesson = null;
      let lessonLabel = "";
      if (draft.intent === "homework_create") {
        list = checklist.value.split(/\r?\n/).map((value) => value.trim()).filter(Boolean);
        if (list.length > 50 || list.some((value) => value.length > 200)) throw new Error("checklist");
        if (lessonSelect.value !== "") {
          const choice = lessonSelect._choices[Number(lessonSelect.value)];
          if (!choice || !lessonStillCurrent(card, target.id, choice.payload)) throw new Error("lesson");
          lesson = clone(choice.payload);
          lessonLabel = choice.label;
        }
        payload = {
          member: target.id,
          member_revision: target.revision,
          title: titleValue,
          due_at: dueAt,
          checklist: list,
          reminder_minutes: reminderValue,
          grace_minutes: graceValue,
          lesson,
        };
      } else {
        const task = currentTask(card, draft.taskId);
        if (!task || task.revision !== draft.taskRevision || task.assignee !== target.id || !REVISABLE.has(task.status)) throw new Error("task");
        list = clone(draft.preservedChecklist);
        lesson = clone(draft.preservedLesson);
        lessonLabel = lesson ? lessonOptions(card, target.id).find((choice) => sameLesson(choice.payload, lesson))?.label || `${lesson.date} · ${lesson.timetable_id}` : "";
        payload = {
          id: task.id,
          revision: task.revision,
          member_revision: target.revision,
          title: titleValue,
          due_at: dueAt,
          reminder_minutes: reminderValue,
          grace_minutes: graceValue,
        };
      }
      draft.memberId = target.id;
      draft.memberRevision = target.revision;
      draft.review = deepFreeze({
        payload,
        childName: target.name || target.id,
        dueLabel: dueLabel(card, dueAt),
        checklist: list,
        lessonLabel,
      });
      notice.hidden = true;
      card.render();
    } catch {
      notice.hidden = false;
    }
  });
  section.append(form);
}

function openPreparation(card, option) {
  const scope = access(card);
  if (!scope || !preparationOptions(card).some((item) => sameLesson(item.payload, option.payload))) return;
  card._schoolWorkDraft = {
    intent: "backpack_start",
    access: scope,
    memberId: option.payload.member,
    memberRevision: option.payload.member_revision,
    review: deepFreeze(clone(option)),
    pending: null,
  };
  card._actionError = null;
  card.render();
}

export function renderSchoolWork(card, body) {
  if (!card || !body || !card._data) return;
  const scope = access(card);
  if (!scope) {
    card._schoolWorkDraft = null;
    return;
  }
  if (card._schoolWorkDraft && !draftAllowed(card, card._schoolWorkDraft, !card._schoolWorkDraft.pending)) {
    card._schoolWorkDraft = null;
    card._actionError = "conflict";
  }
  const copy = copyOf(card);
  const section = node("section", null, "school-work");
  section.append(node("style", STYLE), node("h2", copy.title));
  const guide = node("details");
  guide.append(node("summary", copy.guide));
  guide.append(node("p", copy.help, "sub"), node("p", copy.private_hint, "sub"), node("p", `${copy.timezone}: ${card._data.settings?.timezone || "UTC"}`, "sub"));
  section.append(guide);
  body.append(section);

  const draft = card._schoolWorkDraft;
  if (draft) {
    if (draft.review) appendReview(section, card, draft, copy);
    else renderEditor(section, card, draft, copy);
    return;
  }

  const parent = PARENTS.has(scope.role);
  const homeworkGroup = node("section", null, "item school-work-group");
  homeworkGroup.append(node("h3", copy.homework));
  if (modules(card, "school", "tasks")) {
    const add = card.button(copy.new_homework, () => {
      if (!add.isConnected || card._writing || !sameAccess(card, scope)) return;
      openHomework(card);
    }, true);
    homeworkGroup.append(add);
  }
  const visibleHomework = modules(card, "school", "tasks")
    ? homework(card).filter((item) => parent || item.assignee === scope.actor)
    : [];
  if (!visibleHomework.length) homeworkGroup.append(node("p", copy.no_homework, "sub"));
  const taskList = node("div", null, "school-work-list");
  for (const item of visibleHomework) {
    const row = node("article", null, "item school-work-row");
    row.dataset.schoolHomework = item.id;
    row.append(node("strong", item.title || item.id));
    row.append(node("p", `${copy.child}: ${memberName(card, item.assignee, copy)} · ${copy.status}: ${taskLabel(card, item)}`, "sub"));
    if (item.due_at) row.append(node("p", `${copy.due_label}: ${dueLabel(card, item.due_at)}`, "sub"));
    if (Array.isArray(item.checklist) && item.checklist.length) {
      const list = node("ul");
      for (const entry of item.checklist) list.append(node("li", `${entry?.done ? "✓ " : ""}${entry?.text || ""}`));
      row.append(list);
    }
    if (item.report) row.append(node("p", `${copy.report}: ${item.report}`, "sub"));
    if (item.review_note) row.append(node("p", `${copy.review_note}: ${item.review_note}`, "sub"));
    if (parent && REVISABLE.has(item.status) && child(card, item.assignee)) {
      const edit = card.button(copy.revise_homework, () => {
        if (!edit.isConnected || card._writing || !sameAccess(card, scope)) return;
        const current = currentTask(card, item.id);
        if (current?.revision !== item.revision) return;
        openHomework(card, current);
      });
      row.append(edit);
    }
    taskList.append(row);
  }
  homeworkGroup.append(taskList, node("p", copy.private_hint, "sub"));
  section.append(homeworkGroup);

  const preparationGroup = node("section", null, "item school-work-group");
  preparationGroup.append(node("h3", copy.preparation), node("p", copy.routines_hint, "sub"));
  if (modules(card, "school", "routines")) {
    const options = preparationOptions(card);
    if (!options.length) preparationGroup.append(node("p", copy.no_preparation, "sub"));
    for (const option of options) {
      const row = node("article", null, "item school-work-row");
      row.dataset.schoolPreparationOption = `${option.payload.timetable_id}:${option.payload.date}`;
      row.append(node("strong", option.lessonLabel));
      if (parent) row.append(node("p", `${copy.child}: ${option.childName}`, "sub"));
      row.append(node("p", `${copy.routine}: ${option.routineTitle} (${copy.version} ${option.payload.routine_revision})`, "sub"));
      const start = card.button(copy.start_preparation, () => {
        if (!start.isConnected || card._writing || !sameAccess(card, scope)) return;
        openPreparation(card, option);
      });
      row.append(start);
      preparationGroup.append(row);
    }
  }
  const history = node("details");
  history.append(node("summary", copy.preparation_history));
  const rows = preparations(card).filter((item) => parent || item.member === scope.actor);
  if (!rows.length) history.append(node("p", copy.no_preparation_history, "sub"));
  for (const item of rows) {
    const row = node("article", null, "item school-work-row");
    row.dataset.schoolPreparation = item.id;
    row.append(node("strong", `${item.date} · ${memberName(card, item.member, copy)}`));
    row.append(node("p", `${copy.status}: ${card.t?.[item.status] || copy[`status_${item.status}`] || item.status} · ${copy.run_status}: ${card.t?.[item.run_status] || copy[`status_${item.run_status}`] || item.run_status}`, "sub"));
    if (item.run_id) row.append(node("p", `${copy.run}: ${item.run_id}`, "sub"));
    history.append(row);
  }
  preparationGroup.append(history);
  section.append(preparationGroup);
}
