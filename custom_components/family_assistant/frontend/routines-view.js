/* Routines view rendering and copy for Family Assistant card. All user content inserted via textContent only. */

import { makeRecurrenceDraft, recurrencePayload, renderRecurrence } from "./recurrence-form.js";
import { wallTime } from "./local-time.js";
import { renderConditionForm } from "./condition-form.js";
import { normalizeCondition } from "./condition-validation.js";

export const ROUTINES_COPY = {
  en: {
    condition_error: "Check the skip condition, approved entities, and time window.",
    step_assignee: "Who completes this step",
    inherit_assignee: "The member running this routine",
    handoff_notice: "Each step goes to its assigned member in private. Everyone assigned to this run can see its steps; only the current step’s assignee can confirm it. Parents can override with a reason.",
    recurrence_error: "Check the recurrence settings and dates.",
    title: "Family routines",
    templates_title: "Routine templates",
    no_templates: "No routine templates configured.",
    active_runs_title: "Active routine runs",
    no_active_runs: "No active routine runs.",
    completed_runs_title: "Completed & past runs",
    no_completed_runs: "No completed routine runs.",
    new_template: "New routine",
    edit_template: "Edit routine",
    start_routine: "Start routine",
    start_for: "Assignee for this run",
    start_button: "Start",
    preset_picker: "Load from preset (optional)",
    preset_none: "— Blank routine —",
    template_title: "Title",
    template_description: "Description",
    template_enabled: "Routine enabled",
    template_assignees: "Assigned family members",
    steps_title: "Steps (ordered)",
    step_num: "Step",
    step_title: "Step title",
    step_offset: "Offset (minutes from start, 0..10080)",
    step_confirmation: "Completion mode",
    confirmation_manual: "Manual confirmation (user button)",
    confirmation_none: "Automatic progression",
    confirmation_entity_state: "Automatic when condition is true",
    step_escalate: "Escalate if overdue (minutes, 1..1440, optional)",
    step_skip_mode: "Skip this step during mode",
    step_entity_condition: "Target entity state condition",
    condition_entity_id: "Observed entity ID",
    condition_expected_state: "Expected state value",
    condition_max_age: "Max age (seconds, 1..3600)",
    complex_preserved_notice: "Advanced condition rules are preserved. Changing simple controls will replace them.",
    replace_condition: "Replace with simple condition",
    step_skip_editor: "Advanced skip condition",
    step_completion_editor: "Automatic completion condition",
    completion_inactive_notice:
      "The completion condition remains in this draft, but saving manual or immediate completion will remove it from the template.",
    add_step: "Add step",
    remove_step: "Remove",
    move_up: "Up",
    move_down: "Down",
    save: "Save",
    cancel: "Cancel",
    retry: "Retry",
    edit: "Edit",
    confirm_step: "Mark step done",
    parent_override: "Parent override",
    override_completed: "Mark completed",
    override_skipped: "Mark skipped",
    cancel_run: "Cancel run",
    reason: "Reason",
    reason_required: "Reason is required.",
    title_required: "Title is required.",
    steps_required: "At least one step is required.",
    steps_max_exceeded: "Routines can have at most 30 steps.",
    assignees_required: "Select at least one assigned member.",
    assignees_max_exceeded: "Routines can have at most 20 assigned members.",
    step_order_descending: "Step offsets must be non-decreasing (cannot occur earlier than previous step).",
    invalid_offset: "Step offset must be an integer between 0 and 10080 minutes.",
    invalid_escalate: "Escalation must be an integer between 1 and 1440 minutes.",
    invalid_max_age: "Condition max age must be an integer between 1 and 3600 seconds.",
    invalid_entity_id: "Entity ID must be in domain.object format and in the observation allowlist.",
    invalid_state: "State condition cannot be empty, unknown, or unavailable.",
    allowlist_title: "Entity observation allowlist",
    allowlist_notice: "Notice: Only entities in this allowlist can be observed by routine conditions. Conditions only observe states and never operate or control devices.",
    allowlist_edit: "Edit allowlist",
    allowlist_placeholder: "domain.entity_id (one per line, lowercase)",
    allowlist_invalid: "Each entity ID must be a lowercase domain.object format, up to 255 characters.",
    allowlist_duplicate: "Allowlist cannot contain duplicate entity IDs.",
    allowlist_max_exceeded: "Allowlist can contain at most 50 entities.",
    modes_title: "Household routine modes",
    modes_notice: "Household modes affect condition evaluation. Normal is exclusive; other modes can be combined.",
    modes_edit: "Update modes",
    mode_normal: "Normal (exclusive)",
    mode_holidays: "Holidays",
    mode_guests: "Guests",
    mode_ill: "Illness",
    mode_vacation: "Vacation",
    history: "History",
    status_pending: "Pending",
    status_active: "Active",
    status_completed: "Completed",
    status_skipped: "Skipped",
    status_cancelled: "Cancelled",
    unknown_member: "Unknown member",
    system_actor: "System",
    step_status: "Step status",
    member: "Member",
    started: "Started",
    planned: "Planned",
    none: "None",
    child_start_notice: "You can start routines assigned to you.",
    stale_error: "Data changed elsewhere. Action cancelled.",
    conflict_error: "Conflict: revision mismatch. Form closed.",
    action_saved: "Saved",
    action_started: "Started",
    action_step_activated: "Step activated",
    action_step_completed: "Step completed",
    action_step_skipped: "Step skipped",
    action_step_escalated: "Step escalated",
    action_completed: "Routine completed",
    action_skipped: "Routine skipped",
    action_cancelled: "Routine cancelled",
    reason_condition: "Condition met",
    reason_automatic: "Automatic",
    reason_confirmation: "Confirmed by user",
    reason_authorization_removed: "Authorization removed",
  },
  ru: {
    condition_error: "Проверьте условие пропуска, разрешённые объекты и временной интервал.",
    step_assignee: "Кто выполняет этот шаг",
    inherit_assignee: "Участник, для которого запущен распорядок",
    handoff_notice: "Каждый шаг приходит исполнителю в личку. Участники выполнения видят его шаги; подтвердить текущий шаг может только его исполнитель. Родитель может переопределить результат с причиной.",
    recurrence_error: "Проверьте настройки повторения и даты.",
    title: "Семейные распорядки",
    templates_title: "Шаблоны распорядков",
    no_templates: "Шаблоны распорядков не настроены.",
    active_runs_title: "Активные выполнения",
    no_active_runs: "Нет активных выполнений распорядков.",
    completed_runs_title: "Завершённые и прошлые выполнения",
    no_completed_runs: "Нет завершённых выполнений.",
    new_template: "Новый распорядок",
    edit_template: "Изменить распорядок",
    start_routine: "Запустить распорядок",
    start_for: "Исполнитель этого запуска",
    start_button: "Запустить",
    preset_picker: "Загрузить из готового шаблона (необязательно)",
    preset_none: "— Пустой распорядок —",
    template_title: "Название",
    template_description: "Описание",
    template_enabled: "Распорядок включён",
    template_assignees: "Назначенные члены семьи",
    steps_title: "Шаги (по порядку)",
    step_num: "Шаг",
    step_title: "Название шага",
    step_offset: "Смещение от начала (минут, 0..10080)",
    step_confirmation: "Способ подтверждения",
    confirmation_manual: "Вручную (кнопка участника)",
    confirmation_none: "Автоматический переход",
    confirmation_entity_state: "Автоматически, когда условие истинно",
    step_escalate: "Эскалация при просрочке (минут, 1..1440, необязательно)",
    step_skip_mode: "Пропускать шаг в режиме",
    step_entity_condition: "Условие по состоянию объекта",
    condition_entity_id: "ID наблюдаемого объекта",
    condition_expected_state: "Ожидаемое состояние",
    condition_max_age: "Макс. давность (секунд, 1..3600)",
    complex_preserved_notice: "Сохранены расширенные правила условий. Изменение параметров заменит их.",
    replace_condition: "Заменить простым условием",
    step_skip_editor: "Расширенное условие пропуска",
    step_completion_editor: "Условие автоматического завершения",
    completion_inactive_notice:
      "Условие завершения сохранено в этом черновике, но сохранение ручного или немедленного завершения удалит его из шаблона.",
    add_step: "Добавить шаг",
    remove_step: "Удалить",
    move_up: "Выше",
    move_down: "Ниже",
    save: "Сохранить",
    cancel: "Отмена",
    retry: "Повторить",
    edit: "Изменить",
    confirm_step: "Отметить выполнение шага",
    parent_override: "Решение родителя",
    override_completed: "Отметить выполненным",
    override_skipped: "Отметить пропущенным",
    cancel_run: "Отменить запуск",
    reason: "Причина",
    reason_required: "Укажите причину.",
    title_required: "Укажите название.",
    steps_required: "Нужен хотя бы один шаг.",
    steps_max_exceeded: "В распорядке может быть не более 30 шагов.",
    assignees_required: "Выберите хотя бы одного исполнителя.",
    assignees_max_exceeded: "В распорядке может быть не более 20 исполнителей.",
    step_order_descending: "Смещение шагов не может уменьшаться (шаг не может начинаться раньше предыдущего).",
    invalid_offset: "Смещение шага должно быть целым числом от 0 до 10080 минут.",
    invalid_escalate: "Эскалация должна быть целым числом от 1 до 1440 минут.",
    invalid_max_age: "Максимальная давность должна быть целым числом от 1 до 3600 секунд.",
    invalid_entity_id: "ID объекта должен быть в формате domain.object и входить в разрешённый список.",
    invalid_state: "Состояние не может быть пустым, unknown или unavailable.",
    allowlist_title: "Список разрешённых объектов",
    allowlist_notice: "Уведомление: Условия распорядков могут только наблюдать за объектами из этого списка. Условия никогда не управляют устройствами.",
    allowlist_edit: "Изменить список",
    allowlist_placeholder: "domain.entity_id (по одному на строку, строчные буквы)",
    allowlist_invalid: "Каждый ID объекта должен быть строчным в формате domain.object до 255 символов.",
    allowlist_duplicate: "Список разрешённых объектов не должен содержать дубликатов.",
    allowlist_max_exceeded: "В списке может быть не более 50 объектов.",
    modes_title: "Режимы дома для распорядков",
    modes_notice: "Режимы дома влияют на условия шагов. Обычный режим является исключительным; остальные режимы можно совмещать.",
    modes_edit: "Изменить режимы",
    mode_normal: "Обычный (исключительный)",
    mode_holidays: "Каникулы / праздники",
    mode_guests: "Гости",
    mode_ill: "Болезнь",
    mode_vacation: "Отпуск",
    history: "История",
    status_pending: "Ожидает",
    status_active: "Активно",
    status_completed: "Выполнено",
    status_skipped: "Пропущено",
    status_cancelled: "Отменено",
    unknown_member: "Неизвестный участник",
    system_actor: "Система",
    step_status: "Статус шага",
    member: "Участник",
    started: "Запущен",
    planned: "Запланирован",
    none: "Нет",
    child_start_notice: "Вы можете запускать назначенные вам распорядки.",
    stale_error: "Данные изменились. Действие отменено.",
    conflict_error: "Конфликт: несоответствие ревизии. Форма закрыта.",
    action_saved: "Сохранено",
    action_started: "Запущено",
    action_step_activated: "Шаг активирован",
    action_step_completed: "Шаг выполнен",
    action_step_skipped: "Шаг пропущен",
    action_step_escalated: "Эскалация шага",
    action_completed: "Распорядок завершён",
    action_skipped: "Распорядок пропущен",
    action_cancelled: "Распорядок отменён",
    reason_condition: "По условию",
    reason_automatic: "Автоматически",
    reason_confirmation: "Подтверждено участником",
    reason_authorization_removed: "Отозваны права",
  },
  uk: {
    condition_error: "Перевірте умову пропуску, дозволені об’єкти й часовий інтервал.",
    step_assignee: "Хто виконує цей крок",
    inherit_assignee: "Учасник, для якого запущено розпорядок",
    handoff_notice: "Кожен крок надходить виконавцю в особистий чат. Учасники виконання бачать його кроки; підтвердити поточний крок може лише його виконавець. Батьки можуть змінити результат із причиною.",
    recurrence_error: "Перевірте налаштування повторення та дати.",
    title: "Сімейні розпорядки",
    templates_title: "Шаблони розпорядків",
    no_templates: "Шаблони розпорядків не налаштовані.",
    active_runs_title: "Активні виконання",
    no_active_runs: "Немає активних виконань розпорядків.",
    completed_runs_title: "Завершені та минулі виконання",
    no_completed_runs: "Немає завершених виконань.",
    new_template: "Новий розпорядок",
    edit_template: "Редагувати розпорядок",
    start_routine: "Запустити розпорядок",
    start_for: "Виконавець цього запуску",
    start_button: "Запустити",
    preset_picker: "Завантажити з готового шаблону (необов'язково)",
    preset_none: "— Порожній розпорядок —",
    template_title: "Назва",
    template_description: "Опис",
    template_enabled: "Розпорядок увімкнено",
    template_assignees: "Призначені члени родини",
    steps_title: "Кроки (за порядком)",
    step_num: "Крок",
    step_title: "Назва кроку",
    step_offset: "Зсув від початку (хвилин, 0..10080)",
    step_confirmation: "Спосіб підтвердження",
    confirmation_manual: "Вручну (кнопка учасника)",
    confirmation_none: "Автоматичний перехід",
    confirmation_entity_state: "Автоматично, коли умова істинна",
    step_escalate: "Ескалація у разі затримки (хвилин, 1..1440, необов'язково)",
    step_skip_mode: "Пропускати крок у режимі",
    step_entity_condition: "Умова за станом об'єкта",
    condition_entity_id: "ID спостережуваного об'єкта",
    condition_expected_state: "Очікуваний стан",
    condition_max_age: "Макс. давність (секунд, 1..3600)",
    complex_preserved_notice: "Збережено розширені правила умов. Зміна параметрів замінить їх.",
    replace_condition: "Замінити простою умовою",
    step_skip_editor: "Розширена умова пропуску",
    step_completion_editor: "Умова автоматичного завершення",
    completion_inactive_notice:
      "Умова завершення збережена в цій чернетці, але збереження ручного або негайного завершення видалить її з шаблону.",
    add_step: "Додати крок",
    remove_step: "Видалити",
    move_up: "Вище",
    move_down: "Нижче",
    save: "Зберегти",
    cancel: "Скасувати",
    retry: "Повторити",
    edit: "Редагувати",
    confirm_step: "Позначити виконання кроку",
    parent_override: "Рішення батьків",
    override_completed: "Позначити виконаним",
    override_skipped: "Позначити пропущеним",
    cancel_run: "Скасувати запуск",
    reason: "Причина",
    reason_required: "Вкажіть причину.",
    title_required: "Вкажіть назву.",
    steps_required: "Потрібен щонайменше один крок.",
    steps_max_exceeded: "У розпорядку може бути не більше 30 кроків.",
    assignees_required: "Виберіть щонайменше одного виконавця.",
    assignees_max_exceeded: "У розпорядку може бути не більше 20 виконавців.",
    step_order_descending: "Зсув кроків не може зменшуватися (крок не може починатися раніше попереднього).",
    invalid_offset: "Зсув кроку має бути цілим числом від 0 до 10080 хвилин.",
    invalid_escalate: "Ескалація має бути цілим числом від 1 до 1440 хвилин.",
    invalid_max_age: "Максимальна давність має бути цілим числом від 1 до 3600 секунд.",
    invalid_entity_id: "ID об'єкта має бути у форматі domain.object та входити до дозволеного списку.",
    invalid_state: "Стан не може бути порожнім, unknown або unavailable.",
    allowlist_title: "Список дозволених об'єктів",
    allowlist_notice: "Повідомлення: Умови розпорядків можуть лише спостерігати за об'єктами з цього списку. Умови ніколи не керують пристроями.",
    allowlist_edit: "Редагувати список",
    allowlist_placeholder: "domain.entity_id (по одному на рядок, малі літери)",
    allowlist_invalid: "Кожен ID об'єкта має бути малими літерами у форматі domain.object до 255 символів.",
    allowlist_duplicate: "Список дозволених об'єктів не повинен містити дублікатів.",
    allowlist_max_exceeded: "У списку може бути не більше 50 об'єктів.",
    modes_title: "Режими дому для розпорядків",
    modes_notice: "Режими дому впливають на умови кроків. Звичайний режим є виключним; решту режимів можна поєднувати.",
    modes_edit: "Змінити режими",
    mode_normal: "Звичайний (виключний)",
    mode_holidays: "Канікули / свята",
    mode_guests: "Гості",
    mode_ill: "Хвороба",
    mode_vacation: "Відпустка",
    history: "Історія",
    status_pending: "Очікує",
    status_active: "Активно",
    status_completed: "Виконано",
    status_skipped: "Пропущено",
    status_cancelled: "Скасовано",
    unknown_member: "Невідомий учасник",
    system_actor: "Система",
    step_status: "Статус кроку",
    member: "Учасник",
    started: "Запущено",
    planned: "Заплановано",
    none: "Немає",
    child_start_notice: "Ви можете запускати призначені вам розпорядки.",
    stale_error: "Дані змінилися. Дію скасовано.",
    conflict_error: "Конфлікт: невідповідність ревізії. Форму закрито.",
    action_saved: "Збережено",
    action_started: "Запущено",
    action_step_activated: "Крок активовано",
    action_step_completed: "Крок виконано",
    action_step_skipped: "Крок пропущено",
    action_step_escalated: "Ескалація кроку",
    action_completed: "Розпорядок завершено",
    action_skipped: "Розпорядок пропущено",
    action_cancelled: "Розпорядок скасовано",
    reason_condition: "За умовою",
    reason_automatic: "Автоматично",
    reason_confirmation: "Підтверджено учасником",
    reason_authorization_removed: "Відкликано права",
  },
};

