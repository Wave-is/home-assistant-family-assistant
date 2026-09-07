/* Task item and archive rendering and copy for Family Assistant card. */

import { wallTime, wallTimeCandidates } from "./local-time.js";
import { renderTaskMedia } from "./task-media-view.js";
import { personalTaskCopy } from "./personal-task-copy.js";
import { renderReportHistory } from "./task-report-history.js";

export const TASK_ITEM_COPY = {
  en: {
    status_assigned: "Assigned",
    status_accepted: "Accepted",
    status_in_progress: "In progress",
    status_submitted: "In review",
    status_needs_changes: "Needs changes",
    status_completed: "Completed",
    status_cancelled: "Cancelled",
    status_archived: "Archived",
    status_unknown: "Unknown status",
    action_accept: "Accept",
    action_start: "Start",
    action_submit_report: "Send report",
    action_edit: "Edit task",
    school_managed: "Change this homework's title and deadline in the School card.",
    action_cancel: "Cancel task",
    action_complete: "Confirm done",
    action_request_changes: "Request changes",
    action_archive: "Archive",
    action_confirm_archive: "Confirm archive",
    action_confirm_cancel: "Confirm cancellation",
    action_save: "Save",
    action_cancel_edit: "Cancel",
    action_retry: "Retry",
    label_title: "Title",
    label_assignee: "Assignee",
    label_creator: "Created by",
    label_due: "Deadline",
    label_due_fold: "Daylight saving time choice",
    label_due_fold_select: "Choose time instant",
    label_due_fold_standard: "First occurrence / earlier instant",
    label_due_fold_daylight: "Second occurrence / later instant",
    label_report: "Report",
    label_review_note: "Review note",
    label_checklist: "Checklist",
    label_deadline_policy: "Deadline policy",
    label_reminder_minutes: "Reminder before deadline (minutes, 0 disables)",
    label_grace_minutes: "Grace after deadline (minutes)",
    label_penalty: "Missed task points (0 disables)",
    archive_title: "Archived & Completed Tasks",
    archive_empty: "No archived tasks",
    unknown_member: "Unknown member",
    error_dst_gap: "This time does not exist due to daylight saving time clock change. Choose another time.",
    error_dst_ambiguous: "This time occurs twice due to daylight saving time. Please select which instant you mean.",
    error_note_required: "Review note is required.",
    error_report_required: "Report text is required.",
    error_stale_state: "Task was updated or permissions changed. Please refresh and try again.",
    warning_archive: "Archiving permanently files this task in history.",
    warning_cancel: "Cancelling will terminate this task."
  },
  ru: {
    status_assigned: "Назначена",
    status_accepted: "Принята",
    status_in_progress: "В работе",
    status_submitted: "На проверке",
    status_needs_changes: "На доработке",
    status_completed: "Выполнена",
    status_cancelled: "Отменена",
    status_archived: "В архиве",
    status_unknown: "Неизвестный статус",
    action_accept: "Принять",
    action_start: "Начать",
    action_submit_report: "Сдать отчёт",
    action_edit: "Изменить задачу",
    school_managed: "Название и срок домашнего задания меняются в карточке «Школа».",
    action_cancel: "Отменить задачу",
    action_complete: "Подтвердить выполнение",
    action_request_changes: "Вернуть на доработку",
    action_archive: "В архив",
    action_confirm_archive: "Подтвердить архивацию",
    action_confirm_cancel: "Подтвердить отмену",
    action_save: "Сохранить",
    action_cancel_edit: "Отмена",
    action_retry: "Повторить",
    label_title: "Что нужно сделать?",
    label_assignee: "Кому?",
    label_creator: "Создал(а)",
    label_due: "Срок",
    label_due_fold: "Выбор времени при переводе часов",
    label_due_fold_select: "Выберите момент времени",
    label_due_fold_standard: "Первое вхождение / раньше",
    label_due_fold_daylight: "Второе вхождение / позже",
    label_report: "Отчёт",
    label_review_note: "Замечания к отчёту",
    label_checklist: "Чек-лист",
    label_deadline_policy: "Политика срока",
    label_reminder_minutes: "Напомнить до срока (минут, 0 — выключено)",
    label_grace_minutes: "Пауза после срока (минут)",
    label_penalty: "Баллы за пропуск задачи (0 — без штрафа)",
    archive_title: "Архив и завершённые задачи",
    archive_empty: "В архиве пусто",
    unknown_member: "Неизвестный участник",
    error_dst_gap: "Такого времени нет из-за перевода часов. Выберите другое время.",
    error_dst_ambiguous: "Это время повторяется дважды из-за перевода часов. Выберите нужный момент.",
    error_note_required: "Введите замечания к задаче.",
    error_report_required: "Введите текст отчёта.",
    error_stale_state: "Задача изменилась или права были отозваны. Обновите страницу и попробуйте снова.",
    warning_archive: "Задача будет перемещена в архив.",
    warning_cancel: "Задача будет отменена."
  },
  uk: {
    status_assigned: "Призначено",
    status_accepted: "Прийнято",
    status_in_progress: "У роботі",
    status_submitted: "На перевірці",
    status_needs_changes: "На доопрацюванні",
    status_completed: "Виконано",
    status_cancelled: "Скасовано",
    status_archived: "В архіві",
    status_unknown: "Невідомий статус",
    action_accept: "Прийняти",
    action_start: "Почати",
    action_submit_report: "Здати звіт",
    action_edit: "Редагувати завдання",
    school_managed: "Назва й термін домашнього завдання змінюються в картці «Школа».",
    action_cancel: "Скасувати завдання",
    action_complete: "Підтвердити виконання",
    action_request_changes: "Повернути на доопрацювання",
    action_archive: "В архів",
    action_confirm_archive: "Підтвердити архівування",
    action_confirm_cancel: "Підтвердити скасування",
    action_save: "Зберегти",
    action_cancel_edit: "Скасувати",
    action_retry: "Повторити",
    label_title: "Що потрібно зробити?",
    label_assignee: "Кому?",
    label_creator: "Створив(ла)",
    label_due: "Термін",
    label_due_fold: "Вибір часу при переведенні годинника",
    label_due_fold_select: "Оберіть момент часу",
    label_due_fold_standard: "Перше входження / раніше",
    label_due_fold_daylight: "Друге входження / пізніше",
    label_report: "Звіт",
    label_review_note: "Зауваження до звіту",
    label_checklist: "Чек-лист",
    label_deadline_policy: "Політика терміну",
    label_reminder_minutes: "Нагадати до терміну (хвилини, 0 — вимкнено)",
    label_grace_minutes: "Пауза після терміну (хвилини)",
    label_penalty: "Бали за пропуск завдання (0 — без штрафу)",
    archive_title: "Архів і завершені завдання",
    archive_empty: "В архіві порожньо",
    unknown_member: "Невідомий учасник",
    error_dst_gap: "Такого часу немає через переведення годинника. Оберіть інший час.",
    error_dst_ambiguous: "Цей час настає двічі через переведення годинника. Будь ласка, оберіть потрібний момент.",
    error_note_required: "Введіть зауваження до завдання.",
    error_report_required: "Введіть текст звіту.",
    error_stale_state: "Завдання змінилося або права було відкликано. Оновіть сторінку і спробуйте знову.",
    warning_archive: "Завдання буде переміщено в архів.",
    warning_cancel: "Завдання буде скасовано."
  }
};

