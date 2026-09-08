/* Parent-only bulk task panel and review workflow for Family Assistant cards. */

import { TASK_BATCH_COPY } from "./task-batch-copy.js";

const PARENTS = new Set(["owner", "parent"]);
const NON_TERMINAL = new Set(["assigned", "accepted", "in_progress", "submitted", "needs_changes"]);
const TERMINAL = new Set(["completed", "cancelled", "archived"]);

const STYLE = `
  .task-batch { display: grid; gap: 12px; margin-bottom: 16px; }
  .task-batch details { border: 1px solid var(--divider-color, #dfe9e7); border-radius: 12px; padding: 12px; }
  .task-batch summary { cursor: pointer; font-size: 13px; font-weight: 600; }
  .task-batch-content, .task-batch-select, .task-batch-review { display: grid; gap: 10px; min-width: 0; }
  .task-batch-list { display: grid; gap: 8px; max-height: 380px; overflow-y: auto; padding: 4px; border: 1px solid var(--divider-color, #dfe9e7); border-radius: 10px; }
  .task-batch-row { display: flex; align-items: flex-start; gap: 10px; padding: 8px; border: 1px solid var(--divider-color, #e3ebe9); border-radius: 8px; min-width: 0; }
  .task-batch-row p { margin: 0; overflow-wrap: anywhere; }
  .task-batch-check { display: flex !important; align-items: flex-start; gap: 8px !important; cursor: pointer; width: 100%; min-width: 0; }
  .task-batch-check input[type="checkbox"] { flex: 0 0 auto; margin-top: 2px; }
  .task-batch-info { display: grid; gap: 2px; min-width: 0; flex: 1; }
  .task-batch-actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 8px; }
  .task-batch-preview { display: grid; gap: 8px; min-width: 0; }
  .task-batch-preview article { display: grid; gap: 6px; min-width: 0; padding: 12px; border: 1px solid var(--divider-color, #dfe9e7); border-radius: 10px; }
  .task-batch-preview p { margin: 0; overflow-wrap: anywhere; }
  .task-batch-preview .task-batch-title { font-weight: 600; }
  .task-batch-preview .task-batch-meta { font-size: 13px; color: var(--secondary-text-color, #657d80); }
  .task-batch-warning { padding: 8px; border-inline-start: 4px solid var(--warning-color, #d97706); background: rgba(238, 150, 60, .1); border-radius: 4px; font-size: 13px; }
  @media(max-width: 560px) {
    .task-batch-actions > button { width: 100%; }
  }
`;

function node(tag, text, className) {
  const el = document.createElement(tag);
  if (text !== undefined && text !== null) el.textContent = String(text);
  if (className) el.className = className;
  return el;
}

const freeze = (value) => {
  if (!value || typeof value !== "object" || Object.isFrozen(value)) return value;
  Object.freeze(value);
  for (const child of Object.values(value)) freeze(child);
  return value;
};

function language(card) {
  return String(card?._config?.language || card?._hass?.language || "en").split(/[-_]/)[0];
}

function copy(card) {
  const lang = language(card);
  return TASK_BATCH_COPY[lang] || TASK_BATCH_COPY.en;
}

function validRevision(value) {
  return Number.isSafeInteger(value) && value >= 1;
}

function members(card) {
  return Array.isArray(card?._data?.members) ? card._data.members : [];
}

function member(card, id) {
  return members(card).find((m) => m && m.id === id) || null;
}

function activeMember(card, id) {
  const m = member(card, id);
  return m && m.active === true && m.role !== "guest" && validRevision(m.revision) ? m : null;
}

function tasks(card) {
  return Array.isArray(card?._data?.tasks) ? card._data.tasks : [];
}

function taskById(card, id) {
  return tasks(card).find((t) => t && t.id === id) || null;
}

function modules(card) {
  return Array.isArray(card?._data?.settings?.modules) ? card._data.settings.modules : [];
}

function ordinaryTask(task) {
  if (!task || typeof task !== "object") return false;
  if (typeof task.id !== "string" || !task.id.trim() || task.id.length > 80) return false;
  if (!validRevision(task.revision)) return false;
  if (task.delivery_scope === "personal" || task.delivery_scope === "private" || task.personal === true) return false;
  if (["maintenance_fault", "maintenance_service", "school_homework"].includes(task.source?.kind)) return false;
  if (task.managed_by != null && task.managed_by !== "") return false;
  return true;
}

