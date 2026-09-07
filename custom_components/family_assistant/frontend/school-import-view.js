/* Explicit calendar read into an unsaved, still-reviewed school draft. */

import { SCHOOL_IMPORT_COPY } from "./school-import-copy.js";

const node = (tag, text) => {
  const result = document.createElement(tag);
  if (text !== undefined) result.textContent = text;
  return result;
};
const clone = (value) => JSON.parse(JSON.stringify(value));

export function calendarDraft(result, week, timezone) {
  if (!result || result.saved !== false || result.timezone !== timezone || result.valid_from !== week ||
      !/^\d{4}-\d{2}-\d{2}$/.test(week) || !Array.isArray(result.lessons) ||
      result.lessons.length < 1 || result.lessons.length > 70 || result.count !== result.lessons.length)
    throw new Error("invalid");
  const date = new Date(`${week}T00:00:00Z`);
  if (Number.isNaN(date.valueOf()) || date.getUTCDay() !== 1 || date.toISOString().slice(0, 10) !== week)
    throw new Error("invalid");
  date.setUTCDate(date.getUTCDate() + 6);
  if (result.valid_until !== date.toISOString().slice(0, 10)) throw new Error("invalid");
  const lessons = result.lessons.map((lesson) => {
    if (!lesson || !Number.isInteger(lesson.weekday) || lesson.weekday < 0 || lesson.weekday > 6 ||
        typeof lesson.subject !== "string" || !lesson.subject.trim() || lesson.subject.length > 120 ||
        typeof lesson.room !== "string" || lesson.room.length > 80 ||
        typeof lesson.start !== "string" || typeof lesson.end !== "string" ||
        !/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(lesson.start) ||
        !/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(lesson.end) || lesson.start >= lesson.end ||
        !Array.isArray(lesson.materials) || lesson.materials.length !== 0) throw new Error("invalid");
    return { weekday: String(lesson.weekday), start: lesson.start, end: lesson.end,
      subject: lesson.subject, room: lesson.room, materials: "" };
  });
  return { valid_from: result.valid_from, valid_until: result.valid_until, lessons, exceptions: "" };
}

export function renderSchoolImport(card, draft, parent, allowed) {
  const lang = (card._config?.language || card._hass?.language || "en").split("-")[0];
  const copy = SCHOOL_IMPORT_COPY[lang] || SCHOOL_IMPORT_COPY.en;
  const area = node("fieldset");
  area.dataset.schoolImport = "calendar";
  area.append(node("legend", copy.title), node("p", copy.help));
  const calendarLabel = node("label", copy.calendar);
  const calendar = node("input");
  calendar.name = "calendar_entity";
  calendar.placeholder = "calendar.school";
  calendar.value = draft.calendarEntity || "";
  const suggestions = node("datalist");
  suggestions.id = `school-calendars-${crypto.randomUUID()}`;
  calendar.setAttribute("list", suggestions.id);
  for (const [id, state] of Object.entries(card._hass?.states || {})
    .filter(([id]) => /^calendar\.[a-z0-9_]{1,120}$/.test(id)).sort(([a], [b]) => a.localeCompare(b)).slice(0, 200)) {
    const option = node("option", state?.attributes?.friendly_name || id);
    option.value = id;
    suggestions.append(option);
  }
  calendarLabel.append(calendar);
  const weekLabel = node("label", copy.week);
  const week = node("input");
  week.name = "calendar_week";
  week.type = "date";
  week.value = draft.calendarWeek || "";
  weekLabel.append(week);
  const load = node("button", draft.calendarPending ? copy.loading : copy.load);
  load.type = "button";
  load.disabled = Boolean(draft.calendarPending);
  for (const [input, key] of [[calendar, "calendarEntity"], [week, "calendarWeek"]]) {
    input.addEventListener("input", () => { if (allowed()) draft[key] = input.value; });
    input.addEventListener("change", () => { if (allowed()) draft[key] = input.value; });
  }
  area.append(calendarLabel, suggestions, weekLabel, load);
  if (draft.calendarStatus) area.append(node("p", copy[draft.calendarStatus] || copy.failure));
  load.addEventListener("click", async () => {
    if (!allowed() || !area.isConnected || draft.calendarPending || card._writing) return;
    const entity = calendar.value;
    const monday = week.value;
    if (!/^calendar\.[a-z0-9_]{1,120}$/.test(entity) || !/^\d{4}-\d{2}-\d{2}$/.test(monday)) {
      draft.calendarStatus = "failure";
      card.render();
      return;
    }
    draft.calendarEntity = entity;
    draft.calendarWeek = monday;
    const timezone = card._data?.settings?.timezone;
    const entry = card._entry;
    const client = card._hass;
    const member = `${draft.memberId}:${draft.memberRevision}`;
    const values = JSON.stringify(draft.values);
    const token = {};
    draft.calendarPending = token;
    draft.calendarStatus = null;
    load.disabled = true;
    load.textContent = copy.loading;
    const current = () => allowed() && card._schoolDraft === draft && draft.kind === "edit" &&
      card._entry === entry && card._hass === client &&
      card._data?.settings?.timezone === timezone &&
      `${draft.memberId}:${draft.memberRevision}` === member &&
      draft.calendarEntity === entity && draft.calendarWeek === monday &&
      JSON.stringify(draft.values) === values;
    try {
      const result = await client.callWS({ type: "family_assistant/school_calendar_preview", entry_id: entry,
        entity_id: entity, week_start: monday });
      if (!current()) return;
      const imported = calendarDraft(result, monday, timezone);
      draft.values = { ...clone(draft.values), ...imported };
      draft.reviewed = false;
      draft.calendarStatus = "loaded";
    } catch {
      if (current()) draft.calendarStatus = "failure";
    } finally {
      if (draft.calendarPending === token) draft.calendarPending = null;
      if (allowed() && card._schoolDraft === draft) card.render();
    }
  });
  parent.append(area);
}
