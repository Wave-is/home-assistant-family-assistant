/**
 * Shared frontend recurrence form controls for Home Assistant Family Assistant.
 * Pure ES module with strict validation, zero network/private imports, safe DOM textContent rendering.
 */

export const RECURRENCE_COPY = {
  en: {
    help: "How the schedule handles clock changes and missed runs",
    legend: "Recurrence",
    enable: "Repeat according to schedule",
    frequency: "Frequency",
    daily: "Daily",
    weekly: "Weekly",
    monthly: "Monthly",
    interval: "Repeat every",
    intervalDailyUnit: "days",
    intervalWeeklyUnit: "weeks",
    intervalMonthlyUnit: "months",
    startDate: "Start date",
    untilDate: "End date (optional)",
    time: "Time",
    timezone: "Time zone (IANA)",
    weekdays: "Weekdays",
    dayNames: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    dayNamesFull: [
      "Monday",
      "Tuesday",
      "Wednesday",
      "Thursday",
      "Friday",
      "Saturday",
      "Sunday",
    ],
    monthDay: "Day of month (1–31)",
    exceptions: "Exception dates (YYYY-MM-DD, one per line or comma-separated)",
    catchupHours: "Catchup window (hours, 0–48)",
    dstExplanation:
      "When Daylight Saving Time changes: spring gap times that do not exist are skipped; autumn overlap times pick the first occurrence once per date.",
    monthMissingExplanation:
      "For months with fewer days than the chosen day of month (e.g. day 31 in February or April), that month's occurrence is skipped.",
    catchupZeroExplanation:
      "A catchup window of 0 hours does not disable catchup: it keeps an approximately one-minute execution window at scheduled time.",
    timezoneExplanation:
      "Dates and times are evaluated in the specified IANA calendar time zone, independent of browser time zone.",
  },
  ru: {
    help: "Перевод часов и пропущенные запуски",
    legend: "Повторение",
    enable: "Повторять по расписанию",
    frequency: "Периодичность",
    daily: "Ежедневно",
    weekly: "Еженедельно",
    monthly: "Ежемесячно",
    interval: "Повторять каждые",
    intervalDailyUnit: "дней",
    intervalWeeklyUnit: "недель",
    intervalMonthlyUnit: "месяцев",
    startDate: "Дата начала",
    untilDate: "Дата окончания (необязательно)",
    time: "Время",
    timezone: "Часовой пояс (IANA)",
    weekdays: "Дни недели",
    dayNames: ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"],
    dayNamesFull: [
      "Понедельник",
      "Вторник",
      "Среда",
      "Четверг",
      "Пятница",
      "Суббота",
      "Воскресенье",
    ],
    monthDay: "День месяца (1–31)",
    exceptions: "Даты-исключения (ГГГГ-ММ-ДД, по одной в строке или через запятую)",
    catchupHours: "Окно наверстывания (часов, 0–48)",
    dstExplanation:
      "При переходе на летнее/зимнее время: несуществующее время в весеннем пропуске пропускается; повторяющееся время осеннего перевода выбирается один раз по первому вхождению.",
    monthMissingExplanation:
      "В месяцах, где меньше дней, чем выбранный день месяца (например, 31-е число в феврале или апреле), срабатывание в этом месяце пропускается.",
    catchupZeroExplanation:
      "Окно наверстывания 0 часов не отключает выполнение: сохраняется приблизительно одноминутное окно запуска в назначенное время.",
    timezoneExplanation:
      "Даты и время вычисляются в указанном часовом поясе IANA независимо от часового пояса браузера.",
  },
  uk: {
    help: "Переведення годинника та пропущені запуски",
    legend: "Повторення",
    enable: "Повторювати за розкладом",
    frequency: "Періодичність",
    daily: "Щодня",
    weekly: "Щотижня",
    monthly: "Щомісяця",
    interval: "Повторювати кожні",
    intervalDailyUnit: "днів",
    intervalWeeklyUnit: "тижнів",
    intervalMonthlyUnit: "місяців",
    startDate: "Дата початку",
    untilDate: "Дата завершення (необов’язково)",
    time: "Час",
    timezone: "Часовий пояс (IANA)",
    weekdays: "Дні тижня",
    dayNames: ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"],
    dayNamesFull: [
      "Понеділок",
      "Вівторок",
      "Середа",
      "Четвер",
      "Пʼятниця",
      "Субота",
      "Неділя",
    ],
    monthDay: "День місяця (1–31)",
    exceptions: "Дати-винятки (РРРР-ММ-ДД, по одній у рядку або через кому)",
    catchupHours: "Вікно наздоганяння (годин, 0–48)",
    dstExplanation:
      "При переході часу: неіснуючий час у весняному пропуску пропускається; час осіннього переведення стрілок вибирається один раз за першим входженням.",
    monthMissingExplanation:
      "У місяцях, де менше днів, ніж обраний день місяця (наприклад, 31-ше число у лютому або квітні), виконання в цьому місяці пропускається.",
    catchupZeroExplanation:
      "Вікно наздоганяння 0 годин не вимикає запуск: зберігається приблизно однохвилинне вікно запуску в запланований час.",
    timezoneExplanation:
      "Дати і час обчислюються у вказаному часовому поясі IANA незалежно від часового поясу браузера.",
  },
};