const ALL_MODES = ["normal", "holidays", "guests", "ill", "vacation"];
const ENTITY_REGEX = /^[a-z0-9_]+\.[a-z0-9_]+$/;

function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = String(text);
  if (className) node.className = className;
  return node;
}

function getCopy(card) {
  const lang = card._config?.language || card._hass?.language?.split("-")[0] || "en";
  return ROUTINES_COPY[lang] || ROUTINES_COPY.en;
}

function getMemberName(card, id) {
  if (!id) return "";
  if (id === "system") return getCopy(card).system_actor;
  const found = (card._data?.members || []).find((m) => m && m.id === id);
  return found?.name || getCopy(card).unknown_member;
}

function formatDate(card, isoStr) {
  if (!isoStr) return "";
  const lang = card._config?.language || card._hass?.language || "en";
  const tz = card._data?.settings?.timezone || card._hass?.config?.time_zone || "UTC";
  try {
    return new Date(isoStr).toLocaleString(lang, { timeZone: tz });
  } catch {
    return isoStr;
  }
}

function clone(val) {
  return val === undefined ? undefined : JSON.parse(JSON.stringify(val));
}

function makeDefaultStep(offset = 0) {
  return {
    assignee: null,
    title: "",
    raw_offset: String(offset),
    confirmation: "manual",
    raw_escalate: "15",
    skip_when: null,
    skip_dirty: false,
    completion_condition: null,
    completion_dirty: false,
  };
}

