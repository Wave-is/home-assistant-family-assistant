/* Explicit parent unreviewed discovery subscriptions: local evidence, no router writes. */

import { NETWORK_WATCH_COPY } from "./network-watch-copy.js";

const ROLES = new Set(["owner", "parent"]);
const DEFAULT_INTERVAL = 30;

const node = (tag, val, cls) => {
  const el = document.createElement(tag);
  if (val !== undefined && val !== null) el.textContent = String(val);
  if (cls) el.className = cls;
  return el;
};

const clone = (v) => JSON.parse(JSON.stringify(v));
const deepFreeze = (v) => {
  if (!v || typeof v !== "object" || Object.isFrozen(v)) return v;
  Object.freeze(v);
  for (const c of Object.values(v)) deepFreeze(c);
  return v;
};

const createOperationId = () =>
  typeof crypto?.randomUUID === "function"
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;

const STYLE = `
  .network-watch{display:grid;gap:12px}.network-watch-guide{margin:0}
  .network-watch-card,.network-watch-review{display:grid;gap:8px;min-width:0}
  .network-watch-card p,.network-watch-card dd,.network-watch-review p,.network-watch-review dd{overflow-wrap:anywhere;margin:0}
  .network-watch-card dl,.network-watch-review dl{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:6px 10px;margin:0}
  .network-watch-card dt,.network-watch-review dt{font-weight:600}.network-watch-card dd,.network-watch-review dd{margin:0}
  .network-watch-badge{display:inline-block;padding:2px 8px;border-radius:12px;font-size:12px;font-weight:600}
  .network-watch-badge.active{background:rgba(30,140,60,.15);color:#1e8c3c}
  .network-watch-badge.suspended{background:rgba(220,130,0,.15);color:#dc8200}
  .network-watch-badge.disabled{background:rgba(140,140,140,.15);color:#666}
  .network-watch-alert{padding:10px 14px;border-radius:8px;border:1px solid}.network-watch-alert.warning{background:rgba(240,160,20,.1);border-color:rgba(240,160,20,.3)}
  .network-watch-actions{display:flex;flex-wrap:wrap;gap:8px}.network-watch-confirm{display:flex;flex-direction:row;justify-content:flex-start;gap:8px;align-items:flex-start}
  .network-watch-confirm input{flex:0 0 auto;margin-top:3px}.network-watch-field{display:grid;gap:6px}.network-watch-field input{max-width:200px}
  @media(max-width:520px){.network-watch-actions>button{width:100%}.network-watch-card dl,.network-watch-review dl{grid-template-columns:minmax(0,1fr)}.network-watch-card dd,.network-watch-review dd{margin-bottom:4px}.network-watch-field input{max-width:100%}}
`;

function copyOf(card) {
  const lang = card?._config?.language || card?._hass?.language || "en";
  return NETWORK_WATCH_COPY[String(lang).split(/[-_]/)[0].toLowerCase()] || NETWORK_WATCH_COPY.en;
}

const validRevision = (v) => Number.isSafeInteger(v) && v >= 1;
const validInterval = (v) => Number.isSafeInteger(v) && v >= 5 && v <= 1440;
const members = (card) => (Array.isArray(card?._data?.members) ? card._data.members : []);
const member = (card, id) => members(card).find((m) => m?.id === id) || null;
const admission = (card) => (typeof card?._data?.network?.admission === "object" ? card._data.network.admission : null);
const watch = (card) => {
  const w = card?._data?.network?.admission?.watch;
  return w && typeof w === "object" && w.unavailable !== true ? w : null;
};

const validWatch = (w, actorRev) => Boolean(
  w && validRevision(w.actor_revision) && w.actor_revision === actorRev &&
  (w.watch_revision === null || (validRevision(w.watch_revision) && w.watch_revision < Number.MAX_SAFE_INTEGER)) &&
  typeof w.enabled === "boolean" && typeof w.effective === "boolean" &&
  validInterval(w.min_interval_minutes) && (w.baseline_at === null || typeof w.baseline_at === "string") &&
  Number.isSafeInteger(w.seen_count) && w.seen_count >= 0 &&
  Number.isSafeInteger(w.pending_count) && w.pending_count >= 0 &&
  typeof w.capacity_blocked === "boolean" && typeof w.private_chat_ready === "boolean" &&
  (!w.effective || (w.enabled && !w.capacity_blocked && w.private_chat_ready)),
);