function isTaskEligible(card, task, action) {
  if (!ordinaryTask(task)) return false;
  if (typeof task.assignee !== "string" || !task.assignee) return false;
  if (!activeMember(card, task.assignee)) return false;

  if (action === "tasks.complete" || action === "tasks.cancel") {
    return NON_TERMINAL.has(task.status) && !TERMINAL.has(task.status);
  }
  if (action === "tasks.archive") {
    return task.status === "completed" || task.status === "cancelled";
  }
  return false;
}

function eligibleTasks(card, action) {
  return tasks(card).filter((t) => isTaskEligible(card, t, action));
}

function access(card) {
  const data = card?._data;
  if (!data) return null;
  if (!PARENTS.has(data.role) || data.role === "guest") return null;
  if (!modules(card).includes("tasks")) return null;
  const actor = member(card, data.actor);
  if (!actor || actor.active !== true || actor.role !== data.role || !validRevision(actor.revision)) {
    return null;
  }
  if (data.actor_revision != null && data.actor_revision !== actor.revision) return null;
  return {
    entry: card._entry,
    generation: card._generation,
    haUser: card?._hass?.user?.id ?? null,
    actor: data.actor,
    role: data.role,
    actorRevision: actor.revision,
  };
}

function sameAccess(card, expected) {
  const actual = access(card);
  return Boolean(actual && expected && JSON.stringify(actual) === JSON.stringify(expected));
}

function firstSendAllowed(card, draft) {
  if (!sameAccess(card, draft?.access)) return false;
  if (!Array.isArray(draft.selectedTasks) || draft.selectedTasks.length === 0 || draft.selectedTasks.length > 20) {
    return false;
  }
  for (const snap of draft.selectedTasks) {
    const current = taskById(card, snap.id);
    if (!current) return false;
    if (current.revision !== snap.revision) return false;
    if (current.status !== snap.status) return false;
    if (current.assignee !== snap.assignee) return false;
    const m = member(card, snap.assignee);
    if (!m || m.active !== true || m.role === "guest") return false;
    if (!validRevision(m.revision) || m.revision !== snap.assignee_revision) return false;
    if (m.role !== draft.assigneeSnapshots?.[snap.assignee]?.role) return false;
    if (!isTaskEligible(card, current, draft.action)) return false;
  }
  return true;
}

function retryAllowed(card, draft) {
  if (!draft?.pending || !sameAccess(card, draft.access)) return false;
  for (const cmd of draft.pending.payload.commands || []) {
    const taskId = cmd.payload?.id;
    const currentTask = taskById(card, taskId);
    const snap = draft.selectedTasks?.find((s) => s.id === taskId);
    const assigneeId = snap?.assignee;
    if (!assigneeId || !ordinaryTask(currentTask) || currentTask.assignee !== assigneeId) return false;
    const m = member(card, assigneeId);
    if (!m || m.active !== true || m.role === "guest" ||
        m.revision !== snap.assignee_revision ||
        m.role !== draft.assigneeSnapshots?.[assigneeId]?.role) return false;
  }
  return true;
}

function draftAllowed(card, draft) {
  if (!draft) return false;
  if (draft.pending) return retryAllowed(card, draft);
  if (draft.stage === "review") return firstSendAllowed(card, draft);
  return sameAccess(card, draft.access);
}

function stale(card, draft, element) {
  if (!element?.isConnected || card._taskBatchDraft !== draft || card._writing) return true;
  if (!sameAccess(card, draft.access)) {
    disposeTaskBatch(card);
    card.render();
    return true;
  }
  if (!draftAllowed(card, draft)) {
    if (draft.pending) {
      card._taskBatchDraft = null;
    } else if (draft.stage === "review") {
      draft.stage = "select";
      draft.confirmed = false;
      draft.selectedTasks = [];
      draft.selectedIds = (draft.selectedIds || []).filter((id) => {
        const t = taskById(card, id);
        return t && isTaskEligible(card, t, draft.action);
      });
      draft.error = "staleError";
    } else {
      card._taskBatchDraft = null;
    }
    card.render();
    return true;
  }
  return false;
}

function button(card, text, action, primary = false) {
  const btn = node("button", text, primary ? "primary" : "");
  btn.type = "button";
  btn.disabled = Boolean(card._writing);
  btn.addEventListener("click", action);
  return btn;
}

function projection(data) {
  return {
    actor: data?.actor ?? null,
    role: data?.role ?? null,
    modules: (data?.settings?.modules || []).filter((item) => item === "tasks"),
    members: (data?.members || []).map(({ id, name, role, active, revision }) => ({
      id,
      name,
      role,
      active,
      revision,
    })),
    tasks: (data?.tasks || []).map(({ id, revision, status, assignee, title, delivery_scope, managed_by, source }) => ({
      id,
      revision,
      status,
      assignee,
      title,
      delivery_scope,
      managed_by,
      sourceKind: source?.kind,
    })),
  };
}

