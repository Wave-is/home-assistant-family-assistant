/* Generic card availability states. Never interpolate projected family data. */

export const AVAILABILITY_COPY = Object.freeze({
  en: Object.freeze({
    loadingTitle: "Loading this card",
    loadingBody: "Loading current information…",
    moduleTitle: "Module unavailable",
    moduleBody: "This module is disabled for this household.",
    roleTitle: "Card unavailable",
    roleBody: "This card is not available for this account.",
    errorTitle: "Could not load this card",
    errorBody: "No family information is shown until loading succeeds.",
    retry: "Try again",
  }),
  ru: Object.freeze({
    loadingTitle: "Загрузка карточки",
    loadingBody: "Загружаю актуальные данные…",
    moduleTitle: "Модуль недоступен",
    moduleBody: "Этот модуль выключен для данной семьи.",
    roleTitle: "Карточка недоступна",
    roleBody: "Эта карточка недоступна для данной учётной записи.",
    errorTitle: "Не удалось загрузить карточку",
    errorBody: "Семейные данные не показываются, пока загрузка не завершится успешно.",
    retry: "Повторить",
  }),
  uk: Object.freeze({
    loadingTitle: "Завантаження картки",
    loadingBody: "Завантажую актуальні дані…",
    moduleTitle: "Модуль недоступний",
    moduleBody: "Цей модуль вимкнено для цієї родини.",
    roleTitle: "Картка недоступна",
    roleBody: "Ця картка недоступна для цього облікового запису.",
    errorTitle: "Не вдалося завантажити картку",
    errorBody: "Сімейні дані не показуються, доки завантаження не завершиться успішно.",
    retry: "Повторити",
  }),
});

const STATES = new Set(["loading", "module_disabled", "role_unavailable", "error"]);

function language(card) {
  const value = card?._config?.language || card?._hass?.language?.split("-")[0] || "en";
  return Object.hasOwn(AVAILABILITY_COPY, value) ? value : "en";
}

export function availabilityState(card, module, projection) {
  if (card?._error) return "error";
  if (!card?._data) return "loading";
  const modules = card._data.settings?.modules;
  if (!Array.isArray(modules) || typeof module !== "string" || !modules.includes(module)) {
    return "module_disabled";
  }
  if (projection === null || projection === undefined) return "role_unavailable";
  return null;
}

function node(tag, text, className) {
  const value = document.createElement(tag);
  if (className) value.className = className;
  if (text !== undefined) value.textContent = text;
  return value;
}

export function renderAvailabilityShell(card, body, { module, projection, state } = {}) {
  const current = state === undefined ? availabilityState(card, module, projection) : state;
  if (current === null) return null;
  if (!STATES.has(current) || body?.nodeType !== 1 || typeof body.append !== "function") return null;

  const copy = AVAILABILITY_COPY[language(card)];
  const labels = {
    loading: [copy.loadingTitle, copy.loadingBody],
    module_disabled: [copy.moduleTitle, copy.moduleBody],
    role_unavailable: [copy.roleTitle, copy.roleBody],
    error: [copy.errorTitle, copy.errorBody],
  };
  const shell = node("section", undefined, `availability-shell availability-${current}`);
  shell.dataset.state = current;
  shell.setAttribute("aria-live", current === "error" ? "assertive" : "polite");
  shell.setAttribute("aria-busy", current === "loading" ? "true" : "false");
  shell.setAttribute("role", current === "error" ? "alert" : "status");
  shell.append(
    node("h3", labels[current][0], "availability-title"),
    node("p", labels[current][1], current === "error" ? "notice" : "empty"),
  );
  if (current === "error") {
    const retry = node("button", copy.retry, "availability-retry");
    retry.type = "button";
    // refresh() renders its catch branch before clearing _loading in finally.
    // Keeping this button enabled is safe: refresh itself rejects overlap.
    retry.disabled = Boolean(card?._writing);
    retry.addEventListener("click", () => {
      if (!retry.isConnected || retry.disabled || typeof card?.refresh !== "function") return;
      void card.refresh();
    });
    shell.append(retry);
  }
  body.append(shell);
  return current;
}