const CLOCK_PATTERN = /^(?:[01]\d|2[0-3]):[0-5]\d$/;
const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
const INTEGER_STRING_PATTERN = /^(?:0|[1-9]\d*)$/;

const ALLOWED_RULE_KEYS = Object.freeze(
  new Set([
    "frequency",
    "interval",
    "start_date",
    "until",
    "time",
    "timezone",
    "weekdays",
    "month_day",
    "exceptions",
    "catchup_hours",
  ])
);

function isLeapYear(year) {
  return (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0;
}

function daysInMonth(year, month) {
  if (month === 2) return isLeapYear(year) ? 29 : 28;
  if (month === 4 || month === 6 || month === 9 || month === 11) return 30;
  return 31;
}

function throwInvalidField(field) {
  const err = new Error(`invalid_field: ${field}`);
  err.code = "invalid_field";
  err.field = field;
  throw err;
}

function assertValidCalendarDate(value, fieldName) {
  if (typeof value !== "string" || !DATE_PATTERN.test(value)) {
    throwInvalidField(fieldName);
  }
  const [yStr, mStr, dStr] = value.split("-");
  const year = Number(yStr);
  const month = Number(mStr);
  const day = Number(dStr);
  if (year < 1 || year > 9999 || month < 1 || month > 12) {
    throwInvalidField(fieldName);
  }
  const maxDay = daysInMonth(year, month);
  if (day < 1 || day > maxDay) {
    throwInvalidField(fieldName);
  }
}

function getCalendarParts(dateStr) {
  if (typeof dateStr !== "string" || !DATE_PATTERN.test(dateStr)) {
    return null;
  }
  const [yStr, mStr, dStr] = dateStr.split("-");
  const year = Number(yStr);
  const month = Number(mStr);
  const day = Number(dStr);
  if (year < 1 || year > 9999 || month < 1 || month > 12) return null;
  const maxDay = daysInMonth(year, month);
  if (day < 1 || day > maxDay) return null;
  const d = new Date(0);
  d.setUTCFullYear(year, month - 1, day);
  d.setUTCHours(0, 0, 0, 0);
  // JavaScript getUTCDay(): 0 is Sunday, 1 is Monday ... 6 is Saturday.
  // Python start.weekday(): 0 is Monday ... 6 is Sunday.
  const pyWeekday = (d.getUTCDay() + 6) % 7;
  return { year, month, day, weekday: pyWeekday };
}

function assertValidTimezone(zone) {
  if (typeof zone !== "string" || !zone.trim() || zone.length > 80 || /^[+-]/.test(zone)) {
    throwInvalidField("timezone");
  }
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: zone });
  } catch {
    throwInvalidField("timezone");
  }
}

function parseStrictInt(value, fieldName) {
  if (typeof value === "number") {
    if (!Number.isInteger(value)) {
      throwInvalidField(fieldName);
    }
    return value;
  }
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (!INTEGER_STRING_PATTERN.test(trimmed)) {
      throwInvalidField(fieldName);
    }
    return Number(trimmed);
  }
  throwInvalidField(fieldName);
}

