/* Explicit self/guardian consent for nonurgent notification presence gating. */

import { PRESENCE_NOTIFICATIONS_COPY } from "./presence-notifications-copy.js";

const ROLES = new Set(["owner", "parent", "adult", "child"]);
const DEFAULT_WAIT_MINUTES = 720;

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

const STYLE = `
  .presence-notifications{display:grid;gap:12px}.presence-notifications-guide{margin:0}.presence-notifications-list{display:grid;gap:8px}
  .presence-notifications-self,.presence-notifications-managed-row,.presence-notifications-review{display:grid;gap:8px;min-width:0}
  .presence-notifications p,.presence-notifications dd{overflow-wrap:anywhere}.presence-notifications-self p,.presence-notifications-managed-row p,.presence-notifications-review p{margin:0}
  .presence-notifications-actions{display:flex;flex-wrap:wrap;gap:8px}.presence-notifications .presence-notifications-confirm{display:flex;flex-direction:row;justify-content:flex-start;gap:8px;align-items:flex-start}
  .presence-notifications-confirm input{flex:0 0 auto;margin-top:3px}.presence-notifications-review dl{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:6px 10px;margin:0}
  .presence-notifications-review dt{font-weight:600}.presence-notifications-review dd{margin:0}
  .presence-notifications-field{display:grid;gap:6px}
  .presence-notifications-field input{max-width:200px}
  @media(max-width:520px){.presence-notifications-actions>button{width:100%}.presence-notifications-review dl{grid-template-columns:minmax(0,1fr)}.presence-notifications-review dd{margin-bottom:4px}.presence-notifications-field input{max-width:100%}}
`;

function copyOf(card) {
  const language = card?._config?.language || card?._hass?.language || "en";
  return (
    PRESENCE_NOTIFICATIONS_COPY[language.split(/[-_]/)[0]] ||
    PRESENCE_NOTIFICATIONS_COPY.en
  );
}

function validRevision(value) {
  return Number.isSafeInteger(value) && value >= 1;
}

function validWait(value) {
  return Number.isSafeInteger(value) && value >= 15 && value <= 1440;
}

function canEdit(row) {
  return validRevision(row.binding_revision) &&
    (row.preference_revision === null || row.preference_revision < Number.MAX_SAFE_INTEGER);
}

function members(card) {
  return Array.isArray(card?._data?.members) ? card._data.members : [];
}

function member(card, id) {
  return members(card).find((item) => item?.id === id) || null;
}

function memberName(card, id, copy) {
  return member(card, id)?.name || copy.unavailable_member;
}

function notifications(card) {
  const value = card?._data?.presence?.notifications;
  return value && typeof value === "object" ? value : null;
}

function validRow(row) {
  return Boolean(
    row &&
    typeof row.member === "string" &&
    row.member &&
    validRevision(row.member_revision) &&
    (row.binding_revision === null || validRevision(row.binding_revision)) &&
    typeof row.source_available === "boolean" &&
    (row.preference_revision === null || validRevision(row.preference_revision)) &&
    typeof row.enabled === "boolean" &&
    typeof row.effective === "boolean" &&
    validWait(row.max_wait_minutes) &&
    (row.approved_by === null ||
      (typeof row.approved_by === "string" && row.approved_by)) &&
    (!row.source_available || validRevision(row.binding_revision)) &&
    (!row.enabled || (validRevision(row.preference_revision) && row.approved_by)) &&
    (!row.effective || (row.enabled && row.source_available)),
  );
}

function selfRow(card) {
  const row = notifications(card)?.self;
  const actor = member(card, card?._data?.actor);
  if (
    !validRow(row) ||
    row.member !== actor?.id ||
    row.member_revision !== actor?.revision
  )
    return null;
  return row;
}

function managedRows(card) {
  if (!["owner", "parent"].includes(card?._data?.role)) return [];
  const rows = notifications(card)?.managed;
  if (!Array.isArray(rows)) return [];
  const seen = new Set();
  return rows.filter((row) => {
    const current = member(card, row?.member);
    if (
      !validRow(row) ||
      current?.active !== true ||
      current.role !== "child" ||
      current.revision !== row.member_revision ||
      seen.has(row.member)
    )
      return false;
    seen.add(row.member);
    return true;
  });
}

