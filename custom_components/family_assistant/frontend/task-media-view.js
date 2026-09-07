/* Explicit, private task photo upload and download workflow. */

import { downloadMedia, uploadMedia } from "./media-client.js";
import { TASK_MEDIA_COPY } from "./task-media-copy.js";

const MAX_BYTES = 10 * 1024 * 1024;
const MAX_FILE_NAME_DISPLAY = 160;
const MIME_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);
const OPEN = new Set(["assigned", "accepted", "in_progress", "needs_changes"]);
const PRIVILEGED = new Set(["owner", "parent"]);
const SEGMENT = /^[A-Za-z0-9_-]{1,128}$/;
const STYLE = `
  .task-media{display:grid;gap:8px;margin-top:10px;padding-top:8px;border-top:1px solid var(--divider-color,#ddd)}
  .task-media p{margin:0;overflow-wrap:anywhere}.task-media-form,.task-media-review,.task-media-attachment{display:grid;gap:8px}
  .task-media-actions{display:flex;flex-wrap:wrap;gap:8px}.task-media-confirm{display:flex;gap:8px;align-items:flex-start}
  .task-media-confirm input{flex:0 0 auto;margin-top:3px}.task-media-preview{display:block;max-width:100%;max-height:360px;object-fit:contain}
  .task-media-file{overflow-wrap:anywhere}.task-media-attachment{padding:8px;border:1px solid var(--divider-color,#ddd);border-radius:8px}
  .task-media-purge{display:grid;gap:8px;padding:10px;border:1px solid var(--error-color,#b3261e);border-radius:8px}
  .task-media-purge textarea{box-sizing:border-box;width:100%;min-height:72px}
  @media(max-width:520px){.task-media-actions>button{width:100%}}
`;

const el = (tag, value, className) => {
  const result = document.createElement(tag);
  if (value !== undefined && value !== null) result.textContent = String(value);
  if (className) result.className = className;
  return result;
};
const validRevision = (value) => Number.isSafeInteger(value) && value >= 1;
const copyOf = (card) => {
  const language = card?._config?.language || card?._hass?.language || "en";
  return TASK_MEDIA_COPY[language.split("-")[0]] || TASK_MEDIA_COPY.en;
};
const member = (card, id) =>
  (Array.isArray(card?._data?.members) ? card._data.members : []).find(
    (item) => item?.id === id,
  ) || null;
const task = (card, id) =>
  (Array.isArray(card?._data?.tasks) ? card._data.tasks : []).find(
    (item) => item?.id === id,
  ) || null;

function access(card, item, { upload = false } = {}) {
  const data = card?._data;
  const actor = member(card, data?.actor);
  const assignee = member(card, item?.assignee);
  const privileged = PRIVILEGED.has(actor?.role);
  if (
    !card?._entry ||
    !SEGMENT.test(card._entry) ||
    !data ||
    !actor ||
    actor.active !== true ||
    actor.role !== data.role ||
    !validRevision(actor.revision) ||
    !Array.isArray(data.settings?.modules) ||
    !data.settings.modules.includes("tasks") ||
    !item ||
    item.report_type !== "photo" ||
    !SEGMENT.test(item.id || "") ||
    !validRevision(item.revision) ||
    (!privileged && item.assignee !== actor.id) ||
    ((upload || !privileged) &&
      (!assignee ||
        assignee.active !== true ||
        assignee.role === "guest" ||
        !validRevision(assignee.revision) ||
        item.assignee_revision !== assignee.revision))
  )
    return null;
  return {
    entry: card._entry,
    generation: card._generation,
    hassUserId:
      typeof card?._hass?.user?.id === "string" ? card._hass.user.id : null,
    actor: actor.id,
    actorRevision: actor.revision,
    role: actor.role,
    taskId: item.id,
    taskRevision: item.revision,
    taskStatus: item.status,
    assignee: item.assignee,
    assigneeRevision: item.assignee_revision,
  };
}