export function makeRecurrenceDraft(rule = null, defaults = {}) {
  const deepCopyDefaults = defaults ? JSON.parse(JSON.stringify(defaults)) : {};
  const deepCopyRule = rule ? JSON.parse(JSON.stringify(rule)) : null;

  const enabled = Boolean(deepCopyRule != null);

  const frequency = deepCopyRule?.frequency ?? deepCopyDefaults.frequency ?? "daily";
  const interval =
    deepCopyRule?.interval != null
      ? String(deepCopyRule.interval)
      : deepCopyDefaults.interval != null
      ? String(deepCopyDefaults.interval)
      : "1";

  const startDate =
    deepCopyRule?.start_date ?? deepCopyDefaults.start_date ?? "";
  const until =
    deepCopyRule?.until != null
      ? String(deepCopyRule.until)
      : deepCopyDefaults.until != null
      ? String(deepCopyDefaults.until)
      : "";

  const time = deepCopyRule?.time ?? deepCopyDefaults.time ?? "08:00";
  const timezone =
    deepCopyRule?.timezone ??
    deepCopyDefaults.timezone ??
    (typeof Intl !== "undefined"
      ? Intl.DateTimeFormat().resolvedOptions().timeZone
      : "UTC") ??
    "UTC";

  // Derive default weekday and month_day from valid start_date if not explicitly provided
  const startParts = getCalendarParts(startDate);

  let weekdays = startParts ? [startParts.weekday] : [0];
  if (Array.isArray(deepCopyRule?.weekdays)) {
    weekdays = [...deepCopyRule.weekdays];
  } else if (Array.isArray(deepCopyDefaults.weekdays)) {
    weekdays = [...deepCopyDefaults.weekdays];
  }

  const monthDay =
    deepCopyRule?.month_day != null
      ? String(deepCopyRule.month_day)
      : deepCopyDefaults.month_day != null
      ? String(deepCopyDefaults.month_day)
      : startParts
      ? String(startParts.day)
      : "1";

  let exceptions = "";
  if (Array.isArray(deepCopyRule?.exceptions)) {
    exceptions = deepCopyRule.exceptions.join("\n");
  } else if (typeof deepCopyRule?.exceptions === "string") {
    exceptions = deepCopyRule.exceptions;
  } else if (Array.isArray(deepCopyDefaults.exceptions)) {
    exceptions = deepCopyDefaults.exceptions.join("\n");
  } else if (typeof deepCopyDefaults.exceptions === "string") {
    exceptions = deepCopyDefaults.exceptions;
  }

  const catchupHours =
    deepCopyRule?.catchup_hours != null
      ? String(deepCopyRule.catchup_hours)
      : deepCopyDefaults.catchup_hours != null
      ? String(deepCopyDefaults.catchup_hours)
      : "24";

  const draft = {
    enabled,
    frequency,
    interval,
    start_date: startDate,
    until,
    time,
    timezone,
    weekdays,
    month_day: monthDay,
    exceptions,
    catchup_hours: catchupHours,
  };

  // Preserve any unknown existing fields from rule to prevent silent data loss in draft
  if (deepCopyRule && typeof deepCopyRule === "object") {
    for (const key of Object.keys(deepCopyRule)) {
      if (!(key in draft)) {
        draft[key] = deepCopyRule[key];
      }
    }
  }

  return draft;
}

