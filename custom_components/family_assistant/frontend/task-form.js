import {wallTimeCandidates} from "./local-time.js";
import {personalTaskCopy} from "./personal-task-copy.js";

export const TASK_FORM_COPY = {
  en: {
    checklist: "Steps — one per line (optional)",
    reportType: "Report required",
    text: "Text",
    none: "No report text",
    photo: "Photo",
    zone: "Deadline uses household time zone",
    fold: "This time occurs twice. Choose an occurrence",
    choose: "Choose…",
    first: "First occurrence",
    second: "Second occurrence",
    invalid: "This local time does not exist or is invalid. Choose another time.",
    retry: "Retry the same task",
    frozen: "The outcome is unconfirmed. Retry sends the same task, without creating a second copy.",
    multiMember: "Assign to multiple people",
    multiMemberHint: "Creates a separate task for each person (not shared completion). Reports are individual; penalties apply only if enabled.",
    selectMembers: "Select people (1–20)",
    selectedCount: "Selected: {count} / 20",
    maxMembersNotice: "Maximum 20 people reached",
    reviewBatch: "Review tasks",
    reviewTitle: "Review multi-member tasks",
    reviewPeople: "Selected people",
    reviewDeadline: "Deadline",
    reviewChecklist: "Checklist",
    reviewReport: "Report",
    reviewPolicy: "Penalties & reminders",
    noDeadline: "No deadline",
    noChecklist: "No checklist steps",
    confirmBatch: "I confirm creating separate tasks for all selected people",
    applyBatch: "Create separate tasks",
    back: "Back",
    cancel: "Cancel",
    closeWithoutRollback: "Close without rollback",
    uncertainNotice: "This batch was submitted and may already have been applied on the server. Closing will not roll back any created tasks.",
    staleError: "Selected members or their revisions changed. Please review and confirm again.",
    memberCountError: "Select between 1 and 20 active members.",
    memberRevision: "rev",
  },
  ru: {
    checklist: "Шаги — по одному в строке (необязательно)",
    reportType: "Требуемый отчёт",
    text: "Текст",
    none: "Без текста отчёта",
    photo: "Фото",
    zone: "Срок в часовом поясе семьи",
    fold: "Это время встречается дважды. Выберите вариант",
    choose: "Выберите…",
    first: "Первое вхождение",
    second: "Второе вхождение",
    invalid: "Такого местного времени нет или оно некорректно. Выберите другое.",
    retry: "Повторить ту же задачу",
    frozen: "Результат не подтверждён. Повтор отправит ту же задачу, не создавая вторую копию.",
    multiMember: "Назначить нескольким людям",
    multiMemberHint: "Для каждого человека создаётся отдельная задача (не общее выполнение). Отчёты индивидуальные, штрафы — только если вы их включили.",
    selectMembers: "Выберите участников (1–20)",
    selectedCount: "Выбрано: {count} / 20",
    maxMembersNotice: "Достигнут максимум 20 человек",
    reviewBatch: "Проверить задачи",
    reviewTitle: "Проверка задач для нескольких участников",
    reviewPeople: "Выбранные участники",
    reviewDeadline: "Срок",
    reviewChecklist: "Шаги",
    reviewReport: "Отчёт",
    reviewPolicy: "Штрафы и напоминания",
    noDeadline: "Без срока",
    noChecklist: "Без шагов",
    confirmBatch: "Подтверждаю создание отдельных задач для всех выбранных участников",
    applyBatch: "Создать отдельные задачи",
    back: "Назад",
    cancel: "Отмена",
    closeWithoutRollback: "Закрыть без отката",
    uncertainNotice: "Пакет был отправлен и мог уже выполниться на сервере. Закрытие не отменит уже созданные задачи.",
    staleError: "Выбранные участники или их версии изменились. Проверьте и подтвердите снова.",
    memberCountError: "Выберите от 1 до 20 активных участников.",
    memberRevision: "версия",
  },
  uk: {
    checklist: "Кроки — по одному в рядку (необов’язково)",
    reportType: "Потрібний звіт",
    text: "Текст",
    none: "Без тексту звіту",
    photo: "Фото",
    zone: "Строк у часовому поясі сім’ї",
    fold: "Цей час трапляється двічі. Виберіть варіант",
    choose: "Виберіть…",
    first: "Перше входження",
    second: "Друге входження",
    invalid: "Такого місцевого часу немає або він некоректний. Виберіть інший.",
    retry: "Повторити те саме завдання",
    frozen: "Результат не підтверджено. Повтор надішле те саме завдання, не створюючи другу копію.",
    multiMember: "Призначити кільком людям",
    multiMemberHint: "Для кожної людини створюється окреме завдання (не спільне виконання). Звіти індивідуальні, штрафи — лише якщо ви їх увімкнули.",
    selectMembers: "Виберіть учасників (1–20)",
    selectedCount: "Обрано: {count} / 20",
    maxMembersNotice: "Досягнуто максимум 20 людей",
    reviewBatch: "Перевірити завдання",
    reviewTitle: "Перевірка завдань для кількох учасників",
    reviewPeople: "Вибрані учасники",
    reviewDeadline: "Термін",
    reviewChecklist: "Кроки",
    reviewReport: "Звіт",
    reviewPolicy: "Штрафи та нагадування",
    noDeadline: "Без терміну",
    noChecklist: "Без кроків",
    confirmBatch: "Підтверджую створення окремих завдань для всіх вибраних учасників",
    applyBatch: "Створити окремі завдання",
    back: "Назад",
    cancel: "Скасувати",
    closeWithoutRollback: "Закрити без відкату",
    uncertainNotice: "Пакет було надіслано і він міг уже виконатися на сервері. Закриття не скасує вже створені завдання.",
    staleError: "Вибрані учасники або їхні версії змінилися. Перевірте та підтвердьте знову.",
    memberCountError: "Виберіть від 1 до 20 активних учасників.",
    memberRevision: "версія",
  },
};