function frameCurrent(card, snapshot) {
  const actor = member(card, snapshot?.actor);
  const userId =
    typeof card?._hass?.user?.id === "string" ? card._hass.user.id : null;
  return Boolean(
    connected(card) &&
      !card._error &&
      snapshot &&
      card._entry === snapshot.entry &&
      card._generation === snapshot.generation &&
      card._data?.actor === snapshot.actor &&
      card._data?.role === snapshot.role &&
      actor?.active === true &&
      actor.revision === snapshot.actorRevision &&
      actor.role === snapshot.role &&
      userId === snapshot.hassUserId &&
      card._data?.settings?.modules?.includes("tasks"),
  );
}

const sameAccess = (left, right) =>
  Boolean(left && right) && JSON.stringify(left) === JSON.stringify(right);

function attachment(item, id) {
  const current = Array.isArray(item?.report_attachments)
    ? item.report_attachments
    : [];
  for (const value of current) if (value?.id === id) return value;
  for (const report of Array.isArray(item?.previous_reports)
    ? item.previous_reports
    : [])
    for (const value of Array.isArray(report?.report_attachments)
      ? report.report_attachments
      : [])
      if (value?.id === id) return value;
  return null;
}

function exactAttachment(value) {
  return Boolean(
    value &&
      !Array.isArray(value) &&
      Object.keys(value).sort().join(",") ===
        "id,mime_type,purpose,revision,size_bytes,status" &&
      SEGMENT.test(value.id || "") &&
      validRevision(value.revision) &&
      value.purpose === "task_report" &&
      MIME_TYPES.has(value.mime_type) &&
      Number.isSafeInteger(value.size_bytes) &&
      value.size_bytes >= 1 &&
      value.size_bytes <= MAX_BYTES &&
      value.status === "attached",
  );
}

function reportSlot(item, generation) {
  if (!validRevision(generation)) return null;
  if (item?.report_generation === generation) return item;
  const matches = (Array.isArray(item?.previous_reports) ? item.previous_reports : [])
    .filter((report) => report?.report_generation === generation);
  return matches.length === 1 ? matches[0] : null;
}

function purgeAccess(card, item, value, generation) {
  const snapshot = access(card, item);
  const slot = reportSlot(item, generation);
  if (
    !snapshot ||
    snapshot.role !== "owner" ||
    !exactAttachment(value) ||
    attachment(item, value.id) !== value ||
    !slot ||
    !Array.isArray(slot.report_attachments) ||
    slot.report_attachments.length !== 1 ||
    slot.report_attachments[0]?.id !== value.id
  ) return null;
  return {
    ...snapshot,
    reportGeneration: generation,
    mediaId: value.id,
    mediaRevision: value.revision,
  };
}

function purgeDraftCurrent(card, draft) {
  const currentTask = task(card, draft?.access?.taskId);
  if (!currentTask || !frameCurrent(card, draft.access)) return false;
  const currentValue = attachment(currentTask, draft.access.mediaId);
  if (
    currentTask.revision === draft.access.taskRevision &&
    sameAccess(
      purgeAccess(
        card,
        currentTask,
        currentValue,
        draft.access.reportGeneration,
      ),
      draft.access,
    )
  ) return true;
  const slot = reportSlot(currentTask, draft.access.reportGeneration);
  return Boolean(
    draft.purgePending &&
      validRevision(currentTask.revision) &&
      currentTask.revision >= draft.access.taskRevision + 1 &&
      !currentValue &&
      typeof slot?.report_media_purged_at === "string" &&
      slot.report_media_purged_at.length > 0
  );
}