function access(card) {
  const data = card?._data;
  const actor = member(card, data?.actor);
  const row = selfRow(card);
  if (
    !data?.actor ||
    !ROLES.has(data?.role) ||
    actor?.active !== true ||
    actor.role !== data.role ||
    !validRevision(actor.revision) ||
    !Array.isArray(data?.settings?.modules) ||
    !data.settings.modules.includes("presence") ||
    !row
  )
    return null;
  return {
    generation: card._generation ?? null,
    entry: card._entry ?? null,
    userId: card._hass?.user?.id ?? null,
    actor: data.actor,
    role: data.role,
    actorRevision: actor.revision,
  };
}

function sameAccess(card, expected) {
  const current = access(card);
  return (
    Boolean(current && expected) &&
    JSON.stringify(current) === JSON.stringify(expected)
  );
}

function sourceSnapshot(row) {
  return {
    member: row.member,
    member_revision: row.member_revision,
    binding_revision: row.binding_revision,
    source_available: row.source_available,
    preference_revision: row.preference_revision,
    enabled: row.enabled,
    effective: row.effective,
    max_wait_minutes: row.max_wait_minutes,
    approved_by: row.approved_by,
  };
}

function sameRow(left, right) {
  return Boolean(
    left &&
    right &&
    left.member === right.member &&
    left.member_revision === right.member_revision &&
    left.binding_revision === right.binding_revision &&
    left.source_available === right.source_available &&
    left.preference_revision === right.preference_revision &&
    left.enabled === right.enabled &&
    left.effective === right.effective &&
    left.max_wait_minutes === right.max_wait_minutes &&
    (left.approved_by ?? null) === (right.approved_by ?? null),
  );
}

function expectedRevision(source) {
  return source.preference_revision === null
    ? 1
    : source.preference_revision + 1;
}

function draftRow(card, draft) {
  return draft?.mode === "guardian"
    ? managedRows(card).find((row) => row.member === draft.source.member) || null
    : selfRow(card);
}

function pendingAllowed(card, draft) {
  if (!sameAccess(card, draft?.access) || !draft?.pending) return false;
  const current = draftRow(card, draft);
  if (
    !current ||
    current.member_revision !== draft.source.member_revision ||
    current.binding_revision !== draft.source.binding_revision
  )
    return false;
  return (
    sameRow(current, draft.source) ||
    (current.enabled === draft.desired &&
      current.preference_revision === expectedRevision(draft.source) &&
      current.max_wait_minutes === draft.maxWaitMinutes &&
      current.approved_by === draft.access.actor)
  );
}

function draftAllowed(card, draft, exact = true) {
  if (!sameAccess(card, draft?.access) || !draft?.source) return false;
  if (draft.pending) return pendingAllowed(card, draft);
  const current = draftRow(card, draft);
  return Boolean(current && (!exact || sameRow(current, draft.source)));
}

function projection(data) {
  const enabledModules = Array.isArray(data?.settings?.modules)
    ? data.settings.modules
    : [];
  const projectedMembers = Array.isArray(data?.members) ? data.members : [];
  const notifs = data?.presence?.notifications;
  const relevant = new Set([
    data?.actor,
    notifs?.self?.member,
    ...(Array.isArray(notifs?.managed)
      ? notifs.managed.map((row) => row?.member)
      : []),
  ]);
  return {
    actor: data?.actor ?? null,
    role: data?.role ?? null,
    module: enabledModules.includes("presence"),
    members: projectedMembers
      .filter((item) => relevant.has(item?.id))
      .map(({ id, name, role, active, revision }) => ({
        id,
        name,
        role,
        active,
        revision,
      })),
    notifications: notifs
      ? {
          self: notifs.self ?? null,
          managed: Array.isArray(notifs.managed) ? notifs.managed : null,
        }
      : null,
  };
}

export function reconcilePresenceNotificationsRefresh(card, previousData) {
  if (!card) return false;
  const changed =
    JSON.stringify(projection(previousData)) !==
    JSON.stringify(projection(card._data));
  let force =
    changed &&
    Boolean(
      card._presenceNotificationsDraft ||
        card.shadowRoot?.querySelector(".presence-notifications"),
    );
  if (
    card._presenceNotificationsDraft &&
    !draftAllowed(
      card,
      card._presenceNotificationsDraft,
      !card._presenceNotificationsDraft.pending,
    )
  ) {
    card._presenceNotificationsDraft = null;
    card._actionError = "conflict";
    force = true;
  }
  return force;
}

