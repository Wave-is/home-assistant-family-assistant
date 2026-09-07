/* Revision-bound create/edit workflow for wake-up schedules. No device actions. */

export const ALARM_EDITOR_COPY = {
  en: {
    add: "Add wake-up schedule",
    edit: "Edit schedule",
    heading_create: "New wake-up schedule",
    heading_edit: "Edit wake-up schedule",
    member: "Family member",
    name: "Schedule name",
    time: "Wake-up time",
    timezone: "Time zone",
    days: "Days",
    day_names: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    enabled: "Schedule enabled",
    enabled_value: "Enabled",
    disabled_value: "Disabled",
    exceptions: "Exception dates",
    exceptions_hint: "One YYYY-MM-DD date per line. These dates will not ring.",
    profile: "Wake-up style",
    gentle: "Messages only",
    strict: "Messages and the separately configured siren",
    second_min: "Second check, earliest (minutes)",
    second_max: "Second check, latest (minutes)",
    recheck_grace: "Siren recheck grace (seconds)",
    penalty: "Missed wake-up points (0 disables)",
    continue: "Review schedule",
    review: "Review wake-up schedule",
    confirm: "I reviewed the named member, dates, time zone, and wake-up settings.",
    create: "Create schedule",
    save: "Save schedule",
    retry: "Retry exact request",
    back: "Back",
    cancel: "Cancel",
    none: "None",
    validation: "Check every field and select at least one day.",
  },
  ru: {
    add: "Добавить расписание подъёма",
    edit: "Изменить расписание",
    heading_create: "Новое расписание подъёма",
    heading_edit: "Изменить расписание подъёма",
    member: "Участник семьи",
    name: "Название расписания",
    time: "Время подъёма",
    timezone: "Часовой пояс",
    days: "Дни",
    day_names: ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"],
    enabled: "Расписание включено",
    enabled_value: "Включено",
    disabled_value: "Выключено",
    exceptions: "Даты-исключения",
    exceptions_hint: "Одна дата ГГГГ-ММ-ДД в строке. В эти даты будильник не сработает.",
    profile: "Режим пробуждения",
    gentle: "Только сообщения",
    strict: "Сообщения и отдельно настроенная сирена",
    second_min: "Повторная проверка, не раньше (минуты)",
    second_max: "Повторная проверка, не позже (минуты)",
    recheck_grace: "Пауза до повтора сирены (секунды)",
    penalty: "Баллы за пропуск (0 — без штрафа)",
    continue: "Проверить расписание",
    review: "Проверка расписания подъёма",
    confirm: "Я проверил(а) участника, даты, часовой пояс и настройки подъёма.",
    create: "Создать расписание",
    save: "Сохранить расписание",
    retry: "Повторить точный запрос",
    back: "Назад",
    cancel: "Отмена",
    none: "Нет",
    validation: "Проверьте все поля и выберите хотя бы один день.",
  },
  uk: {
    add: "Додати розклад підйому",
    edit: "Змінити розклад",
    heading_create: "Новий розклад підйому",
    heading_edit: "Змінити розклад підйому",
    member: "Учасник родини",
    name: "Назва розкладу",
    time: "Час підйому",
    timezone: "Часовий пояс",
    days: "Дні",
    day_names: ["Понеділок", "Вівторок", "Середа", "Четвер", "П’ятниця", "Субота", "Неділя"],
    enabled: "Розклад увімкнено",
    enabled_value: "Увімкнено",
    disabled_value: "Вимкнено",
    exceptions: "Дати-винятки",
    exceptions_hint: "Одна дата РРРР-ММ-ДД у рядку. У ці дати будильник не спрацює.",
    profile: "Режим пробудження",
    gentle: "Лише повідомлення",
    strict: "Повідомлення й окремо налаштована сирена",
    second_min: "Повторна перевірка, не раніше (хвилини)",
    second_max: "Повторна перевірка, не пізніше (хвилини)",
    recheck_grace: "Пауза до повтору сирени (секунди)",
    penalty: "Бали за пропуск (0 — без штрафу)",
    continue: "Перевірити розклад",
    review: "Перевірка розкладу підйому",
    confirm: "Я перевірив(-ла) учасника, дати, часовий пояс і налаштування підйому.",
    create: "Створити розклад",
    save: "Зберегти розклад",
    retry: "Повторити точний запит",
    back: "Назад",
    cancel: "Скасувати",
    none: "Немає",
    validation: "Перевірте всі поля й виберіть принаймні один день.",
  },
};