const el = (tag, text) => {
  const node = document.createElement(tag);
  if (text != null) node.textContent = text;
  return node;
};

const deepFreeze = (obj) => {
  if (!obj || typeof obj !== "object" || Object.isFrozen(obj)) return obj;
  Object.freeze(obj);
  for (const child of Object.values(obj)) deepFreeze(child);
  return obj;
};

function isFormAttached(card, form) {
  if (card.isConnected && !form.isConnected) return false;
  if (card.shadowRoot && !card.shadowRoot.contains(form)) return false;
  return true;
}

function getScope(card) {
  const data = card?._data;
  if (!data) return null;
  const actor = data.actor;
  const actorMember = (data.members || []).find((m) => m && m.id === actor);
  if (
    !actorMember ||
    actorMember.active !== true ||
    actorMember.role !== data.role ||
    !Number.isSafeInteger(actorMember.revision) ||
    actorMember.revision < 1
  ) {
    return null;
  }
  if (data.actor_revision != null && data.actor_revision !== actorMember.revision) return null;
  return {
    entry: card._entry,
    generation: card._generation,
    haUser: card._hass?.user?.id ?? null,
    actor,
    role: data.role,
    actorRevision: actorMember.revision,
    timezone: data.settings?.timezone || card._hass?.config?.time_zone || "UTC",
    hasTasks: (data.settings?.modules || []).includes("tasks"),
  };
}

function sameScope(a, b) {
  if (!a || !b) return false;
  return (
    a.entry === b.entry &&
    a.generation === b.generation &&
    a.haUser === b.haUser &&
    a.actor === b.actor &&
    a.role === b.role &&
    a.actorRevision === b.actorRevision &&
    a.timezone === b.timezone &&
    a.hasTasks === b.hasTasks
  );
}

function getActiveNonguestMembers(card) {
  return (card._data?.members || []).filter(
    (m) =>
      m &&
      m.active === true &&
      m.role !== "guest" &&
      Number.isSafeInteger(m.revision) &&
      m.revision >= 1
  );
}

function checkReviewedMembers(card, reviewedMembers) {
  if (
    !Array.isArray(reviewedMembers) ||
    reviewedMembers.length === 0 ||
    reviewedMembers.length > 20
  ) {
    return false;
  }
  for (const snap of reviewedMembers) {
    const current = (card._data?.members || []).find((m) => m && m.id === snap.id);
    if (!current) return false;
    if (current.active !== true) return false;
    if (current.role === "guest" || current.role !== snap.role) return false;
    if (current.revision !== snap.revision) return false;
  }
  return true;
}