const FINAL_STATUSES = new Set(["completed", "cancelled", "archived"]);

function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = String(text);
  if (className) node.className = className;
  return node;
}

function getCopy(card) {
  const lang = card._config?.language || card._hass?.language?.split("-")[0] || "en";
  return TASK_ITEM_COPY[lang] || TASK_ITEM_COPY.en;
}

function getMemberName(card, id) {
  if (!id) return "";
  const members = card._data?.members || [];
  const found = members.find(m => m && m.id === id);
  if (found && found.name) return found.name;
  const copy = getCopy(card);
  return copy.unknown_member;
}

function getHouseholdZone(card) {
  return (
    card._data?.settings?.timezone ||
    card._hass?.config?.time_zone ||
    "UTC"
  );
}

function formatHouseholdDate(card, isoDateStr) {
  if (!isoDateStr) return "";
  const zone = getHouseholdZone(card);
  const lang = card._config?.language || card._hass?.language || "en";
  try {
    const d = new Date(isoDateStr);
    return d.toLocaleString(lang, { timeZone: zone });
  } catch {
    return isoDateStr;
  }
}

function baseCanInteract(card, generationAtStart) {
  if (card._writing) return false;
  if (generationAtStart !== undefined && card._generation !== generationAtStart) return false;
  return true;
}

async function executeCardCommand(card, action, payload, generationAtStart) {
  if (!baseCanInteract(card, generationAtStart)) return false;
  try {
    await card.command(action, payload);
    if (card._generation === generationAtStart) {
      if (!card._actionError) {
        card._taskItemAction = null;
        card.render();
      }
    }
    return true;
  } catch {
    return false;
  }
}