export function reconcileTaskBatchRefresh(card, previousData) {
  if (!card) return false;
  const changed =
    JSON.stringify(projection(previousData)) !== JSON.stringify(projection(card._data));
  let force = changed && Boolean(card.shadowRoot?.querySelector(".task-batch"));
  const draft = card._taskBatchDraft;
  if (draft) {
    if (draft.pending) {
      if (!retryAllowed(card, draft)) {
        card._taskBatchDraft = null;
        force = true;
      }
    } else {
      if (!sameAccess(card, draft.access)) {
        card._taskBatchDraft = null;
        force = true;
      } else if (draft.stage === "review") {
        if (!firstSendAllowed(card, draft)) {
          draft.stage = "select";
          draft.confirmed = false;
          draft.selectedTasks = [];
          draft.selectedIds = (draft.selectedIds || []).filter((id) => {
            const t = taskById(card, id);
            return t && isTaskEligible(card, t, draft.action);
          });
          draft.error = "staleError";
          force = true;
        }
      } else if (draft.stage === "select") {
        const prevLen = draft.selectedIds.length;
        draft.selectedIds = (draft.selectedIds || []).filter((id) => {
          const t = taskById(card, id);
          return t && isTaskEligible(card, t, draft.action);
        });
        if (draft.selectedIds.length !== prevLen) {
          force = true;
        }
      }
    }
  }
  return force;
}

export function disposeTaskBatch(card) {
  if (!card) return;
  card._taskBatchDraft = null;
  card.shadowRoot?.querySelectorAll(".task-batch").forEach(element => element.remove());
}

function proceedToReview(card, draft) {
  if (draft.selectedIds.length < 1 || draft.selectedIds.length > 20) {
    draft.error = "validationError";
    card.render();
    return;
  }
  const selectedTasks = [];
  const assigneeSnapshots = {};
  for (const id of draft.selectedIds) {
    const task = taskById(card, id);
    if (!task || !isTaskEligible(card, task, draft.action)) {
      draft.error = "staleError";
      card.render();
      return;
    }
    const m = member(card, task.assignee);
    if (!m || m.active !== true || m.role === "guest" || !validRevision(m.revision)) {
      draft.error = "staleError";
      card.render();
      return;
    }
    selectedTasks.push({
      id: task.id,
      title: task.title,
      revision: task.revision,
      status: task.status,
      assignee: task.assignee,
      assignee_name: m.name || "",
      assignee_revision: m.revision,
    });
    assigneeSnapshots[m.id] = {
      id: m.id,
      name: m.name || "",
      role: m.role,
      revision: m.revision,
    };
  }
  draft.selectedTasks = freeze(selectedTasks);
  draft.assigneeSnapshots = freeze(assigneeSnapshots);
  draft.stage = "review";
  draft.confirmed = false;
  draft.error = null;
  card.render();
}

async function executeBatch(card, draft, root) {
  if (!root?.isConnected || card._taskBatchDraft !== draft || card._writing) return;

  if (!draft.confirmed) {
    draft.error = "validationError";
    card.render();
    return;
  }

  if (!draft.pending) {
    if (!firstSendAllowed(card, draft)) {
      draft.stage = "select";
      draft.confirmed = false;
      draft.selectedTasks = [];
      draft.selectedIds = (draft.selectedIds || []).filter((id) => {
        const t = taskById(card, id);
        return t && isTaskEligible(card, t, draft.action);
      });
      draft.error = "staleError";
      card.render();
      return;
    }

    const commands = draft.selectedTasks.map((t) => ({
      action: draft.action,
      payload: {
        id: t.id,
        revision: t.revision,
      },
    }));
    const payload = freeze({ commands });
    const operationId = crypto.randomUUID();
    draft.pending = freeze({
      operation_id: operationId,
      action: "batch",
      payload,
    });
  } else {
    if (!retryAllowed(card, draft)) {
      card._taskBatchDraft = null;
      card._actionError = "forbidden";
      card.render();
      return;
    }
  }

  const pending = draft.pending;
  await card.command(pending.action, pending.payload, pending.operation_id);

  if (card._taskBatchDraft !== draft) return;
  if (draft.pending ? !retryAllowed(card, draft) : !sameAccess(card, draft.access)) return;

  if (!card._actionError) {
    card._taskBatchDraft = null;
  }
  card.render();
}

