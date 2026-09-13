/* Explicit consent for ordinary one-off child-task settlement only. */
export const SETTLEMENT_COPY = {
  en: {
    title: "Daily missed-task settlement (optional)",
    hint: "Only one-off child tasks with a deadline. Not personal, recurring, school or maintenance work. Old missed days are skipped without penalties after an outage. Identity, deadline or module changes require a fresh policy review.",
    daily_rollover: "Move an unfinished task to the next day",
    settle_time: "Settle no earlier than (household time)",
    repeat_penalty: "Allow the configured penalty again on later missed days (subject to the global switch and daily cap)",
    same_day_correction: "Reverse only this task's exact penalty when a parent confirms completion on the settlement day",
    review: "Review and reauthorize this policy", corrected: "Correct this task's exact same-day penalty",
    reason: "Parent independently reviewed this task's same-day penalty", needs_review: "Task completed; its exact penalty still needs parent review.",
    receipt: "Last settlement", active: "Active", revoked: "Revoked — review required", disabled: "Off",
    settlement_capacity: "Daily rollover paused: all 366 audit slots are used. History is preserved; no further rollover or penalty. Parent review is required.",
    applied: "Penalty recorded", skipped_outage: "Older day skipped; no penalty", skipped_retroactive: "Pre-policy deadline; no penalty", skipped_disabled: "Automatic penalties or Court off; no penalty", skipped_zero: "No penalty configured", skipped_duplicate: "Already assessed; no duplicate penalty", skipped_cap: "Daily cap reached; no penalty",
  },
  ru: {
    title: "Ежедневный перенос невыполненной задачи (необязательно)",
    hint: "Только разовая задача ребёнка со сроком. Не личные напоминания, серии, школа или обслуживание. После простоя старые дни пропускаются без штрафов. Изменение личности, срока или модулей требует новой проверки политики.",
    daily_rollover: "Переносить невыполненную задачу на следующий день",
    settle_time: "Подводить итог не раньше (время семьи)",
    repeat_penalty: "Разрешить настроенный штраф повторно за последующие пропущенные дни (с общим выключателем и дневным лимитом)",
    same_day_correction: "Отменять только точный штраф этой задачи, если родитель подтвердил выполнение в день начисления",
    review: "Проверить и заново разрешить политику", corrected: "Исправить точный штраф этой задачи за день выполнения",
    reason: "Родитель независимо проверил точный штраф задачи за день выполнения", needs_review: "Задача выполнена; её точный штраф ещё требует проверки родителем.",
    receipt: "Последний перенос", active: "Включено", revoked: "Отозвано — нужна проверка", disabled: "Выключено",
    settlement_capacity: "Ежедневный перенос остановлен: заполнены все 366 записей журнала. История сохранена; новых переносов и штрафов нет. Нужна проверка родителя.",
    applied: "Штраф начислен", skipped_outage: "Старый день пропущен без штрафа", skipped_retroactive: "Срок до включения политики; без штрафа", skipped_disabled: "Автоштрафы или Суд выключены; без штрафа", skipped_zero: "Штраф не настроен", skipped_duplicate: "Уже учтено; без повторного штрафа", skipped_cap: "Дневной лимит достигнут; без штрафа",
  },
  uk: {
    title: "Щоденне перенесення невиконаного завдання (необов’язково)",
    hint: "Лише разове завдання дитини з терміном. Не особисті нагадування, серії, школа чи обслуговування. Після простою старі дні пропускаються без штрафів. Зміна особи, терміну чи модулів потребує нової перевірки політики.",
    daily_rollover: "Переносити невиконане завдання на наступний день",
    settle_time: "Підбивати підсумок не раніше (час родини)",
    repeat_penalty: "Дозволити налаштований штраф повторно за наступні пропущені дні (із загальним вимикачем і денним лімітом)",
    same_day_correction: "Скасовувати лише точний штраф цього завдання, якщо батьки підтвердили виконання в день нарахування",
    review: "Перевірити й повторно дозволити політику", corrected: "Виправити точний штраф цього завдання за день виконання",
    reason: "Батьки незалежно перевірили точний штраф завдання за день виконання", needs_review: "Завдання виконано; його точний штраф ще потребує перевірки батьками.",
    receipt: "Останнє перенесення", active: "Увімкнено", revoked: "Відкликано — потрібна перевірка", disabled: "Вимкнено",
    settlement_capacity: "Щоденне перенесення зупинено: заповнено всі 366 записів журналу. Історію збережено; нових перенесень і штрафів немає. Потрібна перевірка батьків.",
    applied: "Штраф нараховано", skipped_outage: "Старий день пропущено без штрафу", skipped_retroactive: "Термін до ввімкнення політики; без штрафу", skipped_disabled: "Автоштрафи або Суд вимкнено; без штрафу", skipped_zero: "Штраф не налаштовано", skipped_duplicate: "Уже враховано; без повторного штрафу", skipped_cap: "Денний ліміт досягнуто; без штрафу",
  },
};

export const defaultMissedPolicy = () => ({daily_rollover: false, settle_time: "20:00", repeat_penalty: false, same_day_correction: false});
export const settlementCopy = card => SETTLEMENT_COPY[card._config?.language || card._hass?.language?.split("-")[0]] || SETTLEMENT_COPY.en;
export const settlementActorRevision = card => card._data.members.find(m => m.id === card._data.actor)?.revision;
export const settlementSupported = (card, item) => card.parent && !item.delivery_scope && !item.source && !item.series_id && !item.occurrence_id && item.managed_by !== "school" && card._data.members.some(m => m.id === item.assignee && m.active && m.role === "child");

export function settlementControls(card, el, container, initial, onChange) {
  const copy = settlementCopy(card);
  const policy = {...defaultMissedPolicy(), ...initial};
  const fieldset = el("fieldset");
  fieldset.dataset.taskSettlement = "true";
  fieldset.append(el("legend", copy.title), el("p", copy.hint));
  const inputs = {};
  for (const key of Object.keys(policy)) {
    const label = el("label", copy[key]);
    const input = el("input");
    input.name = `missed_${key}`;
    input.type = key === "settle_time" ? "time" : "checkbox";
    if (input.type === "checkbox") input.checked = policy[key];
    else input.value = policy[key];
    label.append(input);
    fieldset.append(label);
    inputs[key] = input;
  }
  const read = () => Object.fromEntries(Object.entries(inputs).map(([key, input]) => [key, input.type === "checkbox" ? input.checked : input.value]));
  const sync = () => {
    if (!inputs.daily_rollover.checked) {
      inputs.repeat_penalty.checked = false;
      inputs.same_day_correction.checked = false;
    }
    for (const key of ["settle_time", "repeat_penalty", "same_day_correction"]) inputs[key].disabled = !inputs.daily_rollover.checked;
    inputs.settle_time.required = inputs.daily_rollover.checked;
  };
  for (const input of Object.values(inputs)) input.addEventListener("change", () => {
    if (fieldset.disabled || card._writing) return;
    sync();
    onChange(read());
  });
  sync();
  container.append(fieldset);
  return {fieldset, read, available(value) { sync(); fieldset.disabled = !value; }, sync};
}
