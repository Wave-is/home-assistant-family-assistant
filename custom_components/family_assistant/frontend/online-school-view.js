/* Private read-only portal facts; external content is always text or an explicit link. */
import { ONLINE_SCHOOL_COPY } from "./online-school-copy.js";
import { inMemberContext } from "./panel-member-context.js";

const ROLES = new Set(["owner", "parent", "child"]);
const DATE = /^\d{4}-\d{2}-\d{2}$/;
const validRevision = value => Number.isSafeInteger(value) && value >= 1;
const node = (tag, text, className) => {
  const element = document.createElement(tag);
  if (text !== undefined && text !== null) element.textContent = String(text);
  if (className) element.className = className;
  return element;
};
const safeText = (value, limit = 4000) => typeof value === "string" ? value.slice(0, limit) : "";
const list = value => Array.isArray(value) ? value : [];
const STYLE = `
  .online-school{display:grid;gap:14px;margin-bottom:20px}.online-school h3,.online-school h4{margin:0}
  .online-school p{margin:5px 0;overflow-wrap:anywhere}.online-source{display:grid;gap:12px;padding:14px;border:1px solid var(--divider-color,#7774);border-radius:12px;min-width:0}
  .online-meta,.online-lesson{display:grid;gap:7px}.online-lesson{padding:12px;border-inline-start:3px solid var(--primary-color,#168b83);background:var(--secondary-background-color,#f5f5f5);border-radius:6px;min-width:0}
  .online-cancelled{border-inline-start-color:var(--warning-color,#b67d24)}.online-school .online-body{white-space:pre-wrap}
  .online-school .online-days{display:flex;flex-wrap:wrap;gap:8px}.online-school button{min-height:40px;padding:7px 15px}
  .online-school button[aria-pressed=true]{font-weight:700;border-color:var(--primary-color,#168b83)}
  .online-school a{overflow-wrap:anywhere;color:var(--primary-color,#168b83)}.online-school ul{padding-inline-start:20px;margin:5px 0}
  .online-school .online-assignment-link{display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:3;overflow:hidden;line-height:1.4}
  .online-school details{padding-top:6px}.online-school summary{cursor:pointer;font-weight:600;min-height:32px}.online-school li{margin:7px 0;overflow-wrap:anywhere}
  .online-stale{color:var(--warning-color,#9d650d)}@media(max-width:520px){.online-source{padding:10px}.online-lesson{padding:9px}.online-days button{flex:1}}
`;

function actor(card) {
  const data = card?._data;
  const member = list(data?.members).find(row => row.id === data?.actor);
  if (!ROLES.has(data?.role) || member?.active !== true || member.role !== data.role ||
      !validRevision(member.revision) || !data.settings?.modules?.includes("school")) return null;
  return member;
}

function sources(card) {
  if (!actor(card)) return [];
  return list(card._data?.school?.online?.sources).filter(source => {
    if (!source || typeof source.id !== "string") return false;
    const member = list(card._data.members).find(row => row.id === source.member);
    return inMemberContext(card, source.member) && member?.active === true && member.role === "child" &&
      validRevision(member.revision) && source.member_revision === member.revision &&
      validRevision(source.revision) && (card._data.role !== "child" || source.member === card._data.actor) &&
      (card._data.role !== "child" || source.enabled === true);
  }).slice(0, 20);
}

function scope(card, source) {
  const currentActor = actor(card);
  if (!currentActor || !sources(card).some(row => row.id === source.id)) return "";
  return JSON.stringify([card._entry, card._generation, currentActor.id, currentActor.revision,
    currentActor.role, card._config?.member_id, source.id, source.revision, source.member,
    source.member_revision, source.enabled, source.last_success]);
}

function current(card, source, expected, root) {
  const live = sources(card).find(row => row.id === source.id);
  return root.isConnected && !!live && expected !== "" && scope(card, live) === expected;
}

export function onlineSchoolSafeLink(value) {
  if (typeof value !== "string" || value.length > 2048 || /[\s\\]/.test(value)) return null;
  try {
    const url = new URL(value);
    const host = url.hostname.toLowerCase().replace(/\.$/, "");
    if (url.protocol !== "https:" || url.username || url.password || (url.port && url.port !== "443") ||
        !host.includes(".") || host === "localhost" || /\.(?:local|internal|localhost)$/.test(host) ||
        /^(?:127\.|10\.|169\.254\.|192\.168\.|0\.)/.test(host) ||
        /^172\.(?:1[6-9]|2\d|3[01])\./.test(host) || host.startsWith("[")) return null;
    for (const key of url.searchParams.keys()) {
      if (["token", "_token", "access_token", "session", "sessionid", "password", "email"].includes(key.toLowerCase())) return null;
    }
    url.hash = "";
    return url.href;
  } catch { return null; }
}

