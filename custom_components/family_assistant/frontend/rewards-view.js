/* Rewards view rendering and copy for Family Assistant card. All user content inserted via textContent only. */

export const REWARD_COPY = {
  en: {
    title: "Rewards & privileges", catalog_title: "Catalog", no_catalog: "No rewards in catalog.",
    requests_title: "Requests", no_requests: "No reward requests.", balances_title: "Reward balances",
    no_balances: "No balances available.", terminal_requests: "Completed & closed requests",
    new_reward: "New reward", edit: "Edit", request: "Request", save: "Save", cancel: "Cancel",
    retry: "Retry", approve: "Approve", reject: "Reject", fulfill: "Fulfill", refund: "Refund",
    name: "Name", cost: "Cost (points 1–10000)", description: "Description", enabled: "Available in catalog",
    ttl: "Request TTL (hours, 1–720)", eligible: "Eligible family members", all_members: "All family members",
    member: "Family member", note: "Optional note", reason: "Mandatory reason",
    privilege_note: "User-defined privilege only; no automatic device effect.",
    balance_earned: "Earned", balance_reserved: "Reserved", balance_spent: "Spent",
    balance_available: "Available", balance_debt: "Net debt",
    status_requested: "Requested", status_approved: "Approved", status_fulfilled: "Fulfilled",
    status_rejected: "Rejected", status_cancelled: "Cancelled", status_expired: "Expired",
    status_refunded: "Refunded", history_title: "History", insufficient_funds: "Insufficient available points.",
    unknown_member: "Unknown member", error_cost: "Cost must be an integer between 1 and 10000.",
    error_ttl: "TTL must be an integer between 1 and 720 hours.", error_name: "Name is required.",
    error_reason: "Reason is required.",
    eligibility_help: "Leave everyone unchecked to make this available to all non-guest members.",
    cost_short: "Cost", points_unit: "points",
  },
  ru: {
    title: "Награды и привилегии", catalog_title: "Каталог", no_catalog: "В каталоге нет наград.",
    requests_title: "Запросы", no_requests: "Запросов наград нет.", balances_title: "Балансы наград",
    no_balances: "Балансы недоступны.", terminal_requests: "Завершённые и закрытые запросы",
    new_reward: "Новая награда", edit: "Изменить", request: "Запросить", save: "Сохранить", cancel: "Отмена",
    retry: "Повторить", approve: "Одобрить", reject: "Отклонить", fulfill: "Выполнить", refund: "Вернуть баллы",
    name: "Название", cost: "Стоимость (баллы 1–10000)", description: "Описание", enabled: "Доступно в каталоге",
    ttl: "Срок действия заявки (часов, 1–720)", eligible: "Кто может получать", all_members: "Все члены семьи",
    member: "Член семьи", note: "Примечание (необязательно)", reason: "Обязательная причина",
    privilege_note: "Договорная привилегия; устройства автоматически не переключаются.",
    balance_earned: "Заработано", balance_reserved: "Зарезервировано", balance_spent: "Потрачено",
    balance_available: "Доступно", balance_debt: "Чистый долг",
    status_requested: "Запрошено", status_approved: "Одобрено", status_fulfilled: "Выполнено",
    status_rejected: "Отклонено", status_cancelled: "Отменено", status_expired: "Истекло",
    status_refunded: "Возвращено", history_title: "История", insufficient_funds: "Недостаточно доступных баллов.",
    unknown_member: "Неизвестный участник", error_cost: "Стоимость должна быть целым числом от 1 до 10000.",
    error_ttl: "Срок должен быть целым числом от 1 до 720 часов.", error_name: "Укажите название.",
    error_reason: "Укажите причину.",
    eligibility_help: "Не отмечайте никого, чтобы разрешить всем участникам, кроме гостей.",
    cost_short: "Стоимость", points_unit: "баллов",
  },
  uk: {
    title: "Винагороди та привілеї", catalog_title: "Каталог", no_catalog: "У каталозі немає винагород.",
    requests_title: "Запити", no_requests: "Запитів винагород немає.", balances_title: "Баланси винагород",
    no_balances: "Баланси недоступні.", terminal_requests: "Завершені та закриті запити",
    new_reward: "Нова винагорода", edit: "Редагувати", request: "Запитати", save: "Зберегти", cancel: "Скасувати",
    retry: "Повторити", approve: "Схвалити", reject: "Відхилити", fulfill: "Виконати", refund: "Повернути бали",
    name: "Назва", cost: "Вартість (бали 1–10000)", description: "Опис", enabled: "Доступно в каталозі",
    ttl: "Термін дії заявки (годин, 1–720)", eligible: "Хто може отримувати", all_members: "Усі члени родини",
    member: "Член родини", note: "Примітка (необов'язково)", reason: "Обов'язкова причина",
    privilege_note: "Домовлені привілеї; пристрої автоматично не змінюються.",
    balance_earned: "Зароблено", balance_reserved: "Зарезервовано", balance_spent: "Витрачено",
    balance_available: "Доступно", balance_debt: "Чистий борг",
    status_requested: "Запитано", status_approved: "Схвалено", status_fulfilled: "Виконано",
    status_rejected: "Відхилено", status_cancelled: "Скасовано", status_expired: "Закінчився термін",
    status_refunded: "Повернуто", history_title: "Історія", insufficient_funds: "Недостатньо доступних балів.",
    unknown_member: "Невідомий учасник", error_cost: "Вартість має бути цілим числом від 1 до 10000.",
    error_ttl: "Термін має бути цілим числом від 1 до 720 годин.", error_name: "Вкажіть назву.",
    error_reason: "Вкажіть причину.",
    eligibility_help: "Не позначайте нікого, щоб дозволити всім учасникам, крім гостей.",
    cost_short: "Вартість", points_unit: "балів",
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
  return REWARD_COPY[lang] || REWARD_COPY.en;
}

function getMemberName(card, id) {
  if (!id) return "";
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

export function renderRewards(card, body) {
  if (!card || !body || !card._data) return;
  const role = card._data.role;
  if (!["owner","parent","adult","child"].includes(role) || !card._data.actor || !card._data.settings?.modules?.includes("court") || !card._data.rewards) return;

  const copy = getCopy(card), data = card._data, isParent = Boolean(card.parent) && ["owner","parent"].includes(role);
  const actorId = data.actor, zone = getHouseholdZone(card), startGen = card._generation;
  const rewards = data.rewards || {};
  const catalog = rewards.catalog || [], allRequests = rewards.requests || [], balances = rewards.balances || [];
  if(!isParent && card._rewardDraft?.type?.startsWith("catalog_"))card._rewardDraft=null;
  if(!isParent && card._rewardDraft?.type==="transition"){
    const target=allRequests.find(r=>r.id===card._rewardDraft.id);
    if(!target||target.member!==data.actor||target.status!=="requested"||card._rewardDraft.decision!=="cancel")card._rewardDraft=null;
  }

  const isStale = () => card._generation !== startGen || card._data?.role !== role || card._data?.actor !== actorId || getHouseholdZone(card) !== zone || !card._data?.settings?.modules?.includes("court");

  const runCmd = async (action, payload) => {
    if (isStale() || card._writing) return;
    try {
      await card.command(action, payload);
      if (!isStale()) {
        if (!card._actionError) card._rewardDraft = null;
        card.render();
      }
    } catch {}
  };

  // Section 1: Balances (distinct from score ledger)
  const balSection = el("section", null, "item");
  balSection.append(el("strong", copy.balances_title), el("p", copy.privilege_note, "sub"));
  const balList = isParent ? balances : balances.filter(b => b.member === actorId);
  if (!balList.length) balSection.append(el("div", copy.no_balances, "empty"));
  else {
    const ul = el("ul", null, "list");
    for (const b of balList) {
      const li = el("li", null, "item");
      li.append(el("strong", getMemberName(card, b.member)));
      const earnedSigned = (b.earned > 0 ? "+" : "") + b.earned;
      const sub = `${copy.balance_earned}: ${earnedSigned} · ${copy.balance_reserved}: ${b.reserved} · ${copy.balance_spent}: ${b.spent} · ${copy.balance_available}: ${b.available}` + (b.net < 0 ? ` · ${copy.balance_debt}: ${b.net}` : "");
      li.append(el("div", sub, "sub"));
      ul.append(li);
    }
    balSection.append(ul);
  }
  body.append(balSection);

  // Section 2: Catalog
  const catSection = el("section", null, "item");
  catSection.append(el("strong", copy.catalog_title));
  if (isParent) {
    const isCreating = card._rewardDraft?.type === "catalog_create";
    const controls=el("div",null,"actions");
    controls.append(card.button(isCreating ? copy.cancel : copy.new_reward, () => {
      if (isStale() || card._writing) return;
      card._rewardDraft = isCreating ? null : { type: "catalog_create", name: "", cost: 10, description: "", enabled: true, request_ttl_hours: 72, eligible: [] };
      card._actionError = null; card.render();
    }, !isCreating));
    catSection.append(controls);
  }

  // Catalog Form (Create / Edit)
  if (isParent && card._rewardDraft && (card._rewardDraft.type === "catalog_create" || card._rewardDraft.type === "catalog_edit")) {
    const d = card._rewardDraft, isEdit = d.type === "catalog_edit", isFrozen = Boolean(d.frozenPayload);
    const form = el("form", null, "editor");
    const nameInput = card.input(form, "name", copy.name, "text", d.name || "");
    const costInput = card.input(form, "cost", copy.cost, "number", String(d.cost ?? 10));
    const descInput = card.input(form, "description", copy.description, "text", d.description || "", false);
    const ttlInput = card.input(form, "ttl", copy.ttl, "number", String(d.request_ttl_hours ?? 72));
    nameInput.disabled = costInput.disabled = descInput.disabled = ttlInput.disabled = isFrozen || Boolean(card._writing);

    const enLabel = el("label", copy.enabled, "check"), enBox = el("input");
    enBox.type = "checkbox"; enBox.name = "enabled"; enBox.checked = d.enabled !== false; enBox.disabled = isFrozen || Boolean(card._writing);
    enLabel.prepend(enBox); form.append(enLabel);

    const eligFs = el("fieldset");
    eligFs.append(el("legend", copy.eligible));
    eligFs.append(el("p",copy.eligibility_help,"sub"));
    const nonguest = (card._data.members || []).filter(m => m.active && m.role !== "guest");
    const eligBoxes = [];
    for (const m of nonguest) {
      const ml = el("label", m.name, "check"), cb = el("input");
      cb.type = "checkbox"; cb.value = m.id;
      cb.checked = Array.isArray(d.eligible) && d.eligible.includes(m.id);
      cb.disabled = isFrozen || Boolean(card._writing);
      ml.prepend(cb); eligFs.append(ml); eligBoxes.push(cb);
    }
    form.append(eligFs);

    const errDiv = el("div", null, "notice"); errDiv.style.display = "none"; form.append(errDiv);
    const actions = el("div", null, "actions");
    const saveBtn = card.button(card._actionError && isFrozen ? copy.retry : copy.save, () => {}, true);
    saveBtn.type = "submit"; actions.append(saveBtn);
    actions.append(card.button(copy.cancel, () => { card._rewardDraft = null; card._actionError = null; card.render(); }));
    form.append(actions);

    const syncDraft = () => {
      if (isFrozen || isStale() || card._writing) return;
      d.name = nameInput.value; d.cost = costInput.value; d.description = descInput.value;
      d.request_ttl_hours = ttlInput.value; d.enabled = enBox.checked;
      d.eligible = eligBoxes.filter(c => c.checked).map(c => c.value);
    };
    nameInput.addEventListener("input", syncDraft); costInput.addEventListener("input", syncDraft);
    descInput.addEventListener("input", syncDraft); ttlInput.addEventListener("input", syncDraft);
    enBox.addEventListener("change", syncDraft); eligBoxes.forEach(cb => cb.addEventListener("change", syncDraft));

    form.addEventListener("submit", e => {
      e.preventDefault();
      if (isStale() || card._writing || !card.parent) { card._rewardDraft = null; card.render(); return; }
      if (isFrozen) { runCmd("court.reward_save", d.frozenPayload); return; }
      const nm = nameInput.value.trim(), c = Number(costInput.value), ttl = Number(ttlInput.value);
      if (!nm) { errDiv.textContent = copy.error_name; errDiv.style.display = "block"; return; }
      if (!Number.isInteger(c) || c < 1 || c > 10000) { errDiv.textContent = copy.error_cost; errDiv.style.display = "block"; return; }
      if (!Number.isInteger(ttl) || ttl < 1 || ttl > 720) { errDiv.textContent = copy.error_ttl; errDiv.style.display = "block"; return; }
      const payload = { name: nm, cost: c, description: descInput.value.trim(), enabled: enBox.checked, eligible: eligBoxes.filter(cb => cb.checked).map(cb => cb.value), request_ttl_hours: ttl };
      if (isEdit) {
        const item = card._data.rewards?.catalog?.find(i => i.id === d.id);
        if (!item || item.revision !== d.revision) { card._rewardDraft = null; card._actionError = "conflict"; card.render(); return; }
        payload.id = d.id; payload.revision = d.revision;
      }
      if(payload.eligible.some(id=>!card._data.members.some(m=>m.id===id&&m.active&&m.role!=="guest"))){card._actionError="unknown_member";card.render();return;}
      Object.assign(d,payload);d.frozenPayload = payload;
      runCmd("court.reward_save", payload);
    });
    catSection.append(form);
  }

  // Catalog Item list
  const catItems = catalog.filter(i => isParent || (i.enabled && (!i.eligible?.length || i.eligible.includes(actorId))));
  if (!catItems.length) catSection.append(el("div", copy.no_catalog, "empty"));
  else {
    const ul = el("ul", null, "list");
    for (const item of catItems) {
      const li = el("li", null, "item");
      li.append(el("strong", `${item.id} · ${item.name}`));
      const meta = `${copy.cost_short}: ${item.cost} ${copy.points_unit}` + (item.description ? ` · ${item.description}` : "") + (isParent ? ` · ${item.enabled ? copy.enabled : copy.status_cancelled}` : "");
      li.append(el("div", meta, "sub"));
      const act = el("div", null, "actions");
      if (isParent) {
        act.append(card.button(copy.edit, () => {
          if (isStale() || card._writing) return;
          card._rewardDraft = { type: "catalog_edit", id: item.id, revision: item.revision, name: item.name, cost: item.cost, description: item.description, enabled: item.enabled, request_ttl_hours: item.request_ttl_hours, eligible: [...(item.eligible || [])] };
          card._actionError = null; card.render();
        }));
      }
      if (item.enabled) {
        act.append(card.button(copy.request, () => {
          if (isStale() || card._writing) return;
          card._rewardDraft = { type: "request_confirm", id: item.id, revision: item.revision, member: actorId, note: "" };
          card._actionError = null; card.render();
        }, true));
      }
      li.append(act);

      // Confirmation for requesting this reward
      if (card._rewardDraft?.type === "request_confirm" && card._rewardDraft.id === item.id) {
        const d = card._rewardDraft, isFrozen = Boolean(d.frozenPayload);
        const reqForm = el("form", null, "editor");
        let mSelect = null;
        if (isParent) {
          mSelect = card.memberSelect(reqForm);
          if (d.member) mSelect.value = d.member;
          mSelect.disabled = isFrozen || Boolean(card._writing);
          mSelect.addEventListener("change", () => { if (!isFrozen) { d.member = mSelect.value; card.render(); } });
        }
        const reqMem = isParent ? (mSelect ? mSelect.value : d.member) : actorId;
        const curBal = (balances.find(b => b.member === reqMem)?.available) ?? 0;
        const info = el("div", `${copy.cost_short}: ${item.cost} ${copy.points_unit} | ${copy.balance_available}: ${curBal}`, "sub");
        reqForm.append(info);
        const noteInput = card.input(reqForm, "note", copy.note, "text", d.note || "", false);
        noteInput.disabled = isFrozen || Boolean(card._writing);
        noteInput.addEventListener("input", () => { if (!isFrozen) d.note = noteInput.value; });

        const reqErr = el("div", null, "notice"); reqErr.style.display = "none"; reqForm.append(reqErr);
        const reqActs = el("div", null, "actions");
        const submitReq = card.button(card._actionError && isFrozen ? copy.retry : copy.request, () => {}, true);
        submitReq.type = "submit"; reqActs.append(submitReq);
        reqActs.append(card.button(copy.cancel, () => { card._rewardDraft = null; card._actionError = null; card.render(); }));
        reqForm.append(reqActs);

        reqForm.addEventListener("submit", e => {
          e.preventDefault();
          if (isStale() || card._writing) return;
          if (isFrozen) { runCmd("court.reward_request", d.frozenPayload); return; }
          const target = isParent ? (mSelect ? mSelect.value : d.member) : actorId;
          const curItem = card._data.rewards?.catalog?.find(i => i.id === d.id);
          if (!curItem || curItem.revision !== d.revision) { card._rewardDraft = null; card._actionError = "conflict"; card.render(); return; }
          if(!curItem.enabled||!card._data.members.some(m=>m.id===target&&m.active&&m.role!=="guest")||(curItem.eligible?.length&&!curItem.eligible.includes(target))){card._actionError="forbidden";card.render();return;}
          const targetBal = (card._data.rewards?.balances?.find(b => b.member === target)?.available) ?? 0;
          if (targetBal < curItem.cost) { reqErr.textContent = copy.insufficient_funds; reqErr.style.display = "block"; return; }
          const payload = { id: d.id, revision: d.revision, member: target, note: noteInput.value.trim() };
          Object.assign(d,payload);d.frozenPayload = payload;
          runCmd("court.reward_request", payload);
        });
        li.append(reqForm);
      }
      ul.append(li);
    }
    catSection.append(ul);
  }
  body.append(catSection);

  // Section 3: Requests
  const reqSection = el("section", null, "item");
  reqSection.append(el("strong", copy.requests_title));
  const userRequests = isParent ? allRequests : allRequests.filter(r => r.member === actorId);
  const activeReqs = userRequests.filter(r => ["requested", "approved"].includes(r.status));
  const termReqs = userRequests.filter(r => !["requested", "approved"].includes(r.status));

  function renderRequestItem(req) {
    const li = el("li", null, "item");
    li.append(el("strong", `${req.id} · ${req.name} (${req.cost})`));
    const stKey = `status_${req.status}`;
    const statusText = copy[stKey] || req.status;
    let sub = `${getMemberName(card, req.member)} · ${statusText} · ${formatDateInZone(card, req.created_at, zone)}`;
    if (req.description) sub += ` · ${req.description}`;
    li.append(el("div", sub, "sub"));

    if (Array.isArray(req.history) && req.history.length > 0) {
      const hDet = el("details", null, "sub");
      hDet.append(el("summary", `${copy.history_title} (${req.history.length})`));
      const hUl = el("ul", null, "list");
      for (const h of req.history) {
        const hLi = el("li", null, "sub");
        hLi.textContent = `${formatDateInZone(card, h.at, zone)} · ${getMemberName(card, h.actor)}: ${copy[`status_${h.status}`] || h.status} — ${h.reason}`;
        hUl.append(hLi);
      }
      hDet.append(hUl); li.append(hDet);
    }

    const isPending = ["requested", "approved"].includes(req.status);
    const canRefund = isParent && req.status === "fulfilled";
    if (isPending || canRefund) {
      const actDiv = el("div", null, "actions");
      const openTrans = (dec) => {
        if (isStale() || card._writing) return;
        card._rewardDraft = { type: "transition", id: req.id, revision: req.revision, decision: dec, reason: "" };
        card._actionError = null; card.render();
      };

      if (isParent) {
        if (req.status === "requested") {
          actDiv.append(card.button(copy.approve, () => openTrans("approve"), true));
          actDiv.append(card.button(copy.reject, () => openTrans("reject")));
          actDiv.append(card.button(copy.cancel, () => openTrans("cancel")));
        } else if (req.status === "approved") {
          actDiv.append(card.button(copy.fulfill, () => openTrans("fulfill"), true));
          actDiv.append(card.button(copy.cancel, () => openTrans("cancel")));
        } else if (req.status === "fulfilled") {
          actDiv.append(card.button(copy.refund, () => openTrans("refund")));
        }
      } else if (req.status === "requested" && req.member === actorId) {
        actDiv.append(card.button(copy.cancel, () => openTrans("cancel")));
      }
      if (actDiv.children.length > 0) li.append(actDiv);

      // Transition Form
      if (card._rewardDraft?.type === "transition" && card._rewardDraft.id === req.id) {
        const d = card._rewardDraft, isFrozen = Boolean(d.frozenPayload);
        const tForm = el("form", null, "editor");
        const rInput = card.input(tForm, "reason", `${copy.reason} (${copy[d.decision] || d.decision})`, "text", d.reason || "");
        rInput.disabled = isFrozen || Boolean(card._writing);
        rInput.addEventListener("input", () => { if (!isFrozen) d.reason = rInput.value; });

        const tErr = el("div", null, "notice"); tErr.style.display = "none"; tForm.append(tErr);
        const tActs = el("div", null, "actions");
        const submitBtn = card.button(card._actionError && isFrozen ? copy.retry : copy[d.decision] || copy.save, () => {}, true);
        submitBtn.type = "submit"; tActs.append(submitBtn);
        tActs.append(card.button(copy.cancel, () => { card._rewardDraft = null; card._actionError = null; card.render(); }));
        tForm.append(tActs);

        tForm.addEventListener("submit", e => {
          e.preventDefault();
          if (isStale() || card._writing) return;
          if (isFrozen) { runCmd("court.reward_transition", d.frozenPayload); return; }
          const rText = rInput.value.trim();
          if (!rText) { tErr.textContent = copy.error_reason; tErr.style.display = "block"; return; }
          const curReq = card._data.rewards?.requests?.find(r => r.id === d.id);
          if (!curReq || curReq.revision !== d.revision) { card._rewardDraft = null; card._actionError = "conflict"; card.render(); return; }
          if (!card.parent && (curReq.status !== "requested" || curReq.member !== actorId || d.decision !== "cancel")) {
            card._rewardDraft = null; card.render(); return;
          }
          const origins={approve:["requested"],reject:["requested"],cancel:["requested","approved"],fulfill:["approved"],refund:["fulfilled"]};
          if (!origins[d.decision]?.includes(curReq.status)) {
            card._rewardDraft = null; card.render(); return;
          }
          const payload = { id: d.id, revision: d.revision, decision: d.decision, reason: rText };
          d.reason=rText;d.frozenPayload = payload;
          runCmd("court.reward_transition", payload);
        });
        li.append(tForm);
      }
    }
    return li;
  }

  if (!activeReqs.length && !termReqs.length) reqSection.append(el("div", copy.no_requests, "empty"));
  else {
    if (activeReqs.length) {
      const aUl = el("ul", null, "list");
      for (const req of activeReqs) aUl.append(renderRequestItem(req));
      reqSection.append(aUl);
    }
    if (termReqs.length) {
      const det = el("details", null, "item");
      // Refund review lives inside this section, including after a failed save.
      det.open = termReqs.some(req => card._rewardDraft?.type === "transition" && card._rewardDraft.id === req.id);
      det.append(el("summary", `${copy.terminal_requests} (${termReqs.length})`));
      const tUl = el("ul", null, "list");
      for (const req of termReqs) tUl.append(renderRequestItem(req));
      det.append(tUl); reqSection.append(det);
    }
  }
  body.append(reqSection);
}