function draftCurrent(card, draft) {
  if (!draft?.access) return false;
  if (draft.kind === "purge") return purgeDraftCurrent(card, draft);
  const currentTask = task(card, draft.access.taskId);
  const currentAccess = access(card, currentTask, { upload: true });
  if (sameAccess(currentAccess, draft.access)) return true;
  if (!draft.submitPending || !draft.available || !currentTask) return false;
  const assignee = member(card, draft.access.assignee);
  const committed = attachment(currentTask, draft.available.id);
  return Boolean(
    frameCurrent(card, draft.access) &&
      currentTask.report_type === "photo" &&
      currentTask.id === draft.access.taskId &&
      currentTask.revision === draft.access.taskRevision + 1 &&
      currentTask.status === "submitted" &&
      currentTask.assignee === draft.access.assignee &&
      currentTask.assignee_revision === draft.access.assigneeRevision &&
      assignee?.active === true &&
      assignee.revision === draft.access.assigneeRevision &&
      exactAttachment(committed) &&
      committed.revision === draft.available.revision + 1
  );
}

function connected(card) {
  return !("isConnected" in card) || card.isConnected;
}

function live(card, draft = null) {
  return connected(card) && !card._error && !card._writing &&
    (!draft || card._taskMediaDraft === draft) &&
    (!draft || draftCurrent(card, draft));
}

function abortDraft(draft) {
  try {
    draft?.controller?.abort();
  } catch {
    // Abort is best effort; scope guards remain authoritative.
  }
}

function revokeDownload(value) {
  try {
    value?.controller?.abort();
  } catch {
    // Best effort.
  }
  if (value?.url)
    try {
      URL.revokeObjectURL(value.url);
    } catch {
      // Object URLs may not exist in a test/runtime without browser support.
    }
}

function revokeDraftPreview(draft) {
  if (!draft?.previewUrl) return false;
  try {
    URL.revokeObjectURL(draft.previewUrl);
  } catch {
    // Object URLs may not exist in a test/runtime without browser support.
  }
  draft.previewUrl = null;
  return true;
}

function ensureDraftPreview(card, draft) {
  if (
    draft?.previewUrl ||
    draft?.previewFailed ||
    !draft?.file ||
    card?._error ||
    card?._taskMediaDraft !== draft ||
    !draftCurrent(card, draft)
  )
    return;
  try {
    draft.previewUrl = URL.createObjectURL(draft.file);
  } catch {
    draft.previewFailed = true;
  }
}

function clearDraft(card, { conflict = false } = {}) {
  abortDraft(card?._taskMediaDraft);
  revokeDraftPreview(card?._taskMediaDraft);
  if (card) card._taskMediaDraft = null;
  if (card && conflict) card._actionError = "conflict";
}

function downloads(card) {
  if (!(card._taskMediaDownloads instanceof Map)) card._taskMediaDownloads = new Map();
  return card._taskMediaDownloads;
}

function errorCode(error) {
  return [
    "conflict",
    "forbidden",
    "media_invalid",
    "media_too_large",
    "media_unavailable",
    "module_disabled",
    "invalid_field",
    "photo_required",
    "storage_error",
  ].includes(error?.code)
    ? error.code
    : "media_unavailable";
}

async function refresh(card) {
  if (typeof card.refresh === "function") await card.refresh();
  if (typeof card.render === "function") card.render();
}

async function execute(card, draft, request) {
  // The caller owns _writing while the request is in flight. Recheck only the
  // durable authority snapshot here; _writing prevents a second UI action.
  if (
    !connected(card) ||
    card._taskMediaDraft !== draft ||
    !draftCurrent(card, draft)
  )
    throw Object.assign(new Error("conflict"), { code: "conflict" });
  return draft.hass.callWS({
    type: "family_assistant/execute",
    entry_id: draft.access.entry,
    action: request.action,
    payload: request.payload,
    operation_id: request.operation_id,
  });
}

function validReceipt(value, expectedStatus, expectedId = null, expectedRevision = null) {
  return Boolean(
    value &&
      !Array.isArray(value) &&
      Object.keys(value).sort().join(",") === "id,revision,status" &&
      SEGMENT.test(value.id || "") &&
      validRevision(value.revision) &&
      value.status === expectedStatus &&
      (expectedId === null || value.id === expectedId) &&
      (expectedRevision === null || value.revision === expectedRevision),
  );
}

