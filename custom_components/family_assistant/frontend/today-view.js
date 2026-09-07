/* Bounded, display-only overview built from the current authorized projection. */

import { renderAvailabilityShell } from "./availability-shell.js";
import { countHealthAttention } from "./health-view.js";
import { wallTimeCandidates } from "./local-time.js";
import { TASK_ITEM_COPY } from "./task-items.js";

export const TODAY_COPY = Object.freeze({
  en: Object.freeze({
    summary: "At a glance",
    overdue: "Overdue",
    dueSoon: "Due in the next 48 hours",
    approvals: "Waiting for parent review",
    upcoming: "Coming up",
    shopping: "Shopping totals",
    activeRuns: "Active routines and alarms",
    presence: "Reported presence",
    balances: "Current points",
    health: "System attention",
    tasks: "Tasks",
    shoppingReady: "Ready to buy",
    shoppingPending: "Waiting for approval",
    taskReviews: "Task reports",
    calendarReviews: "Calendar requests",
    healthSignals: "Health signals",
    deliveryIssues: "Delivery issues",
    calendar: "Calendar",
    school: "School",
    alarm: "Alarm",
    routine: "Routine",
    allDay: "All day",
    unnamedAlarm: "Wake-up alarm",
    empty: "Nothing needs attention in the current overview.",
    more: "More items are available in the dedicated card.",
    tasksNav: "Use the Tasks card for details and actions.",
    shoppingNav: "Use the Shopping card for item details and approvals.",
    approvalsNav:
      "Use the Tasks, Shopping, and Calendar cards to review these items.",
    agendaNav:
      "Use the Calendar, School, or Alarms card for details and actions.",
    runsNav: "Use the Routines or Alarms card to act on a current run.",
    presenceNav:
      "Use the Presence card to review or change your own sharing preference.",
    balancesNav:
      "Use the Rules & rewards card for the points ledger and actions.",
    healthNav:
      "Parents can review details in System health and Home Assistant Repairs.",
    presenceLimit:
      "This is normalized reported home/away evidence, not confirmed occupancy or precise location.",
    status_reported_home: "Reported home",
    status_reported_away: "Reported away",
    status_unknown: "Unknown",
    reason_fresh: "Current observation",
    reason_stale: "Observation is stale",
    reason_unavailable: "Source unavailable",
    reason_unconfigured: "Source not configured",
    reason_not_shared: "Not shared with parents",
    alarm_first: "First check",
    alarm_waiting_second: "Waiting for second check",
    alarm_second: "Second check",
    unknownMember: "Unknown member",
    unavailable:
      "The household time settings are unavailable. No overview data is shown.",
  }),
  ru: Object.freeze({
    summary: "Кратко",
    overdue: "Просрочено",
    dueSoon: "Срок в ближайшие 48 часов",
    approvals: "Ожидает проверки родителя",
    upcoming: "Скоро",
    shopping: "Счётчики покупок",
    activeRuns: "Активные рутины и будильники",
    presence: "Сообщённое присутствие",
    balances: "Текущие баллы",
    health: "Требует внимания",
    tasks: "Задачи",
    shoppingReady: "Можно покупать",
    shoppingPending: "Ожидает одобрения",
    taskReviews: "Отчёты по задачам",
    calendarReviews: "Запросы календаря",
    healthSignals: "Сигналы состояния",
    deliveryIssues: "Проблемы доставки",
    calendar: "Календарь",
    school: "Школа",
    alarm: "Будильник",
    routine: "Рутина",
    allDay: "Весь день",
    unnamedAlarm: "Будильник",
    empty: "В текущем обзоре нет записей, требующих внимания.",
    more: "Другие записи доступны в отдельной карточке.",
    tasksNav: "Подробности и действия доступны в карточке «Задачи».",
    shoppingNav: "Позиции и одобрения доступны в карточке «Покупки».",
    approvalsNav:
      "Проверьте эти записи в карточках задач, покупок и календаря.",
    agendaNav:
      "Подробности и действия доступны в карточках календаря, школы и будильников.",
    runsNav:
      "Действия с текущим запуском доступны в карточке рутин или будильников.",
    presenceNav:
      "Проверить или изменить собственную настройку доступа можно в карточке присутствия.",
    balancesNav:
      "История баллов и действия доступны в карточке «Правила и поощрения».",
    healthNav:
      "Родители могут проверить подробности в карточке состояния и разделе «Проблемы» HA.",
    presenceLimit:
      "Это нормализованные сообщения «дома/не дома», а не подтверждение присутствия или точное местоположение.",
    status_reported_home: "Сообщено: дома",
    status_reported_away: "Сообщено: не дома",
    status_unknown: "Неизвестно",
    reason_fresh: "Актуальное наблюдение",
    reason_stale: "Наблюдение устарело",
    reason_unavailable: "Источник недоступен",
    reason_unconfigured: "Источник не настроен",
    reason_not_shared: "Нет доступа для родителей",
    alarm_first: "Первая проверка",
    alarm_waiting_second: "Ожидается вторая проверка",
    alarm_second: "Вторая проверка",
    unknownMember: "Неизвестный участник",
    unavailable:
      "Настройки времени семьи недоступны. Данные обзора не показаны.",
  }),
  uk: Object.freeze({
    summary: "Коротко",
    overdue: "Прострочено",
    dueSoon: "Термін у найближчі 48 годин",
    approvals: "Очікує перевірки когось із батьків",
    upcoming: "Незабаром",
    shopping: "Лічильники покупок",
    activeRuns: "Активні рутини та будильники",
    presence: "Повідомлена присутність",
    balances: "Поточні бали",
    health: "Потребує уваги",
    tasks: "Завдання",
    shoppingReady: "Можна купувати",
    shoppingPending: "Очікує схвалення",
    taskReviews: "Звіти про завдання",
    calendarReviews: "Запити календаря",
    healthSignals: "Сигнали стану",
    deliveryIssues: "Проблеми доставки",
    calendar: "Календар",
    school: "Школа",
    alarm: "Будильник",
    routine: "Рутина",
    allDay: "Увесь день",
    unnamedAlarm: "Будильник",
    empty: "У поточному огляді немає записів, що потребують уваги.",
    more: "Інші записи доступні в окремій картці.",
    tasksNav: "Подробиці та дії доступні в картці «Завдання».",
    shoppingNav: "Позиції та схвалення доступні в картці «Покупки».",
    approvalsNav: "Перевірте ці записи в картках завдань, покупок і календаря.",
    agendaNav:
      "Подробиці та дії доступні в картках календаря, школи й будильників.",
    runsNav: "Дії з поточним запуском доступні в картці рутин або будильників.",
    presenceNav:
      "Перевірити або змінити власне налаштування доступу можна в картці присутності.",
    balancesNav:
      "Історія балів і дії доступні в картці «Правила та заохочення».",
    healthNav:
      "Батьки можуть перевірити подробиці в картці стану та розділі «Проблеми» HA.",
    presenceLimit:
      "Це нормалізовані повідомлення «вдома/не вдома», а не підтвердження присутності чи точне місцеперебування.",
    status_reported_home: "Повідомлено: вдома",
    status_reported_away: "Повідомлено: не вдома",
    status_unknown: "Невідомо",
    reason_fresh: "Актуальне спостереження",
    reason_stale: "Спостереження застаріло",
    reason_unavailable: "Джерело недоступне",
    reason_unconfigured: "Джерело не налаштоване",
    reason_not_shared: "Немає доступу для батьків",
    alarm_first: "Перша перевірка",
    alarm_waiting_second: "Очікується друга перевірка",
    alarm_second: "Друга перевірка",
    unknownMember: "Невідомий учасник",
    unavailable:
      "Налаштування часу родини недоступні. Дані огляду не показано.",
  }),
});