function access(card) {
  const data = card?._data, actor = member(card, data?.actor), adm = admission(card), w = watch(card);
  if (!data?.actor || !ROLES.has(data?.role) || actor?.active !== true || actor.role !== data.role ||
      !validRevision(actor.revision) || !Array.isArray(data?.settings?.modules) ||
      !data.settings.modules.includes("mikrotik") || !adm || !validWatch(w, actor.revision)) return null;
  return {
    generation: card._generation ?? null, entry: card._entry ?? null, userId: card._hass?.user?.id ?? null,
    actor: data.actor, role: data.role, actorRevision: actor.revision, backend: adm.backend ?? null,
    watchRevision: w.watch_revision ?? null,
  };
}

const sameAccess = (card, exp, allowNext = false) => {
  const cur = access(card);
  if (cur && exp && allowNext && cur.watchRevision === (exp.watchRevision || 0) + 1)
    cur.watchRevision = exp.watchRevision;
  return Boolean(cur && exp) && JSON.stringify(cur) === JSON.stringify(exp);
};

const sourceSnapshot = (w) => ({
  actor_revision: w.actor_revision, watch_revision: w.watch_revision, enabled: w.enabled,
  effective: w.effective, min_interval_minutes: w.min_interval_minutes, baseline_at: w.baseline_at,
  seen_count: w.seen_count, pending_count: w.pending_count, capacity_blocked: w.capacity_blocked,
  private_chat_ready: w.private_chat_ready,
});

const sameWatch = (l, r) => Boolean(
  l && r && l.actor_revision === r.actor_revision && l.watch_revision === r.watch_revision &&
  l.enabled === r.enabled && l.capacity_blocked === r.capacity_blocked,
);

function draftAllowed(card, draft, exact = true) {
  if (!draft?.source || !sameAccess(card, draft.access)) return false;
  const w = watch(card);
  if (!w || (exact && !sameWatch(w, draft.source))) return false;
  if (draft.desired) {
    const adm = admission(card);
    if (!adm || adm.status !== "fresh" || !adm.token || adm.token !== draft.token || !w.private_chat_ready) {
      return false;
    }
  }
  return true;
}

function pendingAllowed(card, draft) {
  if (!draft?.pending?.action || !draft?.source || !sameAccess(card, draft.access, true)) return false;
  const w = watch(card);
  if (!w) return false;
  const expRev = (draft.source.watch_revision || 0) + 1;
  return (sameWatch(w, draft.source) && draftAllowed(card, draft)) || (w.watch_revision === expRev && w.enabled === draft.desired);
}

function watchProjection(data) {
  const modules = Array.isArray(data?.settings?.modules) ? data.settings.modules : [];
  const actor = data?.actor ?? null, m = Array.isArray(data?.members) ? data.members.find((r) => r?.id === actor) : null;
  const adm = data?.network?.admission, w = adm?.watch;
  return {
    mikrotik: modules.includes("mikrotik"), actor, role: data?.role ?? null,
    actorActive: m?.active ?? null, actorRevision: m?.revision ?? null, status: adm?.status ?? null,
    token: adm?.token ?? null, backend: adm?.backend ?? null,
    watch: w && typeof w === "object" ? {
      actor_revision: w.actor_revision ?? null, watch_revision: w.watch_revision ?? null,
      enabled: w.enabled ?? null, effective: w.effective ?? null,
      min_interval_minutes: w.min_interval_minutes ?? null, baseline_at: w.baseline_at ?? null,
      seen_count: w.seen_count ?? null, pending_count: w.pending_count ?? null,
      capacity_blocked: w.capacity_blocked ?? null, private_chat_ready: w.private_chat_ready ?? null,
      unavailable: w.unavailable ?? null,
    } : null,
  };
}

export function reconcileNetworkWatchRefresh(card, previousData) {
  if (!card) return false;
  const changed = JSON.stringify(watchProjection(previousData)) !== JSON.stringify(watchProjection(card._data));
  let force = changed && Boolean(card._networkWatchDraft || card.shadowRoot?.querySelector(".network-watch"));
  const draft = card._networkWatchDraft;
  if (!draft) return force;

  if (draft.pending) {
    const w = watch(card);
    const expRev = (draft.source.watch_revision || 0) + 1;
    if (pendingAllowed(card, draft) && w && w.watch_revision === expRev && w.enabled === draft.desired && !card._actionError) {
      card._networkWatchDraft = null;
      return true;
    }
    if (!pendingAllowed(card, draft)) {
      card._networkWatchDraft = null;
      card._actionError = "conflict";
      return true;
    }
  } else if (!draftAllowed(card, draft, true)) {
    card._networkWatchDraft = null;
    card._actionError = "conflict";
    return true;
  }
  return force;
}