async function reserveAndUpload(card, draft) {
  if (!live(card, draft) || draft.submitPending) return;
  const writeOwner = {};
  card._taskMediaWriteOwner = writeOwner;
  card._writing = true;
  card._actionError = null;
  try {
    if (!draft.reservation) {
      draft.reserveAttempted = true;
      const receipt = await execute(card, draft, draft.reserveRequest);
      if (!validReceipt(receipt, "reserved", null, 1))
        throw Object.assign(new Error("media_invalid"), { code: "media_invalid" });
      draft.reservation = Object.freeze({ ...receipt });
    }
    if (!draft.controller || draft.controller.signal.aborted)
      draft.controller = new AbortController();
    const available = await uploadMedia(draft.hass, {
      entryId: draft.access.entry,
      id: draft.reservation.id,
      revision: draft.reservation.revision,
      file: draft.file,
      signal: draft.controller.signal,
      isCurrent: () => card._taskMediaDraft === draft && draftCurrent(card, draft),
    });
    draft.available = Object.freeze({ ...available });
    draft.stage = "ready";
  } catch (error) {
    if (card._taskMediaDraft === draft && frameCurrent(card, draft.access))
      card._actionError = errorCode(error);
  } finally {
    const ownsWrite = card._taskMediaWriteOwner === writeOwner;
    if (ownsWrite) {
      card._taskMediaWriteOwner = null;
      card._writing = false;
    }
    if (ownsWrite && frameCurrent(card, draft.access)) await refresh(card);
  }
}

async function submitPhoto(card, draft) {
  if (!live(card, draft) || !draft.available) return;
  draft.submitPending = true;
  const writeOwner = {};
  card._taskMediaWriteOwner = writeOwner;
  card._writing = true;
  card._actionError = null;
  try {
    const receipt = await execute(card, draft, draft.submitRequest);
    if (
      !validReceipt(
        receipt,
        "submitted",
        draft.access.taskId,
        draft.access.taskRevision + 1,
      )
    )
      throw Object.assign(new Error("media_invalid"), { code: "media_invalid" });
    if (
      card._taskMediaDraft !== draft ||
      !frameCurrent(card, draft.access) ||
      !draftCurrent(card, draft)
    )
      return;
    clearDraft(card);
  } catch (error) {
    if (card._taskMediaDraft === draft && frameCurrent(card, draft.access))
      card._actionError = errorCode(error);
  } finally {
    const ownsWrite = card._taskMediaWriteOwner === writeOwner;
    if (ownsWrite) {
      card._taskMediaWriteOwner = null;
      card._writing = false;
    }
    if (ownsWrite && frameCurrent(card, draft.access)) await refresh(card);
  }
}

function button(card, label, callback, primary = false) {
  const result = typeof card.button === "function"
    ? card.button(label, callback, primary)
    : el("button", label, primary ? "primary" : "");
  result.type = "button";
  if (typeof card.button !== "function") result.addEventListener("click", callback);
  result.disabled = Boolean(card._writing);
  return result;
}

function confirmRow(copy, name) {
  const label = el("label", null, "task-media-confirm");
  const input = el("input");
  input.type = "checkbox";
  input.name = name;
  input.required = true;
  label.append(input, el("span", copy));
  return { label, input };
}

