/* Parent-only, localized operational health and delivery review. */

import { ERRORS } from "./errors.js";

export const HEALTH_COPY = Object.freeze({
  en: Object.freeze({
    parentsOnly: "System delivery details are available to parents only.",
    summary: "Current attention",
    healthSignals: "Components needing attention",
    deliveryIssues: "Delivery problems",
    components: "Components",
    deliveries: "Notification delivery",
    noHealthIssues: "No component health problems are currently reported.",
    noDeliveryIssues: "No unresolved delivery problems.",
    moreSignals: "Additional health signals",
    unknownModule: "Other component",
    unknownStatus: "Status needs review.",
    unknownNotification: "Notification",
    unknownTime: "Time unavailable",
    uncertain: "Delivery uncertain",
    failed: "Delivery failed",
    awaiting_channel: "Waiting for a linked private chat",
    retryDelivery: "Review and resend",
    resolveDelivery: "Resolve without resending",
    retryWarning:
      "Telegram may already have accepted the message. Resending can create a duplicate.",
    resolveWarning:
      "This closes the warning without resending or claiming delivery.",
    retryConsent: "I accept the possible duplicate",
    channelHint: "Link the recipient's private chat in the Telegram options.",
    reason: "Reason",
    save: "Save",
    connected: "Connected",
    fallback: "Using the configured fallback provider",
    delivery_attention: "Delivery needs review",
    frontend_resource_attention: "Dashboard resources need review",
    digest_retention_attention: "Summary retention needs review",
    school_retention_attention: "School reminder retention needs review",
    modules: Object.freeze({
      telegram: "Telegram",
      notifications: "Notification delivery",
      conversation_storage: "Conversation storage",
      scheduler: "Scheduler",
      media: "Private photos",
      frontend: "Dashboard resources",
      presence: "Presence",
      recipes: "Recipe source",
      conversation: "Language assistant",
      mikrotik: "Family network",
      digests: "Family summaries",
      school_retention: "School reminders",
      backup: "Backups",
    }),
    events: Object.freeze({
      tasks: "Tasks",
      alarms: "Wake-up checks",
      shopping: "Shopping",
      court: "Family court",
      routines: "Routines",
      rewards: "Rewards",
      calendar: "Calendar",
      network: "Family network",
      telegram_reply: "Private Telegram reply",
      telegram_poll_reply: "Family poll",
      family_digest: "Family summary",
      pantry_expiry: "Pantry reminder",
      school_preparation_reminder: "School reminder",
    }),
  }),
  ru: Object.freeze({
    parentsOnly: "Подробности состояния доставки доступны только родителям.",
    summary: "Требует внимания сейчас",
    healthSignals: "Компоненты, требующие внимания",
    deliveryIssues: "Проблемы доставки",
    components: "Компоненты",
    deliveries: "Доставка уведомлений",
    noHealthIssues: "Сейчас нет сообщений о проблемах компонентов.",
    noDeliveryIssues: "Нет нерешённых проблем доставки.",
    moreSignals: "Дополнительные сигналы состояния",
    unknownModule: "Другой компонент",
    unknownStatus: "Состояние требует проверки.",
    unknownNotification: "Уведомление",
    unknownTime: "Время недоступно",
    uncertain: "Результат доставки неизвестен",
    failed: "Ошибка доставки",
    awaiting_channel: "Ожидается привязка личного чата",
    retryDelivery: "Проверить и повторить",
    resolveDelivery: "Закрыть без повтора",
    retryWarning:
      "Telegram уже мог принять сообщение. Повторная отправка может создать дубликат.",
    resolveWarning:
      "Предупреждение будет закрыто без повтора и без утверждения о доставке.",
    retryConsent: "Понимаю, что возможен дубликат",
    channelHint: "Привяжите личный чат получателя в настройках Telegram.",
    reason: "Причина",
    save: "Сохранить",
    connected: "Подключено",
    fallback: "Используется настроенный резервный провайдер",
    delivery_attention: "Нужно проверить доставку",
    frontend_resource_attention: "Нужно проверить ресурсы панели",
    digest_retention_attention: "Нужно проверить хранение семейных сводок",
    school_retention_attention: "Нужно проверить хранение школьных напоминаний",
    modules: Object.freeze({
      telegram: "Telegram",
      notifications: "Доставка уведомлений",
      conversation_storage: "Хранилище диалогов",
      scheduler: "Планировщик",
      media: "Личные фото",
      frontend: "Ресурсы панели",
      presence: "Присутствие",
      recipes: "Источник рецептов",
      conversation: "Языковой помощник",
      mikrotik: "Семейная сеть",
      digests: "Семейные сводки",
      school_retention: "Школьные напоминания",
      backup: "Резервные копии",
    }),
    events: Object.freeze({
      tasks: "Задачи",
      alarms: "Проверки пробуждения",
      shopping: "Покупки",
      court: "Семейный суд",
      routines: "Рутины",
      rewards: "Поощрения",
      calendar: "Календарь",
      network: "Семейная сеть",
      telegram_reply: "Личный ответ Telegram",
      telegram_poll_reply: "Семейное голосование",
      family_digest: "Семейная сводка",
      pantry_expiry: "Напоминание о запасах",
      school_preparation_reminder: "Школьное напоминание",
    }),
  }),
  uk: Object.freeze({
    parentsOnly: "Подробиці стану доставки доступні лише батькам.",
    summary: "Потребує уваги зараз",
    healthSignals: "Компоненти, що потребують уваги",
    deliveryIssues: "Проблеми доставки",
    components: "Компоненти",
    deliveries: "Доставка сповіщень",
    noHealthIssues: "Зараз немає повідомлень про проблеми компонентів.",
    noDeliveryIssues: "Немає невирішених проблем доставки.",
    moreSignals: "Додаткові сигнали стану",
    unknownModule: "Інший компонент",
    unknownStatus: "Стан потребує перевірки.",
    unknownNotification: "Сповіщення",
    unknownTime: "Час недоступний",
    uncertain: "Результат доставки невідомий",
    failed: "Помилка доставки",
    awaiting_channel: "Очікується прив’язка особистого чату",
    retryDelivery: "Перевірити й повторити",
    resolveDelivery: "Закрити без повтору",
    retryWarning:
      "Telegram уже міг прийняти повідомлення. Повторне надсилання може створити дублікат.",
    resolveWarning:
      "Попередження буде закрито без повтору й без твердження про доставку.",
    retryConsent: "Розумію, що можливий дублікат",
    channelHint: "Прив’яжіть особистий чат отримувача в налаштуваннях Telegram.",
    reason: "Причина",
    save: "Зберегти",
    connected: "Підключено",
    fallback: "Використовується налаштований резервний провайдер",
    delivery_attention: "Потрібно перевірити доставку",
    frontend_resource_attention: "Потрібно перевірити ресурси панелі",
    digest_retention_attention: "Потрібно перевірити зберігання родинних зведень",
    school_retention_attention: "Потрібно перевірити зберігання шкільних нагадувань",
    modules: Object.freeze({
      telegram: "Telegram",
      notifications: "Доставка сповіщень",
      conversation_storage: "Сховище діалогів",
      scheduler: "Планувальник",
      media: "Особисті фото",
      frontend: "Ресурси панелі",
      presence: "Присутність",
      recipes: "Джерело рецептів",
      conversation: "Мовний помічник",
      mikrotik: "Родинна мережа",
      digests: "Родинні зведення",
      school_retention: "Шкільні нагадування",
      backup: "Резервні копії",
    }),
    events: Object.freeze({
      tasks: "Завдання",
      alarms: "Перевірки пробудження",
      shopping: "Покупки",
      court: "Родинний суд",
      routines: "Рутини",
      rewards: "Заохочення",
      calendar: "Календар",
      network: "Родинна мережа",
      telegram_reply: "Особиста відповідь Telegram",
      telegram_poll_reply: "Родинне голосування",
      family_digest: "Родинне зведення",
      pantry_expiry: "Нагадування про запаси",
      school_preparation_reminder: "Шкільне нагадування",
    }),
  }),
});

