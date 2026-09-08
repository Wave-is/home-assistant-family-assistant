/* Local network admission review: local ledger approvals only; no router writes or enforcement. */

import { NETWORK_ADMISSION_COPY } from "./network-admission-copy.js";
import { ERRORS } from "./errors.js";

const ROLES = new Set(["owner", "parent"]);

const node = (tag, value, className) => {
  const result = document.createElement(tag);
  if (value !== undefined && value !== null) result.textContent = String(value);
  if (className) result.className = className;
  return result;
};

const clone = (value) => JSON.parse(JSON.stringify(value));

const deepFreeze = (value) => {
  if (!value || typeof value !== "object" || Object.isFrozen(value))
    return value;
  Object.freeze(value);
  for (const child of Object.values(value)) deepFreeze(child);
  return value;
};

const createOperationId = () =>
  typeof crypto?.randomUUID === "function"
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;

const STYLE = `
  .network-admission { display: grid; gap: 12px; }
  .network-admission-guide { margin: 0; }
  .network-admission-header { display: grid; gap: 6px; }
  .network-admission-meta { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
  .network-admission-badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 12px; font-weight: 600; }
  .network-admission-badge.fresh { background: rgba(30,140,60,.15); color: #1e8c3c; }
  .network-admission-badge.stale { background: rgba(220,130,0,.15); color: #dc8200; }
  .network-admission-badge.unavailable { background: rgba(200,40,40,.15); color: #c82828; }
  .network-admission-badge.protected { background: rgba(70,100,180,.15); color: #4664b4; }
  .network-admission-badge.approved { background: rgba(30,140,60,.15); color: #1e8c3c; }
  .network-admission-badge.unreviewed { background: rgba(140,140,140,.15); color: #666; }
  .network-admission-badge.preview { background: rgba(180,100,20,.15); color: #b46414; }
  .network-admission-badge.applied { background: rgba(30,140,60,.15); color: #1e8c3c; }
  .network-admission-badge.cancelled { background: rgba(140,140,140,.15); color: #888; }
  .network-admission-alert { padding: 10px 14px; border-radius: 8px; border: 1px solid; }
  .network-admission-alert.warning { background: rgba(240,160,20,.1); border-color: rgba(240,160,20,.3); }
  .network-admission-alert.error { background: rgba(220,40,40,.1); border-color: rgba(220,40,40,.3); color: #c82828; }
  .network-admission-alert.info { background: rgba(30,140,220,.1); border-color: rgba(30,140,220,.3); }
  .network-admission-card { border: 1px solid var(--divider-color, #e0e0e0); border-radius: 10px; padding: 12px; display: grid; gap: 8px; min-width: 0; }
  .network-admission-card p, .network-admission-card dd { overflow-wrap: anywhere; margin: 0; }
  .network-admission-card dl { display: grid; grid-template-columns: max-content minmax(0, 1fr); gap: 6px 10px; margin: 0; }
  .network-admission-card dt { font-weight: 600; }
  .network-admission-card dd { margin: 0; }
  .network-admission-mac { font-family: monospace; font-size: 13px; }
  .network-admission-actions { display: flex; flex-wrap: wrap; gap: 8px; }
  .network-admission-checkbox-wrap { display: flex; flex-direction: row; align-items: flex-start; gap: 8px; cursor: pointer; }
  .network-admission-checkbox-wrap input { flex: 0 0 auto; margin-top: 3px; }
  .network-admission-field { display: grid; gap: 6px; }
  .network-admission-field input { width: 100%; max-width: 340px; box-sizing: border-box; padding: 6px 10px; border: 1px solid var(--divider-color, #ccc); border-radius: 6px; font-size: 14px; }
  .network-admission-warning-tag { font-size: 11px; padding: 2px 6px; border-radius: 4px; background: rgba(220,100,0,.12); color: #b45000; margin-right: 4px; margin-bottom: 2px; display: inline-block; }
  .network-admission-plans { display: grid; gap: 8px; }
  .network-admission-devices { display: grid; gap: 8px; }
  @media(max-width: 520px) {
    .network-admission-actions > button { width: 100%; }
    .network-admission-card dl { grid-template-columns: minmax(0, 1fr); }
    .network-admission-card dd { margin-bottom: 4px; }
    .network-admission-field input { max-width: 100%; }
  }
`;