async function loadAttachment(card, item, value) {
  const current = attachment(task(card, item.id), value.id);
  if (!exactAttachment(current) || current.revision !== value.revision) return;
  const key = `${value.id}:${value.revision}`;
  const map = downloads(card);
  revokeDownload(map.get(key));
  const controller = new AbortController();
  const scope = access(card, task(card, item.id));
  const hass = card._hass;
  map.set(key, { controller, loading: true, scope, hass });
  card._actionError = null;
  if (typeof card.render === "function") card.render();
  try {
    const blob = await downloadMedia(hass, {
      entryId: card._entry,
      id: value.id,
      revision: value.revision,
      signal: controller.signal,
      isCurrent: () => {
        const liveValue = attachment(task(card, item.id), value.id);
        return frameCurrent(card, scope) &&
          sameAccess(access(card, task(card, item.id)), scope) &&
          exactAttachment(liveValue) && liveValue.revision === value.revision;
      },
    });
    const latest = map.get(key);
    if (latest?.controller !== controller) return;
    latest.url = URL.createObjectURL(blob);
    latest.loading = false;
  } catch (error) {
    const latest = map.get(key);
    if (latest?.controller === controller) map.delete(key);
    if (frameCurrent(card, scope)) card._actionError = errorCode(error);
  }
  if (frameCurrent(card, scope) && typeof card.render === "function") card.render();
}

function beginPurge(card, item, value, generation) {
  const snapshot = purgeAccess(card, item, value, generation);
  if (!snapshot || !live(card)) return false;
  if (card._taskMediaDraft) clearDraft(card);
  card._taskMediaDraft = {
    kind: "purge",
    access: Object.freeze({ ...snapshot }),
    hass: card._hass,
    stage: "reason",
    reason: "",
    request: null,
    purgePending: false,
  };
  return true;
}

function freezePurge(card, draft) {
  if (!live(card, draft) || draft.stage !== "reason") return false;
  const reason = typeof draft.reason === "string" ? draft.reason.trim() : "";
  if (!reason || reason.length > 500) return false;
  draft.reason = reason;
  draft.request = Object.freeze({
    action: "tasks.report_media_purge",
    payload: Object.freeze({
      id: draft.access.taskId,
      revision: draft.access.taskRevision,
      report_generation: draft.access.reportGeneration,
      media_id: draft.access.mediaId,
      media_revision: draft.access.mediaRevision,
      reason,
      confirmed: true,
    }),
    operation_id: crypto.randomUUID(),
  });
  draft.stage = "review";
  return true;
}

async function purgePhoto(card, draft) {
  if (!live(card, draft) || !draft.request) return;
  draft.purgePending = true;
  const writeOwner = {};
  card._taskMediaWriteOwner = writeOwner;
  card._writing = true;
  card._actionError = null;
  try {
    const receipt = await execute(card, draft, draft.request);
    if (
      !validReceipt(
        receipt,
        draft.access.taskStatus,
        draft.access.taskId,
        draft.access.taskRevision + 1,
      )
    ) throw Object.assign(new Error("media_invalid"), { code: "media_invalid" });
    if (
      card._taskMediaDraft !== draft ||
      !frameCurrent(card, draft.access) ||
      !draftCurrent(card, draft)
    ) return;
    clearDraft(card);
  } catch (error) {
    if (card._taskMediaDraft === draft && frameCurrent(card, draft.access))
      card._actionError = errorCode(error);
  } finally {
    const ownsWrite = card._taskMediaWriteOwner === writeOwner;
    if (ownsWrite) {
      card._taskMediaWriteOwner = null;
      card._writing = false;
    }
    if (ownsWrite && frameCurrent(card, draft.access)) await refresh(card);
  }
}

function renderAttachment(card, section, item, value, generation, label, copy) {
  if (!exactAttachment(value)) return;
  const box = el("div", null, "task-media-attachment");
  box.append(
    el("strong", label),
    el("p", `${value.mime_type} · ${value.size_bytes} ${copy.bytes}`, "sub"),
  );
  const key = `${value.id}:${value.revision}`;
  const loaded = downloads(card).get(key);
  if (loaded?.loading) box.append(el("p", copy.loading, "sub"));
  else if (loaded?.url) {
    const image = el("img", null, "task-media-preview");
    image.src = loaded.url;
    image.alt = copy.photo_alt;
    box.append(
      image,
      button(card, copy.remove_preview, () => {
        revokeDownload(loaded);
        downloads(card).delete(key);
        if (typeof card.render === "function") card.render();
      }),
    );
  } else box.append(button(card, copy.download, () => loadAttachment(card, item, value)));
  if (purgeAccess(card, item, value, generation))
    box.append(
      button(card, copy.remove_retained, () => {
        const currentTask = task(card, item.id);
        const currentValue = attachment(currentTask, value.id);
        if (!beginPurge(card, currentTask, currentValue, generation)) return;
        card._actionError = null;
        if (typeof card.render === "function") card.render();
      }),
    );
  section.append(box);
}