export function recurrencePayload(draft) {
  if (!draft || typeof draft !== "object") {
    throwInvalidField("recurrence");
  }

  if (typeof draft.enabled !== "boolean") {
    throwInvalidField("enabled");
  }

  if (draft.enabled === false) {
    return null;
  }

  // Reject unknown server-rule keys with stable invalid_field error
  for (const key of Object.keys(draft)) {
    if (key !== "enabled" && !ALLOWED_RULE_KEYS.has(key)) {
      throwInvalidField(key);
    }
  }

  const frequency = draft.frequency;
  if (!["daily", "weekly", "monthly"].includes(frequency)) {
    throwInvalidField("frequency");
  }

  const interval = parseStrictInt(draft.interval, "interval");
  if (interval < 1 || interval > 52) {
    throwInvalidField("interval");
  }

  assertValidCalendarDate(draft.start_date, "start_date");
  const startDate = draft.start_date;

  let until = null;
  if (draft.until !== null && draft.until !== undefined && String(draft.until).trim() !== "") {
    const untilStr = String(draft.until).trim();
    assertValidCalendarDate(untilStr, "until");
    if (untilStr < startDate) {
      throwInvalidField("until");
    }
    until = untilStr;
  }

  if (typeof draft.time !== "string" || !CLOCK_PATTERN.test(draft.time)) {
    throwInvalidField("time");
  }
  const time = draft.time;

  assertValidTimezone(draft.timezone);
  const timezone = draft.timezone;

  if (!Array.isArray(draft.weekdays) || draft.weekdays.length === 0) {
    throwInvalidField("weekdays");
  }
  const parsedWeekdays = [];
  for (const d of draft.weekdays) {
    const dayInt = parseStrictInt(d, "weekdays");
    if (dayInt < 0 || dayInt > 6) {
      throwInvalidField("weekdays");
    }
    parsedWeekdays.push(dayInt);
  }
  const sortedWeekdays = Array.from(new Set(parsedWeekdays)).sort((a, b) => a - b);

  const monthDay = parseStrictInt(draft.month_day, "month_day");
  if (monthDay < 1 || monthDay > 31) {
    throwInvalidField("month_day");
  }

  let rawExceptionTokens = [];
  if (Array.isArray(draft.exceptions)) {
    rawExceptionTokens = draft.exceptions;
  } else if (typeof draft.exceptions === "string") {
    rawExceptionTokens = draft.exceptions
      .split(/[\r\n,]+/)
      .map(s => s.trim())
      .filter(Boolean);
  } else if (draft.exceptions === null || draft.exceptions === undefined) {
    rawExceptionTokens = [];
  } else {
    throwInvalidField("exceptions");
  }

  if (rawExceptionTokens.length > 366) {
    throwInvalidField("exceptions");
  }

  const validatedExceptions = new Set();
  for (const item of rawExceptionTokens) {
    const trimmed = String(item).trim();
    assertValidCalendarDate(trimmed, "exceptions");
    validatedExceptions.add(trimmed);
  }
  const sortedExceptions = Array.from(validatedExceptions).sort();

  const catchupHours = parseStrictInt(draft.catchup_hours, "catchup_hours");
  if (catchupHours < 0 || catchupHours > 48) {
    throwInvalidField("catchup_hours");
  }

  return {
    frequency,
    interval,
    start_date: startDate,
    until,
    time,
    timezone,
    weekdays: sortedWeekdays,
    month_day: monthDay,
    exceptions: sortedExceptions,
    catchup_hours: catchupHours,
  };
}

function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) {
    node.textContent = String(text);
  }
  if (className) {
    node.className = className;
  }
  return node;
}