function renderSelect(card, section, draft) {
  const c = copy(card);
  const form = node("form", null, "task-batch-select");
  form.addEventListener("submit", (e) => e.preventDefault());

  form.append(node("h3", c.selectTasks));

  const actionWrap = node("label", null);
  actionWrap.append(node("span", c.actionLabel));
  const selectAction = node("select");
  selectAction.name = "batch_action";
  selectAction.setAttribute("aria-label", c.actionLabel);
  for (const [key, label] of [
    ["tasks.complete", c.actionComplete],
    ["tasks.cancel", c.actionCancel],
    ["tasks.archive", c.actionArchive],
  ]) {
    const opt = node("option", label);
    opt.value = key;
    opt.selected = key === draft.action;
    selectAction.append(opt);
  }
  actionWrap.append(selectAction);
  form.append(actionWrap);

  selectAction.addEventListener("change", () => {
    if (stale(card, draft, form)) return;
    draft.action = selectAction.value;
    draft.selectedIds = draft.selectedIds.filter((id) => {
      const t = taskById(card, id);
      return t && isTaskEligible(card, t, draft.action);
    });
    draft.error = null;
    card.render();
  });

  const countText = c.selectedLimit.replace("{count}", String(draft.selectedIds.length));
  form.append(node("div", countText, "sub"));

  if (draft.selectedIds.length >= 20) {
    form.append(node("div", c.maxLimitNotice, "task-batch-warning"));
  }

  if (draft.error) {
    const alert = node("div", c[draft.error] || draft.error, "notice");
    alert.setAttribute("role", "alert");
    form.append(alert);
  }

  const eligible = eligibleTasks(card, draft.action);
  if (!eligible.length) {
    form.append(node("p", c.emptyEligible, "empty"));
  } else {
    const list = node("div", null, "task-batch-list");
    const displayed = eligible.slice(0, draft.pageLimit);
    for (const task of displayed) {
      const m = member(card, task.assignee);
      const memberName = m?.name || c.unknown_member;
      const statusText = c[`status_${task.status}`] || task.status;

      const row = node("div", null, "task-batch-row");
      const label = node("label", null, "task-batch-check");
      const check = node("input");
      check.type = "checkbox";
      check.name = "task_select";
      check.value = task.id;
      check.checked = draft.selectedIds.includes(task.id);
      check.disabled = !check.checked && draft.selectedIds.length >= 20;

      const info = node("div", null, "task-batch-info");
      const titleStrong = node("strong", `${task.id}: ${task.title}`);
      const meta = node(
        "span",
        `${c.tableAssignee}: ${memberName} · ${c.tableStatus}: ${statusText} · ${c.tableTaskRevision}: ${task.revision}`,
        "sub"
      );
      info.append(titleStrong, meta);
      label.append(check, info);
      row.append(label);

      check.addEventListener("change", () => {
        if (stale(card, draft, form)) return;
        if (check.checked) {
          if (draft.selectedIds.length < 20 && !draft.selectedIds.includes(task.id)) {
            draft.selectedIds.push(task.id);
          }
        } else {
          draft.selectedIds = draft.selectedIds.filter((id) => id !== task.id);
        }
        draft.error = null;
        card.render();
      });

      list.append(row);
    }
    form.append(list);

    if (eligible.length > draft.pageLimit) {
      form.append(
        button(card, c.loadMore, () => {
          if (stale(card, draft, form)) return;
          draft.pageLimit += 100;
          card.render();
        })
      );
    }
  }

  const actions = node("div", null, "task-batch-actions");
  const reviewBtn = button(
    card,
    c.reviewBatch,
    () => {
      if (stale(card, draft, form)) return;
      proceedToReview(card, draft);
    },
    true
  );
  reviewBtn.disabled =
    draft.selectedIds.length === 0 || draft.selectedIds.length > 20 || Boolean(card._writing);
  actions.append(
    reviewBtn,
    button(card, c.cancel, () => {
      if (!section.isConnected || card._writing || card._taskBatchDraft !== draft) return;
      card._taskBatchDraft = null;
      card.render();
    })
  );
  form.append(actions);

  section.append(form);
}