function beginReview(card, item, file) {
  if (!file || !MIME_TYPES.has(file.type) || !Number.isSafeInteger(file.size) ||
      file.size < 1 || file.size > MAX_BYTES)
    return false;
  const snapshot = access(card, item, { upload: true });
  if (!snapshot || !OPEN.has(item.status)) return false;
  if (card._taskMediaDraft) clearDraft(card);
  const frozenAccess = Object.freeze({ ...snapshot });
  card._taskMediaDraft = {
    kind: "upload",
    access: frozenAccess,
    // Keep using the authenticated session object that began the reviewed flow.
    hass: card._hass,
    stage: "review",
    // File objects are immutable browser handles. Keep the exact reviewed
    // object reference; freezing host objects is not portable across browsers.
    file,
    reserveRequest: Object.freeze({
      action: "media.reserve",
      payload: Object.freeze({
        purpose: "task_report",
        task_id: item.id,
        task_revision: item.revision,
        uploader_revision: snapshot.actorRevision,
      }),
      operation_id: crypto.randomUUID(),
    }),
    submitRequest: Object.freeze({
      action: "tasks.submit",
      payload: null,
      operation_id: crypto.randomUUID(),
    }),
    reservation: null,
    reserveAttempted: false,
    available: null,
    submitPending: false,
    controller: new AbortController(),
    previewUrl: null,
    previewFailed: false,
  };
  return true;
}

function bindSubmitRequest(draft) {
  if (draft.submitRequest.payload || !draft.available) return;
  draft.submitRequest = Object.freeze({
    ...draft.submitRequest,
    payload: Object.freeze({
      id: draft.access.taskId,
      revision: draft.access.taskRevision,
      media: Object.freeze({ id: draft.available.id, revision: draft.available.revision }),
    }),
  });
}

function renderPurge(card, section, draft, copy) {
  if (!purgeDraftCurrent(card, draft)) {
    clearDraft(card, { conflict: true });
    section.append(el("p", copy.stale, "sub"));
    return;
  }
  const review = el("div", null, "task-media-purge");
  review.dataset.taskMediaPurge = draft.access.mediaId;
  review.append(el("h5", copy.remove_title), el("p", copy.remove_warning, "sub"));
  if (draft.stage === "reason") {
    const label = el("label", copy.remove_reason);
    const input = el("textarea");
    input.name = "purge_reason";
    input.maxLength = 500;
    input.required = true;
    input.value = draft.reason;
    input.addEventListener("input", () => {
      draft.reason = input.value;
      action.disabled = !input.value.trim() || input.value.trim().length > 500 || card._writing;
    });
    label.append(input);
    const action = button(card, copy.review_remove, () => {
      if (!freezePurge(card, draft)) return;
      if (typeof card.render === "function") card.render();
    }, true);
    action.disabled = !draft.reason.trim();
    const actions = el("div", null, "task-media-actions");
    actions.append(
      action,
      button(card, copy.cancel, () => {
        if (!live(card, draft)) return;
        clearDraft(card);
        if (typeof card.render === "function") card.render();
      }),
    );
    review.append(label, actions);
  } else {
    review.append(
      el("p", copy.remove_reviewed),
      el("p", draft.reason, "task-media-file"),
    );
    const confirmation = confirmRow(copy.confirm_remove, "confirm_purge");
    confirmation.input.checked = draft.purgePending;
    confirmation.input.disabled = draft.purgePending;
    const action = button(
      card,
      draft.purgePending ? copy.retry_remove : copy.remove_confirmed,
      () => purgePhoto(card, draft),
      true,
    );
    action.disabled = !draft.purgePending;
    confirmation.input.addEventListener("change", () => {
      action.disabled = !confirmation.input.checked || card._writing;
    });
    const actions = el("div", null, "task-media-actions");
    actions.append(
      action,
      button(card, copy.cancel, () => {
        if (!live(card, draft)) return;
        clearDraft(card);
        if (typeof card.render === "function") card.render();
      }),
    );
    review.append(confirmation.label, actions);
  }
  section.append(review);
}