function buildStepFromData(s) {
  return {
    assignee: s.assignee || null,
    title: s.title || "",
    raw_offset: s.offset_minutes != null ? String(s.offset_minutes) : "0",
    confirmation: s.confirmation || "manual",
    raw_escalate: s.escalate_minutes != null ? String(s.escalate_minutes) : "",
    skip_when: s.skip_when ? clone(s.skip_when) : null,
    skip_dirty: false,
    completion_condition: s.completion_condition ? clone(s.completion_condition) : null,
    completion_dirty: false,
  };
}

function conditionHasEntity(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  if (value.kind === "entity_state") return true;
  return (
    (value.kind === "all" || value.kind === "any") &&
    Array.isArray(value.conditions) &&
    value.conditions.some(conditionHasEntity)
  );
}

function conditionForSave(value, dirty, allowlist) {
  try {
    return { value: normalizeCondition(value, { allowlist }), supported: true };
  } catch (error) {
    // Preserve a future backend condition byte-for-byte until the user chooses
    // replacement. Current allowlist revocation remains a local hard stop.
    if (!dirty && error?.code === "invalid_field") {
      return { value: clone(value), supported: false };
    }
    throw error;
  }
}

function routineAccess(card, data = card?._data) {
  const members = Array.isArray(data?.members) ? data.members : [];
  const actor = members.find((member) => member?.id === data?.actor);
  const validRevision = (value) => Number.isSafeInteger(value) && value >= 1;
  if (!actor || actor.active !== true || actor.role !== data?.role ||
      !["owner", "parent", "adult", "child"].includes(actor.role) ||
      !validRevision(actor.revision) || !card?._entry ||
      !data?.settings?.modules?.includes("routines")) return null;
  return JSON.stringify([
    card._generation, card._entry, actor.id, actor.role, actor.revision,
    members.filter((member) => member?.active === true && member.role !== "guest")
      .map((member) => [member.id, member.role, member.revision])
      .sort((left, right) => String(left[0]).localeCompare(String(right[0]))),
  ]);
}

export function reconcileRoutineRefresh(card, previousData) {
  if (!previousData) return false;
  const changedIdentity = routineAccess(card, previousData) !== routineAccess(card);
  const draft = card._routineDraft;
  let changedTarget = false;
  if (draft && !(draft.frozenPayload && draft.operationId)) {
    const data = card._data?.routines;
    if (["allowlist", "modes"].includes(draft.type)) changedTarget = data?.config?.revision !== draft.revision;
    if (["edit_template", "start_run"].includes(draft.type)) changedTarget = data?.templates?.find(item => item.id === (draft.id || draft.template_id))?.revision !== draft.revision;
    if (["step_override", "cancel_run"].includes(draft.type)) changedTarget = data?.runs?.find(item => item.id === draft.run_id)?.revision !== draft.revision;
  }
  if (!changedIdentity && !changedTarget) return false;
  card._routineDraft = null;
  card._actionError = "conflict";
  return true;
}