function link(card, root, source, expected, href, label) {
  const safe = onlineSchoolSafeLink(href);
  if (!safe) return null;
  const assignment = label === undefined;
  if (assignment) {
    const url = new URL(safe);
    const readable = url.hostname + (url.pathname === "/" ? "" : url.pathname) + (url.search ? "?…" : "");
    label = readable.length > 80 ? readable.slice(0, 79) + "…" : readable;
  }
  const anchor = node("a", label);
  anchor.href = safe; anchor.target = "_blank"; anchor.rel = "noopener noreferrer";
  anchor.referrerPolicy = "no-referrer"; anchor.title = safe;
  if (assignment) anchor.className = "online-assignment-link";
  anchor.addEventListener("click", event => {
    if (!current(card, source, expected, root)) event.preventDefault();
  });
  return anchor;
}

function localDay(timezone, mode, now) {
  try {
    const parts = new Intl.DateTimeFormat("en-CA", { timeZone: timezone, year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(now);
    const values = Object.fromEntries(parts.map(part => [part.type, part.value]));
    const day = `${values.year}-${values.month}-${values.day}`;
    if (!DATE.test(day)) return null;
    return mode === "tomorrow" ? new Date(Date.parse(day + "T00:00:00Z") + 86400000).toISOString().slice(0, 10) : day;
  } catch { return null; }
}

function timestamp(value, timezone, language, fallback) {
  if (typeof value !== "string" || !Number.isFinite(Date.parse(value))) return fallback;
  try { return new Intl.DateTimeFormat(language, {timeZone: timezone, dateStyle: "medium", timeStyle: "short"}).format(new Date(value)); }
  catch { return fallback; }
}

function status(source, copy) {
  if (!source.enabled) return copy.disabled;
  const statuses = {ready: "ready", pending: "pending", online_school_auth_failed: "auth",
    online_school_rate_limited: "limited", online_school_student_mismatch: "changed",
    online_school_invalid_response: "invalid", online_school_invalid_config: "invalid", online_school_timeout: "timeout"};
  return copy[statuses[source.status] || "unavailable"];
}

function facts(container, title, records, copy, absence = false) {
  const details = node("details");
  details.append(node("summary", `${title} · ${records.length}`));
  if (!records.length) details.append(node("p", absence ? copy.noAbsences : copy.noGrades, "sub"));
  else {
    const visible = [...records].filter(row => row && typeof row === "object").sort((a, b) => String(b.date || "").localeCompare(String(a.date || ""))).slice(0, 30);
    const items = node("ul");
    for (const row of visible) {
      const item = node("li");
      item.append(node("strong", `${safeText(row.date || row.period, 200)} · ${safeText(row.subject, 200)}${absence ? "" : " · " + safeText(row.value, 200)}`));
      if (!absence && row.kind) item.append(node("p", safeText(row.kind, 200), "sub"));
      if (row.comment) item.append(node("p", safeText(row.comment, 1000), "online-body"));
      items.append(item);
    }
    details.append(items);
    if (visible.length < records.length) details.append(node("p", copy.count.replace("{shown}", visible.length).replace("{total}", records.length), "sub"));
  }
  if (!absence) details.append(node("p", copy.literal, "sub"));
  container.append(details);
}

function lessons(card, root, box, source, expected, day, copy) {
  const snapshot = source.snapshot;
  if (!day) { box.append(node("p", copy.unknownZone)); return; }
  box.append(node("h4", `${day} · ${safeText(source.timezone, 80)}`));
  if (!DATE.test(snapshot.coverage_start || "") || !DATE.test(snapshot.coverage_end || "") ||
      day < snapshot.coverage_start || day > snapshot.coverage_end) {
    box.append(node("p", copy.outside)); return;
  }
  const rows = list(snapshot.lessons).filter(row => row && row.date === day).slice(0, 30);
  if (!rows.length) { box.append(node("p", copy.emptyDay)); return; }
  box.append(node("p", copy.target, "sub"));
  for (const row of rows) {
    const item = node("article", null, "online-lesson" + (row.cancelled ? " online-cancelled" : ""));
    item.dataset.lessonId = row.id;
    item.append(node("strong", `${safeText(row.start, 5)}${row.end ? "–" + safeText(row.end, 5) : ""} · ${safeText(row.subject, 200)}`));
    if (row.cancelled) item.append(node("strong", copy.cancelled));
    if (row.replacement) item.append(node("span", copy.replacement));
    if (row.room || row.teacher) item.append(node("p", `${copy.room}: ${safeText(row.room, 200)} · ${copy.teacher}: ${safeText(row.teacher, 200)}`, "sub"));
    if (row.topic) item.append(node("p", `${copy.topic}: ${safeText(row.topic, 2000)}`, "online-body"));
    item.append(node("strong", copy.homework), node("p", row.homework ? safeText(row.homework) : copy.noHomework, "online-body"));
    if (Number.isInteger(row.estimated_minutes) && row.estimated_minutes >= 0 && row.estimated_minutes <= 1440) {
      item.append(node("p", copy.minutes.replace("{minutes}", row.estimated_minutes), "sub"));
    }
    const ack = source.acknowledgements?.[row.id];
    if (ack?.done === true && ack.homework_hash === row.homework_hash && ack.member_revision === source.member_revision) item.append(node("p", copy.prepared, "sub"));
    const links = node("ul");
    for (const url of list(row.links).slice(0, 20)) {
      const anchor = link(card, root, source, expected, url);
      if (anchor) { const li = node("li"); li.append(anchor); links.append(li); }
    }
    if (links.children.length) item.append(node("span", copy.links), links);
    if (list(row.attachments).length) {
      item.append(node("strong", copy.attachments));
      const files = node("ul");
      for (const file of row.attachments.slice(0, 20)) files.append(node("li", `${safeText(file.name, 200)} · ${safeText(file.ext, 16)}${Number.isSafeInteger(file.size) && file.size >= 0 ? " · " + file.size + " B" : ""}`));
      item.append(files, node("p", copy.filesHint, "sub"));
    }
    box.append(item);
  }
}

export function renderOnlineSchool(card, body, now = new Date()) {
  const currentActor = actor(card);
  if (!currentActor || !body) return;
  const language = (card._config?.language || card._hass?.language || "en").split("-")[0];
  const copy = ONLINE_SCHOOL_COPY[language] || ONLINE_SCHOOL_COPY.en;
  const root = node("section", null, "online-school");
  root.append(node("style", STYLE), node("h3", copy.title));
  if (card._data.role === "owner") root.append(node("p", copy.setup, "sub"));
  const records = sources(card);
  if (!records.length) root.append(node("p", copy.noSources, "sub"));
  const mode = card._onlineSchoolDay === "today" ? "today" : "tomorrow";
  for (const source of records) {
    const expected = scope(card, source);
    const box = node("section", null, "online-source"); box.dataset.sourceId = source.id;
    const member = card._data.members.find(row => row.id === source.member);
    box.append(node("h4", `${safeText(source.label, 200)} · ${safeText(member.name, 200)}`), node("p", status(source, copy), "sub"));
    box.append(node("p", `${copy.lastSuccess}: ${timestamp(source.last_success, source.timezone, language, copy.never)}`, "sub"));
    if (source.enabled !== true || !source.snapshot) {
      if (source.enabled === true) box.append(node("p", copy.noSnapshot));
      root.append(box); continue;
    }
    box.append(node("p", source.stale !== false ? copy.stale : copy.fresh, source.stale !== false ? "online-stale" : "sub"));
    box.append(node("p", `${copy.coverage}: ${safeText(source.snapshot.coverage_start, 10)} – ${safeText(source.snapshot.coverage_end, 10)}`, "sub"));
    const days = node("div", null, "online-days");
    for (const option of ["today", "tomorrow"]) {
      const button = node("button", copy[option]); button.type = "button";
      button.setAttribute("aria-pressed", String(mode === option)); button.dataset.onlineDay = option;
      button.addEventListener("click", () => {
        if (!current(card, source, expected, root)) return;
        card._onlineSchoolDay = option; card.render();
      }); days.append(button);
    }
    box.append(days);
    lessons(card, root, box, source, expected, localDay(source.timezone, mode, now), copy);
    const portal = link(card, root, source, expected, source.snapshot.source_url, copy.portal);
    if (portal) box.append(portal);
    facts(box, copy.grades, list(source.snapshot.grades), copy);
    facts(box, copy.absences, list(source.snapshot.absences), copy, true);
    const changes = node("details"); changes.append(node("summary", copy.changes));
    const recent = list(source.changes).slice(-10).reverse();
    if (!recent.length) changes.append(node("p", copy.noChanges, "sub"));
    for (const change of recent) {
      const labels = {lesson: copy.changeLesson, homework: copy.changeHomework, grade: copy.changeGrade};
      if (labels[change.kind]) changes.append(node("p", `${timestamp(change.at, source.timezone, language, copy.never)} · ${labels[change.kind]}`));
    }
    box.append(changes); root.append(box);
  }
  root.append(node("p", copy.readonly, "sub")); body.append(root);
}
