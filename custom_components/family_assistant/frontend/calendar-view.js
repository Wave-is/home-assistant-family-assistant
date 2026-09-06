/* Calendar view rendering and copy for Family Assistant card. All user content inserted via textContent only. */
import { wallTime, wallTimeCandidates } from "./local-time.js";

export const CALENDAR_COPY = {
  en: {
    history: "History", created: "Created", updated: "Edited", export_on: "Enabled", export_off: "Disabled",
    title: "Family calendar",
    agenda_title: "Upcoming (next 30 days)",
    events_title: "All events",
    no_occurrences: "No upcoming events scheduled.",
    no_events: "No calendar events.",
    new_event: "New event",
    edit: "Edit",
    cancel: "Cancel",
    save: "Save",
    retry: "Retry",
    approve: "Approve",
    cancel_event: "Cancel event",
    archive: "Archive",
    event_title: "Title",
    description: "Description",
    location: "Location",
    all_day: "All day",
    start_date: "Start date",
    end_date: "End date (exclusive)",
    start_time: "Start date & time",
    end_time: "End date & time",
    timezone: "Time zone",
    participants: "Participants",
    escort: "Escort (adult / parent)",
    none: "None",
    visibility: "Visibility",
    visibility_family: "Whole family",
    visibility_participants: "Participants only",
    preparation: "Preparation notes (one per line)",
    reminders: "Reminders before event (minutes, comma-separated 0..10080, max 6)",
    reason: "Reason",
    status_tentative: "Tentative (needs parent approval)",
    status_confirmed: "Confirmed",
    status_cancelled: "Cancelled",
    status_archived: "Archived",
    unknown_member: "Unknown member",
    reason_required: "Reason is required.",
    title_required: "Title is required.",
    start_end_order: "End time must be strictly after start time.",
    export_title: "Export to Home Assistant",
    publish_to_ha: "Publish confirmed family events to Home Assistant calendar entity",
    confirm_public_title: "Confirm public visibility",
    confirm_public_notice: "Home Assistant users with access to this calendar can read shared confirmed events. Private events are not exported. Disabling publication does not remove previously recorded HA history.",
    confirm_public_checkbox: "I understand that confirmed family events will be visible to all Home Assistant users",
    creator: "Creator",
    fold_prompt: "This local time occurs twice due to daylight saving fold. Choose one:",
    fold_first: "First occurrence",
    fold_second: "Second occurrence",
    invalid_local_time: "This local date and time does not exist or is invalid in this time zone. Choose another time.",
    child_notice: "Events created by children are tentative until approved by a parent.",
    conflict_error: "Conflict: event was modified elsewhere. Form closed.",
  },
  ru: {
    history: "История", created: "Создано", updated: "Изменено", export_on: "Включено", export_off: "Выключено",
    title: "Семейный календарь",
    agenda_title: "Ближайшие события (30 дней)",
    events_title: "Все события",
    no_occurrences: "Нет запланированных событий.",
    no_events: "Событий в календаре нет.",
    new_event: "Новое событие",
    edit: "Изменить",
    cancel: "Отмена",
    save: "Сохранить",
    retry: "Повторить",
    approve: "Одобрить",
    cancel_event: "Отменить событие",
    archive: "В архив",
    event_title: "Название",
    description: "Описание",
    location: "Место",
    all_day: "Весь день",
    start_date: "Дата начала",
    end_date: "Дата окончания (не включая)",
    start_time: "Начало (дата и время)",
    end_time: "Окончание (дата и время)",
    timezone: "Часовой пояс",
    participants: "Участники",
    escort: "Сопровождающий (взрослый)",
    none: "Нет",
    visibility: "Видимость",
    visibility_family: "Вся семья",
    visibility_participants: "Только участники",
    preparation: "Подготовка (по пункту на строку)",
    reminders: "Напоминания до события (минуты через запятую 0..10080, не более 6)",
    reason: "Причина",
    status_tentative: "Предварительно (требует подтверждения родителей)",
    status_confirmed: "Подтверждено",
    status_cancelled: "Отменено",
    status_archived: "В архиве",
    unknown_member: "Неизвестный участник",
    reason_required: "Укажите причину.",
    title_required: "Укажите название.",
    start_end_order: "Время окончания должно быть позже времени начала.",
    export_title: "Экспорт в Home Assistant",
    publish_to_ha: "Публиковать подтверждённые семейные события в календарь Home Assistant",
    confirm_public_title: "Подтверждение публичной видимости",
    confirm_public_notice: "Пользователи HA с доступом к календарю увидят общие подтверждённые события. Личные события не экспортируются. Отключение публикации не удаляет уже записанную историю HA.",
    confirm_public_checkbox: "Я понимаю, что подтверждённые семейные события будут видны всем пользователям Home Assistant",
    creator: "Создатель",
    fold_prompt: "Это время повторяется дважды из-за перевода часов. Выберите вариант:",
    fold_first: "Первое вхождение",
    fold_second: "Второе вхождение",
    invalid_local_time: "Такого местного времени нет в этом часовом поясе. Выберите другое время.",
    child_notice: "События, созданные детьми, остаются предварительными до одобрения родителями.",
    conflict_error: "Конфликт: событие было изменено в другом месте. Форма закрыта.",
  },
  uk: {
    history: "Історія", created: "Створено", updated: "Змінено", export_on: "Увімкнено", export_off: "Вимкнено",
    title: "Сімейний календар",
    agenda_title: "Найближчі події (30 днів)",
    events_title: "Усі події",
    no_occurrences: "Немає запланованих подій.",
    no_events: "Подій у календарі немає.",
    new_event: "Нова подія",
    edit: "Редагувати",
    cancel: "Скасувати",
    save: "Зберегти",
    retry: "Повторити",
    approve: "Схвалити",
    cancel_event: "Скасувати подію",
    archive: "До архіву",
    event_title: "Назва",
    description: "Опис",
    location: "Місце",
    all_day: "Цілий день",
    start_date: "Дата початку",
    end_date: "Дата завершення (не враховуючи)",
    start_time: "Початок (дата і час)",
    end_time: "Завершення (дата і час)",
    timezone: "Часовий пояс",
    participants: "Учасники",
    escort: "Супроводжуючий (дорослий)",
    none: "Немає",
    visibility: "Видимість",
    visibility_family: "Уся родина",
    visibility_participants: "Лише учасники",
    preparation: "Підготовка (по пункту на рядок)",
    reminders: "Нагадування до події (хвилини через кому 0..10080, максимум 6)",
    reason: "Причина",
    status_tentative: "Попередньо (потребує схвалення батьків)",
    status_confirmed: "Підтверджено",
    status_cancelled: "Скасовано",
    status_archived: "В архіві",
    unknown_member: "Невідомий учасник",
    reason_required: "Вкажіть причину.",
    title_required: "Вкажіть назву.",
    start_end_order: "Час завершення має бути пізнішим за час початку.",
    export_title: "Експорт до Home Assistant",
    publish_to_ha: "Публікувати підтверджені сімейні події у календар Home Assistant",
    confirm_public_title: "Підтвердження публічної видимості",
    confirm_public_notice: "Користувачі HA з доступом до календаря бачитимуть спільні підтверджені події. Приватні події не експортуються. Вимкнення публікації не видаляє вже записану історію HA.",
    confirm_public_checkbox: "Я розумію, що підтверджені сімейні події будуть доступні всім користувачам Home Assistant",
    creator: "Творець",
    fold_prompt: "Цей час трапляється двічі через переведення годинника. Виберіть варіант:",
    fold_first: "Перше входження",
    fold_second: "Друге входження",
    invalid_local_time: "Такого місцевого часу немає в цьому часовому поясі. Виберіть інший час.",
    child_notice: "Події, створені дітьми, залишаються попередніми до схвалення батьками.",
    conflict_error: "Конфлікт: подію було змінено в іншому місці. Форму закрито.",
  }
};