function renderReview(card, section, draft) {
  const c = copy(card);
  const root = node("div", null, "task-batch-review");

  root.append(node("h3", c.reviewTitle));

  const actionLabels = {
    "tasks.complete": c.actionComplete,
    "tasks.cancel": c.actionCancel,
    "tasks.archive": c.actionArchive,
  };
  const summary = node(
    "p",
    `${c.reviewActionLabel}: ${actionLabels[draft.action] || draft.action} · ${c.reviewCountLabel}: ${draft.selectedTasks.length}`,
    "sub"
  );
  root.append(summary);

  if (draft.error) {
    const alert = node("div", c[draft.error] || draft.error, "notice");
    alert.setAttribute("role", "alert");
    root.append(alert);
  }

  const preview = node("div", null, "task-batch-preview");
  const versions = node("details");
  versions.append(node("summary", c.reviewVersions));
  for (const t of draft.selectedTasks) {
    const item = node("article");
    item.append(
      node("p", t.title, "task-batch-title"),
      node("p", `${t.id} · ${t.assignee_name} · ${c[`status_${t.status}`] || c.status_unknown}`, "task-batch-meta")
    );
    preview.append(item);
    versions.append(node("p", `${t.id} · ${c.tableTaskRevision}: ${t.revision} · ${c.tableAssigneeRevision}: ${t.assignee_revision}`, "sub"));
  }
  root.append(preview, versions);

  if (draft.pending) {
    root.append(node("div", c.pendingNotice, "notice"));
    root.append(node("p", c.uncertainNotice, "sub"));
  }

  const confirmLabel = node("label", null, "task-batch-check");
  const confirmBox = node("input");
  confirmBox.type = "checkbox";
  confirmBox.name = "confirm";
  confirmBox.checked = draft.confirmed === true;
  confirmBox.disabled = Boolean(draft.pending) || Boolean(card._writing);
  confirmLabel.append(confirmBox, node("span", c.confirmLabel));
  root.append(confirmLabel);

  confirmBox.addEventListener("change", () => {
    if (stale(card, draft, root)) return;
    draft.confirmed = confirmBox.checked;
    draft.error = null;
    card.render();
  });

  const actions = node("div", null, "task-batch-actions");
  if (!draft.pending) {
    const submitBtn = button(card, c.applyBatch, () => executeBatch(card, draft, root), true);
    submitBtn.disabled = !draft.confirmed || Boolean(card._writing);
    actions.append(
      submitBtn,
      button(card, c.back, () => {
        if (stale(card, draft, root)) return;
        draft.stage = "select";
        draft.confirmed = false;
        draft.error = null;
        card.render();
      }),
      button(card, c.cancel, () => {
        if (!root.isConnected || card._writing || card._taskBatchDraft !== draft) return;
        card._taskBatchDraft = null;
        card.render();
      })
    );
  } else {
    const retryBtn = button(card, c.retry, () => executeBatch(card, draft, root), true);
    retryBtn.disabled = Boolean(card._writing);
    actions.append(
      retryBtn,
      button(card, c.closeWithoutRollback, () => {
        if (!root.isConnected || card._writing || card._taskBatchDraft !== draft) return;
        card._taskBatchDraft = null;
        card.render();
      })
    );
  }
  root.append(actions);

  section.append(root);
}

export function renderTaskBatch(card, body) {
  if (!card) return;
  const c = copy(card);

  if (card._view !== "tasks" || !card.parent || !access(card)) {
    card._taskBatchDraft = null;
    return;
  }

  const section = node("section", null, "task-batch");
  section.append(node("style", STYLE));

  const draft = card._taskBatchDraft;
  if (!draft) {
    const openingAccess = freeze(access(card));
    const details = node("details");
    details.append(node("summary", c.summaryTitle));
    const content = node("div", null, "task-batch-content");
    content.append(node("p", c.panelTitle, "sub"));
    content.append(
      button(
        card,
        c.startBatch,
        () => {
          if (!section.isConnected || card._writing || !sameAccess(card, openingAccess)) return;
          card._taskBatchDraft = {
            access: freeze(access(card)),
            action: "tasks.complete",
            selectedIds: [],
            stage: "select",
            pageLimit: 100,
            selectedTasks: [],
            assigneeSnapshots: {},
            confirmed: false,
            error: null,
            pending: null,
          };
          card.render();
        },
        true
      )
    );
    details.append(content);
    section.append(details);
    body.append(section);
    return;
  }

  if (!sameAccess(card, draft.access)) {
    disposeTaskBatch(card);
    return;
  }
  if (!draftAllowed(card, draft)) {
    if (draft.pending) {
      card._taskBatchDraft = null;
      body.append(section);
      return;
    }
    if (draft.stage === "review") {
      draft.stage = "select";
      draft.confirmed = false;
      draft.selectedTasks = [];
      draft.selectedIds = (draft.selectedIds || []).filter((id) => {
        const t = taskById(card, id);
        return t && isTaskEligible(card, t, draft.action);
      });
      draft.error = "staleError";
    } else {
      card._taskBatchDraft = null;
      body.append(section);
      return;
    }
  }

  if (draft.stage === "review") {
    renderReview(card, section, draft);
  } else {
    renderSelect(card, section, draft);
  }

  body.append(section);
}