function copyOf(card) {
  const language = card?._config?.language || card?._hass?.language || "en";
  const prefix = String(language).split(/[-_]/)[0].toLowerCase();
  return NETWORK_ADMISSION_COPY[prefix] || NETWORK_ADMISSION_COPY.en;
}

function validRevision(value) {
  return Number.isSafeInteger(value) && value >= 1;
}

function members(card) {
  return Array.isArray(card?._data?.members) ? card._data.members : [];
}

function member(card, id) {
  return members(card).find((item) => item?.id === id) || null;
}

function admission(card) {
  const value = card?._data?.network?.admission;
  return value && typeof value === "object" ? value : null;
}

function access(card) {
  const data = card?._data;
  const actor = member(card, data?.actor);
  const adm = admission(card);
  if (
    !data?.actor ||
    !ROLES.has(data?.role) ||
    actor?.active !== true ||
    actor.role !== data.role ||
    !validRevision(actor.revision) ||
    !Array.isArray(data?.settings?.modules) ||
    !data.settings.modules.includes("mikrotik") ||
    !adm
  ) {
    return null;
  }
  return {
    generation: card._generation ?? null,
    entry: card._entry ?? null,
    userId: card._hass?.user?.id ?? null,
    actor: data.actor,
    role: data.role,
    actorRevision: actor.revision,
    token: adm.token ?? null,
    policyRevision: adm.policy_revision ?? null,
    backend: adm.backend ?? null,
    backendChanged: Boolean(adm.backend_changed),
    status: adm.status ?? null,
  };
}

function sameAccess(card, expected) {
  const current = access(card);
  return (
    Boolean(current && expected) &&
    JSON.stringify(current) === JSON.stringify(expected)
  );
}

function draftAllowed(card, draft, exact = true) {
  if (!sameAccess(card, draft?.access) || !draft?.mac) return false;
  const adm = admission(card);
  if (!adm || adm.status !== "fresh" || adm.can_edit !== true || card._data.role !== "owner") return false;
  const devices = Array.isArray(adm.devices) ? adm.devices : [];
  const dev = devices.find((d) => d.mac === draft.mac);
  if (!dev || dev.status === "protected") return false;
  if (exact && draft.deviceSnapshot) {
    if (
      dev.status !== draft.deviceSnapshot.status ||
      (dev.label ?? null) !== (draft.deviceSnapshot.label ?? null)
    ) {
      return false;
    }
  }
  return true;
}

function admissionProjection(data) {
  const modules = Array.isArray(data?.settings?.modules) ? data.settings.modules : [];
  const actor = data?.actor ?? null;
  const currentMember = Array.isArray(data?.members)
    ? data.members.find((m) => m?.id === actor)
    : null;
  const adm = data?.network?.admission;
  return {
    mikrotik: modules.includes("mikrotik"),
    actor,
    role: data?.role ?? null,
    actorActive: currentMember?.active ?? null,
    actorRevision: currentMember?.revision ?? null,
    admission: adm
      ? {
          status: adm.status ?? null,
          backend: adm.backend ?? null,
          token: adm.token ?? null,
          policy_revision: adm.policy_revision ?? null,
          backend_changed: adm.backend_changed ?? null,
          can_edit: adm.can_edit ?? null,
          counts: adm.counts ?? null,
          devices: Array.isArray(adm.devices)
            ? adm.devices.map((d) => ({
                mac: d.mac,
                status: d.status,
                label: d.label ?? null,
                warnings: Array.isArray(d.warnings) ? [...d.warnings] : [],
              }))
            : null,
          plans: Array.isArray(adm.plans)
            ? adm.plans.map((p) => ({
                id: p.id,
                status: p.status,
                policy_revision: p.policy_revision,
                expires_at: p.expires_at,
                applicable: p.applicable,
                changes: p.changes,
              }))
            : null,
        }
      : null,
  };
}