const CLOCK = /^(?:[01]\d|2[0-3]):[0-5]\d$/;
const DATE = /^\d{4}-\d{2}-\d{2}$/;
const ROLES = new Set(["owner", "parent"]);
const clone = (value) => JSON.parse(JSON.stringify(value));
const freeze = (value) => {
  if (value && typeof value === "object" && !Object.isFrozen(value)) {
    Object.freeze(value);
    for (const child of Object.values(value)) freeze(child);
  }
  return value;
};
const node = (tag, text, className) => {
  const result = document.createElement(tag);
  if (text !== undefined && text !== null) result.textContent = String(text);
  if (className) result.className = className;
  return result;
};
const validRevision = (value) => Number.isSafeInteger(value) && value >= 1;

function copyOf(card) {
  const language = String(card?._config?.language || card?._hass?.language || "en").split(/[-_]/)[0];
  return ALARM_EDITOR_COPY[language] || ALARM_EDITOR_COPY.en;
}

function members(card) {
  return Array.isArray(card?._data?.members) ? card._data.members : [];
}

function eligibleMembers(card) {
  return members(card).filter(
    (item) => item && item.active === true && item.role !== "guest" && validRevision(item.revision),
  ).sort((left, right) => left.id.localeCompare(right.id));
}

function alarms(card) {
  return Array.isArray(card?._data?.alarms) ? card._data.alarms : [];
}

function access(card) {
  const actor = members(card).find((item) => item?.id === card?._data?.actor);
  if (
    !actor ||
    actor.active !== true ||
    actor.role !== card?._data?.role ||
    !ROLES.has(actor.role) ||
    !validRevision(actor.revision) ||
    !Array.isArray(card?._data?.settings?.modules) ||
    !card._data.settings.modules.includes("alarms") ||
    !card._entry
  )
    return null;
  return {
    generation: card._generation,
    entry: card._entry,
    actor: actor.id,
    role: actor.role,
    actorRevision: actor.revision,
    members: eligibleMembers(card).map((item) => [item.id, item.role, item.revision]),
  };
}

function same(left, right) {
  return Boolean(left && right && JSON.stringify(left) === JSON.stringify(right));
}

function alarmPins(card) {
  const normalized = alarms(card).map(normalizedAlarm);
  if (normalized.some((item) => item === null)) return null;
  return normalized
    .map((item) => [item.id, item.revision])
    .sort((left, right) => left[0].localeCompare(right[0]));
}

function strictDate(value) {
  if (!DATE.test(value)) return false;
  const [year, month, day] = value.split("-").map(Number);
  if (year < 1) return false;
  const parsed = new Date(0);
  parsed.setUTCHours(0, 0, 0, 0);
  parsed.setUTCFullYear(year, month - 1, day);
  return parsed.getUTCFullYear() === year && parsed.getUTCMonth() === month - 1 && parsed.getUTCDate() === day;
}

function validTimezone(value) {
  if (typeof value !== "string" || !value || value.length > 80) return false;
  try {
    new Intl.DateTimeFormat("en", { timeZone: value }).format(new Date(0));
    return true;
  } catch (_error) {
    return false;
  }
}

function integer(value, low, high) {
  const text = String(value);
  if (!/^-?\d+$/.test(text)) return null;
  const parsed = Number(text);
  return Number.isSafeInteger(parsed) && parsed >= low && parsed <= high ? parsed : null;
}

function normalizedAlarm(item) {
  if (
    !item ||
    typeof item.id !== "string" ||
    !validRevision(item.revision) ||
    typeof item.member !== "string" ||
    typeof item.name !== "string" ||
    item.name.length > 80 ||
    !CLOCK.test(item.time) ||
    !validTimezone(item.timezone) ||
    !Array.isArray(item.days) ||
    !item.days.length ||
    item.days.some((day) => !Number.isInteger(day) || day < 0 || day > 6) ||
    !Array.isArray(item.exceptions) ||
    item.exceptions.some((day) => typeof day !== "string" || !strictDate(day)) ||
    typeof item.enabled !== "boolean" ||
    !["gentle", "strict"].includes(item.profile)
  )
    return null;
  const secondMin = integer(item.second_min, 1, 25);
  const secondMax = integer(item.second_max, 1, 25);
  const grace = integer(item.recheck_grace, 0, 300);
  const penalty = integer(item.penalty, -10, 0);
  if (secondMin === null || secondMax === null || secondMin > secondMax || grace === null || penalty === null)
    return null;
  return {
    id: item.id,
    revision: item.revision,
    member: item.member,
    name: item.name,
    time: item.time,
    days: [...new Set(item.days)].sort(),
    timezone: item.timezone,
    enabled: item.enabled,
    exceptions: [...new Set(item.exceptions)].sort(),
    second_min: secondMin,
    second_max: secondMax,
    profile: item.profile,
    recheck_grace: grace,
    penalty,
  };
}