const PARENTS = new Set(["owner", "parent"]);
const ISSUE_STATES = new Set(["uncertain", "failed", "awaiting_channel"]);
const ACTION_STATES = new Set(["uncertain", "failed"]);
const HEALTHY_STATES = new Set(["connected", "network_connected"]);
const MAX_HEALTH_ROWS = 50;
const MAX_DELIVERY_ROWS = 100;

const node = (tag, text, className) => {
  const result = document.createElement(tag);
  if (text !== undefined && text !== null) result.textContent = String(text);
  if (className) result.className = className;
  return result;
};

function language(card) {
  const value = card?._config?.language || card?._hass?.language?.split("-")[0] || "en";
  return Object.hasOwn(HEALTH_COPY, value) ? value : "en";
}

function plain(value) {
  return value && typeof value === "object" && !Array.isArray(value);
}

function accessFor(card, data) {
  if (!plain(data) || !PARENTS.has(data.role) || typeof data.actor !== "string") return null;
  const actor = Array.isArray(data.members)
    ? data.members.find((member) => member?.id === data.actor)
    : null;
  if (
    !actor ||
    actor.active !== true ||
    actor.role !== data.role ||
    !Number.isSafeInteger(actor.revision) ||
    actor.revision < 1
  )
    return null;
  return {
    actor: data.actor,
    actorRevision: actor.revision,
    entry: card._entry,
    generation: card._generation,
  };
}

