/* Role-scoped school timetable and upcoming lesson UI. */

import { SCHOOL_COPY } from "./school-copy.js";
import { renderSchoolImport } from "./school-import-view.js";

const PARENTS = new Set(["owner", "parent"]);
const VISIBLE_ROLES = new Set(["owner", "parent", "child"]);
const WEEKDAYS = [
  "monday",
  "tuesday",
  "wednesday",
  "thursday",
  "friday",
  "saturday",
  "sunday",
];
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const CLOCK = /^(?:[01]\d|2[0-3]):[0-5]\d$/;

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
  return SCHOOL_COPY[language.split("-")[0]] || SCHOOL_COPY.en;
};
const text = (copy, key, fallback) => copy[key] || fallback;

const LOCAL_STYLE = `
  .school-section,.school-group{display:grid;gap:12px}.school-scope{margin-bottom:4px}
  .school-form{display:grid;gap:12px}.school-fields,.school-lesson-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
  .school-fields .wide,.school-lesson-fields .wide{grid-column:1/-1}.school-lessons{display:grid;gap:10px}
  .school-lesson{display:block;min-width:0}.school-lesson>*+*{margin-top:10px}.school-lesson>button{width:auto}
  .school-materials{min-height:70px}.school-review ul,.school-record ul{margin:6px 0;padding-inline-start:20px}
  .school-upcoming{display:grid;gap:8px}.school-history{margin-top:10px}
  @media(max-width:520px){.school-fields,.school-lesson-fields{grid-template-columns:minmax(0,1fr)}.school-fields .wide,.school-lesson-fields .wide{grid-column:auto}}
`;

function validRevision(value) {
  return Number.isSafeInteger(value) && value >= 1;
}

function schoolData(data) {
  const school = data?.school;
  return school && typeof school === "object" ? school : null;
}

function memberById(data, memberId) {
  return (data?.members || []).find((member) => member.id === memberId);
}

function actorAccess(card) {
  const data = card?._data;
  const member = memberById(data, data?.actor);
  if (
    !data?.actor ||
    !VISIBLE_ROLES.has(data?.role) ||
    member?.active !== true ||
    member?.role !== data.role ||
    !validRevision(member?.revision) ||
    !data?.settings?.modules?.includes("school") ||
    !schoolData(data)
  )
    return null;
  return {
    generation: card._generation,
    entry: card._entry,
    actor: data.actor,
    role: data.role,
    actorRevision: member.revision,
  };
}

function accessKey(value) {
  return value ? JSON.stringify(Object.values(value)) : "";
}

function sameAccess(card, expected) {
  return (
    Boolean(expected) && accessKey(actorAccess(card)) === accessKey(expected)
  );
}

function records(card) {
  return Array.isArray(card._data?.school?.timetables)
    ? card._data.school.timetables
    : [];
}

function recordById(card, id) {
  return records(card).find((record) => record.id === id);
}

function sameRecord(left, right) {
  return (
    Boolean(left) &&
    Boolean(right) &&
    left.id === right.id &&
    left.revision === right.revision &&
    left.status === right.status &&
    left.member === right.member
  );
}

function childMember(card, memberId) {
  const member = memberById(card._data, memberId);
  return member?.active === true &&
    member.role === "child" &&
    validRevision(member.revision)
    ? member
    : null;
}

function memberSnapshot(card, memberId) {
  const member = memberById(card._data, memberId);
  if (!member || !validRevision(member.revision)) return null;
  return {
    id: member.id,
    revision: member.revision,
    role: member.role,
    active: member.active,
  };
}

function sameMemberSnapshot(card, expected) {
  return (
    Boolean(expected) &&
    JSON.stringify(memberSnapshot(card, expected.id)) ===
      JSON.stringify(expected)
  );
}

function availableChild(card, memberId) {
  const member = childMember(card, memberId);
  return (
    member &&
    !records(card).some(
      (record) => record.member === memberId && record.status === "active",
    )
  );
}