export function reconcileTaskFormRefresh(card, previousData) {
  if (!card) return false;
  const draft = card._taskCreateDraft;
  if (!draft) return false;

  const currentAccess = getScope(card);
  if (!currentAccess || !draft.access || !sameScope(currentAccess, draft.access)) {
    card._taskCreateDraft = null;
    return true;
  }

  let force = false;
  if (draft.pending && !checkReviewedMembers(card, draft.reviewedMembers)) {
    disposeTaskForm(card);
    return true;
  }
  if (draft.multi) {
    if (draft.pending) {
      for (const cmd of draft.pending.payload.commands || []) {
        const assigneeId = cmd.payload?.assignee;
        const currentM = (card._data?.members || []).find((m) => m && m.id === assigneeId);
        if (
          !currentM ||
          currentM.active !== true ||
          currentM.role === "guest" ||
          currentM.revision !== cmd.payload?.assignee_revision
        ) {
          card._taskCreateDraft = null;
          return true;
        }
      }
    } else if (draft.stage === "review") {
      if (!checkReviewedMembers(card, draft.reviewedMembers)) {
        draft.stage = "edit";
        draft.confirmed = false;
        draft.reviewedMembers = null;
        draft.error = "staleError";
        force = true;
      }
    } else {
      const prevCount = (draft.selectedMembers || []).length;
      draft.selectedMembers = (draft.selectedMembers || []).filter((id) => {
        const m = (card._data?.members || []).find((mem) => mem && mem.id === id);
        return (
          m &&
          m.active === true &&
          m.role !== "guest" &&
          Number.isSafeInteger(m.revision) &&
          m.revision >= 1
        );
      });
      if (draft.selectedMembers.length !== prevCount) {
        force = true;
      }
    }
  } else {
    if (draft.pending) {
      const assigneeId = draft.pending.payload?.assignee;
      const currentM = (card._data?.members || []).find((m) => m && m.id === assigneeId);
      if (
        !currentM ||
        currentM.active !== true ||
        currentM.role === "guest" ||
        currentM.revision !== draft.pending.payload?.assignee_revision
      ) {
        card._taskCreateDraft = null;
        return true;
      }
    } else if (draft.assignee) {
      const currentM = (card._data?.members || []).find((m) => m && m.id === draft.assignee);
      if (!currentM || currentM.active !== true || currentM.role === "guest") {
        draft.assignee = "";
        force = true;
      }
    }
  }

  return force;
}

export function disposeTaskForm(card) {
  if (!card) return;
  card._taskCreateDraft = null;
  card.shadowRoot?.querySelectorAll('form[data-task-create]').forEach(form => form.remove());
}