const ACTIVE_TASKS = new Set([
  "assigned",
  "accepted",
  "in_progress",
  "needs_changes",
]);
const PRESENCE_STATUSES = new Set([
  "reported_home",
  "reported_away",
  "unknown",
]);
const PRESENCE_REASONS = new Set([
  "fresh",
  "stale",
  "unavailable",
  "unconfigured",
  "not_shared",
]);
const ACTIVE_ALARM_STAGES = new Set(["first", "waiting_second", "second"]);
const CLOCK = /^(?:[01]\d|2[0-3]):[0-5]\d$/;
const DATE = /^\d{4}-\d{2}-\d{2}$/;
const AWARE_INSTANT =
  /^\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d(?:\.\d{1,6})?)?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$/;
const HOUR = 60 * 60 * 1000;
const DAY = 24 * HOUR;

const STYLE = `
  .today-overview{display:grid;gap:12px;min-width:0}.today-overview h3,.today-overview p{margin:0}
  .today-metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px}
  .today-metric{display:grid;gap:3px;padding:10px;border:1px solid var(--divider-color,#ddd);border-radius:10px;min-width:0}
  .today-metric strong{font-size:1.3rem}.today-section{display:grid;gap:8px;min-width:0}
  .today-list{display:grid;gap:7px;margin:0;padding:0;list-style:none}.today-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:6px 10px;align-items:start}
  .today-row-main{display:grid;gap:3px;min-width:0}.today-row-main>*{overflow-wrap:anywhere}.today-kind{white-space:nowrap}
  .today-presence-note,.today-nav{margin:0}.today-time{font-variant-numeric:tabular-nums;white-space:nowrap}
  @media(max-width:520px){.today-row{grid-template-columns:minmax(0,1fr)}.today-time,.today-kind{white-space:normal}}
`;