function routineOptions(card, memberId) {
  if (!card._data?.settings?.modules?.includes("routines")) return [];
  const members = card._data?.members || [];
  const usable = (id) => {
    const member = members.find((candidate) => candidate.id === id);
    return member?.active === true && member.role !== "guest";
  };
  return (card._data?.routines?.templates || []).filter((template) => {
    const creator = members.find((member) => member.id === template.creator);
    return (
      template?.enabled === true &&
      validRevision(template.revision) &&
      Array.isArray(template.assignees) &&
      template.assignees.includes(memberId) &&
      creator?.active === true &&
      PARENTS.has(creator.role) &&
      Array.isArray(template.steps) &&
      template.steps.every((step) => !step.assignee || usable(step.assignee))
    );
  });
}

function routineStillCurrent(card, memberId, link) {
  if (link === null) return true;
  return routineOptions(card, memberId).some(
    (template) =>
      template.id === link.id && template.revision === link.revision,
  );
}

function draftAllowed(card, draft, exactRecord = true) {
  if (!sameAccess(card, draft?.access) || !PARENTS.has(card._data.role))
    return false;
  // A dispatched operation is immutable and may already have committed. Keep its
  // exact retry handle even if the target record, child, or routine advances.
  if (draft.pending) return true;
  const intent = draft.intent || draft.kind;
  if (intent === "archive") {
    const current = recordById(card, draft.recordId);
    return (
      Boolean(current) &&
      sameMemberSnapshot(card, draft.memberSnapshot) &&
      (!exactRecord ||
        (current.status === "active" && sameRecord(draft.source, current)))
    );
  }
  const member = childMember(card, draft.memberId);
  if (!member || member.revision !== draft.memberRevision) return false;
  if (
    !draft.values?.backpack_decision_required &&
    !routineStillCurrent(
      card,
      draft.memberId,
      draft.values?.backpack_routine ?? null,
    )
  )
    return false;
  if (intent === "edit") {
    const current = recordById(card, draft.recordId);
    return (
      Boolean(current) &&
      current.status === "active" &&
      (!exactRecord || sameRecord(draft.source, current))
    );
  }
  return (
    intent === "new" &&
    (Boolean(draft.pending) || Boolean(availableChild(card, draft.memberId)))
  );
}

function refreshProjection(data) {
  const members = (data?.members || []).map(
    ({ id, name, role, active, revision }) => ({
      id,
      name,
      role,
      active,
      revision,
    }),
  );
  const templates = (data?.routines?.templates || []).map(
    ({ id, revision, title, enabled, assignees, creator, steps }) => ({
      id,
      revision,
      title,
      enabled,
      assignees,
      creator,
      steps: (steps || []).map(({ assignee }) => ({
        assignee: assignee || null,
      })),
    }),
  );
  return {
    actor: data?.actor ?? null,
    role: data?.role ?? null,
    enabled: Boolean(data?.settings?.modules?.includes("school")),
    routinesEnabled: Boolean(data?.settings?.modules?.includes("routines")),
    timezone: data?.settings?.timezone ?? null,
    school: data?.school ?? null,
    members,
    templates,
  };
}

