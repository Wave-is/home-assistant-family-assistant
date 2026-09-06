/* Recurring shopping series UI: textContent-only rendering, typed payloads, parent-only controls. */

export const SHOPPING_SERIES_COPY = {
  en: {
    title: "Recurring shopping",
    addSeries: "Add recurring item",
    editSeries: "Edit recurring item",
    recurring: "Recurring",
    empty: "No recurring shopping items scheduled yet.",
    name: "Name",
    quantity: "Quantity",
    unit: "Unit",
    unitPlaceholder: "e.g. kg, l, pcs",
    buyer: "Assigned buyer (optional)",
    buyerNone: "Anyone (unassigned)",
    inactiveMarker: "inactive",
    frequency: "Repeat",
    daily: "Daily",
    weekly: "Weekly",
    monthly: "Monthly",
    startDate: "Start date",
    untilDate: "End date (optional)",
    time: "Release time",
    timezone: "Time zone",
    interval: "Every N days / weeks / months",
    monthDay: "Day of month (1–31)",
    weeklyDays: "Days for weekly recurrence",
    advanced: "Advanced settings",
    store: "Store (optional)",
    category: "Category (optional)",
    note: "Note (optional)",
    exceptions: "Excluded dates (YYYY-MM-DD, comma-separated)",
    catchupHours: "Catchup window (hours, 0–48)",
    save: "Save",
    cancel: "Cancel",
    back: "Back",
    enable: "Enable",
    disable: "Disable",
    enabled: "Enabled",
    disabled: "Disabled",
    duplicateNotice: "No duplicate item will be added while an unfinished purchase from the same series is still open (including partially purchased items). Manual shopping items with the same name are tracked separately and not merged.",
    validationRequired: "Please enter a valid name.",
    validationQuantity: "Quantity must be between 0.001 and 1000000.",
    validationInterval: "Interval must be an integer between 1 and 52.",
    validationMonthDay: "Month day must be an integer between 1 and 31.",
    validationWeekdays: "Please select at least one weekday for weekly recurrence.",
    validationCatchup: "Catchup hours must be between 0 and 48.",
    dayNames: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
  },
  ru: {
    title: "Регулярные покупки",
    addSeries: "Добавить регулярную покупку",
    editSeries: "Изменить регулярную покупку",
    recurring: "Регулярно",
    empty: "Пока нет настроенных регулярных покупок.",
    name: "Название",
    quantity: "Количество",
    unit: "Единица",
    unitPlaceholder: "например: кг, л, шт",
    buyer: "Покупатель (необязательно)",
    buyerNone: "Любой (без назначения)",
    inactiveMarker: "неактивен",
    frequency: "Повторять",
    daily: "Ежедневно",
    weekly: "Еженедельно",
    monthly: "Ежемесячно",
    startDate: "Дата начала",
    untilDate: "Дата окончания (необязательно)",
    time: "Время создания",
    timezone: "Часовой пояс",
    interval: "Каждые N дней / недель / месяцев",
    monthDay: "День месяца (1–31)",
    weeklyDays: "Дни еженедельного повторения",
    advanced: "Дополнительные параметры",
    store: "Магазин (необязательно)",
    category: "Категория (необязательно)",
    note: "Заметка (необязательно)",
    exceptions: "Исключения: даты ГГГГ-ММ-ДД через запятую",
    catchupHours: "Окно наверстывания (часов, 0–48)",
    save: "Сохранить",
    cancel: "Отмена",
    back: "Назад",
    enable: "Включить",
    disable: "Выключить",
    enabled: "Включено",
    disabled: "Выключено",
    duplicateNotice: "Новая позиция не создается, пока в списке остаётся незавершённая покупка этой серии (включая частичные покупки). Добавленные вручную покупки с таким же названием не объединяются.",
    validationRequired: "Пожалуйста, укажите название.",
    validationQuantity: "Количество должно быть от 0.001 до 1000000.",
    validationInterval: "Интервал должен быть целым числом от 1 до 52.",
    validationMonthDay: "День месяца должен быть числом от 1 до 31.",
    validationWeekdays: "Выберите хотя бы один день недели для еженедельного повтора.",
    validationCatchup: "Окно наверстывания должно быть от 0 до 48 часов.",
    dayNames: ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"],
  },
  uk: {
    title: "Регулярні покупки",
    addSeries: "Додати регулярну покупку",
    editSeries: "Редагувати регулярну покупку",
    recurring: "Регулярно",
    empty: "Поки що немає налаштованих регулярних покупок.",
    name: "Назва",
    quantity: "Кількість",
    unit: "Одиниця",
    unitPlaceholder: "наприклад: кг, л, шт",
    buyer: "Покупець (необов’язково)",
    buyerNone: "Будь-хто (не призначено)",
    inactiveMarker: "неактивний",
    frequency: "Повторювати",
    daily: "Щодня",
    weekly: "Щотижня",
    monthly: "Щомісяця",
    startDate: "Дата початку",
    untilDate: "Дата завершення (необов’язково)",
    time: "Час створення",
    timezone: "Часовий пояс",
    interval: "Кожні N днів / тижнів / місяців",
    monthDay: "День місяця (1–31)",
    weeklyDays: "Дні щотижневого повторення",
    advanced: "Додаткові налаштування",
    store: "Магазин (необов’язково)",
    category: "Категорія (необов’язково)",
    note: "Примітка (необов’язково)",
    exceptions: "Винятки: дати РРРР-ММ-ДД через кому",
    catchupHours: "Вікно наздоганяння (годин, 0–48)",
    save: "Зберегти",
    cancel: "Скасувати",
    back: "Назад",
    enable: "Увімкнути",
    disable: "Вимкнути",
    enabled: "Увімкнено",
    disabled: "Вимкнено",
    duplicateNotice: "Новий пункт не додається, доки відкрита незавершена покупка з цієї ж серії (зокрема частково куплені товари). Додані вручну покупки з такою ж назвою ведуться окремо й не об’єднуються.",
    validationRequired: "Будь ласка, вкажіть назву.",
    validationQuantity: "Кількість має бути від 0.001 до 1000000.",
    validationInterval: "Інтервал має бути цілим числом від 1 до 52.",
    validationMonthDay: "День місяця має бути числом від 1 до 31.",
    validationWeekdays: "Виберіть хоча б один день тижня для щотижневого повторення.",
    validationCatchup: "Вікно наздоганяння має бути від 0 до 48 годин.",
    dayNames: ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"],
  },
};