function valuesFrom(item, card) {
  if (item) {
    const { id: _id, revision: _revision, ...values } = item;
    return values;
  }
  return {
    member: eligibleMembers(card)[0]?.id || "",
    name: "",
    time: "07:30",
    days: [0, 1, 2, 3, 4],
    timezone: card?._data?.settings?.timezone || card?._hass?.config?.time_zone || "UTC",
    enabled: true,
    exceptions: [],
    second_min: 12,
    second_max: 18,
    profile: "gentle",
    recheck_grace: 60,
    penalty: 0,
  };
}

function payloadFrom(raw, draft) {
  const days = raw.days.map(Number).filter((day) => Number.isInteger(day));
  const exceptions = [...new Set(raw.exceptions.map((item) => item.trim()).filter(Boolean))].sort();
  const payload = {
    member: raw.member,
    name: raw.name,
    time: raw.time,
    days: [...new Set(days)].sort(),
    timezone: raw.timezone,
    enabled: raw.enabled,
    exceptions,
    second_min: integer(raw.second_min, 1, 25),
    second_max: integer(raw.second_max, 1, 25),
    profile: raw.profile,
    recheck_grace: integer(raw.recheck_grace, 0, 300),
    penalty: integer(raw.penalty, -10, 0),
  };
  const target = draft.access.members.find(([id]) => id === payload.member);
  if (
    !target ||
    typeof payload.name !== "string" ||
    payload.name.length > 80 ||
    !CLOCK.test(payload.time) ||
    !validTimezone(payload.timezone) ||
    !payload.days.length ||
    payload.days.some((day) => day < 0 || day > 6) ||
    exceptions.length > 366 ||
    exceptions.some((day) => !strictDate(day)) ||
    typeof payload.enabled !== "boolean" ||
    payload.second_min === null ||
    payload.second_max === null ||
    payload.second_min > payload.second_max ||
    !["gentle", "strict"].includes(payload.profile) ||
    payload.recheck_grace === null ||
    payload.penalty === null
  )
    return null;
  if (draft.source) return { id: draft.source.id, revision: draft.source.revision, ...payload };
  return payload;
}

function matchesPayload(item, payload, revision) {
  const normalized = normalizedAlarm(item);
  if (!normalized || normalized.revision !== revision) return false;
  const { id: _id, revision: _revision, ...values } = normalized;
  const { id: _payloadId, revision: _payloadRevision, ...expected } = payload;
  return JSON.stringify(values) === JSON.stringify(expected);
}

function draftAllowed(card, draft) {
  if (!same(access(card), draft?.access)) return false;
  const pins = alarmPins(card);
  if (!pins || !Array.isArray(draft?.alarmPins)) return false;
  if (!draft?.pending) return same(pins, draft?.alarmPins);
  if (same(pins, draft.alarmPins)) return true;
  const payload = draft.pending.payload;
  if (draft.source) {
    return alarms(card).some((item) => item?.id === draft.source.id && matchesPayload(item, payload, draft.source.revision + 1));
  }
  const oldIds = new Set(draft.alarmPins.map(([id]) => id));
  return alarms(card).filter((item) => !oldIds.has(item?.id) && matchesPayload(item, payload, 1)).length === 1;
}

export function openAlarmEditor(card, alarm = null) {
  const currentAccess = access(card);
  const pins = alarmPins(card);
  if (!currentAccess || !pins) return false;
  const source = alarm === null ? null : normalizedAlarm(alarm);
  if (alarm !== null && (!source || !alarms(card).some((item) => item?.id === source.id && item.revision === source.revision)))
    return false;
  card._alarmEditorDraft = {
    access: freeze(clone(currentAccess)),
    alarmPins: freeze(clone(pins)),
    source: source ? freeze(clone(source)) : null,
    values: clone(valuesFrom(source, card)),
    step: "edit",
    pending: null,
  };
  card._actionError = null;
  card.render?.();
  return true;
}

export function reconcileAlarmEditorRefresh(card, previousData) {
  if (!card?._alarmEditorDraft) return false;
  const invalid = !draftAllowed(card, card._alarmEditorDraft);
  if (invalid) {
    card._alarmEditorDraft = null;
    card._actionError = "conflict";
  }
  return invalid || JSON.stringify(previousData?.alarms) !== JSON.stringify(card?._data?.alarms);
}