const node = (tag, value, className) => {
  const result = document.createElement(tag);
  if (value !== undefined && value !== null) result.textContent = String(value);
  if (className) result.className = className;
  return result;
};

const rows = (value) => (Array.isArray(value) ? value : []);
const text = (value) =>
  typeof value === "string" && value.trim() ? value.trim() : null;
const validDate = (value) => {
  if (!DATE.test(value || "")) return false;
  const [year, month, day] = value.split("-").map(Number);
  const probe = new Date(0);
  probe.setUTCFullYear(year, month - 1, day);
  probe.setUTCHours(0, 0, 0, 0);
  return (
    year >= 1 &&
    probe.getUTCFullYear() === year &&
    probe.getUTCMonth() === month - 1 &&
    probe.getUTCDate() === day
  );
};
const instant = (value) => {
  const parsed =
    typeof value === "string" &&
    AWARE_INSTANT.test(value) &&
    validDate(value.slice(0, 10))
      ? Date.parse(value)
      : NaN;
  return Number.isFinite(parsed) ? parsed : null;
};

function language(card) {
  const value = String(
    card?._config?.language || card?._hass?.language || "en",
  ).split(/[-_]/)[0];
  return Object.hasOwn(TODAY_COPY, value) ? value : "en";
}

function timezone(data) {
  const value = data?.settings?.timezone;
  if (typeof value !== "string" || !value) return null;
  try {
    new Intl.DateTimeFormat("en", { timeZone: value }).format(new Date(0));
    return value;
  } catch (_error) {
    return null;
  }
}

function memberName(data, memberId, copy) {
  const member = rows(data?.members).find((item) => item?.id === memberId);
  return text(member?.name) || copy.unknownMember;
}

