/* Explicit authenticated fault images. No completion, messaging or model side effects. */
import { downloadMedia, uploadMedia } from "./media-client.js";
import { FAULT_PHOTO_COPY } from "./fault-photo-copy.js";

const SEGMENT = /^[A-Za-z0-9_-]{1,128}$/;
const ROLES = new Set(["owner", "parent", "adult", "child"]);
const MIME = new Set(["image/jpeg", "image/png", "image/webp"]);
const MAX = 10 * 1024 * 1024;
const revision = (value) => Number.isSafeInteger(value) && value >= 1;
const same = (left, right) => Boolean(left && right) && JSON.stringify(left) === JSON.stringify(right);
const el = (tag, text, className) => {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = String(text);
  if (className) node.className = className;
  return node;
};
const copyOf = (card) => FAULT_PHOTO_COPY[(card._config?.language || card._hass?.language || "en").split("-")[0]] || FAULT_PHOTO_COPY.en;
const faultById = (card, id) => card._data?.maintenance?.faults?.find?.((item) => item.id === id);
function frame(card) {
  const data = card?._data;
  const actor = data?.members?.find?.((item) => item.id === data.actor);
  if (!card?.isConnected || card._error || !SEGMENT.test(card._entry || "") ||
      !actor || actor.active !== true || actor.role !== data.role || !ROLES.has(actor.role) ||
      !revision(actor.revision) || !data.settings?.modules?.includes("maintenance") ||
      !data.settings?.modules?.includes("tasks")) return null;
  return {
    entry: card._entry, generation: card._generation, user: card._hass?.user?.id ?? null,
    actor: actor.id, role: actor.role, actorRevision: actor.revision,
    roster: data.members.map((item) => [item.id, item.revision, item.role, item.active]),
  };
}
function metadata(value) {
  return Boolean(value && !Array.isArray(value) &&
    Object.keys(value).sort().join(",") === "id,mime_type,purpose,revision,size_bytes,status" &&
    SEGMENT.test(value.id || "") && revision(value.revision) &&
    value.purpose === "maintenance_fault" && value.status === "attached" && MIME.has(value.mime_type) &&
    Number.isSafeInteger(value.size_bytes) && value.size_bytes > 0 && value.size_bytes <= MAX);
}
function access(card, fault) {
  const base = frame(card);
  if (!base || !fault || !SEGMENT.test(fault.id || "") || !revision(fault.revision) ||
      fault.status !== "reported" || !SEGMENT.test(fault.task_id || "") || !revision(fault.task_revision)) return null;
  return {
    ...base, id: fault.id, revision: fault.revision,
    task: fault.task_id, taskRevision: fault.task_revision, status: fault.task_status,
    assignee: fault.assignee, reporter: fault.reporter, summary: fault.summary,
    canUpload: fault.can_upload_photo === true,
    photo: metadata(fault.photo_attachment) ? { ...fault.photo_attachment } : null,
  };
}
function current(card, draft) {
  if (!draft || card._faultPhotoDraft !== draft) return false;
  const latest = access(card, faultById(card, draft.scope.id));
  if (same(latest, draft.scope)) return true;
  if (!latest || !draft.pending || latest.revision !== draft.scope.revision + 1) return false;
  // A lost response may follow a committed attach/purge. Keep only that exact retry.
  const normalized = { ...latest, revision: draft.scope.revision, canUpload: draft.scope.canUpload, photo: draft.scope.photo };
  if (!same(normalized, draft.scope)) return false;
  return draft.kind === "upload"
    ? latest.photo?.id === draft.available?.id && latest.photo?.revision === draft.available?.revision + 1
    : latest.photo === null && (faultById(card, draft.scope.id)?.photo_purge?.media_id === draft.scope.photo.id);
}
function clearDraft(card) {
  const draft = card?._faultPhotoDraft;
  draft?.controller?.abort();
  if (draft?.preview) URL.revokeObjectURL(draft.preview);
  if (card) card._faultPhotoDraft = null;
}
function revoke(item) {
  item?.controller?.abort();
  if (item?.url) URL.revokeObjectURL(item.url);
}
export function disposeFaultPhotos(card, { keepDraft = false } = {}) {
  if (keepDraft && card._faultPhotoDraft) {
    card._faultPhotoDraft.controller?.abort();
    if (card._faultPhotoDraft.preview) URL.revokeObjectURL(card._faultPhotoDraft.preview);
    card._faultPhotoDraft.preview = null;
  } else clearDraft(card);
  for (const item of card?._faultPhotoDownloads?.values?.() || []) revoke(item);
  card._faultPhotoDownloads = new Map();
}
export function reconcileFaultPhotos(card) {
  let changed = false;
  if (card._faultPhotoDraft && !current(card, card._faultPhotoDraft)) {
    clearDraft(card); card._actionError = "conflict"; changed = true;
  }
  for (const [id, item] of card._faultPhotoDownloads || []) {
    if (!same(access(card, faultById(card, id)), item.scope)) {
      revoke(item); card._faultPhotoDownloads.delete(id); changed = true;
    }
  }
  return changed;
}
const request = (action, payload) => Object.freeze({ action, payload: Object.freeze(payload), operation_id: crypto.randomUUID() });
const fail = (code) => { throw Object.assign(new Error(code), { code }); };
function errorCode(error) {
  return ["conflict", "forbidden", "media_invalid", "media_too_large", "media_unavailable", "module_disabled", "invalid_field", "storage_error", "quota_exceeded"].includes(error?.code) ? error.code : "media_unavailable";
}
async function execute(card, draft, message) {
  if (!current(card, draft)) fail("conflict");
  return draft.hass.callWS({ type: "family_assistant/execute", entry_id: draft.scope.entry, ...message });
}
function receipt(value, status, id, version) {
  if (!value || Object.keys(value).sort().join(",") !== "id,revision,status" ||
      !SEGMENT.test(value.id || "") || value.status !== status || value.revision !== version ||
      (id !== null && value.id !== id)) fail("media_invalid");
  return Object.freeze({ ...value });
}
async function write(card, draft, operation) {
  if (card._writing || !current(card, draft)) return;
  const owner = {};
  card._faultPhotoWriteOwner = owner; card._writing = true; card._actionError = null;
  card.render();
  try { await operation(); }
  catch (error) {
    if (card._faultPhotoDraft === draft && same(frame(card), draft.frame)) card._actionError = errorCode(error);
  } finally {
    if (card._faultPhotoWriteOwner === owner) {
      card._faultPhotoWriteOwner = null; card._writing = false;
      if (same(frame(card), draft.frame)) { await card.refresh(); card.render(); }
    }
  }
}
async function upload(card, draft) {
  return write(card, draft, async () => {
    draft.attempted = true;
    if (!draft.reservation) draft.reservation = receipt(await execute(card, draft, draft.reserveRequest), "reserved", null, 1);
    draft.controller = new AbortController();
    draft.available = await uploadMedia(draft.hass, {
      entryId: draft.scope.entry, id: draft.reservation.id, revision: draft.reservation.revision,
      file: draft.file, signal: draft.controller.signal, isCurrent: () => current(card, draft),
    });
  });
}
async function commit(card, draft) {
  return write(card, draft, async () => {
    if (!draft.pending) {
      const media = Object.freeze({ id: draft.kind === "upload" ? draft.available.id : draft.scope.photo.id,
        revision: draft.kind === "upload" ? draft.available.revision : draft.scope.photo.revision });
      draft.pending = request(draft.kind === "upload" ? "maintenance.fault_photo_attach" : "maintenance.fault_photo_purge", {
        id: draft.scope.id, revision: draft.scope.revision, actor_member_revision: draft.scope.actorRevision, media,
        ...(draft.kind === "purge" ? { reason: draft.reason.trim() } : {}),
      });
    }
    receipt(await execute(card, draft, draft.pending), "reported", draft.scope.id, draft.scope.revision + 1);
    if (current(card, draft)) clearDraft(card);
  });
}
async function show(card, scope) {
  if (!same(access(card, faultById(card, scope.id)), scope) || !scope.photo) return;
  if (!card._faultPhotoDownloads) card._faultPhotoDownloads = new Map();
  revoke(card._faultPhotoDownloads.get(scope.id));
  const item = { scope, controller: new AbortController(), loading: true };
  card._faultPhotoDownloads.set(scope.id, item);
  card.render();
  const check = () => card._faultPhotoDownloads?.get(scope.id) === item && same(access(card, faultById(card, scope.id)), scope);
  try {
    const blob = await downloadMedia(card._hass, { entryId: scope.entry, id: scope.photo.id, revision: scope.photo.revision,
      signal: item.controller.signal, isCurrent: check });
    if (!check()) return;
    item.url = URL.createObjectURL(blob); item.loading = false;
  } catch (error) {
    if (check()) { card._faultPhotoDownloads.delete(scope.id); card._actionError = errorCode(error); }
  }
  if (frame(card) && card._entry === scope.entry && card._generation === scope.generation) card.render();
}