function renderReview(card, form, draft, copy, canInteract, generation) {
  form.dataset.taskCreate = "true";

  const heading = el("h3", copy.reviewTitle);
  form.append(heading);

  const hint = el("p", copy.multiMemberHint);
  hint.className = "notice";
  form.append(hint);

  const preview = el("div");
  preview.className = "task-multi-review-preview";

  const titleP = el("p");
  const titleB = el("strong", `${card.t.title}: `);
  titleP.append(titleB, document.createTextNode(draft.title));
  preview.append(titleP);

  const peopleP = el("p");
  const peopleB = el("strong", `${copy.reviewPeople} (${draft.reviewedMembers.length}):`);
  peopleP.append(peopleB);
  preview.append(peopleP);

  const memberList = el("ul");
  memberList.className = "task-multi-member-list";
  for (const m of draft.reviewedMembers) {
    const li = el("li", m.name);
    memberList.append(li);
  }
  preview.append(memberList);

  const dueP = el("p");
  const dueB = el("strong", `${copy.reviewDeadline}: `);
  const zone = draft.access?.timezone || "UTC";
  const occurrence = draft.fold === "0" ? copy.first : draft.fold === "1" ? copy.second : "";
  const dueText = draft.due_at ? `${draft.due_at.replace("T", " ")} (${copy.zone}: ${zone})${occurrence ? ` · ${occurrence}` : ""}` : copy.noDeadline;
  dueP.append(dueB, document.createTextNode(dueText));
  preview.append(dueP);

  const checkP = el("p");
  const checkB = el("strong", `${copy.reviewChecklist}: `);
  const steps = (draft.checklist || "").split(/\r?\n/).map((s) => s.trim()).filter(Boolean);
  checkP.append(checkB, document.createTextNode(steps.length ? String(steps.length) : copy.noChecklist));
  preview.append(checkP);
  if (steps.length > 0) {
    const ol = el("ol");
    for (const s of steps) {
      ol.append(el("li", s));
    }
    preview.append(ol);
  }

  const repP = el("p");
  const repB = el("strong", `${copy.reviewReport}: `);
  const repText = copy[draft.report_type] || draft.report_type;
  repP.append(repB, document.createTextNode(repText));
  preview.append(repP);

  const polP = el("p");
  const polB = el("strong", `${copy.reviewPolicy}: `);
  const polText = `${card.t.reminderMinutes}: ${draft.reminder_minutes ?? 60} · ${card.t.graceMinutes}: ${draft.grace_minutes ?? 30} · ${card.t.taskPenalty}: ${draft.penalty ?? 0}`;
  polP.append(polB, document.createTextNode(polText));
  preview.append(polP);

  form.append(preview);

  if (draft.error) {
    const err = el("p", copy[draft.error] || draft.error);
    err.className = "notice";
    err.setAttribute("role", "alert");
    form.append(err);
  }

  if (draft.pending) {
    const uncertain = el("p", copy.uncertainNotice);
    uncertain.className = "notice";
    uncertain.setAttribute("role", "alert");
    form.append(uncertain);

    const frozen = el("p", copy.frozen);
    frozen.className = "notice";
    form.append(frozen);
  }

  const actions = el("div");
  actions.className = "actions";

  let submitBtn = null;
  if (!draft.pending) {
    const confirmWrap = el("label", copy.confirmBatch);
    confirmWrap.className = "check";
    const confirmBox = el("input");
    confirmBox.type = "checkbox";
    confirmBox.name = "confirm_batch";
    confirmBox.checked = draft.confirmed === true;
    confirmWrap.prepend(confirmBox);
    form.append(confirmWrap);

    submitBtn = el("button", copy.applyBatch);
    submitBtn.type = "submit";
    submitBtn.className = "primary";
    submitBtn.disabled = !draft.confirmed || Boolean(card._writing);

    confirmBox.addEventListener("change", () => {
      if (!canInteract()) return;
      draft.confirmed = confirmBox.checked;
      submitBtn.disabled = !draft.confirmed || Boolean(card._writing);
    });

    const backBtn = el("button", copy.back);
    backBtn.type = "button";
    backBtn.addEventListener("click", () => {
      if (!canInteract()) return;
      draft.stage = "edit";
      draft.confirmed = false;
      draft.error = null;
      card.render();
    });

    const cancelBtn = el("button", copy.cancel);
    cancelBtn.type = "button";
    cancelBtn.addEventListener("click", () => {
      if (!isFormAttached(card, form) || card._writing || card._taskCreateDraft !== draft) return;
      card._form = null;
      card._taskCreateDraft = null;
      card.render();
    });

    actions.append(submitBtn, backBtn, cancelBtn);
  } else {
    submitBtn = el("button", copy.retry);
    submitBtn.type = "submit";
    submitBtn.className = "primary";
    submitBtn.disabled = Boolean(card._writing);

    const closeBtn = el("button", copy.closeWithoutRollback);
    closeBtn.type = "button";
    closeBtn.addEventListener("click", () => {
      if (!isFormAttached(card, form) || card._writing || card._taskCreateDraft !== draft) return;
      card._form = null;
      card._taskCreateDraft = null;
      card.render();
    });

    actions.append(submitBtn, closeBtn);
  }
  form.append(actions);

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!canInteract()) return;

    if (!draft.pending) {
      if (!draft.confirmed) return;
      if (!checkReviewedMembers(card, draft.reviewedMembers)) {
        draft.stage = "edit";
        draft.confirmed = false;
        draft.reviewedMembers = null;
        draft.error = "staleError";
        card.render();
        return;
      }

      const steps = (draft.checklist || "").split(/\r?\n/).map((s) => s.trim()).filter(Boolean);
      const commands = draft.reviewedMembers.map((m) => {
        const p = {
          title: draft.title,
          assignee: m.id,
          assignee_revision: m.revision,
          report_type: draft.report_type,
          checklist: steps,
          reminder_minutes: Number(draft.reminder_minutes ?? 60),
          grace_minutes: Number(draft.grace_minutes ?? 30),
          penalty: Number(draft.penalty ?? 0),
        };
        if (draft.reviewedDueAt) p.due_at = draft.reviewedDueAt;
        return { action: "tasks.create", payload: p };
      });

      const operationId = crypto.randomUUID();
      draft.pending = deepFreeze({
        action: "batch",
        payload: { commands },
        operation_id: operationId,
      });
      draft.payload = draft.pending.payload;
    } else {
      if (!checkReviewedMembers(card, draft.reviewedMembers)) {
        disposeTaskForm(card);
        card._form = null;
        card._actionError = "conflict";
        card.render();
        return;
      }
      for (const cmd of draft.pending.payload.commands || []) {
        const currentM = (card._data?.members || []).find((m) => m && m.id === cmd.payload?.assignee);
        if (
          !currentM ||
          currentM.active !== true ||
          currentM.role === "guest" ||
          currentM.revision !== cmd.payload?.assignee_revision
        ) {
          disposeTaskForm(card);
          card._form = null;
          card._actionError = "conflict";
          card.render();
          return;
        }
      }
    }

    const pending = draft.pending;
    await card.command(pending.action, pending.payload, pending.operation_id);

    if (card._generation !== generation) return;
    if (card._taskCreateDraft !== draft) return;
    if (!card._actionError) {
      card._taskCreateDraft = null;
    }
    card.render();
  });
}