function localDateKey(at, zone) {
  try {
    const parts = new Intl.DateTimeFormat("en-CA-u-ca-gregory-nu-latn", {
      timeZone: zone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).formatToParts(new Date(at));
    const value = Object.fromEntries(
      parts.map((part) => [part.type, part.value]),
    );
    return `${value.year}-${value.month}-${value.day}`;
  } catch (_error) {
    return null;
  }
}

function addDays(day, amount) {
  if (!validDate(day)) return null;
  const value = new Date(`${day}T12:00:00Z`);
  if (!Number.isFinite(value.getTime())) return null;
  value.setUTCDate(value.getUTCDate() + amount);
  return value.toISOString().slice(0, 10);
}

function weekday(day) {
  const value = new Date(`${day}T12:00:00Z`);
  return Number.isFinite(value.getTime()) ? (value.getUTCDay() + 6) % 7 : null;
}

function wallInstants(local, zone) {
  try {
    return wallTimeCandidates(local, zone)
      .map(instant)
      .filter((item) => item !== null);
  } catch (_error) {
    return [];
  }
}

function wallInstant(local, zone) {
  return wallInstants(local, zone)[0] ?? null;
}

function nextAlarm(schedule, now) {
  if (
    schedule?.enabled !== true ||
    !CLOCK.test(schedule?.time || "") ||
    !Array.isArray(schedule?.days) ||
    typeof schedule?.timezone !== "string"
  )
    return null;
  const start = localDateKey(now, schedule.timezone);
  if (!start) return null;
  const exceptions = new Set(rows(schedule.exceptions).filter(validDate));
  for (let offset = 0; offset <= 7; offset += 1) {
    const day = addDays(start, offset);
    if (!day || exceptions.has(day) || !schedule.days.includes(weekday(day)))
      continue;
    // alarms.py deliberately resolves an ambiguous wall time with fold=0.
    const at = wallInstant(`${day}T${schedule.time}`, schedule.timezone);
    if (at !== null && at >= now) return at;
  }
  return null;
}

function agenda(data, modules, now) {
  const result = [];
  const zone = timezone(data);
  if (!zone) return result;
  if (modules.has("calendar")) {
    const calendarRows = [];
    for (const item of rows(data?.calendar?.occurrences)) {
      const title = text(item?.title);
      if (!title || typeof item?.start !== "string") continue;
      const allDay = item.all_day === true && validDate(item.start);
      const at = allDay
        ? wallInstant(`${item.start}T00:00`, zone)
        : instant(item.start);
      const currentAllDay = allDay && item.start >= localDateKey(now, zone);
      if (at === null || (!currentAllDay && at < now)) continue;
      calendarRows.push({
        kind: "calendar",
        title,
        at,
        allDay,
        sourceTime: item.start,
      });
    }
    result.push(
      ...calendarRows.sort((left, right) => left.at - right.at).slice(0, 4),
    );
  }
  if (modules.has("school")) {
    const schoolRows = [];
    for (const item of rows(data?.school?.upcoming)) {
      const title = text(item?.subject);
      if (!title || !validDate(item?.date) || !CLOCK.test(item?.start || ""))
        continue;
      const at = wallInstant(`${item.date}T${item.start}`, zone);
      if (at === null || at < now) continue;
      schoolRows.push({
        kind: "school",
        title,
        at,
        sourceTime: `${item.date}T${item.start}`,
        member: item.member,
      });
    }
    result.push(
      ...schoolRows.sort((left, right) => left.at - right.at).slice(0, 4),
    );
  }
  if (modules.has("alarms")) {
    for (const item of rows(data?.alarms)) {
      const at = nextAlarm(item, now);
      if (at === null) continue;
      result.push({
        kind: "alarm",
        title: text(item.name),
        at,
        sourceTime: new Date(at).toISOString(),
        displayZone: item.timezone,
        member: item.member,
      });
    }
  }
  return result.sort((left, right) => left.at - right.at).slice(0, 8);
}

export function buildTodayModel(data, now = Date.now()) {
  if (!data || typeof data !== "object" || data.role === "guest") return null;
  const zone = timezone(data);
  if (!zone || !Number.isFinite(now)) return { unavailable: true };
  const modules = new Set(
    rows(data?.settings?.modules).filter((item) => typeof item === "string"),
  );
  const parent = data.role === "owner" || data.role === "parent";
  const taskRows = modules.has("tasks") ? rows(data.tasks) : [];
  const activeTasks = taskRows
    .filter(
      (item) =>
        ACTIVE_TASKS.has(item?.status) &&
        text(item?.title) &&
        instant(item?.due_at) !== null,
    )
    .map((item) => ({
      title: item.title.trim(),
      assignee: item.assignee,
      status: item.status,
      due_at: item.due_at,
      due: instant(item.due_at),
    }))
    .sort((left, right) => left.due - right.due);
  const overdue = activeTasks.filter((item) => item.due < now);
  const dueSoon = activeTasks.filter(
    (item) => item.due >= now && item.due <= now + 48 * HOUR,
  );

  const shopping = modules.has("shopping") ? rows(data.shopping) : [];
  const shoppingCounts = modules.has("shopping")
    ? {
        approved: shopping.filter((item) => item?.status === "approved").length,
        pending: shopping.filter((item) => item?.status === "pending").length,
      }
    : null;
  const submitted =
    parent && modules.has("tasks")
      ? taskRows
          .filter((item) => item?.status === "submitted" && text(item?.title))
          .map((item) => ({
            title: item.title.trim(),
            assignee: item.assignee,
          }))
      : [];
  const calendarRequests =
    parent && modules.has("calendar")
      ? rows(data?.calendar?.events).filter(
          (item) => item?.status === "tentative" && item?.archived !== true,
        ).length
      : 0;

  const activeRuns = [];
  if (modules.has("routines")) {
    for (const item of rows(data?.routines?.runs)) {
      if (item?.status === "active" && text(item?.title)) {
        activeRuns.push({
          kind: "routine",
          title: item.title.trim(),
          member: item.member,
        });
      }
    }
  }
  if (modules.has("alarms")) {
    for (const item of rows(data?.alarm_runs)) {
      if (ACTIVE_ALARM_STAGES.has(item?.stage)) {
        activeRuns.push({
          kind: "alarm",
          title: null,
          member: item.member,
          stage: item.stage,
        });
      }
    }
  }

  const presenceRows = [];
  if (
    modules.has("presence") &&
    data.presence &&
    typeof data.presence === "object"
  ) {
    if (data.presence.self) presenceRows.push(data.presence.self);
    if (parent) presenceRows.push(...rows(data.presence.shared));
  }
  const safePresence = presenceRows
    .filter(
      (item) =>
        typeof item?.member === "string" &&
        PRESENCE_STATUSES.has(item.status) &&
        PRESENCE_REASONS.has(item.reason),
    )
    .slice(0, 8)
    .map((item) => ({
      member: item.member,
      status: item.status,
      reason: item.reason,
      observed_at:
        typeof item.observed_at === "string" ? item.observed_at : null,
    }));

  const health = parent
    ? {
        signals: countHealthAttention(data.health),
        deliveries: rows(data.delivery_issues).length,
      }
    : null;

  const balances = modules.has("court")
    ? rows(data.members)
        .filter(
          (member) =>
            member?.active === true &&
            typeof member?.id === "string" &&
            (parent || member.id === data.actor),
        )
        .slice(0, 8)
        .map((member) => ({
          member: member.id,
          points: rows(data.court)
            .filter(
              (entry) =>
                entry?.member === member.id &&
                entry?.status === "active" &&
                Number.isSafeInteger(entry?.points),
            )
            .reduce((sum, entry) => sum + entry.points, 0),
        }))
    : [];

  return {
    parent,
    overdue: overdue.slice(0, 4),
    overdueCount: overdue.length,
    dueSoon: dueSoon.slice(0, 4),
    dueSoonCount: dueSoon.length,
    submitted: submitted.slice(0, 4),
    submittedCount: submitted.length,
    calendarRequests,
    shopping: shoppingCounts,
    agenda: agenda(data, modules, now),
    activeRuns: activeRuns.slice(0, 4),
    activeRunCount: activeRuns.length,
    presence: safePresence,
    balances,
    health,
    timezone: zone,
  };
}

function locale(card) {
  return card?._config?.language || card?._hass?.language || "en";
}

function formatInstant(card, value, zone, allDay = false) {
  try {
    return new Intl.DateTimeFormat(locale(card), {
      timeZone: zone,
      weekday: "short",
      month: "short",
      day: "numeric",
      ...(allDay ? {} : { hour: "2-digit", minute: "2-digit" }),
    }).format(new Date(value));
  } catch (_error) {
    return "";
  }
}

function appendMetric(container, label, value, className) {
  const metric = node("div", null, `today-metric ${className}`);
  metric.append(node("strong", value), node("span", label));
  container.append(metric);
}

function section(body, title, className) {
  const value = node("section", null, `today-section ${className}`);
  value.append(node("h3", title));
  body.append(value);
  return value;
}

function appendTaskList(card, target, items, total, copy, taskCopy, zone) {
  const list = node("ul", null, "today-list");
  for (const item of items) {
    const row = node("li", null, "item today-row today-task-row");
    const main = node("span", null, "today-row-main");
    main.append(
      node("strong", item.title),
      node(
        "span",
        `${memberName(card._data, item.assignee, copy)} · ${taskCopy[`status_${item.status}`] || taskCopy.status_unknown}`,
        "sub",
      ),
    );
    const due = node(
      "time",
      formatInstant(card, item.due, zone),
      "sub today-time",
    );
    due.dateTime = item.due_at;
    row.append(main, due);
    list.append(row);
  }
  target.append(list);
  if (total > items.length) target.append(node("p", copy.more, "sub"));
  target.append(node("p", copy.tasksNav, "sub today-nav"));
}

function appendAgenda(card, target, items, copy, zone) {
  const list = node("ul", null, "today-list");
  for (const item of items) {
    const row = node("li", null, "item today-row today-agenda-row");
    row.dataset.kind = item.kind;
    const main = node("span", null, "today-row-main");
    const title = item.title || copy.unnamedAlarm;
    main.append(node("strong", title));
    const meta = [copy[item.kind]];
    if (item.member) meta.push(memberName(card._data, item.member, copy));
    main.append(node("span", meta.join(" · "), "sub"));
    const when = node(
      "time",
      item.allDay
        ? `${formatInstant(card, item.at, zone, true)} · ${copy.allDay}`
        : formatInstant(card, item.at, item.displayZone || zone),
      "sub today-time",
    );
    when.dateTime = item.sourceTime;
    row.append(main, when);
    list.append(row);
  }
  target.append(list, node("p", copy.agendaNav, "sub today-nav"));
}

export function renderToday(card, body) {
  if (!body || typeof body.append !== "function") return;
  const lang = language(card);
  const copy = TODAY_COPY[lang];
  const taskCopy = TASK_ITEM_COPY[lang] || TASK_ITEM_COPY.en;
  const model = buildTodayModel(card?._data);
  if (!model) {
    renderAvailabilityShell(card, body, { state: "role_unavailable" });
    return;
  }
  if (model.unavailable) {
    const unavailable = node(
      "section",
      null,
      "today-overview today-unavailable",
    );
    unavailable.setAttribute("role", "status");
    unavailable.append(node("p", copy.unavailable, "empty"));
    body.append(unavailable);
    return;
  }

  body.append(node("style", STYLE));
  const overview = node("section", null, "today-overview");
  overview.setAttribute("aria-label", copy.summary);
  body.append(overview);

  const metrics = node("div", null, "today-metrics");
  appendMetric(
    metrics,
    copy.overdue,
    model.overdueCount,
    "today-overdue-count",
  );
  appendMetric(metrics, copy.dueSoon, model.dueSoonCount, "today-due-count");
  if (model.shopping) {
    appendMetric(
      metrics,
      copy.shoppingReady,
      model.shopping.approved,
      "today-shopping-approved-count",
    );
  }
  if (model.parent) {
    appendMetric(
      metrics,
      copy.approvals,
      model.submittedCount +
        (model.shopping?.pending || 0) +
        model.calendarRequests,
      "today-approval-count",
    );
  }
  overview.append(metrics);

  if (model.overdue.length) {
    appendTaskList(
      card,
      section(overview, copy.overdue, "today-overdue"),
      model.overdue,
      model.overdueCount,
      copy,
      taskCopy,
      model.timezone,
    );
  }
  if (model.dueSoon.length) {
    appendTaskList(
      card,
      section(overview, copy.dueSoon, "today-due-soon"),
      model.dueSoon,
      model.dueSoonCount,
      copy,
      taskCopy,
      model.timezone,
    );
  }

  if (
    model.parent &&
    (model.submittedCount || model.shopping?.pending || model.calendarRequests)
  ) {
    const approvals = section(overview, copy.approvals, "today-approvals");
    if (model.submitted.length) {
      const list = node("ul", null, "today-list");
      for (const item of model.submitted) {
        const row = node("li", null, "item today-row today-approval-row");
        row.append(
          node("strong", item.title),
          node(
            "span",
            `${copy.taskReviews} · ${memberName(card._data, item.assignee, copy)}`,
            "sub",
          ),
        );
        list.append(row);
      }
      approvals.append(list);
      if (model.submittedCount > model.submitted.length)
        approvals.append(node("p", copy.more, "sub"));
    }
    const counts = node("div", null, "today-metrics");
    appendMetric(
      counts,
      copy.shoppingPending,
      model.shopping?.pending || 0,
      "today-shopping-pending-count",
    );
    appendMetric(
      counts,
      copy.calendarReviews,
      model.calendarRequests,
      "today-calendar-review-count",
    );
    approvals.append(counts, node("p", copy.approvalsNav, "sub today-nav"));
  }

  if (model.agenda.length)
    appendAgenda(
      card,
      section(overview, copy.upcoming, "today-agenda"),
      model.agenda,
      copy,
      model.timezone,
    );

  if (model.shopping) {
    const shopping = section(overview, copy.shopping, "today-shopping");
    const counts = node("div", null, "today-metrics");
    appendMetric(
      counts,
      copy.shoppingReady,
      model.shopping.approved,
      "today-shopping-ready",
    );
    appendMetric(
      counts,
      copy.shoppingPending,
      model.shopping.pending,
      "today-shopping-waiting",
    );
    shopping.append(counts, node("p", copy.shoppingNav, "sub today-nav"));
  }

  if (model.activeRuns.length) {
    const runsSection = section(overview, copy.activeRuns, "today-runs");
    const list = node("ul", null, "today-list");
    for (const item of model.activeRuns) {
      const row = node("li", null, "item today-row today-run-row");
      const label =
        item.kind === "routine"
          ? item.title
          : `${copy.unnamedAlarm} · ${copy[`alarm_${item.stage}`]}`;
      row.append(
        node("strong", label),
        node("span", memberName(card._data, item.member, copy), "sub"),
      );
      list.append(row);
    }
    runsSection.append(list);
    if (model.activeRunCount > model.activeRuns.length)
      runsSection.append(node("p", copy.more, "sub"));
    runsSection.append(node("p", copy.runsNav, "sub today-nav"));
  }

  if (model.presence.length) {
    const presence = section(overview, copy.presence, "today-presence");
    presence.append(node("p", copy.presenceLimit, "sub today-presence-note"));
    const list = node("ul", null, "today-list");
    for (const item of model.presence) {
      const row = node("li", null, "item today-row today-presence-row");
      const main = node("span", null, "today-row-main");
      main.append(
        node("strong", memberName(card._data, item.member, copy)),
        node("span", copy[`reason_${item.reason}`], "sub"),
      );
      const observed = instant(item.observed_at);
      const status = node("span", copy[`status_${item.status}`], "today-kind");
      row.append(main, status);
      if (observed !== null) {
        const when = node(
          "time",
          formatInstant(card, observed, model.timezone),
          "sub today-time",
        );
        when.dateTime = item.observed_at;
        main.append(when);
      }
      list.append(row);
    }
    presence.append(list, node("p", copy.presenceNav, "sub today-nav"));
  }

  if (model.balances.length) {
    const balances = section(overview, copy.balances, "today-balances");
    const list = node("ul", null, "today-list");
    for (const item of model.balances) {
      const row = node("li", null, "item today-row today-balance-row");
      row.append(
        node("strong", memberName(card._data, item.member, copy)),
        node("span", item.points, "today-kind"),
      );
      list.append(row);
    }
    balances.append(list, node("p", copy.balancesNav, "sub today-nav"));
  }

  if (model.health && (model.health.signals || model.health.deliveries)) {
    const health = section(overview, copy.health, "today-health");
    const counts = node("div", null, "today-metrics");
    appendMetric(
      counts,
      copy.healthSignals,
      model.health.signals,
      "today-health-count",
    );
    appendMetric(
      counts,
      copy.deliveryIssues,
      model.health.deliveries,
      "today-delivery-count",
    );
    health.append(counts, node("p", copy.healthNav, "sub today-nav"));
  }

  const visibleSections = overview.querySelectorAll(".today-section").length;
  if (!visibleSections && !model.shopping)
    overview.append(node("p", copy.empty, "empty"));
}