function access(card) {
  return accessFor(card, card?._data);
}

function sameAccess(card, expected) {
  const current = access(card);
  return Boolean(current && expected && JSON.stringify(current) === JSON.stringify(expected));
}

function healthRows(data) {
  if (!plain(data?.health)) return [];
  return Object.entries(data.health).filter(
    ([module, status]) => typeof module === "string" && typeof status === "string",
  );
}

export function countHealthAttention(health) {
  return healthRows({ health }).filter(([, status]) => !HEALTHY_STATES.has(status)).length;
}

function deliveryRows(data) {
  if (!Array.isArray(data?.delivery_issues)) return [];
  return data.delivery_issues.filter(
    (issue) =>
      plain(issue) &&
      typeof issue.id === "string" &&
      issue.id.length > 0 &&
      typeof issue.recipient === "string" &&
      issue.recipient.length > 0 &&
      typeof issue.key === "string" &&
      typeof issue.state === "string" &&
      ISSUE_STATES.has(issue.state) &&
      Number.isSafeInteger(issue.attempts) &&
      issue.attempts >= 0 &&
      typeof issue.created_at === "string",
  );
}

function statusLabel(copy, lang, status) {
  if (Object.hasOwn(copy, status) && typeof copy[status] === "string") return copy[status];
  const known = ERRORS[lang]?.[status];
  return Object.hasOwn(ERRORS[lang] || {}, status) && typeof known === "string"
    ? known
    : copy.unknownStatus;
}

function eventLabel(copy, key) {
  if (Object.hasOwn(copy.events, key) && typeof copy.events[key] === "string") {
    return copy.events[key];
  }
  if (key.startsWith("task_")) return copy.events.tasks;
  if (key.startsWith("alarm_")) return copy.events.alarms;
  if (key.startsWith("shopping_")) return copy.events.shopping;
  if (key.startsWith("court_")) return copy.events.court;
  if (key.startsWith("routine_")) return copy.events.routines;
  if (key.startsWith("reward_")) return copy.events.rewards;
  if (key.startsWith("calendar_")) return copy.events.calendar;
  if (key.startsWith("network_")) return copy.events.network;
  return copy.unknownNotification;
}

function formattedTime(card, value, copy) {
  const match =
    typeof value === "string" && value.length <= 64
      ? /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/.exec(
          value,
        )
      : null;
  if (!match) return copy.unknownTime;
  const [, yearText, monthText, dayText, hourText, minuteText, secondText] = match;
  const year = Number(yearText);
  const month = Number(monthText);
  const day = Number(dayText);
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  if (
    year < 1 ||
    month < 1 ||
    month > 12 ||
    day < 1 ||
    day > days[month - 1] ||
    Number(hourText) > 23 ||
    Number(minuteText) > 59 ||
    Number(secondText) > 59
  )
    return copy.unknownTime;
  const instant = new Date(value);
  if (!Number.isFinite(instant.getTime())) return copy.unknownTime;
  const zone = card?._data?.settings?.timezone;
  try {
    return new Intl.DateTimeFormat(language(card), {
      dateStyle: "medium",
      timeStyle: "short",
      ...(typeof zone === "string" && zone ? { timeZone: zone } : {}),
    }).format(instant);
  } catch {
    return copy.unknownTime;
  }
}

function sameIssue(left, right) {
  return (
    Boolean(left && right) &&
    left.id === right.id &&
    left.key === right.key &&
    left.state === right.state &&
    left.attempts === right.attempts &&
    left.created_at === right.created_at &&
    left.recipient === right.recipient
  );
}

function issueCurrent(card, expectedAccess, expectedIssue) {
  return (
    sameAccess(card, expectedAccess) &&
    deliveryRows(card._data).some((issue) => sameIssue(issue, expectedIssue))
  );
}

function button(card, text, action, primary = false) {
  const result = node("button", text, primary ? "primary" : undefined);
  result.type = "button";
  result.disabled = Boolean(card?._writing);
  result.addEventListener("click", action);
  return result;
}