export function renderRecurrence(
  container,
  draft,
  {
    language = "en",
    lockedFields = [],
    onChange = () => {},
    isStale = () => false,
  } = {}
) {
  const copy = RECURRENCE_COPY[language] || RECURRENCE_COPY.en;
  const lockedSet = new Set(lockedFields);

  const fieldset = el("fieldset", null, "recurrence-fieldset");
  fieldset.setAttribute("data-recurrence-group", "main");

  const legend = el("legend", copy.legend);
  fieldset.append(legend);

  // 1. Enable toggle
  const enableWrap = el("label", null, "recurrence-row recurrence-enable");
  enableWrap.setAttribute("data-recurrence-field", "enabled");
  const enableCheckbox = el("input");
  enableCheckbox.type = "checkbox";
  enableCheckbox.checked = Boolean(draft.enabled);
  enableCheckbox.setAttribute("data-recurrence-control", "enabled");
  if (lockedSet.has("enabled")) {
    enableCheckbox.disabled = true;
  }
  const enableSpan = el("span", ` ${copy.enable}`);
  enableWrap.append(enableCheckbox, enableSpan);
  fieldset.append(enableWrap);

  // Details container for all recurrence controls
  const bodyContainer = el("div", null, "recurrence-body");
  bodyContainer.setAttribute("data-recurrence-group", "body");
  fieldset.append(bodyContainer);

  // 2. Frequency
  const freqWrap = el("label", copy.frequency, "recurrence-label");
  freqWrap.setAttribute("data-recurrence-field", "frequency");
  const freqSelect = el("select");
  freqSelect.setAttribute("data-recurrence-control", "frequency");
  if (lockedSet.has("frequency")) freqSelect.disabled = true;

  for (const freq of ["daily", "weekly", "monthly"]) {
    const opt = el("option", copy[freq]);
    opt.value = freq;
    if (draft.frequency === freq) opt.selected = true;
    freqSelect.append(opt);
  }
  freqWrap.append(freqSelect);
  bodyContainer.append(freqWrap);

  // 3. Interval
  const intervalWrap = el("label", copy.interval, "recurrence-label");
  intervalWrap.setAttribute("data-recurrence-field", "interval");
  const intervalInput = el("input");
  intervalInput.type = "number";
  intervalInput.min = "1";
  intervalInput.max = "52";
  intervalInput.step = "1";
  intervalInput.value = draft.interval ?? "1";
  intervalInput.setAttribute("data-recurrence-control", "interval");
  if (lockedSet.has("interval")) intervalInput.disabled = true;
  const intervalUnitSpan = el("span", ` ${copy.intervalDailyUnit}`, "recurrence-interval-unit");
  intervalWrap.append(intervalInput, intervalUnitSpan);
  bodyContainer.append(intervalWrap);

  // 4. Start date
  const startWrap = el("label", copy.startDate, "recurrence-label");
  startWrap.setAttribute("data-recurrence-field", "start_date");
  const startInput = el("input");
  startInput.type = "date";
  startInput.value = draft.start_date ?? "";
  startInput.setAttribute("data-recurrence-control", "start_date");
  if (lockedSet.has("start_date") || lockedSet.has("start") || lockedSet.has("date")) {
    startInput.disabled = true;
  }
  startWrap.append(startInput);
  bodyContainer.append(startWrap);

  // 5. Until date (optional)
  const untilWrap = el("label", copy.untilDate, "recurrence-label");
  untilWrap.setAttribute("data-recurrence-field", "until");
  const untilInput = el("input");
  untilInput.type = "date";
  untilInput.value = draft.until ?? "";
  untilInput.setAttribute("data-recurrence-control", "until");
  if (lockedSet.has("until") || lockedSet.has("date")) {
    untilInput.disabled = true;
  }
  untilWrap.append(untilInput);
  bodyContainer.append(untilWrap);

  // 6. Time
  const timeWrap = el("label", copy.time, "recurrence-label");
  timeWrap.setAttribute("data-recurrence-field", "time");
  const timeInput = el("input");
  timeInput.type = "time";
  timeInput.value = draft.time ?? "08:00";
  timeInput.setAttribute("data-recurrence-control", "time");
  if (lockedSet.has("time")) timeInput.disabled = true;
  timeWrap.append(timeInput);
  bodyContainer.append(timeWrap);

  // 7. Timezone
  const tzWrap = el("label", copy.timezone, "recurrence-label");
  tzWrap.setAttribute("data-recurrence-field", "timezone");
  const tzInput = el("input");
  tzInput.type = "text";
  tzInput.value = draft.timezone ?? "UTC";
  tzInput.maxLength = 80;
  tzInput.setAttribute("data-recurrence-control", "timezone");
  if (lockedSet.has("timezone")) tzInput.disabled = true;
  tzWrap.append(tzInput);
  bodyContainer.append(tzWrap);

  // 8. Weekdays checkboxes
  const weekdaysGroup = el("fieldset", null, "recurrence-weekdays-fieldset");
  weekdaysGroup.setAttribute("data-recurrence-field", "weekdays");
  weekdaysGroup.setAttribute("data-recurrence-group", "weekdays");
  const weekdaysLegend = el("legend", copy.weekdays);
  weekdaysGroup.append(weekdaysLegend);

  const weekdayBoxes = [];
  const activeWeekdaysSet = new Set(Array.isArray(draft.weekdays) ? draft.weekdays : []);

  copy.dayNames.forEach((name, dayIndex) => {
    const dayWrap = el("label", null, "recurrence-weekday-label");
    const box = el("input");
    box.type = "checkbox";
    box.value = String(dayIndex);
    box.checked = activeWeekdaysSet.has(dayIndex);
    box.setAttribute("data-recurrence-control", "weekdays");
    box.setAttribute("data-weekday-index", String(dayIndex));
    if (lockedSet.has("weekdays")) box.disabled = true;
    weekdayBoxes.push(box);

    const fullTitle = copy.dayNamesFull?.[dayIndex] || name;
    dayWrap.setAttribute("title", fullTitle);
    dayWrap.append(box, el("span", ` ${name}`));
    weekdaysGroup.append(dayWrap);
  });
  bodyContainer.append(weekdaysGroup);

  // 9. Day of month
  const monthDayWrap = el("label", copy.monthDay, "recurrence-label");
  monthDayWrap.setAttribute("data-recurrence-field", "month_day");
  monthDayWrap.setAttribute("data-recurrence-group", "month_day");
  const monthDayInput = el("input");
  monthDayInput.type = "number";
  monthDayInput.min = "1";
  monthDayInput.max = "31";
  monthDayInput.step = "1";
  monthDayInput.value = draft.month_day ?? "1";
  monthDayInput.setAttribute("data-recurrence-control", "month_day");
  if (lockedSet.has("month_day")) monthDayInput.disabled = true;
  monthDayWrap.append(monthDayInput);
  bodyContainer.append(monthDayWrap);

  // 10. Exception dates
  const exceptionsWrap = el("label", copy.exceptions, "recurrence-label");
  exceptionsWrap.setAttribute("data-recurrence-field", "exceptions");
  const exceptionsTextarea = el("textarea");
  exceptionsTextarea.rows = 3;
  exceptionsTextarea.value = draft.exceptions ?? "";
  exceptionsTextarea.setAttribute("data-recurrence-control", "exceptions");
  if (lockedSet.has("exceptions")) exceptionsTextarea.disabled = true;
  exceptionsWrap.append(exceptionsTextarea);
  bodyContainer.append(exceptionsWrap);

  // 11. Catchup hours
  const catchupWrap = el("label", copy.catchupHours, "recurrence-label");
  catchupWrap.setAttribute("data-recurrence-field", "catchup_hours");
  const catchupInput = el("input");
  catchupInput.type = "number";
  catchupInput.min = "0";
  catchupInput.max = "48";
  catchupInput.step = "1";
  catchupInput.value = draft.catchup_hours ?? "24";
  catchupInput.setAttribute("data-recurrence-control", "catchup_hours");
  if (lockedSet.has("catchup_hours")) catchupInput.disabled = true;
  catchupWrap.append(catchupInput);
  bodyContainer.append(catchupWrap);

  // 12. Localized explanations
  const hintsContainer = el("details", null, "recurrence-hints");
  hintsContainer.append(el("summary", copy.help));
  hintsContainer.setAttribute("data-recurrence-group", "hints");

  const tzHint = el("p", copy.timezoneExplanation, "recurrence-hint");
  tzHint.setAttribute("data-recurrence-hint", "timezone");
  hintsContainer.append(tzHint);

  const dstHint = el("p", copy.dstExplanation, "recurrence-hint");
  dstHint.setAttribute("data-recurrence-hint", "dst");
  hintsContainer.append(dstHint);

  const monthHint = el("p", copy.monthMissingExplanation, "recurrence-hint");
  monthHint.setAttribute("data-recurrence-hint", "month_missing");
  hintsContainer.append(monthHint);

  const catchupHint = el("p", copy.catchupZeroExplanation, "recurrence-hint");
  catchupHint.setAttribute("data-recurrence-hint", "catchup_zero");
  hintsContainer.append(catchupHint);

  bodyContainer.append(hintsContainer);

  // Dynamic visibility and disabling:
  // Turning recurrence fully off disables its body controls so that invalid hidden values
  // do not block native form submission. When turning repeat on, controls are re-enabled
  // UNLESS explicitly locked via lockedFields or externally disabled.
  function isFieldLocked(field) {
    if (lockedSet.has(field)) return true;
    if (field === "start_date" && (lockedSet.has("start") || lockedSet.has("date"))) return true;
    if (field === "until" && lockedSet.has("date")) return true;
    return false;
  }

  const managedDisabled = new WeakSet();
  const externalDisabled = new WeakSet();
  function syncControlDisabled(ctrl, field, isIrrelevant) {
    if (ctrl.disabled && !managedDisabled.has(ctrl)) externalDisabled.add(ctrl);
    if (!draft.enabled) {
      ctrl.disabled = true;
    } else if (isIrrelevant) {
      // Hidden irrelevant number/text controls must not block native form submission
      ctrl.disabled = true;
    } else {
      ctrl.disabled = isFieldLocked(field) || externalDisabled.has(ctrl);
    }
    if (ctrl.disabled) managedDisabled.add(ctrl);
    else managedDisabled.delete(ctrl);
  }

  function updateVisibility() {
    bodyContainer.hidden = !draft.enabled;
    const freq = draft.frequency;

    const isWeekdaysIrrelevant = !draft.enabled || freq !== "weekly";
    const isMonthDayIrrelevant = !draft.enabled || freq !== "monthly";

    if (freq === "daily") {
      intervalUnitSpan.textContent = ` ${copy.intervalDailyUnit}`;
      weekdaysGroup.hidden = true;
      monthDayWrap.hidden = true;
      monthHint.hidden = true;
    } else if (freq === "weekly") {
      intervalUnitSpan.textContent = ` ${copy.intervalWeeklyUnit}`;
      weekdaysGroup.hidden = false;
      monthDayWrap.hidden = true;
      monthHint.hidden = true;
    } else if (freq === "monthly") {
      intervalUnitSpan.textContent = ` ${copy.intervalMonthlyUnit}`;
      weekdaysGroup.hidden = true;
      monthDayWrap.hidden = false;
      monthHint.hidden = false;
    }

    // Update disabled attributes
    syncControlDisabled(freqSelect, "frequency", false);
    syncControlDisabled(intervalInput, "interval", false);
    syncControlDisabled(startInput, "start_date", false);
    syncControlDisabled(untilInput, "until", false);
    syncControlDisabled(timeInput, "time", false);
    syncControlDisabled(tzInput, "timezone", false);
    for (const box of weekdayBoxes) {
      syncControlDisabled(box, "weekdays", isWeekdaysIrrelevant);
    }
    syncControlDisabled(monthDayInput, "month_day", isMonthDayIrrelevant);
    syncControlDisabled(exceptionsTextarea, "exceptions", false);
    syncControlDisabled(catchupInput, "catchup_hours", false);
  }
  updateVisibility();

  // Event handlers guarded by control.disabled and isStale()
  function guardedMutate(control, fn) {
    if (control && control.disabled) {
      return;
    }
    if (typeof isStale === "function" && isStale()) {
      return;
    }
    fn();
    updateVisibility();
    if (typeof onChange === "function") {
      onChange(draft);
    }
  }

  enableCheckbox.addEventListener("change", () => {
    guardedMutate(enableCheckbox, () => {
      draft.enabled = enableCheckbox.checked;
    });
  });

  freqSelect.addEventListener("change", () => {
    guardedMutate(freqSelect, () => {
      draft.frequency = freqSelect.value;
    });
  });

  intervalInput.addEventListener("input", () => {
    guardedMutate(intervalInput, () => {
      draft.interval = intervalInput.value;
    });
  });

  startInput.addEventListener("input", () => {
    guardedMutate(startInput, () => {
      draft.start_date = startInput.value;
    });
  });

  untilInput.addEventListener("input", () => {
    guardedMutate(untilInput, () => {
      draft.until = untilInput.value;
    });
  });

  timeInput.addEventListener("input", () => {
    guardedMutate(timeInput, () => {
      draft.time = timeInput.value;
    });
  });

  tzInput.addEventListener("input", () => {
    guardedMutate(tzInput, () => {
      draft.timezone = tzInput.value;
    });
  });

  monthDayInput.addEventListener("input", () => {
    guardedMutate(monthDayInput, () => {
      draft.month_day = monthDayInput.value;
    });
  });

  exceptionsTextarea.addEventListener("input", () => {
    guardedMutate(exceptionsTextarea, () => {
      draft.exceptions = exceptionsTextarea.value;
    });
  });

  catchupInput.addEventListener("input", () => {
    guardedMutate(catchupInput, () => {
      draft.catchup_hours = catchupInput.value;
    });
  });

  for (const box of weekdayBoxes) {
    box.addEventListener("change", () => {
      guardedMutate(box, () => {
        const checkedIndices = weekdayBoxes
          .filter(b => b.checked)
          .map(b => Number(b.value))
          .sort((a, b) => a - b);
        draft.weekdays = checkedIndices;
      });
    });
  }

  container.append(fieldset);
  return fieldset;
}
