/* Shopping item rendering and copy for Family Assistant card. */

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
    label_creator: "Added by",
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
    label_creator: "Добавил(а)",
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
    label_creator: "Додав(ла)",
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
  try {
    await card.command(action, payload);
    if (card._generation === generationAtStart) {
      if (!card._actionError) {
        card._shoppingItemAction = null;
        card.render();
      }
    }
    return true;
  } catch {
    return false;
  }
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

        const numVal = round6(parseFloat(enteredVal));
        actionState.draftQuantity = enteredVal;
        const payload = {
          id: item.id,
          revision: actionState.targetRevision !== undefined ? actionState.targetRevision : item.revision,
          quantity: numVal,
          unit: actionState.targetUnit !== undefined ? actionState.targetUnit : (item.unit != null ? item.unit : "")
        };
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
          if (entry.detail.sources && Array.isArray(entry.detail.sources)) {
            const srcNames = entry.detail.sources.map(sid => getItemDisplayName(card, sid));
            detailParts.push(`${copy.source_items_label}: ${srcNames.join(", ")}`);
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