export function reconcileSchoolRefresh(card, previousData) {
  if (!card) return false;
  const projectionChanged =
    JSON.stringify(refreshProjection(previousData)) !==
    JSON.stringify(refreshProjection(card._data));
  let forceRender =
    projectionChanged &&
    Boolean(
      card._schoolDraft || card.shadowRoot?.querySelector(".school-section"),
    );
  if (
    card._schoolDraft &&
    !draftAllowed(card, card._schoolDraft, !card._schoolDraft.pending)
  ) {
    card._schoolDraft = null;
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
  const parsed = new Date(`${value}T00:00:00Z`);
  if (
    year < 1 ||
    year > 9999 ||
    Number.isNaN(parsed.valueOf()) ||
    parsed.getUTCFullYear() !== year ||
    parsed.getUTCMonth() + 1 !== month ||
    parsed.getUTCDate() !== day
  )
    throw new Error(key);
  return value;
}

function clock(value, key) {
  if (typeof value !== "string" || !CLOCK.test(value)) throw new Error(key);
  return value;
}

function clockMinutes(value) {
  const [hour, minute] = value.split(":").map(Number);
  return hour * 60 + minute;
}

function materials(value) {
  const result = String(value ?? "")
    .split(/\r?\n/)
    .filter((item) => item.trim());
  if (result.length > 12) throw new Error("materials");
  const seen = new Set();
  return result.map((item) => {
    if (item.length > 120) throw new Error("materials");
    const normalized = item.trim();
    const identity = normalized.toLocaleLowerCase("en-US");
    if (seen.has(identity)) throw new Error("materials");
    seen.add(identity);
    return normalized;
  });
}

function exceptions(value, validFrom, validUntil) {
  const result = String(value ?? "")
    .split(/\r?\n/)
    .filter((item) => item.trim())
    .map((item) => dateValue(item.trim(), "exceptions"));
  if (result.length > 366 || new Set(result).size !== result.length)
    throw new Error("exceptions");
  if (
    result.some(
      (item) => item < validFrom || (validUntil !== null && item > validUntil),
    )
  )
    throw new Error("exceptions");
  return result;
}

function timetablePayload(card, draft) {
  const member = childMember(card, draft.memberId);
  if (!member || member.revision !== draft.memberRevision)
    throw new Error("member");
  const values = draft.values;
  if (values.backpack_decision_required) throw new Error("backpack_routine");
  const validFrom = dateValue(values.valid_from, "valid_from");
  const validUntil = values.valid_until
    ? dateValue(values.valid_until, "valid_until")
    : null;
  if (validUntil !== null && validUntil < validFrom)
    throw new Error("valid_until");
  if (
    !Array.isArray(values.lessons) ||
    values.lessons.length < 1 ||
    values.lessons.length > 70
  )
    throw new Error("lessons");
  let materialCount = 0;
  const occupied = new Map();
  const lessons = values.lessons.map((lesson) => {
    const weekday = Number(lesson.weekday);
    if (!Number.isInteger(weekday) || weekday < 0 || weekday > 6)
      throw new Error("weekday");
    const start = clock(lesson.start, "start");
    const end = clock(lesson.end, "end");
    const startMinutes = clockMinutes(start);
    const endMinutes = clockMinutes(end);
    if (startMinutes >= endMinutes) throw new Error("end");
    const intervals = occupied.get(weekday) || [];
    if (
      intervals.some(
        ([otherStart, otherEnd]) =>
          startMinutes < otherEnd && otherStart < endMinutes,
      )
    )
      throw new Error("lessons");
    intervals.push([startMinutes, endMinutes]);
    occupied.set(weekday, intervals);
    const lessonMaterials = materials(lesson.materials);
    materialCount += lessonMaterials.length;
    if (materialCount > 200) throw new Error("materials");
    return {
      weekday,
      start,
      end,
      subject: rawText(lesson.subject, "subject", 120),
      room: rawText(lesson.room, "room", 80, false),
      materials: lessonMaterials,
    };
  });
  const link = values.backpack_routine ?? null;
  if (!routineStillCurrent(card, draft.memberId, link))
    throw new Error("backpack_routine");
  return {
    ...(draft.intent === "edit"
      ? { id: draft.recordId, revision: draft.source.revision }
      : {}),
    member: draft.memberId,
    member_revision: draft.memberRevision,
    title: rawText(values.title, "title", 120),
    valid_from: validFrom,
    valid_until: validUntil,
    lessons,
    backpack_routine:
      link === null ? null : { id: link.id, revision: link.revision },
    exceptions: exceptions(values.exceptions, validFrom, validUntil),
  };
}

function blankLesson() {
  return {
    weekday: "0",
    start: "",
    end: "",
    subject: "",
    room: "",
    materials: "",
  };
}

function valuesFrom(record) {
  const currentRoutine = record?.backpack_routine_current;
  const rawRoutine = record?.backpack_routine;
  const unavailableRoutine =
    rawRoutine && !currentRoutine
      ? { id: rawRoutine.id, revision: rawRoutine.revision }
      : null;
  return {
    title: record?.title || "",
    valid_from: record?.valid_from || "",
    valid_until: record?.valid_until || "",
    exceptions: (record?.exceptions || []).join("\n"),
    lessons: (record?.lessons || [blankLesson()]).map((lesson) => ({
      weekday: String(lesson.weekday),
      start: lesson.start || "",
      end: lesson.end || "",
      subject: lesson.subject || "",
      room: lesson.room || "",
      materials: (lesson.materials || []).join("\n"),
    })),
    backpack_routine: currentRoutine
      ? {
          id: currentRoutine.id,
          revision: currentRoutine.revision,
        }
      : null,
    backpack_routine_unavailable: unavailableRoutine,
    backpack_decision_required: Boolean(unavailableRoutine),
  };
}

function input(parent, labelText, name, value, type = "text") {
  const label = node("label", labelText);
  const control = document.createElement("input");
  control.name = name;
  control.type = type;
  control.value = value ?? "";
  label.append(control);
  parent.append(label);
  return control;
}

function textarea(parent, labelText, name, value, hint) {
  const label = node("label", labelText);
  const control = document.createElement("textarea");
  control.name = name;
  control.value = value ?? "";
  label.append(control);
  if (hint) label.append(node("span", hint, "sub"));
  parent.append(label);
  return control;
}

function memberName(card, memberId, copy) {
  return memberById(card._data, memberId)?.name || copy.unknown_member;
}

function routineName(card, link, copy) {
  if (!link) return copy.backpack_none;
  return (
    (card._data?.routines?.templates || []).find(
      (template) =>
        template.id === link.id && template.revision === link.revision,
    )?.title || copy.backpack_none
  );
}

function appendLessonSummary(parent, lesson, copy) {
  const item = node("li");
  item.append(
    node(
      "strong",
      `${text(copy, WEEKDAYS[lesson.weekday], WEEKDAYS[lesson.weekday])} · ${lesson.start}–${lesson.end} · ${lesson.subject}`,
    ),
  );
  if (lesson.room) item.append(node("span", ` · ${lesson.room}`, "sub"));
  if (lesson.materials?.length)
    item.append(
      node("div", `${copy.materials}: ${lesson.materials.join(", ")}`, "sub"),
    );
  parent.append(item);
}

export function renderSchool(card, body) {
  if (!card || !body || !card._data) return;
  const access = actorAccess(card);
  if (!access) {
    card._schoolDraft = null;
    return;
  }
  if (
    card._schoolDraft &&
    !draftAllowed(card, card._schoolDraft, !card._schoolDraft.pending)
  ) {
    card._schoolDraft = null;
    card._actionError = "conflict";
  }
  const copy = copyOf(card);
  const parent = PARENTS.has(access.role);
  const detached = () => !body.isConnected;
  const guard = (control, draft = null, exact = true) => {
    if (draft && card._schoolDraft !== draft) return false;
    if (
      !sameAccess(card, draft?.access || access) ||
      (draft && !draftAllowed(card, draft, exact && !draft.pending))
    ) {
      card._schoolDraft = null;
      card._actionError = "conflict";
      if (!detached() && control?.isConnected) card.render();
      return false;
    }
    return !detached() && Boolean(control?.isConnected) && !card._writing;
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
  const open = (kind, record = null, member = null) => {
    if (!parent || !guard(body)) return;
    if (kind === "archive") {
      if (
        !record ||
        !sameRecord(record, recordById(card, record.id)) ||
        record.status !== "active"
      )
        return;
      card._schoolDraft = {
        kind: "archive_edit",
        intent: "archive",
        access: deepFreeze(clone(access)),
        recordId: record.id,
        source: deepFreeze(clone(record)),
        targetName: memberName(card, record.member, copy),
        memberSnapshot: deepFreeze(memberSnapshot(card, record.member)),
        title: record.title,
        reason: "",
        reviewed: false,
      };
    } else {
      const target = member || childMember(card, record?.member);
      if (
        !target ||
        (record && !sameRecord(record, recordById(card, record.id)))
      )
        return;
      card._schoolDraft = {
        kind: "edit",
        intent: kind,
        access: deepFreeze(clone(access)),
        recordId: record?.id || null,
        source: record ? deepFreeze(clone(record)) : null,
        memberId: target.id,
        memberRevision: target.revision,
        targetName: target.name,
        values: valuesFrom(record),
        reviewed: false,
      };
    }
    card._actionError = null;
    card.render();
  };
  const close = (draft) => {
    if (!guard(body, draft, false)) return;
    card._schoolDraft = null;
    card._actionError = null;
    card.render();
  };
  const run = async (draft, action, payload) => {
    if (!guard(body, draft, !draft.pending)) return;
    if (!draft.pending)
      draft.pending = deepFreeze({
        action,
        payload: clone(payload),
        operation_id: crypto.randomUUID(),
      });
    const pending = draft.pending;
    await card.command(pending.action, pending.payload, pending.operation_id);
    if (
      sameAccess(card, draft.access) &&
      card._schoolDraft === draft &&
      !card._actionError
    ) {
      card._schoolDraft = null;
      card.render();
    }
  };

  const section = node("section", null, "school-section");
  section.append(node("style", LOCAL_STYLE), node("h2", copy.title));
  section.append(node("p", copy.help, "sub"));
  section.append(
    node(
      "p",
      `${copy.timezone}: ${card._data.settings?.timezone || "UTC"}`,
      "sub school-scope",
    ),
  );
  const draft = card._schoolDraft;
  if (!draft) {
    const upcoming = (
      Array.isArray(card._data.school.upcoming)
        ? card._data.school.upcoming
        : []
    ).filter((item) => parent || item.member === access.actor);
    const agenda = node("section", null, "item school-group");
    agenda.append(node("h3", copy.upcoming));
    if (!upcoming.length) agenda.append(node("p", copy.no_upcoming, "sub"));
    else {
      const list = node("div", null, "school-upcoming");
      for (const item of upcoming) {
        const row = node("article", null, "item");
        row.dataset.schoolUpcoming = item.id;
        row.append(
          node(
            "strong",
            `${item.date} · ${item.start}–${item.end} · ${item.subject}`,
          ),
        );
        if (parent)
          row.append(
            node(
              "p",
              `${copy.member}: ${memberName(card, item.member, copy)}`,
              "sub",
            ),
          );
        if (item.room) row.append(node("p", item.room, "sub"));
        if (Array.isArray(item.materials) && item.materials.length)
          row.append(
            node("p", `${copy.materials}: ${item.materials.join(", ")}`, "sub"),
          );
        if (item.backpack_routine)
          row.append(
            node(
              "p",
              `${copy.backpack_routine}: ${item.backpack_routine.title}`,
              "sub",
            ),
          );
        list.append(row);
      }
      agenda.append(list);
    }
    section.append(agenda);
    if (parent) {
      const currentActive = new Set(
        records(card)
          .filter((record) => record.status === "active")
          .map((record) => record.member),
      );
      const availableChildren = (card._data.members || []).filter(
        (member) =>
          availableChild(card, member.id) && !currentActive.has(member.id),
      );
      if (availableChildren.length)
        section.append(
          localButton(
            copy.new_timetable,
            () => open("new", null, availableChildren[0]),
            true,
          ),
        );
      const timetables = node("section", null, "school-group");
      timetables.append(node("h3", copy.timetables));
      if (!records(card).length)
        timetables.append(node("p", copy.no_timetables, "sub"));
      for (const record of records(card)) {
        const item = node("article", null, "item school-record");
        item.dataset.schoolTimetable = record.id;
        item.append(
          node("strong", record.title),
          node(
            "p",
            `${copy.member}: ${memberName(card, record.member, copy)} · ${text(copy, `status_${record.status}`, record.status)} · ${record.valid_from}–${record.valid_until || "∞"}`,
            "sub",
          ),
        );
        const lessons = node("ul");
        for (const lesson of record.lessons || [])
          appendLessonSummary(lessons, lesson, copy);
        item.append(lessons);
        const routine = record.backpack_routine_current;
        if (routine)
          item.append(
            node("p", `${copy.backpack_routine}: ${routine.title}`, "sub"),
          );
        if (Array.isArray(record.history) && record.history.length) {
          const history = node("details", null, "school-history");
          history.append(node("summary", copy.history));
          for (const event of record.history)
            history.append(
              node(
                "p",
                [
                  event.at,
                  memberName(card, event.actor, copy),
                  text(copy, `action_${event.action}`, event.action),
                  event.reason,
                ]
                  .filter(Boolean)
                  .join(" · "),
                "sub",
              ),
            );
          item.append(history);
        }
        const actions = node("div", null, "actions");
        if (record.status === "active") {
          if (childMember(card, record.member))
            actions.append(localButton(copy.edit, () => open("edit", record)));
          actions.append(
            localButton(copy.archive, () => open("archive", record)),
          );
        }
        if (actions.children.length) item.append(actions);
        timetables.append(item);
      }
      section.append(timetables);
    } else section.append(node("p", copy.readonly, "sub"));
  } else if (draft.kind === "edit") {
    const form = node("form", null, "item school-form");
    form.dataset.schoolForm = "edit";
    form.append(
      node("h3", draft.intent === "new" ? copy.new_timetable : copy.edit),
    );
    const fields = node("div", null, "school-fields");
    const memberLabel = node("label", copy.member);
    const memberSelect = document.createElement("select");
    memberSelect.name = "member";
    const selectable =
      draft.intent === "edit"
        ? [childMember(card, draft.memberId)].filter(Boolean)
        : (card._data.members || []).filter((member) =>
            availableChild(card, member.id),
          );
    for (const member of selectable) {
      const option = node("option", member.name);
      option.value = member.id;
      option.selected = member.id === draft.memberId;
      memberSelect.append(option);
    }
    memberSelect.disabled = draft.intent === "edit";
    memberLabel.append(memberSelect);
    fields.append(memberLabel);
    const controls = {
      title: input(fields, copy.timetable_title, "title", draft.values.title),
      valid_from: input(
        fields,
        copy.valid_from,
        "valid_from",
        draft.values.valid_from,
        "date",
      ),
      valid_until: input(
        fields,
        copy.valid_until,
        "valid_until",
        draft.values.valid_until,
        "date",
      ),
      exceptions: textarea(
        fields,
        copy.exceptions,
        "exceptions",
        draft.values.exceptions,
        copy.exceptions_hint,
      ),
    };
    controls.exceptions.parentElement.classList.add("wide");
    const routineLabel = node("label", copy.backpack_routine);
    const routineSelect = document.createElement("select");
    routineSelect.name = "backpack_routine";
    const none = node("option", copy.backpack_none);
    none.value = "";
    routineSelect.append(none);
    if (draft.values.backpack_decision_required) {
      const unavailable = draft.values.backpack_routine_unavailable;
      const option = node(
        "option",
        `${copy.backpack_unavailable}: ${unavailable.id} · ${copy.revision} ${unavailable.revision}`,
      );
      option.value = "__unavailable__";
      option.selected = true;
      option.disabled = true;
      routineSelect.append(option);
    }
    for (const template of routineOptions(card, draft.memberId)) {
      const option = node("option", template.title);
      option.value = JSON.stringify([template.id, template.revision]);
      option.selected =
        draft.values.backpack_routine?.id === template.id &&
        draft.values.backpack_routine?.revision === template.revision;
      routineSelect.append(option);
    }
    routineLabel.append(routineSelect, node("span", copy.backpack_hint, "sub"));
    if (draft.values.backpack_decision_required)
      routineLabel.append(
        node("span", copy.backpack_unavailable_hint, "notice"),
      );
    fields.append(routineLabel);
    form.append(fields);
    renderSchoolImport(card, draft, form, () =>
      card._schoolDraft === draft && sameAccess(card, draft.access) &&
      draftAllowed(card, draft) && !card._writing,
    );
    const lessons = node("div", null, "school-lessons");
    lessons.append(node("h4", copy.lessons));
    draft.values.lessons.forEach((lesson, index) => {
      const row = node("fieldset", null, "school-lesson");
      row.dataset.schoolLesson = String(index);
      row.append(node("legend", `${copy.lessons} ${index + 1}`));
      const rowFields = node("div", null, "school-lesson-fields");
      const weekdayLabel = node("label", copy.weekday);
      const weekday = document.createElement("select");
      weekday.name = "weekday";
      WEEKDAYS.forEach((key, day) => {
        const option = node("option", text(copy, key, key));
        option.value = String(day);
        option.selected = lesson.weekday === String(day);
        weekday.append(option);
      });
      weekdayLabel.append(weekday);
      rowFields.append(weekdayLabel);
      const rowControls = {
        weekday,
        start: input(rowFields, copy.start, "start", lesson.start, "time"),
        end: input(rowFields, copy.end, "end", lesson.end, "time"),
        subject: input(rowFields, copy.subject, "subject", lesson.subject),
        room: input(rowFields, copy.room, "room", lesson.room),
        materials: textarea(
          rowFields,
          copy.materials,
          "materials",
          lesson.materials,
          copy.materials_hint,
        ),
      };
      rowControls.materials.classList.add("school-materials");
      rowControls.materials.parentElement.classList.add("wide");
      row.append(rowFields);
      for (const [key, control] of Object.entries(rowControls)) {
        control.addEventListener("input", () => {
          if (guard(control, draft)) lesson[key] = control.value;
        });
        control.addEventListener("change", () => {
          if (guard(control, draft)) lesson[key] = control.value;
        });
      }
      if (draft.values.lessons.length > 1)
        row.append(
          localButton(
            copy.remove_lesson,
            () => {
              draft.values.lessons.splice(index, 1);
              card.render();
            },
            false,
            draft,
          ),
        );
      lessons.append(row);
    });
    if (draft.values.lessons.length < 70)
      lessons.append(
        localButton(
          copy.add_lesson,
          () => {
            draft.values.lessons.push(blankLesson());
            card.render();
          },
          false,
          draft,
        ),
      );
    form.append(lessons);
    for (const [key, control] of Object.entries(controls)) {
      control.addEventListener("input", () => {
        if (guard(control, draft)) draft.values[key] = control.value;
      });
      control.addEventListener("change", () => {
        if (guard(control, draft)) draft.values[key] = control.value;
      });
    }
    memberSelect.addEventListener("change", () => {
      if (!guard(memberSelect, draft)) return;
      const target = childMember(card, memberSelect.value);
      if (!target || draft.intent !== "new") return;
      draft.memberId = target.id;
      draft.memberRevision = target.revision;
      draft.targetName = target.name;
      draft.values.backpack_routine = null;
      card.render();
    });
    routineSelect.addEventListener("change", () => {
      if (!guard(routineSelect, draft)) return;
      if (!routineSelect.value) {
        draft.values.backpack_routine = null;
        draft.values.backpack_decision_required = false;
      } else {
        let id;
        let revision;
        try {
          [id, revision] = JSON.parse(routineSelect.value);
        } catch {
          card._schoolDraft = null;
          card._actionError = "conflict";
          card.render();
          return;
        }
        const template = routineOptions(card, draft.memberId).find(
          (candidate) => candidate.id === id && candidate.revision === revision,
        );
        if (!template) {
          card._schoolDraft = null;
          card._actionError = "conflict";
          card.render();
          return;
        }
        draft.values.backpack_routine = {
          id: template.id,
          revision: template.revision,
        };
        draft.values.backpack_decision_required = false;
      }
    });
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
        draft.payload = deepFreeze(timetablePayload(card, draft));
        draft.routineTitle = routineName(
          card,
          draft.payload.backpack_routine,
          copy,
        );
        draft.kind = "review";
        draft.reviewed = false;
        card._actionError = null;
        card.render();
      } catch {
        card._actionError = "invalid_field";
        card.render();
      }
    });
    section.append(form);
  } else if (draft.kind === "archive_edit") {
    const form = node("form", null, "item school-form");
    form.dataset.schoolForm = "archive_edit";
    form.append(
      node("h3", copy.archive_title),
      node("p", `${draft.targetName} · ${draft.title}`, "sub"),
    );
    const reason = input(form, copy.reason, "reason", draft.reason);
    reason.maxLength = 500;
    reason.addEventListener("input", () => {
      if (guard(reason, draft)) draft.reason = reason.value;
    });
    reason.addEventListener("change", () => {
      if (guard(reason, draft)) draft.reason = reason.value;
    });
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
        draft.payload = deepFreeze({
          id: draft.recordId,
          revision: draft.source.revision,
          reason: rawText(reason.value, "reason", 500),
        });
        draft.reason = draft.payload.reason;
        draft.kind = "archive_review";
        draft.reviewed = false;
        card._actionError = null;
        card.render();
      } catch {
        card._actionError = "invalid_field";
        card.render();
      }
    });
    section.append(form);
  } else if (draft.kind === "archive_review" || draft.kind === "review") {
    const form = node("form", null, "item school-form");
    form.dataset.schoolForm = draft.kind;
    if (draft.kind === "archive_review") {
      form.append(
        node("h3", copy.archive_title),
        node("p", `${draft.targetName} · ${draft.title}`, "sub"),
        node("p", `${copy.reason}: ${draft.payload.reason}`, "sub"),
      );
    } else {
      form.append(
        node("h3", copy.review_title),
        node("p", `${draft.targetName} · ${draft.payload.title}`, "sub"),
      );
      const review = node("div", null, "school-review");
      review.append(
        node("p", `${copy.valid_from}: ${draft.payload.valid_from}`),
        node("p", `${copy.valid_until}: ${draft.payload.valid_until || "—"}`),
        node(
          "p",
          `${copy.exceptions}: ${draft.payload.exceptions.join(", ") || copy.none}`,
        ),
        node("p", `${copy.backpack_routine}: ${draft.routineTitle}`),
      );
      const list = node("ul");
      for (const lesson of draft.payload.lessons)
        appendLessonSummary(list, lesson, copy);
      review.append(list);
      form.append(review);
    }
    const label = node("label", null, "check");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.name = "reviewed";
    checkbox.checked = draft.reviewed;
    checkbox.disabled = Boolean(draft.pending);
    label.append(
      checkbox,
      node(
        "span",
        draft.kind === "archive_review"
          ? copy.confirm_archive
          : copy.confirm_save,
      ),
    );
    form.append(label);
    checkbox.addEventListener("change", () => {
      if (guard(checkbox, draft) && !draft.pending)
        draft.reviewed = checkbox.checked;
    });
    const actions = node("div", null, "actions");
    const submit = localButton(
      draft.pending
        ? copy.retry
        : draft.kind === "archive_review"
          ? copy.archive
          : draft.intent === "new"
            ? copy.create
            : copy.save,
      () => {},
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
      if (!guard(form, draft, !draft.pending)) return;
      if (!draft.pending && !checkbox.checked) return;
      draft.reviewed = true;
      if (draft.kind === "archive_review")
        void run(draft, "school.timetable_archive", draft.payload);
      else void run(draft, "school.timetable_save", draft.payload);
    });
    section.append(form);
  }
  body.append(section);
}
