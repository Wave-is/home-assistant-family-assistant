export const PERSONAL_TASK_COPY = {
  en: {
    label: "Personal reminder — only for me",
    hint: "Only you can see or finish this reminder in Family Assistant. Its notifications are private; no parent review, penalties or reassignment.",
    badge: "🔒 Personal reminder",
  },
  ru: {
    label: "Личное напоминание — только для меня",
    hint: "В Family Assistant это напоминание видите и завершаете только вы. Уведомления личные; без проверки родителями, штрафов и переназначения.",
    badge: "🔒 Личное напоминание",
  },
  uk: {
    label: "Особисте нагадування — лише для мене",
    hint: "У Family Assistant це нагадування бачите й завершуєте лише ви. Сповіщення особисті; без перевірки батьками, штрафів і перепризначення.",
    badge: "🔒 Особисте нагадування",
  },
};

export const personalTaskCopy = card => PERSONAL_TASK_COPY[
  card._config?.language || card._hass?.language?.split("-")[0]
] || PERSONAL_TASK_COPY.en;