export function reconcileNetworkAdmissionRefresh(card, previousData) {
  if (!card) return false;
  const changed =
    JSON.stringify(admissionProjection(previousData)) !==
    JSON.stringify(admissionProjection(card._data));
  let force =
    changed &&
    Boolean(
      card._admissionDraft ||
        (card._admissionPlanPending && Object.keys(card._admissionPlanPending).length > 0) ||
        card.shadowRoot?.querySelector(".network-admission"),
    );

  const adm = admission(card);
  if (changed) card._admissionPlanConfirm = {};

  // Reconcile draft
  if (card._admissionDraft) {
    const draft = card._admissionDraft;
    if (draft.pending) {
      if (!sameAccess(card, draft.access) || adm?.status !== "fresh") {
        card._admissionDraft = null;
        card._actionError = "conflict";
        force = true;
      }
    } else {
      if (!draftAllowed(card, draft, true)) {
        card._admissionDraft = null;
        card._actionError = "conflict";
        force = true;
      }
    }
  }

  // Reconcile pending plan actions
  if (card._admissionPlanPending && typeof card._admissionPlanPending === "object") {
    for (const key of Object.keys(card._admissionPlanPending)) {
      const pending = card._admissionPlanPending[key];
      if (!pending) continue;
      const planId = pending.payload?.id;
      const plans = Array.isArray(adm?.plans) ? adm.plans : [];
      const plan = plans.find((p) => p.id === planId);

      if (pending.action === "mikrotik.admission_apply") {
        if (
          plan?.status === "applied"
        ) {
          delete card._admissionPlanPending[key];
          if (card._admissionPlanConfirm) delete card._admissionPlanConfirm[planId];
          force = true;
        } else if (
          !sameAccess(card, pending.access) ||
          !plan ||
          plan.status !== "preview" ||
          (plan.expires_at && new Date(plan.expires_at).getTime() <= Date.now())
        ) {
          delete card._admissionPlanPending[key];
          card._actionError = "conflict";
          force = true;
        }
      } else if (pending.action === "mikrotik.admission_cancel") {
        if (plan?.status === "cancelled") {
          delete card._admissionPlanPending[key];
          force = true;
        } else if (!sameAccess(card, pending.access) || !plan || plan.status !== "preview") {
          delete card._admissionPlanPending[key];
          card._actionError = "conflict";
          force = true;
        }
      }
    }
  }

  return force;
}

function appendDefinition(list, term, description) {
  const value = node("dd");
  if (description instanceof window.Node) value.append(description);
  else value.textContent = String(description ?? "");
  list.append(node("dt", term), value);
}

function warningText(copy, warn) {
  switch (warn) {
    case "locally_administered":
      return copy.warning_locally_administered;
    case "multiple_addresses":
      return copy.warning_multiple_addresses;
    case "ambiguous_identity":
      return copy.warning_ambiguous_identity;
    case "unknown_device":
      return copy.warning_unknown_device;
    default:
      return warn;
  }
}

function actionErrorText(copy, err, card) {
  if (!err) return "";
  switch (err) {
    case "conflict":
      return copy.action_error_conflict;
    case "proposal_expired":
      return copy.action_error_proposal_expired;
    case "network_conflict":
      return copy.action_error_network_conflict;
    case "network_confirmation":
      return copy.action_error_network_confirmation;
    default:
      return (ERRORS[String(card._config?.language || card._hass?.language || "en").split(/[-_]/)[0]] || ERRORS.en)[err] || copy.action_error_failure;
  }
}