function inputField(form, name, label, type, value, limits = {}) {
  const wrapper = node("label", label);
  const input = node("input");
  Object.assign(input, { name, type, value: String(value), required: true });
  for (const [key, setting] of Object.entries(limits)) input[key] = setting;
  wrapper.append(input);
  form.append(wrapper);
  return input;
}

function localButton(card, label, callback, primary = false) {
  const button = card.button(label, callback, primary);
  button.type = "button";
  return button;
}

function focusWhenRendered(card, draft, selector) {
  queueMicrotask(() => {
    if (card._alarmEditorDraft === draft)
      card.shadowRoot?.querySelector(selector)?.focus();
  });
}

function readForm(form) {
  const data = new FormData(form);
  return {
    member: String(data.get("member") || ""),
    name: String(data.get("name") || ""),
    time: String(data.get("time") || ""),
    timezone: String(data.get("timezone") || ""),
    days: data.getAll("days"),
    enabled: data.get("enabled") === "on",
    exceptions: String(data.get("exceptions") || "").split(/[\n,]/),
    second_min: data.get("second_min"),
    second_max: data.get("second_max"),
    profile: String(data.get("profile") || ""),
    recheck_grace: data.get("recheck_grace"),
    penalty: data.get("penalty"),
  };
}

function appendReviewLine(list, term, value) {
  list.append(node("dt", term), node("dd", value));
}