export function renderTaskItem(card, list, item) {
  const row = el("li", null, "item");
  if (list && typeof list.append === "function") {
    list.append(row);
  }
  if (!item) return row;

  const copy = getCopy(card);
  const startGeneration = card._generation;
  const isParent = Boolean(card.parent);
  const isGuest = card._data?.role === "guest";
  const actorId = card._data?.actor;
  const isAssignee = item.assignee === actorId;
  const isCreator = item.creator === actorId;
  const isPersonal = item.delivery_scope === "personal";
  const personalOwner = isPersonal && isCreator && isAssignee;
  const isWriting = Boolean(card._writing);
  const isFinal = FINAL_STATUSES.has(item.status);
  const isSubmitted = item.status === "submitted";
  const originalRole = card._data.role, originalZone = getHouseholdZone(card);
  const originalRevision = item.revision, originalStatus = item.status;
  // A view refresh may replace data while keeping the focused form mounted.
  // Consult the new projection, not only the old object captured by a listener.
  const hasCurrentTarget = () => {
    const current = card._data?.tasks?.find(task => task.id === item.id);
    return card._data?.actor === actorId && card._data.role === originalRole &&
      !isGuest && getHouseholdZone(card) === originalZone &&
      card._data.settings.modules?.includes("tasks") && current &&
      current.revision === originalRevision && current.status === originalStatus;
  };
  const canInteract = (target, generation) => baseCanInteract(target, generation) && hasCurrentTarget();

  // Friendly title & status badge
  const titleRow = el("div", null, "row");
  const titleStrong = el("strong", item.title || "", "grow");
  const statusKey = `status_${item.status || "unknown"}`;
  const statusBadge = el("span", copy[statusKey] || copy.status_unknown, "badge");
  titleRow.append(titleStrong, statusBadge);
  row.append(titleRow);
  if (isPersonal) row.append(el("p", personalTaskCopy(card).badge, "sub"));

  // Friendly metadata: Assignee, Creator, Deadline
  const metaParts = [];
  if (item.assignee) {
    metaParts.push(`${copy.label_assignee}: ${getMemberName(card, item.assignee)}`);
  }
  if (item.creator && item.creator !== item.assignee) {
    metaParts.push(`${copy.label_creator}: ${getMemberName(card, item.creator)}`);
  }
  if (item.due_at) {
    metaParts.push(`${copy.label_due}: ${formatHouseholdDate(card, item.due_at)}`);
  }
  const metaSub = el("div", metaParts.join(" · "), "sub");
  row.append(metaSub);
  if (item.managed_by === "school" && isParent && !isFinal) {
    row.append(el("p", copy.school_managed, "sub"));
  }

  // Checklist items: disabled for guests, submitted tasks, final tasks, and non-parent/non-assignee
  if (Array.isArray(item.checklist) && item.checklist.length > 0) {
    const checklistWrap = el("div", null, "item-checklist");
    checklistWrap.append(el("div", copy.label_checklist, "sub"));

    item.checklist.forEach((checkItem, idx) => {
      const label = el("label", null, "check");
      const checkbox = el("input");
      checkbox.type = "checkbox";
      checkbox.checked = Boolean(checkItem.done);
      const checklistDisabled =
        isWriting ||
        isFinal ||
        isSubmitted ||
        isGuest ||
        (!isParent && !isAssignee);
      checkbox.disabled = checklistDisabled;

      checkbox.addEventListener("change", (e) => {
        if (!canInteract(card, startGeneration) || isGuest || isSubmitted || isFinal || (!card.parent && item.assignee !== card._data?.actor)) {
          e.preventDefault();
          return;
        }
        const done = e.target.checked;
        const payload = {
          id: item.id,
          revision: item.revision,
          checklist_index: idx,
          done
        };
        card._taskItemAction = {
          type: "check",
          itemId: item.id,
          targetRevision: item.revision,
          targetStatus: item.status,
          targetAssignee: item.assignee,
          targetCreator: item.creator,
          frozenPayload: payload,
          generation: startGeneration
        };
        executeCardCommand(card, "tasks.check", payload, startGeneration);
      });

      const span = el("span", checkItem.text || "");
      label.append(checkbox, span);
      checklistWrap.append(label);
    });
    row.append(checklistWrap);
  }

  // Submitted report display
  if (item.report) {
    const reportBox = el("div", null, "sub");
    reportBox.append(el("strong", `${copy.label_report}: `), el("span", item.report));
    row.append(reportBox);
  }

  // Review note display (e.g. when needs_changes)
  const mediaSection = renderTaskMedia(card, item);
  if (mediaSection) row.append(mediaSection);
  if (item.review_note) {
    const noteBox = el("div", null, "notice");
    noteBox.append(el("strong", `${copy.label_review_note}: `), el("span", item.review_note));
    row.append(noteBox);
  }
  const reportHistory = renderReportHistory(card, item, hasCurrentTarget);
  if (reportHistory) row.append(reportHistory);

  // Actions Container
  const actionsEl = el("div", null, "actions");
  const actionState = card._taskItemAction;
  const isCurrentAction = actionState && actionState.itemId === item.id;

  // Base permission flags according to actual domain rules:
  // Non-parent creator edit/cancel requires BOTH creator === actor AND assignee === actor (own-assigned).
  const canPerformAssigneeOps = !isGuest && !isFinal && (isAssignee || isParent);
  const canEdit = item.managed_by !== "school" && !isGuest && !isFinal && !isSubmitted && (isParent || (isCreator && isAssignee));
  const canCancel = !isGuest && !isFinal && (isParent || (isCreator && isAssignee));

  // Stale check helper: returns false if rights were revoked or task status/revision changed
  const isActionStateStale = () => {
    if (!actionState || actionState.itemId !== item.id) return false;
    if (actionState.type === "edit" && item.managed_by === "school") return true;
    if (!hasCurrentTarget()) return true;
    if (actionState.targetRevision !== undefined && actionState.targetRevision !== item.revision) {
      return true;
    }
    if (actionState.targetStatus !== undefined && actionState.targetStatus !== item.status) {
      return true;
    }
    // Verify rights haven't been revoked
    if (card._data?.role === "guest") return true;
    if (["complete", "request_changes", "confirm_archive"].includes(actionState.type) && !card.parent && !personalOwner) {
      return true;
    }
    if (["edit", "confirm_cancel"].includes(actionState.type) && !card.parent && (item.creator !== card._data?.actor || item.assignee !== card._data?.actor)) {
      return true;
    }
    if (["accept", "start", "submit_report"].includes(actionState.type) && !card.parent && item.assignee !== card._data?.actor) {
      return true;
    }
    return false;
  };

  // 1. Accept button: status is 'assigned' or 'needs_changes'
  if (canPerformAssigneeOps && (item.status === "assigned" || item.status === "needs_changes")) {
    const acceptBtn = card.button(copy.action_accept, () => {
      if (!canInteract(card, startGeneration)) return;
      const payload = { id: item.id, revision: item.revision };
      card._taskItemAction = {
        type: "accept",
        itemId: item.id,
        targetRevision: item.revision,
        targetStatus: item.status,
        targetAssignee: item.assignee,
        targetCreator: item.creator,
        frozenPayload: payload,
        generation: startGeneration
      };
      executeCardCommand(card, "tasks.accept", payload, startGeneration);
    }, true);
    actionsEl.append(acceptBtn);
  }

  // 2. Start button: status is 'assigned', 'accepted', or 'needs_changes'
  if (canPerformAssigneeOps && (item.status === "assigned" || item.status === "accepted" || item.status === "needs_changes")) {
    const startBtn = card.button(copy.action_start, () => {
      if (!canInteract(card, startGeneration)) return;
      const payload = { id: item.id, revision: item.revision };
      card._taskItemAction = {
        type: "start",
        itemId: item.id,
        targetRevision: item.revision,
        targetStatus: item.status,
        targetAssignee: item.assignee,
        targetCreator: item.creator,
        frozenPayload: payload,
        generation: startGeneration
      };
      executeCardCommand(card, "tasks.start", payload, startGeneration);
    });
    actionsEl.append(startBtn);
  }

  // 3. Submit report button: status !== 'submitted' and not final
  if (canPerformAssigneeOps && !isSubmitted && item.report_type !== "photo" && !isPersonal) {
    const reportBtn = card.button(copy.action_submit_report, () => {
      if (!canInteract(card, startGeneration)) return;
      card._taskItemAction = {
        type: "submit_report",
        itemId: item.id,
        targetRevision: item.revision,
        targetStatus: item.status,
        targetAssignee: item.assignee,
        targetCreator: item.creator,
        reportType: item.report_type || "text",
        draftReport: item.report || "",
        frozenPayload: null,
        generation: startGeneration
      };
      card._actionError = null;
      card.render();
    });
    actionsEl.append(reportBtn);
  }

  // 4. Parent controls: Complete & Request Changes (note)
  if ((isParent || personalOwner) && !isFinal) {
    // Complete
    const completeBtn = card.button(copy.action_complete, () => {
      if (!canInteract(card, startGeneration)) return;
      const payload = { id: item.id, revision: item.revision };
      card._taskItemAction = {
        type: "complete",
        itemId: item.id,
        targetRevision: item.revision,
        targetStatus: item.status,
        targetAssignee: item.assignee,
        targetCreator: item.creator,
        frozenPayload: payload,
        generation: startGeneration
      };
      executeCardCommand(card, "tasks.complete", payload, startGeneration);
    }, isSubmitted);
    actionsEl.append(completeBtn);

    // Request changes: allowed when status is 'submitted'
    if (isSubmitted && !isPersonal) {
      const reqChangesBtn = card.button(copy.action_request_changes, () => {
        if (!canInteract(card, startGeneration)) return;
        card._taskItemAction = {
          type: "request_changes",
          itemId: item.id,
          targetRevision: item.revision,
          targetStatus: item.status,
          targetAssignee: item.assignee,
          targetCreator: item.creator,
          draftNote: "",
          frozenPayload: null,
          generation: startGeneration
        };
        card._actionError = null;
        card.render();
      });
      actionsEl.append(reqChangesBtn);
    }
  }

  // 5. Edit / Revise: Parents or Creator (for own-assigned tasks), when not submitted
  if (canEdit) {
    const editBtn = card.button(copy.action_edit, () => {
      if (!canInteract(card, startGeneration)) return;
      const zone = getHouseholdZone(card);
      let initialWall = "";
      let initialFold = null;
      if (item.due_at) {
        try {
          initialWall = wallTime(item.due_at, zone);
          const candidates = wallTimeCandidates(initialWall, zone);
          if (candidates.length === 2) {
            const idx = candidates.findIndex(candidate => Math.floor(Date.parse(candidate)/60000) === Math.floor(Date.parse(item.due_at)/60000));
            if (idx !== -1) initialFold = idx;
          }
        } catch {
          initialWall = "";
        }
      }
      card._taskItemAction = {
        type: "edit",
        itemId: item.id,
        targetRevision: item.revision,
        targetStatus: item.status,
        targetAssignee: item.assignee,
        targetCreator: item.creator,
        draftTitle: item.title || "",
        draftAssignee: item.assignee || "",
        draftWallTime: initialWall,
        originalDueAt: item.due_at || null,
        originalWallTime: initialWall,
        draftFold: initialFold,
        foldChanged: false,
        draftReminder: item.deadline_policy?.reminder_minutes ?? 60,
        draftGrace: item.deadline_policy?.grace_minutes ?? 30,
        draftPenalty: item.deadline_policy?.penalty ?? 0,
        frozenPayload: null,
        generation: startGeneration
      };
      card._actionError = null;
      card.render();
    });
    actionsEl.append(editBtn);
  }

  // 6. Cancel: Parents or Creator (for own-assigned tasks)
  if (canCancel) {
    const cancelBtn = card.button(copy.action_cancel, () => {
      if (!canInteract(card, startGeneration)) return;
      const payload = { id: item.id, revision: item.revision };
      card._taskItemAction = {
        type: "confirm_cancel",
        itemId: item.id,
        targetRevision: item.revision,
        targetStatus: item.status,
        targetAssignee: item.assignee,
        targetCreator: item.creator,
        payload,
        frozenPayload: payload,
        generation: startGeneration
      };
      card._actionError = null;
      card.render();
    });
    actionsEl.append(cancelBtn);
  }

  // 7. Archive: Parents only, explicit review
  if ((isParent || personalOwner) && item.status !== "archived") {
    const archiveBtn = card.button(copy.action_archive, () => {
      if (!canInteract(card, startGeneration)) return;
      const payload = { id: item.id, revision: item.revision };
      card._taskItemAction = {
        type: "confirm_archive",
        itemId: item.id,
        targetRevision: item.revision,
        targetStatus: item.status,
        targetAssignee: item.assignee,
        targetCreator: item.creator,
        payload,
        frozenPayload: payload,
        generation: startGeneration
      };
      card._actionError = null;
      card.render();
    });
    actionsEl.append(archiveBtn);
  }

  if (actionsEl.children.length > 0) {
    row.append(actionsEl);
  }

  // Dynamic Interactive Forms for currently active action
  if (isCurrentAction) {
    // If state is stale (status/revision changed or permissions revoked), reject stale form and do not silently upgrade
    if (isActionStateStale()) {
      const staleNotice = el("div", copy.error_stale_state, "notice");
      staleNotice.setAttribute("role", "alert");
      const dismissBtn = card.button(copy.action_cancel_edit, () => {
        card._taskItemAction = null;
        card._actionError = null;
        card.render();
      });
      staleNotice.append(dismissBtn);
      row.append(staleNotice);
      return row;
    }

    const isFailedRetry = Boolean(card._actionError && actionState.frozenPayload);

    // Form A: Report Submission
    if (actionState.type === "submit_report") {
      const form = el("form");
      const isInputFrozen = Boolean(actionState.frozenPayload);

      if (actionState.reportType !== "photo") {
        const initialVal = actionState.draftReport || "";
        const reportInput = card.input(form, "report", copy.label_report, "text", initialVal, actionState.reportType !== "none");
        reportInput.disabled = isWriting || isInputFrozen;
        reportInput.addEventListener("input", (e) => {
          if (!canInteract(card, startGeneration) || isInputFrozen) return;
          actionState.draftReport = e.target.value;
        });

        const validationNotice = el("div", copy.error_report_required, "notice");
        validationNotice.style.display = "none";
        form.append(validationNotice);

        const formActions = el("div", null, "actions");
        const submitText = isFailedRetry ? copy.action_retry : copy.action_save;
        const submitBtn = el("button", submitText, "primary");
        submitBtn.type = "submit";
        submitBtn.disabled = isWriting;
        formActions.append(submitBtn);

        const cancelBtn = card.button(copy.action_cancel_edit, () => {
          card._taskItemAction = null;
          card._actionError = null;
          card.render();
        });
        formActions.append(cancelBtn);
        form.append(formActions);

        form.addEventListener("submit", (e) => {
          e.preventDefault();
          if (!canInteract(card, startGeneration) || isActionStateStale()) return;

          if (isFailedRetry && actionState.frozenPayload) {
            executeCardCommand(card, "tasks.submit", actionState.frozenPayload, startGeneration);
            return;
          }

          const entered = reportInput.value.trim();
          if (actionState.reportType !== "none" && !entered) {
            validationNotice.style.display = "block";
            return;
          }
          validationNotice.style.display = "none";
          actionState.draftReport = reportInput.value;

          const payload = {
            id: item.id,
            revision: actionState.targetRevision !== undefined ? actionState.targetRevision : item.revision,
            report: actionState.reportType === "none" ? null : entered
          };
          actionState.frozenPayload = payload;
          executeCardCommand(card, "tasks.submit", payload, startGeneration);
        });
      }
      row.append(form);
    }

    // Form B: Request Changes Note
    if (actionState.type === "request_changes") {
      const form = el("form");
      const initialVal = actionState.draftNote || "";
      const isInputFrozen = Boolean(actionState.frozenPayload);

      const noteInput = card.input(form, "note", copy.label_review_note, "text", initialVal, true);
      noteInput.disabled = isWriting || isInputFrozen;
      noteInput.addEventListener("input", (e) => {
        if (!canInteract(card, startGeneration) || isInputFrozen) return;
        actionState.draftNote = e.target.value;
      });

      const validationNotice = el("div", copy.error_note_required, "notice");
      validationNotice.style.display = "none";
      form.append(validationNotice);

      const formActions = el("div", null, "actions");
      const submitText = isFailedRetry ? copy.action_retry : copy.action_save;
      const submitBtn = el("button", submitText, "primary");
      submitBtn.type = "submit";
      submitBtn.disabled = isWriting;
      formActions.append(submitBtn);

      const cancelBtn = card.button(copy.action_cancel_edit, () => {
        card._taskItemAction = null;
        card._actionError = null;
        card.render();
      });
      formActions.append(cancelBtn);
      form.append(formActions);

      form.addEventListener("submit", (e) => {
        e.preventDefault();
        if (!canInteract(card, startGeneration) || isActionStateStale()) return;

        if (isFailedRetry && actionState.frozenPayload) {
          executeCardCommand(card, "tasks.request_changes", actionState.frozenPayload, startGeneration);
          return;
        }

        const entered = noteInput.value.trim();
        if (!entered) {
          validationNotice.style.display = "block";
          return;
        }
        validationNotice.style.display = "none";
        actionState.draftNote = noteInput.value;

        const payload = {
          id: item.id,
          revision: actionState.targetRevision !== undefined ? actionState.targetRevision : item.revision,
          note: entered
        };
        actionState.frozenPayload = payload;
        executeCardCommand(card, "tasks.request_changes", payload, startGeneration);
      });

      row.append(form);
    }

    // Form C: Edit / Revise Task
    if (actionState.type === "edit") {
      const form = el("form");
      const isInputFrozen = Boolean(actionState.frozenPayload);
      const zone = getHouseholdZone(card);

      // Title input
      const titleInput = card.input(form, "title", copy.label_title, "text", actionState.draftTitle, true);
      titleInput.disabled = isWriting || isInputFrozen;
      titleInput.addEventListener("input", (e) => {
        if (!canInteract(card, startGeneration) || isInputFrozen) return;
        actionState.draftTitle = e.target.value;
      });

      // Assignee Select: only if Parent
      let assigneeSelect = null;
      if (isParent && !isPersonal) {
        const wrap = el("label", copy.label_assignee);
        assigneeSelect = el("select");
        assigneeSelect.name = "assignee";
        assigneeSelect.disabled = isWriting || isInputFrozen;

        const allMembers = card._data?.members || [];
        const currentAssigneeMember = allMembers.find(m => m.id === item.assignee);
        const activeEligible = allMembers.filter(m => m.active && m.role !== "guest");

        // If current assignee is inactive, render them explicitly so editing title doesn't silently choose first active member
        if (currentAssigneeMember && !currentAssigneeMember.active) {
          const opt = el("option", `${currentAssigneeMember.name} (${copy.unknown_member})`);
          opt.value = currentAssigneeMember.id;
          opt.selected = true;
          assigneeSelect.append(opt);
        }

        for (const m of activeEligible) {
          const opt = el("option", m.name);
          opt.value = m.id;
          if (m.id === (actionState.draftAssignee || item.assignee)) {
            opt.selected = true;
          }
          assigneeSelect.append(opt);
        }
        wrap.append(assigneeSelect);
        form.append(wrap);

        assigneeSelect.addEventListener("change", (e) => {
          if (!canInteract(card, startGeneration) || isInputFrozen) return;
          actionState.draftAssignee = e.target.value;
        });
      }

      // Due at datetime-local input
      const dueInput = card.input(form, "due_at", copy.label_due, "datetime-local", actionState.draftWallTime || "", false);
      dueInput.disabled = isWriting || isInputFrozen;

      // Daylight Saving gap error notice & ambiguous fold select
      const gapNotice = el("div", copy.error_dst_gap, "notice");
      gapNotice.style.display = "none";
      form.append(gapNotice);

      const ambiguousNotice = el("div", copy.error_dst_ambiguous, "notice");
      ambiguousNotice.style.display = "none";
      form.append(ambiguousNotice);

      const foldWrap = el("label", copy.label_due_fold);
      const foldSelect = el("select");
      foldSelect.name = "due_fold";
      foldSelect.disabled = isWriting || isInputFrozen;

      const optPlaceholder = el("option", copy.label_due_fold_select);
      optPlaceholder.value = "";
      const opt0 = el("option", copy.label_due_fold_standard);
      opt0.value = "0";
      const opt1 = el("option", copy.label_due_fold_daylight);
      opt1.value = "1";
      foldSelect.append(optPlaceholder, opt0, opt1);
      foldSelect.value = actionState.draftFold !== null && actionState.draftFold !== undefined ? String(actionState.draftFold) : "";
      foldWrap.append(foldSelect);
      foldWrap.style.display = "none";
      form.append(foldWrap);

      const updateDueCandidates = (val) => {
        gapNotice.style.display = "none";
        ambiguousNotice.style.display = "none";
        foldWrap.style.display = "none";
        if (!val) return [];

        try {
          const candidates = wallTimeCandidates(val, zone);
          if (candidates.length === 0) {
            gapNotice.style.display = "block";
            return [];
          }
          if (candidates.length === 2) {
            foldWrap.style.display = "grid";
          }
          return candidates;
        } catch {
          return [];
        }
      };

      // Initial candidate check
      if (actionState.draftWallTime) {
        updateDueCandidates(actionState.draftWallTime);
      }

      dueInput.addEventListener("input", (e) => {
        if (!canInteract(card, startGeneration) || isInputFrozen) return;
        actionState.draftWallTime = e.target.value;
        // If changed wall time differs from original untouched wall time, reset fold to require explicit choice
        if (e.target.value !== actionState.originalWallTime) {
          actionState.draftFold = null;
          foldSelect.value = "";
        }
        updateDueCandidates(e.target.value);
      });

      foldSelect.addEventListener("change", (e) => {
        if (!canInteract(card, startGeneration) || isInputFrozen) return;
        ambiguousNotice.style.display = "none";
        actionState.draftFold = e.target.value === "" ? null : Number(e.target.value);
        actionState.foldChanged = true;
      });

      // Deadline policy details / inputs
      // Ranges from domain tasks.py & task_events.py:
      // reminder_minutes: 0..10080
      // grace_minutes: 0..1440
      // penalty: -10..0 (parents only)
      const policyDetails = el("details");
      policyDetails.append(el("summary", copy.label_deadline_policy));

      const reminderInput = card.input(policyDetails, "reminder_minutes", copy.label_reminder_minutes, "number", String(actionState.draftReminder), true);
      reminderInput.min = "0";
      reminderInput.max = "10080";
      reminderInput.step = "1";
      reminderInput.disabled = isWriting || isInputFrozen;
      reminderInput.addEventListener("input", (e) => {
        if (!canInteract(card, startGeneration) || isInputFrozen) return;
        actionState.draftReminder = Number(e.target.value);
      });

      const graceInput = card.input(policyDetails, "grace_minutes", copy.label_grace_minutes, "number", String(actionState.draftGrace), true);
      graceInput.min = "0";
      graceInput.max = "1440";
      graceInput.step = "1";
      graceInput.disabled = isWriting || isInputFrozen || isPersonal;
      graceInput.addEventListener("input", (e) => {
        if (!canInteract(card, startGeneration) || isInputFrozen) return;
        actionState.draftGrace = Number(e.target.value);
      });

      let penaltyInput = null;
      if (isParent && !isPersonal) {
        penaltyInput = card.input(policyDetails, "penalty", copy.label_penalty, "number", String(actionState.draftPenalty), true);
        penaltyInput.min = "-10";
        penaltyInput.max = "0";
        penaltyInput.step = "1";
        penaltyInput.disabled = isWriting || isInputFrozen;
        penaltyInput.addEventListener("input", (e) => {
          if (!canInteract(card, startGeneration) || isInputFrozen) return;
          actionState.draftPenalty = Number(e.target.value);
        });
      }

      form.append(policyDetails);

      const formActions = el("div", null, "actions");
      const submitText = isFailedRetry ? copy.action_retry : copy.action_save;
      const submitBtn = el("button", submitText, "primary");
      submitBtn.type = "submit";
      submitBtn.disabled = isWriting;
      formActions.append(submitBtn);

      const cancelBtn = card.button(copy.action_cancel_edit, () => {
        card._taskItemAction = null;
        card._actionError = null;
        card.render();
      });
      formActions.append(cancelBtn);
      form.append(formActions);

      form.addEventListener("submit", (e) => {
        e.preventDefault();
        if (!canInteract(card, startGeneration) || isActionStateStale()) return;

        if (isFailedRetry && actionState.frozenPayload) {
          executeCardCommand(card, "tasks.revise", actionState.frozenPayload, startGeneration);
          return;
        }

        const titleVal = titleInput.value.trim();
        if (!titleVal) return;

        const payload = {
          id: item.id,
          revision: actionState.targetRevision !== undefined ? actionState.targetRevision : item.revision,
          title: titleVal
        };

        if (isParent && assigneeSelect && assigneeSelect.value !== item.assignee) {
          payload.assignee = assigneeSelect.value;
        }

        const wallVal = dueInput.value.trim();
        if (!wallVal) {
          // Cleared due date -> null
          payload.due_at = null;
        } else {
          const candidates = updateDueCandidates(wallVal);
          if (candidates.length === 0) {
            gapNotice.style.display = "block";
            return;
          }

          const isUntouchedWall = actionState.originalWallTime && wallVal === actionState.originalWallTime;
          if (isUntouchedWall && !actionState.foldChanged) {
            payload.due_at = actionState.originalDueAt;
          } else if (candidates.length === 1) {
            payload.due_at = candidates[0];
          } else {
            // Ambiguous fold case:
            // If untouched wall time matches original wall time and fold was not explicitly changed, preserve original exact ISO
            if (!["0","1"].includes(foldSelect.value)) {
              // DST fold must NOT silently default for new/changed ambiguous wall time: require explicit selection
              ambiguousNotice.style.display = "block";
              return;
            } else {
              const foldIdx = Number(foldSelect.value);
              payload.due_at = candidates[foldIdx];
            }
          }
        }

        payload.reminder_minutes = Number(reminderInput.value);
        payload.grace_minutes = Number(graceInput.value);
        if (isParent && penaltyInput) {
          payload.penalty = Number(penaltyInput.value);
        }

        actionState.frozenPayload = payload;
        executeCardCommand(card, "tasks.revise", payload, startGeneration);
      });

      row.append(form);
    }

    // Form D: Confirm Cancel
    if (actionState.type === "confirm_cancel") {
      const confirmNotice = el("div", null, "notice");
      confirmNotice.append(el("p", copy.warning_cancel));

      const confirmActions = el("div", null, "actions");
      const confirmBtnText = isFailedRetry ? copy.action_retry : copy.action_confirm_cancel;
      const confirmBtn = card.button(confirmBtnText, () => {
        if (!canInteract(card, startGeneration) || isActionStateStale()) return;
        const payload = actionState.frozenPayload || {
          id: item.id,
          revision: actionState.targetRevision !== undefined ? actionState.targetRevision : item.revision
        };
        actionState.frozenPayload = payload;
        executeCardCommand(card, "tasks.cancel", payload, startGeneration);
      }, true);
      confirmActions.append(confirmBtn);

      const cancelBtn = card.button(copy.action_cancel_edit, () => {
        card._taskItemAction = null;
        card._actionError = null;
        card.render();
      });
      confirmActions.append(cancelBtn);
      confirmNotice.append(confirmActions);
      row.append(confirmNotice);
    }

    // Form E: Confirm Archive
    if (actionState.type === "confirm_archive") {
      const confirmNotice = el("div", null, "notice");
      confirmNotice.append(el("p", copy.warning_archive));

      const confirmActions = el("div", null, "actions");
      const confirmBtnText = isFailedRetry ? copy.action_retry : copy.action_confirm_archive;
      const confirmBtn = card.button(confirmBtnText, () => {
        if (!canInteract(card, startGeneration) || isActionStateStale()) return;
        const payload = actionState.frozenPayload || {
          id: item.id,
          revision: actionState.targetRevision !== undefined ? actionState.targetRevision : item.revision
        };
        actionState.frozenPayload = payload;
        executeCardCommand(card, "tasks.archive", payload, startGeneration);
      }, true);
      confirmActions.append(confirmBtn);

      const cancelBtn = card.button(copy.action_cancel_edit, () => {
        card._taskItemAction = null;
        card._actionError = null;
        card.render();
      });
      confirmActions.append(cancelBtn);
      confirmNotice.append(confirmActions);
      row.append(confirmNotice);
    }
  }

  return row;
}

export function renderTaskArchive(card, body) {
  const copy = getCopy(card);
  const details = el("details", null, "tasks-archive");
  const summary = el("summary", copy.archive_title);
  details.append(summary);

  const allTasks = card._data?.tasks || [];
  const archivedTasks = allTasks.filter(item =>
    item && FINAL_STATUSES.has(item.status)
  );

  if (archivedTasks.length === 0) {
    details.append(el("div", copy.archive_empty, "empty"));
  } else {
    const list = el("ul", null, "list");
    for (const item of archivedTasks.slice().reverse()) {
      renderTaskItem(card, list, item);
    }
    details.append(list);
  }

  if (body && typeof body.append === "function") {
    body.append(details);
  }
  return details;
}