export function renderNetworkAdmission(card, body) {
  if (!card || !body || !card._data) return;
  const currentAccess = access(card);
  if (!currentAccess) {
    card._admissionDraft = null;
    return;
  }

  const adm = admission(card);
  if (!adm) {
    card._admissionDraft = null;
    return;
  }

  if (card._admissionDraft && !draftAllowed(card, card._admissionDraft, !card._admissionDraft.pending)) {
    card._admissionDraft = null;
    card._actionError = "conflict";
  }

  const copy = copyOf(card);
  const isOwner = currentAccess.role === "owner";
  const isFresh = adm.status === "fresh";
  const canEdit = isOwner && isFresh && adm.can_edit === true;
  const detached = () => !body.isConnected;

  const guard = (control, draft = null, exact = true) => {
    if (draft && card._admissionDraft !== draft) return false;
    if (
      !sameAccess(card, draft?.access || currentAccess) ||
      (draft && !draftAllowed(card, draft, exact && !draft.pending))
    ) {
      card._admissionDraft = null;
      card._actionError = "conflict";
      if (!detached() && control?.isConnected && typeof card.render === "function") {
        card.render();
      }
      return false;
    }
    return !detached() && Boolean(control?.isConnected) && !card._writing;
  };

  const localButton = (label, action, primary = false, draft = null) => {
    let button;
    if (typeof card.button === "function") {
      button = card.button(
        label,
        () => {
          if (guard(button, draft)) action();
        },
        primary,
      );
    } else {
      button = node("button", label, primary ? "primary" : "");
      button.addEventListener("click", () => {
        if (guard(button, draft)) action();
      });
    }
    button.type = "button";
    if (card._writing) button.disabled = true;
    return button;
  };

  const closeDraft = (draft) => {
    if (!guard(body, draft, false)) return;
    card._admissionDraft = null;
    card._actionError = null;
    if (typeof card.render === "function") card.render();
  };

  const startDraft = (device, actionType) => {
    if (!canEdit || device.status === "protected") return;
    card._admissionDraft = {
      access: clone(currentAccess),
      mac: device.mac,
      actionType,
      label: actionType === "remove" ? "" : (device.label || device.candidate_name || ""),
      deviceSnapshot: {
        mac: device.mac,
        status: device.status,
        label: device.label ?? null,
      },
      replaceBackendConfirmed: false,
      pending: null,
    };
    card._actionError = null;
    if (typeof card.render === "function") card.render();
  };

  const runPreview = async (draft) => {
    if (!guard(body, draft, !draft.pending)) return;
    const latestAccess = access(card);
    if (!latestAccess) return;

    if (!draft.pending) {
      const trimmed = (draft.label || "").trim();
      if (draft.actionType !== "remove" && (!trimmed || trimmed.length > 160)) {
        return;
      }
      if (latestAccess.backendChanged && !draft.replaceBackendConfirmed) {
        return;
      }
      const change =
        draft.actionType === "remove"
          ? { mac: draft.mac, approved: false }
          : { mac: draft.mac, approved: true, label: trimmed };

      const payload = {
        actor_revision: latestAccess.actorRevision,
        observation_token: latestAccess.token,
        policy_revision: latestAccess.policyRevision,
        changes: [change],
      };
      if (draft.replaceBackendConfirmed && latestAccess.backendChanged) {
        payload.replace_backend = true;
      }
      draft.pending = deepFreeze({
        action: "mikrotik.admission_preview",
        payload,
        operation_id: createOperationId(),
        access: latestAccess,
      });
    }

    const pending = draft.pending;
    try {
      await card.command(pending.action, pending.payload, pending.operation_id);
    } catch (error) {
      if (!card._actionError) {
        card._actionError = error?.code || "failure";
      }
    }

    if (
      sameAccess(card, draft.access) &&
      card._admissionDraft === draft &&
      !card._actionError
    ) {
      card._admissionDraft = null;
      if (typeof card.render === "function") card.render();
    }
  };

  const runApply = async (plan, control) => {
    if (!guard(control)) return;
    const latestAccess = access(card);
    if (!latestAccess || latestAccess.role !== "owner") return;
    if (plan.applicable !== true || !Number.isFinite(Date.parse(plan.expires_at)) || Date.parse(plan.expires_at) <= Date.now()) return;
    if (card._admissionPlanPending?.[`cancel:${plan.id}`]) return;
    if (!card._admissionPlanConfirm?.[plan.id]) return;

    card._admissionPlanPending = card._admissionPlanPending || {};
    if (!card._admissionPlanPending[plan.id]) {
      const payload = {
        id: plan.id,
        actor_revision: latestAccess.actorRevision,
        confirmed: true,
      };
      card._admissionPlanPending[plan.id] = deepFreeze({
        action: "mikrotik.admission_apply",
        payload,
        operation_id: createOperationId(),
        access: latestAccess,
      });
    }

    const pending = card._admissionPlanPending[plan.id];
    if (!sameAccess(card, pending.access)) return;
    try {
      await card.command(pending.action, pending.payload, pending.operation_id);
    } catch (error) {
      if (!card._actionError) {
        card._actionError = error?.code || "failure";
      }
    }

    if (!card._actionError) {
      delete card._admissionPlanPending[plan.id];
      if (card._admissionPlanConfirm) delete card._admissionPlanConfirm[plan.id];
      if (typeof card.render === "function") card.render();
    }
  };

  const runCancel = async (plan, control) => {
    if (!guard(control)) return;
    const latestAccess = access(card);
    if (!latestAccess || latestAccess.role !== "owner") return;
    if (card._admissionPlanPending?.[plan.id]) return;

    const cancelKey = `cancel:${plan.id}`;
    card._admissionPlanPending = card._admissionPlanPending || {};
    if (!card._admissionPlanPending[cancelKey]) {
      const payload = {
        id: plan.id,
        actor_revision: latestAccess.actorRevision,
      };
      card._admissionPlanPending[cancelKey] = deepFreeze({
        action: "mikrotik.admission_cancel",
        payload,
        operation_id: createOperationId(),
        access: latestAccess,
      });
    }

    const pending = card._admissionPlanPending[cancelKey];
    if (!sameAccess(card, pending.access)) return;
    try {
      await card.command(pending.action, pending.payload, pending.operation_id);
    } catch (error) {
      if (!card._actionError) {
        card._actionError = error?.code || "failure";
      }
    }

    if (!card._actionError) {
      delete card._admissionPlanPending[cancelKey];
      if (typeof card.render === "function") card.render();
    }
  };

  const section = node("section", null, "network-admission");
  section.append(node("style", STYLE));

  // 1. Guide (How admission works)
  const guide = node("details", null, "network-admission-guide");
  guide.append(
    node("summary", copy.guide_title),
    node("p", copy.guide_record_only, "sub"),
    node("p", copy.guide_ha_suggestion, "sub"),
    node("p", copy.guide_no_router_writes, "sub"),
    node("p", copy.guide_enforcement, "sub"),
    node("p", copy.guide_audit_only, "sub"),
    node("p", copy.guide_backend_changed, "sub"),
  );
  section.append(guide);

  // 2. Header & Status
  const header = node("div", null, "network-admission-header");
  header.append(node("h3", copy.title));

  const meta = node("div", null, "network-admission-meta");
  const statusLabel =
    adm.status === "fresh"
      ? copy.status_fresh
      : adm.status === "stale"
      ? copy.status_stale
      : copy.status_unavailable;
  meta.append(node("span", statusLabel, `network-admission-badge ${adm.status || "unavailable"}`));
  meta.append(node("span", copy.mode_audit_only, "network-admission-badge unreviewed"));
  meta.append(node("span", copy.enforcement_disabled, "network-admission-badge unreviewed"));
  header.append(meta);

  // Summary counts
  const total = Array.isArray(adm.devices) ? adm.devices.length : 0;
  const countsText = copy.counts_summary
    .replace("{total}", String(total))
    .replace("{approved}", String(adm.counts?.approved ?? 0))
    .replace("{unreviewed}", String(adm.counts?.unreviewed ?? 0))
    .replace("{protected}", String(adm.counts?.protected ?? 0));
  header.append(node("p", countsText, "sub"));

  section.append(header);

  // 3. Alerts
  if (adm.backend_changed) {
    section.append(node("div", copy.backend_changed_warning, "network-admission-alert warning"));
  }
  if (!isFresh) {
    section.append(node("div", copy.stale_warning, "network-admission-alert warning"));
  }
  if (!isOwner) {
    section.append(node("div", copy.read_only_note, "network-admission-alert info"));
  }
  if (card._actionError) {
    section.append(node("div", actionErrorText(copy, card._actionError, card), "network-admission-alert error"));
  }

  // 4. Draft Editor
  const draft = card._admissionDraft;
  if (draft) {
    const draftCard = node("div", null, "network-admission-card");
    const draftTitle =
      draft.actionType === "approve"
        ? copy.draft_approve_title
        : draft.actionType === "rename"
        ? copy.draft_rename_title
        : copy.draft_remove_title;
    draftCard.append(node("h4", draftTitle));

    const dl = node("dl");
    appendDefinition(dl, copy.mac_address, draft.mac);
    if (draft.deviceSnapshot?.label) {
      appendDefinition(dl, copy.record_label, draft.deviceSnapshot.label);
    }
    const dev = Array.isArray(adm.devices) ? adm.devices.find((d) => d.mac === draft.mac) : null;
    if (dev?.candidate_name) {
      appendDefinition(dl, copy.candidate_name, dev.candidate_name);
    }
    if (dev?.addresses && dev.addresses.length) {
      appendDefinition(dl, copy.ip_addresses, dev.addresses.join(", "));
    }
    draftCard.append(dl);

    if (draft.actionType === "remove") {
      draftCard.append(node("p", copy.draft_remove_confirm, "sub"));
    } else {
      const field = node("label", null, "network-admission-field");
      field.append(node("span", copy.label_input));
      const input = node("input");
      input.type = "text";
      input.maxLength = 160;
      input.value = draft.label || "";
      input.disabled = Boolean(draft.pending || card._writing);
      input.addEventListener("input", (e) => {
        if (draft.pending || !guard(input, draft)) return;
        draft.label = e.target.value;
        const valid = Boolean(draft.label && draft.label.trim().length >= 1 && draft.label.trim().length <= 160);
        const consentOk = !adm.backend_changed || draft.replaceBackendConfirmed;
        previewBtn.disabled = !valid || !consentOk || Boolean(card._writing);
      });
      field.append(input);
      field.append(node("span", copy.label_help, "sub"));
      draftCard.append(field);
    }

    if (adm.backend_changed) {
      const consentWrap = node("label", null, "network-admission-checkbox-wrap");
      const checkbox = node("input");
      checkbox.type = "checkbox";
      checkbox.checked = Boolean(draft.replaceBackendConfirmed);
      checkbox.disabled = Boolean(draft.pending || card._writing);
      checkbox.addEventListener("change", () => {
        if (draft.pending || !guard(checkbox, draft)) return;
        draft.replaceBackendConfirmed = checkbox.checked;
        const valid =
          draft.actionType === "remove" ||
          Boolean(draft.label && draft.label.trim().length >= 1 && draft.label.trim().length <= 160);
        const consentOk = !adm.backend_changed || draft.replaceBackendConfirmed;
        previewBtn.disabled = !valid || !consentOk || Boolean(card._writing);
      });
      consentWrap.append(checkbox, node("span", copy.backend_changed_consent));
      draftCard.append(consentWrap);
    }

    const actions = node("div", null, "network-admission-actions");
    const previewBtn = localButton(
      copy.preview_button,
      () => runPreview(draft),
      true,
      draft,
    );
    const labelValid =
      draft.actionType === "remove" ||
      Boolean(draft.label && draft.label.trim().length >= 1 && draft.label.trim().length <= 160);
    const consentValid = !adm.backend_changed || draft.replaceBackendConfirmed;
    previewBtn.disabled = !labelValid || !consentValid || Boolean(card._writing);

    actions.append(previewBtn);

    if (draft.pending) {
      const retryBtn = localButton(
        copy.retry_button,
        () => runPreview(draft),
        false,
        draft,
      );
      actions.append(retryBtn);
    }

    const cancelBtn = localButton(
      copy.cancel_button,
      () => closeDraft(draft),
      false,
      draft,
    );
    actions.append(cancelBtn);

    draftCard.append(actions);
    section.append(draftCard);
  }

  // 5. Persisted Plans
  const plansContainer = node("div", null, "network-admission-plans");
  plansContainer.append(node("h4", copy.plans_title));

  const plans = Array.isArray(adm.plans) ? adm.plans : [];
  if (plans.length === 0) {
    plansContainer.append(node("p", copy.no_plans, "sub"));
  } else {
    for (const plan of plans) {
      const planCard = node("div", null, "network-admission-card");
      const planHeader = node("div", null, "network-admission-meta");
      planHeader.append(node("strong", `${copy.plan_id}: ${plan.id}`));
      const statusClass =
        plan.status === "preview"
          ? "preview"
          : plan.status === "applied"
          ? "applied"
          : "cancelled";
      const statusText =
        plan.status === "preview"
          ? copy.plan_status_preview
          : plan.status === "applied"
          ? copy.plan_status_applied
          : copy.plan_status_cancelled;
      planHeader.append(node("span", statusText, `network-admission-badge ${statusClass}`));
      planCard.append(planHeader);

      const dl = node("dl");
      if (plan.expires_at) {
        appendDefinition(dl, copy.plan_expires, plan.expires_at);
      }
      if (validRevision(plan.policy_revision)) {
        appendDefinition(dl, copy.plan_policy_revision, String(plan.policy_revision));
      }
      planCard.append(dl);

      if (Array.isArray(plan.changes) && plan.changes.length > 0) {
        planCard.append(node("p", copy.plan_changes, "sub"));
        for (const change of plan.changes) {
          const changeDl = node("dl");
          appendDefinition(changeDl, copy.mac_address, change.mac);
          appendDefinition(changeDl, copy.plan_before, change.before?.label || copy.plan_no_label);
          appendDefinition(
            changeDl,
            copy.plan_after,
            change.after === null ? copy.plan_removed : change.after?.label || copy.plan_no_label,
          );
          planCard.append(changeDl);
        }
      }

      if (plan.backend_changed) {
        planCard.append(node("div", copy.backend_changed_warning, "network-admission-alert warning"));
      }

      // Preview Plan Action Controls (Owner only, fresh only)
      if (plan.status === "preview" && isOwner && canEdit) {
        const expired = plan.applicable !== true || !Number.isFinite(Date.parse(plan.expires_at)) || Date.parse(plan.expires_at) <= Date.now();
        const planConfirmWrap = node("label", null, "network-admission-checkbox-wrap");
        const planCheckbox = node("input");
        planCheckbox.type = "checkbox";
        card._admissionPlanConfirm = card._admissionPlanConfirm || {};
        planCheckbox.checked = Boolean(card._admissionPlanConfirm[plan.id]);
        planCheckbox.disabled = expired || Boolean(card._writing);

        planCheckbox.addEventListener("change", () => {
          if (expired || !guard(planCheckbox)) return;
          card._admissionPlanConfirm[plan.id] = planCheckbox.checked;
          applyBtn.disabled = !planCheckbox.checked || expired || Boolean(card._writing);
        });

        planConfirmWrap.append(planCheckbox, node("span", copy.plan_review_confirm));
        planCard.append(planConfirmWrap);

        const planActions = node("div", null, "network-admission-actions");
        const applyBtn = localButton(
          copy.apply_button,
          () => runApply(plan, applyBtn),
          true,
        );
        applyBtn.disabled = !planCheckbox.checked || expired || Boolean(card._writing);
        planActions.append(applyBtn);

        if (card._admissionPlanPending?.[plan.id]) {
          const retryApplyBtn = localButton(
            copy.retry_button,
            () => runApply(plan, retryApplyBtn),
            false,
          );
          planActions.append(retryApplyBtn);
        }

        const cancelBtn = localButton(
          copy.cancel_button,
          () => runCancel(plan, cancelBtn),
          false,
        );
        planActions.append(cancelBtn);

        const cancelKey = `cancel:${plan.id}`;
        if (card._admissionPlanPending?.[cancelKey]) {
          const retryCancelBtn = localButton(
            copy.retry_button,
            () => runCancel(plan, retryCancelBtn),
            false,
          );
          planActions.append(retryCancelBtn);
        }

        planCard.append(planActions);
      }

      plansContainer.append(planCard);
    }
  }
  section.append(plansContainer);

  // 6. Devices Inventory
  const devicesContainer = node("div", null, "network-admission-devices");
  devicesContainer.append(node("h4", copy.devices_title));

  const devices = Array.isArray(adm.devices) ? adm.devices : [];
  if (devices.length === 0) {
    devicesContainer.append(node("p", copy.empty_devices, "sub"));
  } else {
    for (const dev of devices) {
      const devCard = node("div", null, "network-admission-card");
      const devMeta = node("div", null, "network-admission-meta");
      devMeta.append(node("strong", dev.mac, "network-admission-mac"));

      const badgeClass =
        dev.status === "protected"
          ? "protected"
          : dev.status === "approved"
          ? "approved"
          : "unreviewed";
      const badgeText =
        dev.status === "protected"
          ? copy.status_protected
          : dev.status === "approved"
          ? copy.status_approved
          : copy.status_unreviewed;
      devMeta.append(node("span", badgeText, `network-admission-badge ${badgeClass}`));
      devCard.append(devMeta);

      const dl = node("dl");
      if (dev.label) {
        appendDefinition(dl, copy.record_label, dev.label);
      }
      if (dev.candidate_name) {
        appendDefinition(dl, copy.candidate_name, dev.candidate_name);
      }
      if (dev.addresses && dev.addresses.length) {
        appendDefinition(dl, copy.ip_addresses, dev.addresses.join(", "));
      }
      if (dev.warnings && dev.warnings.length) {
        const warnWrap = node("div");
        for (const w of dev.warnings) {
          warnWrap.append(node("span", warningText(copy, w), "network-admission-warning-tag"));
        }
        appendDefinition(dl, copy.record_status, warnWrap);
      }
      devCard.append(dl);

      // Row Actions: Owner only, fresh only, non-protected only
      if (canEdit && dev.status !== "protected") {
        const rowActions = node("div", null, "network-admission-actions");
        if (dev.status === "unreviewed") {
          rowActions.append(
            localButton(copy.approve_button, () => startDraft(dev, "approve"), true),
          );
        } else if (dev.status === "approved") {
          rowActions.append(
            localButton(copy.rename_button, () => startDraft(dev, "rename"), false),
          );
          rowActions.append(
            localButton(copy.remove_button, () => startDraft(dev, "remove"), false),
          );
        }
        devCard.append(rowActions);
      }

      devicesContainer.append(devCard);
    }
  }
  section.append(devicesContainer);

  body.append(section);
}