export function renderTaskForm(card) {
  reconcileTaskFormRefresh(card, card._data);
  const copy =
    TASK_FORM_COPY[card._config?.language || card._hass?.language?.split("-")[0]] ||
    TASK_FORM_COPY.en;
  const currentScope = getScope(card);
  if (!currentScope || !currentScope.hasTasks || currentScope.role === "guest") {
    disposeTaskForm(card);
    const unavailable = el("p", copy.staleError);
    unavailable.className = "notice";
    unavailable.setAttribute("role", "alert");
    return unavailable;
  }
  const generation = card._generation;
  const entry = card._entry;
  const haUser = card._hass?.user?.id ?? null;
  const actor = card._data?.actor;
  const role = card._data?.role;
  const actorMember = (card._data?.members || []).find((m) => m && m.id === actor);
  const actorRevision = actorMember?.revision;
  const personalCopy = personalTaskCopy(card);
  const zone = card._data?.settings?.timezone || card._hass?.config?.time_zone || "UTC";

  const draft = (card._taskCreateDraft ||= {
    title: "",
    assignee: "",
    due_at: "",
    fold: "",
    checklist: "",
    report_type: "text",
    multi: false,
    selectedMembers: [],
    stage: "edit",
    confirmed: false,
    reviewedMembers: null,
    pending: null,
    payload: null,
    error: null,
    reminder_minutes: 60,
    grace_minutes: 30,
    penalty: 0,
    personal: false,
  });

  if (!draft.access && actorMember && Number.isSafeInteger(actorRevision) && actorRevision >= 1) {
    draft.access = deepFreeze({
      entry,
      generation,
      haUser,
      actor,
      role,
      actorRevision,
      timezone: zone,
      hasTasks: Boolean(card._data?.settings?.modules?.includes("tasks")),
    });
  }

  if (!card.parent) {
    draft.multi = false;
  }

  const form = el("form");
  form.dataset.taskCreate = "true";

  const canInteract = () => {
    if (!sameScope(getScope(card), draft.access)) return false;
    if (!isFormAttached(card, form)) return false;
    if (card._writing) return false;
    if (card._generation !== generation) return false;
    if (card._entry !== entry) return false;
    if ((card._hass?.user?.id ?? null) !== haUser) return false;
    if (card._data?.actor !== actor) return false;
    if (card._data?.role !== role || card._data?.role === "guest") return false;
    const nowActor = (card._data?.members || []).find((m) => m && m.id === actor);
    if (
      !nowActor ||
      nowActor.active !== true ||
      nowActor.role !== role ||
      nowActor.revision !== actorRevision
    )
      return false;
    if (!card._data?.settings?.modules?.includes("tasks")) return false;
    if (zone !== (card._data?.settings?.timezone || card._hass?.config?.time_zone || "UTC"))
      return false;
    if (card._taskCreateDraft !== draft) return false;
    return true;
  };

  if (draft.multi && draft.stage === "review") {
    renderReview(card, form, draft, copy, canInteract, generation);
    return form;
  }

  const title = card.input(form, "title", card.t.title, "text", draft.title);
  title.maxLength = 500;

  const personalWrap = el("label", personalCopy.label);
  const personal = el("input");
  personal.type = "checkbox";
  personal.name = "personal";
  personal.checked = draft.personal === true;
  personalWrap.prepend(personal);
  form.append(personalWrap);

  const personalHint = el("p", personalCopy.hint);
  personalHint.className = "sub";
  personalHint.hidden = !personal.checked;
  form.append(personalHint);

  let multiWrap = null, multi = null, multiHint = null;
  if (card.parent) {
    multiWrap = el("label", copy.multiMember);
    multi = el("input");
    multi.type = "checkbox";
    multi.name = "multi";
    multi.checked = draft.multi === true;
    multiWrap.prepend(multi);
    form.append(multiWrap);

    multiHint = el("p", copy.multiMemberHint);
    multiHint.className = "sub";
    multiHint.hidden = !multi.checked;
    form.append(multiHint);
  }

  const assignee = card.memberSelect(form);
  const assigneeWrap = assignee.closest("label") || assignee.parentElement;
  if (draft.assignee && [...assignee.options].some((o) => o.value === draft.assignee)) {
    assignee.value = draft.assignee;
  } else if (draft.assignee) {
    const missing = el("option", card.t.selectMember);
    missing.value = "";
    assignee.prepend(missing);
    assignee.value = "";
  }
  assignee.required = !draft.multi;

  let multiMembersContainer = null;
  if (card.parent) {
    multiMembersContainer = el("fieldset");
    multiMembersContainer.className = "task-multi-members";
    multiMembersContainer.hidden = !draft.multi;
    const legend = el("legend", copy.selectMembers);
    multiMembersContainer.append(legend);

    const eligible = getActiveNonguestMembers(card);
    const countDiv = el(
      "div",
      copy.selectedCount.replace("{count}", String((draft.selectedMembers || []).length))
    );
    countDiv.className = "sub";
    multiMembersContainer.append(countDiv);

    for (const m of eligible) {
      const mLabel = el("label", ` ${m.name}`);
      mLabel.className = "check";
      const mBox = el("input");
      mBox.type = "checkbox";
      mBox.name = "assignee_multi";
      mBox.value = m.id;
      mBox.checked = (draft.selectedMembers || []).includes(m.id);
      mLabel.prepend(mBox);
      multiMembersContainer.append(mLabel);

      mBox.addEventListener("change", () => {
        if (!canInteract() || draft.payload || draft.pending) return;
        draft.selectedMembers = draft.selectedMembers || [];
        if (mBox.checked) {
          if (!draft.selectedMembers.includes(m.id)) {
            if (draft.selectedMembers.length >= 20) {
              mBox.checked = false;
              return;
            }
            draft.selectedMembers.push(m.id);
          }
        } else {
          draft.selectedMembers = draft.selectedMembers.filter((id) => id !== m.id);
        }
        draft.error = null;
        countDiv.textContent = copy.selectedCount.replace(
          "{count}",
          String(draft.selectedMembers.length)
        );
      });
    }
    form.append(multiMembersContainer);
  }

  const due = card.input(form, "due_at", card.t.due, "datetime-local", draft.due_at, false);
  due.min = "0001-01-01T00:00";
  due.max = "9999-12-31T23:59";
  const hint = el("p", `${copy.zone}: ${zone}`);
  hint.className = "sub";
  form.append(hint);

  const foldWrap = el("label", copy.fold);
  const fold = el("select");
  fold.name = "due_fold";
  for (const [value, label] of [
    ["", copy.choose],
    ["0", copy.first],
    ["1", copy.second],
  ]) {
    const option = el("option", label);
    option.value = value;
    fold.append(option);
  }
  fold.value = draft.fold;
  foldWrap.append(fold);
  form.append(foldWrap);

  const invalid = el("p", copy.invalid);
  invalid.className = "notice";
  invalid.setAttribute("role", "alert");
  invalid.hidden = true;
  form.append(invalid);

  const updateDue = () => {
    invalid.hidden = true;
    foldWrap.hidden = true;
    fold.required = false;
    if (!due.value) return [];
    try {
      const candidates = wallTimeCandidates(due.value, zone);
      invalid.hidden = candidates.length > 0;
      foldWrap.hidden = candidates.length < 2;
      fold.required = candidates.length > 1;
      return candidates;
    } catch {
      invalid.hidden = false;
      return [];
    }
  };
  updateDue();

  const checklistWrap = el("label", copy.checklist);
  const checklist = el("textarea");
  checklist.name = "checklist";
  checklist.rows = 3;
  checklist.value = draft.checklist;
  checklist.maxLength = 10049;
  checklistWrap.append(checklist);
  form.append(checklistWrap);

  const reportWrap = el("label", copy.reportType);
  const report = el("select");
  report.name = "report_type";
  for (const value of ["text", "photo", "none"]) {
    const option = el("option", copy[value] || value);
    option.value = value;
    report.append(option);
  }
  report.value = draft.report_type;
  reportWrap.append(report);
  form.append(reportWrap);

  const advanced = el("details");
  advanced.append(el("summary", card.t.advanced));
  card.deadlinePolicy(advanced);
  form.append(advanced);

  for (const key of ["reminder_minutes", "grace_minutes", "penalty"]) {
    const input = form.elements.namedItem(key);
    if (input && key in draft) input.value = draft[key];
  }

  let submit = null;

  const syncMulti = () => {
    const isMulti = Boolean(multi && multi.checked);
    draft.multi = isMulti;
    if (multiHint) multiHint.hidden = !isMulti;
    if (isMulti) {
      personal.checked = false;
      personal.disabled = true;
      personalHint.hidden = true;
      draft.personal = false;
      assigneeWrap.hidden = true;
      assignee.required = false;
      if (multiMembersContainer) multiMembersContainer.hidden = false;
    } else {
      if (!draft.payload && !draft.pending && !card._writing) {
        personal.disabled = false;
      }
      assigneeWrap.hidden = false;
      assignee.required = true;
      if (multiMembersContainer) multiMembersContainer.hidden = true;
    }
    for (const field of [
      assignee,
      report,
      ...["grace_minutes", "penalty"].map((k) => form.elements.namedItem(k)).filter(Boolean),
    ]) {
      field.disabled = Boolean(card._writing || draft.payload || draft.pending || personal.checked);
    }
    if (submit) {
      submit.textContent =
        draft.payload || draft.pending
          ? copy.retry
          : isMulti
          ? copy.reviewBatch
          : card.t.save;
    }
  };

  const syncPersonal = () => {
    personalHint.hidden = !personal.checked;
    if (personal.checked) {
      if (multi) {
        multi.checked = false;
        multi.disabled = true;
        if (multiHint) multiHint.hidden = true;
      }
      draft.multi = false;
      if (!draft.pending) {
        draft.selectedMembers = [];
        draft.reviewedMembers = null;
        draft.confirmed = false;
      }
      assignee.value = actor || "";
      report.value = "none";
      draft.assignee = actor || "";
      draft.report_type = "none";
      for (const key of ["grace_minutes", "penalty"]) {
        const input = form.elements.namedItem(key);
        if (input) input.value = "0";
        draft[key] = "0";
      }
    } else {
      if (multi && !card._writing && !draft.payload && !draft.pending) {
        multi.disabled = false;
      }
    }
    syncMulti();
  };

  form.addEventListener("input", (event) => {
    if (!canInteract() || draft.payload || draft.pending) return;
    if (event.target === checklist) checklist.setCustomValidity("");
    if (event.target.name) {
      const name = event.target.name === "due_fold" ? "fold" : event.target.name;
      if (event.target === personal) draft.personal = personal.checked;
      else if (event.target === multi) draft.multi = multi.checked;
      else if (event.target.name !== "assignee_multi") draft[name] = event.target.value;
    }
    if (event.target === personal) syncPersonal();
    if (event.target === multi) syncMulti();
    if (event.target === due) {
      draft.fold = "";
      fold.value = "";
      updateDue();
    }
  });

  form.addEventListener("change", (event) => {
    if (!canInteract() || draft.payload || draft.pending) return;
    if (event.target.name) {
      const name = event.target.name === "due_fold" ? "fold" : event.target.name;
      if (event.target === personal) draft.personal = personal.checked;
      else if (event.target === multi) draft.multi = multi.checked;
      else if (event.target.name !== "assignee_multi") draft[name] = event.target.value;
    }
    if (event.target === personal) syncPersonal();
    if (event.target === multi) syncMulti();
  });

  if (draft.error) {
    const err = el("p", copy[draft.error] || draft.error);
    err.className = "notice";
    err.setAttribute("role", "alert");
    form.append(err);
  }

  if (draft.payload || draft.pending) {
    const frozen = el("p", copy.frozen);
    frozen.className = "notice";
    form.append(frozen);

    const closeBtn = el("button", copy.closeWithoutRollback);
    closeBtn.type = "button";
    closeBtn.addEventListener("click", () => {
      if (!isFormAttached(card, form) || card._writing || card._taskCreateDraft !== draft) return;
      card._form = null;
      card._taskCreateDraft = null;
      card.render();
    });
    form.append(closeBtn);
  }

  submit = el(
    "button",
    draft.payload || draft.pending
      ? copy.retry
      : draft.multi
      ? copy.reviewBatch
      : card.t.save
  );
  submit.type = "submit";
  submit.className = "primary";
  form.append(submit);

  for (const field of form.querySelectorAll("input,select,textarea")) {
    field.disabled = Boolean(card._writing || draft.payload || draft.pending);
  }
  syncPersonal();
  submit.disabled = Boolean(card._writing);

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!canInteract()) return;

    if (draft.multi) {
      if (!form.checkValidity()) return;
      const candidates = updateDue();
      if (due.value && !candidates.length) return;
      if (candidates.length > 1 && !["0", "1"].includes(fold.value)) {
        fold.reportValidity();
        return;
      }
      const steps = checklist.value.split(/\r?\n/).map((s) => s.trim()).filter(Boolean);
      if (steps.length > 50 || steps.some((s) => s.length > 200)) {
        checklist.setCustomValidity(card.t.failure);
        checklist.reportValidity();
        return;
      }
      checklist.setCustomValidity("");

      const eligible = getActiveNonguestMembers(card);
      const selected = eligible.filter((m) => (draft.selectedMembers || []).includes(m.id));
      if (selected.length < 1 || selected.length > 20) {
        draft.error = "memberCountError";
        card.render();
        return;
      }

      draft.title = title.value.trim();
      draft.checklist = checklist.value;
      draft.report_type = report.value;
      // The review must describe the DOM values used for the canonical deadline,
      // including autofill which need not have emitted an input/change event.
      draft.due_at = due.value;
      draft.fold = fold.value;
      draft.reviewedDueAt = due.value
        ? candidates.length === 1
          ? candidates[0]
          : candidates[Number(fold.value)]
        : "";
      for (const key of ["reminder_minutes", "grace_minutes", "penalty"]) {
        const input = form.elements.namedItem(key);
        if (input) draft[key] = input.value;
      }

      draft.reviewedMembers = deepFreeze(selected.map((m) => ({
        id: m.id,
        name: m.name,
        role: m.role,
        revision: m.revision,
        active: m.active,
      })));
      draft.stage = "review";
      draft.confirmed = false;
      draft.error = null;
      card.render();
      return;
    }

    if (!draft.pending) {
      if (!form.checkValidity()) return;
      const candidates = updateDue();
      if (due.value && !candidates.length) return;
      if (candidates.length > 1 && !["0", "1"].includes(fold.value)) {
        fold.reportValidity();
        return;
      }
      const selected = card._data.members.find(
        (m) => m.id === assignee.value && m.active && m.role !== "guest"
      );
      if (!selected || (!card.parent && selected.id !== actor)) return;
      if (!Number.isSafeInteger(selected.revision) || selected.revision < 1) return;

      const steps = checklist.value.split(/\r?\n/).map((s) => s.trim()).filter(Boolean);
      if (steps.length > 50 || steps.some((s) => s.length > 200)) {
        checklist.setCustomValidity(card.t.failure);
        checklist.reportValidity();
        return;
      }
      checklist.setCustomValidity("");

      const payload = {
        title: title.value.trim(),
        assignee: selected.id,
        assignee_revision: selected.revision,
        report_type: report.value,
        checklist: steps,
      };
      if (personal.checked) {
        if (selected.id !== actor) return;
        payload.personal = true;
      }
      if (due.value) {
        payload.due_at = candidates.length === 1 ? candidates[0] : candidates[Number(fold.value)];
      }
      for (const key of ["reminder_minutes", "grace_minutes", "penalty"]) {
        const input = form.elements.namedItem(key);
        if (input) payload[key] = Number(input.value);
      }

      const operationId = crypto.randomUUID();
      draft.reviewedMembers = deepFreeze([{
        id: selected.id, name: selected.name, role: selected.role,
        revision: selected.revision, active: selected.active,
      }]);
      draft.pending = deepFreeze({
        action: "tasks.create",
        payload,
        operation_id: operationId,
      });
      draft.payload = draft.pending.payload;
    }

    if (!checkReviewedMembers(card, draft.reviewedMembers)) {
      disposeTaskForm(card);
      card._form = null;
      card._actionError = "conflict";
      card.render();
      return;
    }
    const pending = draft.pending;
    await card.command(pending.action, pending.payload, pending.operation_id);

    if (card._generation !== generation) return;
    if (card._taskCreateDraft !== draft) return;
    if (!card._actionError) {
      card._taskCreateDraft = null;
    }
    card.render();
  });

  return form;
}
