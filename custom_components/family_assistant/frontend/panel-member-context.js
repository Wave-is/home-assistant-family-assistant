/* Optional member_id is a UI scope, never an impersonation or authorization grant.
   Keep the server projection intact so actor and recipient checks remain valid. */
import {PANEL_COPY} from "./panel-copy.js";

export const MEMBER_CONTEXT_VIEWS = ["school", "alarms", "digests"];
export function memberContextId(card) {
  return typeof card?._config?.member_id === "string" ? card._config.member_id : null;
}
export function inMemberContext(card, id) {
  const selected = memberContextId(card);
  return selected === null || selected === id;
}
export function memberContextAvailable(card) {
  const id = memberContextId(card);
  if (id === null) return true;
  const member = card._data?.members?.find(member => member.id === id);
  return Boolean(member?.active && (["owner", "parent"].includes(card._data?.role) || id === card._data?.actor));
}
export function renderMemberContext(card, body) {
  const id = memberContextId(card);
  if (id === null) return true;
  const language = (card._config?.language || card._hass?.language || "en").split("-")[0];
  const copy = PANEL_COPY[language] || PANEL_COPY.en;
  const member = card._data?.members?.find(member => member.id === id);
  const box = document.createElement("section");box.className = "notice member-context";box.dataset.memberContext = id;
  const title = document.createElement("strong");title.textContent = `${copy.memberContext}: ${member?.name || copy.unavailable}`;box.append(title);
  const detail = document.createElement("p");
  if (!memberContextAvailable(card)) {
    detail.textContent = copy.memberContextUnavailable;box.append(detail);box.setAttribute("role", "status");body.append(box);return false;
  }
  if (card._view === "digests" && id !== card._data.actor) {
    detail.textContent = copy.digestSelfOnly;box.append(detail);box.setAttribute("role", "status");body.append(box);return false;
  }
  detail.textContent = card._view === "school" ? copy.schoolMemberContext : copy.memberContextHint;box.append(detail);body.append(box);return true;
}
export function memberContextCommandAllowed(card, action, payload) {
  const id = memberContextId(card);
  if (id === null) return true;
  if (!memberContextAvailable(card)) return false;
  const find = (items, key = "member") => (items || []).find(item => item.id === payload.id)?.[key];
  if (card._view === "alarms") {
    if (action === "alarms.save") return payload.member === id && (!payload.id || find(card._data.alarms) === id);
    if (["alarms.enable", "alarms.test"].includes(action)) return find(card._data.alarms) === id;
    if (["alarms.answer", "alarms.cancel"].includes(action)) return find(card._data.alarm_runs) === id;
  }
  if (card._view === "school") {
    if (action === "school.timetable_save") return payload.member === id && (!payload.id || find(card._data.school?.timetables) === id);
    if (["school.homework_create", "school.backpack_start", "school.preparation_reminder_access_set"].includes(action)) return payload.member === id;
    if (action === "school.timetable_archive") return find(card._data.school?.timetables) === id;
    if (action === "school.homework_revise") return find(card._data.school?.homework, "assignee") === id;
  }
  return card._view === "digests" && action === "digests.access_set" && id === card._data.actor;
}
