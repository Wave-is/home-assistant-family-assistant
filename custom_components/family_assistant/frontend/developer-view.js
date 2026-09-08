/* Explicit owner preview and local download. No telemetry or automatic uploads. */
export const DEVELOPER_COPY = {
  en: {
    title: "Help improve the assistant", enabled: "Technical collection is enabled.",
    disabled: "Technical collection is disabled.",
    hint: "The owner can change consent in Configure → Developer diagnostics. Existing counts are kept when disabled. Only future queued Telegram model failures are counted; no messages, names, IDs, URLs or exact times are collected here.",
    limit: "This report helps locate technical failures, but cannot reproduce a misunderstood command. Nothing is sent automatically. Review the complete JSON before sharing it with a developer.",
    preview: "Review technical report", download: "Download reviewed JSON", close: "Close preview",
    busy: "Reading report…", error: "The report or access changed. Refresh and review again.",
    groups: "Recorded error categories", unavailable: "Diagnostic storage needs review; collection is stopped.",
  },
  ru: {
    title: "Помочь улучшить помощника", enabled: "Сбор технических ошибок включён.",
    disabled: "Сбор технических ошибок выключен.",
    hint: "Владелец меняет согласие в Настроить → Диагностика для разработчика. При отключении прежние счётчики сохраняются. Учитываются только будущие технические сбои запросов Telegram к модели: без сообщений, имён, ID, адресов и точного времени.",
    limit: "Отчёт помогает найти технический сбой, но не воспроизводит неправильно понятую команду. Ничего не отправляется автоматически. Проверьте весь JSON перед передачей разработчику.",
    preview: "Проверить технический отчёт", download: "Скачать проверенный JSON", close: "Закрыть просмотр",
    busy: "Читаю отчёт…", error: "Отчёт или доступ изменились. Обновите страницу и проверьте заново.",
    groups: "Категорий ошибок записано", unavailable: "Хранилище диагностики требует проверки; сбор остановлен.",
  },
  uk: {
    title: "Допомогти покращити помічника", enabled: "Збір технічних помилок увімкнено.",
    disabled: "Збір технічних помилок вимкнено.",
    hint: "Власник змінює згоду в Налаштувати → Діагностика для розробника. Після вимкнення попередні лічильники зберігаються. Враховуються лише майбутні технічні збої запитів Telegram до моделі: без повідомлень, імен, ID, адрес та точного часу.",
    limit: "Звіт допомагає знайти технічний збій, але не відтворює неправильно зрозумілу команду. Нічого не надсилається автоматично. Перевірте весь JSON перед передаванням розробнику.",
    preview: "Перевірити технічний звіт", download: "Завантажити перевірений JSON", close: "Закрити перегляд",
    busy: "Читаю звіт…", error: "Звіт або доступ змінилися. Оновіть сторінку та перевірте знову.",
    groups: "Категорій помилок записано", unavailable: "Сховище діагностики потребує перевірки; збір зупинено.",
  },
};
const CODES = new Set(["provider_not_configured", "provider_timeout", "provider_unreachable",
  "provider_authentication", "provider_model_missing", "provider_bad_response",
  "invalid_model_plan", "search_not_configured", "other"]);
const LIMITS = ["technical_observations_only", "no_message_content", "not_a_semantic_reproducer"];
const exact = (value, keys) => value && !Array.isArray(value) && typeof value === "object" &&
  Object.keys(value).sort().join(",") === [...keys].sort().join(",");
const bounded = (value, min, max) => Number.isSafeInteger(value) && value >= min && value <= max;