function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = String(text);
  if (className) node.className = className;
  return node;
}

function getLocalToday(zone) {
  try {
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: zone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).formatToParts(new Date());
    return ["year", "month", "day"]
      .map(k => parts.find(p => p.type === k)?.value)
      .join("-");
  } catch {
    const d = new Date();
    const pad = n => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  }
}

export function renderShoppingSeries(card, body) {
  const role = card._data?.role;
  if (role === "guest") return;

  const lang = card._config?.language || card._hass?.language?.split("-")[0] || "en";
  const t = SHOPPING_SERIES_COPY[lang] || SHOPPING_SERIES_COPY.en;
  const isParent = Boolean(card.parent);
  const seriesList = card._data?.shopping_series || [];

  const container = el("section", null, "shopping-series-container");

  const header = el("div", null, "toolbar");
  header.append(el("strong", t.title));
  if (isParent) {
    const isFormOpen = Boolean(card._shoppingSeriesFormOpen);
    const toggleBtn = card.button(
      isFormOpen ? t.back : t.addSeries,
      () => {
        card._shoppingSeriesFormOpen = !card._shoppingSeriesFormOpen;
        card._shoppingSeriesEditingItem = null;
        card._shoppingSeriesDraft = null;
        card._form = false;
        if (typeof card.render === "function") card.render();
      },
      !isFormOpen
    );
    header.append(toggleBtn);
  }
  container.append(header);

  container.append(el("p", t.duplicateNotice, "notice"));

  if (isParent && card._shoppingSeriesFormOpen) {
    const editing = card._shoppingSeriesDraft || card._shoppingSeriesEditingItem || null;
    const form = buildSeriesForm(card, t, editing);
    container.append(form);
  }

  if (seriesList.length === 0) {
    container.append(el("div", t.empty, "empty"));
  } else {
    const list = el("div", null, "list");
    for (const item of seriesList) {
      const row = el("div", null, "item");

      const titleLine = el("div", null, "row");
      const titleStrong = el("strong", `${t.recurring} · ${item.name}`, "grow");
      const statusBadge = el("span", t[item.enabled ? "enabled" : "disabled"], "badge");
      titleLine.append(titleStrong, statusBadge);
      row.append(titleLine);

      const parts = [];
      const qty = item.quantity != null ? String(item.quantity) : "1";
      parts.push(`${qty}${item.unit ? " " + item.unit : ""}`);

      if (item.rule?.frequency) {
        parts.push(t[item.rule.frequency] || item.rule.frequency);
      }
      if (item.rule?.time) {
        parts.push(item.rule.time);
      }
      if (item.rule?.interval && item.rule.interval > 1) {
        parts.push(`×${item.rule.interval}`);
      }
      if (item.rule?.frequency === "weekly" && Array.isArray(item.rule.weekdays) && item.rule.weekdays.length) {
        const daysStr = item.rule.weekdays.map(d => t.dayNames[d] || d).join(", ");
        parts.push(daysStr);
      }
      if (item.rule?.frequency === "monthly" && item.rule.month_day) {
        parts.push(`${t.monthDay}: ${item.rule.month_day}`);
      }

      if (item.buyer) {
        const buyerMember = card._data?.members?.find(m => m.id === item.buyer);
        if (buyerMember) {
          const nameDisplay = buyerMember.active
            ? buyerMember.name
            : `${buyerMember.name} (${t.inactiveMarker})`;
          parts.push(`${t.buyer}: ${nameDisplay}`);
        }
      }
      if (item.store) {
        parts.push(item.store);
      }
      if (item.category) {
        parts.push(item.category);
      }

      row.append(el("div", parts.join(" · "), "sub"));

      if (item.note) {
        row.append(el("div", item.note, "sub"));
      }

      if (isParent) {
        const actions = el("div", null, "actions");

        const editBtn = card.button(t.editSeries, () => {
          card._shoppingSeriesEditingItem = item;
          card._shoppingSeriesDraft = null;
          card._form = false;
          card._shoppingSeriesFormOpen = true;
          if (typeof card.render === "function") card.render();
        });
        actions.append(editBtn);

        const enableBtn = card.button(
          t[item.enabled ? "disable" : "enable"],
          () => {
            card.command("shopping.series_enable", {
              id: item.id,
              revision: item.revision,
              enabled: !item.enabled,
            });
          }
        );
        actions.append(enableBtn);

        row.append(actions);
      }

      list.append(row);
    }
    container.append(list);
  }

  body.append(container);
}