export function renderAlarmEditor(card, body) {
  const draft = card?._alarmEditorDraft;
  if (!draft) return false;
  if (!body?.isConnected || !draftAllowed(card, draft)) {
    card._alarmEditorDraft = null;
    card._actionError = "conflict";
    return false;
  }
  const copy = copyOf(card);
  const section = node("section", null, "alarm-editor");
  section.dataset.alarmEditor = draft.source ? "edit" : "create";
  section.append(node("style", `.alarm-editor{display:grid;gap:12px}.alarm-editor form,.alarm-editor-review{display:grid;gap:10px}.alarm-editor-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.alarm-editor-days{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px}.alarm-editor-days label,.alarm-editor-check{display:flex;gap:8px;align-items:flex-start}.alarm-editor textarea{min-height:80px}.alarm-editor-actions{display:flex;gap:8px;flex-wrap:wrap}.alarm-editor-review dl{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:6px 10px;margin:0}@media(max-width:600px){.alarm-editor-grid,.alarm-editor-review dl{grid-template-columns:minmax(0,1fr)}.alarm-editor-actions button{width:100%}}`));
  section.append(node("h2", copy[draft.source ? "heading_edit" : "heading_create"]));
  const current = () => card._alarmEditorDraft === draft && draftAllowed(card, draft) && body.isConnected && !card._writing;
  const close = () => {
    if (!current()) return;
    card._alarmEditorDraft = null;
    card._actionError = null;
    card.render?.();
  };

  if (draft.step === "review") {
    const review = node("div", null, "alarm-editor-review");
    review.append(node("h3", copy.review));
    const list = node("dl");
    const selected = eligibleMembers(card).find((item) => item.id === draft.values.member);
    appendReviewLine(list, copy.member, selected?.name || draft.values.member);
    appendReviewLine(list, copy.name, draft.values.name || copy.none);
    appendReviewLine(list, copy.time, `${draft.values.time} · ${draft.values.timezone}`);
    appendReviewLine(list, copy.days, draft.values.days.map((day) => copy.day_names[day]).join(", "));
    appendReviewLine(list, copy.exceptions, draft.values.exceptions.join(", ") || copy.none);
    appendReviewLine(list, copy.profile, copy[draft.values.profile]);
    appendReviewLine(list, copy.second_min, draft.values.second_min);
    appendReviewLine(list, copy.second_max, draft.values.second_max);
    appendReviewLine(list, copy.recheck_grace, draft.values.recheck_grace);
    appendReviewLine(list, copy.penalty, draft.values.penalty);
    appendReviewLine(
      list,
      copy.enabled,
      draft.values.enabled ? copy.enabled_value : copy.disabled_value,
    );
    review.append(list);
    const confirmation = node("label", null, "alarm-editor-check");
    const checkbox = node("input");
    checkbox.type = "checkbox";
    checkbox.name = "confirmed";
    checkbox.disabled = Boolean(draft.pending);
    confirmation.append(checkbox, node("span", copy.confirm));
    review.append(confirmation);
    const actions = node("div", null, "alarm-editor-actions");
    if (!draft.pending) {
      actions.append(
        localButton(card, copy.back, () => {
          if (current()) {
            draft.step = "edit";
            card.render?.();
            focusWhenRendered(card, draft, '.alarm-editor [name="member"]');
          }
        }),
        localButton(card, copy.cancel, close),
      );
    }
    const submit = localButton(card, draft.pending ? copy.retry : copy[draft.source ? "save" : "create"], async () => {
      if (!current() || (!draft.pending && !checkbox.checked)) return;
      if (!draft.pending) draft.pending = freeze({ action: "alarms.save", payload: clone(draft.values), operation_id: crypto.randomUUID() });
      const pending = draft.pending;
      await card.command(pending.action, pending.payload, pending.operation_id);
      if (card._alarmEditorDraft === draft && !card._actionError && same(access(card), draft.access)) {
        card._alarmEditorDraft = null;
        card.render?.();
      }
    }, true);
    actions.append(submit);
    review.append(actions);
    section.append(review);
    body.append(section);
    focusWhenRendered(card, draft, '.alarm-editor [name="confirmed"]');
    return true;
  }

  const form = node("form");
  const grid = node("div", null, "alarm-editor-grid");
  const memberLabel = node("label", copy.member);
  const memberSelect = node("select");
  memberSelect.name = "member";
  for (const item of eligibleMembers(card)) {
    const option = node("option", item.name);
    option.value = item.id;
    option.selected = item.id === draft.values.member;
    memberSelect.append(option);
  }
  memberLabel.append(memberSelect);
  grid.append(memberLabel);
  inputField(grid, "name", copy.name, "text", draft.values.name, { maxLength: 80, required: false });
  inputField(grid, "time", copy.time, "time", draft.values.time);
  inputField(grid, "timezone", copy.timezone, "text", draft.values.timezone, { maxLength: 80 });
  inputField(grid, "second_min", copy.second_min, "number", draft.values.second_min, { min: "1", max: "25", step: "1" });
  inputField(grid, "second_max", copy.second_max, "number", draft.values.second_max, { min: "1", max: "25", step: "1" });
  inputField(grid, "recheck_grace", copy.recheck_grace, "number", draft.values.recheck_grace, { min: "0", max: "300", step: "1" });
  inputField(grid, "penalty", copy.penalty, "number", draft.values.penalty, { min: "-10", max: "0", step: "1" });
  const profileLabel = node("label", copy.profile);
  const profile = node("select");
  profile.name = "profile";
  for (const value of ["gentle", "strict"]) {
    const option = node("option", copy[value]);
    option.value = value;
    option.selected = value === draft.values.profile;
    profile.append(option);
  }
  profileLabel.append(profile);
  grid.append(profileLabel);
  form.append(grid);
  const dayField = node("fieldset", null, "alarm-editor-days");
  dayField.append(node("legend", copy.days));
  for (let day = 0; day < 7; day += 1) {
    const label = node("label");
    const checkbox = node("input");
    checkbox.type = "checkbox";
    checkbox.name = "days";
    checkbox.value = String(day);
    checkbox.checked = draft.values.days.includes(day);
    label.append(checkbox, node("span", copy.day_names[day]));
    dayField.append(label);
  }
  form.append(dayField);
  const enabledLabel = node("label", null, "alarm-editor-check");
  const enabled = node("input");
  enabled.type = "checkbox";
  enabled.name = "enabled";
  enabled.checked = draft.values.enabled;
  enabledLabel.append(enabled, node("span", copy.enabled));
  form.append(enabledLabel);
  const exceptionLabel = node("label", copy.exceptions);
  const exceptions = node("textarea");
  exceptions.name = "exceptions";
  exceptions.value = draft.values.exceptions.join("\n");
  exceptions.placeholder = copy.exceptions_hint;
  exceptionLabel.append(exceptions, node("span", copy.exceptions_hint, "sub"));
  form.append(exceptionLabel);
  const error = node("p", "", "alarm-editor-validation");
  error.hidden = true;
  error.setAttribute("role", "alert");
  error.setAttribute("aria-live", "polite");
  form.append(error);
  const actions = node("div", null, "alarm-editor-actions");
  actions.append(localButton(card, copy.cancel, close));
  const review = node("button", copy.continue, "primary");
  review.type = "submit";
  actions.append(review);
  form.append(actions);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!current()) return;
    const payload = payloadFrom(readForm(form), draft);
    if (!payload) {
      error.textContent = copy.validation;
      error.hidden = false;
      return;
    }
    draft.values = freeze(payload);
    draft.step = "review";
    card.render?.();
    focusWhenRendered(card, draft, '.alarm-editor [name="confirmed"]');
  });
  section.append(form);
  body.append(section);
  focusWhenRendered(card, draft, '.alarm-editor [name="member"]');
  return true;
}