export function renderFaultPhoto(card, container, fault) {
  reconcileFaultPhotos(card);
  const scope = access(card, fault);
  if (!scope) return;
  const copy = copyOf(card);
  const section = el("section", undefined, "fault-photo"); section.dataset.faultPhoto = fault.id;
  section.append(el("style", `.fault-photo{display:grid;gap:8px;margin-top:10px}.fault-photo form{display:grid;gap:10px}.fault-photo p{margin:0;overflow-wrap:anywhere}.fault-photo img{display:block;max-width:100%;max-height:360px;object-fit:contain}.fault-photo input[type=file],.fault-photo textarea{box-sizing:border-box;max-width:100%}.fault-photo textarea{width:100%;min-height:72px}.fault-photo label{display:block}.fault-photo input[type=checkbox]{margin-inline-end:8px}.fault-photo-actions{display:flex;gap:8px;flex-wrap:wrap}@media(max-width:520px){.fault-photo-actions>button{width:100%}}`));
  const guard = (node, draft = null) => node.isConnected && card.shadowRoot.contains(node) && !card._writing &&
    (draft ? current(card, draft) : same(access(card, faultById(card, scope.id)), scope));
  const button = (text, action, draft = null) => {
    const node = el("button", text); node.type = "button"; node.disabled = Boolean(card._writing);
    node.addEventListener("click", () => { if (guard(node, draft)) action(); }); return node;
  };
  const begin = (kind) => {
    clearDraft(card);
    card._faultPhotoDraft = { kind, scope, frame: frame(card), hass: card._hass, reason: "" };
    card._actionError = null; card.render();
  };
  let draft = card._faultPhotoDraft;
  if (draft?.scope.id !== fault.id) draft = null;
  if (scope.canUpload && !draft) section.append(button(copy.add, () => begin("upload")));
  if (scope.photo) {
    section.append(el("strong", copy.title));
    const item = card._faultPhotoDownloads?.get(fault.id);
    if (item?.url) {
      const img = el("img"); img.src = item.url; img.alt = `${copy.title}: ${fault.summary}`; section.append(img);
      section.append(button(copy.hide, () => { revoke(item); card._faultPhotoDownloads.delete(fault.id); card.render(); }));
    } else {
      const view = button(item?.loading ? copy.pending : copy.view, () => show(card, scope));
      view.disabled ||= Boolean(item?.loading); section.append(view);
    }
    if (scope.role === "owner" && !draft) section.append(button(copy.purge, () => begin("purge")));
  }
  if (draft) {
    const form = el("form"); form.dataset.faultPhotoForm = draft.kind;
    form.append(el("strong", `${draft.kind === "upload" ? copy.title : copy.purge}: ${draft.scope.summary}`),
      el("p", draft.kind === "upload" ? copy.note : copy.purgeNote, "sub"));
    if (draft.kind === "upload") form.append(el("p", copy.privacy, "sub"));
    if (draft.file && !draft.preview) draft.preview = URL.createObjectURL(draft.file);
    if (draft.kind === "upload" && !draft.available) {
      const label = el("label", copy.file), input = el("input");
      input.type = "file"; input.accept = "image/jpeg,image/png,image/webp"; input.disabled = Boolean(draft.attempted || card._writing);
      label.append(input); form.append(label);
      input.addEventListener("change", () => {
        if (!guard(input, draft) || draft.attempted) return;
        const file = input.files?.[0];
        if (!(file instanceof Blob) || !MIME.has(file.type) || !file.size || file.size > MAX) {
          card._actionError = file?.size > MAX ? "media_too_large" : "media_invalid"; card.render(); return;
        }
        if (draft.preview) URL.revokeObjectURL(draft.preview);
        draft.file = file; draft.preview = URL.createObjectURL(file);
        draft.reserveRequest = request("media.reserve", { purpose: "maintenance_fault", fault_id: scope.id, fault_revision: scope.revision, uploader_revision: scope.actorRevision });
        card._actionError = null; card.render();
      });
      const submit = button(draft.attempted ? copy.retry : copy.upload, () => upload(card, draft), draft);
      submit.disabled ||= !draft.file; form.append(submit);
    }
    if (draft.preview) { const img = el("img"); img.src = draft.preview; img.alt = copy.title; form.append(img); }
    if (draft.available || draft.kind === "purge") {
      if (draft.available) form.append(el("p", copy.ready, "sub"));
      if (draft.kind === "purge") {
        const label = el("label", copy.reason), reason = el("textarea"); reason.name = "reason";
        reason.value = draft.reason; reason.maxLength = 500; reason.required = true; reason.disabled = Boolean(draft.pending || card._writing);
        label.append(reason); form.append(label);
        reason.addEventListener("input", () => { if (guard(reason, draft) && !draft.pending) draft.reason = reason.value; });
      }
      const label = el("label"), confirm = el("input"); confirm.type = "checkbox"; confirm.name = "reviewed"; confirm.required = true;
      confirm.checked = Boolean(draft.reviewed); confirm.disabled = Boolean(card._writing);
      label.append(confirm, el("span", draft.kind === "upload" ? copy.confirm : copy.confirmPurge)); form.append(label);
      confirm.addEventListener("change", () => { if (guard(confirm, draft)) draft.reviewed = confirm.checked; });
      const submit = el("button", draft.pending ? copy.retry : draft.kind === "upload" ? copy.attach : copy.purge); submit.type = "submit";
      submit.disabled = Boolean(card._writing); form.append(submit);
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        if (!guard(form, draft) || !confirm.checked || (draft.kind === "purge" && !draft.reason.trim())) return;
        commit(card, draft);
      });
    } else form.addEventListener("submit", (event) => event.preventDefault());
    form.append(button(copy.cancel, () => { clearDraft(card); card.render(); }, draft)); section.append(form);
  }
  if (["owner", "parent"].includes(scope.role) && Array.isArray(fault.photo_history) && fault.photo_history.length) {
    const history = el("details"), list = el("ul"); history.append(el("summary", copy.history));
    for (const event of fault.photo_history.slice(-100)) {
      if (!["fault_photo_attach", "fault_photo_purge"].includes(event.action)) continue;
      const name = card._data.members.find((item) => item.id === event.actor)?.name || event.actor;
      list.append(el("li", `${event.action === "fault_photo_attach" ? copy.attached : copy.purged} · ${name} · ${event.at}${event.reason ? ` · ${event.reason}` : ""}`));
    }
    history.append(list); section.append(history);
  }
  if (section.children.length > 1) container.append(section);
}