export function renderNetworkWatch(card, body) {
  if (!card || !body || !card._data) return;
  const currentAccess = access(card);
  if (!currentAccess) { card._networkWatchDraft = null; return; }
  if (card._networkWatchDraft && !(card._networkWatchDraft.pending ? pendingAllowed(card, card._networkWatchDraft) : draftAllowed(card, card._networkWatchDraft, true))) {
    card._networkWatchDraft = null;
    card._actionError = "conflict";
  }

  const copy = copyOf(card);
  const detached = () => !body.isConnected;
  const guard = (control, draft = null, exact = true) => {
    if (draft && card._networkWatchDraft !== draft) return false;
    if (!sameAccess(card, draft?.access || currentAccess, Boolean(draft?.pending)) || (draft && (draft.pending ? !pendingAllowed(card, draft) : !draftAllowed(card, draft, exact)))) {
      card._networkWatchDraft = null;
      card._actionError = "conflict";
      if (!detached() && control?.isConnected && typeof card.render === "function") card.render();
      return false;
    }
    return !detached() && Boolean(control?.isConnected) && !card._writing;
  };

  const localButton = (label, action, primary = false, draft = null) => {
    let btn;
    if (typeof card.button === "function") {
      btn = card.button(label, () => { if (guard(btn, draft)) action(); }, primary);
    } else {
      btn = node("button", label, primary ? "primary" : "");
      btn.addEventListener("click", () => { if (guard(btn, draft)) action(); });
    }
    btn.type = "button";
    if (card._writing) btn.disabled = true;
    return btn;
  };

  const close = (draft) => {
    if (!guard(body, draft, false)) return;
    card._networkWatchDraft = null;
    card._actionError = null;
    if (typeof card.render === "function") card.render();
  };

  const run = async (draft) => {
    if (!guard(body, draft, !draft.pending)) return;
    if (!draft.pending) {
      const payload = {
        actor_revision: draft.source.actor_revision,
        watch_revision: draft.source.watch_revision,
        enabled: draft.desired,
        min_interval_minutes: draft.minIntervalMinutes,
      };
      if (draft.desired) payload.observation_token = draft.token;
      draft.pending = deepFreeze({
        action: "mikrotik.admission_watch_set",
        payload,
        operation_id: createOperationId(),
      });
    }
    const pending = draft.pending;
    try {
      await card.command(pending.action, pending.payload, pending.operation_id);
    } catch (err) {
      if (!card._actionError) card._actionError = err?.code || "failure";
    }
    const w = watch(card);
    const expRev = (draft.source.watch_revision || 0) + 1;
    if (sameAccess(card, draft.access, true) && card._networkWatchDraft === draft && w && w.watch_revision === expRev && w.enabled === draft.desired && !card._actionError) {
      card._networkWatchDraft = null;
      if (typeof card.render === "function") card.render();
    }
  };

  const section = node("section", null, "network-watch");
  section.append(node("style", STYLE));
  const guide = node("details", null, "network-watch-guide");
  guide.append(node("summary", copy.guide), node("p", copy.help, "sub"));
  section.append(guide);

  const draft = card._networkWatchDraft;
  if (draft) {
    const review = node("form", null, "item network-watch-review");
    review.append(node("h3", copy.review_title));
    const noticeText = !draft.desired ? copy.notice_disable : draft.source.capacity_blocked ? copy.notice_capacity_reset : copy.notice_enable_reconfigure;
    review.append(node("p", noticeText, "sub"));

    const details = node("dl");
    const choiceText = !draft.desired ? copy.disable_choice : draft.source.capacity_blocked ? copy.reset_choice : draft.source.enabled ? copy.reconfigure_choice : copy.enable_choice;
    details.append(node("dt", copy.choice), node("dd", choiceText), node("dt", copy.watch_version), node("dd", draft.source.watch_revision ?? copy.absent));
    review.append(details);

    let intervalInput = null;
    if (draft.desired) {
      const fieldWrap = node("label", null, "network-watch-field");
      fieldWrap.append(node("span", copy.interval_input));
      intervalInput = node("input");
      Object.assign(intervalInput, {
        type: "number", name: "min_interval_minutes", min: "5", max: "1440", step: "1",
        required: true, value: String(draft.minIntervalMinutes), disabled: Boolean(draft.pending),
      });
      fieldWrap.append(intervalInput, node("p", copy.interval_help, "sub"));
      review.append(fieldWrap);
    }

    const confirmWrap = node("label", null, "network-watch-confirm");
    const checkbox = node("input");
    Object.assign(checkbox, {
      type: "checkbox", name: "confirmed", required: true,
      disabled: Boolean(draft.pending), checked: Boolean(draft.pending),
    });
    confirmWrap.append(checkbox, node("span", draft.desired ? copy.confirm_baseline : copy.confirm_disable));
    review.append(confirmWrap);

    const validate = () => {
      if (draft.pending) return true;
      if (!checkbox.checked) return false;
      if (draft.desired && intervalInput) {
        const val = Number(intervalInput.value);
        return Number.isSafeInteger(val) && val >= 5 && val <= 1440;
      }
      return true;
    };

    const actions = node("div", null, "network-watch-actions");
    let running = false;
    const submitAction = () => {
      if (running || !validate()) return;
      if (draft.desired && !draft.pending && intervalInput) {
        const val = Number(intervalInput.value);
        if (Number.isSafeInteger(val) && val >= 5 && val <= 1440) draft.minIntervalMinutes = val;
        else return;
      }
      running = true;
      run(draft).finally(() => { running = false; });
    };

    const submit = localButton(draft.pending ? copy.retry : copy.save, submitAction, true, draft);
    submit.type = "submit";
    submit.disabled = !validate() || Boolean(card._writing);

    if (!draft.pending) {
      checkbox.addEventListener("change", () => {
        if (guard(checkbox, draft, false)) submit.disabled = !validate() || Boolean(card._writing);
      });
      if (intervalInput) {
        intervalInput.addEventListener("input", () => {
          if (!guard(intervalInput, draft, false)) return;
          const val = Number(intervalInput.value);
          if (Number.isSafeInteger(val) && val >= 5 && val <= 1440) draft.minIntervalMinutes = val;
          submit.disabled = !validate() || Boolean(card._writing);
        });
      }
    }

    actions.append(submit, localButton(copy.cancel, () => close(draft), false, draft));
    review.append(actions);
    review.addEventListener("submit", (e) => {
      e.preventDefault();
      if (!submit.disabled && guard(review, draft)) submitAction();
    });
    section.append(review);
    body.append(section);
    return;
  }

  const w = watch(card), adm = admission(card);
  const observing = w.effective && adm.status === "fresh";
  const cardItem = node("article", null, "item network-watch-card");
  cardItem.append(node("strong", copy.title));

  const statusBadge = node(
    "span",
    w.enabled ? (observing ? copy.effective_active : copy.effective_suspended) : copy.effective_disabled,
    `network-watch-badge ${w.enabled ? (observing ? "active" : "suspended") : "disabled"}`,
  );
  const statusP = node("p", `${copy.status}: `);
  statusP.append(statusBadge);
  cardItem.append(statusP);

  if (w.capacity_blocked) cardItem.append(node("div", copy.capacity_blocked_alert, "network-watch-alert warning"));

  const details = node("dl");
  details.append(
    node("dt", copy.tracked_count), node("dd", String(w.seen_count)),
    node("dt", copy.pending_count), node("dd", String(w.pending_count)),
    node("dt", copy.cadence), node("dd", `${w.min_interval_minutes} ${copy.minutes}`),
    node("dt", copy.baseline_at), node("dd", w.baseline_at ? new Date(w.baseline_at).toLocaleString() : copy.none),
    node("dt", copy.chat), node("dd", w.private_chat_ready ? copy.chat_ready : copy.chat_not_ready),
  );
  cardItem.append(details);

  const canEnable = Boolean(adm && adm.status === "fresh" && adm.token && w.private_chat_ready);
  const actions = node("div", null, "network-watch-actions");

  const openDraft = (desired, btn = null) => {
    const current = watch(card), currentAdm = admission(card);
    if (!guard(btn || cardItem) || !sameWatch(current, w)) return;
    if (desired && !canEnable) return;
    card._networkWatchDraft = {
      access: deepFreeze(clone(currentAccess)),
      source: deepFreeze(sourceSnapshot(w)),
      desired,
      minIntervalMinutes: w.min_interval_minutes || DEFAULT_INTERVAL,
      token: desired ? currentAdm.token : null,
      pending: null,
    };
    card._actionError = null;
    if (typeof card.render === "function") card.render();
  };

  if (w.enabled) {
    const editLabel = w.capacity_blocked ? copy.reset_capacity : copy.configure;
    const editBtn = localButton(editLabel, () => openDraft(true), w.capacity_blocked);
    if (!canEnable) editBtn.disabled = true;
    actions.append(
      editBtn,
      localButton(copy.disable, () => openDraft(false)),
    );
  } else {
    const enableBtn = localButton(copy.enable, () => openDraft(true, enableBtn), true);
    if (!canEnable) enableBtn.disabled = true;
    actions.append(enableBtn);
  }
  if (!canEnable) {
    cardItem.append(node("p", !w.private_chat_ready ? copy.chat_not_ready : copy.fresh_required, "sub"));
  }

  cardItem.append(actions);
  section.append(cardItem);
  body.append(section);
}