function review(card, actions, issue, expectedAccess, copy, retry) {
  if (card?._writing || !issueCurrent(card, expectedAccess, issue) || !actions.isConnected) return;
  const form = node("form", null, "health-review");
  form.append(node("p", retry ? copy.retryWarning : copy.resolveWarning, "notice"));
  const reasonLabel = node("label", copy.reason);
  const reason = node("input");
  reason.name = "reason";
  reason.required = true;
  reason.maxLength = 500;
  reasonLabel.append(reason);
  form.append(reasonLabel);
  let confirmed = null;
  if (retry) {
    const consent = node("label", copy.retryConsent, "health-consent");
    confirmed = node("input");
    confirmed.type = "checkbox";
    confirmed.name = "confirmed";
    confirmed.required = true;
    consent.prepend(confirmed);
    form.append(consent);
  }
  const save = node("button", copy.save, "primary");
  save.type = "submit";
  save.disabled = Boolean(card?._writing);
  form.append(save);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (
      card?._writing ||
      !form.isConnected ||
      !issueCurrent(card, expectedAccess, issue) ||
      typeof card.command !== "function"
    )
      return;
    const value = reason.value.trim();
    if (!value || (retry && confirmed?.checked !== true)) return;
    void card.command(
      retry ? "notifications.retry" : "notifications.resolve",
      retry
        ? { id: issue.id, reason: value, confirmed: true }
        : { id: issue.id, reason: value },
    );
  });
  actions.replaceChildren(form);
  reason.focus();
}

function metric(label, value) {
  const result = node("div", null, "metric health-metric");
  result.append(node("b", value), node("span", label));
  return result;
}

export function renderHealth(card, body) {
  if (body?.nodeType !== 1) return false;
  const lang = language(card);
  const copy = HEALTH_COPY[lang];
  const expectedAccess = access(card);
  const section = node("section", null, "health-view");
  section.append(node("style", `
    .health-view{display:grid;gap:16px;min-width:0}
    .health-components,.health-deliveries{display:grid;gap:8px;min-width:0}
    .health-components h3,.health-deliveries h3{margin:0}
    .health-delivery{display:grid;gap:8px;min-width:0}
    .health-delivery strong,.health-delivery time{overflow-wrap:anywhere}
    .health-metrics{grid-template-columns:repeat(auto-fit,minmax(130px,1fr))}
  `));
  body.append(section);
  if (!expectedAccess) {
    section.append(node("p", copy.parentsOnly, "empty"));
    return false;
  }

  const signals = healthRows(card._data);
  const issues = deliveryRows(card._data).slice(-MAX_DELIVERY_ROWS);
  const metrics = node("div", null, "metrics health-metrics");
  metrics.setAttribute("aria-label", copy.summary);
  metrics.append(
    metric(copy.healthSignals, countHealthAttention(card._data.health)),
    metric(copy.deliveryIssues, issues.length),
  );
  section.append(metrics);

  const componentSection = node("section", null, "health-components");
  componentSection.append(node("h3", copy.components));
  if (!signals.length) componentSection.append(node("p", copy.noHealthIssues, "empty"));
  for (const [module, status] of signals.slice(0, MAX_HEALTH_ROWS)) {
    const row = node("div", null, "item health-row");
    row.append(
      node(
        "strong",
        Object.hasOwn(copy.modules, module) && typeof copy.modules[module] === "string"
          ? copy.modules[module]
          : copy.unknownModule,
      ),
      node("p", statusLabel(copy, lang, status), "sub"),
    );
    componentSection.append(row);
  }
  if (signals.length > MAX_HEALTH_ROWS) {
    componentSection.append(
      node("p", `${copy.moreSignals}: ${signals.length - MAX_HEALTH_ROWS}`, "empty"),
    );
  }
  section.append(componentSection);

  const deliverySection = node("section", null, "health-deliveries");
  deliverySection.append(node("h3", copy.deliveries));
  if (!issues.length) deliverySection.append(node("p", copy.noDeliveryIssues, "empty"));
  for (const currentIssue of issues) {
    const issue = Object.freeze({ ...currentIssue });
    const item = node("article", null, "item health-delivery");
    const actions = node("div", null, "actions");
    item.append(
      node("strong", `${eventLabel(copy, issue.key)} · ${copy[issue.state]}`),
      node("time", formattedTime(card, issue.created_at, copy), "sub"),
      actions,
    );
    if (ACTION_STATES.has(issue.state)) {
      actions.append(
        button(card, copy.retryDelivery, () =>
          review(card, actions, issue, expectedAccess, copy, true),
        ),
        button(card, copy.resolveDelivery, () =>
          review(card, actions, issue, expectedAccess, copy, false),
        ),
      );
    } else {
      item.append(node("p", copy.channelHint, "sub"));
    }
    deliverySection.append(item);
  }
  section.append(deliverySection);
  return true;
}

function signature(card, data) {
  const current = accessFor(card, data);
  return JSON.stringify({
    access: current,
    health: healthRows(data),
    issues: deliveryRows(data),
  });
}

export function reconcileHealthRefresh(card, previousData) {
  if (card?._view !== "health" || !card.shadowRoot?.querySelector(".health-view")) return false;
  return signature(card, previousData) !== signature(card, card._data);
}
