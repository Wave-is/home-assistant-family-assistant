/* Shopping item rendering and copy for Family Assistant card. */
import { PRICE_COPY, parsePrice, renderPriceFields } from "./shopping-price.js";

export const SHOPPING_ITEM_COPY = {
  en: {
    status_pending: "Pending approval",
    status_approved: "Ready to buy",
    status_purchased: "Bought",
    status_rejected: "Rejected",
    status_archived: "Archived",
    status_merged: "Merged",
    status_unknown: "Unknown status",
    action_approve: "Approve",
    action_reject: "Reject",
    action_archive: "Archive",
    action_buy_remaining: "Bought remaining",
    action_partial_purchase: "Partial purchase",
    action_merge: "Merge items",
    action_confirm_archive: "Confirm archive",
    action_confirm_merge: "Confirm merge",
    action_cancel: "Cancel",
    action_retry: "Retry",
    action_submit: "Save",
    action_edit: "Edit details",
    action_review: "Review",
    action_confirm_add: "Add to shopping list",
    action_confirm_edit: "Save reviewed changes",
    action_back: "Back",
    action_start_new: "Start a new edit",
    editor_add_title: "Add shopping item",
    editor_edit_title: "Edit shopping item",
    label_no_buyer: "No assigned buyer",
    note_shared: "The note is visible to every active household member. It is not private.",
    child_pending: "This child proposal will wait for parent approval.",
    occurrence_only: "This changes only this generated occurrence, not its recurring template.",
    uncertainty: "The request may already have succeeded. Check the list before starting a different edit.",
    error_invalid_form: "Check the highlighted item details.",
    changed_fields: "Changed fields",
    label_creator: "Added by",
    label_name: "Name",
    label_buyer: "Assigned to",
    label_category: "Category",
    label_store: "Store",
    label_note: "Note",
    label_quantity: "Quantity",
    label_purchased: "Purchased",
    label_remaining: "Remaining",
    label_unit: "Unit",
    label_history: "Item history",
    label_no_history: "No recorded history",
    label_select_candidates: "Select items to merge into this item (up to 19):",
    label_no_candidates: "No mergeable candidates found",
    label_total_after_merge: "Total quantity after merge",
    label_total_purchased_after_merge: "Total purchased after merge",
    warning_merge_sources_retained: "Notice: Merged source items will be marked as merged and retained in archive.",
    error_invalid_quantity: "Please enter a valid positive quantity up to remaining amount (max 6 decimal places).",
    error_no_selection: "Select at least one item to merge.",
    archive_title: "Archived & Completed Items",
    archive_empty: "No archived items",
    history_action_add: "Added",
    history_action_approve: "Approved",
    history_action_reject: "Rejected",
    history_action_archive: "Archived",
    history_action_purchase: "Purchased",
    history_action_merge: "Merged sources into item",
    history_action_edit: "Edited details",
    history_action_merged: "Merged into another item",
    history_show_more: "Show more history",
    unknown_member: "Unknown member",
    unknown_item: "Unknown item",
    source_items_label: "Source items",
    merged_into_label: "Merged into"
  },
  ru: {
    status_pending: "Ожидает подтверждения",
    status_approved: "Можно покупать",
    status_purchased: "Куплено",
    status_rejected: "Отклонено",
    status_archived: "В архиве",
    status_merged: "Объединено",
    status_unknown: "Неизвестный статус",
    action_approve: "Одобрить",
    action_reject: "Отклонить",
    action_archive: "В архив",
    action_buy_remaining: "Куплено: весь остаток",
    action_partial_purchase: "Частичная покупка",
    action_merge: "Объединить",
    action_confirm_archive: "Подтвердить архивацию",
    action_confirm_merge: "Подтвердить объединение",
    action_cancel: "Отмена",
    action_retry: "Повторить",
    action_submit: "Сохранить",
    action_edit: "Изменить данные",
    action_review: "Проверить",
    action_confirm_add: "Добавить в список покупок",
    action_confirm_edit: "Сохранить проверенные изменения",
    action_back: "Назад",
    action_start_new: "Начать новое изменение",
    editor_add_title: "Добавить покупку",
    editor_edit_title: "Изменить покупку",
    label_no_buyer: "Покупатель не назначен",
    note_shared: "Заметку видят все активные участники семьи. Она не является личной.",
    child_pending: "Предложение ребёнка будет ждать подтверждения родителя.",
    occurrence_only: "Изменится только эта созданная позиция, а не её регулярный шаблон.",
    uncertainty: "Запрос уже мог выполниться. Проверьте список перед новым изменением.",
    error_invalid_form: "Проверьте выделенные данные покупки.",
    changed_fields: "Изменённые поля",
    label_creator: "Добавил(а)",
    label_name: "Название",
    label_buyer: "Покупатель",
    label_category: "Категория",
    label_store: "Магазин",
    label_note: "Заметка",
    label_quantity: "Количество",
    label_purchased: "Куплено",
    label_remaining: "Осталось",
    label_unit: "Единица",
    label_history: "История изменений",
    label_no_history: "История отсутствует",
    label_select_candidates: "Выберите элементы для объединения (до 19):",
    label_no_candidates: "Подходящие элементы для объединения не найдены",
    label_total_after_merge: "Итоговое количество после объединения",
    label_total_purchased_after_merge: "Всего куплено после объединения",
    warning_merge_sources_retained: "Внимание: Исходные элементы будут помечены как объединенные и сохранены в архиве.",
    error_invalid_quantity: "Введите корректное положительное число не больше остатка (до 6 знаков).",
    error_no_selection: "Выберите хотя бы один элемент для объединения.",
    archive_title: "Архив и завершенные покупки",
    archive_empty: "В архиве пусто",
    history_action_add: "Добавлено",
    history_action_approve: "Одобрено",
    history_action_reject: "Отклонено",
    history_action_archive: "Архивировано",
    history_action_purchase: "Куплено",
    history_action_merge: "Объединены элементы в этот пункт",
    history_action_edit: "Изменены данные",
    history_action_merged: "Объединено с другим элементом",
    history_show_more: "Показать больше истории",
    unknown_member: "Неизвестный участник",
    unknown_item: "Неизвестный пункт",
    source_items_label: "Исходные пункты",
    merged_into_label: "Объединено в"
  },
  uk: {
    status_pending: "Очікує підтвердження",
    status_approved: "Можна купувати",
    status_purchased: "Куплено",
    status_rejected: "Відхилено",
    status_archived: "В архіві",
    status_merged: "Об'єднано",
    status_unknown: "Невідомий статус",
    action_approve: "Схвалити",
    action_reject: "Відхилити",
    action_archive: "В архів",
    action_buy_remaining: "Куплено: увесь залишок",
    action_partial_purchase: "Часткова покупка",
    action_merge: "Об'єднати",
    action_confirm_archive: "Підтвердити архівування",
    action_confirm_merge: "Підтвердити об'єднання",
    action_cancel: "Скасувати",
    action_retry: "Повторити",
    action_submit: "Зберегти",
    action_edit: "Змінити дані",
    action_review: "Перевірити",
    action_confirm_add: "Додати до списку покупок",
    action_confirm_edit: "Зберегти перевірені зміни",
    action_back: "Назад",
    action_start_new: "Почати нове редагування",
    editor_add_title: "Додати покупку",
    editor_edit_title: "Змінити покупку",
    label_no_buyer: "Покупця не призначено",
    note_shared: "Примітку бачать усі активні учасники родини. Вона не є приватною.",
    child_pending: "Пропозиція дитини чекатиме на схвалення батьків.",
    occurrence_only: "Зміниться лише ця створена позиція, а не її регулярний шаблон.",
    uncertainty: "Запит уже міг виконатися. Перевірте список перед новим редагуванням.",
    error_invalid_form: "Перевірте виділені дані покупки.",
    changed_fields: "Змінені поля",
    label_creator: "Додав(ла)",
    label_name: "Назва",
    label_buyer: "Покупець",
    label_category: "Категорія",
    label_store: "Магазин",
    label_note: "Примітка",
    label_quantity: "Кількість",
    label_purchased: "Куплено",
    label_remaining: "Залишилося",
    label_unit: "Одиниця",
    label_history: "Історія змін",
    label_no_history: "Історія відсутня",
    label_select_candidates: "Оберіть пункти для об'єднання (до 19):",
    label_no_candidates: "Відповідних пунктів для об'єднання не знайдено",
    label_total_after_merge: "Підсумкова кількість після об'єднання",
    label_total_purchased_after_merge: "Всього куплено після об'єднання",
    warning_merge_sources_retained: "Увага: Вихідні пункти буде позначено як об'єднані та збережено в архіві.",
    error_invalid_quantity: "Введіть коректне додатне число не більше залишку (до 6 знаків).",
    error_no_selection: "Оберіть хоча б один пункт для об'єднання.",
    archive_title: "Архів і завершені покупки",
    archive_empty: "В архіві порожньо",
    history_action_add: "Додано",
    history_action_approve: "Схвалено",
    history_action_reject: "Відхилено",
    history_action_archive: "Архівовано",
    history_action_purchase: "Куплено",
    history_action_merge: "Об'єднано елементи у цей пункт",
    history_action_edit: "Змінено дані",
    history_action_merged: "Об'єднано з іншим пунктом",
    history_show_more: "Показати більше історії",
    unknown_member: "Невідомий учасник",
    unknown_item: "Невідомий пункт",
    source_items_label: "Вихідні пункти",
    merged_into_label: "Об'єднано в"
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
  return SHOPPING_ITEM_COPY[lang] || SHOPPING_ITEM_COPY.en;
}

function normalizeName(val) {
  if (val == null) return "";
  return String(val).normalize("NFC").trim().replace(/\s+/g, " ").toLowerCase();
}

function normalizeExact(val) {
  return val ?? "";
}

function round6(num) {
  return Math.round((Number(num) + Number.EPSILON) * 1e6) / 1e6;
}

function isValidQuantity(strVal, maxRemaining) {
  if (typeof strVal !== "string" && typeof strVal !== "number") return false;
  const s = String(strVal).trim();
  if (!s || !/^\d+(\.\d{1,6})?$/.test(s)) return false;
  const n = parseFloat(s);
  if (!Number.isFinite(n) || n <= 0) return false;
  if (round6(n) > round6(maxRemaining)) return false;
  return true;
}

function getMemberName(card, id) {
  if (!id) return "";
  const members = card._data?.members || [];
  const found = members.find(m => m && m.id === id);
  if (found && found.name) return found.name;
  const copy = getCopy(card);
  return copy.unknown_member;
}

function getItemDisplayName(card, itemId) {
  if (!itemId) return "";
  const allItems = card._data?.shopping || [];
  const found = allItems.find(i => i && i.id === itemId);
  if (found && found.name) return found.name;
  const copy = getCopy(card);
  return copy.unknown_item;
}

function formatHouseholdDate(card, isoDateStr) {
  if (!isoDateStr) return "";
  const timezone =
    card._data?.settings?.timezone ||
    card._hass?.config?.time_zone ||
    "UTC";
  const lang = card._config?.language || card._hass?.language || "en";
  try {
    const d = new Date(isoDateStr);
    return d.toLocaleString(lang, { timeZone: timezone });
  } catch {
    return isoDateStr;
  }
}

function canInteract(card, generationAtStart) {
  if (card._writing) return false;
  if (generationAtStart !== undefined && card._generation !== generationAtStart) return false;
  return true;
}

async function executeCardCommand(card, action, payload, generationAtStart) {
  if (!canInteract(card, generationAtStart)) return false;
  const state = card._shoppingItemAction;
  if (action === "shopping.purchase" && state?.itemId === payload.id && !state.operationId) state.operationId = crypto.randomUUID();
  try {
    await card.command(action, payload, action === "shopping.purchase" ? state?.operationId : undefined);
    if (card._generation === generationAtStart) {
      if (!card._actionError && card._shoppingItemAction === state) {
        card._shoppingItemAction = null;
        card.render();
      }
    }
    return true;
  } catch {
    return false;
  }
}

function currentMember(card, id = card._data?.actor) {
  return (card._data?.members || []).find(member => member?.id === id) || null;
}

function editorScope(card) {
  const actor = currentMember(card);
  if (!actor || actor.active !== true || !["owner", "parent", "adult", "child"].includes(actor.role) || actor.role !== card._data?.role || !Number.isSafeInteger(actor.revision) || actor.revision < 1) return null;
  if (!(card._data?.settings?.modules || []).includes("shopping")) return null;
  return {
    generation: card._generation,
    entry: card._entry,
    actor: actor.id,
    actorRevision: actor.revision,
    role: card._data.role,
    members: JSON.stringify((card._data.members || []).filter(member => member?.active === true && member.role !== "guest").map(member => [member.id, member.role, member.revision]).sort((a, b) => a[0].localeCompare(b[0])))
  };
}

function sameEditorScope(card, source) {
  const current = editorScope(card);
  return Boolean(current && source && Object.keys(current).every(key => current[key] === source[key]));
}

function priceCopy(card) {
  const language = card._config?.language || card._hass?.language?.split("-")[0] || "en";
  return PRICE_COPY[language] || PRICE_COPY.en;
}

function currentPurchaseScope(card, action) {
  if (!sameEditorScope(card, action.priceScope) || action.priceUser !== (card._hass?.user?.id ?? null)) return false;
  const item = (card._data?.shopping || []).find(row => row?.id === action.itemId);
  return Boolean(item && (action.frozenPayload || (item.status === "approved" && item.revision === action.targetRevision && (item.unit ?? "") === action.targetUnit)));
}

function mayEdit(card, item) {
  if (!item || !["pending", "approved"].includes(item.status)) return false;
  const role = card._data?.role;
  if (["owner", "parent"].includes(role)) return true;
  if (role === "adult") return item.status === "approved";
  return role === "child" && item.status === "pending" && item.creator === card._data?.actor;
}

function blankDraft(card, item = null) {
  const source = editorScope(card);
  if (!source || (item && !mayEdit(card, item))) return null;
  return {
    mode: item ? "edit" : "create",
    step: "form",
    source,
    itemId: item?.id || null,
    itemRevision: item?.revision || null,
    itemStatus: item?.status || null,
    itemCreator: item?.creator || null,
    generated: Boolean(item?.series_id || item?.occurrence_id),
    values: {
      name: item?.name || "",
      quantity: String(item?.quantity ?? 1),
      unit: item?.unit || "",
      category: item?.category || "",
      store: item?.store || "",
      note: item?.note || "",
      buyer: item?.buyer || ""
    },
    original: item ? {
      name: item.name || "",
      category: item.category || "",
      store: item.store || "",
      note: item.note || "",
      buyer: item.buyer || ""
    } : null,
    pending: null,
    validation: false
  };
}

export function openShoppingEditor(card, item = null) {
  const draft = blankDraft(card, item);
  if (!draft) return false;
  card._shoppingEditorDraft = draft;
  card._shoppingItemAction = null;
  card._shoppingSeriesDraft = null;
  card._shoppingSeriesFormOpen = false;
  card._shoppingSeriesEditingItem = null;
  card._form = false;
  card._actionError = null;
  if (typeof card.render === "function") card.render();
  return true;
}

export function disposeShoppingEditor(card) {
  card._shoppingEditorDraft = null;
}

export function reconcileShoppingEditorRefresh(card) {
  const draft = card._shoppingEditorDraft;
  const action = card._shoppingItemAction;
  if (action?.priceScope && !currentPurchaseScope(card, action)) {
    card._shoppingItemAction = null;
    disposeShoppingEditor(card);
    return true;
  }
  if (
    action?.type?.startsWith("merge_") &&
    !(card._actionError && action.frozenPayload)
  ) {
    const items = card._data?.shopping || [];
    const snapshots = [action.targetSnapshot, ...(action.candidates || [])];
    if (snapshots.some(snapshot => {
      const current = items.find(item => item?.id === snapshot?.id);
      return !current || current.revision !== snapshot.revision;
    })) {
      card._shoppingItemAction = null;
      card._actionError = "conflict";
      if (!draft) return true;
    }
  }
  if (!draft) return false;
  if (!sameEditorScope(card, draft.source)) {
    disposeShoppingEditor(card);
    return true;
  }
  if (draft.pending) return false;
  if (draft.mode === "edit") {
    const item = (card._data?.shopping || []).find(row => row?.id === draft.itemId);
    if (
      !mayEdit(card, item) ||
      item.revision !== draft.itemRevision ||
      item.status !== draft.itemStatus ||
      item.creator !== draft.itemCreator
    ) {
      disposeShoppingEditor(card);
      card._actionError = "conflict";
      return true;
    }
  }
  const buyer = draft.values?.buyer;
  const selected = buyer ? currentMember(card, buyer) : null;
  if (buyer && (!selected || selected.active !== true || selected.role === "guest")) {
    disposeShoppingEditor(card);
    card._actionError = "conflict";
    return true;
  }
  return false;
}

function validDecimal(value) {
  const raw = String(value ?? "").trim();
  if (!/^(?:0|[1-9]\d*)(?:\.\d{1,6})?$/.test(raw)) return null;
  const parsed = Number(raw);
  return Number.isFinite(parsed) && parsed >= 0.001 && parsed <= 1000000 ? parsed : null;
}

function payloadFor(draft) {
  const values = draft.values;
  const common = {
    name: values.name.trim(),
    category: values.category.trim(),
    store: values.store.trim(),
    note: values.note.trim(),
    buyer: values.buyer || null
  };
  if (draft.mode === "edit") {
    return Object.freeze({id: draft.itemId, revision: draft.itemRevision, ...common});
  }
  return Object.freeze({
    ...common,
    quantity: validDecimal(values.quantity),
    unit: values.unit.trim()
  });
}

function validDraft(card, draft) {
  const values = draft.values;
  if (
    typeof values.name !== "string" ||
    !values.name.trim() ||
    values.name.length > 200 ||
    typeof values.category !== "string" ||
    values.category.length > 80 ||
    typeof values.store !== "string" ||
    values.store.length > 80 ||
    typeof values.note !== "string" ||
    values.note.length > 500 ||
    typeof values.buyer !== "string"
  ) return false;
  if (draft.mode === "create" && (validDecimal(values.quantity) === null || values.unit.length > 32)) return false;
  const buyer = values.buyer ? currentMember(card, values.buyer) : null;
  if (values.buyer && (!buyer || buyer.active !== true || buyer.role === "guest")) return false;
  if (card._data?.role === "child" && values.buyer && values.buyer !== card._data.actor) return false;
  if (draft.mode === "edit") {
    const normalized = {
      name: values.name.trim(),
      category: values.category.trim(),
      store: values.store.trim(),
      note: values.note.trim(),
      buyer: values.buyer
    };
    if (Object.keys(normalized).every(key => normalized[key] === draft.original?.[key])) return false;
  }
  return true;
}

async function submitShoppingDraft(card, draft) {
  if (card._shoppingEditorDraft !== draft || !sameEditorScope(card, draft.source) || card._writing) return;
  if (!draft.pending && (reconcileShoppingEditorRefresh(card) || !validDraft(card, draft))) {
    card._actionError = "conflict";
    card.render();
    return;
  }
  if (!draft.pending) {
    draft.pending = {
      action: draft.mode === "edit" ? "shopping.edit" : "shopping.add",
      payload: payloadFor(draft),
      operationId: crypto.randomUUID()
    };
  }
  const pending = draft.pending;
  await card.command(pending.action, pending.payload, pending.operationId);
  if (card._shoppingEditorDraft !== draft || !sameEditorScope(card, draft.source)) return;
  if (!card._actionError) disposeShoppingEditor(card);
  if (typeof card.render === "function") card.render();
}

function field(form, name, label, value, {type = "text", required = false, maximum} = {}) {
  const wrap = el("label", label);
  const input = name === "note" ? el("textarea") : el("input");
  input.name = name;
  if (input.tagName === "INPUT") input.type = type;
  input.value = value;
  input.required = required;
  if (maximum) input.maxLength = maximum;
  wrap.append(input);
  form.append(wrap);
  return input;
}

function appendReviewLine(host, label, value) {
  host.append(el("p", `${label}: ${value || "—"}`, "sub"));
}

export function renderShoppingEditor(card, body) {
  const copy = getCopy(card);
  const toolbar = el("div", null, "toolbar");
  toolbar.append(el("span", `${card._data?.shopping?.length || 0} ${card.t?.units || ""}`, "sub"));
  if (!card._shoppingEditorDraft && card._data?.role !== "guest") {
    toolbar.append(
      card.button(copy.editor_add_title, () => openShoppingEditor(card), true)
    );
  }
  body.append(toolbar);
  const draft = card._shoppingEditorDraft;
  if (!draft) return toolbar;

  const host = el("section", null, "editor shopping-editor");
  host.dataset.shoppingEditor = draft.mode;
  host.append(el("strong", draft.mode === "edit" ? copy.editor_edit_title : copy.editor_add_title));
  if (draft.generated) host.append(el("p", copy.occurrence_only, "notice"));
  host.append(el("p", copy.note_shared, "sub"));
  if (draft.source.role === "child") host.append(el("p", copy.child_pending, "notice"));

  if (draft.step === "form" && !draft.pending) {
    const form = el("form");
    const controls = {};
    controls.name = field(form, "name", copy.label_name, draft.values.name, {required: true, maximum: 200});
    if (draft.mode === "create") {
      const amountFields = el("div", null, "fields");
      form.append(amountFields);
      controls.quantity = field(amountFields, "quantity", copy.label_quantity, draft.values.quantity, {required: true});
      controls.unit = field(amountFields, "unit", copy.label_unit, draft.values.unit, {maximum: 32});
    }
    controls.category = field(form, "category", copy.label_category, draft.values.category, {maximum: 80});
    controls.store = field(form, "store", copy.label_store, draft.values.store, {maximum: 80});
    controls.note = field(form, "note", copy.label_note, draft.values.note, {maximum: 500});
    const buyerWrap = el("label", copy.label_buyer);
    const buyer = el("select");
    buyer.name = "buyer";
    buyer.setAttribute("aria-label", copy.label_buyer);
    const none = el("option", copy.label_no_buyer);
    none.value = "";
    buyer.append(none);
    for (const member of (card._data?.members || []).filter(member =>
      member?.active === true && member.role !== "guest" &&
      (draft.source.role !== "child" || member.id === draft.source.actor)
    )) {
      const option = el("option", member.name);
      option.value = member.id;
      buyer.append(option);
    }
    buyer.value = draft.values.buyer;
    buyerWrap.append(buyer);
    form.append(buyerWrap);
    controls.buyer = buyer;
    for (const [name, control] of Object.entries(controls)) {
      control.disabled = Boolean(card._writing);
      control.addEventListener("input", event => {
        if (card._shoppingEditorDraft !== draft || draft.pending || !sameEditorScope(card, draft.source)) return;
        draft.values[name] = event.target.value;
        draft.validation = false;
      });
    }
    if (draft.validation) form.append(el("div", copy.error_invalid_form, "notice"));
    const actions = el("div", null, "actions");
    actions.append(card.button(copy.action_review, () => {
      if (card._shoppingEditorDraft !== draft || !sameEditorScope(card, draft.source)) return;
      if (!validDraft(card, draft)) {
        draft.validation = true;
        card.render();
        return;
      }
      draft.validation = false;
      draft.step = "review";
      card.render();
    }, true));
    actions.append(card.button(copy.action_cancel, () => {
      if (card._shoppingEditorDraft === draft) disposeShoppingEditor(card);
      card._actionError = null;
      card.render();
    }));
    form.append(actions);
    host.append(form);
  } else {
    const review = el("div", null, "shopping-review");
    review.dataset.shoppingReview = draft.mode;
    appendReviewLine(review, copy.label_name, draft.values.name.trim());
    if (draft.mode === "create") {
      appendReviewLine(review, copy.label_quantity, `${draft.values.quantity} ${draft.values.unit}`.trim());
    }
    appendReviewLine(review, copy.label_category, draft.values.category.trim());
    appendReviewLine(review, copy.label_store, draft.values.store.trim());
    appendReviewLine(review, copy.label_note, draft.values.note.trim());
    appendReviewLine(review, copy.label_buyer, draft.values.buyer ? getMemberName(card, draft.values.buyer) : copy.label_no_buyer);
    if (draft.pending && card._actionError) review.append(el("p", copy.uncertainty, "notice"));
    const actions = el("div", null, "actions");
    actions.append(card.button(
      draft.pending && card._actionError ? copy.action_retry :
        draft.mode === "edit" ? copy.action_confirm_edit : copy.action_confirm_add,
      () => submitShoppingDraft(card, draft),
      true
    ));
    if (!draft.pending) {
      actions.append(card.button(copy.action_back, () => { draft.step = "form"; card.render(); }));
      actions.append(card.button(copy.action_cancel, () => { disposeShoppingEditor(card); card.render(); }));
    } else if (card._actionError) {
      actions.append(card.button(copy.action_start_new, () => {
        if (card._shoppingEditorDraft !== draft) return;
        const latest = draft.mode === "edit" ?
          (card._data?.shopping || []).find(row => row?.id === draft.itemId) : null;
        card._shoppingEditorDraft = draft.mode === "edit" && !latest ? null : blankDraft(card, latest);
        card._actionError = null;
        card.render();
      }));
    }
    review.append(actions);
    host.append(review);
  }
  body.append(host);
  return host;
}

export function renderShoppingItem(card, list, item) {
  const row = el("li", null, "item");
  if (list && typeof list.append === "function") {
    list.append(row);
  }
  if (!item) return row;

  const copy = getCopy(card);
  const startGeneration = card._generation;
  const isParent = Boolean(card.parent);
  const isGuest = card._data?.role === "guest";
  const isWriting = Boolean(card._writing);

  const titleRow = el("div", null, "row");
  const titleStrong = el("strong", item.name || "", "grow");
  const statusKey = `status_${item.status || "unknown"}`;
  const statusBadge = el("span", copy[statusKey] || copy.status_unknown, "badge");
  titleRow.append(titleStrong, statusBadge);
  row.append(titleRow);

  const metaParts = [];
  if (item.category) metaParts.push(`${copy.label_category}: ${item.category}`);
  if (item.store) metaParts.push(`${copy.label_store}: ${item.store}`);
  if (item.note) metaParts.push(`${copy.label_note}: ${item.note}`);
  if (item.creator) metaParts.push(`${copy.label_creator}: ${getMemberName(card, item.creator)}`);
  if (item.buyer) metaParts.push(`${copy.label_buyer}: ${getMemberName(card, item.buyer)}`);

  const qty = Number(item.quantity) || 0;
  const purchased = Number(item.purchased) || 0;
  const remaining = round6(Math.max(0, qty - purchased));
  const unitStr = item.unit ? ` ${item.unit}` : "";

  metaParts.push(
    `${copy.label_quantity}: ${round6(qty)}${unitStr} · ${copy.label_purchased}: ${round6(purchased)}${unitStr} · ${copy.label_remaining}: ${remaining}${unitStr}`
  );

  const metaSub = el("div", metaParts.join(" · "), "sub");
  row.append(metaSub);

  // Controls container
  const actionsEl = el("div", null, "actions");
  if (card._shoppingItemAction?.priceScope && !currentPurchaseScope(card, card._shoppingItemAction)) card._shoppingItemAction = null;
  const actionState = card._shoppingItemAction;
  const isCurrentAction = actionState && actionState.itemId === item.id;

  // Helper button using card.button
  const makeBtn = (text, onClick, primary = false, disabled = false) => {
    let btn;
    if (typeof card.button === "function") {
      btn = card.button(text, (e) => {
        if (!canInteract(card, startGeneration)) return;
        onClick(e);
      }, primary);
    } else {
      btn = el("button", text, primary ? "primary" : "");
      btn.type = "button";
      btn.addEventListener("click", (e) => {
        if (!canInteract(card, startGeneration)) return;
        onClick(e);
      });
    }
    btn.disabled = disabled || isWriting;
    return btn;
  };

  if (mayEdit(card, item)) {
    actionsEl.append(makeBtn(copy.action_edit, () => openShoppingEditor(card, item)));
  }

  // 1. Parent controls for pending items: Approve / Reject
  if (isParent && item.status === "pending") {
    const approveBtn = makeBtn(copy.action_approve, () => {
      executeCardCommand(card, "shopping.approve", { id: item.id, revision: item.revision }, startGeneration);
    }, true);
    const rejectBtn = makeBtn(copy.action_reject, () => {
      executeCardCommand(card, "shopping.reject", { id: item.id, revision: item.revision }, startGeneration);
    });
    actionsEl.append(approveBtn, rejectBtn);
  }

  // 2. Non-guest approved items with remaining: Buy remaining / Partial purchase
  if (!isGuest && item.status === "approved" && remaining > 0) {
    const buyRemainingBtn = makeBtn(copy.action_buy_remaining, () => {
      const payload = {
        id: item.id,
        revision: item.revision,
        quantity: remaining,
        unit: item.unit != null ? item.unit : ""
      };
      card._shoppingItemAction = {
        type: "partial_purchase",
        itemId: item.id,
        payload,
        frozenPayload: payload,
        draftQuantity: String(remaining),
        retryReady: false,
        generation: startGeneration
      };
      executeCardCommand(card, "shopping.purchase", payload, startGeneration);
    }, true);
    actionsEl.append(buyRemainingBtn);

    const partialBtn = makeBtn(copy.action_partial_purchase, () => {
      card._shoppingItemAction = {
        type: "partial_purchase",
        itemId: item.id,
        targetRevision: item.revision,
        targetUnit: item.unit != null ? item.unit : "",
        priceScope: editorScope(card),
        priceUser: card._hass?.user?.id ?? null,
        draftQuantity: "",
        frozenPayload: null,
        retryReady: false,
        generation: startGeneration
      };
      card._actionError = null;
      if (typeof card.render === "function") card.render();
    });
    actionsEl.append(partialBtn);
  }

  // 3. Parent: Archive with explicit review
  if (isParent && item.status !== "archived" && item.status !== "merged") {
    const archiveBtn = makeBtn(copy.action_archive, () => {
      const payload = { id: item.id, revision: item.revision };
      card._shoppingItemAction = {
        type: "archive_confirm",
        itemId: item.id,
        targetRevision: item.revision,
        payload,
        frozenPayload: payload,
        retryReady: false,
        generation: startGeneration
      };
      card._actionError = null;
      if (typeof card.render === "function") card.render();
    });
    actionsEl.append(archiveBtn);
  }

  // 4. Parent: Merge items
  if (isParent && item.status === "approved" && remaining > 0) {
    const mergeBtn = makeBtn(copy.action_merge, () => {
      const allItems = card._data?.shopping || [];
      const targetNormName = item.merge_name ?? normalizeName(item.name);
      const targetUnit = normalizeExact(item.unit);
      const targetCat = normalizeExact(item.category);
      const targetStore = normalizeExact(item.store);
      const targetNote = normalizeExact(item.note);
      const targetBuyer = normalizeExact(item.buyer);

      const candidateSnapshots = allItems
        .filter(other => {
          if (!other || other.id === item.id) return false;
          if (other.status !== "approved") return false;
          const otherRem = round6((Number(other.quantity) || 0) - (Number(other.purchased) || 0));
          if (otherRem <= 0) return false;

          return (
            (other.merge_name ?? normalizeName(other.name)) === targetNormName &&
            normalizeExact(other.unit) === targetUnit &&
            normalizeExact(other.category) === targetCat &&
            normalizeExact(other.store) === targetStore &&
            normalizeExact(other.note) === targetNote &&
            normalizeExact(other.buyer) === targetBuyer
          );
        })
        .map(other => ({
          id: other.id,
          revision: other.revision,
          name: other.name,
          quantity: Number(other.quantity) || 0,
          purchased: Number(other.purchased) || 0,
          remaining: round6((Number(other.quantity) || 0) - (Number(other.purchased) || 0)),
          unit: other.unit || "",
          buyer: other.buyer || null
        }));

      card._shoppingItemAction = {
        type: "merge_select",
        itemId: item.id,
        targetSnapshot: {
          id: item.id,
          revision: item.revision,
          name: item.name,
          quantity: Number(item.quantity) || 0,
          purchased: Number(item.purchased) || 0,
          unit: item.unit || ""
        },
        candidates: candidateSnapshots,
        selectedIds: [],
        step: 1,
        frozenPayload: null,
        retryReady: false,
        generation: startGeneration
      };
      card._actionError = null;
      if (typeof card.render === "function") card.render();
    });
    actionsEl.append(mergeBtn);
  }

  if (actionsEl.children.length > 0) {
    row.append(actionsEl);
  }

  // Interactive Action Forms (Partial Purchase, Archive Confirm, Merge)
  if (isCurrentAction) {
    const isFailedRetry = Boolean(card._actionError && actionState.frozenPayload);

    // A. Partial purchase form
    if (actionState.type === "partial_purchase") {
      const form = el("form");
      const initialVal = actionState.draftQuantity || "";
      const isInputFrozen = Boolean(actionState.frozenPayload);

      let qtyInput;
      if (typeof card.input === "function") {
        qtyInput = card.input(form, "quantity", copy.label_quantity, "text", initialVal, true);
      } else {
        const wrap = el("label", copy.label_quantity);
        qtyInput = el("input");
        qtyInput.name = "quantity";
        qtyInput.type = "text";
        qtyInput.value = initialVal;
        qtyInput.required = true;
        wrap.append(qtyInput);
        form.append(wrap);
      }
      qtyInput.disabled = isWriting || isInputFrozen;
      qtyInput.addEventListener("input", (e) => {
        if (!canInteract(card, startGeneration) || isInputFrozen) return;
        actionState.draftQuantity = e.target.value;
      });

      const costCopy = priceCopy(card);
      const priceNotice = el("div", costCopy.invalid, "notice");
      priceNotice.setAttribute("role", "alert");
      priceNotice.style.display = "none";
      const priceInputs = renderPriceFields(form, costCopy, actionState, {
        disabled: isWriting || isInputFrozen || !currentPurchaseScope(card, actionState),
        isCurrent: () => form.isConnected && card._shoppingItemAction === actionState && canInteract(card, startGeneration) && currentPurchaseScope(card, actionState),
        onChange: () => { priceNotice.style.display = "none"; }
      });
      form.append(priceNotice);

      const validationNotice = el("div", copy.error_invalid_quantity, "notice");
      validationNotice.style.display = "none";
      form.append(validationNotice);

      const formActions = el("div", null, "actions");
      const submitText = isFailedRetry ? copy.action_retry : copy.action_submit;
      const submitBtn = el("button", submitText, "primary");
      submitBtn.type = "submit";
      submitBtn.disabled = isWriting;
      formActions.append(submitBtn);

      const cancelBtn = makeBtn(copy.action_cancel, () => {
        card._shoppingItemAction = null;
        card._actionError = null;
        if (typeof card.render === "function") card.render();
      });
      formActions.append(cancelBtn);
      form.append(formActions);

      form.addEventListener("submit", (e) => {
        e.preventDefault();
        if (!canInteract(card, startGeneration)) return;
        if (actionState.priceScope && (!form.isConnected || card._shoppingItemAction !== actionState || !currentPurchaseScope(card, actionState))) return;

        if (isFailedRetry && actionState.frozenPayload) {
          executeCardCommand(card, "shopping.purchase", actionState.frozenPayload, startGeneration);
          return;
        }

        const enteredVal = qtyInput.value;
        if (!isValidQuantity(enteredVal, remaining)) {
          validationNotice.style.display = "block";
          return;
        }
        validationNotice.style.display = "none";

        const paid = actionState.includePrice === true ? parsePrice(priceInputs.totalInput.value, priceInputs.currencyInput.value) : null;
        if (actionState.includePrice === true && (!currentPurchaseScope(card, actionState) || !paid)) {
          priceNotice.style.display = "block";
          return;
        }

        const numVal = round6(parseFloat(enteredVal));
        actionState.draftQuantity = enteredVal;
        const payload = {
          id: item.id,
          revision: actionState.targetRevision !== undefined ? actionState.targetRevision : item.revision,
          quantity: numVal,
          unit: actionState.targetUnit !== undefined ? actionState.targetUnit : (item.unit != null ? item.unit : "")
        };
        if (paid) payload.price = paid;
        actionState.frozenPayload = payload;
        executeCardCommand(card, "shopping.purchase", payload, startGeneration);
      });

      row.append(form);
    }

    // B. Archive Confirmation
    if (actionState.type === "archive_confirm") {
      const confirmNotice = el("div", null, "notice");
      confirmNotice.append(el("p", copy.action_confirm_archive));

      const confirmActions = el("div", null, "actions");
      const confirmBtnText = isFailedRetry ? copy.action_retry : copy.action_confirm_archive;
      const confirmBtn = makeBtn(confirmBtnText, () => {
        const payload = actionState.frozenPayload || {
          id: item.id,
          revision: actionState.targetRevision !== undefined ? actionState.targetRevision : item.revision
        };
        actionState.frozenPayload = payload;
        executeCardCommand(card, "shopping.archive", payload, startGeneration);
      }, true);
      confirmActions.append(confirmBtn);

      const cancelBtn = makeBtn(copy.action_cancel, () => {
        card._shoppingItemAction = null;
        card._actionError = null;
        if (typeof card.render === "function") card.render();
      });
      confirmActions.append(cancelBtn);
      confirmNotice.append(confirmActions);
      row.append(confirmNotice);
    }

    // C. Merge UI (Step 1: Selection, Step 2: Confirmation)
    if (actionState.type === "merge_select" || actionState.type === "merge_confirm") {
      const mergeContainer = el("div", null, "notice");

      if (actionState.step === 1 || !actionState.step) {
        // Step 1: Candidate Selection
        const candidates = actionState.candidates || [];
        if (candidates.length === 0) {
          mergeContainer.append(el("p", copy.label_no_candidates));
        } else {
          mergeContainer.append(el("p", copy.label_select_candidates));
          const fieldset = el("fieldset");
          const selectedSet = new Set(actionState.selectedIds || []);

          candidates.forEach(cand => {
            const label = el("label");
            const checkbox = el("input");
            checkbox.type = "checkbox";
            checkbox.value = cand.id;
            checkbox.checked = selectedSet.has(cand.id);
            checkbox.disabled = isWriting;

            checkbox.addEventListener("change", (e) => {
              if (!canInteract(card, startGeneration)) return;
              const curSel = actionState.selectedIds ? [...actionState.selectedIds] : [];
              if (e.target.checked) {
                if (curSel.length < 19 && !curSel.includes(cand.id)) {
                  curSel.push(cand.id);
                } else {
                  e.target.checked = false;
                }
              } else {
                const idx = curSel.indexOf(cand.id);
                if (idx !== -1) curSel.splice(idx, 1);
              }
              actionState.selectedIds = curSel;
              if (typeof card.render === "function") card.render();
            });

            const buyerStr = cand.buyer ? ` · ${copy.label_buyer}: ${getMemberName(card, cand.buyer)}` : "";
            const textSpan = el("span", `${cand.name} (${cand.remaining}${cand.unit ? " " + cand.unit : ""})${buyerStr}`);
            label.append(checkbox, textSpan);
            fieldset.append(label);
          });
          mergeContainer.append(fieldset);
        }

        const step1Actions = el("div", null, "actions");
        const nextBtn = makeBtn(copy.action_merge, () => {
          const selIds = actionState.selectedIds || [];
          if (selIds.length === 0) return;

          const chosenCandidates = (actionState.candidates || []).filter(c => selIds.includes(c.id));
          const sourcesPayload = chosenCandidates.map(c => ({ id: c.id, revision: c.revision }));

          let totalQ = Number(actionState.targetSnapshot.quantity) || 0;
          let totalP = Number(actionState.targetSnapshot.purchased) || 0;
          chosenCandidates.forEach(c => {
            totalQ += c.quantity;
            totalP += c.purchased;
          });

          actionState.frozenPayload = {
            id: actionState.targetSnapshot.id,
            revision: actionState.targetSnapshot.revision,
            sources: sourcesPayload
          };
          actionState.frozenChosenNames = chosenCandidates.map(c => c.name);
          actionState.totalQtyAfter = round6(totalQ);
          actionState.totalPurchasedAfter = round6(totalP);
          actionState.step = 2;
          actionState.type = "merge_confirm";
          if (typeof card.render === "function") card.render();
        }, true, (actionState.selectedIds || []).length === 0);
        step1Actions.append(nextBtn);

        const cancelBtn = makeBtn(copy.action_cancel, () => {
          card._shoppingItemAction = null;
          card._actionError = null;
          if (typeof card.render === "function") card.render();
        });
        step1Actions.append(cancelBtn);
        mergeContainer.append(step1Actions);
      } else if (actionState.step === 2) {
        // Step 2: Explicit Confirmation with warning, chosen names, totals
        mergeContainer.append(el("p", copy.warning_merge_sources_retained));

        const chosenSummary = el("p", `${copy.source_items_label}: ${actionState.frozenChosenNames.join(", ")}`, "sub");
        mergeContainer.append(chosenSummary);

        const totalsSummary = el(
          "p",
          `${copy.label_total_after_merge}: ${actionState.totalQtyAfter}${unitStr} · ${copy.label_total_purchased_after_merge}: ${actionState.totalPurchasedAfter}${unitStr}`
        );
        mergeContainer.append(totalsSummary);

        const step2Actions = el("div", null, "actions");
        const confirmBtnText = isFailedRetry ? copy.action_retry : copy.action_confirm_merge;
        const confirmBtn = makeBtn(confirmBtnText, () => {
          executeCardCommand(card, "shopping.merge", actionState.frozenPayload, startGeneration);
        }, true);
        step2Actions.append(confirmBtn);

        const cancelBtn = makeBtn(copy.action_cancel, () => {
          card._shoppingItemAction = null;
          card._actionError = null;
          if (typeof card.render === "function") card.render();
        });
        step2Actions.append(cancelBtn);
        mergeContainer.append(step2Actions);
      }

      row.append(mergeContainer);
    }
  }

  // History rendering: collapsed details, latest 50 with "Show more", dates in household TZ
  const historyEntries = Array.isArray(item.history) ? item.history : [];
  const historyDetails = el("details");
  const historySummary = el("summary", copy.label_history);
  historyDetails.append(historySummary);

  if (historyEntries.length === 0) {
    historyDetails.append(el("p", copy.label_no_history, "sub"));
  } else {
    const listEl = el("ul", null, "list");
    let visibleCount = 50;

    const renderEntries = () => {
      listEl.replaceChildren();
      const slice = historyEntries.slice(-visibleCount).reverse();
      for (const entry of slice) {
        const itemLi = el("li", null, "sub");
        const dateStr = formatHouseholdDate(card, entry.at);
        const actorName = getMemberName(card, entry.actor);
        const actionStr = entry.detail?.merged_into ? copy.history_action_merged : copy[`history_action_${entry.action}`] || copy.label_history;

        const detailParts = [];
        if (entry.detail && typeof entry.detail === "object") {
          if (entry.detail.amount != null) {
            detailParts.push(`${copy.label_quantity}: ${entry.detail.amount}`);
          } else if (entry.detail.quantity != null) {
            detailParts.push(`${copy.label_quantity}: ${entry.detail.quantity}`);
          }
          if (entry.detail.purchased != null) {
            detailParts.push(`${copy.label_purchased}: ${entry.detail.purchased}`);
          }
          if (entry.detail.remaining != null) {
            detailParts.push(`${copy.label_remaining}: ${entry.detail.remaining}`);
          }
          if (entry.detail.unit) {
            detailParts.push(`${copy.label_unit}: ${entry.detail.unit}`);
          }
          const paid = entry.action === "purchase" && parsePrice(entry.detail.price?.total, entry.detail.price?.currency);
          if (paid) {
            detailParts.push(`${priceCopy(card).history}: ${paid.total} ${paid.currency}`);
            if (typeof entry.detail.name === "string") detailParts.push(`${copy.label_name}: ${entry.detail.name}`);
            if (typeof entry.detail.store === "string" && entry.detail.store) detailParts.push(`${copy.label_store}: ${entry.detail.store}`);
          }
          if (entry.detail.sources && Array.isArray(entry.detail.sources)) {
            const srcNames = entry.detail.sources.map(sid => getItemDisplayName(card, sid));
            detailParts.push(`${copy.source_items_label}: ${srcNames.join(", ")}`);
          }
          if (entry.detail.fields && Array.isArray(entry.detail.fields)) {
            const labels = entry.detail.fields.map(field => copy[`label_${field}`] || field);
            detailParts.push(`${copy.changed_fields}: ${labels.join(", ")}`);
          }
          if (entry.detail.merged_into) {
            const tgtName = getItemDisplayName(card, entry.detail.merged_into);
            detailParts.push(`${copy.merged_into_label}: ${tgtName}`);
          }
        }

        const detailSuffix = detailParts.length > 0 ? ` (${detailParts.join(" · ")})` : "";
        itemLi.textContent = `${dateStr} · ${actorName} · ${actionStr}${detailSuffix}`;
        listEl.append(itemLi);
      }
    };

    renderEntries();
    historyDetails.append(listEl);

    if (historyEntries.length > visibleCount) {
      const moreBtn = makeBtn(copy.history_show_more, () => {
        visibleCount += 50;
        renderEntries();
        if (visibleCount >= historyEntries.length) {
          moreBtn.style.display = "none";
        }
      });
      historyDetails.append(moreBtn);
    }
  }

  row.append(historyDetails);
  return row;
}

export function renderShoppingArchive(card, body) {
  const copy = getCopy(card);
  const details = el("details", null, "shopping-archive");
  const summary = el("summary", copy.archive_title);
  details.append(summary);

  const allItems = card._data?.shopping || [];
  const archivedItems = allItems.filter(item =>
    item && ["purchased", "rejected", "archived", "merged"].includes(item.status)
  );

  if (archivedItems.length === 0) {
    details.append(el("div", copy.archive_empty, "empty"));
  } else {
    const list = el("ul", null, "list");
    for (const item of archivedItems.slice().reverse()) {
      renderShoppingItem(card, list, item);
    }
    details.append(list);
  }

  if (body && typeof body.append === "function") {
    body.append(details);
  }
  return details;
}