function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = String(text);
  if (className) node.className = className;
  return node;
}

function getCopy(card) {
  const lang = card._config?.language || card._hass?.language?.split("-")[0] || "en";
  return CALENDAR_COPY[lang] || CALENDAR_COPY.en;
}

function getHouseholdZone(card) {
  return card._data?.settings?.timezone || card._hass?.config?.time_zone || "UTC";
}

function getMemberName(card, id) {
  if (!id) return "";
  const found = (card._data?.members || []).find(m => m && m.id === id);
  return found?.name || getCopy(card).unknown_member;
}

function formatDateInZone(card, isoStr, zone) {
  if (!isoStr) return "";
  const lang = card._config?.language || card._hass?.language || "en";
  try {
    return new Date(isoStr).toLocaleString(lang, { timeZone: zone || "UTC" });
  } catch {
    return isoStr;
  }
}

export function renderCalendar(card, body) {
  if (!card || !body || !card._data) return;
  const role = card._data.role;
  if (!["owner", "parent", "adult", "child"].includes(role) || !card._data.actor) return;
  if (!card._data.settings?.modules?.includes("calendar")) return;

  const copy = getCopy(card);
  const data = card._data;
  const isParent = Boolean(card.parent) && ["owner", "parent"].includes(role);
  const isOwner = role === "owner";
  const actorId = data.actor;
  const defaultZone = getHouseholdZone(card);
  const startGen = card._generation;
  const startEntry = card._entry;
  const scope = JSON.stringify([startGen, startEntry, role, actorId, defaultZone]);
  if (card._calendarDraft) {
    if (card._calendarDraft.scope && card._calendarDraft.scope !== scope) {
      card._calendarDraft = null;
      card._actionError = "conflict";
    } else card._calendarDraft.scope = scope;
  }

  const calendarData = data.calendar || {};
  const events = calendarData.events || [];
  const occurrences = calendarData.occurrences || [];
  const config = calendarData.config || { publish_to_ha: false, revision: 0 };

  const isStale = () =>
    card._generation !== startGen ||
    card._entry !== startEntry ||
    card._data?.role !== role ||
    card._data?.actor !== actorId ||
    getHouseholdZone(card) !== defaultZone ||
    !card._data?.settings?.modules?.includes("calendar");

  const runCmd = async (action, payload) => {
    if (isStale() || card._writing) return;
    const draft = card._calendarDraft;
    try {
      await card.command(action, payload);
      if (!isStale() && card._calendarDraft === draft) {
        if (!card._actionError) {
          card._calendarDraft = null;
        }
        card.render();
      }
    } catch {
      if (!isStale() && card._calendarDraft === draft) {
        card._actionError ||= "not_ready";
        card.render();
      }
    }
  };

  // 1. Owner publish-to-HA configuration
  if (isOwner) {
    const pubSection = el("section", null, "item");
    pubSection.append(el("strong", copy.export_title));
    const pubStatus = el(
      "div",
      `${copy.publish_to_ha}: ${config.publish_to_ha ? copy.export_on : copy.export_off}`,
      "sub"
    );
    pubSection.append(pubStatus);

    const isPubDraft = card._calendarDraft?.type === "publish_config";
    const pubBtn = card.button(isPubDraft ? copy.cancel : copy.edit, () => {
      if (isStale() || card._writing) return;
      card._actionError = null;
      if (isPubDraft) {
        card._calendarDraft = null;
      } else {
        card._calendarDraft = {
          type: "publish_config",
          publish_to_ha: !config.publish_to_ha,
          confirm_public_visibility: false,
          revision: config.revision,
        };
      }
      card.render();
    });
    pubSection.append(pubBtn);

    if (isPubDraft) {
      const d = card._calendarDraft;
      const isFrozen = Boolean(d.frozenPayload);
      const pubForm = el("form", null, "editor");

      const toggleLabel = el("label", copy.publish_to_ha, "check");
      const toggleBox = el("input");
      toggleBox.type = "checkbox";
      toggleBox.name = "publish_to_ha";
      toggleBox.checked = Boolean(d.publish_to_ha);
      toggleBox.disabled = isFrozen || Boolean(card._writing);
      toggleLabel.prepend(toggleBox);
      pubForm.append(toggleLabel);

      const warnBox = el("div", null, "notice");
      warnBox.append(el("strong", copy.confirm_public_title));
      warnBox.append(el("p", copy.confirm_public_notice, "sub"));
      const confirmLabel = el("label", copy.confirm_public_checkbox, "check");
      const confirmInput = el("input");
      confirmInput.type = "checkbox";
      confirmInput.name = "confirm_public_visibility";
      confirmInput.checked = Boolean(d.confirm_public_visibility);
      confirmInput.disabled = isFrozen || Boolean(card._writing);
      confirmLabel.prepend(confirmInput);
      warnBox.append(confirmLabel);
      pubForm.append(warnBox);

      const warnDisplay = () => {
        warnBox.style.display = toggleBox.checked && !config.publish_to_ha ? "block" : "none";
      };
      warnDisplay();

      toggleBox.addEventListener("change", () => {
        d.publish_to_ha = toggleBox.checked;
        warnDisplay();
      });
      confirmInput.addEventListener("change", () => {
        d.confirm_public_visibility = confirmInput.checked;
      });

      const actions = el("div", null, "actions");
      const saveBtn = card.button(
        card._actionError && isFrozen ? copy.retry : copy.save,
        () => {},
        true
      );
      saveBtn.type = "submit";
      actions.append(saveBtn);
      actions.append(
        card.button(copy.cancel, () => {
          card._calendarDraft = null;
          card._actionError = null;
          card.render();
        })
      );
      pubForm.append(actions);

      pubForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        if (isStale() || card._writing || card._calendarDraft !== d) return;

        // Fresh check
        const freshConfig = card._data?.calendar?.config || { publish_to_ha: false, revision: 0 };
        if (freshConfig.revision !== d.revision) {
          card._actionError = "conflict";
          card._calendarDraft = null;
          card.render();
          return;
        }

        let payload = d.frozenPayload;
        if (!payload) {
          payload = {
            publish_to_ha: Boolean(toggleBox.checked),
            revision: freshConfig.revision,
          };
          if (payload.publish_to_ha && !freshConfig.publish_to_ha) {
            if (!confirmInput.checked) {
              card._actionError = "confirmation_required";
              card.render();
              return;
            }
            payload.confirm_public_visibility = Boolean(confirmInput.checked);
          }
          d.frozenPayload = payload;
        }
        await runCmd("calendar.configure", payload);
      });

      pubSection.append(pubForm);
    }
    body.append(pubSection);
  }

  // 2. Event creation / edit toolbar
  const isFormOpen =
    card._calendarDraft?.type === "create" || card._calendarDraft?.type === "edit";
  const toolbar = el("div", null, "toolbar");
  toolbar.append(
    card.button(
      isFormOpen ? copy.cancel : copy.new_event,
      () => {
        if (isStale() || card._writing) return;
        card._actionError = null;
        if (isFormOpen) {
          card._calendarDraft = null;
        } else {
          const now = new Date();
          const today = wallTime(now.toISOString(), defaultZone).slice(0, 10);
          const tomorrow = new Date(today + "T12:00:00Z");
          tomorrow.setUTCDate(tomorrow.getUTCDate() + 1);
          card._calendarDraft = {
            type: "create",
            title: "",
            description: "",
            location: "",
            all_day: false,
            start: "",
            end: "",
            start_date: today,
            end_date: tomorrow.toISOString().slice(0, 10),
            start_time: "10:00",
            end_time: "11:00",
            start_local: "",
            end_local: "",
            start_fold: "",
            end_fold: "",
            timezone: defaultZone,
            participants: [actorId],
            escort: null,
            preparation: [],
            reminder_minutes: [],
            visibility: "family",
          };
        }
        card.render();
      },
      !isFormOpen
    )
  );
  body.append(toolbar);

  // 3. Event Create / Edit Form
  if (isFormOpen) {
    const d = card._calendarDraft;
    const isEdit = d.type === "edit";
    const isFrozen = Boolean(d.frozenPayload);
    const form = el("form", null, "editor");

    if (role === "child") {
      form.append(el("div", copy.child_notice, "notice"));
    }

    const titleInput = card.input(form, "title", copy.event_title, "text", d.title || "", true);
    titleInput.maxLength = 255;
    const descInput = card.input(
      form,
      "description",
      copy.description,
      "text",
      d.description || "",
      false
    );
    descInput.maxLength = 2000;
    const locInput = card.input(form, "location", copy.location, "text", d.location || "", false);
    locInput.maxLength = 500;

    const tzInput = card.input(
      form,
      "timezone",
      copy.timezone,
      "text",
      d.timezone || defaultZone,
      true
    );

    // All Day checkbox
    const allDayLabel = el("label", copy.all_day, "check");
    const allDayBox = el("input");
    allDayBox.type = "checkbox";
    allDayBox.name = "all_day";
    allDayBox.checked = Boolean(d.all_day);
    allDayLabel.prepend(allDayBox);
    form.append(allDayLabel);

    // Timed inputs container
    const timedContainer = el("div");
    const sTimeLabel = el("label", copy.start_time);
    const sTimeInput = el("input");
    sTimeInput.type = "datetime-local";
    sTimeInput.name = "start_time";
    sTimeInput.value = d.start_local || "";
    sTimeLabel.append(sTimeInput);
    timedContainer.append(sTimeLabel);

    // Start fold selector
    const sFoldWrap = el("label", copy.fold_prompt);
    sFoldWrap.style.display = "none";
    const sFoldSelect = el("select");
    sFoldSelect.name = "start_fold";
    sFoldSelect.append(new Option(copy.none, ""));
    sFoldSelect.append(new Option(copy.fold_first, "0"));
    sFoldSelect.append(new Option(copy.fold_second, "1"));
    sFoldSelect.value = d.start_fold || "";
    sFoldWrap.append(sFoldSelect);
    timedContainer.append(sFoldWrap);

    const eTimeLabel = el("label", copy.end_time);
    const eTimeInput = el("input");
    eTimeInput.type = "datetime-local";
    eTimeInput.name = "end_time";
    eTimeInput.value = d.end_local || "";
    eTimeLabel.append(eTimeInput);
    timedContainer.append(eTimeLabel);

    // End fold selector
    const eFoldWrap = el("label", copy.fold_prompt);
    eFoldWrap.style.display = "none";
    const eFoldSelect = el("select");
    eFoldSelect.name = "end_fold";
    eFoldSelect.append(new Option(copy.none, ""));
    eFoldSelect.append(new Option(copy.fold_first, "0"));
    eFoldSelect.append(new Option(copy.fold_second, "1"));
    eFoldSelect.value = d.end_fold || "";
    eFoldWrap.append(eFoldSelect);
    timedContainer.append(eFoldWrap);

    // Date-only inputs container
    const dateContainer = el("div");
    const sDateLabel = el("label", copy.start_date);
    const sDateInput = el("input");
    sDateInput.type = "date";
    sDateInput.name = "start_date";
    sDateInput.value = d.start_date || "";
    sDateLabel.append(sDateInput);
    dateContainer.append(sDateLabel);

    const eDateLabel = el("label", copy.end_date);
    const eDateInput = el("input");
    eDateInput.type = "date";
    eDateInput.name = "end_date";
    eDateInput.value = d.end_date || "";
    eDateLabel.append(eDateInput);
    dateContainer.append(eDateLabel);

    form.append(timedContainer);
    form.append(dateContainer);

    const toggleAllDayView = (isAllDay) => {
      timedContainer.style.display = isAllDay ? "none" : "block";
      dateContainer.style.display = isAllDay ? "block" : "none";
    };
    toggleAllDayView(d.all_day);

    allDayBox.addEventListener("change", () => {
      d.all_day = allDayBox.checked;
      toggleAllDayView(d.all_day);
    });

    const updateFolds = () => {
      if (allDayBox.checked) return;
      const curTz = tzInput.value.trim() || defaultZone;
      try {
        if (sTimeInput.value) {
          const sCands = wallTimeCandidates(sTimeInput.value, curTz);
          sFoldWrap.style.display = sCands.length > 1 ? "block" : "none";
        }
      } catch {}
      try {
        if (eTimeInput.value) {
          const eCands = wallTimeCandidates(eTimeInput.value, curTz);
          eFoldWrap.style.display = eCands.length > 1 ? "block" : "none";
        }
      } catch {}
    };
    sTimeInput.addEventListener("input", updateFolds);
    eTimeInput.addEventListener("input", updateFolds);
    tzInput.addEventListener("input", updateFolds);
    updateFolds();

    // Participants checkboxes
    const partFs = el("fieldset");
    partFs.append(el("legend", copy.participants));
    const activeMembers = (card._data.members || []).filter(
      (m) => m && m.active && m.role !== "guest"
    );
    const partBoxes = [];
    for (const m of activeMembers) {
      const ml = el("label", m.name, "check");
      const cb = el("input");
      cb.type = "checkbox";
      cb.name = "participants";
      cb.value = m.id;
      cb.checked = Array.isArray(d.participants) && d.participants.includes(m.id);
      // Child or non-privileged can only select themselves
      if (!isParent && m.id !== actorId) {
        cb.disabled = true;
      }
      ml.prepend(cb);
      partFs.append(ml);
      partBoxes.push(cb);
    }
    form.append(partFs);

    // Escort selector
    const escortLabel = el("label", copy.escort);
    const escortSelect = el("select");
    escortSelect.name = "escort";
    escortSelect.append(new Option(copy.none, ""));
    const adultMembers = (card._data.members || []).filter(
      (m) => m && m.active && ["owner", "parent", "adult"].includes(m.role)
    );
    for (const m of adultMembers) {
      const opt = new Option(m.name, m.id);
      if (d.escort === m.id) opt.selected = true;
      escortSelect.append(opt);
    }
    escortLabel.append(escortSelect);
    form.append(escortLabel);

    // Preparation textarea
    const prepLabel = el("label", copy.preparation);
    const prepText = el("textarea");
    prepText.name = "preparation";
    prepText.rows = 3;
    prepText.value = Array.isArray(d.preparation) ? d.preparation.join("\n") : d.preparation || "";
    prepLabel.append(prepText);
    form.append(prepLabel);

    // Reminders input
    const remInput = card.input(
      form,
      "reminders",
      copy.reminders,
      "text",
      Array.isArray(d.reminder_minutes)
        ? d.reminder_minutes.join(", ")
        : d.reminder_minutes || "",
      false
    );

    // Visibility selector
    const visLabel = el("label", copy.visibility);
    const visSelect = el("select");
    visSelect.name = "visibility";
    visSelect.append(new Option(copy.visibility_family, "family"));
    visSelect.append(new Option(copy.visibility_participants, "participants"));
    visSelect.value = d.visibility || "family";
    visLabel.append(visSelect);
    form.append(visLabel);

    const errBox = el("div", null, "notice");
    errBox.style.display = "none";
    form.append(errBox);

    const actions = el("div", null, "actions");
    const submitBtn = card.button(
      card._actionError && isFrozen ? copy.retry : copy.save,
      () => {},
      true
    );
    submitBtn.type = "submit";
    actions.append(submitBtn);
    actions.append(
      card.button(copy.cancel, () => {
        card._calendarDraft = null;
        card._actionError = null;
        card.render();
      })
    );
    form.append(actions);

    // Disable elements if frozen or writing
    for (const input of form.querySelectorAll("input, select, textarea")) {
      if (isFrozen || Boolean(card._writing)) input.disabled = true;
    }
    submitBtn.disabled = Boolean(card._writing);

    // Sync draft on inputs
    const syncDraft = () => {
      if (isFrozen || isStale() || card._writing || card._calendarDraft !== d) return;
      d.title = titleInput.value;
      d.description = descInput.value;
      d.location = locInput.value;
      d.timezone = tzInput.value;
      d.all_day = allDayBox.checked;
      d.start_local = sTimeInput.value;
      d.end_local = eTimeInput.value;
      d.start_date = sDateInput.value;
      d.end_date = eDateInput.value;
      d.start_fold = sFoldSelect.value;
      d.end_fold = eFoldSelect.value;
      d.participants = partBoxes.filter((cb) => cb.checked).map((cb) => cb.value);
      d.escort = escortSelect.value || null;
      d.preparation = prepText.value
        .split(/\r?\n/)
        .map((s) => s.trim())
        .filter(Boolean);
      d.visibility = visSelect.value;
      d.reminder_minutes = remInput.value;
    };
    form.addEventListener("input", syncDraft);
    form.addEventListener("change", syncDraft);

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (isStale() || card._writing || card._calendarDraft !== d) return;
      if (isEdit) {
        const fresh = card._data?.calendar?.events?.find(r => r.id === d.id);
        if (!fresh || fresh.revision !== d.revision) {
          card._actionError = "conflict";
          card._calendarDraft = null;
          card.render();
          return;
        }
      }

      if (!d.frozenPayload) {
        syncDraft();
        const tVal = titleInput.value.trim();
        if (!tVal) {
          errBox.textContent = copy.title_required;
          errBox.style.display = "block";
          return;
        }

        const curTz = tzInput.value.trim() || defaultZone;
        let startVal = "";
        let endVal = "";

        if (allDayBox.checked) {
          startVal = sDateInput.value;
          endVal = eDateInput.value;
          if (!startVal || !endVal || endVal <= startVal) {
            errBox.textContent = copy.start_end_order;
            errBox.style.display = "block";
            return;
          }
        } else {
          // Timed
          try {
            const sCands = wallTimeCandidates(sTimeInput.value, curTz);
            if (sCands.length === 0) {
              errBox.textContent = copy.invalid_local_time;
              errBox.style.display = "block";
              return;
            }
            const choose = (input, candidates, choice, original) => {
              if (isEdit && original && d.original_timezone === curTz && choice.value === "" &&
                  wallTime(original, curTz) === input.value) return original;
              if (candidates.length === 1) return candidates[0];
              if (!["0", "1"].includes(choice.value)) throw new Error("fold");
              return candidates[Number(choice.value)];
            };
            startVal = choose(sTimeInput, sCands, sFoldSelect, d.start);

            const eCands = wallTimeCandidates(eTimeInput.value, curTz);
            if (eCands.length === 0) {
              errBox.textContent = copy.invalid_local_time;
              errBox.style.display = "block";
              return;
            }
            endVal = choose(eTimeInput, eCands, eFoldSelect, d.end);

            if (new Date(endVal) <= new Date(startVal)) {
              errBox.textContent = copy.start_end_order;
              errBox.style.display = "block";
              return;
            }
          } catch (err) {
            errBox.textContent = err.message === "fold" ? copy.fold_prompt : copy.invalid_local_time;
            errBox.style.display = "block";
            return;
          }
        }

        // Reminders parse
        const remParts = remInput.value.trim() ? remInput.value.split(",").map(s => s.trim()) : [];
        const rems = remParts.map(Number);
        if (remParts.some(s => !/^\d+$/.test(s)) || rems.some(n => !Number.isInteger(n) || n > 10080) ||
            rems.length > 6 || new Set(rems).size !== rems.length) {
          errBox.textContent = copy.reminders;
          errBox.style.display = "block";
          return;
        }

        const checkedParts = partBoxes.filter((cb) => cb.checked).map((cb) => cb.value);
        const currentMembers = card._data?.members || [];
        if (!checkedParts.length || checkedParts.some(id => !currentMembers.some(m => m.id === id && m.active && m.role !== "guest")) ||
            (!isParent && (checkedParts.length !== 1 || checkedParts[0] !== actorId))) {
          errBox.textContent = copy.participants;
          errBox.style.display = "block";
          return;
        }
        const preparation = prepText.value.split(/\r?\n/).map(s => s.trim()).filter(Boolean);
        if (preparation.length > 30 || preparation.some(s => s.length > 200)) {
          errBox.textContent = copy.preparation;
          errBox.style.display = "block";
          return;
        }

        const payload = {
          title: tVal,
          description: descInput.value.trim(),
          location: locInput.value.trim(),
          all_day: Boolean(allDayBox.checked),
          start: startVal,
          end: endVal,
          timezone: curTz,
          participants: checkedParts,
          escort: escortSelect.value || null,
          preparation,
          reminder_minutes: rems,
          visibility: visSelect.value,
        };

        if (isEdit) {
          payload.id = d.id;
          payload.revision = d.revision;
        }
        d.frozenPayload = payload;
      }

      // Check fresh revision before executing
      if (isEdit) {
        const freshRec = (card._data?.calendar?.events || []).find((ev) => ev.id === d.id);
        if (!freshRec || freshRec.revision !== d.revision) {
          card._actionError = "conflict";
          card._calendarDraft = null;
          card.render();
          return;
        }
      }

      await runCmd("calendar.save", d.frozenPayload);
    });

    body.append(form);
  }

  // 4. Action reason form (Approve, Cancel, Archive)
  const isActionDraft =
    card._calendarDraft?.type === "approve" ||
    card._calendarDraft?.type === "cancel" ||
    card._calendarDraft?.type === "archive";

  if (isActionDraft) {
    const d = card._calendarDraft;
    const isFrozen = Boolean(d.frozenPayload);
    const aForm = el("form", null, "editor");
    const promptTitle =
      d.type === "approve"
        ? copy.approve
        : d.type === "cancel"
        ? copy.cancel_event
        : copy.archive;
    aForm.append(el("strong", promptTitle));

    const reasonInput = card.input(aForm, "reason", copy.reason, "text", d.reason || "", true);
    reasonInput.maxLength = 500;
    reasonInput.disabled = isFrozen || Boolean(card._writing);

    const actions = el("div", null, "actions");
    const submitBtn = card.button(
      card._actionError && isFrozen ? copy.retry : copy.save,
      () => {},
      true
    );
    submitBtn.type = "submit";
    actions.append(submitBtn);
    actions.append(
      card.button(copy.cancel, () => {
        card._calendarDraft = null;
        card._actionError = null;
        card.render();
      })
    );
    aForm.append(actions);

    reasonInput.addEventListener("input", () => {
      if (!isFrozen) d.reason = reasonInput.value;
    });

    aForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (isStale() || card._writing || card._calendarDraft !== d) return;

      const reasonVal = reasonInput.value.trim();
      if (!reasonVal) return;

      // Check fresh revision
      const freshRec = (card._data?.calendar?.events || []).find((ev) => ev.id === d.id);
      if (!freshRec || freshRec.revision !== d.revision) {
        card._actionError = "conflict";
        card._calendarDraft = null;
        card.render();
        return;
      }

      let payload = d.frozenPayload;
      if (!payload) {
        payload = {
          id: d.id,
          revision: d.revision,
          reason: reasonVal,
        };
        d.frozenPayload = payload;
      }
      await runCmd(`calendar.${d.type}`, payload);
    });

    body.append(aForm);
  }

  // 5. Agenda (Occurrences in next 30 days)
  const agendaSec = el("section", null, "item");
  agendaSec.dataset.calendarAgenda = "true";
  agendaSec.append(el("strong", copy.agenda_title));
  if (!occurrences.length) {
    agendaSec.append(el("div", copy.no_occurrences, "empty"));
  } else {
    const ul = el("ul", null, "list");
    for (const occ of occurrences) {
      const li = el("li", null, "item");
      li.append(el("strong", occ.title));
      const timeStr = occ.all_day
        ? `${occ.start} → ${occ.end} (${copy.all_day})`
        : `${formatDateInZone(card, occ.start, occ.timezone)} — ${formatDateInZone(
            card,
            occ.end,
            occ.timezone
          )} (${occ.timezone})`;
      li.append(el("div", timeStr, "sub"));
      if (occ.location) {
        li.append(el("div", `${copy.location}: ${occ.location}`, "sub"));
      }
      ul.append(li);
    }
    agendaSec.append(ul);
  }
  body.append(agendaSec);

  // 6. Events List with edit/approve/cancel/archive controls
  const evSec = el("section", null, "item");
  evSec.dataset.calendarEvents = "true";
  evSec.append(el("strong", copy.events_title));
  if (!events.length) {
    evSec.append(el("div", copy.no_events, "empty"));
  } else {
    const ul = el("ul", null, "list");
    for (const ev of events) {
      const li = el("li", null, "item");
      li.dataset.calendarEvent = ev.id;
      li.append(el("strong", ev.title));

      const statusBadge = el(
        "span",
        copy[`status_${ev.archived ? "archived" : ev.status}`] || ev.status,
        "badge"
      );
      li.append(statusBadge);

      const creatorName = getMemberName(card, ev.creator);
      let subInfo = `${copy.creator}: ${creatorName}`;
      if (ev.location) subInfo += ` · ${copy.location}: ${ev.location}`;
      li.append(el("div", subInfo, "sub"));

      const timeStr = ev.all_day
        ? `${ev.start} → ${ev.end} (${copy.all_day})`
        : `${formatDateInZone(card, ev.start, ev.timezone)} — ${formatDateInZone(
            card,
            ev.end,
            ev.timezone
          )} (${ev.timezone})`;
      li.append(el("div", timeStr, "sub"));

      const actionsDiv = el("div", null, "actions");
      const canEdit = isParent || ev.creator === actorId;

      if (canEdit && !ev.archived && ev.status !== "cancelled") {
        actionsDiv.append(
          card.button(copy.edit, () => {
            if (isStale() || card._writing) return;
            card._calendarDraft = {
              type: "edit",
              id: ev.id,
              revision: ev.revision,
              title: ev.title,
              description: ev.description || "",
              location: ev.location || "",
              all_day: Boolean(ev.all_day),
              start: ev.start,
              end: ev.end,
              start_date: ev.all_day ? ev.start : "",
              end_date: ev.all_day ? ev.end : "",
              start_local: !ev.all_day ? wallTime(ev.start, ev.timezone || defaultZone) : "",
              end_local: !ev.all_day ? wallTime(ev.end, ev.timezone || defaultZone) : "",
              start_fold: "",
              end_fold: "",
              timezone: ev.timezone || defaultZone,
              original_timezone: ev.timezone || defaultZone,
              participants: [...(ev.participants || [])],
              escort: ev.escort || null,
              preparation: [...(ev.preparation || [])],
              reminder_minutes: [...(ev.reminder_minutes || [])],
              visibility: ev.visibility || "family",
            };
            card.render();
          })
        );
      }

      if (isParent && ev.status === "tentative" && !ev.archived) {
        actionsDiv.append(
          card.button(
            copy.approve,
            () => {
              if (isStale() || card._writing) return;
              card._calendarDraft = {
                type: "approve",
                id: ev.id,
                revision: ev.revision,
                reason: "",
              };
              card.render();
            },
            true
          )
        );
      }

      if (canEdit && !ev.archived && ev.status !== "cancelled") {
        actionsDiv.append(
          card.button(copy.cancel_event, () => {
            if (isStale() || card._writing) return;
            card._calendarDraft = {
              type: "cancel",
              id: ev.id,
              revision: ev.revision,
              reason: "",
            };
            card.render();
          })
        );
      }

      if (canEdit && !ev.archived) {
        actionsDiv.append(
          card.button(copy.archive, () => {
            if (isStale() || card._writing) return;
            card._calendarDraft = {
              type: "archive",
              id: ev.id,
              revision: ev.revision,
              reason: "",
            };
            card.render();
          })
        );
      }

      if (actionsDiv.children.length > 0) {
        li.append(actionsDiv);
      }
      if (ev.history?.length) {
        const history = el("details");
        history.append(el("summary", copy.history));
        for (const entry of ev.history) history.append(el("div",
          `${formatDateInZone(card, entry.at, defaultZone)} · ${getMemberName(card, entry.actor)} · ${copy[entry.action] || entry.action}${entry.reason ? ' · ' + entry.reason : ''}`, "sub"));
        li.append(history);
      }
      ul.append(li);
    }
    evSec.append(ul);
  }
  body.append(evSec);
}