export function renderRoutines(card, body) {
  if (!card || !body || !card._data) return;
  const role = card._data.role;
  const actorId = card._data.actor;
  const hasModule = Boolean(card._data.settings?.modules?.includes("routines"));
  const validRole = ["owner", "parent", "adult", "child"].includes(role);

  if (!validRole || !actorId || !hasModule) {
    if (card._routineDraft) card._routineDraft = null;
    return;
  }

  const startGen = card._generation;
  const startEntry = card._entry;
  const scope = routineAccess(card);
  if (!scope) {
    card._routineDraft = null;
    return;
  }

  if (card._routineDraft) {
    if (card._routineDraft.scope && card._routineDraft.scope !== scope) {
      card._routineDraft = null;
      card._actionError = "conflict";
    } else {
      card._routineDraft.scope = scope;
    }
  }

  const staleIdentity = () =>
    card._generation !== startGen ||
    card._entry !== startEntry ||
    card._data?.role !== role ||
    card._data?.actor !== actorId ||
    !card._data?.settings?.modules?.includes("routines") ||
    routineAccess(card) !== scope;
  const isStale = () => !body.isConnected || staleIdentity();

  const copy = getCopy(card);
  const data = card._data;
  const isParent = Boolean(card.parent) && ["owner", "parent"].includes(role);
  const isOwner = role === "owner";

  const routinesData = data.routines || {};
  const templates = routinesData.templates || [];
  const presets = routinesData.presets || [];
  const config = routinesData.config || { modes: ["normal"], entity_allowlist: [], revision: 0 };
  const runs = routinesData.runs || [];

  const localButton = (text, action, primary = false) => {
    const btn = card.button(text, () => {
      if (isStale() || !btn.isConnected || card._writing) return;
      action();
    }, primary);
    return btn;
  };

  const runCmd = async (action, payload, expectedRevision, targetKind, targetId) => {
    if (isStale() || card._writing) return;
    const currentDraft = card._routineDraft;
    const exactDraftRequest = Boolean(currentDraft?.frozenPayload && currentDraft?.operationId &&
      JSON.stringify(currentDraft.frozenPayload) === JSON.stringify(payload) &&
      (!currentDraft.pendingAction || currentDraft.pendingAction === action));
    if (currentDraft?.frozenPayload && !exactDraftRequest) {
      card._actionError = "conflict";
      card._routineDraft = null;
      card.render();
      return;
    }
    if (exactDraftRequest) currentDraft.pendingAction = action;

    if (expectedRevision !== undefined) {
      let freshRev = null;
      if (targetKind === "config") {
        freshRev = card._data?.routines?.config?.revision;
      } else if (targetKind === "template") {
        const t = (card._data?.routines?.templates || []).find((x) => x.id === targetId);
        freshRev = t?.revision;
      } else if (targetKind === "run") {
        const r = (card._data?.routines?.runs || []).find((x) => x.id === targetId);
        freshRev = r?.revision;
      }
      const exactTemplateRetry =
        exactDraftRequest &&
        Number.isSafeInteger(freshRev) &&
        freshRev > expectedRevision;
      if (freshRev !== expectedRevision && !exactTemplateRetry) {
        card._actionError = "conflict";
        card._routineDraft = null;
        card.render();
        return;
      }
    }

    try {
      await card.command(action, payload, exactDraftRequest ? currentDraft.operationId : undefined);
      if (!staleIdentity() && card._routineDraft === currentDraft) {
        if (!card._actionError) {
          card._routineDraft = null;
        }
        card.render();
      }
    } catch {
      if (!staleIdentity() && card._routineDraft === currentDraft) {
        card._actionError ||= "not_ready";
        card.render();
      }
    }
  };

  // 1. OWNER ENTITY ALLOWLIST EDITOR
  if (isOwner) {
    const allowSection = el("details", null, "item");
    allowSection.append(el("summary", copy.allowlist_title));
    const noticeBox = el("div", copy.allowlist_notice, "notice");
    allowSection.append(noticeBox);

    const allowCount = config.entity_allowlist?.length || 0;
    const allowSummary = el("div", null, "sub");
    if (allowCount === 0) {
      allowSummary.textContent = copy.none;
    } else {
      for (const ent of config.entity_allowlist) {
        allowSummary.append(el("span", ent, "badge"));
      }
    }
    allowSection.append(allowSummary);

    const isAllowDraft = card._routineDraft?.type === "allowlist";
    allowSection.open = isAllowDraft;
    const allowBtn = localButton(isAllowDraft ? copy.cancel : copy.allowlist_edit, () => {
      if (card._writing) return;
      card._actionError = null;
      if (isAllowDraft) {
        card._routineDraft = null;
      } else {
        card._routineDraft = {
          type: "allowlist",
          text: (config.entity_allowlist || []).join("\n"),
          revision: config.revision,
          scope,
        };
      }
      card.render();
    });
    allowSection.append(allowBtn);

    if (isAllowDraft) {
      const d = card._routineDraft;
      const isFrozen = Boolean(d.frozenPayload);
      const form = el("form", null, "editor");
      const label = el("label", copy.allowlist_title);
      const ta = el("textarea");
      ta.rows = 4;
      ta.value = d.text || "";
      ta.placeholder = copy.allowlist_placeholder;
      ta.disabled = isFrozen || Boolean(card._writing);
      label.append(ta);
      form.append(label);

      ta.addEventListener("input", () => {
        if (!isFrozen) d.text = ta.value;
      });

      const acts = el("div", null, "actions");
      const saveBtn = localButton(card._actionError && isFrozen ? copy.retry : copy.save, () => {}, true);
      saveBtn.type = "submit";
      acts.append(saveBtn);
      acts.append(
        localButton(copy.cancel, () => {
          if (card._writing) return;
          card._routineDraft = null;
          card._actionError = null;
          card.render();
        })
      );
      form.append(acts);

      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        if (isStale() || card._writing || card._routineDraft !== d) return;

        let payload = d.frozenPayload ? clone(d.frozenPayload) : null;
        if (!payload) {
          const rawLines = ta.value.split(/\r?\n/).map((s) => s.trim()).filter(Boolean);
          if (rawLines.length > 50) {
            card._actionError = copy.allowlist_max_exceeded;
            card.render();
            return;
          }
          const seen = new Set();
          const items = [];
          for (const item of rawLines) {
            if (item.length > 255 || !ENTITY_REGEX.test(item) || item.toLowerCase() !== item) {
              card._actionError = copy.allowlist_invalid;
              card.render();
              return;
            }
            if (seen.has(item)) {
              card._actionError = copy.allowlist_duplicate;
              card.render();
              return;
            }
            seen.add(item);
            items.push(item);
          }
          payload = { entity_allowlist: items, revision: d.revision };
          d.frozenPayload = clone(payload);
          d.operationId = crypto.randomUUID();
        }
        await runCmd("routines.configure", payload, d.revision, "config");
      });

      allowSection.append(form);
    }
    body.append(allowSection);
  }

  // 2. PARENT HOUSEHOLD MODES MULTISELECT
  if (isParent) {
    const modesSection = el("details", null, "item");
    modesSection.append(el("summary", copy.modes_title));
    modesSection.append(el("p", copy.modes_notice, "sub"));

    const currentModes = el("div", null, "sub");
    for (const m of config.modes || ["normal"]) {
      currentModes.append(el("span", copy[`mode_${m}`] || m, "badge"));
    }
    modesSection.append(currentModes);

    const isModesDraft = card._routineDraft?.type === "modes";
    modesSection.open = isModesDraft;
    const modesBtn = localButton(isModesDraft ? copy.cancel : copy.modes_edit, () => {
      if (card._writing) return;
      card._actionError = null;
      if (isModesDraft) {
        card._routineDraft = null;
      } else {
        card._routineDraft = {
          type: "modes",
          selected: [...(config.modes || ["normal"])],
          revision: config.revision,
          scope,
        };
      }
      card.render();
    });
    modesSection.append(modesBtn);

    if (isModesDraft) {
      const d = card._routineDraft;
      const isFrozen = Boolean(d.frozenPayload);
      const form = el("form", null, "editor");
      const fieldset = el("fieldset");
      fieldset.append(el("legend", copy.modes_title));

      const checkboxes = {};
      for (const modeKey of ALL_MODES) {
        const lbl = el("label", copy[`mode_${modeKey}`] || modeKey);
        const cb = el("input");
        cb.type = "checkbox";
        cb.value = modeKey;
        cb.checked = d.selected.includes(modeKey);
        cb.disabled = isFrozen || Boolean(card._writing);
        lbl.prepend(cb);
        fieldset.append(lbl);
        checkboxes[modeKey] = cb;

        cb.addEventListener("change", () => {
          if (isFrozen) return;
          if (modeKey === "normal" && cb.checked) {
            for (const other of ALL_MODES) {
              if (other !== "normal" && checkboxes[other]) checkboxes[other].checked = false;
            }
          } else if (modeKey !== "normal" && cb.checked) {
            if (checkboxes.normal) checkboxes.normal.checked = false;
          }
          const chosen = ALL_MODES.filter((k) => checkboxes[k]?.checked);
          d.selected = chosen.length ? chosen : ["normal"];
          if (!chosen.length && checkboxes.normal) checkboxes.normal.checked = true;
        });
      }
      form.append(fieldset);

      const acts = el("div", null, "actions");
      const saveBtn = localButton(card._actionError && isFrozen ? copy.retry : copy.save, () => {}, true);
      saveBtn.type = "submit";
      acts.append(saveBtn);
      acts.append(
        localButton(copy.cancel, () => {
          if (card._writing) return;
          card._routineDraft = null;
          card._actionError = null;
          card.render();
        })
      );
      form.append(acts);

      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        if (isStale() || card._writing || card._routineDraft !== d) return;

        let payload = d.frozenPayload ? clone(d.frozenPayload) : null;
        if (!payload) {
          const chosen = ALL_MODES.filter((k) => checkboxes[k]?.checked);
          payload = { modes: chosen.length ? chosen : ["normal"], revision: d.revision };
          d.frozenPayload = clone(payload);
          d.operationId = crypto.randomUUID();
        }
        await runCmd("routines.modes", payload, d.revision, "config");
      });

      modesSection.append(form);
    }
    body.append(modesSection);
  }

  // 3. TEMPLATES SECTION
  const isTemplateForm =
    card._routineDraft?.type === "create_template" || card._routineDraft?.type === "edit_template";
  const templatesSection = el("section", null, "item");
  templatesSection.append(el("strong", copy.templates_title));

  if (isParent) {
    const toolbar = el("div", null, "toolbar");
    toolbar.append(
      localButton(isTemplateForm ? copy.cancel : copy.new_template, () => {
        if (card._writing) return;
        card._actionError = null;
        if (isTemplateForm) {
          card._routineDraft = null;
        } else {
          card._routineDraft = {
            type: "create_template",
            preset_id: "",
            title: "",
            description: "",
            enabled: true,
            assignees: [actorId],
            steps: [makeDefaultStep(0)],
            rule: null,
            skip_when: null,
            scope,
          };
        }
        card.render();
      })
    );
    templatesSection.append(toolbar);
  }

  // CREATE / EDIT TEMPLATE FORM (PARENT ONLY)
  if (isParent && isTemplateForm) {
    const d = card._routineDraft;
    const isFrozen = Boolean(d.frozenPayload);
    const form = el("form", null, "editor");

    // Preset picker
    if (d.type === "create_template" && presets.length > 0) {
      const presetWrap = el("label", copy.preset_picker);
      const presetSel = el("select");
      presetSel.disabled = isFrozen || Boolean(card._writing);
      const defOpt = el("option", copy.preset_none);
      defOpt.value = "";
      presetSel.append(defOpt);
      for (const p of presets) {
        const opt = el("option", p.title || p.id);
        opt.value = p.id;
        presetSel.append(opt);
      }
      presetSel.value = d.preset_id || "";
      presetSel.addEventListener("change", () => {
        if (isFrozen) return;
        d.preset_id = presetSel.value;
        const p = presets.find((x) => x.id === presetSel.value);
        if (p) {
          d.title = p.title || "";
          d.description = p.description || "";
          d.skip_when = p.skip_when ? clone(p.skip_when) : null;
          d.steps = (p.steps || []).map((s) => buildStepFromData(s));
          if (!d.steps.length) d.steps = [makeDefaultStep(0)];
        }
        card.render();
      });
      presetWrap.append(presetSel);
      form.append(presetWrap);
    }

    // Title
    const titleWrap = el("label", copy.template_title);
    const titleInput = el("input");
    titleInput.name = "title";
    titleInput.type = "text";
    titleInput.required = true;
    titleInput.maxLength = 255;
    titleInput.value = d.title || "";
    titleInput.disabled = isFrozen || Boolean(card._writing);
    titleInput.addEventListener("input", () => {
      if (!isFrozen) d.title = titleInput.value;
    });
    titleWrap.append(titleInput);
    form.append(titleWrap);

    // Description
    const descWrap = el("label", copy.template_description);
    const descInput = el("textarea");
    descInput.name = "description";
    descInput.rows = 2;
    descInput.maxLength = 2000;
    descInput.value = d.description || "";
    descInput.disabled = isFrozen || Boolean(card._writing);
    descInput.addEventListener("input", () => {
      if (!isFrozen) d.description = descInput.value;
    });
    descWrap.append(descInput);
    form.append(descWrap);

    // Enabled
    const enabledLabel = el("label", copy.template_enabled, "check");
    const enabledInput = el("input");
    enabledInput.name = "enabled";
    enabledInput.type = "checkbox";
    enabledInput.checked = Boolean(d.enabled);
    enabledInput.disabled = isFrozen || Boolean(card._writing);
    enabledInput.addEventListener("change", () => {
      if (!isFrozen) d.enabled = enabledInput.checked;
    });
    enabledLabel.prepend(enabledInput);
    form.append(enabledLabel);

    // Assignees multiselect
    const assigneesFieldset = el("fieldset");
    assigneesFieldset.append(el("legend", copy.template_assignees));
    const eligibleMembers = (data.members || []).filter((m) => m && m.active && m.role !== "guest");
    for (const mem of eligibleMembers) {
      const lbl = el("label", mem.name || mem.id);
      const cb = el("input");
      cb.type = "checkbox";
      cb.value = mem.id;
      cb.checked = (d.assignees || []).includes(mem.id);
      cb.disabled = isFrozen || Boolean(card._writing);
      cb.addEventListener("change", () => {
        if (isFrozen) return;
        const set = new Set(d.assignees || []);
        if (cb.checked) set.add(mem.id);
        else set.delete(mem.id);
        d.assignees = [...set];
      });
      lbl.prepend(cb);
      assigneesFieldset.append(lbl);
    }
    form.append(assigneesFieldset);

    form.append(renderConditionForm({
      value: d.skip_when,
      language: card._config?.language || card._hass?.language || "en",
      allowlist: card._data.routines?.config?.entity_allowlist || [],
      timezone: card._data.settings?.timezone || card._hass?.config?.time_zone || "UTC",
      disabled: isFrozen || Boolean(card._writing),
      context: "template_skip",
      scope: "template-skip",
      isStale: () => isStale() || Boolean(card._writing) || card._routineDraft !== d,
      onChange: value => { d.skip_when = value; },
    }));

    // Ordered steps builder
    const stepsBox = el("div", null, "editor");
    stepsBox.append(el("strong", copy.steps_title));
    const renderSteps = () => {
      stepsBox.replaceChildren(el("strong", copy.steps_title));
      (d.steps || []).forEach((st, idx) => {
        const stepCard = el("div", null, "item");
        stepCard.dataset.routineStepIndex = String(idx);
        stepCard.append(el("strong", `${copy.step_num} ${idx + 1}`));

        // Title
        const sTitleWrap = el("label", copy.step_title);
        const sTitleInput = el("input");
        sTitleInput.type = "text";
        sTitleInput.required = true;
        sTitleInput.maxLength = 255;
        sTitleInput.value = st.title || "";
        sTitleInput.disabled = isFrozen || Boolean(card._writing);
        sTitleInput.addEventListener("input", () => {
          if (!isFrozen) st.title = sTitleInput.value;
        });
        sTitleWrap.append(sTitleInput);
        stepCard.append(sTitleWrap);

        // Offset
        const sOffsetWrap = el("label", copy.step_offset);
        const sOffsetInput = el("input");
        sOffsetInput.type = "number";
        sOffsetInput.min = "0";
        sOffsetInput.max = "10080";
        sOffsetInput.value = st.raw_offset;
        sOffsetInput.disabled = isFrozen || Boolean(card._writing);
        sOffsetInput.addEventListener("input", () => {
          if (!isFrozen) st.raw_offset = sOffsetInput.value;
        });
        sOffsetWrap.append(sOffsetInput);
        stepCard.append(sOffsetWrap);

        const assigneeLabel = el("label", copy.step_assignee);
        const assigneeSelect = el("select");
        assigneeSelect.setAttribute("data-step-assignee", String(idx));
        const inherit = el("option", copy.inherit_assignee); inherit.value = "";
        assigneeSelect.append(inherit);
        for (const member of card._data.members || []) {
          if (!member.active || member.role === "guest") continue;
          const option = el("option", member.name); option.value = member.id;
          assigneeSelect.append(option);
        }
        if (st.assignee && !Array.from(assigneeSelect.options).some(o => o.value === st.assignee)) {
          const missing = el("option", `${copy.unknown_member} (${st.assignee})`); missing.value = st.assignee;
          assigneeSelect.append(missing);
        }
        assigneeSelect.value = st.assignee || "";
        assigneeSelect.disabled = isFrozen || Boolean(card._writing);
        assigneeSelect.addEventListener("change", () => {
          if (isStale() || isFrozen || card._writing || card._routineDraft !== d) return;
          st.assignee = assigneeSelect.value || null;
        });
        assigneeLabel.append(assigneeSelect); stepCard.append(assigneeLabel);

        // Confirmation Mode
        const sConfWrap = el("label", copy.step_confirmation);
        const sConfSelect = el("select");
        sConfSelect.dataset.stepConfirmation = String(idx);
        sConfSelect.disabled = isFrozen || Boolean(card._writing);
        for (const cVal of ["manual", "none", "entity_state"]) {
          const opt = el("option", copy[`confirmation_${cVal}`] || cVal);
          opt.value = cVal;
          sConfSelect.append(opt);
        }
        sConfSelect.value = st.confirmation || "manual";
        sConfWrap.append(sConfSelect);
        stepCard.append(sConfWrap);

        // Escalation minutes
        const sEscWrap = el("label", copy.step_escalate);
        const sEscInput = el("input");
        sEscInput.type = "number";
        sEscInput.min = "1";
        sEscInput.max = "1440";
        sEscInput.value = st.raw_escalate;
        sEscInput.disabled = isFrozen || Boolean(card._writing);
        sEscInput.addEventListener("input", () => {
          if (!isFrozen) st.raw_escalate = sEscInput.value;
        });
        sEscWrap.append(sEscInput);
        stepCard.append(sEscWrap);

        const conditionStale = () =>
          isStale() ||
          isFrozen ||
          Boolean(card._writing) ||
          card._routineDraft !== d ||
          !d.steps.includes(st);

        const skipDetails = el("details", null, "condition-panel");
        skipDetails.dataset.stepCondition = "skip";
        skipDetails.dataset.stepIndex = String(idx);
        skipDetails.open = st.skip_when != null;
        skipDetails.append(el("summary", copy.step_skip_editor));
        skipDetails.append(
          renderConditionForm({
            value: st.skip_when,
            language: card._config?.language || card._hass?.language || "en",
            allowlist: card._data.routines?.config?.entity_allowlist || [],
            timezone: card._data.settings?.timezone || card._hass?.config?.time_zone || "UTC",
            disabled: isFrozen || Boolean(card._writing),
            context: "step_skip",
            scope: `step-${idx}-skip`,
            isStale: conditionStale,
            onChange: (value) => {
              if (conditionStale()) return;
              st.skip_when = value;
              st.skip_dirty = true;
            },
          }),
        );
        stepCard.append(skipDetails);

        if (st.confirmation === "entity_state") {
          const completionDetails = el("details", null, "condition-panel");
          completionDetails.dataset.stepCondition = "completion";
          completionDetails.dataset.stepIndex = String(idx);
          completionDetails.open = st.completion_condition != null;
          completionDetails.append(el("summary", copy.step_completion_editor));
          completionDetails.append(
            renderConditionForm({
              value: st.completion_condition,
              language: card._config?.language || card._hass?.language || "en",
              allowlist: card._data.routines?.config?.entity_allowlist || [],
              timezone: card._data.settings?.timezone || card._hass?.config?.time_zone || "UTC",
              disabled: isFrozen || Boolean(card._writing),
              context: "step_completion",
              scope: `step-${idx}-completion`,
              isStale: conditionStale,
              onChange: (value) => {
                if (conditionStale()) return;
                st.completion_condition = value;
                st.completion_dirty = true;
              },
            }),
          );
          stepCard.append(completionDetails);
        } else if (st.completion_condition != null) {
          stepCard.append(el("p", copy.completion_inactive_notice, "sub"));
        }

        sConfSelect.addEventListener("change", () => {
          if (conditionStale()) return;
          st.confirmation = sConfSelect.value;
          renderSteps();
        });

        // Step reordering / deletion actions
        const sActs = el("div", null, "actions");
        if (idx > 0) {
          sActs.append(
            localButton(copy.move_up, () => {
              if (isFrozen || card._writing) return;
              const temp = d.steps[idx - 1];
              d.steps[idx - 1] = d.steps[idx];
              d.steps[idx] = temp;
              renderSteps();
            })
          );
        }
        if (idx < d.steps.length - 1) {
          sActs.append(
            localButton(copy.move_down, () => {
              if (isFrozen || card._writing) return;
              const temp = d.steps[idx + 1];
              d.steps[idx + 1] = d.steps[idx];
              d.steps[idx] = temp;
              renderSteps();
            })
          );
        }
        if (d.steps.length > 1) {
          sActs.append(
            localButton(copy.remove_step, () => {
              if (isFrozen || card._writing) return;
              d.steps.splice(idx, 1);
              renderSteps();
            })
          );
        }
        stepCard.append(sActs);
        stepsBox.append(stepCard);
      });

      if (d.steps.length < 30) {
        const addBtn = localButton(copy.add_step, () => {
          if (isFrozen || card._writing) return;
          const lastNum = d.steps.length ? Number(d.steps[d.steps.length - 1].raw_offset) : 0;
          const nextOffset = Number.isInteger(lastNum) ? lastNum + 5 : 0;
          d.steps.push(makeDefaultStep(nextOffset));
          renderSteps();
        });
        stepsBox.append(addBtn);
      }
    };
    renderSteps();
    form.append(stepsBox);
    form.append(el("p", copy.handoff_notice, "muted"));

    const zone = card._data.settings?.timezone || card._hass?.config?.time_zone || "UTC";
    d.recurrence ||= makeRecurrenceDraft(d.rule || null, {
      timezone: zone, start_date: wallTime(new Date().toISOString(), zone).slice(0, 10), time: "08:00",
    });
    const recurrenceSection = el("section");
    renderRecurrence(recurrenceSection, d.recurrence, {
      language: card._config?.language || card._hass?.language || "en",
      isStale: () => isStale() || isFrozen || Boolean(card._writing) || card._routineDraft !== d,
    });
    if (isFrozen || card._writing) for (const control of recurrenceSection.querySelectorAll("input,select,textarea")) control.disabled = true;
    form.append(recurrenceSection);

    // Form submission buttons
    const actions = el("div", null, "actions");
    const saveBtn = localButton(card._actionError && isFrozen ? copy.retry : copy.save, () => {}, true);
    saveBtn.type = "submit";
    actions.append(saveBtn);
    actions.append(
      localButton(copy.cancel, () => {
        if (card._writing) return;
        card._routineDraft = null;
        card._actionError = null;
        card.render();
      })
    );
    form.append(actions);

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (isStale() || card._writing || card._routineDraft !== d) return;

      let payload = d.frozenPayload ? clone(d.frozenPayload) : null;
      if (!payload) {
        const titleTrimmed = d.title ? d.title.trim() : "";
        if (!titleTrimmed) {
          card._actionError = copy.title_required;
          card.render();
          return;
        }

        const assigneesList = d.assignees || [];
        if (assigneesList.length === 0) {
          card._actionError = copy.assignees_required;
          card.render();
          return;
        }
        if (assigneesList.length > 20) {
          card._actionError = copy.assignees_max_exceeded;
          card.render();
          return;
        }
        const activeMembers = new Set((card._data.members || []).filter((m) => m && m.active && m.role !== "guest").map((m) => m.id));
        for (const mId of assigneesList) {
          if (!activeMembers.has(mId)) {
            card._actionError = copy.assignees_required;
            card.render();
            return;
          }
        }

        const stepsList = d.steps || [];
        if (stepsList.length === 0) {
          card._actionError = copy.steps_required;
          card.render();
          return;
        }
        if (stepsList.length > 30) {
          card._actionError = copy.steps_max_exceeded;
          card.render();
          return;
        }

        const allowedEntities = new Set(card._data.routines?.config?.entity_allowlist || []);
        const validatedSteps = [];
        let prevOffset = -1;

        for (const st of stepsList) {
          const stTitle = st.title ? st.title.trim() : "";
          if (!stTitle) {
            card._actionError = copy.title_required;
            card.render();
            return;
          }

          if (st.raw_offset === "" || st.raw_offset === null || st.raw_offset === undefined) {
            card._actionError = copy.invalid_offset;
            card.render();
            return;
          }
          const offsetNum = Number(st.raw_offset);
          if (!Number.isInteger(offsetNum) || offsetNum < 0 || offsetNum > 10080) {
            card._actionError = copy.invalid_offset;
            card.render();
            return;
          }
          if (offsetNum < prevOffset) {
            card._actionError = copy.step_order_descending;
            card.render();
            return;
          }
          prevOffset = offsetNum;

          let escalateNum = null;
          if (st.raw_escalate !== "" && st.raw_escalate !== null && st.raw_escalate !== undefined) {
            escalateNum = Number(st.raw_escalate);
            if (!Number.isInteger(escalateNum) || escalateNum < 1 || escalateNum > 1440) {
              card._actionError = copy.invalid_escalate;
              card.render();
              return;
            }
          }

          let skipCondition;
          let compCondition = null;
          try {
            skipCondition = conditionForSave(
              st.skip_when,
              Boolean(st.skip_dirty),
              [...allowedEntities],
            ).value;
            if (st.confirmation === "entity_state") {
              const completion = conditionForSave(
                st.completion_condition,
                Boolean(st.completion_dirty),
                [...allowedEntities],
              );
              if (
                completion.value == null ||
                (completion.supported && !conditionHasEntity(completion.value))
              ) {
                throw new Error("completion_condition");
              }
              compCondition = completion.value;
            }
          } catch {
            card._actionError = copy.condition_error;
            card.render();
            return;
          }

          validatedSteps.push({
            title: stTitle,
            ...(st.assignee ? {assignee: st.assignee} : {}),
            offset_minutes: offsetNum,
            confirmation: st.confirmation,
            completion_condition: compCondition,
            skip_when: skipCondition,
            escalate_minutes: escalateNum,
          });
          if (st.assignee && !activeMembers.has(st.assignee)) {
            card._actionError = copy.assignees_required;
            card.render();
            return;
          }
        }

        let rule;
        try { rule = recurrencePayload(d.recurrence); }
        catch {
          card._actionError = copy.recurrence_error;
          card.render();
          return;
        }
        let skipWhen;
        try {
          skipWhen = normalizeCondition(d.skip_when, {allowlist: [...allowedEntities]});
        } catch {
          card._actionError = copy.condition_error;
          card.render();
          return;
        }
        payload = {
          title: titleTrimmed,
          description: d.description ? d.description.trim() : "",
          enabled: Boolean(d.enabled),
          assignees: assigneesList,
          rule,
          skip_when: skipWhen,
          steps: validatedSteps,
        };
        if (d.type === "edit_template") {
          payload.id = d.id;
          payload.revision = d.revision;
        }
        d.frozenPayload = clone(payload);
        d.operationId = crypto.randomUUID();
      }

      // Legacy in-memory drafts have no private retry ID. They may adopt only
      // the matching existing card receipt, never invent a new request for an
      // uncertain earlier save.
      if (!d.operationId) {
        const fingerprint = JSON.stringify([card._entry, "routines.save", payload]);
        if (card._pending?.fingerprint !== fingerprint || !card._pending?.id) {
          card._actionError = "conflict";
          card.render();
          return;
        }
        d.operationId = card._pending.id;
      }

      await runCmd(
        "routines.save",
        payload,
        d.type === "edit_template" ? d.revision : undefined,
        "template",
        d.id
      );
    });

    templatesSection.append(form);
  }

  // TEMPLATES LIST
  if (!templates.length) {
    templatesSection.append(el("div", copy.no_templates, "empty"));
  } else {
    const list = el("ul", null, "list");
    for (const tmpl of templates) {
      const li = el("li", null, "item");
      li.append(el("strong", tmpl.title));
      if (tmpl.description) {
        li.append(el("div", tmpl.description, "sub"));
      }

      const meta = el("div", null, "sub");
      meta.append(el("span", tmpl.enabled ? copy.status_active : copy.none, "badge"));
      if (tmpl.assignees?.length) {
        const names = tmpl.assignees.map((id) => getMemberName(card, id)).join(", ");
        meta.append(el("span", names, "badge"));
      }
      li.append(meta);

      const actions = el("div", null, "actions");

      // Start routine button
      if (tmpl.enabled) {
        const canStart = isParent || (tmpl.assignees ? tmpl.assignees.includes(actorId) : true);
        if (canStart) {
          actions.append(
            localButton(copy.start_routine, () => {
              if (card._writing) return;
              card._actionError = null;
              card._routineDraft = {
                type: "start_run",
                template_id: tmpl.id,
                revision: tmpl.revision,
                member: isParent ? (tmpl.assignees?.[0] || actorId) : actorId,
                assignees: tmpl.assignees || [actorId],
                scope,
              };
              card.render();
            })
          );
        }
      }

      // Edit template (parent only)
      if (isParent && tmpl.steps) {
        actions.append(
          localButton(copy.edit, () => {
            if (card._writing) return;
            card._actionError = null;
            card._routineDraft = {
              type: "edit_template",
              id: tmpl.id,
              revision: tmpl.revision,
              title: tmpl.title || "",
              description: tmpl.description || "",
              enabled: Boolean(tmpl.enabled),
              assignees: [...(tmpl.assignees || [])],
              rule: tmpl.rule ? clone(tmpl.rule) : null,
              skip_when: tmpl.skip_when ? clone(tmpl.skip_when) : null,
              steps: (tmpl.steps || []).map((s) => buildStepFromData(s)),
              scope,
            };
            card.render();
          })
        );
      }

      if (actions.children.length) li.append(actions);

      // START RUN FORM MODAL / INLINE
      if (card._routineDraft?.type === "start_run" && card._routineDraft.template_id === tmpl.id) {
        const d = card._routineDraft;
        const isFrozen = Boolean(d.frozenPayload);
        const startForm = el("form", null, "editor");

        if (isParent && d.assignees.length > 1) {
          const memWrap = el("label", copy.start_for);
          const sel = el("select");
          sel.disabled = isFrozen || Boolean(card._writing);
          for (const mId of d.assignees) {
            const opt = el("option", getMemberName(card, mId));
            opt.value = mId;
            sel.append(opt);
          }
          sel.value = d.member || actorId;
          sel.addEventListener("change", () => {
            if (!isFrozen) d.member = sel.value;
          });
          memWrap.append(sel);
          startForm.append(memWrap);
        } else {
          startForm.append(el("p", `${copy.start_for}: ${getMemberName(card, d.member)}`, "sub"));
        }

        const sActs = el("div", null, "actions");
        const sSubBtn = localButton(card._actionError && isFrozen ? copy.retry : copy.start_button, () => {}, true);
        sSubBtn.type = "submit";
        sActs.append(sSubBtn);
        sActs.append(
          localButton(copy.cancel, () => {
            if (card._writing) return;
            card._routineDraft = null;
            card._actionError = null;
            card.render();
          })
        );
        startForm.append(sActs);

        startForm.addEventListener("submit", async (e) => {
          e.preventDefault();
          if (isStale() || card._writing || card._routineDraft !== d) return;

          let payload = d.frozenPayload ? clone(d.frozenPayload) : null;
          if (!payload) {
            payload = {
              id: d.template_id,
              revision: d.revision,
              member: d.member || actorId,
            };
            d.frozenPayload = clone(payload);
            d.operationId = crypto.randomUUID();
          }
          await runCmd("routines.start", payload, d.revision, "template", d.template_id);
        });

        li.append(startForm);
      }

      list.append(li);
    }
    templatesSection.append(list);
  }
  body.append(templatesSection);

  // 4. ACTIVE ROUTINE RUNS
  const activeRuns = runs.filter((r) => r.status === "active");
  const activeSection = el("section", null, "item");
  activeSection.append(el("strong", copy.active_runs_title));

  if (!activeRuns.length) {
    activeSection.append(el("div", copy.no_active_runs, "empty"));
  } else {
    const list = el("ul", null, "list");
    for (const run of activeRuns) {
      const li = el("li", null, "item");
      li.append(el("strong", run.title));
      li.append(
        el("div", `${copy.member}: ${getMemberName(card, run.member)} · ${copy.started}: ${formatDate(card, run.started_at)}`, "sub")
      );

      // Steps list
      const stepsUl = el("ul", null, "list");
      (run.steps || []).forEach((st, idx) => {
        const stepLi = el("li", null, "item");
        stepLi.append(el("strong", `${idx + 1}. ${st.title}`));
        const stMeta = el("div", null, "sub");
        stMeta.append(el("span", copy[`status_${st.status}`] || st.status, "badge"));
        if (st.confirmation) {
          stMeta.append(el("span", copy[`confirmation_${st.confirmation}`] || st.confirmation, "badge"));
        }
        stMeta.append(el("span", `${copy.member}: ${getMemberName(card, st.member || run.member)}`, "badge"));
        stepLi.append(stMeta);

        const stepActions = el("div", null, "actions");

        // MANUAL STEP CONFIRMATION (Assigned member only when active & nonce present)
        if ((st.member || run.member) === actorId && st.status === "active" && st.confirmation === "manual" && st.nonce) {
          stepActions.append(
            localButton(copy.confirm_step, async () => {
              if (card._writing) return;
              await runCmd(
                "routines.confirm",
                {
                  id: run.id,
                  revision: run.revision,
                  step: idx,
                  nonce: st.nonce,
                },
                run.revision,
                "run",
                run.id
              );
            }, true)
          );
        }

        // PARENT REASONED OVERRIDE (Completed or Skipped)
        if (isParent && st.status === "active") {
          const isOverrideDraft =
            card._routineDraft?.type === "step_override" &&
            card._routineDraft.run_id === run.id &&
            card._routineDraft.step === idx;

          stepActions.append(
            localButton(isOverrideDraft ? copy.cancel : copy.parent_override, () => {
              if (card._writing) return;
              card._actionError = null;
              if (isOverrideDraft) {
                card._routineDraft = null;
              } else {
                card._routineDraft = {
                  type: "step_override",
                  run_id: run.id,
                  revision: run.revision,
                  step: idx,
                  outcome: "completed",
                  reason: "",
                  scope,
                };
              }
              card.render();
            })
          );

          if (isOverrideDraft) {
            const od = card._routineDraft;
            const isFrozen = Boolean(od.frozenPayload);
            const oForm = el("form", null, "editor");

            const selWrap = el("label", copy.parent_override);
            const selOutcome = el("select");
            selOutcome.disabled = isFrozen || Boolean(card._writing);
            for (const outKey of ["completed", "skipped"]) {
              const opt = el("option", copy[`override_${outKey}`] || outKey);
              opt.value = outKey;
              selOutcome.append(opt);
            }
            selOutcome.value = od.outcome || "completed";
            selOutcome.addEventListener("change", () => {
              if (!isFrozen) od.outcome = selOutcome.value;
            });
            selWrap.append(selOutcome);
            oForm.append(selWrap);

            const rWrap = el("label", copy.reason);
            const rInput = el("input");
            rInput.name = "reason";
            rInput.type = "text";
            rInput.required = true;
            rInput.maxLength = 500;
            rInput.value = od.reason || "";
            rInput.disabled = isFrozen || Boolean(card._writing);
            rInput.addEventListener("input", () => {
              if (!isFrozen) od.reason = rInput.value;
            });
            rWrap.append(rInput);
            oForm.append(rWrap);

            const oActs = el("div", null, "actions");
            const oSave = localButton(card._actionError && isFrozen ? copy.retry : copy.save, () => {}, true);
            oSave.type = "submit";
            oActs.append(oSave);
            oActs.append(
              localButton(copy.cancel, () => {
                if (card._writing) return;
                card._routineDraft = null;
                card._actionError = null;
                card.render();
              })
            );
            oForm.append(oActs);

            oForm.addEventListener("submit", async (e) => {
              e.preventDefault();
              if (isStale() || card._writing || card._routineDraft !== od) return;

              let payload = od.frozenPayload ? clone(od.frozenPayload) : null;
              if (!payload) {
                const trimmedReason = od.reason ? od.reason.trim() : "";
                if (!trimmedReason) {
                  card._actionError = copy.reason_required;
                  card.render();
                  return;
                }
                payload = {
                  id: od.run_id,
                  revision: od.revision,
                  step: od.step,
                  outcome: od.outcome,
                  reason: trimmedReason,
                };
                od.frozenPayload = clone(payload);
                od.operationId = crypto.randomUUID();
              }
              await runCmd("routines.override", payload, od.revision, "run", od.run_id);
            });
            stepLi.append(oForm);
          }
        }

        if (stepActions.children.length) stepLi.append(stepActions);
        stepsUl.append(stepLi);
      });
      li.append(stepsUl);

      // PARENT CANCEL ENTIRE RUN
      if (isParent) {
        const isCancelDraft =
          card._routineDraft?.type === "cancel_run" && card._routineDraft.run_id === run.id;
        const runActions = el("div", null, "actions");
        runActions.append(
          localButton(isCancelDraft ? copy.cancel : copy.cancel_run, () => {
            if (card._writing) return;
            card._actionError = null;
            if (isCancelDraft) {
              card._routineDraft = null;
            } else {
              card._routineDraft = {
                type: "cancel_run",
                run_id: run.id,
                revision: run.revision,
                reason: "",
                scope,
              };
            }
            card.render();
          })
        );
        li.append(runActions);

        if (isCancelDraft) {
          const cd = card._routineDraft;
          const isFrozen = Boolean(cd.frozenPayload);
          const cForm = el("form", null, "editor");
          const cWrap = el("label", copy.reason);
          const cInput = el("input");
          cInput.name = "reason";
          cInput.type = "text";
          cInput.required = true;
          cInput.maxLength = 500;
          cInput.value = cd.reason || "";
          cInput.disabled = isFrozen || Boolean(card._writing);
          cInput.addEventListener("input", () => {
            if (!isFrozen) cd.reason = cInput.value;
          });
          cWrap.append(cInput);
          cForm.append(cWrap);

          const cActs = el("div", null, "actions");
          const cSave = localButton(card._actionError && isFrozen ? copy.retry : copy.cancel_run, () => {}, true);
          cSave.type = "submit";
          cActs.append(cSave);
          cActs.append(
            localButton(copy.cancel, () => {
              if (card._writing) return;
              card._routineDraft = null;
              card._actionError = null;
              card.render();
            })
          );
          cForm.append(cActs);

          cForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            if (isStale() || card._writing || card._routineDraft !== cd) return;

            let payload = cd.frozenPayload ? clone(cd.frozenPayload) : null;
            if (!payload) {
              const trimmedReason = cd.reason ? cd.reason.trim() : "";
              if (!trimmedReason) {
                card._actionError = copy.reason_required;
                card.render();
                return;
              }
              payload = {
                id: cd.run_id,
                revision: cd.revision,
                reason: trimmedReason,
              };
              cd.frozenPayload = clone(payload);
              cd.operationId = crypto.randomUUID();
            }
            await runCmd("routines.cancel", payload, cd.revision, "run", cd.run_id);
          });
          li.append(cForm);
        }
      }

      // History log
      if (run.history?.length) {
        const hist = el("details");
        hist.append(el("summary", copy.history));
        for (const item of run.history) {
          const actionText = copy[`action_${item.action}`] || item.action;
          const reasonText = item.reason ? (copy[`reason_${item.reason}`] || item.reason) : "";
          const text = `${formatDate(card, item.at)} · ${getMemberName(card, item.actor)} · ${actionText}${reasonText ? " (" + reasonText + ")" : ""}`;
          hist.append(el("div", text, "sub"));
        }
        li.append(hist);
      }

      list.append(li);
    }
    activeSection.append(list);
  }
  body.insertBefore(activeSection, templatesSection);

  // 5. COMPLETED & PAST ROUTINE RUNS (READONLY)
  const pastRuns = runs.filter((r) => r.status !== "active");
  const pastSection = el("details", null, "item");
  pastSection.append(el("summary", copy.completed_runs_title));

  if (!pastRuns.length) {
    pastSection.append(el("div", copy.no_completed_runs, "empty"));
  } else {
    const list = el("ul", null, "list");
    for (const run of pastRuns) {
      const li = el("li", null, "item");
      li.append(el("strong", run.title));
      li.append(
        el(
          "div",
          `${copy.member}: ${getMemberName(card, run.member)} · ${copy[`status_${run.status}`] || run.status} · ${copy.started}: ${formatDate(card, run.started_at)}`,
          "sub"
        )
      );

      const stepsUl = el("ul", null, "list");
      (run.steps || []).forEach((st, idx) => {
        const stepLi = el("li", null, "item");
        stepLi.append(el("span", `${idx + 1}. ${st.title} — ${copy[`status_${st.status}`] || st.status}`, "sub"));
        stepsUl.append(stepLi);
      });
      li.append(stepsUl);

      if (run.history?.length) {
        const hist = el("details");
        hist.append(el("summary", copy.history));
        for (const item of run.history) {
          const actionText = copy[`action_${item.action}`] || item.action;
          const reasonText = item.reason ? (copy[`reason_${item.reason}`] || item.reason) : "";
          const text = `${formatDate(card, item.at)} · ${getMemberName(card, item.actor)} · ${actionText}${reasonText ? " (" + reasonText + ")" : ""}`;
          hist.append(el("div", text, "sub"));
        }
        li.append(hist);
      }
      list.append(li);
    }
    pastSection.append(list);
  }
  body.append(pastSection);
}