export function reconcileTaskMediaRefresh(card) {
  if (!card) return false;
  let changed = false;
  const draft = card._taskMediaDraft;
  if (draft && card._error) {
    abortDraft(draft);
    changed = revokeDraftPreview(draft) || changed;
  } else if (draft && !draftCurrent(card, draft)) {
    clearDraft(card, { conflict: true });
    changed = true;
  }
  for (const [key, value] of downloads(card)) {
    const [id, revision] = key.split(":");
    const currentTask = task(card, value.scope?.taskId);
    const current = attachment(currentTask, id);
    if (
      !sameAccess(access(card, currentTask), value.scope) ||
      !exactAttachment(current) ||
      current.revision !== Number(revision)
    ) {
      revokeDownload(value);
      downloads(card).delete(key);
      changed = true;
    }
  }
  return changed;
}

export function disposeTaskMedia(card, { keepDraft = false } = {}) {
  if (!card) return;
  if (keepDraft) {
    abortDraft(card._taskMediaDraft);
    revokeDraftPreview(card._taskMediaDraft);
  }
  else clearDraft(card);
  for (const value of downloads(card).values()) revokeDownload(value);
  downloads(card).clear();
}

export function renderTaskMedia(card, item) {
  if (!card || card._error || !item || item.report_type !== "photo") return null;
  // Projection filtering is authoritative, but this local check also removes a
  // stale child DOM immediately after an identity or assignment change.
  if (!access(card, item)) return null;
  const copy = copyOf(card);
  const section = el("section", null, "task-media");
  section.dataset.taskMediaId = item.id || "";
  section.append(el("style", STYLE), el("h4", copy.title));
  for (const value of Array.isArray(item.report_attachments) ? item.report_attachments : [])
    renderAttachment(card, section, item, value, item.report_generation, copy.current, copy);
  if (typeof item.report_media_purged_at === "string")
    section.append(el("p", copy.removed_marker, "sub"));
  if (PRIVILEGED.has(card?._data?.role))
    for (const report of Array.isArray(item.previous_reports) ? item.previous_reports : []) {
      for (const value of Array.isArray(report?.report_attachments)
        ? report.report_attachments
        : [])
        renderAttachment(
          card,
          section,
          item,
          value,
          report.report_generation,
          copy.previous,
          copy,
        );
      if (typeof report?.report_media_purged_at === "string")
        section.append(el("p", copy.removed_previous_marker, "sub"));
    }

  const currentAccess = access(card, item, { upload: true });
  const draft = card._taskMediaDraft?.access?.taskId === item.id
    ? card._taskMediaDraft
    : null;
  if (draft?.kind === "purge") {
    renderPurge(card, section, draft, copy);
    return section;
  }
  if ((!currentAccess || !OPEN.has(item.status)) && !draft) return section;
  if (!draft) {
    const form = el("form", null, "task-media-form");
    form.append(el("p", copy.privacy, "sub"));
    const label = el("label", copy.choose);
    const input = el("input");
    input.type = "file";
    input.name = "photo";
    input.accept = "image/jpeg,image/png,image/webp";
    input.required = true;
    label.append(input);
    const review = button(card, copy.review, () => {
      if (
        !live(card) ||
        !sameAccess(
          access(card, task(card, item.id), { upload: true }),
          currentAccess,
        )
      )
        return;
      if (!beginReview(card, task(card, item.id), input.files?.[0])) {
        card._actionError = "media_invalid";
        if (typeof card.render === "function") card.render();
        return;
      }
      card._actionError = null;
      if (typeof card.render === "function") card.render();
    });
    form.append(label, review);
    form.addEventListener("submit", (event) => event.preventDefault());
    section.append(form);
    return section;
  }

  if (!draftCurrent(card, draft)) {
    clearDraft(card, { conflict: true });
    section.append(el("p", copy.stale, "sub"));
    return section;
  }
  const review = el("div", null, "task-media-review");
  review.append(el("h5", copy.review_title));
  const rawFileName =
    typeof draft.file?.name === "string" ? draft.file.name : copy.title;
  const fileName =
    rawFileName.length <= MAX_FILE_NAME_DISPLAY
      ? rawFileName
      : `${rawFileName.slice(0, MAX_FILE_NAME_DISPLAY - 1)}…`;
  review.append(
    el("p", fileName, "task-media-file"),
    el("p", `${draft.file.type} · ${draft.file.size} ${copy.bytes}`, "sub"),
    el("p", copy.privacy, "sub"),
  );
  ensureDraftPreview(card, draft);
  if (draft.previewUrl) {
    const preview = el("img", null, "task-media-preview");
    const previewUrl = draft.previewUrl;
    preview.src = previewUrl;
    preview.alt = copy.selected_photo_alt;
    preview.addEventListener("error", () => {
      if (
        card._taskMediaDraft !== draft ||
        draft.previewUrl !== previewUrl ||
        !frameCurrent(card, draft.access)
      )
        return;
      revokeDraftPreview(draft);
      draft.previewFailed = true;
      if (typeof card.render === "function") card.render();
    });
    review.append(preview);
  } else if (draft.previewFailed) review.append(el("p", copy.preview_failed, "sub"));
  if (draft.previewFailed) {
    const actions = el("div", null, "task-media-actions");
    actions.append(
      button(card, copy.cancel, () => {
        if (!live(card, draft)) return;
        clearDraft(card);
        if (typeof card.render === "function") card.render();
      }),
    );
    review.append(actions);
    section.append(review);
    return section;
  }
  if (draft.stage !== "ready") {
    const confirmation = confirmRow(copy.confirm_upload, "confirm_upload");
    const action = button(
      card,
      draft.reserveAttempted ? copy.retry_upload : copy.upload,
      () => reserveAndUpload(card, draft),
      true,
    );
    action.disabled = true;
    confirmation.input.addEventListener("change", () => {
      action.disabled = !confirmation.input.checked || card._writing;
    });
    review.append(confirmation.label);
    const actions = el("div", null, "task-media-actions");
    actions.append(
      action,
      button(card, copy.cancel, () => {
        if (!live(card, draft)) return;
        clearDraft(card);
        if (typeof card.render === "function") card.render();
      }),
    );
    review.append(actions);
  } else {
    bindSubmitRequest(draft);
    review.append(el("p", copy.ready), el("p", copy.abandoned, "sub"));
    const confirmation = confirmRow(copy.confirm_submit, "confirm_submit");
    const action = button(
      card,
      draft.submitPending ? copy.retry_submit : copy.submit,
      () => submitPhoto(card, draft),
      true,
    );
    action.disabled = !draft.submitPending;
    confirmation.input.checked = draft.submitPending;
    confirmation.input.disabled = draft.submitPending;
    confirmation.input.addEventListener("change", () => {
      action.disabled = !confirmation.input.checked || card._writing;
    });
    const actions = el("div", null, "task-media-actions");
    actions.append(
      action,
      button(card, copy.cancel, () => {
        if (!live(card, draft)) return;
        clearDraft(card);
        if (typeof card.render === "function") card.render();
      }),
    );
    review.append(confirmation.label, actions);
  }
  section.append(review);
  return section;
}