function appendDefinition(list, term, description) {
  list.append(node("dt", term), node("dd", description));
}

function appendRowDetails(card, item, row, copy) {
  const statusText = row.enabled
    ? row.effective
      ? copy.effective_active
      : copy.effective_suspended
    : copy.effective_disabled;
  item.append(
    node("p", `${copy.status}: ${statusText}`, "presence-notifications-status"),
  );

  const sourceText = row.source_available
    ? copy.source_available
    : copy.source_unavailable;
  item.append(
    node(
      "p",
      `${copy.source_status}: ${sourceText}`,
      "sub presence-notifications-source",
    ),
  );

  item.append(
    node(
      "p",
      `${copy.max_wait}: ${row.max_wait_minutes} ${copy.minutes}`,
      "sub presence-notifications-wait",
    ),
  );

  if (row.approved_by) {
    const approverName = memberName(card, row.approved_by, copy);
    item.append(
      node(
        "p",
        `${copy.approved_by}: ${approverName}`,
        "sub presence-notifications-approver",
      ),
    );
  }
}

export function renderPresenceNotifications(card, body) {
  if (!card || !body || !card._data) return;
  const currentAccess = access(card);
  if (!currentAccess) {
    card._presenceNotificationsDraft = null;
    return;
  }
  if (
    card._presenceNotificationsDraft &&
    !draftAllowed(
      card,
      card._presenceNotificationsDraft,
      !card._presenceNotificationsDraft.pending,
    )
  ) {
    card._presenceNotificationsDraft = null;
    card._actionError = "conflict";
  }

  const copy = copyOf(card);
  const detached = () => !body.isConnected;
  const guard = (control, draft = null, exact = true) => {
    if (draft && card._presenceNotificationsDraft !== draft) return false;
    if (
      !sameAccess(card, draft?.access || currentAccess) ||
      (draft && !draftAllowed(card, draft, exact && !draft.pending))
    ) {
      card._presenceNotificationsDraft = null;
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

  const close = (draft) => {
    if (!guard(body, draft, false)) return;
    card._presenceNotificationsDraft = null;
    card._actionError = null;
    if (typeof card.render === "function") card.render();
  };

  const run = async (draft) => {
    if (!guard(body, draft, !draft.pending)) return;
    if (!draft.pending) {
      draft.pending = deepFreeze({
        action:
          draft.mode === "guardian"
            ? "presence.guardian_notification_access_set"
            : "presence.notification_access_set",
        payload: {
          member: draft.source.member,
          member_revision: draft.source.member_revision,
          binding_revision: draft.source.binding_revision,
          preference_revision: draft.source.preference_revision,
          enabled: draft.desired,
          max_wait_minutes: draft.maxWaitMinutes,
          actor_member_revision: currentAccess.actorRevision,
        },
        operation_id: crypto.randomUUID(),
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
      card._presenceNotificationsDraft === draft &&
      !card._actionError
    ) {
      card._presenceNotificationsDraft = null;
      if (typeof card.render === "function") card.render();
    }
  };

  const section = node("section", null, "presence-notifications");
  section.append(node("style", STYLE));
  const guide = node("details", null, "presence-notifications-guide");
  guide.append(
    node("summary", copy.guide),
    node("p", copy.help, "sub"),
    node("p", copy.urgent_unchanged, "sub"),
    node("p", copy.unknown_and_cap, "sub"),
    node("p", copy.catchup, "sub"),
    node("p", copy.revocation_and_safety, "sub"),
  );
  section.append(guide);

  const draft = card._presenceNotificationsDraft;
  if (draft) {
    const review = node("form", null, "item presence-notifications-review");
    review.append(
      node(
        "h3",
        draft.mode === "guardian" ? copy.guardian_review : copy.review_title,
      ),
    );
    if (draft.mode === "guardian") {
      review.append(node("p", copy.guardian_help, "sub"));
    }
    const details = node("dl");
    appendDefinition(details, copy.person, draft.memberName);
    const choiceText = !draft.desired
      ? copy.disable_choice
      : draft.source.enabled
        ? copy.edit_choice
        : copy.enable_choice;
    appendDefinition(details, copy.choice, choiceText);
    appendDefinition(details, copy.member_version, draft.source.member_revision);
    appendDefinition(details, copy.binding_version, draft.source.binding_revision);
    appendDefinition(
      details,
      copy.preference_version,
      draft.source.preference_revision === null
        ? copy.absent
        : draft.source.preference_revision,
    );
    if (!draft.desired) {
      appendDefinition(
        details,
        copy.max_wait,
        `${draft.maxWaitMinutes} ${copy.minutes}`,
      );
    }
    review.append(details);

    let waitInput = null;
    if (draft.desired) {
      const waitWrap = node("label", null, "presence-notifications-field");
      waitWrap.append(node("span", copy.max_wait_input));
      waitInput = node("input");
      waitInput.type = "number";
      waitInput.name = "max_wait_minutes";
      waitInput.min = "15";
      waitInput.max = "1440";
      waitInput.step = "1";
      waitInput.required = true;
      waitInput.value = String(draft.maxWaitMinutes);
      waitInput.disabled = Boolean(draft.pending);
      waitWrap.append(waitInput);
      waitWrap.append(node("p", copy.max_wait_help, "sub"));
      review.append(waitWrap);
    }

    const confirmation = node(
      "label",
      null,
      "presence-notifications-confirm",
    );
    const checkbox = node("input");
    checkbox.type = "checkbox";
    checkbox.name = "confirmed";
    checkbox.required = true;
    checkbox.disabled = Boolean(draft.pending);
    if (draft.pending) checkbox.checked = true;
    confirmation.append(checkbox, node("span", copy.confirm));
    review.append(confirmation);

    const validate = () => {
      if (draft.pending) return true;
      if (!checkbox.checked) return false;
      if (draft.desired && waitInput) {
        const val = Number(waitInput.value);
        return Number.isSafeInteger(val) && val >= 15 && val <= 1440;
      }
      return true;
    };

    const actions = node("div", null, "presence-notifications-actions");
    let running = false;
    const submitAction = () => {
      if (running || !validate()) return;
      if (draft.desired && !draft.pending && waitInput) {
        const val = Number(waitInput.value);
        if (Number.isSafeInteger(val) && val >= 15 && val <= 1440) {
          draft.maxWaitMinutes = val;
        } else {
          return;
        }
      }
      running = true;
      run(draft).finally(() => {
        running = false;
      });
    };

    const submit = localButton(
      draft.pending ? copy.retry : copy.save,
      submitAction,
      true,
      draft,
    );
    submit.type = "submit";
    submit.disabled = !validate() || Boolean(card._writing);

    if (!draft.pending) {
      checkbox.addEventListener("change", () => {
        if (!guard(checkbox, draft)) return;
        submit.disabled = !validate() || Boolean(card._writing);
      });
      if (waitInput) {
        waitInput.addEventListener("input", () => {
          if (!guard(waitInput, draft)) return;
          const val = Number(waitInput.value);
          if (Number.isSafeInteger(val) && val >= 15 && val <= 1440) {
            draft.maxWaitMinutes = val;
          }
          submit.disabled = !validate() || Boolean(card._writing);
        });
      }
    }

    actions.append(
      submit,
      localButton(copy.cancel, () => close(draft), false, draft),
    );
    review.append(actions);

    review.addEventListener("submit", (event) => {
      event.preventDefault();
      if (!submit.disabled && guard(review, draft)) {
        submitAction();
      }
    });

    section.append(review);
    body.append(section);
    return;
  }

  const own = selfRow(card);
  const ownItem = node("article", null, "item presence-notifications-self");
  ownItem.dataset.presenceMember = own.member;
  ownItem.dataset.notificationMember = own.member;
  ownItem.append(
    node("h3", copy.your_preference),
    node("strong", memberName(card, own.member, copy)),
  );
  appendRowDetails(card, ownItem, own, copy);

  if (own.enabled) {
    if (canEdit(own)) {
      const disableBtn = localButton(copy.disable, () => {
        const current = selfRow(card);
        if (!guard(disableBtn) || !sameRow(current, own)) return;
        card._presenceNotificationsDraft = {
          kind: "review",
          mode: "self",
          access: deepFreeze(clone(currentAccess)),
          source: deepFreeze(sourceSnapshot(own)),
          desired: false,
          maxWaitMinutes: own.max_wait_minutes,
          memberName: memberName(card, own.member, copy),
          pending: null,
        };
        card._actionError = null;
        if (typeof card.render === "function") card.render();
      });
      ownItem.append(disableBtn);
    }
    if (own.source_available && canEdit(own)) {
      const editBtn = localButton(copy.edit, () => {
        const current = selfRow(card);
        if (!guard(editBtn) || !sameRow(current, own)) return;
        card._presenceNotificationsDraft = {
          kind: "review",
          mode: "self",
          access: deepFreeze(clone(currentAccess)),
          source: deepFreeze(sourceSnapshot(own)),
          desired: true,
          maxWaitMinutes: own.max_wait_minutes,
          memberName: memberName(card, own.member, copy),
          pending: null,
        };
        card._actionError = null;
        if (typeof card.render === "function") card.render();
      });
      ownItem.append(editBtn);
    }
  } else if (own.source_available && canEdit(own)) {
    const enableBtn = localButton(
      copy.enable,
      () => {
        const current = selfRow(card);
        if (!guard(enableBtn) || !sameRow(current, own)) return;
        card._presenceNotificationsDraft = {
          kind: "review",
          mode: "self",
          access: deepFreeze(clone(currentAccess)),
          source: deepFreeze(sourceSnapshot(own)),
          desired: true,
          maxWaitMinutes: own.max_wait_minutes || DEFAULT_WAIT_MINUTES,
          memberName: memberName(card, own.member, copy),
          pending: null,
        };
        card._actionError = null;
        if (typeof card.render === "function") card.render();
      },
      true,
    );
    ownItem.append(enableBtn);
  } else {
    ownItem.append(node("p", copy.unavailable_action, "sub"));
  }
  section.append(ownItem);

  if (["owner", "parent"].includes(card._data.role)) {
    const managed = managedRows(card);
    if (managed.length) {
      section.append(
        node("h3", copy.managed_children),
        node("p", copy.guardian_help, "sub"),
      );
      const list = node(
        "div",
        null,
        "presence-notifications-list presence-notifications-managed",
      );
      for (const row of managed) {
        const item = node(
          "article",
          null,
          "item presence-notifications-managed-row",
        );
        item.dataset.presenceMember = row.member;
        item.dataset.notificationMember = row.member;
        item.append(node("strong", memberName(card, row.member, copy)));
        appendRowDetails(card, item, row, copy);

        if (row.enabled) {
          if (canEdit(row)) {
            const disableBtn = localButton(copy.disable, () => {
              const current = managedRows(card).find(
                (value) => value.member === row.member,
              );
              if (!guard(disableBtn) || !sameRow(current, row)) return;
              card._presenceNotificationsDraft = {
                kind: "review",
                mode: "guardian",
                access: deepFreeze(clone(currentAccess)),
                source: deepFreeze(sourceSnapshot(row)),
                desired: false,
                maxWaitMinutes: row.max_wait_minutes,
                memberName: memberName(card, row.member, copy),
                pending: null,
              };
              card._actionError = null;
              if (typeof card.render === "function") card.render();
            });
            item.append(disableBtn);
          }
          if (row.source_available && canEdit(row)) {
            const editBtn = localButton(copy.edit, () => {
              const current = managedRows(card).find(
                (value) => value.member === row.member,
              );
              if (!guard(editBtn) || !sameRow(current, row)) return;
              card._presenceNotificationsDraft = {
                kind: "review",
                mode: "guardian",
                access: deepFreeze(clone(currentAccess)),
                source: deepFreeze(sourceSnapshot(row)),
                desired: true,
                maxWaitMinutes: row.max_wait_minutes,
                memberName: memberName(card, row.member, copy),
                pending: null,
              };
              card._actionError = null;
              if (typeof card.render === "function") card.render();
            });
            item.append(editBtn);
          }
        } else if (row.source_available && canEdit(row)) {
          const enableBtn = localButton(
            copy.enable,
            () => {
              const current = managedRows(card).find(
                (value) => value.member === row.member,
              );
              if (!guard(enableBtn) || !sameRow(current, row)) return;
              card._presenceNotificationsDraft = {
                kind: "review",
                mode: "guardian",
                access: deepFreeze(clone(currentAccess)),
                source: deepFreeze(sourceSnapshot(row)),
                desired: true,
                maxWaitMinutes: row.max_wait_minutes || DEFAULT_WAIT_MINUTES,
                memberName: memberName(card, row.member, copy),
                pending: null,
              };
              card._actionError = null;
              if (typeof card.render === "function") card.render();
            },
            true,
          );
          item.append(enableBtn);
        } else {
          item.append(node("p", copy.unavailable_action, "sub"));
        }
        list.append(item);
      }
      section.append(list);
    }
  }

  body.append(section);
}