function buildSeriesForm(card, t, editing) {
  const form = el("form", null, "shopping-series-form");
  const defaultTz =
    card._data?.settings?.timezone ||
    card._hass?.config?.time_zone ||
    (typeof Intl !== "undefined" ? Intl.DateTimeFormat().resolvedOptions().timeZone : "UTC") ||
    "UTC";

  const todayStr = getLocalToday(defaultTz);
  const todayDay = Number(todayStr.split("-")[2]) || 1;

  // Error container
  const errorBox = el("div", null, "notice");
  errorBox.style.display = "none";
  errorBox.setAttribute("role", "alert");
  form.append(errorBox);

  function showError(msg) {
    errorBox.textContent = msg;
    errorBox.style.display = "block";
  }

  // 1. Basic Fields
  // Name
  const nameInput = card.input(form, "name", t.name, "text", editing?.name || "", true);
  nameInput.maxLength = 200;

  // Quantity & Unit
  const fieldsRow = el("div", null, "fields");
  form.append(fieldsRow);
  const qtyInput = card.input(
    fieldsRow,
    "quantity",
    t.quantity,
    "number",
    editing?.quantity != null ? String(editing?.quantity) : "1",
    true
  );
  qtyInput.min = "0.001";
  qtyInput.max = "1000000";
  qtyInput.step = "any";

  const unitInput = card.input(
    fieldsRow,
    "unit",
    t.unit,
    "text",
    editing?.unit || "",
    false
  );
  unitInput.placeholder = t.unitPlaceholder;
  unitInput.maxLength = 32;

  // Buyer (optional active family member, or preserved inactive existing buyer)
  const buyerWrap = el("label", t.buyer);
  const buyerSelect = el("select");
  buyerSelect.name = "buyer";
  buyerSelect.setAttribute("aria-label", t.buyer);
  const unassignedOpt = el("option", t.buyerNone);
  unassignedOpt.value = "";
  buyerSelect.append(unassignedOpt);

  const allMembers = card._data?.members || [];
  const activeMembers = allMembers.filter(m => m.active && m.role !== "guest");
  for (const m of activeMembers) {
    const opt = el("option", m.name);
    opt.value = m.id;
    if (editing?.buyer === m.id) opt.selected = true;
    buyerSelect.append(opt);
  }

  // If editing has a buyer that is not in activeMembers, keep them selectable with inactive marker
  if (editing?.buyer && !activeMembers.some(m => m.id === editing.buyer)) {
    const inactiveMember = allMembers.find(m => m.id === editing.buyer);
    const displayName = inactiveMember
      ? `${inactiveMember.name} (${t.inactiveMarker})`
      : `(${t.inactiveMarker})`;
    const inactiveOpt = el("option", displayName);
    inactiveOpt.value = editing.buyer;
    inactiveOpt.selected = true;
    buyerSelect.append(inactiveOpt);
  }

  buyerWrap.append(buyerSelect);
  form.append(buyerWrap);

  // Recurrence / Frequency
  const freqWrap = el("label", t.frequency);
  const freqSelect = el("select");
  freqSelect.name = "frequency";
  freqSelect.setAttribute("aria-label", t.frequency);
  for (const f of ["daily", "weekly", "monthly"]) {
    const opt = el("option", t[f] || f);
    opt.value = f;
    if ((editing?.rule?.frequency || "weekly") === f) opt.selected = true;
    freqSelect.append(opt);
  }
  freqWrap.append(freqSelect);
  form.append(freqWrap);

  // Time & Start Date
  const scheduleRow = el("div", null, "fields");
  form.append(scheduleRow);
  card.input(
    scheduleRow,
    "time",
    t.time,
    "time",
    editing?.rule?.time || "08:00",
    true
  );
  const startDateInput = card.input(
    scheduleRow,
    "start_date",
    t.startDate,
    "date",
    editing?.rule?.start_date || todayStr,
    true
  );

  // Monthly day explicit field
  const monthDayWrap = el("div", null, "month-day-wrap");
  const monthDayVal =
    editing?.rule?.month_day != null
      ? String(editing.rule.month_day)
      : String(todayDay);
  const monthDayInput = card.input(
    monthDayWrap,
    "month_day",
    t.monthDay,
    "number",
    monthDayVal,
    false
  );
  monthDayInput.min = "1";
  monthDayInput.max = "31";
  monthDayInput.step = "1";
  form.append(monthDayWrap);

  // Weekly days checkboxes
  const weekdaysFieldset = el("fieldset", null, "weekdays-fieldset");
  weekdaysFieldset.append(el("legend", t.weeklyDays));
  const activeDays = new Set(
    Array.isArray(editing?.rule?.weekdays)
      ? editing.rule.weekdays
      : [0, 1, 2, 3, 4]
  );
  t.dayNames.forEach((name, dayIdx) => {
    const label = el("label", name);
    const box = el("input");
    box.type = "checkbox";
    box.name = "weekdays";
    box.value = String(dayIdx);
    box.checked = activeDays.has(dayIdx);
    label.append(box);
    weekdaysFieldset.append(label);
  });
  form.append(weekdaysFieldset);

  function syncRecurrenceUI() {
    const currentFreq = freqSelect.value;
    weekdaysFieldset.hidden = currentFreq !== "weekly";
    monthDayWrap.hidden = currentFreq !== "monthly";
  }
  syncRecurrenceUI();
  freqSelect.addEventListener("change", syncRecurrenceUI);

  // 2. Advanced fields
  const details = el("details");
  const summary = el("summary", t.advanced);
  const advancedBody = el("div", null, "advanced");
  details.append(summary, advancedBody);

  const storeInput = card.input(advancedBody, "store", t.store, "text", editing?.store || "", false);
  storeInput.maxLength = 80;

  const categoryInput = card.input(advancedBody, "category", t.category, "text", editing?.category || "", false);
  categoryInput.maxLength = 80;

  const noteInput = card.input(advancedBody, "note", t.note, "text", editing?.note || "", false);
  noteInput.maxLength = 500;

  const tzInput = card.input(
    advancedBody,
    "timezone",
    t.timezone,
    "text",
    editing?.rule?.timezone || defaultTz,
    true
  );

  const untilInput = card.input(
    advancedBody,
    "until",
    t.untilDate,
    "date",
    editing?.rule?.until || "",
    false
  );

  const intervalInput = card.input(
    advancedBody,
    "interval",
    t.interval,
    "number",
    editing?.rule?.interval != null ? String(editing.rule.interval) : "1",
    false
  );
  intervalInput.min = "1";
  intervalInput.max = "52";
  intervalInput.step = "1";

  card.input(
    advancedBody,
    "exceptions",
    t.exceptions,
    "text",
    Array.isArray(editing?.rule?.exceptions) ? editing.rule.exceptions.join(", ") : "",
    false
  );

  const catchupInput = card.input(
    advancedBody,
    "catchup_hours",
    t.catchupHours,
    "number",
    editing?.rule?.catchup_hours != null ? String(editing.rule.catchup_hours) : "24",
    false
  );
  catchupInput.min = "0";
  catchupInput.max = "48";
  catchupInput.step = "1";

  form.append(details);

  // 3. Form action buttons (Save & Cancel)
  const actions = el("div", null, "actions");
  const submitBtn = el("button", t.save, "primary");
  submitBtn.type = "submit";
  submitBtn.disabled = Boolean(card._writing);
  actions.append(submitBtn);

  const cancelBtn = card.button(t.cancel, () => {
    card._shoppingSeriesFormOpen = false;
    card._shoppingSeriesEditingItem = null;
    card._shoppingSeriesDraft = null;
    if (typeof card.render === "function") card.render();
  });
  actions.append(cancelBtn);
  form.append(actions);

  form.addEventListener("submit", async event => {
    event.preventDefault();
    if (card._writing) return;
    errorBox.style.display = "none";

    const formData = new FormData(form);
    const rawName = String(formData.get("name") || "").trim();
    if (!rawName) {
      showError(t.validationRequired);
      return;
    }

    const rawQty = Number(formData.get("quantity"));
    if (!Number.isFinite(rawQty) || rawQty < 0.001 || rawQty > 1000000) {
      showError(t.validationQuantity);
      return;
    }

    const frequency = String(formData.get("frequency") || "daily");
    const intervalVal = Number(formData.get("interval") || 1);
    if (!Number.isInteger(intervalVal) || intervalVal < 1 || intervalVal > 52) {
      showError(t.validationInterval);
      return;
    }

    const catchupVal = Number(formData.get("catchup_hours") || 24);
    if (!Number.isInteger(catchupVal) || catchupVal < 0 || catchupVal > 48) {
      showError(t.validationCatchup);
      return;
    }

    const rule = {
      frequency,
      interval: intervalVal,
      start_date: String(formData.get("start_date") || todayStr),
      time: String(formData.get("time") || "08:00"),
      timezone: String(formData.get("timezone") || defaultTz),
      catchup_hours: catchupVal,
    };

    const rawUntil = String(formData.get("until") || "").trim();
    if (rawUntil) {
      rule.until = rawUntil;
    } else {
      rule.until = null;
    }

    if (frequency === "weekly") {
      const weekdays = formData.getAll("weekdays").map(Number);
      if (weekdays.length === 0) {
        showError(t.validationWeekdays);
        return;
      }
      rule.weekdays = weekdays.sort((a, b) => a - b);
    } else if (editing?.rule?.weekdays) {
      rule.weekdays = editing.rule.weekdays;
    }

    if (frequency === "monthly") {
      const mDay = Number(formData.get("month_day"));
      if (!Number.isInteger(mDay) || mDay < 1 || mDay > 31) {
        showError(t.validationMonthDay);
        return;
      }
      rule.month_day = mDay;
    } else if (editing?.rule?.month_day != null) {
      rule.month_day = editing.rule.month_day;
    }

    const rawExceptions = String(formData.get("exceptions") || "").trim();
    if (rawExceptions) {
      rule.exceptions = rawExceptions
        .split(",")
        .map(s => s.trim())
        .filter(Boolean);
    } else {
      rule.exceptions = [];
    }

    const payload = {
      name: rawName,
      quantity: rawQty,
      unit: String(formData.get("unit") || "").trim(),
      category: String(formData.get("category") || "").trim(),
      store: String(formData.get("store") || "").trim(),
      note: String(formData.get("note") || "").trim(),
      rule,
    };

    const buyerVal = String(formData.get("buyer") || "").trim();
    payload.buyer = buyerVal || null;

    if (editing?.id) {
      payload.id = editing.id;
      payload.revision = editing.revision;
      if (editing.enabled !== undefined) {
        payload.enabled = editing.enabled;
      }
    } else {
      payload.enabled = true;
    }

    const generation = card._generation;
    card._shoppingSeriesDraft = structuredClone(payload);
    await card.command("shopping.series_save", payload);
    if (generation !== card._generation) return;
    // The card adapter reports failures through _actionError. Keep the entered
    // values and original revision for a deliberate retry or conflict review.
    if (!card._actionError) {
      card._shoppingSeriesFormOpen = false;
      card._shoppingSeriesEditingItem = null;
      card._shoppingSeriesDraft = null;
      card.render();
    }
  });

  return form;
}
