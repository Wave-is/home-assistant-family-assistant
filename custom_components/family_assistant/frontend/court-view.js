/* Court view rendering and copy for Family Assistant card. All user content inserted via textContent only. */

export const COURT_COPY = {
  en: {
    title: "Rules & rewards",
    weekly_summary: "Weekly score summary",
    reports_title: "Previous weekly reports",
    no_reports: "No past reports recorded.",
    positives: "Positive",
    negatives: "Negative",
    total: "Total",
    reversed_count: "Reversed",
    no_summary: "No score activity this period.",
    ledger_title: "Score history",
    no_records: "No court records found.",
    award_title: "Award or deduct points",
    member: "Family member",
    points: "Points (-100 to 100, non-zero)",
    reason: "Reason",
    author: "Author",
    source: "Source",
    source_manual: "Manual",
    source_system: "Automatic system",
    source_alarm: "Wake-up alarm",
    source_task: "Task",
    reason_task_missed: "Task was not completed by its deadline",
    reason_alarm_missed: "Wake-up was not confirmed within 30 minutes",
    reason_record: "Penalty record",
    save: "Save",
    cancel: "Cancel",
    retry: "Retry",
    appeal: "Appeal",
    appeal_title: "Appeal score record",
    appeal_reason: "Reason for appeal",
    appeal_pending: "Appeal pending",
    appeal_resolved: "Appeal resolved",
    appeal_history: "Previous appeals",
    appeal_decision: "Decision",
    appeal_decision_uphold: "Uphold",
    appeal_decision_reverse: "Reverse",
    resolve_appeal: "Resolve appeal",
    resolve_appeal_title: "Resolve appeal",
    reverse: "Reverse",
    reverse_title: "Reverse active record",
    reversal_reason: "Reason for reversal",
    status_active: "Active",
    status_reversed: "Reversed",
    second_adult_review_notice: "Second adult review required: the original author and the appellant cannot resolve or reverse this appeal.",
    config_title: "Weekly report configuration",
    config_open: "Configure weekly reports",
    config_close: "Close settings",
    weekly_enabled: "Enable weekly reports (opt-in; does not reset balances)",
    weekday: "Summary weekday",
    time: "Summary time",
    second_adult_review: "Require independent second adult review for appeals",
    second_adult_review_help: "Requires at least 2 active parents or owners in the household.",
    opt_in_notice: "Weekly reports are immutable archives and never reset member point balances or issue automatic penalties.",
    unknown_member: "Unknown member",
    error_stale: "Data or permissions changed. Form closed.",
    error_points: "Points must be a non-zero integer between -100 and 100.",
    error_reason: "Reason is required.",
    weekday_0: "Monday",
    weekday_1: "Tuesday",
    weekday_2: "Wednesday",
    weekday_3: "Thursday",
    weekday_4: "Friday",
    weekday_5: "Saturday",
    weekday_6: "Sunday",
  },
  ru: {
    title: "Правила и поощрения",
    weekly_summary: "Итоги недели",
    reports_title: "Прошедшие еженедельные отчёты",
    no_reports: "Архив отчётов пуст.",
    positives: "Плюсы",
    negatives: "Минусы",
    total: "Итого",
    reversed_count: "Отменено",
    no_summary: "Нет начислений за этот период.",
    ledger_title: "История баллов",
    no_records: "Записей не найдено.",
    award_title: "Начислить или списать баллы",
    member: "Член семьи",
    points: "Баллы (целое от -100 до 100, кроме 0)",
    reason: "Причина",
    author: "Автор",
    source: "Источник",
    source_manual: "Вручную",
    source_system: "Система",
    source_alarm: "Будильник",
    source_task: "Задача",
    reason_task_missed: "Задача не выполнена к сроку",
    reason_alarm_missed: "Подъём не подтверждён за 30 минут",
    reason_record: "Штрафная запись",
    save: "Сохранить",
    cancel: "Отмена",
    retry: "Повторить",
    appeal: "Оспорить",
    appeal_title: "Оспорить начисление",
    appeal_reason: "Причина апелляции",
    appeal_pending: "На рассмотрении",
    appeal_resolved: "Рассмотрено",
    appeal_history: "Предыдущие апелляции",
    appeal_decision: "Решение",
    appeal_decision_uphold: "Оставить в силе",
    appeal_decision_reverse: "Отменить балл",
    resolve_appeal: "Рассмотреть апелляцию",
    resolve_appeal_title: "Рассмотреть апелляцию",
    reverse: "Отменить",
    reverse_title: "Отменить действующий балл",
    reversal_reason: "Причина отмены",
    status_active: "Действует",
    status_reversed: "Отменён",
    second_adult_review_notice: "Требуется проверка вторым родителем: автор записи и подавший апелляцию не могут её рассматривать или отменять.",
    config_title: "Настройка еженедельных отчётов",
    config_open: "Настроить отчёты",
    config_close: "Закрыть настройки",
    weekly_enabled: "Включить еженедельные отчёты (по выбору; балансы не сбрасываются)",
    weekday: "День недели отчёта",
    time: "Время формирования",
    second_adult_review: "Требовать проверку независимым вторым родителем",
    second_adult_review_help: "Требуется минимум 2 активных родителя или владельца в семье.",
    opt_in_notice: "Еженедельные отчёты сохраняются в архив и никогда не сбрасывают балансы баллов и не назначают штрафов.",
    unknown_member: "Неизвестный участник",
    error_stale: "Данные или права изменились. Форма закрыта.",
    error_points: "Баллы должны быть целым числом от -100 до 100, кроме нуля.",
    error_reason: "Укажите причину.",
    weekday_0: "Понедельник",
    weekday_1: "Вторник",
    weekday_2: "Среда",
    weekday_3: "Четверг",
    weekday_4: "Пятница",
    weekday_5: "Суббота",
    weekday_6: "Воскресенье",
  },
  uk: {
    title: "Правила та заохочення",
    weekly_summary: "Підсумки тижня",
    reports_title: "Минулі щотижневі звіти",
    no_reports: "Архів звітів порожній.",
    positives: "Плюси",
    negatives: "Мінуси",
    total: "Разом",
    reversed_count: "Скасовано",
    no_summary: "Немає нарахувань за цей період.",
    ledger_title: "Історія балів",
    no_records: "Записів не знайдено.",
    award_title: "Нарахувати або списати бали",
    member: "Член родини",
    points: "Бали (ціле від -100 до 100, крім 0)",
    reason: "Причина",
    author: "Автор",
    source: "Джерело",
    source_manual: "Вручну",
    source_system: "Система",
    source_alarm: "Будильник",
    source_task: "Завдання",
    reason_task_missed: "Завдання не виконано до терміну",
    reason_alarm_missed: "Підйом не підтверджено за 30 хвилин",
    reason_record: "Штрафний запис",
    save: "Зберегти",
    cancel: "Скасувати",
    retry: "Повторити",
    appeal: "Оскаржити",
    appeal_title: "Оскаржити нарахування",
    appeal_reason: "Причина оскарження",
    appeal_pending: "На розгляді",
    appeal_resolved: "Розглянуто",
    appeal_history: "Попередні апеляції",
    appeal_decision: "Рішення",
    appeal_decision_uphold: "Залишити в силі",
    appeal_decision_reverse: "Скасувати бал",
    resolve_appeal: "Розглянути апеляцію",
    resolve_appeal_title: "Розглянути апеляцію",
    reverse: "Скасувати",
    reverse_title: "Скасувати чинний бал",
    reversal_reason: "Причина скасування",
    status_active: "Діє",
    status_reversed: "Скасовано",
    second_adult_review_notice: "Потрібна перевірка іншим дорослим: автор запису та автор апеляції не можуть її розглядати або скасовувати.",
    config_title: "Налаштування щотижневих звітів",
    config_open: "Налаштувати звіти",
    config_close: "Закрити налаштування",
    weekly_enabled: "Увімкнути щотижневі звіти (за бажанням; баланси не скидаються)",
    weekday: "День тижня для звіту",
    time: "Час формування",
    second_adult_review: "Вимагати перевірку незалежним другим дорослим",
    second_adult_review_help: "Потрібно щонайменше 2 активних батьків або власників у родині.",
    opt_in_notice: "Щотижневі звіти зберігаються в архів і ніколи не скидають баланси балів та не призначають штрафів.",
    unknown_member: "Невідомий учасник",
    error_stale: "Дані або права змінилися. Форму закрито.",
    error_points: "Бали мають бути цілим числом від -100 до 100, крім нуля.",
    error_reason: "Вкажіть причину.",
    weekday_0: "Понеділок",
    weekday_1: "Вівторок",
    weekday_2: "Середа",
    weekday_3: "Четвер",
    weekday_4: "П'ятниця",
    weekday_5: "Субота",
    weekday_6: "Неділя",
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
  return COURT_COPY[lang] || COURT_COPY.en;
}

function getMemberName(card, id) {
  if (!id) return "";
  if (id === "system") return getCopy(card).source_system;
  const found = (card._data?.members || []).find(m => m && m.id === id);
  return found?.name || getCopy(card).unknown_member;
}

function getHouseholdZone(card) {
  return card._data?.settings?.timezone || card._hass?.config?.time_zone || "UTC";
}

function formatDateInZone(card, isoStr, zone) {
  if (!isoStr) return "";
  const lang = card._config?.language || card._hass?.language || "en";
  try { return new Date(isoStr).toLocaleString(lang, { timeZone: zone || "UTC" }); } catch { return isoStr; }
}

function getRecordReason(card, rec) {
  if (rec.reason) return rec.reason;
  const copy = getCopy(card);
  if (rec.reason_key && copy[`reason_${rec.reason_key}`]) {
    const ref = rec.reason_data?.task_id || rec.reason_data?.run_id;
    const task = (card._data?.tasks || []).find(item => item.id === rec.reason_data?.task_id);
    return [copy[`reason_${rec.reason_key}`], ref, task?.title].filter(Boolean).join(" · ");
  }
  return copy.reason_record;
}

function getSourceLabel(card, source) {
  const copy = getCopy(card);
  if (source === "alarm") return copy.source_alarm;
  if (source === "task") return copy.source_task;
  if (source === "manual") return copy.source_manual;
  if (source === "system") return copy.source_system;
  return source || copy.source_manual;
}

export function renderCourt(card, body) {
  if (!card || !body || !card._data) return;
  const copy = getCopy(card), data = card._data, role = data.role;
  const isGuest = role === "guest", isParent = Boolean(card.parent), isOwner = role === "owner";
  const actorId = data.actor, zone = getHouseholdZone(card), startGen = card._generation;

  const isStale = () => card._generation !== startGen || card._data?.role !== role || card._data?.actor !== actorId || getHouseholdZone(card) !== zone || !card._data?.settings?.modules?.includes("court");

  const runCmd = async (action, payload) => {
    if (isStale() || card._writing) return;
    try {
      await card.command(action, payload);
      if (card._generation === startGen) {
        if (!card._actionError) {
          if (action === "court.award") card._courtDraft = null;
          else if (action === "court.configure") { card._courtDraft = null; card._courtConfigOpen = false; }
          else card._courtAction = null;
        }
        card.render();
      }
    } catch {}
  };

  // 1. Weekly summary
  const summary = data.court_summary;
  if (summary) {
    const section = el("section", null, "item"), header = el("div");
    header.append(el("strong", copy.weekly_summary), el("div", `${formatDateInZone(card, summary.start, summary.timezone)} — ${formatDateInZone(card, summary.end, summary.timezone)} (${summary.timezone || zone})`, "sub"));
    section.append(header);
    const rows = summary.rows || [];
    if (!rows.length) section.append(el("div", copy.no_summary, "empty"));
    else {
      const ul = el("ul", null, "list");
      for (const r of rows) {
        const li = el("li", null, "item");
        li.append(el("strong", getMemberName(card, r.member)));
        li.append(el("div", `${copy.positives}: +${r.active_positives} · ${copy.negatives}: ${r.active_negatives} · ${copy.total}: ${r.total > 0 ? "+" : ""}${r.total} · ${copy.reversed_count}: ${r.reversed_count}`, "sub"));
        ul.append(li);
      }
      section.append(ul);
    }
    body.append(section);
  }

  // 2. Prior court reports (Parent view, immutable archives, each formatted using report.timezone)
  if (isParent && Array.isArray(data.court_reports) && data.court_reports.length > 0) {
    const details = el("details", null, "item");
    details.append(el("summary", `${copy.reports_title} (${data.court_reports.length})`));
    const repList = el("ul", null, "list");
    for (const report of data.court_reports.slice().reverse()) {
      const repItem = el("li", null, "item"), repHeader = el("div", null, "row"), repTz = report.timezone || "UTC";
      repHeader.append(el("strong", `${formatDateInZone(card, report.start, repTz)} — ${formatDateInZone(card, report.end, repTz)} (${repTz})`, "grow"));
      repItem.append(repHeader);
      const rRows = report.rows || [];
      if (rRows.length) {
        const rUl = el("ul", null, "list");
        for (const rr of rRows) {
          const rLi = el("li", null, "item");
          rLi.append(el("strong", getMemberName(card, rr.member)));
          rLi.append(el("div", `${copy.positives}: +${rr.active_positives} · ${copy.negatives}: ${rr.active_negatives} · ${copy.total}: ${rr.total > 0 ? "+" : ""}${rr.total} · ${copy.reversed_count}: ${rr.reversed_count}`, "sub"));
          rUl.append(rLi);
        }
        repItem.append(rUl);
      }
      repList.append(repItem);
    }
    details.append(repList);
    body.append(details);
  }

  // 3. Owner weekly configuration
  if (isOwner && data.court_config) {
    const wrap = el("div", null, "item");
    wrap.append(card.button(card._courtConfigOpen ? copy.config_close : copy.config_open, () => {
      if (isStale() || card._writing) return;
      card._courtConfigOpen = !card._courtConfigOpen;
      if (!card._courtConfigOpen) { card._courtDraft = null; card._actionError = null; }
      if (card._courtConfigOpen) {
        card._courtAction = null;
        if (card._courtDraft?.type === "award") card._courtDraft = null;
      }
      card.render();
    }));

    if (card._courtConfigOpen) {
      const cfg = data.court_config, form = el("form");
      const isFrozen = Boolean(card._courtDraft?.type === "config" && card._courtDraft?.frozenPayload);
      const draft = card._courtDraft?.type === "config" ? card._courtDraft : {
        type: "config", revision: cfg.revision ?? 0, weekly_enabled: Boolean(cfg.weekly_enabled), weekday: cfg.weekday ?? 0, time: cfg.time || "00:00", second_adult_review: Boolean(cfg.second_adult_review)
      };
      if (card._courtDraft?.type !== "config") card._courtDraft = draft;
      form.append(el("h3", copy.config_title), el("p", copy.opt_in_notice, "sub"));

      const enLabel = el("label", copy.weekly_enabled, "check"), enBox = el("input");
      enBox.type = "checkbox"; enBox.name = "weekly_enabled"; enBox.checked = draft.weekly_enabled; enBox.disabled = isFrozen || Boolean(card._writing);
      enLabel.prepend(enBox); form.append(enLabel);

      const wdLabel = el("label", copy.weekday), wdSelect = el("select");
      wdSelect.name = "weekday"; wdSelect.disabled = isFrozen || Boolean(card._writing);
      wdSelect.setAttribute("aria-label", copy.weekday);
      for (let i = 0; i <= 6; i++) {
        const opt = el("option", copy[`weekday_${i}`] || String(i)); opt.value = String(i); if (draft.weekday === i) opt.selected = true; wdSelect.append(opt);
      }
      wdLabel.append(wdSelect); form.append(wdLabel);

      const tInput = card.input(form, "time", copy.time, "time", draft.time);
      tInput.disabled = isFrozen || Boolean(card._writing);

      const sarLabel = el("label", copy.second_adult_review, "check"), sarBox = el("input");
      sarBox.type = "checkbox"; sarBox.name = "second_adult_review"; sarBox.checked = draft.second_adult_review; sarBox.disabled = isFrozen || Boolean(card._writing);
      sarLabel.prepend(sarBox); form.append(sarLabel, el("p", copy.second_adult_review_help, "sub"));

      const updateConfigDraft = () => {
        if (isFrozen || isStale() || card._writing) return;
        draft.weekly_enabled = enBox.checked; draft.weekday = Number(wdSelect.value); draft.time = tInput.value; draft.second_adult_review = sarBox.checked;
      };
      enBox.addEventListener("change", updateConfigDraft); wdSelect.addEventListener("change", updateConfigDraft);
      tInput.addEventListener("input", updateConfigDraft); sarBox.addEventListener("change", updateConfigDraft);

      const act = el("div", null, "actions"), saveBtn = card.button(card._actionError && isFrozen ? copy.retry : copy.save, () => {}, true);
      saveBtn.type = "submit"; act.append(saveBtn); form.append(act);

      form.addEventListener("submit", e => {
        e.preventDefault(); if (isStale() || card._writing) return;
        const currentCfg = card._data?.court_config;
        if (!currentCfg || card._data?.role !== "owner") { card._courtDraft = null; card._courtConfigOpen = false; card.render(); return; }
        if (isFrozen) { runCmd("court.configure", card._courtDraft.frozenPayload); return; }
        if (currentCfg.revision !== draft.revision) { card._actionError="conflict"; card.render(); return; }
        const payload = { revision: draft.revision, weekly_enabled: enBox.checked, weekday: Number(wdSelect.value), time: tInput.value, second_adult_review: sarBox.checked };
        card._courtDraft = { type: "config", frozenPayload: payload, ...payload };
        runCmd("court.configure", payload);
      });
      wrap.append(form);
    }
    body.append(wrap);
  }

  // 4. Parent award form
  if (isParent && !isGuest) {
    const wrap = el("div", null, "item"), isAwardOpen = card._courtDraft?.type === "award";
    wrap.append(card.button(isAwardOpen ? copy.cancel : copy.award_title, () => {
      if (isStale() || card._writing) return;
      if (isAwardOpen) { card._courtDraft = null; card._actionError = null; }
      else {
        card._courtAction = null; card._courtConfigOpen = false;
        card._courtDraft = { type: "award", member: "", points: 1, reason: "", frozenPayload: null };
        card._actionError = null;
      }
      card.render();
    }, !isAwardOpen));

    if (isAwardOpen) {
      const form = el("form"), draft = card._courtDraft, isFrozen = Boolean(draft.type === "award" && draft.frozenPayload);
      const mSelect = card.memberSelect(form);
      if (draft.member) mSelect.value = draft.member;
      mSelect.disabled = isFrozen || Boolean(card._writing);

      const ptsInput = card.input(form, "points", copy.points, "number", String(draft.points));
      ptsInput.min = "-100"; ptsInput.max = "100"; ptsInput.step = "1"; ptsInput.disabled = isFrozen || Boolean(card._writing);

      const rInput = card.input(form, "reason", copy.reason, "text", draft.reason);
      rInput.disabled = isFrozen || Boolean(card._writing);

      const updateAwardDraft = () => {
        if (isFrozen || isStale() || card._writing) return;
        draft.member = mSelect.value; draft.points = ptsInput.value; draft.reason = rInput.value;
      };
      mSelect.addEventListener("change", updateAwardDraft); ptsInput.addEventListener("input", updateAwardDraft); rInput.addEventListener("input", updateAwardDraft);

      const err = el("div", null, "notice"); err.style.display = "none"; form.append(err);
      const act = el("div", null, "actions"), subBtn = card.button(card._actionError && isFrozen ? copy.retry : copy.save, () => {}, true);
      subBtn.type = "submit"; act.append(subBtn); form.append(act);

      form.addEventListener("submit", e => {
        e.preventDefault(); if (isStale() || card._writing) return;
        if (!card.parent) { card._courtDraft = null; card.render(); return; }
        if (isFrozen) { runCmd("court.award", draft.frozenPayload); return; }
        const p = Number(ptsInput.value), r = rInput.value.trim();
        if (!Number.isInteger(p) || p === 0 || p < -100 || p > 100) { err.textContent = copy.error_points; err.style.display = "block"; return; }
        if (!r) { err.textContent = copy.error_reason; err.style.display = "block"; return; }
        if (!card._data.members.some(m=>m.id===mSelect.value && m.active && m.role!=="guest")) return;
        err.style.display = "none";
        const payload = { member: mSelect.value, points: p, reason: r };
        card._courtDraft = { type: "award", frozenPayload: payload, ...payload };
        runCmd("court.award", payload);
      });
      wrap.append(form);
    }
    body.append(wrap);
  }

  // 5. Ledger history
  const records = data.court || [], ledger = el("section", null, "item");
  ledger.dataset.courtLedger = "true";
  ledger.append(el("strong", `${copy.ledger_title} (${records.length})`));
  if (!records.length) ledger.append(el("div", copy.no_records, "empty"));
  else {
    const ul = el("ul", null, "list");
    for (const rec of records.slice().reverse()) {
      const li = el("li", null, "item"), mName = getMemberName(card, rec.member), aName = getMemberName(card, rec.actor);
      const sign = rec.points > 0 ? "+" : "", row = el("div", null, "row"), recReason = getRecordReason(card, rec);
      row.append(el("strong", `${rec.id}: ${mName} · ${sign}${rec.points} · ${recReason}`, "grow"), el("span", copy[`status_${rec.status}`] || rec.status, "badge"));
      li.append(row);

      const meta = el("div", null, "sub");
      meta.append(el("span", [`${copy.author}: ${aName}`, `${copy.source}: ${getSourceLabel(card, rec.source)}`, formatDateInZone(card, rec.created_at, zone)].join(" · ")));
      li.append(meta);

      if (rec.reversal) {
        li.append(el("div", `${copy.status_reversed}: ${getMemberName(card, rec.reversal.actor)} · ${formatDateInZone(card, rec.reversal.at, zone)} · ${rec.reversal.reason}`, "sub"));
      }

      const appeal = rec.appeal, isPending = appeal && (!appeal.status || appeal.status === "pending");
      if (rec.previous_appeals?.length) {
        const history=el("details"), list=el("ul");
        history.append(el("summary",`${copy.appeal_history} (${rec.previous_appeals.length})`));
        for (const prior of rec.previous_appeals) {
          list.append(el("li",`${getMemberName(card,prior.actor)} · ${formatDateInZone(card,prior.at,zone)} · ${prior.reason} — ${copy[`appeal_decision_${prior.decision}`] || copy.appeal_resolved}: ${getMemberName(card,prior.resolution?.actor)} · ${formatDateInZone(card,prior.resolution?.at,zone)} · ${prior.resolution?.reason || ""}`));
        }
        history.append(list);li.append(history);
      }
      if (appeal) {
        const apDiv = el("div", null, "sub"), apActor = getMemberName(card, appeal.actor);
        if (isPending) apDiv.append(el("span", `${copy.appeal_pending}: ${apActor} · ${formatDateInZone(card, appeal.at, zone)} · "${appeal.reason}"`, "badge"));
        else apDiv.append(el("span", `${copy.appeal_reason}: ${apActor} · ${formatDateInZone(card,appeal.at,zone)} · ${appeal.reason} — ${copy.appeal_resolved} (${copy[`appeal_decision_${appeal.decision}`] || appeal.decision}): ${getMemberName(card, appeal.resolution?.actor)} · ${formatDateInZone(card, appeal.resolution?.at, zone)} · ${appeal.resolution?.reason || ""}`));
        li.append(apDiv);
      }

      if (!isGuest) {
        const act = el("div", null, "actions"), curAct = card._courtAction, isCur = curAct && curAct.id === rec.id;
        const sar = Boolean(data.court_config?.second_adult_review);

        if (rec.status === "active" && !isPending && (isParent || rec.member === actorId) && !isCur) {
          act.append(card.button(copy.appeal, () => {
            if (isStale() || card._writing) return;
            card._courtDraft = null; card._courtConfigOpen = false;
            card._courtAction = { id: rec.id, revision: rec.revision, type: "appeal", reason: "", frozenPayload: null };
            card._actionError = null; card.render();
          }));
        }
        if (isParent && rec.status === "active" && !isPending && !isCur) {
          act.append(card.button(copy.reverse, () => {
            if (isStale() || card._writing) return;
            card._courtDraft = null; card._courtConfigOpen = false;
            card._courtAction = { id: rec.id, revision: rec.revision, type: "reverse", reason: "", frozenPayload: null };
            card._actionError = null; card.render();
          }));
        }
        if (isParent && rec.status === "active" && isPending) {
          if (sar && (actorId === rec.actor || actorId === appeal.actor)) {
            act.append(el("div", copy.second_adult_review_notice, "notice"));
          } else if (!isCur) {
            act.append(card.button(copy.resolve_appeal, () => {
              if (isStale() || card._writing) return;
              card._courtDraft = null; card._courtConfigOpen = false;
              card._courtAction = { id: rec.id, revision: rec.revision, type: "resolve_appeal", decision: "reverse", reason: "", frozenPayload: null };
              card._actionError = null; card.render();
            }, true));
          }
        }
        if (act.children.length) li.append(act);

        if (isCur) {
          const form = el("form"), isFrozen = Boolean(curAct.frozenPayload);
          if (curAct.revision !== rec.revision) {
            form.append(el("div", copy.error_stale, "notice"), card.button(copy.cancel, () => { card._courtAction = null; card.render(); }));
            li.append(form); ul.append(li); continue;
          }

          let decSel = null;
          if (curAct.type === "appeal") form.append(el("strong", copy.appeal_title));
          else if (curAct.type === "reverse") form.append(el("strong", copy.reverse_title));
          else if (curAct.type === "resolve_appeal") {
            form.append(el("strong", copy.resolve_appeal_title));
            const dl = el("label", copy.appeal_decision); decSel = el("select"); decSel.name = "decision"; decSel.disabled = isFrozen || Boolean(card._writing);
            decSel.setAttribute("aria-label", copy.appeal_decision);
            const oRev = el("option", copy.appeal_decision_reverse), oUph = el("option", copy.appeal_decision_uphold);
            oRev.value = "reverse"; oUph.value = "uphold"; decSel.append(oRev, oUph); decSel.value = curAct.decision || "reverse";
            dl.append(decSel); form.append(dl);
            decSel.addEventListener("change", () => {
              if (isFrozen || isStale() || card._writing) return;
              curAct.decision = decSel.value;
            });
          }

          const rLbl = curAct.type === "appeal" ? copy.appeal_reason : curAct.type === "reverse" ? copy.reversal_reason : copy.reason;
          const rInp = card.input(form, "reason", rLbl, "text", curAct.reason || "");
          rInp.disabled = isFrozen || Boolean(card._writing);
          rInp.addEventListener("input", () => {
            if (isFrozen || isStale() || card._writing) return;
            curAct.reason = rInp.value;
          });

          const fAct = el("div", null, "actions"), btnTxt = card._actionError && isFrozen ? copy.retry : curAct.type === "reverse" ? copy.reverse : copy.save;
          const sBtn = card.button(btnTxt, () => {}, true); sBtn.type = "submit";
          fAct.append(sBtn, card.button(copy.cancel, () => { card._courtAction = null; card._actionError = null; card.render(); }));
          form.append(fAct);

          form.addEventListener("submit", e => {
            e.preventDefault(); if (isStale() || card._writing) return;
            const liveRec = card._data?.court?.find(r => r.id === rec.id);
            if (!liveRec || liveRec.revision !== curAct.revision || liveRec.status !== "active") {
              card._courtAction = null; card.render(); return;
            }
            const liveSar = Boolean(card._data?.court_config?.second_adult_review), liveRole = card._data?.role, liveActor = card._data?.actor;
            const liveParent = ["owner", "parent"].includes(liveRole);
            if (curAct.type === "appeal") {
              if (liveRec.appeal && (!liveRec.appeal.status || liveRec.appeal.status === "pending")) return;
              if (!liveParent && liveRec.member !== liveActor) { card._courtAction = null; card.render(); return; }
            } else if (curAct.type === "reverse" || curAct.type === "resolve_appeal") {
              if (!liveParent) { card._courtAction = null; card.render(); return; }
              const liveAppeal = liveRec.appeal, livePending = liveAppeal && (!liveAppeal.status || liveAppeal.status === "pending");
              if (curAct.type === "resolve_appeal" && !livePending) { card._courtAction = null; card.render(); return; }
              if (livePending && liveSar && (liveActor === liveRec.actor || liveActor === liveAppeal.actor)) { card._courtAction = null; card.render(); return; }
            }
            const actionName = curAct.type === "appeal" ? "court.appeal" : curAct.type === "reverse" ? "court.reverse" : "court.resolve_appeal";
            if (isFrozen) { runCmd(actionName, curAct.frozenPayload); return; }
            const v = rInp.value.trim(); if (!v) return;
            const payload = { id: liveRec.id, revision: liveRec.revision, reason: v, ...(decSel ? { decision: decSel.value } : {}) };
            curAct.reason=v;if(decSel)curAct.decision=decSel.value;
            curAct.frozenPayload = payload;
            runCmd(actionName, payload);
          });
          li.append(form);
        }
      }
      ul.append(li);
    }
    ledger.append(ul);
  }
  body.append(ledger);
}