export function reportJSON(value) {
  if (!exact(value, ["format", "schema", "version", "cases", "overflow_count", "saturated", "limitations"]) ||
      value.format !== "family_assistant_defect_report" || value.schema !== 1 ||
      typeof value.version !== "string" || value.version.length > 64 ||
      !/^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-(?:alpha|beta|rc)\.(?:0|[1-9][0-9]*))?$/.test(value.version) ||
      /\s/.test(value.version) || !Array.isArray(value.cases) || value.cases.length > 64 ||
      !bounded(value.overflow_count, 0, 999999) || typeof value.saturated !== "boolean" ||
      JSON.stringify(value.limitations) !== JSON.stringify(LIMITS)) throw new Error("invalid_report");
  const seen = new Set();
  for (const row of value.cases) {
    if (!exact(row, ["stage", "code", "has_quote", "has_refs", "count"]) ||
        row.stage !== "assistant_job" || !CODES.has(row.code) ||
        typeof row.has_quote !== "boolean" || typeof row.has_refs !== "boolean" ||
        !bounded(row.count, 1, 999999)) throw new Error("invalid_report");
    const key = JSON.stringify([row.code, row.has_quote, row.has_refs]);
    if (seen.has(key)) throw new Error("invalid_report");
    seen.add(key);
  }
  return JSON.stringify(value, null, 2) + "\n";
}

const node = (tag, text, css) => {
  const el = document.createElement(tag);
  if (text != null) el.textContent = text;
  if (css) el.className = css;
  return el;
};
function scope(card) {
  const data = card._data, member = data?.members?.find(m => m.id === data.actor);
  if (data?.role !== "owner" || !member?.active || member.role !== "owner" ||
      !card.isConnected || !card._entry || !card._hass?.user?.id ||
      data.developer_diagnostics?.available !== true) return null;
  return JSON.stringify([card._entry, card._generation, card._hass.user.id,
    data.actor, member.revision, data.developer_diagnostics]);
}

export function renderDeveloper(card, body) {
  const config = card._data?.developer_diagnostics;
  if (card._data?.role !== "owner" || !config) return;
  const lang = (card._config?.language || card._hass?.language || "en").split("-")[0];
  const c = DEVELOPER_COPY[lang] || DEVELOPER_COPY.en;
  const section = node("section", null, "developer-view");
  section.append(node("h3", c.title), node("p", config.available === false ? c.unavailable :
    config.enabled ? c.enabled : c.disabled), node("p", c.hint, "sub"));
  body.append(section);
  if (config.available !== true) return;
  section.append(node("p", `${c.groups}: ${bounded(config.count, 0, 64) ? config.count : 0}`));
  const expected = scope(card);
  if (!expected) return;
  const user = card._hass.user;
  const valid = () => section.isConnected && scope(card) === expected && card._hass?.user === user;
  const actions = node("div", null, "actions"), content = node("div");
  const preview = node("button", c.preview), status = node("p", "", "sub");
  preview.type = "button";
  status.setAttribute("role", "status");
  actions.append(preview);
  section.append(actions, status, content);
  let busy = false;
  const read = async () => reportJSON(await card._hass.callWS({
    type: "family_assistant/developer_report", entry_id: card._entry,
    expected_generation: config.generation,
  }));
  preview.addEventListener("click", async () => {
    if (!valid() || busy) return;
    busy = true; preview.disabled = true; content.replaceChildren(); status.textContent = c.busy;
    try {
      const json = await read();
      if (!valid()) return;
      status.textContent = "";
      const pre = node("pre", json, "developer-json");
      pre.style.whiteSpace = "pre-wrap"; pre.style.overflowWrap = "anywhere";
      pre.tabIndex = 0;
      const download = node("button", c.download), close = node("button", c.close);
      download.type = close.type = "button";
      close.addEventListener("click", () => { content.replaceChildren(); });
      download.addEventListener("click", async () => {
        if (!valid() || !download.isConnected || busy) return;
        busy = true; download.disabled = true;
        try {
          const fresh = await read();
          if (!valid() || !download.isConnected) return;
          if (fresh !== json) throw new Error("changed_report");
          const url = URL.createObjectURL(new Blob([json], {type: "application/json"}));
          const link = node("a"); link.href = url;
          link.download = "family-assistant-technical-report.json";
          section.append(link);
          try { link.click(); } finally { link.remove(); setTimeout(() => URL.revokeObjectURL(url), 0); }
        } catch { if (valid()) { content.replaceChildren(); status.textContent = c.error; } }
        finally { busy = false; download.disabled = false; }
      });
      content.append(node("p", c.limit), pre, download, close);
    } catch { if (valid()) status.textContent = c.error; }
    finally { busy = false; preview.disabled = false; }
  });
}
